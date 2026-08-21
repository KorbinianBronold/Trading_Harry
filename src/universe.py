"""Die eine Quelle dafuer, welche Ticker das System ueberhaupt anfasst.

Aktien (Produktivliste oder volle Liste), Rohstoffe, Krypto und die
Sub-Sektor-ETFs bilden zusammen das Universum. Drei Stellen brauchen genau
diese Liste:

  * `setup/historical_loader.py --universe` — der Bootstrap einer leeren DB
  * `main.run_final_close()` — der einzige Schreiber von `price_history`
  * `main._warn_on_thin_history()` — der Guard gegen zu duenne Historie

Vorher baute jede Stelle sie selbst zusammen. Das ist genau die Naht, an der ein
neu aufgenommener Ticker durchfaellt: er kommt in die Config, aber nicht in den
Backfill, wird mangels Bars uebersprungen und zaehlt Richtung Deaktivierung.
"""
import config


def stock_universe() -> list[str]:
    """Die Aktienliste, die das System aktuell faehrt — ohne Rohstoffe, Krypto
    und ETFs.

    ⚠️ Die EINE Stelle, die `USE_FULL_SP500` auswertet. Bis 2026-08-21 stand der
    Ausdruck `SP500_FULL_TICKERS if USE_FULL_SP500 else ...` fuenffach im Code
    (main.py 2x, db.py, universe.py, capital_provider.py). Dieselbe Streuung war
    bei `LEARNING_RETENTION_DAYS` die Ursache dafuer, dass eine von vier
    Tabellen jahrelang auf einer abweichenden Frist stand — wer hier wieder eine
    lokale Kopie anlegt, baut denselben Fehler nach."""
    return (config.SP500_FULL_TICKERS if config.USE_FULL_SP500
            else config.SP500_PROD_TICKERS)


def full_universe() -> list[str]:
    """Alle Ticker, fuer die das System Kurshistorie vorhaelt — dedupliziert und
    in stabiler Reihenfolge (Aktien, Rohstoffe, Krypto, ETFs).

    Mehrere Sub-Sektoren teilen sich einen ETF (MedTech/Pharma/Healthcare Rest
    zeigen alle auf XLV), deshalb die Deduplizierung."""
    stocks = stock_universe()

    ordered = [
        *stocks,
        *config.COMMODITY_TICKERS.values(),
        *config.CRYPTO_TICKERS.values(),
        *sorted(set(config.SUB_SECTOR_ETFS.values())),
    ]

    seen: set[str] = set()
    return [t for t in ordered if not (t in seen or seen.add(t))]


def thin_history_tickers(conn) -> list[str]:
    """Universums-Ticker mit zu wenig Bars fuer die Indikatorberechnung.

    Reine DB-Abfrage, keine API-Calls. Ein Ticker ganz ohne Historie zaehlt mit
    und ist der schwerere Fall: `_fill_price_gaps` laedt bei leerer Historie
    bewusst nichts nach, er bliebe also dauerhaft uebersprungen."""
    from src.data_collector import MIN_BARS_RSI

    counts = {
        r["ticker"]: r["n"]
        for r in conn.execute(
            "SELECT ticker, COUNT(*) AS n FROM price_history GROUP BY ticker"
        ).fetchall()
    }
    return [t for t in full_universe() if counts.get(t, 0) < MIN_BARS_RSI]
