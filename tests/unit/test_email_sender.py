from unittest.mock import patch, MagicMock
import pytest

from src.email_sender import (
    render_daily_html, render_weekly_html, send_daily_email,
    render_error_html, EmailSendError,
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


def test_render_error_html_contains_exception_type_and_traceback():
    exc = ValueError("something broke badly")
    html = render_error_html("pre_market", "2026-05-22", exc, "Traceback:\n  line 1")
    assert "ValueError" in html
    assert "something broke badly" in html
    assert "2026-05-22" in html
    assert "pre_market" in html
    assert "Traceback" in html


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
