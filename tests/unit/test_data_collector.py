import math
import pandas as pd
import pytest
from src.data_collector import (
    compute_rsi_14, compute_rsi_trend, compute_macd_signal,
    compute_atr_pct, compute_bb_position,
    compute_sma_distance_pct, compute_volume_ratio,
    compute_intraday_range_pct, compute_price_changes,
)


def _df_monotonic_up(rows: int = 250) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=rows, freq="B")
    closes = [100 + i * 0.5 for i in range(rows)]
    return pd.DataFrame({
        "Open":   [c - 0.1 for c in closes],
        "High":   [c + 0.5 for c in closes],
        "Low":    [c - 0.5 for c in closes],
        "Close":  closes,
        "Volume": [1_000_000 + i * 1_000 for i in range(rows)],
    }, index=idx)


def _df_oscillating(rows: int = 250, amp: float = 5.0) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=rows, freq="B")
    closes = [100 + amp * math.sin(i / 5) for i in range(rows)]
    return pd.DataFrame({
        "Open":   closes,
        "High":   [c + amp * 0.3 for c in closes],
        "Low":    [c - amp * 0.3 for c in closes],
        "Close":  closes,
        "Volume": [1_000_000] * rows,
    }, index=idx)


def test_compute_rsi_14_on_monotonic_up_is_high():
    df = _df_monotonic_up(60)
    rsi = compute_rsi_14(df)
    assert rsi > 80


def test_compute_rsi_14_returns_none_when_too_short():
    df = _df_monotonic_up(10)
    assert compute_rsi_14(df) is None


def test_compute_rsi_trend_classifies_rising_and_falling():
    df_up = _df_monotonic_up(60)
    assert compute_rsi_trend(df_up) == "rising"

    df_down = _df_monotonic_up(60)
    df_down["Close"] = df_down["Close"].iloc[::-1].reset_index(drop=True).values
    # rebuild with descending close so RSI falls
    df_down.index = pd.date_range("2025-01-01", periods=60, freq="B")
    assert compute_rsi_trend(df_down) in {"falling", "neutral"}


def test_compute_macd_signal_returns_one_of_three_labels():
    df = _df_monotonic_up(60)
    assert compute_macd_signal(df) in {"bullish_cross", "bearish_cross", "neutral"}


def test_compute_atr_pct_is_positive_for_oscillating_series():
    df = _df_oscillating(60)
    atr = compute_atr_pct(df)
    assert atr is not None
    assert 0 < atr < 50


def test_compute_bb_position_in_zero_one_range():
    df = _df_oscillating(60)
    bb = compute_bb_position(df)
    assert bb is None or 0 <= bb <= 1


def test_compute_sma_distance_pct_positive_for_uptrend():
    df = _df_monotonic_up(250)
    dist20 = compute_sma_distance_pct(df, 20)
    dist50 = compute_sma_distance_pct(df, 50)
    dist200 = compute_sma_distance_pct(df, 200)
    assert dist20 > 0
    assert dist50 > 0
    assert dist200 > 0


def test_compute_sma_distance_pct_returns_none_when_too_short():
    df = _df_monotonic_up(50)
    assert compute_sma_distance_pct(df, 200) is None


def test_compute_volume_ratio_returns_value_near_one_for_flat_volume():
    df = _df_oscillating(60)
    v = compute_volume_ratio(df)
    assert v is not None
    assert 0.9 < v < 1.1


def test_compute_intraday_range_pct_mean_last_5_days():
    rows = 10
    idx = pd.date_range("2025-01-01", periods=rows, freq="B")
    df = pd.DataFrame({
        "Open":   [100] * rows,
        "High":   [102] * rows,   # high-low = 2.0
        "Low":    [100] * rows,
        "Close":  [101] * rows,   # range/close = 2/101 ≈ 1.98%
        "Volume": [1_000_000] * rows,
    }, index=idx)
    r = compute_intraday_range_pct(df)
    assert r is not None
    assert 1.95 < r < 2.01


def test_compute_intraday_range_pct_returns_none_when_too_short():
    df = _df_monotonic_up(3)
    assert compute_intraday_range_pct(df) is None


def test_compute_price_changes_returns_dict_with_expected_keys():
    df = _df_monotonic_up(80)
    out = compute_price_changes(df)
    assert set(out.keys()) == {"price_change_1d", "price_change_5d",
                               "price_change_1m", "price_change_3m"}
    # Monotonic up → all positive
    assert all(v is None or v > 0 for v in out.values())
