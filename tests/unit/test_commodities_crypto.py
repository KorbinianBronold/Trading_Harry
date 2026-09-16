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
        _td("GOLD", "commodity"), _td("SILVER", "commodity"),
        _td("OIL_BRENT", "commodity"),
        _td("BTCUSD", "crypto"), _td("ETHUSD", "crypto"),
        _td("SOLUSD", "crypto"), _td("XRPUSD", "crypto"),
    ]
    batches = build_batches(tds)
    sizes = sorted(len(b) for b in batches)
    assert sizes == [3, 4]
    classes = {td["asset_class"] for b in batches for td in b}
    assert classes == {"commodity", "crypto"}
    for b in batches:
        assert len({td["asset_class"] for td in b}) == 1


def test_build_batches_is_deterministic_within_class():
    tds = [_td("SILVER", "commodity"), _td("GOLD", "commodity")]
    batches = build_batches(tds)
    assert [td["ticker"] for td in batches[0]] == ["GOLD", "SILVER"]


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
    batch = [_td("GOLD", "commodity"), _td("SILVER", "commodity")]

    with patch("src.commodities_crypto.call_claude", return_value=fake) as cc:
        analyses, missing = analyze_batch(
            date="2026-05-19", run_type="pre_market",
            ticker_datas=batch, trend_context=_trend(), policy_context=_policy(),
            extra_context={"fear_greed_value": 62}, cost_tracker=tracker,
        )

    assert [a["ticker"] for a in analyses] == ["GOLD", "SILVER"]
    assert missing == []
    assert cc.call_args.kwargs["stream"] is True
    assert cc.call_args.kwargs["max_tokens"] == max_tokens_for_batch(2)


def test_analyze_batch_bills_cost_tracker():
    fake = _fake_result(BATCH_FIXTURE.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("GOLD", "commodity"), _td("SILVER", "commodity")]

    with patch("src.commodities_crypto.call_claude", return_value=fake):
        analyze_batch(
            date="2026-05-19", run_type="pre_market",
            ticker_datas=batch, trend_context=_trend(), policy_context=_policy(),
            extra_context={"fear_greed_value": 62}, cost_tracker=tracker,
        )
    assert tracker.input_tokens == 4000
    assert tracker.total_eur > 0


def test_analyze_batch_keeps_partial_results():
    """Spec 10 (uebernommen von deep_analysis): gelieferte Analysen werden
    IMMER genommen, ein fehlendes Asset wird gemeldet, nicht erfunden."""
    payload = json.loads(BATCH_FIXTURE.read_text())
    payload["results"] = payload["results"][:1]        # SILVER fehlt
    fake = _fake_result(json.dumps(payload))
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("GOLD", "commodity"), _td("SILVER", "commodity")]

    with patch("src.commodities_crypto.call_claude", return_value=fake):
        analyses, missing = analyze_batch(
            date="2026-05-19", run_type="pre_market",
            ticker_datas=batch, trend_context=_trend(), policy_context=_policy(),
            extra_context={}, cost_tracker=tracker,
        )

    assert [a["ticker"] for a in analyses] == ["GOLD"]
    assert missing == ["SILVER"]


def test_analyze_batch_raises_on_unparseable_response():
    fake = _fake_result("not json", output_tokens=10, web_search_calls=0)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.commodities_crypto.call_claude", return_value=fake):
        with pytest.raises(CommoditiesCryptoError):
            analyze_batch(
            date="2026-05-19", run_type="pre_market",
                ticker_datas=[_td("GOLD", "commodity")],
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
            date="2026-05-19", run_type="pre_market",
                ticker_datas=[_td("GOLD", "commodity"), _td("SILVER", "commodity")],
                trend_context=_trend(), policy_context=_policy(),
                extra_context={}, cost_tracker=tracker,
            )


def test_analyze_batch_max_tokens_override_is_used():
    fake = _fake_result(BATCH_FIXTURE.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("GOLD", "commodity"), _td("SILVER", "commodity")]

    with patch("src.commodities_crypto.call_claude", return_value=fake) as cc:
        analyze_batch(
            date="2026-05-19", run_type="pre_market",
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
        _td("GOLD", "commodity"), _td("SILVER", "commodity"),
        _td("OIL_BRENT", "commodity"),
        _td("BTCUSD", "crypto"), _td("ETHUSD", "crypto"),
        _td("SOLUSD", "crypto"), _td("XRPUSD", "crypto"),
    ]

    with patch("src.commodities_crypto.call_claude", return_value=fake) as cc:
        analyze_commodities_and_crypto(
            date="2026-05-19", run_type="pre_market",
            ticker_datas=tds, trend_context=_trend(), policy_context=_policy(),
            extra_context={"fear_greed_value": 62}, cost_tracker=tracker,
        )
    assert cc.call_count == 2


def test_analyze_commodities_and_crypto_retries_once_then_succeeds():
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("GOLD", "commodity"), _td("SILVER", "commodity")]
    responses = [
        _fake_result("broken", output_tokens=10, web_search_calls=0),
        _fake_result(BATCH_FIXTURE.read_text()),
    ]

    with patch("src.commodities_crypto.call_claude", side_effect=responses) as cc:
        out = analyze_commodities_and_crypto(
            date="2026-05-19", run_type="pre_market",
            ticker_datas=batch, trend_context=_trend(), policy_context=_policy(),
            extra_context={}, cost_tracker=tracker,
        )
    assert cc.call_count == 2
    assert [a["ticker"] for a in out] == ["GOLD", "SILVER"]


def test_analyze_commodities_and_crypto_gives_up_after_two_failures():
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("GOLD", "commodity"), _td("SILVER", "commodity")]
    responses = [
        _fake_result("broken", output_tokens=10, web_search_calls=0),
        _fake_result("still broken", output_tokens=10, web_search_calls=0),
    ]

    with patch("src.commodities_crypto.call_claude", side_effect=responses):
        out = analyze_commodities_and_crypto(
            date="2026-05-19", run_type="pre_market",
            ticker_datas=batch, trend_context=_trend(), policy_context=_policy(),
            extra_context={}, cost_tracker=tracker,
        )
    assert out == []


def test_truncated_batch_is_retried_with_a_larger_ceiling():
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("GOLD", "commodity"), _td("SILVER", "commodity")]
    responses = [
        _fake_result(BATCH_FIXTURE.read_text(), output_tokens=8000,
                     stop_reason="max_tokens"),
        _fake_result(BATCH_FIXTURE.read_text()),
    ]

    with patch("src.commodities_crypto.call_claude", side_effect=responses) as cc:
        analyze_commodities_and_crypto(
            date="2026-05-19", run_type="pre_market",
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
    batch = [_td("GOLD", "commodity")]

    with patch("src.commodities_crypto.call_claude", return_value=fake):
        with pytest.raises(CostCapExceeded):
            analyze_commodities_and_crypto(
            date="2026-05-19", run_type="pre_market",
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
            date="2026-05-19", run_type="pre_market",
            ticker_datas=[_td("BTCUSD", "crypto")],
            trend_context=_trend(), policy_context=_policy(),
            extra_context={"fear_greed_value": 62, "btc_dominance_pct": 54.2},
            cost_tracker=tracker,
        )
    user_msg = mock_call.call_args.kwargs["user"]
    assert "fear_greed_value" in user_msg
    assert "btc_dominance_pct" in user_msg


# ---------- prompt contract ----------


CC_V3 = Path(__file__).parent.parent.parent / "prompts" / "commodities_crypto_v3.txt"


def test_commodities_crypto_v3_pins_contract():
    text = CC_V3.read_text()
    assert '"evidence_quality"' in text
    assert '"thin"' in text
    assert "higher is always better" in text.lower()
    # Batch-Format seit der Umstellung auf asset_class-Batches (2026-08-19):
    # der results-Wrapper MUSS da sein, anders als in v2.
    assert '"results"' in text


def test_commodities_crypto_module_uses_v3():
    import src.commodities_crypto as cc
    assert "evidence_quality" in cc.SYSTEM_PROMPT
    assert '"results"' in cc.SYSTEM_PROMPT


# --- C.43: Datumsanker (F33) und Quellen-/Beleg-Regel (F35) fuer Phase 3b ----

def test_analyze_batch_user_message_starts_with_the_date_anchor():
    """F33 (C.43): wie in Phase 3 (C.42) argumentiert der Prompt mit 'heute',
    die Nutzlast trug aber kein Datum."""
    fake = _fake_result(BATCH_FIXTURE.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.commodities_crypto.call_claude", return_value=fake) as mock_call:
        analyze_batch(
            ticker_datas=[_td("BTCUSD", "crypto")],
            trend_context=_trend(), policy_context=_policy(),
            extra_context={"fear_greed_value": 62},
            cost_tracker=tracker, date="2026-09-14", run_type="pre_market",
        )
    user_msg = mock_call.call_args.kwargs["user"]
    assert user_msg.startswith("Today is 2026-09-14. Run type: pre_market.")


def test_analyze_commodities_and_crypto_threads_the_date_through():
    """Der Orchestrator reicht date/run_type bis in den Call durch."""
    fake = _fake_result(BATCH_FIXTURE.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.commodities_crypto.call_claude", return_value=fake) as mock_call:
        analyze_commodities_and_crypto(
            ticker_datas=[_td("GOLD", "commodity")],
            trend_context=_trend(), policy_context=_policy(),
            extra_context={}, cost_tracker=tracker,
            date="2026-09-14", run_type="pre_market",
        )
    assert mock_call.call_args.kwargs["user"].startswith("Today is 2026-09-14.")


def test_commodities_crypto_v3_pins_the_c43_additions():
    """F33: TIME FRAME mit dem Unterschied zu Aktien (Gold/Oel/Krypto handeln
    schon, wenn der 09:00-ET-Lauf laeuft); F35: Kurs-Seiten sind keine Quelle,
    ein Beleg ohne Datum/Zahl/Quelle ausserhalb des Snapshots macht 'thin'."""
    text = CC_V3.read_text()
    assert "date given in the user message" in text
    assert "pre_market" in text
    assert "already trading" in text.lower()
    assert "quote page" in text.lower()
    assert "outside the snapshot" in text.lower()


# --- C.43: Snapshot-Filter (F37), Technik-Sidecar (F16), extra aus dem Code (F38)

def _batch_entries(user_msg: str) -> list[dict]:
    lines = user_msg.split("\n")
    start = lines.index("BATCH (one asset per line, JSON):") + 1
    return [json.loads(l) for l in lines[start:] if l.startswith("{")]


def test_batch_payload_strips_stock_only_fields_from_the_asset_snapshot():
    """F37: der 3b-Snapshot trug das volle Aktienschema -- pe_ratio/market_cap
    null, sector 'Unknown', data_quality 'medium' aus einer Aktien-Heuristik.
    Die Nutzlast laesst die Aktien-Schluessel weg; td selbst bleibt unangetastet
    (Sidecar-Invariante)."""
    from src.commodities_crypto import _build_batch_user_message
    td = {**_td("GOLD", "commodity"), "pe_ratio": None, "market_cap_b": None,
          "sector": "Unknown", "data_quality": "medium",
          "earnings_in_days": None, "analyst_consensus_period": None}
    before = dict(td)

    msg = _build_batch_user_message([td], _trend(), _policy(), {},
                                    date="2026-09-14", run_type="pre_market")

    assert td == before
    snap = _batch_entries(msg)[0]["snapshot"]
    for k in ("pe_ratio", "market_cap_b", "sector", "data_quality",
              "earnings_in_days", "analyst_consensus_period"):
        assert k not in snap, f"{k} gehoert nicht in den Rohstoff-Snapshot"
    assert snap["price"] == 2380.0
    assert snap["rsi_14"] == 60.0
    assert snap["asset_class"] == "commodity"


def test_batch_payload_carries_the_technical_signal_beside_the_snapshot():
    """F16 (C.34, offen seit dem 1b-Walkthrough): Phase 3 sieht das
    deterministische Technik-Signal, 3b sah nichts, obwohl rank_score es
    hinterher verrechnet. Gleicher Sidecar-Block wie in Phase 3."""
    from src.commodities_crypto import _build_batch_user_message
    msg = _build_batch_user_message(
        [_td("GOLD", "commodity")], _trend(), _policy(), {},
        date="2026-09-14", run_type="pre_market",
        signal_by_ticker={"GOLD": {"tech_direction": "long", "tech_strength": 3,
                                   "tech_agreement": 3}},
    )
    assert _batch_entries(msg)[0]["technical_signal"] == {
        "direction": "long", "strength": 3}


def test_batch_payload_without_sidecar_sends_an_empty_signal():
    from src.commodities_crypto import _build_batch_user_message
    msg = _build_batch_user_message(
        [_td("BTCUSD", "crypto")], _trend(), _policy(), {},
        date="2026-09-14", run_type="pre_market")
    assert _batch_entries(msg)[0]["technical_signal"] == {
        "direction": None, "strength": None}


def test_analyze_commodities_and_crypto_threads_the_signal_sidecar_through():
    fake = _fake_result(BATCH_FIXTURE.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.commodities_crypto.call_claude", return_value=fake) as mock_call:
        analyze_commodities_and_crypto(
            ticker_datas=[_td("GOLD", "commodity"), _td("SILVER", "commodity")],
            trend_context=_trend(), policy_context=_policy(),
            extra_context={}, cost_tracker=tracker,
            date="2026-09-14", run_type="pre_market",
            signal_by_ticker={"GOLD": {"tech_direction": "short", "tech_strength": 2}},
        )
    entries = _batch_entries(mock_call.call_args.kwargs["user"])
    by = {e["snapshot"]["ticker"]: e["technical_signal"] for e in entries}
    assert by["GOLD"] == {"direction": "short", "strength": 2}
    assert by["SILVER"] == {"direction": None, "strength": None}


def test_gold_silver_ratio_is_computed_from_the_two_snapshots():
    """F38: die Ratio ist Arithmetik ueber zwei Snapshots, kein Modell-Output."""
    from src.commodities_crypto import gold_silver_ratio
    assert gold_silver_ratio([{"ticker": "GOLD", "price": 4000.0},
                              {"ticker": "SILVER", "price": 50.0}]) == 80.0
    assert gold_silver_ratio([{"ticker": "GOLD", "price": 4000.0}]) is None
    assert gold_silver_ratio([{"ticker": "GOLD", "price": 4000.0},
                              {"ticker": "SILVER", "price": None}]) is None
    assert gold_silver_ratio([{"ticker": "GOLD", "price": 4000.0},
                              {"ticker": "SILVER", "price": 0.0}]) is None


def test_fetch_btc_dominance_parses_alternative_me_global_format():
    """C.44: der Endpunkt liefert unter dem Schluessel 'percentage' einen ANTEIL
    (Live-Sonde 2026-09-14: 0.638978 = 63,9 %). Die Pipeline fuehrt die
    Dominanz in Prozent (Mail: '{btc_dom}%'), also x100 -- dieselbe
    Einheitenfalle wie bei debt_equity (F39), nur umgekehrt."""
    from src.commodities_crypto import fetch_btc_dominance
    with patch("src.commodities_crypto.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {
            "data": {"bitcoin_percentage_of_market_cap": 0.638978074972638}}
        mock_get.return_value.raise_for_status = lambda: None
        out = fetch_btc_dominance()
    assert out == pytest.approx(63.9, abs=0.01)


def test_fetch_btc_dominance_returns_none_on_failure():
    from src.commodities_crypto import fetch_btc_dominance
    with patch("src.commodities_crypto.requests.get", side_effect=RuntimeError("down")):
        assert fetch_btc_dominance() is None


def test_extra_block_is_overwritten_with_the_supplied_context_values():
    """F38: was die Mail als Gold-Silber-Ratio und BTC-Dominanz zeigt, kommt aus
    dem Code, nicht aus dem Modell -- auch wenn das Modell andere Zahlen
    zurueckgibt."""
    payload = json.loads(BATCH_FIXTURE.read_text())
    payload["results"][0]["extra"] = {"fear_greed_value": 1,
                                      "gold_silver_ratio": 1.0,
                                      "btc_dominance_pct": 1.0}
    fake = _fake_result(json.dumps(payload))
    tracker = CostTracker(hard_cap_eur=10.0)
    ctx = {"fear_greed_value": 62, "fear_greed_label": "Greed",
           "gold_silver_ratio": 80.0, "btc_dominance_pct": 54.2}
    with patch("src.commodities_crypto.call_claude", return_value=fake):
        out = analyze_commodities_and_crypto(
            ticker_datas=[_td("GOLD", "commodity"), _td("SILVER", "commodity")],
            trend_context=_trend(), policy_context=_policy(),
            extra_context=ctx, cost_tracker=tracker,
            date="2026-09-14", run_type="pre_market",
        )
    assert out[0]["extra"] == {"fear_greed_value": 62, "gold_silver_ratio": 80.0,
                               "btc_dominance_pct": 54.2}


def test_commodities_crypto_v3_pins_the_sidecar_and_extra_contract():
    text = CC_V3.read_text()
    assert '"technical_signal"' in text
    assert "not your job" in text.lower()
    assert "EXTRA CONTEXT" in text
