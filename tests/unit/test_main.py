import argparse
from unittest.mock import patch, MagicMock
import pytest

from main import (
    run_pipeline, run_weekly, run_close, parse_args, build_commodity_crypto_inputs,
)
import config


def test_parse_args_accepts_all_run_types():
    for rt in ["pre_market", "trade_proposals", "close", "weekly"]:
        ns = parse_args(["--run-type", rt])
        assert ns.run_type == rt


@pytest.mark.parametrize("removed", ["midday", "evaluate", "position_check"])
def test_parse_args_rejects_removed_run_types(removed):
    """B.1: die drei Run-Types sind vollstaendig entfernt, keine Leichen."""
    with pytest.raises(SystemExit):
        parse_args(["--run-type", removed])


def test_main_dispatches_trade_proposals(mocker):
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
    fake_market_ctx = {"vix_level": 18.0, "vix_source": "capital.com",
                       "advance_decline_ratio": 1.2, "market_regime": "risk_on",
                       "sector_rotation_in": None, "sector_rotation_out": None,
                       "macro_summary": None}

    mocker.patch("main.analyze_trends", side_effect=make_mock("trend", fake_trends))
    mocker.patch("main.collect", side_effect=make_mock("collect", fake_collect))
    mocker.patch("main.quick_filter_batch",
                 side_effect=make_mock("quick_filter", fake_quick))
    mocker.patch("main.run_policy_monitor",
                 side_effect=make_mock("policy", fake_policy))
    mocker.patch("main.analyze_assets", side_effect=make_mock("deep", fake_deep))
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
    fake_ranking = {"top_long": [], "top_short": [], "commodities_crypto": []}
    mocker.patch("main.rank_and_persist",
                 side_effect=lambda **kw: call_log.append("ranking") or fake_ranking)
    mocker.patch("main.check_open_positions",
                 side_effect=lambda **kw: call_log.append("portfolio") or [])

    run_pipeline(run_type="close", date="2026-05-19", db_path=":memory:")

    assert call_log == [
        "trend", "market_context", "collect", "collect", "quick_filter", "policy",
        "deep", "cc", "ranking", "portfolio", "email",
    ]


def test_ranking_runs_before_portfolio_check(mocker):
    """B.5: Phase 4 vor Phase 4a. Phase 4a soll auf den fertigen
    Phase-3-Analysen arbeiten, nicht auf Rohsnapshots."""
    order: list[str] = []
    mocker.patch("main.rank_and_persist",
                 side_effect=lambda **kw: order.append("ranking") or
                 {"top_long": [], "top_short": [], "commodities_crypto": []})
    mocker.patch("main.check_open_positions",
                 side_effect=lambda **kw: order.append("portfolio") or [])
    # uebrige Phasen wie in test_run_pipeline_calls_phases_in_order mocken
    _mock_all_other_phases(mocker)
    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-30", db_path=":memory:")
    assert order == ["ranking", "portfolio"]


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
         patch("main.collect", return_value=([], 0)), \
         patch("main.quick_filter_batch", return_value=[]), \
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
    # Vehikel ist seit Plan 2 trade_proposals statt evaluate — geprueft wird
    # weiterhin die Timezone-Ableitung, nicht der Run-Type.
    mocker.patch.object(m, "run_trade_proposals")
    with freeze_time("2026-05-21T23:30:00+00:00"):
        m.main(["--run-type", "trade_proposals", "--db-path", str(tmp_db_path)])
        call_date = m.run_trade_proposals.call_args[1]["date"]
    assert call_date == "2026-05-22", f"Expected Berlin date 2026-05-22, got {call_date}"




# ---------- Markt-Kontext in der Pipeline (Sprint 3B / Plan 1, Task 11) ----------


def _stub_pipeline(mocker) -> None:
    """Legt alle Phasen ausser dem Markt-Kontext still, damit die Tests unten
    nur dessen Verdrahtung pruefen."""
    mocker.patch("main.analyze_trends", return_value={"trends": []})
    mocker.patch("main.collect", return_value=([], 0))
    mocker.patch("main.quick_filter_batch", return_value=[])
    mocker.patch("main.run_policy_monitor", return_value={})
    mocker.patch("main.analyze_assets", return_value=[])
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
    mocker.patch("main.analyze_assets", side_effect=CostCapExceeded("cap hit"))

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
    ("main.quick_filter_batch",            "quick_filter"),
    ("main.run_policy_monitor",            "policy_monitor"),
    ("main.analyze_assets",                "deep_analysis"),
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
    collect_mock = mocker.patch("main.collect", return_value=([], 0))
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
    mocker.patch("main.collect", return_value=([], 0))
    _stub_trade_proposals_side_phases(mocker)
    send = mocker.patch("main.send_trade_proposals_email")

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    send.assert_called_once()


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


def test_forced_candidates_override_quick_filter_exclude():
    """Der Kern von B.4: ein Ticker mit offener Position darf nicht am
    Quick-Filter haengenbleiben."""
    from main import _apply_forced_candidates
    quick = [{"ticker": "AAPL", "exclude": True},
             {"ticker": "MSFT", "exclude": True}]
    out = _apply_forced_candidates(quick, forced={"AAPL"})
    by_t = {q["ticker"]: q for q in out}
    assert by_t["AAPL"]["exclude"] is False
    assert by_t["MSFT"]["exclude"] is True


def test_forced_candidate_reaches_deep_analysis_with_exclude_false(tmp_db_path, mocker):
    """Integrationstest fuer B.4: eine offene Capital.com-Position auf AAPL, die
    der Quick-Filter eigentlich ausschliessen wollte, muss trotzdem mit
    exclude=False bei analyze_assets (Phase 3) ankommen — sonst greift Phase 1c
    nicht bis in die Tiefenanalyse durch, obwohl echtes Geld daran haengt."""
    _stub_pipeline(mocker)
    mocker.patch("main.fetch_market_context", return_value=dict(_CTX))
    mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
    })

    provider = MagicMock()
    provider.get_open_positions.return_value = [{"ticker": "AAPL"}]
    mocker.patch("main.CapitalComProvider", return_value=provider)

    mocker.patch("main.quick_filter_batch", return_value=[
        {"ticker": "AAPL", "exclude": True, "long_score": 1.0, "short_score": 1.0,
         "confidence": "low", "evidence": []},
    ])
    mock_deep = mocker.patch("main.analyze_assets", return_value=[])

    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))

    passed_quick = mock_deep.call_args.kwargs["quick_filter_results"]
    by_ticker = {q["ticker"]: q for q in passed_quick}
    assert by_ticker["AAPL"]["exclude"] is False


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
                 side_effect=lambda **kw: order.append("collect") or ([], 0))
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
    mocker.patch("main.collect", return_value=([], 0))
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
    mocker.patch("main.collect", return_value=([{"ticker": "AAPL", "price": 101.0}], 0))
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
    mocker.patch("main.collect", return_value=([{"ticker": "AAPL", "price": 101.0}], 0))
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
    mocker.patch("main.collect", return_value=([], 0))
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
    mocker.patch("main.collect", return_value=([], 0))
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
    out = _revalidate_all(
        conn=conn, date="2026-07-30", snapshots={"AAPL": {"price": 101.0}},
        sector_mom={}, market_ctx={"vix_level": 18.0}, policy_context={},
        cost_tracker=CostTracker(),
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
    mocker.patch("main.collect", return_value=([{"ticker": "AAPL", "price": 104.0}], 0))
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
