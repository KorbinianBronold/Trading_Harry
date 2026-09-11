# Shares_Future – SP500 CFD Research Tool

Automatisiertes Research-Tool: tägliche Analyse von S&P-500-Aktien, Rohstoffen
(Gold, Silber, Öl) und Krypto (BTC, ETH, SOL, XRP). **Kein automatisches Trading**
— nur Research und Paper-Trading-Simulation (`SIMULATION_ONLY = True`, hardcoded).
Fixe Rahmenwerte: Long/Short getrennt, `HOLD_TARGET = "intraday"` /
`MAX_HOLD_DAYS = 5`, `ZoneInfo("Europe/Berlin")` überall.
Stack/Env/Verzeichnisbaum: `requirements.txt` / `.env.example` / Repo (nicht doppelt).
Pipeline-Phasen: `main.py:run_pipeline()`.

## Verbindlicher Stand — zuerst lesen

**`docs/superpowers/specs/PROJECT_STATUS.md`** ist der maßgebliche Stand: alle
Sprint-3-Teilschritte (C.x / P2.x / P3.x / M.x), offene Bugs, getroffene
Entscheidungen und die **Design-Invarianten in Langfassung (Abschnitt 6)**. Vor
jeder Implementierung laden.

Kurzfassung Sprint-Stand:
- **Sprint 3C / Analyse-Pipeline-Umbau:** Plan 1 (Fundament), Plan 2 (Trichter),
  Plan 3a (Batch-Tiefenanalyse), Plan 3b (Ranking) — alle abgeschlossen und live
  verifiziert. Einstieg ist der Trichter (`broad_scan` + `cutoff_candidates`,
  `MAX_DEEP_ANALYSIS = 50`); `quick_filter` ist toter Code.
- **Produktivbetrieb:** `analyze.yml` aktiv, 150 sektor-balancierte Ticker
  (`SP500_PROD_TICKERS`). Erster gemessener Produktivlauf: 37 min, ~3,60 €, 0 Skips.
- **Sprint 3D / 3E / 3F:** Platzhalter — bei Erreichen **aktiv nachfragen** und
  gemeinsam ausarbeiten, bevor Code entsteht. Die Stichpunkte sind keine Spec.

## Doku-Karte

- `docs/superpowers/specs/PROJECT_STATUS.md` — verbindlicher Stand, Sprint-Historie,
  Bugs, Design-Invarianten (§6). **Immer aktuell halten** (wie diese Datei und ARCHITECTURE).
- `docs/ARCHITECTURE.md` — Pipeline-Phasen, Module, Datenfluss. **Immer aktuell halten.**
- `docs/SPECIFICATION.md`, `README.md`, `docs/WORKFLOW.md` — Schema/Prompts/Guardrails
  bzw. Überblick. Bekannt veraltet → Finaldurchgang, nicht unaufgefordert anfassen.

## Wissensgraph (graphify)

`graphify-out/` trägt einen AST-Wissensgraphen (kein API-Key nötig).
- Vor Architektur-/Cross-File-Fragen **erst** `graphify query "<frage>"` /
  `graphify path "<A>" "<B>"` / `graphify explain "<konzept>"`, nicht blind grepen.
- `graphify-out/wiki/index.md` für breite Navigation, `GRAPH_REPORT.md` nur für den
  ganz großen Überblick.
- Nach Code-Änderungen `graphify update .` — in jeder Session aktuell halten.

## Skills — pragmatische Auswahl

- **Einfache Navigation** („wo ist X?", „was referenziert Y?") → graphify direkt.
- **Komplexe Tasks** (Bug, Feature, Review) → `superpowers:*`-Skill **zuerst** (gibt
  die Struktur vor), graphify als Werkzeug darin.
- **Unsicher** → superpowers.

## Modell-Einsatz

Jedes Modul liest sein Modell aus `config` (`CLAUDE_MODEL_SONNET = claude-sonnet-5`,
`CLAUDE_MODEL_HAIKU = claude-haiku-4-5`) — nie hart kodieren; Test-Fixtures lesen
ebenfalls aus `config`.
- **Haiku 4.5:** `broad_scan` (News-Scoring), `portfolio_check`, `quick_filter` (tot).
- **Sonnet 5:** `deep_analysis`, `commodities_crypto`, `trend_analyzer`,
  `market_context`, `revalidation`.
- **Opus 5:** nur Sprint 3D (nie produktiv gelaufen). **Fable 5:** teuerstes und
  fähigstes Modell — **keine** Spar-Option.
- ⚠️ Ein Modellwechsel ist nie nur ein String-Swap: Tokenizer, Denk-Verhalten und
  jede kalibrierte `max_tokens`-Decke ändern sich. Nach jedem Wechsel ein Messlauf
  (PROJECT_STATUS C.18).

## Design-Invarianten (nicht verletzen)

Kurzform zum Erkennen einer drohenden Verletzung; Begründung und Randfälle in
**PROJECT_STATUS §6** bzw. den genannten Abschnitten.

**Daten & DB**
- `price_history` = nur **finale** Tagesbars. Entscheidungskurse gehören in
  `predictions.price_premarket/price_open/price_1610`. Drei Schreiber, **nie** der
  laufende Tag. → P3
- Wochenend-Bars nur für Krypto (`universe.has_weekend_sessions`). Rohstoffe bekommen von
  Capital.com eine Sonntagsbar aus einer Stunde Sitzung — alle drei Schreiber verwerfen sie
  über `is_partial_weekend_bar()`, `final_close` räumt Altbestand weg. → C.36
- `technical_indicators`-Zeile `date=T` ist aus Bars bis **T-1** — kein Off-by-one,
  **nicht** „korrigieren" (Leakage). Indikatoren sind pro Tag konstant; mehrere
  Läufe/Tag schreiben wertgleich per `INSERT OR REPLACE`. → C.14
- Je Trade-Idee genau **eine** offene Prediction; `trade_proposals` löst per
  `superseded_by` ab (partieller Index `ux_predictions_one_open_per_idea`). Die
  Schrittreihenfolge in `db.supersede_prediction()` nicht umstellen. → P2.13
- Eine Prediction ist erst **ab dem Folgetag** offene Position, vorher Vorschlag. → §6.4
- `fundamentals_cache`: eine Zeile je Ticker, keine Historie. Was in eine
  Entscheidung einfliesst, wird in `predictions` eingefroren.
  `save_fundamentals_cache()` = `INSERT OR REPLACE` der **ganzen** Zeile (immer
  `earnings_next_date` mitgeben, ISO-Datum, nie Countdown). → C.20
- `config.LEARNING_RETENTION_DAYS` = **eine** Frist für vier Tabellen
  (`news_summaries`, `trend_analyses`, `skipped_tickers`, `cutoff_log`) — nie einzeln
  abweichen. → C.20
- `src/universe.py:full_universe()` ist die **eine** Ticker-Quelle. → C.25
- Migrations-Guards: `PRAGMA table_info()` / `sqlite_master` vor `ALTER`/`CREATE`.
  `learnable=False` (übersprungene Ticker) nie ins Lernmodul.

**Claude-Calls**
- `call_claude()` setzt kein `thinking`-Feld → unter Claude 5 = **adaptives Denken
  an**, teilt die `max_tokens`-Decke mit der Antwort. Jeder neue Aufrufer braucht
  eine `stop_reason`-Prüfung; ein sauberer Lauf beweist nichts (nicht
  deterministisch); jeder Versuch wird **gebucht**. → C.18
- `extract_json_blob()` für **jede** Claude-Antwort (`raw_decode` + `strict=False`);
  nie `json.loads()` daneben bauen. → C.26
- Phase 3 batcht nach Sub-Sektor (**unteilbar**), Phase 3b nach `asset_class`. Ein
  gekappter Batch (`stop_reason == "max_tokens"`) ist ein Fehler, **nie**
  teilverwerten. `BATCH_SIZE_DEEP = 8` ist ein Startwert. → §6.1
- `usage.server_tool_use` ist ein `dict` und fehlt im Stream-Pfad — Websuchen über
  die Content-Blöcke zählen. → C.9 / C.11
- Prompts werden **direkt in der aktiven Datei** angepasst — **keine neuen `_vN.txt`**
  (seit 2026-09-10; davor 2026-09-08: überschreiben erlaubt, neue Version optional; davor:
  nie editieren). Das Suffix im Dateinamen ist nur noch ein Name. Der Prompt-Stand zu einer
  Prediction steht **nur in der Git-Historie** (`git log -p prompts/<datei>`).
  `prompt_versions` ist tot, kein A/B-Testing. → PROJECT_STATUS Regel 10
- **Prompts gehören zu jeder Änderung.** Wer Code, Config, Schema, Spec, Cron oder
  Universum ändert, prüft **im selben Schritt** alle Dateien in `prompts/` — Ticker/Epics,
  Uhrzeiten und Bezugsrahmen, Run-Type-Namen, JSON-Schlüssel, zitierte Schwellen
  (`strength >= 7`, VIX 20/25/35, `1-5d`), Sektor-/Regime-Listen, Modellnamen, Sprache.
  `grep -rn "<Bezeichner>" prompts/` ist Pflicht; die `*_pins_contract`-Tests fangen nur
  Parser-Schlüssel, keine Beispieltexte oder Zahlen. Präzedenzfall: C.25 stellte die
  Ticker im Code um, die Prompts nannten `GC=F`/`BTC-USD` monatelang weiter. → Regel 15

**Analyse / Ranking / Guardrails**
- 8 Score-Dimensionen einzeln persistiert, **keine** Gewichtung im Code
  (`score_total()` / `DIMENSION_WEIGHTS` entfernt). Sortierschlüssel
  `rank_score = analysis_strength × tech_strength`. Keine Gewichtung wieder
  einführen. → C.13
- `analysis_strength()`: `momentum` ist die **absolute** Ausnahme (tief = bärisch),
  die anderen sieben Dimensionen sind trade-relativ. → C.13
- Guardrails: min. **2 Belege** je Dimension. `evidence_quality: "thin"` umgeht das
  **nur** bei exakt diesem Wert; eine thin-Dimension wird **behalten**. → §6.3
- Technisches Signal deterministisch im Code; drei feste Ablesungen (RSI-Momentum,
  MACD-Histogramm, Kurs vs. SMA50 **und** SMA200 — keine Kreuzung); ADX moduliert
  die Stärke, **nie** die Richtung. → §6.2
- Sektor-Momentum = **zwei getrennte** Signale (ETF + DB-Ø), nie verrechnet. → B.3.1
- Sektor-**Rotation** gibt es doppelt: `market_context` (persistiert; Prompt-Kontext für
  Phase 2 und den 16:10-Portfolio-Check) und `trend_analyzer` (nur Prompt-Kontext für
  Phase 2/3/3b/4a). **Kein Guardrail liest Rotation, Regime oder Breite** — der einzige
  Marktkontext-Wert in einem Check ist `vix_level` (`check_vix`). Nicht zusammenführen,
  ohne `market_context` bis in `analyze_batches()` durchzureichen — sonst sieht Phase 3
  gar keine Rotation mehr. → C.27 / C.28
- Um 16:10 gibt es **keinen** Claude-Marktkontext-Call: `vix_only_context()` holt den VIX
  deterministisch, Rotation/Makro für den Portfolio-Check kommen aus der Morgenzeile
  (`db.load_market_context`). Die 16:10-Zeile trägt bewusst nur den VIX.
  `advance_decline_ratio` wird nicht mehr erhoben (Schlüssel bleibt, immer None);
  `sp500_change_pct` und `vix_source` werden seit C.28 persistiert. → C.28
- `SECTOR_ALIASES` → 21 Sub-Sektoren; Unbekanntes bleibt ungemappt (WARN), nie
  Sammeleimer — lieber ungemappt als falsch gemappt. → B.10
- B.3-Checks in **beiden** Läufen erhoben, nur 16:10 durchgesetzt (`enforce`).
  VIX-Schwellen kumulativ: ≥25 nur `confidence='high'`, ≥35 keine neuen Longs. → B.3
- Ein gedrehtes/hart verworfenes Signal bleibt **offen** und wird regulär
  ausgewertet; eine Gegenposition entsteht nie. → P2.12
- **Sidecar-Invariante:** neue Werte laufen **neben** `td`, nie darin (`td` geht in
  drei Prompts). Ein Test pinnt die Schlüsselmenge von `_process_ticker()`. → C.6

**Provider & Daten holen**
- Capital.com ist **alleiniger** OHLC-Provider (kein yfinance-Fallback, unconditional
  instanziiert). Finnhub nur Fundamentals (7-Tage-Cache, 60 Requests/min gedrosselt).
- Phase 1 ist Finnhub-frei; Cache-Miss lädt **Phase 2b** nach (nur Kandidaten) **und**
  spiegelt in die `td`-Dicts zurück. → C.7 / C.8
- Rohstoffe/Krypto bekommen **nie** Fundamentals (`universe.is_commodity_or_crypto`):
  Finnhub löst `GOLD` als Aktie Gold.com Inc auf. Wochenjob und Phase 2b überspringen sie,
  Phase 1 liest für sie keinen Cache, der Wochenjob räumt Altbestand weg. → C.35
- Kurs-Sweep: Sammelabruf `/markets?epics=` in 20er-Chunks, dreistufige 429-Notbremse.
  Fehlender Live-Kurs = **kein** Skip (Fallback letzter finaler Close, WARNING). → P2.2
- Capital.com: `to` nie in der Zukunft (HTTP 400, `_not_in_future()`). Tages-Bar-`open`
  ≠ Eröffnungskurs (Bar ab 08:00 UTC; echter Open aus `MINUTE`-Bar). → P3.4
- Gap-Fill legt **keine** Historie an (nur Löcher; Fenster `GAP_SCAN_BARS = 220` =
  Ladefenster). Neuer Ticker braucht **erst** `historical_loader.py --tickers <X>`.
  Innenliegende Lücken zählen erst ab **zwei** Handelstagen. → B-12 / B.8
- Tests ausserhalb `tests/live/` telefonieren **nicht** (Autouse-Fixture sperrt auf
  Transport-Ebene). → P2.6

**Mail & Sonstiges**
- Resend: `2xx` heisst nur „angenommen"; echter Zustellstatus über `GET /emails/{id}`.
  Portfolio-Sektion **zuerst** in der Mail; davor nur der Kopf (Briefing-Box + eine
  Marktlage-Zeile: VIX, S&P-Tagesänderung, Regime — keine Sektion). → C.30
- `random/` ist Korbinians interner Ordner — **nie** anfassen, nie in Aufräum-,
  Doku- oder Toter-Code-Betrachtungen aufnehmen.
- Neuen Code dokumentieren (Modul-Docstring, 1–2-Satz-Funktions-Docstring). Tests
  nicht löschen/abschwächen (Coverage-Ziel 80 %). Kostendeckel
  `MAX_COST_PER_RUN_EUR = 6.00`, Warnschwelle `4.50`.

## Cron / Zeitpläne — die Fallen

Zeitplan und Run-Types stehen in `.github/workflows/analyze.yml`. Aktive Run-Types:
`pre_market`, `trade_proposals`, `final_close`, `weekly`.

- **DST:** GitHub Actions ist UTC-fix. Der Workflow fährt **nur die Sommerzeit**
  (bewusst, TODO im `schedule`-Block). Ab CET laufen `pre_market`/`weekly` 1 h früher,
  `trade_proposals` fällt aus; nur `final_close` (UTC-Bar-Grenze) gilt ganzjährig.
- `trade_proposals` hängt an der **US-Eröffnung** (10:10 America/New_York): nur der
  EDT-Slot ist geplant, der Workflow prüft `date +%z` und **überspringt** ihn bei EST.
- Zeit-/Kostenangaben im Workflow sind **Soll-, keine Ist-Werte** (Crons feuern
  ~35–40 min zu spät; Kosten zu niedrig geschätzt). → PROJECT_STATUS F.1 / P3.3 / C.26

## Nicht erratbare Befehle

Standard (`pytest tests/ --cov=src --cov-fail-under=80`, `python main.py --run-type
<typ>`) wie üblich. Nicht erratbar:

```bash
# historical_loader.py: genau EIN Modus-Flag ist Pflicht (--tickers / --all /
# --universe / --full-sp500 / --reactivate / --list-inactive / --report-coverage).
# Ohne Flag: argparse-Fehler, KEIN stiller MVP-Pull.
python setup/historical_loader.py --all              # nur die 20 MVP-Aktien
python setup/historical_loader.py --universe         # + Rohstoffe, Krypto, Sektor-ETFs
python setup/historical_loader.py --report-coverage  # Bars je Ticker, reine DB-Abfrage
python setup/historical_loader.py --list-inactive    # stillgelegte Ticker + Retry-Datum
python setup/historical_loader.py --reactivate AAPL MSFT

# Capital.com-Epics prüfen (manuell, read-only)
python setup/verify_epics.py --symbols SOXX VGT

# Live-Checks gegen echte APIs. Ohne --run-live übersprungen (kein ungefragter Mailversand).
pytest tests/live -m live_api --run-live      # nur lesend
pytest tests/live --run-live                  # inkl. echtem Mailversand
```

## Docker (nur manuelles Testen)

Kein Scheduler/Cron im Container — Automatik läuft ausschliesslich über `analyze.yml`.
Der Run-Type ist Pflicht; ohne Argument greift `CMD ["--help"]` und es startet
**keine** Pipeline. `docker-compose.yml` mountet `./data` → Läufe schreiben in die
echte DB. Gefahrlos experimentieren mit überschriebenem Mount:

```bash
docker compose run --rm -v /tmp/dbtest:/app/data trading-harry --run-type final_close
```
