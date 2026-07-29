import sqlite3
import pytest
from pathlib import Path

# --- Live-Tests -------------------------------------------------------------
# Tests mit @pytest.mark.live_email verschicken eine ECHTE E-Mail ueber SendGrid.
# Sie laufen deshalb nur, wenn --run-live-email ausdruecklich gesetzt ist. Ohne
# das Flag werden sie uebersprungen, damit `pytest tests/` niemals ungefragt
# Post verschickt — weder lokal noch im normalen CI-Lauf.


def pytest_addoption(parser):
    """Registriert --run-live-email; ohne dieses Flag bleiben Live-Tests aus."""
    parser.addoption(
        "--run-live-email", action="store_true", default=False,
        help="Live-Tests ausfuehren, die echte E-Mails ueber SendGrid verschicken",
    )


def pytest_configure(config):
    """Meldet den live_email-Marker an, damit --strict-markers nicht stolpert."""
    config.addinivalue_line(
        "markers",
        "live_email: verschickt eine echte E-Mail; braucht --run-live-email",
    )


def pytest_collection_modifyitems(config, items):
    """Ueberspringt alle live_email-Tests, solange --run-live-email fehlt."""
    if config.getoption("--run-live-email"):
        return
    skip = pytest.mark.skip(
        reason="Live-Mailversand: nur mit --run-live-email (verschickt echte Post)"
    )
    for item in items:
        if "live_email" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def in_memory_db():
    """Fresh in-memory SQLite per test."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """A file-based SQLite path that lives only for the test."""
    return tmp_path / "test.db"


@pytest.fixture
def sample_ticker_data() -> dict:
    """Realistic single-ticker payload as produced by data_collector."""
    return {
        "ticker": "AAPL",
        "price": 178.50,
        "price_change_1d": 1.2,
        "price_change_5d": 3.4,
        "price_change_1m": 5.6,
        "price_change_3m": 12.3,
        "rsi_14": 58.4,
        "rsi_trend": "rising",
        "macd_signal": "bullish_cross",
        "atr_pct": 1.8,
        "bb_position": 0.62,
        "above_sma20": 2.1,
        "above_sma50": 5.4,
        "above_sma200": 12.8,
        "volume_ratio": 1.15,
        "pe_ratio": 28.4,
        "forward_pe": 26.2,
        "analyst_target_upside": 8.5,
        "analyst_consensus": "Buy",
        "market_cap_b": 2800.0,
        "debt_equity": 1.45,
        "sector": "Technology",
        "earnings_in_days": 14,
        "earnings_beat_pct": 4.2,
        "data_quality": "high",
    }
