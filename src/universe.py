"""Die eine Quelle dafuer, welche Ticker das System ueberhaupt anfasst.

Aktien (MVP oder volle Liste), Rohstoffe, Krypto und die Sub-Sektor-ETFs bilden
zusammen das Universum. Drei Stellen brauchen genau diese Liste:

  * `setup/historical_loader.py --universe` — der Bootstrap einer leeren DB
  * `main.run_final_close()` — der einzige Schreiber von `price_history`
  * `main._warn_on_thin_history()` — der Guard gegen zu duenne Historie

Vorher baute jede Stelle sie selbst zusammen. Das ist genau die Naht, an der ein
neu aufgenommener Ticker durchfaellt: er kommt in die Config, aber nicht in den
Backfill, wird mangels Bars uebersprungen und zaehlt Richtung Deaktivierung.
"""
import config


def full_universe() -> list[str]:
    """Alle Ticker, fuer die das System Kurshistorie vorhaelt — dedupliziert und
    in stabiler Reihenfolge (Aktien, Rohstoffe, Krypto, ETFs).

    Mehrere Sub-Sektoren teilen sich einen ETF (MedTech/Pharma/Healthcare Rest
    zeigen alle auf XLV), deshalb die Deduplizierung."""
    stocks = (config.SP500_FULL_TICKERS if config.USE_FULL_SP500
              else config.SP500_MVP_TICKERS)

    ordered = [
        *stocks,
        *config.COMMODITY_TICKERS.values(),
        *config.CRYPTO_TICKERS.values(),
        *sorted(set(config.SUB_SECTOR_ETFS.values())),
    ]

    seen: set[str] = set()
    return [t for t in ordered if not (t in seen or seen.add(t))]
