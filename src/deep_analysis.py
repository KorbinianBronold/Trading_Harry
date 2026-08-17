"""Phase 3: Policy monitor (1× per run) + Batch-Tiefenanalyse nach Sub-Sektor.

Beide Aufrufer nutzen Sonnet + server-seitige web_search. Die Ticker werden von
build_batches() nach Sub-Sektor gruppiert und je Batch in einem gestreamten
Call analysiert (analyze_batch()); analyze_batches() umschliesst das mit dem
Retry/Halbier-Fehlerpfad aus Spec 10. Das 8-Dimensionen-Scoring kommt vom
Modell unveraendert zurueck und wird stromabwaerts von guardrails.py geprueft.
Nur CostCapExceeded (aus cost_tracker) ist fatal."""
import json
import logging
from pathlib import Path

import config
from src.cost_tracker import CostTracker
from src.utils import call_claude, extract_json_blob, WEB_SEARCH_TOOL

log = logging.getLogger("shares_future.deep_analysis")

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
DEEP_SYSTEM_PROMPT = (PROMPT_DIR / "deep_analysis_v2.txt").read_text()  # fuer analyze_batch()
POLICY_SYSTEM_PROMPT = (PROMPT_DIR / "policy_monitor_v1.txt").read_text()

MODEL = "claude-sonnet-4-6"
# Spec 4.8: der alte feste Wert 4096 war fuer EINEN Ticker ausgelegt, das
# Budget wird deshalb aus der Batchgroesse abgeleitet.
#
# ⚠️ Die erste Fassung (900/Ticker + 2000 fest) ist durch den Testlauf aus
# Plan 3a Task 10 WIDERLEGT -- Details PROJECT_STATUS C.9. Zwei Fehler:
#
# 1. 900 lag unter dem echten Bedarf. Der v2-Prompt verlangt je Ticker acht
#    Dimensionen mit je zwei Belegzeilen plus evidence_quality, eine
#    600-Zeichen-Summary, ~20 Zahlenfelder und sources_used. Gemessen:
#    bei ~2048 Tokens/Ticker liefen 5 von 6 Batches durch, bei ~1400 nur
#    1 von 9. 2500 setzt darueber an, mit Luft fuer den geschwaetzigen Fall.
# 2. Der FESTE Reserve-Term machte die Formel regressiv: er verwaesserte den
#    Pro-Ticker-Wert, je groesser der Batch wurde (1150/Ticker bei n=8 gegen
#    2048 bei n=2). Genau verkehrt herum -- im grossen Batch kann ein einzelner
#    geschwaetziger Ticker das Budget der anderen aufzehren, der braucht also
#    MEHR Luft, nicht weniger. Die Reserve deckt nur den JSON-Rahmen
#    ({"results": [...]}, ~10 Tokens); 200 ist dafuer reichlich.
#
# Die Decke kostet fuer sich genommen nichts: abgerechnet wird, was tatsaechlich
# erzeugt wird. Ein zu knapper Wert dagegen kostet den ganzen Call -- ein
# gekapptes Ergebnis wird verworfen (s. BatchTruncatedError). Im Testlauf gingen
# so ~21 % der Laufkosten fuer nichts drauf.
TOKENS_PER_TICKER_DEEP = 2500
BATCH_TOKEN_RESERVE = 200
MAX_TOKENS_DEEP_MIN = 4096
MAX_TOKENS_POLICY = 3072

# Eine identische Wiederholung nach einer Kappung liefert deterministisch
# dieselbe Kappung -- im Testlauf fuenfmal beobachtet, je ~2-3 Minuten fuer ein
# garantiert wertloses Ergebnis. Die Wiederholung bekommt deshalb mehr Platz.
# Faktor 2 statt eines feineren Werts: wer einmal ueber die Decke laeuft, ist
# selten knapp darueber, und die Decke kostet nur, was sie auch nutzt.
TRUNCATION_RETRY_FACTOR = 2


class DeepAnalysisError(RuntimeError):
    """Per-asset deep_analysis call produced unparseable output."""


class BatchTruncatedError(DeepAnalysisError):
    """Die Batch-Antwort lief in max_tokens und ist abgeschnitten.

    Eigene Klasse, weil der Fehlerpfad anders reagieren muss als bei einer
    kaputten Antwort: hier ist die Decke das Problem, also hilft nur mehr
    Platz -- dieselbe Anfrage nochmal zu stellen liefert dieselbe Kappung.
    Bleibt ein DeepAnalysisError, damit Aufrufer ausserhalb des Fehlerpfads
    weiterhin nur eine Fehlerklasse kennen muessen."""


class PolicyMonitorError(RuntimeError):
    """Policy monitor failed to produce parseable output."""


def run_policy_monitor(
    date: str, run_type: str, cost_tracker: CostTracker,
) -> dict:
    """Single Sonnet+web_search call. Returns
    {policy_risk_level, events, summary}. Tolerates empty events list."""
    user_msg = (
        f"Today is {date}. Run type: {run_type}. "
        "Use web_search 2-5 times to surface market-moving policy/geopolitics "
        "events from the last 48h. Then return the JSON object defined in your "
        "system prompt."
    )
    result = call_claude(
        model=MODEL, system=POLICY_SYSTEM_PROMPT, user=user_msg,
        max_tokens=MAX_TOKENS_POLICY, tools=[WEB_SEARCH_TOOL],
    )
    cost_tracker.add_from_result(result)
    parsed = extract_json_blob(result.text, PolicyMonitorError)
    if "events" not in parsed or "policy_risk_level" not in parsed:
        raise PolicyMonitorError(
            "Policy monitor response missing required keys "
            "(policy_risk_level, events)"
        )
    log.info(
        f"Policy monitor: level={parsed['policy_risk_level']} "
        f"events={len(parsed['events'])} cost={cost_tracker.total_eur:.3f} EUR"
    )
    return parsed


def build_batches(
    ticker_datas: list[dict],
    batch_size: int = config.BATCH_SIZE_DEEP,
) -> list[list[dict]]:
    """Gruppiert Ticker fuer die Batch-Tiefenanalyse nach Sub-Sektor (Spec 20.2).

    Sub-Sektoren sind unteilbare Einheiten, die per First-Fit-Decreasing in
    Batches bis batch_size gepackt werden -- ausser ein Sub-Sektor ueberschreitet
    batch_size allein, dann wird er vorher aufgeteilt. Ticker ohne Sektor bilden
    eine eigene Einheit statt still in einen fremden Sub-Sektor zu rutschen.

    Deterministisch: innerhalb einer Einheit alphabetisch nach Ticker, Einheiten
    nach (Groesse absteigend, erster Ticker). Ohne das waeren weder die Tests
    noch der 3D-Vergleich zweier Laeufe reproduzierbar.

    Die Regel wirkt in beide Richtungen, weil sich die Verteilung mit der
    Universumsgroesse dreht: heute (20 Aktien, 12 Sub-Sektoren, groesster 3)
    dominiert das Zusammenlegen, beim 3F-Ausbau das Aufteilen."""
    if batch_size < 1:
        raise ValueError(f"batch_size muss >= 1 sein, war {batch_size}")

    by_sector: dict[str, list[dict]] = {}
    for td in ticker_datas:
        by_sector.setdefault(td.get("sector") or "", []).append(td)

    units: list[list[dict]] = []
    for sector in sorted(by_sector):
        members = sorted(by_sector[sector], key=lambda t: t["ticker"])
        for i in range(0, len(members), batch_size):
            units.append(members[i:i + batch_size])

    units.sort(key=lambda u: (-len(u), u[0]["ticker"]))

    batches: list[list[dict]] = []
    for unit in units:
        for b in batches:
            if len(b) + len(unit) <= batch_size:
                b.extend(unit)
                break
        else:
            batches.append(list(unit))

    log.info(
        f"Phase 3: {len(ticker_datas)} Ticker in {len(batches)} Batches "
        f"(Groessen: {[len(b) for b in batches]}, batch_size={batch_size})"
    )
    return batches


def max_tokens_for_batch(n: int) -> int:
    """Output-Token-Budget fuer einen Batch von n Tickern (Spec 4.8)."""
    return max(MAX_TOKENS_DEEP_MIN, n * TOKENS_PER_TICKER_DEEP + BATCH_TOKEN_RESERVE)


def _batch_entry(td: dict, cutoff: dict) -> dict:
    """Ein Eintrag der Batch-Nutzlast: der td-Schnappschuss unveraendert, daneben
    der Phase-2-Scan und das deterministische Technik-Signal.

    Sidecar-Invariante: td wird NICHT ergaenzt, der Zusatzkontext liegt in
    eigenen Schluesseln neben ihm. Wer stattdessen in td schreibt, aendert
    stillschweigend vier Prompts."""
    return {
        "snapshot": td,
        "news_scan": {"news_strength": cutoff.get("news_strength")},
        "technical_signal": {
            "direction": cutoff.get("tech_direction"),
            "strength": cutoff.get("tech_strength"),
        },
    }


def _build_batch_user_message(
    ticker_datas: list[dict],
    cutoff_by_ticker: dict[str, dict],
    trend_context: dict,
    policy_context: dict,
) -> str:
    """Komponiert die User-Message fuer einen ganzen Batch: gemeinsamer Trend-
    und Policy-Kontext einmal, dann je Ticker ein Eintrag."""
    parts = [
        "TREND CONTEXT:", json.dumps(trend_context, ensure_ascii=False),
        "\nPOLICY CONTEXT:", json.dumps(policy_context, ensure_ascii=False),
        "\nBATCH (one ticker per line, JSON):",
    ]
    for td in ticker_datas:
        entry = _batch_entry(td, cutoff_by_ticker.get(td["ticker"], {}))
        parts.append(json.dumps(entry, ensure_ascii=False))
    parts.append(
        "\nReturn the JSON object defined in your system prompt with one entry "
        "per ticker above, in the same order."
    )
    return "\n".join(parts)


def analyze_batch(
    ticker_datas: list[dict],
    cutoff_by_ticker: dict[str, dict],
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
    max_tokens_override: int | None = None,
) -> tuple[list[dict], list[str]]:
    """Analysiert einen ganzen Batch in EINEM gestreamten Sonnet-Call.

    Rueckgabe: (analyses, missing_tickers). Gelieferte Analysen werden IMMER
    uebernommen, auch wenn Ticker fehlen -- Spec 10: 'zehn gute Analysen
    schlagen null'. Das unterscheidet die Tiefenanalyse bewusst von
    quick_filter_batch, das bei fehlenden Tickern warf.

    max_tokens_override hebt die aus der Batchgroesse abgeleitete Decke an.
    Genutzt vom Fehlerpfad nach einer Kappung -- sonst None.

    Wirft DeepAnalysisError, wenn die Antwort als GANZES unbrauchbar ist:
    unparsebar oder ohne results-Liste. Bei einer Kappung (stop_reason ==
    'max_tokens', Spec 4.8 -- kein akzeptables Ergebnis) wirft sie die
    Unterklasse BatchTruncatedError, damit der Aufrufer aus Task 7 mit mehr
    Platz wiederholen kann statt mit derselben Decke."""
    if not ticker_datas:
        return [], []

    user_msg = _build_batch_user_message(
        ticker_datas, cutoff_by_ticker, trend_context, policy_context)
    max_tokens = max_tokens_override or max_tokens_for_batch(len(ticker_datas))

    result = call_claude(
        model=MODEL, system=DEEP_SYSTEM_PROMPT, user=user_msg,
        max_tokens=max_tokens, tools=[WEB_SEARCH_TOOL], stream=True,
    )
    cost_tracker.add_from_result(result)

    if getattr(result, "stop_reason", None) == "max_tokens":
        raise BatchTruncatedError(
            f"Batch-Antwort bei max_tokens={max_tokens} abgeschnitten "
            f"(stop_reason=max_tokens, {len(ticker_datas)} Ticker) -- ein "
            f"abgeschnittenes Ergebnis wird nicht verwertet (Spec 4.8)"
        )

    parsed = extract_json_blob(result.text, DeepAnalysisError)
    results = parsed.get("results")
    if not isinstance(results, list):
        raise DeepAnalysisError("Batch-Antwort ohne 'results'-Liste")

    by_ticker = {r.get("ticker"): r for r in results if isinstance(r, dict)}

    analyses, missing = [], []
    for td in ticker_datas:
        t = td["ticker"]
        a = by_ticker.get(t)
        if a is None:
            missing.append(t)
            continue
        analyses.append(a)

    if missing:
        log.warning(
            f"Batch lieferte {len(analyses)}/{len(ticker_datas)} Ticker; "
            f"fehlend: {', '.join(missing)}"
        )
    log.info(
        f"Batch ({len(ticker_datas)} Ticker) fertig: {len(analyses)} Analysen, "
        f"{result.web_search_calls} Websuchen, "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return analyses, missing


def _run_one_batch_with_recovery(
    batch: list[dict],
    cutoff_by_ticker: dict[str, dict],
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
) -> tuple[list[dict], list[str]]:
    """Spec 10: einmal wiederholen -> einmal halbieren (jede Haelfte genau
    einmal) -> aufgeben. Bewusst begrenzte Tiefe: ein kaputter Prompt soll
    nicht endlos retryen, aber ein Fehler soll auch nicht den ganzen Batch
    kosten.

    Diese Ebene faengt NUR DeepAnalysisError (unbrauchbare Ausgabe).
    CostCapExceeded laeuft ungehindert durch -- ein Kosten-Abbruch ist fatal,
    und ihn hier zu wiederholen liesse den Lauf ueber den Deckel hinaus
    weiterlaufen. Transiente API-Fehler behandelt bereits retry_with_backoff
    in call_claude(); das ist eine andere Fehlerklasse und eine andere Ebene.

    ⚠️ Eine KAPPUNG wird anders behandelt als eine kaputte Antwort (C.9):
    dieselbe Anfrage mit derselben Decke liefert wieder dieselbe Kappung, die
    Wiederholung bekommt deshalb TRUNCATION_RETRY_FACTOR-fach Platz. Der
    angehobene Faktor gilt danach auch fuer die Haelften -- seit der
    Formel-Korrektur aendert Halbieren den Platz PRO TICKER nicht mehr (frueher
    tat es das nur zufaellig ueber den 4096er-Boden), ein Halbieren mit
    normaler Decke waere also ein Schlag ins Wasser."""
    faktor = 1

    def attempt(tds: list[dict]) -> tuple[list[dict], list[str]]:
        override = max_tokens_for_batch(len(tds)) * faktor if faktor > 1 else None
        return analyze_batch(
            ticker_datas=tds, cutoff_by_ticker=cutoff_by_ticker,
            trend_context=trend_context, policy_context=policy_context,
            cost_tracker=cost_tracker, max_tokens_override=override,
        )

    for versuch in (1, 2):
        try:
            return attempt(batch)
        except BatchTruncatedError as e:
            # Muss VOR dem DeepAnalysisError-Zweig stehen (Unterklasse).
            faktor = TRUNCATION_RETRY_FACTOR
            log.warning(
                f"Batch-Versuch {versuch}/2 abgeschnitten ({len(batch)} Ticker): "
                f"{e}. Naechster Versuch mit {TRUNCATION_RETRY_FACTOR}-facher "
                f"Decke -- eine identische Wiederholung kaeme identisch zurueck."
            )
        except DeepAnalysisError as e:
            log.warning(
                f"Batch-Versuch {versuch}/2 fehlgeschlagen "
                f"({len(batch)} Ticker): {e}"
            )

    if len(batch) == 1:
        t = batch[0]["ticker"]
        log.warning(f"{t}: Batch der Groesse 1 zweimal fehlgeschlagen, aufgegeben")
        return [], [t]

    mid = len(batch) // 2
    log.warning(
        f"Batch ({len(batch)} Ticker) zweimal fehlgeschlagen, halbiere in "
        f"{mid} + {len(batch) - mid}"
    )
    analyses: list[dict] = []
    failed: list[str] = []
    for haelfte in (batch[:mid], batch[mid:]):
        try:
            a, m = attempt(haelfte)
            analyses.extend(a)
            failed.extend(m)
        except DeepAnalysisError as e:
            tickers = [td["ticker"] for td in haelfte]
            log.warning(
                f"Haelfte ({', '.join(tickers)}) fehlgeschlagen, aufgegeben: {e}"
            )
            failed.extend(tickers)
    return analyses, failed


def analyze_batches(
    ticker_datas: list[dict],
    cutoff_by_ticker: dict[str, dict],
    trend_context: dict,
    policy_context: dict,
    cost_tracker: CostTracker,
    batch_size: int = config.BATCH_SIZE_DEEP,
) -> tuple[list[dict], list[str]]:
    """Phase 3: gruppiert die Kandidaten in Sub-Sektor-Batches und analysiert
    jeden mit der Fehlerpfad-Schale aus Spec 10.

    Rueckgabe: (analyses, failed_tickers). Ersetzt analyze_assets() --
    CostCapExceeded propagiert weiterhin (der Orchestrator verschickt die
    Teilergebnis-Mail)."""
    analyses: list[dict] = []
    failed: list[str] = []
    for batch in build_batches(ticker_datas, batch_size=batch_size):
        a, f = _run_one_batch_with_recovery(
            batch=batch, cutoff_by_ticker=cutoff_by_ticker,
            trend_context=trend_context, policy_context=policy_context,
            cost_tracker=cost_tracker,
        )
        analyses.extend(a)
        failed.extend(f)

    if failed:
        log.warning(
            f"Phase 3: {len(failed)} Ticker ohne Analyse "
            f"({', '.join(sorted(failed))})"
        )
    log.info(
        f"Phase 3 done: {len(analyses)} Analysen aus {len(ticker_datas)} "
        f"Kandidaten, cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return analyses, failed
