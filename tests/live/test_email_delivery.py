"""Live-Test des Mailversands — verschickt eine ECHTE E-Mail.

Anders als die lesenden Pruefungen in test_api_connectivity.py hat dieser Test
eine sichtbare Nebenwirkung und verbraucht Versandkontingent. Deshalb ein
eigener Marker: `pytest tests/live --run-live -m live_api` prueft alle
Verbindungen, ohne Post zu verschicken.

Anlass: am 2026-07-29 lief ein vollstaendiger `pre_market` fuer 3,31 EUR durch
und scheiterte erst beim Versand. Die Ursache war nicht der Schluessel, sondern
ein Konto ohne Versandkontingent beim Vorgaenger-Anbieter, der beides als
HTTP 401 meldete. Genau deshalb ist der lesende Key-Test von diesem Versand-Test
getrennt: schlaegt nur dieser hier fehl, liegt es an Kontingent oder Absender.

Laeuft nur mit `--run-live` (s. tests/conftest.py)."""
import time

import pytest
import requests

import config
from src.email_sender import _send

# Resend nimmt die Mail mit 2xx an und stellt danach asynchron zu. Diese Zustaende
# gelten als endgueltiger Fehlschlag; alles andere (queued, sent, delivered) als ok.
FAILURE_EVENTS = {"failed", "bounced", "complained"}
POLL_WAITS = (2, 3, 5, 8)

SUBJECT = "Trading_Harry — Test-Versand"
BODY = "Test Versand erfolgreich"


@pytest.mark.live_email
def test_sends_test_email(report, key_source):
    """Verschickt eine echte Mail mit dem Text 'Test Versand erfolgreich' und
    protokolliert Erfolg oder Fehlschlag."""
    fehlend = [
        name for name, wert in (
            ("RESEND_API_KEY", config.RESEND_API_KEY),
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
        message_id = _send(
            api_key=config.RESEND_API_KEY,
            email_from=config.EMAIL_FROM,
            email_to=config.EMAIL_TO,
            subject=SUBJECT,
            html_body=BODY,
        )
    except Exception as e:
        report(f"❌ Test-Versand FEHLGESCHLAGEN (Key aus {key_source}) "
               f"an {config.EMAIL_TO}: {type(e).__name__}: {e}")
        raise

    if not message_id:
        report(f"⚠️  Resend hat angenommen, aber keine id geliefert — Zustellung "
               f"nicht pruefbar (Key aus {key_source})")
        return

    # HIER liegt die eigentliche Pruefung. Ein 2xx auf den POST bedeutet nur
    # "angenommen". Am 2026-07-30 meldete Resend genau so einen Erfolg und stellte
    # dann NICHT zu: last_event="failed", weil die Absenderdomain nicht verifiziert
    # war. Wer nur den Statuscode prueft, meldet einen Erfolg, den es nicht gibt.
    last_event = None
    for wait in POLL_WAITS:
        time.sleep(wait)
        resp = requests.get(
            f"https://api.resend.com/emails/{message_id}",
            headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"},
            timeout=20,
        )
        if resp.status_code != 200:
            report(f"⚠️  Zustellstatus nicht abrufbar ({resp.status_code}) — "
                   f"Mail wurde angenommen, id={message_id}")
            return
        last_event = resp.json().get("last_event")
        if last_event and last_event != "queued":
            break

    if last_event in FAILURE_EVENTS:
        report(f"❌ Test-Versand NICHT zugestellt (Key aus {key_source}) an "
               f"{config.EMAIL_TO}: last_event={last_event!r}, "
               f"Absender={config.EMAIL_FROM}, id={message_id}")
        pytest.fail(
            f"Resend nahm die Mail an, stellte sie aber nicht zu "
            f"(last_event={last_event!r}). Haeufigste Ursache: Absenderdomain "
            f"{config.EMAIL_FROM.split('@')[-1]!r} ist nicht verifiziert."
        )

    report(f"✅ Test-Versand zugestellt (Key aus {key_source}) an "
           f"{config.EMAIL_TO} — last_event={last_event!r}, id={message_id}")
