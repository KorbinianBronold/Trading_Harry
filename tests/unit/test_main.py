import argparse
from unittest.mock import patch, MagicMock
import pytest

from main import (
    run_pipeline, run_evaluate, run_weekly, run_close, parse_args, build_commodity_crypto_inputs,
)
import config


def test_parse_args_accepts_all_run_types():
    for rt in ["pre_market", "midday", "close", "evaluate", "weekly"]:
        ns = parse_args(["--run-type", rt])
        assert ns.run_type == rt


def test_parse_args_rejects_unknown_run_type():
    with pytest.raises(SystemExit):
        parse_args(["--run-type", "noon"])


def test_build_commodity_crypto_inputs_combines_config_maps():
    inputs = build_commodity_crypto_inputs()
    tickers = {d["ticker"] for d in inputs}
    expected = set(config.COMMODITY_TICKERS.values()) | set(config.CRYPTO_TICKERS.values())
    assert tickers == expected


def test_run_pipeline_calls_phases_in_order():
    """Smoke-mock every phase and assert the call order."""
    call_log: list[str] = []

    def make_mock(name: str, return_value):
        def _fn(*a, **kw):
            call_log.append(name)
            return return_value
        return _fn

    fake_trends = {"trends": [{"name": "x"}], "trend_summary": "ok"}
    fake_policy = {"policy_risk_level": "low", "events": []}
    fake_collect = ([{"ticker": "AAPL", "intraday_range_pct": 1.5, "price": 178.0}], 0)
    fake_quick = [{"ticker": "AAPL", "exclude": False, "long_score": 7.0,
                   "short_score": 2.0, "confidence": "high", "evidence": []}]
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
    fake_portfolio = []
    fake_ranking = {"top_long": fake_deep, "top_short": [],
                    "commodities_crypto": []}

    patches = [
        patch("main.analyze_trends", side_effect=make_mock("trend", fake_trends)),
        patch("main.collect", side_effect=make_mock("collect", fake_collect)),
        patch("main.quick_filter_batch",
              side_effect=make_mock("quick_filter", fake_quick)),
        patch("main.run_policy_monitor",
              side_effect=make_mock("policy", fake_policy)),
        patch("main.analyze_assets",
              side_effect=make_mock("deep", fake_deep)),
        patch("main.analyze_commodities_and_crypto",
              side_effect=make_mock("cc", fake_cc)),
        patch("main.check_open_positions",
              side_effect=make_mock("portfolio", fake_portfolio)),
        patch("main.rank_and_persist",
              side_effect=make_mock("ranking", fake_ranking)),
        patch("main.fetch_fear_greed", return_value={"value": 50, "label": "Neutral"}),
        patch("main.send_daily_email", side_effect=make_mock("email", None)),
        patch("main.YFinanceProvider"),
        patch("main.FinnhubProvider"),
    ]
    with patches[0], patches[1], patches[2], patches[3], patches[4], \
         patches[5], patches[6], patches[7], patches[8], patches[9], \
         patches[10], patches[11]:
        run_pipeline(run_type="close", date="2026-05-19", db_path=":memory:")

    assert call_log == [
        "trend", "collect", "collect", "quick_filter", "policy",
        "deep", "cc", "portfolio", "ranking", "email",
    ]


def test_run_pipeline_aborts_when_trend_fails(tmp_db_path):
    from src.trend_analyzer import TrendAnalyzerError
    with patch("main.analyze_trends", side_effect=TrendAnalyzerError("no trends")), \
         patch("main.send_daily_email") as mock_email, \
         patch("main.YFinanceProvider"), patch("main.FinnhubProvider"):
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
         patch("main.collect", return_value=([], 0)), \
         patch("main.quick_filter_batch", return_value=[]), \
         patch("main.run_policy_monitor",
               side_effect=CostCapExceeded("cap hit")), \
         patch("main.send_daily_email") as mock_email, \
         patch("main.YFinanceProvider"), patch("main.FinnhubProvider"):
        run_pipeline(run_type="close", date="2026-05-19", db_path=str(tmp_db_path))
    # Email IS sent with the partial payload + abort warning
    args = mock_email.call_args.kwargs
    assert args["payload"]["cost_summary"]["aborted_at_phase"] == "policy_monitor"


def test_run_evaluate_calls_evaluator_no_email(tmp_db_path):
    with patch("main.evaluate_open_predictions", return_value=3) as mock_eval, \
         patch("main.send_daily_email") as mock_email, \
         patch("main.YFinanceProvider"):
        run_evaluate(date="2026-05-19", db_path=str(tmp_db_path))
    mock_eval.assert_called_once()
    mock_email.assert_not_called()


def test_run_weekly_calls_send_weekly_email(tmp_db_path):
    with patch("main.send_weekly_email") as mock_send, \
         patch("main.load_recent_outcomes_aggregate",
               return_value={"long_correct": 0, "long_total": 0,
                             "long_avg_pl": 0.0, "short_correct": 0,
                             "short_total": 0, "short_avg_pl": 0.0,
                             "total_pl_eur": 0.0, "trades": []}):
        run_weekly(date="2026-05-24", db_path=str(tmp_db_path))
    mock_send.assert_called_once()


def test_close_run_does_not_call_claude(tmp_db_path, mocker):
    """Close run must not invoke Claude or send email."""
    mock_claude = mocker.patch("src.utils.call_claude")
    mocker.patch("src.email_sender._send")
    mock_evaluate = mocker.patch("main.evaluate_open_predictions", return_value=0)

    run_close(date="2026-05-21", db_path=str(tmp_db_path))

    mock_claude.assert_not_called()
    mock_evaluate.assert_called_once()


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
    mocker.patch.object(m, "run_evaluate")
    with freeze_time("2026-05-21T23:30:00+00:00"):
        m.main(["--run-type", "evaluate", "--db-path", str(tmp_db_path)])
        call_date = m.run_evaluate.call_args[1]["date"]
    assert call_date == "2026-05-22", f"Expected Berlin date 2026-05-22, got {call_date}"


def test_position_check_calls_get_open_positions(tmp_db_path, mocker):
    """position_check must call get_open_positions on Capital.com."""
    mocker.patch("main.config.CAPITAL_COM_API_KEY", "test-key")
    mock_capital = mocker.MagicMock()
    mock_capital.get_open_positions.return_value = []
    mocker.patch("main.CapitalComProvider", return_value=mock_capital)
    mocker.patch("src.utils.call_claude")
    mocker.patch("src.email_sender._send")

    from main import run_position_check
    run_position_check(date="2026-05-21", db_path=str(tmp_db_path))
    mock_capital.get_open_positions.assert_called_once()


def test_position_check_always_sends_email(tmp_db_path, mocker):
    mocker.patch("main.config.CAPITAL_COM_API_KEY", "test-key")
    mock_capital = mocker.MagicMock()
    mock_capital.get_open_positions.return_value = []
    mocker.patch("main.CapitalComProvider", return_value=mock_capital)
    mocker.patch("src.utils.call_claude")
    mock_send = mocker.patch("src.email_sender._send")

    from main import run_position_check
    run_position_check(date="2026-05-21", db_path=str(tmp_db_path))
    mock_send.assert_called_once()
