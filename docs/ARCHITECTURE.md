# Shares_Future – Architektur & Design

## Überblick

Das System folgt einer **Pipeline-Architektur** mit 6 Phasen (Phase 0–5), die sequenziell ausgeführt werden. Jede Phase ist entkoppelt über klare Daten-Schnittstellen und kann unabhängig getestet werden.

```
┌─────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR (main.py)                      │
│  Dispatch: --run-type {pre_market|midday|close|evaluate|weekly}  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  PHASE 0: TREND-ANALYSE                          │
│  Input: —                                                         │
│  Claude: 1× Sonnet + web_search                                  │
│  Output: {trends[], sector_rotation, trend_summary}              │
│  Cost: ~0.20 EUR                                                 │
│  Fail: ❌ Abort (TrendAnalyzerError propagates, no email)        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  PHASE 1: DATENSAMMLUNG                          │
│  Input: —                                                         │
│  Quelle: yfinance (90 Tage, 500 Aktien + Commodities/Crypto)    │
│  Berechnen: RSI-14, MACD, ATR, SMA200, PE, Volume-Ratio, etc.   │
│  Output: list[{ticker, price, rsi_14, macd, ..., intraday_range}│
│  Cost: ~0.00 EUR                                                 │
│  Fail: ✅ Skip Ticker, continue                                   │
│  DB: tech_indicators-Table persistieren                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              PHASE 2: QUICK-FILTER (Batch-Scoring)               │
│  Input: phase1_data[], trend_context                             │
│  Claude: Haiku × ceil(500/30) Calls (30er-Batches)              │
│  Output: list[{ticker, long_score, short_score, confidence}]    │
│  Logik: Top 80 Long + Top 80 Short behalten                     │
│  Cost: ~0.15 EUR                                                 │
│  Fail: ✅ Skip Batch, continue                                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│            PHASE 3: POLICY-MONITOR (1× pro Run)                  │
│  Input: —                                                         │
│  Claude: 1× Sonnet + web_search                                  │
│  Output: {policy_risk_level, events[], summary}                  │
│  Scope: Tariffs, Zentralbank, Geopolitik, Regulierung          │
│  Cost: ~0.10 EUR                                                 │
│  Fail: ✅ Empty context, continue (aber warn)                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│          PHASE 3: DEEP-ANALYSIS (Top 80 Long/Short)              │
│  Input: quick_filter_top_80[], trend_context, policy_context    │
│  Claude: Sonnet × 80 Calls (1 Ticker pro Call) + web_search     │
│  Output: list[{ticker, direction, scores{8}, hold_days, ...}]   │
│  8-Dim Score: market_env, company_quality, valuation, momentum, │
│              risk, sector_trend, catalyst, policy_risk           │
│  Cost: ~2.50 EUR (biggest cost)                                  │
│  Guardrails: R/R ≥ 1.5, hold_days ≤ 3, intraday_range ≥ 1%    │
│  Fail: ✅ Skip Ticker, continue                                   │
│  Order: Sequential (nicht parallel) für deterministisches Cost-Tracking│
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│      PHASE 3b: COMMODITIES & CRYPTO (7 Fixed Assets)             │
│  Input: trend_context, policy_context, Fear&Greed Index         │
│  Assets: Gold, Silver, Oil, BTC, ETH, SOL, XRP                  │
│  Claude: Sonnet × 7 Calls + web_search                          │
│  Output: list[{ticker="Gold", direction, scores{8}, ...}]       │
│  Extra Context: fear_greed_value, btc_dominance_pct, ratio      │
│  Cost: ~0.35 EUR                                                 │
│  Guardrails: Same as Phase 3 (8-Dim, R/R, hold_days, range)    │
│  Fail: ✅ Skip Asset, continue                                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│       PHASE 4a: PORTFOLIO-CHECK (Offene Positionen)              │
│  Input: db.predictions[status='open' & date ≤ 3 days ago],      │
│         current_snapshots, trend_context, policy_context        │
│  Claude: Sonnet × N offene Positionen + web_search              │
│  Output: list[{prediction_id, action="HALTEN|SCHLIESSEN|..."}]  │
│  Logik: Jede offene Position wird neu evaluiert                 │
│  Cost: ~0.20 EUR (abhängig von offenen Positionen)              │
│  Fail: ✅ Skip Position, continue                                │
│  DB: position_recommendations-Table schreiben                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│         PHASE 4: RANKING & PERSISTIERUNG                         │
│  Input: deep_analysis[], commodities_crypto[], phase4a_recs    │
│  Logik: Guardrail-Filter → Top-10 Long/Short nach prob_pct      │
│  Output: {top_long[], top_short[], commodities_crypto[]}        │
│  DB: predictions-Table schreiben (future_outcome tracking)       │
│  Learnable: Alle = true (außer skip-by-guardrails)             │
│  Cost: ~0.00 EUR                                                 │
│  Fail: ❌ Propagates (Ranking MUSS funktionieren)               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              PHASE 5: E-MAIL & REPORTING                         │
│  Input: top_10_long, top_10_short, commodities_crypto,          │
│         yesterday_outcomes_agg, cost_summary                     │
│  HTML: 4 Sektionen (Portfolio → Stocks → Trends → Commodities)  │
│  SendGrid: E-Mail an EMAIL_TO                                   │
│  Cost: ~0.00 EUR (SendGrid kostenlos)                           │
│  Fail: ⚠️ Log, aber keine Abort (beste Anstrengung)             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Module & Responsibilities

### 1. **`src/data_collector.py`** (Phase 1)

Datensammlung für 500 SP500-Aktien + Commodities/Crypto.

```python
def collect(
    provider: DataProvider,
    tickers: list[str],
    cost_tracker: CostTracker,
) -> tuple[list[dict], list[str]]:
    """
    Returns: (ok_data, skipped_tickers)
    - ok_data: [{ticker, price, rsi_14, macd, atr_pct, above_sma200, 
                volume_ratio, pe_ratio, market_cap_b, sector, earnings_in_days,
                earnings_beat_pct, data_quality, intraday_range_pct}]
    - skipped_tickers: list (no data, bad quality, etc.)
    
    Rate Limiting: 0.8s/Ticker + 12s/30er-Batch
    Data Quality: 3 Levels (high/medium/low)
    """
```

**Invarianten:**
- Mindestens 20 Zeilen historische Daten pro Ticker
- `intraday_range_pct` = (High - Low) / Close × 100 (letzte 5 Tage)
- `above_sma200` = (Price - SMA200) / SMA200 × 100
- RSI-14, MACD, ATR berechenbar (oder `data_quality=low`)

---

### 2. **`src/trend_analyzer.py`** (Phase 0)

Makro-Trends identifizieren (einmalig pro Run).

```python
def analyze_trends(cost_tracker: CostTracker) -> dict:
    """
    1 Sonnet + web_search Call.
    Returns: {
        trends: [{name, strength:0-10, duration_estimate, summary, 
                 beneficiary_tickers[], negative_tickers[]}],
        sector_rotation: {into: [XLK], out_of: [XLU]},
        trend_summary: str
    }
    """
```

**Fail-Verhalten:** `TrendAnalyzerError` propagates → kein Email (Phase 0 ist fatal).

---

### 3. **`src/quick_filter.py`** (Phase 2)

Batch-Scoring ohne Web-Search (reduziert auf Top 80).

```python
def quick_filter_batch(
    batch: list[dict],  # Phase 1 data
    trend_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """
    Haiku Call (30er-Batch).
    Returns: [{ticker, long_score:0-10, short_score:0-10, 
              confidence, evidence[], exclude:bool}]
    
    Logik:
    - long_score ≥ 6.5 & short_score ≤ 4.0 → Long
    - short_score ≥ 6.5 & long_score ≤ 4.0 → Short
    - Sonst: beide Scores gleich, direction=none → Guardrail droppt
    """
```

**Fail-Verhalten:** `QuickFilterError` → skip Batch, continue mit nächstem.

---

### 4. **`src/deep_analysis.py`** (Phase 3)

Tiefenanalyse mit Web-Search (8-dimensionales Scoring).

```python
def run_policy_monitor(date, run_type, cost_tracker) -> dict:
    """
    1 Sonnet + web_search Call EINMALIG pro Run.
    Returns: {policy_risk_level:0-10, events:[], summary:str}
    """

def analyze_asset(
    ticker_data: dict,
    quick_filter_result: dict,
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> dict | None:
    """
    Sonnet + web_search.
    Skip ohne Claude-Call wenn quick_filter_result['exclude']=True.
    
    Returns: {
        ticker, direction: "long"|"short"|"none",
        probability_pct: 0-100,
        scores: {
            market_environment: {value, evidence[]},
            company_quality: {value, evidence[]},
            ...  (8 dimensions)
        },
        hold_days_recommended: 1-3,
        intraday_range_pct: 1.0+,
        technical_indicators: {...},
        sources_used: []
    }
    
    Guardrails (nach dieser Funktion geprüft):
    - hold_days > 3 → reject
    - intraday_range < 1.0 → reject
    - R/R < 1.5 → reject
    - direction = "none" → reject (beide Scores gleich)
    """
```

**Fail-Verhalten:** `DeepAnalysisError` → skip Ticker, continue.

**Billing:** `cost_tracker.add_from_result(result)` **VOR** JSON parse.

---

### 5. **`src/commodities_crypto.py`** (Phase 3b)

7 feste Assets (Gold, Silver, Oil, BTC, ETH, SOL, XRP).

```python
def fetch_fear_greed() -> dict | None:
    """Externe API: https://api.alternative.me/fng/
    Returns: {value: 0-100, label: "Extreme Fear"|...}"""

def analyze_commodities_and_crypto(
    ticker_datas: dict,
    trend_context: dict,
    policy_context: dict,
    extra_context: dict,  # {fear_greed_value, btc_dominance, ...}
    cost_tracker: CostTracker,
) -> list[dict]:
    """
    Sonnet × 7 (1 pro Asset) + web_search.
    Same schema as deep_analysis (8-Dim + hold_days + intraday_range).
    
    Extra context für Prompt:
    - fear_greed_value (on-chain sentiment)
    - btc_dominance_pct (crypto market share)
    - gold_silver_ratio (commodity divergence)
    """
```

**Fail-Verhalten:** `CommoditiesCryptoError` → skip Asset, continue.

---

### 6. **`src/portfolio_check.py`** (Phase 4a)

Evaluiert täglich alle offenen Positionen (max 3 Tage alt).

```python
def check_open_positions(
    conn: sqlite3.Connection,
    today: str,
    run_type: str,
    snapshots_by_ticker: dict,  # {ticker: {price, ...}}
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """
    Für jede offene Position (≤ 3 Tage alt):
      - Sonnet + web_search Call
      - Returns: {prediction_id, action:"HALTEN"|"SCHLIESSEN"|"ANPASSEN",
                 reason, new_sl_price, new_tp_price, market_context_changed}
      - Speichert position_recommendations-Row
    
    Skip: Position wenn Ticker kein aktueller Snapshot.
    """
```

**Fail-Verhalten:** `PortfolioCheckError` → skip Position, continue.

---

### 7. **`src/ranking.py`** (Phase 4)

Filtert, sortiert und persistiert Top-10-Setups.

```python
def rank_and_persist(
    conn: sqlite3.Connection,
    date: str,
    run_type: str,
    stock_analyses: list[dict],       # Phase 3 output
    commodity_crypto_analyses: list,  # Phase 3b output
    market_context: dict,
) -> dict:
    """
    Logik:
    1. Guardrail-Filter (hold_days ≤ 3, intraday_range ≥ 1%, R/R ≥ 1.5, no "none")
    2. Split Long/Short
    3. Sort by probability_pct DESC
    4. Keep Top 10 each, ALL commodities/crypto
    5. Persist to db.predictions
    
    Returns: {top_long[], top_short[], commodities_crypto[]}
    """
```

**Fail-Verhalten:** `RankingError` → propagates (MUSS funktionieren).

---

### 8. **`src/evaluator.py`** (Täglich, nach Close)

Walk-Forward OHLC-Hit-Check für gestrige Setups.

```python
def evaluate_open_predictions(
    conn: sqlite3.Connection,
    today: str,
    price_provider: DataProvider,
) -> int:
    """
    Für jede offene & learnable & date<today Prediction:
      1. Fetch OHLC-Fenster [pred.date → today]
      2. Walk-Forward Hit-Check (max 3 Bars)
      3. Bestimme exit_reason + exit_price + days_to_close
      4. Atomisch update outcomes-Row + prediction.status
    
    Exit Reasons:
      - "tp_hit": TP erreicht (optimistisch)
      - "sl_hit": SL erreicht (stop loss)
      - "pessimistic_overlap": TP & SL same bar → SL annehmen
      - "timeout": 3 Bars vorbei, kein Hit
      - "data_missing": OHLC-Fetch failed/empty
    
    Profit/Loss: CFD Simulation @ 500 EUR Margin, 5:1 Hebel
    """
```

---

### 9. **`src/email_sender.py`** (Phase 5)

Rendert HTML und sendet via SendGrid.

```python
def render_daily_html(
    date: str,
    top_long: list[dict],
    top_short: list[dict],
    portfolio_recs: list[dict],  # Phase 4a output
    commodity_crypto: list[dict],
    yesterday_outcomes: dict,     # {long_correct, long_total, ...}
    cost_summary: dict,           # {total_eur, aborted_at_phase, ...}
    trends: list[dict],
) -> str:
    """
    4 Sektionen (in dieser Reihenfolge):
      1. Portfolio-Empfehlungen (Phase 4a: HALTEN/SCHLIESSEN/ANPASSEN)
      2. Stock Rankings (Top-10 Long + Top-10 Short)
      3. Trends (Makro-Trends + Sector-Rotation)
      4. Commodities & Crypto
    
    Footer: Tages-Outcomes, Skipped, Cost, Disclaimer
    """

def send_daily_email(to: str, html: str, date: str) -> bool:
    """SendGrid API Call"""
```

---

### 10. **`src/guardrails.py`**

Qualitätskontrolle auf analysen vor Ranking.

```python
class GuardrailsChecker:
    def check_analysis(analysis: dict) -> bool:
        """
        Prüft:
        1. Alle 8 Dimensionen vorhanden + scores 0-10
        2. Jede Dimension ≥ 2 Belege
        3. R/R Ratio ≥ 1.5
        4. hold_days_recommended: 1-3
        5. intraday_range_pct ≥ 1.0
        6. direction ≠ "none"
        """
```

---

### 11. **`src/db.py`**

SQLite-Schema + Persistence.

**Tabellen:**
- `predictions` – Alle generierten Setups (id, date, ticker, direction, scores, ...)
- `technical_indicators` – Phase 1 Daten (rsi_14, macd, ...)
- `outcomes` – Walk-Forward Ergebnisse (tp_hit, sl_hit, days_to_close, p&l, ...)
- `position_recommendations` – Phase 4a Output (HALTEN/SCHLIESSEN/ANPASSEN)
- `cost_tracking` – Claude-API Kosten pro Run

**Wichtige Helpers:**
- `save_prediction(conn, pred_dict)` – Phase 4
- `load_open_predictions_within_max_age_days(conn, today, max_trading_days=3)` – Phase 4a
- `update_outcome_close(conn, pred_id, exit_reason, exit_price, ...)` – Evaluator
- `load_recent_outcomes(conn, days=7)` – Weekly Email

---

### 12. **`src/cost_tracker.py`**

Tägliches API-Budget (Hard Cap: ~4 EUR/Run).

```python
class CostTracker:
    def add_from_result(result: ClaudeResult) -> None:
        """Claude SDK result object → parse input/output tokens + web_search_calls"""
    
    def add_call(model, input_tokens, output_tokens, web_search_calls) -> None:
        """Legacy 6-kwarg API (deprecated in Plan 3)"""
    
    def raise_on_cap_exceeded() -> raises CostCapExceeded:
        """wenn total_eur > hard_cap"""
```

**Hard Cap Logik in main.py:**
```python
try:
    phases_1_to_4(cost_tracker)
except CostCapExceeded as e:
    cost_tracker.aborted_at_phase = "policy_monitor"  # placeholder
    send_partial_email(cost_summary={"aborted_at_phase": ...})
```

---

## Data Flow: Ein Beispiel

```
heute = 2026-05-20, run_type = "close"

[main.run_pipeline("close", "2026-05-20")]
  ↓
[Phase 0] analyze_trends()
  → 1 Sonnet + web_search
  ← {trends: [{name: "ai-capex", strength: 8, ...}], ...}
  ✓ costs ~0.20 EUR

  ↓
[Phase 1] collect(provider, sp500_tickers)
  → yfinance × 500 (0.8s/Ticker, 12s/30er-Batch)
  ← 487 OK, 13 skipped
  ✓ costs ~0.00 EUR

  ↓
[Phase 2] quick_filter_batch()
  → Haiku × 17 Calls (30er-Batches)
  ← 500 Ergebnisse (scores + exclude-Flag)
  → Filter: Top 80 long, Top 80 short
  ✓ costs ~0.15 EUR

  ↓
[Phase 3] run_policy_monitor()
  → 1 Sonnet + web_search
  ← policy_risk_level, events
  ✓ costs ~0.10 EUR

  ↓
[Phase 3] analyze_assets()
  → Sonnet × 80 Calls + web_search (sequential!)
  ← 72 OK, 8 skipped (error/guardrail)
  ✓ costs ~2.50 EUR

  ↓
[Phase 3b] analyze_commodities_and_crypto()
  → Sonnet × 7 Calls
  ← 7 Assets (Gold, Silver, Oil, BTC, ETH, SOL, XRP)
  ✓ costs ~0.35 EUR

  ↓
[Phase 4a] check_open_positions()
  → if db.predictions[status='open' & date ≤ 2026-05-17] exists
  → Sonnet × N Calls
  ← N Empfehlungen (HALTEN/SCHLIESSEN/ANPASSEN)
  ✓ costs ~0.20 EUR

  ↓
[Phase 4] rank_and_persist()
  → Guardrail-Filter + Top-10
  → db.predictions schreiben
  ✓ costs ~0.00 EUR

  ↓
[Phase 5] render_daily_html() + send_daily_email()
  → 4 HTML-Sektionen
  → SendGrid API
  ✓ costs ~0.00 EUR

TOTAL: ~3.50 EUR
[Phase 4a Cost Cap Hit] → send_partial_email(aborted=True) → exit
```

---

## Invarianten (Never Violated)

1. **SIMULATION_ONLY=True** – Niemals echte Order-Ausführung
2. **CFD-Kurzfristfokus** – hold_days ≤ 3, intraday_range ≥ 1%
3. **Phase 0 ist fatal** – TrendAnalyzerError → no email
4. **Billing vor Parse** – `cost_tracker.add_from_result()` VOR JSON-Extraktion
5. **Guardrail-Pflicht** – Vor Phase 4 Ranking MÜSSEN alle Analysen durch Checks
6. **Atomare DB-Writes** – `evaluator.update_outcome_close` ACID-transactional
7. **Portfolio-Sektion zuerst** – Email-Rendering: Portfolio → Stocks → Trends → Commodities

---

## Testing-Strategie

- **Unit Tests** (155): Isolierte Module, Mock-Claude, Fixtures
- **Integration Tests** (3): Volle Pipeline mit 5 Aktien + E2E HTML-Render
- **Coverage Gate**: 80% Minimum (aktuell 89.62%)
- **Baseline**: `pytest tests/ -q` → 159 passed, 0 failures

---

## Skalierung für Sprint 2

- **Paid API** (Polygon/FMP) für historischen 3-Jahres-Pull
- **500 SP500 Tickers** (statt MVP-Subset)
- **Auto-Update** SP500-List monatlich
- **Regional Provider** (Japan, Europa optional)

---

Siehe auch: `WORKFLOW.md` für Live-Betrieb, `docs/superpowers/plans/` für detaillierte Task-Plans.
