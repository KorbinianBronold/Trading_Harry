import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

import config
from src.db import init_schema
from src.cost_tracker import CostTracker
from src.trend_analyzer import analyze_trends, TrendAnalyzerError


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mock_trend_response.json"


def _fake_claude_result(text: str, web_search_calls: int = 4) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 4000
    r.output_tokens = 3000
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = config.CLAUDE_MODEL_SONNET
    r.web_search_calls = web_search_calls
    return r


def test_analyze_trends_parses_response_and_writes_db(in_memory_db):
    init_schema(in_memory_db)
    payload = FIXTURE_PATH.read_text()
    fake = _fake_claude_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.utils.call_claude", return_value=fake):
        out = analyze_trends(
            conn=in_memory_db,
            date="2026-05-19",
            run_type="pre_market",
            cost_tracker=tracker,
        )

    assert len(out["trends"]) == 2
    assert out["sector_rotation"]["into"] == ["XLK", "XLE"]
    rows = in_memory_db.execute(
        "SELECT trend_name, strength FROM trend_analyses "
        "WHERE date='2026-05-19' ORDER BY strength DESC"
    ).fetchall()
    assert [r["trend_name"] for r in rows] == [
        "ai-capex-acceleration", "oil-supply-tightening"
    ]


def test_analyze_trends_bills_cost_tracker(in_memory_db):
    init_schema(in_memory_db)
    payload = FIXTURE_PATH.read_text()
    fake = _fake_claude_result(payload, web_search_calls=5)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.utils.call_claude", return_value=fake):
        analyze_trends(
            conn=in_memory_db,
            date="2026-05-19",
            run_type="pre_market",
            cost_tracker=tracker,
        )

    assert tracker.web_search_calls == 5
    assert tracker.input_tokens == 4000
    assert tracker.output_tokens == 3000
    assert tracker.total_eur > 0


def test_analyze_trends_raises_on_invalid_json(in_memory_db):
    init_schema(in_memory_db)
    fake = _fake_claude_result("this is not json at all")
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.utils.call_claude", return_value=fake):
        with pytest.raises(TrendAnalyzerError):
            analyze_trends(
                conn=in_memory_db, date="2026-05-19",
                run_type="pre_market", cost_tracker=tracker,
            )


def test_analyze_trends_raises_on_empty_trends(in_memory_db):
    init_schema(in_memory_db)
    fake = _fake_claude_result(json.dumps({
        "trends": [],
        "sector_rotation": {"into": [], "out_of": []},
        "trend_summary": "Web search returned nothing usable.",
    }))
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.utils.call_claude", return_value=fake):
        with pytest.raises(TrendAnalyzerError, match="empty"):
            analyze_trends(
                conn=in_memory_db, date="2026-05-19",
                run_type="pre_market", cost_tracker=tracker,
            )


def test_analyze_trends_extracts_json_from_markdown_fences(in_memory_db):
    """Sonnet sometimes wraps JSON in ```json ... ```. Be tolerant."""
    init_schema(in_memory_db)
    payload = FIXTURE_PATH.read_text()
    fenced = f"```json\n{payload}\n```"
    fake = _fake_claude_result(fenced)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.utils.call_claude", return_value=fake):
        out = analyze_trends(
            conn=in_memory_db, date="2026-05-19",
            run_type="pre_market", cost_tracker=tracker,
        )
    assert len(out["trends"]) == 2


def test_analyze_trends_uses_web_search_tool_in_request(in_memory_db):
    init_schema(in_memory_db)
    payload = FIXTURE_PATH.read_text()
    fake = _fake_claude_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.utils.call_claude", return_value=fake) as mock_call:
        analyze_trends(
            conn=in_memory_db, date="2026-05-19",
            run_type="pre_market", cost_tracker=tracker,
        )

    kwargs = mock_call.call_args.kwargs
    assert kwargs["model"] == config.CLAUDE_MODEL_SONNET
    assert kwargs["tools"] is not None
    assert any(t.get("name") == "web_search" for t in kwargs["tools"])


# ---------- B5: Abbruchgrund sichtbar machen ----------


def test_empty_trends_error_carries_the_models_own_explanation(in_memory_db):
    """Der Prompt fordert bei leerer Trendliste ausdruecklich eine Begruendung in
    `trend_summary` an. Phase 0 ist fatal (Spec 3) -- wenn der Lauf daran stirbt,
    muss diese Begruendung in der Fehlermeldung stehen, sonst ist sie verloren:
    `trend_summary` wird nirgends persistiert."""
    init_schema(in_memory_db)
    fake = _fake_claude_result(json.dumps({
        "trends": [],
        "sector_rotation": {"into": [], "out_of": []},
        "trend_summary": "Alle Quellen hinter Paywall, keine belastbare Evidenz.",
    }))
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.utils.call_claude", return_value=fake):
        with pytest.raises(TrendAnalyzerError) as excinfo:
            analyze_trends(conn=in_memory_db, date="2026-05-19",
                           run_type="pre_market", cost_tracker=tracker)

    assert "Paywall" in str(excinfo.value)


def test_empty_trends_error_survives_a_missing_explanation(in_memory_db):
    """Liefert das Modell gar keine Begruendung, muss der Abbruch trotzdem
    sauber greifen -- kein KeyError, kein 'None' im Text."""
    init_schema(in_memory_db)
    fake = _fake_claude_result(json.dumps({"trends": []}))
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.utils.call_claude", return_value=fake):
        with pytest.raises(TrendAnalyzerError, match="empty") as excinfo:
            analyze_trends(conn=in_memory_db, date="2026-05-19",
                           run_type="pre_market", cost_tracker=tracker)

    assert "None" not in str(excinfo.value)


# ---------- B2: das handelbare Universum steht im Prompt ----------


def test_user_message_names_the_tradeable_universe(in_memory_db):
    """Phase 0 bekommt sonst keinerlei Systemwissen: ohne die Liste nennt das
    Modell S&P-500-Ticker, die es bei uns gar nicht gibt (im Lauf vom 02.09.
    waren UAL und CCL dabei). Die Ticker-Listen sind der maschinenlesbare Teil
    der Antwort -- sie muessen auf das zeigen, was die Pipeline handeln kann."""
    init_schema(in_memory_db)
    fake = _fake_claude_result(FIXTURE_PATH.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.utils.call_claude", return_value=fake) as mock_call:
        analyze_trends(conn=in_memory_db, date="2026-05-19",
                       run_type="pre_market", cost_tracker=tracker)

    user_msg = mock_call.call_args.kwargs["user"]
    assert "AAPL" in user_msg                 # Aktie aus stock_universe()
    assert "BTCUSD" in user_msg               # Krypto
    assert "GOLD" in user_msg                 # Rohstoff
    assert "XLF" not in user_msg              # Sektor-ETF: nie handelbar, nur Momentum
