# Shares_Future – SP500 CFD Research Tool

## Projektübersicht
Automatisiertes Research-Tool zur täglichen Analyse von S&P 500 Aktien,
Rohstoffen (Gold, Silber, Öl) und Kryptowährungen (BTC, ETH, SOL, XRP).

Kein automatisches Trading. Nur Research und Paper-Trading Simulation.

## Tech Stack
- Python 3.11+
- Anthropic Claude API (claude-sonnet-4-6)
- Capital.com Demo API (primary OHLC, 600 Calls/Min, kostenlos)
- Finnhub Free (Fundamentals, 7-Tage Cache)
- yfinance (Fallback wenn Capital.com nicht verfügbar)
- SQLite für Tracking und Lernmodul
- SendGrid für E-Mail Reports
- GitHub Actions für Scheduling (6 Run-Types täglich)
- pytest für Tests (min. 80% Coverage)

## Projektstruktur
```
Shares_Future/
├── src/
│   ├── providers/          # DataProvider Interface
│   │   ├── base.py
│   │   ├── capital_provider.py  # Capital.com (primary OHLC + positions)
│   │   ├── yfinance_provider.py # Fallback
│   │   └── finnhub_provider.py  # Fundamentals (gecacht)
│   ├── data_collector.py   # Phase 1: Datenabruf
│   ├── trend_analyzer.py   # Phase 0: Megatrend-Analyse
│   ├── quick_filter.py     # Phase 2: Batch-Analyse ohne Web-Search
│   ├── deep_analysis.py    # Phase 3: Claude + Web-Search
│   ├── commodities_crypto.py # Phase 3b: Gold, Silber, Öl, BTC, ETH, SOL, XRP
│   ├── ranking.py          # Phase 4: Ranking + SQLite
│   ├── learning_module.py  # Long/Short Lernmodul getrennt
│   ├── prompt_optimizer.py # Automatische Prompt-Verbesserung
│   ├── email_sender.py     # Tages + Wochen-Mail
│   ├── guardrails.py       # Qualitätskontrolle (Pflicht)
│   └── utils.py
├── setup/
│   └── historical_loader.py  # 3-Jahres-Pull via Capital.com
├── data/
│   ├── tracking.db         # SQLite Hauptdatenbank
│   ├── learnings.json       # Long/Short Performance getrennt
│   └── prompt_versions.json # Prompt-Versionen für A/B-Test
├── prompts/                 # Versionierte Prompts
├── tests/                   # pytest, min. 80% Coverage
├── config.py
└── main.py
```

## Analyse-Pipeline
```
Phase 0: Trend-Analyse     → Megatrends identifizieren
Phase 1: Datenabruf        → Capital.com (primary) / yfinance (fallback)
                             500 Aktien + Commodities + Crypto
                             1 Bar täglich fetchen + letzte 200 aus DB
Phase 2: Quick-Filter      → Batches à 30, kein Web-Search, Top 80
Phase 3: Tiefenanalyse     → Web-Search + Policy Risk Monitor, Top 80
Phase 3b: Feste Assets     → Gold, Silber, Öl, BTC, ETH, SOL, XRP immer
Phase 4: Ranking           → Top 10 Long + Top 10 Short + Learnings
Phase 5: E-Mail            → 3 Sektionen: Aktien, Trends, Commodities/Crypto
```

## Wichtige Designentscheidungen
- Provider-Hierarchie: Capital.com (primary OHLC) → Finnhub (Fundamentals, gecacht) → yfinance (Fallback)
- Guardrails: jede Analyse braucht min. 2 Belege je Score-Dimension
- Long/Short getrennt tracken und optimieren
- Übersprungene Aktien: learnable=False, nie ins Lernmodul
- SIMULATION_ONLY=True: niemals echte Orders
- ATR-Mindest: SP500_MIN_ATR_PCT = 2.0
- MAX_HOLD_DAYS = 5, HOLD_TARGET = "intraday"
- Timezone: TZ="Europe/Berlin" in Bash, ZoneInfo("Europe/Berlin") in Python
- Prompts versioniert mit A/B-Testing

## Cron-Jobs (Berliner Zeit)
| Run-Type         | Zeit (Berlin) | Kosten   | Beschreibung                              |
|------------------|---------------|----------|-------------------------------------------|
| pre_market       | 14:00         | ~3,20 EUR | Vollständige Pipeline Phase 0–4, Mail      |
| evaluate         | 15:00         | ~0,00 EUR | Nur TP/SL-Check, kein Claude, kein Mail   |
| midday           | 16:15         | ~3,20 EUR | Vollständige Pipeline Phase 0–4, Mail      |
| position_check   | 17:30 (NEU)   | ~0,20 EUR | Capital.com GET /positions + Claude + Mail |
| close            | 22:30         | ~0,00 EUR | NUR DB-Pflege, kein Claude, kein Mail     |
| weekly           | So 20:00      | ~0,00 EUR | Wochenperformance-Mail                    |

**Gesamt/Tag:** ~6,60 EUR | **Gesamt/Monat (500 Ticker):** ~145 EUR | **MVP (20 Ticker):** ~29 EUR

## Wichtige Befehle
```bash
# Historischer Setup-Pull – alle SP500-Ticker (3 Jahre via Capital.com)
python setup/historical_loader.py --all

# Historischer Setup-Pull – vollständige 500-Ticker-Liste
python setup/historical_loader.py --full-sp500

# Historischer Setup-Pull – einzelner Ticker
python setup/historical_loader.py --tickers AAPL MSFT NVDA

# Manueller Run
python main.py --run-type pre_market
python main.py --run-type evaluate
python main.py --run-type midday
python main.py --run-type position_check
python main.py --run-type close
python main.py --run-type weekly

# Tests
pytest tests/ --cov=src --cov-fail-under=80

# Einzelne Test-Suite
pytest tests/unit/test_guardrails.py -v
```

## Environment Variables (.env)
```
ANTHROPIC_API_KEY=...
SENDGRID_API_KEY=...
EMAIL_TO=...
EMAIL_FROM=...
CAPITAL_COM_API_KEY=...   # Capital.com Demo API Key
CAPITAL_COM_PASSWORD=...  # Capital.com Demo Passwort
FINNHUB_API_KEY=...       # Finnhub Free (Fundamentals)
```

## GitHub Secrets (für Actions)
ANTHROPIC_API_KEY, SENDGRID_API_KEY, EMAIL_TO, EMAIL_FROM,
CAPITAL_COM_API_KEY, CAPITAL_COM_PASSWORD, FINNHUB_API_KEY

## Scoring
8 Dimensionen, Gewichtung:
market_environment 10%, company_quality 18%, valuation 12%,
momentum 22%, risk 10%, sector_trend 10%, catalyst 10%, policy_risk 8%

CFD Simulation: 500 EUR Margin, 5:1 Hebel = 2500 EUR Exposure
1% Bewegung = 25 EUR Gewinn/Verlust (simuliert)

## Sprint-Übersicht
- **Sprint 1:** ERLEDIGT — 159 Tests, 89.62% Coverage, gemerged in main (2026-05-20)
- **Sprint 2 / Plan 1:** Plan geschrieben (2026-05-22), Implementierung ausstehend
  - Plan: `docs/superpowers/plans/2026-05-21-sprint2-plan1-capital-provider-db-incremental.md`
  - Scope: capital_provider.py, fundamentals_cache, DB-Incremental, position_check, Timezone-Fix, historical_loader
- **Sprint 3:** offen — Learning Module, Prompt-Optimizer, A/B-Testing

## Vollständige Spezifikation
Siehe docs/SPECIFICATION.md für alle Details zu:
- Datenbankschema
- Prompt-Templates
- Guardrails-Logik
- Lernmodul (Long/Short getrennt)
- E-Mail-Format
- Test-Struktur
