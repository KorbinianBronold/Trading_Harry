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


# ---------- SendGrid (lesend, ohne Kontingent zu verbrauchen) ----------

@pytest.mark.live_api
def test_sendgrid_key_is_accepted_without_sending(report, key_source):
    """Prueft NUR den Schluessel, nicht den Versand — GET /v3/user/profile
    kostet kein Kontingent.

    Die Trennung ist bewusst: SendGrid meldet ein aufgebrauchtes Kontingent als
    HTTP 401, also genauso wie einen unbrauchbaren Schluessel. Schlaegt dieser
    Test fehl, ist der Key kaputt; schlaegt nur test_email_delivery fehl, ist der
    Key in Ordnung und das Kontingent leer."""
    import json
    import urllib.error
    import urllib.request

    if not config.SENDGRID_API_KEY:
        report(f"❌ SendGrid: kein SENDGRID_API_KEY aus {key_source}")
        pytest.fail(f"SENDGRID_API_KEY fehlt in {key_source}")

    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/user/profile",
        headers={"Authorization": f"Bearer {config.SENDGRID_API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            assert resp.status == 200
    except urllib.error.HTTPError as e:
        body = e.read(400).decode("utf-8", "replace")
        report(f"❌ SendGrid-Key FEHLGESCHLAGEN ({key_source}): {e.code} — {body}")
        raise

    # Kontingent mitmelden — genau das fehlte am 2026-07-29 bei der Fehlersuche.
    creds = urllib.request.Request(
        "https://api.sendgrid.com/v3/user/credits",
        headers={"Authorization": f"Bearer {config.SENDGRID_API_KEY}"},
    )
    try:
        with urllib.request.urlopen(creds, timeout=20) as resp:
            c = json.load(resp)
        report(f"✅ SendGrid-Key gueltig ({key_source}) — "
               f"Kontingent: {c.get('remain')} von {c.get('total')} frei "
               f"(Reset {c.get('reset_frequency')})")
        if not c.get("total"):
            report("   ⚠️  total=0 — der Versand wird trotz gueltigem Key mit "
                   "401 'Maximum credits exceeded' scheitern")
    except Exception:
        report(f"✅ SendGrid-Key gueltig ({key_source}) — Kontingent nicht abrufbar")
