"""Die rechnerischen Checks aus Sprint 3B / B.3.

Bewusst netzwerk- und Claude-frei: jede Funktion nimmt Werte entgegen, die
anderswo bereits erhoben wurden (Markt-Kontext aus Phase 0b, Sektor-Momentum aus
Phase 1d, Kurse aus price_history), und gibt ein Urteil zurueck. Dadurch ist das
Modul ohne Mocking testbar.

Ein Check, der NICHT anschlaegt, gibt None zurueck und erzeugt keine Zeile — das
ist B.3.1 woertlich: "keines vorhanden -> kein Check, kein Log-Eintrag".

Ob ein anschlagender Check das Signal auch blockiert, entscheidet NICHT dieses
Modul, sondern der Aufrufer ueber den enforce-Parameter (Entscheidung E4):
run_pipeline() uebergibt False, run_trade_proposals() uebergibt True."""
import logging
import sqlite3
from dataclasses import dataclass

import config
from src import db

log = logging.getLogger("shares_future.signal_checks")


@dataclass(frozen=True)
class CheckResult:
    """Ein angeschlagener Check. `enforced=True` heisst: das Signal wird verworfen;
    `False` heisst: Warnung in der Mail, Signal geht durch."""
    rule: str
    detail: str
    enforced: bool


def daily_change_pct(
    conn: sqlite3.Connection, ticker: str, date: str,
) -> float | None:
    """Tagesperformance in Prozent aus den letzten zwei Bars bis einschliesslich
    `date`. None, wenn weniger als zwei Bars vorliegen oder der Vortagesschluss 0 ist."""
    rows = conn.execute(
        """SELECT close FROM price_history
           WHERE ticker = ? AND date <= ?
           ORDER BY date DESC LIMIT 2""",
        (ticker, date),
    ).fetchall()
    if len(rows) < 2:
        return None
    cur, prev = float(rows[0]["close"]), float(rows[1]["close"])
    if prev <= 0:
        return None
    return (cur - prev) / prev * 100.0


def compute_relative_strength(
    conn: sqlite3.Connection, ticker: str, date: str,
) -> float | None:
    """Tagesperformance des Tickers minus die seines Sub-Sektor-ETF, in
    Prozentpunkten. None, wenn der Ticker keinem Sub-Sektor zugeordnet ist oder
    einer der beiden Werte fehlt.

    Kein Score und kein Guardrail (die 8-Dimensionen-Gewichtung ist eingefroren):
    der Wert geht als Input in den Re-Validierungs-Prompt und als Spalte in die Mail."""
    sector = db.get_ticker_sector(conn, ticker)
    if sector is None:
        return None
    own = daily_change_pct(conn, ticker, date)
    etf = daily_change_pct(conn, sector["etf"], date)
    if own is None or etf is None:
        return None
    return own - etf


def check_cluster(sector_name: str | None, count: int) -> CheckResult | None:
    """Warnt, wenn ab config.SECTOR_CLUSTER_WARN_AT Signale im selben Sub-Sektor
    liegen. Immer weich: Klumpenrisiko ist eine Positionsgroessen-Frage, keine
    Aussage ueber die Qualitaet des einzelnen Setups."""
    if sector_name is None or count < config.SECTOR_CLUSTER_WARN_AT:
        return None
    return CheckResult(
        rule="sector_cluster",
        detail=f"{count} Signale im Sub-Sektor {sector_name} — Klumpenrisiko",
        enforced=False,
    )
