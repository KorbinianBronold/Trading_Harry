"""Signal-Zeitpunkt und Verdichtung der Intraday-Bars.

Reine Funktionen -- keine DB, kein Netz, kein Claude. Deshalb ohne einen
einzigen Mock testbar."""
import pandas as pd
import pytest

from src.signal_window import signal_time_utc, collapse_to_daily_bar, day_end_utc


def test_signal_time_follows_us_dst_not_berlin():
    """Der Signal-Zeitpunkt haengt an der US-Sitzung. EU und USA schalten an
    verschiedenen Wochenenden um -- eine Berliner Rechnung ginge in den
    Zwischenwochen daneben."""
    # Sommer (EDT, UTC-4): 10:10 ET == 14:10 UTC
    assert signal_time_utc("trade_proposals", "2026-08-05") == "2026-08-05T14:10:00"
    # Winter (EST, UTC-5): 10:10 ET == 15:10 UTC
    assert signal_time_utc("trade_proposals", "2026-01-15") == "2026-01-15T15:10:00"


def test_pre_market_signal_is_before_the_open():
    """pre_market entsteht um 09:00 ET -- eine halbe Stunde VOR der Eroeffnung.
    Das Auswertungsfenster umfasst die Eroeffnung damit vollstaendig."""
    assert signal_time_utc("pre_market", "2026-08-05") == "2026-08-05T13:00:00"


def test_unknown_run_type_has_no_signal_time():
    assert signal_time_utc("weekly", "2026-08-05") is None


def test_day_end_is_the_utc_boundary():
    """openingHours der Instrumente endet auf 00:00 UTC (zone: UTC), deshalb ist
    die Tagesgrenze UTC-Mitternacht und nicht der US-Schluss."""
    assert day_end_utc("2026-08-05") == "2026-08-06T00:00:00"


def test_regular_open_follows_us_dst():
    """Der REGULAERE Open (09:30 ET) -- nicht zu verwechseln mit dem Beginn der
    Capital.com-Handelszeit (08:00 UTC, also vorboerslich)."""
    from src.signal_window import regular_open_utc
    assert regular_open_utc("2026-08-05") == "2026-08-05T13:30:00"   # EDT
    assert regular_open_utc("2026-01-15") == "2026-01-15T14:30:00"   # EST


def test_is_premarket_compares_against_the_regular_open():
    """marketStatus taugt dafuer nicht: es meldete um 08:37 ET TRADEABLE,
    mitten in der Vorboerse. Also die Uhr."""
    from src.signal_window import is_premarket
    assert is_premarket("2026-08-05", "2026-08-05T13:00:00") is True   # 09:00 ET
    assert is_premarket("2026-08-05", "2026-08-05T14:10:00") is False  # 10:10 ET


def _minute_df(rows):
    return pd.DataFrame(
        [{"Open": o, "High": h, "Low": l, "Close": c, "Volume": v}
         for o, h, l, c, v in rows],
        index=pd.to_datetime(
            [f"2026-08-05 14:{10 + i:02d}:00" for i in range(len(rows))]),
    )


def test_collapse_takes_extremes_and_last_close():
    """Der Kern: aus vielen Minutenbars wird EINE Tagesbar. Ohne diese
    Verdichtung zaehlte _walk_forward_hit jede Minute als eigenen 'Tag' und
    days_to_close waere zerstoert -- genau die Kennzahl, an der 3Ds hold_day
    haengt."""
    df = _minute_df([
        (100.0, 101.0,  99.5, 100.5, 10),
        (100.5, 104.0, 100.0, 103.0, 20),   # Tages-High
        (103.0, 103.5,  97.0,  98.0, 30),   # Tages-Low, letzter Close
    ])
    bar = collapse_to_daily_bar(df)
    assert bar == {"Open": 100.0, "High": 104.0, "Low": 97.0,
                   "Close": 98.0, "Volume": 60}


def test_collapse_of_nothing_is_none():
    """Feiertag, Handelsstopp oder Abruffehler: kein Fenster, keine Bar. Die
    Auswertung beginnt dann bei D+1 statt zu scheitern."""
    assert collapse_to_daily_bar(None) is None
    assert collapse_to_daily_bar(pd.DataFrame()) is None
