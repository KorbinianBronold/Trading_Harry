"""Orchestrator. Dispatches by --run-type.

Owns the single CostTracker per run. Phase 0 (trend) failure aborts the run by
re-raising; the GH Actions step turns red and the user is alerted via the
workflow's email-on-failure notification. Cost-cap aborts produce a partial
e-mail with the warning bar."""
import argparse
import logging
import sys
import traceback
from datetime import date as date_cls, datetime, timedelta
from zoneinfo import ZoneInfo

import config
from src import db
from src.cost_tracker import CostTracker, CostCapExceeded
from src.data_collector import collect
from src.sector_momentum import collect_sector_momentum
from src.trend_analyzer import analyze_trends, TrendAnalyzerError
from src.quick_filter import quick_filter_batch
from src.deep_analysis import run_policy_monitor, analyze_assets
from src.commodities_crypto import (
    analyze_commodities_and_crypto, fetch_fear_greed,
)
from src.market_context import fetch_market_context, MarketContextError
from src.portfolio_check import check_open_positions
from src.ranking import rank_and_persist
from src.evaluator import evaluate_open_predictions
from src import signal_checks
from src.revalidation import revalidate_one, RevalidationError
from src.email_sender import (
    send_daily_email, send_weekly_email, generate_daily_briefing,
    send_error_email,
)
from src.providers.finnhub_provider import FinnhubProvider
from src.providers.capital_provider import CapitalComProvider

log = logging.getLogger("shares_future.main")

BERLIN = ZoneInfo("Europe/Berlin")

RUN_TYPES = ["pre_market", "trade_proposals", "close", "weekly"]


class MailDeliveryError(RuntimeError):
    """Die Analyse lief vollstaendig durch und ist persistiert — nur der
    Mailversand scheiterte (B-10). Eigener Typ, damit Zustellprobleme nicht mit
    Analysefehlern verwechselt werden."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parses CLI args: --run-type (required), --date, --db-path."""
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


def _forced_candidates(price_provider) -> set[str]:
    """Phase 1c (B.4): Ticker mit offener Capital.com-Position. Sie muessen in
    Phase 3, egal was der Quick-Filter sagt — es haengt echtes Geld daran.

    Epics ohne Gegenstueck in unserer Ticker-Liste (von Hand eroeffnete
    Fremdpositionen) werden geloggt und uebersprungen: fuer sie gibt es keine
    Indikator-Daten."""
    from src.providers.capital_provider import epic_to_ticker
    forced: set[str] = set()
    for pos in price_provider.get_open_positions():
        epic = pos.get("ticker")
        if not epic:
            continue
        ticker = epic_to_ticker(epic)
        if ticker is None:
            log.info(f"Offene Position {epic}: kein Ticker-Gegenstueck, uebersprungen")
            continue
        forced.add(ticker)
    if forced:
        log.info(f"Phase 1c: {len(forced)} Pflicht-Kandidaten aus offenen Positionen: "
                 f"{sorted(forced)}")
    return forced


def _apply_forced_candidates(
    quick_results: list[dict], forced: set[str],
) -> list[dict]:
    """Setzt exclude=False fuer jeden Pflicht-Kandidaten aus Phase 1c, damit
    Phase 3 ihn garantiert analysiert."""
    for q in quick_results:
        if q.get("ticker") in forced:
            q["exclude"] = False
    return quick_results


def _aggregate_yesterday_outcomes(conn, today: str) -> dict:
    """Aggregates yesterday's evaluated outcomes into long/short hit counts and
    total P&L, for the daily e-mail's performance footer."""
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
    """Full Phase 0–5 pipeline. Seit Sprint 3B / Plan 2 nur noch fuer pre_market —
    midday ist entfallen, trade_proposals hat einen eigenen, schlankeren Ablauf."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    db.cleanup_old_data(conn)
    cost_tracker = CostTracker()
    price_provider = CapitalComProvider()
    earnings_provider = FinnhubProvider()

    aborted_at: str | None = None
    # B-05: die Abbruch-Phase wird mitgefuehrt statt geraten. Jeder Phasenblock
    # im try setzt sie, bevor er laeuft.
    current_phase = "trend_analysis"
    payload = {
        "date": date, "run_type": run_type,
        "briefing": [],
        "portfolio_recs": [], "top_long": [], "top_short": [],
        "commodities_crypto": [], "trends": [],
        "skipped_tickers": [],
        "market_context": {},
        "yesterday_outcomes": {},
        "cost_summary": {},
    }

    # Phase 0 — fatal if it fails
    trend_context = analyze_trends(
        conn=conn, date=date, run_type=run_type, cost_tracker=cost_tracker,
    )
    payload["trends"] = trend_context.get("trends", [])

    try:
        current_phase = "market_context"
        # Phase 0b — Markt-Kontext (VIX, A/D-Ratio, Regime). Nicht fatal: schlaegt
        # der Call fehl, laeuft der Run mit leerem Kontext weiter. CostCapExceeded
        # faengt der aeussere Handler — Kosten-Abbruch schickt trotzdem Mail.
        market_ctx = {
            "vix_level": None, "vix_source": None, "advance_decline_ratio": None,
            "market_regime": None, "sector_rotation_in": None,
            "sector_rotation_out": None, "macro_summary": None,
        }
        try:
            market_ctx = fetch_market_context(
                date=date, run_type=run_type, cost_tracker=cost_tracker,
                price_provider=price_provider,
            )
            db.save_market_context(
                conn, {**market_ctx, "date": date, "run_type": run_type})
        except MarketContextError as e:
            log.warning(f"Markt-Kontext nicht ermittelbar, Run laeuft ohne: {e}")
        payload["market_context"] = market_ctx

        current_phase = "data_collection"
        # Phase 1 — Stocks data
        _tickers = config.SP500_FULL_TICKERS if config.USE_FULL_SP500 else config.SP500_MVP_TICKERS
        sp500_tds, skipped_sp = collect(
            tickers=_tickers,
            price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn, date=date, run_type=run_type,
        )
        current_phase = "data_collection_cc"
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

        current_phase = "open_positions"
        # Phase 1c — offene Positionen als Pflicht-Kandidaten (B.4)
        forced = _forced_candidates(price_provider)

        current_phase = "sector_momentum"
        # Phase 1d — beide Momentum-Signale je Sub-Sektor (B.3.1 / D9). Muss NACH
        # Phase 1 laufen: db_momentum mittelt die heutigen Bars aus price_history.
        # Nicht fatal — ein ETF-Ausfall darf keinen bezahlten Lauf kosten.
        sector_mom: dict[int, dict] = {}
        try:
            sector_mom = collect_sector_momentum(
                conn=conn, date=date, run_type=run_type,
                price_provider=price_provider,
            )
        except CostCapExceeded:
            # Muss vor dem blanken except stehen, sonst frisst der Auffang-Zweig
            # den Kosten-Abbruch und der Lauf laeuft ueber den Deckel hinaus weiter.
            raise
        except Exception as e:
            log.warning(f"Sektor-Momentum nicht ermittelbar, Run laeuft ohne: {e}")

        current_phase = "quick_filter"
        # Phase 2 — quick filter (stocks only)
        quick = quick_filter_batch(
            batch=sp500_tds, trend_context=trend_context,
            cost_tracker=cost_tracker,
        )
        quick = _apply_forced_candidates(quick, forced)

        current_phase = "policy_monitor"
        # Phase 3 policy monitor (1× for all of Phase 3 + 3b + 4a)
        policy_context = run_policy_monitor(
            date=date, run_type=run_type, cost_tracker=cost_tracker,
        )
        payload["briefing"] = generate_daily_briefing(trend_context, policy_context)

        current_phase = "deep_analysis"
        # Phase 3 deep analysis
        deep_stocks = analyze_assets(
            ticker_datas=sp500_tds,
            quick_filter_results=quick,
            trend_context=trend_context,
            policy_context=policy_context,
            cost_tracker=cost_tracker,
        )

        current_phase = "commodities_crypto"
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

        current_phase = "ranking"
        # Phase 4 — Ranking + persist predictions (market_ctx kommt aus Phase 0b)
        ranked = rank_and_persist(
            conn=conn, date=date, run_type=run_type,
            stock_analyses=deep_stocks,
            commodity_crypto_analyses=deep_cc,
            market_context=market_ctx,
            sector_momentum=sector_mom,
        )
        payload["top_long"]            = ranked["top_long"]
        payload["top_short"]           = ranked["top_short"]
        payload["commodities_crypto"]  = ranked["commodities_crypto"]

        current_phase = "portfolio_check"
        # Phase 4a — Portfolio-Check auf den FERTIGEN Phase-3-Analysen (B.5).
        # Die Mail-Reihenfolge bleibt davon unberuehrt: die Portfolio-Sektion ist
        # weiterhin die erste Sektion der Tagesmail (dokumentierte Invariante).
        analyses_by_ticker = {a["ticker"]: a for a in (deep_stocks + deep_cc)}
        portfolio_recs = check_open_positions(
            conn=conn, today=date, run_type=run_type,
            analyses_by_ticker=analyses_by_ticker,
            trend_context=trend_context, policy_context=policy_context,
            cost_tracker=cost_tracker,
        )
        payload["portfolio_recs"] = portfolio_recs

    except CostCapExceeded as e:
        log.warning(f"Run aborted in phase '{current_phase}': {e}")
        cost_tracker.aborted_at_phase = current_phase
        aborted_at = current_phase

    # Always: write cost summary + send mail (even on partial run)
    payload["yesterday_outcomes"] = _aggregate_yesterday_outcomes(conn, today=date)
    payload["cost_summary"] = cost_tracker.summary(run_type=run_type, date=date)
    db.save_cost_tracking(conn, payload["cost_summary"])

    # B-10: Zustellung vom Analyse-Erfolg trennen. Alles oben ist zu diesem
    # Zeitpunkt committet; ein Mailfehler darf daran nichts aendern und soll in
    # der Logzeile klar als Zustellproblem erkennbar sein, damit niemand die
    # Ursache in einer Analysephase sucht. Der Fehler wird trotzdem
    # weitergereicht — ein unbemerkter Mailausfall waere schlimmer als ein
    # roter Job.
    try:
        send_daily_email(
            payload=payload,
            api_key=config.RESEND_API_KEY,
            email_from=config.EMAIL_FROM, email_to=config.EMAIL_TO,
        )
    except Exception as e:
        log.error(
            f"Analyse vollstaendig durchgelaufen und persistiert "
            f"({len(payload['top_long'])} long, {len(payload['top_short'])} short, "
            f"{len(payload['commodities_crypto'])} commodity/crypto, "
            f"{payload['cost_summary'].get('total_eur')} EUR) — "
            f"nur der Mailversand scheiterte: {e}"
        )
        raise MailDeliveryError(str(e)) from e
    finally:
        conn.close()


def run_close(date: str, db_path: str) -> None:
    """Close-Run: DB Datenpflege only. No Claude, no email."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    price_provider = CapitalComProvider()
    n = evaluate_open_predictions(conn=conn, today=date, price_provider=price_provider)
    log.info(f"Close run: {n} predictions evaluated")
    db.cleanup_old_data(conn)
    conn.close()


def _persist_revision(
    conn, pred, verdict: dict, snapshot: dict, date: str,
    checks: list, momentum: tuple[float | None, float | None],
) -> int | None:
    """Setzt das Urteil des 16:10-Laufs nach der Tabelle aus Spec 6.3 um.

    Gibt die ID der neuen trade_proposals-Zeile zurueck, oder None, wenn keine
    entstand (Urteil 'gedreht' oder ein hart greifender Check). In beiden
    None-Faellen bleibt die pre_market-Zeile offen und wird regulaer ausgewertet —
    nur so laesst sich messen, ob die Ablehnung richtig lag."""
    etf_mom, db_mom = momentum
    ticker, direction = pred["ticker"], pred["direction"]

    if verdict["verdict"] == "gedreht":
        # E5: melden, nicht handeln. Das Gegensignal ist nie durch Phase 3
        # gelaufen — es haette keine Belege und kein analytisch hergeleitetes TP/SL.
        db.record_revision(conn, pred["id"], "gedreht")
        return None

    if signal_checks.blocks(checks):
        db.record_revision(conn, pred["id"], "verworfen")
        return None

    entry = snapshot.get("price") or pred["entry_price"]
    rr = signal_checks.recompute_rr_ratio(
        entry, pred["tp_price"], pred["sl_price"], direction)
    if rr is None or rr < config.RR_RATIO_MIN_HARD:
        db.log_guardrail_reject(conn, {
            "date": date, "run_type": "trade_proposals", "ticker": ticker,
            "direction": direction, "rule": "rr_ratio",
            "detail": f"R/R nach Opening {rr} < {config.RR_RATIO_MIN_HARD} "
                      f"(Einstieg {entry} statt {pred['entry_price']})",
            "enforced": 1,
            "sector_etf_momentum": etf_mom, "sector_db_momentum": db_mom,
        })
        db.record_revision(conn, pred["id"], "verworfen")
        return None

    new_id = db.save_prediction(conn, {
        "date": date, "run_type": "trade_proposals",
        "asset_class": pred["asset_class"], "ticker": ticker, "direction": direction,
        "entry_price": entry,
        "tp_price": pred["tp_price"], "tp_pct": pred["tp_pct"],
        "sl_price": pred["sl_price"], "sl_pct": pred["sl_pct"],
        "rr_ratio": round(rr, 2),
        "total_score": pred["total_score"],
        "probability_pct": verdict.get("probability_pct"),
        "confidence": pred["confidence"],
        "score_market_env": pred["score_market_env"],
        "score_company": pred["score_company"],
        "score_valuation": pred["score_valuation"],
        "score_momentum": pred["score_momentum"],
        "score_risk": pred["score_risk"],
        "score_sector": pred["score_sector"],
        "score_catalyst": pred["score_catalyst"],
        "score_policy": pred["score_policy"],
        "market_regime": pred["market_regime"],
        "vix_at_prediction": pred["vix_at_prediction"],
        "sector": pred["sector"],
        "earnings_warning": pred["earnings_warning"],
        "summary": verdict.get("reason") or pred["summary"],
        "learnable": True,
        "hold_days_recommended": pred["hold_days_recommended"],
        "intraday_range_pct": pred["intraday_range_pct"],
        "sector_etf_momentum": etf_mom, "sector_db_momentum": db_mom,
    })
    db.record_revision(conn, pred["id"], verdict["verdict"], superseded_by=new_id)
    return new_id


def run_trade_proposals(date: str, db_path: str) -> None:
    """Run-Type trade_proposals (16:10 Berlin): prueft die pre_market-Signale nach
    dem Opening-Rauschen billig nach und loest sie ab.

    Kein Phase 0 — die Megatrend-Analyse aendert sich nicht in 70 Minuten, der Run
    liest sie aus der DB. Der Policy-Monitor laeuft dagegen MIT Websuche: seit E1
    ist er die einzige Recherche des Laufs."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    cost_tracker = CostTracker()
    price_provider = CapitalComProvider()
    earnings_provider = FinnhubProvider()

    aborted_at: str | None = None
    current_phase = "market_context"
    payload = {
        "date": date, "run_type": "trade_proposals",
        "briefing": [], "portfolio_recs": [], "signal_changes": [],
        "commodities_crypto": [], "market_context": {},
        "cost_summary": {},
    }

    try:
        market_ctx = {"vix_level": None, "advance_decline_ratio": None,
                      "market_regime": None}
        try:
            market_ctx = fetch_market_context(
                date=date, run_type="trade_proposals", cost_tracker=cost_tracker,
                price_provider=price_provider,
            )
            db.save_market_context(
                conn, {**market_ctx, "date": date, "run_type": "trade_proposals"})
        except MarketContextError as e:
            log.warning(f"Markt-Kontext nicht ermittelbar, Run laeuft ohne: {e}")
        payload["market_context"] = market_ctx

        current_phase = "data_collection"
        _tickers = (config.SP500_FULL_TICKERS if config.USE_FULL_SP500
                    else config.SP500_MVP_TICKERS)
        sp_tds, _ = collect(
            tickers=_tickers, price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn, date=date, run_type="trade_proposals")
        cc_tickers = [d["ticker"] for d in build_commodity_crypto_inputs()]
        cc_tds, _ = collect(
            tickers=cc_tickers, price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn, date=date, run_type="trade_proposals")
        snapshots = {td["ticker"]: td for td in (sp_tds + cc_tds)}

        current_phase = "open_positions"
        _forced_candidates(price_provider)   # nur fuer den Log — Phase 4a sieht sie ohnehin

        current_phase = "sector_momentum"
        sector_mom: dict[int, dict] = {}
        try:
            sector_mom = collect_sector_momentum(
                conn=conn, date=date, run_type="trade_proposals",
                price_provider=price_provider)
        except CostCapExceeded:
            # Muss vor dem blanken except stehen, sonst frisst der Auffang-Zweig
            # den Kosten-Abbruch und der Lauf laeuft ueber den Deckel hinaus weiter.
            raise
        except Exception as e:
            log.warning(f"Sektor-Momentum nicht ermittelbar, Run laeuft ohne: {e}")

        current_phase = "policy_monitor"
        # Seit E1 die einzige Websuche des Laufs. Faellt sie aus, ist die
        # Re-Validierung rein preisbasiert — immer noch besser als gar keine.
        policy_context: dict = {"policy_risk_level": "unknown", "events": []}
        try:
            policy_context = run_policy_monitor(
                date=date, run_type="trade_proposals", cost_tracker=cost_tracker)
        except CostCapExceeded:
            # Dieselbe Reihenfolge wie beim Sektor-Momentum: sonst liefe der Lauf
            # ueber den Deckel hinaus weiter und die Kostenzeile nennte die
            # falsche Phase — genau der Fehler, den B-05 beseitigt hat.
            raise
        except Exception as e:
            log.warning(f"Policy-Monitor ausgefallen, Re-Validierung laeuft "
                        f"rein preisbasiert weiter: {e}")
            payload["briefing"] = ["⚠️ Policy-Monitor ausgefallen — "
                                   "keine Nachrichtenlage in dieser Prüfung."]

        current_phase = "revalidation"
        payload["signal_changes"] = _revalidate_all(
            conn=conn, date=date, snapshots=snapshots, sector_mom=sector_mom,
            market_ctx=market_ctx, policy_context=policy_context,
            cost_tracker=cost_tracker,
        )

        current_phase = "portfolio_check"
        # Der Morgenlauf sieht sector_rotation/macro_summary, weil sein
        # trend_context die ROHE Phase-0-Antwort ist (die Felder stehen dort als
        # Top-Level-Keys). trend_analyses persistiert diese Felder nie — nur die
        # Pro-Trend-Spalten —, load_trend_context() kann sie also nicht
        # rekonstruieren. Der frisch erhobene Markt-Kontext liefert inhaltlich
        # den naechstliegenden Ersatz (anderer Claude-Call, dieselbe Frage nach
        # Rotation/Makrolage): hier eingemischt, damit der Portfolio-Check nicht
        # aermer dasteht als am Morgen.
        trend_ctx = {
            **(db.load_trend_context(conn, date) or {}),
            "sector_rotation_in": market_ctx.get("sector_rotation_in"),
            "sector_rotation_out": market_ctx.get("sector_rotation_out"),
            "macro_summary": market_ctx.get("macro_summary"),
        }
        payload["portfolio_recs"] = check_open_positions(
            conn=conn, today=date, run_type="trade_proposals",
            analyses_by_ticker=snapshots,
            trend_context=trend_ctx,
            policy_context=policy_context, cost_tracker=cost_tracker,
        )

    except CostCapExceeded as e:
        log.warning(f"Run aborted in phase '{current_phase}': {e}")
        cost_tracker.aborted_at_phase = current_phase
        aborted_at = current_phase

    payload["cost_summary"] = cost_tracker.summary(
        run_type="trade_proposals", date=date)
    db.save_cost_tracking(conn, payload["cost_summary"])
    log.info(f"trade_proposals fertig: {len(payload['signal_changes'])} Signale "
             f"geprueft, {payload['cost_summary']['total_eur']} EUR"
             + (f", abgebrochen in {aborted_at}" if aborted_at else ""))
    conn.close()


def _revalidate_all(
    conn, date: str, snapshots: dict, sector_mom: dict,
    market_ctx: dict, policy_context: dict, cost_tracker: CostTracker,
) -> list[dict]:
    """Prueft jedes heutige offene pre_market-Signal nach und persistiert das
    Ergebnis. Gibt die Zeilen fuer die Mail zurueck.

    Ein Fehlschlag betrifft immer nur EIN Signal: die zugehoerige Zeile bleibt dann
    unangetastet offen und erscheint in der Mail als 'nicht geprueft'."""
    open_preds = db.load_predictions_for_revalidation(conn, date)
    log.info(f"Re-Validierung: {len(open_preds)} offene pre_market-Signale")

    counts = signal_checks.cluster_counts(conn, [p["ticker"] for p in open_preds])
    out: list[dict] = []
    for pred in open_preds:
        ticker = pred["ticker"]
        snapshot = snapshots.get(ticker, {})
        etf_mom, db_mom = signal_checks.momentum_for(conn, ticker, sector_mom)
        sector = db.get_ticker_sector(conn, ticker)
        sector_name = sector["name"] if sector else None
        checks = [c for c in (
            signal_checks.check_vix(pred["direction"], pred["confidence"],
                                    market_ctx.get("vix_level"), enforce=True),
            signal_checks.check_sector_momentum(pred["direction"], etf_mom, db_mom,
                                                enforce=True),
            signal_checks.check_cluster(sector_name,
                                        counts.get(sector_name or "", 0)),
        ) if c is not None]

        # E4: auch der 16:10-Lauf persistiert JEDEN angeschlagenen Check — sonst
        # zeigt die Guardrail-Statistik der Weekly-Mail nur die weiche Haelfte und
        # die enforced-Spalte waere wertlos.
        for c in checks:
            db.log_guardrail_reject(conn, {
                "date": date, "run_type": "trade_proposals", "ticker": ticker,
                "direction": pred["direction"], "rule": c.rule, "detail": c.detail,
                "enforced": 1 if c.enforced else 0,
                "sector_etf_momentum": etf_mom, "sector_db_momentum": db_mom,
            })

        try:
            verdict = revalidate_one(
                prediction=pred, snapshot=snapshot, checks=checks,
                relative_strength=signal_checks.compute_relative_strength(
                    conn, ticker, date),
                policy_context=policy_context, cost_tracker=cost_tracker,
            )
        except RevalidationError as e:
            log.warning(f"{ticker}: Re-Validierung fehlgeschlagen, Zeile bleibt "
                        f"unveraendert offen: {e}")
            # Dieselben Schluessel wie im Normalpfad unten (nur als None) — sonst
            # faellt ein spaeterer direkter Dict-Zugriff (statt .get()) bei einer
            # 'nicht_geprueft'-Zeile mit KeyError um.
            out.append({"ticker": ticker, "direction": pred["direction"],
                        "verdict": "nicht_geprueft",
                        "probability_before": pred["probability_pct"],
                        "probability_after": None,
                        "entry_window_low": None, "entry_window_high": None,
                        "reason": str(e), "checks": []})
            continue

        new_id = _persist_revision(
            conn=conn, pred=pred, verdict=verdict, snapshot=snapshot,
            date=date, checks=checks, momentum=(etf_mom, db_mom),
        )
        out.append({
            "ticker": ticker, "direction": pred["direction"],
            "verdict": "verworfen" if (new_id is None and
                                       verdict["verdict"] != "gedreht")
                       else verdict["verdict"],
            "probability_before": pred["probability_pct"],
            "probability_after": verdict.get("probability_pct"),
            "entry_window_low": verdict.get("entry_window_low"),
            "entry_window_high": verdict.get("entry_window_high"),
            "reason": verdict.get("reason"),
            "checks": [f"{c.rule}: {c.detail}" for c in checks],
        })
    return out


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
        payload=payload, api_key=config.RESEND_API_KEY,
        email_from=config.EMAIL_FROM, email_to=config.EMAIL_TO,
    )
    conn.close()


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: dispatches to the right run_* function by --run-type and
    e-mails a traceback (then exits 1) if the run raises unexpectedly."""
    ns = parse_args(argv)
    date = ns.date or datetime.now(BERLIN).date().isoformat()
    try:
        if ns.run_type == "pre_market":
            run_pipeline(run_type=ns.run_type, date=date, db_path=ns.db_path)
        elif ns.run_type == "trade_proposals":
            run_trade_proposals(date=date, db_path=ns.db_path)
        elif ns.run_type == "close":
            run_close(date=date, db_path=ns.db_path)
        elif ns.run_type == "weekly":
            run_weekly(date=date, db_path=ns.db_path)
        else:  # pragma: no cover — argparse validated
            sys.exit(2)
    except SystemExit:
        raise
    except Exception as exc:
        tb_text = traceback.format_exc()
        log.error(f"Run {ns.run_type} FAILED: {exc}\n{tb_text}")
        if config.RESEND_API_KEY and config.EMAIL_FROM and config.EMAIL_TO:
            try:
                send_error_email(
                    run_type=ns.run_type, date=date, exc=exc,
                    traceback_text=tb_text,
                    api_key=config.RESEND_API_KEY,
                    email_from=config.EMAIL_FROM, email_to=config.EMAIL_TO,
                )
            except Exception as mail_exc:
                log.error(f"Failed to send error email: {mail_exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
