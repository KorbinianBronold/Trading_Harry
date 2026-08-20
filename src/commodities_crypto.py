"""Phase 3b: Commodities + Crypto deep analysis.

Same Sonnet + web_search shape as Phase 3, with a dedicated prompt and a
per-run Fear & Greed fetch injected as extra_context. The 7 assets are always
analysed regardless of trend/quick-filter (Spec 6: no funnel, no cutoff, no
exception).

Batched by asset_class (commodity vs crypto) since 2026-08-19: was one call
per asset (7 sequential calls, ~40s each) until a runtime check found Phase 3b
alone taking ~4.8min of a 16min pre_market run. Grouping mirrors
deep_analysis.build_batches()'s sub-sector grouping -- the shared macro lens
(rates/USD for commodities, Fear&Greed/dominance for crypto) is only really
shared within one asset_class."""
import json
import logging
from pathlib import Path

import requests

from src.cost_tracker import CostTracker
from src.utils import call_claude, extract_json_blob, WEB_SEARCH_TOOL

log = logging.getLogger("shares_future.commodities_crypto")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "commodities_crypto_v3.txt").read_text()

MODEL = "claude-sonnet-5"
FEAR_GREED_URL = "https://api.alternative.me/fng/"
FEAR_GREED_TIMEOUT_SEC = 5

# Gleiche Herleitung wie TOKENS_PER_TICKER_DEEP (deep_analysis.py, C.10): die
# alte Einzel-Asset-Decke war 3584 fuer EIN Asset -- das wird jetzt der
# Pro-Asset-Anteil, die Reserve deckt nur den JSON-Rahmen ({"results": [...]}).
#
# ⚠️ 2026-08-20-Migration auf claude-sonnet-5 (adaptives Denken standardmaessig
# an, Denk- und Antworttokens teilen sich die max_tokens-Decke): 3584 reicht
# NICHT verlaesslich. Der erste Messlauf verfuehrte zum Gegenteil -- dort liefen
# beide Batches (n=3, n=4) im ersten Versuch sauber durch, waehrend die
# deep_analysis-Batches kappten. Der Verifikationslauf danach kappte dann den
# n=3-Batch bei max_tokens=10952, bei identischem Code und identischer Decke.
#
# Das ist der eigentliche Befund dieser Migration und der Grund, warum hier
# ueberhaupt eine Zahl steht statt "gemessen, passt": ein einzelner sauberer
# Durchlauf beweist unter adaptivem Denken NICHTS. Genau dieselbe Nicht-
# Determiniertheit traf Phase 0 (trend_analyzer) in umgekehrter Reihenfolge.
# Demonstriert ausreichend war die verdoppelte Decke, 21904/3 = ~7300 je Asset;
# 8192 liegt darueber und kostet nur, was es auch nutzt.
TOKENS_PER_ASSET_CC = 8192
BATCH_TOKEN_RESERVE_CC = 200
MAX_TOKENS_CC_MIN = 4096

# Wie deep_analysis.TRUNCATION_RETRY_FACTOR: eine identische Wiederholung nach
# einer Kappung kaeme identisch zurueck, die Wiederholung bekommt mehr Platz.
TRUNCATION_RETRY_FACTOR = 2


class CommoditiesCryptoError(RuntimeError):
    """Batch commodities/crypto call produced unparseable output."""


class BatchTruncatedError(CommoditiesCryptoError):
    """Die Batch-Antwort lief in max_tokens und ist abgeschnitten -- die
    Wiederholung braucht mehr Platz, nicht dieselbe Anfrage nochmal."""


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


def max_tokens_for_batch(n: int) -> int:
    """Output-Token-Budget fuer einen Batch von n Assets."""
    return max(MAX_TOKENS_CC_MIN, n * TOKENS_PER_ASSET_CC + BATCH_TOKEN_RESERVE_CC)


def build_batches(ticker_datas: list[dict]) -> list[list[dict]]:
    """Gruppiert die Assets nach asset_class (commodity/crypto) -- bei den
    fixen 7 Assets ergibt das exakt 2 Batches (3 + 4) statt 7 Einzelcalls.
    Deterministisch: innerhalb einer Klasse alphabetisch nach Ticker,
    Klassen alphabetisch."""
    by_class: dict[str, list[dict]] = {}
    for td in ticker_datas:
        by_class.setdefault(td.get("asset_class") or "", []).append(td)

    batches = [
        sorted(by_class[cls], key=lambda t: t["ticker"])
        for cls in sorted(by_class)
    ]
    log.info(
        f"Phase 3b: {len(ticker_datas)} Assets in {len(batches)} Batches "
        f"(Groessen: {[len(b) for b in batches]})"
    )
    return batches


def _build_batch_user_message(
    ticker_datas: list[dict],
    trend_context: dict,
    policy_context: dict,
    extra_context: dict,
) -> str:
    """Komponiert die User-Message fuer einen ganzen Batch: gemeinsamer Trend-,
    Policy- und Extra-Kontext einmal, dann je Asset ein Eintrag."""
    parts = [
        "TREND CONTEXT:", json.dumps(trend_context, ensure_ascii=False),
        "\nPOLICY CONTEXT:", json.dumps(policy_context, ensure_ascii=False),
        "\nEXTRA CONTEXT:", json.dumps(extra_context, ensure_ascii=False),
        "\nBATCH (one asset per line, JSON):",
    ]
    for td in ticker_datas:
        parts.append(json.dumps(td, ensure_ascii=False))
    parts.append(
        "\nReturn the JSON object defined in your system prompt with one entry "
        "per asset above, in the same order."
    )
    return "\n".join(parts)


def analyze_batch(
    ticker_datas: list[dict],
    trend_context: dict,
    policy_context: dict,
    extra_context: dict,
    cost_tracker: CostTracker,
    max_tokens_override: int | None = None,
) -> tuple[list[dict], list[str]]:
    """Analysiert einen ganzen Asset-Klassen-Batch in EINEM gestreamten
    Sonnet-Call. Rueckgabe: (analyses, missing_tickers) -- gelieferte Analysen
    werden immer uebernommen, auch wenn Assets fehlen.

    Wirft CommoditiesCryptoError, wenn die Antwort als GANZES unbrauchbar ist;
    bei einer Kappung (stop_reason == 'max_tokens') die Unterklasse
    BatchTruncatedError, damit der Aufrufer mit mehr Platz wiederholen kann."""
    if not ticker_datas:
        return [], []

    user_msg = _build_batch_user_message(
        ticker_datas, trend_context, policy_context, extra_context)
    max_tokens = max_tokens_override or max_tokens_for_batch(len(ticker_datas))

    result = call_claude(
        model=MODEL, system=SYSTEM_PROMPT, user=user_msg,
        max_tokens=max_tokens, tools=[WEB_SEARCH_TOOL], stream=True,
    )
    cost_tracker.add_from_result(result)

    if getattr(result, "stop_reason", None) == "max_tokens":
        raise BatchTruncatedError(
            f"Batch-Antwort bei max_tokens={max_tokens} abgeschnitten "
            f"(stop_reason=max_tokens, {len(ticker_datas)} Assets) -- ein "
            f"abgeschnittenes Ergebnis wird nicht verwertet"
        )

    parsed = extract_json_blob(result.text, CommoditiesCryptoError)
    results = parsed.get("results")
    if not isinstance(results, list):
        raise CommoditiesCryptoError("Batch-Antwort ohne 'results'-Liste")

    by_ticker = {r.get("ticker"): r for r in results if isinstance(r, dict)}

    analyses, missing = [], []
    for td in ticker_datas:
        t = td["ticker"]
        a = by_ticker.get(t)
        if a is None:
            missing.append(t)
            continue
        analyses.append(a)

    if missing:
        log.warning(
            f"Batch lieferte {len(analyses)}/{len(ticker_datas)} Assets; "
            f"fehlend: {', '.join(missing)}"
        )
    log.info(
        f"Batch ({len(ticker_datas)} Assets) fertig: {len(analyses)} Analysen, "
        f"{result.web_search_calls} Websuchen, "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return analyses, missing


def _run_one_batch_with_recovery(
    batch: list[dict],
    trend_context: dict,
    policy_context: dict,
    extra_context: dict,
    cost_tracker: CostTracker,
) -> tuple[list[dict], list[str]]:
    """Einmal wiederholen, dann aufgeben -- kein Halbieren wie in
    deep_analysis.py: die Batches sind mit hoechstens 4 Assets (asset_class-
    Gruppierung der 7 fixen Commodities/Crypto) bereits so klein, dass eine
    weitere Aufteilung kaum noch Call-Overhead spart.

    Bei einer Kappung bekommt die Wiederholung TRUNCATION_RETRY_FACTOR-fach
    Platz -- eine identische Anfrage mit derselben Decke kaeme identisch
    abgeschnitten zurueck (deep_analysis.py, C.9).

    CostCapExceeded laeuft ungehindert durch, wie im Stocks-Pfad."""
    faktor = 1
    last_error: Exception | None = None

    for versuch in (1, 2):
        override = max_tokens_for_batch(len(batch)) * faktor if faktor > 1 else None
        try:
            return analyze_batch(
                ticker_datas=batch, trend_context=trend_context,
                policy_context=policy_context, extra_context=extra_context,
                cost_tracker=cost_tracker, max_tokens_override=override,
            )
        except BatchTruncatedError as e:
            faktor = TRUNCATION_RETRY_FACTOR
            last_error = e
            log.warning(
                f"Batch-Versuch {versuch}/2 abgeschnitten ({len(batch)} Assets): "
                f"{e}. Naechster Versuch mit {TRUNCATION_RETRY_FACTOR}-facher Decke."
            )
        except CommoditiesCryptoError as e:
            last_error = e
            log.warning(
                f"Batch-Versuch {versuch}/2 fehlgeschlagen "
                f"({len(batch)} Assets): {e}"
            )

    tickers = [td["ticker"] for td in batch]
    log.warning(
        f"Batch ({', '.join(tickers)}) zweimal fehlgeschlagen, aufgegeben: "
        f"{last_error}"
    )
    return [], tickers


def analyze_commodities_and_crypto(
    ticker_datas: list[dict],
    trend_context: dict,
    policy_context: dict,
    extra_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """Phase 3b: batcht die 7 fixen Assets nach asset_class (2 Batches statt
    7 Einzelcalls) und analysiert jeden mit der Retry-Schale oben.

    CostCapExceeded propagiert weiterhin -- der Orchestrator verschickt die
    Teilergebnis-Mail."""
    analyses: list[dict] = []
    failed: list[str] = []
    for batch in build_batches(ticker_datas):
        a, f = _run_one_batch_with_recovery(
            batch=batch, trend_context=trend_context,
            policy_context=policy_context, extra_context=extra_context,
            cost_tracker=cost_tracker,
        )
        analyses.extend(a)
        failed.extend(f)

    if failed:
        log.warning(
            f"Phase 3b: {len(failed)} Assets ohne Analyse "
            f"({', '.join(sorted(failed))})"
        )
    log.info(
        f"Phase 3b done: {len(analyses)} analyses, "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return analyses
