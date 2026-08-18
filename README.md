# Shares_Future – S&P 500 CFD Research Tool

> Automatisiertes Research-Tool für die tägliche Analyse von S&P-500-Aktien, Rohstoffen
> und Kryptowährungen mit mehrdimensionalem Scoring und Web-Search-Integration.

**Zuletzt aktualisiert:** 2026-08-09 — vollständig auf den Ist-Stand gezogen.

**Kein automatisches Trading.** Nur Research und Paper-Trading-Simulation.
`SIMULATION_ONLY=True` ist eine harte Invariante.

> Verbindlich für den Projektstand ist `docs/superpowers/specs/PROJECT_STATUS.md`.
> Dieses README beschreibt, *was* das Tool ist; PROJECT_STATUS beschreibt, *wo* es steht.

## Quick Start

```bash
# 1. Setup (einmalig)
python -m pip install -r requirements.txt
pytest tests/ --cov=src --cov-fail-under=80   # Stand 2026-08-09: 608 passed, 7 skipped, 93 %

# 2. Historie laden — PFLICHT vor dem ersten Lauf.
#    Ohne Bars wird jeder Ticker als "insufficient bars" uebersprungen.
python setup/historical_loader.py --universe

# 3. Sieht die Datenbank gesund aus? (reine DB-Abfrage, keine API-Calls)
python setup/historical_loader.py --report-coverage

# 4. Lokal ausfuehren — ACHTUNG: kein Mock-Modus. Ein pre_market-Lauf ruft echte
#    APIs auf, kostet ~3,13 EUR (gemessen, 20 Ticker) und verschickt echte Mail.
#    Gefahrlos sind close und final_close: keine Claude-Calls, keine Mail.
python main.py --run-type final_close --db-path /tmp/wegwerf.db
```

Für gefahrlose Experimente siehe „Lokales Docker-Setup" in `CLAUDE.md` — dort wird der
DB-Mount überschrieben, sodass nichts in `data/tracking.db` landet.

## Was macht Shares_Future?

Analysiert je Lauf **46 Instrumente**:

| Gruppe | Umfang |
|---|---|
| Aktien | **20** (MVP-Liste). `USE_FULL_SP500` existiert, `SP500_FULL_TICKERS` ist aber noch ein Stub — die volle Liste kommt mit Sprint 3F |
| Rohstoffe | 3 — Gold, Silber, Öl |
| Krypto | 4 — BTC, ETH, SOL, XRP |
| Sub-Sektor-ETFs | 19 — nur als Momentum-Referenz, nie selbst analysiert |

Jedes Asset wird über 8 Dimensionen bewertet (Gewichte in `config.DIMENSION_WEIGHTS`):
Market Environment, Company Quality, Valuation, Momentum, Risk, Sector Trend, Catalyst,
Policy Risk.

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
Phase 2   Quick-Filter (Haiku, EIN Call ueber alle Ticker)
Phase 2b  Policy-Monitor (1x je Lauf)
Phase 3   Tiefenanalyse je Kandidat (Web-Search, 8 Dimensionen)
Phase 3b  Rohstoffe/Krypto (immer analysiert)
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
| `final_close` | 00:15 UTC, **täglich** | schreibt die finalen Tagesbars, bewertet offene Predictions | ~0 EUR |
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
| KI | Sonnet 4.6 (Phase 0/3), Haiku 4.5 (Phase 2) | Web-Search eingebaut |
| Marktdaten (OHLC) | **Capital.com** — alleiniger Provider, kein Fallback | yfinance seit 2026-07-09 entfernt |
| Fundamentaldaten | Finnhub (7-Tage-Cache) | |
| Persistenz | SQLite (`data/tracking.db`) | Backup als GitHub-Release-Asset `db-latest` |
| Scheduler | GitHub Actions Cron | UTC-basiert |
| E-Mail | Resend | eigene Domain verifiziert |
| Tests | pytest | 80 % Coverage-Gate, **608 Tests** |

## Projekt-Status (Kurzfassung)

| Sprint | Stand |
|---|---|
| 1 — Foundation | ✅ abgeschlossen |
| 2 — Capital-Provider, DB, Position-Check | ✅ abgeschlossen |
| 3B — Cron-Struktur + Pipeline-Umbau | ✅ Code fertig (20/20 Tasks) |
| 3B-M — Mail-Provider Resend | ✅ abgeschlossen |
| Preismodell-Umbau | ✅ Code fertig, `final_close` + Evaluator live verifiziert |
| 3C — Ranking-Überarbeitung | 📋 spezifiziert, offen |
| 3D / 3E / 3F | ⚠️ **Platzhalter** — Sprint wird erst gemeinsam ausgearbeitet |

⚠️ **`analyze.yml` steht auf `disabled_manually`.** Die Reaktivierung ist eine bewusste
Entscheidung und setzt voraus, dass `db-latest` echte Historie hat (Workflow
`bootstrap-db`, nur `workflow_dispatch`). Sonst bricht jeder Lauf am Historien-Guard ab.

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
- [ ] `pytest tests/ -q` → 608 passed, 7 skipped
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
