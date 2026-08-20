"""Invarianten der Konfiguration, die sonst niemand prueft."""
import config

# ---------- Universum + Kostendeckel (Spec F4/F5/F7) ------------------------

def test_full_sp500_list_has_no_duplicates():
    assert len(config.SP500_FULL_TICKERS) == len(set(config.SP500_FULL_TICKERS))


def test_full_sp500_contains_every_mvp_ticker():
    """Die MVP-Ticker haben Historie und duerfen nicht herausfallen."""
    assert set(config.SP500_MVP_TICKERS) <= set(config.SP500_FULL_TICKERS)


def test_full_sp500_is_no_longer_a_stub():
    """Spec F4: war bis 2026-08-20 ein Alias auf die 20 MVP-Ticker."""
    assert len(config.SP500_FULL_TICKERS) > 100


def test_full_sp500_excludes_tickers_capital_com_does_not_carry():
    """Spec F5: nicht aufloesende Ticker werden weggelassen, nicht 'vorsichts-
    halber' aufgenommen -- sie wuerden als insufficient bars uebersprungen und
    sich ueber TICKER_MAX_SKIPS selbst deaktivieren."""
    for t in ("BK", "EA", "EMR", "MMC"):
        assert t not in config.SP500_FULL_TICKERS, f"{t} loest bei Capital.com nicht auf"


def test_cost_warn_threshold_stays_below_the_hard_cap():
    assert config.COST_WARN_THRESHOLD_EUR < config.MAX_COST_PER_RUN_EUR
