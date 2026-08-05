"""Schutz um die Live-Tests herum.

Die Tests in tests/live/ sprechen echte APIs an und verschicken echte Post.
Diese Tests stellen sicher, dass ein normaler `pytest tests/`-Lauf das niemals
ungefragt tut und dass die Actions-Verdrahtung vollstaendig bleibt."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFTEST = (ROOT / "tests" / "conftest.py").read_text()
LIVE_MAIL = (ROOT / "tests" / "live" / "test_email_delivery.py").read_text()
LIVE_API = (ROOT / "tests" / "live" / "test_api_connectivity.py").read_text()
WORKFLOW = (ROOT / ".github" / "workflows" / "test.yml").read_text()

# Jeder Key, den die Pipeline braucht, muss live geprueft werden.
REQUIRED_SECRETS = (
    "ANTHROPIC_API_KEY", "FINNHUB_API_KEY",
    "CAPITAL_COM_API_KEY", "CAPITAL_COM_IDENTIFIER", "CAPITAL_COM_PASSWORD",
    "RESEND_API_KEY", "EMAIL_FROM", "EMAIL_TO",
)


def test_live_tests_are_skipped_without_the_flag():
    """Der Standardlauf darf weder telefonieren noch Mail verschicken."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/live", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=120,
    )
    assert proc.returncode == 0, f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    assert "passed" not in proc.stdout, (
        f"Ein Live-Test lief ohne --run-live durch:\n{proc.stdout}"
    )
    assert "skipped" in proc.stdout, proc.stdout


def test_flag_and_markers_are_wired_in_conftest():
    assert "--run-live" in CONFTEST
    assert "live_api" in CONFTEST
    assert "live_email" in CONFTEST
    assert "pytest_collection_modifyitems" in CONFTEST


def test_read_only_checks_and_the_send_use_different_markers():
    """Sonst laesst sich die Verbindung nicht pruefen, ohne Post zu verschicken —
    und ein leeres Kontingent waere nicht von einem kaputten Key zu trennen."""
    assert "@pytest.mark.live_email" in LIVE_MAIL
    assert "@pytest.mark.live_api" in LIVE_API
    assert "@pytest.mark.live_email" not in LIVE_API


def test_every_external_service_has_a_connectivity_check():
    for needle in ("anthropic", "finnhub", "capital", "resend"):
        assert needle in LIVE_API.lower(), f"Keine Live-Pruefung fuer {needle}"


def test_body_text_is_exactly_what_was_asked_for():
    assert 'BODY = "Test Versand erfolgreich"' in LIVE_MAIL


def test_workflow_runs_live_checks_on_every_push():
    """'Bei jeder Aenderung' heisst: an jedem Push, nicht nur auf main."""
    assert "live-api-checks:" in WORKFLOW
    assert "--run-live" in WORKFLOW
    assert 'branches: ["**"]' in WORKFLOW


def test_workflow_passes_every_secret_the_checks_need():
    for name in REQUIRED_SECRETS:
        assert f"secrets.{name}" in WORKFLOW, f"Secret {name} fehlt in test.yml"


def test_workflow_runs_the_send_even_if_connections_fail():
    """Sonst verdeckt ein einzelner kaputter Provider den Mail-Status."""
    send_step = WORKFLOW.split("Send test email")[1]
    assert "if: always()" in WORKFLOW.split("Send test email")[0][-400:] \
        or "if: always()" in send_step[:200]


def test_default_test_job_does_not_enable_live_runs():
    """Der Coverage-Job darf die Live-Tests nicht mitziehen."""
    job = WORKFLOW.split("live-api-checks:")[0]
    assert "--run-live" not in job


def test_guard_blocks_a_direct_post():
    """Der Mailversand-Endpunkt ist gesperrt und die Meldung nennt die Adresse."""
    import pytest
    import requests

    with pytest.raises(RuntimeError, match="Ungemockter POST-Aufruf"):
        requests.post("https://api.resend.com/emails", json={"to": "x@example.com"})


def test_guard_blocks_a_direct_get():
    """Auch lesende Fremdaufrufe sind gesperrt — nicht nur der Mailversand.

    Genau diese Luecke kostete Zeit: ein Unit-Test baute eine echte
    Capital.com-Session auf, der Fehler wurde intern geschluckt, der Test blieb
    gruen. Ein reiner Mail-Schutz haette das nie gemeldet."""
    import pytest
    import requests

    with pytest.raises(RuntimeError, match="Ungemockter GET-Aufruf"):
        requests.get("https://demo-api-capital.backend-capital.com/api/v1/prices/AAPL")


def test_guard_message_names_the_called_address():
    """Wer an einem Kursanbieter-Problem sitzt, darf nicht in die
    Mail-Dokumentation geschickt werden."""
    import pytest
    import requests

    with pytest.raises(RuntimeError, match="finnhub.io"):
        requests.get("https://finnhub.io/api/v1/quote")


def test_guard_blocks_send_daily_email_without_mock():
    """Ungemockter Versand schlaegt fehl, statt echte Post zu verschicken."""
    import pytest
    from src.email_sender import send_daily_email, EmailSendError

    payload = {
        "date": "2026-01-01", "run_type": "test",
        "top_long": [], "top_short": [], "portfolio_recs": [], "trends": [],
        "commodities_crypto": [], "cost_summary": {},
        "yesterday_outcomes": {}, "skipped_tickers": [],
    }
    with pytest.raises(EmailSendError, match="Ungemockter POST-Aufruf"):
        send_daily_email(payload, "test-key", "from@test.com", "to@test.com")


def test_guard_blocks_a_requests_session():
    """Die Sperre lag auf requests.get/post — der finnhub-SDK ruft aber
    self._session.get() auf und lief damit komplett daran vorbei.

    Genau diese Bauart hat schon zweimal echte Fremdaufrufe aus Unit-Tests
    gelassen; ein Schutz, der nur die Modulfunktionen kennt, ist keiner."""
    import pytest
    import requests

    with pytest.raises(RuntimeError, match="Ungemockter"):
        requests.Session().get("https://finnhub.io/api/v1/stock/profile2")


def test_guard_blocks_httpx_the_anthropic_transport():
    """Der teuerste Pfad ueberhaupt war ungeschuetzt: das Anthropic-SDK
    transportiert ueber httpx, nicht ueber requests. Mit einem
    ANTHROPIC_API_KEY in der .env -- config.py ruft load_dotenv() -- macht jeder
    Test, der call_claude() zu mocken vergisst, echte und abgerechnete Calls."""
    import pytest
    import httpx

    with pytest.raises(RuntimeError, match="Ungemockter"):
        httpx.Client().get("https://api.anthropic.com/v1/messages")


def test_guard_covers_every_requests_verb():
    """PUT/DELETE/PATCH waren nie gesperrt."""
    import pytest
    import requests

    for verb in ("put", "delete", "patch", "head"):
        with pytest.raises(RuntimeError, match="Ungemockter"):
            getattr(requests, verb)("https://api.resend.com/emails")


def test_guard_blocks_the_real_call_claude_path():
    """Der teure Pfad, End-to-End geprueft.

    Die httpx-Sperre allein genuegt nicht: sie verhindert den Aufruf zwar, aber
    das Anthropic-SDK faengt die Exception und wirft sie als
    APIConnectionError('Connection error.') neu. Die Meldung der Sperre ginge
    verloren -- der Entwickler saehe nur 'Connection error.' und wuesste nicht,
    warum. Genau dieses Verschlucken hat den zweiten Vorfall so lange verdeckt.
    Deshalb wird der Client zusaetzlich direkt stillgelegt."""
    import pytest
    from src.utils import call_claude

    with pytest.raises(RuntimeError, match="Ungemockter POST-Aufruf"):
        call_claude(model="claude-haiku-4-5-20251001", system="s", user="u")
