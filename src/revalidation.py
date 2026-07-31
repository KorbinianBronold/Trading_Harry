"""Der billige Zweitcheck des trade_proposals-Laufs (Entscheidung E1).

Ein Sonnet-Call je Signal, OHNE web_search: die Recherche hat die Tiefenanalyse am
Morgen bereits bezahlt, und Breaking News zwischen 15:00 und 16:10 deckt der eine
Policy-Monitor-Call des Laufs ab. Gemessen kostet eine volle Tiefenanalyse ~0,12 EUR
und ~54 s — 27 davon haetten den 4-EUR-Deckel gerissen und die 70-Minuten-Luecke
zwischen den beiden Crons gesprengt.

Das Modul urteilt nur. Was mit dem Urteil geschieht — Ablösung der pre_market-Zeile,
neue Prediction oder blosse Warnung — entscheidet main.run_trade_proposals()."""
import json
import logging
from pathlib import Path

import config
from src.cost_tracker import CostTracker
from src.signal_checks import CheckResult
from src.utils import call_claude, extract_json_blob

log = logging.getLogger("shares_future.revalidation")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "trade_proposals_v1.txt").read_text()

MODEL = config.CLAUDE_MODEL_SONNET
MAX_TOKENS = 1024

VERDICTS = frozenset({"bestaetigt", "geschwaecht", "unveraendert", "gedreht"})


class RevalidationError(RuntimeError):
    """Die Re-Validierung lieferte unlesbares oder schematisch ungueltiges JSON."""


def _build_user_message(
    prediction: dict, snapshot: dict, checks: list[CheckResult],
    relative_strength: float | None, policy_context: dict,
) -> str:
    """Serialisiert Morgen-These, frischen Snapshot, relative Staerke, die bereits
    angeschlagenen Checks und den Policy-Kontext in EINE Nachricht."""
    pred = {k: prediction[k] for k in prediction.keys()}
    fired = [f"{c.rule}: {c.detail}" for c in checks] or ["keine"]
    rs = "unbekannt" if relative_strength is None else f"{relative_strength:+.2f} Punkte"
    return "\n".join([
        "ORIGINAL PREDICTION:", json.dumps(pred, ensure_ascii=False, default=str),
        "\nCURRENT SNAPSHOT:", json.dumps(snapshot, ensure_ascii=False, default=str),
        f"\nRELATIVE STRENGTH: {rs}",
        "\nFIRED CHECKS:", "\n".join(f"- {f}" for f in fired),
        "\nPOLICY CONTEXT:", json.dumps(policy_context, ensure_ascii=False),
        "\nGib das JSON-Objekt aus deinem System-Prompt zurueck.",
    ])


def revalidate_one(
    prediction: dict,
    snapshot: dict,
    checks: list[CheckResult],
    relative_strength: float | None,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> dict:
    """Prueft EIN Morgensignal gegen frische Kurse. Gibt das geparste Urteil zurueck,
    ergaenzt um den Ticker. Wirft RevalidationError bei unlesbarer Antwort oder
    unbekanntem Urteil — der Aufrufer faengt das und laesst die Zeile dann offen."""
    user_msg = _build_user_message(
        prediction, snapshot, checks, relative_strength, policy_context)
    result = call_claude(
        model=MODEL, system=SYSTEM_PROMPT, user=user_msg,
        max_tokens=MAX_TOKENS, tools=[],
    )
    cost_tracker.add_from_result(result)
    parsed = extract_json_blob(result.text, RevalidationError)

    verdict = parsed.get("verdict")
    if verdict not in VERDICTS:
        raise RevalidationError(
            f"Unbekanntes Urteil {verdict!r} (erlaubt: {sorted(VERDICTS)})"
        )
    parsed["ticker"] = prediction["ticker"]
    parsed["prediction_id"] = prediction["id"]
    return parsed
