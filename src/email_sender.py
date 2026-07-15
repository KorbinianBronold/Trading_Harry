"""Phase 5: E-Mail rendering and SendGrid delivery.

Error-Mail: send_error_email() is called by main.py on any unhandled exception.
It replaces the normal run email so the user is informed via the same channel.

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
    """HTML-escapes `s`, returning an empty string for None."""
    if s is None:
        return ""
    return html.escape(str(s))


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
    """Renders the dark 'Was heute zaehlt' briefing box, or '' if there are no bullets."""
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


def _section_portfolio(recs: list[dict]) -> str:
    """Renders the Phase-4a portfolio-recommendations table (HALTEN/SCHLIESSEN/
    ANPASSEN), the first section of the daily e-mail."""
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
    """Renders one <tr> for a single ranked stock setup, with trend/policy flag icons."""
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
    """Renders the Top-10 Long and Top-10 Short stock tables."""
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
    """Renders the dark-card trends section (megatrends + sector rotation)."""
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
    """Renders the commodities/crypto table plus the gold/silver-ratio and
    BTC-dominance footnote when available."""
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
    """Renders the e-mail footer: abort warning (if any), yesterday's performance,
    skipped tickers, run cost, and the disclaimer."""
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
        + _section_briefing(payload.get("briefing") or [])
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
    """Renders and sends the daily pre_market/midday e-mail via SendGrid."""
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
    """Renders and sends the Sunday weekly-performance e-mail via SendGrid."""
    html_body = render_weekly_html(payload)
    subject = (
        f"[Shares_Future] {payload.get('week_label')} — Wochen-Summary"
    )
    _send(api_key, email_from, email_to, subject, html_body)


def _send(api_key: str, email_from: str, email_to: str,
          subject: str, html_body: str) -> None:
    """Shared SendGrid delivery call used by every send_*_email(); raises
    EmailSendError on a non-2xx response."""
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


# ---------- Position-Check HTML ----------

def render_position_check_html(payload: dict) -> str:
    """Renders the position_check status-mail body: one row per open position
    with a status icon and note."""
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
    """Renders and sends the position_check status e-mail via SendGrid."""
    html_body = render_position_check_html(payload)
    checks = payload.get("checks") or []
    n_warn = sum(1 for c in checks if c.get("status") in ("near_sl", "signal_fallen"))
    subject = (
        f"[Shares_Future] {payload.get('date')} Position-Check — "
        f"{len(checks)} Pos, {n_warn} Warnung(en)"
    )
    _send(api_key, email_from, email_to, subject, html_body)


# ---------- Error Mail ----------

def render_error_html(
    run_type: str, date: str, exc: BaseException, traceback_text: str,
) -> str:
    """Renders the failure-notification e-mail body with the exception type,
    message, and full traceback."""
    exc_type = type(exc).__name__
    exc_msg = _h(str(exc))
    tb_html = _h(traceback_text).replace("\n", "<br>").replace(" ", "&nbsp;")
    return (
        '<html><body style="font-family:monospace;font-size:13px;">'
        f'<h1 style="color:#c00;">[Shares_Future] Run FAILED — {_h(date)} {_h(run_type)}</h1>'
        f'<p><b>Exception:</b> {_h(exc_type)}: {exc_msg}</p>'
        '<h2>Root Cause / Traceback</h2>'
        f'<pre style="background:#f5f5f5;padding:12px;border-radius:4px;">{tb_html}</pre>'
        f'<p><small>{_h(_DISCLAIMER)}</small></p>'
        '</body></html>'
    )


def send_error_email(
    run_type: str,
    date: str,
    exc: BaseException,
    traceback_text: str,
    api_key: str,
    email_from: str,
    email_to: str,
) -> None:
    """Renders and sends the run-failure notification e-mail via SendGrid; called
    by main.py's top-level exception handler."""
    html_body = render_error_html(run_type, date, exc, traceback_text)
    subject = f"[Shares_Future] FEHLER {date} {run_type} — {type(exc).__name__}"
    _send(api_key, email_from, email_to, subject, html_body)
