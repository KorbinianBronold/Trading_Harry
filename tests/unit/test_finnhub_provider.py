import pytest
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


def test_get_fundamentals_returns_structured_dict(mocker):
    mock_client = mocker.MagicMock()
    mock_client.company_profile2.return_value = {
        "marketCapitalization": 3_000_000.0,
        "finnhubIndustry": "Technology",
    }
    mock_client.company_basic_financials.return_value = {
        "metric": {
            "peNormalizedAnnual": 25.5,
            "forwardPE": 22.0,
            "totalDebt/totalEquityAnnual": 50.0,
        }
    }
    mock_client.recommendation_trends.return_value = [
        {"buy": 20, "hold": 5, "sell": 2}
    ]
    mock_client.price_target.return_value = {"targetMean": 200.0}

    import src.providers.finnhub_provider as fh
    original = fh._client
    fh._client = mock_client
    try:
        from src.providers.finnhub_provider import FinnhubProvider
        result = FinnhubProvider().get_fundamentals("AAPL")
    finally:
        fh._client = original

    assert result.get("sector") == "Technology"
    assert result.get("pe_ratio") == pytest.approx(25.5)
    assert result.get("market_cap_b") == pytest.approx(3000.0)
    assert result.get("consensus") == "buy"


def test_get_fundamentals_no_client_returns_empty():
    import src.providers.finnhub_provider as fh
    original = fh._client
    fh._client = None
    try:
        result = fh.FinnhubProvider().get_fundamentals("AAPL")
    finally:
        fh._client = original
    assert result == {}
