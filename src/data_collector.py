"""Phase 1: Data collection + indicator math.

Indicator helpers are pure functions over a pandas OHLCV DataFrame and are
tested in isolation. The collect()/_process_ticker() functions live in this
same module (added in Tasks 4 and 5) and wire these helpers up with the
DataProvider interface and db.py.
"""
import logging
import math
import time
from typing import Any

import pandas as pd
import pandas_ta as ta

log = logging.getLogger("shares_future.data_collector")

MIN_BARS_RSI = 20
MIN_BARS_ATR = 20
MIN_BARS_BB = 25
MIN_BARS_VOL = 25
MIN_BARS_INTRADAY = 5
MIN_BARS_MACD = 35


def _last_finite(series: pd.Series) -> float | None:
    if series is None or len(series) == 0:
        return None
    val = series.iloc[-1]
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return float(val)


def compute_rsi_14(df: pd.DataFrame) -> float | None:
    if len(df) < MIN_BARS_RSI:
        return None
    rsi = ta.rsi(df["Close"], length=14)
    return _last_finite(rsi)


def compute_rsi_trend(df: pd.DataFrame) -> str:
    """rising | falling | neutral based on last vs. 3-bar-ago RSI."""
    if len(df) < MIN_BARS_RSI + 3:
        return "neutral"
    rsi = ta.rsi(df["Close"], length=14)
    if rsi is None or len(rsi) < 4:
        return "neutral"
    last, prev = rsi.iloc[-1], rsi.iloc[-4]
    if pd.isna(last) or pd.isna(prev):
        return "neutral"
    if last - prev > 2:
        return "rising"
    if last - prev < -2:
        return "falling"
    return "neutral"


def compute_macd_signal(df: pd.DataFrame) -> str:
    """bullish_cross if MACD crossed above signal in the last 2 bars,
    bearish_cross if crossed below, else neutral."""
    if len(df) < MIN_BARS_MACD:
        return "neutral"
    macd = ta.macd(df["Close"])
    if macd is None or macd.empty:
        return "neutral"
    macd_line = macd.iloc[:, 0]
    signal_line = macd.iloc[:, 2]
    if len(macd_line) < 3 or len(signal_line) < 3:
        return "neutral"
    diff_now = macd_line.iloc[-1] - signal_line.iloc[-1]
    diff_prev = macd_line.iloc[-2] - signal_line.iloc[-2]
    if pd.isna(diff_now) or pd.isna(diff_prev):
        return "neutral"
    if diff_prev < 0 and diff_now >= 0:
        return "bullish_cross"
    if diff_prev > 0 and diff_now <= 0:
        return "bearish_cross"
    return "neutral"


def compute_atr_pct(df: pd.DataFrame) -> float | None:
    if len(df) < MIN_BARS_ATR:
        return None
    atr = ta.atr(df["High"], df["Low"], df["Close"], length=14)
    last = _last_finite(atr)
    if last is None:
        return None
    close = _last_finite(df["Close"])
    if not close:
        return None
    return round(last / close * 100, 3)


def compute_bb_position(df: pd.DataFrame) -> float | None:
    if len(df) < MIN_BARS_BB:
        return None
    bb = ta.bbands(df["Close"], length=20)
    if bb is None or bb.empty:
        return None
    lower = bb.iloc[-1, 0]
    upper = bb.iloc[-1, 2]
    close = df["Close"].iloc[-1]
    if pd.isna(lower) or pd.isna(upper) or upper == lower:
        return None
    pos = (close - lower) / (upper - lower)
    return round(max(0.0, min(1.0, float(pos))), 3)


def compute_sma_distance_pct(df: pd.DataFrame, length: int) -> float | None:
    if len(df) < length:
        return None
    sma = ta.sma(df["Close"], length=length)
    last = _last_finite(sma)
    if last is None:
        return None
    close = _last_finite(df["Close"])
    if not close:
        return None
    return round((close - last) / last * 100, 3)


def compute_volume_ratio(df: pd.DataFrame) -> float | None:
    """Avg volume last 5 bars / avg volume last 20 bars."""
    if len(df) < MIN_BARS_VOL:
        return None
    avg_5 = df["Volume"].iloc[-5:].mean()
    avg_20 = df["Volume"].iloc[-20:].mean()
    if avg_20 == 0 or pd.isna(avg_5) or pd.isna(avg_20):
        return None
    return round(float(avg_5 / avg_20), 3)


def compute_intraday_range_pct(df: pd.DataFrame) -> float | None:
    """Mean of (High-Low)/Close*100 over last 5 trading days. Source for the
    CFD-Kurzfrist intraday-range guardrail (spec §6)."""
    if len(df) < MIN_BARS_INTRADAY:
        return None
    tail = df.iloc[-MIN_BARS_INTRADAY:]
    ratios = (tail["High"] - tail["Low"]) / tail["Close"] * 100
    val = ratios.mean()
    if pd.isna(val):
        return None
    return round(float(val), 3)


def compute_price_changes(df: pd.DataFrame) -> dict[str, float | None]:
    """Percentage changes vs. close N bars ago. Approximations:
       1d=1, 5d=5, 1m=21, 3m=63 trading days."""
    close = df["Close"]
    last = close.iloc[-1]

    def pct(offset: int) -> float | None:
        if len(close) <= offset:
            return None
        prev = close.iloc[-1 - offset]
        if prev == 0 or pd.isna(prev):
            return None
        return round(float((last - prev) / prev * 100), 3)

    return {
        "price_change_1d": pct(1),
        "price_change_5d": pct(5),
        "price_change_1m": pct(21),
        "price_change_3m": pct(63),
    }


from src.providers.base import DataProvider
from src import db
import config

BATCH_PAUSE_EVERY = 30  # spec §"Rate Limiting yfinance"


def _classify_data_quality(td: dict) -> str:
    required   = ("rsi_14", "atr_pct")
    peripheral = ("pe_ratio", "market_cap_b", "sector", "above_sma200")
    if any(td.get(k) is None for k in required):
        return "low"
    missing_peripheral = sum(1 for k in peripheral if td.get(k) is None)
    return "medium" if missing_peripheral >= 1 else "high"


def _ensure_today_bar(
    ticker: str,
    price_provider: DataProvider,
    conn,
    date: str,
) -> None:
    """Append today's bar to price_history via INSERT OR IGNORE.

    Tries single-bar fetch (get_ohlc_after) first; falls back to full
    history fetch for fresh installs without historical_loader data."""
    existing = conn.execute(
        "SELECT 1 FROM price_history WHERE ticker=? AND date=?",
        (ticker, date),
    ).fetchone()
    if existing:
        return

    df: pd.DataFrame | None = None
    try:
        _ohlc = price_provider.get_ohlc_after(ticker, date, date)
        df = _ohlc if isinstance(_ohlc, pd.DataFrame) else None
    except Exception as e:
        log.warning(f"{ticker}: single-bar fetch failed: {e}")

    if df is None or df.empty:
        try:
            _hist = price_provider.get_price_history(ticker, days=200)
            df = _hist if isinstance(_hist, pd.DataFrame) else None
        except Exception as e:
            log.warning(f"{ticker}: full-history fallback failed: {e}")
            return

    if df is None or df.empty:
        return

    _raw_source = getattr(price_provider, "_source_name", None)
    source = _raw_source if isinstance(_raw_source, str) else "yfinance"
    for ts, row in df.iterrows():
        d = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        if d > date:
            continue
        db.insert_price_bar_if_missing(
            conn, ticker=ticker, date=d,
            open_=float(row.get("Open", 0)),
            high=float(row.get("High", 0)),
            low=float(row.get("Low", 0)),
            close=float(row.get("Close", 0)),
            volume=int(row.get("Volume", 0) or 0),
            source=source,
        )
    conn.commit()


def _persist_indicators(conn, ticker: str, date: str, td: dict) -> None:
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
    })


def _process_ticker(
    ticker: str,
    price_provider: DataProvider,
    earnings_provider: DataProvider,
    conn,
    date: str,
    run_type: str,
) -> dict | None:
    # Step 1: Ensure today's bar is in DB
    _ensure_today_bar(ticker, price_provider, conn, date)

    # Step 2: Load last 200 days from DB for indicator calculation
    df = db.load_price_history_from_db(conn, ticker, as_of_date=date, limit=200)

    if df is None or len(df) < MIN_BARS_RSI:
        rows = 0 if df is None else len(df)
        db.log_skipped_ticker(
            conn, ticker=ticker, date=date, run_type=run_type,
            reason=f"insufficient bars: {rows} < {MIN_BARS_RSI}",
            learnable=False,
        )
        return None

    # Indicators (computed from DB data — df has capitalized column names)
    pc = compute_price_changes(df)
    td: dict[str, Any] = {
        "ticker": ticker,
        "price":  float(df["Close"].iloc[-1]),
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
        db.log_skipped_ticker(
            conn, ticker=ticker, date=date, run_type=run_type,
            reason="data_quality=low: critical indicators missing",
            learnable=False,
        )
        return None

    _persist_indicators(conn, ticker, date, td)
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
    we sleep config.YFINANCE_BATCH_PAUSE seconds to avoid yfinance rate limits.
    """
    results: list[dict] = []
    skipped = 0
    for i, t in enumerate(tickers):
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
            results.append(td)

        if (i + 1) % BATCH_PAUSE_EVERY == 0 and (i + 1) < len(tickers):
            log.info(
                f"Batch pause: processed {i + 1}/{len(tickers)} tickers, "
                f"sleeping {config.YFINANCE_BATCH_PAUSE}s"
            )
            time.sleep(config.YFINANCE_BATCH_PAUSE)

    log.info(f"Phase 1 done: {len(results)} ok, {skipped} skipped")
    return results, skipped
