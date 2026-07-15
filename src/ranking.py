"""Phase 4: Rank guardrail-passing analyses and persist to predictions.

Stocks: top 10 by probability_pct per direction (long / short).
Commodities + crypto: always all kept, regardless of score.
Every selected analysis is written as a learnable=True predictions row."""
import logging
from typing import Iterable

from src import db
from src.guardrails import GuardrailsChecker
import config

log = logging.getLogger("shares_future.ranking")

TOP_N = 10


def score_total(analysis: dict) -> float:
    """Weighted sum of the 8 score dimensions using config.DIMENSION_WEIGHTS."""
    s = analysis.get("scores", {})
    total = 0.0
    for dim, weight in config.DIMENSION_WEIGHTS.items():
        v = s.get(dim, {}).get("value")
        if v is not None:
            total += float(v) * weight
    return round(total, 3)


def _guardrail_filter(analyses: Iterable[dict]) -> list[dict]:
    """Drops analyses with direction='none' or that fail GuardrailsChecker, logging
    the reason for each rejection."""
    checker = GuardrailsChecker()
    kept: list[dict] = []
    for a in analyses:
        if a.get("direction") == "none":
            continue
        ok, errs = checker.check_analysis(a)
        if not ok:
            log.info(
                f"{a.get('ticker', '?')}: dropped by guardrails: {'; '.join(errs)}"
            )
            continue
        kept.append(a)
    return kept


def _to_prediction_row(
    analysis: dict, date: str, run_type: str, market_context: dict,
) -> dict:
    """Maps one guardrail-passing analysis dict onto the flat column layout
    expected by db.save_prediction()."""
    scores = analysis.get("scores", {})
    return {
        "date": date, "run_type": run_type,
        "asset_class": analysis.get("asset_class"),
        "ticker": analysis["ticker"], "direction": analysis["direction"],
        "entry_price": analysis["current_price"],
        "tp_price": analysis["tp_price"], "tp_pct": analysis.get("tp_pct"),
        "sl_price": analysis["sl_price"], "sl_pct": analysis.get("sl_pct"),
        "rr_ratio": analysis["rr_ratio"],
        "total_score": analysis.get("total_score") or score_total(analysis),
        "probability_pct": analysis.get("probability_pct"),
        "confidence": analysis.get("confidence"),
        "score_market_env": scores.get("market_environment", {}).get("value"),
        "score_company":    scores.get("company_quality", {}).get("value"),
        "score_valuation":  scores.get("valuation", {}).get("value"),
        "score_momentum":   scores.get("momentum", {}).get("value"),
        "score_risk":       scores.get("risk", {}).get("value"),
        "score_sector":     scores.get("sector_trend", {}).get("value"),
        "score_catalyst":   scores.get("catalyst", {}).get("value"),
        "score_policy":     scores.get("policy_risk", {}).get("value"),
        "atr_pct": None, "rsi_at_entry": None, "volume_ratio": None,
        "market_regime": market_context.get("market_regime"),
        "vix_at_prediction": market_context.get("vix_level"),
        "sector": market_context.get("sector"),
        "trend_boost": None,
        "earnings_warning": bool(analysis.get("earnings_warning")),
        "summary": analysis.get("summary"),
        "learnable": True,
        "hold_days_recommended": analysis.get("hold_days_recommended"),
        "intraday_range_pct": analysis.get("intraday_range_pct"),
    }


def rank_and_persist(
    conn,
    date: str,
    run_type: str,
    stock_analyses: list[dict],
    commodity_crypto_analyses: list[dict],
    market_context: dict,
) -> dict:
    """Returns {top_long, top_short, commodities_crypto} (each a list of dicts)
    and writes a predictions row per selected analysis. Order within each list
    is by probability_pct descending."""
    kept_stocks = _guardrail_filter(stock_analyses)
    kept_cc     = _guardrail_filter(commodity_crypto_analyses)

    longs  = sorted(
        [a for a in kept_stocks if a["direction"] == "long"],
        key=lambda a: a.get("probability_pct") or 0, reverse=True,
    )[:TOP_N]
    shorts = sorted(
        [a for a in kept_stocks if a["direction"] == "short"],
        key=lambda a: a.get("probability_pct") or 0, reverse=True,
    )[:TOP_N]

    for a in (*longs, *shorts, *kept_cc):
        db.save_prediction(conn, _to_prediction_row(
            a, date=date, run_type=run_type, market_context=market_context,
        ))

    log.info(
        f"Phase 4 done: {len(longs)} long, {len(shorts)} short, "
        f"{len(kept_cc)} commodity/crypto persisted"
    )
    return {
        "top_long": longs,
        "top_short": shorts,
        "commodities_crypto": kept_cc,
    }
