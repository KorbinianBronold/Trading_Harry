"""Sektor-Momentum: zwei unabhaengige Signale je Sub-Sektor.

Der ETF-Pfad holt die Tagesperformance des Sub-Sektor-ETF von Capital.com. Der
DB-Pfad mittelt die Tagesperformance aller Ticker desselben Sub-Sektors aus
price_history — reines SQL, kostenlos, aber erst ab
config.SECTOR_DB_MOMENTUM_MIN_TICKERS Tickern aussagekraeftig. Beide Werte werden
getrennt gespeichert und nie verrechnet: Sprint 3D soll datenbasiert messen
koennen, welches Signal besser predictet.

Das Modul erhebt und persistiert nur. Die Guardrail-Auswertung (hartes Reject nur
bei uebereinstimmenden Signalen, sonst weiche Warnung) gehoert zu Phase B.3.
Eingefuehrt in Sprint 3B / Plan 1 (Entscheidung D9)."""
import logging

import pandas as pd

import config
from src import db
from src.providers.base import DataProvider

log = logging.getLogger("shares_future.sector_momentum")


def _bar_date(ts) -> str:
    """Normalisiert einen DataFrame-Index-Eintrag auf ein ISO-Datum."""
    return ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]


def _daily_change_pct(df: pd.DataFrame | None) -> float | None:
    """Tagesperformance in Prozent aus den letzten zwei Bars, oder None wenn
    weniger als zwei Bars vorliegen bzw. der Vortagesschluss 0 ist."""
    if df is None or len(df) < 2:
        return None
    prev = float(df["Close"].iloc[-2])
    cur = float(df["Close"].iloc[-1])
    if prev <= 0:
        return None
    return (cur - prev) / prev * 100.0


def _fetch_etf_momentum(
    price_provider: DataProvider, conn, etf: str, date: str,
) -> float | None:
    """Holt die letzten Bars des Sektor-ETF, schreibt sie in price_history und
    gibt die Tagesperformance zurueck. None bei jedem Abruf- oder Datenproblem.

    Bars nach `date` werden verworfen, damit das ETF-Signal denselben Handelstag
    misst wie das DB-Signal."""
    try:
        df = price_provider.get_price_history(etf, days=5)
    except Exception as e:
        log.warning(f"{etf}: ETF-Momentum-Abruf fehlgeschlagen: {e}")
        return None
    if df is None or df.empty:
        log.warning(f"{etf}: keine Bars fuer ETF-Momentum")
        return None

    df = df[[_bar_date(ts) <= date for ts in df.index]]
    if df.empty:
        log.warning(f"{etf}: nur Bars nach {date} — kein ETF-Momentum")
        return None

    _raw = getattr(price_provider, "_source_name", None)
    source = _raw if isinstance(_raw, str) else "capital.com"
    for ts, row in df.iterrows():
        db.insert_price_bar_if_missing(
            conn, ticker=etf, date=_bar_date(ts),
            open_=float(row.get("Open", 0)), high=float(row.get("High", 0)),
            low=float(row.get("Low", 0)), close=float(row.get("Close", 0)),
            volume=int(row.get("Volume", 0) or 0), source=source,
        )
    conn.commit()
    return _daily_change_pct(df)


def collect_sector_momentum(
    conn, date: str, run_type: str, price_provider: DataProvider,
) -> dict[int, dict]:
    """Erhebt beide Momentum-Signale fuer jeden Sub-Sektor und persistiert sie.

    Gibt {sector_id: {"etf_momentum": ..., "db_momentum": ..., "ticker_count": ...}}
    zurueck. Jeder ETF wird nur einmal abgerufen, auch wenn sich mehrere
    Sub-Sektoren einen teilen (MedTech/Pharma/Healthcare Rest -> XLV)."""
    db_by_sector = db.compute_sector_db_momentum(conn, date=date)

    etf_cache: dict[str, float | None] = {}
    out: dict[int, dict] = {}

    for name, etf in config.SUB_SECTOR_ETFS.items():
        row = conn.execute(
            "SELECT id FROM sectors WHERE name = ?", (name,),
        ).fetchone()
        if row is None:
            log.warning(f"Sub-Sektor {name!r} fehlt in der sectors-Tabelle")
            continue
        sector_id = int(row["id"])

        if etf not in etf_cache:
            etf_cache[etf] = _fetch_etf_momentum(price_provider, conn, etf, date)

        agg = db_by_sector.get(sector_id, {"momentum": None, "ticker_count": 0})
        # Zwei Befunde aus dem Live-Lauf vom 2026-07-28 (Handelstag 27.07.), die
        # die Guardrail-Logik in Plan 2 kennen muss:
        #
        # 1. RICHTUNG VERGLEICHEN, NICHT BETRAG. Die beiden Signale messen
        #    dieselbe Bewegung, aber nicht dieselbe Grundgesamtheit: Retail kam
        #    auf +2,89% (XRT) gegen +1,17% (DB), Financials Rest auf +1,00%
        #    gegen +2,07% — einmal Faktor ~2,5 nach oben, einmal nach unten.
        #    XRT ist gleichgewichtet und small-cap-lastig, unsere Retail-Ticker
        #    sind AMZN/WMT/HD. Ein Schwellenwert auf der Differenz der Betraege
        #    waere damit Rauschen; belastbar ist nur das Vorzeichen.
        #
        # 2. SEMICONDUCTORS-LUECKE — loest sich erst mit Sprint 3F. Bei der
        #    20-Ticker-MVP-Liste erreichen nur 2 von 21 Sub-Sektoren die
        #    SECTOR_DB_MOMENTUM_MIN_TICKERS-Grenze. Ausgerechnet der groesste
        #    Tagesmove hatte keinen Gegencheck: SOXX -2,50% bei nur 2 Tickern
        #    (NVDA, AVGO) -> db_momentum NULL. Der Hybrid degradiert also genau
        #    dort auf die weiche Warnung, wo ein harter Guardrail am meisten
        #    brachte. Kein Fehler, sondern eine Frage der Abdeckung: erst die
        #    volle Ticker-Liste aus 3F fuellt die Sub-Sektoren auf.
        entry = {
            "etf_momentum": etf_cache[etf],
            "db_momentum":  agg["momentum"],
            "ticker_count": agg["ticker_count"],
        }
        db.save_sector_momentum(conn, {
            "date": date, "run_type": run_type, "sector_id": sector_id, **entry,
        })
        out[sector_id] = entry

    both = sum(1 for e in out.values()
               if e["etf_momentum"] is not None and e["db_momentum"] is not None)
    log.info(
        f"Sektor-Momentum: {len(out)} Sub-Sektoren, {both} mit beiden Signalen "
        f"(nur dort kann der Guardrail hart greifen)"
    )
    return out
