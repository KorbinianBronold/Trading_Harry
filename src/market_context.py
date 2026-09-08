"""Phase 0b: tagesaktueller Marktkontext.

Ein Claude-Call mit Websuche liefert S&P-500-Tagesaenderung, Marktregime,
Sektor-Rotation und einen Makro-Einzeiler als strukturiertes JSON. Der VIX wird
bevorzugt numerisch von Capital.com genommen (deterministisch); Claudes Wert
dient nur als Rueckfallebene, falls das Epic keine Bars liefert.

Seit C.28 (2026-09-08) zwei Erhebungswege mit identischem Schluesselsatz:
  * fetch_market_context() -- der Claude-Call, nur im Morgenlauf (pre_market)
  * vix_only_context()     -- deterministisch, fuer den 16:10-Lauf: dort
    entscheidet ausschliesslich der VIX (check_vix mit enforce=True), der
    zweite Claude-Call speiste ausser einer DB-Zeile nichts
Die Advance/Decline-Ratio wird nicht mehr erhoben (P2.11 Befund 2, entschieden
in C.28): per Websuche gab es nie eine belegbare S&P-500-spezifische Quelle, der
Wert war seit dem 13.08. in jedem Lauf NULL und hatte keinen Abnehmer ausser
einer Mail-Kontextzeile. Der Schluessel bleibt (None), Schema und Mail bleiben stabil.

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

# Alle Schluessel, auf die sich Aufrufer verlassen duerfen -- in beiden
# Erhebungswegen identisch. Wer hier etwas ergaenzt, ergaenzt es fuer beide.
CONTEXT_KEYS = (
    "sp500_change_pct", "vix_level", "vix_source", "advance_decline_ratio",
    "market_regime", "sector_rotation_in", "sector_rotation_out", "macro_summary",
)


def _empty_context() -> dict:
    """Vollstaendiges Kontext-Dict, alle Werte None."""
    return {k: None for k in CONTEXT_KEYS}


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

    Keys: CONTEXT_KEYS. Alle Keys sind immer vorhanden, nicht belegbare Werte
    sind None; advance_decline_ratio ist seit C.28 immer None (nicht mehr
    erhoben). Raises MarketContextError, wenn die Antwort nicht als JSON lesbar
    ist."""
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
    # vix_source wird seit C.28 persistiert -- "claude" ohne Wert waere eine
    # Falschaussage in der Tabelle, deshalb None, wenn keine Quelle lieferte.
    if vix_capital is not None:
        vix_source = "capital.com"
    elif vix_claude is not None:
        vix_source = "claude"
    else:
        vix_source = None

    out = {
        **_empty_context(),          # setzt u.a. advance_decline_ratio = None (C.28)
        "sp500_change_pct":      _as_float(parsed.get("sp500_change_pct")),
        "vix_level":             vix_level,
        "vix_source":            vix_source,
        "market_regime":         regime,
        "sector_rotation_in":    parsed.get("sector_rotation_in"),
        "sector_rotation_out":   parsed.get("sector_rotation_out"),
        "macro_summary":         parsed.get("macro_summary"),
    }
    log.info(
        f"Markt-Kontext: VIX={out['vix_level']} ({vix_source}), "
        f"S&P={out['sp500_change_pct']}%, Regime={out['market_regime']}"
    )
    return out


def vix_only_context(date: str, price_provider) -> dict:
    """Marktkontext ohne Claude-Call: nur der VIX, deterministisch von Capital.com.

    Fuer den 16:10-Lauf (C.28, Option 2). Dort entscheidet ausschliesslich der
    VIX -- check_vix mit enforce=True ist der einzige harte Guardrail-Moment
    des Tages -- und der braucht keine Websuche. Regime, Rotation und
    Makro-Satz bleiben None: sie werden hier nicht erhoben und sollen in der
    16:10-Zeile auch nicht als erhoben erscheinen. Den Morgenkontext fuer den
    Portfolio-Check laedt der Aufrufer ueber db.load_market_context()."""
    out = _empty_context()
    vix = _vix_from_capital(price_provider, date)
    out["vix_level"] = vix
    out["vix_source"] = "capital.com" if vix is not None else None
    log.info(f"Markt-Kontext (16:10, ohne Claude): VIX={vix}")
    return out
