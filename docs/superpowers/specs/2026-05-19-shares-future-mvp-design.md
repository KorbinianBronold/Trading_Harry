> ⚠️ HISTORISCH — docs/superpowers/specs/PROJECT_STATUS.md lesen stattdessen

# Shares_Future — MVP Design

**Datum:** 2026-05-19 | **Zuletzt aktualisiert:** 2026-05-22
**Status:** Sprint 1 ERLEDIGT — Sprint 2 Plan geschrieben
**Vorgängerdokument:** `docs/SPECIFICATION.md` (Version 5.0, 2026-05-22)

Dieses Dokument ergänzt und ersetzt selektiv die ursprüngliche Spec. Wo dieses Dokument von der Spec abweicht, gilt dieses Dokument.

---

## Zielsetzung (unverändert)

Automatisiertes Research-Tool zur täglichen Analyse von S&P 500 Aktien, Rohstoffen (Gold, Silber, Öl) und Kryptowährungen (BTC, ETH, SOL, XRP). Paper-Trading Research-Tool ohne automatische Orderausführung.

---

## Design-Prinzip: CFD-Kurzfristfokus

Das Tool ist explizit für **kurzfristige CFD-Trades** optimiert und denkt in Tages-Zyklen, nicht in Wochen:

- **Haltedauer:** wenige Stunden bis maximal 3 Handelstage.
- **Täglicher Reset:** jede offene Position wird in jedem Werktags-Analyse-Run neu bewertet (Phase 4a, siehe §3).
- **Flexibilität:** schnelle Reaktion auf Marktveränderungen — keine Position wird blind gehalten.

Daraus folgende harte Invarianten, die überall im System gelten:

1. Setups mit `hold_days_recommended > 5` werden via Guardrail rejected (`MAX_HOLD_DAYS = 5`, siehe §6).
2. Assets mit `intraday_range_pct < 1.0%` (Durchschnitt der letzten 5 Tage) werden via Guardrail rejected (siehe §6).
3. Phase 4a (Portfolio-Check) bewertet alle gestern offenen Positionen mit `HALTEN | SCHLIESSEN | ANPASSEN` und erscheint als **erste Sektion** in der E-Mail — vor den neuen Top-10 (siehe §3).
4. Der **`close`-Run (lokal 21:30 / 22:30) ist der wichtigste**: er produziert die Setups und Phase-4a-Empfehlungen für den nächsten Handelstag, die der Trader im `pre_market`-Run morgens bestätigt findet (siehe §7).

---

## 1 · Scope & Sequencing

Wir kippen das „Sofort vollständig bauen"-Mandat der Spec und bauen in drei Sprints mit expliziten Gates.

### Sprint 1 — MVP

**In Scope:**
- 20 SP500 Mega Caps (yfinance) + 3 Commodities (Gold, Silber, Öl) + 4 Crypto (BTC, ETH, SOL, XRP) = 27 Assets
- Phasen 0, 1, 2, 3, 3b, 4, 5 vollständig
- DB-Schema vollständig wie in Spec (auch Felder, die erst später gefüllt werden)
- Predictions werden ab Tag 1 mit allen 8 Score-Dimensionen gespeichert → Daten für späteres Lernmodul
- Walk-Forward Evaluator (OHLC-Hit-Check, 1-5 Handelstage)
- Guardrails vollständig
- Daily E-Mail (4 Sektionen inkl. Phase-4a-Portfolio-Empfehlungen) + Weekly E-Mail (reduziert)
- GitHub Actions Cron + DB-Persistenz via Release Assets
- Cost-Tracking + Hard-Cap
- Tests min. 80% Coverage

**Status: ERLEDIGT — 159 Tests, 89.62% Coverage, gemerged in main (2026-05-20)**

**Out of Scope (defer):**
- Learning Module / dynamische Schwellwerte → Sprint 3
- Prompt-Optimizer / A/B-Testing → Sprint 3
- Capital.com Provider + historischer Loader → Sprint 2
- SP500 auf 500 Ticker → Sprint 2
- SP500-Auto-Update monatlich → Sprint 2

---

### Sprint 1 Fixes (am bestehenden Code, geplant 2026-05-22)

- ATR-Mindest: SP500_MIN_ATR_PCT = 2.0
- Intraday-Fokus in allen Prompts
- "Was heute zählt"-Box in täglicher E-Mail
- close-Run vereinfacht: kein Claude, kein Mail
- Timezone-Fix: TZ="Europe/Berlin" in analyze.yml + zoneinfo in Python
- Doppelte Cron-Einträge für DST (Sommer/Winter)

### Ticker-Auswahl (Sprint 1)

Top 20 nach Marktkapitalisierung Stand 2026-05-19:
`AAPL, MSFT, NVDA, GOOGL, AMZN, META, TSLA, BRK.B, JPM, V, UNH, XOM, JNJ, WMT, MA, PG, HD, LLY, ABBV, AVGO`

Plus festes Asset-Set:
- Commodities: `GC=F` (Gold), `SI=F` (Silber), `CL=F` (Öl)
- Crypto: `BTC-USD`, `ETH-USD`, `SOL-USD`, `XRP-USD`

### Sprint 2 / Plan 1 (Capital Provider + DB Incremental + Position Check)

Voraussetzung: Sprint 1 stabil seit ≥1 Woche.

Plan: `docs/superpowers/plans/2026-05-21-sprint2-plan1-capital-provider-db-incremental.md`
Status: Plan geschrieben, Implementierung ausstehend

Scope:
- `capital_provider.py`: CapitalComProvider (primary OHLC, GET /positions, premarket)
- `fundamentals_cache`: Finnhub-Fundamentals mit 7-Tage TTL
- DB-Incremental-Update: täglich nur 1 Bar fetchen, Indikatoren aus DB (200 Tage)
- `position_check` Run-Type: Capital.com Position-Read + Claude + Status-Mail
- Timezone-Fix (in Sprint-1-Fix integriert)
- `historical_loader.py`: 3-Jahres-Pull via Capital.com
- 500-Ticker Scaling: USE_FULL_SP500 Flag

### Sprint 3 — Lernen & Optimieren

Voraussetzung: Sprint 2 stabil seit ≥1 Monat, ausreichend Outcome-Daten.

- Learning Module (Long/Short getrennt, dynamische Schwellwerte)
- Prompt-Optimizer mit A/B-Testing
- Erweiterte Weekly-Mail mit Lerninhalten

---

## 2 · Architektur & Module

Spec-Struktur weitgehend übernommen, mit folgenden Anpassungen:

```
src/
├── providers/
│   ├── base.py                  # DataProvider Interface (Spec wie ist)
│   ├── yfinance_provider.py     # MVP-Hauptquelle (täglich)
│   ├── finnhub_provider.py      # NEU: Earnings-Calendar
│   └── paid_provider.py         # STUB im MVP, in Sprint 2 ausimplementieren
├── data_collector.py            # Phase 1: Quotes + Indicators
├── trend_analyzer.py            # Phase 0: Megatrends
├── quick_filter.py              # Phase 2: Batch-Scoring (Haiku)
├── deep_analysis.py             # Phase 3: 8-Dim Score + Policy Monitor
├── commodities_crypto.py        # Phase 3b: Festes Asset-Set
├── portfolio_check.py           # NEU Phase 4a: Tägliche Bewertung offener Positionen (CFD-Kurzfrist)
├── ranking.py                   # Phase 4: Top-Selektion + DB-Save
├── email_sender.py              # Phase 5: Daily + Weekly E-Mail
├── guardrails.py                # Qualitätskontrolle, R/R-Check
├── evaluator.py                 # NEU: Walk-Forward OHLC-Hit-Check
├── cost_tracker.py              # NEU: Pro-Run Kostenmessung + Hard-Cap
├── db.py                        # NEU: Schema-Setup, Migrations, Helpers
└── utils.py                     # Logging, Retry, Claude-Wrapper

setup/
└── historical_loader.py         # Sprint 2

prompts/
├── quick_filter_v1.txt
├── deep_analysis_v1.txt
├── trend_analyzer_v1.txt
├── commodities_crypto_v1.txt
└── policy_monitor_v1.txt

tests/
├── unit/                        # Ein Test pro src/-Modul
├── integration/
│   ├── test_full_pipeline.py
│   ├── test_eval_loop.py
│   └── test_email_render.py
├── fixtures/
└── conftest.py
```

### Wichtige Boundary-Regeln

- Module reden mit der DB **nur über `db.py`** — keine SQL-Statements in den Phase-Modulen
- Claude-API-Aufrufe gehen durch **einen einheitlichen Wrapper in `utils.py`** für Caching, Retry, Cost-Tracking
- `guardrails.py` und `cost_tracker.py` sind **Cross-Cutting** — werden überall aufgerufen, hängen von nichts ab
- `main.py` ist **nur Orchestrator** (Dispatch nach `run_type`), keine Geschäftslogik

### Aufteilung Spec-`learning_module.py`

Wird im MVP aufgesplittet:
- `evaluator.py` (Sprint 1) — berechnet Vortags-Outcomes via Walk-Forward
- `learning_module.py` (Sprint 3) — eigentliches Lernen aus aggregierten Outcomes

---

## 3 · Daten-Fluss

### Pre-Market-Run (analog für midday/close)

```
1. main.py --run-type pre_market
   └─ Lädt config, initialisiert db.py, cost_tracker startet bei 0

2. trend_analyzer (Sonnet + Web-Search)
   └─ Output: {dominant_trends, sector_rotation, trend_summary}
   └─ DB-Write: trend_analyses
   └─ cost_tracker.add(...) → abort wenn > 4 EUR

3. data_collector (yfinance + finnhub)
   └─ Loop über 27 Assets:
      ├─ get_price_history (90d OHLCV)
      ├─ get_fundamentals
      ├─ get_earnings_calendar (Finnhub)
      └─ berechne RSI/MACD/ATR/BB/SMAs/Volume-Ratio
   └─ DB-Write: price_history (UPSERT), technical_indicators

4. quick_filter (Haiku, 1 Batch von 20 SP500)
   └─ Input: TickerData + trend_context + leerer learning_context im MVP
   └─ Output: long_score, short_score, confidence, evidence, exclude
   └─ Im MVP gehen alle 20 weiter (Top-80-Cap irrelevant)

5. policy_monitor (Sonnet + Web-Search, 1x)
   └─ Output: globale policy_risk_events
   └─ DB-Write: market_context

6. deep_analysis (Sonnet + Web-Search, pro Asset, max 5 parallel)
   └─ Input: TickerData + quick_filter_result + trend + policy_events
   └─ Output: 8 Score-Dimensionen mit Belegen, TP/SL, summary
   └─ Guardrails-Check → reject wenn Pflichtfelder/Evidenz fehlen
   └─ Signal-Consistency: long needs momentum ≥ 6, short needs momentum ≤ 4

7. commodities_crypto (parallel zu Schritt 6)
   └─ 7 Assets, Sonnet + Web-Search, eigener Prompt
   └─ Gleiche Guardrails wie Aktien

8. portfolio_check (Phase 4a, Sonnet + Web-Search, pro offener Position aus Vortagen)
   └─ Lädt alle Predictions mit `status='open'` und Alter ≤ 5 Handelstage (`learnable=True`)
   └─ Input pro Position: ursprüngliche These + aktueller TickerData + Trend + policy_events
   └─ Prüft: Hält die These? Hat sich Markt/News/Technicals verändert? Gibt es ein stärkeres Signal?
   └─ Output pro Position: `action ∈ {HALTEN, SCHLIESSEN, ANPASSEN}` + Begründung + ggf. neue SL/TP
   └─ DB-Write: `position_recommendations` (siehe §5)
   └─ Konsequenz: Empfehlung erscheint als **erste Sektion** in der E-Mail vor den neuen Top-10 — direkt umsetzbar beim Aufwachen

9. ranking
   └─ Filter: nur guardrail-bestandene Analysen
   └─ Top 10 Long + Top 10 Short
   └─ Commodities + Crypto: alle ausgeben
   └─ DB-Write: predictions (alle Score-Dimensionen, learnable=True)

10. email_sender
    └─ Lädt: position_recommendations (Phase 4a), predictions, trend, eval-stats von gestern
    └─ Rendert 4-Sektionen-HTML: (1) Portfolio-Empfehlungen, (2) Aktien Top-10, (3) Trends, (4) Commodities/Crypto
    └─ SendGrid POST
    └─ DB-Write: cost_tracking (Run-Kosten)
```

### Evaluate-Run (täglich, läuft still ohne Mail)

```
1. Lade alle predictions mit status='open' UND Alter ≤ 5 Handelstage UND learnable=True
2. Pro Prediction:
   - Hole OHLC für die seit Prediction verstrichenen Handelstage
   - Walk-forward Tag für Tag:
     - Long: Low ≤ SL? → sl_hit. High ≥ TP UND Low > SL? → tp_hit
     - Short: spiegelbildlich
   - Bei Tagesrange-Umschluss (High ≥ TP UND Low ≤ SL): sl_hit (pessimistisch)
   - Nach 3 Tagen ohne Hit: close zum Close von Tag 3, P/L = relative Bewegung
3. DB-Write: outcomes + predictions.status / closed_date / closed_price
4. Keine neue E-Mail
```

### Weekly-Run (Sonntag)

Aggregiere Outcomes der Woche, rendere reduzierte Weekly-Mail (Win-Rate aus Walk-Forward + Trade-Liste + Cost-Summary). Lernmodul-Inhalte fehlen im MVP.

### Fehler-Verhalten

- **Phase 0 (Trend) fehlt** → Run abbrechen + Alert-Mail (Trend ist Pflicht-Kontext)
- **Asset-Daten fehlen** (Phase 1) → skip mit `learnable=False`, weiter
- **Phase 3 für einzelnes Asset fehlt** → skip mit Logging, weiter
- **Phase 3 für ALLE Assets fehlt** → Mail trotzdem senden mit "keine Setups gefunden" + Trends + Commodities
- **Cost-Hard-Cap überschritten** → Run beendet, partielle Mail mit Warnung, `cost_tracking.aborted_at_phase` gesetzt

---

## 4 · Modell-Strategie & Kosten-Kontrolle

### Modelle pro Modul

| Modul | Modell | Web-Search? | Typische Tokens (in + out) |
|---|---|---|---|
| `trend_analyzer` | `claude-sonnet-4-6` | ✓ | 4k + 3k |
| `quick_filter` | `claude-haiku-4-5` | – | 6k + 2k (Batch) |
| `policy_monitor` | `claude-sonnet-4-6` | ✓ | 3k + 2k |
| `deep_analysis` (pro Asset) | `claude-sonnet-4-6` | ✓ | 5k + 4k |
| `commodities_crypto` (pro Asset) | `claude-sonnet-4-6` | ✓ | 4k + 3k |
| `learning_module` (Sprint 3) | `claude-opus-4-7` | – | – |

### Prompt-Caching

5-min TTL bei Anthropic. `cache_control: ephemeral` auf:
- System-Prompt (Phase-spezifisch)
- Trend-Kontext (1× pro Run, 20× wiederverwendet)
- Policy-Events (1× pro Run, 20× wiederverwendet)
- Learning-Kontext (leer im MVP)

Effekt: deep_analysis-Loop innerhalb von 5 min → 19 von 20 Calls hitten den Cache → ca. 90 % Token-Rabatt auf statischen Anteil.

### Cost-Tracker

```python
class CostTracker:
    HARD_CAP_EUR = 4.00            # MVP
    WARN_THRESHOLD_EUR = 3.00      # logged, läuft weiter

    def add_call(self, model, input_tok, output_tok,
                 cache_read_tok=0, web_search_calls=0):
        cost = self._calc(...)
        self.total_eur += cost
        if self.total_eur > self.HARD_CAP_EUR:
            raise CostCapExceeded(...)

    def persist(self, run_type: str):
        # nach Run: in cost_tracking-Tabelle persistieren
```

### Pre-Run-Schätzung

Vor Phase 3: `estimated = current_cost + n_deep * 0.10 + n_commodities * 0.10`. Wenn `estimated > HARD_CAP`: nur Top-N analysieren, Mail mit Warnung.

### Cost-Aufschlüsselung in E-Mail-Footer

> Run-Kosten: 2.84 EUR | Cache-Hit-Rate: 87% | Tokens: 142k/63k | Web-Searches: 23

### Kosten-Übersicht pro Tag (Sprint 2, 500 Ticker)

| Run-Type | Kosten |
|---|---|
| pre_market | ~3,20 EUR |
| evaluate | ~0,00 EUR |
| midday | ~3,20 EUR |
| position_check | ~0,20 EUR |
| close | ~0,00 EUR |
| **Gesamt/Tag** | **~6,60 EUR** |
| **Gesamt/Monat (500 Ticker)** | **~145 EUR** |
| **Gesamt/Monat (MVP 20 Ticker)** | **~29 EUR** |

---

## 5 · DB-Persistenz & Eval-Schema

### Release-Asset-Workflow

```yaml
- name: Download DB von Release
  run: |
    gh release download db-latest --pattern "tracking.db" --dir data/ \
      || echo "Erstmaliger Run - leere DB wird erzeugt"
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

- name: Run analysis
  run: python main.py --run-type $TYPE

- name: Upload DB als Release Asset
  if: success()
  run: |
    gh release upload db-latest tracking.db --clobber
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Eine Release `db-latest` mit immer aktueller DB. Versions-History via wöchentlichem Snapshot-Release `db-YYYY-Www` (nicht überschrieben) → automatisches Backup.

### Schema-Deltas zur Spec

Tabellen `technical_indicators`, `fundamentals`, `news_summaries`, `trend_analyses`, `market_context`, `skipped_tickers`, `prompt_versions` bleiben unverändert wie in Spec.

`price_history` erhält ein neues Feld (Sprint 2):

```sql
ALTER TABLE price_history ADD COLUMN premarket_price REAL;
   -- nullable, Capital.com vorbörslicher Kurs
```

`predictions` erhält fünf zusätzliche Felder:

```sql
ALTER TABLE predictions ADD COLUMN status TEXT DEFAULT 'open';
   -- 'open' | 'closed_tp' | 'closed_sl' | 'closed_timeout' | 'closed_data_missing'
ALTER TABLE predictions ADD COLUMN closed_date TEXT;
ALTER TABLE predictions ADD COLUMN closed_price REAL;
ALTER TABLE predictions ADD COLUMN hold_day INTEGER DEFAULT 0;
   -- aktueller Haltetag, täglich +1
ALTER TABLE predictions ADD COLUMN extended_hold BOOLEAN DEFAULT 0;
   -- True ab Tag 2
```

`outcomes` erhält vier zusätzliche Felder:

```sql
ALTER TABLE outcomes ADD COLUMN days_to_close INTEGER;     -- 1–5
ALTER TABLE outcomes ADD COLUMN exit_reason TEXT;
   -- 'tp_hit' | 'sl_hit' | 'timeout_forced' | 'pessimistic_overlap'
ALTER TABLE outcomes ADD COLUMN hold_day INTEGER;
ALTER TABLE outcomes ADD COLUMN extended_hold BOOLEAN;
```

Neue Tabelle `fundamentals_cache` (Sprint 2):

```sql
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
```

`cost_tracking` wird zur Tabelle (statt JSON):

```sql
CREATE TABLE cost_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT, run_type TEXT,
    total_eur REAL, claude_eur REAL, web_search_eur REAL,
    input_tokens INTEGER, output_tokens INTEGER,
    cache_read_tokens INTEGER, cache_hit_rate REAL,
    web_search_calls INTEGER,
    aborted_at_phase TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### CFD-Kurzfrist-Schema-Erweiterungen

`predictions` erhält zwei weitere Pflichtfelder aus dem `deep_analysis`-Output:

```sql
ALTER TABLE predictions ADD COLUMN hold_days_recommended INTEGER;
   -- vom deep_analysis-Prompt zurückgegeben; > 3 → Guardrail-Reject
ALTER TABLE predictions ADD COLUMN intraday_range_pct REAL;
   -- (High-Low)/Close*100 Durchschnitt der letzten 5 Handelstage; < 1.0 → Guardrail-Reject
```

`technical_indicators` erhält ein Feld, das `data_collector._process_ticker()` befüllt:

```sql
ALTER TABLE technical_indicators ADD COLUMN intraday_range_pct REAL;
   -- Quelle für predictions.intraday_range_pct
```

Neue Tabelle `position_recommendations` für die Phase-4a-Ausgabe:

```sql
CREATE TABLE position_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    run_type TEXT NOT NULL,
    prediction_id INTEGER NOT NULL REFERENCES predictions(id),
    action TEXT NOT NULL,
        -- 'HALTEN' | 'SCHLIESSEN' | 'ANPASSEN'
    reason TEXT NOT NULL,
    new_sl_price REAL,                  -- nur bei action='ANPASSEN'
    new_tp_price REAL,                  -- nur bei action='ANPASSEN'
    market_context_changed BOOLEAN,     -- These-Validation aus dem Prompt
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, run_type, prediction_id)
);

CREATE INDEX idx_position_recs_prediction ON position_recommendations(prediction_id);
```

### Walk-Forward-Eval State-Machine

```
                    ┌─────────────┐
                    │   pending   │
                    └─────┬───────┘
                          │ evaluator run
                          ▼
                    ┌─────────────┐
                    │    open     │
                    └─────┬───────┘
                          │
              ┌───────────┼───────────────┬─────────────────────┐
              ▼           ▼               ▼                     ▼
        ┌─────────┐ ┌─────────┐    ┌─────────────┐ ┌──────────────────┐
        │closed_tp│ │closed_sl│    │closed_timeout│ │closed_data_missing│
        └─────────┘ └─────────┘    └─────────────┘ └──────────────────┘
```

### Eval-Logik (Pseudocode)

```python
def evaluate_open_predictions(today):
    for pred in db.load_open_predictions():
        days_elapsed = trading_days_since(pred.date, today)
        if days_elapsed == 0:
            continue

        ohlc = fetch_ohlc(pred.ticker, from_=pred.date, to=today)
        if not ohlc:
            close(pred, exit_reason='data_missing', exit_price=None, day=days_elapsed)
            continue

        closed = False
        for day_offset, bar in enumerate(ohlc, start=1):
            if pred.direction == 'long':
                hit_tp = bar.high >= pred.tp_price
                hit_sl = bar.low  <= pred.sl_price
            else:
                hit_tp = bar.low  <= pred.tp_price
                hit_sl = bar.high >= pred.sl_price

            if hit_tp and hit_sl:
                close(pred, exit_reason='pessimistic_overlap',
                      exit_price=pred.sl_price, day=day_offset)
                closed = True
                break
            if hit_sl:
                close(pred, exit_reason='sl_hit',
                      exit_price=pred.sl_price, day=day_offset)
                closed = True
                break
            if hit_tp:
                close(pred, exit_reason='tp_hit',
                      exit_price=pred.tp_price, day=day_offset)
                closed = True
                break

        if not closed and days_elapsed >= 5:
            close(pred, exit_reason='timeout_forced',
                  exit_price=ohlc[-1].close, day=5)
```

### Datenpflege

Wie in Spec: 90 Tage news_summaries, 180 Tage trend_analyses, 30 Tage skipped_tickers.

---

## 6 · Scoring-Korrekturen

Folgende Inkonsistenzen aus der Spec sind in diesem Design korrigiert:

### Signal-Konsistenz-Check

```
Long  braucht momentum_score ≥ 6.0
Short braucht momentum_score ≤ 4.0   # Spec sagte 7.0 — war Copy-Paste-Fehler
```

### R/R-Ratio

- **Standard-Formel**: `tp = sl * 2.0` (1:2)
- **Hard-Minimum (Guardrails)**: `R/R ≥ 1.5` (engerer SL bei sehr nahem Support/Resistance erlaubt)
- Prosa-Aussage „immer min. 1:2" aus Spec ist damit überholt — gilt nur als Default

### Dimensions-Gewichtungen

Unverändert wie in Spec:

```python
DIMENSION_WEIGHTS = {
    "market_environment": 0.10,
    "company_quality":    0.18,
    "valuation":           0.12,
    "momentum":           0.22,
    "risk":               0.10,
    "sector_trend":       0.10,
    "catalyst":           0.10,
    "policy_risk":        0.08,
}
```

### CFD-Kurzfrist-Guardrails

Zusätzlich zu Required-Fields, Evidenz-Min., R/R-Min. und Signal-Konsistenz muss `guardrails.py` zwei harte Filter durchsetzen:

```python
if analysis.get("hold_days_recommended", 99) > 5:
    errors.append("Haltedauer > 5 Tage – nicht CFD-geeignet")

if analysis.get("intraday_range_pct", 0) < 1.0:
    errors.append("Intraday-Range < 1.0% – nicht CFD-geeignet")
```

Begründung:
- **`hold_days_recommended`**: vom `deep_analysis`-Prompt erzwungenes Pflichtfeld. Setups, die der Trader länger als 5 Handelstage halten müsste (`MAX_HOLD_DAYS = 5`), gehören nicht in eine CFD-Top-10.
- **`intraday_range_pct`**: aus `data_collector._process_ticker()` als `(High-Low)/Close*100`, gemittelt über die letzten 5 Handelstage. Aktien mit Range < 1 % bewegen sich innerhalb eines Tages zu wenig, um Intraday-CFDs sinnvoll zu traden.

`intraday_range_pct` wird zusätzlich in der E-Mail-Tabelle als Spalte „Range/Tag" neben „ATR/Tag" ausgegeben.

---

## 7 · Cron-Plan & DST

GitHub Actions läuft in UTC ohne DST-Awareness. Wir fixieren in UTC und akzeptieren die 1-h-Verschiebung zwischen Winter und Sommer (lokale Zeit verschiebt sich; *relative* Zeit zum US-Markt bleibt stabil, weil US und EU beide DST haben).

Jeder Run-Type hat **zwei Cron-Einträge** (Sommer/Winter) für DST-Korrektheit. Run-Type-Bestimmung via `TZ="Europe/Berlin"` in Bash.

| Berliner Zeit | `run_type` | Kosten | Zweck |
|---|---|---|---|
| 14:00 Mo–Fr | `pre_market` | ~3,20 EUR | Setups vor US-Open. Mail |
| 15:00 Mo–Fr | `evaluate` | ~0,00 EUR | Walk-Forward Hit-Check. Kein Mail |
| 16:15 Mo–Fr | `midday` | ~3,20 EUR | 45 min nach US-Open. Mail |
| 17:30 Mo–Fr | `position_check` | ~0,20 EUR | Capital.com GET /positions + Claude + Status-Mail (Sprint 2) |
| 22:30 Mo–Fr | `close` | ~0,00 EUR | NUR Datenpflege, kein Claude, kein Mail |
| 20:00 So | `weekly` | ~0,00 EUR | Wochen-Performance. Mail |

Pro Werktag: **2 Analyse-Mails** + 1 Position-Check-Mail + stille Runs. Sonntags Weekly-Mail.

**Wichtigste Runs:** `pre_market` und `midday` (je ~3,20 EUR). `close` ist vereinfacht und nur noch Datenpflege. Phase 4a läuft in den Analyse-Runs und steht ganz oben in der E-Mail.

---

## 8 · Environment Variables

```
ANTHROPIC_API_KEY=...
SENDGRID_API_KEY=...
EMAIL_TO=korbinian.bronold@gmail.com
EMAIL_FROM=...
FINNHUB_API_KEY=...              # Earnings-Calendar + Fundamentals (gecacht)
CAPITAL_COM_API_KEY=...          # Sprint 2: Capital.com Demo API
CAPITAL_COM_PASSWORD=...         # Sprint 2: Capital.com Demo Passwort
```

GitHub Secrets analog. `GITHUB_TOKEN` ist von Actions automatisch verfügbar (für Release-Upload).

---

## 9 · Testing

### Struktur

```
tests/
├── unit/                            # Mocked externals
│   ├── test_yfinance_provider.py   # Rate-Limiting, Retry, OHLC-Parsing
│   ├── test_finnhub_provider.py    # Earnings-Parsing, Quota-Handling
│   ├── test_data_collector.py      # Indikator-Berechnung, Skipped-Logging
│   ├── test_trend_analyzer.py
│   ├── test_quick_filter.py
│   ├── test_deep_analysis.py
│   ├── test_commodities_crypto.py
│   ├── test_ranking.py
│   ├── test_evaluator.py           # Alle 4 Exit-Reasons
│   ├── test_portfolio_check.py     # HALTEN/SCHLIESSEN/ANPASSEN-Klassifikation
│   ├── test_email_sender.py        # HTML-Snapshot, inkl. Phase-4a-Sektion
│   ├── test_guardrails.py          # Alle Reject-Cases, R/R-Check 1.5, hold_days>3, intraday<1.0
│   ├── test_cost_tracker.py        # Hard-Cap-Abort
│   └── test_db.py                  # Schema, Migrations, Upserts
├── integration/
│   ├── test_full_pipeline.py       # E2E 5 Ticker, alle Phasen
│   ├── test_eval_loop.py           # Predict Tag 1 → 3 Tage OHLC-Fixture → Eval
│   └── test_email_render.py        # HTML-Snapshot
├── fixtures/
│   ├── sample_ohlc.csv             # 90 Tage × 27 Assets
│   ├── mock_claude_responses.json
│   ├── mock_finnhub_earnings.json
│   └── mock_trend_response.json
└── conftest.py
```

### Test-Philosophie

- **Unit**: alle externen Dependencies gemockt (Claude, yfinance, Finnhub, SendGrid). Schnell, deterministisch.
- **Integration**: 5 Ticker, alle Phasen verkettet, externe APIs weiter gemockt. Validiert Phase-Glue.
- **Smoke** (manuell vor jedem Sprint-Übergang): echte APIs, gemockter SendGrid.

CI-Gate: 80 % Coverage in `.github/workflows/test.yml` erzwungen.

---

## 10 · Implementierungs-Reihenfolge (Sprint 1)

| # | Modul / Schritt | Test-Gate |
|---|---|---|
| 1 | `requirements.txt`, `.env.example`, `config.py` | – |
| 2 | `src/utils.py` (Logging, Retry, Claude-Wrapper mit Caching) | `test_utils.py` |
| 3 | `tests/conftest.py` | – |
| 4 | `src/db.py` (Schema, Migrations, Helpers) | `test_db.py` |
| 5 | `src/providers/*` (yfinance + finnhub + paid-stub) | provider-Tests |
| 6 | `src/guardrails.py` | `test_guardrails.py` |
| 7 | `src/cost_tracker.py` | `test_cost_tracker.py` |
| 8 | `src/data_collector.py` | `test_data_collector.py` |
| 9 | `src/trend_analyzer.py` | `test_trend_analyzer.py` |
| 10 | `src/quick_filter.py` | `test_quick_filter.py` |
| 11 | `src/deep_analysis.py` (mit Policy-Monitor) | `test_deep_analysis.py` |
| 12 | `src/commodities_crypto.py` | `test_commodities_crypto.py` |
| 13 | `src/ranking.py` | `test_ranking.py` |
| 14 | `src/evaluator.py` | `test_evaluator.py` |
| 15 | `src/portfolio_check.py` (Phase 4a) | `test_portfolio_check.py` |
| 16 | `src/email_sender.py` (Daily 4-Sektionen + Weekly reduziert) | `test_email_sender.py` |
| 17 | `main.py` (Orchestrator) | `test_full_pipeline.py` |
| 18 | Coverage-Check | `pytest --cov-fail-under=80` |
| 19 | `.github/workflows/test.yml` | grüner Push-Build |
| 20 | **Smoke-Test manuell** mit echtem yfinance + Claude + SendGrid | E-Mail im Posteingang |
| 21 | `.github/workflows/analyze.yml` (Cron + Release-Asset) | erster Cron-Run grün |

### Sprint-1-Definition of Done

- ✅ Drei aufeinanderfolgende Werktage haben automatisch 3 Mails/Tag versendet
- ✅ Evaluate-Run hat min. 3× Outcomes erfolgreich geschrieben
- ✅ Weekly-Mail einmal versendet
- ✅ Run-Kosten reproducierbar < 4 EUR
- ✅ DB-Persistenz via Release-Asset hat einen Cron-Cycle überlebt

Erst danach: Sprint-Gate-Review → Entscheidung über Sprint 2.

---

## 11 · Defaults & Kleinteile

- **Earnings-Calendar**: Finnhub Free Tier (`FINNHUB_API_KEY`) — als eigener Provider hinter dem DataProvider-Interface. Bei `None`-Response toleriert das Scoring den fehlenden Wert.
- **Weekly-Mail im MVP**: läuft als Pipeline-Test, reduzierter Inhalt (kein Lernmodul-Output).
- **DST**: UTC-fix, 1-h-Verschiebung akzeptiert.
- **SP500-Auto-Update**: Sprint 2.
- **Trump/Policy-Formulierung**: bleibt wie in Spec (Trump als Unterfall, nicht Fixpunkt).
- **E-Mail-Design Sektion 2 (Dunkel)**: bleibt wie in Spec.

---

## 12 · Disclaimer

```
Shares_Future ist ein automatisiertes Research- und Paper-Trading-System
ohne automatische Orderausführung. Alle Analysen dienen ausschließlich
zu Informationszwecken und stellen KEINE Anlageberatung dar.
CFD-Handel kann zum Totalverlust führen. Keine Garantie für Prognosen.
```

`SIMULATION_ONLY = True` ist hart verdrahtet und darf niemals auf `False` gesetzt werden.

---

*Shares_Future MVP Design | 2026-05-19 | Zuletzt aktualisiert 2026-05-22 | basiert auf Spec v5.0 vom 2026-05-22*
