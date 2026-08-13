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
from src import db
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


def _live_price(price_provider, ticker: str, df) -> float:
    """Aktueller Kurs fuer die Entscheidung. Faellt auf den letzten finalen Close
    zurueck, wenn der Live-Abruf nichts liefert -- ein alter Kurs ist besser als
    gar keine Analyse, und der Ticker wird dadurch nicht uebersprungen."""
    try:
        live = price_provider.get_premarket_price(ticker)
    except Exception as e:
        log.warning(f"{ticker}: Live-Kurs nicht abrufbar: {e}")
        live = None
    if live is not None:
        return float(live)
    log.warning(f"{ticker}: kein Live-Kurs, nutze letzten finalen Close")
    return float(df["Close"].iloc[-1])


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
) -> dict | None:
    """Runs the full Phase-1 pipeline for one ticker: ensures today's bar exists,
    computes indicators from the last 220 DB days, and fetches fundamentals/earnings
    (cache-first). Returns the TickerData dict, or None (with a skipped_tickers row)
    if there's insufficient or low-quality data."""
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

    # Indicators (computed from DB data — df has capitalized column names)
    pc = compute_price_changes(df)
    td: dict[str, Any] = {
        "ticker": ticker,
        # Entscheidungskurs kommt LIVE, nicht aus price_history: die Historie
        # enthaelt seit dem Preismodell-Umbau nur noch finale Tagesbars und endet
        # damit bei D-1. Ohne diesen Abruf analysierte die Pipeline auf dem
        # Schluss von gestern.
        "price": _live_price(price_provider, ticker, df),
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
    # erst Sprint 3D). Nur fuer die Persistierung weiter unten zusammengefuehrt.
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

    # Fundamentals: cache-first
    cached_fund = db.get_cached_fundamentals(conn, ticker, today=date)
    if cached_fund is not None:
        fundamentals = cached_fund
    else:
        try:
            _raw_fund = earnings_provider.get_fundamentals(ticker)
            fundamentals = _raw_fund if isinstance(_raw_fund, dict) else {}
        except Exception as e:
            log.warning(f"{ticker}: fundamentals raised: {e}")
            fundamentals = {}
        if fundamentals:
            db.save_fundamentals_cache(conn, ticker, fundamentals, fetched_date=date)

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
    _sector_id = db.resolve_sector_id(conn, fundamentals.get("sector"))
    if _sector_id is not None:
        db.upsert_ticker_sector(conn, ticker, _sector_id, source="finnhub")

    # Earnings
    try:
        earnings = earnings_provider.get_earnings_calendar(ticker) or {}
    except Exception as e:
        log.warning(f"{ticker}: earnings raised: {e}")
        earnings = {}
    td["earnings_in_days"]  = earnings.get("days_to_next")
    td["earnings_beat_pct"] = earnings.get("last_beat_pct")

    td["data_quality"] = _classify_data_quality(td)
    if td["data_quality"] == "low":
        _skip(
            conn, ticker=ticker, date=date, run_type=run_type,
            reason="data_quality=low: critical indicators missing",
        )
        return None

    _persist_indicators(conn, ticker, date, {**td, **extra_indicators})
    return td


def collect(
    tickers: list[str],
    price_provider: DataProvider,
    earnings_provider: DataProvider,
    conn,
    date: str,
    run_type: str,
) -> tuple[list[dict], int]:
    """Run Phase 1 over the MVP universe. Returns (ticker_data_list, skipped_count).

    Tickers are processed sequentially. After every BATCH_PAUSE_EVERY tickers
    we sleep config.CAPITAL_COM_BATCH_PAUSE seconds to respect Capital.com rate limits.
    """
    results: list[dict] = []
    skipped = 0
    for i, t in enumerate(tickers):
        # Sprint 3B / B.7: dauerhaft datenlose Ticker kosten keine API-Calls mehr,
        # bis ihr retry_after-Datum erreicht ist.
        if db.is_ticker_inactive(conn, t, today=date):
            status = db.get_ticker_status(conn, t)
            log.info(
                f"{t}: inaktiv nach {status['skip_count']} Skips — uebersprungen, "
                f"Retry ab {status['retry_after']}"
            )
            skipped += 1
            continue

        td = _process_ticker(
            ticker=t,
            price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn,
            date=date,
            run_type=run_type,
        )
        if td is None:
            skipped += 1
        else:
            # Erfolgreicher Abruf heilt den Zaehler — sonst liefe ein Ticker durch
            # verstreute Einzelausfaelle ueber Monate in die Deaktivierung.
            db.reactivate_ticker(conn, t)
            results.append(td)

        if (i + 1) % BATCH_PAUSE_EVERY == 0 and (i + 1) < len(tickers):
            log.info(
                f"Batch pause: processed {i + 1}/{len(tickers)} tickers, "
                f"sleeping {config.CAPITAL_COM_BATCH_PAUSE}s"
            )
            time.sleep(config.CAPITAL_COM_BATCH_PAUSE)

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
    return results, skipped
