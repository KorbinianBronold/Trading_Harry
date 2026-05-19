"""Phase 3b: Commodities + Crypto deep analysis.

Same Sonnet + web_search shape as Phase 3, with a dedicated prompt and a
per-run Fear & Greed fetch injected as extra_context. The 7 assets are always
analysed regardless of trend/quick-filter, but per-asset failures are caught
so a single broken call never aborts the run."""
import json
import logging
from pathlib import Path

import requests

from src.cost_tracker import CostTracker
from src.utils import call_claude, extract_json_blob, WEB_SEARCH_TOOL

log = logging.getLogger("shares_future.commodities_crypto")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "commodities_crypto_v1.txt").read_text()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 3584
FEAR_GREED_URL = "https://api.alternative.me/fng/"
FEAR_GREED_TIMEOUT_SEC = 5


class CommoditiesCryptoError(RuntimeError):
    """Per-asset commodities/crypto call produced unparseable output."""


def fetch_fear_greed() -> dict | None:
    """Returns {value:int, label:str} or None on any failure."""
    try:
        r = requests.get(FEAR_GREED_URL, timeout=FEAR_GREED_TIMEOUT_SEC)
        r.raise_for_status()
        d = r.json()["data"][0]
        return {"value": int(d["value"]), "label": d["value_classification"]}
    except Exception as e:  # broad on purpose: optional enrichment
        log.warning(f"fetch_fear_greed failed: {e}")
        return None


def _build_user_message(
    ticker_data: dict,
    trend_context: dict,
    policy_context: dict,
    extra_context: dict,
) -> str:
    parts = [
        "TREND CONTEXT:", json.dumps(trend_context, ensure_ascii=False),
        "\nPOLICY CONTEXT:", json.dumps(policy_context, ensure_ascii=False),
        "\nEXTRA CONTEXT:", json.dumps(extra_context, ensure_ascii=False),
        "\nASSET SNAPSHOT:", json.dumps(ticker_data, ensure_ascii=False),
        "\nReturn the JSON object defined in your system prompt for THIS one asset.",
    ]
    return "\n".join(parts)


def analyze_asset(
    ticker_data: dict,
    trend_context: dict,
    policy_context: dict,
    extra_context: dict,
    cost_tracker: CostTracker,
) -> dict:
    """Deep-analyze ONE commodity or crypto. Raises CommoditiesCryptoError on
    unparseable response — caller catches in the loop."""
    user_msg = _build_user_message(
        ticker_data=ticker_data,
        trend_context=trend_context,
        policy_context=policy_context,
        extra_context=extra_context,
    )
    result = call_claude(
        model=MODEL, system=SYSTEM_PROMPT, user=user_msg,
        max_tokens=MAX_TOKENS, tools=[WEB_SEARCH_TOOL],
    )
    cost_tracker.add_from_result(result)
    return extract_json_blob(result.text, CommoditiesCryptoError)


def analyze_commodities_and_crypto(
    ticker_datas: list[dict],
    trend_context: dict,
    policy_context: dict,
    extra_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """Loops the 7 fixed assets. Per-asset failures are caught and logged so a
    single broken call never aborts the run. CostCapExceeded propagates."""
    out: list[dict] = []
    for td in ticker_datas:
        t = td.get("ticker", "?")
        try:
            a = analyze_asset(
                ticker_data=td, trend_context=trend_context,
                policy_context=policy_context, extra_context=extra_context,
                cost_tracker=cost_tracker,
            )
        except CommoditiesCryptoError as e:
            log.warning(f"{t}: commodities_crypto failed: {e}")
            continue
        out.append(a)
    log.info(
        f"Phase 3b done: {len(out)} analyses, "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return out
