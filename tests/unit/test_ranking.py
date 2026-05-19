from unittest.mock import MagicMock
import pytest

from src import db
from src.ranking import rank_and_persist, score_total


def _analysis(ticker: str, direction: str = "long", momentum: float = 7.0,
              hold_days: int = 2, intraday: float = 1.5,
              total_score: float = 7.5, prob: int = 68,
              rr: float = 2.5, current: float = 100.0,
              asset_class: str = "stock") -> dict:
    """Minimal guardrail-passing analysis dict, with knobs."""
    tp = current + 5.0 if direction == "long" else current - 5.0
    sl = current - 2.0 if direction == "long" else current + 2.0
    return {
        "ticker": ticker, "asset_class": asset_class,
        "direction": direction, "confidence": "high",
        "current_price": current, "tp_price": tp, "sl_price": sl,
        "tp_pct": 5.0, "sl_pct": 2.0, "rr_ratio": rr,
        "total_score": total_score, "probability_pct": prob,
        "hold_days_recommended": hold_days,
        "intraday_range_pct": intraday,
        "summary": "ok", "earnings_warning": False,
        "sources_used": ["a.com", "b.com"],
        "signal_consistency_check": "ok",
        "scores": {
            "market_environment": {"value": 7.0, "evidence": ["x", "y"]},
            "company_quality":    {"value": 7.0, "evidence": ["x", "y"]},
            "valuation":           {"value": 6.0, "evidence": ["x", "y"]},
            "momentum":           {"value": momentum, "evidence": ["x", "y"]},
            "risk":               {"value": 6.0, "evidence": ["x", "y"]},
            "sector_trend":       {"value": 7.0, "evidence": ["x", "y"]},
            "catalyst":           {"value": 7.0, "evidence": ["x", "y"]},
            "policy_risk":        {"value": 6.0, "evidence": ["x", "y"]},
        },
    }


def _market_ctx() -> dict:
    return {"vix_level": 14.0, "market_regime": "risk_on", "sector": "Technology"}


def test_score_total_uses_dimension_weights():
    a = _analysis("AAPL", momentum=8.0)
    t = score_total(a)
    assert 6.0 < t < 8.5


def test_rank_and_persist_top_10_long_and_short(in_memory_db):
    db.init_schema(in_memory_db)
    stocks = (
        [_analysis(f"L{i}", direction="long", momentum=8.0, prob=70 - i)
         for i in range(15)]
        + [_analysis(f"S{i}", direction="short", momentum=3.0, prob=70 - i)
           for i in range(15)]
    )
    out = rank_and_persist(
        conn=in_memory_db, date="2026-05-19", run_type="close",
        stock_analyses=stocks, commodity_crypto_analyses=[],
        market_context=_market_ctx(),
    )
    assert len(out["top_long"]) == 10
    assert len(out["top_short"]) == 10
    assert out["top_long"][0]["probability_pct"] >= out["top_long"][-1]["probability_pct"]
    rows = in_memory_db.execute(
        "SELECT direction, COUNT(*) AS n FROM predictions GROUP BY direction"
    ).fetchall()
    counts = {r["direction"]: r["n"] for r in rows}
    assert counts["long"] == 10
    assert counts["short"] == 10


def test_rank_drops_guardrail_failures(in_memory_db):
    db.init_schema(in_memory_db)
    good = _analysis("AAPL", momentum=8.0)
    bad_hold = _analysis("BAD1", momentum=8.0, hold_days=5)
    bad_range = _analysis("BAD2", momentum=8.0, intraday=0.5)
    bad_momentum = _analysis("BAD3", direction="long", momentum=3.0)
    out = rank_and_persist(
        conn=in_memory_db, date="2026-05-19", run_type="close",
        stock_analyses=[good, bad_hold, bad_range, bad_momentum],
        commodity_crypto_analyses=[],
        market_context=_market_ctx(),
    )
    tickers = [p["ticker"] for p in out["top_long"]]
    assert tickers == ["AAPL"]


def test_rank_drops_direction_none(in_memory_db):
    db.init_schema(in_memory_db)
    a = _analysis("AAPL", momentum=8.0)
    a["direction"] = "none"
    out = rank_and_persist(
        conn=in_memory_db, date="2026-05-19", run_type="close",
        stock_analyses=[a], commodity_crypto_analyses=[],
        market_context=_market_ctx(),
    )
    assert out["top_long"] == []
    assert out["top_short"] == []


def test_rank_keeps_all_commodities_crypto(in_memory_db):
    db.init_schema(in_memory_db)
    cc = [
        _analysis("GC=F", asset_class="commodity"),
        _analysis("SI=F", asset_class="commodity"),
        _analysis("BTC-USD", asset_class="crypto"),
    ]
    out = rank_and_persist(
        conn=in_memory_db, date="2026-05-19", run_type="close",
        stock_analyses=[], commodity_crypto_analyses=cc,
        market_context=_market_ctx(),
    )
    assert {a["ticker"] for a in out["commodities_crypto"]} == {"GC=F", "SI=F", "BTC-USD"}


def test_rank_persists_predictions_with_score_dimensions(in_memory_db):
    db.init_schema(in_memory_db)
    a = _analysis("AAPL", momentum=8.0)
    rank_and_persist(
        conn=in_memory_db, date="2026-05-19", run_type="close",
        stock_analyses=[a], commodity_crypto_analyses=[],
        market_context=_market_ctx(),
    )
    row = in_memory_db.execute(
        "SELECT score_momentum, score_company, hold_days_recommended, "
        "intraday_range_pct, learnable FROM predictions WHERE ticker='AAPL'"
    ).fetchone()
    assert row["score_momentum"] == 8.0
    assert row["hold_days_recommended"] == 2
    assert row["intraday_range_pct"] == 1.5
    assert row["learnable"] == 1
