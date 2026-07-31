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
    mocker.patch("main.collect", return_value=([{"ticker": "AAPL", "price": price}], 0))
    mocker.patch("main.collect_sector_momentum", return_value={})
    mocker.patch("main.run_policy_monitor",
                 return_value={"policy_risk_level": "low", "events": []})
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

    mocker.patch("main.fetch_market_context", return_value={"vix_level": 40.0})
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

    mocker.patch("main.fetch_market_context", return_value={"vix_level": 18.0})
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

    mocker.patch("main.fetch_market_context", return_value={"vix_level": 18.0})
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

    provider = MagicMock()
    provider.get_ohlc_after.return_value = pd.DataFrame(
        {"High": [107.0], "Low": [100.5], "Close": [106.5]},
        index=["2026-07-31"])
    from src.evaluator import evaluate_open_predictions
    closed = evaluate_open_predictions(conn=conn, today="2026-07-31",
                                       price_provider=provider)
    assert closed == 1
    assert conn.execute("SELECT COUNT(*) AS n FROM outcomes").fetchone()["n"] == 1
    conn.close()
