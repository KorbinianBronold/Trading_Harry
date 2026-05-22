# Shares_Future – Vollständige Spezifikation
## SP500 CFD Research Tool | Claude Code Buildanweisung
## Stand: 2026-05-22 | Version 5.0

---

## ZIELSETZUNG

Automatisiertes Research-Tool zur täglichen Analyse von S&P 500 Aktien,
Rohstoffen (Gold, Silber, Öl) und Kryptowährungen (BTC, ETH, SOL, XRP).

Ziel: Erklärbares, mehrdimensionales Ranking potenzieller Long- und Short-
Kandidaten für CFD-Trades – inklusive qualitativer Beurteilung, Score,
Confidence, TP/SL-Empfehlung und Begründung.

Das System ist ein Paper-Trading Research-Tool ohne automatische Order-
ausführung. Es lernt kontinuierlich aus eigenen Vorhersagen und verbessert
sich automatisch – Prompts, Gewichtungen und Filterregeln inklusive.

---

## WICHTIG: SOFORT VOLLSTÄNDIG BAUEN

Kein MVP-Ansatz. Kein schrittweises Hochskalieren.
Das Tool wird direkt vollständig gebaut weil historische Kursdaten
einmalig über eine kostenpflichtige API geladen werden.

Entwicklungsreihenfolge: Schritt für Schritt, nach jedem Schritt testen.
Aber das Ziel ist ein vollständig lauffähiges System – nicht ein Prototyp.

---

## TECH STACK

```
Sprache:     Python 3.11+
KI:          Anthropic Claude API (claude-sonnet-4-6)
Marktdaten:  Flexibles DataProvider-Interface (Hierarchie):
             - Primär:    Capital.com Demo API (OHLCV, 600 Calls/Min, kostenlos)
                          ENV: CAPITAL_COM_API_KEY, CAPITAL_COM_PASSWORD
             - Fundamentals: Finnhub Free (7-Tage Cache in DB)
                          ENV: FINNHUB_API_KEY
             - Fallback:  yfinance (wenn Capital.com nicht verfügbar)
E-Mail:      SendGrid API (Free Tier: 100 Mails/Tag)
Hosting:     GitHub Actions (Free Tier: 2.000 Min/Monat)
Datenbank:   SQLite (tracking.db, ~200-500 MB nach 1 Jahr)
Scheduler:   GitHub Actions Cron (6 Run-Types täglich)
Tests:       pytest mit min. 80% Code Coverage
```

---

## PROJEKTSTRUKTUR

```
Shares_Future/
├── .github/
│   └── workflows/
│       ├── analyze.yml          # 3× täglich + Auswertung
│       └── test.yml             # Tests bei jedem Push
├── src/
│   ├── providers/
│   │   ├── base.py              # DataProvider Interface
│   │   ├── capital_provider.py  # Capital.com (primary OHLC + positions)
│   │   ├── yfinance_provider.py # Fallback
│   │   └── finnhub_provider.py  # Fundamentals (7-Tage gecacht)
│   ├── data_collector.py        # Phase 1: Datenabruf
│   ├── trend_analyzer.py        # Phase 0: Megatrend-Analyse
│   ├── quick_filter.py          # Phase 2: Batch ohne Web-Search
│   ├── deep_analysis.py         # Phase 3: Claude + Web-Search
│   ├── commodities_crypto.py    # Phase 3b: Feste Assets
│   ├── ranking.py               # Phase 4: Ranking + DB
│   ├── learning_module.py       # Tägliche Auswertung + Optimierung
│   ├── prompt_optimizer.py      # Automatische Prompt-Verbesserung
│   ├── email_sender.py          # Phase 5: Tages + Wochen-Mail
│   ├── guardrails.py            # Qualitätskontrolle (Pflicht)
│   └── utils.py                 # Logging, Retry, DB-Helpers
├── setup/
│   └── historical_loader.py     # Einmaliger + Delta-Abruf
├── data/
│   ├── sp500_tickers.json       # Auto-Update monatlich
│   ├── tracking.db              # SQLite Hauptdatenbank
│   ├── learnings.json           # Long/Short Lernmodul
│   ├── prompt_versions.json     # Prompt-Versionen + Performance
│   └── cost_tracking.json       # API-Kosten pro Run
├── prompts/
│   ├── quick_filter_v1.txt      # Versionierte Prompts
│   ├── deep_analysis_v1.txt
│   └── policy_risk_v1.txt
├── tests/
│   ├── unit/                    # Ein Test pro Modul
│   ├── integration/             # End-to-End mit 5 Aktien
│   ├── fixtures/                # Mock-Daten
│   └── conftest.py
├── docs/
│   └── SPECIFICATION.md         # Diese Datei
├── CLAUDE.md
├── config.py
├── main.py
└── requirements.txt
```

---

## DATENPROVIDER – FLEXIBLES INTERFACE

### Provider-Hierarchie

**Preisdaten (OHLCV, täglich):**
1. Primary: `CapitalComProvider` (Capital.com Demo API)
2. Fallback: `YFinanceProvider` (wenn Capital.com nicht verfügbar)

**Fundamentaldaten (wöchentlich gecacht):**
- `FinnhubProvider.get_fundamentals()` → Tabelle `fundamentals_cache` (7-Tage TTL)
- Im täglichen Run: Cache aus DB lesen, kein Live-Call wenn < 7 Tage alt

```python
# src/providers/base.py
class DataProvider:
    """
    Interface für alle Datenprovider.
    Swap zwischen Capital.com und yfinance ohne Umbau.
    """
    def get_price_history(self, ticker: str, days: int) -> pd.DataFrame | None: ...
    def get_fundamentals(self, ticker: str) -> dict: ...
    def get_earnings_calendar(self, ticker: str) -> dict: ...
    def get_last_available_date(self, ticker: str) -> str | None: ...


# src/providers/capital_provider.py
class CapitalComProvider(DataProvider):
    """
    Primary OHLC-Provider (Capital.com Demo API).
    Base URL: https://demo-api-capital.backend-capital.com/
    Rate Limit: 600 Calls/Min, kostenlos
    ENV: CAPITAL_COM_API_KEY, CAPITAL_COM_PASSWORD

    Ticker-Mapping:
    - SP500-Ticker: direkt übergeben
    - Gold="GOLD", Silber="SILVER", Öl="CRUDE_OIL"
    - BTC="BITCOIN", ETH="ETHEREUM", SOL="SOLANA", XRP="XRP"
    """
    def get_price_history(self, ticker: str, days: int = 200) -> pd.DataFrame | None:
        """Holt OHLCV-Daten via Capital.com REST API."""
        ...

    def get_ohlc_after(self, ticker: str, start_date: str,
                       end_date: str) -> pd.DataFrame | None:
        """Holt OHLCV-Daten für ein bestimmtes Datumsfenster."""
        ...

    def get_premarket_price(self, ticker: str) -> float | None:
        """Vorbörslicher Kurs falls verfügbar (für pre_market Run)."""
        ...

    def get_open_positions(self) -> list[dict]:
        """GET /api/v1/positions — offene Capital.com-Trades (nur lesend)."""
        ...

    def get_closed_positions(self, date: str) -> list[dict]:
        """GET /api/v1/history/activity — heute geschlossene Trades."""
        ...

    def get_fundamentals(self, ticker: str) -> dict:
        """Leer — Fundamentals kommen von FinnhubProvider."""
        return {}

    def get_earnings_calendar(self, ticker: str) -> dict:
        """Leer — Earnings kommen von FinnhubProvider."""
        return {}


# src/providers/yfinance_provider.py
class YFinanceProvider(DataProvider):
    """
    Fallback-Provider wenn Capital.com nicht verfügbar.
    Rate-Limiting: 0.8s zwischen Tickern + Jitter, 12s alle 30 Ticker.
    """
    PAUSE_BETWEEN_TICKERS = 0.8
    PAUSE_BETWEEN_BATCHES = 12
    PAUSE_ON_ERROR        = 30
    MAX_RETRIES           = 3
    JITTER_MAX            = 0.5

    def get_price_history(self, ticker: str, days: int = 200) -> pd.DataFrame | None:
        for attempt in range(self.MAX_RETRIES):
            try:
                import random, time
                time.sleep(self.PAUSE_BETWEEN_TICKERS + random.uniform(0, self.JITTER_MAX))
                hist = yf.Ticker(ticker).history(period=f'{days}d')
                if hist is None or hist.empty or len(hist) < 20:
                    raise ValueError(f"Unzureichende Daten: {len(hist) if hist is not None else 0} Zeilen")
                return hist
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.PAUSE_ON_ERROR * (2 ** attempt))
        log_error(f"{ticker}: Alle {self.MAX_RETRIES} Versuche fehlgeschlagen")
        return None


# src/providers/finnhub_provider.py — Fundamentals mit 7-Tage Cache
class FinnhubProvider:
    """
    Fundamentaldaten via Finnhub Free Tier.
    ENV: FINNHUB_API_KEY
    Cache: fundamentals_cache-Tabelle in tracking.db (TTL 7 Tage).
    Im täglichen Run: Cache aus DB lesen → nur neu laden wenn > 7 Tage alt.
    """
    def get_fundamentals(self, ticker: str) -> dict:
        """
        Returns: {pe_ratio, forward_pe, market_cap_b, debt_equity,
                  sector, analyst_upside, consensus}
        """
        ...

    def get_earnings_calendar(self, ticker: str) -> dict:
        """
        Returns: {days_to_next, last_beat_pct}
        """
        ...
```

---

## HISTORISCHER SETUP-PULL (setup/historical_loader.py)

```python
"""
Historischer Datenabruf über Capital.com Demo API.
Lädt 3-Jahres-Historie für alle oder ausgewählte Ticker.

Verwendung:
  python setup/historical_loader.py --all              # Alle SP500-Ticker (3 Jahre)
  python setup/historical_loader.py --full-sp500       # Vollständige 500-Ticker-Liste
  python setup/historical_loader.py --tickers AAPL MSFT NVDA  # Einzelne Ticker

Delta-Logik:
  Prüft für jeden Ticker den letzten Eintrag in der DB.
  Lädt nur Daten ab diesem Datum bis heute.
"""

def get_last_db_date(conn, ticker: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(date) FROM price_history WHERE ticker = ?", (ticker,)
    ).fetchone()
    return row[0] if row and row[0] else None

def needs_update(conn, ticker: str) -> tuple[bool, str | None]:
    last_date = get_last_db_date(conn, ticker)
    if not last_date:
        return True, (datetime.now() - timedelta(days=365*3)).strftime('%Y-%m-%d')
    last_dt = datetime.strptime(last_date, '%Y-%m-%d')
    if (datetime.now() - last_dt).days <= 1:
        return False, None
    return True, (last_dt + timedelta(days=1)).strftime('%Y-%m-%d')

def run_historical_load(tickers: list[str]):
    conn     = sqlite3.connect(DB_PATH)
    provider = CapitalComProvider()
    stats    = {'updated': 0, 'skipped': 0, 'failed': 0, 'new_rows': 0}

    for i, ticker in enumerate(tickers):
        update_needed, from_date = needs_update(conn, ticker)
        if not update_needed:
            stats['skipped'] += 1
            continue
        try:
            hist = provider.get_ohlc_after(ticker, from_date,
                                           datetime.now().strftime('%Y-%m-%d'))
            if hist is None or hist.empty:
                stats['failed'] += 1
                continue
            for date, row in hist.iterrows():
                conn.execute("""
                    INSERT OR IGNORE INTO price_history
                    (ticker, date, open, high, low, close, volume, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (ticker, date.strftime('%Y-%m-%d'),
                      row['Open'], row['High'], row['Low'],
                      row['Close'], int(row['Volume']), 'capital_com'))
            conn.commit()
            stats['updated'] += 1
        except Exception as e:
            log_error(f"{ticker}: {e}")
            stats['failed'] += 1
        time.sleep(0.1)  # Capital.com erlaubt 600 Calls/Min
        if (i + 1) % 100 == 0:
            time.sleep(2)

    conn.close()
    print(f"Aktualisiert: {stats['updated']} | Übersprungen: {stats['skipped']} | "
          f"Fehler: {stats['failed']} | Neue Zeilen: {stats['new_rows']}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--all',        action='store_true',  help='Alle SP500-Ticker')
    group.add_argument('--full-sp500', action='store_true',  help='Vollständige 500-Ticker-Liste')
    group.add_argument('--tickers',    nargs='+',            help='Einzelne Ticker')
    args = parser.parse_args()

    if args.all or args.full_sp500:
        tickers = load_sp500_tickers()
    else:
        tickers = args.tickers
    run_historical_load(tickers)
```

---

## PHASE 0 – TREND-ANALYSE (trend_analyzer.py)

Einmal pro Run, vor allem anderen. Identifiziert Megatrends und
Sektor-Rotationen die alle nachfolgenden Analysen beeinflussen.

```python
TREND_PROMPT = """
Du bist Markt-Stratege. Identifiziere die aktuell dominantesten
Investment-Themen und Megatrends welche Aktienkurse kurzfristig
und mittelfristig bewegen.

SUCHBEREICHE:
Technologie: KI/LLMs, Robotics/Humanoid, Quantencomputing, Halbleiter,
             Raumfahrt, Biotech/Longevity, Cybersecurity
Makro:       Geopolitische Konflikte, Energiewende, Rohstoff-Superzyklus,
             Deglobalisierung/Reshoring, Zinspolitik
Märkte:      Sektorrotationen, M&A-Wellen, regulatorische Wellen, IPOs

FÜR JEDEN TREND:
- Stärke 1-10
- Betroffene S&P 500 Aktien (Profiteure + Verlierer)
- Nächster konkreter Katalysator mit Datum
- Geschätzte Dauer (Tage/Wochen/Monate)
- Quellen angeben

AUSGABE NUR ALS JSON:
{
  "dominant_trends": [{
    "name": "Humanoid Robotics",
    "category": "Technologie",
    "strength": 9,
    "duration": "Monate",
    "summary": "...",
    "next_catalyst": "Tesla Earnings 22.07.",
    "beneficiaries": [{"ticker": "TSLA", "reason": "Optimus-Produktion"}],
    "negatively_affected": [{"ticker": "MAN", "reason": "Automatisierung"}],
    "sources": ["Reuters 18.05."]
  }],
  "sector_rotation": {
    "capital_flowing_into": ["Energy", "Defense"],
    "capital_flowing_out": ["Consumer Discretionary"],
    "note": "Risk-off durch Geopolitik"
  },
  "trend_summary_for_email": "2-3 Sätze für E-Mail Zusammenfassung"
}
"""
```

---

## PHASE 1 – DATENABRUF (data_collector.py)

```python
def collect_all_data(tickers: list, provider: DataProvider) -> tuple[list, list]:
    """
    Gibt (erfolgreiche_daten, übersprungene_ticker) zurück.
    Batch-Pausen gegen yfinance Rate-Limiting.
    Übersprungene Aktien: learnable=False, nie ins Lernmodul.
    """
    successful, skipped = [], []
    for i, ticker in enumerate(tickers):
        if i > 0 and i % 30 == 0:
            time.sleep(YFinanceProvider.PAUSE_BETWEEN_BATCHES)
        data = provider.get_price_history(ticker)
        if data is None:
            skip = {'ticker': ticker, 'date': today(), 'learnable': False,
                    'reason': 'datenabruf_fehlgeschlagen'}
            skipped.append(skip)
            db_save_skipped(skip)
            continue
        processed = _process_ticker(ticker, data, provider)
        if processed:
            successful.append(processed)
    if len(successful) / len(tickers) < 0.70:
        send_alert_email(f"Datenabruf: nur {len(successful)}/{len(tickers)} verfügbar")
    return successful, skipped


def _process_ticker(ticker: str, hist: pd.DataFrame, provider: DataProvider) -> dict | None:
    """Berechnet alle technischen Indikatoren aus OHLCV-Daten."""
    try:
        close  = hist['Close']
        rsi    = ta.rsi(close, length=14)
        macd   = ta.macd(close)
        atr    = ta.atr(hist['High'], hist['Low'], close, length=14)
        bb     = ta.bbands(close, length=20)
        sma20  = ta.sma(close, length=20)
        sma50  = ta.sma(close, length=50)
        sma200 = ta.sma(close, length=200)
        price  = close.iloc[-1]
        prev   = close.iloc[-2]
        fund   = provider.get_fundamentals(ticker)
        earn   = provider.get_earnings_calendar(ticker)
        return {
            "ticker":                ticker,
            "price":                 round(price, 2),
            "price_change_1d":       round((price-prev)/prev*100, 2),
            "price_change_5d":       round(_pct(close, 5), 2),
            "price_change_1m":       round(_pct(close, 21), 2),
            "price_change_3m":       round(_pct(close, 63), 2),
            "rsi_14":                round(rsi.iloc[-1], 1) if rsi is not None else None,
            "rsi_trend":             _rsi_trend(rsi),
            "macd_signal":           _macd_signal(macd),
            "atr_pct":               round(atr.iloc[-1]/price*100, 2) if atr is not None else None,
            "bb_position":           _bb_pos(price, bb),
            "above_sma20":           round((price/sma20.iloc[-1]-1)*100, 2) if sma20 is not None else None,
            "above_sma50":           round((price/sma50.iloc[-1]-1)*100, 2) if sma50 is not None else None,
            "above_sma200":          round((price/sma200.iloc[-1]-1)*100, 2) if sma200 is not None else None,
            "volume_ratio":          round(_vol_ratio(hist), 2),
            "pe_ratio":              fund.get('pe_ratio'),
            "forward_pe":            fund.get('forward_pe'),
            "analyst_target_upside": fund.get('analyst_upside'),
            "analyst_consensus":     fund.get('consensus'),
            "market_cap_b":          fund.get('market_cap_b'),
            "debt_equity":           fund.get('debt_equity'),
            "sector":                fund.get('sector', 'Unknown'),
            "earnings_in_days":      earn.get('days_to_next'),
            "earnings_beat_pct":     earn.get('last_beat_pct'),
            "data_quality":          _data_quality(rsi, macd, atr),
        }
    except Exception as e:
        log_error(f"{ticker}: Verarbeitungsfehler – {e}")
        return None
```

---

## PHASE 2 – QUICK FILTER (quick_filter.py)

Kein Web-Search. Batches à 30. Lernkontext aus learnings.json.
Jeder Score braucht min. 2 konkrete Belege (Guardrail prüft das).

Ausschluss-Kriterien: market_cap_b < 5, atr_pct < 2.0, data_quality = 'low'

Trend-Boost: Wenn Aktie in Trend-Beneficiaries und Trend-Stärke >= 7
→ long_score + 0.5. Wenn in negatively_affected → short_score + 0.5.

Prompt-Template (prompts/quick_filter_v1.txt):
```
Du bist quantitativer Aktienanalyst. Analysiere {n} Aktien anhand
technischer und fundamentaler Rohdaten. Kein Web-Search in diesem Schritt.

HISTORISCHE LEARNINGS: {learning_context}
MARKTKONTEXT: {market_context}
AKTIEN-DATEN: {batch_data}

SCORING (1-10) mit PFLICHT: min. 2 konkrete Belege pro Score.
- long_score: Wahrscheinlichkeit Anstieg 1-3 Tage
- short_score: Wahrscheinlichkeit Rückgang 1-3 Tage
- confidence: low/medium/high

AUSGABE NUR ALS JSON:
{"results": [{"ticker": "AAPL", "long_score": 7.5, "short_score": 3.0,
"confidence": "high", "evidence": {"long": ["RSI 42", "SMA200 +12%"],
"short": []}, "exclude": false, "exclude_reason": null}]}
```

---

## PHASE 3 – TIEFENANALYSE (deep_analysis.py)

### Political & Policy Risk Monitor (einmal pro Run)

Sucht nach aktuellen Ereignissen mit Marktbezug:
Zölle/Handelspolitik, Zentralbank-Kommunikation, geopolitische Konflikte,
Regulierungsentscheidungen, Verteidigung/NATO, Healthcare-Regulierung,
China/Taiwan, spezifisch genannte Unternehmen durch Regierungschefs.

Trump ist ein Unterfall davon, kein Fixpunkt.
Ergebnis fließt als 8. Dimension "policy_risk" in jede Aktienanalyse.

### 8 Scoring-Dimensionen mit Pflicht-Belegen

Jede Dimension braucht min. 2 konkrete Belege mit Zahlen oder Quellen.
Kein Score ohne Beleg wird von Guardrails akzeptiert.

```python
DIMENSION_WEIGHTS = {
    "market_environment": 0.10,  # Makro, Zinsen, Sektor-Trend
    "company_quality":    0.18,  # Earnings, Management, Guidance
    "valuation":          0.12,  # P/E vs. Peers, Analyst-Kursziel
    "momentum":           0.22,  # RSI, MACD, SMA, Rel. Stärke
    "risk":               0.10,  # ATR, Schulden, regulatorische Risiken
    "sector_trend":       0.10,  # Sektor-ETF, Kapitalflüsse
    "catalyst":           0.10,  # Konkrete Ereignisse 1-7 Tage
    "policy_risk":        0.08,  # aus Policy Monitor
}
```

### Signal-Konsistenz-Check (Pflicht vor Ausgabe)

Long braucht momentum >= 6.0.
Short braucht momentum <= 7.0.
Bei Widerspruch: Analyse verworfen, nicht ausgegeben.

### TP/SL-Berechnung (ATR-basiert, immer min. 1:2 R/R)

```python
def calculate_tp_sl(atr_pct):
    if atr_pct < 1.0:   sl = atr_pct * 0.8   # Ruhige Aktie (WMT)
    elif atr_pct < 2.0: sl = atr_pct * 1.0   # Moderat (AAPL)
    else:               sl = atr_pct * 1.2   # Hoch volatil (NVDA)
    tp                = sl * 2.0
    trailing_activate = tp * 0.5
    trailing_distance = sl * 0.6
    return sl, tp, trailing_activate, trailing_distance
```

---

## PHASE 3B – COMMODITIES + CRYPTO (commodities_crypto.py)

Immer analysiert, kein Filter, eigener Prompt.

```python
COMMODITY_TICKERS = {"Gold": "GC=F", "Silber": "SI=F", "Öl": "CL=F"}
CRYPTO_TICKERS    = {"Bitcoin": "BTC-USD", "Ethereum": "ETH-USD",
                     "Solana": "SOL-USD", "XRP": "XRP-USD"}

def get_fear_greed():
    r = requests.get("https://api.alternative.me/fng/", timeout=5)
    d = r.json()["data"][0]
    return {"value": int(d["value"]), "label": d["value_classification"]}
```

Analyse: Gold/Silber → Zinsen + USD, Öl → OPEC + Geopolitik,
Crypto → Fear & Greed + BTC-Dominanz. Policy Monitor fließt ein.

---

## PHASE 4 – RANKING + DATENBANK (ranking.py)

### Dynamische Schwellenwerte aus Learnings

```python
def get_thresholds() -> tuple[float, float]:
    try:
        with open(LEARNINGS_PATH) as f:
            l = json.load(f)
        return (l['dynamic_thresholds']['long_threshold_current'],
                l['dynamic_thresholds']['short_threshold_current'])
    except:
        return 7.0, 7.0
```

Nur Analysen die Guardrails bestehen landen im Ranking.
Top 10 Long + Top 10 Short nach probability_pct sortiert.
Commodities und Crypto immer ausgegeben, unabhängig vom Score.

### Vollständiges SQLite-Schema

```sql
-- Kursdaten (historisch + täglich incremental via Capital.com)
CREATE TABLE price_history (
    ticker TEXT, date TEXT, open REAL, high REAL,
    low REAL, close REAL NOT NULL, volume INTEGER,
    premarket_price REAL,                 -- nullable, Capital.com vorbörslich
    source TEXT DEFAULT 'capital_com', UNIQUE(ticker, date)
);

-- Technische Indikatoren (berechnet, gecacht)
CREATE TABLE technical_indicators (
    ticker TEXT, date TEXT, rsi_14 REAL, macd_signal TEXT,
    atr_pct REAL, bb_position REAL, above_sma20 REAL,
    above_sma50 REAL, above_sma200 REAL, volume_ratio REAL,
    UNIQUE(ticker, date)
);

-- Fundamentaldaten (quartalsweise)
CREATE TABLE fundamentals (
    ticker TEXT, report_date TEXT, eps_actual REAL,
    eps_estimated REAL, eps_beat_pct REAL, revenue_actual REAL,
    guidance_raised BOOLEAN, pe_ratio REAL, forward_pe REAL,
    debt_equity REAL, UNIQUE(ticker, report_date)
);

-- News-Summaries (nur 2-3 Sätze, nie Volltext, 90 Tage Retention)
CREATE TABLE news_summaries (
    ticker TEXT, date TEXT, run_type TEXT, summary TEXT NOT NULL,
    sentiment TEXT, source TEXT, market_impact TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trend-Analysen (täglich, 180 Tage Retention)
CREATE TABLE trend_analyses (
    date TEXT, run_type TEXT, trend_name TEXT, strength INTEGER,
    duration_estimate TEXT, summary TEXT, beneficiary_tickers TEXT,
    negative_tickers TEXT, next_catalyst TEXT, UNIQUE(date, trend_name)
);

-- Markt-Kontext (täglich pro Run)
CREATE TABLE market_context (
    date TEXT, run_type TEXT, sp500_change_pct REAL, vix_level REAL,
    market_regime TEXT, oil_price REAL, gold_price REAL, btc_price REAL,
    fear_greed_value INTEGER, policy_risk_level TEXT,
    sector_rotation_in TEXT, sector_rotation_out TEXT, macro_summary TEXT,
    UNIQUE(date, run_type)
);

-- Vorhersagen (Lernmodul)
CREATE TABLE predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT, run_type TEXT, asset_class TEXT, ticker TEXT, direction TEXT,
    entry_price REAL, tp_price REAL, tp_pct REAL, sl_price REAL,
    sl_pct REAL, rr_ratio REAL, total_score REAL, probability_pct INTEGER,
    confidence TEXT, score_market_env REAL, score_company REAL,
    score_valuation REAL, score_momentum REAL, score_risk REAL,
    score_sector REAL, score_catalyst REAL, score_policy REAL,
    atr_pct REAL, rsi_at_entry REAL, volume_ratio REAL, market_regime TEXT,
    vix_at_prediction REAL, sector TEXT, trend_boost TEXT,
    earnings_warning BOOLEAN, summary TEXT,
    hold_day INTEGER DEFAULT 0,           -- aktueller Haltetag, täglich +1
    extended_hold BOOLEAN DEFAULT 0,      -- True ab Tag 2
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Ergebnisse (täglich befüllt)
CREATE TABLE outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id INTEGER REFERENCES predictions(id),
    direction TEXT, evaluated_date TEXT, price_after_eod REAL,
    price_change_eod_pct REAL, correct_direction_eod BOOLEAN,
    tp_hit BOOLEAN, sl_hit BOOLEAN, profit_loss_eur REAL,
    hold_day INTEGER,                     -- Haltetag bei Close
    extended_hold BOOLEAN,                -- True wenn > 1 Tag gehalten
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fundamentals-Cache (Finnhub, 7-Tage TTL)
CREATE TABLE IF NOT EXISTS fundamentals_cache (
    ticker TEXT NOT NULL,
    fetched_date TEXT NOT NULL,
    pe_ratio REAL,
    forward_pe REAL,
    market_cap_b REAL,
    debt_equity REAL,
    sector TEXT,
    analyst_upside REAL,
    consensus TEXT,
    UNIQUE(ticker)
);

-- Übersprungene Ticker (nie lernbar)
CREATE TABLE skipped_tickers (
    ticker TEXT, date TEXT, run_type TEXT, reason TEXT,
    learnable BOOLEAN DEFAULT FALSE, skip_count INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Prompt-Versionen (A/B-Testing)
CREATE TABLE prompt_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_name TEXT, version INTEGER, content TEXT, created_date TEXT,
    long_accuracy REAL, short_accuracy REAL, total_predictions INTEGER,
    is_active BOOLEAN DEFAULT TRUE, replaced_date TEXT
);
```

### Automatische Datenpflege (täglich)

```python
def cleanup_old_data(conn):
    conn.execute("DELETE FROM news_summaries WHERE date < date('now', '-90 days')")
    conn.execute("DELETE FROM trend_analyses WHERE date < date('now', '-180 days')")
    conn.execute("DELETE FROM skipped_tickers WHERE date < date('now', '-30 days')")
    conn.commit()
```

---

## LEARNING MODULE – GETRENNTE LONG/SHORT OPTIMIERUNG

```python
def evaluate_yesterday():
    """
    Täglich 15:00 Uhr MEZ. Wertet Vortags-Vorhersagen aus.
    Long und Short getrennt tracken und optimieren.
    Übersprungene Aktien (learnable=False) niemals auswerten.
    """
    predictions = db_load_predictions(date=yesterday, run_type='pre_market')
    long_results, short_results = [], []

    for pred in predictions:
        if pred['learnable'] is False:
            continue

        price  = yf.Ticker(pred['ticker']).history(period='2d')['Close'].iloc[-1]
        change = (price - pred['entry_price']) / pred['entry_price'] * 100
        correct = (pred['direction']=='long' and change>0) or \
                  (pred['direction']=='short' and change<0)
        tp_hit  = abs(change) >= pred['tp_pct'] and correct
        sl_hit  = abs(change) >= pred['sl_pct'] and not correct

        exposure = 500 * 5  # 500 EUR Margin, 5:1 Hebel
        pl = (change/100)*exposure*(1 if pred['direction']=='long' else -1)
        pl = max(min(pl, pred['tp_pct']/100*exposure), -pred['sl_pct']/100*exposure)

        result = {**pred, 'correct': correct, 'tp_hit': tp_hit,
                  'sl_hit': sl_hit, 'pl_eur': pl}

        if pred['direction'] == 'long': long_results.append(result)
        else:                           short_results.append(result)
        db_save_outcome(result)

    update_long_learnings(long_results)
    update_short_learnings(short_results)
    update_dynamic_thresholds()


def update_dynamic_thresholds():
    """Passt Score-Schwellenwerte an wenn Long/Short signifikant abweichen."""
    with open(LEARNINGS_PATH) as f:
        l = json.load(f)

    long_acc  = l['long_performance']['overall'].get('correct_direction_eod_pct', 50)
    short_acc = l['short_performance']['overall'].get('correct_direction_eod_pct', 50)
    diff = short_acc - long_acc

    if diff > 10:    # Short deutlich besser
        l['dynamic_thresholds']['long_threshold_current']  = round(7.0 + diff/100, 2)
        l['dynamic_thresholds']['short_threshold_current'] = round(7.0 - diff/200, 2)
    elif diff < -10: # Long deutlich besser
        l['dynamic_thresholds']['long_threshold_current']  = round(7.0 - abs(diff)/200, 2)
        l['dynamic_thresholds']['short_threshold_current'] = round(7.0 + abs(diff)/100, 2)
    else:
        l['dynamic_thresholds']['long_threshold_current']  = 7.0
        l['dynamic_thresholds']['short_threshold_current'] = 7.0

    l['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    with open(LEARNINGS_PATH, 'w') as f:
        json.dump(l, f, indent=2, ensure_ascii=False)
```

---

## PROMPT OPTIMIZER (src/prompt_optimizer.py)

Automatische Prompt-Verbesserung – läuft wöchentlich sonntags.

```python
OPTIMIZER_PROMPT = """
Du bist KI-System-Optimierer. Analysiere die Performance der aktuellen
Analyse-Prompts und schlage konkrete Verbesserungen vor.

AKTUELLE PROMPT-VERSION: {current_prompt}
PERFORMANCE (letzte 4 Wochen):
Long-Trefferquote: {long_accuracy}%
Short-Trefferquote: {short_accuracy}%
HÄUFIGSTE FEHLMUSTER: {error_patterns}
BEISPIELE FALSCHER VORHERSAGEN: {wrong_predictions}

AUFGABE:
1. Identifiziere systematische Schwächen im Prompt
2. Schlage konkrete Textänderungen vor
3. Erkläre warum diese die Trefferquote verbessern sollten

AUSGABE ALS JSON:
{
  "weaknesses_found": ["..."],
  "proposed_changes": [{"section": "...", "current": "...",
    "proposed": "...", "reasoning": "..."}],
  "expected_improvement": "Long +3-5%, weil..."
}
"""
# Neue Version 1 Woche A/B-testen. Bessere Version gewinnt automatisch.
```

---

## GUARDRAILS (src/guardrails.py)

Pflichtmodul. Jede Analyse muss bestehen bevor sie ins Ranking kommt.

```python
class GuardrailsChecker:
    MAX_COST_PER_RUN_EUR = 2.00
    MIN_SOURCES          = 2
    MIN_EVIDENCE         = 2    # Belege je Score-Dimension
    MIN_RR_RATIO         = 1.5

    def check_analysis(self, a: dict) -> tuple[bool, list[str]]:
        errors = []
        for f in ['ticker','total_score','direction','confidence','tp_price',
                  'sl_price','summary','sources_used','signal_consistency_check']:
            if f not in a or a[f] is None:
                errors.append(f"Pflichtfeld fehlt: {f}")
        if len(a.get('sources_used',[])) < self.MIN_SOURCES:
            errors.append(f"Zu wenige Quellen")
        for dim, sd in a.get('scores',{}).items():
            if len(sd.get('evidence',[])) < self.MIN_EVIDENCE:
                errors.append(f"{dim}: zu wenige Belege")
        p, tp, sl = a.get('current_price',0), a.get('tp_price',0), a.get('sl_price',0)
        if a.get('direction') == 'long':
            if tp <= p: errors.append(f"Long TP {tp} nicht über Einstieg {p}")
            if sl >= p: errors.append(f"Long SL {sl} nicht unter Einstieg {p}")
        elif a.get('direction') == 'short':
            if tp >= p: errors.append(f"Short TP {tp} nicht unter Einstieg {p}")
            if sl <= p: errors.append(f"Short SL {sl} nicht über Einstieg {p}")
        if a.get('rr_ratio',0) < self.MIN_RR_RATIO:
            errors.append(f"R/R {a.get('rr_ratio')} < {self.MIN_RR_RATIO}")
        if a.get('data_quality')=='low' and a.get('confidence')=='high':
            errors.append("Confidence 'high' bei data_quality 'low'")
        return len(errors)==0, errors
```

---

## PHASE 5 – E-MAIL (email_sender.py)

### Tägliche E-Mail – 3 Sektionen

**Sektion 1: S&P 500 – Top 10 Long + Top 10 Short**
Tabelle: Rang, Ticker, Score, Wahrscheinlichkeit, Kurs, TP, SL, R/R,
ATR/Tag, Trend-Boost Flag, Policy-Risk Flag, Kurzbegründung.

**Sektion 2: Trend-Analyse**
Dunkles Design, Megatrends als Karten mit Stärke, Profiteuren, Verlierern,
nächstem Katalysator. Sektor-Rotation Übersicht.

**Sektion 3: Rohstoffe + Crypto**
Gold, Silber, Öl mit Direction, Score, Wahrscheinlichkeit, TP/SL.
BTC, ETH, SOL, XRP mit Direction, Score, Fear & Greed, TP/SL.
Gold/Silver-Ratio als Zusatzinfo.

**Footer immer:** Tages-Performance gestern (Long X/10, Short Y/10,
simulierter P/L), Übersprungene Aktien, Disclaimer, Run-Kosten.

### Wöchentliche Performance-Mail (sonntags 20:00 Uhr MEZ)

```
Betreff: [Shares_Future] Woche KW21 – Trefferquote + Learnings

WOCHENPERFORMANCE
Long  Trefferquote: 34/60 (56.7%) | Ø P/L: +18.50 EUR/Trade
Short Trefferquote: 38/60 (63.3%) | Ø P/L: +21.80 EUR/Trade
Sim. Gesamt-P/L:    +1.210 EUR

STÄRKSTE SIGNALE
✅ Guidance-Cut Short:  4/4 (100%)
✅ Earnings-Beat Long:  7/10 (70%)
❌ Pre-Earnings Long:   3/8 (37%) – schwach

NEUE LERNREGELN
→ SOX-ETF < -2%: Semiconductor-Longs gesperrt
→ Analyst > 15 Buy-Ratings: Short-Score -2 Punkte

PROMPT-OPTIMIERUNG
v2 im A/B-Test: v1: 58.1% vs v2: 61.3% (noch 4 Tage)

NÄCHSTE WOCHE – WICHTIGE EVENTS
Earnings: NVDA (Mi), WMT (Do)
Events:   FOMC-Protokoll (Mi)
```

---

## GITHUB ACTIONS (.github/workflows/analyze.yml)

```yaml
name: Shares_Future Analysis

on:
  schedule:
    # pre_market 14:00 Berlin (Sommer UTC+2 / Winter UTC+1)
    - cron: '0 12 * * 1-5'    # Sommer (MESZ)
    - cron: '0 13 * * 1-5'    # Winter (MEZ)
    # evaluate 15:00 Berlin
    - cron: '0 13 * * 1-5'    # Sommer
    - cron: '0 14 * * 1-5'    # Winter
    # midday 16:15 Berlin
    - cron: '15 14 * * 1-5'   # Sommer
    - cron: '15 15 * * 1-5'   # Winter
    # position_check 17:30 Berlin
    - cron: '30 15 * * 1-5'   # Sommer
    - cron: '30 16 * * 1-5'   # Winter
    # close 22:30 Berlin
    - cron: '30 20 * * 1-5'   # Sommer
    - cron: '30 21 * * 1-5'   # Winter
    # weekly Sonntag 20:00 Berlin
    - cron: '0 18 * * 0'      # Sommer
    - cron: '0 19 * * 0'      # Winter
  workflow_dispatch:

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Restore DB
        uses: actions/cache@v3
        with:
          path: data/tracking.db
          key: db-${{ github.run_number }}
          restore-keys: db-
      - uses: actions/setup-python@v4
        with: {python-version: '3.11'}
      - run: pip install -r requirements.txt
      - name: Run
        env:
          ANTHROPIC_API_KEY:    ${{ secrets.ANTHROPIC_API_KEY }}
          SENDGRID_API_KEY:     ${{ secrets.SENDGRID_API_KEY }}
          CAPITAL_COM_API_KEY:  ${{ secrets.CAPITAL_COM_API_KEY }}
          CAPITAL_COM_PASSWORD: ${{ secrets.CAPITAL_COM_PASSWORD }}
          FINNHUB_API_KEY:      ${{ secrets.FINNHUB_API_KEY }}
          EMAIL_TO:             ${{ secrets.EMAIL_TO }}
          EMAIL_FROM:           ${{ secrets.EMAIL_FROM }}
        run: |
          HOUR=$(TZ="Europe/Berlin" date +%H)
          MIN=$(TZ="Europe/Berlin" date +%M)
          DOW=$(TZ="Europe/Berlin" date +%u)
          if [ "$DOW" = "7" ] && [ "$HOUR" = "20" ]; then TYPE="weekly"
          elif [ "$HOUR" = "15" ] && [ "$MIN" -lt "30" ]; then TYPE="evaluate"
          elif [ "$HOUR" = "14" ] && [ "$MIN" -lt "30" ]; then TYPE="pre_market"
          elif [ "$HOUR" = "16" ] && [ "$MIN" -ge "10" ]; then TYPE="midday"
          elif [ "$HOUR" = "17" ] && [ "$MIN" -ge "30" ]; then TYPE="position_check"
          elif [ "$HOUR" = "22" ] || [ "$HOUR" = "21" ]; then TYPE="close"
          else TYPE="close"; fi
          python main.py --run-type $TYPE
      - name: Save DB
        uses: actions/cache@v3
        with:
          path: data/tracking.db
          key: db-${{ github.run_number }}
```

---

## KONFIGURATION (config.py)

```python
import os

ANTHROPIC_API_KEY    = os.getenv("ANTHROPIC_API_KEY")
SENDGRID_API_KEY     = os.getenv("SENDGRID_API_KEY")
EMAIL_TO             = os.getenv("EMAIL_TO")
EMAIL_FROM           = os.getenv("EMAIL_FROM")
CAPITAL_COM_API_KEY  = os.getenv("CAPITAL_COM_API_KEY")
CAPITAL_COM_PASSWORD = os.getenv("CAPITAL_COM_PASSWORD")
FINNHUB_API_KEY      = os.getenv("FINNHUB_API_KEY")

CLAUDE_MODEL    = "claude-sonnet-4-6"
SIMULATION_ONLY = True   # NIEMALS auf False setzen

SP500_MIN_MARKET_CAP_B = 5
SP500_MIN_ATR_PCT      = 2.0        # Mindest-ATR für CFD-Eignung
MAX_DEEP_ANALYSIS      = 80
BATCH_SIZE_QUICK       = 30
RR_RATIO_MIN           = 1.5
CFD_MARGIN_EUR         = 500
CFD_LEVERAGE           = 5
MAX_HOLD_DAYS          = 5          # Zwangsschluss nach 5 Handelstagen
HOLD_TARGET            = "intraday" # Primärziel: Intraday-Close

DIMENSION_WEIGHTS = {
    "market_environment": 0.10,
    "company_quality":    0.18,
    "valuation":          0.12,
    "momentum":           0.22,
    "risk":               0.10,
    "sector_trend":       0.10,
    "catalyst":           0.10,
    "policy_risk":        0.08,
}

COMMODITY_TICKERS = {"Gold": "GC=F", "Silber": "SI=F", "Öl": "CL=F"}
CRYPTO_TICKERS    = {"Bitcoin": "BTC-USD", "Ethereum": "ETH-USD",
                     "Solana": "SOL-USD", "XRP": "XRP-USD"}

MAX_COST_PER_RUN_EUR  = 2.00
CLAUDE_PARALLEL_CALLS = 5
YFINANCE_PAUSE_SEC    = 0.8
YFINANCE_BATCH_PAUSE  = 12
```

---

## TESTS

```
tests/
├── unit/
│   ├── test_data_collector.py    # yfinance Rate-Limiting, Retry-Logik
│   ├── test_quick_filter.py      # Batch-Analyse, Trend-Boost, Ausschlüsse
│   ├── test_deep_analysis.py     # Claude API Mock, JSON-Parsing
│   ├── test_guardrails.py        # Alle Qualitätsprüfungen
│   ├── test_learning_module.py   # Long/Short getrennt, Skip-Ausschluss
│   ├── test_ranking.py           # Schwellenwerte, Sortierung
│   ├── test_email_sender.py      # HTML-Rendering, Pflichtfelder
│   └── test_prompt_optimizer.py  # Versions-Management
├── integration/
│   └── test_full_pipeline.py     # End-to-End 5 Aktien
├── fixtures/
│   ├── mock_yfinance.py
│   ├── mock_claude.py
│   └── sample_data.json
└── conftest.py                   # In-Memory SQLite, geteilte Fixtures

Mindest-Coverage: 80% (in CI erzwungen)
```

---

## ENTWICKLUNGS-REIHENFOLGE (strikt einhalten, nach jedem Schritt testen)

```
1.  config.py + requirements.txt + .env.example
2.  src/utils.py – Logging, Retry, DB-Setup, Hilfsfunktionen
3.  tests/conftest.py – In-Memory DB, Mock-Fixtures
4.  src/providers/base.py + capital_provider.py + yfinance_provider.py + finnhub_provider.py
    → pytest tests/unit/test_data_collector.py ✓
5.  setup/historical_loader.py – full + delta Modus
    → Lokal testen: python setup/historical_loader.py --mode full --ticker AAPL
6.  src/guardrails.py
    → pytest tests/unit/test_guardrails.py ✓
7.  src/data_collector.py
    → pytest tests/unit/test_data_collector.py ✓
8.  src/trend_analyzer.py (Phase 0)
    → pytest tests/unit/test_trend_analyzer.py ✓
9.  src/quick_filter.py (Phase 2, kein Web-Search)
    → pytest tests/unit/test_quick_filter.py ✓
10. src/deep_analysis.py (Phase 3, Web-Search + Policy Monitor)
    → pytest tests/unit/test_deep_analysis.py ✓
11. src/commodities_crypto.py (Phase 3b)
12. src/ranking.py + SQLite vollständig aufsetzen
    → pytest tests/unit/test_ranking.py ✓
13. src/learning_module.py (Long/Short getrennt)
    → pytest tests/unit/test_learning_module.py ✓
14. src/prompt_optimizer.py
    → pytest tests/unit/test_prompt_optimizer.py ✓
15. src/email_sender.py (Tages + Wochen-Mail)
    → pytest tests/unit/test_email_sender.py ✓
16. main.py – alle Phasen integriert
    → pytest tests/integration/test_full_pipeline.py ✓
    → pytest tests/ --cov=src --cov-fail-under=80 ✓
17. .github/workflows/analyze.yml + test.yml
18. README.md mit Setup-Guide
```

---

## DISCLAIMER

```python
DISCLAIMER = """
Shares_Future ist ein automatisiertes Research- und Paper-Trading-System
ohne automatische Orderausführung. Alle Analysen dienen ausschließlich
zu Informationszwecken und stellen KEINE Anlageberatung dar.
CFD-Handel kann zum Totalverlust führen. Keine Garantie für Prognosen.
"""
```

---

*Shares_Future | Version 5.0 | 2026-05-22*
