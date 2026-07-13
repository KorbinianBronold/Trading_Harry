> ⚠️ HISTORISCH — docs/superpowers/specs/PROJECT_STATUS.md lesen stattdessen

# Sprint 1 / Plan 2: Data Collector, Trend Analyzer, Quick Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 0 (trend analysis), Phase 1 (data collection with indicators), and Phase 2 (Haiku batch quick-filter) on top of the merged foundation (`7110f29`).

**Architecture:** Three thin orchestration modules sitting on the existing foundation. `data_collector` loops the 27-asset MVP universe and produces a list of `TickerData` dicts plus DB writes via `db.py`. `trend_analyzer` runs once per run with Sonnet + web-search and writes 3-7 trend rows. `quick_filter` accepts the list of `TickerData` and the trend context, runs a single Haiku batch call, and returns per-ticker scores. All Claude calls go through the existing `utils.call_claude` wrapper and accumulate into a `CostTracker` instance owned by the caller.

**Tech Stack:** Python 3.11+, pandas, pandas-ta (RSI/MACD/ATR/BB/SMA), yfinance + finnhub (already wrapped), Anthropic SDK with prompt caching + server-side web_search tool, sqlite3, pytest, pytest-mock, freezegun.

**Spec reference:** `docs/superpowers/specs/2026-05-19-trading-harry-mvp-design.md` §1, §3, §4, §6, §10 rows 8-10.

**Foundation reference:** Plan 1 merged as `7110f29`. Available: `config.py`, `src/utils.py` (`retry_with_backoff`, `call_claude`, `ClaudeResult`), `src/db.py` (schema + upsert/save helpers), `src/providers/{base,yfinance,finnhub,paid}_provider.py`, `src/guardrails.py`, `src/cost_tracker.py` (`CostTracker`, `CostCapExceeded`), `tests/conftest.py` (`in_memory_db`, `tmp_db_path`, `sample_ticker_data`).

---

## File Structure

```
Shares_Future/
├── prompts/                                  # NEW directory
│   ├── trend_analyzer_v1.txt                 # NEW
│   └── quick_filter_v1.txt                   # NEW
├── src/
│   ├── utils.py                              # MODIFY: ClaudeResult.web_search_calls
│   ├── db.py                                 # MODIFY: new helpers + migration
│   ├── data_collector.py                     # NEW
│   ├── trend_analyzer.py                     # NEW
│   └── quick_filter.py                       # NEW
└── tests/
    ├── fixtures/
    │   ├── mock_trend_response.json          # NEW
    │   └── mock_quick_filter_response.json   # NEW
    └── unit/
        ├── test_utils.py                     # MODIFY: web_search_calls test
        ├── test_db.py                        # MODIFY: tests for new helpers + migration
        ├── test_data_collector.py            # NEW
        ├── test_trend_analyzer.py            # NEW
        └── test_quick_filter.py              # NEW
```

### Boundary rules carried over from spec §2

- Phase modules call DB only through `db.py` (no inline SQL).
- All Claude calls go through `utils.call_claude` (prompt caching, retry, token return).
- `CostTracker` is **owned by the caller** (orchestrator in main.py will create it; in this plan, tests create one and modules accept it as a parameter).
- On missing data: log via `db.log_skipped_ticker(..., learnable=False)` and continue. Never raise out of an asset loop.

---

## Task 1: Foundation extensions — `ClaudeResult.web_search_calls`, db.py helpers, schema migration

The trend analyzer and quick-filter need three foundation extensions before they can be built:

1. `ClaudeResult` must surface `web_search_calls` so `CostTracker.add_call(..., web_search_calls=...)` can bill correctly. The current wrapper only returns text + token counts.
2. `db.py` needs three new helpers — `upsert_technical_indicators`, `save_trend_analysis`, `log_skipped_ticker` — used by the three new phase modules.
3. `technical_indicators` needs the `intraday_range_pct` column (spec §5 CFD-Kurzfrist-Schema-Erweiterungen). It is the source for `predictions.intraday_range_pct` (predictions column is filled by deep_analysis in a later plan).

These are not quality nits; the next three tasks depend on them.

**Files:**
- Modify: `src/utils.py:48-90` (extend `ClaudeResult` + `call_claude`)
- Modify: `src/db.py:13-19` (add `intraday_range_pct` column to schema) + append new helpers
- Modify: `tests/unit/test_utils.py` (add web_search_calls assertion)
- Modify: `tests/unit/test_db.py` (add tests for new helpers + migration idempotency)

- [ ] **Step 1.1: Write failing test for `web_search_calls` in `ClaudeResult`**

Append to `tests/unit/test_utils.py`:

```python
def test_call_claude_extracts_web_search_calls():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="ok")]
    fake_response.usage.input_tokens = 100
    fake_response.usage.output_tokens = 50
    fake_response.usage.cache_read_input_tokens = 0
    fake_response.usage.cache_creation_input_tokens = 0
    fake_response.usage.server_tool_use = MagicMock(web_search_requests=3)

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("src.utils._anthropic_client", fake_client):
        result = call_claude(
            model="claude-sonnet-4-6",
            system="s", user="u",
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        )

    assert result.web_search_calls == 3


def test_call_claude_web_search_calls_zero_when_absent():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="ok")]
    fake_response.usage.input_tokens = 10
    fake_response.usage.output_tokens = 5
    fake_response.usage.cache_read_input_tokens = 0
    fake_response.usage.cache_creation_input_tokens = 0
    # No server_tool_use attribute → 0
    del fake_response.usage.server_tool_use

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("src.utils._anthropic_client", fake_client):
        result = call_claude(model="claude-haiku-4-5", system="s", user="u")

    assert result.web_search_calls == 0
```

- [ ] **Step 1.2: Run test, expect failure**

Run: `pytest tests/unit/test_utils.py::test_call_claude_extracts_web_search_calls tests/unit/test_utils.py::test_call_claude_web_search_calls_zero_when_absent -v`
Expected: AttributeError — `ClaudeResult` has no `web_search_calls`.

- [ ] **Step 1.3: Extend `ClaudeResult` and `call_claude`**

In `src/utils.py`, modify the `ClaudeResult` dataclass and the `call_claude` return statement:

```python
@dataclass
class ClaudeResult:
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    model: str
    web_search_calls: int = 0
```

And inside `call_claude`, replace the existing `return ClaudeResult(...)` block with:

```python
    text_parts = [b.text for b in response.content if hasattr(b, "text")]

    server_tool_use = getattr(response.usage, "server_tool_use", None)
    web_search_calls = 0
    if server_tool_use is not None:
        web_search_calls = getattr(server_tool_use, "web_search_requests", 0) or 0

    return ClaudeResult(
        text="\n".join(text_parts),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        cache_creation_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
        model=model,
        web_search_calls=web_search_calls,
    )
```

- [ ] **Step 1.4: Run test, expect green**

Run: `pytest tests/unit/test_utils.py -v`
Expected: 7 passed (5 existing + 2 new).

- [ ] **Step 1.5: Write failing tests for db.py extensions**

Append to `tests/unit/test_db.py`:

```python
from src.db import (
    upsert_technical_indicators, save_trend_analysis, log_skipped_ticker,
)


def test_technical_indicators_schema_has_intraday_range_pct(in_memory_db):
    init_schema(in_memory_db)
    cols = [r["name"] for r in in_memory_db.execute(
        "PRAGMA table_info(technical_indicators)"
    ).fetchall()]
    assert "intraday_range_pct" in cols


def test_upsert_technical_indicators_inserts_and_replaces(in_memory_db):
    init_schema(in_memory_db)
    upsert_technical_indicators(in_memory_db, {
        "ticker": "AAPL", "date": "2026-05-19",
        "rsi_14": 58.4, "macd_signal": "bullish_cross", "atr_pct": 1.8,
        "bb_position": 0.62, "above_sma20": 2.1, "above_sma50": 5.4,
        "above_sma200": 12.8, "volume_ratio": 1.15, "intraday_range_pct": 1.4,
    })
    row = in_memory_db.execute(
        "SELECT * FROM technical_indicators WHERE ticker=? AND date=?",
        ("AAPL", "2026-05-19"),
    ).fetchone()
    assert row["rsi_14"] == 58.4
    assert row["intraday_range_pct"] == 1.4

    # Re-upsert overwrites
    upsert_technical_indicators(in_memory_db, {
        "ticker": "AAPL", "date": "2026-05-19",
        "rsi_14": 60.0, "macd_signal": "neutral", "atr_pct": 1.9,
        "bb_position": 0.7, "above_sma20": 2.5, "above_sma50": 5.6,
        "above_sma200": 13.0, "volume_ratio": 1.2, "intraday_range_pct": 1.5,
    })
    row = in_memory_db.execute(
        "SELECT rsi_14, intraday_range_pct FROM technical_indicators "
        "WHERE ticker=? AND date=?", ("AAPL", "2026-05-19"),
    ).fetchone()
    assert row["rsi_14"] == 60.0
    assert row["intraday_range_pct"] == 1.5


def test_save_trend_analysis_roundtrip(in_memory_db):
    init_schema(in_memory_db)
    save_trend_analysis(in_memory_db, {
        "date": "2026-05-19", "run_type": "pre_market",
        "trend_name": "ai-capex-acceleration",
        "strength": 8, "duration_estimate": "1m+",
        "summary": "Hyperscalers raised guidance two quarters in a row.",
        "beneficiary_tickers": ["NVDA", "AVGO"],
        "negative_tickers": ["INTC"],
        "next_catalyst": "GTC keynote 2026-06-12",
    })
    row = in_memory_db.execute(
        "SELECT * FROM trend_analyses WHERE trend_name=?",
        ("ai-capex-acceleration",),
    ).fetchone()
    assert row["strength"] == 8
    assert row["beneficiary_tickers"] == "NVDA,AVGO"
    assert row["negative_tickers"] == "INTC"


def test_save_trend_analysis_unique_per_date_and_name(in_memory_db):
    init_schema(in_memory_db)
    row = {
        "date": "2026-05-19", "run_type": "pre_market",
        "trend_name": "ai-capex-acceleration",
        "strength": 8, "duration_estimate": "1m+",
        "summary": "x", "beneficiary_tickers": ["NVDA"],
        "negative_tickers": [], "next_catalyst": "x",
    }
    save_trend_analysis(in_memory_db, row)
    save_trend_analysis(in_memory_db, {**row, "strength": 9})  # replace
    rows = in_memory_db.execute(
        "SELECT strength FROM trend_analyses WHERE trend_name=?",
        ("ai-capex-acceleration",),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["strength"] == 9


def test_log_skipped_ticker_inserts_row(in_memory_db):
    init_schema(in_memory_db)
    log_skipped_ticker(
        in_memory_db,
        ticker="XYZ", date="2026-05-19", run_type="pre_market",
        reason="yfinance returned no data", learnable=False,
    )
    row = in_memory_db.execute(
        "SELECT * FROM skipped_tickers WHERE ticker=?", ("XYZ",),
    ).fetchone()
    assert row["reason"] == "yfinance returned no data"
    assert row["learnable"] == 0
```

- [ ] **Step 1.6: Run failing tests**

Run: `pytest tests/unit/test_db.py -v`
Expected: ImportError on `upsert_technical_indicators`, `save_trend_analysis`, `log_skipped_ticker`.

- [ ] **Step 1.7: Add `intraday_range_pct` to schema**

In `src/db.py`, modify the `technical_indicators` table definition inside `SCHEMA_SQL` from:

```sql
CREATE TABLE IF NOT EXISTS technical_indicators (
    ticker TEXT NOT NULL, date TEXT NOT NULL,
    rsi_14 REAL, macd_signal TEXT, atr_pct REAL,
    bb_position REAL, above_sma20 REAL, above_sma50 REAL, above_sma200 REAL,
    volume_ratio REAL,
    UNIQUE(ticker, date)
);
```

to:

```sql
CREATE TABLE IF NOT EXISTS technical_indicators (
    ticker TEXT NOT NULL, date TEXT NOT NULL,
    rsi_14 REAL, macd_signal TEXT, atr_pct REAL,
    bb_position REAL, above_sma20 REAL, above_sma50 REAL, above_sma200 REAL,
    volume_ratio REAL, intraday_range_pct REAL,
    UNIQUE(ticker, date)
);
```

- [ ] **Step 1.8: Add a forward-compat migration for existing DBs**

Append below the `SCHEMA_SQL` constant in `src/db.py`:

```python
def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Idempotent column-add migrations for pre-existing DBs.
    SQLite does not support IF NOT EXISTS on ALTER TABLE, so we inspect first."""
    existing = {r["name"] for r in conn.execute(
        "PRAGMA table_info(technical_indicators)"
    ).fetchall()}
    if "intraday_range_pct" not in existing:
        conn.execute(
            "ALTER TABLE technical_indicators ADD COLUMN intraday_range_pct REAL"
        )
    conn.commit()
```

And update `init_schema` to call it:

```python
def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    _apply_migrations(conn)
```

- [ ] **Step 1.9: Implement the three new helpers**

Append to `src/db.py`:

```python
def upsert_technical_indicators(conn: sqlite3.Connection, row: dict) -> None:
    cols = [
        "ticker", "date", "rsi_14", "macd_signal", "atr_pct",
        "bb_position", "above_sma20", "above_sma50", "above_sma200",
        "volume_ratio", "intraday_range_pct",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    values = [row.get(c) for c in cols]
    conn.execute(
        f"INSERT OR REPLACE INTO technical_indicators ({', '.join(cols)}) "
        f"VALUES ({placeholders})",
        values,
    )
    conn.commit()


def save_trend_analysis(conn: sqlite3.Connection, trend: dict) -> None:
    """Insert or replace one trend row. Lists serialised as comma-joined strings."""
    beneficiaries = ",".join(trend.get("beneficiary_tickers") or [])
    negatives = ",".join(trend.get("negative_tickers") or [])
    conn.execute(
        """INSERT OR REPLACE INTO trend_analyses
           (date, run_type, trend_name, strength, duration_estimate, summary,
            beneficiary_tickers, negative_tickers, next_catalyst)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            trend["date"], trend["run_type"], trend["trend_name"],
            trend.get("strength"), trend.get("duration_estimate"),
            trend.get("summary"), beneficiaries, negatives,
            trend.get("next_catalyst"),
        ),
    )
    conn.commit()


def log_skipped_ticker(
    conn: sqlite3.Connection,
    ticker: str, date: str, run_type: str,
    reason: str, learnable: bool = False,
) -> None:
    conn.execute(
        """INSERT INTO skipped_tickers
           (ticker, date, run_type, reason, learnable)
           VALUES (?, ?, ?, ?, ?)""",
        (ticker, date, run_type, reason, 1 if learnable else 0),
    )
    conn.commit()
```

- [ ] **Step 1.10: Run all db tests, expect green**

Run: `pytest tests/unit/test_db.py -v`
Expected: 11 passed (6 existing + 5 new).

- [ ] **Step 1.11: Commit**

```bash
git add src/utils.py src/db.py tests/unit/test_utils.py tests/unit/test_db.py
git commit -m "Extend ClaudeResult.web_search_calls + db helpers + intraday_range_pct migration"
```

---

## Task 2: Prompt templates

Two prompt files used by `trend_analyzer` and `quick_filter`. They are read at module import time. Sprint 3 introduces versioned A/B-tested prompts; in MVP we read v1 from disk.

**Files:**
- Create: `prompts/trend_analyzer_v1.txt`
- Create: `prompts/quick_filter_v1.txt`

- [ ] **Step 2.1: Create `prompts/trend_analyzer_v1.txt`**

```
You are a macro market analyst specialized in identifying dominant market trends
relevant to short-term CFD trades (hold 1-3 trading days) on US large-cap equities,
gold, silver, oil, and major crypto.

Use the web_search tool to gather current evidence (last 24h news, sector ETF flows,
macro indicators, policy events). Always cite at least one source per trend.

Output ONLY a single JSON object, no prose before or after, with this EXACT shape:

{
  "trends": [
    {
      "name": "<short kebab-case label, e.g. 'ai-capex-acceleration'>",
      "strength": <integer 1-10>,
      "duration_estimate": "<one of: '1-3d', '1w', '1m+'>",
      "summary": "<one paragraph, max 400 chars, includes a source attribution>",
      "beneficiary_tickers": ["TICK1", "TICK2"],
      "negative_tickers": ["TICK3"],
      "next_catalyst": "<event description + ISO date e.g. 'FOMC 2026-06-18'>"
    }
  ],
  "sector_rotation": {
    "into":   ["<sector ETF or sector name>", "..."],
    "out_of": ["<sector ETF or sector name>", "..."]
  },
  "trend_summary": "<2-3 sentence overall market take, max 600 chars>"
}

Constraints:
- Return 3 to 7 trends, sorted by strength descending.
- Tickers must be valid SP500 symbols, commodity futures (GC=F, SI=F, CL=F),
  or major crypto (BTC-USD, ETH-USD, SOL-USD, XRP-USD).
- Never invent dates; if a catalyst is unknown, write "TBD".
- If web_search returns nothing usable, return an empty "trends" list and explain
  in "trend_summary".
```

- [ ] **Step 2.2: Create `prompts/quick_filter_v1.txt`**

```
You are a batch-screening analyst for short-term CFD trades (hold 1-3 trading days).
You receive a batch of tickers with their technical + fundamental snapshot and the
current macro trend context. You do NOT have web access — work only from the data
provided in the user message.

Output ONLY a single JSON object, no prose before or after, with this EXACT shape:

{
  "results": [
    {
      "ticker": "<symbol from the batch>",
      "long_score":  <number 0-10, one decimal allowed>,
      "short_score": <number 0-10, one decimal allowed>,
      "confidence":  "<one of: 'low', 'medium', 'high'>",
      "evidence":    ["<one terse line>", "<another>"],
      "exclude":     <true | false>
    }
  ]
}

Scoring rules:
- long_score and short_score are independent — both can be high if the setup is
  ambiguous (low confidence).
- Set "exclude": true if any of the following holds:
    * data_quality == "low"
    * atr_pct < 0.8
    * an obvious red flag in the snapshot (e.g., earnings within 2 trading days
      AND high momentum collapse risk)
- Confidence must be "low" whenever data_quality == "medium".
- Evidence: 1-3 short lines. Cite specific numbers from the snapshot.
- Return one entry per ticker in the batch, in the same order. Never invent tickers.
```

- [ ] **Step 2.3: Verify prompts load**

Run: `python -c "from pathlib import Path; print(len(Path('prompts/trend_analyzer_v1.txt').read_text())); print(len(Path('prompts/quick_filter_v1.txt').read_text()))"`
Expected: Two positive integers printed.

- [ ] **Step 2.4: Commit**

```bash
git add prompts/trend_analyzer_v1.txt prompts/quick_filter_v1.txt
git commit -m "Add v1 prompt templates for trend_analyzer and quick_filter"
```

---

## Task 3: `data_collector.py` — indicator helpers (pure math)

Pure functions over `pandas.DataFrame` that compute the indicators consumed downstream. Tested in isolation with deterministic synthetic price series. No I/O, no provider calls, no DB. Splits Task 3 → Task 4 → Task 5 so each layer has a clean test surface.

**Files:**
- Create: `src/data_collector.py` (indicator helpers only in this task)
- Create: `tests/unit/test_data_collector.py` (indicator tests only in this task)

- [ ] **Step 3.1: Write failing tests for indicator helpers**

`tests/unit/test_data_collector.py`:

```python
import math
import pandas as pd
import pytest
from src.data_collector import (
    compute_rsi_14, compute_rsi_trend, compute_macd_signal,
    compute_atr_pct, compute_bb_position,
    compute_sma_distance_pct, compute_volume_ratio,
    compute_intraday_range_pct, compute_price_changes,
)


def _df_monotonic_up(rows: int = 250) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=rows, freq="B")
    closes = [100 + i * 0.5 for i in range(rows)]
    return pd.DataFrame({
        "Open":   [c - 0.1 for c in closes],
        "High":   [c + 0.5 for c in closes],
        "Low":    [c - 0.5 for c in closes],
        "Close":  closes,
        "Volume": [1_000_000 + i * 1_000 for i in range(rows)],
    }, index=idx)


def _df_oscillating(rows: int = 250, amp: float = 5.0) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=rows, freq="B")
    closes = [100 + amp * math.sin(i / 5) for i in range(rows)]
    return pd.DataFrame({
        "Open":   closes,
        "High":   [c + amp * 0.3 for c in closes],
        "Low":    [c - amp * 0.3 for c in closes],
        "Close":  closes,
        "Volume": [1_000_000] * rows,
    }, index=idx)


def test_compute_rsi_14_on_monotonic_up_is_high():
    df = _df_monotonic_up(60)
    rsi = compute_rsi_14(df)
    assert rsi > 80


def test_compute_rsi_14_returns_none_when_too_short():
    df = _df_monotonic_up(10)
    assert compute_rsi_14(df) is None


def test_compute_rsi_trend_classifies_rising_and_falling():
    df_up = _df_monotonic_up(60)
    assert compute_rsi_trend(df_up) == "rising"

    df_down = _df_monotonic_up(60)
    df_down["Close"] = df_down["Close"].iloc[::-1].reset_index(drop=True).values
    # rebuild with descending close so RSI falls
    df_down.index = pd.date_range("2025-01-01", periods=60, freq="B")
    assert compute_rsi_trend(df_down) in {"falling", "neutral"}


def test_compute_macd_signal_returns_one_of_three_labels():
    df = _df_monotonic_up(60)
    assert compute_macd_signal(df) in {"bullish_cross", "bearish_cross", "neutral"}


def test_compute_atr_pct_is_positive_for_oscillating_series():
    df = _df_oscillating(60)
    atr = compute_atr_pct(df)
    assert atr is not None
    assert 0 < atr < 50


def test_compute_bb_position_in_zero_one_range():
    df = _df_oscillating(60)
    bb = compute_bb_position(df)
    assert bb is None or 0 <= bb <= 1


def test_compute_sma_distance_pct_positive_for_uptrend():
    df = _df_monotonic_up(250)
    dist20 = compute_sma_distance_pct(df, 20)
    dist50 = compute_sma_distance_pct(df, 50)
    dist200 = compute_sma_distance_pct(df, 200)
    assert dist20 > 0
    assert dist50 > 0
    assert dist200 > 0


def test_compute_sma_distance_pct_returns_none_when_too_short():
    df = _df_monotonic_up(50)
    assert compute_sma_distance_pct(df, 200) is None


def test_compute_volume_ratio_returns_value_near_one_for_flat_volume():
    df = _df_oscillating(60)
    v = compute_volume_ratio(df)
    assert v is not None
    assert 0.9 < v < 1.1


def test_compute_intraday_range_pct_mean_last_5_days():
    rows = 10
    idx = pd.date_range("2025-01-01", periods=rows, freq="B")
    df = pd.DataFrame({
        "Open":   [100] * rows,
        "High":   [102] * rows,   # high-low = 2.0
        "Low":    [100] * rows,
        "Close":  [101] * rows,   # range/close = 2/101 ≈ 1.98%
        "Volume": [1_000_000] * rows,
    }, index=idx)
    r = compute_intraday_range_pct(df)
    assert r is not None
    assert 1.95 < r < 2.01


def test_compute_intraday_range_pct_returns_none_when_too_short():
    df = _df_monotonic_up(3)
    assert compute_intraday_range_pct(df) is None


def test_compute_price_changes_returns_dict_with_expected_keys():
    df = _df_monotonic_up(80)
    out = compute_price_changes(df)
    assert set(out.keys()) == {"price_change_1d", "price_change_5d",
                               "price_change_1m", "price_change_3m"}
    # Monotonic up → all positive
    assert all(v is None or v > 0 for v in out.values())
```

- [ ] **Step 3.2: Run failing tests**

Run: `pytest tests/unit/test_data_collector.py -v`
Expected: ImportError — `src/data_collector` doesn't exist.

- [ ] **Step 3.3: Implement indicator helpers**

`src/data_collector.py`:

```python
"""Phase 1: Data collection + indicator math.

Indicator helpers are pure functions over a pandas OHLCV DataFrame and are
tested in isolation. The collect()/_process_ticker() functions live in this
same module (added in Tasks 4 and 5) and wire these helpers up with the
DataProvider interface and db.py.
"""
import logging
import math
from typing import Any

import pandas as pd
import pandas_ta as ta

log = logging.getLogger("shares_future.data_collector")

MIN_BARS_RSI = 20
MIN_BARS_ATR = 20
MIN_BARS_BB = 25
MIN_BARS_VOL = 25
MIN_BARS_INTRADAY = 5


def _last_finite(series: pd.Series) -> float | None:
    if series is None or len(series) == 0:
        return None
    val = series.iloc[-1]
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return float(val)


def compute_rsi_14(df: pd.DataFrame) -> float | None:
    if len(df) < MIN_BARS_RSI:
        return None
    rsi = ta.rsi(df["Close"], length=14)
    return _last_finite(rsi)


def compute_rsi_trend(df: pd.DataFrame) -> str:
    """rising | falling | neutral based on last vs. 3-bar-ago RSI."""
    if len(df) < MIN_BARS_RSI + 3:
        return "neutral"
    rsi = ta.rsi(df["Close"], length=14)
    if rsi is None or len(rsi) < 4:
        return "neutral"
    last, prev = rsi.iloc[-1], rsi.iloc[-4]
    if pd.isna(last) or pd.isna(prev):
        return "neutral"
    if last - prev > 2:
        return "rising"
    if last - prev < -2:
        return "falling"
    return "neutral"


def compute_macd_signal(df: pd.DataFrame) -> str:
    """bullish_cross if MACD crossed above signal in the last 2 bars,
    bearish_cross if crossed below, else neutral."""
    if len(df) < 35:
        return "neutral"
    macd = ta.macd(df["Close"])
    if macd is None or macd.empty:
        return "neutral"
    macd_line = macd.iloc[:, 0]
    signal_line = macd.iloc[:, 2]
    if len(macd_line) < 3 or len(signal_line) < 3:
        return "neutral"
    diff_now = macd_line.iloc[-1] - signal_line.iloc[-1]
    diff_prev = macd_line.iloc[-2] - signal_line.iloc[-2]
    if pd.isna(diff_now) or pd.isna(diff_prev):
        return "neutral"
    if diff_prev < 0 and diff_now >= 0:
        return "bullish_cross"
    if diff_prev > 0 and diff_now <= 0:
        return "bearish_cross"
    return "neutral"


def compute_atr_pct(df: pd.DataFrame) -> float | None:
    if len(df) < MIN_BARS_ATR:
        return None
    atr = ta.atr(df["High"], df["Low"], df["Close"], length=14)
    last = _last_finite(atr)
    if last is None:
        return None
    close = _last_finite(df["Close"])
    if not close:
        return None
    return round(last / close * 100, 3)


def compute_bb_position(df: pd.DataFrame) -> float | None:
    if len(df) < MIN_BARS_BB:
        return None
    bb = ta.bbands(df["Close"], length=20)
    if bb is None or bb.empty:
        return None
    lower = bb.iloc[-1, 0]
    upper = bb.iloc[-1, 2]
    close = df["Close"].iloc[-1]
    if pd.isna(lower) or pd.isna(upper) or upper == lower:
        return None
    pos = (close - lower) / (upper - lower)
    return round(max(0.0, min(1.0, float(pos))), 3)


def compute_sma_distance_pct(df: pd.DataFrame, length: int) -> float | None:
    if len(df) < length:
        return None
    sma = ta.sma(df["Close"], length=length)
    last = _last_finite(sma)
    if last is None:
        return None
    close = _last_finite(df["Close"])
    if not close:
        return None
    return round((close - last) / last * 100, 3)


def compute_volume_ratio(df: pd.DataFrame) -> float | None:
    """Avg volume last 5 bars / avg volume last 20 bars."""
    if len(df) < MIN_BARS_VOL:
        return None
    avg_5 = df["Volume"].iloc[-5:].mean()
    avg_20 = df["Volume"].iloc[-20:].mean()
    if avg_20 == 0 or pd.isna(avg_5) or pd.isna(avg_20):
        return None
    return round(float(avg_5 / avg_20), 3)


def compute_intraday_range_pct(df: pd.DataFrame) -> float | None:
    """Mean of (High-Low)/Close*100 over last 5 trading days. Source for the
    CFD-Kurzfrist intraday-range guardrail (spec §6)."""
    if len(df) < MIN_BARS_INTRADAY:
        return None
    tail = df.iloc[-MIN_BARS_INTRADAY:]
    ratios = (tail["High"] - tail["Low"]) / tail["Close"] * 100
    val = ratios.mean()
    if pd.isna(val):
        return None
    return round(float(val), 3)


def compute_price_changes(df: pd.DataFrame) -> dict[str, float | None]:
    """Percentage changes vs. close N bars ago. Approximations:
       1d=1, 5d=5, 1m=21, 3m=63 trading days."""
    close = df["Close"]
    last = close.iloc[-1]

    def pct(offset: int) -> float | None:
        if len(close) <= offset:
            return None
        prev = close.iloc[-1 - offset]
        if prev == 0 or pd.isna(prev):
            return None
        return round(float((last - prev) / prev * 100), 3)

    return {
        "price_change_1d": pct(1),
        "price_change_5d": pct(5),
        "price_change_1m": pct(21),
        "price_change_3m": pct(63),
    }
```

- [ ] **Step 3.4: Run tests, expect green**

Run: `pytest tests/unit/test_data_collector.py -v`
Expected: 12 passed.

- [ ] **Step 3.5: Commit**

```bash
git add src/data_collector.py tests/unit/test_data_collector.py
git commit -m "Add data_collector indicator helpers with pandas-ta wrappers"
```

---

## Task 4: `data_collector.py` — `_process_ticker()` (per-asset pipeline)

Wires one ticker through provider → indicators → fundamentals → earnings into a `TickerData` dict, and persists `price_history` + `technical_indicators` via `db.py`. Skips on insufficient data, logging via `db.log_skipped_ticker(..., learnable=False)`. Returns `None` on skip.

**Files:**
- Modify: `src/data_collector.py` (append `_process_ticker` + helpers)
- Modify: `tests/unit/test_data_collector.py` (append `_process_ticker` tests)

- [ ] **Step 4.1: Write failing tests for `_process_ticker`**

Append to `tests/unit/test_data_collector.py`:

```python
from unittest.mock import MagicMock
from src.db import init_schema
from src.data_collector import _process_ticker, _classify_data_quality


def _good_provider(df: pd.DataFrame, fundamentals: dict | None = None) -> MagicMock:
    p = MagicMock()
    p.get_price_history.return_value = df
    p.get_fundamentals.return_value = fundamentals or {
        "pe_ratio": 28.4, "forward_pe": 26.2,
        "market_cap_b": 2800.0, "debt_equity": 1.45,
        "sector": "Technology",
        "analyst_upside": 8.5, "consensus": "buy",
    }
    return p


def _earnings_provider(days_to_next: int | None = 14, beat_pct: float | None = 4.2) -> MagicMock:
    p = MagicMock()
    p.get_earnings_calendar.return_value = {
        "days_to_next": days_to_next, "last_beat_pct": beat_pct,
    }
    return p


def test_process_ticker_returns_full_ticker_data(in_memory_db):
    init_schema(in_memory_db)
    df = _df_monotonic_up(250)
    out = _process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(),
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )
    assert out is not None
    assert out["ticker"] == "AAPL"
    assert out["price"] > 0
    assert out["rsi_14"] is not None
    assert out["macd_signal"] in {"bullish_cross", "bearish_cross", "neutral"}
    assert out["atr_pct"] is not None
    assert out["sector"] == "Technology"
    assert out["earnings_in_days"] == 14
    assert out["earnings_beat_pct"] == 4.2
    assert out["data_quality"] in {"high", "medium", "low"}
    assert out["intraday_range_pct"] is not None


def test_process_ticker_writes_price_history_and_indicators(in_memory_db):
    init_schema(in_memory_db)
    df = _df_monotonic_up(80)
    _process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(),
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )
    ph = in_memory_db.execute(
        "SELECT COUNT(*) AS c FROM price_history WHERE ticker=?", ("AAPL",)
    ).fetchone()["c"]
    ti = in_memory_db.execute(
        "SELECT COUNT(*) AS c FROM technical_indicators WHERE ticker=?", ("AAPL",)
    ).fetchone()["c"]
    assert ph == 80
    assert ti == 1


def test_process_ticker_skips_on_none_price_history(in_memory_db):
    init_schema(in_memory_db)
    bad = MagicMock()
    bad.get_price_history.return_value = None
    bad.get_fundamentals.return_value = {}

    out = _process_ticker(
        ticker="XYZ",
        price_provider=bad,
        earnings_provider=_earnings_provider(),
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )
    assert out is None
    row = in_memory_db.execute(
        "SELECT reason, learnable FROM skipped_tickers WHERE ticker=?", ("XYZ",)
    ).fetchone()
    assert row is not None
    assert row["learnable"] == 0


def test_process_ticker_skips_on_too_few_bars(in_memory_db):
    init_schema(in_memory_db)
    short_df = _df_monotonic_up(10)  # < MIN_BARS for indicators

    out = _process_ticker(
        ticker="NEW",
        price_provider=_good_provider(short_df),
        earnings_provider=_earnings_provider(),
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )
    assert out is None
    row = in_memory_db.execute(
        "SELECT * FROM skipped_tickers WHERE ticker=?", ("NEW",)
    ).fetchone()
    assert row is not None
    assert "bars" in row["reason"].lower() or "indicator" in row["reason"].lower()


def test_process_ticker_tolerates_missing_earnings(in_memory_db):
    init_schema(in_memory_db)
    df = _df_monotonic_up(80)
    out = _process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(days_to_next=None, beat_pct=None),
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )
    assert out is not None
    assert out["earnings_in_days"] is None
    assert out["earnings_beat_pct"] is None


def test_classify_data_quality_high_when_all_fields_present():
    td = {
        "rsi_14": 60, "atr_pct": 1.8, "above_sma200": 12.0,
        "pe_ratio": 25, "market_cap_b": 1000, "sector": "Technology",
    }
    assert _classify_data_quality(td) == "high"


def test_classify_data_quality_medium_when_some_missing():
    td = {
        "rsi_14": 60, "atr_pct": 1.8, "above_sma200": 12.0,
        "pe_ratio": None, "market_cap_b": 1000, "sector": "Technology",
    }
    assert _classify_data_quality(td) == "medium"


def test_classify_data_quality_low_when_indicator_missing():
    td = {
        "rsi_14": None, "atr_pct": None, "above_sma200": None,
        "pe_ratio": 25, "market_cap_b": 1000, "sector": "Technology",
    }
    assert _classify_data_quality(td) == "low"
```

- [ ] **Step 4.2: Run failing tests**

Run: `pytest tests/unit/test_data_collector.py -v`
Expected: ImportError on `_process_ticker`, `_classify_data_quality`.

- [ ] **Step 4.3: Implement `_process_ticker` and `_classify_data_quality`**

Append to `src/data_collector.py`:

```python
from src.providers.base import DataProvider
from src import db


def _classify_data_quality(td: dict) -> str:
    """high if all critical fields present, medium if peripheral fields missing,
    low if any required indicator is missing."""
    required = ("rsi_14", "atr_pct", "above_sma200")
    peripheral = ("pe_ratio", "market_cap_b", "sector")

    if any(td.get(k) is None for k in required):
        return "low"
    missing_peripheral = sum(1 for k in peripheral if td.get(k) is None)
    if missing_peripheral >= 1:
        return "medium"
    return "high"


def _persist_price_history(conn, ticker: str, df: pd.DataFrame) -> None:
    for ts, row in df.iterrows():
        db.upsert_price_history(
            conn, ticker=ticker, date=ts.strftime("%Y-%m-%d"),
            open_=float(row["Open"]), high=float(row["High"]),
            low=float(row["Low"]), close=float(row["Close"]),
            volume=int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
        )
    conn.commit()


def _persist_indicators(conn, ticker: str, date: str, td: dict) -> None:
    db.upsert_technical_indicators(conn, {
        "ticker": ticker, "date": date,
        "rsi_14": td.get("rsi_14"),
        "macd_signal": td.get("macd_signal"),
        "atr_pct": td.get("atr_pct"),
        "bb_position": td.get("bb_position"),
        "above_sma20": td.get("above_sma20"),
        "above_sma50": td.get("above_sma50"),
        "above_sma200": td.get("above_sma200"),
        "volume_ratio": td.get("volume_ratio"),
        "intraday_range_pct": td.get("intraday_range_pct"),
    })


def _process_ticker(
    ticker: str,
    price_provider: DataProvider,
    earnings_provider: DataProvider,
    conn,
    date: str,
    run_type: str,
) -> dict | None:
    """Run one ticker through the Phase-1 pipeline. Returns a TickerData dict on
    success; returns None and writes a skipped_tickers row on any failure."""
    try:
        df = price_provider.get_price_history(ticker, days=90)
    except Exception as e:  # provider already retries; this is final
        df = None
        log.warning(f"{ticker}: price_provider raised: {e}")

    if df is None or len(df) < MIN_BARS_RSI:
        rows = 0 if df is None else len(df)
        db.log_skipped_ticker(
            conn, ticker=ticker, date=date, run_type=run_type,
            reason=f"insufficient bars: {rows} < {MIN_BARS_RSI}",
            learnable=False,
        )
        return None

    # Indicators
    pc = compute_price_changes(df)
    td: dict[str, Any] = {
        "ticker": ticker,
        "price": float(df["Close"].iloc[-1]),
        **pc,
        "rsi_14": compute_rsi_14(df),
        "rsi_trend": compute_rsi_trend(df),
        "macd_signal": compute_macd_signal(df),
        "atr_pct": compute_atr_pct(df),
        "bb_position": compute_bb_position(df),
        "above_sma20":  compute_sma_distance_pct(df, 20),
        "above_sma50":  compute_sma_distance_pct(df, 50),
        "above_sma200": compute_sma_distance_pct(df, 200),
        "volume_ratio": compute_volume_ratio(df),
        "intraday_range_pct": compute_intraday_range_pct(df),
    }

    # Fundamentals (tolerate missing keys)
    try:
        fundamentals = price_provider.get_fundamentals(ticker) or {}
    except Exception as e:
        log.warning(f"{ticker}: fundamentals raised: {e}")
        fundamentals = {}
    td.update({
        "pe_ratio":              fundamentals.get("pe_ratio"),
        "forward_pe":            fundamentals.get("forward_pe"),
        "market_cap_b":          fundamentals.get("market_cap_b"),
        "debt_equity":           fundamentals.get("debt_equity"),
        "sector":                fundamentals.get("sector", "Unknown"),
        "analyst_target_upside": fundamentals.get("analyst_upside"),
        "analyst_consensus":     fundamentals.get("consensus"),
    })

    # Earnings (tolerate missing)
    try:
        earnings = earnings_provider.get_earnings_calendar(ticker) or {}
    except Exception as e:
        log.warning(f"{ticker}: earnings raised: {e}")
        earnings = {}
    td["earnings_in_days"] = earnings.get("days_to_next")
    td["earnings_beat_pct"] = earnings.get("last_beat_pct")

    td["data_quality"] = _classify_data_quality(td)

    if td["data_quality"] == "low":
        db.log_skipped_ticker(
            conn, ticker=ticker, date=date, run_type=run_type,
            reason="data_quality=low: critical indicators missing",
            learnable=False,
        )
        return None

    _persist_price_history(conn, ticker, df)
    _persist_indicators(conn, ticker, date, td)
    return td
```

- [ ] **Step 4.4: Run tests, expect green**

Run: `pytest tests/unit/test_data_collector.py -v`
Expected: 20 passed (12 indicator tests + 8 process tests).

- [ ] **Step 4.5: Commit**

```bash
git add src/data_collector.py tests/unit/test_data_collector.py
git commit -m "Add _process_ticker pipeline with skip-on-failure and data quality classifier"
```

---

## Task 5: `data_collector.py` — `collect()` orchestrator (loop with batch pause)

Loops the MVP universe (SP500 mega caps + commodities + crypto) calling `_process_ticker` for each. Sleeps `config.YFINANCE_BATCH_PAUSE` every 30 tickers (per spec §"Rate Limiting yfinance"). Returns a list of `TickerData` dicts, plus a count of skipped tickers.

**Files:**
- Modify: `src/data_collector.py` (append `collect`)
- Modify: `tests/unit/test_data_collector.py` (append `collect` tests)

- [ ] **Step 5.1: Write failing tests for `collect`**

Append to `tests/unit/test_data_collector.py`:

```python
from unittest.mock import patch
from src.data_collector import collect, BATCH_PAUSE_EVERY


def test_collect_returns_list_of_ticker_data(in_memory_db):
    init_schema(in_memory_db)
    df = _df_monotonic_up(80)
    pp = _good_provider(df)
    ep = _earnings_provider()

    with patch("src.data_collector.time.sleep") as sleep_mock:
        results, skipped = collect(
            tickers=["AAPL", "MSFT", "NVDA"],
            price_provider=pp,
            earnings_provider=ep,
            conn=in_memory_db,
            date="2026-05-19",
            run_type="pre_market",
        )

    assert len(results) == 3
    assert skipped == 0
    assert {r["ticker"] for r in results} == {"AAPL", "MSFT", "NVDA"}


def test_collect_skips_failed_tickers_but_continues(in_memory_db):
    init_schema(in_memory_db)
    df = _df_monotonic_up(80)

    pp = MagicMock()
    def history(ticker, days=90):
        return None if ticker == "BAD" else df
    pp.get_price_history.side_effect = history
    pp.get_fundamentals.return_value = {
        "pe_ratio": 25, "forward_pe": 24, "market_cap_b": 1000,
        "debt_equity": 1.0, "sector": "Technology",
        "analyst_upside": 5, "consensus": "buy",
    }
    ep = _earnings_provider()

    with patch("src.data_collector.time.sleep"):
        results, skipped = collect(
            tickers=["AAPL", "BAD", "MSFT"],
            price_provider=pp,
            earnings_provider=ep,
            conn=in_memory_db,
            date="2026-05-19",
            run_type="pre_market",
        )

    assert {r["ticker"] for r in results} == {"AAPL", "MSFT"}
    assert skipped == 1


def test_collect_pauses_between_batches(in_memory_db):
    init_schema(in_memory_db)
    df = _df_monotonic_up(80)
    pp = _good_provider(df)
    ep = _earnings_provider()

    tickers = [f"T{i}" for i in range(BATCH_PAUSE_EVERY + 1)]
    with patch("src.data_collector.time.sleep") as sleep_mock:
        collect(
            tickers=tickers,
            price_provider=pp,
            earnings_provider=ep,
            conn=in_memory_db,
            date="2026-05-19",
            run_type="pre_market",
        )

    # The batch pause is the longest sleep argument; assert it was called.
    batch_calls = [c for c in sleep_mock.call_args_list
                   if c.args and c.args[0] >= 5]
    assert len(batch_calls) >= 1
```

- [ ] **Step 5.2: Run failing tests**

Run: `pytest tests/unit/test_data_collector.py -v`
Expected: ImportError on `collect`, `BATCH_PAUSE_EVERY`.

- [ ] **Step 5.3: Implement `collect`**

Append to `src/data_collector.py`:

```python
import time
import config

BATCH_PAUSE_EVERY = 30  # spec §"Rate Limiting yfinance"


def collect(
    tickers: list[str],
    price_provider: DataProvider,
    earnings_provider: DataProvider,
    conn,
    date: str,
    run_type: str,
) -> tuple[list[dict], int]:
    """Run Phase 1 over the MVP universe. Returns (ticker_data_list, skipped_count).

    Tickers are processed sequentially. After every BATCH_PAUSE_EVERY tickers
    we sleep config.YFINANCE_BATCH_PAUSE seconds to avoid yfinance rate limits.
    """
    results: list[dict] = []
    skipped = 0
    for i, t in enumerate(tickers):
        td = _process_ticker(
            ticker=t,
            price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn,
            date=date,
            run_type=run_type,
        )
        if td is None:
            skipped += 1
        else:
            results.append(td)

        if (i + 1) % BATCH_PAUSE_EVERY == 0 and (i + 1) < len(tickers):
            log.info(
                f"Batch pause: processed {i + 1}/{len(tickers)} tickers, "
                f"sleeping {config.YFINANCE_BATCH_PAUSE}s"
            )
            time.sleep(config.YFINANCE_BATCH_PAUSE)

    log.info(f"Phase 1 done: {len(results)} ok, {skipped} skipped")
    return results, skipped
```

- [ ] **Step 5.4: Run tests, expect green**

Run: `pytest tests/unit/test_data_collector.py -v`
Expected: 23 passed.

- [ ] **Step 5.5: Commit**

```bash
git add src/data_collector.py tests/unit/test_data_collector.py
git commit -m "Add data_collector.collect orchestrator with batch pause"
```

---

## Task 6: `trend_analyzer.py` — Phase 0

One Sonnet call with the server-side `web_search` tool. Parses the JSON output, persists each trend via `db.save_trend_analysis`, and bills the call to a caller-provided `CostTracker`. Raises on parse failure or empty response (per spec §3 "Phase 0 fehlt → Run abbrechen + Alert-Mail").

**Files:**
- Create: `tests/fixtures/mock_trend_response.json`
- Create: `src/trend_analyzer.py`
- Create: `tests/unit/test_trend_analyzer.py`

- [ ] **Step 6.1: Create the mock response fixture**

`tests/fixtures/mock_trend_response.json`:

```json
{
  "trends": [
    {
      "name": "ai-capex-acceleration",
      "strength": 8,
      "duration_estimate": "1m+",
      "summary": "Hyperscalers raised guidance two quarters in a row (Reuters 2026-05-18).",
      "beneficiary_tickers": ["NVDA", "AVGO"],
      "negative_tickers": ["INTC"],
      "next_catalyst": "GTC keynote 2026-06-12"
    },
    {
      "name": "oil-supply-tightening",
      "strength": 6,
      "duration_estimate": "1w",
      "summary": "OPEC+ extended cuts; WTI +3% week (Bloomberg 2026-05-19).",
      "beneficiary_tickers": ["XOM", "CL=F"],
      "negative_tickers": ["DAL"],
      "next_catalyst": "OPEC meeting 2026-06-05"
    }
  ],
  "sector_rotation": {
    "into": ["XLK", "XLE"],
    "out_of": ["XLU"]
  },
  "trend_summary": "Risk-on continues, led by AI and energy. Volatility low (VIX 14)."
}
```

- [ ] **Step 6.2: Write failing tests**

`tests/unit/test_trend_analyzer.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.db import init_schema
from src.cost_tracker import CostTracker
from src.trend_analyzer import analyze_trends, TrendAnalyzerError


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mock_trend_response.json"


def _fake_claude_result(text: str, web_search_calls: int = 4) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 4000
    r.output_tokens = 3000
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = "claude-sonnet-4-6"
    r.web_search_calls = web_search_calls
    return r


def test_analyze_trends_parses_response_and_writes_db(in_memory_db):
    init_schema(in_memory_db)
    payload = FIXTURE_PATH.read_text()
    fake = _fake_claude_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.trend_analyzer.call_claude", return_value=fake):
        out = analyze_trends(
            conn=in_memory_db,
            date="2026-05-19",
            run_type="pre_market",
            cost_tracker=tracker,
        )

    assert len(out["trends"]) == 2
    assert out["sector_rotation"]["into"] == ["XLK", "XLE"]
    rows = in_memory_db.execute(
        "SELECT trend_name, strength FROM trend_analyses "
        "WHERE date='2026-05-19' ORDER BY strength DESC"
    ).fetchall()
    assert [r["trend_name"] for r in rows] == [
        "ai-capex-acceleration", "oil-supply-tightening"
    ]


def test_analyze_trends_bills_cost_tracker(in_memory_db):
    init_schema(in_memory_db)
    payload = FIXTURE_PATH.read_text()
    fake = _fake_claude_result(payload, web_search_calls=5)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.trend_analyzer.call_claude", return_value=fake):
        analyze_trends(
            conn=in_memory_db,
            date="2026-05-19",
            run_type="pre_market",
            cost_tracker=tracker,
        )

    assert tracker.web_search_calls == 5
    assert tracker.input_tokens == 4000
    assert tracker.output_tokens == 3000
    assert tracker.total_eur > 0


def test_analyze_trends_raises_on_invalid_json(in_memory_db):
    init_schema(in_memory_db)
    fake = _fake_claude_result("this is not json at all")
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.trend_analyzer.call_claude", return_value=fake):
        with pytest.raises(TrendAnalyzerError):
            analyze_trends(
                conn=in_memory_db, date="2026-05-19",
                run_type="pre_market", cost_tracker=tracker,
            )


def test_analyze_trends_raises_on_empty_trends(in_memory_db):
    init_schema(in_memory_db)
    fake = _fake_claude_result(json.dumps({
        "trends": [],
        "sector_rotation": {"into": [], "out_of": []},
        "trend_summary": "Web search returned nothing usable.",
    }))
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.trend_analyzer.call_claude", return_value=fake):
        with pytest.raises(TrendAnalyzerError, match="empty"):
            analyze_trends(
                conn=in_memory_db, date="2026-05-19",
                run_type="pre_market", cost_tracker=tracker,
            )


def test_analyze_trends_extracts_json_from_markdown_fences(in_memory_db):
    """Sonnet sometimes wraps JSON in ```json ... ```. Be tolerant."""
    init_schema(in_memory_db)
    payload = FIXTURE_PATH.read_text()
    fenced = f"```json\n{payload}\n```"
    fake = _fake_claude_result(fenced)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.trend_analyzer.call_claude", return_value=fake):
        out = analyze_trends(
            conn=in_memory_db, date="2026-05-19",
            run_type="pre_market", cost_tracker=tracker,
        )
    assert len(out["trends"]) == 2


def test_analyze_trends_uses_web_search_tool_in_request(in_memory_db):
    init_schema(in_memory_db)
    payload = FIXTURE_PATH.read_text()
    fake = _fake_claude_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.trend_analyzer.call_claude", return_value=fake) as mock_call:
        analyze_trends(
            conn=in_memory_db, date="2026-05-19",
            run_type="pre_market", cost_tracker=tracker,
        )

    kwargs = mock_call.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert kwargs["tools"] is not None
    assert any(t.get("name") == "web_search" for t in kwargs["tools"])
```

- [ ] **Step 6.3: Run failing tests**

Run: `pytest tests/unit/test_trend_analyzer.py -v`
Expected: ImportError on `analyze_trends`, `TrendAnalyzerError`.

- [ ] **Step 6.4: Implement `trend_analyzer.py`**

`src/trend_analyzer.py`:

```python
"""Phase 0: Megatrend identification.

Single Sonnet call with the server-side web_search tool. Output is a structured
JSON blob which we persist row-per-trend in the trend_analyses table. The caller
(main.py orchestrator) treats a TrendAnalyzerError as fatal for the run, per
spec §3 "Phase 0 fehlt → Run abbrechen + Alert-Mail".
"""
import json
import logging
import re
from pathlib import Path

from src import db
from src.cost_tracker import CostTracker
from src.utils import call_claude

log = logging.getLogger("shares_future.trend_analyzer")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "trend_analyzer_v1.txt").read_text()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
}


class TrendAnalyzerError(RuntimeError):
    """Phase 0 produced no usable output. Caller MUST abort the run."""


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Tolerate ```json ... ``` fences and leading/trailing prose."""
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Try to find the outermost {...} substring
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise TrendAnalyzerError(f"Could not parse JSON: {e}") from e


def analyze_trends(
    conn,
    date: str,
    run_type: str,
    cost_tracker: CostTracker,
) -> dict:
    """Returns the parsed dict {trends, sector_rotation, trend_summary}.

    Side effects:
      - One row in trend_analyses per trend (replace-on-conflict).
      - cost_tracker.add_call() called once for the Claude billing.

    Raises:
      TrendAnalyzerError if the response is unparseable or has zero trends.
      CostCapExceeded propagates from cost_tracker.add_call().
    """
    user_msg = (
        f"Today is {date}. Run type: {run_type}. "
        "Use web_search 3-5 times to gather evidence on dominant short-term "
        "market trends, then return the JSON object defined in your system prompt."
    )

    result = call_claude(
        model=MODEL,
        system=SYSTEM_PROMPT,
        user=user_msg,
        max_tokens=MAX_TOKENS,
        tools=[WEB_SEARCH_TOOL],
    )

    cost_tracker.add_call(
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cache_read_tokens=result.cache_read_tokens,
        cache_creation_tokens=result.cache_creation_tokens,
        web_search_calls=result.web_search_calls,
    )

    parsed = _extract_json(result.text)
    trends = parsed.get("trends") or []
    if not trends:
        raise TrendAnalyzerError(
            "Trend analyzer returned empty trends list — aborting run."
        )

    for t in trends:
        db.save_trend_analysis(conn, {
            "date": date, "run_type": run_type,
            "trend_name":          t.get("name"),
            "strength":            t.get("strength"),
            "duration_estimate":   t.get("duration_estimate"),
            "summary":             t.get("summary"),
            "beneficiary_tickers": t.get("beneficiary_tickers") or [],
            "negative_tickers":    t.get("negative_tickers") or [],
            "next_catalyst":       t.get("next_catalyst"),
        })

    log.info(
        f"Phase 0 done: {len(trends)} trends, "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return parsed
```

- [ ] **Step 6.5: Run tests, expect green**

Run: `pytest tests/unit/test_trend_analyzer.py -v`
Expected: 6 passed.

- [ ] **Step 6.6: Commit**

```bash
git add src/trend_analyzer.py tests/unit/test_trend_analyzer.py tests/fixtures/mock_trend_response.json
git commit -m "Add trend_analyzer: Phase 0 Sonnet+web_search call with JSON parsing and DB writes"
```

---

## Task 7: `quick_filter.py` — Phase 2 batch scoring

One Haiku batch call. Takes the list of `TickerData` dicts and the trend context, returns a list of per-ticker scoring dicts. No web search. No DB writes — the output is consumed in-memory by Phase 3 (deep analysis) in a later plan. Single Claude call per batch keeps quick-filter cost negligible (~0.01 EUR per 20-ticker batch with caching).

**Files:**
- Create: `tests/fixtures/mock_quick_filter_response.json`
- Create: `src/quick_filter.py`
- Create: `tests/unit/test_quick_filter.py`

- [ ] **Step 7.1: Create the mock response fixture**

`tests/fixtures/mock_quick_filter_response.json`:

```json
{
  "results": [
    {
      "ticker": "AAPL",
      "long_score": 7.5,
      "short_score": 2.0,
      "confidence": "high",
      "evidence": ["RSI 58 rising", "above SMA200 +12.8%", "earnings beat 4.2%"],
      "exclude": false
    },
    {
      "ticker": "MSFT",
      "long_score": 6.8,
      "short_score": 3.2,
      "confidence": "medium",
      "evidence": ["MACD bullish_cross", "volume_ratio 1.15"],
      "exclude": false
    },
    {
      "ticker": "BADCO",
      "long_score": 0.0,
      "short_score": 0.0,
      "confidence": "low",
      "evidence": ["data_quality low"],
      "exclude": true
    }
  ]
}
```

- [ ] **Step 7.2: Write failing tests**

`tests/unit/test_quick_filter.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.cost_tracker import CostTracker
from src.quick_filter import quick_filter_batch, QuickFilterError


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mock_quick_filter_response.json"


def _fake_haiku_result(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 6000
    r.output_tokens = 2000
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = "claude-haiku-4-5"
    r.web_search_calls = 0
    return r


def _td(ticker: str, **overrides) -> dict:
    base = {
        "ticker": ticker, "price": 100.0,
        "rsi_14": 55.0, "macd_signal": "neutral", "atr_pct": 1.5,
        "above_sma200": 8.0, "volume_ratio": 1.1,
        "pe_ratio": 25.0, "market_cap_b": 200.0, "sector": "Technology",
        "earnings_in_days": 14, "earnings_beat_pct": 3.0,
        "data_quality": "high",
        "intraday_range_pct": 1.5,
    }
    base.update(overrides)
    return base


def _trend_context() -> dict:
    return {
        "trends": [{"name": "ai-capex-acceleration", "strength": 8,
                    "beneficiary_tickers": ["AAPL"], "negative_tickers": []}],
        "sector_rotation": {"into": ["XLK"], "out_of": ["XLU"]},
        "trend_summary": "Risk-on, AI leading."
    }


def test_quick_filter_returns_one_entry_per_ticker():
    payload = FIXTURE_PATH.read_text()
    fake = _fake_haiku_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("AAPL"), _td("MSFT"), _td("BADCO", data_quality="low")]

    with patch("src.quick_filter.call_claude", return_value=fake):
        out = quick_filter_batch(
            batch=batch,
            trend_context=_trend_context(),
            cost_tracker=tracker,
        )

    assert len(out) == 3
    assert out[0]["ticker"] == "AAPL"
    assert out[0]["long_score"] == 7.5
    assert out[2]["exclude"] is True


def test_quick_filter_uses_haiku_and_no_web_search():
    fake = _fake_haiku_result(FIXTURE_PATH.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.quick_filter.call_claude", return_value=fake) as mock_call:
        quick_filter_batch(
            batch=[_td("AAPL"), _td("MSFT"), _td("BADCO")],
            trend_context=_trend_context(),
            cost_tracker=tracker,
        )

    kwargs = mock_call.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5"
    assert kwargs.get("tools") in (None, [])


def test_quick_filter_bills_cost_tracker():
    fake = _fake_haiku_result(FIXTURE_PATH.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.quick_filter.call_claude", return_value=fake):
        quick_filter_batch(
            batch=[_td("AAPL"), _td("MSFT"), _td("BADCO")],
            trend_context=_trend_context(),
            cost_tracker=tracker,
        )

    assert tracker.input_tokens == 6000
    assert tracker.output_tokens == 2000
    assert tracker.total_eur > 0


def test_quick_filter_raises_on_invalid_json():
    fake = _fake_haiku_result("not json")
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.quick_filter.call_claude", return_value=fake):
        with pytest.raises(QuickFilterError):
            quick_filter_batch(
                batch=[_td("AAPL")],
                trend_context=_trend_context(),
                cost_tracker=tracker,
            )


def test_quick_filter_raises_on_missing_ticker_in_response():
    """If a ticker from the batch is missing from results, that's a prompt failure."""
    payload = json.dumps({"results": [
        {"ticker": "AAPL", "long_score": 7.0, "short_score": 2.0,
         "confidence": "medium", "evidence": ["x"], "exclude": False},
    ]})
    fake = _fake_haiku_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.quick_filter.call_claude", return_value=fake):
        with pytest.raises(QuickFilterError, match="missing"):
            quick_filter_batch(
                batch=[_td("AAPL"), _td("MSFT")],
                trend_context=_trend_context(),
                cost_tracker=tracker,
            )


def test_quick_filter_empty_batch_returns_empty_list():
    tracker = CostTracker(hard_cap_eur=10.0)
    out = quick_filter_batch(
        batch=[],
        trend_context=_trend_context(),
        cost_tracker=tracker,
    )
    assert out == []
    assert tracker.input_tokens == 0


def test_quick_filter_user_message_includes_tickers_and_trends():
    fake = _fake_haiku_result(FIXTURE_PATH.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.quick_filter.call_claude", return_value=fake) as mock_call:
        quick_filter_batch(
            batch=[_td("AAPL"), _td("MSFT"), _td("BADCO")],
            trend_context=_trend_context(),
            cost_tracker=tracker,
        )

    user_msg = mock_call.call_args.kwargs["user"]
    assert "AAPL" in user_msg
    assert "MSFT" in user_msg
    assert "ai-capex-acceleration" in user_msg
```

- [ ] **Step 7.3: Run failing tests**

Run: `pytest tests/unit/test_quick_filter.py -v`
Expected: ImportError on `quick_filter_batch`, `QuickFilterError`.

- [ ] **Step 7.4: Implement `quick_filter.py`**

`src/quick_filter.py`:

```python
"""Phase 2: Haiku batch quick-filter.

Single Claude Haiku call per batch (no web search). Returns one scoring dict per
input ticker. No DB writes — caller consumes the list in-memory and feeds it to
Phase 3 (deep analysis) in a later plan.
"""
import json
import logging
import re
from pathlib import Path

from src.cost_tracker import CostTracker
from src.utils import call_claude

log = logging.getLogger("shares_future.quick_filter")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "quick_filter_v1.txt").read_text()

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 4096


class QuickFilterError(RuntimeError):
    """Quick-filter output unparseable or incomplete."""


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def _extract_json(text: str) -> dict:
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise QuickFilterError(f"Could not parse JSON: {e}") from e


def _format_batch_for_prompt(batch: list[dict], trend_context: dict) -> str:
    """Compose a deterministic user message containing one snapshot per ticker."""
    parts = ["TREND CONTEXT:", json.dumps(trend_context, ensure_ascii=False)]
    parts.append("\nBATCH (one ticker per line, JSON):")
    for td in batch:
        parts.append(json.dumps(td, ensure_ascii=False))
    parts.append(
        "\nReturn the JSON object defined in your system prompt with one entry "
        "per ticker above, in the same order."
    )
    return "\n".join(parts)


def quick_filter_batch(
    batch: list[dict],
    trend_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """Score a batch of tickers in a single Haiku call.

    Returns a list of dicts, each: {ticker, long_score, short_score, confidence,
    evidence, exclude}. Output preserves input ordering by ticker.

    Raises:
      QuickFilterError on unparseable JSON or missing tickers in response.
      CostCapExceeded propagates from cost_tracker.add_call().
    """
    if not batch:
        return []

    user_msg = _format_batch_for_prompt(batch, trend_context)

    result = call_claude(
        model=MODEL,
        system=SYSTEM_PROMPT,
        user=user_msg,
        max_tokens=MAX_TOKENS,
    )

    cost_tracker.add_call(
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cache_read_tokens=result.cache_read_tokens,
        cache_creation_tokens=result.cache_creation_tokens,
        web_search_calls=result.web_search_calls,
    )

    parsed = _extract_json(result.text)
    results = parsed.get("results")
    if not isinstance(results, list):
        raise QuickFilterError("Response missing 'results' list")

    by_ticker = {r.get("ticker"): r for r in results}
    expected = {td["ticker"] for td in batch}
    missing = expected - set(by_ticker.keys())
    if missing:
        raise QuickFilterError(
            f"Quick filter response missing tickers: {sorted(missing)}"
        )

    ordered = [by_ticker[td["ticker"]] for td in batch]
    log.info(
        f"Phase 2 done: {len(ordered)} scored, "
        f"{sum(1 for r in ordered if r.get('exclude'))} excluded, "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return ordered
```

- [ ] **Step 7.5: Run tests, expect green**

Run: `pytest tests/unit/test_quick_filter.py -v`
Expected: 7 passed.

- [ ] **Step 7.6: Commit**

```bash
git add src/quick_filter.py tests/unit/test_quick_filter.py tests/fixtures/mock_quick_filter_response.json
git commit -m "Add quick_filter: Phase 2 Haiku batch scoring with order-preserving output"
```

---

## Task 8: Final check — all tests green + coverage ≥ 80%

- [ ] **Step 8.1: Run the full unit-test suite**

Run: `pytest tests/unit/ -v`
Expected: All Plan 1 tests (39) plus the new Plan 2 tests pass — roughly 80+ tests total.

- [ ] **Step 8.2: Check coverage of new modules**

Run: `pytest tests/unit/ --cov=src --cov-report=term-missing --cov-fail-under=80`
Expected: Each of `src/data_collector.py`, `src/trend_analyzer.py`, `src/quick_filter.py`, plus the modified `src/utils.py` and `src/db.py`, is ≥ 80%. The overall project coverage stays ≥ 80%.

- [ ] **Step 8.3: If coverage gaps remain, add targeted tests**

For any module under 80%, read the `--cov-report=term-missing` line list and add focused tests for the uncovered branches. Common gaps to anticipate:
- `data_collector.compute_*` `None`-returns on short series — covered by Task 3 tests.
- `_process_ticker` exception branches in fundamentals/earnings fetch — add a test where `price_provider.get_fundamentals` raises.
- `trend_analyzer._extract_json` substring-fallback branch — add a test with prose surrounding the JSON.

Do NOT lower the threshold.

- [ ] **Step 8.4: Final commit if coverage tests added**

```bash
git add tests/unit/
git commit -m "Add coverage tests for collector/trend/quick-filter modules"
```

---

## Self-Review Notes

**Spec coverage** (against `docs/superpowers/specs/2026-05-19-trading-harry-mvp-design.md`):

| Spec section | Task | Status |
|---|---|---|
| §3 Phase 0 trend_analyzer with web_search, DB-write trend_analyses | Task 6 | ✅ |
| §3 Phase 0 fehlt → Run abbrechen (TrendAnalyzerError) | Task 6 | ✅ |
| §3 Phase 1 data_collector loops 27 assets, computes RSI/MACD/ATR/BB/SMA/Volume | Task 3-5 | ✅ |
| §3 Phase 1 DB-Write price_history (UPSERT), technical_indicators | Task 4 | ✅ |
| §3 Phase 1 Asset-Daten fehlen → skip mit learnable=False | Task 4 | ✅ |
| §3 Phase 2 quick_filter Haiku, 1 Batch von 20, kein Web-Search | Task 7 | ✅ |
| §3 Phase 2 Output {long_score, short_score, confidence, evidence, exclude} | Task 7 | ✅ |
| §3 Phase 2 learning_context leer im MVP | Task 7 | ✅ |
| §4 Prompt caching auf System-Prompt + Trend-Kontext | Task 1 (utils) | ✅ |
| §4 web_search billing in CostTracker | Task 1 | ✅ |
| §4 cost_tracker.add_call billed per Claude call | Tasks 6, 7 | ✅ |
| §5 technical_indicators.intraday_range_pct ALTER | Task 1 | ✅ |
| §5 CFD-Kurzfrist: intraday_range_pct computed by data_collector | Task 3 | ✅ |
| §6 CFD-Kurzfrist: intraday_range_pct als (High-Low)/Close*100, avg 5 Tage | Task 3 | ✅ |
| §"Rate Limiting yfinance": 0.8s/Ticker, 12s alle 30 Ticker | Task 5 | ✅ |
| §10 row 8 data_collector with test_data_collector | Tasks 3-5 | ✅ |
| §10 row 9 trend_analyzer with test_trend_analyzer | Task 6 | ✅ |
| §10 row 10 quick_filter with test_quick_filter | Task 7 | ✅ |

**Items deliberately deferred (carry-overs are tracked in memory `[[project-carryover-issues]]`):**

| Spec section | Why deferred |
|---|---|
| §6 Guardrail `hold_days_recommended > 3` | Field is filled by Phase 3 deep_analysis (later plan). Guardrail addition belongs with deep_analysis. |
| §6 Guardrail `intraday_range_pct < 1.0` (predictions field) | Same — guardrail check fires after deep_analysis writes its predictions row. The column on `predictions` will be added then. |
| Phase 3 deep_analysis, Phase 3b commodities_crypto, Phase 4a portfolio_check, Phase 4 ranking, Phase 5 email_sender, evaluator, main.py | All explicitly out of scope for this plan; covered in subsequent Sprint 1 plans. |
| Carry-over issues 1-5 from Plan 1 | None of the touched files in this plan are `yfinance_provider.py`, `cost_tracker.py` core math, or `conftest.in_memory_db`. Plan scope discipline → defer. |

**Placeholder scan:** No TBDs, "implement later", "similar to Task N", or empty test bodies. All code blocks include the actual content the implementer needs to type.

**Type consistency:**
- `TickerData` is a `dict` everywhere (mirrors `conftest.sample_ticker_data` keys); never elevated to a dataclass — keeps DB serialisation simple.
- `ClaudeResult` field `web_search_calls` matches the parameter name `web_search_calls` in `CostTracker.add_call` and in `cost_tracker` accumulator state.
- `CostTracker` is always **passed in** to `analyze_trends` and `quick_filter_batch`, never created inside (orchestrator-owned).
- `analyze_trends(...) → dict` and `quick_filter_batch(...) → list[dict]` — matched in tests and module signatures.
- `_process_ticker(...) → dict | None`; `collect(...) → tuple[list[dict], int]` — matched in tests.
- Exception classes `TrendAnalyzerError` and `QuickFilterError` both extend `RuntimeError`, both raised on parse failure.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-19-sprint1-plan2-collector-trend-quickfilter.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
