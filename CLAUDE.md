# Shares_Future – SP500 CFD Research Tool

**Zuletzt aktualisiert:** 2026-08-20 — 🧊 **Trainingsdaten-Fundament: der
Wissensstand wird jetzt je Prediction eingefroren.** Audit gegen das Schema ergab
drei Verlustarten: `news_summaries` wurde nach **30 Tagen gelöscht** (kürzeste Frist
im Projekt, vergeben als die Tabelle noch ein Log war — man behielt das Label und
verlor die Begründung), `fundamentals_cache` **überschreibt** sich (eine Zeile je
Ticker, nie Historie), und `relative_strength` wurde **berechnet und weggeworfen**.
Neu: `config.LEARNING_RETENTION_DAYS = 730` für alle vier befristeten Tabellen
(parametrisiert statt vier SQL-Literale — die Streuung war die Ursache), sieben
neue `predictions`-Spalten (Fundamental-Rohwerte + Analysten-**Periode** +
relative Stärke), `relative_strength` jetzt in **beiden** Läufen. Rein additiv,
kein Backfill. **916 Tests grün**, Migration gegen eine Kopie der echten DB
geprüft (14 Predictions, 46.019 Bars unverändert). Details: PROJECT_STATUS **C.20**.

Davor, 2026-08-20 — 📊 **Rohstoff-/Krypto-Abschnitt der Mail war
leer — zwei vorbestehende Ursachen, nicht aus der Migration.** Die 16:10-Mail konnte den
Abschnitt **nie** befüllen (`run_trade_proposals` initialisierte
`payload["commodities_crypto"] = []` und wies es nie zu; Phase 3b läuft dort nicht), die
pre_market-Mail zeigte nur, was `ranking._guardrail_filter()` überlebte — Enthaltungen
(`direction='none'`) und dünne Belege fielen **ganz** raus statt nur aus dem Ranking.
⚠️ Spec § 6 („kein Vorfilter für die sieben") betrifft die **Analyse**, die korrekt lief;
verloren gingen sie erst beim Rendern. Neu: alle sieben immer im Payload
(`_commodities_payload`), nicht handelbare mit Kurs + Einschätzung, aber **ohne TP/SL**
(das wäre eine Empfehlung, die die Analyse nicht gegeben hat); 16:10 lädt die
Morgen-Einschätzung aus `news_summaries` (`_commodities_from_morning`, 0 EUR, kein
zweiter Claude-Call); neue Spalte „Einschätzung" rendert das `summary`-Feld, das der
v3-Prompt längst liefert. **900 Tests grün**, live über die Kette pre_market → 16:10
verifiziert. Details: PROJECT_STATUS **C.19**.

Davor, 2026-08-20 — 🧠 **Migration auf Claude 5 (Sonnet 5 /
Opus 5), inklusive der Messung, die der String-Swap übersprungen hatte.**
`utils.call_claude()` setzt **kein** `thinking`-Feld — unter `claude-sonnet-4-6` hiess
das „kein Denken", unter `claude-sonnet-5` heisst dasselbe Weglassen „**adaptives
Denken an**", und die Denk-Tokens teilen sich die `max_tokens`-Decke mit dem
Antworttext. Genau dieses Risiko war 2026-08-11 der dokumentierte Grund, **nicht** zu
wechseln (Spec § 14). Vier Messläufe gegen Wegwerf-Kopien: **jedes Modul kappte in
einem ANDEREN Lauf, bei identischem Code und identischer Decke** — adaptives Denken ist
nicht deterministisch, ein sauberer Durchlauf beweist **nichts**. Schwerster Fall:
`trend_analyzer` (Phase 0) hatte keine `stop_reason`-Prüfung, eine Kappung kam als
`JSONDecodeError` an — und Phase 0 ist laut Spec § 3 fatal für den ganzen Lauf.
Neu: `utils.call_claude_retry_on_truncation()` (erkennen → einmal mit doppelter Decke
wiederholen → werfen, **jeder** Versuch gebucht) für die vier Einzelcall-Module
(`trend_analyzer`, `market_context`, `revalidation`, `run_policy_monitor`); die
Batch-Module behalten ihren reicheren Pfad. **Damit hat jeder Sonnet-5-Aufrufer eine
Kappungs-Erkennung.** Decken neu kalibriert: `TOKENS_PER_TICKER_DEEP` 2500 → 6000,
`TOKENS_PER_ASSET_CC` 3584 → 8192, Phase 0 4096 → 12288, `MAX_TOKENS_POLICY`
3072 → 9216, die beiden 1024er → 6144.
**884 Tests grün, 93 % Coverage** (⚠️ plus ein **vorbestehender** roter Test in
`test_broad_scan.py`, nicht aus dieser Migration — die „880 grün" unten waren zu
optimistisch). Nachgemessen: `trade_proposals` end-to-end sauber, und
`revalidate_one()` 6× wiederholt **6/6 sauber** — wobei **drei der sechs Stichproben
über der alten 1024er Decke lagen**: rund die Hälfte aller 16:10-Re-Validierungen
hätte gekappt, mangels `stop_reason`-Prüfung still als „Zeile bleibt offen".
Details: PROJECT_STATUS **C.18**.

Davor, 2026-08-19 — 📧 **`final_close` verschickt jetzt eine
Auswertungs-Mail.** Bewusster Bruch mit der bisherigen Entscheidung ("kein
Claude-Call, keine Mail") — bleibt weiterhin ohne Claude-Call (0 EUR
Zusatzkosten), aber eine Tabelle (Ticker, Richtung, 16:10-Urteil, Entry, Exit,
Ergebnis, Richtung korrekt EOD, P&L) zeigt jetzt direkt nach der Auswertung,
welche `pre_market`/`trade_proposals`-Predictions richtig lagen. Zwei
Design-Annahmen aus der ersten Anfrage stimmten nicht mit dem Datenmodell
überein und wurden vor der Umsetzung geklärt: die Richtung ändert sich
zwischen `pre_market` und `trade_proposals` **strukturell nie** (bei
gedreht/verworfen entsteht gar keine neue Zeile, die Original-Richtung wird
ausgewertet — E5), also eine Richtungs-Spalte + „16:10-Urteil" statt zwei
Richtungs-Spalten; und das Urteil sitzt je nach Ausgang auf unterschiedlichen
Zeilen (`record_revision()` vs. `supersede_prediction()`), `db.load_evaluated_outcomes()`
braucht deshalb einen Rückwärts-Join über `superseded_by`. Die alte
Fussleiste in der nächsten `pre_market`-Mail bleibt zusätzlich bestehen.
**880 Tests grün, 92,52 % Coverage.** Noch nicht live verifiziert. Details:
PROJECT_STATUS **C.17**.

Davor, 2026-08-19 — 🧹 **Tote Tabellen/Spalten aufgeräumt,
`market_context` + `news_summaries` verdrahtet.** Analyse der frisch gesyncten
Produktions-DB fand `fundamentals` (0 Zeilen, `fundamentals_cache` übernahm die Rolle
vollständig) und `news_summaries` (0 Zeilen, kein Insert-Pfad existierte) sowie sechs
strukturell immer `NULL`e `market_context`-Spalten. `fundamentals` und
`market_context.oil_price/gold_price/btc_price` **entfernt** (Rohpreise liegen bereits
vollständig in `price_history`, dieselbe Capital.com-Pipeline wie die Aktien) —
⚠️ bewusster Bruch mit dem `price_history.premarket_price`-Präzedenzfall (tote Spalte
bleibt sonst stehen statt DROP, um die produktive DB nicht anzufassen), gegen eine Kopie
der echten DB getestet. `fear_greed_value`/`policy_risk_level` **werden** berechnet
(Phase 3b/3), landeten aber nie in `market_context` — `save_market_context()` läuft in
Phase 0b, bevor beide Werte existieren. Neues `update_market_context_extras()`
(`UPDATE`, kein `INSERT OR REPLACE`) trägt sie nach. `news_summaries` jetzt aus Phase 2
(`broad_scan`) **und** Phase 3/3b (`deep_analysis`/`commodities_crypto`) befüllt —
`sentiment`/`market_impact` sind dabei **abgeleitete** Werte (Richtung/Confidence),
keine direkt vom Modell gelieferten Felder; Vorarbeit für Sprint 3D.
**868 Tests grün, 92,46 % Coverage.** Noch nicht live verifiziert. Details:
PROJECT_STATUS **C.16**.

Davor, 2026-08-19 — ⚡ **Phase 3b (Commodities/Crypto) gebatcht
nach `asset_class` statt sieben Einzelcalls.** Eine Laufzeit-Prüfung der Cron-Jobs vom
2026-08-18 fand `pre_market` bei 16 Minuten; Aufschlüsselung zeigte Phase 3b (7 fixe
Assets: Gold, Silber, Öl, BTC, ETH, SOL, XRP) allein bei ~4,8 Minuten — sieben
sequenzielle Sonnet-Calls à ca. 40s, weil `commodities_crypto.py` seit Plan 3a bewusst
„ein Call je Asset" blieb (gepinnt in einem jetzt ersetzten Test). Diese Formulierung
war eine unbegründete Vereinfachung obendrauf: Spec §6 verlangt nur, dass die sieben
Assets **nie gefiltert** werden, nicht, dass sie einzeln aufgerufen werden. Jetzt zwei
Batches (Commodities, Crypto) statt sieben Calls — analog zu `deep_analysis.py`s
Sub-Sektor-Batching bei Aktien. Neue Prompt-Version `commodities_crypto_v3.txt`
(Regel 10: v2 bleibt unangetastet), Fehlerpfad bewusst schlanker als bei Aktien
(einmal wiederholen, kein Halbieren — Batches sind mit max. 4 Assets schon klein).
⚠️ Trade-off: ein zweimal fehlgeschlagener Batch verliert jetzt bis zu 4 Assets statt
eines. Noch nicht live verifiziert. Details: PROJECT_STATUS **C.15**.

Davor, 2026-08-18 — 🗑️ **Run-Type `close` (22:30) ersatzlos
entfallen.** Aktiv sind nur noch `pre_market`, `trade_proposals`, `final_close`,
`weekly`. Zuerst fiel `evaluate_open_predictions()` aus `run_close()` weg — es war ein
liegen gebliebenes Duplikat: die B.6-Entscheidung hatte es bewusst dort gehalten, WEIL
damals der `evaluate`-Run wegfiel und sonst niemand `outcomes` geschrieben hätte, und
`final_close` hat genau diese Lücke am 2026-08-06 geschlossen. Es war dabei nicht nur
redundant, sondern schädlich: um 22:30 ist die Tagesbar noch nicht final (Schluss 00:00
UTC), TP/SL prüfen aber gegen Tages-High/Low, das sich bis dahin nur ausweiten kann — und
weil `evaluate_open_predictions()` geschlossene Predictions überspringt, **gewann die zu
früh geschriebene Zeile gegen die korrekte**. Danach war `run_close()` vollständig
redundant: `cleanup_old_data()` läuft in `pre_market` direkt nach `init_schema()`, der
Gap-Fill im selben `collect()`-Pfad, und die `technical_indicators`-Zeile ist
**wertgleich** (s. Designentscheidungen). Details: PROJECT_STATUS **C.14**.

Davor, 2026-08-18 — ✅ **Plan 3b (Ranking) abgeschlossen
(12/12 Tasks, Gesamt-Review + Fix-Welle + Re-Review sauber).** `rank_score`
(`analysis_strength × tech_strength`) ersetzt `probability_pct` als Sortierschlüssel,
`candidate_class` trennt core/divergence/conflict in Persistierung und Aggregaten, der
C.1-Fix (`atr_pct`/`rsi_at_entry`/`volume_ratio`) ist mitgenommen, `score_total()`/
`DIMENSION_WEIGHTS` sind entfernt. Der Gesamt-Review über alle 12 Commits fand **zwei
Critical-Befunde an den Nähten, die kein Einzel-Task-Review sehen konnte**:
`analysis_strength()` zählte für jeden Short verkehrt herum (Kollision zwischen Spec 5.2s
absoluter Zählregel und der trade-relativen Polarität der aktiven v2-Prompts — Spec 5.2
korrigiert, Prompts unverändert), und `candidate_class` ging beim 16:10-Ablösen einer
Divergenz-Prediction verloren (`divergence_summary`/`load_revision_effectiveness()`
dadurch strukturell leer für genau die Kandidaten mit echtem Ergebnis). Beide plus drei
Important-Befunde (`check_earnings` nie durchgesetzt, `divergence_summary` nie gerendert,
mehrdeutige Wochentabellen-Zeilen) in einer Fix-Welle behoben, re-reviewed: alle
ADDRESSED, keine neue Breakage. Live-Testlauf gegen eine Wegwerf-Kopie bestätigt den
Fix (Top-10-Sortierung von Hand nachgerechnet korrekt, 0 Mutations-Leck in den
Portfolio-Check-Prompt, 1,9187 EUR — keine Kostenregression gegenüber C.11).
**838 Tests grün, 92,36 % Coverage.** Details: PROJECT_STATUS **C.13**.

Davor, 2026-08-17 — ✅ **Verifikationslauf bestanden
(PROJECT_STATUS C.11).** Nach der Neukalibrierung (`TOKENS_PER_TICKER_DEEP` 900 → 2500,
`BATCH_TOKEN_RESERVE` 2000 → 200, Wiederholung nach Kappung mit doppelter Decke) trat
`stop_reason=max_tokens` **kein einziges Mal** auf: 12 von 12 Kandidaten analysiert,
Budget zu 47–54 % genutzt, Phase 3 bei **0,0204 EUR je Ticker** (Ziel war 0,034, alter
Weg ~0,12). Gesamtlauf 1,9072 EUR in 14,6 min. Dabei ein **zweiter**
`web_search_calls`-Zählfehler gefunden und behoben (gestreamte Antworten tragen kein
`usage.server_tool_use`). **777 Tests grün, 91,52 % Coverage.**
⏳ Offen: `BATCH_SIZE_DEEP = 8` ist weiter ein Startwert (bei 47 % Auslastung wäre mehr
denkbar), dann der Abschluss-Review über die Plan-3a-Commits, dann Plan 3b.

Davor, 2026-08-17 — ⚠️ **Plan 3a (Batch-Tiefenanalyse) ist
code-vollständig (11/11 Tasks), aber NICHT produktionsreif.** Phase 3 läuft gebatcht nach
Sub-Sektor, `deep_analysis_v2` + `commodities_crypto_v2` sind aktiv, `call_claude()` kann
streamen. **Der Testlauf (Task 10) hat `MAX_TOKENS_DEEP` widerlegt:** `stop_reason=max_tokens`
trat in beiden Messläufen mehrfach auf, in einem Fall sogar bei einem auf **2 Ticker**
halbierten Batch — `TOKENS_PER_TICKER_DEEP = 900` ist zu niedrig für den v2-Prompt. Lauf 1
(Batch 8) verlor dadurch 8 von 16 Kandidaten, Lauf 2 (Batch 4) zwei — und war dabei
**teurer und langsamer**, weil kleinere Batches nur öfter in die Halbierungs-Kaskade
laufen. **Vor dem nächsten echten Lauf muss `TOKENS_PER_TICKER_DEEP` neu kalibriert
werden.** `BATCH_SIZE_DEEP = 8` ist unverändert ein unbestätigter Startwert, kein
Messergebnis. Details: PROJECT_STATUS **C.9**.
Nebenbefund, separat behoben: `web_search_calls` stand **strukturell immer auf 0** —
`server_tool_use` kommt als `dict`, wurde aber mit `getattr()` gelesen. Betraf jeden
Websuche-Aufrufer seit Einführung des Tools; alle bisher ausgewiesenen
`web_search_eur`-Werte sind dadurch zu niedrig. **770 Tests grün, 91,50 % Coverage.**

Davor, 2026-08-15 — ✅ **Plan 2 (Trichter) abgeschlossen inkl.
Abschluss-Review** über `c978d70..HEAD`: vier Befunde, alle behoben. Zwei verfehlten den
Zweck ihrer eigenen Task — **Phase 2b hatte keinen Produktions-Aufrufer** (Task 7 baute
`fetch_missing_fundamentals()`, Task 10 verdrahtete sie entgegen der eigenen Notiz nicht;
jetzt `run_phase_2b()`, das die Werte auch in die `td`-Dicts zurückspiegelt), und die
**Finnhub-Ratenbegrenzung zählte Methodenaufrufe statt echter Requests** (`get_fundamentals()`
setzt drei ab → der Wochenlauf wäre mit ~120 Requests/min gegen ein 60/min-Limit gelaufen).
Dazu: `tech_strength` fehlte in `cutoff_log`, und die Tabelle hatte als einzige
Ereignistabelle keine Retention (jetzt 180 Tage). Details: PROJECT_STATUS **C.8**.
**746 Tests grün, 91,28 % Coverage.** Offen: nur noch Plan 3 (Analyse & Ranking).

Davor, 2026-08-15 — **Plan 2 (Trichter), Task 13: Doku — alle 13 Tasks
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

## Knowledge Graph
**graphify-out/graph.json und GRAPH_REPORT.md müssen in jeder Session aktuell gehalten werden** — vor komplexeren Fragen zu Architektur/Cross-File-Abhängigkeiten zuerst `/graphify query` oder `graphify update` laufen lassen, nie blind in Einzeldateien gehen. Das verhindert Navigations-Fehler und Duplicate-Work. Der Graph wird per AST extrahiert (kein API-Key nötig), neue/geänderte Dateien werden bei `graphify update` automatisch reindexiert.

## Modell-Einsatz (2026-08-19 Entscheidung — seit 2026-08-20 live, C.18)
**Haiku für einfache Scoring-Tasks, Sonnet 5 für Tiefenanalyse, Opus nur für Sprint 3D:**
- `broad_scan` (News-Scoring 0-3): **Haiku 4.5** → spart 90% Kosten (~$0.001/Call)
- `portfolio_check` (HALTEN/SCHLIESSEN): **Haiku 4.5** → strukturiert, kein Overkill (~$0.006/Lauf)
- `deep_analysis` + `commodities_crypto` (8 Dimensionen): **Sonnet 5** → braucht Nuance, schneller
- `trend_analyzer`, `market_context`, `revalidation`: **Sonnet 5** (Claude 5 Standard)
- **Opus 5:** nicht in Produktion außer Sprint 3D (Learning Modul). `MODEL_PRICING` kennt
  die Zeile, produktiv gelaufen ist sie nie.
- **Fable 5:** wird nach 3D-Evaluierung erwogen. ⚠️ **Nicht als Spar-Option missverstehen**
  (frühere Notiz hier sagte „sehr schnell, ideal für tägliche Scoring-Läufe" — das ist
  falsch): Fable 5 ist das **fähigste** Modell und mit $10/$50 je Mio. Tokens **teurer
  als Opus**. Für die täglichen Scoring-Läufe bleibt Haiku die richtige Wahl.
- Test-Skript (`random/test_prompts_manual.ipynb`): maximal **Sonnet 5** (kein Opus)
- ⚠️ **Ein Modellwechsel ist nie nur ein String-Swap.** Er ändert Tokenizer,
  Denk-Verhalten und damit jede kalibrierte `max_tokens`-Decke — s. Designentscheidungen
  und PROJECT_STATUS C.18. Nach jedem Wechsel gehört ein Messlauf dazu.
- ✅ **Jedes Modul liest sein Modell aus `config`** (seit 2026-08-20), keins kodiert
  den String hart: `CLAUDE_MODEL_SONNET` für `trend_analyzer`, `deep_analysis`,
  `commodities_crypto`, `market_context`, `revalidation`; `CLAUDE_MODEL_HAIKU` für
  `broad_scan`, `portfolio_check`, `quick_filter` (tot). Ein Wechsel ist damit **eine**
  Zeile in `config.py`. Vorher liefen hart kodierte Strings und Test-Fixtures
  auseinander — `test_broad_scan` war seit `0db8644` rot (Erwartung Sonnet, Code Haiku),
  und `test_portfolio_check` rechnete still zu Sonnet-4.6-Preisen, während der Code
  Haiku abrechnete. Beides fiel erst beim Aufräumen dieser Migration auf.
  ⚠️ **Test-Fixtures lesen ebenfalls aus `config`**, damit sie nicht wieder
  auseinanderlaufen. Zwei bewusste Ausnahmen: `test_cost_tracker.py` prüft
  `MODEL_PRICING` anhand seiner Schlüssel (mit `config` wäre der Test tautologisch),
  und `test_utils.py` reicht das Modell nur generisch durch.

## Wichtige Designentscheidungen
- Provider-Hierarchie: Capital.com (alleiniger OHLC-Provider) → Finnhub (Fundamentals, gecacht) — yfinance seit Sprint 3 entfernt (2026-07-09)
- Guardrails: jede Analyse braucht min. 2 Belege je Score-Dimension
- Die acht Score-Dimensionen (Market Environment, Company Quality, Valuation, Momentum,
  Risk, Sector Trend, Catalyst, Policy Risk) bleiben **erhalten und werden einzeln
  persistiert** — eine Gewichtung zu einem Gesamtscore findet **im Code nicht statt**
  und ist bewusst Aufgabe von Sprint 3D (Spec § 5.7). Seit Plan 3b sind `score_total()`
  und `config.DIMENSION_WEIGHTS` entfernt; der Sortierschlüssel ist `rank_score`
  (`analysis_strength × tech_strength`, § 5.2/5.4), keine gewichtete Summe. Wer hier
  wieder eine Gewichtung einführt, unterläuft genau die Trennung, die 3D später messen
  soll — welche Dimension predictet, statt es per Annahme festzulegen.
  ⚠️ **`analysis_strength()` (Spec § 5.2) zählt `momentum` anders als die anderen
  sieben Dimensionen.** Die aktiven v2-Prompts (`deep_analysis_v2.txt`,
  `commodities_crypto_v2.txt`) verlangen für sieben Dimensionen **trade-relative**
  Polarität ("hoch = gut für DIESEN Trade", `valuation: 10` heisst bei einem Short
  „teuer genug für einen Short"). `momentum` bleibt die eine **absolute** Ausnahme
  (tiefer Wert = bärisch), weil sowohl die Guardrails (`src/guardrails.py`) als auch
  der Prompts eigene Hard-Rule (`direction='short'` verlangt `momentum <= 4.0`) darauf
  aufbauen. Die v2-Prompts sagen an dieser einen Stelle bewusst nicht „momentum ist die
  Ausnahme" (Regel 10: Prompts werden nicht mehr geändert, nur der Code passt sich an) —
  wer den Prompt liest, muss diesen Absatz hier kennen, sonst wirkt die Formel
  widersprüchlich zum Prompt-Wortlaut. Gefunden im Plan-3b-Abschlussreview (PROJECT_STATUS
  C.13), vorher zählte jeder Short verkehrt herum.
- Long/Short getrennt tracken und optimieren
- Übersprungene Aktien: learnable=False, nie ins Lernmodul
- SIMULATION_ONLY=True: niemals echte Orders
- ATR-Mindest: SP500_MIN_ATR_PCT = 2.0
- MAX_HOLD_DAYS = 5, HOLD_TARGET = "intraday"
- Timezone: TZ="Europe/Berlin" in Bash, ZoneInfo("Europe/Berlin") in Python
- ⚠️ Prompts sind **nur über den Dateinamen** versioniert (`deep_analysis_v2.txt`), und die
  Version steht fest im Modul-Import. **A/B-Testing gibt es nicht** — die Tabelle
  `prompt_versions` wird von `init_schema()` angelegt und nirgends gelesen oder
  geschrieben (verifiziert 2026-08-09). Ein Wechsel ist eine Code-Änderung, kein
  Datenbank-Eintrag. Gehört zu Sprint 3D.
  ⚠️ Seit Plan 3a ist **`deep_analysis_v2` aktiv**, seit C.15 (2026-08-19) ist es für
  Commodities/Crypto **`commodities_crypto_v3`** (v2 lief nur bis dahin) — die v1/v2-
  Dateien liegen unangetastet daneben (Regel 10: Prompts werden nie überschrieben, neue
  Versionen sind neue Dateien). Wer eine alte Version ändert, ändert nichts am Verhalten.
- **Phase 3 analysiert gebatcht nach Sub-Sektor, nicht je Ticker.** Ein Sub-Sektor ist
  eine **unteilbare Einheit**, die per First-Fit-Decreasing in Batches bis
  `BATCH_SIZE_DEEP` gepackt wird — zerrissen wird er nur, wenn er den Wert allein
  überschreitet. Grund: die Vergleichbarkeit innerhalb eines Prompts ist der Punkt der
  Übung; ein halber Sub-Sektor in zwei Calls verliert genau die.
  ⚠️ **`BATCH_SIZE_DEEP = 8` ist ein unbestätigter Startwert, kein Messergebnis.**
  Ein abgeschnittener Batch (`stop_reason == "max_tokens"`) gilt als Fehler und wird
  **nie** teilverwertet; der Fehlerpfad ist einmal wiederholen → einmal halbieren →
  aufgeben.
  ⚠️ **Die Ausgabe-Decke (`max_tokens`) kostet für sich genommen nichts** — abgerechnet
  wird, was erzeugt wird. Ein zu knapper Wert kostet dagegen den **ganzen** Call. Deshalb
  ist der Pro-Ticker-Wert grosszügig und die Reserve klein: ein **fester** Reserve-Term
  macht die Formel regressiv (er verwässert den Pro-Ticker-Wert, je grösser der Batch),
  und genau das war der C.9-Befund. Ein Test pinnt die Eigenschaft:
  `max_tokens_for_batch(n) / n >= TOKENS_PER_TICKER_DEEP` für alle n.
  ⚠️ **Nach einer Kappung nie identisch wiederholen** — gleiche Eingabe plus gleiche
  Decke ergibt dieselbe Kappung. Dafür gibt es `BatchTruncatedError`; die Wiederholung
  und die Hälften laufen mit angehobener Decke. Seit der Formel-Korrektur ändert
  Halbieren den Platz **pro Ticker** nicht mehr (früher tat es das nur zufällig über den
  4096er-Boden), es wäre ohne diesen Punkt wirkungslos.
- ⚠️ **`call_claude()` setzt kein `thinking`-Feld — und genau das bedeutet unter
  Claude 5 das Gegenteil von früher.** Bei `claude-sonnet-4-6` hiess Weglassen „kein
  Denken", bei `claude-sonnet-5`/`claude-opus-5` heisst es „**adaptives Denken an**".
  Denk- und Antworttokens teilen sich dieselbe `max_tokens`-Decke, jede vor dem
  2026-08-20 kalibrierte Decke ist deshalb neu zu messen (C.18). **Wer hier wieder ein
  Modell wechselt, wechselt implizit auch das Token-Budget.**
  ⚠️ **Adaptives Denken ist nicht deterministisch — ein sauberer Lauf beweist nichts.**
  In der C.18-Messreihe kappte Phase 3 nur im ersten, Phase 0 nur im zweiten und
  Phase 3b nur im dritten von vier Läufen, jeweils bei identischem Code und identischer
  Decke. Deshalb ist die **Erkennung** das eigentliche Netz und die angehobene Decke nur
  die Optimierung, die sie selten auslöst: Batch-Pfade über `BatchTruncatedError`,
  Einzelcalls (`trend_analyzer`, `market_context`, `revalidation`,
  `deep_analysis.run_policy_monitor`) über `utils.call_claude_retry_on_truncation()`.
  **Ein neuer Claude-Aufrufer ohne `stop_reason`-Prüfung ist ein Bug**, kein
  Stilfehler — bei `trend_analyzer` kam eine Kappung als `JSONDecodeError` an und riss
  laut Spec § 3 den ganzen Lauf mit.
  ⚠️ `run_policy_monitor` wurde beim ersten Durchgang **übersehen** und erst bei einer
  vollständigen Aufstellung aller `call_claude`-Aufrufstellen gefunden — es lief in
  fünf Messläufen sauber und sah deshalb unauffällig aus, hatte aber mit 3072 die
  knappste Decke im Projekt. **Wer hier ein Modell wechselt, zählt die Aufrufstellen ab**,
  statt sich auf saubere Läufe zu verlassen. Haiku-Aufrufer (`broad_scan`,
  `portfolio_check`) sind nicht betroffen: dort ist Denken ohne `thinking`-Feld aus.
  ⚠️ Jeder Versuch wird **gebucht**, auch der verworfene gekappte. Ihn auszulassen wäre
  die Fehlerklasse, die hier schon zweimal Kosten verschleiert hat (Cache-Doppelabzug,
  `web_search_calls`).
- **Phase 3b (Commodities/Crypto) analysiert seit C.15 (2026-08-19) gebatcht nach
  `asset_class`, nicht mehr je Asset.** Zwei Batches (Commodities: Gold/Silber/Öl,
  Crypto: BTC/ETH/SOL/XRP) statt sieben Einzelcalls — dieselbe Begründung wie beim
  Phase-3-Sub-Sektor-Batching: der gemeinsame Kontext (Makro-Linse vs. Fear&Greed/
  Dominance) ist nur innerhalb einer Klasse wirklich gemeinsam. **Ändert nichts an
  Spec §6** (alle sieben Assets laufen immer, kein Trichter, kein Cutoff) — Batching
  betrifft nur die Call-Struktur, nicht die Auswahl.
  ⚠️ **Der Fehlerpfad ist bewusst schlanker als bei Aktien:** einmal wiederholen (bei
  einer Kappung mit doppelter Decke wie in `deep_analysis.py`), dann aufgeben — **kein
  Halbieren**. Bei höchstens 4 Assets pro Batch spart eine weitere Aufteilung kaum noch
  Call-Overhead. Trade-off: ein zweimal fehlgeschlagener Batch verliert bis zu 4 Assets
  auf einen Schlag, vorher war jedes Asset unabhängig.
- ⚠️ `evidence_quality: "thin"` umgeht die Zwei-Belege-Pflicht der Guardrails — aber
  **nur bei exakt diesem Wert**. Ein fehlendes Feld (v1-Ergebnis) oder ein unbekannter
  Wert fällt auf die strenge Regel zurück. Eine thin-Dimension wird **behalten**, nicht
  weggelassen: stilles Weglassen war in diesem Projekt wiederholt eine Diagnose-Falle.
- ⚠️ **`usage`-Felder, die das SDK nicht selbst modelliert, sind zweimal eine Falle** —
  beide Male hat es dieselbe Zahl still auf 0 gehalten:
  1. `server_tool_use` ist ein **`dict`**, kein Objekt (`Usage.model_config` hat
     `extra="allow"`, Pydantic reicht rohes JSON durch). `getattr()` darauf liefert immer
     den Default.
  2. Im **gestreamten** Pfad fehlt das Feld ganz — `get_final_message()` liefert
     `usage.server_tool_use == None`, obwohl dieselbe Antwort `server_tool_use`-Content-
     Blöcke trägt. Die **Blöcke sind die Wahrheit**, das usage-Feld nur die Zählung.
  Alle vor dem 2026-08-17 ausgewiesenen `web_search_eur`-Werte sind dadurch zu niedrig.
  ⚠️ Lehre über den Einzelfall hinaus: **eine kaputte Messung sieht einem kaputten
  Verhalten zum Verwechseln ähnlich.** Aus „0 Websuchen" plus konkreten Nachrichten in
  der Antwort war der naheliegende Schluss „das Modell erfindet Quellen" — und er war
  falsch. Entschieden hat es erst eine unabhängige Wahrheitsquelle (die Content-Blöcke),
  nicht die Plausibilität der Geschichte.
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
- ⚠️ **Die Indikatoren sind pro Tag konstant — sie können sich im Tagesverlauf nicht
  ändern.** Jede Indikator-Funktion in `_process_ticker()` bekommt ausschliesslich `df`,
  und `df` ist `db.load_price_history_from_db(...)`, also **nur finale Tagesbars bis
  D-1**. Der Live-Kurs geht getrennt in `td["price"]` und wird nie nach
  `technical_indicators` geschrieben. Mehrere Läufe am selben Tag (`pre_market` 15:00,
  `trade_proposals` 16:10) schreiben deshalb per `INSERT OR REPLACE` auf `(ticker, date)`
  **wertgleiche** Zeilen. Genau das machte den `close`-Lauf um 22:30 überflüssig — die
  Annahme „abends stehen aktuellere Indikatoren drin" ist konstruktionsbedingt falsch.
- ⚠️ **Was eine Prediction wusste, steht IN der Prediction — nicht im Cache.**
  `fundamentals_cache` hält nur eine Zeile je Ticker (`INSERT OR REPLACE`,
  7-Tage-TTL) und hat **keine Historie**. Fundamental-Rohwerte, Analysten-Konsens
  **samt Periode** und `relative_strength` werden deshalb seit 2026-08-20 in
  `predictions` eingefroren (C.20). **Wer ein neues Merkmal einführt, das in die
  Entscheidung einfliesst, friert es dort mit ein** — sonst ist es für Sprint 3D
  nicht vorhanden, und zwar rückwirkend unheilbar.
  ⚠️ Die Analysten-Periode wird **aufgezeichnet, nicht durchgesetzt**: welche
  Frist einen Konsens veralten lässt, soll 3D messen. Wer hier ein
  Verfallsdatum hart einbaut, nimmt genau die Messung vorweg.
- ⚠️ **`config.LEARNING_RETENTION_DAYS` gilt für vier Tabellen gemeinsam**
  (`news_summaries`, `trend_analyses`, `skipped_tickers`, `cutoff_log`). Wer eine
  davon auf eine eigene Frist setzt, wiederholt den Fehler, der `news_summaries`
  auf 30 Tage stellte, während das zugehörige Label dauerhaft blieb. `cutoff_log`
  fällt bewusst darunter: es trägt den **Selektions-Bias** — ohne ihn trainiert 3D
  nur auf Tickern, die den Trichter passiert haben.
- ⚠️ **Für 3D wichtig, und KEIN Bug:** die `technical_indicators`-Zeile mit `date = T` ist
  aus Bars bis **T-1** berechnet, ist gegenüber ihrem eigenen Datumslabel also um einen
  Handelstag „versetzt". Das ist für Prediction-Features genau richtig: der Schlusskurs
  von Tag T darf nicht in die Vorhersage für Tag T einfliessen, sonst ist es Leakage. Wer
  das später als Off-by-one „korrigiert", baut sich ein Modell, das in der Auswertung
  glänzt und im Livebetrieb versagt. Beim 3D-Entwurf bewusst mitdenken.
- ⚠️ **Sidecar-Invariante: neue Werte laufen *neben* `td`, nie darin.** Das `td`-Dict aus
  `_process_ticker()` wird in **drei live laufenden** Claude-Prompts `json.dumps`'t:
  `deep_analysis` (seit Plan 3a als `snapshot` im Batch-Eintrag), `commodities_crypto`
  und über `main.py`s `snapshots` auch `portfolio_check`. Wer dort einen Schlüssel
  hinzufügt, ändert stillschweigend alle drei.
  ⚠️ Zwei Module sind **bewusst nicht** in dieser Liste: `broad_scan` setzt seine Nutzlast
  über `_payload_for_ticker()` explizit zusammen statt `td` durchzureichen (R23), und
  `quick_filter` ist seit Plan 2 toter Code — im Repo, aber nicht in der Pipeline.
  Deshalb reist `collect()` mit einem dritten Rückgabewert: dem **Sidecar**
  (`premarket_change_pct` + die vier Technik-Signal-Werte), und die 29 Plan-1-Indikatoren
  liegen in einem separaten `extra_indicators`-Dict, das erst unmittelbar vor
  `_persist_indicators()` dazukommt. Anlass war ein echter Vorfall: Plan 1 schickte 29
  Werte (~250 Tokens je Ticker) unbemerkt in die Prompts. Ein Test pinnt die exakte
  Schlüsselmenge von `_process_ticker()`.
- **Phase 1 ist Finnhub-frei.** Sie liest `fundamentals_cache` und ruft nichts ab; das
  Nachladen bei Cache-Miss ist Phase 2b (`run_phase_2b()`, läuft zwischen Cutoff und
  Phase 3) und trifft **nur die Kandidaten**. ⚠️ Phase 2b macht **zwei** Dinge, die
  zusammengehören: Cache füllen **und** die Werte in die `td`-Dicts zurückspiegeln — ohne
  Schritt 2 wärmte sie nur den Cache für morgen, während der heutige Phase-3-Prompt
  weiter `None` sähe. Dort entsteht laut Spec § 18.1f auch die `medium`/`high`-Einstufung
  von `data_quality`; eine Rückstufung auf `low` ist ausgeschlossen (der low-Skip gehört
  allein in Phase 1). `get_earnings_calendar()` kommt im
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

⚠️ **Der Workflow fährt bewusst NUR die Sommerzeit** (Entscheidung 2026-08-18, TODO
steht im `schedule`-Block von `analyze.yml`). Ab der Rückstellung auf CET laufen
`pre_market` und `weekly` eine Stunde früher als dort notiert, und
`trade_proposals` fällt ganz aus. Das ist bekannt und aufgeschoben, kein Versehen.
Einzige Ausnahme: `final_close` hängt an der UTC-Bar-Grenze und gilt ganzjährig.

⚠️ Für `trade_proposals` ist DST **nicht** nur eine Verschiebung: der Lauf hängt an
der **US-Eröffnung** (10:10 America/New_York), nicht an Berlin. Geplant ist derzeit
nur der EDT-Slot (14:10 UTC = 16:10 Berlin); der EST-Slot (15:10 UTC) ist bewusst
auskommentiert. Der Workflow prüft trotzdem weiter `TZ=America/New_York date +%z`
und **überspringt** den Slot, sobald New York auf EST steht — lieber kein Lauf als
einer zur falschen Zeit. Maßgeblich ist bewusst die US-Zeitzone: EU und USA schalten
an verschiedenen Wochenenden um. Ohne diese Prüfung lief der Lauf von November bis
März **vor** der Eröffnung, und der Opening-Gap-Check verglich zwei Pre-Open-Kurse.

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
`docker compose run --rm -v /tmp/dbtest:/app/data trading-harry --run-type final_close`

## Sprint-Stand
**Vor jeder Implementierung `docs/superpowers/specs/PROJECT_STATUS.md` lesen** — dort
steht der verbindliche Stand inklusive aller Sprint-3-Teilschritte, der offenen Bugs
und der getroffenen Entscheidungen. Kurzfassung:

- **Sprint 3B** teilweise: Plan 1 (Fundament) erledigt; **Plan 2 (Pipeline-Umbau) zu
  20 von 20 Tasks umgesetzt** — die Commits liegen **direkt
  auf `main` und sind gepusht**. Einen Branch `sprint3b/plan2-pipeline-umbau` gibt es
  weder lokal noch remote (`git ls-remote --heads origin` kennt nur `refs/heads/main`,
  geprüft 2026-08-03). Offen: Task 20, ein Gesamt-Review über die Plan-2-Commits
  und die Live-Verifikation. ✅ **`analyze.yml` seit 2026-08-18 wieder aktiv** (manuell
  re-aktiviert, erster Lauf am selben Tag erfolgreich). Der Plan-2-Code **ist am 2026-08-04 dreimal gelaufen** (pre_market, trade_proposals,
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
    ✅ **abgeschlossen**: 13/13 Tasks plus Abschluss-Review mit vier behobenen Befunden.
    Der Trichter ist live — `quick_filter` ist aus `run_pipeline()` verschwunden,
    `broad_scan` + `cutoff_candidates` (`MAX_DEEP_ANALYSIS` 80 → 50) + `run_phase_2b`
    laufen, gemessen gegen echte Daten: 3,3551 EUR, kein `CostCapExceeded`, güns­tiger als
    der alte Weg. `run_weekly()` füllt `fundamentals_cache` + `earnings_next_date` fürs
    ganze Universum, `FinnhubProvider` drosselt sich auf 60 **Requests**/Minute.
    Stand: PROJECT_STATUS **C.7** (zwölf Umsetzungs-Befunde) und **C.8** (Review).
  - **Plan 3 (Analyse & Ranking)** — in **3a** und **3b** geteilt:
    - **Plan 3a (Batch-Tiefenanalyse)** —
      `…/plans/2026-08-16-analyse-pipeline-plan3a-batch-tiefenanalyse.md`,
      ✅ **11/11 Tasks umgesetzt und live verifiziert.** Phase 3 batcht nach
      Sub-Sektor, v2-Prompts sind aktiv, `call_claude()` streamt. Der erste Testlauf
      hatte `MAX_TOKENS_DEEP` widerlegt (C.9); nach der Neukalibrierung
      (`TOKENS_PER_TICKER_DEEP` 900 → 2500, `BATCH_TOKEN_RESERVE` 2000 → 200) trat
      im Verifikationslauf **kein einziges** `max_tokens` mehr auf, 12 von 12
      Kandidaten analysiert, Phase 3 bei **0,0204 EUR je Ticker** — der angezielte
      Kostenhebel (Ziel 0,034 EUR) ist damit **unterboten**, nicht nur erreicht.
      Abschluss-Review über `e3dc5a7..HEAD` durchgeführt: keine kritischen Befunde,
      vier Doku-/Prompt-Konsistenzpunkte behoben. Stand: PROJECT_STATUS
      **C.9–C.11**.
    - **Plan 3b (Ranking)** —
      `…/plans/2026-08-17-analyse-pipeline-plan3b-ranking.md`,
      ✅ **12/12 Tasks umgesetzt, Gesamt-Review + Fix-Welle + Re-Review sauber, live
      verifiziert.** `rank_score`/`candidate_class` ersetzen `probability_pct` als
      Sortier-/Klassifikationslogik, ein eigener Divergenz-Mail-Abschnitt, der C.1-Fix
      ist mitgenommen. Der Gesamt-Review fand zwei Critical-Befunde an den Nähten
      zwischen Plan 3a und 3b (Short-Polarität in `analysis_strength()`,
      `candidate_class`-Verlust beim 16:10-Ablösen) — beide plus drei Important-Befunde
      in einer Welle behoben. Stand: PROJECT_STATUS **C.13**.
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
