"""E2E mocked-API pipeline test: 3 SP500 tickers + 2 commodities."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import config

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
    fake_provider.get_ohlc_after.return_value = None
    # Der Entscheidungskurs kommt seit dem Preismodell-Umbau (2026-08-06) live
    # statt aus dem letzten DB-Close. Derselbe Wert wie zuvor, damit Guardrails
    # und TP/SL-Fixtures unveraendert greifen.
    fake_provider.get_premarket_price.return_value = float(
        _mock_ohlc()["Close"].iloc[-1])
    # Seit Sprint 3C / Plan 2, Task 5 laeuft Phase 1b ueber den Sammelabruf
    # get_premarket_prices_batch() statt ueber get_premarket_price() je Ticker
    # (_sweep_phase()). Ohne dieses Mock liefert die bare MagicMock-Kette einen
    # nicht-JSON-serialisierbaren Wert in den Sidecar, den broad_scan_batch()
    # (Task 10) als erstes tatsaechlich serialisiert -- vorher blieb das
    # unbemerkt, weil quick_filter_batch() den Sidecar nie gelesen hat.
    _close_price = float(_mock_ohlc()["Close"].iloc[-1])
    fake_provider.get_premarket_prices_batch.side_effect = (
        lambda tickers: {t: _close_price for t in tickers}
    )
    fake_provider.get_fundamentals.return_value = {
        "pe_ratio": 25.0, "forward_pe": 23.0, "market_cap_b": 200.0,
        "debt_equity": 1.0, "sector": "Technology", "analyst_upside": 5.0,
        "consensus": "Buy",
    }
    fake_provider.get_earnings_calendar.return_value = {
        "days_to_next": 14, "last_beat_pct": 3.5,
    }
    fake_provider_cls.return_value = fake_provider

    monkeypatch.setattr(orchestrator, "CapitalComProvider", fake_provider_cls)
    monkeypatch.setattr(orchestrator, "FinnhubProvider", fake_provider_cls)
    monkeypatch.setattr(orchestrator.config, "SP500_PROD_TICKERS",
                        ["AAPL", "MSFT", "NVDA"])
    monkeypatch.setattr(orchestrator.config, "COMMODITY_TICKERS",
                        {"Gold": "GC=F"})
    monkeypatch.setattr(orchestrator.config, "CRYPTO_TICKERS",
                        {"Bitcoin": "BTC-USD"})

    # Stub Claude calls (one mock per module-level call_claude)
    trend_resp = (FIXTURE_DIR / "mock_trend_response.json").read_text()
    policy_resp = (FIXTURE_DIR / "mock_policy_monitor_response.json").read_text()
    deep_resp = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    cc_resp = (FIXTURE_DIR / "mock_commodities_crypto_response.json").read_text()

    def _r(text, web_search_calls=2, model=config.CLAUDE_MODEL_SONNET):
        r = MagicMock()
        r.text = text
        r.input_tokens = 1000
        r.output_tokens = 600
        r.cache_read_tokens = 200
        r.cache_creation_tokens = 100
        r.model = model
        r.web_search_calls = web_search_calls
        return r

    # Seit Sprint 3C / Plan 2, Task 10 ersetzt der Nachrichten-Scan
    # (broad_scan_batch) den Haiku-Quick-Filter. news_strength=1 fuer alle drei
    # laesst sie den Cutoff passieren, damit die drei nachfolgenden
    # deep_analysis-Calls (sequence[3..5]) weiterhin wie bisher feuern.
    broad_scan_resp_3 = json.dumps({"results": [
        {"ticker": "AAPL", "news_strength": 1, "news_note": "x"},
        {"ticker": "MSFT", "news_strength": 1, "news_note": "x"},
        {"ticker": "NVDA", "news_strength": 1, "news_note": "x"},
    ]})

    # Seit Sprint 3C / Plan 3a, Task 9 laeuft Phase 3 gebatcht
    # (analyze_batches()): alle drei Ticker liegen im selben Sub-Sektor
    # ("Technology", aus dem gefakten get_fundamentals()) und landen deshalb
    # in EINEM Batch -- ein einziger call_claude-Call mit einer
    # results-Liste statt drei Einzelantworten.
    deep_obj = json.loads(deep_resp)
    def _deep_for(ticker: str) -> dict:
        cp = dict(deep_obj)
        cp["ticker"] = ticker
        return cp

    deep_batch_resp = json.dumps({"results": [
        _deep_for("AAPL"), _deep_for("MSFT"), _deep_for("NVDA"),
    ]})

    # Seit 2026-08-19 laeuft Phase 3b gebatcht nach asset_class
    # (commodities_crypto.build_batches()): mit genau 1 Commodity- und 1
    # Crypto-Ticker landet hier weiterhin je ein Asset in einem Batch, aber
    # die Antwort braucht jetzt den results-Wrapper wie bei Phase 3.
    cc_obj = json.loads(cc_resp)
    def _cc_for(ticker: str, asset_class: str) -> str:
        cp = dict(cc_obj)
        cp["ticker"] = ticker
        cp["asset_class"] = asset_class
        return json.dumps({"results": [cp]})

    # Phase 0b: wie die anderen Phasen auf Modulebene gemockt, damit der
    # Integrationstest den Markt-Kontext wirklich durchlaeuft (Parsen +
    # DB-Schreiben) statt ihn wegzustubben.
    market_ctx_resp = json.dumps({
        "vix_level": 17.8, "advance_decline_ratio": 1.6,
        "market_regime": "risk_on", "sector_rotation_in": "Technology",
        "sector_rotation_out": "Utilities", "macro_summary": "Ruhig.",
    })

    sequence = [
        _r(trend_resp, web_search_calls=4),                  # analyze_trends
        _r(broad_scan_resp_3, web_search_calls=3),            # broad_scan
        _r(policy_resp, web_search_calls=3),                 # policy_monitor
        _r(deep_batch_resp),                                  # deep: 1 Batch (AAPL+MSFT+NVDA)
        _r(_cc_for("GC=F", "commodity")),                    # cc: 1 Batch (Gold)
        _r(_cc_for("BTC-USD", "crypto")),                    # cc: 1 Batch (BTC)
    ]

    # Seit Sprint 3B / Plan 2 (B.5) laeuft Phase 4a NACH Phase 4 (Ranking) und
    # sieht damit auch die soeben in diesem Lauf persistierten Predictions als
    # offene Positionen — anders als vorher braucht der Mock hier also eine
    # echte Antwort statt eines ungenutzten Platzhalters.
    portfolio_check_resp = json.dumps({
        "action": "HALTEN", "reason": "These intakt, kein Eingriff noetig.",
        "new_sl_price": None, "new_tp_price": None,
        "market_context_changed": False, "sources_used": [],
    })

    # Kurshistorie ins Setup: seit dem Preismodell-Umbau (2026-08-06) ist
    # final_close der alleinige Schreiber von price_history, Phase 1 liest sie
    # nur noch. In Produktion legt sie setup/historical_loader.py an; frueher
    # schrieb der Fallback der Datensammlung sie hier stillschweigend mit.
    from src import db as _seed_db
    _seed_conn = _seed_db.connect(str(db_path))
    _seed_db.init_schema(_seed_conn)
    for _t in ("AAPL", "MSFT", "NVDA", "GC=F", "BTC-USD"):
        for _ts, _row in _mock_ohlc().iterrows():
            _seed_db.upsert_price_history(
                _seed_conn, ticker=_t, date=_ts.strftime("%Y-%m-%d"),
                open_=float(_row["Open"]), high=float(_row["High"]),
                low=float(_row["Low"]), close=float(_row["Close"]),
                volume=int(_row["Volume"]), source="capital.com",
            )
    _seed_conn.commit()
    _seed_conn.close()

    with patch("src.market_context.call_claude_retry_on_truncation",
               side_effect=[_r(market_ctx_resp, web_search_calls=2)]), \
         patch("src.trend_analyzer.call_claude_retry_on_truncation", side_effect=[sequence[0]]), \
         patch("src.broad_scan.call_claude", side_effect=[sequence[1]]), \
         patch("src.deep_analysis.call_claude_retry_on_truncation",
               side_effect=[sequence[2]]), \
         patch("src.deep_analysis.call_claude", side_effect=[sequence[3]]), \
         patch("src.commodities_crypto.call_claude",
               side_effect=[sequence[4], sequence[5]]), \
         patch("src.portfolio_check.call_claude",
               side_effect=lambda **kw: _r(portfolio_check_resp, web_search_calls=0)), \
         patch("src.email_sender.requests.post") as mock_sg, \
         patch("src.commodities_crypto.fetch_fear_greed",
               return_value={"value": 55, "label": "Greed"}):
        mock_sg.return_value = MagicMock(status_code=200,
                                         json=lambda: {'id': 'test-id'})
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

    # Phase 0b hat geschrieben, und die Predictions tragen den echten Kontext
    # statt der frueher hardcodierten None-Werte.
    ctx = conn.execute("SELECT * FROM market_context WHERE date='2026-05-19'").fetchone()
    assert ctx["advance_decline_ratio"] == 1.6      # aus Claudes JSON
    assert ctx["market_regime"] == "risk_on"        # dito
    # Der VIX kommt NICHT aus Claudes 17.8, sondern aus dem (hier gefakten)
    # Capital.com-Bar: der numerische Wert schlaegt den recherchierten.
    vix_from_provider = float(_mock_ohlc()["Close"].iloc[-1])
    assert ctx["vix_level"] == vix_from_provider

    pred = conn.execute(
        "SELECT vix_at_prediction, market_regime FROM predictions LIMIT 1").fetchone()
    assert pred["vix_at_prediction"] == vix_from_provider
    assert pred["market_regime"] == "risk_on"

    mock_sg.assert_called_once()
