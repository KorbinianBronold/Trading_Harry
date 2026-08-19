import argparse
from unittest.mock import patch, MagicMock
import pytest

import main
from main import (
    run_pipeline, run_weekly, parse_args, build_commodity_crypto_inputs,
)
import config


def test_parse_args_accepts_all_run_types():
    for rt in ["pre_market", "trade_proposals", "final_close", "weekly"]:
        ns = parse_args(["--run-type", rt])
        assert ns.run_type == rt


@pytest.mark.parametrize("removed", ["midday", "evaluate", "position_check", "close"])
def test_parse_args_rejects_removed_run_types(removed):
    """B.1: die drei Run-Types sind vollstaendig entfernt, keine Leichen."""
    with pytest.raises(SystemExit):
        parse_args(["--run-type", removed])


def test_main_dispatches_trade_proposals(mocker):
    mocker.patch("main._abort_on_thin_history")
    fn = mocker.patch("main.run_trade_proposals")
    from main import main as main_fn
    main_fn(["--run-type", "trade_proposals", "--date", "2026-07-30"])
    fn.assert_called_once()


def test_parse_args_rejects_unknown_run_type():
    with pytest.raises(SystemExit):
        parse_args(["--run-type", "noon"])


def test_build_commodity_crypto_inputs_combines_config_maps():
    inputs = build_commodity_crypto_inputs()
    tickers = {d["ticker"] for d in inputs}
    expected = set(config.COMMODITY_TICKERS.values()) | set(config.CRYPTO_TICKERS.values())
    assert tickers == expected


def _mock_all_other_phases(mocker) -> list[str]:
    """Legt alle Pipeline-Phasen AUSSER Ranking (`rank_and_persist`) und
    Portfolio-Check (`check_open_positions`) mit Fake-Rueckgabewerten still und
    protokolliert die Aufrufreihenfolge in der zurueckgegebenen Liste. Die
    beiden ausgesparten Phasen mockt jeder aufrufende Test selbst — ihre
    Reihenfolge zueinander ist genau das, was Sprint 3B / Plan 2 (B.5) hier
    prueft; ein zweiter `mocker.patch` auf dasselbe Ziel wuerde den zuerst
    gesetzten Fake sonst stillschweigend ueberschreiben (aus
    test_run_pipeline_calls_phases_in_order herausgezogen, Task 6)."""
    call_log: list[str] = []

    def make_mock(name: str, return_value):
        def _fn(*a, **kw):
            call_log.append(name)
            return return_value
        return _fn

    fake_trends = {"trends": [{"name": "x"}], "trend_summary": "ok"}
    fake_policy = {"policy_risk_level": "low", "events": []}
    fake_collect = ([{"ticker": "AAPL", "intraday_range_pct": 1.5, "price": 178.0}], 0, {})
    fake_broad_scan = [{"ticker": "AAPL", "news_strength": 2, "news_note": "x"}]
    fake_deep = [{"ticker": "AAPL", "direction": "long", "current_price": 178.0,
                  "tp_price": 184.0, "sl_price": 176.0, "rr_ratio": 3.0,
                  "total_score": 7.6, "probability_pct": 65, "confidence": "high",
                  "hold_days_recommended": 2, "intraday_range_pct": 1.5,
                  "summary": "ok", "sources_used": ["a.com", "b.com"],
                  "signal_consistency_check": "ok", "earnings_warning": False,
                  "scores": {dim: {"value": 7.0, "evidence": ["x", "y"]}
                             for dim in [
                                 "market_environment","company_quality","valuation",
                                 "momentum","risk","sector_trend","catalyst","policy_risk",
                             ]}}]
    fake_cc = []
    fake_market_ctx = {"vix_level": 18.0, "vix_source": "capital.com",
                       "advance_decline_ratio": 1.2, "market_regime": "risk_on",
                       "sector_rotation_in": None, "sector_rotation_out": None,
                       "macro_summary": None}

    mocker.patch("main.analyze_trends", side_effect=make_mock("trend", fake_trends))
    mocker.patch("main.collect", side_effect=make_mock("collect", fake_collect))
    mocker.patch("main.broad_scan_batch",
                 side_effect=make_mock("broad_scan", fake_broad_scan))
    mocker.patch("main.run_policy_monitor",
                 side_effect=make_mock("policy", fake_policy))
    mocker.patch("main.analyze_batches", side_effect=make_mock("deep", (fake_deep, [])))
    mocker.patch("main.analyze_commodities_and_crypto",
                 side_effect=make_mock("cc", fake_cc))
    mocker.patch("main.fetch_fear_greed", return_value={"value": 50, "label": "Neutral"})
    mocker.patch("main.send_daily_email", side_effect=make_mock("email", None))
    mocker.patch("main.FinnhubProvider")
    # Phase 0b muss mitgemockt werden, sonst geht der Test echt ans Netz:
    # fetch_market_context ruft Claude und Capital.com.
    mocker.patch("main.fetch_market_context",
                 side_effect=make_mock("market_context", fake_market_ctx))
    mocker.patch("main.CapitalComProvider")
    return call_log


def test_run_pipeline_calls_phases_in_order(mocker):
    """Smoke-mock every phase and assert the call order. Seit Sprint 3B / Plan 2
    (B.5) laeuft Phase 4 (Ranking) vor Phase 4a (Portfolio-Check), damit Letzterer
    auf den fertigen Phase-3-Analysen arbeiten kann statt auf Rohsnapshots."""
    call_log = _mock_all_other_phases(mocker)
    fake_ranking = {
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    }
    mocker.patch("main.rank_and_persist",
                 side_effect=lambda **kw: call_log.append("ranking") or fake_ranking)
    mocker.patch("main.check_open_positions",
                 side_effect=lambda **kw: call_log.append("portfolio") or [])

    run_pipeline(run_type="pre_market", date="2026-05-19", db_path=":memory:")

    assert call_log == [
        "trend", "market_context", "collect", "collect", "broad_scan", "policy",
        "deep", "cc", "ranking", "portfolio", "email",
    ]


def test_ranking_runs_before_portfolio_check(mocker):
    """B.5: Phase 4 vor Phase 4a. Phase 4a soll auf den fertigen
    Phase-3-Analysen arbeiten, nicht auf Rohsnapshots."""
    order: list[str] = []
    mocker.patch("main.rank_and_persist",
                 side_effect=lambda **kw: order.append("ranking") or
                 {"top_long": [], "top_short": [], "commodities_crypto": [],
                  "divergence": [], "divergence_stats": {
                      "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0}})
    mocker.patch("main.check_open_positions",
                 side_effect=lambda **kw: order.append("portfolio") or [])
    # uebrige Phasen wie in test_run_pipeline_calls_phases_in_order mocken
    _mock_all_other_phases(mocker)
    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-30", db_path=":memory:")
    assert order == ["ranking", "portfolio"]


# ---------- C.16: market_context-Backfill + news_summaries (2026-08-19) ----------


def test_run_pipeline_backfills_market_context_with_fear_greed_and_policy(
        mocker, tmp_db_path):
    """fear_greed_value (Phase 3b) und policy_risk_level (Phase 3) entstehen
    erst NACH save_market_context() in Phase 0b -- der Backfill muss sie auf
    dieselbe (date, run_type)-Zeile nachtragen."""
    _mock_all_other_phases(mocker)
    mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0}})
    mocker.patch("main.check_open_positions", return_value=[])

    run_pipeline(run_type="pre_market", date="2026-05-19", db_path=str(tmp_db_path))

    import sqlite3
    conn = sqlite3.connect(str(tmp_db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM market_context WHERE date='2026-05-19' "
        "AND run_type='pre_market'").fetchone()
    conn.close()
    assert row["fear_greed_value"] == 50          # aus fetch_fear_greed-Mock
    assert row["policy_risk_level"] == "low"       # aus run_policy_monitor-Mock
    assert row["vix_level"] == 18.0                # unveraendert aus Phase 0b


def test_run_pipeline_writes_news_summaries_from_broad_scan_and_deep_analysis(
        mocker, tmp_db_path):
    _mock_all_other_phases(mocker)
    mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0}})
    mocker.patch("main.check_open_positions", return_value=[])

    run_pipeline(run_type="pre_market", date="2026-05-19", db_path=str(tmp_db_path))

    import sqlite3
    conn = sqlite3.connect(str(tmp_db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT ticker, source, sentiment, market_impact FROM news_summaries "
        "WHERE ticker='AAPL' ORDER BY source").fetchall()
    conn.close()
    by_source = {r["source"]: r for r in rows}
    assert set(by_source) == {"broad_scan", "deep_analysis"}
    # broad_scan: news_strength=2 aus dem Mock -> "notable", kein Sentiment
    assert by_source["broad_scan"]["market_impact"] == "notable"
    assert by_source["broad_scan"]["sentiment"] is None
    # deep_analysis: direction="long" -> "bullish", confidence="high" durchgereicht
    assert by_source["deep_analysis"]["sentiment"] == "bullish"
    assert by_source["deep_analysis"]["market_impact"] == "high"


def test_run_pipeline_aborts_when_trend_fails(tmp_db_path):
    from src.trend_analyzer import TrendAnalyzerError
    with patch("main.analyze_trends", side_effect=TrendAnalyzerError("no trends")), \
         patch("main.send_daily_email") as mock_email, \
         patch("main.FinnhubProvider"):
        with pytest.raises(TrendAnalyzerError):
            run_pipeline(run_type="close", date="2026-05-19",
                         db_path=str(tmp_db_path))
    # No daily email is sent on Phase 0 failure (the alerting path is the
    # exception propagating — the GH Actions step turns red).
    mock_email.assert_not_called()


def test_run_pipeline_partial_email_when_cost_cap_hit(tmp_db_path):
    from src.cost_tracker import CostCapExceeded
    with patch("main.analyze_trends", return_value={"trends": [{"name": "x"}],
                                                     "trend_summary": "ok"}), \
         patch("main.collect", return_value=([], 0, {})), \
         patch("main.run_policy_monitor",
               side_effect=CostCapExceeded("cap hit")), \
         patch("main.send_daily_email") as mock_email, \
         patch("main.fetch_market_context", return_value={}), \
         patch("main.CapitalComProvider"), \
         patch("main.FinnhubProvider"):
        run_pipeline(run_type="close", date="2026-05-19", db_path=str(tmp_db_path))
    # Email IS sent with the partial payload + abort warning
    args = mock_email.call_args.kwargs
    assert args["payload"]["cost_summary"]["aborted_at_phase"] == "policy_monitor"



def test_run_weekly_calls_send_weekly_email(tmp_db_path):
    with patch("main.send_weekly_email") as mock_send, \
         patch("main._update_weekly_fundamentals") as mock_fundamentals, \
         patch("main.FinnhubProvider"), \
         patch("main.load_recent_outcomes_aggregate",
               return_value={"long_correct": 0, "long_total": 0,
                             "long_avg_pl": 0.0, "short_correct": 0,
                             "short_total": 0, "short_avg_pl": 0.0,
                             "total_pl_eur": 0.0, "trades": []}):
        run_weekly(date="2026-05-24", db_path=str(tmp_db_path))
    mock_send.assert_called_once()
    mock_fundamentals.assert_called_once()


# ---------- Sprint 3C / Plan 2, Task 12: Fundamentals/Earnings-Vorlauf ----------


def test_run_weekly_runs_the_fundamentals_prerun_before_the_aggregate(tmp_db_path):
    """Der Vorlauf muss VOR dem woechentlichen Aggregat laufen (Spec 18: er
    fuellt fundamentals_cache, das das Aggregat/die Mail nicht direkt liest,
    aber die Reihenfolge aus dem Plan ist bewusst -- Fundamentals zuerst)."""
    order = []
    with patch("main.send_weekly_email"), \
         patch("main._update_weekly_fundamentals",
               side_effect=lambda *a, **kw: order.append("fundamentals")), \
         patch("main.FinnhubProvider"), \
         patch("main.load_recent_outcomes_aggregate",
               side_effect=lambda *a, **kw: order.append("aggregate") or {
                   "long_correct": 0, "long_total": 0, "long_avg_pl": 0.0,
                   "short_correct": 0, "short_total": 0, "short_avg_pl": 0.0,
                   "total_pl_eur": 0.0, "trades": []}):
        run_weekly(date="2026-05-24", db_path=str(tmp_db_path))
    assert order == ["fundamentals", "aggregate"]


def test_final_close_evaluates_open_predictions(tmp_db_path, mocker):
    """Die Gegenseite derselben Invariante — und ohne sie waere die Entfernung
    aus run_close() ungesichert: faellt der Aufruf auch hier weg, schreibt
    NIEMAND mehr outcomes-Zeilen, und zwar lautlos. Kein Test hat das bisher
    gepinnt (nur die Bar-Fortschreibung war abgedeckt)."""
    import pandas as pd
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn); conn.close()

    prov = MagicMock()
    prov._source_name = "capital.com"
    prov.get_ohlc_after.side_effect = lambda t, *a, **k: pd.DataFrame(
        {"Open": [99.0], "High": [102.0], "Low": [98.0],
         "Close": [100.0], "Volume": [1000]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-08-05")]))
    mocker.patch("main.CapitalComProvider", return_value=prov)
    ev = mocker.patch("main.evaluate_open_predictions", return_value=2)
    mocker.patch("main.send_final_close_email")  # C.17: sonst blockiert das Netz-Fixture

    from main import run_final_close
    run_final_close(date="2026-08-06", db_path=str(tmp_db_path))
    ev.assert_called_once()


# ---------- C.17: final_close-Mail (2026-08-19) ----------


def test_run_final_close_sends_email_with_evaluated_outcomes(tmp_db_path, mocker):
    """evaluate_open_predictions() bleibt gemockt (wie oben) -- die outcomes-
    Zeile wird direkt geseedet, damit der neue Query-Aufruf etwas findet."""
    import pandas as pd
    from src import db
    conn = db.connect(str(tmp_db_path))
    db.init_schema(conn)
    pred_id = db.save_prediction(conn, {
        "date": "2026-08-04", "run_type": "pre_market", "ticker": "AAPL",
        "direction": "long", "entry_price": 178.5, "tp_price": 182.0,
        "sl_price": 176.7,
    })
    conn.execute(
        """INSERT INTO outcomes
           (prediction_id, direction, evaluated_date, price_after_eod,
            correct_direction_eod, tp_hit, sl_hit, exit_reason, profit_loss_eur)
           VALUES (?, 'long', '2026-08-05', 182.0, 1, 1, 0, 'tp_hit', 35.0)""",
        (pred_id,),
    )
    conn.commit()
    conn.close()

    prov = MagicMock()
    prov._source_name = "capital.com"
    prov.get_ohlc_after.side_effect = lambda t, *a, **k: pd.DataFrame(
        {"Open": [99.0], "High": [102.0], "Low": [98.0],
         "Close": [100.0], "Volume": [1000]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-08-05")]))
    mocker.patch("main.CapitalComProvider", return_value=prov)
    mocker.patch("main.evaluate_open_predictions", return_value=1)
    send = mocker.patch("main.send_final_close_email")

    from main import run_final_close
    run_final_close(date="2026-08-06", db_path=str(tmp_db_path))

    send.assert_called_once()
    payload = send.call_args.kwargs["payload"]
    assert payload["date"] == "2026-08-06"
    assert [r["ticker"] for r in payload["rows"]] == ["AAPL"]


def test_run_final_close_sends_email_even_with_zero_evaluations(tmp_db_path, mocker):
    """Kein stiller Ausfall: die Mail geht auch raus, wenn nichts ausgewertet
    wurde (z.B. weil alle offenen Predictions noch im 5-Tage-Fenster sind)."""
    import pandas as pd
    prov = MagicMock()
    prov._source_name = "capital.com"
    prov.get_ohlc_after.side_effect = lambda t, *a, **k: pd.DataFrame(
        {"Open": [99.0], "High": [102.0], "Low": [98.0],
         "Close": [100.0], "Volume": [1000]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-08-05")]))
    mocker.patch("main.CapitalComProvider", return_value=prov)
    mocker.patch("main.evaluate_open_predictions", return_value=0)
    send = mocker.patch("main.send_final_close_email")

    from main import run_final_close
    run_final_close(date="2026-08-06", db_path=str(tmp_db_path))

    send.assert_called_once()
    assert send.call_args.kwargs["payload"]["rows"] == []


def test_prompts_contain_intraday_focus():
    from pathlib import Path
    prompt_dir = Path("prompts")
    for name in [
        "deep_analysis_v1.txt",
        "commodities_crypto_v1.txt",
        "portfolio_check_v1.txt",
    ]:
        text = (prompt_dir / name).read_text()
        assert "Intraday-Horizont" in text, f"{name} missing intraday focus paragraph"


from freezegun import freeze_time

def test_main_date_uses_berlin_timezone(tmp_db_path, mocker):
    """At 23:30 UTC on 2026-05-21, Berlin (CEST UTC+2) is 01:30 on 2026-05-22."""
    import importlib
    import main as m
    importlib.reload(m)
    # Vehikel ist seit Plan 2 trade_proposals statt evaluate, seit dem
    # Historien-Guard `close`, und seit dessen Entfernung (2026-08-18)
    # `final_close` — geprueft wird weiterhin die Timezone-Ableitung, nicht der
    # Run-Type. final_close braucht wie close keine Historie und laeuft deshalb
    # auch gegen die leere Test-DB bis zum Dispatch durch.
    mocker.patch.object(m, "run_final_close")
    with freeze_time("2026-05-21T23:30:00+00:00"):
        m.main(["--run-type", "final_close", "--db-path", str(tmp_db_path)])
        call_date = m.run_final_close.call_args[1]["date"]
    assert call_date == "2026-05-22", f"Expected Berlin date 2026-05-22, got {call_date}"




# ---------- Markt-Kontext in der Pipeline (Sprint 3B / Plan 1, Task 11) ----------


def _stub_pipeline(mocker) -> None:
    """Legt alle Phasen ausser dem Markt-Kontext still, damit die Tests unten
    nur dessen Verdrahtung pruefen."""
    mocker.patch("main.analyze_trends", return_value={"trends": []})
    mocker.patch("main.collect", return_value=([], 0, {}))
    mocker.patch("main.run_policy_monitor", return_value={})
    mocker.patch("main.analyze_batches", return_value=([], []))
    mocker.patch("main.analyze_commodities_and_crypto", return_value=[])
    mocker.patch("main.fetch_fear_greed", return_value={})
    mocker.patch("main.check_open_positions", return_value=[])
    mocker.patch("main.generate_daily_briefing", return_value=[])
    mocker.patch("main.send_daily_email")
    mocker.patch("main.CapitalComProvider", return_value=mocker.MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=mocker.MagicMock())


_CTX = {
    "vix_level": 23.4, "vix_source": "capital.com",
    "advance_decline_ratio": 0.8, "market_regime": "risk_off",
    "sector_rotation_in": "Utilities", "sector_rotation_out": "Technology",
    "macro_summary": "nervoes",
}


def test_pipeline_persists_market_context_and_passes_it_to_ranking(tmp_db_path, mocker):
    """Der Markt-Kontext landet in der DB und im Ranking — nicht mehr hardcoded None."""
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mock_rank = mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })

    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))

    passed = mock_rank.call_args.kwargs["market_context"]
    assert passed["vix_level"] == 23.4
    assert passed["market_regime"] == "risk_off"

    from src import db
    conn = db.connect(str(tmp_db_path))
    row = conn.execute(
        "SELECT * FROM market_context WHERE date='2026-07-27'").fetchone()
    assert row["vix_level"] == 23.4
    assert row["advance_decline_ratio"] == 0.8
    assert row["run_type"] == "pre_market"
    conn.close()


def test_pipeline_puts_market_context_into_the_mail_payload(tmp_db_path, mocker):
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })
    mock_mail = mocker.patch("main.send_daily_email")

    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))

    payload = mock_mail.call_args.kwargs["payload"]
    assert payload["market_context"]["market_regime"] == "risk_off"


def test_market_context_is_called_with_the_price_provider(tmp_db_path, mocker):
    """Ohne Provider faellt der VIX auf Claudes Schaetzwert zurueck."""
    _stub_pipeline(mocker)
    provider = mocker.MagicMock()
    mocker.patch("main.CapitalComProvider", return_value=provider)
    mock_ctx = mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })

    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))
    assert mock_ctx.call_args.kwargs["price_provider"] is provider


def test_pipeline_survives_market_context_failure(tmp_db_path, mocker):
    """Ein fehlgeschlagener Markt-Kontext-Call darf den Run nicht abbrechen."""
    from src.market_context import MarketContextError
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context",
                 side_effect=MarketContextError("no json"))
    mock_rank = mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })
    mock_mail = mocker.patch("main.send_daily_email")

    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))

    passed = mock_rank.call_args.kwargs["market_context"]
    assert passed["vix_level"] is None
    assert passed["market_regime"] is None
    mock_mail.assert_called_once()


def test_market_context_cost_cap_still_sends_mail(tmp_db_path, mocker):
    """CostCapExceeded darf NICHT vom MarketContextError-Handler geschluckt
    werden — Kosten-Abbruch beendet die Phasen, schickt aber trotzdem Mail."""
    from src.cost_tracker import CostCapExceeded
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context",
                 side_effect=CostCapExceeded("cap reached"))
    mock_rank = mocker.patch("main.rank_and_persist")
    mock_mail = mocker.patch("main.send_daily_email")

    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))

    mock_rank.assert_not_called()
    mock_mail.assert_called_once()


# ---------- B-05: echte Abbruch-Phase melden (Sprint 3B / Plan 1, Task 13) ----------


def test_cost_cap_abort_reports_the_actual_phase(tmp_db_path, mocker):
    """B-05: Bricht der Run in Phase 3 ab, darf nicht 'policy_monitor' gemeldet werden."""
    from src.cost_tracker import CostCapExceeded
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mocker.patch("main.analyze_batches", side_effect=CostCapExceeded("cap hit"))

    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))

    from src import db
    conn = db.connect(str(tmp_db_path))
    row = conn.execute(
        "SELECT aborted_at_phase FROM cost_tracking WHERE date='2026-07-27'").fetchone()
    conn.close()
    assert row["aborted_at_phase"] == "deep_analysis"


@pytest.mark.parametrize("phase_fn, expected", [
    ("main.fetch_market_context",          "market_context"),
    ("main.collect_sector_momentum",       "sector_momentum"),
    ("main.broad_scan_batch",              "broad_scan"),
    ("main.run_policy_monitor",            "policy_monitor"),
    ("main.analyze_batches",               "deep_analysis"),
    ("main.analyze_commodities_and_crypto", "commodities_crypto"),
    ("main.check_open_positions",          "portfolio_check"),
    ("main.rank_and_persist",              "ranking"),
])
def test_every_phase_reports_itself_on_cost_cap(tmp_db_path, mocker, phase_fn, expected):
    """Der Phasenname muss aus der tatsaechlichen Abbruchstelle stammen — sonst
    zeigt die Fehlermail wieder pauschal auf dieselbe Phase."""
    from src.cost_tracker import CostCapExceeded
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })
    mocker.patch(phase_fn, side_effect=CostCapExceeded("cap hit"))

    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))

    from src import db
    conn = db.connect(str(tmp_db_path))
    row = conn.execute(
        "SELECT aborted_at_phase FROM cost_tracking WHERE date='2026-07-27'").fetchone()
    conn.close()
    assert row["aborted_at_phase"] == expected


def test_successful_run_reports_no_aborted_phase(tmp_db_path, mocker):
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })

    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))

    from src import db
    conn = db.connect(str(tmp_db_path))
    row = conn.execute(
        "SELECT aborted_at_phase FROM cost_tracking WHERE date='2026-07-27'").fetchone()
    conn.close()
    assert row["aborted_at_phase"] is None


def test_guess_aborted_phase_is_gone():
    import main
    assert not hasattr(main, "_guess_aborted_phase")


# ---------- B-10: Mailversand vom Analyse-Erfolg trennen ----------


def test_mail_failure_does_not_discard_the_run(tmp_db_path, mocker):
    """Die Analyse ist zu diesem Zeitpunkt persistiert. Ein Zustellfehler darf
    daran nichts aendern — die Kostenzeile muss in der DB stehen bleiben."""
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })
    mocker.patch("main.send_daily_email",
                 side_effect=RuntimeError("HTTP Error 401: Unauthorized"))

    from main import run_pipeline, MailDeliveryError
    with pytest.raises(MailDeliveryError):
        run_pipeline(run_type="pre_market", date="2026-07-27",
                     db_path=str(tmp_db_path))

    from src import db
    conn = db.connect(str(tmp_db_path))
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM cost_tracking WHERE date='2026-07-27'"
    ).fetchone()["n"] == 1
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM market_context WHERE date='2026-07-27'"
    ).fetchone()["n"] == 1
    conn.close()


def test_mail_failure_still_fails_the_run(tmp_db_path, mocker):
    """Der Lauf bleibt rot — ein unbemerkter Mailausfall waere schlimmer als
    ein roter Job."""
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })
    mocker.patch("main.send_daily_email",
                 side_effect=RuntimeError("HTTP Error 401: Unauthorized"))
    mocker.patch("main.send_error_email")

    from main import main as cli
    with pytest.raises(SystemExit) as e:
        cli(["--run-type", "pre_market", "--date", "2026-07-27",
             "--db-path", str(tmp_db_path)])
    assert e.value.code == 1


def test_mail_failure_message_names_the_analysis_as_complete(tmp_db_path, mocker, caplog):
    """Die Logzeile muss 'Analyse fertig, nur Zustellung kaputt' sagen — sonst
    sucht man den Fehler in der falschen Phase."""
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })
    mocker.patch("main.send_daily_email",
                 side_effect=RuntimeError("HTTP Error 401: Unauthorized"))

    from main import run_pipeline, MailDeliveryError
    with caplog.at_level("ERROR"):
        with pytest.raises(MailDeliveryError):
            run_pipeline(run_type="pre_market", date="2026-07-27",
                         db_path=str(tmp_db_path))
    assert "persistiert" in caplog.text
    assert "Mailversand" in caplog.text


def test_successful_mail_leaves_no_error(tmp_db_path, mocker):
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })
    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27",
                 db_path=str(tmp_db_path))


# ---------- Sprint 3B / Plan 2, Task 1/13: trade_proposals ----------

def _stub_trade_proposals_side_phases(mocker) -> None:
    """Legt die Phasen still, die Task 13 um das urspruengliche Geruest herum
    ergaenzt hat (Markt-Kontext, Sektor-Momentum, Policy-Monitor,
    Portfolio-Check) — die beiden Geruest-Tests unten pruefen nur die
    Kurs-Erfassung bzw. den Mailversand (Task 14) und sollen dafuer nicht
    wirklich Claude oder Capital.com anfassen."""
    mocker.patch("main.fetch_market_context", return_value={"vix_level": 18.0})
    mocker.patch("main.collect_sector_momentum", return_value={})
    mocker.patch("main.run_policy_monitor",
                 return_value={"policy_risk_level": "low", "events": []})
    mocker.patch("main.check_open_positions", return_value=[])


def test_run_trade_proposals_collects_all_tickers(tmp_db_path, mocker):
    """B.2/Schritt 1: der 16:10-Lauf zieht frische Kurse fuer ALLE Ticker,
    nicht nur fuer die Top-Listen."""
    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    collect_mock = mocker.patch("main.collect", return_value=([], 0, {}))
    _stub_trade_proposals_side_phases(mocker)
    mocker.patch("main.send_trade_proposals_email")  # Task 14: sonst echter Versand

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    # zwei Aufrufe: SP500 und Commodities/Crypto
    assert collect_mock.call_count == 2
    passed = [set(c.kwargs["tickers"]) for c in collect_mock.call_args_list]
    assert set(config.SP500_MVP_TICKERS) in passed
    cc = set(config.COMMODITY_TICKERS.values()) | set(config.CRYPTO_TICKERS.values())
    assert cc in passed


def test_run_trade_proposals_sends_the_mail(tmp_db_path, mocker):
    """Task 14: der Nachmittagslauf verschickt jetzt die 16:10-Mail -- die alte
    Erwartung (kein Versand) galt nur fuer den damaligen Ausbaustand."""
    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.collect", return_value=([], 0, {}))
    _stub_trade_proposals_side_phases(mocker)
    send = mocker.patch("main.send_trade_proposals_email")

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    send.assert_called_once()


def test_run_trade_proposals_backfills_only_policy_risk_level(tmp_db_path, mocker):
    """trade_proposals ruft fetch_fear_greed() nie (kein Phase 3b) -- nur
    policy_risk_level darf hier nachgetragen werden, fear_greed_value bleibt
    NULL statt eines erfundenen Werts."""
    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.collect", return_value=([], 0, {}))
    _stub_trade_proposals_side_phases(mocker)
    mocker.patch("main.send_trade_proposals_email")

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    import sqlite3
    conn = sqlite3.connect(str(tmp_db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM market_context WHERE date='2026-07-30' "
        "AND run_type='trade_proposals'").fetchone()
    conn.close()
    assert row["policy_risk_level"] == "low"
    assert row["fear_greed_value"] is None


# ---------- Sprint 3B / Plan 2, Task 5: Phase 1c — Pflicht-Kandidaten (B.4) ----------


def test_forced_candidates_maps_epics_and_skips_foreign(mocker):
    """B.4: bekannte Epics werden zu Tickern, fremde geloggt und uebersprungen."""
    provider = MagicMock()
    provider.get_open_positions.return_value = [
        {"ticker": "GOLD"}, {"ticker": "AAPL"}, {"ticker": "PPHE"},
    ]
    from main import _forced_candidates
    assert _forced_candidates(provider) == {"GC=F", "AAPL"}


def test_forced_candidates_is_empty_when_provider_fails(mocker):
    """get_open_positions() gibt bei Fehlern [] zurueck — kein Absturz."""
    provider = MagicMock()
    provider.get_open_positions.return_value = []
    from main import _forced_candidates
    assert _forced_candidates(provider) == set()


def test_forced_candidate_reaches_deep_analysis(tmp_db_path, mocker):
    """Integrationstest fuer B.4: eine offene Capital.com-Position auf AAPL, die
    der Cutoff eigentlich nicht ausgewaehlt haette (news_strength=0, kein
    Tech-Signal), muss trotzdem in Phase 3 (analyze_batches) ankommen — sonst
    greift Phase 1c nicht bis in die Tiefenanalyse durch, obwohl echtes Geld
    daran haengt. Die Ueberschreibung sitzt seit Sprint 3C / Plan 2 Task 10
    direkt in cutoff_candidates() (forced_candidates-Parameter), nicht mehr in
    einem separaten _apply_forced_candidates()-Schritt. Seit Plan 3a Task 9
    zeigt sich die Aufnahme als Praesenz in ticker_datas statt als
    exclude=False -- quick_filter_results ist mit dem Interim-Adapter
    entfallen."""
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })
    mocker.patch("main.collect", return_value=(
        [{"ticker": "AAPL", "intraday_range_pct": 1.5, "price": 178.0}], 0, {}))

    provider = MagicMock()
    provider.get_open_positions.return_value = [{"ticker": "AAPL"}]
    mocker.patch("main.CapitalComProvider", return_value=provider)

    mocker.patch("main.broad_scan_batch", return_value=[
        {"ticker": "AAPL", "news_strength": 0, "news_note": ""},
    ])
    mock_deep = mocker.patch("main.analyze_batches", return_value=([], []))

    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))

    passed_tickers = [td["ticker"] for td in mock_deep.call_args.kwargs["ticker_datas"]]
    assert passed_tickers == ["AAPL"]


# ---------- Phase 2b verdrahtet (Abschluss-Review Plan 2, Spec 4.7) ----------


def test_phase_2b_runs_for_the_cutoff_candidates(tmp_db_path, mocker):
    """Abschluss-Review-Befund: fetch_missing_fundamentals() war gebaut und
    getestet, hatte aber KEINEN Produktions-Aufrufer -- Spec 4.7 verlangt sie
    als Selbstheilung fuer Kandidaten mit Cache-Miss. Der Test pinnt, dass
    Phase 2b laeuft und genau die Cutoff-Auswahl bekommt."""
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })
    mocker.patch("main.collect", return_value=(
        [{"ticker": "AAPL", "intraday_range_pct": 1.5, "price": 178.0},
         {"ticker": "MSFT", "intraday_range_pct": 1.2, "price": 400.0}], 0, {}))
    mocker.patch("main.broad_scan_batch", return_value=[
        {"ticker": "AAPL", "news_strength": 2, "news_note": "x"},
        {"ticker": "MSFT", "news_strength": 0, "news_note": ""},
    ])
    mock_2b = mocker.patch("main.run_phase_2b")

    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))

    mock_2b.assert_called_once()
    kwargs = mock_2b.call_args.kwargs
    # nur der qualifizierte Ticker, nicht das ganze Universum (Spec 4.7)
    assert kwargs["candidates"] == ["AAPL"]


def test_phase_2b_failure_does_not_abort_the_run(tmp_db_path, mocker):
    """Finnhub ist in 2b ausdruecklich kein Single Point of Failure (Spec 4.7):
    ein Ausfall kostet Kontext-Qualitaet, nicht den bezahlten Lauf."""
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })
    mocker.patch("main.collect", return_value=(
        [{"ticker": "AAPL", "intraday_range_pct": 1.5, "price": 178.0}], 0, {}))
    mocker.patch("main.broad_scan_batch", return_value=[
        {"ticker": "AAPL", "news_strength": 2, "news_note": "x"}])
    mocker.patch("main.run_phase_2b", side_effect=RuntimeError("finnhub down"))
    mock_email = mocker.patch("main.send_daily_email")

    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))

    mock_email.assert_called_once()
    assert mock_email.call_args.kwargs["payload"]["cost_summary"][
        "aborted_at_phase"] is None


# ---------- Sprint 3C / Plan 3a, Task 9: run_pipeline() auf Batch-Phase-3 ----------


def test_run_pipeline_deep_analysis_only_receives_selected_tickers(tmp_db_path, mocker):
    """Die Auswahl liegt im Cutoff, nicht mehr im exclude-Flag: Phase 3 sieht
    ausschliesslich die selektierten Ticker."""
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })
    mocker.patch("main.collect", return_value=(
        [{"ticker": "AAPL", "intraday_range_pct": 1.5, "price": 178.0},
         {"ticker": "MSFT", "intraday_range_pct": 1.2, "price": 400.0}], 0, {}))
    mocker.patch("main.broad_scan_batch", return_value=[
        {"ticker": "AAPL", "news_strength": 2, "news_note": "x"},
        {"ticker": "MSFT", "news_strength": 0, "news_note": ""},
    ])

    with patch("main.analyze_batches", return_value=([], [])) as ab:
        run_pipeline(run_type="pre_market", date="2026-07-27",
                     db_path=str(tmp_db_path))

    uebergeben = [td["ticker"] for td in ab.call_args.kwargs["ticker_datas"]]
    assert uebergeben == ["AAPL"]          # MSFT wurde nicht selektiert


def test_adapter_and_single_analysis_path_are_gone():
    """Die Plan-2-Interimsbruecke ist entfernt, nicht nur ungenutzt --
    ungelesener Code, der Wirkung vortaeuscht, ist genau die Altlast-Klasse,
    die MAX_DEEP_ANALYSIS vor Plan 2 war."""
    import src.deep_analysis as da
    assert not hasattr(da, "adapt_cutoff_to_quick_filter")
    assert not hasattr(da, "analyze_assets")
    assert not hasattr(da, "analyze_asset")


# ---------- Sprint 3B / Plan 2, Task 3: kein toter Code (B.1) ----------

def test_removed_functions_are_gone():
    """B.1: 'vollstaendig, keine Leichen'. Ein spaeterer Reflex-Import wuerde
    hier auffliegen."""
    import main
    import src.email_sender as es
    for name in ("run_position_check", "run_evaluate"):
        assert not hasattr(main, name), f"main.{name} existiert noch"
    for name in ("render_position_check_html", "send_position_check_email"):
        assert not hasattr(es, name), f"email_sender.{name} existiert noch"


def test_position_check_prompt_file_is_deleted():
    from pathlib import Path
    assert not (Path("prompts") / "position_check_v1.txt").exists()


# ---------- Sprint 3B / Plan 2, Task 9: Phase 1d — Sektor-Momentum (D9) ----------


def test_sector_momentum_is_collected_after_data_collection(mocker):
    """Plan 1 hat collect_sector_momentum gebaut, aber nie aufgerufen. Ohne
    diesen Test faellt ein spaeteres Herausfallen nicht auf.

    _mock_all_other_phases patcht main.collect selbst mit einem Fake — deshalb
    muss der eigene, ordnungspruefende Fake HIER NACH dem Helper gesetzt werden,
    sonst ueberschreibt der Helper ihn wieder stillschweigend (genau die Falle,
    vor der sein Docstring fuer rank_and_persist/check_open_positions warnt)."""
    order: list[str] = []
    _mock_all_other_phases(mocker)
    mocker.patch("main.collect",
                 side_effect=lambda **kw: order.append("collect") or ([], 0, {}))
    mocker.patch("main.collect_sector_momentum",
                 side_effect=lambda **kw: order.append("sector_momentum") or {})
    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-30", db_path=":memory:")
    assert "sector_momentum" in order, "Phase 1d laeuft gar nicht"
    assert order.index("collect") < order.index("sector_momentum"), (
        "db_momentum mittelt die heutigen Bars — die schreibt erst Phase 1"
    )


def test_sector_momentum_failure_does_not_abort_the_run(mocker):
    """Ein Sektor-ETF-Ausfall darf keinen 3-EUR-Lauf kosten."""
    mocker.patch("main.collect_sector_momentum", side_effect=RuntimeError("boom"))
    _mock_all_other_phases(mocker)
    mocker.patch("main.collect", return_value=([], 0, {}))
    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-30", db_path=":memory:")
    # kein raise


# ---------- Sprint 3B / Plan 2, Task 13: Re-Validierung + Persistenz ----------


def _pred_row(conn, **over):
    base = {"date": "2026-07-30", "run_type": "pre_market", "ticker": "AAPL",
            "direction": "long", "entry_price": 100.0, "tp_price": 106.0,
            "sl_price": 98.0, "probability_pct": 65, "confidence": "high"}
    from src import db
    return db.save_prediction(conn, {**base, **over})


def test_confirmed_signal_supersedes_the_morning_row(in_memory_db):
    from src import db
    from main import _persist_revision
    db.init_schema(in_memory_db)
    pid = _pred_row(in_memory_db)
    pred = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()

    new_id = _persist_revision(
        conn=in_memory_db, pred=pred,
        verdict={"verdict": "bestaetigt", "probability_pct": 71,
                 "reason": "haelt", "entry_window_low": 100.2,
                 "entry_window_high": 101.0},
        snapshot={"price": 101.0}, date="2026-07-30", checks=[],
        momentum=(1.2, 0.8),
    )
    assert new_id is not None
    old = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    assert old["status"] == "superseded" and old["superseded_by"] == new_id
    new = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (new_id,)).fetchone()
    assert new["run_type"] == "trade_proposals"
    assert new["entry_price"] == 101.0, "Einstieg ist der 16:10-Kurs"
    assert new["tp_price"] == 106.0, "TP bleibt absolut — das Ziel wandert nicht"
    assert new["probability_pct"] == 71


def test_supersession_carries_the_plan3b_signal_columns(in_memory_db):
    """C2 (Plan-3b-Abschluss-Review): die 16:10-Nachfolgezeile muss den
    Signalzustand tragen, der sie erzeugt hat -- allen voran candidate_class.

    Vorher fehlten die acht Spalten in der supersede_prediction()-Nutzlast, und
    db._insert_prediction() stempelte die Nachfolgezeile per Default-Merge auf
    'core'. Still, aber folgenreich: eine bestaetigte Divergenz-Zeile ist die
    EINZIGE Divergenz-Zeile, die je ein Outcome bekommt -- sie landete damit im
    core-Topf, und divergence.confirmed blieb strukturell 0.

    Bewusst durch den Produktionspfad (_persist_revision), nicht ueber eine von
    Hand gesetzte Zeile: der bestehende db-Test war genau deshalb gruen, obwohl
    die Pipeline diesen Zustand gar nicht erzeugen konnte."""
    from src import db
    from main import _persist_revision
    db.init_schema(in_memory_db)
    pid = _pred_row(
        in_memory_db, candidate_class="divergence", tech_direction="neutral",
        tech_agreement=0, tech_adx_band="weak", tech_strength=0,
        analysis_strength=6, rank_score=None, news_strength=3,
    )
    pred = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    assert pred["candidate_class"] == "divergence", "Testaufbau"

    new_id = _persist_revision(
        conn=in_memory_db, pred=pred,
        verdict={"verdict": "bestaetigt", "probability_pct": 71, "reason": "haelt"},
        snapshot={"price": 101.0}, date="2026-07-30", checks=[],
        momentum=(None, None),
    )
    new = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (new_id,)).fetchone()
    assert new["candidate_class"] == "divergence", \
        "Die Klasse muss die Abloesung ueberleben, sonst kippt der core/divergence-Split"
    assert new["tech_direction"] == "neutral"
    assert new["tech_agreement"] == 0
    assert new["tech_adx_band"] == "weak"
    assert new["tech_strength"] == 0
    assert new["analysis_strength"] == 6
    assert new["rank_score"] is None
    assert new["news_strength"] == 3


def test_supersession_carries_the_c1_indicators(in_memory_db):
    """O2 (Plan-3b-Gesamtreview): der C.1-Fix (atr_pct/rsi_at_entry/volume_ratio
    nicht mehr hart None) deckte nur den pre_market-Pfad ab
    (_to_prediction_row()) -- _persist_revision() liess die 16:10-Nachfolgezeile
    unangetastet, die drei Spalten blieben auf JEDER trade_proposals-Zeile None.
    Gleiche Fehlerklasse wie C2 (Werte vorhanden, aber nicht durchgereicht), hier
    aber am 16:10-Snapshot statt an den Plan-3b-Signalspalten: main.py baut
    `snapshots = {td["ticker"]: td for td in ...}` aus einem frischen collect()-
    Lauf, td traegt atr_pct/rsi_14/volume_ratio bereits (src/data_collector.py) --
    identisch zu dem Weg, den main._signal_context() fuer den Morgenlauf nutzt."""
    from src import db
    from main import _persist_revision
    db.init_schema(in_memory_db)
    pid = _pred_row(in_memory_db)
    pred = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()

    new_id = _persist_revision(
        conn=in_memory_db, pred=pred,
        verdict={"verdict": "bestaetigt", "probability_pct": 71, "reason": "haelt"},
        snapshot={"price": 101.0, "atr_pct": 2.7, "rsi_14": 61.2,
                  "volume_ratio": 1.05},
        date="2026-07-30", checks=[], momentum=(None, None),
    )
    new = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (new_id,)).fetchone()
    assert new["atr_pct"] == 2.7
    assert new["rsi_at_entry"] == 61.2
    assert new["volume_ratio"] == 1.05


def test_supersession_survives_a_snapshot_without_c1_indicators(in_memory_db):
    """Kein Rohstoff/Krypto-Sonderfall noetig, aber ein fehlender Snapshot-Wert
    (z.B. Datenausfall) darf _persist_revision() nicht zum Absturz bringen."""
    from src import db
    from main import _persist_revision
    db.init_schema(in_memory_db)
    pid = _pred_row(in_memory_db)
    pred = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()

    new_id = _persist_revision(
        conn=in_memory_db, pred=pred,
        verdict={"verdict": "bestaetigt", "probability_pct": 71, "reason": "haelt"},
        snapshot={"price": 101.0}, date="2026-07-30", checks=[],
        momentum=(None, None),
    )
    new = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (new_id,)).fetchone()
    assert new["atr_pct"] is None
    assert new["rsi_at_entry"] is None
    assert new["volume_ratio"] is None


def test_confirmed_divergence_lands_in_the_divergence_bucket(in_memory_db):
    """Die Wirkung von C2 dort, wo sie sichtbar wird: nach einer bestaetigten
    Divergenz-Zeile muss load_revision_effectiveness() sie im divergence-Topf
    zaehlen, nicht im core-Topf."""
    from src import db
    from main import _persist_revision
    db.init_schema(in_memory_db)
    pid = _pred_row(in_memory_db, candidate_class="divergence")
    pred = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    new_id = _persist_revision(
        conn=in_memory_db, pred=pred,
        verdict={"verdict": "bestaetigt", "probability_pct": 71, "reason": "haelt"},
        snapshot={"price": 101.0}, date="2026-07-30", checks=[],
        momentum=(None, None),
    )
    db.save_outcome(in_memory_db, {
        "prediction_id": new_id, "evaluated_date": "2026-07-31",
        "price_after_eod": 104.0, "correct_direction_eod": True,
        "profit_loss_eur": 12.0, "exit_reason": "eod",
    })
    eff = db.load_revision_effectiveness(in_memory_db, "2026-07-01")
    assert eff["divergence"]["confirmed"]["total"] == 1
    assert eff["core"]["confirmed"]["total"] == 0


def test_flipped_signal_creates_no_counter_position(in_memory_db):
    """E5: melden, nicht handeln."""
    from src import db
    from main import _persist_revision
    db.init_schema(in_memory_db)
    pid = _pred_row(in_memory_db)
    pred = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()

    new_id = _persist_revision(
        conn=in_memory_db, pred=pred,
        verdict={"verdict": "gedreht", "probability_pct": 30, "reason": "gekippt"},
        snapshot={"price": 99.0}, date="2026-07-30", checks=[], momentum=(None, None),
    )
    assert new_id is None
    rows = in_memory_db.execute("SELECT * FROM predictions").fetchall()
    assert len(rows) == 1, "keine Gegenposition"
    assert rows[0]["status"] == "open", "bleibt offen und wird ausgewertet"
    assert rows[0]["revision_verdict"] == "gedreht"


def test_hard_check_marks_the_signal_verworfen(in_memory_db):
    from src import db
    from main import _persist_revision
    from src.signal_checks import CheckResult
    db.init_schema(in_memory_db)
    pid = _pred_row(in_memory_db)
    pred = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()

    new_id = _persist_revision(
        conn=in_memory_db, pred=pred,
        verdict={"verdict": "bestaetigt", "probability_pct": 71, "reason": "x"},
        snapshot={"price": 101.0}, date="2026-07-30",
        checks=[CheckResult("vix_no_new_longs", "VIX 41", enforced=True)],
        momentum=(None, None),
    )
    assert new_id is None
    row = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row["revision_verdict"] == "verworfen" and row["status"] == "open"


def test_entry_past_the_stop_is_verworfen(in_memory_db):
    """Der Kurs ist seit 15:00 durch den SL gelaufen — kein Einstieg mehr."""
    from src import db
    from main import _persist_revision
    db.init_schema(in_memory_db)
    pid = _pred_row(in_memory_db)
    pred = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()

    new_id = _persist_revision(
        conn=in_memory_db, pred=pred,
        verdict={"verdict": "bestaetigt", "probability_pct": 71, "reason": "x"},
        snapshot={"price": 97.0}, date="2026-07-30", checks=[], momentum=(None, None),
    )
    assert new_id is None
    row = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row["revision_verdict"] == "verworfen"


def test_revalidation_failure_leaves_the_row_untouched(tmp_db_path, mocker):
    """Nie auf Basis eines Fehlers abloesen — sonst verschwindet ein gutes
    Signal, weil ein Call einmal unlesbar antwortete."""
    from src import db
    from src.revalidation import RevalidationError
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    pid = _pred_row(conn)
    conn.commit(); conn.close()

    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.collect", return_value=([{"ticker": "AAPL", "price": 101.0}], 0, {}))
    mocker.patch("main.fetch_market_context", return_value={"vix_level": 18.0})
    mocker.patch("main.collect_sector_momentum", return_value={})
    mocker.patch("main.run_policy_monitor", return_value={"policy_risk_level": "low",
                                                         "events": []})
    mocker.patch("main.check_open_positions", return_value=[])
    mocker.patch("main.revalidate_one", side_effect=RevalidationError("kaputt"))
    mocker.patch("main.send_trade_proposals_email")  # Task 14: sonst echter Versand

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    row = conn.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row["status"] == "open"
    assert row["revision_verdict"] is None
    conn.close()


def test_skipped_ticker_is_never_superseded_on_a_stale_price(tmp_db_path, mocker):
    """C2: collect() gibt uebersprungene Ticker gar nicht erst zurueck — weder die
    per B.7 stillgelegten noch die mit fehlgeschlagenem Abruf.

    Ohne frischen Kurs darf der 16:10-Lauf die Morgenzeile NICHT abloesen. Sonst
    faellt der Einstieg auf den 15:00-Kurs zurueck (`snapshot.get("price") or
    pred["entry_price"]`) und die neue Zeile behauptet einen Nachmittags-Einstieg,
    den es nie gab — P&L, correct_direction_eod und jeder 3D-Vergleich von
    Morgen- gegen Nachmittags-probability_pct erben den Fehler stillschweigend.

    Der Claude-Call entfaellt gleich mit: er saehe nur 'CURRENT SNAPSHOT: {}'."""
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    pid = _pred_row(conn)
    conn.commit(); conn.close()

    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    # AAPL wurde uebersprungen -> taucht in der Ergebnisliste nicht auf.
    mocker.patch("main.collect", return_value=([], 1, {}))
    mocker.patch("main.fetch_market_context", return_value={"vix_level": 18.0})
    mocker.patch("main.collect_sector_momentum", return_value={})
    mocker.patch("main.run_policy_monitor", return_value={"policy_risk_level": "low",
                                                         "events": []})
    mocker.patch("main.check_open_positions", return_value=[])
    reval = mocker.patch("main.revalidate_one")
    mail = mocker.patch("main.send_trade_proposals_email")

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    reval.assert_not_called(), "ohne frischen Kurs kein Claude-Call"

    conn = db.connect(str(tmp_db_path))
    row = conn.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row["status"] == "open", "die Morgenzeile bleibt offen"
    assert row["revision_verdict"] is None
    assert row["superseded_by"] is None
    n_new = conn.execute(
        "SELECT COUNT(*) c FROM predictions WHERE run_type='trade_proposals'"
    ).fetchone()["c"]
    assert n_new == 0, "keine Zeile mit erfundenem 16:10-Einstieg"
    conn.close()

    changes = mail.call_args.kwargs["payload"]["signal_changes"]
    assert [c["verdict"] for c in changes] == ["nicht_geprueft"]


def _tp_run_mocks(mocker, prices):
    """Die immergleichen Mocks fuer einen run_trade_proposals-Lauf."""
    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.collect", return_value=(prices, 0, {}))
    mocker.patch("main.fetch_market_context", return_value={"vix_level": 18.0})
    mocker.patch("main.collect_sector_momentum", return_value={})
    mocker.patch("main.run_policy_monitor", return_value={"policy_risk_level": "low",
                                                         "events": []})
    mocker.patch("main.check_open_positions", return_value=[])
    return mocker.patch("main.send_trade_proposals_email")


def test_transient_api_error_does_not_kill_the_run(tmp_db_path, mocker):
    """C3: call_claude reicht nach zwei Retries die rohe Exception durch.

    Ein 429/529 der Anthropic-API kommt als APIStatusError an — kein
    RevalidationError. Frueher entkam der bis aus run_trade_proposals heraus:
    save_cost_tracking() lief nie, jeder bereits ausgegebene EUR blieb
    unverbucht, und die schon abgeloesten Ticker sah niemand. Bei ~27
    sequentiellen Calls je Lauf ist ein transienter Fehler kein Randfall."""
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    pid = _pred_row(conn)
    conn.commit(); conn.close()

    mail = _tp_run_mocks(mocker, [{"ticker": "AAPL", "price": 101.0}])
    mocker.patch("main.revalidate_one",
                 side_effect=RuntimeError("529 overloaded_error"))

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    row = conn.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row["status"] == "open", "nie auf Basis eines Fehlers abloesen"
    assert row["revision_verdict"] is None
    n_cost = conn.execute("SELECT COUNT(*) c FROM cost_tracking").fetchone()["c"]
    assert n_cost == 1, "die Kosten des Laufs muessen verbucht werden"
    conn.close()

    mail.assert_called_once()
    changes = mail.call_args.kwargs["payload"]["signal_changes"]
    assert [c["verdict"] for c in changes] == ["nicht_geprueft"]


def test_cost_cap_keeps_the_already_checked_signals(tmp_db_path, mocker):
    """Ein Abbruch am Kostendeckel darf das bereits Geleistete nicht verwerfen.

    Frueher hing das Ergebnis an `payload[...] = _revalidate_all(...)`: reisst der
    Aufruf ab, findet die Zuweisung nie statt und die Mail meldet '0 Signale' —
    obwohl die ersten Zeilen in der DB laengst abgeloest sind. Spec 7.1 verlangt
    Teilergebnis plus Warnbalken."""
    from src import db
    from src.cost_tracker import CostCapExceeded
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    _pred_row(conn, ticker="AAPL")
    _pred_row(conn, ticker="MSFT")
    conn.commit(); conn.close()

    mail = _tp_run_mocks(mocker, [{"ticker": "AAPL", "price": 101.0},
                                  {"ticker": "MSFT", "price": 101.0}])
    mocker.patch("main.revalidate_one", side_effect=[
        {"verdict": "bestaetigt", "probability_pct": 70, "reason": "haelt",
         "entry_window_low": 100.5, "entry_window_high": 101.5},
        CostCapExceeded("Deckel erreicht"),
    ])

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    changes = mail.call_args.kwargs["payload"]["signal_changes"]
    assert len(changes) == 1, "das bereits gepruefte Signal bleibt in der Mail"
    assert changes[0]["ticker"] == "AAPL"
    assert changes[0]["verdict"] == "bestaetigt"
    summary = mail.call_args.kwargs["payload"]["cost_summary"]
    assert summary["aborted_at_phase"] == "revalidation"


@pytest.mark.parametrize("phase,target", [
    ("market_context",  "main.fetch_market_context"),
    ("data_collection", "main.collect"),
    ("sector_momentum", "main.collect_sector_momentum"),
    ("policy_monitor",  "main.run_policy_monitor"),
    ("revalidation",    "main.revalidate_one"),
    ("portfolio_check", "main.check_open_positions"),
])
def test_cost_abort_reports_the_right_phase(tmp_db_path, mocker, phase, target):
    """B-05 fuer den neuen Run-Type: bricht der Lauf am Kosten-Deckel ab, muss die
    Kostenzeile die TATSAECHLICHE Phase nennen. Der alte Bug gab hier systematisch
    'policy_monitor' zurueck, egal wo es knallte. Eine kuenftig ergaenzte Phase ohne
    current_phase-Zuweisung faellt hier auf."""
    from src import db
    from src.cost_tracker import CostCapExceeded
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    _pred_row(conn); conn.commit(); conn.close()

    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.fetch_market_context", return_value={"vix_level": 18.0})
    mocker.patch("main.collect", return_value=([{"ticker": "AAPL", "price": 101.0}], 0, {}))
    mocker.patch("main.collect_sector_momentum", return_value={})
    mocker.patch("main.run_policy_monitor",
                 return_value={"policy_risk_level": "low", "events": []})
    mocker.patch("main.revalidate_one", return_value={
        "verdict": "bestaetigt", "probability_pct": 71, "reason": "ok"})
    mocker.patch("main.check_open_positions", return_value=[])
    mocker.patch("main.send_trade_proposals_email")  # Task 14: sonst echter Versand
    mocker.patch(target, side_effect=CostCapExceeded("Deckel"))

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    row = conn.execute(
        "SELECT aborted_at_phase FROM cost_tracking WHERE run_type='trade_proposals'"
    ).fetchone()
    assert row["aborted_at_phase"] == phase
    conn.close()


# ---------- Review-Fix 1: Rotationsfelder erreichen den Nachmittags-Portfolio-Check ----------


def test_portfolio_check_sees_sector_rotation_from_market_context(tmp_db_path, mocker):
    """load_trend_context() kann sector_rotation/trend_summary nicht rekonstruieren
    (trend_analyses persistiert sie nie) -- der frisch erhobene Markt-Kontext
    liefert aber sector_rotation_in/out und macro_summary, und die werden am
    Aufrufort in den Trend-Kontext gemischt, den der Portfolio-Check sieht.
    Sonst bekaeme der 16:10-Lauf einen strikt aermeren Prompt als der Morgenlauf."""
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn); conn.close()

    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.collect", return_value=([], 0, {}))
    mocker.patch("main.fetch_market_context", return_value={
        "vix_level": 18.0, "sector_rotation_in": "Utilities",
        "sector_rotation_out": "Technology", "macro_summary": "nervoes",
    })
    mocker.patch("main.collect_sector_momentum", return_value={})
    mocker.patch("main.run_policy_monitor",
                 return_value={"policy_risk_level": "low", "events": []})
    mock_portfolio = mocker.patch("main.check_open_positions", return_value=[])
    mocker.patch("main.send_trade_proposals_email")  # Task 14: sonst echter Versand

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    passed_trend_ctx = mock_portfolio.call_args.kwargs["trend_context"]
    assert passed_trend_ctx["sector_rotation_in"] == "Utilities"
    assert passed_trend_ctx["sector_rotation_out"] == "Technology"
    assert passed_trend_ctx["macro_summary"] == "nervoes"


def test_portfolio_check_still_works_with_a_real_morning_trend_context(tmp_db_path, mocker):
    """Regression: der Merge darf die aus trend_analyses gelesenen Trends nicht
    verdraengen, nur die Rotationsfelder ergaenzen."""
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    db.save_trend_analysis(conn, {
        "date": "2026-07-30", "run_type": "pre_market",
        "trend_name": "ai-capex-acceleration", "strength": 8,
        "duration_estimate": "1m+", "summary": "x",
        "beneficiary_tickers": ["NVDA"], "negative_tickers": [],
        "next_catalyst": "x",
    })
    conn.close()

    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.collect", return_value=([], 0, {}))
    mocker.patch("main.fetch_market_context", return_value={
        "vix_level": 18.0, "sector_rotation_in": "Utilities",
        "sector_rotation_out": "Technology", "macro_summary": "nervoes",
    })
    mocker.patch("main.collect_sector_momentum", return_value={})
    mocker.patch("main.run_policy_monitor",
                 return_value={"policy_risk_level": "low", "events": []})
    mock_portfolio = mocker.patch("main.check_open_positions", return_value=[])
    mocker.patch("main.send_trade_proposals_email")  # Task 14: sonst echter Versand

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    passed_trend_ctx = mock_portfolio.call_args.kwargs["trend_context"]
    assert passed_trend_ctx["trends"][0]["name"] == "ai-capex-acceleration"
    assert passed_trend_ctx["sector_rotation_in"] == "Utilities"


# ---------- Review-Fix 2: signal_changes hat auf jedem Pfad dieselben Schluessel ----------


def test_signal_changes_have_consistent_keys_on_revalidation_failure(tmp_db_path, mocker):
    """Der Fehlerpfad (RevalidationError) muss dieselben Schluessel liefern wie
    der Normalpfad -- sonst faellt ein spaeterer direkter Dict-Zugriff (statt
    .get()) bei einer 'nicht_geprueft'-Zeile mit KeyError um, sobald Task 14
    daraus die Mail rendert."""
    from src import db
    from src.revalidation import RevalidationError
    from src.cost_tracker import CostTracker
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    _pred_row(conn)
    conn.commit()

    mocker.patch("main.revalidate_one", side_effect=RevalidationError("kaputt"))

    from main import _revalidate_all
    out: list[dict] = []
    _revalidate_all(
        conn=conn, date="2026-07-30", snapshots={"AAPL": {"price": 101.0}},
        sector_mom={}, market_ctx={"vix_level": 18.0}, policy_context={},
        cost_tracker=CostTracker(), out=out,
    )
    conn.close()

    assert len(out) == 1
    expected_keys = {"ticker", "direction", "verdict", "probability_before",
                      "probability_after", "entry_window_low",
                      "entry_window_high", "reason", "checks"}
    assert set(out[0].keys()) == expected_keys
    assert out[0]["entry_window_low"] is None
    assert out[0]["entry_window_high"] is None


# ---------- Task 15 (B.3): Opening-Gap-Check im 16:10-Lauf ----------


def test_opening_gap_reaches_the_revalidation_prompt(tmp_db_path, mocker):
    """Der Gap muss beim Modell ankommen, sonst kann es ihn nicht wuerdigen."""
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    _pred_row(conn, entry_price=100.0)
    conn.commit(); conn.close()

    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.collect", return_value=([{"ticker": "AAPL", "price": 104.0}], 0, {}))
    mocker.patch("main.fetch_market_context", return_value={"vix_level": 18.0})
    mocker.patch("main.collect_sector_momentum", return_value={})
    mocker.patch("main.run_policy_monitor", return_value={"policy_risk_level": "low",
                                                          "events": []})
    mocker.patch("main.check_open_positions", return_value=[])
    mocker.patch("main.send_trade_proposals_email")
    reval = mocker.patch("main.revalidate_one", return_value={
        "verdict": "geschwaecht", "probability_pct": 50, "reason": "Gap"})

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    fired = {c.rule for c in reval.call_args.kwargs["checks"]}
    assert "opening_gap" in fired


# ---------- I1 (Plan-3b-Abschluss-Review): earnings-Check um 16:10 ----------


def test_imminent_earnings_blocks_the_signal_at_1610(in_memory_db, mocker):
    """Spec 5.3: der earnings-Check wird um 16:10 DURCHGESETZT.

    Er hatte bis zum Abschluss-Review genau eine Aufrufstelle -- ranking, und
    dort nur mit enforce=False. Er konnte damit nie etwas blockieren, also genau
    das nicht leisten, wofuer er das folgenlose Modell-Attribut earnings_warning
    ersetzen sollte."""
    from src import db
    from src.cost_tracker import CostTracker
    db.init_schema(in_memory_db)
    _pred_row(in_memory_db)
    reval = mocker.patch("main.revalidate_one", return_value={
        "verdict": "bestaetigt", "probability_pct": 71, "reason": "haelt"})

    from main import _revalidate_all
    out: list[dict] = []
    _revalidate_all(
        conn=in_memory_db, date="2026-07-30",
        snapshots={"AAPL": {"price": 101.0, "earnings_in_days": 1}},
        sector_mom={}, market_ctx={"vix_level": 18.0}, policy_context={},
        cost_tracker=CostTracker(), out=out,
    )

    fired = {c.rule: c for c in reval.call_args.kwargs["checks"]}
    assert "earnings_imminent" in fired, "Check laeuft um 16:10 gar nicht mit"
    assert fired["earnings_imminent"].enforced is True, \
        "erhoben, aber weich -- dann blockiert er weiterhin nichts"
    # Und er wirkt: keine Nachfolgezeile, die Morgenzeile traegt 'verworfen'.
    assert out[0]["verdict"] == "verworfen"
    rows = in_memory_db.execute(
        "SELECT run_type, status, revision_verdict FROM predictions").fetchall()
    assert len(rows) == 1, "keine trade_proposals-Nachfolgezeile"
    assert rows[0]["revision_verdict"] == "verworfen"
    assert rows[0]["status"] == "open", "bleibt offen, damit die Ablehnung messbar ist"


def test_distant_earnings_does_not_block_at_1610(in_memory_db, mocker):
    """Gegenprobe: der Check darf den Normalfall nicht anfassen -- sonst waere
    der Test oben auch mit einem immer-anschlagenden Check gruen."""
    from src import db
    from src.cost_tracker import CostTracker
    db.init_schema(in_memory_db)
    _pred_row(in_memory_db)
    reval = mocker.patch("main.revalidate_one", return_value={
        "verdict": "bestaetigt", "probability_pct": 71, "reason": "haelt"})

    from main import _revalidate_all
    out: list[dict] = []
    _revalidate_all(
        conn=in_memory_db, date="2026-07-30",
        snapshots={"AAPL": {"price": 101.0, "earnings_in_days": 30}},
        sector_mom={}, market_ctx={"vix_level": 18.0}, policy_context={},
        cost_tracker=CostTracker(), out=out,
    )
    assert "earnings_imminent" not in {
        c.rule for c in reval.call_args.kwargs["checks"]}
    assert out[0]["verdict"] == "bestaetigt"


# ---------- Task 5 (Preismodell): final_close ----------


def test_final_close_writes_final_bars_for_tickers_and_etfs(tmp_db_path, mocker):
    """final_close ist der EINZIGE Schreiber von price_history -- inklusive der
    Sub-Sektor-ETFs. Nur mit genau einem Schreiber, der ausschliesslich finale
    Bars schreibt, kann der Frozen-Bar-Bug nicht wiederkehren."""
    import pandas as pd
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn); conn.close()

    def _bar(close):
        return pd.DataFrame(
            {"Open": [close - 1], "High": [close + 2], "Low": [close - 2],
             "Close": [close], "Volume": [1000]},
            index=pd.DatetimeIndex([pd.Timestamp("2026-08-05")]))

    prov = MagicMock()
    prov._source_name = "capital.com"
    prov.get_ohlc_after.side_effect = lambda t, *a, **k: _bar(100.0)
    mocker.patch("main.CapitalComProvider", return_value=prov)
    mocker.patch("main.evaluate_open_predictions", return_value=0)
    mocker.patch("main.config.SP500_MVP_TICKERS", ["AAPL"])
    mocker.patch("main.config.USE_FULL_SP500", False)
    mocker.patch("main.config.SUB_SECTOR_ETFS", {"Semis": "SOXX"})
    mocker.patch("main.config.COMMODITY_TICKERS", {})
    mocker.patch("main.config.CRYPTO_TICKERS", {"Bitcoin": "BTC-USD"})
    mocker.patch("main.send_final_close_email")  # C.17: sonst blockiert das Netz-Fixture

    from main import run_final_close
    run_final_close(date="2026-08-06", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    tickers = {r["ticker"] for r in conn.execute(
        "SELECT DISTINCT ticker FROM price_history").fetchall()}
    conn.close()
    assert tickers == {"AAPL", "BTC-USD", "SOXX"}


def test_final_close_covers_exactly_the_bootstrap_universe(tmp_db_path, mocker):
    """final_close und `historical_loader --universe` muessen dieselbe Liste
    anfassen. Laufen sie auseinander, backfillt der Bootstrap einen Ticker, den
    final_close nie fortschreibt (oder umgekehrt) — und die Luecke faellt erst
    auf, wenn die Pipeline ihn mangels Bars ueberspringt."""
    import pandas as pd
    from src import db
    from src.universe import full_universe
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn); conn.close()

    bar = pd.DataFrame(
        {"Open": [99.0], "High": [102.0], "Low": [98.0],
         "Close": [100.0], "Volume": [1000]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-08-05")]))

    prov = MagicMock()
    prov._source_name = "capital.com"
    prov.get_ohlc_after.side_effect = lambda t, *a, **k: bar
    mocker.patch("main.CapitalComProvider", return_value=prov)
    mocker.patch("main.evaluate_open_predictions", return_value=0)
    mocker.patch("main.send_final_close_email")  # C.17: sonst blockiert das Netz-Fixture

    from main import run_final_close
    run_final_close(date="2026-08-06", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    written = {r["ticker"] for r in conn.execute(
        "SELECT DISTINCT ticker FROM price_history").fetchall()}
    conn.close()
    assert written == set(full_universe())


def test_final_close_treats_a_missing_bar_as_normal(tmp_db_path, mocker):
    """Wochenende und Feiertag: fuer Aktien gibt es keine neue Tagesbar, fuer
    Crypto schon. Das ist der erwartete Normalfall, kein Fehler -- der Job
    ueberspringt den Ticker und endet gruen."""
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn); conn.close()

    prov = MagicMock()
    prov._source_name = "capital.com"
    prov.get_ohlc_after.return_value = None          # keine Bar, kein Fehler
    mocker.patch("main.CapitalComProvider", return_value=prov)
    mocker.patch("main.evaluate_open_predictions", return_value=0)
    mocker.patch("main.config.SP500_MVP_TICKERS", ["AAPL"])
    mocker.patch("main.config.USE_FULL_SP500", False)
    mocker.patch("main.config.SUB_SECTOR_ETFS", {})
    mocker.patch("main.build_commodity_crypto_inputs", return_value=[])
    mocker.patch("main.send_final_close_email")  # C.17: sonst blockiert das Netz-Fixture

    from main import run_final_close
    run_final_close(date="2026-08-06", db_path=str(tmp_db_path))   # darf nicht werfen

    conn = db.connect(str(tmp_db_path))
    n = conn.execute("SELECT COUNT(*) c FROM price_history").fetchone()["c"]
    conn.close()
    assert n == 0


def test_final_close_is_a_known_run_type():
    from main import RUN_TYPES
    assert "final_close" in RUN_TYPES


def test_close_is_a_removed_run_type():
    """`close` (22:30 Berlin) ist am 2026-08-18 ersatzlos entfallen.

    Nach dem Entfernen von evaluate_open_predictions() blieben nur noch drei
    Aufgaben uebrig, und alle drei erledigt pre_market um 15:00 bereits:
      * cleanup_old_data() -- laeuft dort direkt nach init_schema(),
      * _fill_price_gaps() -- derselbe collect()-Pfad,
      * _persist_indicators() -- mit BYTE-IDENTISCHEN Werten, weil jede
        Indikator-Funktion ausschliesslich `df` bekommt und `df` nur finale
        Tagesbars bis D-1 enthaelt (load_price_history_from_db). Der Live-Kurs
        landet in td["price"] und wird nie nach technical_indicators
        geschrieben -- die Zeile kann sich im Tagesverlauf gar nicht aendern.

    Dazu zwei aktive Nachteile: ein voller Capital.com-Kurs-Sweep ohne
    einzigartigen Output, und ein dritter collect()-Lauf pro Tag, der
    ticker_status.skip_count 1,5x so schnell gegen TICKER_MAX_SKIPS treibt.

    ⚠️ Bewusst kein Substring-Test wie test_workflow_has_no_removed_run_types:
    "close" steckt in "final_close" drin, ein `"close" not in ...` waere
    entweder immer rot oder muesste das echte Signal verschlucken."""
    from main import RUN_TYPES
    assert "close" not in RUN_TYPES
    assert "final_close" in RUN_TYPES, "final_close darf davon nicht betroffen sein"
    assert not hasattr(main, "run_close"), (
        "run_close() ist entfallen -- eine zurueckgebliebene Funktion waere "
        "toter Code, den niemand mehr aufruft")


# ---------- Task 7b (Preismodell): price_open und is_premarket befuellen ----------


def test_premarket_flag_comes_from_the_clock():
    """15:00 Berlin ist 09:00 ET -- eine halbe Stunde VOR der Eroeffnung. Der
    Kurs ist duenn gehandelt und darf in der Analyse nicht als regulaerer Kurs
    behandelt werden.

    Aus der Uhr abgeleitet, nicht aus marketStatus: das Feld meldete am
    2026-08-06 um 08:37 ET TRADEABLE -- mitten in der Vorboerse."""
    from main import _premarket_flag
    assert _premarket_flag("2026-08-05", "2026-08-05T13:00:00") == 1
    assert _premarket_flag("2026-08-05", "2026-08-05T14:10:00") == 0


def test_opening_price_comes_from_the_minute_bar_not_the_day_bar(tmp_db_path, mocker):
    """Der 'Open' der Tagesbar ist NICHT der Eroeffnungskurs: Capital.com laesst
    die Tagesbar um 08:00 UTC beginnen (openingHours, erweiterte Zeiten). Bei
    AAPL am 2026-08-05 lagen beide 0,47 % auseinander -- Tagesbar 310,54 gegen
    tatsaechlicher Open 309,09. Deshalb ein eigener MINUTE-Abruf.

    Entry/TP/SL liegen bewusst auf derselben Kursskala wie der 16:10-Kurs: die
    R/R-Ratio wird in _persist_revision gegen den AKTUELLEN Kurs neu gerechnet,
    und ein Setup mit negativem Reward wuerde vom harten Guardrail zu Recht
    verworfen -- dann entstuende gar keine trade_proposals-Zeile."""
    import pandas as pd
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    _pred_row(conn, ticker="AAPL", entry_price=305.0,
              tp_price=341.0, sl_price=301.0)
    conn.commit(); conn.close()

    mail = _tp_run_mocks(mocker, [{"ticker": "AAPL", "price": 311.0}])
    # _tp_run_mocks hat CapitalComProvider bereits gepatcht -- hier gezielt den
    # Intraday-Abruf nachruesten, den _opening_prices braucht.
    prov = main.CapitalComProvider.return_value
    prov.get_intraday_ohlc.return_value = pd.DataFrame(
        {"Open": [309.09], "High": [309.6], "Low": [307.8],
         "Close": [307.94], "Volume": [431]},
        index=pd.to_datetime(["2026-07-30 13:30:00"]))
    mocker.patch("main.revalidate_one", return_value={
        "verdict": "bestaetigt", "probability_pct": 70, "reason": "ok",
        "entry_window_low": 310.0, "entry_window_high": 312.0})

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    row = conn.execute(
        "SELECT * FROM predictions WHERE run_type='trade_proposals'").fetchone()
    conn.close()
    assert row is not None, "die Ablösezeile muss entstanden sein"
    assert row["price_open"] == 309.09, "der echte Eroeffnungskurs"
    assert row["price_1610"] == 311.0
    assert row["is_premarket"] == 0, "10:10 ET liegt nach der Eroeffnung"


def test_opening_price_stays_null_for_commodities_and_crypto(tmp_db_path, mocker):
    """E6: 24/7-Instrumente haben keinen Eroeffnungskurs. Krypto und Rohstoffe
    handeln durchgehend und haetten um 13:30 UTC selbstverstaendlich eine
    Minutenbar -- nur beschreibt die kein Eroeffnungs-Ereignis. _opening_prices
    darf deshalb nur mit Aktien-Tickern aufgerufen werden; price_open muss fuer
    eine Krypto-/Rohstoff-Zeile aus demselben Lauf NULL bleiben, waehrend die
    Aktienzeile ihren echten Wert bekommt."""
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    _pred_row(conn, ticker="AAPL", entry_price=100.0,
              tp_price=106.0, sl_price=98.0)
    _pred_row(conn, ticker="BTC-USD", asset_class="crypto",
              entry_price=64000.0, tp_price=70000.0, sl_price=62000.0)
    conn.commit(); conn.close()

    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    # Erster collect()-Aufruf liefert die Aktien (sp_tds), der zweite Krypto/
    # Rohstoffe (cc_tds) -- dieselbe Reihenfolge wie in run_trade_proposals.
    mocker.patch("main.collect", side_effect=[
        ([{"ticker": "AAPL", "price": 101.0}], 0, {}),
        ([{"ticker": "BTC-USD", "price": 65000.0}], 0, {}),
    ])
    mocker.patch("main.fetch_market_context", return_value={"vix_level": 18.0})
    mocker.patch("main.collect_sector_momentum", return_value={})
    mocker.patch("main.run_policy_monitor", return_value={"policy_risk_level": "low",
                                                         "events": []})
    mocker.patch("main.check_open_positions", return_value=[])
    mocker.patch("main.send_trade_proposals_email")

    import pandas as pd
    prov = main.CapitalComProvider.return_value
    prov.get_intraday_ohlc.return_value = pd.DataFrame(
        {"Open": [309.09], "High": [309.6], "Low": [307.8],
         "Close": [307.94], "Volume": [431]},
        index=pd.to_datetime(["2026-07-30 13:30:00"]))
    mocker.patch("main.revalidate_one", return_value={
        "verdict": "bestaetigt", "probability_pct": 70, "reason": "ok",
        "entry_window_low": 100.0, "entry_window_high": 102.0})

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    rows = {r["ticker"]: r for r in conn.execute(
        "SELECT * FROM predictions WHERE run_type='trade_proposals'").fetchall()}
    conn.close()
    assert set(rows) == {"AAPL", "BTC-USD"}, "beide Zeilen muessen abgeloest sein"
    assert rows["AAPL"]["price_open"] == 309.09, "Aktie bekommt den echten Open"
    assert rows["BTC-USD"]["price_open"] is None, (
        "24/7-Instrument hat keinen Eroeffnungskurs -- NULL statt erfundenem Wert (E6)")


def test_pre_market_warns_when_the_final_bar_is_missing(in_memory_db):
    """final_close verschickt keine Mail. Faellt er aus, wird nichts mehr
    bewertet -- und niemand merkt es. Deshalb prueft pre_market, ob die finale
    Bar des letzten Handelstags vorliegt."""
    from src import db
    from main import _final_bar_warning
    db.init_schema(in_memory_db)
    db.upsert_price_history(in_memory_db, "AAPL", "2026-08-03",
                            100, 101, 99, 100, 10)

    warn = _final_bar_warning(in_memory_db, date="2026-08-06")
    assert warn is not None and "final_close" in warn

    db.upsert_price_history(in_memory_db, "AAPL", "2026-08-05",
                            100, 101, 99, 100, 10)
    assert _final_bar_warning(in_memory_db, date="2026-08-06") is None


# ---------- Guard: zu duenne Historie bricht ab, statt leer zu laufen ----------

def _seed_full_universe(conn, bars: int):
    """Gibt jedem Universums-Ticker `bars` Tagesbars."""
    from src import db
    from src.universe import full_universe
    for t in full_universe():
        for i in range(bars):
            db.insert_price_bar_if_missing(
                conn, ticker=t, date=f"2026-01-{i + 1:02d}",
                open_=1.0, high=2.0, low=0.5, close=1.5, volume=1, source="t")
    conn.commit()


def test_run_aborts_before_spending_anything_on_thin_history(tmp_db_path, mocker):
    """Option-1-Bootstrap behebt das Problem einmalig; dieser Guard verhindert,
    dass es unbemerkt wiederkehrt (B-12: neuer Ticker ohne Backfill).

    Der Abbruch liegt vor jeder Phase -- ein Lauf, der ohnehin nichts
    persistieren kann, soll keine ~3,30 EUR fuer Trend- und Tiefenanalysen
    ausgeben."""
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn); conn.close()
    pipeline = mocker.patch("main.run_pipeline")
    mocker.patch("main.send_error_email")

    from main import main as cli
    with pytest.raises(SystemExit):
        cli(["--run-type", "pre_market", "--db-path", str(tmp_db_path)])

    pipeline.assert_not_called()


def test_thin_history_abort_names_the_fix(tmp_db_path, mocker):
    """Die Meldung muss den Ausweg nennen — sonst steht man vor demselben
    Raetsel wie am 2026-08-04."""
    from src import db
    from main import _abort_on_thin_history, HistoryTooThinError
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn); conn.close()

    with pytest.raises(HistoryTooThinError) as exc:
        _abort_on_thin_history(str(tmp_db_path))

    assert "historical_loader" in str(exc.value)
    assert "--universe" in str(exc.value)


def test_guard_lets_a_healthy_database_through(tmp_db_path):
    """Der Guard darf den Normalfall nicht anfassen."""
    from src import db
    from src.data_collector import MIN_BARS_RSI
    from main import _abort_on_thin_history
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    _seed_full_universe(conn, MIN_BARS_RSI + 1)
    conn.close()

    _abort_on_thin_history(str(tmp_db_path))  # darf nicht werfen


def test_guard_tolerates_a_minority_of_thin_tickers(tmp_db_path):
    """Einzelne zickende Ticker sind Normalbetrieb — dafuer gibt es
    skipped_tickers und die Deaktivierung, keinen Laufabbruch."""
    from src import db
    from src.data_collector import MIN_BARS_RSI
    from src.universe import full_universe
    from main import _abort_on_thin_history
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    _seed_full_universe(conn, MIN_BARS_RSI + 1)
    conn.execute("DELETE FROM price_history WHERE ticker = ?",
                 (full_universe()[0],))
    conn.commit(); conn.close()

    _abort_on_thin_history(str(tmp_db_path))  # darf nicht werfen


@pytest.mark.parametrize("run_type", ["final_close", "weekly"])
def test_guard_exempts_run_types_that_do_not_need_history(run_type):
    """final_close schreibt die Historie selbst -- ein Guard dort verhinderte
    die Selbstheilung. weekly berichtet nur; beide sollen auch bei duenner
    Historie laufen. (close stand hier bis 2026-08-18 und ist als Run-Type
    entfallen -- s. test_close_is_a_removed_run_type.)"""
    from main import _RUN_TYPES_NEEDING_HISTORY
    assert run_type not in _RUN_TYPES_NEEDING_HISTORY


def test_signal_context_bundles_tech_signal_and_c1_indicators():
    from main import _signal_context
    tds = [{"ticker": "AAPL", "atr_pct": 2.5, "rsi_14": 55.0,
            "volume_ratio": 0.9, "earnings_in_days": 3}]
    sidecar = {"AAPL": {"tech_direction": "long", "tech_agreement": 2,
                        "tech_adx_band": "normal", "tech_strength": 3}}
    ctx = _signal_context(tds, sidecar, news_strength_by_ticker={"AAPL": 2})
    assert ctx["AAPL"] == {
        "tech_direction": "long", "tech_agreement": 2,
        "tech_adx_band": "normal", "tech_strength": 3,
        "atr_pct": 2.5, "rsi_14": 55.0, "volume_ratio": 0.9,
        "earnings_in_days": 3, "news_strength": 2,
    }


def test_signal_context_defaults_news_strength_to_none_without_a_map():
    from main import _signal_context
    tds = [{"ticker": "GC=F", "atr_pct": None, "rsi_14": None,
            "volume_ratio": None, "earnings_in_days": None}]
    ctx = _signal_context(tds, {})
    assert ctx["GC=F"]["news_strength"] is None
    assert ctx["GC=F"]["tech_direction"] is None


def test_run_pipeline_passes_signal_context_to_ranking(tmp_db_path, mocker):
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mock_rank = mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })
    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))
    assert "signal_context" in mock_rank.call_args.kwargs


def test_load_recent_outcomes_aggregate_separates_divergence(tmp_db_path):
    from main import load_recent_outcomes_aggregate
    from src import db
    conn = db.connect(str(tmp_db_path))
    db.init_schema(conn)
    core_id = db.save_prediction(conn, {
        "date": "2026-08-16", "run_type": "pre_market", "ticker": "AAPL",
        "direction": "long", "entry_price": 100.0, "tp_price": 105.0,
        "sl_price": 98.0, "rr_ratio": 2.5, "candidate_class": "core",
    })
    conn.execute(
        """INSERT INTO outcomes (prediction_id, direction, evaluated_date,
                                  correct_direction_eod, profit_loss_eur)
           VALUES (?, 'long', '2026-08-17', 1, 15.0)""", (core_id,))
    div_id = db.save_prediction(conn, {
        "date": "2026-08-16", "run_type": "pre_market", "ticker": "GC=F",
        "direction": "long", "entry_price": 2000.0, "tp_price": 2050.0,
        "sl_price": 1980.0, "rr_ratio": 2.5, "candidate_class": "divergence",
    })
    conn.execute(
        """INSERT INTO outcomes (prediction_id, direction, evaluated_date,
                                  correct_direction_eod, profit_loss_eur)
           VALUES (?, 'long', '2026-08-17', 0, -20.0)""", (div_id,))
    conn.commit()

    agg = load_recent_outcomes_aggregate(conn, today="2026-08-17")
    assert agg["long_total"] == 1
    assert agg["total_pl_eur"] == 15.0
    assert agg["divergence_summary"]["long_total"] == 1
    assert agg["divergence_summary"]["total_pl_eur"] == -20.0
    conn.close()
