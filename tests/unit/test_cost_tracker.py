import pytest
from src.cost_tracker import CostTracker, CostCapExceeded


def test_zero_state():
    t = CostTracker()
    assert t.total_eur == 0.0
    assert t.input_tokens == 0
    assert t.web_search_calls == 0


def test_add_haiku_call_accumulates_eur_and_tokens():
    t = CostTracker(hard_cap_eur=10.0)
    t.add_call(
        model="claude-haiku-4-5",
        input_tokens=10_000, output_tokens=2_000,
        cache_read_tokens=0, web_search_calls=0,
    )
    assert t.input_tokens == 10_000
    assert t.output_tokens == 2_000
    assert t.total_eur > 0


def test_cache_read_tokens_priced_lower_than_fresh_input():
    fresh = CostTracker()
    fresh.add_call(
        model="claude-sonnet-4-6",
        input_tokens=10_000, output_tokens=0,
        cache_read_tokens=0, web_search_calls=0,
    )
    cached = CostTracker()
    cached.add_call(
        model="claude-sonnet-4-6",
        input_tokens=10_000, output_tokens=0,
        cache_read_tokens=9_000, web_search_calls=0,
    )
    assert cached.total_eur < fresh.total_eur


def test_hard_cap_raises_when_exceeded():
    t = CostTracker(hard_cap_eur=0.01)
    with pytest.raises(CostCapExceeded):
        t.add_call(
            model="claude-sonnet-4-6",
            input_tokens=100_000, output_tokens=100_000,
            cache_read_tokens=0, web_search_calls=0,
        )


def test_web_search_calls_are_counted_and_billed():
    t = CostTracker(hard_cap_eur=10.0)
    t.add_call(
        model="claude-sonnet-4-6",
        input_tokens=0, output_tokens=0,
        cache_read_tokens=0, web_search_calls=5,
    )
    assert t.web_search_calls == 5
    assert t.web_search_eur > 0


def test_persist_returns_summary_dict():
    t = CostTracker()
    t.add_call(
        model="claude-haiku-4-5",
        input_tokens=1000, output_tokens=500,
        cache_read_tokens=200, web_search_calls=1,
    )
    summary = t.summary(run_type="pre_market", date="2026-05-19")
    assert summary["run_type"] == "pre_market"
    assert summary["date"] == "2026-05-19"
    assert summary["total_eur"] > 0
    assert "cache_hit_rate" in summary
    assert 0 <= summary["cache_hit_rate"] <= 1


from unittest.mock import MagicMock
from src.cost_tracker import CostTracker


def test_add_from_result_forwards_all_fields():
    tracker = CostTracker(hard_cap_eur=10.0)
    result = MagicMock(
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=400,
        cache_read_tokens=200,
        cache_creation_tokens=100,
        web_search_calls=2,
    )
    tracker.add_from_result(result)
    assert tracker.input_tokens == 1000
    assert tracker.output_tokens == 400
    assert tracker.cache_read_tokens == 200
    assert tracker.web_search_calls == 2
    assert tracker.total_eur > 0
