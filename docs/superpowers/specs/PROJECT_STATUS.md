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
| **Sprint 3A: Roadmap-Überarbeitung** | (2026-07-27) | Dieses Dokument. Der alte Plan "Cron-Struktur umbauen (pre_open/post_open-Split)" wurde in einer Review-Session **verworfen** und durch die Sprints 3B–3F unten ersetzt. |

---

## 2. Sprint-3-Roadmap

> **Reihenfolge:** 3B → 3C → 3D → 3E → 3F. Jeder Sprint wird vor Implementierungsbeginn
> in einer eigenen Session besprochen und bekommt eine eigene Plan-Datei unter
> `docs/superpowers/plans/`.

| Sprint | Inhalt | Status |
|---|---|---|
| 3A | Roadmap + Doku aktualisieren | ✅ erledigt (dieses Dokument) |
| 3B | Cron-Struktur + Pipeline-Umbau | 📋 spezifiziert, Implementierung offen |
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
| **Sektor-ETF-Momentum** | Long nur wenn zugehöriger Sektor-ETF positiv, Short nur wenn negativ | **Pflicht-Guardrail** (hartes Reject) |
| **Relative Stärke** | Performance des Tickers vs. seinem Sektor | Score-Input |
| **Marktbreite** | Advancing/Declining-Ratio im S&P 500 | Kontext / Warnung |
| **VIX-Level** | >25: nur noch `confidence='high'`-Signale ausgeben. >35: **keine neuen Long-Signale** | Hartes Filter-Kriterium |
| **Opening-Gap-Check** | Großer Gap zwischen `pre_market`-Kurs und aktuellem Kurs | Warnhinweis in der Mail |
| **Entry-Fenster** | Empfehlung eines Pullback-Levels statt reinem Market-Entry | Zusatzfeld in der Mail |
| **Korrelations-Check** | Klumpenrisiko-Warnung wenn mehrere Signale im selben Sektor liegen | Warnhinweis in der Mail |

**Offene Detailfragen für die 3B-Planungssession** (nicht blockierend für dieses Dokument):
- Datenquelle für Sektor-ETFs (XLK, XLF, …) und VIX — Capital.com-Epics prüfen, ggf. TICKER_MAP erweitern
- Marktbreite (A/D-Ratio) ist über Capital.com vermutlich nicht direkt verfügbar → Alternative
  nötig (z.B. Ableitung aus den eigenen 500 Tickern in der DB, sobald 3F läuft)

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

**Offen:** Soll `inactive` je zurückgesetzt werden (z.B. manuell oder nach N Tagen)? Ohne
Reset-Pfad fällt ein Ticker nach 20 Skips dauerhaft raus — bei temporären Capital.com-Ausfällen
womöglich zu hart. Vorschlag für die Planungssession: Reset-Kommando im `historical_loader`
oder automatischer Retry alle 30 Tage.

**Nebenwirkung:** `skipped_tickers` wächst ohne Löschung unbegrenzt. Vorschlag: Event-Rows
nach 90 Tagen löschen, den Aggregat-Zähler in `ticker_status` aber **nie** zurücksetzen.

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

### B.10 — Sektor-Datenbank-Struktur

Grundlage für den Sektor-ETF-Momentum-Check (B.3) und die Sektor-Auswertung in der
Weekly-Mail. Zwei neue Tabellen in `src/db.py`:

**1. `sectors`** — Referenztabelle aller GICS-Sektoren mit zugehörigem Sektor-ETF:

```sql
CREATE TABLE IF NOT EXISTS sectors (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    etf  TEXT NOT NULL
);
```

Wird beim ersten DB-Setup mit den 11 Standard-GICS-Sektoren befüllt:

| Sektor | ETF |
|---|---|
| Technology | XLK |
| Energy | XLE |
| Financials | XLF |
| Healthcare | XLV |
| Industrials | XLI |
| Communication | XLC |
| Consumer Discretionary | XLY |
| Consumer Staples | XLP |
| Materials | XLB |
| Real Estate | XLRE |
| Utilities | XLU |

**2. `ticker_sectors`** — Mapping Ticker → Sektor:

```sql
CREATE TABLE IF NOT EXISTS ticker_sectors (
    ticker     TEXT PRIMARY KEY,
    sector_id  INTEGER REFERENCES sectors(id),
    source     TEXT DEFAULT 'finnhub',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Befüllung: organisch in Phase 1** (`data_collector.py`). Wenn Finnhub den Sektor für einen
Ticker zurückgibt, wird er automatisch in `ticker_sectors` geschrieben. Kein manueller Import,
kein statisches Mapping im Code. Sektor-Information kommt aus dem
**Finnhub-Fundamentals-Cache** (Option A), nicht aus einer hartcodierten Tabelle.

**Nutzung:** `trade_proposals` und `weekly` lesen den zugehörigen Sektor-ETF-Ticker per JOIN:
`ticker → ticker_sectors → sectors.etf`.

**⚠️ Offener Punkt — Namensabgleich Finnhub ↔ GICS:**
`FinnhubProvider.get_fundamentals()` liefert das Feld `finnhubIndustry`, und dessen Werte sind
**keine GICS-Sektornamen**. Zwei Abweichungsklassen:

1. *Abweichende Sektor-Bezeichnungen* — z.B. `Consumer Cyclical` statt `Consumer Discretionary`,
   `Consumer Defensive` statt `Consumer Staples`, `Basic Materials` statt `Materials`,
   `Financial Services` statt `Financials`, `Communication Services` statt `Communication`
2. *Granularität auf Industrie- statt Sektor-Ebene* — z.B. `Semiconductors`, `Banking`,
   `Pharmaceuticals` statt des übergeordneten Sektors

Ein direkter String-Match gegen `sectors.name` würde also für einen erheblichen Teil der Ticker
fehlschlagen — `sector_id` bliebe leer und der als **Pflicht-Guardrail** definierte
Sektor-ETF-Momentum-Check (B.3) liefe für diese Ticker ins Leere.

**Vorschlag für die 3B-Planungssession** (noch nicht entschieden):
- Normalisierungs-Layer zwischen Finnhub-Wert und `sectors.name` — entweder als
  Alias-Spalte/-Tabelle in der DB oder als Dict in `data_collector.py`
- Nicht auflösbare Werte: `sector_id` NULL lassen, Vorkommen **loggen** (nicht still schlucken),
  damit die Alias-Liste iterativ wächst
- Explizit festlegen, wie sich der Sektor-ETF-Guardrail bei unbekanntem Sektor verhält:
  Ticker durchlassen (Guardrail greift nicht) oder verwerfen? Bei "Pflicht-Guardrail" wäre
  Verwerfen konsequent — würde aber bei lückenhaftem Mapping viele valide Signale killen.

### B.11 — Kleinere Fixes in 3B

- **B-05:** `main.py:_guess_aborted_phase()` gibt aktuell immer `"policy_monitor"` zurück,
  unabhängig von der tatsächlichen Abbruch-Phase. Fix: echten Phasennamen durchreichen
  (z.B. Variable `current_phase` im `try`-Block mitführen und im `except` auslesen).
- **E-Mail:** `hold_days_recommended` als eigene Spalte in der Top-10-Long/Short-Tabelle ergänzen.

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

---

## 3. Bekannte Bugs (offen)

| # | Datei | Bug | Schwere | Geplant in |
|---|---|---|---|---|
| B-03 | `config.py:SP500_FULL_TICKERS` | Ist Stub (= MVP-Liste), `USE_FULL_SP500=true` würde nur 20 Ticker laufen lassen | Mittel | Sprint 3F |
| B-05 | `main.py:_guess_aborted_phase()` | Gibt immer `"policy_monitor"` zurück, egal wo der Abort war | Niedrig | Sprint 3B |

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
