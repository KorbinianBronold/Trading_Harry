# PROJECT_STATUS.md — Shares_Future (Trading_Harry)

**Zuletzt aktualisiert:** 2026-07-13  
**Aktueller Branch:** main  
**Letzter Merge:** Sprint 2 / Plan 1 (2026-05-22) — Sprint 3 in Arbeit, Teilfortschritt s. Abschnitt 2

---

## 1. Was gebaut wurde

### Sprint 1 — Foundation (abgeschlossen, gemerged 2026-05-20)
**159 Tests, 89.62% Coverage.**

| Modul | Was gebaut |
|---|---|
| `config.py` | Alle Konstanten, Ticker-Listen (MVP 20 + Commodity + Crypto), DIMENSION_WEIGHTS, Capital.com-Credentials |
| `src/db.py` | Vollständiges SQLite-Schema: price_history, technical_indicators, fundamentals, predictions, outcomes, skipped_tickers, trend_analyses, market_context, cost_tracking, prompt_versions, news_summaries, position_recommendations |
| `src/providers/base.py` | DataProvider-Interface |
| `src/providers/yfinance_provider.py` | yFinance-Implementierung (primary in Sprint 1) |
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

**Intraday-Focus:** ATR_MIN=2.0, MAX_HOLD_DAYS=5, HOLD_TARGET="intraday" — in Sprint 1 late gesetzt.

---

### Sprint 2 / Plan 1 — Capital Provider + DB Incremental + Position Check (abgeschlossen, gemerged 2026-05-22)

| Modul | Was gebaut |
|---|---|
| `src/providers/capital_provider.py` | CapitalComProvider: lazy session auth (CST + X-SECURITY-TOKEN), `get_price_history()`, `get_ohlc_after()`, `get_premarket_price()`, `get_open_positions()`, `get_closed_positions()`, TICKER_MAP für epics |
| `src/db.py` — Ergänzungen | `fundamentals_cache`-Tabelle (UNIQUE ticker, 7-Tage-TTL), `insert_price_bar_if_missing()`, `load_price_history_from_db()`, `get_cached_fundamentals()`, `save_fundamentals_cache()`, `update_outcome_close()`, Migration-Guards (`_apply_migrations`) |
| `src/providers/finnhub_provider.py` | `get_fundamentals()` implementiert (PE, Forward-PE, Market-Cap, D/E, Sector, Analyst-Consensus) — Finnhub Free, 403-Bug bei `price_target` entfernt |
| `main.py` — position_check | `run_position_check()`: Capital.com GET /positions → Claude → Position-Check-Mail |
| `setup/historical_loader.py` | 3-Jahres-Pull aller SP500-Ticker via Capital.com; Flags: `--all`, `--full-sp500`, `--tickers` |
| `config.py` | `USE_FULL_SP500`-Flag, `SP500_FULL_TICKERS` (noch Stub = MVP-Liste), `CAPITAL_COM_IDENTIFIER` |
| `analyze.yml` | `CAPITAL_COM_IDENTIFIER`-Secret hinzugefügt, DST-bezogenes Zeit-Matching (mit bekanntem Bug, s.u.) |
| Timezone-Fix | `ZoneInfo("Europe/Berlin")` überall in Python, `TZ="Europe/Berlin"` in Bash |
| Briefing-Box | "Was heute zählt" in Daily-Mail |
| Error-Mail | `send_error_email()` bei Exception im Main-Orchestrator |

**Provider-Hierarchie ab Sprint 2:** Capital.com (OHLC primary) → Finnhub (Fundamentals, gecacht) → yFinance (Fallback wenn Capital.com nicht verfügbar).

---

### Sprint 3 — Fortschritt (in Arbeit, Stand 2026-07-13)

Bereits erledigt, obwohl noch keine Sprint-3-Abschlussmeldung erfolgt ist:

| Was | Commit | Details |
|---|---|---|
| yFinance komplett entfernt | `d17c2f5` (2026-07-09) | `src/providers/yfinance_provider.py` gelöscht, `yfinance` aus `requirements.txt`, `config.py` (`YFINANCE_*` → `CAPITAL_COM_BATCH_PAUSE`), `main.py` (`run_pipeline()`, `run_close()`, `run_evaluate()` instanziieren jetzt unconditional `CapitalComProvider()`), Tests entsprechend angepasst. Capital.com ist seither alleiniger OHLC-Provider ohne Fallback. |
| DST-Bug (ehem. Bug B-01) mitgefixt | `d17c2f5` (2026-07-09) | `analyze.yml`: Run-Type-Erkennung matcht jetzt `github.event.schedule`-String direkt per `case`, statt Uhrzeit zu parsen. Damit auch Bug B-04 (Kommentar/Code-Mismatch) hinfällig. |
| Toter Code entfernt | `e198520`, `b3d743c` (2026-07-09) | `src/providers/paid_provider.py` + zugehöriger Test gelöscht (unbenutzter Stub, nicht Teil der dokumentierten Architektur). |

Noch offen aus dem ursprünglichen Sprint-3-Scope: Punkte B, E, F, G unten sowie Bugs B-03, B-05, B-06.

## 2. Was in Sprint 3 noch offen ist

### B — Cron-Struktur umbauen
Aktuelle Struktur (veraltet):

| Run-Type | Cron (UTC) | Berlin (CEST) |
|---|---|---|
| pre_market | 0 13 * * 1-5 | 15:00 |
| evaluate | 0 14 * * 1-5 | 16:00 |
| midday | 0 17 * * 1-5 | 19:00 |
| position_check | 30 15 * * 1-5 | 17:30 |
| close | 30 20 * * 1-5 | 22:30 |
| weekly | 0 18 * * 0 | 20:00 |

**Neue Ziel-Struktur:**
- `evaluate` streichen (wird in `close` integriert)
- `midday` streichen (zu spät, kein Mehrwert nach 19:00 Berlin)
- `pre_open` neu (15:00 Berlin): erster Tagesrun, nur Phase 0+1 (Trend-Analyse + Datenabruf), kein Ranking, keine Mail, ~0,20€
- `post_open` (16:15 Berlin): Hauptrun, Phase 0–4, Mail (bisheriger pre_market)
- `close` (22:30 Berlin): DB-Pflege + TP/SL-Evaluierung (bisher separate evaluate-Run)

### D — SendGrid Status prüfen
E-Mail-Versand ist implementiert aber nie live getestet. Vor erstem echten Lauf sicherstellen:
- SendGrid ist aktiv und getestet. SENDGRID_API_KEY, EMAIL_FROM, EMAIL_TO sind in GitHub Secrets gesetzt und verifiziert.
- Kein Handlungsbedarf in Sprint 3.
- Test-Mail via `python -c "from src.email_sender import ..."` senden

### E — `learning_module.py` bauen
- Liest `outcomes`-Tabelle getrennt nach Long / Short
- Berechnet Hit-Rate (korrekte Richtung), Ø P&L, Ø Score bei Treffern vs. Fehltreffer
- Schreibt `data/learnings.json` mit Format `{long: {...}, short: {...}}`
- Wird von `ranking.py` geladen und als Kontext in Deep-Analysis-Prompts eingebaut
- `learnable=False`-Predictions nie ins Lernmodul

### F — `prompt_optimizer.py` bauen
- Liest `prompt_versions`-Tabelle aus SQLite
- Vergleicht Long/Short-Accuracy zwischen Prompt-Versionen (A/B-Test)
- Wenn neue Version ≥ N Predictions hat und signifikant besser: markiert als `is_active=True`, alte als `is_active=False`
- Schreibt neue Prompt-Kandidaten basierend auf Learnings (Claude-generiert)

### G — Volle 500-Ticker-Liste
- `config.py`: `SP500_FULL_TICKERS` von Stub auf echte 500 Symbole erweitern
- `USE_FULL_SP500=true` in GitHub Actions Env setzen
- historical_loader für alle 500 Ticker laufen lassen (Capital.com, 3 Jahre)
- Rate-Limiting beachten: Capital.com 600 Calls/Min

---

## 3. Bekannte Bugs (offen)

| # | Datei | Bug | Schwere |
|---|---|---|---|
| B-03 | `config.py:SP500_FULL_TICKERS` | Ist Stub (= MVP-Liste), `USE_FULL_SP500=true` würde nur 20 Ticker laufen lassen | Mittel |
| B-05 | `main.py:_guess_aborted_phase()` | Gibt immer `"policy_monitor"` zurück, egal wo der Abort war | Niedrig |
| B-06 | `config.py` vs `guardrails.py` | MAX_HOLD_DAYS=5 in config.py, aber guardrails.py und evaluator.py nutzen hardcoded 3 — Widerspruch | Niedrig |

**Behoben (2026-07-09, Commit `d17c2f5`):**

| # | Datei | Bug | Fix |
|---|---|---|---|
| B-01 | `analyze.yml` | Run-Type-Erkennung per Uhrzeit brach bei DST | Matcht jetzt `github.event.schedule`-String direkt via `case` |
| B-02 | `main.py:run_evaluate()` | Hardcoded `YFinanceProvider()` | Nutzt jetzt `CapitalComProvider()` |
| B-04 | `analyze.yml` | Cron-Kommentar/Code-Mismatch | Hinfällig, da Matching nicht mehr über geparste Uhrzeit läuft |

---

## 4. Architektur-Entscheidungen die nicht rückgängig gemacht werden dürfen

| Entscheidung | Begründung |
|---|---|
| `SIMULATION_ONLY = True` immer | Niemals echte Orders. Hardcoded, keine Env-Variable. |
| Capital.com als primärer OHLC-Provider | 600 Calls/Min kostenlos auf Demo; yFinance hat Rate-Limits und ist unzuverlässig |
| SQLite für alle Tracking-Daten | Kein externer DB-Server nötig; DB via GitHub Releases persistiert |
| `learnable=False` für übersprungene Tickers | Schlechte Daten dürfen das Lernmodul nicht vergiften |
| Long / Short getrennt tracken | Hit-Rates sind asymmetrisch; gemeinsames Tracking würde Bias verschleiern |
| `ZoneInfo("Europe/Berlin")` überall | Märkte schließen um Berliner Zeit; Crons in Berlin-Zeit geplant |
| Capital.com Session-Level Auth | Ein Session-Object pro Run (lazy init); nicht je Request neu authentifizieren |
| Fundamentals 7-Tage-Cache in SQLite | Finnhub Free hat Limits; Fundamentals ändern sich selten |
| `extract_json_blob()` mit `raw_decode` | Claude hängt oft Text nach dem JSON; JSONDecoder.raw_decode toleriert das |
| Provider-Hierarchie: Capital.com (alleinig) → Finnhub (nur Fundamentals) | yFinance seit Sprint 3 entfernt (Commit `d17c2f5`, 2026-07-09); kein Fallback mehr für OHLC |
| DB-Persistenz via GitHub Releases (`db-latest`) | Kein externer Storage nötig; funktioniert mit kostenlosen GH Actions |
| 8 Score-Dimensionen mit festem Gewicht | market_env 10%, company 18%, valuation 12%, momentum 22%, risk 10%, sector 10%, catalyst 10%, policy 8% — nicht ändern ohne A/B-Test |
| `CostCapExceeded` bricht Phasen ab, sendet trotzdem Mail | Partielle Ergebnisse sind besser als gar keine |

---

## 5. Verhaltensregeln für Claude Code in zukünftigen Sessions

1. **PROJECT_STATUS.md zuerst lesen** — vor jedem neuen Plan oder jeder Implementierung dieses Dokument laden, um den aktuellen Stand zu kennen.

2. **Nie echte Orders ausführen** — `SIMULATION_ONLY=True` ist sakrosankt. Kein Code darf je `requests.post(...positions...)` für echte Trades aufrufen.

3. **Capital.com ist alleiniger OHLC-Provider** — yFinance wurde in Sprint 3 entfernt (Commit `d17c2f5`, 2026-07-09). Kein neuer Code darf yFinance importieren oder als Fallback wieder einführen.

4. **Kein Fallback-Pattern mehr nötig** — `run_pipeline()`, `run_close()` und `run_evaluate()` instanziieren `CapitalComProvider()` unconditional. Nicht wieder ein `if config.CAPITAL_COM_API_KEY else ...`-Fallback einbauen.

5. **Migrations-Guards in `_apply_migrations()`** — neue Spalten immer per `PRAGMA table_info()` prüfen vor `ALTER TABLE`, nie direkt ausführen.

6. **`learnable=False` Predictions nie ins Lernmodul** — die `learnable`-Flag ist semantisch wichtig; nie ignorieren.

7. **Timezone immer `ZoneInfo("Europe/Berlin")`** — kein `datetime.now()` ohne Timezone, kein UTC-Drift.

8. **Tests nicht löschen oder abschwächen** — Coverage-Ziel 80%. Bei Refactoring: Tests zuerst anpassen, dann Code.

9. **Historische Plan-Dateien** — `docs/superpowers/plans/` enthält abgeschlossene Pläne mit `⚠️ HISTORISCH`-Banner. Diese Dateien nicht mehr bearbeiten; stattdessen neue Plan-Datei anlegen.

10. **Prompt-Dateien versionieren** — neue Prompt-Versionen immer in `prompts/` mit Version-Suffix, nie alte überschreiben ohne DB-Eintrag in `prompt_versions`.

11. **`extract_json_blob()` für alle Claude-Antworten nutzen** — nie direkt `json.loads(result.text)` ohne den raw_decode-Wrapper.

12. **Kosten im Auge behalten** — MAX_COST_PER_RUN_EUR=4.00; teure neue Phasen immer mit CostTracker integrieren.
