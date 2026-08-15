# Analyse-Pipeline-Umbau, Plan 2: Trichter — Implementation Plan

**Status:** 🟡 **In Umsetzung — 9 von 13 Tasks committed (Stand 2026-08-15)**
**Erstellt:** 2026-08-13

| Task | Stand | Commit(s) |
|---|---|---|
| 1 ADX-Grenzwerte pinnen | ✅ | `086d49a` |
| 2 `cache_hit_rate` | ✅ | `aa2f222` |
| 3 `GAP_SCAN_BARS` 200 → 220 | ✅ | `da4cab1` |
| 4 Provider-Sammelabruf + 429-Notbremse | ✅ | `4801a63`, `a242d32` |
| 5 Phase 1a/1b Gate/Sweep/Indikatoren | ✅ | `aea3656`, `03354bb` |
| 6 Phase 1d Technik-Signal verdrahten | ✅ | `8351e31` |
| 7 Fundamentals aus Phase 1 lösen | ✅ | `f545901`, `7165bf5` |
| 8 `broad_scan.py` + Prompt | ✅ | `b861b48`, `b902b23`, `9a7cd1f` |
| 9 Cutoff + `cutoff_log` | ✅ | *(dieser Commit)* |
| 10 `run_pipeline()` verdrahten | ⏳ offen | — |
| 11 Finnhub-Ratenbegrenzung | ⏳ offen | — |
| 12 `run_weekly()`-Vorlauf | ⏳ offen | — |
| 13 Doku nachziehen | 🟡 teilweise | PROJECT_STATUS C.7, CLAUDE.md und ARCHITECTURE.md sind gezogen; Modul-Docstrings und die Phasentabelle fehlen |

⚠️ **Zwei Korrekturen an diesem Plan, gegen den Code geprüft:**
1. **Global Constraint 2 gilt für Task 3 nicht.** `GAP_SCAN_BARS` 200 → 220 **ändert** die
   Ticker-Auswahl (mehr erkannte Lücken → mehr Nachladeversuche, ggf. mehr Skips) — genau
   deshalb lag es nicht in Plan 1. Bewusste, dokumentierte Ausnahme; für Tasks 1–2 und 4–8
   ist die Garantie eingehalten.
2. **Numerierungs-Fehler in Constraint 2:** dort heisst es „Task 9 (broad_scan) ist der
   erste Konsument". `broad_scan` ist **Task 8**, und erster Konsument ist **Task 10**
   (die Verdrahtung). Task 9 ist der Cutoff.
3. **Task 9s eigener Pseudocode hatte drei Bugs**, alle beim Implementieren gegen den
   echten Code gefunden und in `cutoff_candidates()` anders gelöst: der separate
   `tech_signals`-Parameter existiert nicht (liegt im Sidecar aus Task 5/6), die
   Wahrheitswertprüfung auf `premarket_change_pct` hätte einen echten 0,0-%-Wert wie
   `None` behandelt, und `rank_position` über `enumerate(all_evaluated)` in **unsortierter**
   Reihenfolge wäre für den 3D-Vergleich „51. gegen 50." wertlos gewesen. Details:
   PROJECT_STATUS C.7, Befund 6.

⚠️ **Vor Task 10 zu entscheiden — Kostendeckel.** Gemessen am 2026-08-14: 3,9217 EUR gegen
`MAX_COST_PER_RUN_EUR = 4.00`. Task 10 tauscht Haiku ohne Websuche gegen Sonnet **mit**
Websuche; bei 20 MVP-Tickern greift `MAX_DEEP_ANALYSIS = 50` nicht, Phase 3 bleibt bei 20
Einzelcalls. Der Lauf wird damit **teurer**, nicht billiger — der Hebel ist das
Phase-3-Batching aus Plan 3. Deckel anheben oder Batching vorziehen, sonst endet der erste
Testlauf in `CostCapExceeded`. S. PROJECT_STATUS C.7, Befund 2.

⏳ **Task 4 hat eine offene Frage hinterlassen:** ob der Sammelabruf ein `offer`-Feld
liefert (Spec § 19.1a), ist **nicht** protokolliert. Die Sonde prüft es
(`setup/probe_epics_batch.py:144-147`), `get_premarket_prices_batch()` liest nur `bid`.
**Betrifft:** Phase 1–2 (Datensammlung & Scan), Auswahl-Logik, Trichter-Cutoff
**Design & Designentscheidungen:** docs/superpowers/specs/2026-08-11-analyse-pipeline-umbau-design.md (§ 4.2–4.8, § 6.1–6.3, § 18)

> Dieser Plan setzt Plan 1 um (Indikator-Fundament) in neue Pipeline-Phasen um. Beim
> Abschluss ist der Trichter live: `quick_filter.py` entfällt, `broad_scan` wählt aus,
> `MAX_DEEP_ANALYSIS = 50` wird gelesen. Phase 3 bleibt ein Call je Ticker (Batching
> kommt Plan 3).

---

## Einordnung

**Dependency:** Plan 1 (Fundament) ist fertig und gepusht.

**Integration:** Jede Task benutzt die bestehende DB (Fixture kopiert sie). Keine
Änderungen an `data/tracking.db`, die DB wird nur gelesen; Migrationen (`technical_indicators`,
`cutoff_log`) laufen gegen die **Kopie**.

**Testläufe:** Während der Umsetzung lokal gegen 20 MVP-Ticker mit echten Capital.com-
und Finnhub-Calls (read-only, kein Mailversand). Die `db-latest`-Snapshot vom 2026-08-12
enthält nur ~19 Bars je Ticker — darunter `MIN_BARS_RSI = 20`. Das Gate wird aggressiv
schießen; das ist erwartet und entlarvt den Test bei Task 5 und 8.

**Zwischen-Reviews:** Nach Task 8 (Phase-1-Umbau) und nach Task 11 (Trichter-Integration)
— beide Checkpoints wegen Risiken an häufig aufgerufener Code.

---

## Global Constraints

1. **Keine Feature-Flags.** Vorfixes (Tasks 1–3) + Gruppe 2 (5–8) gehen direkt auf main.
2. **Keine Verhaltensänderung bis Task 9.** Tasks 1–8 bereiten vor, ändern aber nicht
   die Auswahl. Task 9 (broad_scan) ist der erste Konsument.
3. **Phase 1 bleibt `collect()`-Signatur.** `collect(tickers, price_provider,
   earnings_provider, conn, date, run_type)` ändert sich nicht. Rückgabe bleibt
   `(list[dict], int)`.
4. **Parallelisierung nur in Gruppe 1.** Tasks 4–11 sind streng sequenziell.
5. **Tests: Transport-Level-Sperren, kein Web.** Autouse-Fixture aus `tests/conftest.py`
   bleibt; keine Livedata. **Task 4 (Provider-Sweep) ist die Ausnahme:** die Sonde
   `setup/probe_epics_batch.py` wird **mit `--run-live` ausgeführt**, gelesen nur,
   kein Schreiben, um die `marketDetails`-Antwort auf `offer` zu prüfen (Spec § 18.1a).

---

## Task 1: ADX-Grenzwerte pinnen

**Vorfix — vor Task 4.** Unabhängig, kann parallel zu Gruppe 2 laufen.

**Brief:** Die Schwellen `ADX_WEAK_BELOW = 20.0` und `ADX_STRONG_ABOVE = 25.0` sind
von keinem Test gepinnt. `technical_signal.py:_vote_adx()` prüft `< 20` und `> 25`,
also offene Intervalle — ein Test mit genau 20.0 oder 25.0 fällt durch beide Bänder
und deckt den Bug nicht. Zwei neue Tests schreiben die exakten Schwellen fest und
bleiben nach Plan 3.

**Dateien:** `config.py`, `src/technical_signal.py`, `tests/unit/test_technical_signal.py`

**Step 1 (TDD — Test schreiben):**
```python
# In tests/unit/test_technical_signal.py, neuer Test:

def test_adx_exactly_20_is_weak():
    """ADX=20.0 ist exakt die Grenze; alles < 20 ist schwach."""
    assert compute_technical_signal(
        rsi_14=55, rsi_trend="up",
        macd_line=0.5, macd_signal=0,
        close=110, sma_50=100, sma_200=95,
        adx_14=20.0  # exakt die Grenze
    )["tech_strength"] == 1  # gedeckelt auf 1, nicht 2+


def test_adx_exactly_25_is_strong():
    """ADX=25.0 ist exakt die Grenze; alles > 25 ist stark."""
    # Drei Teilindikatoren stimmen überein
    assert compute_technical_signal(
        rsi_14=55, rsi_trend="up",
        macd_line=0.5, macd_signal=0,
        close=110, sma_50=100, sma_200=95,
        adx_14=25.0  # exakt die Grenze
    )["tech_strength"] == 3  # nicht erhöht auf 4

def test_adx_below_20_is_weak():
    """ADX < 20: Stärke gedeckelt auf 1."""
    assert compute_technical_signal(
        rsi_14=55, rsi_trend="up",
        macd_line=0.5, macd_signal=0,
        close=110, sma_50=100, sma_200=95,
        adx_14=19.9
    )["tech_strength"] == 1

def test_adx_above_25_is_strong():
    """ADX > 25: Stärke erhöht um 1."""
    assert compute_technical_signal(
        rsi_14=55, rsi_trend="up",
        macd_line=0.5, macd_signal=0,
        close=110, sma_50=100, sma_200=95,
        adx_14=25.1
    )["tech_strength"] == 4  # 3 + 1 Bonus
```

**Step 2:** Tests laufen rot — die Grenzwerte sind nirgends getestet.

**Step 3:** Code lesen (`src/technical_signal.py:_vote_adx()`, `config.py:ADX_*`) und
sicherstellen, dass:
- `adx < ADX_WEAK_BELOW` (20.0) → `strength gedeckelt auf 1`
- `adx > ADX_STRONG_ABOVE` (25.0) → `strength += 1`
- Die Grenzwerte werden aus `config` gelesen, nicht hardcoded
- `==`-Grenzen fallen ins Band "normal" (nicht weak, nicht strong)

**Step 4:** Tests laufen grün; Testlauf über vorhandene Tests (`pytest tests/ --cov`),
kein Rückgang.

**Reviewer:** Bittet den Implementer, die Arithmetik der Grenzwerte zu zeigen:
- exakt 20.0 in `_vote_adx()` → nirgends befördern
- exakt 25.0 → nirgends +1 vergeben

---

## Task 2: `cache_hit_rate` um `cache_creation_tokens` ergänzen

**Vorfix — vor den Tests der Kostenmessung.**

**Brief:** Heute rechnet `cost_tracker.py:cache_hit_rate = cache_read / input_tokens`.
Das ist falsch: `cache_read_tokens` und `cache_creation_tokens` sind beide in
`input_tokens` enthalten (die API liefert nur den ungecachten Rest). Der Rate wird
der Nenner „zu klein" und der Wert geht über 1.0 bei Läufen, in denen der Cache
groß geschrieben wird (System-Prompt).

Die Rate sollte sein: `cache_read / (cache_read + cache_creation)` — nur die
beiden gecachten Teile, nicht die gesamten Input-Tokens.

**Dateien:** `src/cost_tracker.py`, `tests/unit/test_cost_tracker.py`

**Step 1 (TDD):**
```python
# Test, der die aktuelle Rate zu hoch macht:
def test_cache_hit_rate_includes_creation():
    """Beim ersten Lauf (Cache-Schreiben) sollte hit_rate < 1.0 sein,
    weil Cache-Creation mitgezählt wird."""
    tracker = CostTracker()
    tracker.add_from_result(MockResult(
        input_tokens=100,
        cache_read_tokens=10,
        cache_creation_tokens=50,
        output_tokens=20,
    ))
    # Nenner ist jetzt (10 + 50), nicht 100
    # Also 10 / 60 ≈ 0.167, nicht 10 / 100
    assert tracker.cache_hit_rate < 0.2
```

**Step 2:** Test läuft rot — `cache_hit_rate` wird zu hoch gemessen.

**Step 3:** `cost_tracker.py` aktualisieren:
```python
@property
def cache_hit_rate(self) -> float:
    """Anteil der gecachten Input-Tokens an allen gecachten Tokens
    (Lese + Schreib). Gibt 0 zurück, wenn kein Caching aktiv."""
    cached_total = self.cache_read_tokens + self.cache_creation_tokens
    if cached_total == 0:
        return 0.0
    return min(1.0, self.cache_read_tokens / cached_total)
```

**Step 4:** Tests grün, bestehende Tests (insbesondere `test_cache_read_tokens_priced_lower_than_fresh_input`)
passen sich an.

**Reviewer:** Prüft die Formel gegen die Spec § 13.1 und die API-Antwort-Struktur.

---

## Task 3: `GAP_SCAN_BARS` 200 → 220

**Verhaltensänderung, eigene Messung.**

**Brief:** Das Ladefenster ist seit Plan 1 auf 220 Bars, die Lückenerkennung schaut
aber nur 200 Bars zurück. Bars 201–220 bleiben damit unsichtbar; eine dort versteckte
Lücke kann den SMA200-Wert verfälschen. Die Anhebung ist eine echte Verhaltensänderung
(mehr erkannte Lücken → mehr Nachladeversuche → ggf. mehr Skips).

**Dateien:** `src/data_collector.py`

**Step 1:** Kommentar in `data_collector.py:42–46` lesen; die Anhebung ist ausdrücklich
als offener Punkt notiert.

**Step 2:** Konstante anheben:
```python
# Zeile 47
GAP_SCAN_BARS = 220  # war 200 — jetzt deckungsgleich mit dem Lade-Fenster
```

**Step 3:** Kommentar korrigieren:
```python
# Zeile 42–47
# Wie weit die Lueckenpruefung zurueckschaut. 220 Bars — deckungsgleich mit dem
# Lade-Fenster seit dem Umbau (2026-08-12). Eine Luecke bei Bar 201-220 waere
# vorher unsichtbar und koennte SMA200 verfaelschen.
```

**Step 4:** Testlauf lokal mit 20 MVP-Tickern, `cost_tracker` liest die Kosten.
Dokumentieren, wie viele zusätzliche Nachlade-Calls entstehen.

**Reviewer:** Prüft die Logik in `_first_gap_day()` — stellt sicher, dass die
Erhöhung tatsächlich Lücken bei 201–220 findet.

---

## Task 4: Provider — Sammelabruf `/markets?epics=`, 20er-Chunks, 429-Notbremse

**Neu, read-only Sonde + Integration.**

**Brief:** `capital_provider.py:get_premarket_price()` ruft heute je Ticker einen
einzelnen Call auf `/api/v1/markets/{epic}` ab. Bei 500 Tickern sind das 500 Calls.
Die Spec § 4.3.1 antwortet: `/markets?epics=A,B,C,...` funktioniert, Chunks zu 20
sind praktisch. Diese Task baut den Sweep mit Chunking, 429-Handling und der Beantwortung
der offenen Frage § 18.1a (liefert `marketDetails` ein `offer`-Feld für den Spread?).

**Dateien:** `src/providers/capital_provider.py`, `setup/probe_epics_batch.py`,
`tests/live/test_capital_provider.py` (neu, mit `@pytest.mark.live_api`)

**Step 1:** Sonde ausführen (Spec § 12, Task 1 wurde beantwortet, Task 1a offen):
```bash
# Lokal, mit --run-live (read-only)
python setup/probe_epics_batch.py --run-live
```
Dokumentieren: liefert `marketDetails[].snapshot` die Felder `bid` **und** `offer`?

**Step 2:** Neue Methode in `CapitalComProvider`:
```python
def get_premarket_prices_batch(
    self, tickers: list[str], chunk_size: int = 20
) -> dict[str, float | None]:
    """Ruft aktuelle Bid-Kurse über Batch-Abfrage ab: /markets?epics=A,B,C
    mit Chunks zu 20. Rückgabe: {ticker: bid, ...}. Fehlende Ticker bleiben
    raus (nicht im Dict).

    Fehlerbehandlung:
    - Erster 429 → getaktet (Retry-After/2s), betroffener Ticker einmal wiederholt
    - Weiterer 429 im Takt → Ticker übersprungen
    - 5 aufeinanderfolgende 429 → Abbruch, WARNING
    """
```

**Step 3 (TDD):** Test-Struktur für mocked Responses:
```python
def test_premarket_prices_batch_chunks():
    """Gruppiert Tickers in 20er-Chunks."""
    # Mock 25 Epics; erwarte 2 Calls (20 + 5)
    provider = CapitalComProvider()
    # mock the HTTP layer to count calls
    # Assertion: genau 2 Requests an /markets?epics=...

def test_premarket_prices_batch_handles_429():
    """Beim ersten 429: takten, einmal wiederholen.
    Beim zweiten 429 im Takt: überspringen."""

def test_premarket_prices_batch_aborts_on_five_consecutive_429s():
    """Nach 5 aufeinanderfolgende 429 wird abgebrochen."""
```

**Step 4:** Integration in `collect()` — wird in Task 5.

**Step 5:** Testlauf lokal: `python setup/probe_epics_batch.py --run-live` und
dokumentieren, ob `offer` in der Antwort steht (beantwortet Spec § 18.1a).

**Reviewer:** Liest die 429-Logik und bestätigt:
- Taktung ist persistent (ein Sleep pro Lauf, nicht pro Ticker)
- Retry-After wird respektiert
- 5er-Counter wird korrekt gezählt
- Wenn `offer` vorhanden ist: dokumentieren als zukünftiger Backlog-Punkt (§ 17)

---

## Task 5: Phase 1a/1b — Gate, Sweep, Indikator-Verdrahtung

**Streng sequenziell nach Task 4. Riskant — ändert `collect()` und `_process_ticker()`.**

**Brief:** Phase 1 zerfällt in Pässe statt einer Schleife pro Ticker:
1. Gate: inaktiv? Bars < MIN_BARS? → raus
2. Sweep: ein Batch-Call über alle Überlebenden → `premarket_change_pct`
3. Indikatoren & Technik-Signal: je Überlebendem, lokal

`collect()` schleife wird in drei Pas-Funktionen zerlegt, `_process_ticker()` wird
**vereinfacht** (keine Fundamentals-Verdrahtung mehr — geht in 2b).

**Dateien:** `src/data_collector.py`, `src/providers/base.py`,
`tests/unit/test_data_collector.py`, `tests/live/test_collection_integration.py` (neu)

**Step 1 (TDD — neue Tests schreiben, bevor Code umgebaut wird):**

Drei Tests für die neuen Pässe:
```python
def test_collect_gate_filters_inactive_and_short_history(conn):
    """Gate-Pass: inaktive Ticker und Bars < 20 werden rausgefiltert."""
    results, skipped = collect(
        tickers=["AAPL", "INACT_TICKER", "NOHIST"],
        ...
    )
    # INACT_TICKER ist in `is_ticker_inactive()` True
    # NOHIST hat 5 Bars (< MIN_BARS_RSI=20)
    # Assertion: len(results) == 1 (nur AAPL)
    # Assertion: skipped == 2

def test_collect_sweep_adds_premarket_change_pct(conn):
    """Sweep-Pass: live-Kurse werden geholt, premarket_change_pct wird berechnet."""
    # Mock capital_provider.get_premarket_prices_batch() to return known values
    # Assertion: jedes Ergebnis hat premarket_change_pct (float oder None)
    # Assertion: Berechnung korrekt: (live - letzter_close) / letzter_close * 100

def test_collect_computes_technical_signal(conn):
    """Indikatoren & Technik-Signal sind nach collect() in jedem Ergebnis."""
    results, _ = collect(...)
    for td in results:
        assert "tech_direction" in td
        assert "tech_strength" in td
        assert td["tech_direction"] in ("long", "short", "neutral")
        assert 0 <= td["tech_strength"] <= 4
```

**Step 2:** Code-Struktur — Tests laufen rot.

Neue Hilfsfunktionen:
```python
def _gate_phase(
    tickers: list[str], conn, date: str, run_type: str
) -> list[str]:
    """Phase 1a — gibt die Überlebenden zurück (ungefiltert auf Historie)."""
    survivors = []
    for t in tickers:
        if db.is_ticker_inactive(conn, t, today=date):
            _skip(conn, t, date, run_type, "inaktiv nach TICKER_MAX_SKIPS")
            continue
        survivors.append(t)
    return survivors

def _sweep_phase(
    survivors: list[str], price_provider: DataProvider
) -> dict[str, float | None]:
    """Phase 1b — Live-Kurse über Batch-Abfrage, premarket_change_pct."""
    # ruft get_premarket_prices_batch() auf
    # rechnet premarket_change_pct pro Ticker
    # gibt dict zurück: {ticker: premarket_change_pct}
```

**Step 3:** `_process_ticker()` vereinfachen — Fundamentals/Earnings raus:

```python
def _process_ticker(
    ticker: str,
    price_provider: DataProvider,
    conn,
    date: str,
    run_type: str,
    premarket_change_pct: float | None = None,
) -> dict | None:
    """Lädt Historie, rechnet Indikatoren, Technik-Signal. Keine Fundamentals hier mehr."""
    # ... (Gate für Bars bleibt)
    # Indikatoren (alles wie gehabt)
    # Technik-Signal ausrechnen
    td["premarket_change_pct"] = premarket_change_pct
    # KEINE Fundamentals-Verdrahtung mehr!
    # Nur minimal: sector bleibt auf "Unknown", earnings_in_days = None
    # Die echten Fundamentals kommen in Phase 2b
```

**Step 4:** `collect()` umbauen:
```python
def collect(...) -> tuple[list[dict], int]:
    survivors = _gate_phase(tickers, conn, date, run_type)
    # Phase 1b: Sweep
    premarket = _sweep_phase(survivors, price_provider)
    # Phase 1c/1d: je Überlebendem
    results = []
    for t in survivors:
        td = _process_ticker(
            t, price_provider, conn, date, run_type,
            premarket_change_pct=premarket[t]
        )
        if td is not None:
            results.append(td)
    return results, len(tickers) - len(results)
```

**Step 5:** Rohstoff-Ausnahme (Spec § 6.1) implementieren:

```python
def _gate_phase(...):
    # Neue Logik für Rohstoffe/Krypto
    commodities_crypto = [t for t in full_universe()
                          if t in COMMODITY_TICKERS.values()
                          or t in CRYPTO_TICKERS.values()]
    for t in tickers:
        if db.is_ticker_inactive(conn, t, today=date):
            if t in commodities_crypto:
                # Warnung statt Skip!
                log.warning(
                    f"{t}: Rohstoff/Krypto inaktiv — sollte laut Architektur "
                    f"immer analysiert werden. Manuell reactivate?"
                )
                survivors.append(t)  # nicht überspringen!
            else:
                _skip(conn, t, date, run_type, "inaktiv nach TICKER_MAX_SKIPS")
```

**Step 6:** Tests gegen die neuen Pässe:

```bash
pytest tests/unit/test_data_collector.py::test_collect_gate_filters_* -v
pytest tests/unit/test_data_collector.py::test_collect_sweep_* -v
pytest tests/unit/test_data_collector.py::test_collect_computes_* -v
```

**Step 7:** Testlauf lokal mit 20 MVP-Tickern + 7 Rohstoffe/Krypto:

```bash
python main.py --run-type pre_market --db-path data/tracking.db
```

Beobachten:
- Wie viele Ticker bleibt die Gate über?
- Sweep-Laufzeit (sollte deutlich schneller als vorher — statt 500 Calls, ~25)
- premarket_change_pct-Werte (vernünftig oder viele None?)

**Reviewer-Checkpoint 1 (nach Task 5, vor Task 6):** Intermediate Review über Tasks 4–5:

- Sweep-Logik und 429-Handling
- `_process_ticker()`-Schnittstelle passt?
- Rohstoff-Ausnahmen korrekt?
- premarket_change_pct-Berechnung?

---

## Task 6: Phase 1d — Technik-Signal verdrahten

**Streng sequenziell nach Task 5.**

**Brief:** `src/technical_signal.py` existiert seit Plan 1, wird aber nur von Tests
aufgerufen. Task 6 verdrahtet es in `_process_ticker()` und speichert die Werte
(`tech_direction`, `tech_agreement`, `tech_adx_band`, `tech_strength`) in `td`.

**Dateien:** `src/data_collector.py`, `src/indicators.py` (lesen nur),
`src/technical_signal.py` (verwenden), `tests/unit/test_data_collector.py`

**Step 1 (TDD):**

```python
def test_process_ticker_includes_technical_signal(conn):
    """Nach collect() enthält jedes Ergebnis das Tech-Signal."""
    results, _ = collect(...)
    for td in results:
        assert "tech_direction" in td
        assert "tech_agreement" in td
        assert "tech_adx_band" in td
        assert "tech_strength" in td
        assert td["tech_direction"] in ("long", "short", "neutral")
        assert 0 <= td["tech_agreement"] <= 3
        assert td["tech_adx_band"] in ("weak", "normal", "strong")
        assert 0 <= td["tech_strength"] <= 4
```

**Step 2:** `_process_ticker()` um Technik-Signal-Berechnung erweitern:

```python
def _process_ticker(...):
    # ... Indikatoren berechnet ...
    from src.technical_signal import compute_technical_signal
    signal = compute_technical_signal(
        rsi_14=td.get("rsi_14"),
        rsi_trend=td.get("rsi_trend"),
        macd_line=extra_indicators.get("macd_line"),
        macd_signal=extra_indicators.get("macd_signal_line"),
        close=df["Close"].iloc[-1],
        sma_50=extra_indicators.get("ema_50_dist_pct"),  # nein, die raw-Werte!
        sma_200=td.get("above_sma200"),  # auch nein — das ist ein Flag
        adx_14=extra_indicators.get("adx_14"),
    )
    td.update({
        "tech_direction": signal["direction"],
        "tech_agreement": signal["agreement"],
        "tech_adx_band": signal["adx_band"],
        "tech_strength": signal["strength"],
    })
```

**Hinweis:** `compute_technical_signal()` braucht **Rohwerte** (Close, SMA50-Wert, SMA200-Wert,
ADX), nicht die Prozent-Distanzen. Ich muss sicherstellen, dass die richtigen Werte
übergeben werden. Das ist ein kritischer Punkt — muss im Testlauf verifiziert werden.

**Step 3:** Test laufen lassen.

**Step 4:** Validierung in `_classify_data_quality()` — `tech_strength` wird kein
Klassifikator, aber `tech_direction = 'neutral'` ist ein Grund für späteren Ausfall
(Phase 4 / Plan 3). Dokumentieren.

**Reviewer:** Prüft, dass die Rohwerte korrekt an `compute_technical_signal()` übergeben
werden und dass die Rückgabewerte sauber in `td` landen.

---

## Task 7: Fundamentals aus Phase 1 lösen → Cache-Lesung + Phase-2b-Funktion

**Streng sequenziell nach Task 6.**

**Brief:** Heute holt `_process_ticker()` Fundamentals und Earnings je Lauf. Task 7
teilt auf:
- Phase 1: Liest nur `fundamentals_cache` (0 Calls, kein Finnhub)
- Phase 2b (Task 9): neue Funktion `fetch_missing_fundamentals()` für Kandidaten

Gleichzeitig wird das Earnings-Datum statt der Tageszahl gespeichert (Spec § 18.1d).

**Dateien:** `src/data_collector.py`, `src/db.py` (Schema-Update),
`tests/unit/test_data_collector.py`, `tests/unit/test_db.py`

**Step 1 (TDD):**

```python
def test_process_ticker_reads_fundamentals_cache_only(conn):
    """Phase 1 liest Cache; fehlt er, gibt es nur Defaults."""
    # Setup: Cache für AAPL mit gültiger TTL
    db.save_fundamentals_cache(conn, "AAPL", {
        "pe_ratio": 28.5, "market_cap_b": 3.2, "sector": "Technology",
        "earnings_next_date": "2026-08-20"  # neu!
    }, fetched_date="2026-08-13")
    
    # Lauf
    results, _ = collect(["AAPL"], ...)
    assert results[0]["pe_ratio"] == 28.5
    assert results[0]["market_cap_b"] == 3.2
    assert results[0]["earnings_in_days"] == 7  # berechnet aus Datum
    
def test_process_ticker_uses_defaults_on_cache_miss(conn):
    """Kein Cache → Defaults (None, None, 'Unknown')."""
    # Cache ist leer
    results, _ = collect(["AAPL"], ...)
    assert results[0]["pe_ratio"] is None
    assert results[0]["market_cap_b"] is None
    assert results[0]["sector"] == "Unknown"
    assert results[0]["earnings_in_days"] is None
```

**Step 2:** DB-Schema Update — `fundamentals_cache` um `earnings_next_date` erweitern:

```python
# src/db.py, in _apply_migrations():
if migration_level < 42:  # nächste freie Nummer
    conn.execute("""
        ALTER TABLE fundamentals_cache
        ADD COLUMN earnings_next_date TEXT
    """)
    # Alte earnings_calendar-Einträge (aus dem Tageslauf) gibt es nicht
    # (weekly verwaltet sie); daher unproblematisch
```

**Step 3:** `_process_ticker()` umbauen — nur noch Cache-Lesung:

```python
def _process_ticker(...):
    # ... Indikatoren, Tech-Signal ...
    
    # Fundamentals: nur aus Cache
    cached_fund = db.get_cached_fundamentals(conn, ticker, today=date)
    fundamentals = cached_fund or {}
    
    # earnings_in_days aus dem Datum berechnen
    earnings_date_str = fundamentals.get("earnings_next_date")
    earnings_in_days = None
    if earnings_date_str:
        from datetime import date as _d
        next_date = _d.fromisoformat(earnings_date_str)
        earnings_in_days = (next_date - _d.fromisoformat(date)).days
    
    td.update({
        "pe_ratio": fundamentals.get("pe_ratio"),
        "market_cap_b": fundamentals.get("market_cap_b"),
        "sector": fundamentals.get("sector", "Unknown"),
        "analyst_target_upside": fundamentals.get("analyst_upside"),
        "analyst_consensus": fundamentals.get("consensus"),
        "earnings_in_days": earnings_in_days,
        "earnings_beat_pct": None,  # nicht aus dem Cache; laufen wir jetzt nicht mehr
        # NICHT mehr: earnings_provider.get_earnings_calendar() — das kommt in weekly!
    })
```

**Step 4:** Phase-2b-Funktion anlegen (noch nicht verwendet, wird Task 9):

```python
# src/data_collector.py, neue Funktion

def fetch_missing_fundamentals(
    candidates: list[dict],  # aus dem Cutoff, mit Ticker
    conn,
    earnings_provider: DataProvider,
    date: str,
) -> None:
    """Holt Fundamentals und Earnings-Termine für Kandidaten mit Cache-Miss.
    Speichert alles in fundamentals_cache. Nicht fatal: ein API-Fehler überspringt
    den Ticker, der Lauf läuft weiter."""
    for td in candidates:
        t = td["ticker"]
        if db.get_cached_fundamentals(conn, t, today=date) is not None:
            continue  # hab schon genug
        try:
            raw = earnings_provider.get_fundamentals(t)
            # ... verarbeiten, mit earnings_next_date statt days_to_next ...
            earnings = earnings_provider.get_earnings_calendar(t)
            # earnings["days_to_next"] → in Datum umrechnen
            if earnings.get("days_to_next") is not None:
                from datetime import date as _d, timedelta
                next_d = (_d.fromisoformat(date) 
                         + timedelta(days=earnings["days_to_next"]))
                raw["earnings_next_date"] = next_d.isoformat()
            db.save_fundamentals_cache(conn, t, raw, fetched_date=date)
        except Exception as e:
            log.warning(f"{t}: Fundamentals fetch failed: {e}")
```

**Step 5:** Tests laufen lassen.

**Reviewer:** Prüft die Datums-Umrechnung und dass die Migration sauber ist.

---

## Task 8: `broad_scan.py` + Prompt — Phase-2-Nachrichten-Scan

**Streng sequenziell nach Task 7, aber noch nicht verdrahtet in `main.run_pipeline()`
(kommt Task 11).**

**Brief:** Phase 2 ist ein Sonnet-Call mit Websuche über **alle** Überlebenden nach
Gate/Sweep. Ausgabe: `{ticker, news_strength (0–3), news_note}` je Ticker.

Neue Datei `src/broad_scan.py`, neuer Prompt `prompts/broad_scan_v1.txt`.

**Dateien:** `src/broad_scan.py` (neu), `prompts/broad_scan_v1.txt` (neu),
`tests/unit/test_broad_scan.py` (neu), `tests/live/test_broad_scan_integration.py` (neu)

**Step 1:** Prompt schreiben — Spec § 4.6:

```
prompts/broad_scan_v1.txt:

You are a news analyst for short-term CFD trades (hold 1–3 days).

CONTEXT: [Trend context, Policy context]

TICKERS (one per line, JSON):
[{ticker, change%, 1d/5d%, rsi, atr%, sector}, ...]

TASK: Search for market-moving news about these tickers using web_search 3–6 times.
Return this JSON object:

{
  "results": [
    {
      "ticker": "...",
      "news_strength": <0|1|2|3>,
      "news_note": "<beleg>" or ""
    }
  ]
}

news_strength:
  0 = keine Auffälligkeit
  1 = am Rande erwähnt
  2 = klarer Katalysator
  3 = marktbewegend

Muss >= Stärke 1 einen "news_note" enthalten, sonst setz die Stärke auf 0.
Veranstalte KEINE Schätzungen der technischen Auffälligkeit — die
liegt als tech_strength vor.
```

**Step 2 (TDD):**

```python
def test_broad_scan_returns_results_for_all_tickers(cost_tracker):
    """Scan liefert genau ein Ergebnis je Input-Ticker."""
    results = broad_scan_batch(
        ticker_datas=[
            {"ticker": "AAPL", ...},
            {"ticker": "MSFT", ...},
        ],
        trend_context={...},
        market_context={...},
        cost_tracker=cost_tracker,
    )
    assert len(results) == 2
    assert {r["ticker"] for r in results} == {"AAPL", "MSFT"}

def test_broad_scan_strength_requires_note(cost_tracker):
    """Stärke >= 1 braucht eine note; sonst wird Stärke auf 0 gezogen."""
    # Mock Claude rückgabe mit strength=2 aber leerer note
    # Erwarte: strength → 0, note bleibt leer

def test_broad_scan_parses_json_correctly(cost_tracker):
    """Unparsbare Responses werfen BroadScanError."""
    # Mock bad JSON
    # Expect BroadScanError
```

**Step 3:** `src/broad_scan.py` — Struktur wie `quick_filter.py`:

```python
"""Phase 2: Broadcast-Nachrichten-Scan mit Websuche."""

class BroadScanError(RuntimeError):
    """Scan output unparseable."""

def broad_scan_batch(
    ticker_datas: list[dict],
    trend_context: dict,
    market_context: dict,
    cost_tracker: CostTracker,
) -> list[dict]:
    """Ein Sonnet-Call mit Websuche über alle Tickers."""
    user_msg = _format_batch_for_prompt(ticker_datas, trend_context, market_context)
    result = call_claude(
        model="claude-sonnet-4-6",
        system=SYSTEM_PROMPT,
        user=user_msg,
        max_tokens=4096,
        tools=[WEB_SEARCH_TOOL],
    )
    cost_tracker.add_from_result(result)
    parsed = extract_json_blob(result.text, BroadScanError)
    results = parsed.get("results", [])
    
    # Validierung: Stärke ohne Note → auf 0
    for r in results:
        if r.get("news_strength", 0) >= 1 and not r.get("news_note", "").strip():
            r["news_strength"] = 0
    
    return results
```

**Step 4:** Tests laufen lassen (mit mocked Claude).

**Step 5:** Liveverifikation gegen echte API (mit `--run-live`, falls der Test auf
echte Daten warten will). Beobachten: Kosten, Suchanfragen, Ausgabequalität.

**Reviewer:** Prüft den Prompt auf Klarheit und prüft die Note-Validierung.

---

## Task 9: Cutoff + Tabelle `cutoff_log` + Migration

**Streng sequenziell nach Task 8. Noch nicht in `main.py` verdrahtet (Task 11).**

**Brief:** Nach Phase 2 werden die Kandidaten ausgewählt: `news_strength >= 1 ODER
tech_strength >= TECH_MIN_FOR_DEEP`, sortiert nach `(news_strength, |premarket_change_pct|,
tech_strength, ticker)`, gedeckelt bei `MAX_DEEP_ANALYSIS`.

Die Eingangs-Kandidatenliste (vor Cutoff) wird in neue Tabelle `cutoff_log` geschrieben —
für 3D nötig, um den 51. mit dem 50. zu vergleichen.

Neue Tabelle und Migration, neue Cutoff-Funktion in `broad_scan.py`.

**Dateien:** `src/db.py` (Schema + Migration), `src/broad_scan.py` (Cutoff-Funktion),
`tests/unit/test_db.py`, `tests/unit/test_broad_scan.py`

**Step 1 (TDD):**

```python
def test_cutoff_sorts_by_news_first():
    """Kandidaten sortiert: news_strength absteigend."""
    results = cutoff_candidates(
        ticker_datas=[...],
        broad_scan_results=[
            {"ticker": "A", "news_strength": 1},
            {"ticker": "B", "news_strength": 0},
            {"ticker": "C", "news_strength": 2},
        ],
        tech_signals={...},
        max_deep_analysis=50,
    )
    # Ergebnis sollte C, A, B sein (Stärke absteigend)

def test_cutoff_respects_max_deep_analysis():
    """Deckel bei MAX_DEEP_ANALYSIS."""
    results = cutoff_candidates(
        ticker_datas=[...],  # 100 Ticker
        ...
        max_deep_analysis=50,
    )
    assert len(results) == 50

def test_cutoff_qualifies_only_news_or_tech():
    """Kandidat = news_strength >= 1 ODER tech_strength >= TECH_MIN_FOR_DEEP."""

def test_cutoff_log_written_for_all_tickers():
    """cutoff_log enthält alle bewerteten Ticker, nicht nur die selected."""
```

**Step 2:** DB-Schema:

```python
# src/db.py, SCHEMA_SQL

CREATE TABLE IF NOT EXISTS cutoff_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    run_type TEXT NOT NULL,
    ticker TEXT NOT NULL,
    news_strength INTEGER,
    premarket_change_pct REAL,
    tech_direction TEXT,
    tech_agreement INTEGER,
    rank_position INTEGER,  # Reihenfolge nach Sortierung
    selected BOOLEAN NOT NULL,  # true = Top MAX_DEEP_ANALYSIS
    UNIQUE(date, run_type, ticker)
);
```

**Step 3:** Migration:

```python
# src/db.py, in _apply_migrations()

if migration_level < 43:
    conn.execute("""CREATE TABLE IF NOT EXISTS cutoff_log (...)""")
```

**Step 4:** Cutoff-Funktion in `broad_scan.py`:

```python
def cutoff_candidates(
    ticker_datas: list[dict],
    broad_scan_results: list[dict],
    tech_signals: dict[str, dict],
    forced_candidates: set[str],
    max_deep_analysis: int = 50,
) -> tuple[list[dict], list[dict]]:
    """Selektiert Kandidaten nach (news_strength, |premarket_change_pct|, tech_strength).
    Rückgabe: (selected, all_evaluated) für die Logging."""
    
    by_ticker = {td["ticker"]: td for td in ticker_datas}
    evaluated = []
    for td in ticker_datas:
        t = td["ticker"]
        scan = next((s for s in broad_scan_results if s["ticker"] == t), {})
        tech = tech_signals.get(t, {})
        news_str = scan.get("news_strength", 0)
        tech_str = tech.get("tech_strength", 0)
        
        qualifies = news_str >= 1 or tech_str >= TECH_MIN_FOR_DEEP
        change_pct = td.get("premarket_change_pct")
        
        evaluated.append({
            "ticker": t,
            "news_strength": news_str,
            "premarket_change_pct": change_pct,
            "tech_direction": tech.get("tech_direction"),
            "tech_agreement": tech.get("tech_agreement"),
            "qualifies": qualifies,
        })
    
    # Sortierung
    def sort_key(e):
        return (
            -e["news_strength"],
            -(abs(e["premarket_change_pct"]) if e["premarket_change_pct"] else -1),
            -tech_signals.get(e["ticker"], {}).get("tech_strength", 0),
            e["ticker"],
        )
    
    qualified = [e for e in evaluated if e["qualifies"] or e["ticker"] in forced_candidates]
    qualified.sort(key=sort_key)
    selected = qualified[:max_deep_analysis]
    
    return selected, evaluated
```

**Step 5:** Persistierung:

```python
def log_cutoff(
    conn, date: str, run_type: str,
    selected: list[dict], all_evaluated: list[dict]
) -> None:
    """Schreibt cutoff_log."""
    seen = set()
    for rank, item in enumerate(all_evaluated):
        t = item["ticker"]
        sel = t in {s["ticker"] for s in selected}
        conn.execute("""
            INSERT OR REPLACE INTO cutoff_log
            (date, run_type, ticker, news_strength, premarket_change_pct,
             tech_direction, tech_agreement, rank_position, selected)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (date, run_type, t, item["news_strength"], item["premarket_change_pct"],
              item.get("tech_direction"), item.get("tech_agreement"), rank, sel))
        seen.add(t)
    conn.commit()
```

**Step 6:** Tests laufen lassen.

**Reviewer:** Prüft die Sortierreihenfolge exakt: News vor Technik vor Ticker-Name.

---

## Task 10: `main.run_pipeline()` — quick_filter raus, Interim-Adapter, Cutoff live

**Riskant — Naht zwischen Phase 2 und Phase 3.**

**Brief:** `quick_filter_batch()` wird durch `broad_scan_batch()` + `cutoff_candidates()`
ersetzt. Die ausgewählten Kandidaten gehen an `analyze_assets()`.

`analyze_assets()` erwartet heute `quick_filter_results` mit `exclude`-Flag. Der
Interim-Adapter adaptiert die Cutoff-Ausgabe auf diese Struktur, bis Plan 3 `deep_analysis_v2`
einführt und das `exclude`-Flag obsolet macht.

`MAX_DEEP_ANALYSIS` wechselt 80 → 50 und wird ab sofort gelesen.

**Dateien:** `main.py`, `src/deep_analysis.py` (Adapter),
`tests/unit/test_deep_analysis.py` (Adapter-Tests)

**Step 1 (TDD — Adapter-Tests):**

```python
def test_cutoff_results_adapted_to_quick_filter_schema():
    """Interim-Adapter konvertiert Cutoff-Kandidaten zu quick_filter-Schema."""
    cutoff_results = [
        {"ticker": "AAPL", "news_strength": 2, ...},
        {"ticker": "MSFT", "news_strength": 0, ...},
    ]
    adapted = adapt_cutoff_to_quick_filter(cutoff_results)
    assert len(adapted) == 2
    assert adapted[0]["exclude"] is False  # qualifiziert
    assert adapted[1]["exclude"] is True   # nicht qualifiziert (nur wenn nicht tech)
```

**Step 2:** Adapter schreiben:

```python
# src/deep_analysis.py, neue Funktion

def adapt_cutoff_to_quick_filter(
    cutoff_selected: list[dict],
    all_tickers: list[dict],
) -> list[dict]:
    """Konvertiert Cutoff-Output zu quick_filter-kompatiblem Format für den
    Interim-Schritt (bis Plan 3 auf v2 umstellt)."""
    selected_tickers = {r["ticker"] for r in cutoff_selected}
    results = []
    for td in all_tickers:
        t = td["ticker"]
        results.append({
            "ticker": t,
            "exclude": t not in selected_tickers,
            "long_score": None,    # kommt in v2
            "short_score": None,
            "confidence": None,
        })
    return results
```

**Step 3:** `main.run_pipeline()` umbauen:

```python
# Alte Phase 2: quick_filter
# quick = quick_filter_batch(sp500_tds, trend_context, cost_tracker)
# quick = _apply_forced_candidates(quick, forced)

# Neue Phase 2:
broad_results = broad_scan_batch(
    sp500_tds, trend_context, market_context={...}, cost_tracker=cost_tracker
)
selected, all_evaluated = cutoff_candidates(
    ticker_datas=sp500_tds,
    broad_scan_results=broad_results,
    tech_signals={td["ticker"]: td for td in sp500_tds},
    forced_candidates=forced,
    max_deep_analysis=config.MAX_DEEP_ANALYSIS,
)
db.log_cutoff(conn, date, "pre_market", selected, all_evaluated)

# Interim-Adapter
quick = adapt_cutoff_to_quick_filter(selected, sp500_tds)

# Phase 3 bleibt unverändert
deep_stocks = analyze_assets(sp500_tds, quick, ...)
```

**Step 4:** `config.py`:

```python
# Alte Werte entfernen oder deprecaten
# MAX_DEEP_ANALYSIS = 50  (war 80)
# BATCH_SIZE_QUICK entfernen (war tot)
```

**Step 5:** Tests laufen lassen.

**Reviewer-Checkpoint 2 (nach Task 10, vor Task 12):** Intermediate Review über Tasks 8–10:

- Scan-Logik und Web-Search-Integratio
- Cutoff-Sortierung stimmt?
- Adapter-Schnittstelle passt?
- MAX_DEEP_ANALYSIS wird gelesen?
- cutoff_log-Struktur für 3D brauchbar?

---

## Task 11: Finnhub-Ratenbegrenzung + `earnings_next_date` Schema

**Parallel nach Task 10, aber vor Task 12.**

**Brief:** `get_earnings_calendar()` wird aus dem Tageslauf entfernt und in den
Wochenlauf verschoben (Task 13). Bis dahin ist auch die alte
`_FUNDAMENTALS_TTL_DAYS = 7` Konvention zu ändern — der Wochenjob fetcht einmal
die ganze Woche und wird über Ratenbegrenzung getaktet.

**Dateien:** `src/providers/finnhub_provider.py`, `src/db.py`,
`tests/unit/test_db.py`

**Step 1:** Ratenbegrenzung in Finnhub-Provider:

```python
# src/providers/finnhub_provider.py

_FINNHUB_RATE_LIMIT = 60  # Calls/min
_FINNHUB_RATE_WINDOW_MS = 60000
_rate_limiter: dict = {"calls": [], "last_reset": 0}

def _respect_finnhub_rate_limit():
    """Pause, damit wir unter 60 Calls/min bleiben."""
    import time
    now = time.time() * 1000
    # sliding window: alte Einträge > 1min entfernen
    _rate_limiter["calls"] = [
        c for c in _rate_limiter["calls"]
        if now - c < _FINNHUB_RATE_WINDOW_MS
    ]
    if len(_rate_limiter["calls"]) >= 60:
        sleep_ms = (
            _FINNHUB_RATE_WINDOW_MS 
            - (now - _rate_limiter["calls"][0])
        )
        log.info(f"Finnhub rate limit: sleeping {sleep_ms/1000:.1f}s")
        time.sleep(sleep_ms / 1000)
    _rate_limiter["calls"].append(now)
```

Auf jede `get_fundamentals()` und `get_earnings_calendar()` vor dem Call anwenden.

**Step 2:** Migration für `earnings_next_date` ist schon in Task 7 — keine neue nötig.

**Step 3:** Test-Struktur:

```python
def test_finnhub_rate_limiter_pauses_at_60_calls():
    """Nach 60 Calls sperrt die Funktion."""
    # Mock 60 Aufrufe schnell hintereinander
    # Erwarte: der 61. Call wird um ~1s verzögert
```

**Reviewer:** Prüft, dass die Rate-Limitierung über alle Calls gleichmäßig verteilt ist.

---

## Task 12: `run_weekly()` — Vorlauf mit Finnhub-Fundamentals und Earnings

**Unabhängig von Task 11 (kann parallel laufen).**

**Brief:** Der Wochenlauf (Freitag ~00:00 UTC) füllt `fundamentals_cache` und die
Earnings-Termine für das gesamte Universum. Das ist ein neuer `run_weekly()` Vorlauf
vor dem wöchentlichen Aggregat.

500 Ticker × Finnhub 60/min = 8,3 Minuten + Pausen. Mit der Ratenbegrenzung aus
Task 11 ist die Laufzeit kalkulierbar.

**Dateien:** `main.py` (run_weekly), `src/providers/finnhub_provider.py`,
`tests/unit/test_weekly_fundamentals.py` (neu, mit `@pytest.mark.live_api`)

**Step 1:** `run_weekly()` erweitern:

```python
# main.py

def run_weekly(date: str, db_path: str) -> None:
    conn = db.connect(db_path)
    db.init_schema(conn)
    
    # Neuer Vorlauf: Fundamentals für das ganze Universum
    log.info("Updating fundamentals cache for full universe...")
    earnings_provider = FinnhubProvider()
    universe = full_universe()
    
    for ticker in universe:
        if db.get_cached_fundamentals(conn, ticker, today=date):
            continue  # bereits aktuell
        try:
            raw = earnings_provider.get_fundamentals(ticker)
            earnings = earnings_provider.get_earnings_calendar(ticker)
            
            # earnings["days_to_next"] → Datum
            if earnings.get("days_to_next") is not None:
                from datetime import date as _d, timedelta
                next_d = (_d.fromisoformat(date)
                         + timedelta(days=earnings["days_to_next"]))
                raw["earnings_next_date"] = next_d.isoformat()
            
            db.save_fundamentals_cache(conn, ticker, raw, fetched_date=date)
            log.debug(f"{ticker}: fundamentals cached")
        except Exception as e:
            log.warning(f"{ticker}: weekly fundamentals failed (non-fatal): {e}")
            # nicht fatal — ein fehlender Ticker in der Woche macht der
            # Tageslauf nach, oder er wird mit Defaults analysiert
    
    # Danach das wöchentliche Aggregat wie gehabt
    agg = load_recent_outcomes_aggregate(conn, today=date)
    # ... Mail ...
```

**Step 2:** Tests (mit mocked Finnhub-Responses).

**Reviewer:** Prüft, dass der Vorlauf nicht fatal ist und die Wochenlauf-Logik unangetastet bleibt.

---

## Task 13: Doku nachziehen — ARCHITECTURE, CLAUDE.md, PROJECT_STATUS

**Unabhängig, kann parallel zu Tasks 11–12 laufen, aber erst nach dem Zwischen-Review-2.**

**Brief:** Modul-Docstrings, CLAUDE.md-Updates, PROJECT_STATUS C.7 (Plan 2 Abschluss).

**Dateien:** `src/broad_scan.py` (Docstring), `src/db.py` (Tabellendoku),
`docs/ARCHITECTURE.md`, `docs/CLAUDE.md`, `docs/superpowers/specs/PROJECT_STATUS.md`

**Step 1:** Neue Modul-Docstrings:

```python
# src/broad_scan.py
"""Phase 2: News-Scan mit Websuche.

Ein Sonnet-Call pro Lauf über alle Überlebenden des Gates. Gibt news_strength
(0–3) pro Ticker, basierend auf Nachrichten-Katalysatoren. Die Ausgabe speist
direkt in den Cutoff (Spec § 4.6, § 4.7)."""
```

**Step 2:** CLAUDE.md erweitern mit Phase 2 / Phase 2b:

```markdown
## Phasen der Pipeline (nach Sprint 3C, Plan 2)

| # | Phase | Modul | API-Calls | Kosten |
|---|---|---|---|---|
| 1a | Skip-Gate | `data_collector` | 0 | — |
| 1b | Kurs-Sweep | `capital_provider` | ~n/20 | — |
| 1c/1d | Indikatoren + Tech-Signal | `indicators` | 0 | — |
| **2** | **Nachrichten-Scan** | `broad_scan` | 1 (Sonnet) | ~0,32 EUR |
| **2a** | **Cutoff** | `broad_scan` | 0 | — |
| **2b** | **Fundamentals (Kandidaten)** | `data_collector` | ≤50 (Finnhub) | ≤0,10 EUR |
| 3 | Tiefenanalyse | `deep_analysis` | ≤50 (Sonnet) | ~1,71 EUR |
...
```

**Step 3:** PROJECT_STATUS C.7 (Plan 2 Abschluss):

```markdown
## C.7 Plan 2 — Trichter

(Wird beim Plan-Abschluss ausgefüllt)
```

**Step 4:** ARCHITECTURE.md — neue Abschnitte:

```markdown
## Trichter (Candidate Selection)

Nach Phase 1 existieren die Überlebenden der Gate-Prüfung. Phase 2 fragt nach
Nachrichten und wendet den Cutoff an.

**Cutoff-Regel:** news_strength >= 1 ODER tech_strength >= TECH_MIN_FOR_DEEP.
Sortierung: (news, |change%|, tech, ticker), Deckel MAX_DEEP_ANALYSIS=50.

Warum Nachrichten vor Technik? News ist knapp, Technik liegt für jeden vor.
Die Reihenfolge ist eine bewusste Vermutung, nicht datengetrieben — 3D ersetzt
sie später (Spec § 18.2).
```

**Reviewer:** Prüft Konsistenz der Doku über alle Dateien.

---

## Abschluss-Review (nach Task 13)

**Wer:** Opus mit Fokus auf Schnittstellenkonsistenz und Integrationstests.

**Prüfung über:** `c978d70..HEAD` (Plan-1-Ende bis Plan-2-Ende), alle 13 Tasks.

**Kritische Punkte:**

1. **Gesamter Phase-1-Ablauf:** Gate → Sweep → Indikatoren → Technik-Signal
2. **Phase-2-Schnittstelle:** Scan-Input (ticker_datas format), Scan-Output,
   Cutoff-Eingabe, Cutoff-Ausgabe, Adapter
3. **Rohstoff-Ausnahmen:** Umgehen Gate+Sweep? Umgehen Scan? Umgehen Cutoff?
4. **Kosten:** Gesamtlauf + Einzelphasen gegen Spec § 13.2
5. **Regressions-Test:** Phase 3 / 3b / 4 / 4a laufen unverändert?
6. **DB-Konsistenz:** cutoff_log-Struktur, Migrations-Sicherheit, keine Altdaten beschrieben

**Befunde:** Wie Plan 1, als Diff gegen das Design.

---

## Datenbank-Zustand nach Plan 2

- `technical_indicators`: 40 Spalten (11 alt + 29 neu aus Plan 1)
- `predictions`: unverändert (neue Spalten kommen Plan 3)
- `cutoff_log`: neu, ~500 Zeilen pro Lauf (alle Ticker, mit Ranking)
- `fundamentals_cache`: `earnings_next_date` neu (TEXT)
- `price_history`: unverändert

Keine Altzeilen beschrieben, keine Datenverluste. Kopie-zu-Kopie Migration
zum Schutz.

---

## Migration zur Produktion

Nach erfolgreichem Testlauf (kostenkonsistent mit Spec § 13.2, keine neuen
Fehler):

1. **Lokales Commit:** `git add -A && git commit -m "..."`
2. **Push:** Manuell durch Korbinian (kein `git push` durch Claude)
3. **GitHub Actions:** Workflow triggert `pre_market`, `close`, ggf. `final_close`
4. **Monitoring:** Laufzeit, Kosten, Qualität der Cutoff-Auswahl
5. **Feedback an Plan 3:** Wie gut funktioniert der Trichter? Auf Nachrichtenlage
   optimiert? Tech-Stärke richtig gewichtet?

