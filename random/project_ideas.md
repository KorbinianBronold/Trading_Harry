- Twitter / X / Truth Social mit einbeziehen.
    - Möglichkeit zu haben Trend Setter welche gerade aktuell sind zu definieren in config file, welche dann analysiert weredn sollen (Trump, Musk etc.)

Sprint 3 mit aufnehmen:
- historical loader wird einmal manuell ausgeführt, dann soll immer automatisch nach gap prüfen (nur handesltage, WE nicht relevant). dann auffüllen

- Logging von Reuqests und Responses Falls du Roh-Responses dauerhaft sehen willst, wäre das eine kleine Änderung in src/utils.py (Debug-Logging des Response-Texts hinter einem Flag). Das ginge, wirkt aber erst ab dem nächsten Lauf — sag Bescheid, ob ich das für Plan 2 vormerken soll.


Later:
- jetzt SQLite behalten, später DuckDB/DWH wenn nötig

### Initialer run der die daten der letzten Jahre hold nicht vergessen

┌────────────────┬───────────────┬───────────────┬───────────┬────────────────────────────┐
│      Job       │   UTC-Cron    │ Berlin (CEST) │  Kosten   │      main.py-Funktion      │
├────────────────┼───────────────┼───────────────┼───────────┼────────────────────────────┤
│ pre_market     │ 0 13 * * 1-5  │ 15:00 Mo–Fr   │ ~3,20 EUR │ run_pipeline("pre_market") │
├────────────────┼───────────────┼───────────────┼───────────┼────────────────────────────┤
│ evaluate       │ 0 14 * * 1-5  │ 16:00 Mo–Fr   │ ~0,00 EUR │ run_evaluate()             │
├────────────────┼───────────────┼───────────────┼───────────┼────────────────────────────┤
│ midday         │ 0 17 * * 1-5  │ 19:00 Mo–Fr   │ ~3,20 EUR │ run_pipeline("midday")     │
├────────────────┼───────────────┼───────────────┼───────────┼────────────────────────────┤
│ position_check │ 30 15 * * 1-5 │ 17:30 Mo–Fr   │ ~0,20 EUR │ run_position_check()       │
├────────────────┼───────────────┼───────────────┼───────────┼────────────────────────────┤
│ close          │ 30 20 * * 1-5 │ 22:30 Mo–Fr   │ ~0,00 EUR │ run_close()                │
├────────────────┼───────────────┼───────────────┼───────────┼────────────────────────────┤
│ weekly         │ 0 18 * * 0    │ 20:00 So      │ ~0,00 EUR │ run_weekly()               │
└────────────────┴───────────────┴───────────────┴───────────┴────────────────────────────┘


### pre_market
┌───────────────────────────────┬────────────────────────┬──────────────────────────────────┬───────────────────────────┐
│             Phase             │     main.py-Zeile      │              Aufruf              │     Implementiert in      │
├───────────────────────────────┼────────────────────────┼──────────────────────────────────┼───────────────────────────┤
│ Phase 0 — Trend-Analyse       │ main.py:144            │ analyze_trends()                 │ src/trend_analyzer.py     │
├───────────────────────────────┼────────────────────────┼──────────────────────────────────┼───────────────────────────┤
│ Phase 1 — Aktien-Kursdaten    │ main.py:152            │ collect()                        │ src/data_collector.py     │
├───────────────────────────────┼────────────────────────┼──────────────────────────────────┼───────────────────────────┤
│ Phase 1b —                    │ main.py:158 (Zeile     │                                  │                           │
│ Commodities/Crypto-Kursdaten  │ grob, direkt nach      │ collect() (2. Aufruf)            │ src/data_collector.py     │
│                               │ Phase 1)               │                                  │                           │
├───────────────────────────────┼────────────────────────┼──────────────────────────────────┼───────────────────────────┤
│ Phase 2 — Quick-Filter        │ main.py:182            │ quick_filter_batch()             │ src/quick_filter.py       │
├───────────────────────────────┼────────────────────────┼──────────────────────────────────┼───────────────────────────┤
│ Phase 3 — Policy-Monitor      │ main.py:188            │ run_policy_monitor()             │ src/deep_analysis.py      │
├───────────────────────────────┼────────────────────────┼──────────────────────────────────┼───────────────────────────┤
│ Phase 3 — Tiefenanalyse       │ main.py:194            │ analyze_assets()                 │ src/deep_analysis.py      │
├───────────────────────────────┼────────────────────────┼──────────────────────────────────┼───────────────────────────┤
│ Phase 3b —                    │ main.py:203            │ analyze_commodities_and_crypto() │ src/commodities_crypto.py │
│ Commodities/Crypto-Analyse    │                        │                                  │                           │
├───────────────────────────────┼────────────────────────┼──────────────────────────────────┼───────────────────────────┤
│ Phase 4a — Portfolio-Check    │ main.py:215            │ check_open_positions()           │ src/portfolio_check.py    │
├───────────────────────────────┼────────────────────────┼──────────────────────────────────┼───────────────────────────┤
│ Phase 4 — Ranking + Persist   │ main.py:225            │ rank_and_persist()               │ src/ranking.py            │
├───────────────────────────────┼────────────────────────┼──────────────────────────────────┼───────────────────────────┤
│                               │ main.py:249 (kein      │                                  │                           │
│ Phase 5 — E-Mail              │ Phase-Kommentar,       │ send_daily_email()               │ src/email_sender.py       │
│                               │ direkt nach dem        │                                  │                           │
│                               │ try/except)            │                                  │

### evaluate
┌─────────────────────┬───────────────────┬─────────────────────────────────────────────┬──────────────────────────────┐
│       Schritt       │    Datei:Zeile    │                   Aufruf                    │       Implementiert in       │
├─────────────────────┼───────────────────┼─────────────────────────────────────────────┼──────────────────────────────┤
│ Setup (DB-Connect,  │ main.py:329-331   │ db.connect(), db.init_schema(),             │ src/db.py, src/providers/cap │
│ Schema, Provider)   │                   │ CapitalComProvider()                        │ ital_provider.py             │
├─────────────────────┼───────────────────┼─────────────────────────────────────────────┼──────────────────────────────┤
│ Walk-Forward-Evalua │                   │                                             │                              │
│ tion                │ main.py:332       │ evaluate_open_predictions()                 │ src/evaluator.py:67          │
│ (Orchestrierung)    │                   │                                             │                              │
├─────────────────────┼───────────────────┼─────────────────────────────────────────────┼──────────────────────────────┤
│ Offene Predictions  │ evaluator.py:74-7 │ SQL-Query (inline)                          │ src/evaluator.py             │
│ laden               │ 8                 │                                             │                              │
├─────────────────────┼───────────────────┼─────────────────────────────────────────────┼──────────────────────────────┤
│ OHLC-Daten abrufen  │ evaluator.py:85-8 │ price_provider.get_ohlc_after()             │ src/providers/capital_provid │
│                     │ 7                 │                                             │ er.py                        │
├─────────────────────┼───────────────────┼─────────────────────────────────────────────┼──────────────────────────────┤
│ Datenausfall        │ evaluator.py:92-1 │ db.update_outcome_close(exit_reason="data_m │ src/db.py                    │
│ behandeln           │ 00                │ issing")                                    │                              │
├─────────────────────┼───────────────────┼─────────────────────────────────────────────┼──────────────────────────────┤
│ TP/SL/Timeout       │ evaluator.py:102- │ _walk_forward_hit()                         │ src/evaluator.py:27          │
│ prüfen              │ 105               │                                             │                              │
├─────────────────────┼───────────────────┼─────────────────────────────────────────────┼──────────────────────────────┤
│ P&L berechnen       │ evaluator.py:106- │ _profit_loss_eur()                          │ src/evaluator.py:54          │
│                     │ 109               │                                             │                              │
├─────────────────────┼───────────────────┼─────────────────────────────────────────────┼──────────────────────────────┤
│ Ergebnis            │ evaluator.py:117- │ db.update_outcome_close()                   │ src/db.py                    │
│ persistieren        │ 123               │                                             │                              │
├─────────────────────┼───────────────────┼─────────────────────────────────────────────┼──────────────────────────────┤
│ Cleanup (Connection │ main.py:336       │ conn.close()                                │ —                            │
│  schließen)         │                   │                                             │                              │
└─────────────────────┴───────────────────┴─────────────────────────────────────────────┴──────────────────────────────┘


### Sprints
Sprint nach: Job 1: Pre Market
Mein Vorschlag für die Sprint-Aufteilung:
Sprint 3a — Bugfixes + Cron-Umbau

3a-1: Prompt-Fix (Intraday, läuft gerade)
3a-2: MAX_HOLD_DAYS = 5 überall konsistent
3a-3: RR_RATIO_DEFAULT = 2.0 als Pflicht
3a-4: atr_pct, rsi_at_entry, volume_ratio in Prediction-Row befüllen
3a-5: Cron-Umbau analyze.yml (midday + evaluate → pre_open + post_open)
3a-6: main.py neue Run-Types (pre_open, post_open)
3a-7: Phase 1c (offene Positionen vor Quick Filter)
3a-8: Phase 4 vor Phase 4a tauschen
3a-9: hold_days in E-Mail Tabelle
3a-10: Gap-Erkennung in data_collector.py

Sprint 3b — Ranking + Learning Modul Grundgerüst

3b-1: Ranking überarbeiten (kombinierter Score aus allen Dimensionen)
3b-2: outcomes-Tabelle: day_hit Spalte (Intraday bis Tag 5)
3b-3: evaluator.py: tagesgenaues TP/SL-Tracking
3b-4: learning_module.py bauen (Long/Short Hit-Rates, learnings.json)
3b-5: Quick Filter Score-Schwellenwert via Learning Modul
3b-6: Wöchentliche E-Mail: Learning Modul Output

Sprint 3c — Human in the Loop

3c-1: GitHub Issue Erstellung via Learning Modul
3c-2: apply_changes.yml Workflow
3c-3: prompt_optimizer.py
3c-4: Volle 500-Ticker-Liste + Pre-Filter