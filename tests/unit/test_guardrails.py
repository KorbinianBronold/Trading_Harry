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
        "data_quality": "high",
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
    a = _valid_long()
    a["data_quality"] = "low"
    a["confidence"] = "high"
    ok, errors = GuardrailsChecker().check_analysis(a)
    assert not ok
    assert any("confidence" in e.lower() for e in errors)


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


def test_guardrail_rejects_hold_days_above_3():
    c = GuardrailsChecker()
    ok, errs = c.check_analysis(_valid_analysis(hold_days_recommended=4))
    assert not ok
    assert any("Haltedauer" in e and "3" in e for e in errs)


def test_guardrail_accepts_hold_days_3():
    c = GuardrailsChecker()
    ok, errs = c.check_analysis(_valid_analysis(hold_days_recommended=3))
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
