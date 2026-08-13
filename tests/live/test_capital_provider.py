"""Batch-Live-Kurs-Abruf: get_premarket_prices_batch() (Spec 4.3.1 / 4.3.3).

Testet Chunking und die 429-Notbremse von CapitalComProvider.get_premarket_prices_batch().
Liegt unter tests/live/ und traegt @pytest.mark.live_api wie jede andere Datei
in diesem Ordner (braucht --run-live, s. tests/conftest.py) -- fachlich gehoert
der Test zur Live-Kurs-Anbindung, auch wenn die HTTP-Schicht hier komplett
gemockt ist und kein echter Call stattfindet. Der eigentliche Live-Check (macht
der Sammelabruf wirklich mit, liefert er ein offer-Feld?) laeuft separat und
read-only ueber setup/probe_epics_batch.py --run-live.
"""
import logging

import pytest

pytestmark = pytest.mark.live_api


class _Resp:
    """Minimaler Fake fuer requests.Response -- nur was der Batch-Code liest."""

    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json = json_data or {}
        self.headers = headers or {}

    def json(self):
        return self._json


def _market(epic: str, bid: float | None, offer: float | None = None) -> dict:
    snap = {}
    if bid is not None:
        snap["bid"] = bid
    if offer is not None:
        snap["offer"] = offer
    return {"instrument": {"epic": epic}, "snapshot": snap}


def _provider(monkeypatch):
    from src.providers.capital_provider import CapitalComProvider
    prov = CapitalComProvider()
    monkeypatch.setattr(prov, "_headers", lambda: {})
    monkeypatch.setattr(prov, "_map", lambda t: t)  # Ticker == Epic im Test
    return prov


def test_premarket_prices_batch_chunks(monkeypatch):
    """25 Epics -> 2 Calls (20 + 5)."""
    tickers = [f"T{i}" for i in range(25)]
    calls: list[list[str]] = []

    def _fake_get(url, headers=None, params=None, timeout=None):
        epics = params["epics"].split(",")
        calls.append(epics)
        markets = [_market(e, 100.0 + i) for i, e in enumerate(epics)]
        return _Resp(200, {"marketDetails": markets})

    monkeypatch.setattr("src.providers.capital_provider.requests.get", _fake_get)
    prov = _provider(monkeypatch)

    result = prov.get_premarket_prices_batch(tickers, chunk_size=20)

    assert len(calls) == 2, f"Erwartet 2 Calls fuer 25 Epics/Chunk20, bekam {len(calls)}"
    assert len(calls[0]) == 20 and len(calls[1]) == 5
    assert len(result) == 25
    assert result["T0"] == 100.0
    assert result["T24"] == 104.0  # zweiter Chunk, letzter Ticker


def test_premarket_prices_batch_missing_bid_is_none(monkeypatch):
    """Ein Snapshot ohne bid ergibt None im Dict, nicht 0 und nicht Auslassung --
    der Ticker WURDE beantwortet, nur ohne Kurs (Spec 4.3: None statt 0)."""
    def _fake_get(url, headers=None, params=None, timeout=None):
        return _Resp(200, {"marketDetails": [_market("A", None), _market("B", 10.0)]})

    monkeypatch.setattr("src.providers.capital_provider.requests.get", _fake_get)
    prov = _provider(monkeypatch)

    result = prov.get_premarket_prices_batch(["A", "B"], chunk_size=20)
    assert result == {"A": None, "B": 10.0}


def test_premarket_prices_batch_handles_429(monkeypatch):
    """Erster 429 -> Pause (Retry-After-Header) + Chunk einmal wiederholt -> Erfolg."""
    calls: list[str] = []
    sleeps: list[float] = []

    def _fake_get(url, headers=None, params=None, timeout=None):
        calls.append(params["epics"])
        if len(calls) == 1:
            return _Resp(429, {}, headers={"Retry-After": "5"})
        epics = params["epics"].split(",")
        return _Resp(200, {"marketDetails": [_market(e, 42.0) for e in epics]})

    monkeypatch.setattr("src.providers.capital_provider.requests.get", _fake_get)
    monkeypatch.setattr(
        "src.providers.capital_provider.time.sleep", lambda s: sleeps.append(s)
    )
    prov = _provider(monkeypatch)

    result = prov.get_premarket_prices_batch(["A", "B", "C"], chunk_size=20)

    assert len(calls) == 2, "429 dann Retry: genau 2 Calls fuer den einen Chunk"
    assert sleeps == [5.0], "Pause muss den Retry-After-Header uebernehmen"
    assert result == {"A": 42.0, "B": 42.0, "C": 42.0}


def test_premarket_prices_batch_second_429_skips_chunk_without_retry(monkeypatch):
    """Ein Chunk, der auch nach dem einen Retry noch 429 liefert, wird
    uebersprungen (nicht erneut versucht) -- seine Ticker fehlen im Dict."""
    calls: list[str] = []

    def _fake_get(url, headers=None, params=None, timeout=None):
        calls.append(params["epics"])
        return _Resp(429, {}, headers={"Retry-After": "0"})

    monkeypatch.setattr("src.providers.capital_provider.requests.get", _fake_get)
    monkeypatch.setattr("src.providers.capital_provider.time.sleep", lambda s: None)
    prov = _provider(monkeypatch)

    result = prov.get_premarket_prices_batch(["A", "B"], chunk_size=20)

    assert len(calls) == 2, "genau ein Retry, dann Aufgabe fuer diesen Chunk"
    assert result == {}, "kein Ticker aus dem uebersprungenen Chunk im Dict"


def test_premarket_prices_batch_aborts_on_five_consecutive_429s(monkeypatch, caplog):
    """5 aufeinanderfolgende 429 -> Sweep bricht ab, Rest ohne Live-Kurs, WARNING."""
    tickers = [f"T{i}" for i in range(100)]  # 5 Chunks zu 20
    calls: list[str] = []

    def _fake_get(url, headers=None, params=None, timeout=None):
        calls.append(params["epics"])
        return _Resp(429, {}, headers={"Retry-After": "0"})

    monkeypatch.setattr("src.providers.capital_provider.requests.get", _fake_get)
    monkeypatch.setattr("src.providers.capital_provider.time.sleep", lambda s: None)
    prov = _provider(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="shares_future.capital"):
        result = prov.get_premarket_prices_batch(tickers, chunk_size=20)

    assert result == {}, "kein einziger Chunk kam durch"
    assert len(calls) == 5, "nach dem 5. 429 in Folge wird sofort abgebrochen"
    assert any("429" in r.message and "abgebrochen" in r.message for r in caplog.records)


def test_premarket_prices_batch_success_resets_the_429_streak(monkeypatch):
    """Ein Erfolg zwischen zwei 429-Serien reisst die Kette -- die Notbremse
    zaehlt AUFEINANDERFOLGENDE 429, nicht die Gesamtzahl im Lauf."""
    tickers = [f"T{i}" for i in range(140)]  # 7 Chunks zu 20
    calls: list[str] = []

    def _fake_get(url, headers=None, params=None, timeout=None):
        calls.append(params["epics"])
        n = len(calls)
        # Chunk 1: 429, Retry -> 429 (2 Calls, Serie=2, uebersprungen).
        # Chunk 2: 429 (Serie=3, uebersprungen, kein Retry mehr da schon getaktet).
        # Chunk 3: Erfolg -> Serie reisst.
        # Chunk 4+: wieder 429 je einzeln -- darf NICHT vor dem 5. in Folge abbrechen.
        if n in (1, 2, 3):
            return _Resp(429, {}, headers={"Retry-After": "0"})
        if n == 4:
            epics = calls[-1].split(",")
            return _Resp(200, {"marketDetails": [_market(e, 1.0) for e in epics]})
        return _Resp(429, {}, headers={"Retry-After": "0"})

    monkeypatch.setattr("src.providers.capital_provider.requests.get", _fake_get)
    monkeypatch.setattr("src.providers.capital_provider.time.sleep", lambda s: None)
    prov = _provider(monkeypatch)

    result = prov.get_premarket_prices_batch(tickers, chunk_size=20)

    # Chunk 3 (calls 4) kam durch -> seine 20 Ticker sind im Dict.
    assert len(result) == 20
