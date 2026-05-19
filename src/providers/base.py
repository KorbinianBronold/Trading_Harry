from abc import ABC, abstractmethod
from typing import Any
import pandas as pd


class DataProvider(ABC):
    @abstractmethod
    def get_price_history(self, ticker: str, days: int = 90) -> pd.DataFrame | None:
        ...

    @abstractmethod
    def get_fundamentals(self, ticker: str) -> dict:
        ...

    @abstractmethod
    def get_earnings_calendar(self, ticker: str) -> dict:
        ...

    @abstractmethod
    def get_last_available_date(self, ticker: str) -> str | None:
        ...

    @abstractmethod
    def get_ohlc_after(
        self, ticker: str, start_date: str, end_date: str,
    ) -> pd.DataFrame | None:
        """Daily OHLC bars inclusive [start_date, end_date]. None if empty."""
        ...
