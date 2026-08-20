"""Tests fuer src/revalidation.py — der billige 16:10-Check (Entscheidung E1)."""
from unittest.mock import MagicMock
import pytest

from src.cost_tracker import CostTracker


def _claude(text: str) -> MagicMock:
    return MagicMock(text=text, model="claude-sonnet-5",
                     input_tokens=800, output_tokens=200,
                     cache_read_tokens=0, cache_creation_tokens=0,
                     web_search_calls=0)


PRED = {"id": 7, "ticker": "AAPL", "direction": "long", "entry_price": 178.0,
        "tp_price": 184.0, "sl_price": 176.0, "probability_pct": 65,
        "confidence": "high", "summary": "Momentum-Setup"}
OK_JSON = ('{"verdict": "bestaetigt", "probability_pct": 71, '
           '"entry_window_low": 178.2, "entry_window_high": 179.0, '
           '"reason": "haelt nach Opening"}')


def test_revalidation_uses_no_web_search(mocker):
    """E1: die 27 Einzelrecherchen sind gestrichen — genau das spart die Kosten."""
    call = mocker.patch("src.utils.call_claude", return_value=_claude(OK_JSON))
    from src.revalidation import revalidate_one
    revalidate_one(prediction=PRED, snapshot={"ticker": "AAPL", "price": 179.0},
                   checks=[], relative_strength=1.4, policy_context={},
                   cost_tracker=CostTracker())
    assert call.call_args.kwargs["tools"] == []


def test_revalidation_returns_verdict_and_probability(mocker):
    mocker.patch("src.utils.call_claude", return_value=_claude(OK_JSON))
    from src.revalidation import revalidate_one
    out = revalidate_one(prediction=PRED, snapshot={"ticker": "AAPL", "price": 179.0},
                         checks=[], relative_strength=1.4, policy_context={},
                         cost_tracker=CostTracker())
    assert out["verdict"] == "bestaetigt"
    assert out["probability_pct"] == 71
    assert out["entry_window_low"] == 178.2
    assert out["ticker"] == "AAPL"


def test_revalidation_rejects_an_unknown_verdict(mocker):
    """Ein erfundenes Urteil darf nicht still als 'bestaetigt' durchgehen."""
    mocker.patch("src.utils.call_claude",
                 return_value=_claude('{"verdict": "super", "probability_pct": 71}'))
    from src.revalidation import revalidate_one, RevalidationError
    with pytest.raises(RevalidationError):
        revalidate_one(prediction=PRED, snapshot={}, checks=[],
                       relative_strength=None, policy_context={},
                       cost_tracker=CostTracker())


def test_revalidation_raises_on_unparseable_output(mocker):
    mocker.patch("src.utils.call_claude", return_value=_claude("kein JSON"))
    from src.revalidation import revalidate_one, RevalidationError
    with pytest.raises(RevalidationError):
        revalidate_one(prediction=PRED, snapshot={}, checks=[],
                       relative_strength=None, policy_context={},
                       cost_tracker=CostTracker())


def test_revalidation_books_its_cost(mocker):
    mocker.patch("src.utils.call_claude", return_value=_claude(OK_JSON))
    from src.revalidation import revalidate_one
    tracker = CostTracker()
    revalidate_one(prediction=PRED, snapshot={}, checks=[],
                   relative_strength=None, policy_context={},
                   cost_tracker=tracker)
    assert tracker.total_eur > 0


def test_fired_checks_reach_the_model(mocker):
    """Der Prompt muss die Warnungen kennen, sonst kann er sie nicht wuerdigen."""
    call = mocker.patch("src.utils.call_claude", return_value=_claude(OK_JSON))
    from src.revalidation import revalidate_one
    from src.signal_checks import CheckResult
    revalidate_one(
        prediction=PRED, snapshot={}, relative_strength=None, policy_context={},
        checks=[CheckResult("vix_high_confidence_only", "VIX 28.4 zu hoch", False)],
        cost_tracker=CostTracker(),
    )
    assert "VIX 28.4 zu hoch" in call.call_args.kwargs["user"]
