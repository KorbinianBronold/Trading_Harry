"""Predict on Tag 0, 3-day OHLC fixture, evaluator closes correctly."""
import pandas as pd
from unittest.mock import MagicMock

from src import db
from src.evaluator import evaluate_open_predictions


def test_predict_then_evaluate_two_days_later_tp_hit(tmp_path):
    conn = db.connect(str(tmp_path / "e.db"))
    db.init_schema(conn)
    pid = db.save_prediction(conn, {
        "date": "2026-05-19", "run_type": "close",
        "asset_class": "stock", "ticker": "AAPL", "direction": "long",
        "entry_price": 100.0, "tp_price": 105.0, "tp_pct": 5.0,
        "sl_price": 95.0, "sl_pct": 5.0, "rr_ratio": 1.0,
        "total_score": 7.5, "probability_pct": 65, "confidence": "high",
        "score_market_env": 7.0, "score_company": 7.0, "score_valuation": 6.0,
        "score_momentum": 8.0, "score_risk": 6.0, "score_sector": 7.0,
        "score_catalyst": 7.0, "score_policy": 6.0,
        "atr_pct": 1.8, "rsi_at_entry": 58.0, "volume_ratio": 1.0,
        "market_regime": "risk_on", "vix_at_prediction": 14.0,
        "sector": "Technology", "trend_boost": None,
        "earnings_warning": False, "summary": "ok",
        "learnable": True, "hold_days_recommended": 2,
        "intraday_range_pct": 1.5,
    })
    idx = pd.to_datetime(["2026-05-19", "2026-05-20", "2026-05-21"])
    df = pd.DataFrame({
        "Open":  [100.0, 100.0, 102.0],
        "High":  [101.0, 105.5, 104.0],
        "Low":   [99.0,   99.5, 101.0],
        "Close": [100.0, 104.0, 103.0],
    }, index=idx)
    provider = MagicMock()
    provider.get_ohlc_after.return_value = df

    evaluate_open_predictions(conn=conn, today="2026-05-21", price_provider=provider)

    row = conn.execute(
        "SELECT status, closed_price FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_tp"
    assert row["closed_price"] == 105.0
    out = conn.execute(
        "SELECT exit_reason, days_to_close FROM outcomes WHERE prediction_id=?",
        (pid,),
    ).fetchone()
    assert out["exit_reason"] == "tp_hit"
    assert out["days_to_close"] == 2  # entry-day bar included; bar 2 = 2026-05-20 hits TP
