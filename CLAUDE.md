# Shares_Future – SP500 CFD Research Tool

**Zuletzt aktualisiert:** 2026-08-06 — Task-20-Review abgeschlossen, acht Defekte behoben
(Details: PROJECT_STATUS.md, P2.8). Code liegt auf `main`, Pipeline weiterhin deaktiviert.

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
- **Je Trade-Idee existiert immer genau EINE offene Prediction.** `trade_proposals`
  löst die `pre_market`-Zeile über `status='superseded'` + `superseded_by` ab, statt
  eine zweite daneben zu legen. Ohne das schliesst der Evaluator beide und jede
  Kennzahl zählt doppelt. Das Urteil steht auf der **alten** Zeile
  (`revision_verdict`) — in drei von sechs Ausgängen entsteht gar keine neue.
- Ein gedrehtes oder hart verworfenes Signal bleibt **offen** und wird regulär
  ausgewertet; nur so lässt sich messen, ob die Ablehnung richtig lag. Eine
  Gegenposition entsteht dabei nie (das Gegensignal lief nie durch Phase 3).
- B.3-Checks werden in **beiden** Läufen erhoben, aber nur um 16:10 durchgesetzt —
  gesteuert über den `enforce`-Parameter in `src/signal_checks.py`, den der Aufrufer
  setzt. Um 15:00 ist die US-Börse zu; die Morgenmail ist ein Research-Briefing.
- VIX-Schwellen wirken **kumulativ, nie partitioniert**: ab 25 nur noch
  `confidence='high'` (beide Richtungen, ohne Obergrenze), zusätzlich ab 35 keine
  neuen Longs. Ein Filter darf nicht lockerer werden, je unruhiger der Markt ist.
- Eine Prediction ist erst **ab dem Folgetag** eine offene Position — vorher ist sie
  ein Vorschlag. Sonst prüft Phase 4a die Signale desselben Laufs gegen ihre eigene,
  Sekunden alte Analyse.
- Tests ausserhalb `tests/live/` dürfen **nicht** nach draussen telefonieren. Ein
  Autouse-Fixture in `tests/conftest.py` sperrt auf **Transport-Ebene**
  (`requests.adapters.HTTPAdapter.send`, `httpx.Client.send`) und legt den
  Anthropic-Client zusätzlich still. Nur `requests.get`/`post` zu patchen reichte
  nicht: finnhub nutzt `requests.Session`, das Anthropic-SDK httpx. Anlass waren
  zwei reale Vorfälle: echte Mails aus einem Testlauf und eine echte
  Capital.com-Session aus einem Unit-Test, die still geschluckt wurde.
- Der Bar des **laufenden** Tages wird überschrieben, abgeschlossene Tage nie.
  Capital.coms DAY-Bar existiert schon während des Tages und bewegt sich weiter
  (inkl. erweiterter Handelszeiten). Wer sie einfriert, lässt den 16:10-Lauf
  „frische" Kurse gegen sich selbst vergleichen und schreibt den echten
  Tagesschluss nie.

## Cron-Jobs — die zwei Fallen
Zeitplan und Run-Types stehen in `.github/workflows/analyze.yml`. Zwei Dinge, die
man dort **nicht** sieht:

**DST.** Cron ist UTC-fix, GitHub Actions passt nicht an die Sommerzeit an. Die
Kommentare im Workflow gelten für CEST; im Winter (CET) läuft alles 1 h früher.

⚠️ Für `trade_proposals` ist das **nicht** nur eine Verschiebung: der Lauf hängt an
der **US-Eröffnung** (10:10 America/New_York), nicht an Berlin. Deshalb gibt es
**zwei** Cron-Slots — 14:10 UTC unter EDT, 15:10 UTC unter EST — und der Workflow
verwirft den jeweils falschen anhand von `TZ=America/New_York date +%z`. Maßgeblich
ist bewusst die US-Zeitzone: EU und USA schalten an verschiedenen Wochenenden um.
Mit nur dem Sommer-Slot lief der Lauf von November bis März **vor** der Eröffnung.

**Kosten.** Die Schätzungen im Workflow und in älteren Dokumenten sind
nachweislich zu niedrig. Erster echter Messlauf am 2026-07-29: ein `pre_market`
mit **20** MVP-Tickern kostete **3,3143 EUR** (`cost_tracking`) — die Doku nannte
~3,20 EUR für 500 Ticker. Treiber ist Phase 3 mit ~0,12 EUR je Tiefenanalyse.

⚠️ **`MAX_DEEP_ANALYSIS = 80` und `BATCH_SIZE_QUICK = 30` sind tote Konstanten** —
sie werden nirgends im Code gelesen (verifiziert 2026-07-30). Es gibt **keinen**
Deckel auf die Zahl der Tiefenanalysen ausser `CostCapExceeded`, und Phase 2 macht
*einen* Haiku-Call über alle Ticker statt 30er-Batches. Jede Hochrechnung, die mit
„80 Slots" argumentiert, ist damit die optimistische Untergrenze. Der Fix gehört zu
Sprint 3C (C.4, technischer Pre-Filter) — der Pre-Filter ist dort **nicht** eine
bessere Auswahl innerhalb eines bestehenden Deckels, sondern die einzige
Mengenbegrenzung überhaupt.
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

- **Sprint 3B** teilweise: Plan 1 (Fundament) erledigt; **Plan 2 (Pipeline-Umbau) zu
  20 von 20 Tasks umgesetzt** — die Commits liegen **direkt
  auf `main` und sind gepusht**. Einen Branch `sprint3b/plan2-pipeline-umbau` gibt es
  weder lokal noch remote (`git ls-remote --heads origin` kennt nur `refs/heads/main`,
  geprüft 2026-08-03). Offen: Task 20, ein Gesamt-Review über die Plan-2-Commits
  und die Live-Verifikation. ⚠️ Der Code ist **gemerged, aber nie ausgeführt**:
  `analyze.yml` steht auf `disabled_manually`, letzter Pipeline-Lauf 2026-07-13.
  Run-Types sind seither
  `pre_market` / `trade_proposals` / `close` / `weekly`.
- **3C** offen (Ranking-Überarbeitung)
- **3D / 3E / 3F** sind ⚠️ **Platzhalter** — bei Erreichen aktiv nachfragen und den
  Sprint gemeinsam ausarbeiten, **bevor** Code entsteht. Die Stichpunkte dort sind
  keine Spezifikation.

## Vollständige Spezifikation
Siehe docs/SPECIFICATION.md für Datenbankschema, Prompt-Templates, Guardrails-Logik,
Lernmodul, E-Mail-Format und Test-Struktur.
