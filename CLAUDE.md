# Shares_Future – SP500 CFD Research Tool

## Projektübersicht
Automatisiertes Research-Tool zur täglichen Analyse von S&P 500 Aktien,
Rohstoffen (Gold, Silber, Öl) und Kryptowährungen (BTC, ETH, SOL, XRP).

Kein automatisches Trading. Nur Research und Paper-Trading Simulation.

Stack, Abhängigkeiten, Verzeichnisbaum und Env-Variablen stehen in
`requirements.txt`, `.env.example` und im Repo selbst — hier bewusst nicht doppelt.
Die Pipeline-Phasen lassen sich an `main.py:run_pipeline()` ablesen.

## Wichtige Designentscheidungen
- Provider-Hierarchie: Capital.com (alleiniger OHLC-Provider) → Finnhub (Fundamentals, gecacht) — yfinance seit Sprint 3 entfernt (2026-07-09)
- Guardrails: jede Analyse braucht min. 2 Belege je Score-Dimension
- Long/Short getrennt tracken und optimieren
- Übersprungene Aktien: learnable=False, nie ins Lernmodul
- SIMULATION_ONLY=True: niemals echte Orders
- ATR-Mindest: SP500_MIN_ATR_PCT = 2.0
- MAX_HOLD_DAYS = 5, HOLD_TARGET = "intraday"
- Timezone: TZ="Europe/Berlin" in Bash, ZoneInfo("Europe/Berlin") in Python
- Prompts versioniert mit A/B-Testing
- `SECTOR_ALIASES` normalisiert Finnhubs `finnhubIndustry` auf 21 **Sub-Sektoren**
  (feiner als GICS: Halbleiter gegen SOXX statt gegen den breiten XLK). Unbekannte
  Rohwerte werden mit WARN geloggt und bleiben ungemappt — nie stillschweigend
  in einen Sammeleimer geworfen. Grundregel: lieber ungemappt als falsch gemappt.
- Ticker werden nach `TICKER_MAX_SKIPS = 20` Datenqualitäts-Skips deaktiviert,
  Auto-Retry nach `TICKER_RETRY_AFTER_DAYS = 30`, manueller Reset via `--reactivate`
- Sektor-Momentum wird als **zwei getrennte Signale** erhoben (ETF + DB-Durchschnitt)
  und nie verrechnet — Sprint 3D soll messen, welches besser predictet
- Mailversand über Resend. Ein `2xx` heisst nur "angenommen"; die Zustellung läuft
  asynchron und scheitert ggf. später unter `GET /emails/{id}` mit
  `last_event="failed"`. Erfolg nie am Statuscode festmachen.

## Cron-Jobs — die zwei Fallen
Zeitplan und Run-Types stehen in `.github/workflows/analyze.yml`. Zwei Dinge, die
man dort **nicht** sieht:

**DST.** Cron ist UTC-fix, GitHub Actions passt nicht an die Sommerzeit an. Die
Kommentare im Workflow gelten für CEST; im Winter (CET) läuft alles 1 h früher.

**Kosten.** Die Schätzungen im Workflow und in älteren Dokumenten sind
nachweislich zu niedrig. Erster echter Messlauf am 2026-07-29: ein `pre_market`
mit **20** MVP-Tickern kostete **3,3143 EUR** (`cost_tracking`) — die Doku nannte
~3,20 EUR für 500 Ticker. Treiber ist Phase 3 mit ~0,12 EUR je Tiefenanalyse;
hochgerechnet auf die 80 Slots aus `MAX_DEEP_ANALYSIS` landet ein Lauf bei
~10,8 EUR und bricht am Deckel `MAX_COST_PER_RUN_EUR = 4.00` ab.
Details, Laufzeit-Hochrechnung und der Cron-Konflikt: PROJECT_STATUS.md, F.1.

## Wichtige Befehle
Standardaufrufe (`pytest tests/ --cov=src --cov-fail-under=80`, `python main.py
--run-type <typ>`) sind wie üblich. Nicht erratbar sind diese:

```bash
# historical_loader.py: genau EIN Modus-Flag ist Pflicht (--tickers / --all /
# --full-sp500 / --reactivate / --list-inactive). Ein Aufruf ohne Flag bricht mit
# argparse-Fehler ab und startet NICHT mehr stillschweigend den MVP-Pull.
python setup/historical_loader.py --all

# Ticker-Status (Sprint 3B / B.7) – reine DB-Operationen, keine Capital.com-Calls
python setup/historical_loader.py --list-inactive          # stillgelegte Ticker + Retry-Datum
python setup/historical_loader.py --reactivate AAPL MSFT   # sofort zurücksetzen

# Capital.com-Epics der Sub-Sektor-ETFs + VIX prüfen (manuell, read-only)
python setup/verify_epics.py --symbols SOXX VGT

# Live-Checks gegen die echten APIs. Ohne --run-live werden sie uebersprungen,
# damit ein normaler Testlauf niemals ungefragt Mail verschickt.
pytest tests/live -m live_api --run-live      # nur lesend, verschickt nichts
pytest tests/live --run-live                  # inkl. echtem Mailversand
```

## Lokales Docker-Setup
Nur für manuelles Testen einzelner Run-Types — **kein Scheduler/Cron im Container.**
Automatisierte Ausführung läuft ausschliesslich über GitHub Actions (`analyze.yml`).

**Der Run-Type ist Pflicht.** Ohne Argument — Run-Button in Docker Desktop,
`docker run <image>`, `docker compose up` — greift `CMD ["--help"]` und das Image
gibt seine Hilfe aus (Exit 0). Es startet bewusst *keine* Pipeline: ein
versehentlicher Klick soll nicht gegen die gemountete `data/tracking.db` laufen.

`docker-compose.yml` mountet `./data` — Läufe schreiben also in die echte Datenbank.
Für gefahrlose Experimente den Mount überschreiben:
`docker compose run --rm -v /tmp/dbtest:/app/data trading-harry --run-type close`

## Sprint-Stand
**Vor jeder Implementierung `docs/superpowers/specs/PROJECT_STATUS.md` lesen** — dort
steht der verbindliche Stand inklusive aller Sprint-3-Teilschritte, der offenen Bugs
und der getroffenen Entscheidungen. Kurzfassung:

- **Sprint 3B** teilweise: Plan 1 (Fundament) erledigt, Plan 2 (Cron-/Pipeline-Umbau)
  noch nicht geschrieben
- **3C** offen (Ranking-Überarbeitung)
- **3D / 3E / 3F** sind ⚠️ **Platzhalter** — bei Erreichen aktiv nachfragen und den
  Sprint gemeinsam ausarbeiten, **bevor** Code entsteht. Die Stichpunkte dort sind
  keine Spezifikation.

## Vollständige Spezifikation
Siehe docs/SPECIFICATION.md für Datenbankschema, Prompt-Templates, Guardrails-Logik,
Lernmodul, E-Mail-Format und Test-Struktur.
