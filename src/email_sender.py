"""Phase 5: E-Mail rendering and delivery via Resend.

Error-Mail: send_error_email() is called by main.py on any unhandled exception.
It replaces the normal run email so the user is informed via the same channel.

Daily mail: a header -- abort banner (only after a cost-cap abort, C.47), the
"Was heute zaehlt" briefing box (first bullet = the run's result, C.47), ONE
Marktlage line (VIX with the active VIX rule, S&P 500 change, regime; C.30) and
ONE Rotation/Makro line from the morning market_context (C.47) -- followed by
five sections in this fixed order (a test pins the whole sequence):
  1. Portfolio-Empfehlungen (Phase 4a) — directly actionable on market open
  2. Aktien Top-10 Long + Top-10 Short
  3. Divergenz-Kandidaten (Spec 5.5) with the abstention/conflict counters
  4. Trends (dark cards)
  5. Commodities + Crypto

Plus a footer with the evaluated outcomes since the last trading day, skipped
tickers, run cost and the disclaimer. Sections the run never reached after a
cost-cap abort say so instead of "nothing found" (C.47 / F55). No Claude call
in this phase. Weekly mail is a shorter HTML body with the same delivery infra."""
import html
import logging
import re
from datetime import date as date_cls
from typing import Any

import requests

import config

log = logging.getLogger("shares_future.email_sender")

RESEND_ENDPOINT = "https://api.resend.com/emails"


class EmailSendError(RuntimeError):
    """Delivery failed (non-2xx or transport error). Caller should still treat
    the run as successful — the data is in the DB (s. B-10)."""


# ---------- Daily HTML ----------

_DISCLAIMER = (
    "Shares_Future ist ein automatisiertes Research- und Paper-Trading-System "
    "ohne automatische Orderausführung. Alle Analysen dienen ausschließlich zu "
    "Informationszwecken und stellen KEINE Anlageberatung dar. CFD-Handel kann "
    "zum Totalverlust führen. Keine Garantie für Prognosen."
)

# C.47 / F55: Phasenreihenfolge von main.run_pipeline() (die current_phase-
# Literale dort, in derselben Folge -- ein Test pinnt das). Damit weiss die
# Mail, welche Sektionen ein Kostendeckel-Abbruch gar nicht mehr erreicht hat.
PHASE_ORDER = (
    "trend_analysis", "market_context", "data_collection", "data_collection_cc",
    "open_positions", "sector_momentum", "broad_scan", "fundamentals_2b",
    "policy_monitor", "deep_analysis", "commodities_crypto", "ranking",
    "portfolio_check",
)

# Reihenfolge der Portfolio-Aktionen im Ergebnis-Bullet und im Betreff (F61):
# handlungsrelevant zuerst, Platzhalter zuletzt.
_ACTION_ORDER = ("SCHLIESSEN", "ANPASSEN", "HALTEN", "KEINE ANALYSE", "NICHT GEPRUEFT")

# Obergrenze der Summary in den Aktien-Tabellen: das Prompt-Maximum von
# deep_analysis_v2 ("max 600 chars, ends with the trade thesis"). Ein Schnitt
# darunter verlor die These (C.47 / F56).
_SUMMARY_MAX = 600


def _h(s: Any) -> str:
    """HTML-escapes `s`, returning an empty string for None."""
    if s is None:
        return ""
    return html.escape(str(s))


def _cut(s: Any, n: int) -> str:
    """Kuerzt `s` auf hoechstens `n` Zeichen an einer Wortgrenze und haengt '…'
    an; None -> ''. IMMER vor _h() aufrufen: _h(x)[:n] zerschnitt Entities, in
    der Mail stand dann 'Fed&#' oder '&am' als Text (C.47 / F56)."""
    if s is None:
        return ""
    s = str(s)
    if len(s) <= n:
        return s
    head = s[:n]
    space = head.rfind(" ")
    if space > n // 2:
        head = head[:space]
    return head.rstrip() + "…"


def generate_daily_briefing(trend_context: dict, policy_context: dict) -> list[str]:
    """Returns 4-6 bullet strings for the 'Was heute zaehlt' box -- rein
    deterministisch aus Phase 0 und dem Policy-Monitor, ohne Claude-Call. Das
    Ergebnis des Laufs (Positionen, Setups) kennt diese Funktion nicht; das
    stellt render_daily_html() per result_bullet() voran (C.47 / F61)."""
    bullets: list[str] = []
    strong = sorted(
        [t for t in (trend_context.get("trends") or []) if t.get("strength", 0) >= 7],
        key=lambda t: -t.get("strength", 0),
    )
    for t in strong[:2]:
        name = t.get("name") or t.get("trend_name", "Trend")
        bullets.append(f"{name}: {_cut(t.get('summary'), 100)}")
    if (policy_context.get("policy_risk_level") or "").lower() == "high":
        events = policy_context.get("events") or []
        if events:
            bullets.append(f"Policy-Risiko HOCH: {_cut(events[0].get('headline'), 140)}")
    for t in (trend_context.get("trends") or []):
        tickers = t.get("beneficiary_tickers") or []
        if tickers:
            # F61: mit Trendname und bis zu drei Tickern -- 'Trend-Beneficiary:
            # JPM' allein sagte nicht, welcher Trend gemeint ist.
            name = t.get("name") or t.get("trend_name", "Trend")
            bullets.append(f"Trend-Beneficiary ({name}): {', '.join(tickers[:3])}")
            break
    for t in (trend_context.get("trends") or []):
        cat = t.get("next_catalyst")
        # Positiv auf einen Termin pruefen statt negativ auf "TBD": das Modell
        # mischte Beschreibung und Platzhalter ("FOMC meeting September 2026 TBD",
        # 2026-09-02) und kann ebenso datumslos ohne TBD formulieren ("FOMC
        # meeting soon"). Der Bullet verspricht einen Katalysator-TERMIN -- also
        # kommt nur durch, was ein ISO-Datum traegt. Das deckt beide Fehlformen
        # mit einer Regel ab.
        if cat and re.search(r"\d{4}-\d{2}-\d{2}", cat):
            bullets.append(f"Naechster Katalysator: {_cut(cat, 80)}")
            break
    return bullets[:6]


def _book_summary(payload: dict) -> str:
    """Portfolio-Stand in einem Halbsatz: '1× SCHLIESSEN, 2× HALTEN', 'keine
    offene Position' oder 'Positionen nicht abrufbar' (C.47 / F61)."""
    if payload.get("positions_unavailable"):
        return "Positionen nicht abrufbar"
    recs = payload.get("portfolio_recs") or []
    if not recs:
        return "keine offene Position"
    counts: dict[str, int] = {}
    for r in recs:
        counts[r.get("action") or "?"] = counts.get(r.get("action") or "?", 0) + 1
    order = [a for a in _ACTION_ORDER if a in counts] + \
            [a for a in counts if a not in _ACTION_ORDER]
    return ", ".join(f"{counts[a]}× {a}" for a in order)


def result_bullet(payload: dict) -> str | None:
    """Erster Bullet der Briefing-Box (C.47 / F61): was der Lauf ergeben hat --
    Portfolio-Aktionen, Setups je Seite, Divergenz-Kandidaten. None bei einem
    Kostendeckel-Abbruch: dann sagt der Balken im Kopf, was fehlt."""
    if (payload.get("cost_summary") or {}).get("aborted_at_phase"):
        return None
    n_long = len(payload.get("top_long") or [])
    n_short = len(payload.get("top_short") or [])
    n_div = len(payload.get("divergence") or [])
    return (f"Heute: {_book_summary(payload)} · {n_long} Long / {n_short} Short "
            f"Setups · {n_div} Divergenz-Kandidaten")


def _not_run(payload: dict, phase: str) -> str | None:
    """Hinweistext, wenn `phase` beim Kostendeckel-Abbruch nicht mehr fertig
    wurde (C.47 / F55) -- sonst None. 'Keine Setups gefunden' nach einem
    Abbruch in Phase 3 las wie ein Ergebnis (dieselbe Klasse wie F53).
    Unbekannte Phasennamen gelten als gelaufen: lieber echte Daten zeigen als
    sie faelschlich fuer fehlend erklaeren."""
    aborted = (payload.get("cost_summary") or {}).get("aborted_at_phase")
    if not aborted or aborted not in PHASE_ORDER or phase not in PHASE_ORDER:
        return None
    if PHASE_ORDER.index(aborted) <= PHASE_ORDER.index(phase):
        return f"Nicht ausgeführt (Abbruch in Phase {aborted})."
    return None


def _section_abort(payload: dict) -> str:
    """Roter Balken im KOPF der Mail bei einem Kostendeckel-Abbruch (C.47 / F55).
    Bis dahin stand die Zeile im Fussteil -- der Leser sah oben NICHT GEPRUEFT
    und 'Keine Setups' und erfuhr erst ganz unten, warum."""
    aborted = (payload.get("cost_summary") or {}).get("aborted_at_phase")
    if not aborted:
        return ""
    return (
        '<p style="background:#c00;color:#fff;padding:10px;margin:0 0 16px 0;">'
        f'<b>⚠️ Lauf abgebrochen in Phase {_h(aborted)}</b> (Kostendeckel erreicht). '
        'Sektionen ab dieser Phase sind nicht ausgeführt; offene Positionen '
        'stehen als NICHT GEPRUEFT.</p>'
    )


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


def _move_pct(entry: Any, current: Any, direction: Any) -> float | None:
    """Kursbewegung seit dem Einstieg in Prozent, aus Sicht der Position
    (Short gespiegelt); None ohne beide Kurse."""
    try:
        e, c = float(entry), float(current)
    except (TypeError, ValueError):
        return None
    if e == 0:
        return None
    pct = (c - e) / e * 100.0
    return -pct if direction == "short" else pct


def _since(opened_at: Any, today: Any) -> str:
    """'seit 2026-09-11 (4 Tage)' aus dem Broker-Zeitstempel; '' wenn er fehlt
    oder nicht als Datum lesbar ist."""
    try:
        opened = date_cls.fromisoformat(str(opened_at)[:10])
    except (TypeError, ValueError):
        return ""
    out = f"seit {opened.isoformat()}"
    try:
        age = (date_cls.fromisoformat(str(today)) - opened).days
        out += f" ({age} Tage)"
    except (TypeError, ValueError):
        pass
    return out


def _position_cell(r: dict, today: Any) -> str:
    """Positionszelle (C.47 / F59): Richtung, Groesse, Entry -> Kurs mit
    Bewegung seit Entry, darunter Alter und die Broker-Levels. Bis dahin sah
    der Leser 'long @ 4344.75 (jetzt 4286.77)' -- ohne Stop, Alter, Groesse."""
    entry, cur = r.get("entry_price"), r.get("current_price")
    head = _h(r.get("direction"))
    if r.get("size") is not None:
        head += f' {_h(r["size"])}'
    head += f' @ {_h(entry)}'
    if cur is not None:
        head += f' → {_h(cur)}'
        move = _move_pct(entry, cur, r.get("direction"))
        if move is not None:
            head += f' ({move:+.2f} %)'
    levels = (f'SL {_h(r.get("sl_price")) or "—"} / '
              f'TP {_h(r.get("tp_price")) or "—"}')
    tail = " · ".join(x for x in (_since(r.get("opened_at"), today), levels) if x)
    return f'{head}<br><small>{tail}</small>'


def _section_portfolio(recs: list[dict], positions_unavailable: bool = False,
                       today: Any = None) -> str:
    """Renders the Phase-4a table (HALTEN/SCHLIESSEN/ANPASSEN/KEINE ANALYSE/
    NICHT GEPRUEFT) for the positions actually open at Capital.com (C.37), the
    first section of the daily and the 16:10 e-mail. `positions_unavailable` =
    the broker call failed: say so instead of rendering an empty section that
    reads like 'all closed'. NICHT GEPRUEFT rows come from portfolio_check.
    pending_rows() and survive a cost-cap abort before or during 4a (C.46 / F53).
    `today` (ISO) dient nur dem Positionsalter (C.47 / F59)."""
    if positions_unavailable:
        return ('<h2>Portfolio-Empfehlungen</h2>'
                '<p><i>Capital.com-Positionen nicht abrufbar, keine Empfehlungen.</i></p>')
    if not recs:
        return ('<h2>Portfolio-Empfehlungen</h2>'
                '<p><i>Keine offenen Positionen bei Capital.com.</i></p>')
    rows = []
    for r in recs:
        new_lvls = ""
        if r["action"] == "ANPASSEN":
            # C.46 / F51: ANPASSEN darf ein einzelnes Level nachziehen -- nur
            # gelieferte Levels rendern, nie 'neues TP None'. C.47 / F59: das
            # alte Level daneben, sonst ist der Nachzug nicht beurteilbar.
            parts = []
            if r.get("new_sl_price") is not None:
                parts.append(f'neuer SL {_h(r["new_sl_price"])} '
                             f'(vorher {_h(r.get("sl_price")) or "—"})')
            if r.get("new_tp_price") is not None:
                parts.append(f'neues TP {_h(r["new_tp_price"])} '
                             f'(vorher {_h(r.get("tp_price")) or "—"})')
            new_lvls = " · " + ", ".join(parts)
        label = r.get("ticker") or r.get("epic")
        rows.append(
            f'<tr><td><b>{_h(r["action"])}</b></td>'
            f'<td>{_h(label)}</td>'
            f'<td>{_position_cell(r, today)}</td>'
            f'<td>{_h(r.get("profit_loss"))}</td>'
            f'<td>{_h(r.get("reason", ""))}{new_lvls}</td></tr>'
        )
    return (
        '<h2>Portfolio-Empfehlungen</h2>'
        '<table border="1" cellpadding="4" cellspacing="0">'
        '<tr><th>Action</th><th>Ticker</th><th>Position</th><th>P&amp;L</th>'
        '<th>Begründung</th></tr>'
        + "".join(rows) + '</table>'
    )


# C.45 / F43: Kurzlabels fuer die im Ranking angeschlagenen Checks (Regelnamen
# aus src/signal_checks.py, die rank_and_persist() als _checks an jede Zeile
# haengt). Eine unbekannte Regel erscheint unter ihrem Namen, nie stumm.
CHECK_FLAG_LABELS = {
    "earnings_imminent":        "Earnings ≤2d",
    "stop_inside_noise":        "Stop im Rauschen",
    "tp_beyond_range":          "TP > Range",
    "sector_momentum":          "Sektor gegen Trade",
    "sector_momentum_partial":  "Sektor gegen Trade (1 Signal)",
    "sector_momentum_conflict": "Sektor uneinig",
    "sector_cluster":           "Klumpen",
    "vix_high_confidence_only": "VIX",
    "vix_no_new_longs":         "VIX (keine Longs)",
}


def _check_flags(a: dict) -> str:
    """Die angeschlagenen Checks einer Zeile als Labels, mit ' · ' getrennt."""
    return " · ".join(_h(CHECK_FLAG_LABELS.get(r, r)) for r in a.get("_checks") or [])


def _policy_flag(a: dict) -> str:
    """⚠️ bei policy_risk <= 4 (trade-relative Skala: tief = riskant, C.13)."""
    scores = a.get("scores") or {}
    return "⚠️" if (scores.get("policy_risk") or {}).get("value", 10) <= 4 else ""


def _flags(a: dict) -> str:
    """Flags-Zelle: weiche Checks des Laufs (C.45 / F43) plus Policy-⚠️ --
    seit C.47 / F64 in Top-10 UND Divergenz dieselbe Zelle."""
    return " · ".join(x for x in (_check_flags(a), _policy_flag(a)) if x)


def _level(price: Any, pct: Any) -> str:
    """'920.0 (4.55 %)' -- Level mit dem aus den Preisen abgeleiteten Abstand
    (C.45), auf den sich die Range-Flags beziehen (C.47 / F60)."""
    return f'{_h(price)} ({_h(pct)} %)' if pct is not None else _h(price)


_STOCK_TABLE_HEAD = (
    '<tr><th>#</th><th>Ticker</th><th>Sub-Sektor</th><th>Modell-Score</th>'
    '<th>P%</th><th>Conf.</th>'
    '<th>Rank-Score</th><th>Analysis-Strength</th><th>Technik</th>'
    '<th>Kurs (Snapshot)</th><th>TP</th><th>SL</th><th>R/R</th>'
    '<th>ATR/Tag</th><th>Range/Tag</th><th>Haltedauer</th>'
    '<th>Flags</th><th>Begründung</th></tr>'
)


def _row_for_setup(rank: int, a: dict) -> str:
    """Renders one <tr> for a single ranked stock setup. Das fruehere 🔥
    (trend_boost) stand in _to_prediction_row() hart auf None und ist weg."""
    return (
        f'<tr><td>{rank}</td><td>{_h(a["ticker"])}</td>'
        f'<td>{_h(a.get("_sub_sector"))}</td>'
        f'<td>{_h(a.get("total_score"))}</td>'
        f'<td>{_h(a.get("probability_pct"))}%</td>'
        f'<td>{_h(a.get("confidence"))}</td>'
        # I5 (Plan-3b-Gesamtreview): Score/P% sind NICHT der Sortierschluessel --
        # das ist rank_score = analysis_strength x tech_strength. Ohne diese
        # Spalten war die Top-10-Reihenfolge fuer einen Mail-Leser ohne
        # DB-Zugriff nicht nachvollziehbar; seit C.47 / F60 stehen beide
        # Faktoren daneben.
        f'<td>{_h(a.get("_rank_score"))}</td>'
        f'<td>{_h(a.get("_analysis_strength"))}</td>'
        f'<td>{_h(a.get("_tech_strength"))}</td>'
        f'<td>{_h(a.get("current_price"))}</td>'
        f'<td>{_level(a.get("tp_price"), a.get("tp_pct"))}</td>'
        f'<td>{_level(a.get("sl_price"), a.get("sl_pct"))}</td>'
        f'<td>{_h(a.get("rr_ratio"))}</td>'
        f'<td>{_h(a.get("atr_pct"))}</td>'
        f'<td>{_h(a.get("intraday_range_pct"))}</td>'
        f'<td>{_h(a.get("hold_days_recommended"))}</td>'
        f'<td>{_flags(a)}</td>'
        f'<td>{_h(_cut(a.get("summary", ""), _SUMMARY_MAX))}</td></tr>'
    )


def _section_stocks(top_long: list[dict], top_short: list[dict],
                    not_run: str | None = None) -> str:
    """Renders the Top-10 Long and Top-10 Short stock tables. `not_run` (C.47 /
    F55) ersetzt beide Tabellen durch den Abbruch-Hinweis."""
    if not_run:
        return f'<h2>Aktien Top-10</h2><p><i>{_h(not_run)}</i></p>'
    if not top_long and not top_short:
        return '<h2>Aktien Top-10</h2><p><i>Keine Setups gefunden.</i></p>'

    def _table(rows: list[dict], side: str) -> str:
        if not rows:
            return f'<p><i>Keine {side}-Setups.</i></p>'
        return ('<table border="1" cellpadding="4" cellspacing="0">' + _STOCK_TABLE_HEAD
                + "".join(_row_for_setup(i + 1, a) for i, a in enumerate(rows))
                + '</table>')

    return ('<h2>Aktien Top-10 Long</h2>' + _table(top_long, "Long")
            + '<h2>Aktien Top-10 Short</h2>' + _table(top_short, "Short"))


def _row_for_divergence(a: dict) -> str:
    """Renders one <tr> for a divergence candidate -- dieselben Kernspalten wie
    _row_for_setup(), aber ohne Rang (die Liste ist nicht nach Top-N sortiert
    im selben Sinn) und ohne rank_score (der ist per Konstruktion immer NULL
    fuer Divergenz-Kandidaten, s. Spec 5.4-Fussnote)."""
    return (
        f'<tr><td>{_h(a["ticker"])}</td><td>{_h(a["direction"])}</td>'
        f'<td>{_h(a.get("_analysis_strength"))}</td>'
        f'<td>{_h(a.get("current_price"))}</td>'
        f'<td>{_level(a.get("tp_price"), a.get("tp_pct"))}</td>'
        f'<td>{_level(a.get("sl_price"), a.get("sl_pct"))}</td>'
        f'<td>{_h(a.get("rr_ratio"))}</td>'
        f'<td>{_flags(a)}</td>'
        f'<td>{_h(_cut(a.get("summary", ""), _SUMMARY_MAX))}</td></tr>'
    )


def _section_divergence(divergence: list[dict], stats: dict,
                        not_run: str | None = None) -> str:
    """Spec 5.5: eigener, klar getrennter Abschnitt -- niemals vermischt mit
    den Top-10-Listen. Die Zaehler stehen daneben, damit 'nichts gefunden' von
    'vieles verworfen' unterscheidbar bleibt (der dominierende Fall laut dem
    Verifikationslauf vom 2026-08-17: 16 von 19 Analysen enthielten sich).
    `not_run` (C.47 / F55): Abbruch vor dem Ranking -- keine Zaehler, die
    waeren Nullen ohne Bedeutung."""
    if not_run:
        return f'<h2>Divergenz-Kandidaten</h2><p><i>{_h(not_run)}</i></p>'
    stats = stats or {}
    counters = (
        f'<p><i>Enthaltungen mit Technik-Richtung: '
        f'{_h(stats.get("tech_only_abstentions", 0))} · '
        f'Technik-Konflikte verworfen: {_h(stats.get("conflicts", 0))} · '
        f'Deckel-Ueberlauf: {_h(stats.get("overflow", 0))} · '
        f'Top-10-Ueberlauf: {_h(stats.get("core_overflow", 0))}</i></p>'
    )
    if not divergence:
        return ('<h2>Divergenz-Kandidaten</h2>'
                '<p><i>Keine.</i></p>' + counters)
    head = (
        '<tr><th>Ticker</th><th>Richtung</th><th>Analysis-Strength</th>'
        '<th>Kurs (Snapshot)</th><th>TP</th><th>SL</th><th>R/R</th><th>Flags</th>'
        '<th>Begründung</th></tr>'
    )
    rows = "".join(_row_for_divergence(a) for a in divergence)
    return (
        '<h2>Divergenz-Kandidaten</h2>'
        '<p><i>Starkes Signal in einer Dimension, noch keine Bestätigung in '
        'der anderen.</i></p>'
        '<table border="1" cellpadding="4" cellspacing="0">' + head + rows +
        '</table>' + counters
    )


def _section_trends(trends: list[dict]) -> str:
    """Renders the dark-card trends section (ein Karte je Megatrend aus Phase 0).
    Die Sektor-Rotation steht seit C.47 / F57 als Zeile im Kopf der Mail, aus
    dem persistierten market_context -- nicht hier."""
    if not trends:
        return '<h2>Trends</h2><p><i>Keine Trends erkannt.</i></p>'
    cards = []
    for t in trends:
        catalyst = t.get("next_catalyst")
        cards.append(
            '<div style="background:#1a1a1a;color:#eee;padding:12px;'
            'margin:6px 0;border-radius:8px;">'
            f'<h3 style="margin:0;color:#80c0ff;">{_h(t.get("name"))} '
            f'<small>(Stärke {_h(t.get("strength"))}, '
            f'{_h(t.get("duration_estimate"))})</small></h3>'
            f'<p>{_h(t.get("summary"))}</p>'
            f'<p><b>+</b> {_h(", ".join(t.get("beneficiary_tickers") or [])) or "—"}<br>'
            f'<b>−</b> {_h(", ".join(t.get("negative_tickers") or [])) or "—"}<br>'
            f'<b>Catalyst:</b> '
            f'{_h(catalyst) if catalyst and catalyst != "TBD" else "—"}</p>'
            '</div>'
        )
    return '<h2>Trends</h2>' + "".join(cards)


def _section_commodities_crypto(items: list[dict],
                                not_run: str | None = None) -> str:
    """Renders the commodities/crypto table plus the gold/silver-ratio and
    BTC-dominance footnote when available. `not_run` (C.47 / F55): Abbruch
    vor dem Ranking der Morgenmail."""
    if not_run:
        return f'<h2>Commodities + Crypto</h2><p><i>{_h(not_run)}</i></p>'
    if not items:
        return ('<h2>Commodities + Crypto</h2>'
                '<p><i>Keine Daten.</i></p>')
    rows = []
    for a in items:
        extra = a.get("extra") or {}
        # Ein Asset ohne handelbares Signal (Enthaltung oder an den Guardrails
        # gescheitert) erscheint TROTZDEM -- Spec 6 garantiert, dass alle sieben
        # immer analysiert werden, und die alte SPECIFICATION.md (Sektion 3)
        # nennt sie namentlich. Vorher fielen sie ganz raus und der Abschnitt
        # stand auf "Keine Daten.". Unterdrueckt werden nur TP/SL: die sind eine
        # Handelsempfehlung, und genau die hat die Analyse hier nicht gegeben.
        tradeable = a.get("tradeable", True)
        if tradeable:
            direction = _h(a.get("direction"))
            tp, sl = _h(a.get("tp_price")), _h(a.get("sl_price"))
            score = _h(a.get("total_score"))
            prob = f'{_h(a.get("probability_pct"))}%'
        else:
            direction = f'<i>{_h(a.get("direction") or "none")}</i>'
            tp = sl = score = prob = "&ndash;"
        rows.append(
            f'<tr><td>{_h(a["ticker"])}</td>'
            f'<td>{direction}</td>'
            f'<td>{score}</td>'
            f'<td>{prob}</td>'
            f'<td>{_h(a.get("current_price"))}</td>'
            f'<td>{tp}</td>'
            f'<td>{sl}</td>'
            f'<td>{_h(extra.get("fear_greed_value"))}</td>'
            f'<td>{_h(a.get("summary"))}</td></tr>'
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
        '<tr><th>Ticker</th><th>Dir</th><th>Modell-Score</th><th>P%</th>'
        '<th>Kurs</th><th>TP</th><th>SL</th><th>F&amp;G</th>'
        '<th>Einschätzung</th></tr>'
        + "".join(rows) + '</table>' + footer
    )


def _performance_line(y: dict) -> str:
    """Fussteil-Zeile mit den ausgewerteten Outcomes (C.47 / F58): Zeitraum
    (letzter Handelstag bis gestern, main._aggregate_yesterday_outcomes) und
    die Simulationsbasis, ohne die 'sim. P/L 25 EUR' nichts sagt. Leer ohne
    Outcome-Dict -- die 16:10-Mail traegt keins."""
    if not y:
        return ""
    since, until = y.get("since"), y.get("until")
    if since and until and since != until:
        label = f"Performance {_h(since)} – {_h(until)}"
    elif since or until:
        label = f"Performance {_h(since or until)}"
    else:
        label = "Performance"
    return (
        f'<p><b>{label}:</b> '
        f'Long {_h(y.get("long_correct"))}/{_h(y.get("long_total"))}, '
        f'Short {_h(y.get("short_correct"))}/{_h(y.get("short_total"))}, '
        f'sim. P/L {_h(y.get("total_pl_eur"))} EUR '
        f'<small>(je Signal {config.CFD_MARGIN_EUR} EUR Margin × '
        f'Hebel {config.CFD_LEVERAGE})</small></p>'
    )


def _section_footer(payload: dict) -> str:
    """Renders the e-mail footer: evaluated outcomes, skipped tickers, run cost,
    and the disclaimer. Der Abbruch-Hinweis steht seit C.47 / F55 im Kopf
    (_section_abort), nicht mehr hier."""
    cost = payload.get("cost_summary") or {}
    skipped = payload.get("skipped_tickers") or []
    return (
        '<hr>'
        + _performance_line(payload.get("yesterday_outcomes") or {})
        + f'<p><b>Übersprungene Aktien:</b> {_h(", ".join(skipped)) or "—"}</p>'
        '<p><b>Run-Kosten:</b> '
        f'{_h(cost.get("total_eur"))} EUR | '
        f'Cache-Hit-Rate: {_h(round((cost.get("cache_hit_rate") or 0) * 100, 1))}% | '
        f'Tokens: {_h(cost.get("input_tokens"))}/'
        f'{_h(cost.get("output_tokens"))} | '
        f'Web-Searches: {_h(cost.get("web_search_calls"))}</p>'
        f'<p><small><b>Disclaimer:</b> {_h(_DISCLAIMER)}</small></p>'
    )


def render_daily_html(payload: dict) -> str:
    """Build the daily e-mail body: Kopf (Abbruch-Balken, Briefing-Box mit
    Ergebnis-Bullet, Marktlage- und Rotationszeile), dann die Sektionen
    Portfolio -> Aktien Top-10 Long/Short -> Divergenz -> Trends ->
    Commodities + Crypto, dann der Fussteil. Ein Test pinnt die Sequenz."""
    bullets = [b for b in (result_bullet(payload), *(payload.get("briefing") or [])) if b]
    # Aktien, Divergenz und Commodities kommen alle aus Phase 4 (payload wird
    # in der Phase 'ranking' befuellt) -- ein Abbruch davor laesst sie leer.
    not_run = _not_run(payload, "ranking")
    return (
        '<html><body style="font-family:sans-serif;font-size:14px;">'
        f'<h1>Shares_Future — {_h(payload.get("date"))} '
        f'({_h(payload.get("run_type"))})</h1>'
        + _section_abort(payload)
        + _section_briefing(bullets)
        + _section_market_line(payload.get("market_context") or {})
        + _section_portfolio(payload.get("portfolio_recs") or [],
                             positions_unavailable=bool(payload.get("positions_unavailable")),
                             today=payload.get("date"))
        + _section_stocks(
            payload.get("top_long") or [], payload.get("top_short") or [],
            not_run=not_run,
        )
        + _section_divergence(
            payload.get("divergence") or [], payload.get("divergence_stats"),
            not_run=not_run,
        )
        + _section_trends(payload.get("trends") or [])
        + _section_commodities_crypto(payload.get("commodities_crypto") or [],
                                      not_run=not_run)
        + _section_footer(payload)
        + '</body></html>'
    )


# ---------- Weekly HTML ----------

def _weekly_revision_block(eff: dict | None) -> str:
    """B.9/Block 1: verdient der 16:10-Lauf seine Kosten? Liegt die Trefferquote
    der abgelehnten Signale unter der der bestaetigten, filtert er richtig.

    Seit Plan 3b (Spec 5.6) liefert load_revision_effectiveness() core und
    divergence getrennt -- ein Unterblock je Klasse, nie eine gemeinsame
    Zahl, damit eine schwache Divergenz-Trefferquote keine starke Core-Quote
    verwaessert oder umgekehrt."""
    if not eff:
        return ('<h2>16:10-Prüfung</h2>'
                '<p><i>Noch keine ausgewerteten Signale seit dem Umbau.</i></p>')

    def _line(label: str, g: dict) -> str:
        return (f'<tr><td>{label}</td><td>{g["correct"]}/{g["total"]}</td>'
                f'<td>{g["pl_eur"]} EUR</td></tr>')

    empty = {"total": 0, "correct": 0, "pl_eur": 0.0}
    blocks = []
    for cls, cls_label in (("core", "Core"), ("divergence", "Divergenz")):
        group = eff.get(cls, {})
        confirmed = group.get("confirmed", empty)
        rejected  = group.get("rejected", empty)
        unchecked = group.get("unchecked", empty)
        if not (confirmed["total"] or rejected["total"]):
            blocks.append(
                f'<h3>{cls_label}</h3>'
                '<p><i>Noch keine ausgewerteten Signale seit dem Umbau.</i></p>'
            )
            continue
        blocks.append(
            f'<h3>{cls_label}</h3>'
            '<table border="1" cellpadding="4" cellspacing="0">'
            '<tr><th>Gruppe</th><th>Treffer</th><th>P/L</th></tr>'
            + _line("um 16:10 bestätigt", confirmed)
            + _line("um 16:10 abgelehnt", rejected)
            + _line("nie geprüft", unchecked)
            + '</table>'
        )
    return (
        '<h2>16:10-Prüfung</h2>'
        + "".join(blocks)
        + f'<p><small>ausgewertet ab {_h(eff.get("since"))}</small></p>'
    )


def _weekly_performance_block(label: str, data: dict | None) -> str:
    """Performance-Zahlen und Trade-Liste EINER candidate_class (Spec 5.6).

    Zwei Bloecke nebeneinander, nie eine gemeinsame Summe -- dasselbe Muster wie
    in _weekly_revision_block(). Der Grund ist derselbe wie dort: der Split
    existiert, um core gegen divergence MESSEN zu koennen; eine vermischte Zahl
    beantwortet die Frage nicht mehr.

    ⚠️ Der Divergenz-Block muss sichtbar sein, auch wenn er leer ist. Seit Plan
    3b traegt der Core-Block nur noch die core-Zeilen — ohne den zweiten Block
    faellt das P/L eines Divergenz-Trades ersatzlos aus der Mail, und die
    kleinere Gesamtzahl liest sich wie eine ruhige Woche statt wie ein fehlender
    Zweig. Genau diese Verwechslung (kaputte Messung gegen kaputtes Verhalten)
    hat dieses Projekt schon zweimal Zeit gekostet."""
    if not data:
        return (f'<h3>{label}</h3>'
                '<p><i>Keine Daten für diese Gruppe.</i></p>')
    trades = data.get("trades") or []
    trades_rows = "".join(
        f'<tr><td>{_h(t["date"])}</td><td>{_h(t["ticker"])}</td>'
        f'<td>{_h(t["direction"])}</td>'
        f'<td>{_h(t.get("entry_price"))}</td>'
        f'<td>{_h(t.get("exit_price"))}</td>'
        f'<td>{_h(t.get("exit_reason"))}</td>'
        f'<td>{_h(t.get("profit_loss_eur"))}</td></tr>'
        for t in trades
    )
    table = (
        '<table border="1" cellpadding="4" cellspacing="0">'
        '<tr><th>Datum</th><th>Ticker</th><th>Dir</th>'
        '<th>Entry</th><th>Exit</th><th>Reason</th><th>P/L EUR</th></tr>'
        + trades_rows + '</table>'
    ) if trades_rows else '<p><i>Keine Trades.</i></p>'
    return (
        f'<h3>{label}</h3>'
        f'<p>Long: {_h(data.get("long_correct"))}/{_h(data.get("long_total"))} | '
        f'Ø P/L {_h(data.get("long_avg_pl"))} EUR</p>'
        f'<p>Short: {_h(data.get("short_correct"))}/{_h(data.get("short_total"))} | '
        f'Ø P/L {_h(data.get("short_avg_pl"))} EUR</p>'
        f'<p><b>Sim. P/L {label}:</b> {_h(data.get("total_pl_eur"))} EUR</p>'
        + table
    )


def _weekly_simple_table(title: str, headers: list[str],
                         rows: list[dict], keys: list[str]) -> str:
    """Generische Tabelle fuer die Weekly-Bloecke 2-4."""
    if not rows:
        return f'<h2>{title}</h2><p><i>Keine Einträge.</i></p>'
    head = "".join(f'<th>{h}</th>' for h in headers)
    body = "".join(
        '<tr>' + "".join(f'<td>{_h(r[k] if k in r.keys() else None)}</td>'
                         for k in keys) + '</tr>'
        for r in rows
    )
    return (f'<h2>{title}</h2>'
            '<table border="1" cellpadding="4" cellspacing="0">'
            f'<tr>{head}</tr>{body}</table>')


def render_weekly_html(payload: dict) -> str:
    """Reduced weekly e-mail. No learnings/prompt-optimizer in Sprint 1.

    ⚠️ Die Performance-Zahlen auf der obersten payload-Ebene sind seit Plan 3b
    NUR die core-Zeilen (main.load_recent_outcomes_aggregate). Die
    Divergenz-Kandidaten stehen in payload['divergence_summary'] und bekommen
    einen eigenen, gleich aufgebauten Block -- s. _weekly_performance_block()."""
    cost = payload.get("cost_summary") or {}
    return (
        '<html><body style="font-family:sans-serif;font-size:14px;">'
        f'<h1>Shares_Future Wochen-Summary — {_h(payload.get("week_label"))}</h1>'
        '<h2>Performance &amp; Trades</h2>'
        + _weekly_performance_block("Core (Technik bestätigt)", payload)
        + _weekly_performance_block(
            "Divergenz (nur Analyse-Signal)", payload.get("divergence_summary"))
        + f'<p><b>Run-Kosten Woche:</b> {_h(cost.get("total_eur"))} EUR</p>'
        + _weekly_revision_block(payload.get("revision_effectiveness"))
        + _weekly_simple_table(
            # ⚠️ candidate_class MUSS mitgerendert werden: seit Plan 3b
            # gruppiert db.load_revision_verdict_stats() nach
            # (revision_verdict, candidate_class) und liefert damit ZWEI Zeilen
            # je Urteil. Ohne die Spalte stehen zwei Zeilen "bestaetigt" mit
            # verschiedenen Zahlen untereinander und nichts unterscheidet sie.
            "Signal-Veränderungen",
            ["Urteil", "Klasse", "Anzahl", "ausgewertet", "Ø P/L"],
            payload.get("verdict_stats") or [],
            ["revision_verdict", "candidate_class", "n", "n_evaluated", "avg_pl"])
        + _weekly_simple_table(
            "Guardrails", ["Lauf", "Regel", "verworfen?", "Anzahl"],
            payload.get("guardrail_stats") or [],
            ["run_type", "rule", "enforced", "n"])
        + _weekly_simple_table(
            "Übersprungene Ticker", ["Ticker", "diese Woche", "Gründe",
                                     "gesamt", "inaktiv", "Retry ab"],
            payload.get("skipped_stats") or [],
            ["ticker", "n_week", "reasons", "skip_total", "inactive", "retry_after"])
        + (f'<h2>Sub-Sektor-Abdeckung</h2><p>'
           f'{_h((payload.get("sector_coverage") or {}).get("mapped"))} von '
           f'{_h((payload.get("sector_coverage") or {}).get("total"))} Tickern '
           f'gemappt ({_h((payload.get("sector_coverage") or {}).get("pct"))} %)</p>'
           if payload.get("sector_coverage") else "")
        + f'<p><small>{_h(_DISCLAIMER)}</small></p>'
        '</body></html>'
    )


# ---------- Trade-Proposals HTML (16:10) ----------

_VERDICT_LABEL = {
    "bestaetigt":    "✅ bestätigt",
    "geschwaecht":   "🔸 geschwächt",
    "unveraendert":  "➖ unverändert",
    "gedreht":       "🔁 gedreht",
    "verworfen":     "⛔ verworfen",
    "nicht_geprueft": "❔ nicht geprüft",
}


def _section_signal_changes(changes: list[dict]) -> str:
    """Kernsektion der 16:10-Mail: was ist seit der Morgenanalyse mit jedem Signal
    passiert (B.2/Schritt 5). Seit C.49 / F72 mit den Preisen: Entry 15:00,
    Eroeffnung, Kurs 16:10 mit Bewegung seit der Eroeffnung, TP/SL und das R/R
    gegen den 16:10-Kurs -- die einzige handlungsrelevante Mail zeigte bis
    dahin keine Levels. Zeilen ohne diese Schluessel (nicht_geprueft, alte
    Payloads) rendern '—'."""
    if not changes:
        return ('<h2>Signal-Prüfung 16:10</h2>'
                '<p><i>Keine offenen Morgensignale zu prüfen.</i></p>')

    def _num(v: Any) -> str:
        return _h(v) if v is not None else "—"

    rows = []
    for c in changes:
        before, after = c.get("probability_before"), c.get("probability_after")
        arrow = f'{_h(before)}% → {_h(after)}%' if after is not None else f'{_h(before)}% → —'
        window = "—"
        if c.get("entry_window_low") is not None and c.get("entry_window_high") is not None:
            window = f'{_h(c["entry_window_low"])} – {_h(c["entry_window_high"])}'
        move = c.get("move_since_open_pct")
        now_cell = _num(c.get("price_1610"))
        if move is not None:
            now_cell += f' ({float(move):+.2f} %)'
        levels = ("—" if c.get("tp_price") is None and c.get("sl_price") is None
                  else f'{_num(c.get("tp_price"))} / {_num(c.get("sl_price"))}')
        # title traegt den rohen Verdict-Slug (z.B. "bestaetigt"): das Label
        # daneben ist bewusst in korrektem Deutsch mit Umlaut, aber Tests und
        # spaetere Auswertungen sollen sich auf den stabilen Rohwert stuetzen
        # koennen, nicht auf die Emoji-Uebersetzung.
        rows.append(
            f'<tr><td>{_h(c["ticker"])}</td>'
            f'<td>{_h(c.get("direction"))}</td>'
            f'<td title="{_h(c.get("verdict"))}">'
            f'{_VERDICT_LABEL.get(c.get("verdict"), _h(c.get("verdict")))}</td>'
            f'<td>{arrow}</td>'
            f'<td>{_num(c.get("entry_premarket"))}</td>'
            f'<td>{_num(c.get("price_open"))}</td>'
            f'<td>{now_cell}</td>'
            f'<td>{levels}</td>'
            f'<td>{_num(c.get("rr_new"))}</td>'
            f'<td>{window}</td>'
            f'<td>{_h("; ".join(c.get("checks") or []))}</td>'
            f'<td>{_h(_cut(c.get("reason", ""), 200))}</td></tr>'
        )
    return (
        '<h2>Signal-Prüfung 16:10</h2>'
        '<table border="1" cellpadding="4" cellspacing="0">'
        '<tr><th>Ticker</th><th>Dir</th><th>Urteil</th><th>Wahrsch.</th>'
        '<th>Entry 15:00</th><th>Open</th><th>Kurs 16:10 (seit Open)</th>'
        '<th>TP / SL</th><th>R/R neu</th>'
        '<th>Entry-Fenster</th><th>Checks</th><th>Begründung</th></tr>'
        + "".join(rows) + '</table>'
    )


def _vix_rule(vix: Any) -> str:
    """Die aktive VIX-Regel als Zusatz zur Marktlage (C.47 / F57): ab 25 nur
    high confidence, ab 35 keine neuen Longs (B.3, config). Bis dahin sah der
    Leser die Zahl, nicht die Folge."""
    try:
        v = float(vix)
    except (TypeError, ValueError):
        return ""
    if v >= config.VIX_NO_NEW_LONGS:
        return f' (ab {config.VIX_NO_NEW_LONGS:g}: keine neuen Longs)'
    if v >= config.VIX_HIGH_CONFIDENCE_ONLY:
        return f' (ab {config.VIX_HIGH_CONFIDENCE_ONLY:g}: nur high confidence)'
    return ""


def _as_list(raw: Any) -> list[str]:
    """Sektorliste aus market_context: das Modell liefert einen kommaseparierten
    String (Prompt), die DB-Zeile ebenso, main._split_sectors() eine Liste --
    alle drei Formen landen hier als Liste."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [x.strip() for x in str(raw).split(",") if x.strip()]


def _rotation_line(ctx: dict) -> str:
    """Zweite Kopfzeile (C.47 / F57): Sektor-Rotation und Makro-Einzeiler aus
    dem morgendlichen market_context (GICS-Namen, persistiert). Beide steuern
    Phase 2/3/4a per Prompt, der Leser sah bis dahin keins von beiden."""
    into, out = _as_list(ctx.get("sector_rotation_in")), _as_list(ctx.get("sector_rotation_out"))
    macro = (ctx.get("macro_summary") or "").strip()
    parts = []
    if into or out:
        parts.append(f'<b>Rotation:</b> in {_h(", ".join(into)) or "—"} '
                     f'· out {_h(", ".join(out)) or "—"}')
    if macro:
        parts.append(f'<b>Makro:</b> {_h(macro)}')
    return f'<p style="margin:0 0 16px 0;">{" &middot; ".join(parts)}</p>' if parts else ""


def _market_line(ctx: dict) -> str:
    """'VIX 17.67 &middot; S&amp;P 500 -0.71 % &middot; Regime risk_off' -- nur
    belegte Werte, leerer String wenn keiner. Gemeinsamer Kern fuer Tages- und
    16:10-Mail. Die A/D-Ratio wird seit C.28 nicht mehr erhoben und hier bewusst
    ignoriert, auch wenn eine alte Payload den Schluessel noch traegt."""
    parts = []
    vix = ctx.get("vix_level")
    if vix is not None:
        parts.append(f'VIX {_h(vix)}{_vix_rule(vix)}')
    spx = ctx.get("sp500_change_pct")
    if spx is not None:
        try:
            parts.append(f'S&amp;P 500 {float(spx):+.2f} %')
        except (TypeError, ValueError):
            pass
    regime = ctx.get("market_regime")
    if regime:
        parts.append(f'Regime {_h(regime)}')
    return " &middot; ".join(parts)


def _section_market_warnings(ctx: dict) -> str:
    """Marktlage als eigene Sektion der 16:10-Mail. Um 16:10 traegt der Kontext
    nur den VIX (vix_only_context, C.28) -- die Zeile zeigt, was da ist."""
    line = _market_line(ctx)
    return f'<h2>Marktlage</h2><p>{line}</p>' if line else ""


def _section_market_line(ctx: dict) -> str:
    """Marktlage als Zeile im KOPF der Tagesmail, direkt unter dem Briefing.
    Bis C.30 war sie dort unsichtbar, obwohl VIX und Regime harte Guardrails
    steuern. Bewusst keine <h2>-Sektion: Portfolio bleibt die erste Sektion
    (dokumentierte Invariante)."""
    line = _market_line(ctx)
    return ((f'<p style="margin:0 0 16px 0;"><b>Marktlage:</b> {line}</p>'
             if line else "") + _rotation_line(ctx))


def render_trade_proposals_html(payload: dict) -> str:
    """16:10-Mail. Portfolio bleibt die erste Sektion (dokumentierte Invariante).

    Die Ueberschrift heisst bewusst 'Nachpruefung', nicht 'Signal-Pruefung': das
    Wort 'Signal' steht sonst schon in der H1 -- noch vor der Portfolio-Sektion --
    und der Test auf die Invariante sucht naiv per str.index() nach dem ersten
    Auftreten von 'Signal'. Der Sektionstitel weiter unten heisst weiterhin
    'Signal-Pruefung 16:10'."""
    return (
        '<html><body style="font-family:sans-serif;font-size:14px;">'
        f'<h1>Shares_Future — {_h(payload.get("date"))} (16:10 Nachprüfung)</h1>'
        + _section_abort(payload)
        + _section_briefing(payload.get("briefing") or [])
        + _section_portfolio(payload.get("portfolio_recs") or [],
                             positions_unavailable=bool(payload.get("positions_unavailable")),
                             today=payload.get("date"))   # C.50 / F76: Positionsalter
        + _section_signal_changes(payload.get("signal_changes") or [])
        + _section_commodities_crypto(payload.get("commodities_crypto") or [])
        + _section_market_warnings(payload.get("market_context") or {})
        + _section_footer(payload)
        + '</body></html>'
    )


def send_trade_proposals_email(
    payload: dict, api_key: str, email_from: str, email_to: str,
) -> None:
    """Rendert und versendet die 16:10-Mail ueber Resend."""
    changes = payload.get("signal_changes") or []
    confirmed = sum(1 for c in changes if c.get("verdict") == "bestaetigt")
    subject = (f"[Shares_Future] {payload.get('date')} trade_proposals — "
               f"{confirmed}/{len(changes)} bestätigt")
    _send(api_key, email_from, email_to, subject, render_trade_proposals_html(payload))


# ---------- final_close-Mail (C.17) ----------

_EXIT_REASON_LABEL = {
    "tp_hit": "✅ TP", "sl_hit": "❌ SL",
    "pessimistic_overlap": "❌ SL (TP+SL selber Tag)",
    "timeout": "⏱ Timeout", "data_missing": "⚠️ Fehlende Daten",
}


def render_final_close_html(payload: dict) -> str:
    """final_close-Mail (C.17): eine Zeile je heute ausgewerteter Prediction --
    Entry/Exit-Kurs, Ergebnis (TP/SL/Timeout/Fehlende Daten) und, falls
    vorhanden, das 16:10-Urteil (bestaetigt/geschwaecht/unveraendert/gedreht/
    verworfen). Predictions ohne 16:10-Pruefung zeigen eine leere Zelle."""
    rows = payload.get("rows") or []
    if not rows:
        return (
            '<html><body style="font-family:sans-serif;font-size:14px;">'
            f'<h1>Shares_Future — {_h(payload.get("date"))} (final_close)</h1>'
            '<p><i>Keine Predictions heute ausgewertet.</i></p>'
            '</body></html>'
        )

    trs = []
    for r in rows:
        ergebnis = _EXIT_REASON_LABEL.get(r.get("exit_reason"), _h(r.get("exit_reason")))
        cde = r.get("correct_direction_eod")
        korrekt = "—" if cde is None else ("Ja" if cde else "Nein")
        pl = r.get("profit_loss_eur")
        pl_str = "—" if pl is None else f'{pl:.2f}'
        trs.append(
            f'<tr><td>{_h(r.get("ticker"))}</td>'
            f'<td>{_h(r.get("direction"))}</td>'
            f'<td>{_h(r.get("revision_verdict") or "—")}</td>'
            f'<td>{_h(r.get("entry_price"))}</td>'
            f'<td>{_h(r.get("price_after_eod"))}</td>'
            f'<td>{ergebnis}</td>'
            f'<td>{korrekt}</td>'
            f'<td>{pl_str}</td></tr>'
        )
    return (
        '<html><body style="font-family:sans-serif;font-size:14px;">'
        f'<h1>Shares_Future — {_h(payload.get("date"))} (final_close)</h1>'
        '<table border="1" cellpadding="4" cellspacing="0">'
        '<tr><th>Ticker</th><th>Richtung</th><th>16:10-Urteil</th>'
        '<th>Entry</th><th>Exit</th><th>Ergebnis</th>'
        '<th>Richtung korrekt (EOD)</th><th>P&amp;L (EUR)</th></tr>'
        + "".join(trs) + '</table>'
        '</body></html>'
    )


def send_final_close_email(
    payload: dict, api_key: str, email_from: str, email_to: str,
) -> None:
    """Rendert und versendet die final_close-Mail ueber Resend. Wird IMMER
    verschickt, auch bei 0 Auswertungen (kein stiller Ausfall)."""
    n = len(payload.get("rows") or [])
    tp = sum(1 for r in (payload.get("rows") or []) if r.get("tp_hit"))
    sl = sum(1 for r in (payload.get("rows") or []) if r.get("sl_hit"))
    subject = (f"[Shares_Future] {payload.get('date')} final_close — "
               f"{n} ausgewertet ({tp}× TP, {sl}× SL)")
    _send(api_key, email_from, email_to, subject, render_final_close_html(payload))


# ---------- Delivery ----------

def send_daily_email(
    payload: dict, api_key: str, email_from: str, email_to: str,
) -> None:
    """Renders and sends the daily pre_market e-mail via Resend."""
    html_body = render_daily_html(payload)
    # C.47 / F55+F61: Abbruch und Portfolio-Aktionen gehoeren in den Betreff --
    # 'Top 0L / 0S' sah nach einem ruhigen Tag aus, auch bei Abbruch in Phase 3.
    aborted = (payload.get("cost_summary") or {}).get("aborted_at_phase")
    parts = ([f"ABBRUCH {aborted}"] if aborted else []) + [
        _book_summary(payload),
        f"Top {len(payload.get('top_long') or [])}L / "
        f"{len(payload.get('top_short') or [])}S",
    ]
    subject = (f"[Shares_Future] {payload.get('date')} {payload.get('run_type')} — "
               + " · ".join(parts))
    _send(api_key, email_from, email_to, subject, html_body)


def send_weekly_email(
    payload: dict, api_key: str, email_from: str, email_to: str,
) -> None:
    """Renders and sends the Sunday weekly-performance e-mail via Resend."""
    html_body = render_weekly_html(payload)
    subject = (
        f"[Shares_Future] {payload.get('week_label')} — Wochen-Summary"
    )
    _send(api_key, email_from, email_to, subject, html_body)


def _send(api_key: str, email_from: str, email_to: str,
          subject: str, html_body: str) -> str | None:
    """Shared delivery call used by every send_*_email(); raises EmailSendError
    on any non-2xx response or transport failure.

    Bewusst `requests` und kein Anbieter-SDK: es ist genau ein POST, requests ist
    ohnehin Abhaengigkeit (capital_provider), und Resend sitzt hinter Cloudflare,
    das die urllib-Signatur mit HTTP 403 / "error code: 1010" sperrt.

    Der Antwort-Body wird ausdruecklich mitgereicht. Ein abgelehnter Absender und
    ein ungueltiger Schluessel kommen beide als 4xx; ohne Klartext sucht man den
    Fehler an der falschen Stelle. Beim Vorgaenger-Anbieter ist genau daran ein
    Abend verlorengegangen: ein aufgebrauchtes Kontingent kam als 401 und sah wie
    ein kaputter Key aus (Hintergrund: PROJECT_STATUS, Abschnitt 3B-M)."""
    try:
        resp = requests.post(
            RESEND_ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": email_from,
                "to": [email_to],
                "subject": subject,
                "html": html_body,
            },
            timeout=30,
        )
    except Exception as e:
        raise EmailSendError(f"Resend request failed: {type(e).__name__}: {e}") from e

    if not (200 <= resp.status_code < 300):
        raise EmailSendError(
            f"Resend rejected the message (status {resp.status_code}): "
            f"{resp.text[:500]}"
        )

    try:
        message_id = resp.json().get("id")
    except Exception:
        message_id = None
    # Bewusst "accepted", nicht "sent": Resend nimmt die Mail mit 2xx an und
    # stellt danach asynchron zu. Ein Fehlschlag (z.B. unverifizierte
    # Absenderdomain) taucht erst spaeter unter GET /emails/{id} als
    # last_event="failed" auf. Die id wird zurueckgegeben, damit der Aufrufer die
    # echte Zustellung nachsehen kann — der Live-Test tut das.
    log.info(
        f"Resend accepted message (status={resp.status_code}"
        f"{f', id={message_id}' if message_id else ''})"
    )
    return message_id


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
    """Renders and sends the run-failure notification e-mail via Resend; called
    by main.py's top-level exception handler."""
    html_body = render_error_html(run_type, date, exc, traceback_text)
    subject = f"[Shares_Future] FEHLER {date} {run_type} — {type(exc).__name__}"
    _send(api_key, email_from, email_to, subject, html_body)
