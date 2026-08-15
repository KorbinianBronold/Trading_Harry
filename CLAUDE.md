# Shares_Future – SP500 CFD Research Tool

**Zuletzt aktualisiert:** 2026-08-15 — **Plan 2 (Trichter), Task 13: Doku — alle 13 Tasks
abgeschlossen.** `docs/ARCHITECTURE.md` nachgezogen: Modul 3 (`quick_filter.py`) als
„ersetzt" markiert, Modul 3b (`broad_scan.py`) als „live", Pipeline-Grafik auf
Phase 2/2a und Phase 1 (Gate/Sweep/Process) aktualisiert, `cutoff_log` ergänzt,
Finnhub-Ratenbegrenzung dokumentiert, veraltete Test-Baseline korrigiert.
**Plan 2 (Trichter) ist vollständig umgesetzt** — live, gegen echte Daten gemessen
(3,3551 EUR, günstiger als der alte Weg). Offen bleibt nur der Abschluss-Review über
`c978d70..HEAD`, dann Plan 3. **733 Tests grün, 91,52 % Coverage.**

Davor, 2026-08-15 — **Plan 2 (Trichter), Task 12: Wochenlauf-Vorlauf.**
`main._update_weekly_fundamentals()`, verdrahtet vor dem wöchentlichen Aggregat in
`run_weekly()`: füllt `fundamentals_cache` **und** `earnings_next_date` fürs ganze
Universum via `full_universe()`. **Bug-Fix gegenüber dem Plan-Pseudocode:** dessen
Skip-Prüfung („ist gecacht?") hätte einen vom Tageslauf frisch gecachten Ticker (der laut
R15 nie Earnings mitbringt) für immer übersprungen und er hätte nie ein Earnings-Datum
bekommen — die Prüfung verlangt jetzt zusätzlich ein gesetztes `earnings_next_date`.
Details: PROJECT_STATUS **C.7**, Befund 11.

Davor, 2026-08-15 — **Plan 2 (Trichter), Task 11: Finnhub-Ratenbegrenzung.**
`FinnhubProvider._respect_rate_limit()`: Sliding-Window-Drosselung (60 Calls/60s),
instanzgebunden statt modulweit wie im Plan-Pseudocode. Details: PROJECT_STATUS **C.7**,
Befund 10.

Davor, 2026-08-15 — **Plan 2 (Trichter), Task 10: Trichter ist live.**
`main.run_pipeline()` ruft `broad_scan_batch()` + `cutoff_candidates()` +
`adapt_cutoff_to_quick_filter()` statt `quick_filter_batch()`; `MAX_DEEP_ANALYSIS`
80 → 50, jetzt gelesen. `main._apply_forced_candidates()` entfernt — die Pflicht-
Kandidaten-Logik sitzt seit Task 9 in `cutoff_candidates()` selbst.
✅ **Live gegen eine Wegwerf-Kopie von `data/tracking.db` gemessen** (echte API-Calls,
20 MVP-Ticker, kein Mailversand): **3,3551 EUR, kein `CostCapExceeded`** — güns­tiger als
der alte Weg (3,9217 EUR am 14.08.). Die **Kostendeckel-Sorge aus dem letzten Eintrag war
eine unbestätigte Vermutung und lag falsch**: der Cutoff schloss 5 von 20 Tickern aus der
teuren Phase 3 aus, das spart mehr als `broad_scan` zusätzlich kostet. Details, Lehre und
Phasen-Aufschlüsselung: PROJECT_STATUS **C.7**, Befund 2 (Korrektur) und Befund 9.

Davor, 2026-08-15 — **Plan 2 (Trichter), Task 9: Cutoff.** `config.TECH_MIN_FOR_DEEP = 2`,
Tabelle `cutoff_log`, `db.log_cutoff()`, `broad_scan.cutoff_candidates()` — TDD gegen den
echten Sidecar aus Task 5/6, nicht gegen den Plan-Pseudocode blind übernommen. Details:
PROJECT_STATUS **C.7**, Befund 6.

Davor, 2026-08-15 — **Live-Verifikation von Plan 2 (Sprint 3B) abgeschlossen.**
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
Verhaltensänderung.** Details: PROJECT_STATUS C.6. (Plan 2 hat darauf aufgesetzt, s. oben.)
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
- ⚠️ **Sidecar-Invariante: neue Werte laufen *neben* `td`, nie darin.** Das `td`-Dict aus
  `_process_ticker()` wird in **vier** Claude-Prompts `json.dumps`'t (`quick_filter`,
  `deep_analysis`, `commodities_crypto` und über `main.py`s `snapshots` auch
  `portfolio_check`). Wer dort einen Schlüssel hinzufügt, ändert stillschweigend vier
  Prompts. Deshalb reist `collect()` mit einem dritten Rückgabewert: dem **Sidecar**
  (`premarket_change_pct` + die vier Technik-Signal-Werte), und die 29 Plan-1-Indikatoren
  liegen in einem separaten `extra_indicators`-Dict, das erst unmittelbar vor
  `_persist_indicators()` dazukommt. Anlass war ein echter Vorfall: Plan 1 schickte 29
  Werte (~250 Tokens je Ticker) unbemerkt in die Prompts. Ein Test pinnt die exakte
  Schlüsselmenge von `_process_ticker()`.
- **Phase 1 ist Finnhub-frei.** Sie liest `fundamentals_cache` und ruft nichts ab; das
  Nachladen bei Cache-Miss ist Phase 2b (`fetch_missing_fundamentals()`, gebaut, noch
  nicht verdrahtet) und trifft nur Kandidaten. `get_earnings_calendar()` kommt im
  Tageslauf nicht mehr vor, `earnings_beat_pct` ist dort dauerhaft `None`.
  ⚠️ `earnings_next_date` wird als **ISO-Datum** gecacht, nie als Countdown:
  `earnings_in_days` wird beim Lesen gerechnet, ein Termin in der Vergangenheit liefert
  `None`. Ein gecachter Tageszähler wäre nach vier Tagen schlicht falsch.
  ⚠️ `save_fundamentals_cache()` ist ein `INSERT OR REPLACE` der **ganzen** Zeile — wer
  dort schreibt, ohne `earnings_next_date` mitzubringen, löscht es (der Wochenjob und die
  Fundamentals-TTL haben verschiedene Rhythmen).
- Der Kurs-Sweep holt alle Live-Kurse als **Sammelabruf** (`/markets?epics=`, Chunks zu 20,
  ~25 Calls für 500 Ticker statt ~500). 20 ist eine bestätigte Untergrenze, kein gemessenes
  Maximum — grösser bringt nichts. Dreistufige 429-Notbremse: erster 429 → getakteter Modus,
  weitere → Chunk überspringen, fünf in Folge → Sweep abbrechen. ⚠️ Ein fehlender Live-Kurs
  ist **kein Skip**: er fällt auf den letzten finalen Close zurück (WARNING), und
  `premarket_change_pct` bleibt `None` statt einer erfundenen 0.
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
- Lückenerkennung prüft den **gesamten jüngsten Abschnitt** (`GAP_SCAN_BARS = 220`), nicht
  nur `MAX(date)`. Sonst blendet die erste Bar nach einem Ausfall das Loch dahinter für
  immer aus. Der Wert ist **deckungsgleich mit dem Ladefenster** von
  `load_price_history_from_db()` — bei 200 gegen 220 wäre eine Lücke auf Bar 201–220
  unsichtbar, verzerrte aber SMA200. ⚠️ Innenliegende Lücken zählen erst ab **zwei**
  aufeinanderfolgenden Handelstagen: einzelne fehlende Wochentage sind US-Feiertage
  (35 der 1000 AAPL-Bars).
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

✅ **Historisch — bis 2026-08-15 wahr, dann durch Plan 2 / Task 10 geschlossen:**
`MAX_DEEP_ANALYSIS = 80` und `BATCH_SIZE_QUICK = 30` waren tote Konstanten, ungelesen,
kein Deckel ausser `CostCapExceeded`. Jede Hochrechnung mit „80 Slots" war die
optimistische Untergrenze. **Seit Task 10:** `MAX_DEEP_ANALYSIS = 50` wird von
`broad_scan.cutoff_candidates()` gelesen und ist der einzige harte Deckel auf Phase 3;
`BATCH_SIZE_QUICK` ist entfernt. Für die 500-Ticker-Hochrechnung (3F) bleibt relevant,
dass die Deckel-Wirkung bei 500 Kandidaten etwas anderes ist als bei den bisher
gemessenen 20 (dort greift der Cutoff über die Qualifikationsregel, nicht über den
Deckel — s. PROJECT_STATUS C.7, Befund 9). Details: PROJECT_STATUS.md, F.1.

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
- **3C** (Ranking-Überarbeitung): Die Teilschritte C.1–C.4 sind in einer gemeinsamen Spec
  aufgegangen, die den Trichter, die zwei Signale und das Ranking zusammen neu fasst:
  `docs/superpowers/specs/2026-08-11-analyse-pipeline-umbau-design.md`.
  Die Umsetzung zerfällt in **drei unabhängig lieferbare Pläne**:
  - **Plan 1 (Fundament)** — `…/plans/2026-08-11-analyse-pipeline-plan1-fundament.md`,
    **abgeschlossen, ändert kein Pipeline-Verhalten**: das Technik-Signal ist berechenbar,
    steuert aber nichts. Stand: PROJECT_STATUS **C.6**.
  - **Plan 2 (Trichter)** — `…/plans/2026-08-13-analyse-pipeline-plan2-trichter.md`,
    **alle 13 Tasks umgesetzt und dokumentiert**, alle auf `main`. ✅ **Der Trichter ist
    live** — `quick_filter` ist aus `run_pipeline()` verschwunden, `broad_scan` +
    `cutoff_candidates` (`MAX_DEEP_ANALYSIS` 80 → 50) laufen live, gemessen gegen echte
    Daten: 3,3551 EUR, kein `CostCapExceeded`, güns­tiger als der alte Weg. `run_weekly()`
    füllt `fundamentals_cache` + `earnings_next_date` fürs ganze Universum,
    `FinnhubProvider` drosselt sich auf 60 Calls/Minute. Offen: nur noch der
    Abschluss-Review über `c978d70..HEAD`. Stand und zwölf Befunde: PROJECT_STATUS **C.7**.
  - **Plan 3 (Analyse & Ranking)** — offen; bringt Phase-3-Batching (der eigentliche
    Kostenhebel: ~0,034 statt ~0,12 EUR je Ticker), `deep_analysis_v2` und `rank_score`.
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

## Claude-Skills: pragmatische Auswahl

**Standard:** Superpowers-Skills **immer** checken vor jeder Response — das ist die Regel aus `superpowers:using-superpowers`.

**Exception für dieses Projekt (bewusste Effizienz-Entscheidung):** Bei offensichtlich einfachen Code-Navigations-Fragen darf graphify direkt kommen:
- **Einfache Navigation** ("wo ist Funktion X?", "was referenziert Y?") → `graphify query/path/explain` direkt (Millisekunden, keine LLM-Kosten)
- **Komplexe Tasks** (Bug debuggen, Feature planen, Code reviewen) → `superpowers:*`-Skill **zuerst** (gibt Struktur vor), graphify dann als Werkzeug darin
- **Unsicher** → superpowers (Standard-Weg: nie falsch, aber möglicherweise teurer)

Die Exception gilt **nur** für Navigation. Alles andere checkt Skills zuerst.
