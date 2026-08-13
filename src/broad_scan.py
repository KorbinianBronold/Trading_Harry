"""Phase 2: Sonnet-Batch-Nachrichtenscan mit Websuche.

Ein Sonnet-Call mit Websuche ueber alle Ueberlebenden aus Phase 1. Liefert je
Ticker {ticker, news_strength (0-3), news_note}. Noch nicht in die Pipeline
verdrahtet -- das macht Task 10, die auch die Rohstoff/Krypto-Filterung vor
dem Aufruf uebernimmt (Spec 6.2, R25). Kein DB-Schreiben -- der Aufrufer
konsumiert die Liste im Speicher."""
import json
import logging
from pathlib import Path

import config
from src.cost_tracker import CostTracker
from src.utils import call_claude, extract_json_blob, WEB_SEARCH_TOOL

log = logging.getLogger("shares_future.broad_scan")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "broad_scan_v1.txt").read_text()

MODEL = config.CLAUDE_MODEL_SONNET

# R27: 500 Ticker x ein Ergebnisobjekt sprengt quick_filters 4096 deutlich --
# die Rechnung dazu steht im Task-8-Report. Ein aktiver Nachrichtentag beim
# vollen 500-Ticker-Ausbau braucht geschaetzt ~15.400 Tokens, ein
# Sicherheitsfaktor fuer ausfuehrlichere Notizen ergibt ~26.000-32.000.
# 24000 gibt echten Spielraum ueber der Worst-Case-Schaetzung.
#
# Korrektur nach Review-Finding: eine fruehere Fassung dieses Kommentars
# behauptete, die Anthropic-SDK verweigere nicht gestreamte Requests oberhalb
# einer Token-Schaetzung mit ValueError. Das stimmt fuer neuere SDK-Versionen,
# aber NICHT fuer das hier gepinnte anthropic==0.42.0 (requirements.txt) --
# verifiziert durch Durchsuchen des installierten Pakets, kein solcher Guard
# vorhanden. Das echte Risiko bei einem nicht gestreamten call_claude()-Call
# (src/utils.py, kein stream=True) ist der httpx-Default-Timeout des Clients
# von 600s (DEFAULT_TIMEOUT in anthropic._constants): eine sehr lange
# Generierung plus mehrere Websuchen koennte ihn reissen; retry_with_backoff
# versucht es dann zweimal erneut und wirft danach unveraendert weiter --
# das ist ein anderer Fehlerfall als das R26-Degradieren unten und wird hier
# bewusst NICHT abgefangen (gleiches Verhalten wie quick_filter/deep_analysis).
# _warn_if_possibly_truncated() macht eine Kappung im Log sichtbar, statt sie
# mit einem echten ruhigen Nachrichtentag zu verwechseln -- ClaudeResult
# traegt keinen stop_reason, output_tokens nahe der Grenze ist das einzige
# verfuegbare Signal.
MAX_TOKENS = 24000
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
    """Loggt eine WARNING, wenn output_tokens nahe MAX_TOKENS liegt (R27-Fix).

    ClaudeResult traegt keinen stop_reason -- output_tokens nahe der Grenze
    ist das einzige verfuegbare Signal fuer eine moeglicherweise abgeschnittene
    Antwort. Ohne diese Warnung ist ein anschliessend komplett auf
    news_strength=0 degradierter Batch (siehe _parse_scan_results) im Log
    nicht von einem echten ruhigen Nachrichtentag zu unterscheiden --
    ausgerechnet an newsreichen Tagen, an denen das Signal am meisten zaehlt."""
    if result.output_tokens >= MAX_TOKENS * TRUNCATION_WARNING_RATIO:
        log.warning(
            f"Phase 2 (broad_scan): output_tokens={result.output_tokens} nahe "
            f"MAX_TOKENS={MAX_TOKENS} -- die Antwort war moeglicherweise "
            f"abgeschnitten. Falls dieser Batch auf news_strength=0 "
            f"degradiert, kann das an einem echten ruhigen Nachrichtentag "
            f"liegen ODER an dieser Kappung -- MAX_TOKENS pruefen/erhoehen, "
            f"wenn das haeufiger auftritt."
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
