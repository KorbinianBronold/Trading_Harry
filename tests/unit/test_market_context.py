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
{"vix_level": 21.5, "sp500_change_pct": -0.71, "advance_decline_ratio": 1.4,
 "market_regime": "neutral",
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
    assert out["sp500_change_pct"] == -0.71
    # seit C.28 nicht mehr erhoben: auch wenn das Modell den Wert schickt, bleibt er None
    assert out["advance_decline_ratio"] is None
    assert out["market_regime"] == "neutral"
    assert out["vix_level"] == 21.5
    assert out["vix_source"] == "claude"
    assert out["sector_rotation_in"] == "Technology"
    assert out["sector_rotation_out"] == "Utilities"
    assert out["macro_summary"] == "Ruhiger Handelstag."
    tracker.add_from_result.assert_called_once()


def test_fetch_market_context_uses_web_search(mocker):
    """Ohne Websuche kann Claude weder VIX-Fallback noch S&P-Tagesaenderung belegen."""
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
    # C.28: vix_source wird persistiert -- "claude" ohne Wert waere eine Falschaussage
    assert out["vix_source"] is None


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
                                   '"sp500_change_pct": "n/a"}')
    assert out["vix_level"] is None
    assert out["sp500_change_pct"] is None


def test_missing_keys_yield_a_complete_dict_of_nones(mocker):
    """Der Aufrufer darf sich auf alle Keys verlassen, auch bei magerer Antwort."""
    out = _fetch(mocker, json_text="{}")
    assert set(out) == {
        "sp500_change_pct", "vix_level", "vix_source", "advance_decline_ratio",
        "market_regime", "sector_rotation_in", "sector_rotation_out", "macro_summary",
    }
    assert out["sp500_change_pct"] is None
    assert out["advance_decline_ratio"] is None
    assert out["macro_summary"] is None


def test_numeric_strings_are_coerced(mocker):
    """Claude liefert Zahlen gelegentlich als String — das ist kein Rateversuch."""
    out = _fetch(mocker, json_text='{"vix_level": "18.4", '
                                   '"sp500_change_pct": "-0.71"}')
    assert out["vix_level"] == 18.4
    assert out["sp500_change_pct"] == -0.71


def test_cost_tracker_runs_before_parsing_can_fail(mocker):
    """Ein unlesbares JSON darf die bereits verbrauchten Tokens nicht verschlucken."""
    from src.market_context import MarketContextError
    tracker = MagicMock()
    with pytest.raises(MarketContextError):
        _fetch(mocker, json_text="Mist", tracker=tracker)
    tracker.add_from_result.assert_called_once()


# ---------- C.28: 16:10 ohne Claude-Call ----------


def test_vix_only_context_needs_no_claude_call(mocker):
    """Der 16:10-Lauf entscheidet ausschliesslich ueber den VIX (check_vix mit
    enforce=True), und der kommt deterministisch von Capital.com. Der zweite
    Claude-Call las historisch niemand -- Regime/Rotation/Makro bleiben None
    und sollen auch nicht als erhoben erscheinen."""
    claude = mocker.patch("src.utils.call_claude")
    from src.market_context import vix_only_context, CONTEXT_KEYS
    out = vix_only_context(date="2026-09-08", price_provider=_vix_provider(19.2))

    claude.assert_not_called()
    assert set(out) == set(CONTEXT_KEYS)
    assert out["vix_level"] == 19.2
    assert out["vix_source"] == "capital.com"
    for key in ("sp500_change_pct", "market_regime", "sector_rotation_in",
                "sector_rotation_out", "macro_summary", "advance_decline_ratio"):
        assert out[key] is None, key


def test_vix_only_context_without_bars_is_all_none(mocker):
    """Kein Bar -> kein VIX, keine Quelle. check_vix filtert bei None nicht --
    ein fehlender Messwert ist kein Grund, alle Signale zu verwerfen."""
    from src.market_context import vix_only_context
    out = vix_only_context(date="2026-09-08", price_provider=_vix_provider(None))
    assert out["vix_level"] is None
    assert out["vix_source"] is None


def test_both_context_builders_share_one_key_set(mocker):
    """Beide Erhebungswege muessen dasselbe Dict liefern -- Aufrufer (Mail,
    save_market_context, Portfolio-Check) unterscheiden nicht, woher es kam."""
    from src.market_context import vix_only_context
    claude_out = _fetch(mocker)
    det_out = vix_only_context(date="2026-07-27", price_provider=None)
    assert set(claude_out) == set(det_out)


# ---------- Vertragstest: prompts/market_context_v1.txt ----------


def test_market_context_v1_pins_contract():
    """Seit Regel 10 wird die Datei direkt editiert; hier haengt Code dran:
      * die drei Regime-Strings muessen EXAKT VALID_REGIMES sein
      * die Feldnamen, die fetch_market_context() liest
      * advance_decline_ratio ist seit C.28 gestrichen und darf nicht zurueckkommen
      * die Rotation ist auf die 11 GICS-Sektoren begrenzt
      * Bezugsrahmen je run_type, englische Einzeiler-Makrozeile ohne VIX-Zahl (D2)
      * C.31: risk_off kennt "zyklische Sektoren am Tabellenende" (sonst bleibt ein
        Down-Tag ohne VIX-Spike immer neutral) und die GICS-Zuordnung einzelner
        Aktien (Alphabet = Communication Services, nicht IT)"""
    from pathlib import Path
    from src.market_context import VALID_REGIMES
    text = (Path(__file__).parent.parent.parent / "prompts" / "market_context_v1.txt").read_text()

    for key in ('"sp500_change_pct"', '"vix_level"', '"market_regime"',
                '"sector_rotation_in"', '"sector_rotation_out"', '"macro_summary"'):
        assert key in text, f"{key} fehlt im Prompt"
    for regime in VALID_REGIMES:
        assert f'"{regime}"' in text, f"Regime {regime!r} fehlt im Prompt"
    assert "advance_decline" not in text

    for sector in ("Energy", "Materials", "Industrials", "Consumer Discretionary",
                   "Consumer Staples", "Health Care", "Financials",
                   "Information Technology", "Communication Services",
                   "Utilities", "Real Estate"):
        assert sector in text, f"GICS-Sektor {sector} fehlt"

    assert "pre_market" in text and "trade_proposals" in text   # Bezugsrahmen
    assert "English" in text                                     # D2
    assert "null" in text                                        # lieber null als geraten
    assert "VIX" in text and "macro_summary" in text

    # C.31: der risk_off-Zweig braucht eine Bedingung, die ein Down-Tag ohne
    # VIX-Spike erfuellen kann; und Alphabet darf nicht als IT gebucht werden.
    assert "lagging" in text
    assert "Alphabet" in text and "Communication Services" in text
