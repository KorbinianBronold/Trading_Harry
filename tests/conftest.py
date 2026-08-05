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


def _refuse(verb: str, url: str) -> RuntimeError:
    """Die eine Fehlermeldung der Sperre — nennt Verb und Zieladresse."""
    return RuntimeError(
        f"Ungemockter {verb}-Aufruf an {url} blockiert.\n"
        "Tests ausserhalb von tests/live/ duerfen nicht nach draussen "
        "telefonieren -- weder Mail verschicken noch Kurse, "
        "Fundamentaldaten, Kontostaende oder Claude-Antworten abrufen.\n"
        "Moegliche Loesungen:\n"
        "  - die aufrufende Funktion mocken (z.B. main.collect)\n"
        "  - den Provider mocken (z.B. main.CapitalComProvider)\n"
        "  - die Versandfunktion mocken (z.B. src.email_sender._send)\n"
        "  - den Claude-Aufruf mocken (z.B. main.revalidate_one)\n"
        "Ein echter Fremdsystem-Test gehoert nach tests/live/ und traegt "
        "den Marker live_api oder live_email."
    )


@pytest.fixture(autouse=True)
def _block_outgoing_http(monkeypatch, request):
    """Sperrt jeden ausgehenden HTTP-Aufruf ausserhalb von tests/live/.

    Die Sperre sitzt auf der TRANSPORT-Ebene, nicht auf den bequemen
    Modulfunktionen. requests.get/post allein zu patchen reichte nachweislich
    nicht:

      * der finnhub-SDK ruft self._session.get() auf einem eigenen
        requests.Session-Objekt auf und lief komplett daran vorbei,
      * das Anthropic-SDK transportiert ueber httpx statt requests -- mit einem
        ANTHROPIC_API_KEY in der .env (config.py ruft load_dotenv()) machte damit
        jeder Test, der call_claude() zu mocken vergass, echte und abgerechnete
        Calls,
      * PUT/DELETE/PATCH/HEAD waren nie gesperrt.

    requests.adapters.HTTPAdapter.send ist der Punkt, durch den JEDER
    requests-Aufruf laeuft -- Modulfunktion wie Session. httpx.Client.send und
    httpx.AsyncClient.send sind das Gegenstueck fuer das Anthropic-SDK.

    Anlass: zwei reale Vorfaelle. Erst gingen aus einem gewoehnlichen Testlauf
    echte Mails an die private Adresse raus, weil ein neuer Sendepfad nicht
    gemockt war. Danach baute ein Unit-Test eine echte Capital.com-Session auf,
    weil run_close() seit B.6 echten Sammelcode ausfuehrt -- der Fehler wurde
    intern geschluckt, der Test blieb gruen, und niemand haette es bemerkt.

    Ausgenommen sind nur Tests mit den Markern 'live_api' oder 'live_email';
    die laufen ohnehin ausschliesslich mit --run-live."""
    if any(m in request.keywords for m in LIVE_MARKERS):
        return

    def _blocked_adapter_send(self, request_obj, *args, **kwargs):
        raise _refuse(getattr(request_obj, "method", "?") or "?",
                      getattr(request_obj, "url", "<unbekannte Adresse>"))

    def _blocked_httpx_send(self, request_obj, *args, **kwargs):
        raise _refuse(getattr(request_obj, "method", "?") or "?",
                      getattr(request_obj, "url", "<unbekannte Adresse>"))

    monkeypatch.setattr(
        "requests.adapters.HTTPAdapter.send", _blocked_adapter_send)
    monkeypatch.setattr("httpx.Client.send", _blocked_httpx_send)
    monkeypatch.setattr("httpx.AsyncClient.send", _blocked_httpx_send)

    # Der Anthropic-Client wird zusaetzlich direkt stillgelegt. Die httpx-Sperre
    # allein verhindert den Aufruf zwar zuverlaessig, aber das SDK FAENGT die
    # Exception und wirft sie als APIConnectionError('Connection error.') neu --
    # die Meldung der Sperre geht verloren, und @retry_with_backoff haengt noch
    # zwei Wartezyklen an jeden solchen Test. Genau dieses Verschlucken war der
    # Grund fuer den zweiten Vorfall. Hier bricht es sofort und lesbar ab.
    import src.utils

    class _BlockedAnthropic:
        class messages:
            @staticmethod
            def create(*args, **kwargs):
                raise _refuse("POST", "https://api.anthropic.com/v1/messages")

    monkeypatch.setattr(src.utils, "_anthropic_client", _BlockedAnthropic())


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
