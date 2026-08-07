from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd
import pytest

from src import db
from src.evaluator import evaluate_open_predictions, _walk_forward_hit

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_ohlc_eval.csv"
ALL_OHLC = pd.read_csv(FIXTURE)


def _ohlc(ticker: str) -> pd.DataFrame:
    df = ALL_OHLC[ALL_OHLC["ticker"] == ticker].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").drop(columns=["ticker"])
    df.columns = [c.capitalize() for c in df.columns]
    return df


def _make_pred(conn, ticker: str, direction: str = "long",
               entry: float = 100.0, tp: float = 105.0, sl: float = 95.0,
               date: str = "2026-05-19", run_type: str = "close") -> int:
    return db.save_prediction(conn, {
        "date": date, "run_type": run_type, "asset_class": "stock",
        "ticker": ticker, "direction": direction,
        "entry_price": entry, "tp_price": tp, "tp_pct": 5.0,
        "sl_price": sl, "sl_pct": 5.0, "rr_ratio": 1.0,
        "total_score": 7.0, "probability_pct": 60, "confidence": "medium",
        "score_market_env": 7.0, "score_company": 7.0, "score_valuation": 6.0,
        "score_momentum": 7.0, "score_risk": 6.0, "score_sector": 7.0,
        "score_catalyst": 7.0, "score_policy": 6.0,
        "atr_pct": 2.0, "rsi_at_entry": 55.0, "volume_ratio": 1.0,
        "market_regime": "risk_on", "vix_at_prediction": 14.0,
        "sector": "Technology", "trend_boost": None,
        "earnings_warning": False, "summary": "test",
        "learnable": True, "hold_days_recommended": 2,
        "intraday_range_pct": 1.5,
    })


def _load_bars(conn, ticker: str) -> None:
    """Legt die Fixture-Bars als finale Tagesbars in price_history ab.

    Seit dem Umbau auf das Preismodell holt der Evaluator die Bars nicht mehr
    selbst beim Provider, sondern liest sie aus price_history -- der Live-Abruf
    lief zum close-Zeitpunkt und lieferte provisorische High/Low."""
    for _, r in _ohlc(ticker).iterrows():
        db.upsert_price_history(
            conn, ticker, r.name.strftime("%Y-%m-%d"),
            float(r["Open"]), float(r["High"]), float(r["Low"]),
            float(r["Close"]), 0)
    conn.commit()


def _provider(intraday: pd.DataFrame | None = None) -> MagicMock:
    """Provider-Doppel. Der Evaluator fragt ihn nur noch nach dem
    Intraday-Fenster des Signaltags; alles danach kommt aus price_history."""
    provider = MagicMock()
    provider.get_intraday_ohlc.return_value = intraday
    return provider


def _intraday_from_fixture(ticker: str, date: str) -> pd.DataFrame:
    """Die Fixture-Bar von `date` als Intraday-Fenster ab dem Signal-Zeitpunkt.

    Eine einzelne Zeile genuegt: collapse_to_daily_bar verdichtet ohnehin auf
    High=Max / Low=Min / Close=letzter."""
    row = _ohlc(ticker).loc[pd.Timestamp(date)]
    return pd.DataFrame(
        {"Open": [row["Open"]], "High": [row["High"]], "Low": [row["Low"]],
         "Close": [row["Close"]], "Volume": [0]},
        index=pd.to_datetime([f"{date} 14:10:00"]))


def test_long_tp_hit(in_memory_db):
    """days_to_close ist von 2 auf 1 gewandert, und das ist die korrekte neue
    Erwartung: das Fenster beginnt am Signal-Zeitpunkt, nicht am Tagesbeginn.
    Ein close-Lauf hat gar keinen Signal-Zeitpunkt am Prognosetag -- er
    entscheidet nach Handelsschluss --, also ist die Bar vom 2026-05-20 die
    erste, in der die Position ueberhaupt existiert."""
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "LONG_TP", direction="long",
                     entry=100.0, tp=105.0, sl=95.0)
    _load_bars(in_memory_db, "LONG_TP")
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=_provider(),
    )
    row = in_memory_db.execute(
        "SELECT status, closed_price FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_tp"
    assert row["closed_price"] == 105.0
    out = in_memory_db.execute(
        "SELECT exit_reason, tp_hit, days_to_close FROM outcomes "
        "WHERE prediction_id=?", (pid,),
    ).fetchone()
    assert out["exit_reason"] == "tp_hit"
    assert out["tp_hit"] == 1
    assert out["days_to_close"] == 1


def test_long_sl_hit(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "LONG_SL", direction="long",
                     entry=100.0, tp=105.0, sl=95.0)
    _load_bars(in_memory_db, "LONG_SL")
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=_provider(),
    )
    row = in_memory_db.execute(
        "SELECT status, closed_price FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_sl"
    out = in_memory_db.execute(
        "SELECT exit_reason FROM outcomes WHERE prediction_id=?", (pid,),
    ).fetchone()
    assert out["exit_reason"] == "sl_hit"


def test_short_tp_hit(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "SHORT_TP", direction="short",
                     entry=100.0, tp=95.0, sl=105.0)
    _load_bars(in_memory_db, "SHORT_TP")
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=_provider(),
    )
    row = in_memory_db.execute(
        "SELECT status FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_tp"


def test_short_sl_hit(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "SHORT_SL", direction="short",
                     entry=100.0, tp=95.0, sl=105.0)
    _load_bars(in_memory_db, "SHORT_SL")
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=_provider(),
    )
    row = in_memory_db.execute(
        "SELECT status FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_sl"


def test_incomplete_window_keeps_the_prediction_open(in_memory_db):
    """Frueher 'timeout nach drei Tagen'. Zwei Dinge haben sich seither
    verschoben, deshalb der neue Name:

    1. Die erste Fixture-Bar ist der Prognosetag selbst und faellt fuer einen
       close-Lauf aus dem Fenster -- es bleiben zwei Bars statt drei.
    2. Zwei Bars sind kein abgelaufenes Fenster. MAX_HOLD_DAYS = 5 war bis
       hierher nie in Kraft: der Evaluator schloss jede Prediction beim ersten
       Lauf als 'timeout', weil er nur die VERFUEGBAREN Bars ansah und nicht
       fragte, ob der Auswertungszeitraum ueberhaupt vorbei ist.

    Solange das Fenster laeuft, ist die Prediction schlicht noch nicht
    entschieden: keine outcomes-Zeile, kein geschlossener Status."""
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "TIMEOUT", direction="long",
                     entry=100.0, tp=110.0, sl=90.0)
    _load_bars(in_memory_db, "TIMEOUT")
    n = evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-22", price_provider=_provider(),
    )
    assert n == 0, "der Rueckgabewert zaehlt geschlossene Predictions"
    row = in_memory_db.execute(
        "SELECT status FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "open"
    assert in_memory_db.execute(
        "SELECT COUNT(*) AS n FROM outcomes WHERE prediction_id=?", (pid,),
    ).fetchone()["n"] == 0


def test_full_window_without_a_hit_times_out(in_memory_db):
    """Die Gegenprobe: sind MAX_HOLD_DAYS Bars da und keine reisst TP oder SL,
    ist die Prediction entschieden und schliesst als timeout."""
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "FLAT", direction="long",
                     entry=100.0, tp=110.0, sl=90.0)
    for d, close in [("2026-05-20", 100.1), ("2026-05-21", 100.2),
                     ("2026-05-22", 100.3), ("2026-05-25", 100.4),
                     ("2026-05-26", 100.5)]:
        db.upsert_price_history(in_memory_db, "FLAT", d,
                                100.0, 101.0, 99.0, close, 0)
    in_memory_db.commit()
    n = evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-27", price_provider=_provider(),
    )
    assert n == 1
    row = in_memory_db.execute(
        "SELECT status, closed_price FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_timeout"
    assert row["closed_price"] == 100.5
    out = in_memory_db.execute(
        "SELECT exit_reason, days_to_close FROM outcomes WHERE prediction_id=?",
        (pid,),
    ).fetchone()
    assert out["exit_reason"] == "timeout"
    assert out["days_to_close"] == 5


def test_stale_prediction_times_out_despite_an_incomplete_window(in_memory_db):
    """Notbremse gegen Zombie-Zeilen: liefert ein Ticker dauerhaft keine neuen
    Bars mehr -- stillgelegt per B.7, delistet, Datenausfall --, wuerde die
    Prediction ohne diese Grenze ewig offen bleiben und in jeder Auswertung als
    'noch laufend' mitgeschleppt."""
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "TIMEOUT", direction="long",
                     entry=100.0, tp=110.0, sl=90.0)
    _load_bars(in_memory_db, "TIMEOUT")
    n = evaluate_open_predictions(          # 20 Kalendertage nach dem Signal
        conn=in_memory_db, today="2026-06-08", price_provider=_provider(),
    )
    assert n == 1
    row = in_memory_db.execute(
        "SELECT status, closed_price FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_timeout"
    assert row["closed_price"] == 100.5
    out = in_memory_db.execute(
        "SELECT exit_reason, days_to_close FROM outcomes WHERE prediction_id=?",
        (pid,),
    ).fetchone()
    assert out["exit_reason"] == "timeout"
    assert out["days_to_close"] == 2, "die Notbremse zaehlt die Bars, die da sind"


def test_pessimistic_overlap_closes_at_sl(in_memory_db):
    """Die Regel 'TP und SL in derselben Bar -> pessimistisch SL' gilt
    unveraendert; nur die Bar, in der sie greift, ist eine andere. Die einzige
    Fixture-Bar ist der Prognosetag selbst, also braucht dieser Fall einen Lauf
    MIT Signal-Zeitpunkt (trade_proposals) und das Intraday-Fenster."""
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "OVERLAP", direction="long",
                     entry=100.0, tp=105.0, sl=95.0,
                     run_type="trade_proposals")
    provider = _provider(_intraday_from_fixture("OVERLAP", "2026-05-19"))
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=provider,
    )
    row = in_memory_db.execute(
        "SELECT status, closed_price FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_sl"
    assert row["closed_price"] == 95.0
    out = in_memory_db.execute(
        "SELECT exit_reason FROM outcomes WHERE prediction_id=?", (pid,),
    ).fetchone()
    assert out["exit_reason"] == "pessimistic_overlap"


def test_data_missing_closes_with_data_missing_reason(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "GONE", direction="long",
                     entry=100.0, tp=105.0, sl=95.0)
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-20", price_provider=_provider(),
    )
    row = in_memory_db.execute(
        "SELECT status FROM predictions WHERE id=?", (pid,),
    ).fetchone()
    assert row["status"] == "closed_data_missing"
    out = in_memory_db.execute(
        "SELECT exit_reason FROM outcomes WHERE prediction_id=?", (pid,),
    ).fetchone()
    assert out["exit_reason"] == "data_missing"


def test_evaluate_ignores_already_closed(in_memory_db):
    db.init_schema(in_memory_db)
    pid = _make_pred(in_memory_db, "LONG_TP", direction="long")
    db.close_prediction(in_memory_db, pid, status="closed_tp",
                        closed_date="2026-05-20", closed_price=105.0)
    _load_bars(in_memory_db, "LONG_TP")
    evaluate_open_predictions(
        conn=in_memory_db, today="2026-05-21", price_provider=_provider(),
    )
    out_count = in_memory_db.execute(
        "SELECT COUNT(*) AS n FROM outcomes WHERE prediction_id=?", (pid,),
    ).fetchone()["n"]
    assert out_count == 0


def test_walk_forward_helper_tp_first():
    """Helper covers the bar-by-bar comparison logic in isolation."""
    df = _ohlc("LONG_TP")
    reason, exit_price, day = _walk_forward_hit(
        df, direction="long", tp=105.0, sl=95.0,
    )
    assert reason == "tp_hit"
    assert exit_price == 105.0
    assert day == 2


def test_walk_forward_helper_honors_five_day_cap():
    """MAX_HOLD_DAYS now tracks config.MAX_HOLD_DAYS (5) instead of a hardcoded 3 —
    a hit on day 5 must still be detected, not cut off early."""
    from src.evaluator import MAX_HOLD_DAYS
    assert MAX_HOLD_DAYS == 5

    idx = pd.date_range("2026-06-01", periods=5, freq="B")
    df = pd.DataFrame({
        "High":  [101, 101, 101, 101, 111],
        "Low":   [99, 99, 99, 99, 100],
        "Close": [100, 100, 100, 100, 110],
    }, index=idx)

    reason, exit_price, day = _walk_forward_hit(df, direction="long", tp=110.0, sl=90.0)
    assert reason == "tp_hit"
    assert exit_price == 110.0
    assert day == 5


def test_window_starts_at_the_signal_not_at_midnight(in_memory_db, mocker):
    """Der alte Fehler war nicht 'Tag D zaehlt', sondern 'der falsche Teil von
    Tag D zaehlt': die Tagesbar laeuft ab 08:00 UTC, das Signal entsteht erst um
    10:10 ET. Ein TP-Treffer davor ist ein Artefakt.

    Hier reisst der TP nur VOR dem Signal -- danach bleibt der Kurs darunter.
    Das darf nicht als Treffer zaehlen.

    Seit der Hold-Days-Korrektur faellt die Antwort noch deutlicher aus: eine
    einzelne Bar ohne Treffer ist ein unvollstaendiges Fenster, die Prediction
    bleibt offen und es entsteht gar keine outcomes-Zeile. Die Zusicherung
    haelt beide Formen aus, weil es hier um den TP geht und nicht darum, wann
    geschlossen wird."""
    import pandas as pd
    from src import db
    from src.evaluator import evaluate_open_predictions
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-08-05", "run_type": "trade_proposals", "ticker": "AAPL",
        "direction": "long", "entry_price": 100.0,
        "tp_price": 110.0, "sl_price": 95.0})

    prov = mocker.MagicMock()
    # Fenster ab 14:10 UTC: Hoch nur 104 -- der TP bei 110 wird nicht erreicht.
    prov.get_intraday_ohlc.return_value = pd.DataFrame(
        {"Open": [100.0], "High": [104.0], "Low": [99.0],
         "Close": [103.0], "Volume": [500]},
        index=pd.to_datetime(["2026-08-05 14:10:00"]))

    evaluate_open_predictions(conn=in_memory_db, today="2026-08-06",
                              price_provider=prov)

    row = in_memory_db.execute(
        "SELECT * FROM outcomes WHERE prediction_id=?", (pid,)).fetchone()
    assert row is None or row["exit_reason"] != "tp_hit", (
        "ein TP-Treffer vor dem Signal darf nicht zaehlen")


def test_intraday_hit_closes_on_day_one(in_memory_db, mocker):
    """Und die Gegenprobe: reisst der TP NACH dem Signal am selben Tag, muss er
    mit days_to_close == 1 zaehlen. Genau daran haengt 3Ds hold_day=1.

    Seit der Hold-Days-Korrektur ist dieser Wert eindeutig: ein unvollstaendiges
    Fenster laeuft nicht mehr in einen timeout, days_to_close == 1 kann also nur
    noch 'am Signaltag getroffen' heissen."""
    import pandas as pd
    from src import db
    from src.evaluator import evaluate_open_predictions
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-08-05", "run_type": "trade_proposals", "ticker": "AAPL",
        "direction": "long", "entry_price": 100.0,
        "tp_price": 110.0, "sl_price": 95.0})

    prov = mocker.MagicMock()
    prov.get_intraday_ohlc.return_value = pd.DataFrame(
        {"Open": [100.0], "High": [112.0], "Low": [99.0],
         "Close": [111.0], "Volume": [500]},
        index=pd.to_datetime(["2026-08-05 14:10:00"]))

    evaluate_open_predictions(conn=in_memory_db, today="2026-08-06",
                              price_provider=prov)

    row = in_memory_db.execute(
        "SELECT * FROM outcomes WHERE prediction_id=?", (pid,)).fetchone()
    assert row["exit_reason"] == "tp_hit"
    assert row["days_to_close"] == 1, "Intraday-Treffer ist Tag 1"


def test_evaluated_date_is_the_trading_day_not_the_run_date(in_memory_db, mocker):
    """Sonst findet _aggregate_yesterday_outcomes (WHERE evaluated_date =
    today - 1) nichts mehr und die Fussleiste der Tagesmail zeigt stumm Nullen."""
    import pandas as pd
    from src import db
    from src.evaluator import evaluate_open_predictions
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-08-05", "run_type": "trade_proposals", "ticker": "AAPL",
        "direction": "long", "entry_price": 100.0,
        "tp_price": 110.0, "sl_price": 95.0})

    prov = mocker.MagicMock()
    prov.get_intraday_ohlc.return_value = pd.DataFrame(
        {"Open": [100.0], "High": [112.0], "Low": [99.0],
         "Close": [111.0], "Volume": [500]},
        index=pd.to_datetime(["2026-08-05 14:10:00"]))

    evaluate_open_predictions(conn=in_memory_db, today="2026-08-06",
                              price_provider=prov)

    row = in_memory_db.execute(
        "SELECT * FROM outcomes WHERE prediction_id=?", (pid,)).fetchone()
    assert row["evaluated_date"] == "2026-08-05", (
        "evaluated_date ist der Handelstag, dessen Bar geschlossen hat")


def test_missing_intraday_data_falls_back_to_the_next_day(in_memory_db, mocker):
    """Feiertag, Handelsstopp oder Abruffehler: ohne Fenster beginnt die
    Auswertung bei D+1, statt zu scheitern."""
    import pandas as pd
    from src import db
    from src.evaluator import evaluate_open_predictions
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-08-05", "run_type": "trade_proposals", "ticker": "AAPL",
        "direction": "long", "entry_price": 100.0,
        "tp_price": 110.0, "sl_price": 95.0})
    db.upsert_price_history(in_memory_db, "AAPL", "2026-08-06",
                            99.0, 115.0, 98.0, 114.0, 100)

    prov = mocker.MagicMock()
    prov.get_intraday_ohlc.return_value = None   # kein Fenster

    evaluate_open_predictions(conn=in_memory_db, today="2026-08-07",
                              price_provider=prov)

    row = in_memory_db.execute(
        "SELECT * FROM outcomes WHERE prediction_id=?", (pid,)).fetchone()
    assert row["exit_reason"] == "tp_hit", "der Tagesbar von D+1 traegt den Treffer"
