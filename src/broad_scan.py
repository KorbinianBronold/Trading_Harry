"""Phase 2 (Nachrichten-Scan) + Phase 2a (Cutoff).

broad_scan_batch(): ein Sonnet-Call mit Websuche ueber alle Ueberlebenden aus
Phase 1. Liefert je Ticker {ticker, news_strength (0-3), news_note}.

cutoff_candidates(): waehlt daraus die Kandidaten fuer Phase 3 (Spec 4.7) --
deterministisch, kein Claude-Call. Kein DB-Schreiben in diesem Modul; die
Persistenz von cutoff_candidates()' zweitem Rueckgabewert ist db.log_cutoff().

Noch nicht in die Pipeline verdrahtet -- das macht Task 10, die auch die
Rohstoff/Krypto-Filterung vor dem broad_scan_batch()-Aufruf uebernimmt
(Spec 6.2, R25)."""
import json
import logging
from pathlib import Path

import config
from src.cost_tracker import CostTracker
from src.utils import call_claude, extract_json_blob, WEB_SEARCH_TOOL

log = logging.getLogger("shares_future.broad_scan")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "broad_scan_v1.txt").read_text()

MODEL = config.CLAUDE_MODEL_HAIKU  # News-Scoring (0-3) braucht keine Sonnet-Kraft, spart 90%

# R27 / Spec 20.4: 500 Ticker x ein Ergebnisobjekt sprengt quick_filters 4096
# deutlich -- die Rechnung steht im Task-8-Report. Ein aktiver Nachrichtentag
# beim vollen 500-Ticker-Ausbau braucht geschaetzt ~15.400 Output-Tokens; mit
# Sicherheitsfaktor fuer ausfuehrlichere Notizen ~26.000-32.000.
#
# Korrektur (Plan 3a, Task 2): der Wert stand auf 24.000 und lag damit UNTER
# der eigenen Sicherheitsspanne, waehrend der Kommentar "echten Spielraum"
# behauptete. Jetzt 32.000, die Oberkante der Spanne. Das kostet nichts:
# max_tokens ist eine Obergrenze, abgerechnet werden nur tatsaechlich
# generierte Tokens.
#
# Zum Timeout-Risiko: eine fruehere Fassung dieses Kommentars behauptete, die
# Anthropic-SDK verweigere nicht gestreamte Requests oberhalb einer
# Token-Schaetzung mit ValueError. Das stimmt fuer neuere SDK-Versionen, aber
# NICHT fuer das hier gepinnte anthropic==0.42.0 (requirements.txt) --
# verifiziert durch Durchsuchen des installierten Pakets. Das echte Risiko war
# der httpx-Default-Timeout von 600s bei langer Generierung plus mehreren
# Websuchen. Seit Plan 3a laeuft dieser Call gestreamt (stream=True), womit
# genau dieses Risiko entfaellt.
MAX_TOKENS = 32000
TRUNCATION_WARNING_RATIO = 0.9

# R23: die Nutzlast wird explizit zusammengesetzt (nicht json.dumps(td)) --
# genau die Felder aus Spec 4.6. Sieben stammen aus td, das achte
# (premarket_change_pct) aus dem Sidecar (R22). Als benannte Konstante, damit
# die Feldliste nicht inline verstreut im Code steht.
PAYLOAD_FIELDS_FROM_TD = (
    "ticker", "price", "price_change_1d", "price_change_5d",
    "rsi_14", "atr_pct", "sector",
)


class BroadScanError(RuntimeError):
    """Interner Marker fuer eine nicht parsebare Phase-2-Antwort.

    Verlaesst broad_scan_batch() NIE (R26-Entscheidung): ein kaputter Scan ist
    laut Spec Section 10 nicht fatal, der Lauf soll weiterlaufen und der
    Cutoff dann nur nach tech_strength und premarket_change_pct sortieren.
    Statt die Exception nach aussen zu werfen, degradiert broad_scan_batch()
    den ganzen Batch auf news_strength=0 und loggt eine WARNING."""


def _payload_for_ticker(td: dict, sidecar: dict[str, dict]) -> dict:
    """Baut die Acht-Feld-Nutzlast fuer einen Ticker: sieben Felder aus td
    plus premarket_change_pct aus dem Sidecar. Ein Ticker, der im Sidecar
    fehlt, ist kein Fehler -- der Wert ist dann schlicht None (R22)."""
    payload = {field: td.get(field) for field in PAYLOAD_FIELDS_FROM_TD}
    payload["premarket_change_pct"] = (
        sidecar.get(td["ticker"], {}).get("premarket_change_pct")
    )
    return payload


def _format_batch_for_prompt(
    ticker_datas: list[dict],
    sidecar: dict[str, dict],
    trend_context: dict,
    market_context: dict,
) -> str:
    """Komponiert die User-Message: Trend- und Marktkontext, dann je Ticker
    die explizite Acht-Feld-Nutzlast (R23) -- nie ein roher td-Dump."""
    parts = ["TREND CONTEXT:", json.dumps(trend_context, ensure_ascii=False)]
    parts.append("\nMARKET CONTEXT:")
    parts.append(json.dumps(market_context, ensure_ascii=False))
    parts.append("\nBATCH (one ticker per line, JSON):")
    for td in ticker_datas:
        parts.append(json.dumps(_payload_for_ticker(td, sidecar), ensure_ascii=False))
    parts.append(
        "\nReturn the JSON object defined in your system prompt with one entry "
        "per ticker above, in the same order."
    )
    return "\n".join(parts)


def _zero_result(ticker: str) -> dict:
    """Neutrales Ergebnis fuer einen Ticker ohne verwertbaren Scan-Treffer."""
    return {"ticker": ticker, "news_strength": 0, "news_note": ""}


def _apply_note_rule(ticker: str, entry: dict) -> dict:
    """Code-Regel aus Spec 4.6: news_strength >= 1 ohne news_note wird auf 0
    gezogen -- muss auch greifen, wenn das Modell sich nicht an die
    Prompt-Vorgabe haelt, deshalb hier statt nur im Prompt-Text.

    Bindet news_strength zusaetzlich an seine dokumentierte Domaene (Ganzzahl
    0-3, prompts/broad_scan_v1.txt Zeile 20): ein Wert ausserhalb des Bereichs
    oder mit Nachkommaanteil (7, -2, 2.5) wird -- konsistent mit jeder anderen
    Validierung hier -- auf 0 gezogen statt an die naechste Grenze geklemmt
    oder gerundet. Ein Modell, das die eigene Ganzzahl-0-3-Vorgabe schon
    verletzt, ist nicht vertrauenswuerdig genug, um den Ausreisser als
    absichtliches 'sehr starkes Signal' zu deuten -- Klemmen/Runden waere
    Raten statt Lesen, und ein zu Unrecht auf 3 geklemmter Wert wuerde das
    fuer Task 9 geplante Ranking verzerren, nicht nur verrauschen. bool wird
    bewusst vor der numerischen Pruefung ausgeschlossen: isinstance(True, int)
    ist in Python wahr, ein boolescher Wert soll aber nicht stillschweigend
    als 0/1 durchrutschen, sondern wie jeder andere Typfehler auf 0 fallen."""
    strength = entry.get("news_strength")
    if isinstance(strength, bool) or not isinstance(strength, (int, float)):
        strength = 0
    elif strength != int(strength) or not (0 <= strength <= 3):
        log.warning(
            f"{ticker}: news_strength {strength!r} ausserhalb der "
            f"dokumentierten Domaene (Ganzzahl 0-3), auf 0 gezogen"
        )
        strength = 0
    else:
        strength = int(strength)
    note = entry.get("news_note") or ""
    if strength >= 1 and not note:
        log.warning(f"{ticker}: news_strength {strength} ohne news_note, auf 0 gezogen")
        strength = 0
    return {"ticker": ticker, "news_strength": strength, "news_note": note}


def _warn_if_possibly_truncated(result) -> None:
    """Loggt eine WARNING, wenn die Antwort gekappt wurde (R27-Fix).

    Zwei Signale, in dieser Rangfolge: stop_reason == "max_tokens" ist der
    harte Beweis (seit Plan 3a auf ClaudeResult verfuegbar); output_tokens nahe
    MAX_TOKENS bleibt als Verdachtsmoment fuer den Fall, dass ein Provider
    stop_reason nicht liefert. Ohne diese Warnung ist ein anschliessend komplett
    auf news_strength=0 degradierter Batch (siehe _parse_scan_results) im Log
    nicht von einem echten ruhigen Nachrichtentag zu unterscheiden --
    ausgerechnet an newsreichen Tagen, an denen das Signal am meisten zaehlt."""
    hard = getattr(result, "stop_reason", None) == "max_tokens"
    near = result.output_tokens >= MAX_TOKENS * TRUNCATION_WARNING_RATIO
    if not (hard or near):
        return
    grund = "stop_reason=max_tokens" if hard else (
        f"output_tokens={result.output_tokens} nahe MAX_TOKENS={MAX_TOKENS}"
    )
    log.warning(
        f"Phase 2 (broad_scan): {grund} -- die Antwort war moeglicherweise "
        f"abgeschnitten. Falls dieser Batch auf news_strength=0 degradiert, "
        f"kann das an einem echten ruhigen Nachrichtentag liegen ODER an "
        f"dieser Kappung -- MAX_TOKENS pruefen/erhoehen, wenn das haeufiger "
        f"auftritt."
    )


def _parse_scan_results(text: str) -> dict[str, dict]:
    """Parst die Modellantwort zu {ticker: rohes_ergebnis_dict}. Liefert ein
    leeres Dict (statt zu werfen) wenn die Antwort unparsebar ist oder die
    'results'-Liste fehlt -- der Aufrufer degradiert dann jeden Ticker auf
    news_strength=0 (R26)."""
    try:
        parsed = extract_json_blob(text, BroadScanError)
        results = parsed.get("results")
        if not isinstance(results, list):
            raise BroadScanError("Response missing 'results' list")
    except BroadScanError as e:
        log.warning(
            f"Phase 2 (broad_scan) unparsebar, degradiere auf news_strength=0 "
            f"fuer den ganzen Batch: {e}"
        )
        return {}
    return {r.get("ticker"): r for r in results if isinstance(r, dict)}


def broad_scan_batch(
    ticker_datas: list[dict],
    sidecar: dict[str, dict],
    trend_context: dict,
    market_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """Scort alle uebergebenen Ticker in einem einzigen Sonnet+Websuche-Call.

    Liefert IMMER genau ein Ergebnis je Input-Ticker, in Eingabereihenfolge --
    ein fehlender Ticker in der Antwort bekommt news_strength=0 (nie ein
    Abbruch, anders als quick_filter). Eine komplett unparsebare Antwort
    degradiert ebenfalls auf news_strength=0 fuer den ganzen Batch statt zu
    werfen (R26, Spec Section 10). Rohstoffe/Krypto filtert der Aufrufer
    (R25/Task 10) -- diese Funktion scort, was sie bekommt."""
    if not ticker_datas:
        return []

    user_msg = _format_batch_for_prompt(
        ticker_datas, sidecar, trend_context, market_context)

    result = call_claude(
        model=MODEL,
        system=SYSTEM_PROMPT,
        user=user_msg,
        max_tokens=MAX_TOKENS,
        tools=[WEB_SEARCH_TOOL],
        stream=True,
    )
    cost_tracker.add_from_result(result)
    _warn_if_possibly_truncated(result)

    by_ticker = _parse_scan_results(result.text)

    ordered = []
    for td in ticker_datas:
        t = td["ticker"]
        entry = by_ticker.get(t)
        if entry is None:
            log.warning(f"{t}: kein Scan-Ergebnis in der Antwort, news_strength=0")
            ordered.append(_zero_result(t))
            continue
        ordered.append(_apply_note_rule(t, entry))

    log.info(
        f"Phase 2 (broad_scan) done: {len(ordered)} gescannt, "
        f"cost so far: {cost_tracker.total_eur:.3f} EUR"
    )
    return ordered


def cutoff_candidates(
    ticker_datas: list[dict],
    broad_scan_results: list[dict],
    sidecar: dict[str, dict],
    forced_candidates: set[str],
    max_deep_analysis: int = config.MAX_DEEP_ANALYSIS,
) -> tuple[list[dict], list[dict]]:
    """Phase 2a: waehlt die Kandidaten fuer Phase 3 (Spec 4.7).

    Kandidat = news_strength >= 1 ODER tech_strength >= TECH_MIN_FOR_DEEP ODER
    Pflicht-Kandidat aus Phase 1e. Sortierung: Pflicht-Kandidaten zuerst, dann
    (news_strength, |premarket_change_pct|, tech_strength, ticker) absteigend.
    Ein fehlender premarket_change_pct sortiert hinter jedem gemessenen Wert
    -- auch hinter einem echten 0.0, deshalb die explizite `is not None`-
    Pruefung statt einer Wahrheitswert-Abfrage.

    Rueckgabe: (selected, all_evaluated). all_evaluated traegt ALLE Ticker in
    derselben Sortierreihenfolge mit rank_position und selected-Flag -- das
    ist die Nutzlast fuer db.log_cutoff() (3D vergleicht den 51. mit dem 50.).
    Tech-Werte und premarket_change_pct kommen aus dem Sidecar (R22), nie aus
    td -- Rohstoffe/Krypto filtert der Aufrufer vorher (Spec 18.3)."""
    scan_by_ticker = {s["ticker"]: s for s in broad_scan_results}

    evaluated = []
    for td in ticker_datas:
        t = td["ticker"]
        scan = scan_by_ticker.get(t, {})
        side = sidecar.get(t, {})
        news_strength = scan.get("news_strength", 0)
        tech_strength = side.get("tech_strength", 0)
        forced = t in forced_candidates
        qualifies = (
            news_strength >= 1
            or tech_strength >= config.TECH_MIN_FOR_DEEP
            or forced
        )
        evaluated.append({
            "ticker": t,
            "news_strength": news_strength,
            "premarket_change_pct": side.get("premarket_change_pct"),
            "tech_direction": side.get("tech_direction"),
            "tech_agreement": side.get("tech_agreement"),
            "tech_strength": tech_strength,
            "forced": forced,
            "qualifies": qualifies,
        })

    def sort_key(e):
        change = e["premarket_change_pct"]
        return (
            0 if e["forced"] else 1,
            -e["news_strength"],
            -abs(change) if change is not None else 1.0,
            -e["tech_strength"],
            e["ticker"],
        )

    evaluated.sort(key=sort_key)

    selected_tickers = set()
    for e in evaluated:
        if e["qualifies"] and len(selected_tickers) < max_deep_analysis:
            selected_tickers.add(e["ticker"])

    for rank, e in enumerate(evaluated):
        e["rank_position"] = rank
        e["selected"] = e["ticker"] in selected_tickers

    selected = [e for e in evaluated if e["selected"]]
    return selected, evaluated
