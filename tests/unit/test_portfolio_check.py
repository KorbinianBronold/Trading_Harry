import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src import db
from src.cost_tracker import CostTracker
from src.portfolio_check import (
    check_open_positions, check_one_position, PortfolioCheckError,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def _fake_result(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 3000
    r.output_tokens = 2000
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = "claude-sonnet-4-6"
    r.web_search_calls = 2
    return r


def _make_open_prediction(conn, date: str = "2026-05-18", ticker: str = "AAPL") -> int:
    return db.save_prediction(conn, {
        "date": date, "run_type": "close", "asset_class": "stock",
        "ticker": ticker, "direction": "long",
        "entry_price": 178.0, "tp_price": 184.0, "tp_pct": 3.4,
        "sl_price": 176.0, "sl_pct": 1.1, "rr_ratio": 3.0,
        "total_score": 7.8, "probability_pct": 68, "confidence": "high",
        "score_market_env": 7.0, "score_company": 8.0, "score_valuation": 6.0,
        "score_momentum": 8.0, "score_risk": 6.0, "score_sector": 7.0,
        "score_catalyst": 7.0, "score_policy": 6.0,
        "atr_pct": 1.8, "rsi_at_entry": 58.0, "volume_ratio": 1.15,
        "market_regime": "risk_on", "vix_at_prediction": 14.0,
        "sector": "Technology", "trend_boost": "ai-capex",
        "earnings_warning": False, "summary": "AAPL long thesis",
        "learnable": True, "hold_days_recommended": 2,
        "intraday_range_pct": 1.4,
    })


def test_check_one_position_returns_parsed(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_open_prediction(in_memory_db)
    pred = in_memory_db.execute(
        "SELECT * FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    payload = (FIXTURE_DIR / "mock_portfolio_check_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    snapshot = {"ticker": "AAPL", "price": 181.2, "rsi_14": 60.0,
                "macd_signal": "bullish_cross", "atr_pct": 1.8,
                "intraday_range_pct": 1.5}
    trend = {"trend_summary": "risk-on"}
    policy = {"policy_risk_level": "low", "events": []}

    with patch("src.portfolio_check.call_claude", return_value=fake):
        out = check_one_position(
            prediction=pred, current_snapshot=snapshot,
            trend_context=trend, policy_context=policy,
            cost_tracker=tracker,
        )
    assert out["action"] == "ANPASSEN"
    assert out["new_sl_price"] == 178.5


def test_check_open_positions_writes_recommendation_rows(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_open_prediction(in_memory_db)
    payload = (FIXTURE_DIR / "mock_portfolio_check_response.json").read_text()
    # Adjust the fixture prediction_id to match the just-inserted one
    payload_obj = json.loads(payload)
    payload_obj["prediction_id"] = pid
    fake = _fake_result(json.dumps(payload_obj))
    tracker = CostTracker(hard_cap_eur=10.0)
    snapshots_by_ticker = {"AAPL": {"ticker": "AAPL", "price": 181.2,
                                    "rsi_14": 60.0, "macd_signal": "bullish_cross",
                                    "atr_pct": 1.8, "intraday_range_pct": 1.5}}

    with patch("src.portfolio_check.call_claude", return_value=fake):
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            snapshots_by_ticker=snapshots_by_ticker,
            trend_context={"trend_summary": "risk-on"},
            policy_context={"policy_risk_level": "low", "events": []},
            cost_tracker=tracker,
        )
    rows = in_memory_db.execute(
        "SELECT action, new_sl_price FROM position_recommendations "
        "WHERE prediction_id=?", (pid,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["action"] == "ANPASSEN"
    assert len(out) == 1


def test_check_open_positions_skips_position_with_missing_snapshot(in_memory_db):
    """If the data_collector didn't produce a snapshot for the ticker
    (e.g., yfinance failure), we skip the position rather than crash."""
    db.init_schema(in_memory_db)
    _make_open_prediction(in_memory_db, ticker="AAPL")
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.portfolio_check.call_claude") as mock_call:
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            snapshots_by_ticker={},
            trend_context={"trend_summary": ""},
            policy_context={"policy_risk_level": "low", "events": []},
            cost_tracker=tracker,
        )
    assert out == []
    mock_call.assert_not_called()


def test_check_open_positions_skips_old_predictions(in_memory_db):
    """Predictions older than max_trading_days are not loaded."""
    db.init_schema(in_memory_db)
    _make_open_prediction(in_memory_db, date="2026-05-10")
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.portfolio_check.call_claude") as mock_call:
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            snapshots_by_ticker={"AAPL": {"ticker": "AAPL", "price": 180.0,
                                          "intraday_range_pct": 1.5}},
            trend_context={}, policy_context={},
            cost_tracker=tracker,
        )
    assert out == []
    mock_call.assert_not_called()


def test_check_one_position_raises_on_invalid_json(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_open_prediction(in_memory_db)
    pred = in_memory_db.execute(
        "SELECT * FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    fake = _fake_result("not json")
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.portfolio_check.call_claude", return_value=fake):
        with pytest.raises(PortfolioCheckError):
            check_one_position(
                prediction=pred,
                current_snapshot={"ticker": "AAPL", "price": 181.0,
                                  "intraday_range_pct": 1.5},
                trend_context={}, policy_context={},
                cost_tracker=tracker,
            )


def test_check_open_positions_continues_after_single_failure(in_memory_db):
    db.init_schema(in_memory_db)
    p1 = _make_open_prediction(in_memory_db, ticker="AAPL")
    p2 = _make_open_prediction(in_memory_db, ticker="MSFT")
    good_payload = json.loads((FIXTURE_DIR / "mock_portfolio_check_response.json").read_text())
    good_payload["ticker"] = "MSFT"
    good_payload["prediction_id"] = p2
    side_effects = [_fake_result("bad"), _fake_result(json.dumps(good_payload))]
    tracker = CostTracker(hard_cap_eur=10.0)
    snapshots = {
        "AAPL": {"ticker": "AAPL", "price": 181.0, "intraday_range_pct": 1.5},
        "MSFT": {"ticker": "MSFT", "price": 410.0, "intraday_range_pct": 1.4},
    }
    with patch("src.portfolio_check.call_claude", side_effect=side_effects):
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            snapshots_by_ticker=snapshots,
            trend_context={}, policy_context={},
            cost_tracker=tracker,
        )
    assert len(out) == 1
    assert out[0]["ticker"] == "MSFT"


def test_check_open_positions_returns_empty_when_no_open(in_memory_db):
    db.init_schema(in_memory_db)
    tracker = CostTracker(hard_cap_eur=10.0)
    out = check_open_positions(
        conn=in_memory_db, today="2026-05-20", run_type="pre_market",
        snapshots_by_ticker={}, trend_context={}, policy_context={},
        cost_tracker=tracker,
    )
    assert out == []
