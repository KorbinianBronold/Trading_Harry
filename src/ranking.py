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
    signal_ctx: dict,
    etf_momentum: float | None = None, db_momentum: float | None = None,
) -> dict:
    """Maps one classified analysis dict onto the flat column layout expected
    by db.save_prediction(). Der Sektor kommt aus ticker_sectors, nicht mehr
    aus dem marktweiten market_context-Dict.

    signal_ctx traegt (Spec 20.5, Task 7/8): das Technik-Signal zum
    Entscheidungszeitpunkt, die drei C.1-Indikatoren (vorher hart auf None),
    den Phase-2-Scan-Wert. analysis traegt zusaetzlich die drei Schluessel
    _candidate_class/_analysis_strength/_rank_score, die rank_and_persist()
    beim Klassifizieren aufklebt (s. dort)."""
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
        "total_score": analysis.get("total_score"),
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
        # C.1-Fix (Abschluss-Review Sprint 3C): standen hart auf None, obwohl
        # laengst berechnet -- Voraussetzung dafuer, dass 3D auf diesen drei
        # Dimensionen ueberhaupt lernen kann.
        "atr_pct": signal_ctx.get("atr_pct"),
        "rsi_at_entry": signal_ctx.get("rsi_14"),
        "volume_ratio": signal_ctx.get("volume_ratio"),
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
        "candidate_class": analysis.get("_candidate_class", "core"),
        "tech_direction": signal_ctx.get("tech_direction"),
        "tech_agreement": signal_ctx.get("tech_agreement"),
        "tech_adx_band": signal_ctx.get("tech_adx_band"),
        "tech_strength": signal_ctx.get("tech_strength"),
        "analysis_strength": analysis.get("_analysis_strength"),
        "rank_score": analysis.get("_rank_score"),
        "news_strength": signal_ctx.get("news_strength"),
        # Spec E2 (2026-08-20): der Wissensstand gehoert zur ENTSCHEIDUNG, nicht
        # zum Ticker. fundamentals_cache haelt nur eine Zeile je Ticker und
        # ueberschreibt sie alle 7 Tage -- ohne diese sechs Felder ist der
        # Fundamentalstand einer alten Prediction unrekonstruierbar und damit
        # fuer Sprint 3D nicht existent.
        "pe_ratio":       signal_ctx.get("pe_ratio"),
        "forward_pe":     signal_ctx.get("forward_pe"),
        "market_cap_b":   signal_ctx.get("market_cap_b"),
        "debt_equity":    signal_ctx.get("debt_equity"),
        "analyst_consensus": signal_ctx.get("analyst_consensus"),
        "analyst_consensus_period": signal_ctx.get("analyst_consensus_period"),
        # Spec E4: in BEIDEN Laeufen berechnet, nicht nur um 16:10 -- ein
        # Merkmal, das systematisch mit dem run_type korreliert, ist fuer 3D
        # schlimmer als keins. Reine DB-Rechnung, kostet nichts.
        "relative_strength": signal_checks.compute_relative_strength(
            conn, analysis["ticker"], date),
    }


def _run_checks(
    analysis: dict, conn, date: str, run_type: str,
    market_context: dict, sector_momentum: dict[int, dict],
    cluster_counts: dict[str, int], enforce: bool,
    earnings_in_days: int | None = None,
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
            signal_checks.check_earnings(
                direction, earnings_in_days, enforce=enforce),
            # Spec G1/G3: in BEIDEN Laeufen erhoben, immer weich. Sammelt die
            # Verteilung, damit STOP_MIN_INTRADAY_RANGE_FRAC nach ~30 Outcomes
            # eine Messung ist statt einer Annahme.
            signal_checks.check_stop_distance(
                analysis.get("sl_pct"), analysis.get("intraday_range_pct")),
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
    signal_context: dict[str, dict],
    sector_momentum: dict[int, dict] | None = None,
    enforce_checks: bool = False,
) -> dict:
    """Returns {top_long, top_short, commodities_crypto, divergence,
    divergence_stats} und schreibt je Auswahl eine predictions-Zeile.

    signal_context: dict[ticker -> dict] mit dem Technik-Signal, den drei
    C.1-Indikatoren und dem Phase-2-Scan-Wert je Ticker (main.py baut das ueber
    _signal_context()). Fehlt ein Ticker darin, verhaelt sich das wie ein
    fehlendes Technik-Signal (_classify() faellt auf 'divergence').

    enforce_checks steuert Entscheidung E4. ⚠️ Faktisch uebergibt HEUTE kein
    Aufrufer True: rank_and_persist() laeuft nur im Morgenlauf (run_pipeline),
    und der erhebt die Checks bewusst weich — um 15:00 ist die US-Boerse zu, die
    Morgenmail ist ein Research-Briefing. Die Durchsetzung sitzt im 16:10-Lauf,
    aber nicht hier: run_trade_proposals() geht ueber main._revalidate_all(),
    das die Checks selbst mit enforce=True aufruft. Der Parameter bleibt als
    Schalter bestehen, ist aber derzeit unbenutzt — wer ihn liest, soll nicht
    glauben, irgendwo laufe rank_and_persist() scharf.

    Klassifikation (Spec 5.3-5.5): core -> Top-10 nach rank_score, divergence
    -> eigene, auf DIVERGENCE_TOP_N je Richtung gedeckelte Liste, conflict ->
    verworfen als guardrail_reject (rule='tech_news_conflict'). Rohstoffe/
    Krypto (cc=True in _classify) werden nie als conflict verworfen (Spec
    20.5 #2)."""
    sector_momentum = sector_momentum or {}
    kept_stocks, abstained_stocks = _guardrail_filter(
        stock_analyses, conn, date, run_type)
    kept_cc, abstained_cc = _guardrail_filter(
        commodity_crypto_analyses, conn, date, run_type)
    abstained = abstained_stocks + abstained_cc

    # Spec 5.5, mittlere Tabellenzeile: Technik hat Richtung, Analyse enthielt
    # sich. _guardrail_filter() hat direction='none' oben bereits verworfen --
    # hier nur zaehlen, wie viele davon eine Technik-Richtung hatten, fuer die
    # Mail-Kennzahl. Nicht persistierbar (Claude hat sich enthalten, es gibt
    # kein TP/SL), deshalb ausschliesslich ein Zaehler.
    tech_only_abstentions = sum(
        1 for a in (*stock_analyses, *commodity_crypto_analyses)
        if a.get("direction") == "none"
        and signal_context.get(a.get("ticker", ""), {}).get("tech_direction")
            in ("long", "short")
    )

    counts = cluster_counts(conn, [a["ticker"] for a in kept_stocks])
    surviving_stocks: list[dict] = []
    for a in kept_stocks:
        ctx = signal_context.get(a["ticker"], {})
        results = _run_checks(
            a, conn, date, run_type, market_context, sector_momentum,
            counts, enforce_checks,
            earnings_in_days=ctx.get("earnings_in_days"),
        )
        if signal_checks.blocks(results):
            log.info(f"{a['ticker']}: durch B.3-Check verworfen "
                     f"({', '.join(r.rule for r in results if r.enforced)})")
            continue
        surviving_stocks.append(a)

    # ⚠️ KOPIE, NICHT MUTATION -- das ist keine Stilfrage. Die Analyse-Dicts in
    # stock_analyses/commodity_crypto_analyses sind DIESELBEN Objekte, die
    # main.py danach als analyses_by_ticker an check_open_positions() gibt, und
    # portfolio_check serialisiert sie ungefiltert in seinen Prompt
    # (src/portfolio_check.py:53, current_snapshot -> json.dumps). Wer hier
    # a["_candidate_class"] = ... schreibt, schickt drei neue Schluessel in
    # einen live laufenden Claude-Prompt -- genau der Vorfall aus
    # PROJECT_STATUS C.6, wo 29 Plan-1-Werte unbemerkt in vier Prompts liefen.
    # Die angereicherten Kopien wandern in den Rueckgabewert und damit in die
    # Mail; die Originale bleiben unberuehrt.
    def _enrich(a: dict, klasse: str, strength: int, rank_score: int | None) -> dict:
        return {**a, "_candidate_class": klasse,
                "_analysis_strength": strength, "_rank_score": rank_score}

    core: list[dict] = []
    divergence: list[dict] = []
    conflicts = 0
    for a in surviving_stocks:
        ctx = signal_context.get(a["ticker"], {})
        klasse, strength, rank_score = _classify(a, ctx, cc=False)
        if klasse == "core":
            core.append(_enrich(a, klasse, strength, rank_score))
        elif klasse == "divergence":
            divergence.append(_enrich(a, klasse, strength, rank_score))
        else:  # conflict
            conflicts += 1
            db.log_guardrail_reject(conn, {
                "date": date, "run_type": run_type, "ticker": a["ticker"],
                "direction": a["direction"], "rule": "tech_news_conflict",
                "detail": f"Analyse={a['direction']}, "
                          f"Technik={ctx.get('tech_direction')}",
                "enforced": 1,
            })

    cc_classified: list[dict] = []
    for a in kept_cc:
        ctx = signal_context.get(a["ticker"], {})
        klasse, strength, rank_score = _classify(a, ctx, cc=True)
        cc_classified.append(_enrich(a, klasse, strength, rank_score))

    def _key(a: dict) -> tuple:
        return _rank_key(a["_analysis_strength"], a["_rank_score"], a["ticker"])

    longs  = sorted((a for a in core if a["direction"] == "long"),  key=_key)[:TOP_N]
    shorts = sorted((a for a in core if a["direction"] == "short"), key=_key)[:TOP_N]

    div_long  = sorted((a for a in divergence if a["direction"] == "long"),  key=_key)
    div_short = sorted((a for a in divergence if a["direction"] == "short"), key=_key)
    overflow = (max(0, len(div_long) - config.DIVERGENCE_TOP_N)
               + max(0, len(div_short) - config.DIVERGENCE_TOP_N))
    div_long  = div_long[:config.DIVERGENCE_TOP_N]
    div_short = div_short[:config.DIVERGENCE_TOP_N]
    divergence_kept = div_long + div_short

    cc_sorted = sorted(cc_classified, key=_key)

    for a in (*longs, *shorts, *divergence_kept, *cc_sorted):
        ctx = signal_context.get(a["ticker"], {})
        etf_mom, db_mom = momentum_for(conn, a["ticker"], sector_momentum)
        db.save_prediction(conn, _to_prediction_row(
            a, date=date, run_type=run_type, market_context=market_context,
            conn=conn, signal_ctx=ctx, etf_momentum=etf_mom, db_momentum=db_mom,
        ))

    n_in = len(list(stock_analyses)) + len(list(commodity_crypto_analyses))
    n_out = len(longs) + len(shorts) + len(divergence_kept) + len(cc_sorted)
    log.info(
        f"Phase 4 done: {len(longs)} long, {len(shorts)} short, "
        f"{len(divergence_kept)} divergence, {len(cc_sorted)} commodity/crypto "
        f"persisted (aus {n_in} Analysen, davon {abstained} enthalten, "
        f"{conflicts} Technik-Konflikte, {overflow} Divergenz-Deckel-Ueberlauf)"
    )

    if n_out == 0:
        log.warning(
            f"Phase 4: KEINE Prediction persistiert (aus {n_in} Analysen, "
            f"{abstained} Enthaltungen). Der Lauf bleibt ohne Ergebnis — "
            f"Ursache pruefen: zu wenig Historie, Guardrails oder Enthaltungen."
        )
    return {
        "top_long": longs, "top_short": shorts,
        "commodities_crypto": cc_sorted,
        "divergence": divergence_kept,
        "divergence_stats": {
            "tech_only_abstentions": tech_only_abstentions,
            "conflicts": conflicts,
            "overflow": overflow,
        },
    }
