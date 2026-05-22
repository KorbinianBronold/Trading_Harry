# Sprint 2 / Plan 1: Capital Provider + DB Incremental + Position Check

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Capital.com as primary price provider, switch to incremental DB-based indicator calculation, add Finnhub fundamentals caching (7-day TTL), add `position_check` run type, fix timezone handling, and apply Sprint 1 quick-config corrections.

**Architecture:** `CapitalComProvider` replaces yfinance as the primary OHLC source (yfinance remains as fallback). `_process_ticker` switches to an incremental strategy: append today's single bar to `price_history`, then compute indicators from the last 200 DB rows — no more full 90-day fetch per run. A new `fundamentals_cache` table gives Finnhub data a 7-day TTL. `position_check` is a lightweight new run type that reads Capital.com open positions and sends a brief status mail.

**Tech Stack:** Python 3.12, SQLite, requests (already in deps), Capital.com REST API, Finnhub Python SDK, pandas-ta, zoneinfo (stdlib), pytest, freezegun.

**Spec reference:** `docs/2026-05-21-sprint2-changes.md`

---

## File Structure

```
Shares_Future/
├── config.py                              [modify — ATR=2.0, MAX_HOLD_DAYS, Capital.com keys]
├── main.py                                [modify — close run, position_check, BERLIN TZ, Capital.com provider]
├── .env.example                           [modify — CAPITAL_COM_* vars]
├── .github/workflows/analyze.yml          [modify — double crons, TZ="Europe/Berlin" bash]
├── prompts/
│   ├── deep_analysis_v1.txt               [modify — intraday focus paragraph]
│   ├── commodities_crypto_v1.txt          [modify — intraday focus paragraph]
│   ├── portfolio_check_v1.txt             [modify — intraday focus paragraph]
│   └── position_check_v1.txt             [create — new prompt for position status check]
├── src/
│   ├── db.py                              [modify — fundamentals_cache table, premarket_price migration,
│   │                                               load_price_history_from_db, insert_price_bar_if_missing,
│   │                                               cache helpers, fix carryover #21 raw-tx]
│   ├── data_collector.py                  [modify — incremental strategy, fundamentals cache,
│   │                                               carryover #13 MIN_BARS_MACD constant]
│   ├── email_sender.py                    [modify — generate_daily_briefing, _section_briefing,
│   │                                               render_position_check_html, send_position_check_email]
│   └── providers/
│       ├── capital_provider.py            [create — CapitalComProvider]
│       └── finnhub_provider.py            [modify — implement get_fundamentals, BERLIN TZ]
├── setup/
│   ├── __init__.py                        [create — empty]
│   └── historical_loader.py               [create — 3-year pull via Capital.com]
└── tests/
    ├── unit/
    │   ├── test_capital_provider.py        [create]
    │   ├── test_data_collector.py          [modify — incremental + cache tests]
    │   ├── test_db.py                      [modify — fundamentals_cache helpers]
    │   ├── test_finnhub_provider.py        [modify — get_fundamentals tests]
    │   ├── test_email_sender.py            [modify — briefing box + position_check mail]
    │   ├── test_main.py                    [modify — close run, position_check, TZ]
    │   └── test_historical_loader.py       [create]
```

---

## Task 1: Sprint 1 Config + Close-Run Simplification

**Files:**
- Modify: `config.py`
- Modify: `main.py`
- Modify: `tests/unit/test_main.py`

- [ ] **Step 1.1: Write the failing test for close-run**

```python
# tests/unit/test_main.py — append:
def test_close_run_does_not_call_claude(tmp_db_path, mocker):
    """Close run must not invoke Claude or send email."""
    mock_claude = mocker.patch("src.utils.call_claude")
    mocker.patch("src.email_sender._send")
    mocker.patch("src.evaluator.evaluate_open_predictions", return_value=0)

    from main import run_close
    run_close(date="2026-05-21", db_path=str(tmp_db_path))

    mock_claude.assert_not_called()
```

- [ ] **Step 1.2: Run test to confirm it fails**

```
pytest tests/unit/test_main.py::test_close_run_does_not_call_claude -v
```

Expected: `FAIL` — `cannot import name 'run_close'`

- [ ] **Step 1.3: Update config.py — ATR + hold constants**

In `config.py`, replace:

```python
SP500_MIN_ATR_PCT = 0.8
```

With:

```python
SP500_MIN_ATR_PCT = 2.0
MAX_HOLD_DAYS = 5
HOLD_TARGET = "intraday"
```

- [ ] **Step 1.4: Add run_close() to main.py and route close run**

In `main.py`, add after `run_evaluate`:

```python
def run_close(date: str, db_path: str) -> None:
    """Close-Run: DB Datenpflege only. No Claude, no email."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    price_provider = YFinanceProvider()
    n = evaluate_open_predictions(conn=conn, today=date, price_provider=price_provider)
    log.info(f"Close run: {n} predictions evaluated")
    db.cleanup_old_data(conn)
    conn.close()
```

In `main()`, replace:

```python
if ns.run_type in ("pre_market", "midday", "close"):
    run_pipeline(run_type=ns.run_type, date=date, db_path=ns.db_path)
```

With:

```python
if ns.run_type in ("pre_market", "midday"):
    run_pipeline(run_type=ns.run_type, date=date, db_path=ns.db_path)
elif ns.run_type == "close":
    run_close(date=date, db_path=ns.db_path)
```

- [ ] **Step 1.5: Run test to confirm it passes**

```
pytest tests/unit/test_main.py::test_close_run_does_not_call_claude -v
```

Expected: `PASS`

- [ ] **Step 1.6: Full suite**

```
pytest tests/ --cov=src --cov-fail-under=80 -q
```

Expected: green, ≥ 80 % coverage

- [ ] **Step 1.7: Commit**

```bash
git add config.py main.py tests/unit/test_main.py
git commit -m "feat: simplify close-run (no Claude/mail) and set ATR_MIN=2.0, MAX_HOLD_DAYS=5"
```

---

## Task 2: Prompt Intraday-Kalibrierung

**Files:**
- Modify: `prompts/deep_analysis_v1.txt`
- Modify: `prompts/commodities_crypto_v1.txt`
- Modify: `prompts/portfolio_check_v1.txt`

- [ ] **Step 2.1: Write failing test**

```python
# tests/unit/test_main.py — append:
def test_prompts_contain_intraday_focus():
    from pathlib import Path
    prompt_dir = Path("prompts")
    for name in [
        "deep_analysis_v1.txt",
        "commodities_crypto_v1.txt",
        "portfolio_check_v1.txt",
    ]:
        text = (prompt_dir / name).read_text()
        assert "Intraday-Horizont" in text, f"{name} missing intraday focus paragraph"
```

- [ ] **Step 2.2: Run test to confirm it fails**

```
pytest tests/unit/test_main.py::test_prompts_contain_intraday_focus -v
```

Expected: `FAIL`

- [ ] **Step 2.3: Add intraday paragraph to each prompt**

In `prompts/deep_analysis_v1.txt`, after line 1 insert:

```
Analysiere ausschliesslich was heute preisrelevant ist (Intraday-Horizont).
TP und SL muessen innerhalb eines Handelstages erreichbar sein.
Katalysatoren muessen heute oder vorboerslich morgen wirken.
```

Repeat the same three lines at the top of:
- `prompts/commodities_crypto_v1.txt` (after the opening "You are…" line)
- `prompts/portfolio_check_v1.txt` (after the opening "You are…" line)

- [ ] **Step 2.4: Run test to confirm it passes**

```
pytest tests/unit/test_main.py::test_prompts_contain_intraday_focus -v
```

Expected: `PASS`

- [ ] **Step 2.5: Commit**

```bash
git add prompts/
git commit -m "feat: add intraday-focus constraint to all analysis prompts"
```

---

## Task 3: "Was heute zählt"-Box + Email Improvements

**Files:**
- Modify: `src/email_sender.py`
- Modify: `main.py`
- Modify: `tests/unit/test_email_sender.py`

- [ ] **Step 3.1: Write failing tests**

```python
# tests/unit/test_email_sender.py — append:
def test_generate_daily_briefing_high_strength_trends():
    from src.email_sender import generate_daily_briefing
    trend_context = {
        "trends": [
            {"name": "ai-capex", "strength": 9,
             "summary": "AI spending accelerates across hyperscalers",
             "beneficiary_tickers": ["NVDA", "MSFT"],
             "next_catalyst": "NVDA earnings 2026-05-28"},
            {"name": "oil-supply", "strength": 7,
             "summary": "OPEC cuts production by 500k bpd",
             "beneficiary_tickers": [], "next_catalyst": "TBD"},
            {"name": "weak-trend", "strength": 4,
             "summary": "Low strength, must be excluded",
             "beneficiary_tickers": [], "next_catalyst": "TBD"},
        ]
    }
    policy_context = {"policy_risk_level": "low", "events": []}
    bullets = generate_daily_briefing(trend_context, policy_context)
    assert any("ai-capex" in b for b in bullets)
    assert any("oil-supply" in b for b in bullets)
    assert not any("weak-trend" in b for b in bullets)


def test_generate_daily_briefing_policy_high_adds_bullet():
    from src.email_sender import generate_daily_briefing
    trend_context = {"trends": []}
    policy_context = {
        "policy_risk_level": "high",
        "events": [{"headline": "Fed surprise rate cut announced"}],
    }
    bullets = generate_daily_briefing(trend_context, policy_context)
    assert any("HOCH" in b for b in bullets)
    assert any("Fed" in b for b in bullets)


def test_generate_daily_briefing_max_6_bullets():
    from src.email_sender import generate_daily_briefing
    trend_context = {
        "trends": [
            {"name": f"trend-{i}", "strength": 9, "summary": "X" * 80,
             "beneficiary_tickers": [f"T{i}"], "next_catalyst": f"Event {i}"}
            for i in range(10)
        ]
    }
    policy_context = {"policy_risk_level": "high",
                      "events": [{"headline": "Big event"}]}
    bullets = generate_daily_briefing(trend_context, policy_context)
    assert len(bullets) <= 6


def test_render_daily_html_includes_briefing_section():
    from src.email_sender import render_daily_html
    payload = {
        "date": "2026-05-21", "run_type": "pre_market",
        "briefing": ["ai-capex: AI spending accelerates", "Policy-Risiko HOCH: tariffs"],
        "portfolio_recs": [], "top_long": [], "top_short": [],
        "commodities_crypto": [], "trends": [],
        "skipped_tickers": [], "yesterday_outcomes": {}, "cost_summary": {},
    }
    html = render_daily_html(payload)
    assert "Was heute" in html
    assert "ai-capex" in html
```

- [ ] **Step 3.2: Run tests to confirm they fail**

```
pytest tests/unit/test_email_sender.py::test_generate_daily_briefing_high_strength_trends tests/unit/test_email_sender.py::test_render_daily_html_includes_briefing_section -v
```

Expected: `FAIL` — `ImportError: cannot import name 'generate_daily_briefing'`

- [ ] **Step 3.3: Add generate_daily_briefing() and _section_briefing() to email_sender.py**

In `src/email_sender.py`, after the `_h()` helper function, add:

```python
def generate_daily_briefing(trend_context: dict, policy_context: dict) -> list[str]:
    """Returns 4-6 bullet strings for the 'Was heute zaehlt' box."""
    bullets: list[str] = []
    strong = sorted(
        [t for t in (trend_context.get("trends") or []) if t.get("strength", 0) >= 7],
        key=lambda t: -t.get("strength", 0),
    )
    for t in strong[:2]:
        name = t.get("name") or t.get("trend_name", "Trend")
        summary = (t.get("summary") or "")[:70]
        bullets.append(f"{name}: {summary}")
    if (policy_context.get("policy_risk_level") or "").lower() == "high":
        events = policy_context.get("events") or []
        if events:
            headline = (events[0].get("headline") or "")[:80]
            bullets.append(f"Policy-Risiko HOCH: {headline}")
    for t in (trend_context.get("trends") or []):
        tickers = t.get("beneficiary_tickers") or []
        if tickers:
            bullets.append(f"Trend-Beneficiary: {tickers[0]}")
            break
    for t in (trend_context.get("trends") or []):
        cat = t.get("next_catalyst")
        if cat and cat != "TBD":
            bullets.append(f"Naechster Katalysator: {cat[:60]}")
            break
    return bullets[:6]


def _section_briefing(bullets: list[str]) -> str:
    if not bullets:
        return ""
    items = "".join(f"<li>{_h(b)}</li>" for b in bullets)
    return (
        '<div style="background:#1a1a2e;color:#fff;padding:16px;'
        'margin-bottom:20px;border-radius:4px;">'
        '<h2 style="color:#fff;margin:0 0 12px 0;">Was heute zaehlt</h2>'
        f'<ul style="margin:0;padding-left:20px;">{items}</ul>'
        '</div>'
    )
```

- [ ] **Step 3.4: Insert briefing section at top of render_daily_html()**

In `src/email_sender.py`, find `render_daily_html()`. After the opening `<h1>` tag and before `_section_portfolio(...)`, insert:

```python
+ _section_briefing(payload.get("briefing") or [])
```

The resulting render order is: briefing → portfolio → stocks → trends → commodities → footer.

- [ ] **Step 3.5: Pass briefing payload in main.py run_pipeline()**

In `main.py`, after the `run_policy_monitor` call (line where `policy_context` is assigned) and before the deep-analysis block, add:

```python
from src.email_sender import generate_daily_briefing
payload["briefing"] = generate_daily_briefing(trend_context, policy_context)
```

Also add `"briefing": []` to the initial `payload` dict inside `run_pipeline()`.

- [ ] **Step 3.6: Run tests to confirm they pass**

```
pytest tests/unit/test_email_sender.py -v
```

Expected: all `PASS`

- [ ] **Step 3.7: Full suite**

```
pytest tests/ --cov=src --cov-fail-under=80 -q
```

- [ ] **Step 3.8: Commit**

```bash
git add src/email_sender.py main.py tests/unit/test_email_sender.py
git commit -m "feat: add 'Was heute zaehlt' briefing box to daily email"
```

---

## Task 4: Timezone Fix (analyze.yml + Python zoneinfo)

**Files:**
- Modify: `.github/workflows/analyze.yml`
- Modify: `main.py`
- Modify: `src/providers/finnhub_provider.py`
- Modify: `tests/unit/test_main.py`

- [ ] **Step 4.1: Write failing test for Berlin date derivation**

```python
# tests/unit/test_main.py — append:
from freezegun import freeze_time

def test_main_date_uses_berlin_timezone(tmp_db_path, mocker):
    """At 23:30 UTC on 2026-05-21, Berlin (CEST UTC+2) is 01:30 on 2026-05-22."""
    mocker.patch("main.run_evaluate")
    import importlib
    with freeze_time("2026-05-21T23:30:00+00:00"):
        import main as m
        importlib.reload(m)
        m.main(["--run-type", "evaluate", "--db-path", str(tmp_db_path)])
        call_date = m.run_evaluate.call_args[1]["date"]
    assert call_date == "2026-05-22", f"Expected Berlin date 2026-05-22, got {call_date}"
```

- [ ] **Step 4.2: Run test to confirm it fails**

```
pytest tests/unit/test_main.py::test_main_date_uses_berlin_timezone -v
```

Expected: `FAIL` — date is "2026-05-21" (UTC), not "2026-05-22"

- [ ] **Step 4.3: Add BERLIN timezone to main.py**

In `main.py`, add to the import block:

```python
from datetime import date as date_cls, datetime, timedelta
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
```

Replace (in `main()`):

```python
date = ns.date or date_cls.today().isoformat()
```

With:

```python
date = ns.date or datetime.now(BERLIN).date().isoformat()
```

- [ ] **Step 4.4: Fix FinnhubProvider to use Berlin timezone**

In `src/providers/finnhub_provider.py`, replace:

```python
import logging
from datetime import datetime, timedelta
import finnhub
```

With:

```python
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import finnhub

BERLIN = ZoneInfo("Europe/Berlin")
```

And replace:

```python
today = datetime.now().date()
```

With:

```python
today = datetime.now(BERLIN).date()
```

- [ ] **Step 4.5: Replace analyze.yml schedule + run_type detection**

Replace the entire `schedule:` block and the "Determine run_type" step with:

```yaml
schedule:
  # pre_market 14:00 Berlin
  - cron: '0 12 * * 1-5'   # Sommer CEST UTC+2
  - cron: '0 13 * * 1-5'   # Winter CET UTC+1
  # evaluate 15:00 Berlin
  - cron: '0 13 * * 1-5'   # Sommer
  - cron: '0 14 * * 1-5'   # Winter
  # midday 16:15 Berlin
  - cron: '15 14 * * 1-5'  # Sommer
  - cron: '15 15 * * 1-5'  # Winter
  # position_check 17:30 Berlin
  - cron: '30 15 * * 1-5'  # Sommer
  - cron: '30 16 * * 1-5'  # Winter
  # close 22:30 Berlin
  - cron: '30 20 * * 1-5'  # Sommer
  - cron: '30 21 * * 1-5'  # Winter
  # weekly Sonntag 20:00 Berlin
  - cron: '0 18 * * 0'     # Sommer
  - cron: '0 19 * * 0'     # Winter
```

Replace the "Determine run_type" step `run:` block with:

```bash
if [ -n "${{ inputs.run_type }}" ]; then
  echo "type=${{ inputs.run_type }}" >> "$GITHUB_OUTPUT"
  exit 0
fi
HOUR=$(TZ="Europe/Berlin" date +%H)
MIN=$(TZ="Europe/Berlin" date +%M)
DOW=$(TZ="Europe/Berlin" date +%u)
if [ "$DOW" = "7" ] && [ "$HOUR" = "20" ]; then T="weekly"
elif [ "$HOUR" = "15" ] && [ "$MIN" -lt "30" ]; then T="evaluate"
elif [ "$HOUR" = "14" ] && [ "$MIN" -lt "15" ]; then T="pre_market"
elif [ "$HOUR" = "16" ] && [ "$MIN" -ge "10" ]; then T="midday"
elif [ "$HOUR" = "17" ] && [ "$MIN" -ge "25" ]; then T="position_check"
elif [ "$HOUR" = "22" ] || [ "$HOUR" = "21" ]; then T="close"
else T="close"; fi
echo "type=$T" >> "$GITHUB_OUTPUT"
```

Also update `workflow_dispatch` options to include `position_check`:

```yaml
options: [pre_market, midday, close, evaluate, weekly, position_check]
```

- [ ] **Step 4.6: Run tests to confirm they pass**

```
pytest tests/unit/test_main.py -v
```

Expected: all `PASS`

- [ ] **Step 4.7: Full suite**

```
pytest tests/ --cov=src --cov-fail-under=80 -q
```

- [ ] **Step 4.8: Commit**

```bash
git add .github/workflows/analyze.yml main.py src/providers/finnhub_provider.py tests/unit/test_main.py
git commit -m "fix: use Europe/Berlin timezone for date derivation and run-type detection"
```

---

## Task 5: CapitalComProvider

**Files:**
- Create: `src/providers/capital_provider.py`
- Create: `tests/unit/test_capital_provider.py`
- Modify: `config.py`
- Modify: `.env.example`

- [ ] **Step 5.1: Add Capital.com config vars**

In `config.py`, append:

```python
CAPITAL_COM_API_KEY  = os.getenv("CAPITAL_COM_API_KEY")
CAPITAL_COM_PASSWORD = os.getenv("CAPITAL_COM_PASSWORD")
CAPITAL_COM_BASE_URL = "https://demo-api-capital.backend-capital.com"
```

In `.env.example`, append:

```
CAPITAL_COM_API_KEY=
CAPITAL_COM_PASSWORD=
```

- [ ] **Step 5.2: Write failing tests**

```python
# tests/unit/test_capital_provider.py
import pytest
from unittest.mock import MagicMock
import pandas as pd

_PRICES = {
    "prices": [
        {
            "snapshotTime": "2026/05/20 00:00:00:000",
            "openPrice":  {"bid": 100.0, "ask": 100.1},
            "highPrice":  {"bid": 105.0, "ask": 105.1},
            "lowPrice":   {"bid":  99.0, "ask":  99.1},
            "closePrice": {"bid": 102.0, "ask": 102.1},
            "lastTradedVolume": 1_000_000,
        }
    ]
}
_AUTH_HEADERS = {"CST": "test_cst", "X-SECURITY-TOKEN": "test_token"}


def _mock_post(url, **kwargs):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.headers = _AUTH_HEADERS
    return m


def _mock_prices_get(url, **kwargs):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = _PRICES
    return m


def test_get_price_history_returns_dataframe(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    monkeypatch.setattr("requests.get", _mock_prices_get)
    from src.providers.capital_provider import CapitalComProvider
    df = CapitalComProvider().get_price_history("AAPL", days=30)
    assert df is not None and not df.empty
    assert set(["Open", "High", "Low", "Close", "Volume"]).issubset(df.columns)


def test_get_price_history_empty_returns_none(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    def _empty(url, **kwargs):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {"prices": []}
        return m
    monkeypatch.setattr("requests.get", _empty)
    from src.providers.capital_provider import CapitalComProvider
    assert CapitalComProvider().get_price_history("AAPL") is None


def test_ticker_mapping_gold_uses_GOLD_epic(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    called = []
    def _capture(url, **kwargs):
        called.append(url)
        return _mock_prices_get(url, **kwargs)
    monkeypatch.setattr("requests.get", _capture)
    from src.providers.capital_provider import CapitalComProvider
    CapitalComProvider().get_price_history("GC=F", days=5)
    assert any("GOLD" in u for u in called), f"GOLD not in {called}"


def test_get_open_positions_maps_direction(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    def _pos(url, **kwargs):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {
            "positions": [{
                "position": {
                    "direction": "BUY", "level": 100.5,
                    "stopLevel": 98.0, "limitLevel": 103.0, "profit": 2.0,
                },
                "market": {"epic": "AAPL", "bid": 101.0},
            }]
        }
        return m
    monkeypatch.setattr("requests.get", _pos)
    from src.providers.capital_provider import CapitalComProvider
    positions = CapitalComProvider().get_open_positions()
    assert len(positions) == 1
    assert positions[0]["ticker"] == "AAPL"
    assert positions[0]["direction"] == "long"
    assert positions[0]["entry_price"] == 100.5


def test_get_premarket_price_returns_bid(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    def _mkt(url, **kwargs):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {"snapshot": {"bid": 150.25, "offer": 150.30}}
        return m
    monkeypatch.setattr("requests.get", _mkt)
    from src.providers.capital_provider import CapitalComProvider
    assert CapitalComProvider().get_premarket_price("AAPL") == 150.25


def test_get_price_history_on_error_returns_none(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    monkeypatch.setattr("requests.get", lambda *a, **k: (_ for _ in ()).throw(Exception("conn refused")))
    from src.providers.capital_provider import CapitalComProvider
    assert CapitalComProvider().get_price_history("AAPL") is None


def test_get_closed_positions_filters_by_action_type(monkeypatch):
    monkeypatch.setattr("requests.post", _mock_post)
    def _act(url, **kwargs):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {
            "activities": [
                {
                    "epic": "AAPL", "type": "POSITION",
                    "details": {
                        "direction": "BUY", "level": 102.5, "profit": 2.0,
                        "actions": [{"actionType": "POSITION_CLOSED"}],
                    },
                },
                {
                    "epic": "MSFT", "type": "POSITION",
                    "details": {
                        "direction": "SELL", "level": 200.0, "profit": -1.0,
                        "actions": [{"actionType": "POSITION_OPENED"}],
                    },
                },
            ]
        }
        return m
    monkeypatch.setattr("requests.get", _act)
    from src.providers.capital_provider import CapitalComProvider
    closed = CapitalComProvider().get_closed_positions("2026-05-21")
    assert len(closed) == 1
    assert closed[0]["ticker"] == "AAPL"
```

- [ ] **Step 5.3: Run tests to confirm they fail**

```
pytest tests/unit/test_capital_provider.py -v
```

Expected: `FAIL` — `ModuleNotFoundError: No module named 'src.providers.capital_provider'`

- [ ] **Step 5.4: Create src/providers/capital_provider.py**

```python
"""Capital.com Demo REST API provider.

Authentication: POST /api/v1/session → CST + X-SECURITY-TOKEN headers.
Session is created lazily on first call and reused for the lifetime of the
provider instance (one instance per run).
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

import config
from src.providers.base import DataProvider

log = logging.getLogger("shares_future.capital")
BERLIN = ZoneInfo("Europe/Berlin")

TICKER_MAP: dict[str, str] = {
    "GC=F":    "GOLD",
    "SI=F":    "SILVER",
    "CL=F":    "CRUDE_OIL",
    "BTC-USD": "BITCOIN",
    "ETH-USD": "ETHEREUM",
    "SOL-USD": "SOLANA",
    "XRP-USD": "XRP",
}


class CapitalComProvider(DataProvider):
    _source_name = "capital.com"

    def __init__(self) -> None:
        self._cst: str | None = None
        self._security_token: str | None = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _ensure_session(self) -> None:
        if self._cst:
            return
        resp = requests.post(
            f"{config.CAPITAL_COM_BASE_URL}/api/v1/session",
            json={
                "identifier":        config.CAPITAL_COM_API_KEY,
                "password":          config.CAPITAL_COM_PASSWORD,
                "encryptedPassword": False,
            },
            headers={"X-CAP-API-KEY": config.CAPITAL_COM_API_KEY},
            timeout=30,
        )
        resp.raise_for_status()
        self._cst             = resp.headers.get("CST")
        self._security_token  = resp.headers.get("X-SECURITY-TOKEN")

    def _headers(self) -> dict:
        self._ensure_session()
        return {
            "X-CAP-API-KEY":    config.CAPITAL_COM_API_KEY,
            "CST":              self._cst,
            "X-SECURITY-TOKEN": self._security_token,
        }

    def _map(self, ticker: str) -> str:
        return TICKER_MAP.get(ticker, ticker)

    # ------------------------------------------------------------------
    # Price parsing
    # ------------------------------------------------------------------

    def _parse_prices(self, prices: list[dict]) -> pd.DataFrame | None:
        if not prices:
            return None
        rows = []
        for p in prices:
            snap = p.get("snapshotTime", "")
            # Capital.com format: "YYYY/MM/DD HH:MM:SS:mmm"
            date_str = snap.replace("/", "-")[:10]
            rows.append({
                "Date":   date_str,
                "Open":   float(p["openPrice"]["bid"]),
                "High":   float(p["highPrice"]["bid"]),
                "Low":    float(p["lowPrice"]["bid"]),
                "Close":  float(p["closePrice"]["bid"]),
                "Volume": int(p.get("lastTradedVolume") or 0),
            })
        df = pd.DataFrame(rows)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        return df if not df.empty else None

    # ------------------------------------------------------------------
    # DataProvider interface
    # ------------------------------------------------------------------

    def get_price_history(self, ticker: str, days: int = 90) -> pd.DataFrame | None:
        epic = self._map(ticker)
        end   = datetime.now(BERLIN)
        start = end - timedelta(days=days)
        try:
            resp = requests.get(
                f"{config.CAPITAL_COM_BASE_URL}/api/v1/prices/{epic}",
                headers=self._headers(),
                params={
                    "resolution": "DAY",
                    "max":        days,
                    "from":       start.strftime("%Y-%m-%dT%H:%M:%S"),
                    "to":         end.strftime("%Y-%m-%dT%H:%M:%S"),
                },
                timeout=30,
            )
            resp.raise_for_status()
            return self._parse_prices(resp.json().get("prices", []))
        except Exception as e:
            log.warning(f"{ticker}: Capital.com price fetch failed: {e}")
            return None

    def get_ohlc_after(
        self, ticker: str, start_date: str, end_date: str,
    ) -> pd.DataFrame | None:
        epic = self._map(ticker)
        try:
            resp = requests.get(
                f"{config.CAPITAL_COM_BASE_URL}/api/v1/prices/{epic}",
                headers=self._headers(),
                params={
                    "resolution": "DAY",
                    "max":        1000,
                    "from":       f"{start_date}T00:00:00",
                    "to":         f"{end_date}T23:59:59",
                },
                timeout=30,
            )
            resp.raise_for_status()
            return self._parse_prices(resp.json().get("prices", []))
        except Exception as e:
            log.warning(f"{ticker}: Capital.com OHLC fetch failed: {e}")
            return None

    def get_last_available_date(self, ticker: str) -> str | None:
        df = self.get_price_history(ticker, days=5)
        if df is None or df.empty:
            return None
        return df.index[-1].strftime("%Y-%m-%d")

    # ------------------------------------------------------------------
    # Capital.com-specific extras (not in DataProvider base)
    # ------------------------------------------------------------------

    def get_premarket_price(self, ticker: str) -> float | None:
        epic = self._map(ticker)
        try:
            resp = requests.get(
                f"{config.CAPITAL_COM_BASE_URL}/api/v1/markets/{epic}",
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            bid = resp.json().get("snapshot", {}).get("bid")
            return float(bid) if bid is not None else None
        except Exception as e:
            log.warning(f"{ticker}: Capital.com premarket fetch failed: {e}")
            return None

    def get_open_positions(self) -> list[dict]:
        try:
            resp = requests.get(
                f"{config.CAPITAL_COM_BASE_URL}/api/v1/positions",
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            out = []
            for p in resp.json().get("positions", []):
                pos = p.get("position", {})
                mkt = p.get("market", {})
                out.append({
                    "ticker":        mkt.get("epic"),
                    "direction":     "long" if pos.get("direction") == "BUY" else "short",
                    "entry_price":   pos.get("level"),
                    "current_price": mkt.get("bid"),
                    "tp_price":      pos.get("limitLevel"),
                    "sl_price":      pos.get("stopLevel"),
                    "profit_loss":   pos.get("profit"),
                    "status":        "open",
                })
            return out
        except Exception as e:
            log.warning(f"Capital.com open positions fetch failed: {e}")
            return []

    def get_closed_positions(self, date: str) -> list[dict]:
        try:
            resp = requests.get(
                f"{config.CAPITAL_COM_BASE_URL}/api/v1/history/activity",
                headers=self._headers(),
                params={
                    "from":     f"{date}T00:00:00",
                    "to":       f"{date}T23:59:59",
                    "detailed": "true",
                },
                timeout=30,
            )
            resp.raise_for_status()
            out = []
            for act in resp.json().get("activities", []):
                if act.get("type") != "POSITION":
                    continue
                det = act.get("details", {})
                actions = det.get("actions") or []
                if not any(a.get("actionType") == "POSITION_CLOSED" for a in actions):
                    continue
                out.append({
                    "ticker":      act.get("epic"),
                    "direction":   "long" if det.get("direction") == "BUY" else "short",
                    "exit_price":  det.get("level"),
                    "profit_loss": det.get("profit"),
                    "status":      "closed",
                })
            return out
        except Exception as e:
            log.warning(f"Capital.com closed positions fetch failed: {e}")
            return []

    # Capital.com does not provide fundamentals or earnings — delegate to Finnhub
    def get_fundamentals(self, ticker: str) -> dict:
        return {}

    def get_earnings_calendar(self, ticker: str) -> dict:
        return {}
```

- [ ] **Step 5.5: Run tests to confirm they pass**

```
pytest tests/unit/test_capital_provider.py -v
```

Expected: all 7 tests `PASS`

- [ ] **Step 5.6: Full suite**

```
pytest tests/ --cov=src --cov-fail-under=80 -q
```

- [ ] **Step 5.7: Commit**

```bash
git add src/providers/capital_provider.py tests/unit/test_capital_provider.py config.py .env.example
git commit -m "feat: add CapitalComProvider for OHLC, premarket price, and position reads"
```

---

## Task 6: fundamentals_cache + FinnhubProvider.get_fundamentals()

**Files:**
- Modify: `src/db.py`
- Modify: `src/providers/finnhub_provider.py`
- Modify: `tests/unit/test_db.py`
- Modify: `tests/unit/test_finnhub_provider.py`

Carryover fix included here: **#21** (`db.update_outcome_close` uses raw `BEGIN`/`COMMIT`/`ROLLBACK` — switch to `with conn:`).

- [ ] **Step 6.1: Write failing tests**

```python
# tests/unit/test_db.py — append:
from src.db import init_schema, get_cached_fundamentals, save_fundamentals_cache


def test_fundamentals_cache_miss_on_fresh_db(in_memory_db):
    init_schema(in_memory_db)
    assert get_cached_fundamentals(in_memory_db, "AAPL") is None


def test_fundamentals_cache_hit_within_7_days(in_memory_db):
    init_schema(in_memory_db)
    data = {
        "pe_ratio": 25.0, "forward_pe": 22.0, "market_cap_b": 3000.0,
        "debt_equity": 0.5, "sector": "Technology",
        "analyst_upside": 10.0, "consensus": "buy",
    }
    save_fundamentals_cache(in_memory_db, "AAPL", data, fetched_date="2026-05-21")
    result = get_cached_fundamentals(in_memory_db, "AAPL", today="2026-05-21")
    assert result is not None
    assert result["pe_ratio"] == 25.0
    assert result["sector"] == "Technology"


def test_fundamentals_cache_stale_after_7_days(in_memory_db):
    init_schema(in_memory_db)
    save_fundamentals_cache(in_memory_db, "AAPL", {"pe_ratio": 20.0}, fetched_date="2026-05-01")
    result = get_cached_fundamentals(in_memory_db, "AAPL", today="2026-05-21")
    assert result is None


def test_fundamentals_cache_upsert_overwrites_stale(in_memory_db):
    init_schema(in_memory_db)
    save_fundamentals_cache(in_memory_db, "AAPL", {"pe_ratio": 20.0}, fetched_date="2026-05-01")
    save_fundamentals_cache(in_memory_db, "AAPL", {"pe_ratio": 25.0}, fetched_date="2026-05-21")
    result = get_cached_fundamentals(in_memory_db, "AAPL", today="2026-05-21")
    assert result is not None
    assert result["pe_ratio"] == 25.0
```

```python
# tests/unit/test_finnhub_provider.py — append:
def test_get_fundamentals_returns_structured_dict(mocker):
    mock_client = mocker.MagicMock()
    mock_client.company_profile2.return_value = {
        "marketCapitalization": 3_000_000.0,
        "finnhubIndustry": "Technology",
    }
    mock_client.company_basic_financials.return_value = {
        "metric": {
            "peNormalizedAnnual": 25.5,
            "forwardPE": 22.0,
            "totalDebt/totalEquityAnnual": 50.0,
        }
    }
    mock_client.recommendation_trends.return_value = [
        {"buy": 20, "hold": 5, "sell": 2}
    ]
    mock_client.price_target.return_value = {"targetMean": 200.0}

    import src.providers.finnhub_provider as fh
    original = fh._client
    fh._client = mock_client
    try:
        from src.providers.finnhub_provider import FinnhubProvider
        result = FinnhubProvider().get_fundamentals("AAPL")
    finally:
        fh._client = original

    assert result.get("sector") == "Technology"
    assert result.get("pe_ratio") == pytest.approx(25.5)
    assert result.get("market_cap_b") == pytest.approx(3000.0)
    assert result.get("consensus") == "buy"


def test_get_fundamentals_no_client_returns_empty():
    import src.providers.finnhub_provider as fh
    original = fh._client
    fh._client = None
    try:
        result = fh.FinnhubProvider().get_fundamentals("AAPL")
    finally:
        fh._client = original
    assert result == {}
```

- [ ] **Step 6.2: Run tests to confirm they fail**

```
pytest tests/unit/test_db.py::test_fundamentals_cache_miss_on_fresh_db tests/unit/test_finnhub_provider.py::test_get_fundamentals_returns_structured_dict -v
```

Expected: `FAIL`

- [ ] **Step 6.3: Add fundamentals_cache table + helpers to db.py**

Append the following CREATE TABLE to `SCHEMA_SQL` (before the final closing `"""`):

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

In `_apply_migrations()`, append:

```python
tables = {r["name"] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()}
if "fundamentals_cache" not in tables:
    conn.execute("""
        CREATE TABLE fundamentals_cache (
            ticker TEXT NOT NULL,
            fetched_date TEXT NOT NULL,
            pe_ratio REAL, forward_pe REAL, market_cap_b REAL,
            debt_equity REAL, sector TEXT,
            analyst_upside REAL, consensus TEXT,
            UNIQUE(ticker)
        )
    """)
conn.commit()
```

Append these helper functions to `db.py`:

```python
_FUNDAMENTALS_TTL_DAYS = 7


def get_cached_fundamentals(
    conn: sqlite3.Connection,
    ticker: str,
    today: str | None = None,
) -> dict | None:
    from datetime import date as _d, timedelta
    _today = today or _d.today().isoformat()
    cutoff = (_d.fromisoformat(_today) - timedelta(days=_FUNDAMENTALS_TTL_DAYS)).isoformat()
    row = conn.execute(
        "SELECT * FROM fundamentals_cache WHERE ticker=? AND fetched_date >= ?",
        (ticker, cutoff),
    ).fetchone()
    return dict(row) if row else None


def save_fundamentals_cache(
    conn: sqlite3.Connection,
    ticker: str,
    data: dict,
    fetched_date: str | None = None,
) -> None:
    from datetime import date as _d
    _fetched = fetched_date or _d.today().isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO fundamentals_cache
           (ticker, fetched_date, pe_ratio, forward_pe, market_cap_b,
            debt_equity, sector, analyst_upside, consensus)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ticker, _fetched,
            data.get("pe_ratio"), data.get("forward_pe"), data.get("market_cap_b"),
            data.get("debt_equity"), data.get("sector"),
            data.get("analyst_upside"), data.get("consensus"),
        ),
    )
    conn.commit()
```

Also apply carryover fix **#21**: in `update_outcome_close()`, replace the raw `conn.execute("BEGIN")` / `COMMIT` / `ROLLBACK` block with:

```python
def update_outcome_close(...) -> None:
    status_map = {
        "tp_hit": "closed_tp", "sl_hit": "closed_sl",
        "timeout": "closed_timeout", "pessimistic_overlap": "closed_sl",
        "data_missing": "closed_data_missing",
    }
    status = status_map.get(exit_reason, "closed_timeout")
    with conn:
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
```

- [ ] **Step 6.4: Implement FinnhubProvider.get_fundamentals()**

Replace the stub `get_fundamentals` in `src/providers/finnhub_provider.py` with:

```python
def get_fundamentals(self, ticker: str) -> dict:
    if _client is None:
        return {}
    try:
        profile  = _client.company_profile2(symbol=ticker) or {}
        resp     = _client.company_basic_financials(ticker, "all") or {}
        metrics  = resp.get("metric") or {}
        recs     = _client.recommendation_trends(ticker) or []
        _client.price_target(ticker)  # fetched for side-effect; not used yet
    except Exception as e:
        log.warning(f"{ticker}: Finnhub fundamentals failed: {e}")
        return {}

    consensus = None
    if recs:
        r     = recs[0]
        total = (r.get("buy") or 0) + (r.get("hold") or 0) + (r.get("sell") or 0)
        if total > 0:
            ratio     = (r.get("buy") or 0) / total
            consensus = "buy" if ratio >= 0.6 else ("sell" if ratio <= 0.3 else "hold")

    mc_millions = profile.get("marketCapitalization")
    market_cap_b = round(mc_millions / 1000, 2) if mc_millions else None

    de_raw   = metrics.get("totalDebt/totalEquityAnnual")
    debt_eq  = round(de_raw / 100, 4) if de_raw is not None else None

    return {
        "pe_ratio":     metrics.get("peNormalizedAnnual"),
        "forward_pe":   metrics.get("forwardPE"),
        "market_cap_b": market_cap_b,
        "debt_equity":  debt_eq,
        "sector":       profile.get("finnhubIndustry"),
        "analyst_upside": None,
        "consensus":    consensus,
    }
```

- [ ] **Step 6.5: Run tests to confirm they pass**

```
pytest tests/unit/test_db.py tests/unit/test_finnhub_provider.py -v
```

Expected: all `PASS`

- [ ] **Step 6.6: Full suite**

```
pytest tests/ --cov=src --cov-fail-under=80 -q
```

- [ ] **Step 6.7: Commit**

```bash
git add src/db.py src/providers/finnhub_provider.py tests/unit/test_db.py tests/unit/test_finnhub_provider.py
git commit -m "feat: add fundamentals_cache (7-day TTL) and implement Finnhub get_fundamentals"
```

---

## Task 7: DB-Incremental-Update

**Files:**
- Modify: `src/db.py`
- Modify: `src/data_collector.py`
- Modify: `main.py`
- Modify: `tests/unit/test_data_collector.py`

Carryover fix included: **#13** (`magic number 35` in compute_macd_signal → `MIN_BARS_MACD`).

- [ ] **Step 7.1: Write failing tests**

```python
# tests/unit/test_data_collector.py — append:
from src import db as _db
from datetime import date as _date, timedelta


def _ohlcv_rows(n: int = 90, end: str = "2026-05-21") -> list[tuple]:
    """Returns n consecutive rows of OHLCV, last row = end date."""
    end_d = _date.fromisoformat(end)
    rows = []
    for i in range(n):
        d = (end_d - timedelta(days=n - 1 - i)).isoformat()
        close = 100.0 + i * 0.5
        rows.append((d, close - 0.1, close + 0.5, close - 0.5, close, 1_000_000))
    return rows


def test_incremental_no_fetch_when_today_in_db(in_memory_db, mocker):
    """When today's bar already exists, no price fetch occurs."""
    _db.init_schema(in_memory_db)
    for d, o, h, l, c, v in _ohlcv_rows(90, "2026-05-21"):
        _db.upsert_price_history(in_memory_db, "AAPL", d, o, h, l, c, v)

    mock_price = mocker.MagicMock()
    mock_price.get_ohlc_after.return_value   = None
    mock_price.get_price_history.return_value = None
    mock_earn  = mocker.MagicMock()
    mock_earn.get_earnings_calendar.return_value = {}
    mock_earn.get_fundamentals.return_value      = {}

    from src.data_collector import _process_ticker
    td = _process_ticker("AAPL", mock_price, mock_earn, in_memory_db, "2026-05-21", "test")

    mock_price.get_ohlc_after.assert_not_called()
    mock_price.get_price_history.assert_not_called()
    assert td is not None


def test_incremental_fetches_and_persists_missing_today(in_memory_db, mocker):
    """When today is missing, get_ohlc_after is called and bar is stored."""
    import pandas as pd
    _db.init_schema(in_memory_db)
    for d, o, h, l, c, v in _ohlcv_rows(89, "2026-05-20"):
        _db.upsert_price_history(in_memory_db, "AAPL", d, o, h, l, c, v)

    today_df = pd.DataFrame(
        {"Open": [101.0], "High": [104.0], "Low": [100.0], "Close": [103.0], "Volume": [2_000_000]},
        index=pd.DatetimeIndex(["2026-05-21"]),
    )
    today_df.index.name = "Date"

    mock_price = mocker.MagicMock()
    mock_price.get_ohlc_after.return_value = today_df
    mock_earn  = mocker.MagicMock()
    mock_earn.get_earnings_calendar.return_value = {}
    mock_earn.get_fundamentals.return_value      = {}

    from src.data_collector import _process_ticker
    td = _process_ticker("AAPL", mock_price, mock_earn, in_memory_db, "2026-05-21", "test")

    mock_price.get_ohlc_after.assert_called_once()
    assert td is not None
    row = in_memory_db.execute(
        "SELECT close FROM price_history WHERE ticker='AAPL' AND date='2026-05-21'"
    ).fetchone()
    assert row is not None
    assert row["close"] == pytest.approx(103.0)


def test_incremental_fallback_to_full_history_when_ohlc_after_none(in_memory_db, mocker):
    """If get_ohlc_after returns None, full history fetch is attempted."""
    import pandas as pd
    _db.init_schema(in_memory_db)

    full_df_rows = _ohlcv_rows(90, "2026-05-21")
    idx = pd.DatetimeIndex([r[0] for r in full_df_rows])
    full_df = pd.DataFrame(
        {
            "Open":   [r[1] for r in full_df_rows],
            "High":   [r[2] for r in full_df_rows],
            "Low":    [r[3] for r in full_df_rows],
            "Close":  [r[4] for r in full_df_rows],
            "Volume": [r[5] for r in full_df_rows],
        },
        index=idx,
    )
    full_df.index.name = "Date"

    mock_price = mocker.MagicMock()
    mock_price.get_ohlc_after.return_value    = None
    mock_price.get_price_history.return_value = full_df
    mock_earn  = mocker.MagicMock()
    mock_earn.get_earnings_calendar.return_value = {}
    mock_earn.get_fundamentals.return_value      = {}

    from src.data_collector import _process_ticker
    td = _process_ticker("AAPL", mock_price, mock_earn, in_memory_db, "2026-05-21", "test")

    mock_price.get_price_history.assert_called_once()
    assert td is not None
```

- [ ] **Step 7.2: Run tests to confirm they fail**

```
pytest tests/unit/test_data_collector.py::test_incremental_no_fetch_when_today_in_db -v
```

Expected: `FAIL`

- [ ] **Step 7.3: Add DB helpers to db.py**

In `_apply_migrations()`, append (after the existing migrations):

```python
ph_cols = {r["name"] for r in conn.execute(
    "PRAGMA table_info(price_history)"
).fetchall()}
if "premarket_price" not in ph_cols:
    conn.execute("ALTER TABLE price_history ADD COLUMN premarket_price REAL")
conn.commit()
```

Append these two functions to `db.py`:

```python
def insert_price_bar_if_missing(
    conn: sqlite3.Connection,
    ticker: str, date: str,
    open_: float, high: float, low: float, close: float,
    volume: int, source: str = "capital.com",
) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO price_history
           (ticker, date, open, high, low, close, volume, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticker, date, open_, high, low, close, volume, source),
    )


def load_price_history_from_db(
    conn: sqlite3.Connection,
    ticker: str,
    as_of_date: str,
    limit: int = 200,
) -> "pd.DataFrame | None":
    import pandas as pd
    rows = conn.execute(
        """SELECT date, open, high, low, close, volume
           FROM price_history
           WHERE ticker=? AND date <= ?
           ORDER BY date DESC LIMIT ?""",
        (ticker, as_of_date, limit),
    ).fetchall()
    if not rows:
        return None
    df = pd.DataFrame([dict(r) for r in rows])
    df = df.rename(columns={
        "date": "Date", "open": "Open", "high": "High",
        "low": "Low", "close": "Close", "volume": "Volume",
    })
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date").sort_index()
```

- [ ] **Step 7.4: Refactor data_collector.py with incremental strategy**

Apply carryover fix **#13**: at the top of `src/data_collector.py`, add:

```python
MIN_BARS_MACD = 35
```

And in `compute_macd_signal`, replace `if len(df) < 35:` with `if len(df) < MIN_BARS_MACD:`.

Add the `_ensure_today_bar` helper (place it just before `_process_ticker`):

```python
def _ensure_today_bar(
    ticker: str,
    price_provider: DataProvider,
    conn,
    date: str,
) -> None:
    """Append today's bar to price_history via INSERT OR IGNORE.

    Tries single-bar fetch (get_ohlc_after) first; falls back to full
    history fetch for fresh installs without historical_loader data."""
    existing = conn.execute(
        "SELECT 1 FROM price_history WHERE ticker=? AND date=?",
        (ticker, date),
    ).fetchone()
    if existing:
        return

    df: pd.DataFrame | None = None
    try:
        df = price_provider.get_ohlc_after(ticker, date, date)
    except Exception as e:
        log.warning(f"{ticker}: single-bar fetch failed: {e}")

    if df is None or df.empty:
        try:
            df = price_provider.get_price_history(ticker, days=200)
        except Exception as e:
            log.warning(f"{ticker}: full-history fallback failed: {e}")
            return

    if df is None or df.empty:
        return

    source = getattr(price_provider, "_source_name", "yfinance")
    for ts, row in df.iterrows():
        d = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        if d > date:
            continue
        db.insert_price_bar_if_missing(
            conn, ticker=ticker, date=d,
            open_=float(row.get("Open", 0)),
            high=float(row.get("High", 0)),
            low=float(row.get("Low", 0)),
            close=float(row.get("Close", 0)),
            volume=int(row.get("Volume", 0) or 0),
            source=source,
        )
    conn.commit()
```

Replace `_process_ticker` with the incremental version:

```python
def _process_ticker(
    ticker: str,
    price_provider: DataProvider,
    earnings_provider: DataProvider,
    conn,
    date: str,
    run_type: str,
) -> dict | None:
    # Step 1: Ensure today's bar is in DB
    _ensure_today_bar(ticker, price_provider, conn, date)

    # Step 2: Load last 200 days from DB for indicator calculation
    df = db.load_price_history_from_db(conn, ticker, as_of_date=date, limit=200)

    if df is None or len(df) < MIN_BARS_RSI:
        rows = 0 if df is None else len(df)
        db.log_skipped_ticker(
            conn, ticker=ticker, date=date, run_type=run_type,
            reason=f"insufficient bars: {rows} < {MIN_BARS_RSI}",
            learnable=False,
        )
        return None

    # Indicators (computed from DB data — df has capitalized column names)
    pc = compute_price_changes(df)
    td: dict[str, Any] = {
        "ticker": ticker,
        "price":  float(df["Close"].iloc[-1]),
        **pc,
        "rsi_14":             compute_rsi_14(df),
        "rsi_trend":          compute_rsi_trend(df),
        "macd_signal":        compute_macd_signal(df),
        "atr_pct":            compute_atr_pct(df),
        "bb_position":        compute_bb_position(df),
        "above_sma20":        compute_sma_distance_pct(df, 20),
        "above_sma50":        compute_sma_distance_pct(df, 50),
        "above_sma200":       compute_sma_distance_pct(df, 200),
        "volume_ratio":       compute_volume_ratio(df),
        "intraday_range_pct": compute_intraday_range_pct(df),
    }

    # Fundamentals: cache-first (Task 6)
    cached_fund = db.get_cached_fundamentals(conn, ticker, today=date)
    if cached_fund is not None:
        fundamentals = cached_fund
    else:
        try:
            fundamentals = earnings_provider.get_fundamentals(ticker) or {}
        except Exception as e:
            log.warning(f"{ticker}: fundamentals raised: {e}")
            fundamentals = {}
        if fundamentals:
            db.save_fundamentals_cache(conn, ticker, fundamentals, fetched_date=date)

    td.update({
        "pe_ratio":              fundamentals.get("pe_ratio"),
        "forward_pe":            fundamentals.get("forward_pe"),
        "market_cap_b":          fundamentals.get("market_cap_b"),
        "debt_equity":           fundamentals.get("debt_equity"),
        "sector":                fundamentals.get("sector", "Unknown"),
        "analyst_target_upside": fundamentals.get("analyst_upside"),
        "analyst_consensus":     fundamentals.get("consensus"),
    })

    # Earnings
    try:
        earnings = earnings_provider.get_earnings_calendar(ticker) or {}
    except Exception as e:
        log.warning(f"{ticker}: earnings raised: {e}")
        earnings = {}
    td["earnings_in_days"]  = earnings.get("days_to_next")
    td["earnings_beat_pct"] = earnings.get("last_beat_pct")

    td["data_quality"] = _classify_data_quality(td)
    if td["data_quality"] == "low":
        db.log_skipped_ticker(
            conn, ticker=ticker, date=date, run_type=run_type,
            reason="data_quality=low: critical indicators missing",
            learnable=False,
        )
        return None

    _persist_indicators(conn, ticker, date, td)
    return td
```

Also update `_classify_data_quality` — restore `above_sma200` as a peripheral field now that 200-day data is available from the DB (carryover fix **#9**):

```python
def _classify_data_quality(td: dict) -> str:
    required   = ("rsi_14", "atr_pct")
    peripheral = ("pe_ratio", "market_cap_b", "sector", "above_sma200")
    if any(td.get(k) is None for k in required):
        return "low"
    missing_peripheral = sum(1 for k in peripheral if td.get(k) is None)
    return "medium" if missing_peripheral >= 1 else "high"
```

Remove the now-unused `_persist_price_history` helper (it was only called from the old `_process_ticker`). Keep `_persist_indicators` unchanged.

- [ ] **Step 7.5: Switch main.py to CapitalComProvider as primary**

In `main.py`, add import:

```python
from src.providers.capital_provider import CapitalComProvider
```

In `run_pipeline()`, replace:

```python
price_provider = YFinanceProvider()
```

With:

```python
price_provider = CapitalComProvider() if config.CAPITAL_COM_API_KEY else YFinanceProvider()
```

Do the same in `run_close()`.

- [ ] **Step 7.6: Run tests to confirm they pass**

```
pytest tests/unit/test_data_collector.py -v
```

Expected: all `PASS`

- [ ] **Step 7.7: Full suite**

```
pytest tests/ --cov=src --cov-fail-under=80 -q
```

- [ ] **Step 7.8: Commit**

```bash
git add src/db.py src/data_collector.py main.py tests/unit/test_data_collector.py
git commit -m "feat: incremental DB update — single-bar fetch per run, indicators from 200-day DB window"
```

---

## Task 8: position_check Run-Type

**Files:**
- Create: `prompts/position_check_v1.txt`
- Modify: `src/email_sender.py`
- Modify: `main.py`
- Modify: `tests/unit/test_main.py`
- Modify: `tests/unit/test_email_sender.py`

- [ ] **Step 8.1: Write failing tests**

```python
# tests/unit/test_main.py — append:
def test_position_check_calls_get_open_positions(tmp_db_path, mocker):
    """position_check must call get_open_positions on Capital.com."""
    mock_capital = mocker.MagicMock()
    mock_capital.get_open_positions.return_value = []
    mocker.patch("main.CapitalComProvider", return_value=mock_capital)
    mocker.patch("src.utils.call_claude")
    mocker.patch("src.email_sender._send")

    from main import run_position_check
    run_position_check(date="2026-05-21", db_path=str(tmp_db_path))
    mock_capital.get_open_positions.assert_called_once()


def test_position_check_always_sends_email(tmp_db_path, mocker):
    mock_capital = mocker.MagicMock()
    mock_capital.get_open_positions.return_value = []
    mocker.patch("main.CapitalComProvider", return_value=mock_capital)
    mocker.patch("src.utils.call_claude")
    mock_send = mocker.patch("src.email_sender._send")

    from main import run_position_check
    run_position_check(date="2026-05-21", db_path=str(tmp_db_path))
    mock_send.assert_called_once()
```

```python
# tests/unit/test_email_sender.py — append:
def test_render_position_check_html_contains_tickers():
    from src.email_sender import render_position_check_html
    payload = {
        "date": "2026-05-21",
        "checks": [
            {"ticker": "AAPL", "direction": "long",
             "status": "on_track", "note": "Moving as expected"},
            {"ticker": "MSFT", "direction": "short",
             "status": "near_sl",  "note": "Approaching stop-loss"},
        ],
        "summary": "1 position on track, 1 near SL.",
    }
    html = render_position_check_html(payload)
    assert "AAPL" in html
    assert "MSFT" in html
    assert "on track" in html.lower() or "[OK]" in html


def test_send_position_check_email_subject_contains_count(mocker):
    mock_send = mocker.patch("src.email_sender._send")
    from src.email_sender import send_position_check_email
    send_position_check_email(
        payload={
            "date": "2026-05-21",
            "checks": [
                {"ticker": "AAPL", "status": "near_sl", "direction": "long", "note": ""},
            ],
            "summary": "1 warning.",
        },
        api_key="key", email_from="a@b.com", email_to="x@y.com",
    )
    subject = mock_send.call_args[0][3]
    assert "2026-05-21" in subject
    assert "1" in subject
```

- [ ] **Step 8.2: Run tests to confirm they fail**

```
pytest tests/unit/test_main.py::test_position_check_calls_get_open_positions -v
```

Expected: `FAIL` — `cannot import name 'run_position_check'`

- [ ] **Step 8.3: Create prompts/position_check_v1.txt**

```
You are a risk monitor checking whether open CFD positions are on track.
Analysiere ausschliesslich was heute preisrelevant ist (Intraday-Horizont).
TP und SL muessen innerhalb eines Handelstages erreichbar sein.
Katalysatoren muessen heute oder vorboerslich morgen wirken.

You receive a JSON list of open positions with entry price, current price, TP and SL.
For each position assess briefly whether it is on track.

Output ONLY a single JSON object with this EXACT shape:

{
  "checks": [
    {
      "ticker": "<symbol>",
      "direction": "<long|short>",
      "status": "<on_track|near_sl|signal_fallen>",
      "note": "<one sentence, max 120 chars>"
    }
  ],
  "summary": "<overall assessment, max 300 chars>"
}

status values:
  on_track      — position moving as expected, TP likely reachable today
  near_sl       — price within 20% of the SL distance, monitor closely
  signal_fallen — fundamental change, original thesis no longer holds

If no positions provided return: {"checks": [], "summary": "Keine offenen Positionen."}
```

- [ ] **Step 8.4: Add email helpers to email_sender.py**

Append to `src/email_sender.py`:

```python
def render_position_check_html(payload: dict) -> str:
    checks = payload.get("checks") or []
    _icons = {"on_track": "[OK]", "near_sl": "[WARN]", "signal_fallen": "[ALERT]"}
    rows = "".join(
        f'<tr><td>{_h(_icons.get(c.get("status", ""), ""))}</td>'
        f'<td>{_h(c.get("ticker"))}</td>'
        f'<td>{_h(c.get("direction"))}</td>'
        f'<td>{_h(c.get("note", ""))}</td></tr>'
        for c in checks
    )
    return (
        '<html><body style="font-family:sans-serif;font-size:14px;">'
        f'<h1>Shares_Future Position-Check — {_h(payload.get("date"))}</h1>'
        f'<p><b>{_h(payload.get("summary"))}</b></p>'
        '<table border="1" cellpadding="4" cellspacing="0">'
        '<tr><th>Status</th><th>Ticker</th><th>Dir</th><th>Note</th></tr>'
        + rows
        + '</table>'
        f'<p><small>{_h(_DISCLAIMER)}</small></p>'
        '</body></html>'
    )


def send_position_check_email(
    payload: dict, api_key: str, email_from: str, email_to: str,
) -> None:
    html_body = render_position_check_html(payload)
    checks = payload.get("checks") or []
    n_warn = sum(1 for c in checks if c.get("status") in ("near_sl", "signal_fallen"))
    subject = (
        f"[Shares_Future] {payload.get('date')} Position-Check — "
        f"{len(checks)} Pos, {n_warn} Warnung(en)"
    )
    _send(api_key, email_from, email_to, subject, html_body)
```

- [ ] **Step 8.5: Add run_position_check() and route to main.py**

In `main.py`, add to imports:

```python
import json
from pathlib import Path
from src.email_sender import (
    send_daily_email, send_weekly_email, send_position_check_email,
)
from src.utils import call_claude, extract_json_blob
```

(Remove any duplicate imports of `send_daily_email` / `send_weekly_email` already there.)

Update `RUN_TYPES`:

```python
RUN_TYPES = ["pre_market", "midday", "close", "evaluate", "weekly", "position_check"]
```

Add function after `run_close`:

```python
def run_position_check(date: str, db_path: str) -> None:
    """Read open Capital.com positions, compare to DB predictions, send status mail."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    capital = CapitalComProvider()

    real_positions = capital.get_open_positions()
    open_preds     = db.load_open_predictions(conn)
    real_by_ticker = {p["ticker"]: p for p in real_positions if p.get("ticker")}

    position_inputs = [
        {
            "ticker":        pred["ticker"],
            "direction":     pred["direction"],
            "entry_price":   pred["entry_price"],
            "current_price": real_by_ticker.get(pred["ticker"], {}).get("current_price"),
            "tp_price":      pred["tp_price"],
            "sl_price":      pred["sl_price"],
            "profit_loss":   real_by_ticker.get(pred["ticker"], {}).get("profit_loss"),
        }
        for pred in open_preds
    ]

    if not position_inputs:
        parsed = {"checks": [], "summary": "Keine offenen Positionen."}
    else:
        system_prompt = (Path("prompts") / "position_check_v1.txt").read_text()
        user_msg      = f"Today is {date}. Open positions:\n{json.dumps(position_inputs, indent=2)}"
        result        = call_claude(
            model=config.CLAUDE_MODEL_SONNET,
            system=system_prompt,
            user=user_msg,
            max_tokens=1024,
            tools=[],
        )
        try:
            parsed = extract_json_blob(result.text, RuntimeError)
        except Exception:
            parsed = {"checks": [], "summary": "Parse error — raw: " + result.text[:200]}

    send_position_check_email(
        payload={"date": date, **parsed},
        api_key=config.SENDGRID_API_KEY,
        email_from=config.EMAIL_FROM,
        email_to=config.EMAIL_TO,
    )
    conn.close()
```

In `main()`, add the route:

```python
elif ns.run_type == "position_check":
    run_position_check(date=date, db_path=ns.db_path)
```

Also update `parse_args` choices to match `RUN_TYPES`.

- [ ] **Step 8.6: Run tests to confirm they pass**

```
pytest tests/unit/test_main.py tests/unit/test_email_sender.py -v
```

Expected: all `PASS`

- [ ] **Step 8.7: Full suite**

```
pytest tests/ --cov=src --cov-fail-under=80 -q
```

- [ ] **Step 8.8: Commit**

```bash
git add prompts/position_check_v1.txt src/email_sender.py main.py tests/unit/test_main.py tests/unit/test_email_sender.py
git commit -m "feat: add position_check run-type — Capital.com position read + brief status mail"
```

---

## Task 9: historical_loader.py + 500-Ticker Scaling

**Files:**
- Create: `setup/__init__.py`
- Create: `setup/historical_loader.py`
- Create: `tests/unit/test_historical_loader.py`
- Modify: `config.py`
- Modify: `main.py`

- [ ] **Step 9.1: Write failing tests**

```python
# tests/unit/test_historical_loader.py
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date, timedelta


def _multi_day_df(days: int = 756) -> pd.DataFrame:
    dates = pd.date_range(start="2023-01-02", periods=days, freq="B")
    return pd.DataFrame(
        {
            "Open":   [100.0] * days,
            "High":   [105.0] * days,
            "Low":    [ 99.0] * days,
            "Close":  [102.0] * days,
            "Volume": [1_000_000] * days,
        },
        index=dates,
    )


def test_load_ticker_history_inserts_rows(tmp_path):
    db_path = str(tmp_path / "test.db")
    import sqlite3
    from src import db
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)
    conn.close()

    with patch("setup.historical_loader.CapitalComProvider") as MockCap:
        MockCap.return_value.get_price_history.return_value = _multi_day_df(756)
        from setup.historical_loader import load_ticker_history
        inserted = load_ticker_history("AAPL", db_path=db_path)

    assert inserted > 0
    conn = sqlite3.connect(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM price_history WHERE ticker='AAPL'"
    ).fetchone()[0]
    conn.close()
    assert count == inserted


def test_load_ticker_history_skips_duplicates(tmp_path):
    db_path = str(tmp_path / "test.db")
    import sqlite3
    from src import db
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)
    conn.close()

    df = _multi_day_df(30)
    with patch("setup.historical_loader.CapitalComProvider") as MockCap:
        MockCap.return_value.get_price_history.return_value = df
        from setup.historical_loader import load_ticker_history
        first  = load_ticker_history("MSFT", db_path=db_path)
        second = load_ticker_history("MSFT", db_path=db_path)

    assert first  == 30
    assert second == 0


def test_load_all_calls_load_ticker_history_per_ticker(mocker):
    mock_load = mocker.patch(
        "setup.historical_loader.load_ticker_history", return_value=100
    )
    from setup.historical_loader import load_all
    load_all(tickers=["AAPL", "MSFT", "NVDA"], db_path=":memory:")
    assert mock_load.call_count == 3


def test_load_ticker_history_returns_zero_on_empty_df(tmp_path):
    db_path = str(tmp_path / "test.db")
    import sqlite3
    from src import db
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)
    conn.close()

    with patch("setup.historical_loader.CapitalComProvider") as MockCap:
        MockCap.return_value.get_price_history.return_value = None
        from setup.historical_loader import load_ticker_history
        result = load_ticker_history("UNKNOWN", db_path=db_path)

    assert result == 0
```

- [ ] **Step 9.2: Run tests to confirm they fail**

```
pytest tests/unit/test_historical_loader.py -v
```

Expected: `FAIL` — `ModuleNotFoundError: No module named 'setup.historical_loader'`

- [ ] **Step 9.3: Create setup/__init__.py**

Create an empty file at `setup/__init__.py`.

- [ ] **Step 9.4: Create setup/historical_loader.py**

```python
"""One-time 3-year historical data pull via Capital.com.

Usage:
    python setup/historical_loader.py --all          # loads SP500_MVP_TICKERS
    python setup/historical_loader.py --full-sp500   # loads SP500_FULL_TICKERS (~500)
    python setup/historical_loader.py --tickers AAPL MSFT NVDA

Each ticker: get_price_history(days=1095) → INSERT OR IGNORE into price_history.
"""
import argparse
import logging
import sqlite3
import time

import config
from src import db
from src.providers.capital_provider import CapitalComProvider

log = logging.getLogger("shares_future.historical_loader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DAYS_3_YEARS       = 1095
PAUSE_BETWEEN_TICKERS = 0.5  # 0.5s → 120 req/min; Capital.com allows 600/min


def load_ticker_history(
    ticker: str,
    db_path: str = str(config.DB_PATH),
    days: int    = DAYS_3_YEARS,
) -> int:
    """Fetch and persist historical OHLCV for one ticker.

    Returns the number of rows newly inserted (0 if all already existed)."""
    provider = CapitalComProvider()
    df = provider.get_price_history(ticker, days=days)
    if df is None or df.empty:
        log.warning(f"{ticker}: no data returned from Capital.com")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)

    inserted = 0
    for ts, row in df.iterrows():
        d   = ts.strftime("%Y-%m-%d")
        cur = conn.execute(
            """INSERT OR IGNORE INTO price_history
               (ticker, date, open, high, low, close, volume, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticker, d,
                float(row.get("Open",   0)),
                float(row.get("High",   0)),
                float(row.get("Low",    0)),
                float(row.get("Close",  0)),
                int(row.get("Volume", 0) or 0),
                "capital.com",
            ),
        )
        inserted += cur.rowcount
    conn.commit()
    conn.close()
    log.info(f"{ticker}: {inserted}/{len(df)} rows inserted")
    return inserted


def load_all(
    tickers: list[str],
    db_path: str  = str(config.DB_PATH),
    days: int     = DAYS_3_YEARS,
) -> dict[str, int]:
    """Load historical data for all tickers. Returns {ticker: rows_inserted}."""
    results: dict[str, int] = {}
    for i, ticker in enumerate(tickers):
        log.info(f"[{i + 1}/{len(tickers)}] Loading {ticker}…")
        results[ticker] = load_ticker_history(ticker, db_path=db_path, days=days)
        time.sleep(PAUSE_BETWEEN_TICKERS)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Load 3-year Capital.com price history")
    group  = parser.add_mutually_exclusive_group()
    group.add_argument("--tickers",    nargs="+", help="Specific tickers to load")
    group.add_argument("--all",        action="store_true", help="Load SP500_MVP_TICKERS")
    group.add_argument("--full-sp500", action="store_true", help="Load SP500_FULL_TICKERS (~500)")
    parser.add_argument("--db-path", default=str(config.DB_PATH))
    parser.add_argument("--days",    type=int, default=DAYS_3_YEARS)
    args = parser.parse_args()

    if args.tickers:
        tickers = args.tickers
    elif getattr(args, "full_sp500", False):
        tickers = config.SP500_FULL_TICKERS
    else:
        tickers = config.SP500_MVP_TICKERS

    log.info(f"Loading {len(tickers)} tickers × {args.days} days")
    results = load_all(tickers, db_path=args.db_path, days=args.days)
    log.info(f"Done. {sum(results.values())} rows inserted across {len(tickers)} tickers.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 9.5: Add SP500_FULL_TICKERS + USE_FULL_SP500 to config.py**

In `config.py`, append:

```python
USE_FULL_SP500 = os.getenv("USE_FULL_SP500", "false").lower() == "true"

# Full S&P 500 ticker list.
# Source: https://en.wikipedia.org/wiki/List_of_S%26P_500_companies
# Implementer: replace this MVP stub with the complete 500-symbol list
# before setting USE_FULL_SP500=true in production.
SP500_FULL_TICKERS: list[str] = SP500_MVP_TICKERS  # replace with full list
```

- [ ] **Step 9.6: Update main.py to use full tickers when enabled**

In `run_pipeline()`, replace:

```python
sp500_tds, skipped_sp = collect(
    tickers=config.SP500_MVP_TICKERS,
```

With:

```python
_tickers = config.SP500_FULL_TICKERS if config.USE_FULL_SP500 else config.SP500_MVP_TICKERS
sp500_tds, skipped_sp = collect(
    tickers=_tickers,
```

- [ ] **Step 9.7: Run tests to confirm they pass**

```
pytest tests/unit/test_historical_loader.py -v
```

Expected: all 4 tests `PASS`

- [ ] **Step 9.8: Full suite**

```
pytest tests/ --cov=src --cov-fail-under=80 -q
```

Expected: green, ≥ 80 % coverage

- [ ] **Step 9.9: Commit**

```bash
git add setup/ tests/unit/test_historical_loader.py config.py main.py
git commit -m "feat: historical_loader for 3-year Capital.com pull + USE_FULL_SP500 flag"
```

---

## Self-Review Checklist

The following was checked against `docs/2026-05-21-sprint2-changes.md`:

| Spec item | Covered by |
|---|---|
| Änderung A — Run-Types (evaluate / close / position_check) | Tasks 1, 8 |
| Änderung B — Timezone double-crons + TZ="Europe/Berlin" bash | Task 4 |
| Änderung B — Python `zoneinfo` throughout | Tasks 4, 5 |
| Änderung C — CapitalComProvider (OHLC, premarket, positions) | Task 5 |
| Änderung C — Finnhub for fundamentals (not Capital.com) | Task 6 |
| Änderung D — DB incremental: 1 bar/day + indicators from DB | Task 7 |
| Änderung D — premarket_price column | Task 7 |
| Änderung D — `historical_loader.py` 3-year pull | Task 9 |
| Änderung E — ATR_MIN=2.0, MAX_HOLD_DAYS=5, HOLD_TARGET="intraday" | Task 1 |
| Änderung E — Intraday focus in all prompts | Task 2 |
| Änderung F — generate_daily_briefing + "Was heute zählt" box | Task 3 |
| Änderung G — position_check run with GET /positions | Task 8 |
| fundamentals_cache table (7-day TTL) | Task 6 |
| Sprint 2 scope — 500-ticker scaling | Task 9 |
| Carryover #9 — above_sma200 back in peripheral | Task 7 |
| Carryover #13 — MIN_BARS_MACD constant | Task 7 |
| Carryover #21 — raw BEGIN/COMMIT in update_outcome_close | Task 6 |

**No placeholders found.** All steps contain complete code.

**Type consistency verified:** `load_price_history_from_db` returns a DataFrame with capitalized columns (Open/High/Low/Close/Volume) matching what `compute_*` helpers expect. `_ensure_today_bar` uses `insert_price_bar_if_missing` which is defined in Task 7 Step 3.
