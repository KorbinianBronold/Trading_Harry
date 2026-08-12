from src.technical_signal import TechnicalSignal, compute


def _td(**overrides) -> dict:
    """Neutraler Ausgangs-Snapshot; jeder Test setzt nur, was er braucht."""
    base = {
        "rsi_14": 50.0, "rsi_trend": "neutral",
        "macd_line": 0.0, "macd_signal_line": 0.0,
        "above_sma50": 0.0, "above_sma200": 0.0,
        "adx_14": 22.0,
    }
    base.update(overrides)
    return base


def _bullish(**overrides) -> dict:
    bullish_dict = {
        "rsi_14": 60.0, "rsi_trend": "rising",
        "macd_line": 1.0, "macd_signal_line": 0.5,
        "above_sma50": 2.0, "above_sma200": 5.0,
    }
    bullish_dict.update(overrides)
    return _td(**bullish_dict)


def _bearish(**overrides) -> dict:
    bearish_dict = {
        "rsi_14": 40.0, "rsi_trend": "falling",
        "macd_line": -1.0, "macd_signal_line": -0.5,
        "above_sma50": -2.0, "above_sma200": -5.0,
    }
    bearish_dict.update(overrides)
    return _td(**bearish_dict)


def test_all_three_agree_long():
    sig = compute(_bullish())
    assert sig.direction == "long"
    assert sig.agreement == 3


def test_all_three_agree_short():
    sig = compute(_bearish())
    assert sig.direction == "short"
    assert sig.agreement == 3


def test_majority_of_two_still_gives_a_direction():
    """RSI und MACD bullish, SMA-Trend neutral -> Mehrheit traegt."""
    sig = compute(_bullish(above_sma50=0.0, above_sma200=-1.0))
    assert sig.direction == "long"
    assert sig.agreement == 2


def test_no_majority_is_neutral():
    sig = compute(_td())
    assert sig.direction == "neutral"
    assert sig.strength == 0


def test_strong_adx_raises_strength_by_one():
    weak = compute(_bullish(adx_14=22.0))
    strong = compute(_bullish(adx_14=30.0))
    assert strong.adx_band == "strong"
    assert strong.strength == weak.strength + 1
    assert strong.strength <= 4


def test_weak_adx_caps_strength_at_one_without_removing_direction():
    """ADX ist Verstaerkungsfaktor, nicht Filter: die Richtung bleibt."""
    sig = compute(_bullish(adx_14=15.0))
    assert sig.adx_band == "weak"
    assert sig.direction == "long"
    assert sig.strength == 1


def test_missing_sma200_degrades_to_neutral_vote_not_to_failure():
    """Unter 200 Bars ist SMA200 None. Der Teilindikator stimmt dann neutral --
    nicht 'fehlend' -- und die Richtung entsteht aus RSI und MACD."""
    sig = compute(_bullish(above_sma200=None))
    assert sig.direction == "long"
    assert sig.agreement == 2


def test_missing_adx_is_treated_as_normal_band():
    sig = compute(_bullish(adx_14=None))
    assert sig.adx_band == "normal"


def test_completely_empty_snapshot_is_neutral():
    sig = compute({})
    assert sig.direction == "neutral"
    assert sig.agreement == 0
    assert sig.strength == 0


def test_rsi_above_midline_without_a_rising_trend_does_not_vote_long():
    """RSI wird als Momentum gelesen: ueber 50 allein genuegt nicht, der Trend
    muss bestaetigen. Ohne diese Zusicherung koennte aus dem 'und' ein 'oder'
    werden, ohne dass ein Test es merkt."""
    sig = compute(_td(rsi_14=70.0, rsi_trend="falling",
                      macd_line=1.0, macd_signal_line=0.5,
                      above_sma50=2.0, above_sma200=5.0))
    assert sig.agreement == 2   # MACD und SMA, nicht RSI
