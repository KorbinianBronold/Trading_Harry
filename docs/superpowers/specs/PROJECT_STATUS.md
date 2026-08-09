# PROJECT_STATUS.md — Shares_Future (Trading_Harry)

**Zuletzt aktualisiert:** 2026-08-09 — **Live-Verifikation weitgehend erledigt.**
`pre_market`, `close` und `final_close` sind ausgeführt und geprüft (P3.5, P2.10); die
Ursache der leeren 04.08.-Läufe ist geklärt (P2.4) und in sechs Commits behoben (P2.9).
Sämtliche `.md`-Dokumente sind auf diesen Stand gezogen (P2.11).
**608 Tests grün, Coverage 93,47 %.**

⏳ **Offen:** `trade_proposals` und `weekly` (nie ausgeführt), der einmalige
`bootstrap-db`-Lauf, danach die Reaktivierung von `analyze.yml`.
⚠️ `analyze.yml` steht weiterhin auf `disabled_manually` — das ist eine bewusste
Entscheidung, keine Nachlässigkeit.

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
| 3B | Cron-Struktur + Pipeline-Umbau | 🟢 **Code vollständig** — Plan 1 (2026-07-29) und Plan 2 (20/20 Tasks, 2026-08-04), alles auf `main`. Verifiziert: `pre_market`, `close`, `final_close` (P2.10, P3.5). ⏳ Offen: `trade_proposals`, `weekly`, `bootstrap-db`-Lauf, dann Reaktivierung von `analyze.yml` |
| **3B-M** | **Mail-Provider-Wechsel (Zwischensprint)** | ✅ **ABGESCHLOSSEN 2026-07-30** — Mailversand läuft über **Resend**, eigene Domain verifiziert, Zustellung live bestätigt. Details s. unten |
| 3C | Ranking-Überarbeitung | 📋 spezifiziert, Implementierung offen |
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
dabei aber **keine Predictions**; `analyze.yml` ist seither wieder `disabled_manually`.
Die Live-Verifikation (P2.4) bleibt damit ein echtes Gate — die Mechanik hat einmal
getragen, die Wirkung ist unbestätigt.

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
- `claude_commands.md` gelöscht — dokumentierte einen Docker-**Cron-Container**, den es nie
  gab (CLAUDE.md: „kein Scheduler/Cron im Container"), sonst nur Claude-CLI-Aufrufe.
- `project_ideas.md` gelöscht — enthielt die **alte** Cron-Tabelle mit
  `midday`/`evaluate`/`position_check` und eine von der realen Sprint-Struktur überholte
  Sprint-Aufteilung. Die drei noch offenen Ideen daraus stehen jetzt in Abschnitt 2b.

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
`schedule`. Danach wurde `analyze.yml` wieder deaktiviert (`state=disabled_manually`),
weshalb der Irrtum entstand.

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

⏳ **Offen bleiben `trade_proposals` und `weekly`** — beide nie ausgeführt.
`trade_proposals` re-validiert die `pre_market`-Signale **desselben Tages**; dafür braucht
es eine DB mit frischen Signalen. Dahinter steckt die verwickeltste Mechanik von Plan 2
(`superseded_by`, `revision_verdict`, „genau EINE offene Prediction je Trade-Idee"), die
bis heute nie eine einzige Zeile zu bearbeiten hatte.

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
