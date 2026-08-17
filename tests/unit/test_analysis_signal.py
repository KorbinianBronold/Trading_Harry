"""Tests fuer src/analysis_signal.py -- Spec 5.2, reine Zaehlfunktion."""
import pytest

from src.analysis_signal import analysis_strength


def _dim(value, evidence=("a concrete line", "a second line"), quality="ok"):
    return {"value": value, "evidence": list(evidence), "evidence_quality": quality}


OTHER_DIMS = ["market_environment", "company_quality", "valuation",
              "risk", "sector_trend", "catalyst", "policy_risk"]


def _analysis(direction="long", **dim_overrides):
    """Acht Dimensionen, alle auf einem Wert, der FUER den Trade spricht.

    ⚠️ Die beiden Richtungen sehen bewusst verschieden aus, und das ist kein
    Zufall des Fixtures, sondern die Konvention der aktiven v2-Prompts:
      * long  -- alle acht hoch (7.0 >= MOMENTUM_LONG_MIN=6.0).
      * short -- `momentum` TIEF (2.0 <= MOMENTUM_SHORT_MAX=4.0, absolut
        abgelesenes Kurs-Momentum), die uebrigen sieben HOCH (9.0), weil sie
        trade-relativ erhoben werden: 'guenstig bewertet fuer einen Long' und
        'ueberdehnt bewertet fuer einen Short' sind beide eine 10.
    Ein Short mit acht niedrigen Werten ist kein starker Short, sondern einer,
    gegen den alles spricht -- siehe test_bad_short_scores_one."""
    dims = [*OTHER_DIMS, "momentum"]
    if direction == "long":
        scores = {d: _dim(7.0) for d in dims}
    else:
        scores = {d: _dim(9.0) for d in OTHER_DIMS}
        scores["momentum"] = _dim(2.0)
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


def test_good_short_scores_eight():
    """Der Regressionstest zu C1: ein gut belegter Short nach der Konvention der
    v2-Prompts -- momentum 2.0 (baerische Kursbewegung), die anderen sieben auf
    9.0 (jede spricht FUER diesen Short). Die alte Implementierung zaehlte hier
    1, weil sie die absolute Momentum-Schwelle auf alle acht anwandte."""
    assert analysis_strength(_analysis("short")) == 8


def test_bad_short_scores_one_not_eight():
    """Das Gegenstueck: ein Short, gegen den ALLE acht Dimensionen sprechen --
    baerische Kursbewegung, aber teuer bewertet, starke Firma, gutes Umfeld.
    Nur `momentum` darf zaehlen. Die alte Implementierung gab hier 8, und die
    Guardrails haetten es nicht gemerkt: sie pruefen nur scores.momentum."""
    a = _analysis("short", **{d: _dim(2.0) for d in OTHER_DIMS})
    assert analysis_strength(a) == 1


def test_short_momentum_above_its_threshold_does_not_count():
    """momentum bleibt absolut: 4.1 > MOMENTUM_SHORT_MAX=4.0 spricht gegen den
    Short, obwohl 'hoch' bei den anderen sieben gut waere."""
    a = _analysis("short", momentum=_dim(4.1))
    assert analysis_strength(a) == 7


def test_short_non_momentum_dimension_below_threshold_does_not_count():
    """Trade-relativ: eine 5.9 bei `valuation` heisst 'stuetzt diesen Short
    kaum' -- unabhaengig von der Richtung dieselbe Schwelle wie beim Long."""
    a = _analysis("short", valuation=_dim(5.9))
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
