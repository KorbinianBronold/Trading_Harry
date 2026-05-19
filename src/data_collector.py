"""Phase 1: Data collection + indicator math.

Indicator helpers are pure functions over a pandas OHLCV DataFrame and are
tested in isolation. The collect()/_process_ticker() functions live in this
same module (added in Tasks 4 and 5) and wire these helpers up with the
DataProvider interface and db.py.
"""
import logging
import math
from typing import Any

import pandas as pd
import pandas_ta as ta

log = logging.getLogger("shares_future.data_collector")

MIN_BARS_RSI = 20
MIN_BARS_ATR = 20
MIN_BARS_BB = 25
MIN_BARS_VOL = 25
MIN_BARS_INTRADAY = 5


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
    if len(df) < 35:
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
