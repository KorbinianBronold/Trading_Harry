import sqlite3
import pytest
from src.db import init_schema, get_tables


def test_init_schema_creates_all_tables(in_memory_db):
    init_schema(in_memory_db)
    tables = get_tables(in_memory_db)
    expected = {
        "price_history",
        "technical_indicators",
        "fundamentals",
        "news_summaries",
        "trend_analyses",
        "market_context",
        "predictions",
        "outcomes",
        "skipped_tickers",
        "prompt_versions",
        "cost_tracking",
    }
    assert expected.issubset(set(tables))


def test_init_schema_is_idempotent(in_memory_db):
    init_schema(in_memory_db)
    init_schema(in_memory_db)
    tables = get_tables(in_memory_db)
    assert "predictions" in tables


from src.db import (
    init_schema, save_prediction, load_open_predictions,
    close_prediction, save_outcome, save_cost_tracking,
)


def _sample_pred() -> dict:
    return {
        "date": "2026-05-19", "run_type": "pre_market", "asset_class": "stock",
        "ticker": "AAPL", "direction": "long",
        "entry_price": 178.5, "tp_price": 182.0, "tp_pct": 2.0,
        "sl_price": 176.7, "sl_pct": 1.0, "rr_ratio": 2.0,
        "total_score": 7.8, "probability_pct": 65, "confidence": "high",
        "score_market_env": 7.0, "score_company": 8.5, "score_valuation": 6.5,
        "score_momentum": 8.0, "score_risk": 6.0, "score_sector": 7.5,
        "score_catalyst": 7.0, "score_policy": 5.5,
        "atr_pct": 1.8, "rsi_at_entry": 58.4, "volume_ratio": 1.15,
        "market_regime": "risk_on", "vix_at_prediction": 14.2, "sector": "Technology",
        "trend_boost": "AI", "earnings_warning": False,
        "summary": "Test prediction", "learnable": True,
    }


def test_save_and_load_prediction(in_memory_db):
    init_schema(in_memory_db)
    pid = save_prediction(in_memory_db, _sample_pred())
    assert pid == 1
    opens = load_open_predictions(in_memory_db)
    assert len(opens) == 1
    assert opens[0]["ticker"] == "AAPL"
    assert opens[0]["status"] == "open"


def test_close_prediction_changes_status(in_memory_db):
    init_schema(in_memory_db)
    pid = save_prediction(in_memory_db, _sample_pred())
    close_prediction(in_memory_db, pid, "closed_tp", "2026-05-20", 182.0)
    opens = load_open_predictions(in_memory_db)
    assert len(opens) == 0
    row = in_memory_db.execute(
        "SELECT * FROM predictions WHERE id=?", (pid,)
    ).fetchone()
    assert row["status"] == "closed_tp"
    assert row["closed_price"] == 182.0


def test_save_outcome_roundtrip(in_memory_db):
    init_schema(in_memory_db)
    pid = save_prediction(in_memory_db, _sample_pred())
    save_outcome(in_memory_db, {
        "prediction_id": pid, "direction": "long",
        "evaluated_date": "2026-05-20",
        "price_after_eod": 182.0, "price_change_eod_pct": 1.96,
        "correct_direction_eod": True,
        "tp_hit": True, "sl_hit": False,
        "days_to_close": 1, "exit_reason": "tp_hit",
        "profit_loss_eur": 50.0,
    })
    row = in_memory_db.execute(
        "SELECT * FROM outcomes WHERE prediction_id=?", (pid,)
    ).fetchone()
    assert row["exit_reason"] == "tp_hit"
    assert row["days_to_close"] == 1


def test_save_cost_tracking_roundtrip(in_memory_db):
    init_schema(in_memory_db)
    save_cost_tracking(in_memory_db, {
        "date": "2026-05-19", "run_type": "pre_market",
        "total_eur": 2.84, "claude_eur": 2.50, "web_search_eur": 0.34,
        "input_tokens": 142000, "output_tokens": 63000,
        "cache_read_tokens": 95000, "cache_hit_rate": 0.87,
        "web_search_calls": 23, "aborted_at_phase": None,
    })
    row = in_memory_db.execute("SELECT * FROM cost_tracking").fetchone()
    assert row["total_eur"] == 2.84
    assert row["cache_hit_rate"] == 0.87


from src.db import (
    upsert_technical_indicators, save_trend_analysis, log_skipped_ticker,
)


def test_technical_indicators_schema_has_intraday_range_pct(in_memory_db):
    init_schema(in_memory_db)
    cols = [r["name"] for r in in_memory_db.execute(
        "PRAGMA table_info(technical_indicators)"
    ).fetchall()]
    assert "intraday_range_pct" in cols


def test_upsert_technical_indicators_inserts_and_replaces(in_memory_db):
    init_schema(in_memory_db)
    upsert_technical_indicators(in_memory_db, {
        "ticker": "AAPL", "date": "2026-05-19",
        "rsi_14": 58.4, "macd_signal": "bullish_cross", "atr_pct": 1.8,
        "bb_position": 0.62, "above_sma20": 2.1, "above_sma50": 5.4,
        "above_sma200": 12.8, "volume_ratio": 1.15, "intraday_range_pct": 1.4,
    })
    row = in_memory_db.execute(
        "SELECT * FROM technical_indicators WHERE ticker=? AND date=?",
        ("AAPL", "2026-05-19"),
    ).fetchone()
    assert row["rsi_14"] == 58.4
    assert row["intraday_range_pct"] == 1.4

    # Re-upsert overwrites
    upsert_technical_indicators(in_memory_db, {
        "ticker": "AAPL", "date": "2026-05-19",
        "rsi_14": 60.0, "macd_signal": "neutral", "atr_pct": 1.9,
        "bb_position": 0.7, "above_sma20": 2.5, "above_sma50": 5.6,
        "above_sma200": 13.0, "volume_ratio": 1.2, "intraday_range_pct": 1.5,
    })
    row = in_memory_db.execute(
        "SELECT rsi_14, intraday_range_pct FROM technical_indicators "
        "WHERE ticker=? AND date=?", ("AAPL", "2026-05-19"),
    ).fetchone()
    assert row["rsi_14"] == 60.0
    assert row["intraday_range_pct"] == 1.5


def test_save_trend_analysis_roundtrip(in_memory_db):
    init_schema(in_memory_db)
    save_trend_analysis(in_memory_db, {
        "date": "2026-05-19", "run_type": "pre_market",
        "trend_name": "ai-capex-acceleration",
        "strength": 8, "duration_estimate": "1m+",
        "summary": "Hyperscalers raised guidance two quarters in a row.",
        "beneficiary_tickers": ["NVDA", "AVGO"],
        "negative_tickers": ["INTC"],
        "next_catalyst": "GTC keynote 2026-06-12",
    })
    row = in_memory_db.execute(
        "SELECT * FROM trend_analyses WHERE trend_name=?",
        ("ai-capex-acceleration",),
    ).fetchone()
    assert row["strength"] == 8
    assert row["beneficiary_tickers"] == "NVDA,AVGO"
    assert row["negative_tickers"] == "INTC"


def test_save_trend_analysis_unique_per_date_and_name(in_memory_db):
    init_schema(in_memory_db)
    row = {
        "date": "2026-05-19", "run_type": "pre_market",
        "trend_name": "ai-capex-acceleration",
        "strength": 8, "duration_estimate": "1m+",
        "summary": "x", "beneficiary_tickers": ["NVDA"],
        "negative_tickers": [], "next_catalyst": "x",
    }
    save_trend_analysis(in_memory_db, row)
    save_trend_analysis(in_memory_db, {**row, "strength": 9})  # replace
    rows = in_memory_db.execute(
        "SELECT strength FROM trend_analyses WHERE trend_name=?",
        ("ai-capex-acceleration",),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["strength"] == 9


def test_log_skipped_ticker_inserts_row(in_memory_db):
    init_schema(in_memory_db)
    log_skipped_ticker(
        in_memory_db,
        ticker="XYZ", date="2026-05-19", run_type="pre_market",
        reason="yfinance returned no data", learnable=False,
    )
    row = in_memory_db.execute(
        "SELECT * FROM skipped_tickers WHERE ticker=?", ("XYZ",),
    ).fetchone()
    assert row["reason"] == "yfinance returned no data"
    assert row["learnable"] == 0
