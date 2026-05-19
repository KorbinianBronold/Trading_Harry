import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.cost_tracker import CostTracker
from src.commodities_crypto import (
    analyze_commodities_and_crypto, analyze_asset,
    fetch_fear_greed, CommoditiesCryptoError,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def _fake_result(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 4000
    r.output_tokens = 3000
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = "claude-sonnet-4-6"
    r.web_search_calls = 2
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


def test_analyze_asset_returns_parsed():
    payload = (FIXTURE_DIR / "mock_commodities_crypto_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.commodities_crypto.call_claude", return_value=fake):
        out = analyze_asset(
            ticker_data=_td("GC=F", "commodity"),
            trend_context=_trend(),
            policy_context=_policy(),
            extra_context={"fear_greed_value": 62},
            cost_tracker=tracker,
        )
    assert out["ticker"] == "GC=F"
    assert out["asset_class"] == "commodity"


def test_analyze_asset_bills_cost_tracker():
    payload = (FIXTURE_DIR / "mock_commodities_crypto_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.commodities_crypto.call_claude", return_value=fake):
        analyze_asset(
            ticker_data=_td("GC=F", "commodity"),
            trend_context=_trend(), policy_context=_policy(),
            extra_context={"fear_greed_value": 62}, cost_tracker=tracker,
        )
    assert tracker.input_tokens == 4000
    assert tracker.total_eur > 0


def test_analyze_asset_raises_on_unparseable():
    fake = _fake_result("not json")
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.commodities_crypto.call_claude", return_value=fake):
        with pytest.raises(CommoditiesCryptoError):
            analyze_asset(
                ticker_data=_td("GC=F", "commodity"),
                trend_context=_trend(), policy_context=_policy(),
                extra_context={}, cost_tracker=tracker,
            )


def test_analyze_loop_skips_individual_failures():
    payload = (FIXTURE_DIR / "mock_commodities_crypto_response.json").read_text()
    tracker = CostTracker(hard_cap_eur=10.0)
    side_effects = [_fake_result("bad"), _fake_result(payload)]
    with patch("src.commodities_crypto.call_claude", side_effect=side_effects):
        out = analyze_commodities_and_crypto(
            ticker_datas=[_td("BAD=F", "commodity"), _td("GC=F", "commodity")],
            trend_context=_trend(), policy_context=_policy(),
            extra_context={"fear_greed_value": 62}, cost_tracker=tracker,
        )
    assert len(out) == 1
    assert out[0]["ticker"] == "GC=F"


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


def test_user_message_includes_extra_context_keys():
    payload = (FIXTURE_DIR / "mock_commodities_crypto_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.commodities_crypto.call_claude", return_value=fake) as mock_call:
        analyze_asset(
            ticker_data=_td("BTC-USD", "crypto"),
            trend_context=_trend(), policy_context=_policy(),
            extra_context={"fear_greed_value": 62, "btc_dominance_pct": 54.2},
            cost_tracker=tracker,
        )
    user_msg = mock_call.call_args.kwargs["user"]
    assert "fear_greed_value" in user_msg
    assert "btc_dominance_pct" in user_msg
