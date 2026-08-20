import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

import config
from src.cost_tracker import CostTracker
from src.commodities_crypto import (
    analyze_commodities_and_crypto, analyze_batch, build_batches,
    max_tokens_for_batch, fetch_fear_greed,
    CommoditiesCryptoError, BatchTruncatedError,
    TOKENS_PER_ASSET_CC,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
BATCH_FIXTURE = FIXTURE_DIR / "mock_commodities_crypto_batch_response.json"


def _fake_result(text: str, output_tokens: int = 4000,
                  stop_reason: str = "end_turn",
                  web_search_calls: int = 2) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 4000
    r.output_tokens = output_tokens
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = config.CLAUDE_MODEL_SONNET
    r.web_search_calls = web_search_calls
    r.stop_reason = stop_reason
    return r


def _td(ticker: str, asset_class: str) -> dict:
    return {
        "ticker": ticker, "asset_class": asset_class, "name": "Gold",
        "price": 2380.0, "rsi_14": 60.0, "atr_pct": 1.2,
        "intraday_range_pct": 1.2, "above_sma50": 1.5,
        "macd_signal": "neutral", "volume_ratio": 1.0,
        "data_quality": "high",
    }


def _trend() -> dict:
    return {"trends": [], "trend_summary": "calm"}


def _policy() -> dict:
    return {"policy_risk_level": "low", "events": [], "summary": ""}


# ---------- build_batches() ----------


def test_build_batches_groups_by_asset_class():
    tds = [
        _td("GC=F", "commodity"), _td("SI=F", "commodity"),
        _td("CL=F", "commodity"),
        _td("BTC-USD", "crypto"), _td("ETH-USD", "crypto"),
        _td("SOL-USD", "crypto"), _td("XRP-USD", "crypto"),
    ]
    batches = build_batches(tds)
    sizes = sorted(len(b) for b in batches)
    assert sizes == [3, 4]
    classes = {td["asset_class"] for b in batches for td in b}
    assert classes == {"commodity", "crypto"}
    for b in batches:
        assert len({td["asset_class"] for td in b}) == 1


def test_build_batches_is_deterministic_within_class():
    tds = [_td("SI=F", "commodity"), _td("GC=F", "commodity")]
    batches = build_batches(tds)
    assert [td["ticker"] for td in batches[0]] == ["GC=F", "SI=F"]


def test_build_batches_empty_input():
    assert build_batches([]) == []


# ---------- max_tokens_for_batch() ----------


def test_max_tokens_for_batch_scales_with_size():
    assert max_tokens_for_batch(4) > max_tokens_for_batch(1)


def test_max_tokens_never_falls_below_per_asset_value():
    for n in range(1, 8):
        assert max_tokens_for_batch(n) / n >= TOKENS_PER_ASSET_CC


# ---------- analyze_batch() ----------


def test_analyze_batch_returns_one_analysis_per_asset():
    fake = _fake_result(BATCH_FIXTURE.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("GC=F", "commodity"), _td("SI=F", "commodity")]

    with patch("src.commodities_crypto.call_claude", return_value=fake) as cc:
        analyses, missing = analyze_batch(
            ticker_datas=batch, trend_context=_trend(), policy_context=_policy(),
            extra_context={"fear_greed_value": 62}, cost_tracker=tracker,
        )

    assert [a["ticker"] for a in analyses] == ["GC=F", "SI=F"]
    assert missing == []
    assert cc.call_args.kwargs["stream"] is True
    assert cc.call_args.kwargs["max_tokens"] == max_tokens_for_batch(2)


def test_analyze_batch_bills_cost_tracker():
    fake = _fake_result(BATCH_FIXTURE.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("GC=F", "commodity"), _td("SI=F", "commodity")]

    with patch("src.commodities_crypto.call_claude", return_value=fake):
        analyze_batch(
            ticker_datas=batch, trend_context=_trend(), policy_context=_policy(),
            extra_context={"fear_greed_value": 62}, cost_tracker=tracker,
        )
    assert tracker.input_tokens == 4000
    assert tracker.total_eur > 0


def test_analyze_batch_keeps_partial_results():
    """Spec 10 (uebernommen von deep_analysis): gelieferte Analysen werden
    IMMER genommen, ein fehlendes Asset wird gemeldet, nicht erfunden."""
    payload = json.loads(BATCH_FIXTURE.read_text())
    payload["results"] = payload["results"][:1]        # SI=F fehlt
    fake = _fake_result(json.dumps(payload))
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("GC=F", "commodity"), _td("SI=F", "commodity")]

    with patch("src.commodities_crypto.call_claude", return_value=fake):
        analyses, missing = analyze_batch(
            ticker_datas=batch, trend_context=_trend(), policy_context=_policy(),
            extra_context={}, cost_tracker=tracker,
        )

    assert [a["ticker"] for a in analyses] == ["GC=F"]
    assert missing == ["SI=F"]


def test_analyze_batch_raises_on_unparseable_response():
    fake = _fake_result("not json", output_tokens=10, web_search_calls=0)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.commodities_crypto.call_claude", return_value=fake):
        with pytest.raises(CommoditiesCryptoError):
            analyze_batch(
                ticker_datas=[_td("GC=F", "commodity")],
                trend_context=_trend(), policy_context=_policy(),
                extra_context={}, cost_tracker=tracker,
            )


def test_analyze_batch_raises_when_output_was_truncated():
    fake = _fake_result(
        BATCH_FIXTURE.read_text(), output_tokens=8000, stop_reason="max_tokens")
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.commodities_crypto.call_claude", return_value=fake):
        with pytest.raises(BatchTruncatedError, match="max_tokens"):
            analyze_batch(
                ticker_datas=[_td("GC=F", "commodity"), _td("SI=F", "commodity")],
                trend_context=_trend(), policy_context=_policy(),
                extra_context={}, cost_tracker=tracker,
            )


def test_analyze_batch_max_tokens_override_is_used():
    fake = _fake_result(BATCH_FIXTURE.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("GC=F", "commodity"), _td("SI=F", "commodity")]

    with patch("src.commodities_crypto.call_claude", return_value=fake) as cc:
        analyze_batch(
            ticker_datas=batch, trend_context=_trend(), policy_context=_policy(),
            extra_context={}, cost_tracker=tracker, max_tokens_override=99999,
        )
    assert cc.call_args.kwargs["max_tokens"] == 99999


# ---------- analyze_commodities_and_crypto() ----------


def test_analyze_commodities_and_crypto_runs_one_batch_per_asset_class():
    """7 Assets (3 commodity + 4 crypto) -> genau 2 call_claude-Aufrufe statt 7."""
    fake = _fake_result(BATCH_FIXTURE.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)
    tds = [
        _td("GC=F", "commodity"), _td("SI=F", "commodity"),
        _td("CL=F", "commodity"),
        _td("BTC-USD", "crypto"), _td("ETH-USD", "crypto"),
        _td("SOL-USD", "crypto"), _td("XRP-USD", "crypto"),
    ]

    with patch("src.commodities_crypto.call_claude", return_value=fake) as cc:
        analyze_commodities_and_crypto(
            ticker_datas=tds, trend_context=_trend(), policy_context=_policy(),
            extra_context={"fear_greed_value": 62}, cost_tracker=tracker,
        )
    assert cc.call_count == 2


def test_analyze_commodities_and_crypto_retries_once_then_succeeds():
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("GC=F", "commodity"), _td("SI=F", "commodity")]
    responses = [
        _fake_result("broken", output_tokens=10, web_search_calls=0),
        _fake_result(BATCH_FIXTURE.read_text()),
    ]

    with patch("src.commodities_crypto.call_claude", side_effect=responses) as cc:
        out = analyze_commodities_and_crypto(
            ticker_datas=batch, trend_context=_trend(), policy_context=_policy(),
            extra_context={}, cost_tracker=tracker,
        )
    assert cc.call_count == 2
    assert [a["ticker"] for a in out] == ["GC=F", "SI=F"]


def test_analyze_commodities_and_crypto_gives_up_after_two_failures():
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("GC=F", "commodity"), _td("SI=F", "commodity")]
    responses = [
        _fake_result("broken", output_tokens=10, web_search_calls=0),
        _fake_result("still broken", output_tokens=10, web_search_calls=0),
    ]

    with patch("src.commodities_crypto.call_claude", side_effect=responses):
        out = analyze_commodities_and_crypto(
            ticker_datas=batch, trend_context=_trend(), policy_context=_policy(),
            extra_context={}, cost_tracker=tracker,
        )
    assert out == []


def test_truncated_batch_is_retried_with_a_larger_ceiling():
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("GC=F", "commodity"), _td("SI=F", "commodity")]
    responses = [
        _fake_result(BATCH_FIXTURE.read_text(), output_tokens=8000,
                     stop_reason="max_tokens"),
        _fake_result(BATCH_FIXTURE.read_text()),
    ]

    with patch("src.commodities_crypto.call_claude", side_effect=responses) as cc:
        analyze_commodities_and_crypto(
            ticker_datas=batch, trend_context=_trend(), policy_context=_policy(),
            extra_context={}, cost_tracker=tracker,
        )
    first_ceiling = cc.call_args_list[0].kwargs["max_tokens"]
    second_ceiling = cc.call_args_list[1].kwargs["max_tokens"]
    assert second_ceiling == first_ceiling * 2


def test_analyze_commodities_and_crypto_cost_cap_propagates():
    from src.cost_tracker import CostCapExceeded
    tracker = CostTracker(hard_cap_eur=0.0001)
    fake = _fake_result(BATCH_FIXTURE.read_text())
    batch = [_td("GC=F", "commodity")]

    with patch("src.commodities_crypto.call_claude", return_value=fake):
        with pytest.raises(CostCapExceeded):
            analyze_commodities_and_crypto(
                ticker_datas=batch, trend_context=_trend(), policy_context=_policy(),
                extra_context={}, cost_tracker=tracker,
            )


# ---------- fetch_fear_greed() (unveraendert) ----------


def test_fetch_fear_greed_parses_alternative_me_format():
    with patch("src.commodities_crypto.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {
            "data": [{"value": "62", "value_classification": "Greed"}],
        }
        mock_get.return_value.raise_for_status = lambda: None
        out = fetch_fear_greed()
    assert out == {"value": 62, "label": "Greed"}


def test_fetch_fear_greed_returns_none_on_failure():
    with patch("src.commodities_crypto.requests.get",
               side_effect=Exception("network")):
        assert fetch_fear_greed() is None


# ---------- user message ----------


def test_user_message_includes_extra_context_keys():
    fake = _fake_result(BATCH_FIXTURE.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.commodities_crypto.call_claude", return_value=fake) as mock_call:
        analyze_batch(
            ticker_datas=[_td("BTC-USD", "crypto")],
            trend_context=_trend(), policy_context=_policy(),
            extra_context={"fear_greed_value": 62, "btc_dominance_pct": 54.2},
            cost_tracker=tracker,
        )
    user_msg = mock_call.call_args.kwargs["user"]
    assert "fear_greed_value" in user_msg
    assert "btc_dominance_pct" in user_msg


# ---------- prompt contract ----------


CC_V3 = Path(__file__).parent.parent.parent / "prompts" / "commodities_crypto_v3.txt"
CC_V2 = Path(__file__).parent.parent.parent / "prompts" / "commodities_crypto_v2.txt"


def test_commodities_crypto_v3_pins_contract():
    text = CC_V3.read_text()
    assert '"evidence_quality"' in text
    assert '"thin"' in text
    assert "higher is always better" in text.lower()
    # Batch-Format seit der Umstellung auf asset_class-Batches (2026-08-19):
    # der results-Wrapper MUSS da sein, anders als in v2.
    assert '"results"' in text


def test_commodities_crypto_v2_untouched():
    """Regel 10: v1/v2-Dateien werden nie ueberschrieben, neue Versionen sind
    neue Dateien. v2 bleibt auf der Platte, auch wenn das Modul jetzt v3 laedt."""
    text = CC_V2.read_text()
    assert '"results"' not in text


def test_commodities_crypto_module_uses_v3():
    import src.commodities_crypto as cc
    assert "evidence_quality" in cc.SYSTEM_PROMPT
    assert '"results"' in cc.SYSTEM_PROMPT
