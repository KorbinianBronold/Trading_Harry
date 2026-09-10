"""Live-Konsistenzpruefung fuer prompts/market_context_v1.txt (C.30).

Die Regime-Klassifikation passiert im Modell, nicht im Code -- ein Unit-Test
kann sie nicht pruefen. Hier laeuft deshalb ein ECHTER Claude-Call gegen den
aktiven Prompt und prueft, ob die Antwort mit ihren eigenen Zahlen und den
Prompt-Regeln zusammenpasst. Kein Golden-Value-Test: der Markt von heute ist
unbekannt, geprueft wird nur die innere Widerspruchsfreiheit.

  * market_regime ist einer der drei erlaubten Strings
  * risk_on verlangt laut Prompt einen positiven S&P-Tag, risk_off einen
    negativen -- die notwendige Bedingung ist mit den mitgelieferten Zahlen
    pruefbar, die hinreichende (VIX-Band ODER Sektorfuehrung) nicht
  * Rotation nur aus den 11 GICS-Sektoren, hoechstens drei je Richtung
  * macro_summary ist eine Zeile

⚠️ Kostenpflichtig und nicht deterministisch: Sonnet 5 plus bis zu fuenf
Websuchen, gemessen ~0,27 EUR pro Aufruf (C.28). Laeuft NUR mit --run-live
(s. tests/conftest.py) und ist bewusst nicht Teil der normalen Suite:

    pytest tests/live -m live_api --run-live -k market_context

price_provider=None: der VIX in der Antwort ist dann Claudes eigener Wert --
genau der, gegen den das Modell sein Regime gebildet hat."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import config

GICS_SECTORS = {
    "Energy", "Materials", "Industrials", "Consumer Discretionary",
    "Consumer Staples", "Health Care", "Financials", "Information Technology",
    "Communication Services", "Utilities", "Real Estate",
}


def _sectors(raw: str | None) -> list[str]:
    return [s.strip() for s in (raw or "").split(",") if s.strip()]


@pytest.mark.live_api
def test_market_regime_is_consistent_with_its_own_numbers(report):
    """Ein echter Call; die Antwort muss zu den Prompt-Regeln passen."""
    if not config.ANTHROPIC_API_KEY:
        pytest.fail("ANTHROPIC_API_KEY fehlt")

    from src.cost_tracker import CostTracker
    from src.market_context import fetch_market_context, VALID_REGIMES

    today = datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat()
    tracker = CostTracker()
    out = fetch_market_context(
        date=today, run_type="pre_market", cost_tracker=tracker, price_provider=None,
    )
    report(
        f"market_context live {today}: regime={out['market_regime']} "
        f"S&P={out['sp500_change_pct']} VIX={out['vix_level']} ({out['vix_source']}) "
        f"in={out['sector_rotation_in']!r} out={out['sector_rotation_out']!r} "
        f"| {tracker.total_eur:.4f} EUR, {tracker.web_search_calls} Websuchen"
    )

    # 1. Regime ist ein gueltiger String -- None hiesse: das Modell hat sich
    #    nicht an die drei Werte gehalten (market_context.py setzt Unbekanntes auf None)
    assert out["market_regime"] in VALID_REGIMES, out["market_regime"]

    # 2. Notwendige Bedingung der Prompt-Regeln: Richtung des S&P-Tags
    spx = out["sp500_change_pct"]
    if spx is not None:
        if out["market_regime"] == "risk_on":
            assert spx > 0, f"risk_on bei S&P {spx:+.2f} % widerspricht dem Prompt"
        if out["market_regime"] == "risk_off":
            assert spx < 0, f"risk_off bei S&P {spx:+.2f} % widerspricht dem Prompt"

    # 3. Rotation: nur GICS-Namen, hoechstens drei je Richtung
    for key in ("sector_rotation_in", "sector_rotation_out"):
        parts = _sectors(out[key])
        assert len(parts) <= 3, f"{key}: {parts}"
        assert set(parts) <= GICS_SECTORS, f"{key}: nicht-GICS in {parts}"

    # 4. Makro-Zeile: eine Zeile, englisch ist nicht pruefbar -- die Zeilenform schon
    if out["macro_summary"]:
        assert "\n" not in out["macro_summary"]

    # 5. A/D wird nicht mehr erhoben -- auch live nie ein Wert
    assert out["advance_decline_ratio"] is None
