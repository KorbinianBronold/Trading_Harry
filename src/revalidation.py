"""Der billige Zweitcheck des trade_proposals-Laufs (Entscheidung E1).

Ein Sonnet-Call je Signal, OHNE web_search: die Recherche hat die Tiefenanalyse am
Morgen bereits bezahlt. Der POLICY CONTEXT im Prompt ist seit C.48 / F65 die
Morgenlage aus der DB (Entscheidung 16.09.: der Policy-Monitor laeuft nur einmal am
Tag) -- der 16:10-Lauf hat damit gar keine Websuche mehr. Gemessen kostet eine
volle Tiefenanalyse ~0,12 EUR und ~54 s — 27 davon haetten den 4-EUR-Deckel
gerissen und die 70-Minuten-Luecke zwischen den beiden Crons gesprengt.

Das Modul urteilt nur. Was mit dem Urteil geschieht — Ablösung der pre_market-Zeile,
neue Prediction oder blosse Warnung — entscheidet main.run_trade_proposals()."""
import json
import logging
from pathlib import Path

import config
from src.cost_tracker import CostTracker
from src.portfolio_check import TECHNICAL_KEYS
from src.signal_checks import CheckResult, derive_levels
from src.utils import call_claude_retry_on_truncation, extract_json_blob

log = logging.getLogger("shares_future.revalidation")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "trade_proposals_v1.txt").read_text()

MODEL = config.CLAUDE_MODEL_SONNET
# ⚠️ 1024 war gegen claude-sonnet-4-6 bemessen, das ohne explizites
# thinking-Feld nicht dachte. Unter claude-sonnet-5 teilen sich Denk- und
# Antworttokens die Decke. Der Fall ist hier besonders unguenstig:
# revalidate_one() laeuft je offener Position, und eine gekappte Antwort liesse
# die Zeile offen (s. Docstring) -- also ein stiller Ausfall genau im
# 16:10-Lauf, der ueber Ablehnungen entscheidet.
#
# GEMESSEN (2026-08-20, C.18): 6 Wiederholungen mit echter Prediction-Zeile und
# echtem collect()-Snapshot, 6/6 sauber, Output 775-1232 Tokens (Spitze bei 20 %
# dieser Decke). ⚠️ DREI der sechs Stichproben lagen ueber der alten 1024er
# Decke -- der Wert war also nicht vorsorglich zu hoch gegriffen, sondern
# vorher zu knapp: rund die Haelfte der 16:10-Re-Validierungen haette gekappt,
# und mangels stop_reason-Pruefung waere das als "Zeile bleibt offen"
# durchgegangen statt als Fehler.
MAX_TOKENS = 6144

VERDICTS = frozenset({"bestaetigt", "geschwaecht", "unveraendert", "gedreht"})

# C.49 / F67: was von der Morgen-Prediction in den Prompt geht -- die These
# und ihre Levels, nicht die Pipeline-Zeile (id, status, learnable, rank_score,
# candidate_class, created_at, Score-Spalten ...). Bis C.49 ging SELECT *
# mit rund 60 Spalten in den bezahlten Call (dieselbe Klasse wie F48).
PREDICTION_KEYS = (
    "ticker", "direction", "entry_price", "is_premarket",
    "tp_price", "sl_price", "tp_pct", "sl_pct", "rr_ratio",
    "probability_pct", "confidence", "hold_days_recommended",
    "intraday_range_pct", "summary",
)
# Der Snapshot: dieselben 14 Technik-Schluessel wie im Portfolio-Check (C.46)
# plus der echte Eroeffnungskurs (C.49 / F70).
SNAPSHOT_KEYS = (*TECHNICAL_KEYS, "price_open")


class RevalidationError(RuntimeError):
    """Die Re-Validierung lieferte unlesbares oder schematisch ungueltiges JSON."""


def _field(row, key: str):
    """Feldzugriff, der fuer sqlite3.Row UND dict funktioniert (Row kennt kein .get)."""
    return row[key] if key in row.keys() else None


def prediction_view(prediction) -> dict:
    """Die Morgen-These fuer den Prompt: nur PREDICTION_KEYS, in dieser Reihenfolge."""
    return {k: prediction[k] for k in PREDICTION_KEYS if k in prediction.keys()}


def snapshot_view(snapshot: dict) -> dict:
    """Der 16:10-Snapshot fuer den Prompt: nur SNAPSHOT_KEYS (Technik + Open),
    keine Fundamentals, kein Sektor, kein data_quality."""
    return {k: snapshot.get(k) for k in SNAPSHOT_KEYS}


def _pct(a: float | None, b: float | None) -> str:
    """'+1.46 %' fuer die Bewegung von a nach b, '?' ohne beide Werte."""
    if not a or b is None:
        return "?"
    return f"{(b - a) / a * 100:+.2f} %"


def _build_user_message(
    prediction, snapshot: dict, checks: list[CheckResult],
    relative_strength: float | None, policy_context: dict,
    tech: dict | None = None, date: str | None = None,
) -> str:
    """Serialisiert Datumsanker, Morgen-These (PREDICTION_KEYS), 16:10-Snapshot
    (SNAPSHOT_KEYS), Technik-Signal Morgen -> jetzt (0-4), die Levels gegen den
    aktuellen Kurs, die Bewegung Vorboerse -> Open -> jetzt, die relative
    Staerke, die angeschlagenen Checks und die Morgen-Policy-Lage in EINE
    Nachricht (C.49 / F67 + F70)."""
    pred = prediction_view(prediction)
    snap = snapshot_view(snapshot)
    keys = prediction.keys()
    direction = prediction["direction"]
    price = snapshot.get("price")
    tp, sl = _field(prediction, "tp_price"), _field(prediction, "sl_price")
    morning_sig = (f"{prediction['tech_direction']}/{prediction['tech_strength']}"
                   if "tech_direction" in keys and prediction["tech_direction"] else "unknown")
    now_sig = (f"{tech.get('tech_direction')}/{tech.get('tech_strength')}"
               if tech and tech.get("tech_direction") else "unknown")
    if price and tp is not None and sl is not None:
        lv = derive_levels(price, tp, sl, direction)
        levels = (f"entry {price}, TP {tp} ({lv['tp_pct']} %), SL {sl} ({lv['sl_pct']} %), "
                  f"R/R {lv['rr_ratio']} (hard minimum {config.RR_RATIO_MIN_HARD})")
    else:
        levels = "unknown (no current price)"
    entry, opn = _field(prediction, "entry_price"), snapshot.get("price_open")
    move = (f"pre-market entry {entry} -> open {opn} ({_pct(entry, opn)}) "
            f"-> now {price} ({_pct(opn, price)} since open)" if opn
            else f"pre-market entry {entry} -> now {price} ({_pct(entry, price)}; no opening bar)")
    fired = [f"{c.rule}: {c.detail}" for c in checks] or ["keine"]
    rs = ("unbekannt" if relative_strength is None
          else f"{relative_strength:+.2f} Punkte (seit gestern Schluss, gegen den Sub-Sektor-ETF)")
    head = ([f"Today is {date}. Run type: trade_proposals "
             f"(about 40 minutes after the US open, 10:10 ET).\n"] if date else [])
    return "\n".join([
        *head,
        "ORIGINAL PREDICTION (pre_market, before the open):",
        json.dumps(pred, ensure_ascii=False, default=str),
        "\nCURRENT SNAPSHOT (price now; technicals include today's session so far):",
        json.dumps(snap, ensure_ascii=False, default=str),
        f"\nTECHNICAL SIGNAL (deterministic, strength 0-4): morning {morning_sig} -> now {now_sig}",
        f"\nLEVELS AT CURRENT PRICE: {levels}",
        f"MOVE: {move}",
        f"\nRELATIVE STRENGTH: {rs}",
        "\nFIRED CHECKS:", "\n".join(f"- {f}" for f in fired),
        "\nPOLICY CONTEXT (from this morning's research, not refreshed):",
        json.dumps(policy_context, ensure_ascii=False),
        "\nGib das JSON-Objekt aus deinem System-Prompt zurueck.",
    ])


def _window_error(direction: str, tp, sl, low, high) -> str | None:
    """Plausibilitaet des Entry-Fensters (C.49 / F71, F51-Klasse): beide Werte
    oder keiner, low <= high, und das Fenster liegt zwischen Stop und Ziel."""
    if low is None and high is None:
        return None
    if low is None or high is None:
        return "nur eine Grenze geliefert"
    try:
        low, high = float(low), float(high)
    except (TypeError, ValueError):
        return "keine Zahl"
    if low > high:
        return f"low {low} > high {high}"
    if tp is None or sl is None:
        return None
    if direction == "long" and not (sl < low and high < tp):
        return f"nicht zwischen SL {sl} und TP {tp} (long)"
    if direction == "short" and not (tp < low and high < sl):
        return f"nicht zwischen TP {tp} und SL {sl} (short)"
    return None


def revalidate_one(
    prediction: dict,
    snapshot: dict,
    checks: list[CheckResult],
    relative_strength: float | None,
    policy_context: dict,
    cost_tracker: CostTracker,
    tech: dict | None = None,
    date: str | None = None,
) -> dict:
    """Prueft EIN Morgensignal gegen frische Kurse. Gibt das geparste Urteil zurueck,
    ergaenzt um den Ticker. Wirft RevalidationError bei unlesbarer Antwort,
    unbekanntem Urteil oder einer Wahrscheinlichkeit ausserhalb 0-100 — der
    Aufrufer faengt das und laesst die Zeile dann offen. Ein unplausibles
    Entry-Fenster (Seite, Reihenfolge, halb) wird verworfen (beide None, WARNING),
    das Urteil bleibt (C.49 / F71). `tech` ist der Sidecar-Eintrag des Tickers
    von jetzt, `date` der Datumsanker."""
    user_msg = _build_user_message(
        prediction, snapshot, checks, relative_strength, policy_context,
        tech=tech, date=date)
    # Bucht jeden Versuch selbst -- auch einen verworfenen gekappten.
    result = call_claude_retry_on_truncation(
        model=MODEL, system=SYSTEM_PROMPT, user=user_msg,
        max_tokens=MAX_TOKENS, cost_tracker=cost_tracker, tools=[],
    )
    parsed = extract_json_blob(result.text, RevalidationError)

    verdict = parsed.get("verdict")
    if verdict not in VERDICTS:
        raise RevalidationError(
            f"Unbekanntes Urteil {verdict!r} (erlaubt: {sorted(VERDICTS)})"
        )
    prob = parsed.get("probability_pct")
    try:
        prob = int(round(float(prob)))
    except (TypeError, ValueError):
        raise RevalidationError(f"probability_pct nicht lesbar: {prob!r}")
    if not 0 <= prob <= 100:
        raise RevalidationError(f"probability_pct {prob} ausserhalb 0-100")
    parsed["probability_pct"] = prob

    err = _window_error(prediction["direction"], _field(prediction, "tp_price"),
                        _field(prediction, "sl_price"),
                        parsed.get("entry_window_low"), parsed.get("entry_window_high"))
    if err:
        log.warning(f"{prediction['ticker']}: Entry-Fenster verworfen -- {err} "
                    f"(low={parsed.get('entry_window_low')}, "
                    f"high={parsed.get('entry_window_high')})")
        parsed["entry_window_low"] = parsed["entry_window_high"] = None
    parsed["ticker"] = prediction["ticker"]
    parsed["prediction_id"] = prediction["id"]
    return parsed
