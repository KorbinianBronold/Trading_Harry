import pytest
from src.providers.paid_provider import PaidProvider


def test_get_price_history_raises():
    with pytest.raises(NotImplementedError, match="Sprint 1"):
        PaidProvider().get_price_history("AAPL")


def test_get_fundamentals_raises():
    with pytest.raises(NotImplementedError, match="Sprint 1"):
        PaidProvider().get_fundamentals("AAPL")


def test_get_earnings_calendar_raises():
    with pytest.raises(NotImplementedError, match="Sprint 1"):
        PaidProvider().get_earnings_calendar("AAPL")


def test_get_last_available_date_raises():
    with pytest.raises(NotImplementedError, match="Sprint 1"):
        PaidProvider().get_last_available_date("AAPL")
