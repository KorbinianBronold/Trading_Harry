# Shares_Future – S&P 500 CFD Research Tool

> Automatisiertes Research-Tool für tägliche Analyse von S&P 500 Aktien, Rohstoffen und Kryptowährungen mit mehrdimensionalem Scoring, Web-Search-Integration und kontinuierlichem Lernen.

## Quick Start

```bash
# 1. Setup (einmalig)
python -m pip install -r requirements.txt
pytest tests/ --cov=src --cov-fail-under=80  # Baseline: 159 tests, 89.62% coverage

# 2. Lokal testen (mit Mock-Daten)
python main.py --run-type pre_market --date 2026-05-19

# 3. Live auf GitHub Actions
# → Secrets konfigurieren (ANTHROPIC_API_KEY, SENDGRID_API_KEY, EMAIL_TO, EMAIL_FROM)
# → workflow_dispatch auf analyze.yml auslösen
# → Daily: 3 Runs (14:00, 14:45, 21:30 UTC), 1 Eval, 1 Weekly (So 20:00)
```

## Was macht Shares_Future?

Das Tool analysiert täglich:
- **500 S&P 500 Aktien** (Phase 1: Datensammlung, Phase 2: Quick-Filter)
- **4 Rohstoffe** (Gold, Silber, Öl, Fear&Greed Index)
- **4 Kryptowährungen** (BTC, ETH, SOL, XRP)

Jedes Asset wird durch 8 Dimensionen bewertet:
1. **Market Environment** (10%) – Makro, VIX, Fed-Moves
2. **Company Quality** (18%) – Earnings, Guidance, Moat
3. **Valuation** (12%) – P/E, Relative Value
4. **Momentum** (22%) – RSI, MACD, Price Action
5. **Risk** (10%) – Volatility, Technical Support/Resistance
6. **Sector Trend** (10%) – Rotation, Leadership
7. **Catalyst** (10%) – Events, Earnings Calendar
8. **Policy Risk** (8%) – Tariffs, Regulations, Geopolitics

**Output:** Top 10 Long + Top 10 Short Kandidaten pro Handelstag + Commodities/Crypto (alle behalten).

## Core Workflow (Phase 0–5)

```
Phase 0: Trend-Analyse
  ↓ (1 Sonnet + web_search)
Phase 1: Datenabruf (500 Aktien + Commodities/Crypto)
  ↓ (yfinance, 90 Tage, Rate-Limiting: 0.8s/Ticker + 12s/30er-Batch)
Phase 2: Quick-Filter (Batch-Score ohne Web-Search)
  ↓ (Haiku, 30er-Batches, Top 80 lange/kurz behalten)
Phase 3: Tiefenanalyse (Web-Search, 8-Dim Score)
  ↓ + Policy-Monitor (1× pro Run)
Phase 3b: Feste Assets (Commodities/Crypto, Fear&Greed, 8-Dim Score)
  ↓
Phase 4a: Portfolio-Check (offene Positionen: HALTEN/SCHLIESSEN/ANPASSEN)
  ↓
Phase 4: Ranking (Top-10-Filter via Guardrails, DB-Persistierung)
  ↓
Phase 5: E-Mail (4 Sektionen: Portfolio → Aktien → Trends → Commodities)
```

## Der CFD-Kurzfristfokus (Hart codiert)

Alle Setups MÜSSEN erfüllen:
- **Max 3 Handelstage Haltedauer** – Guardrail reject `hold_days_recommended > 3`
- **Min 1.0% Intraday-Range** – Guardrail reject `intraday_range_pct < 1.0`
- **Phase 4a zuerst in der E-Mail** – Portfolio-Empfehlungen VOR Aktien-Rankings
- **`close`-Run (21:30 UTC) ist der wichtigste** – Setups für den nächsten Handelstag

## Tech Stack

| Komponente | Wahl | Grund |
|---|---|---|
| **Sprache** | Python 3.12 | Modern, viele Markt-Libraries |
| **KI** | Claude Sonnet 4.6 (Phase 3+) + Haiku 4.5 (Phase 2) | Beste Kosten/Qualität, Web-Search built-in |
| **Marktdaten** | yfinance (primär) + Paid API (Setup) | Kostenlos, zuverlässig, Rate-Limiting-aware |
| **Persistenz** | SQLite (`tracking.db`) | Lokal, ACID, Release-Asset-Backup via GitHub |
| **Scheduler** | GitHub Actions Cron | Free Tier 2000 Min/Monat, UTC-basiert |
| **E-Mail** | SendGrid | 100 Mails/Tag kostenlos, API-basiert |
| **Tests** | pytest | 80% Coverage-Gate, 159 Tests (unit + integration) |

## Projekt-Status

**Sprint 1 (MVP-Pipeline):**
- ✅ Plan 1 (Foundation): 39 Tests
- ✅ Plan 2 (Collector/Trend/QuickFilter): 82 Tests
- ✅ Plan 3 (Deep/Phase4a/Email/Orchestrator): 159 Tests (77 neu)
- ⏳ Live-Validierung: 3 Werktage Cron, 1 Weekly-Mail, DB-Persistenz (siehe WORKFLOW.md)

**Sprint 2 (Skalierung):**
- Paid API (Polygon/FMP) für 500 SP500 Tickers
- Historischer 3-Jahres-Pull
- Auto-Update SP500-List monatlich

**Sprint 3 (Lernen):**
- Learning Module (Long/Short getrennt)
- Prompt-Optimizer A/B-Testing
- Erweiterte Weekly-Mail

## Wichtige Dateien

- **`CLAUDE.md`** – Projekt-Direktiven für AI-Entwickler
- **`config.py`** – Alle Konstanten (Gewichtungen, Limits, API-Keys)
- **`main.py`** – Orchestrator: `--run-type {pre_market|midday|close|evaluate|weekly}`
- **`docs/SPECIFICATION.md`** – Vollständige technische Spezifikation
- **`docs/ARCHITECTURE.md`** – Data Flow, Module, Interfaces
- **`docs/WORKFLOW.md`** – Live-Execution, Cron-Timing, DoD-Checklist

## Bekannte Carry-Overs

30 dokumentierte Code-Quality-Items für künftige Sprints (siehe `memory/project_carryover_issues.md`). Kein kritischer Bug aktiv; alle wurden bewusst nicht behoben, um Plan-Treue zu wahren (siehe [[feedback_plan_authority]]).

## First Run Checklist

- [ ] `requirements.txt` installiert + Python 3.12+ aktiv
- [ ] `pytest tests/ -q` → 159 passed (✅ lokal grün)
- [ ] GitHub Secrets: ANTHROPIC_API_KEY, SENDGRID_API_KEY, EMAIL_TO, EMAIL_FROM
- [ ] `.github/workflows/analyze.yml` aktiviert (nicht FINNHUB_API_KEY!)
- [ ] `workflow_dispatch` auf `analyze.yml` testen
- [ ] Erste 3 Runs beobachten (14:00, 14:45, 21:30 UTC)
- [ ] Release-Asset `db-latest` erscheint nach erstem erfolgreichen Run
- [ ] E-Mails in EMAIL_TO ankommen (täglich + wöchentlich)
- [ ] Kosten < 4 EUR pro Run (Cost Tracker in `tracking.db`)

## Lizenz & Disclaimer

Dieses Tool ist ein **Research-Tool, kein Trading-System**. Es gibt keine automatischen Order-Ausführungen, nur Paper-Trading Simulationen. SIMULATION_ONLY=True ist eine harte Invariante – die Code-Basis executes niemals echte Trades.

---

**Fragen?** Siehe `docs/SPECIFICATION.md` für die technische Tiefe oder `docs/WORKFLOW.md` für Live-Operationen.
