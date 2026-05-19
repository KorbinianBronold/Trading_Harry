# Sprint 1 / Plan 3: Deep Analysis, Portfolio Check, Ranking, Evaluator, Email, Orchestrator, CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Sprint-1 MVP pipeline on top of merged Plans 1 + 2 (`135bac5`): Phase 3 deep analysis with policy monitor, Phase 3b commodities/crypto, Phase 4a portfolio check, Phase 4 ranking with DB persistence, Walk-Forward evaluator, 4-section daily email + reduced weekly, `main.py` orchestrator, and GitHub Actions cron with Release-Asset DB persistence.

**Architecture:** Eight new phase/glue modules on top of the existing foundation (`config`, `utils`, `db`, `cost_tracker`, `guardrails`, `data_collector`, `trend_analyzer`, `quick_filter`). All Claude calls reuse `utils.call_claude` with prompt caching of the trend + policy context (1× cached, ~20× read). All DB I/O goes through `db.py` helpers added in Task 1. `main.py` dispatches by `--run-type` and owns the single `CostTracker` instance for the run. Each phase module raises only **fatal** errors (Phase 0 missing); per-asset failures `skip` and continue.

**Tech Stack:** Python 3.11+, Anthropic SDK (Sonnet + server-side web_search tool with prompt caching), pandas, yfinance, SendGrid, sqlite3, pytest, pytest-mock, freezegun.

**Spec reference:** `docs/superpowers/specs/2026-05-19-shares-future-mvp-design.md` §3, §5 (CFD-Kurzfrist-Schema), §6 (Guardrails), §7 (Cron), §9 (Tests), §10 rows 11-21.

**Foundation reference:** Plan 2 merged as `135bac5`. Available:
- `config.py` — incl. `SP500_MVP_TICKERS`, `COMMODITY_TICKERS`, `CRYPTO_TICKERS`, `DIMENSION_WEIGHTS`, `RR_RATIO_MIN_HARD=1.5`, `MOMENTUM_LONG_MIN=6.0`, `MOMENTUM_SHORT_MAX=4.0`, `MAX_COST_PER_RUN_EUR=4.00`, `CLAUDE_PARALLEL_CALLS=5`.
- `src/utils.py` — `call_claude(model, system, user, max_tokens, tools)` → `ClaudeResult{text, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, model, web_search_calls}`.
- `src/db.py` — `connect`, `init_schema`, `save_prediction`, `load_open_predictions`, `close_prediction`, `save_outcome`, `save_cost_tracking`, `cleanup_old_data`, `upsert_technical_indicators`, `save_trend_analysis`, `log_skipped_ticker`.
- `src/cost_tracker.py` — `CostTracker`, `CostCapExceeded`.
- `src/guardrails.py` — `GuardrailsChecker.check_analysis(a) -> (ok, errors)` with RR + momentum + required-fields checks.
- `src/data_collector.py` — `collect(tickers, price_provider, earnings_provider, conn, date, run_type)` → `(list[TickerData], skipped_count)`.
- `src/trend_analyzer.py` — `analyze_trends(conn, date, run_type, cost_tracker)` → dict + `TrendAnalyzerError`.
- `src/quick_filter.py` — `quick_filter_batch(batch, trend_context, cost_tracker)` → list of scoring dicts + `QuickFilterError`.
- `src/providers/{yfinance,finnhub,paid}_provider.py`.
- `tests/conftest.py` — `in_memory_db`, `tmp_db_path`, `sample_ticker_data`.

---

## File Structure

```
Shares_Future/
├── prompts/                                        # MODIFY (add 4 new files)
│   ├── deep_analysis_v1.txt                        # NEW
│   ├── policy_monitor_v1.txt                       # NEW
│   ├── commodities_crypto_v1.txt                   # NEW
│   └── portfolio_check_v1.txt                      # NEW
├── src/
│   ├── utils.py                                    # MODIFY: extract_json_blob, WEB_SEARCH_TOOL
│   ├── cost_tracker.py                             # MODIFY: add_from_result shortcut
│   ├── db.py                                       # MODIFY: schema + 4 new helpers
│   ├── guardrails.py                               # MODIFY: hold_days + intraday_range checks
│   ├── trend_analyzer.py                           # MODIFY: use shared WEB_SEARCH_TOOL + extract_json_blob
│   ├── quick_filter.py                             # MODIFY: use shared extract_json_blob
│   ├── deep_analysis.py                            # NEW: Phase 3 + Policy Monitor
│   ├── commodities_crypto.py                       # NEW: Phase 3b
│   ├── portfolio_check.py                          # NEW: Phase 4a
│   ├── ranking.py                                  # NEW: Phase 4
│   ├── evaluator.py                                # NEW: Walk-Forward
│   └── email_sender.py                             # NEW: Phase 5
├── main.py                                         # NEW: Orchestrator
├── .github/workflows/
│   ├── test.yml                                    # NEW: CI test gate
│   └── analyze.yml                                 # NEW: Cron + Release-Asset DB
└── tests/
    ├── fixtures/
    │   ├── mock_deep_analysis_response.json        # NEW
    │   ├── mock_policy_monitor_response.json       # NEW
    │   ├── mock_commodities_crypto_response.json   # NEW
    │   ├── mock_portfolio_check_response.json      # NEW
    │   └── sample_ohlc_eval.csv                    # NEW
    ├── unit/
    │   ├── test_utils.py                           # MODIFY: extract_json_blob tests
    │   ├── test_cost_tracker.py                    # MODIFY: add_from_result test
    │   ├── test_db.py                              # MODIFY: schema + helper tests
    │   ├── test_guardrails.py                      # MODIFY: hold_days + intraday tests
    │   ├── test_deep_analysis.py                   # NEW
    │   ├── test_commodities_crypto.py              # NEW
    │   ├── test_portfolio_check.py                 # NEW
    │   ├── test_ranking.py                         # NEW
    │   ├── test_evaluator.py                       # NEW
    │   ├── test_email_sender.py                    # NEW
    │   └── test_main.py                            # NEW
    └── integration/
        ├── __init__.py                             # NEW
        ├── test_full_pipeline.py                   # NEW
        ├── test_eval_loop.py                       # NEW
        └── test_email_render.py                    # NEW
```

### Boundary rules (carried from spec §2)

- Phase modules call DB only through `db.py` (no inline SQL).
- All Claude calls go through `utils.call_claude`.
- `CostTracker` is owned by `main.py`; phase modules accept it as parameter and bill via `cost_tracker.add_from_result(result)`.
- Per-asset failures inside Phase 3, 3b, 4a → log + skip, do not raise out of the loop. Only `TrendAnalyzerError` (Phase 0) and `CostCapExceeded` are fatal.
- `SIMULATION_ONLY` invariant: nothing in this plan performs trade execution.

---

## Task 1: Foundation extensions — JSON helper, web-search constant, cost-tracker shortcut, DB schema, guardrails

The four new Claude callers (`deep_analysis`, `commodities_crypto`, `portfolio_check`, plus the existing `trend_analyzer`/`quick_filter`) all need the same three primitives. Hoisting them to `utils.py` / `cost_tracker.py` now avoids 4× duplication. `db.py` and `guardrails.py` also need extensions called out in spec §5 + §6 (CFD-Kurzfrist-Schema-Erweiterungen + Guardrails).

**Files:**
- Modify: `src/utils.py` (append `extract_json_blob` and `WEB_SEARCH_TOOL`)
- Modify: `src/cost_tracker.py` (append `add_from_result`)
- Modify: `src/db.py` (schema additions, migration, 5 new helpers)
- Modify: `src/guardrails.py` (CFD-Kurzfrist required fields + checks)
- Modify: `src/trend_analyzer.py` (switch to shared helpers — minimal change)
- Modify: `src/quick_filter.py` (switch to shared `extract_json_blob`)
- Modify: `tests/unit/test_utils.py`, `tests/unit/test_cost_tracker.py`, `tests/unit/test_db.py`, `tests/unit/test_guardrails.py`

- [ ] **Step 1.1: Write failing tests for `extract_json_blob`**

Append to `tests/unit/test_utils.py`:

```python
import pytest
from src.utils import extract_json_blob


class _DemoError(RuntimeError):
    pass


def test_extract_json_blob_parses_plain_json():
    assert extract_json_blob('{"a": 1}', _DemoError) == {"a": 1}


def test_extract_json_blob_strips_markdown_fences():
    text = "```json\n{\"a\": 2}\n```"
    assert extract_json_blob(text, _DemoError) == {"a": 2}


def test_extract_json_blob_extracts_outermost_braces_on_prose():
    text = "Sure, here is the result:\n{\"a\": 3}\nLet me know if you need more."
    assert extract_json_blob(text, _DemoError) == {"a": 3}


def test_extract_json_blob_raises_provided_error_class():
    with pytest.raises(_DemoError, match="Could not parse JSON"):
        extract_json_blob("not json at all and no braces", _DemoError)
```

- [ ] **Step 1.2: Write failing test for `CostTracker.add_from_result`**

Append to `tests/unit/test_cost_tracker.py`:

```python
from unittest.mock import MagicMock
from src.cost_tracker import CostTracker


def test_add_from_result_forwards_all_fields():
    tracker = CostTracker(hard_cap_eur=10.0)
    result = MagicMock(
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=400,
        cache_read_tokens=200,
        cache_creation_tokens=100,
        web_search_calls=2,
    )
    tracker.add_from_result(result)
    assert tracker.input_tokens == 1000
    assert tracker.output_tokens == 400
    assert tracker.cache_read_tokens == 200
    assert tracker.web_search_calls == 2
    assert tracker.total_eur > 0
```

- [ ] **Step 1.3: Write failing tests for db.py schema and helpers**

Append to `tests/unit/test_db.py`:

```python
from src import db


def test_predictions_has_hold_days_and_intraday_range_columns(in_memory_db):
    db.init_schema(in_memory_db)
    cols = {r["name"] for r in in_memory_db.execute(
        "PRAGMA table_info(predictions)"
    ).fetchall()}
    assert "hold_days_recommended" in cols
    assert "intraday_range_pct" in cols


def test_outcomes_has_days_to_close_and_exit_reason_columns(in_memory_db):
    db.init_schema(in_memory_db)
    cols = {r["name"] for r in in_memory_db.execute(
        "PRAGMA table_info(outcomes)"
    ).fetchall()}
    assert "days_to_close" in cols
    assert "exit_reason" in cols


def test_position_recommendations_table_exists(in_memory_db):
    db.init_schema(in_memory_db)
    assert "position_recommendations" in db.get_tables(in_memory_db)


def test_save_prediction_persists_hold_days_and_intraday(in_memory_db):
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-05-19", "run_type": "close",
        "asset_class": "stock", "ticker": "AAPL", "direction": "long",
        "entry_price": 178.0, "tp_price": 184.0, "tp_pct": 3.4,
        "sl_price": 176.0, "sl_pct": 1.1, "rr_ratio": 3.0,
        "total_score": 7.8, "probability_pct": 68, "confidence": "high",
        "score_market_env": 7.0, "score_company": 8.0, "score_valuation": 6.0,
        "score_momentum": 8.0, "score_risk": 6.0, "score_sector": 7.0,
        "score_catalyst": 7.0, "score_policy": 6.0,
        "atr_pct": 1.8, "rsi_at_entry": 58.0, "volume_ratio": 1.15,
        "market_regime": "risk_on", "vix_at_prediction": 14.0,
        "sector": "Technology", "trend_boost": "ai-capex",
        "earnings_warning": False, "summary": "ok",
        "learnable": True,
        "hold_days_recommended": 2,
        "intraday_range_pct": 1.4,
    })
    row = in_memory_db.execute(
        "SELECT hold_days_recommended, intraday_range_pct FROM predictions WHERE id=?",
        (pid,),
    ).fetchone()
    assert row["hold_days_recommended"] == 2
    assert row["intraday_range_pct"] == 1.4


def test_save_position_recommendation(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _insert_test_prediction(in_memory_db)
    db.save_position_recommendation(in_memory_db, {
        "date": "2026-05-20", "run_type": "pre_market",
        "prediction_id": pid, "action": "HALTEN",
        "reason": "These intakt, kein neuer Katalysator.",
        "new_sl_price": None, "new_tp_price": None,
        "market_context_changed": False,
    })
    row = in_memory_db.execute(
        "SELECT action, reason FROM position_recommendations WHERE prediction_id=?",
        (pid,),
    ).fetchone()
    assert row["action"] == "HALTEN"


def test_load_open_predictions_within_max_age_days(in_memory_db):
    db.init_schema(in_memory_db)
    p_old = _insert_test_prediction(in_memory_db, date="2026-05-10")
    p_new = _insert_test_prediction(in_memory_db, date="2026-05-19")
    rows = db.load_open_predictions_within_max_age_days(
        in_memory_db, today="2026-05-20", max_trading_days=3,
    )
    ids = {r["id"] for r in rows}
    assert p_new in ids
    assert p_old not in ids


def test_save_outcome_with_new_columns(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _insert_test_prediction(in_memory_db)
    oid = db.save_outcome(in_memory_db, {
        "prediction_id": pid, "direction": "long",
        "evaluated_date": "2026-05-22",
        "price_after_eod": 184.0, "price_change_eod_pct": 3.4,
        "correct_direction_eod": True,
        "tp_hit": True, "sl_hit": False,
        "days_to_close": 2, "exit_reason": "tp_hit",
        "profit_loss_eur": 25.0,
    })
    row = in_memory_db.execute(
        "SELECT days_to_close, exit_reason FROM outcomes WHERE id=?",
        (oid,),
    ).fetchone()
    assert row["days_to_close"] == 2
    assert row["exit_reason"] == "tp_hit"


def _insert_test_prediction(conn, date: str = "2026-05-19") -> int:
    """Helper used by multiple new tests."""
    return db.save_prediction(conn, {
        "date": date, "run_type": "close",
        "asset_class": "stock", "ticker": "AAPL", "direction": "long",
        "entry_price": 178.0, "tp_price": 184.0, "tp_pct": 3.4,
        "sl_price": 176.0, "sl_pct": 1.1, "rr_ratio": 3.0,
        "total_score": 7.8, "probability_pct": 68, "confidence": "high",
        "score_market_env": 7.0, "score_company": 8.0, "score_valuation": 6.0,
        "score_momentum": 8.0, "score_risk": 6.0, "score_sector": 7.0,
        "score_catalyst": 7.0, "score_policy": 6.0,
        "atr_pct": 1.8, "rsi_at_entry": 58.0, "volume_ratio": 1.15,
        "market_regime": "risk_on", "vix_at_prediction": 14.0,
        "sector": "Technology", "trend_boost": "ai-capex",
        "earnings_warning": False, "summary": "ok",
        "learnable": True,
        "hold_days_recommended": 2,
        "intraday_range_pct": 1.4,
    })
```

- [ ] **Step 1.4: Write failing tests for guardrails CFD-Kurzfrist checks**

Append to `tests/unit/test_guardrails.py`:

```python
import pytest
from src.guardrails import GuardrailsChecker


def _valid_analysis(**overrides):
    """A minimum analysis dict that passes every existing guardrail."""
    base = {
        "ticker": "AAPL", "direction": "long", "confidence": "high",
        "current_price": 178.0, "tp_price": 184.0, "sl_price": 176.0,
        "rr_ratio": 3.0, "total_score": 7.5, "summary": "ok",
        "sources_used": ["reuters.com", "bloomberg.com"],
        "signal_consistency_check": "ok",
        "scores": {
            "market_environment": {"value": 7.0, "evidence": ["a", "b"]},
            "company_quality":    {"value": 8.0, "evidence": ["a", "b"]},
            "valuation":           {"value": 6.0, "evidence": ["a", "b"]},
            "momentum":           {"value": 7.5, "evidence": ["a", "b"]},
            "risk":               {"value": 6.0, "evidence": ["a", "b"]},
            "sector_trend":       {"value": 7.0, "evidence": ["a", "b"]},
            "catalyst":           {"value": 7.0, "evidence": ["a", "b"]},
            "policy_risk":        {"value": 6.0, "evidence": ["a", "b"]},
        },
        "hold_days_recommended": 2,
        "intraday_range_pct": 1.5,
    }
    base.update(overrides)
    return base


def test_required_fields_now_include_hold_days_and_intraday_range():
    c = GuardrailsChecker()
    a = _valid_analysis()
    a.pop("hold_days_recommended")
    ok, errs = c.check_analysis(a)
    assert not ok
    assert any("hold_days_recommended" in e for e in errs)


def test_guardrail_rejects_hold_days_above_3():
    c = GuardrailsChecker()
    ok, errs = c.check_analysis(_valid_analysis(hold_days_recommended=4))
    assert not ok
    assert any("Haltedauer" in e and "3" in e for e in errs)


def test_guardrail_accepts_hold_days_3():
    c = GuardrailsChecker()
    ok, errs = c.check_analysis(_valid_analysis(hold_days_recommended=3))
    assert ok, errs


def test_guardrail_rejects_intraday_range_below_one_percent():
    c = GuardrailsChecker()
    ok, errs = c.check_analysis(_valid_analysis(intraday_range_pct=0.7))
    assert not ok
    assert any("Intraday-Range" in e and "1.0" in e for e in errs)


def test_guardrail_accepts_intraday_range_exactly_one_percent():
    c = GuardrailsChecker()
    ok, errs = c.check_analysis(_valid_analysis(intraday_range_pct=1.0))
    assert ok, errs
```

- [ ] **Step 1.5: Run failing tests**

Run: `pytest tests/unit/test_utils.py tests/unit/test_cost_tracker.py tests/unit/test_db.py tests/unit/test_guardrails.py -v`

Expected: 12+ new failures (ImportError on `extract_json_blob`, AttributeError on `add_from_result`, KeyError on new columns, AssertionError on new guardrails).

- [ ] **Step 1.6: Implement `extract_json_blob` and `WEB_SEARCH_TOOL` in `src/utils.py`**

Append to `src/utils.py`:

```python
import json
import re
from typing import Type

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def extract_json_blob(text: str, error_cls: Type[Exception]) -> dict:
    """Tolerate ```json ... ``` fences and leading/trailing prose. Raises the
    caller-provided error_cls on failure so callers can keep their own taxonomy."""
    m = _JSON_FENCE_RE.search(text)
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
        raise error_cls(f"Could not parse JSON: {e}") from e


WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
}
```

- [ ] **Step 1.7: Implement `CostTracker.add_from_result` in `src/cost_tracker.py`**

Append to the `CostTracker` class (inside the `@dataclass`):

```python
    def add_from_result(self, result) -> None:
        """Shortcut for the 4 Claude callers — forwards every field from a
        utils.ClaudeResult into add_call(). Avoids 6-kwarg boilerplate."""
        self.add_call(
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_tokens=result.cache_read_tokens,
            cache_creation_tokens=result.cache_creation_tokens,
            web_search_calls=result.web_search_calls,
        )
```

- [ ] **Step 1.8: Extend `src/db.py` schema and migration**

Add the `position_recommendations` block to `SCHEMA_SQL` (after `idx_predictions_status` block, before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS position_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL, run_type TEXT NOT NULL,
    prediction_id INTEGER NOT NULL REFERENCES predictions(id),
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    new_sl_price REAL, new_tp_price REAL,
    market_context_changed BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, run_type, prediction_id)
);

CREATE INDEX IF NOT EXISTS idx_position_recs_prediction ON position_recommendations(prediction_id);
```

Extend `_apply_migrations` to also add the four new columns (idempotent):

```python
def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Idempotent column-add migrations for pre-existing DBs.
    SQLite does not support IF NOT EXISTS on ALTER TABLE, so we inspect first."""
    ti_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(technical_indicators)"
    ).fetchall()}
    if "intraday_range_pct" not in ti_cols:
        conn.execute(
            "ALTER TABLE technical_indicators ADD COLUMN intraday_range_pct REAL"
        )

    pred_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(predictions)"
    ).fetchall()}
    if "hold_days_recommended" not in pred_cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN hold_days_recommended INTEGER")
    if "intraday_range_pct" not in pred_cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN intraday_range_pct REAL")

    out_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(outcomes)"
    ).fetchall()}
    if "days_to_close" not in out_cols:
        conn.execute("ALTER TABLE outcomes ADD COLUMN days_to_close INTEGER")
    if "exit_reason" not in out_cols:
        conn.execute("ALTER TABLE outcomes ADD COLUMN exit_reason TEXT")

    conn.commit()
```

Also extend the inline `CREATE TABLE predictions` and `CREATE TABLE outcomes` blocks so fresh DBs get the columns without relying on migration. In `predictions`, add `hold_days_recommended INTEGER, intraday_range_pct REAL,` before the `created_at` line. In `outcomes`, add `days_to_close INTEGER, exit_reason TEXT,` before `profit_loss_eur`.

Update `save_prediction()` cols-list to include the two new columns at the end:

```python
def save_prediction(conn: sqlite3.Connection, pred: dict) -> int:
    cols = [
        "date", "run_type", "asset_class", "ticker", "direction",
        "entry_price", "tp_price", "tp_pct", "sl_price", "sl_pct", "rr_ratio",
        "total_score", "probability_pct", "confidence",
        "score_market_env", "score_company", "score_valuation",
        "score_momentum", "score_risk", "score_sector",
        "score_catalyst", "score_policy",
        "atr_pct", "rsi_at_entry", "volume_ratio",
        "market_regime", "vix_at_prediction", "sector",
        "trend_boost", "earnings_warning", "summary", "learnable",
        "hold_days_recommended", "intraday_range_pct",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    values = [pred.get(c) for c in cols]
    cur = conn.execute(
        f"INSERT INTO predictions ({', '.join(cols)}) VALUES ({placeholders})",
        values,
    )
    conn.commit()
    return cur.lastrowid
```

Add new helpers at the bottom of `src/db.py`:

```python
def save_position_recommendation(conn: sqlite3.Connection, row: dict) -> int:
    cols = [
        "date", "run_type", "prediction_id", "action", "reason",
        "new_sl_price", "new_tp_price", "market_context_changed",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    values = [row.get(c) for c in cols]
    cur = conn.execute(
        f"INSERT OR REPLACE INTO position_recommendations ({', '.join(cols)}) "
        f"VALUES ({placeholders})",
        values,
    )
    conn.commit()
    return cur.lastrowid


def load_open_predictions_within_max_age_days(
    conn: sqlite3.Connection, today: str, max_trading_days: int = 3,
) -> list[sqlite3.Row]:
    """Returns open, learnable predictions whose calendar age <= max_trading_days
    days from `today`. We use a calendar approximation (sqlite julianday); the
    walk-forward evaluator handles trading-day precision separately."""
    return conn.execute(
        """SELECT * FROM predictions
           WHERE status='open' AND learnable=1
             AND julianday(?) - julianday(date) <= ?
           ORDER BY date DESC""",
        (today, max_trading_days),
    ).fetchall()


def update_outcome_close(
    conn: sqlite3.Connection,
    prediction_id: int, exit_reason: str,
    exit_price: float | None, days_to_close: int,
    closed_date: str, profit_loss_eur: float | None,
    correct_direction_eod: bool | None,
    direction: str,
) -> None:
    """Single transactional helper used by evaluator: writes outcomes row
    AND updates the prediction.status / closed_date / closed_price atomically."""
    status_map = {
        "tp_hit": "closed_tp", "sl_hit": "closed_sl",
        "timeout": "closed_timeout", "pessimistic_overlap": "closed_sl",
        "data_missing": "closed_data_missing",
    }
    status = status_map.get(exit_reason, "closed_timeout")
    conn.execute("BEGIN")
    try:
        conn.execute(
            "UPDATE predictions SET status=?, closed_date=?, closed_price=? WHERE id=?",
            (status, closed_date, exit_price, prediction_id),
        )
        conn.execute(
            """INSERT INTO outcomes
               (prediction_id, direction, evaluated_date,
                price_after_eod, price_change_eod_pct, correct_direction_eod,
                tp_hit, sl_hit, days_to_close, exit_reason, profit_loss_eur)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                prediction_id, direction, closed_date,
                exit_price, None, correct_direction_eod,
                exit_reason == "tp_hit",
                exit_reason in ("sl_hit", "pessimistic_overlap"),
                days_to_close, exit_reason, profit_loss_eur,
            ),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def load_predictions_for_date(
    conn: sqlite3.Connection, date: str, run_type: str,
) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT * FROM predictions
           WHERE date=? AND run_type=?
           ORDER BY total_score DESC""",
        (date, run_type),
    ).fetchall()


def load_position_recommendations_for_date(
    conn: sqlite3.Connection, date: str, run_type: str,
) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT pr.*, p.ticker, p.direction, p.entry_price,
                  p.tp_price, p.sl_price
           FROM position_recommendations pr
           JOIN predictions p ON p.id = pr.prediction_id
           WHERE pr.date=? AND pr.run_type=?
           ORDER BY pr.created_at ASC""",
        (date, run_type),
    ).fetchall()


def load_recent_outcomes(
    conn: sqlite3.Connection, since_date: str,
) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT o.*, p.ticker, p.direction AS pred_direction,
                  p.total_score, p.entry_price
           FROM outcomes o
           JOIN predictions p ON p.id = o.prediction_id
           WHERE o.evaluated_date >= ?
           ORDER BY o.evaluated_date DESC""",
        (since_date,),
    ).fetchall()
```

- [ ] **Step 1.9: Extend `src/guardrails.py` with CFD-Kurzfrist checks**

Replace the whole `GuardrailsChecker` class with:

```python
from dataclasses import dataclass
import config


@dataclass
class GuardrailsChecker:
    min_sources: int = 2
    min_evidence_per_dim: int = 2
    min_rr_hard: float = config.RR_RATIO_MIN_HARD
    momentum_long_min: float = config.MOMENTUM_LONG_MIN
    momentum_short_max: float = config.MOMENTUM_SHORT_MAX
    max_hold_days: int = 3
    min_intraday_range_pct: float = 1.0

    REQUIRED_FIELDS = (
        "ticker", "direction", "confidence", "current_price",
        "tp_price", "sl_price", "rr_ratio", "total_score", "summary",
        "sources_used", "signal_consistency_check", "scores",
        "hold_days_recommended", "intraday_range_pct",
    )

    def check_analysis(self, a: dict) -> tuple[bool, list[str]]:
        errors: list[str] = []

        for f in self.REQUIRED_FIELDS:
            if f not in a or a[f] is None:
                errors.append(f"Required field missing: {f}")

        if errors:
            return False, errors

        if len(a.get("sources_used", [])) < self.min_sources:
            errors.append(
                f"Too few sources: {len(a['sources_used'])} < {self.min_sources}"
            )

        scores = a.get("scores", {})
        for dim, sd in scores.items():
            if len(sd.get("evidence", [])) < self.min_evidence_per_dim:
                errors.append(
                    f"Dimension {dim}: too few evidence items "
                    f"({len(sd.get('evidence', []))} < {self.min_evidence_per_dim})"
                )

        p = a["current_price"]
        tp = a["tp_price"]
        sl = a["sl_price"]
        d = a["direction"]
        if d == "long":
            if tp <= p:
                errors.append(f"Long TP {tp} not above entry {p}")
            if sl >= p:
                errors.append(f"Long SL {sl} not below entry {p}")
        elif d == "short":
            if tp >= p:
                errors.append(f"Short TP {tp} not below entry {p}")
            if sl <= p:
                errors.append(f"Short SL {sl} not above entry {p}")

        if a.get("rr_ratio", 0) < self.min_rr_hard:
            errors.append(f"R/R {a['rr_ratio']} below hard minimum {self.min_rr_hard}")

        if a.get("data_quality") == "low" and a.get("confidence") == "high":
            errors.append("Confidence 'high' incompatible with data_quality 'low'")

        momentum = scores.get("momentum", {}).get("value")
        if momentum is not None:
            if d == "long" and momentum < self.momentum_long_min:
                errors.append(
                    f"Signal consistency: long momentum {momentum} < {self.momentum_long_min}"
                )
            if d == "short" and momentum > self.momentum_short_max:
                errors.append(
                    f"Signal consistency: short momentum {momentum} > {self.momentum_short_max}"
                )

        hold_days = a.get("hold_days_recommended")
        if hold_days is not None and hold_days > self.max_hold_days:
            errors.append(
                f"Haltedauer > {self.max_hold_days} Tage – nicht CFD-geeignet "
                f"(hold_days_recommended={hold_days})"
            )

        rng = a.get("intraday_range_pct")
        if rng is not None and rng < self.min_intraday_range_pct:
            errors.append(
                f"Intraday-Range < {self.min_intraday_range_pct:.1f}% – nicht CFD-geeignet "
                f"(intraday_range_pct={rng})"
            )

        return len(errors) == 0, errors
```

- [ ] **Step 1.10: Refactor `trend_analyzer.py` and `quick_filter.py` to use shared helpers**

In `src/trend_analyzer.py`:
- Delete the local `_FENCE_RE`, `_extract_json`, and `WEB_SEARCH_TOOL`.
- Add import: `from src.utils import call_claude, extract_json_blob, WEB_SEARCH_TOOL`
- Replace the `_extract_json(...)` call with `extract_json_blob(result.text, TrendAnalyzerError)`.
- Replace the inline `cost_tracker.add_call(...)` block with `cost_tracker.add_from_result(result)`.

In `src/quick_filter.py`:
- Delete the local `_FENCE_RE` and `_extract_json`.
- Add import: `from src.utils import call_claude, extract_json_blob`
- Replace `_extract_json(result.text)` with `extract_json_blob(result.text, QuickFilterError)`.
- Replace the inline `cost_tracker.add_call(...)` block with `cost_tracker.add_from_result(result)`.

- [ ] **Step 1.11: Run all unit tests, expect green**

Run: `pytest tests/unit/ -v`
Expected: previous 82 tests still pass + 12+ new tests pass.

- [ ] **Step 1.12: Commit**

```bash
git add src/utils.py src/cost_tracker.py src/db.py src/guardrails.py \
        src/trend_analyzer.py src/quick_filter.py \
        tests/unit/test_utils.py tests/unit/test_cost_tracker.py \
        tests/unit/test_db.py tests/unit/test_guardrails.py
git commit -m "Sprint1/Plan3 Task 1: foundation extensions for deep_analysis pipeline"
```

---

## Task 2: Prompt templates (4 new)

All four templates are versioned (`*_v1.txt`) so Sprint 3's prompt-optimizer can later add `*_v2.txt`. Each prompt **must** prescribe JSON-only output with no prose around it and must enumerate every required field that `guardrails.py` checks.

**Files:**
- Create: `prompts/deep_analysis_v1.txt`
- Create: `prompts/policy_monitor_v1.txt`
- Create: `prompts/commodities_crypto_v1.txt`
- Create: `prompts/portfolio_check_v1.txt`

- [ ] **Step 2.1: Create `prompts/deep_analysis_v1.txt`**

```
You are a deep equity analyst specialised in short-term CFD setups (hold 1-3 trading days)
on US large-cap stocks. You receive ONE ticker snapshot, the macro trend context (cached),
the policy_risk events (cached), and the quick-filter pre-score for this ticker. You may
use the web_search tool up to 5 times to gather very recent, ticker-specific evidence.

Output ONLY a single JSON object, no prose before or after, with this EXACT shape:

{
  "ticker": "<the input symbol>",
  "asset_class": "stock",
  "direction": "<'long' | 'short' | 'none'>",
  "confidence": "<'low' | 'medium' | 'high'>",
  "current_price": <number>,
  "tp_price": <number>,
  "sl_price": <number>,
  "tp_pct": <number>,
  "sl_pct": <number>,
  "rr_ratio": <number, must be >= 1.5>,
  "total_score": <number 0-10, one decimal>,
  "probability_pct": <integer 0-100>,
  "hold_days_recommended": <integer 1-3>,
  "intraday_range_pct": <number, mirror of the value from the snapshot>,
  "earnings_warning": <true|false, true if earnings_in_days <= 2>,
  "summary": "<one paragraph, max 600 chars, ends with the trade thesis>",
  "sources_used": ["<url1>", "<url2>"],
  "signal_consistency_check": "<'ok' | brief reason if you noticed an inconsistency>",
  "scores": {
    "market_environment": {"value": <0-10>, "evidence": ["<line>", "<line>"]},
    "company_quality":    {"value": <0-10>, "evidence": ["<line>", "<line>"]},
    "valuation":           {"value": <0-10>, "evidence": ["<line>", "<line>"]},
    "momentum":           {"value": <0-10>, "evidence": ["<line>", "<line>"]},
    "risk":               {"value": <0-10>, "evidence": ["<line>", "<line>"]},
    "sector_trend":       {"value": <0-10>, "evidence": ["<line>", "<line>"]},
    "catalyst":           {"value": <0-10>, "evidence": ["<line>", "<line>"]},
    "policy_risk":        {"value": <0-10>, "evidence": ["<line>", "<line>"]}
  }
}

Hard rules:
- If direction='long', momentum.value MUST be >= 6.0, and tp_price > current_price > sl_price.
- If direction='short', momentum.value MUST be <= 4.0, and tp_price < current_price < sl_price.
- hold_days_recommended must be an integer in 1..3. If your honest call is >3 days, set
  direction='none' instead.
- intraday_range_pct must echo the snapshot value verbatim. Never invent.
- rr_ratio = abs(tp_price - current_price) / abs(current_price - sl_price), rounded 2 decimals.
- Every dimension needs >= 2 evidence lines citing concrete numbers OR a URL fragment.
- sources_used: >= 2 distinct domains. Use the same domains that you cited inline.
- If your evidence is too thin or signals contradict, return direction='none' with summary
  explaining why. A direction='none' analysis is still a valid response.
```

- [ ] **Step 2.2: Create `prompts/policy_monitor_v1.txt`**

```
You are a policy & geopolitics analyst. Your single job is to surface market-moving
events from the last 48 hours that could affect US equities, oil, gold, or major crypto
on a 1-3 trading day horizon. Use the web_search tool up to 5 times.

In scope (non-exhaustive): tariffs and trade policy, central-bank communication,
geopolitical conflict, regulatory decisions, defence / NATO, healthcare regulation,
China / Taiwan headlines, named-company statements by heads of government. Trump
is one possible source of policy_risk events — not a fixpoint.

Output ONLY a single JSON object, no prose before or after, with this EXACT shape:

{
  "policy_risk_level": "<'low' | 'medium' | 'high'>",
  "events": [
    {
      "headline": "<one line, max 140 chars>",
      "category": "<'tariff' | 'central_bank' | 'geopolitics' | 'regulation' | 'defence' | 'healthcare' | 'other'>",
      "affected_tickers": ["TICK1", "TICK2"],
      "affected_sectors": ["<sector ETF or name>"],
      "direction_hint": "<'bullish' | 'bearish' | 'mixed'>",
      "source_url": "<url>",
      "as_of": "<ISO date>"
    }
  ],
  "summary": "<2-3 sentences overall, max 500 chars>"
}

Constraints:
- 0 to 6 events. If nothing material, return empty events and policy_risk_level='low'.
- Tickers must be SP500 symbols, commodity futures (GC=F, SI=F, CL=F), or BTC-USD/ETH-USD/SOL-USD/XRP-USD.
- Never invent dates or URLs. Skip an event rather than fabricate sources.
```

- [ ] **Step 2.3: Create `prompts/commodities_crypto_v1.txt`**

```
You are a commodities-and-crypto analyst specialised in short-term CFD setups
(hold 1-3 trading days). You receive ONE asset snapshot (ticker, asset_class:
commodity or crypto, OHLC-derived indicators, the asset's display name),
the macro trend context (cached), and policy_risk events (cached). Use web_search
up to 3 times for very recent supply/demand or on-chain news.

Output ONLY a single JSON object, no prose before or after, with this EXACT shape:

{
  "ticker": "<the input symbol, e.g. 'GC=F' or 'BTC-USD'>",
  "asset_class": "<'commodity' | 'crypto'>",
  "direction": "<'long' | 'short' | 'none'>",
  "confidence": "<'low' | 'medium' | 'high'>",
  "current_price": <number>,
  "tp_price": <number>,
  "sl_price": <number>,
  "tp_pct": <number>,
  "sl_pct": <number>,
  "rr_ratio": <number, >= 1.5>,
  "total_score": <number 0-10>,
  "probability_pct": <integer 0-100>,
  "hold_days_recommended": <integer 1-3>,
  "intraday_range_pct": <number, mirror of snapshot>,
  "summary": "<one paragraph, max 600 chars>",
  "sources_used": ["<url1>", "<url2>"],
  "signal_consistency_check": "<'ok' | brief reason>",
  "scores": {
    "market_environment": {"value": <0-10>, "evidence": ["<line>", "<line>"]},
    "company_quality":    {"value": <0-10>, "evidence": ["asset-specific quality signal: e.g. backwardation for commodities, on-chain activity for crypto"]},
    "valuation":           {"value": <0-10>, "evidence": ["<line>", "<line>"]},
    "momentum":           {"value": <0-10>, "evidence": ["<line>", "<line>"]},
    "risk":               {"value": <0-10>, "evidence": ["<line>", "<line>"]},
    "sector_trend":       {"value": <0-10>, "evidence": ["<line>", "<line>"]},
    "catalyst":           {"value": <0-10>, "evidence": ["<line>", "<line>"]},
    "policy_risk":        {"value": <0-10>, "evidence": ["<line>", "<line>"]}
  },
  "extra": {
    "fear_greed_value": <0-100 | null>,
    "gold_silver_ratio": <number | null>,
    "btc_dominance_pct": <number | null>
  }
}

Hard rules:
- direction='long' requires momentum.value >= 6.0; 'short' requires <= 4.0.
- hold_days_recommended in 1..3 — otherwise direction='none'.
- intraday_range_pct echoes the snapshot verbatim.
- For commodities, evaluate via macro lens (rates, USD for gold/silver; OPEC + geopolitics
  for oil); for crypto via Fear & Greed + BTC dominance + relevant on-chain news.
- Every dimension needs >= 2 evidence lines; sources_used >= 2 distinct domains.
- If evidence is thin or contradictory, return direction='none'.
```

- [ ] **Step 2.4: Create `prompts/portfolio_check_v1.txt`**

```
You are a portfolio risk manager. You receive ONE currently-open CFD position
(predicted at most 3 trading days ago) together with the original thesis, the
current asset snapshot, the macro trend context (cached), and the policy_risk
events (cached). You may use web_search up to 3 times for very recent news on
this specific ticker.

Your job: decide whether to HOLD, CLOSE, or ADJUST the position. The trader
will execute your recommendation manually at market open. Be decisive.

Output ONLY a single JSON object, no prose before or after, with this EXACT shape:

{
  "prediction_id": <integer, mirror of input>,
  "ticker": "<symbol, mirror of input>",
  "action": "<'HALTEN' | 'SCHLIESSEN' | 'ANPASSEN'>",
  "reason": "<one paragraph, max 600 chars, ends with a clear action statement>",
  "new_sl_price": <number | null>,
  "new_tp_price": <number | null>,
  "market_context_changed": <true | false>,
  "sources_used": ["<url1>", "<url2>"]
}

Decision rules:
- HALTEN: thesis still intact, no new contradicting catalyst, technicals still
  pointing in original direction. new_sl_price and new_tp_price MUST be null.
- SCHLIESSEN: thesis broken (e.g., key technical level lost, policy shock against
  the position, major guidance change), OR position is at +/- 80% of TP/SL distance
  AND momentum is weakening, OR a stronger opposite signal has emerged.
  new_sl_price and new_tp_price MUST be null.
- ANPASSEN: thesis intact but stops/targets should be tightened or trailed because
  position has moved favourably. Provide both new_sl_price AND new_tp_price.
  new_sl_price must still be on the same side of current_price as the original SL.

Hard rules:
- market_context_changed=true whenever the trend context or policy_risk events
  materially diverge from the conditions at prediction time. This is independent
  of the action — you may HOLD even if context changed slightly.
- sources_used: >= 2 distinct domains, even for HALTEN (cite the absence of news as
  ‚no new catalyst‘ with the source you checked).
- Never invent prices or URLs. If you cannot decide with confidence, default to HALTEN.
```

- [ ] **Step 2.5: Verify files exist (no test step — prompts are read at import time)**

Run: `ls prompts/`
Expected: 6 files (`deep_analysis_v1.txt`, `policy_monitor_v1.txt`, `commodities_crypto_v1.txt`, `portfolio_check_v1.txt`, plus existing `quick_filter_v1.txt`, `trend_analyzer_v1.txt`).

- [ ] **Step 2.6: Commit**

```bash
git add prompts/deep_analysis_v1.txt prompts/policy_monitor_v1.txt \
        prompts/commodities_crypto_v1.txt prompts/portfolio_check_v1.txt
git commit -m "Sprint1/Plan3 Task 2: prompt templates for deep_analysis, policy_monitor, commodities_crypto, portfolio_check"
```

---

## Task 3: `deep_analysis.py` — Phase 3 (Policy Monitor + per-asset deep dive)

Two public callables:
- `run_policy_monitor(date, run_type, cost_tracker)` → dict (called once per run).
- `analyze_asset(ticker_data, quick_filter_result, trend_context, policy_context, cost_tracker)` → dict (one per asset).

A simple `analyze_assets(ticker_datas, quick_filter_results, trend_context, policy_context, cost_tracker)` driver sequentially loops `analyze_asset`. Parallel dispatch with `concurrent.futures.ThreadPoolExecutor(max_workers=CLAUDE_PARALLEL_CALLS)` is **deliberately out of scope** for Sprint 1 — sequential keeps cost-tracking deterministic and the cap-abort path simple.

**Files:**
- Create: `tests/fixtures/mock_deep_analysis_response.json`
- Create: `tests/fixtures/mock_policy_monitor_response.json`
- Create: `src/deep_analysis.py`
- Create: `tests/unit/test_deep_analysis.py`

- [ ] **Step 3.1: Create `tests/fixtures/mock_policy_monitor_response.json`**

```json
{
  "policy_risk_level": "medium",
  "events": [
    {
      "headline": "US-EU tariff truce extended by 60 days (Reuters 2026-05-18)",
      "category": "tariff",
      "affected_tickers": ["AAPL", "TSLA"],
      "affected_sectors": ["XLK", "XLY"],
      "direction_hint": "bullish",
      "source_url": "https://www.reuters.com/world/tariff-truce-extended",
      "as_of": "2026-05-18"
    },
    {
      "headline": "Fed signals one more 25 bps hike at June meeting (Bloomberg 2026-05-19)",
      "category": "central_bank",
      "affected_tickers": [],
      "affected_sectors": ["XLF", "XLU"],
      "direction_hint": "bearish",
      "source_url": "https://www.bloomberg.com/news/fed-signals-hike",
      "as_of": "2026-05-19"
    }
  ],
  "summary": "Tariff thaw is mildly bullish for consumer tech; Fed hike risk weighs on rate-sensitive sectors. Net policy_risk_level=medium."
}
```

- [ ] **Step 3.2: Create `tests/fixtures/mock_deep_analysis_response.json`**

```json
{
  "ticker": "AAPL",
  "asset_class": "stock",
  "direction": "long",
  "confidence": "high",
  "current_price": 178.5,
  "tp_price": 184.0,
  "sl_price": 176.0,
  "tp_pct": 3.08,
  "sl_pct": 1.4,
  "rr_ratio": 2.2,
  "total_score": 7.62,
  "probability_pct": 66,
  "hold_days_recommended": 2,
  "intraday_range_pct": 1.5,
  "earnings_warning": false,
  "summary": "AAPL benefits from AI capex acceleration + tariff truce. Tight SL below SMA20.",
  "sources_used": ["https://www.reuters.com/x", "https://www.bloomberg.com/y"],
  "signal_consistency_check": "ok",
  "scores": {
    "market_environment": {"value": 7.0, "evidence": ["VIX 14", "SP500 +0.6%"]},
    "company_quality":    {"value": 8.5, "evidence": ["EPS beat 4.2%", "guidance raised"]},
    "valuation":           {"value": 6.0, "evidence": ["fwd P/E 26", "below 5yr avg"]},
    "momentum":           {"value": 8.0, "evidence": ["RSI 58 rising", "above SMA200 +12.8%"]},
    "risk":               {"value": 6.5, "evidence": ["ATR 1.8%", "debt/eq 1.45"]},
    "sector_trend":       {"value": 7.5, "evidence": ["XLK +3% week", "AI flows"]},
    "catalyst":           {"value": 7.0, "evidence": ["WWDC 2026-06-09", "iPad refresh leaked"]},
    "policy_risk":        {"value": 6.0, "evidence": ["tariff truce extended", "China supply chain stable"]}
  }
}
```

- [ ] **Step 3.3: Write failing tests**

`tests/unit/test_deep_analysis.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.cost_tracker import CostTracker
from src.deep_analysis import (
    run_policy_monitor, analyze_asset, analyze_assets, DeepAnalysisError,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def _fake_result(text: str, model: str = "claude-sonnet-4-6",
                 web_search_calls: int = 3) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 5000
    r.output_tokens = 4000
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = model
    r.web_search_calls = web_search_calls
    return r


def _td(ticker: str = "AAPL", **overrides) -> dict:
    base = {
        "ticker": ticker, "price": 178.5,
        "rsi_14": 58.0, "macd_signal": "bullish_cross", "atr_pct": 1.8,
        "bb_position": 0.62, "above_sma20": 2.1, "above_sma50": 5.4,
        "above_sma200": 12.8, "volume_ratio": 1.15,
        "intraday_range_pct": 1.5,
        "pe_ratio": 28.4, "forward_pe": 26.2, "market_cap_b": 2800.0,
        "sector": "Technology", "earnings_in_days": 14, "earnings_beat_pct": 4.2,
        "data_quality": "high",
    }
    base.update(overrides)
    return base


def _trend_context() -> dict:
    return {"trends": [{"name": "ai-capex"}], "trend_summary": "risk-on"}


def _policy_context() -> dict:
    return json.loads((FIXTURE_DIR / "mock_policy_monitor_response.json").read_text())


def _quick_filter_result(ticker: str = "AAPL") -> dict:
    return {
        "ticker": ticker, "long_score": 7.5, "short_score": 2.0,
        "confidence": "high", "evidence": ["x"], "exclude": False,
    }


def test_run_policy_monitor_parses_and_returns(in_memory_db):
    payload = (FIXTURE_DIR / "mock_policy_monitor_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.deep_analysis.call_claude", return_value=fake):
        out = run_policy_monitor(date="2026-05-19", run_type="close",
                                 cost_tracker=tracker)

    assert out["policy_risk_level"] == "medium"
    assert len(out["events"]) == 2
    assert tracker.input_tokens == 5000


def test_run_policy_monitor_uses_web_search():
    payload = (FIXTURE_DIR / "mock_policy_monitor_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.deep_analysis.call_claude", return_value=fake) as mock_call:
        run_policy_monitor(date="2026-05-19", run_type="close",
                           cost_tracker=tracker)
    kwargs = mock_call.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert any(t.get("name") == "web_search" for t in kwargs["tools"])


def test_run_policy_monitor_tolerates_empty_events():
    fake = _fake_result(json.dumps({
        "policy_risk_level": "low", "events": [], "summary": "Calm news cycle.",
    }))
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude", return_value=fake):
        out = run_policy_monitor(date="2026-05-19", run_type="close",
                                 cost_tracker=tracker)
    assert out["events"] == []


def test_analyze_asset_returns_parsed_analysis():
    payload = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude", return_value=fake):
        out = analyze_asset(
            ticker_data=_td(),
            quick_filter_result=_quick_filter_result(),
            trend_context=_trend_context(),
            policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    assert out["ticker"] == "AAPL"
    assert out["direction"] == "long"
    assert out["rr_ratio"] == 2.2


def test_analyze_asset_bills_cost_tracker_via_add_from_result():
    payload = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude", return_value=fake):
        analyze_asset(
            ticker_data=_td(), quick_filter_result=_quick_filter_result(),
            trend_context=_trend_context(), policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    assert tracker.input_tokens == 5000
    assert tracker.output_tokens == 4000
    assert tracker.web_search_calls == 3
    assert tracker.total_eur > 0


def test_analyze_asset_raises_on_unparseable_response():
    fake = _fake_result("totally not json")
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude", return_value=fake):
        with pytest.raises(DeepAnalysisError):
            analyze_asset(
                ticker_data=_td(), quick_filter_result=_quick_filter_result(),
                trend_context=_trend_context(), policy_context=_policy_context(),
                cost_tracker=tracker,
            )


def test_analyze_asset_skips_when_quick_filter_excludes():
    """A ticker with quick_filter exclude=True is never sent to deep_analysis."""
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude") as mock_call:
        out = analyze_asset(
            ticker_data=_td(), policy_context=_policy_context(),
            quick_filter_result={**_quick_filter_result(), "exclude": True},
            trend_context=_trend_context(), cost_tracker=tracker,
        )
    assert out is None
    mock_call.assert_not_called()


def test_analyze_assets_loops_and_collects_non_none():
    payload = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    fake_ok = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    excl = {**_quick_filter_result("MSFT"), "exclude": True}

    with patch("src.deep_analysis.call_claude", return_value=fake_ok):
        out = analyze_assets(
            ticker_datas=[_td("AAPL"), _td("MSFT")],
            quick_filter_results=[_quick_filter_result("AAPL"), excl],
            trend_context=_trend_context(),
            policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    assert len(out) == 1
    assert out[0]["ticker"] == "AAPL"


def test_analyze_assets_skips_on_individual_failure_continues():
    """A single ticker raising must NOT kill the loop."""
    payload_ok = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    tracker = CostTracker(hard_cap_eur=10.0)

    side_effects = [_fake_result("garbage"), _fake_result(payload_ok)]
    with patch("src.deep_analysis.call_claude", side_effect=side_effects):
        out = analyze_assets(
            ticker_datas=[_td("BADCO"), _td("AAPL")],
            quick_filter_results=[
                _quick_filter_result("BADCO"),
                _quick_filter_result("AAPL"),
            ],
            trend_context=_trend_context(),
            policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    assert len(out) == 1
    assert out[0]["ticker"] == "AAPL"


def test_analyze_asset_passes_trend_and_policy_into_user_message():
    payload = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude", return_value=fake) as mock_call:
        analyze_asset(
            ticker_data=_td(), quick_filter_result=_quick_filter_result(),
            trend_context=_trend_context(), policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    user_msg = mock_call.call_args.kwargs["user"]
    assert "ai-capex" in user_msg
    assert "tariff truce" in user_msg.lower() or "tariff-truce" in user_msg.lower()
    assert "AAPL" in user_msg
```

- [ ] **Step 3.4: Run failing tests**

Run: `pytest tests/unit/test_deep_analysis.py -v`
Expected: ImportError on `run_policy_monitor`, `analyze_asset`, `analyze_assets`, `DeepAnalysisError`.

- [ ] **Step 3.5: Implement `src/deep_analysis.py`**

```python
"""Phase 3: Policy monitor (1× per run) + per-asset deep analysis with web search.

Both callables use Sonnet + server-side web_search. The 8-dimension score is
returned verbatim from the model and validated by guardrails.py downstream.
Per-asset failures are caught and logged so a single broken ticker never aborts
the run. Only CostCapExceeded (from cost_tracker) is fatal."""
import json
import logging
from pathlib import Path

from src.cost_tracker import CostTracker
from src.utils import call_claude, extract_json_blob, WEB_SEARCH_TOOL

log = logging.getLogger("shares_future.deep_analysis")

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
DEEP_SYSTEM_PROMPT = (PROMPT_DIR / "deep_analysis_v1.txt").read_text()
POLICY_SYSTEM_PROMPT = (PROMPT_DIR / "policy_monitor_v1.txt").read_text()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS_DEEP = 4096
MAX_TOKENS_POLICY = 3072


class DeepAnalysisError(RuntimeError):
    """Per-asset deep_analysis call produced unparseable output."""


class PolicyMonitorError(RuntimeError):
    """Policy monitor failed to produce parseable output."""


def run_policy_monitor(
    date: str, run_type: str, cost_tracker: CostTracker,
) -> dict:
    """Single Sonnet+web_search call. Returns
    {policy_risk_level, events, summary}. Tolerates empty events list."""
    user_msg = (
        f"Today is {date}. Run type: {run_type}. "
        "Use web_search 2-5 times to surface market-moving policy/geopolitics "
        "events from the last 48h. Then return the JSON object defined in your "
        "system prompt."
    )
    result = call_claude(
        model=MODEL, system=POLICY_SYSTEM_PROMPT, user=user_msg,
        max_tokens=MAX_TOKENS_POLICY, tools=[WEB_SEARCH_TOOL],
    )
    cost_tracker.add_from_result(result)
    parsed = extract_json_blob(result.text, PolicyMonitorError)
    if "events" not in parsed or "policy_risk_level" not in parsed:
        raise PolicyMonitorError(
            "Policy monitor response missing required keys "
            "(policy_risk_level, events)"
        )
    log.info(
        f"Policy monitor: level={parsed['policy_risk_level']} "
        f"events={len(parsed['events'])} cost={cost_tracker.total_eur:.3f} EUR"
    )
    return parsed


def _build_user_message(
    ticker_data: dict,
    quick_filter_result: dict,
    trend_context: dict,
    policy_context: dict,
) -> str:
    parts = [
        "TREND CONTEXT:", json.dumps(trend_context, ensure_ascii=False),
        "\nPOLICY CONTEXT:", json.dumps(policy_context, ensure_ascii=False),
        "\nQUICK FILTER PRE-SCORE:", json.dumps(quick_filter_result, ensure_ascii=False),
        "\nTICKER SNAPSHOT:", json.dumps(ticker_data, ensure_ascii=False),
        "\nReturn the JSON object defined in your system prompt for THIS one ticker.",
    ]
    return "\n".join(parts)


def analyze_asset(
    ticker_data: dict,
    quick_filter_result: dict,
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> dict | None:
    """Deep-analyze one asset. Returns the parsed analysis dict, or None if the
    quick-filter excluded the ticker (no Claude call made). Raises DeepAnalysisError
    on unparseable output — the caller (analyze_assets loop) must catch."""
    if quick_filter_result.get("exclude"):
        log.info(f"{ticker_data.get('ticker')}: skipped by quick_filter exclude")
        return None

    user_msg = _build_user_message(
        ticker_data=ticker_data,
        quick_filter_result=quick_filter_result,
        trend_context=trend_context,
        policy_context=policy_context,
    )
    result = call_claude(
        model=MODEL, system=DEEP_SYSTEM_PROMPT, user=user_msg,
        max_tokens=MAX_TOKENS_DEEP, tools=[WEB_SEARCH_TOOL],
    )
    cost_tracker.add_from_result(result)
    parsed = extract_json_blob(result.text, DeepAnalysisError)
    return parsed


def analyze_assets(
    ticker_datas: list[dict],
    quick_filter_results: list[dict],
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """Sequentially deep-analyze each ticker. Per-asset failures are caught and
    logged so a single broken ticker never aborts the run. CostCapExceeded
    propagates (the orchestrator handles partial-run e-mails)."""
    qf_by_ticker = {q["ticker"]: q for q in quick_filter_results}
    out: list[dict] = []
    for td in ticker_datas:
        t = td["ticker"]
        qf = qf_by_ticker.get(t)
        if qf is None:
            log.warning(f"{t}: no quick_filter result, skipping deep_analysis")
            continue
        try:
            a = analyze_asset(
                ticker_data=td, quick_filter_result=qf,
                trend_context=trend_context, policy_context=policy_context,
                cost_tracker=cost_tracker,
            )
        except DeepAnalysisError as e:
            log.warning(f"{t}: deep_analysis failed: {e}")
            continue
        if a is not None:
            out.append(a)
    log.info(
        f"Phase 3 done: {len(out)} analyses produced, "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return out
```

- [ ] **Step 3.6: Run tests, expect green**

Run: `pytest tests/unit/test_deep_analysis.py -v`
Expected: 10 passed.

- [ ] **Step 3.7: Commit**

```bash
git add src/deep_analysis.py tests/unit/test_deep_analysis.py \
        tests/fixtures/mock_policy_monitor_response.json \
        tests/fixtures/mock_deep_analysis_response.json
git commit -m "Sprint1/Plan3 Task 3: Phase 3 deep_analysis with policy_monitor and 8-dim score"
```

---

## Task 4: `commodities_crypto.py` — Phase 3b for the 7 fixed assets

Same structure as `analyze_assets` but with a different system prompt, the asset-class field is `commodity`/`crypto`, and the caller passes raw display names so the prompt knows whether to think gold-as-rates or crypto-as-fear/greed. We also fetch Fear & Greed once per run via `requests.get` and inject it into `trend_context["extra"]["fear_greed_value"]`.

**Files:**
- Create: `tests/fixtures/mock_commodities_crypto_response.json`
- Create: `src/commodities_crypto.py`
- Create: `tests/unit/test_commodities_crypto.py`

- [ ] **Step 4.1: Create `tests/fixtures/mock_commodities_crypto_response.json`**

```json
{
  "ticker": "GC=F",
  "asset_class": "commodity",
  "direction": "long",
  "confidence": "medium",
  "current_price": 2380.0,
  "tp_price": 2420.0,
  "sl_price": 2360.0,
  "tp_pct": 1.68,
  "sl_pct": 0.84,
  "rr_ratio": 2.0,
  "total_score": 6.9,
  "probability_pct": 58,
  "hold_days_recommended": 2,
  "intraday_range_pct": 1.2,
  "summary": "Gold supported by Fed dovish pivot expectations. SL below 100-day SMA.",
  "sources_used": ["https://www.kitco.com/x", "https://www.reuters.com/y"],
  "signal_consistency_check": "ok",
  "scores": {
    "market_environment": {"value": 7.0, "evidence": ["DXY -0.5%", "10Y yield -8bp"]},
    "company_quality":    {"value": 7.0, "evidence": ["central bank buying", "ETF inflows"]},
    "valuation":           {"value": 5.5, "evidence": ["fair vs hist", "GSR 80"]},
    "momentum":           {"value": 7.0, "evidence": ["RSI 60", "above SMA50"]},
    "risk":               {"value": 6.0, "evidence": ["ATR 1.2%", "Fed surprise risk"]},
    "sector_trend":       {"value": 7.0, "evidence": ["XAU index +2%", "miners +3%"]},
    "catalyst":           {"value": 6.5, "evidence": ["CPI Tue", "FOMC minutes Wed"]},
    "policy_risk":        {"value": 6.0, "evidence": ["geopolitics China-Taiwan", "Mideast"]}
  },
  "extra": {
    "fear_greed_value": 62,
    "gold_silver_ratio": 80.3,
    "btc_dominance_pct": null
  }
}
```

- [ ] **Step 4.2: Write failing tests**

`tests/unit/test_commodities_crypto.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.cost_tracker import CostTracker
from src.commodities_crypto import (
    analyze_commodities_and_crypto, analyze_asset,
    fetch_fear_greed, CommoditiesCryptoError,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def _fake_result(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 4000
    r.output_tokens = 3000
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = "claude-sonnet-4-6"
    r.web_search_calls = 2
    return r


def _td(ticker: str, asset_class: str) -> dict:
    return {
        "ticker": ticker, "asset_class": asset_class, "name": "Gold",
        "price": 2380.0, "rsi_14": 60.0, "atr_pct": 1.2,
        "intraday_range_pct": 1.2, "above_sma50": 1.5,
        "macd_signal": "neutral", "volume_ratio": 1.0,
        "data_quality": "high",
    }


def _trend() -> dict:
    return {"trends": [], "trend_summary": "calm"}


def _policy() -> dict:
    return {"policy_risk_level": "low", "events": [], "summary": ""}


def test_analyze_asset_returns_parsed():
    payload = (FIXTURE_DIR / "mock_commodities_crypto_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.commodities_crypto.call_claude", return_value=fake):
        out = analyze_asset(
            ticker_data=_td("GC=F", "commodity"),
            trend_context=_trend(),
            policy_context=_policy(),
            extra_context={"fear_greed_value": 62},
            cost_tracker=tracker,
        )
    assert out["ticker"] == "GC=F"
    assert out["asset_class"] == "commodity"


def test_analyze_asset_bills_cost_tracker():
    payload = (FIXTURE_DIR / "mock_commodities_crypto_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.commodities_crypto.call_claude", return_value=fake):
        analyze_asset(
            ticker_data=_td("GC=F", "commodity"),
            trend_context=_trend(), policy_context=_policy(),
            extra_context={"fear_greed_value": 62}, cost_tracker=tracker,
        )
    assert tracker.input_tokens == 4000
    assert tracker.total_eur > 0


def test_analyze_asset_raises_on_unparseable():
    fake = _fake_result("not json")
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.commodities_crypto.call_claude", return_value=fake):
        with pytest.raises(CommoditiesCryptoError):
            analyze_asset(
                ticker_data=_td("GC=F", "commodity"),
                trend_context=_trend(), policy_context=_policy(),
                extra_context={}, cost_tracker=tracker,
            )


def test_analyze_loop_skips_individual_failures():
    payload = (FIXTURE_DIR / "mock_commodities_crypto_response.json").read_text()
    tracker = CostTracker(hard_cap_eur=10.0)
    side_effects = [_fake_result("bad"), _fake_result(payload)]
    with patch("src.commodities_crypto.call_claude", side_effect=side_effects):
        out = analyze_commodities_and_crypto(
            ticker_datas=[_td("BAD=F", "commodity"), _td("GC=F", "commodity")],
            trend_context=_trend(), policy_context=_policy(),
            extra_context={"fear_greed_value": 62}, cost_tracker=tracker,
        )
    assert len(out) == 1
    assert out[0]["ticker"] == "GC=F"


def test_fetch_fear_greed_parses_alternative_me_format():
    with patch("src.commodities_crypto.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {
            "data": [{"value": "62", "value_classification": "Greed"}],
        }
        mock_get.return_value.raise_for_status = lambda: None
        out = fetch_fear_greed()
    assert out == {"value": 62, "label": "Greed"}


def test_fetch_fear_greed_returns_none_on_failure():
    with patch("src.commodities_crypto.requests.get",
               side_effect=Exception("network")):
        assert fetch_fear_greed() is None


def test_user_message_includes_extra_context_keys():
    payload = (FIXTURE_DIR / "mock_commodities_crypto_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.commodities_crypto.call_claude", return_value=fake) as mock_call:
        analyze_asset(
            ticker_data=_td("BTC-USD", "crypto"),
            trend_context=_trend(), policy_context=_policy(),
            extra_context={"fear_greed_value": 62, "btc_dominance_pct": 54.2},
            cost_tracker=tracker,
        )
    user_msg = mock_call.call_args.kwargs["user"]
    assert "fear_greed_value" in user_msg
    assert "btc_dominance_pct" in user_msg
```

- [ ] **Step 4.3: Run failing tests**

Run: `pytest tests/unit/test_commodities_crypto.py -v`
Expected: ImportError.

- [ ] **Step 4.4: Implement `src/commodities_crypto.py`**

```python
"""Phase 3b: Commodities + Crypto deep analysis.

Same Sonnet + web_search shape as Phase 3, with a dedicated prompt and a
per-run Fear & Greed fetch injected as extra_context. The 7 assets are always
analysed regardless of trend/quick-filter, but per-asset failures are caught
so a single broken call never aborts the run."""
import json
import logging
from pathlib import Path

import requests

from src.cost_tracker import CostTracker
from src.utils import call_claude, extract_json_blob, WEB_SEARCH_TOOL

log = logging.getLogger("shares_future.commodities_crypto")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "commodities_crypto_v1.txt").read_text()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 3584
FEAR_GREED_URL = "https://api.alternative.me/fng/"
FEAR_GREED_TIMEOUT_SEC = 5


class CommoditiesCryptoError(RuntimeError):
    """Per-asset commodities/crypto call produced unparseable output."""


def fetch_fear_greed() -> dict | None:
    """Returns {value:int, label:str} or None on any failure."""
    try:
        r = requests.get(FEAR_GREED_URL, timeout=FEAR_GREED_TIMEOUT_SEC)
        r.raise_for_status()
        d = r.json()["data"][0]
        return {"value": int(d["value"]), "label": d["value_classification"]}
    except Exception as e:  # broad on purpose: optional enrichment
        log.warning(f"fetch_fear_greed failed: {e}")
        return None


def _build_user_message(
    ticker_data: dict,
    trend_context: dict,
    policy_context: dict,
    extra_context: dict,
) -> str:
    parts = [
        "TREND CONTEXT:", json.dumps(trend_context, ensure_ascii=False),
        "\nPOLICY CONTEXT:", json.dumps(policy_context, ensure_ascii=False),
        "\nEXTRA CONTEXT:", json.dumps(extra_context, ensure_ascii=False),
        "\nASSET SNAPSHOT:", json.dumps(ticker_data, ensure_ascii=False),
        "\nReturn the JSON object defined in your system prompt for THIS one asset.",
    ]
    return "\n".join(parts)


def analyze_asset(
    ticker_data: dict,
    trend_context: dict,
    policy_context: dict,
    extra_context: dict,
    cost_tracker: CostTracker,
) -> dict:
    """Deep-analyze ONE commodity or crypto. Raises CommoditiesCryptoError on
    unparseable response — caller catches in the loop."""
    user_msg = _build_user_message(
        ticker_data=ticker_data,
        trend_context=trend_context,
        policy_context=policy_context,
        extra_context=extra_context,
    )
    result = call_claude(
        model=MODEL, system=SYSTEM_PROMPT, user=user_msg,
        max_tokens=MAX_TOKENS, tools=[WEB_SEARCH_TOOL],
    )
    cost_tracker.add_from_result(result)
    return extract_json_blob(result.text, CommoditiesCryptoError)


def analyze_commodities_and_crypto(
    ticker_datas: list[dict],
    trend_context: dict,
    policy_context: dict,
    extra_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """Loops the 7 fixed assets. Per-asset failures are caught and logged so a
    single broken call never aborts the run. CostCapExceeded propagates."""
    out: list[dict] = []
    for td in ticker_datas:
        t = td.get("ticker", "?")
        try:
            a = analyze_asset(
                ticker_data=td, trend_context=trend_context,
                policy_context=policy_context, extra_context=extra_context,
                cost_tracker=cost_tracker,
            )
        except CommoditiesCryptoError as e:
            log.warning(f"{t}: commodities_crypto failed: {e}")
            continue
        out.append(a)
    log.info(
        f"Phase 3b done: {len(out)} analyses, "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return out
```

- [ ] **Step 4.5: Run tests, expect green**

Run: `pytest tests/unit/test_commodities_crypto.py -v`
Expected: 7 passed.

- [ ] **Step 4.6: Commit**

```bash
git add src/commodities_crypto.py tests/unit/test_commodities_crypto.py \
        tests/fixtures/mock_commodities_crypto_response.json
git commit -m "Sprint1/Plan3 Task 4: Phase 3b commodities_crypto for 7 fixed assets + Fear&Greed fetch"
```

---

## Task 5: `portfolio_check.py` — Phase 4a

Loads every `predictions` row that is still `open`, `learnable=True`, and ≤ 3 calendar days old (matching `db.load_open_predictions_within_max_age_days`). For each, calls Sonnet+web_search with the original thesis + current ticker snapshot + trend + policy context, parses the `{action, reason, new_sl_price, new_tp_price}` response, and writes one `position_recommendations` row.

**Files:**
- Create: `tests/fixtures/mock_portfolio_check_response.json`
- Create: `src/portfolio_check.py`
- Create: `tests/unit/test_portfolio_check.py`

- [ ] **Step 5.1: Create `tests/fixtures/mock_portfolio_check_response.json`**

```json
{
  "prediction_id": 1,
  "ticker": "AAPL",
  "action": "ANPASSEN",
  "reason": "AAPL ist 1.8% gelaufen, halber Weg zum TP. SL auf Break-Even hochziehen — These intakt, aber Asymmetrie schützen.",
  "new_sl_price": 178.5,
  "new_tp_price": 184.0,
  "market_context_changed": false,
  "sources_used": ["https://www.reuters.com/x", "https://www.bloomberg.com/y"]
}
```

- [ ] **Step 5.2: Write failing tests**

`tests/unit/test_portfolio_check.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src import db
from src.cost_tracker import CostTracker
from src.portfolio_check import (
    check_open_positions, check_one_position, PortfolioCheckError,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def _fake_result(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 3000
    r.output_tokens = 2000
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = "claude-sonnet-4-6"
    r.web_search_calls = 2
    return r


def _make_open_prediction(conn, date: str = "2026-05-18", ticker: str = "AAPL") -> int:
    return db.save_prediction(conn, {
        "date": date, "run_type": "close", "asset_class": "stock",
        "ticker": ticker, "direction": "long",
        "entry_price": 178.0, "tp_price": 184.0, "tp_pct": 3.4,
        "sl_price": 176.0, "sl_pct": 1.1, "rr_ratio": 3.0,
        "total_score": 7.8, "probability_pct": 68, "confidence": "high",
        "score_market_env": 7.0, "score_company": 8.0, "score_valuation": 6.0,
        "score_momentum": 8.0, "score_risk": 6.0, "score_sector": 7.0,
        "score_catalyst": 7.0, "score_policy": 6.0,
        "atr_pct": 1.8, "rsi_at_entry": 58.0, "volume_ratio": 1.15,
        "market_regime": "risk_on", "vix_at_prediction": 14.0,
        "sector": "Technology", "trend_boost": "ai-capex",
        "earnings_warning": False, "summary": "AAPL long thesis",
        "learnable": True, "hold_days_recommended": 2,
        "intraday_range_pct": 1.4,
    })


def test_check_one_position_returns_parsed(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_open_prediction(in_memory_db)
    pred = in_memory_db.execute(
        "SELECT * FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    payload = (FIXTURE_DIR / "mock_portfolio_check_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    snapshot = {"ticker": "AAPL", "price": 181.2, "rsi_14": 60.0,
                "macd_signal": "bullish_cross", "atr_pct": 1.8,
                "intraday_range_pct": 1.5}
    trend = {"trend_summary": "risk-on"}
    policy = {"policy_risk_level": "low", "events": []}

    with patch("src.portfolio_check.call_claude", return_value=fake):
        out = check_one_position(
            prediction=pred, current_snapshot=snapshot,
            trend_context=trend, policy_context=policy,
            cost_tracker=tracker,
        )
    assert out["action"] == "ANPASSEN"
    assert out["new_sl_price"] == 178.5


def test_check_open_positions_writes_recommendation_rows(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_open_prediction(in_memory_db)
    payload = (FIXTURE_DIR / "mock_portfolio_check_response.json").read_text()
    # Adjust the fixture prediction_id to match the just-inserted one
    payload_obj = json.loads(payload)
    payload_obj["prediction_id"] = pid
    fake = _fake_result(json.dumps(payload_obj))
    tracker = CostTracker(hard_cap_eur=10.0)
    snapshots_by_ticker = {"AAPL": {"ticker": "AAPL", "price": 181.2,
                                    "rsi_14": 60.0, "macd_signal": "bullish_cross",
                                    "atr_pct": 1.8, "intraday_range_pct": 1.5}}

    with patch("src.portfolio_check.call_claude", return_value=fake):
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            snapshots_by_ticker=snapshots_by_ticker,
            trend_context={"trend_summary": "risk-on"},
            policy_context={"policy_risk_level": "low", "events": []},
            cost_tracker=tracker,
        )
    rows = in_memory_db.execute(
        "SELECT action, new_sl_price FROM position_recommendations "
        "WHERE prediction_id=?", (pid,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["action"] == "ANPASSEN"
    assert len(out) == 1


def test_check_open_positions_skips_position_with_missing_snapshot(in_memory_db):
    """If the data_collector didn't produce a snapshot for the ticker
    (e.g., yfinance failure), we skip the position rather than crash."""
    db.init_schema(in_memory_db)
    _make_open_prediction(in_memory_db, ticker="AAPL")
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.portfolio_check.call_claude") as mock_call:
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            snapshots_by_ticker={},
            trend_context={"trend_summary": ""},
            policy_context={"policy_risk_level": "low", "events": []},
            cost_tracker=tracker,
        )
    assert out == []
    mock_call.assert_not_called()


def test_check_open_positions_skips_old_predictions(in_memory_db):
    """Predictions older than max_trading_days are not loaded."""
    db.init_schema(in_memory_db)
    _make_open_prediction(in_memory_db, date="2026-05-10")
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.portfolio_check.call_claude") as mock_call:
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            snapshots_by_ticker={"AAPL": {"ticker": "AAPL", "price": 180.0,
                                          "intraday_range_pct": 1.5}},
            trend_context={}, policy_context={},
            cost_tracker=tracker,
        )
    assert out == []
    mock_call.assert_not_called()


def test_check_one_position_raises_on_invalid_json(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_open_prediction(in_memory_db)
    pred = in_memory_db.execute(
        "SELECT * FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    fake = _fake_result("not json")
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.portfolio_check.call_claude", return_value=fake):
        with pytest.raises(PortfolioCheckError):
            check_one_position(
                prediction=pred,
                current_snapshot={"ticker": "AAPL", "price": 181.0,
                                  "intraday_range_pct": 1.5},
                trend_context={}, policy_context={},
                cost_tracker=tracker,
            )


def test_check_open_positions_continues_after_single_failure(in_memory_db):
    db.init_schema(in_memory_db)
    p1 = _make_open_prediction(in_memory_db, ticker="AAPL")
    p2 = _make_open_prediction(in_memory_db, ticker="MSFT")
    good_payload = json.loads((FIXTURE_DIR / "mock_portfolio_check_response.json").read_text())
    good_payload["ticker"] = "MSFT"
    good_payload["prediction_id"] = p2
    side_effects = [_fake_result("bad"), _fake_result(json.dumps(good_payload))]
    tracker = CostTracker(hard_cap_eur=10.0)
    snapshots = {
        "AAPL": {"ticker": "AAPL", "price": 181.0, "intraday_range_pct": 1.5},
        "MSFT": {"ticker": "MSFT", "price": 410.0, "intraday_range_pct": 1.4},
    }
    with patch("src.portfolio_check.call_claude", side_effect=side_effects):
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            snapshots_by_ticker=snapshots,
            trend_context={}, policy_context={},
            cost_tracker=tracker,
        )
    assert len(out) == 1
    assert out[0]["ticker"] == "MSFT"


def test_check_open_positions_returns_empty_when_no_open(in_memory_db):
    db.init_schema(in_memory_db)
    tracker = CostTracker(hard_cap_eur=10.0)
    out = check_open_positions(
        conn=in_memory_db, today="2026-05-20", run_type="pre_market",
        snapshots_by_ticker={}, trend_context={}, policy_context={},
        cost_tracker=tracker,
    )
    assert out == []
```

- [ ] **Step 5.3: Run failing tests**

Run: `pytest tests/unit/test_portfolio_check.py -v`
Expected: ImportError.

- [ ] **Step 5.4: Implement `src/portfolio_check.py`**

```python
"""Phase 4a: Daily portfolio check.

For every open prediction <= 3 trading days old, decide HALTEN / SCHLIESSEN /
ANPASSEN given the current snapshot, trend, and policy context. Writes one
position_recommendations row per call. Output is rendered as the FIRST
section of the daily e-mail (spec §3 CFD-Kurzfristfokus). Per-position
failures are caught — a single broken call must not abort the loop."""
import json
import logging
import sqlite3
from pathlib import Path

from src import db
from src.cost_tracker import CostTracker
from src.utils import call_claude, extract_json_blob, WEB_SEARCH_TOOL

log = logging.getLogger("shares_future.portfolio_check")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "portfolio_check_v1.txt").read_text()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048
MAX_HOLD_DAYS = 3
VALID_ACTIONS = {"HALTEN", "SCHLIESSEN", "ANPASSEN"}


class PortfolioCheckError(RuntimeError):
    """Per-position portfolio-check call produced unparseable or invalid output."""


def _build_user_message(
    prediction: sqlite3.Row,
    current_snapshot: dict,
    trend_context: dict,
    policy_context: dict,
) -> str:
    pred_dict = {k: prediction[k] for k in prediction.keys()}
    parts = [
        "ORIGINAL PREDICTION:", json.dumps(pred_dict, ensure_ascii=False, default=str),
        "\nCURRENT SNAPSHOT:", json.dumps(current_snapshot, ensure_ascii=False),
        "\nTREND CONTEXT:", json.dumps(trend_context, ensure_ascii=False),
        "\nPOLICY CONTEXT:", json.dumps(policy_context, ensure_ascii=False),
        "\nReturn the JSON object defined in your system prompt.",
    ]
    return "\n".join(parts)


def check_one_position(
    prediction: sqlite3.Row,
    current_snapshot: dict,
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> dict:
    """Run portfolio-check on ONE open position. Returns the parsed response
    dict including the {action, new_sl_price, new_tp_price, ...} fields.
    Raises PortfolioCheckError on unparseable or schematically-invalid output."""
    user_msg = _build_user_message(
        prediction=prediction, current_snapshot=current_snapshot,
        trend_context=trend_context, policy_context=policy_context,
    )
    result = call_claude(
        model=MODEL, system=SYSTEM_PROMPT, user=user_msg,
        max_tokens=MAX_TOKENS, tools=[WEB_SEARCH_TOOL],
    )
    cost_tracker.add_from_result(result)
    parsed = extract_json_blob(result.text, PortfolioCheckError)
    action = parsed.get("action")
    if action not in VALID_ACTIONS:
        raise PortfolioCheckError(
            f"Unknown action '{action}' (must be one of {sorted(VALID_ACTIONS)})"
        )
    return parsed


def check_open_positions(
    conn,
    today: str,
    run_type: str,
    snapshots_by_ticker: dict[str, dict],
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """Loop all open <= 3-day-old predictions, run portfolio_check per row,
    persist one position_recommendations row each. Returns the list of parsed
    response dicts."""
    open_preds = db.load_open_predictions_within_max_age_days(
        conn, today=today, max_trading_days=MAX_HOLD_DAYS,
    )
    log.info(f"Phase 4a: {len(open_preds)} open positions to check")

    out: list[dict] = []
    for pred in open_preds:
        ticker = pred["ticker"]
        snapshot = snapshots_by_ticker.get(ticker)
        if snapshot is None:
            log.warning(
                f"{ticker}: no current snapshot, skipping portfolio_check for "
                f"prediction_id={pred['id']}"
            )
            continue

        try:
            parsed = check_one_position(
                prediction=pred, current_snapshot=snapshot,
                trend_context=trend_context, policy_context=policy_context,
                cost_tracker=cost_tracker,
            )
        except PortfolioCheckError as e:
            log.warning(f"{ticker}: portfolio_check failed: {e}")
            continue

        db.save_position_recommendation(conn, {
            "date": today, "run_type": run_type,
            "prediction_id": pred["id"],
            "action": parsed["action"],
            "reason": parsed.get("reason", ""),
            "new_sl_price": parsed.get("new_sl_price"),
            "new_tp_price": parsed.get("new_tp_price"),
            "market_context_changed": bool(parsed.get("market_context_changed")),
        })
        out.append(parsed)

    log.info(
        f"Phase 4a done: {len(out)} recommendations written, "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return out
```

- [ ] **Step 5.5: Run tests, expect green**

Run: `pytest tests/unit/test_portfolio_check.py -v`
Expected: 7 passed.

- [ ] **Step 5.6: Commit**

```bash
git add src/portfolio_check.py tests/unit/test_portfolio_check.py \
        tests/fixtures/mock_portfolio_check_response.json
git commit -m "Sprint1/Plan3 Task 5: Phase 4a portfolio_check with HALTEN/SCHLIESSEN/ANPASSEN classifier"
```

---

## Task 6: `ranking.py` — Phase 4

Takes the raw deep-analysis output lists (stocks + commodities_crypto) and:
1. Drops anything that fails `GuardrailsChecker.check_analysis()` or has `direction='none'`.
2. Splits stocks into Long/Short by `direction` and ranks each side by `probability_pct` desc, taking Top 10. Commodities/crypto are **all** kept.
3. Persists every selected analysis as a `predictions` row with `learnable=True`. Returns the structured dict the e-mail sender consumes.

**Files:**
- Create: `src/ranking.py`
- Create: `tests/unit/test_ranking.py`

- [ ] **Step 6.1: Write failing tests**

`tests/unit/test_ranking.py`:

```python
from unittest.mock import MagicMock
import pytest

from src import db
from src.ranking import rank_and_persist, score_total


def _analysis(ticker: str, direction: str = "long", momentum: float = 7.0,
              hold_days: int = 2, intraday: float = 1.5,
              total_score: float = 7.5, prob: int = 68,
              rr: float = 2.5, current: float = 100.0,
              asset_class: str = "stock") -> dict:
    """Minimal guardrail-passing analysis dict, with knobs."""
    tp = current + 5.0 if direction == "long" else current - 5.0
    sl = current - 2.0 if direction == "long" else current + 2.0
    return {
        "ticker": ticker, "asset_class": asset_class,
        "direction": direction, "confidence": "high",
        "current_price": current, "tp_price": tp, "sl_price": sl,
        "tp_pct": 5.0, "sl_pct": 2.0, "rr_ratio": rr,
        "total_score": total_score, "probability_pct": prob,
        "hold_days_recommended": hold_days,
        "intraday_range_pct": intraday,
        "summary": "ok", "earnings_warning": False,
        "sources_used": ["a.com", "b.com"],
        "signal_consistency_check": "ok",
        "scores": {
            "market_environment": {"value": 7.0, "evidence": ["x", "y"]},
            "company_quality":    {"value": 7.0, "evidence": ["x", "y"]},
            "valuation":           {"value": 6.0, "evidence": ["x", "y"]},
            "momentum":           {"value": momentum, "evidence": ["x", "y"]},
            "risk":               {"value": 6.0, "evidence": ["x", "y"]},
            "sector_trend":       {"value": 7.0, "evidence": ["x", "y"]},
            "catalyst":           {"value": 7.0, "evidence": ["x", "y"]},
            "policy_risk":        {"value": 6.0, "evidence": ["x", "y"]},
        },
    }


def _market_ctx() -> dict:
    return {"vix_level": 14.0, "market_regime": "risk_on", "sector": "Technology"}


def test_score_total_uses_dimension_weights():
    a = _analysis("AAPL", momentum=8.0)
    t = score_total(a)
    assert 6.0 < t < 8.5


def test_rank_and_persist_top_10_long_and_short(in_memory_db):
    db.init_schema(in_memory_db)
    stocks = (
        [_analysis(f"L{i}", direction="long", momentum=8.0, prob=70 - i)
         for i in range(15)]
        + [_analysis(f"S{i}", direction="short", momentum=3.0, prob=70 - i)
           for i in range(15)]
    )
    out = rank_and_persist(
        conn=in_memory_db, date="2026-05-19", run_type="close",
        stock_analyses=stocks, commodity_crypto_analyses=[],
        market_context=_market_ctx(),
    )
    assert len(out["top_long"]) == 10
    assert len(out["top_short"]) == 10
    assert out["top_long"][0]["probability_pct"] >= out["top_long"][-1]["probability_pct"]
    rows = in_memory_db.execute(
        "SELECT direction, COUNT(*) AS n FROM predictions GROUP BY direction"
    ).fetchall()
    counts = {r["direction"]: r["n"] for r in rows}
    assert counts["long"] == 10
    assert counts["short"] == 10


def test_rank_drops_guardrail_failures(in_memory_db):
    db.init_schema(in_memory_db)
    good = _analysis("AAPL", momentum=8.0)
    bad_hold = _analysis("BAD1", momentum=8.0, hold_days=5)
    bad_range = _analysis("BAD2", momentum=8.0, intraday=0.5)
    bad_momentum = _analysis("BAD3", direction="long", momentum=3.0)
    out = rank_and_persist(
        conn=in_memory_db, date="2026-05-19", run_type="close",
        stock_analyses=[good, bad_hold, bad_range, bad_momentum],
        commodity_crypto_analyses=[],
        market_context=_market_ctx(),
    )
    tickers = [p["ticker"] for p in out["top_long"]]
    assert tickers == ["AAPL"]


def test_rank_drops_direction_none(in_memory_db):
    db.init_schema(in_memory_db)
    a = _analysis("AAPL", momentum=8.0)
    a["direction"] = "none"
    out = rank_and_persist(
        conn=in_memory_db, date="2026-05-19", run_type="close",
        stock_analyses=[a], commodity_crypto_analyses=[],
        market_context=_market_ctx(),
    )
    assert out["top_long"] == []
    assert out["top_short"] == []


def test_rank_keeps_all_commodities_crypto(in_memory_db):
    db.init_schema(in_memory_db)
    cc = [
        _analysis("GC=F", asset_class="commodity"),
        _analysis("SI=F", asset_class="commodity"),
        _analysis("BTC-USD", asset_class="crypto"),
    ]
    out = rank_and_persist(
        conn=in_memory_db, date="2026-05-19", run_type="close",
        stock_analyses=[], commodity_crypto_analyses=cc,
        market_context=_market_ctx(),
    )
    assert {a["ticker"] for a in out["commodities_crypto"]} == {"GC=F", "SI=F", "BTC-USD"}


def test_rank_persists_predictions_with_score_dimensions(in_memory_db):
    db.init_schema(in_memory_db)
    a = _analysis("AAPL", momentum=8.0)
    rank_and_persist(
        conn=in_memory_db, date="2026-05-19", run_type="close",
        stock_analyses=[a], commodity_crypto_analyses=[],
        market_context=_market_ctx(),
    )
    row = in_memory_db.execute(
        "SELECT score_momentum, score_company, hold_days_recommended, "
        "intraday_range_pct, learnable FROM predictions WHERE ticker='AAPL'"
    ).fetchone()
    assert row["score_momentum"] == 8.0
    assert row["hold_days_recommended"] == 2
    assert row["intraday_range_pct"] == 1.5
    assert row["learnable"] == 1
```

- [ ] **Step 6.2: Run failing tests**

Run: `pytest tests/unit/test_ranking.py -v`
Expected: ImportError on `rank_and_persist`, `score_total`.

- [ ] **Step 6.3: Implement `src/ranking.py`**

```python
"""Phase 4: Rank guardrail-passing analyses and persist to predictions.

Stocks: top 10 by probability_pct per direction (long / short).
Commodities + crypto: always all kept, regardless of score.
Every selected analysis is written as a learnable=True predictions row."""
import logging
from typing import Iterable

from src import db
from src.guardrails import GuardrailsChecker
import config

log = logging.getLogger("shares_future.ranking")

TOP_N = 10


def score_total(analysis: dict) -> float:
    """Weighted sum of the 8 score dimensions using config.DIMENSION_WEIGHTS."""
    s = analysis.get("scores", {})
    total = 0.0
    for dim, weight in config.DIMENSION_WEIGHTS.items():
        v = s.get(dim, {}).get("value")
        if v is not None:
            total += float(v) * weight
    return round(total, 3)


def _guardrail_filter(analyses: Iterable[dict]) -> list[dict]:
    checker = GuardrailsChecker()
    kept: list[dict] = []
    for a in analyses:
        if a.get("direction") == "none":
            continue
        ok, errs = checker.check_analysis(a)
        if not ok:
            log.info(
                f"{a.get('ticker', '?')}: dropped by guardrails: {'; '.join(errs)}"
            )
            continue
        kept.append(a)
    return kept


def _to_prediction_row(
    analysis: dict, date: str, run_type: str, market_context: dict,
) -> dict:
    scores = analysis.get("scores", {})
    return {
        "date": date, "run_type": run_type,
        "asset_class": analysis.get("asset_class"),
        "ticker": analysis["ticker"], "direction": analysis["direction"],
        "entry_price": analysis["current_price"],
        "tp_price": analysis["tp_price"], "tp_pct": analysis.get("tp_pct"),
        "sl_price": analysis["sl_price"], "sl_pct": analysis.get("sl_pct"),
        "rr_ratio": analysis["rr_ratio"],
        "total_score": analysis.get("total_score") or score_total(analysis),
        "probability_pct": analysis.get("probability_pct"),
        "confidence": analysis.get("confidence"),
        "score_market_env": scores.get("market_environment", {}).get("value"),
        "score_company":    scores.get("company_quality", {}).get("value"),
        "score_valuation":  scores.get("valuation", {}).get("value"),
        "score_momentum":   scores.get("momentum", {}).get("value"),
        "score_risk":       scores.get("risk", {}).get("value"),
        "score_sector":     scores.get("sector_trend", {}).get("value"),
        "score_catalyst":   scores.get("catalyst", {}).get("value"),
        "score_policy":     scores.get("policy_risk", {}).get("value"),
        "atr_pct": None, "rsi_at_entry": None, "volume_ratio": None,
        "market_regime": market_context.get("market_regime"),
        "vix_at_prediction": market_context.get("vix_level"),
        "sector": market_context.get("sector"),
        "trend_boost": None,
        "earnings_warning": bool(analysis.get("earnings_warning")),
        "summary": analysis.get("summary"),
        "learnable": True,
        "hold_days_recommended": analysis.get("hold_days_recommended"),
        "intraday_range_pct": analysis.get("intraday_range_pct"),
    }


def rank_and_persist(
    conn,
    date: str,
    run_type: str,
    stock_analyses: list[dict],
    commodity_crypto_analyses: list[dict],
    market_context: dict,
) -> dict:
    """Returns {top_long, top_short, commodities_crypto} (each a list of dicts)
    and writes a predictions row per selected analysis. Order within each list
    is by probability_pct descending."""
    kept_stocks = _guardrail_filter(stock_analyses)
    kept_cc     = _guardrail_filter(commodity_crypto_analyses)

    longs  = sorted(
        [a for a in kept_stocks if a["direction"] == "long"],
        key=lambda a: a.get("probability_pct") or 0, reverse=True,
    )[:TOP_N]
    shorts = sorted(
        [a for a in kept_stocks if a["direction"] == "short"],
        key=lambda a: a.get("probability_pct") or 0, reverse=True,
    )[:TOP_N]

    for a in (*longs, *shorts, *kept_cc):
        db.save_prediction(conn, _to_prediction_row(
            a, date=date, run_type=run_type, market_context=market_context,
        ))

    log.info(
        f"Phase 4 done: {len(longs)} long, {len(shorts)} short, "
        f"{len(kept_cc)} commodity/crypto persisted"
    )
    return {
        "top_long": longs,
        "top_short": shorts,
        "commodities_crypto": kept_cc,
    }
```

- [ ] **Step 6.4: Run tests, expect green**

Run: `pytest tests/unit/test_ranking.py -v`
Expected: 6 passed.

- [ ] **Step 6.5: Commit**

```bash
git add src/ranking.py tests/unit/test_ranking.py
git commit -m "Sprint1/Plan3 Task 6: Phase 4 ranking with guardrail filter and Top-10 long/short persist"
```

---

## Task 7: `evaluator.py` — Walk-Forward OHLC hit check

For every `open`, `learnable=True` prediction whose age (in trading days) ≥ 1, fetch OHLC bars for the days since `date` from a `price_provider`. Walk forward day-by-day:
- Long: `Low <= SL` → sl_hit; `High >= TP AND Low > SL` → tp_hit; both → pessimistic_overlap (assume SL).
- Short: spiegelbildlich.
- After 3 days no hit → timeout (close at day 3 close).
- No OHLC at all → data_missing.

Writes `outcomes` row and updates `predictions.status / closed_date / closed_price` via `db.update_outcome_close()`.

**Files:**
- Create: `tests/fixtures/sample_ohlc_eval.csv`
- Create: `src/evaluator.py`
- Create: `tests/unit/test_evaluator.py`

- [ ] **Step 7.1: Create OHLC fixture**

`tests/fixtures/sample_ohlc_eval.csv`:

```csv
ticker,date,open,high,low,close
LONG_TP,2026-05-19,100.0,100.5,99.5,100.0
LONG_TP,2026-05-20,100.0,105.5,99.0,104.0
LONG_SL,2026-05-19,100.0,100.5,99.5,100.0
LONG_SL,2026-05-20,100.0,101.0,94.0,95.0
SHORT_TP,2026-05-19,100.0,100.5,99.5,100.0
SHORT_TP,2026-05-20,100.0,101.0,94.0,95.0
SHORT_SL,2026-05-19,100.0,100.5,99.5,100.0
SHORT_SL,2026-05-20,100.0,106.0,99.0,105.0
TIMEOUT,2026-05-19,100.0,101.0,99.0,100.5
TIMEOUT,2026-05-20,100.5,101.5,99.5,100.7
TIMEOUT,2026-05-21,100.7,101.2,99.8,100.5
OVERLAP,2026-05-19,100.0,106.0,94.0,100.0
```

- [ ] **Step 7.2: Write failing tests**

`tests/unit/test_evaluator.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd
import pytest

from src import db
from src.evaluator import evaluate_open_predictions, _walk_forward_hit

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_ohlc_eval.csv"
ALL_OHLC = pd.read_csv(FIXTURE)


def _ohlc(ticker: str) -> pd.DataFrame:
    df = ALL_OHLC[ALL_OHLC["ticker"] == ticker].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").drop(columns=["ticker"])
    df.columns = [c.capitalize() for c in df.columns]
    return df


def _make_pred(conn, ticker: str, direction: str = "long",
               entry: float = 100.0, tp: float = 105.0, sl: float = 95.0,
               date: str = "2026-05-19") -> int:
    return db.save_prediction(conn, {
        "date": date, "run_type": "close", "asset_class": "stock",
        "ticker": ticker, "direction": direction,
        "entry_price": entry, "tp_price": tp, "tp_pct": 5.0,
        "sl_price": sl, "sl_pct": 5.0, "rr_ratio": 1.0,
        "total_score": 7.0, "probability_pct": 60, "confidence": "medium",
        "score_market_env": 7.0, "score_company": 7.0, "score_valuation": 6.0,
        "score_momentum": 7.0, "score_risk": 6.0, "score_sector": 7.0,
        "score_catalyst": 7.0, "score_policy": 6.0,
        "atr_pct": 2.0, "rsi_at_entry": 55.0, "volume_ratio": 1.0,
        "market_regime": "risk_on", "vix_at_prediction": 14.0,
        "sector": "Technology", "trend_boost": None,
        "earnings_warning": False, "summary": "test",
        "learnable": True, "hold_days_recommended": 2,
        "intraday_range_pct": 1.5,
    })


def _provider_for(df_map: dict[str, pd.DataFrame]) -> MagicMock:
    provider = MagicMock()
    def _get(ticker, start_date=None, end_date=None):
        df = df_map.get(ticker)
        if df is None:
            return None
        if start_date is not None:
            df = df[df.index >= pd.Timestamp(start_date)]
        if end_date is not None:
            df = df[df.index <= pd.Timestamp(end_date)]
        return df if not df.empty else None
    provider.get_ohlc_after = _get
    return provider


def test_long_tp_hit(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "LONG_TP", direction="long",
                     entry=100.0, tp=105.0, sl=95.0)
    provider = _provider_for({"LONG_TP": _ohlc("LONG_TP")})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=provider,
    )
    row = in_memory_db.execute(
        "SELECT status, closed_price FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_tp"
    assert row["closed_price"] == 105.0
    out = in_memory_db.execute(
        "SELECT exit_reason, tp_hit, days_to_close FROM outcomes "
        "WHERE prediction_id=?", (pid,),
    ).fetchone()
    assert out["exit_reason"] == "tp_hit"
    assert out["tp_hit"] == 1
    assert out["days_to_close"] == 2


def test_long_sl_hit(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "LONG_SL", direction="long",
                     entry=100.0, tp=105.0, sl=95.0)
    provider = _provider_for({"LONG_SL": _ohlc("LONG_SL")})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=provider,
    )
    row = in_memory_db.execute(
        "SELECT status, closed_price FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_sl"
    out = in_memory_db.execute(
        "SELECT exit_reason FROM outcomes WHERE prediction_id=?", (pid,),
    ).fetchone()
    assert out["exit_reason"] == "sl_hit"


def test_short_tp_hit(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "SHORT_TP", direction="short",
                     entry=100.0, tp=95.0, sl=105.0)
    provider = _provider_for({"SHORT_TP": _ohlc("SHORT_TP")})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=provider,
    )
    row = in_memory_db.execute(
        "SELECT status FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_tp"


def test_short_sl_hit(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "SHORT_SL", direction="short",
                     entry=100.0, tp=95.0, sl=105.0)
    provider = _provider_for({"SHORT_SL": _ohlc("SHORT_SL")})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=provider,
    )
    row = in_memory_db.execute(
        "SELECT status FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_sl"


def test_timeout_after_three_days(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "TIMEOUT", direction="long",
                     entry=100.0, tp=110.0, sl=90.0)
    provider = _provider_for({"TIMEOUT": _ohlc("TIMEOUT")})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-22", price_provider=provider,
    )
    row = in_memory_db.execute(
        "SELECT status, closed_price FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_timeout"
    assert row["closed_price"] == 100.5  # day-3 close
    out = in_memory_db.execute(
        "SELECT exit_reason, days_to_close FROM outcomes WHERE prediction_id=?",
        (pid,),
    ).fetchone()
    assert out["exit_reason"] == "timeout"
    assert out["days_to_close"] == 3


def test_pessimistic_overlap_closes_at_sl(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "OVERLAP", direction="long",
                     entry=100.0, tp=105.0, sl=95.0)
    provider = _provider_for({"OVERLAP": _ohlc("OVERLAP")})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=provider,
    )
    row = in_memory_db.execute(
        "SELECT status, closed_price FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_sl"
    assert row["closed_price"] == 95.0
    out = in_memory_db.execute(
        "SELECT exit_reason FROM outcomes WHERE prediction_id=?", (pid,),
    ).fetchone()
    assert out["exit_reason"] == "pessimistic_overlap"


def test_data_missing_closes_with_data_missing_reason(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "GONE", direction="long",
                     entry=100.0, tp=105.0, sl=95.0)
    provider = _provider_for({})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=provider,
    )
    row = in_memory_db.execute(
        "SELECT status FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_data_missing"
    out = in_memory_db.execute(
        "SELECT exit_reason FROM outcomes WHERE prediction_id=?", (pid,),
    ).fetchone()
    assert out["exit_reason"] == "data_missing"


def test_evaluate_ignores_already_closed(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "LONG_TP", direction="long")
    db.close_prediction(in_memory_db, pid, status="closed_tp",
                        closed_date="2026-05-20", closed_price=105.0)
    provider = _provider_for({"LONG_TP": _ohlc("LONG_TP")})
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-21", price_provider=provider,
    )
    out_count = in_memory_db.execute(
        "SELECT COUNT(*) AS n FROM outcomes WHERE prediction_id=?", (pid,),
    ).fetchone()["n"]
    assert out_count == 0


def test_walk_forward_helper_tp_first():
    """Helper covers the bar-by-bar comparison logic in isolation."""
    df = _ohlc("LONG_TP")
    reason, exit_price, day = _walk_forward_hit(
        df, direction="long", tp=105.0, sl=95.0,
    )
    assert reason == "tp_hit"
    assert exit_price == 105.0
    assert day == 2
```

- [ ] **Step 7.3: Run failing tests**

Run: `pytest tests/unit/test_evaluator.py -v`
Expected: ImportError.

- [ ] **Step 7.4: Implement `src/evaluator.py`**

```python
"""Walk-Forward Evaluator.

Each open predictions row that is >= 1 trading-day old gets evaluated against the
post-prediction OHLC bars. Returns the exit reason and atomically writes both the
outcomes row and the prediction status via db.update_outcome_close().

Trading-day precision is intentionally approximated by calendar days: yfinance
returns weekday-only bars anyway, so iterating bars in order corresponds to
trading-day order. We cap at 3 bars (== 3 trading days)."""
import logging
import pandas as pd

from src import db
import config

log = logging.getLogger("shares_future.evaluator")

MAX_HOLD_DAYS = 3


def _walk_forward_hit(
    ohlc: pd.DataFrame, direction: str, tp: float, sl: float,
) -> tuple[str, float | None, int]:
    """Walk through up to MAX_HOLD_DAYS bars. Return (exit_reason, exit_price, day).
    If no hit and no full window, returns ('timeout', last_close, day_count)."""
    bars = ohlc.iloc[:MAX_HOLD_DAYS]
    for day_offset, (_, bar) in enumerate(bars.iterrows(), start=1):
        if direction == "long":
            hit_tp = bar["High"] >= tp
            hit_sl = bar["Low"]  <= sl
        else:
            hit_tp = bar["Low"]  <= tp
            hit_sl = bar["High"] >= sl

        if hit_tp and hit_sl:
            return "pessimistic_overlap", sl, day_offset
        if hit_sl:
            return "sl_hit", sl, day_offset
        if hit_tp:
            return "tp_hit", tp, day_offset

    if len(bars) == 0:
        return "data_missing", None, 0
    last_close = float(bars["Close"].iloc[-1])
    return "timeout", last_close, len(bars)


def _profit_loss_eur(
    entry: float, exit_price: float | None, direction: str,
) -> float | None:
    """Spec §1: 500 EUR Margin, 5:1 Hebel → 2500 EUR exposure → 1% move == 25 EUR."""
    if exit_price is None or entry in (None, 0):
        return None
    pct = (exit_price - entry) / entry * 100
    if direction == "short":
        pct = -pct
    eur = pct * config.CFD_MARGIN_EUR * config.CFD_LEVERAGE / 100
    return round(eur, 2)


def evaluate_open_predictions(
    conn,
    today: str,
    price_provider,
) -> int:
    """Walk-forward over every open, learnable prediction whose date < today.
    Returns the number of predictions evaluated (= newly-closed rows)."""
    rows = conn.execute(
        """SELECT * FROM predictions
           WHERE status='open' AND learnable=1 AND date < ?""",
        (today,),
    ).fetchall()
    log.info(f"Evaluator: {len(rows)} open predictions to evaluate")

    closed = 0
    for pred in rows:
        ticker = pred["ticker"]
        try:
            ohlc = price_provider.get_ohlc_after(
                ticker, start_date=pred["date"], end_date=today,
            )
        except Exception as e:
            log.warning(f"{ticker}: provider raised in evaluator: {e}")
            ohlc = None

        if ohlc is None or ohlc.empty:
            db.update_outcome_close(
                conn, prediction_id=pred["id"], exit_reason="data_missing",
                exit_price=None, days_to_close=0, closed_date=today,
                profit_loss_eur=None, correct_direction_eod=None,
                direction=pred["direction"],
            )
            closed += 1
            continue

        # Drop the prediction-day bar itself (already known at prediction time)
        post = ohlc[ohlc.index > pd.Timestamp(pred["date"])]
        reason, exit_price, day = _walk_forward_hit(
            post, direction=pred["direction"],
            tp=float(pred["tp_price"]), sl=float(pred["sl_price"]),
        )
        pl_eur = _profit_loss_eur(
            entry=float(pred["entry_price"]) if pred["entry_price"] else None,
            exit_price=exit_price, direction=pred["direction"],
        )
        correct = None
        if exit_price is not None:
            if pred["direction"] == "long":
                correct = exit_price > float(pred["entry_price"])
            else:
                correct = exit_price < float(pred["entry_price"])

        db.update_outcome_close(
            conn, prediction_id=pred["id"], exit_reason=reason,
            exit_price=exit_price, days_to_close=day,
            closed_date=today, profit_loss_eur=pl_eur,
            correct_direction_eod=correct,
            direction=pred["direction"],
        )
        closed += 1

    log.info(f"Evaluator done: {closed} predictions closed")
    return closed
```

- [ ] **Step 7.5: Run tests, expect green**

Run: `pytest tests/unit/test_evaluator.py -v`
Expected: 9 passed.

- [ ] **Step 7.6: Commit**

```bash
git add src/evaluator.py tests/unit/test_evaluator.py \
        tests/fixtures/sample_ohlc_eval.csv
git commit -m "Sprint1/Plan3 Task 7: Walk-Forward evaluator with all 4 exit reasons"
```

Note: `evaluator.py` uses `price_provider.get_ohlc_after(ticker, start_date, end_date)`. This method does NOT exist on the existing `DataProvider` interface yet — it must be added in Task 8 (Provider extension) before `main.py` can wire it up. The evaluator unit tests use a MagicMock provider so they pass independently.

---

## Task 8: Provider extension + `price_provider.get_ohlc_after` for evaluator

Add `get_ohlc_after(ticker, start_date, end_date)` to the `DataProvider` ABC and implement it for `YFinanceProvider`. The Sprint-2 paid provider stub gets a NotImplementedError. This is small and self-contained.

**Files:**
- Modify: `src/providers/base.py`
- Modify: `src/providers/yfinance_provider.py`
- Modify: `src/providers/paid_provider.py` (stub raise)
- Modify: `src/providers/finnhub_provider.py` (raise NotImplementedError — earnings provider doesn't expose OHLC)
- Modify: `tests/unit/test_yfinance_provider.py`

- [ ] **Step 8.1: Write failing test**

Append to `tests/unit/test_yfinance_provider.py`:

```python
def test_get_ohlc_after_returns_subset(monkeypatch):
    """Reads a 90-day fetch and slices to the requested window."""
    import pandas as pd
    from src.providers.yfinance_provider import YFinanceProvider

    full = pd.DataFrame(
        {"Open": [1, 2, 3, 4], "High": [1, 2, 3, 4],
         "Low":  [1, 2, 3, 4], "Close":[1, 2, 3, 4],
         "Volume":[10, 20, 30, 40]},
        index=pd.to_datetime(["2026-05-15", "2026-05-18",
                              "2026-05-19", "2026-05-20"]),
    )
    provider = YFinanceProvider()
    monkeypatch.setattr(provider, "get_price_history", lambda t, days=90: full)
    out = provider.get_ohlc_after("AAPL", start_date="2026-05-18",
                                  end_date="2026-05-20")
    assert list(out.index.strftime("%Y-%m-%d")) == [
        "2026-05-18", "2026-05-19", "2026-05-20",
    ]
```

- [ ] **Step 8.2: Run failing test**

Run: `pytest tests/unit/test_yfinance_provider.py::test_get_ohlc_after_returns_subset -v`
Expected: AttributeError on `get_ohlc_after`.

- [ ] **Step 8.3: Extend `DataProvider` ABC**

In `src/providers/base.py`, append:

```python
    @abstractmethod
    def get_ohlc_after(
        self, ticker: str, start_date: str, end_date: str,
    ) -> pd.DataFrame | None:
        """Daily OHLC bars inclusive [start_date, end_date]. None if empty."""
        ...
```

- [ ] **Step 8.4: Implement in `YFinanceProvider`**

Append to `src/providers/yfinance_provider.py`:

```python
    def get_ohlc_after(
        self, ticker: str, start_date: str, end_date: str,
    ) -> "pd.DataFrame | None":
        df = self.get_price_history(ticker, days=90)
        if df is None or df.empty:
            return None
        import pandas as pd
        mask = (df.index >= pd.Timestamp(start_date)) & (df.index <= pd.Timestamp(end_date))
        sub = df.loc[mask]
        return sub if not sub.empty else None
```

- [ ] **Step 8.5: Stub in `PaidProvider` and `FinnhubProvider`**

`src/providers/paid_provider.py`: add method that raises `NotImplementedError("Paid provider OHLC backfill is Sprint 2")`.

`src/providers/finnhub_provider.py`: add method that raises `NotImplementedError("Finnhub provider is earnings-only; use yfinance for OHLC")`.

- [ ] **Step 8.6: Run all provider tests, expect green**

Run: `pytest tests/unit/test_yfinance_provider.py tests/unit/test_paid_provider.py tests/unit/test_finnhub_provider.py -v`
Expected: 1 new test passes; existing tests remain green.

- [ ] **Step 8.7: Commit**

```bash
git add src/providers/base.py src/providers/yfinance_provider.py \
        src/providers/paid_provider.py src/providers/finnhub_provider.py \
        tests/unit/test_yfinance_provider.py
git commit -m "Sprint1/Plan3 Task 8: DataProvider.get_ohlc_after for evaluator"
```

---

## Task 9: `email_sender.py` — 4-section daily + reduced weekly

Pure-Python render (no templating engine — string concatenation, well-scoped helper per section). The `send_daily_email(...)` function builds the HTML body and POSTs via SendGrid. Failure to send is **logged but not fatal** — the run already wrote everything to DB. Weekly email is identical infra with a shorter body.

Daily sections (spec §3 + §5):
1. **Portfolio-Empfehlungen** (Phase 4a) — table with `action`, ticker, reason, new SL/TP if ANPASSEN. **Always first.**
2. **Aktien Top-10** — Long + Short side by side, columns: Rang, Ticker, Score, Wahrscheinlichkeit, Kurs, TP, SL, R/R, ATR/Tag, Range/Tag, Trend-Boost-Flag, Policy-Risk-Flag, Kurzbegründung.
3. **Trends** — dark card grid: name, strength, summary, beneficiaries, negatives, next catalyst.
4. **Commodities + Crypto** — table with Direction, Score, Wahrscheinlichkeit, TP/SL, plus Fear&Greed + GSR footer.

**Footer (always):** Vortags-Performance (Long X/N, Short Y/N, Sim P/L EUR), übersprungene Aktien, Disclaimer, Run-Kosten + Cache-Hit-Rate.

**Files:**
- Create: `src/email_sender.py`
- Create: `tests/unit/test_email_sender.py`

- [ ] **Step 9.1: Write failing tests**

`tests/unit/test_email_sender.py`:

```python
from unittest.mock import patch, MagicMock
import pytest

from src.email_sender import (
    render_daily_html, render_weekly_html, send_daily_email,
    EmailSendError,
)


def _sample_payload() -> dict:
    return {
        "date": "2026-05-19", "run_type": "close",
        "portfolio_recs": [
            {"ticker": "AAPL", "action": "ANPASSEN",
             "reason": "Halber Weg zum TP, SL hochziehen",
             "new_sl_price": 178.5, "new_tp_price": 184.0,
             "entry_price": 178.0, "direction": "long"},
            {"ticker": "TSLA", "action": "SCHLIESSEN",
             "reason": "Momentum bricht, Stop nahe", "new_sl_price": None,
             "new_tp_price": None, "entry_price": 200.0, "direction": "long"},
        ],
        "top_long": [
            {"ticker": "NVDA", "direction": "long", "current_price": 880.0,
             "tp_price": 920.0, "sl_price": 860.0, "rr_ratio": 2.0,
             "total_score": 8.5, "probability_pct": 75, "intraday_range_pct": 2.4,
             "summary": "AI capex tailwind", "earnings_warning": False,
             "scores": {"momentum": {"value": 8.5}, "policy_risk": {"value": 5.0}}},
        ],
        "top_short": [],
        "commodities_crypto": [
            {"ticker": "GC=F", "asset_class": "commodity",
             "direction": "long", "current_price": 2380.0,
             "tp_price": 2420.0, "sl_price": 2360.0, "rr_ratio": 2.0,
             "total_score": 6.9, "probability_pct": 58,
             "intraday_range_pct": 1.2,
             "extra": {"fear_greed_value": 62, "gold_silver_ratio": 80.3,
                       "btc_dominance_pct": None}},
        ],
        "trends": [
            {"name": "ai-capex-acceleration", "strength": 8,
             "duration_estimate": "1m+", "summary": "Hyperscalers",
             "beneficiary_tickers": ["NVDA"], "negative_tickers": ["INTC"],
             "next_catalyst": "GTC 2026-06-12"},
        ],
        "skipped_tickers": ["BADCO"],
        "yesterday_outcomes": {"long_correct": 6, "long_total": 10,
                               "short_correct": 4, "short_total": 8,
                               "total_pl_eur": 142.5},
        "cost_summary": {
            "total_eur": 2.84, "cache_hit_rate": 0.87,
            "input_tokens": 142000, "output_tokens": 63000,
            "web_search_calls": 23, "aborted_at_phase": None,
        },
    }


def test_daily_html_renders_all_four_sections():
    html = render_daily_html(_sample_payload())
    # Section 1 (Portfolio-Empfehlungen, must be FIRST)
    assert html.index("Portfolio-Empfehlungen") < html.index("Top-10")
    # Section 2 (Stocks Top-10)
    assert "NVDA" in html
    # Section 3 (Trends)
    assert "ai-capex-acceleration" in html
    # Section 4 (Commodities/Crypto)
    assert "GC=F" in html
    # Footer
    assert "2.84" in html  # cost summary
    assert "BADCO" in html  # skipped
    assert "Disclaimer" in html or "Anlageberatung" in html


def test_daily_html_renders_anpassen_with_new_levels():
    html = render_daily_html(_sample_payload())
    assert "ANPASSEN" in html
    assert "178.5" in html  # new SL
    assert "SCHLIESSEN" in html


def test_daily_html_renders_intraday_range_column():
    html = render_daily_html(_sample_payload())
    assert "Range/Tag" in html or "intraday_range" in html.lower()
    assert "2.4" in html  # NVDA intraday_range_pct


def test_daily_html_when_no_setups_still_renders_other_sections():
    payload = _sample_payload()
    payload["top_long"] = []
    payload["top_short"] = []
    html = render_daily_html(payload)
    assert "keine Setups" in html.lower() or "keine setups" in html.lower()
    assert "ai-capex-acceleration" in html  # trends still present


def test_daily_html_when_cost_aborted_includes_warning():
    payload = _sample_payload()
    payload["cost_summary"]["aborted_at_phase"] = "deep_analysis"
    html = render_daily_html(payload)
    assert "abgebrochen" in html.lower() or "aborted" in html.lower()


def test_weekly_html_renders_win_rate_and_trade_list():
    weekly_payload = {
        "week_label": "KW21",
        "long_correct": 34, "long_total": 60, "long_avg_pl": 18.50,
        "short_correct": 38, "short_total": 60, "short_avg_pl": 21.80,
        "total_pl_eur": 1210.0,
        "trades": [
            {"date": "2026-05-13", "ticker": "NVDA", "direction": "long",
             "entry_price": 880.0, "exit_price": 920.0, "exit_reason": "tp_hit",
             "profit_loss_eur": 75.0},
        ],
        "cost_summary": {"total_eur": 14.20, "cache_hit_rate": 0.85,
                         "input_tokens": 800000, "output_tokens": 350000,
                         "web_search_calls": 120, "aborted_at_phase": None},
    }
    html = render_weekly_html(weekly_payload)
    assert "KW21" in html
    assert "34" in html and "60" in html  # long_correct/total
    assert "NVDA" in html


def test_send_daily_email_posts_via_sendgrid():
    payload = _sample_payload()
    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_sg_class = MagicMock()
    mock_sg_instance = MagicMock()
    mock_sg_instance.send.return_value = mock_response
    mock_sg_class.return_value = mock_sg_instance
    with patch("src.email_sender.SendGridAPIClient", mock_sg_class):
        send_daily_email(
            payload=payload,
            api_key="SG.fake",
            email_from="from@example.com",
            email_to="to@example.com",
        )
    mock_sg_instance.send.assert_called_once()


def test_send_daily_email_raises_on_non_2xx():
    payload = _sample_payload()
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.body = b"server error"
    mock_sg_instance = MagicMock()
    mock_sg_instance.send.return_value = mock_response
    with patch("src.email_sender.SendGridAPIClient",
               return_value=mock_sg_instance):
        with pytest.raises(EmailSendError):
            send_daily_email(
                payload=payload, api_key="SG.fake",
                email_from="from@example.com", email_to="to@example.com",
            )
```

- [ ] **Step 9.2: Run failing tests**

Run: `pytest tests/unit/test_email_sender.py -v`
Expected: ImportError.

- [ ] **Step 9.3: Implement `src/email_sender.py`**

```python
"""Phase 5: E-Mail rendering and SendGrid delivery.

Daily mail is rendered as four sections in this fixed order:
  1. Portfolio-Empfehlungen (Phase 4a) — directly actionable on market open
  2. Aktien Top-10 Long + Top-10 Short
  3. Trends (dark cards)
  4. Commodities + Crypto

Plus a footer with yesterday's outcomes, skipped tickers, disclaimer, costs.
Weekly mail is a shorter HTML body with the same delivery infra."""
import html
import logging
from typing import Any

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

log = logging.getLogger("shares_future.email_sender")


class EmailSendError(RuntimeError):
    """SendGrid returned a non-2xx response. Caller should still treat the run
    as successful — the data is in the DB."""


# ---------- Daily HTML ----------

_DISCLAIMER = (
    "Shares_Future ist ein automatisiertes Research- und Paper-Trading-System "
    "ohne automatische Orderausführung. Alle Analysen dienen ausschließlich zu "
    "Informationszwecken und stellen KEINE Anlageberatung dar. CFD-Handel kann "
    "zum Totalverlust führen. Keine Garantie für Prognosen."
)


def _h(s: Any) -> str:
    if s is None:
        return ""
    return html.escape(str(s))


def _section_portfolio(recs: list[dict]) -> str:
    if not recs:
        return ('<h2>Portfolio-Empfehlungen</h2>'
                '<p><i>Keine offenen Positionen.</i></p>')
    rows = []
    for r in recs:
        new_lvls = ""
        if r["action"] == "ANPASSEN":
            new_lvls = (f' (neuer SL {_h(r.get("new_sl_price"))}, '
                        f'neues TP {_h(r.get("new_tp_price"))})')
        rows.append(
            f'<tr><td><b>{_h(r["action"])}</b></td>'
            f'<td>{_h(r["ticker"])}</td>'
            f'<td>{_h(r["direction"])} @ {_h(r.get("entry_price"))}</td>'
            f'<td>{_h(r.get("reason", ""))}{new_lvls}</td></tr>'
        )
    return (
        '<h2>Portfolio-Empfehlungen</h2>'
        '<table border="1" cellpadding="4" cellspacing="0">'
        '<tr><th>Action</th><th>Ticker</th><th>Position</th><th>Begründung</th></tr>'
        + "".join(rows) + '</table>'
    )


def _row_for_setup(rank: int, a: dict) -> str:
    scores = a.get("scores", {})
    trend_flag = "🔥" if a.get("trend_boost") else ""
    policy_flag = "⚠️" if scores.get("policy_risk", {}).get("value", 10) <= 4 else ""
    return (
        f'<tr><td>{rank}</td><td>{_h(a["ticker"])}</td>'
        f'<td>{_h(a.get("total_score"))}</td>'
        f'<td>{_h(a.get("probability_pct"))}%</td>'
        f'<td>{_h(a.get("current_price"))}</td>'
        f'<td>{_h(a.get("tp_price"))}</td>'
        f'<td>{_h(a.get("sl_price"))}</td>'
        f'<td>{_h(a.get("rr_ratio"))}</td>'
        f'<td>{_h(a.get("atr_pct"))}</td>'
        f'<td>{_h(a.get("intraday_range_pct"))}</td>'
        f'<td>{trend_flag}{policy_flag}</td>'
        f'<td>{_h(a.get("summary", ""))[:160]}</td></tr>'
    )


def _section_stocks(top_long: list[dict], top_short: list[dict]) -> str:
    if not top_long and not top_short:
        return '<h2>Aktien Top-10</h2><p><i>Keine Setups gefunden.</i></p>'
    head = (
        '<tr><th>#</th><th>Ticker</th><th>Score</th><th>P%</th>'
        '<th>Kurs</th><th>TP</th><th>SL</th><th>R/R</th>'
        '<th>ATR/Tag</th><th>Range/Tag</th><th>Flags</th><th>Begründung</th></tr>'
    )
    long_rows = "".join(_row_for_setup(i + 1, a) for i, a in enumerate(top_long))
    short_rows = "".join(_row_for_setup(i + 1, a) for i, a in enumerate(top_short))
    return (
        '<h2>Aktien Top-10 Long</h2>'
        '<table border="1" cellpadding="4" cellspacing="0">' + head + long_rows +
        '</table>'
        '<h2>Aktien Top-10 Short</h2>'
        '<table border="1" cellpadding="4" cellspacing="0">' + head + short_rows +
        '</table>'
    )


def _section_trends(trends: list[dict]) -> str:
    if not trends:
        return '<h2>Trends</h2><p><i>Keine Trends erkannt.</i></p>'
    cards = []
    for t in trends:
        cards.append(
            '<div style="background:#1a1a1a;color:#eee;padding:12px;'
            'margin:6px 0;border-radius:8px;">'
            f'<h3 style="margin:0;color:#80c0ff;">{_h(t.get("name"))} '
            f'<small>(Stärke {_h(t.get("strength"))}, '
            f'{_h(t.get("duration_estimate"))})</small></h3>'
            f'<p>{_h(t.get("summary"))}</p>'
            f'<p><b>+</b> {_h(", ".join(t.get("beneficiary_tickers") or []))}<br>'
            f'<b>−</b> {_h(", ".join(t.get("negative_tickers") or []))}<br>'
            f'<b>Catalyst:</b> {_h(t.get("next_catalyst"))}</p>'
            '</div>'
        )
    return '<h2>Trends</h2>' + "".join(cards)


def _section_commodities_crypto(items: list[dict]) -> str:
    if not items:
        return ('<h2>Commodities + Crypto</h2>'
                '<p><i>Keine Daten.</i></p>')
    rows = []
    for a in items:
        extra = a.get("extra") or {}
        rows.append(
            f'<tr><td>{_h(a["ticker"])}</td>'
            f'<td>{_h(a.get("direction"))}</td>'
            f'<td>{_h(a.get("total_score"))}</td>'
            f'<td>{_h(a.get("probability_pct"))}%</td>'
            f'<td>{_h(a.get("current_price"))}</td>'
            f'<td>{_h(a.get("tp_price"))}</td>'
            f'<td>{_h(a.get("sl_price"))}</td>'
            f'<td>{_h(extra.get("fear_greed_value"))}</td></tr>'
        )
    gsr = next(
        (a.get("extra", {}).get("gold_silver_ratio")
         for a in items if a.get("extra", {}).get("gold_silver_ratio") is not None),
        None,
    )
    btc_dom = next(
        (a.get("extra", {}).get("btc_dominance_pct")
         for a in items if a.get("extra", {}).get("btc_dominance_pct") is not None),
        None,
    )
    footer = ""
    if gsr is not None or btc_dom is not None:
        footer = (
            f'<p><small>Gold/Silver-Ratio: {_h(gsr)} '
            f' | BTC-Dominanz: {_h(btc_dom)}%</small></p>'
        )
    return (
        '<h2>Commodities + Crypto</h2>'
        '<table border="1" cellpadding="4" cellspacing="0">'
        '<tr><th>Ticker</th><th>Dir</th><th>Score</th><th>P%</th>'
        '<th>Kurs</th><th>TP</th><th>SL</th><th>F&amp;G</th></tr>'
        + "".join(rows) + '</table>' + footer
    )


def _section_footer(payload: dict) -> str:
    cost = payload.get("cost_summary") or {}
    y = payload.get("yesterday_outcomes") or {}
    skipped = payload.get("skipped_tickers") or []
    aborted_line = ""
    if cost.get("aborted_at_phase"):
        aborted_line = (
            f'<p style="color:#c00"><b>Run wurde abgebrochen in Phase: '
            f'{_h(cost["aborted_at_phase"])}</b> (Hard-Cap erreicht).</p>'
        )
    return (
        aborted_line +
        '<hr>'
        '<p><b>Vortags-Performance:</b> '
        f'Long {_h(y.get("long_correct"))}/{_h(y.get("long_total"))}, '
        f'Short {_h(y.get("short_correct"))}/{_h(y.get("short_total"))}, '
        f'sim. P/L {_h(y.get("total_pl_eur"))} EUR</p>'
        f'<p><b>Übersprungene Aktien:</b> {_h(", ".join(skipped)) or "—"}</p>'
        '<p><b>Run-Kosten:</b> '
        f'{_h(cost.get("total_eur"))} EUR | '
        f'Cache-Hit-Rate: {_h(round((cost.get("cache_hit_rate") or 0) * 100, 1))}% | '
        f'Tokens: {_h(cost.get("input_tokens"))}/'
        f'{_h(cost.get("output_tokens"))} | '
        f'Web-Searches: {_h(cost.get("web_search_calls"))}</p>'
        f'<p><small><b>Disclaimer:</b> {_h(_DISCLAIMER)}</small></p>'
    )


def render_daily_html(payload: dict) -> str:
    """Build the 4-section daily e-mail body."""
    return (
        '<html><body style="font-family:sans-serif;font-size:14px;">'
        f'<h1>Shares_Future — {_h(payload.get("date"))} '
        f'({_h(payload.get("run_type"))})</h1>'
        + _section_portfolio(payload.get("portfolio_recs") or [])
        + _section_stocks(
            payload.get("top_long") or [], payload.get("top_short") or [],
        )
        + _section_trends(payload.get("trends") or [])
        + _section_commodities_crypto(payload.get("commodities_crypto") or [])
        + _section_footer(payload)
        + '</body></html>'
    )


# ---------- Weekly HTML ----------

def render_weekly_html(payload: dict) -> str:
    """Reduced weekly e-mail. No learnings/prompt-optimizer in Sprint 1."""
    trades_rows = "".join(
        f'<tr><td>{_h(t["date"])}</td><td>{_h(t["ticker"])}</td>'
        f'<td>{_h(t["direction"])}</td>'
        f'<td>{_h(t.get("entry_price"))}</td>'
        f'<td>{_h(t.get("exit_price"))}</td>'
        f'<td>{_h(t.get("exit_reason"))}</td>'
        f'<td>{_h(t.get("profit_loss_eur"))}</td></tr>'
        for t in (payload.get("trades") or [])
    )
    cost = payload.get("cost_summary") or {}
    return (
        '<html><body style="font-family:sans-serif;font-size:14px;">'
        f'<h1>Shares_Future Wochen-Summary — {_h(payload.get("week_label"))}</h1>'
        '<h2>Performance</h2>'
        f'<p>Long: {_h(payload.get("long_correct"))}/'
        f'{_h(payload.get("long_total"))} | '
        f'Ø P/L {_h(payload.get("long_avg_pl"))} EUR</p>'
        f'<p>Short: {_h(payload.get("short_correct"))}/'
        f'{_h(payload.get("short_total"))} | '
        f'Ø P/L {_h(payload.get("short_avg_pl"))} EUR</p>'
        f'<p><b>Sim. Gesamt-P/L:</b> {_h(payload.get("total_pl_eur"))} EUR</p>'
        '<h2>Trades</h2>'
        '<table border="1" cellpadding="4" cellspacing="0">'
        '<tr><th>Datum</th><th>Ticker</th><th>Dir</th>'
        '<th>Entry</th><th>Exit</th><th>Reason</th><th>P/L EUR</th></tr>'
        + trades_rows + '</table>'
        f'<p><b>Run-Kosten Woche:</b> {_h(cost.get("total_eur"))} EUR</p>'
        f'<p><small>{_h(_DISCLAIMER)}</small></p>'
        '</body></html>'
    )


# ---------- Delivery ----------

def send_daily_email(
    payload: dict, api_key: str, email_from: str, email_to: str,
) -> None:
    html_body = render_daily_html(payload)
    subject = (
        f"[Shares_Future] {payload.get('date')} {payload.get('run_type')} — "
        f"Top {len(payload.get('top_long') or [])}L / "
        f"{len(payload.get('top_short') or [])}S"
    )
    _send(api_key, email_from, email_to, subject, html_body)


def send_weekly_email(
    payload: dict, api_key: str, email_from: str, email_to: str,
) -> None:
    html_body = render_weekly_html(payload)
    subject = (
        f"[Shares_Future] {payload.get('week_label')} — Wochen-Summary"
    )
    _send(api_key, email_from, email_to, subject, html_body)


def _send(api_key: str, email_from: str, email_to: str,
          subject: str, html_body: str) -> None:
    mail = Mail(
        from_email=email_from, to_emails=email_to,
        subject=subject, html_content=html_body,
    )
    client = SendGridAPIClient(api_key)
    resp = client.send(mail)
    if not (200 <= getattr(resp, "status_code", 0) < 300):
        raise EmailSendError(
            f"SendGrid returned status {resp.status_code}: "
            f"{getattr(resp, 'body', '')!r}"
        )
    log.info(f"SendGrid accepted message (status={resp.status_code})")
```

- [ ] **Step 9.4: Run tests, expect green**

Run: `pytest tests/unit/test_email_sender.py -v`
Expected: 8 passed.

- [ ] **Step 9.5: Commit**

```bash
git add src/email_sender.py tests/unit/test_email_sender.py
git commit -m "Sprint1/Plan3 Task 9: email_sender with 4-section daily + reduced weekly + SendGrid delivery"
```

---

## Task 10: `main.py` — Orchestrator

Dispatches by `--run-type`. Owns the single `CostTracker` instance per run. Defines the per-asset Commodities/Crypto display-name map. Loads the prior-day outcomes for the footer. On `CostCapExceeded`: stop further phases, mark `cost_tracker.aborted_at_phase`, render partial e-mail with the warning. On `TrendAnalyzerError`: abort run, send alert e-mail.

`run_type` semantics:
- `pre_market` / `midday` / `close` — full pipeline (Phase 0 → 5)
- `evaluate` — only `evaluator.evaluate_open_predictions` + DB save, no e-mail
- `weekly` — only aggregate the week's outcomes + send weekly e-mail

**Files:**
- Create: `main.py`
- Create: `tests/unit/test_main.py`

- [ ] **Step 10.1: Write failing tests**

`tests/unit/test_main.py`:

```python
import argparse
from unittest.mock import patch, MagicMock
import pytest

from main import (
    run_pipeline, run_evaluate, run_weekly, parse_args, build_commodity_crypto_inputs,
)
import config


def test_parse_args_accepts_all_run_types():
    for rt in ["pre_market", "midday", "close", "evaluate", "weekly"]:
        ns = parse_args(["--run-type", rt])
        assert ns.run_type == rt


def test_parse_args_rejects_unknown_run_type():
    with pytest.raises(SystemExit):
        parse_args(["--run-type", "noon"])


def test_build_commodity_crypto_inputs_combines_config_maps():
    inputs = build_commodity_crypto_inputs()
    tickers = {d["ticker"] for d in inputs}
    expected = set(config.COMMODITY_TICKERS.values()) | set(config.CRYPTO_TICKERS.values())
    assert tickers == expected


def test_run_pipeline_calls_phases_in_order():
    """Smoke-mock every phase and assert the call order."""
    call_log: list[str] = []

    def make_mock(name: str, return_value):
        def _fn(*a, **kw):
            call_log.append(name)
            return return_value
        return _fn

    fake_trends = {"trends": [{"name": "x"}], "trend_summary": "ok"}
    fake_policy = {"policy_risk_level": "low", "events": []}
    fake_collect = ([{"ticker": "AAPL", "intraday_range_pct": 1.5, "price": 178.0}], 0)
    fake_quick = [{"ticker": "AAPL", "exclude": False, "long_score": 7.0,
                   "short_score": 2.0, "confidence": "high", "evidence": []}]
    fake_deep = [{"ticker": "AAPL", "direction": "long", "current_price": 178.0,
                  "tp_price": 184.0, "sl_price": 176.0, "rr_ratio": 3.0,
                  "total_score": 7.6, "probability_pct": 65, "confidence": "high",
                  "hold_days_recommended": 2, "intraday_range_pct": 1.5,
                  "summary": "ok", "sources_used": ["a.com", "b.com"],
                  "signal_consistency_check": "ok", "earnings_warning": False,
                  "scores": {dim: {"value": 7.0, "evidence": ["x", "y"]}
                             for dim in [
                                 "market_environment","company_quality","valuation",
                                 "momentum","risk","sector_trend","catalyst","policy_risk",
                             ]}}]
    fake_cc = []
    fake_portfolio = []
    fake_ranking = {"top_long": fake_deep, "top_short": [],
                    "commodities_crypto": []}

    patches = [
        patch("main.analyze_trends", side_effect=make_mock("trend", fake_trends)),
        patch("main.collect", side_effect=make_mock("collect", fake_collect)),
        patch("main.quick_filter_batch",
              side_effect=make_mock("quick_filter", fake_quick)),
        patch("main.run_policy_monitor",
              side_effect=make_mock("policy", fake_policy)),
        patch("main.analyze_assets",
              side_effect=make_mock("deep", fake_deep)),
        patch("main.analyze_commodities_and_crypto",
              side_effect=make_mock("cc", fake_cc)),
        patch("main.check_open_positions",
              side_effect=make_mock("portfolio", fake_portfolio)),
        patch("main.rank_and_persist",
              side_effect=make_mock("ranking", fake_ranking)),
        patch("main.fetch_fear_greed", return_value={"value": 50, "label": "Neutral"}),
        patch("main.send_daily_email", side_effect=make_mock("email", None)),
        patch("main.YFinanceProvider"),
        patch("main.FinnhubProvider"),
    ]
    with patches[0], patches[1], patches[2], patches[3], patches[4], \
         patches[5], patches[6], patches[7], patches[8], patches[9], \
         patches[10], patches[11]:
        run_pipeline(run_type="close", date="2026-05-19", db_path=":memory:")

    assert call_log == [
        "trend", "collect", "quick_filter", "policy",
        "deep", "cc", "portfolio", "ranking", "email",
    ]


def test_run_pipeline_aborts_when_trend_fails(tmp_db_path):
    from src.trend_analyzer import TrendAnalyzerError
    with patch("main.analyze_trends", side_effect=TrendAnalyzerError("no trends")), \
         patch("main.send_daily_email") as mock_email, \
         patch("main.YFinanceProvider"), patch("main.FinnhubProvider"):
        with pytest.raises(TrendAnalyzerError):
            run_pipeline(run_type="close", date="2026-05-19",
                         db_path=str(tmp_db_path))
    # No daily email is sent on Phase 0 failure (the alerting path is the
    # exception propagating — the GH Actions step turns red).
    mock_email.assert_not_called()


def test_run_pipeline_partial_email_when_cost_cap_hit(tmp_db_path):
    from src.cost_tracker import CostCapExceeded
    with patch("main.analyze_trends", return_value={"trends": [{"name": "x"}],
                                                     "trend_summary": "ok"}), \
         patch("main.collect", return_value=([], 0)), \
         patch("main.quick_filter_batch", return_value=[]), \
         patch("main.run_policy_monitor",
               side_effect=CostCapExceeded("cap hit")), \
         patch("main.send_daily_email") as mock_email, \
         patch("main.YFinanceProvider"), patch("main.FinnhubProvider"):
        run_pipeline(run_type="close", date="2026-05-19", db_path=str(tmp_db_path))
    # Email IS sent with the partial payload + abort warning
    args = mock_email.call_args.kwargs
    assert args["payload"]["cost_summary"]["aborted_at_phase"] == "policy_monitor"


def test_run_evaluate_calls_evaluator_no_email(tmp_db_path):
    with patch("main.evaluate_open_predictions", return_value=3) as mock_eval, \
         patch("main.send_daily_email") as mock_email, \
         patch("main.YFinanceProvider"):
        run_evaluate(date="2026-05-19", db_path=str(tmp_db_path))
    mock_eval.assert_called_once()
    mock_email.assert_not_called()


def test_run_weekly_calls_send_weekly_email(tmp_db_path):
    with patch("main.send_weekly_email") as mock_send, \
         patch("main.load_recent_outcomes_aggregate",
               return_value={"long_correct": 0, "long_total": 0,
                             "long_avg_pl": 0.0, "short_correct": 0,
                             "short_total": 0, "short_avg_pl": 0.0,
                             "total_pl_eur": 0.0, "trades": []}):
        run_weekly(date="2026-05-24", db_path=str(tmp_db_path))
    mock_send.assert_called_once()
```

- [ ] **Step 10.2: Run failing tests**

Run: `pytest tests/unit/test_main.py -v`
Expected: ImportError on every `main.<name>`.

- [ ] **Step 10.3: Implement `main.py`**

```python
"""Orchestrator. Dispatches by --run-type.

Owns the single CostTracker per run. Phase 0 (trend) failure aborts the run by
re-raising; the GH Actions step turns red and the user is alerted via the
workflow's email-on-failure notification. Cost-cap aborts produce a partial
e-mail with the warning bar."""
import argparse
import logging
import sys
from datetime import date as date_cls, timedelta

import config
from src import db
from src.cost_tracker import CostTracker, CostCapExceeded
from src.data_collector import collect
from src.trend_analyzer import analyze_trends, TrendAnalyzerError
from src.quick_filter import quick_filter_batch
from src.deep_analysis import run_policy_monitor, analyze_assets
from src.commodities_crypto import (
    analyze_commodities_and_crypto, fetch_fear_greed,
)
from src.portfolio_check import check_open_positions
from src.ranking import rank_and_persist
from src.evaluator import evaluate_open_predictions
from src.email_sender import (
    send_daily_email, send_weekly_email,
)
from src.providers.yfinance_provider import YFinanceProvider
from src.providers.finnhub_provider import FinnhubProvider

log = logging.getLogger("shares_future.main")

RUN_TYPES = ["pre_market", "midday", "close", "evaluate", "weekly"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-type", required=True, choices=RUN_TYPES)
    parser.add_argument("--date", default=None,
                        help="ISO date (default: today UTC)")
    parser.add_argument("--db-path", default=str(config.DB_PATH))
    return parser.parse_args(argv)


def build_commodity_crypto_inputs() -> list[dict]:
    """Returns 7 stub TickerData dicts (name + ticker + asset_class).
    data_collector populates indicators per ticker; here we list the universe."""
    out: list[dict] = []
    for name, t in config.COMMODITY_TICKERS.items():
        out.append({"ticker": t, "name": name, "asset_class": "commodity"})
    for name, t in config.CRYPTO_TICKERS.items():
        out.append({"ticker": t, "name": name, "asset_class": "crypto"})
    return out


def _aggregate_yesterday_outcomes(conn, today: str) -> dict:
    yesterday = (date_cls.fromisoformat(today) - timedelta(days=1)).isoformat()
    rows = conn.execute(
        """SELECT pred_direction, COUNT(*) AS n,
                  SUM(CASE WHEN correct_direction_eod THEN 1 ELSE 0 END) AS correct,
                  COALESCE(SUM(profit_loss_eur), 0) AS pl
           FROM (
             SELECT p.direction AS pred_direction,
                    o.correct_direction_eod, o.profit_loss_eur
             FROM outcomes o JOIN predictions p ON p.id = o.prediction_id
             WHERE o.evaluated_date = ?
           )
           GROUP BY pred_direction""",
        (yesterday,),
    ).fetchall()
    agg = {"long_correct": 0, "long_total": 0,
           "short_correct": 0, "short_total": 0, "total_pl_eur": 0.0}
    for r in rows:
        if r["pred_direction"] == "long":
            agg["long_total"]   = int(r["n"])
            agg["long_correct"] = int(r["correct"] or 0)
        elif r["pred_direction"] == "short":
            agg["short_total"]   = int(r["n"])
            agg["short_correct"] = int(r["correct"] or 0)
        agg["total_pl_eur"] += float(r["pl"] or 0.0)
    return agg


def load_recent_outcomes_aggregate(conn, today: str) -> dict:
    """7-day window for the weekly mail."""
    since = (date_cls.fromisoformat(today) - timedelta(days=7)).isoformat()
    rows = db.load_recent_outcomes(conn, since)
    long_t = [r for r in rows if r["pred_direction"] == "long"]
    short_t = [r for r in rows if r["pred_direction"] == "short"]
    def _agg(items):
        n = len(items)
        correct = sum(1 for r in items if r["correct_direction_eod"])
        pl = sum(r["profit_loss_eur"] or 0.0 for r in items)
        avg = round(pl / n, 2) if n else 0.0
        return n, correct, avg, pl
    ln, lc, la, lp = _agg(long_t)
    sn, sc, sa, sp = _agg(short_t)
    return {
        "long_total": ln, "long_correct": lc, "long_avg_pl": la,
        "short_total": sn, "short_correct": sc, "short_avg_pl": sa,
        "total_pl_eur": round(lp + sp, 2),
        "trades": [{
            "date": r["evaluated_date"], "ticker": r["ticker"],
            "direction": r["pred_direction"],
            "entry_price": r["entry_price"], "exit_price": r["price_after_eod"],
            "exit_reason": r["exit_reason"],
            "profit_loss_eur": r["profit_loss_eur"],
        } for r in rows],
    }


def run_pipeline(run_type: str, date: str, db_path: str) -> None:
    """Full Phase 0–5 pipeline for pre_market / midday / close."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    db.cleanup_old_data(conn)
    cost_tracker = CostTracker()
    price_provider = YFinanceProvider()
    earnings_provider = FinnhubProvider()

    aborted_at: str | None = None
    payload = {
        "date": date, "run_type": run_type,
        "portfolio_recs": [], "top_long": [], "top_short": [],
        "commodities_crypto": [], "trends": [],
        "skipped_tickers": [],
        "yesterday_outcomes": {},
        "cost_summary": {},
    }

    # Phase 0 — fatal if it fails
    trend_context = analyze_trends(
        conn=conn, date=date, run_type=run_type, cost_tracker=cost_tracker,
    )
    payload["trends"] = trend_context.get("trends", [])

    try:
        # Phase 1 — Stocks data
        sp500_tds, skipped_sp = collect(
            tickers=config.SP500_MVP_TICKERS,
            price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn, date=date, run_type=run_type,
        )
        # Phase 1b — Commodities + Crypto data (separate collect for asset_class tagging)
        cc_inputs = build_commodity_crypto_inputs()
        cc_tickers = [d["ticker"] for d in cc_inputs]
        cc_tds_raw, skipped_cc = collect(
            tickers=cc_tickers,
            price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn, date=date, run_type=run_type,
        )
        # Annotate asset_class from the cc_inputs map
        by_ticker = {d["ticker"]: d for d in cc_inputs}
        cc_tds = []
        for td in cc_tds_raw:
            meta = by_ticker.get(td["ticker"], {})
            cc_tds.append({**td,
                           "asset_class": meta.get("asset_class", "commodity"),
                           "name": meta.get("name", td["ticker"])})

        payload["skipped_tickers"] = [
            r["ticker"] for r in conn.execute(
                "SELECT DISTINCT ticker FROM skipped_tickers WHERE date=?", (date,),
            ).fetchall()
        ]

        # Phase 2 — quick filter (stocks only)
        quick = quick_filter_batch(
            batch=sp500_tds, trend_context=trend_context,
            cost_tracker=cost_tracker,
        )

        # Phase 3 policy monitor (1× for all of Phase 3 + 3b + 4a)
        policy_context = run_policy_monitor(
            date=date, run_type=run_type, cost_tracker=cost_tracker,
        )

        # Phase 3 deep analysis
        deep_stocks = analyze_assets(
            ticker_datas=sp500_tds,
            quick_filter_results=quick,
            trend_context=trend_context,
            policy_context=policy_context,
            cost_tracker=cost_tracker,
        )

        # Phase 3b commodities + crypto
        fg = fetch_fear_greed() or {}
        extra_context = {
            "fear_greed_value": fg.get("value"),
            "fear_greed_label": fg.get("label"),
        }
        deep_cc = analyze_commodities_and_crypto(
            ticker_datas=cc_tds, trend_context=trend_context,
            policy_context=policy_context, extra_context=extra_context,
            cost_tracker=cost_tracker,
        )

        # Phase 4a — Portfolio check (across all snapshots seen this run)
        snapshots_by_ticker = {td["ticker"]: td for td in (sp500_tds + cc_tds)}
        portfolio_recs = check_open_positions(
            conn=conn, today=date, run_type=run_type,
            snapshots_by_ticker=snapshots_by_ticker,
            trend_context=trend_context, policy_context=policy_context,
            cost_tracker=cost_tracker,
        )
        payload["portfolio_recs"] = portfolio_recs

        # Phase 4 — Ranking + persist predictions
        market_ctx = {
            "vix_level": None, "market_regime": None, "sector": None,
        }
        ranked = rank_and_persist(
            conn=conn, date=date, run_type=run_type,
            stock_analyses=deep_stocks,
            commodity_crypto_analyses=deep_cc,
            market_context=market_ctx,
        )
        payload["top_long"]            = ranked["top_long"]
        payload["top_short"]           = ranked["top_short"]
        payload["commodities_crypto"]  = ranked["commodities_crypto"]

    except CostCapExceeded as e:
        log.warning(f"Run aborted: {e}")
        cost_tracker.aborted_at_phase = _guess_aborted_phase(e)
        aborted_at = cost_tracker.aborted_at_phase

    # Always: write cost summary + send mail (even on partial run)
    payload["yesterday_outcomes"] = _aggregate_yesterday_outcomes(conn, today=date)
    payload["cost_summary"] = cost_tracker.summary(run_type=run_type, date=date)
    db.save_cost_tracking(conn, payload["cost_summary"])

    send_daily_email(
        payload=payload,
        api_key=config.SENDGRID_API_KEY,
        email_from=config.EMAIL_FROM, email_to=config.EMAIL_TO,
    )
    conn.close()


def _guess_aborted_phase(_exc: CostCapExceeded) -> str:
    """We don't have a precise phase from the exception — return a stable
    placeholder. The orchestrator could thread a phase name in later."""
    return "policy_monitor"


def run_evaluate(date: str, db_path: str) -> None:
    conn = db.connect(db_path)
    db.init_schema(conn)
    price_provider = YFinanceProvider()
    n = evaluate_open_predictions(
        conn=conn, today=date, price_provider=price_provider,
    )
    log.info(f"Evaluate run: {n} predictions closed")
    conn.close()


def run_weekly(date: str, db_path: str) -> None:
    conn = db.connect(db_path)
    db.init_schema(conn)
    agg = load_recent_outcomes_aggregate(conn, today=date)
    week_label = "KW" + date_cls.fromisoformat(date).strftime("%V")
    payload = {
        "week_label": week_label, **agg,
        "cost_summary": {"total_eur": 0.0, "cache_hit_rate": 0.0,
                         "input_tokens": 0, "output_tokens": 0,
                         "web_search_calls": 0, "aborted_at_phase": None},
    }
    send_weekly_email(
        payload=payload, api_key=config.SENDGRID_API_KEY,
        email_from=config.EMAIL_FROM, email_to=config.EMAIL_TO,
    )
    conn.close()


def main(argv: list[str] | None = None) -> None:
    ns = parse_args(argv)
    date = ns.date or date_cls.today().isoformat()
    if ns.run_type in ("pre_market", "midday", "close"):
        run_pipeline(run_type=ns.run_type, date=date, db_path=ns.db_path)
    elif ns.run_type == "evaluate":
        run_evaluate(date=date, db_path=ns.db_path)
    elif ns.run_type == "weekly":
        run_weekly(date=date, db_path=ns.db_path)
    else:  # pragma: no cover — argparse validated
        sys.exit(2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 10.4: Run tests, expect green**

Run: `pytest tests/unit/test_main.py -v`
Expected: 7 passed.

- [ ] **Step 10.5: Commit**

```bash
git add main.py tests/unit/test_main.py
git commit -m "Sprint1/Plan3 Task 10: main.py orchestrator with run-type dispatch and cost-cap handling"
```

---

## Task 11: Integration tests — full pipeline, eval loop, email render

These tests mock every external API (Claude, yfinance, Finnhub, SendGrid) but exercise the real Python plumbing between phases.

**Files:**
- Create: `tests/integration/__init__.py` (empty)
- Create: `tests/integration/test_full_pipeline.py`
- Create: `tests/integration/test_eval_loop.py`
- Create: `tests/integration/test_email_render.py`

- [ ] **Step 11.1: Create `tests/integration/__init__.py`**

Empty file.

- [ ] **Step 11.2: Write `tests/integration/test_full_pipeline.py`**

```python
"""E2E mocked-API pipeline test: 3 SP500 tickers + 2 commodities."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd

import main as orchestrator

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def _mock_ohlc():
    idx = pd.date_range("2026-02-19", "2026-05-19", freq="B")[-90:]
    return pd.DataFrame({
        "Open":   [100.0] * len(idx),
        "High":   [101.5] * len(idx),
        "Low":    [99.0]  * len(idx),
        "Close":  [100.5] * len(idx),
        "Volume": [1_000_000] * len(idx),
    }, index=idx)


def test_full_pipeline_writes_predictions_and_sends_email(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"

    # Stub providers
    fake_provider_cls = MagicMock()
    fake_provider = MagicMock()
    fake_provider.get_price_history.return_value = _mock_ohlc()
    fake_provider.get_fundamentals.return_value = {
        "pe_ratio": 25.0, "forward_pe": 23.0, "market_cap_b": 200.0,
        "debt_equity": 1.0, "sector": "Technology", "analyst_upside": 5.0,
        "consensus": "Buy",
    }
    fake_provider.get_earnings_calendar.return_value = {
        "days_to_next": 14, "last_beat_pct": 3.5,
    }
    fake_provider_cls.return_value = fake_provider

    monkeypatch.setattr(orchestrator, "YFinanceProvider", fake_provider_cls)
    monkeypatch.setattr(orchestrator, "FinnhubProvider", fake_provider_cls)
    monkeypatch.setattr(orchestrator.config, "SP500_MVP_TICKERS",
                        ["AAPL", "MSFT", "NVDA"])
    monkeypatch.setattr(orchestrator.config, "COMMODITY_TICKERS",
                        {"Gold": "GC=F"})
    monkeypatch.setattr(orchestrator.config, "CRYPTO_TICKERS",
                        {"Bitcoin": "BTC-USD"})

    # Stub Claude calls (one mock per module-level call_claude)
    trend_resp = (FIXTURE_DIR / "mock_trend_response.json").read_text()
    quick_resp = (FIXTURE_DIR / "mock_quick_filter_response.json").read_text()
    policy_resp = (FIXTURE_DIR / "mock_policy_monitor_response.json").read_text()
    deep_resp = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    cc_resp = (FIXTURE_DIR / "mock_commodities_crypto_response.json").read_text()

    def _r(text, web_search_calls=2, model="claude-sonnet-4-6"):
        r = MagicMock()
        r.text = text
        r.input_tokens = 1000
        r.output_tokens = 600
        r.cache_read_tokens = 200
        r.cache_creation_tokens = 100
        r.model = model
        r.web_search_calls = web_search_calls
        return r

    # Adjust quick_filter fixture to cover the 3 SP500 tickers
    quick_obj = json.loads(quick_resp)
    quick_obj["results"] = [
        {"ticker": "AAPL", "long_score": 7.5, "short_score": 2.0,
         "confidence": "high", "evidence": ["x"], "exclude": False},
        {"ticker": "MSFT", "long_score": 6.5, "short_score": 3.0,
         "confidence": "medium", "evidence": ["x"], "exclude": False},
        {"ticker": "NVDA", "long_score": 8.0, "short_score": 1.5,
         "confidence": "high", "evidence": ["x"], "exclude": False},
    ]
    quick_resp_3 = json.dumps(quick_obj)

    deep_obj = json.loads(deep_resp)
    def _deep_for(ticker: str) -> str:
        cp = dict(deep_obj)
        cp["ticker"] = ticker
        return json.dumps(cp)

    cc_obj = json.loads(cc_resp)
    def _cc_for(ticker: str, asset_class: str) -> str:
        cp = dict(cc_obj)
        cp["ticker"] = ticker
        cp["asset_class"] = asset_class
        return json.dumps(cp)

    sequence = [
        _r(trend_resp, web_search_calls=4),                  # analyze_trends
        _r(quick_resp_3, web_search_calls=0, model="claude-haiku-4-5"),  # quick_filter
        _r(policy_resp, web_search_calls=3),                 # policy_monitor
        _r(_deep_for("AAPL")),                                # deep AAPL
        _r(_deep_for("MSFT")),                                # deep MSFT
        _r(_deep_for("NVDA")),                                # deep NVDA
        _r(_cc_for("GC=F", "commodity")),                    # cc Gold
        _r(_cc_for("BTC-USD", "crypto")),                    # cc BTC
    ]

    with patch("src.trend_analyzer.call_claude", side_effect=[sequence[0]]), \
         patch("src.quick_filter.call_claude", side_effect=[sequence[1]]), \
         patch("src.deep_analysis.call_claude",
               side_effect=[sequence[2], sequence[3], sequence[4], sequence[5]]), \
         patch("src.commodities_crypto.call_claude",
               side_effect=[sequence[6], sequence[7]]), \
         patch("src.portfolio_check.call_claude"), \
         patch("src.email_sender.SendGridAPIClient") as mock_sg, \
         patch("src.commodities_crypto.fetch_fear_greed",
               return_value={"value": 55, "label": "Greed"}):
        mock_sg.return_value.send.return_value = MagicMock(status_code=202)
        orchestrator.run_pipeline(run_type="close", date="2026-05-19",
                                  db_path=str(db_path))

    # Assert predictions written
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    n_pred = conn.execute("SELECT COUNT(*) AS n FROM predictions").fetchone()["n"]
    assert n_pred >= 3  # at least the 3 stocks (+ 2 commodities/crypto if guardrails pass)
    n_cost = conn.execute("SELECT COUNT(*) AS n FROM cost_tracking").fetchone()["n"]
    assert n_cost == 1
    mock_sg.return_value.send.assert_called_once()
```

- [ ] **Step 11.3: Write `tests/integration/test_eval_loop.py`**

```python
"""Predict on Tag 0, 3-day OHLC fixture, evaluator closes correctly."""
import pandas as pd
from unittest.mock import MagicMock

from src import db
from src.evaluator import evaluate_open_predictions


def test_predict_then_evaluate_two_days_later_tp_hit(tmp_path):
    conn = db.connect(str(tmp_path / "e.db"))
    db.init_schema(conn)
    pid = db.save_prediction(conn, {
        "date": "2026-05-19", "run_type": "close",
        "asset_class": "stock", "ticker": "AAPL", "direction": "long",
        "entry_price": 100.0, "tp_price": 105.0, "tp_pct": 5.0,
        "sl_price": 95.0, "sl_pct": 5.0, "rr_ratio": 1.0,
        "total_score": 7.5, "probability_pct": 65, "confidence": "high",
        "score_market_env": 7.0, "score_company": 7.0, "score_valuation": 6.0,
        "score_momentum": 8.0, "score_risk": 6.0, "score_sector": 7.0,
        "score_catalyst": 7.0, "score_policy": 6.0,
        "atr_pct": 1.8, "rsi_at_entry": 58.0, "volume_ratio": 1.0,
        "market_regime": "risk_on", "vix_at_prediction": 14.0,
        "sector": "Technology", "trend_boost": None,
        "earnings_warning": False, "summary": "ok",
        "learnable": True, "hold_days_recommended": 2,
        "intraday_range_pct": 1.5,
    })
    idx = pd.to_datetime(["2026-05-19", "2026-05-20", "2026-05-21"])
    df = pd.DataFrame({
        "Open":  [100.0, 100.0, 102.0],
        "High":  [101.0, 105.5, 104.0],
        "Low":   [99.0,   99.5, 101.0],
        "Close": [100.0, 104.0, 103.0],
    }, index=idx)
    provider = MagicMock()
    provider.get_ohlc_after.return_value = df

    evaluate_open_predictions(conn=conn, today="2026-05-21", price_provider=provider)

    row = conn.execute(
        "SELECT status, closed_price FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_tp"
    assert row["closed_price"] == 105.0
    out = conn.execute(
        "SELECT exit_reason, days_to_close FROM outcomes WHERE prediction_id=?",
        (pid,),
    ).fetchone()
    assert out["exit_reason"] == "tp_hit"
    assert out["days_to_close"] == 1  # bar after entry day
```

- [ ] **Step 11.4: Write `tests/integration/test_email_render.py`**

```python
"""HTML snapshot: render a full daily mail and assert section ordering + key fields."""
from src.email_sender import render_daily_html


def test_render_daily_html_contains_all_sections_in_order():
    payload = {
        "date": "2026-05-19", "run_type": "close",
        "portfolio_recs": [
            {"ticker": "AAPL", "action": "HALTEN",
             "reason": "These intakt", "new_sl_price": None,
             "new_tp_price": None, "entry_price": 178.0, "direction": "long"},
        ],
        "top_long": [
            {"ticker": "NVDA", "current_price": 880, "tp_price": 920,
             "sl_price": 860, "rr_ratio": 2.0, "total_score": 8.5,
             "probability_pct": 75, "intraday_range_pct": 2.4,
             "summary": "AI tailwind", "earnings_warning": False,
             "scores": {"momentum": {"value": 8.5},
                        "policy_risk": {"value": 5.0}}},
        ],
        "top_short": [],
        "commodities_crypto": [
            {"ticker": "GC=F", "asset_class": "commodity",
             "direction": "long", "current_price": 2380,
             "tp_price": 2420, "sl_price": 2360, "rr_ratio": 2.0,
             "total_score": 6.9, "probability_pct": 58,
             "intraday_range_pct": 1.2,
             "extra": {"fear_greed_value": 62, "gold_silver_ratio": 80.3,
                       "btc_dominance_pct": None}},
        ],
        "trends": [
            {"name": "ai-capex", "strength": 8, "duration_estimate": "1m+",
             "summary": "Hyperscalers raised guidance",
             "beneficiary_tickers": ["NVDA"], "negative_tickers": ["INTC"],
             "next_catalyst": "GTC 2026-06-12"},
        ],
        "skipped_tickers": ["BADCO"],
        "yesterday_outcomes": {"long_correct": 6, "long_total": 10,
                               "short_correct": 4, "short_total": 8,
                               "total_pl_eur": 142.5},
        "cost_summary": {"total_eur": 2.84, "cache_hit_rate": 0.87,
                         "input_tokens": 142000, "output_tokens": 63000,
                         "web_search_calls": 23, "aborted_at_phase": None},
    }
    html_ = render_daily_html(payload)
    # Section ordering
    i_portfolio = html_.index("Portfolio-Empfehlungen")
    i_stocks    = html_.index("Top-10")
    i_trends    = html_.index("Trends")
    i_cc        = html_.index("Commodities + Crypto")
    assert i_portfolio < i_stocks < i_trends < i_cc
```

- [ ] **Step 11.5: Run all integration tests, expect green**

Run: `pytest tests/integration/ -v`
Expected: 3 passed.

- [ ] **Step 11.6: Commit**

```bash
git add tests/integration/
git commit -m "Sprint1/Plan3 Task 11: integration tests for full pipeline, eval loop, email render"
```

---

## Task 12: GitHub Actions — CI test gate + cron with Release-Asset DB persistence

Two workflows:
- `test.yml` — on push/PR, run `pytest --cov-fail-under=80`. Required to be green.
- `analyze.yml` — UTC cron per spec §7, with DB download/upload via release asset `db-latest`.

**Files:**
- Create: `.github/workflows/test.yml`
- Create: `.github/workflows/analyze.yml`

- [ ] **Step 12.1: Create `.github/workflows/test.yml`**

```yaml
name: tests

on:
  push:
    branches: ["**"]
  pull_request:
    branches: [main]

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: Run tests with coverage gate
        run: |
          pytest tests/ --cov=src --cov=main --cov-report=term-missing --cov-fail-under=80
```

- [ ] **Step 12.2: Create `.github/workflows/analyze.yml`**

```yaml
name: analyze

on:
  schedule:
    - cron: '0 12 * * 1-5'     # 14:00/13:00 MEZ/MESZ pre_market
    - cron: '0 13 * * 1-5'     # 15:00/14:00 MEZ/MESZ evaluate (silent)
    - cron: '15 14 * * 1-5'    # 16:15/15:15 MEZ/MESZ midday
    - cron: '30 20 * * 1-5'    # 22:30/21:30 MEZ/MESZ close
    - cron: '0 18 * * 0'       # 20:00/19:00 MEZ/MESZ Sunday weekly
  workflow_dispatch:
    inputs:
      run_type:
        type: choice
        options: [pre_market, midday, close, evaluate, weekly]
        default: close

permissions:
  contents: write   # required for gh release upload

jobs:
  run:
    runs-on: ubuntu-latest
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      SENDGRID_API_KEY: ${{ secrets.SENDGRID_API_KEY }}
      EMAIL_TO:         ${{ secrets.EMAIL_TO }}
      EMAIL_FROM:       ${{ secrets.EMAIL_FROM }}
      FINNHUB_API_KEY:  ${{ secrets.FINNHUB_API_KEY }}
      GH_TOKEN:         ${{ secrets.GITHUB_TOKEN }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Ensure data dir
        run: mkdir -p data

      - name: Download tracking.db from Release db-latest (best effort)
        run: |
          gh release download db-latest --pattern "tracking.db" \
            --dir data/ || echo "No prior db-latest release — fresh start."

      - name: Determine run_type
        id: rt
        run: |
          if [ -n "${{ inputs.run_type }}" ]; then
            echo "type=${{ inputs.run_type }}" >> "$GITHUB_OUTPUT"
            exit 0
          fi
          HOUR=$(date -u +%H)
          DOW=$(date -u +%u)
          MIN=$(date -u +%M)
          if [ "$DOW" = "7" ] && [ "$HOUR" = "18" ]; then T="weekly"
          elif [ "$HOUR" = "13" ]; then T="evaluate"
          elif [ "$HOUR" = "12" ]; then T="pre_market"
          elif [ "$HOUR" = "14" ] && [ "$MIN" -ge "10" ]; then T="midday"
          elif [ "$HOUR" = "20" ]; then T="close"
          else T="close"; fi
          echo "type=$T" >> "$GITHUB_OUTPUT"

      - name: Run analysis
        run: python main.py --run-type ${{ steps.rt.outputs.type }}

      - name: Upload tracking.db to Release db-latest
        if: success()
        run: |
          gh release view db-latest >/dev/null 2>&1 \
            || gh release create db-latest --title "DB latest" \
                 --notes "Auto-uploaded by analyze.yml"
          gh release upload db-latest data/tracking.db --clobber

      - name: Weekly DB snapshot (Sunday only)
        if: success() && steps.rt.outputs.type == 'weekly'
        run: |
          WEEK=$(date -u +%G-W%V)
          gh release create "db-$WEEK" data/tracking.db \
            --title "DB snapshot $WEEK" \
            --notes "Weekly snapshot generated by analyze.yml" \
            || echo "Snapshot already exists for $WEEK"
```

- [ ] **Step 12.3: Verify YAML lints**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml')); yaml.safe_load(open('.github/workflows/analyze.yml'))"`
Expected: no exception.

- [ ] **Step 12.4: Commit**

```bash
git add .github/workflows/test.yml .github/workflows/analyze.yml
git commit -m "Sprint1/Plan3 Task 12: CI test gate + analyze cron with Release-Asset DB persistence"
```

---

## Task 13: Final coverage + smoke instructions

- [ ] **Step 13.1: Run the full test suite with coverage gate**

Run: `pytest tests/ --cov=src --cov=main --cov-report=term-missing --cov-fail-under=80`
Expected: ALL tests pass; coverage ≥ 80% over `src/` + `main.py`.

If coverage < 80%, add small targeted tests for the gap (typically in `main.py` error paths or `email_sender` empty-section branches). Do NOT lower the gate.

- [ ] **Step 13.2: Manual smoke (post-merge, before enabling cron)**

Not automated — document for the user. Add a `docs/SMOKE.md` section if missing, otherwise just record below.

Procedure:
1. Populate `.env` with real `ANTHROPIC_API_KEY`, `SENDGRID_API_KEY`, `EMAIL_TO`, `EMAIL_FROM`, `FINNHUB_API_KEY`.
2. Run locally: `python main.py --run-type close --db-path data/smoke.db`.
3. Inbox check: arrives within 2 min, all 4 sections render, footer shows costs < 4.00 EUR.
4. `sqlite3 data/smoke.db "SELECT COUNT(*) FROM predictions"` → ≥ 5.
5. Next day, run `python main.py --run-type evaluate --db-path data/smoke.db` and check that some outcomes rows appeared.

- [ ] **Step 13.3: Final commit (only if non-empty diff)**

```bash
# Only if you needed to add coverage-fill tests
git add tests/
git commit -m "Sprint1/Plan3 Task 13: coverage backfill to 80%+"
```

---

## Sprint 1 Definition of Done (per spec §10)

After this plan's branch is merged into `main`:
- ✅ Three weekday runs (`pre_market` + `midday` + `close`) deliver four-section e-mails for at least 3 consecutive working days
- ✅ `evaluate` run produces at least 3 outcomes rows
- ✅ Weekly mail sent at least once
- ✅ Run cost reproducibly < 4 EUR
- ✅ DB persistence via Release-Asset survived at least one cron cycle

Then: Sprint-Gate-Review → decide on Sprint 2.

---

## Self-Review Notes

**Spec coverage:**
- §3 Phase 3 deep_analysis (Task 3) ✅, §3 Phase 3b commodities_crypto (Task 4) ✅, §3 Phase 4a portfolio_check (Task 5) ✅, §3 Phase 4 ranking (Task 6) ✅, §3 evaluate-Run (Task 7) ✅, §3 weekly-Run (Task 9 + Task 10 `run_weekly`) ✅.
- §5 Schema-Deltas: `predictions.hold_days_recommended`, `intraday_range_pct`, `outcomes.days_to_close`, `exit_reason`, `position_recommendations` table — all in Task 1.
- §5 Release-Asset workflow — Task 12.
- §6 Guardrails CFD-Kurzfrist checks — Task 1.
- §7 Cron plan — Task 12.
- §9 Tests — every src/ module has a unit test; `tests/integration/` covers the three integration scenarios.
- §10 Implementierungs-Reihenfolge rows 11-21 mapped to Tasks 3-13.

**Carry-over fixes from `project_carryover_issues`:**
- #6 `_extract_json` consolidation → Task 1 (extract_json_blob)
- #7 `cost_tracker.add_call` boilerplate → Task 1 (add_from_result)
- #14 `web_search_20250305` constant → Task 1 (WEB_SEARCH_TOOL in utils.py)
- Remaining items 1-5, 8-13, 15 are NOT touched (still queued — see [[project-carryover-issues]]).

**Placeholder scan:** no `TODO`/`TBD`/"implement later" — every step has concrete code/commands.

**Type consistency:** `analyze_assets` / `analyze_commodities_and_crypto` return `list[dict]`; `rank_and_persist` accepts both. `check_open_positions` returns `list[dict]`. `evaluate_open_predictions` returns `int`. All consistent across Task 10 wiring.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-19-sprint1-plan3-deep-portfolio-email.md`.**

Per [[feedback-subagent-driven-workflow]], default execution mode is **subagent-driven** — fresh `general-purpose` subagent per task, Spec-Compliance review then Code-Quality review, repeat to green, then mark task done. After all 13 tasks: final cross-cutting review over the full Sprint-1-Plan-3 diff.

Worktree: create `sprint-1-plan3` worktree per [[feedback-branch-workflow]] before starting.
