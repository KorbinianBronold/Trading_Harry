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
