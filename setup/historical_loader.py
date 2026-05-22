"""One-time 3-year historical data pull via Capital.com.

Usage:
    python setup/historical_loader.py --all          # loads SP500_MVP_TICKERS
    python setup/historical_loader.py --full-sp500   # loads SP500_FULL_TICKERS (~500)
    python setup/historical_loader.py --tickers AAPL MSFT NVDA

Each ticker: get_price_history(days=1095) → INSERT OR IGNORE into price_history.
"""
import argparse
import logging
import sqlite3
import time

import config
from src import db
from src.providers.capital_provider import CapitalComProvider

log = logging.getLogger("shares_future.historical_loader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DAYS_3_YEARS          = 1095
PAUSE_BETWEEN_TICKERS = 0.5  # 0.5s → 120 req/min; Capital.com allows 600/min


def load_ticker_history(
    ticker: str,
    db_path: str = str(config.DB_PATH),
    days: int    = DAYS_3_YEARS,
) -> int:
    """Fetch and persist historical OHLCV for one ticker.

    Returns the number of rows newly inserted (0 if all already existed)."""
    provider = CapitalComProvider()
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
    """Load historical data for all tickers. Returns {ticker: rows_inserted}."""
    results: dict[str, int] = {}
    for i, ticker in enumerate(tickers):
        log.info(f"[{i + 1}/{len(tickers)}] Loading {ticker}...")
        results[ticker] = load_ticker_history(ticker, db_path=db_path, days=days)
        time.sleep(PAUSE_BETWEEN_TICKERS)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Load 3-year Capital.com price history")
    group  = parser.add_mutually_exclusive_group()
    group.add_argument("--tickers",    nargs="+", help="Specific tickers to load")
    group.add_argument("--all",        action="store_true", help="Load SP500_MVP_TICKERS")
    group.add_argument("--full-sp500", action="store_true", help="Load SP500_FULL_TICKERS (~500)")
    parser.add_argument("--db-path", default=str(config.DB_PATH))
    parser.add_argument("--days",    type=int, default=DAYS_3_YEARS)
    args = parser.parse_args()

    if args.tickers:
        tickers = args.tickers
    elif getattr(args, "full_sp500", False):
        tickers = config.SP500_FULL_TICKERS
    else:
        tickers = config.SP500_MVP_TICKERS

    log.info(f"Loading {len(tickers)} tickers x {args.days} days")
    results = load_all(tickers, db_path=args.db_path, days=args.days)
    log.info(f"Done. {sum(results.values())} rows inserted across {len(tickers)} tickers.")


if __name__ == "__main__":
    main()
