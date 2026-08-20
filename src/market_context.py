"""Phase 0b: tagesaktueller Marktkontext.

Ein Claude-Call mit Websuche liefert VIX, Advance/Decline-Ratio, Marktregime und
Sektor-Rotation als strukturiertes JSON. Der VIX wird bevorzugt numerisch von
Capital.com genommen (deterministisch); Claudes Wert dient nur als Rueckfallebene,
falls das Epic keine Bars liefert.

Nicht belegbare Werte bleiben None. Das ist Absicht und kein Mangel: die Zahlen
steuern nachgelagert harte Risikofilter (VIX > 25 nur noch confidence='high',
VIX > 35 keine neuen Longs), und ein geratener Wert waere dort schlimmer als gar
keiner.

Das Modul kennt weder Datenbank noch E-Mail — es beschafft und validiert nur.
Persistiert wird vom Aufrufer (main.py) ueber db.save_market_context().
Eingefuehrt in Sprint 3B / Plan 1 (Spec B.3, Entscheidung D2)."""
import logging
from pathlib import Path

import config
from src.cost_tracker import CostTracker
from src.utils import (call_claude_retry_on_truncation, extract_json_blob,
                       WEB_SEARCH_TOOL)

log = logging.getLogger("shares_future.market_context")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "market_context_v1.txt").read_text()

MODEL = config.CLAUDE_MODEL_SONNET
# ⚠️ 1024 war gegen claude-sonnet-4-6 bemessen (kein Denken ohne explizites
# thinking-Feld). Unter claude-sonnet-5 teilen sich Denk- und Antworttokens die
# Decke; die Antwort ist hier zwar klein, der Denk-Aufschlag ist es nicht.
# Anders als bei trend_analyzer wurde hier KEINE Kappung beobachtet -- der Wert
# steigt trotzdem, weil derselbe Messlauf gezeigt hat, dass ein einmaliges
# Durchlaufen unter adaptivem Denken nichts beweist (Phase 0 lief einmal sauber
# und kappte beim naechsten Lauf). Die Decke kostet nur, was sie nutzt.
MAX_TOKENS = 6144
VALID_REGIMES = {"risk_on", "risk_off", "neutral"}


class MarketContextError(RuntimeError):
    """Der Markt-Kontext-Call lieferte keine parsebare Antwort."""


def _as_float(value) -> float | None:
    """Konvertiert einen Claude-Wert nach float; alles Nicht-Numerische wird None.
    Zahlen als String sind erlaubt — das ist ein Formatdetail, kein Rateversuch."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _vix_from_capital(price_provider, date: str) -> float | None:
    """Liest den letzten VIX-Schlusskurs ueber das Capital.com-Epic. Gibt None
    zurueck, wenn kein Provider uebergeben wurde oder keine Bars ankommen."""
    if price_provider is None:
        return None
    try:
        df = price_provider.get_price_history(config.VIX_TICKER, days=5)
    except Exception as e:
        log.warning(f"VIX-Abruf ueber Capital.com fehlgeschlagen: {e}")
        return None
    if df is None or getattr(df, "empty", True):
        return None
    try:
        return float(df["Close"].iloc[-1])
    except Exception as e:
        log.warning(f"VIX-Bar nicht lesbar: {e}")
        return None


def fetch_market_context(
    date: str,
    run_type: str,
    cost_tracker: CostTracker,
    price_provider=None,
) -> dict:
    """Ermittelt den Marktkontext fuer `date` und gibt ein validiertes Dict zurueck.

    Keys: vix_level, vix_source, advance_decline_ratio, market_regime,
    sector_rotation_in, sector_rotation_out, macro_summary. Alle Keys sind immer
    vorhanden, nicht belegbare Werte sind None. Raises MarketContextError, wenn
    die Antwort nicht als JSON lesbar ist."""
    user_msg = (
        f"Heutiges Datum: {date} (Run: {run_type}).\n"
        "Ermittle den aktuellen US-Marktkontext und antworte mit dem JSON-Objekt "
        "aus deinem System-Prompt."
    )
    # Bucht jeden Versuch selbst -- auch einen verworfenen gekappten. Die Tokens
    # sind verbraucht, egal ob die Antwort lesbar ist.
    result = call_claude_retry_on_truncation(
        model=MODEL, system=SYSTEM_PROMPT, user=user_msg,
        max_tokens=MAX_TOKENS, cost_tracker=cost_tracker, tools=[WEB_SEARCH_TOOL],
    )
    parsed = extract_json_blob(result.text, MarketContextError)

    regime = parsed.get("market_regime")
    if regime not in VALID_REGIMES:
        if regime is not None:
            log.warning(f"unbekanntes market_regime {regime!r} — auf None gesetzt")
        regime = None

    vix_capital = _vix_from_capital(price_provider, date)
    vix_claude = _as_float(parsed.get("vix_level"))
    vix_level = vix_capital if vix_capital is not None else vix_claude
    vix_source = "capital.com" if vix_capital is not None else "claude"

    out = {
        "vix_level":             vix_level,
        "vix_source":            vix_source,
        "advance_decline_ratio": _as_float(parsed.get("advance_decline_ratio")),
        "market_regime":         regime,
        "sector_rotation_in":    parsed.get("sector_rotation_in"),
        "sector_rotation_out":   parsed.get("sector_rotation_out"),
        "macro_summary":         parsed.get("macro_summary"),
    }
    log.info(
        f"Markt-Kontext: VIX={out['vix_level']} ({vix_source}), "
        f"A/D={out['advance_decline_ratio']}, Regime={out['market_regime']}"
    )
    return out
