"""Phase 4a: Daily portfolio check.

For every open prediction <= config.MAX_HOLD_DAYS trading days old, decide HALTEN /
SCHLIESSEN / ANPASSEN given the current snapshot, trend, and policy context. Writes one
position_recommendations row per call. Output is rendered as the FIRST
section of the daily e-mail (spec §3 CFD-Kurzfristfokus). Per-position
failures are caught — a single broken call must not abort the loop.

Seit Sprint 3B / Plan 2 (B.5) laeuft der Check OHNE web_search und nach Phase 4:
Input ist die fertige Phase-3-Analyse plus die Original-These aus der DB. Das spart
die Recherchekosten, behaelt aber Urteilsvermoegen und Begruendungstext fuer die Mail.
"""
import json
import logging
import sqlite3
from pathlib import Path

import config
from src import db
from src.cost_tracker import CostTracker
from src.utils import call_claude, extract_json_blob

log = logging.getLogger("shares_future.portfolio_check")

# v2 seit 2026-08-06: v1 verlangte weiterhin web_search und >= 2 Quell-Domains,
# obwohl B.5 den Aufruf auf tools=[] gestellt hat. Das Modell konnte die Vorgabe
# nur durch Erfinden erfuellen — und `reason` steht als erste Sektion in der
# Tagesmail. v1 bleibt als Beleg dessen liegen, was vorher lief (Regel 10).
SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "portfolio_check_v2.txt").read_text()

# HALTEN/SCHLIESSEN/ANPASSEN — strukturiert, Haiku reicht. Aus config gelesen
# statt hart kodiert (2026-08-20): ein hart kodierter String greift beim naechsten
# Modellwechsel still daneben, weil er nicht mitwandert. Genau das war bei
# broad_scan der Fall, wo Test-Fixture und Produktionsmodell auseinanderliefen.
MODEL = config.CLAUDE_MODEL_HAIKU
MAX_TOKENS = 2048
MAX_HOLD_DAYS = config.MAX_HOLD_DAYS
VALID_ACTIONS = {"HALTEN", "SCHLIESSEN", "ANPASSEN"}


class PortfolioCheckError(RuntimeError):
    """Per-position portfolio-check call produced unparseable or invalid output."""


def _build_user_message(
    prediction: sqlite3.Row,
    current_snapshot: dict,
    trend_context: dict,
    policy_context: dict,
) -> str:
    """Serializes the original prediction, current snapshot, and trend/policy
    context into the user message sent to Claude for one portfolio check."""
    pred_dict = {k: prediction[k] for k in prediction.keys()}
    parts = [
        "ORIGINAL PREDICTION:", json.dumps(pred_dict, ensure_ascii=False, default=str),
        "\nCURRENT SNAPSHOT:", json.dumps(current_snapshot, ensure_ascii=False),
        "\nTREND CONTEXT:", json.dumps(trend_context, ensure_ascii=False),
        "\nPOLICY CONTEXT:", json.dumps(policy_context, ensure_ascii=False),
        "\nReturn the JSON object defined in your system prompt.",
    ]
    return "\n".join(parts)


def check_one_position(
    prediction: sqlite3.Row,
    current_snapshot: dict,
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> dict:
    """Run portfolio-check on ONE open position. Returns the parsed response
    dict including the {action, new_sl_price, new_tp_price, ...} fields.
    Raises PortfolioCheckError on unparseable or schematically-invalid output."""
    user_msg = _build_user_message(
        prediction=prediction, current_snapshot=current_snapshot,
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


def check_open_positions(
    conn,
    today: str,
    run_type: str,
    analyses_by_ticker: dict[str, dict],
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """Loop all open predictions <= config.MAX_HOLD_DAYS days old, run portfolio_check
    per row, persist one position_recommendations row each. `analyses_by_ticker`
    enthaelt seit B.5 die fertigen Phase-3-Tiefenanalysen (nicht mehr die rohen
    Phase-1-Snapshots). Returns the list of parsed response dicts."""
    open_preds = db.load_open_predictions_within_max_age_days(
        conn, today=today, max_trading_days=MAX_HOLD_DAYS,
    )
    log.info(f"Phase 4a: {len(open_preds)} open positions to check")

    out: list[dict] = []
    for pred in open_preds:
        ticker = pred["ticker"]
        analysis = analyses_by_ticker.get(ticker)
        if analysis is None:
            log.warning(
                f"{ticker}: no current analysis, skipping portfolio_check for "
                f"prediction_id={pred['id']}"
            )
            continue

        try:
            parsed = check_one_position(
                prediction=pred, current_snapshot=analysis,
                trend_context=trend_context, policy_context=policy_context,
                cost_tracker=cost_tracker,
            )
        except PortfolioCheckError as e:
            log.warning(f"{ticker}: portfolio_check failed: {e}")
            continue

        parsed["ticker"]      = pred["ticker"]
        parsed["direction"]   = pred["direction"]
        parsed["entry_price"] = pred["entry_price"]

        db.save_position_recommendation(conn, {
            "date": today, "run_type": run_type,
            "prediction_id": pred["id"],
            "action": parsed["action"],
            "reason": parsed.get("reason", ""),
            "new_sl_price": parsed.get("new_sl_price"),
            "new_tp_price": parsed.get("new_tp_price"),
            "market_context_changed": bool(parsed.get("market_context_changed")),
        })
        out.append(parsed)

    log.info(
        f"Phase 4a done: {len(out)} recommendations written, "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return out
