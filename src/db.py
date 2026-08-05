"""SQLite schema definition, migrations, and every DB read/write helper used by
the pipeline. All SQL lives here — phase modules never write raw SQL themselves."""
import logging
import sqlite3
from datetime import date as _date_cls, timedelta
from pathlib import Path
from typing import Any

import config

log = logging.getLogger("shares_future.db")

# Case-insensitiver Lookup über config.SECTOR_ALIASES. Einmal beim Import gebaut,
# damit resolve_sector_id() nicht bei jedem Ticker neu normalisieren muss.
_SECTOR_ALIAS_LOOKUP: dict[str, str] = {
    raw.strip().casefold(): sub for raw, sub in config.SECTOR_ALIASES.items()
}

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
    advance_decline_ratio REAL,
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
    superseded_by INTEGER REFERENCES predictions(id),
    revision_verdict TEXT,
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

CREATE TABLE IF NOT EXISTS sectors (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    etf  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ticker_sectors (
    ticker     TEXT PRIMARY KEY,
    sector_id  INTEGER REFERENCES sectors(id),
    source     TEXT DEFAULT 'finnhub',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ticker_status (
    ticker          TEXT PRIMARY KEY,
    skip_count      INTEGER NOT NULL DEFAULT 0,
    inactive        INTEGER NOT NULL DEFAULT 0,
    first_skip_date TEXT,
    last_skip_date  TEXT,
    retry_after     TEXT
);

CREATE TABLE IF NOT EXISTS guardrail_rejects (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    date                 TEXT NOT NULL,
    run_type             TEXT NOT NULL,
    ticker               TEXT NOT NULL,
    direction            TEXT,
    rule                 TEXT NOT NULL,
    detail               TEXT,
    enforced             INTEGER NOT NULL DEFAULT 1,
    sector_etf_momentum  REAL,   -- D9: Momentum-Snapshot zum Reject-Zeitpunkt
    sector_db_momentum   REAL,   -- D9: dito, DB-basiert
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_guardrail_rejects_date ON guardrail_rejects(date);

CREATE TABLE IF NOT EXISTS sector_momentum (
    date         TEXT NOT NULL,
    run_type     TEXT NOT NULL,
    sector_id    INTEGER NOT NULL REFERENCES sectors(id),
    etf_momentum REAL,      -- NULL wenn kein ETF verfuegbar
    db_momentum  REAL,      -- NULL wenn < SECTOR_DB_MOMENTUM_MIN_TICKERS Ticker
    ticker_count INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, run_type, sector_id)
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
    # D9: der Momentum-Snapshot haengt an der Prediction, weil nur sie ueber
    # outcomes mit echten Trade-Ergebnissen verknuepft ist.
    if "sector_etf_momentum" not in pred_cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN sector_etf_momentum REAL")
    if "sector_db_momentum" not in pred_cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN sector_db_momentum REAL")
    # E3 (Plan 2): der 16:10-Lauf loest die pre_market-Zeile ab, statt eine
    # zweite offene Zeile daneben zu legen. Ohne das schliesst der Evaluator
    # beide und jede Kennzahl zaehlt doppelt.
    if "superseded_by" not in pred_cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN superseded_by INTEGER")
    if "revision_verdict" not in pred_cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN revision_verdict TEXT")

    # guardrail_rejects existiert erst seit Task 8 — bei aelteren DBs legt der
    # SCHEMA_SQL-Lauf davor die Tabelle bereits mit beiden Spalten an.
    gr_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(guardrail_rejects)"
    ).fetchall()}
    if gr_cols and "sector_etf_momentum" not in gr_cols:
        conn.execute("ALTER TABLE guardrail_rejects ADD COLUMN sector_etf_momentum REAL")
    if gr_cols and "sector_db_momentum" not in gr_cols:
        conn.execute("ALTER TABLE guardrail_rejects ADD COLUMN sector_db_momentum REAL")

    mc_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(market_context)"
    ).fetchall()}
    if "advance_decline_ratio" not in mc_cols:
        conn.execute("ALTER TABLE market_context ADD COLUMN advance_decline_ratio REAL")

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
    """Opens a SQLite connection with row_factory=sqlite3.Row and foreign keys enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Creates every table/index if missing, seeds reference data, and applies
    pending migrations. Safe to call on every run — idempotent."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    _apply_migrations(conn)
    _seed_sectors(conn)


def _seed_sectors(conn: sqlite3.Connection) -> None:
    """Befüllt die sectors-Tabelle mit den Sub-Sektoren aus config.SUB_SECTOR_ETFS.
    Idempotent über ON CONFLICT auf name UNIQUE; ein geänderter ETF wird nachgezogen."""
    for name, etf in config.SUB_SECTOR_ETFS.items():
        conn.execute(
            "INSERT INTO sectors (name, etf) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET etf = excluded.etf",
            (name, etf),
        )
    conn.commit()


def resolve_sector_id(conn: sqlite3.Connection, raw_sector: str | None) -> int | None:
    """Normalisiert einen Finnhub-Sektorwert über config.SECTOR_ALIASES auf einen
    Sub-Sektornamen und gibt dessen sectors.id zurück. Nicht auflösbare Werte ergeben
    None und werden mit WARN geloggt, damit die Alias-Liste iterativ wachsen kann."""
    if not raw_sector:
        return None
    sub_sector = _SECTOR_ALIAS_LOOKUP.get(raw_sector.strip().casefold())
    if sub_sector is None:
        log.warning(f"unknown sector value from provider: {raw_sector!r}")
        return None
    row = conn.execute("SELECT id FROM sectors WHERE name = ?", (sub_sector,)).fetchone()
    return int(row["id"]) if row else None


def upsert_ticker_sector(
    conn: sqlite3.Connection, ticker: str, sector_id: int, source: str = "finnhub",
) -> None:
    """Schreibt oder aktualisiert die Sub-Sektor-Zuordnung eines Tickers."""
    conn.execute(
        """INSERT INTO ticker_sectors (ticker, sector_id, source, updated_at)
           VALUES (?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(ticker) DO UPDATE SET
               sector_id  = excluded.sector_id,
               source     = excluded.source,
               updated_at = CURRENT_TIMESTAMP""",
        (ticker, sector_id, source),
    )
    conn.commit()


def get_ticker_sector(conn: sqlite3.Connection, ticker: str) -> sqlite3.Row | None:
    """Gibt sector_id, Sub-Sektorname und Sektor-ETF für `ticker` zurück (JOIN über
    ticker_sectors -> sectors), oder None wenn kein Mapping existiert."""
    return conn.execute(
        """SELECT ts.sector_id AS sector_id, s.name AS name, s.etf AS etf
           FROM ticker_sectors ts JOIN sectors s ON s.id = ts.sector_id
           WHERE ts.ticker = ?""",
        (ticker,),
    ).fetchone()


def compute_sector_db_momentum(
    conn: sqlite3.Connection,
    date: str,
    min_tickers: int = config.SECTOR_DB_MOMENTUM_MIN_TICKERS,
) -> dict[int, dict]:
    """Berechnet je Sub-Sektor die durchschnittliche Tagesperformance aller
    zugeordneten Ticker aus price_history — reines SQL, keine API-Calls, 0 EUR.

    Gibt {sector_id: {"momentum": float | None, "ticker_count": int}} zurueck.
    `momentum` ist None, wenn weniger als `min_tickers` Ticker des Sub-Sektors
    einen Vortagesbar haben; der Durchschnitt waere dann statistisch wertlos.
    Ticker ohne Vortagesbar zaehlen nicht mit."""
    rows = conn.execute(
        """SELECT ts.sector_id AS sector_id,
                  AVG((cur.close - prev.close) / prev.close * 100.0) AS momentum,
                  COUNT(*) AS n
           FROM ticker_sectors ts
           JOIN price_history cur
             ON cur.ticker = ts.ticker AND cur.date = ?
           JOIN price_history prev
             ON prev.ticker = ts.ticker
            AND prev.date = (SELECT MAX(p.date) FROM price_history p
                             WHERE p.ticker = ts.ticker AND p.date < ?)
           WHERE prev.close > 0
           GROUP BY ts.sector_id""",
        (date, date),
    ).fetchall()
    out: dict[int, dict] = {}
    for r in rows:
        n = int(r["n"])
        out[int(r["sector_id"])] = {
            "momentum": float(r["momentum"]) if n >= min_tickers else None,
            "ticker_count": n,
        }
    return out


def save_sector_momentum(conn: sqlite3.Connection, row: dict) -> None:
    """Schreibt oder ueberschreibt die beiden Momentum-Signale eines Sub-Sektors
    fuer einen Run (UNIQUE date + run_type + sector_id)."""
    cols = ["date", "run_type", "sector_id", "etf_momentum",
            "db_momentum", "ticker_count"]
    placeholders = ", ".join(["?"] * len(cols))
    conn.execute(
        f"INSERT OR REPLACE INTO sector_momentum ({', '.join(cols)}) "
        f"VALUES ({placeholders})",
        [row.get(c) for c in cols],
    )
    conn.commit()


def load_sector_momentum(
    conn: sqlite3.Connection, date: str, run_type: str,
) -> dict[int, sqlite3.Row]:
    """Gibt die gespeicherten Momentum-Zeilen eines Runs als {sector_id: Row}
    zurueck."""
    rows = conn.execute(
        "SELECT * FROM sector_momentum WHERE date = ? AND run_type = ?",
        (date, run_type),
    ).fetchall()
    return {int(r["sector_id"]): r for r in rows}


def get_tables(conn: sqlite3.Connection) -> list[str]:
    """Returns the names of all tables currently in the database."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def upsert_price_history(
    conn: sqlite3.Connection, ticker: str, date: str,
    open_: float, high: float, low: float, close: float, volume: int,
    source: str = "capital.com",
) -> None:
    """Inserts or overwrites one price_history row for `ticker`/`date`.

    Gegenstueck zu insert_price_bar_if_missing: gedacht fuer den Bar des noch
    laufenden Tages, der sich bis zum Schluss weiter bewegt."""
    conn.execute(
        """INSERT OR REPLACE INTO price_history
           (ticker, date, open, high, low, close, volume, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticker, date, open_, high, low, close, volume, source),
    )


def _insert_prediction(conn: sqlite3.Connection, pred: dict) -> int:
    """Inserts one predictions row from a flat dict and returns its new id.

    Committet bewusst NICHT — so kann supersede_prediction() den INSERT mit dem
    UPDATE der abgeloesten Zeile in eine Transaktion legen.

    `learnable` faellt auf True zurueck, wenn der Aufrufer den Schluessel
    weglaesst: die INSERT-Spaltenliste listet ihn immer explizit auf, ein
    fehlender Wert wuerde sonst NULL statt des Schema-Defaults (DEFAULT 1)
    schreiben — und NULL erfuellt keinen der `learnable = 1`-Filter."""
    pred = {"learnable": True, **pred}
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
        # D9 (Plan 2 / Task 10): standen seit Plan 1 im Schema, aber nicht in
        # dieser Liste — deshalb blieben sie bis hierher immer NULL.
        "sector_etf_momentum", "sector_db_momentum",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    values = [pred.get(c) for c in cols]
    cur = conn.execute(
        f"INSERT INTO predictions ({', '.join(cols)}) VALUES ({placeholders})",
        values,
    )
    return cur.lastrowid


def save_prediction(conn: sqlite3.Connection, pred: dict) -> int:
    """Inserts one predictions row and commits. Siehe _insert_prediction."""
    new_id = _insert_prediction(conn, pred)
    conn.commit()
    return new_id


def supersede_prediction(
    conn: sqlite3.Connection, old_id: int, new_pred: dict, verdict: str,
) -> int:
    """Legt die trade_proposals-Nachfolgezeile an und loest die pre_market-Zeile
    im SELBEN Commit ab (E3). Gibt die ID der neuen Zeile zurueck.

    Warum eine Transaktion und nicht zwei Aufrufe: zwischen einem committeten
    INSERT und einem noch offenen UPDATE stuenden zwei offene, lernbare Zeilen
    fuer dieselbe (date, ticker, direction) in der DB. Bricht der Lauf genau dort
    ab — Lock, abgebrochener Actions-Job, Runner-Timeout —, ist dieser Zustand
    dauerhaft: es gibt weder ein UNIQUE ueber die drei Spalten (Befund 8) noch
    einen Reparaturlauf. Der Evaluator schliesst dann beide Zeilen und jede
    Kennzahl zaehlt doppelt. Genau das soll E3 verhindern."""
    try:
        new_id = _insert_prediction(conn, new_pred)
        conn.execute(
            """UPDATE predictions
               SET revision_verdict = ?, superseded_by = ?, status = 'superseded'
               WHERE id = ?""",
            (verdict, new_id, old_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return new_id


def load_open_predictions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Returns every prediction still open and eligible for learning."""
    return conn.execute(
        "SELECT * FROM predictions WHERE status = 'open' AND learnable = 1"
    ).fetchall()


def close_prediction(
    conn: sqlite3.Connection, pred_id: int, status: str,
    closed_date: str, closed_price: float | None,
) -> None:
    """Marks one prediction as closed with its final status, date, and price."""
    conn.execute(
        "UPDATE predictions SET status=?, closed_date=?, closed_price=? WHERE id=?",
        (status, closed_date, closed_price, pred_id),
    )
    conn.commit()


def record_revision(
    conn: sqlite3.Connection, pred_id: int, verdict: str,
    superseded_by: int | None = None,
) -> None:
    """Schreibt das Urteil des 16:10-Laufs auf die pre_market-Zeile (E3).

    Mit `superseded_by` wird die Zeile abgeloest: status='superseded', damit der
    Evaluator und Phase 4a sie nicht mehr sehen — beide filtern auf status='open'.
    Ohne `superseded_by` (Urteil 'gedreht' oder 'verworfen') bleibt sie offen und
    wird regulaer ausgewertet; nur so laesst sich messen, ob die Ablehnung richtig lag.

    Das Urteil sitzt bewusst auf der ALTEN Zeile: in drei von sechs Ausgaengen
    entsteht gar keine neue, dort waere es sonst nirgends."""
    if superseded_by is None:
        conn.execute(
            "UPDATE predictions SET revision_verdict = ? WHERE id = ?",
            (verdict, pred_id),
        )
    else:
        conn.execute(
            """UPDATE predictions
               SET revision_verdict = ?, superseded_by = ?, status = 'superseded'
               WHERE id = ?""",
            (verdict, superseded_by, pred_id),
        )
    conn.commit()


def save_outcome(conn: sqlite3.Connection, outcome: dict) -> int:
    """Inserts one outcomes row from a flat dict and returns its new id."""
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
    """Inserts one cost_tracking row from a CostTracker.summary() dict."""
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
    """Loescht abgelaufene Zeilen: news_summaries > 30 Tage, trend_analyses
    > 180 Tage, skipped_tickers-Events > 90 Tage (Sprint 3B / B.7, D4).

    Die Skip-Events halten laenger als frueher, weil die Weekly-Mail auswerten
    soll, welcher Ticker wie oft und warum uebersprungen wurde. News altern
    dagegen schneller aus — aeltere Zusammenfassungen sind wertlos.

    ticker_status wird bewusst NIE angefasst: der kumulative Skip-Zaehler und das
    inactive-Flag muessen die Event-Retention ueberleben. Zurueckgesetzt wird nur
    ueber reactivate_ticker() oder das automatische retry_after-Datum."""
    conn.executescript(
        """
        DELETE FROM news_summaries WHERE date < date('now', '-30 days');
        DELETE FROM trend_analyses WHERE date < date('now', '-180 days');
        DELETE FROM skipped_tickers WHERE date < date('now', '-90 days');
        """
    )
    conn.commit()


def upsert_technical_indicators(conn: sqlite3.Connection, row: dict) -> None:
    """Inserts or overwrites one technical_indicators row for a ticker/date."""
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


def load_trend_context(conn: sqlite3.Connection, date: str) -> dict:
    """Liest die am Morgen gespeicherten `trend_analyses`-Zeilen fuer `date` und
    baut daraus dieselbe Struktur, die analyze_trends() zurueckgibt (Schluessel
    `trends`, je Eintrag `name` statt der DB-Spalte `trend_name`).

    Der 16:10-Lauf macht keine eigene Trendanalyse — die Megatrend-Lage aendert
    sich nicht in 70 Minuten —, sondern liest den Vormittags-Eintrag einfach aus
    der DB, damit der Portfolio-Check denselben Trend-Kontext bekommt wie im
    Morgenlauf. Gibt {} zurueck, wenn fuer den Tag noch keine Trends vorliegen
    (z. B. weil Phase 0 am Morgen fehlgeschlagen ist); der Portfolio-Check
    vertraegt einen leeren Trend-Kontext.

    Bewusst akzeptierte Luecke: `sector_rotation` und `trend_summary` — zwei
    Top-Level-Felder, die analyze_trends() zusaetzlich zu `trends` liefert —
    fehlen hier. Der Morgenlauf sieht sie nur, weil sein trend_context die ROHE
    Phase-0-Antwort ist; save_trend_analysis() persistiert ausschliesslich die
    Pro-Trend-Spalten (trend_name, strength, ... next_catalyst), nie diese
    beiden Felder. Es gibt also nichts, aus dem sich hier rekonstruieren liesse
    — nicht mangelnde Sorgfalt, sondern ein fehlendes Speicherziel. Aufrufer,
    die einen Ersatz brauchen, muessen ihn aus dem separat erhobenen
    Markt-Kontext (sector_rotation_in/out, macro_summary aus market_context.py
    — ein anderer Claude-Call, aber inhaltlich die naechstliegende Frage) an
    der eigenen Aufrufstelle einmischen; run_trade_proposals() tut das bereits
    fuer den Portfolio-Check."""
    rows = conn.execute(
        "SELECT * FROM trend_analyses WHERE date = ?", (date,),
    ).fetchall()
    if not rows:
        return {}
    trends = []
    for r in rows:
        trends.append({
            "name": r["trend_name"],
            "strength": r["strength"],
            "duration_estimate": r["duration_estimate"],
            "summary": r["summary"],
            "beneficiary_tickers": r["beneficiary_tickers"].split(",")
                                   if r["beneficiary_tickers"] else [],
            "negative_tickers": r["negative_tickers"].split(",")
                                if r["negative_tickers"] else [],
            "next_catalyst": r["next_catalyst"],
        })
    return {"trends": trends}


def save_market_context(conn: sqlite3.Connection, row: dict) -> None:
    """Schreibt oder ueberschreibt den Marktkontext eines Runs
    (UNIQUE date + run_type). Fehlende Keys werden zu NULL — ein Kontext, in dem
    nichts belegbar war, muss speicherbar bleiben."""
    cols = [
        "date", "run_type", "sp500_change_pct", "vix_level", "market_regime",
        "oil_price", "gold_price", "btc_price", "fear_greed_value",
        "policy_risk_level", "sector_rotation_in", "sector_rotation_out",
        "macro_summary", "advance_decline_ratio",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    conn.execute(
        f"INSERT OR REPLACE INTO market_context ({', '.join(cols)}) "
        f"VALUES ({placeholders})",
        [row.get(c) for c in cols],
    )
    conn.commit()


def log_skipped_ticker(
    conn: sqlite3.Connection,
    ticker: str, date: str, run_type: str,
    reason: str, learnable: bool = False,
) -> None:
    """Records that `ticker` was skipped on `date` and why, so it's excluded
    from the learning module unless learnable=True.

    Zusätzlich wird der kumulative Zähler in ticker_status hochgezählt; über
    config.TICKER_MAX_SKIPS hinaus wird der Ticker deaktiviert und ein Retry-Datum
    gesetzt (Sprint 3B / B.7). Das Event-Log bleibt davon unberührt — die
    Weekly-Mail braucht die Einzelereignisse mit Datum und Grund."""
    conn.execute(
        """INSERT INTO skipped_tickers
           (ticker, date, run_type, reason, learnable)
           VALUES (?, ?, ?, ?, ?)""",
        (ticker, date, run_type, reason, 1 if learnable else 0),
    )
    conn.execute(
        """INSERT INTO ticker_status
               (ticker, skip_count, first_skip_date, last_skip_date)
           VALUES (?, 1, ?, ?)
           ON CONFLICT(ticker) DO UPDATE SET
               skip_count     = ticker_status.skip_count + 1,
               last_skip_date = excluded.last_skip_date""",
        (ticker, date, date),
    )
    row = conn.execute(
        "SELECT skip_count FROM ticker_status WHERE ticker = ?", (ticker,),
    ).fetchone()
    if row and int(row["skip_count"]) > config.TICKER_MAX_SKIPS:
        retry_after = (
            _date_cls.fromisoformat(date)
            + timedelta(days=config.TICKER_RETRY_AFTER_DAYS)
        ).isoformat()
        conn.execute(
            "UPDATE ticker_status SET inactive = 1, retry_after = ? WHERE ticker = ?",
            (retry_after, ticker),
        )
        log.warning(
            f"{ticker}: deaktiviert nach {row['skip_count']} Skips "
            f"(> {config.TICKER_MAX_SKIPS}), Retry ab {retry_after}"
        )
    conn.commit()


def log_guardrail_reject(conn: sqlite3.Connection, row: dict) -> None:
    """Persistiert eine verworfene (oder bei enforced=0 nur markierte) Analyse mit
    Regelname und Detailtext, damit die Weekly-Mail auswerten kann, welche
    Guardrails wie oft greifen (Sprint 3B / B.9)."""
    cols = ["date", "run_type", "ticker", "direction", "rule", "detail", "enforced",
            "sector_etf_momentum", "sector_db_momentum"]
    placeholders = ", ".join(["?"] * len(cols))
    conn.execute(
        f"INSERT INTO guardrail_rejects ({', '.join(cols)}) VALUES ({placeholders})",
        [row.get(c) for c in cols],
    )
    conn.commit()


def load_guardrail_rejects_since(
    conn: sqlite3.Connection, since: str,
) -> list[sqlite3.Row]:
    """Gibt alle Guardrail-Rejects ab (einschliesslich) `since` zurueck,
    neueste zuerst."""
    return conn.execute(
        "SELECT * FROM guardrail_rejects WHERE date >= ? ORDER BY date DESC, ticker",
        (since,),
    ).fetchall()


def get_ticker_status(conn: sqlite3.Connection, ticker: str) -> sqlite3.Row | None:
    """Gibt die ticker_status-Zeile eines Tickers zurück, oder None wenn er noch
    nie übersprungen wurde."""
    return conn.execute(
        "SELECT * FROM ticker_status WHERE ticker = ?", (ticker,),
    ).fetchone()


def is_ticker_inactive(conn: sqlite3.Connection, ticker: str, today: str) -> bool:
    """True, wenn `ticker` deaktiviert ist UND sein Retry-Datum noch in der Zukunft
    liegt. Ab dem Retry-Datum gilt er wieder als aktiv, damit die Pipeline ihn
    erneut versucht — sonst fiele ein Ticker nach einem Ausfall dauerhaft raus."""
    row = conn.execute(
        "SELECT inactive, retry_after FROM ticker_status WHERE ticker = ?", (ticker,),
    ).fetchone()
    if row is None or not row["inactive"]:
        return False
    retry_after = row["retry_after"]
    if retry_after is None:
        return True
    return today < retry_after


def reactivate_ticker(conn: sqlite3.Connection, ticker: str) -> bool:
    """Setzt skip_count, inactive und retry_after für `ticker` zurück. Gibt True
    zurück, wenn tatsächlich etwas zurückgesetzt wurde."""
    cur = conn.execute(
        """UPDATE ticker_status
           SET skip_count = 0, inactive = 0, retry_after = NULL
           WHERE ticker = ? AND (skip_count > 0 OR inactive = 1)""",
        (ticker,),
    )
    conn.commit()
    return cur.rowcount > 0


def list_inactive_tickers(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Gibt alle aktuell deaktivierten Ticker zurück, alphabetisch sortiert."""
    return conn.execute(
        "SELECT * FROM ticker_status WHERE inactive = 1 ORDER BY ticker"
    ).fetchall()


def save_position_recommendation(conn: sqlite3.Connection, row: dict) -> int:
    """Inserts or overwrites one Phase-4a position_recommendations row and
    returns its id."""
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
    conn: sqlite3.Connection, today: str, max_trading_days: int = config.MAX_HOLD_DAYS,
) -> list[sqlite3.Row]:
    """Returns open, learnable predictions whose calendar age <= max_trading_days
    days from `today`. We use a calendar approximation (sqlite julianday); the
    walk-forward evaluator handles trading-day precision separately.

    Predictions mit `date == today` sind ausgeschlossen: sie sind zum Zeitpunkt
    des Laufs frische Vorschlaege aus Phase 4 desselben Laufs, noch keine
    offenen Positionen. Erst ab dem Folgetag darf Phase 4a (der Portfolio-Check)
    sie gegenchecken (Sprint 3B / Plan 2, Fix zu B.5) — ohne diesen Ausschluss
    pruefte Phase 4a jede gerade erst persistierte Prediction gegen genau die
    Analyse, die sie erzeugt hat: ein unnoetiger Claude-Call je Signal und
    derselbe Ticker doppelt in der Mail."""
    return conn.execute(
        """SELECT * FROM predictions
           WHERE status='open' AND learnable=1
             AND date < ?
             AND julianday(?) - julianday(date) <= ?
           ORDER BY date DESC""",
        (today, today, max_trading_days),
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
    """Returns all predictions for a given date/run_type, best score first."""
    return conn.execute(
        """SELECT * FROM predictions
           WHERE date=? AND run_type=?
           ORDER BY total_score DESC""",
        (date, run_type),
    ).fetchall()


def load_predictions_for_revalidation(
    conn: sqlite3.Connection, date: str,
) -> list[sqlite3.Row]:
    """Die heutigen offenen pre_market-Predictions — Eingangsmenge der
    Re-Validierung im 16:10-Lauf."""
    return conn.execute(
        """SELECT * FROM predictions
           WHERE date = ? AND run_type = 'pre_market'
             AND status = 'open' AND learnable = 1
           ORDER BY probability_pct DESC""",
        (date,),
    ).fetchall()


def load_position_recommendations_for_date(
    conn: sqlite3.Connection, date: str, run_type: str,
) -> list[sqlite3.Row]:
    """Returns Phase-4a recommendations for a date/run_type joined with their
    underlying prediction (ticker, direction, entry/TP/SL)."""
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
    """Returns outcomes evaluated on/after since_date, joined with their
    prediction's ticker/direction/score/entry price, newest first."""
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
    """Returns cached fundamentals for `ticker` if fetched within the last
    7 days, else None (caller should re-fetch and re-cache)."""
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
    """Inserts or overwrites `ticker`'s cached fundamentals with today's (or
    the given) fetch date, resetting its 7-day TTL."""
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
    """Inserts one price_history bar only if that ticker/date doesn't already
    exist — used for incremental daily updates, never overwrites."""
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
    """Loads up to `limit` most recent price_history rows for `ticker` on/before
    as_of_date as an OHLCV DataFrame, for local indicator computation instead of
    a fresh provider fetch. None if no rows exist."""
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


# --- Weekly-Aggregate fuer die vier B.9-Bloecke (Sprint 3B / Plan 2, Task 18) ---

def _first_trade_proposals_date(conn: sqlite3.Connection) -> str | None:
    """Tag des ersten trade_proposals-Laufs. Davor kann es kein revision_verdict
    gegeben haben — ohne diese Grenze waechst die Gruppe 'nie geprueft' auf Dauer
    als Altlast mit und die Auswertung wird unbrauchbar."""
    row = conn.execute(
        "SELECT MIN(date) AS d FROM predictions WHERE run_type = 'trade_proposals'"
    ).fetchone()
    return row["d"] if row and row["d"] else None


def load_revision_effectiveness(
    conn: sqlite3.Connection, since_date: str,
) -> dict:
    """B.9/Block 1 in der Fassung nach E3: verdient der 16:10-Lauf seine Kosten?

    Durch die Abloesung hat jede Trade-Idee genau EIN Outcome — 'Trefferquote nach
    run_type' waere damit sinnlos. Verglichen werden stattdessen drei Gruppen:
      confirmed — vom 16:10-Lauf bestaetigte Signale (run_type='trade_proposals')
      rejected  — vom 16:10-Lauf abgelehnte (revision_verdict gedreht/verworfen)
      unchecked — nie geprueft (z.B. weil der Lauf ausfiel)

    Liegt die Trefferquote der abgelehnten unter der der bestaetigten, filtert der
    Lauf richtig."""
    start = _first_trade_proposals_date(conn)
    empty = {"total": 0, "correct": 0, "pl_eur": 0.0}
    if start is None:
        return {"confirmed": dict(empty), "rejected": dict(empty),
                "unchecked": dict(empty), "since": since_date}
    floor = max(since_date, start)

    def _agg(where: str) -> dict:
        r = conn.execute(
            f"""SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN o.correct_direction_eod
                                         THEN 1 ELSE 0 END), 0) AS correct,
                       COALESCE(SUM(o.profit_loss_eur), 0) AS pl
                FROM outcomes o JOIN predictions p ON p.id = o.prediction_id
                WHERE p.date >= ? AND {where}""",
            (floor,),
        ).fetchone()
        return {"total": int(r["total"]), "correct": int(r["correct"]),
                "pl_eur": round(float(r["pl"]), 2)}

    return {
        "confirmed": _agg("p.run_type = 'trade_proposals'"),
        "rejected":  _agg("p.run_type = 'pre_market' AND "
                          "p.revision_verdict IN ('gedreht', 'verworfen')"),
        "unchecked": _agg("p.run_type = 'pre_market' AND "
                          "p.revision_verdict IS NULL"),
        "since": floor,
    }


def load_revision_verdict_stats(
    conn: sqlite3.Connection, since_date: str,
) -> list[sqlite3.Row]:
    """B.9/Block 2: wie oft wurde bestaetigt / geschwaecht / gedreht / verworfen,
    und wie liefen die Gruppen danach."""
    return conn.execute(
        """SELECT p.revision_verdict AS revision_verdict, COUNT(*) AS n,
                  ROUND(AVG(COALESCE(o.profit_loss_eur, 0)), 2) AS avg_pl
           FROM predictions p
           LEFT JOIN outcomes o ON o.prediction_id = p.id
           WHERE p.date >= ? AND p.revision_verdict IS NOT NULL
           GROUP BY p.revision_verdict
           ORDER BY n DESC""",
        (since_date,),
    ).fetchall()


def load_guardrail_reject_stats(
    conn: sqlite3.Connection, since_date: str,
) -> list[sqlite3.Row]:
    """B.9/Block 3: welche Guardrails greifen wie oft — getrennt nach weicher
    Warnung (enforced=0, pre_market) und harter Ablehnung (enforced=1, 16:10)."""
    return conn.execute(
        """SELECT rule, enforced, COUNT(*) AS n
           FROM guardrail_rejects
           WHERE date >= ?
           GROUP BY rule, enforced
           ORDER BY n DESC""",
        (since_date,),
    ).fetchall()


def load_skipped_ticker_stats(
    conn: sqlite3.Connection, since_date: str,
) -> list[sqlite3.Row]:
    """B.9/Block 4: welcher Ticker wurde diese Woche wie oft und warum
    uebersprungen, plus sein kumulativer Stand aus ticker_status."""
    return conn.execute(
        """SELECT s.ticker, COUNT(*) AS n_week,
                  GROUP_CONCAT(DISTINCT s.reason) AS reasons,
                  ts.skip_count AS skip_total, ts.inactive, ts.retry_after
           FROM skipped_tickers s
           LEFT JOIN ticker_status ts ON ts.ticker = s.ticker
           WHERE s.date >= ?
           GROUP BY s.ticker
           ORDER BY n_week DESC""",
        (since_date,),
    ).fetchall()


def load_sector_mapping_coverage(conn: sqlite3.Connection) -> dict:
    """Anteil der Ticker mit Sub-Sektor-Zuordnung. B.10 nennt eine stabil hohe
    Quote als Voraussetzung dafuer, SECTOR_GUARDRAIL_STRICT auf True zu stellen."""
    universe = (config.SP500_FULL_TICKERS if config.USE_FULL_SP500
                else config.SP500_MVP_TICKERS)
    marks = ",".join("?" * len(universe))
    row = conn.execute(
        f"""SELECT COUNT(*) AS n FROM ticker_sectors
            WHERE sector_id IS NOT NULL AND ticker IN ({marks})""",
        universe,
    ).fetchone()
    mapped, total = int(row["n"]), len(universe)
    return {"mapped": mapped, "total": total,
            "pct": round(mapped / total * 100, 1) if total else 0.0}
