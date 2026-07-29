"""Live-Test des Mailversands — verschickt eine ECHTE E-Mail.

Zweck: laufend belegen, dass die SendGrid-Zustellung funktioniert, statt es erst
im naechsten Produktionslauf zu merken. Der Anlass ist konkret: am 2026-07-29
lief ein vollstaendiger `pre_market` fuer 3,31 EUR durch und scheiterte erst
beim Versand mit HTTP 401 — der Key war abgelaufen, ohne dass es jemand wusste.

Laeuft NUR mit `--run-live-email` (s. tests/conftest.py). Ein normaler
`pytest tests/`-Lauf ueberspringt ihn, damit weder lokal noch im CI ungefragt
Post rausgeht.

Zwei Aufrufwege, die BEWUSST verschiedene Dinge pruefen:
  lokal   : Key aus .env        -> `pytest tests/live --run-live-email`
  Actions : Key aus dem Secret  -> .github/workflows/test.yml, Job email-delivery
Beide Werte sind unabhaengig voneinander und koennen einzeln ablaufen. Nur der
Secret-Wert entscheidet daraeber, ob im Produktivbetrieb Mails ankommen."""
import logging
import os

import pytest

import config
from src.email_sender import _send, EmailSendError

log = logging.getLogger("shares_future.live_email")

SUBJECT = "Trading_Harry — Test-Versand"
BODY = "Test Versand erfolgreich"


def _report(line: str) -> None:
    """Schreibt eine Ergebniszeile ins Log und, falls unter GitHub Actions, in
    die Job-Zusammenfassung — dort ist sie ohne Log-Suche sichtbar."""
    log.info(line)
    print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


@pytest.mark.live_email
def test_sends_test_email():
    """Verschickt eine echte Mail mit dem Text 'Test Versand erfolgreich' und
    protokolliert Erfolg oder Fehlschlag."""
    quelle = "GitHub Secret" if os.environ.get("GITHUB_ACTIONS") else ".env (lokal)"
    fehlend = [
        name for name, wert in (
            ("SENDGRID_API_KEY", config.SENDGRID_API_KEY),
            ("EMAIL_FROM", config.EMAIL_FROM),
            ("EMAIL_TO", config.EMAIL_TO),
        ) if not wert
    ]
    if fehlend:
        # Bewusst ein Fehler, kein Skip: wer --run-live-email setzt, will einen
        # Versand sehen. Ein stiller Skip wuerde genau das verschleiern.
        _report(f"❌ Test-Versand NICHT moeglich — fehlende Werte aus {quelle}: "
                f"{', '.join(fehlend)}")
        pytest.fail(f"Fehlende Mail-Credentials aus {quelle}: {', '.join(fehlend)}")

    try:
        _send(
            api_key=config.SENDGRID_API_KEY,
            email_from=config.EMAIL_FROM,
            email_to=config.EMAIL_TO,
            subject=SUBJECT,
            html_body=BODY,
        )
    except (EmailSendError, Exception) as e:      # noqa: B014 - Zustellung darf alles werfen
        _report(f"❌ Test-Versand FEHLGESCHLAGEN (Key aus {quelle}) "
                f"an {config.EMAIL_TO}: {type(e).__name__}: {e}")
        raise

    _report(f"✅ Test-Versand erfolgreich (Key aus {quelle}) an {config.EMAIL_TO}")
