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


@pytest.mark.parametrize("yf_ticker,expected_epic", [
    ("GC=F",    "GOLD"),
    ("SI=F",    "SILVER"),
    ("CL=F",    "OIL_CRUDE"),
    ("BTC-USD", "BTCUSD"),
    ("ETH-USD", "ETHUSD"),
    ("SOL-USD", "SOLUSD"),
    ("XRP-USD", "XRPUSD"),
    ("BRK-B",   "BRKB"),
])
def test_ticker_map_all_epics(monkeypatch, yf_ticker, expected_epic):
    monkeypatch.setattr("requests.post", _mock_post)
    called = []
    def _capture(url, **kwargs):
        called.append(url)
        return _mock_prices_get(url, **kwargs)
    monkeypatch.setattr("requests.get", _capture)
    from src.providers.capital_provider import CapitalComProvider
    CapitalComProvider().get_price_history(yf_ticker, days=5)
    assert any(expected_epic in u for u in called), \
        f"Expected epic '{expected_epic}' in request URL, got: {called}"


def test_auth_failed_flag_skips_all_subsequent_calls(monkeypatch):
    post_calls = []
    def _failing_post(url, **kwargs):
        post_calls.append(url)
        m = MagicMock()
        m.raise_for_status.side_effect = Exception("401 Unauthorized")
        m.headers = {}
        return m
    monkeypatch.setattr("requests.post", _failing_post)
    from src.providers.capital_provider import CapitalComProvider
    p = CapitalComProvider()
    assert p.get_price_history("AAPL") is None   # first call → auth fails
    assert p.get_price_history("MSFT") is None   # second call → skipped via _auth_failed
    assert len(post_calls) == 1, "Session POST should only be attempted once"


def test_get_ohlc_after_same_day_steps_from_back(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    captured = {}
    def _capture(url, **kwargs):
        captured.update(kwargs.get("params", {}))
        return _mock_prices_get(url, **kwargs)
    monkeypatch.setattr("requests.get", _capture)
    from src.providers.capital_provider import CapitalComProvider
    CapitalComProvider().get_ohlc_after("AAPL", "2026-05-22", "2026-05-22")
    assert captured.get("from") == "2026-05-21T00:00:00", \
        f"Expected 'from' stepped back 1 day, got: {captured.get('from')}"
    assert captured.get("to") == "2026-05-22T00:00:00"


# ---------- max-Deckel der Prices-API ----------

def test_get_price_history_clamps_days_to_api_maximum(monkeypatch):
    """Capital.com beantwortet max>1000 mit HTTP 400.

    Regression: historical_loader forderte 1095 Tage an und bekam fuer JEDEN
    Ticker einen 400er — der dokumentierte Setup-Pull schrieb 0 Zeilen, ohne
    dass der Fehler als solcher sichtbar wurde.
    """
    monkeypatch.setattr("requests.post", _mock_post)
    captured = {}

    def _capture(url, **kwargs):
        captured.update(kwargs.get("params", {}))
        return _mock_prices_get(url, **kwargs)

    monkeypatch.setattr("requests.get", _capture)
    from src.providers.capital_provider import CapitalComProvider, MAX_BARS_PER_REQUEST
    CapitalComProvider().get_price_history("AAPL", days=1095)
    assert captured["max"] == MAX_BARS_PER_REQUEST == 1000


def test_get_price_history_leaves_small_day_counts_untouched(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    captured = {}

    def _capture(url, **kwargs):
        captured.update(kwargs.get("params", {}))
        return _mock_prices_get(url, **kwargs)

    monkeypatch.setattr("requests.get", _capture)
    from src.providers.capital_provider import CapitalComProvider
    CapitalComProvider().get_price_history("AAPL", days=200)
    assert captured["max"] == 200


# ---------- search_markets (Sprint 3B / Plan 1, Task 1) ----------

_MARKETS = {
    "markets": [
        {
            "epic": "XLK",
            "instrumentName": "Technology Select Sector SPDR Fund",
            "instrumentType": "SHARES",
            "marketStatus": "TRADEABLE",
        }
    ]
}


def _mock_markets_get(url, **kwargs):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = _MARKETS
    return m


def test_search_markets_returns_market_dicts(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    monkeypatch.setattr("requests.get", _mock_markets_get)
    from src.providers.capital_provider import CapitalComProvider
    assert CapitalComProvider().search_markets("XLK") == _MARKETS["markets"]


def test_search_markets_passes_search_term_as_param(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    captured = {}

    def _capture(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs.get("params", {}))
        return _mock_markets_get(url, **kwargs)

    monkeypatch.setattr("requests.get", _capture)
    from src.providers.capital_provider import CapitalComProvider
    CapitalComProvider().search_markets("SOXX")
    assert captured.get("searchTerm") == "SOXX"
    assert captured["url"].endswith("/api/v1/markets")


def test_search_markets_returns_empty_list_on_error(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)

    def _boom(url, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("requests.get", _boom)
    from src.providers.capital_provider import CapitalComProvider
    assert CapitalComProvider().search_markets("XLK") == []


# ---------- Sub-Sektor-ETF-Konstanten ----------

def test_every_sub_sector_etf_and_vix_maps_to_a_non_empty_epic():
    """Jedes ETF-Symbol und der VIX müssen über _map() auf ein nicht-leeres Epic
    zeigen — entweder identisch oder über einen TICKER_MAP-Eintrag."""
    import config
    from src.providers.capital_provider import CapitalComProvider
    provider = CapitalComProvider()
    for symbol in list(config.SUB_SECTOR_ETFS.values()) + [config.VIX_TICKER]:
        epic = provider._map(symbol)
        assert isinstance(epic, str) and epic, f"{symbol} maps to empty epic"


def test_sub_sector_etfs_are_complete_and_consistent():
    import config
    assert len(config.SUB_SECTOR_ETFS) == 21
    assert all(config.SUB_SECTOR_ETFS.values()), "kein Sub-Sektor ohne ETF"
    # Jeder Sub-Sektor-Name muss sich selbst über SECTOR_ALIASES auflösen lassen,
    # sonst wäre er per Finnhub-Wert nie erreichbar.
    for name in config.SUB_SECTOR_ETFS:
        assert config.SECTOR_ALIASES.get(name) == name, f"{name} fehlt in SECTOR_ALIASES"


def test_every_sector_alias_target_is_a_known_sub_sector():
    import config
    unknown = {
        target for target in config.SECTOR_ALIASES.values()
        if target not in config.SUB_SECTOR_ETFS
    }
    assert not unknown, f"SECTOR_ALIASES zeigt auf unbekannte Sub-Sektoren: {unknown}"
