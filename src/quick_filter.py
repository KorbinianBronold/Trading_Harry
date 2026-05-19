"""Phase 2: Haiku batch quick-filter.

Single Claude Haiku call per batch (no web search). Returns one scoring dict per
input ticker. No DB writes — caller consumes the list in-memory and feeds it to
Phase 3 (deep analysis) in a later plan.
"""
import json
import logging
from pathlib import Path

from src.cost_tracker import CostTracker
from src.utils import call_claude, extract_json_blob

log = logging.getLogger("shares_future.quick_filter")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "quick_filter_v1.txt").read_text()

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 4096


class QuickFilterError(RuntimeError):
    """Quick-filter output unparseable or incomplete."""


def _format_batch_for_prompt(batch: list[dict], trend_context: dict) -> str:
    """Compose a deterministic user message containing one snapshot per ticker."""
    parts = ["TREND CONTEXT:", json.dumps(trend_context, ensure_ascii=False)]
    parts.append("\nBATCH (one ticker per line, JSON):")
    for td in batch:
        parts.append(json.dumps(td, ensure_ascii=False))
    parts.append(
        "\nReturn the JSON object defined in your system prompt with one entry "
        "per ticker above, in the same order."
    )
    return "\n".join(parts)


def quick_filter_batch(
    batch: list[dict],
    trend_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """Score a batch of tickers in a single Haiku call.

    Returns a list of dicts, each: {ticker, long_score, short_score, confidence,
    evidence, exclude}. Output preserves input ordering by ticker.

    Raises:
      QuickFilterError on unparseable JSON or missing tickers in response.
      CostCapExceeded propagates from cost_tracker.add_call().
    """
    if not batch:
        return []

    user_msg = _format_batch_for_prompt(batch, trend_context)

    result = call_claude(
        model=MODEL,
        system=SYSTEM_PROMPT,
        user=user_msg,
        max_tokens=MAX_TOKENS,
    )

    cost_tracker.add_from_result(result)

    parsed = extract_json_blob(result.text, QuickFilterError)
    results = parsed.get("results")
    if not isinstance(results, list):
        raise QuickFilterError("Response missing 'results' list")

    by_ticker = {r.get("ticker"): r for r in results}
    expected = {td["ticker"] for td in batch}
    missing = expected - set(by_ticker.keys())
    if missing:
        raise QuickFilterError(
            f"Quick filter response missing tickers: {sorted(missing)}"
        )

    ordered = [by_ticker[td["ticker"]] for td in batch]
    log.info(
        f"Phase 2 done: {len(ordered)} scored, "
        f"{sum(1 for r in ordered if r.get('exclude'))} excluded, "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return ordered
