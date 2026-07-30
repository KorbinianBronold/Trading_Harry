"""Tests fuer src/signal_checks.py — die rechnerischen B.3-Checks.

Bewusst ohne jedes Mocking: das Modul spricht weder mit Claude noch mit dem Netz.
Faellt hier etwas um, liegt es an der Logik und nicht an einer Fremd-API."""
import pytest

from src import db


def _seed_sector(conn, ticker="AAPL", sector="Technology Hardware", etf="XLK"):
    """Legt einen Sub-Sektor an und ordnet ihm den Ticker zu."""
    db.init_schema(conn)
    sid = conn.execute("SELECT id FROM sectors WHERE name=?", (sector,)).fetchone()["id"]
    conn.execute("INSERT OR REPLACE INTO ticker_sectors (ticker, sector_id) VALUES (?, ?)",
                 (ticker, sid))
    conn.commit()
    return sid


def _bar(conn, ticker, date, close):
    conn.execute(
        "INSERT OR REPLACE INTO price_history (ticker, date, close) VALUES (?, ?, ?)",
        (ticker, date, close))
    conn.commit()


def test_daily_change_pct_uses_the_two_most_recent_bars(in_memory_db):
    db.init_schema(in_memory_db)
    _bar(in_memory_db, "AAPL", "2026-07-29", 100.0)
    _bar(in_memory_db, "AAPL", "2026-07-30", 102.0)
    from src.signal_checks import daily_change_pct
    assert daily_change_pct(in_memory_db, "AAPL", "2026-07-30") == pytest.approx(2.0)


def test_daily_change_pct_ignores_bars_after_the_date(in_memory_db):
    """Sonst misst der 16:10-Lauf gegen einen Kurs, den es noch nicht gab."""
    db.init_schema(in_memory_db)
    _bar(in_memory_db, "AAPL", "2026-07-29", 100.0)
    _bar(in_memory_db, "AAPL", "2026-07-30", 102.0)
    _bar(in_memory_db, "AAPL", "2026-07-31", 200.0)
    from src.signal_checks import daily_change_pct
    assert daily_change_pct(in_memory_db, "AAPL", "2026-07-30") == pytest.approx(2.0)


def test_daily_change_pct_is_none_with_a_single_bar(in_memory_db):
    db.init_schema(in_memory_db)
    _bar(in_memory_db, "AAPL", "2026-07-30", 102.0)
    from src.signal_checks import daily_change_pct
    assert daily_change_pct(in_memory_db, "AAPL", "2026-07-30") is None


def test_relative_strength_is_ticker_minus_sector_etf(in_memory_db):
    """+3% Ticker gegen +1% ETF ergibt +2 Punkte relative Staerke."""
    _seed_sector(in_memory_db)
    _bar(in_memory_db, "AAPL", "2026-07-29", 100.0)
    _bar(in_memory_db, "AAPL", "2026-07-30", 103.0)
    _bar(in_memory_db, "XLK", "2026-07-29", 100.0)
    _bar(in_memory_db, "XLK", "2026-07-30", 101.0)
    from src.signal_checks import compute_relative_strength
    assert compute_relative_strength(
        in_memory_db, "AAPL", "2026-07-30") == pytest.approx(2.0)


def test_relative_strength_is_none_without_sector_mapping(in_memory_db):
    """Grundregel: lieber kein Wert als ein Wert gegen ein fremdes Instrument."""
    db.init_schema(in_memory_db)
    _bar(in_memory_db, "GOOGL", "2026-07-29", 100.0)
    _bar(in_memory_db, "GOOGL", "2026-07-30", 103.0)
    from src.signal_checks import compute_relative_strength
    assert compute_relative_strength(in_memory_db, "GOOGL", "2026-07-30") is None


def test_cluster_check_is_silent_below_the_threshold():
    from src.signal_checks import check_cluster
    assert check_cluster("Semiconductors", 2) is None


def test_cluster_check_warns_at_the_threshold():
    from src.signal_checks import check_cluster
    r = check_cluster("Semiconductors", 3)
    assert r is not None
    assert r.rule == "sector_cluster"
    assert r.enforced is False, "Klumpenrisiko ist immer nur eine Warnung"
    assert "Semiconductors" in r.detail
