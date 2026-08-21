# Shares_Future – S&P 500 CFD Research Tool

> Automatisiertes Research-Tool für die tägliche Analyse von S&P-500-Aktien, Rohstoffen
> und Kryptowährungen mit mehrdimensionalem Scoring und Web-Search-Integration.

**Zuletzt aktualisiert:** 2026-08-19 — auf den Ist-Stand gezogen (Plan 3b Ranking,
Phase-3b-Batching, `final_close`-Mail, DB-Aufräumen — Details PROJECT_STATUS C.13–C.17).

**Kein automatisches Trading.** Nur Research und Paper-Trading-Simulation.
`SIMULATION_ONLY=True` ist eine harte Invariante.

> Verbindlich für den Projektstand ist `docs/superpowers/specs/PROJECT_STATUS.md`.
> Dieses README beschreibt, *was* das Tool ist; PROJECT_STATUS beschreibt, *wo* es steht.

## Quick Start

```bash
# 1. Setup (einmalig)
python -m pip install -r requirements.txt
pytest tests/ --cov=src --cov-fail-under=80   # Stand 2026-08-19: 880 passed, 14 skipped, 92,5 %

# 2. Historie laden — PFLICHT vor dem ersten Lauf.
#    Ohne Bars wird jeder Ticker als "insufficient bars" uebersprungen.
python setup/historical_loader.py --universe

# 3. Sieht die Datenbank gesund aus? (reine DB-Abfrage, keine API-Calls)
python setup/historical_loader.py --report-coverage

# 4. Lokal ausfuehren — ACHTUNG: kein Mock-Modus. Ein pre_market-Lauf ruft echte
#    APIs auf, kostet ~3,13 EUR (gemessen, 20 Ticker) und verschickt echte Mail.
#    final_close macht keine Claude-Calls (0 EUR), verschickt aber seit C.17
#    (2026-08-19) ebenfalls eine echte Mail -- auch gegen eine Wegwerf-DB, denn
#    der Mailversand haengt nicht am --db-path.
python main.py --run-type final_close --db-path /tmp/wegwerf.db
```

Für gefahrlose Experimente siehe „Lokales Docker-Setup" in `CLAUDE.md` — dort wird der
DB-Mount überschrieben, sodass nichts in `data/tracking.db` landet.

## Was macht Shares_Future?

Analysiert je Lauf **176 Instrumente**:

| Gruppe | Umfang |
|---|---|
| Aktien | **150** (`SP500_PROD_TICKERS`, sektor-balanciert aus den 451 verifizierten Tickern). `USE_FULL_SP500=true` schaltet auf die volle Liste (451) |
| Rohstoffe | 3 — `GOLD`, `SILVER`, `OIL_CRUDE` |
| Krypto | 4 — `BTCUSD`, `ETHUSD`, `SOLUSD`, `XRPUSD` |
| Sub-Sektor-ETFs | 19 — nur als Momentum-Referenz, nie selbst analysiert |

⚠️ In die **teure Tiefenanalyse** (Phase 3) gehen davon höchstens
`MAX_DEEP_ANALYSIS = 50` — ein grösseres Universum erzeugt deshalb keine
zusätzlichen Predictions, sondern eine bessere Auswahl aus einem grösseren Pool.

⚠️ Die Ticker der Rohstoffe/Krypto **sind** die Capital.com-Epics (seit
2026-08-21, PROJECT_STATUS C.25) — vorher stand dort yfinance-Notation
(`GC=F`, `BTC-USD`), die vor jedem Call übersetzt werden musste.

Jedes Asset wird über 8 Dimensionen bewertet — Market Environment, Company Quality,
Valuation, Momentum, Risk, Sector Trend, Catalyst, Policy Risk. **Keine feste
Gewichtung:** seit Plan 3b (2026-08-18) ist `config.DIMENSION_WEIGHTS` entfernt: der
Sortierschlüssel ist `rank_score` (`analysis_strength × tech_strength`, PROJECT_STATUS
C.13) — eine Gewichtung zu einem Gesamtscore ist bewusst Aufgabe von Sprint 3D.

**Output:** bis zu 10 Long + 10 Short (`ranking.TOP_N`) plus Rohstoffe/Krypto, die die
Guardrails passieren.

## Ablauf eines `pre_market`-Laufs

Die verbindliche Reihenfolge steht in `main.py:run_pipeline()`; hier die Kurzform:

```
Phase 0   Trend-Analyse (Sonnet + Web-Search)
Phase 0b  Markt-Kontext (VIX, Regime)
Phase 1   Datenabruf Aktien, dann Rohstoffe/Krypto (Capital.com)
Phase 1c  Pflicht-Kandidaten aus offenen Capital.com-Positionen
Phase 1d  Sektor-Momentum (zwei getrennte Signale: ETF + DB-Durchschnitt)
Phase 2   Nachrichten-Scan (Sonnet + Web-Search, EIN Call ueber alle Ticker,
          ersetzt seit Plan 2 den alten Haiku-Quick-Filter -- toter Code seither)
Phase 2a  Cutoff (waehlt <= MAX_DEEP_ANALYSIS Kandidaten fuer Phase 3)
Phase 2b  Fundamentaldaten der Kandidaten (Finnhub, nicht fatal bei Ausfall)
Phase 3   Policy-Monitor (1x je Lauf) + Tiefenanalyse je Kandidat, gebatcht
          nach Sub-Sektor (Web-Search, 8 Dimensionen)
Phase 3b  Rohstoffe/Krypto (immer alle 7 analysiert, seit C.15 gebatcht nach
          asset_class statt 7 Einzelcalls)
Phase 4   Ranking + Guardrails -> predictions
Phase 4a  Portfolio-Check auf offenen Predictions
Phase 5   E-Mail
```

⚠️ **Phase 4 laeuft vor Phase 4a.** In der Mail steht die Portfolio-Sektion trotzdem
zuerst — das ist eine dokumentierte Invariante und kein Widerspruch.

## Run-Types

| Run-Type | Zeit | Zweck | Kosten |
|---|---|---|---|
| `pre_market` | 13:00 UTC, Mo–Fr | volle Pipeline | **3,13 EUR** (gemessen, 20 Ticker) |
| `trade_proposals` | 10:10 New York¹ | Re-Validierung der Morgensignale | ~0,5–0,7 EUR |
| `final_close` | 00:15 UTC, **täglich** | schreibt die finalen Tagesbars, bewertet offene Predictions, verschickt Auswertungs-Mail *(seit C.17)* | ~0 EUR |
| `weekly` | So 18:00 UTC | Wochenauswertung | ~0 EUR |

¹ Hängt an der US-Eröffnung, nicht an Berlin. Geplant ist nur der EDT-Slot (14:10 UTC);
der Workflow fährt vorerst ausschliesslich die Berliner Sommerzeit und überspringt den
Lauf, sobald New York auf EST steht. Details in `CLAUDE.md`.

⚠️ Die Berlin-Zeiten in `analyze.yml` gelten für CEST; im Winter läuft alles 1 h früher
(bewusst aufgeschoben, TODO im Workflow).

⚠️ `close` (20:30 UTC) ist am 2026-08-18 **ersatzlos entfallen** — `final_close` wertet
aus, alles Übrige erledigte `pre_market` ohnehin. Details: PROJECT_STATUS **C.14**.

## Der CFD-Kurzfristfokus

Alle Setups müssen erfüllen (`src/guardrails.py`, Werte aus `config.py`):

- **Max. `MAX_HOLD_DAYS = 5` Handelstage** Haltedauer, `HOLD_TARGET = "intraday"`
- **Min. `SP500_MIN_ATR_PCT = 2.0` ATR** — Mindestbewegung
- **R/R ≥ 1.5** — hartes Minimum
- **Mindestens 2 Belege je Score-Dimension**

## Tech Stack

| Komponente | Wahl | Grund |
|---|---|---|
| Sprache | Python 3.12 | |
| KI | Sonnet 4.6 (alle aktiven Phasen) | Web-Search eingebaut. Haiku-Pfad (`quick_filter.py`) ist toter Code seit Plan 2 — im Repo, nicht in der Pipeline |
| Marktdaten (OHLC) | **Capital.com** — alleiniger Provider, kein Fallback | yfinance seit 2026-07-09 entfernt |
| Fundamentaldaten | Finnhub (7-Tage-Cache) | |
| Persistenz | SQLite (`data/tracking.db`) | Backup als GitHub-Release-Asset `db-latest` |
| Scheduler | GitHub Actions Cron | UTC-basiert |
| E-Mail | Resend | eigene Domain verifiziert |
| Tests | pytest | 80 % Coverage-Gate, **894 Tests** (880 passed, 14 skipped) |

## Projekt-Status (Kurzfassung)

| Sprint | Stand |
|---|---|
| 1 — Foundation | ✅ abgeschlossen |
| 2 — Capital-Provider, DB, Position-Check | ✅ abgeschlossen |
| 3B — Cron-Struktur + Pipeline-Umbau | ✅ abgeschlossen, live verifiziert |
| 3B-M — Mail-Provider Resend | ✅ abgeschlossen |
| Preismodell-Umbau | ✅ abgeschlossen, `final_close` + Evaluator live verifiziert |
| 3C — Analyse-Pipeline-Umbau (Trichter, Ranking) | ✅ abgeschlossen (Plan 1/2/3a/3b), live verifiziert |
| 3D / 3E / 3F | ⚠️ **Platzhalter** — Sprint wird erst gemeinsam ausgearbeitet |

✅ **`analyze.yml` ist aktiv** (seit 2026-08-18 manuell reaktiviert). Die Voraussetzung
war, dass `db-latest` echte Historie hat (Workflow `bootstrap-db`, nur `workflow_dispatch` — erledigt 2026-08-08).

## Wichtige Dateien

- **`CLAUDE.md`** — Direktiven und die nicht-ableitbaren Fallen. Vor dem Arbeiten lesen.
- **`docs/superpowers/specs/PROJECT_STATUS.md`** — **verbindlicher Ist-Stand**
- **`docs/ARCHITECTURE.md`** — Datenfluss, Module, Interfaces
- **`docs/WORKFLOW.md`** — Live-Betrieb, Cron-Timing, Betriebsfehler
- **`docs/SPECIFICATION.md`** — ⚠️ historisch (Version 5.0, 2026-05-22), überholt
- **`config.py`** — alle Konstanten
- **`main.py`** — Orchestrator, `--run-type` ist Pflichtargument

## First Run Checklist

- [ ] `requirements.txt` installiert, Python 3.12+
- [ ] `pytest tests/ -q` → 880 passed, 14 skipped
- [ ] Secrets: `ANTHROPIC_API_KEY`, `RESEND_API_KEY`, `EMAIL_TO`, `EMAIL_FROM`,
      `FINNHUB_API_KEY`, `CAPITAL_COM_API_KEY`, `CAPITAL_COM_IDENTIFIER`,
      `CAPITAL_COM_PASSWORD`
- [ ] **Workflow `bootstrap-db` einmal auslösen** — sonst hat die CI-DB keine Historie
- [ ] `analyze.yml` aktivieren (bewusste Entscheidung)
- [ ] Erste Läufe beobachten, Release-Asset `db-latest` prüfen
- [ ] Mailzustellung prüfen — ein `2xx` von Resend heisst nur „angenommen"

## Lizenz & Disclaimer

Research-Tool, **kein Trading-System**. Keine automatischen Order-Ausführungen, nur
Paper-Trading-Simulation. `SIMULATION_ONLY=True` ist eine harte Invariante.
