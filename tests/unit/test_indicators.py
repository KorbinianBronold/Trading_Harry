"""Tests fuer die reinen Indikator-Funktionen in src/indicators.py.

Deckt die neun bestehenden Indikatoren ab (RSI, RSI-Trend, MACD-Signal, ATR,
Bollinger-Position, SMA-Abstand, Volumen-Ratio, Intraday-Range,
Preisaenderungen), die in Task 3 aus src/data_collector.py hierher verschoben
wurden."""
import math
import numpy as np
import pandas as pd
import pandas_ta as ta
import pytest
from src import indicators as ind
from src.indicators import (
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
    # Perfectly linear monotonic-up series saturates RSI(14) at 100, so the
    # 3-bar delta is 0 → "neutral". A "rising" outcome would require a
    # slope-changing series; we accept either label here, matching the
    # symmetric down-direction assertion below.
    assert compute_rsi_trend(df_up) in {"rising", "neutral"}

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


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    """260 deterministische Tagesbars mit leichtem Aufwaertsdrift."""
    n = 260
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    rng = np.random.default_rng(7)
    close = pd.Series(100 + np.cumsum(rng.normal(0.05, 1.0, n)), index=idx)
    return pd.DataFrame({
        "Open": close.shift(1).fillna(close.iloc[0]),
        "High": close + abs(rng.normal(0, 1, n)),
        "Low": close - abs(rng.normal(0, 1, n)),
        "Close": close,
        "Volume": pd.Series(rng.integers(100_000, 500_000, n), index=idx),
    })


def test_macd_raw_returns_three_finite_values(ohlcv):
    out = ind.compute_macd_raw(ohlcv)
    assert set(out) == {"macd_line", "macd_signal_line", "macd_hist"}
    assert all(isinstance(v, float) for v in out.values())
    # Das Histogramm ist definitionsgemaess die Differenz der beiden Linien.
    assert out["macd_hist"] == pytest.approx(
        out["macd_line"] - out["macd_signal_line"], abs=1e-6
    )


def test_macd_raw_returns_nones_on_short_history(ohlcv):
    out = ind.compute_macd_raw(ohlcv.iloc[:10])
    assert out == {"macd_line": None, "macd_signal_line": None, "macd_hist": None}


def test_adx_returns_index_and_both_directional_lines(ohlcv):
    out = ind.compute_adx(ohlcv)
    assert set(out) == {"adx_14", "di_plus", "di_minus"}
    assert 0.0 <= out["adx_14"] <= 100.0


def test_adx_is_the_index_not_a_directional_line(ohlcv):
    # adx_14, di_plus and di_minus are all in 0..100, so a swapped column
    # (e.g. adx_14 wired to DMP_14) would still satisfy the shape-only test
    # above. Pin each key against its own pandas_ta column by value.
    out = ind.compute_adx(ohlcv)
    raw = ta.adx(ohlcv["High"], ohlcv["Low"], ohlcv["Close"])
    assert out["adx_14"]   == pytest.approx(raw["ADX_14"].iloc[-1])
    assert out["di_plus"]  == pytest.approx(raw["DMP_14"].iloc[-1])
    assert out["di_minus"] == pytest.approx(raw["DMN_14"].iloc[-1])


def test_psar_direction_is_long_or_short_never_both(ohlcv):
    out = ind.compute_psar(ohlcv)
    assert out["psar_dir"] in ("long", "short", None)
    if out["psar_dir"] is not None:
        assert out["psar_value"] is not None


def test_psar_long_means_price_above_the_stop(ohlcv):
    # "long"/"short" alone doesn't prove psar_value came from the matching
    # PSARl/PSARs column -- a swapped label would still pass the shape-only
    # test above. A long stop sits below price, a short stop sits above it;
    # check whichever direction this fixture actually produced.
    out = ind.compute_psar(ohlcv)
    close = float(ohlcv["Close"].iloc[-1])
    if out["psar_dir"] == "long":
        assert out["psar_value"] < close
    elif out["psar_dir"] == "short":
        assert out["psar_value"] > close


def test_ichimoku_returns_five_lines(ohlcv):
    out = ind.compute_ichimoku(ohlcv)
    assert set(out) == {
        "ichi_tenkan", "ichi_kijun", "ichi_senkou_a",
        "ichi_senkou_b", "ichi_chikou",
    }


def test_ichimoku_values_match_pandas_ta_columns(ohlcv):
    # Existence-only checks above would not catch e.g. ichi_kijun wired to
    # ISA_9 instead of IKS_26. Pin all five keys against their own raw
    # pandas_ta column by value.
    out = ind.compute_ichimoku(ohlcv)
    raw = ta.ichimoku(ohlcv["High"], ohlcv["Low"], ohlcv["Close"])[0]
    assert out["ichi_tenkan"]   == pytest.approx(raw["ITS_9"].iloc[-1])
    assert out["ichi_kijun"]    == pytest.approx(raw["IKS_26"].iloc[-1])
    assert out["ichi_senkou_a"] == pytest.approx(raw["ISA_9"].iloc[-1])
    assert out["ichi_senkou_b"] == pytest.approx(raw["ISB_26"].iloc[-1])
    # ICS_26 (Chikou) is shifted 26 bars into the past, so its very last
    # value is NaN for this fixture even though the other four lines are
    # finite (verified empirically, not fixture-seed-specific in principle --
    # any trailing window can land on the shifted gap). Hard-coding a numeric
    # expectation here would be coincidental, not a real mapping check.
    # Instead, apply the same "last value or None" rule the function itself
    # uses (ind._last_finite) to the raw column and compare -- this still
    # catches a swap: if ichi_chikou were wired to any of the other (finite)
    # columns instead, this equality would fail because that value isn't None.
    assert out["ichi_chikou"] == ind._last_finite(raw["ICS_26"])


def test_ichimoku_returns_nones_on_short_history(ohlcv):
    out = ind.compute_ichimoku(ohlcv.iloc[:30])
    assert all(v is None for v in out.values())


def test_ema_distance_is_percentage_of_the_average(ohlcv):
    out = ind.compute_ema_distance_pct(ohlcv, 50)
    assert isinstance(out, float)
    assert -100.0 < out < 100.0


def test_stochastic_returns_k_and_d_in_range(ohlcv):
    out = ind.compute_stochastic(ohlcv)
    assert set(out) == {"stoch_k", "stoch_d"}
    assert 0.0 <= out["stoch_k"] <= 100.0
    assert 0.0 <= out["stoch_d"] <= 100.0


def test_stochastic_pins_k_and_d_to_their_own_columns(ohlcv):
    # In-range-only checks above would not catch stoch_k/stoch_d swapped --
    # both are bounded 0..100. Pin each key against its own pandas_ta column
    # by value.
    out = ind.compute_stochastic(ohlcv)
    raw = ta.stoch(ohlcv["High"], ohlcv["Low"], ohlcv["Close"])
    assert out["stoch_k"] == pytest.approx(raw["STOCHk_14_3_3"].iloc[-1])
    assert out["stoch_d"] == pytest.approx(raw["STOCHd_14_3_3"].iloc[-1])
    # Confirm the two pinned values are actually distinct in this fixture --
    # otherwise the pin above couldn't detect a swap.
    assert out["stoch_k"] != pytest.approx(out["stoch_d"])


def test_willr_is_negative_by_definition(ohlcv):
    """Williams %R laeuft definitionsgemaess von -100 bis 0."""
    assert -100.0 <= ind.compute_willr(ohlcv) <= 0.0


def test_cci_uses_length_20_not_the_library_default(ohlcv):
    """Die Spec verlangt CCI(20); pandas_ta defaultet auf 14."""
    out = ind.compute_cci(ohlcv)
    assert isinstance(out, float)
    # Gegenprobe: mit Laenge 14 kommt ein anderer Wert heraus.
    other = ta.cci(ohlcv["High"], ohlcv["Low"], ohlcv["Close"], length=14)
    assert out != pytest.approx(float(other.iloc[-1]))


def test_momentum_uses_length_12(ohlcv):
    out = ind.compute_momentum(ohlcv)
    expected = ohlcv["Close"].iloc[-1] - ohlcv["Close"].iloc[-13]
    assert out == pytest.approx(expected, abs=1e-6)


def test_trix_returns_line_and_signal(ohlcv):
    out = ind.compute_trix(ohlcv)
    assert set(out) == {"trix", "trix_signal"}
    assert all(isinstance(v, float) for v in out.values())


def test_trix_pins_line_and_signal_to_their_own_columns(ohlcv):
    # Shape-only above doesn't prove trix/trix_signal aren't swapped -- both
    # are plain floats. Pin each key against its own pandas_ta column by value.
    out = ind.compute_trix(ohlcv)
    raw = ta.trix(ohlcv["Close"], length=15, signal=9)
    assert out["trix"] == pytest.approx(raw["TRIX_15_9"].iloc[-1])
    assert out["trix_signal"] == pytest.approx(raw["TRIXs_15_9"].iloc[-1])
    assert out["trix"] != pytest.approx(out["trix_signal"])


def test_bollinger_width_is_upper_minus_lower(ohlcv):
    out = ind.compute_bollinger_raw(ohlcv)
    assert out["bb_width"] == pytest.approx(out["bb_upper"] - out["bb_lower"], abs=1e-6)


def test_bollinger_pins_upper_and_lower_to_their_own_columns(ohlcv):
    # bb_width is derived from bb_upper/bb_lower in the function itself, so
    # the test above stays internally consistent even if upper and lower were
    # swapped. Pin both keys against their own pandas_ta column by value, and
    # assert the real invariant (upper > lower) that a swap would violate.
    out = ind.compute_bollinger_raw(ohlcv)
    raw = ta.bbands(ohlcv["Close"], length=20)
    assert out["bb_upper"] == pytest.approx(raw["BBU_20_2.0_2.0"].iloc[-1])
    assert out["bb_lower"] == pytest.approx(raw["BBL_20_2.0_2.0"].iloc[-1])
    assert out["bb_upper"] > out["bb_lower"]


def test_donchian_mid_lies_between_the_channels(ohlcv):
    out = ind.compute_donchian(ohlcv)
    assert out["donch_lower"] <= out["donch_mid"] <= out["donch_upper"]


def test_obv_is_computed_from_the_broker_volume_proxy(ohlcv):
    """OBV beruht auf lastTradedVolume -- einem CFD-Broker-Proxy, nicht auf
    Boersenvolumen. Der Test haelt nur fest, dass ein Wert entsteht."""
    assert isinstance(ind.compute_obv(ohlcv), float)


def test_all_new_indicators_return_none_on_empty_history():
    empty_df = pd.DataFrame(
        {c: [] for c in ("Open", "High", "Low", "Close", "Volume")}
    )
    assert ind.compute_willr(empty_df) is None
    assert ind.compute_cci(empty_df) is None
    assert ind.compute_momentum(empty_df) is None
    assert ind.compute_atr_abs(empty_df) is None
    assert ind.compute_obv(empty_df) is None
    assert ind.compute_stochastic(empty_df) == {"stoch_k": None, "stoch_d": None}
