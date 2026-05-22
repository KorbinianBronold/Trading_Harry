import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date, timedelta


def _multi_day_df(days: int = 756) -> pd.DataFrame:
    dates = pd.date_range(start="2023-01-02", periods=days, freq="B")
    return pd.DataFrame(
        {
            "Open":   [100.0] * days,
            "High":   [105.0] * days,
            "Low":    [ 99.0] * days,
            "Close":  [102.0] * days,
            "Volume": [1_000_000] * days,
        },
        index=dates,
    )


def test_load_ticker_history_inserts_rows(tmp_path):
    db_path = str(tmp_path / "test.db")
    import sqlite3
    from src import db
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)
    conn.close()

    with patch("setup.historical_loader.CapitalComProvider") as MockCap:
        MockCap.return_value.get_price_history.return_value = _multi_day_df(756)
        from setup.historical_loader import load_ticker_history
        inserted = load_ticker_history("AAPL", db_path=db_path)

    assert inserted > 0
    conn = sqlite3.connect(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM price_history WHERE ticker='AAPL'"
    ).fetchone()[0]
    conn.close()
    assert count == inserted


def test_load_ticker_history_skips_duplicates(tmp_path):
    db_path = str(tmp_path / "test.db")
    import sqlite3
    from src import db
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)
    conn.close()

    df = _multi_day_df(30)
    with patch("setup.historical_loader.CapitalComProvider") as MockCap:
        MockCap.return_value.get_price_history.return_value = df
        from setup.historical_loader import load_ticker_history
        first  = load_ticker_history("MSFT", db_path=db_path)
        second = load_ticker_history("MSFT", db_path=db_path)

    assert first  == 30
    assert second == 0


def test_load_all_calls_load_ticker_history_per_ticker(mocker):
    mock_load = mocker.patch(
        "setup.historical_loader.load_ticker_history", return_value=100
    )
    from setup.historical_loader import load_all
    load_all(tickers=["AAPL", "MSFT", "NVDA"], db_path=":memory:")
    assert mock_load.call_count == 3


def test_load_ticker_history_returns_zero_on_empty_df(tmp_path):
    db_path = str(tmp_path / "test.db")
    import sqlite3
    from src import db
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)
    conn.close()

    with patch("setup.historical_loader.CapitalComProvider") as MockCap:
        MockCap.return_value.get_price_history.return_value = None
        from setup.historical_loader import load_ticker_history
        result = load_ticker_history("UNKNOWN", db_path=db_path)

    assert result == 0
