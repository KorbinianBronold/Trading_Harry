import random
import time
import logging
import pandas as pd
import yfinance as yf
from src.providers.base import DataProvider

log = logging.getLogger("shares_future.yfinance")


class YFinanceProvider(DataProvider):
    PAUSE_BETWEEN_TICKERS = 0.8
    PAUSE_BETWEEN_BATCHES = 12
    PAUSE_ON_ERROR = 5
    MAX_RETRIES = 2
    JITTER_MAX = 0.5
    MIN_ROWS = 20

    def get_price_history(self, ticker: str, days: int = 90) -> pd.DataFrame | None:
        for attempt in range(self.MAX_RETRIES):
            try:
                time.sleep(self.PAUSE_BETWEEN_TICKERS + random.uniform(0, self.JITTER_MAX))
                hist = yf.Ticker(ticker).history(period=f"{days}d")
                if hist is None or hist.empty or len(hist) < self.MIN_ROWS:
                    rows = len(hist) if hist is not None else 0
                    raise ValueError(f"Insufficient data: {rows} rows")
                return hist
            except Exception as e:
                log.warning(f"{ticker}: yfinance attempt {attempt + 1} failed: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.PAUSE_ON_ERROR * (2 ** attempt))
        log.error(f"{ticker}: all {self.MAX_RETRIES} yfinance attempts failed")
        return None

    def get_fundamentals(self, ticker: str) -> dict:
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception as e:
            log.warning(f"{ticker}: fundamentals fetch failed: {e}")
            return {}

        target = info.get("targetMeanPrice")
        current = info.get("currentPrice")
        upside = ((target - current) / current * 100) if target and current else None
        market_cap = info.get("marketCap")
        return {
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "market_cap_b": (market_cap / 1e9) if market_cap else None,
            "debt_equity": (info.get("debtToEquity") / 100) if info.get("debtToEquity") else None,
            "sector": info.get("sector", "Unknown"),
            "analyst_upside": upside,
            "consensus": info.get("recommendationKey"),
        }

    def get_earnings_calendar(self, ticker: str) -> dict:
        # yfinance earnings calendar is unreliable; handled by FinnhubProvider.
        return {"days_to_next": None, "last_beat_pct": None}

    def get_last_available_date(self, ticker: str) -> str | None:
        df = self.get_price_history(ticker, days=5)
        if df is None or df.empty:
            return None
        return df.index[-1].strftime("%Y-%m-%d")

    def get_ohlc_after(
        self, ticker: str, start_date: str, end_date: str,
    ) -> "pd.DataFrame | None":
        df = self.get_price_history(ticker, days=90)
        if df is None or df.empty:
            return None
        import pandas as pd
        mask = (df.index >= pd.Timestamp(start_date)) & (df.index <= pd.Timestamp(end_date))
        sub = df.loc[mask]
        return sub if not sub.empty else None
