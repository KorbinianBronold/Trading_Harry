"""One-time 3-year historical data pull via Capital.com.

Usage:
    python setup/historical_loader.py --all          # loads SP500_MVP_TICKERS
    python setup/historical_loader.py --universe     # stocks + commodities + crypto + ETFs
    python setup/historical_loader.py --full-sp500   # loads SP500_FULL_TICKERS (~500)
    python setup/historical_loader.py --tickers AAPL MSFT NVDA

Each ticker: get_price_history(days=1095) → INSERT OR IGNORE into price_history.
"""
import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path

# Direktaufruf ("python setup/historical_loader.py") legt nur setup/ auf sys.path —
# ohne diesen Bootstrap schlaegt "import config" fehl, obwohl CLAUDE.md genau
# diesen Aufruf dokumentiert. Bei "python -m setup.historical_loader" ist
# __package__ gesetzt und der Block greift nicht.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from src import db  # noqa: E402
from src.providers.capital_provider import (  # noqa: E402
    CapitalComProvider, MAX_BARS_PER_REQUEST,
)
from src.universe import full_universe  # noqa: E402

log = logging.getLogger("shares_future.historical_loader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Capital.com liefert BARS, nicht Kalendertage — 1000 Tagesbars sind rund vier
# Handelsjahre und damit mehr als die angepeilten drei. Der frueher hier stehende
# Wert 1095 (Kalendertage) ueberschritt das API-Limit und liess jeden Abruf mit
# HTTP 400 scheitern, s. capital_provider.MAX_BARS_PER_REQUEST.
DAYS_3_YEARS          = MAX_BARS_PER_REQUEST
PAUSE_BETWEEN_TICKERS = 0.5  # 0.5s → 120 req/min; Capital.com allows 600/min


def load_ticker_history(
    ticker: str,
    db_path: str = str(config.DB_PATH),
    days: int    = DAYS_3_YEARS,
    provider: CapitalComProvider | None = None,
) -> int:
    """Fetch and persist historical OHLCV for one ticker.

    `provider` sollte von load_all() durchgereicht werden, damit alle Ticker
    dieselbe Capital.com-Session teilen (s. dort). Ohne Angabe wird eine eigene
    Instanz gebaut — praktisch fuer Einzelaufrufe.

    Returns the number of rows newly inserted (0 if all already existed)."""
    provider = provider or CapitalComProvider()
    df = provider.get_price_history(ticker, days=days)
    if df is None or df.empty:
        log.warning(f"{ticker}: no data returned from Capital.com")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)

    inserted = 0
    for ts, row in df.iterrows():
        d   = ts.strftime("%Y-%m-%d")
        cur = conn.execute(
            """INSERT OR IGNORE INTO price_history
               (ticker, date, open, high, low, close, volume, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticker, d,
                float(row.get("Open",   0)),
                float(row.get("High",   0)),
                float(row.get("Low",    0)),
                float(row.get("Close",  0)),
                int(row.get("Volume", 0) or 0),
                "capital.com",
            ),
        )
        inserted += cur.rowcount
    conn.commit()
    conn.close()
    log.info(f"{ticker}: {inserted}/{len(df)} rows inserted")
    return inserted


def load_all(
    tickers: list[str],
    db_path: str = str(config.DB_PATH),
    days: int    = DAYS_3_YEARS,
) -> dict[str, int]:
    """Load historical data for all tickers. Returns {ticker: rows_inserted}.

    Baut GENAU EINEN Provider und reicht ihn durch: Capital.com limitiert den
    /session-Endpoint, und der Provider authentifiziert lazy je Instanz. Eine
    Instanz je Ticker liess den Lauf ab ~20 Tickern in HTTP 429 laufen und
    verstiess gegen die Invariante 'Ein Session-Object pro Run' (B-09)."""
    provider = CapitalComProvider()
    results: dict[str, int] = {}
    for i, ticker in enumerate(tickers):
        log.info(f"[{i + 1}/{len(tickers)}] Loading {ticker}...")
        results[ticker] = load_ticker_history(
            ticker, db_path=db_path, days=days, provider=provider,
        )
        time.sleep(PAUSE_BETWEEN_TICKERS)
    return results


def _run_list_inactive(db_path: str) -> None:
    """Gibt alle deaktivierten Ticker mit Skip-Zahl und Retry-Datum aus."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    rows = db.list_inactive_tickers(conn)
    if not rows:
        print("Keine deaktivierten Ticker.")
    else:
        print(f"{len(rows)} deaktivierte Ticker "
              f"(> {config.TICKER_MAX_SKIPS} Skips):\n")
        for r in rows:
            print(f"  {r['ticker']:<10} skips={r['skip_count']:<4} "
                  f"letzter Skip={r['last_skip_date']}  "
                  f"Retry ab={r['retry_after']}")
        print("\nSofort reaktivieren:  "
              "python setup/historical_loader.py --reactivate TICKER")
    conn.close()


def _run_report_coverage(db_path: str) -> None:
    """Gibt je Universums-Ticker die Zahl der Bars aus und markiert alles, was
    unter MIN_BARS_RSI liegt.

    Reine DB-Operation, kein einziger Capital.com-Call. Genau dieser Report
    haette die drei leeren Laeufe vom 2026-08-04 in Sekunden erklaert: dort
    standen 19 Bars je Aktie, eine unter der Grenze."""
    from src.data_collector import MIN_BARS_RSI

    conn = db.connect(db_path)
    db.init_schema(conn)
    counts = {
        r["ticker"]: (r["n"], r["last_date"])
        for r in conn.execute(
            "SELECT ticker, COUNT(*) AS n, MAX(date) AS last_date "
            "FROM price_history GROUP BY ticker"
        ).fetchall()
    }
    conn.close()

    universe = full_universe()
    thin = [t for t in universe if counts.get(t, (0, None))[0] < MIN_BARS_RSI]

    print(f"Historien-Abdeckung: {len(universe)} Ticker im Universum, "
          f"Mindestbedarf {MIN_BARS_RSI} Bars\n")
    for t in universe:
        n, last = counts.get(t, (0, None))
        mark = "  " if n >= MIN_BARS_RSI else "!!"
        print(f"{mark} {t:<10} {n:>5} Bars   letzter {last or '—'}")

    if thin:
        print(f"\n{len(thin)} Ticker unter der Grenze: {', '.join(thin)}")
        print("Beheben mit:  python setup/historical_loader.py --universe")
    else:
        print("\nAlle Ticker haben genug Historie.")


def _run_reactivate(db_path: str, tickers: list[str]) -> None:
    """Setzt skip_count und inactive-Flag der genannten Ticker zurueck."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    for t in tickers:
        changed = db.reactivate_ticker(conn, t)
        print(f"{t}: {'reaktiviert' if changed else 'kein Skip-Status — nichts zu tun'}")
    conn.close()


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: laedt historische Bars oder verwaltet den Ticker-Status.
    Genau eine der Modus-Optionen ist Pflicht."""
    parser = argparse.ArgumentParser(
        description="Capital.com price history loader + ticker status management",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tickers",    nargs="+", help="Specific tickers to load")
    group.add_argument("--all",        action="store_true", help="Load SP500_MVP_TICKERS")
    group.add_argument("--full-sp500", action="store_true", help="Load SP500_FULL_TICKERS (~500)")
    group.add_argument("--universe",   action="store_true",
                       help="Load the full universe: stocks + commodities + crypto + sector ETFs")
    group.add_argument("--reactivate", nargs="+", metavar="TICKER",
                       help="Reset skip_count/inactive for these tickers (no data load)")
    group.add_argument("--list-inactive", action="store_true",
                       help="List deactivated tickers with their retry date (no data load)")
    group.add_argument("--report-coverage", action="store_true",
                       help="Report bars per universe ticker, flag thin history (no data load)")
    parser.add_argument("--db-path", default=str(config.DB_PATH))
    parser.add_argument("--days",    type=int, default=DAYS_3_YEARS)
    args = parser.parse_args(argv)

    # Status-Modi: reine DB-Operationen, kein einziger Capital.com-Call.
    if args.list_inactive:
        _run_list_inactive(args.db_path)
        return
    if args.report_coverage:
        _run_report_coverage(args.db_path)
        return
    if args.reactivate:
        _run_reactivate(args.db_path, args.reactivate)
        return

    if args.tickers:
        tickers = args.tickers
    elif args.universe:
        tickers = full_universe()
    elif getattr(args, "full_sp500", False):
        tickers = config.SP500_FULL_TICKERS
    else:
        tickers = config.SP500_MVP_TICKERS

    log.info(f"Loading {len(tickers)} tickers x {args.days} days")
    results = load_all(tickers, db_path=args.db_path, days=args.days)
    log.info(f"Done. {sum(results.values())} rows inserted across {len(tickers)} tickers.")


if __name__ == "__main__":
    main()
