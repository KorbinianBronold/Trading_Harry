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
│   │   ├── capital_provider.py  # Capital.com (alleiniger OHLC-Provider + positions)
│   │   └── finnhub_provider.py  # Fundamentals (gecacht)
│   ├── data_collector.py   # Phase 1: Datenabruf + Gap-Erkennung
│   ├── trend_analyzer.py   # Phase 0: Megatrend-Analyse
│   ├── market_context.py   # Phase 0b: VIX, A/D-Ratio, Regime (Claude + Web-Search)
│   ├── sector_momentum.py  # ETF- + DB-Momentum je Sub-Sektor (nur Erhebung)
│   ├── quick_filter.py     # Phase 2: Batch-Analyse ohne Web-Search
│   ├── deep_analysis.py    # Phase 3: Claude + Web-Search + Policy-Monitor
│   ├── commodities_crypto.py # Phase 3b: Gold, Silber, Öl, BTC, ETH, SOL, XRP
│   ├── portfolio_check.py  # Phase 4a: offene Positionen HALTEN/SCHLIESSEN/ANPASSEN
│   ├── ranking.py          # Phase 4: Ranking + SQLite
│   ├── evaluator.py        # Walk-Forward TP/SL/Timeout-Auswertung
│   ├── email_sender.py     # Tages + Wochen-Mail
│   ├── guardrails.py       # Qualitätskontrolle (Pflicht)
│   ├── cost_tracker.py     # Kosten-Tracking + Hard-Cap
│   ├── db.py               # SQLite-Schema, Migrationen, alle DB-Helper
│   ├── utils.py
│   # learning_module.py  → noch nicht implementiert (Sprint 3D)
│   # prompt_optimizer.py → noch nicht implementiert (Sprint 3D/3E)
├── setup/
│   ├── historical_loader.py  # 3-Jahres-Pull via Capital.com + Ticker-Status-CLI
│   └── verify_epics.py       # Capital.com-Epics der Sektor-ETFs prüfen (manuell)
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
**Ist-Zustand** (`main.py:run_pipeline()`):
```
Phase 0:  Trend-Analyse    → Megatrends identifizieren (fatal wenn sie fehlschlägt)
Phase 0b: Markt-Kontext    → VIX, A/D-Ratio, Regime, Sektor-Rotation (Claude + Web-Search)
                             NICHT fatal: schlägt der Call fehl, läuft der Run mit leerem Kontext
Phase 1:  Datenabruf       → Capital.com (alleiniger OHLC-Provider), Aktien
                             1 Bar täglich fetchen + letzte 200 aus DB
                             inkl. Gap-Erkennung: fehlende Handelstage nachladen
Phase 1b: Datenabruf       → Commodities + Crypto (separater collect-Aufruf)
Phase 2:  Quick-Filter     → Batches à 30, kein Web-Search, Top 80
Phase 3:  Policy-Monitor   → 1× pro Run, Web-Search
Phase 3:  Tiefenanalyse    → Web-Search, 8 Score-Dimensionen, Top 80
Phase 3b: Feste Assets     → Gold, Silber, Öl, BTC, ETH, SOL, XRP immer
Phase 4a: Portfolio-Check  → offene Positionen: HALTEN/SCHLIESSEN/ANPASSEN
Phase 4:  Ranking          → Top 10 Long + Top 10 Short, persist predictions
Phase 5:  E-Mail           → Briefing, Portfolio, Aktien, Trends, Commodities/Crypto
```

**Geplante Änderungen in Sprint 3B** (noch nicht implementiert, s. PROJECT_STATUS.md):
- **Phase 1c neu** nach 1b: offene Capital.com-Positionen laden, deren Ticker als
  Pflicht-Kandidaten für Phase 3 markieren (überspringen den Quick-Filter-Ausschluss)
- **Phase 4 und 4a tauschen**: erst Ranking, dann Portfolio-Check — Phase 4a nutzt dann die
  fertigen Phase-3-Ergebnisse (Claude-Call ohne Web-Search) statt eigener Web-Searches.
  Die Mail-Reihenfolge bleibt davon unberührt: Portfolio-Sektion steht weiterhin zuerst.

## Wichtige Designentscheidungen
- Provider-Hierarchie: Capital.com (alleiniger OHLC-Provider) → Finnhub (Fundamentals, gecacht) — yfinance seit Sprint 3 entfernt (2026-07-09)
- Guardrails: jede Analyse braucht min. 2 Belege je Score-Dimension
- Long/Short getrennt tracken und optimieren
- Übersprungene Aktien: learnable=False, nie ins Lernmodul
- SIMULATION_ONLY=True: niemals echte Orders
- ATR-Mindest: SP500_MIN_ATR_PCT = 2.0
- MAX_HOLD_DAYS = 5, HOLD_TARGET = "intraday"
- Timezone: TZ="Europe/Berlin" in Bash, ZoneInfo("Europe/Berlin") in Python
- Prompts versioniert mit A/B-Testing
- `SECTOR_ALIASES` normalisiert Finnhubs `finnhubIndustry` auf 21 **Sub-Sektoren**
  (feiner als GICS: Halbleiter gegen SOXX statt gegen den breiten XLK). Unbekannte
  Rohwerte werden mit WARN geloggt und bleiben ungemappt — nie stillschweigend
  in einen Sammeleimer geworfen. Grundregel: lieber ungemappt als falsch gemappt.
- Ticker werden nach `TICKER_MAX_SKIPS = 20` Datenqualitäts-Skips deaktiviert,
  Auto-Retry nach `TICKER_RETRY_AFTER_DAYS = 30`, manueller Reset via `--reactivate`
- Sektor-Momentum wird als **zwei getrennte Signale** erhoben (ETF + DB-Durchschnitt)
  und nie verrechnet — Sprint 3D soll messen, welches besser predictet

## Cron-Jobs (Berliner Zeit)
**Ist-Zustand**, aus `.github/workflows/analyze.yml` (Cron ist UTC-fix, GitHub Actions
passt nicht an DST an — Zeiten unten gelten für CEST/Sommer, im Winter (CET) läuft
alles 1h früher).

| Run-Type         | Zeit (Berlin, CEST) | Kosten   | Beschreibung                              |
|------------------|----------------------|----------|-------------------------------------------|
| pre_market       | 15:00                | ~3,20 EUR | Vollständige Pipeline Phase 0–5, Mail      |
| evaluate         | 16:00                | ~0,00 EUR | Nur TP/SL-Check, kein Claude, kein Mail   |
| midday           | 19:00                | ~3,20 EUR | Vollständige Pipeline Phase 0–5, Mail      |
| position_check   | 17:30                | ~0,20 EUR | Capital.com GET /positions + Claude + Mail |
| close            | 22:30                | ~0,00 EUR | TP/SL-Check + DB-Pflege, kein Claude, kein Mail |
| weekly           | So 20:00              | ~0,00 EUR | Wochenperformance-Mail                    |

**Gesamt/Tag:** ~6,60 EUR | **Gesamt/Monat (500 Ticker):** ~145 EUR | **MVP (20 Ticker):** ~29 EUR

### Geplanter Umbau (Sprint 3B — noch NICHT implementiert)
Spezifikation: `docs/superpowers/specs/PROJECT_STATUS.md`, Abschnitt "Sprint 3B".

| Run-Type | Zeit | Änderung |
|---|---|---|
| `pre_market` | 15:00 | unverändert |
| `trade_proposals` | 16:10 | **NEU** — ersetzt `evaluate`; prüft nach dem Opening-Rauschen, ob die pre_market-Signale noch gültig sind |
| `close` | 22:30 | vereinfacht (Schlusskurse aller Ticker + DB-Cleanup; TP/SL bleibt bis Sprint 3D) |
| `weekly` | So 20:00 | Struktur gleich, Inhalt erweitert |
| ~~`midday`~~ | — | entfällt |
| ~~`position_check`~~ | — | entfällt (Capital.com live am Handy einsehbar) |

Erwartete Kosten danach: ~4,20 EUR/Tag → **~88 EUR/Monat** (500 Ticker).

**Neue DB-Tabellen in 3B:**
- `ticker_status` — kumulativer `skip_count` pro Ticker + `inactive`-Flag (ab >20 Skips)
- `sectors` — 11 GICS-Sektoren mit zugehörigem Sektor-ETF (Technology→XLK, Energy→XLE, …),
  einmalig beim DB-Setup befüllt
- `ticker_sectors` — Mapping Ticker → Sektor, wird **organisch in Phase 1** aus dem
  Finnhub-Fundamentals-Cache befüllt (kein statisches Mapping im Code).
  Genutzt von `trade_proposals` + `weekly` für den Sektor-ETF-Momentum-Check via JOIN.

## Wichtige Befehle
```bash
# historical_loader.py: genau EIN Modus-Flag ist Pflicht (--tickers / --all /
# --full-sp500 / --reactivate / --list-inactive). Ein Aufruf ohne Flag bricht mit
# argparse-Fehler ab und startet NICHT mehr stillschweigend den MVP-Pull.

# Historischer Setup-Pull – alle SP500-Ticker (3 Jahre via Capital.com)
python setup/historical_loader.py --all

# Historischer Setup-Pull – vollständige 500-Ticker-Liste
python setup/historical_loader.py --full-sp500

# Historischer Setup-Pull – einzelner Ticker
python setup/historical_loader.py --tickers AAPL MSFT NVDA

# Ticker-Status (Sprint 3B / B.7) – reine DB-Operationen, keine Capital.com-Calls
python setup/historical_loader.py --list-inactive          # stillgelegte Ticker + Retry-Datum
python setup/historical_loader.py --reactivate AAPL MSFT   # sofort zurücksetzen

# Capital.com-Epics der Sub-Sektor-ETFs + VIX prüfen (manuell, read-only)
python setup/verify_epics.py
python setup/verify_epics.py --symbols SOXX VGT            # einzelne Symbole

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

## Lokales Docker-Setup
Nur fuer manuelles Testen einzelner Run-Types — kein Scheduler/Cron im Container.
Automatisierte Ausfuehrung laeuft ausschliesslich ueber GitHub Actions (`analyze.yml`).
Dateien: `Dockerfile`, `docker-compose.yml`.

```bash
docker compose build
docker compose run --rm trading-harry --run-type pre_market
docker compose run --rm trading-harry --run-type close
```

## Environment Variables (.env)
```
ANTHROPIC_API_KEY=...
SENDGRID_API_KEY=...
EMAIL_TO=...
EMAIL_FROM=...
CAPITAL_COM_API_KEY=...    # Capital.com Demo API Key
CAPITAL_COM_IDENTIFIER=... # Capital.com Account-E-Mail/Login
CAPITAL_COM_PASSWORD=...   # Capital.com Demo Passwort
FINNHUB_API_KEY=...        # Finnhub Free (Fundamentals)
```

## GitHub Secrets (für Actions)
ANTHROPIC_API_KEY, SENDGRID_API_KEY, EMAIL_TO, EMAIL_FROM,
CAPITAL_COM_API_KEY, CAPITAL_COM_IDENTIFIER, CAPITAL_COM_PASSWORD, FINNHUB_API_KEY

## Scoring
8 Dimensionen, Gewichtung:
market_environment 10%, company_quality 18%, valuation 12%,
momentum 22%, risk 10%, sector_trend 10%, catalyst 10%, policy_risk 8%

CFD Simulation: 500 EUR Margin, 5:1 Hebel = 2500 EUR Exposure
1% Bewegung = 25 EUR Gewinn/Verlust (simuliert)

## Sprint-Übersicht
**Vor jeder Implementierung `docs/superpowers/specs/PROJECT_STATUS.md` lesen** — dort steht
der verbindliche Stand inkl. Spezifikation aller Sprint-3-Teilschritte.

- **Sprint 1:** ERLEDIGT — 159 Tests, 89.62% Coverage, gemerged in main (2026-05-20)
- **Sprint 2 / Plan 1:** ERLEDIGT — gemerged 2026-05-22
  - Plan: `docs/superpowers/plans/2026-05-21-sprint2-plan1-capital-provider-db-incremental.md`
  - Scope: capital_provider.py, fundamentals_cache, DB-Incremental, position_check, Timezone-Fix, historical_loader
- **Sprint 3** — in Arbeit, aufgeteilt in Teilsprints:
  - **3A** ERLEDIGT (2026-07-27) — Roadmap + Doku aktualisiert
  - Vorab erledigt: yfinance-Entfernung + DST-Fix (2026-07-09), Docker-Test-Image (2026-07-13),
    Code-Dokumentation (2026-07-15), Intraday-Prompt-Fix + Bug B-06 (2026-07-17)
  - **3B** OFFEN — Cron-Struktur + Pipeline-Umbau (`trade_proposals`, Phase 1c, Phase-4/4a-Tausch,
    close-Vereinfachung, Gap-Erkennung, B-05)
  - **3C** OFFEN — Ranking-Überarbeitung (fehlende Indikator-Werte, kombinierter `ranking_score`,
    R/R-Ziel 2.0, technischer Pre-Filter)
  - **3D** PLATZHALTER — Learning Modul ⚠️ braucht eigene Planungssession vor Implementierung
  - **3E** PLATZHALTER — Human-in-the-Loop ⚠️ braucht eigene Planungssession
  - **3F** PLATZHALTER — volle 500-Ticker-Skalierung ⚠️ braucht eigene Planungssession

## Vollständige Spezifikation
Siehe docs/SPECIFICATION.md für alle Details zu:
- Datenbankschema
- Prompt-Templates
- Guardrails-Logik
- Lernmodul (Long/Short getrennt)
- E-Mail-Format
- Test-Struktur
