import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

import config
from src import db
from src.cost_tracker import CostTracker
from src.portfolio_check import (
    check_open_positions, check_one_position, PortfolioCheckError,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def _fake_result(text: str, stop_reason: str | None = "end_turn") -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 3000
    r.output_tokens = 2000
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = config.CLAUDE_MODEL_SONNET  # C.46: 4a laeuft auf Sonnet 5
    r.web_search_calls = 0
    r.stop_reason = stop_reason
    return r


# Seit C.46 laeuft der Call ueber utils.call_claude_retry_on_truncation, das
# intern src.utils.call_claude ruft -- dort wird gepatcht.
CALL = "src.utils.call_claude"

# Pflichtparameter seit C.46 / F47 (Datumsanker).
WHEN = {"date": "2026-09-15", "run_type": "pre_market"}


def _make_open_prediction(conn, date: str = "2026-05-18", ticker: str = "AAPL") -> int:
    return db.save_prediction(conn, {
        "date": date, "run_type": "close", "asset_class": "stock",
        "ticker": ticker, "direction": "long",
        "entry_price": 178.0, "tp_price": 184.0, "tp_pct": 3.4,
        "sl_price": 176.0, "sl_pct": 1.1, "rr_ratio": 3.0,
        "total_score": 7.8, "probability_pct": 68, "confidence": "high",
        "score_market_env": 7.0, "score_company": 8.0, "score_valuation": 6.0,
        "score_momentum": 8.0, "score_risk": 6.0, "score_sector": 7.0,
        "score_catalyst": 7.0, "score_policy": 6.0,
        "atr_pct": 1.8, "rsi_at_entry": 58.0, "volume_ratio": 1.15,
        "market_regime": "risk_on", "vix_at_prediction": 14.0,
        "sector": "Technology", "trend_boost": "ai-capex",
        "earnings_warning": False, "summary": "AAPL long thesis",
        "learnable": True, "hold_days_recommended": 2,
        "intraday_range_pct": 1.4,
    })


def _position(**overrides) -> dict:
    """Eine offene Capital.com-Position, wie main._open_broker_positions() sie
    liefert (C.37): Broker-Felder plus epic/ticker."""
    base = {
        "deal_id": "d-aapl-1", "epic": "AAPL", "ticker": "AAPL", "direction": "long",
        "entry_price": 178.0, "current_price": 181.2, "tp_price": 184.0,
        "sl_price": 176.0, "size": 1, "profit_loss": 3.2,
        "opened_at": "2026-05-18T14:30:00", "status": "open",
    }
    base.update(overrides)
    return base


def _snapshot(ticker: str = "AAPL", price: float = 181.2) -> dict:
    return {"ticker": ticker, "price": price, "rsi_14": 60.0,
            "macd_signal": "bullish", "atr_pct": 1.8, "intraday_range_pct": 1.5}


def _ctx():
    return {"trend_summary": "risk-on"}, {"policy_risk_level": "low", "events": []}


def test_check_one_position_returns_parsed():
    payload = (FIXTURE_DIR / "mock_portfolio_check_response.json").read_text()
    trend, policy = _ctx()
    with patch(CALL, return_value=_fake_result(payload)):
        out = check_one_position(
            position=_position(), current_snapshot=_snapshot(),
            trend_context=trend, policy_context=policy,
            cost_tracker=CostTracker(hard_cap_eur=10.0), **WHEN,
        )
    assert out["action"] == "ANPASSEN"
    assert out["new_sl_price"] == 178.5


def test_check_one_position_sends_the_position_not_a_prediction():
    """C.37: Claude bekommt die Broker-Position (Einstieg, TP/SL, P&L, Alter),
    keine Prediction und keine Ursprungsthese -- Positionen und Predictions
    sind getrennte Welten."""
    payload = (FIXTURE_DIR / "mock_portfolio_check_response.json").read_text()
    trend, policy = _ctx()
    with patch(CALL, return_value=_fake_result(payload)) as call:
        check_one_position(
            position=_position(), current_snapshot=_snapshot(),
            trend_context=trend, policy_context=policy,
            cost_tracker=CostTracker(hard_cap_eur=10.0), **WHEN,
        )
    user_msg = call.call_args.kwargs["user"]
    assert "OPEN POSITION" in user_msg and '"deal_id": "d-aapl-1"' in user_msg
    assert '"profit_loss": 3.2' in user_msg
    assert "ORIGINAL PREDICTION" not in user_msg


def test_check_open_positions_writes_position_check_rows(in_memory_db):
    db.init_schema(in_memory_db)
    payload = (FIXTURE_DIR / "mock_portfolio_check_response.json").read_text()
    trend, policy = _ctx()
    with patch(CALL, return_value=_fake_result(payload)):
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            positions=[_position()], analyses_by_ticker={"AAPL": _snapshot()},
            trend_context=trend, policy_context=policy,
            cost_tracker=CostTracker(hard_cap_eur=10.0),
        )
    rows = in_memory_db.execute(
        "SELECT deal_id, ticker, action, new_sl_price, profit_loss FROM position_checks"
    ).fetchall()
    assert len(rows) == 1 and rows[0]["deal_id"] == "d-aapl-1"
    assert rows[0]["action"] == "ANPASSEN" and rows[0]["profit_loss"] == 3.2
    assert len(out) == 1


def test_check_open_positions_lists_positions_without_analysis_without_a_call(in_memory_db):
    """Fremdposition (kein Ticker im Universum) oder Ticker ohne aktuelle
    Analyse: kein Claude-Call, keine Persistierung -- aber eine Zeile fuer die
    Mail, damit die Position nicht unsichtbar bleibt."""
    db.init_schema(in_memory_db)
    positions = [_position(deal_id="d-x", epic="PPHE", ticker=None),
                 _position(deal_id="d-y", epic="MSFT", ticker="MSFT")]
    with patch(CALL) as call:
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            positions=positions, analyses_by_ticker={},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0),
        )
    call.assert_not_called()
    assert [r["action"] for r in out] == ["KEINE ANALYSE", "KEINE ANALYSE"]
    assert out[0]["epic"] == "PPHE" and out[1]["ticker"] == "MSFT"
    assert in_memory_db.execute("SELECT COUNT(*) FROM position_checks").fetchone()[0] == 0


def test_check_open_positions_returns_empty_when_positions_unavailable(in_memory_db):
    """None = Abruf gescheitert: keine Empfehlungen, kein Call (die Mail zeigt
    den Ausfall ueber payload['positions_unavailable'])."""
    db.init_schema(in_memory_db)
    with patch(CALL) as call:
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            positions=None, analyses_by_ticker={"AAPL": _snapshot()},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0),
        )
    assert out == []
    call.assert_not_called()


def test_check_open_positions_returns_empty_when_no_open(in_memory_db):
    db.init_schema(in_memory_db)
    out = check_open_positions(
        conn=in_memory_db, today="2026-05-20", run_type="pre_market",
        positions=[], analyses_by_ticker={}, trend_context={}, policy_context={},
        cost_tracker=CostTracker(hard_cap_eur=10.0),
    )
    assert out == []


def test_check_open_positions_never_reads_predictions(in_memory_db):
    """C.37, die Trennung: eine offene Prediction ist KEINE Position. Ohne
    Capital.com-Position gibt es keinen Portfolio-Check, egal was in
    `predictions` steht -- die laeuft getrennt durch die mehrtaegige Auswertung."""
    db.init_schema(in_memory_db)
    _make_open_prediction(in_memory_db, date="2026-05-19", ticker="AAPL")
    with patch(CALL) as call:
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            positions=[], analyses_by_ticker={"AAPL": _snapshot()},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0),
        )
    assert out == []
    call.assert_not_called()


def test_check_one_position_raises_on_invalid_json():
    with patch(CALL, return_value=_fake_result("not json")):
        with pytest.raises(PortfolioCheckError):
            check_one_position(
                position=_position(), current_snapshot=_snapshot(),
                trend_context={}, policy_context={},
                cost_tracker=CostTracker(hard_cap_eur=10.0), **WHEN,
            )


def test_check_open_positions_continues_after_single_failure(in_memory_db):
    db.init_schema(in_memory_db)
    good = json.loads((FIXTURE_DIR / "mock_portfolio_check_response.json").read_text())
    # Levels zur MSFT-Position (Kurs 410): seit C.46 / F51 prueft der Code die
    # Seite, die AAPL-Fixture-Levels (178.5 / 184.0) wuerden herabgestuft.
    good.update({"ticker": "MSFT", "deal_id": "d-msft-1",
                 "new_sl_price": 405.0, "new_tp_price": 420.0})
    side_effects = [_fake_result("bad"), _fake_result(json.dumps(good))]
    positions = [_position(), _position(deal_id="d-msft-1", epic="MSFT", ticker="MSFT",
                                        entry_price=400.0, current_price=410.0)]
    with patch(CALL, side_effect=side_effects):
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            positions=positions,
            analyses_by_ticker={"AAPL": _snapshot(), "MSFT": _snapshot("MSFT", 410.0)},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0),
        )
    # C.46 / F53: die gescheiterte Position verschwindet nicht mehr aus der
    # Mail, sie steht als NICHT GEPRUEFT mit dem Fehlergrund drin.
    assert [r["action"] for r in out] == ["NICHT GEPRUEFT", "ANPASSEN"]
    assert out[1]["ticker"] == "MSFT"
    assert "fehlgeschlagen" in out[0]["reason"]


def test_check_open_positions_enriches_with_position_fields(in_memory_db):
    """Der Mail-Renderer braucht Ticker, Richtung, Einstieg, aktuellen Kurs und
    P&L -- die kommen aus der Position, nicht aus der Claude-Antwort."""
    db.init_schema(in_memory_db)
    raw = json.dumps({"deal_id": "d-aapl-1", "ticker": "AAPL", "action": "HALTEN",
                      "reason": "kein neuer Katalysator", "new_sl_price": None,
                      "new_tp_price": None, "market_context_changed": False})
    with patch(CALL, return_value=_fake_result(raw)):
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            positions=[_position()], analyses_by_ticker={"AAPL": _snapshot()},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0),
        )
    assert len(out) == 1
    r = out[0]
    assert (r["ticker"], r["direction"], r["entry_price"]) == ("AAPL", "long", 178.0)
    assert r["current_price"] == 181.2 and r["profit_loss"] == 3.2 and r["deal_id"] == "d-aapl-1"
    assert r["action"] == "HALTEN"


def test_check_one_position_uses_no_web_search(mocker):
    """B.5: der Portfolio-Check verzichtet auf eine eigene Websuche — die
    Phase-3-Analyse hat die Recherche bereits bezahlt."""
    call = mocker.patch(CALL)
    call.return_value = MagicMock(
        text='{"action": "HALTEN", "reason": "ok"}',
        model=config.CLAUDE_MODEL_HAIKU, input_tokens=10, output_tokens=5,
        cache_read_tokens=0, cache_creation_tokens=0, web_search_calls=0,
    )
    from src.portfolio_check import check_one_position
    from src.cost_tracker import CostTracker
    check_one_position(
        position=_position(), current_snapshot={"ticker": "AAPL"},
        trend_context={}, policy_context={}, cost_tracker=CostTracker(), **WHEN,
    )
    assert call.call_args.kwargs["tools"] == []


# ---------- Prompt und Aufruf muessen zusammenpassen (Review 2026-08-06) ----------


def test_prompt_does_not_ask_for_a_tool_the_call_never_provides():
    """B.5 hat web_search entfernt (`tools=[]`), der Prompt verlangte sie weiter.

    Damit bekam das Modell eine Anweisung, die es nur durch Erfinden erfuellen
    kann: 'You may use web_search up to 3 times', dazu 'sources_used: >= 2
    distinct domains, even for HALTEN' -- und im selben Prompt 'Never invent
    prices or URLs'. Zwei Regeln, die sich ohne Werkzeug ausschliessen.

    Das ist kein Schoenheitsfehler: `reason` wird persistiert und steht als
    ERSTE Sektion in der Tagesmail. Was das Modell unter diesem Druck
    zusammenreimt, liest der Nutzer als Begruendung fuer eine Halte- oder
    Schliessen-Empfehlung."""
    from src.portfolio_check import SYSTEM_PROMPT

    assert "web_search" not in SYSTEM_PROMPT, (
        "Der Prompt nennt weiterhin web_search, obwohl tools=[] uebergeben wird")
    assert "sources_used" not in SYSTEM_PROMPT, (
        "Ohne Websuche kann das Modell keine Quellen belegen -- die Pflicht "
        "erzeugt nur erfundene URLs")
    assert "distinct domains" not in SYSTEM_PROMPT


def test_prompt_still_carries_the_rules_that_do_not_depend_on_tools():
    """Die Entschaerfung darf den Rest nicht mitnehmen: die drei Aktionen, die
    Intraday-Vorgabe und das Verbot erfundener Preise gelten unveraendert."""
    from src.portfolio_check import SYSTEM_PROMPT

    for needle in ("HALTEN", "SCHLIESSEN", "ANPASSEN",
                   "market_context_changed", "HORIZON", "Never invent prices"):
        assert needle in SYSTEM_PROMPT, f"'{needle}' fehlt im Prompt"


def test_prompt_speaks_of_positions_not_predictions():
    """C.37: der Prompt bewertet eine Capital.com-Position, keine Prediction.
    Regel 15: prediction_id und 'original thesis' duerfen nicht mehr vorkommen,
    deal_id muss (der Parser-Schluessel, den die Persistierung liest)."""
    from src.portfolio_check import SYSTEM_PROMPT
    assert "deal_id" in SYSTEM_PROMPT
    assert "prediction_id" not in SYSTEM_PROMPT
    assert "original thesis" not in SYSTEM_PROMPT
    assert "predicted at most" not in SYSTEM_PROMPT


# ---------- C.46: Phase-4a-Review (F47-F53) ----------

def test_user_message_starts_with_the_date_anchor():
    """F47: wie F22/F33 -- ohne Datum kann das Modell weder das Alter der
    Position (opened_at) noch 'heute' einordnen, und 'at market open' stimmt
    nur um 15:00."""
    payload = (FIXTURE_DIR / "mock_portfolio_check_response.json").read_text()
    with patch(CALL, return_value=_fake_result(payload)) as call:
        check_one_position(
            position=_position(), current_snapshot=_snapshot(),
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0),
            date="2026-09-15", run_type="trade_proposals",
        )
    user_msg = call.call_args.kwargs["user"]
    assert user_msg.startswith("Today is 2026-09-15. Run type: trade_proposals.")


def test_build_snapshot_has_three_blocks_and_only_whitelisted_keys():
    """F48: ein deterministischer Payload in beiden Laeufen -- Technik aus td,
    Technik-Signal aus dem Sidecar, Analyse aus Phase 3. Nichts anderes
    (is_premarket, sources_used, ... bleiben draussen, C.6)."""
    from src.portfolio_check import build_snapshot
    td = {"ticker": "AAPL", "price": 181.2, "rsi_14": 60.0, "rsi_trend": "rising",
          "macd_signal": "bullish", "above_sma50": 2.1, "above_sma200": 9.0,
          "above_sma20": 1.0, "bb_position": 0.8, "atr_pct": 1.8,
          "intraday_range_pct": 1.5, "volume_ratio": 1.1, "earnings_in_days": 20,
          "price_change_1d": 0.4, "price_change_5d": 1.2,
          "pe_ratio": 30.0, "data_quality": "high", "sector": "Technology"}
    tech = {"tech_direction": "long", "tech_agreement": 3, "tech_adx_band": "normal",
            "tech_strength": 3, "premarket_change_pct": 0.2}
    analysis = {"ticker": "AAPL", "direction": "long", "confidence": "medium",
                "probability_pct": 60, "summary": "s", "signal_consistency_check": "ok",
                "scores": {"momentum": {"value": 7.0, "evidence": ["a", "b"],
                                        "evidence_quality": "ok"}},
                "tp_price": 184.0, "sl_price": 176.0, "rr_ratio": 1.9,
                "sources_used": ["x"], "is_premarket": 1, "total_score": 7.1}
    snap = build_snapshot(td, tech, analysis)
    assert set(snap) == {"technicals", "technical_signal", "analysis"}
    assert snap["technicals"]["rsi_14"] == 60.0
    assert "pe_ratio" not in snap["technicals"] and "data_quality" not in snap["technicals"]
    assert snap["technical_signal"] == {"direction": "long", "strength": 3}
    assert snap["analysis"]["scores"]["momentum"]["evidence"] == ["a", "b"]
    assert snap["analysis"]["tp_price"] == 184.0
    for key in ("sources_used", "is_premarket", "total_score", "ticker"):
        assert key not in snap["analysis"]


def test_build_snapshot_drops_levels_of_an_abstention():
    """F49: TP/SL einer direction='none'-Analyse sind Schema-Pflichtzahlen ohne
    Bedeutung -- Haiku las sie im Walkthrough als 'downside bias'."""
    from src.portfolio_check import build_snapshot
    analysis = {"direction": "none", "confidence": "low", "summary": "s",
                "tp_price": 4230.0, "sl_price": 4325.0, "rr_ratio": 1.5, "scores": {}}
    snap = build_snapshot({"price": 4290.0}, None, analysis)
    assert snap["analysis"]["direction"] == "none"
    for key in ("tp_price", "sl_price", "rr_ratio"):
        assert key not in snap["analysis"]
    assert snap["technical_signal"] is None


def test_build_snapshot_without_analysis_is_the_1610_shape():
    from src.portfolio_check import build_snapshot
    snap = build_snapshot({"price": 100.0}, {"tech_direction": "neutral", "tech_strength": 0}, None)
    assert snap["analysis"] is None
    assert snap["technical_signal"] == {"direction": "neutral", "strength": 0}


def test_check_open_positions_calls_with_technicals_even_without_an_analysis(in_memory_db):
    """F48: um 16:10 gibt es keine Phase 3 -- der Check laeuft auf Technik plus
    Policy. KEINE ANALYSE bleibt fuer Positionen ohne jeden Snapshot."""
    db.init_schema(in_memory_db)
    raw = json.dumps({"deal_id": "d-aapl-1", "ticker": "AAPL", "action": "HALTEN",
                      "reason": "ok", "new_sl_price": None, "new_tp_price": None,
                      "market_context_changed": False})
    with patch(CALL, return_value=_fake_result(raw)) as call:
        out = check_open_positions(
            conn=in_memory_db, today="2026-09-15", run_type="trade_proposals",
            positions=[_position(), _position(deal_id="d-x", epic="MSFT", ticker="MSFT")],
            analyses_by_ticker={},
            tds_by_ticker={"AAPL": _snapshot()},
            signal_by_ticker={"AAPL": {"tech_direction": "long", "tech_strength": 2}},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0),
        )
    assert call.call_count == 1
    user_msg = call.call_args.kwargs["user"]
    assert '"technicals"' in user_msg and '"analysis": null' in user_msg
    assert '"strength": 2' in user_msg
    assert [r["action"] for r in out] == ["HALTEN", "KEINE ANALYSE"]


def test_user_message_carries_no_stray_analysis_keys(in_memory_db):
    """Der C.6-Nebenbefund aus C.45: is_premarket und sources_used reisten ueber
    das Original-Dict in den bezahlten Prompt."""
    db.init_schema(in_memory_db)
    raw = json.dumps({"deal_id": "d-aapl-1", "ticker": "AAPL", "action": "HALTEN",
                      "reason": "ok", "new_sl_price": None, "new_tp_price": None,
                      "market_context_changed": False})
    analysis = {"ticker": "AAPL", "direction": "long", "confidence": "high",
                "summary": "s", "scores": {}, "is_premarket": 1,
                "sources_used": ["https://x.com"], "tp_price": 1, "sl_price": 0.5,
                "rr_ratio": 2.0}
    with patch(CALL, return_value=_fake_result(raw)) as call:
        check_open_positions(
            conn=in_memory_db, today="2026-09-15", run_type="pre_market",
            positions=[_position()], analyses_by_ticker={"AAPL": analysis},
            tds_by_ticker={"AAPL": _snapshot()}, signal_by_ticker={},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0),
        )
    user_msg = call.call_args.kwargs["user"]
    assert "is_premarket" not in user_msg and "sources_used" not in user_msg
    assert "x.com" not in user_msg


def test_anpassen_with_only_a_new_stop_is_accepted():
    """F51: der nachgezogene Stop ohne neues TP ist die haeufigste Anpassung --
    eine Position ohne Broker-TP konnte bis C.46 nicht angepasst werden."""
    raw = json.dumps({"deal_id": "d-aapl-1", "ticker": "AAPL", "action": "ANPASSEN",
                      "reason": "trail", "new_sl_price": 179.0, "new_tp_price": None,
                      "market_context_changed": False})
    with patch(CALL, return_value=_fake_result(raw)):
        out = check_one_position(
            position=_position(), current_snapshot=_snapshot(),
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0), **WHEN,
        )
    assert out["action"] == "ANPASSEN" and out["new_sl_price"] == 179.0


@pytest.mark.parametrize("direction, current, new_sl, new_tp, why", [
    ("long",  181.2, 182.0, None,  "SL ueber dem Kurs (Long)"),
    ("long",  181.2, None,  180.0, "TP unter dem Kurs (Long)"),
    ("short", 181.2, 180.0, None,  "SL unter dem Kurs (Short)"),
    ("short", 181.2, None,  182.0, "TP ueber dem Kurs (Short)"),
    ("long",  181.2, None,  None,  "gar kein Level"),
])
def test_anpassen_with_invalid_levels_is_downgraded_to_halten(
        direction, current, new_sl, new_tp, why, caplog):
    """F51: ein neuer Stop auf der falschen Seite waere bei Ausfuehrung ein
    sofortiger Stop-out. Der Code prueft die Seite; ungueltig heisst HALTEN
    mit Hinweis in reason (persistiert, damit 3D es sieht) und WARNING."""
    import logging
    raw = json.dumps({"deal_id": "d-aapl-1", "ticker": "AAPL", "action": "ANPASSEN",
                      "reason": "trail", "new_sl_price": new_sl, "new_tp_price": new_tp,
                      "market_context_changed": False})
    pos = _position(direction=direction, current_price=current)
    with patch(CALL, return_value=_fake_result(raw)), \
         caplog.at_level(logging.WARNING, logger="shares_future.portfolio_check"):
        out = check_one_position(
            position=pos, current_snapshot=_snapshot(),
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0), **WHEN,
        )
    assert out["action"] == "HALTEN", why
    assert out["new_sl_price"] is None and out["new_tp_price"] is None
    assert out["reason"].startswith("[Levels ungueltig")
    assert "herabgestuft" in caplog.text


def test_truncated_answer_is_retried_with_a_bigger_cap_and_both_attempts_billed():
    """F52: nackter call_claude ohne stop_reason-Pruefung -- eine Kappung kam als
    JSON-Fehler an und die Position bekam still keine Empfehlung (C.18-Klasse)."""
    payload = (FIXTURE_DIR / "mock_portfolio_check_response.json").read_text()
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch(CALL, side_effect=[_fake_result('{"action": "HAL', stop_reason="max_tokens"),
                                  _fake_result(payload)]) as call:
        out = check_one_position(
            position=_position(), current_snapshot=_snapshot(),
            trend_context={}, policy_context={}, cost_tracker=tracker, **WHEN,
        )
    assert out["action"] == "ANPASSEN"
    assert call.call_count == 2
    first, second = call.call_args_list
    assert second.kwargs["max_tokens"] == first.kwargs["max_tokens"] * 2
    assert tracker.input_tokens == 3000 * 2, "beide Versuche gebucht, nicht nur der verwertete"


def test_portfolio_check_runs_on_sonnet():
    """C.46 (Entscheidung Korbinian): 4a ist die einzige Phase, deren Ausgabe
    eine Handlung an echtem Kapital ist -- Sonnet 5 statt Haiku, ~0,03 EUR je
    Position. Aus config gelesen, nie hart kodiert."""
    from src import portfolio_check
    payload = (FIXTURE_DIR / "mock_portfolio_check_response.json").read_text()
    assert portfolio_check.MODEL == config.CLAUDE_MODEL_SONNET
    with patch(CALL, return_value=_fake_result(payload)) as call:
        check_one_position(
            position=_position(), current_snapshot=_snapshot(),
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0), **WHEN,
        )
    assert call.call_args.kwargs["model"] == config.CLAUDE_MODEL_SONNET


def test_pending_rows_list_every_position_as_not_checked():
    """F53: bevor 4a laeuft (oder wenn der Kostendeckel vorher zuschlaegt),
    zeigt die Mail die Positionen als NICHT GEPRUEFT statt 'keine Positionen'."""
    from src.portfolio_check import pending_rows, NOT_CHECKED
    rows = pending_rows([_position(), _position(deal_id="d-x", epic="PPHE", ticker=None)])
    assert [r["action"] for r in rows] == [NOT_CHECKED, NOT_CHECKED]
    assert rows[1]["epic"] == "PPHE" and rows[0]["profit_loss"] == 3.2
    assert pending_rows(None) == [] and pending_rows([]) == []


def test_check_open_positions_fills_the_callers_list_in_place(in_memory_db):
    """F53 (Spec 7.1-Muster wie _revalidate_all): reisst der Kostendeckel mitten
    in der Schleife, haelt die Liste des Aufrufers die fertigen Zeilen und die
    restlichen als NICHT GEPRUEFT -- statt gar nichts."""
    from src.cost_tracker import CostCapExceeded
    from src.portfolio_check import pending_rows
    db.init_schema(in_memory_db)
    good = json.dumps({"deal_id": "d-aapl-1", "ticker": "AAPL", "action": "HALTEN",
                       "reason": "ok", "new_sl_price": None, "new_tp_price": None,
                       "market_context_changed": False})
    positions = [_position(), _position(deal_id="d-msft-1", epic="MSFT", ticker="MSFT")]
    out = pending_rows(positions)
    tracker = CostTracker(hard_cap_eur=0.0001)      # der zweite Call reisst den Deckel
    first = _fake_result(good)
    first.input_tokens = first.output_tokens = 1      # erster Call bleibt unter dem Deckel
    with patch(CALL, side_effect=[first, _fake_result(good)]):
        with pytest.raises(CostCapExceeded):
            check_open_positions(
                conn=in_memory_db, today="2026-09-15", run_type="pre_market",
                positions=positions, analyses_by_ticker={},
                tds_by_ticker={"AAPL": _snapshot(), "MSFT": _snapshot("MSFT", 410.0)},
                signal_by_ticker={}, trend_context={}, policy_context={},
                cost_tracker=tracker, out=out,
            )
    assert [r["action"] for r in out] == ["HALTEN", "NICHT GEPRUEFT"]


def test_prompt_pins_the_c46_contract():
    """F47/F48/F49/F50/F51/F54: Datumsanker, drei Snapshot-Bloecke mit Skala,
    Enthaltung ist kein Gegensignal, Horizont statt Intraday-Regel, ANPASSEN mit
    mindestens einem Level, reason auf Englisch."""
    from src.portfolio_check import SYSTEM_PROMPT
    for needle in ("TIME FRAME", "pre_market", "trade_proposals", "HORIZON",
                   '"technicals"', '"technical_signal"', '"analysis"', "0-4",
                   "NOT a signal against", "at least one", "in English"):
        assert needle in SYSTEM_PROMPT, needle
    assert "both new_sl_price AND new_tp_price" not in SYSTEM_PROMPT
    assert "innerhalb eines Handelstages" not in SYSTEM_PROMPT
