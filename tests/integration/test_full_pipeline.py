"""E2E mocked-API pipeline test: 3 SP500 tickers + 2 commodities."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd

import main as orchestrator

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def _mock_ohlc():
    idx = pd.date_range("2026-02-19", "2026-05-19", freq="B")[-90:]
    # NOTE: Deviation from plan-text — the plan supplies constant Close=100.5,
    # which yields RSI=None (no up/down moves) and triggers data_quality=low,
    # skipping every ticker. Tiny alternating variation keeps the spirit of a
    # synthetic fixture but lets the Phase-1 indicators produce non-None RSI so
    # the pipeline reaches Phase 3 and ultimately persists predictions. All
    # other code in this test is copied verbatim from the plan.
    closes = [100.5 + (i % 2) * 0.5 for i in range(len(idx))]
    return pd.DataFrame({
        "Open":   [100.0] * len(idx),
        "High":   [101.5] * len(idx),
        "Low":    [99.0]  * len(idx),
        "Close":  closes,
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
