"""Orchestrator. Dispatches by --run-type.

Owns the single CostTracker per run. Phase 0 (trend) failure aborts the run by
re-raising; the GH Actions step turns red and the user is alerted via the
workflow's email-on-failure notification. Cost-cap aborts produce a partial
e-mail with the warning bar."""
import argparse
import logging
import sys
from datetime import date as date_cls, datetime, timedelta
from zoneinfo import ZoneInfo

import config
from src import db
from src.cost_tracker import CostTracker, CostCapExceeded
from src.data_collector import collect
from src.trend_analyzer import analyze_trends, TrendAnalyzerError
from src.quick_filter import quick_filter_batch
from src.deep_analysis import run_policy_monitor, analyze_assets
from src.commodities_crypto import (
    analyze_commodities_and_crypto, fetch_fear_greed,
)
from src.portfolio_check import check_open_positions
from src.ranking import rank_and_persist
from src.evaluator import evaluate_open_predictions
from src.email_sender import (
    send_daily_email, send_weekly_email, generate_daily_briefing,
)
from src.providers.yfinance_provider import YFinanceProvider
from src.providers.finnhub_provider import FinnhubProvider

log = logging.getLogger("shares_future.main")

BERLIN = ZoneInfo("Europe/Berlin")

RUN_TYPES = ["pre_market", "midday", "close", "evaluate", "weekly", "position_check"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-type", required=True, choices=RUN_TYPES)
    parser.add_argument("--date", default=None,
                        help="ISO date (default: today Europe/Berlin)")
    parser.add_argument("--db-path", default=str(config.DB_PATH))
    return parser.parse_args(argv)


def build_commodity_crypto_inputs() -> list[dict]:
    """Returns 7 stub TickerData dicts (name + ticker + asset_class).
    data_collector populates indicators per ticker; here we list the universe."""
    out: list[dict] = []
    for name, t in config.COMMODITY_TICKERS.items():
        out.append({"ticker": t, "name": name, "asset_class": "commodity"})
    for name, t in config.CRYPTO_TICKERS.items():
        out.append({"ticker": t, "name": name, "asset_class": "crypto"})
    return out


def _aggregate_yesterday_outcomes(conn, today: str) -> dict:
    yesterday = (date_cls.fromisoformat(today) - timedelta(days=1)).isoformat()
    rows = conn.execute(
        """SELECT pred_direction, COUNT(*) AS n,
                  SUM(CASE WHEN correct_direction_eod THEN 1 ELSE 0 END) AS correct,
                  COALESCE(SUM(profit_loss_eur), 0) AS pl
           FROM (
             SELECT p.direction AS pred_direction,
                    o.correct_direction_eod, o.profit_loss_eur
             FROM outcomes o JOIN predictions p ON p.id = o.prediction_id
             WHERE o.evaluated_date = ?
           )
           GROUP BY pred_direction""",
        (yesterday,),
    ).fetchall()
    agg = {"long_correct": 0, "long_total": 0,
           "short_correct": 0, "short_total": 0, "total_pl_eur": 0.0}
    for r in rows:
        if r["pred_direction"] == "long":
            agg["long_total"]   = int(r["n"])
            agg["long_correct"] = int(r["correct"] or 0)
        elif r["pred_direction"] == "short":
            agg["short_total"]   = int(r["n"])
            agg["short_correct"] = int(r["correct"] or 0)
        agg["total_pl_eur"] += float(r["pl"] or 0.0)
    return agg


def load_recent_outcomes_aggregate(conn, today: str) -> dict:
    """7-day window for the weekly mail."""
    since = (date_cls.fromisoformat(today) - timedelta(days=7)).isoformat()
    rows = db.load_recent_outcomes(conn, since)
    long_t = [r for r in rows if r["pred_direction"] == "long"]
    short_t = [r for r in rows if r["pred_direction"] == "short"]
    def _agg(items):
        n = len(items)
        correct = sum(1 for r in items if r["correct_direction_eod"])
        pl = sum(r["profit_loss_eur"] or 0.0 for r in items)
        avg = round(pl / n, 2) if n else 0.0
        return n, correct, avg, pl
    ln, lc, la, lp = _agg(long_t)
    sn, sc, sa, sp = _agg(short_t)
    return {
        "long_total": ln, "long_correct": lc, "long_avg_pl": la,
        "short_total": sn, "short_correct": sc, "short_avg_pl": sa,
        "total_pl_eur": round(lp + sp, 2),
        "trades": [{
            "date": r["evaluated_date"], "ticker": r["ticker"],
            "direction": r["pred_direction"],
            "entry_price": r["entry_price"], "exit_price": r["price_after_eod"],
            "exit_reason": r["exit_reason"],
            "profit_loss_eur": r["profit_loss_eur"],
        } for r in rows],
    }


def run_pipeline(run_type: str, date: str, db_path: str) -> None:
    """Full Phase 0–5 pipeline for pre_market / midday / close."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    db.cleanup_old_data(conn)
    cost_tracker = CostTracker()
    price_provider = YFinanceProvider()
    earnings_provider = FinnhubProvider()

    aborted_at: str | None = None
    payload = {
        "date": date, "run_type": run_type,
        "briefing": [],
        "portfolio_recs": [], "top_long": [], "top_short": [],
        "commodities_crypto": [], "trends": [],
        "skipped_tickers": [],
        "yesterday_outcomes": {},
        "cost_summary": {},
    }

    # Phase 0 — fatal if it fails
    trend_context = analyze_trends(
        conn=conn, date=date, run_type=run_type, cost_tracker=cost_tracker,
    )
    payload["trends"] = trend_context.get("trends", [])

    try:
        # Phase 1 — Stocks data
        sp500_tds, skipped_sp = collect(
            tickers=config.SP500_MVP_TICKERS,
            price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn, date=date, run_type=run_type,
        )
        # Phase 1b — Commodities + Crypto data (separate collect for asset_class tagging)
        cc_inputs = build_commodity_crypto_inputs()
        cc_tickers = [d["ticker"] for d in cc_inputs]
        cc_tds_raw, skipped_cc = collect(
            tickers=cc_tickers,
            price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn, date=date, run_type=run_type,
        )
        # Annotate asset_class from the cc_inputs map
        by_ticker = {d["ticker"]: d for d in cc_inputs}
        cc_tds = []
        for td in cc_tds_raw:
            meta = by_ticker.get(td["ticker"], {})
            cc_tds.append({**td,
                           "asset_class": meta.get("asset_class", "commodity"),
                           "name": meta.get("name", td["ticker"])})

        payload["skipped_tickers"] = [
            r["ticker"] for r in conn.execute(
                "SELECT DISTINCT ticker FROM skipped_tickers WHERE date=?", (date,),
            ).fetchall()
        ]

        # Phase 2 — quick filter (stocks only)
        quick = quick_filter_batch(
            batch=sp500_tds, trend_context=trend_context,
            cost_tracker=cost_tracker,
        )

        # Phase 3 policy monitor (1× for all of Phase 3 + 3b + 4a)
        policy_context = run_policy_monitor(
            date=date, run_type=run_type, cost_tracker=cost_tracker,
        )
        payload["briefing"] = generate_daily_briefing(trend_context, policy_context)

        # Phase 3 deep analysis
        deep_stocks = analyze_assets(
            ticker_datas=sp500_tds,
            quick_filter_results=quick,
            trend_context=trend_context,
            policy_context=policy_context,
            cost_tracker=cost_tracker,
        )

        # Phase 3b commodities + crypto
        fg = fetch_fear_greed() or {}
        extra_context = {
            "fear_greed_value": fg.get("value"),
            "fear_greed_label": fg.get("label"),
        }
        deep_cc = analyze_commodities_and_crypto(
            ticker_datas=cc_tds, trend_context=trend_context,
            policy_context=policy_context, extra_context=extra_context,
            cost_tracker=cost_tracker,
        )

        # Phase 4a — Portfolio check (across all snapshots seen this run)
        snapshots_by_ticker = {td["ticker"]: td for td in (sp500_tds + cc_tds)}
        portfolio_recs = check_open_positions(
            conn=conn, today=date, run_type=run_type,
            snapshots_by_ticker=snapshots_by_ticker,
            trend_context=trend_context, policy_context=policy_context,
            cost_tracker=cost_tracker,
        )
        payload["portfolio_recs"] = portfolio_recs

        # Phase 4 — Ranking + persist predictions
        market_ctx = {
            "vix_level": None, "market_regime": None, "sector": None,
        }
        ranked = rank_and_persist(
            conn=conn, date=date, run_type=run_type,
            stock_analyses=deep_stocks,
            commodity_crypto_analyses=deep_cc,
            market_context=market_ctx,
        )
        payload["top_long"]            = ranked["top_long"]
        payload["top_short"]           = ranked["top_short"]
        payload["commodities_crypto"]  = ranked["commodities_crypto"]

    except CostCapExceeded as e:
        log.warning(f"Run aborted: {e}")
        cost_tracker.aborted_at_phase = _guess_aborted_phase(e)
        aborted_at = cost_tracker.aborted_at_phase

    # Always: write cost summary + send mail (even on partial run)
    payload["yesterday_outcomes"] = _aggregate_yesterday_outcomes(conn, today=date)
    payload["cost_summary"] = cost_tracker.summary(run_type=run_type, date=date)
    db.save_cost_tracking(conn, payload["cost_summary"])

    send_daily_email(
        payload=payload,
        api_key=config.SENDGRID_API_KEY,
        email_from=config.EMAIL_FROM, email_to=config.EMAIL_TO,
    )
    conn.close()


def _guess_aborted_phase(_exc: CostCapExceeded) -> str:
    """We don't have a precise phase from the exception — return a stable
    placeholder. The orchestrator could thread a phase name in later."""
    return "policy_monitor"


def run_close(date: str, db_path: str) -> None:
    """Close-Run: DB Datenpflege only. No Claude, no email."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    price_provider = YFinanceProvider()
    n = evaluate_open_predictions(conn=conn, today=date, price_provider=price_provider)
    log.info(f"Close run: {n} predictions evaluated")
    db.cleanup_old_data(conn)
    conn.close()


def run_evaluate(date: str, db_path: str) -> None:
    conn = db.connect(db_path)
    db.init_schema(conn)
    price_provider = YFinanceProvider()
    n = evaluate_open_predictions(
        conn=conn, today=date, price_provider=price_provider,
    )
    log.info(f"Evaluate run: {n} predictions closed")
    conn.close()


def run_weekly(date: str, db_path: str) -> None:
    conn = db.connect(db_path)
    db.init_schema(conn)
    agg = load_recent_outcomes_aggregate(conn, today=date)
    week_label = "KW" + date_cls.fromisoformat(date).strftime("%V")
    payload = {
        "week_label": week_label, **agg,
        "cost_summary": {"total_eur": 0.0, "cache_hit_rate": 0.0,
                         "input_tokens": 0, "output_tokens": 0,
                         "web_search_calls": 0, "aborted_at_phase": None},
    }
    send_weekly_email(
        payload=payload, api_key=config.SENDGRID_API_KEY,
        email_from=config.EMAIL_FROM, email_to=config.EMAIL_TO,
    )
    conn.close()


def main(argv: list[str] | None = None) -> None:
    ns = parse_args(argv)
    date = ns.date or datetime.now(BERLIN).date().isoformat()
    if ns.run_type in ("pre_market", "midday"):
        run_pipeline(run_type=ns.run_type, date=date, db_path=ns.db_path)
    elif ns.run_type == "close":
        run_close(date=date, db_path=ns.db_path)
    elif ns.run_type == "evaluate":
        run_evaluate(date=date, db_path=ns.db_path)
    elif ns.run_type == "weekly":
        run_weekly(date=date, db_path=ns.db_path)
    else:  # pragma: no cover — argparse validated
        sys.exit(2)


if __name__ == "__main__":
    main()
