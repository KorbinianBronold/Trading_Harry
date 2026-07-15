"""Phase 4a: Daily portfolio check.

For every open prediction <= 3 trading days old, decide HALTEN / SCHLIESSEN /
ANPASSEN given the current snapshot, trend, and policy context. Writes one
position_recommendations row per call. Output is rendered as the FIRST
section of the daily e-mail (spec §3 CFD-Kurzfristfokus). Per-position
failures are caught — a single broken call must not abort the loop."""
import json
import logging
import sqlite3
from pathlib import Path

from src import db
from src.cost_tracker import CostTracker
from src.utils import call_claude, extract_json_blob, WEB_SEARCH_TOOL

log = logging.getLogger("shares_future.portfolio_check")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "portfolio_check_v1.txt").read_text()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048
MAX_HOLD_DAYS = 3
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
        max_tokens=MAX_TOKENS, tools=[WEB_SEARCH_TOOL],
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
    snapshots_by_ticker: dict[str, dict],
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """Loop all open <= 3-day-old predictions, run portfolio_check per row,
    persist one position_recommendations row each. Returns the list of parsed
    response dicts."""
    open_preds = db.load_open_predictions_within_max_age_days(
        conn, today=today, max_trading_days=MAX_HOLD_DAYS,
    )
    log.info(f"Phase 4a: {len(open_preds)} open positions to check")

    out: list[dict] = []
    for pred in open_preds:
        ticker = pred["ticker"]
        snapshot = snapshots_by_ticker.get(ticker)
        if snapshot is None:
            log.warning(
                f"{ticker}: no current snapshot, skipping portfolio_check for "
                f"prediction_id={pred['id']}"
            )
            continue

        try:
            parsed = check_one_position(
                prediction=pred, current_snapshot=snapshot,
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
