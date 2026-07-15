"""Abstract interface every price/fundamentals data provider must implement,
so the rest of the pipeline can swap providers (Capital.com, Finnhub) without changes."""
from abc import ABC, abstractmethod
from typing import Any
import pandas as pd


class DataProvider(ABC):
    @abstractmethod
    def get_price_history(self, ticker: str, days: int = 90) -> pd.DataFrame | None:
        """Return the last `days` daily OHLCV bars for `ticker`, or None if unavailable."""
        ...

    @abstractmethod
    def get_fundamentals(self, ticker: str) -> dict:
        """Return fundamentals (PE, market cap, sector, etc.) for `ticker` as a dict."""
        ...

    @abstractmethod
    def get_earnings_calendar(self, ticker: str) -> dict:
        """Return next/last earnings info for `ticker` (days to next report, last beat %)."""
        ...

    @abstractmethod
    def get_last_available_date(self, ticker: str) -> str | None:
        """Return the most recent date this provider has price data for `ticker`."""
        ...

    @abstractmethod
    def get_ohlc_after(
        self, ticker: str, start_date: str, end_date: str,
    ) -> pd.DataFrame | None:
        """Daily OHLC bars inclusive [start_date, end_date]. None if empty."""
        ...
