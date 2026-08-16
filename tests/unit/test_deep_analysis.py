import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.cost_tracker import CostTracker
from src.deep_analysis import (
    run_policy_monitor, DeepAnalysisError,
    build_batches, analyze_batch, analyze_batches, max_tokens_for_batch,
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


def _ok_response_for(tickers: list[str]) -> MagicMock:
    """Baut eine gueltige Batch-Antwort fuer genau diese Ticker."""
    template = json.loads(BATCH_FIXTURE.read_text())["results"][0]
    results = []
    for t in tickers:
        r = json.loads(json.dumps(template))
        r["ticker"] = t
        results.append(r)
    return _fake_result(json.dumps({"results": results}))


def _broken_response() -> MagicMock:
    return _fake_result("kaputt", web_search_calls=0, output_tokens=10)


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


# ---------- analyze_batches() (Sprint 3C / Plan 3a, Task 7) ----------


def test_analyze_batches_retries_once_then_succeeds():
    """Erster Versuch kaputt, Wiederholung gut -- kein Halbieren noetig."""
    tds = [_std("AAPL", "Technology"), _std("MSFT", "Technology")]
    responses = [_broken_response(), _ok_response_for(["AAPL", "MSFT"])]

    with patch("src.deep_analysis.call_claude", side_effect=responses) as cc:
        analyses, failed = analyze_batches(
            ticker_datas=tds,
            cutoff_by_ticker={t["ticker"]: _cutoff(t["ticker"]) for t in tds},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0), batch_size=8,
        )

    assert cc.call_count == 2
    assert sorted(a["ticker"] for a in analyses) == ["AAPL", "MSFT"]
    assert failed == []


def test_analyze_batches_halves_after_two_failures():
    """Zwei Fehlschlaege -> halbieren, jede Haelfte genau einmal. Eine gute
    Haelfte wird behalten, die kaputte gibt ihre Ticker auf."""
    tds = [_std(t, "Technology") for t in ("AAPL", "MSFT", "NVDA", "AVGO")]
    responses = [
        _broken_response(),                      # Versuch 1
        _broken_response(),                      # Versuch 2 (Wiederholung)
        _ok_response_for(["AAPL", "AVGO"]),      # linke Haelfte (alphabetisch)
        _broken_response(),                      # rechte Haelfte
    ]

    with patch("src.deep_analysis.call_claude", side_effect=responses) as cc:
        analyses, failed = analyze_batches(
            ticker_datas=tds,
            cutoff_by_ticker={t["ticker"]: _cutoff(t["ticker"]) for t in tds},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0), batch_size=8,
        )

    assert cc.call_count == 4
    assert sorted(a["ticker"] for a in analyses) == ["AAPL", "AVGO"]
    assert sorted(failed) == ["MSFT", "NVDA"]


def test_analyze_batches_gives_up_after_halving():
    """Begrenzte Tiefe: nach dem Halbieren wird NICHT weiter geviertelt."""
    tds = [_std(t, "Technology") for t in ("AAPL", "MSFT", "NVDA", "AVGO")]
    responses = [_broken_response() for _ in range(4)]

    with patch("src.deep_analysis.call_claude", side_effect=responses) as cc:
        analyses, failed = analyze_batches(
            ticker_datas=tds,
            cutoff_by_ticker={t["ticker"]: _cutoff(t["ticker"]) for t in tds},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0), batch_size=8,
        )

    assert cc.call_count == 4          # 2 Versuche + 2 Haelften, nicht mehr
    assert analyses == []
    assert sorted(failed) == ["AAPL", "AVGO", "MSFT", "NVDA"]


def test_analyze_batches_single_ticker_batch_does_not_halve():
    """Ein Batch mit einem Ticker kann nicht halbiert werden -- nach zwei
    Versuchen aufgeben, nicht in eine Endlosschleife laufen."""
    tds = [_std("AAPL", "Technology")]
    responses = [_broken_response(), _broken_response()]

    with patch("src.deep_analysis.call_claude", side_effect=responses) as cc:
        analyses, failed = analyze_batches(
            ticker_datas=tds, cutoff_by_ticker={"AAPL": _cutoff("AAPL")},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0), batch_size=8,
        )

    assert cc.call_count == 2
    assert analyses == []
    assert failed == ["AAPL"]


def test_analyze_batches_cost_cap_propagates():
    """CostCapExceeded ist fatal und darf NICHT als Batch-Fehler behandelt und
    wiederholt werden -- sonst laeuft der Lauf ueber den Deckel hinaus weiter."""
    from src.cost_tracker import CostCapExceeded
    tds = [_std("AAPL", "Technology")]

    with patch("src.deep_analysis.call_claude", side_effect=CostCapExceeded("cap")):
        with pytest.raises(CostCapExceeded):
            analyze_batches(
                ticker_datas=tds, cutoff_by_ticker={"AAPL": _cutoff("AAPL")},
                trend_context={}, policy_context={},
                cost_tracker=CostTracker(hard_cap_eur=10.0), batch_size=8,
            )


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
