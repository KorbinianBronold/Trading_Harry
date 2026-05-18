from src.providers.base import DataProvider


class PaidProvider(DataProvider):
    """Stub. Real implementation arrives in Sprint 2 (historical loader)."""

    def get_price_history(self, ticker, days=90):
        raise NotImplementedError("PaidProvider is stubbed in Sprint 1")

    def get_fundamentals(self, ticker):
        raise NotImplementedError("PaidProvider is stubbed in Sprint 1")

    def get_earnings_calendar(self, ticker):
        raise NotImplementedError("PaidProvider is stubbed in Sprint 1")

    def get_last_available_date(self, ticker):
        raise NotImplementedError("PaidProvider is stubbed in Sprint 1")
