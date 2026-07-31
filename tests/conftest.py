import sqlite3
import pytest
from pathlib import Path

# --- Live-Tests -------------------------------------------------------------
# Tests unter tests/live/ sprechen echte Fremdsysteme an. Sie laufen nur mit
# --run-live, damit `pytest tests/` niemals ungefragt nach draussen telefoniert.
#
# Zwei Marker, weil sich die Nebenwirkungen unterscheiden:
#   live_api   — rein lesende Verbindungspruefung, keine sichtbare Wirkung
#   live_email — verschickt echte Post und verbraucht Versandkontingent
# So laesst sich die Verbindung pruefen, ohne sich selbst zuzuspammen:
#   pytest tests/live --run-live -m live_api
LIVE_MARKERS = ("live_api", "live_email")


def pytest_addoption(parser):
    """Registriert --run-live; ohne dieses Flag bleiben alle Live-Tests aus."""
    parser.addoption(
        "--run-live", action="store_true", default=False,
        help="Live-Tests gegen echte APIs ausfuehren (Verbindung + Mailversand)",
    )


def pytest_configure(config):
    """Meldet die Live-Marker an, damit --strict-markers nicht stolpert."""
    config.addinivalue_line(
        "markers", "live_api: echte, lesende API-Verbindungspruefung; braucht --run-live",
    )
    config.addinivalue_line(
        "markers", "live_email: verschickt eine echte E-Mail; braucht --run-live",
    )


def pytest_collection_modifyitems(config, items):
    """Ueberspringt alle Live-Tests, solange --run-live fehlt."""
    if config.getoption("--run-live"):
        return
    skip = pytest.mark.skip(
        reason="Live-Test gegen echte APIs: nur mit --run-live"
    )
    for item in items:
        if any(m in item.keywords for m in LIVE_MARKERS):
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


@pytest.fixture(autouse=True)
def _block_outgoing_http(monkeypatch, request):
    """Sperrt jeden ausgehenden HTTP-Aufruf ausserhalb von tests/live/.

    Deckt bewusst ALLE Fremdsysteme ab, nicht nur den Mailversand: Kursanbieter,
    Fundamentaldaten und Mail laufen im Produktivcode saemtlich ueber
    requests.get / requests.post (geprueft, es gibt keinen weiteren Einstieg --
    kein Session-Objekt, kein urllib, kein httpx).

    Anlass: zwei reale Vorfaelle. Erst gingen aus einem gewoehnlichen Testlauf
    echte Mails an die private Adresse raus, weil ein neuer Sendepfad nicht
    gemockt war. Danach baute ein Unit-Test eine echte Capital.com-Session auf,
    weil run_close() seit B.6 echten Sammelcode ausfuehrt -- der Fehler wurde
    intern geschluckt, der Test blieb gruen, und niemand haette es bemerkt.

    Ausgenommen sind nur Tests mit den Markern 'live_api' oder 'live_email';
    die laufen ohnehin ausschliesslich mit --run-live."""
    if any(m in request.keywords for m in LIVE_MARKERS):
        return

    def _blocked(verb: str):
        """Baut den Ersatz fuer requests.<verb>, der die Zieladresse nennt."""
        def _fail(*args, **kwargs):
            url = args[0] if args else kwargs.get("url", "<unbekannte Adresse>")
            raise RuntimeError(
                f"Ungemockter {verb}-Aufruf an {url} blockiert.\n"
                "Tests ausserhalb von tests/live/ duerfen nicht nach draussen "
                "telefonieren -- weder Mail verschicken noch Kurse, "
                "Fundamentaldaten oder Kontostaende abrufen.\n"
                "Moegliche Loesungen:\n"
                "  - die aufrufende Funktion mocken (z.B. main.collect)\n"
                "  - den Provider mocken (z.B. main.CapitalComProvider)\n"
                "  - die Versandfunktion mocken (z.B. src.email_sender._send)\n"
                "  - oder gezielt requests.get / requests.post patchen\n"
                "Ein echter Fremdsystem-Test gehoert nach tests/live/ und traegt "
                "den Marker live_api oder live_email."
            )
        return _fail

    monkeypatch.setattr("requests.get", _blocked("GET"))
    monkeypatch.setattr("requests.post", _blocked("POST"))


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
