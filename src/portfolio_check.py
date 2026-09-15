"""Phase 4a: Portfolio-Check auf den bei Capital.com TATSAECHLICH offenen
Positionen (C.37, 2026-09-11).

Je Position ein Sonnet-5-Call (seit C.46; davor Haiku): HALTEN / SCHLIESSEN /
ANPASSEN aus Broker-Position (Richtung, Einstieg, TP/SL, P&L, Alter), einem
deterministischen Snapshot (Technik aus td, Technik-Signal aus dem Sidecar, die
Phase-3-Analyse falls vorhanden), Trend- und Policy-Kontext. Eine Zeile je Deal
in position_checks; das Ergebnis ist die ERSTE Sektion der Tagesmail (spec §3
CFD-Kurzfristfokus).

Bis C.37 lud der Check "offene Positionen" aus `predictions` (Papier-Vorschlaege
der letzten MAX_HOLD_DAYS Tage) und empfahl HALTEN/SCHLIESSEN fuer Positionen,
die es beim Broker nie gab (10.09.: 7 Empfehlungen bei 0 offenen Positionen).
Predictions und Positionen sind seither getrennte Welten: Predictions laufen
weiter durch die mehrtaegige Auswertung (Lernmodul), Positionen kommen nur von
Capital.com (main._open_broker_positions, Phase 1c). Dieses Modul liest
`predictions` nicht.

Bis C.46 bekam der Prompt um 15:00 das rohe Phase-3-Analyse-Dict und um 16:10
das rohe td -- zwei verschiedene Objekte unter demselben Prompt, ohne das
deterministische Technik-Signal, mit Schluesseln, die nie fuer einen Prompt
gedacht waren (is_premarket, sources_used; C.6-Klasse). build_snapshot() baut
seither in BEIDEN Laeufen denselben dreiteiligen Payload.

Positionen ohne jeden Snapshot (Fremdposition ausserhalb des Universums, Ticker
in Phase 1 uebersprungen) bekommen keinen Call, erscheinen aber als Zeile
"KEINE ANALYSE" in der Mail. `positions is None` (Abruf gescheitert) liefert
keine Empfehlungen -- die Mail zeigt den Ausfall. Bevor der Check laeuft (oder
wenn der Kostendeckel vorher zuschlaegt), stehen die Positionen als
"NICHT GEPRUEFT" in der Mail (pending_rows, C.46 / F53).

Seit Sprint 3B / Plan 2 (B.5) laeuft der Check OHNE web_search und nach Phase 4.
"""
import json
import logging
from pathlib import Path

import config
from src import db
from src.cost_tracker import CostTracker
from src.utils import call_claude_retry_on_truncation, extract_json_blob

log = logging.getLogger("shares_future.portfolio_check")

# v2 seit 2026-08-06: v1 verlangte weiterhin web_search und >= 2 Quell-Domains,
# obwohl B.5 den Aufruf auf tools=[] gestellt hat. Seit C.37 (Regel 10) direkt
# in der aktiven Datei auf Positionen statt Predictions umgestellt; seit C.46
# Datumsanker, dreiteiliger Snapshot, Horizont-Regel, ANPASSEN mit einem Level.
SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "portfolio_check_v2.txt").read_text()

# C.46 (Entscheidung Korbinian, 2026-09-15): Sonnet 5 statt Haiku 4.5 -- 4a ist
# die einzige Phase, deren Ausgabe eine Handlung an echtem Kapital ist; der
# Aufpreis liegt bei ~0,03 EUR je Position. Aus config gelesen, nie hart
# kodiert (2026-08-20). Decke wie revalidation (Sonnet 5 denkt adaptiv, die
# Denk-Tokens teilen sich die Decke mit der Antwort, C.18); Kappung faengt
# call_claude_retry_on_truncation. Messlauf nach dem Wechsel: C.46.
MODEL = config.CLAUDE_MODEL_SONNET
MAX_TOKENS = 6144
VALID_ACTIONS = {"HALTEN", "SCHLIESSEN", "ANPASSEN"}
# Mail-Zeile fuer Positionen ohne Analyse -- kein Claude-Call, keine Persistierung.
NO_ANALYSIS = "KEINE ANALYSE"
# Mail-Zeile, solange der Check nicht gelaufen ist (C.46 / F53).
NOT_CHECKED = "NICHT GEPRUEFT"

# Felder der Broker-Position, die die Mail und die Persistierung brauchen.
_POSITION_FIELDS = (
    "deal_id", "epic", "ticker", "direction", "entry_price", "current_price",
    "tp_price", "sl_price", "size", "profit_loss", "opened_at",
)

# C.46 / F48: was aus td in den Prompt geht -- Technik und Termine, keine
# Fundamentals, kein data_quality, kein Sektor (die stehen in der Analyse bzw.
# steuern anderswo). Die Skala des Technik-Signals (0-4) steht im Prompt.
TECHNICAL_KEYS = (
    "price", "price_change_1d", "price_change_5d", "rsi_14", "rsi_trend",
    "macd_signal", "above_sma20", "above_sma50", "above_sma200", "bb_position",
    "atr_pct", "intraday_range_pct", "volume_ratio", "earnings_in_days",
)
# Was aus der Phase-3-Analyse in den Prompt geht: Urteil, Belege, Konsistenz --
# nicht die Quellenliste, nicht die Pipeline-Marker (is_premarket), nicht der
# Modell-Score (F36).
ANALYSIS_KEYS = (
    "direction", "confidence", "probability_pct", "summary",
    "signal_consistency_check", "scores",
)
# Nur mit Richtung sinnvoll (C.46 / F49): TP/SL einer Enthaltung sind
# Schema-Pflichtzahlen ohne Bedeutung und wurden als Meinung gelesen.
ANALYSIS_LEVEL_KEYS = ("tp_price", "sl_price", "rr_ratio")


class PortfolioCheckError(RuntimeError):
    """Per-position portfolio-check call produced unparseable or invalid output."""


def build_snapshot(
    td: dict | None, tech: dict | None, analysis: dict | None,
) -> dict:
    """Der dreiteilige 4a-Payload (C.46 / F48): "technicals" aus dem Phase-1-td,
    "technical_signal" aus dem Sidecar (Richtung, Staerke 0-4), "analysis" aus
    Phase 3 -- oder None, wo es den Teil nicht gibt (16:10 hat keine Phase 3).
    Baut NEUE Dicts: die Originale bleiben unberuehrt und kein fremder Schluessel
    erreicht den Prompt (C.6). TP/SL/R/R der Analyse nur bei long/short (F49)."""
    technicals = {k: td.get(k) for k in TECHNICAL_KEYS} if td else None
    signal = None
    if tech:
        signal = {"direction": tech.get("tech_direction"),
                  "strength": tech.get("tech_strength")}
    view = None
    if analysis:
        view = {k: analysis.get(k) for k in ANALYSIS_KEYS}
        if analysis.get("direction") in ("long", "short"):
            view.update({k: analysis.get(k) for k in ANALYSIS_LEVEL_KEYS})
    return {"technicals": technicals, "technical_signal": signal, "analysis": view}


def _build_user_message(
    position: dict,
    current_snapshot: dict,
    trend_context: dict,
    policy_context: dict,
    date: str,
    run_type: str,
) -> str:
    """Serialisiert Datumsanker (C.46 / F47), Broker-Position, den dreiteiligen
    Snapshot und Trend-/Policy-Kontext in die User-Nachricht fuer EINEN
    Portfolio-Check. Keine Prediction, keine Ursprungsthese (C.37)."""
    pos = {k: position.get(k) for k in _POSITION_FIELDS}
    parts = [
        f"Today is {date}. Run type: {run_type}.",
        "\nOPEN POSITION (Capital.com):", json.dumps(pos, ensure_ascii=False, default=str),
        "\nCURRENT SNAPSHOT:", json.dumps(current_snapshot, ensure_ascii=False, default=str),
        "\nTREND CONTEXT:", json.dumps(trend_context, ensure_ascii=False),
        "\nPOLICY CONTEXT:", json.dumps(policy_context, ensure_ascii=False),
        "\nReturn the JSON object defined in your system prompt.",
    ]
    return "\n".join(parts)


def _level_error(
    direction: str | None, current_price: float | None,
    new_sl: float | None, new_tp: float | None,
) -> str | None:
    """Prueft die Levels einer ANPASSEN-Empfehlung gegen den Kurs (C.46 / F51):
    ein Stop auf der Gewinnseite waere bei Ausfuehrung ein sofortiger Stop-out.
    Gibt den Grund zurueck, wenn die Levels ungueltig sind, sonst None."""
    if new_sl is None and new_tp is None:
        return "ANPASSEN ohne neues Level"
    if current_price is None or direction not in ("long", "short"):
        return None
    below, above = ("SL", "TP") if direction == "long" else ("TP", "SL")
    lo = new_sl if direction == "long" else new_tp
    hi = new_tp if direction == "long" else new_sl
    if lo is not None and lo >= current_price:
        return f"neues {below} {lo} nicht unter dem Kurs {current_price}"
    if hi is not None and hi <= current_price:
        return f"neues {above} {hi} nicht ueber dem Kurs {current_price}"
    return None


def check_one_position(
    position: dict,
    current_snapshot: dict,
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
    *,
    date: str,
    run_type: str,
) -> dict:
    """Portfolio-Check fuer EINE offene Capital.com-Position. Gibt das geparste
    Antwort-Dict ({action, reason, new_sl_price, new_tp_price, ...}) zurueck.
    PortfolioCheckError bei unparsebarer oder schematisch ungueltiger Antwort.

    Eine Kappung (stop_reason max_tokens) wird ueber call_claude_retry_on_truncation
    einmal mit doppelter Decke wiederholt, beide Versuche gebucht (C.46 / F52).
    ANPASSEN mit ungueltigen Levels wird auf HALTEN herabgestuft -- mit Hinweis
    in `reason`, damit die persistierte Zeile es zeigt (C.46 / F51)."""
    user_msg = _build_user_message(
        position=position, current_snapshot=current_snapshot,
        trend_context=trend_context, policy_context=policy_context,
        date=date, run_type=run_type,
    )
    result = call_claude_retry_on_truncation(
        model=MODEL, system=SYSTEM_PROMPT, user=user_msg,
        max_tokens=MAX_TOKENS, cost_tracker=cost_tracker, tools=[],
    )
    parsed = extract_json_blob(result.text, PortfolioCheckError)
    action = parsed.get("action")
    if action not in VALID_ACTIONS:
        raise PortfolioCheckError(
            f"Unknown action '{action}' (must be one of {sorted(VALID_ACTIONS)})"
        )
    if action == "ANPASSEN":
        err = _level_error(
            position.get("direction"), position.get("current_price"),
            parsed.get("new_sl_price"), parsed.get("new_tp_price"),
        )
        if err:
            log.warning(f"{position.get('ticker') or position.get('epic')}: "
                        f"ANPASSEN mit ungueltigen Levels ({err}) -- "
                        f"herabgestuft auf HALTEN")
            parsed = {
                **parsed, "action": "HALTEN",
                "reason": f"[Levels ungueltig: {err} -- herabgestuft auf HALTEN] "
                          f"{parsed.get('reason', '')}",
                "new_sl_price": None, "new_tp_price": None,
            }
    return parsed


def _row(position: dict, action: str, reason: str) -> dict:
    """Mail-Zeile ohne Claude-Ergebnis: Positionsfelder plus Aktion und Grund."""
    return {**{k: position.get(k) for k in _POSITION_FIELDS},
            "action": action, "reason": reason,
            "new_sl_price": None, "new_tp_price": None, "market_context_changed": None}


def _no_analysis_row(position: dict) -> dict:
    """Mail-Zeile fuer eine Position ohne Snapshot und Analyse -- sichtbar, aber
    ohne Empfehlung und ohne Claude-Call."""
    why = ("Fremdposition ausserhalb des Universums" if not position.get("ticker")
           else "kein Snapshot und keine Analyse fuer diesen Ticker")
    return _row(position, NO_ANALYSIS, why)


def pending_rows(positions: list[dict] | None) -> list[dict]:
    """Platzhalterzeilen je Position, solange der Check nicht gelaufen ist
    (C.46 / F53): main setzt sie direkt nach Phase 1c in den Payload, damit ein
    Abbruch in Phase 3/4/4a in der Mail nie wie 'keine Positionen' liest."""
    return [_row(p, NOT_CHECKED, "Portfolio-Check noch nicht gelaufen")
            for p in (positions or [])]


def check_open_positions(
    conn,
    today: str,
    run_type: str,
    positions: list[dict] | None,
    analyses_by_ticker: dict[str, dict],
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
    *,
    tds_by_ticker: dict[str, dict] | None = None,
    signal_by_ticker: dict[str, dict] | None = None,
    out: list[dict] | None = None,
) -> list[dict]:
    """Prueft jede uebergebene Capital.com-Position (main._open_broker_positions),
    persistiert je Deal eine position_checks-Zeile und gibt die Empfehlungen fuer
    die Mail zurueck (angereichert um Ticker, Richtung, Einstieg, Kurs, P&L).

    tds_by_ticker (Phase-1-Snapshots) und signal_by_ticker (Technik-Sidecar)
    liefern die deterministische Technik, analyses_by_ticker die Phase-3-Analyse
    (um 16:10 leer) -- build_snapshot() baut daraus den Payload (C.46 / F48).
    Ein Call findet statt, sobald td ODER Analyse vorliegt; ohne beides bleibt
    die Zeile KEINE ANALYSE.

    `out` gehoert dem Aufrufer (Spec 7.1, wie main._revalidate_all): die Liste
    wird in place mit Platzhaltern gefuellt und Zeile fuer Zeile ersetzt. Reisst
    der Kostendeckel mitten in der Schleife, stehen die fertigen Zeilen und die
    restlichen als NICHT GEPRUEFT in der Mail (C.46 / F53). Ein fehlgeschlagener
    Einzel-Call bleibt ebenfalls als NICHT GEPRUEFT sichtbar statt zu verschwinden.

    `positions is None` = Abruf gescheitert: keine Empfehlungen, kein Call.
    Liest `predictions` NICHT (C.37)."""
    tds_by_ticker = tds_by_ticker or {}
    signal_by_ticker = signal_by_ticker or {}
    if out is None:
        out = []
    out[:] = pending_rows(positions)
    if positions is None:
        log.warning("Phase 4a: Capital.com-Positionen nicht abrufbar -- keine Empfehlungen")
        return out
    log.info(f"Phase 4a: {len(positions)} offene Capital.com-Position(en) zu pruefen")
    for i, pos in enumerate(positions):
        ticker = pos.get("ticker")
        td = tds_by_ticker.get(ticker) if ticker else None
        analysis = analyses_by_ticker.get(ticker) if ticker else None
        if td is None and analysis is None:
            log.warning(
                f"Position {pos.get('epic')} (deal {pos.get('deal_id')}): "
                f"kein Snapshot, keine Analyse -- nur Mail-Zeile, kein Portfolio-Check"
            )
            out[i] = _no_analysis_row(pos)
            continue
        snapshot = build_snapshot(td, signal_by_ticker.get(ticker), analysis)
        try:
            parsed = check_one_position(
                position=pos, current_snapshot=snapshot,
                trend_context=trend_context, policy_context=policy_context,
                cost_tracker=cost_tracker, date=today, run_type=run_type,
            )
        except PortfolioCheckError as e:
            log.warning(f"{ticker}: portfolio_check failed: {e}")
            out[i] = _row(pos, NOT_CHECKED, f"Portfolio-Check fehlgeschlagen: {e}")
            continue
        rec = {**parsed, **{k: pos.get(k) for k in _POSITION_FIELDS}}
        db.save_position_check(conn, {
            **{k: pos.get(k) for k in _POSITION_FIELDS if k != "epic"},
            "date": today, "run_type": run_type,
            "action": parsed["action"],
            "reason": parsed.get("reason", ""),
            "new_sl_price": parsed.get("new_sl_price"),
            "new_tp_price": parsed.get("new_tp_price"),
            "market_context_changed": bool(parsed.get("market_context_changed")),
        })
        out[i] = rec

    log.info(
        f"Phase 4a done: {len(out)} Zeilen "
        f"({sum(1 for r in out if r['action'] in VALID_ACTIONS)} Empfehlungen), "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return out
