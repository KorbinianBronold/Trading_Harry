import pytest
from unittest.mock import MagicMock
import pandas as pd

_PRICES = {
    "prices": [
        {
            "snapshotTime": "2026/05/20 00:00:00:000",
            "openPrice":  {"bid": 100.0, "ask": 100.1},
            "highPrice":  {"bid": 105.0, "ask": 105.1},
            "lowPrice":   {"bid":  99.0, "ask":  99.1},
            "closePrice": {"bid": 102.0, "ask": 102.1},
            "lastTradedVolume": 1_000_000,
        }
    ]
}
_AUTH_HEADERS = {"CST": "test_cst", "X-SECURITY-TOKEN": "test_token"}


def _mock_post(url, **kwargs):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.headers = _AUTH_HEADERS
    return m


def _mock_prices_get(url, **kwargs):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = _PRICES
    return m


def test_get_price_history_returns_dataframe(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    monkeypatch.setattr("requests.get", _mock_prices_get)
    from src.providers.capital_provider import CapitalComProvider
    df = CapitalComProvider().get_price_history("AAPL", days=30)
    assert df is not None and not df.empty
    assert set(["Open", "High", "Low", "Close", "Volume"]).issubset(df.columns)


def test_get_price_history_empty_returns_none(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    def _empty(url, **kwargs):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {"prices": []}
        return m
    monkeypatch.setattr("requests.get", _empty)
    from src.providers.capital_provider import CapitalComProvider
    assert CapitalComProvider().get_price_history("AAPL") is None


def test_ticker_mapping_gold_uses_GOLD_epic(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    called = []
    def _capture(url, **kwargs):
        called.append(url)
        return _mock_prices_get(url, **kwargs)
    monkeypatch.setattr("requests.get", _capture)
    from src.providers.capital_provider import CapitalComProvider
    CapitalComProvider().get_price_history("GC=F", days=5)
    assert any("GOLD" in u for u in called), f"GOLD not in {called}"


def test_get_open_positions_maps_direction(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    def _pos(url, **kwargs):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {
            "positions": [{
                "position": {
                    "direction": "BUY", "level": 100.5,
                    "stopLevel": 98.0, "limitLevel": 103.0, "profit": 2.0,
                },
                "market": {"epic": "AAPL", "bid": 101.0},
            }]
        }
        return m
    monkeypatch.setattr("requests.get", _pos)
    from src.providers.capital_provider import CapitalComProvider
    positions = CapitalComProvider().get_open_positions()
    assert len(positions) == 1
    assert positions[0]["ticker"] == "AAPL"
    assert positions[0]["direction"] == "long"
    assert positions[0]["entry_price"] == 100.5


def test_get_premarket_price_returns_bid(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    def _mkt(url, **kwargs):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {"snapshot": {"bid": 150.25, "offer": 150.30}}
        return m
    monkeypatch.setattr("requests.get", _mkt)
    from src.providers.capital_provider import CapitalComProvider
    assert CapitalComProvider().get_premarket_price("AAPL") == 150.25


def test_get_price_history_on_error_returns_none(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    monkeypatch.setattr("requests.get", lambda *a, **k: (_ for _ in ()).throw(Exception("conn refused")))
    from src.providers.capital_provider import CapitalComProvider
    assert CapitalComProvider().get_price_history("AAPL") is None


def test_get_closed_positions_filters_by_action_type(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    def _act(url, **kwargs):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {
            "activities": [
                {
                    "epic": "AAPL", "type": "POSITION",
                    "details": {
                        "direction": "BUY", "level": 102.5, "profit": 2.0,
                        "actions": [{"actionType": "POSITION_CLOSED"}],
                    },
                },
                {
                    "epic": "MSFT", "type": "POSITION",
                    "details": {
                        "direction": "SELL", "level": 200.0, "profit": -1.0,
                        "actions": [{"actionType": "POSITION_OPENED"}],
                    },
                },
            ]
        }
        return m
    monkeypatch.setattr("requests.get", _act)
    from src.providers.capital_provider import CapitalComProvider
    closed = CapitalComProvider().get_closed_positions("2026-05-21")
    assert len(closed) == 1
    assert closed[0]["ticker"] == "AAPL"
