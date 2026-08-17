"""Tests fuer src/analysis_signal.py -- Spec 5.2, reine Zaehlfunktion."""
import pytest

from src.analysis_signal import analysis_strength


def _dim(value, evidence=("a concrete line", "a second line"), quality="ok"):
    return {"value": value, "evidence": list(evidence), "evidence_quality": quality}


def _analysis(direction="long", **dim_overrides):
    """Acht Dimensionen, alle standardmaessig auf einem Wert, der fuer die
    gegebene Richtung zaehlt (long: 7.0 >= MOMENTUM_LONG_MIN=6.0)."""
    base_value = 7.0 if direction == "long" else 3.0
    dims = ["market_environment", "company_quality", "valuation", "momentum",
            "risk", "sector_trend", "catalyst", "policy_risk"]
    scores = {d: _dim(base_value) for d in dims}
    scores.update(dim_overrides)
    return {"direction": direction, "scores": scores}


def test_all_eight_dimensions_count_when_all_confirm():
    assert analysis_strength(_analysis("long")) == 8


def test_direction_none_scores_zero_regardless_of_dimensions():
    a = _analysis("long")
    a["direction"] = "none"
    assert analysis_strength(a) == 0


def test_unknown_direction_scores_zero():
    a = _analysis("long")
    a["direction"] = "sideways"
    assert analysis_strength(a) == 0


def test_thin_evidence_quality_does_not_count_even_with_two_lines():
    a = _analysis("long", momentum=_dim(9.0, quality="thin"))
    assert analysis_strength(a) == 7


def test_fewer_than_two_evidence_lines_does_not_count():
    a = _analysis("long", momentum=_dim(9.0, evidence=("only one line",)))
    assert analysis_strength(a) == 7


def test_value_on_wrong_side_of_threshold_does_not_count_for_long():
    # momentum_long_min = 6.0 -- 5.9 is just under it
    a = _analysis("long", momentum=_dim(5.9))
    assert analysis_strength(a) == 7


def test_value_exactly_at_threshold_counts_for_long():
    a = _analysis("long", momentum=_dim(6.0))
    assert analysis_strength(a) == 8


def test_short_uses_the_short_threshold():
    # momentum_short_max = 4.0 -- base_value fuer short ist 3.0, zaehlt
    assert analysis_strength(_analysis("short")) == 8


def test_short_value_above_threshold_does_not_count():
    a = _analysis("short", momentum=_dim(4.1))
    assert analysis_strength(a) == 7


def test_missing_value_does_not_count():
    a = _analysis("long")
    a["scores"]["risk"] = {"evidence": ["x", "y"], "evidence_quality": "ok"}
    assert analysis_strength(a) == 7


def test_missing_dimension_does_not_count():
    a = _analysis("long")
    del a["scores"]["catalyst"]
    assert analysis_strength(a) == 7


def test_missing_scores_dict_scores_zero():
    assert analysis_strength({"direction": "long"}) == 0
