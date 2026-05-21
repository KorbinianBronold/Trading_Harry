import sqlite3
from pathlib import Path
from typing import Any

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS price_history (
    ticker TEXT NOT NULL, date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL NOT NULL, volume INTEGER,
    source TEXT DEFAULT 'yfinance',
    UNIQUE(ticker, date)
);

CREATE TABLE IF NOT EXISTS technical_indicators (
    ticker TEXT NOT NULL, date TEXT NOT NULL,
    rsi_14 REAL, macd_signal TEXT, atr_pct REAL,
    bb_position REAL, above_sma20 REAL, above_sma50 REAL, above_sma200 REAL,
    volume_ratio REAL, intraday_range_pct REAL,
    UNIQUE(ticker, date)
);

CREATE TABLE IF NOT EXISTS fundamentals (
    ticker TEXT NOT NULL, report_date TEXT NOT NULL,
    eps_actual REAL, eps_estimated REAL, eps_beat_pct REAL,
    revenue_actual REAL, guidance_raised BOOLEAN,
    pe_ratio REAL, forward_pe REAL, debt_equity REAL,
    UNIQUE(ticker, report_date)
);

CREATE TABLE IF NOT EXISTS news_summaries (
    ticker TEXT, date TEXT NOT NULL, run_type TEXT,
    summary TEXT NOT NULL, sentiment TEXT, source TEXT, market_impact TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trend_analyses (
    date TEXT NOT NULL, run_type TEXT, trend_name TEXT NOT NULL,
    strength INTEGER, duration_estimate TEXT, summary TEXT,
    beneficiary_tickers TEXT, negative_tickers TEXT, next_catalyst TEXT,
    UNIQUE(date, trend_name)
);

CREATE TABLE IF NOT EXISTS market_context (
    date TEXT NOT NULL, run_type TEXT NOT NULL,
    sp500_change_pct REAL, vix_level REAL, market_regime TEXT,
    oil_price REAL, gold_price REAL, btc_price REAL,
    fear_greed_value INTEGER, policy_risk_level TEXT,
    sector_rotation_in TEXT, sector_rotation_out TEXT, macro_summary TEXT,
    UNIQUE(date, run_type)
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL, run_type TEXT NOT NULL, asset_class TEXT,
    ticker TEXT NOT NULL, direction TEXT NOT NULL,
    entry_price REAL, tp_price REAL, tp_pct REAL,
    sl_price REAL, sl_pct REAL, rr_ratio REAL,
    total_score REAL, probability_pct INTEGER, confidence TEXT,
    score_market_env REAL, score_company REAL, score_valuation REAL,
    score_momentum REAL, score_risk REAL, score_sector REAL,
    score_catalyst REAL, score_policy REAL,
    atr_pct REAL, rsi_at_entry REAL, volume_ratio REAL,
    market_regime TEXT, vix_at_prediction REAL, sector TEXT,
    trend_boost TEXT, earnings_warning BOOLEAN, summary TEXT,
    learnable BOOLEAN DEFAULT 1,
    status TEXT DEFAULT 'open',
    closed_date TEXT, closed_price REAL,
    hold_days_recommended INTEGER, intraday_range_pct REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id INTEGER REFERENCES predictions(id),
    direction TEXT, evaluated_date TEXT NOT NULL,
    price_after_eod REAL, price_change_eod_pct REAL,
    correct_direction_eod BOOLEAN,
    tp_hit BOOLEAN, sl_hit BOOLEAN,
    days_to_close INTEGER, exit_reason TEXT,
    profit_loss_eur REAL,
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS skipped_tickers (
    ticker TEXT NOT NULL, date TEXT NOT NULL, run_type TEXT,
    reason TEXT, learnable BOOLEAN DEFAULT 0,
    skip_count INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_name TEXT NOT NULL, version INTEGER NOT NULL,
    content TEXT NOT NULL, created_date TEXT,
    long_accuracy REAL, short_accuracy REAL, total_predictions INTEGER,
    is_active BOOLEAN DEFAULT 1, replaced_date TEXT,
    UNIQUE(prompt_name, version)
);

CREATE TABLE IF NOT EXISTS cost_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL, run_type TEXT NOT NULL,
    total_eur REAL, claude_eur REAL, web_search_eur REAL,
    input_tokens INTEGER, output_tokens INTEGER,
    cache_read_tokens INTEGER, cache_hit_rate REAL,
    web_search_calls INTEGER, aborted_at_phase TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_predictions_status ON predictions(status);
CREATE INDEX IF NOT EXISTS idx_predictions_date ON predictions(date);
CREATE INDEX IF NOT EXISTS idx_price_history_ticker_date ON price_history(ticker, date);

CREATE TABLE IF NOT EXISTS position_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL, run_type TEXT NOT NULL,
    prediction_id INTEGER NOT NULL REFERENCES predictions(id),
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    new_sl_price REAL, new_tp_price REAL,
    market_context_changed BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, run_type, prediction_id)
);

CREATE INDEX IF NOT EXISTS idx_position_recs_prediction ON position_recommendations(prediction_id);

CREATE TABLE IF NOT EXISTS fundamentals_cache (
    ticker TEXT NOT NULL,
    fetched_date TEXT NOT NULL,
    pe_ratio REAL,
    forward_pe REAL,
    market_cap_b REAL,
    debt_equity REAL,
    sector TEXT,
    analyst_upside REAL,
    consensus TEXT,
    UNIQUE(ticker)
);
"""


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Idempotent column-add migrations for pre-existing DBs.
    SQLite does not support IF NOT EXISTS on ALTER TABLE, so we inspect first."""
    ti_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(technical_indicators)"
    ).fetchall()}
    if "intraday_range_pct" not in ti_cols:
        conn.execute(
            "ALTER TABLE technical_indicators ADD COLUMN intraday_range_pct REAL"
        )

    pred_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(predictions)"
    ).fetchall()}
    if "hold_days_recommended" not in pred_cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN hold_days_recommended INTEGER")
    if "intraday_range_pct" not in pred_cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN intraday_range_pct REAL")

    out_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(outcomes)"
    ).fetchall()}
    if "days_to_close" not in out_cols:
        conn.execute("ALTER TABLE outcomes ADD COLUMN days_to_close INTEGER")
    if "exit_reason" not in out_cols:
        conn.execute("ALTER TABLE outcomes ADD COLUMN exit_reason TEXT")

    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "fundamentals_cache" not in tables:
        conn.execute("""
            CREATE TABLE fundamentals_cache (
                ticker TEXT NOT NULL,
                fetched_date TEXT NOT NULL,
                pe_ratio REAL, forward_pe REAL, market_cap_b REAL,
                debt_equity REAL, sector TEXT,
                analyst_upside REAL, consensus TEXT,
                UNIQUE(ticker)
            )
        """)

    ph_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(price_history)"
    ).fetchall()}
    if "premarket_price" not in ph_cols:
        conn.execute("ALTER TABLE price_history ADD COLUMN premarket_price REAL")
    conn.commit()


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    _apply_migrations(conn)


def get_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def upsert_price_history(
    conn: sqlite3.Connection, ticker: str, date: str,
    open_: float, high: float, low: float, close: float, volume: int,
    source: str = "yfinance",
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO price_history
           (ticker, date, open, high, low, close, volume, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticker, date, open_, high, low, close, volume, source),
    )


def save_prediction(conn: sqlite3.Connection, pred: dict) -> int:
    cols = [
        "date", "run_type", "asset_class", "ticker", "direction",
        "entry_price", "tp_price", "tp_pct", "sl_price", "sl_pct", "rr_ratio",
        "total_score", "probability_pct", "confidence",
        "score_market_env", "score_company", "score_valuation",
        "score_momentum", "score_risk", "score_sector",
        "score_catalyst", "score_policy",
        "atr_pct", "rsi_at_entry", "volume_ratio",
        "market_regime", "vix_at_prediction", "sector",
        "trend_boost", "earnings_warning", "summary", "learnable",
        "hold_days_recommended", "intraday_range_pct",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    values = [pred.get(c) for c in cols]
    cur = conn.execute(
        f"INSERT INTO predictions ({', '.join(cols)}) VALUES ({placeholders})",
        values,
    )
    conn.commit()
    return cur.lastrowid


def load_open_predictions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM predictions WHERE status = 'open' AND learnable = 1"
    ).fetchall()


def close_prediction(
    conn: sqlite3.Connection, pred_id: int, status: str,
    closed_date: str, closed_price: float | None,
) -> None:
    conn.execute(
        "UPDATE predictions SET status=?, closed_date=?, closed_price=? WHERE id=?",
        (status, closed_date, closed_price, pred_id),
    )
    conn.commit()


def save_outcome(conn: sqlite3.Connection, outcome: dict) -> int:
    cols = [
        "prediction_id", "direction", "evaluated_date",
        "price_after_eod", "price_change_eod_pct", "correct_direction_eod",
        "tp_hit", "sl_hit", "days_to_close", "exit_reason", "profit_loss_eur",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    values = [outcome.get(c) for c in cols]
    cur = conn.execute(
        f"INSERT INTO outcomes ({', '.join(cols)}) VALUES ({placeholders})",
        values,
    )
    conn.commit()
    return cur.lastrowid


def save_cost_tracking(conn: sqlite3.Connection, row: dict) -> None:
    cols = [
        "date", "run_type", "total_eur", "claude_eur", "web_search_eur",
        "input_tokens", "output_tokens", "cache_read_tokens", "cache_hit_rate",
        "web_search_calls", "aborted_at_phase",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    values = [row.get(c) for c in cols]
    conn.execute(
        f"INSERT INTO cost_tracking ({', '.join(cols)}) VALUES ({placeholders})",
        values,
    )
    conn.commit()


def cleanup_old_data(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DELETE FROM news_summaries WHERE date < date('now', '-90 days');
        DELETE FROM trend_analyses WHERE date < date('now', '-180 days');
        DELETE FROM skipped_tickers WHERE date < date('now', '-30 days');
        """
    )
    conn.commit()


def upsert_technical_indicators(conn: sqlite3.Connection, row: dict) -> None:
    cols = [
        "ticker", "date", "rsi_14", "macd_signal", "atr_pct",
        "bb_position", "above_sma20", "above_sma50", "above_sma200",
        "volume_ratio", "intraday_range_pct",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    values = [row.get(c) for c in cols]
    conn.execute(
        f"INSERT OR REPLACE INTO technical_indicators ({', '.join(cols)}) "
        f"VALUES ({placeholders})",
        values,
    )
    conn.commit()


def save_trend_analysis(conn: sqlite3.Connection, trend: dict) -> None:
    """Insert or replace one trend row. Lists serialised as comma-joined strings."""
    beneficiaries = ",".join(trend.get("beneficiary_tickers") or [])
    negatives = ",".join(trend.get("negative_tickers") or [])
    conn.execute(
        """INSERT OR REPLACE INTO trend_analyses
           (date, run_type, trend_name, strength, duration_estimate, summary,
            beneficiary_tickers, negative_tickers, next_catalyst)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            trend["date"], trend["run_type"], trend["trend_name"],
            trend.get("strength"), trend.get("duration_estimate"),
            trend.get("summary"), beneficiaries, negatives,
            trend.get("next_catalyst"),
        ),
    )
    conn.commit()


def log_skipped_ticker(
    conn: sqlite3.Connection,
    ticker: str, date: str, run_type: str,
    reason: str, learnable: bool = False,
) -> None:
    conn.execute(
        """INSERT INTO skipped_tickers
           (ticker, date, run_type, reason, learnable)
           VALUES (?, ?, ?, ?, ?)""",
        (ticker, date, run_type, reason, 1 if learnable else 0),
    )
    conn.commit()


def save_position_recommendation(conn: sqlite3.Connection, row: dict) -> int:
    cols = [
        "date", "run_type", "prediction_id", "action", "reason",
        "new_sl_price", "new_tp_price", "market_context_changed",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    values = [row.get(c) for c in cols]
    cur = conn.execute(
        f"INSERT OR REPLACE INTO position_recommendations ({', '.join(cols)}) "
        f"VALUES ({placeholders})",
        values,
    )
    conn.commit()
    return cur.lastrowid


def load_open_predictions_within_max_age_days(
    conn: sqlite3.Connection, today: str, max_trading_days: int = 3,
) -> list[sqlite3.Row]:
    """Returns open, learnable predictions whose calendar age <= max_trading_days
    days from `today`. We use a calendar approximation (sqlite julianday); the
    walk-forward evaluator handles trading-day precision separately."""
    return conn.execute(
        """SELECT * FROM predictions
           WHERE status='open' AND learnable=1
             AND julianday(?) - julianday(date) <= ?
           ORDER BY date DESC""",
        (today, max_trading_days),
    ).fetchall()


def update_outcome_close(
    conn: sqlite3.Connection,
    prediction_id: int, exit_reason: str,
    exit_price: float | None, days_to_close: int,
    closed_date: str, profit_loss_eur: float | None,
    correct_direction_eod: bool | None,
    direction: str,
) -> None:
    """Single transactional helper used by evaluator: writes outcomes row
    AND updates the prediction.status / closed_date / closed_price atomically."""
    status_map = {
        "tp_hit": "closed_tp", "sl_hit": "closed_sl",
        "timeout": "closed_timeout", "pessimistic_overlap": "closed_sl",
        "data_missing": "closed_data_missing",
    }
    status = status_map.get(exit_reason, "closed_timeout")
    with conn:
        conn.execute(
            "UPDATE predictions SET status=?, closed_date=?, closed_price=? WHERE id=?",
            (status, closed_date, exit_price, prediction_id),
        )
        conn.execute(
            """INSERT INTO outcomes
               (prediction_id, direction, evaluated_date,
                price_after_eod, price_change_eod_pct, correct_direction_eod,
                tp_hit, sl_hit, days_to_close, exit_reason, profit_loss_eur)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                prediction_id, direction, closed_date,
                exit_price, None, correct_direction_eod,
                exit_reason == "tp_hit",
                exit_reason in ("sl_hit", "pessimistic_overlap"),
                days_to_close, exit_reason, profit_loss_eur,
            ),
        )


def load_predictions_for_date(
    conn: sqlite3.Connection, date: str, run_type: str,
) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT * FROM predictions
           WHERE date=? AND run_type=?
           ORDER BY total_score DESC""",
        (date, run_type),
    ).fetchall()


def load_position_recommendations_for_date(
    conn: sqlite3.Connection, date: str, run_type: str,
) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT pr.*, p.ticker, p.direction, p.entry_price,
                  p.tp_price, p.sl_price
           FROM position_recommendations pr
           JOIN predictions p ON p.id = pr.prediction_id
           WHERE pr.date=? AND pr.run_type=?
           ORDER BY pr.created_at ASC""",
        (date, run_type),
    ).fetchall()


def load_recent_outcomes(
    conn: sqlite3.Connection, since_date: str,
) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT o.*, p.ticker, p.direction AS pred_direction,
                  p.total_score, p.entry_price
           FROM outcomes o
           JOIN predictions p ON p.id = o.prediction_id
           WHERE o.evaluated_date >= ?
           ORDER BY o.evaluated_date DESC""",
        (since_date,),
    ).fetchall()


_FUNDAMENTALS_TTL_DAYS = 7


def get_cached_fundamentals(
    conn: sqlite3.Connection,
    ticker: str,
    today: str | None = None,
) -> dict | None:
    from datetime import date as _d, timedelta
    _today = today or _d.today().isoformat()
    cutoff = (_d.fromisoformat(_today) - timedelta(days=_FUNDAMENTALS_TTL_DAYS)).isoformat()
    row = conn.execute(
        "SELECT * FROM fundamentals_cache WHERE ticker=? AND fetched_date >= ?",
        (ticker, cutoff),
    ).fetchone()
    return dict(row) if row else None


def save_fundamentals_cache(
    conn: sqlite3.Connection,
    ticker: str,
    data: dict,
    fetched_date: str | None = None,
) -> None:
    from datetime import date as _d
    _fetched = fetched_date or _d.today().isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO fundamentals_cache
           (ticker, fetched_date, pe_ratio, forward_pe, market_cap_b,
            debt_equity, sector, analyst_upside, consensus)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ticker, _fetched,
            data.get("pe_ratio"), data.get("forward_pe"), data.get("market_cap_b"),
            data.get("debt_equity"), data.get("sector"),
            data.get("analyst_upside"), data.get("consensus"),
        ),
    )
    conn.commit()


def insert_price_bar_if_missing(
    conn: sqlite3.Connection,
    ticker: str, date: str,
    open_: float, high: float, low: float, close: float,
    volume: int, source: str = "capital.com",
) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO price_history
           (ticker, date, open, high, low, close, volume, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticker, date, open_, high, low, close, volume, source),
    )


def load_price_history_from_db(
    conn: sqlite3.Connection,
    ticker: str,
    as_of_date: str,
    limit: int = 200,
) -> "pd.DataFrame | None":
    import pandas as pd
    rows = conn.execute(
        """SELECT date, open, high, low, close, volume
           FROM price_history
           WHERE ticker=? AND date <= ?
           ORDER BY date DESC LIMIT ?""",
        (ticker, as_of_date, limit),
    ).fetchall()
    if not rows:
        return None
    df = pd.DataFrame([dict(r) for r in rows])
    df = df.rename(columns={
        "date": "Date", "open": "Open", "high": "High",
        "low": "Low", "close": "Close", "volume": "Volume",
    })
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date").sort_index()
