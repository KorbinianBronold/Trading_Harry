"""Phase 0: Megatrend identification.

Single Sonnet call with the server-side web_search tool. Output is a structured
JSON blob which we persist row-per-trend in the trend_analyses table. The caller
(main.py orchestrator) treats a TrendAnalyzerError as fatal for the run, per
spec §3 "Phase 0 fehlt → Run abbrechen + Alert-Mail".
"""
import json
import logging
import re
from pathlib import Path

from src import db
from src.cost_tracker import CostTracker
from src.utils import call_claude

log = logging.getLogger("shares_future.trend_analyzer")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "trend_analyzer_v1.txt").read_text()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
}


class TrendAnalyzerError(RuntimeError):
    """Phase 0 produced no usable output. Caller MUST abort the run."""


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Tolerate ```json ... ``` fences and leading/trailing prose."""
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Try to find the outermost {...} substring
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise TrendAnalyzerError(f"Could not parse JSON: {e}") from e


def analyze_trends(
    conn,
    date: str,
    run_type: str,
    cost_tracker: CostTracker,
) -> dict:
    """Returns the parsed dict {trends, sector_rotation, trend_summary}.

    Side effects:
      - One row in trend_analyses per trend (replace-on-conflict).
      - cost_tracker.add_call() called once for the Claude billing.

    Raises:
      TrendAnalyzerError if the response is unparseable or has zero trends.
      CostCapExceeded propagates from cost_tracker.add_call().
    """
    user_msg = (
        f"Today is {date}. Run type: {run_type}. "
        "Use web_search 3-5 times to gather evidence on dominant short-term "
        "market trends, then return the JSON object defined in your system prompt."
    )

    result = call_claude(
        model=MODEL,
        system=SYSTEM_PROMPT,
        user=user_msg,
        max_tokens=MAX_TOKENS,
        tools=[WEB_SEARCH_TOOL],
    )

    cost_tracker.add_call(
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cache_read_tokens=result.cache_read_tokens,
        cache_creation_tokens=result.cache_creation_tokens,
        web_search_calls=result.web_search_calls,
    )

    parsed = _extract_json(result.text)
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
