"""Phase 4a: Portfolio-Check auf den bei Capital.com TATSAECHLICH offenen
Positionen (C.37, 2026-09-11).

Je Position ein Haiku-Call: HALTEN / SCHLIESSEN / ANPASSEN aus Broker-Position
(Richtung, Einstieg, TP/SL, P&L, Alter), aktueller Analyse bzw. Snapshot, Trend-
und Policy-Kontext. Eine Zeile je Deal in position_checks; das Ergebnis ist die
ERSTE Sektion der Tagesmail (spec §3 CFD-Kurzfristfokus).

Bis C.37 lud der Check "offene Positionen" aus `predictions` (Papier-Vorschlaege
der letzten MAX_HOLD_DAYS Tage) und empfahl HALTEN/SCHLIESSEN fuer Positionen,
die es beim Broker nie gab (10.09.: 7 Empfehlungen bei 0 offenen Positionen).
Predictions und Positionen sind seither getrennte Welten: Predictions laufen
weiter durch die mehrtaegige Auswertung (Lernmodul), Positionen kommen nur von
Capital.com (main._open_broker_positions, Phase 1c). Dieses Modul liest
`predictions` nicht.

Positionen ohne aktuelle Analyse (Fremdposition ausserhalb des Universums,
Ticker in Phase 3 uebersprungen) bekommen keinen Call, erscheinen aber als
Zeile "KEINE ANALYSE" in der Mail. `positions is None` (Abruf gescheitert)
liefert keine Empfehlungen -- die Mail zeigt den Ausfall.

Seit Sprint 3B / Plan 2 (B.5) laeuft der Check OHNE web_search und nach Phase 4:
Input ist die fertige Phase-3-Analyse (16:10: der Phase-1-Snapshot).
"""
import json
import logging
from pathlib import Path

import config
from src import db
from src.cost_tracker import CostTracker
from src.utils import call_claude, extract_json_blob

log = logging.getLogger("shares_future.portfolio_check")

# v2 seit 2026-08-06: v1 verlangte weiterhin web_search und >= 2 Quell-Domains,
# obwohl B.5 den Aufruf auf tools=[] gestellt hat. Seit C.37 (Regel 10) direkt
# in der aktiven Datei auf Positionen statt Predictions umgestellt.
SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "portfolio_check_v2.txt").read_text()

# HALTEN/SCHLIESSEN/ANPASSEN — strukturiert, Haiku reicht. Aus config gelesen
# statt hart kodiert (2026-08-20): ein hart kodierter String greift beim naechsten
# Modellwechsel still daneben, weil er nicht mitwandert.
MODEL = config.CLAUDE_MODEL_HAIKU
MAX_TOKENS = 2048
VALID_ACTIONS = {"HALTEN", "SCHLIESSEN", "ANPASSEN"}
# Mail-Zeile fuer Positionen ohne Analyse -- kein Claude-Call, keine Persistierung.
NO_ANALYSIS = "KEINE ANALYSE"

# Felder der Broker-Position, die die Mail und die Persistierung brauchen.
_POSITION_FIELDS = (
    "deal_id", "epic", "ticker", "direction", "entry_price", "current_price",
    "tp_price", "sl_price", "size", "profit_loss", "opened_at",
)


class PortfolioCheckError(RuntimeError):
    """Per-position portfolio-check call produced unparseable or invalid output."""


def _build_user_message(
    position: dict,
    current_snapshot: dict,
    trend_context: dict,
    policy_context: dict,
) -> str:
    """Serialisiert Broker-Position, aktuellen Snapshot und Trend-/Policy-Kontext
    in die User-Nachricht fuer EINEN Portfolio-Check. Keine Prediction, keine
    Ursprungsthese (C.37)."""
    pos = {k: position.get(k) for k in _POSITION_FIELDS}
    parts = [
        "OPEN POSITION (Capital.com):", json.dumps(pos, ensure_ascii=False, default=str),
        "\nCURRENT SNAPSHOT:", json.dumps(current_snapshot, ensure_ascii=False),
        "\nTREND CONTEXT:", json.dumps(trend_context, ensure_ascii=False),
        "\nPOLICY CONTEXT:", json.dumps(policy_context, ensure_ascii=False),
        "\nReturn the JSON object defined in your system prompt.",
    ]
    return "\n".join(parts)


def check_one_position(
    position: dict,
    current_snapshot: dict,
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> dict:
    """Portfolio-Check fuer EINE offene Capital.com-Position. Gibt das geparste
    Antwort-Dict ({action, reason, new_sl_price, new_tp_price, ...}) zurueck.
    PortfolioCheckError bei unparsebarer oder schematisch ungueltiger Antwort."""
    user_msg = _build_user_message(
        position=position, current_snapshot=current_snapshot,
        trend_context=trend_context, policy_context=policy_context,
    )
    result = call_claude(
        model=MODEL, system=SYSTEM_PROMPT, user=user_msg,
        max_tokens=MAX_TOKENS, tools=[],
    )
    cost_tracker.add_from_result(result)
    parsed = extract_json_blob(result.text, PortfolioCheckError)
    action = parsed.get("action")
    if action not in VALID_ACTIONS:
        raise PortfolioCheckError(
            f"Unknown action '{action}' (must be one of {sorted(VALID_ACTIONS)})"
        )
    return parsed


def _no_analysis_row(position: dict) -> dict:
    """Mail-Zeile fuer eine Position ohne Analyse -- sichtbar, aber ohne
    Empfehlung und ohne Claude-Call."""
    why = ("Fremdposition ausserhalb des Universums" if not position.get("ticker")
           else "keine aktuelle Analyse fuer diesen Ticker")
    return {**{k: position.get(k) for k in _POSITION_FIELDS},
            "action": NO_ANALYSIS, "reason": why,
            "new_sl_price": None, "new_tp_price": None, "market_context_changed": None}


def check_open_positions(
    conn,
    today: str,
    run_type: str,
    positions: list[dict] | None,
    analyses_by_ticker: dict[str, dict],
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """Prueft jede uebergebene Capital.com-Position (main._open_broker_positions),
    persistiert je Deal eine position_checks-Zeile und gibt die Empfehlungen fuer
    die Mail zurueck (angereichert um Ticker, Richtung, Einstieg, Kurs, P&L).

    `positions is None` = Abruf gescheitert: keine Empfehlungen, kein Call.
    Positionen ohne Analyse werden als NO_ANALYSIS-Zeile zurueckgegeben.
    Liest `predictions` NICHT (C.37)."""
    if positions is None:
        log.warning("Phase 4a: Capital.com-Positionen nicht abrufbar -- keine Empfehlungen")
        return []
    log.info(f"Phase 4a: {len(positions)} offene Capital.com-Position(en) zu pruefen")
    out: list[dict] = []
    for pos in positions:
        ticker = pos.get("ticker")
        analysis = analyses_by_ticker.get(ticker) if ticker else None
        if analysis is None:
            log.warning(
                f"Position {pos.get('epic')} (deal {pos.get('deal_id')}): "
                f"keine Analyse -- nur Mail-Zeile, kein Portfolio-Check"
            )
            out.append(_no_analysis_row(pos))
            continue
        try:
            parsed = check_one_position(
                position=pos, current_snapshot=analysis,
                trend_context=trend_context, policy_context=policy_context,
                cost_tracker=cost_tracker,
            )
        except PortfolioCheckError as e:
            log.warning(f"{ticker}: portfolio_check failed: {e}")
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
        out.append(rec)

    log.info(
        f"Phase 4a done: {len(out)} Zeilen "
        f"({sum(1 for r in out if r['action'] != NO_ANALYSIS)} Empfehlungen), "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return out
