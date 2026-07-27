import sqlite3
import pytest
from src.db import init_schema, get_tables, get_cached_fundamentals, save_fundamentals_cache


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


from src import db


def test_predictions_has_hold_days_and_intraday_range_columns(in_memory_db):
    db.init_schema(in_memory_db)
    cols = {r["name"] for r in in_memory_db.execute(
        "PRAGMA table_info(predictions)"
    ).fetchall()}
    assert "hold_days_recommended" in cols
    assert "intraday_range_pct" in cols


def test_outcomes_has_days_to_close_and_exit_reason_columns(in_memory_db):
    db.init_schema(in_memory_db)
    cols = {r["name"] for r in in_memory_db.execute(
        "PRAGMA table_info(outcomes)"
    ).fetchall()}
    assert "days_to_close" in cols
    assert "exit_reason" in cols


def test_position_recommendations_table_exists(in_memory_db):
    db.init_schema(in_memory_db)
    assert "position_recommendations" in db.get_tables(in_memory_db)


def test_save_prediction_persists_hold_days_and_intraday(in_memory_db):
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-05-19", "run_type": "close",
        "asset_class": "stock", "ticker": "AAPL", "direction": "long",
        "entry_price": 178.0, "tp_price": 184.0, "tp_pct": 3.4,
        "sl_price": 176.0, "sl_pct": 1.1, "rr_ratio": 3.0,
        "total_score": 7.8, "probability_pct": 68, "confidence": "high",
        "score_market_env": 7.0, "score_company": 8.0, "score_valuation": 6.0,
        "score_momentum": 8.0, "score_risk": 6.0, "score_sector": 7.0,
        "score_catalyst": 7.0, "score_policy": 6.0,
        "atr_pct": 1.8, "rsi_at_entry": 58.0, "volume_ratio": 1.15,
        "market_regime": "risk_on", "vix_at_prediction": 14.0,
        "sector": "Technology", "trend_boost": "ai-capex",
        "earnings_warning": False, "summary": "ok",
        "learnable": True,
        "hold_days_recommended": 2,
        "intraday_range_pct": 1.4,
    })
    row = in_memory_db.execute(
        "SELECT hold_days_recommended, intraday_range_pct FROM predictions WHERE id=?",
        (pid,),
    ).fetchone()
    assert row["hold_days_recommended"] == 2
    assert row["intraday_range_pct"] == 1.4


def test_save_position_recommendation(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _insert_test_prediction(in_memory_db)
    db.save_position_recommendation(in_memory_db, {
        "date": "2026-05-20", "run_type": "pre_market",
        "prediction_id": pid, "action": "HALTEN",
        "reason": "These intakt, kein neuer Katalysator.",
        "new_sl_price": None, "new_tp_price": None,
        "market_context_changed": False,
    })
    row = in_memory_db.execute(
        "SELECT action, reason FROM position_recommendations WHERE prediction_id=?",
        (pid,),
    ).fetchone()
    assert row["action"] == "HALTEN"


def test_load_open_predictions_within_max_age_days(in_memory_db):
    db.init_schema(in_memory_db)
    p_old = _insert_test_prediction(in_memory_db, date="2026-05-10")
    p_new = _insert_test_prediction(in_memory_db, date="2026-05-19")
    rows = db.load_open_predictions_within_max_age_days(
        in_memory_db, today="2026-05-20", max_trading_days=3,
    )
    ids = {r["id"] for r in rows}
    assert p_new in ids
    assert p_old not in ids


def test_save_outcome_with_new_columns(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _insert_test_prediction(in_memory_db)
    oid = db.save_outcome(in_memory_db, {
        "prediction_id": pid, "direction": "long",
        "evaluated_date": "2026-05-22",
        "price_after_eod": 184.0, "price_change_eod_pct": 3.4,
        "correct_direction_eod": True,
        "tp_hit": True, "sl_hit": False,
        "days_to_close": 2, "exit_reason": "tp_hit",
        "profit_loss_eur": 25.0,
    })
    row = in_memory_db.execute(
        "SELECT days_to_close, exit_reason FROM outcomes WHERE id=?",
        (oid,),
    ).fetchone()
    assert row["days_to_close"] == 2
    assert row["exit_reason"] == "tp_hit"


def _insert_test_prediction(conn, date: str = "2026-05-19") -> int:
    """Helper used by multiple new tests."""
    return db.save_prediction(conn, {
        "date": date, "run_type": "close",
        "asset_class": "stock", "ticker": "AAPL", "direction": "long",
        "entry_price": 178.0, "tp_price": 184.0, "tp_pct": 3.4,
        "sl_price": 176.0, "sl_pct": 1.1, "rr_ratio": 3.0,
        "total_score": 7.8, "probability_pct": 68, "confidence": "high",
        "score_market_env": 7.0, "score_company": 8.0, "score_valuation": 6.0,
        "score_momentum": 8.0, "score_risk": 6.0, "score_sector": 7.0,
        "score_catalyst": 7.0, "score_policy": 6.0,
        "atr_pct": 1.8, "rsi_at_entry": 58.0, "volume_ratio": 1.15,
        "market_regime": "risk_on", "vix_at_prediction": 14.0,
        "sector": "Technology", "trend_boost": "ai-capex",
        "earnings_warning": False, "summary": "ok",
        "learnable": True,
        "hold_days_recommended": 2,
        "intraday_range_pct": 1.4,
    })


def test_fundamentals_cache_miss_on_fresh_db(in_memory_db):
    init_schema(in_memory_db)
    assert get_cached_fundamentals(in_memory_db, "AAPL") is None


def test_fundamentals_cache_hit_within_7_days(in_memory_db):
    init_schema(in_memory_db)
    data = {
        "pe_ratio": 25.0, "forward_pe": 22.0, "market_cap_b": 3000.0,
        "debt_equity": 0.5, "sector": "Technology",
        "analyst_upside": 10.0, "consensus": "buy",
    }
    save_fundamentals_cache(in_memory_db, "AAPL", data, fetched_date="2026-05-21")
    result = get_cached_fundamentals(in_memory_db, "AAPL", today="2026-05-21")
    assert result is not None
    assert result["pe_ratio"] == 25.0
    assert result["sector"] == "Technology"


def test_fundamentals_cache_stale_after_7_days(in_memory_db):
    init_schema(in_memory_db)
    save_fundamentals_cache(in_memory_db, "AAPL", {"pe_ratio": 20.0}, fetched_date="2026-05-01")
    result = get_cached_fundamentals(in_memory_db, "AAPL", today="2026-05-21")
    assert result is None


def test_fundamentals_cache_upsert_overwrites_stale(in_memory_db):
    init_schema(in_memory_db)
    save_fundamentals_cache(in_memory_db, "AAPL", {"pe_ratio": 20.0}, fetched_date="2026-05-01")
    save_fundamentals_cache(in_memory_db, "AAPL", {"pe_ratio": 25.0}, fetched_date="2026-05-21")
    result = get_cached_fundamentals(in_memory_db, "AAPL", today="2026-05-21")
    assert result is not None
    assert result["pe_ratio"] == 25.0


# ---------- Sub-Sektor-Tabellen (Sprint 3B / Plan 1, Task 3) ----------

from src.db import (
    resolve_sector_id, upsert_ticker_sector, get_ticker_sector,
)


def test_init_schema_creates_sector_tables(in_memory_db):
    init_schema(in_memory_db)
    tables = set(get_tables(in_memory_db))
    assert {"sectors", "ticker_sectors"}.issubset(tables)


def test_sectors_table_is_seeded_with_all_sub_sectors(in_memory_db):
    import config
    init_schema(in_memory_db)
    rows = in_memory_db.execute("SELECT name, etf FROM sectors ORDER BY name").fetchall()
    assert len(rows) == 21
    assert {r["name"]: r["etf"] for r in rows} == config.SUB_SECTOR_ETFS


def test_sector_seeding_is_idempotent(in_memory_db):
    init_schema(in_memory_db)
    init_schema(in_memory_db)
    n = in_memory_db.execute("SELECT COUNT(*) AS n FROM sectors").fetchone()["n"]
    assert n == 21


def test_resolve_sector_id_maps_exact_sub_sector_name(in_memory_db):
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Semiconductors")
    assert sid is not None
    row = in_memory_db.execute("SELECT name FROM sectors WHERE id=?", (sid,)).fetchone()
    assert row["name"] == "Semiconductors"


def test_resolve_sector_id_maps_finnhub_alias(in_memory_db):
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Consumer Cyclical")
    row = in_memory_db.execute("SELECT name FROM sectors WHERE id=?", (sid,)).fetchone()
    assert row["name"] == "Consumer Discretionary Rest"


def test_resolve_sector_id_splits_broad_finnhub_values_into_sub_sectors(in_memory_db):
    """Der Kern von D7: 'Software' und 'Semiconductors' duerfen NICHT beide im
    breiten Technologie-Eimer landen."""
    init_schema(in_memory_db)
    soft = resolve_sector_id(in_memory_db, "Software")
    semi = resolve_sector_id(in_memory_db, "Semiconductors")
    assert soft != semi
    etfs = {
        r["etf"] for r in in_memory_db.execute(
            "SELECT etf FROM sectors WHERE id IN (?, ?)", (soft, semi)).fetchall()
    }
    assert etfs == {"VGT", "SOXX"}


def test_resolve_sector_id_returns_none_for_deliberately_unmapped_values(in_memory_db):
    """D5: Werte ohne passenden ETF bleiben ungemappt statt falsch geroutet."""
    init_schema(in_memory_db)
    for raw in ("Media", "Chemicals"):
        assert resolve_sector_id(in_memory_db, raw) is None


def test_resolve_sector_id_is_case_and_whitespace_insensitive(in_memory_db):
    init_schema(in_memory_db)
    assert resolve_sector_id(in_memory_db, "  semiconductors ") == \
           resolve_sector_id(in_memory_db, "Semiconductors")


def test_resolve_sector_id_returns_none_for_unknown_and_logs(in_memory_db, caplog):
    init_schema(in_memory_db)
    with caplog.at_level("WARNING"):
        assert resolve_sector_id(in_memory_db, "Underwater Basket Weaving") is None
    assert "Underwater Basket Weaving" in caplog.text


def test_resolve_sector_id_returns_none_for_none_without_logging(in_memory_db, caplog):
    init_schema(in_memory_db)
    with caplog.at_level("WARNING"):
        assert resolve_sector_id(in_memory_db, None) is None
    assert "unknown sector" not in caplog.text


def test_upsert_ticker_sector_inserts_then_updates(in_memory_db):
    init_schema(in_memory_db)
    hardware = resolve_sector_id(in_memory_db, "Technology Hardware")
    semi = resolve_sector_id(in_memory_db, "Semiconductors")
    upsert_ticker_sector(in_memory_db, "AAPL", hardware)
    upsert_ticker_sector(in_memory_db, "AAPL", semi)
    rows = in_memory_db.execute("SELECT * FROM ticker_sectors WHERE ticker='AAPL'").fetchall()
    assert len(rows) == 1
    assert rows[0]["sector_id"] == semi


def test_get_ticker_sector_joins_name_and_etf(in_memory_db):
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Semiconductors")
    upsert_ticker_sector(in_memory_db, "NVDA", sid)
    row = get_ticker_sector(in_memory_db, "NVDA")
    assert row["name"] == "Semiconductors"
    assert row["etf"] == "SOXX"


def test_get_ticker_sector_returns_none_when_unmapped(in_memory_db):
    init_schema(in_memory_db)
    assert get_ticker_sector(in_memory_db, "NOPE") is None


# ---------- ticker_status (Sprint 3B / Plan 1, Task 5) ----------

from src.db import (
    log_skipped_ticker, get_ticker_status, is_ticker_inactive,
    reactivate_ticker, list_inactive_tickers, cleanup_old_data,
)


def _skip(conn, ticker: str, date: str = "2026-07-27", times: int = 1) -> None:
    for _ in range(times):
        log_skipped_ticker(
            conn, ticker=ticker, date=date, run_type="pre_market",
            reason="insufficient bars: 0 < 20",
        )


def test_init_schema_creates_ticker_status(in_memory_db):
    init_schema(in_memory_db)
    assert "ticker_status" in get_tables(in_memory_db)


def test_log_skipped_ticker_still_writes_event_row(in_memory_db):
    init_schema(in_memory_db)
    _skip(in_memory_db, "XYZ")
    rows = in_memory_db.execute(
        "SELECT * FROM skipped_tickers WHERE ticker='XYZ'").fetchall()
    assert len(rows) == 1
    assert rows[0]["reason"].startswith("insufficient bars")


def test_log_skipped_ticker_accumulates_skip_count(in_memory_db):
    init_schema(in_memory_db)
    for d in ("2026-07-25", "2026-07-26", "2026-07-27"):
        _skip(in_memory_db, "XYZ", date=d)
    st = get_ticker_status(in_memory_db, "XYZ")
    assert st["skip_count"] == 3
    assert st["first_skip_date"] == "2026-07-25"
    assert st["last_skip_date"] == "2026-07-27"
    assert st["inactive"] == 0


def test_ticker_becomes_inactive_past_threshold(in_memory_db):
    import config
    init_schema(in_memory_db)
    _skip(in_memory_db, "DEAD", times=config.TICKER_MAX_SKIPS + 1)
    st = get_ticker_status(in_memory_db, "DEAD")
    assert st["skip_count"] == config.TICKER_MAX_SKIPS + 1
    assert st["inactive"] == 1
    assert st["retry_after"] == "2026-08-26"   # 2026-07-27 + 30 Tage


def test_ticker_stays_active_exactly_at_threshold(in_memory_db):
    """Deaktivierung erst BEI UEBERSCHREITEN, nicht beim Erreichen."""
    import config
    init_schema(in_memory_db)
    _skip(in_memory_db, "EDGE", times=config.TICKER_MAX_SKIPS)
    st = get_ticker_status(in_memory_db, "EDGE")
    assert st["skip_count"] == config.TICKER_MAX_SKIPS
    assert st["inactive"] == 0
    assert st["retry_after"] is None


def test_is_ticker_inactive_true_before_retry_date(in_memory_db):
    import config
    init_schema(in_memory_db)
    _skip(in_memory_db, "DEAD", times=config.TICKER_MAX_SKIPS + 1)
    assert is_ticker_inactive(in_memory_db, "DEAD", today="2026-08-01") is True


def test_is_ticker_inactive_false_on_and_after_retry_date(in_memory_db):
    import config
    init_schema(in_memory_db)
    _skip(in_memory_db, "DEAD", times=config.TICKER_MAX_SKIPS + 1)
    assert is_ticker_inactive(in_memory_db, "DEAD", today="2026-08-26") is False
    assert is_ticker_inactive(in_memory_db, "DEAD", today="2026-09-30") is False


def test_is_ticker_inactive_false_for_unknown_ticker(in_memory_db):
    init_schema(in_memory_db)
    assert is_ticker_inactive(in_memory_db, "AAPL", today="2026-07-27") is False


def test_is_ticker_inactive_false_for_skipped_but_active_ticker(in_memory_db):
    init_schema(in_memory_db)
    _skip(in_memory_db, "XYZ", times=3)
    assert is_ticker_inactive(in_memory_db, "XYZ", today="2026-07-27") is False


def test_failed_retry_pushes_retry_after_forward(in_memory_db):
    """Schlaegt der Retry erneut fehl, verlaengert sich die Sperre um 30 Tage."""
    import config
    init_schema(in_memory_db)
    _skip(in_memory_db, "DEAD", times=config.TICKER_MAX_SKIPS + 1)
    _skip(in_memory_db, "DEAD", date="2026-08-26")
    st = get_ticker_status(in_memory_db, "DEAD")
    assert st["retry_after"] == "2026-09-25"   # 2026-08-26 + 30 Tage
    assert st["inactive"] == 1


def test_reactivate_ticker_resets_counter_and_flag(in_memory_db):
    import config
    init_schema(in_memory_db)
    _skip(in_memory_db, "DEAD", times=config.TICKER_MAX_SKIPS + 1)
    assert reactivate_ticker(in_memory_db, "DEAD") is True
    st = get_ticker_status(in_memory_db, "DEAD")
    assert st["skip_count"] == 0
    assert st["inactive"] == 0
    assert st["retry_after"] is None


def test_reactivate_ticker_returns_false_when_nothing_to_reset(in_memory_db):
    init_schema(in_memory_db)
    assert reactivate_ticker(in_memory_db, "AAPL") is False


def test_reactivate_ticker_returns_false_on_already_clean_status(in_memory_db):
    init_schema(in_memory_db)
    _skip(in_memory_db, "XYZ")
    reactivate_ticker(in_memory_db, "XYZ")
    assert reactivate_ticker(in_memory_db, "XYZ") is False


def test_list_inactive_tickers(in_memory_db):
    import config
    init_schema(in_memory_db)
    _skip(in_memory_db, "DEAD", times=config.TICKER_MAX_SKIPS + 1)
    _skip(in_memory_db, "OK")
    names = [r["ticker"] for r in list_inactive_tickers(in_memory_db)]
    assert names == ["DEAD"]


def test_cleanup_never_touches_ticker_status(in_memory_db):
    """Der kumulative Zaehler muss die Event-Retention ueberleben (B.7 / D4)."""
    import config
    init_schema(in_memory_db)
    _skip(in_memory_db, "DEAD", date="2020-01-01", times=config.TICKER_MAX_SKIPS + 1)
    cleanup_old_data(in_memory_db)
    st = get_ticker_status(in_memory_db, "DEAD")
    assert st is not None
    assert st["skip_count"] == config.TICKER_MAX_SKIPS + 1
    assert st["inactive"] == 1


# ---------- guardrail_rejects (Sprint 3B / Plan 1, Task 8) ----------

from src.db import log_guardrail_reject, load_guardrail_rejects_since


def test_init_schema_creates_guardrail_rejects(in_memory_db):
    init_schema(in_memory_db)
    assert "guardrail_rejects" in get_tables(in_memory_db)


def test_log_and_load_guardrail_rejects(in_memory_db):
    init_schema(in_memory_db)
    log_guardrail_reject(in_memory_db, {
        "date": "2026-07-27", "run_type": "pre_market", "ticker": "AAPL",
        "direction": "long", "rule": "rr_ratio",
        "detail": "R/R 1.2 below hard minimum 1.5", "enforced": 1,
    })
    log_guardrail_reject(in_memory_db, {
        "date": "2026-07-20", "run_type": "pre_market", "ticker": "MSFT",
        "direction": "short", "rule": "sector_unknown",
        "detail": "no sector mapping", "enforced": 0,
    })
    rows = load_guardrail_rejects_since(in_memory_db, since="2026-07-25")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["rule"] == "rr_ratio"
    assert rows[0]["enforced"] == 1


def test_load_guardrail_rejects_includes_the_since_date_itself(in_memory_db):
    init_schema(in_memory_db)
    log_guardrail_reject(in_memory_db, {
        "date": "2026-07-25", "run_type": "pre_market", "ticker": "AAPL",
        "direction": "long", "rule": "rr_ratio", "detail": "x", "enforced": 1,
    })
    assert len(load_guardrail_rejects_since(in_memory_db, since="2026-07-25")) == 1


def test_log_guardrail_reject_defaults_missing_keys_to_null(in_memory_db):
    """Ein Reject ohne direction/detail darf nicht knallen — die Weekly-Mail
    gruppiert nach rule, alles andere ist optional."""
    init_schema(in_memory_db)
    log_guardrail_reject(in_memory_db, {
        "date": "2026-07-27", "run_type": "pre_market", "ticker": "AAPL",
        "rule": "other", "enforced": 0,
    })
    row = load_guardrail_rejects_since(in_memory_db, since="2026-07-27")[0]
    assert row["direction"] is None
    assert row["detail"] is None


# ---------- Retention (Sprint 3B / Plan 1, Task 9 — Entscheidung D4) ----------


def test_cleanup_deletes_news_older_than_30_days(in_memory_db):
    init_schema(in_memory_db)
    # news_summaries.summary ist NOT NULL — muss mitgegeben werden.
    in_memory_db.execute(
        "INSERT INTO news_summaries (ticker, date, summary) "
        "VALUES ('AAPL', date('now','-45 days'), 'alt')"
    )
    in_memory_db.execute(
        "INSERT INTO news_summaries (ticker, date, summary) "
        "VALUES ('MSFT', date('now','-10 days'), 'frisch')"
    )
    in_memory_db.commit()
    cleanup_old_data(in_memory_db)
    left = [r["ticker"] for r in in_memory_db.execute(
        "SELECT ticker FROM news_summaries").fetchall()]
    assert left == ["MSFT"]


def test_cleanup_keeps_skipped_events_for_90_days(in_memory_db):
    init_schema(in_memory_db)
    in_memory_db.execute(
        "INSERT INTO skipped_tickers (ticker, date, run_type, reason) "
        "VALUES ('OLD', date('now','-100 days'), 'pre_market', 'x')"
    )
    in_memory_db.execute(
        "INSERT INTO skipped_tickers (ticker, date, run_type, reason) "
        "VALUES ('RECENT', date('now','-60 days'), 'pre_market', 'x')"
    )
    in_memory_db.commit()
    cleanup_old_data(in_memory_db)
    left = [r["ticker"] for r in in_memory_db.execute(
        "SELECT ticker FROM skipped_tickers ORDER BY ticker").fetchall()]
    assert left == ["RECENT"]


def test_cleanup_keeps_trend_analyses_for_180_days(in_memory_db):
    """trend_analyses bleibt bei 180 Tagen — D4 aendert nur news und skipped."""
    init_schema(in_memory_db)
    in_memory_db.execute(
        "INSERT INTO trend_analyses (date, run_type, trend_name) "
        "VALUES (date('now','-200 days'), 'pre_market', 'alt')"
    )
    in_memory_db.execute(
        "INSERT INTO trend_analyses (date, run_type, trend_name) "
        "VALUES (date('now','-150 days'), 'pre_market', 'jung')"
    )
    in_memory_db.commit()
    cleanup_old_data(in_memory_db)
    left = [r["trend_name"] for r in in_memory_db.execute(
        "SELECT trend_name FROM trend_analyses").fetchall()]
    assert left == ["jung"]
