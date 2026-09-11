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
        *config.COMMODITY_TICKERS,
        *config.CRYPTO_TICKERS,
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


def is_commodity_or_crypto(ticker: str) -> bool:
    """True fuer die festen Rohstoff-/Krypto-Epics (config.COMMODITY_TICKERS,
    config.CRYPTO_TICKERS) -- die EINE Frage, die vier Stellen stellen: Gate-
    Ausnahme (Phase 1a), Cache-Lesung (Phase 1), Nachladen (Phase 2b) und der
    Wochenjob. Finnhub kennt keine Rohstoffe, loest aber `GOLD` als die Aktie
    Gold.com Inc auf (C.35) -- deshalb bekommen diese Klassen nie Fundamentals."""
    return ticker in config.COMMODITY_TICKERS or ticker in config.CRYPTO_TICKERS


def has_weekend_sessions(ticker: str) -> bool:
    """True, wenn das Instrument am Wochenende eine volle Sitzung hat -- nur
    Krypto (24/7). Aktien und ETFs handeln gar nicht, Rohstoffe oeffnen bei
    Capital.com erst Sonntag 23:00 UTC."""
    return ticker in config.CRYPTO_TICKERS


def is_partial_weekend_bar(ticker: str, date_iso: str) -> bool:
    """Samstags-/Sonntagsbar eines Instruments ohne Wochenendsitzung (C.36).

    Capital.com liefert Rohstoffen fuer Sonntag eine Tagesbar aus einer Stunde
    Sitzung (Gold Ø 0,56 % Spanne gegen 2,5 % werktags); sie drueckte
    intraday_range_pct (Mittel der letzten 5 Bars) und ATR und kippte Gold in
    ruhigen Phasen unter den 1-%-Guardrail. Alle drei Schreiber von
    price_history (final_close, Gap-Fill, Loader) verwerfen solche Bars ueber
    genau diese Funktion; final_close raeumt Altbestand weg."""
    from datetime import date as _d
    return _d.fromisoformat(date_iso).weekday() >= 5 and not has_weekend_sessions(ticker)
