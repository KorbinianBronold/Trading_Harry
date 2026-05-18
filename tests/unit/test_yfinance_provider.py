import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from src.providers.yfinance_provider import YFinanceProvider


def _make_hist_df(rows: int = 60) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=rows, freq="B")
    return pd.DataFrame({
        "Open":  [100 + i * 0.5 for i in range(rows)],
        "High":  [101 + i * 0.5 for i in range(rows)],
        "Low":   [ 99 + i * 0.5 for i in range(rows)],
        "Close": [100 + i * 0.5 for i in range(rows)],
        "Volume":[1_000_000 + i * 1000 for i in range(rows)],
    }, index=idx)


def test_get_price_history_returns_dataframe():
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = _make_hist_df(60)

    with patch("yfinance.Ticker", return_value=fake_ticker), \
         patch("time.sleep"):  # no real delays in tests
        p = YFinanceProvider()
        df = p.get_price_history("AAPL", days=90)

    assert df is not None
    assert "Close" in df.columns
    assert len(df) == 60


def test_get_price_history_returns_none_on_insufficient_data():
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = _make_hist_df(10)  # < 20 → reject

    with patch("yfinance.Ticker", return_value=fake_ticker), \
         patch("time.sleep"):
        p = YFinanceProvider()
        df = p.get_price_history("AAPL", days=90)

    assert df is None


def test_get_price_history_retries_on_error():
    fake_ticker = MagicMock()
    fake_ticker.history.side_effect = [
        Exception("transient"),
        _make_hist_df(60),
    ]

    with patch("yfinance.Ticker", return_value=fake_ticker), \
         patch("time.sleep"):
        p = YFinanceProvider()
        df = p.get_price_history("AAPL", days=90)

    assert df is not None
    assert fake_ticker.history.call_count == 2


def test_get_fundamentals_extracts_known_fields():
    fake_ticker = MagicMock()
    fake_ticker.info = {
        "trailingPE": 28.4, "forwardPE": 26.2,
        "marketCap": 2_800_000_000_000,
        "debtToEquity": 145.0,
        "sector": "Technology",
        "targetMeanPrice": 195.0, "currentPrice": 180.0,
        "recommendationKey": "buy",
    }

    with patch("yfinance.Ticker", return_value=fake_ticker), \
         patch("time.sleep"):
        p = YFinanceProvider()
        f = p.get_fundamentals("AAPL")

    assert f["pe_ratio"] == 28.4
    assert f["forward_pe"] == 26.2
    assert f["market_cap_b"] == 2800.0
    assert f["sector"] == "Technology"
    assert f["consensus"] == "buy"
    assert f["analyst_upside"] == pytest.approx((195 - 180) / 180 * 100)
