"""Phase 1: Data collection.

Provider- und DB-Verdrahtung fuer collect()/_process_ticker(): zieht OHLCV-Bars
ueber die DataProvider-Schnittstelle, erkennt und fuellt Luecken, schreibt nach
db.py. Die reine Indikatormathematik (RSI, MACD, ATR, ...) sitzt seit Task 3
in src/indicators.py -- dieses Modul importiert sie nur noch.
"""
import logging
import time
from datetime import date as _date_cls, timedelta
from typing import Any

from src.indicators import (
    MIN_BARS_RSI,
    compute_adx,
    compute_atr_abs,
    compute_atr_pct,
    compute_bb_position,
    compute_bollinger_raw,
    compute_cci,
    compute_donchian,
    compute_ema_distance_pct,
    compute_ichimoku,
    compute_intraday_range_pct,
    compute_macd_raw,
    compute_macd_signal,
    compute_momentum,
    compute_obv,
    compute_price_changes,
    compute_psar,
    compute_rsi_14,
    compute_rsi_trend,
    compute_sma_distance_pct,
    compute_stochastic,
    compute_trix,
    compute_volume_ratio,
    compute_willr,
)

log = logging.getLogger("shares_future.data_collector")

# Wie weit die Lueckenpruefung zurueckschaut. 220 Bars — deckungsgleich mit dem
# Indikator-Ladefenster seit dem Umbau (2026-08-12). Eine dort versteckte Luecke
# kann sonst SMA200 verfaelschen. Diese Anhebung aendert, welche Ticker uebersprungen
# werden: mehr erkannte Luecken → mehr Nachladeversuche → ggf. mehr Skips.
GAP_SCAN_BARS = 220


from src.providers.base import DataProvider
from src import db, technical_signal
import config

BATCH_PAUSE_EVERY = 30


def _classify_data_quality(td: dict) -> str:
    """Classifies a ticker's data as 'low' (missing core indicators), 'medium'
    (missing peripheral fundamentals), or 'high' (everything present)."""
    required   = ("rsi_14", "atr_pct")
    peripheral = ("pe_ratio", "market_cap_b", "sector", "above_sma200")
    if any(td.get(k) is None for k in required):
        return "low"
    missing_peripheral = sum(1 for k in peripheral if td.get(k) is None)
    return "medium" if missing_peripheral >= 1 else "high"


def _earnings_in_days(next_date_str: str | None, today_str: str) -> int | None:
    """Rechnet das gecachte earnings_next_date (ISO-Datum) in Kalendertage ab
    `today_str` um (Sprint 3C / Analyse-Pipeline-Umbau, Task 7 -- Spec 18.1d).

    None bei fehlendem oder unparsebarem Datum -- ein kaputter String darf den
    Lauf nicht reissen. Liegt das Datum in der Vergangenheit (Termin bereits
    gelaufen, der Cache-Eintrag aber noch innerhalb der 7-Tage-TTL warm), gibt
    es ebenfalls None statt eines negativen Werts zurueck: das Feld heisst
    "Tage bis zum NAECHSTEN Termin" und war das auch vor diesem Umbau so --
    Finnhubs get_earnings_calendar() lieferte nur zukuenftige Termine, nie
    einen negativen days_to_next. Ein negativer Wert waere hier ein stiller
    Bedeutungswechsel auf "Tage seit dem letzten Termin", den kein Konsument
    (die vier Claude-Prompts, die td json.dumps'en) erwartet."""
    if not next_date_str:
        return None
    try:
        delta = (
            _date_cls.fromisoformat(next_date_str) - _date_cls.fromisoformat(today_str)
        ).days
    except ValueError:
        log.warning(f"earnings_next_date unparsebar: {next_date_str!r}")
        return None
    return delta if delta >= 0 else None


def _expected_trading_days(from_date: str, to_date: str) -> list[str]:
    """Listet alle Wochentage (Mo-Fr) NACH `from_date` bis einschliesslich `to_date`.

    Bekannte Einschraenkung (Spec B.8): ohne Boersen-Feiertagskalender gelten
    US-Feiertage wie Thanksgiving faelschlich als Handelstag. Der Nachladeversuch
    liefert dann schlicht keine Bars — funktional unkritisch, kostet je einen
    leeren API-Call."""
    start = _date_cls.fromisoformat(from_date)
    end = _date_cls.fromisoformat(to_date)
    out: list[str] = []
    cur = start + timedelta(days=1)
    while cur <= end:
        if cur.weekday() < 5:          # 0=Montag ... 4=Freitag
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def _consecutive_runs(days: list[str]) -> list[list[str]]:
    """Gruppiert aufsteigend sortierte Handelstage in zusammenhaengende Laeufe.

    Zusammenhaengend heisst: hoechstens ein Wochenende dazwischen (<= 3
    Kalendertage), damit Freitag und Montag als ein Lauf gelten."""
    runs: list[list[str]] = []
    for d in days:
        if runs and (_date_cls.fromisoformat(d)
                     - _date_cls.fromisoformat(runs[-1][-1])).days <= 3:
            runs[-1].append(d)
        else:
            runs.append([d])
    return runs


def _first_gap_day(have: set[str], oldest: str, newest: str, date: str) -> str | None:
    """Erster Handelstag, ab dem nachgeladen werden muss — oder None.

    Zwei Faelle, bewusst mit verschiedenen Schwellen:

    * INNENLIEGEND (zwischen `oldest` und `newest`): erst ein Lauf von zwei
      aufeinanderfolgenden Handelstagen zaehlt. Ohne Boersenkalender sind
      einzelne fehlende Wochentage US-Feiertage — in der echten Datenbank sind
      35 der 1000 AAPL-Bars genau das. Wer sie als Luecke behandelt, laedt bei
      jedem Lauf fuer jeden Ticker ins Leere nach.
    * HINTEN (nach `newest`): unveraendert die alte Regel. Der laufende Tag
      zaehlt mit, greift also ab einem echten fehlenden Handelstag."""
    interior = [d for d in _expected_trading_days(oldest, newest) if d not in have]
    for run in _consecutive_runs(interior):
        if len(run) >= 2:
            return run[0]

    trailing = _expected_trading_days(newest, date)
    # Nur der heutige Bar fehlt -> der ist noch nicht final, den holt final_close.
    return trailing[0] if len(trailing) > 1 else None


def _fill_price_gaps(
    ticker: str, price_provider: DataProvider, conn, date: str,
) -> int:
    """Laedt fehlende Bars bis `date` nach und gibt die Anzahl neu eingefuegter
    Zeilen zurueck.

    Kein Nachladen, wenn der Ticker noch gar keine Historie hat (das uebernimmt
    setup/historical_loader.py) oder wenn nur der heutige Bar fehlt — der ist zur
    Laufzeit noch nicht final und wird erst vom final_close-Lauf geschrieben.

    Geprueft wird der GESAMTE juengste Abschnitt, nicht nur der letzte Bar.
    Vorher fragte die Erkennung allein `MAX(date)`: sobald final_close nach einem
    Ausfall die Bar von gestern schrieb, war der Zeiger wieder aktuell und das
    Loch dahinter fuer immer unsichtbar. Gemessen am 2026-08-08 — AAPL hatte
    2026-07-29 und 2026-08-07, dazwischen sieben Handelstage nichts, und ein
    vollstaendiger close-Lauf ruehrte sie nicht an."""
    rows = conn.execute(
        "SELECT date FROM price_history WHERE ticker = ? AND date <= ? "
        "ORDER BY date DESC LIMIT ?",
        (ticker, date, GAP_SCAN_BARS),
    ).fetchall()
    if not rows:
        return 0

    have = {r["date"] for r in rows}
    newest, oldest = max(have), min(have)
    if newest >= date and len(have) == 1:
        return 0

    start = _first_gap_day(have, oldest=oldest, newest=newest, date=date)
    if start is None:
        return 0

    # get_ohlc_after ist exklusiv im Startdatum — einen Tag davor ansetzen.
    anchor = (_date_cls.fromisoformat(start) - timedelta(days=1)).isoformat()
    log.info(
        f"{ticker}: Luecke erkannt — ab {start} fehlen Handelstage "
        f"(letzter Bar {newest}). Lade nach."
    )
    try:
        df = price_provider.get_ohlc_after(ticker, anchor, date)
    except Exception as e:
        log.warning(f"{ticker}: Gap-Nachladen fehlgeschlagen: {e}")
        return 0
    if df is None or df.empty:
        log.warning(f"{ticker}: Gap-Nachladen lieferte keine Bars")
        return 0

    _raw_source = getattr(price_provider, "_source_name", None)
    source = _raw_source if isinstance(_raw_source, str) else "capital.com"
    inserted = 0
    for ts, r in df.iterrows():
        d = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        # `>= date` statt `> date`: der laufende Tag ist noch nicht final und
        # gehoert final_close. Ihn hier nachzuladen brachte die provisorische
        # Teilbar zurueck, deren Beseitigung der ganze Umbau ist.
        if d < start or d >= date or d in have:
            continue
        db.insert_price_bar_if_missing(
            conn, ticker=ticker, date=d,
            open_=float(r.get("Open", 0)), high=float(r.get("High", 0)),
            low=float(r.get("Low", 0)), close=float(r.get("Close", 0)),
            volume=int(r.get("Volume", 0) or 0), source=source,
        )
        inserted += 1
    conn.commit()
    log.info(f"{ticker}: {inserted} fehlende Bars nachgeladen")
    return inserted


def _persist_indicators(conn, ticker: str, date: str, td: dict) -> None:
    """Writes one row of computed technical indicators for `ticker`/`date` to
    the technical_indicators table."""
    db.upsert_technical_indicators(conn, {
        "ticker": ticker, "date": date,
        "rsi_14": td.get("rsi_14"),
        "macd_signal": td.get("macd_signal"),
        "atr_pct": td.get("atr_pct"),
        "bb_position": td.get("bb_position"),
        "above_sma20": td.get("above_sma20"),
        "above_sma50": td.get("above_sma50"),
        "above_sma200": td.get("above_sma200"),
        "volume_ratio": td.get("volume_ratio"),
        "intraday_range_pct": td.get("intraday_range_pct"),
        # Sprint 3C / Analyse-Pipeline-Umbau (Task 7): die 29 neuen Spalten.
        "ema_50_dist_pct": td.get("ema_50_dist_pct"),
        "macd_line": td.get("macd_line"),
        "macd_signal_line": td.get("macd_signal_line"),
        "macd_hist": td.get("macd_hist"),
        "adx_14": td.get("adx_14"),
        "di_plus": td.get("di_plus"),
        "di_minus": td.get("di_minus"),
        "psar_value": td.get("psar_value"),
        "psar_dir": td.get("psar_dir"),
        "ichi_tenkan": td.get("ichi_tenkan"),
        "ichi_kijun": td.get("ichi_kijun"),
        "ichi_senkou_a": td.get("ichi_senkou_a"),
        "ichi_senkou_b": td.get("ichi_senkou_b"),
        "ichi_chikou": td.get("ichi_chikou"),
        "stoch_k": td.get("stoch_k"),
        "stoch_d": td.get("stoch_d"),
        "willr_14": td.get("willr_14"),
        "cci_20": td.get("cci_20"),
        "mom_12": td.get("mom_12"),
        "trix": td.get("trix"),
        "trix_signal": td.get("trix_signal"),
        "bb_upper": td.get("bb_upper"),
        "bb_lower": td.get("bb_lower"),
        "bb_width": td.get("bb_width"),
        "atr_abs": td.get("atr_abs"),
        "donch_upper": td.get("donch_upper"),
        "donch_mid": td.get("donch_mid"),
        "donch_lower": td.get("donch_lower"),
        "obv": td.get("obv"),
    })


def _live_price(
    ticker: str, premarket_price: float | None, df,
) -> tuple[float, float | None]:
    """Entscheidungskurs + premarket_change_pct fuer die Sidecar (Sprint 3C /
    Analyse-Pipeline-Umbau, Task 5, R1/R3/R7).

    `premarket_price` kommt seit dem Sweep-Umbau NICHT mehr aus einem eigenen
    Einzelabruf hier, sondern aus Phase 1b (_sweep_phase() in collect()) --
    Spec 4.3.1: EIN Batch-Call ueber alle Ticker statt einem je Ticker. Fehlt
    er (Chunk uebersprungen, Antwort ohne bid, oder ein Provider ganz ohne
    Batch-Unterstuetzung), faellt der Kurs auf den letzten finalen Close
    zurueck (WARNING, kein Skip -- ein alter Kurs ist besser als gar keine
    Analyse). premarket_change_pct bleibt in diesem Fall None statt 0: eine 0
    behauptete "eroeffnet unveraendert", eine Beobachtung, die niemand
    gemessen hat (Spec 4.3)."""
    last_close = float(df["Close"].iloc[-1])
    if premarket_price is not None:
        pct = (
            (premarket_price - last_close) / last_close * 100
            if last_close else None
        )
        return float(premarket_price), pct
    log.warning(f"{ticker}: kein Live-Kurs, nutze letzten finalen Close")
    return last_close, None


def _skip(conn, ticker: str, date: str, run_type: str, reason: str) -> None:
    """Vermerkt einen uebersprungenen Ticker in skipped_tickers UND im Log.

    Beides ist noetig: die Zeile traegt die Auswertung (Weekly, Deaktivierung),
    die Logzeile macht einen Lauf ohne DB-Zugriff nachvollziehbar. Am 2026-08-04
    fehlte Letzteres — 18 Ticker verschwanden ohne Begruendung aus dem
    Actions-Log, und die Ursache war erst nach dem Download der CI-Datenbank
    sichtbar."""
    log.warning(f"{ticker}: uebersprungen — {reason}")
    db.log_skipped_ticker(
        conn, ticker=ticker, date=date, run_type=run_type,
        reason=reason, learnable=False,
    )


def _process_ticker(
    ticker: str,
    price_provider: DataProvider,
    earnings_provider: DataProvider,
    conn,
    date: str,
    run_type: str,
    premarket_price: float | None = None,
) -> tuple[dict, dict] | None:
    """Runs the full Phase-1 pipeline for one ticker: ensures today's bar exists,
    computes indicators from the last 220 DB days, and reads fundamentals/earnings
    from fundamentals_cache (cache-only, s.u.). Returns (TickerData dict, sidecar
    entry dict), or None (with a skipped_tickers row) if there's insufficient or
    low-quality data.

    `premarket_price` kommt seit Task 5 aus dem Batch-Sweep in collect()
    (Phase 1b), nicht mehr aus einem Einzelabruf hier drin (R3). Der zweite
    Rueckgabewert -- premarket_change_pct plus (seit Task 6) das Technik-Signal
    -- ist bewusst NICHT Teil des td-Dicts (R1/Spec 18.1e): collect() uebernimmt
    ihn unveraendert als Sidecar-Eintrag.

    `earnings_provider` bleibt seit Task 7 (Sprint 3C / Analyse-Pipeline-Umbau)
    Teil der Signatur, wird hier aber nicht mehr aufgerufen -- Phase 1 macht 0
    Finnhub-Calls, das Nachladen sitzt in fetch_missing_fundamentals()
    (Phase 2b, ab Task 10 verdrahtet). Der Parameter bleibt fuer eine stabile
    Schnittstelle zu collect() stehen, statt den Aufrufer und alle bestehenden
    Tests fuer eine Zwischen-Task umzubauen."""
    # Step 1: Luecken schliessen (Spec B.8)
    _fill_price_gaps(ticker, price_provider, conn, date)

    # Step 2: Load last 220 days from DB for indicator calculation
    df = db.load_price_history_from_db(conn, ticker, as_of_date=date, limit=220)

    if df is None or len(df) < MIN_BARS_RSI:
        rows = 0 if df is None else len(df)
        _skip(
            conn, ticker=ticker, date=date, run_type=run_type,
            reason=f"insufficient bars: {rows} < {MIN_BARS_RSI}",
        )
        return None

    # Entscheidungskurs kommt LIVE (aus dem Sweep), nicht aus price_history: die
    # Historie enthaelt seit dem Preismodell-Umbau nur noch finale Tagesbars und
    # endet damit bei D-1. Ohne diesen Live-Kurs analysierte die Pipeline auf dem
    # Schluss von gestern.
    price, premarket_change_pct = _live_price(ticker, premarket_price, df)

    # Indicators (computed from DB data — df has capitalized column names)
    pc = compute_price_changes(df)
    td: dict[str, Any] = {
        "ticker": ticker,
        "price": price,
        **pc,
        "rsi_14":             compute_rsi_14(df),
        "rsi_trend":          compute_rsi_trend(df),
        "macd_signal":        compute_macd_signal(df),
        "atr_pct":            compute_atr_pct(df),
        "bb_position":        compute_bb_position(df),
        "above_sma20":        compute_sma_distance_pct(df, 20),
        "above_sma50":        compute_sma_distance_pct(df, 50),
        "above_sma200":       compute_sma_distance_pct(df, 200),
        "volume_ratio":       compute_volume_ratio(df),
        "intraday_range_pct": compute_intraday_range_pct(df),
    }

    # Sprint 3C / Analyse-Pipeline-Umbau (Plan 1, Task 5/6): 29 weitere Spalten
    # fuer technical_indicators. Bewusst NICHT in td -- td wird unveraendert in
    # vier Claude-Prompts json.dumps't (quick_filter.py, deep_analysis.py,
    # commodities_crypto.py, portfolio_check.py ueber main.py's `snapshots`).
    # Ein zusaetzlicher Key hier wuerde also Ticker-Auswahl und Scoring
    # beeinflussen, obwohl kein Konsument die neuen Werte lesen soll (das ist
    # erst Sprint 3D). Weiter unten zusammengefuehrt: fuer die Persistierung UND
    # (Task 6) als Eingabe fuer technical_signal.compute() -- macd_line/
    # macd_signal_line/adx_14 sitzen nur hier, nicht in td.
    extra_indicators: dict[str, Any] = {
        **compute_macd_raw(df),
        **compute_adx(df),
        **compute_psar(df),
        **compute_ichimoku(df),
        **compute_stochastic(df),
        **compute_trix(df),
        **compute_bollinger_raw(df),
        **compute_donchian(df),
        "ema_50_dist_pct": compute_ema_distance_pct(df, 50),
        "willr_14":        compute_willr(df),
        "cci_20":          compute_cci(df),
        "mom_12":          compute_momentum(df),
        "atr_abs":         compute_atr_abs(df),
        "obv":             compute_obv(df),
    }

    # Fundamentals: NUR Cache-Lesung (Sprint 3C / Analyse-Pipeline-Umbau, Task 7).
    # Phase 1 ruft Finnhub nicht mehr auf -- 0 Calls, kein Geld. Das Nachladen
    # bei einem Cache-Miss sitzt jetzt in fetch_missing_fundamentals()
    # (Phase 2b), die diese Task baut, aber bewusst noch NICHT verdrahtet
    # (das macht Task 10, R16).
    #
    # R14: bewusst akzeptierte Verhaltensaenderung bis dahin -- ein Cache-Miss
    # kann keinen Skip ausloesen (_classify_data_quality stuft 'low' nur nach
    # rsi_14/atr_pct ein), verschiebt aber 'high' auf 'medium', weil pe_ratio/
    # market_cap_b/sector zu den peripheral-Feldern zaehlen.
    fundamentals = db.get_cached_fundamentals(conn, ticker, today=date) or {}

    td.update({
        "pe_ratio":              fundamentals.get("pe_ratio"),
        "forward_pe":            fundamentals.get("forward_pe"),
        "market_cap_b":          fundamentals.get("market_cap_b"),
        "debt_equity":           fundamentals.get("debt_equity"),
        "sector":                fundamentals.get("sector", "Unknown"),
        "analyst_target_upside": fundamentals.get("analyst_upside"),
        "analyst_consensus":     fundamentals.get("consensus"),
    })

    # Sub-Sektor-Mapping organisch pflegen (Sprint 3B / B.10): der Finnhub-Rohwert
    # wird normalisiert und in ticker_sectors geschrieben — kein statisches
    # Ticker->Sektor-Mapping im Code. Unbekannte Werte loggt db.resolve_sector_id();
    # der Ticker bleibt dann schlicht ungemappt und laeuft ohne Sektor-Guardrail.
    # Bei einem Cache-Miss ist fundamentals.get("sector") None -- resolve_sector_id
    # gibt dann fruehzeitig None zurueck und der Upsert entfaellt, eine bestehende
    # Zuordnung bleibt also stehen statt auf 'Unknown' zurueckgesetzt zu werden.
    _sector_id = db.resolve_sector_id(conn, fundamentals.get("sector"))
    if _sector_id is not None:
        db.upsert_ticker_sector(conn, ticker, _sector_id, source="finnhub")

    # Earnings (R15): get_earnings_calendar() verschwindet aus dem Tageslauf --
    # gehoert in den Wochenjob (Spec 18.1c). earnings_beat_pct gibt es im
    # Tageslauf deshalb nicht mehr. earnings_in_days wird stattdessen aus dem
    # gecachten earnings_next_date (Datum, s.o. save_fundamentals_cache)
    # gerechnet -- relativ zum HEUTIGEN Abrufdatum, nicht zum Fetch-Zeitpunkt.
    td["earnings_in_days"]  = _earnings_in_days(fundamentals.get("earnings_next_date"), date)
    td["earnings_beat_pct"] = None

    td["data_quality"] = _classify_data_quality(td)
    if td["data_quality"] == "low":
        _skip(
            conn, ticker=ticker, date=date, run_type=run_type,
            reason="data_quality=low: critical indicators missing",
        )
        return None

    merged_indicators = {**td, **extra_indicators}
    _persist_indicators(conn, ticker, date, merged_indicators)

    # Sprint 3C / Analyse-Pipeline-Umbau (Task 6): das deterministische
    # Technik-Signal braucht Werte aus BEIDEN Dicts (RSI/SMA aus td, MACD/ADX
    # aus extra_indicators) -- derselbe Merge wie fuer die Persistierung.
    # Landet, wie premarket_change_pct, NUR im Sidecar-Eintrag (R1): td selbst
    # bleibt unangetastet.
    signal = technical_signal.compute(merged_indicators)
    sidecar_entry = {
        "premarket_change_pct": premarket_change_pct,
        "tech_direction":       signal.direction,
        "tech_agreement":       signal.agreement,
        "tech_adx_band":        signal.adx_band,
        "tech_strength":        signal.strength,
    }
    return td, sidecar_entry


def _gate_phase(tickers: list[str], conn, date: str) -> list[str]:
    """Phase 1a: filtert dauerhaft deaktivierte Ticker heraus (Sprint 3B / B.7),
    bevor Sweep oder Indikatoren auch nur einen weiteren API-Call ausloesen.

    Die Bar-Zaehlung bleibt bewusst AUSSEN VOR (Spec 18.1a): sie sitzt weiter in
    _process_ticker(), NACH dem Luecken-Nachladen dort. Wuerde sie hierher
    vorgezogen, fielen Ticker raus, die nach dem Nachladen genug Bars haetten.

    Rohstoffe und Krypto sind von der Deaktivierung ausgenommen (Spec 6.1):
    sie bleiben trotz inaktivem Status Survivors, nur mit WARNING statt dem
    harten Rauswurf -- das Universum ist hier so klein, dass ein dauerhaft
    fehlender Rohstoff-/Krypto-Wert schwerer wiegt als bei 500 Aktien."""
    exempt = set(config.COMMODITY_TICKERS.values()) | set(config.CRYPTO_TICKERS.values())
    survivors: list[str] = []
    for t in tickers:
        if db.is_ticker_inactive(conn, t, today=date):
            if t in exempt:
                log.warning(
                    f"{t}: inaktiv, aber Rohstoff/Krypto-Ausnahme (Spec 6.1) — "
                    f"bleibt Survivor"
                )
                survivors.append(t)
                continue
            status = db.get_ticker_status(conn, t)
            log.info(
                f"{t}: inaktiv nach {status['skip_count']} Skips — uebersprungen, "
                f"Retry ab {status['retry_after']}"
            )
            continue
        survivors.append(t)
    return survivors


def _sweep_phase(
    tickers: list[str], price_provider: DataProvider,
) -> dict[str, float | None]:
    """Phase 1b: EIN Batch-Call ueber alle Survivors fuer den Live-Kurs
    (Spec 4.3.1) statt bis zu 500 Einzelabrufen. Der Rueckgabewert speist in
    Phase 1c sowohl td["price"] als auch premarket_change_pct (R3) -- niemals
    beides einzeln je Ticker abgerufen.

    Provider ohne Batch-Unterstuetzung (nur Capital.com liefert ueberhaupt
    Live-Kurse, s. src/providers/base.py) werfen NotImplementedError; der
    Sweep faengt das ab und liefert ein leeres Dict -- jeder Ticker faellt dann
    in Phase 1c auf seinen letzten finalen Close zurueck, keiner wird deswegen
    uebersprungen. Uebersteigt der Anteil der Survivors ohne Live-Kurs 20 %,
    warnt der Sweep von sich aus (Spec 4.3, Muster D3). Keine Batch-Pause hier
    (Spec 4.3.2) -- die 429-Behandlung steckt bereits in
    get_premarket_prices_batch(), die Pause um die Netz-lastige 1c-Schleife
    bleibt in collect()."""
    if not tickers:
        return {}
    try:
        prices = price_provider.get_premarket_prices_batch(tickers)
    except NotImplementedError as e:
        log.warning(f"Sweep: {e}")
        return {}

    missing = sum(1 for t in tickers if prices.get(t) is None)
    if missing / len(tickers) > 0.2:
        log.warning(
            f"Sweep: {missing} von {len(tickers)} Survivors ohne Live-Kurs "
            f"({missing / len(tickers):.0%}) — Fallback auf letzten Close"
        )
    return prices


def collect(
    tickers: list[str],
    price_provider: DataProvider,
    earnings_provider: DataProvider,
    conn,
    date: str,
    run_type: str,
) -> tuple[list[dict], int, dict[str, dict]]:
    """Run Phase 1 in drei Paessen (Sprint 3C / Analyse-Pipeline-Umbau, Task 5):

      1a Gate (_gate_phase):    inaktive Ticker raus, Rohstoffe/Krypto ausgenommen
      1b Sweep (_sweep_phase):  EIN Batch-Kursabruf ueber alle Survivors
      1c Indikatoren:           _process_ticker() je Survivor, lokal

    Gibt (ticker_data_list, skipped_count, sidecar) zurueck. `sidecar` traegt je
    erfolgreich verarbeitetem Ticker premarket_change_pct und (seit Task 6) das
    Technik-Signal (tech_direction/tech_agreement/tech_adx_band/tech_strength)
    -- NIEMALS als Key in td (R1/Spec 18.1e): td wird unveraendert in vier
    Claude-Prompts json.dumps't, ein zusaetzlicher Key dort aenderte
    Ticker-Auswahl und Scoring.

    Die Batch-Pause (BATCH_PAUSE_EVERY) sitzt weiterhin um die 1c-Schleife --
    die ruft ueber _fill_price_gaps() weiter je Ticker bei Capital.com an. Der
    Sweep braucht keine eigene Pause (Spec 4.3.2)."""
    survivors = _gate_phase(tickers, conn, date)
    premarket_prices = _sweep_phase(survivors, price_provider)

    results: list[dict] = []
    sidecar: dict[str, dict] = {}
    for i, t in enumerate(survivors):
        out = _process_ticker(
            ticker=t,
            price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn,
            date=date,
            run_type=run_type,
            premarket_price=premarket_prices.get(t),
        )
        if out is not None:
            td, sidecar_entry = out
            # Erfolgreicher Abruf heilt den Zaehler — sonst liefe ein Ticker durch
            # verstreute Einzelausfaelle ueber Monate in die Deaktivierung.
            db.reactivate_ticker(conn, t)
            results.append(td)
            sidecar[t] = sidecar_entry

        if (i + 1) % BATCH_PAUSE_EVERY == 0 and (i + 1) < len(survivors):
            log.info(
                f"Batch pause: processed {i + 1}/{len(survivors)} tickers, "
                f"sleeping {config.CAPITAL_COM_BATCH_PAUSE}s"
            )
            time.sleep(config.CAPITAL_COM_BATCH_PAUSE)

    # len(tickers) - len(results) statt eines eigenen Zaehlers: identisch mit
    # der Summe aus Gate-Rauswuerfen und 1c-Skips, aber ohne zwei Zaehler
    # synchron halten zu muessen.
    skipped = len(tickers) - len(results)
    if skipped:
        # Gebuendelt statt 500 Einzelzeilen: die Verteilung der Gruende sagt,
        # ob eine Handvoll Ticker zickt oder die halbe Datenbank leer ist.
        reasons = db.skip_reason_counts(conn, date=date, run_type=run_type)
        breakdown = ", ".join(f"{n}x {r}" for r, n in reasons)
        log.warning(
            f"Phase 1: {skipped} von {len(tickers)} Tickern uebersprungen"
            + (f" — {breakdown}" if breakdown else "")
        )

    log.info(f"Phase 1 done: {len(results)} ok, {skipped} skipped")
    return results, skipped, sidecar


def fetch_missing_fundamentals(
    tickers: list[str],
    earnings_provider: DataProvider,
    conn,
    date: str,
) -> None:
    """Phase 2b (Sprint 3C / Analyse-Pipeline-Umbau, Task 7): holt Fundamentals
    bei Finnhub NACH fuer Ticker, die in Phase 1 einen Cache-Miss hatten, und
    schreibt sie in fundamentals_cache. Prueft den Cache selbst -- statt eine
    bereits als "miss" markierte Liste zu erwarten -- so bleibt die Funktion
    unabhaengig vom Aufrufer testbar und ist ein no-op fuer bereits gecachte
    Ticker, egal wie oft sie aufgerufen wird.

    R16: wird in DIESER Task bewusst NICHT verdrahtet -- main.py ruft sie noch
    nicht auf, das macht Task 10. Bis dahin bleibt jeder Cache-Miss aus Phase 1
    unbeantwortet (R14).

    Robust: ein API-Fehler bei einem Ticker ueberspringt NUR diesen (WARNING),
    der Lauf laeuft fuer die uebrigen Ticker weiter.

    R15: holt bewusst NUR get_fundamentals() -- get_earnings_calendar() gehoert
    in den Wochenjob (Spec 18.1c), nicht in diesen taeglichen Nachlade-Pfad.
    get_fundamentals() liefert deshalb nie ein earnings_next_date. Da
    save_fundamentals_cache() ein INSERT OR REPLACE der GANZEN Zeile ist,
    wuerde ein blindes Schreiben von `raw` ein dort bereits vom Wochenjob
    eingetragenes Datum loeschen, sobald IRGENDEIN anderes Feld (z.B.
    pe_ratio) seine eigene 7-Tage-TTL ueberschreitet -- zwei unabhaengige
    Ablauf-Rhythmen teilen sich einen Voll-Zeilen-Schreibpfad. Deshalb wird
    ein bereits vorhandenes earnings_next_date unten TTL-los nachgelesen und
    in `raw` uebernommen, bevor geschrieben wird."""
    for t in tickers:
        if db.get_cached_fundamentals(conn, t, today=date) is not None:
            continue
        try:
            raw = earnings_provider.get_fundamentals(t)
        except Exception as e:
            log.warning(f"{t}: fundamentals raised (Phase 2b): {e}")
            continue
        if not isinstance(raw, dict) or not raw:
            continue
        if not raw.get("earnings_next_date"):
            # get_cached_fundamentals() ist TTL-gefiltert und wuerde hier genau
            # in dem Fall None liefern, den wir auffangen muessen (die
            # 7-Tage-Fundamentals-TTL ist abgelaufen, aber ein frueher vom
            # Wochenjob gesetztes Datum soll trotzdem ueberleben) -- deshalb
            # direkt gegen die Tabelle, ohne TTL-Cutoff.
            existing = conn.execute(
                "SELECT earnings_next_date FROM fundamentals_cache WHERE ticker = ?",
                (t,),
            ).fetchone()
            if existing is not None and existing["earnings_next_date"]:
                raw["earnings_next_date"] = existing["earnings_next_date"]
        db.save_fundamentals_cache(conn, t, raw, fetched_date=date)
        _sector_id = db.resolve_sector_id(conn, raw.get("sector"))
        if _sector_id is not None:
            db.upsert_ticker_sector(conn, t, _sector_id, source="finnhub")
