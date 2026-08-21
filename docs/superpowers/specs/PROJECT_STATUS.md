# PROJECT_STATUS.md — Shares_Future (Trading_Harry)

**Zuletzt aktualisiert:** 2026-08-18 — 🗑️ **Run-Type `close` (22:30) ersatzlos
entfallen.** Aktiv sind nur noch `pre_market`, `trade_proposals`, `final_close`,
`weekly`. Zuerst fiel `evaluate_open_predictions()` weg — ein liegen gebliebenes Duplikat,
dessen Begründung (B.6: „sonst schreibt niemand `outcomes`") seit `final_close` hinfällig
war, und das um 22:30 auf einer noch nicht finalen Tagesbar arbeitete und damit Treffer
verschlucken konnte. Danach war `run_close()` vollständig redundant: `cleanup_old_data()`,
Gap-Fill und die **wertgleiche** `technical_indicators`-Zeile erledigt `pre_market` um
15:00 ohnehin — Indikatoren können sich im Tagesverlauf konstruktionsbedingt nicht ändern.
Dazu zwei aktive Nachteile (Kurs-Sweep ohne Nutzen, 1,5× schnellere Auto-Deaktivierung).
**841 Tests grün, 92,39 % Coverage.** Details: **C.14**.

Davor, 2026-08-18 — ✅ **Plan 3b (Ranking) abgeschlossen (12/12
Tasks).** `rank_score` (`analysis_strength × tech_strength`) ersetzt `probability_pct`
als Sortierschlüssel, `candidate_class` trennt core/divergence/conflict in
Persistierung und Aggregaten, der C.1-Fix (`atr_pct`/`rsi_at_entry`/`volume_ratio`) ist
mitgenommen, `score_total()`/`DIMENSION_WEIGHTS` sind entfernt. Der anschliessende
Gesamt-Review über alle 12 Commits fand **zwei Critical-Befunde**, beide an Nähten, die
kein Einzel-Task-Review sehen konnte — `analysis_strength()` zählte für jeden Short
verkehrt herum, `candidate_class` ging beim 16:10-Ablösen einer Divergenz-Prediction
verloren — plus drei Important-Befunde; alle fünf in einer Fix-Welle behoben, Re-Review
bestätigt: ADDRESSED, keine neue Breakage. Live-Testlauf gegen eine Wegwerf-Kopie: 7
core-Predictions (2 long, 4 short, 1 Commodity), 0 divergence, 0 conflict — plausibel;
Top-10-Sortierung von Hand nachgerechnet, korrekt; 0 Mutations-Leck in den
Portfolio-Check-Prompt; 1,9187 EUR, keine Kostenregression gegenüber C.11. **838 Tests
grün, 92,36 % Coverage.** Details: PROJECT_STATUS **C.13**.

Davor, 2026-08-17 — ✅ **Plan 3a (Batch-Tiefenanalyse) abgeschlossen:
Abschluss-Review über `e3dc5a7..HEAD` durchgeführt (C.12), keine kritischen Befunde.**
Vier Important-Befunde, alle behoben — anders als bei Plan 2 keine fehlenden
Produktions-Aufrufer, ausschliesslich Doku-/Prompt-Konsistenz: CLAUDE.md und
ARCHITECTURE.md widersprachen sich intern (Kopf sagte „live verifiziert", Sprint-Stand
bzw. Dateikopf weiter unten noch „nicht produktionsreif"), der `BATCH_SIZE_DEEP`-Kommentar
in `config.py` rechnete mit der alten 900er-Formel, `commodities_crypto_v2.txt` widersprach
im selben Prompt dem eigenen `thin`-Mechanismus, und die Plan-Datei selbst hatte die beiden
Fix-Commits nicht nachgezogen. **Offen bleibt nur noch Plan 3b** (Ranking). Details: **C.12**.

Davor, 2026-08-17 — ✅ **Verifikationslauf bestanden (C.11): der
Token-Fix wirkt, das Kostenziel ist unterboten.** `stop_reason=max_tokens` trat **kein
einziges Mal** auf, **12 von 12 Kandidaten analysiert** (vorher 8 bzw. 14 von 16), Budget
zu 47–54 % genutzt, Phase 3 bei **0,0204 EUR je Ticker** gegen ein Ziel von 0,034 und
~0,12 im alten Weg. Gesamtlauf 1,9072 EUR in 14,6 min. ⚠️ Wie knapp der alte Wert war:
der 8er-Batch brauchte 9 409 Tokens bei einem alten Budget von 9 200 — **2,3 % daneben**,
nicht grob falsch. Dabei ein **zweiter** `web_search_calls`-Zählfehler gefunden und
behoben (gestreamte Antworten tragen kein `usage.server_tool_use`; gezählt werden jetzt
ersatzweise die Content-Blöcke) — und ein eigener Fehlalarm korrigiert, der aus der
kaputten Zählung eine erfundene Recherche gelesen hatte. **777 Tests grün, 91,52 %.**

Davor, 2026-08-17 — **Token-Budget neu kalibriert (C.10).**
`TOKENS_PER_TICKER_DEEP` 900 → 2500, `BATCH_TOKEN_RESERVE` 2000 → 200 (der feste
Reserve-Term machte die Formel regressiv: 1150 Tokens/Ticker bei n=8 gegen 2048 bei n=2 —
grosse Batches bekamen am wenigsten Luft, genau verkehrt herum), und nach einer Kappung
wird nicht mehr identisch wiederholt, sondern mit doppelter Decke
(`BatchTruncatedError`). Das allein war in beiden Messläufen ~21 % der Laufkosten für
garantiert wertlose Ergebnisse. **775 Tests grün, 91,52 % Coverage.**
⏳ **Nur gegen Unit-Tests belegt, nicht gegen die echte API** — der Verifikationslauf
gegen eine Wegwerf-DB steht aus und ist der nächste Schritt. Details: **C.10**.
Dabei gefunden, bewusst offen: `cost_tracker.MODEL_PRICING` kennt kein Claude-5-Modell
und würde bei einem Modellwechsel `ValueError` werfen — relevant, weil Sonnet 5 ($2/$10)
rund ein Drittel billiger ist als das genutzte Sonnet 4.6 ($3/$15).

Davor, 2026-08-16 — ⚠️ **Plan 3a Task 10: Testlauf gegen echte Daten
gemessen — `MAX_TOKENS_DEEP` reicht nicht.** Zwei Läufe gegen eine Wegwerf-Kopie von
`data/tracking.db` (`run_type=pre_market`, 20 MVP-Ticker, echte Capital.com-/Finnhub-/
Anthropic-Calls, Mailversand über ungültigen `RESEND_API_KEY` unterdrückt): einmal mit
`BATCH_SIZE_DEEP=8` (Default), einmal mit `BATCH_SIZE_DEEP=4`. **`stop_reason=max_tokens`
trat in beiden Läufen mehrfach auf — auch nach dem Halbieren, in Lauf 2 sogar bei einem
auf 2 Ticker halbierten Batch (4096 Tokens).** Lauf 1 verlor 8 von 16 Kandidaten komplett
(50 %, 1,8501 EUR), Lauf 2 verlor 2 von 16 (12,5 %, 2,3842 EUR) — die kleinere Batchgrösse
kostete dabei **mehr**, nicht weniger, weil die meisten 4er-Batches erst nach zwei
gescheiterten Versuchen auf 2er-Hälften halbiert werden mussten. `config.py` ist auf
`BATCH_SIZE_DEEP=8` zurückgesetzt (Testwert 4 nicht committet). Details, alle sechs
Prüffragen aus Spec § 12 und Empfehlung: **C.9**. Task 10 ist mit diesem Befund
abgeschlossen; Task 11 (Doku) folgt erst nach einer Entscheidung über
`TOKENS_PER_TICKER_DEEP`, weil die Doku sonst einen Wert als „gemessen und gut"
beschreiben würde, der es nicht ist.

Davor, 2026-08-15 — ✅ **Plan 2 (Trichter) ist abgeschlossen:
Abschluss-Review über `c978d70..HEAD` durchgeführt, vier Befunde gefunden und behoben.**
Zwei davon verfehlten den erklärten Zweck ihrer eigenen Task:
**(R1)** Phase 2b hatte trotz Spec § 4.7 **keinen Produktions-Aufrufer** — Task 7 baute
`fetch_missing_fundamentals()` und schrieb „das macht Task 10", Task 10 tat es nicht.
Behoben mit `run_phase_2b()`, das die Werte auch in die `td`-Dicts zurückspiegelt (der
naheliegende Ein-Zeilen-Fix hätte nur den Cache für morgen gewärmt) und dabei Spec § 18.1f
einlöst. **(R2)** Die Ratenbegrenzung aus Task 11 zählte Methodenaufrufe statt echter
Requests — `get_fundamentals()` setzt drei ab — und hätte den Wochenlauf mit ~120
Requests/min gegen ein 60/min-Limit fahren lassen. Dazu **(R3)** `tech_strength` fehlte in
`cutoff_log`, obwohl es den Cutoff mitentscheidet, und **(R4)** dieselbe Tabelle war die
einzige Ereignistabelle ohne Retention. Details: **C.8**.
**746 Tests grün, 91,28 % Coverage** (`--cov=src --cov=main`). Offen: nur noch Plan 3
(Analyse & Ranking).

Davor, 2026-08-15 — **Plan 2 (Trichter), Task 13: Doku — alle 13 Tasks
abgeschlossen.** `docs/ARCHITECTURE.md` nachgezogen: Modul 3 (`quick_filter.py`) als
„ersetzt" markiert, Modul 3b (`broad_scan.py`) als „live", die grosse Pipeline-Grafik auf
Phase 2/2a (Nachrichten-Scan + Cutoff) und Phase 1 (Gate/Sweep/Process) aktualisiert,
`cutoff_log` in der Tabellenübersicht ergänzt, `FinnhubProvider`-Ratenbegrenzung
dokumentiert, veraltete Test-Baseline (647 Tests / 93,32 %) auf den echten Stand korrigiert.
**Plan 2 (Trichter) ist damit vollständig umgesetzt** — der Trichter läuft live und ist
gegen echte Daten gemessen (3,3551 EUR, günstiger als der alte Weg über `quick_filter`).
Offen bleibt nur noch der Abschluss-Review über `c978d70..HEAD`, dann Plan 3
(Analyse & Ranking). **733 Tests grün, 91,52 % Coverage.**

Davor, 2026-08-15 — **Plan 2 (Trichter), Task 12: Wochenlauf-Vorlauf.**
`main._update_weekly_fundamentals()`, verdrahtet vor dem wöchentlichen Aggregat in
`run_weekly()`: füllt `fundamentals_cache` **und** `earnings_next_date` fürs ganze
Universum. **Bug-Fix gegenüber dem Plan-Pseudocode:** dessen Skip-Prüfung („ist gecacht?")
hätte einen vom Tageslauf frisch gecachten Ticker (der nie Earnings mitbringt, R15) für
immer übersprungen und er hätte nie ein Earnings-Datum bekommen. Details: **C.7**,
Befund 11 (Bug-Fix) und Befund 12 (Testlaufzeit).

Davor, 2026-08-15 — **Plan 2 (Trichter), Task 11: Finnhub-Ratenbegrenzung.**
`FinnhubProvider._respect_rate_limit()`: Sliding-Window-Drosselung (60 Calls/60s),
instanzgebunden statt modulweit wie im Plan-Pseudocode. Details: **C.7**, Befund 10.

Davor, 2026-08-15 — **Plan 2 (Trichter), Task 10: Verdrahtung, live gemessen.**
`main.run_pipeline()` ruft jetzt `broad_scan_batch()` + `cutoff_candidates()`
+ `adapt_cutoff_to_quick_filter()` statt `quick_filter_batch()`; `MAX_DEEP_ANALYSIS`
80 → 50. **Live gegen eine Wegwerf-Kopie von `data/tracking.db` gemessen** (echte
Capital.com-/Finnhub-/Anthropic-Calls, 20 MVP-Ticker, kein Mailversand):
**3,3551 EUR, kein `CostCapExceeded`** — güns­tiger als der alte Weg (3,9217 EUR am
14.08.). Die **Kostendeckel-Sorge aus dem letzten Eintrag war eine unbestätigte
Vermutung und lag falsch**: der Cutoff schloss 5 von 20 Tickern aus der teuren Phase 3
aus, das spart mehr als `broad_scan` zusätzlich kostet. Details, Lehre und
Phasen-Aufschlüsselung: PROJECT_STATUS **C.7**, Befund 2 (Korrektur) und Befund 9.

Davor, 2026-08-15 — **Plan 2 (Trichter), Task 9: Cutoff + `cutoff_log`.**
TDD, gegen den echten Sidecar aus Task 5/6 implementiert, nicht gegen den Plan-Pseudocode
blind übernommen — drei Abweichungen vom Plan-Pseudocode dabei gefunden (Details **C.7**,
Befund 6).

Davor, 2026-08-15 — **Doku-Abgleich gegen das echte Repo.**
Der Stand von **Plan 2 des Analyse-Pipeline-Umbaus (Trichter)** stand in keinem Dokument:
8 der 13 Tasks waren committed und gepusht (Vorfixes, Batch-Kurs-Sweep, Phase-1-Zerlegung,
Technik-Signal im Sidecar, Fundamentals-Entkopplung, `broad_scan.py`), während Kopf und
Roadmap weiter „Einstieg ist jetzt Plan 2" sagten. Neu damals: Abschnitt **C.7**.

Davor, 2026-08-15 — **Die Live-Verifikation von Plan 2 (Sprint 3B) ist abgeschlossen.**
Am 2026-08-14 liefen `pre_market`, `trade_proposals` und `close` zu den echten Cron-Zeiten
gegen eine Wegwerf-Kopie. **E3 (Ablösung statt Dublette) und E5 (gedrehte Signale werden
gemeldet, nicht gehandelt) verhalten sich exakt wie spezifiziert** — 8 Signale, 5 abgelöst,
3 offen ohne Nachfolger, genau eine offene Zeile je Trade-Idee. Alle drei Mails zugestellt.
Details und vier Befunde: Abschnitt **P2.12**.
✅ Ein Befund war ein echter Datenfehler (vier doppelte offene Predictions aus einem
Doppellauf am 13.08.) — bereinigt **und die Ursache geschlossen**: ein partieller
UNIQUE-Index erzwingt die Invariante „je Trade-Idee genau EINE offene Prediction" jetzt in
SQLite. **707 Tests grün, Coverage 90,94 %.** Details: **P2.13**.
⏳ Offen: `weekly` (nie inhaltlich verifiziert), der `bootstrap-db`-Lauf, danach die
Reaktivierung von `analyze.yml`.

Davor, 2026-08-12 — **Plan 1 (Fundament) des Analyse-Pipeline-Umbaus ist
code-fertig**, Tasks 2–8 committed (Task 9 zieht diese Dokumente nach). 17 Indikatoren
laufen mit und füllen 29 neue Spalten in `technical_indicators`; das Technik-Signal ist
berechenbar, steuert aber nichts. **Keine Verhaltensänderung.** 647 Tests grün, Coverage
93,32 %. Details: Abschnitt **C.6**. (Plan 2 hat darauf aufgesetzt und ist zu 13 von 13
Tasks umgesetzt — s. **C.7**, nicht mehr „Einstieg".)
⚠️ Der abschliessende Ganz-Branch-Review fand die Verhaltensänderungs-Garantie zunächst
gebrochen vor (29 neue Werte liefen in vier Claude-Prompts mit) plus einen strukturellen
`ichi_chikou`-Bug — Fix-Wave-Details unten in C.6.

⚠️ **Befund aus der Design-Phase, seit `f8f6684` behoben:** `cost_tracker` zog
Cache-Treffer zweimal ab (`fresh_input`, Zeile 52). **Alle vor 2026-08-12 gemessenen
Laufkosten sind damit zu niedrig ausgewiesen** — grob 5 % beim Lauf vom 2026-08-09,
wachsend mit der Cache-Trefferquote. Dieselbe Fehlannahme steckte in `cache_hit_rate`,
die dadurch über 1 gehen konnte.

Davor, 2026-08-09 — **Live-Verifikation weitgehend erledigt.**
`pre_market`, `close` und `final_close` sind ausgeführt und geprüft (P3.5, P2.10); die
Ursache der leeren 04.08.-Läufe ist geklärt (P2.4) und in sechs Commits behoben (P2.9).
Sämtliche `.md`-Dokumente sind auf diesen Stand gezogen (P2.11).
**608 Tests grün, Coverage 93,47 %.**

✅ **Abgeschlossen:** `bootstrap-db`-Lauf (2026-08-08), Reaktivierung von `analyze.yml`
(2026-08-18, erster Lauf erfolgreich).
⏳ **Offen:** `weekly` (nie ausgeführt und nicht inhaltlich verifiziert).

Davor, 2026-08-06 — Task-20-Review abgeschlossen: **acht Defekte behoben**
(3 Criticals, eingefrorene Tagesbar, beide Weekly-Blöcke, Winter-Cron, Netzsperre), Details
in **P2.8**. Kosten- und `MAX_DEEP_ANALYSIS`-Aussagen sind in B.1, B.13, C.4 und F.1
vereinheitlicht — die Widersprüche gegen die eigene Korrekturbox sind raus.

**Aktueller Branch:** `main`, alles gepusht (Stand 2026-08-09: `origin/main` = lokal).
Einen Branch `sprint3b/plan2-pipeline-umbau` gibt es weder lokal noch remote.
**Letzter Merge:** Sprint 2 / Plan 1 (2026-05-22) — Sprint 3 in Arbeit, Roadmap s. Abschnitt 2

> **Historie dieser Kopfzeile** — zwei Aussagen, die hier lange falsch standen und
> jeweils Arbeit gekostet haben. Beide bleiben als Warnung stehen:
>
> **Korrektur 2026-08-03:** Dieses Dokument und `CLAUDE.md` behaupteten, der Plan-2-Code
> liege auf einem eigenen, ungepushten Feature-Branch. Falsch — remote existiert
> ausschliesslich `main`, alle Plan-2-Commits sind dessen Vorfahren.
>
> **Korrektur 2026-08-08:** Es hiess, die Pipeline sei „kein einziges Mal" gelaufen.
> Ebenfalls falsch — am 2026-08-04 liefen drei Läufe erfolgreich durch, nur eben ohne
> Predictions. Ursache inzwischen geklärt (P2.4).
>
> **Lehre daraus:** Aussagen über Branch- und Ausführungsstand gegen das echte Repo
> prüfen (`git ls-remote`, `gh run list`), nicht aus dem Gedächtnis fortschreiben.

---

## 1. Was gebaut wurde

### Sprint 1 — Foundation (abgeschlossen, gemerged 2026-05-20)
**159 Tests, 89.62% Coverage.**

| Modul | Was gebaut |
|---|---|
| `config.py` | Alle Konstanten, Ticker-Listen (MVP 20 + Commodity + Crypto), DIMENSION_WEIGHTS (in Plan 3b entfernt, s. C.13), Capital.com-Credentials |
| `src/db.py` | Vollständiges SQLite-Schema: price_history, technical_indicators, fundamentals, predictions, outcomes, skipped_tickers, trend_analyses, market_context, cost_tracking, prompt_versions, news_summaries, position_recommendations |
| `src/providers/base.py` | DataProvider-Interface |
| `src/providers/yfinance_provider.py` | yFinance-Implementierung (primary in Sprint 1, in Sprint 3 entfernt) |
| `src/providers/finnhub_provider.py` | Finnhub für Fundamentals (7-Tage-Cache) |
| `src/cost_tracker.py` | CostTracker: Token-Zählung, EUR-Schätzung, CostCapExceeded-Exception |
| `src/utils.py` | `call_claude()`, `extract_json_blob()` (mit raw_decode für trailing commentary) |
| `src/trend_analyzer.py` | Phase 0: Megatrend-Analyse via Claude + Web-Search |
| `src/data_collector.py` | Phase 1: OHLC + technische Indikatoren (RSI, MACD, ATR, BB, SMA) |
| `src/quick_filter.py` | Phase 2: Batch-Analyse à 30 Ticker, kein Web-Search, Top 80 |
| `src/deep_analysis.py` | Phase 3: Policy-Monitor + Tiefenanalyse (8 Score-Dimensionen) |
| `src/commodities_crypto.py` | Phase 3b: Gold, Silber, Öl, BTC, ETH, SOL, XRP immer |
| `src/portfolio_check.py` | Phase 4a: Open Positions mit TP/SL-Empfehlung |
| `src/ranking.py` | Phase 4: Top 10 Long + Top 10 Short, persist predictions |
| `src/evaluator.py` | Walk-Forward-Evaluator: TP/SL/Timeout-Schließung von Predictions |
| `src/guardrails.py` | Qualitätskontrolle: min. 2 Belege je Score-Dimension |
| `src/email_sender.py` | Daily-Mail (3 Sektionen), Weekly-Mail, Position-Check-Mail, Error-Mail |
| `main.py` | Orchestrator: run_pipeline, run_close, run_evaluate, run_weekly, run_position_check |
| `.github/workflows/analyze.yml` | CI: 6 Crons, DB-Persistenz via GitHub Releases (db-latest), wöchentlicher Snapshot |
| `prompts/` | Versionierte Prompt-Dateien |
| `tests/` | Unit + Integration Tests |

---

### Sprint 2 / Plan 1 — Capital Provider + DB Incremental + Position Check (abgeschlossen, gemerged 2026-05-22)

| Modul | Was gebaut |
|---|---|
| `src/providers/capital_provider.py` | CapitalComProvider: lazy session auth (CST + X-SECURITY-TOKEN), `get_price_history()`, `get_ohlc_after()`, `get_premarket_price()`, `get_open_positions()`, `get_closed_positions()`, TICKER_MAP für epics |
| `src/db.py` — Ergänzungen | `fundamentals_cache`-Tabelle (UNIQUE ticker, 7-Tage-TTL), `insert_price_bar_if_missing()`, `load_price_history_from_db()`, `get_cached_fundamentals()`, `save_fundamentals_cache()`, `update_outcome_close()`, Migration-Guards (`_apply_migrations`) |
| `src/providers/finnhub_provider.py` | `get_fundamentals()` implementiert (PE, Forward-PE, Market-Cap, D/E, Sector, Analyst-Consensus) — Finnhub Free, 403-Bug bei `price_target` entfernt |
| `main.py` — position_check | `run_position_check()`: Capital.com GET /positions → Claude → Position-Check-Mail (**in Sprint 3B / Plan 2 entfernt**, `59f5e2c` — hier nur als Sprint-2-Historie) |
| `setup/historical_loader.py` | 3-Jahres-Pull aller SP500-Ticker via Capital.com; Flags: `--all`, `--full-sp500`, `--tickers` |
| `config.py` | `USE_FULL_SP500`-Flag, `SP500_FULL_TICKERS` (noch Stub = MVP-Liste), `CAPITAL_COM_IDENTIFIER` |
| `analyze.yml` | `CAPITAL_COM_IDENTIFIER`-Secret hinzugefügt |
| Timezone-Fix | `ZoneInfo("Europe/Berlin")` überall in Python, `TZ="Europe/Berlin"` in Bash |
| Briefing-Box | "Was heute zählt" in Daily-Mail |
| Error-Mail | `send_error_email()` bei Exception im Main-Orchestrator |

---

### Sprint 3 — bereits erledigte Teilstücke

| Was | Commit / Datum | Details |
|---|---|---|
| yFinance komplett entfernt | `d17c2f5` (2026-07-09) | `src/providers/yfinance_provider.py` gelöscht, `yfinance` aus `requirements.txt`, `config.py` (`YFINANCE_*` → `CAPITAL_COM_BATCH_PAUSE`), `main.py` instanziiert unconditional `CapitalComProvider()`, Tests angepasst. Capital.com ist seither alleiniger OHLC-Provider ohne Fallback. |
| DST-Bug (ehem. Bug B-01) gefixt | `d17c2f5` (2026-07-09) | `analyze.yml`: Run-Type-Erkennung matcht jetzt `github.event.schedule`-String direkt per `case`, statt Uhrzeit zu parsen. Damit auch Bug B-04 (Kommentar/Code-Mismatch) hinfällig. |
| Toter Code entfernt | `e198520`, `b3d743c` (2026-07-09) | `src/providers/paid_provider.py` + zugehöriger Test gelöscht. |
| Lokales Docker-Test-Image | `4320036`, `977e71a` (2026-07-13) | `Dockerfile`, `docker-compose.yml` — führt einzelne Run-Types manuell aus (`docker compose run --rm trading-harry --run-type X`). Kein Scheduler/Cron im Container; automatisierte Ausführung bleibt ausschließlich GitHub Actions vorbehalten. |
| Vollständige Code-Dokumentation | `e3b6e86` (2026-07-15) | Jedes Modul hat eine Modul-Beschreibung, jede Funktion einen 1-2-Satz-Docstring. Gilt ab jetzt als Standard für neuen Code. |
| Intraday-Widerspruch in Prompts behoben | (2026-07-17) | `prompts/deep_analysis_v1.txt` + `prompts/commodities_crypto_v1.txt`: "hold 1-3 trading days"-Framing entfernt. Intraday ist explizit das primäre UND einzige Ziel — Setups, die nicht klar intraday funktionieren, müssen `direction='none'` sein. `hold_days_recommended` bleibt Pflichtfeld (für das Learning Modul), ist aber kein Akzeptanzkriterium mehr. |
| Bug B-06 behoben: MAX_HOLD_DAYS vereinheitlicht | `c2c8e1c` (2026-07-17) | `guardrails.py`, `evaluator.py`, `portfolio_check.py`, `db.py` nutzen `config.MAX_HOLD_DAYS` (=5) als einzige Quelle der Wahrheit statt eigener hardcodierter `3`. Tests angepasst + neuer Test beweist die 5-Tage-Ausweitung im Walk-Forward-Evaluator. |
| **Sprint 3B / Plan 1, Schnitt 4: Tasks 10–14 — Plan 1 ABGESCHLOSSEN** | `e53fd18`, `ccb3010`, `7698276`, `7c4c311` (2026-07-29) | `src/market_context.py` (Phase 0b: VIX, A/D-Ratio, Regime via Claude + Websuche) inkl. `prompts/market_context_v1.txt` und `db.save_market_context()`; Verdrahtung in `run_pipeline()` — das hardcodierte `None`-Dict ist weg, `predictions.vix_at_prediction` und `market_regime` tragen echte Werte; Gap-Erkennung in Phase 1 (`_expected_trading_days`, `_fill_price_gaps`); B-05 gefixt. Docker-Smoke-Test grün, Migration gegen eine bestehende `tracking.db` verifiziert. 380 Tests, 92.42% Coverage. |
| **Sprint 3B / Plan 1, Schnitt 3: Tasks 8, 9, 9a** | `6ab199d`, `6c42cc2`, `6fb3290` (2026-07-28) | `guardrail_rejects` mit gruppiertem Regelnamen (`_rule_name()` deckt alle 12 Meldungen von `GuardrailsChecker` ab); `predictions.sector` kommt jetzt aus `ticker_sectors` statt aus dem marktweiten Kontext-Dict, wo der Key nie gesetzt war; Retention auf 30/180/90 umgestellt; `sector_momentum` + `collect_sector_momentum()` erheben beide D9-Signale. Live gegen Capital.com + Finnhub verifiziert (s. Abschnitt B.3.1). 329 Tests, 92.09% Coverage. |
| **Sprint 3B / Plan 1, Schnitt 2: Tasks 5–7** | `c035f6c`, `031868d`, `18aa1cb` (2026-07-27) | `ticker_status` mit kumulativem Skip-Zähler, Deaktivierung ab >20 Skips, Auto-Retry nach 30 Tagen; `collect()` überspringt inaktive Ticker ohne API-Call und heilt den Zähler bei Erfolg; CLI `--reactivate` / `--list-inactive`. **Verhaltensänderung:** die Modus-Gruppe von `historical_loader.py` ist jetzt `required=True` — ein Aufruf ohne Flag (oder mit vertipptem Flag) bricht mit argparse-Fehler ab, statt wie bisher stillschweigend den vollen `SP500_MVP_TICKERS`-Pull zu starten. Gegen die echte Capital.com-API mit `FAKEXXXX` verifiziert: Zähler 1→21, Umschlag bei 21, 0 Calls bis `retry_after`, Retry danach, Fehlschlag verlängert die Sperre. 280 Tests, 91.95% Coverage. |
| **Sprint 3B / Plan 1, Schnitt 1: Tasks 3–4 + zwei Loader-Fixes** | `a4211d5`, `990597f`, `ea624ef`, `0e539c4` (2026-07-27) | `sectors` + `ticker_sectors` inkl. Seeding und `resolve_sector_id`; organische Befüllung in Phase 1. Dazu zwei unabhängige `historical_loader`-Bugs behoben (s. Abschnitt 3). Live-Lauf bestätigt 18/20 MVP-Ticker gemappt. 254 Tests, 91.8% Coverage. |
| **Sprint 3B / Plan 1, Tasks 1–2: Sub-Sektor-Taxonomie** | `7a11a00`, `aec7a2f`, `89f9c04` (2026-07-27) | `config.SUB_SECTOR_ETFS` (21 Sub-Sektoren auf 19 ETFs), `config.SECTOR_ALIASES` (104 Finnhub-Aliase), `CapitalComProvider.search_markets()`, `setup/verify_epics.py`. Alle 19 ETFs + VIX gegen die Capital.com Demo-API verifiziert. Branch `sprint3b/plan1-fundament`. |
| **Sprint 3A: Roadmap-Überarbeitung** | (2026-07-27) | Dieses Dokument. Der alte Plan "Cron-Struktur umbauen (pre_open/post_open-Split)" wurde in einer Review-Session **verworfen** und durch die Sprints 3B–3F unten ersetzt. |

---

## 2. Sprint-3-Roadmap

> **Reihenfolge:** 3B → 3C → 3D → 3E → 3F. Jeder Sprint wird vor Implementierungsbeginn
> in einer eigenen Session besprochen und bekommt eine eigene Plan-Datei unter
> `docs/superpowers/plans/`.

| Sprint | Inhalt | Status |
|---|---|---|
| 3A | Roadmap + Doku aktualisieren | ✅ erledigt (dieses Dokument) |
| 3B | Cron-Struktur + Pipeline-Umbau | 🟢 **Code vollständig, Live-Verifikation abgeschlossen** — Plan 1 (2026-07-29) und Plan 2 (20/20 Tasks, 2026-08-04), alles auf `main`. Verifiziert: `pre_market`, `close`, `final_close` (P2.10, P3.5) und **`trade_proposals` inkl. E3/E5 (2026-08-14, P2.12)**. ⏳ Offen: `weekly`, `bootstrap-db`-Lauf, dann Reaktivierung von `analyze.yml` |
| **3B-M** | **Mail-Provider-Wechsel (Zwischensprint)** | ✅ **ABGESCHLOSSEN 2026-07-30** — Mailversand läuft über **Resend**, eigene Domain verifiziert, Zustellung live bestätigt. Details s. unten |
| 3C | Ranking-Überarbeitung | 🟡 **Plan 1 (Fundament) abgeschlossen** (C.6) · **Plan 2 (Trichter) abgeschlossen inkl. Abschluss-Review**, 13/13 Tasks + vier behobene Review-Befunde, s. **C.7** und **C.8** · Plan 3 (Analyse & Ranking) offen. C.1–C.4 sind in den Analyse-Pipeline-Umbau aufgegangen |
| 3D | Learning Modul | ⚠️ **Platzhalter — Planungssession ausstehend** |
| 3E | Human-in-the-Loop | ⚠️ **Platzhalter — Planungssession ausstehend** |
| 3F | Volle 500-Ticker-Skalierung | ⚠️ **Platzhalter — Planungssession ausstehend** |

---

## Sprint 3B — Cron-Struktur + Pipeline-Umbau

### B.1 — Ziel-Cron-Struktur ✅ *(umgesetzt 2026-07-30, `02ab4ba` + `59f5e2c`)*

> Die Tabelle unten ist seit dem Umbau **Ist-Stand, nicht Plan**. `midday`, `evaluate`
> und `position_check` sind restlos entfernt — Run-Type, Cron-Eintrag, Funktionen,
> Prompt-Datei, Mail-Renderer und Tests. `main.py:RUN_TYPES` kennt nur noch die vier
> Zeilen darüber.

| Run-Type | Zeit (Berlin) | Änderung | Kosten (geschätzt) |
|---|---|---|---|
| `pre_market` | 15:00 Mo–Fr | **unverändert** — volle Pipeline Phase 0–5 | **3,31 EUR bei 20 Tickern** (gemessen) |
| `trade_proposals` | 16:10 Mo–Fr¹ | **NEU** — ersetzt `evaluate` vollständig (anderer Zweck, s. B.2) | ~0,5–0,7 EUR (E1) |
| `close` | 22:30 Mo–Fr | **vereinfacht** (s. B.6) | ~0,00 EUR |
| `final_close` | 02:15 / 01:15 (= **00:15 UTC**), **täglich** | **NEU** (Preismodell-Umbau, s. P3) — holt die finalen Tagesbars und bewertet. Kein Claude-Call, keine Mail | ~0,00 EUR |
| `weekly` | So 20:00 | Struktur unverändert, **Inhalt erweitert** (s. B.9) | ~0,00 EUR |
| ~~`midday`~~ | — | **komplett entfernen** | — |
| ~~`evaluate`~~ | — | **ersetzt durch `trade_proposals`** | — |
| ~~`position_check`~~ | — | **komplett entfernen** | — |

¹ Der Cron hängt an der **US-Eröffnung**, nicht an Berlin: 10:10 America/New_York, also
14:10 UTC unter EDT und 15:10 UTC unter EST. `analyze.yml` hat beide Slots, der Workflow
verwirft den jeweils falschen. Mit nur dem Sommer-Slot lief der Lauf von November bis
März **vor** der Eröffnung (Fix 2026-08-06).

**`pre_market` bleibt explizit unverändert.** Der frühere Plan, ihn in `pre_open` (nur Phase 0+1)
und `post_open` (Phase 0–4) aufzuspalten, ist verworfen.

⚠️ **Kostenwirkung — die frühere Rechnung hier war falsch und ist zurückgezogen.**
Sie lautete „alt ~6,60 → neu ~4,20 EUR/Tag bei 500 Tickern, ~88 EUR/Monat, 3F-Ziel
bereits getroffen". Beide Eingangsgrößen stimmen nicht: der erste echte Messlauf am
2026-07-29 kostete **3,31 EUR für 20 Ticker** (nicht ~3,20 EUR für 500), und einen Deckel
auf Phase 3 gibt es nicht (`MAX_DEEP_ANALYSIS` ist tot). Das ~90-EUR-Ziel für 3F ist damit
**nicht** getroffen, sondern offen — die belastbare Hochrechnung steht in F.1.

Gesichert ist nur die *Richtung*: der Wegfall von `midday` und der Ersatz von `evaluate`
durch das billige `trade_proposals` (E1) senken die Tageskosten. Um wie viel, entscheidet
sich erst mit dem Pre-Filter aus C.4.

**Zu entfernen (vollständig, keine Leichen):**
- `midday`: Cron-Eintrag in `analyze.yml`, Run-Type in `main.py:RUN_TYPES`, Dispatch in `main()`,
  `workflow_dispatch`-Option, alle Referenzen in Tests und Doku
- `position_check`: Cron-Eintrag, Run-Type, `run_position_check()`, `prompts/position_check_v1.txt`,
  `render_position_check_html()` + `send_position_check_email()` in `email_sender.py`, zugehörige Tests
- **Begründung position_check:** kein Mehrwert — offene Capital.com-Positionen sind jederzeit
  live auf dem Handy einsehbar.
- **Bleibt erhalten:** `CapitalComProvider.get_open_positions()` — wird von der neuen Phase 1c gebraucht.

### B.2 — `trade_proposals` (neuer Run-Type, 16:10 Berlin)

**Zweck:** Nach dem Opening-Rauschen (US-Open 15:30 Berlin) prüfen, ob die `pre_market`-Signale
noch gültig sind, und konkrete Handlungsempfehlungen für den Tag geben.

> ### ⚠️ Aktualisiert 2026-08-04 (Task 20): Schritt 2 und 6 sind durch E1/E3 überholt
>
> Die Tabelle unten beschrieb den Stand vor der Planungssession vom 2026-07-30. Zwei
> Zeilen gelten so **nicht mehr**:
>
> - **Schritt 2 — keine zweite Tiefenanalyse.** Gemessen kostet eine Phase-3-Analyse
>   ~0,12 EUR / ~54 s; 27 Assets wären ~3,24 EUR gegen den 4-EUR-Deckel gewesen.
>   Stattdessen prüft `src/revalidation.py` **billig ohne Websuche** nach (E1),
>   Ist-Aufwand ~0,5–0,7 EUR/Lauf. Breaking News deckt der eine Policy-Monitor-Call ab.
> - **Schritt 6 — kein Vergleich `pre_market` vs. `trade_proposals`.** Durch die
>   Ablösung (E3) hat jede Trade-Idee genau **ein** Outcome; eine Trefferquote je
>   `run_type` ist damit nicht mehr berechenbar. Der 16:10-Lauf *ersetzt* die
>   Morgenzeile über `status='superseded'` + `superseded_by`, statt eine zweite
>   danebenzulegen — sonst schlösse der Evaluator beide und jede Kennzahl zählte
>   doppelt. Was stattdessen gemessen wird, steht in B.9/Block 1.
>
> Ergänzend **E5:** Ein gedrehtes oder hart verworfenes Signal wird **gemeldet, nicht
> gehandelt**. Das Gegensignal lief nie durch Phase 3, hat also weder Belege noch ein
> hergeleitetes TP/SL. Es bleibt offen und wird regulär ausgewertet — nur so lässt sich
> messen, ob die Ablehnung richtig lag.

| Schritt | Was passiert |
|---|---|
| 1 | Frische Kurse für **ALLE** Ticker (SP500 + Commodities/Crypto) von Capital.com laden und in `price_history` schreiben — nicht nur für die Top-Listen |
| 2 | ~~Nur die `pre_market` **Top 10 Long + Top 10 Short + alle 7 Commodities/Crypto** erneut durch Phase 3 (Tiefenanalyse) schicken~~ → **E1:** billige Re-Validierung ohne Websuche über `src/revalidation.py` |
| 3 | `probability_pct` vorher (`pre_market`) vs. nachher (`trade_proposals`) pro Ticker vergleichen |
| 4 | Zusätzliche Checks (s. B.3) |
| 5 | Update-Mail: Vorher/Nachher-Vergleich pro Ticker (**bestätigt / geschwächt / gedreht / unverändert**) plus die neuen Checks |
| 6 | ~~Alle Predictions dieses Runs ebenfalls in `predictions` speichern … damit das Learning Modul später `pre_market` vs. `trade_proposals` vergleichen kann~~ → **E3:** die Morgenzeile wird **abgelöst**, nicht dupliziert; das Urteil steht als `revision_verdict` auf der **alten** Zeile |

### B.3 — Neue Checks in `trade_proposals`

> ### ⚠️ Aktualisiert 2026-08-04 (Task 20): zwei Korrekturen aus der Umsetzung
>
> - **Die Checks werden in BEIDEN Läufen erhoben, aber nur um 16:10 durchgesetzt**
>   (E4). Gesteuert über den `enforce`-Parameter in `src/signal_checks.py`, den der
>   Aufrufer setzt. Um 15:00 ist die US-Börse zu — die Morgenmail ist ein
>   Research-Briefing, keine Handelsentscheidung. 3D bekommt trotzdem Messwerte aus
>   beiden Läufen, und `guardrail_rejects.enforced` trennt weiche Warnung (0) von
>   harter Ablehnung (1).
> - **Die VIX-Schwellen wirken kumulativ, nicht partitioniert.** Die Zeile unten las
>   sich als „25–35: nur high" und „ab 35: keine Longs". So gelesen wäre der Filter bei
>   VIX 40 *lockerer* als bei VIX 28 — ein mittelmässiges Short-Signal wäre bei 28
>   verworfen und bei 40 durchgelassen worden. Richtig ist: **ab 25 nur noch
>   `confidence='high'`, beide Richtungen, ohne Obergrenze; zusätzlich ab 35 keine
>   neuen Longs.** Monotonie ist nachgemessen (`926a059`).

| Check | Beschreibung | Wirkung |
|---|---|---|
| **Sektor-Momentum (hybrid)** | Zwei unabhängige Signale, s. Detailabschnitt unten | Hart **nur bei Übereinstimmung**, sonst weiche Warnung |
| **Relative Stärke** | Performance des Tickers vs. seinem Sub-Sektor | Score-Input |
| **Marktbreite** | Advancing/Declining-Ratio im S&P 500 | Kontext / Warnung |
| **VIX-Level** | **kumulativ:** ab 25 nur noch `confidence='high'` (beide Richtungen, ohne Obergrenze); **zusätzlich** ab 35 keine neuen Long-Signale | Hartes Filter-Kriterium (nur `enforce=True`) |
| **Opening-Gap-Check** | Großer Gap zwischen `pre_market`-Kurs und aktuellem Kurs | Warnhinweis in der Mail |
| **Entry-Fenster** | Empfehlung eines Pullback-Levels statt reinem Market-Entry | Zusatzfeld in der Mail |
| **Korrelations-Check** | Klumpenrisiko-Warnung wenn mehrere Signale im selben Sub-Sektor liegen | Warnhinweis in der Mail |

#### B.3.1 — Sektor-Momentum als Hybrid *(Entscheidung 2026-07-27)*

Statt eines einzelnen ETF-Signals werden **zwei unabhängige Momentum-Signale** je
Sub-Sektor erhoben und **getrennt gespeichert**:

| Signal | Quelle | NULL wenn |
|---|---|---|
| `etf_momentum` | Tagesperformance des Sub-Sektor-ETF von Capital.com | kein ETF für den Sub-Sektor verfügbar (z.B. Communication) |
| `db_momentum` | Ø Tagesperformance aller Ticker desselben Sub-Sektors, per SQL über `price_history` × `ticker_sectors` | weniger als **3 Ticker** im Sub-Sektor vorhanden |

Das DB-Signal kostet **0 EUR** — reine SQL-Aggregation, kein API-Call, kein Claude.

**Guardrail-Logik:**

| Lage | Verhalten |
|---|---|
| beide vorhanden, **gleiche Richtung** | hartes Signal — blockiert, wenn `SECTOR_GUARDRAIL_STRICT=True` |
| beide vorhanden, **widersprüchlich** | weiche Warnung, `guardrail_rejects.enforced = 0` |
| **nur eines** vorhanden | weiche Warnung, `guardrail_rejects.enforced = 0` |
| **keines** vorhanden | kein Check, **kein** Log-Eintrag |

Beide Werte werden zusätzlich an jeder Prediction und an jedem Guardrail-Reject
mitgeschrieben, damit Sprint 3D datenbasiert messen kann, welches der beiden
Signale besser mit den tatsächlichen Trade-Ergebnissen korreliert.

> **Reichweite bei MVP-Größe — gemessen am 2026-07-27:** von 21 Sub-Sektoren erreichen
> bei der 20-Ticker-MVP-Liste nur **zwei** die 3-Ticker-Mindestgrenze: Retail
> (AMZN, WMT, HD) und Financials Rest (BRK-B, V, MA). Technology Hardware,
> Semiconductors und Pharma liegen bei je 2 Tickern, der Rest bei 1.
> Bis Sprint 3F die volle Ticker-Liste aktiviert, ist `db_momentum` also fast durchweg
> NULL und der Hybrid degradiert meist auf „nur ETF vorhanden" → weiche Warnung.
> Akzeptiert: die Struktur kostet nichts und trägt sofort, sobald 3F läuft.

> **Live bestätigt am 2026-07-28** (echter Capital.com-Pull, Handelstag 2026-07-27,
> 18/20 Ticker via Finnhub gemappt). Die Prognose oben stimmt exakt: **21/21
> Sub-Sektoren liefern `etf_momentum`** (alle 19 ETF-Epics antworten), aber nur
> **2 von 21** erreichen die 3-Ticker-Grenze für `db_momentum` — Retail
> (+2,89% ETF / +1,17% DB) und Financials Rest (+1,00% / +2,07%). Beide Paare
> zeigen in dieselbe Richtung, der harte Guardrail wäre also in genau 2 von 21
> Sub-Sektoren scharf.
>
> Zwei Beobachtungen für 3D, solange die Signale noch nicht bewertet werden:
> - Die Beträge weichen deutlich voneinander ab (Retail ETF ≈ 2,5× DB). XRT ist
>   gleichgewichtet und small-cap-lastig, unsere Retail-Ticker sind AMZN/WMT/HD.
>   Bei der Bewertung in Plan 2 zählt daher die **Richtung**, nicht der Betrag.
> - Ausgerechnet der größte Tagesmove hat keinen Gegencheck: Semiconductors
>   −2,50% (SOXX) mit nur 2 Tickern (NVDA, AVGO) → `db_momentum` NULL.

**Erledigte Detailfragen** (waren offen, entschieden am 2026-07-27):
- ✅ Datenquelle Sektor-ETFs + VIX: Capital.com, verifiziert per `setup/verify_epics.py`.
  20/20 Epics bestätigt, alle TRADEABLE, kein `TICKER_MAP`-Eintrag nötig.
- ✅ Marktbreite (A/D-Ratio): eigener Claude-Call mit Websuche (`src/market_context.py`),
  schreibt in die bestehende `market_context`-Tabelle.

### B.4 — Phase 1c (neu, nach Phase 1b)

Offene Capital.com-Positionen laden und die zugehörigen Ticker als **Pflicht-Kandidaten für
Phase 3** markieren. Diese überspringen den Quick-Filter-Ausschluss in Phase 2, unabhängig
vom Score.

**Annahme (zu bestätigen):** `get_open_positions()` liefert Capital.com-**Epics** zurück
(z.B. `GOLD`, `BTCUSD`, `BRKB`). Für den Abgleich mit internen Tickern wird eine Reverse-Map
zu `capital_provider.TICKER_MAP` gebraucht. Epics ohne Gegenstück in unserer Ticker-Liste
(manuell eröffnete Fremdpositionen) werden geloggt und übersprungen — für sie existieren
keine Indikator-Daten.

### B.5 — Phase 4 / 4a Reihenfolge tauschen

**Neu:** erst Phase 4 (Ranking der neuen Signale), dann Phase 4a (Portfolio-Check).

Phase 4a nutzt künftig die **fertigen Phase-3-Analyseergebnisse** der Ticker mit offenen
Positionen (aus Phase 1c markiert), statt eigene zusätzliche Web-Searches zu machen.

**Entscheidung (2026-07-27):** Phase 4a bleibt ein Claude-Call, aber **ohne `web_search`-Tool**.
Input: fertige Phase-3-Analyse + Original-These aus der DB. Output unverändert
`HALTEN / SCHLIESSEN / ANPASSEN` mit Begründung. Spart die Web-Search-Kosten, behält aber
das Urteilsvermögen und den Begründungstext für die Mail.

**Wichtig:** Die getauschte *Ausführungs*-Reihenfolge ändert **nicht** die *Mail*-Reihenfolge.
Die Portfolio-Sektion bleibt die erste Sektion der Tagesmail (dokumentierte Invariante,
s. Abschnitt 4).

### B.6 — `close` vereinfachen

**Neuer Umfang:**
1. **Schlusskurse ALLER Ticker** (SP500 + Commodities/Crypto) von Capital.com holen und in
   `price_history` schreiben *(neu — bisher nur implizit über den Evaluator)*
2. **TP/SL-Auswertung + P&L bleibt vorerst erhalten** *(Entscheidung 2026-07-27)*
3. DB-Cleanup mit angepassten Regeln (s. B.7)

**Zur Entscheidung bei Punkt 2:** Ursprünglich sollte die TP/SL-Auswertung sofort aus `close`
entfernt werden ("wandert ins Learning Modul"). Da aber `evaluate` gleichzeitig wegfällt, würde
zwischen 3B und 3D **niemand mehr `outcomes`-Rows schreiben** — das Learning Modul hätte
keine Trainingsdaten aus dieser Zeit. Deshalb: `evaluate_open_predictions()` bleibt in `close`,
bis das Learning Modul in 3D die Auswertung übernimmt. Erst dann wird sie hier entfernt.

> ✅ **Überholt am 2026-08-18 — die Begründung ist seit dem Preismodell-Umbau hinfällig.**
> Die Lücke, die diese Entscheidung schließen sollte, gibt es nicht mehr: `final_close`
> (00:15 UTC, eingeführt 2026-08-06, s. Abschnitt P3) wertet selbst aus und ist damit
> die zugesagte „andere Stelle, die `outcomes` schreibt". Der Aufruf in `close` war ab
> da ein **liegen gebliebenes Duplikat**, kein bewusster Zweitpfad — und nicht bloß
> redundant, sondern schädlich: um 22:30 Berlin ist die Tagesbar noch nicht final
> (Schluss 00:00 UTC), TP/SL werden aber gegen Tages-High/Low geprüft, das sich bis
> dahin nur ausweiten kann. `close` sah also ein zu enges Fenster, und weil
> `evaluate_open_predictions()` bereits geschlossene Predictions überspringt, gewann
> die zu früh geschriebene Zeile gegen die korrekte aus `final_close`.
> **Entfernt** (`run_close()` wertet nicht mehr aus); `final_close` ist die einzige
> Auswertungsstelle, beide Seiten der Invariante sind jetzt per Test gepinnt.

### B.7 — DB-Cleanup-Regeln (in `close`)

| Tabelle | Alt | Neu |
|---|---|---|
| `news_summaries` | > 90 Tage löschen | **> 30 Tage** löschen |
| `trend_analyses` | > 180 Tage löschen | unverändert |
| `skipped_tickers` | > 30 Tage löschen | **nicht mehr löschen** — stattdessen `skip_count` pro Ticker hochzählen; ab `skip_count > 20` Ticker als **inaktiv** markieren und nicht weiter analysieren |

**Annahme zum Schema (zu bestätigen):** Die heutige `skipped_tickers`-Tabelle ist ein reines
Event-Log — `log_skipped_ticker()` macht pro Skip ein `INSERT`, die Spalte `skip_count` steht
immer auf `1` und wird nie erhöht. Für die neue Anforderung braucht es beides:

- **Event-Log bleibt** (mit Datum) — die Weekly-Mail soll "welcher Ticker diese Woche wie oft
  und warum übersprungen" ausweisen (s. B.9)
- **Neue Aggregat-Tabelle `ticker_status`** (`ticker` UNIQUE, `skip_count`, `inactive`,
  `first_skip_date`, `last_skip_date`) führt den kumulativen Zähler und das Inaktiv-Flag

Geprüft wird das Flag in `data_collector.collect()`, bevor ein Ticker verarbeitet wird.
Migration über `_apply_migrations()` mit `PRAGMA table_info()`-Guard (Regel 5).

**✅ Entschieden (2026-07-27) — Reset des `inactive`-Flags:** zweigleisig.
`ticker_status.retry_after` setzt beim Deaktivieren ein Datum 30 Tage in der Zukunft;
ab diesem Tag versucht `data_collector.collect()` den Ticker wieder. Erfolg setzt
`skip_count = 0`, erneuter Fehlschlag verschiebt `retry_after` um weitere 30 Tage.
Zusätzlich `python setup/historical_loader.py --reactivate TICKER …` für den sofortigen
manuellen Override, plus `--list-inactive` zur Übersicht. Konstanten:
`config.TICKER_MAX_SKIPS = 20`, `config.TICKER_RETRY_AFTER_DAYS = 30`.

**✅ Entschieden (2026-07-27) — Retention:** `skipped_tickers`-Events werden nach
**90 Tagen** gelöscht (statt bisher 30), `news_summaries` nach **30 Tagen**
(statt 90), `trend_analyses` unverändert nach 180. Der Aggregat-Zähler in
`ticker_status` wird **nie** automatisch gelöscht oder zurückgesetzt — nur über
`retry_after` oder `--reactivate`.

### B.8 — Gap-Erkennung in Phase 1

In `data_collector.py`: bei jedem Datenabruf prüfen, ob zwischen dem letzten DB-Datum und
heute eine Lücke existiert. Wochenenden und Handelstage korrekt berücksichtigen (kein Gap,
wenn der letzte Handelstag Freitag und heute Montag ist). Bei echtem Gap: fehlende Bars
automatisch von Capital.com nachladen.

`setup/historical_loader.py` bleibt ausschließlich für die einmalige manuelle
Erstinitialisierung — kein automatischer Aufruf aus der Pipeline.

**Bekannte Einschränkung:** Ohne Börsen-Feiertagskalender werden US-Feiertage (Thanksgiving,
Independence Day, …) fälschlich als Gap erkannt. Der Nachladeversuch liefert dann schlicht
keine Bars — funktional unkritisch, kostet aber je einen leeren API-Call. Ein
Feiertagskalender ist optional und nicht Teil von 3B.

### B.9 — Weekly-Mail erweitern

Zusätzlich zum heutigen Inhalt (Long/Short-Trefferquote, Ø P&L, Trade-Liste, Gesamt-P&L):

| Neuer Block | Inhalt |
|---|---|
| **~~`pre_market` vs. `trade_proposals`~~ → bestätigt vs. abgelehnt** | ⚠️ **Neu formuliert 2026-07-30 (E3).** „Trefferquote getrennt nach `run_type`" ist nicht mehr berechenbar: durch den Ablöse-Mechanismus hat jede Trade-Idee genau **ein** Outcome. Verglichen werden stattdessen drei Gruppen — um 16:10 **bestätigt** (`run_type='trade_proposals'`), um 16:10 **abgelehnt** (`run_type='pre_market'` mit `revision_verdict IN ('gedreht','verworfen')`) und **nie geprüft** (`revision_verdict IS NULL`, eingegrenzt ab dem ersten 16:10-Lauf). Liegt die Trefferquote der abgelehnten unter der der bestätigten, verdient der Lauf seine Kosten. |
| **Signal-Veränderungs-Statistik** | Wie oft wurden Signale im `trade_proposals`-Run bestätigt / geschwächt / gedreht — und wie performten die jeweiligen Gruppen danach? |
| **Guardrail-Reject-Statistik** | Welche Guardrails haben diese Woche wie oft Signale verworfen (Intraday-Range, R/R, Momentum-Konsistenz, hold_days). Zeigt, ob Filter zu streng oder zu locker sind. |
| **Skipped-Ticker-Übersicht** | Welche Ticker wurden diese Woche wie oft übersprungen und warum — passend zur neuen `skip_count`-Logik (inaktiv ab >20). |

**Hinweis:** Für die Guardrail-Reject-Statistik werden die Reject-Gründe aktuell nur geloggt
(`ranking._guardrail_filter()` → `log.info`), nicht persistiert. 3B muss sie in die DB schreiben
(z.B. neue Tabelle `guardrail_rejects` oder Wiederverwendung von `skipped_tickers` mit
eigenem `reason`-Präfix).

### B.10 — Sub-Sektor-Datenbank-Struktur

> **Überarbeitet 2026-07-27.** Die ursprüngliche Fassung sah 11 GICS-Sektoren vor.
> Ersetzt durch **21 Sub-Sektoren**: ein Halbleiter-Setup gehört gegen SOXX geprüft,
> nicht gegen den breiten XLK, in dem Software und Hardware das Signal verwässern.

Grundlage für den Sektor-Momentum-Check (B.3.1) und die Sektor-Auswertung in der
Weekly-Mail. Drei neue Tabellen in `src/db.py`:

**1. `sectors`** — Referenztabelle der Sub-Sektoren mit zugehörigem ETF:

```sql
CREATE TABLE IF NOT EXISTS sectors (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    etf  TEXT NOT NULL
);
```

Wird beim DB-Setup aus `config.SUB_SECTOR_ETFS` befüllt (21 Sub-Sektoren auf 19 ETFs —
MedTech, Pharma und Healthcare Rest teilen sich XLV):

| Sub-Sektor | ETF | | Sub-Sektor | ETF |
|---|---|---|---|---|
| Semiconductors | SOXX | | Aerospace & Defense | ITA |
| Software | VGT | | Transport | XTN |
| Technology Hardware | XLK | | Industrials Rest | XLI |
| Biotech | XBI | | Metals & Mining | XME |
| MedTech | XLV | | Real Estate | XLRE |
| Pharma | XLV | | Utilities | XLU |
| Healthcare Rest | XLV | | Consumer Staples | XLP |
| Oil & Gas | XOP | | Consumer Discretionary Rest | XLY |
| Clean Energy | ICLN | | Banks | KBWB |
| Retail | XRT | | Financials Rest | XLF |
| Auto | CARZ | | | |

**Alle 19 ETFs + VIX sind am 2026-07-27 gegen die Capital.com Demo-API verifiziert**
(exakter Epic-Treffer, TRADEABLE, Instrumentenname gegengelesen). Neue Einträge nie
ungeprüft ergänzen: Capital.com führt z.B. das Epic `PPH` für die PPHE Hotel Group,
nicht für den gleichnamigen Pharma-ETF.

**Nicht abbildbar**, weil Capital.com keinen passenden ETF führt:
- **Communication** — weder XLC noch VOX, FCOM, IXP, XTL oder IYZ vorhanden.
  GOOGL/META laufen dauerhaft ohne ETF-Signal.
- **Chemie / Verpackung / Papier** — XLB, VAW und IYM fehlen. Nur der Bergbauteil ist
  über XME abgedeckt, deshalb heisst der Sub-Sektor „Metals & Mining" und nicht
  „Materials" — er misst genau das und nicht mehr.

**2. `ticker_sectors`** — Mapping Ticker → Sub-Sektor:

```sql
CREATE TABLE IF NOT EXISTS ticker_sectors (
    ticker     TEXT PRIMARY KEY,
    sector_id  INTEGER REFERENCES sectors(id),
    source     TEXT DEFAULT 'finnhub',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Befüllung: organisch in Phase 1** (`data_collector.py`) aus dem
Finnhub-Fundamentals-Cache. Kein statisches Ticker→Sektor-Mapping im Code.

**3. `sector_momentum`** *(neu, 2026-07-27)* — die beiden Momentum-Signale je
Sub-Sektor und Run, getrennt gespeichert (s. B.3.1):

```sql
CREATE TABLE IF NOT EXISTS sector_momentum (
    date          TEXT NOT NULL,
    run_type      TEXT NOT NULL,
    sector_id     INTEGER NOT NULL REFERENCES sectors(id),
    etf_momentum  REAL,      -- NULL wenn kein ETF verfuegbar
    db_momentum   REAL,      -- NULL wenn < 3 Ticker im Sub-Sektor
    ticker_count  INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, run_type, sector_id)
);
```

> **Warum nicht in `market_context`:** die Tabelle hat `UNIQUE(date, run_type)`, hält also
> genau eine marktweite Zeile pro Run. Sektor-Momentum fällt pro Sub-Sektor an — 21 Werte
> je Run. Zwei Spalten in `market_context` könnten davon nur einen einzigen aufnehmen.

Zusätzlich bekommen **`predictions`** und **`guardrail_rejects`** je die Spalten
`sector_etf_momentum` und `sector_db_momentum` (REAL, nullable):
- in `guardrail_rejects`, um auswerten zu können, ob die weichen Warnungen richtig lagen
- in `predictions`, weil **nur** diese über `outcomes` mit echten Trade-Ergebnissen
  verknüpft sind. Verworfene Signale werden nie zu Trades und haben keine Outcomes —
  die von Sprint 3D geforderte Korrelation „welches Signal predictet besser" ist
  ausschliesslich über `predictions` berechenbar.

**Verifiziert am Live-Lauf (2026-07-27):** Phase 1 gegen Capital.com + Finnhub über
alle 20 MVP-Ticker — 20 verarbeitet, **18 gemappt**, 0 übersprungen. Einziger nicht
auflösbarer Rohwert: `Media` (GOOGL, META), und zwar erwartungsgemäß, weil Communication
mangels ETF gestrichen wurde. **Entscheidung bestätigt (2026-07-27): bleibt ungemappt.**

Zwei Rohwerte wichen von der Erwartung ab und sind hier festgehalten, damit sie nicht
erneut geraten werden: **ABBV meldet `Biotechnology`** (nicht `Pharmaceuticals`) und
landet daher bei XBI, **WMT meldet `Retail`** (nicht Consumer Staples) und landet bei XRT.

**Nutzung:** `trade_proposals` und `weekly` lesen den Sub-Sektor-ETF per JOIN
`ticker → ticker_sectors → sectors.etf`.

**✅ Entschieden (2026-07-27) — Namensabgleich Finnhub ↔ Sub-Sektoren:**
`config.SECTOR_ALIASES` (104 Einträge) bildet Finnhubs gemischtes `finnhubIndustry`-Vokabular
— Sektor-Ebene, Industrie-Ebene und Yahoo-Bezeichnungen — auf die 21 Sub-Sektoren ab.
Alias-Dict im Code statt in der DB: in git versioniert, unit-testbar, bei DB-Verlust nicht weg.
Der Lookup ist case- und whitespace-insensitiv. Nicht auflösbare Werte lassen `sector_id`
auf NULL und erzeugen einen WARN-Log mit dem exakten Rohwert, damit die Liste bewusst per
Commit wächst. Grundregel: **lieber ungemappt als falsch gemappt** — ein Momentum-Check
gegen ein fremdes Instrument erzeugt aktiv falsche Signale, ein fehlender Check nur keine.

**✅ Entschieden (2026-07-27) — Guardrail bei unbekanntem Sektor:**
`config.SECTOR_GUARDRAIL_STRICT`, initial `False`. Bei NULL-Sektor greift der Guardrail
nicht; das Signal geht mit Warnhinweis durch und bekommt eine `guardrail_rejects`-Zeile
mit `rule='sector_unknown'`, `enforced=0`. Die Weekly-Mail weist die Mapping-Abdeckung aus;
bei stabil hoher Quote wird das Flag auf `True` gestellt. Auch dann bleibt hartes Rejecten
auf den Fall beschränkt, dass **beide** Momentum-Signale vorliegen und übereinstimmen (B.3.1).

### B.11 — Kleinere Fixes in 3B

- ✅ **B-05 erledigt (2026-07-29, `7c4c311`):** `run_pipeline()` führt eine
  `current_phase`-Variable durch den `try`-Block; `_guess_aborted_phase()` ist
  ersatzlos entfernt. Ein Test je Phase stellt sicher, dass eine künftig ergänzte
  Phase ohne `current_phase`-Zuweisung auffliegt, statt die Abbruch-Mail falsch
  zu beschriften.
- ⏭ **E-Mail:** `hold_days_recommended` als eigene Spalte in der Top-10-Long/Short-Tabelle
  ergänzen — **gehört zu Plan 2**, zusammen mit den übrigen Mail-Arbeiten (B.9).

### B.13 — Phase 3 parallelisieren *(⚠️ ZURÜCKGEZOGEN 2026-07-30 — gehört wieder zu 3F)*

> **Diese Entscheidung wurde am 2026-07-30 umgekehrt (Plan-2-Entscheidung E2).**
> Ihre Begründung — `trade_proposals` fresse mit ~530 Actions-Minuten/Monat die
> Einsparung aus dem entfallenden `midday` wieder auf — beruhte auf der Annahme,
> der 16:10-Lauf schicke 27 Assets erneut durch die volle Phase 3. Mit der billigen
> Re-Validierung (E1) sind es **~220 statt ~530 Minuten**; die Summe liegt bei
> **~790/Monat** statt ~1 100 und damit klar unter den 2 000 des Free-Tarifs.
> Auch die Cron-Kollision ist bei MVP-Grösse entschärft (~25 min Lauf gegen 70 min
> Abstand). Die Parallelisierung zahlt erst auf 3F ein, wo `pre_market` allein bei
> ~2 090 Minuten/Monat läge. **Plan 2 enthält dazu keinen Task.**
> Der folgende Abschnitt bleibt als Begründungsdokument stehen.

**Ursprünglich entschieden (2026-07-29, überholt):** Die Parallelisierung von Phase 3 wird
**nicht** nach 3F verschoben, sondern in Plan 2 gezogen. Grund: sie entscheidet mit, ob die geplante Cron-Struktur
überhaupt tragfähig ist, und sie ist die einzige Maßnahme, die das Actions-Budget vor
dem Umzug auf ein privates Repo entlastet.

`src/deep_analysis.py` arbeitet die Ticker strikt sequenziell ab (`for td in
ticker_datas:`). Bei gemessenen ~54 s je Analyse macht das die Laufzeit fast vollständig
aus: von 25 Minuten Gesamtlauf entfallen 17 auf Phase 3.

**Actions-Minuten** (Repo ist aktuell public → unbegrenzt; privat sind es 2 000/Monat
im Free-Tarif, 3 000 im Pro-Tarif):

| | heute | nach 3B ohne Parallelisierung | nach 3B mit 5 parallelen Analysen |
|---|---|---|---|
| `pre_market` | 550 | 550 | ~180 |
| `midday` | 550 | entfällt | entfällt |
| `trade_proposals` | — (`evaluate` 22) | ~530 | ~180 |
| Rest | ~70 | ~22 | ~22 |
| **Summe/Monat** | **~1 190** | **~1 100** | **~380** |

> **Wichtig:** Sprint 3B senkt zwar die Euro-Kosten wie geplant, bei den Actions-Minuten
> passiert ohne Parallelisierung aber praktisch **nichts** — `trade_proposals` frisst
> die Einsparung aus dem entfallenen `midday` fast vollständig wieder auf, weil es
> 27 Assets erneut durch Phase 3 schickt. Das war in der ursprünglichen 3B-Rechnung
> nicht berücksichtigt, dort wurde nur in Euro gerechnet.

**Zwei Haken, die Plan 2 lösen muss:**
- `CostTracker` akkumuliert nicht thread-sicher
- die `MAX_COST_PER_RUN_EUR`-Prüfung würde racy — der Deckel könnte überschritten werden

**Löst nicht das Kostenproblem aus F.1.** Parallelisierung verkürzt die Laufzeit, nicht
die Rechnung. Für 3F braucht es zusätzlich einen **überhaupt erst zu bauenden** Deckel auf
Phase 3 — `MAX_DEEP_ANALYSIS` ist eine tote Konstante und deckelt heute nichts —, ein
günstigeres Modell für Phase 3 oder einen deutlich schärferen Pre-Filter aus 3C.

### B.12 — Stand der Umsetzung: Plan 1 fertig, Plan 2 umgesetzt

**Plan 1 (Fundament) ist abgeschlossen** (2026-07-29, Tasks 1–14, Plan-Datei
`docs/superpowers/plans/2026-07-27-sprint3b-plan1-fundament.md`). Er war
ausschliesslich **additiv**: die Pipeline läuft unverändert weiter, es kamen nur
neue Tabellen, Helper und der Phase-0b-Call dazu.

Geliefert: `sectors` / `ticker_sectors` / `ticker_status` / `guardrail_rejects` /
`sector_momentum`, `SECTOR_ALIASES`-Normalisierung, Skip-Zähler mit Auto-Retry,
beide Momentum-Signale, Markt-Kontext (Phase 0b), Gap-Erkennung, B-05.

**Plan 2 (Pipeline-Umbau) ist zu 20/20 Tasks umgesetzt** (2026-07-30 bis 2026-08-04).
Spec: `docs/superpowers/specs/2026-07-30-sprint3b-plan2-pipeline-umbau-design.md`,
Plan-Datei: `docs/superpowers/plans/2026-07-30-sprint3b-plan2-pipeline-umbau.md`.
**Vollständiger Stand, Entscheidungen und Befunde: eigener Abschnitt weiter unten.**

⚠️ **Umgesetzt heisst hier: der Code ist geschrieben, getestet und auf `main`.** Er lief
am **2026-08-04 dreimal erfolgreich** (`pre_market`, `trade_proposals`, `close`), erzeugte
dabei aber **keine Predictions**. Die Live-Verifikation (P2.4) durch lokal gehostete
Wegwerf-Kopien erfolgte später (2026-08-14, P2.12): alle Läufe erfolgreich, echte Mail
versendet. **`analyze.yml` seit 2026-08-18 wieder aktiv**, erster Produktionslauf
erfolgreich.

Eingangsvoraussetzungen für Plan 2 — **alle erfüllt**:
- ✅ verifizierte ETF-Epics (D8: 20/20 bestätigt, `setup/verify_epics.py`)
- ✅ Datenbasis für die Weekly-Auswertung (`guardrail_rejects`, `ticker_status`)
- ✅ beide Momentum-Signale live gemessen, inkl. der zwei Befunde in B.3.1
  (Richtung statt Betrag vergleichen; Abdeckungslücke bis 3F)

Zwei Dinge, die Plan 2 mitnehmen muss und die nicht aus dem Code hervorgehen:
- `predictions.sector_etf_momentum` / `sector_db_momentum` und die gleichnamigen
  Spalten in `guardrail_rejects` **existieren, werden aber noch von niemandem
  befüllt**. Plan 1 hat bewusst nur die Spalten angelegt.
- `ticker_sectors` ist in der produktiven `tracking.db` noch leer. Phase 1 füllt
  sie organisch beim nächsten vollen Run; bis dahin liefert `db_momentum`
  überall NULL.

---

## Sprint 3B / Plan 2 — Pipeline-Umbau 🟢 20 von 20 Tasks (Code), Verifikation offen

**Wo der Code liegt:** Tasks 1–17 als 25 Commits (`fd7e20a`…`58782e4`), Tasks 18–20 als
`0fec73b`, `ae0a79c`, `33b26c5` und der Doku-Commit — alles **direkt auf `main`, gepusht**.
Es gab nie einen Branch `sprint3b/plan2-pipeline-umbau` — remote existiert nur
`refs/heads/main` (`git ls-remote --heads origin`, 2026-08-03). Die Arbeit an 1–17 entstand
in einem anderen Klon und kam hier per Fast-Forward-Pull auf `main` an.
**Stand 2026-08-04:** 524 Tests, 92,36 % Coverage (`--cov=src --cov=main`; mit `--cov=src`
allein 93 %). Suite grün unter Europe/Berlin **und** UTC.

**Spec:** `docs/superpowers/specs/2026-07-30-sprint3b-plan2-pipeline-umbau-design.md`
**Plan:** `docs/superpowers/plans/2026-07-30-sprint3b-plan2-pipeline-umbau.md`

### P2.1 — Die fünf Entscheidungen der Planungssession (2026-07-30)

| # | Entscheidung | Warum |
|---|---|---|
| **E1** | `trade_proposals` prüft **billig ohne Websuche** statt voller Phase 3 | Gemessen kostet eine Tiefenanalyse ~0,12 EUR / ~54 s. 27 Assets wären ~3,24 EUR gegen den 4-EUR-Deckel gewesen. Breaking News deckt der eine Policy-Monitor-Call ab — einmal statt 27-mal. Ist-Aufwand: ~0,5–0,7 EUR/Lauf. |
| **E2** | B.13 (Parallelisierung) wandert zurück nach **3F** | Die Actions-Minuten-Begründung trägt nach E1 nicht mehr (s. B.13). |
| **E3** | `pre_market`-Predictions werden **abgelöst**, nicht dupliziert | `predictions` hat kein UNIQUE über (date, ticker, direction); der Evaluator hätte beide Zeilen geschlossen → doppelte Trefferquote und doppelter P&L. Zusätzlich: um 15:00 Berlin ist die US-Börse zu, die Morgensignale sind gar nicht handelbar. |
| **E4** | Checks in **beiden** Runs erheben, **nur um 16:10** durchsetzen | Die Morgenmail ist ein Research-Briefing, keine Handelsentscheidung. 3D bekommt trotzdem Messwerte aus beiden Läufen. |
| **E5** | Gedrehte Signale werden **gemeldet, nicht gehandelt** | Das Gegensignal lief nie durch Phase 3 — keine Belege, kein analytisch hergeleitetes TP/SL. Eine Position darauf zu eröffnen unterliefe die Guardrail-Grundregel. |

### P2.2 — Umgesetzt (Tasks 1–17)

| Schnitt | Tasks | Inhalt | Commits |
|---|---|---|---|
| 1 | 1–3 | `midday`, `evaluate`, `position_check` restlos entfernt; `analyze.yml` auf die Ziel-Crons; `trade_proposals` als Gerüst | `fd7e20a`, `02ab4ba`, `59f5e2c` |
| 2 | 4–6 | Phase 1c (offene Positionen als Pflicht-Kandidaten); Phase 4 vor 4a; Portfolio-Check ohne Websuche | `b5d4ba9`–`822f29e` |
| 3 | 7–10 | `src/signal_checks.py` neu; VIX-Filter + D9 mit `enforce`-Schalter; Sektor-Momentum verdrahtet; Momentum-Spalten befüllt | `14c9cf5`–`fc975df` |
| 4 | 11–14 | `superseded_by` + `revision_verdict`; `src/revalidation.py` + `prompts/trade_proposals_v1.txt`; `run_trade_proposals()` vollständig; 16:10-Mail | `ddc9df1`–`d05f5f5` |
| 5 | 15–16 | Opening-Gap-Check; End-to-End-Nachweis für E3 und E4 | `508c696`, `83fcb1c`, `9b3b1e0` |
| 6 | 17 | `close` holt die Schlusskurse aller Ticker | `0a546b0`, `0b7c952` |

**Zwei Commits ausserhalb des Plans**, beide auf ausdrückliche Anweisung:
`70f883b` und `58782e4` — Sperre gegen ausgehende HTTP-Aufrufe in Tests (s. P2.5).

**Ein weiterer Commit gehörte zu keinem Task:** `feee447` „add random" (2026-07-31) legte
vier Dateien unter `random/` ab — getrackt *und* in `.gitignore`, weil sie erzwungen
hinzugefügt worden waren (Ignore-Regeln greifen bei bereits getrackten Dateien nicht).

**Aufgelöst am 2026-08-06:**
- die beiden Sonden sind produktive Werkzeuge geworden und liegen jetzt bei den anderen:
  `setup/probe_ticker_deactivation.py` (Realtest der B.7-Deaktivierung) und
  `setup/probe_sector_mapping.py` (Abdeckung der `finnhubIndustry`-Rohwerte). Beide laufen
  gegen eine **Kopie** der DB, `data/tracking.db` bleibt unberührt.
- ⚠️ **KORREKTUR 2026-08-12:** hier stand, `claude_commands.md` und `project_ideas.md`
  seien **gelöscht** worden. Das ist falsch — beide Dateien liegen unverändert unter
  `random/` und sind getrackt (`git ls-files random/`). Richtig ist nur, dass ihre
  *Inhalte* überholt sind: `claude_commands.md` beschreibt einen Docker-Cron-Container,
  den es nie gab, und `project_ideas.md` trägt die alte Cron-Tabelle mit
  `midday`/`evaluate`/`position_check` sowie eine überholte Sprint-Aufteilung. Die drei
  noch offenen Ideen daraus stehen in Abschnitt 2b.
- ⚠️ **`random/` ist Korbinians interner Ordner und wird nicht angefasst** — auch nicht
  aufgeräumt, umbenannt oder als tot bewertet. Die falsche Löschungs-Behauptung oben ist
  genau daraus entstanden, dass eine frühere Session ihn als Altlast behandelt hat.

### P2.3 — Alle 20 Tasks umgesetzt

| Task | Inhalt | Stand |
|---|---|---|
| **18** | Fünf Weekly-Aggregate in `src/db.py`: `load_revision_effectiveness`, `load_revision_verdict_stats`, `load_guardrail_reject_stats`, `load_skipped_ticker_stats`, `load_sector_mapping_coverage` | ✅ `0fec73b` (2026-08-04) |
| **19** | Weekly-Mail um die vier B.9-Blöcke erweitern; `hold_days_recommended` als Spalte in der Tagesmail (B.11) | ✅ `ae0a79c` (2026-08-04) |
| **20** | Doku-Abschluss + Aufräumliste aus P2.6 | ✅ (2026-08-04) |

Zu Task 18 gegenüber dem Plantext ergänzt: ein Test für `load_skipped_ticker_stats`.
Der Plan implementierte die Funktion ohne Test, obwohl gerade ihr Join zwischen dem
Ereignis-Log (`skipped_tickers`) und dem kumulativen `ticker_status` fehleranfällig ist.

**Danach ausstehend:** ein Gesamt-Review über die kompletten Plan-2-Commits, dann die
Live-Verifikation (s. P2.4). Beides prüft Code, der **auf `main` liegt, aber noch nie
gelaufen ist** — die Verifikation bleibt damit ein echtes Gate vor der ersten Ausführung.

### P2.4 — ⏳ Live-Verifikation teilweise erfolgt (Korbinian)

⚠️ **KORREKTUR 2026-08-08.** Dieser Abschnitt behauptete, der Plan-2-Code sei „kein
einziges Mal ausgeführt" worden. Das stimmt nicht mehr. Über die GitHub-API belegt:

| Zeitpunkt (UTC) | Run-Type | Ergebnis |
|---|---|---|
| 2026-08-04 15:16 | `pre_market` | `success` |
| 2026-08-04 16:21 | `trade_proposals` | `success` |
| 2026-08-04 21:44 | `close` | `success` |

Alle drei auf Commit `92773c8`, also **mit vollständigem Plan-2-Code**, ausgelöst per
`schedule`. Danach wurde `analyze.yml` deaktiviert (manuell), um das Fehler-Gate zu
schliessen, bis die Ursache geklärt war.

**Aber: die Läufe erzeugten keine Predictions.** In der `db-latest`-DB gibt es für den
2026-08-04 zwar `cost_tracking`-Zeilen für `pre_market` und `trade_proposals`, aber
**keine einzige `predictions`-Zeile** — die jüngsten stammen vom 2026-07-13. Technisch
erfolgreich (Exit 0, Mail raus, DB hochgeladen), inhaltlich ohne Ergebnis.

#### ✅ Ursache geklärt (2026-08-08) — die CI-Datenbank hatte keine Historie

Kein stiller Ausfall. Der Grund stand wörtlich in `skipped_tickers` der CI-DB, in allen
drei Läufen identisch: **`insufficient bars: 19 < 20`** für exakt 18 Ticker
(`MIN_BARS_RSI = 20`).

`db-latest` wurde **nie mit `historical_loader` bestückt**. Es sammelte nur die Bars ein,
die die Läufe selbst schrieben — herunterladen, laufen, hochladen. Die Leere erhielt sich
selbst:

| Gruppe | Bars in `db-latest` (2026-08-04) |
|---|---|
| 18 MVP-Aktien | **19** (2026-05-21 → 08-04) |
| PG, HD | 217 |
| Rohstoffe / Krypto | 23 / 26 |
| Sektor-ETFs | 5 |

Die Kette daraus:

1. Phase 1: 18 von 20 raus. Übrig blieben PG und HD — die zwei defensivsten Werte, und
   nur, weil sie zufällig Historie hatten.
2. Sektor-Momentum: „0 mit beiden Signalen". Nicht wegen der ETFs (deren Signal kommt
   **live vom Provider**, nicht aus der DB), sondern weil `db_momentum` mangels Tickern
   überall NULL blieb.
3. Phase 4: von 9 Kandidaten hatten **8 `direction='none'`** (bewusste Enthaltung),
   CL=F fiel an R/R 1.47 < 1.5. Also 0 persistiert.
4. `trade_proposals` fand folgerichtig „0 offene pre_market-Signale"; `close` wertete die
   3 Altlasten aus.

Die Pipeline hat sich also **korrekt verhalten**. Gegen eine Datenbank ohne Historie ist
„grün und leer" das richtige Ergebnis. Was fehlte, war die Sichtbarkeit — dazu die vier
Fixes in **P2.9**.

⚠️ **Achtung bei `db-latest`:** das Release-Asset stammt vom 2026-08-04 und enthält den
Stand *dieser* Läufe — 46 Ticker, aber sehr ungleich befüllt (HD 217 Bars, CARZ 5). Die
lokale `data/tracking.db` auf Korbinians Rechner ist ein anderer Stand. Für Indikatoren
ist die lokale die brauchbarere (SMA200 braucht 200 Bars). Wer neu aufsetzt, nimmt sie mit
oder lässt den Bootstrap laufen, statt sich auf `db-latest` zu verlassen.
Praktisch heisst das: Die Verifikation unten ist weiterhin eine **Abnahme vor der ersten
Ausführung**, kein Nachziehen hinter einem laufenden System. Ein Befund hier kostet nichts
ausser Nacharbeit.

✅ **Die 12 überfälligen Predictions sind erledigt** (Stand 2026-08-08): alle 12 — 3 vom
2026-07-13 (eine mit `run_type='midday'`) und 9 vom 2026-07-29 — stehen auf
`status='closed_stale_pre_rollout'`. In `data/tracking.db` sind **null** Zeilen offen. Der
Evaluator kann hier nichts mehr gegen Wochen alte Kurse auswerten.

✅ **Schritt 1 ist erledigt** (2026-08-04): `init_schema()` gegen eine Kopie der
produktiven DB ergänzt `superseded_by` und `revision_verdict` sauber. Reines SQLite,
keine API-Aufrufe, kein Mailversand.

Die Schritte 2 und 3 bewusst **nicht** von Subagenten ausführen — sie kosten echtes Geld
und verschicken echte Post:

```bash
# 1. Migration gegen eine KOPIE der Produktions-DB, nie gegen das Original
cp data/tracking.db /tmp/migrationstest.db
python -c "from src import db; c = db.connect('/tmp/migrationstest.db'); db.init_schema(c); \
print([r['name'] for r in c.execute('PRAGMA table_info(predictions)')])"
# erwartet: superseded_by und revision_verdict in der Liste

# 2. Docker-Smoke-Test gegen eine Wegwerf-DB
docker compose run --rm -v /tmp/dbtest:/app/data trading-harry --run-type trade_proposals

# 3. Echter Lauf, nachdem ein pre_market-Lauf Signale erzeugt hat
python main.py --run-type pre_market
python main.py --run-type trade_proposals
```

Zu prüfen: 16:10-Mail kommt an; je Ticker genau **eine** offene Zeile in `predictions`;
`guardrail_rejects` enthält Zeilen aus **beiden** Läufen; `cost_tracking` weist den
16:10-Lauf mit **deutlich unter 1 EUR** aus. Liegt er höher, stimmt E1 nicht und der
Prompt oder die Eingabemenge muss nachgesehen werden.

⚠️ **`enforced` trennt nicht die Läufe** (korrigiert 2026-08-06). Die Spalte heißt
„dieser Check hat das Signal tatsächlich verworfen" — so liest sie auch
`signal_checks.blocks()` — und **beide Läufe schreiben beide Werte**: `pre_market`
schreibt `enforced=1`, wenn der klassische `GuardrailsChecker` greift (`ranking.py`
verwirft den Kandidaten dort wirklich), und `trade_proposals` schreibt `enforced=0` für
die immer weichen Checks (Klumpenrisiko, Opening-Gap, einseitiges Momentum). Wer die
Läufe auseinanderhalten will, muss nach `run_type` gruppieren — Weekly-Block 3 tut das
seit dem Fix.

### P2.5 — Befunde aus der Umsetzung

Drei Defekte stammten aus dem Plantext selbst und wären ohne die Umsetzung nicht aufgefallen:

1. **VIX-Filter wurde bei steigender Volatilität lockerer.** Code und mitgelieferter Test
   im Plan widersprachen sich. Die naheliegende Auflösung (partitionierte Schwellen) hätte
   ein mittelmässiges Short-Signal bei VIX 28 verworfen und bei VIX 40 durchgelassen.
   Entschieden: **kumulativ** — ab 25 nur noch `confidence='high'` (beide Richtungen, ohne
   Obergrenze), zusätzlich ab 35 keine neuen Longs. Monotonie nachgemessen (`926a059`).
2. **Der B.5-Tausch erzeugte einen Selbst-Check.** Nach dem Tausch sah Phase 4a auch die
   Predictions, die Phase 4 Sekunden zuvor geschrieben hatte (Alter 0) → ein zusätzlicher
   Claude-Call je neuem Signal und derselbe Ticker doppelt in der Mail. Nebenbefund: der
   Tausch war für seinen erklärten Zweck **gar nicht nötig** — die Phase-3-Analysen lagen
   auch vorher schon vor. Entschieden: Tausch bleibt, `date < today` schliesst
   Predictions desselben Tages aus (`822f29e`).
3. **`save_prediction()` schrieb NULL statt Schema-Default.** Fehlte `learnable` im Dict,
   wurde explizit NULL geschrieben — die Zeile wäre für **jedes** `WHERE learnable = 1`
   unsichtbar gewesen. Vorbestehender Bug, bei der Umsetzung von Task 11 gefunden und
   behoben.

**Zwei Vorfälle mit Aussenwirkung:**

- **Echte Mails aus einem Testlauf.** Während Task 14 gingen mehrfach echte Test-Mails an
  `EMAIL_TO`, weil bestehende Tests `run_trade_proposals()` durchlaufen liessen und der
  neue Sendepfad noch nicht gemockt war. Inhaltlich harmlos, aber unangekündigt.
- **Ein Unit-Test baute eine echte Capital.com-Session auf**, nachdem `run_close()` in
  Task 17 echten Sammelcode bekam. Der Fehler wurde intern geschluckt, der Test blieb grün.

**Konsequenz (`70f883b`, `58782e4`):** `tests/conftest.py` sperrt jetzt per Autouse-Fixture
**jeden** ausgehenden `requests.get`/`requests.post` ausserhalb von `tests/live/`; die
Fehlermeldung nennt die tatsächlich aufgerufene Adresse. Der Produktivcode hat keinen
weiteren HTTP-Einstieg (kein `Session`, kein `urllib`, kein `httpx` — geprüft).
**Merke:** Die erste Fassung setzte `src.email_sender.requests.post` und war dadurch
unbeabsichtigt ein globaler POST-Block mit irreführender Meldung — `import requests`
liefert überall dasselbe Modulobjekt.

### P2.6 — Aufräumliste für Task 20

Alles unkritisch, alles bewusst vertagt. Vollständige Liste im SDD-Ledger
(`.superpowers/sdd/2026-07-30-sprint3b-plan2-pipeline-umbau/progress.md`):

| Was | Wo |
|---|---|
| Echte Umlaute statt `ue/ae/oe` (Projektkonvention) | `src/revalidation.py:9`, `tests/unit/test_db.py:1062` — beide aus dem Plantext übernommen |
| Ungenutzter Logger | `src/revalidation.py` |
| Parameter `cluster_counts` schattiert den gleichnamigen Import | `src/ranking.py:_run_checks` — aktuell folgenlos |
| `except CostCapExceeded` in Phase 1d unerreichbar | `collect_sector_momentum()` bekommt keinen `cost_tracker`; bewusste Vorwärtskompatibilität |
| `get_ticker_sector()` wird je Ticker bis zu 4× abgefragt | `src/ranking.py` — bei MVP-Grösse vernachlässigbar |
| `_h(reason)[:200]` escaped vor dem Kürzen | `src/email_sender.py` — kann eine HTML-Entity mitten durchschneiden |
| Docstrings mit 3 statt 1–2 Sätzen, unvollständiger Satz | `epic_to_ticker`, `revalidate_one`, `_forced_candidates` |
| Docstring nennt Phase 1d nicht als Ausnahme | `_mock_all_other_phases` in `tests/unit/test_main.py` |
| Plan-Erratum: „8 Tests" statt 7 | Plan-Datei, Task 7 Step 4 |
| **`cost_summary` in `run_weekly()` ist hart auf Nullen verdrahtet** — die Weekly-Mail meldet dauerhaft „Run-Kosten Woche: 0.0 EUR", obwohl `cost_tracking` echte Werte führt (3,3143 EUR für den 29.07.). Es gibt bislang nur `save_cost_tracking()`, keine Lesefunktion. Fix wäre ein `db.load_cost_summary(conn, since)` mit `SUM`/`AVG` plus eine Zeile in `run_weekly()`. *(gefunden 2026-08-04 bei Task 19, bewusst nicht dort behoben — Task 19 sollte den Plan unverändert umsetzen)* | `main.py:run_weekly()`, `src/email_sender.py:render_weekly_html()` |

### P2.8 — Review von Task 20: acht behobene Defekte (2026-08-05/06)

Das Gesamt-Review über die Plan-2-Commits (`a57f9dc`…`92773c8`) lief über drei getrennte
Reviewer. Alle Befunde wurden vor der Umsetzung am Code nachgeprüft; jeder Fix hat einen
eigenen Commit und einen Test, der vorher rot war.

| # | Defekt | Wirkung, wenn er live gegangen wäre | Fix |
|---|---|---|---|
| C1 | Ablösung lief über **zwei** Commits (`save_prediction` + `record_revision`) | Bricht der Lauf dazwischen ab, stehen dauerhaft **zwei offene Zeilen** für dieselbe Trade-Idee. Der Evaluator schließt beide, jede Kennzahl zählt doppelt — genau die Doppelzählung, die E3 verhindern soll. Kein UNIQUE (Befund 8), kein Reparaturlauf | `db.supersede_prediction()` legt INSERT und UPDATE in **eine** Transaktion — so heißt die Funktion auch in Spec 5.2 |
| C2 | Übersprungene Ticker bekamen einen **erfundenen** 16:10-Einstieg | `collect()` liefert sie gar nicht zurück, `snapshot.get("price") or pred["entry_price"]` fiel still auf den 15:00-Kurs zurück — und löste die Morgenzeile trotzdem ab. P&L und jeder 3D-Vergleich erben den Fehler lautlos | Ohne frischen Kurs bleibt die Zeile offen und gilt als „nicht geprüft" (Spec 7.1); der Claude-Call entfällt |
| C3 | Nur `RevalidationError` gefangen | `call_claude` reicht nach zwei Retries die **rohe** Exception durch; ein 429/529 kommt als `APIStatusError`. Der entkam bis aus `run_trade_proposals` heraus: `save_cost_tracking()` lief nie, ausgegebenes Geld blieb unverbucht. Bei ~27 Calls je Lauf kein Randfall | Breit gefangen, `CostCapExceeded` vorher durchgereicht. Zusätzlich überlebt das Teilergebnis jetzt einen Deckel-Abbruch |
| — | **Eingefrorene Tagesbar** | `_ensure_today_bar()` stieg bei vorhandener Zeile aus. Der 15:00-Lauf schrieb damit eine Pre-Market-Quote fest: der 16:10-Lauf verglich „frische" Kurse **gegen sich selbst** (Opening-Gap konnte nie feuern) und der echte Tagesschluss wurde **nie** geschrieben — die Zeile blieb dauerhaft falsch und verfälschte jeden daraus gerechneten Indikator | Laufender Tag wird überschrieben, abgeschlossene Tage nie. Grundlage: Read-only-Sonde, s. unten. ⚠️ **Am 2026-08-07 überholt** — der Preismodell-Umbau (P3) hat `_ensure_today_bar()` ganz entfernt; `price_history` hat jetzt nur noch einen Schreiber, damit kann das Einfrieren strukturell nicht mehr entstehen |
| — | Weekly-Block 3 ließ `run_type` fallen | Harte Ablehnungen des **Morgenlaufs** lasen sich als Ablehnungen des 16:10-Laufs | Gruppierung nach `(run_type, rule, enforced)` |
| — | Weekly-Block 2 jointe auf `p.id` | Bestätigte Zeilen sind `superseded` und bekommen **nie** ein Outcome — das hängt am Nachfolger. „bestätigt: Ø 0 EUR / gedreht: −18 EUR" hätte Bestätigen als wertlos ausgewiesen | Join über `COALESCE(superseded_by, id)`; `avg_pl` bleibt NULL statt 0, dazu `n_evaluated` |
| — | `trade_proposals`-Cron nur für die US-Sommerzeit | Von November bis März lief der Lauf um 09:10 ET — **20 min vor** der Eröffnung. Lautlos: kein Fehler, nur vier Monate Unsinnsdaten pro Jahr | Zweiter Slot (15:10 UTC); der Workflow verwirft den zur aktuellen US-Zeitzone falschen |
| — | Netzsperre der Tests nur auf `requests.get/post` | finnhub nutzt `requests.Session`, das Anthropic-SDK **httpx** — der teuerste Pfad war der einzige ungeschützte. Mit Key in der `.env` machte jeder Test, der `call_claude` zu mocken vergaß, echte Calls | Sperre auf Transport-Ebene (`HTTPAdapter.send`, `httpx.Client.send`); Anthropic-Client zusätzlich stillgelegt, weil das SDK die Exception sonst zu „Connection error." verschluckt |

**Read-only-Sonde gegen Capital.com (2026-08-05, 22:05 UTC), Grundlage des Bar-Fixes:**
- Für einen noch nicht eröffneten Tag gibt es **gar keine** Bar — 2026-08-06 fehlte
  vollständig. Eine Pre-Open-Quote als eigener Sonderfall existiert also nicht.
- Die Bar des laufenden Tages **bewegt sich weiter**: AAPLs Volumen lief zwischen zwei
  Abrufen von 63024 auf 63028 — zwei Stunden **nach** dem regulären US-Schluss. Die
  DAY-Bar deckt damit auch die erweiterten Handelszeiten ab und existiert um 15:00 Berlin
  (09:00 ET, Pre-Market) längst.

**Nicht bestätigt:** die Annahme, die `enforced`-Polarität sei vertauscht. Beide
Schreibstellen sagen die Wahrheit (s. Korrekturbox in P2.4); falsch war nur ihre
Beschreibung.

### P2.7 — Bekannte, bewusst akzeptierte Lücke

`trend_summary` und das verschachtelte `sector_rotation` aus `analyze_trends()` werden
**nirgends persistiert**. `db.load_trend_context()` kann sie deshalb nicht rekonstruieren;
der 16:10-Portfolio-Check bekommt einen etwas ärmeren Trend-Kontext als der Morgenlauf.
Die Rotationsfelder aus `market_context` werden am Aufrufort ergänzt (`41a724a`), der Rest
bleibt offen. Im Docstring von `load_trend_context()` dokumentiert.

---

### P2.9 — Bootstrap, Sichtbarkeit und zwei Historien-Defekte (2026-08-08)

Aus der Ursachenanalyse zu den leeren 04.08.-Läufen (s. P2.4) sind sechs Commits
entstanden. Zwei davon beheben echte Datenfehler, vier machen Stilles sichtbar.

| Commit | Was |
|---|---|
| `8003e2e` | **CI-Bootstrap.** `src/universe.py` wird die eine Quelle, welche Ticker das System anfasst; `historical_loader --universe` und `--report-coverage`; `.github/workflows/bootstrap-db.yml` (nur `workflow_dispatch`, teilt die concurrency-Gruppe mit `analyze.yml`). `run_final_close` nutzt dieselbe Funktion, ein Test hält beide zusammen. |
| `a5b5548` | **D1** — übersprungene Ticker begründen sich im Log. `_skip()` vereint Log- und DB-Zeile, `db.skip_reason_counts()` bündelt die Gründe eines Laufs. |
| `ab6b5d2` | **D2** — Enthaltungen (`direction='none'`) sind zählbar, bleiben aber bewusst **kein** Reject: in `guardrail_rejects` gebucht, verzerrten sie die Weekly-Auswertung. |
| `ccdf5a6` | **D3** — ein Lauf ohne persistierte Prediction warnt von sich aus, unabhängig von der Ursache. |
| `9394e8f` | **Guard** — mehr als die halbe Tickerliste ohne Historie bricht den Lauf ab, bevor er Geld kostet. Am CLI-Einstieg, nicht in `run_pipeline`: das ist eine Betriebs-Vorbedingung, keine Pipeline-Logik. Ausgenommen `final_close` (schreibt die Historie selbst), `close`, `weekly`. |
| `fe756bd` | **Lücken-Defekt.** `_fill_price_gaps` fragte allein `MAX(date)`. Nach einem Ausfall schreibt `final_close` um 00:15 die Bar von gestern — der Zeiger ist wieder aktuell und das Loch dahinter war **für immer unsichtbar**. Geprüft wird jetzt der gesamte jüngste Abschnitt (`GAP_SCAN_BARS = 200`). |
| `0b025a8` | **Loader schrieb den laufenden Tag.** `--universe` gab den vier Krypto-Tickern am Samstag eine Bar von genau diesem Tag — Krypto handelt durchgehend, die UTC-Bar schliesst erst um 00:00 UTC. Dieselbe Vermischung provisorisch/final, die der Preismodell-Umbau beseitigt hat, nur über den Loader-Pfad. |

⚠️ **Feiertage sind keine Lücken.** Innenliegende Lücken zählen bewusst erst ab **zwei
aufeinanderfolgenden** Handelstagen. Ohne Börsenkalender sind einzelne fehlende Wochentage
US-Feiertage — in `data/tracking.db` sind **35 der 1000 AAPL-Bars** genau das. Wer sie als
Lücke behandelt, lädt bei jedem Lauf für jeden Ticker ins Leere nach. Die hintere Kante
behält die alte Schwelle.

⚠️ **Das ETF-Momentum hängt nicht an der DB.** `_fetch_etf_momentum` holt die Bars **live
vom Provider** (`sector_momentum.py:55`). „0 mit beiden Signalen" kam am 04.08. vom
DB-Bein. Dessen Grenze ist strukturell: bei 20 Tickern erreichen nur **2 von 21**
Sub-Sektoren `SECTOR_DB_MOMENTUM_MIN_TICKERS = 3` (Retail: AMZN/WMT/HD, Financials Rest:
BRK-B/V/MA). Ein Smoke-Test kann den harten Sektor-Guardrail also nur dort auslösen —
das löst erst 3F, nicht mehr Historie.

---

### P2.10 — ✅ Erster vollständiger `pre_market`-Lauf (2026-08-09)

Freigegeben von Korbinian, ausgeführt **lokal gegen eine Wegwerf-Kopie** von
`data/tracking.db` (46 Ticker, 46.200 Bars, 0 offene Predictions). Echte API-Calls, echte
Mail. Protokoll: `pre_market-2026-08-09.log` (gitignored).

⚠️ **Es war ein Sonntag.** Phase 1 arbeitete auf Freitagsbars, der Opening-Gap-Check hatte
keinen Live-Kurs. Der Lauf belegt die **Mechanik**, nicht die inhaltliche Qualität.

| Phase | Ergebnis |
|---|---|
| Phase 0 | 7 Trends, 0,13 EUR |
| Phase 1 | **20 ok, 0 skipped** (+ 7 Rohstoffe/Krypto) — gegen `2 ok, 18 skipped` am 04.08. |
| Phase 1c | 1 Pflicht-Kandidat aus offener Capital.com-Position: XOM |
| Phase 1d | **2 von 21** Sub-Sektoren mit beiden Signalen |
| Phase 2 | 20 bewertet, 0 ausgeschlossen |
| Phase 3 | **alle 20** in Tiefenanalyse, kumuliert 2,53 EUR |
| Phase 3b | 7 Analysen, kumuliert 3,13 EUR |
| Phase 4 | **4 long, 3 short, 3 commodity/crypto** aus 27 Analysen, davon **16 enthalten** |
| Phase 5 | Mail `delivered` (per `GET /emails/{id}` geprüft, nicht nur `2xx`) |

**Kosten: 3,1318 EUR** (101.648 Input-, 62.976 Output-Tokens) — deckt sich mit den
3,3143 EUR vom 2026-07-29.

**Die D2-Zeile trägt.** `4 long, 3 short, 3 commodity/crypto persisted (aus 27 Analysen,
davon 16 enthalten)` — 27 − 16 − 1 Guardrail-Drop (ETH-USD, R/R 1,41) = 10. Die Rechnung
geht ohne DB-Zugriff auf. Genau das fehlte am 04.08.

Nur **zwei WARNINGs** im ganzen Lauf, beide `unknown sector value from provider: 'Media'`
(GOOGL/META, dokumentiert als bewusst ungemappt). D1 und D3 schwiegen korrekt.

**Zwei Beobachtungen ohne Handlungsbedarf:**

1. „Offene Position" heisst an zwei Stellen Verschiedenes: Phase 1c meint Positionen bei
   **Capital.com**, Phase 4a offene **Predictions in der DB**. Beide Zahlen waren korrekt
   (1 bzw. 0), im Log liest es sich wie ein Widerspruch. Formulierungssache.
2. `web_search_calls = 0` bei 31 Anthropic-Requests, obwohl Phase 0 als „Claude +
   Web-Search" dokumentiert ist. Betrifft nur die Kostenaufschlüsselung. Nicht verfolgt.

⚠️ Die 10 Predictions liegen **nur in der Wegwerf-Kopie**. `data/tracking.db` ist
unberührt (12 Predictions, 0 offen). Für eine `trade_proposals`-Verifikation müsste die
Kopie übernommen werden — bei Signalen aus einem Sonntagslauf nicht empfohlen.

---

### P2.11 — ✅ Doku-Durchgang über alle `.md` (2026-08-09)

Der in `[[feedback_doc_maintenance_order]]` aufgeschobene Schlussdurchgang. Bearbeitet:

| Datei | Was |
|---|---|
| `README.md` | vollständig neu — yfinance, „Max 3 Handelstage", 159 Tests, Fear&Greed als Rohstoff, 500 Ticker und die Sprint-Historie waren alle falsch |
| `docs/WORKFLOW.md` | vollständig neu — dokumentierte noch `midday`, `evaluate`, `position_check` und das alte Doppel-Cron-Modell |
| `docs/ARCHITECTURE.md` | `universe.py` (10d), erweiterte Invarianten, Testzahlen, Änderungen 08-08/09 |
| `docs/SPECIFICATION.md` | als **historisch eingefroren**. Der frühere Vermerk „Task 20 zieht dieses Dokument nach" ist bewusst verworfen — der Inhalt würde ARCHITECTURE und PROJECT_STATUS duplizieren |
| `…/2026-05-19-shares-future-mvp-design.md` | Banner geschärft, Status-Zeile korrigiert |
| `CLAUDE.md` | am 2026-08-08 nachgezogen |

**Nicht angefasst** (bewusst, Regel 9): `docs/superpowers/plans/*` und
`.superpowers/sdd/*` — historische Artefakte mit `⚠️ HISTORISCH`-Banner.

**Zwei Befunde aus dem Durchgang:**

1. ✅ **B-06 ist erledigt.** `guardrails.py`, `evaluator.py` und `portfolio_check.py` lesen
   inzwischen alle `config.MAX_HOLD_DAYS`. Die Doku sagt durchgehend **5**; der alte
   Vorbehalt „Doku soll den hardcodierten Wert 3 spiegeln" ist gegenstandslos.
2. ⚠️ **Das Repo heisst `KorbinianBronold/Trading_Harry`, das Produkt `Shares_Future`.**
   Ältere Dokumente nannten als Repo `Shares_Future` — alle `gh --repo`-Befehle darin
   liefen ins Leere. In WORKFLOW.md korrigiert und erklärt.

**Aus dem maschinellen Gegencheck (Doku gegen Code, 2026-08-09)** — vier Befunde, die
beim blossen Lesen nicht aufgefallen wären:

3. ⚠️ **`price_history` hat DREI Schreiber, nicht einen.** CLAUDE.md und ARCHITECTURE.md
   behaupteten „genau EINEN Schreiber: `final_close`" und nannten `historical_loader` als
   „einzigen weiteren". `data_collector._fill_price_gaps()` schreibt aber ebenfalls
   (Sicherheitsnetz nach Ausfällen). Einheitlich ist die **Regel** — nie der laufende Tag —,
   nicht die Zahl der Schreibstellen. In beiden Dokumenten korrigiert.
4. ⚠️ **A/B-Testing für Prompts existiert nicht.** CLAUDE.md führte „Prompts versioniert
   mit A/B-Testing" als Designentscheidung. Tatsächlich ist die Version nur der Dateiname
   und im Modul-Import fest verdrahtet; ein Wechsel ist eine Code-Änderung. Gehört zu 3D.
   Nebenbefund: `prompts/portfolio_check_v1.txt` ist verwaist (genutzt wird v2), und
   Prompts werden auf Modulebene gelesen — eine Änderung wirkt erst nach Neustart.
5. ⚠️ **Zwei tote Tabellen:** `fundamentals` und `prompt_versions` werden von
   `init_schema()` angelegt und haben **null** Lese- oder Schreibzugriffe im gesamten
   Code. Dieselbe Klasse Altlast wie `MAX_DEEP_ANALYSIS` und `BATCH_SIZE_QUICK`.
6. ⚠️ **Drei Module fehlten in ARCHITECTURE.md:** `src/utils.py`, `src/providers/base.py`
   und `src/providers/finnhub_provider.py` — ergänzt als 11b–11d.

**Geprüft und in Ordnung:** alle sechs Crons stimmen mit `analyze.yml` überein · alle
dokumentierten CLI-Flags existieren · alle Dateiverweise lösen auf · Konstanten
(`MAX_HOLD_DAYS`, ATR, Cost-Cap, VIX 25/35 kumulativ, `TOP_N`) decken sich mit `config.py` ·
Docker `ENTRYPOINT`/`CMD` entsprechen der Beschreibung · kein yfinance- oder
`midday`/`evaluate`/`position_check`-Rest ausserhalb von Historien-Kontext.

---

### P2.12 — ✅ Live-Verifikation von Plan 2 abgeschlossen (2026-08-14)

**Der letzte offene Prüfstein von Plan 2 ist eingelöst.** `trade_proposals` hatte bis
hierhin nie eine einzige Zeile zu bearbeiten (s. P3.5); die Ablöse-Mechanik aus E3/E5 war
damit ungetestet. Am 2026-08-14 (Freitag) liefen `pre_market`, `trade_proposals` und
`close` **zu den echten Cron-Zeiten aus `analyze.yml`** (15:00 / 16:10 / 22:30 Berlin),
lokal gegen eine **Wegwerf-Kopie** von `data/tracking.db`, mit echten API-Calls und echtem
Mailversand. `analyze.yml` blieb dabei `disabled_manually`, `data/tracking.db` unberührt.

Erstmals mit vollständigem DEBUG-Logging: Root-Logger auf DEBUG plus `ANTHROPIC_LOG=debug`.
⚠️ Das SDK loggt auf DEBUG **nur Requests, keine Response-Bodies** — für die Verifikation
der Mail-Inhalte musste `GET /emails/{id}` bei Resend herhalten. Wer künftig Antworten
braucht, muss sie selbst protokollieren.

**Das Ergebnis: E3 und E5 verhalten sich exakt wie spezifiziert.** 8 Signale aus dem
Morgenlauf, alle 8 um 16:10 geprüft:

| Ticker | `revision_verdict` | Ausgang |
|---|---|---|
| NVDA long, XRP-USD short | `unveraendert` | abgelöst (`superseded_by` 36 / 40) |
| ABBV long, GC=F short, UNH short | `geschwaecht` | abgelöst (37 / 39 / 38) |
| AVGO long | `gedreht` | bleibt **offen**, kein Nachfolger |
| BRK-B short, MSFT long | `verworfen` | bleibt **offen**, kein Nachfolger |

- **E3 trägt:** 5 Ablösungen, je genau eine `superseded`-Zeile plus eine neue offene. Keine
  Dublette, keine verwaiste Zeile.
- **E5 trägt:** die drei gedrehten/verworfenen bleiben offen und werden regulär ausgewertet;
  eine Gegenposition entsteht nicht.
- **„Genau EINE offene Prediction je Trade-Idee":** 8 Ideen → 8 offene Zeilen. Geht auf.

`close` schloss die Kette: Evaluator fand 15 offene (vom 13.08.), schloss 5 per `sl_hit`.

| Lauf | Kosten | Anmerkung |
|---|---|---|
| `pre_market` | **3,9217 EUR** | 20 Tiefenanalysen + 7 Rohstoffe/Krypto; 4 long / 2 short / 2 c-c aus 27 Analysen, 18 Enthaltungen |
| `trade_proposals` | **0,6268 EUR** | 8 Signale geprüft — am oberen Rand der E1-Erwartung (0,5–0,7), E1 bestätigt |
| `close` | 0 | kein Claude-Call |

Der Anstieg bei `pre_market` gegen die 3,13 EUR vom 2026-08-09 ist **kein** Kostenwachstum
der Analyse: Phase 4a prüfte diesmal 15 offene Positionen (0,282 EUR) gegen null am 09.08.,
und der `cost_tracker`-Fix aus `f8f6684` weist Cache-Treffer seither korrekt aus — die
alten Zahlen waren zu niedrig. Beide Läufe sind nur eingeschränkt vergleichbar.

Alle drei Mails **zugestellt** (`last_event="delivered"`, per `GET /emails/{id}` geprüft,
nicht am Statuscode festgemacht) — inklusive der Weekly-Mail vom 2026-08-14 10:55
(`KW33 — Wochen-Summary`). ⚠️ `weekly` bleibt trotzdem als **nicht verifiziert** geführt:
zugestellt heisst nicht inhaltlich geprüft, und `cost_summary` ist dort weiterhin hart auf
Nullen verdrahtet (P2.6).

#### Vier Befunde aus der Verifikation

**1. Doppelte offene Predictions — bereinigt, Ursache offen.**
`pre_market` lief am 13.08. zweimal (08:54:03 und 08:55:59). Ergebnis: vier Trade-Ideen
mit je **zwei** offenen Zeilen (AAPL short 19/24, GOOGL short 17/25, META short 18/23,
XOM long 13/22). `predictions` hat **kein UNIQUE** — nur Indizes auf `status` und `date`.
Der Evaluator hätte beide geschlossen, jede Kennzahl doppelt gezählt; Phase 4a prüfte und
bezahlte sie täglich doppelt (15 statt 11 Claude-Calls).
**Bereinigt am 2026-08-15** in `data/tracking.db`: die vier älteren Zeilen (13, 17, 18, 19)
auf `status='closed_stale_pre_rollout'`, `closed_date='2026-08-15'`, `learnable=0` — dasselbe
Muster wie die 12 Juli-Altlasten. Sicherung unter `data/tracking.db.bak-20260815-120803`.
Danach 11 offene Zeilen, kein `(ticker, direction)`-Paar mehr doppelt.
✅ **Ursache geschlossen am 2026-08-15** — s. P2.13.

**2. `advance_decline_ratio` ist strukturell NULL — und hat gar keinen Abnehmer.**
Der Wert ist seit dem 13.08. in jedem Lauf NULL; nur der 29.07. trägt einen (2,5).
**Root Cause: keine belastbare Datenquelle, kein Code-Fehler.** `prompts/market_context_v1.txt`
weist ausdrücklich an: *„Nicht ermittelbar -> null. Niemals schätzen oder erfinden"* und
*„Ein null-Wert ist ausdrücklich besser als eine geratene Zahl"*. Claude findet per Websuche
keine belegbare A/D-Ratio und antwortet weisungsgemäss mit `null`. Das Parsing in
`market_context.py:104` arbeitet korrekt.
⚠️ **Wichtige Präzisierung gegenüber B.3:** die Marktbreite ist **kein Guardrail und war
nie einer**. Einziger Konsument im gesamten Code ist `email_sender.py:415`
(`_section_market_warnings`) — B.3 weist ihr selbst nur „Kontext / Warnung" zu, der
Docstring dort sagt es ebenfalls. Es läuft also nicht ein Check leer, sondern eine
Kontextzeile bleibt leer. Vor Sprint 3C ist zu entscheiden, ob die A/D-Ratio eine echte
Quelle bekommt (Provider statt Websuche) oder ersatzlos entfällt.

**3. VIX-Widerspruch — die Guardrail rechnet mit dem richtigen Wert.**
`market_context.py:96-98` bevorzugt den Capital.com-Wert und fällt nur ersatzweise auf
Claudes Zahl zurück; `signal_checks.check_vix` liest genau dieses `vix_level`. Am 14.08.
war das **17,6** (Quelle im Log: `VIX=17.6 (capital.com)`). Claudes „~14,55" steht
ausschliesslich im Freitext `macro_summary`.
**Betroffen ist nicht die Schwelle, sondern der Kontext:** `macro_summary` wird von
**keiner** Mail gerendert (die Tagesmail ruft `_section_market_warnings` gar nicht auf,
s. Befund unten), erreicht aber über `main.py:705` den Re-Validierungs-Prompt des
16:10-Laufs — Claude liest dort also eine VIX-Zahl, die 3 Punkte neben der liegt, mit der
gefiltert wird.
⚠️ **Offene Frage für 3C/3D:** die Capital.com-Notierung lag ~3 Punkte über dem
Spot-VIX — das Muster eines VIX-**Future**-CFDs (Contango), nicht des Spot-Index.
`VIX_HIGH_CONFIDENCE_ONLY = 25` und `VIX_NO_NEW_LONGS = 35` sind erkennbar für den
Spot-Index gedacht. Bei systematischem Aufschlag greifen beide Filter **früher als
beabsichtigt**. Zu klären, bevor die Schwellen scharf gestellt oder nachjustiert werden.

**Nebenbefund derselben Prüfung:** `_section_market_warnings` hängt nur in
`render_trade_proposals_html` (`email_sender.py:441`), **nicht** in `render_daily_html`.
Die Morgenmail zeigt damit weder VIX noch Marktbreite — in der 16:10-Mail steht
„Marktlage · VIX 17.7", in der 15:00-Mail nichts. Verifiziert an beiden versendeten Mails.
Nicht zwingend falsch (E4: um 15:00 wird ohnehin nicht durchgesetzt), aber undokumentiert.

**4. Fünf leere `market_context`-Spalten — nur dokumentiert, bewusst nicht gefixt.**
`sp500_change_pct`, `oil_price`, `gold_price`, `btc_price` und `fear_greed_value` sind in
**jeder** Zeile NULL. `fetch_market_context()` liefert diese Keys nicht, `save_market_context()`
führt sie aber in der Spaltenliste (`db.py:822`). Für die ersten vier gilt: **wirklich tot** —
kein Konsument im Code, dieselbe Altlast-Klasse wie `MAX_DEEP_ANALYSIS` und die Tabellen
`fundamentals` / `prompt_versions` (P2.11, Befund 5).

`fear_greed_value` liegt anders und braucht eine eigene Klärung: **es gibt den Wert dreimal.**

| # | Weg | Zustand |
|---|---|---|
| 1 | `commodities_crypto.fetch_fear_greed()` → `main.py:403` → `extra_context` | **funktioniert** — lieferte am 14.08. `{value: 29, label: "Fear"}` und ging als `EXTRA CONTEXT` in alle 7 Prompts (im Request-Log belegt) |
| 2 | `market_context.fear_greed_value` (Spalte) | **tot** — nie geschrieben |
| 3 | `prompts/commodities_crypto_v1.txt:45` → `analysis["extra"]["fear_greed_value"]` | **das ist, was die Mail zeigt** (`email_sender.py:197`) |

✅ **Verifiziert, nicht vermutet:** die versendete Mail vom 14.08. zeigt in der F&G-Spalte
**29** für GC=F und XRP-USD — Claude spiegelt den injizierten Wert exakt. Der angezeigte
Wert ist also valide. **Aber nur zufällig verlässlich:** der Prompt gibt für
`fear_greed_value` keinerlei Feldregel vor (anders als `market_context_v1.txt`, das Raten
ausdrücklich verbietet). Nichts verpflichtet Claude, den Kontextwert durchzureichen — eine
abweichende oder `null`-Antwort landete unbemerkt in der Mail, obwohl der echte Wert
danebenliegt. **Klärungspunkt für 3C/3D:** die Drei-Wege-Redundanz auflösen — Weg 1 direkt
in die Mail rendern, Weg 3 aus dem Prompt streichen, Weg 2 mit den vier toten Spalten
zusammen entfernen.

**Weiterhin offen:** `weekly` (nie inhaltlich verifiziert), der einmalige `bootstrap-db`-Lauf
— davor der Check, ob der `db-latest`-Upload trägt — und danach die Reaktivierung von
`analyze.yml`.

---

### P2.13 — ✅ Die Invariante steht jetzt in der Datenbank (2026-08-15)

Befund 1 aus P2.12 hatte nur die Symptome beseitigt. Seit `ux_predictions_one_open_per_idea`
erzwingt SQLite selbst, was die Doku seit Plan 2 behauptet: **je Trade-Idee genau EINE
offene Prediction.**

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_predictions_one_open_per_idea
    ON predictions(date, ticker, direction) WHERE status = 'open';
```

**Warum partiell.** Ein UNIQUE über die drei Spalten allein hätte E3 gebrochen: die
abgelöste `pre_market`-Zeile und ihre `trade_proposals`-Nachfolgerin teilen sich alle drei
Werte und stehen dauerhaft nebeneinander. Nur die **offenen** dürfen eindeutig sein.

⚠️ **Der Index erzwingt eine Reihenfolge, die nicht umgestellt werden darf.**
`supersede_prediction()` fügte bisher **erst ein** und setzte die alte Zeile danach auf
`superseded`. SQLite prüft einen Unique-Index **je Statement, nicht beim Commit** — dieser
INSERT scheitert also, solange die alte Zeile noch offen ist. Die Funktion arbeitet jetzt in
drei Schritten (alte Zeile auf `superseded` → INSERT → `superseded_by` nachtragen), alle
weiterhin in **einer** Transaktion. Die Atomizitäts-Begründung aus C1 (P2.8) bleibt damit
unangetastet.

**Bestandsdatenbanken.** `CREATE UNIQUE INDEX` scheitert an vorhandenen Duplikaten — ohne
Vorbereinigung stürbe `init_schema()` bei **jedem** Lauf. Deshalb räumt
`_enforce_one_open_prediction_per_idea()` vorher auf: die jeweils **ältere** Zeile geht auf
`closed_stale_pre_rollout` mit `learnable = 0`, mit einer WARNING, die die IDs nennt.
Verifiziert gegen eine echte Kopie mit den vier 13.08.-Duplikaten — dieselben IDs
(13, 17, 18, 19), Index angelegt, zweiter Aufruf idempotent.

**Wenn die Regel greift, stirbt der Lauf nicht.** `save_prediction()` fängt den
`IntegrityError`, loggt die Trade-Idee als WARNING und gibt `None` zurück. Ein Abbruch wäre
teurer als der Nutzen: der Fall entsteht praktisch nur durch einen Doppellauf, und dann ist
Phase 3 längst bezahlt — die Exception risse das Ranking mitten in einer je Zeile
committenden Schleife auseinander. `ranking.py:221` wertet den Rückgabewert ohnehin nicht aus.

**707 Tests grün, Coverage 90,94 %** (`--cov=src --cov=main`). Die Umstellung war
testgetrieben: die zwei neuen Tests waren erst rot, und der Index legte beim ersten
Gesamtlauf **13 bestehende Tests** um — darunter der komplette E3-Pfad. Genau diese
Regression war der Beweis, dass die Reihenfolge in `supersede_prediction()` das eigentliche
Risiko der Änderung war.

Drei Tests bauten in ihrem **Setup** den nun verbotenen Zustand (zwei offene Zeilen je
Idee) und wurden auf den Pfad gezogen, den die Produktion tatsächlich geht.
⚠️ Dabei fiel auf: **der `superseded_by`-Zweig von `record_revision()` hatte keinen
Produktions-Aufrufer mehr** — alle drei Stellen in `main.py` (534, 538, 553) rufen ohne ihn
auf, seit C1 die Ablösung nach `supersede_prediction()` verlegt hat. Sein einziger
legitimer Anwendungsfall war seit dem Index zusätzlich strukturell unmöglich: er setzt
voraus, dass alte und neue Zeile gleichzeitig offen sind.

✅ **Entfernt am 2026-08-15.** `record_revision()` nimmt nur noch `(conn, pred_id, verdict)`
und lässt die Zeile immer offen; Ablösen kann ausschliesslich `supersede_prediction()`.
Damit ist der zweite, **nicht-atomare** Weg zur Ablösung weg — genau der Defekt, den C1
geschlossen hat, blieb als Parameter bis hierhin aufrufbar. Die **Spalte** `superseded_by`
bleibt selbstverständlich: sie trägt `supersede_prediction()` und den
`COALESCE(superseded_by, id)`-Join von Weekly-Block 2.
Ein Test pinnt die Verengung (`test_record_revision_cannot_supersede_a_row`) — er war vor
dem Eingriff rot und verhindert, dass der Parameter unbemerkt zurückkehrt.

**Angewandt auf `data/tracking.db`** am 2026-08-15: 11 offene Zeilen, keine Duplikate,
Index vorhanden. Sicherung vor dem Eingriff: `data/tracking.db.bak-20260815-120803`.

---

## Preismodell-Umbau — drei Entscheidungs-Snapshots + finale Tages-OHLC (P3) ✅ CODE FERTIG

**Spec:** `docs/superpowers/specs/2026-08-06-preismodell-snapshots-design.md`
**Plan:** `docs/superpowers/plans/2026-08-06-preismodell-snapshots.md`
**Umgesetzt:** 2026-08-06/07, 11 Tasks, 13 Commits.
**Stand unmittelbar nach diesem Umbau (2026-08-07):** 570 Tests grün, 7 skipped,
Coverage 93,29 %. *(Aktuell sind es 608 — s. Kopfzeile.)*

### P3.1 — Worum es ging

Das Preismodell trennt jetzt zwei Dinge, die vorher dieselbe Quelle hatten und
deshalb ständig verwechselt wurden:

| | Was | Quelle |
|---|---|---|
| **Indikator-Historie** | RSI, ATR, SMA, MACD — braucht abgeschlossene Tage | `price_history`, **nur finale Bars, ein Schreiber** |
| **Entscheidungs-Snapshot** | Der Kurs, zu dem eine Aussage getroffen wurde | `predictions.price_premarket` / `price_open` / `price_1610` |

Genau diese Vermischung war der Frozen-Bar-Bug aus P2.8: der 15:00-Lauf schrieb eine
Pre-Market-Quote als „Tagesbar" fest, und alles Spätere las sie als Tatsache.

### P3.2 — Die Änderungen

| SHA | Was | Warum |
|---|---|---|
| `413ed68` | `to` nie in der Zukunft an Capital.com | Undokumentierter HTTP 400, fünf Minuten genügen. `final_close` läuft um Mitternacht genau dort hinein und wäre strukturell gescheitert |
| `e912f48` | Intraday-Abruf mit `resolution`-Parameter | Der Code kannte nur `DAY`. Eigener Parser, weil `_parse_prices` `snapshotTime` auf `[:10]` schneidet — Minutenbars kollabierten sonst auf einen Index |
| `c1fdcc5` | Drei Entscheidungs-Snapshots in `predictions` | Additiv, `entry_price` unangetastet, damit 3D beide Zeitpunkte vergleichen kann |
| `0ee4f76` | `src/signal_window.py` | Signal-Zeitpunkt und Verdichtung, reine Funktionen ohne Netz |
| `5372732` | `run_final_close` | Holt die finalen Tagesbars für Ticker, Commodities/Crypto **und** Sub-Sektor-ETFs |
| `71e2db2` | Auswertung ab dem Signal-Zeitpunkt | Fenster beginnt am Signal, nicht am Tagesbeginn |
| `efea2bd` | Predictions bleiben offen, solange ihr Fenster läuft | s. P3.4, Befund 1 |
| `11a3337` | `price_history` hat nur noch einen Schreiber | `_ensure_today_bar()` und der ETF-Schreiber in `sector_momentum` entfallen |
| `c327487` | Echten Eröffnungskurs und Vorbörsen-Markierung befüllen | Lücke, die eine Selbstprüfung des Plans gefunden hat: beide Werte wurden nur gelesen, nie erzeugt |
| `75aef35` | Kein erfundener Eröffnungskurs für Krypto/Rohstoffe (E6) | s. P3.4, Befund 4 |
| `b659ef4` | Sektor-Momentum ohne die Bar des laufenden Tages | Der Join lief auf exakte Datumsgleichheit mit heute — hätte lautlos D9 abgeschaltet |
| `f291096` | Veraltete Bars fälschen das Sektor-Momentum nicht mehr | s. P3.4, Befund 3 |
| `587a7ee` | `final_close`-Cron, Concurrency-Lock, Ausfallwarnung | Der Lock existierte in **keinem** Workflow |

### P3.3 — Warum der Cron täglich läuft und DST hier keine Rolle spielt

`final_close` hängt an der **Bar-Grenze**, nicht an einer Börsensitzung.
`instrument.openingHours` meldet `zone: UTC` und schliesst auf 00:00 UTC — Job und
Datenquelle liegen am selben Anker, eine Zeitumstellung verschiebt beide nicht
gegeneinander. **Anders als `trade_proposals`, der an der US-Sitzung hängt und deshalb
zwei Slots braucht.** Diese Frage ist damit beantwortet und soll nicht erneut aufkommen.

**Täglich statt Mo–Fr:** freitags schliesst der Handel um 21:00 UTC, die Bar wird erst
danach final — erst der **Samstagslauf** holt Freitags Schlusskurs. Ohne den Samstag
fehlte jede Woche ein Handelstag in der Historie.

### P3.4 — Vier Befunde, die erst die Umsetzung zutage gefördert hat

Das ist der eigentliche Ertrag des Umbaus — alle vier waren vorher unsichtbar.

1. **`MAX_HOLD_DAYS = 5` war nie in Kraft.** `_walk_forward_hit` lieferte `timeout`,
   sobald in den *verfügbaren* Bars kein Treffer lag, ohne zu prüfen, ob das Fenster
   überhaupt abgelaufen war. **Jede Prediction schloss beim ersten Auswertungslauf**,
   am Tag nach ihrer Entstehung. Vorbestehend, behoben in `efea2bd` (neuer Zustand
   `pending` plus Notbremse `MAX_OPEN_CALENDAR_DAYS = 14` gegen Zombie-Zeilen).
2. **`_ensure_today_bar` war als Test-Fixture tragend.** 13 Tests bezogen ihre
   Kurshistorie aus dem Seiteneffekt dieser Funktion statt aus eigenem Setup. Der
   Rückbau legte das offen; sie seeden jetzt selbst, was den Vertrag von
   `_process_ticker` ehrlicher prüft.
3. **Der Riegel gegen veraltete Bars.** Die Umstellung auf „die letzten zwei Bars"
   behob den stillen Totalausfall, öffnete aber eine zweite Lücke: ein stillgelegter
   Ticker trug seine letzte je vorhandene Tagesbewegung dauerhaft weiter. Gemessen
   sprang das Sektor-Momentum dadurch von `None` auf **18,0**, und `ticker_count`
   erreichte fälschlich das Minimum — aus „kein Signal" wurde „starkes Signal", auf
   das D9 gehandelt hätte. Behoben in `f291096` mit **zwei** Riegeln: Bar-Alter und
   Abstand der beiden Bars (Letzterer fängt den Ticker mit frischem letztem Bar und
   monatealtem Vorgänger).
4. **Krypto und Rohstoffe bekamen einen erfundenen Eröffnungskurs.** Die Annahme, der
   `MINUTE`-Abruf liefere für 24/7-Instrumente keine Bar, war falsch — sie handeln
   durchgehend. Der Wert war kein Eröffnungskurs, sondern der Kurs zu einem
   bedeutungslosen Zeitpunkt (BTC-USD 64060,9, GC=F 4196,98). Die Tests waren dabei
   **grün** — aufgefallen ist es nur bei einer Live-Prüfung gegen die echte API.
   Behoben in `75aef35`, jetzt mit eigenem Test.

### P3.5 — ✅ `final_close` erstmals ausgeführt und verifiziert (2026-08-08)

`analyze.yml` steht unverändert auf `disabled_manually`; ausgeführt wurde **lokal gegen
Wegwerf-Kopien** von `data/tracking.db`, mit echten (lesenden) Capital.com-Calls, ohne
Claude-Call und ohne Mailversand.

**`final_close`:** 46 finale Bars für den Handelstag 2026-08-07 geschrieben (`upsert`,
ersetzt also eine provisorische durch die finale Bar). Läuft sauber durch.

**Der Evaluator auf finalen Bars** — der eigentliche Kern des Umbaus — mit drei
synthetischen offenen Predictions vom 2026-08-04 auf AAPL:

| Aufbau | Erwartung | Ergebnis |
|---|---|---|
| TP 313,00 | Treffer (Hoch 08-05: 313,19) | `closed_tp` @ 313,00 ✅ |
| SL 306,00 | Treffer (Tief 08-05: 305,05) | `closed_sl` @ 306,00 ✅ |
| TP 400 / SL 200 | kein Treffer, Fenster läuft | bleibt `open` ✅ |

Der dritte Fall bestätigt die Invariante aus `efea2bd`: eine Prediction bleibt offen,
solange ihr Fenster läuft. `closed_date` ist bei beiden geschlossenen der **Handelstag**
2026-08-07, nicht das Laufdatum — E7 greift.

**`close`** lief gegen dieselbe DB mit `Phase 1 done: 20 ok, 0 skipped` (gegen `2 ok,
18 skipped` am 04.08.).

✅ **`pre_market` ist am 2026-08-09 gelaufen** — Ergebnisse in **P2.10**.
✅ **Docker-Smoke-Test erledigt** (2026-08-09): Image baut, ohne Argument gibt es die Hilfe
aus statt eine Pipeline zu starten, `final_close` und `close` laufen im Container gegen
einen Wegwerf-Mount, `data/tracking.db` bleibt unberührt.

✅ **`trade_proposals` ist am 2026-08-14 gelaufen und verifiziert** — s. **P2.12**. Der
Absatz, der hier stand („beide nie ausgeführt"), ist damit überholt. Bestätigt hat sich
dabei genau die Erwartung, die ihn begründete: der Lauf re-validiert die Signale
**desselben Tages**, weshalb er einen vorausgehenden `pre_market`-Lauf braucht — ein
Testlauf am Vormittag fand deshalb „0 offene pre_market-Signale" und liess die Mechanik
erneut unberührt.

⏳ **Offen bleibt `weekly`** — zwar zugestellt, aber nie inhaltlich verifiziert; die fünf
Aggregate aus Task 18 und die vier B.9-Blöcke sind ungeprüft, und `cost_summary` ist hart
auf Nullen verdrahtet (P2.6).

---

## Sprint 3B-M — Mail-Provider-Wechsel (Zwischensprint) ✅ ABGESCHLOSSEN

> **Eingeschoben am 2026-07-29, abgeschlossen am 2026-07-30.** Lief vor 3B/Plan 2;
> Nummerierung von 3C–3F blieb unberührt. Grund für die Vorziehung: ohne
> funktionierenden Versand ist jeder Pipeline-Lauf blind — die Analyse landet zwar in
> der DB (B-10), aber niemand sieht sie.
>
> **Endstand:** Versand läuft über **Resend**, Absenderdomain `tradingharry.com`
> verifiziert, Zustellung live bestätigt. Einziger offener Punkt ist das Kündigen des
> alten Anbieterkontos (Schritt 11) — rein administrativ, ohne Code-Bezug.

### M.1 — Anlass

Der vorherige Mail-Anbieter war nicht *kaputt*, sondern **kontingentlos**. Der
Schlüssel war gültig und trug die Sende-Berechtigung, aber das Konto meldete
`total: 0, remain: 0, is_hard_limit: true` — die Testphase war ohne Anschlusstarif
ausgelaufen. Jeder Versand scheiterte mit HTTP 401 und `"Maximum credits exceeded"`.

**Wichtig für die Fehlersuche in Zukunft:** Leeres Kontingent und unbrauchbarer
Schlüssel kamen dort unter demselben 401 zurück. Deshalb sind die Live-Checks seit
`d79c896` getrennt — `test_api_connectivity` prüft lesend den Schlüssel, ein zweiter
Check die Absenderdomain, und `test_email_delivery` den tatsächlichen Versand.

### M.2 — Provider-Auswahl: **Resend** *(entschieden und umgesetzt 2026-07-30)*

Kriterien, an denen die Wahl hängt:

| Kriterium | Warum es hier zählt |
|---|---|
| **Dauerhaft kostenloses Kontingent** | Bedarf ist klein und planbar: 2 Mails/Tag heute, nach 3B ~3/Tag plus Wochenmail — also < 100/Monat. Genau daran ist der Vorgänger gescheitert (Testphase ohne Anschlusstarif). |
| **Absender-Verifikation ohne eigene Domain** | Aktuell ist `EMAIL_FROM == EMAIL_TO` (private Gmail-Adresse). Anbieter, die eine verifizierte Domain erzwingen, bedeuten Zusatzaufwand. |
| **Python-SDK oder simples REST** | `_send()` braucht genau einen POST. Ein SDK ist bequem, aber `urllib` reicht — weniger Abhängigkeiten. |
| **HTML-Mails** | Die Tagesmail ist HTML mit Tabellen. Reine Text-APIs scheiden aus. |
| **Aussagekräftige Fehler-Bodies** | Ein 401 ohne Klartext kostet Stunden — beim Vorgänger genau so passiert. |

Als Sonderfall zu prüfen: **SMTP direkt** (z.B. über den bestehenden Gmail-Account mit
App-Passwort). Kein Anbieterkonto, kein Kontingentproblem, `smtplib` ist in der
Standardbibliothek — dafür kein Zustellungs-Reporting und Gmail-eigene Sendelimits.

### M.2a — Gemessene Fakten zu Resend *(2026-07-30)*

| Befund | Wert |
|---|---|
| Freikontingent | **3 000 Mails/Monat, 100/Tag** (vom Konto bestätigt) |
| Verifizierte Domain | **`tradingharry.com`** (seit 2026-07-30, Region eu-west-1) → Absender `noreply@tradingharry.com`, beliebige Empfänger |
| Key-Rechte | **Full Access** — bewusst, damit die lesende Verbindungsprüfung über `GET /domains` möglich bleibt |
| Endpunkt | `POST https://api.resend.com/emails`, Felder `from`, `to[]`, `subject`, `html` |

**⚠️ Zwei Fallen, die Zeit gekostet hätten:**

1. **Cloudflare blockt `urllib`.** Resend liegt hinter Cloudflare, das Requests mit
   der `Python-urllib`-Signatur mit **HTTP 403 und `error code: 1010`** abweist — als
   Klartext, nicht als JSON. Das sieht wie ein Auth-Fehler aus und ist keiner. Mit
   `requests` geht alles durch. Deshalb nutzt `_send()` `requests`, kein Anbieter-SDK,
   und ein Test stellt sicher, dass `email_sender` kein `urllib` importiert.
2. **Full Access heisst Kontoverwaltung.** Der Key kann nicht nur senden, sondern auch
   API-Keys und Domains lesen und ändern. Wer `.env` oder das GitHub-Secret erlangt, hat
   Kontozugriff, nicht bloss Versandrechte. Bewusst akzeptiert für ein Ein-Personen-Repo;
   die Alternative wäre ein Sending-only-Key, dann entfällt aber die lesende Prüfung und
   Key-, Kontingent- und Absenderprobleme sind nicht mehr auseinanderzuhalten.

### M.6 — Ergebnis der Live-Verifikation *(2026-07-30)*

**Erster Anlauf war ein Fehlalarm.** Der Test meldete „Versand erfolgreich", weil er
nur den HTTP-Status prüfte. Resend nimmt mit `200` an und stellt **asynchron** zu; die
Mail scheiterte danach mit `last_event="failed"`, weil keine Absenderdomain verifiziert
war. Zwei Ursachen, beide auf Claudes Seite:

1. **Erfolgskriterium zu schwach.** `2xx` heißt „angenommen", nicht „zugestellt".
2. **`onboarding@resend.dev` als Absender empfohlen**, ohne es zu prüfen. Resends Doku
   ist eindeutig: *„You must add and verify at least one domain"* und *„Resend sends
   emails using a domain you own (not a shared or public domain)."* Der daraufhin
   gebaute Domain-Check hat diese falsche Annahme dann sogar per `assert` abgesegnet.

**Konsequenz im Code** (`034ef5c`): `_send()` gibt die `messageId` zurück, der
Versandtest pollt `GET /emails/{id}` und fällt bei `failed`/`bounced`/`complained`.
Die lesenden Checks sind getrennt in „Key gültig" und „Absenderdomain verifiziert" —
ein gültiger Schlüssel sagt nichts über Zustellbarkeit.

**Endstand nach Domain-Verifikation:** eigene Domain `tradingharry.com` registriert
(Nameserver bei Cloudflare) und in Resend verifiziert. Alle **sieben** Live-Checks grün:
Anthropic, Finnhub-Quote, Finnhub-Fundamentals, Capital.com, Resend-Key,
Resend-Absenderdomain und der echte Versand mit bestätigter Zustellung.

> **Diagnose-Notiz:** Die Verifikation hing zwei Stunden auf „pending", weil die
> DNS-Zone leer war — `dig` fand weder MX noch TXT noch DKIM, auch nicht auf den
> üblichen Tippfehler-Varianten. Ursache: die Records müssen dort gesetzt werden,
> wohin die **Nameserver** zeigen (hier Cloudflare), nicht beim Registrar. Bei
> Cloudflare hängt das Feld „Name" die Zone automatisch an — voller Hostname im
> Namensfeld erzeugt `send.example.com.example.com`. `dig` zeigt beides in Sekunden
> und unabhängig vom Prüfzyklus des Anbieters.

### M.3 — Vorgehen

Die Umsetzung war überschaubar, weil `src/email_sender.py:_send()` bereits **die einzige
providerspezifische Stelle** ist — jedes `send_*_email()` läuft dort durch. Der Austausch
blieb damit auf den Funktionsrumpf plus Konfiguration beschränkt; eine zusätzliche
Provider-Abstraktion wie bei `DataProvider` wäre für einen einmaligen Wechsel überzogen
gewesen. Bestätigt: kein einziger Aufrufer musste angepasst werden, Signatur und
`EmailSendError` sind unverändert.

Schrittfolge s. Abschnitt M.4 unten. Betroffene Dateien s. M.5.

### M.4 — Schritte

| # | Schritt | Wer |
|---|---|---|
| 1 | Provider auswählen (Kriterien M.2) | Korbinian |
| 2 | Konto anlegen, Absender verifizieren, Kontingent schriftlich festhalten | Korbinian |
| 3 | Key in `.env` **und** in die GitHub-Secrets legen | Korbinian |
| 4 | Live-Check erweitern: lesende Schlüsselprüfung des neuen Anbieters, Kontingent ausweisen | Claude |
| 5 | `requirements.txt` tauschen, `config.py`-Konstante umbenennen | Claude |
| 6 | `_send()` neu implementieren — Signatur und `EmailSendError` bleiben unverändert | Claude |
| 7 | Referenzen in `main.py` und den Workflows nachziehen | Claude |
| 8 | Unit-Tests auf den neuen Client umstellen, Integrationstest anpassen | Claude |
| 9 | Live verifizieren: lokal **und** über Actions (zwei unabhängige Schlüssel) | Claude |
| 10 | Doku aktualisieren (Liste M.5) | Claude |
| 11 | ⏳ **noch offen:** Secret des alten Anbieters aus GitHub entfernen, Konto kündigen | Korbinian |

**Reihenfolge ist bindend:** Schritt 6 erst nach 2, sonst lässt sich der neue Pfad nicht
verifizieren und man tauscht blind. Die Schritte 1–3 kann nur Korbinian ausführen.

### M.5 — Betroffene Dateien

**Code:**
- `src/email_sender.py` — `_send()` und der Import; einzige providerspezifische Stelle
- ✅ `config.py` — Konstante auf `RESEND_API_KEY` umgestellt
- ✅ `main.py` — 5 Referenzen auf `config.RESEND_API_KEY` umgestellt
- `requirements.txt` — Paket tauschen

**CI / Umgebung:**
- `.github/workflows/analyze.yml`
- `.github/workflows/test.yml`
- `.env.example`
- (dazu die lokale `.env` und die GitHub-Secrets selbst — keine Dateien im Repo)

**Tests:**
- `tests/unit/test_email_sender.py`
- `tests/live/test_api_connectivity.py`
- `tests/live/test_email_delivery.py`
- `tests/unit/test_live_email_guard.py`
- `tests/integration/test_full_pipeline.py`
- `tests/conftest.py`

**Doku, aktuell zu halten (Regel 14):**
- `CLAUDE.md` — Tech-Stack, Environment-Variablen, GitHub-Secrets
- `docs/ARCHITECTURE.md` — Modulbeschreibung `email_sender`
- `docs/superpowers/specs/PROJECT_STATUS.md` — dieser Abschnitt

**Doku, bekannt veraltet (Regel 14 — bewusst nicht anfassen):**
- `docs/WORKFLOW.md`, `docs/SPECIFICATION.md`,
  `docs/superpowers/specs/2026-05-19-shares-future-mvp-design.md`
- ✅ **Auf Wunsch (2026-07-30) vollständig mitgezogen:** `README.md`, `docs/WORKFLOW.md`,
  `docs/SPECIFICATION.md` und `mvp-design.md`. Ursprünglich hätten nur README und
  WORKFLOW eine Regel-14-Ausnahme bekommen, weil sie **Handlungsanweisungen** enthalten
  (WORKFLOW.md hatte ab Zeile 450 ein Runbook mit `curl` gegen die API des alten Anbieters) und
  damit aktiv in die Irre geführt hätten. Entschieden wurde, alle vier umzustellen.
- **Historische Plan-Dateien** (Regel 9): Inhalt unverändert, aber je ein Banner oben
  ergänzt, der auf den Wechsel hinweist. Sie dort umzuschreiben hätte behauptet, Sprint 1
  sei mit Resend gebaut worden — sachlich falsch.

**Historische Plandateien (Regel 9 — nicht bearbeiten):**
`2026-05-19-sprint1-plan1-foundation.md`, `2026-05-19-sprint1-plan3-deep-portfolio-email.md`,
`2026-05-21-sprint2-plan1-capital-provider-db-incremental.md`

---

## Sprint 3C — Ranking-Überarbeitung

### C.1 — Fehlende Indikator-Werte in Predictions

`atr_pct`, `rsi_at_entry` und `volume_ratio` werden in `ranking._to_prediction_row()` aktuell
**hart als `None`** gespeichert, obwohl sie in Phase 1 längst berechnet wurden. Die Werte müssen
aus dem Phase-1-Snapshot (`ticker_data`) korrekt übernommen werden.

Betrifft `src/ranking.py`. Voraussetzung dafür, dass 3D überhaupt auf diesen Dimensionen
lernen kann.

### C.2 — Kombinierter Ranking-Score

Das Ranking sortiert heute allein nach `probability_pct`. Künftig soll ein **kombinierter Score
aus allen verfügbaren Dimensionen** gebildet werden:

- Kursdaten
- Technische Indikatoren (RSI, ATR, MACD, Volume-Ratio)
- Fundamentals (P/E, Earnings-Beat, Analyst-Konsensus)
- Trend-Boost aus Phase 0
- Policy-Kontext aus Phase 3

**Entscheidung (2026-07-27):** Der kombinierte Score wird ein **neues, separates Feld**
(`ranking_score`, neue Spalte in `predictions`). Das bestehende `total_score` — die gewichtete
Summe der 8 Claude-Score-Dimensionen — **bleibt unverändert**. Gründe:

1. Die 8-Dimensionen-Gewichtung ist eine dokumentierte Architektur-Invariante
   ("nicht ändern ohne A/B-Test", s. Abschnitt 4)
2. Alte und neue Predictions bleiben vergleichbar
3. Das Learning Modul kann in 3D datenbasiert messen, welcher der beiden Scores besser predictet

**Gewichtung der neuen Dimensionen:** bewusst offen. Für 3C gilt: alle Werte greifbar machen und
in einen **nachvollziehbaren** (dokumentierten, reproduzierbaren) kombinierten Score einfließen
lassen. Die datenbasierte Optimierung der Gewichte ist Aufgabe von Sprint 3D.

### C.3 — R/R-Ratio-Ziel durchsetzen

`config.RR_RATIO_DEFAULT = 2.0` soll als klares Ziel durchgesetzt werden: Claude soll
standardmäßig 1:2 anpeilen. `config.RR_RATIO_MIN_HARD = 1.5` bleibt das harte Minimum in den
Guardrails (unverändert).

**Umsetzung:** Prompt-Änderung in `deep_analysis` + `commodities_crypto`. Laut Regel 10
(Abschnitt 5) bedeutet das **neue Prompt-Versionen `*_v2.txt`** plus Eintrag in der
`prompt_versions`-Tabelle — die v1-Dateien werden nicht überschrieben.

### C.4 — Technischer Pre-Filter vor Phase 2

Reiner Python-Filter (ATR, RSI, Volume, Market Cap) **ohne Claude-Kosten**, der die Ticker-Menge
vor dem Haiku-Batching reduziert.

**Ziel:** Vorbereitung der 500-Ticker-Skalierung (Sprint 3F) bei überschaubaren Kosten
(~90 EUR/Monat angestrebt).

⚠️ **Es gibt keinen Deckel auf Phase 3.** `MAX_DEEP_ANALYSIS = 80` wird nirgends im Code
gelesen (verifiziert 2026-07-30, erneut 2026-08-06) — `analyze_assets()` analysiert
**jeden** nicht-`exclude`ten Ticker, begrenzt nur durch `CostCapExceeded`. Der Pre-Filter
ist damit **nicht** eine Verbesserung der Auswahl innerhalb eines bestehenden Deckels,
sondern **die einzige Mengenbegrenzung überhaupt**, die C.4 einzuziehen hat. Er wirkt auf
Phase-2-Kosten, Phase-3-Kosten und Laufzeit zugleich.

Wer hier einen Deckel voraussetzt, unterschätzt die 500-Ticker-Kosten um ein Vielfaches —
siehe die Korrekturbox in F.1.

### C.5 — Analyse-Pipeline-Umbau: Spec und Pläne (2026-08-11)

Die Teilschritte C.1–C.4 sind in einer eigenen Spezifikation aufgegangen, die den Trichter,
die zwei Signale und das Ranking gemeinsam neu fasst:

- **Spec:** `docs/superpowers/specs/2026-08-11-analyse-pipeline-umbau-design.md`
- **Plan 1 (Fundament):** `docs/superpowers/plans/2026-08-11-analyse-pipeline-plan1-fundament.md`
- **Plan 2 (Trichter):** `docs/superpowers/plans/2026-08-13-analyse-pipeline-plan2-trichter.md`
  — 13 von 13 Tasks umgesetzt, s. **C.7**
- **Plan 3 (Analyse & Ranking):** in **3a** und **3b** geteilt (Spec § 20.1)
  - **Plan 3a (Batch-Tiefenanalyse):**
    `docs/superpowers/plans/2026-08-16-analyse-pipeline-plan3a-batch-tiefenanalyse.md`
    — 11 von 11 Tasks umgesetzt, aber **mit offenem Befund**: der Testlauf (Task 10)
    hat `MAX_TOKENS_DEEP` widerlegt, s. **C.9**. Code-vollständig, nicht produktionsreif.
  - **Plan 3b (Ranking):** offen, noch keine Plan-Datei. Bekommt sie erst, wenn der
    Token-Befund aus C.9 geschlossen ist — `rank_score` sollte laut Plan-3a-Abschluss
    gegen echte Beispieldaten entworfen werden, und die liefert erst ein Lauf ohne
    abgeschnittene Batches.

Die Spec ersetzt C.1 (fehlende Indikator-Werte — jetzt Teil des `predictions`-Umbaus),
C.2 (kombinierter Score — jetzt `rank_score` aus zwei zählbaren Signalen), C.3
(R/R-Ziel — in den Prompts v2) und C.4 (technischer Pre-Filter — jetzt Skip-Gate plus
harter Cutoff). `MAX_DEEP_ANALYSIS` wird dabei erstmals wirksam und wechselt von **80
(tot) auf 50**.

#### ✅ Read-only-Sonde gegen Capital.com (2026-08-12) — Sammelabruf von Kursen

Beantwortet die offene Frage aus Spec § 4.3.1. Skript: `setup/probe_epics_batch.py`
(`b771c65`), reine GET-Abfragen.

| Prüfung | Ergebnis |
|---|---|
| `GET /api/v1/markets/{epic}` (Einzelabruf, heutiger Pfad) | HTTP 200, AAPL bid 304,27 |
| `GET /api/v1/markets?epics=AAPL,MSFT,NVDA` | **HTTP 200**, Antwortfeld `marketDetails`, 3 von 3 Instrumenten |
| dieselbe Abfrage mit 10 Epics | HTTP 200, 10 von 10 |
| dieselbe Abfrage mit 20 Epics | HTTP 200, 20 von 20 |

**Der Sammelabruf funktioniert.** Für 500 Ticker bedeutet das **25 Calls statt ~500** —
das Laufzeitproblem des Kurs-Sweeps ist damit gelöst, ohne Phase 1 zu parallelisieren
(das bleibt 3F). Die Taktungsfrage aus Spec § 4.3.2 wird gegenstandslos: 25 Calls
streifen das 600/min-Limit nicht. Die 429-Notbremse aus § 4.3.3 bleibt als Sicherheitsnetz,
wird aber realistisch nie feuern.

⚠️ **20 ist eine bestätigte Untergrenze, kein gemessenes Maximum.** Die Sonde blieb bei 20
stehen, weil `SP500_MVP_TICKERS` genau 20 Einträge hat — sie hat die Liste erschöpft, nicht
eine Grenze gefunden. Wo Capital.com abschneidet, ist unbekannt. **Das ist gleichgültig:**
bei 25 Calls für das volle Universum bringt eine grössere Chunk-Grösse nichts mehr. Plan 2
setzt konservativ **20** und sucht die echte Grenze nicht.

Nebenbefund: `_map()` liess AAPL, MSFT und NVDA unverändert durch — `TICKER_MAP` enthält
nur **acht Ausnahmen** (Gold, Silber, Öl, die vier Krypto-Paare, BRK-B). US-Large-Caps sind
bei Capital.com 1:1 ihr Tickersymbol. Für die Chunk-Bildung heisst das: `_map()` gilt
uniform, kein Sonderweg nötig.

⏳ **Weiterhin offen, auch nach Task 4 (Stand 2026-08-15):** liefert `marketDetails` neben
`bid` auch `offer`? Die Sonde prüft es inzwischen (`probe_epics_batch.py:144-147`), aber ein
Ergebnis ist nirgends protokolliert, und `get_premarket_prices_batch()` liest ausschliesslich
`bid` — s. C.7, Befund 5. Ursprüngliche Notiz: falls ja, fällt
der Spread beim Sweep kostenlos mit ab und der 2b-Punkt „spread-bereinigtes R/R" wird
deutlich billiger. Kostet bei der Implementierung einen Blick in die Rohantwort.

### C.6 — Analyse-Pipeline-Umbau, Plan 1 (Fundament) ✅ abgeschlossen 2026-08-12

Spec: `docs/superpowers/specs/2026-08-11-analyse-pipeline-umbau-design.md`
Plan: `docs/superpowers/plans/2026-08-11-analyse-pipeline-plan1-fundament.md`

**Keine Verhaltensänderung.** 17 Indikatoren laufen mit und füllen 29 neue Spalten
in `technical_indicators`; das Technik-Signal ist berechenbar, steuert aber nichts.
647 Tests, 93,32 % Coverage (`pytest tests/ --cov=src --cov-fail-under=80 -q`), nach dem
abschliessenden Fix-Wave (s. Befund-Absätze unten).

| Task | Commit | Was landete |
|---|---|---|
| 2 | `f8f6684` | `cost_tracker`-Fix: `fresh_input` zog Cache-Treffer kein zweites Mal mehr ab |
| 3 | `d9136c6`, `0e91225` | Indikator-Mathematik aus `data_collector.py` nach `src/indicators.py` ausgelagert (reine Verschiebung, Testzahl unverändert) |
| 4 | `4445018` | Ladefenster `load_price_history_from_db()` 200 → 220 Bars |
| 5 | `0607d33`, `f81b164` | EMA50, MACD-Rohwerte, ADX, Parabolic SAR, Ichimoku |
| 6 | `c9760e4` | Stochastik, Williams %R, CCI(20), Momentum(12), TRIX(15,9), Bollinger-Rohwerte, ATR absolut, Donchian(20), OBV |
| 7 | `5e9a9ec` | 29 neue Spalten in `technical_indicators`, migrationsgeschützt; die vierzehn Funktionen in `_process_ticker` verdrahtet |
| 8 | `f65777a` | `src/technical_signal.py` — deterministisches Signal, noch kein Abnehmer |

⚠️ **Befund: `cost_tracker` rechnete zu billig.** `fresh_input` zog die Cache-Treffer
ein zweites Mal ab, obwohl `input_tokens` von der API bereits der ungecachte Rest ist.
**Alle vor 2026-08-12 gemessenen Laufkosten sind damit zu niedrig ausgewiesen** — grob
5 % beim Lauf vom 2026-08-09, wachsend mit der Cache-Trefferquote. Dieselbe
Fehlannahme steckte in `cache_hit_rate`, die dadurch über 1 gehen konnte.

⚠️ **Bewusst nicht geschlossen: `GAP_SCAN_BARS` bleibt bei 200, das Ladefenster ist jetzt
220.** Die Lückenprüfung in `data_collector.py` scannt weiterhin nur die letzten 200 Bars,
während `load_price_history_from_db()` seit Task 4 220 lädt. Eine Lücke, die genau auf
Bar 201–220 liegt, ist für die Lückenprüfung damit unsichtbar, verzerrt aber weiterhin
SMA200. Eine Anhebung von `GAP_SCAN_BARS` würde ändern, welche Ticker wegen Datenqualität
übersprungen werden — eine Verhaltensänderung, die Plan 1 explizit nicht anfassen darf
(s. Kommentar an der Konstanten, `src/data_collector.py`). Liegt bei Plan 2.
✅ **Eingelöst in Plan 2, Task 3** (`da4cab1`): `GAP_SCAN_BARS = 220`. Es ist damit die eine
bewusste Verhaltensänderung vor Task 10 — s. C.7, Befund 1.

Nach Task 9 gilt: der Stand ist gefahrlos einspielbar, kein einziges Pipeline-Verhalten
hat sich geändert. Plan 2 (Trichter) setzt darauf auf.

⚠️ **Befund aus dem abschliessenden Ganz-Branch-Review (2026-08-12): Der Satz oben stimmte
nicht.** `_process_ticker` mischte die 29 neuen Werte in dasselbe `td`-Dict, das
unveraendert in vier Claude-Prompts `json.dumps`'t wird (`quick_filter.py`,
`deep_analysis.py`, `commodities_crypto.py`, und ueber `main.py`s `snapshots` in
`run_trade_proposals` auch `portfolio_check.py`) — rund 250 zusaetzliche Tokens je
Ticker, die Phase 2 bei der Ticker-Auswahl gesehen hat. **Gefixt:** die 29 Spalten werden
jetzt in einem separaten `extra_indicators`-Dict berechnet und erst unmittelbar vor
`_persist_indicators()` mit `td` zusammengefuehrt; die Rueckgabe von `_process_ticker()`
ist wieder byte-fuer-byte die Form von vor Plan 1 (verifiziert per Diff gegen den Stand vor
Task 5). Ein neuer Test (`test_process_ticker_return_shape_excludes_the_29_new_indicator_columns`)
pinnt die exakte Schluesselmenge.

Zweiter Befund derselben Review: `ichi_chikou` war **strukturell immer `None`** —
pandas_tas `ICS_26` traegt den heutigen Schlusskurs 26 Bars in die Zukunft projiziert und
ist fuer die juengsten 26 Zeilen deshalb grundsaetzlich NaN, bei 220 wie bei 500 Bars.
**Gefixt:** die Spalte speichert jetzt den Schlusskurs von vor 26 Bars — den Wert, gegen
den der Chikou-Span den heutigen Kurs tatsaechlich vergleicht. Der bisherige Test verglich
`None == None` und haette den Bug nie gefangen; er pinnt jetzt einen echten Zahlenwert.

Nach diesem Fix-Wave: 647 Tests (+1), 93,32 % Coverage — beide Befunde behoben, ohne dass
Plan 1 seine Nichtangriffsgarantie fuer das Pipeline-Verhalten verliert.

---

### C.7 — Analyse-Pipeline-Umbau, Plan 2 (Trichter) 🟢 13 von 13 Tasks

Spec: `docs/superpowers/specs/2026-08-11-analyse-pipeline-umbau-design.md` (§ 4.2–4.8, § 18)
Plan: `docs/superpowers/plans/2026-08-13-analyse-pipeline-plan2-trichter.md`

**Stand 2026-08-15**, gegen das echte Repo geprüft: alles auf `main`, Arbeitsbaum clean,
`origin/main` == lokal. **733 Tests grün, 14 skipped, 91,52 % Coverage** (`--cov=src`).
✅ **Alle 13 Tasks umgesetzt.** Nur der Abschluss-Review über `c978d70..HEAD` steht noch aus.

✅ **Der Trichter ist live verdrahtet und live gegen echte Daten gemessen** (Task 10,
s. Befund 9 unten). `quick_filter_batch()` ist aus `run_pipeline()` verschwunden.

| Task | Commit(s) | Was landete |
|---|---|---|
| 1 | `086d49a` | ADX-Grenzwerte gepinnt: `_adx_band()` nutzt geschlossene Intervalle (≤/≥), vier Randwert-Tests (20,0 → weak, 25,0 → strong). Derselbe Commit trägt die Plan-Datei selbst |
| 2 | `aa2f222` | `cache_hit_rate = cache_read / (cache_read + cache_creation)`. Die alte Formel teilte durch `input_tokens` — das ist bereits der ungecachte Rest, die Rate konnte über 1 gehen |
| 3 | `da4cab1` | `GAP_SCAN_BARS` 200 → 220, deckungsgleich mit dem Ladefenster aus Plan 1 Task 4 |
| 4 | `4801a63`, `a242d32` | `CapitalComProvider.get_premarket_prices_batch()`: `/markets?epics=` in 20er-Chunks statt eines GET je Ticker, dreistufige 429-Notbremse (getakteter Modus → Chunk-Skip → Abbruch nach fünf 429 in Folge). `base.py` bekommt die Methode als **nicht**-abstrakte Default-Implementierung, damit `FinnhubProvider` nicht ohne Nutzen bricht |
| 5 | `aea3656`, `03354bb` | `collect()` läuft in drei Pässen: `_gate_phase()` (deaktivierte Ticker, Rohstoffe/Krypto ausgenommen — § 6.1), `_sweep_phase()` (ein Batch-Call für alle Überlebenden), `_process_ticker()` (übernimmt den Sweep-Kurs statt selbst anzufragen). Fehlender Live-Kurs fällt auf den letzten finalen Close zurück (WARNING, kein Skip), `premarket_change_pct` bleibt dabei `None` statt einer erfundenen 0. **Rückgabe ist jetzt ein 3-Tupel** `(results, skipped, sidecar)` |
| 6 | `8351e31` | `technical_signal.compute()` liest `{**td, **extra_indicators}`; die vier Werte (`tech_direction`, `tech_agreement`, `tech_adx_band`, `tech_strength`) gehen in den **Sidecar**, nie in `td` |
| 7 | `f545901`, `7165bf5` | Phase 1 liest `fundamentals_cache` **nur noch** (0 Finnhub-Calls); das Nachladen sitzt in `fetch_missing_fundamentals()` (Phase 2b, gebaut, noch nicht verdrahtet). `earnings_next_date` wird als ISO-Datum gecacht statt als relative Tageszahl (§ 18.1d), `earnings_in_days` beim Lesen gerechnet, ein Termin in der Vergangenheit liefert `None`. `get_earnings_calendar()` ist aus dem Tageslauf verschwunden, `earnings_beat_pct` dort dauerhaft `None` |
| 8 | `b861b48`, `b902b23`, `9a7cd1f` | `src/broad_scan.py` + `prompts/broad_scan_v1.txt`: ein Sonnet-Call mit Websuche über alle Phase-1-Überlebenden, je Ticker `news_strength` (0–3) + `news_note`. Nutzlast wird aus **acht** Feldern gebaut statt `td` zu dumpen — die 19 unbeteiligten `td`-Felder bleiben draussen. Ein unparsebarer Scan degradiert den ganzen Batch auf `news_strength=0` statt zu werfen (§ 10) |
| 9 | *(Vorgänger-Commit)* | `config.TECH_MIN_FOR_DEEP = 2`; Tabelle `cutoff_log` (SCHEMA_SQL + Migrationsguard über `sqlite_master`, kein Zähler); `db.log_cutoff()` (`INSERT OR REPLACE`, ein Aufruf pro Lauf schreibt **alle** bewerteten Ticker); `broad_scan.cutoff_candidates()` |
| 10 | `efd341a` | `main.run_pipeline()`: `quick_filter_batch()` raus, `broad_scan_batch()` + `cutoff_candidates()` + `db.log_cutoff()` rein, `deep_analysis.adapt_cutoff_to_quick_filter()` als Interim-Adapter. `MAX_DEEP_ANALYSIS` 80 → 50, `BATCH_SIZE_QUICK` entfernt (tot). `main._apply_forced_candidates()` entfernt — die Pflicht-Kandidaten-Logik sitzt jetzt in `cutoff_candidates()` selbst. **Live gegen echte Daten verifiziert, s. Befund 9** |
| 11 | `1ebd247` | `FinnhubProvider._respect_rate_limit()`: Sliding-Window-Drosselung (60 Calls/60s), **instanzgebunden** (nicht modulweit wie im Plan-Pseudocode) — der Wochenlauf haelt eine Instanz über das ganze Universum, dieselbe Invariante wie „ein Session-Object pro Run" bei Capital.com. Vor jedem echten `get_fundamentals()`- und `get_earnings_calendar()`-Call, nach dem bestehenden `_client is None`-Kurzschluss (kein Call ohne API-Key → keine Drosselung nötig) |
| 12 | `695699b` | `main._update_weekly_fundamentals()`, verdrahtet in `run_weekly()` vor dem wöchentlichen Aggregat. Füllt `fundamentals_cache` **und** `earnings_next_date` fürs ganze Universum via `full_universe()`. **Bug-Fix gegenüber dem Plan-Pseudocode, s. Befund 11**: die Skip-Prüfung verlangt neben frischen Fundamentals zusätzlich ein gesetztes `earnings_next_date` — sonst hätte ein vom Tageslauf frisch gecachter Ticker (der nie Earnings mitbringt) nie eins bekommen |
| 13 | *(dieser Commit)* | Doku-Feinarbeit: `docs/ARCHITECTURE.md` — Modul 3 (`quick_filter.py`) als „ersetzt" markiert, Modul 3b (`broad_scan.py`) als „live" markiert, die grosse Pipeline-ASCII-Grafik (Phase 2/2a neu, Phase 1 auf Gate/Sweep/Process aktualisiert), `cutoff_log` in der Tabellenübersicht ergänzt, `FinnhubProvider`-Ratenbegrenzung dokumentiert, veraltete Test-Baseline (647/93,32 %) auf 733/91,52 % korrigiert. Modul-Docstrings (`src/broad_scan.py`, `src/db.py`) waren bereits in Tasks 9/10 erledigt |

Kein weiterer Task offen. Nächster Schritt: Abschluss-Review über `c978d70..HEAD`,
Testlauf mit Kostenmessung gegen Spec § 13.2, dann Plan 3 (Analyse & Ranking).

#### Befunde

**1. ⚠️ Task 3 ist die eine bewusste Ausnahme von „keine Verhaltensänderung bis Task 10".**
`GAP_SCAN_BARS` 200 → 220 **ändert die Ticker-Auswahl**: mehr erkannte Lücken heisst mehr
Nachladeversuche und damit potenziell mehr Skips. Genau deshalb durfte es nicht in Plan 1
(s. C.6, letzter ⚠️-Absatz) — dort war die Nichtangriffsgarantie bindend. Global Constraint 2
des Plans ist damit für Tasks 1–2 und 4–8 wahr, für Task 3 bewusst nicht.

**2. ✅ Kostendeckel-Sorge war unbegründet — live widerlegt, s. Befund 9.** Vor Task 10
stand hier die Vermutung, der Tausch Haiku-Quick-Filter → Sonnet-Scan-mit-Websuche würde
den MVP-Lauf über `MAX_COST_PER_RUN_EUR = 4.00` treiben, weil `MAX_DEEP_ANALYSIS = 50`
bei 20 Tickern nicht greift. **Das war eine Plausibilitätsvermutung, keine Messung** —
und falsch: der reale Lauf kostete 3,3551 EUR, **günstiger** als der Referenzlauf vom
14.08. (3,9217 EUR). Der Cutoff schliesst genug Ticker aus Phase 3 aus (5 von 20 in der
Messung), dass die Ersparnis dort den Mehrpreis von `broad_scan` übersteigt — die
Milchmädchenrechnung „50 greift nicht, also bleibt Phase 3 gleich teuer" berücksichtigte
nicht, dass der Cutoff *innerhalb* der 20 trotzdem aussortiert, nicht nur *über* 20 deckelt.

**Lehre:** `cost_tracking` hat keine Phasenaufschlüsselung (nur eine Zeile je Lauf) —
diese Einschränkung stand schon vor Task 9 fest. Die richtige Reaktion darauf war nicht,
aus Spec-Schätzungen eine Kostenwarnung zu extrapolieren, sondern **zu messen** (wie
Befund 9 es dann auch getan hat). Vor einer Warnung, die den Nutzer zu einer Entscheidung
zwingt, zuerst prüfen, ob die Messung selbst güns­tig genug ist, um sie einzuholen.

**3. Der Zwischen-Review nach Task 8 hat gegriffen** — zwei Befunde, beide gefixt:
- `MAX_TOKENS` war mit einer **falschen Begründung** gedeckelt: der Kommentar behauptete
  einen SDK-seitigen `ValueError`-Guard gegen grosse `max_tokens` bei Non-Streaming-Requests,
  den es im gepinnten `anthropic==0.42.0` nachweislich nicht gibt. Das reale Risiko ist der
  600-s-Default-Timeout. 16000 → 24000, dazu eine WARNING bei Nähe zur Grenze — sonst ist ein
  wegen Kappung auf `news_strength=0` degradierter Batch im Log nicht von einem echten ruhigen
  Nachrichtentag zu unterscheiden (`b902b23`). Im Prompt zugleich „3–6" → „3–5" Websuchen
  korrigiert, weil `WEB_SEARCH_TOOL` bei `max_uses=5` deckelt.
- `news_strength` wurde nur auf *numerisch* geprüft, nie auf den **Wertebereich**: 7 oder −2
  liefen durch. Werte ausserhalb 0–3 und Nachkommaanteile werden jetzt auf 0 gezogen (nicht
  geklemmt), `bool` gilt als Typfehler (`9a7cd1f`). Relevant genau für Task 9, das nach
  `news_strength` sortiert.

**4. Ein Review-Fund zu Task 7, der zwei Ablauf-Rhythmen betraf.**
`save_fundamentals_cache()` ist ein `INSERT OR REPLACE` der **ganzen** Zeile. Da
`get_fundamentals()` nie ein `earnings_next_date` liefert (das kommt vom Wochenjob, Task 12),
löschte ein Refresh wegen abgelaufener Fundamentals-TTL ein bereits gesetztes Datum.
Fix bewusst **lokal** in `fetch_missing_fundamentals()` statt als COALESCE-Semantik für alle
Aufrufer (`7165bf5`).

**6. Task 9 weicht an drei Stellen bewusst vom Plan-Pseudocode ab.** Alle drei sind
Bugs bzw. Inkonsistenzen im Plan selbst, gefunden beim Implementieren gegen den echten
Sidecar aus Task 5/6:
- **`tech_signals` als eigener Parameter entfällt.** Der Plan übergibt `tech_signals`
  getrennt von `ticker_datas` und liest `premarket_change_pct` aus `td` — beides gibt es
  seit der Sidecar-Invariante (C.6/C.7 Task 5–6) nicht mehr: beide Werte liegen im
  **Sidecar**, nicht in `td`. `cutoff_candidates()` nimmt deshalb denselben
  `sidecar: dict[str, dict]`-Parameter wie `broad_scan_batch()`.
- **`None` vs. `0.0` bei `premarket_change_pct`.** Der Plan sortiert mit
  `abs(pct) if pct else -1` — eine Wahrheitswertprüfung, die einen echten 0,0-%-Wert
  wie ein fehlendes `None` behandelt (`bool(0.0) is False`). Die Spec verlangt aber
  „`None` sortiert hinter **jedem gemessenen** Wert", explizit auch einer gemessenen 0.
  Implementiert mit `is not None`, mit eigenem Test (`test_cutoff_missing_premarket_
  change_pct_sorts_behind_measured_zero`).
- **`rank_position` aus `enumerate(all_evaluated)` in Original-Reihenfolge wäre sinnlos.**
  Der Plan sortiert nur die *qualifizierten* Kandidaten, vergibt `rank_position` aber über
  `all_evaluated` in **unsortierter** Ticker-Reihenfolge — der Rang hätte nichts mit der
  Cutoff-Sortierung zu tun. Implementiert: **alle** Ticker (qualifiziert oder nicht) laufen
  durch denselben Sortierschlüssel, `rank_position` ist der Index danach. Das erfüllt den
  eigentlichen Zweck der Tabelle direkt: den 51. neben dem 50. zu sehen.
- Zusätzlich: Pflicht-Kandidaten stehen über einen eigenen primären Sortierschlüssel
  (`0 if forced else 1`) vorn, wie in § 4.7 gefordert, aber im Pseudocode nicht umgesetzt.

**7. Spec § 19.1a bleibt unbeantwortet: liefert der Sammelabruf ein `offer`-Feld?**
Die Sonde prüft es (`setup/probe_epics_batch.py:144-147`), ein Ergebnis ist **nirgends
protokolliert**, und `get_premarket_prices_batch()` liest ausschliesslich `bid`. Das
spread-bereinigte R/R aus § 4.3.1 bleibt damit offen — der Lauf mit `--run-live` ist
nachzuholen, nicht zu vermuten.

**8. Doku-Befund: dieser Abschnitt fehlte, während acht Tasks committed und gepusht waren.**
Der Kopf dieses Dokuments und CLAUDE.md sagten beide „Einstieg ist jetzt Plan 2" — dasselbe
Muster, vor dem die zwei Korrekturkästen im Kopf warnen. Nachgezogen am 2026-08-15.
Nebenbefund im Plan selbst: Global Constraint 2 nennt „Task 9 (broad_scan)" als ersten
Konsumenten; `broad_scan` ist Task 8, und erster Konsument ist Task 10.

**9. ✅ Task 10 live gemessen (2026-08-15): 3,3551 EUR, kein `CostCapExceeded`, günstiger
als der alte Weg.** Lauf gegen eine Wegwerf-Kopie von `data/tracking.db`, echte
Capital.com-/Finnhub-/Anthropic-Calls, 20 MVP-Ticker, `run_type=pre_market`,
Mailversand unterdrückt (Testlauf-Konvention „kein Mailversand" aus der Plan-Einordnung).
Die reale Produktions-DB blieb unberührt.

| Phase | Kumulierte Kosten | Was passierte |
|---|---|---|
| 0 (Trends) | 0,140 EUR | 7 Trends |
| 0b (Marktkontext) + 2 (`broad_scan`) | 0,413 EUR | zusammen 0,273 EUR — `cost_tracking` trennt Phasen nicht, s. unten |
| 2a (Cutoff) | — | **15 von 20 Kandidaten ausgewählt**, `MAX_DEEP_ANALYSIS=50` greift nicht (erwartet) |
| Policy Monitor | 0,540 EUR | level=high, 6 Events |
| 3 (Tiefenanalyse) | 2,435 EUR | **15 Calls, nicht 20** — die 5 vom Cutoff ausgeschlossenen (META, BRK-B, JPM, JNJ, PG) wurden im Log als „skipped by quick_filter exclude" bestätigt, exakt deckungsgleich mit `cutoff_log.selected=0` |
| 3b (Rohstoffe/Krypto) | 3,166 EUR | 7 Assets, alle immer |
| 4a (Portfolio-Check) | **3,3551 EUR** | 11 offene Positionen, 10 Empfehlungen geschrieben |

**Die ursprüngliche Sorge war falsch, aber aus einem nachvollziehbaren Grund.** Sie nahm
an, Phase 3 bliebe bei 20 Einzelcalls, weil der Deckel (50) nicht greift — das stimmt für
den Deckel, aber der Cutoff selbst sortiert *unabhängig vom Deckel* nach Qualifikation
aus. 5 ausgeschlossene Ticker sparen ~5 × 0,126 EUR ≈ 0,63 EUR in Phase 3 — mehr, als
`broad_scan` zusätzlich kostet. Der Vergleich zum 14.08.-Lauf (3,9217 EUR, alle 20 tief
analysiert) ist nicht exakt bereinigt (andere Anzahl offener Positionen, andere
Cache-Trefferquote), zeigt aber dieselbe Grössenordnung: **kein Kostensprung, eher das
Gegenteil.**

⚠️ **Weiterhin unlösbar ohne Code-Änderung: die genaue Aufteilung Marktkontext/`broad_scan`
bleibt eine Schätzung** (0,273 EUR zusammen), weil `cost_tracking` nur eine Gesamtzeile je
Lauf führt, keine Phasenzeilen. Für 3D/3F relevant, falls die Phasenkosten je einzeln
gebraucht werden.

**Kein Zufallsbefund, kein Crash.** Cache-Trefferquote 47,48 %, `aborted_at_phase: None`,
keine ERROR-Zeilen im Log. Ein Nebenbefund ohne Regression: `META` hatte eine offene
Paper-Position (Prediction), wurde vom Cutoff aber nicht für Phase 3 ausgewählt — der
Portfolio-Check konnte dafür keine frische Analyse finden und übersprang sie mit einer
WARNING (`10 von 11` Empfehlungen). Das ist **kein neues Verhalten**: `analyze_asset()`
hat `exclude=True`-Ticker schon unter dem alten Quick-Filter übersprungen, exakt derselbe
Mechanismus — nur sichtbar geworden, weil der Cutoff diesmal genau diesen Fall traf.

⏳ **Nebenbefund, nicht untersucht, nicht Teil von Task 10:** die finale `cost_summary`
weist `web_search_calls: 0` und `web_search_eur: 0.0` aus, obwohl mehrere Phasen
(Trends, Policy Monitor, `broad_scan`, Tiefenanalysen) alle mit `WEB_SEARCH_TOOL`
aufgerufen wurden. `CostTracker.add_call()`/`add_from_result()` selbst summieren korrekt
(`src/cost_tracker.py:77`) — der Wert kommt bereits als 0 aus `utils.call_claude()`
(`web_search_calls = getattr(server_tool_use, "web_search_requests", 0) or 0`,
`src/utils.py:96`), vermutlich weil das reale API-Antwortobjekt `server_tool_use` anders
befüllt als angenommen. Nicht verifiziert, nur beobachtet — vorbestehend, keine der
Tasks 1–13 hat `cost_tracker.py` oder `utils.py` seit Plan-1-Task-2 angefasst. Für eine
eigene Untersuchung vormerken, nicht für einen Aufräumlauf.

**10. Task 11 weicht bewusst vom Plan-Pseudocode ab: instanzgebundener statt modulweiter
Rate-Limiter-State.** Der Plan (§ Task 11, Step 1) schlägt ein Modul-Dict
`_rate_limiter: dict = {"calls": [], "last_reset": 0}` vor — modulweiter, mutierbarer
Zustand mit einem nie gelesenen `last_reset`-Schlüssel. Implementiert stattdessen als
`self._call_times: list[float]` auf `FinnhubProvider` selbst: der Wochenlauf (Task 12)
hält ohnehin **eine** Instanz über das ganze Universum — dieselbe Invariante wie „ein
Session-Object pro Run" bei Capital.com (Abschnitt 4) —, und modulweiter State hätte
Tests kontaminiert (ein Test mit 60 Calls hätte den nächsten Test mit einem bereits
gefüllten Fenster starten lassen, ohne expliziten Reset zwischen Tests). Sechs Tests
pinnen das Verhalten, darunter einer, der zwei Instanzen explizit gegeneinander prüft
(`test_rate_limiter_state_is_per_instance_not_shared_globally`).

**11. Task 12s Skip-Prüfung im Plan-Pseudocode hätte Ticker dauerhaft ohne Earnings-Datum
gelassen.** Der Plan (§ Task 12, Step 1) überspringt einen Ticker, sobald
`db.get_cached_fundamentals()` irgendetwas zurückgibt — unabhängig davon, ob die Zeile ein
`earnings_next_date` trägt. Der häufigste Fall ist aber genau eine Zeile **ohne**: Phase 2b
(`fetch_missing_fundamentals()`, Task 7) legt für Kandidaten täglich frische
Fundamentals-Zeilen an, ruft aber laut R15 **nie** `get_earnings_calendar()` — das ist
bewusst dem Wochenjob vorbehalten (Spec § 18.1c). Eine reine „ist gecacht"-Prüfung hätte
so einen Ticker für immer übersprungen, sobald er einmal über den Tageslauf gecacht wurde,
und er hätte **nie** ein Earnings-Datum bekommen. Implementiert: übersprungen wird nur, wenn
die Zeile **sowohl** frisch **als auch** mit gesetztem `earnings_next_date` vorliegt. Ein
eigener Test pinnt genau diesen Unterschied
(`test_does_not_skip_fresh_fundamentals_without_an_earnings_date`).

**12. Ein vorbestehender Test verlor 60 Sekunden an blockierte Netzwerk-Retries, sobald
`_update_weekly_fundamentals()` verdrahtet war.** `test_run_weekly_calls_send_weekly_email`
mockte weder `FinnhubProvider` noch den neuen Vorlauf — gegen eine leere Test-DB galt jeder
Ticker als ungecacht, und der Lauf über das volle `full_universe()` (~30 Ticker × 2 Calls)
traf die Transport-Sperre aus `tests/conftest.py` (Abschnitt „Tests telefonieren nicht nach
draussen") pro Call einzeln, mit spürbarer Retry-Latenz der zugrundeliegenden HTTP-Clients.
Der Test blieb dabei grün — funktional korrekt, nur eben eine Minute lang. Gefixt durch
`patch("main.FinnhubProvider")` und `patch("main._update_weekly_fundamentals")`, konsistent
mit jedem anderen `run_*`-Test in dieser Datei, der Provider immer explizit mockt. Neuer
Test `test_run_weekly_runs_the_fundamentals_prerun_before_the_aggregate` pinnt zusätzlich
die Reihenfolge (Vorlauf vor dem Aggregat, wie im Plan vorgesehen). Laufzeit danach: 1,0 s
statt 60,7 s.

---

### C.8 — Abschluss-Review Plan 2 ✅ (2026-08-15), vier Befunde, alle behoben

Prüfung über `c978d70..HEAD` (Plan-1-Ende bis Plan-2-Ende) gegen die sechs Kriterien aus
der Plan-Datei. **746 Tests grün, 91,28 % Coverage** (`--cov=src --cov=main`), nach den
Fixes unten. Vier Befunde, davon zwei, die den erklärten Zweck ihrer eigenen Task
verfehlten.

| Kriterium | Ergebnis |
|---|---|
| 1. Phase-1-Ablauf (Gate → Sweep → Indikatoren → Technik-Signal) | ✅ sauber; Rohstoff-/Krypto-Ausnahme im Gate verifiziert |
| 2. Phase-2-Schnittstelle (Scan-In/Out, Cutoff, Adapter) | ⚠️ **Befund R1** — Phase 2b fehlte komplett |
| 3. Rohstoff-Ausnahmen (Scan/Cutoff/2b umgangen?) | ✅ alle drei bekommen ausschliesslich `sp500_tds`/`selected`, `cc_tds` taucht dort nirgends auf |
| 4. Kosten gegen Spec § 13.2 | ✅ gemessen, s. Befund 9 |
| 5. Regression Phase 3 / 3b / 4 / 4a | ✅ unverändert, Integrationstests grün |
| 6. DB-Konsistenz (`cutoff_log`, Migration, Altdaten) | ⚠️ **Befunde R2 + R3** |

**R1. ⚠️ Phase 2b hatte keinen Produktions-Aufrufer — die Spec verlangt sie ausdrücklich.**
`fetch_missing_fundamentals()` war in Task 7 gebaut, mit acht Tests belegt, und der eigene
Docstring sagte „das macht Task 10, R16". **Task 10 hat es nicht getan.** Damit fehlte die
in Spec § 4.7 / § 18.1b beschriebene Selbstheilung: ein Ticker mit Cache-Miss ging mit
`pe_ratio=None`, `market_cap_b=None`, `sector="Unknown"` in die Tiefenanalyse, obwohl die
Spec festhält, dass „`market_cap_b` Claude weiterhin über den Ticker-Snapshot aus 2b
erreicht".
**Behoben** mit `data_collector.run_phase_2b()`, verdrahtet zwischen Cutoff und Phase 3.
⚠️ Der naheliegende Ein-Zeilen-Fix (nur `fetch_missing_fundamentals()` aufrufen) wäre eine
Halblösung gewesen: er wärmt den Cache für **morgen**, während der **heutige** Prompt
weiter `None` sähe — die `td`-Dicts entstehen in Phase 1 und werden von Phase 3 gelesen.
`run_phase_2b()` spiegelt die Werte deshalb in die `td`-Dicts zurück. Dabei zusätzlich
Spec § 18.1f eingelöst, das bis dahin niemand umgesetzt hatte: die
**medium/high-Einstufung von `data_quality` entsteht in 2b**, nicht in Phase 1 — eine
Rückstufung auf `'low'` ist ausgeschlossen, der low-Skip gehört ausschliesslich in Phase 1.
Die Feldliste liegt jetzt einmal in `_apply_fundamentals_to_td()` statt doppelt (Phase 1
und 2b hätten sonst auseinanderlaufen können), das Sektor-Mapping analog in `_map_sector()`.
Sechs neue Tests, darunter einer, der die **Sidecar-Invariante** pinnt: 2b füllt nur
bestehende `td`-Schlüssel, führt nie neue ein.

**R2. ⚠️ Die Ratenbegrenzung aus Task 11 zählte Methodenaufrufe statt echter Requests —
und verfehlte damit ihren Zweck um Faktor 2.** `get_fundamentals()` setzt **drei**
Finnhub-Requests ab (`company_profile2`, `company_basic_financials`,
`recommendation_trends`), registrierte aber nur **einen** beim Limiter. Im Wochenlauf sind
das je Ticker 4 echte Requests gegen 2 Registrierungen: der Limiter hätte 60
Registrierungen/Minute durchgelassen = 30 Ticker/min = **120 echte Requests/min gegen ein
60/min-Limit**. Genau das 429, das Task 11 verhindern sollte.
**Behoben:** `_respect_rate_limit()` sitzt jetzt vor **jedem** einzelnen Request. Drei
Tests, die die alte (falsche) Arithmetik gepinnt hatten, sind auf das korrigierte Modell
gezogen; zwei neue pinnen die Request-Zählung explizit
(`test_rate_limiter_counts_every_real_http_call_not_every_method_call`,
`test_a_multi_request_method_hits_the_limit_after_20_calls`).

**R3. `cutoff_log` speicherte `tech_strength` nicht — den dritten Sortierschlüssel und die
halbe Qualifikationsregel.** Die Tabelle existiert ausschliesslich, damit 3D „den 51. mit
dem 50. vergleichen" kann. Der Wert, der über `tech_strength ≥ TECH_MIN_FOR_DEEP`
entscheidet und die Sortierung mitbestimmt, fehlte aber. Aus `tech_agreement` ist er
**nicht** ableitbar: das ADX-Band moduliert ihn (weak deckelt auf 1, strong gibt +1), und
`tech_adx_band` wird ebenfalls nicht gespeichert. **Behoben:** Spalte + Migrationsguard für
Bestands-DBs aus der Task-9-Zwischenzeit.
⏳ Bewusst **nicht** ergänzt: ein `forced`-Flag. Ein Pflicht-Kandidat kann mit
`news_strength=0` und `tech_strength=0` selektiert erscheinen, was ohne Flag verwirrt —
rekonstruierbar bleibt es über die Positionshistorie, und eine Spalte für einen noch nicht
existierenden Konsumenten ist eine Schema-Festlegung auf Verdacht. Für 3D vormerken.

**R4. `cutoff_log` war die einzige Ereignistabelle ohne Retention — und die
volumenstärkste.** Eine Zeile je **bewertetem** Ticker je Lauf: bei 500 Tickern ~1000
Zeilen täglich, ~250 k im Jahr. `cleanup_old_data()` kannte sie nicht, während
`news_summaries` (30 d), `skipped_tickers` (90 d) und `trend_analyses` (180 d) alle
begrenzt sind. Die Datenbank reist bei **jedem** Lauf durch ein GitHub Release, unbegrenztes
Wachstum ist dort keine Theorie. **Behoben** mit 180 Tagen — bewusst dieselbe Grenze wie
`trend_analyses`: reichlich für die 3D-Auswertung, für die die Tabelle gebaut wurde, aber
beschränkt.

⏳ **Nicht behoben, bewusst:** `prompts/deep_analysis_v1.txt` spricht weiter von der
„quick-filter pre-score", bekommt seit Task 10 aber die Cutoff-Felder (`news_strength`,
`tech_direction`, `tech_strength`). Der Prompt liest keine konkreten Feldnamen aus, der
Widerspruch ist rein sprachlich — und Plan 3 ersetzt die Datei ohnehin durch
`deep_analysis_v2`. Eine v1-Änderung jetzt wäre Arbeit an einem Artefakt mit bekanntem
Ablaufdatum.

---

### C.9 — Plan 3a Task 10: Testlauf gegen echte Daten ⚠️ (2026-08-16)

Zwei Läufe gegen eine Wegwerf-Kopie von `data/tracking.db` (`cp` vor jedem Lauf erneuert),
`docker compose run --rm -e RESEND_API_KEY=<ungültig> -v /tmp/plan3a-testlauf:/app/data
trading-harry --run-type pre_market`. Echte Capital.com-/Finnhub-/Anthropic-Calls, 20
MVP-Ticker, die Produktions-DB blieb unberührt. Mailversand lief gegen Resend, scheiterte
mit dem erwarteten 401 (`API key is invalid`), `MailDeliveryError` — Analyse war zu diesem
Zeitpunkt bereits vollständig persistiert (B-10-Pfad, unverändert korrekt).

| | Lauf 1 (`BATCH_SIZE_DEEP=8`, Default) | Lauf 2 (`BATCH_SIZE_DEEP=4`, temporär) |
|---|---|---|
| Kandidaten nach Cutoff | 16 von 20 | 16 von 20 |
| Batches | 2 × 8 | 4 × 4 |
| Analysiert | **8 von 16 (50 %)** | **14 von 16 (87,5 %)** |
| Verloren | ABBV, AMZN, AVGO, GOOGL, HD, META, NVDA, WMT (ein ganzer 8er-Batch) | UNH, XOM |
| Gesamtkosten | 1,8501 EUR | 2,3842 EUR |
| Wanduhrzeit gesamt | ~19 min 23 s | ~29 min 14 s |
| `stop_reason=max_tokens` aufgetreten | 4× (Batch@8 ×2, Hälften@4 ×2) | 6× (Batches@4 ×2 dreimal, Hälfte@2 ×1) |

**Die sechs Prüffragen aus Spec § 12:**

**1. Wie skaliert die Laufzeit mit der Batchgrösse?** Nicht linear, und die kleinere
Batchgrösse ist **langsamer und teurer** — gegenläufig zur Erwartung. Lauf 2 (Batch 4)
brauchte 51 % mehr Wanduhrzeit und 29 % mehr Kosten als Lauf 1 (Batch 8), weil kleinere
Batches das Token-Problem (Frage 4) nicht lösen, sondern nur die Retry-Kaskade verlängern:
drei von vier 4er-Batches scheiterten erst zweimal bei Batchgrösse 4, bevor sie auf 2+2
halbiert wurden — jeder gescheiterte Versuch kostet Zeit und Tokens, ohne verwertbares
Ergebnis.

**2. Recherchiert Claude selektiv?** **Weiterhin unbeantwortet, aber die Ursache ist
geklärt und behoben: `web_search_calls` war ein eigenständiger Zählungsbug, nicht
batch-spezifisch.** `src/utils.py:_result_from_message()` las
`getattr(server_tool_use, "web_search_requests", 0)` — aber `response.usage.server_tool_use`
kommt von der Anthropic-API (`anthropic==0.42.0`) als **plain `dict`** zurück
(`Usage.model_config` hat `extra="allow"`, Pydantic reicht unbekannte Felder als rohes JSON
durch, nicht als Objekt mit Attributen). `getattr()` auf einem `dict` liefert immer den
Default — die Zählung stand seit Einführung von `WEB_SEARCH_TOOL` dauerhaft auf `0`,
unabhängig davon, ob und wie oft tatsächlich gesucht wurde. Verifiziert mit einem
Live-Probe-Call gegen die echte API: das Modell rief `web_search` nachweislich auf
(`content` enthielt `server_tool_use`- und `web_search_tool_result`-Blöcke,
`resp.usage.server_tool_use == {'web_search_requests': 1, ...}`), der alte Code hätte
daraus trotzdem `0` gezählt. **Der bestehende Test
`test_call_claude_extracts_web_search_calls` maskierte den Bug**, weil er
`server_tool_use` als `MagicMock(web_search_requests=3)` mockte — ein Objekt mit
Attributen, nicht den tatsächlichen API-Typ. **Behoben:** `.get()` statt `getattr()`
(`src/utils.py`), Test auf ein `dict`-Mock umgestellt. 770 Tests weiterhin grün.
Die eigentliche Frage — recherchiert `analyze_batch()` selektiv? — bleibt offen, weil die
Läufe aus Task 10 mit der kaputten Zählung liefen und **nicht** wiederholt wurden; das
wäre ein dritter kostenpflichtiger Testlauf und damit ausserhalb des Scopes dieses Fixes.

**3. Bleibt die Qualität bis zum Ende des Batches konstant?** **Nur schwach beantwortbar.**
Die Rohantworten je Ticker werden nicht separat persistiert; sichtbar sind nur die nach
Ranking/Guardrails überlebenden `predictions`-Zeilen. Deren Summary-Längen (546–935
Zeichen) und Scores (3,1–7,6) zeigen in Lauf 2 keinen erkennbaren Abfall zwischen den
zuerst und zuletzt aufgeführten Tickern eines Batches — aber das ist ein Signal aus einer
gefilterten Teilmenge (4 von 14 erfolgreichen Analysen wurden überhaupt ge-rankt), keine
Aussage über alle Ticker.

**4. Reicht `MAX_TOKENS_DEEP`? Darf `stop_reason=max_tokens` nie auftreten?** **Nein —
klar widerlegt, in beiden Läufen wiederholt.** Nicht nur bei der Zielbatchgrösse: in Lauf 2
scheiterte sogar ein auf **2** Ticker halbierter Batch (UNH, XOM) am Boden-Budget
`MAX_TOKENS_DEEP_MIN=4096`. `TOKENS_PER_TICKER_DEEP=900` ist damit als Schätzung
widerlegt — der reale Bedarf des `deep_analysis_v2`-Prompts (8-Dimensionen-Scoring,
`evidence_quality`, R/R-Begründung) liegt spürbar höher. Eine grobe Hochrechnung aus den
beobachteten Ausfällen: verlässlich max_tokens-frei war nur der eine Batch, der auf Anhieb
durchlief (Lauf 2, Batch 3) — kein Wert, aus dem sich der wahre Bedarf präzise ableiten
lässt, aber ein starkes Signal, dass 900 zu niedrig ist.

**5. Ist `rank_score` plausibel?** **Nicht anwendbar — existiert noch nicht.**
`rank_score` ist ausschliesslich Plan-3b-Vokabular (`docs/…/plan3a…md`, „Nach diesem
Plan"); `grep` über `src/*.py` findet keine Fundstelle ausserhalb des Plan-Dokuments
selbst. Diese Prüffrage kann erst mit Plan 3b beantwortet werden.

**6. Kosten je Ticker gegen den Plan-2-Referenzwert (3,3551 EUR / 20 Ticker ≈ 0,168
EUR/Ticker)?** Beide Läufe liegen **darunter** — Lauf 1 bei 0,093 EUR/Ticker (Gesamtlauf ÷
20), Lauf 2 bei 0,119 EUR/Ticker — trotz der Ausfälle. Isoliert auf Phase 3 (Tiefenanalyse
allein, Kostenanstieg zwischen Policy-Monitor-Ende und Phase-3b-Start ÷ erfolgreich
analysierte Ticker): Lauf 1 ≈ 0,079 EUR/erfolgreichem Ticker, Lauf 2 ≈ 0,074
EUR/erfolgreichem Ticker — beide weit über dem Ziel „~0,034 EUR/Ticker" aus dem
Plan-Goal. Der Abstand zum Ziel ist grösstenteils der in Frage 4 gefundene Bug: gescheiterte
Versuche verbrauchen Tokens und werden verworfen, ohne dass ihre Kosten sich in einer
verwertbaren Analyse niederschlagen. Eine belastbare Kostenmessung ohne diesen Fehler steht
noch aus.

**Empfehlung:** `BATCH_SIZE_DEEP` **nicht** auf 4 senken — die Messung zeigt, dass eine
kleinere Batchgrösse das eigentliche Problem (zu knappes Token-Budget je Ticker) nicht löst,
sondern nur öfter in die (teure) Halbierungs-Kaskade läuft. Der nächste Schritt ist eine
Neukalibrierung von `TOKENS_PER_TICKER_DEEP` (aktuell 900, vermutlich zu niedrig um
mindestens den Faktor 2), nicht eine Batchgrössen-Änderung — das ist aber ein Code-Eingriff
und damit ausserhalb des Scopes von Task 10 („Kein Code — eine Messung"). `config.py` ist
unverändert (`BATCH_SIZE_DEEP=8`, der Testwert 4 war nie committet).

⚠️ **Ehrlich vermerkt:** von sechs Prüffragen sind zwei (2, 5) nicht abschliessend
beantwortbar mit den aktuellen Daten — Frage 2, weil die Zählung selbst zur Laufzeit von
Task 10 einen eigenständigen Bug hatte (jetzt behoben, s. oben, aber die Läufe wurden
nicht wiederholt), Frage 5 weil `rank_score` erst in Plan 3b entsteht. Frage 3 ist nur
schwach beantwortbar (gefilterte Stichprobe). Das ist der ehrliche Stand, kein
Formfehler dieser Messung.

⚠️ **Nebenbefund beim Auswerten dieses Abschnitts, separat committet:** `web_search_calls`
stand strukturell immer auf `0` — `src/utils.py:_result_from_message()` las
`server_tool_use` (ein `dict` von der API) mit `getattr()` statt `.get()`. Betraf jeden
Aufrufer von `call_claude(tools=[WEB_SEARCH_TOOL])` (`trend_analyzer`, `market_context`,
`broad_scan`, `deep_analysis`, `commodities_crypto`), nicht nur Phase 3, und war
unabhängig vom Batching aus diesem Plan. Behoben, Details im Commit.

---

### C.10 — Token-Budget neu kalibriert (2026-08-17) ⏳ noch nicht live verifiziert

Antwort auf den Befund aus **C.9**. Drei Änderungen in `src/deep_analysis.py`,
**775 Tests grün, 91,52 % Coverage**.

**1. `TOKENS_PER_TICKER_DEEP` 900 → 2500.** Die Messung aus C.9 liefert die Belege:
bei ~2048 Tokens/Ticker liefen 5 von 6 Batches durch, bei ~1400 nur 1 von 9. 2500 setzt
darüber an. ⚠️ Die Decke kostet für sich genommen **nichts** — abgerechnet wird, was
erzeugt wird. Ein zu knapper Wert kostet dagegen den **ganzen** Call, weil ein gekapptes
Ergebnis verworfen wird.

**2. `BATCH_TOKEN_RESERVE` 2000 → 200 — der eigentliche Konstruktionsfehler.** Der feste
Reserve-Term machte die Formel **regressiv**: er verwässerte den Pro-Ticker-Wert, je
grösser der Batch wurde. Genau verkehrt herum — im grossen Batch kann ein einzelner
geschwätziger Ticker das Budget der anderen aufzehren, der braucht also mehr Luft, nicht
weniger. Die Reserve deckt nur den JSON-Rahmen `{"results": [...]}` (~10 Tokens).

| n | alt | alt /Ticker | neu | neu /Ticker |
|---|---|---|---|---|
| 2 | 4096 | 2048 | 5200 | 2600 |
| 4 | 5600 | **1400** | 10200 | 2550 |
| 8 | 9200 | **1150** | 20200 | 2525 |

Ein Test pinnt die Eigenschaft statt nur die Zahlen:
`max_tokens_for_batch(n) / n >= TOKENS_PER_TICKER_DEEP` für alle n.

**3. Nach einer Kappung wird nicht mehr identisch wiederholt.** Neue Fehlerklasse
`BatchTruncatedError` (Unterklasse von `DeepAnalysisError`, Aufrufer draussen merken
nichts); die Wiederholung bekommt `TRUNCATION_RETRY_FACTOR = 2`-fach Platz. Der Faktor
wandert in die Halbierung mit — **seit Fix 2 ändert Halbieren den Platz pro Ticker nicht
mehr.** Vorher tat es das nur zufällig über den 4096er-Boden (4→2 Ticker hob das Budget
von 1400 auf 2048), was nie so entworfen war. Ohne diesen Punkt wäre das Halbieren nach
der Formel-Korrektur ein Schlag ins Wasser gewesen.
Der bisherige Weg war messbare Verschwendung: identische Eingabe + identische Decke =
identische Kappung, in beiden Läufen **fünfmal** beobachtet, je ~2–3 Minuten. Ein
gekappter Call erzeugt exakt `max_tokens` Ausgabe-Tokens, die Kosten sind also exakt:

| | verworfene Ausgabe-Tokens | ≈ Kosten für nichts |
|---|---|---|
| Lauf 1 | 29 600 | ~0,40 EUR von 1,85 (**22 %**) |
| Lauf 2 | 37 696 | ~0,51 EUR von 2,38 (**21 %**) |

⏳ **Offen und ausdrücklich nicht behauptet:** Diese Werte sind **gegen Unit-Tests**
belegt, **nicht gegen die echte API**. Ob `max_tokens` damit verschwindet und was ein
Lauf dann wirklich kostet, weiss erst ein Wiederholungslauf gegen eine Wegwerf-DB — der
ist bewusst als eigener Schritt vorgesehen. Erst er beantwortet auch die in C.9 offenen
Prüffragen 2, 3 und 6, und erst dann ist Spec § 13.2 (0,034 EUR/Ticker) überhaupt prüfbar.

⚠️ **Latenter Blocker, dabei gefunden, bewusst NICHT behoben:**
`cost_tracker.MODEL_PRICING` kennt **kein Claude-5-Modell**, und `add_call()` wirft
`ValueError("Unknown model pricing")` bei unbekanntem Modell — ein Modellwechsel würde den
Lauf also sofort abstürzen lassen. Für das aktuell genutzte `claude-sonnet-4-6` stimmen
die Preise ($3/$15/$0,30/$3,75). Relevant, weil **Sonnet 5 mit $2/$10 rund ein Drittel
billiger ist** als Sonnet 4.6 und Phase 3 ausgabedominiert ist — der grösste bekannte
Kostenhebel liegt damit im Modellwechsel, nicht in dieser Kalibrierung. Der Eintrag
`claude-opus-4-7` ($15/$75) ist ausserdem veraltet. Gehört zusammen entschieden, nicht
nebenbei: ein anderes Modell ändert das Antwortverhalten und entwertet die Messbasis.

---

### C.11 — Verifikationslauf ✅ (2026-08-17): der Token-Fix wirkt, Kostenziel unterboten

Lauf gegen eine Wegwerf-Kopie (`_verify_run/tracking.db`), echte APIs, `pre_market`,
20 MVP-Ticker, Mail über einen gepatchten `_send` abgefangen statt verschickt. Die
Produktions-DB blieb unberührt. Protokolliert wurde je Phase eine eigene Datei mit
**vollem Request und voller Response** je Call — reine Instrumentierung von aussen, es
wurde kein Produktionscode angefasst.

**1. `stop_reason=max_tokens` ist verschwunden.**

| Batch | Ticker | Budget | genutzt | Auslastung | Ergebnis |
|---|---|---|---|---|---|
| 1 | 8 | 20 200 | 9 409 | 46,6 % | `end_turn`, 8 Analysen |
| 2 | 4 | 10 200 | 5 548 | 54,4 % | `end_turn`, 4 Analysen |

**12 von 12 Kandidaten analysiert, 0 verloren, 0 Wiederholungen, 0 Halbierungen** (C.9:
8 von 16 bzw. 14 von 16 verloren, mit fünf sinnlosen Retries).

⚠️ **Wie knapp es war:** Der 8er-Batch brauchte **9 409** Tokens — das alte Budget war
**9 200**. Er verfehlte es um 209 Tokens, also **2,3 %**. Das erklärt die Streuung aus C.9
exakt: der alte Wert lag nicht grob daneben, sondern haarscharf an der Grenze, weshalb
manche Batches durchliefen und manche nicht. Ein Wert „knapp richtig" ist hier
schlimmer als deutlich zu hoch — die Decke kostet nichts, die Kappung den ganzen Call.

**2. Das Kostenziel aus Spec § 13.2 ist unterboten.** Phase 3 kostete 0,245 EUR für
12 Ticker = **0,0204 EUR je Ticker**, gegen ein Ziel von 0,034 und ~0,12 im alten
Ein-Call-je-Ticker-Weg — rund **6× billiger**. Gesamtlauf **1,9072 EUR**, Laufzeit
**14,6 min** (C.9: 19,4 und 29,2 min). ⚠️ Die 0,245 EUR sind eine **Untergrenze**: die
Websuchen der gestreamten Phasen waren zu diesem Zeitpunkt noch nicht gezählt (Punkt 3).

**3. Zweiter, eigenständiger Zählfehler bei `web_search_calls` — gefunden, weil der erste
behoben war.** Der Lauf wies 32 Websuchen aus (vorher strukturell 0), aber verteilt:
`trend` 5, `market_context` 3, `policy_monitor` 5, `commodities` 19 — und ausgerechnet
`broad_scan` **0** und `deep_analysis` **0**. Exakte Korrelation: **jeder Call mit
`stream=True` zählte 0, jeder mit `stream=False` zählte.**
Zwei Proben gegen die echte API haben das aufgeklärt: **die Suche findet in beiden Pfaden
statt** — beide Antworten tragen `server_tool_use`- und `web_search_tool_result`-Blöcke —
aber `get_final_message()` liefert `usage.server_tool_use == None`. Es fehlte also nur die
**Zählung**, nicht die Recherche. **Behoben:** fehlt das usage-Feld, werden die
`server_tool_use`-Content-Blöcke gezählt; wo das Feld existiert, behält es Vorrang. Gegen
die echte API verifiziert (beide Pfade melden jetzt 1). **777 Tests grün, 91,52 %.**

⚠️ **Zwischendurch ein Fehlalarm, der hier festgehalten gehört.** Aus „0 Websuchen" plus
konkreten, datierten Nachrichten in der Antwort (AVGO/VMware-Lücke, ABBV-Guidance
67,6 Mrd., dazu URLs, die im Input nicht vorkamen) hatte ich geschlossen, das Modell
**erfinde** Nachrichten und Quellen — ein schwerer Vorwurf, und er war **falsch**. Die
Inhalte waren echt recherchiert; nur der Zähler log. Die Lehre: eine kaputte Messung
sieht einem kaputten Verhalten zum Verwechseln ähnlich. Erst die Content-Blöcke als
unabhängige Wahrheitsquelle haben es entschieden — nicht die Plausibilität der Geschichte.

**Beantwortet damit aus C.9:**
- **Prüffrage 4 (reicht `MAX_TOKENS_DEEP`?)** — ✅ ja, mit ~2× Reserve.
- **Prüffrage 6 (Kosten)** — ✅ 0,0204 EUR/Ticker, Ziel unterboten (Untergrenze, s. o.).
- **Prüffrage 1 (Laufzeit)** — ✅ 14,6 min, deutlich schneller ohne die Retry-Kaskade.
- **Prüffrage 2 (selektive Recherche)** — ⏳ **weiterhin offen**, jetzt aber aus einem
  präzise bekannten Grund: dieser Lauf lief noch mit der kaputten Streaming-Zählung. Der
  nächste Lauf misst es erstmals belastbar.
- **Prüffrage 3 (Qualität am Batch-Ende)** und **5 (`rank_score`)** — unverändert offen;
  5 gehört zu Plan 3b.

⏳ **Offen:** `BATCH_SIZE_DEEP = 8` bleibt ein Startwert — bei 46,6 % Auslastung wäre ein
grösserer Batch denkbar, gemessen ist er nicht. Danach der Abschluss-Review über die
Plan-3a-Commits, dann Plan 3b.

---

### C.12 — Abschluss-Review Plan 3a ✅ (2026-08-17), keine kritischen Befunde

Review über `e3dc5a7..61557a1` (16 Commits, 23 Dateien, +4143/-409 Zeilen), analog zum
Plan-2-Review aus **C.8**. Geprüft: Plan-Abgleich, Fehlerpfad-Korrektheit von Hand
nachverfolgt (`BatchTruncatedError`-Reihenfolge, Faktor-Weitergabe durch Halbierung,
`CostCapExceeded`-Propagation), Sidecar-Invariante, Mock-Treue der Tests gegen die
echten API-Antwortformen, Token-Budget-Arithmetik von Hand nachgerechnet, Testsuite
ausgeführt (777 grün, 91,52 %). **Keine Critical-Befunde.** Vier Important-Befunde, alle
noch am selben Tag behoben — anders als bei Plan 2 keine Funktion ohne Produktions-
Aufrufer, keine falsch dimensionierte Ratenbegrenzung; hier ausschliesslich Doku- und
Prompt-Konsistenz, die den vorangegangenen Fix-Commits hinterherhinkte.

**1. CLAUDE.md und ARCHITECTURE.md widersprachen sich selbst.** Die Fix-Commits `7aae691`
(C.10) und `61557a1` (C.11) hatten in beiden Dateien nur den Kopfeintrag aktualisiert,
nicht aber den weiter unten stehenden Sprint-Stand-Abschnitt (CLAUDE.md) bzw. den
Dateikopf (ARCHITECTURE.md) — beide sagten dort weiterhin „nicht produktionsreif" nach
dem C.9-Stand, während der jeweils andere Teil derselben Datei schon „live verifiziert"
sagte. **Behoben:** beide Stellen auf C.10/C.11 gezogen.

**2. `config.py:264-269` — der `BATCH_SIZE_DEEP`-Kommentar rechnete mit der alten
900er-Formel.** Er behauptete weiterhin „MAX_TOKENS_DEEP landet bei ~9.200", nach der
Kalibrierung liefert `max_tokens_for_batch(8)` tatsächlich 20.200 — über der im selben
Kommentar genannten „~16.000er Zone", in der laut Spec 4.8 Timeouts drohen. Praktisch
folgenlos (der Call läuft gestreamt), aber ein künftiger Leser hätte mit falschen Zahlen
gerechnet. **Behoben**, inklusive Verweis auf die C.11-Verifikation.

**3. `prompts/commodities_crypto_v2.txt:86` widersprach dem eigenen `thin`-Mechanismus.**
Eine unveraendert aus v1 übernommene Hard-Rule verlangte weiterhin „every dimension needs
&gt;= 2 evidence lines", direkt unter dem neuen EVIDENCE-QUALITY-Block, der ausdrücklich
erlaubt, eine Dimension als `"thin"` mit weniger zu markieren, und explizit vor dem
Auffüllen warnt. Der Prompt sagte dem Modell an zwei Stellen das Gegenteil — genau die
Auffüll-Versuchung, die `thin` verhindern soll. `deep_analysis_v2.txt` hatte diese Zeile
nicht; der Fehler war spezifisch auf die Rohstoff/Krypto-Variante beschränkt, weil Task 5
den v1→v2-Abgleich dieser einen Zeile nicht in der Diff-Liste hatte. **Behoben:** Zeile
umgeschrieben, verweist jetzt auf die EVIDENCE-QUALITY-Regel statt sie zu widersprechen.
Kein Test pinnte den alten Wortlaut, keine Testkorrektur nötig.

**4. Die Plan-Datei selbst blieb auf dem Task-11-Stand.** `git log` zeigt: letzter
berührender Commit war `0a92d44` (Task 11); die beiden folgenden Fix-Commits (`7aae691`,
`61557a1`) haben die Plan-Datei nicht angefasst, ihr Status-Kopf sagte weiterhin „NICHT
produktionsreif". Unschädlich in Richtung Sicherheit (untertreibt statt zu übertreiben),
aber dieselbe Kategorie Befund wie bei Plan 2 — nur diesmal nicht weil eine Task ohne
Wirkung committet wurde, sondern weil der finale Stand nach Post-hoc-Fixes nirgends im
Plan-Dokument selbst reflektiert war. **Behoben:** Task-Tabelle um die drei Fix-Commits
ergänzt, Status auf „live verifiziert, Abschluss-Review durchgeführt" gezogen.

⏳ **Minor, bewusst nicht behoben:** zwei Codezeilen in `deep_analysis.py`
(Leerlisten-Kurzschluss in `analyze_batch()`, der Zweig „valides JSON ohne `results`-Liste
im Batch-Fall") sind testtechnisch ungedeckt — bei 98 % Modul-Coverage nicht dringend.
`TRUNCATION_RETRY_FACTOR` eskaliert bewusst nur einmal (1→2), nie weiter (Spec 10: begrenzte
Tiefe) — im Verifikationslauf bei 46–54 % Auslastung kein beobachtetes Problem.

**Fazit des Reviews:** Kern der Implementierung — Fehlerpfad, Token-Formel, Sidecar-
Invariante, Verdrahtung in `run_pipeline()` — korrekt, gegen echte API-Läufe verifiziert,
durch Tests abgesichert, die tatsächlich die relevanten Werte prüfen statt nur „es gab
einen Retry". Plan 3a ist damit **abgeschlossen**. Nächster Schritt: Plan 3b.

---

### C.13 — Plan 3b (Ranking) abgeschlossen ✅ (2026-08-18): zwei Critical-Befunde an den Nähten, alle behoben

12/12 Tasks umgesetzt via `superpowers:subagent-driven-development` (frischer Subagent
je Task, Task-Review nach jedem Task, ein Fix-Round bei Task 8). `rank_score`
(`analysis_strength × tech_strength`) ersetzt `probability_pct` als Sortierschlüssel,
`candidate_class` (`core`/`divergence`/`conflict`) trennt Persistierung und Aggregate,
der C.1-Fix (`atr_pct`/`rsi_at_entry`/`volume_ratio` standen hart auf `None`) ist
mitgenommen, `score_total()`/`config.DIMENSION_WEIGHTS` sind entfernt.

**Gesamt-Review über `bc19c8c..d03316b` (12 Commits)**, analog zu C.8/C.12. Die
Prüfperspektive war bewusst anders als bei den Task-Reviews: nicht „stimmt Task N mit
seinem eigenen Brief überein", sondern End-to-End-Datenfluss, die Mutations-Invariante
über den **gesamten** Pfad (nicht nur innerhalb von `rank_and_persist()`), Konsistenz
von `candidate_class` über **alle** `predictions`-Leser (nicht nur die drei, die Plan
3b explizit anfasste), und Migrations-/Rückwärtskompatibilität. Genau aus dieser
Perspektive kamen die beiden Critical-Befunde — beide unsichtbar für jedes
Einzel-Task-Review, weil sie an Nähten zwischen Tasks bzw. zwischen Plan 3a und 3b
sitzen, nicht innerhalb einer Task-Diff.

**1. `analysis_strength()` zählte für jeden Short verkehrt herum.** Die aktiven
v2-Prompts (`prompts/deep_analysis_v2.txt`, seit Plan 3a) verlangen für alle acht
Score-Dimensionen **trade-relative** Polarität — „HIGHER IS ALWAYS BETTER FOR THE
PROPOSED TRADE", `valuation: 10 = … stretched for a short`. `analysis_strength()`
(Spec § 5.2) wandte stattdessen `momentum`s **absolute** Schwelle auf alle acht an
(`short → value <= 4.0`). Gemessen: ein gut belegter Short (Momentum 2.0, die anderen
sieben bei 9.0) zählte **1**, ein Short, dessen Fundamentaldaten komplett gegen den
Trade sprachen (alle acht bei 2.0), zählte **8** — und kam trotzdem durch die
Guardrails, die nur `momentum` selbst prüfen. Die Short-Top-10 war damit grob
**invertiert** sortiert, die persistierte `analysis_strength` für Shorts unbrauchbar.
**Ursache war ein Spec-/Prompt-Defekt, kein Umsetzungsfehler von Plan 3b** — Spec 5.2
unterstellte absolute Polarität für alle acht, die Plan-3a-Prompts etablierten
trade-relative; die Kollision lag zwischen zwei Plänen, kein Task-Brief konnte sie
sehen. **Behoben:** `momentum` behält die richtungsabhängige absolute Regel (die
Guardrails und die Prompts eigene Hard-Rule hängen daran), die anderen sieben zählen
jetzt `value >= MOMENTUM_LONG_MIN` unabhängig von der Richtung. Spec § 5.2 korrigiert,
**Prompts bewusst unverändert** (Regel 10 — der Selbstwiderspruch im Prompt-Wortlaut
„EVERY one of the eight" gegen die eine `momentum`-Ausnahme bleibt dort stehen, ist
jetzt aber in CLAUDE.md dokumentiert). Vorher-Nachher am Code gemessen: guter Short
1→8, schlechter Short 8→1, Longs unverändert. Die Short-Tests, die die alte (falsche)
Semantik pinnten, wurden auf die neue umgeschrieben, nicht nur grün gepatcht — ein
Re-Reviewer hat jede umgeschriebene Assertion von Hand gegen `MOMENTUM_LONG_MIN`/
`MOMENTUM_SHORT_MAX` nachgerechnet.

**2. `candidate_class` ging beim 16:10-Ablösen einer Divergenz-Prediction verloren.**
`main.py`s `_persist_revision()` baute die Nachfolgezeile für
`db.supersede_prediction()` ohne die acht neuen Plan-3b-Spalten — `_insert_prediction()`
stempelte die Nachfolgezeile damit per Default auf `'core'`. Folge, beides still:
`load_recent_outcomes_aggregate()`s `divergence_summary` war strukturell leer für
**genau** die Divergenz-Kandidaten, die 16:10 überlebt haben — die einzigen mit einem
echten Ergebnis — und `load_revision_effectiveness()`s `divergence.confirmed` blieb
dauerhaft 0, während `core.confirmed` mit Divergenzen aufgebläht wurde. Exakt die
Frage, für die Tasks 5/6/10 die Trennung gebaut hatten. Verschärfend: ein bestehender
Test hatte den `divergence`+`trade_proposals`-Zustand von Hand geseedet statt über den
echten Pfad zu laufen — grün auf einem Zustand, den die Pipeline gar nicht erzeugen
konnte, maskierte also den Bug. **Behoben:** `_persist_revision()` reicht alle acht
Spalten aus `pred` (bereits ein `SELECT *`) in den `supersede_prediction()`-Payload
durch; ein neuer Test treibt `_persist_revision()` direkt und prüft die **Wirkung**
über `load_revision_effectiveness()` (`divergence.confirmed=1`, `core.confirmed=0`).

**Drei Important-Befunde, in derselben Welle behoben:**
- `check_earnings()` (Task 4) wurde erhoben, aber **nie durchgesetzt** — kein Aufrufer
  übergab je `enforce_checks=True`, und der 16:10-Pfad (`_revalidate_all`) rief die
  Funktion gar nicht auf, obwohl Spec § 5.3 genau das verlangt. Jetzt in
  `_revalidate_all` verdrahtet, `earnings_in_days` kommt aus dem ohnehin im 16:10-
  Snapshot vorhandenen Wert (kein neuer Datenpfad nötig).
- `divergence_summary` wurde gebaut, aber in der Wochenmail nie gerendert — das
  „Performance"-Wochenblock war still auf `core` verengt. Jetzt als eigener,
  beschrifteter Unterblock gerendert, nie mit `core` vermischt.
- Die Wochentabelle „Signal-Veränderungen" gruppiert seit Task 5 nach
  `(revision_verdict, candidate_class)`, zeigte aber keine `candidate_class`-Spalte —
  zwei „bestaetigt"-Zeilen waren ununterscheidbar. Spalte ergänzt.

**Nicht in der Fix-Welle, bewusste Entscheidungen:**
- `_aggregate_yesterday_outcomes()` (der Tages-Footer „Vortags-Performance") vermischt
  weiterhin core und divergence — Spec § 5.6 zählt „drei Funktionen" auf, die getrennt
  werden müssen, tatsächlich gibt es vier Leser von `predictions`/`outcomes`. Ruling: der
  Tages-Footer ist eine „wie lief gestern"-Portfolioansicht, dort ist Mischen
  vertretbar — es ist jetzt eine dokumentierte Entscheidung, kein Zufall.
- ✅ **I5 behoben (2026-08-18, `896783e`):** Die Top-10-Tabellen in der Tagesmail
  sortieren nach `rank_score`, zeigten aber nur `total_score`/`probability_pct` als
  Spalten — im Live-Lauf sichtbar geworden: BRK-B (Score 5.5) stand vor META
  (Score 7.0), weil `rank_score` 9 gegen 4 sagt. `_row_for_setup()`/
  `_section_stocks()` zeigen jetzt zwei zusätzliche Spalten (`Rank-Score`,
  `Analysis-Strength`), Werte kommen aus den `_rank_score`/`_analysis_strength`-Keys,
  die `rank_and_persist()`s `_enrich()` ohnehin an jede Top-10-Zeile anhängt. TDD,
  zwei neue Tests (u. a. fehlender Key rendert leer statt abzustürzen).
- ✅ **O2 behoben (2026-08-18, `b0a8034`):** Der C.1-Fix aus dem Sprint-3C-Abschluss-
  Review (`atr_pct`/`rsi_at_entry`/`volume_ratio` von hart-`None` auf echte Werte)
  betraf nur den `pre_market`-Pfad (`_to_prediction_row()`). Der 16:10-Pfad
  (`_persist_revision()`) liess diese drei Spalten unangetastet — sie blieben auf
  **jeder** `trade_proposals`-Zeile `None`. Gleiche Fehlerklasse wie C2 (Werte
  vorhanden, aber nicht durchgereicht), hier am 16:10-`snapshot` statt an den
  Plan-3b-Signalspalten: derselbe frische `collect()`-Snapshot, den
  `_signal_context()` für den Morgenlauf liest, trägt `atr_pct`/`rsi_14`/
  `volume_ratio` bereits. TDD, zwei neue Tests (Werte durchgereicht; fehlender
  Snapshot-Wert stürzt nicht ab).

**Live-Testlauf** gegen eine Wegwerf-Kopie (`_verify_run_2/tracking.db`), echte
Capital.com/Finnhub/Anthropic-Calls, `RESEND_API_KEY=invalid` (Mail abgefangen statt
verschickt), volle Request/Response-Protokollierung je Phase in
`_verify_run_2/logs/` (Kopie und Anpassung von `_verify_run/run_verbose.py` aus C.9/
C.11 — reine Instrumentierung von aussen, kein Produktionscode angefasst). 12 von 20
MVP-Tickern durch den Cutoff, 12 Tiefenanalysen + 7 Rohstoff/Krypto-Analysen, **7
core-Predictions** (2 long: XOM/NVDA, 4 short: BRK-B/META/HD/AVGO, 1 Commodity: CL=F),
**0 divergence, 0 conflict** — plausibel, keine leere Ausbeute durch einen Bug.
`rank_score IS NULL` trat in diesem Lauf nicht auf (kein divergence-Kandidat), keine
Verletzung der NULL-nie-0-Regel gefunden. Top-10-Sortierung von Hand gegen
`analysis_strength × tech_strength` nachgerechnet: Long XOM(21)>NVDA(16), Short
BRK-B(9)>META(4)>HD(3)>AVGO(2) — beide korrekt absteigend. `check_earnings` feuerte in
diesem Lauf nicht (kein Kandidat ≤2 Tage vor Earnings) — Check korrekt inaktiv, aber
nicht positiv scharfgeschaltet beobachtet. Divergenz-Sektion der (abgefangenen) Mail
korrekt gerendert: „Keine." plus Zähler „Enthaltungen mit Technik-Richtung: 6 ·
Technik-Konflikte verworfen: 0 · Deckel-Ueberlauf: 0". **Mutations-Invariante live
bestätigt:** 0 Treffer für `_candidate_class`/`_analysis_strength`/`_rank_score` im
Phase-4a-Portfolio-Check-Prompt — der C.6-Vorfall (29 Plan-1-Werte liefen unbemerkt in
Prompts) wiederholt sich nicht. Kein `stop_reason=max_tokens`, keine unerwarteten
Fehler (nur die bekannte „unknown sector value 'Media'"-Warnung und ein erwarteter
Portfolio-Check-Skip für AAPL). **Kosten 1,9187 EUR, 14,4 min — praktisch identisch zur
C.11-Baseline (1,9072 EUR)**, keine Regression durch Plan 3b.

⏳ **Bewusst nicht in diesem Pass behoben** (Doku-Nachzug, kein Code): die Plan-Datei
selbst (`…/plan3b-ranking.md:185,206`) trägt noch den alten, falschen
`analysis_strength`-Pseudocode aus der Zeit vor dem C1-Fix — ausgeführte Plan-Dateien
sind in diesem Projekt historische Artefakte, keine lebende Spezifikation, aber ein
Leser könnte den Bug dort wortgetreu wiederherleiten. `README.md` und
`docs/SPECIFICATION.md` nennen `DIMENSION_WEIGHTS` weiterhin als aktives Konzept —
beide waren laut vorangegangenem Doku-Audit bereits vor Plan 3b als veraltet bekannt
und für einen eigenen Aufräum-Pass vorgemerkt; hier bewusst nicht mit angefasst, um
diesen Pass nicht zu vermischen.

**838 Tests grün, 92,36 % Coverage** (Baseline vor der Fix-Welle: 828/92,33 %).

**Fazit:** Kern der Implementierung — Klassifikation, `rank_score`-Formel,
Mutations-Sicherheit, Migration — korrekt und gegen einen echten Lauf verifiziert. Die
beiden Critical-Befunde zeigen aber deutlich, wozu der Gesamt-Review da ist: beide
lagen exakt dort, wo ein Plan seine eigenen Tasks nicht mehr sieht — an der Naht zu
Plan 3a (Prompt-Polarität) und an einer Stelle, die keine Plan-3b-Task explizit
anfasste (`_persist_revision()`). Plan 3b ist damit **abgeschlossen**. Nächster
Schritt: Sprint 3D (Learning Modul) — braucht eine eigene Planungssession.

---

### C.14 — Run-Type `close` ersatzlos entfallen 🗑️ (2026-08-18)

Zwei Schritte, bewusst als getrennte Commits, weil der zweite eine eigene Entscheidung
verlangte statt als Nebenprodukt mitzulaufen.

**Schritt 1 — `evaluate_open_predictions()` raus aus `run_close()`** (`44520b1`).
`final_close` ist die einzige Auswertungsstelle; so war es beim Preismodell-Design
entschieden (Option 1, „Bewertung wandert in den 00:00-Job"). Der Aufruf in `close` war
ein **liegen gebliebenes Duplikat**, kein bewusster Zweitpfad: die B.6-Entscheidung vom
2026-07-27 hielt `evaluate` ausdrücklich in `close`, **weil damals gleichzeitig der
`evaluate`-Run wegfiel und sonst niemand mehr `outcomes` geschrieben hätte**.
`final_close` (2026-08-06) hat genau diese Lücke geschlossen — die Begründung war
seitdem hinfällig, nur hat niemand den Aufruf nachgezogen. Der B.6-Abschnitt oben ist
entsprechend annotiert (nicht umgeschrieben).

⚠️ Es war dabei **nicht nur redundant, sondern schädlich**: um 22:30 Berlin ist die
Tagesbar noch nicht final (Schluss 00:00 UTC laut `openingHours`), TP-/SL-Treffer werden
aber gegen das Tages-High/Low geprüft, und das kann sich bis zum Schluss nur
**ausweiten**. `close` sah also ein zu enges Fenster und konnte einen Treffer übersehen,
den `final_close` 105 Minuten später gesehen hätte — und weil
`evaluate_open_predictions()` bereits geschlossene Predictions überspringt, **gewann die
zu früh geschriebene Zeile gegen die korrekte**.

**Schritt 2 — der ganze Run-Type entfällt** (`a92c698`). Nach Schritt 1 blieben in
`run_close()` drei Aufgaben, und **alle drei erledigt `pre_market` um 15:00 bereits**:

| Aufgabe | auch in pre_market | Unterschied |
|---|---|---|
| `db.cleanup_old_data()` | `run_pipeline`, direkt nach `init_schema()` | keiner |
| `_fill_price_gaps()` | derselbe `collect()`-Pfad | keiner |
| `_persist_indicators()` | derselbe `collect()`-Pfad | **keiner — wertgleich** |

Der dritte Punkt widerlegt die naheliegende Gegenthese („abends stehen aktuellere
Indikatoren drin"): **die Indikatoren können sich im Tagesverlauf gar nicht ändern.**
Jede Indikator-Funktion bekommt ausschliesslich `df` = `load_price_history_from_db(...)`,
also nur finale Bars bis D-1; der Live-Kurs landet in `td["price"]` und wird nie nach
`technical_indicators` geschrieben. `INSERT OR REPLACE` auf `(ticker, date)` überschrieb
die Zeile um 22:30 mit identischen Werten.

Dazu zwei **aktive Nachteile**, jeder für sich ein Grund: ein voller
Capital.com-Kurs-Sweep (~46 Ticker) ohne einzigartigen Output, und ein dritter
`collect()`-Lauf pro Tag, der `ticker_status.skip_count` **1,5× so schnell** gegen
`TICKER_MAX_SKIPS = 20` treibt — ein dauerhaft kaputter Ticker wäre also schneller
automatisch stillgelegt worden als beabsichtigt.

Das Gegenargument (Ausfallsicherheit, zweiter Anlauf falls `pre_market` scheitert) wurde
geprüft und entkräftet: `cleanup_old_data()` läuft in `pre_market` direkt nach
`init_schema()`, also auch bei einem späten Abbruch, und `_fill_price_gaps()` ist selbst
nur ein Sicherheitsnetz für Ausfälle, das `final_close` täglich ohnehin überflüssig macht.

**Entfernt:** Cron-Zeile `30 20 * * 1-5`, ihr `case`-Zweig, `run_close()`, der
Dispatch-Zweig, `close` aus `RUN_TYPES` und aus den `workflow_dispatch`-Optionen. Zwei
leicht zu übersehende Folgestellen mit korrigiert: der `workflow_dispatch`-**Default**
stand auf `close` (jetzt `final_close`), und der `*)`-Fallback im `case` fiel auf `close`
zurück — er startete damit bei einem unbekannten Trigger stillschweigend einen echten
Lauf. Er setzt jetzt `type=` leer, der Schritt „Run analysis" überspringt dann.

**Tests:** `test_close_still_evaluates_open_predictions` pinnte exakt das entfernte
Verhalten und wurde **umgedreht statt gelöscht**. Neu ergänzt:
`test_final_close_evaluates_open_predictions` — die Gegenseite war **ungepinnt**, fiele
der Aufruf auch dort weg, schriebe niemand mehr `outcomes`, und zwar lautlos. Dazu
`test_close_is_a_removed_run_type`; bewusst **kein** Substring-Test wie
`test_workflow_has_no_removed_run_types`, weil `"close"` in `"final_close"` steckt und
ein `"close" not in ...` entweder immer rot wäre oder das echte Signal verschluckte.
**841 Tests grün, 92,39 % Coverage.**

Nebenbefund für 3D (kein Bug, s. Abschnitt „Sprint 3D"): die
`technical_indicators`-Zeile mit `date = T` ist aus Bars bis `T-1` berechnet — für
Prediction-Features genau richtig, aber leicht als Off-by-one misszuverstehen.

---

### C.15 — Phase 3b (Commodities/Crypto) gebatcht nach asset_class (2026-08-19)

**Anlass:** eine Laufzeit-Prüfung der Cron-Jobs vom 2026-08-18 fand `pre_market` bei
16 Minuten — deutlich mehr als die anderen Läufe. Aufschlüsselung nach Phase: Phase 3
(17 Aktien, gebatcht, 3 Calls) brauchte ~7 Minuten, aber **Phase 3b (7 Commodities/
Crypto) allein ~4,8 Minuten** — sieben sequenzielle Einzelcalls à ca. 40s, weil
`commodities_crypto.py` seit Plan 3a (Task 5) bewusst **ein Call je Asset** blieb,
kein Batch (Spec §6/§9, gepinnt in `test_commodities_crypto_v2_pins_contract`).

**Die Entscheidung war zum Zeitpunkt von Plan 3a richtig begründet, aber die
Begründung betraf nicht die API-Call-Struktur:** Spec §6 verlangt, dass die sieben
Assets **nie gefiltert** werden (kein Trichter, kein Cutoff, keine Ausnahme) — das
bleibt unverändert. Batching ändert nicht, *welche* Assets analysiert werden, nur
*wie viele Calls* das tut. Die „ein Call je Asset"-Formulierung in Plan 3a war eine
zusätzliche, unbegründete Vereinfachung obendrauf, keine Ableitung aus §6.

**Fix:** `commodities_crypto.py` batcht jetzt nach `asset_class` — Commodities (Gold,
Silber, Öl) und Crypto (BTC, ETH, SOL, XRP) je ein Batch, analog zu
`deep_analysis.build_batches()`s Sub-Sektor-Gruppierung bei Aktien: der gemeinsame
Kontext (Makro-Linse für Rohstoffe, Fear&Greed/Dominance für Krypto) ist nur
**innerhalb** einer Klasse wirklich gemeinsam, deshalb keine einzelne Batch über
alle 7. Aus 7 sequenziellen Calls wurden 2 — bei den heute festen 3+4 Assets ein
fester Faktor, kein weiterer Trichter.

**Neue Prompt-Version** `prompts/commodities_crypto_v3.txt` (Regel 10: v1/v2 bleiben
unangetastet auf der Platte) — inhaltlich identisch zu v2, nur mit dem
`results`-Listen-Wrapper aus `deep_analysis_v2.txt` übernommen.
`test_commodities_crypto_v2_untouched` pinnt, dass v2 weiterhin **kein**
`results`-Objekt enthält.

**Fehlerpfad bewusst schlanker als bei Aktien:** `_run_one_batch_with_recovery()`
wiederholt einmal (bei einer Kappung mit `TRUNCATION_RETRY_FACTOR`-facher Decke wie
in `deep_analysis.py`, C.9), gibt danach den ganzen Batch auf — **kein Halbieren**.
Bei maximal 4 Assets pro Batch (asset_class-Gruppierung der fixen 7) spart eine
weitere Aufteilung kaum noch Call-Overhead; die Halbier-Kaskade aus Spec 10 war für
Batches bis 8 Ticker gebaut.

⚠️ **Trade-off, nicht kostenlos:** vorher war jedes Asset unabhängig — ein
kaputter Call verlor genau ein Asset. Jetzt verliert ein zweimal fehlgeschlagener
Batch bis zu 4 Assets auf einen Schlag. Bislang unbeobachtet (die Retry-Stufe fängt
den häufigen Fall), aber eine reale Verschlechterung des Fehlerbilds gegenüber
vorher — im Read-Live-Testlauf beobachten.

**Tests:** `test_commodities_crypto.py` komplett neu geschrieben (TDD, RED vor
GREEN) — `build_batches()`, `max_tokens_for_batch()`, `analyze_batch()` (inkl.
Truncation, Teilergebnisse, Fehler), `analyze_commodities_and_crypto()` (Retry,
Aufgeben, `CostCapExceeded`-Propagation, Batch-Anzahl). `analyze_asset()` (die alte
Einzel-Call-Funktion) ist ersatzlos entfernt, keine Aufrufer mehr ausserhalb der
alten Tests. `tests/integration/test_full_pipeline.py` angepasst: die
Commodities/Crypto-Mock-Antworten brauchen jetzt den `results`-Wrapper.
**854 Tests grün, 92,41 % Coverage.**

Noch nicht live verifiziert — die Zeitersparnis (7 × ~40s → 2 Batchcalls) ist aus
der Architektur hergeleitet, nicht gegen die echte API gemessen. Nächster
`pre_market`-Lauf zeigt die tatsächliche Phase-3b-Dauer.

---

### C.16 — Tote Tabellen/Spalten aufgeräumt, `market_context` + `news_summaries` verdrahtet (2026-08-19)

**Anlass:** Analyse der frisch aus GitHub gesyncten DB (erster Produktionslauf nach
der Reaktivierung, s. C.14/C.15-Umfeld) fand drei leere Tabellen
(`fundamentals`, `news_summaries`, `prompt_versions`) und sechs strukturell immer
`NULL`e Spalten in `market_context` (`sp500_change_pct`, `oil_price`, `gold_price`,
`btc_price`, `fear_greed_value`, `policy_risk_level`).

**Befund je Fall:**
- `fundamentals` — nie beschrieben, `fundamentals_cache` übernahm die Rolle vollständig.
  Keine `save_fundamentals()`-Funktion existiert überhaupt. **Entfernt** (Korbinian
  bestätigt: fundamentals_cache reicht).
- `prompt_versions` — bereits bekannt und dokumentiert (A/B-Testing nie gebaut,
  Sprint 3D). Unverändert stehen gelassen.
- `news_summaries` — Schema + Retention-Job (`cleanup_old_data()`) existierten, aber
  kein Insert-Pfad. Korbinian will die Tabelle **für Sprint 3D** — jetzt verdrahtet,
  s.u.
- `market_context.oil_price/gold_price/btc_price` — die Rohpreise liegen bereits
  vollständig in `price_history` (GC=F/SI=F/CL=F/BTC-USD/ETH-USD/SOL-USD/XRP-USD,
  je 1000 Bars bis 2026-08-18, über dieselbe Capital.com-Pipeline wie die Aktien).
  Korbinian: Preise gehören dorthin, nicht dupliziert in `market_context`.
  **Spalten entfernt.**
- `market_context.fear_greed_value/policy_risk_level` — **werden** berechnet
  (Phase 3b `fetch_fear_greed()`, Phase 3 `run_policy_monitor()`), landeten aber nur
  in Mail/Prompt-Kontext, nie zurück in `market_context`. Root Cause:
  `save_market_context()` läuft in **Phase 0b**, bevor Phase 3/3b überhaupt starten.
  **Jetzt per Backfill nachgetragen**, s.u.
- `market_context.sp500_change_pct` — kein Ticker dafür definiert (anders als
  `VIX_TICKER`), auf Korbinians Wunsch **offen gelassen**, keine Änderung.

⚠️ **Migrations-Präzedenzfall gebrochen, bewusst:** `price_history.premarket_price`
ist eine dokumentiert-tote Spalte, die **stehen gelassen** wurde, um die
produktive DB (persistiert via GitHub Release) nicht mit einem `DROP COLUMN`
anzufassen (`src/db.py:394-397`). Für `fundamentals`/`oil_price`/`gold_price`/
`btc_price` hat sich Korbinian **bewusst gegen** dieses Muster entschieden — auf
Nachfrage explizit "tatsächlich droppen" gewählt. Begründung für den Unterschied:
`fundamentals` war leer (0 Zeilen, minimales Risiko), `market_context` hat nur
4 Zeilen (nicht 46.000+ wie `price_history`). Gegen eine **Kopie** der echten
Produktions-DB getestet: Migration lief sauber, alle 4 Zeilen erhalten, keine
Datenverluste.

**Neue Funktionen** (`src/db.py`):
- `update_market_context_extras(conn, date, run_type, fear_greed_value,
  policy_risk_level)` — `UPDATE`, nicht `INSERT OR REPLACE` (würde sonst die in
  Phase 0b gespeicherten Felder überschreiben). Aufgerufen in `main.py` nach Phase 3b
  (`run_pipeline()`, beide Werte verfügbar) und nach dem Policy-Monitor
  (`run_trade_proposals()`, nur `policy_risk_level` — `trade_proposals` ruft
  `fetch_fear_greed()` nie, `fear_greed_value` bleibt bewusst `NULL` statt erfunden).
- `save_news_summaries(conn, rows)` — Batch-Insert, kein UNIQUE-Constraint (mehrere
  Quellen dürfen für denselben Ticker/Tag nebeneinander stehen).

**Feld-Mapping für `news_summaries`** (Korbinians Entscheidung: beide Quellen,
Phase 2 UND Phase 3): weder `broad_scan` noch `deep_analysis`/`commodities_crypto`
liefern `sentiment`/`market_impact` direkt — abgeleitet statt unbelegt gelassen:
- Phase 2 (`broad_scan`): `summary`=`news_note`, `market_impact` aus `news_strength`
  (0→none, 1→minor, 2→notable, 3→major), `sentiment`=`NULL` (Stärke ist eine
  Betrags-, keine Richtungsskala — nicht ableitbar).
- Phase 3/3b (`deep_analysis`/`commodities_crypto`): `summary`=`summary`,
  `sentiment` aus `direction` (long→bullish, short→bearish, none→neutral),
  `market_impact`=`confidence` (low/medium/high passt direkt durch).

Nur in `run_pipeline()` verdrahtet (`pre_market`) — `run_trade_proposals()` durchläuft
weder Phase 2 noch Phase 3/3b (nur die leichtgewichtige `_revalidate_all()`), hat also
keine Quelle für neue `news_summaries`-Zeilen.

**Tests:** 14 neue Tests (`test_db.py`: Schema-Drop fresh + Migration auf Legacy-DB
für `fundamentals` und die drei Preisspalten, `update_market_context_extras()`
inkl. No-Op auf fehlender Zeile, `save_news_summaries()` inkl. Mehrfachquellen;
`test_main.py`: End-to-End-Backfill in `run_pipeline()` und
`run_trade_proposals()` gegen eine echte Temp-DB). **868 Tests grün, 92,46 %
Coverage.**

Noch nicht live verifiziert — der nächste `pre_market`/`trade_proposals`-Lauf zeigt
erstmals befüllte `fear_greed_value`/`policy_risk_level`-Spalten und
`news_summaries`-Zeilen.

---

### C.17 — `final_close` verschickt jetzt eine Auswertungs-Mail (2026-08-19)

**Anlass:** Korbinian wollte nach jedem `final_close`-Lauf sehen, welche Predictions
aus `pre_market`/`trade_proposals` richtig oder falsch lagen — bisher gab es dafür
nur eine aggregierte Kurzfassung (Trefferquote long/short, Gesamt-P&L) in der
Fussleiste der **nächsten** `pre_market`-Mail, keine Einzeltabelle direkt nach der
Auswertung. Bewusster Bruch mit der bisherigen Design-Entscheidung
(`main.py`-Docstring: "Der Lauf ist bewusst schlank: kein Claude-Call, keine Mail") —
`final_close` bleibt weiterhin ohne Claude-Call (0 EUR Zusatzkosten), bekommt aber
jetzt eine reine DB-Auswertungs-Mail.

**Design-Klärung vor der Umsetzung (bounded, per Brainstorming-Skill):** Zwei
Annahmen aus der ersten Anfrage stimmten nicht mit dem Datenmodell überein:

1. **"Vorhersage pre_market" + "Vorhersage trade_proposals" als zwei
   Richtungs-Spalten** wäre in jedem Fall redundant gewesen. `main.py:_persist_revision()`
   kopiert bei den Urteilen `bestätigt`/`geschwächt`/`unverändert` die Richtung
   unverändert in die neue `trade_proposals`-Zeile; bei `gedreht`/`verworfen`
   entsteht gar keine neue Zeile — die pre_market-Zeile bleibt mit ihrer
   **ursprünglichen** Richtung offen und wird so ausgewertet (E5: "melden, nicht
   handeln", nie eine Gegenposition). Die Richtung ändert sich zwischen den beiden
   Läufen strukturell **nie**. Stattdessen: eine Richtungs-Spalte + eine neue
   "16:10-Urteil"-Spalte (bestätigt/geschwächt/unverändert/gedreht/verworfen/leer).
2. **Das Urteil sitzt nicht immer auf der ausgewerteten Zeile.** Bei
   `gedreht`/`verworfen` schreibt `record_revision()` es direkt auf die (weiter
   offene) pre_market-Zeile. Bei `bestätigt`/`geschwächt`/`unverändert` schreibt
   `supersede_prediction()` es auf die **abgelöste** pre_market-Zeile — ausgewertet
   wird aber die neue `trade_proposals`-Nachfolgezeile, deren eigenes
   `revision_verdict` NULL bleibt. `db.load_evaluated_outcomes()` braucht deshalb
   einen `LEFT JOIN` zurück über `superseded_by` plus `COALESCE`, um das Urteil in
   beiden Fällen zu finden.

**Tabellenspalten** (final: Ticker, Richtung, 16:10-Urteil, Entry, Exit, Ergebnis,
Richtung korrekt (EOD), P&L): "Ergebnis" bildet `exit_reason` auf ein Label ab
(TP/SL/SL bei TP+SL selber Tag/Timeout/Fehlende Daten — `evaluator.py`s
`pessimistic_overlap`-Fall extra benannt, weil er sonst als gewöhnlicher SL-Treffer
missverstanden würde). "Richtung korrekt (EOD)" bleibt eine **eigene** Spalte neben
"Ergebnis": beide stimmen bei TP/SL-Treffern immer überein, weichen aber beim
Timeout-Fall auseinander (Position lief 5 Tage ohne TP/SL-Treffer, der Exit-Kurs kann
trotzdem in die richtige oder falsche Richtung zeigen).

**Neu:**
- `db.load_evaluated_outcomes(conn, evaluated_date)` — Query mit dem
  Rückwärts-Join oben, alphabetisch nach Ticker sortiert.
- `email_sender.render_final_close_html()` / `send_final_close_email()` — eigene
  Mail, **immer** verschickt (auch bei 0 Auswertungen: "Keine Predictions heute
  ausgewertet.") — kein stiller Ausfall, konsistent mit dem Rest des Projekts.
- `run_final_close()` (`main.py`) ruft nach `evaluate_open_predictions()` die neue
  Query auf und verschickt die Mail; Docstring korrigiert ("kein Claude-Call" bleibt
  wahr, "keine Mail" nicht mehr).

**Die alte Fussleiste bleibt** (Korbinians Entscheidung): `_aggregate_yesterday_outcomes()`
und ihr Rendering in der pre_market-Mail sind unverändert — unterschiedlicher
Zeitpunkt (nächster Morgen statt sofort), unterschiedlicher Zweck (Kurzfassung statt
Detailtabelle).

**Tests:** 5 neue Tests in `test_db.py` (Preis-/Ergebnisfelder, Datums-Scoping, drei
Varianten des Urteil-Lookups), 6 in `test_email_sender.py` (Rendering, Label-Mapping,
Urteil-Anzeige, 0-Zeilen-Fall, Versand), 2 neue + 4 angepasste in `test_main.py`
(die vier bestehenden `final_close`-Tests kannten die neue Mail nicht und liefen
sonst gegen das Netz-Blocking-Fixture). **880 Tests grün, 92,52 % Coverage.**

Noch nicht live verifiziert.

---

### C.18 — Migration auf Claude 5 (Sonnet 5 / Opus 5) + Kappungs-Erkennung für alle Einzelcalls (2026-08-20)

**Anlass:** Korbinian hatte die Modell-Strings auf `claude-sonnet-5` / `claude-opus-5`
umgestellt (`config.py`, `deep_analysis.py`, `commodities_crypto.py`,
`trend_analyzer.py` + Testfixtures) und um eine Prüfung gebeten. Die Modell-IDs
selbst waren korrekt und vollständig durchgereicht — der Befund lag woanders.

**Der eigentliche Befund: eine Design-Entscheidung wurde still umgekehrt.**
`utils.call_claude()` setzt **kein** `thinking`-Feld. Unter `claude-sonnet-4-6` hiess
das: **kein Denken**. Unter `claude-sonnet-5` heisst dasselbe Weglassen:
**adaptives Denken an** — und die Denk-Tokens teilen sich die `max_tokens`-Decke mit
dem Antworttext. Genau dieses Risiko war der dokumentierte Grund, 2026-08-11 **nicht**
auf Sonnet 5 zu wechseln (Spec § 14: „Ein Modellwechsel ist ein eigener Schritt mit
eigener Messung"). Diese Messung fand nie statt; der String-Swap hat sie übersprungen.

**Vier Messläufe** gegen Wegwerf-Kopien von `data/tracking.db` (`main.py --db-path`,
echte Capital.com-/Finnhub-/Anthropic-Calls, 20 MVP-Ticker,
`RESEND_API_KEY=invalid` — Mailversand abgefangen; alle Kopien nach dem Lauf
gelöscht, die echte DB nie angefasst):

| Lauf | Phase 0 (`trend_analyzer`) | Phase 3 (`deep_analysis`) | Phase 3b (`commodities_crypto`) | Kosten |
|------|---------------------------|---------------------------|----------------------------------|--------|
| 1 (Ist-Stand) | sauber | **beide Batches gekappt** (n=8, n=4) | sauber | 2,0766 EUR |
| 2 (nach Fix Phase 3) | **gekappt → Lauf abgebrochen** | — (nie erreicht) | — | — |
| 3 (nach Fix Phase 0) | sauber | sauber | **n=3 gekappt** | 1,9894 EUR |
| 4 (nach Fix Phase 3b) | sauber | sauber | sauber | 1,4289 EUR |

⚠️ **Die Lehre steht in den Spalten, nicht in den Zahlen: jedes Modul kappte in einem
ANDEREN Lauf, bei identischem Code und identischer Decke.** Adaptives Denken ist
nicht deterministisch. Ein einzelner sauberer Durchlauf beweist damit **nicht**, dass
eine Decke reicht — genau dieser Fehlschluss hätte in Lauf 1 dazu geführt,
`commodities_crypto` unangetastet zu lassen (dort stand nach Lauf 1 sogar schon der
Kommentar „bewusst nicht prophylaktisch erhöht ohne Kappungsbefund" im Code; Lauf 3
hat ihn widerlegt und er wurde korrigiert).

**Lauf 2 war der schwerste Fall und lag ausserhalb des ursprünglichen Auftrags:**
`trend_analyzer` (Phase 0) hatte — anders als die Batch-Module — **keine**
`stop_reason`-Prüfung. Eine Kappung kam dort als `JSONDecodeError`
(„Unterminated string") an, und Phase 0 ist laut Spec § 3 **fatal für den ganzen
Lauf**. Dieselbe Lücke hatten `market_context` und `revalidation`
(beide `MAX_TOKENS = 1024`, beide ohne Erkennung). Bei `revalidation` wäre der Ausfall
besonders unangenehm: er trifft je offene Position im 16:10-Lauf und liesse die Zeile
still offen.

**Neu — `utils.call_claude_retry_on_truncation()`** (+ `ClaudeTruncatedError`,
`TRUNCATION_RETRY_FACTOR = 2` lokal in `utils.py`, bewusst nicht aus `deep_analysis`
importiert): erkennt `stop_reason == "max_tokens"`, wiederholt **einmal** mit
verdoppelter Decke und wirft, wenn auch die Wiederholung kappt. **Bucht jeden Versuch**
— auch den verworfenen. Ihn nicht zu buchen wäre genau die Fehlerklasse, die in diesem
Projekt schon zweimal Kosten verschleiert hat (Cache-Doppelabzug, `web_search_calls`).
Die drei Einzelcall-Module nutzen sie jetzt; die Batch-Module behalten ihren eigenen,
reicheren Fehlerpfad (Wiederholen → Halbieren) über `BatchTruncatedError`.

**Neu kalibrierte Decken** (die Decke kostet nur, was sie nutzt — ein zu knapper Wert
kostet den ganzen Call):

| Modul | vorher | jetzt | Grundlage |
|-------|--------|-------|-----------|
| `deep_analysis.TOKENS_PER_TICKER_DEEP` | 2500 | **6000** | demonstriert nötig: `(n*2500+200)*2` = 5000/Ticker (Lauf 1) |
| `commodities_crypto.TOKENS_PER_ASSET_CC` | 3584 | **8192** | demonstriert nötig: 21904/3 ≈ 7300/Asset (Lauf 3) |
| `trend_analyzer.MAX_TOKENS` | 4096 | **12288** | Kappung in Lauf 2 |
| `market_context.MAX_TOKENS` | 1024 | **6144** | vorsorglich (keine Kappung beobachtet) |
| `revalidation.MAX_TOKENS` | 1024 | **6144** | vorsorglich (im `pre_market`-Lauf nicht enthalten) |

Die Formel-Form `max(MIN, n*PER_X + RESERVE)` bleibt unangetastet — der C.9-Fehler
(fester Reserve-Term verwässert den Pro-Ticker-Wert) wird nicht wieder eingeführt,
`BATCH_TOKEN_RESERVE` bleibt bei 200. Seit `TOKENS_PER_TICKER_DEEP = 6000` bindet
`MAX_TOKENS_DEEP_MIN = 4096` für kein `n >= 1` mehr; der pinnende Test wurde
entsprechend nachgezogen.

**`MODEL_PRICING` (`cost_tracker.py`)**: `claude-opus-5` (5,00/25,00) und
`claude-sonnet-5` (3,00/15,00) ergänzt, die alten Einträge bewusst **behalten** —
`add_call()` wirft `ValueError` bei unbekanntem Modell, das ist als Sicherheitsnetz
gewollt (Spec § 13).

**Tests:** 5 neue in `test_utils.py` (Durchreichen im Normalfall, verdoppelte
Wiederholung, Buchung des verworfenen Versuchs, Wurf bei doppelter Kappung,
Weiterreichen von `tools`/`stream`). Die Patch-Ziele in `test_trend_analyzer.py`,
`test_market_context.py` und `test_revalidation.py` zeigen jetzt auf
`src.utils.call_claude` statt auf den Modul-Namensraum — so läuft die **echte**
Helper-Logik inklusive Buchung unter Test, statt wegge­mockt zu werden.
**884 Tests grün, 93 % Coverage.**

⚠️ **Vorbestehender roter Test, NICHT aus dieser Migration:**
`test_broad_scan_uses_configured_model_and_web_search` erwartet
`config.CLAUDE_MODEL_SONNET`, während `broad_scan.py` bewusst
`config.CLAUDE_MODEL_HAIKU` nutzt (Modell-Einsatz-Entscheidung vom 2026-08-19). Der
Test war schon vor dieser Session rot — gegen `git stash` verifiziert. Die Angabe
„880 Tests grün" in C.17/CLAUDE.md war insofern zu optimistisch. Bewusst hier nicht
mitrepariert (fremder Befund, eigener Fix).

**Nachgemessen am selben Tag (die beiden nach dem Hauptlauf offenen Punkte):**

1. **`trade_proposals` end-to-end**, gegen eine Wegwerf-Kopie mit `--date 2026-08-18`
   (dort lag noch ein offenes `pre_market`-Signal, AVGO short — deshalb ohne
   vorgeschalteten `pre_market`-Lauf und für 0,396 EUR statt ~3 EUR): `market_context`
   sauber, Policy-Monitor sauber, 1 Signal re-validiert, **keine Kappung**.
2. **`revalidate_one()` 6× wiederholt** mit echter Prediction-Zeile und echtem
   `collect()`-Snapshot (weil ein einzelner Durchlauf unter adaptivem Denken nichts
   beweist — s. o.): **6/6 sauber**, Output 775–1232 Tokens (Mittel 992), Spitze bei
   **20 % der 6144er Decke**.

⚠️ **Der Nebenbefund ist der eigentliche Ertrag: die 6144 waren nicht „vorsorglich",
sie waren nötig.** Drei der sechs Stichproben (1068, 1232, 1065 Tokens) liegen **über
der alten Decke von 1024** — bei unverändertem Code hätte also rund die Hälfte aller
16:10-Re-Validierungen gekappt. Und weil `revalidation` bis zu dieser Migration keine
`stop_reason`-Prüfung hatte, wäre das nicht als Fehler aufgefallen, sondern als
`RevalidationError` → „Zeile bleibt offen" (s. Docstring): ein **stiller** Ausfall
genau in dem Lauf, der über Ablehnungen entscheidet. Für `market_context` (ebenfalls
1024 → 6144) gibt es diese Stichprobenreihe nicht; dort stützen nur die vier Läufe des
Hauptdurchgangs plus der `trade_proposals`-Lauf, alle sauber.

3. **Smoketest `claude-opus-5`** (die ID steht in `config.CLAUDE_MODEL_OPUS`, wird aber
   von **keiner** Produktionsstelle gelesen — ein Tippfehler wäre erst in Sprint 3D
   aufgefallen): löst auf, antwortet, `MODEL_PRICING` kennt sie. 0,0002 EUR.

**Nachtrag am selben Tag — ein vierter Aufrufer, im ersten Durchgang übersehen:**

Auf die Frage „ist die Migration abgeschlossen?" hat eine vollständige Aufstellung
aller `call_claude`-Aufrufstellen **`deep_analysis.run_policy_monitor()`** als vierten
Sonnet-5-Einzelcall mit derselben Lücke gefunden — dieselbe Bug-Klasse wie Phase 0,
nur nicht durch einen Absturz sichtbar geworden:

- `MAX_TOKENS_POLICY = 3072` war nach der Migration die **knappste verbliebene Decke
  im Projekt** — knapper als die 4096, an denen `trend_analyzer` nachweislich kappte.
- Kein `stop_reason`-Check: eine Kappung wäre als `JSONDecodeError` →
  `PolicyMonitorError` erschienen.
- Der Aufrufer (`main.py`, Phase `policy_monitor`) fängt das **nicht** ab — eine
  Kappung hätte den ganzen `pre_market`-Lauf gerissen, exakt wie in Messlauf 2.

Dass er in fünf Läufen sauber blieb, war nach der Lehre oben **kein Beleg**. Jetzt auf
`call_claude_retry_on_truncation()` umgestellt, `MAX_TOKENS_POLICY` 3072 → **9216**
(3×, dieselbe Anhebung wie bei `trend_analyzer`). **Damit hat jeder Sonnet-5-Aufrufer
im Projekt eine Kappungs-Erkennung** — die Batch-Module über `BatchTruncatedError`, die
vier Einzelcalls über den Helfer.

Nicht betroffen und bewusst unangetastet: `broad_scan` und `portfolio_check` laufen auf
**Haiku 4.5**, wo Denken ohne explizites `thinking`-Feld aus bleibt (`broad_scan` hat
ohnehin eine eigene `stop_reason`-Prüfung); `quick_filter` ist seit Plan 2 toter Code.

**Live nachverifiziert:** `trade_proposals` erneut gegen eine Wegwerf-Kopie —
Policy-Monitor sauber (`level=high`, 3 Events), Re-Validierung sauber, 0,4841 EUR.
**`weekly` einmal komplett geprüft:** macht **null Claude-Calls** (nur Finnhub,
DB-Aggregate, Mail) und ist von der Migration damit strukturell nicht betroffen; der
Lauf ging bis zum Mailversand durch. **886 Tests grün.**

**Aufräumen zum Abschluss — Modell-Strings vereinheitlicht.** Der zuletzt rote Test
`test_broad_scan_uses_configured_model_and_web_search` war **kein** Migrationsschaden:
Commit `0db8644` (2026-08-19) stellte `broad_scan` + `portfolio_check` auf Haiku um,
ohne die Tests nachzuziehen — der Code war richtig, die Erwartung veraltet. Beim
Beheben kamen zwei weitere, **grün gebliebene** Fehler derselben Art zum Vorschein:

- `test_broad_scan.py` setzte in der Fixture `r.model = CLAUDE_MODEL_SONNET`, während
  der Code Haiku abrechnet — die Kostenprüfungen rechneten still zu **dreifachen**
  Preisen. Kein Test schlug an, weil nur `total_eur > 0` geprüft wird.
- `test_portfolio_check.py` behauptete `claude-sonnet-4-6` — ein Modell, das seit der
  Migration nirgends mehr läuft.

Ursache in allen drei Fällen: **hart kodierte Modell-Strings**, die bei einem Wechsel
nicht mitwandern. Deshalb liest jetzt **jedes** Modul sein Modell aus `config`
(`portfolio_check` und `quick_filter` waren die letzten beiden mit Literal; die drei
Sonnet-Module hatten es beim String-Swap ebenfalls hart bekommen), und die
Test-Fixtures ebenso. Bewusste Ausnahmen: `test_cost_tracker.py` (prüft `MODEL_PRICING`
anhand seiner Schlüssel — mit `config` tautologisch) und `test_utils.py` (generischer
Durchreicher). Gegenprobe: eine Änderung in `config.py` wandert nachweislich durch alle
acht Module. Der Helfer `_fake_sonnet_result` heisst jetzt `_fake_result` — ein
modellspezifischer Fixture-Name ist genau die Namensfäule, die hier zwei Fehler
verdeckt hat. **887 Tests grün, 0 rot.**

**Offen bleibt:** `claude-opus-5` ist weiterhin nirgends produktiv verdrahtet — die
Preiszeile ist damit smoke-getestet, aber nicht unter Last erprobt. Und `market_context`
hat als einziges der vier Einzelcall-Module keine Stichprobenreihe, nur sechs saubere
Einzelläufe.

---

### C.19 — Rohstoff-/Krypto-Abschnitt der Mail war leer (2026-08-20)

**Anlass:** Korbinian meldete mit Screenshot, dass „Commodities + Crypto" in der Mail
auf **„Keine Daten."** steht, obwohl der Abschnitt immer Marktlage, Trend und eine
Einschätzung zu den sieben Assets zeigen sollte.

**Zwei verschiedene Ursachen, beide vorbestehend — nichts davon aus der C.18-Migration:**

1. **16:10-Mail (der Screenshot).** `run_trade_proposals()` initialisierte
   `payload["commodities_crypto"] = []` und wies es **nie wieder zu** — die einzige
   Zuweisung im Projekt stand in `run_pipeline()`. Phase 3b läuft um 16:10 bewusst
   nicht (Spec § 6: die Tiefenanalyse ist ein Morgenlauf), und die dort gesammelten
   `cc_tds` flossen nur in `snapshots` für die Re-Validierung. **Der Abschnitt konnte
   dort also nie befüllt sein — 100 % aller 16:10-Mails, seit es den Run-Type gibt.**
   Identifiziert über die Abfolge im Screenshot (Commodities → Marktlage → Vortags-
   Performance), die es nur im `trade_proposals`-Template gibt.
2. **pre_market-Mail.** Der Payload kam aus `ranked["commodities_crypto"]`, das durch
   `ranking._guardrail_filter()` läuft: Enthaltungen (`direction='none'`) und Analysen,
   die die Zwei-Belege-Regel reissen, fallen dort **ganz** heraus statt nur aus dem
   Ranking. Gemessen in der C.18-Messreihe: Lauf 1 → 3 von 7 überlebten (SOL/XRP wegen
   dünner Catalyst-Belege), Lauf 4 → 7 von 7. Bei lauter Enthaltungen wäre auch diese
   Mail leer.

⚠️ **Spec-Lage, weil sie in zwei Richtungen zeigt:** Spec § 6 („kein Vorfilter für die
sieben") betrifft die **Analyse** — die lief korrekt, alle sieben werden immer
analysiert. Verloren gingen sie erst beim Mail-Rendering. Die alte `SPECIFICATION.md`
(Sektion 3) nennt tatsächlich alle sieben namentlich, ist aber ausdrücklich **als
historisch eingefroren markiert** und damit kein gültiger Beleg. Die Absicht ist also
belegt, stand aber in keinem gültigen Dokument — dieser Eintrag schliesst die Lücke.

**Neu:**
- `db.load_news_summaries(conn, date, source)` — je Ticker die jüngste Zeile
  (`MAX(rowid)`, die Tabelle hat bewusst kein UNIQUE).
- `main._commodities_payload(deep_cc, ranked_cc)` — alle sieben in den Payload;
  handelbare behalten die **gerankte** Zeile (sie trägt die Phase-4-Anreicherung), die
  übrigen kommen als rohe Analyse durch, markiert mit `tradeable=False`.
- `main._commodities_from_morning(conn, date, snapshots)` — 16:10 lädt die
  Morgen-Einschätzung aus `news_summaries` (dort landen seit C.16 **alle sieben**, auch
  die nicht handelbaren) und reichert sie mit dem frischen 16:10-Kurs an. **0 EUR, kein
  zweiter Claude-Call.**
- `email_sender._section_commodities_crypto()` rendert nicht handelbare Assets mit
  Kurs und Einschätzung, aber **ohne TP/SL** — die sind eine Handelsempfehlung, und
  genau die hat die Analyse dort nicht gegeben. Neue Spalte „Einschätzung": das
  `summary`-Feld liefert der v3-Prompt längst, es wurde nur nie gerendert (Prompts
  blieben unangetastet, Regel 10).

**Tests:** 13 neue (5 Renderer, 5 in `test_main.py`, 3 für `load_news_summaries`).
**900 Tests grün.**

### C.20 — Trainingsdaten-Fundament: Wissensstand einfrieren, Retention vereinheitlichen (2026-08-20)

**Anlass:** Korbinian fragte, ob sein Zielbild — aus Kursen, Technik, News,
Marktlage, Fundamentaldaten, Risiko, Marktrendite, Über-/Unterkauft und
Branchenstimmung eine Prognose zu rechnen — im Code überhaupt angelegt ist. Ein
Audit gegen das Schema ergab: **sieben der neun Größen sind je Prediction sauber
eingefroren**, zwei nicht. Dazu kam ein dritter Verlust, den niemand auf dem
Schirm hatte.

**Die Leitfrage, aus der alles folgt:** *Ist für jede Prediction später
rekonstruierbar, was das System zum Zeitpunkt der Entscheidung wusste?* Ein
Merkmal, das zum Trainingszeitpunkt fehlt, existiert für 3D nicht — und
rückwirkend ist das nicht heilbar.

**Drei Verlustarten gefunden:**

1. **Löschung.** `news_summaries` stand auf **30 Tagen** — der kürzesten Frist im
   Projekt. Vergeben, als die Tabelle noch ein Log war, **bevor** C.16 sie zur
   Trainingsdatenquelle machte. Man behielt das Label (`outcomes`, dauerhaft) und
   verlor nach einem Monat die Begründung. `cutoff_log` (180 T.) trägt zusätzlich
   den **Selektions-Bias**: ohne ihn trainiert 3D nur auf Tickern, die den
   Trichter passiert haben.
2. **Überschreiben.** `fundamentals_cache` hält genau **eine** Zeile je Ticker
   (`INSERT OR REPLACE`, 7-Tage-TTL) — es gab nie eine Historie. In `predictions`
   standen nur die abgeleiteten Scores, nicht die Rohwerte.
3. **Wegwerfen.** `compute_relative_strength()` lief nur im 16:10-Prompt und
   wurde nirgends persistiert.

**Umsetzung** (Spec: `2026-08-20-trainingsdaten-fundament-design.md`, Plan:
`plans/2026-08-20-trainingsdaten-fundament.md`):

- **E1** `config.LEARNING_RETENTION_DAYS = 730` für alle vier befristeten
  Tabellen, parametrisiert statt vier SQL-Literale. Genau die Streuung war die
  Ursache. ⚠️ Grössenrechnung steht an der Konstante: bei 500 Tickern wären es
  mehrere hundert MB — **bei einer Universumsvergrösserung erneut prüfen**.
- **E2** Sieben neue `predictions`-Spalten: `pe_ratio`, `forward_pe`,
  `market_cap_b`, `debt_equity`, `analyst_consensus`, `analyst_consensus_period`,
  `relative_strength`. Bewusst **in `predictions`**, nicht als Cache-Historie: der
  Wert gehört zur *Entscheidung*, und ein Join über Gültigkeitsfenster wäre genau
  die Komplexität, die später Leakage produziert.
- **E3** Finnhubs `period` wird durchgereicht. **Aufgezeichnet, nicht
  durchgesetzt** — welche Frist einen Konsens veralten lässt, soll 3D messen,
  nicht eine Zeile im Provider per Annahme entscheiden.
- **E4** `relative_strength` in **beiden** Läufen berechnet. Nur um 16:10 wäre es
  systematisch mit dem `run_type` korreliert und damit schlimmer als kein Merkmal.
- **E5** `analyst_upside` bleibt leer und wird **nicht** entfernt — Finnhub
  liefert dort kein Kursziel. Abwesenheit ist ehrlich, erfundene Daten wären es
  nicht; die Spalte bleibt Landestelle für eine spätere Quelle.
- **E6** Kein Backfill. Die Rohwerte von damals existieren nicht mehr — sie zu
  rekonstruieren hiesse, sie zu erfinden.
- **E7** Rein additiv (`ALTER TABLE ADD COLUMN`), kein DROP, keine Umbenennung.

⚠️ **Sidecar-Invariante bewusst erweitert.** `analyst_consensus_period` liegt im
`td` und damit in drei Prompts. Das ist kein Leck wie die 29 Plan-1-Indikatoren
(~250 Tokens technischer Rohwerte je Ticker): das Feld gehört zu seinen
Geschwistern — `pe_ratio` und `analyst_consensus` liegen längst dort. Beide
Invarianten-Tests wurden mit Begründung im Test nachgezogen.

**Tests:** 916 grün. Die vier Einzeltests, die je eine eigene Retention pinnten
(30/90/180/180), sind durch parametrisierte Tests über alle vier Tabellen ersetzt
— plus ein Regressionstest, der `news_summaries` explizit über 30 Tage hält.
Migration gegen eine Kopie der echten DB geprüft: Spalten da, 14 Predictions und
46.019 Bars unverändert.

**Aufgeschoben:** `news_summaries.sentiment` ist **kein** Sentiment, sondern aus
der gewählten Richtung rückabgeleitet — wer es als unabhängiges Nachrichtensignal
auswertet, korreliert das Modell mit seiner eigenen Ausgabe. Umbenennung ist der
nächste Schritt. Ebenso offen: Universum auf ~100 Ticker (Kostenrechnung s. u.),
`analyst_upside` befüllen, TP/SL-Kalibrierung ab ~30 Outcomes (heute 7 von 7
`sl_hit` — bei n=7 nicht entscheidbar).

### C.21 — Zirkularität behoben, Universum auf 142 Ticker (2026-08-20)

Fortsetzung von C.20. Zwei Schritte, deren **Reihenfolge Teil des Designs** ist:
erst die verfälschende Aufzeichnung reparieren, dann den Durchsatz vervielfachen —
andernfalls skaliert man den Fehler mit.
Spec: `2026-08-20-zirkularitaet-und-universum-design.md` (Entscheidungen F1–F7).

**Teil A — `news_summaries.sentiment` → `derived_direction` (F1/F2).**
Die Spalte trug keine Nachrichtenstimmung, sondern die aus der vom Modell
**gewählten Richtung** rückabgeleitete Kodierung (`long`→`bullish`). Wer sie in
Sprint 3D als unabhängiges Nachrichtensignal ausgewertet hätte, korrelierte das
Modell mit seiner eigenen Ausgabe — eine Tautologie, die nach starkem Signal
aussieht. **Umbenannt, nicht gelöscht:** der Wert ist korrekt, nur der Name lud
zur Fehlinterpretation ein. Migration per `RENAME COLUMN`, idempotent, gegen eine
Kopie der echten DB geprüft (Werte erhalten, zweiter Lauf No-Op).

**Teil B — Universum 20 → 142 (F4–F7).**
`SP500_FULL_TICKERS` war ein **Stub auf die 20 MVP-Ticker** — `USE_FULL_SP500`
hätte also gar nichts vergrössert. Jetzt 20 MVP + 122 verifizierte Large Caps.

⚠️ **Die Epic-Verifikation war ein Gate, keine Formalie (F5):** geprüft per
**direktem** Abruf `/markets?epics=`, ausdrücklich **nicht** über
`verify_epics.py` — das nutzt die Volltextsuche, und die liefert laut
`SUB_SECTOR_ETFS`-Kommentar zu jedem Kürzel irgendetwas. Von 126 Kandidaten
lösten **122 auf, vier nicht** (BK, EA, EMR, MMC) und fehlen bewusst: ein Ticker
ohne Kurse würde als `insufficient bars` übersprungen, zählte Richtung
`TICKER_MAX_SKIPS` und deaktivierte sich selbst.

142 statt der in F4 geplanten ~100: verifizierte Ticker für eine runde Zahl
wegzuwerfen wäre schlechter als sie zu nutzen, und die Kostenrechnung trägt es
(~4,92 € je Lauf gegen den neuen Deckel von 6,00 €).

**Kostendeckel (F7):** `MAX_COST_PER_RUN_EUR` 4,00 → **6,00**,
`COST_WARN_THRESHOLD_EUR` 3,00 → 4,50. Angehoben, weil die **Grundlast** steigt —
der Deckel bleibt die letzte Sicherung gegen einen Kostenunfall, der Puffer von
~1,08 € deckt die Streuung aus adaptivem Denken (C.18).

**Backfill (F6):** 121.643 Bars über 142 Ticker gegen eine Wegwerf-Kopie geladen,
`--report-coverage` meldet „Alle Ticker haben genug Historie".

⚠️ **`USE_FULL_SP500` bleibt `false`.** Die Aktivierung ist Korbinians
Entscheidung und braucht **vorher den Backfill gegen die produktive DB** — der
hier gefahrene lief bewusst nur gegen eine Kopie. Reihenfolge: verifizieren →
laden → `--report-coverage` → erst dann der Env-Schalter.

**Messlauf mit 142 Tickern** (Wegwerf-Kopie, `USE_FULL_SP500=true`, echte APIs):

| | gemessen | meine Hochrechnung |
|---|---|---|
| Lauf gesamt | **3,4712 €** | 4,92 € |
| davon `broad_scan` (142 Ticker) | **0,576 €** | 1,97 € |
| Laufzeit | **34 min** | ungemessen |
| Kappungen | **0** | — |
| Ergebnis | 142 ok / 0 skipped, 10 long + 2 short + 7 cc | — |

⚠️ **Meine lineare Kostenhochrechnung war um Faktor 3,4 zu pessimistisch** — für
`broad_scan` 1,97 € geschätzt, 0,576 € gemessen. Grund: der Scan **batcht**, der
gemeinsame Kontext (Trend, Marktlage) wird über den Batch amortisiert statt je
Ticker bezahlt. Wer künftig auf 500 hochrechnet, darf **nicht** linear
fortschreiben: die frühere 500er-Schätzung von ~9,88 € ist damit ebenfalls zu
hoch, realistisch dürften es grob 4–5 € sein. Vor einem 3F-Sprung trotzdem messen,
nicht rechnen.

⚠️ **Neues Regime: der Cutoff greift jetzt am Deckel.** 50 von 142 Kandidaten —
`MAX_DEEP_ANALYSIS = 50` bindet erstmals, bei 20 Tickern entschied noch die
Qualifikationsregel (9–13 von 20). Genau die Unterscheidung, die im
`cleanup_old_data`-Umfeld für 3F notiert war. **Damit ist Phase 3 ab jetzt
kostenmässig gedeckelt** und wächst bei weiterer Vergrösserung nicht mehr mit —
aber die Auswahl wird selektiver, was für 3D den Selektions-Bias verstärkt
(`cutoff_log` hält ihn fest, s. C.20).

⚠️ **Laufzeit 34 min** (vorher ~17 min bei 20 Tickern). Das Fenster zwischen
`pre_market` (15:00) und `trade_proposals` (16:10) beträgt 70 min — es passt, aber
die Reserve halbiert sich. Bei einer weiteren Vergrösserung ist die Laufzeit die
bindende Grenze, nicht die Kosten.

**Tests:** 925 grün, darunter eine neue `test_config.py` mit den Invarianten, die
sonst niemand prüft (keine Duplikate, MVP-Ticker enthalten, die vier
nicht-auflösenden ausgeschlossen, `WARN < MAX`).

### C.22 — Outcome-Qualität: Stop-Distanz, Risikobudget, Horizont-Labels (2026-08-21)

Nach C.20 (Merkmale) und C.21 (Zirkularität) der dritte Teil derselben
Voraussetzung: die **Labels** müssen stimmen.
Spec: `2026-08-21-outcome-qualitaet-design.md` (Entscheidungen G1–G7).

**Anlass:** Alle 7 Outcomes waren `sl_hit`, **6 davon an Tag 1**.

⚠️ **Zwei eigene Diagnosen erwiesen sich beim Nachrechnen als falsch** und
stehen hier, damit sie nicht wiederkehren:

- ❌ „Der SL ist zu eng gesetzt." Er ist intraday-eng **by design** — der
  v2-Prompt verlangt wörtlich „Intraday ist das einzige akzeptierte Ziel".
- ❌ „Das 5-Tage-Fenster reisst intraday-enge Stopps." 6 von 7 fielen an Tag 1.

✅ **Zutreffend:** gemessen an `intraday_range_pct` liegt der Stop bei
**0,39–0,78 einer typischen Tagesspanne**, keiner darüber. Er wird vom
**Rauschen** erreicht, bevor die These sich bewähren kann.

**A — `check_stop_distance`, weich (G1–G3).** Erhoben in beiden Läufen, schreibt
`guardrail_rejects` mit `enforced=0`. ⚠️ **Hart hätte er alle 14 vorliegenden
Signale verworfen** — eine Abschaltung, keine Kalibrierung. Gegenprobe an den
echten Daten: 14 von 14 hätten gemeldet. `STOP_MIN_INTRADAY_RANGE_FRAC = 0.8`
ist ein **unbestätigter Startwert**; wer ihn scharf stellt, ohne die Verteilung
anzusehen, schaltet die Pipeline ab.

**B — `check_stop_budget_spent`, hart, nur 16:10 (G4/G5).** Die R/R-Hürde fängt
den Fall **nicht** — sie belohnt Nähe zum Stop sogar: weil `R/R = Ertrag /
Restrisiko` rechnet und der Guardrail nur eine Untergrenze prüft, stieg NVDA am
2026-08-19 auf **26,2** und wurde freigegeben, **0,11 % vor seinem Stop**.
Geprüft wird stattdessen das verbrauchte Morgen-Risikobudget
(`STOP_BUDGET_SPENT_MAX = 0.75`). Gegenprobe an den echten Zeilen: **NVDA (88 %)
und GC=F (75 %) wären beide abgelehnt worden** — beide wurden ausgestoppt.

**C — Horizont-Labels, neue Tabelle `outcome_horizons` (G6/G7).** Je Prediction
und Handelstag eine Zeile: Schlusskurs, Rendite, ob TP/SL **bis dahin** gefallen
wären, ob die Richtung stimmte. Rein beobachtend, **0 € Zusatzkosten**, kein
Claude-Call. Anders als die Fundamental-Rohwerte (C.20) **rückwirkend
nachrüstbar** — die Bars liegen in `price_history`; `setup/backfill_horizons.py`
labelt idempotent nach.

**Was die Labels sofort zeigen** (3 nachbeschriftete Predictions, alle als
`sl_hit` gewertet): **#1 HD short war an 4 von 5 Tagen richtig und hätte bis
Tag 5 den TP erreicht.** Die These war gut, der Stop zu eng — genau die
Information, die bisher weggeworfen wurde. #2 PG dagegen war ab Tag 2 wirklich
falsch. Ohne die Labels sähen beide identisch aus.

⚠️ **Dabei gefunden und behoben: „Tag 1" bedeutete zweierlei.** Der Live-Pfad
zählt die synthetische Bar **ab Signalzeitpunkt** als Tag 1, ein Backfill ohne
Provider beginnt bei **D+1**. Ohne Kennzeichnung hätte 3D die Horizonte still
gegeneinander verschoben gelernt. Neue Spalte `includes_signal_day` hält den
Unterschied fest; `_bar_sequence()` toleriert `price_provider=None` jetzt
explizit statt über eine AttributeError-Warnung je Ticker.

**Tests:** 947 grün.

### C.23 — Vollständige S&P-500-Liste: 451 verifizierte Ticker (2026-08-21)

Fortsetzung von C.21, wo `SP500_FULL_TICKERS` von einem Stub auf 142
handverlesene Ticker kam. Jetzt die vollständige Liste.

**Quelle:** die S&P-500-Konstituenten als **CSV**
(`github.com/datasets/s-and-p-500-companies`), 503 Symbole, Punktnotation auf
die Projektkonvention normalisiert (`BRK.B` → `BRK-B`).

⚠️ **Ein erster Versuch über die gerenderte Wikipedia-Tabelle wurde verworfen.**
Das zusammenfassende Modell lieferte halluzinierte Symbole (`OLAPK`, `XCYG`,
`WYRE WYRE`, `TESA`) und längst übernommene Firmen (`RHT` 2019, `SVB` 2023,
`PXD`/`SPLK` 2024). Wäre das ungeprüft in die Config gewandert, hätte das
Epic-Gate zwar das meiste abgefangen — aber Symbole, die zufällig auflösen,
wären unter dem falschen Etikett „S&P 500" eingezogen. **Für Listen dieser Art
eine strukturierte Quelle nehmen, keine zusammengefasste Seite.**

**Epic-Gate (Spec F5):** 450 von 503 lösten per direktem `/markets?epics=`-Abruf
auf (89 %), **53 nicht** und fehlen bewusst — darunter durchaus grosse Namen
(`EMR`, `DD`, `TEL`, `TT`, `WST`, `STE`). Eine Suche über die Volltextsuche wurde
nicht versucht: CLAUDE.md warnt ausdrücklich davor, und „lieber ungemappt als
falsch gemappt" gilt hier genauso wie bei den Sektor-ETFs.

**Eine Handkorrektur:** `FI` ergänzt — die CSV führt Fiserv noch unter dem alten
`FISV`, Capital.com kennt nur das neue Symbol.

**Gegenprobe:** alle 20 MVP-Ticker enthalten, und **keiner der bisherigen 142
fällt heraus** — die handgebaute Zwischenliste war durchweg echt.

⚠️ **Der Gap-Mechanismus rettet einen nicht.** Beim Planen kam die Annahme auf,
man könne 500 Ticker live schalten und `_fill_price_gaps()` fülle die Historie
nach. Das ist falsch: die Funktion sagt in ihrem eigenen Docstring „Kein
Nachladen, wenn der Ticker noch gar keine Historie hat", und ihr Scanfenster
ist `GAP_SCAN_BARS = 220`. Ohne Backfill würde jeder neue Ticker als
`insufficient bars` übersprungen und sich nach `TICKER_MAX_SKIPS = 20` Läufen
selbst deaktivieren.

**Backfill durchgeführt** (477 Ticker = 451 Aktien + 7 Rohstoffe/Krypto + 19
Sektor-ETFs, über `--universe` mit `USE_FULL_SP500=true`):

| | |
|---|---|
| Dauer | **8 Minuten** (geschätzt waren 45) |
| Neue Bars | **429.465** |
| DB gesamt | 6,2 MB → **60,0 MB**, 475.484 Bars, 477 Ticker |
| `--report-coverage` | **„Alle Ticker haben genug Historie."** |
| `predictions` / `outcomes` | **14 / 7 — unverändert** |

Rohstoffe und Krypto sind mit erfasst und aktuell (je ~1002 Bars, letzter
2026-08-20). Die 60 MB sind für den Release-Artefakt-Transport unkritisch.

⚠️ **Erstmals gegen die produktive `data/tracking.db` gelaufen** statt gegen eine
Wegwerf-Kopie. Begründung: der Backfill ist rein additiv (nur `price_history`,
keine `predictions`/`outcomes`), und der Zweck ist genau, den Stand dort zu
haben. Vorher wurde `data/tracking.db.backup-vor-500er-backfill` angelegt.

**`USE_FULL_SP500` bleibt `false`** — die Liste allein vergrössert nichts.
⚠️ Vor der Aktivierung fehlt eine **Laufzeitmessung**: bei 142 Tickern dauerte
`pre_market` bereits 34 min, das Fenster bis `trade_proposals` (16:10) sind
70 min. Die Kosten sind unkritisch (hochgerechnet ~4,3 € gegen den 6-€-Deckel),
die Laufzeit ist die bindende Grenze.

**Tests:** 947 grün.

⚠️ **Richtigstellung durch C.24:** der Satz „Erstmals gegen die produktive
`data/tracking.db` gelaufen" ist **falsch**. `data/tracking.db` ist eine lokale
Kopie; die produktive Datenbank ist das Release-Asset `db-latest`. Der
C.23-Backfill hat die produktive DB nie erreicht — dort standen weiterhin nur
46 Ticker mit Historie. Die Zeile „`predictions`/`outcomes` 14 / 7 — unverändert"
belegt es selbst: die produktive DB führte zu diesem Zeitpunkt **43 / 24**.

### C.24 — Produktivuniversum: 150 sektor-balancierte Ticker (2026-08-21)

Die 451er-Liste aus C.23 bleibt als **verifizierter Pool** bestehen; produktiv
gefahren werden **150** daraus ausgewählte Ticker (`SP500_PROD_TICKERS`).

**Warum nicht alle 451:** `MAX_DEEP_ANALYSIS = 50` deckelt Phase 3, und bei 142
Tickern griff dieser Deckel bereits am Anschlag (C.21). Ein grösseres Universum
erzeugt deshalb **keine zusätzlichen Predictions**, sondern nur eine andere
Auswahl — aus 451 Kandidaten wäre es ein 11-%-Trichter, dessen Selektion niemand
mehr nachvollziehen kann. Dazu die Kosten: 20 Ticker kosten gemessen 1,6863 €
(Mittel aus drei Produktivläufen, Streuung 1,38–2,04 durch adaptives Denken),
142 Ticker 3,4712 €; linear auf 451 hochgerechnet ~7,4 € gegen einen Deckel von
6,00 €. ⚠️ Die lineare Rechnung lag bei C.21 schon einmal um Faktor 3,4 daneben —
verlässlich ist nur eine Messung, und die steht für 451 aus.

**Auswahlregel** (aus den 451, vier Schritte):
1. Die 20 `SP500_MVP_TICKERS` gesetzt (längste Historie).
2. Mindestens **3** je Sub-Sektor. Die Zahl ist nicht gegriffen: sie ist
   `SECTOR_DB_MOMENTUM_MIN_TICKERS`, und darunter liefert
   `compute_sector_db_momentum()` strukturell `NULL` — der Sub-Sektor trüge
   gar kein Signal bei.
3. Restliche Plätze proportional zur Sektorgrösse im S&P 500.
4. Innerhalb eines Sub-Sektors nach Ø Dollar-Volumen der letzten 60 Bars — bei
   `HOLD_TARGET="intraday"` mit CFD-Hebel 5 bestimmt Liquidität den Spread.

**Sektor-Zuordnung:** einmaliger `company_profile2`-Abruf über alle 451 Ticker
(~8 min, kostenlos, rein lesend). **409 gemappt, 42 ungemappt, 0 Fehler.** Die 42
verteilen sich auf genau fünf Rohwerte — `Media` (16), `Chemicals` (10),
`Communications` (6), `Packaging` (4), `Telecommunication` (4) — also exakt die,
die `SECTOR_ALIASES` bewusst nicht mappt. Die Entscheidung „lieber ungemappt als
falsch gemappt" bestätigt sich damit an echten Daten.

⚠️ Bewusst **nicht** in `fundamentals_cache` geschrieben:
`save_fundamentals_cache()` ist ein `INSERT OR REPLACE` der ganzen Zeile und
hätte `earnings_next_date` gelöscht.

**Verteilung** (20 von 21 Sub-Sektoren): Industrials Rest 15, Financials Rest 15,
Technology Hardware 11, Healthcare Rest 10, Utilities 9, Real Estate 9, Consumer
Staples 9, Consumer Discretionary Rest 8, Retail 8, Oil & Gas 8, Semiconductors
7, Banks 6, Transport 6, Biotech 5, Aerospace & Defense 5, Pharma 5, Auto 4,
MedTech 4, Metals & Mining 4.

⚠️ **GOOGL und META** tragen `finnhubIndustry='Media'` und bleiben ungemappt —
für Communication führt Capital.com keinen ETF. Sie laufen wie in D6 dokumentiert
ohne Sektor-Guardrail, sind als MVP-Ticker aber gesetzt.
⚠️ **„Clean Energy" (ICLN) ist strukturell unbesetzbar:** Finnhub führt FSLR als
`Semiconductors`, und kein anderer S&P-500-Wert fällt dorthin. Kein Auswahlfehler
— der Sub-Sektor hat schlicht kein Mitglied im Index.

**Nebenbefund, mitbehoben:** der Ausdruck `SP500_FULL_TICKERS if USE_FULL_SP500
else ...` stand **fünffach** im Code (`main.py` 2×, `db.py`, `universe.py`,
`capital_provider.py`). Dieselbe Streuung liess bei `LEARNING_RETENTION_DAYS`
eine von vier Tabellen auf einer abweichenden Frist stehen. Jetzt eine Quelle:
`universe.stock_universe()`. Ein Test scannt den Quellbaum und wird rot, sobald
jemand den Schalter wieder lokal kopiert.

⚠️ **Bedeutungswechsel von `USE_FULL_SP500`:** `false` heisst ab jetzt **150**
(vorher 20), `true` weiterhin 451. Die Umstellung auf 150 braucht deshalb
**keine** Env-Variable — sie greift, sobald der Code gepusht ist.

**Backfill gegen die PRODUKTIVE DB** (das Release-Asset, nicht die lokale Kopie):

| | |
|---|---|
| Vorher | 46 Ticker mit ≥220 Bars, 46.111 Bars, 6,1 MB |
| Eingefügt | **129.779 Bars** über 176 Ticker, ~3 min |
| Nachher | **176 Ticker** (150 Aktien + 7 Rohstoffe/Krypto + 19 ETFs), 175.890 Bars, 21,6 MB |
| `--report-coverage` | **„Alle Ticker haben genug Historie."** |
| `predictions` / `outcomes` | **43 / 24 — unverändert** |
| `news_summaries` / `cutoff_log` | **128 / 60 — unverändert** |
| `PRAGMA integrity_check` | `ok`, nach dem Upload erneut gegengeprüft |

⚠️ **Die lokale `data/tracking.db` wurde NICHT hochgeladen.** Sie trägt zwar mehr
Kurshistorie (475.484 Bars aus dem C.23-Backfill), aber deutlich **weniger**
Trainingsdaten (14/7 Predictions/Outcomes gegen 43/24, 0 statt 128
`news_summaries`). Ein Upload hätte 29 Predictions, 17 Outcomes und 128
News-Zusammenfassungen vernichtet — genau die Daten, um die es bei Sprint 3D geht.

**Tests:** 955 grün, 92,76 % Coverage.

⏳ **Offen:** eine **Laufzeitmessung** unter 150 Tickern. Rechnerisch ~35 min
(CI-Lauf mit 20 Tickern: 15m44s; 142 Ticker: 34 min) gegen ein Fenster von 70 min
zwischen `pre_market` (13:00 UTC) und `trade_proposals` (14:10 UTC). Der Puffer
schrumpft, und `concurrency: cancel-in-progress: false` lässt `trade_proposals`
warten statt starten.

⏳ **Parallelisierung ist noch nicht angefangen:** `CLAUDE_PARALLEL_CALLS = 5`
steht in `config.py`, wird aber **nirgends gelesen** — im gesamten Produktivcode
gibt es kein `ThreadPoolExecutor`, kein `asyncio`, kein `threading`. Alle
Claude-Calls laufen strikt sequenziell. Bei 150 Tickern ist das der grösste
Laufzeithebel, und `CostTracker` müsste dafür erst thread-safe werden.

## Sprint 3D — Learning Modul

⚠️ **Noch nicht ausgearbeitet — braucht eine eigene Planungssession, bevor die Implementierung
beginnt.**

Grob umrissen (aus früheren Notizen, **nicht** als Spezifikation zu verstehen):
- Liest `outcomes` getrennt nach Long / Short
- Hit-Rate, Ø P&L, Ø Score bei Treffern vs. Fehltreffern
- Schreibt `data/learnings.json`
- `learnable=False`-Predictions nie ins Lernmodul
- **⚠️ Logging & Auditability (2026-08-19 gemeldet):** Request/Response-Payloads, Prompts
  und Claude-Antworten werden derzeit nicht persistiert — nur CostTracker + Skip-Gründe. Für
  3D gebraucht: separater `audit_log` Table (Metadaten: Timestamp, Ticker, Phase,
  Prompt-Version, Kosten, `stop_reason`) + optionale Blob-Speicherung für Learning-Runs
  unter `--log-prompts`-Flag. Deckt auch Compliance-Anforderungen ab. Details: nachzudenken
  in der 3D-Planungssession.
- ~~Übernimmt die TP/SL-Auswertung aus `close` (s. B.6)~~ — **erledigt/hinfällig:** die
  Auswertung sitzt seit dem Preismodell-Umbau in `final_close`, und `close` ist am
  2026-08-18 ganz entfallen (C.14). 3D muss die Auswertung nicht mehr „übernehmen".
- Optimiert die Gewichte des `ranking_score` aus 3C
- `news_summaries` wird seit C.16 (2026-08-19) befüllt (Phase 2 `broad_scan` +
  Phase 3/3b `deep_analysis`/`commodities_crypto`) — `sentiment`/`market_impact`
  sind dort **abgeleitete**, keine direkt vom Modell gelieferten Werte (Mapping
  s. C.16). 3D sollte das beim Feature-Engineering kennen, bevor es diese Spalten
  als Ground Truth behandelt.

**⚠️ Zwei Eigenschaften der Trainingsdaten, die 3D kennen muss — beide sind KEINE Bugs:**

1. **Die `technical_indicators`-Zeile mit `date = T` ist aus Bars bis `T-1` berechnet**
   (gefunden am 2026-08-18 bei der `close`-Analyse, C.14). Jede Indikator-Funktion in
   `data_collector._process_ticker()` bekommt ausschliesslich `df` =
   `db.load_price_history_from_db(...)`, und das sind nur **finale** Tagesbars — die Bar
   für Tag T schreibt `final_close` erst um 00:15 UTC des Folgetags. Die Zeile ist
   gegenüber ihrem eigenen Datumslabel also um einen Handelstag versetzt.
   **Das ist für Prediction-Features genau richtig:** der Schlusskurs von Tag T darf nicht
   in die Vorhersage für Tag T einfliessen, sonst ist es Leakage — ein Modell, das in der
   Rückrechnung glänzt und im Livebetrieb versagt. Wer das später als Off-by-one
   „korrigiert", zerstört genau diese Eigenschaft. Beim Feature-Engineering explizit
   mitdenken und die Semantik in `learnings.json` dokumentieren.
2. **Die Indikatoren sind pro Tag konstant.** Aus demselben Grund schreiben mehrere Läufe
   am selben Tag (`pre_market` 15:00, `trade_proposals` 16:10) per `INSERT OR REPLACE`
   wertgleiche Zeilen. Es gibt also **keine** Intraday-Auflösung in dieser Tabelle — wer
   für 3D eine braucht (z. B. „wie sah RSI zum 16:10-Einstieg aus?"), muss sie neu
   erheben, nicht aus `technical_indicators` zu rekonstruieren versuchen.
- Zwei bereits im Code markierte TODOs gehören hierher:
  - `src/evaluator.py` (bei `MAX_HOLD_DAYS`): tagesgenaue TP/SL-Auswertung mit echten
    Intraday-Bars statt Tages-High/Low — beseitigt den `pessimistic_overlap`-Fallback
  - `src/quick_filter.py`: dynamische Score-Schwellenwerte aus `learnings.json` statt rein
    promptgetriebener Filterung

---

## Sprint 3E — Human-in-the-Loop

⚠️ **Noch nicht ausgearbeitet — braucht eine eigene Planungssession, bevor die Implementierung
beginnt.**

Geplant ist eine GitHub-Issue-basierte Freigabe von Learning-Modul-Vorschlägen: Änderungen, die
das Lernmodul vorschlägt (Gewichte, Schwellenwerte, Prompt-Kandidaten), werden nicht automatisch
übernommen, sondern zur manuellen Bestätigung vorgelegt. Details offen.

---

## Sprint 3F — Volle 500-Ticker-Skalierung

⚠️ **Noch nicht ausgearbeitet — braucht eine eigene Planungssession, bevor die Implementierung
beginnt.**

Offene Punkte:
- **B-03:** `config.SP500_FULL_TICKERS` ist ein Stub (= MVP-Liste mit 20 Tickern).
  `USE_FULL_SP500=true` würde heute nur 20 Ticker laufen lassen.
- Aktivierung von `USE_FULL_SP500` in der GitHub-Actions-Env
- `historical_loader` für alle 500 Ticker laufen lassen (Capital.com, 3 Jahre, 600 Calls/Min)

### F.1 — ⚠️ Laufzeit und Kosten skalieren nicht *(gemessen 2026-07-29)*

Der erste vollständige Echtlauf liefert harte Zahlen, die 3F blockieren. **Beides muss
in der Planungssession gelöst werden, bevor `USE_FULL_SP500` aktiviert wird.**

**Messung** (`pre_market`, 20 MVP-Ticker, 2026-07-29 19:27–19:52):

| Kennzahl | gemessen |
|---|---|
| Gesamtlaufzeit | ~25 min |
| Gesamtkosten | **3,3143 EUR** (`cost_tracking`) |
| Tiefenanalysen | 19 Stück, ~54 s und ~0,12 EUR je Stück |
| Phase 3 gesamt | 17 min, 2,27 EUR |

> ### ⚠️ Korrektur 2026-07-30: **den Deckel gibt es nicht**
>
> Die folgende Hochrechnung setzt voraus, dass `MAX_DEEP_ANALYSIS = 80` die Zahl der
> Tiefenanalysen begrenzt. **Das tut sie nicht.** Bei der Umsetzung von Plan 2 wurde
> verifiziert: `MAX_DEEP_ANALYSIS` und `BATCH_SIZE_QUICK` sind **tote Konstanten** —
> sie werden nirgends im Code referenziert. `main.py` übergibt *alle* Ticker in
> **einem** Haiku-Call an `quick_filter_batch()` (das 30er-Batching existiert nicht),
> und `analyze_assets()` analysiert **jeden** nicht-`exclude`ten Ticker.
>
> Ausser `CostCapExceeded` begrenzt also **nichts** die Zahl der Tiefenanalysen. Die
> Zahlen unten sind damit die *optimistische* Untergrenze: bei 500 Tickern könnten es
> deutlich mehr als 80 Analysen werden, je nachdem wie viele der Quick-Filter
> durchlässt. Der Fix gehört zu **C.4** (technischer Pre-Filter) und ist bewusst
> **nicht** Teil von Plan 2.

**Hochrechnung auf die 80 Slots aus `MAX_DEEP_ANALYSIS`** *(unter der widerlegten
Annahme, dass der Deckel greift)*:

| | 20 Ticker (gemessen) | 500 Ticker (hochgerechnet) |
|---|---|---|
| Phase 3 | 17 min / 2,27 EUR | **~72 min / ~9,55 EUR** |
| Gesamtlauf | ~25 min / 3,31 EUR | **~95 min / ~10,8 EUR** |
| gegen `MAX_COST_PER_RUN_EUR = 4.00` | ✅ | ❌ **2,7-fach überschritten** |

**Zwei Konsequenzen:**

1. **Kosten-Abbruch.** Bei 80 Analysen greift `CostCapExceeded` nach etwa 30 Stück —
   der Lauf käme nie bis Phase 4. Dank B-05 meldet die Mail immerhin korrekt
   `deep_analysis` als Abbruchphase.
2. **Cron-Kollision.** Die für 3B geplante Struktur legt `pre_market` auf 15:00 und
   `trade_proposals` auf 16:10 — **70 Minuten Abstand**. Ein 95-Minuten-Lauf liefe noch,
   wenn der nächste startet. GitHub Actions serialisiert das nicht; zwei parallele Läufe
   auf derselben DB, und bei der Release-Persistenz gewinnt der, der zuletzt hochlädt.
   Bei 20 Tickern (25 min) unkritisch, ab 3F ein harter Konflikt.

**Der Hebel:** Phase 3 läuft strikt sequenziell (`src/deep_analysis.py`, `for td in
ticker_datas:`). Bei 5 parallelen Analysen fallen die 72 Minuten auf ~15.
~~Entschieden am 2026-07-29: die Parallelisierung wird nach Plan 2 vorgezogen.~~
**Am 2026-07-30 mit Entscheidung E2 zurückgenommen — B.13 gehört wieder zu 3F.**
Die Actions-Minuten-Begründung trug nach E1 nicht mehr (Details in B.13).

Das löst allerdings **nur die Laufzeit, nicht die Kosten**; dafür braucht es entweder
einen **überhaupt erst zu bauenden** Deckel auf Phase 3 (`MAX_DEEP_ANALYSIS` ist eine
tote Konstante, s. Korrekturbox unten), ein günstigeres Modell für Phase 3, oder den
technischen Pre-Filter aus 3C mit deutlich schärferer Wirkung.

**Actions-Minuten:** Das Repo ist derzeit **public**, damit sind die Minuten unbegrenzt
und kostenlos. Geplant ist der Wechsel auf privat — dann greifen 2 000 Minuten/Monat
(Free-Tarif). Bei 95 min/Tag × 22 Handelstage wären allein `pre_market` ≈ 2 090 Minuten
fällig, also über dem Kontingent. Rechnung s. B.13.

---

## 2b. Ideen ohne Sprint-Zuordnung

Gerettet aus `random/project_ideas.md`, bevor die Datei aufgelöst wurde (2026-08-06).
Alles andere darin war entweder erledigt (Gap-Erkennung, Cron-Umbau) oder von der
tatsächlichen Sprint-Struktur überholt. **Keine Zusagen — nur festgehalten, damit sie
nicht verloren gehen.**

| Idee | Notiz |
|---|---|
| **Social-Media-Signale** (X/Twitter, Truth Social) | Trendsetter über `config` konfigurierbar (Trump, Musk, …), deren Posts in die Analyse einfliessen. Grösster Brocken der drei; berührt Guardrails (Belegpflicht) und Kosten. |
| **Roh-Requests/-Responses hinter einem Flag loggen** | Kleine Änderung in `src/utils.py` (Debug-Logging des Response-Texts). Hilfreich, um Prompt- und Parse-Fehler nachzuvollziehen, statt sie aus der Wirkung zu erraten. |
| **SQLite später ggf. auf DuckDB/DWH** | Bewusst *nicht* jetzt. Erst relevant, wenn die Auswertungen über einzelne Läufe hinausgehen (3D/3F). |
| **Gap-Analyse Final-Close → nächster Open** | Mit `price_open` und der finalen Tages-OHLC liegen seit dem Preismodell-Umbau (P3) beide Seiten vor. Offen ist, ob die Lücke prognostisch etwas trägt. |
| **Fair-Value-Gap-Erkennung im Lernmodul** | Setzt die Gap-Analyse voraus. Gehört zu 3D, nicht davor. |

---

## 3. Bekannte Bugs (offen)

| # | Datei | Bug | Schwere | Geplant in |
|---|---|---|---|---|
| B-03 | `config.py:SP500_FULL_TICKERS` | Ist Stub (= MVP-Liste), `USE_FULL_SP500=true` würde nur 20 Ticker laufen lassen | Mittel | Sprint 3F |
| B-11 | `src/evaluator.py` | **`days_to_close` ist bei der Notbremse mehrdeutig.** Schliesst eine Prediction über `MAX_OPEN_CALENDAR_DAYS = 14` bei unvollständigem Fenster, entsteht bei nur einer Bar `days_to_close = 1` — derselbe Wert wie bei einem echten Intraday-Treffer. Unterscheidbar bleibt es an `exit_reason` (`timeout` gegen `tp_hit`/`sl_hit`). **Für 3D: `days_to_close` nie ohne `exit_reason` auswerten.** Bewusst nicht behoben — ein eigener `exit_reason` schlüge in die Weekly-Statistik (`GROUP BY exit_reason`) durch, für einen seltenen Fall | Niedrig | 3D beachten |
| B-12 | `src/data_collector.py` | **Neue Ticker brauchen einen manuellen Backfill.** Mit dem Wegfall von `_ensure_today_bar` (P3) entfällt der stille Bootstrap-Pfad: ein neu in die Config aufgenommener Ticker hat keine Historie, wird als `insufficient bars: 0 < 20` mit `learnable=False` übersprungen und zählt nach `TICKER_MAX_SKIPS = 20` Läufen Richtung Deaktivierung. Reihenfolge ab jetzt: erst `setup/historical_loader.py --tickers <X>`, dann in die Config | Niedrig (Bedienung) | dokumentiert |
| B-13 | `src/sector_momentum.py` | `_fetch_etf_momentum` nimmt weiterhin `conn`, ohne noch zu schreiben — toter Parameter seit dem Rückbau des ETF-Schreibers. Absichtlich nicht entfernt, weil es Aufrufer nach sich zöge | Kosmetisch | Aufräumlauf |
| B-14 | `tests/unit/test_data_collector.py` | `test_process_ticker_skips_on_none_price_history` trägt einen irreführenden Namen: sein Provider-Mock ist totes Setup, `_process_ticker` liest die Historie nicht mehr über den Provider. Die Zusicherungen gelten unverändert und prüfen etwas Sinnvolles (Ticker ohne DB-Historie wird übersprungen und nicht-lernbar protokolliert) — nur der Name passt nicht mehr | Kosmetisch | Aufräumlauf |

**Behoben (2026-07-29, im ersten echten Gesamtlauf gefunden):**

| # | Datei | Bug | Fix |
|---|---|---|---|
| B-10 | `.github/workflows/analyze.yml`, `main.py` | Der Upload der `tracking.db` nach Release `db-latest` hing an `if: success()`. Ein fehlgeschlagener Mailversand beendet den Analyse-Schritt mit Exit 1 → **die DB wurde nicht hochgeladen und die komplette Arbeit des Laufs war verloren**, obwohl sie längst committet war. Im Lauf vom 2026-07-29 wären so 7 Trend-Analysen, der Marktkontext, 9 Predictions, das Sektor-Mapping und die Kostenzeile weggeworfen worden — für 3,31 EUR. Nicht hypothetisch: der Mailversand antwortete zu diesem Zeitpunkt durchgängig mit 401. | Upload auf `if: always()` umgestellt (der Wochen-Snapshot bleibt bewusst auf `success()`). Zusätzlich in `main.py`: `send_daily_email` wird gefangen, loggt ausdrücklich „Analyse persistiert, nur Mailversand scheiterte" und wirft `MailDeliveryError` — der Job bleibt rot, aber die Ursache ist nicht mehr mit einem Analysefehler zu verwechseln. |

**Behoben (2026-07-29, beim Auffüllen der Produktions-DB gefunden):**

| # | Datei | Bug | Fix |
|---|---|---|---|
| B-09 | `setup/historical_loader.py` | `load_ticker_history()` baute **pro Ticker** ein eigenes `CapitalComProvider()`. Da der Provider lazy je Instanz authentifiziert, waren 27 Ticker = 27 Session-Logins in 20 Sekunden → Capital.com antwortete mit **HTTP 429** auf `/session`, und alle Commodity/Crypto-Ticker kamen ohne Daten zurück. Verstiess zugleich gegen die Invariante „Ein Session-Object pro Run" (Abschnitt 4). | `load_all()` baut genau einen Provider und reicht ihn durch; `load_ticker_history()` nimmt ihn als optionalen Parameter und baut nur beim Einzelaufruf selbst einen. Test zählt die Instanzen. |

**Behoben (2026-07-29, Sprint 3B / Plan 1, Schnitt 4):**

| # | Datei | Bug | Fix |
|---|---|---|---|
| B-05 | `main.py:_guess_aborted_phase()` | Gab immer `"policy_monitor"` zurück, egal wo der Run tatsächlich abbrach — die Kosten-Abbruch-Mail zeigte damit systematisch auf die falsche Phase. | `run_pipeline()` führt `current_phase` durch den `try`-Block, der `except`-Zweig liest sie aus. `_guess_aborted_phase()` ersatzlos entfernt. Parametrisierter Test über alle sieben Phasen, die `CostCapExceeded` werfen können. (`7c4c311`) |

**Behoben (2026-07-27, Sprint 3B / Plan 1, Schnitt 1):**

| # | Datei | Bug | Fix |
|---|---|---|---|
| B-07 | `setup/historical_loader.py` | `python setup/historical_loader.py --all` scheiterte mit `ModuleNotFoundError: No module named 'config'` — genau der in CLAUDE.md dokumentierte Aufruf. Beim Direktaufruf liegt nur `setup/` auf `sys.path`. Nur `python -m setup.historical_loader` funktionierte. | `sys.path`-Bootstrap, auf `__package__` geguardet. Beide Aufrufvarianten per Subprozess-Test abgedeckt. (`ea624ef`) |
| B-08 | `setup/historical_loader.py`, `src/providers/capital_provider.py` | Der Setup-Pull schrieb **0 Zeilen**: Capital.com beantwortet `/prices` mit `max>1000` per HTTP 400, `DAYS_3_YEARS` stand auf 1095. Die Konstante verwechselte Kalendertage mit Bars. Der 400er war unsichtbar, weil er nur als „no data returned" durchkam. | `capital_provider.MAX_BARS_PER_REQUEST = 1000` deckelt in `get_price_history()`; `DAYS_3_YEARS` leitet sich davon ab. Pull liefert jetzt 20 000 Zeilen. (`0e539c4`) |

**Behoben (2026-07-09, Commit `d17c2f5`):**

| # | Datei | Bug | Fix |
|---|---|---|---|
| B-01 | `analyze.yml` | Run-Type-Erkennung per Uhrzeit brach bei DST | Matcht jetzt `github.event.schedule`-String direkt via `case` |
| B-02 | `main.py:run_evaluate()` | Hardcoded `YFinanceProvider()` | Nutzt jetzt `CapitalComProvider()` |
| B-04 | `analyze.yml` | Cron-Kommentar/Code-Mismatch | Hinfällig, da Matching nicht mehr über geparste Uhrzeit läuft |

**Behoben (2026-07-17, Commit `c2c8e1c`):**

| # | Datei | Bug | Fix |
|---|---|---|---|
| B-06 | `guardrails.py`, `evaluator.py`, `portfolio_check.py`, `db.py` | MAX_HOLD_DAYS=5 in config.py, aber hardcoded 3 in vier Modulen | Alle vier referenzieren `config.MAX_HOLD_DAYS` (=5). Tests angepasst, neuer Test beweist die 5-Tage-Abdeckung im Walk-Forward-Evaluator. |

---

## 4. Architektur-Entscheidungen die nicht rückgängig gemacht werden dürfen

| Entscheidung | Begründung |
|---|---|
| `SIMULATION_ONLY = True` immer | Niemals echte Orders. Hardcoded, keine Env-Variable. |
| Capital.com als alleiniger OHLC-Provider | 600 Calls/Min kostenlos auf Demo; yFinance hatte Rate-Limits und war unzuverlässig. Kein Fallback mehr (seit `d17c2f5`). |
| SQLite für alle Tracking-Daten | Kein externer DB-Server nötig; DB via GitHub Releases persistiert |
| `learnable=False` für übersprungene Tickers | Schlechte Daten dürfen das Lernmodul nicht vergiften |
| Long / Short getrennt tracken | Hit-Rates sind asymmetrisch; gemeinsames Tracking würde Bias verschleiern |
| `ZoneInfo("Europe/Berlin")` überall | Märkte schließen um Berliner Zeit; Crons in Berlin-Zeit geplant |
| Capital.com Session-Level Auth | Ein Session-Object pro Run (lazy init); nicht je Request neu authentifizieren |
| Fundamentals 7-Tage-Cache in SQLite | Finnhub Free hat Limits; Fundamentals ändern sich selten |
| `extract_json_blob()` mit `raw_decode` | Claude hängt oft Text nach dem JSON; JSONDecoder.raw_decode toleriert das |
| DB-Persistenz via GitHub Releases (`db-latest`) | Kein externer Storage nötig; funktioniert mit kostenlosen GH Actions |
| **8 Score-Dimensionen mit festem Gewicht** | market_env 10%, company 18%, valuation 12%, momentum 22%, risk 10%, sector 10%, catalyst 10%, policy 8% — nicht ändern ohne A/B-Test. Der kombinierte `ranking_score` aus 3C kommt **zusätzlich** dazu, ersetzt `total_score` nicht. |
| **Portfolio-Sektion zuerst in der Mail** | Direkt umsetzbar beim Aufwachen. Gilt unabhängig davon, dass Phase 4a ab 3B *nach* Phase 4 ausgeführt wird. |
| `CostCapExceeded` bricht Phasen ab, sendet trotzdem Mail | Partielle Ergebnisse sind besser als gar keine |
| **Sektor-ETFs nur verifiziert aufnehmen** | Jedes Symbol in `config.SUB_SECTOR_ETFS` muss per `setup/verify_epics.py` bestätigt sein: exakter Epic-Treffer, TRADEABLE, Instrumentenname gegengelesen. Capital.coms Marktsuche ist eine Volltextsuche und liefert zu jedem Kürzel irgendetwas — ungeprüft übernommen ergab das u.a. KBE→KB Home und PPH→PPHE Hotel Group. Lieber ungemappt als falsch gemappt. |
| **Intraday ist das einzige Ziel** | Setups, die nicht klar intraday funktionieren, müssen `direction='none'` liefern — kein Ausweichen auf Mehrtages-Calls. `hold_days_recommended` bleibt reines Learning-Modul-Feld. |

---

## 5. Verhaltensregeln für Claude Code in zukünftigen Sessions

1. **PROJECT_STATUS.md zuerst lesen** — vor jedem neuen Plan oder jeder Implementierung dieses
   Dokument laden, um den aktuellen Stand zu kennen.

2. **Sprints 3D, 3E, 3F sind Platzhalter** — bei Erreichen dieser Sprints **aktiv nachfragen**
   und den Sprint gemeinsam ausarbeiten, **bevor** Code geschrieben wird. Nicht annehmen, die
   Stichpunkte oben seien eine Spezifikation.

3. **Nie echte Orders ausführen** — `SIMULATION_ONLY=True` ist sakrosankt. Kein Code darf je
   `requests.post(...positions...)` für echte Trades aufrufen.

4. **Capital.com ist alleiniger OHLC-Provider** — kein neuer Code darf yFinance importieren oder
   als Fallback wieder einführen. `run_pipeline()`, `run_close()` etc. instanziieren
   `CapitalComProvider()` unconditional — kein `if config.CAPITAL_COM_API_KEY else ...`-Pattern.

5. **Migrations-Guards in `_apply_migrations()`** — neue Spalten/Tabellen immer per
   `PRAGMA table_info()` bzw. `sqlite_master`-Abfrage prüfen vor `ALTER TABLE` / `CREATE TABLE`,
   nie direkt ausführen.

6. **`learnable=False` Predictions nie ins Lernmodul** — die `learnable`-Flag ist semantisch
   wichtig; nie ignorieren.

7. **Timezone immer `ZoneInfo("Europe/Berlin")`** — kein `datetime.now()` ohne Timezone, kein
   UTC-Drift.

8. **Tests nicht löschen oder abschwächen** — Coverage-Ziel 80%. Bei Refactoring: Tests zuerst
   anpassen, dann Code.

9. **Historische Plan-Dateien** — `docs/superpowers/plans/` enthält abgeschlossene Pläne mit
   `⚠️ HISTORISCH`-Banner. Diese Dateien nicht mehr bearbeiten; stattdessen neue Plan-Datei anlegen.

10. **Prompt-Dateien versionieren** — neue Prompt-Versionen immer in `prompts/` mit
    Version-Suffix (`_v2.txt`), nie alte überschreiben ohne DB-Eintrag in `prompt_versions`.

11. **`extract_json_blob()` für alle Claude-Antworten nutzen** — nie direkt
    `json.loads(result.text)` ohne den raw_decode-Wrapper.

12. **Kosten im Auge behalten** — `MAX_COST_PER_RUN_EUR = 4.00`; teure neue Phasen immer mit
    `CostTracker` integrieren.

13. **Neuen Code immer dokumentieren** — jedes neue File bekommt eine Modul-Beschreibung, jede
    neue Funktion einen 1-2-Satz-Docstring (Standard seit Commit `e3b6e86`).

14. **Nachgelagerte Doku-Pflege** — `README.md`, `docs/WORKFLOW.md`, `docs/SPECIFICATION.md` und
    `docs/superpowers/specs/2026-05-19-shares-future-mvp-design.md` sind bekannt veraltet und
    werden bewusst erst in einem finalen Durchgang aktualisiert, wenn Sprint 3 abgeschlossen ist.
    Nicht unaufgefordert anfassen. `CLAUDE.md`, `PROJECT_STATUS.md` und `docs/ARCHITECTURE.md`
    dagegen immer aktuell halten.
