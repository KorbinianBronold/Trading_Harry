# Sprint 1 / Plan 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundation layer of Shares_Future MVP — config, cross-cutting utilities, database layer, data providers, quality guardrails, and cost tracking. All testable in isolation with mocked externals.

**Architecture:** Layered foundation. `config.py` sets constants from env. `utils.py` provides logging/retry/Claude wrapper with prompt caching. `db.py` owns all SQL. Providers implement the `DataProvider` interface (`yfinance`, `finnhub`, plus a stub `paid_provider`). `guardrails.py` and `cost_tracker.py` are pure cross-cutting modules — depend on nothing, used everywhere.

**Tech Stack:** Python 3.11+, sqlite3 (stdlib), pandas, pandas-ta, yfinance, finnhub-python, anthropic SDK, pytest, pytest-cov.

**Spec reference:** `docs/superpowers/specs/2026-05-19-shares-future-mvp-design.md`

---

## File Structure

```
Shares_Future/
├── .env.example                    # ENV-Var template
├── config.py                       # Constants + env loading
├── requirements.txt                # Python deps
├── src/
│   ├── __init__.py
│   ├── utils.py                    # Logging, retry, Claude wrapper
│   ├── db.py                       # SQL schema, migrations, helpers
│   ├── guardrails.py               # Quality checks (R/R, evidence, signal consistency)
│   ├── cost_tracker.py             # Per-run cost accounting + hard cap
│   └── providers/
│       ├── __init__.py
│       ├── base.py                 # DataProvider interface
│       ├── yfinance_provider.py    # OHLC + fundamentals via yfinance
│       ├── finnhub_provider.py     # Earnings calendar
│       └── paid_provider.py        # Stub for Sprint 2
└── tests/
    ├── __init__.py
    ├── conftest.py                 # Shared fixtures (in-memory DB)
    ├── unit/
    │   ├── __init__.py
    │   ├── test_utils.py
    │   ├── test_db.py
    │   ├── test_guardrails.py
    │   ├── test_cost_tracker.py
    │   ├── test_yfinance_provider.py
    │   └── test_finnhub_provider.py
    └── fixtures/
        ├── __init__.py
        ├── sample_ohlc.csv         # 90 days × 5 tickers
        └── mock_claude_responses.json
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `config.py`
- Create: `src/__init__.py`, `src/providers/__init__.py`, `tests/__init__.py`, `tests/unit/__init__.py`, `tests/fixtures/__init__.py`

- [ ] **Step 1.1: Create requirements.txt**

```
anthropic==0.42.0
pandas==2.2.3
pandas-ta==0.3.14b0
yfinance==0.2.50
finnhub-python==2.4.21
sendgrid==6.11.0
python-dotenv==1.0.1
requests==2.32.3
pytest==8.3.4
pytest-cov==6.0.0
pytest-mock==3.14.0
freezegun==1.5.1
```

- [ ] **Step 1.2: Create .env.example**

```
ANTHROPIC_API_KEY=
SENDGRID_API_KEY=
EMAIL_TO=korbinian.bronold@gmail.com
EMAIL_FROM=
FINNHUB_API_KEY=
PAID_API_KEY=
PAID_API_TYPE=polygon
```

- [ ] **Step 1.3: Create .gitignore**

```
.DS_Store
.env
__pycache__/
*.pyc
.pytest_cache/
.coverage
htmlcov/
data/tracking.db
data/*.json
*.egg-info/
.venv/
venv/
```

- [ ] **Step 1.4: Create config.py**

```python
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "tracking.db"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_FROM = os.getenv("EMAIL_FROM")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
PAID_API_KEY = os.getenv("PAID_API_KEY")
PAID_API_TYPE = os.getenv("PAID_API_TYPE", "polygon")

CLAUDE_MODEL_SONNET = "claude-sonnet-4-6"
CLAUDE_MODEL_HAIKU = "claude-haiku-4-5"
CLAUDE_MODEL_OPUS = "claude-opus-4-7"

SIMULATION_ONLY = True

SP500_MVP_TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B",
    "JPM", "V", "UNH", "XOM", "JNJ", "WMT", "MA", "PG", "HD", "LLY",
    "ABBV", "AVGO",
]
COMMODITY_TICKERS = {"Gold": "GC=F", "Silber": "SI=F", "Öl": "CL=F"}
CRYPTO_TICKERS = {
    "Bitcoin": "BTC-USD", "Ethereum": "ETH-USD",
    "Solana": "SOL-USD", "XRP": "XRP-USD",
}

SP500_MIN_MARKET_CAP_B = 5
SP500_MIN_ATR_PCT = 0.8
MAX_DEEP_ANALYSIS = 80
BATCH_SIZE_QUICK = 30

RR_RATIO_DEFAULT = 2.0
RR_RATIO_MIN_HARD = 1.5
MOMENTUM_LONG_MIN = 6.0
MOMENTUM_SHORT_MAX = 4.0

CFD_MARGIN_EUR = 500
CFD_LEVERAGE = 5

MAX_COST_PER_RUN_EUR = 4.00
COST_WARN_THRESHOLD_EUR = 3.00
CLAUDE_PARALLEL_CALLS = 5

YFINANCE_PAUSE_SEC = 0.8
YFINANCE_BATCH_PAUSE = 12

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
```

- [ ] **Step 1.5: Create package init files (all empty)**

Create empty files:
- `src/__init__.py`
- `src/providers/__init__.py`
- `tests/__init__.py`
- `tests/unit/__init__.py`
- `tests/fixtures/__init__.py`

- [ ] **Step 1.6: Verify config imports**

Run: `python -c "from config import DB_PATH, SP500_MVP_TICKERS; print(len(SP500_MVP_TICKERS))"`
Expected: `20`

- [ ] **Step 1.7: Commit**

```bash
git add requirements.txt .env.example .gitignore config.py src/__init__.py src/providers/__init__.py tests/__init__.py tests/unit/__init__.py tests/fixtures/__init__.py
git commit -m "Scaffold project: requirements, config, package layout"
```

---

## Task 2: utils.py — Logging, Retry, Claude Wrapper

**Files:**
- Create: `src/utils.py`
- Create: `tests/unit/test_utils.py`

- [ ] **Step 2.1: Write failing test for retry decorator**

`tests/unit/test_utils.py`:

```python
import time
import pytest
from src.utils import retry_with_backoff


def test_retry_succeeds_on_first_try():
    calls = []

    @retry_with_backoff(max_retries=3, base_delay=0.01)
    def f():
        calls.append(1)
        return "ok"

    assert f() == "ok"
    assert len(calls) == 1


def test_retry_succeeds_after_failures():
    calls = []

    @retry_with_backoff(max_retries=3, base_delay=0.01)
    def f():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("transient")
        return "ok"

    assert f() == "ok"
    assert len(calls) == 3


def test_retry_raises_after_exhaustion():
    @retry_with_backoff(max_retries=2, base_delay=0.01)
    def f():
        raise ValueError("permanent")

    with pytest.raises(ValueError, match="permanent"):
        f()
```

- [ ] **Step 2.2: Run failing tests**

Run: `pytest tests/unit/test_utils.py -v`
Expected: ImportError / NotFound for `retry_with_backoff`.

- [ ] **Step 2.3: Implement retry decorator in src/utils.py**

```python
import logging
import time
from functools import wraps
from typing import Any, Callable

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("shares_future")


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        log.warning(
                            f"{fn.__name__} failed (attempt {attempt + 1}/{max_retries}): {e}. "
                            f"Retrying in {delay:.1f}s"
                        )
                        time.sleep(delay)
            raise last_exc

        return wrapper

    return decorator
```

- [ ] **Step 2.4: Run tests, expect green**

Run: `pytest tests/unit/test_utils.py -v`
Expected: 3 passed.

- [ ] **Step 2.5: Write failing tests for Claude wrapper**

Append to `tests/unit/test_utils.py`:

```python
from unittest.mock import MagicMock, patch
from src.utils import call_claude, ClaudeResult


def test_call_claude_returns_text_and_usage():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="hello world")]
    fake_response.usage.input_tokens = 100
    fake_response.usage.output_tokens = 50
    fake_response.usage.cache_read_input_tokens = 80
    fake_response.usage.cache_creation_input_tokens = 0

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("src.utils._anthropic_client", fake_client):
        result = call_claude(
            model="claude-sonnet-4-6",
            system="you are a helpful assistant",
            user="say hello",
        )

    assert isinstance(result, ClaudeResult)
    assert result.text == "hello world"
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    assert result.cache_read_tokens == 80


def test_call_claude_uses_cache_control_for_system_prompt():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="ok")]
    fake_response.usage.input_tokens = 10
    fake_response.usage.output_tokens = 5
    fake_response.usage.cache_read_input_tokens = 0
    fake_response.usage.cache_creation_input_tokens = 10

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("src.utils._anthropic_client", fake_client):
        call_claude(
            model="claude-haiku-4-5",
            system="long static system prompt",
            user="dynamic question",
        )

    kwargs = fake_client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5"
    assert isinstance(kwargs["system"], list)
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["system"][0]["text"] == "long static system prompt"
```

- [ ] **Step 2.6: Run tests, expect failures**

Run: `pytest tests/unit/test_utils.py -v`
Expected: ImportError for `call_claude`, `ClaudeResult`.

- [ ] **Step 2.7: Implement Claude wrapper**

Append to `src/utils.py`:

```python
from dataclasses import dataclass
from anthropic import Anthropic
import config

_anthropic_client = Anthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else None


@dataclass
class ClaudeResult:
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    model: str


@retry_with_backoff(max_retries=3, base_delay=2.0)
def call_claude(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 4096,
    tools: list | None = None,
) -> ClaudeResult:
    if _anthropic_client is None:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system_blocks,
        messages=[{"role": "user", "content": user}],
    )
    if tools:
        kwargs["tools"] = tools

    response = _anthropic_client.messages.create(**kwargs)

    text_parts = [b.text for b in response.content if hasattr(b, "text")]
    return ClaudeResult(
        text="\n".join(text_parts),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        cache_creation_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
        model=model,
    )
```

- [ ] **Step 2.8: Run tests, expect green**

Run: `pytest tests/unit/test_utils.py -v`
Expected: 5 passed.

- [ ] **Step 2.9: Commit**

```bash
git add src/utils.py tests/unit/test_utils.py
git commit -m "Add utils: retry decorator and Claude wrapper with cache control"
```

---

## Task 3: conftest.py — Shared Test Fixtures

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 3.1: Write conftest with shared fixtures**

```python
import sqlite3
import pytest
from pathlib import Path


@pytest.fixture
def in_memory_db():
    """Fresh in-memory SQLite per test."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """A file-based SQLite path that lives only for the test."""
    return tmp_path / "test.db"


@pytest.fixture
def sample_ticker_data() -> dict:
    """Realistic single-ticker payload as produced by data_collector."""
    return {
        "ticker": "AAPL",
        "price": 178.50,
        "price_change_1d": 1.2,
        "price_change_5d": 3.4,
        "price_change_1m": 5.6,
        "price_change_3m": 12.3,
        "rsi_14": 58.4,
        "rsi_trend": "rising",
        "macd_signal": "bullish_cross",
        "atr_pct": 1.8,
        "bb_position": 0.62,
        "above_sma20": 2.1,
        "above_sma50": 5.4,
        "above_sma200": 12.8,
        "volume_ratio": 1.15,
        "pe_ratio": 28.4,
        "forward_pe": 26.2,
        "analyst_target_upside": 8.5,
        "analyst_consensus": "Buy",
        "market_cap_b": 2800.0,
        "debt_equity": 1.45,
        "sector": "Technology",
        "earnings_in_days": 14,
        "earnings_beat_pct": 4.2,
        "data_quality": "high",
    }
```

- [ ] **Step 3.2: Verify fixtures are loadable**

Create a quick smoke test by running:

```bash
pytest tests/unit/test_utils.py -v --collect-only
```

Expected: Tests collected without conftest errors.

- [ ] **Step 3.3: Commit**

```bash
git add tests/conftest.py
git commit -m "Add shared pytest fixtures: in-memory DB and sample ticker data"
```

---

## Task 4: db.py — Schema Setup & Helpers

**Files:**
- Create: `src/db.py`
- Create: `tests/unit/test_db.py`

- [ ] **Step 4.1: Write failing test for schema initialization**

`tests/unit/test_db.py`:

```python
import sqlite3
import pytest
from src.db import init_schema, get_tables


def test_init_schema_creates_all_tables(in_memory_db):
    init_schema(in_memory_db)
    tables = get_tables(in_memory_db)
    expected = {
        "price_history",
        "technical_indicators",
        "fundamentals",
        "news_summaries",
        "trend_analyses",
        "market_context",
        "predictions",
        "outcomes",
        "skipped_tickers",
        "prompt_versions",
        "cost_tracking",
    }
    assert expected.issubset(set(tables))


def test_init_schema_is_idempotent(in_memory_db):
    init_schema(in_memory_db)
    init_schema(in_memory_db)
    tables = get_tables(in_memory_db)
    assert "predictions" in tables
```

- [ ] **Step 4.2: Run failing tests**

Run: `pytest tests/unit/test_db.py -v`
Expected: ImportError.

- [ ] **Step 4.3: Implement db.py schema**

```python
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS price_history (
    ticker TEXT NOT NULL, date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL NOT NULL, volume INTEGER,
    source TEXT DEFAULT 'yfinance',
    UNIQUE(ticker, date)
);

CREATE TABLE IF NOT EXISTS technical_indicators (
    ticker TEXT NOT NULL, date TEXT NOT NULL,
    rsi_14 REAL, macd_signal TEXT, atr_pct REAL,
    bb_position REAL, above_sma20 REAL, above_sma50 REAL, above_sma200 REAL,
    volume_ratio REAL,
    UNIQUE(ticker, date)
);

CREATE TABLE IF NOT EXISTS fundamentals (
    ticker TEXT NOT NULL, report_date TEXT NOT NULL,
    eps_actual REAL, eps_estimated REAL, eps_beat_pct REAL,
    revenue_actual REAL, guidance_raised BOOLEAN,
    pe_ratio REAL, forward_pe REAL, debt_equity REAL,
    UNIQUE(ticker, report_date)
);

CREATE TABLE IF NOT EXISTS news_summaries (
    ticker TEXT, date TEXT NOT NULL, run_type TEXT,
    summary TEXT NOT NULL, sentiment TEXT, source TEXT, market_impact TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trend_analyses (
    date TEXT NOT NULL, run_type TEXT, trend_name TEXT NOT NULL,
    strength INTEGER, duration_estimate TEXT, summary TEXT,
    beneficiary_tickers TEXT, negative_tickers TEXT, next_catalyst TEXT,
    UNIQUE(date, trend_name)
);

CREATE TABLE IF NOT EXISTS market_context (
    date TEXT NOT NULL, run_type TEXT NOT NULL,
    sp500_change_pct REAL, vix_level REAL, market_regime TEXT,
    oil_price REAL, gold_price REAL, btc_price REAL,
    fear_greed_value INTEGER, policy_risk_level TEXT,
    sector_rotation_in TEXT, sector_rotation_out TEXT, macro_summary TEXT,
    UNIQUE(date, run_type)
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL, run_type TEXT NOT NULL, asset_class TEXT,
    ticker TEXT NOT NULL, direction TEXT NOT NULL,
    entry_price REAL, tp_price REAL, tp_pct REAL,
    sl_price REAL, sl_pct REAL, rr_ratio REAL,
    total_score REAL, probability_pct INTEGER, confidence TEXT,
    score_market_env REAL, score_company REAL, score_valuation REAL,
    score_momentum REAL, score_risk REAL, score_sector REAL,
    score_catalyst REAL, score_policy REAL,
    atr_pct REAL, rsi_at_entry REAL, volume_ratio REAL,
    market_regime TEXT, vix_at_prediction REAL, sector TEXT,
    trend_boost TEXT, earnings_warning BOOLEAN, summary TEXT,
    learnable BOOLEAN DEFAULT 1,
    status TEXT DEFAULT 'open',
    closed_date TEXT, closed_price REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id INTEGER REFERENCES predictions(id),
    direction TEXT, evaluated_date TEXT NOT NULL,
    price_after_eod REAL, price_change_eod_pct REAL,
    correct_direction_eod BOOLEAN,
    tp_hit BOOLEAN, sl_hit BOOLEAN,
    days_to_close INTEGER, exit_reason TEXT,
    profit_loss_eur REAL,
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS skipped_tickers (
    ticker TEXT NOT NULL, date TEXT NOT NULL, run_type TEXT,
    reason TEXT, learnable BOOLEAN DEFAULT 0,
    skip_count INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_name TEXT NOT NULL, version INTEGER NOT NULL,
    content TEXT NOT NULL, created_date TEXT,
    long_accuracy REAL, short_accuracy REAL, total_predictions INTEGER,
    is_active BOOLEAN DEFAULT 1, replaced_date TEXT,
    UNIQUE(prompt_name, version)
);

CREATE TABLE IF NOT EXISTS cost_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL, run_type TEXT NOT NULL,
    total_eur REAL, claude_eur REAL, web_search_eur REAL,
    input_tokens INTEGER, output_tokens INTEGER,
    cache_read_tokens INTEGER, cache_hit_rate REAL,
    web_search_calls INTEGER, aborted_at_phase TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_predictions_status ON predictions(status);
CREATE INDEX IF NOT EXISTS idx_predictions_date ON predictions(date);
CREATE INDEX IF NOT EXISTS idx_price_history_ticker_date ON price_history(ticker, date);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def get_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def upsert_price_history(
    conn: sqlite3.Connection, ticker: str, date: str,
    open_: float, high: float, low: float, close: float, volume: int,
    source: str = "yfinance",
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO price_history
           (ticker, date, open, high, low, close, volume, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticker, date, open_, high, low, close, volume, source),
    )


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
    ]
    placeholders = ", ".join(["?"] * len(cols))
    values = [pred.get(c) for c in cols]
    cur = conn.execute(
        f"INSERT INTO predictions ({', '.join(cols)}) VALUES ({placeholders})",
        values,
    )
    conn.commit()
    return cur.lastrowid


def load_open_predictions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM predictions WHERE status = 'open' AND learnable = 1"
    ).fetchall()


def close_prediction(
    conn: sqlite3.Connection, pred_id: int, status: str,
    closed_date: str, closed_price: float | None,
) -> None:
    conn.execute(
        "UPDATE predictions SET status=?, closed_date=?, closed_price=? WHERE id=?",
        (status, closed_date, closed_price, pred_id),
    )
    conn.commit()


def save_outcome(conn: sqlite3.Connection, outcome: dict) -> int:
    cols = [
        "prediction_id", "direction", "evaluated_date",
        "price_after_eod", "price_change_eod_pct", "correct_direction_eod",
        "tp_hit", "sl_hit", "days_to_close", "exit_reason", "profit_loss_eur",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    values = [outcome.get(c) for c in cols]
    cur = conn.execute(
        f"INSERT INTO outcomes ({', '.join(cols)}) VALUES ({placeholders})",
        values,
    )
    conn.commit()
    return cur.lastrowid


def save_cost_tracking(conn: sqlite3.Connection, row: dict) -> None:
    cols = [
        "date", "run_type", "total_eur", "claude_eur", "web_search_eur",
        "input_tokens", "output_tokens", "cache_read_tokens", "cache_hit_rate",
        "web_search_calls", "aborted_at_phase",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    values = [row.get(c) for c in cols]
    conn.execute(
        f"INSERT INTO cost_tracking ({', '.join(cols)}) VALUES ({placeholders})",
        values,
    )
    conn.commit()


def cleanup_old_data(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DELETE FROM news_summaries WHERE date < date('now', '-90 days');
        DELETE FROM trend_analyses WHERE date < date('now', '-180 days');
        DELETE FROM skipped_tickers WHERE date < date('now', '-30 days');
        """
    )
    conn.commit()
```

- [ ] **Step 4.4: Run schema tests, expect green**

Run: `pytest tests/unit/test_db.py -v`
Expected: 2 passed.

- [ ] **Step 4.5: Add tests for prediction save/load/close + outcome roundtrip**

Append to `tests/unit/test_db.py`:

```python
from src.db import (
    init_schema, save_prediction, load_open_predictions,
    close_prediction, save_outcome, save_cost_tracking,
)


def _sample_pred() -> dict:
    return {
        "date": "2026-05-19", "run_type": "pre_market", "asset_class": "stock",
        "ticker": "AAPL", "direction": "long",
        "entry_price": 178.5, "tp_price": 182.0, "tp_pct": 2.0,
        "sl_price": 176.7, "sl_pct": 1.0, "rr_ratio": 2.0,
        "total_score": 7.8, "probability_pct": 65, "confidence": "high",
        "score_market_env": 7.0, "score_company": 8.5, "score_valuation": 6.5,
        "score_momentum": 8.0, "score_risk": 6.0, "score_sector": 7.5,
        "score_catalyst": 7.0, "score_policy": 5.5,
        "atr_pct": 1.8, "rsi_at_entry": 58.4, "volume_ratio": 1.15,
        "market_regime": "risk_on", "vix_at_prediction": 14.2, "sector": "Technology",
        "trend_boost": "AI", "earnings_warning": False,
        "summary": "Test prediction", "learnable": True,
    }


def test_save_and_load_prediction(in_memory_db):
    init_schema(in_memory_db)
    pid = save_prediction(in_memory_db, _sample_pred())
    assert pid == 1
    opens = load_open_predictions(in_memory_db)
    assert len(opens) == 1
    assert opens[0]["ticker"] == "AAPL"
    assert opens[0]["status"] == "open"


def test_close_prediction_changes_status(in_memory_db):
    init_schema(in_memory_db)
    pid = save_prediction(in_memory_db, _sample_pred())
    close_prediction(in_memory_db, pid, "closed_tp", "2026-05-20", 182.0)
    opens = load_open_predictions(in_memory_db)
    assert len(opens) == 0
    row = in_memory_db.execute(
        "SELECT * FROM predictions WHERE id=?", (pid,)
    ).fetchone()
    assert row["status"] == "closed_tp"
    assert row["closed_price"] == 182.0


def test_save_outcome_roundtrip(in_memory_db):
    init_schema(in_memory_db)
    pid = save_prediction(in_memory_db, _sample_pred())
    save_outcome(in_memory_db, {
        "prediction_id": pid, "direction": "long",
        "evaluated_date": "2026-05-20",
        "price_after_eod": 182.0, "price_change_eod_pct": 1.96,
        "correct_direction_eod": True,
        "tp_hit": True, "sl_hit": False,
        "days_to_close": 1, "exit_reason": "tp_hit",
        "profit_loss_eur": 50.0,
    })
    row = in_memory_db.execute(
        "SELECT * FROM outcomes WHERE prediction_id=?", (pid,)
    ).fetchone()
    assert row["exit_reason"] == "tp_hit"
    assert row["days_to_close"] == 1


def test_save_cost_tracking_roundtrip(in_memory_db):
    init_schema(in_memory_db)
    save_cost_tracking(in_memory_db, {
        "date": "2026-05-19", "run_type": "pre_market",
        "total_eur": 2.84, "claude_eur": 2.50, "web_search_eur": 0.34,
        "input_tokens": 142000, "output_tokens": 63000,
        "cache_read_tokens": 95000, "cache_hit_rate": 0.87,
        "web_search_calls": 23, "aborted_at_phase": None,
    })
    row = in_memory_db.execute("SELECT * FROM cost_tracking").fetchone()
    assert row["total_eur"] == 2.84
    assert row["cache_hit_rate"] == 0.87
```

- [ ] **Step 4.6: Run all db tests, expect green**

Run: `pytest tests/unit/test_db.py -v`
Expected: 6 passed.

- [ ] **Step 4.7: Commit**

```bash
git add src/db.py tests/unit/test_db.py
git commit -m "Add db.py: full schema with predictions/outcomes/cost_tracking helpers"
```

---

## Task 5: providers — base, yfinance, finnhub, paid stub

**Files:**
- Create: `src/providers/base.py`
- Create: `src/providers/yfinance_provider.py`
- Create: `src/providers/finnhub_provider.py`
- Create: `src/providers/paid_provider.py`
- Create: `tests/unit/test_yfinance_provider.py`
- Create: `tests/unit/test_finnhub_provider.py`

- [ ] **Step 5.1: Define DataProvider interface in base.py**

```python
from abc import ABC, abstractmethod
from typing import Any
import pandas as pd


class DataProvider(ABC):
    @abstractmethod
    def get_price_history(self, ticker: str, days: int = 90) -> pd.DataFrame | None:
        ...

    @abstractmethod
    def get_fundamentals(self, ticker: str) -> dict:
        ...

    @abstractmethod
    def get_earnings_calendar(self, ticker: str) -> dict:
        ...

    @abstractmethod
    def get_last_available_date(self, ticker: str) -> str | None:
        ...
```

- [ ] **Step 5.2: Write failing test for yfinance provider OHLC parsing**

`tests/unit/test_yfinance_provider.py`:

```python
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from src.providers.yfinance_provider import YFinanceProvider


def _make_hist_df(rows: int = 60) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=rows, freq="B")
    return pd.DataFrame({
        "Open":  [100 + i * 0.5 for i in range(rows)],
        "High":  [101 + i * 0.5 for i in range(rows)],
        "Low":   [ 99 + i * 0.5 for i in range(rows)],
        "Close": [100 + i * 0.5 for i in range(rows)],
        "Volume":[1_000_000 + i * 1000 for i in range(rows)],
    }, index=idx)


def test_get_price_history_returns_dataframe():
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = _make_hist_df(60)

    with patch("yfinance.Ticker", return_value=fake_ticker), \
         patch("time.sleep"):  # no real delays in tests
        p = YFinanceProvider()
        df = p.get_price_history("AAPL", days=90)

    assert df is not None
    assert "Close" in df.columns
    assert len(df) == 60


def test_get_price_history_returns_none_on_insufficient_data():
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = _make_hist_df(10)  # < 20 → reject

    with patch("yfinance.Ticker", return_value=fake_ticker), \
         patch("time.sleep"):
        p = YFinanceProvider()
        df = p.get_price_history("AAPL", days=90)

    assert df is None


def test_get_price_history_retries_on_error():
    fake_ticker = MagicMock()
    fake_ticker.history.side_effect = [
        Exception("transient"),
        _make_hist_df(60),
    ]

    with patch("yfinance.Ticker", return_value=fake_ticker), \
         patch("time.sleep"):
        p = YFinanceProvider()
        df = p.get_price_history("AAPL", days=90)

    assert df is not None
    assert fake_ticker.history.call_count == 2


def test_get_fundamentals_extracts_known_fields():
    fake_ticker = MagicMock()
    fake_ticker.info = {
        "trailingPE": 28.4, "forwardPE": 26.2,
        "marketCap": 2_800_000_000_000,
        "debtToEquity": 145.0,
        "sector": "Technology",
        "targetMeanPrice": 195.0, "currentPrice": 180.0,
        "recommendationKey": "buy",
    }

    with patch("yfinance.Ticker", return_value=fake_ticker), \
         patch("time.sleep"):
        p = YFinanceProvider()
        f = p.get_fundamentals("AAPL")

    assert f["pe_ratio"] == 28.4
    assert f["forward_pe"] == 26.2
    assert f["market_cap_b"] == 2800.0
    assert f["sector"] == "Technology"
    assert f["consensus"] == "buy"
    assert f["analyst_upside"] == pytest.approx((195 - 180) / 180 * 100)
```

- [ ] **Step 5.3: Run failing tests**

Run: `pytest tests/unit/test_yfinance_provider.py -v`
Expected: ImportError.

- [ ] **Step 5.4: Implement YFinanceProvider**

`src/providers/yfinance_provider.py`:

```python
import random
import time
import logging
import pandas as pd
import yfinance as yf
from src.providers.base import DataProvider

log = logging.getLogger("shares_future.yfinance")


class YFinanceProvider(DataProvider):
    PAUSE_BETWEEN_TICKERS = 0.8
    PAUSE_BETWEEN_BATCHES = 12
    PAUSE_ON_ERROR = 30
    MAX_RETRIES = 3
    JITTER_MAX = 0.5
    MIN_ROWS = 20

    def get_price_history(self, ticker: str, days: int = 90) -> pd.DataFrame | None:
        for attempt in range(self.MAX_RETRIES):
            try:
                time.sleep(self.PAUSE_BETWEEN_TICKERS + random.uniform(0, self.JITTER_MAX))
                hist = yf.Ticker(ticker).history(period=f"{days}d")
                if hist is None or hist.empty or len(hist) < self.MIN_ROWS:
                    rows = len(hist) if hist is not None else 0
                    raise ValueError(f"Insufficient data: {rows} rows")
                return hist
            except Exception as e:
                log.warning(f"{ticker}: yfinance attempt {attempt + 1} failed: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.PAUSE_ON_ERROR * (2 ** attempt))
        log.error(f"{ticker}: all {self.MAX_RETRIES} yfinance attempts failed")
        return None

    def get_fundamentals(self, ticker: str) -> dict:
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception as e:
            log.warning(f"{ticker}: fundamentals fetch failed: {e}")
            return {}

        target = info.get("targetMeanPrice")
        current = info.get("currentPrice")
        upside = ((target - current) / current * 100) if target and current else None
        market_cap = info.get("marketCap")
        return {
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "market_cap_b": (market_cap / 1e9) if market_cap else None,
            "debt_equity": (info.get("debtToEquity") / 100) if info.get("debtToEquity") else None,
            "sector": info.get("sector", "Unknown"),
            "analyst_upside": upside,
            "consensus": info.get("recommendationKey"),
        }

    def get_earnings_calendar(self, ticker: str) -> dict:
        # yfinance earnings calendar is unreliable; handled by FinnhubProvider.
        return {"days_to_next": None, "last_beat_pct": None}

    def get_last_available_date(self, ticker: str) -> str | None:
        df = self.get_price_history(ticker, days=5)
        if df is None or df.empty:
            return None
        return df.index[-1].strftime("%Y-%m-%d")
```

- [ ] **Step 5.5: Run yfinance tests, expect green**

Run: `pytest tests/unit/test_yfinance_provider.py -v`
Expected: 4 passed.

- [ ] **Step 5.6: Write failing tests for FinnhubProvider**

`tests/unit/test_finnhub_provider.py`:

```python
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from src.providers.finnhub_provider import FinnhubProvider


def test_get_earnings_calendar_returns_days_to_next():
    future_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
    fake_client = MagicMock()
    fake_client.earnings_calendar.return_value = {
        "earningsCalendar": [
            {"symbol": "AAPL", "date": future_date,
             "epsActual": None, "epsEstimate": 2.10},
        ]
    }

    with patch("src.providers.finnhub_provider._client", fake_client):
        p = FinnhubProvider()
        out = p.get_earnings_calendar("AAPL")

    assert out["days_to_next"] == 14
    assert out["last_beat_pct"] is None


def test_get_earnings_calendar_handles_empty_response():
    fake_client = MagicMock()
    fake_client.earnings_calendar.return_value = {"earningsCalendar": []}

    with patch("src.providers.finnhub_provider._client", fake_client):
        p = FinnhubProvider()
        out = p.get_earnings_calendar("AAPL")

    assert out == {"days_to_next": None, "last_beat_pct": None}


def test_get_earnings_calendar_handles_api_error():
    fake_client = MagicMock()
    fake_client.earnings_calendar.side_effect = Exception("rate limit")

    with patch("src.providers.finnhub_provider._client", fake_client):
        p = FinnhubProvider()
        out = p.get_earnings_calendar("AAPL")

    assert out == {"days_to_next": None, "last_beat_pct": None}


def test_get_earnings_calendar_returns_beat_pct_when_actual_present():
    past_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    fake_client = MagicMock()
    fake_client.earnings_calendar.return_value = {
        "earningsCalendar": [
            {"symbol": "AAPL", "date": past_date,
             "epsActual": 2.20, "epsEstimate": 2.00},
        ]
    }

    with patch("src.providers.finnhub_provider._client", fake_client):
        p = FinnhubProvider()
        out = p.get_earnings_calendar("AAPL")

    # past beat: actual 2.20 vs estimate 2.00 → +10%
    assert out["last_beat_pct"] == 10.0
```

- [ ] **Step 5.7: Run failing tests**

Run: `pytest tests/unit/test_finnhub_provider.py -v`
Expected: ImportError.

- [ ] **Step 5.8: Implement FinnhubProvider**

`src/providers/finnhub_provider.py`:

```python
import logging
from datetime import datetime, timedelta
import finnhub
import config
from src.providers.base import DataProvider

log = logging.getLogger("shares_future.finnhub")

_client = (
    finnhub.Client(api_key=config.FINNHUB_API_KEY)
    if config.FINNHUB_API_KEY else None
)


class FinnhubProvider(DataProvider):
    LOOKBACK_DAYS = 90
    LOOKAHEAD_DAYS = 60

    def get_price_history(self, ticker, days=90):
        raise NotImplementedError("FinnhubProvider only supplies earnings")

    def get_fundamentals(self, ticker):
        return {}

    def get_last_available_date(self, ticker):
        return None

    def get_earnings_calendar(self, ticker: str) -> dict:
        if _client is None:
            return {"days_to_next": None, "last_beat_pct": None}
        today = datetime.now().date()
        try:
            resp = _client.earnings_calendar(
                _from=(today - timedelta(days=self.LOOKBACK_DAYS)).isoformat(),
                to=(today + timedelta(days=self.LOOKAHEAD_DAYS)).isoformat(),
                symbol=ticker,
            )
        except Exception as e:
            log.warning(f"{ticker}: finnhub earnings call failed: {e}")
            return {"days_to_next": None, "last_beat_pct": None}

        items = (resp or {}).get("earningsCalendar", [])
        if not items:
            return {"days_to_next": None, "last_beat_pct": None}

        future = []
        last_beat = None
        for it in items:
            try:
                d = datetime.strptime(it["date"], "%Y-%m-%d").date()
            except (KeyError, ValueError):
                continue
            if d >= today:
                future.append((d, it))
            else:
                actual = it.get("epsActual")
                est = it.get("epsEstimate")
                if actual is not None and est and est != 0:
                    last_beat = round((actual - est) / est * 100, 2)

        days_to_next = None
        if future:
            future.sort(key=lambda x: x[0])
            days_to_next = (future[0][0] - today).days

        return {"days_to_next": days_to_next, "last_beat_pct": last_beat}
```

- [ ] **Step 5.9: Run finnhub tests, expect green**

Run: `pytest tests/unit/test_finnhub_provider.py -v`
Expected: 4 passed.

- [ ] **Step 5.10: Implement paid_provider stub**

`src/providers/paid_provider.py`:

```python
from src.providers.base import DataProvider


class PaidProvider(DataProvider):
    """Stub. Real implementation arrives in Sprint 2 (historical loader)."""

    def get_price_history(self, ticker, days=90):
        raise NotImplementedError("PaidProvider is stubbed in Sprint 1")

    def get_fundamentals(self, ticker):
        raise NotImplementedError("PaidProvider is stubbed in Sprint 1")

    def get_earnings_calendar(self, ticker):
        raise NotImplementedError("PaidProvider is stubbed in Sprint 1")

    def get_last_available_date(self, ticker):
        raise NotImplementedError("PaidProvider is stubbed in Sprint 1")
```

- [ ] **Step 5.11: Commit**

```bash
git add src/providers/ tests/unit/test_yfinance_provider.py tests/unit/test_finnhub_provider.py
git commit -m "Add DataProvider interface plus yfinance, finnhub, paid stub providers"
```

---

## Task 6: guardrails.py — Quality Checks

**Files:**
- Create: `src/guardrails.py`
- Create: `tests/unit/test_guardrails.py`

- [ ] **Step 6.1: Write failing test cases (one per rule)**

`tests/unit/test_guardrails.py`:

```python
import pytest
from src.guardrails import GuardrailsChecker


def _valid_long() -> dict:
    return {
        "ticker": "AAPL", "direction": "long", "confidence": "high",
        "current_price": 178.5, "tp_price": 182.0, "sl_price": 176.7,
        "rr_ratio": 1.94,
        "total_score": 7.5, "summary": "Test reason",
        "sources_used": ["Reuters", "Bloomberg"],
        "signal_consistency_check": "pass",
        "data_quality": "high",
        "scores": {
            "market_environment": {"value": 7, "evidence": ["VIX 14", "SP500 +0.5%"]},
            "company_quality":    {"value": 8, "evidence": ["EPS beat 5%", "Guidance raised"]},
            "valuation":          {"value": 6, "evidence": ["PE 28", "Target +8%"]},
            "momentum":           {"value": 8, "evidence": ["RSI 58", "SMA200 +12%"]},
            "risk":               {"value": 6, "evidence": ["ATR 1.8", "D/E 1.4"]},
            "sector_trend":       {"value": 7, "evidence": ["XLK +1%", "Inflows positive"]},
            "catalyst":           {"value": 7, "evidence": ["Earnings 14d", "WWDC June"]},
            "policy_risk":        {"value": 5, "evidence": ["No new tariffs", "Stable rates"]},
        },
    }


def test_valid_long_passes():
    ok, errors = GuardrailsChecker().check_analysis(_valid_long())
    assert ok, errors


def test_missing_required_field_fails():
    a = _valid_long()
    del a["summary"]
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("summary" in e.lower() for e in errors)


def test_too_few_sources_fails():
    a = _valid_long()
    a["sources_used"] = ["Reuters"]
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("source" in e.lower() for e in errors)


def test_too_few_evidence_per_dimension_fails():
    a = _valid_long()
    a["scores"]["momentum"]["evidence"] = ["only one"]
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("momentum" in e.lower() for e in errors)


def test_long_with_tp_below_entry_fails():
    a = _valid_long()
    a["tp_price"] = 175.0  # below current_price 178.5
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("tp" in e.lower() for e in errors)


def test_long_with_sl_above_entry_fails():
    a = _valid_long()
    a["sl_price"] = 180.0  # above current_price 178.5
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("sl" in e.lower() for e in errors)


def test_rr_ratio_below_hard_minimum_fails():
    a = _valid_long()
    a["rr_ratio"] = 1.2  # below 1.5 hard min
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("r/r" in e.lower() or "rr" in e.lower() for e in errors)


def test_high_confidence_with_low_data_quality_fails():
    a = _valid_long()
    a["data_quality"] = "low"
    a["confidence"] = "high"
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("confidence" in e.lower() for e in errors)


def test_signal_consistency_long_low_momentum_fails():
    a = _valid_long()
    a["scores"]["momentum"]["value"] = 5  # below 6.0 → long signal inconsistent
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("signal_consistency" in e.lower() or "momentum" in e.lower() for e in errors)


def test_signal_consistency_short_high_momentum_fails():
    a = _valid_long()
    a["direction"] = "short"
    a["tp_price"] = 170.0  # below entry
    a["sl_price"] = 181.0  # above entry
    a["rr_ratio"] = 1.94
    # momentum is 8 → too high for short, should fail consistency
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("momentum" in e.lower() for e in errors)
```

- [ ] **Step 6.2: Run failing tests**

Run: `pytest tests/unit/test_guardrails.py -v`
Expected: ImportError.

- [ ] **Step 6.3: Implement GuardrailsChecker**

`src/guardrails.py`:

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

    REQUIRED_FIELDS = (
        "ticker", "direction", "confidence", "current_price",
        "tp_price", "sl_price", "rr_ratio", "total_score", "summary",
        "sources_used", "signal_consistency_check", "scores",
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

        return len(errors) == 0, errors
```

- [ ] **Step 6.4: Run all guardrails tests, expect green**

Run: `pytest tests/unit/test_guardrails.py -v`
Expected: 10 passed.

- [ ] **Step 6.5: Commit**

```bash
git add src/guardrails.py tests/unit/test_guardrails.py
git commit -m "Add guardrails with required-field, source, evidence, R/R, signal-consistency checks"
```

---

## Task 7: cost_tracker.py — Per-Run Cost Tracking & Hard Cap

**Files:**
- Create: `src/cost_tracker.py`
- Create: `tests/unit/test_cost_tracker.py`

- [ ] **Step 7.1: Write failing tests**

`tests/unit/test_cost_tracker.py`:

```python
import pytest
from src.cost_tracker import CostTracker, CostCapExceeded


def test_zero_state():
    t = CostTracker()
    assert t.total_eur == 0.0
    assert t.input_tokens == 0
    assert t.web_search_calls == 0


def test_add_haiku_call_accumulates_eur_and_tokens():
    t = CostTracker(hard_cap_eur=10.0)
    t.add_call(
        model="claude-haiku-4-5",
        input_tokens=10_000, output_tokens=2_000,
        cache_read_tokens=0, web_search_calls=0,
    )
    assert t.input_tokens == 10_000
    assert t.output_tokens == 2_000
    assert t.total_eur > 0


def test_cache_read_tokens_priced_lower_than_fresh_input():
    fresh = CostTracker()
    fresh.add_call(
        model="claude-sonnet-4-6",
        input_tokens=10_000, output_tokens=0,
        cache_read_tokens=0, web_search_calls=0,
    )
    cached = CostTracker()
    cached.add_call(
        model="claude-sonnet-4-6",
        input_tokens=10_000, output_tokens=0,
        cache_read_tokens=9_000, web_search_calls=0,
    )
    assert cached.total_eur < fresh.total_eur


def test_hard_cap_raises_when_exceeded():
    t = CostTracker(hard_cap_eur=0.01)
    with pytest.raises(CostCapExceeded):
        t.add_call(
            model="claude-sonnet-4-6",
            input_tokens=100_000, output_tokens=100_000,
            cache_read_tokens=0, web_search_calls=0,
        )


def test_web_search_calls_are_counted_and_billed():
    t = CostTracker(hard_cap_eur=10.0)
    t.add_call(
        model="claude-sonnet-4-6",
        input_tokens=0, output_tokens=0,
        cache_read_tokens=0, web_search_calls=5,
    )
    assert t.web_search_calls == 5
    assert t.web_search_eur > 0


def test_persist_returns_summary_dict():
    t = CostTracker()
    t.add_call(
        model="claude-haiku-4-5",
        input_tokens=1000, output_tokens=500,
        cache_read_tokens=200, web_search_calls=1,
    )
    summary = t.summary(run_type="pre_market", date="2026-05-19")
    assert summary["run_type"] == "pre_market"
    assert summary["date"] == "2026-05-19"
    assert summary["total_eur"] > 0
    assert "cache_hit_rate" in summary
    assert 0 <= summary["cache_hit_rate"] <= 1
```

- [ ] **Step 7.2: Run failing tests**

Run: `pytest tests/unit/test_cost_tracker.py -v`
Expected: ImportError.

- [ ] **Step 7.3: Implement CostTracker**

`src/cost_tracker.py`:

```python
from dataclasses import dataclass, field
import config

USD_PER_EUR = 1.10

# Per million tokens, USD. Use Anthropic published rates (May 2026).
MODEL_PRICING = {
    "claude-opus-4-7":   {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_write": 18.75},
    "claude-sonnet-4-6": {"input":  3.00, "output": 15.00, "cache_read": 0.30, "cache_write":  3.75},
    "claude-haiku-4-5":  {"input":  1.00, "output":  5.00, "cache_read": 0.10, "cache_write":  1.25},
}

WEB_SEARCH_USD_PER_CALL = 0.01  # Approx Anthropic web search billing


class CostCapExceeded(Exception):
    pass


@dataclass
class CostTracker:
    hard_cap_eur: float = config.MAX_COST_PER_RUN_EUR
    warn_threshold_eur: float = config.COST_WARN_THRESHOLD_EUR

    total_eur: float = 0.0
    claude_eur: float = 0.0
    web_search_eur: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    web_search_calls: int = 0
    aborted_at_phase: str | None = None
    _warned: bool = field(default=False, repr=False)

    def add_call(
        self,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
        web_search_calls: int = 0,
    ) -> None:
        pricing = MODEL_PRICING.get(model)
        if pricing is None:
            raise ValueError(f"Unknown model pricing: {model}")

        fresh_input = max(0, input_tokens - cache_read_tokens)
        usd_input  = fresh_input          / 1_000_000 * pricing["input"]
        usd_output = output_tokens         / 1_000_000 * pricing["output"]
        usd_cache_read   = cache_read_tokens     / 1_000_000 * pricing["cache_read"]
        usd_cache_write  = cache_creation_tokens / 1_000_000 * pricing["cache_write"]
        usd_web    = web_search_calls * WEB_SEARCH_USD_PER_CALL

        usd_total = usd_input + usd_output + usd_cache_read + usd_cache_write + usd_web
        eur_total = usd_total / USD_PER_EUR

        self.claude_eur     += (usd_input + usd_output + usd_cache_read + usd_cache_write) / USD_PER_EUR
        self.web_search_eur += usd_web / USD_PER_EUR
        self.total_eur      += eur_total

        self.input_tokens      += input_tokens
        self.output_tokens     += output_tokens
        self.cache_read_tokens += cache_read_tokens
        self.web_search_calls  += web_search_calls

        if self.total_eur > self.hard_cap_eur:
            raise CostCapExceeded(
                f"Run cost {self.total_eur:.2f} EUR > cap {self.hard_cap_eur:.2f} EUR"
            )
        if not self._warned and self.total_eur > self.warn_threshold_eur:
            self._warned = True

    def summary(self, run_type: str, date: str) -> dict:
        hit_rate = 0.0
        if self.input_tokens > 0:
            hit_rate = self.cache_read_tokens / self.input_tokens
        return {
            "date": date, "run_type": run_type,
            "total_eur": round(self.total_eur, 4),
            "claude_eur": round(self.claude_eur, 4),
            "web_search_eur": round(self.web_search_eur, 4),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_hit_rate": round(hit_rate, 4),
            "web_search_calls": self.web_search_calls,
            "aborted_at_phase": self.aborted_at_phase,
        }
```

- [ ] **Step 7.4: Run tests, expect green**

Run: `pytest tests/unit/test_cost_tracker.py -v`
Expected: 6 passed.

- [ ] **Step 7.5: Commit**

```bash
git add src/cost_tracker.py tests/unit/test_cost_tracker.py
git commit -m "Add CostTracker with model pricing, cache discount, hard cap, and summary"
```

---

## Task 8: Final Foundation Check — All Tests Green + Coverage

- [ ] **Step 8.1: Run all foundation tests**

Run: `pytest tests/unit/ -v`
Expected: All tests in `test_utils.py`, `test_db.py`, `test_guardrails.py`, `test_cost_tracker.py`, `test_yfinance_provider.py`, `test_finnhub_provider.py` pass.

- [ ] **Step 8.2: Check coverage of foundation modules**

Run: `pytest tests/unit/ --cov=src --cov-report=term-missing`
Expected: Modules `src/utils.py`, `src/db.py`, `src/guardrails.py`, `src/cost_tracker.py`, `src/providers/*` each ≥80% coverage.

- [ ] **Step 8.3: If coverage gaps exist, add tests for uncovered branches**

For each module under 80%: look at `--cov-report=term-missing` output and add tests for the listed line numbers. Do NOT lower the threshold. Common gaps: error paths in retry, edge cases in fundamentals parsing.

- [ ] **Step 8.4: Final commit if coverage tests added**

```bash
git add tests/unit/
git commit -m "Add coverage tests for foundation modules"
```

---

## Self-Review Notes

**Spec coverage** (against `docs/superpowers/specs/2026-05-19-shares-future-mvp-design.md`):

| Spec section | Task | Status |
|---|---|---|
| §2 DataProvider Interface | Task 5 | ✅ |
| §2 yfinance_provider with retry/jitter | Task 5 | ✅ |
| §2 finnhub_provider for earnings | Task 5 | ✅ |
| §2 paid_provider stub for Sprint 2 | Task 5 | ✅ |
| §2 db.py centralizes SQL | Task 4 | ✅ |
| §2 guardrails cross-cutting | Task 6 | ✅ |
| §2 cost_tracker cross-cutting | Task 7 | ✅ |
| §2 utils.py Claude wrapper with caching | Task 2 | ✅ |
| §4 Prompt caching `cache_control: ephemeral` | Task 2 | ✅ |
| §4 Mixed-model pricing (Haiku/Sonnet/Opus) | Task 7 | ✅ |
| §4 Hard cap with abort | Task 7 | ✅ |
| §5 Schema deltas: status, closed_date, closed_price | Task 4 | ✅ |
| §5 outcomes.days_to_close, exit_reason | Task 4 | ✅ |
| §5 cost_tracking as table | Task 4 | ✅ |
| §5 cleanup_old_data | Task 4 | ✅ |
| §6 R/R ≥ 1.5 hard min | Task 6 | ✅ |
| §6 momentum_long ≥ 6, momentum_short ≤ 4 | Task 6 | ✅ |
| §8 ENV vars including FINNHUB_API_KEY | Task 1 | ✅ |

**Placeholder scan:** No TBDs, all code blocks complete, no "similar to" references.

**Type consistency:** `ClaudeResult`, `CostTracker`, `GuardrailsChecker`, `DataProvider` interface used consistently. `cache_read_tokens` named identically in utils.py, cost_tracker.py, db.py.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-19-sprint1-plan1-foundation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
