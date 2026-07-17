from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd
import pytest

from src import db
from src.evaluator import evaluate_open_predictions, _walk_forward_hit

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_ohlc_eval.csv"
ALL_OHLC = pd.read_csv(FIXTURE)


def _ohlc(ticker: str) -> pd.DataFrame:
    df = ALL_OHLC[ALL_OHLC["ticker"] == ticker].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").drop(columns=["ticker"])
    df.columns = [c.capitalize() for c in df.columns]
    return df


def _make_pred(conn, ticker: str, direction: str = "long",
               entry: float = 100.0, tp: float = 105.0, sl: float = 95.0,
               date: str = "2026-05-19") -> int:
    return db.save_prediction(conn, {
        "date": date, "run_type": "close", "asset_class": "stock",
        "ticker": ticker, "direction": direction,
        "entry_price": entry, "tp_price": tp, "tp_pct": 5.0,
        "sl_price": sl, "sl_pct": 5.0, "rr_ratio": 1.0,
        "total_score": 7.0, "probability_pct": 60, "confidence": "medium",
        "score_market_env": 7.0, "score_company": 7.0, "score_valuation": 6.0,
        "score_momentum": 7.0, "score_risk": 6.0, "score_sector": 7.0,
        "score_catalyst": 7.0, "score_policy": 6.0,
        "atr_pct": 2.0, "rsi_at_entry": 55.0, "volume_ratio": 1.0,
        "market_regime": "risk_on", "vix_at_prediction": 14.0,
        "sector": "Technology", "trend_boost": None,
        "earnings_warning": False, "summary": "test",
        "learnable": True, "hold_days_recommended": 2,
        "intraday_range_pct": 1.5,
    })


def _provider_for(df_map: dict[str, pd.DataFrame]) -> MagicMock:
    provider = MagicMock()
    def _get(ticker, start_date=None, end_date=None):
        df = df_map.get(ticker)
        if df is None:
            return None
        if start_date is not None:
            df = df[df.index >= pd.Timestamp(start_date)]
        if end_date is not None:
            df = df[df.index <= pd.Timestamp(end_date)]
        return df if not df.empty else None
    provider.get_ohlc_after = _get
    return provider


def test_long_tp_hit(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "LONG_TP", direction="long",
                     entry=100.0, tp=105.0, sl=95.0)
    provider = _provider_for({"LONG_TP": _ohlc("LONG_TP")})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=provider,
    )
    row = in_memory_db.execute(
        "SELECT status, closed_price FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_tp"
    assert row["closed_price"] == 105.0
    out = in_memory_db.execute(
        "SELECT exit_reason, tp_hit, days_to_close FROM outcomes "
        "WHERE prediction_id=?", (pid,),
    ).fetchone()
    assert out["exit_reason"] == "tp_hit"
    assert out["tp_hit"] == 1
    assert out["days_to_close"] == 2


def test_long_sl_hit(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "LONG_SL", direction="long",
                     entry=100.0, tp=105.0, sl=95.0)
    provider = _provider_for({"LONG_SL": _ohlc("LONG_SL")})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=provider,
    )
    row = in_memory_db.execute(
        "SELECT status, closed_price FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_sl"
    out = in_memory_db.execute(
        "SELECT exit_reason FROM outcomes WHERE prediction_id=?", (pid,),
    ).fetchone()
    assert out["exit_reason"] == "sl_hit"


def test_short_tp_hit(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "SHORT_TP", direction="short",
                     entry=100.0, tp=95.0, sl=105.0)
    provider = _provider_for({"SHORT_TP": _ohlc("SHORT_TP")})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=provider,
    )
    row = in_memory_db.execute(
        "SELECT status FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_tp"


def test_short_sl_hit(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "SHORT_SL", direction="short",
                     entry=100.0, tp=95.0, sl=105.0)
    provider = _provider_for({"SHORT_SL": _ohlc("SHORT_SL")})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=provider,
    )
    row = in_memory_db.execute(
        "SELECT status FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_sl"


def test_timeout_after_three_days(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "TIMEOUT", direction="long",
                     entry=100.0, tp=110.0, sl=90.0)
    provider = _provider_for({"TIMEOUT": _ohlc("TIMEOUT")})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-22", price_provider=provider,
    )
    row = in_memory_db.execute(
        "SELECT status, closed_price FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_timeout"
    assert row["closed_price"] == 100.5  # day-3 close
    out = in_memory_db.execute(
        "SELECT exit_reason, days_to_close FROM outcomes WHERE prediction_id=?",
        (pid,),
    ).fetchone()
    assert out["exit_reason"] == "timeout"
    assert out["days_to_close"] == 3


def test_pessimistic_overlap_closes_at_sl(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "OVERLAP", direction="long",
                     entry=100.0, tp=105.0, sl=95.0)
    provider = _provider_for({"OVERLAP": _ohlc("OVERLAP")})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=provider,
    )
    row = in_memory_db.execute(
        "SELECT status, closed_price FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_sl"
    assert row["closed_price"] == 95.0
    out = in_memory_db.execute(
        "SELECT exit_reason FROM outcomes WHERE prediction_id=?", (pid,),
    ).fetchone()
    assert out["exit_reason"] == "pessimistic_overlap"


def test_data_missing_closes_with_data_missing_reason(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "GONE", direction="long",
                     entry=100.0, tp=105.0, sl=95.0)
    provider = _provider_for({})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=provider,
    )
    row = in_memory_db.execute(
        "SELECT status FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_data_missing"
    out = in_memory_db.execute(
        "SELECT exit_reason FROM outcomes WHERE prediction_id=?", (pid,),
    ).fetchone()
    assert out["exit_reason"] == "data_missing"


def test_evaluate_ignores_already_closed(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "LONG_TP", direction="long")
    db.close_prediction(in_memory_db, pid, status="closed_tp",
                        closed_date="2026-05-20", closed_price=105.0)
    provider = _provider_for({"LONG_TP": _ohlc("LONG_TP")})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-21", price_provider=provider,
    )
    out_count = in_memory_db.execute(
        "SELECT COUNT(*) AS n FROM outcomes WHERE prediction_id=?", (pid,),
    ).fetchone()["n"]
    assert out_count == 0


def test_walk_forward_helper_tp_first():
    """Helper covers the bar-by-bar comparison logic in isolation."""
    df = _ohlc("LONG_TP")
    reason, exit_price, day = _walk_forward_hit(
        df, direction="long", tp=105.0, sl=95.0,
    )
    assert reason == "tp_hit"
    assert exit_price == 105.0
    assert day == 2


def test_walk_forward_helper_honors_five_day_cap():
    """MAX_HOLD_DAYS now tracks config.MAX_HOLD_DAYS (5) instead of a hardcoded 3 —
    a hit on day 5 must still be detected, not cut off early."""
    from src.evaluator import MAX_HOLD_DAYS
    assert MAX_HOLD_DAYS == 5

    idx = pd.date_range("2026-06-01", periods=5, freq="B")
    df = pd.DataFrame({
        "High":  [101, 101, 101, 101, 111],
        "Low":   [99, 99, 99, 99, 100],
        "Close": [100, 100, 100, 100, 110],
    }, index=idx)

    reason, exit_price, day = _walk_forward_hit(df, direction="long", tp=110.0, sl=90.0)
    assert reason == "tp_hit"
    assert exit_price == 110.0
    assert day == 5
