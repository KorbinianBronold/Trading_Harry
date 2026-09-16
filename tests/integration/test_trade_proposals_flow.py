"""End-to-End-Nachweis fuer den 16:10-Lauf (Sprint 3B / Plan 2).

Zwei Eigenschaften, die sich nur im Zusammenspiel zeigen:
  1. E4 — derselbe Check warnt um 15:00 und blockiert um 16:10
  2. E3 — nach der Abloesung existiert je Trade-Idee genau EIN offenes Signal
Beide wuerden bei einem Bruch keine Exception werfen, sondern still falsche
Kennzahlen liefern."""
from unittest.mock import MagicMock

from src import db


def _mock_16_10(mocker, price: float, verdict: dict):
    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.collect", return_value=([{"ticker": "AAPL", "price": price}], 0, {}))
    mocker.patch("main.collect_sector_momentum", return_value={})
    mocker.patch("main.check_open_positions", return_value=[])
    mocker.patch("main.send_trade_proposals_email")
    mocker.patch("main.revalidate_one", return_value=verdict)


def _morning_long(conn, prob=65):
    return db.save_prediction(conn, {
        "date": "2026-07-30", "run_type": "pre_market", "ticker": "AAPL",
        "direction": "long", "entry_price": 100.0, "tp_price": 106.0,
        "sl_price": 98.0, "probability_pct": prob, "confidence": "medium"})


def test_vix_blocks_at_1610_but_not_at_1500(tmp_db_path, mocker):
    """E4 in einem Durchlauf: derselbe VIX von 40 laesst das Morgensignal
    stehen und verwirft es um 16:10."""
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    pid = _morning_long(conn)
    conn.commit(); conn.close()

    mocker.patch("main.vix_only_context", return_value={"vix_level": 40.0})
    _mock_16_10(mocker, price=101.0,
                verdict={"verdict": "bestaetigt", "probability_pct": 71,
                         "reason": "ok"})
    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    row = conn.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row["revision_verdict"] == "verworfen"
    assert row["status"] == "open", "verworfene Signale bleiben auswertbar"
    n = conn.execute("SELECT COUNT(*) AS n FROM predictions").fetchone()["n"]
    assert n == 1, "ein hart verworfenes Signal erzeugt keine neue Zeile"
    rej = conn.execute(
        "SELECT rule, enforced FROM guardrail_rejects").fetchall()
    assert any(r["rule"] == "vix_no_new_longs" and r["enforced"] == 1 for r in rej)
    conn.close()


def test_exactly_one_open_signal_survives_the_revision(tmp_db_path, mocker):
    """E3: die Grundlage dafuer, dass kein Aggregat doppelt zaehlt."""
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    _morning_long(conn)
    conn.commit(); conn.close()

    mocker.patch("main.vix_only_context", return_value={"vix_level": 18.0})
    _mock_16_10(mocker, price=101.0,
                verdict={"verdict": "bestaetigt", "probability_pct": 71,
                         "reason": "ok"})
    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    assert conn.execute("SELECT COUNT(*) AS n FROM predictions").fetchone()["n"] == 2
    open_rows = db.load_open_predictions(conn)
    assert len(open_rows) == 1
    assert open_rows[0]["run_type"] == "trade_proposals"
    conn.close()


def test_evaluator_closes_exactly_one_outcome(tmp_db_path, mocker):
    """Der eigentliche Schaden waere hier sichtbar: zwei Outcomes fuer eine Idee
    verdoppeln Trefferquote und P&L in jeder Auswertung."""
    import pandas as pd
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    _morning_long(conn)
    conn.commit(); conn.close()

    mocker.patch("main.vix_only_context", return_value={"vix_level": 18.0})
    _mock_16_10(mocker, price=101.0,
                verdict={"verdict": "bestaetigt", "probability_pct": 71,
                         "reason": "ok"})
    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    n_before = conn.execute("SELECT COUNT(*) AS n FROM predictions").fetchone()["n"]
    assert n_before == 2, ("Vorbedingung: abgeloeste Morgenzeile UND ihre "
                           "Abloesung muessen existieren, sonst prueft der Rest "
                           "dieses Tests keinen Mechanismus")
    assert len(db.load_open_predictions(conn)) == 1, (
        "Vorbedingung: von den zwei Zeilen darf genau eine offen sein")

    # Das Fenster beginnt am Signal-Zeitpunkt des 16:10-Laufs, der Treffer liegt
    # also im Intraday-Fenster des Prognosetags selbst.
    provider = MagicMock()
    provider.get_intraday_ohlc.return_value = pd.DataFrame(
        {"Open": [101.0], "High": [107.0], "Low": [100.5], "Close": [106.5],
         "Volume": [0]},
        index=pd.to_datetime(["2026-07-30 14:10:00"]))
    from src.evaluator import evaluate_open_predictions
    closed = evaluate_open_predictions(conn=conn, today="2026-07-31",
                                       price_provider=provider)
    assert closed == 1
    out = conn.execute("SELECT exit_reason FROM outcomes").fetchall()
    assert len(out) == 1
    assert out[0]["exit_reason"] == "tp_hit", (
        "sonst wird dieser Test auf dem data_missing-Pfad gruen und prueft den "
        "E3-Mechanismus gegen einen degenerierten Fall")
    conn.close()


def test_1610_reuses_the_morning_policy_events_and_writes_none_of_its_own(tmp_db_path, mocker):
    """C.48 / F65 (Entscheidung 16.09.): der 16:10-Lauf hat keinen eigenen
    Policy-Call mehr. Die Morgen-Events (news_summaries, source='policy_monitor')
    bleiben die einzige Datenspur des Tages, die Revalidation sieht die
    Morgenlage aus market_context.policy_context_json."""
    import main
    morning = {
        "policy_risk_level": "medium", "summary": "x",
        "events": [{"headline": "Fed speaker turns hawkish", "detail": "",
                    "effective_date": None,
                    "beneficiary_tickers": ["GOLD"], "negative_tickers": []}]}
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    _morning_long(conn)
    db.save_policy_context(conn, "2026-07-30", "pre_market", morning)
    db.save_news_summaries(
        conn, main._news_summaries_from_policy(morning, "2026-07-30", "pre_market"))
    conn.commit(); conn.close()

    mocker.patch("main.vix_only_context", return_value={"vix_level": 18.0})
    _mock_16_10(mocker, price=101.0,
                verdict={"verdict": "bestaetigt", "probability_pct": 70,
                         "reason": "ok"})
    policy = mocker.patch("main.run_policy_monitor")
    main.run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    policy.assert_not_called()
    assert main.revalidate_one.call_args.kwargs["policy_context"] == morning
    conn = db.connect(str(tmp_db_path))
    rows = conn.execute(
        "SELECT ticker, derived_direction, run_type FROM news_summaries "
        "WHERE source='policy_monitor'").fetchall()
    conn.close()
    assert [tuple(r) for r in rows] == [("GOLD", "bullish", "pre_market")]
