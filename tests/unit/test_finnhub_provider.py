import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from freezegun import freeze_time
from src.providers.finnhub_provider import FinnhubProvider

# 23:30 UTC am 21.05. ist in Berlin (CEST, UTC+2) bereits 01:30 am 22.05. — genau die
# Stunden, in denen das Kalenderdatum des Runners von Berlin abweicht. Die Fixture-Daten
# unten sind deshalb hart gesetzt statt aus der Wanduhr abgeleitet: `datetime.now()` haette
# die Erwartung an die Zeitzone des Runners gekoppelt und den Test in UTC-CI rot gemacht,
# obwohl der Provider korrekt rechnet. Der fixierte Zeitpunkt prueft zusaetzlich, dass
# `get_earnings_calendar()` wirklich in Berlin-Zeit rechnet — mit naivem `now()` kaeme 15.
BERLIN_MIDNIGHT_EDGE = "2026-05-21T23:30:00+00:00"   # Berlin: 2026-05-22


@freeze_time(BERLIN_MIDNIGHT_EDGE)
def test_get_earnings_calendar_returns_days_to_next():
    future_date = "2026-06-05"          # 14 Tage nach dem Berliner 2026-05-22
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


@freeze_time(BERLIN_MIDNIGHT_EDGE)
def test_get_earnings_calendar_returns_beat_pct_when_actual_present():
    past_date = "2026-04-22"           # 30 Tage vor dem Berliner 2026-05-22
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


# ---------- Ratenbegrenzung (Sprint 3C / Plan 2, Task 11) ----------


def _empty_client():
    """Fake-Client, dessen Aufrufe Nones/leere Antworten liefern -- die
    Rate-Limiter-Tests interessieren sich nur dafuer, DASS ein Call passiert,
    nicht fuer sein Ergebnis."""
    c = MagicMock()
    c.company_profile2.return_value = {}
    c.company_basic_financials.return_value = {}
    c.recommendation_trends.return_value = []
    c.earnings_calendar.return_value = {"earningsCalendar": []}
    return c


def test_no_sleep_under_the_limit(mocker):
    """Weit unter 60 Calls/min: kein einziger Sleep."""
    sleeps = []
    mocker.patch("src.providers.finnhub_provider.time.sleep",
                 side_effect=lambda s: sleeps.append(s))
    with patch("src.providers.finnhub_provider._client", _empty_client()):
        p = FinnhubProvider()
        for _ in range(5):
            p.get_fundamentals("AAPL")
    assert sleeps == []


def test_sleeps_when_60_calls_already_in_the_current_window(mocker):
    """Der 61. Call innerhalb von 60s muss warten, bis der aelteste der 60
    aus dem Fenster faellt."""
    t = [1_000.0]
    mocker.patch("src.providers.finnhub_provider.time.time", side_effect=lambda: t[0])
    sleeps = []
    mocker.patch("src.providers.finnhub_provider.time.sleep",
                 side_effect=lambda s: sleeps.append(s))
    with patch("src.providers.finnhub_provider._client", _empty_client()):
        p = FinnhubProvider()
        for _ in range(60):
            p.get_fundamentals("AAPL")
        assert sleeps == []          # noch keiner der ersten 60 wartet

        p.get_fundamentals("AAPL")   # der 61.

    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(60.0, abs=0.01)


def test_calls_older_than_the_window_are_evicted(mocker):
    """60 Calls, aber der aelteste liegt schon ausserhalb des 60s-Fensters --
    der 61. darf sofort durch, kein Sleep."""
    t = [1_000.0]
    mocker.patch("src.providers.finnhub_provider.time.time", side_effect=lambda: t[0])
    sleeps = []
    mocker.patch("src.providers.finnhub_provider.time.sleep",
                 side_effect=lambda s: sleeps.append(s))
    with patch("src.providers.finnhub_provider._client", _empty_client()):
        p = FinnhubProvider()
        for _ in range(60):
            p.get_fundamentals("AAPL")
        t[0] += 61.0                 # das aelteste Fenster ist jetzt abgelaufen
        p.get_fundamentals("AAPL")

    assert sleeps == []


def test_get_earnings_calendar_also_respects_the_rate_limit(mocker):
    """Task 11 verlangt beide Finnhub-Methoden gedrosselt, nicht nur
    get_fundamentals()."""
    t = [1_000.0]
    mocker.patch("src.providers.finnhub_provider.time.time", side_effect=lambda: t[0])
    sleeps = []
    mocker.patch("src.providers.finnhub_provider.time.sleep",
                 side_effect=lambda s: sleeps.append(s))
    with patch("src.providers.finnhub_provider._client", _empty_client()):
        p = FinnhubProvider()
        for _ in range(60):
            p.get_earnings_calendar("AAPL")
        p.get_earnings_calendar("AAPL")

    assert len(sleeps) == 1


def test_rate_limiter_state_is_per_instance_not_shared_globally(mocker):
    """Eine zweite FinnhubProvider-Instanz startet mit einem leeren Fenster --
    kein modulweiter State, der Tests oder parallele Instanzen kontaminiert."""
    t = [1_000.0]
    mocker.patch("src.providers.finnhub_provider.time.time", side_effect=lambda: t[0])
    sleeps = []
    mocker.patch("src.providers.finnhub_provider.time.sleep",
                 side_effect=lambda s: sleeps.append(s))
    with patch("src.providers.finnhub_provider._client", _empty_client()):
        p1 = FinnhubProvider()
        for _ in range(60):
            p1.get_fundamentals("AAPL")

        p2 = FinnhubProvider()
        p2.get_fundamentals("AAPL")

    assert sleeps == []


def test_no_client_skips_rate_limiter_entirely(mocker):
    """Ohne API-Key gibt es keinen echten Call -- also auch keinen Grund zu
    drosseln (deckt sich mit dem bestehenden Fruehausstieg)."""
    sleeps = []
    mocker.patch("src.providers.finnhub_provider.time.sleep",
                 side_effect=lambda s: sleeps.append(s))
    import src.providers.finnhub_provider as fh
    original = fh._client
    fh._client = None
    try:
        p = fh.FinnhubProvider()
        for _ in range(70):
            p.get_fundamentals("AAPL")
    finally:
        fh._client = original
    assert sleeps == []
