"""Tests fuer src/market_context.py — Phase 0b, der Markt-Kontext-Call
(Sprint 3B / Plan 1, Task 10, Entscheidung D2). Komplett offline: call_claude
und der Capital.com-Provider sind durchgehend gemockt."""
from unittest.mock import MagicMock

import pandas as pd
import pytest


def _claude_result(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    return r


_GOOD_JSON = """
{"vix_level": 21.5, "advance_decline_ratio": 1.4, "market_regime": "neutral",
 "sector_rotation_in": "Technology", "sector_rotation_out": "Utilities",
 "macro_summary": "Ruhiger Handelstag."}
"""


def _vix_provider(close: float | None) -> MagicMock:
    p = MagicMock()
    if close is None:
        p.get_price_history.return_value = None
    else:
        p.get_price_history.return_value = pd.DataFrame(
            {"Open": [close], "High": [close], "Low": [close],
             "Close": [close], "Volume": [0]},
            index=pd.to_datetime(["2026-07-27"]),
        )
    return p


def _fetch(mocker, json_text: str = _GOOD_JSON, provider=None, tracker=None):
    mocker.patch("src.utils.call_claude",
                 return_value=_claude_result(json_text))
    from src.market_context import fetch_market_context
    return fetch_market_context(
        date="2026-07-27", run_type="pre_market",
        cost_tracker=tracker or MagicMock(), price_provider=provider,
    )


def test_fetch_market_context_parses_claude_json(mocker):
    tracker = MagicMock()
    out = _fetch(mocker, tracker=tracker)
    assert out["advance_decline_ratio"] == 1.4
    assert out["market_regime"] == "neutral"
    assert out["vix_level"] == 21.5
    assert out["vix_source"] == "claude"
    assert out["sector_rotation_in"] == "Technology"
    assert out["sector_rotation_out"] == "Utilities"
    assert out["macro_summary"] == "Ruhiger Handelstag."
    tracker.add_from_result.assert_called_once()


def test_fetch_market_context_uses_web_search(mocker):
    """Ohne Websuche kann Claude weder VIX noch A/D-Ratio belegen."""
    from src.utils import WEB_SEARCH_TOOL
    patched = mocker.patch("src.utils.call_claude",
                           return_value=_claude_result(_GOOD_JSON))
    from src.market_context import fetch_market_context
    fetch_market_context(date="2026-07-27", run_type="pre_market",
                         cost_tracker=MagicMock(), price_provider=None)
    assert patched.call_args.kwargs["tools"] == [WEB_SEARCH_TOOL]


def test_capital_vix_overrides_claude_value(mocker):
    """Der numerische Capital.com-Wert schlaegt Claudes recherchierte Zahl."""
    out = _fetch(mocker, provider=_vix_provider(19.2))
    assert out["vix_level"] == 19.2
    assert out["vix_source"] == "capital.com"


def test_claude_vix_used_when_capital_returns_nothing(mocker):
    out = _fetch(mocker, provider=_vix_provider(None))
    assert out["vix_level"] == 21.5
    assert out["vix_source"] == "claude"


def test_claude_vix_used_when_capital_raises(mocker):
    provider = MagicMock()
    provider.get_price_history.side_effect = RuntimeError("Capital.com 500")
    out = _fetch(mocker, provider=provider)
    assert out["vix_level"] == 21.5
    assert out["vix_source"] == "claude"


def test_vix_stays_none_when_neither_source_delivers(mocker):
    out = _fetch(mocker, json_text='{"vix_level": null}',
                 provider=_vix_provider(None))
    assert out["vix_level"] is None


def test_invalid_market_regime_falls_back_to_none(mocker):
    out = _fetch(mocker, json_text='{"market_regime": "euphorisch"}')
    assert out["market_regime"] is None


@pytest.mark.parametrize("regime", ["risk_on", "risk_off", "neutral"])
def test_all_valid_regimes_pass_through(mocker, regime):
    out = _fetch(mocker, json_text='{"market_regime": "%s"}' % regime)
    assert out["market_regime"] == regime


def test_unparseable_response_raises(mocker):
    from src.market_context import MarketContextError
    with pytest.raises(MarketContextError):
        _fetch(mocker, json_text="kein JSON hier")


def test_non_numeric_values_become_none(mocker):
    """Lieber None als eine geratene Zahl — diese Werte steuern harte Filter."""
    out = _fetch(mocker, json_text='{"vix_level": "keine Ahnung", '
                                   '"advance_decline_ratio": null}')
    assert out["vix_level"] is None
    assert out["advance_decline_ratio"] is None


def test_missing_keys_yield_a_complete_dict_of_nones(mocker):
    """Der Aufrufer darf sich auf alle Keys verlassen, auch bei magerer Antwort."""
    out = _fetch(mocker, json_text="{}")
    assert set(out) == {
        "vix_level", "vix_source", "advance_decline_ratio", "market_regime",
        "sector_rotation_in", "sector_rotation_out", "macro_summary",
    }
    assert out["advance_decline_ratio"] is None
    assert out["macro_summary"] is None


def test_numeric_strings_are_coerced(mocker):
    """Claude liefert Zahlen gelegentlich als String — das ist kein Rateversuch."""
    out = _fetch(mocker, json_text='{"vix_level": "18.4", '
                                   '"advance_decline_ratio": "1.35"}')
    assert out["vix_level"] == 18.4
    assert out["advance_decline_ratio"] == 1.35


def test_cost_tracker_runs_before_parsing_can_fail(mocker):
    """Ein unlesbares JSON darf die bereits verbrauchten Tokens nicht verschlucken."""
    from src.market_context import MarketContextError
    tracker = MagicMock()
    with pytest.raises(MarketContextError):
        _fetch(mocker, json_text="Mist", tracker=tracker)
    tracker.add_from_result.assert_called_once()
