"""Invarianten der Konfiguration, die sonst niemand prueft."""
import config

# ---------- Produktivuniversum (2026-08-21) ---------------------------------

def test_prod_list_has_the_agreed_size():
    """150 sektor-balancierte Ticker. Die Zahl ist eine Kostenentscheidung:
    142 Ticker massen 3,4712 EUR (C.21) gegen MAX_COST_PER_RUN_EUR = 6,00."""
    assert len(config.SP500_PROD_TICKERS) == 150


def test_prod_list_has_no_duplicates():
    assert len(config.SP500_PROD_TICKERS) == len(set(config.SP500_PROD_TICKERS))


def test_prod_list_contains_every_mvp_ticker():
    """Die MVP-Ticker haben die laengste Historie und duerfen nicht
    herausfallen."""
    assert set(config.SP500_MVP_TICKERS) <= set(config.SP500_PROD_TICKERS)


def test_prod_list_is_a_subset_of_the_verified_pool():
    """Jeder Produktivticker ist per direktem Epic-Abruf gegen Capital.com
    verifiziert -- die Pruefung steckt in SP500_FULL_TICKERS. Ein Ticker
    ausserhalb des Pools waere ungeprueft und koennte mangels Kursen als
    'insufficient bars' durchfallen."""
    assert set(config.SP500_PROD_TICKERS) <= set(config.SP500_FULL_TICKERS)


# ---------- Universum + Kostendeckel (Spec F4/F5/F7) ------------------------

def test_full_sp500_list_has_no_duplicates():
    assert len(config.SP500_FULL_TICKERS) == len(set(config.SP500_FULL_TICKERS))


def test_full_sp500_contains_every_mvp_ticker():
    """Die MVP-Ticker haben Historie und duerfen nicht herausfallen."""
    assert set(config.SP500_MVP_TICKERS) <= set(config.SP500_FULL_TICKERS)


def test_full_sp500_is_no_longer_a_stub():
    """Spec F4: war bis 2026-08-20 ein Alias auf die 20 MVP-Ticker,
    dann 142 handverlesene, seit 2026-08-21 die verifizierte S&P-500-Liste."""
    assert len(config.SP500_FULL_TICKERS) > 400


def test_full_sp500_excludes_tickers_capital_com_does_not_carry():
    """Spec F5: nicht aufloesende Ticker werden weggelassen, nicht 'vorsichts-
    halber' aufgenommen -- sie wuerden als insufficient bars uebersprungen und
    sich ueber TICKER_MAX_SKIPS selbst deaktivieren."""
    # Stichprobe aus den 53, die beim direkten Epic-Abruf durchfielen.
    for t in ("EMR", "DD", "TEL", "TT", "BF-B", "FISV"):
        assert t not in config.SP500_FULL_TICKERS, f"{t} loest bei Capital.com nicht auf"


def test_renamed_fiserv_uses_the_symbol_capital_com_knows():
    """Die CSV fuehrt Fiserv noch als FISV; Capital.com kennt nur FI."""
    assert "FI" in config.SP500_FULL_TICKERS


def test_cost_warn_threshold_stays_below_the_hard_cap():
    assert config.COST_WARN_THRESHOLD_EUR < config.MAX_COST_PER_RUN_EUR
