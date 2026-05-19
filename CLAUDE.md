# Shares_Future – SP500 CFD Research Tool

## Projektübersicht
Automatisiertes Research-Tool zur täglichen Analyse von S&P 500 Aktien,
Rohstoffen (Gold, Silber, Öl) und Kryptowährungen (BTC, ETH, SOL, XRP).

Kein automatisches Trading. Nur Research und Paper-Trading Simulation.

## Tech Stack
- Python 3.11+
- Anthropic Claude API (claude-sonnet-4-5)
- yfinance für tägliche Marktdaten
- SQLite für Tracking und Lernmodul
- SendGrid für E-Mail Reports
- GitHub Actions für Scheduling (3× täglich)
- pytest für Tests (min. 80% Coverage)

## Projektstruktur
```
Shares_Future/
├── src/
│   ├── providers/          # DataProvider Interface (yfinance + paid API)
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
│   └── historical_loader.py  # Einmaliger + Delta-Datenabruf
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
Phase 1: Datenabruf        → yfinance, 500 Aktien + Commodities + Crypto
Phase 2: Quick-Filter      → Batches à 30, kein Web-Search, Top 80
Phase 3: Tiefenanalyse     → Web-Search + Policy Risk Monitor, Top 80
Phase 3b: Feste Assets     → Gold, Silber, Öl, BTC, ETH, SOL, XRP immer
Phase 4: Ranking           → Top 10 Long + Top 10 Short + Learnings
Phase 5: E-Mail            → 3 Sektionen: Aktien, Trends, Commodities/Crypto
```

## Wichtige Designentscheidungen
- DataProvider Interface: yfinance und kostenpflichtige API austauschbar
- Guardrails: jede Analyse braucht min. 2 Belege je Score-Dimension
- Long/Short getrennt tracken und optimieren
- Übersprungene Aktien: learnable=False, nie ins Lernmodul
- SIMULATION_ONLY=True: niemals echte Orders
- Rate Limiting yfinance: 0.8s zwischen Tickern, 12s alle 30 Ticker
- Prompts versioniert mit A/B-Testing

## Cron-Jobs (MEZ)
- 15:00 Uhr: Auswertung Vortag (evaluate)
- 14:00 Uhr: Pre-Market Analyse
- 16:15 Uhr: Post-Noise Update (45 Min nach Eröffnung)
- 22:30 Uhr: After-Market Analyse
- So 20:00 Uhr: Wochen-Performance-Summary

## Wichtige Befehle
```bash
# Historischer Setup-Pull (einmalig)
python setup/historical_loader.py --mode full

# Delta-Update (während paid API aktiv)
python setup/historical_loader.py --mode delta

# Manueller Run
python main.py --run-type pre_market

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
PAID_API_KEY=...          # optional, für historischen Datenabruf
PAID_API_TYPE=polygon     # polygon / fmp / alphavantage
```

## GitHub Secrets (für Actions)
ANTHROPIC_API_KEY, SENDGRID_API_KEY, EMAIL_TO, EMAIL_FROM,
PAID_API_KEY, PAID_API_TYPE

## Scoring
8 Dimensionen, Gewichtung:
market_environment 10%, company_quality 18%, valuation 12%,
momentum 22%, risk 10%, sector_trend 10%, catalyst 10%, policy_risk 8%

CFD Simulation: 500 EUR Margin, 5:1 Hebel = 2500 EUR Exposure
1% Bewegung = 25 EUR Gewinn/Verlust (simuliert)

## Vollständige Spezifikation
Siehe docs/SPECIFICATION.md für alle Details zu:
- Datenbankschema
- Prompt-Templates
- Guardrails-Logik
- Lernmodul (Long/Short getrennt)
- E-Mail-Format
- Test-Struktur
