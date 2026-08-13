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

    def get_premarket_prices_batch(
        self, tickers: list[str], chunk_size: int = 20,
    ) -> dict[str, float | None]:
        """Batch live-quote lookup for many tickers at once (Spec 4.3.1).

        Deliberately NOT @abstractmethod: single-ticker get_premarket_price()
        is itself not part of this interface today — only Capital.com serves
        live quotes at all (Provider-Hierarchie: Capital.com ist alleiniger
        OHLC-Provider, Finnhub liefert nur Fundamentals). Forcing every
        DataProvider subclass to implement this would break FinnhubProvider
        for a method it is never called on. Declared here anyway so the
        contract is documented and typed for callers that hold a DataProvider
        reference. Default: not supported."""
        raise NotImplementedError(
            f"{type(self).__name__} liefert keine Live-Kurse "
            f"(get_premarket_prices_batch)"
        )
