"""Tests fuer src/universe.py — die eine Quelle dafuer, welche Ticker das System
ueberhaupt anfasst.

Hintergrund: der Bootstrap-Lauf (historical_loader), final_close und der
Historien-Guard brauchen alle dieselbe Liste. Solange jeder sie selbst
zusammenbaut, faellt ein neu aufgenommener Ticker irgendwo durch — genau der
Fall, der am 2026-08-04 drei gruene, aber leere Laeufe erzeugt hat.
"""
import config
from src.universe import full_universe


def test_full_universe_covers_stocks_commodities_crypto_and_etfs(mocker):
    """Das Universum ist die Vereinigung aller vier Gruppen — fehlt eine, laeuft
    der Bootstrap an ihr vorbei und die Pipeline skippt sie spaeter mangels Bars."""
    mocker.patch.object(config, "SP500_MVP_TICKERS", ["AAPL"])
    mocker.patch.object(config, "USE_FULL_SP500", False)
    mocker.patch.object(config, "COMMODITY_TICKERS", {"Gold": "GC=F"})
    mocker.patch.object(config, "CRYPTO_TICKERS", {"Bitcoin": "BTC-USD"})
    mocker.patch.object(config, "SUB_SECTOR_ETFS", {"Semis": "SOXX"})

    assert set(full_universe()) == {"AAPL", "GC=F", "BTC-USD", "SOXX"}


def test_full_universe_follows_use_full_sp500(mocker):
    """Bei USE_FULL_SP500=True zieht der Bootstrap die grosse Liste — sonst
    haette Sprint 3F 480 Ticker ohne Historie."""
    mocker.patch.object(config, "SP500_MVP_TICKERS", ["AAPL"])
    mocker.patch.object(config, "SP500_FULL_TICKERS", ["AAPL", "TSLA", "NFLX"])
    mocker.patch.object(config, "USE_FULL_SP500", True)
    mocker.patch.object(config, "COMMODITY_TICKERS", {})
    mocker.patch.object(config, "CRYPTO_TICKERS", {})
    mocker.patch.object(config, "SUB_SECTOR_ETFS", {})

    assert set(full_universe()) == {"AAPL", "TSLA", "NFLX"}


def test_full_universe_has_no_duplicates(mocker):
    """Mehrere Sub-Sektoren teilen sich einen ETF (MedTech/Pharma -> XLV). Ein
    doppelter Eintrag wuerde den Ticker zweimal laden — verschwendete Calls."""
    mocker.patch.object(config, "SP500_MVP_TICKERS", ["AAPL"])
    mocker.patch.object(config, "USE_FULL_SP500", False)
    mocker.patch.object(config, "COMMODITY_TICKERS", {})
    mocker.patch.object(config, "CRYPTO_TICKERS", {})
    mocker.patch.object(config, "SUB_SECTOR_ETFS",
                        {"MedTech": "XLV", "Pharma": "XLV", "Rest": "XLV"})

    universe = full_universe()
    assert len(universe) == len(set(universe))
    assert universe.count("XLV") == 1


def test_full_universe_is_deterministic(mocker):
    """Zwei Aufrufe liefern dieselbe Reihenfolge — sonst ist ein Loader-Lauf
    nicht reproduzierbar und Logs lassen sich nicht vergleichen."""
    mocker.patch.object(config, "SUB_SECTOR_ETFS",
                        {"A": "XLU", "B": "SOXX", "C": "XLF"})
    assert full_universe() == full_universe()


def test_real_universe_contains_the_known_groups():
    """Gegen die echte Config: alle vier Gruppen sind vertreten. Faengt ein
    versehentliches Leeren einer Liste in config.py."""
    universe = set(full_universe())
    assert {"AAPL", "MSFT"} <= universe          # Aktien
    assert {"GC=F", "CL=F"} <= universe          # Rohstoffe
    assert {"BTC-USD", "ETH-USD"} <= universe    # Krypto
    assert {"SOXX", "XLK"} <= universe           # Sub-Sektor-ETFs
