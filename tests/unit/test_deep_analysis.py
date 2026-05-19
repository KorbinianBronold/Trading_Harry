import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.cost_tracker import CostTracker
from src.deep_analysis import (
    run_policy_monitor, analyze_asset, analyze_assets, DeepAnalysisError,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def _fake_result(text: str, model: str = "claude-sonnet-4-6",
                 web_search_calls: int = 3) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 5000
    r.output_tokens = 4000
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = model
    r.web_search_calls = web_search_calls
    return r


def _td(ticker: str = "AAPL", **overrides) -> dict:
    base = {
        "ticker": ticker, "price": 178.5,
        "rsi_14": 58.0, "macd_signal": "bullish_cross", "atr_pct": 1.8,
        "bb_position": 0.62, "above_sma20": 2.1, "above_sma50": 5.4,
        "above_sma200": 12.8, "volume_ratio": 1.15,
        "intraday_range_pct": 1.5,
        "pe_ratio": 28.4, "forward_pe": 26.2, "market_cap_b": 2800.0,
        "sector": "Technology", "earnings_in_days": 14, "earnings_beat_pct": 4.2,
        "data_quality": "high",
    }
    base.update(overrides)
    return base


def _trend_context() -> dict:
    return {"trends": [{"name": "ai-capex"}], "trend_summary": "risk-on"}


def _policy_context() -> dict:
    return json.loads((FIXTURE_DIR / "mock_policy_monitor_response.json").read_text())


def _quick_filter_result(ticker: str = "AAPL") -> dict:
    return {
        "ticker": ticker, "long_score": 7.5, "short_score": 2.0,
        "confidence": "high", "evidence": ["x"], "exclude": False,
    }


def test_run_policy_monitor_parses_and_returns(in_memory_db):
    payload = (FIXTURE_DIR / "mock_policy_monitor_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.deep_analysis.call_claude", return_value=fake):
        out = run_policy_monitor(date="2026-05-19", run_type="close",
                                 cost_tracker=tracker)

    assert out["policy_risk_level"] == "medium"
    assert len(out["events"]) == 2
    assert tracker.input_tokens == 5000


def test_run_policy_monitor_uses_web_search():
    payload = (FIXTURE_DIR / "mock_policy_monitor_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.deep_analysis.call_claude", return_value=fake) as mock_call:
        run_policy_monitor(date="2026-05-19", run_type="close",
                           cost_tracker=tracker)
    kwargs = mock_call.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert any(t.get("name") == "web_search" for t in kwargs["tools"])


def test_run_policy_monitor_tolerates_empty_events():
    fake = _fake_result(json.dumps({
        "policy_risk_level": "low", "events": [], "summary": "Calm news cycle.",
    }))
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude", return_value=fake):
        out = run_policy_monitor(date="2026-05-19", run_type="close",
                                 cost_tracker=tracker)
    assert out["events"] == []


def test_analyze_asset_returns_parsed_analysis():
    payload = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude", return_value=fake):
        out = analyze_asset(
            ticker_data=_td(),
            quick_filter_result=_quick_filter_result(),
            trend_context=_trend_context(),
            policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    assert out["ticker"] == "AAPL"
    assert out["direction"] == "long"
    assert out["rr_ratio"] == 2.2


def test_analyze_asset_bills_cost_tracker_via_add_from_result():
    payload = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude", return_value=fake):
        analyze_asset(
            ticker_data=_td(), quick_filter_result=_quick_filter_result(),
            trend_context=_trend_context(), policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    assert tracker.input_tokens == 5000
    assert tracker.output_tokens == 4000
    assert tracker.web_search_calls == 3
    assert tracker.total_eur > 0


def test_analyze_asset_raises_on_unparseable_response():
    fake = _fake_result("totally not json")
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude", return_value=fake):
        with pytest.raises(DeepAnalysisError):
            analyze_asset(
                ticker_data=_td(), quick_filter_result=_quick_filter_result(),
                trend_context=_trend_context(), policy_context=_policy_context(),
                cost_tracker=tracker,
            )


def test_analyze_asset_skips_when_quick_filter_excludes():
    """A ticker with quick_filter exclude=True is never sent to deep_analysis."""
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude") as mock_call:
        out = analyze_asset(
            ticker_data=_td(), policy_context=_policy_context(),
            quick_filter_result={**_quick_filter_result(), "exclude": True},
            trend_context=_trend_context(), cost_tracker=tracker,
        )
    assert out is None
    mock_call.assert_not_called()


def test_analyze_assets_loops_and_collects_non_none():
    payload = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    fake_ok = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    excl = {**_quick_filter_result("MSFT"), "exclude": True}

    with patch("src.deep_analysis.call_claude", return_value=fake_ok):
        out = analyze_assets(
            ticker_datas=[_td("AAPL"), _td("MSFT")],
            quick_filter_results=[_quick_filter_result("AAPL"), excl],
            trend_context=_trend_context(),
            policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    assert len(out) == 1
    assert out[0]["ticker"] == "AAPL"


def test_analyze_assets_skips_on_individual_failure_continues():
    """A single ticker raising must NOT kill the loop."""
    payload_ok = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    tracker = CostTracker(hard_cap_eur=10.0)

    side_effects = [_fake_result("garbage"), _fake_result(payload_ok)]
    with patch("src.deep_analysis.call_claude", side_effect=side_effects):
        out = analyze_assets(
            ticker_datas=[_td("BADCO"), _td("AAPL")],
            quick_filter_results=[
                _quick_filter_result("BADCO"),
                _quick_filter_result("AAPL"),
            ],
            trend_context=_trend_context(),
            policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    assert len(out) == 1
    assert out[0]["ticker"] == "AAPL"


def test_analyze_asset_passes_trend_and_policy_into_user_message():
    payload = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude", return_value=fake) as mock_call:
        analyze_asset(
            ticker_data=_td(), quick_filter_result=_quick_filter_result(),
            trend_context=_trend_context(), policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    user_msg = mock_call.call_args.kwargs["user"]
    assert "ai-capex" in user_msg
    assert "tariff truce" in user_msg.lower() or "tariff-truce" in user_msg.lower()
    assert "AAPL" in user_msg
