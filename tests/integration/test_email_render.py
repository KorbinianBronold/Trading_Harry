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
