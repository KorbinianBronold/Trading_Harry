# Shares_Future – Architektur & Design

**Zuletzt aktualisiert:** 2026-09-15 — 🛡️ **Phase-4a-Review (C.46): Portfolio-Check auf
Sonnet 5 mit deterministischem Snapshot.** `portfolio_check.build_snapshot()` baut in
beiden Läufen denselben dreiteiligen Payload (Technik aus `td`, Technik-Signal mit Skala
0-4, Phase-3-Analyse oder `null`; TP/SL einer Enthaltung fallen weg), die User-Message
trägt Datum und Run-Type, der Prompt eine Horizont-Regel statt des Intraday-Absatzes,
ANPASSEN darf ein einzelnes Level nachziehen und der Code prüft die Seite (ungültig →
HALTEN), Kappungen fängt `call_claude_retry_on_truncation`, und `pending_rows()` hält
die Positionen ab Phase 1c als `NICHT GEPRUEFT` im Payload (Spec-7.1-Muster mit `out`).
Modell: Sonnet 5 statt Haiku 4.5 (Entscheidung Korbinian). In diesem Dokument geändert:
Phase-4a-Box, Modul 7. Details: PROJECT_STATUS **C.46**.

Davor, 2026-09-14 — 🎯 **Phase-4-Review (C.45): Entscheidungswerte
aus dem Snapshot statt aus dem Modell-Echo.** `entry_price`/`price_premarket` und
`intraday_range_pct` kommen jetzt aus dem Phase-1-Snapshot, `rr_ratio`/`tp_pct`/`sl_pct`
werden im Code aus den Preisen abgeleitet (`ranking._normalise_from_snapshot()`, arbeitet
auf einer Kopie); die Guardrails prüfen die abgeleiteten Werte, `data_quality` kommt als
Parameter aus dem Snapshot (die Regel war tot). Neu: weicher `check_tp_reach`
(`tp_beyond_range`, beide Läufe), `_checks` an jeder Ranking-Zeile und als Flags in der
Morgenmail, `core_overflow` in `divergence_stats`, Quellen als distinkte Domains, VIX
`>=`, unbekannte `direction` hart verworfen, `MIN_INTRADAY_RANGE_PCT` in `config`.
In diesem Dokument geändert: Phase-4-Box, Module 6, 10 und 10a. Details: PROJECT_STATUS
**C.45**.

Davor, 2026-08-20 — 🧊 **Trainingsdaten-Fundament (C.20).**
`predictions` friert jetzt zusätzlich den **Wissensstand** ein: Fundamental-Rohwerte,
Analysten-Konsens samt Periode und `relative_strength` (sieben neue Spalten).
Grund: `fundamentals_cache` hält nur eine Zeile je Ticker und überschreibt sie —
es gab nie eine Historie. Die Retention der vier befristeten Tabellen läuft über
`config.LEARNING_RETENTION_DAYS` (730) statt über vier SQL-Literale;
`news_summaries` stand als einzige auf 30 Tagen. Details: PROJECT_STATUS **C.20**.

Davor, 2026-08-20 — 🧠 **Migration auf Claude 5 (Sonnet 5 / Opus 5)
inklusive Neukalibrierung aller Token-Decken.** In diesem Dokument geändert: die
`max_tokens_for_batch()`-Formel (jetzt `n * 6000 + 200`, der 4096er-Boden bindet nicht
mehr) und der C.10/C.11-Kalibrierungsblock bei Modul 4. Hintergrund: `call_claude()`
setzt kein `thinking`-Feld — bei `claude-sonnet-4-6` hiess das „kein Denken", bei
`claude-sonnet-5` heisst es „adaptives Denken an", und Denk- wie Antworttokens teilen
sich dieselbe Decke. Neu ist ausserdem `utils.call_claude_retry_on_truncation()`, das
den drei Einzelcall-Modulen (`trend_analyzer`, `market_context`, `revalidation`)
überhaupt erst eine Kappungs-Erkennung gibt — bei `trend_analyzer` riss eine Kappung
vorher den ganzen Lauf mit. Details: PROJECT_STATUS **C.18**.

Davor, 2026-08-18 — 🗑️ **Run-Type `close` ersatzlos entfallen.**
Die TP/SL-Auswertung gehört seit dem Preismodell-Umbau in `final_close` (00:15 UTC) —
der Aufruf in `close` war ein liegen gebliebenes Duplikat und sah um 22:30 eine noch
nicht finale Tagesbar. Danach blieb in `run_close()` nichts übrig, das `pre_market`
um 15:00 nicht ohnehin täte: `cleanup_old_data()` läuft dort direkt nach
`init_schema()`, der Gap-Fill im selben `collect()`-Pfad, und die
`technical_indicators`-Zeile ist **wertgleich** — jede Indikator-Funktion bekommt
ausschliesslich finale Bars bis D-1, der Live-Kurs landet nur in `td["price"]` und
wird nie persistiert. Es gibt daher keine „tagsüber aktualisierten" Indikatoren.
Aktive Run-Types sind jetzt `pre_market`, `trade_proposals`, `final_close`, `weekly`.
Details: PROJECT_STATUS **C.14**.

Davor, 2026-08-18 — ✅ **Sprint 3C / Plan 3b (Ranking) abgeschlossen:
12/12 Tasks, Gesamt-Review + Fix-Welle + Re-Review sauber, live verifiziert
(PROJECT_STATUS C.13).** Neu in diesem Dokument: Modul 6 (`src/ranking.py`) auf
`rank_score`/`candidate_class` statt `probability_pct`-Sortierung umgeschrieben,
`signal_context`-Parameter ergänzt, die Mutations-Invariante gegenüber Phase 4a
explizit dokumentiert. Der Gesamt-Review über alle 12 Commits fand zwei
Critical-Befunde an den Nähten zwischen Plan 3a und 3b — `analysis_strength()` zählte
für jeden Short verkehrt herum (Polaritäts-Kollision mit den aktiven v2-Prompts),
`candidate_class` ging beim 16:10-Ablösen einer Divergenz-Prediction verloren — beide
plus drei Important-Befunde in einer Welle behoben, re-reviewed sauber. Sprint 3C ist
damit **abgeschlossen** (Fundament, Trichter, Batch-Tiefenanalyse, Ranking); als
Nächstes Sprint 3D (Learning Modul, braucht eigene Planungssession).

Davor, 2026-08-17 — ✅ **Sprint 3C / Plan 3a (Batch-Tiefenanalyse)
abgeschlossen: 11/11 Tasks, live verifiziert, Abschluss-Review durchgeführt
(PROJECT_STATUS C.9–C.11).** Neu in diesem Dokument: **Phase 3 ist eine Batch-Phase**
(Grafik + Modul 4 neu beschrieben — `build_batches()` / `analyze_batch()` /
`analyze_batches()`, `analyze_asset()` und `analyze_assets()` sind ersatzlos entfallen),
die beiden **v2-Prompts** in der Prompt-Tabelle, und die Test-Baseline auf 777.
Der erste Testlauf hatte `MAX_TOKENS_DEEP` widerlegt — `stop_reason=max_tokens` trat
wiederholt auf, bis hinunter zu 2-Ticker-Batches. **Nach der Neukalibrierung**
(`TOKENS_PER_TICKER_DEEP` 900 → 2500, `BATCH_TOKEN_RESERVE` 2000 → 200, Wiederholung
nach Kappung mit doppelter Decke) trat im Verifikationslauf **kein einziges**
`max_tokens` mehr auf: 12 von 12 Kandidaten analysiert, Phase 3 bei **0,0204 EUR je
Ticker** — der angezielte Kostenhebel (Ziel 0,034 EUR) ist damit **unterboten**.
`BATCH_SIZE_DEEP = 8` bleibt trotzdem ein unbestätigter Startwert (47–54 % Auslastung
gemessen, nicht auf Optimalität getestet). Ebenfalls behoben: `web_search_calls` hatte
**zwei** unabhängige Zählfehler (dict-statt-Objekt und fehlendes `usage`-Feld im
Streaming-Pfad) und stand dadurch strukturell immer auf 0.

Davor, 2026-08-15 — **Sprint 3C / Plan 2 (Trichter) abgeschlossen
inkl. Abschluss-Review (13/13 Tasks, vier behobene Review-Befunde — PROJECT_STATUS C.8).**
Neu daraus in diesem Dokument: **Phase 2b** als eigene Box in der Pipeline-Grafik (sie war
nie verdrahtet), die Klarstellung, dass die Finnhub-Drosselung je **Request** zählt statt
je Methodenaufruf, sowie `tech_strength` + 180-Tage-Retention bei `cutoff_log`.

✅ **Der Trichter ist live**: `quick_filter.py` ist aus `run_pipeline()` verschwunden
(Modul 3 unten als „ersetzt" markiert), `broad_scan.py` + `cutoff_candidates()` (Modul 3b)
+ `run_phase_2b()` laufen und sind gegen echte Daten gemessen (3,3551 EUR, günstiger als
der alte Weg). `run_weekly()` füllt `fundamentals_cache` + `earnings_next_date` für alle
Aktien des Universums (Rohstoffe/Krypto nie, C.35). Plan 2 ist damit abgeschlossen; als Nächstes Plan 3 (Analyse & Ranking).
Stand: PROJECT_STATUS **C.7** und **C.8**.

Davor, 2026-08-15 — Live-Verifikation von Plan 2 (Sprint 3B) abgeschlossen
(PROJECT_STATUS P2.12): `pre_market` → `trade_proposals` → `close` liefen zu den echten
Cron-Zeiten, E3 (Ablösung) und E5 (kein Gegenpositionshandel) bestätigt. Dabei gefunden und
geschlossen: `predictions` erzwingt jetzt über einen partiellen UNIQUE-Index
`ux_predictions_one_open_per_idea` (`WHERE status='open'`), dass je Trade-Idee genau eine
offene Zeile existiert — s. Abschnitt „Eine offene Prediction je Trade-Idee" unten und
PROJECT_STATUS P2.13. `record_revision()` verlor dabei ihren `superseded_by`-Parameter;
Ablösen kann seither ausschliesslich `supersede_prediction()`.

Davor, 2026-08-12 — Sprint 3C / Plan 1 (Fundament) nachgezogen: zwei
neue Module (`src/indicators.py`, `src/technical_signal.py`), 29 neue Spalten in
`technical_indicators`, Ladefenster-Invariante, Testzahlen auf 647. **Keine
Verhaltensänderung** — Details PROJECT_STATUS C.6. ⚠️ Diese Garantie war zwischenzeitlich
gebrochen (die 29 neuen Werte liefen in vier Claude-Prompts mit) und ist erst mit dem
abschliessenden Review-Fix-Wave wieder wahr — s. PROJECT_STATUS C.6 für den Befund.

Davor, 2026-08-09 — `src/universe.py` als eine Quelle des Ticker-
Universums, Historien-Guard, erweiterte Invariantenliste, Testzahlen auf 608.

> **Dieses Dokument beschreibt den IST-Zustand des Codes.**
>
> ✅ **Stand 2026-08-04:** In Task 20 auf Sprint 3B / Plan 2 nachgezogen. Die frühere
> Abweichungsliste ist eingearbeitet und deshalb entfallen — Phasen 1c/1d, die
> getauschte Reihenfolge 4 → 4a, `analyses_by_ticker` und die beiden neuen Module
> `src/signal_checks.py` / `src/revalidation.py` stehen jetzt im Text selbst.
>
> ✅ **Live-Verifikation abgeschlossen (2026-08-14, PROJECT_STATUS P2.12).**
> `pre_market` → `trade_proposals` → `close` liefen zu den echten Cron-Zeiten gegen eine
> Wegwerf-Kopie, mit echten API-Calls und echtem Mailversand. ✅ **`analyze.yml` seit
> 2026-08-18 wieder aktiv** (manuell reaktiviert nach `bootstrap-db`, erster Lauf gelaufen).
> Einzig `weekly` ist zugestellt, aber nicht inhaltlich geprüft.
>
> Historische Abschnitte weiter unten (Sprint 1 / Sprint 2) sind bewusst nicht
> umgeschrieben — sie sind als Historie gekennzeichnet.

## Überblick

Das System folgt einer **Pipeline-Architektur** mit den Phasen 0, 0b, 1, 1c, 1d, 2, 2a, 3, 4, 4a, 5, die sequenziell ausgeführt werden. Jede Phase ist entkoppelt über klare Daten-Schnittstellen und kann unabhängig getestet werden.

**Reihenfolge beachten:** Ranking (Phase 4) läuft seit B.5 **vor** dem Portfolio-Check (4a), nicht danach. Phase 4a bekommt dadurch die fertigen Phase-3-Analysen und braucht keinen eigenen `web_search`.

### Die zentrale Trennung: Historie gegen Snapshot

Seit dem Preismodell-Umbau (2026-08-07, PROJECT_STATUS P3) sind zwei Dinge sauber
getrennt, die vorher dieselbe Quelle hatten:

| | Wofür | Wo |
|---|---|---|
| **Indikator-Historie** | RSI, ATR, SMA, MACD — braucht abgeschlossene Tage | `price_history` — **ausschliesslich finale Tagesbars** |
| **Entscheidungs-Snapshot** | Der Kurs, zu dem eine Aussage getroffen wurde | `predictions.price_premarket` / `price_open` / `price_1610` |

**`price_history` nimmt ausschliesslich finale Tagesbars auf.** Die Vermischung beider
Begriffe war der Frozen-Bar-Bug: der 15:00-Lauf schrieb eine Pre-Market-Quote als
„Tagesbar" fest, und alles Spätere las sie als Tatsache.

Es gibt **drei** Schreiber, alle an dieselbe Regel gebunden — **nie der laufende Tag**:

| Schreiber | Rolle |
|---|---|
| `main.run_final_close()` | der einzige im Normalbetrieb, 00:15 UTC täglich, `upsert` |
| `setup/historical_loader.py` | manueller Backfill (`--universe`, `--tickers`, …) |
| `data_collector._fill_price_gaps()` | Sicherheitsnetz nach Ausfällen; greift im Normalbetrieb nicht |

⚠️ Ältere Fassungen dieses Dokuments sprachen von „genau EINEM Schreiber" und nannten den
Gap-Filler nicht. Sachlich falsch — die **Regel** ist einheitlich, die Zahl der
Schreibstellen ist es nicht (korrigiert 2026-08-09).

⚠️ **Wochenend-Teilbars (C.36, 2026-09-11):** Capital.com liefert Rohstoffen eine Sonntagsbar
aus einer Stunde Sitzung (Öffnung So 23:00 UTC; Gold Ø 0,56 % Spanne gegen 2,5 % werktags).
Sie drückte `intraday_range_pct` (Mittel der letzten 5 Bars) und ATR und kippte Gold in ruhigen
Phasen unter den 1-%-Guardrail. Alle drei Schreiber verwerfen Sa/So-Bars von Instrumenten ohne
Wochenendsitzung über `universe.is_partial_weekend_bar()` (nur Krypto hat eine:
`has_weekend_sessions()`); `run_final_close()` räumt Altbestand per `db.delete_weekend_bars()`
bei jedem Lauf weg. Bewusster Verzicht: der Evaluator (`load_price_history_after`) sieht für
Rohstoffe die Handelsstunde So 23–24 UTC nicht mehr.

Konsequenz: `price_history` endet zur Laufzeit der Analyse-Läufe bei **D-1**. Der
Entscheidungskurs kommt deshalb live über `get_premarket_price()`, nicht aus dem letzten
DB-Close.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR (main.py)                            │
│ Dispatch: --run-type {pre_market|trade_proposals|close|final_close|weekly}│
└──────────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  PHASE 0: TREND-ANALYSE                          │
│  Input: —                                                         │
│  Claude: 1× Sonnet + web_search                                  │
│  Output: {trends[], sector_rotation, trend_summary}              │
│  Cost: ~0.20 EUR                                                 │
│  Fail: ❌ Abort (TrendAnalyzerError propagates, no email)        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│         PHASE 1: DATENSAMMLUNG (Gate → Sweep → Process)         │
│  Input: —                                                         │
│  Gate: deaktivierte Ticker raus (Rohstoffe/Krypto ausgenommen)   │
│  Sweep: EIN Batch-Call für alle Live-Kurse (20er-Chunks)         │
│  Process: Indikatoren aus 220 DB-Tagen, Technik-Signal → Sidecar│
│  Quelle: Capital.com (alleiniger OHLC-Provider, kein Fallback)   │
│  Berechnen: RSI-14, MACD, ATR, SMA200, PE, Volume-Ratio, etc.   │
│  Output: (results, skipped, sidecar) — sidecar NIE in td, s.     │
│          Sidecar-Invariante in CLAUDE.md                         │
│  Cost: ~0.00 EUR                                                 │
│  Fail: ✅ Skip Ticker, continue                                   │
│  DB: technical_indicators-Table persistieren                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│      PHASE 1c: OFFENE POSITIONEN ALS PFLICHT-KANDIDATEN          │
│  Capital.com GET /positions → Epics über die Reverse-Map auf     │
│  Ticker zurückführen. Diese Ticker gehen garantiert in Phase 3,  │
│  auch wenn der Cutoff sie aussortiert hätte — sonst verliert     │
│  man die Analyse zu einer Position, die man hält.                 │
│  Cost: ~0.00 EUR | Fail: ✅ leere Liste, continue                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│          PHASE 1d: SEKTOR-MOMENTUM (zwei Signale)                │
│  ETF-Momentum (Capital.com, je Sub-Sektor-ETF) und              │
│  DB-Momentum (Durchschnitt der Ticker aus ticker_sectors).      │
│  Werden GETRENNT gespeichert und nie verrechnet — 3D soll       │
│  messen, welches besser predictet.                               │
│  DB: sector_momentum | Cost: ~0.00 EUR                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│           PHASE 2: NACHRICHTEN-SCAN (broad_scan_batch)           │
│  Seit Sprint 3C / Plan 2, Task 10 (2026-08-15) — ersetzt         │
│  quick_filter_batch(), s. Modul 3/3b weiter unten                │
│  Input: sp500_tds[], sidecar, trend_context, market_context,     │
│         date, run_type (C.39: Datumsanker fürs 24-48h-Fenster)   │
│  Nutzlast je Ticker: ticker, sector, premarket_change_pct,       │
│         earnings_in_days — keine Technik, kein Kurs (C.39)       │
│  Claude: 1× Haiku + web_search (max 5) über ALLE Ticker         │
│  Output: {ticker: {news_strength: 0-3, news_note}}               │
│  Fail: ✅ unparsebar → ganzer Batch auf news_strength=0           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              PHASE 2a: CUTOFF (cutoff_candidates)                │
│  Kandidat: news_strength ≥ 1 ODER tech_strength ≥                │
│            TECH_MIN_FOR_DEEP (= 2), Pflicht-Kandidaten vorn       │
│  Sortierung: (news_strength, |premarket_change_pct|,             │
│              tech_strength, ticker), Deckel MAX_DEEP_ANALYSIS    │
│  ✅ MAX_DEEP_ANALYSIS = 50 wird seit Task 10 gelesen              │
│     (vorher 80, tot; BATCH_SIZE_QUICK entfernt)                  │
│  Output: (selected, all_evaluated) → db.log_cutoff() schreibt    │
│          BEIDE (3D braucht den 51. neben dem 50.)                │
│  Cost: 0 EUR (reiner Code)                                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│        PHASE 2b: FUNDAMENTALDATEN DER KANDIDATEN                 │
│  data_collector.run_phase_2b() — nur fuer die Cutoff-Auswahl     │
│  1. fehlende Fundamentals bei Finnhub nachladen (0 Calls, wenn   │
│     der Cache warm ist — Normalfall dank Wochenlauf)             │
│  2. Werte in die td-Dicts zurueckspiegeln: ohne das waermte 2b   │
│     nur den Cache fuer MORGEN, der heutige Prompt saehe None     │
│  3. data_quality medium->high neu einstufen (Spec 18.1f);        │
│     Rueckstufung auf 'low' ausgeschlossen                        │
│  Rohstoffe/Krypto: nie dabei (Spec 6.3 — Finnhub hat nichts)     │
│  Fail: ✅ nicht fatal, kostet nur Kontext-Qualitaet               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│            PHASE 3: POLICY-MONITOR (1× pro Run)                  │
│  Input: —                                                         │
│  Claude: 1× Sonnet + web_search                                  │
│  Output: {policy_risk_level low|medium|high, events[], summary} │
│  Scope: Tariffs, Zentralbank, Geopolitik, Regulierung          │
│  Persist: policy_risk_level -> market_context (Backfill),        │
│           Events -> news_summaries (source=policy_monitor, C.41) │
│  Cost: ~0.21-0.25 EUR (gemessen 2026-09-13, 4-5 Websuchen)      │
│  Fail: pre_market ❌ PolicyMonitorError nicht gefangen -> Lauf   │
│        bricht ab (nur der Kappungs-Retry aus C.18 schuetzt);     │
│        trade_proposals ✅ leerer Kontext ('unknown'), weiter     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│      PHASE 3: BATCH-TIEFENANALYSE (≤ MAX_DEEP_ANALYSIS Ticker)   │
│  Input: selected (nur die Cutoff-Auswahl!), cutoff_by_ticker,    │
│         trend_context, policy_context                            │
│  Batching: build_batches() gruppiert nach SUB-SEKTOR, packt      │
│    ganze Sub-Sektoren per First-Fit-Decreasing bis               │
│    BATCH_SIZE_DEEP (8); zerrissen nur, wenn einer allein         │
│    darueber liegt. Deterministisch sortiert (3D-Vergleichbarkeit)│
│  Claude: Sonnet × 1 Call PRO BATCH + web_search, gestreamt       │
│  max_tokens: n × TOKENS_PER_TICKER_DEEP + Reserve, min 4096      │
│  Output: (analyses[], failed_tickers[])                          │
│  8-Dim Score: market_env, company_quality, valuation, momentum, │
│              risk, sector_trend, catalyst, policy_risk           │
│  Fail: stop_reason=max_tokens ODER unparsebar → DeepAnalysisError│
│    → 1× wiederholen → 1× halbieren → aufgeben (Ticker in failed) │
│    ⚠️ Ein abgeschnittener Batch wird NIE teilverwertet           │
│  Guardrails: R/R ≥ 1.5, hold_days ≤ 5, intraday_range ≥ 1%,   │
│    Zwei-Belege-Pflicht — ausser evidence_quality == "thin"       │
│  ⚠️ NICHT PRODUKTIONSREIF: max_tokens trat im Testlauf bis       │
│     hinunter zu 2-Ticker-Batches auf (PROJECT_STATUS C.9)        │
│  Order: Sequential (nicht parallel) für deterministisches Cost-Tracking│
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│      PHASE 3b: COMMODITIES & CRYPTO (7 Fixed Assets)             │
│  Input: trend_context, policy_context, date/run_type (C.43),    │
│         je Asset {snapshot ohne Aktien-Felder, technical_signal} │
│  Assets: Gold, Silver, Brent, BTC, ETH, SOL, XRP                │
│  Claude: Sonnet × 2 Calls (je asset_class, C.15) + web_search   │
│  Output: list[{ticker="GOLD", direction, scores{8}, extra}]     │
│  Extra Context (aus dem Code, C.43): fear_greed_value,          │
│         gold_silver_ratio (Snapshots), btc_dominance_pct (API)  │
│  Cost: ~0.35 EUR                                                 │
│  Guardrails: Same as Phase 3 (8-Dim, R/R, hold_days, range)    │
│  Fail: ✅ Batch (bis 4 Assets) als missing, Lauf geht weiter     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│         PHASE 4: RANKING & PERSISTIERUNG                         │
│  Input: deep_analysis[], commodities_crypto[], signal_context    │
│  Logik: Snapshot-Normalisierung (Entry/Range aus td, R/R+Pct   │
│         aus Preisen, C.45) → Guardrails → B.3-Checks →          │
│         core/divergence/conflict → Top-10 je Richtung nach      │
│         rank_score = analysis_strength × tech_strength (C.13)   │
│  Checks: src/signal_checks.py (VIX, Sektor-Momentum, Klumpen,  │
│          Earnings, Stop-Distanz, TP-Reichweite) — erhoben in   │
│          beiden Läufen, enforce nur 16:10 (_revalidate_all);   │
│          Gap + Stop-Budget nur 16:10                            │
│  Output: {top_long[], top_short[], commodities_crypto[],        │
│           divergence[], divergence_stats} (+ _checks je Zeile)  │
│  DB: predictions + guardrail_rejects schreiben                   │
│  Learnable: Alle = true (außer skip-by-guardrails)             │
│  Cost: ~0.00 EUR                                                 │
│  Fail: ❌ Propagates (Ranking MUSS funktionieren)               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│       PHASE 4a: PORTFOLIO-CHECK (Capital.com-Positionen)         │
│  ⚠️ Läuft seit B.5 NACH Phase 4 — kein eigener web_search.      │
│  Input: positions aus Phase 1c (LIVE bei Capital.com, C.37),    │
│         build_snapshot(td, Sidecar, Phase-3-Analyse|null) je    │
│         Ticker (C.46, beide Läufe gleich), trend/policy_context │
│  User-Message: "Today is <date>. Run type: <run_type>." (C.46)  │
│  Claude: Sonnet 5 × N offene Positionen, OHNE web_search,       │
│          call_claude_retry_on_truncation (Decke 6144)           │
│  Output: list[{deal_id, action="HALTEN|SCHLIESSEN|ANPASSEN|     │
│                KEINE ANALYSE|NICHT GEPRUEFT", ...}]              │
│  ANPASSEN: >= 1 Level; Seite wird im Code geprüft, ungültig →   │
│            HALTEN mit Hinweis in reason (C.46 / F51)            │
│  Hinweis: liest `predictions` NICHT — Predictions sind Papier-  │
│           Vorschläge fürs Lernmodul, keine Positionen.           │
│  positions=None (Abruf gescheitert): keine Empfehlungen,        │
│           Mail sagt „nicht abrufbar". Abbruch vor/in 4a:        │
│           Positionen bleiben als NICHT GEPRUEFT sichtbar (F53). │
│  Cost: ~0.03 EUR je echter Position (Sonnet; Haiku war 0.006)   │
│  Fail: ✅ Position bleibt NICHT GEPRUEFT, continue              │
│  DB: position_checks (je Deal, ohne Leser: 3D-Historie);        │
│      position_recommendations tot                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│   CLOSE RUN: Schlusskurse ALLER Ticker + TP/SL-Auswertung        │
│   + cleanup_old_data()  (kein Claude, kein Mail)                 │
│   WEEKLY RUN: Aggregate + Wochenmail                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              PHASE 5: E-MAIL & REPORTING                         │
│  Input: top_10_long, top_10_short, commodities_crypto,          │
│         yesterday_outcomes_agg, cost_summary                     │
│  HTML: 4 Sektionen (Portfolio → Stocks → Trends → Commodities)  │
│  Resend: E-Mail an EMAIL_TO                                      │
│  Cost: ~0.00 EUR (Freikontingent)                               │
│  Fail: ⚠️ Log, aber keine Abort (beste Anstrengung)             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Module & Responsibilities

### 1. **`src/data_collector.py`** (Phase 1)

Datensammlung für 500 SP500-Aktien + Commodities/Crypto. **Seit Sprint 3C / Plan 2, Task 5
(`aea3656`) in drei Pässen** statt einer Schleife mit einem Kurs-Call je Ticker.

```python
def collect(
    tickers: list[str],
    price_provider: DataProvider,
    earnings_provider: DataProvider,
    conn,
    date: str,
    run_type: str,
) -> tuple[list[dict], int, dict[str, dict]]:
    """Returns: (ok_data, skipped_count, sidecar)"""
```

| Pass | Funktion | Was passiert |
|---|---|---|
| **1a Gate** | `_gate_phase()` | wirft dauerhaft deaktivierte Ticker heraus, **bevor** ein API-Call fällt. Die Bar-Zählung bleibt bewusst draussen (Spec § 18.1a): sie sitzt hinter `_fill_price_gaps()`, sonst fielen Ticker heraus, die nach dem Nachladen genug Bars hätten. Rohstoffe und Krypto sind von der Deaktivierung ausgenommen (§ 6.1) — nur WARNING statt Rauswurf |
| **1b Sweep** | `_sweep_phase()` | **ein** Batch-Call für die Live-Kurse aller Survivors. Provider ohne Batch-Unterstützung werfen `NotImplementedError`, der Sweep fängt das ab und liefert ein leeres Dict — dann fällt jeder Ticker auf seinen letzten finalen Close zurück, **keiner wird deswegen übersprungen**. Über 20 % Survivors ohne Live-Kurs → WARNING |
| **1c/1d** | `_process_ticker()` | Indikatoren aus den letzten 220 DB-Bars, Technik-Signal, Fundamentals **nur aus dem Cache**. Übernimmt den Sweep-Kurs statt selbst anzufragen |

Die einzigen Capital.com-Calls der 1c-Schleife sind die Gap-Fills (`_fill_price_gaps()`, nur bei erkannter Lücke). Die Batch-Pause (`BATCH_PAUSE_EVERY = 30`, `config.CAPITAL_COM_BATCH_PAUSE = 12 s`) zählt seit 2026-09-10 (C.32) **diese Calls**, nicht die Ticker-Position: `_fill_price_gaps()` meldet jeden Versuch in `GapFillStats`, `collect()` schläft nach je 30 Versuchen, nie nach dem letzten Survivor. Ohne Lücke schläft ein Lauf gar nicht — vorher fix alle 30 Ticker, bei 150 Tickern ~48 s Leerlauf.

**Der dritte Rückgabewert ist der Sidecar** — ein Dict `ticker → {premarket_change_pct,
tech_direction, tech_agreement, tech_adx_band, tech_strength}`. Er existiert, weil `td`
unverändert in vier Claude-Prompts serialisiert wird; s. „Sidecar-Invariante" unten und
CLAUDE.md.

```python
def fetch_missing_fundamentals(tickers, earnings_provider, conn, date) -> ...
    """Phase 2b: holt Fundamentals für Kandidaten mit Cache-Miss nach.
    Gebaut (Task 7), noch NICHT verdrahtet — das ist Task 10."""
```

**Invarianten:**
- Mindestens 20 Zeilen historische Daten pro Ticker (`MIN_BARS_RSI`)
- `intraday_range_pct` = (High - Low) / Close × 100 (letzte 5 Tage)
- `above_sma200` = (Price - SMA200) / SMA200 × 100
- RSI-14, MACD, ATR berechenbar (oder `data_quality=low`)
- **Phase 1 ist Finnhub-frei:** `fundamentals_cache` wird nur gelesen, 0 Calls.
  `get_earnings_calendar()` kommt im Tageslauf nicht mehr vor, `earnings_beat_pct` ist
  dort dauerhaft `None`. `earnings_next_date` liegt als ISO-Datum im Cache,
  `earnings_in_days` wird beim Lesen gerechnet
- ⚠️ **Sidecar-Invariante:** neue Werte gehören **nie** in `td`. `td` wird in
  `quick_filter`, `deep_analysis`, `commodities_crypto` und über `main.py`s `snapshots`
  auch `portfolio_check` `json.dumps`'t — ein zusätzlicher Schlüssel ändert stillschweigend
  vier Prompts. Die 29 Plan-1-Indikatoren liegen deshalb in `extra_indicators` und kommen
  erst unmittelbar vor `_persist_indicators()` dazu; ein Test pinnt die Schlüsselmenge

---

### 1b. **`src/indicators.py`** (neu, Sprint 3C / Plan 1 Fundament, 2026-08-12)

Die 17 technischen Indikatoren aus der Spec als reine Funktionen über ein OHLCV-DataFrame
(Spalten `Open/High/Low/Close/Volume`, gross geschrieben — wie
`db.load_price_history_from_db()` liefert). **Kein Provider-, DB- oder Netzzugriff.** Aus
`data_collector.py` herausgelöst (`d9136c6`, `0e91225`), weil dort Indikatormathematik mit
Provider- und DB-Verdrahtung vermischt war — reine Verschiebung, Testzahl unverändert.

```python
def compute_rsi_14(df) -> float | None: ...
def compute_macd_raw(df) -> dict[str, float | None]: ...      # {macd_line, macd_signal_line, macd_hist}
def compute_adx(df) -> dict[str, float | None]: ...           # {adx_14, di_plus, di_minus}
def compute_psar(df) -> dict[str, float | str | None]: ...    # {psar_value, psar_dir}
def compute_ichimoku(df) -> dict[str, float | None]: ...      # 5 Linien
def compute_stochastic(df) -> dict[str, float | None]: ...    # {stoch_k, stoch_d}
def compute_bollinger_raw(df) -> dict[str, float | None]: ... # {bb_upper, bb_lower, bb_width}
def compute_donchian(df) -> dict[str, float | None]: ...      # {donch_upper, donch_mid, donch_lower}
def compute_trix(df) -> dict[str, float | None]: ...          # {trix, trix_signal}
def compute_willr(df) / compute_cci(df) / compute_momentum(df) / compute_atr_abs(df) / compute_obv(df) -> float | None: ...
def compute_ema_distance_pct(df, length) -> float | None: ...
```

Jede Funktion trägt ihre eigene `MIN_BARS_*`-Schwelle (10 für PSAR bis 78 für Ichimoku)
und liefert unterhalb davon `None` statt eines unsicheren Werts.

⚠️ `compute_obv` beruht auf `lastTradedVolume` — einem CFD-Broker-Proxy von Capital.com,
nicht auf Börsenvolumen. Als Richtungsmaß brauchbar, als Niveauaussage nicht.
⚠️ Fehlende Werte sind `None`, nie `0` — eine Null wäre eine erfundene Messung.

Verdrahtet in `data_collector._process_ticker()` (`5e9a9ec`); die Ergebnisse füllen 29
Spalten in `technical_indicators` (s. Modul 11).

---

### 1c. **`src/technical_signal.py`** (neu, Sprint 3C / Plan 1 Fundament, `f65777a`)

Richtung (`long`/`short`/`neutral`) und zählbare Stärke (0–4) aus drei abstimmenden
Teilindikatoren — RSI als Momentum (nicht Mean-Reversion), MACD über das
Histogramm-Vorzeichen (nicht die Kreuzung), SMA-Trend (Kurs > SMA50 **und** Kurs >
SMA200 — zwei unabhängige Kurs-zu-SMA-Distanzen, **kein** Vergleich von SMA50 gegen
SMA200, also kein Golden-/Death-Cross-Signal). ADX moduliert die Stärke (`weak` → eine
Stimme weniger, Boden 1; `strong` → +1, Deckel 4 — seit C.33, davor `weak` → fix 1),
**filtert aber nie die Richtung**. Das Label `td["macd_signal"]` aus Phase 1
(`compute_macd_signal()`) liest seit C.33 dieselben Rohwerte mit demselben Vergleich:
`bullish` / `bearish` / `neutral` statt der früheren Kreuzungs-Labels — eine MACD-Wahrheit
je Ticker. Deterministisch, kein
Claude-Call, keine DB, kein Netz — eine reine Funktion über das Phase-1-Snapshot-Dict,
deshalb tabellengetrieben ohne Mocking testbar.

```python
@dataclass(frozen=True)
class TechnicalSignal:
    direction: str  # "long" | "short" | "neutral"
    agreement: int  # wie viele der drei Teilindikatoren übereinstimmen
    adx_band: str   # "weak" | "normal" | "strong"
    strength: int   # 0-4

def compute(td: dict) -> TechnicalSignal: ...
```

Die drei Ablesungen sind bewusste Entscheidungen, keine zwingenden Herleitungen — welche
davon besser predictet, misst Sprint 3D aus der Outcome-Historie.

**Wird ab Plan 3 vom Ranking konsumiert — bis dahin ist das Signal berechenbar, aber
steuert nichts.**

---

### 2. **`src/trend_analyzer.py`** (Phase 0)

Makro-Trends identifizieren (einmalig pro Run).

```python
def analyze_trends(cost_tracker: CostTracker) -> dict:
    """
    1 Sonnet + web_search Call.
    Returns: {
        trends: [{name, strength:0-10, duration_estimate, summary, 
                 beneficiary_tickers[], negative_tickers[]}],
        sector_rotation: {into: [XLK], out_of: [XLU]},
        trend_summary: str
    }
    """
```

**Fail-Verhalten:** `TrendAnalyzerError` propagates → kein Email (Phase 0 ist fatal).

---

### 2b. **`src/market_context.py`** (Phase 0b, seit Sprint 3B / Plan 1)

Tagesaktueller Marktzustand (einmalig pro Run).

```python
def fetch_market_context(date, run_type, cost_tracker, price_provider=None) -> dict:
    """
    1 Sonnet + web_search Call -- nur im Morgenlauf (pre_market). Alle Keys immer
    vorhanden (CONTEXT_KEYS), nicht belegbare Werte None:
    {sp500_change_pct, vix_level, vix_source, advance_decline_ratio, market_regime,
     sector_rotation_in, sector_rotation_out, macro_summary}
    """

def vix_only_context(date, price_provider) -> dict:
    """
    Derselbe Schluesselsatz OHNE Claude-Call: nur vix_level/vix_source (Capital.com),
    alles andere None. Der 16:10-Lauf nutzt ausschliesslich diesen Weg (C.28).
    """
```

**VIX-Präzedenz:** Der numerische Capital.com-Bar schlägt Claudes recherchierte
Zahl; `vix_source` weist aus, welche Quelle gewonnen hat — seit C.28 auch in der
Tabelle (`market_context.vix_source`). Capital.com notiert einen VIX-**Future**-CFD,
~1,3 Punkte über Spot (P2.12); bei der Schwelle 25 ist die Quelle keine Nebensache.

**Seit C.28 (2026-09-08):** `advance_decline_ratio` wird nicht mehr erhoben (nie eine
belegbare S&P-500-Quelle, seit 13.08. immer NULL, kein Abnehmer ausser einer
Mail-Kontextzeile) — der Schlüssel bleibt, immer None. Neu erhoben wird
`sp500_change_pct` (Spalte seit Plan 1, war nie befüllt). Im Prompt: Regime über
Kriterien verankert, Rotation auf die 11 GICS-Sektoren begrenzt, Bezugsrahmen je
`run_type` (vorbörslich = Vortagesschluss + Overnight), `macro_summary` englisch und
ohne VIX-Zahl. Um 16:10 gibt es **keinen** zweiten Claude-Call mehr: der einzige dort
entscheidende Wert ist der VIX (`check_vix`, `enforce=True`); Rotation/Makro für den
Portfolio-Check kommen aus der Morgenzeile (`db.load_market_context()`) — seit C.30 in
**derselben Form** wie die rohe Phase-0-Antwort (`sector_rotation: {into, out_of}` als
Listen, `main._split_sectors()`), damit der Portfolio-Check morgens und um 16:10 dieselben
Schlüssel sieht; `macro_summary` bleibt ein eigener Key. Die 16:10-Mail-Sektion „Marktlage"
zeigt nur, was der Kontext trägt (VIX); der A/D-Zweig ist entfernt, die Tagesmail zeigt
die Marktlage seit C.30 als Zeile im Kopf.

**Seit C.31 (2026-09-10):** Die Regime-Regel definiert die Sektorgruppen einmal
(defensiv: Utilities, Consumer Staples, Health Care; zyklisch: IT, Consumer
Discretionary, Industrials, Financials, Energy, Materials; Real Estate und
Communication Services bewusst in keiner Gruppe) und kennt im `risk_off`-Zweig als
dritte hinreichende Bedingung „zyklische Sektoren am Tabellenende" — vorher blieb ein
Down-Tag ohne VIX > 20 und ohne führende Defensive immer `neutral` (Ölschock 10.09.).
Die Rotationsregel nennt die häufigsten GICS-Fehlzuordnungen (Alphabet/Meta/Netflix =
Communication Services, Amazon/Tesla = Consumer Discretionary, Visa/Mastercard =
Financials). Kein Konsument liest Rotation oder Regime als Guardrail — reine
Metadaten (`predictions.market_regime`, Mail-Zeile).

**Warum None statt Schätzung:** Die Werte steuern nachgelagert harte Risikofilter
(VIX > 25 nur noch `confidence='high'`, VIX > 35 keine neuen Longs). Ein geratener
Wert wäre dort schlimmer als gar keiner.

**Fail-Verhalten:** `MarketContextError` wird in `run_pipeline()` gefangen → der Run
läuft mit leerem Kontext weiter (Phase 0b ist **nicht** fatal). `CostCapExceeded`
propagiert dagegen wie gewohnt zum äusseren Handler.

---

### 2c. **`src/sector_momentum.py`** (seit Sprint 3B / Plan 1)

Zwei unabhängige Momentum-Signale je Sub-Sektor, getrennt gespeichert und **nie
verrechnet** — Sprint 3D soll datenbasiert messen, welches besser predictet.

```python
def collect_sector_momentum(conn, date, run_type, price_provider) -> dict[int, dict]:
    """{sector_id: {etf_momentum, db_momentum, ticker_count}}"""
```

- `etf_momentum` – Tagesperformance des Sub-Sektor-ETF von Capital.com für den letzten **abgeschlossenen** Handelstag (seit C.38/F17: der Bar des Lauftags ist eine Teilbar und zählt nicht; vorher maß der ETF „heute bis jetzt", der DB-Pfad gestern). Jeder ETF
  wird nur einmal abgerufen (21 Sub-Sektoren teilen sich 19 ETFs); die Bars landen
  in `price_history`, weil keine Phase-1-Ticker-Liste sie enthält.
- `db_momentum` – Ø Tagesperformance aller Ticker des Sub-Sektors, reines SQL,
  0 EUR. NULL unterhalb `config.SECTOR_DB_MOMENTUM_MIN_TICKERS = 3`.

**Nur Erhebung.** Die Guardrail-Auswertung (hartes Reject nur bei zwei
übereinstimmenden Signalen) gehört zu Plan 2.

---

### 3. **`src/quick_filter.py`** (Phase 2) — ✅ ersetzt, Modul bleibt im Repo

**Seit Sprint 3C / Plan 2, Task 10 nicht mehr Teil von `run_pipeline()`.**
`main.py` importiert `quick_filter_batch` nicht mehr; sein Nachfolger ist
`broad_scan.py` + `cutoff_candidates()` (Modul 3b unten). Die Datei selbst ist noch nicht
gelöscht — `tests/unit/test_quick_filter.py` deckt sie weiterhin ab, und ein Löschen ist
kein Bestandteil von Plan 2. Beschreibung unten als **historische Referenz**, kein
Ist-Zustand mehr.

Batch-Scoring ohne Web-Search (reduziert auf Top 80).

```python
def quick_filter_batch(
    batch: list[dict],  # Phase 1 data
    trend_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """
    Haiku Call (30er-Batch).
    Returns: [{ticker, long_score:0-10, short_score:0-10, 
              confidence, evidence[], exclude:bool}]
    
    Logik:
    - long_score ≥ 6.5 & short_score ≤ 4.0 → Long
    - short_score ≥ 6.5 & long_score ≤ 4.0 → Short
    - Sonst: beide Scores gleich, direction=none → Guardrail droppt
    """
```

**Fail-Verhalten:** `QuickFilterError` → skip Batch, continue mit nächstem.

---

### 3b. **`src/broad_scan.py`** (Sprint 3C / Plan 2 — ✅ live seit Task 10)

Phase 2: **ein** Sonnet-Call **mit Websuche** über alle Phase-1-Überlebenden, statt eines
Haiku-Calls ohne Websuche. Er liefert pro Ticker eine zählbare Nachrichtenstärke — **keine
Richtung und keine „lohnt sich"-Einschätzung.**

```python
def broad_scan_batch(ticker_datas, sidecar, trend_context, market_context,
                     cost_tracker, date, run_type) -> list[dict]:
    """→ [{ticker, news_strength: 0-3, news_note: str}] in Eingabereihenfolge"""
```

| `news_strength` | Bedeutung |
|---|---|
| 0 | keine Auffälligkeit |
| 1 | am Rande erwähnt |
| 2 | klarer Einzelticker-Katalysator |
| 3 | marktbewegend |

**Entscheidungen, die nicht aus dem Code folgen:**
- Die Nutzlast wird **explizit aus vier Feldern gebaut** (`ticker`, `sector`,
  `earnings_in_days` aus `td`, `premarket_change_pct` aus dem Sidecar), nicht aus `td`
  gedumpt. Seit C.39 (2026-09-11) **ohne** `price`, `price_change_1d/5d`, `rsi_14`,
  `atr_pct`: der Prompt verbot ihre Nutzung, das Modell rechnete sie trotzdem in die
  Stärke ein (MRVL Stärke 2 für „up 4.76 % on strong momentum"). Der Vorbörsen-Gap bleibt
  als einziger Kurswert — ein Level-3-Hinweis, die Stärke kommt aus der Ursache.
- **Datumsanker:** die User-Message beginnt mit „Today is {date}. Run type: …" — ohne ihn
  galt am 10.09. ein Downgrade vom 8. Januar als Nachricht (C.39, F22).
- **Trend-Echo zählt nicht:** Exposure zu einem Thema aus TREND CONTEXT ist keine
  Ticker-Nachricht (am 10.09. acht Energie-Titel mit „Iran conflict premium"); nur
  tickerspezifische, neue Information erreicht Stärke ≥ 1 (C.39, F21).
- **`news_note` ist Pflicht ab Stärke 1.** Fehlt der Beleg, setzt der Code die Stärke auf
  0: eine Stärke ohne Beleg ist nicht überprüfbar. Dasselbe für Werte ausserhalb 0–3,
  Nachkommaanteile und `bool` — sie werden auf 0 gezogen, nicht geklemmt.
- **Kein `technical_flag` vom Modell.** Das Technik-Signal ist Mathematik über
  `price_history`, kostet nichts und liegt für jeden Ticker vor; Sonnets Einschätzung
  derselben Zahlen wäre teurer, ungenauer und eine zweite Wahrheit für dieselbe Grösse.
- Ein **unparsebarer** Scan degradiert den ganzen Batch auf `news_strength=0` statt zu
  werfen (Spec § 10) — ein einzelner fehlender Ticker ebenso.
- ⚠️ `MAX_TOKENS = 24000`, und eine WARNING feuert bei Nähe zur Grenze. Ohne sie wäre ein
  wegen Kappung auf 0 degradierter Batch im Log nicht von einem echten ruhigen
  Nachrichtentag zu unterscheiden. Der begrenzende Faktor ist der 600-s-Client-Timeout,
  **nicht** ein SDK-Guard — den gibt es in `anthropic==0.42.0` nicht.

**Phase 2a — Cutoff, `cutoff_candidates()` (Task 9), live verdrahtet in `run_pipeline()`
(Task 10):** Kandidat = `news_strength ≥ 1 ODER tech_strength ≥ TECH_MIN_FOR_DEEP` (= 2),
Sortierung `(news_strength, |premarket_change_pct|, tech_strength, ticker)`, Schnitt bei
`MAX_DEEP_ANALYSIS` (50, seit Task 10 gelesen — vorher 80 und tot). Die ausgewählten
Kandidaten laufen seit Plan 3a **direkt** an `analyze_batches()` weiter — der
Interim-Adapter `adapt_cutoff_to_quick_filter()` ist entfallen, und Phase 3 sieht
ausschliesslich `selected` statt aller Ticker plus Exclude-Flag; **jeder** bewertete
Ticker (nicht nur die ausgewählten) landet über `db.log_cutoff()` in der Tabelle
`cutoff_log` — 3D braucht die volle Liste, um den 51. mit dem 50. zu vergleichen. Die
Rohstoffe/Krypto umgehen Scan, Cutoff und 2b komplett (§ 18.3), Pflicht-Kandidaten aus
Phase 1e stehen vorn und zählen gegen den Deckel.

✅ **Live gegen echte Daten gemessen (2026-08-15, 20 MVP-Ticker):** 3,3551 EUR gesamt,
kein `CostCapExceeded` — günstiger als der alte Weg über `quick_filter` (3,9217 EUR).
15 von 20 Tickern qualifizierten, die 5 ausgeschlossenen wurden in Phase 3 tatsächlich
übersprungen. Details: PROJECT_STATUS C.7, Befund 9.

---

### 4. **`src/deep_analysis.py`** (Phase 3) — ⚠️ Batch-Phase seit Plan 3a

Tiefenanalyse mit Web-Search (8-dimensionales Scoring), **gebatcht nach Sub-Sektor**.
`analyze_asset()` und `analyze_assets()` (1 Call je Ticker) sind **ersatzlos entfallen** —
ein Test pinnt ihre Abwesenheit, damit sie nicht versehentlich zurückkehren.

```python
def run_policy_monitor(date, run_type, cost_tracker) -> dict:
    """
    1 Sonnet + web_search Call EINMALIG pro Run.
    Returns: {policy_risk_level: 'low'|'medium'|'high'|'unknown', events:[], summary:str}
    policy_risk_level wird normalisiert (C.41): lower(), Whitelist, sonst 'unknown'.
    Je Event: headline, detail, category, beneficiary_tickers, negative_tickers,
    affected_sectors (GICS), source_url, as_of, effective_date.
    """

def build_batches(ticker_datas, batch_size=config.BATCH_SIZE_DEEP) -> list[list[dict]]:
    """
    Reine Gruppierung, kein Claude-Call.
    Sub-Sektoren sind UNTEILBARE Einheiten, per First-Fit-Decreasing
    gepackt — ausser eine Einheit ueberschreitet batch_size allein,
    dann wird sie vorher aufgeteilt. Ticker ohne Sektor bilden eine
    eigene Einheit statt still in einen fremden zu rutschen.
    Deterministisch: innerhalb einer Einheit alphabetisch, Einheiten
    nach (Groesse absteigend, erster Ticker) — ohne das waere weder
    der Test noch ein 3D-Vergleich zweier Laeufe reproduzierbar.
    """

def max_tokens_for_batch(n) -> int:
    """max(4096, n * TOKENS_PER_TICKER_DEEP + BATCH_TOKEN_RESERVE)
    = max(4096, n * 6000 + 200), seit C.18 neu kalibriert (davor 2500,
    C.10). Der 4096er-Boden bindet seit C.18 fuer kein n >= 1 mehr.
    ⚠️ Die Reserve ist BEWUSST klein: ein grosser fester Term verwaessert
    den Pro-Ticker-Wert, je groesser der Batch wird (das war der C.9-Bug --
    1150 Tokens/Ticker bei n=8 gegen 2048 bei n=2)."""

def analyze_batch(
    ticker_datas, cutoff_by_ticker, trend_context, policy_context, cost_tracker,
    date, run_type, max_tokens_override=None,
) -> tuple[list[dict], list[str]]:
    """
    EIN gestreamter Sonnet+web_search-Call fuer den ganzen Batch.
    User-Message beginnt mit "Today is {date}. Run type: {run_type}."
    (C.42/F33 -- ohne Anker riet das Modell das Datum aus Suchtreffern).
    Nutzlast je Ticker (Sidecar-Invariante!): {snapshot: td,
    news_scan: {news_strength, news_note, premarket_change_pct},
    technical_signal: {direction, strength}} — td selbst unveraendert.
    news_note/premarket_change_pct kommen seit C.42 aus dem Cutoff-Dict
    (F34: der Prompt verlangt gezielte Suche beim im Scan genannten
    Katalysator, vorher kam nur die Zahl an).

    Returns: (analyses, missing_tickers) — Teilergebnisse werden
    uebernommen, fehlende Ticker gemeldet statt still verschluckt.
    Raises BatchTruncatedError bei stop_reason == "max_tokens",
    DeepAnalysisError bei unparsebarer Antwort. Ein abgeschnittenes
    Ergebnis wird NIE teilverwertet (Spec 4.8).
    """

def analyze_batches(..., date, run_type, batch_size) -> tuple[list[dict], list[str]]:
    """
    Umschliesst analyze_batch() mit dem Fehlerpfad aus Spec 10:
    1× wiederholen → 1× halbieren (jede Haelfte genau einmal) → aufgeben.
    Faengt NUR DeepAnalysisError. CostCapExceeded laeuft ungehindert
    durch — ihn hier zu wiederholen liesse den Lauf ueber den Deckel
    hinaus weiterlaufen. Transiente API-Fehler behandelt bereits
    retry_with_backoff() in call_claude(); andere Fehlerklasse, andere Ebene.

    ⚠️ Eine KAPPUNG wird anders behandelt als eine kaputte Antwort:
    dieselbe Anfrage mit derselben Decke kaeme identisch zurueck, also
    laeuft die Wiederholung mit TRUNCATION_RETRY_FACTOR-facher Decke —
    und die Haelften ebenfalls, weil Halbieren seit C.10 den Platz PRO
    TICKER nicht mehr aendert.
    """
```

**Fail-Verhalten:** `DeepAnalysisError` → Retry/Halbierung, danach landen die Ticker in
`failed` und `run_pipeline()` loggt sie als WARNING. Kein stiller Verlust.

**Billing:** `cost_tracker.add_from_result(result)` **VOR** JSON parse.

⚠️ **Testlauf-Befund (2026-08-16, PROJECT_STATUS C.9):** Das Token-Budget reichte nicht.
Lauf mit `BATCH_SIZE_DEEP=8` verlor einen kompletten 8er-Batch (beide Versuche **und**
beide 4er-Hälften an `max_tokens`), Lauf mit `BATCH_SIZE_DEEP=4` verlor zwei Ticker an
einer gescheiterten 2er-Hälfte. Eine **kleinere** Batchgrösse war dabei teurer und
langsamer, weil sie nur öfter in die Halbierungs-Kaskade läuft.
✅ **Neu kalibriert am 2026-08-17 (C.10) und live verifiziert (C.11):** 2500 statt 900
Tokens je Ticker, Reserve 200 statt 2000, Wiederholung nach Kappung mit doppelter Decke.
Im Verifikationslauf trat `max_tokens` **kein einziges Mal** auf, 12 von 12 Kandidaten
wurden analysiert (Budget zu 47–54 % genutzt), Phase 3 kostete **0,0204 EUR je Ticker**
gegen ein Ziel von 0,034. ⚠️ Wie knapp der alte Wert war: der 8er-Batch brauchte 9 409
Tokens bei 9 200 Budget — 2,3 % daneben, nicht grob falsch.

⚠️ **Der C.10/C.11-Wert 2500 galt nur für `claude-sonnet-4-6` — seit der Migration auf
`claude-sonnet-5` (2026-08-20, C.18) sind es 6000.** Grund ist kein neuer Prompt,
sondern das Modell: `call_claude()` setzt kein `thinking`-Feld, was bei Sonnet 4.6
„kein Denken" hiess und bei Sonnet 5 „adaptives Denken an" heisst — Denk- und
Antworttokens teilen sich dieselbe Decke. Im Messlauf kappten **beide** Batches beim
ersten Versuch. Parallel: `TOKENS_PER_ASSET_CC` (Phase 3b) 3584 → 8192, und die drei
Einzelcall-Module bekamen mit `utils.call_claude_retry_on_truncation()` überhaupt erst
eine Kappungs-Erkennung. ⚠️ **Adaptives Denken ist nicht deterministisch** — in der
Messreihe kappte jedes Modul in einem anderen Lauf bei identischem Code; ein sauberer
Lauf ist deshalb kein Beleg für eine ausreichende Decke.

---

### 4b. **`src/providers/capital_provider.py`** (Sprint 2)

Capital.com Demo API als primary OHLC-Datenquelle.

```python
class CapitalComProvider(DataProvider):
    """
    Primary OHLC-Provider (Capital.com Demo API).
    Base URL: https://demo-api-capital.backend-capital.com/
    Rate Limit: 600 Calls/Min
    ENV: CAPITAL_COM_API_KEY, CAPITAL_COM_PASSWORD
    
    Ticker-Mapping (Stand C.34, 2026-09-10):
    - SP500-Ticker: direkt übergeben (TICKER_MAP nur für Ausnahmen wie BRK-B)
    - Rohstoffe/Krypto: Ticker = Epic, kein Mapping — Gold="GOLD", Silber="SILVER",
      Öl="OIL_BRENT" (Brent Oil Spot; bis 2026-09-10 "OIL_CRUDE" = WTI),
      BTC="BTCUSD", ETH="ETHUSD", SOL="SOLUSD", XRP="XRPUSD"
    """
    def get_price_history(ticker, days) -> pd.DataFrame: ...
    def get_ohlc_after(ticker, start_date, end_date) -> pd.DataFrame: ...
    def get_premarket_price(ticker) -> float | None: ...
    def get_open_positions() -> list[dict]: ...
    def get_closed_positions(date) -> list[dict]: ...
    def get_fundamentals() -> dict: ...       # leer – nicht zuständig
    def get_earnings_calendar() -> dict: ...  # leer – nicht zuständig
```

**Fundamentals** werden separat von `FinnhubProvider.get_fundamentals()` abgerufen und in `fundamentals_cache`-Tabelle mit 7-Tage TTL gecacht. Im täglichen Run wird der Cache aus der DB gelesen, kein Live-Call.
`debt_equity` = Finnhub `totalDebt/totalEquityQuarterly` (aktuelles Quartal, **Ratio**, unskaliert;
Rückfall `…Annual`) — bis C.44 (2026-09-14) las der Provider den Fiskaljahreswert und teilte
durch 100 (AAPL 0,0135 statt 0,78). Werte vor dem 14.09. in `fundamentals_cache`/`predictions`
sind entsprechend verzerrt (PROJECT_STATUS C.44).

⚠️ **Ratenbegrenzung (Sprint 3C / Plan 2, Task 11):** `FinnhubProvider._respect_rate_limit()`
drosselt auf 60 **Requests**/60s (Sliding-Window, **instanzgebunden** — nicht modulweit).
Der Wochenlauf (Task 12, `main._update_weekly_fundamentals()`) hält dafür ohnehin **eine**
Instanz über das ganze Universum, dieselbe Invariante wie „ein Session-Object pro Run"
bei Capital.com.
⚠️ **Gezählt wird je echtem Request, nicht je Methodenaufruf** — `get_fundamentals()`
setzt **drei** Finnhub-Requests ab (`company_profile2`, `company_basic_financials`,
`recommendation_trends`), `get_earnings_calendar()` einen. Die erste Fassung registrierte
nur den Methodenaufruf und hätte das Limit effektiv verdreifacht; im Wochenlauf wären das
~120 Requests/min gegen ein 60/min-Limit gewesen (Abschluss-Review, PROJECT_STATUS C.8/R2).
`get_earnings_calendar()` läuft **nur dort** — der Tageslauf (`fetch_missing_fundamentals()`,
Phase 2b) ruft sie nie, das ist die Aufgabenteilung aus Spec § 18.1c.

⚠️ **Rohstoffe/Krypto bekommen nie Fundamentals (C.35, 2026-09-10):** Finnhub löst `GOLD` als
die Aktie Gold.com Inc auf (PE, Market Cap, Earnings, Branche „Distributors", Alias Retail).
`universe.is_commodity_or_crypto()` ist die eine Frage an vier Stellen: Gate-Ausnahme (1a),
Cache-Lesung in `_process_ticker()` (1), `fetch_missing_fundamentals()` (2b) und der Wochenlauf,
der zusätzlich per `db.purge_non_equity_fundamentals()` Altbestand in `fundamentals_cache` und
`ticker_sectors` entfernt — `db-latest` heilt damit am nächsten Sonntag von selbst.

---

### 5. **`src/commodities_crypto.py`** (Phase 3b)

7 feste Assets (Gold, Silver, Brent — seit C.34 statt WTI —, BTC, ETH, SOL, XRP). Seit C.15 (2026-08-19)
gebatcht nach `asset_class` (Commodities: 3, Crypto: 4) statt 7 Einzelcalls — die
7 Assets selbst sind weiterhin ungefiltert (Spec § 6), nur die Call-Struktur änderte
sich.

```python
def fetch_fear_greed() -> dict | None:
    """Externe API: https://api.alternative.me/fng/
    Returns: {value: 0-100, label: "Extreme Fear"|...}"""

def build_batches(ticker_datas: list[dict]) -> list[list[dict]]:
    """Gruppiert nach asset_class -- Commodities- und Crypto-Batch getrennt,
    analog zu deep_analysis.build_batches()'s Sub-Sektor-Gruppierung."""

def analyze_batch(
    ticker_datas: list[dict],
    trend_context: dict,
    policy_context: dict,
    extra_context: dict,  # {fear_greed_value, fear_greed_label, gold_silver_ratio, btc_dominance_pct}
    cost_tracker: CostTracker,
    date: str, run_type: str,                        # C.43/F33: Datumsanker
    signal_by_ticker: dict[str, dict] | None = None, # C.43/F16: 1b-Sidecar
    max_tokens_override: int | None = None,
) -> tuple[list[dict], list[str]]:
    """
    EIN gestreamter Sonnet-Call fuer einen ganzen asset_class-Batch + web_search.
    User-Message beginnt mit "Today is {date}. Run type: {run_type}.";
    je Asset ein _batch_entry(): {snapshot: td OHNE STOCK_ONLY_SNAPSHOT_KEYS
    (pe_ratio, sector, data_quality, earnings_*, analyst_*; C.43/F37),
    technical_signal: {direction, strength}} -- td selbst unveraendert.
    Same schema as deep_analysis (results-Liste, 8-Dim + hold_days + intraday_range).
    Raises BatchTruncatedError bei stop_reason == 'max_tokens'.
    """

def fetch_btc_dominance() -> float | None:
    """C.43/F38: BTC-Anteil an der Krypto-Marktkapitalisierung (alternative.me
    v2/global) oder None -- optionale Anreicherung wie fetch_fear_greed()."""

def gold_silver_ratio(ticker_datas) -> float | None:
    """C.43/F38: GOLD-Kurs / SILVER-Kurs aus den Snapshots, None wenn einer fehlt."""

def analyze_commodities_and_crypto(
    ticker_datas: dict,
    trend_context: dict,
    policy_context: dict,
    extra_context: dict,
    cost_tracker: CostTracker,
    date: str, run_type: str,
    signal_by_ticker: dict[str, dict] | None = None,
) -> list[dict]:
    """Sonnet × 2 (1 pro asset_class) statt × 7. Ruft build_batches() + analyze_batch()
    mit Retry-Schale (_run_one_batch_with_recovery: einmal wiederholen, kein Halbieren).
    Nach dem Call wird a["extra"] fuer EXTRA_KEYS mit den Werten aus extra_context
    ueberschrieben (C.43/F38): die Mail zeigt Ratio/Dominanz aus dem Code, nie aus
    dem Modell."""
```

**Fail-Verhalten:** ein Batch-Call, der zweimal fehlschlägt (unparsebar oder
`BatchTruncatedError`), gibt seine ganzen Assets als `missing` auf — bis zu 4 auf
einen Schlag statt 1 wie im alten Einzelcall-Pfad (Trade-off, s. PROJECT_STATUS C.15).

---

### 6. **`src/ranking.py`** (Phase 4)

Filtert, klassifiziert, sortiert und persistiert die Kandidaten. **Läuft seit B.5 vor
Phase 4a.** Seit Plan 3b (Spec § 5) ersetzt `rank_score`/`candidate_class` die alte
`probability_pct`-Sortierung; `score_total()`/`config.DIMENSION_WEIGHTS` sind entfernt.

```python
def rank_and_persist(
    conn: sqlite3.Connection,
    date: str,
    run_type: str,
    stock_analyses: list[dict],       # Phase 3 output
    commodity_crypto_analyses: list,  # Phase 3b output
    market_context: dict,
    signal_context: dict[str, dict],  # Technik-Signal + C.1-Indikatoren + news_strength + Snapshot-Kurs/Range/data_quality je Ticker (main.py::_signal_context())
    sector_momentum: dict[int, dict] | None = None,
    enforce_checks: bool = False,
) -> dict:
    """
    Logik (Spec § 5):
    0. Normalisierung auf einer KOPIE (C.45 / F41): current_price und
       price_premarket = Snapshot-Kurs, intraday_range_pct = Snapshot-Wert,
       rr_ratio/tp_pct/sl_pct aus den Preisen (signal_checks.derive_levels);
       Abweichung zum Modell-Echo = WARNING, fehlender Snapshot-Kurs = WARNING
    1. Guardrail-Filter auf der Kopie (hold_days ≤ 5, intraday_range ≥
       config.MIN_INTRADAY_RANGE_PCT, abgeleitete R/R ≥ 1.5, ≥ 2 distinkte
       Quell-Domains, direction ∈ {long, short}, data_quality aus signal_context)
    2. Checks aus src/signal_checks.py (VIX, Sektor-Momentum, Klumpen, Earnings,
       Stop-Distanz, TP-Reichweite) — erhoben in BEIDEN Läufen, durchgesetzt nur
       bei enforce=True (16:10); die angeschlagenen Regeln hängen als _checks
       an der angereicherten Kopie (Flags in der Mail, C.45 / F43)
    3. Klassifikation je Kandidat (_classify(), § 5.3): core (Technik-Richtung
       stimmt mit Analyse überein), divergence (Technik neutral/fehlt, wird
       persistiert, eigene Mail-Sektion), conflict (Technik gegenläufig — verworfen
       als guardrail_reject; gilt NIE für Rohstoffe/Krypto, § 20.5 #2).
       rank_score = analysis_strength × tech_strength, aber NULL statt 0, sobald
       einer der beiden Faktoren 0/unbekannt ist (§ 5.4).
    4. Split Long/Short, je core und divergence
    5. Sort by rank_score DESC (Fallback: analysis_strength, dann Ticker)
    6. Keep Top 10 je Richtung (core), Top DIVERGENCE_TOP_N je Richtung
       (divergence, § 5.5), ALLE commodities/crypto
    7. Persist to db.predictions (inkl. candidate_class, tech_*, rank_score,
       analysis_strength, news_strength); Verworfenes nach db.guardrail_rejects

    Returns: {top_long[], top_short[], commodities_crypto[], divergence[],
              divergence_stats: {tech_only_abstentions, conflicts, overflow,
                                 core_overflow}}   # core_overflow: C.45 / F44
    """
```

**Fail-Verhalten:** `RankingError` → propagates (MUSS funktionieren).

⚠️ **Mutations-Invariante:** die Analyse-Dicts aus `stock_analyses`/
`commodity_crypto_analyses` werden von `rank_and_persist()` nie mutiert — dieselben
Objekte gehen danach an `check_open_positions()` (Phase 4a) und werden dort
`json.dumps`'t in einen Claude-Prompt. Klassifikation/Ranking hängen
`_candidate_class`/`_analysis_strength`/`_rank_score` nur an **Kopien** (`{**a, ...}`),
nie ans Original — derselbe Vorfall wie C.6 (unbemerkte Prompt-Kosten durch einen
angehefteten Schlüssel), diesmal vorab getestet. Ein Test pinnt die Schlüsselmenge der
Originale unverändert.

---

### 7. **`src/portfolio_check.py`** (Phase 4a)

Prüft die bei **Capital.com tatsächlich offenen Positionen** (C.37, 2026-09-11) —
Quelle ist `main._open_broker_positions()` aus Phase 1c, ein Abruf je Lauf. Liest
`predictions` nicht: Predictions sind Papier-Vorschläge und laufen getrennt durch
die mehrtägige Auswertung. **Läuft seit B.5 nach Phase 4.** Seit C.46 bekommt der
Prompt in **beiden** Läufen denselben dreiteiligen Snapshot aus `build_snapshot()`
statt des rohen Analyse-Dicts (15:00) bzw. rohen `td` (16:10); Modell Sonnet 5.

```python
def build_snapshot(td, tech, analysis) -> dict:
    """{"technicals": <14 td-Schlüssel: Kurs, Änderungen, RSI+Trend, MACD-Label,
        SMA-Abstände, BB, ATR, Range, Volumen, Earnings-Termin> | None,
        "technical_signal": {"direction", "strength" (0-4)} | None,
        "analysis": {direction, confidence, probability_pct, summary,
                     signal_consistency_check, scores (Werte + Belege);
                     tp/sl/rr NUR bei long/short (F49)} | None}
    Neue Dicts: Originale unberührt, kein fremder Schlüssel im Prompt (C.6)."""

def pending_rows(positions) -> list[dict]:
    """Zeilen action="NICHT GEPRUEFT" je Position; main setzt sie nach Phase 1c
    in payload["portfolio_recs"], 4a ersetzt sie in place (F53)."""

def check_open_positions(
    conn, today, run_type,
    positions: list[dict] | None,          # Capital.com-Positionen; None = Abruf gescheitert
    analyses_by_ticker: dict[str, dict],   # Phase-3-Analysen (16:10: {})
    trend_context, policy_context, cost_tracker,
    *, tds_by_ticker=None, signal_by_ticker=None, out=None,
) -> list[dict]:
    """
    Je Position (deal_id, direction, entry/current price, TP/SL, size, P&L, opened_at):
      - Sonnet-5-Call OHNE web_search (B.5), User-Message beginnt mit
        "Today is <date>. Run type: <run_type>." (F47); Kappung → Wiederholung
        mit doppelter Decke, beide Versuche gebucht (F52)
      - Call, sobald td ODER Analyse vorliegt; ohne beides "KEINE ANALYSE"
      - Returns: {deal_id, ticker, action:"HALTEN"|"SCHLIESSEN"|"ANPASSEN",
                 reason (English), new_sl_price, new_tp_price, market_context_changed}
                 + Positionsfelder für die Mail; ANPASSEN mit ungültigen Levels
                 → HALTEN mit "[Levels ungueltig: …]" in reason (F51)
      - Speichert eine position_checks-Zeile je Deal und Lauf
      - out gehört dem Aufrufer (Spec 7.1): Kostendeckel mitten in der Schleife
        lässt fertige Zeilen plus NICHT GEPRUEFT stehen; ein gescheiterter
        Einzel-Call bleibt als NICHT GEPRUEFT sichtbar
    positions is None: keine Empfehlungen (Mail: „nicht abrufbar").
    """
```

**Fail-Verhalten:** `PortfolioCheckError` → skip Position, continue.

Bis C.37 lud der Check „offene Positionen" aus `predictions` (≤ `MAX_HOLD_DAYS`, `date <
today`) und empfahl HALTEN/SCHLIESSEN für Positionen, die es beim Broker nie gab (10.09.:
7 Empfehlungen bei 0 offenen Positionen). `db.load_open_predictions_within_max_age_days()`,
`save_position_recommendation()`, `load_position_recommendations_for_date()` und die Tabelle
`position_recommendations` sind seither ohne Aufrufer (Finaldurchgang).

---

### 8. **`src/evaluator.py`** (Täglich, im `final_close`-Lauf)

Walk-Forward OHLC-Hit-Check für gestrige Setups.

> **Seit dem Preismodell-Umbau (2026-08-07, PROJECT_STATUS P3)** läuft die Auswertung
> nicht mehr im `close`-Lauf um 20:30 UTC, sondern in `final_close` um 00:15 UTC, und
> sie liest `price_history` statt selbst live zu holen. Grund: `_walk_forward_hit`
> prüft TP **und** SL gegen `High`/`Low`, und beide können sich im Tagesverlauf nur
> **ausweiten**. Eine provisorische Bar hat eine engere Spanne als die finale — sie
> meldet systematisch zu wenige Treffer und zu viele `timeout`.
>
> **Das Fenster beginnt am Signal-Zeitpunkt**, nicht am Tagesbeginn: die Tagesbar läuft
> ab 08:00 UTC, das Signal entsteht erst um 09:00 ET (`pre_market`) bzw. 10:10 ET
> (`trade_proposals`). Treffer aus der Zeit davor sind Artefakte. Den ganzen Prognosetag
> auszuschliessen wäre aber das *gespiegelte* Artefakt — 3D verfolgt die Trefferquote
> getrennt nach Intraday (`hold_day = 1`) und Extended. Deshalb kommt der Signaltag als
> **eine verdichtete Bar** in die Sequenz (s. `src/signal_window.py`): so zählt
> `_walk_forward_hit` weiterhin je Bar einen Tag, und `days_to_close == 1` heisst
> weiterhin „am Signaltag getroffen".
>
> `evaluated_date` bezeichnet den **Handelstag**, dessen Bar geschlossen hat — nicht das
> Laufdatum. Sonst fände `_aggregate_yesterday_outcomes` nichts mehr.

```python
def evaluate_open_predictions(
    conn: sqlite3.Connection,
    today: str,
    price_provider: DataProvider,
) -> int:
    """
    Für jede offene & learnable & date<today Prediction:
      1. Fetch OHLC-Fenster [pred.date → today]
      2. Walk-Forward Hit-Check (max 3 Bars)
      3. Bestimme exit_reason + exit_price + days_to_close
      4. Atomisch update outcomes-Row + prediction.status
    
    Exit Reasons:
      - "tp_hit": TP erreicht (optimistisch)
      - "sl_hit": SL erreicht (stop loss)
      - "pessimistic_overlap": TP & SL same bar → SL annehmen
      - "timeout": 3 Bars vorbei, kein Hit
      - "data_missing": OHLC-Fetch failed/empty
    
    Profit/Loss: CFD Simulation @ 500 EUR Margin, 5:1 Hebel
    """
```

---

### 9. **`src/email_sender.py`** (Phase 5)

Rendert HTML und sendet via **Resend** (`POST https://api.resend.com/emails`).

> **Provider-Wechsel erledigt (Sprint 3B-M, 2026-07-30).** `_send()` ist die einzige
> providerspezifische Stelle — jedes `send_*_email()` laeuft dort durch. Bewusst
> `requests` statt Anbieter-SDK: es ist genau ein POST, `requests` ist ohnehin
> Abhaengigkeit, und Resend sitzt hinter Cloudflare, das die `urllib`-Signatur mit
> HTTP 403 / „error code: 1010" abweist. Resend verlangt eine **verifizierte eigene
> Domain**; `tradingharry.com` ist seit 2026-07-30 verifiziert, Absender ist
> `noreply@tradingharry.com`. Ein 2xx auf den POST heisst nur „angenommen" — die
> Zustellung laeuft asynchron, Fehlschlaege zeigen sich erst unter
> `GET /emails/{id}` als `last_event="failed"`.

```python
def render_daily_html(
    date: str,
    top_long: list[dict],
    top_short: list[dict],
    portfolio_recs: list[dict],  # Phase 4a output
    commodity_crypto: list[dict],
    yesterday_outcomes: dict,     # {long_correct, long_total, ...}
    cost_summary: dict,           # {total_eur, aborted_at_phase, ...}
    trends: list[dict],
) -> str:
    """
    Kopf (keine Sektion): Briefing-Box "Was heute zaehlt" + EINE Marktlage-Zeile
    (VIX, S&P-500-Tagesaenderung, Regime) aus dem morgendlichen market_context
    (C.30). Portfolio bleibt die erste Sektion.
    4 Sektionen (in dieser Reihenfolge):
      1. Portfolio-Empfehlungen (Phase 4a: HALTEN/SCHLIESSEN/ANPASSEN)
      2. Stock Rankings (Top-10 Long + Top-10 Short)
      3. Trends (Makro-Trends + Sector-Rotation)
      4. Commodities & Crypto
    
    Footer: Tages-Outcomes, Skipped, Cost, Disclaimer
    """

def send_daily_email(to: str, html: str, date: str) -> bool:
    """Resend API Call"""
```

---

### 10. **`src/guardrails.py`**

Qualitätskontrolle auf analysen vor Ranking.

```python
class GuardrailsChecker:
    def check_analysis(analysis: dict, *, data_quality: str | None = None) -> tuple[bool, list[str]]:
        """
        Prüft (seit C.45 die NORMALISIERTE Kopie aus ranking, s. Modul 6):
        1. Pflichtfelder; direction ∈ {long, short, none} (sonst harter Reject, C.45)
        2. sources_used: ≥ 2 DISTINKTE Domains (nicht Einträge, C.45)
        3. Jede Dimension ≥ 2 Belege (evidence_quality "thin" ausgenommen, § 6.3)
        4. TP/SL auf der richtigen Seite des Entry
        5. R/R Ratio ≥ 1.5 — der aus den Preisen abgeleitete Wert, nie das Modell-Echo
        6. confidence 'high' nicht bei data_quality 'low' — data_quality kommt als
           Parameter aus dem Snapshot (bis C.45 las die Regel einen Schlüssel, den
           das Prompt-Schema nicht kennt; sie war tot)
        7. momentum-Wert passend zur Richtung (long ≥ 6, short ≤ 4)
        8. hold_days_recommended ≤ config.MAX_HOLD_DAYS
        9. intraday_range_pct ≥ config.MIN_INTRADAY_RANGE_PCT
        direction 'none' wird vorher in ranking._guardrail_filter() als Enthaltung
        gezählt und erreicht den Checker nicht.
        """
```

---

### 10a. **`src/signal_checks.py`** (neu in 3B / Plan 2)

Die rechnerischen Checks aus B.3. **Bewusst netzwerk- und Claude-frei:** jede Funktion
bekommt bereits erhobene Werte (Markt-Kontext aus Phase 0b, Sektor-Momentum aus Phase 1d,
Kurse aus `price_history`) und gibt ein Urteil zurück. Dadurch ohne Mocking testbar.

```python
check_vix(...)             -> CheckResult | None   # kumulativ: ab 25 (>=) nur high,
                                                   # zusätzlich ab 35 (>=) keine neuen Longs
check_sector_momentum(...) -> CheckResult | None   # hart nur bei Übereinstimmung
check_cluster(...)         -> CheckResult | None   # Klumpenrisiko im Sub-Sektor (immer weich)
check_earnings(...)        -> CheckResult | None   # Earnings in <= 2 Tagen (hart nur 16:10)
check_stop_distance(...)   -> CheckResult | None   # Stop < 0.8 Range (immer weich, C.22)
check_tp_reach(...)        -> CheckResult | None   # TP > 0.9 Range (immer weich, C.45)
check_opening_gap(...)     -> CheckResult | None   # Gap pre_market → 16:10 (nur 16:10)
check_stop_budget_spent(...) -> CheckResult | None # Risikobudget verbraucht (hart, nur 16:10)
derive_levels(entry, tp, sl, direction) -> dict    # rr_ratio/tp_pct/sl_pct aus Preisen (C.45)
compute_relative_strength(...)                     # Ticker vs. Sub-Sektor
blocks(results)            -> bool                 # blockiert irgendein Ergebnis?
```

⚠️ **Die beiden Range-Beobachter sind rechnerisch unvereinbar** (C.45): Stop ≥ 0,8
und TP ≤ 0,9 der Range ergibt R/R ≤ 1,125 < 1,5. Jedes guardrail-taugliche Setup
löst also mindestens einen von beiden aus; gemessen wird, wie weit die Setups
ausserhalb liegen, nicht ob. Beide Schwellen sind unbestätigte Startwerte.

**Zwei Regeln, die man hier leicht falsch macht:**
- Ein Check, der **nicht** anschlägt, gibt `None` zurück und erzeugt **keine** Zeile —
  wörtlich B.3.1: „keines vorhanden → kein Check, kein Log-Eintrag".
- Ob ein anschlagender Check das Signal auch **blockiert**, entscheidet nicht dieses
  Modul, sondern der Aufrufer über `enforce` (E4). Um 15:00 wird nur erhoben, um
  16:10 durchgesetzt.

⚠️ **`enforced` in `guardrail_rejects` ist kein Lauf-Kennzeichen.** Die Spalte sagt
„dieser Check hat das Signal tatsächlich verworfen" — so liest sie auch
`signal_checks.blocks()`. **Beide Läufe schreiben beide Werte:** `pre_market` schreibt
`enforced=1`, wenn der klassische `GuardrailsChecker` in `ranking.py` greift (dort wird
der Kandidat wirklich verworfen), und `trade_proposals` schreibt `enforced=0` für die
immer weichen Checks (Klumpenrisiko, Opening-Gap, einseitiges Momentum). Wer die Läufe
trennen will, gruppiert nach `run_type` — Weekly-Block 3 tut das.

---

### 10b. **`src/revalidation.py`** (neu in 3B / Plan 2)

Der billige Zweitcheck des `trade_proposals`-Laufs (E1). Ein Sonnet-Call je Signal,
**ohne `web_search`** — die Recherche hat die Tiefenanalyse am Morgen bezahlt, und
Breaking News zwischen 15:00 und 16:10 deckt der eine Policy-Monitor-Call ab.

```python
revalidate_one(...) -> dict   # {verdict, probability_pct, reason, ...}
                              # verdict ∈ bestaetigt | geschwaecht | unveraendert
                              #           | gedreht | verworfen
```

**Das Modul urteilt nur.** Was mit dem Urteil geschieht — Ablösung der `pre_market`-Zeile
über `superseded_by`, eine neue Prediction oder blosse Warnung — entscheidet
`main.run_trade_proposals()`. In drei von sechs Ausgängen entsteht gar keine neue Zeile.

---

### 10c. **`src/signal_window.py`** (neu im Preismodell-Umbau, 2026-08-07)

Reine Funktionen: **keine DB, kein Netz, kein Claude.** Deshalb ohne einen einzigen
Mock testbar.

| Funktion | Zweck |
|---|---|
| `signal_time_utc(run_type, date)` | Wann das Signal entstand — 09:00 ET für `pre_market`, 10:10 ET für `trade_proposals` |
| `regular_open_utc(date)` | Die **reguläre** US-Eröffnung (09:30 ET) |
| `is_premarket(date, now_utc)` | Lag der Erhebungszeitpunkt vor der Eröffnung? |
| `day_end_utc(date)` | Tagesgrenze — 00:00 UTC des Folgetags |
| `collapse_to_daily_bar(df)` | Verdichtet Intraday-Bars zu **einer** Tagesbar |

**Die Verdichtung ist der Kern.** `High` = Maximum, `Low` = Minimum, `Close` = letzter.
Ohne sie zählte `_walk_forward_hit` jede Minute als eigenen „Tag" und zerstörte
`days_to_close` — die Kennzahl, an der 3Ds `hold_day` hängt.

**Alle Zeiten hängen an `America/New_York`, nie an `Europe/Berlin`.** EU und USA schalten
die Sommerzeit an verschiedenen Wochenenden um; in den Zwischenwochen ginge eine Berliner
Rechnung daneben.

⚠️ `marketStatus` aus `/markets/{epic}` taugt **nicht** zur Vorbörsen-Erkennung: es
meldete am 2026-08-06 um 08:37 ET `TRADEABLE`, mitten in der Vorbörse. Es beschreibt die
Handelbarkeit des CFDs inklusive erweiterter Zeiten, nicht die Sitzungsphase. Deshalb die
Uhr.

---

### 10d. **`src/universe.py`** (neu 2026-08-08)

Die **eine Quelle** dafür, welche Ticker das System überhaupt anfasst. Reine Funktionen,
keine DB-Abhängigkeit ausser einer Leseabfrage.

| Funktion | Zweck |
|---|---|
| `stock_universe()` | Nur die Aktien — **die einzige Stelle, die `USE_FULL_SP500` auswertet** (150 produktiv / 451 voll) |
| `full_universe()` | `stock_universe()` + Rohstoffe + Krypto + Sub-Sektor-ETFs, dedupliziert, stabile Reihenfolge |
| `thin_history_tickers(conn)` | Universums-Ticker mit weniger als `MIN_BARS_RSI` Bars |

⚠️ **`stock_universe()` ist seit 2026-08-21 die Einzelquelle des Schalters**
(PROJECT_STATUS C.24). Vorher stand `SP500_FULL_TICKERS if USE_FULL_SP500
else ...` **fünffach** im Code (`main.py` 2×, `db.py`, `universe.py`,
`capital_provider.py`) — dieselbe Streuung, die bei `LEARNING_RETENTION_DAYS`
eine von vier Tabellen auf einer abweichenden Frist stehen liess. Ein Test
(`test_universe.py`) scannt den Quellbaum und wird rot, sobald jemand den
Ausdruck wieder lokal kopiert.

**Warum ein eigenes Modul.** Drei Stellen brauchen exakt dieselbe Liste:
`main.run_final_close()` (der einzige Schreiber von `price_history`),
`historical_loader --universe` (der Backfill) und `main._abort_on_thin_history()` (der
Guard). Vorher baute jede Stelle sie selbst zusammen — genau die Naht, an der ein neu
aufgenommener Ticker durchfällt: er kommt in die Config, aber nicht in den Backfill, wird
mangels Bars übersprungen und zählt Richtung Deaktivierung.

Die Deduplizierung ist nötig, weil sich mehrere Sub-Sektoren einen ETF teilen
(MedTech/Pharma/Healthcare Rest zeigen alle auf XLV).

⚠️ Die ETFs stehen zwar in `price_history` (`final_close` schreibt sie mit), aber **nicht**
in `ticker_sectors` — sie verfälschen `db_momentum` also nicht.

---

### 11. **`src/db.py`**

SQLite-Schema + Persistence.

**Tabellen:**
- `predictions` – Alle generierten Setups (id, date, ticker, direction, scores, hold_day, extended_hold, ...)
- `technical_indicators` – Phase 1 Daten (rsi_14, macd, ..., seit Sprint 3C / Plan 1
  zusätzlich 29 Spalten für die 17 Indikatoren aus `src/indicators.py`, s. unten)
- `outcomes` – Walk-Forward Ergebnisse (tp_hit, sl_hit, days_to_close, hold_day, extended_hold, p&l, ...)
- `position_checks` – Phase 4a Output je Capital.com-Deal (HALTEN/SCHLIESSEN/ANPASSEN), seit C.37
- `position_recommendations` – bis C.37 Phase 4a Output je Prediction; ohne Schreiber, Historie
- `cost_tracking` – Claude-API Kosten pro Run
- `fundamentals_cache` – Finnhub-Fundamentals mit 7-Tage TTL (UNIQUE per ticker)
- `price_history` – ausschliesslich finale Tages-OHLCV (s. „Die zentrale Trennung" oben)
- `market_context` – ein Marktzustand je Run (UNIQUE date+run_type), seit 3B echt befüllt.
  Seit C.16 (2026-08-19) **ohne** `oil_price`/`gold_price`/`btc_price` (Rohpreise liegen
  vollständig in `price_history`, dieselbe Capital.com-Pipeline wie die Aktien) und mit
  `fear_greed_value`/`policy_risk_level` per Backfill befüllt (`update_market_context_extras()`,
  s. Helpers unten) — beide Werte entstehen erst in Phase 3/3b, lange nach
  `save_market_context()` in Phase 0b. `sp500_change_pct` wird seit C.28 vom
  Phase-0b-Prompt erhoben (vorher nie befüllt); `vix_source` ist seit C.28 eine Spalte
  (Migrations-Guard); `advance_decline_ratio` bleibt als Spalte, wird aber nicht mehr
  erhoben (immer NULL). Die `trade_proposals`-Zeile trägt seit C.28 nur `vix_level`/
  `vix_source` — kein zweiter Claude-Call um 16:10 (`vix_only_context()`).
- `skipped_tickers` – Ereignis-Log je übersprungenem Ticker mit Grund; trägt die
  Weekly-Auswertung und die Deaktivierung
- `trend_analyses` – Phase-0-Ausgaben
- `news_summaries` – seit C.16 (2026-08-19) befüllt aus Phase 2 (`broad_scan`) **und**
  Phase 3/3b (`deep_analysis`/`commodities_crypto`), seit C.41 (2026-09-13) auch aus dem
  Policy-Monitor (`source='policy_monitor'`, je Event eine Zeile pro genanntem Ticker,
  `ticker=NULL` für marktweite Events, in `pre_market` **und** `trade_proposals`),
  Vorarbeit für Sprint 3D.
  `sentiment`/`market_impact` sind **abgeleitete** Werte (aus `direction`/`confidence`
  bzw. `news_strength`), keine direkt vom Modell gelieferten Felder. Kein
  UNIQUE-Constraint — mehrere Quellen dürfen für denselben Ticker/Tag nebeneinander stehen.
- `cutoff_log` *(neu, Sprint 3C / Plan 2, Task 9)* – **jeder** von Phase 2 bewertete
  Ticker, nicht nur die für Phase 3 ausgewählten (`selected`-Flag +
  `rank_position` nach der Cutoff-Sortierung, seit C.40 auch `forced` = Pflicht-Kandidat
  aus offener Capital.com-Position, sonst wäre ein selektierter 0/0-Ticker für 3D
  grundlos). UNIQUE(date, run_type, ticker);
  ein doppelter Lauf ersetzt statt zu duplizieren. 3D braucht die volle Liste,
  um den 51. mit dem 50. zu vergleichen. ⚠️ Trägt seit dem Plan-2-Abschluss-Review
  auch `tech_strength` — der Wert entscheidet die Qualifikation mit und ist aus
  `tech_agreement` **nicht** ableitbar (das ADX-Band moduliert ihn). Als
  volumenstärkste Tabelle des Systems (~1000 Zeilen/Tag bei 500 Tickern) hat sie
  **180 Tage Retention** in `cleanup_old_data()`

✅ **`fundamentals` entfernt** (C.16, 2026-08-19): war seit Einführung nie beschrieben,
`fundamentals_cache` übernahm die Rolle vollständig. Per `DROP TABLE`-Migration entfernt
(anders als der `price_history.premarket_price`-Präzedenzfall unten — die Tabelle war
leer, das Risiko minimal). `news_summaries` war ebenfalls tot (kein Insert-Pfad), ist
seit C.16 aber **verdrahtet** statt entfernt (s. oben) — Korbinian will sie für Sprint 3D.
⚠️ **Eine tote Tabelle bleibt:** `prompt_versions` wird von `init_schema()` angelegt,
aber **nirgends gelesen oder geschrieben** (verifiziert 2026-08-09) — sie gehört zum
noch nicht gebauten A/B-Testing (Sprint 3D). ✅ Eine weitere Altlast dieser Klasse ist
seit Task 10 geschlossen: `MAX_DEEP_ANALYSIS` wird gelesen (80 → 50), `BATCH_SIZE_QUICK`
ist entfernt, nicht nur tot.

**Neu in Sprint 3B / Plan 1** (angelegt 2026-07-27/29):
- `ticker_status` – kumulativer `skip_count` + `inactive`-Flag + `retry_after` pro Ticker
- `sectors` – **21 Sub-Sektoren** auf 19 ETFs (Semiconductors→SOXX, Software→VGT, …),
  Seed beim DB-Setup aus `config.SUB_SECTOR_ETFS`. Bewusst feiner als die
  11 GICS-Sektoren, die hier ursprünglich geplant waren.
- `ticker_sectors` – Ticker→Sub-Sektor-Mapping, organisch in Phase 1 aus dem Finnhub-Cache
- `guardrail_rejects` – verworfene Analysen mit gruppiertem `rule`-Namen und `enforced`-Flag
- `sector_momentum` – die beiden Momentum-Signale je Sub-Sektor und Run
  (UNIQUE date+run_type+sector_id)

**Neue Spalten in 3B / Plan 1:**
- `market_context.advance_decline_ratio`
- `predictions.sector_etf_momentum`, `predictions.sector_db_momentum`
- `guardrail_rejects.sector_etf_momentum`, `guardrail_rejects.sector_db_momentum`

> Die vier Momentum-Spalten sind angelegt, werden aber noch von niemandem
> **befüllt** — das macht Plan 2 zusammen mit der Guardrail-Auswertung.

**Neu in Sprint 3C / Plan 1 (Fundament), abgeschlossen 2026-08-12** (s. PROJECT_STATUS C.6):
- `technical_indicators` um **29 Spalten** erweitert (`5e9a9ec`), migrationsgeschützt
  (`_apply_migrations`, additiv, alle NULL-fähig) — MACD/ADX je drei, Ichimoku fünf,
  Bollinger/Donchian je drei, PSAR/Stochastik/TRIX je zwei, plus `ema_50_dist_pct`,
  `willr_14`, `cci_20`, `mom_12`, `atr_abs`, `obv`
- Befüllt von `data_collector._process_ticker()`, aber **noch von niemandem konsumiert** —
  keine Verhaltensänderung

**Geplant in Plan 3** (noch nicht angelegt):
- `predictions.ranking_score` – neue Spalte für den kombinierten Score

**Wichtige Helpers:**
- `save_prediction(conn, pred_dict)` – Phase 4
- `save_position_check(conn, row)` – Phase 4a (je Capital.com-Deal, C.37)
- `load_open_predictions_within_max_age_days(conn, today, ...)` – bis C.37 Phase 4a, jetzt ohne Aufrufer
- `update_outcome_close(conn, pred_id, exit_reason, exit_price, ...)` – Evaluator
- `load_recent_outcomes(conn, days=7)` – Weekly Email
- `resolve_sector_id(conn, raw)` / `upsert_ticker_sector(...)` / `get_ticker_sector(...)` – Sub-Sektoren
- `is_ticker_inactive(conn, ticker, today)` / `reactivate_ticker(...)` / `list_inactive_tickers(...)` – Skip-Logik
- `log_guardrail_reject(conn, row)` / `load_guardrail_rejects_since(conn, since)` – Weekly-Auswertung
- `compute_sector_db_momentum(...)` / `save_sector_momentum(...)` / `load_sector_momentum(...)` – D9
- `save_market_context(conn, row)` – Phase 0b
- `update_market_context_extras(conn, date, run_type, fear_greed_value, policy_risk_level)`
  *(C.16)* – Backfill nach Phase 3/3b, `UPDATE` statt `INSERT OR REPLACE`
- `save_news_summaries(conn, rows)` *(C.16)* – Batch-Insert, mehrere Quellen je Ticker/Tag

**Retention** (`cleanup_old_data`, seit 3B): `news_summaries` 30 Tage,
`trend_analyses` 180 Tage, `skipped_tickers`-Events 90 Tage. `ticker_status`
wird **nie** automatisch gelöscht — der kumulative Zähler muss die Event-Retention
überleben.

---

### 11b. **`src/utils.py`**

Querschnitts-Helfer, die jedes Claude-aufrufende Modul benutzt.

| Baustein | Zweck |
|---|---|
| `retry_with_backoff(...)` | Dekorator für transiente API-Fehler |
| `ClaudeResult` | Ergebnis-Objekt inkl. Token-Zahlen **und `stop_reason`** — Grundlage der Kostenerfassung |
| `call_claude(..., stream=False)` | Anthropic-Wrapper mit Prompt-Caching, optional gestreamt |
| `call_claude_retry_on_truncation(...)` | `call_claude()` + Kappungs-Erkennung für die Einzelcall-Module (C.18) |
| `ClaudeTruncatedError` | Wurf, wenn auch die Wiederholung mit doppelter Decke kappt |
| `extract_json_blob(text, error_cls)` | toleranter JSON-Auszug aus Claudes Antwort |

⚠️ `extract_json_blob` nutzt `raw_decode`, weil Claude gelegentlich Fliesstext hinter das
JSON hängt. Ein striktes `json.loads` scheiterte daran.

⚠️ **`call_claude_retry_on_truncation()` ist der Einzelcall-Gegenpart zu
`BatchTruncatedError`** (C.18). Es erkennt `stop_reason == "max_tokens"`, wiederholt
**einmal** mit `TRUNCATION_RETRY_FACTOR`-facher Decke und wirft danach — die Batch-Module
behalten ihren reicheren Pfad (Wiederholen → Halbieren) und nutzen es nicht. Genutzt von
`trend_analyzer`, `market_context`, `revalidation` und `deep_analysis.run_policy_monitor()`
(letzteres als Nachtrag — beim ersten Durchgang übersehen, obwohl es mit 3072 die
knappste Decke hatte); dort kam eine Kappung vorher als
`JSONDecodeError` an, und bei `trend_analyzer` ist das laut Spec § 3 fatal für den ganzen
Lauf. **Es bucht jeden Versuch selbst** — auch den verworfenen gekappten — die drei
Aufrufer rufen `cost_tracker.add_from_result()` deshalb nicht mehr selbst auf.

⚠️ **`stream=True` ist nötig, sobald die erwartete Ausgabe gross wird** (Plan 3a):
der nicht gestreamte Pfad hängt am httpx-Default-Timeout von 600 s, den eine lange
Generierung plus mehrere Websuchen reisst. Genutzt von `broad_scan` und `analyze_batch()`.
Default bleibt `False` — kein bestehender Aufrufer ändert sein Verhalten ungewollt.
`stream=True` nimmt `messages.stream()` + `get_final_message()`, was dieselbe Message-Form
liefert wie `messages.create()`; beide Pfade teilen sich `_result_from_message()`.

⚠️ **`stop_reason == "max_tokens"` ist ein Fehlerfall, kein Ergebnis.** `broad_scan` und
`analyze_batch()` werten ihn aus und verwerfen die Antwort komplett — ein abgeschnittener
JSON-Block ist nicht teilverwertbar. Vor Plan 3a trug `ClaudeResult` das Feld nicht und
`broad_scan` musste `output_tokens` gegen `MAX_TOKENS` schätzen.

⚠️ **`web_search_calls` hatte ZWEI unabhängige Zählfehler, beide seit 2026-08-17 behoben
— und beide hielten dieselbe Zahl still auf 0.**
1. `response.usage.server_tool_use` kommt als **`dict`**, nicht als Objekt
   (`Usage.model_config` hat `extra="allow"`, Pydantic reicht rohes JSON durch);
   `getattr()` darauf liefert immer den Default. Gelesen wird jetzt mit `.get()`.
2. Im **gestreamten** Pfad fehlt das Feld ganz: `get_final_message()` liefert
   `usage.server_tool_use == None`, obwohl dieselbe Antwort `server_tool_use`-Content-
   Blöcke trägt (gegen die echte API verifiziert). Genau die beiden gestreamten Aufrufer
   — `broad_scan` und `analyze_batch()` — zählten dadurch dauerhaft 0. Fehlt das Feld,
   werden jetzt ersatzweise die Content-Blöcke gezählt; wo es existiert, behält es Vorrang.

Alle bis 2026-08-17 ausgewiesenen `web_search_eur`-Werte sind dadurch zu niedrig.

⚠️ **Reihenfolge-Invariante:** `cost_tracker.add_from_result()` läuft **vor** der
JSON-Extraktion. Sonst kostet eine unparsebare Antwort Geld, das nie erfasst wird.

---

### 11c. **`src/providers/base.py`**

`DataProvider` (ABC) — das Interface, das die Pipeline von der Datenquelle entkoppelt:
`get_price_history`, `get_fundamentals`, `get_earnings_calendar`,
`get_last_available_date`, `get_ohlc_after`.

Kein Provider implementiert alle Methoden sinnvoll — siehe unten.

---

### 11d. **`src/providers/finnhub_provider.py`**

Fundamentaldaten und Earnings-Kalender über den Finnhub-Free-Tier.

⚠️ **Liefert bewusst keine Kursdaten.** `get_price_history` und `get_ohlc_after` sind
Stubs; OHLC kommt ausschliesslich von `CapitalComProvider`. Der Provider erfüllt also nur
die Fundamentals-Hälfte des Interfaces.

Ergebnisse werden über `fundamentals_cache` mit 7-Tage-TTL zwischengespeichert — der
Free-Tier ist ratenbegrenzt.

⚠️ `price_target` wurde entfernt: der Free-Tier antwortet dort mit HTTP 403.

---

### 11e. **`prompts/` — Versionierung, aber kein A/B-Test**

Jedes Claude-aufrufende Modul lädt seinen System-Prompt beim Import aus einer Datei mit
Versionssuffix:

| Modul | Prompt |
|---|---|
| `trend_analyzer` | `trend_analyzer_v1.txt` |
| `market_context` | `market_context_v1.txt` |
| `broad_scan` | `broad_scan_v1.txt` — ✅ live, ersetzt `quick_filter` seit Task 10 |
| `deep_analysis` | **`deep_analysis_v2.txt`** (Batch, `thin`, Polarität, R/R 1:2), `policy_monitor_v1.txt` |
| `commodities_crypto` | **`commodities_crypto_v3.txt`** (Batch nach `asset_class`, seit C.15) |
| `portfolio_check` | **`portfolio_check_v2.txt`** |
| `revalidation` | `trade_proposals_v1.txt` |

⚠️ **A/B-Testing ist nicht implementiert** (verifiziert 2026-08-09). Die Version ist im
Modul fest verdrahtet; ein Wechsel ist eine Code-Änderung. Die Tabelle `prompt_versions`
wird angelegt und **nie benutzt** — sie gehört zu Sprint 3D.

⚠️ `prompts/portfolio_check_v1.txt` ist verwaist: genutzt wird v2. Dasselbe gilt seit
Plan 3a für `deep_analysis_v1.txt`, und seit C.15 für `commodities_crypto_v1.txt`
**und** `commodities_crypto_v2.txt` (genutzt wird jetzt v3).

**Prompts werden direkt in der aktiven Datei angepasst — keine neuen Versionsdateien**
(PROJECT_STATUS Regel 10; seit 2026-09-08 überschreibbar, seit 2026-09-10 ohne neue
`_vN.txt`). Das Version-Suffix ist nur noch ein Dateiname. Womit eine konkrete Prediction
erzeugt wurde, ist nur über `git log -p prompts/<datei>` plus dem `date` der Prediction
rekonstruierbar.

**Prompts gehören zu jeder Änderung** (Regel 15, seit 2026-09-10): Code-, Config-, Schema-,
Spec-, Cron- oder Universums-Änderungen ziehen **immer** eine Prüfung aller Dateien in
`prompts/` nach sich — Ticker/Epics, Uhrzeiten, Run-Types, JSON-Schlüssel, zitierte
Schwellen, Sektor-/Regime-Listen, Modellnamen, Sprache. Die `*_pins_contract`-Tests
fangen nur die Schlüssel, an denen Code hängt; Beispieltexte und Zahlen prüft niemand
automatisch — deshalb `grep -rn "<Bezeichner>" prompts/` bei jeder Änderung.

Zwei Testarten hängen daran, sie sind **nicht** dasselbe:
- **Vertragstests** (`test_deep_analysis_v2_pins_contract`,
  `test_commodities_crypto_v3_pins_contract`) prüfen, dass die **aktive** Datei die
  Schlüssel enthält, auf die der Parser sich verlässt (`"results"`, `"evidence_quality"`,
  `"thin"`, Polaritätsregel). Sie werden durch die Regeländerung **wichtiger**, nicht
  überflüssig: sie sind das Netz, das eine Prompt-Bearbeitung auffängt, die den Vertrag bricht.
- **`*_untouched`-Tests** (`test_deep_analysis_v1_untouched`,
  `test_commodities_crypto_v2_untouched`) erzwangen ausschließlich die **alte** Regel und
  bewachen heute nur noch verwaiste Dateien — seit Regel 10 (2026-09-10: keine neuen
  Versionen) sind sie samt den vier Altlast-Dateien (`deep_analysis_v1`,
  `commodities_crypto_v1/v2`, `portfolio_check_v1`) Kandidaten zum Entfernen.

⚠️ Die Prompts werden **auf Modulebene** gelesen, nicht je Aufruf. Eine geänderte
Prompt-Datei wirkt erst nach einem Neustart des Prozesses.

---

### 12. **`src/cost_tracker.py`**

Tägliches API-Budget (Hard Cap: ~4 EUR/Run).

```python
class CostTracker:
    def add_from_result(result: ClaudeResult) -> None:
        """Claude SDK result object → parse input/output tokens + web_search_calls"""
    
    def add_call(model, input_tokens, output_tokens, web_search_calls) -> None:
        """Legacy 6-kwarg API (deprecated in Plan 3)"""
    
    def raise_on_cap_exceeded() -> raises CostCapExceeded:
        """wenn total_eur > hard_cap"""
```

**Hard Cap Logik in main.py:**
```python
current_phase = "..."           # wird durch den try-Block mitgeführt
try:
    phases_1_to_4(cost_tracker)
except CostCapExceeded as e:
    send_partial_email(cost_summary={"aborted_at_phase": current_phase})
```
✅ Seit `7c4c311` (Bug B-05) steht dort die **echte** Phase: `run_pipeline()` führt
`current_phase` mit, der `except`-Zweig liest sie. Das frühere
`_guess_aborted_phase()` gab immer `"policy_monitor"` zurück und liess die
Kosten-Abbruch-Mail systematisch auf die falsche Phase zeigen.

---

## Data Flow: Ein Beispiel

⚠️ **Illustration aus Sprint 1, keine Messung.** Die Zahlen stammen aus der
500-Ticker-Hochrechnung von damals; echte gemessene Läufe stehen in PROJECT_STATUS
(P2.10, P2.12: 20 Ticker, 3,13 bzw. 3,92 EUR). Der Ablauf stimmt, die Mengen nicht.

```
heute = 2026-05-20, run_type = "pre_market"

[main.run_pipeline("pre_market", "2026-05-20")]
  ↓
[Phase 0] analyze_trends()
  → 1 Sonnet + web_search
  ← {trends: [{name: "ai-capex", strength: 8, ...}], ...}
  ✓ costs ~0.20 EUR

  ↓
[Phase 1] collect(provider, sp500_tickers)
  → Capital.com × 500 (incremental: 1 Bar/Ticker, Indikatoren aus DB)
  ← 487 OK, 13 skipped
  ✓ costs ~0.00 EUR

  ↓
[Phase 2] broad_scan_batch() — seit Plan 2, Task 10 (2026-08-15)
  → 1 Sonnet-Call + Websuche über ALLE Ticker
  ← {ticker: {news_strength: 0-3, news_note}}

  ↓
[Phase 2a] cutoff_candidates()
  → news_strength ≥ 1 ODER tech_strength ≥ TECH_MIN_FOR_DEEP, gedeckelt bei
    MAX_DEEP_ANALYSIS = 50 (seit Task 10 gelesen, vorher 80 und tot)
  ← selected, all_evaluated → db.log_cutoff() schreibt BEIDE (reiner Code, 0 EUR)
  ⓘ Echte Kosten/Auswahlgrössen (20-Ticker-Live-Messung, nicht diese
    Sprint-1-Illustration): PROJECT_STATUS C.7, Befund 9

  ↓
[Phase 3] run_policy_monitor()
  → 1 Sonnet + web_search
  ← policy_risk_level, events
  ✓ costs ~0.10 EUR

  ↓
[Phase 3] analyze_batches()          # seit Plan 3a: Batch statt 1 Call/Ticker
  → build_batches() gruppiert nach Sub-Sektor (BATCH_SIZE_DEEP = 8)
  → Sonnet × 1 Call PRO BATCH + web_search, gestreamt (sequential!)
  ← (analyses, failed) — failed = Ticker, deren Batch auch nach
    Wiederholung und Halbierung nichts lieferte
  ⚠️ Kosten hier NICHT belastbar: der Testlauf lief mit zu knappem
    Token-Budget, s. PROJECT_STATUS C.9

  ↓
[Phase 3b] analyze_commodities_and_crypto()      # seit C.15 (2026-08-19): Batch statt 1 Call/Asset
  → build_batches() gruppiert nach asset_class (Commodities: 3, Crypto: 4)
  → Sonnet × 2 Calls (1 pro Batch) + web_search, gestreamt
  ← 7 Assets (Gold, Silver, Brent, BTC, ETH, SOL, XRP)
  ✓ costs ~0.35 EUR (unveraendert, weniger Calls != weniger Tokens)

  ↓
[Phase 4] rank_and_persist()
  → Guardrail-Filter + signal_checks (enforce nur um 16:10) + Top-10
  → db.predictions + db.guardrail_rejects schreiben
  ✓ costs ~0.00 EUR

  ↓
[Phase 4a] check_open_positions()          # seit B.5 NACH Phase 4
  → if db.predictions[status='open' & learnable=1 & date < today] exists
  → Sonnet × N Calls, OHNE web_search (nutzt die Phase-3-Analysen)
  ← N Empfehlungen (HALTEN/SCHLIESSEN/ANPASSEN)
  ✓ costs ~0.20 EUR

  ↓
[Phase 5] render_daily_html() + send_daily_email()
  → 4 HTML-Sektionen
  → Resend API
  ✓ costs ~0.00 EUR

TOTAL: ~3.50 EUR
[Phase 4a Cost Cap Hit] → send_partial_email(aborted=True) → exit
```

---

## Invarianten (Never Violated)

1. **SIMULATION_ONLY=True** – Niemals echte Order-Ausführung
2. **CFD-Kurzfristfokus** – hold_days ≤ 5 (`config.MAX_HOLD_DAYS`); `guardrails.py`, `evaluator.py`, `portfolio_check.py` und `db.py` referenzieren seit 2026-07-17 alle denselben Wert statt eigener hardcodierter Konstanten (Bug B-06 behoben). intraday_range ≥ 1 % (`guardrails.min_intraday_range_pct`, einziger Volatilitätsfilter; `SP500_MIN_ATR_PCT`/`SP500_MIN_MARKET_CAP_B` waren nie verdrahtet und sind seit 2026-09-10 entfernt, s. PROJECT_STATUS C.32)
3. **Phase 0 ist fatal** – TrendAnalyzerError → no email
4. **Billing vor Parse** – `cost_tracker.add_from_result()` VOR JSON-Extraktion
5. **Guardrail-Pflicht** – Vor Phase 4 Ranking MÜSSEN alle Analysen durch Checks
6. **Atomare DB-Writes** – `evaluator.update_outcome_close` ACID-transactional
7. **Portfolio-Sektion zuerst** – Email-Rendering: Portfolio → Stocks → Trends → Commodities
8. **Timezone** – Alle datetime-Berechnungen in `ZoneInfo("Europe/Berlin")`; Bash: `TZ="Europe/Berlin" date`.
   **Ausnahme:** alles, was an der US-Sitzung hängt (`signal_window.py`, der
   `trade_proposals`-Slot), rechnet in `America/New_York` — s. dort
9. **`price_history` enthält nur FINALE Tagesbars** – ein Schreiber im Betrieb
   (`final_close`), `historical_loader` als manueller Backfill. Beide schreiben nie den
   laufenden Tag. Die Vermischung von provisorisch und final war der Frozen-Bar-Bug
10. **Eine offene Prediction je Trade-Idee** – `trade_proposals` löst die `pre_market`-Zeile
    über `status='superseded'` + `superseded_by` ab, statt eine zweite daneben zu legen.
    Das Urteil steht auf der **alten** Zeile (`revision_verdict`). Seit 2026-08-15 erzwingt
    das ein partieller UNIQUE-Index `ux_predictions_one_open_per_idea` auf
    `(date, ticker, direction) WHERE status='open'` — bewusst partiell, sonst könnten
    abgelöste und ablösende Zeile (die sich alle drei Spalten teilen) nicht nebeneinander
    stehen. Daraus folgt eine erzwungene Reihenfolge in `supersede_prediction()`: die alte
    Zeile muss `status='open'` verlassen, **bevor** die neue eingefügt wird — SQLite prüft
    den Index je Statement, nicht beim Commit. `record_revision()` kann seither **nicht**
    mehr ablösen (Parameter `superseded_by` entfernt); dafür gibt es ausschliesslich
    `supersede_prediction()`, das INSERT und UPDATE in einer Transaktion hält (C1, P2.8).
    Bestandsdatenbanken bereinigt `init_schema()` selbst: die ältere von zwei offenen
    Duplikaten geht auf `closed_stale_pre_rollout`. Details: PROJECT_STATUS P2.13
11. **Ein Lauf ohne brauchbare Historie startet nicht** – der Guard in `main` bricht
    `pre_market` und `trade_proposals` ab, bevor Kosten entstehen (seit 2026-08-08)
12. **Tests telefonieren nicht nach draussen** – ausserhalb `tests/live/` sperrt ein
    Autouse-Fixture auf Transport-Ebene
13. **Ladefenster ≥ längster Indikator + Reserve** – `load_price_history_from_db()` muss
    mindestens die Länge des längsten Indikators tragen, aktuell **220** Bars (SMA200
    braucht 200; die 20 Bars Reserve verhindern, dass der Wert an einer einzigen
    fehlenden Bar hängt). ✅ **`GAP_SCAN_BARS` trägt seit Plan 2, Task 3 (`da4cab1`)
    ebenfalls 220** — Lückenprüfung und Ladefenster sind wieder **eine** Zahl. Bei 200
    gegen 220 war eine Lücke auf Bar 201–220 unsichtbar, verzerrte aber SMA200. Die
    Anhebung ändert die Ticker-Auswahl (mehr erkannte Lücken → mehr Nachladeversuche,
    ggf. mehr Skips) und war deshalb in Plan 1 nicht erlaubt, s. PROJECT_STATUS C.6/C.7

---

## Testing-Strategie

- **Unit Tests**: isolierte Module, Mock-Claude, Fixtures
- **Integration Tests** (4): volle Pipeline + E2E-HTML-Render + trade_proposals-Flow
- **Coverage Gate**: 80 % Minimum (aktuell 91,52 %)
- **Baseline**: `pytest tests/ --cov=src --cov=main --cov-fail-under=80 -q` →
  **777 passed, 14 skipped**, 0 failures (Stand 2026-08-17, nach der
  Token-Neukalibrierung — s. PROJECT_STATUS C.9 und C.10). Die übersprungenen sind die Live-Tests unter `tests/live/`; sie
  laufen nur mit `--run-live` und sprechen dann echte APIs an (inkl. echtem Mailversand).
  ⚠️ **Grüne Tests sind hier kein Reifezeugnis:** der `max_tokens`-Befund aus C.9 ist
  gegen die echte API entstanden, nicht im Testlauf — die Unit-Tests mocken `call_claude()`
  und können ein zu knappes Token-Budget grundsätzlich nicht sehen. Dieselbe Lücke hatte
  der `web_search_calls`-Bug: ein grüner Test mockte `server_tool_use` als Objekt, während
  die echte API ein `dict` liefert.

---

## Sprint 2 / Plan 1 — umgesetzt (2026-05-22)

Plan: `docs/superpowers/plans/2026-05-21-sprint2-plan1-capital-provider-db-incremental.md`

- **capital_provider.py** – CapitalComProvider (alleiniger OHLC-Provider, GET /positions, premarket)
- **fundamentals_cache** – Finnhub-Fundamentals mit 7-Tage TTL
- **DB-Incremental-Update** – täglich nur 1 Bar fetchen, Indikatoren aus DB (200 Tage)
  *(der Bar-Abruf im Analyse-Lauf ist im Preismodell-Umbau entfallen, s. P3 — die
  Indikatoren kommen weiterhin aus der DB, die Tagesbar schreibt nur noch
  `final_close`. Steht hier als Sprint-2-Historie, nicht als Ist-Zustand)*
- **position_check Run-Type** – Capital.com Position-Read + Claude + Status-Mail
  *(in Sprint 3B / Plan 2 restlos entfernt, `59f5e2c` — steht hier nur als
  Sprint-2-Historie, nicht als Ist-Zustand)*
- **Timezone-Fix** – `ZoneInfo("Europe/Berlin")` in Python, `TZ="Europe/Berlin"` in Bash
- **historical_loader.py** – 3-Jahres-Pull via Capital.com (`--all`, `--full-sp500`, `--tickers`).
  Seit Sprint 3B zusätzlich die reinen Status-Modi `--reactivate` / `--list-inactive`;
  die Modus-Gruppe ist `required=True` (Aufruf ohne Flag ist ein Fehler, kein Default-Pull).
  Seit 2026-08-08 ausserdem `--universe` (voller Backfill über `universe.full_universe()`)
  und `--report-coverage` (Bars je Ticker, markiert alles unter `MIN_BARS_RSI`).
- **Universums-Skalierung** – `USE_FULL_SP500` wählt zwischen `SP500_PROD_TICKERS`
  (150, sektor-balanciert, der Produktivstand seit 2026-08-21) und
  `SP500_FULL_TICKERS` (451 verifizierte Ticker). Der frühere Stub-Zustand
  (Bug B-03) ist seit C.21/C.23 erledigt; die 150er-Auswahl beschreibt C.24.
  ⚠️ Ausgewertet wird das Flag an **genau einer** Stelle:
  `universe.stock_universe()`. Bis 2026-08-21 stand der Ausdruck fünffach im
  Code — ein Test (`test_universe.py`) hält die Einzelquelle jetzt fest.
  ⚠️ Die Universumsgrösse ist **nicht** die Zahl der Tiefenanalysen:
  `MAX_DEEP_ANALYSIS = 50` deckelt Phase 3 unabhängig davon.

---

## Geplante Architektur-Änderungen (Sprint 3B / 3C)

Vollständige Spezifikation: `docs/superpowers/specs/PROJECT_STATUS.md`.
Kurzüberblick, was sich an der oben beschriebenen Architektur ändern wird:

**Bereits umgesetzt** (Sprint 3B / Plan 1, abgeschlossen 2026-07-29):

| Bereich | Änderung |
|---|---|
| Pipeline | **Phase 0b neu**: Markt-Kontext (VIX, A/D-Ratio, Regime) — ersetzt das hardcodierte `None`-Dict vor dem Ranking |
| `data_collector` | Gap-Erkennung mit Handelstags-Logik + automatisches Nachladen fehlender Bars |
| `data_collector` | Inaktive Ticker überspringen; Sektor-Mapping organisch pflegen |
| Schema | `ticker_status`, `sectors` (21 Sub-Sektoren statt der ursprünglich geplanten 11 GICS), `ticker_sectors`, `guardrail_rejects`, `sector_momentum` + 5 neue Spalten |
| Retention | news 90→30 Tage, skipped_tickers-Events 30→90 Tage, `ticker_status` nie gelöscht |
| `ranking` | Rejects werden persistiert; `predictions.sector` kommt aus `ticker_sectors` |
| `main` | B-05 gefixt: echte Abbruch-Phase statt Platzhalter |

### Sprint 3B / Plan 2 — umgesetzt (2026-07-30 bis 2026-08-04)

Code vollständig, 20/20 Tasks, alles auf `main`. ✅ `analyze.yml` seit 2026-08-18 reaktiviert
(nach erfolgreichem `bootstrap-db`). Ausgeführt und verifiziert sind `pre_market`, `close`,
`final_close` und seit 2026-08-14 auch `trade_proposals` (lokal, gegen Wegwerf-Kopien, zu den
echten Cron-Zeiten) — PROJECT_STATUS P2.10, P3.5, P2.12. Erster Produktionslauf am 2026-08-18.
Offen bleibt nur noch `weekly`: zugestellt, aber nicht inhaltlich geprüft.

| Bereich | Änderung |
|---|---|
| Run-Types | `midday`, `evaluate`, `position_check` entfernt; neu `trade_proposals` (16:10 Berlin) |
| Pipeline | **Phase 1c**: offene Capital.com-Positionen als Pflicht-Kandidaten für Phase 3 — seit C.37 auch die **einzige Quelle** des Portfolio-Checks (4a) |
| Pipeline | **Phase 1d**: Sektor-Momentum verdrahtet (war toter Code) |
| Pipeline | **Phase 4 vor 4a** — 4a nutzt die fertigen Phase-3-Analysen, ohne Web-Search. Mail-Reihenfolge bleibt: Portfolio zuerst |
| Module | **neu** `src/signal_checks.py` und `src/revalidation.py` (s. 10a/10b) |
| Guardrails | Momentum-Signale angewandt (hartes Reject nur bei Übereinstimmung); die vier Momentum-Spalten werden befüllt |
| `close` | Holt Schlusskurse aller Ticker; TP/SL-Auswertung bleibt bis 3D — ⚠️ **überholt:** `close` ist am 2026-08-18 ersatzlos entfallen (C.14) |
| Weekly-Mail | vier B.9-Blöcke aus `guardrail_rejects`, `ticker_status`, `revision_verdict` und der Sub-Sektor-Abdeckung |
| Tagesmail | `hold_days_recommended` als Spalte „Haltedauer" (B.11) |

**Noch offen:**

| Bereich | Änderung | Sprint |
|---|---|---|
| `run_weekly` | `cost_summary` ist hart auf Nullen verdrahtet — die Weekly-Mail meldet dauerhaft 0,00 EUR. Es fehlt ein `db.load_cost_summary()` | 3C |
| Schema | Neue Spalte `predictions.ranking_score` | 3C |
| `ranking` | `atr_pct`/`rsi_at_entry`/`volume_ratio` korrekt befüllen; kombinierter `ranking_score` **zusätzlich** zu `total_score` | 3C |
| Phase 2 | Technischer Python-Pre-Filter (ATR/RSI/Volume/Market-Cap) vor dem Haiku-Batching | 3C |

⚠️ **Der Pre-Filter ist keine Optimierung, sondern die einzige Mengenbegrenzung.**
`MAX_DEEP_ANALYSIS = 80` und `BATCH_SIZE_QUICK = 30` sind tote Konstanten — nirgends im
Code gelesen. Gemessen am 2026-08-09: alle 20 Ticker gingen in Phase 3, 2,53 der
3,13 EUR entfielen darauf. Bei `MAX_COST_PER_RUN_EUR = 4.00` sind das 78 % des Caps bei
4 % der Zielgröße.

---

## Änderungen 2026-08-08/09 — Sichtbarkeit und Datenintegrität

Aus der Ursachenanalyse der leeren Läufe vom 2026-08-04 (PROJECT_STATUS P2.4/P2.9):

| Bereich | Änderung |
|---|---|
| **neu** `src/universe.py` | eine Quelle des Ticker-Universums (s. 10d) |
| **neu** `.github/workflows/bootstrap-db.yml` | einmaliger Backfill der CI-DB, nur `workflow_dispatch`, teilt die `concurrency`-Gruppe mit `analyze.yml` |
| `main` | Historien-Guard am CLI-Einstieg — Abbruch bei zu dünner Datenlage, bevor Kosten entstehen. Ausgenommen `final_close`, `close`, `weekly` |
| `data_collector` | `_skip()` loggt jeden Skip mit Grund; `collect()` gibt die Verteilung gebündelt aus (D1) |
| `data_collector` | Lückenerkennung prüft den gesamten jüngsten Abschnitt (`GAP_SCAN_BARS = 220`, deckungsgleich mit dem Ladefenster) statt nur `MAX(date)`. ⚠️ Innenliegende Lücken erst ab **zwei** aufeinanderfolgenden Handelstagen — einzelne fehlende Wochentage sind US-Feiertage |
| `ranking` | Enthaltungen (`direction='none'`) werden gezählt und in der Phase-4-Zeile mitgeführt, bleiben aber **kein** Reject (D2); ein Lauf ohne Prediction warnt von sich aus (D3) |
| `db` | `skip_reason_counts()` — Skip-Gründe eines Laufs, gruppiert auf der Art des Grundes |
| `historical_loader` | schreibt den laufenden Tag nicht mehr (fiel bei Krypto auf, das durchgehend handelt) |

---

Siehe auch: `PROJECT_STATUS.md` für Roadmap + Sprint-Spezifikationen,
`docs/superpowers/plans/` für abgeschlossene Task-Pläne.
