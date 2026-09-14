import pytest
from src.guardrails import GuardrailsChecker


def _valid_long() -> dict:
    return {
        "ticker": "AAPL", "direction": "long", "confidence": "high",
        "current_price": 178.5, "tp_price": 182.0, "sl_price": 176.7,
        "rr_ratio": 1.94,
        "total_score": 7.5, "summary": "Test reason",
        "sources_used": ["Reuters", "Bloomberg"],
        "signal_consistency_check": "pass",
        "scores": {
            "market_environment": {"value": 7, "evidence": ["VIX 14", "SP500 +0.5%"]},
            "company_quality":    {"value": 8, "evidence": ["EPS beat 5%", "Guidance raised"]},
            "valuation":          {"value": 6, "evidence": ["PE 28", "Target +8%"]},
            "momentum":           {"value": 8, "evidence": ["RSI 58", "SMA200 +12%"]},
            "risk":               {"value": 6, "evidence": ["ATR 1.8", "D/E 1.4"]},
            "sector_trend":       {"value": 7, "evidence": ["XLK +1%", "Inflows positive"]},
            "catalyst":           {"value": 7, "evidence": ["Earnings 14d", "WWDC June"]},
            "policy_risk":        {"value": 5, "evidence": ["No new tariffs", "Stable rates"]},
        },
        "hold_days_recommended": 2,
        "intraday_range_pct": 1.5,
    }


def test_valid_long_passes():
    ok, errors = GuardrailsChecker().check_analysis(_valid_long())
    assert ok, errors


def test_missing_required_field_fails():
    a = _valid_long()
    del a["summary"]
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("summary" in e.lower() for e in errors)


def test_too_few_sources_fails():
    a = _valid_long()
    a["sources_used"] = ["Reuters"]
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("source" in e.lower() for e in errors)


def test_too_few_evidence_per_dimension_fails():
    a = _valid_long()
    a["scores"]["momentum"]["evidence"] = ["only one"]
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("momentum" in e.lower() for e in errors)


def test_long_with_tp_below_entry_fails():
    a = _valid_long()
    a["tp_price"] = 175.0  # below current_price 178.5
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("tp" in e.lower() for e in errors)


def test_long_with_sl_above_entry_fails():
    a = _valid_long()
    a["sl_price"] = 180.0  # above current_price 178.5
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("sl" in e.lower() for e in errors)


def test_rr_ratio_below_hard_minimum_fails():
    a = _valid_long()
    a["rr_ratio"] = 1.2  # below 1.5 hard min
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("r/r" in e.lower() or "rr" in e.lower() for e in errors)


def test_high_confidence_with_low_data_quality_fails():
    """F42 (C.45): data_quality ist eine Phase-1-Tatsache aus dem Snapshot und
    kommt als Parameter -- das Analyse-Dict des Modells traegt den Schluessel nie."""
    a = _valid_long()
    a["confidence"] = "high"
    ok, errors = GuardrailsChecker().check_analysis(a, data_quality="low")
    assert not ok
    assert any("confidence" in e.lower() for e in errors)


def test_data_quality_inside_the_analysis_dict_is_ignored():
    """F42: bis C.45 las die Regel a['data_quality'] -- ein Schluessel, den das
    Prompt-Schema nicht kennt. Die Regel war tot. Ein injizierter Wert im Dict
    darf nichts bewirken, sonst kehrt der tote Pfad zurueck."""
    a = _valid_long()
    a["data_quality"] = "low"
    a["confidence"] = "high"
    ok, _ = GuardrailsChecker().check_analysis(a)
    assert ok


def test_signal_consistency_long_low_momentum_fails():
    a = _valid_long()
    a["scores"]["momentum"]["value"] = 5  # below 6.0 → long signal inconsistent
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("signal_consistency" in e.lower() or "momentum" in e.lower() for e in errors)


def test_signal_consistency_short_high_momentum_fails():
    a = _valid_long()
    a["direction"] = "short"
    a["tp_price"] = 170.0  # below entry
    a["sl_price"] = 181.0  # above entry
    a["rr_ratio"] = 1.94
    # momentum is 8 → too high for short, should fail consistency
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("momentum" in e.lower() for e in errors)


import pytest
from src.guardrails import GuardrailsChecker


def _valid_analysis(**overrides):
    """A minimum analysis dict that passes every existing guardrail."""
    base = {
        "ticker": "AAPL", "direction": "long", "confidence": "high",
        "current_price": 178.0, "tp_price": 184.0, "sl_price": 176.0,
        "rr_ratio": 3.0, "total_score": 7.5, "summary": "ok",
        "sources_used": ["reuters.com", "bloomberg.com"],
        "signal_consistency_check": "ok",
        "scores": {
            "market_environment": {"value": 7.0, "evidence": ["a", "b"]},
            "company_quality":    {"value": 8.0, "evidence": ["a", "b"]},
            "valuation":           {"value": 6.0, "evidence": ["a", "b"]},
            "momentum":           {"value": 7.5, "evidence": ["a", "b"]},
            "risk":               {"value": 6.0, "evidence": ["a", "b"]},
            "sector_trend":       {"value": 7.0, "evidence": ["a", "b"]},
            "catalyst":           {"value": 7.0, "evidence": ["a", "b"]},
            "policy_risk":        {"value": 6.0, "evidence": ["a", "b"]},
        },
        "hold_days_recommended": 2,
        "intraday_range_pct": 1.5,
    }
    base.update(overrides)
    return base


def test_required_fields_now_include_hold_days_and_intraday_range():
    c = GuardrailsChecker()
    a = _valid_analysis()
    a.pop("hold_days_recommended")
    ok, errs = c.check_analysis(a)
    assert not ok
    assert any("hold_days_recommended" in e for e in errs)


def test_guardrail_rejects_hold_days_above_5():
    c = GuardrailsChecker()
    ok, errs = c.check_analysis(_valid_analysis(hold_days_recommended=6))
    assert not ok
    assert any("Haltedauer" in e and "5" in e for e in errs)


def test_guardrail_accepts_hold_days_3():
    c = GuardrailsChecker()
    ok, errs = c.check_analysis(_valid_analysis(hold_days_recommended=3))
    assert ok, errs


def test_guardrail_accepts_hold_days_5():
    c = GuardrailsChecker()
    ok, errs = c.check_analysis(_valid_analysis(hold_days_recommended=5))
    assert ok, errs


def test_guardrail_rejects_intraday_range_below_one_percent():
    c = GuardrailsChecker()
    ok, errs = c.check_analysis(_valid_analysis(intraday_range_pct=0.7))
    assert not ok
    assert any("Intraday-Range" in e and "1.0" in e for e in errs)


def test_guardrail_accepts_intraday_range_exactly_one_percent():
    c = GuardrailsChecker()
    ok, errs = c.check_analysis(_valid_analysis(intraday_range_pct=1.0))
    assert ok, errs


def test_check_analysis_thin_dimension_skips_evidence_requirement():
    """Eine als thin markierte Dimension darf weniger als zwei Belege haben."""
    a = _valid_analysis()
    a["scores"]["valuation"] = {
        "value": 5.0, "evidence": ["nur eine Zeile"], "evidence_quality": "thin",
    }
    passed, errors = GuardrailsChecker().check_analysis(a)
    assert passed, errors


def test_check_analysis_thin_dimension_with_zero_evidence_allowed():
    """thin heisst 'ich habe nichts gefunden' -- auch leer ist zulaessig.
    Weglassen der Dimension waere es NICHT (Spec 4.8)."""
    a = _valid_analysis()
    a["scores"]["valuation"] = {
        "value": 5.0, "evidence": [], "evidence_quality": "thin",
    }
    passed, errors = GuardrailsChecker().check_analysis(a)
    assert passed, errors


def test_check_analysis_ok_dimension_still_needs_two_evidence():
    """Keine generelle Aufweichung: ohne thin-Markierung gilt die Pflicht."""
    a = _valid_analysis()
    a["scores"]["valuation"] = {
        "value": 5.0, "evidence": ["nur eine"], "evidence_quality": "ok",
    }
    passed, errors = GuardrailsChecker().check_analysis(a)
    assert not passed
    assert any("valuation" in e for e in errors)


def test_check_analysis_missing_evidence_quality_still_needs_two_evidence():
    """Ein v1-Ergebnis ohne evidence_quality faellt auf die strenge Regel
    zurueck -- die Ausnahme greift nur bei ausdruecklichem 'thin'."""
    a = _valid_analysis()
    a["scores"]["valuation"] = {"value": 5.0, "evidence": ["nur eine"]}
    passed, errors = GuardrailsChecker().check_analysis(a)
    assert not passed
    assert any("valuation" in e for e in errors)


def test_check_analysis_unknown_evidence_quality_is_strict():
    """Ein unbekannter Wert ist kein Freifahrtschein -- nur exakt 'thin'
    oeffnet die Ausnahme."""
    a = _valid_analysis()
    a["scores"]["valuation"] = {
        "value": 5.0, "evidence": ["nur eine"], "evidence_quality": "duenn",
    }
    passed, errors = GuardrailsChecker().check_analysis(a)
    assert not passed


# ---------- C.45 / F46: Quellen als Domains, Richtung, Schwelle aus config ----------

def test_two_urls_on_the_same_domain_count_as_one_source():
    """Der Prompt verlangt '>= 2 distinct domains'; der Code zaehlte Eintraege."""
    a = _valid_long()
    a["sources_used"] = ["https://www.reuters.com/a", "https://reuters.com/b"]
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any(e.lower().startswith("too few sources") for e in errors)


def test_two_urls_on_different_domains_pass():
    a = _valid_long()
    a["sources_used"] = ["https://www.reuters.com/a", "https://bloomberg.com/b"]
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert ok, errors


def test_unknown_direction_is_rejected_not_waved_through():
    """'Long' statt 'long' passierte bis C.45 alle Regeln: weder TP/SL- noch
    Momentum-Pruefung griffen, und die Zeile waere persistiert worden."""
    a = _valid_long()
    a["direction"] = "Long"
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("direction" in e.lower() for e in errors)


def test_min_intraday_range_threshold_comes_from_config():
    """Die einzige Guardrail-Schwelle, die bis C.45 nicht in config stand."""
    import config
    assert GuardrailsChecker().min_intraday_range_pct == config.MIN_INTRADAY_RANGE_PCT
    assert config.MIN_INTRADAY_RANGE_PCT == 1.0
