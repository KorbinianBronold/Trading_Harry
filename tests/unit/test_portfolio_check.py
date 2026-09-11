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


def _fake_result(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 3000
    r.output_tokens = 2000
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = config.CLAUDE_MODEL_HAIKU  # portfolio_check laeuft auf Haiku, nicht Sonnet
    r.web_search_calls = 2
    return r


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
    with patch("src.portfolio_check.call_claude", return_value=_fake_result(payload)):
        out = check_one_position(
            position=_position(), current_snapshot=_snapshot(),
            trend_context=trend, policy_context=policy,
            cost_tracker=CostTracker(hard_cap_eur=10.0),
        )
    assert out["action"] == "ANPASSEN"
    assert out["new_sl_price"] == 178.5


def test_check_one_position_sends_the_position_not_a_prediction():
    """C.37: Claude bekommt die Broker-Position (Einstieg, TP/SL, P&L, Alter),
    keine Prediction und keine Ursprungsthese -- Positionen und Predictions
    sind getrennte Welten."""
    payload = (FIXTURE_DIR / "mock_portfolio_check_response.json").read_text()
    trend, policy = _ctx()
    with patch("src.portfolio_check.call_claude", return_value=_fake_result(payload)) as call:
        check_one_position(
            position=_position(), current_snapshot=_snapshot(),
            trend_context=trend, policy_context=policy,
            cost_tracker=CostTracker(hard_cap_eur=10.0),
        )
    user_msg = call.call_args.kwargs["user"]
    assert "OPEN POSITION" in user_msg and '"deal_id": "d-aapl-1"' in user_msg
    assert '"profit_loss": 3.2' in user_msg
    assert "ORIGINAL PREDICTION" not in user_msg


def test_check_open_positions_writes_position_check_rows(in_memory_db):
    db.init_schema(in_memory_db)
    payload = (FIXTURE_DIR / "mock_portfolio_check_response.json").read_text()
    trend, policy = _ctx()
    with patch("src.portfolio_check.call_claude", return_value=_fake_result(payload)):
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
    with patch("src.portfolio_check.call_claude") as call:
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
    with patch("src.portfolio_check.call_claude") as call:
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
    with patch("src.portfolio_check.call_claude") as call:
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            positions=[], analyses_by_ticker={"AAPL": _snapshot()},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0),
        )
    assert out == []
    call.assert_not_called()


def test_check_one_position_raises_on_invalid_json():
    with patch("src.portfolio_check.call_claude", return_value=_fake_result("not json")):
        with pytest.raises(PortfolioCheckError):
            check_one_position(
                position=_position(), current_snapshot=_snapshot(),
                trend_context={}, policy_context={},
                cost_tracker=CostTracker(hard_cap_eur=10.0),
            )


def test_check_open_positions_continues_after_single_failure(in_memory_db):
    db.init_schema(in_memory_db)
    good = json.loads((FIXTURE_DIR / "mock_portfolio_check_response.json").read_text())
    good.update({"ticker": "MSFT", "deal_id": "d-msft-1"})
    side_effects = [_fake_result("bad"), _fake_result(json.dumps(good))]
    positions = [_position(), _position(deal_id="d-msft-1", epic="MSFT", ticker="MSFT",
                                        entry_price=400.0, current_price=410.0)]
    with patch("src.portfolio_check.call_claude", side_effect=side_effects):
        out = check_open_positions(
            conn=in_memory_db, today="2026-05-20", run_type="pre_market",
            positions=positions,
            analyses_by_ticker={"AAPL": _snapshot(), "MSFT": _snapshot("MSFT", 410.0)},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0),
        )
    assert len(out) == 1 and out[0]["ticker"] == "MSFT"


def test_check_open_positions_enriches_with_position_fields(in_memory_db):
    """Der Mail-Renderer braucht Ticker, Richtung, Einstieg, aktuellen Kurs und
    P&L -- die kommen aus der Position, nicht aus der Claude-Antwort."""
    db.init_schema(in_memory_db)
    raw = json.dumps({"deal_id": "d-aapl-1", "ticker": "AAPL", "action": "HALTEN",
                      "reason": "kein neuer Katalysator", "new_sl_price": None,
                      "new_tp_price": None, "market_context_changed": False})
    with patch("src.portfolio_check.call_claude", return_value=_fake_result(raw)):
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
    call = mocker.patch("src.portfolio_check.call_claude")
    call.return_value = MagicMock(
        text='{"action": "HALTEN", "reason": "ok"}',
        model=config.CLAUDE_MODEL_HAIKU, input_tokens=10, output_tokens=5,
        cache_read_tokens=0, cache_creation_tokens=0, web_search_calls=0,
    )
    from src.portfolio_check import check_one_position
    from src.cost_tracker import CostTracker
    check_one_position(
        position=_position(), current_snapshot={"ticker": "AAPL"},
        trend_context={}, policy_context={}, cost_tracker=CostTracker(),
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
                   "market_context_changed", "Intraday", "Never invent prices"):
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
