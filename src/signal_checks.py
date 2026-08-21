"""Die rechnerischen Checks aus Sprint 3B / B.3.

Bewusst netzwerk- und Claude-frei: jede Funktion nimmt Werte entgegen, die
anderswo bereits erhoben wurden (Markt-Kontext aus Phase 0b, Sektor-Momentum aus
Phase 1d, Kurse aus price_history), und gibt ein Urteil zurueck. Dadurch ist das
Modul ohne Mocking testbar.

Ein Check, der NICHT anschlaegt, gibt None zurueck und erzeugt keine Zeile — das
ist B.3.1 woertlich: "keines vorhanden -> kein Check, kein Log-Eintrag".

Ob ein anschlagender Check das Signal auch blockiert, entscheidet NICHT dieses
Modul, sondern der Aufrufer ueber den enforce-Parameter (Entscheidung E4):
der Morgenlauf (run_pipeline -> ranking._run_checks) uebergibt False, der
16:10-Lauf (run_trade_proposals -> main._revalidate_all) uebergibt True.
⚠️ Die beiden Aufrufstellen sind getrennter Code, keine gemeinsame Funktion mit
umgeschaltetem Flag — ein neuer Check muss in BEIDE Listen eingetragen werden,
sonst wird er nur erhoben oder nur durchgesetzt. Genau daran fehlte
check_earnings bis zum Plan-3b-Abschluss-Review (Befund I1)."""
import logging
import sqlite3
from dataclasses import dataclass

import config
from src import db

log = logging.getLogger("shares_future.signal_checks")


@dataclass(frozen=True)
class CheckResult:
    """Ein angeschlagener Check. `enforced=True` heisst: das Signal wird verworfen;
    `False` heisst: Warnung in der Mail, Signal geht durch."""
    rule: str
    detail: str
    enforced: bool


def daily_change_pct(
    conn: sqlite3.Connection, ticker: str, date: str,
) -> float | None:
    """Tagesperformance des letzten ABGESCHLOSSENEN Handelstags, in Prozent.

    Nimmt die beiden letzten Bars bis einschliesslich `date`. Seit dem
    Preismodell-Umbau (2026-08-06) enthaelt price_history nur finale Bars; der
    laufende Tag ist hier also bewusst NICHT enthalten. Das ist die richtige
    Grundlage: relative Staerke und D9 vergleichen abgeschlossene Tage, eine
    Teilbar waere kein Vergleichsmassstab.

    None, wenn weniger als zwei Bars vorliegen oder der Vortagesschluss 0 ist."""
    rows = conn.execute(
        """SELECT close FROM price_history
           WHERE ticker = ? AND date <= ?
           ORDER BY date DESC LIMIT 2""",
        (ticker, date),
    ).fetchall()
    if len(rows) < 2:
        return None
    cur, prev = float(rows[0]["close"]), float(rows[1]["close"])
    if prev <= 0:
        return None
    return (cur - prev) / prev * 100.0


def compute_relative_strength(
    conn: sqlite3.Connection, ticker: str, date: str,
) -> float | None:
    """Tagesperformance des Tickers minus die seines Sub-Sektor-ETF, in
    Prozentpunkten. None, wenn der Ticker keinem Sub-Sektor zugeordnet ist oder
    einer der beiden Werte fehlt.

    Kein Score und kein Guardrail (die 8-Dimensionen-Gewichtung ist eingefroren):
    der Wert geht als Input in den Re-Validierungs-Prompt und als Spalte in die Mail."""
    sector = db.get_ticker_sector(conn, ticker)
    if sector is None:
        return None
    own = daily_change_pct(conn, ticker, date)
    etf = daily_change_pct(conn, sector["etf"], date)
    if own is None or etf is None:
        return None
    return own - etf


def check_stop_distance(
    sl_pct: float | None, intraday_range_pct: float | None,
) -> CheckResult | None:
    """Meldet, wenn der Stop INNERHALB der typischen Tagesschwankung liegt.

    Anlass (2026-08-21): alle sieben vorliegenden Outcomes waren sl_hit, SECHS
    davon an Tag 1. Gemessen an intraday_range_pct lag der Stop bei 0,39-0,78
    einer typischen Tagesspanne -- kein einziger darueber. Ein Einstieg mitten
    in der Sitzung hat den Rest der Tagesspanne vor sich, und die deckt den Stop
    ab: er wird vom RAUSCHEN erreicht, bevor die These sich bewaehren kann.

    Gemessen an intraday_range_pct, NICHT an ATR: die ATR enthaelt die
    Uebernacht-Luecke, der Stop konkurriert aber gegen die Intraday-Bewegung.

    ⚠️ IMMER WEICH (enforced=False), und das ist keine Bequemlichkeit: mit der
    Startschwelle haette ein harter Check ALLE 14 damals vorliegenden Signale
    verworfen -- eine Abschaltung, keine Kalibrierung. Welche Schwelle richtig
    ist, weiss heute niemand; der Check sammelt erst die Verteilung
    (guardrail_rejects mit enforced=0, sichtbar in der Wochenmail), damit sie
    nach ~30 Outcomes eine MESSUNG ist statt einer Annahme. Dasselbe Muster wie
    SECTOR_GUARDRAIL_STRICT."""
    if sl_pct is None or not intraday_range_pct:
        return None
    frac = abs(sl_pct) / abs(intraday_range_pct)
    if frac >= config.STOP_MIN_INTRADAY_RANGE_FRAC:
        return None
    return CheckResult(
        rule="stop_inside_noise",
        detail=(f"Stop bei {frac:.2f} der typischen Tagesspanne "
                f"(SL {abs(sl_pct):.2f} % gegen Range {abs(intraday_range_pct):.2f} %, "
                f"Schwelle {config.STOP_MIN_INTRADAY_RANGE_FRAC})"),
        enforced=False,
    )


def check_stop_budget_spent(
    entry_price: float | None, sl_price: float | None,
    current_price: float | None, enforce: bool = False,
) -> CheckResult | None:
    """Verwirft ein Signal, dessen Risikobudget vor der Eroeffnung aufgebraucht ist.

    Der Morgenlauf definiert mit (entry - sl) ein Risikobudget. Laeuft der Kurs
    bis 16:10 dagegen, ist ein Teil davon schon weg, BEVOR die Position
    ueberhaupt eroeffnet wird. Ab STOP_BUDGET_SPENT_MAX ist die Praemisse des
    Morgens widerlegt.

    ⚠️ Warum nicht ueber die R/R-Ratio: weil R/R = Ertrag / RESTrisiko rechnet,
    STEIGT die Kennzahl, je naeher der Kurs an den Stop rueckt -- und der
    Guardrail prueft nur eine Untergrenze. NVDA wurde am 2026-08-19 so mit
    'R/R 26,2' als exzellentes Setup freigegeben und stand dabei 0,11 % vor
    seinem Stop; es wurde noch am selben Tag ausgestoppt. Ein Deckel auf die
    R/R waere ein Symptomfix an einer abgeleiteten Kennzahl -- das verbrauchte
    Budget beschreibt direkt, was schiefgeht.

    Richtungsneutral (Spec G5): bei einem Short liegt der Stop UEBER dem Entry,
    die Rechnung spiegelt sich. Ein Vorzeichenfehler traefe sonst nur eine
    Richtung und bliebe lange unentdeckt."""
    if entry_price is None or sl_price is None or current_price is None:
        return None
    budget = entry_price - sl_price          # long: > 0, short: < 0
    if budget == 0:
        return None
    spent = (entry_price - current_price) / budget
    if spent <= config.STOP_BUDGET_SPENT_MAX:
        return None
    return CheckResult(
        rule="stop_too_close",
        detail=(f"{spent:.0%} des Risikobudgets verbraucht, bevor die Position "
                f"eroeffnet ist (Kurs {current_price:.2f}, Stop {sl_price:.2f}, "
                f"Morgen-Entry {entry_price:.2f})"),
        enforced=enforce,
    )


def check_cluster(sector_name: str | None, count: int) -> CheckResult | None:
    """Warnt, wenn ab config.SECTOR_CLUSTER_WARN_AT Signale im selben Sub-Sektor
    liegen. Immer weich: Klumpenrisiko ist eine Positionsgroessen-Frage, keine
    Aussage ueber die Qualitaet des einzelnen Setups."""
    if sector_name is None or count < config.SECTOR_CLUSTER_WARN_AT:
        return None
    return CheckResult(
        rule="sector_cluster",
        detail=f"{count} Signale im Sub-Sektor {sector_name} — Klumpenrisiko",
        enforced=False,
    )


def blocks(results: list[CheckResult]) -> bool:
    """True, wenn mindestens ein Check das Signal tatsaechlich verwirft."""
    return any(r.enforced for r in results)


def check_vix(
    direction: str, confidence: str | None, vix_level: float | None, *,
    enforce: bool,
) -> CheckResult | None:
    """VIX-Filter aus B.3. Die beiden Schwellen gelten KUMULATIV, nicht exklusiv:
    ab VIX_HIGH_CONFIDENCE_ONLY nur noch confidence='high' — fuer beide Richtungen
    und ohne Obergrenze —, zusaetzlich ab VIX_NO_NEW_LONGS gar keine neuen
    Long-Signale mehr. Der Filter darf mit steigender Volatilitaet nur strenger
    werden, nie lockerer: ein Short mit confidence='medium' bleibt auch weit
    oberhalb von VIX_NO_NEW_LONGS blockiert, weil das Confidence-Band dort nicht
    endet, sondern weiterlaeuft. Nur das zusaetzliche Long-Verbot ist auf 'long'
    beschraenkt — Shorts sind ausschliesslich davon nie betroffen.

    Faellt Phase 0b aus und bleibt vix_level None, filtert der Check nicht — ein
    fehlender Messwert ist kein Grund, alle Signale zu verwerfen."""
    if vix_level is None:
        return None
    if vix_level > config.VIX_NO_NEW_LONGS and direction == "long":
        return CheckResult(
            rule="vix_no_new_longs",
            detail=f"VIX {vix_level:.1f} > {config.VIX_NO_NEW_LONGS:.0f} — "
                   f"keine neuen Long-Signale",
            enforced=enforce,
        )
    if vix_level > config.VIX_HIGH_CONFIDENCE_ONLY and confidence != "high":
        return CheckResult(
            rule="vix_high_confidence_only",
            detail=f"VIX {vix_level:.1f} > {config.VIX_HIGH_CONFIDENCE_ONLY:.0f} — "
                   f"nur confidence='high', hier '{confidence}'",
            enforced=enforce,
        )
    return None


def check_earnings(
    direction: str, earnings_in_days: int | None, *, enforce: bool,
) -> CheckResult | None:
    """Spec 5.3: ein Earnings-Termin in <= EARNINGS_WARNING_DAYS ist die
    einzige fundamentale Tatsache mit unmittelbarer Intraday-Wirkung -- er
    kann den Kurs springen lassen und entwertet damit das analytisch
    hergeleitete TP/SL. Ersetzt das reine Modell-Attribut 'earnings_warning'
    (das blockierte nichts) durch einen echten Check.

    earnings_in_days ist fuer Rohstoffe/Krypto immer None -- der Check ist
    dort trivial erfuellt, kein Sonderfall im Code noetig."""
    if earnings_in_days is None:
        return None
    if earnings_in_days > config.EARNINGS_WARNING_DAYS:
        return None
    return CheckResult(
        rule="earnings_imminent",
        detail=f"Earnings in {earnings_in_days} Tag(en) "
               f"(<= {config.EARNINGS_WARNING_DAYS}) — TP/SL-Basis unsicher",
        enforced=enforce,
    )


def _supports(direction: str, momentum: float) -> bool:
    """True, wenn das Sektor-Momentum in dieselbe Richtung zeigt wie der Trade."""
    return momentum > 0 if direction == "long" else momentum < 0


def check_sector_momentum(
    direction: str, etf_momentum: float | None, db_momentum: float | None, *,
    enforce: bool,
) -> CheckResult | None:
    """D9-Guardrail nach B.3.1. Verglichen wird die RICHTUNG, nie der Betrag.

    Der Live-Lauf vom 2026-07-28 zeigt Abweichungen um Faktor ~2,5 zwischen ETF-
    und DB-Signal bei identischem Vorzeichen (Retail +2,89% gegen +1,17%): XRT ist
    gleichgewichtet und small-cap-lastig, unsere Retail-Ticker sind AMZN/WMT/HD.
    Ein Schwellenwert auf der Differenz waere damit reines Rauschen.

    Hart verworfen wird nur, wenn BEIDE Signale vorliegen, in dieselbe Richtung
    zeigen, der Trade-Richtung widersprechen — und SECTOR_GUARDRAIL_STRICT an ist."""
    if etf_momentum is None and db_momentum is None:
        return None

    if etf_momentum is not None and db_momentum is not None:
        if (etf_momentum > 0) != (db_momentum > 0):
            return CheckResult(
                rule="sector_momentum_conflict",
                detail=f"Sektor-Momentum widerspruechlich: ETF {etf_momentum:+.2f}%, "
                       f"DB {db_momentum:+.2f}%",
                enforced=False,
            )
        if _supports(direction, etf_momentum):
            return None
        return CheckResult(
            rule="sector_momentum",
            detail=f"Beide Sektor-Signale gegen {direction}: "
                   f"ETF {etf_momentum:+.2f}%, DB {db_momentum:+.2f}%",
            enforced=enforce and config.SECTOR_GUARDRAIL_STRICT,
        )

    value = etf_momentum if etf_momentum is not None else db_momentum
    source = "ETF" if etf_momentum is not None else "DB"
    if _supports(direction, value):
        return None
    return CheckResult(
        rule="sector_momentum_partial",
        detail=f"Nur das {source}-Signal vorhanden ({value:+.2f}%) und gegen "
               f"{direction} — kein Gegencheck moeglich",
        enforced=False,
    )


def momentum_for(
    conn: sqlite3.Connection, ticker: str, sector_momentum: dict[int, dict],
) -> tuple[float | None, float | None]:
    """Liefert (etf_momentum, db_momentum) fuer den Sub-Sektor des Tickers.
    (None, None), wenn der Ticker keinem Sub-Sektor zugeordnet ist."""
    sector = db.get_ticker_sector(conn, ticker)
    if sector is None:
        return None, None
    entry = sector_momentum.get(sector["sector_id"]) or {}
    return entry.get("etf_momentum"), entry.get("db_momentum")


def cluster_counts(
    conn: sqlite3.Connection, tickers: list[str],
) -> dict[str, int]:
    """Zaehlt, wie viele der uebergebenen Ticker je Sub-Sektor anfallen —
    Grundlage fuer die Klumpenrisiko-Warnung. Ungemappte Ticker zaehlen nicht mit."""
    counts: dict[str, int] = {}
    for t in tickers:
        sector = db.get_ticker_sector(conn, t)
        if sector is None:
            continue
        counts[sector["name"]] = counts.get(sector["name"], 0) + 1
    return counts


def check_opening_gap(
    pre_market_price: float | None, current_price: float | None,
) -> CheckResult | None:
    """Warnt bei einer grossen Luecke zwischen dem 15:00-Kurs und dem aktuellen.

    Als 15:00-Kurs dient der entry_price der Morgen-Prediction — genau der Wert, den
    B.3 mit 'pre_market-Kurs' meint. Kein zusaetzlicher Abruf noetig.

    Immer weich: ein Gap sagt etwas ueber den Einstiegszeitpunkt, nicht ueber die
    These. Ob das Setup dadurch unbrauchbar wird, faengt die neu berechnete
    R/R-Ratio in main._persist_revision() ab."""
    if not pre_market_price or current_price is None:
        return None
    gap = (current_price - pre_market_price) / pre_market_price * 100.0
    if abs(gap) < config.OPENING_GAP_WARN_PCT:
        return None
    return CheckResult(
        rule="opening_gap",
        detail=f"Gap seit 15:00: {gap:+.1f}% "
               f"({pre_market_price} → {current_price})",
        enforced=False,
    )


def recompute_rr_ratio(
    entry: float, tp: float, sl: float, direction: str,
) -> float | None:
    """Chance/Risiko-Verhaeltnis gegen einen NEUEN Einstiegskurs.

    Die Kursziele der Morgen-These bleiben absolut — sie wandern nicht, nur weil der
    Einstieg 40 Minuten spaeter erfolgt. Verschiebt sich der Einstieg aber Richtung TP,
    schrumpft das Verhaeltnis. None, wenn der Kurs bereits durch TP oder SL gelaufen
    ist; dann gibt es kein sinnvolles Verhaeltnis mehr."""
    if direction == "long":
        reward, risk = tp - entry, entry - sl
    else:
        reward, risk = entry - tp, sl - entry
    if reward <= 0 or risk <= 0:
        return None
    return reward / risk
