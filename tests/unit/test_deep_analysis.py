import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.cost_tracker import CostTracker
from src.deep_analysis import (
    run_policy_monitor, analyze_asset, analyze_assets, DeepAnalysisError,
    adapt_cutoff_to_quick_filter, build_batches,
    analyze_batch, max_tokens_for_batch,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def _fake_result(text: str, model: str = "claude-sonnet-4-6",
                 web_search_calls: int = 3, output_tokens: int = 4000,
                 stop_reason: str = "end_turn") -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 5000
    r.output_tokens = output_tokens
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = model
    r.web_search_calls = web_search_calls
    r.stop_reason = stop_reason
    return r


def _td(ticker: str = "AAPL", **overrides) -> dict:
    base = {
        "ticker": ticker, "price": 178.5,
        "rsi_14": 58.0, "macd_signal": "bullish_cross", "atr_pct": 1.8,
        "bb_position": 0.62, "above_sma20": 2.1, "above_sma50": 5.4,
        "above_sma200": 12.8, "volume_ratio": 1.15,
        "intraday_range_pct": 1.5,
        "pe_ratio": 28.4, "forward_pe": 26.2, "market_cap_b": 2800.0,
        "sector": "Technology", "earnings_in_days": 14, "earnings_beat_pct": 4.2,
        "data_quality": "high",
    }
    base.update(overrides)
    return base


def _trend_context() -> dict:
    return {"trends": [{"name": "ai-capex"}], "trend_summary": "risk-on"}


def _policy_context() -> dict:
    return json.loads((FIXTURE_DIR / "mock_policy_monitor_response.json").read_text())


def _quick_filter_result(ticker: str = "AAPL") -> dict:
    return {
        "ticker": ticker, "long_score": 7.5, "short_score": 2.0,
        "confidence": "high", "evidence": ["x"], "exclude": False,
    }


def test_run_policy_monitor_parses_and_returns(in_memory_db):
    payload = (FIXTURE_DIR / "mock_policy_monitor_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.deep_analysis.call_claude", return_value=fake):
        out = run_policy_monitor(date="2026-05-19", run_type="close",
                                 cost_tracker=tracker)

    assert out["policy_risk_level"] == "medium"
    assert len(out["events"]) == 2
    assert tracker.input_tokens == 5000


def test_run_policy_monitor_uses_web_search():
    payload = (FIXTURE_DIR / "mock_policy_monitor_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.deep_analysis.call_claude", return_value=fake) as mock_call:
        run_policy_monitor(date="2026-05-19", run_type="close",
                           cost_tracker=tracker)
    kwargs = mock_call.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert any(t.get("name") == "web_search" for t in kwargs["tools"])


def test_run_policy_monitor_tolerates_empty_events():
    fake = _fake_result(json.dumps({
        "policy_risk_level": "low", "events": [], "summary": "Calm news cycle.",
    }))
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude", return_value=fake):
        out = run_policy_monitor(date="2026-05-19", run_type="close",
                                 cost_tracker=tracker)
    assert out["events"] == []


def test_analyze_asset_returns_parsed_analysis():
    payload = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude", return_value=fake):
        out = analyze_asset(
            ticker_data=_td(),
            quick_filter_result=_quick_filter_result(),
            trend_context=_trend_context(),
            policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    assert out["ticker"] == "AAPL"
    assert out["direction"] == "long"
    assert out["rr_ratio"] == 2.2


def test_analyze_asset_bills_cost_tracker_via_add_from_result():
    payload = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude", return_value=fake):
        analyze_asset(
            ticker_data=_td(), quick_filter_result=_quick_filter_result(),
            trend_context=_trend_context(), policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    assert tracker.input_tokens == 5000
    assert tracker.output_tokens == 4000
    assert tracker.web_search_calls == 3
    assert tracker.total_eur > 0


def test_analyze_asset_raises_on_unparseable_response():
    fake = _fake_result("totally not json")
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude", return_value=fake):
        with pytest.raises(DeepAnalysisError):
            analyze_asset(
                ticker_data=_td(), quick_filter_result=_quick_filter_result(),
                trend_context=_trend_context(), policy_context=_policy_context(),
                cost_tracker=tracker,
            )


def test_analyze_asset_skips_when_quick_filter_excludes():
    """A ticker with quick_filter exclude=True is never sent to deep_analysis."""
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude") as mock_call:
        out = analyze_asset(
            ticker_data=_td(), policy_context=_policy_context(),
            quick_filter_result={**_quick_filter_result(), "exclude": True},
            trend_context=_trend_context(), cost_tracker=tracker,
        )
    assert out is None
    mock_call.assert_not_called()


def test_analyze_assets_loops_and_collects_non_none():
    payload = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    fake_ok = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    excl = {**_quick_filter_result("MSFT"), "exclude": True}

    with patch("src.deep_analysis.call_claude", return_value=fake_ok):
        out = analyze_assets(
            ticker_datas=[_td("AAPL"), _td("MSFT")],
            quick_filter_results=[_quick_filter_result("AAPL"), excl],
            trend_context=_trend_context(),
            policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    assert len(out) == 1
    assert out[0]["ticker"] == "AAPL"


def test_analyze_assets_skips_on_individual_failure_continues():
    """A single ticker raising must NOT kill the loop."""
    payload_ok = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    tracker = CostTracker(hard_cap_eur=10.0)

    side_effects = [_fake_result("garbage"), _fake_result(payload_ok)]
    with patch("src.deep_analysis.call_claude", side_effect=side_effects):
        out = analyze_assets(
            ticker_datas=[_td("BADCO"), _td("AAPL")],
            quick_filter_results=[
                _quick_filter_result("BADCO"),
                _quick_filter_result("AAPL"),
            ],
            trend_context=_trend_context(),
            policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    assert len(out) == 1
    assert out[0]["ticker"] == "AAPL"


def test_analyze_asset_passes_trend_and_policy_into_user_message():
    payload = (FIXTURE_DIR / "mock_deep_analysis_response.json").read_text()
    fake = _fake_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude", return_value=fake) as mock_call:
        analyze_asset(
            ticker_data=_td(), quick_filter_result=_quick_filter_result(),
            trend_context=_trend_context(), policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    user_msg = mock_call.call_args.kwargs["user"]
    assert "ai-capex" in user_msg
    assert "tariff truce" in user_msg.lower() or "tariff-truce" in user_msg.lower()
    assert "AAPL" in user_msg


# ---------- adapt_cutoff_to_quick_filter() (Sprint 3C / Plan 2, Task 10) ----------


def test_adapt_cutoff_to_quick_filter_maps_selected_to_exclude_false():
    """Interim-Adapter: cutoff_candidates()' zweiter Rueckgabewert (all_evaluated,
    JEDER Ticker mit einem selected-Flag aus Task 9) wird zur quick_filter-Form,
    die analyze_asset() heute erwartet -- exclude ist das Komplement von selected."""
    all_evaluated = [
        {"ticker": "AAPL", "news_strength": 2, "tech_direction": "long",
         "tech_strength": 3, "selected": True},
        {"ticker": "MSFT", "news_strength": 0, "tech_direction": "none",
         "tech_strength": 0, "selected": False},
    ]

    adapted = adapt_cutoff_to_quick_filter(all_evaluated)

    assert len(adapted) == 2
    by_ticker = {a["ticker"]: a for a in adapted}
    assert by_ticker["AAPL"]["exclude"] is False
    assert by_ticker["MSFT"]["exclude"] is True


def test_adapt_cutoff_to_quick_filter_carries_the_cutoff_reasoning():
    """Es gibt kein long_score/short_score mehr im Cutoff-Modell -- an ihrer
    Stelle die tatsaechliche Begruendung, damit Phase 3 nicht auf reinen
    None-Platzhaltern sitzt."""
    all_evaluated = [
        {"ticker": "AAPL", "news_strength": 2, "tech_direction": "long",
         "tech_strength": 3, "selected": True},
    ]

    adapted = adapt_cutoff_to_quick_filter(all_evaluated)

    assert adapted[0]["news_strength"] == 2
    assert adapted[0]["tech_direction"] == "long"
    assert adapted[0]["tech_strength"] == 3


def test_adapt_cutoff_to_quick_filter_excluded_ticker_skips_deep_analysis():
    """Gegenprobe gegen die echte analyze_asset()-Gate-Logik, nicht nur gegen
    die Adapter-Form: ein exclude=True aus dem Adapter fuehrt tatsaechlich zu
    keinem Claude-Call."""
    adapted = adapt_cutoff_to_quick_filter([
        {"ticker": "MSFT", "news_strength": 0, "tech_direction": "none",
         "tech_strength": 0, "selected": False},
    ])
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.deep_analysis.call_claude") as mock_call:
        result = analyze_asset(
            ticker_data=_td("MSFT"),
            quick_filter_result=adapted[0],
            trend_context=_trend_context(), policy_context=_policy_context(),
            cost_tracker=tracker,
        )
    assert result is None
    mock_call.assert_not_called()


# ---------- build_batches() (Sprint 3C / Plan 3a, Task 3) ----------


def _std(ticker: str, sector: str | None) -> dict:
    return {"ticker": ticker, "sector": sector, "price": 100.0}


def test_build_batches_packs_whole_subsectors():
    """Ganze Sub-Sektoren werden gepackt, nie zerrissen -- die echte
    MVP-Verteilung (20 Aktien, 12 Sub-Sektoren) ergibt 3 Batches (8/8/4)."""
    tds = (
        [_std(t, "Retail") for t in ("AMZN", "WMT", "HD")]
        + [_std(t, "Financial Services") for t in ("BRK-B", "V", "MA")]
        + [_std(t, "Technology") for t in ("AAPL", "MSFT")]
        + [_std(t, "Semiconductors") for t in ("NVDA", "AVGO")]
        + [_std(t, "Pharmaceuticals") for t in ("JNJ", "LLY")]
        + [_std(t, "Media") for t in ("GOOGL", "META")]
        + [_std("UNH", "Health Care"), _std("XOM", "Energy"),
           _std("PG", "Consumer products"), _std("ABBV", "Biotechnology"),
           _std("JPM", "Banking"), _std("TSLA", "Automobiles")]
    )

    batches = build_batches(tds, batch_size=8)

    assert [len(b) for b in batches] == [8, 8, 4]
    assert sum(len(b) for b in batches) == 20
    # kein Ticker doppelt, keiner verloren
    assert sorted(td["ticker"] for b in batches for td in b) == sorted(
        td["ticker"] for td in tds
    )
    # Retail bleibt zusammen
    for b in batches:
        retail = [td["ticker"] for td in b if td["sector"] == "Retail"]
        assert retail in ([], ["AMZN", "HD", "WMT"])


def test_build_batches_splits_oversized_subsector():
    """Ein Sub-Sektor groesser als batch_size wird aufgeteilt -- der Fall, der
    beim 3F-Ausbau die Regel dominiert (Spec 20.2)."""
    tds = [_std(f"SEMI{i:02d}", "Semiconductors") for i in range(19)]

    batches = build_batches(tds, batch_size=8)

    assert [len(b) for b in batches] == [8, 8, 3]


def test_build_batches_is_deterministic():
    """Gleiche Eingabe in anderer Reihenfolge -> identische Batches. Ohne das
    sind Tests und der 3D-Vergleich zweier Laeufe wertlos."""
    tds = [
        _std("MSFT", "Technology"), _std("AMZN", "Retail"),
        _std("AAPL", "Technology"), _std("HD", "Retail"),
        _std("XOM", "Energy"),
    ]
    a = build_batches(tds, batch_size=3)
    b = build_batches(list(reversed(tds)), batch_size=3)

    assert [[td["ticker"] for td in x] for x in a] == \
           [[td["ticker"] for td in y] for y in b]


def test_build_batches_groups_missing_sector_together():
    """Ticker ohne Sektor bilden eine eigene Einheit statt still in fremde
    Sub-Sektoren zu rutschen -- Grundregel des Projekts: lieber ungemappt als
    falsch gemappt."""
    tds = [_std("AAPL", "Technology"), _std("A", None), _std("B", "")]

    batches = build_batches(tds, batch_size=8)

    assert len(batches) == 1
    assert sorted(td["ticker"] for td in batches[0]) == ["A", "AAPL", "B"]


def test_build_batches_empty_input():
    assert build_batches([], batch_size=8) == []


def test_build_batches_rejects_zero_batch_size():
    with pytest.raises(ValueError, match="batch_size"):
        build_batches([_std("AAPL", "Technology")], batch_size=0)


# ---------- analyze_batch() (Sprint 3C / Plan 3a, Task 6) ----------


BATCH_FIXTURE = FIXTURE_DIR / "mock_deep_analysis_batch_response.json"


def _cutoff(ticker: str, news_strength: int = 2) -> dict:
    return {
        "ticker": ticker, "news_strength": news_strength,
        "tech_direction": "long", "tech_strength": 3,
    }


def test_max_tokens_for_batch_scales_with_size():
    """Abgeleitet statt fest: 4096 war fuer EINEN Ticker ausgelegt."""
    assert max_tokens_for_batch(8) == 9200      # 8 * 900 + 2000
    assert max_tokens_for_batch(1) == 4096      # Einzelfall unveraendert
    assert max_tokens_for_batch(20) == 20000


def test_analyze_batch_returns_one_analysis_per_ticker():
    fake = _fake_result(BATCH_FIXTURE.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_std("AAPL", "Technology"), _std("MSFT", "Technology")]

    with patch("src.deep_analysis.call_claude", return_value=fake) as cc:
        analyses, missing = analyze_batch(
            ticker_datas=batch,
            cutoff_by_ticker={"AAPL": _cutoff("AAPL"), "MSFT": _cutoff("MSFT")},
            trend_context={}, policy_context={}, cost_tracker=tracker,
        )

    assert [a["ticker"] for a in analyses] == ["AAPL", "MSFT"]
    assert missing == []
    assert cc.call_args.kwargs["stream"] is True
    assert cc.call_args.kwargs["max_tokens"] == max_tokens_for_batch(2)


def test_analyze_batch_keeps_partial_results():
    """Spec 10: 'zehn gute Analysen schlagen null'. Ein fehlender Ticker wird
    gemeldet, nicht erfunden -- und kippt nie die gelieferten."""
    payload = json.loads(BATCH_FIXTURE.read_text())
    payload["results"] = payload["results"][:1]       # MSFT fehlt
    fake = _fake_result(json.dumps(payload))
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_std("AAPL", "Technology"), _std("MSFT", "Technology")]

    with patch("src.deep_analysis.call_claude", return_value=fake):
        analyses, missing = analyze_batch(
            ticker_datas=batch,
            cutoff_by_ticker={"AAPL": _cutoff("AAPL"), "MSFT": _cutoff("MSFT")},
            trend_context={}, policy_context={}, cost_tracker=tracker,
        )

    assert [a["ticker"] for a in analyses] == ["AAPL"]
    assert missing == ["MSFT"]


def test_analyze_batch_raises_on_unparseable_response():
    """Anders als broad_scan (das auf 0 degradiert) wirft die Tiefenanalyse --
    Task 7 faengt und wiederholt/halbiert."""
    fake = _fake_result("not json at all", web_search_calls=0, output_tokens=10)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.deep_analysis.call_claude", return_value=fake):
        with pytest.raises(DeepAnalysisError):
            analyze_batch(
                ticker_datas=[_std("AAPL", "Technology")],
                cutoff_by_ticker={"AAPL": _cutoff("AAPL")},
                trend_context={}, policy_context={}, cost_tracker=tracker,
            )


def test_analyze_batch_raises_when_output_was_truncated():
    """Spec 4.8: stop_reason == 'max_tokens' ist ein Fehlerfall, kein
    akzeptables Ergebnis -- auch wenn das Teil-JSON zufaellig parsebar waere."""
    fake = _fake_result(
        BATCH_FIXTURE.read_text(), output_tokens=9200, stop_reason="max_tokens")
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.deep_analysis.call_claude", return_value=fake):
        with pytest.raises(DeepAnalysisError, match="max_tokens"):
            analyze_batch(
                ticker_datas=[_std("AAPL", "Technology"), _std("MSFT", "Technology")],
                cutoff_by_ticker={"AAPL": _cutoff("AAPL"), "MSFT": _cutoff("MSFT")},
                trend_context={}, policy_context={}, cost_tracker=tracker,
            )


def test_analyze_batch_payload_does_not_mutate_td():
    """Sidecar-Invariante: der Batch-Aufbau haengt keine Schluessel an td."""
    fake = _fake_result(BATCH_FIXTURE.read_text())
    td = _std("AAPL", "Technology")
    before = set(td)

    with patch("src.deep_analysis.call_claude", return_value=fake):
        analyze_batch(
            ticker_datas=[td], cutoff_by_ticker={"AAPL": _cutoff("AAPL")},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0),
        )

    assert set(td) == before


# ---------- deep_analysis_v2.txt (Sprint 3C / Plan 3a, Task 4) ----------


def test_deep_analysis_v2_pins_contract_the_code_relies_on():
    """Was hier steht, verlaesst sich Code drauf: der results-Schluessel
    (Task 6 parst ihn), evidence_quality (Task 8 macht die thin-Ausnahme
    daran fest) und die Polaritaets-Festlegung (Plan 3b zaehlt news_strength
    danach). Keine Stilpruefung -- nur der Vertrag."""
    v2 = Path(__file__).parent.parent.parent / "prompts" / "deep_analysis_v2.txt"
    text = v2.read_text()

    assert '"results"' in text
    assert '"evidence_quality"' in text
    assert '"thin"' in text
    # Polaritaet: die drei Dimensionen, bei denen "hoch = gut" nicht
    # selbsterklaerend ist, muessen ausdruecklich geregelt sein (Spec 5.2)
    for dim in ("risk", "policy_risk", "valuation"):
        assert dim in text
    assert "higher is always better" in text.lower()
    # Claude waehlt nicht aus (Spec 4.8)
    assert "never omit" in text.lower()


def test_deep_analysis_v1_untouched():
    """Regel 10: v1 bleibt auf der Platte, unveraendert."""
    v1 = Path(__file__).parent.parent.parent / "prompts" / "deep_analysis_v1.txt"
    assert v1.exists()
    assert "You receive ONE ticker snapshot" in v1.read_text()
