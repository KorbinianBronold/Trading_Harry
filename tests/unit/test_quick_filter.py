import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.cost_tracker import CostTracker
from src.quick_filter import quick_filter_batch, QuickFilterError


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mock_quick_filter_response.json"


def _fake_haiku_result(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 6000
    r.output_tokens = 2000
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = "claude-haiku-4-5"
    r.web_search_calls = 0
    return r


def _td(ticker: str, **overrides) -> dict:
    base = {
        "ticker": ticker, "price": 100.0,
        "rsi_14": 55.0, "macd_signal": "neutral", "atr_pct": 1.5,
        "above_sma200": 8.0, "volume_ratio": 1.1,
        "pe_ratio": 25.0, "market_cap_b": 200.0, "sector": "Technology",
        "earnings_in_days": 14, "earnings_beat_pct": 3.0,
        "data_quality": "high",
        "intraday_range_pct": 1.5,
    }
    base.update(overrides)
    return base


def _trend_context() -> dict:
    return {
        "trends": [{"name": "ai-capex-acceleration", "strength": 8,
                    "beneficiary_tickers": ["AAPL"], "negative_tickers": []}],
        "sector_rotation": {"into": ["XLK"], "out_of": ["XLU"]},
        "trend_summary": "Risk-on, AI leading."
    }


def test_quick_filter_returns_one_entry_per_ticker():
    payload = FIXTURE_PATH.read_text()
    fake = _fake_haiku_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("AAPL"), _td("MSFT"), _td("BADCO", data_quality="low")]

    with patch("src.quick_filter.call_claude", return_value=fake):
        out = quick_filter_batch(
            batch=batch,
            trend_context=_trend_context(),
            cost_tracker=tracker,
        )

    assert len(out) == 3
    assert out[0]["ticker"] == "AAPL"
    assert out[0]["long_score"] == 7.5
    assert out[2]["exclude"] is True


def test_quick_filter_uses_haiku_and_no_web_search():
    fake = _fake_haiku_result(FIXTURE_PATH.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.quick_filter.call_claude", return_value=fake) as mock_call:
        quick_filter_batch(
            batch=[_td("AAPL"), _td("MSFT"), _td("BADCO")],
            trend_context=_trend_context(),
            cost_tracker=tracker,
        )

    kwargs = mock_call.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5"
    assert kwargs.get("tools") in (None, [])


def test_quick_filter_bills_cost_tracker():
    fake = _fake_haiku_result(FIXTURE_PATH.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.quick_filter.call_claude", return_value=fake):
        quick_filter_batch(
            batch=[_td("AAPL"), _td("MSFT"), _td("BADCO")],
            trend_context=_trend_context(),
            cost_tracker=tracker,
        )

    assert tracker.input_tokens == 6000
    assert tracker.output_tokens == 2000
    assert tracker.total_eur > 0


def test_quick_filter_raises_on_invalid_json():
    fake = _fake_haiku_result("not json")
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.quick_filter.call_claude", return_value=fake):
        with pytest.raises(QuickFilterError):
            quick_filter_batch(
                batch=[_td("AAPL")],
                trend_context=_trend_context(),
                cost_tracker=tracker,
            )


def test_quick_filter_raises_on_missing_ticker_in_response():
    """If a ticker from the batch is missing from results, that's a prompt failure."""
    payload = json.dumps({"results": [
        {"ticker": "AAPL", "long_score": 7.0, "short_score": 2.0,
         "confidence": "medium", "evidence": ["x"], "exclude": False},
    ]})
    fake = _fake_haiku_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.quick_filter.call_claude", return_value=fake):
        with pytest.raises(QuickFilterError, match="missing"):
            quick_filter_batch(
                batch=[_td("AAPL"), _td("MSFT")],
                trend_context=_trend_context(),
                cost_tracker=tracker,
            )


def test_quick_filter_empty_batch_returns_empty_list():
    tracker = CostTracker(hard_cap_eur=10.0)
    out = quick_filter_batch(
        batch=[],
        trend_context=_trend_context(),
        cost_tracker=tracker,
    )
    assert out == []
    assert tracker.input_tokens == 0


def test_quick_filter_user_message_includes_tickers_and_trends():
    fake = _fake_haiku_result(FIXTURE_PATH.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.quick_filter.call_claude", return_value=fake) as mock_call:
        quick_filter_batch(
            batch=[_td("AAPL"), _td("MSFT"), _td("BADCO")],
            trend_context=_trend_context(),
            cost_tracker=tracker,
        )

    user_msg = mock_call.call_args.kwargs["user"]
    assert "AAPL" in user_msg
    assert "MSFT" in user_msg
    assert "ai-capex-acceleration" in user_msg
