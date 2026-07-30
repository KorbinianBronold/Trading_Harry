"""Live-Verbindungspruefung aller externen APIs.

Prueft ausschliesslich, ob Zugangsdaten akzeptiert werden und ein Request eine
verwertbare Response liefert — keine Inhalte, keine Fachlogik. Alle Aufrufe sind
lesend; einzige Ausnahme ist der eigentliche Mailversand, der bewusst in
test_email_delivery.py steht und Kontingent verbraucht.

Laeuft nur mit `--run-live` (s. tests/conftest.py).

Lokal liest der Code die Werte aus `.env`, unter GitHub Actions aus den Secrets.
Im Normalfall sind sie identisch, aber sie koennen einzeln ablaufen — und nur
der Secret-Wert entscheidet, ob die geplanten Laeufe durchkommen. Deshalb laeuft
diese Datei an beiden Orten.

Kosten: Der Anthropic-Test erzeugt einen Ein-Token-Request auf dem guenstigsten
Modell (Bruchteile eines Cents). Finnhub und Capital.com sind auf ihren
kostenlosen Stufen unbegrenzt genug fuer eine Abfrage pro Push."""
import pytest

import config


# ---------- Anthropic ----------

@pytest.mark.live_api
def test_anthropic_key_is_accepted(report, key_source):
    """Kleinstmoeglicher Request: ein Token auf dem guenstigsten Modell."""
    if not config.ANTHROPIC_API_KEY:
        report(f"❌ Anthropic: kein ANTHROPIC_API_KEY aus {key_source}")
        pytest.fail(f"ANTHROPIC_API_KEY fehlt in {key_source}")

    from anthropic import Anthropic
    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    try:
        resp = client.messages.create(
            model=config.CLAUDE_MODEL_HAIKU,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
    except Exception as e:
        report(f"❌ Anthropic FEHLGESCHLAGEN ({key_source}): {type(e).__name__}: {e}")
        raise

    assert getattr(resp, "id", None), "Antwort ohne id — kein verwertbarer Response"
    report(f"✅ Anthropic erreichbar ({key_source}), Modell {resp.model}")


# ---------- Finnhub ----------

@pytest.mark.live_api
def test_finnhub_key_is_accepted(report, key_source):
    """Eine Kursabfrage auf AAPL — leichtester lesender Endpunkt."""
    if not config.FINNHUB_API_KEY:
        report(f"❌ Finnhub: kein FINNHUB_API_KEY aus {key_source}")
        pytest.fail(f"FINNHUB_API_KEY fehlt in {key_source}")

    import finnhub
    client = finnhub.Client(api_key=config.FINNHUB_API_KEY)
    try:
        quote = client.quote("AAPL")
    except Exception as e:
        report(f"❌ Finnhub FEHLGESCHLAGEN ({key_source}): {type(e).__name__}: {e}")
        raise

    # Ein ungueltiger Key liefert bei Finnhub kein Exception, sondern ein leeres
    # bzw. genulltes Dict — deshalb auf einen echten Kurs pruefen.
    assert quote and quote.get("c"), f"Finnhub lieferte keinen Kurs: {quote!r}"
    report(f"✅ Finnhub erreichbar ({key_source}), AAPL c={quote['c']}")


@pytest.mark.live_api
def test_finnhub_fundamentals_endpoint_answers(report, key_source):
    """Der Endpunkt, den die Pipeline tatsaechlich nutzt (Sektor-Mapping)."""
    import finnhub
    client = finnhub.Client(api_key=config.FINNHUB_API_KEY)
    try:
        profile = client.company_profile2(symbol="AAPL")
    except Exception as e:
        report(f"❌ Finnhub-Profil FEHLGESCHLAGEN ({key_source}): {type(e).__name__}: {e}")
        raise
    assert profile and profile.get("finnhubIndustry"), (
        f"Kein finnhubIndustry — davon haengt das Sektor-Mapping ab: {profile!r}"
    )
    report(f"✅ Finnhub-Fundamentals ({key_source}), "
           f"AAPL industry={profile['finnhubIndustry']!r}")


# ---------- Capital.com ----------

@pytest.mark.live_api
def test_capital_com_session_and_read(report, key_source):
    """Session-Auth plus eine lesende Marktabfrage. Beides gehoert zusammen:
    die Session allein sagt noch nichts ueber die Datenrechte."""
    fehlend = [n for n, v in (
        ("CAPITAL_COM_API_KEY", config.CAPITAL_COM_API_KEY),
        ("CAPITAL_COM_IDENTIFIER", config.CAPITAL_COM_IDENTIFIER),
        ("CAPITAL_COM_PASSWORD", config.CAPITAL_COM_PASSWORD),
    ) if not v]
    if fehlend:
        report(f"❌ Capital.com: fehlende Werte aus {key_source}: {', '.join(fehlend)}")
        pytest.fail(f"Capital.com-Zugangsdaten fehlen in {key_source}: {fehlend}")

    from src.providers.capital_provider import CapitalComProvider
    provider = CapitalComProvider()
    try:
        df = provider.get_price_history("AAPL", days=5)
    except Exception as e:
        report(f"❌ Capital.com FEHLGESCHLAGEN ({key_source}): {type(e).__name__}: {e}")
        raise

    assert df is not None and not df.empty, (
        "Capital.com lieferte keine Bars — Session oder Datenrechte pruefen"
    )
    report(f"✅ Capital.com erreichbar ({key_source}), "
           f"AAPL {len(df)} Bars bis {df.index[-1].date()}")


# ---------- Resend (lesend, ohne Kontingent zu verbrauchen) ----------

def _resend_get(path: str):
    """GET auf die Resend-API. Bewusst `requests`, NICHT urllib: Resend sitzt
    hinter Cloudflare, das die urllib-Signatur mit HTTP 403 und dem Klartext
    "error code: 1010" abweist — das sieht wie ein Auth-Fehler aus und ist keiner."""
    import requests
    return requests.get(
        f"https://api.resend.com{path}",
        headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"},
        timeout=20,
    )


@pytest.mark.live_api
def test_resend_key_is_accepted_without_sending(report, key_source):
    """Prueft NUR den Schluessel, nicht die Zustellbarkeit — kostet kein Kontingent.

    Die Trennung von der Domain-Pruefung darunter ist bewusst: ein gueltiger
    Schluessel sagt nichts darueber, ob eine Mail ankommt. Genau diese Verwechslung
    hat beim Vorgaenger-Anbieter einen Abend gekostet."""
    if not config.RESEND_API_KEY:
        report(f"❌ Resend: kein RESEND_API_KEY aus {key_source}")
        pytest.fail(f"RESEND_API_KEY fehlt in {key_source}")

    resp = _resend_get("/domains")
    if resp.status_code != 200:
        report(f"❌ Resend-Key FEHLGESCHLAGEN ({key_source}): "
               f"{resp.status_code} — {resp.text[:200]}")
        pytest.fail(f"Resend antwortete {resp.status_code}: {resp.text[:200]}")

    report(f"✅ Resend-Key gueltig ({key_source})")


@pytest.mark.live_api
def test_resend_has_a_verified_sender_domain(report, key_source):
    """Ohne verifizierte Absenderdomain nimmt Resend die Mail mit 2xx AN und
    stellt sie dann NICHT zu — `last_event` wird "failed".

    Am 2026-07-30 so passiert: `onboarding@resend.dev` als Absender, POST 200,
    Zustellung gescheitert mit "Domain is not verified". Dieser Adresse darf man
    also nicht vertrauen; sie ist Resends eigener Onboarding-Absender und nicht
    fuer fremde Konten freigegeben. Der Test faellt deshalb rot, solange keine
    eigene Domain verifiziert ist — sonst meldet die Suite eine Zustellfaehigkeit,
    die nicht existiert."""
    resp = _resend_get("/domains")
    assert resp.status_code == 200, resp.text[:200]
    domains = resp.json().get("data", [])
    verified = [d.get("name") for d in domains if d.get("status") == "verified"]
    pending = [f"{d.get('name')} ({d.get('status')})"
               for d in domains if d.get("status") != "verified"]

    if verified:
        report(f"✅ Resend-Absenderdomain verifiziert ({key_source}): {verified}")
        sender_domain = (config.EMAIL_FROM or "").split("@")[-1]
        assert sender_domain in verified, (
            f"EMAIL_FROM={config.EMAIL_FROM!r} nutzt {sender_domain!r}, "
            f"verifiziert ist aber nur {verified}"
        )
        return

    report(f"❌ Keine verifizierte Absenderdomain ({key_source}). "
           f"Angelegt: {pending or 'keine'}. Aktuell EMAIL_FROM={config.EMAIL_FROM} — "
           f"Resend nimmt die Mail an und stellt sie NICHT zu.")
    pytest.fail(
        "Keine verifizierte Domain bei Resend. Der Versand scheitert asynchron mit "
        "last_event='failed'. Loesung: eigene Domain in Resend anlegen und die "
        "DNS-Records setzen, dann EMAIL_FROM darauf umstellen."
    )
