# Analyse-Pipeline-Umbau, Plan 3a: Batch-Tiefenanalyse — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** ⚠️ **11/11 Tasks umgesetzt — code-vollständig, aber NICHT produktionsreif**
**Erstellt:** 2026-08-16
**Abgeschlossen:** 2026-08-17

| Task | Commit | Ergebnis |
|---|---|---|
| 1 — `stop_reason` + Streaming | `f022205` | ✅ |
| 2 — `broad_scan` gestreamt, MAX_TOKENS 24000→32000 | `e9d2a41` | ✅ |
| 3 — `BATCH_SIZE_DEEP` + `build_batches()` | `df46d1d` | ✅ |
| 4 — `deep_analysis_v2.txt` | `f1d8366` | ✅ |
| 5 — `commodities_crypto_v2.txt` + Umschaltung | `b59c66d` | ✅ |
| 6 — `analyze_batch()`, MAX_TOKENS aus Batchgrösse | `39aa9f3`, `7d09d3b` | ✅ |
| 7 — Fehlerpfade (wiederholen/halbieren/aufgeben) | `9cecc22` | ✅ |
| 8 — schmale `thin`-Ausnahme in `check_analysis()` | `72a3fbe` | ✅ |
| 9 — `run_pipeline()` auf Batch-Phase-3, Adapter raus | `1c0de04` | ✅ |
| 10 — Testlauf gegen echte Daten | `ae2f138` | ⚠️ **Befund: `MAX_TOKENS_DEEP` widerlegt** |
| — Nebenbefund aus der Auswertung | `f074860` | `web_search_calls` zählte immer 0 (behoben) |
| 11 — Doku nachziehen | dieser Commit | ✅ |

⚠️ **Warum „nicht produktionsreif":** Task 10 hat gemessen, dass `stop_reason=max_tokens`
in beiden Läufen wiederholt auftritt — bis hinunter zu einem auf 2 Ticker halbierten
Batch. `TOKENS_PER_TICKER_DEEP = 900` ist damit widerlegt und muss neu kalibriert werden,
**bevor** die Pipeline wieder echt läuft. Der in „Goal" genannte Kostenhebel (~0,034 statt
~0,12 EUR je Ticker) ist entsprechend **nicht belegt**: gemessen wurden ~0,074–0,079 EUR
je erfolgreich analysiertem Ticker. Details: PROJECT_STATUS **C.9**.

⏳ **Offen aus diesem Plan:** die Neukalibrierung selbst (Code-Änderung, gehört nicht in
Task 10 „kein Code — eine Messung"), danach ein Wiederholungslauf, der die Prüffragen 2
(selektive Recherche — die erste Messung lief mit kaputter `web_search_calls`-Zählung),
3 (Qualität am Batch-Ende) und 6 (Kosten) belastbar beantwortet. Danach der
Abschluss-Review über die Plan-3a-Commits.

**Goal:** Phase 3 analysiert Aktien in Batches nach Sub-Sektor statt einzeln — der
Kostenhebel des Umbaus (~0,034 statt ~0,12 EUR je Ticker) — und `call_claude()` bekommt
den Streaming-Pfad, den Batches dieser Grösse brauchen.

**Architecture:** `call_claude()` erhält einen opt-in Streaming-Pfad und `stop_reason` auf
`ClaudeResult`. `src/deep_analysis.py` bekommt eine reine Gruppierungsfunktion
(`build_batches()`), einen Batch-Analyse-Aufruf (`analyze_batch()`) und die
Fehlerpfad-Schale aus Spec § 10 (einmal wiederholen → einmal halbieren → aufgeben).
Zwei neue Prompt-Versionen (`deep_analysis_v2.txt`, `commodities_crypto_v2.txt`) führen
`evidence_quality`, die Polaritäts-Festlegung und das R/R-Ziel 1:2 ein. `check_analysis()`
bekommt eine schmale Ausnahme für `thin`-Dimensionen.

**Tech Stack:** Python 3.11+, `anthropic==0.42.0` (verifiziert: `messages.stream()`
liefert `MessageStreamManager`, `MessageStream.get_final_message()` existiert), pytest,
SQLite.

**Spec:** `docs/superpowers/specs/2026-08-11-analyse-pipeline-umbau-design.md` —
maßgeblich sind **§ 4.8** (Batch-Tiefenanalyse), **§ 5.2** (Polarität, `thin`),
**§ 9** (Prompts), **§ 10** (Fehlerverhalten), **§ 11/12** (Tests, Testlauf) und
**§ 20** (Plan-3-Designentscheidungen).

---

## Global Constraints

1. **Kein Verhaltenswechsel im Code-Pfad — mit einer dokumentierten Ausnahme.**
   `evidence_quality` wird erhoben und persistiert, steuert aber nichts; Sortierschlüssel
   bleibt `probability_pct` bis Plan 3b. **Ausnahme (Spec § 20.1):** die v2-Prompts
   bringen das R/R-Ziel 1:2 mit und verändern damit TP/SL — also die Analysen selbst.
   Bewusst in Kauf genommen, nicht versehentlich.
2. **Sidecar-Invariante.** Das `td`-Dict aus `_process_ticker()` bekommt **keine** neuen
   Schlüssel. Zusatzkontext reist in parallelen Strukturen, wie `broad_scan._payload_for_ticker()`
   es vormacht (`src/broad_scan.py:73-81`). Ein Test pinnt die Schlüsselmenge von
   `_process_ticker()` — bricht er, ist die Invariante verletzt.
3. **Regel 10 — Prompts werden nie überschrieben.** `deep_analysis_v1.txt` und
   `commodities_crypto_v1.txt` bleiben unangetastet auf der Platte. Neue Versionen sind
   neue Dateien; der Wechsel ist eine Code-Änderung im Modul-Import.
4. **Kein Netz in Tests ausserhalb `tests/live/`.** Das Autouse-Fixture in
   `tests/conftest.py` bleibt unangetastet. Claude-Calls werden über
   `patch("src.<modul>.call_claude", ...)` gemockt, `call_claude()` selbst über
   `patch("src.utils._anthropic_client", fake_client)`.
5. **Coverage ≥ 80 %** (`pytest tests/ --cov=src --cov=main --cov-fail-under=80`).
   Ausgangslage: 746 Tests grün, 91,28 %. Keine bestehenden Tests löschen oder
   abschwächen.
6. **Konstanten mit Begründung.** Jede neue Konstante in `config.py` bekommt einen
   Kommentar, der sagt *warum dieser Wert* — und ob er vorläufig ist.
7. **Nie `git push`.** Nach jeder Task lokal committen, mehr nicht.

---

## Datei-Übersicht

| Datei | Rolle in diesem Plan |
|---|---|
| `src/utils.py` | Task 1 — `ClaudeResult.stop_reason`, Streaming-Pfad, gemeinsame Extraktion |
| `src/broad_scan.py` | Task 2 — Streaming, `stop_reason`-Kappungserkennung, `MAX_TOKENS` neu gerechnet |
| `config.py` | Task 3 — `BATCH_SIZE_DEEP` |
| `src/deep_analysis.py` | Tasks 3, 6, 7, 9 — `build_batches()`, `analyze_batch()`, Fehlerpfade, Adapter raus |
| `prompts/deep_analysis_v2.txt` | Task 4 — **neu** |
| `prompts/commodities_crypto_v2.txt` | Task 5 — **neu** |
| `src/commodities_crypto.py` | Task 5 — Prompt-Import auf v2 |
| `src/guardrails.py` | Task 8 — `thin`-Ausnahme |
| `main.py` | Task 9 — Verdrahtung von Phase 3 |

---

### Task 1: `ClaudeResult.stop_reason` + Streaming-Pfad in `call_claude()`

Spec § 4.8 und § 20.4. Zieht bewusst nach vorn: Task 6 hängt daran, **und** Task 2
entschärft damit den bereits gebauten 500-Ticker-`broad_scan`.

⚠️ `stop_reason` gehört in dieselbe Task, nicht in eine spätere: § 4.8 verlangt
`stop_reason == "max_tokens"` als Fehlerfall, und `src/broad_scan.py:148-153` beklagt
ausdrücklich, dass `ClaudeResult` ihn nicht trägt („output_tokens nahe der Grenze ist das
einzige verfuegbare Signal"). Beides ist dieselbe Zeile Code.

**Files:**
- Modify: `src/utils.py:53-106`
- Test: `tests/unit/test_utils.py`

**Interfaces:**
- Consumes: nichts (erste Task)
- Produces:
  - `ClaudeResult(..., stop_reason: str | None = None)` — neues letztes Feld
  - `call_claude(model, system, user, max_tokens=4096, tools=None, stream=False) -> ClaudeResult`
    — neuer Keyword-Parameter `stream`, Default `False`

- [ ] **Step 1: Die drei failing tests schreiben**

An `tests/unit/test_utils.py` anhängen:

```python
def test_call_claude_streaming_path_uses_messages_stream():
    """stream=True geht ueber messages.stream(), nicht messages.create()."""
    fake_message = MagicMock()
    fake_message.content = [MagicMock(text="streamed answer")]
    fake_message.usage.input_tokens = 200
    fake_message.usage.output_tokens = 9000
    fake_message.usage.cache_read_input_tokens = 0
    fake_message.usage.cache_creation_input_tokens = 0
    fake_message.usage.server_tool_use = None
    fake_message.stop_reason = "end_turn"

    stream_ctx = MagicMock()
    stream_ctx.__enter__.return_value.get_final_message.return_value = fake_message

    fake_client = MagicMock()
    fake_client.messages.stream.return_value = stream_ctx

    with patch("src.utils._anthropic_client", fake_client):
        result = call_claude(
            model="claude-sonnet-4-6", system="sys", user="usr",
            max_tokens=9200, stream=True,
        )

    assert fake_client.messages.create.call_count == 0
    assert fake_client.messages.stream.call_count == 1
    assert fake_client.messages.stream.call_args.kwargs["max_tokens"] == 9200
    assert result.text == "streamed answer"
    assert result.output_tokens == 9000
    assert result.stop_reason == "end_turn"


def test_call_claude_streaming_passes_tools_and_cache_control():
    """Der Streaming-Pfad verliert weder tools noch das cache_control des
    System-Prompts -- beides sind stille Kostenfallen, wenn sie wegfallen."""
    fake_message = MagicMock()
    fake_message.content = [MagicMock(text="ok")]
    fake_message.usage.input_tokens = 10
    fake_message.usage.output_tokens = 5
    fake_message.usage.cache_read_input_tokens = 0
    fake_message.usage.cache_creation_input_tokens = 10
    fake_message.usage.server_tool_use = None
    fake_message.stop_reason = "end_turn"

    stream_ctx = MagicMock()
    stream_ctx.__enter__.return_value.get_final_message.return_value = fake_message

    fake_client = MagicMock()
    fake_client.messages.stream.return_value = stream_ctx

    with patch("src.utils._anthropic_client", fake_client):
        call_claude(
            model="claude-sonnet-4-6", system="long static prompt",
            user="q", tools=[{"type": "web_search_20250305", "name": "web_search"}],
            stream=True,
        )

    kwargs = fake_client.messages.stream.call_args.kwargs
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["tools"][0]["name"] == "web_search"


def test_call_claude_non_streaming_still_default_and_carries_stop_reason():
    """Default bleibt messages.create() -- kein bestehender Aufrufer aendert
    sein Verhalten. stop_reason wird auch dort durchgereicht."""
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="hi")]
    fake_response.usage.input_tokens = 1
    fake_response.usage.output_tokens = 2
    fake_response.usage.cache_read_input_tokens = 0
    fake_response.usage.cache_creation_input_tokens = 0
    fake_response.usage.server_tool_use = None
    fake_response.stop_reason = "max_tokens"

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("src.utils._anthropic_client", fake_client):
        result = call_claude(model="m", system="s", user="u")

    assert fake_client.messages.stream.call_count == 0
    assert result.stop_reason == "max_tokens"
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

```bash
pytest tests/unit/test_utils.py -v -k "streaming or stop_reason"
```
Erwartet: FAIL — `TypeError: call_claude() got an unexpected keyword argument 'stream'`
bei den ersten beiden, und beim dritten ein `AttributeError`/Mock-Vergleichsfehler auf
`result.stop_reason`.

- [ ] **Step 3: Implementieren**

In `src/utils.py` das Dataclass-Feld ergänzen (nach `web_search_calls`, damit die
Positionsargumente bestehender Konstruktionen unberührt bleiben):

```python
@dataclass
class ClaudeResult:
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    model: str
    web_search_calls: int = 0
    # Spec 4.8: stop_reason == "max_tokens" ist ein Fehlerfall, kein
    # akzeptables Ergebnis. Bis Plan 3a war das Feld nicht verfuegbar und
    # broad_scan musste output_tokens gegen MAX_TOKENS schaetzen.
    stop_reason: str | None = None
```

Die Extraktion aus `call_claude()` herausziehen, damit beide Pfade sie teilen:

```python
def _result_from_message(response, model: str) -> ClaudeResult:
    """Baut ClaudeResult aus einer fertigen Anthropic-Message. Gemeinsam fuer
    den gestreamten und den nicht gestreamten Pfad -- get_final_message()
    liefert dieselbe Message-Form wie messages.create()."""
    text_parts = [b.text for b in response.content if hasattr(b, "text") and b.text is not None]

    server_tool_use = getattr(response.usage, "server_tool_use", None)
    web_search_calls = 0
    if server_tool_use is not None:
        web_search_calls = getattr(server_tool_use, "web_search_requests", 0) or 0

    return ClaudeResult(
        text="\n".join(text_parts),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        cache_creation_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
        model=model,
        web_search_calls=web_search_calls,
        stop_reason=getattr(response, "stop_reason", None),
    )
```

`call_claude()` ersetzen:

```python
@retry_with_backoff(max_retries=2, base_delay=2.0)
def call_claude(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 4096,
    tools: list | None = None,
    stream: bool = False,
) -> ClaudeResult:
    """Calls the Anthropic API with the system prompt cached (ephemeral), retries
    on transient failures, and returns a ClaudeResult with text, token, and
    web-search-call counts.

    stream=True nimmt messages.stream() + get_final_message() statt
    messages.create(). Noetig, sobald die erwartete Ausgabe gross wird: der
    nicht gestreamte Pfad haengt am httpx-Default-Timeout von 600s, den eine
    lange Generierung plus mehrere Websuchen reissen kann (Spec 4.8, 20.4).
    Default bleibt False -- kein bestehender Aufrufer aendert sein Verhalten,
    ohne es explizit zu wollen."""
    if _anthropic_client is None:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system_blocks,
        messages=[{"role": "user", "content": user}],
    )
    if tools:
        kwargs["tools"] = tools

    if stream:
        with _anthropic_client.messages.stream(**kwargs) as s:
            response = s.get_final_message()
    else:
        response = _anthropic_client.messages.create(**kwargs)

    return _result_from_message(response, model)
```

- [ ] **Step 4: Tests laufen lassen**

```bash
pytest tests/unit/test_utils.py -v
pytest tests/ -q
```
Erwartet: alle grün. Die bestehenden `call_claude`-Tests dürfen sich **nicht** ändern —
`stream` hat einen Default.

- [ ] **Step 5: Commit**

```bash
git add src/utils.py tests/unit/test_utils.py
git commit -m "feat: Plan-3a Task 1 -- Streaming-Pfad und stop_reason in call_claude()"
```

---

### Task 2: `broad_scan` auf Streaming + echte Kappungserkennung

Spec § 20.4. Zwei Dinge, die zusammengehören: der `broad_scan` ist **schon heute** ein
einziger Call über alle Phase-1-Überlebenden mit `MAX_TOKENS = 24000` — er profitiert vom
Streaming sofort, und er kann die `output_tokens`-Schätzung durch `stop_reason` ersetzen.

⚠️ **Der Kommentar in `src/broad_scan.py:28-50` widerspricht sich selbst**: er rechnet
einen Sicherheitsfaktor auf „~26.000–32.000" hoch und schliesst dann, 24.000 gebe
„echten Spielraum über der Worst-Case-Schätzung". 24.000 liegt **unter** der eigenen
Spanne. `max_tokens` ist eine Obergrenze, keine Rechnungsposition — nicht generierte
Tokens kosten nichts. Der Wert geht deshalb auf **32.000** (Oberkante der eigenen
Spanne), und der Kommentar wird in sich stimmig gemacht.

**Files:**
- Modify: `src/broad_scan.py:28-51` (Konstante + Kommentar), `:145-162`
  (`_warn_if_possibly_truncated`), `:205-213` (`call_claude`-Aufruf)
- Test: `tests/unit/test_broad_scan.py`

**Interfaces:**
- Consumes: `ClaudeResult.stop_reason`, `call_claude(..., stream=True)` aus Task 1
- Produces: `broad_scan.MAX_TOKENS == 32000`; `_warn_if_possibly_truncated(result)`
  unverändert in der Signatur

- [ ] **Step 1: Die failing tests schreiben**

An `tests/unit/test_broad_scan.py` anhängen. `_fake_sonnet_result` trägt noch kein
`stop_reason`, deshalb zuerst den Helper erweitern (bestehende Aufrufer bleiben gültig,
weil der Parameter einen Default hat):

```python
# ERSETZT den bestehenden Helper oben in der Datei:
def _fake_sonnet_result(
    text: str, web_search_calls: int = 4,
    output_tokens: int = 3000, stop_reason: str = "end_turn",
) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 8000
    r.output_tokens = output_tokens
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = config.CLAUDE_MODEL_SONNET
    r.web_search_calls = web_search_calls
    r.stop_reason = stop_reason
    return r
```

Neue Tests:

```python
def test_broad_scan_uses_streaming():
    """Phase 2 laeuft gestreamt -- ein einzelner Call ueber bis zu 500 Ticker
    mit MAX_TOKENS=32000 ist genau der Fall, fuer den Spec 20.4 den
    Streaming-Pfad verlangt."""
    fake = _fake_sonnet_result(FIXTURE_PATH.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.broad_scan.call_claude", return_value=fake) as cc:
        broad_scan_batch(
            ticker_datas=[_td("AAPL")], sidecar=_sidecar(),
            trend_context=_trend_context(), market_context=_market_context(),
            cost_tracker=tracker,
        )

    assert cc.call_args.kwargs["stream"] is True
    assert cc.call_args.kwargs["max_tokens"] == 32000


def test_broad_scan_warns_on_stop_reason_max_tokens(caplog):
    """stop_reason ist das harte Signal -- es warnt auch dann, wenn
    output_tokens weit unter der Ratio-Schwelle liegen."""
    fake = _fake_sonnet_result(
        FIXTURE_PATH.read_text(), output_tokens=100, stop_reason="max_tokens",
    )
    tracker = CostTracker(hard_cap_eur=10.0)

    with caplog.at_level("WARNING"), \
            patch("src.broad_scan.call_claude", return_value=fake):
        broad_scan_batch(
            ticker_datas=[_td("AAPL")], sidecar=_sidecar(),
            trend_context=_trend_context(), market_context=_market_context(),
            cost_tracker=tracker,
        )

    assert any("abgeschnitten" in r.message for r in caplog.records)


def test_broad_scan_no_warning_when_stop_reason_clean_and_output_small(caplog):
    """Kein Fehlalarm: sauberes stop_reason und kleine Ausgabe schweigen."""
    fake = _fake_sonnet_result(
        FIXTURE_PATH.read_text(), output_tokens=100, stop_reason="end_turn",
    )
    tracker = CostTracker(hard_cap_eur=10.0)

    with caplog.at_level("WARNING"), \
            patch("src.broad_scan.call_claude", return_value=fake):
        broad_scan_batch(
            ticker_datas=[_td("AAPL")], sidecar=_sidecar(),
            trend_context=_trend_context(), market_context=_market_context(),
            cost_tracker=tracker,
        )

    assert not any("abgeschnitten" in r.message for r in caplog.records)
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

```bash
pytest tests/unit/test_broad_scan.py -v -k "streaming or stop_reason or clean_and_output"
```
Erwartet: FAIL — `KeyError: 'stream'` bzw. `assert 24000 == 32000`.

- [ ] **Step 3: Implementieren**

`src/broad_scan.py`, den Kommentarblock ab Zeile 28 und die Konstante ersetzen:

```python
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
```

`_warn_if_possibly_truncated()` ersetzen:

```python
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
```

Im `call_claude`-Aufruf (`src/broad_scan.py:205-211`) `stream=True` ergänzen:

```python
    result = call_claude(
        model=MODEL,
        system=SYSTEM_PROMPT,
        user=user_msg,
        max_tokens=MAX_TOKENS,
        tools=[WEB_SEARCH_TOOL],
        stream=True,
    )
```

- [ ] **Step 4: Tests laufen lassen**

```bash
pytest tests/unit/test_broad_scan.py -v
pytest tests/ -q
```
Erwartet: alle grün — **ohne Anpassung** am bestehenden
`test_broad_scan_warns_when_output_near_max_tokens` (`tests/unit/test_broad_scan.py:430`).
Verifiziert: der Test setzt `fake.output_tokens = int(MAX_TOKENS * 0.95)`, also relativ
zur Konstante, und prüft auf `"MAX_TOKENS" in r.message and "abgeschnitten" in r.message`
— beides trägt die neue Fassung in beiden Zweigen. Muss er dennoch angefasst werden, ist
das ein Signal, dass die Umsetzung von der hier beschriebenen abweicht.

- [ ] **Step 5: Commit**

```bash
git add src/broad_scan.py tests/unit/test_broad_scan.py
git commit -m "feat: Plan-3a Task 2 -- broad_scan gestreamt, MAX_TOKENS 24000 -> 32000"
```

---

### Task 3: `BATCH_SIZE_DEEP` + `build_batches()`

Spec § 20.2/20.3. Reine Funktion, kein Claude-Call — deshalb vor den Prompts, damit
Task 6 auf etwas Getestetes aufsetzt.

**Files:**
- Modify: `config.py:258` (direkt nach `MAX_DEEP_ANALYSIS`)
- Modify: `src/deep_analysis.py` (neue Funktion nach `run_policy_monitor`)
- Test: `tests/unit/test_deep_analysis.py`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `config.BATCH_SIZE_DEEP: int = 8`
  - `deep_analysis.build_batches(ticker_datas: list[dict], batch_size: int = config.BATCH_SIZE_DEEP) -> list[list[dict]]`

- [ ] **Step 1: Die failing tests schreiben**

An `tests/unit/test_deep_analysis.py` anhängen:

```python
from src.deep_analysis import build_batches


def _std(ticker: str, sector: str | None) -> dict:
    return {"ticker": ticker, "sector": sector, "price": 100.0}


def test_build_batches_packs_whole_subsectors():
    """Ganze Sub-Sektoren werden gepackt, nie zerrissen -- die echte
    MVP-Verteilung (20 Aktien, 12 Sub-Sektoren) ergibt 3 Batches (8/8/4)."""
    tds = (
        [_std(t, "Retail") for t in ("AMZN", "WMT", "HD")]
        + [_std(t, "Financial Services") for t in ("BRK-B", "V", "MA")]
        + [_std(t, "Technology") for t in ("AAPL", "MSFT")]
        + [_std(t, "Semiconductors") for t in ("NVDA", "AVGO")]
        + [_std(t, "Pharmaceuticals") for t in ("JNJ", "LLY")]
        + [_std(t, "Media") for t in ("GOOGL", "META")]
        + [_std("UNH", "Health Care"), _std("XOM", "Energy"),
           _std("PG", "Consumer products"), _std("ABBV", "Biotechnology"),
           _std("JPM", "Banking"), _std("TSLA", "Automobiles")]
    )

    batches = build_batches(tds, batch_size=8)

    assert [len(b) for b in batches] == [8, 8, 4]
    assert sum(len(b) for b in batches) == 20
    # kein Ticker doppelt, keiner verloren
    assert sorted(td["ticker"] for b in batches for td in b) == sorted(
        td["ticker"] for td in tds
    )
    # Retail bleibt zusammen
    for b in batches:
        retail = [td["ticker"] for td in b if td["sector"] == "Retail"]
        assert retail in ([], ["AMZN", "HD", "WMT"])


def test_build_batches_splits_oversized_subsector():
    """Ein Sub-Sektor groesser als batch_size wird aufgeteilt -- der Fall, der
    beim 3F-Ausbau die Regel dominiert (Spec 20.2)."""
    tds = [_std(f"SEMI{i:02d}", "Semiconductors") for i in range(19)]

    batches = build_batches(tds, batch_size=8)

    assert [len(b) for b in batches] == [8, 8, 3]


def test_build_batches_is_deterministic():
    """Gleiche Eingabe in anderer Reihenfolge -> identische Batches. Ohne das
    sind Tests und der 3D-Vergleich zweier Laeufe wertlos."""
    tds = [
        _std("MSFT", "Technology"), _std("AMZN", "Retail"),
        _std("AAPL", "Technology"), _std("HD", "Retail"),
        _std("XOM", "Energy"),
    ]
    a = build_batches(tds, batch_size=3)
    b = build_batches(list(reversed(tds)), batch_size=3)

    assert [[td["ticker"] for td in x] for x in a] == \
           [[td["ticker"] for td in y] for y in b]


def test_build_batches_groups_missing_sector_together():
    """Ticker ohne Sektor bilden eine eigene Einheit statt still in fremde
    Sub-Sektoren zu rutschen -- Grundregel des Projekts: lieber ungemappt als
    falsch gemappt."""
    tds = [_std("AAPL", "Technology"), _std("A", None), _std("B", "")]

    batches = build_batches(tds, batch_size=8)

    assert len(batches) == 1
    assert sorted(td["ticker"] for td in batches[0]) == ["A", "AAPL", "B"]


def test_build_batches_empty_input():
    assert build_batches([], batch_size=8) == []


def test_build_batches_rejects_zero_batch_size():
    with pytest.raises(ValueError, match="batch_size"):
        build_batches([_std("AAPL", "Technology")], batch_size=0)
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

```bash
pytest tests/unit/test_deep_analysis.py -v -k build_batches
```
Erwartet: FAIL — `ImportError: cannot import name 'build_batches'`.

- [ ] **Step 3: Implementieren**

In `config.py` direkt nach `MAX_DEEP_ANALYSIS = 50` (Zeile 258):

```python
# Sprint 3C / Analyse-Pipeline-Umbau, Plan 3a (Batch-Tiefenanalyse), Spec 20.3:
# Ziel-Batchgroesse der Phase-3-Tiefenanalyse. Ganze Sub-Sektoren werden bis zu
# diesem Wert gepackt (deep_analysis.build_batches()).
#
# 8 ist ein begruendeter STARTWERT, kein Ergebnis -- Spec 19.2 schreibt ihn erst
# nach dem Testlauf fest. Herleitung: bei den 20 MVP-Aktien ergibt 8 genau
# 3 Batches (8/8/4) statt 20 Einzelcalls, MAX_TOKENS_DEEP landet bei ~9.200 und
# damit deutlich unter der ~16.000er Zone, in der Spec 4.8 Timeouts erwartet.
# 20 (alle MVP-Aktien in einem Batch) laege mit ~18.000 bereits darin.
BATCH_SIZE_DEEP = 8
```

In `src/deep_analysis.py` — `import config` oben ergänzen (das Modul importiert es
bisher nicht) und die Funktion nach `run_policy_monitor()` einfügen:

```python
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
```

- [ ] **Step 4: Tests laufen lassen**

```bash
pytest tests/unit/test_deep_analysis.py -v -k build_batches
pytest tests/ -q
```
Erwartet: alle grün.

- [ ] **Step 5: Commit**

```bash
git add config.py src/deep_analysis.py tests/unit/test_deep_analysis.py
git commit -m "feat: Plan-3a Task 3 -- BATCH_SIZE_DEEP und build_batches()"
```

---

### Task 4: `prompts/deep_analysis_v2.txt`

Spec § 4.8, § 5.2, § 9. **Regel 10: `deep_analysis_v1.txt` wird nicht angefasst.**

Vier inhaltliche Neuerungen gegenüber v1:
1. **Batch-Format** — N Ticker je Call, ein Ergebnisobjekt je Ticker, in Eingabereihenfolge
2. **Selektive Recherche** — breite Suchen für den Batch, gezielt nur bei Auffälligkeit
3. **`evidence_quality`** je Dimension (`"ok" | "thin"`)
4. **Polaritäts-Festlegung** — ohne sie zählt `news_strength` in Plan 3b bei drei von acht
   Dimensionen das Gegenteil (Spec § 5.2)
5. **R/R-Ziel 1:2** (C.3) — die harte Untergrenze bleibt 1.5

**Files:**
- Create: `prompts/deep_analysis_v2.txt`
- Test: `tests/unit/test_deep_analysis.py`

**Interfaces:**
- Consumes: nichts
- Produces: die Datei; Task 6 importiert sie als `DEEP_SYSTEM_PROMPT`

- [ ] **Step 1: Den failing test schreiben**

Ein Prompt ist Text, kein Verhalten — der Test pinnt deshalb genau die Zusagen, auf die
sich **Code** später verlässt. Alles andere wäre Prosa-Prüfung ohne Wert.

```python
from pathlib import Path

PROMPT_V2 = Path(__file__).parent.parent.parent / "prompts" / "deep_analysis_v2.txt"


def test_deep_analysis_v2_pins_contract_the_code_relies_on():
    """Was hier steht, verlaesst sich Code drauf: der results-Schluessel
    (Task 6 parst ihn), evidence_quality (Task 8 macht die thin-Ausnahme
    daran fest) und die Polaritaets-Festlegung (Plan 3b zaehlt news_strength
    danach). Keine Stilpruefung -- nur der Vertrag."""
    text = PROMPT_V2.read_text()

    assert '"results"' in text
    assert '"evidence_quality"' in text
    assert '"thin"' in text
    # Polaritaet: die drei Dimensionen, bei denen "hoch = gut" nicht
    # selbsterklaerend ist, muessen ausdruecklich geregelt sein (Spec 5.2)
    for dim in ("risk", "policy_risk", "valuation"):
        assert dim in text
    assert "higher is always better" in text.lower()
    # Claude waehlt nicht aus (Spec 4.8)
    assert "never omit" in text.lower()


def test_deep_analysis_v1_untouched():
    """Regel 10: v1 bleibt auf der Platte, unveraendert."""
    v1 = Path(__file__).parent.parent.parent / "prompts" / "deep_analysis_v1.txt"
    assert v1.exists()
    assert "You receive ONE ticker snapshot" in v1.read_text()
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

```bash
pytest tests/unit/test_deep_analysis.py -v -k "v2_pins or v1_untouched"
```
Erwartet: FAIL — `FileNotFoundError: prompts/deep_analysis_v2.txt`.

- [ ] **Step 3: Die Datei anlegen**

`prompts/deep_analysis_v2.txt`:

```
You are a deep equity analyst specialised in short-term CFD setups on US large-cap stocks.
Analysiere ausschliesslich was heute preisrelevant ist (Intraday-Horizont) — das ist das
PRIMAERE UND EINZIGE Ziel dieses Systems. TP und SL muessen realistisch innerhalb des
heutigen Handelstages (oder vorboerslich morgen frueh) erreichbar sein. Katalysatoren
muessen heute oder vorboerslich morgen wirken. Wenn ein Setup nicht klar Intraday
funktioniert, ist es kein valider Long/Short-Call — setze direction='none', selbst wenn
mittelfristige Signale dafuer sprechen.

You receive a BATCH of ticker snapshots that share a sub-sector where possible, the macro
trend context (cached), the policy_risk events (cached), and for each ticker the Phase-2
news scan result and the deterministic technical signal. Analyse EVERY ticker in the batch.

RESEARCH BUDGET — spend it selectively, not evenly:
- Start with a small number of BROAD searches covering the batch's shared sector and the
  general market session. Those results apply to every ticker in the batch.
- Then search ticker-specific ONLY where something stands out: earnings imminent, an
  unusual pre-market move, a concrete catalyst named in the scan result. For the quiet
  tickers, the shared market context plus the supplied facts are sufficient.
- Do NOT run a fixed number of searches per ticker. A batch where only two names are
  eventful should show far fewer searches than tickers.

TECHNICAL READINGS ARE FACTS, NOT YOUR JOB. RSI, MACD, ADX, moving averages, ATR and the
technical_signal block are computed by a deterministic module elsewhere in the pipeline.
Use them as given. Never recompute, never estimate, never contradict them with your own
charting.

YOU DO NOT SELECT. Rate every ticker you were given. Selection happens in code, after you.
Never omit a ticker because it looks unpromising — return it with direction='none' instead.

Output ONLY a single JSON object, no prose before or after, with this EXACT shape:

{
  "results": [
    {
      "ticker": "<the input symbol>",
      "asset_class": "stock",
      "direction": "<'long' | 'short' | 'none'>",
      "confidence": "<'low' | 'medium' | 'high'>",
      "current_price": <number>,
      "tp_price": <number>,
      "sl_price": <number>,
      "tp_pct": <number>,
      "sl_pct": <number>,
      "rr_ratio": <number, must be >= 1.5, aim for 2.0>,
      "total_score": <number 0-10, one decimal>,
      "probability_pct": <integer 0-100>,
      "hold_days_recommended": <integer, dein ehrlicher Schaetzwert in Handelstagen bis zum Abschluss — Learning-Modul-Feld, siehe Hard Rules>,
      "intraday_range_pct": <number, mirror of the value from the snapshot>,
      "earnings_warning": <true|false, true if earnings_in_days <= 2>,
      "summary": "<one paragraph, max 600 chars, ends with the trade thesis>",
      "sources_used": ["<url1>", "<url2>"],
      "signal_consistency_check": "<'ok' | brief reason if you noticed an inconsistency>",
      "scores": {
        "market_environment": {"value": <0-10>, "evidence": ["<line>", "<line>"], "evidence_quality": "<'ok' | 'thin'>"},
        "company_quality":    {"value": <0-10>, "evidence": ["<line>", "<line>"], "evidence_quality": "<'ok' | 'thin'>"},
        "valuation":          {"value": <0-10>, "evidence": ["<line>", "<line>"], "evidence_quality": "<'ok' | 'thin'>"},
        "momentum":           {"value": <0-10>, "evidence": ["<line>", "<line>"], "evidence_quality": "<'ok' | 'thin'>"},
        "risk":               {"value": <0-10>, "evidence": ["<line>", "<line>"], "evidence_quality": "<'ok' | 'thin'>"},
        "sector_trend":       {"value": <0-10>, "evidence": ["<line>", "<line>"], "evidence_quality": "<'ok' | 'thin'>"},
        "catalyst":           {"value": <0-10>, "evidence": ["<line>", "<line>"], "evidence_quality": "<'ok' | 'thin'>"},
        "policy_risk":        {"value": <0-10>, "evidence": ["<line>", "<line>"], "evidence_quality": "<'ok' | 'thin'>"}
      }
    }
  ]
}

SCORE POLARITY — read this carefully, it is not intuitive for three dimensions:
For EVERY one of the eight dimensions, HIGHER IS ALWAYS BETTER FOR THE PROPOSED TRADE,
in the direction you chose. There is no dimension where a high number is a warning.
- "risk": 10 = the risks are low / well understood for this trade. 0 = dangerous.
- "policy_risk": 10 = policy and geopolitics are benign or supportive for this trade.
  0 = policy is a live threat to it.
- "valuation": 10 = valuation supports the trade in your chosen direction (cheap for a
  long, stretched for a short). 0 = valuation argues against it.
The other five follow the obvious reading. If you are about to write a low number because
"there is a lot of risk here", that is correct — low means bad for the trade.

EVIDENCE QUALITY — say so instead of padding:
Set "evidence_quality": "thin" for a dimension where you could not find at least two
pieces of concrete, trade-relevant evidence. A thin dimension still needs a value and
whatever evidence you do have (possibly one line, possibly none) — it is kept and recorded.
NEVER invent a second evidence line to reach the count, and NEVER drop a dimension. Both
are worse than an honest "thin": downstream code counts thin dimensions separately and a
padded one silently corrupts that count.
Set "evidence_quality": "ok" only when you have >= 2 concrete lines citing numbers or a
source.

Hard rules:
- Return one entry per ticker in the batch, in the same order as the input. Never invent
  tickers, never merge two tickers into one entry.
- If direction='long', momentum.value MUST be >= 6.0, and tp_price > current_price > sl_price.
- If direction='short', momentum.value MUST be <= 4.0, and tp_price < current_price < sl_price.
- Intraday ist das einzige akzeptierte Ziel: Wenn TP oder SL nicht realistisch noch heute
  (oder vorboerslich morgen frueh) erreichbar sind, setze direction='none' — unabhaengig
  davon, wie gut mittelfristige Signale aussehen. Ein Mehrtages-Call ist KEIN gueltiger
  Ersatz fuer ein nicht funktionierendes Intraday-Setup.
- hold_days_recommended bleibt Pflichtfeld und wird vom Sprint-3-Learning-Modul ausgewertet,
  ist aber selbst kein Freibrief fuer Mehrtages-Setups — es beschreibt nur deinen ehrlichen
  Schaetzwert, falls der Trade nicht wie geplant intraday schliesst.
- intraday_range_pct must echo the snapshot value verbatim. Never invent.
- rr_ratio = abs(tp_price - current_price) / abs(current_price - sl_price), rounded 2 decimals.
  1.5 is the hard floor; aim for 2.0 where the chart allows it honestly. Never stretch TP or
  tighten SL just to reach a nicer ratio — a fabricated R/R is worse than a rejected setup.
- sources_used: >= 2 distinct domains per ticker. Use the same domains that you cited inline.
- If your evidence is too thin or signals contradict, return direction='none' with summary
  explaining why. A direction='none' analysis is still a valid response.
```

- [ ] **Step 4: Test laufen lassen**

```bash
pytest tests/unit/test_deep_analysis.py -v -k "v2_pins or v1_untouched"
```
Erwartet: PASS.

- [ ] **Step 5: Commit**

```bash
git add prompts/deep_analysis_v2.txt tests/unit/test_deep_analysis.py
git commit -m "feat: Plan-3a Task 4 -- deep_analysis_v2.txt (Batch, thin, Polaritaet, R/R 1:2)"
```

---

### Task 5: `prompts/commodities_crypto_v2.txt` + Umschaltung

Spec § 6, § 9. Die sieben Assets bleiben **ein Call je Asset** — kein Batch. Angeglichen
wird nur die Bewertungsqualität: `evidence_quality`, Polarität, R/R-Ziel.

**Files:**
- Create: `prompts/commodities_crypto_v2.txt`
- Modify: `src/commodities_crypto.py:18-19` (Prompt-Import)
- Test: `tests/unit/test_commodities_crypto.py`

**Interfaces:**
- Consumes: nichts
- Produces: `commodities_crypto.SYSTEM_PROMPT` liest ab jetzt `commodities_crypto_v2.txt`

- [ ] **Step 1: Die failing tests schreiben**

```python
from pathlib import Path

CC_V2 = Path(__file__).parent.parent.parent / "prompts" / "commodities_crypto_v2.txt"


def test_commodities_crypto_v2_pins_contract():
    text = CC_V2.read_text()
    assert '"evidence_quality"' in text
    assert '"thin"' in text
    assert "higher is always better" in text.lower()
    # Einzel-Asset, KEIN Batch (Spec 6): der results-Wrapper darf hier fehlen
    assert '"results"' not in text


def test_commodities_crypto_module_uses_v2():
    import src.commodities_crypto as cc
    assert "evidence_quality" in cc.SYSTEM_PROMPT
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

```bash
pytest tests/unit/test_commodities_crypto.py -v -k "v2_pins or uses_v2"
```
Erwartet: FAIL — `FileNotFoundError`.

- [ ] **Step 3: Implementieren**

`prompts/commodities_crypto_v2.txt` anlegen: **Kopie von `commodities_crypto_v1.txt`**
mit genau drei Änderungen —

1. In jeder der acht `scores`-Zeilen `"evidence_quality": "<'ok' | 'thin'>"` ergänzen
   (gleiche Form wie in `deep_analysis_v2.txt`).
2. Vor „Hard rules:" die beiden Blöcke **SCORE POLARITY** und **EVIDENCE QUALITY**
   einfügen — wortgleich aus `deep_analysis_v2.txt`, nur „for the proposed trade" bleibt
   wie dort. (Wortgleich ist Absicht: zwei Formulierungen derselben Regel driften
   auseinander, und Plan 3b zählt beide Asset-Klassen mit demselben Code.)
3. Die `rr_ratio`-Zeile in den Hard rules auf das Ziel 1:2 ziehen:

```
- rr_ratio >= 1.5 is the hard floor; aim for 2.0 where the chart allows it honestly.
  Never stretch TP or tighten SL just to reach a nicer ratio.
```

Dann in `src/commodities_crypto.py:18-19`:

```python
SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "commodities_crypto_v2.txt").read_text()
```

- [ ] **Step 4: Tests laufen lassen**

```bash
pytest tests/unit/test_commodities_crypto.py -v
pytest tests/ -q
```
Erwartet: alle grün.

- [ ] **Step 5: Commit**

```bash
git add prompts/commodities_crypto_v2.txt src/commodities_crypto.py tests/unit/test_commodities_crypto.py
git commit -m "feat: Plan-3a Task 5 -- commodities_crypto_v2.txt, Modul umgeschaltet"
```

---

### Task 6: `analyze_batch()` — ein Batch, ein Call

Spec § 4.8, § 10 (Teilergebnisse). Der Kern des Kostenhebels.

⚠️ **Teilergebnisse werden übernommen, nicht verworfen.** `quick_filter_batch` warf bei
fehlenden Tickern; für die Tiefenanalyse wäre das falsch — „zehn gute Analysen schlagen
null" (Spec § 10). Fehlende Ticker werden gemeldet, nicht erfunden.

**Files:**
- Modify: `src/deep_analysis.py` (Import auf v2, `MAX_TOKENS_DEEP`-Ableitung, neue Funktionen)
- Test: `tests/unit/test_deep_analysis.py`
- Create: `tests/fixtures/mock_deep_analysis_batch_response.json`

**Interfaces:**
- Consumes: `call_claude(..., stream=True)` (Task 1), `build_batches()` (Task 3),
  `deep_analysis_v2.txt` (Task 4)
- Produces:
  - `deep_analysis.max_tokens_for_batch(n: int) -> int`
  - `deep_analysis.analyze_batch(ticker_datas, cutoff_by_ticker, trend_context, policy_context, cost_tracker) -> tuple[list[dict], list[str]]`
    — Rückgabe `(analyses, missing_tickers)`; wirft `DeepAnalysisError` nur, wenn die
    Antwort als Ganzes unparsebar ist

- [ ] **Step 1: Fixture + failing tests schreiben**

`tests/fixtures/mock_deep_analysis_batch_response.json` — zwei Ticker, einer mit einer
`thin`-Dimension:

```json
{
  "results": [
    {
      "ticker": "AAPL", "asset_class": "stock", "direction": "long",
      "confidence": "medium", "current_price": 178.5, "tp_price": 182.0,
      "sl_price": 176.75, "tp_pct": 1.96, "sl_pct": -0.98, "rr_ratio": 2.0,
      "total_score": 7.2, "probability_pct": 62, "hold_days_recommended": 1,
      "intraday_range_pct": 1.5, "earnings_warning": false,
      "summary": "Batch fixture for AAPL.",
      "sources_used": ["https://a.example", "https://b.example"],
      "signal_consistency_check": "ok",
      "scores": {
        "market_environment": {"value": 7.0, "evidence": ["e1", "e2"], "evidence_quality": "ok"},
        "company_quality":    {"value": 8.0, "evidence": ["e1", "e2"], "evidence_quality": "ok"},
        "valuation":          {"value": 5.0, "evidence": ["e1"], "evidence_quality": "thin"},
        "momentum":           {"value": 7.5, "evidence": ["e1", "e2"], "evidence_quality": "ok"},
        "risk":               {"value": 6.0, "evidence": ["e1", "e2"], "evidence_quality": "ok"},
        "sector_trend":       {"value": 7.0, "evidence": ["e1", "e2"], "evidence_quality": "ok"},
        "catalyst":           {"value": 6.5, "evidence": ["e1", "e2"], "evidence_quality": "ok"},
        "policy_risk":        {"value": 7.0, "evidence": ["e1", "e2"], "evidence_quality": "ok"}
      }
    },
    {
      "ticker": "MSFT", "asset_class": "stock", "direction": "none",
      "confidence": "low", "current_price": 410.0, "tp_price": 410.0,
      "sl_price": 410.0, "tp_pct": 0.0, "sl_pct": 0.0, "rr_ratio": 0.0,
      "total_score": 4.0, "probability_pct": 40, "hold_days_recommended": 1,
      "intraday_range_pct": 1.2, "earnings_warning": false,
      "summary": "No intraday setup for MSFT.",
      "sources_used": ["https://a.example", "https://b.example"],
      "signal_consistency_check": "ok",
      "scores": {
        "market_environment": {"value": 5.0, "evidence": ["e1", "e2"], "evidence_quality": "ok"},
        "company_quality":    {"value": 7.0, "evidence": ["e1", "e2"], "evidence_quality": "ok"},
        "valuation":          {"value": 5.0, "evidence": ["e1", "e2"], "evidence_quality": "ok"},
        "momentum":           {"value": 5.0, "evidence": ["e1", "e2"], "evidence_quality": "ok"},
        "risk":               {"value": 5.0, "evidence": ["e1", "e2"], "evidence_quality": "ok"},
        "sector_trend":       {"value": 5.0, "evidence": ["e1", "e2"], "evidence_quality": "ok"},
        "catalyst":           {"value": 4.0, "evidence": ["e1", "e2"], "evidence_quality": "ok"},
        "policy_risk":        {"value": 6.0, "evidence": ["e1", "e2"], "evidence_quality": "ok"}
      }
    }
  ]
}
```

Tests. ⚠️ **Den bestehenden Helper erweitern, keinen zweiten anlegen:**
`tests/unit/test_deep_analysis.py:15` hat bereits `_fake_result(text, model,
web_search_calls)`. Er bekommt zwei Parameter dazu, alle bisherigen Aufrufer bleiben
gültig:

```python
def _fake_result(text: str, model: str = "claude-sonnet-4-6",
                 web_search_calls: int = 3, output_tokens: int = 4000,
                 stop_reason: str = "end_turn") -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 5000
    r.output_tokens = output_tokens
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = model
    r.web_search_calls = web_search_calls
    r.stop_reason = stop_reason
    return r
```

`json`, `Path`, `patch`, `MagicMock`, `pytest` und `CostTracker` sind in der Datei
bereits importiert (Zeilen 1-6) — nicht doppelt importieren. `FIXTURE_DIR` existiert
ebenfalls (Zeile 12) und wird wiederverwendet:

```python
from src.deep_analysis import (
    analyze_batch, max_tokens_for_batch, DeepAnalysisError,
)

BATCH_FIXTURE = FIXTURE_DIR / "mock_deep_analysis_batch_response.json"


def _cutoff(ticker: str, news_strength: int = 2) -> dict:
    return {
        "ticker": ticker, "news_strength": news_strength,
        "tech_direction": "long", "tech_strength": 3,
    }


def test_max_tokens_for_batch_scales_with_size():
    """Abgeleitet statt fest: 4096 war fuer EINEN Ticker ausgelegt."""
    assert max_tokens_for_batch(8) == 9200      # 8 * 900 + 2000
    assert max_tokens_for_batch(1) == 4096      # Einzelfall unveraendert
    assert max_tokens_for_batch(20) == 20000


def test_analyze_batch_returns_one_analysis_per_ticker():
    fake = _fake_result(BATCH_FIXTURE.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_std("AAPL", "Technology"), _std("MSFT", "Technology")]

    with patch("src.deep_analysis.call_claude", return_value=fake) as cc:
        analyses, missing = analyze_batch(
            ticker_datas=batch,
            cutoff_by_ticker={"AAPL": _cutoff("AAPL"), "MSFT": _cutoff("MSFT")},
            trend_context={}, policy_context={}, cost_tracker=tracker,
        )

    assert [a["ticker"] for a in analyses] == ["AAPL", "MSFT"]
    assert missing == []
    assert cc.call_args.kwargs["stream"] is True
    assert cc.call_args.kwargs["max_tokens"] == max_tokens_for_batch(2)


def test_analyze_batch_keeps_partial_results():
    """Spec 10: 'zehn gute Analysen schlagen null'. Ein fehlender Ticker wird
    gemeldet, nicht erfunden -- und kippt nie die gelieferten."""
    payload = json.loads(BATCH_FIXTURE.read_text())
    payload["results"] = payload["results"][:1]       # MSFT fehlt
    fake = _fake_result(json.dumps(payload))
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_std("AAPL", "Technology"), _std("MSFT", "Technology")]

    with patch("src.deep_analysis.call_claude", return_value=fake):
        analyses, missing = analyze_batch(
            ticker_datas=batch,
            cutoff_by_ticker={"AAPL": _cutoff("AAPL"), "MSFT": _cutoff("MSFT")},
            trend_context={}, policy_context={}, cost_tracker=tracker,
        )

    assert [a["ticker"] for a in analyses] == ["AAPL"]
    assert missing == ["MSFT"]


def test_analyze_batch_raises_on_unparseable_response():
    """Anders als broad_scan (das auf 0 degradiert) wirft die Tiefenanalyse --
    Task 7 faengt und wiederholt/halbiert."""
    fake = _fake_result("not json at all", web_search_calls=0, output_tokens=10)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.deep_analysis.call_claude", return_value=fake):
        with pytest.raises(DeepAnalysisError):
            analyze_batch(
                ticker_datas=[_std("AAPL", "Technology")],
                cutoff_by_ticker={"AAPL": _cutoff("AAPL")},
                trend_context={}, policy_context={}, cost_tracker=tracker,
            )


def test_analyze_batch_raises_when_output_was_truncated():
    """Spec 4.8: stop_reason == 'max_tokens' ist ein Fehlerfall, kein
    akzeptables Ergebnis -- auch wenn das Teil-JSON zufaellig parsebar waere."""
    fake = _fake_result(
        BATCH_FIXTURE.read_text(), output_tokens=9200, stop_reason="max_tokens")
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.deep_analysis.call_claude", return_value=fake):
        with pytest.raises(DeepAnalysisError, match="max_tokens"):
            analyze_batch(
                ticker_datas=[_std("AAPL", "Technology"), _std("MSFT", "Technology")],
                cutoff_by_ticker={"AAPL": _cutoff("AAPL"), "MSFT": _cutoff("MSFT")},
                trend_context={}, policy_context={}, cost_tracker=tracker,
            )


def test_analyze_batch_payload_does_not_mutate_td():
    """Sidecar-Invariante: der Batch-Aufbau haengt keine Schluessel an td."""
    fake = _fake_result(BATCH_FIXTURE.read_text())
    td = _std("AAPL", "Technology")
    before = set(td)

    with patch("src.deep_analysis.call_claude", return_value=fake):
        analyze_batch(
            ticker_datas=[td], cutoff_by_ticker={"AAPL": _cutoff("AAPL")},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0),
        )

    assert set(td) == before
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

```bash
pytest tests/unit/test_deep_analysis.py -v -k "analyze_batch or max_tokens_for_batch"
```
Erwartet: FAIL — `ImportError: cannot import name 'analyze_batch'`.

- [ ] **Step 3: Implementieren**

In `src/deep_analysis.py` den Prompt-Import und die Token-Konstanten ersetzen
(Zeilen 17, 21):

```python
DEEP_SYSTEM_PROMPT = (PROMPT_DIR / "deep_analysis_v2.txt").read_text()
```

```python
# Spec 4.8: der alte feste Wert 4096 war fuer EINEN Ticker ausgelegt. Neu aus
# der Batchgroesse abgeleitet -- Richtwert ~900 Output-Tokens je Ticker plus
# Reserve fuer den JSON-Rahmen. Die Untergrenze 4096 haelt den Einzelfall
# (Batchgroesse 1) exakt auf dem bisherigen Budget.
TOKENS_PER_TICKER_DEEP = 900
BATCH_TOKEN_RESERVE = 2000
MAX_TOKENS_DEEP_MIN = 4096
MAX_TOKENS_POLICY = 3072


def max_tokens_for_batch(n: int) -> int:
    """Output-Token-Budget fuer einen Batch von n Tickern (Spec 4.8)."""
    return max(MAX_TOKENS_DEEP_MIN, n * TOKENS_PER_TICKER_DEEP + BATCH_TOKEN_RESERVE)
```

Die Batch-Funktionen ergänzen:

```python
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
) -> tuple[list[dict], list[str]]:
    """Analysiert einen ganzen Batch in EINEM gestreamten Sonnet-Call.

    Rueckgabe: (analyses, missing_tickers). Gelieferte Analysen werden IMMER
    uebernommen, auch wenn Ticker fehlen -- Spec 10: 'zehn gute Analysen
    schlagen null'. Das unterscheidet die Tiefenanalyse bewusst von
    quick_filter_batch, das bei fehlenden Tickern warf.

    Wirft DeepAnalysisError, wenn die Antwort als GANZES unbrauchbar ist:
    unparsebar, ohne results-Liste, oder abgeschnitten (stop_reason ==
    'max_tokens', Spec 4.8 -- kein akzeptables Ergebnis). Der Aufrufer aus
    Task 7 faengt das und wiederholt bzw. halbiert."""
    if not ticker_datas:
        return [], []

    user_msg = _build_batch_user_message(
        ticker_datas, cutoff_by_ticker, trend_context, policy_context)
    max_tokens = max_tokens_for_batch(len(ticker_datas))

    result = call_claude(
        model=MODEL, system=DEEP_SYSTEM_PROMPT, user=user_msg,
        max_tokens=max_tokens, tools=[WEB_SEARCH_TOOL], stream=True,
    )
    cost_tracker.add_from_result(result)

    if getattr(result, "stop_reason", None) == "max_tokens":
        raise DeepAnalysisError(
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
```

- [ ] **Step 4: Tests laufen lassen**

```bash
pytest tests/unit/test_deep_analysis.py -v
pytest tests/ -q
```
Erwartet: alle grün. ⚠️ Bestehende Tests, die `analyze_asset()` gegen den v1-Prompt
prüfen, laufen weiter — `analyze_asset()` bleibt in Task 6 unangetastet und wird erst in
Task 9 entfernt.

- [ ] **Step 5: Commit**

```bash
git add src/deep_analysis.py tests/unit/test_deep_analysis.py tests/fixtures/mock_deep_analysis_batch_response.json
git commit -m "feat: Plan-3a Task 6 -- analyze_batch(), MAX_TOKENS aus Batchgroesse"
```

---

### Task 7: Fehlerpfade — einmal wiederholen, einmal halbieren, aufgeben

Spec § 10: „einmal wiederholen → dann **einmal halbieren**, beide Hälften versuchen →
dann aufgeben, Ticker als übersprungen buchen. Ohne das kostet ein Fehler ~13 Ticker
statt einen. Begrenzte Tiefe, damit ein kaputter Prompt nicht endlos retryt."

⚠️ **Nicht zu verwechseln mit `retry_with_backoff` in `call_claude()`.** Das behandelt
*transiente API-Fehler* (Netz, 5xx). Diese Schale behandelt *unbrauchbare Ausgaben* —
eine andere Fehlerklasse, deshalb eine eigene Ebene.

**Files:**
- Modify: `src/deep_analysis.py` (neue Funktion nach `analyze_batch`)
- Test: `tests/unit/test_deep_analysis.py`

**Interfaces:**
- Consumes: `analyze_batch()` (Task 6)
- Produces: `deep_analysis.analyze_batches(ticker_datas, cutoff_by_ticker, trend_context, policy_context, cost_tracker, batch_size=config.BATCH_SIZE_DEEP) -> tuple[list[dict], list[str]]`

- [ ] **Step 1: Die failing tests schreiben**

```python
def _ok_response_for(tickers: list[str]) -> MagicMock:
    """Baut eine gueltige Batch-Antwort fuer genau diese Ticker."""
    template = json.loads(BATCH_FIXTURE.read_text())["results"][0]
    results = []
    for t in tickers:
        r = json.loads(json.dumps(template))
        r["ticker"] = t
        results.append(r)
    return _fake_result(json.dumps({"results": results}))


def _broken_response() -> MagicMock:
    return _fake_result("kaputt", web_search_calls=0, output_tokens=10)


def test_analyze_batches_retries_once_then_succeeds():
    """Erster Versuch kaputt, Wiederholung gut -- kein Halbieren noetig."""
    tds = [_std("AAPL", "Technology"), _std("MSFT", "Technology")]
    responses = [_broken_response(), _ok_response_for(["AAPL", "MSFT"])]

    with patch("src.deep_analysis.call_claude", side_effect=responses) as cc:
        analyses, failed = analyze_batches(
            ticker_datas=tds,
            cutoff_by_ticker={t["ticker"]: _cutoff(t["ticker"]) for t in tds},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0), batch_size=8,
        )

    assert cc.call_count == 2
    assert sorted(a["ticker"] for a in analyses) == ["AAPL", "MSFT"]
    assert failed == []


def test_analyze_batches_halves_after_two_failures():
    """Zwei Fehlschlaege -> halbieren, jede Haelfte genau einmal. Eine gute
    Haelfte wird behalten, die kaputte gibt ihre Ticker auf."""
    tds = [_std(t, "Technology") for t in ("AAPL", "MSFT", "NVDA", "AVGO")]
    responses = [
        _broken_response(),                      # Versuch 1
        _broken_response(),                      # Versuch 2 (Wiederholung)
        _ok_response_for(["AAPL", "AVGO"]),      # linke Haelfte (alphabetisch)
        _broken_response(),                      # rechte Haelfte
    ]

    with patch("src.deep_analysis.call_claude", side_effect=responses) as cc:
        analyses, failed = analyze_batches(
            ticker_datas=tds,
            cutoff_by_ticker={t["ticker"]: _cutoff(t["ticker"]) for t in tds},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0), batch_size=8,
        )

    assert cc.call_count == 4
    assert sorted(a["ticker"] for a in analyses) == ["AAPL", "AVGO"]
    assert sorted(failed) == ["MSFT", "NVDA"]


def test_analyze_batches_gives_up_after_halving():
    """Begrenzte Tiefe: nach dem Halbieren wird NICHT weiter geviertelt."""
    tds = [_std(t, "Technology") for t in ("AAPL", "MSFT", "NVDA", "AVGO")]
    responses = [_broken_response() for _ in range(4)]

    with patch("src.deep_analysis.call_claude", side_effect=responses) as cc:
        analyses, failed = analyze_batches(
            ticker_datas=tds,
            cutoff_by_ticker={t["ticker"]: _cutoff(t["ticker"]) for t in tds},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0), batch_size=8,
        )

    assert cc.call_count == 4          # 2 Versuche + 2 Haelften, nicht mehr
    assert analyses == []
    assert sorted(failed) == ["AAPL", "AVGO", "MSFT", "NVDA"]


def test_analyze_batches_single_ticker_batch_does_not_halve():
    """Ein Batch mit einem Ticker kann nicht halbiert werden -- nach zwei
    Versuchen aufgeben, nicht in eine Endlosschleife laufen."""
    tds = [_std("AAPL", "Technology")]
    responses = [_broken_response(), _broken_response()]

    with patch("src.deep_analysis.call_claude", side_effect=responses) as cc:
        analyses, failed = analyze_batches(
            ticker_datas=tds, cutoff_by_ticker={"AAPL": _cutoff("AAPL")},
            trend_context={}, policy_context={},
            cost_tracker=CostTracker(hard_cap_eur=10.0), batch_size=8,
        )

    assert cc.call_count == 2
    assert analyses == []
    assert failed == ["AAPL"]


def test_analyze_batches_cost_cap_propagates():
    """CostCapExceeded ist fatal und darf NICHT als Batch-Fehler behandelt und
    wiederholt werden -- sonst laeuft der Lauf ueber den Deckel hinaus weiter."""
    from src.cost_tracker import CostCapExceeded
    tds = [_std("AAPL", "Technology")]

    with patch("src.deep_analysis.call_claude", side_effect=CostCapExceeded("cap")):
        with pytest.raises(CostCapExceeded):
            analyze_batches(
                ticker_datas=tds, cutoff_by_ticker={"AAPL": _cutoff("AAPL")},
                trend_context={}, policy_context={},
                cost_tracker=CostTracker(hard_cap_eur=10.0), batch_size=8,
            )
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

```bash
pytest tests/unit/test_deep_analysis.py -v -k analyze_batches
```
Erwartet: FAIL — `ImportError: cannot import name 'analyze_batches'`.

- [ ] **Step 3: Implementieren**

```python
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
    in call_claude(); das ist eine andere Fehlerklasse und eine andere Ebene."""
    def attempt(tds: list[dict]) -> tuple[list[dict], list[str]]:
        return analyze_batch(
            ticker_datas=tds, cutoff_by_ticker=cutoff_by_ticker,
            trend_context=trend_context, policy_context=policy_context,
            cost_tracker=cost_tracker,
        )

    for versuch in (1, 2):
        try:
            return attempt(batch)
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
```

- [ ] **Step 4: Tests laufen lassen**

```bash
pytest tests/unit/test_deep_analysis.py -v
pytest tests/ -q
```
Erwartet: alle grün.

- [ ] **Step 5: Commit**

```bash
git add src/deep_analysis.py tests/unit/test_deep_analysis.py
git commit -m "feat: Plan-3a Task 7 -- Fehlerpfade: wiederholen, halbieren, aufgeben"
```

---

### Task 8: `check_analysis()` — schmale `thin`-Ausnahme

Spec § 4.8: „`thin`-Dimensionen umgehen die Zwei-Belege-Pflicht, zählen dafür nicht in die
News-Stärke. **Keine generelle Aufweichung der Beleg-Pflicht.**"

⚠️ Der zweite Halbsatz ist Plan 3b (`news_strength` existiert noch nicht). Hier entsteht
**nur** die Ausnahme in der Guardrail. Dass sie ohne den Gegenpart eine reine Lockerung
ist, ist der Preis des 3a/3b-Schnitts — deshalb der Test, der sie eng hält.

**Files:**
- Modify: `src/guardrails.py:43-49`
- Test: `tests/unit/test_guardrails.py`

**Interfaces:**
- Consumes: `evidence_quality` aus den v2-Prompts (Tasks 4/5)
- Produces: `check_analysis()` unverändert in der Signatur

- [ ] **Step 1: Die failing tests schreiben**

```python
def test_check_analysis_thin_dimension_skips_evidence_requirement():
    """Eine als thin markierte Dimension darf weniger als zwei Belege haben."""
    a = _valid_analysis()
    a["scores"]["valuation"] = {
        "value": 5.0, "evidence": ["nur eine Zeile"], "evidence_quality": "thin",
    }
    passed, errors = GuardrailsChecker().check_analysis(a)
    assert passed, errors


def test_check_analysis_thin_dimension_with_zero_evidence_allowed():
    """thin heisst 'ich habe nichts gefunden' -- auch leer ist zulaessig.
    Weglassen der Dimension waere es NICHT (Spec 4.8)."""
    a = _valid_analysis()
    a["scores"]["valuation"] = {
        "value": 5.0, "evidence": [], "evidence_quality": "thin",
    }
    passed, errors = GuardrailsChecker().check_analysis(a)
    assert passed, errors


def test_check_analysis_ok_dimension_still_needs_two_evidence():
    """Keine generelle Aufweichung: ohne thin-Markierung gilt die Pflicht."""
    a = _valid_analysis()
    a["scores"]["valuation"] = {
        "value": 5.0, "evidence": ["nur eine"], "evidence_quality": "ok",
    }
    passed, errors = GuardrailsChecker().check_analysis(a)
    assert not passed
    assert any("valuation" in e for e in errors)


def test_check_analysis_missing_evidence_quality_still_needs_two_evidence():
    """Ein v1-Ergebnis ohne evidence_quality faellt auf die strenge Regel
    zurueck -- die Ausnahme greift nur bei ausdruecklichem 'thin'."""
    a = _valid_analysis()
    a["scores"]["valuation"] = {"value": 5.0, "evidence": ["nur eine"]}
    passed, errors = GuardrailsChecker().check_analysis(a)
    assert not passed
    assert any("valuation" in e for e in errors)


def test_check_analysis_unknown_evidence_quality_is_strict():
    """Ein unbekannter Wert ist kein Freifahrtschein -- nur exakt 'thin'
    oeffnet die Ausnahme."""
    a = _valid_analysis()
    a["scores"]["valuation"] = {
        "value": 5.0, "evidence": ["nur eine"], "evidence_quality": "duenn",
    }
    passed, errors = GuardrailsChecker().check_analysis(a)
    assert not passed
```

⚠️ `_valid_analysis()` ist ein bestehender Helper in `tests/unit/test_guardrails.py`.
Falls er anders heisst, den vorhandenen verwenden statt einen zweiten anzulegen.

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

```bash
pytest tests/unit/test_guardrails.py -v -k thin
```
Erwartet: FAIL bei den ersten beiden — „Dimension valuation: too few evidence items".

- [ ] **Step 3: Implementieren**

`src/guardrails.py`, die Schleife bei Zeile 43-49 ersetzen:

```python
        scores = a.get("scores", {})
        for dim, sd in scores.items():
            # Spec 4.8: eine ausdruecklich als "thin" markierte Dimension
            # umgeht die Zwei-Belege-Pflicht. Sie wird BEHALTEN statt
            # weggelassen -- stilles Weglassen hat sich in diesem Projekt
            # wiederholt als Diagnose-Falle erwiesen (vgl. direction='none',
            # frueher lautlos verworfen). In Plan 3b zaehlt eine thin-Dimension
            # dafuer nicht in news_strength.
            #
            # Bewusst eng: NUR der exakte Wert "thin" oeffnet die Ausnahme.
            # Ein fehlendes Feld (v1-Ergebnis) oder ein unbekannter Wert faellt
            # auf die strenge Regel zurueck. Keine generelle Aufweichung.
            if sd.get("evidence_quality") == "thin":
                continue
            if len(sd.get("evidence", [])) < self.min_evidence_per_dim:
                errors.append(
                    f"Dimension {dim}: too few evidence items "
                    f"({len(sd.get('evidence', []))} < {self.min_evidence_per_dim})"
                )
```

- [ ] **Step 4: Tests laufen lassen**

```bash
pytest tests/unit/test_guardrails.py -v
pytest tests/ -q
```
Erwartet: alle grün.

- [ ] **Step 5: Commit**

```bash
git add src/guardrails.py tests/unit/test_guardrails.py
git commit -m "feat: Plan-3a Task 8 -- schmale thin-Ausnahme in check_analysis()"
```

---

### Task 9: Verdrahtung — `run_pipeline()` auf Batch-Phase-3

Der Schnitt, ab dem der Kostenhebel real wird. Hier fällt auch der Interim-Adapter aus
Plan 2 weg — sein eigener Docstring sagt: „Bleibt bis Plan 3 `deep_analysis_v2` einfuehrt
und `quick_filter_result` obsolet macht" (`src/deep_analysis.py:145-156`).

⚠️ **Der Auswahlschritt wandert.** Bisher entschied `analyze_asset()` selbst über
`quick_filter_result["exclude"]`, wer analysiert wird. Ab jetzt übergibt `main.py` nur
noch die **ausgewählten** Ticker — `selected` aus `cutoff_candidates()`. Die Auswahl
liegt damit vollständig im Cutoff, wo sie hingehört.

**Files:**
- Modify: `main.py:402-421`
- Modify: `src/deep_analysis.py` — `analyze_asset()`, `analyze_assets()`,
  `_build_user_message()` und `adapt_cutoff_to_quick_filter()` entfernen
- Test: `tests/unit/test_main.py`, `tests/unit/test_deep_analysis.py` (Altlast-Tests)

**Interfaces:**
- Consumes: `analyze_batches()` (Task 7), `cutoff_candidates()` (bestehend)
- Produces: `run_pipeline()` ruft Phase 3 gebatcht auf

- [ ] **Step 1: Den failing test schreiben**

In `tests/unit/test_main.py`:

```python
def test_run_pipeline_deep_analysis_only_receives_selected_tickers():
    """Die Auswahl liegt im Cutoff, nicht mehr im exclude-Flag: Phase 3 sieht
    ausschliesslich die selektierten Ticker."""
    # Aufbau analog zu den bestehenden run_pipeline-Tests in dieser Datei;
    # cutoff_candidates so mocken, dass es genau einen von zwei Tickern waehlt.
    ...
    with patch("main.analyze_batches", return_value=([], [])) as ab:
        run_pipeline(run_type="pre_market", ...)

    uebergeben = [td["ticker"] for td in ab.call_args.kwargs["ticker_datas"]]
    assert uebergeben == ["AAPL"]          # MSFT wurde nicht selektiert


def test_adapter_and_single_analysis_path_are_gone():
    """Die Plan-2-Interimsbruecke ist entfernt, nicht nur ungenutzt --
    ungelesener Code, der Wirkung vortaeuscht, ist genau die Altlast-Klasse,
    die MAX_DEEP_ANALYSIS vor Plan 2 war."""
    import src.deep_analysis as da
    assert not hasattr(da, "adapt_cutoff_to_quick_filter")
    assert not hasattr(da, "analyze_assets")
    assert not hasattr(da, "analyze_asset")
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

```bash
pytest tests/unit/test_main.py -v -k "only_receives_selected or adapter_and_single"
```
Erwartet: FAIL — `adapt_cutoff_to_quick_filter` existiert noch.

- [ ] **Step 3: Implementieren**

In `main.py` den Import (Zeile 22) ändern:

```python
from src.deep_analysis import run_policy_monitor, analyze_batches
```

`main.py:402-421` ersetzen:

```python
        # Phase 3 sieht ausschliesslich die selektierten Ticker. Bis Plan 3a
        # uebergab main ALLE Ticker plus ein exclude-Flag (der Interim-Adapter
        # aus Plan 2, Task 10) -- die Auswahl liegt jetzt vollstaendig im
        # Cutoff, wo sie hingehoert.
        selected_tickers = {c["ticker"] for c in selected}
        selected_tds = [td for td in sp500_tds if td["ticker"] in selected_tickers]
        cutoff_by_ticker = {c["ticker"]: c for c in selected}

        current_phase = "policy_monitor"
        # Phase 3 policy monitor (1× for all of Phase 3 + 3b + 4a)
        policy_context = run_policy_monitor(
            date=date, run_type=run_type, cost_tracker=cost_tracker,
        )
        payload["briefing"] = generate_daily_briefing(trend_context, policy_context)

        current_phase = "deep_analysis"
        # Phase 3 — Batch-Tiefenanalyse nach Sub-Sektor (Spec 4.8, 20.2).
        # failed_deep sind Ticker, deren Batch auch nach Wiederholung und
        # Halbierung nichts lieferte (Spec 10) -- sie werden gezaehlt, nicht
        # stillschweigend verschluckt.
        deep_stocks, failed_deep = analyze_batches(
            ticker_datas=selected_tds,
            cutoff_by_ticker=cutoff_by_ticker,
            trend_context=trend_context,
            policy_context=policy_context,
            cost_tracker=cost_tracker,
            batch_size=config.BATCH_SIZE_DEEP,
        )
        if failed_deep:
            log.warning(
                f"Phase 3: {len(failed_deep)} Kandidaten ohne Analyse: "
                f"{', '.join(sorted(failed_deep))}"
            )
```

In `src/deep_analysis.py` ersatzlos entfernen: `_build_user_message()` (Zeile 62-77),
`analyze_asset()` (80-106), `analyze_assets()` (109-142) und
`adapt_cutoff_to_quick_filter()` (145-166). Den Modul-Docstring (Zeile 1-6) auf den
neuen Zuschnitt ziehen.

In `tests/unit/test_deep_analysis.py` den Import-Block (Zeilen 7-10) mitziehen — er
importiert die entfernten Namen und lässt sonst die **ganze Datei** beim Sammeln
scheitern:

```python
from src.deep_analysis import (
    run_policy_monitor, DeepAnalysisError,
    build_batches, analyze_batch, analyze_batches, max_tokens_for_batch,
)
```

Bestehende Tests in derselben Datei, die `analyze_asset`/`analyze_assets`/
`adapt_cutoff_to_quick_filter` prüfen, entfernen — sie testen entfernten Code.
⚠️ **Nur diese.** Jeder andere Test bleibt, insbesondere die `run_policy_monitor`-Tests.

Ebenso prüfen, ob `main.py` oder andere Module `analyze_assets` noch importieren:

```bash
grep -rn "analyze_assets\|analyze_asset\|adapt_cutoff_to_quick_filter" --include="*.py" .
```
Erwartet nach dieser Task: nur noch Treffer in `src/commodities_crypto.py`
(dort heisst die Funktion ebenfalls `analyze_asset`, ist aber eine **andere** —
Rohstoffe/Krypto bleiben Einzelcalls, § 6). Nicht anfassen.

- [ ] **Step 4: Tests laufen lassen**

```bash
pytest tests/ -q
pytest tests/ --cov=src --cov=main --cov-fail-under=80 -q
```
Erwartet: alle grün, Coverage ≥ 80 %.

- [ ] **Step 5: Commit**

```bash
git add main.py src/deep_analysis.py tests/unit/test_main.py tests/unit/test_deep_analysis.py
git commit -m "feat: Plan-3a Task 9 -- run_pipeline() auf Batch-Phase-3, Interim-Adapter raus"
```

---

### Task 10: Testlauf gegen echte Daten

Spec § 12. **Kein Code — eine Messung.** Beantwortet § 19 #2 (Batchgrösse) und liefert
die Daten für #4 (`rank_score`, Plan 3b).

⚠️ **Niemals gegen `data/tracking.db`.** Wegwerf-Kopie, wie beim Plan-2-Testlauf
(PROJECT_STATUS C.7, Befund 9).

**Files:**
- Create: `docs/superpowers/specs/PROJECT_STATUS.md` — neuer Abschnitt **C.9**
- Kein Produktionscode

- [ ] **Step 1: Wegwerf-Umgebung aufsetzen**

```bash
mkdir -p /tmp/plan3a-testlauf
cp data/tracking.db /tmp/plan3a-testlauf/tracking.db
```

- [ ] **Step 2: Lauf mit `BATCH_SIZE_DEEP = 8`**

```bash
docker compose run --rm -v /tmp/plan3a-testlauf:/app/data trading-harry --run-type pre_market
```
⚠️ Kein Mailversand. Vorher prüfen, dass die Mail-Konfiguration im Testlauf leer ist
bzw. der Versand abgeschaltet — der Plan-2-Lauf hat das genauso gehandhabt.

- [ ] **Step 3: Zweiter Lauf mit anderer Batchgrösse**

`config.BATCH_SIZE_DEEP` temporär auf **4** setzen (nicht committen), Kopie der DB
erneuern, Lauf wiederholen. § 12 verlangt **zwei** Grössen — ohne die zweite ist die
Laufzeitfrage nicht beantwortbar.

- [ ] **Step 4: Die sechs Prüffragen aus § 12 beantworten**

| Prüffrage | Messgrösse | Woher |
|---|---|---|
| Wie skaliert die Laufzeit mit der Batch-Grösse? | Wanduhr je Batch, **nicht linear annehmen** | Log-Zeitstempel der `Batch (… Ticker) fertig`-Zeilen |
| Recherchiert Claude selektiv? | `web_search_calls` ÷ Ticker im Batch. Nahe 1 ⇒ selektiv, nahe 5 ⇒ der Prompt greift nicht | dieselbe Log-Zeile |
| Bleibt die Qualität bis zum **Ende** des Batches? | mittlere Belegzahl und Summary-Länge der ersten fünf gegen die letzten fünf Ticker | `predictions` in der Wegwerf-DB |
| Reicht `MAX_TOKENS_DEEP`? | `stop_reason == "max_tokens"` darf **nie** auftreten | Task 6 wirft dann — im Log sichtbar |
| Ist `rank_score` plausibel? | Rangliste von Hand gegen die Analysen gelesen | Vorarbeit für Plan 3b |
| Kosten je Ticker | `cost_tracking`-Tabelle gegen 3,3551 EUR (Plan-2-Lauf, 20 Ticker) | Wegwerf-DB |

- [ ] **Step 5: Ergebnis festhalten und committen**

PROJECT_STATUS **C.9** anlegen: gemessene Zahlen, Antwort auf § 19 #2, und ob
`BATCH_SIZE_DEEP = 8` bleibt. Falls der Testlauf den Wert kippt: `config.py` in
**diesem** Commit anpassen, mit der Messung als Begründung im Kommentar.

⚠️ **Ehrlich berichten.** Wenn eine Prüffrage unbeantwortet bleibt (z. B. weil zu wenige
Ticker den Cutoff passierten), gehört das als solches nach C.9 — nicht als bestandener
Punkt.

```bash
git add docs/superpowers/specs/PROJECT_STATUS.md config.py
git commit -m "docs: Plan-3a Task 10 -- Testlauf gemessen, Spec 19.2 beantwortet"
```

---

### Task 11: Doku nachziehen

**Files:**
- Modify: `CLAUDE.md`, `docs/superpowers/specs/PROJECT_STATUS.md`, `docs/ARCHITECTURE.md`
- Modify: `docs/superpowers/specs/2026-08-11-analyse-pipeline-umbau-design.md` (Status-Kopf)
- Modify: dieser Plan (Task-Tabelle mit Commits, Status auf abgeschlossen)

- [ ] **Step 1: `CLAUDE.md`**

Kopfeintrag für Plan 3a. In „Wichtige Designentscheidungen" ergänzen:
- Phase 3 läuft gebatcht nach Sub-Sektor; ganze Sub-Sektoren werden gepackt, nie
  zerrissen — ausser sie überschreiten `BATCH_SIZE_DEEP` allein
- `call_claude(stream=True)` für alle grossen Ausgaben; `broad_scan` nutzt es ebenfalls
- `evidence_quality: "thin"` umgeht die Zwei-Belege-Pflicht, **nur** bei exakt `"thin"`
- ⚠️ Prompt-Versionen: `deep_analysis_v2` / `commodities_crypto_v2` sind aktiv, v1 liegt
  unangetastet daneben

**Nichts aufnehmen, was aus Code oder ARCHITECTURE.md ableitbar ist** — CLAUDE.md ist
bewusst auf nicht-ableitbaren Inhalt getrimmt (Lehre aus Plan 2, Task 13).

- [ ] **Step 2: `PROJECT_STATUS.md`**

C.5 („Plan 3 offen, noch keine Plan-Datei") auf den 3a/3b-Schnitt ziehen und auf diese
Plan-Datei verweisen. Abschnitt **C.9** aus Task 10 einordnen.

- [ ] **Step 3: `docs/ARCHITECTURE.md`**

Pipeline-Grafik: Phase 3 als Batch-Phase. `src/deep_analysis.py` neu beschreiben
(`build_batches`, `analyze_batch`, `analyze_batches`; `analyze_asset`/`analyze_assets`
entfallen). Prompt-Tabelle um die beiden v2-Dateien ergänzen. Test-Baseline auf den
Stand nach Task 9 korrigieren.

- [ ] **Step 4: Spec-Kopf**

In `2026-08-11-analyse-pipeline-umbau-design.md` die Plan-3a-Zeile auf ✅ ziehen und
Plan 3b als einzigen offenen Rest ausweisen.

- [ ] **Step 5: Verifizieren und committen**

```bash
pytest tests/ --cov=src --cov=main --cov-fail-under=80 -q
graphify update .
git add -A
git commit -m "docs: Plan-3a Task 11 -- Doku nachgezogen, alle 11 Tasks abgeschlossen"
```

---

## Nach diesem Plan

**Abschluss-Review über die Plan-3a-Commits**, wie nach Plan 2 (`c978d70..HEAD` fand vier
Befunde, zwei davon verfehlten den Zweck ihrer eigenen Task). Erst danach Plan 3b.

**Plan 3b (Analyse & Ranking)** — bekommt eine eigene Plan-Datei, geschrieben **nach**
dem Testlauf, damit `rank_score` gegen echte Beispieldaten geprüft ist statt am
Schreibtisch festgelegt: `news_strength`, Qualifikation, `earnings_in_days`-Check,
`rank_score` als Sortierschlüssel, `candidate_class` + `DIVERGENCE_TOP_N`,
core/divergence in den Aggregaten, `score_total()`/`DIMENSION_WEIGHTS` raus,
Mail-Abschnitt.

---

## Selbstprüfung dieses Plans

**Spec-Abdeckung § 4.8, § 9, § 10, § 20 — Task je Anforderung:**

| Spec-Anforderung | Task |
|---|---|
| Batches nach Sub-Sektor | 3 |
| Selektive Recherche, `max_uses` batchabhängig | 4 (Prompt) — ⚠️ s. Lücke 1 |
| Technische Indikatoren als Fakten | 4, 6 (`technical_signal` in der Nutzlast) |
| Claude bewertet alle, wählt nicht aus | 4, 6 (`missing`-Meldung statt Auswahl) |
| Streaming-Pfad | 1 |
| `MAX_TOKENS_DEEP` aus Batchgrösse, `max_tokens` = Fehler | 6 |
| `thin` behalten, schmale Guardrail-Ausnahme | 4, 5, 8 |
| Polaritäts-Festlegung | 4, 5 |
| R/R-Ziel 1:2 | 4, 5 |
| Batch-Fehler: wiederholen → halbieren → aufgeben | 7 |
| Teilergebnis übernehmen, fehlende als skipped | 6, 7 |
| `CostCapExceeded` unverändert fatal | 7 (Test) |
| Prompts v2 als neue Dateien (Regel 10) | 4, 5 |
| Testlauf § 12 | 10 |

**⚠️ Bekannte Lücke 1 — `max_uses` bleibt bei 5.** Spec § 4.8 schlägt
`max_uses = 4 + 2 × Batchgrösse` als Obergrenze vor. `WEB_SEARCH_TOOL` ist heute eine
modulweite Konstante (`src/utils.py:133-137`) mit festem `max_uses: 5`; sie
batchabhängig zu machen heisst, sie zur Funktion zu machen und alle fünf Aufrufer
anzufassen. **Bewusst nicht in 3a**: der Prompt steuert die Selektivität (Task 4), und
§ 12 misst mit `web_search_calls ÷ Ticker`, **ob** er greift. Greift er nicht, ist die
Obergrenze das falsche Werkzeug — dann ist der Prompt zu schärfen. Wenn der Testlauf
zeigt, dass 5 tatsächlich klemmt, ist das ein eigener, dann belegter Task.

**⚠️ Bekannte Lücke 2 — `news_note` wird nicht in Phase 3 durchgereicht.**
`cutoff_candidates()` gibt `news_strength` zurück, aber nicht `news_note`
(`src/broad_scan.py:270-279`). Die Notiz würde die selektive Recherche gezielter machen.
Nicht in 3a, weil es eine zusätzliche Datenleitung durch zwei Funktionen bedeutet und der
Nutzen unbelegt ist — Phase 3 sucht ohnehin selbst. Nach dem Testlauf zu bewerten.

**Platzhalter-Scan:** keine TBD/TODO. Task 9 Step 1 enthält bewusst `...` im Testgerüst —
dort ist der bestehende `run_pipeline`-Testaufbau aus `tests/unit/test_main.py`
einzusetzen, der zu lang ist, um ihn hier zu duplizieren, und der beim Schreiben ohnehin
gelesen werden muss.

**Typ-Konsistenz geprüft:** `analyze_batch()` → `tuple[list[dict], list[str]]`,
`analyze_batches()` → dieselbe Form, `build_batches()` → `list[list[dict]]`,
`max_tokens_for_batch(int)` → `int`. `cutoff_by_ticker` ist durchgehend
`dict[str, dict]` und wird in den Tasks 6, 7 und 9 gleich benannt.
