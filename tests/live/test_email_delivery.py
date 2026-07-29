"""Live-Test des Mailversands — verschickt eine ECHTE E-Mail.

Anders als die lesenden Pruefungen in test_api_connectivity.py hat dieser Test
eine sichtbare Nebenwirkung und verbraucht SendGrid-Kontingent. Deshalb ein
eigener Marker: `pytest tests/live --run-live -m live_api` prueft alle
Verbindungen, ohne Post zu verschicken.

Anlass: am 2026-07-29 lief ein vollstaendiger `pre_market` fuer 3,31 EUR durch
und scheiterte erst beim Versand. Die Ursache war nicht der Schluessel, sondern
ein Konto ohne Versandkontingent — SendGrid meldet beides als HTTP 401. Genau
deshalb ist der lesende Key-Test von diesem Versand-Test getrennt: schlaegt nur
dieser hier fehl, ist der Schluessel in Ordnung und das Kontingent leer.

Laeuft nur mit `--run-live` (s. tests/conftest.py)."""
import pytest

import config
from src.email_sender import _send

SUBJECT = "Trading_Harry — Test-Versand"
BODY = "Test Versand erfolgreich"


@pytest.mark.live_email
def test_sends_test_email(report, key_source):
    """Verschickt eine echte Mail mit dem Text 'Test Versand erfolgreich' und
    protokolliert Erfolg oder Fehlschlag."""
    fehlend = [
        name for name, wert in (
            ("SENDGRID_API_KEY", config.SENDGRID_API_KEY),
            ("EMAIL_FROM", config.EMAIL_FROM),
            ("EMAIL_TO", config.EMAIL_TO),
        ) if not wert
    ]
    if fehlend:
        # Bewusst ein Fehler, kein Skip: wer --run-live setzt, will einen
        # Versand sehen. Ein stiller Skip wuerde genau das verschleiern.
        report(f"❌ Test-Versand NICHT moeglich — fehlende Werte aus {key_source}: "
               f"{', '.join(fehlend)}")
        pytest.fail(f"Fehlende Mail-Credentials aus {key_source}: {', '.join(fehlend)}")

    try:
        _send(
            api_key=config.SENDGRID_API_KEY,
            email_from=config.EMAIL_FROM,
            email_to=config.EMAIL_TO,
            subject=SUBJECT,
            html_body=BODY,
        )
    except Exception as e:
        report(f"❌ Test-Versand FEHLGESCHLAGEN (Key aus {key_source}) "
               f"an {config.EMAIL_TO}: {type(e).__name__}: {e}")
        raise

    report(f"✅ Test-Versand erfolgreich (Key aus {key_source}) an {config.EMAIL_TO}")
