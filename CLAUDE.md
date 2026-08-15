# Shares_Future – SP500 CFD Research Tool

**Zuletzt aktualisiert:** 2026-08-15 — **Live-Verifikation von Plan 2 abgeschlossen.**
`trade_proposals` lief am 2026-08-14 erstmals gegen echte Signale; E3 (Ablösung statt
Dublette) und E5 (gedrehte Signale werden gemeldet, nicht gehandelt) verhalten sich wie
spezifiziert. Details und vier Befunde: PROJECT_STATUS **P2.12**.
✅ Der dabei gefundene Datenfehler — vier doppelte offene Predictions aus einem
Doppellauf am 13.08. — ist bereinigt **und die Ursache geschlossen**: ein partieller
UNIQUE-Index erzwingt die Invariante jetzt in der Datenbank (s. unten).
⏳ Offen: `weekly` (zugestellt, aber nie inhaltlich verifiziert), der einmalige
`bootstrap-db`-Lauf, danach die Reaktivierung von `analyze.yml`.

Davor, 2026-08-12 — Sprint 3C / **Plan 1 (Fundament) ist code-fertig**
(Analyse-Pipeline-Umbau: Trichter, zwei zählbare Signale, neues Ranking). 17 Indikatoren
laufen mit und füllen 29 neue Spalten, das Technik-Signal ist berechenbar — **keine
Verhaltensänderung.** Details: PROJECT_STATUS C.6. Einstieg ist jetzt Plan 2 (Trichter).
⚠️ Der abschliessende Ganz-Branch-Review fand die Garantie tatsächlich gebrochen vor (die
29 neuen Werte liefen in vier Claude-Prompts mit) und einen zweiten Bug (`ichi_chikou` war
strukturell immer `None`) — beide im selben Fix-Wave behoben, s. PROJECT_STATUS C.6.

Davor, 2026-08-09 — `pre_market` erstmals vollständig gelaufen (3,13 EUR, 10 Predictions,
Mail zugestellt), Docker-Smoke-Test bestanden, alle `.md`-Dateien auf diesen Stand gezogen.
Details: PROJECT_STATUS P2.10 / P2.11.
⚠️ Die dort genannten Kosten sind **zu niedrig** ausgewiesen: `cost_tracker` zog
Cache-Treffer zweimal ab. Seit `f8f6684` (Plan 1, Task 2) behoben.

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
- ⚠️ Prompts sind **nur über den Dateinamen** versioniert (`deep_analysis_v1.txt`), und die
  Version steht fest im Modul-Import. **A/B-Testing gibt es nicht** — die Tabelle
  `prompt_versions` wird von `init_schema()` angelegt und nirgends gelesen oder
  geschrieben (verifiziert 2026-08-09). Ein Wechsel ist eine Code-Änderung, kein
  Datenbank-Eintrag. Gehört zu Sprint 3D.
- `SECTOR_ALIASES` normalisiert Finnhubs `finnhubIndustry` auf 21 **Sub-Sektoren**
  (feiner als GICS: Halbleiter gegen SOXX statt gegen den breiten XLK). Unbekannte
  Rohwerte werden mit WARN geloggt und bleiben ungemappt — nie stillschweigend
  in einen Sammeleimer geworfen. Grundregel: lieber ungemappt als falsch gemappt.
- Ticker werden nach `TICKER_MAX_SKIPS = 20` Datenqualitäts-Skips deaktiviert,
  Auto-Retry nach `TICKER_RETRY_AFTER_DAYS = 30`, manueller Reset via `--reactivate`
- Sektor-Momentum wird als **zwei getrennte Signale** erhoben (ETF + DB-Durchschnitt)
  und nie verrechnet — Sprint 3D soll messen, welches besser predictet
- Das technische Signal ist **deterministisch im Code** (`src/technical_signal.py`),
  kein Claude-Call: drei Teilindikatoren stimmen ab, ADX moduliert die Stärke,
  filtert aber nie die Richtung. Die drei Ablesungen (RSI als Momentum, MACD über
  das Histogramm, Kurs über SMA50 **und** über SMA200 — keine SMA50-vs-SMA200-
  Kreuzung) sind bewusste Entscheidungen — welche besser predictet, misst 3D.
- `technical_indicators` trägt 17 Indikatoren, von denen zunächst nur vier etwas
  steuern. Der Rest läuft mit, damit 3D später Historie hat statt bei null zu beginnen.
- Mailversand über Resend. Ein `2xx` heisst nur "angenommen"; die Zustellung läuft
  asynchron und scheitert ggf. später unter `GET /emails/{id}` mit
  `last_event="failed"`. Erfolg nie am Statuscode festmachen.
- **Je Trade-Idee existiert immer genau EINE offene Prediction.** `trade_proposals`
  löst die `pre_market`-Zeile über `status='superseded'` + `superseded_by` ab, statt
  eine zweite daneben zu legen. Ohne das schliesst der Evaluator beide und jede
  Kennzahl zählt doppelt. Das Urteil steht auf der **alten** Zeile
  (`revision_verdict`) — in drei von sechs Ausgängen entsteht gar keine neue.
  Seit 2026-08-15 erzwingt das die **Datenbank**: ein partieller UNIQUE-Index
  `ux_predictions_one_open_per_idea` über `(date, ticker, direction) WHERE
  status='open'`. Partiell ist Absicht — ein UNIQUE über die drei Spalten allein
  bräche E3, weil abgelöste und ablösende Zeile alle drei Werte teilen.
  ⚠️ **Daraus folgt eine Reihenfolge, die man nicht umstellen darf:**
  `db.supersede_prediction()` setzt die alte Zeile **zuerst** auf `superseded`
  und fügt erst dann die neue ein (`superseded_by` kommt im dritten Schritt
  nach). SQLite prüft den Index je Statement, nicht beim Commit — ein INSERT
  davor scheitert. Alle drei Schritte liegen weiterhin in einer Transaktion.
  Bestehende DBs mit Duplikaten räumt `init_schema()` beim ersten Lauf auf
  (ältere Zeile → `closed_stale_pre_rollout`, `learnable=0`, mit WARNING).
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
- `price_history` enthält **ausschliesslich finale Tagesbars**. Entscheidungskurse gehören
  nicht dorthin, sondern in `predictions.price_premarket` / `price_open` / `price_1610` —
  die Vermischung beider war der Frozen-Bar-Bug. Es gibt **drei** Schreiber, alle an
  dieselbe Regel gebunden (**nie der laufende Tag**):
  1. `final_close` (00:15 UTC, täglich) — der einzige im Normalbetrieb, `upsert`
  2. `setup/historical_loader.py` — manueller Backfill, seit `0b025a8` ebenfalls ohne
     den laufenden Tag (fiel bei Krypto auf: durchgehender Handel, UTC-Bar schliesst
     erst 00:00; bei Aktien fehlt die Wochenendbar ohnehin)
  3. `data_collector._fill_price_gaps()` — Sicherheitsnetz nach Ausfällen, greift im
     Normalbetrieb nicht
- `src/universe.py:full_universe()` ist die **eine Quelle**, welche Ticker das System
  anfasst (Aktien + Rohstoffe + Krypto + Sub-Sektor-ETFs). `run_final_close`, der
  Bootstrap und der Historien-Guard lesen alle dort — getrennt gepflegt liefen sie
  auseinander, und ein neuer Ticker bekäme Backfill ohne Fortschreibung oder umgekehrt.
- Lückenerkennung prüft den **gesamten jüngsten Abschnitt** (200 Bars), nicht nur
  `MAX(date)`. Sonst blendet die erste Bar nach einem Ausfall das Loch dahinter für
  immer aus. ⚠️ Innenliegende Lücken zählen erst ab **zwei** aufeinanderfolgenden
  Handelstagen: einzelne fehlende Wochentage sind US-Feiertage (35 der 1000 AAPL-Bars).
- ⚠️ Capital.com beantwortet ein `to` **in der Zukunft** (UTC) mit HTTP 400 — fünf
  Minuten genügen. Nicht dokumentiert, empirisch ermittelt. `_not_in_future()` klemmt es.
- ⚠️ Der `open` der Tages-Bar ist **nicht** der Eröffnungskurs: die Bar beginnt laut
  `openingHours` um 08:00 UTC, also vorbörslich. Gemessen 0,47 % Abweichung bei AAPL
  (310,54 gegen 309,09). Der echte Eröffnungskurs kommt aus einer `MINUTE`-Bar.
- ⚠️ **Ein neuer Ticker braucht erst `setup/historical_loader.py --tickers <X>`**,
  bevor er in die Config kommt. Ohne Historie wird er als `insufficient bars`
  übersprungen und zählt Richtung Deaktivierung — der stille Bootstrap-Pfad ist
  mit `_ensure_today_bar` weggefallen.
- ⚠️ **`random/` ist Korbinians interner Ordner.** Nicht anfassen: keine Edits, keine
  Löschungen, keine Aufräumvorschläge, kein „diese Datei ist tot"-Befund. Änderungen
  darin sind akzeptiert und brauchen keine Begründung. Nur auf ausdrückliche Anweisung
  bearbeiten — und aus jeder Aufräum-, Doku- und Toter-Code-Betrachtung heraushalten.

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
# --universe / --full-sp500 / --reactivate / --list-inactive / --report-coverage).
# Ein Aufruf ohne Flag bricht mit argparse-Fehler ab und startet NICHT mehr
# stillschweigend den MVP-Pull.
python setup/historical_loader.py --all        # nur die 20 MVP-Aktien
python setup/historical_loader.py --universe   # + Rohstoffe, Krypto, Sektor-ETFs

# Sieht die DB gesund aus? Bars je Universums-Ticker, markiert alles unter
# MIN_BARS_RSI. Reine DB-Abfrage, keine Capital.com-Calls.
python setup/historical_loader.py --report-coverage

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
  und die Live-Verifikation. ⚠️ `analyze.yml` steht auf `disabled_manually`. Der
  Plan-2-Code **ist am 2026-08-04 dreimal gelaufen** (pre_market, trade_proposals,
  close, alle erfolgreich), hat dabei aber **keine Predictions erzeugt** — warum, ist
  ungeklärt und die erste Frage der Verifikation (PROJECT_STATUS, P2.4).
  Run-Types sind seither
  `pre_market` / `trade_proposals` / `close` / `final_close` / `weekly`.
  ✅ **Ursache geklärt (2026-08-08):** die CI-DB (`db-latest`) hatte nie echte Historie —
  19 Bars je Aktie, eine unter `MIN_BARS_RSI = 20`. Kein stiller Ausfall; die Pipeline
  verhielt sich korrekt. Details und die sechs Folge-Commits: PROJECT_STATUS P2.4/P2.9.
  ⚠️ **`db-latest` nie als Datenquelle verwenden**, ohne die Abdeckung zu prüfen — es
  bestückt sich sonst nur aus den CI-eigenen Schreibvorgängen selbst. Dafür gibt es den
  Workflow `bootstrap-db` (nur `workflow_dispatch`).
- **Preismodell-Umbau** (2026-08-06/07) abgeschlossen: drei Entscheidungs-Snapshots
  in `predictions`, neuer Run-Type `final_close`, Evaluator auf finale Bars.
  Spec: `docs/superpowers/specs/2026-08-06-preismodell-snapshots-design.md`,
  Stand und Befunde in PROJECT_STATUS, Abschnitt P3. ⚠️ **Nie in einem echten
  Pipelinelauf ausgeführt** — verifiziert wurde nur lesend gegen die API, in
  Wegwerf-Datenbanken. Er entstand nach den Läufen vom 2026-08-04.
- **3C** (Ranking-Überarbeitung): **Plan 1 (Fundament) ist code-fertig**, Plan 2 und 3
  offen. Die Teilschritte C.1–C.4 sind in einer gemeinsamen Spec aufgegangen, die den
  Trichter, die zwei Signale und das Ranking zusammen neu fasst:
  `docs/superpowers/specs/2026-08-11-analyse-pipeline-umbau-design.md`.
  Die Umsetzung zerfällt in **drei unabhängig lieferbare Pläne**; Plan 1 (Fundament:
  17 Indikatoren, Technik-Signal, Schema) ist unter
  `docs/superpowers/plans/2026-08-11-analyse-pipeline-plan1-fundament.md` **abgeschlossen
  und ändert kein Pipeline-Verhalten** — das Technik-Signal ist berechenbar, steuert aber
  nichts. Einstieg ist jetzt **Plan 2 (Trichter)**. Stand und Messprotokoll:
  PROJECT_STATUS, Abschnitt C.6.
- **3D / 3E / 3F** sind ⚠️ **Platzhalter** — bei Erreichen aktiv nachfragen und den
  Sprint gemeinsam ausarbeiten, **bevor** Code entsteht. Die Stichpunkte dort sind
  keine Spezifikation.

## Vollständige Spezifikation
Siehe docs/SPECIFICATION.md für Datenbankschema, Prompt-Templates, Guardrails-Logik,
Lernmodul, E-Mail-Format und Test-Struktur.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
