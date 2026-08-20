"""Phase 0: Megatrend identification.

Single Sonnet call with the server-side web_search tool. Output is a structured
JSON blob which we persist row-per-trend in the trend_analyses table. The caller
(main.py orchestrator) treats a TrendAnalyzerError as fatal for the run, per
spec §3 "Phase 0 fehlt → Run abbrechen + Alert-Mail".
"""
import logging
from pathlib import Path

import config
from src import db
from src.cost_tracker import CostTracker
from src.utils import (call_claude_retry_on_truncation, extract_json_blob,
                       WEB_SEARCH_TOOL)

log = logging.getLogger("shares_future.trend_analyzer")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "trend_analyzer_v1.txt").read_text()

MODEL = config.CLAUDE_MODEL_SONNET
# ⚠️ 4096 war gegen claude-sonnet-4-6 bemessen, das ohne explizites
# thinking-Feld gar nicht dachte. Unter claude-sonnet-5 (adaptives Denken an,
# Denk- und Antworttokens teilen sich die Decke) reicht der Wert NICHT
# verlaesslich: im Messlauf lief Phase 0 einmal sauber durch und kappte beim
# naechsten Lauf bei identischem Code -- die Antwort brach dann mitten im JSON
# ab ('Unterminated string'), und Phase 0 ist laut Spec 3 fatal fuer den
# ganzen Lauf. 12288 gibt dem Antworttext seinen alten Platz zurueck und legt
# den gemessenen Denk-Aufschlag obendrauf; die Kappungs-Erkennung in
# call_claude_retry_on_truncation() ist das eigentliche Netz darunter, weil
# adaptives Denken nicht deterministisch ist.
MAX_TOKENS = 12288


class TrendAnalyzerError(RuntimeError):
    """Phase 0 produced no usable output. Caller MUST abort the run."""


def analyze_trends(
    conn,
    date: str,
    run_type: str,
    cost_tracker: CostTracker,
) -> dict:
    """Runs Phase 0: fetches current market trends via Claude + web search and
    persists one row per trend to `trend_analyses`. Raises TrendAnalyzerError if
    the response is unparseable or has zero trends."""
    user_msg = (
        f"Today is {date}. Run type: {run_type}. "
        "Use web_search 3-5 times to gather evidence on dominant short-term "
        "market trends, then return the JSON object defined in your system prompt."
    )

    # Bucht jeden Versuch selbst -- auch einen verworfenen gekappten.
    result = call_claude_retry_on_truncation(
        model=MODEL,
        system=SYSTEM_PROMPT,
        user=user_msg,
        max_tokens=MAX_TOKENS,
        cost_tracker=cost_tracker,
        tools=[WEB_SEARCH_TOOL],
    )

    parsed = extract_json_blob(result.text, TrendAnalyzerError)
    trends = parsed.get("trends") or []
    if not trends:
        raise TrendAnalyzerError(
            "Trend analyzer returned empty trends list — aborting run."
        )

    for t in trends:
        db.save_trend_analysis(conn, {
            "date": date, "run_type": run_type,
            "trend_name":          t.get("name"),
            "strength":            t.get("strength"),
            "duration_estimate":   t.get("duration_estimate"),
            "summary":             t.get("summary"),
            "beneficiary_tickers": t.get("beneficiary_tickers") or [],
            "negative_tickers":    t.get("negative_tickers") or [],
            "next_catalyst":       t.get("next_catalyst"),
        })

    log.info(
        f"Phase 0 done: {len(trends)} trends, "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return parsed
