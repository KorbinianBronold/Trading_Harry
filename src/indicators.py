"""Technische Indikatoren als reine Funktionen ueber ein OHLCV-DataFrame.

Jede Funktion nimmt einen DataFrame mit den Spalten Open/High/Low/Close/Volume
(gross geschrieben, wie db.load_price_history_from_db ihn liefert) und gibt einen
Skalar oder None zurueck. Kein Provider-, kein DB- und kein Netzzugriff.

REGEL: reicht die Historie fuer einen Indikator nicht, ist das Ergebnis None --
niemals 0. Eine Null waere eine erfundene Messung.
"""
import math

import pandas as pd
import pandas_ta as ta

MIN_BARS_RSI = 20
MIN_BARS_ATR = 20
MIN_BARS_BB = 25
MIN_BARS_VOL = 25
MIN_BARS_INTRADAY = 5
MIN_BARS_MACD = 35
MIN_BARS_ADX = 28
MIN_BARS_ICHIMOKU = 78
MIN_BARS_PSAR = 10
MIN_BARS_STOCH = 20
MIN_BARS_TRIX = 50
MIN_BARS_DONCHIAN = 20
MIN_BARS_WILLR = 20

_CCI_LENGTH, _MOM_LENGTH = 20, 12
_TRIX_LENGTH, _TRIX_SIGNAL = 15, 9

# Spaltennamen von pandas_ta 0.4.71b0, am 2026-08-11 gegen die installierte
# Version verifiziert. Sie enthalten die Parameter im Namen -- aendert sich eine
# Laenge, aendert sich der Spaltenname mit.
_MACD_LINE, _MACD_HIST, _MACD_SIGNAL = "MACD_12_26_9", "MACDh_12_26_9", "MACDs_12_26_9"
_ADX, _DMP, _DMN = "ADX_14", "DMP_14", "DMN_14"
_PSAR_LONG, _PSAR_SHORT = "PSARl_0.02_0.2", "PSARs_0.02_0.2"


def _last_finite(series: pd.Series) -> float | None:
    """Returns the last value of `series` as a float, or None if the series is
    empty or the last value is NaN."""
    if series is None or len(series) == 0:
        return None
    val = series.iloc[-1]
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return float(val)


def compute_rsi_14(df: pd.DataFrame) -> float | None:
    """Returns the latest 14-period RSI, or None if there's not enough history."""
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
    """Returns the latest 14-period ATR as a percentage of closing price, or
    None if there's not enough history."""
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
    """Returns where the close sits within its 20-period Bollinger Bands, as a
    0-1 fraction (0 = lower band, 1 = upper band); None if not enough history."""
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
    """Returns how far the close is above/below its `length`-period SMA, as a
    percentage; None if there's not enough history."""
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


def compute_ema_distance_pct(df: pd.DataFrame, length: int) -> float | None:
    """Abstand des Schlusskurses zum EMA der Laenge `length` in Prozent."""
    if len(df) < length:
        return None
    ema = ta.ema(df["Close"], length=length)
    last = _last_finite(ema)
    close = _last_finite(df["Close"])
    if last is None or not close:
        return None
    return round((close - last) / last * 100, 3)


def compute_macd_raw(df: pd.DataFrame) -> dict[str, float | None]:
    """MACD-Linie, Signallinie und Histogramm als Rohwerte.

    Ergaenzt compute_macd_signal(), das nur die Kreuzung meldet und deshalb an
    den meisten Tagen 'neutral' liefert -- als Dauersignal unbrauchbar. Das
    Vorzeichen des Histogramms traegt dagegen jeden Tag eine Aussage.
    """
    empty = {"macd_line": None, "macd_signal_line": None, "macd_hist": None}
    if len(df) < MIN_BARS_MACD:
        return empty
    macd = ta.macd(df["Close"])
    if macd is None or macd.empty:
        return empty
    return {
        "macd_line":        _last_finite(macd[_MACD_LINE]),
        "macd_signal_line": _last_finite(macd[_MACD_SIGNAL]),
        "macd_hist":        _last_finite(macd[_MACD_HIST]),
    }


def compute_adx(df: pd.DataFrame) -> dict[str, float | None]:
    """ADX(14) als Trendstaerke plus die beiden Richtungslinien DI+ und DI-."""
    empty = {"adx_14": None, "di_plus": None, "di_minus": None}
    if len(df) < MIN_BARS_ADX:
        return empty
    adx = ta.adx(df["High"], df["Low"], df["Close"])
    if adx is None or adx.empty:
        return empty
    return {
        "adx_14":   _last_finite(adx[_ADX]),
        "di_plus":  _last_finite(adx[_DMP]),
        "di_minus": _last_finite(adx[_DMN]),
    }


def compute_psar(df: pd.DataFrame) -> dict[str, float | str | None]:
    """Parabolic SAR: Stopp-Niveau und die Richtung, in der es steht.

    pandas_ta liefert zwei getrennte Spalten -- PSARl traegt Werte im
    Aufwaertstrend, PSARs im Abwaertstrend, die jeweils andere ist NaN. Die
    Richtung ergibt sich daraus, welche der beiden belegt ist.
    """
    empty: dict[str, float | str | None] = {"psar_value": None, "psar_dir": None}
    if len(df) < MIN_BARS_PSAR:
        return empty
    psar = ta.psar(df["High"], df["Low"], df["Close"])
    if psar is None or psar.empty:
        return empty
    long_v = _last_finite(psar[_PSAR_LONG]) if _PSAR_LONG in psar else None
    short_v = _last_finite(psar[_PSAR_SHORT]) if _PSAR_SHORT in psar else None
    if long_v is not None:
        return {"psar_value": long_v, "psar_dir": "long"}
    if short_v is not None:
        return {"psar_value": short_v, "psar_dir": "short"}
    return empty


def compute_ichimoku(df: pd.DataFrame) -> dict[str, float | None]:
    """Die fuenf Ichimoku-Linien.

    ta.ichimoku() gibt ein TUPEL zurueck: (historische Linien, in die Zukunft
    projizierte Spans). Nur der erste Teil ist hier gemeint.

    ichi_chikou ist NICHT pandas_tas Spalte ICS_26: die traegt den heutigen
    Schlusskurs, 26 Bars in die Zukunft projiziert (zur Chart-Darstellung des
    Chikou-Spans) -- fuer die juengsten 26 Zeilen also strukturell NaN, nie
    nur zufaellig leer. Stattdessen der Schlusskurs von vor 26 Bars: der Wert,
    gegen den der Chikou-Span den heutigen Kurs tatsaechlich vergleicht.
    """
    keys = ("ichi_tenkan", "ichi_kijun", "ichi_senkou_a",
            "ichi_senkou_b", "ichi_chikou")
    empty = dict.fromkeys(keys, None)
    if len(df) < MIN_BARS_ICHIMOKU:
        return empty
    result = ta.ichimoku(df["High"], df["Low"], df["Close"])
    hist = result[0] if isinstance(result, tuple) else result
    if hist is None or hist.empty:
        return empty
    chikou_lag = 26
    ichi_chikou = (
        _last_finite(df["Close"].iloc[:-chikou_lag])
        if len(df) > chikou_lag else None
    )
    return {
        "ichi_tenkan":   _last_finite(hist["ITS_9"]),
        "ichi_kijun":    _last_finite(hist["IKS_26"]),
        "ichi_senkou_a": _last_finite(hist["ISA_9"]),
        "ichi_senkou_b": _last_finite(hist["ISB_26"]),
        "ichi_chikou":   ichi_chikou,
    }


def compute_stochastic(df: pd.DataFrame) -> dict[str, float | None]:
    """Stochastik-Oszillator: %K und %D."""
    empty = {"stoch_k": None, "stoch_d": None}
    if len(df) < MIN_BARS_STOCH:
        return empty
    st = ta.stoch(df["High"], df["Low"], df["Close"])
    if st is None or st.empty:
        return empty
    return {
        "stoch_k": _last_finite(st["STOCHk_14_3_3"]),
        "stoch_d": _last_finite(st["STOCHd_14_3_3"]),
    }


def compute_willr(df: pd.DataFrame) -> float | None:
    """Williams %R(14). Laeuft definitionsgemaess von -100 bis 0."""
    if len(df) < MIN_BARS_WILLR:
        return None
    return _last_finite(ta.willr(df["High"], df["Low"], df["Close"]))


def compute_cci(df: pd.DataFrame) -> float | None:
    """CCI mit Laenge 20. pandas_ta defaultet auf 14 -- die Laenge wird
    ausdruecklich uebergeben, weil die Spec 20 verlangt."""
    if len(df) < _CCI_LENGTH:
        return None
    return _last_finite(
        ta.cci(df["High"], df["Low"], df["Close"], length=_CCI_LENGTH)
    )


def compute_momentum(df: pd.DataFrame) -> float | None:
    """Momentum(12): absolute Kursdifferenz zu vor 12 Bars. pandas_ta
    defaultet auf 10."""
    if len(df) <= _MOM_LENGTH:
        return None
    return _last_finite(ta.mom(df["Close"], length=_MOM_LENGTH))


def compute_trix(df: pd.DataFrame) -> dict[str, float | None]:
    """TRIX(15) mit Signallinie(9). pandas_ta defaultet auf 30."""
    empty = {"trix": None, "trix_signal": None}
    if len(df) < MIN_BARS_TRIX:
        return empty
    tr = ta.trix(df["Close"], length=_TRIX_LENGTH, signal=_TRIX_SIGNAL)
    if tr is None or tr.empty:
        return empty
    return {
        "trix":        _last_finite(tr[f"TRIX_{_TRIX_LENGTH}_{_TRIX_SIGNAL}"]),
        "trix_signal": _last_finite(tr[f"TRIXs_{_TRIX_LENGTH}_{_TRIX_SIGNAL}"]),
    }


def compute_bollinger_raw(df: pd.DataFrame) -> dict[str, float | None]:
    """Oberes und unteres Bollinger-Band als Kursniveaus plus deren Abstand.

    Ergaenzt compute_bb_position(), das nur die relative Lage im Band meldet
    und die Bandbreite -- also das Volatilitaetsniveau -- wegwirft.
    """
    empty = {"bb_upper": None, "bb_lower": None, "bb_width": None}
    if len(df) < MIN_BARS_BB:
        return empty
    bb = ta.bbands(df["Close"], length=20)
    if bb is None or bb.empty:
        return empty
    lower, upper = bb.iloc[-1, 0], bb.iloc[-1, 2]
    if pd.isna(lower) or pd.isna(upper):
        return empty
    return {
        "bb_upper": round(float(upper), 4),
        "bb_lower": round(float(lower), 4),
        "bb_width": round(float(upper - lower), 4),
    }


def compute_atr_abs(df: pd.DataFrame) -> float | None:
    """ATR(14) als absoluter Kursbetrag. compute_atr_pct() liefert denselben
    Wert relativ zum Schlusskurs; fuer Abstandsrechnungen wird der absolute
    gebraucht."""
    if len(df) < MIN_BARS_ATR:
        return None
    return _last_finite(ta.atr(df["High"], df["Low"], df["Close"], length=14))


def compute_donchian(df: pd.DataFrame) -> dict[str, float | None]:
    """Donchian-Kanal(20): oberes, mittleres und unteres Band."""
    empty = {"donch_upper": None, "donch_mid": None, "donch_lower": None}
    if len(df) < MIN_BARS_DONCHIAN:
        return empty
    dc = ta.donchian(df["High"], df["Low"])
    if dc is None or dc.empty:
        return empty
    return {
        "donch_lower": _last_finite(dc["DCL_20_20"]),
        "donch_mid":   _last_finite(dc["DCM_20_20"]),
        "donch_upper": _last_finite(dc["DCU_20_20"]),
    }


def compute_obv(df: pd.DataFrame) -> float | None:
    """On-Balance-Volume.

    WARNUNG: beruht auf `lastTradedVolume` von Capital.com -- einem
    CFD-Broker-Proxy, NICHT auf Boersenvolumen. Der Wert beschreibt Capital.coms
    eigenen Handelsfluss. Als Richtungsmass brauchbar, als Niveauaussage nicht.
    """
    if len(df) < MIN_BARS_VOL:
        return None
    return _last_finite(ta.obv(df["Close"], df["Volume"]))
