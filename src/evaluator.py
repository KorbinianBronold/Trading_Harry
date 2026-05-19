"""Walk-Forward Evaluator.

Each open predictions row that is >= 1 trading-day old gets evaluated against the
post-prediction OHLC bars. Returns the exit reason and atomically writes both the
outcomes row and the prediction status via db.update_outcome_close().

Trading-day precision is intentionally approximated by calendar days: yfinance
returns weekday-only bars anyway, so iterating bars in order corresponds to
trading-day order. We cap at 3 bars (== 3 trading days)."""
import logging
import pandas as pd

from src import db
import config

log = logging.getLogger("shares_future.evaluator")

MAX_HOLD_DAYS = 3


def _walk_forward_hit(
    ohlc: pd.DataFrame, direction: str, tp: float, sl: float,
) -> tuple[str, float | None, int]:
    """Walk through up to MAX_HOLD_DAYS bars. Return (exit_reason, exit_price, day).
    If no hit and no full window, returns ('timeout', last_close, day_count)."""
    bars = ohlc.iloc[:MAX_HOLD_DAYS]
    for day_offset, (_, bar) in enumerate(bars.iterrows(), start=1):
        if direction == "long":
            hit_tp = bar["High"] >= tp
            hit_sl = bar["Low"]  <= sl
        else:
            hit_tp = bar["Low"]  <= tp
            hit_sl = bar["High"] >= sl

        if hit_tp and hit_sl:
            return "pessimistic_overlap", sl, day_offset
        if hit_sl:
            return "sl_hit", sl, day_offset
        if hit_tp:
            return "tp_hit", tp, day_offset

    if len(bars) == 0:
        return "data_missing", None, 0
    last_close = float(bars["Close"].iloc[-1])
    return "timeout", last_close, len(bars)


def _profit_loss_eur(
    entry: float, exit_price: float | None, direction: str,
) -> float | None:
    """Spec §1: 500 EUR Margin, 5:1 Hebel → 2500 EUR exposure → 1% move == 25 EUR."""
    if exit_price is None or entry in (None, 0):
        return None
    pct = (exit_price - entry) / entry * 100
    if direction == "short":
        pct = -pct
    eur = pct * config.CFD_MARGIN_EUR * config.CFD_LEVERAGE / 100
    return round(eur, 2)


def evaluate_open_predictions(
    conn,
    today: str,
    price_provider,
) -> int:
    """Walk-forward over every open, learnable prediction whose date < today.
    Returns the number of predictions evaluated (= newly-closed rows)."""
    rows = conn.execute(
        """SELECT * FROM predictions
           WHERE status='open' AND learnable=1 AND date < ?""",
        (today,),
    ).fetchall()
    log.info(f"Evaluator: {len(rows)} open predictions to evaluate")

    closed = 0
    for pred in rows:
        ticker = pred["ticker"]
        try:
            ohlc = price_provider.get_ohlc_after(
                ticker, start_date=pred["date"], end_date=today,
            )
        except Exception as e:
            log.warning(f"{ticker}: provider raised in evaluator: {e}")
            ohlc = None

        if ohlc is None or ohlc.empty:
            db.update_outcome_close(
                conn, prediction_id=pred["id"], exit_reason="data_missing",
                exit_price=None, days_to_close=0, closed_date=today,
                profit_loss_eur=None, correct_direction_eod=None,
                direction=pred["direction"],
            )
            closed += 1
            continue

        # Drop the prediction-day bar itself (already known at prediction time)
        post = ohlc[ohlc.index > pd.Timestamp(pred["date"])]
        reason, exit_price, day = _walk_forward_hit(
            post, direction=pred["direction"],
            tp=float(pred["tp_price"]), sl=float(pred["sl_price"]),
        )
        pl_eur = _profit_loss_eur(
            entry=float(pred["entry_price"]) if pred["entry_price"] else None,
            exit_price=exit_price, direction=pred["direction"],
        )
        correct = None
        if exit_price is not None:
            if pred["direction"] == "long":
                correct = exit_price > float(pred["entry_price"])
            else:
                correct = exit_price < float(pred["entry_price"])

        db.update_outcome_close(
            conn, prediction_id=pred["id"], exit_reason=reason,
            exit_price=exit_price, days_to_close=day,
            closed_date=today, profit_loss_eur=pl_eur,
            correct_direction_eod=correct,
            direction=pred["direction"],
        )
        closed += 1

    log.info(f"Evaluator done: {closed} predictions closed")
    return closed
