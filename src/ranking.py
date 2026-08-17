"""Phase 4: Rank guardrail-passing analyses and persist to predictions.

Stocks: top 10 by probability_pct per direction (long / short).
Commodities + crypto: always all kept, regardless of score.
Every selected analysis is written as a learnable=True predictions row."""
import logging
from typing import Iterable

from src import db
from src import signal_checks
from src.signal_checks import momentum_for, cluster_counts
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


def _rule_name(error_message: str) -> str:
    """Leitet aus einer Guardrail-Fehlermeldung einen kurzen, gruppierbaren
    Regelnamen ab, damit die Weekly-Mail nach Regel aggregieren kann."""
    msg = error_message.lower()
    if msg.startswith("required field missing"):
        return "required_field"
    if msg.startswith("too few sources"):
        return "sources"
    if "too few evidence" in msg:
        return "evidence"
    if msg.startswith("r/r"):
        return "rr_ratio"
    if "signal consistency" in msg:
        return "momentum_consistency"
    if "haltedauer" in msg:
        return "hold_days"
    if "intraday-range" in msg:
        return "intraday_range"
    if "confidence" in msg:
        return "confidence_data_quality"
    if "not above entry" in msg or "not below entry" in msg:
        return "tp_sl_direction"
    return "other"


from src.analysis_signal import analysis_strength


def _classify(
    analysis: dict, signal_ctx: dict, *, cc: bool,
) -> tuple[str, int, int | None]:
    """Klassifiziert eine guardrail- und B.3-check-bestandene Analyse nach
    Spec 5.3-5.5. Gibt (candidate_class, analysis_strength, rank_score)
    zurueck. direction='none' ist hier bereits durch _guardrail_filter()
    ausgefiltert -- nur long/short erreichen diese Funktion.

    rank_score ist NULL, sobald EINER der beiden Faktoren ausserhalb seines
    Wertebereichs liegt (Spec 5.4 nennt 1..8 bzw. 1..4, 20.5 #3): ein Produkt
    mit 0 loescht die Aussage des anderen Faktors, und 0 hiesse 'schlechtester
    Kandidat', wo 'nicht vergleichbar' gilt.

    BEIDE Nullfaelle sind erreichbar, nicht nur der offensichtliche:
      * tech_strength == 0 -- technical_signal.compute() liefert das NUR beim
        neutralen Fall (src/technical_signal.py:103-106), also bei jedem
        Divergenz-Kandidaten.
      * analysis_strength == 0 bei GESETZTER Richtung -- seltener, aber
        moeglich: die Guardrails pruefen den momentum-WERT gegen
        MOMENTUM_LONG_MIN (src/guardrails.py:84-93), waehrend
        analysis_strength zusaetzlich >= 2 Belege und evidence_quality != thin
        verlangt. Eine Analyse mit momentum=7.0, evidence_quality='thin' und
        acht schwachen Dimensionen besteht die Guardrails und zaehlt trotzdem
        0. Ohne die Pruefung auf `strength` bekaeme sie rank_score = 0 statt
        NULL.

    cc=True (Rohstoffe/Krypto, Spec 20.5 #2): die Zwei-Signal-Huerde gilt
    nicht. Ein fehlendes oder gegenlaeufiges Technik-Signal disqualifiziert
    nicht -- 'always kept, regardless of score' bleibt bestehen, das
    Technik-Signal traegt nur noch zum rank_score bei, wenn es da ist."""
    strength = analysis_strength(analysis)
    tech_direction = signal_ctx.get("tech_direction")
    tech_strength = signal_ctx.get("tech_strength")
    direction = analysis["direction"]

    rank_score = strength * tech_strength if (strength and tech_strength) else None

    if cc:
        return "core", strength, rank_score

    if tech_direction == direction:
        return "core", strength, rank_score
    if tech_direction in ("long", "short"):
        return "conflict", strength, rank_score
    # tech_direction ist 'neutral' ODER fehlt (kein Sidecar-Eintrag) --
    # beides konservativ wie eine Divergenz behandeln, nie wie ein Konflikt.
    return "divergence", strength, rank_score


def _rank_key(strength: int, rank_score: int | None, ticker: str) -> tuple:
    """Sortierschluessel fuer Top-10 und Divergenz-Listen: rank_score
    absteigend, faellt bei NULL auf analysis_strength zurueck (Spec 5.4),
    Ticker alphabetisch als deterministischer Tie-Break (Spec 5.4)."""
    primary = rank_score if rank_score is not None else strength
    return (-primary, -strength, ticker)


def _guardrail_filter(
    analyses: Iterable[dict], conn, date: str, run_type: str,
) -> tuple[list[dict], int]:
    """Drops analyses with direction='none' or that fail GuardrailsChecker.
    Gibt (behaltene Analysen, Zahl der Enthaltungen) zurueck.

    Jede Ablehnung wird zusaetzlich als guardrail_rejects-Zeile persistiert, damit
    die Weekly-Mail auswerten kann, welche Regeln wie oft greifen (Sprint 3B / B.9).
    direction='none' ist dabei kein Reject, sondern eine bewusste Enthaltung —
    sie wird gezaehlt und geloggt, aber nicht als Regelverstoss gebucht. Sonst
    verzerrte sie die Auswertung, welche Regel wie oft greift."""
    checker = GuardrailsChecker()
    kept: list[dict] = []
    abstained = 0
    for a in analyses:
        if a.get("direction") == "none":
            abstained += 1
            continue
        ok, errs = checker.check_analysis(a)
        if not ok:
            ticker = a.get("ticker", "?")
            log.info(f"{ticker}: dropped by guardrails: {'; '.join(errs)}")
            db.log_guardrail_reject(conn, {
                "date": date, "run_type": run_type, "ticker": ticker,
                "direction": a.get("direction"),
                "rule": _rule_name(errs[0]),
                "detail": "; ".join(errs),
                "enforced": 1,
            })
            continue
        kept.append(a)
    return kept, abstained


def _to_prediction_row(
    analysis: dict, date: str, run_type: str, market_context: dict, conn,
    etf_momentum: float | None = None, db_momentum: float | None = None,
) -> dict:
    """Maps one guardrail-passing analysis dict onto the flat column layout
    expected by db.save_prediction(). Der Sektor kommt aus ticker_sectors
    (Sprint 3B / B.10), nicht mehr aus dem marktweiten market_context-Dict —
    dort stand nie ein Wert, weshalb predictions.sector bisher immer NULL war."""
    scores = analysis.get("scores", {})
    sector_row = db.get_ticker_sector(conn, analysis["ticker"])
    return {
        "date": date, "run_type": run_type,
        "asset_class": analysis.get("asset_class"),
        "ticker": analysis["ticker"], "direction": analysis["direction"],
        "entry_price": analysis["current_price"],
        "price_premarket": analysis.get("price_premarket"),
        "is_premarket":    analysis.get("is_premarket"),
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
        "sector": sector_row["name"] if sector_row else None,
        "trend_boost": None,
        "earnings_warning": bool(analysis.get("earnings_warning")),
        "summary": analysis.get("summary"),
        "sector_etf_momentum": etf_momentum,
        "sector_db_momentum": db_momentum,
        "learnable": True,
        "hold_days_recommended": analysis.get("hold_days_recommended"),
        "intraday_range_pct": analysis.get("intraday_range_pct"),
    }


def _run_checks(
    analysis: dict, conn, date: str, run_type: str,
    market_context: dict, sector_momentum: dict[int, dict],
    cluster_counts: dict[str, int], enforce: bool,
) -> list[signal_checks.CheckResult]:
    """Fuehrt die B.3-Checks fuer EINE Analyse aus und persistiert jeden
    angeschlagenen Check als guardrail_rejects-Zeile — mit dem Momentum-Snapshot,
    damit 3D auswerten kann, ob die weichen Warnungen richtig lagen.

    Gibt die angeschlagenen Checks zurueck; ob sie blockieren, entscheidet der
    Aufrufer ueber signal_checks.blocks()."""
    ticker = analysis["ticker"]
    direction = analysis.get("direction")
    etf_mom, db_mom = momentum_for(conn, ticker, sector_momentum)
    sector = db.get_ticker_sector(conn, ticker)
    sector_name = sector["name"] if sector else None

    results = [
        r for r in (
            signal_checks.check_vix(
                direction, analysis.get("confidence"),
                market_context.get("vix_level"), enforce=enforce),
            signal_checks.check_sector_momentum(
                direction, etf_mom, db_mom, enforce=enforce),
            signal_checks.check_cluster(
                sector_name, cluster_counts.get(sector_name or "", 0)),
        ) if r is not None
    ]

    for r in results:
        db.log_guardrail_reject(conn, {
            "date": date, "run_type": run_type, "ticker": ticker,
            "direction": direction, "rule": r.rule, "detail": r.detail,
            "enforced": 1 if r.enforced else 0,
            "sector_etf_momentum": etf_mom, "sector_db_momentum": db_mom,
        })
    return results


def rank_and_persist(
    conn,
    date: str,
    run_type: str,
    stock_analyses: list[dict],
    commodity_crypto_analyses: list[dict],
    market_context: dict,
    sector_momentum: dict[int, dict] | None = None,
    enforce_checks: bool = False,
) -> dict:
    """Returns {top_long, top_short, commodities_crypto} und schreibt je Auswahl
    eine predictions-Zeile.

    `enforce_checks` steuert Entscheidung E4: run_pipeline() uebergibt False
    (erheben und warnen), run_trade_proposals() uebergibt True (durchsetzen)."""
    sector_momentum = sector_momentum or {}
    kept_stocks, abstained_stocks = _guardrail_filter(
        stock_analyses, conn, date, run_type)
    kept_cc, abstained_cc = _guardrail_filter(
        commodity_crypto_analyses, conn, date, run_type)
    abstained = abstained_stocks + abstained_cc

    counts = cluster_counts(conn, [a["ticker"] for a in kept_stocks])
    surviving: list[dict] = []
    for a in kept_stocks:
        results = _run_checks(
            a, conn, date, run_type, market_context, sector_momentum,
            counts, enforce_checks,
        )
        if signal_checks.blocks(results):
            log.info(f"{a['ticker']}: durch B.3-Check verworfen "
                     f"({', '.join(r.rule for r in results if r.enforced)})")
            continue
        surviving.append(a)

    longs  = sorted(
        [a for a in surviving if a["direction"] == "long"],
        key=lambda a: a.get("probability_pct") or 0, reverse=True,
    )[:TOP_N]
    shorts = sorted(
        [a for a in surviving if a["direction"] == "short"],
        key=lambda a: a.get("probability_pct") or 0, reverse=True,
    )[:TOP_N]

    for a in (*longs, *shorts, *kept_cc):
        etf_mom, db_mom = momentum_for(conn, a["ticker"], sector_momentum)
        db.save_prediction(conn, _to_prediction_row(
            a, date=date, run_type=run_type, market_context=market_context,
            conn=conn, etf_momentum=etf_mom, db_momentum=db_mom,
        ))

    # Die Zahl der Eingaben gehoert dazu: ohne sie ist nicht zu sehen, ob "0
    # persistiert" aus null Kandidaten entstand oder aus neun, die alle
    # weggefiltert wurden. Genau diese Luecke machte den 2026-08-04-Lauf
    # unerklaerbar.
    n_in = len(list(stock_analyses)) + len(list(commodity_crypto_analyses))
    n_out = len(longs) + len(shorts) + len(kept_cc)
    log.info(
        f"Phase 4 done: {len(longs)} long, {len(shorts)} short, "
        f"{len(kept_cc)} commodity/crypto persisted "
        f"(aus {n_in} Analysen, davon {abstained} enthalten)"
    )

    # Unabhaengig von der Ursache: ein Lauf, der nichts persistiert, hat sein
    # Ziel verfehlt und darf nicht als gruener Job durchrutschen. Am 2026-08-04
    # endeten drei Laeufe genau so -- technisch erfolgreich, inhaltlich leer,
    # ohne ein einziges WARNING. Die Diagnose kostete den Umweg ueber die
    # heruntergeladene CI-Datenbank.
    if n_out == 0:
        log.warning(
            f"Phase 4: KEINE Prediction persistiert (aus {n_in} Analysen, "
            f"{abstained} Enthaltungen). Der Lauf bleibt ohne Ergebnis — "
            f"Ursache pruefen: zu wenig Historie, Guardrails oder Enthaltungen."
        )
    return {"top_long": longs, "top_short": shorts, "commodities_crypto": kept_cc}
