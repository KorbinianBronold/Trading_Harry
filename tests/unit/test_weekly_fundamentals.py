"""Tests fuer den Wochenlauf-Fundamentals/Earnings-Vorlauf (Sprint 3C /
Analyse-Pipeline-Umbau, Plan 2, Task 12). Rein gemockt -- kein Netz, kein
Marker: full_universe() bei USE_FULL_SP500=false hat nur ~30 Ticker, ein
echter Live-Sweep waere hier weder noetig noch im Sinne von tests/live/
(das ist fuer leichte Verbindungspruefungen reserviert, kein Bulk-Fetch)."""
from datetime import date as date_cls
from unittest.mock import MagicMock

from src import db
from main import _update_weekly_fundamentals


def _fundamentals(**overrides) -> dict:
    base = {
        "pe_ratio": 25.0, "forward_pe": 22.0, "market_cap_b": 200.0,
        "debt_equity": 1.0, "sector": "Technology",
        "analyst_upside": 5.0, "consensus": "buy",
    }
    base.update(overrides)
    return base


def test_fetches_fundamentals_and_earnings_for_an_uncached_ticker(in_memory_db):
    db.init_schema(in_memory_db)
    provider = MagicMock()
    provider.get_fundamentals.return_value = _fundamentals()
    provider.get_earnings_calendar.return_value = {"days_to_next": 14, "last_beat_pct": 3.5}

    _update_weekly_fundamentals(in_memory_db, date="2026-08-15",
                                provider=provider, universe=["AAPL"])

    cached = db.get_cached_fundamentals(in_memory_db, "AAPL", today="2026-08-15")
    assert cached is not None
    assert cached["sector"] == "Technology"
    assert cached["earnings_next_date"] == "2026-08-29"   # 14 Tage nach 15.08.
    provider.get_fundamentals.assert_any_call("AAPL")
    provider.get_earnings_calendar.assert_any_call("AAPL")


def test_skips_a_ticker_with_fresh_fundamentals_and_a_set_earnings_date(in_memory_db):
    """Der eigentliche Zweck des Vorlaufs ist erledigt -- kein erneuter Call."""
    db.init_schema(in_memory_db)
    db.save_fundamentals_cache(
        in_memory_db, "AAPL",
        {**_fundamentals(), "earnings_next_date": "2026-09-01"},
        fetched_date="2026-08-14",
    )
    provider = MagicMock()

    _update_weekly_fundamentals(in_memory_db, date="2026-08-15",
                                provider=provider, universe=["AAPL"])

    provider.get_fundamentals.assert_not_called()
    provider.get_earnings_calendar.assert_not_called()


def test_does_not_skip_fresh_fundamentals_without_an_earnings_date(in_memory_db):
    """Bug-Fix gegenueber dem Plan-Pseudocode: eine Zeile, die der Tageslauf
    (fetch_missing_fundamentals, Task 7) frisch angelegt hat, traegt NIE ein
    earnings_next_date -- eine reine 'ist gecacht'-Pruefung wuerde diesen
    Ticker fuer immer ueberspringen und er bekaeme nie ein Earnings-Datum."""
    db.init_schema(in_memory_db)
    db.save_fundamentals_cache(
        in_memory_db, "AAPL", _fundamentals(), fetched_date="2026-08-15",
    )
    provider = MagicMock()
    provider.get_fundamentals.return_value = _fundamentals()
    provider.get_earnings_calendar.return_value = {"days_to_next": 5, "last_beat_pct": None}

    _update_weekly_fundamentals(in_memory_db, date="2026-08-15",
                                provider=provider, universe=["AAPL"])

    provider.get_earnings_calendar.assert_any_call("AAPL")
    cached = db.get_cached_fundamentals(in_memory_db, "AAPL", today="2026-08-15")
    assert cached["earnings_next_date"] == "2026-08-20"


def test_ticker_with_no_upcoming_earnings_gets_no_earnings_date(in_memory_db):
    db.init_schema(in_memory_db)
    provider = MagicMock()
    provider.get_fundamentals.return_value = _fundamentals()
    provider.get_earnings_calendar.return_value = {"days_to_next": None, "last_beat_pct": None}

    _update_weekly_fundamentals(in_memory_db, date="2026-08-15",
                                provider=provider, universe=["AAPL"])

    cached = db.get_cached_fundamentals(in_memory_db, "AAPL", today="2026-08-15")
    assert cached is not None
    assert cached["earnings_next_date"] is None


def test_a_failing_ticker_does_not_abort_the_run(in_memory_db):
    """Nicht fatal: ein API-Fehler bei einem Ticker ueberspringt nur ihn."""
    db.init_schema(in_memory_db)
    provider = MagicMock()

    def _fundamentals_side_effect(ticker):
        if ticker == "AAPL":
            raise RuntimeError("finnhub down")
        return _fundamentals()

    provider.get_fundamentals.side_effect = _fundamentals_side_effect
    provider.get_earnings_calendar.return_value = {"days_to_next": None, "last_beat_pct": None}

    _update_weekly_fundamentals(in_memory_db, date="2026-08-15",
                                provider=provider, universe=["AAPL", "MSFT"])

    assert db.get_cached_fundamentals(in_memory_db, "AAPL", today="2026-08-15") is None
    assert db.get_cached_fundamentals(in_memory_db, "MSFT", today="2026-08-15") is not None


def test_an_empty_fundamentals_response_is_not_persisted(in_memory_db):
    """get_fundamentals() faengt seine eigenen Fehler intern ab und liefert
    dann {} statt zu werfen (kein API-Key, alle Sub-Calls gescheitert) -- ein
    leeres Dict darf keine Cache-Zeile anlegen."""
    db.init_schema(in_memory_db)
    provider = MagicMock()
    provider.get_fundamentals.return_value = {}
    provider.get_earnings_calendar.return_value = {"days_to_next": None, "last_beat_pct": None}

    _update_weekly_fundamentals(in_memory_db, date="2026-08-15",
                                provider=provider, universe=["AAPL"])

    assert db.get_cached_fundamentals(in_memory_db, "AAPL", today="2026-08-15") is None


def test_covers_the_full_universe_by_default(in_memory_db, mocker):
    """Ohne explizites universe-Argument laeuft der Vorlauf ueber
    full_universe() -- die eine Quelle des Ticker-Universums."""
    db.init_schema(in_memory_db)
    mocker.patch("main.full_universe", return_value=["AAPL", "GC=F"])
    provider = MagicMock()
    provider.get_fundamentals.return_value = _fundamentals()
    provider.get_earnings_calendar.return_value = {"days_to_next": None, "last_beat_pct": None}

    _update_weekly_fundamentals(in_memory_db, date="2026-08-15", provider=provider)

    assert provider.get_fundamentals.call_count == 2
