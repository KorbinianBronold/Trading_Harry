# Shares_Future – Architektur & Design

**Zuletzt aktualisiert:** 2026-08-04 — Task 20: Phasen 1c/1d ergänzt, Phase 4 vor 4a,
signal_checks und revalidation als Module, position_check als Historie markiert

> **Dieses Dokument beschreibt den IST-Zustand des Codes.**
>
> ✅ **Stand 2026-08-04:** In Task 20 auf Sprint 3B / Plan 2 nachgezogen. Die frühere
> Abweichungsliste ist eingearbeitet und deshalb entfallen — Phasen 1c/1d, die
> getauschte Reihenfolge 4 → 4a, `analyses_by_ticker` und die beiden neuen Module
> `src/signal_checks.py` / `src/revalidation.py` stehen jetzt im Text selbst.
>
> ⚠️ **Eine Einschränkung bleibt:** Der beschriebene Code liegt vollständig auf `main`,
> wurde aber **noch nie ausgeführt**. `analyze.yml` steht auf `disabled_manually`, der
> letzte Pipeline-Lauf war am 2026-07-13. Was hier steht, ist also der Ist-Zustand des
> *Codes*, nicht der eines laufenden Systems. Live-Verifikation: PROJECT_STATUS, P2.4.
>
> Historische Abschnitte weiter unten (Sprint 1 / Sprint 2) sind bewusst nicht
> umgeschrieben — sie sind als Historie gekennzeichnet.

## Überblick

Das System folgt einer **Pipeline-Architektur** mit 9 Phasen (0, 0b, 1, 1c, 1d, 2, 3, 4, 4a, 5), die sequenziell ausgeführt werden. Jede Phase ist entkoppelt über klare Daten-Schnittstellen und kann unabhängig getestet werden.

**Reihenfolge beachten:** Ranking (Phase 4) läuft seit B.5 **vor** dem Portfolio-Check (4a), nicht danach. Phase 4a bekommt dadurch die fertigen Phase-3-Analysen und braucht keinen eigenen `web_search`.

```
┌─────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR (main.py)                      │
│  Dispatch: --run-type {pre_market|trade_proposals|close|weekly}  │
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
│  Quelle: Capital.com (alleiniger OHLC-Provider, kein Fallback)   │
│           500 Aktien + Commodities/Crypto                        │
│           1 Bar täglich fetchen + letzte 200 aus DB              │
│  Berechnen: RSI-14, MACD, ATR, SMA200, PE, Volume-Ratio, etc.   │
│  Output: list[{ticker, price, rsi_14, macd, ..., intraday_range}│
│  Cost: ~0.00 EUR                                                 │
│  Fail: ✅ Skip Ticker, continue                                   │
│  DB: tech_indicators-Table persistieren                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│      PHASE 1c: OFFENE POSITIONEN ALS PFLICHT-KANDIDATEN          │
│  Capital.com GET /positions → Epics über die Reverse-Map auf     │
│  Ticker zurückführen. Diese Ticker gehen garantiert in Phase 3,  │
│  auch wenn der Quick-Filter sie aussortiert hätte — sonst        │
│  verliert man die Analyse zu einer Position, die man hält.       │
│  Cost: ~0.00 EUR | Fail: ✅ leere Liste, continue                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│          PHASE 1d: SEKTOR-MOMENTUM (zwei Signale)                │
│  ETF-Momentum (Capital.com, je Sub-Sektor-ETF) und              │
│  DB-Momentum (Durchschnitt der Ticker aus ticker_sectors).      │
│  Werden GETRENNT gespeichert und nie verrechnet — 3D soll       │
│  messen, welches besser predictet.                               │
│  DB: sector_momentum | Cost: ~0.00 EUR                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              PHASE 2: QUICK-FILTER (Batch-Scoring)               │
│  Input: phase1_data[], trend_context                             │
│  Claude: 1× Haiku über ALLE Ticker                              │
│  ⚠️ BATCH_SIZE_QUICK und MAX_DEEP_ANALYSIS sind tote            │
│     Konstanten — es gibt weder 30er-Batches noch einen Deckel    │
│     auf die Tiefenanalysen. Fix gehört zu C.4.                   │
│  Output: list[{ticker, long_score, short_score, confidence}]    │
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
│  Guardrails: R/R ≥ 1.5, hold_days ≤ 5, intraday_range ≥ 1%    │
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
│         PHASE 4: RANKING & PERSISTIERUNG                         │
│  Input: deep_analysis[], commodities_crypto[]                    │
│  Logik: Guardrail-Filter → Top-10 Long/Short nach prob_pct      │
│  Checks: src/signal_checks.py (VIX, Klumpen, rel. Stärke, Gap)  │
│          enforce=True nur im 16:10-Lauf, sonst weiche Warnung   │
│  Output: {top_long[], top_short[], commodities_crypto[]}        │
│  DB: predictions + guardrail_rejects schreiben                   │
│  Learnable: Alle = true (außer skip-by-guardrails)             │
│  Cost: ~0.00 EUR                                                 │
│  Fail: ❌ Propagates (Ranking MUSS funktionieren)               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│       PHASE 4a: PORTFOLIO-CHECK (Offene Positionen)              │
│  ⚠️ Läuft seit B.5 NACH Phase 4 und nutzt deren fertige         │
│     Phase-3-Analysen — kein eigener web_search mehr.             │
│  Input: db.predictions[status='open' & date < today],           │
│         analyses_by_ticker, trend_context, policy_context       │
│  Claude: Sonnet × N offene Positionen, OHNE web_search          │
│  Output: list[{prediction_id, action="HALTEN|SCHLIESSEN|..."}]  │
│  Hinweis: date < today — eine Prediction ist erst ab dem        │
│           Folgetag eine offene Position, vorher ein Vorschlag.   │
│  Cost: ~0.20 EUR (abhängig von offenen Positionen)              │
│  Fail: ✅ Skip Position, continue                                │
│  DB: position_recommendations-Table schreiben                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│   CLOSE RUN: Schlusskurse ALLER Ticker + TP/SL-Auswertung        │
│   + cleanup_old_data()  (kein Claude, kein Mail)                 │
│   WEEKLY RUN: Aggregate + Wochenmail                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              PHASE 5: E-MAIL & REPORTING                         │
│  Input: top_10_long, top_10_short, commodities_crypto,          │
│         yesterday_outcomes_agg, cost_summary                     │
│  HTML: 4 Sektionen (Portfolio → Stocks → Trends → Commodities)  │
│  Resend: E-Mail an EMAIL_TO                                      │
│  Cost: ~0.00 EUR (Freikontingent)                               │
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

### 2b. **`src/market_context.py`** (Phase 0b, seit Sprint 3B / Plan 1)

Tagesaktueller Marktzustand (einmalig pro Run).

```python
def fetch_market_context(date, run_type, cost_tracker, price_provider=None) -> dict:
    """
    1 Sonnet + web_search Call. Alle Keys immer vorhanden, nicht belegbare Werte None:
    {vix_level, vix_source, advance_decline_ratio, market_regime,
     sector_rotation_in, sector_rotation_out, macro_summary}
    """
```

**VIX-Präzedenz:** Der numerische Capital.com-Bar schlägt Claudes recherchierte
Zahl; `vix_source` weist aus, welche Quelle gewonnen hat.

**Warum None statt Schätzung:** Die Werte steuern nachgelagert harte Risikofilter
(VIX > 25 nur noch `confidence='high'`, VIX > 35 keine neuen Longs). Ein geratener
Wert wäre dort schlimmer als gar keiner.

**Fail-Verhalten:** `MarketContextError` wird in `run_pipeline()` gefangen → der Run
läuft mit leerem Kontext weiter (Phase 0b ist **nicht** fatal). `CostCapExceeded`
propagiert dagegen wie gewohnt zum äusseren Handler.

---

### 2c. **`src/sector_momentum.py`** (seit Sprint 3B / Plan 1)

Zwei unabhängige Momentum-Signale je Sub-Sektor, getrennt gespeichert und **nie
verrechnet** — Sprint 3D soll datenbasiert messen, welches besser predictet.

```python
def collect_sector_momentum(conn, date, run_type, price_provider) -> dict[int, dict]:
    """{sector_id: {etf_momentum, db_momentum, ticker_count}}"""
```

- `etf_momentum` – Tagesperformance des Sub-Sektor-ETF von Capital.com. Jeder ETF
  wird nur einmal abgerufen (21 Sub-Sektoren teilen sich 19 ETFs); die Bars landen
  in `price_history`, weil keine Phase-1-Ticker-Liste sie enthält.
- `db_momentum` – Ø Tagesperformance aller Ticker des Sub-Sektors, reines SQL,
  0 EUR. NULL unterhalb `config.SECTOR_DB_MOMENTUM_MIN_TICKERS = 3`.

**Nur Erhebung.** Die Guardrail-Auswertung (hartes Reject nur bei zwei
übereinstimmenden Signalen) gehört zu Plan 2.

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
        hold_days_recommended: 1-5,
        intraday_range_pct: 1.0+,
        technical_indicators: {...},
        sources_used: []
    }
    
    Guardrails (nach dieser Funktion geprüft):
    - hold_days > 5 → reject
    - intraday_range < 1.0 → reject
    - R/R < 1.5 → reject
    - direction = "none" → reject (beide Scores gleich)
    """
```

**Fail-Verhalten:** `DeepAnalysisError` → skip Ticker, continue.

**Billing:** `cost_tracker.add_from_result(result)` **VOR** JSON parse.

---

### 4b. **`src/providers/capital_provider.py`** (Sprint 2)

Capital.com Demo API als primary OHLC-Datenquelle.

```python
class CapitalComProvider(DataProvider):
    """
    Primary OHLC-Provider (Capital.com Demo API).
    Base URL: https://demo-api-capital.backend-capital.com/
    Rate Limit: 600 Calls/Min
    ENV: CAPITAL_COM_API_KEY, CAPITAL_COM_PASSWORD
    
    Ticker-Mapping:
    - SP500-Ticker: direkt übergeben
    - Gold="GOLD", Silber="SILVER", Öl="CRUDE_OIL"
    - BTC="BITCOIN", ETH="ETHEREUM", SOL="SOLANA", XRP="XRP"
    """
    def get_price_history(ticker, days) -> pd.DataFrame: ...
    def get_ohlc_after(ticker, start_date, end_date) -> pd.DataFrame: ...
    def get_premarket_price(ticker) -> float | None: ...
    def get_open_positions() -> list[dict]: ...
    def get_closed_positions(date) -> list[dict]: ...
    def get_fundamentals() -> dict: ...       # leer – nicht zuständig
    def get_earnings_calendar() -> dict: ...  # leer – nicht zuständig
```

**Fundamentals** werden separat von `FinnhubProvider.get_fundamentals()` abgerufen und in `fundamentals_cache`-Tabelle mit 7-Tage TTL gecacht. Im täglichen Run wird der Cache aus der DB gelesen, kein Live-Call.

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

### 6. **`src/ranking.py`** (Phase 4)

Filtert, sortiert und persistiert Top-10-Setups. **Läuft seit B.5 vor Phase 4a.**

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
    1. Guardrail-Filter (hold_days ≤ 5, intraday_range ≥ 1%, R/R ≥ 1.5, no "none")
    2. Checks aus src/signal_checks.py (VIX, Klumpen, relative Stärke, Gap) —
       erhoben in BEIDEN Läufen, durchgesetzt nur bei enforce=True (16:10)
    3. Split Long/Short
    4. Sort by probability_pct DESC
    5. Keep Top 10 each, ALL commodities/crypto
    6. Persist to db.predictions; Verworfenes nach db.guardrail_rejects

    Returns: {top_long[], top_short[], commodities_crypto[]}
    """
```

**Fail-Verhalten:** `RankingError` → propagates (MUSS funktionieren).

---

### 7. **`src/portfolio_check.py`** (Phase 4a)

Evaluiert alle offenen Positionen (max `MAX_HOLD_DAYS` Tage alt). **Läuft seit B.5
nach Phase 4** und arbeitet auf deren fertigen Phase-3-Analysen.

```python
def check_open_positions(
    conn,
    today: str,
    run_type: str,
    analyses_by_ticker: dict[str, dict],   # fertige Phase-3-Analysen, NICHT Snapshots
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """
    Für jede offene Position (≤ MAX_HOLD_DAYS alt):
      - Sonnet-Call OHNE web_search (B.5) — der Kontext kommt aus Phase 3
      - Returns: {prediction_id, action:"HALTEN"|"SCHLIESSEN"|"ANPASSEN",
                 reason, new_sl_price, new_tp_price, market_context_changed}
      - Speichert position_recommendations-Row

    Nur Predictions mit date < today: eine Prediction desselben Laufs ist ein
    Vorschlag, keine offene Position — sonst prüfte 4a die Signale gegen ihre
    eigene, Sekunden alte Analyse.
    """
```

**Fail-Verhalten:** `PortfolioCheckError` → skip Position, continue.

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

Rendert HTML und sendet via **Resend** (`POST https://api.resend.com/emails`).

> **Provider-Wechsel erledigt (Sprint 3B-M, 2026-07-30).** `_send()` ist die einzige
> providerspezifische Stelle — jedes `send_*_email()` laeuft dort durch. Bewusst
> `requests` statt Anbieter-SDK: es ist genau ein POST, `requests` ist ohnehin
> Abhaengigkeit, und Resend sitzt hinter Cloudflare, das die `urllib`-Signatur mit
> HTTP 403 / „error code: 1010" abweist. Resend verlangt eine **verifizierte eigene
> Domain**; `tradingharry.com` ist seit 2026-07-30 verifiziert, Absender ist
> `noreply@tradingharry.com`. Ein 2xx auf den POST heisst nur „angenommen" — die
> Zustellung laeuft asynchron, Fehlschlaege zeigen sich erst unter
> `GET /emails/{id}` als `last_event="failed"`.

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
    """Resend API Call"""
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
        4. hold_days_recommended: 1-5
        5. intraday_range_pct ≥ 1.0
        6. direction ≠ "none"
        """
```

---

### 10a. **`src/signal_checks.py`** (neu in 3B / Plan 2)

Die rechnerischen Checks aus B.3. **Bewusst netzwerk- und Claude-frei:** jede Funktion
bekommt bereits erhobene Werte (Markt-Kontext aus Phase 0b, Sektor-Momentum aus Phase 1d,
Kurse aus `price_history`) und gibt ein Urteil zurück. Dadurch ohne Mocking testbar.

```python
check_vix(...)             -> CheckResult | None   # kumulativ: ab 25 nur high,
                                                   # zusätzlich ab 35 keine neuen Longs
check_sector_momentum(...) -> CheckResult | None   # hart nur bei Übereinstimmung
check_cluster(...)         -> CheckResult | None   # Klumpenrisiko im Sub-Sektor
check_opening_gap(...)     -> CheckResult | None   # Gap pre_market → 16:10
compute_relative_strength(...)                     # Ticker vs. Sub-Sektor
blocks(results)            -> bool                 # blockiert irgendein Ergebnis?
```

**Zwei Regeln, die man hier leicht falsch macht:**
- Ein Check, der **nicht** anschlägt, gibt `None` zurück und erzeugt **keine** Zeile —
  wörtlich B.3.1: „keines vorhanden → kein Check, kein Log-Eintrag".
- Ob ein anschlagender Check das Signal auch **blockiert**, entscheidet nicht dieses
  Modul, sondern der Aufrufer über `enforce` (E4). Um 15:00 wird nur erhoben und
  mit `enforced=0` protokolliert, um 16:10 durchgesetzt.

---

### 10b. **`src/revalidation.py`** (neu in 3B / Plan 2)

Der billige Zweitcheck des `trade_proposals`-Laufs (E1). Ein Sonnet-Call je Signal,
**ohne `web_search`** — die Recherche hat die Tiefenanalyse am Morgen bezahlt, und
Breaking News zwischen 15:00 und 16:10 deckt der eine Policy-Monitor-Call ab.

```python
revalidate_one(...) -> dict   # {verdict, probability_pct, reason, ...}
                              # verdict ∈ bestaetigt | geschwaecht | unveraendert
                              #           | gedreht | verworfen
```

**Das Modul urteilt nur.** Was mit dem Urteil geschieht — Ablösung der `pre_market`-Zeile
über `superseded_by`, eine neue Prediction oder blosse Warnung — entscheidet
`main.run_trade_proposals()`. In drei von sechs Ausgängen entsteht gar keine neue Zeile.

---

### 11. **`src/db.py`**

SQLite-Schema + Persistence.

**Tabellen:**
- `predictions` – Alle generierten Setups (id, date, ticker, direction, scores, hold_day, extended_hold, ...)
- `technical_indicators` – Phase 1 Daten (rsi_14, macd, ...)
- `outcomes` – Walk-Forward Ergebnisse (tp_hit, sl_hit, days_to_close, hold_day, extended_hold, p&l, ...)
- `position_recommendations` – Phase 4a Output (HALTEN/SCHLIESSEN/ANPASSEN)
- `cost_tracking` – Claude-API Kosten pro Run
- `fundamentals_cache` – Finnhub-Fundamentals mit 7-Tage TTL (UNIQUE per ticker)
- `price_history` – OHLCV inkl. premarket_price (nullable)
- `market_context` – ein Marktzustand je Run (UNIQUE date+run_type), seit 3B echt befüllt

**Neu in Sprint 3B / Plan 1** (angelegt 2026-07-27/29):
- `ticker_status` – kumulativer `skip_count` + `inactive`-Flag + `retry_after` pro Ticker
- `sectors` – **21 Sub-Sektoren** auf 19 ETFs (Semiconductors→SOXX, Software→VGT, …),
  Seed beim DB-Setup aus `config.SUB_SECTOR_ETFS`. Bewusst feiner als die
  11 GICS-Sektoren, die hier ursprünglich geplant waren.
- `ticker_sectors` – Ticker→Sub-Sektor-Mapping, organisch in Phase 1 aus dem Finnhub-Cache
- `guardrail_rejects` – verworfene Analysen mit gruppiertem `rule`-Namen und `enforced`-Flag
- `sector_momentum` – die beiden Momentum-Signale je Sub-Sektor und Run
  (UNIQUE date+run_type+sector_id)

**Neue Spalten in 3B / Plan 1:**
- `market_context.advance_decline_ratio`
- `predictions.sector_etf_momentum`, `predictions.sector_db_momentum`
- `guardrail_rejects.sector_etf_momentum`, `guardrail_rejects.sector_db_momentum`

> Die vier Momentum-Spalten sind angelegt, werden aber noch von niemandem
> **befüllt** — das macht Plan 2 zusammen mit der Guardrail-Auswertung.

**Geplant in 3C** (noch nicht angelegt):
- `predictions.ranking_score` – neue Spalte für den kombinierten Score

**Wichtige Helpers:**
- `save_prediction(conn, pred_dict)` – Phase 4
- `load_open_predictions_within_max_age_days(conn, today, max_trading_days=config.MAX_HOLD_DAYS)` – Phase 4a
- `update_outcome_close(conn, pred_id, exit_reason, exit_price, ...)` – Evaluator
- `load_recent_outcomes(conn, days=7)` – Weekly Email
- `resolve_sector_id(conn, raw)` / `upsert_ticker_sector(...)` / `get_ticker_sector(...)` – Sub-Sektoren
- `is_ticker_inactive(conn, ticker, today)` / `reactivate_ticker(...)` / `list_inactive_tickers(...)` – Skip-Logik
- `log_guardrail_reject(conn, row)` / `load_guardrail_rejects_since(conn, since)` – Weekly-Auswertung
- `compute_sector_db_momentum(...)` / `save_sector_momentum(...)` / `load_sector_momentum(...)` – D9
- `save_market_context(conn, row)` – Phase 0b

**Retention** (`cleanup_old_data`, seit 3B): `news_summaries` 30 Tage,
`trend_analyses` 180 Tage, `skipped_tickers`-Events 90 Tage. `ticker_status`
wird **nie** automatisch gelöscht — der kumulative Zähler muss die Event-Retention
überleben.

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
  → Capital.com × 500 (incremental: 1 Bar/Ticker, Indikatoren aus DB)
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
[Phase 4] rank_and_persist()
  → Guardrail-Filter + signal_checks (enforce nur um 16:10) + Top-10
  → db.predictions + db.guardrail_rejects schreiben
  ✓ costs ~0.00 EUR

  ↓
[Phase 4a] check_open_positions()          # seit B.5 NACH Phase 4
  → if db.predictions[status='open' & learnable=1 & date < today] exists
  → Sonnet × N Calls, OHNE web_search (nutzt die Phase-3-Analysen)
  ← N Empfehlungen (HALTEN/SCHLIESSEN/ANPASSEN)
  ✓ costs ~0.20 EUR

  ↓
[Phase 5] render_daily_html() + send_daily_email()
  → 4 HTML-Sektionen
  → Resend API
  ✓ costs ~0.00 EUR

TOTAL: ~3.50 EUR
[Phase 4a Cost Cap Hit] → send_partial_email(aborted=True) → exit
```

---

## Invarianten (Never Violated)

1. **SIMULATION_ONLY=True** – Niemals echte Order-Ausführung
2. **CFD-Kurzfristfokus** – hold_days ≤ 5 (`config.MAX_HOLD_DAYS`); `guardrails.py`, `evaluator.py`, `portfolio_check.py` und `db.py` referenzieren seit 2026-07-17 alle denselben Wert statt eigener hardcodierter Konstanten (Bug B-06 behoben). intraday_range ≥ 1%; SP500_MIN_ATR_PCT = 2.0
3. **Phase 0 ist fatal** – TrendAnalyzerError → no email
4. **Billing vor Parse** – `cost_tracker.add_from_result()` VOR JSON-Extraktion
5. **Guardrail-Pflicht** – Vor Phase 4 Ranking MÜSSEN alle Analysen durch Checks
6. **Atomare DB-Writes** – `evaluator.update_outcome_close` ACID-transactional
7. **Portfolio-Sektion zuerst** – Email-Rendering: Portfolio → Stocks → Trends → Commodities
8. **Timezone** – Alle datetime-Berechnungen in `ZoneInfo("Europe/Berlin")`; Bash: `TZ="Europe/Berlin" date`

---

## Testing-Strategie

- **Unit Tests** (155): Isolierte Module, Mock-Claude, Fixtures
- **Integration Tests** (3): Volle Pipeline mit 5 Aktien + E2E HTML-Render
- **Coverage Gate**: 80% Minimum (aktuell 92.45%)
- **Baseline**: `pytest tests/ -q` → 411 passed, 7 skipped, 0 failures (Stand 2026-07-30).
  Die 7 übersprungenen sind die Live-Tests unter `tests/live/`; sie laufen nur mit
  `--run-live` und sprechen dann echte APIs an (inkl. echtem Mailversand).

---

## Sprint 2 / Plan 1 — umgesetzt (2026-05-22)

Plan: `docs/superpowers/plans/2026-05-21-sprint2-plan1-capital-provider-db-incremental.md`

- **capital_provider.py** – CapitalComProvider (alleiniger OHLC-Provider, GET /positions, premarket)
- **fundamentals_cache** – Finnhub-Fundamentals mit 7-Tage TTL
- **DB-Incremental-Update** – täglich nur 1 Bar fetchen, Indikatoren aus DB (200 Tage)
- **position_check Run-Type** – Capital.com Position-Read + Claude + Status-Mail
  *(in Sprint 3B / Plan 2 restlos entfernt, `59f5e2c` — steht hier nur als
  Sprint-2-Historie, nicht als Ist-Zustand)*
- **Timezone-Fix** – `ZoneInfo("Europe/Berlin")` in Python, `TZ="Europe/Berlin"` in Bash
- **historical_loader.py** – 3-Jahres-Pull via Capital.com (`--all`, `--full-sp500`, `--tickers`).
  Seit Sprint 3B zusätzlich die reinen Status-Modi `--reactivate` / `--list-inactive`;
  die Modus-Gruppe ist `required=True` (Aufruf ohne Flag ist ein Fehler, kein Default-Pull).
- **500-Ticker Scaling** – `USE_FULL_SP500`-Flag (Ticker-Liste noch Stub, s. Bug B-03)

---

## Geplante Architektur-Änderungen (Sprint 3B / 3C)

Vollständige Spezifikation: `docs/superpowers/specs/PROJECT_STATUS.md`.
Kurzüberblick, was sich an der oben beschriebenen Architektur ändern wird:

**Bereits umgesetzt** (Sprint 3B / Plan 1, abgeschlossen 2026-07-29):

| Bereich | Änderung |
|---|---|
| Pipeline | **Phase 0b neu**: Markt-Kontext (VIX, A/D-Ratio, Regime) — ersetzt das hardcodierte `None`-Dict vor dem Ranking |
| `data_collector` | Gap-Erkennung mit Handelstags-Logik + automatisches Nachladen fehlender Bars |
| `data_collector` | Inaktive Ticker überspringen; Sektor-Mapping organisch pflegen |
| Schema | `ticker_status`, `sectors` (21 Sub-Sektoren statt der ursprünglich geplanten 11 GICS), `ticker_sectors`, `guardrail_rejects`, `sector_momentum` + 5 neue Spalten |
| Retention | news 90→30 Tage, skipped_tickers-Events 30→90 Tage, `ticker_status` nie gelöscht |
| `ranking` | Rejects werden persistiert; `predictions.sector` kommt aus `ticker_sectors` |
| `main` | B-05 gefixt: echte Abbruch-Phase statt Platzhalter |

### Sprint 3B / Plan 2 — umgesetzt (2026-07-30 bis 2026-08-04)

Code vollständig, 20/20 Tasks, alles auf `main`. ⚠️ **Noch nie ausgeführt** —
`analyze.yml` steht auf `disabled_manually`; die Live-Verifikation steht aus
(PROJECT_STATUS, P2.4).

| Bereich | Änderung |
|---|---|
| Run-Types | `midday`, `evaluate`, `position_check` entfernt; neu `trade_proposals` (16:10 Berlin) |
| Pipeline | **Phase 1c**: offene Capital.com-Positionen als Pflicht-Kandidaten für Phase 3 |
| Pipeline | **Phase 1d**: Sektor-Momentum verdrahtet (war toter Code) |
| Pipeline | **Phase 4 vor 4a** — 4a nutzt die fertigen Phase-3-Analysen, ohne Web-Search. Mail-Reihenfolge bleibt: Portfolio zuerst |
| Module | **neu** `src/signal_checks.py` und `src/revalidation.py` (s. 10a/10b) |
| Guardrails | Momentum-Signale angewandt (hartes Reject nur bei Übereinstimmung); die vier Momentum-Spalten werden befüllt |
| `close` | Holt Schlusskurse aller Ticker; TP/SL-Auswertung bleibt bis 3D |
| Weekly-Mail | vier B.9-Blöcke aus `guardrail_rejects`, `ticker_status`, `revision_verdict` und der Sub-Sektor-Abdeckung |
| Tagesmail | `hold_days_recommended` als Spalte „Haltedauer" (B.11) |

**Noch offen:**

| Bereich | Änderung | Sprint |
|---|---|---|
| `run_weekly` | `cost_summary` ist hart auf Nullen verdrahtet — die Weekly-Mail meldet dauerhaft 0,00 EUR. Es fehlt ein `db.load_cost_summary()` | 3C |
| Schema | Neue Spalte `predictions.ranking_score` | 3C |
| `ranking` | `atr_pct`/`rsi_at_entry`/`volume_ratio` korrekt befüllen; kombinierter `ranking_score` **zusätzlich** zu `total_score` | 3C |
| Phase 2 | Technischer Python-Pre-Filter (ATR/RSI/Volume/Market-Cap) vor dem Haiku-Batching | 3C |

---

Siehe auch: `PROJECT_STATUS.md` für Roadmap + Sprint-Spezifikationen,
`docs/superpowers/plans/` für abgeschlossene Task-Pläne.
