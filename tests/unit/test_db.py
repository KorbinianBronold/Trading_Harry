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


# Sprint 3C / Analyse-Pipeline-Umbau, Task 7: 29 neue Spalten fuer die
# Indikatoren aus Task 5/6 (MACD, ADX, PSAR, Ichimoku, Stochastik, TRIX,
# Bollinger-Rohwerte, Donchian, plus sechs Einzelwerte).
NEW_INDICATOR_COLUMNS = [
    "ema_50_dist_pct",
    "macd_line", "macd_signal_line", "macd_hist",
    "adx_14", "di_plus", "di_minus",
    "psar_value", "psar_dir",
    "ichi_tenkan", "ichi_kijun", "ichi_senkou_a", "ichi_senkou_b", "ichi_chikou",
    "stoch_k", "stoch_d",
    "willr_14", "cci_20", "mom_12",
    "trix", "trix_signal",
    "bb_upper", "bb_lower", "bb_width",
    "atr_abs",
    "donch_upper", "donch_mid", "donch_lower",
    "obv",
]


def test_technical_indicators_carries_the_new_columns(tmp_path):
    from src import db
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(technical_indicators)")}
    missing = set(NEW_INDICATOR_COLUMNS) - cols
    assert not missing, f"Fehlende Spalten: {sorted(missing)}"


def test_migration_adds_columns_to_an_existing_table(tmp_path):
    """Die Migration muss auf einer ALTEN Tabelle greifen, nicht nur auf einer
    frisch angelegten -- sonst bleibt die Produktions-DB zurueck."""
    from src import db
    path = str(tmp_path / "old.db")
    conn = db.connect(path)
    conn.executescript("""
        CREATE TABLE technical_indicators (
            ticker TEXT NOT NULL, date TEXT NOT NULL,
            rsi_14 REAL, macd_signal TEXT, atr_pct REAL,
            bb_position REAL, above_sma20 REAL, above_sma50 REAL,
            above_sma200 REAL, volume_ratio REAL,
            UNIQUE(ticker, date)
        );
    """)
    conn.commit()

    db.init_schema(conn)

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(technical_indicators)")}
    assert set(NEW_INDICATOR_COLUMNS) <= cols


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


# ---------- load_trend_context (Task 13): der 16:10-Lauf liest den Morgen ----------

def test_load_trend_context_mirrors_analyze_trends_shape(in_memory_db):
    """Der 16:10-Lauf macht keine eigene Trendanalyse, sondern liest die
    Morgen-Zeilen aus trend_analyses — im selben Format, das analyze_trends()
    liefert (Schluessel 'name', nicht die DB-Spalte 'trend_name')."""
    from src.db import load_trend_context
    init_schema(in_memory_db)
    save_trend_analysis(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "trend_name": "ai-capex-acceleration",
        "strength": 8, "duration_estimate": "1m+",
        "summary": "Hyperscalers raised guidance.",
        "beneficiary_tickers": ["NVDA", "AVGO"],
        "negative_tickers": ["INTC"],
        "next_catalyst": "GTC keynote 2026-06-12",
    })
    ctx = load_trend_context(in_memory_db, "2026-07-30")
    assert len(ctx["trends"]) == 1
    trend = ctx["trends"][0]
    assert trend["name"] == "ai-capex-acceleration"
    assert trend["strength"] == 8
    assert trend["beneficiary_tickers"] == ["NVDA", "AVGO"]
    assert trend["negative_tickers"] == ["INTC"]


def test_load_trend_context_is_empty_dict_without_a_morning_entry(in_memory_db):
    """Faellt Phase 0 am Morgen aus, gibt es fuer den Tag keine Zeile —
    der Portfolio-Check muss mit einem leeren Kontext klarkommen."""
    from src.db import load_trend_context
    init_schema(in_memory_db)
    assert load_trend_context(in_memory_db, "2026-07-30") == {}


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


def test_save_prediction_persists_sector_momentum(in_memory_db):
    """Die Spalten existierten seit Plan 1, wurden aber nie geschrieben."""
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market", "ticker": "AAPL",
        "direction": "long", "sector_etf_momentum": -1.5, "sector_db_momentum": -0.9,
    })
    row = in_memory_db.execute(
        "SELECT sector_etf_momentum, sector_db_momentum FROM predictions WHERE id=?",
        (pid,)).fetchone()
    assert row["sector_etf_momentum"] == -1.5
    assert row["sector_db_momentum"] == -0.9


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


def test_load_open_predictions_excludes_same_day_predictions(in_memory_db):
    """Sprint 3B / Plan 2, Task 6 Fix: eine Prediction von heute ist noch keine
    offene Position, sondern nur ein frischer Vorschlag aus Phase 4 desselben
    Laufs — erst ab dem Folgetag darf Phase 4a sie gegenchecken."""
    db.init_schema(in_memory_db)
    pid_today = _insert_test_prediction(in_memory_db, date="2026-05-20")
    rows = db.load_open_predictions_within_max_age_days(
        in_memory_db, today="2026-05-20", max_trading_days=5,
    )
    ids = {r["id"] for r in rows}
    assert pid_today not in ids


def test_load_open_predictions_includes_yesterdays_open_prediction(in_memory_db):
    """Gegenprobe zum Ausschluss: eine noch offene Prediction von gestern muss
    weiterhin gefunden werden, der Folgetag-Filter darf nicht zu viel wegschneiden."""
    db.init_schema(in_memory_db)
    pid_yesterday = _insert_test_prediction(in_memory_db, date="2026-05-19")
    rows = db.load_open_predictions_within_max_age_days(
        in_memory_db, today="2026-05-20", max_trading_days=5,
    )
    ids = {r["id"] for r in rows}
    assert pid_yesterday in ids


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


# ---------- earnings_next_date (Sprint 3C / Analyse-Pipeline-Umbau, Task 7) ----------
# R12/R13: save_fundamentals_cache() schreibt ein INSERT OR REPLACE mit fest
# aufgezaehlter Spaltenliste -- ein zusaetzlicher dict-Key allein reicht nicht,
# er muss auch dort eingetragen sein. Der Test liest deshalb aus der DB
# zurueck statt nur den Funktionsaufruf zu pruefen.

def test_save_fundamentals_cache_persists_earnings_next_date(in_memory_db):
    """R13: earnings_next_date landet WIRKLICH in der DB, nicht nur im Aufruf."""
    init_schema(in_memory_db)
    save_fundamentals_cache(
        in_memory_db, "AAPL",
        {"pe_ratio": 25.0, "earnings_next_date": "2026-06-02"},
        fetched_date="2026-05-21",
    )
    row = in_memory_db.execute(
        "SELECT earnings_next_date FROM fundamentals_cache WHERE ticker=?", ("AAPL",)
    ).fetchone()
    assert row is not None
    assert row["earnings_next_date"] == "2026-06-02"


def test_save_fundamentals_cache_earnings_next_date_defaults_to_null(in_memory_db):
    """Kein earnings_next_date im data-dict -> NULL, kein KeyError."""
    init_schema(in_memory_db)
    save_fundamentals_cache(in_memory_db, "AAPL", {"pe_ratio": 25.0}, fetched_date="2026-05-21")
    row = in_memory_db.execute(
        "SELECT earnings_next_date FROM fundamentals_cache WHERE ticker=?", ("AAPL",)
    ).fetchone()
    assert row["earnings_next_date"] is None


def test_get_cached_fundamentals_returns_earnings_next_date(in_memory_db):
    """get_cached_fundamentals() macht SELECT * -- die neue Spalte kommt
    automatisch mit, ohne dass die Lesefunktion angefasst werden muss."""
    init_schema(in_memory_db)
    save_fundamentals_cache(
        in_memory_db, "AAPL",
        {"pe_ratio": 25.0, "earnings_next_date": "2026-06-02"},
        fetched_date="2026-05-21",
    )
    result = get_cached_fundamentals(in_memory_db, "AAPL", today="2026-05-21")
    assert result["earnings_next_date"] == "2026-06-02"


def test_migration_adds_earnings_next_date_idempotently(in_memory_db):
    """R12: zweimal init_schema() laeuft ohne Fehler, Spalte existiert danach."""
    init_schema(in_memory_db)
    init_schema(in_memory_db)
    cols = {r["name"] for r in in_memory_db.execute(
        "PRAGMA table_info(fundamentals_cache)").fetchall()}
    assert "earnings_next_date" in cols


def test_migration_adds_earnings_next_date_to_a_legacy_fundamentals_cache():
    """R12: Migration gegen eine DB, deren fundamentals_cache die Spalte noch
    nicht kennt (Muster wie test_migration_adds_supersede_columns_to_an_existing_db)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE fundamentals_cache (
        ticker TEXT NOT NULL, fetched_date TEXT NOT NULL,
        pe_ratio REAL, forward_pe REAL, market_cap_b REAL,
        debt_equity REAL, sector TEXT, analyst_upside REAL, consensus TEXT,
        UNIQUE(ticker))""")
    conn.commit()
    init_schema(conn)
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(fundamentals_cache)").fetchall()}
    assert "earnings_next_date" in cols
    conn.close()


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


def test_log_guardrail_reject_persists_sector_momentum(in_memory_db):
    db.init_schema(in_memory_db)
    db.log_guardrail_reject(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market", "ticker": "AAPL",
        "direction": "long", "rule": "sector_momentum", "detail": "x",
        "enforced": 0, "sector_etf_momentum": -1.5, "sector_db_momentum": -0.9,
    })
    row = in_memory_db.execute(
        "SELECT sector_etf_momentum, sector_db_momentum FROM guardrail_rejects"
    ).fetchone()
    assert row["sector_etf_momentum"] == -1.5
    assert row["sector_db_momentum"] == -0.9


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


# ---------- sector_momentum (Sprint 3B / Plan 1, Task 9a — Entscheidung D9) ----------

from src.db import (
    compute_sector_db_momentum, save_sector_momentum, load_sector_momentum,
)


def _bar(conn, ticker: str, date: str, close: float) -> None:
    from src import db as _db
    _db.insert_price_bar_if_missing(
        conn, ticker=ticker, date=date, open_=close, high=close,
        low=close, close=close, volume=1000, source="capital.com",
    )


def test_init_schema_creates_sector_momentum(in_memory_db):
    init_schema(in_memory_db)
    assert "sector_momentum" in get_tables(in_memory_db)


def test_predictions_has_sector_momentum_columns(in_memory_db):
    init_schema(in_memory_db)
    cols = {r["name"] for r in in_memory_db.execute(
        "PRAGMA table_info(predictions)").fetchall()}
    assert {"sector_etf_momentum", "sector_db_momentum"}.issubset(cols)


def test_guardrail_rejects_has_sector_momentum_columns(in_memory_db):
    init_schema(in_memory_db)
    cols = {r["name"] for r in in_memory_db.execute(
        "PRAGMA table_info(guardrail_rejects)").fetchall()}
    assert {"sector_etf_momentum", "sector_db_momentum"}.issubset(cols)


def test_compute_sector_db_momentum_averages_daily_change(in_memory_db):
    """Drei Pharma-Ticker mit +2%, +4% und +6% ergeben +4% Sektor-Momentum."""
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Pharmaceuticals")
    for t, prev, today in (("JNJ", 100.0, 102.0), ("LLY", 100.0, 104.0),
                           ("ABBV", 100.0, 106.0)):
        upsert_ticker_sector(in_memory_db, t, sid)
        _bar(in_memory_db, t, "2026-07-24", prev)
        _bar(in_memory_db, t, "2026-07-27", today)
    in_memory_db.commit()

    out = compute_sector_db_momentum(in_memory_db, date="2026-07-27")
    assert out[sid]["ticker_count"] == 3
    assert round(out[sid]["momentum"], 4) == 4.0


def test_compute_sector_db_momentum_is_none_below_minimum(in_memory_db):
    """Zwei Ticker reichen nicht — der Durchschnitt waere statistisch wertlos."""
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Semiconductors")
    for t in ("NVDA", "AVGO"):
        upsert_ticker_sector(in_memory_db, t, sid)
        _bar(in_memory_db, t, "2026-07-24", 100.0)
        _bar(in_memory_db, t, "2026-07-27", 105.0)
    in_memory_db.commit()

    out = compute_sector_db_momentum(in_memory_db, date="2026-07-27")
    assert out[sid]["momentum"] is None
    assert out[sid]["ticker_count"] == 2


def test_compute_sector_db_momentum_honours_custom_minimum(in_memory_db):
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Semiconductors")
    for t in ("NVDA", "AVGO"):
        upsert_ticker_sector(in_memory_db, t, sid)
        _bar(in_memory_db, t, "2026-07-24", 100.0)
        _bar(in_memory_db, t, "2026-07-27", 105.0)
    in_memory_db.commit()
    out = compute_sector_db_momentum(in_memory_db, date="2026-07-27", min_tickers=2)
    assert round(out[sid]["momentum"], 4) == 5.0


def test_compute_sector_db_momentum_skips_tickers_without_previous_bar(in_memory_db):
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Pharmaceuticals")
    for t in ("JNJ", "LLY", "ABBV"):
        upsert_ticker_sector(in_memory_db, t, sid)
        _bar(in_memory_db, t, "2026-07-27", 105.0)
    _bar(in_memory_db, "JNJ", "2026-07-24", 100.0)
    in_memory_db.commit()
    out = compute_sector_db_momentum(in_memory_db, date="2026-07-27")
    assert out.get(sid, {}).get("ticker_count", 0) == 1


def test_compute_sector_db_momentum_ignores_bars_after_the_date(in_memory_db):
    """Der Vortagesbar muss echt vor `date` liegen — sonst wuerde ein spaeter
    nachgeladener Bar die Tagesperformance verfaelschen."""
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Pharmaceuticals")
    for t in ("JNJ", "LLY", "ABBV"):
        upsert_ticker_sector(in_memory_db, t, sid)
        _bar(in_memory_db, t, "2026-07-24", 100.0)
        _bar(in_memory_db, t, "2026-07-27", 102.0)
        _bar(in_memory_db, t, "2026-07-28", 200.0)
    in_memory_db.commit()
    out = compute_sector_db_momentum(in_memory_db, date="2026-07-27")
    assert round(out[sid]["momentum"], 4) == 2.0


def test_compute_sector_db_momentum_ignores_unmapped_tickers(in_memory_db):
    init_schema(in_memory_db)
    _bar(in_memory_db, "NOSECTOR", "2026-07-24", 100.0)
    _bar(in_memory_db, "NOSECTOR", "2026-07-27", 110.0)
    in_memory_db.commit()
    assert compute_sector_db_momentum(in_memory_db, date="2026-07-27") == {}


def test_sector_db_momentum_uses_the_last_final_day(in_memory_db):
    """Der Join lief auf cur.date = heute, also exakte Gleichheit. Seit
    price_history nur noch finale Bars enthaelt, existiert die heutige Zeile zur
    Laufzeit nicht -- der Join traefe nie, db_momentum bliebe dauerhaft NULL, D9
    koennte 'beide Signale vorhanden' nie erfuellen und der Sektor-Guardrail
    waere lautlos tot."""
    db.init_schema(in_memory_db)
    in_memory_db.execute(
        "INSERT INTO sectors (name, etf) VALUES ('Semis', 'SOXX')")
    sid = in_memory_db.execute(
        "SELECT id FROM sectors WHERE name='Semis'").fetchone()["id"]
    for t in ("AAPL", "MSFT", "NVDA"):
        in_memory_db.execute(
            "INSERT INTO ticker_sectors (ticker, sector_id) VALUES (?, ?)", (t, sid))
        db.upsert_price_history(in_memory_db, t, "2026-08-04", 100, 101, 99, 100, 10)
        db.upsert_price_history(in_memory_db, t, "2026-08-05", 100, 103, 100, 102, 10)
    in_memory_db.commit()

    # Lauf am 2026-08-06: fuer heute gibt es noch keine finale Bar.
    out = db.compute_sector_db_momentum(in_memory_db, date="2026-08-06")
    assert sid in out, "der Sektor muss trotzdem einen Wert bekommen"
    assert out[sid]["momentum"] == pytest.approx(2.0), "102 gegen 100 sind +2 %"
    assert out[sid]["ticker_count"] == 3


def _sector_with(conn, name: str, bars: dict[str, list[tuple[str, float]]]) -> int:
    """Legt einen Sub-Sektor an und haengt je Ticker die uebergebenen
    (Datum, Close)-Bars ein. Gibt die sector_id zurueck."""
    sid = resolve_sector_id(conn, name)
    for ticker, rows in bars.items():
        upsert_ticker_sector(conn, ticker, sid)
        for d, close in rows:
            _bar(conn, ticker, d, close)
    conn.commit()
    return sid


def test_sector_db_momentum_ignores_stillgelegte_ticker(in_memory_db):
    """Ein stillgelegter Ticker trug seine letzte je vorhandene Tagesbewegung
    dauerhaft weiter, weil 'die letzten zwei Bars' kein Alter kennt.

    Gemessen mit zwei lebenden Tickern (+2 %) und einem seit Maerz toten
    (+50 %): das Sektor-Momentum sprang von None auf 18,0, und ticker_count
    erreichte faelschlich das Minimum -- aus 'kein Signal' wurde 'starkes
    Signal', auf das D9 gehandelt haette. Kein Uebervorsichts-Riegel."""
    init_schema(in_memory_db)
    sid = _sector_with(in_memory_db, "Semiconductors", {
        "AAPL": [("2026-08-04", 100.0), ("2026-08-05", 102.0)],
        "MSFT": [("2026-08-04", 100.0), ("2026-08-05", 102.0)],
        # Seit Maerz tot, damals +50 %.
        "DEAD": [("2026-03-02", 100.0), ("2026-03-03", 150.0)],
    })

    out = db.compute_sector_db_momentum(in_memory_db, date="2026-08-06")
    assert out[sid]["ticker_count"] == 2, "der tote Ticker zaehlt nicht mit"
    assert out[sid]["momentum"] is None, (
        "zwei Ticker unterschreiten min_tickers=3 -- ohne Riegel waeren es 18,0")


def test_sector_db_momentum_ignores_ticker_with_a_gap(in_memory_db):
    """Frischer letzter Bar, aber der Vorgaenger liegt Monate davor: die
    Fuenf-Monats-Bewegung wuerde als *Tages*performance verrechnet. Eine reine
    Frischepruefung auf den letzten Bar liesse genau diesen Fall durch."""
    init_schema(in_memory_db)
    sid = _sector_with(in_memory_db, "Pharmaceuticals", {
        "JNJ": [("2026-08-04", 100.0), ("2026-08-05", 102.0)],
        "LLY": [("2026-08-04", 100.0), ("2026-08-05", 102.0)],
        # Letzter Bar ist frisch, der davor stammt vom 1. Maerz.
        "GAPY": [("2026-03-01", 100.0), ("2026-08-05", 150.0)],
    })

    out = db.compute_sector_db_momentum(in_memory_db, date="2026-08-06")
    assert out[sid]["ticker_count"] == 2, "der Ticker mit Luecke zaehlt nicht mit"
    assert out[sid]["momentum"] is None


def test_sector_db_momentum_counts_a_friday_bar_on_monday(in_memory_db):
    """Gegenprobe: der Riegel darf den Normalbetrieb nicht abschneiden.

    Montagslauf (2026-08-10), letzter finaler Bar ist der Freitag (08-07) --
    drei Kalendertage. Ein zu scharfer Riegel waere derselbe stille Ausfall
    noch einmal, nur andersherum."""
    init_schema(in_memory_db)
    sid = _sector_with(in_memory_db, "Semiconductors", {
        t: [("2026-08-06", 100.0), ("2026-08-07", 102.0)]
        for t in ("NVDA", "AVGO", "AMD")
    })

    out = db.compute_sector_db_momentum(in_memory_db, date="2026-08-10")
    assert out[sid]["ticker_count"] == 3, "Freitagsbar am Montag zaehlt regulaer"
    assert out[sid]["momentum"] == pytest.approx(2.0)


def test_save_and_load_sector_momentum_upserts(in_memory_db):
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Semiconductors")
    row = {"date": "2026-07-27", "run_type": "pre_market", "sector_id": sid,
           "etf_momentum": 1.5, "db_momentum": None, "ticker_count": 2}
    save_sector_momentum(in_memory_db, row)
    save_sector_momentum(in_memory_db, {**row, "etf_momentum": 2.5})
    loaded = load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")
    assert len(loaded) == 1
    assert loaded[sid]["etf_momentum"] == 2.5
    assert loaded[sid]["db_momentum"] is None


def test_load_sector_momentum_is_scoped_to_date_and_run_type(in_memory_db):
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Semiconductors")
    base = {"sector_id": sid, "etf_momentum": 1.0,
            "db_momentum": None, "ticker_count": 0}
    save_sector_momentum(in_memory_db, {**base, "date": "2026-07-27",
                                        "run_type": "pre_market"})
    save_sector_momentum(in_memory_db, {**base, "date": "2026-07-27",
                                        "run_type": "trade_proposals"})
    save_sector_momentum(in_memory_db, {**base, "date": "2026-07-26",
                                        "run_type": "pre_market"})
    assert len(load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")) == 1
    assert load_sector_momentum(in_memory_db, "2026-07-25", "pre_market") == {}


# ---------- market_context (Sprint 3B / Plan 1, Task 10 — Entscheidung D2) ----------

from src.db import save_market_context


def test_market_context_has_advance_decline_column(in_memory_db):
    init_schema(in_memory_db)
    cols = {r["name"] for r in in_memory_db.execute(
        "PRAGMA table_info(market_context)").fetchall()}
    assert "advance_decline_ratio" in cols


def test_save_market_context_upserts_on_date_and_run_type(in_memory_db):
    init_schema(in_memory_db)
    row = {
        "date": "2026-07-27", "run_type": "pre_market", "vix_level": 18.0,
        "advance_decline_ratio": 1.4, "market_regime": "risk_on",
        "sector_rotation_in": "Technology", "sector_rotation_out": "Utilities",
        "macro_summary": "ruhig",
    }
    save_market_context(in_memory_db, row)
    save_market_context(in_memory_db, {**row, "vix_level": 22.0})
    rows = in_memory_db.execute("SELECT * FROM market_context").fetchall()
    assert len(rows) == 1
    assert rows[0]["vix_level"] == 22.0
    assert rows[0]["advance_decline_ratio"] == 1.4


def test_save_market_context_keeps_runs_of_the_same_day_apart(in_memory_db):
    """pre_market und trade_proposals messen denselben Tag zu anderer Stunde."""
    init_schema(in_memory_db)
    base = {"date": "2026-07-27", "vix_level": 18.0, "market_regime": "risk_on"}
    save_market_context(in_memory_db, {**base, "run_type": "pre_market"})
    save_market_context(in_memory_db, {**base, "run_type": "trade_proposals",
                                       "vix_level": 26.0})
    rows = in_memory_db.execute(
        "SELECT run_type, vix_level FROM market_context ORDER BY run_type").fetchall()
    assert [(r["run_type"], r["vix_level"]) for r in rows] == [
        ("pre_market", 18.0), ("trade_proposals", 26.0),
    ]


def test_save_market_context_tolerates_a_sparse_row(in_memory_db):
    """Ein Kontext, in dem Claude nichts belegen konnte, muss speicherbar sein."""
    init_schema(in_memory_db)
    save_market_context(in_memory_db, {"date": "2026-07-27",
                                       "run_type": "pre_market"})
    row = in_memory_db.execute("SELECT * FROM market_context").fetchone()
    assert row["vix_level"] is None
    assert row["market_regime"] is None


# ---------- Migrationspfad bestehender DBs (Regel 5) ----------


_SPRINT3B_TABLES = ("sectors", "ticker_sectors", "ticker_status",
                    "guardrail_rejects", "sector_momentum")
_SPRINT3B_COLUMNS = (
    ("market_context", "advance_decline_ratio"),
    ("predictions",    "sector_etf_momentum"),
    ("predictions",    "sector_db_momentum"),
)


def _legacy_db() -> sqlite3.Connection:
    """Eine DB im Zustand VOR Sprint 3B. Aufgebaut aus dem echten Schema, dann
    um die 3B-Zugaenge zurueckgebaut — so bleibt der Rest originalgetreu und der
    Test bricht nicht bei jeder unabhaengigen Schema-Erweiterung.

    Genau diesen Fall muss _apply_migrations() abfangen: CREATE TABLE IF NOT
    EXISTS legt eine fehlende Tabelle an, fasst eine bestehende aber nie an —
    neue Spalten brauchen den PRAGMA-Guard (Regel 5)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    for table in _SPRINT3B_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    for table, column in _SPRINT3B_COLUMNS:
        conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    conn.execute(
        "INSERT INTO market_context (date, run_type, vix_level) "
        "VALUES ('2026-01-02', 'pre_market', 15.0)"
    )
    conn.commit()
    return conn


def test_legacy_db_really_lacks_the_sprint3b_additions():
    """Schutz vor einem stumpfen Fixture: waeren die Zugaenge schon da, wuerden
    die Migrationstests unten nichts mehr beweisen."""
    conn = _legacy_db()
    tables = set(get_tables(conn))
    assert not tables & set(_SPRINT3B_TABLES)
    for table, column in _SPRINT3B_COLUMNS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        assert column not in cols
    conn.close()


def test_migration_adds_advance_decline_ratio_to_existing_market_context():
    conn = _legacy_db()
    init_schema(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(market_context)")}
    assert "advance_decline_ratio" in cols
    conn.close()


def test_migration_adds_sector_momentum_columns_to_existing_predictions():
    conn = _legacy_db()
    init_schema(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(predictions)")}
    assert {"sector_etf_momentum", "sector_db_momentum"}.issubset(cols)
    conn.close()


def test_migration_creates_the_new_sprint3b_tables():
    conn = _legacy_db()
    init_schema(conn)
    tables = set(get_tables(conn))
    assert {"sectors", "ticker_sectors", "ticker_status",
            "guardrail_rejects", "sector_momentum"}.issubset(tables)
    assert conn.execute("SELECT COUNT(*) AS n FROM sectors").fetchone()["n"] == 21
    conn.close()


def test_migration_preserves_existing_rows():
    """Eine Migration darf nie Daten kosten."""
    conn = _legacy_db()
    init_schema(conn)
    row = conn.execute("SELECT * FROM market_context").fetchone()
    assert row["vix_level"] == 15.0
    assert row["advance_decline_ratio"] is None
    conn.close()


def test_migration_is_idempotent_on_an_already_migrated_db():
    conn = _legacy_db()
    init_schema(conn)
    init_schema(conn)
    assert conn.execute("SELECT COUNT(*) AS n FROM sectors").fetchone()["n"] == 21
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM market_context").fetchone()["n"] == 1
    conn.close()


# ---------- E3: Ablösung statt Dopplung ----------

def test_predictions_has_supersede_columns(in_memory_db):
    db.init_schema(in_memory_db)
    cols = {r["name"] for r in in_memory_db.execute(
        "PRAGMA table_info(predictions)").fetchall()}
    assert {"superseded_by", "revision_verdict"}.issubset(cols)


def test_migration_adds_supersede_columns_to_an_existing_db(tmp_db_path):
    """Migration gegen eine DB, die die Spalten noch nicht kennt (Regel 5)."""
    import sqlite3
    conn = sqlite3.connect(tmp_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
        run_type TEXT NOT NULL, ticker TEXT NOT NULL, direction TEXT NOT NULL,
        status TEXT DEFAULT 'open', learnable BOOLEAN DEFAULT 1)""")
    conn.commit()
    db.init_schema(conn)
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(predictions)").fetchall()}
    assert {"superseded_by", "revision_verdict"}.issubset(cols)
    conn.close()


def test_record_revision_cannot_supersede_a_row(in_memory_db):
    """record_revision() loest NIE ab — dafuer gibt es ausschliesslich
    supersede_prediction(), das INSERT und UPDATE in eine Transaktion legt (C1,
    P2.8). Der frueher hier vorhandene superseded_by-Parameter war der zweite,
    nicht-atomare Weg zum selben Ziel und ist entfernt: seit dem partiellen
    UNIQUE-Index koennen alte und neue Zeile ohnehin nicht gleichzeitig offen
    sein, sein einziger Anwendungsfall war also strukturell unmoeglich geworden."""
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "long"})

    with pytest.raises(TypeError):
        db.record_revision(in_memory_db, pid, verdict="bestaetigt", superseded_by=99)

    # Auch das Urteil, das frueher zur Abloesung gehoerte, laesst die Zeile offen.
    db.record_revision(in_memory_db, pid, verdict="bestaetigt")
    row = in_memory_db.execute(
        "SELECT status, superseded_by FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row["status"] == "open"
    assert row["superseded_by"] is None


def test_record_revision_keeps_a_rejected_signal_open(in_memory_db):
    """E5: ein gedrehtes Signal bleibt offen und wird regulaer ausgewertet —
    genau das beantwortet, ob die Drehung richtig lag."""
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "long"})
    db.record_revision(in_memory_db, pid, verdict="gedreht")
    row = in_memory_db.execute(
        "SELECT status, superseded_by, revision_verdict FROM predictions WHERE id=?",
        (pid,)).fetchone()
    assert row["status"] == "open"
    assert row["superseded_by"] is None
    assert row["revision_verdict"] == "gedreht"


class _UpdateFailsConn:
    """Reicht alles an die echte Verbindung durch, laesst aber jedes
    UPDATE predictions scheitern — simuliert den Abbruch (Lock, Job-Kill,
    Runner-Timeout) genau zwischen INSERT und UPDATE."""

    def __init__(self, real):
        self._real = real

    def execute(self, sql, *args, **kwargs):
        if sql.strip().upper().startswith("UPDATE PREDICTIONS"):
            raise sqlite3.OperationalError("database is locked")
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_supersede_prediction_is_atomic(in_memory_db):
    """C1: INSERT der Nachfolgezeile und UPDATE der abgeloesten Zeile muessen in
    EINER Transaktion liegen.

    Reisst der UPDATE weg, darf keine zweite offene Zeile zurueckbleiben. Sonst
    stehen zwei offene, lernbare Zeilen fuer dieselbe (date, ticker, direction) in
    der DB, der Evaluator schliesst beide, und Weekly-P&L wie Mail-Footer zaehlen
    doppelt — exakt die Doppelzaehlung, die E3 verhindern soll. Ein UNIQUE ueber
    die drei Spalten gibt es laut Befund 8 nicht, ein Reparaturlauf ebenso wenig:
    der Zustand bliebe dauerhaft."""
    db.init_schema(in_memory_db)
    old = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "long"})

    with pytest.raises(sqlite3.OperationalError):
        db.supersede_prediction(
            _UpdateFailsConn(in_memory_db), old,
            {"date": "2026-07-30", "run_type": "trade_proposals",
             "ticker": "AAPL", "direction": "long"},
            verdict="bestaetigt")

    open_rows = in_memory_db.execute(
        "SELECT * FROM predictions WHERE status = 'open' AND learnable = 1"
    ).fetchall()
    assert len(open_rows) == 1, (
        "nach dem Fehlschlag darf nur die pre_market-Zeile offen sein — sonst "
        "schliesst der Evaluator beide")
    assert open_rows[0]["id"] == old
    assert open_rows[0]["revision_verdict"] is None


def test_supersede_prediction_writes_both_sides(in_memory_db):
    """Der Normalfall: neue Zeile entsteht, alte wird im selben Zug abgeloest."""
    db.init_schema(in_memory_db)
    old = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "long", "entry_price": 100.0})

    new_id = db.supersede_prediction(in_memory_db, old, {
        "date": "2026-07-30", "run_type": "trade_proposals",
        "ticker": "AAPL", "direction": "long", "entry_price": 101.5,
    }, verdict="bestaetigt")

    old_row = in_memory_db.execute(
        "SELECT * FROM predictions WHERE id=?", (old,)).fetchone()
    new_row = in_memory_db.execute(
        "SELECT * FROM predictions WHERE id=?", (new_id,)).fetchone()
    assert old_row["status"] == "superseded"
    assert old_row["superseded_by"] == new_id
    assert old_row["revision_verdict"] == "bestaetigt"
    assert new_row["run_type"] == "trade_proposals"
    assert new_row["entry_price"] == 101.5
    assert new_row["status"] == "open"
    # Die neue Zeile traegt bewusst KEIN Urteil — es sitzt auf der alten, weil in
    # drei von sechs Ausgaengen gar keine neue entsteht.
    assert new_row["revision_verdict"] is None


def test_second_open_prediction_for_the_same_idea_is_rejected(in_memory_db):
    """Zwei offene Zeilen fuer dieselbe (date, ticker, direction) darf es nie
    geben — der Evaluator schloesse beide und jede Kennzahl zaehlte doppelt.

    Real passiert am 2026-08-13, als pre_market zweimal lief (P2.12, Befund 1)."""
    db.init_schema(in_memory_db)
    first = db.save_prediction(in_memory_db, {
        "date": "2026-08-13", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "short", "entry_price": 303.35})

    second = db.save_prediction(in_memory_db, {
        "date": "2026-08-13", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "short", "entry_price": 303.29})

    assert first is not None
    assert second is None, "der Doppellauf darf keine zweite Zeile anlegen"
    open_rows = in_memory_db.execute(
        "SELECT * FROM predictions WHERE status='open'").fetchall()
    assert len(open_rows) == 1
    assert open_rows[0]["entry_price"] == 303.35, "die erste Zeile bleibt stehen"


def test_init_schema_closes_preexisting_open_duplicates(in_memory_db):
    """Bestandsdatenbanken tragen die Duplikate schon — ohne Bereinigung liesse
    sich der Index dort gar nicht anlegen und jeder Lauf stuerbe an init_schema."""
    db.init_schema(in_memory_db)
    in_memory_db.execute("DROP INDEX IF EXISTS ux_predictions_one_open_per_idea")
    older = db._insert_prediction(in_memory_db, {
        "date": "2026-08-13", "run_type": "pre_market",
        "ticker": "XOM", "direction": "long", "entry_price": 158.24})
    newer = db._insert_prediction(in_memory_db, {
        "date": "2026-08-13", "run_type": "pre_market",
        "ticker": "XOM", "direction": "long", "entry_price": 158.24})
    in_memory_db.commit()

    db.init_schema(in_memory_db)

    older_row = in_memory_db.execute(
        "SELECT * FROM predictions WHERE id=?", (older,)).fetchone()
    newer_row = in_memory_db.execute(
        "SELECT * FROM predictions WHERE id=?", (newer,)).fetchone()
    assert older_row["status"] == "closed_stale_pre_rollout"
    assert older_row["learnable"] == 0, "eine Dublette gehoert nie ins Lernmodul"
    assert newer_row["status"] == "open", "die juengste Zeile bleibt die gueltige"


def test_superseded_predictions_are_invisible_to_the_evaluator(in_memory_db):
    """Der Kern von E3: eine Trade-Idee, genau EIN Outcome. Ohne das zaehlt
    jede Kennzahl doppelt."""
    db.init_schema(in_memory_db)
    old = db.save_prediction(in_memory_db, {
        "date": "2026-07-29", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "long"})
    # Ueber supersede_prediction() statt record_revision(): das ist der Weg, den
    # run_trade_proposals() geht, und seit dem UNIQUE-Index der einzige, auf dem
    # beide Zeilen ueberhaupt entstehen koennen.
    new = db.supersede_prediction(in_memory_db, old, {
        "date": "2026-07-29", "run_type": "trade_proposals",
        "ticker": "AAPL", "direction": "long"}, verdict="bestaetigt")
    open_ids = {r["id"] for r in db.load_open_predictions(in_memory_db)}
    assert open_ids == {new}
    within = {r["id"] for r in db.load_open_predictions_within_max_age_days(
        in_memory_db, today="2026-07-30")}
    assert within == {new}, "auch Phase 4a darf den Ticker nur einmal sehen"


def test_load_predictions_for_revalidation_is_scoped(in_memory_db):
    db.init_schema(in_memory_db)
    keep = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "long"})
    db.save_prediction(in_memory_db, {          # falscher Tag
        "date": "2026-07-29", "run_type": "pre_market",
        "ticker": "MSFT", "direction": "long"})
    db.save_prediction(in_memory_db, {          # falscher run_type
        "date": "2026-07-30", "run_type": "trade_proposals",
        "ticker": "NVDA", "direction": "long"})
    rows = db.load_predictions_for_revalidation(in_memory_db, "2026-07-30")
    assert {r["id"] for r in rows} == {keep}


# --- Sprint 3B / Plan 2, Task 18: Weekly-Aggregate fuer die vier B.9-Bloecke ---

def _outcome(conn, pred_id, correct, pl):
    conn.execute(
        """INSERT INTO outcomes (prediction_id, evaluated_date,
                                 correct_direction_eod, profit_loss_eur)
           VALUES (?, '2026-07-31', ?, ?)""",
        (pred_id, 1 if correct else 0, pl))
    conn.commit()


def test_revision_effectiveness_splits_confirmed_from_rejected(in_memory_db):
    """Der Kern von B.9/Block 1 in der Fassung nach E3."""
    db.init_schema(in_memory_db)
    good = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "trade_proposals",
        "ticker": "AAPL", "direction": "long"})
    bad = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "ticker": "NVDA", "direction": "long"})
    db.record_revision(in_memory_db, bad, verdict="gedreht")
    _outcome(in_memory_db, good, correct=True, pl=25.0)
    _outcome(in_memory_db, bad, correct=False, pl=-30.0)

    out = db.load_revision_effectiveness(in_memory_db, since_date="2026-07-01")
    assert out["confirmed"]["total"] == 1 and out["confirmed"]["correct"] == 1
    assert out["rejected"]["total"] == 1 and out["rejected"]["correct"] == 0
    assert out["confirmed"]["pl_eur"] == 25.0
    assert out["rejected"]["pl_eur"] == -30.0


def test_revision_effectiveness_excludes_rows_before_the_first_1610_run(in_memory_db):
    """Sonst waechst 'nie geprueft' auf Dauer als Altlast mit."""
    db.init_schema(in_memory_db)
    old = db.save_prediction(in_memory_db, {
        "date": "2026-07-01", "run_type": "pre_market",
        "ticker": "MSFT", "direction": "long"})
    _outcome(in_memory_db, old, correct=False, pl=-10.0)
    db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "trade_proposals",
        "ticker": "AAPL", "direction": "long"})

    out = db.load_revision_effectiveness(in_memory_db, since_date="2026-06-01")
    assert out["unchecked"]["total"] == 0, "Altlast vor dem ersten 16:10-Lauf"


def test_revision_effectiveness_is_empty_without_any_1610_run(in_memory_db):
    db.init_schema(in_memory_db)
    db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "long"})
    out = db.load_revision_effectiveness(in_memory_db, since_date="2026-07-01")
    assert out["confirmed"]["total"] == 0
    assert out["rejected"]["total"] == 0


def test_revision_verdict_stats_group_by_verdict(in_memory_db):
    db.init_schema(in_memory_db)
    # Je Verdict ein eigener Ticker: drei offene Zeilen fuer dieselbe Trade-Idee
    # laesst der partielle UNIQUE-Index nicht mehr zu, und sie waeren auch nie
    # entstanden — gruppiert wird nach Verdict, nicht nach Ticker.
    for ticker, verdict in (
        ("AAPL", "bestaetigt"), ("MSFT", "bestaetigt"), ("NVDA", "gedreht"),
    ):
        pid = db.save_prediction(in_memory_db, {
            "date": "2026-07-30", "run_type": "pre_market",
            "ticker": ticker, "direction": "long"})
        db.record_revision(in_memory_db, pid, verdict=verdict)
    rows = {r["revision_verdict"]: r["n"]
            for r in db.load_revision_verdict_stats(in_memory_db, "2026-07-01")}
    assert rows == {"bestaetigt": 2, "gedreht": 1}


def test_revision_verdict_stats_read_pl_from_the_successor(in_memory_db):
    """Block 2 muss das P&L der abloesenden Zeile lesen.

    Eine bestaetigte pre_market-Zeile ist status='superseded' und bekommt damit
    per Konstruktion NIE ein Outcome — das haengt an der Nachfolgezeile, und die
    traegt kein revision_verdict. Ein Join auf p.id allein liefert deshalb fuer
    'bestaetigt', 'geschwaecht' und 'unveraendert' strukturell 0,00 EUR, waehrend
    'gedreht' und 'verworfen' echte Zahlen zeigen (die bleiben ja offen). Die
    Weekly-Mail laese dann 'bestaetigt: 0 EUR / gedreht: -18 EUR' — als waere
    Bestaetigen wertlos."""
    db.init_schema(in_memory_db)

    old = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "long"})
    new = db.supersede_prediction(in_memory_db, old, {
        "date": "2026-07-30", "run_type": "trade_proposals",
        "ticker": "AAPL", "direction": "long"}, verdict="bestaetigt")
    db.save_outcome(in_memory_db, {
        "prediction_id": new, "direction": "long",
        "evaluated_date": "2026-07-31", "profit_loss_eur": 42.0})

    flipped = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "ticker": "MSFT", "direction": "long"})
    db.record_revision(in_memory_db, flipped, verdict="gedreht")
    db.save_outcome(in_memory_db, {
        "prediction_id": flipped, "direction": "long",
        "evaluated_date": "2026-07-31", "profit_loss_eur": -18.0})

    rows = {r["revision_verdict"]: r
            for r in db.load_revision_verdict_stats(in_memory_db, "2026-07-01")}
    assert rows["bestaetigt"]["avg_pl"] == 42.0
    assert rows["gedreht"]["avg_pl"] == -18.0


def test_revision_verdict_stats_tell_flat_from_unevaluated(in_memory_db):
    """Ein noch nicht ausgewertetes Urteil darf nicht wie 0,00 EUR aussehen.

    AVG(COALESCE(pl, 0)) macht aus 'noch kein Outcome' eine Null und damit ein
    Ergebnis, das von einem echten Nullergebnis nicht zu unterscheiden ist.
    n_evaluated sagt, worauf der Schnitt beruht."""
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "long"})
    db.record_revision(in_memory_db, pid, verdict="verworfen")

    rows = {r["revision_verdict"]: r
            for r in db.load_revision_verdict_stats(in_memory_db, "2026-07-01")}
    assert rows["verworfen"]["n"] == 1
    assert rows["verworfen"]["n_evaluated"] == 0
    assert rows["verworfen"]["avg_pl"] is None, "kein Outcome heisst kein Schnitt"


def test_guardrail_reject_stats_separate_the_two_runs(in_memory_db):
    """Block 3 muss nach run_type UND enforced trennen.

    enforced heisst 'dieser Check hat das Signal tatsaechlich verworfen' —
    so liest es auch signal_checks.blocks(). Es heisst NICHT 'aus welchem Lauf',
    und beide Laeufe schreiben beide Werte:

      * pre_market schreibt enforced=1, wenn der klassische GuardrailsChecker
        greift (ranking.py verwirft den Kandidaten dort wirklich),
      * trade_proposals schreibt enforced=0 fuer die immer weichen Checks
        (Klumpenrisiko, Opening-Gap, einseitiges Momentum).

    Ohne run_type in der Gruppierung liest man die harten Ablehnungen des
    Morgenlaufs als Ablehnungen des 16:10-Laufs."""
    db.init_schema(in_memory_db)
    for run_type, rule, enforced in [
        ("pre_market",      "rr_ratio",         1),   # klassischer Guardrail
        ("pre_market",      "sector_cluster",   0),   # weiche Warnung (E4)
        ("trade_proposals", "vix_no_new_longs", 1),   # harte Ablehnung
        ("trade_proposals", "sector_cluster",   0),   # weich, auch um 16:10
    ]:
        db.log_guardrail_reject(in_memory_db, {
            "date": "2026-07-30", "run_type": run_type, "ticker": "AAPL",
            "direction": "long", "rule": rule, "detail": "x",
            "enforced": enforced})

    rows = db.load_guardrail_reject_stats(in_memory_db, "2026-07-01")
    by_key = {(r["run_type"], r["rule"], r["enforced"]): r["n"] for r in rows}
    assert by_key[("pre_market", "rr_ratio", 1)] == 1
    assert by_key[("pre_market", "sector_cluster", 0)] == 1
    assert by_key[("trade_proposals", "vix_no_new_longs", 1)] == 1
    assert by_key[("trade_proposals", "sector_cluster", 0)] == 1


def test_skipped_ticker_stats_join_event_log_with_cumulative_status(in_memory_db):
    """B.9/Block 4. Im Plan ohne Test geblieben — die Funktion verbindet das
    Ereignis-Log (mehrere Zeilen je Ticker) mit dem kumulativen ticker_status,
    und genau dieser Join ist die Stelle, an der man sich vertun kann."""
    db.init_schema(in_memory_db)
    # Der Skip vom 15.06. liegt VOR since_date. Er zaehlt damit nicht ins Fenster,
    # erhoeht aber den kumulativen Zaehler — dadurch sind n_week (2) und
    # skip_total (3) verschieden und ein Vertauschen der beiden Spalten faellt auf.
    db.log_skipped_ticker(in_memory_db, "FAKE", "2026-06-15", "pre_market", "no data")
    db.log_skipped_ticker(in_memory_db, "FAKE", "2026-07-30", "pre_market", "no data")
    db.log_skipped_ticker(in_memory_db, "FAKE", "2026-07-31", "pre_market", "stale quote")
    db.log_skipped_ticker(in_memory_db, "MSFT", "2026-06-01", "pre_market", "alt")
    in_memory_db.commit()

    rows = {r["ticker"]: r for r in
            db.load_skipped_ticker_stats(in_memory_db, "2026-07-01")}
    assert "MSFT" not in rows, "vor since_date, darf nicht auftauchen"
    assert rows["FAKE"]["n_week"] == 2, "nur die Ereignisse im Fenster"
    assert rows["FAKE"]["skip_total"] == 3, "kumulativ aus ticker_status, fensterunabhaengig"
    assert "no data" in rows["FAKE"]["reasons"]
    assert "stale quote" in rows["FAKE"]["reasons"], "mehrere Gruende zusammengefasst"


def test_sector_mapping_coverage_counts_mapped_tickers(in_memory_db):
    """B.10 nennt die Abdeckung als Voraussetzung dafuer,
    SECTOR_GUARDRAIL_STRICT irgendwann auf True zu stellen."""
    import config
    db.init_schema(in_memory_db)
    sid = in_memory_db.execute(
        "SELECT id FROM sectors WHERE name='Retail'").fetchone()["id"]
    in_memory_db.execute(
        "INSERT INTO ticker_sectors (ticker, sector_id) VALUES ('AMZN', ?)", (sid,))
    in_memory_db.commit()
    out = db.load_sector_mapping_coverage(in_memory_db)
    assert out["mapped"] == 1
    assert out["total"] == len(config.SP500_MVP_TICKERS)
    assert 0.0 <= out["pct"] <= 100.0


def test_migration_adds_the_three_decision_snapshots(tmp_db_path):
    """Additiv und idempotent -- muss auch gegen eine bestehende tracking.db
    laufen. entry_price bleibt unangetastet."""
    conn = db.connect(str(tmp_db_path))
    db.init_schema(conn)
    db.init_schema(conn)  # zweimal: idempotent
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(predictions)").fetchall()}
    assert {"price_premarket", "price_open", "price_1610",
            "is_premarket"}.issubset(cols)
    assert "entry_price" in cols, "die bestehende Spalte bleibt"
    conn.close()


def test_save_prediction_persists_the_snapshots(in_memory_db):
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-08-06", "run_type": "trade_proposals",
        "ticker": "AAPL", "direction": "long", "entry_price": 310.0,
        "price_premarket": 308.5, "price_open": 309.09, "price_1610": 310.0,
        "is_premarket": 0,
    })
    row = in_memory_db.execute(
        "SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row["price_premarket"] == 308.5
    assert row["price_open"] == 309.09
    assert row["price_1610"] == 310.0
    assert row["is_premarket"] == 0


# ---------- skip_reason_counts (D1): Gruende buendeln ----------

def test_skip_reason_counts_groups_by_reason_kind(in_memory_db):
    """Die Gruende tragen variable Zahlen ("insufficient bars: 19 < 20").
    Ungruppiert waere jede Zeile ein eigener Eintrag und die Verteilung
    unlesbar — gerade im Fall, den das Ganze sichtbar machen soll."""
    from src.db import skip_reason_counts
    init_schema(in_memory_db)
    for t, n in (("AAA", 19), ("BBB", 17), ("CCC", 3)):
        log_skipped_ticker(
            in_memory_db, ticker=t, date="2026-08-04", run_type="pre_market",
            reason=f"insufficient bars: {n} < 20", learnable=False)
    log_skipped_ticker(
        in_memory_db, ticker="DDD", date="2026-08-04", run_type="pre_market",
        reason="data_quality=low: critical indicators missing", learnable=False)

    counts = dict(skip_reason_counts(in_memory_db, date="2026-08-04",
                                     run_type="pre_market"))
    assert counts == {"insufficient bars": 3, "data_quality=low": 1}


def test_skip_reason_counts_is_scoped_to_the_run(in_memory_db):
    """Sonst zaehlt die Zusammenfassung eines Laufs die Skips aller Vortage mit."""
    from src.db import skip_reason_counts
    init_schema(in_memory_db)
    log_skipped_ticker(
        in_memory_db, ticker="OLD", date="2026-07-13", run_type="pre_market",
        reason="insufficient bars: 5 < 20", learnable=False)
    log_skipped_ticker(
        in_memory_db, ticker="NEW", date="2026-08-04", run_type="pre_market",
        reason="insufficient bars: 19 < 20", learnable=False)

    counts = dict(skip_reason_counts(in_memory_db, date="2026-08-04",
                                     run_type="pre_market"))
    assert counts == {"insufficient bars": 1}


def test_skip_reason_counts_orders_by_frequency(in_memory_db):
    """Der haeufigste Grund steht vorn — er ist der, der den Lauf erklaert."""
    from src.db import skip_reason_counts
    init_schema(in_memory_db)
    log_skipped_ticker(
        in_memory_db, ticker="ONE", date="2026-08-04", run_type="close",
        reason="data_quality=low: whatever", learnable=False)
    for t in ("AAA", "BBB"):
        log_skipped_ticker(
            in_memory_db, ticker=t, date="2026-08-04", run_type="close",
            reason="insufficient bars: 19 < 20", learnable=False)

    counts = skip_reason_counts(in_memory_db, date="2026-08-04", run_type="close")
    assert counts[0][0] == "insufficient bars"


def test_sma200_computable_with_default_load_window(tmp_path):
    """Das Standard-Ladefenster muss SMA200 tragen, sonst faellt der
    SMA-Teilindikator des Technik-Signals dauerhaft aus."""
    from datetime import date, timedelta
    from src.db import connect, load_price_history_from_db, insert_price_bar_if_missing
    from src.indicators import compute_sma_distance_pct

    conn = connect(str(tmp_path / "t.db"))
    init_schema(conn)
    base = date(2025, 1, 1)
    for i in range(230):
        d = (base + timedelta(days=i)).isoformat()
        insert_price_bar_if_missing(
            conn, ticker="AAPL", date=d, open_=100.0, high=101.0,
            low=99.0, close=100.0 + i * 0.1, volume=1_000, source="test",
        )
    conn.commit()

    df = load_price_history_from_db(conn, "AAPL", as_of_date="2025-12-31")
    # Reserve ueber SMA200 hinaus: bei exakt 200 haengt der Wert
    # an einer einzigen fehlenden Bar.
    assert len(df) >= 220
    assert compute_sma_distance_pct(df, 200) is not None
