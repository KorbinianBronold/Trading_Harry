# PROJECT_STATUS.md — Shares_Future (Trading_Harry)

**Zuletzt aktualisiert:** 2026-07-27
**Aktueller Branch:** main
**Letzter Merge:** Sprint 2 / Plan 1 (2026-05-22) — Sprint 3 in Arbeit, Roadmap s. Abschnitt 2

---

## 1. Was gebaut wurde

### Sprint 1 — Foundation (abgeschlossen, gemerged 2026-05-20)
**159 Tests, 89.62% Coverage.**

| Modul | Was gebaut |
|---|---|
| `config.py` | Alle Konstanten, Ticker-Listen (MVP 20 + Commodity + Crypto), DIMENSION_WEIGHTS, Capital.com-Credentials |
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
| `main.py` — position_check | `run_position_check()`: Capital.com GET /positions → Claude → Position-Check-Mail (**wird in Sprint 3B wieder entfernt**) |
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
| 3B | Cron-Struktur + Pipeline-Umbau | 🟡 **Plan 1 (Fundament) vollständig abgeschlossen** (2026-07-29, Tasks 1–14); Plan 2 (Pipeline-Umbau) noch nicht geschrieben |
| 3C | Ranking-Überarbeitung | 📋 spezifiziert, Implementierung offen |
| 3D | Learning Modul | ⚠️ **Platzhalter — Planungssession ausstehend** |
| 3E | Human-in-the-Loop | ⚠️ **Platzhalter — Planungssession ausstehend** |
| 3F | Volle 500-Ticker-Skalierung | ⚠️ **Platzhalter — Planungssession ausstehend** |

---

## Sprint 3B — Cron-Struktur + Pipeline-Umbau

### B.1 — Ziel-Cron-Struktur

| Run-Type | Zeit (Berlin) | Änderung | Kosten (geschätzt) |
|---|---|---|---|
| `pre_market` | 15:00 Mo–Fr | **unverändert** — volle Pipeline Phase 0–5 | ~3,20 EUR (500 Ticker) |
| `trade_proposals` | 16:10 Mo–Fr | **NEU** — ersetzt `evaluate` vollständig (anderer Zweck, s. B.2) | ~1,00 EUR |
| `close` | 22:30 Mo–Fr | **vereinfacht** (s. B.5) | ~0,00 EUR |
| `weekly` | So 20:00 | Struktur unverändert, **Inhalt erweitert** (s. B.9) | ~0,00 EUR |
| ~~`midday`~~ | — | **komplett entfernen** | — |
| ~~`evaluate`~~ | — | **ersetzt durch `trade_proposals`** | — |
| ~~`position_check`~~ | — | **komplett entfernen** | — |

**`pre_market` bleibt explizit unverändert.** Der frühere Plan, ihn in `pre_open` (nur Phase 0+1)
und `post_open` (Phase 0–4) aufzuspalten, ist verworfen.

**Kostenwirkung:** alt ~6,60 EUR/Tag → neu ~4,20 EUR/Tag (bei 500 Tickern), also
~139 EUR → **~88 EUR/Monat**. Das trifft das für Sprint 3F gesetzte ~90-EUR-Ziel bereits
ohne den technischen Pre-Filter aus 3C — der schafft zusätzlichen Puffer.

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

| Schritt | Was passiert |
|---|---|
| 1 | Frische Kurse für **ALLE** Ticker (SP500 + Commodities/Crypto) von Capital.com laden und in `price_history` schreiben — nicht nur für die Top-Listen |
| 2 | Nur die `pre_market` **Top 10 Long + Top 10 Short + alle 7 Commodities/Crypto** erneut durch Phase 3 (Tiefenanalyse) schicken — nicht die komplette Ticker-Liste |
| 3 | `probability_pct` vorher (`pre_market`) vs. nachher (`trade_proposals`) pro Ticker vergleichen |
| 4 | Zusätzliche Checks (s. B.3) |
| 5 | Update-Mail: Vorher/Nachher-Vergleich pro Ticker (**bestätigt / geschwächt / gedreht / unverändert**) plus die neuen Checks |
| 6 | Alle Predictions dieses Runs ebenfalls in `predictions` speichern — mit `run_type='trade_proposals'`, damit das Learning Modul später `pre_market` vs. `trade_proposals` vergleichen kann |

### B.3 — Neue Checks in `trade_proposals`

| Check | Beschreibung | Wirkung |
|---|---|---|
| **Sektor-Momentum (hybrid)** | Zwei unabhängige Signale, s. Detailabschnitt unten | Hart **nur bei Übereinstimmung**, sonst weiche Warnung |
| **Relative Stärke** | Performance des Tickers vs. seinem Sub-Sektor | Score-Input |
| **Marktbreite** | Advancing/Declining-Ratio im S&P 500 | Kontext / Warnung |
| **VIX-Level** | >25: nur noch `confidence='high'`-Signale ausgeben. >35: **keine neuen Long-Signale** | Hartes Filter-Kriterium |
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
| **`pre_market` vs. `trade_proposals`** | Trefferquote und Ø P&L getrennt nach `run_type`. Beantwortet die Kernfrage von 3B: verbessert der 16:10-Run die Signale tatsächlich, oder verursacht er nur Kosten? |
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

### B.13 — Phase 3 parallelisieren *(Entscheidung 2026-07-29, gehört in Plan 2)*

**Entschieden:** Die Parallelisierung von Phase 3 wird **nicht** nach 3F verschoben,
sondern in Plan 2 gezogen. Grund: sie entscheidet mit, ob die geplante Cron-Struktur
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
die Rechnung. Für 3F braucht es zusätzlich ein kleineres `MAX_DEEP_ANALYSIS`, ein
günstigeres Modell für Phase 3 oder einen deutlich schärferen Pre-Filter aus 3C.

### B.12 — Stand der Umsetzung: Plan 1 fertig, Plan 2 offen

**Plan 1 (Fundament) ist abgeschlossen** (2026-07-29, Tasks 1–14, Plan-Datei
`docs/superpowers/plans/2026-07-27-sprint3b-plan1-fundament.md`). Er war
ausschliesslich **additiv**: die Pipeline läuft unverändert weiter, es kamen nur
neue Tabellen, Helper und der Phase-0b-Call dazu.

Geliefert: `sectors` / `ticker_sectors` / `ticker_status` / `guardrail_rejects` /
`sector_momentum`, `SECTOR_ALIASES`-Normalisierung, Skip-Zähler mit Auto-Retry,
beide Momentum-Signale, Markt-Kontext (Phase 0b), Gap-Erkennung, B-05.

**Plan 2 (Pipeline-Umbau) ist noch nicht geschrieben.** Er umfasst B.1, B.2, B.4,
B.5, B.6, B.9 sowie die **Anwendung** der in Plan 1 beschafften Daten — insbesondere
die D9-Guardrail-Logik (hartes Reject nur bei zwei übereinstimmenden Signalen,
sonst weiche Warnung mit `enforced=0`) und `config.SECTOR_GUARDRAIL_STRICT`.

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
(~90 EUR/Monat angestrebt). Da `MAX_DEEP_ANALYSIS = 80` die teure Phase 3 ohnehin deckelt,
wirkt der Pre-Filter primär auf die Phase-2-Kosten und die Laufzeit — der große Hebel für 3F
ist trotzdem, dass die 80 Phase-3-Slots mit den *besten* Kandidaten gefüllt werden statt mit
zufällig durchgerutschten.

---

## Sprint 3D — Learning Modul

⚠️ **Noch nicht ausgearbeitet — braucht eine eigene Planungssession, bevor die Implementierung
beginnt.**

Grob umrissen (aus früheren Notizen, **nicht** als Spezifikation zu verstehen):
- Liest `outcomes` getrennt nach Long / Short
- Hit-Rate, Ø P&L, Ø Score bei Treffern vs. Fehltreffern
- Schreibt `data/learnings.json`
- `learnable=False`-Predictions nie ins Lernmodul
- Übernimmt die TP/SL-Auswertung aus `close` (s. B.6)
- Optimiert die Gewichte des `ranking_score` aus 3C
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

**Hochrechnung auf die 80 Slots aus `MAX_DEEP_ANALYSIS`** — der Deckel greift ab
~100 Tickern, die Tickerzahl selbst ist also *nicht* der Engpass:

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
**Entschieden am 2026-07-29: die Parallelisierung wird nach Plan 2 vorgezogen** —
Details, Zahlen und die beiden Thread-Safety-Haken in Abschnitt B.13.

Das löst allerdings **nur die Laufzeit, nicht die Kosten**; dafür braucht es entweder
ein kleineres `MAX_DEEP_ANALYSIS`, ein günstigeres Modell für Phase 3, oder den
technischen Pre-Filter aus 3C mit deutlich schärferer Wirkung.

**Actions-Minuten:** Das Repo ist derzeit **public**, damit sind die Minuten unbegrenzt
und kostenlos. Geplant ist der Wechsel auf privat — dann greifen 2 000 Minuten/Monat
(Free-Tarif). Bei 95 min/Tag × 22 Handelstage wären allein `pre_market` ≈ 2 090 Minuten
fällig, also über dem Kontingent. Rechnung s. B.13.

---

## 3. Bekannte Bugs (offen)

| # | Datei | Bug | Schwere | Geplant in |
|---|---|---|---|---|
| B-03 | `config.py:SP500_FULL_TICKERS` | Ist Stub (= MVP-Liste), `USE_FULL_SP500=true` würde nur 20 Ticker laufen lassen | Mittel | Sprint 3F |

**Behoben (2026-07-29, im ersten echten Gesamtlauf gefunden):**

| # | Datei | Bug | Fix |
|---|---|---|---|
| B-10 | `.github/workflows/analyze.yml`, `main.py` | Der Upload der `tracking.db` nach Release `db-latest` hing an `if: success()`. Ein fehlgeschlagener Mailversand beendet den Analyse-Schritt mit Exit 1 → **die DB wurde nicht hochgeladen und die komplette Arbeit des Laufs war verloren**, obwohl sie längst committet war. Im Lauf vom 2026-07-29 wären so 7 Trend-Analysen, der Marktkontext, 9 Predictions, das Sektor-Mapping und die Kostenzeile weggeworfen worden — für 3,31 EUR. Nicht hypothetisch: der SendGrid-Key antwortet aktuell mit 401. | Upload auf `if: always()` umgestellt (der Wochen-Snapshot bleibt bewusst auf `success()`). Zusätzlich in `main.py`: `send_daily_email` wird gefangen, loggt ausdrücklich „Analyse persistiert, nur Mailversand scheiterte" und wirft `MailDeliveryError` — der Job bleibt rot, aber die Ursache ist nicht mehr mit einem Analysefehler zu verwechseln. |

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
