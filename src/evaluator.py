"""Walk-Forward Evaluator.

Each open predictions row that is >= 1 trading-day old gets evaluated against the
post-prediction OHLC bars. Returns the exit reason and atomically writes both the
outcomes row and the prediction status via db.update_outcome_close().

Trading-day precision is intentionally approximated by calendar days: Capital.com
returns weekday-only bars, so iterating bars in order corresponds to trading-day
order. We cap at config.MAX_HOLD_DAYS bars (currently 5 trading days)."""
import logging
from datetime import date as date_cls, timedelta

import pandas as pd

from src import db
from src.signal_window import signal_time_utc, day_end_utc, collapse_to_daily_bar
import config

log = logging.getLogger("shares_future.evaluator")

# TODO(Sprint 3 Learning Module): Tagesgenaue TP/SL-Auswertung. Aktuell prueft
# _walk_forward_hit() nur, ob TP/SL irgendwo innerhalb der Tages-High/Low-Range
# lag (daher der "pessimistic_overlap"-Fallback, wenn beide im selben Tag treffen
# wuerden) — das ist keine echte Intraday-Praezision. Das Learning Modul soll
# echte Intraday-Bars (statt Tages-OHLC) nutzen, um TP/SL-Reihenfolge exakt zu
# bestimmen (ueber alle config.MAX_HOLD_DAYS Tage hinweg).
MAX_HOLD_DAYS = config.MAX_HOLD_DAYS

# Notbremse gegen Zombie-Predictions. Seit der Evaluator eine Prediction bei
# unvollstaendigem Fenster offen laesst, braucht es eine obere Schranke: liefert
# ein Ticker dauerhaft keine neuen Bars mehr -- stillgelegt per B.7, delistet,
# Datenausfall --, wuerde die Zeile sonst nie geschlossen und in jeder Auswertung
# als "noch laufend" mitgeschleppt. Grosszuegig gegenueber MAX_HOLD_DAYS = 5
# Handelstagen (Wochenenden, Feiertage, ein ausgefallener Lauf), aber endlich.
MAX_OPEN_CALENDAR_DAYS = 14


def _walk_forward_hit(
    ohlc: pd.DataFrame, direction: str, tp: float, sl: float,
) -> tuple[str, float | None, int]:
    """Walk through up to MAX_HOLD_DAYS bars. Return (exit_reason, exit_price, day).

    Ohne Treffer haengt der Ausgang davon ab, ob das Fenster abgelaufen ist:
      - weniger als MAX_HOLD_DAYS Bars -> 'pending', die Prediction ist noch
        nicht entschieden und bleibt offen
      - MAX_HOLD_DAYS Bars             -> 'timeout'
      - gar keine Bar                  -> 'data_missing'

    'pending' und 'data_missing' sind bewusst verschieden: "noch nicht
    entschieden" gegen "keine Daten vorhanden". Frueher lieferte diese Funktion
    in allen drei Faellen 'timeout', sobald in den VERFUEGBAREN Bars kein
    Treffer lag -- damit schloss jede Prediction beim ersten Auswertungslauf und
    MAX_HOLD_DAYS war nie in Kraft.

    exit_price traegt auch bei 'pending' schon den letzten Close, damit die
    Notbremse in evaluate_open_predictions ihn ohne zweite Berechnung
    verwenden kann. Ueber den Kalender entscheidet der Aufrufer: diese Funktion
    kennt nur Bars, nicht das Datum."""
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
    if len(bars) < MAX_HOLD_DAYS:
        return "pending", last_close, len(bars)
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


def _bar_sequence(conn, price_provider, pred) -> "pd.DataFrame | None":
    """Baut die Auswertungssequenz fuer eine Prediction.

    Element 1 ist die synthetische Tagesbar des SIGNALTAGS -- verdichtet aus den
    Minutenbars ab dem Signal-Zeitpunkt. Danach folgen die finalen Tagesbars aus
    price_history. Die Verdichtung ist noetig, damit _walk_forward_hit weiterhin
    je Bar einen Tag zaehlt: Minutenbars direkt in der Sequenz wuerden
    days_to_close zerstoeren, und daran haengt 3Ds hold_day.

    Fehlt das Intraday-Fenster (Feiertag, Handelsstopp, Abruffehler), beginnt die
    Sequenz bei D+1 -- die Prediction wird dadurch nicht schlechter behandelt."""
    frames = []
    start = signal_time_utc(pred["run_type"], pred["date"])
    if start is not None:
        try:
            intraday = price_provider.get_intraday_ohlc(
                pred["ticker"], start, day_end_utc(pred["date"]))
        except Exception as e:
            log.warning(f"{pred['ticker']}: Intraday-Abruf fehlgeschlagen: {e}")
            intraday = None
        bar = collapse_to_daily_bar(intraday)
        if bar is not None:
            frames.append(pd.DataFrame(
                [bar], index=pd.to_datetime([pred["date"]])))

    later = db.load_price_history_after(conn, pred["ticker"], pred["date"])
    if later is not None and not later.empty:
        frames.append(later)

    if not frames:
        return None
    return pd.concat(frames)


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
        # E7: evaluated_date ist der Handelstag, dessen Bar geschlossen hat --
        # nicht das Laufdatum. final_close laeuft am Folgetag; mit dem Laufdatum
        # faende _aggregate_yesterday_outcomes (WHERE evaluated_date = today - 1)
        # nichts mehr und die Fussleiste der Tagesmail zeigte stumm Nullen.
        evaluated_day = (date_cls.fromisoformat(today) - timedelta(days=1)).isoformat()

        ohlc = _bar_sequence(conn, price_provider, pred)

        if ohlc is None or ohlc.empty:
            db.update_outcome_close(
                conn, prediction_id=pred["id"], exit_reason="data_missing",
                exit_price=None, days_to_close=0, closed_date=evaluated_day,
                profit_loss_eur=None, correct_direction_eod=None,
                direction=pred["direction"],
            )
            closed += 1
            continue

        reason, exit_price, day = _walk_forward_hit(
            ohlc, direction=pred["direction"],
            tp=float(pred["tp_price"]), sl=float(pred["sl_price"]),
        )

        if reason == "pending":
            # Das Fenster laeuft noch. Die Prediction bleibt offen und wird beim
            # naechsten Lauf erneut geprueft — es entsteht KEINE outcomes-Zeile,
            # sonst zaehlte dieselbe Idee mehrfach. Nur die Notbremse schliesst
            # hier, damit ein verstummter Ticker keine Zombie-Zeile hinterlaesst.
            age_days = (date_cls.fromisoformat(today)
                        - date_cls.fromisoformat(pred["date"])).days
            if age_days <= MAX_OPEN_CALENDAR_DAYS:
                continue
            log.info(f"{ticker}: Fenster unvollstaendig, aber {age_days} Tage "
                     f"alt — wird als timeout geschlossen")
            reason = "timeout"

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
            closed_date=evaluated_day, profit_loss_eur=pl_eur,
            correct_direction_eod=correct,
            direction=pred["direction"],
        )
        closed += 1

    log.info(f"Evaluator done: {closed} predictions closed")
    return closed
