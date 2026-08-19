"""Orchestrator. Dispatches by --run-type.

Owns the single CostTracker per run. Phase 0 (trend) failure aborts the run by
re-raising; the GH Actions step turns red and the user is alerted via the
workflow's email-on-failure notification. Cost-cap aborts produce a partial
e-mail with the warning bar."""
import argparse
import logging
import sys
import traceback
from datetime import date as date_cls, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import config
from src import db
from src import signal_window
from src.cost_tracker import CostTracker, CostCapExceeded
from src.data_collector import collect, run_phase_2b
from src.sector_momentum import collect_sector_momentum
from src.trend_analyzer import analyze_trends, TrendAnalyzerError
from src.broad_scan import broad_scan_batch, cutoff_candidates
from src.deep_analysis import run_policy_monitor, analyze_batches
from src.commodities_crypto import (
    analyze_commodities_and_crypto, fetch_fear_greed,
)
from src.market_context import fetch_market_context, MarketContextError
from src.portfolio_check import check_open_positions
from src.ranking import rank_and_persist
from src.evaluator import evaluate_open_predictions
from src.universe import full_universe, thin_history_tickers
from src import signal_checks
from src.revalidation import revalidate_one, RevalidationError
from src.email_sender import (
    send_daily_email, send_weekly_email, generate_daily_briefing,
    send_error_email, send_trade_proposals_email, send_final_close_email,
)
from src.providers.finnhub_provider import FinnhubProvider
from src.providers.capital_provider import CapitalComProvider

log = logging.getLogger("shares_future.main")

BERLIN = ZoneInfo("Europe/Berlin")

RUN_TYPES = ["pre_market", "trade_proposals", "final_close", "weekly"]


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


def _signal_context(
    tds: list[dict], sidecar: dict[str, dict],
    news_strength_by_ticker: dict[str, int] | None = None,
) -> dict[str, dict]:
    """Buendelt je Ticker die Werte, die Phase 4 (Ranking) braucht, aber weder
    im Claude-Analyse-Dict noch im td-Snapshot allein stehen: das
    Technik-Signal aus dem Sidecar, die drei C.1-Indikatoren, und (nur bei
    Aktien, ueber news_strength_by_ticker) den Phase-2-Scan-Wert.

    Getrennt von td gehalten aus demselben Grund wie der Sidecar selbst (R1):
    kein zusaetzlicher Key landet in einem der Claude-Prompts."""
    news_strength_by_ticker = news_strength_by_ticker or {}
    out: dict[str, dict] = {}
    for td in tds:
        t = td["ticker"]
        side = sidecar.get(t, {})
        out[t] = {
            "tech_direction": side.get("tech_direction"),
            "tech_agreement": side.get("tech_agreement"),
            "tech_adx_band":  side.get("tech_adx_band"),
            "tech_strength":  side.get("tech_strength"),
            "atr_pct":        td.get("atr_pct"),
            "rsi_14":         td.get("rsi_14"),
            "volume_ratio":   td.get("volume_ratio"),
            "earnings_in_days": td.get("earnings_in_days"),
            "news_strength":  news_strength_by_ticker.get(t),
        }
    return out


def _direction_split(rows: list) -> dict:
    """Baut die long/short-Zusammenfassung fuer eine Zeilenmenge -- extrahiert
    aus load_recent_outcomes_aggregate(), damit core und divergence dieselbe
    Rechnung nutzen, ohne sich zu vermischen (Spec 5.6)."""
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


def load_recent_outcomes_aggregate(conn, today: str) -> dict:
    """7-day window for the weekly mail. Seit Plan 3b (Spec 5.6) getrennt nach
    candidate_class: die Top-Level-Kennzahlen bleiben 'core' (unveraendertes
    Verhalten fuer bestehende Mail-Konsumenten), 'divergence_summary' traegt
    dieselbe Struktur fuer die Divergenz-Kandidaten -- nie vermischt in einer
    gemeinsamen Zahl."""
    since = (date_cls.fromisoformat(today) - timedelta(days=7)).isoformat()
    rows = db.load_recent_outcomes(conn, since)
    core_rows = [r for r in rows if r["candidate_class"] == "core"]
    div_rows  = [r for r in rows if r["candidate_class"] == "divergence"]
    result = _direction_split(core_rows)
    result["divergence_summary"] = _direction_split(div_rows)
    return result


def _premarket_flag(date: str, now_utc: str | None = None) -> int:
    """1, wenn der Erhebungszeitpunkt vor der regulaeren US-Eroeffnung liegt.

    Aus der Uhr, nicht aus marketStatus: das Feld meldete am 2026-08-06 um
    08:37 ET `TRADEABLE`, mitten in der Vorboerse. Es beschreibt die
    Handelbarkeit des CFDs einschliesslich erweiterter Zeiten, nicht die
    Sitzungsphase."""
    now = now_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return 1 if signal_window.is_premarket(date, now) else 0


# C.16 (2026-08-19): news_summaries-Vorarbeit fuer Sprint 3D. Weder broad_scan
# noch deep_analysis/commodities_crypto liefern "sentiment"/"market_impact"
# direkt -- die Felder werden aus dem naechstliegenden vorhandenen Wert
# abgeleitet, statt sie unbelegt zu lassen.
_NEWS_IMPACT_FROM_STRENGTH = {0: "none", 1: "minor", 2: "notable", 3: "major"}
_SENTIMENT_FROM_DIRECTION = {"long": "bullish", "short": "bearish", "none": "neutral"}


def _news_summaries_from_broad_scan(
    broad_results: list[dict], date: str, run_type: str,
) -> list[dict]:
    """Phase-2-Nachrichten-Scan -> news_summaries-Zeilen. sentiment bleibt
    None: news_strength ist eine Betrags-, keine Richtungsskala."""
    return [
        {
            "ticker": r.get("ticker"), "date": date, "run_type": run_type,
            "summary": r.get("news_note") or "", "sentiment": None,
            "source": "broad_scan",
            "market_impact": _NEWS_IMPACT_FROM_STRENGTH.get(r.get("news_strength")),
        }
        for r in broad_results
    ]


def _news_summaries_from_analyses(
    analyses: list[dict], date: str, run_type: str, source: str,
) -> list[dict]:
    """Phase-3/3b-Tiefenanalysen -> news_summaries-Zeilen. sentiment aus
    direction, market_impact aus confidence (low/medium/high passt direkt)."""
    return [
        {
            "ticker": a.get("ticker"), "date": date, "run_type": run_type,
            "summary": a.get("summary") or "",
            "sentiment": _SENTIMENT_FROM_DIRECTION.get(a.get("direction")),
            "source": source, "market_impact": a.get("confidence"),
        }
        for a in analyses
    ]


def _opening_prices(price_provider, tickers: list[str], date: str) -> dict[str, float]:
    """Tatsaechlicher Eroeffnungskurs je Ticker, minutengenau.

    Der 'Open' der Tagesbar taugt dafuer nicht: Capital.com laesst sie um
    08:00 UTC beginnen (openingHours, erweiterte Zeiten). Bei AAPL am 2026-08-05
    lagen Tagesbar-Open (310,54) und tatsaechlicher Open (309,09) 0,47 %
    auseinander.

    Zum Abrufzeitpunkt (10:10 ET) liegt die Eroeffnung bereits in der
    Vergangenheit, der Abruf ist also rein historisch.

    Der Aufrufer uebergibt ausschliesslich Aktien. Krypto und Rohstoffe handeln
    durchgehend und haetten zwar eine Minutenbar um 13:30 UTC, aber keinen
    Eroeffnungskurs -- der Wert waere ein beliebiger Zeitpunkt, kein Ereignis.
    Fuer sie bleibt price_open NULL (E6)."""
    start = signal_window.regular_open_utc(date)
    end = (datetime.fromisoformat(start) + timedelta(minutes=1)).strftime(
        "%Y-%m-%dT%H:%M:%S")
    out: dict[str, float] = {}
    for ticker in tickers:
        try:
            df = price_provider.get_intraday_ohlc(ticker, start, end)
        except Exception as e:
            log.warning(f"{ticker}: Eroeffnungskurs nicht abrufbar: {e}")
            continue
        if df is None or df.empty:
            log.info(f"{ticker}: kein Eroeffnungs-Bar (24/7-Instrument?)")
            continue
        out[ticker] = float(df["Open"].iloc[0])
    return out


def _final_bar_warning(conn, date: str) -> str | None:
    """Warnt, wenn fuer den letzten Werktag keine finale Tagesbar vorliegt.

    final_close verschickt bewusst keine Mail. Faellt er aus, wird nichts mehr
    bewertet und niemand merkt es -- die Weekly saehe nur duenner aus. Diese
    Pruefung macht den Ausfall in der Tagesmail sichtbar."""
    d = date_cls.fromisoformat(date) - timedelta(days=1)
    while d.weekday() >= 5:          # Sa/So ueberspringen
        d -= timedelta(days=1)
    newest = db.load_final_bar_date(conn)
    if newest is not None and newest >= d.isoformat():
        return None
    return (f"⚠️ Keine finale Tagesbar für {d.isoformat()} "
            f"(neueste: {newest or 'keine'}) — lief final_close?")


class HistoryTooThinError(RuntimeError):
    """Zu viele Universums-Ticker haben zu wenig Bars fuer die Indikatoren."""


# Nur diese Run-Types brauchen brauchbare Historie, um ueberhaupt etwas
# produzieren zu koennen. Ausgenommen sind bewusst:
#   final_close — schreibt die Historie selbst, er ist die Loesung, nicht das
#                 Opfer; ein Guard hier verhinderte die Selbstheilung
#   close       — wertet offene Predictions aus; das soll auch dann laufen,
#                 wenn die Historie fuer neue Signale zu duenn ist
#   weekly      — reine Auswertung bestehender Daten, kein Datenbedarf
_RUN_TYPES_NEEDING_HISTORY = ("pre_market", "trade_proposals")


def _abort_on_thin_history(db_path: str) -> None:
    """Bricht ab, wenn mehr als die Haelfte des Universums zu wenig Historie hat.

    Der Guard steht am CLI-Einstieg, vor jeder Phase: ein Lauf ohne brauchbare
    Historie kann ohnehin nichts persistieren und soll dafuer keine ~3,30 EUR an
    Trend- und Tiefenanalysen ausgeben. Am 2026-08-04 lief genau das dreimal
    durch: 19 Bars je Aktie, eine unter MIN_BARS_RSI, drei gruene, leere Laeufe.

    Bewusst eine Mehrheitsregel, kein Alles-oder-Nichts: einzelne zickende
    Ticker sind Normalbetrieb (dafuer gibt es skipped_tickers und die
    Deaktivierung), eine halb leere Datenbank ist ein Betriebsfehler."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    try:
        thin = thin_history_tickers(conn)
    finally:
        conn.close()
    universe_size = len(full_universe())
    if universe_size and len(thin) * 2 > universe_size:
        raise HistoryTooThinError(
            f"{len(thin)} von {universe_size} Tickern haben zu wenig Historie "
            f"({', '.join(thin[:10])}{' …' if len(thin) > 10 else ''}). "
            f"Der Lauf wuerde fast alles ueberspringen und nichts persistieren. "
            f"Beheben mit: python setup/historical_loader.py --universe "
            f"(in CI: Workflow 'bootstrap-db'). "
            f"Bestandsaufnahme: python setup/historical_loader.py --report-coverage"
        )


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
        sp500_tds, skipped_sp, sp500_sidecar = collect(
            tickers=_tickers,
            price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn, date=date, run_type=run_type,
        )
        current_phase = "data_collection_cc"
        # Phase 1b — Commodities + Crypto data (separate collect for asset_class tagging)
        cc_inputs = build_commodity_crypto_inputs()
        cc_tickers = [d["ticker"] for d in cc_inputs]
        cc_tds_raw, skipped_cc, cc_sidecar = collect(
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

        current_phase = "broad_scan"
        # Phase 2 — Nachrichten-Scan (Sonnet + Websuche, stocks only). Ersetzt
        # den Haiku-Quick-Filter (Sprint 3C / Analyse-Pipeline-Umbau, Plan 2,
        # Task 10). Rohstoffe/Krypto umgehen Scan, Cutoff und 2b komplett
        # (Spec 18.3) -- sie laufen separat ueber cc_tds/deep_cc weiter unten.
        broad_results = broad_scan_batch(
            ticker_datas=sp500_tds, sidecar=sp500_sidecar,
            trend_context=trend_context, market_context=market_ctx,
            cost_tracker=cost_tracker,
        )
        # Phase 2a — Cutoff: waehlt ≤ MAX_DEEP_ANALYSIS Kandidaten aus, Pflicht-
        # Kandidaten aus Phase 1c stehen vorn und zaehlen gegen den Deckel.
        selected, all_evaluated = cutoff_candidates(
            ticker_datas=sp500_tds, broad_scan_results=broad_results,
            sidecar=sp500_sidecar, forced_candidates=forced,
            max_deep_analysis=config.MAX_DEEP_ANALYSIS,
        )
        db.log_cutoff(conn, date=date, run_type=run_type, evaluated=all_evaluated)
        log.info(
            f"Phase 2a (cutoff) done: {len(selected)} von {len(all_evaluated)} "
            f"Kandidaten ausgewaehlt (max_deep_analysis={config.MAX_DEEP_ANALYSIS})"
        )

        current_phase = "fundamentals_2b"
        # Phase 2b — Fundamentaldaten der Kandidaten (Spec 4.7, 18.1b/f).
        # Nicht fatal: Finnhub ist hier ausdruecklich kein Single Point of
        # Failure, ein Ausfall kostet nur Kontext-Qualitaet, keinen Lauf.
        try:
            run_phase_2b(
                ticker_datas=sp500_tds,
                candidates=[c["ticker"] for c in selected],
                earnings_provider=earnings_provider,
                conn=conn, date=date,
            )
        except Exception as e:
            log.warning(f"Phase 2b nicht vollstaendig, Run laeuft weiter: {e}")

        # Phase 3 sieht ausschliesslich die selektierten Ticker. Bis Plan 3a
        # uebergab main ALLE Ticker plus ein exclude-Flag (der Interim-Adapter
        # aus Plan 2, Task 10) -- die Auswahl liegt jetzt vollstaendig im
        # Cutoff, wo sie hingehoert.
        selected_tickers = {c["ticker"] for c in selected}
        selected_tds = [td for td in sp500_tds if td["ticker"] in selected_tickers]
        cutoff_by_ticker = {c["ticker"]: c for c in selected}

        current_phase = "policy_monitor"
        # Phase 3 policy monitor (1× for all of Phase 3 + 3b + 4a)
        policy_context = run_policy_monitor(
            date=date, run_type=run_type, cost_tracker=cost_tracker,
        )
        payload["briefing"] = generate_daily_briefing(trend_context, policy_context)

        current_phase = "deep_analysis"
        # Phase 3 — Batch-Tiefenanalyse nach Sub-Sektor (Spec 4.8, 20.2).
        # failed_deep sind Ticker, deren Batch auch nach Wiederholung und
        # Halbierung nichts lieferte (Spec 10) -- sie werden gezaehlt, nicht
        # stillschweigend verschluckt.
        deep_stocks, failed_deep = analyze_batches(
            ticker_datas=selected_tds,
            cutoff_by_ticker=cutoff_by_ticker,
            trend_context=trend_context,
            policy_context=policy_context,
            cost_tracker=cost_tracker,
            batch_size=config.BATCH_SIZE_DEEP,
        )
        if failed_deep:
            log.warning(
                f"Phase 3: {len(failed_deep)} Kandidaten ohne Analyse: "
                f"{', '.join(sorted(failed_deep))}"
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

        # C.16: fear_greed_value (Phase 3b) und policy_risk_level (Phase 3)
        # entstehen beide erst NACH dem save_market_context()-Aufruf aus
        # Phase 0b -- deshalb ein Backfill statt eines zweiten Inserts.
        db.update_market_context_extras(
            conn, date=date, run_type=run_type,
            fear_greed_value=fg.get("value"),
            policy_risk_level=policy_context.get("policy_risk_level"),
        )
        db.save_news_summaries(
            conn,
            _news_summaries_from_broad_scan(broad_results, date, run_type)
            + _news_summaries_from_analyses(
                deep_stocks, date, run_type, "deep_analysis")
            + _news_summaries_from_analyses(
                deep_cc, date, run_type, "commodities_crypto"),
        )

        # Der 15:00-Kurs ist regulaer vorboerslich (09:00 ET). Die Markierung
        # geht in die Prediction-Zeile und in den Re-Validierungs-Prompt --
        # ein duenn gehandelter Vorboersenkurs ist kein Sitzungskurs.
        _pm = _premarket_flag(date)
        for _a in deep_stocks + deep_cc:
            _a["price_premarket"] = _a.get("current_price")
            _a["is_premarket"] = _pm

        current_phase = "ranking"
        # Phase 4 — Ranking + persist predictions (market_ctx kommt aus Phase 0b).
        # signal_context buendelt Technik-Signal, C.1-Indikatoren und den
        # Phase-2-Scan-Wert je Ticker (Spec 20.5) -- weder im Claude-Dict noch
        # in td allein vorhanden.
        signal_context = {
            **_signal_context(
                sp500_tds, sp500_sidecar,
                news_strength_by_ticker={
                    c["ticker"]: c["news_strength"] for c in selected
                },
            ),
            **_signal_context(cc_tds, cc_sidecar),
        }
        ranked = rank_and_persist(
            conn=conn, date=date, run_type=run_type,
            stock_analyses=deep_stocks,
            commodity_crypto_analyses=deep_cc,
            market_context=market_ctx,
            signal_context=signal_context,
            sector_momentum=sector_mom,
        )
        payload["top_long"]            = ranked["top_long"]
        payload["top_short"]           = ranked["top_short"]
        payload["commodities_crypto"]  = ranked["commodities_crypto"]
        payload["divergence"]          = ranked["divergence"]
        payload["divergence_stats"]    = ranked["divergence_stats"]

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
    _warn = _final_bar_warning(conn, date=date)
    if _warn:
        payload["briefing"] = [*payload.get("briefing", []), _warn]
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

    # E3: INSERT der neuen Zeile und Abloesung der alten in EINER Transaktion —
    # zwei getrennte Commits liessen bei einem Abbruch dazwischen zwei offene
    # Zeilen stehen, und der Evaluator schloesse beide.
    return db.supersede_prediction(conn, pred["id"], {
        "date": date, "run_type": "trade_proposals",
        "asset_class": pred["asset_class"], "ticker": ticker, "direction": direction,
        "entry_price": entry,
        "price_premarket": pred["price_premarket"],
        "price_open":      snapshot.get("price_open"),
        "price_1610":      snapshot.get("price"),
        "is_premarket":    0,
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
        # ⚠️ Die acht Plan-3b-Spalten MUESSEN mitwandern (Spec 7.2:
        # "Persistiert wird, was tatsaechlich entschieden hat"). Die 16:10-Zeile
        # ist die einzige, die je ein Outcome bekommt — sie muss den
        # Signalzustand tragen, der sie erzeugt hat.
        # Ohne sie stempelt db._insert_prediction() die Nachfolgezeile per
        # Default-Merge auf candidate_class='core', und zwar STILL:
        #   * divergence_summary in der Weekly-Mail waere strukturell leer,
        #     ausgerechnet fuer die Divergenz-Kandidaten mit realisiertem Ergebnis;
        #   * load_revision_effectiveness() filtert seinen 'confirmed'-Topf ueber
        #     candidate_class -> divergence.confirmed bliebe dauerhaft 0, waehrend
        #     core.confirmed mit Divergenz-Zeilen aufgeblasen waere.
        # Das ist genau der Vergleich, fuer den der core/divergence-Split gebaut
        # wurde. pred kommt aus load_predictions_for_revalidation() (SELECT *),
        # traegt die Werte also bereits.
        "candidate_class": pred["candidate_class"],
        "tech_direction": pred["tech_direction"],
        "tech_agreement": pred["tech_agreement"],
        "tech_adx_band": pred["tech_adx_band"],
        "tech_strength": pred["tech_strength"],
        "analysis_strength": pred["analysis_strength"],
        "rank_score": pred["rank_score"],
        "news_strength": pred["news_strength"],
        # O2 (Plan-3b-Gesamtreview): der C.1-Fix (atr_pct/rsi_at_entry/volume_ratio
        # nicht mehr hart None, s. _to_prediction_row() in src/ranking.py) deckte
        # nur den pre_market-Pfad ab. snapshot ist derselbe frische td-Snapshot
        # aus collect(), den main._signal_context() fuer den Morgenlauf liest --
        # dieselben drei Schluessel sind hier ebenso vorhanden.
        "atr_pct": snapshot.get("atr_pct"),
        "rsi_at_entry": snapshot.get("rsi_14"),
        "volume_ratio": snapshot.get("volume_ratio"),
    }, verdict=verdict["verdict"])


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
        sp_tds, _, _ = collect(
            tickers=_tickers, price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn, date=date, run_type="trade_proposals")
        cc_tickers = [d["ticker"] for d in build_commodity_crypto_inputs()]
        cc_tds, _, _ = collect(
            tickers=cc_tickers, price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn, date=date, run_type="trade_proposals")
        snapshots = {td["ticker"]: td for td in (sp_tds + cc_tds)}

        opens = _opening_prices(
            price_provider, [td["ticker"] for td in sp_tds], date)
        for _t, _snap in snapshots.items():
            _snap["price_open"] = opens.get(_t)

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

        # C.16: trade_proposals ruft fetch_fear_greed() nie (kein Phase 3b
        # hier) -- fear_greed_value bleibt bewusst NULL statt eines erfundenen
        # Werts, nur policy_risk_level wird nachgetragen.
        db.update_market_context_extras(
            conn, date=date, run_type="trade_proposals",
            fear_greed_value=None,
            policy_risk_level=policy_context.get("policy_risk_level"),
        )

        current_phase = "revalidation"
        # out= statt Zuweisung: bricht der Lauf hier am Kostendeckel ab, sind die
        # bis dahin geprueften Signale schon persistiert und muessen auch in der
        # Mail stehen (Spec 7.1: Teilergebnis plus Warnbalken).
        _revalidate_all(
            conn=conn, date=date, snapshots=snapshots, sector_mom=sector_mom,
            market_ctx=market_ctx, policy_context=policy_context,
            cost_tracker=cost_tracker, out=payload["signal_changes"],
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

    # B-10: Zustellung von der Re-Validierung trennen, dasselbe Muster wie in
    # run_pipeline(). Alles oben ist zu diesem Zeitpunkt bereits persistiert;
    # ein Mailfehler darf daran nichts aendern, soll aber klar als
    # Zustellproblem sichtbar werden und nicht in einer Analysephase gesucht
    # werden.
    try:
        send_trade_proposals_email(
            payload=payload, api_key=config.RESEND_API_KEY,
            email_from=config.EMAIL_FROM, email_to=config.EMAIL_TO,
        )
    except Exception as e:
        log.error(
            f"Re-Validierung vollstaendig persistiert "
            f"({len(payload['signal_changes'])} Signale, "
            f"{payload['cost_summary'].get('total_eur')} EUR) — "
            f"nur der Mailversand scheiterte: {e}"
        )
        raise MailDeliveryError(str(e)) from e
    finally:
        conn.close()


def _unchecked_row(pred, reason: str) -> dict:
    """Die Mail-Zeile fuer ein Signal, das der 16:10-Lauf nicht pruefen konnte.

    Dieselben Schluessel wie im Normalpfad (nur als None) — sonst faellt ein
    spaeterer direkter Dict-Zugriff (statt .get()) bei einer 'nicht_geprueft'-Zeile
    mit KeyError um."""
    return {"ticker": pred["ticker"], "direction": pred["direction"],
            "verdict": "nicht_geprueft",
            "probability_before": pred["probability_pct"],
            "probability_after": None,
            "entry_window_low": None, "entry_window_high": None,
            "reason": reason, "checks": []}


def _revalidate_all(
    conn, date: str, snapshots: dict, sector_mom: dict,
    market_ctx: dict, policy_context: dict, cost_tracker: CostTracker,
    out: list[dict],
) -> list[dict]:
    """Prueft jedes heutige offene pre_market-Signal nach und persistiert das
    Ergebnis. Haengt die Zeilen fuer die Mail an `out` an.

    Ein Fehlschlag betrifft immer nur EIN Signal: die zugehoerige Zeile bleibt dann
    unangetastet offen und erscheint in der Mail als 'nicht geprueft'.

    `out` gehoert bewusst dem Aufrufer statt als Rueckgabewert zu entstehen: reisst
    der Lauf am Kostendeckel ab, ist das bereits Gepruefte laengst in der DB
    abgeloest. Haenge es an einer Zuweisung, ginge es fuer die Mail verloren und
    der Nutzer laese '0 Signale' neben dem Warnbalken (Spec 7.1: Teilergebnis)."""
    open_preds = db.load_predictions_for_revalidation(conn, date)
    log.info(f"Re-Validierung: {len(open_preds)} offene pre_market-Signale")

    counts = signal_checks.cluster_counts(conn, [p["ticker"] for p in open_preds])
    for pred in open_preds:
        ticker = pred["ticker"]
        snapshot = snapshots.get(ticker, {})
        if not snapshot.get("price"):
            # Spec 7.1: ohne frischen Kurs nie abloesen. collect() liefert
            # uebersprungene Ticker gar nicht erst zurueck (stillgelegt per B.7
            # oder Abruf fehlgeschlagen). Der Einstieg fiele sonst still auf den
            # 15:00-Kurs zurueck und die neue Zeile behauptete einen
            # Nachmittags-Einstieg, den es nie gab. Der Claude-Call entfaellt
            # gleich mit — er saehe einen leeren Snapshot.
            log.warning(f"{ticker}: kein frischer Kurs zum 16:10-Lauf "
                        f"(uebersprungen?), Zeile bleibt unveraendert offen")
            out.append(_unchecked_row(pred, "kein frischer Kurs zum 16:10-Lauf"))
            continue
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
            # Spec 5.3: "erhoben in beiden Laeufen, durchgesetzt um 16:10" --
            # das ist DIESE Stelle. Der Morgenlauf erhebt denselben Check in
            # ranking._run_checks() mit enforce=False; ohne die Zeile hier waere
            # er ueberall weich und koennte nie etwas blockieren -- also genau
            # das, was er laut Spec ersetzen sollte (das folgenlose
            # Modell-Attribut earnings_warning).
            # earnings_in_days steht direkt im Snapshot: collect() rechnet es in
            # _apply_fundamentals_to_td() aus dem gecachten ISO-Datum, jedes Mal
            # frisch (Spec 18.1d, ein gecachter Countdown waere nach vier Tagen
            # falsch). Fuer Rohstoffe/Krypto ist es None, der Check dort trivial
            # erfuellt.
            signal_checks.check_earnings(
                pred["direction"], snapshot.get("earnings_in_days"),
                enforce=True),
            signal_checks.check_opening_gap(
                pred["entry_price"], snapshot.get("price")),
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
        except CostCapExceeded:
            # Deckel gilt fuer den ganzen Lauf, nicht fuer ein Signal — muss
            # durch bis zum Handler in run_trade_proposals. Dasselbe Muster wie
            # in den uebrigen Phasen.
            raise
        except Exception as e:
            # Bewusst breit: call_claude() reicht nach zwei Retries die rohe
            # Exception durch, ein 429/529 kommt also als APIStatusError an und
            # nicht als RevalidationError. Frueher entkam der bis aus
            # run_trade_proposals heraus — save_cost_tracking() lief nie und die
            # bereits abgeloesten Ticker sah niemand. Ein Fehlschlag darf immer
            # nur EIN Signal kosten (Spec 7.1).
            log.warning(f"{ticker}: Re-Validierung fehlgeschlagen, Zeile bleibt "
                        f"unveraendert offen: {e}")
            out.append(_unchecked_row(pred, str(e)))
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


def _write_final_bar(conn, price_provider, ticker: str, target: str) -> bool:
    """Holt die finale Tagesbar fuer `ticker` am Handelstag `target` und schreibt
    sie. True, wenn eine Bar geschrieben wurde.

    Eine fehlende Bar ist der erwartete Normalfall, kein Fehler: am Wochenende
    und an Feiertagen gibt es fuer Aktien keine neue Tagesbar, fuer Crypto
    schon."""
    try:
        df = price_provider.get_ohlc_after(ticker, target, target)
    except Exception as e:
        log.warning(f"{ticker}: finaler Abruf fehlgeschlagen: {e}")
        return False
    if df is None or df.empty:
        log.info(f"{ticker}: keine neue Tagesbar fuer {target} (Wochenende/Feiertag?)")
        return False

    _raw = getattr(price_provider, "_source_name", None)
    source = _raw if isinstance(_raw, str) else "capital.com"
    written = False
    for ts, row in df.iterrows():
        d = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        if d != target:
            continue
        db.upsert_price_history(
            conn, ticker=ticker, date=d,
            open_=float(row.get("Open", 0)), high=float(row.get("High", 0)),
            low=float(row.get("Low", 0)), close=float(row.get("Close", 0)),
            volume=int(row.get("Volume", 0) or 0), source=source,
        )
        written = True
    if not written:
        log.info(f"{ticker}: Antwort enthielt keine Bar fuer {target}")
    return written


def run_final_close(date: str, db_path: str) -> None:
    """Run-Type final_close (00:15 UTC, taeglich): holt die FINALE Tages-OHLC,
    bewertet danach die offenen Predictions und verschickt eine Auswertungs-
    Mail (C.17, seit 2026-08-19).

    `date` ist das UTC-Laufdatum; ausgewertet wird der UTC-Vortag. Die Tagesbar
    wird laut openingHours (`zone: UTC`) um 00:00 UTC final -- vorher gelesen
    waere sie provisorisch, und High/Low koennen sich bis dahin nur ausweiten.
    Genau darauf beruhen TP- und SL-Pruefung.

    Kein Claude-Call -- die Mail ist eine reine DB-Auswertung (outcomes +
    predictions), null zusaetzliche Kosten. Wird IMMER verschickt, auch bei
    0 Auswertungen (kein stiller Ausfall) -- die aggregierte Kurzfassung
    bleibt zusaetzlich in der Fussleiste der naechsten pre_market-Mail."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    price_provider = CapitalComProvider()

    target = (date_cls.fromisoformat(date) - timedelta(days=1)).isoformat()
    log.info(f"final_close: finalisiere Handelstag {target}")

    # Dieselbe Liste, die `historical_loader --universe` backfillt — siehe
    # src/universe.py. Getrennt gepflegt liefen beide auseinander, und ein
    # Ticker haette Backfill ohne Fortschreibung (oder umgekehrt).
    written = 0
    for ticker in full_universe():
        if _write_final_bar(conn, price_provider, ticker, target):
            written += 1
    conn.commit()
    log.info(f"final_close: {written} finale Bars fuer {target} geschrieben")

    n = evaluate_open_predictions(
        conn=conn, today=date, price_provider=price_provider)
    log.info(f"final_close: {n} Predictions bewertet")

    rows = [dict(r) for r in db.load_evaluated_outcomes(conn, target)]
    conn.close()

    send_final_close_email(
        payload={"date": date, "rows": rows},
        api_key=config.RESEND_API_KEY,
        email_from=config.EMAIL_FROM, email_to=config.EMAIL_TO,
    )


def _update_weekly_fundamentals(
    conn, date: str, provider, universe: list[str] | None = None,
) -> None:
    """Wochenlauf-Vorlauf (Sprint 3C / Analyse-Pipeline-Umbau, Plan 2,
    Task 12; Spec 18.1c): fuellt fundamentals_cache UND earnings_next_date
    fuer das ganze Universum. get_earnings_calendar() ist bewusst NUR hier --
    der Tageslauf (data_collector.fetch_missing_fundamentals(), Task 7 / R15)
    ruft sie nie, das ist die in Spec 18.1c getroffene Aufgabenteilung.

    Ein Ticker mit frischen Fundamentals, aber OHNE earnings_next_date, wird
    NICHT uebersprungen -- das ist der haeufigste Fall (der Tageslauf hat ihn
    als Kandidaten nachgeladen, kennt aber keine Earnings) und der Grund,
    warum die Skip-Pruefung mehr braucht als 'ist gecacht': der Plan-
    Pseudocode prueft nur Letzteres und haette solche Ticker fuer immer ohne
    Earnings-Datum gelassen.

    Nicht fatal: ein API-Fehler bei einem Ticker (oder ein leeres Ergebnis --
    get_fundamentals() faengt eigene Fehler intern ab und liefert dann {})
    ueberspringt nur diesen, der Lauf macht mit den uebrigen weiter."""
    updated = skipped = failed = 0
    for ticker in universe if universe is not None else full_universe():
        cached = db.get_cached_fundamentals(conn, ticker, today=date)
        if cached is not None and cached.get("earnings_next_date"):
            skipped += 1
            continue
        try:
            raw = provider.get_fundamentals(ticker)
            earnings = provider.get_earnings_calendar(ticker)
        except Exception as e:
            log.warning(f"{ticker}: weekly fundamentals failed (non-fatal): {e}")
            failed += 1
            continue
        if not isinstance(raw, dict) or not raw:
            failed += 1
            continue
        if earnings.get("days_to_next") is not None:
            next_date = (date_cls.fromisoformat(date)
                        + timedelta(days=earnings["days_to_next"]))
            raw["earnings_next_date"] = next_date.isoformat()
        db.save_fundamentals_cache(conn, ticker, raw, fetched_date=date)
        updated += 1
    log.info(
        f"Weekly fundamentals pre-run: {updated} updated, {skipped} already "
        f"fresh (fundamentals + earnings), {failed} failed"
    )


def run_weekly(date: str, db_path: str) -> None:
    conn = db.connect(db_path)
    db.init_schema(conn)
    _update_weekly_fundamentals(conn, date=date, provider=FinnhubProvider())
    agg = load_recent_outcomes_aggregate(conn, today=date)
    week_label = "KW" + date_cls.fromisoformat(date).strftime("%V")
    since = (date_cls.fromisoformat(date) - timedelta(days=7)).isoformat()
    payload = {
        "week_label": week_label, **agg,
        "revision_effectiveness": db.load_revision_effectiveness(conn, since),
        "verdict_stats":   db.load_revision_verdict_stats(conn, since),
        "guardrail_stats": db.load_guardrail_reject_stats(conn, since),
        "skipped_stats":   db.load_skipped_ticker_stats(conn, since),
        "sector_coverage": db.load_sector_mapping_coverage(conn),
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
        if ns.run_type in _RUN_TYPES_NEEDING_HISTORY:
            _abort_on_thin_history(ns.db_path)
        if ns.run_type == "pre_market":
            run_pipeline(run_type=ns.run_type, date=date, db_path=ns.db_path)
        elif ns.run_type == "trade_proposals":
            run_trade_proposals(date=date, db_path=ns.db_path)
        elif ns.run_type == "final_close":
            run_final_close(date=date, db_path=ns.db_path)
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
