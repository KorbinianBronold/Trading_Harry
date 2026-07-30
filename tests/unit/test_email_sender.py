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


def test_send_daily_email_posts_to_resend():
    payload = _sample_payload()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"id": "abc-123"}
    with patch("src.email_sender.requests.post", return_value=resp) as post:
        send_daily_email(
            payload=payload,
            api_key="re_fake",
            email_from="onboarding@resend.dev",
            email_to="to@example.com",
        )
    post.assert_called_once()
    url = post.call_args.args[0] if post.call_args.args else post.call_args.kwargs["url"]
    assert url == "https://api.resend.com/emails"
    sent = post.call_args.kwargs["json"]
    assert sent["from"] == "onboarding@resend.dev"
    assert sent["to"] == ["to@example.com"]
    assert "<" in sent["html"], "HTML-Body muss als html-Feld gehen, nicht als text"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer re_fake"


def test_send_uses_requests_not_urllib():
    """Resend sitzt hinter Cloudflare, das die urllib-Signatur mit 403/1010
    sperrt. Der Versand MUSS ueber requests laufen."""
    import inspect
    import re
    from src import email_sender
    src = inspect.getsource(email_sender)
    # Auf den Import pruefen, nicht auf das Wort — der Docstring erwaehnt urllib
    # bewusst, um die Entscheidung zu begruenden.
    assert not re.search(r"^\s*(import urllib|from urllib)", src, re.M)
    assert "requests.post" in src


def test_send_daily_email_raises_on_non_2xx():
    payload = _sample_payload()
    resp = MagicMock()
    resp.status_code = 500
    resp.text = "server error"
    with patch("src.email_sender.requests.post", return_value=resp):
        with pytest.raises(EmailSendError):
            send_daily_email(
                payload=payload, api_key="re_fake",
                email_from="onboarding@resend.dev", email_to="to@example.com",
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




# ---------- Fehlertext des Anbieters durchreichen ----------


def test_send_surfaces_the_provider_response_body(mocker):
    """Ein 4xx ohne Klartext kostet Stunden. Beim Vorgaenger-Anbieter war ein
    leeres Kontingent nicht von einem kaputten Key zu unterscheiden, weil der Body
    verworfen wurde. Bei Resend kommen ein abgelehnter Absender und ein
    ungueltiger Key ebenfalls beide als 4xx — der Body muss mit."""
    from src.email_sender import _send, EmailSendError

    resp = mocker.MagicMock()
    resp.status_code = 403
    resp.text = '{"message":"The onboarding@resend.dev address is restricted"}'
    mocker.patch("src.email_sender.requests.post", return_value=resp)

    with pytest.raises(EmailSendError) as e:
        _send("re_k", "onboarding@resend.dev", "c@d.de", "subj", "<p>x</p>")

    assert "restricted" in str(e.value)
    assert "403" in str(e.value)


def test_send_survives_a_transport_error(mocker):
    """Ein Netzwerkfehler darf nicht als AttributeError durchschlagen."""
    from src.email_sender import _send, EmailSendError

    mocker.patch("src.email_sender.requests.post",
                 side_effect=ConnectionError("connection reset"))
    with pytest.raises(EmailSendError) as e:
        _send("re_k", "onboarding@resend.dev", "c@d.de", "subj", "<p>x</p>")
    assert "connection reset" in str(e.value)


def test_send_logs_the_message_id_on_success(mocker, caplog):
    """Resend gibt eine id zurueck — die ist der Belegnachweis im Log."""
    from src.email_sender import _send

    resp = mocker.MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"id": "9f1c-42"}
    mocker.patch("src.email_sender.requests.post", return_value=resp)

    with caplog.at_level("INFO"):
        _send("re_k", "onboarding@resend.dev", "c@d.de", "subj", "<p>x</p>")
    assert "9f1c-42" in caplog.text


def test_send_returns_the_message_id(mocker):
    """Der Aufrufer braucht die id, um die tatsaechliche Zustellung nachzusehen —
    ein 2xx auf den POST heisst bei Resend nur 'angenommen', nicht 'zugestellt'."""
    from src.email_sender import _send
    resp = mocker.MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"id": "2c89-abc"}
    mocker.patch("src.email_sender.requests.post", return_value=resp)
    assert _send("re_k", "a@b.de", "c@d.de", "s", "<p>x</p>") == "2c89-abc"


def test_send_returns_none_when_no_id_comes_back(mocker):
    from src.email_sender import _send
    resp = mocker.MagicMock()
    resp.status_code = 200
    resp.json.side_effect = ValueError("no json")
    mocker.patch("src.email_sender.requests.post", return_value=resp)
    assert _send("re_k", "a@b.de", "c@d.de", "s", "<p>x</p>") is None
