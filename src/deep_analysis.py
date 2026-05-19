"""Phase 3: Policy monitor (1× per run) + per-asset deep analysis with web search.

Both callables use Sonnet + server-side web_search. The 8-dimension score is
returned verbatim from the model and validated by guardrails.py downstream.
Per-asset failures are caught and logged so a single broken ticker never aborts
the run. Only CostCapExceeded (from cost_tracker) is fatal."""
import json
import logging
from pathlib import Path

from src.cost_tracker import CostTracker
from src.utils import call_claude, extract_json_blob, WEB_SEARCH_TOOL

log = logging.getLogger("shares_future.deep_analysis")

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
DEEP_SYSTEM_PROMPT = (PROMPT_DIR / "deep_analysis_v1.txt").read_text()
POLICY_SYSTEM_PROMPT = (PROMPT_DIR / "policy_monitor_v1.txt").read_text()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS_DEEP = 4096
MAX_TOKENS_POLICY = 3072


class DeepAnalysisError(RuntimeError):
    """Per-asset deep_analysis call produced unparseable output."""


class PolicyMonitorError(RuntimeError):
    """Policy monitor failed to produce parseable output."""


def run_policy_monitor(
    date: str, run_type: str, cost_tracker: CostTracker,
) -> dict:
    """Single Sonnet+web_search call. Returns
    {policy_risk_level, events, summary}. Tolerates empty events list."""
    user_msg = (
        f"Today is {date}. Run type: {run_type}. "
        "Use web_search 2-5 times to surface market-moving policy/geopolitics "
        "events from the last 48h. Then return the JSON object defined in your "
        "system prompt."
    )
    result = call_claude(
        model=MODEL, system=POLICY_SYSTEM_PROMPT, user=user_msg,
        max_tokens=MAX_TOKENS_POLICY, tools=[WEB_SEARCH_TOOL],
    )
    cost_tracker.add_from_result(result)
    parsed = extract_json_blob(result.text, PolicyMonitorError)
    if "events" not in parsed or "policy_risk_level" not in parsed:
        raise PolicyMonitorError(
            "Policy monitor response missing required keys "
            "(policy_risk_level, events)"
        )
    log.info(
        f"Policy monitor: level={parsed['policy_risk_level']} "
        f"events={len(parsed['events'])} cost={cost_tracker.total_eur:.3f} EUR"
    )
    return parsed


def _build_user_message(
    ticker_data: dict,
    quick_filter_result: dict,
    trend_context: dict,
    policy_context: dict,
) -> str:
    parts = [
        "TREND CONTEXT:", json.dumps(trend_context, ensure_ascii=False),
        "\nPOLICY CONTEXT:", json.dumps(policy_context, ensure_ascii=False),
        "\nQUICK FILTER PRE-SCORE:", json.dumps(quick_filter_result, ensure_ascii=False),
        "\nTICKER SNAPSHOT:", json.dumps(ticker_data, ensure_ascii=False),
        "\nReturn the JSON object defined in your system prompt for THIS one ticker.",
    ]
    return "\n".join(parts)


def analyze_asset(
    ticker_data: dict,
    quick_filter_result: dict,
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> dict | None:
    """Deep-analyze one asset. Returns the parsed analysis dict, or None if the
    quick-filter excluded the ticker (no Claude call made). Raises DeepAnalysisError
    on unparseable output — the caller (analyze_assets loop) must catch."""
    if quick_filter_result.get("exclude"):
        log.info(f"{ticker_data.get('ticker')}: skipped by quick_filter exclude")
        return None

    user_msg = _build_user_message(
        ticker_data=ticker_data,
        quick_filter_result=quick_filter_result,
        trend_context=trend_context,
        policy_context=policy_context,
    )
    result = call_claude(
        model=MODEL, system=DEEP_SYSTEM_PROMPT, user=user_msg,
        max_tokens=MAX_TOKENS_DEEP, tools=[WEB_SEARCH_TOOL],
    )
    cost_tracker.add_from_result(result)
    parsed = extract_json_blob(result.text, DeepAnalysisError)
    return parsed


def analyze_assets(
    ticker_datas: list[dict],
    quick_filter_results: list[dict],
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """Sequentially deep-analyze each ticker. Per-asset failures are caught and
    logged so a single broken ticker never aborts the run. CostCapExceeded
    propagates (the orchestrator handles partial-run e-mails)."""
    qf_by_ticker = {q["ticker"]: q for q in quick_filter_results}
    out: list[dict] = []
    for td in ticker_datas:
        t = td["ticker"]
        qf = qf_by_ticker.get(t)
        if qf is None:
            log.warning(f"{t}: no quick_filter result, skipping deep_analysis")
            continue
        try:
            a = analyze_asset(
                ticker_data=td, quick_filter_result=qf,
                trend_context=trend_context, policy_context=policy_context,
                cost_tracker=cost_tracker,
            )
        except DeepAnalysisError as e:
            log.warning(f"{t}: deep_analysis failed: {e}")
            continue
        if a is not None:
            out.append(a)
    log.info(
        f"Phase 3 done: {len(out)} analyses produced, "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return out
