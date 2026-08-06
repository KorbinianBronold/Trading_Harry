"""Signal-Zeitpunkt und Verdichtung der Intraday-Bars zu einer Tagesbar.

Das Auswertungsfenster beginnt am Signal-Zeitpunkt, nicht am Tagesanfang: die
Tagesbar laeuft laut openingHours ab 08:00 UTC, das Signal entsteht aber erst um
09:00 ET (pre_market) beziehungsweise 10:10 ET (trade_proposals). TP/SL-Treffer
aus der Zeit davor sind Artefakte -- die Position gab es da noch nicht.

Den ganzen Prognosetag auszuschliessen waere jedoch das gespiegelte Artefakt:
Sprint 3D verfolgt die Trefferquote getrennt nach Intraday (hold_day = 1) und
Extended (2-5), und ohne Tag D koennte eine Intraday-These nie am selben Tag als
getroffen erfasst werden.

Reine Funktionen: keine DB, kein Netz, kein Claude."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

NEW_YORK = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# Wann das Signal des jeweiligen Laufs entsteht, in US-Ortszeit. Bewusst an
# America/New_York gehaengt und nicht an Europe/Berlin: EU und USA schalten die
# Sommerzeit an verschiedenen Wochenenden um.
SIGNAL_TIMES_ET: dict[str, time] = {
    "pre_market":      time(9, 0),    # vor der Eroeffnung (09:30 ET)
    "trade_proposals": time(10, 10),  # 40 min nach der Eroeffnung
}

# Regulaere US-Sitzung. NICHT zu verwechseln mit der Capital.com-Handelszeit:
# openingHours meldet 08:00-00:00 UTC, also erweiterte Zeiten. Der "Open" der
# Tagesbar ist deshalb NICHT der Eroeffnungskurs -- gemessen am 2026-08-05 lagen
# beide bei AAPL 0,47 % auseinander (310,54 gegen 309,09).
REGULAR_OPEN_ET = time(9, 30)


def signal_time_utc(run_type: str, date: str) -> str | None:
    """UTC-Zeitstempel des Signals fuer `run_type` an `date`, oder None, wenn der
    Run-Type keinen Entscheidungszeitpunkt hat."""
    et = SIGNAL_TIMES_ET.get(run_type)
    if et is None:
        return None
    local = datetime.combine(datetime.fromisoformat(date).date(), et, tzinfo=NEW_YORK)
    return local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def regular_open_utc(date: str) -> str:
    """UTC-Zeitstempel der regulaeren US-Eroeffnung an `date`."""
    local = datetime.combine(
        datetime.fromisoformat(date).date(), REGULAR_OPEN_ET, tzinfo=NEW_YORK)
    return local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def is_premarket(date: str, now_utc: str) -> bool:
    """True, wenn `now_utc` vor der regulaeren Eroeffnung liegt.

    Aus der Uhr abgeleitet und nicht aus `marketStatus`: das Feld meldete am
    2026-08-06 um 08:37 ET `TRADEABLE` -- mitten in der Vorboerse. Es beschreibt
    die Handelbarkeit des CFDs einschliesslich erweiterter Zeiten, nicht die
    Sitzungsphase."""
    return datetime.fromisoformat(now_utc) < datetime.fromisoformat(
        regular_open_utc(date))


def day_end_utc(date: str) -> str:
    """Ende des Handelstags als UTC-Zeitstempel.

    Die Instrumente laufen laut openingHours bis 00:00 UTC (`zone: UTC`), die
    Tagesgrenze ist also UTC-Mitternacht -- nicht der regulaere US-Schluss."""
    end = datetime.fromisoformat(date).date() + timedelta(days=1)
    return f"{end.isoformat()}T00:00:00"


def collapse_to_daily_bar(df: "pd.DataFrame | None") -> dict | None:
    """Verdichtet Intraday-Bars zu EINER Tagesbar.

    High ist das Maximum, Low das Minimum, Close der letzte Wert des Fensters.
    Genau diese Verdichtung haelt _walk_forward_hit unveraendert: die Funktion
    zaehlt day_offset je Bar, und daraus wird days_to_close. Minutenbars direkt
    in die Sequenz zu geben, wuerde jede Minute als eigenen Tag zaehlen.

    None, wenn kein Fenster vorliegt (Feiertag, Handelsstopp, Abruffehler) --
    die Auswertung beginnt dann bei D+1, statt zu scheitern."""
    if df is None or len(df) == 0:
        return None
    return {
        "Open":   float(df["Open"].iloc[0]),
        "High":   float(df["High"].max()),
        "Low":    float(df["Low"].min()),
        "Close":  float(df["Close"].iloc[-1]),
        "Volume": int(df["Volume"].sum()),
    }
