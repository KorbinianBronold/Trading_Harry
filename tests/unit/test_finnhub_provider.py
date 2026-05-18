from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from src.providers.finnhub_provider import FinnhubProvider


def test_get_earnings_calendar_returns_days_to_next():
    future_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
    fake_client = MagicMock()
    fake_client.earnings_calendar.return_value = {
        "earningsCalendar": [
            {"symbol": "AAPL", "date": future_date,
             "epsActual": None, "epsEstimate": 2.10},
        ]
    }

    with patch("src.providers.finnhub_provider._client", fake_client):
        p = FinnhubProvider()
        out = p.get_earnings_calendar("AAPL")

    assert out["days_to_next"] == 14
    assert out["last_beat_pct"] is None


def test_get_earnings_calendar_handles_empty_response():
    fake_client = MagicMock()
    fake_client.earnings_calendar.return_value = {"earningsCalendar": []}

    with patch("src.providers.finnhub_provider._client", fake_client):
        p = FinnhubProvider()
        out = p.get_earnings_calendar("AAPL")

    assert out == {"days_to_next": None, "last_beat_pct": None}


def test_get_earnings_calendar_handles_api_error():
    fake_client = MagicMock()
    fake_client.earnings_calendar.side_effect = Exception("rate limit")

    with patch("src.providers.finnhub_provider._client", fake_client):
        p = FinnhubProvider()
        out = p.get_earnings_calendar("AAPL")

    assert out == {"days_to_next": None, "last_beat_pct": None}


def test_get_earnings_calendar_returns_beat_pct_when_actual_present():
    past_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    fake_client = MagicMock()
    fake_client.earnings_calendar.return_value = {
        "earningsCalendar": [
            {"symbol": "AAPL", "date": past_date,
             "epsActual": 2.20, "epsEstimate": 2.00},
        ]
    }

    with patch("src.providers.finnhub_provider._client", fake_client):
        p = FinnhubProvider()
        out = p.get_earnings_calendar("AAPL")

    # past beat: actual 2.20 vs estimate 2.00 → +10%
    assert out["last_beat_pct"] == 10.0
