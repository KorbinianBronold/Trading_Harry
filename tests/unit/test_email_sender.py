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


def test_daily_html_top10_shows_the_actual_sort_key():
    """I5 (Plan-3b-Gesamtreview): die Top-10-Tabellen sortieren nach rank_score,
    zeigten bisher aber nur total_score/probability_pct -- fuer einen Mail-Leser
    ohne DB-Zugriff war die Reihenfolge nicht nachvollziehbar (im Live-Lauf sichtbar:
    BRK-B mit Score 5.5 stand vor META mit Score 7.0, weil rank_score 9 gegen 4 sagt).
    _rank_score/_analysis_strength sind exakt die Schluessel, die rank_and_persist()s
    _enrich() an jede Top-10-Zeile anhaengt (src/ranking.py)."""
    payload = _sample_payload()
    payload["top_long"][0]["_rank_score"] = 21
    payload["top_long"][0]["_analysis_strength"] = 7
    html = render_daily_html(payload)
    assert "Rank-Score" in html
    assert "Analysis-Strength" in html
    assert "<td>21</td>" in html
    assert "<td>7</td>" in html


def test_daily_html_top10_rank_score_missing_renders_empty_not_crash():
    """Divergenz-Kandidaten haben nie _rank_score/_analysis_strength in dieser Form
    (die Klassifikations-Keys sind Top-10-spezifisch) -- ein fehlender Schluessel darf
    die Tabelle nicht zum Absturz bringen."""
    payload = _sample_payload()
    html = render_daily_html(payload)  # _sample_payload() setzt beide Keys nicht
    assert "Rank-Score" in html


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


# ---------- Sprint 3B / Plan 2, Task 14: die 16:10-Mail (Vorher/Nachher) ----------


VERDICT_PAYLOAD = {
    "date": "2026-07-30", "run_type": "trade_proposals",
    "briefing": [], "portfolio_recs": [], "commodities_crypto": [],
    "market_context": {"vix_level": 28.4, "advance_decline_ratio": 0.7},
    "cost_summary": {"total_eur": 0.61, "cache_hit_rate": 0.0, "input_tokens": 1,
                     "output_tokens": 1, "web_search_calls": 2,
                     "aborted_at_phase": None},
    "signal_changes": [
        {"ticker": "AAPL", "direction": "long", "verdict": "bestaetigt",
         "probability_before": 65, "probability_after": 71,
         "entry_window_low": 178.2, "entry_window_high": 179.0,
         "reason": "haelt nach Opening", "checks": []},
        {"ticker": "NVDA", "direction": "long", "verdict": "gedreht",
         "probability_before": 70, "probability_after": 28,
         "reason": "Sektor dreht", "checks": ["sector_momentum: SOXX -2.5%"]},
        {"ticker": "MSFT", "direction": "short", "verdict": "nicht_geprueft",
         "probability_before": 60, "probability_after": None,
         "reason": "Call unlesbar", "checks": []},
    ],
}


def test_trade_proposals_mail_shows_before_and_after():
    from src.email_sender import render_trade_proposals_html
    html = render_trade_proposals_html(VERDICT_PAYLOAD)
    assert "65" in html and "71" in html
    assert "AAPL" in html and "bestaetigt" in html


def test_trade_proposals_mail_marks_flipped_and_unchecked():
    from src.email_sender import render_trade_proposals_html
    html = render_trade_proposals_html(VERDICT_PAYLOAD)
    assert "gedreht" in html
    assert "nicht geprüft" in html or "nicht_geprueft" in html


def test_trade_proposals_mail_lists_fired_checks():
    from src.email_sender import render_trade_proposals_html
    assert "SOXX -2.5%" in render_trade_proposals_html(VERDICT_PAYLOAD)


def test_portfolio_stays_the_first_section():
    """Dokumentierte Invariante — gilt auch fuer die 16:10-Mail."""
    from src.email_sender import render_trade_proposals_html
    html = render_trade_proposals_html(VERDICT_PAYLOAD)
    assert html.index("Portfolio") < html.index("Signal")


def test_trade_proposals_mail_shows_market_warnings():
    from src.email_sender import render_trade_proposals_html
    html = render_trade_proposals_html(VERDICT_PAYLOAD)
    assert "28.4" in html or "28,4" in html


def test_send_trade_proposals_email_uses_the_shared_sender(mocker):
    send = mocker.patch("src.email_sender._send")
    from src.email_sender import send_trade_proposals_email
    send_trade_proposals_email(VERDICT_PAYLOAD, api_key="k",
                               email_from="a@b.c", email_to="d@e.f")
    send.assert_called_once()
    assert "trade_proposals" in send.call_args[0][3] or "16:10" in send.call_args[0][3]


# --- Sprint 3B / Plan 2, Task 19: Weekly-Bloecke (B.9) + Haltedauer (B.11) ---

def test_daily_table_has_a_hold_days_column():
    """B.11: hold_days_recommended ist Pflichtfeld der Analyse, stand aber nie
    in der Mail."""
    from src.email_sender import render_daily_html
    html = render_daily_html({
        "date": "2026-07-30", "run_type": "pre_market",
        "top_long": [{"ticker": "AAPL", "total_score": 7.6, "probability_pct": 65,
                      "current_price": 178.0, "tp_price": 184.0, "sl_price": 176.0,
                      "rr_ratio": 3.0, "hold_days_recommended": 2,
                      "summary": "ok", "scores": {}}],
        "top_short": [], "commodities_crypto": [], "trends": [],
        "briefing": [], "portfolio_recs": [],
        "cost_summary": {"total_eur": 3.3}, "yesterday_outcomes": {},
    })
    assert "Haltedauer" in html
    assert "<td>2</td>" in html


WEEKLY_PAYLOAD = {
    "week_label": "KW31", "long_total": 4, "long_correct": 3, "long_avg_pl": 12.0,
    "short_total": 2, "short_correct": 1, "short_avg_pl": -4.0,
    "total_pl_eur": 28.0, "trades": [],
    "cost_summary": {"total_eur": 18.4},
    "revision_effectiveness": {
        "core": {
            "confirmed": {"total": 6, "correct": 4, "pl_eur": 55.0},
            "rejected":  {"total": 3, "correct": 0, "pl_eur": -41.0},
            "unchecked": {"total": 1, "correct": 1, "pl_eur": 9.0},
        },
        "divergence": {
            "confirmed": {"total": 0, "correct": 0, "pl_eur": 0.0},
            "rejected":  {"total": 0, "correct": 0, "pl_eur": 0.0},
            "unchecked": {"total": 0, "correct": 0, "pl_eur": 0.0},
        },
        "since": "2026-07-25",
    },
    # Wie db.load_revision_verdict_stats() seit Plan 3b liefert: nach
    # (revision_verdict, candidate_class) gruppiert, also zwei Zeilen je Urteil.
    "verdict_stats": [
        {"revision_verdict": "bestaetigt", "candidate_class": "core",
         "n": 6, "n_evaluated": 5, "avg_pl": 9.2},
        {"revision_verdict": "bestaetigt", "candidate_class": "divergence",
         "n": 2, "n_evaluated": 2, "avg_pl": -3.4},
        {"revision_verdict": "gedreht", "candidate_class": "core",
         "n": 3, "n_evaluated": 3, "avg_pl": -13.7},
    ],
    "guardrail_stats": [{"rule": "vix_no_new_longs", "enforced": 1, "n": 2},
                        {"rule": "sector_momentum_partial", "enforced": 0, "n": 9}],
    "skipped_stats": [{"ticker": "FAKE", "n_week": 4, "reasons": "no data",
                       "skip_total": 12, "inactive": 0, "retry_after": None}],
    "sector_coverage": {"mapped": 18, "total": 20, "pct": 90.0},
}


def test_weekly_shows_confirmed_versus_rejected():
    from src.email_sender import render_weekly_html
    html = render_weekly_html(WEEKLY_PAYLOAD)
    assert "bestätigt" in html and "abgelehnt" in html
    assert "4/6" in html and "0/3" in html


def test_weekly_shows_all_four_blocks():
    from src.email_sender import render_weekly_html
    html = render_weekly_html(WEEKLY_PAYLOAD)
    assert "gedreht" in html                    # Block 2
    assert "vix_no_new_longs" in html           # Block 3
    assert "FAKE" in html                       # Block 4
    assert "90.0" in html or "90,0" in html     # Mapping-Abdeckung


def test_weekly_survives_a_week_without_any_1610_run():
    """Erste Woche nach dem Umbau: alle neuen Bloecke sind leer."""
    from src.email_sender import render_weekly_html
    payload = {**WEEKLY_PAYLOAD, "revision_effectiveness": None,
               "verdict_stats": [], "guardrail_stats": [], "skipped_stats": [],
               "sector_coverage": None}
    html = render_weekly_html(payload)
    assert "KW31" in html          # kein Absturz, Grundgeruest steht


def test_daily_mail_has_a_divergence_section_when_present():
    from src.email_sender import render_daily_html
    payload = {
        "date": "2026-08-17", "run_type": "pre_market",
        "divergence": [{
            "ticker": "AAPL", "direction": "long", "current_price": 230.0,
            "tp_price": 235.0, "sl_price": 228.0, "rr_ratio": 2.5,
            "_analysis_strength": 6, "summary": "Strong news, neutral technicals",
        }],
        "divergence_stats": {"tech_only_abstentions": 3, "conflicts": 1, "overflow": 0},
    }
    html = render_daily_html(payload)
    assert "Divergenz-Kandidaten" in html
    assert "AAPL" in html
    # Die Kennzahlen muessen als Zahl NEBEN ihrem Label stehen. Ein blankes
    # `"3" in html` waere wertlos -- die 3 steckt auch in "235.0".
    assert "Enthaltungen mit Technik-Richtung: 3" in html
    assert "Technik-Konflikte verworfen: 1" in html


def test_daily_mail_divergence_section_handles_empty_list():
    from src.email_sender import render_daily_html
    payload = {
        "date": "2026-08-17", "run_type": "pre_market",
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    }
    html = render_daily_html(payload)
    assert "Divergenz" in html


def test_weekly_verdict_table_distinguishes_the_two_candidate_classes():
    """I3 (Plan-3b-Abschluss-Review): load_revision_verdict_stats() gruppiert
    seit Plan 3b nach (revision_verdict, candidate_class), die Tabelle rendert
    aber nur das Urteil -- zwei Zeilen 'bestaetigt' mit verschiedenen Zahlen und
    nichts, was sie unterscheidet."""
    from src.email_sender import render_weekly_html
    html = render_weekly_html(WEEKLY_PAYLOAD)
    section = html.split("Signal-Veränderungen", 1)[1].split("<h2>", 1)[0]
    assert "Klasse" in section, "Spaltenueberschrift fehlt"
    # Beide bestaetigt-Zeilen sind vollstaendig und zuordenbar:
    assert "<td>bestaetigt</td><td>core</td><td>6</td>" in section
    assert "<td>bestaetigt</td><td>divergence</td><td>2</td>" in section


def test_weekly_renders_core_and_divergence_performance_separately():
    """I2 (Plan-3b-Abschluss-Review): divergence_summary wurde gebaut und in die
    Nutzlast gelegt, aber nie gerendert. Der P/L eines Divergenz-Trades fiel
    damit ersatzlos aus der Wochenmail -- und die kleinere Zahl las sich wie
    eine ruhige Woche, nicht wie ein fehlender Zweig."""
    from src.email_sender import render_weekly_html
    payload = {
        **WEEKLY_PAYLOAD,
        "trades": [{"date": "2026-08-12", "ticker": "MSFT", "direction": "long",
                    "entry_price": 400.0, "exit_price": 410.0,
                    "exit_reason": "tp_hit", "profit_loss_eur": 31.0}],
        "divergence_summary": {
            "long_total": 2, "long_correct": 1, "long_avg_pl": -7.5,
            "short_total": 0, "short_correct": 0, "short_avg_pl": 0.0,
            "total_pl_eur": -15.0,
            "trades": [{"date": "2026-08-13", "ticker": "GC=F",
                        "direction": "long", "entry_price": 2400.0,
                        "exit_price": 2385.0, "exit_reason": "sl_hit",
                        "profit_loss_eur": -15.0}],
        },
    }
    html = render_weekly_html(payload)
    # Beide Gruppen sind benannt, sonst kann der Leser die Zahlen nicht zuordnen.
    assert "Core" in html and "Divergenz" in html
    # Beide P/L-Summen stehen da -- und getrennt, nicht addiert.
    assert "28.0" in html, "core-Gesamt-P/L fehlt"
    assert "-15.0" in html, "divergence-Gesamt-P/L fehlt"
    assert "13.0" not in html, "core und divergence duerfen nie summiert werden"
    # Beide Trade-Listen sind da.
    assert "MSFT" in html and "GC=F" in html


def test_weekly_divergence_block_is_visible_even_when_empty():
    """Ein leerer Block ist eine Aussage ('keine Divergenz-Trades'), ein
    fehlender ist eine stille Luecke."""
    from src.email_sender import render_weekly_html
    html = render_weekly_html({**WEEKLY_PAYLOAD, "divergence_summary": None})
    # Auf das VOLLE Label pruefen: "Divergenz" allein steht auch im
    # 16:10-Block, der Test waere sonst aus dem falschen Grund gruen.
    assert "Divergenz (nur Analyse-Signal)" in html


def test_weekly_revision_block_reads_the_split_shape():
    from src.email_sender import render_weekly_html
    empty_group = {"total": 0, "correct": 0, "pl_eur": 0.0}
    payload = {
        "week_label": "KW34",
        "revision_effectiveness": {
            "core": {"confirmed": dict(empty_group), "rejected": dict(empty_group),
                     "unchecked": dict(empty_group)},
            "divergence": {"confirmed": dict(empty_group), "rejected": dict(empty_group),
                           "unchecked": dict(empty_group)},
            "since": "2026-08-10",
        },
        "verdict_stats": [], "guardrail_stats": [], "skipped_stats": [],
        "sector_coverage": [],
        "long_total": 0, "long_correct": 0, "long_avg_pl": 0.0,
        "short_total": 0, "short_correct": 0, "short_avg_pl": 0.0,
        "total_pl_eur": 0.0, "trades": [],
        "divergence_summary": {"long_total": 0, "long_correct": 0, "long_avg_pl": 0.0,
                               "short_total": 0, "short_correct": 0, "short_avg_pl": 0.0,
                               "total_pl_eur": 0.0, "trades": []},
        "cost_summary": {"total_eur": 0.0, "cache_hit_rate": 0.0,
                         "input_tokens": 0, "output_tokens": 0,
                         "web_search_calls": 0, "aborted_at_phase": None},
    }
    html = render_weekly_html(payload)  # darf nicht werfen
    assert "KW34" in html


# ---------- final_close-Mail (C.17, 2026-08-19) ----------


def _final_close_row(**overrides) -> dict:
    row = {
        "ticker": "AAPL", "direction": "long", "run_type": "pre_market",
        "revision_verdict": None, "entry_price": 178.5,
        "price_after_eod": 182.0, "tp_hit": 1, "sl_hit": 0,
        "exit_reason": "tp_hit", "correct_direction_eod": 1,
        "profit_loss_eur": 35.0,
    }
    row.update(overrides)
    return row


def test_final_close_mail_shows_ticker_prices_and_result():
    from src.email_sender import render_final_close_html
    payload = {"date": "2026-08-19", "rows": [_final_close_row()]}
    html = render_final_close_html(payload)
    assert "AAPL" in html
    assert "178.5" in html and "182.0" in html
    assert "35.0" in html or "35,0" in html


def test_final_close_mail_maps_exit_reason_to_a_label():
    from src.email_sender import render_final_close_html
    payload = {"date": "2026-08-19", "rows": [
        _final_close_row(ticker="AAPL", exit_reason="tp_hit", tp_hit=1, sl_hit=0),
        _final_close_row(ticker="MSFT", exit_reason="sl_hit", tp_hit=0, sl_hit=1,
                          correct_direction_eod=0, profit_loss_eur=-20.0),
        _final_close_row(ticker="NVDA", exit_reason="timeout", tp_hit=0, sl_hit=0),
        _final_close_row(ticker="GOOGL", exit_reason="data_missing",
                          tp_hit=0, sl_hit=0, correct_direction_eod=None,
                          profit_loss_eur=None),
    ]}
    html = render_final_close_html(payload)
    assert "TP" in html
    assert "SL" in html
    assert "Timeout" in html
    assert "Fehlende Daten" in html


def test_final_close_mail_shows_the_1610_verdict_when_present():
    from src.email_sender import render_final_close_html
    payload = {"date": "2026-08-19", "rows": [
        _final_close_row(ticker="NVDA", revision_verdict="bestaetigt",
                         run_type="trade_proposals"),
        _final_close_row(ticker="META", revision_verdict="gedreht"),
    ]}
    html = render_final_close_html(payload)
    assert "bestaetigt" in html
    assert "gedreht" in html


def test_final_close_mail_handles_no_evaluations():
    from src.email_sender import render_final_close_html
    html = render_final_close_html({"date": "2026-08-19", "rows": []})
    assert "keine" in html.lower() or "Keine" in html


def test_send_final_close_email_uses_the_shared_sender(mocker):
    send = mocker.patch("src.email_sender._send")
    from src.email_sender import send_final_close_email
    payload = {"date": "2026-08-19", "rows": [_final_close_row()]}
    send_final_close_email(payload, api_key="k", email_from="a@b.c", email_to="d@e.f")
    send.assert_called_once()
    assert "final_close" in send.call_args[0][3]


# ---- Commodities/Crypto: alle 7 immer zeigen (Bugfix 2026-08-20) ----------
# Vorher rutschten Assets, bei denen Claude sich enthielt (direction='none')
# oder die Guardrails an der Zwei-Belege-Regel scheiterten, komplett aus der
# Mail -- der Abschnitt zeigte dann "Keine Daten.". Die alte SPECIFICATION.md
# (Sektion 3) nennt aber alle sieben namentlich, und Spec 6 garantiert, dass
# sie IMMER analysiert werden. Die Analyse war da, nur das Rendering warf sie weg.

from src.email_sender import _section_commodities_crypto


def _cc(ticker, direction="long", tradeable=True, summary="Gold zieht an."):
    return {
        "ticker": ticker, "asset_class": "commodity", "direction": direction,
        "current_price": 2380.0, "tp_price": 2420.0, "sl_price": 2360.0,
        "total_score": 6.9, "probability_pct": 58, "confidence": "medium",
        "summary": summary, "tradeable": tradeable,
        "extra": {"fear_greed_value": 62},
    }


def test_commodities_section_renders_non_tradeable_assets_instead_of_dropping_them():
    """Der Kern des Bugs: ein Asset ohne handelbares Signal muss trotzdem
    erscheinen -- mit Einschaetzung, nur ohne Handelsempfehlung."""
    html = _section_commodities_crypto([
        _cc("BTC-USD", direction="none", tradeable=False,
            summary="Seitwaerts, kein klares Setup."),
    ])
    assert "Keine Daten" not in html
    assert "BTC-USD" in html
    assert "Seitwaerts, kein klares Setup." in html


def test_commodities_section_suppresses_tp_sl_for_non_tradeable_assets():
    """TP/SL sind eine Handelsempfehlung -- bei einer Enthaltung waeren sie
    eine Aussage, die die Analyse gerade NICHT getroffen hat."""
    html = _section_commodities_crypto([
        _cc("BTC-USD", direction="none", tradeable=False),
    ])
    assert "2420" not in html and "2360" not in html


def test_commodities_section_keeps_tp_sl_for_tradeable_assets():
    html = _section_commodities_crypto([_cc("GC=F", tradeable=True)])
    assert "2420" in html and "2360" in html


def test_commodities_section_shows_the_summary_column():
    """Das summary-Feld liefert der v3-Prompt laengst -- es wurde nur nie
    gerendert. Genau das sind die 'Einschaetzungen' in der Mail."""
    html = _section_commodities_crypto([_cc("GC=F", summary="Zinsen stuetzen.")])
    assert "Zinsen stuetzen." in html


def test_commodities_section_still_says_keine_daten_only_when_truly_empty():
    assert "Keine Daten" in _section_commodities_crypto([])
