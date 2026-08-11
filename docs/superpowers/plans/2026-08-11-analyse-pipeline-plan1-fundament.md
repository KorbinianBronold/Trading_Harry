# Analyse-Pipeline-Umbau, Plan 1: Fundament — Implementation Plan

> **Für agentische Bearbeiter:** ERFORDERLICHE SUB-SKILL: `superpowers:subagent-driven-development`
> (empfohlen) oder `superpowers:executing-plans`, um diesen Plan Task für Task umzusetzen.
> Die Schritte nutzen Checkbox-Syntax (`- [ ]`) zur Fortschrittsverfolgung.

**Goal:** Die 17 technischen Indikatoren und das deterministische Technik-Signal berechnen
und persistieren — **ohne jede Verhaltensänderung** an der Pipeline.

**Architecture:** Die Indikator-Mathematik wandert aus `src/data_collector.py` in ein eigenes
Modul `src/indicators.py` und wird von 9 auf 17 Indikatoren erweitert. Ein zweites neues
Modul `src/technical_signal.py` leitet daraus Richtung und zählbare Stärke ab. Beides wird
in Phase 1 berechnet und in `technical_indicators` geschrieben; **kein bestehender
Konsument liest die neuen Werte**. Der Plan ist damit gefahrlos einspielbar und beginnt
sofort, die Historie zu sammeln, auf der Sprint 3D später lernt.

**Tech Stack:** Python 3.12, pandas, `pandas_ta` 0.4.71b0 (bereits Abhängigkeit), SQLite,
pytest.

**Spec:** `docs/superpowers/specs/2026-08-11-analyse-pipeline-umbau-design.md`

## Einordnung

Die Spec zerfällt in drei unabhängig lieferbare Pläne. Dies ist der erste:

| Plan | Inhalt | Verhaltensänderung |
|---|---|---|
| **1 — Fundament (dieser Plan)** | Vorarbeiten, 17 Indikatoren, Technik-Signal, Schema | **keine** |
| 2 — Trichter | Kurs-Sweep, neue Reihenfolge, Phase-2-Scan, Cutoff, Wochenjob | Auswahl ändert sich |
| 3 — Analyse & Ranking | Batching, Qualifikation, Divergenz, Mail, Aggregate | Ergebnis ändert sich |

## Global Constraints

- **Timezone:** `ZoneInfo("Europe/Berlin")` in Python, `TZ="Europe/Berlin"` in Bash. Kein
  `datetime.now()` ohne Timezone.
- **Tests telefonieren nicht nach draussen.** Das Autouse-Fixture in `tests/conftest.py`
  sperrt auf Transport-Ebene. Nicht anfassen, nicht umgehen.
- **Migrations-Guards:** neue Spalten und Tabellen immer per `PRAGMA table_info()` bzw.
  `sqlite_master`-Abfrage prüfen, nie direkt `ALTER TABLE` ausführen.
- **Coverage ≥ 80 %** (`pytest tests/ --cov=src --cov-fail-under=80`). Bestehende Tests
  werden nicht gelöscht und nicht abgeschwächt.
- **Dokumentationspflicht:** jedes neue File bekommt eine Modul-Beschreibung, jede neue
  Funktion einen 1–2-Satz-Docstring.
- **Fehlende Werte sind `None`, niemals `0`.** Ein Indikator, für den die Historie nicht
  reicht, liefert `None`. Eine Null wäre eine erfundene Messung.
- **Niemals `git push`.** Committet wird lokal nach jedem Task.
- `random/` wird nicht angefasst.

---

## Dateistruktur

| Datei | Verantwortung | Status |
|---|---|---|
| `setup/probe_epics_batch.py` | Read-only-Sonde: akzeptiert `/api/v1/markets` eine `epics=`-Liste? | **neu** |
| `src/cost_tracker.py` | Kostenrechnung — Fix der doppelten Cache-Subtraktion | ändern |
| `src/indicators.py` | die 17 Indikator-Funktionen, reine Mathematik über ein OHLCV-DataFrame | **neu** |
| `src/technical_signal.py` | Richtung + zählbare Stärke aus den Indikatoren | **neu** |
| `src/data_collector.py` | Provider- und DB-Verdrahtung; Indikator-Mathematik entfällt | ändern |
| `src/db.py` | Schema `technical_indicators` + Migration; Ladefenster | ändern |
| `tests/unit/test_indicators.py` | Tests der Indikator-Funktionen | **neu** |
| `tests/unit/test_technical_signal.py` | Tabellengetriebene Tests des Signals | **neu** |
| `tests/unit/test_data_collector.py` | Indikator-Tests wandern raus, Rest bleibt | ändern |
| `tests/unit/test_cost_tracker.py` | Test für den `fresh_input`-Fix | ändern |

**Warum die Trennung:** `data_collector.py` hat 537 Zeilen und mischt Indikator-Mathematik
mit Provider- und DB-Verdrahtung. 17 statt 9 Indikatoren trieben sie auf ~750. Die
Indikator-Funktionen sind reine Funktionen über ein DataFrame und lassen sich isoliert
testen — sie gehören in ein eigenes Modul.

---

## Task 1: Read-only-Sonde — akzeptiert `/api/v1/markets` eine `epics=`-Liste?

Diese Sonde produziert **keinen Produktivcode**. Ihr Ergebnis entscheidet in Plan 2 über
die Implementierung des Kurs-Sweeps (Spec § 4.3.1) und wird in PROJECT_STATUS festgehalten.
Sie steht hier an erster Stelle, weil ihr Ergebnis vor jeder Zeile Sweep-Code vorliegen muss.

**Files:**
- Create: `setup/probe_epics_batch.py`
- Test: keiner — das Skript wird manuell gegen die Demo-API ausgeführt und schreibt nichts

**Interfaces:**
- Consumes: `src.providers.capital_provider.CapitalComProvider` (bestehende Session-Auth)
- Produces: nichts für spätere Tasks. Das Ergebnis ist ein Doku-Eintrag.

- [ ] **Step 1: Sonde schreiben**

```python
"""Read-only-Sonde: akzeptiert Capital.coms /markets-Endpunkt eine Liste von Epics?

Beantwortet die offene Frage aus der Spec (§ 4.3.1). Bei ~500 Tickern entscheidet sie
zwischen einem Sammelabruf (~10 Calls) und 500 Einzel-Calls. Schreibt nichts, weder in
die Datenbank noch bei Capital.com -- reine GET-Abfragen.

Aufruf:
    python setup/probe_epics_batch.py
"""
import sys
from pathlib import Path

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

import config
from src.providers.capital_provider import CapitalComProvider

# Bewusst MVP-Ticker mit bekannt gutem Epic-Mapping, damit ein Fehlschlag
# eindeutig am Listen-Parameter liegt und nicht am Symbol.
PROBE_TICKERS = ["AAPL", "MSFT", "NVDA"]


def main() -> int:
    """Fragt einen Epic einzeln und danach drei Epics als Liste ab und meldet,
    ob der Sammelabruf funktioniert."""
    provider = CapitalComProvider()
    epics = [provider._map(t) for t in PROBE_TICKERS]
    print(f"Epics: {dict(zip(PROBE_TICKERS, epics))}")

    # Referenz: der heute genutzte Einzelabruf
    single = requests.get(
        f"{config.CAPITAL_COM_BASE_URL}/api/v1/markets/{epics[0]}",
        headers=provider._headers(), timeout=30,
    )
    print(f"\nEinzelabruf /markets/{epics[0]}: HTTP {single.status_code}")
    if single.ok:
        print(f"  bid = {single.json().get('snapshot', {}).get('bid')}")

    # Kandidat: kommaseparierte Liste
    joined = ",".join(epics)
    batch = requests.get(
        f"{config.CAPITAL_COM_BASE_URL}/api/v1/markets",
        headers=provider._headers(), params={"epics": joined}, timeout=30,
    )
    print(f"\nSammelabruf /markets?epics={joined}: HTTP {batch.status_code}")
    if not batch.ok:
        print(f"  Body: {batch.text[:400]}")
        print("\nERGEBNIS: Sammelabruf NICHT verfuegbar -> Plan 2 nutzt Einzel-Calls.")
        return 1

    payload = batch.json()
    markets = payload.get("marketDetails") or payload.get("markets") or []
    print(f"  Antwort-Schluessel: {list(payload.keys())}")
    print(f"  Zurueckgelieferte Instrumente: {len(markets)} (angefragt: {len(epics)})")
    for m in markets:
        snap = m.get("snapshot", {})
        instrument = m.get("instrument", {})
        print(f"    {instrument.get('epic')}: bid={snap.get('bid')}")

    if len(markets) == len(epics):
        print("\nERGEBNIS: Sammelabruf FUNKTIONIERT -> Plan 2 nutzt Chunks.")
        print("  Naechste Frage fuer Plan 2: maximale Listenlaenge (50? 100?).")
        return 0

    print("\nERGEBNIS: Teilantwort -- vor Nutzung die Laengenbegrenzung ermitteln.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Sonde ausführen**

⚠️ **Braucht echte Capital.com-Zugangsdaten in der `.env`.** Read-only, kein Schreibpfad,
keine Order.

Run: `python setup/probe_epics_batch.py`

Erwartet: eine der drei Ergebniszeilen. Alle drei sind gültige Antworten.

- [ ] **Step 3: Ergebnis dokumentieren**

Ergebnis in `docs/superpowers/specs/PROJECT_STATUS.md` festhalten, neuer Absatz unter dem
Sprint-3C-Abschnitt. Muster der Read-only-Sonde aus P2.8: **was gemessen wurde, wann, und
was daraus folgt.** Skelett, die eckigen Klammern mit dem tatsächlichen Ergebnis füllen:

```markdown
**Read-only-Sonde gegen Capital.com ([DATUM], [UHRZEIT] UTC) — Sammelabruf von Kursen:**
- `GET /api/v1/markets/{epic}` (Einzelabruf, heutiger Pfad): HTTP [STATUS]
- `GET /api/v1/markets?epics=A,B,C`: HTTP [STATUS], [N] von 3 Instrumenten zurück
- **Folge für Plan 2:** [Sammelabruf nutzbar, Chunk-Größe noch zu ermitteln |
  nicht nutzbar, Einzel-Calls ohne Pause unter dem 600/min-Limit]
```

- [ ] **Step 4: Commit**

```bash
git add setup/probe_epics_batch.py docs/superpowers/specs/PROJECT_STATUS.md
git commit -m "chore: Sonde fuer Capital.com-Sammelabruf und ihr Ergebnis"
```

---

## Task 2: `cost_tracker` — Cache-Treffer werden zweimal abgezogen

Spec § 13.1. **Muss vor jeder Kostenmessung erledigt sein**, sonst misst der Testlauf mit
einem fehlerhaften Massstab.

Die Anthropic-API liefert `input_tokens` bereits als **ungecachten Rest**; die Gesamtgrösse
ist `input_tokens + cache_read + cache_creation`. `cost_tracker.py:52` subtrahiert
`cache_read` ein zweites Mal.

**Files:**
- Modify: `src/cost_tracker.py:52` und `src/cost_tracker.py:95`
- Test: `tests/unit/test_cost_tracker.py`

**Interfaces:**
- Consumes: nichts Neues
- Produces: `CostTracker.add_call()` rechnet unverändert in der Signatur, aber korrekt;
  `summary()["cache_hit_rate"]` bleibt im Bereich 0..1

- [ ] **Step 1: Failing Test schreiben**

```python
def test_input_tokens_are_already_the_uncached_remainder():
    """Die API liefert input_tokens als ungecachten Rest -- cache_read darf nicht
    ein zweites Mal abgezogen werden."""
    t = CostTracker(hard_cap_eur=100.0)
    t.add_call(
        model="claude-sonnet-4-6",
        input_tokens=3_000,        # bereits OHNE die gecachten Tokens
        output_tokens=0,
        cache_read_tokens=2_000,
    )
    # 3000 frische Input-Tokens zu 3 USD/Mio + 2000 Cache-Reads zu 0,30 USD/Mio
    expected_usd = 3_000 / 1e6 * 3.00 + 2_000 / 1e6 * 0.30
    assert t.total_eur == pytest.approx(expected_usd / 1.10)


def test_cache_hit_rate_stays_within_zero_and_one():
    """Trefferquote = Cache-Reads / Gesamt-Prompt, nicht / ungecachter Rest."""
    t = CostTracker(hard_cap_eur=100.0)
    t.add_call(
        model="claude-sonnet-4-6",
        input_tokens=1_000,
        output_tokens=0,
        cache_read_tokens=9_000,
    )
    rate = t.summary(run_type="pre_market", date="2026-08-11")["cache_hit_rate"]
    assert 0.0 <= rate <= 1.0
    assert rate == pytest.approx(9_000 / 10_000)
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_cost_tracker.py -k "uncached_remainder or within_zero" -v`

Erwartet: **beide FAIL.** Der erste, weil `fresh_input` auf 1000 statt 3000 kommt; der
zweite, weil `cache_hit_rate` bei 9.0 landet.

- [ ] **Step 3: Beide Stellen korrigieren**

In `src/cost_tracker.py`, `add_call()`:

```python
        # Die API liefert input_tokens bereits als ungecachten Rest; die
        # Gesamtgroesse des Prompts ist input_tokens + cache_read + cache_creation.
        # Ein zweiter Abzug von cache_read rechnete die Kosten systematisch zu
        # niedrig -- der Fehler wuchs mit der Cache-Trefferquote.
        usd_input  = input_tokens              / 1_000_000 * pricing["input"]
        usd_output = output_tokens             / 1_000_000 * pricing["output"]
```

Die Zeile `fresh_input = max(0, input_tokens - cache_read_tokens)` ersatzlos entfernen.

In `summary()`:

```python
        hit_rate = 0.0
        total_prompt = self.input_tokens + self.cache_read_tokens
        if total_prompt > 0:
            hit_rate = self.cache_read_tokens / total_prompt
```

- [ ] **Step 4: Tests laufen lassen**

Run: `pytest tests/unit/test_cost_tracker.py -v`

Erwartet: **alle PASS.** Falls ein bestehender Test bricht, weil er die alte Rechnung
festschrieb: der Test hat die Fehlannahme mit-zementiert und wird auf die korrekte
Erwartung gezogen — nicht der Fix zurückgenommen.

- [ ] **Step 5: Commit**

```bash
git add src/cost_tracker.py tests/unit/test_cost_tracker.py
git commit -m "fix: cost_tracker zog Cache-Treffer zweimal ab

Die Anthropic-API liefert input_tokens bereits als ungecachten Rest.
Der zusaetzliche Abzug rechnete jeden Lauf zu billig -- der Fehler wuchs
mit der Cache-Trefferquote. Betrifft auch cache_hit_rate, die dadurch
ueber 1 gehen konnte."
```

---

## Task 3: `src/indicators.py` — Extraktion der bestehenden neun

Reiner Umzug, **keine Verhaltensänderung**. Die neuen Indikatoren kommen in Task 4 und 5.

**Files:**
- Create: `src/indicators.py`
- Modify: `src/data_collector.py` (Zeilen 33–182 entfernen, Import ergänzen)
- Create: `tests/unit/test_indicators.py`
- Modify: `tests/unit/test_data_collector.py` (Indikator-Tests herausnehmen)

**Interfaces:**
- Produces: `compute_rsi_14`, `compute_rsi_trend`, `compute_macd_signal`,
  `compute_atr_pct`, `compute_bb_position`, `compute_sma_distance_pct`,
  `compute_volume_ratio`, `compute_intraday_range_pct`, `compute_price_changes`,
  `_last_finite` — alle mit unveränderten Signaturen aus `data_collector`.
  Konstanten `MIN_BARS_RSI`, `MIN_BARS_ATR`, `MIN_BARS_BB`, `MIN_BARS_VOL`,
  `MIN_BARS_INTRADAY`, `MIN_BARS_MACD` ziehen mit um.

- [ ] **Step 1: Neues Modul anlegen**

`src/indicators.py` mit Modul-Docstring und den **unverändert kopierten** Funktionen aus
`src/data_collector.py:19–182` (inklusive der `MIN_BARS_*`-Konstanten und `_last_finite`):

```python
"""Technische Indikatoren als reine Funktionen ueber ein OHLCV-DataFrame.

Jede Funktion nimmt einen DataFrame mit den Spalten Open/High/Low/Close/Volume
(gross geschrieben, wie db.load_price_history_from_db ihn liefert) und gibt einen
Skalar oder None zurueck. Kein Provider-, kein DB- und kein Netzzugriff.

REGEL: reicht die Historie fuer einen Indikator nicht, ist das Ergebnis None --
niemals 0. Eine Null waere eine erfundene Messung.
"""
import math

import pandas as pd
import pandas_ta as ta

MIN_BARS_RSI = 20
MIN_BARS_ATR = 20
MIN_BARS_BB = 25
MIN_BARS_VOL = 25
MIN_BARS_INTRADAY = 5
MIN_BARS_MACD = 35

# Ab hier die neun bestehenden Funktionen WORTGLEICH aus
# src/data_collector.py:33-182 uebernehmen, in dieser Reihenfolge:
#   _last_finite, compute_rsi_14, compute_rsi_trend, compute_macd_signal,
#   compute_atr_pct, compute_bb_position, compute_sma_distance_pct,
#   compute_volume_ratio, compute_intraday_range_pct, compute_price_changes
# Keine Zeile aendern -- dieser Task ist ein Umzug. Inhaltliche Aenderungen
# waeren in einem reinen Refactoring nicht nachvollziehbar und wuerden die
# Zusicherung "gleiche Testergebnisse wie vorher" (Step 4) entwerten.
```

⚠️ `GAP_SCAN_BARS` bleibt in `data_collector.py` — es steuert die Lückenerkennung, nicht
die Indikatorrechnung.

- [ ] **Step 2: `data_collector.py` auf das neue Modul umstellen**

Zeilen 19–182 entfernen und ersetzen durch:

```python
from src.indicators import (
    MIN_BARS_RSI,
    compute_atr_pct,
    compute_bb_position,
    compute_intraday_range_pct,
    compute_macd_signal,
    compute_price_changes,
    compute_rsi_14,
    compute_rsi_trend,
    compute_sma_distance_pct,
    compute_volume_ratio,
)
```

`GAP_SCAN_BARS = 200` bleibt stehen.

- [ ] **Step 3: Indikator-Tests umziehen**

Die Tests der neun Funktionen aus `tests/unit/test_data_collector.py` nach
`tests/unit/test_indicators.py` verschieben, Import auf `from src.indicators import ...`
umstellen. **Inhaltlich unverändert** — es ist ein Umzug, keine Neufassung.

⚠️ `test_process_ticker_skips_on_none_price_history` bleibt in
`test_data_collector.py`. Sein Name ist irreführend (Bug B-14), seine Zusicherungen sind
richtig. Nicht in diesem Task anfassen.

- [ ] **Step 4: Volle Suite laufen lassen**

Run: `pytest tests/ -q`

Erwartet: **alle PASS**, dieselbe Zahl wie vorher. Ein reiner Umzug ändert keine
Testergebnisse.

- [ ] **Step 5: Commit**

```bash
git add src/indicators.py src/data_collector.py tests/unit/test_indicators.py tests/unit/test_data_collector.py
git commit -m "refactor: Indikator-Mathematik nach src/indicators.py ausgelagert

Reiner Umzug ohne Verhaltensaenderung. data_collector.py mischte
Indikatorrechnung mit Provider- und DB-Verdrahtung; mit 17 statt 9
Indikatoren waere die Datei auf ~750 Zeilen gewachsen."
```

---

## Task 4: Ladefenster auf 220 Bars

SMA200 braucht 200 Bars, `load_price_history_from_db()` lädt genau 200 — der Wert ist damit
dauerhaft grenzwertig und häufig `None`. Ohne die Anhebung fällt ein Drittel des
Technik-Signals aus (Spec § 4.4).

**Files:**
- Modify: `src/db.py` (`load_price_history_from_db`, Default-`limit`)
- Modify: `src/data_collector.py:391` (Aufruf)
- Test: `tests/unit/test_db.py`

**Interfaces:**
- Produces: `db.load_price_history_from_db(conn, ticker, as_of_date, limit=220)`

- [ ] **Step 1: Failing Test schreiben**

```python
def test_sma200_computable_with_default_load_window(tmp_path):
    """Das Standard-Ladefenster muss SMA200 tragen, sonst faellt der
    SMA-Teilindikator des Technik-Signals dauerhaft aus."""
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    base = date(2025, 1, 1)
    for i in range(230):
        d = (base + timedelta(days=i)).isoformat()
        db.insert_price_bar_if_missing(
            conn, ticker="AAPL", date=d, open_=100.0, high=101.0,
            low=99.0, close=100.0 + i * 0.1, volume=1_000, source="test",
        )
    conn.commit()

    df = db.load_price_history_from_db(conn, "AAPL", as_of_date="2025-12-31")
    assert len(df) >= 200
    assert compute_sma_distance_pct(df, 200) is not None
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_db.py::test_sma200_computable_with_default_load_window -v`

Erwartet: **FAIL** — `len(df)` ist 200, `compute_sma_distance_pct(df, 200)` liefert einen
Wert nur, wenn `len(df) >= 200`; bei exakt 200 hängt es an einer einzigen Bar. Der Test
schlägt fehl, sobald das Fenster knapper ist als der längste Indikator.

- [ ] **Step 3: Default anheben**

In `src/db.py`:

```python
def load_price_history_from_db(
    conn: sqlite3.Connection, ticker: str, as_of_date: str, limit: int = 220,
) -> pd.DataFrame | None:
    """Laedt die letzten `limit` finalen Tagesbars bis `as_of_date`.

    220 statt 200: der laengste Indikator (SMA200) braucht 200 Bars, und bei
    exakt 200 haengt sein Wert an einer einzigen fehlenden Bar. Die Reserve
    haelt den SMA-Teilindikator des Technik-Signals verfuegbar.
    """
```

In `src/data_collector.py` den Aufruf entsprechend anpassen (`limit=220`).

- [ ] **Step 4: Tests laufen lassen**

Run: `pytest tests/unit/test_db.py tests/unit/test_data_collector.py -q`

Erwartet: **alle PASS.**

- [ ] **Step 5: Commit**

```bash
git add src/db.py src/data_collector.py tests/unit/test_db.py
git commit -m "fix: Ladefenster auf 220 Bars, damit SMA200 zuverlaessig traegt"
```

---

## Task 5: Neue Trend-Indikatoren

EMA(50), MACD-Rohwerte, ADX(14), Parabolic SAR, Ichimoku.

⚠️ **Die `pandas_ta`-Spaltennamen und Rückgabetypen sind am 2026-08-11 gegen Version
0.4.71b0 verifiziert.** `ichimoku()` gibt ein **Tupel** zurück, ADX heisst `DMP_14`/`DMN_14`
(nicht `DI_plus`/`DI_minus`), und `cci`/`mom`/`trix` haben andere Default-Längen als die
Spec verlangt — die Längen müssen explizit übergeben werden.

**Files:**
- Modify: `src/indicators.py`
- Test: `tests/unit/test_indicators.py`

**Interfaces:**
- Produces:
  - `compute_ema_distance_pct(df, length) -> float | None`
  - `compute_macd_raw(df) -> dict` mit Schlüsseln `macd_line`, `macd_signal_line`, `macd_hist`
  - `compute_adx(df) -> dict` mit Schlüsseln `adx_14`, `di_plus`, `di_minus`
  - `compute_psar(df) -> dict` mit Schlüsseln `psar_value`, `psar_dir` (`"long"`/`"short"`/`None`)
  - `compute_ichimoku(df) -> dict` mit Schlüsseln `ichi_tenkan`, `ichi_kijun`,
    `ichi_senkou_a`, `ichi_senkou_b`, `ichi_chikou`
  - Konstanten `MIN_BARS_ADX = 28`, `MIN_BARS_ICHIMOKU = 78`, `MIN_BARS_EMA50 = 50`

- [ ] **Step 1: Gemeinsames Fixture und Failing Tests schreiben**

```python
import numpy as np
import pandas as pd
import pytest

from src import indicators as ind


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    """260 deterministische Tagesbars mit leichtem Aufwaertsdrift."""
    n = 260
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    rng = np.random.default_rng(7)
    close = pd.Series(100 + np.cumsum(rng.normal(0.05, 1.0, n)), index=idx)
    return pd.DataFrame({
        "Open": close.shift(1).fillna(close.iloc[0]),
        "High": close + abs(rng.normal(0, 1, n)),
        "Low": close - abs(rng.normal(0, 1, n)),
        "Close": close,
        "Volume": pd.Series(rng.integers(100_000, 500_000, n), index=idx),
    })


def test_macd_raw_returns_three_finite_values(ohlcv):
    out = ind.compute_macd_raw(ohlcv)
    assert set(out) == {"macd_line", "macd_signal_line", "macd_hist"}
    assert all(isinstance(v, float) for v in out.values())
    # Das Histogramm ist definitionsgemaess die Differenz der beiden Linien.
    assert out["macd_hist"] == pytest.approx(
        out["macd_line"] - out["macd_signal_line"], abs=1e-6
    )


def test_macd_raw_returns_nones_on_short_history(ohlcv):
    out = ind.compute_macd_raw(ohlcv.iloc[:10])
    assert out == {"macd_line": None, "macd_signal_line": None, "macd_hist": None}


def test_adx_returns_index_and_both_directional_lines(ohlcv):
    out = ind.compute_adx(ohlcv)
    assert set(out) == {"adx_14", "di_plus", "di_minus"}
    assert 0.0 <= out["adx_14"] <= 100.0


def test_psar_direction_is_long_or_short_never_both(ohlcv):
    out = ind.compute_psar(ohlcv)
    assert out["psar_dir"] in ("long", "short", None)
    if out["psar_dir"] is not None:
        assert out["psar_value"] is not None


def test_ichimoku_returns_five_lines(ohlcv):
    out = ind.compute_ichimoku(ohlcv)
    assert set(out) == {
        "ichi_tenkan", "ichi_kijun", "ichi_senkou_a",
        "ichi_senkou_b", "ichi_chikou",
    }


def test_ichimoku_returns_nones_on_short_history(ohlcv):
    out = ind.compute_ichimoku(ohlcv.iloc[:30])
    assert all(v is None for v in out.values())


def test_ema_distance_is_percentage_of_the_average(ohlcv):
    out = ind.compute_ema_distance_pct(ohlcv, 50)
    assert isinstance(out, float)
    assert -100.0 < out < 100.0
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_indicators.py -k "macd_raw or adx or psar or ichimoku or ema_distance" -v`

Erwartet: **alle FAIL** mit `AttributeError: module 'src.indicators' has no attribute ...`

- [ ] **Step 3: Implementieren**

In `src/indicators.py` ergänzen:

```python
MIN_BARS_EMA50 = 50
MIN_BARS_ADX = 28
MIN_BARS_ICHIMOKU = 78

# Spaltennamen von pandas_ta 0.4.71b0, am 2026-08-11 gegen die installierte
# Version verifiziert. Sie enthalten die Parameter im Namen -- aendert sich eine
# Laenge, aendert sich der Spaltenname mit.
_MACD_LINE, _MACD_HIST, _MACD_SIGNAL = "MACD_12_26_9", "MACDh_12_26_9", "MACDs_12_26_9"
_ADX, _DMP, _DMN = "ADX_14", "DMP_14", "DMN_14"
_PSAR_LONG, _PSAR_SHORT = "PSARl_0.02_0.2", "PSARs_0.02_0.2"


def compute_ema_distance_pct(df: pd.DataFrame, length: int) -> float | None:
    """Abstand des Schlusskurses zum EMA der Laenge `length` in Prozent."""
    if len(df) < length:
        return None
    ema = ta.ema(df["Close"], length=length)
    last = _last_finite(ema)
    close = _last_finite(df["Close"])
    if last is None or not close:
        return None
    return round((close - last) / last * 100, 3)


def compute_macd_raw(df: pd.DataFrame) -> dict[str, float | None]:
    """MACD-Linie, Signallinie und Histogramm als Rohwerte.

    Ergaenzt compute_macd_signal(), das nur die Kreuzung meldet und deshalb an
    den meisten Tagen 'neutral' liefert -- als Dauersignal unbrauchbar. Das
    Vorzeichen des Histogramms traegt dagegen jeden Tag eine Aussage.
    """
    empty = {"macd_line": None, "macd_signal_line": None, "macd_hist": None}
    if len(df) < MIN_BARS_MACD:
        return empty
    macd = ta.macd(df["Close"])
    if macd is None or macd.empty:
        return empty
    return {
        "macd_line":        _last_finite(macd[_MACD_LINE]),
        "macd_signal_line": _last_finite(macd[_MACD_SIGNAL]),
        "macd_hist":        _last_finite(macd[_MACD_HIST]),
    }


def compute_adx(df: pd.DataFrame) -> dict[str, float | None]:
    """ADX(14) als Trendstaerke plus die beiden Richtungslinien DI+ und DI-."""
    empty = {"adx_14": None, "di_plus": None, "di_minus": None}
    if len(df) < MIN_BARS_ADX:
        return empty
    adx = ta.adx(df["High"], df["Low"], df["Close"])
    if adx is None or adx.empty:
        return empty
    return {
        "adx_14":   _last_finite(adx[_ADX]),
        "di_plus":  _last_finite(adx[_DMP]),
        "di_minus": _last_finite(adx[_DMN]),
    }


def compute_psar(df: pd.DataFrame) -> dict[str, float | str | None]:
    """Parabolic SAR: Stopp-Niveau und die Richtung, in der es steht.

    pandas_ta liefert zwei getrennte Spalten -- PSARl traegt Werte im
    Aufwaertstrend, PSARs im Abwaertstrend, die jeweils andere ist NaN. Die
    Richtung ergibt sich daraus, welche der beiden belegt ist.
    """
    empty: dict[str, float | str | None] = {"psar_value": None, "psar_dir": None}
    if len(df) < 10:
        return empty
    psar = ta.psar(df["High"], df["Low"], df["Close"])
    if psar is None or psar.empty:
        return empty
    long_v = _last_finite(psar[_PSAR_LONG]) if _PSAR_LONG in psar else None
    short_v = _last_finite(psar[_PSAR_SHORT]) if _PSAR_SHORT in psar else None
    if long_v is not None:
        return {"psar_value": long_v, "psar_dir": "long"}
    if short_v is not None:
        return {"psar_value": short_v, "psar_dir": "short"}
    return empty


def compute_ichimoku(df: pd.DataFrame) -> dict[str, float | None]:
    """Die fuenf Ichimoku-Linien.

    ta.ichimoku() gibt ein TUPEL zurueck: (historische Linien, in die Zukunft
    projizierte Spans). Nur der erste Teil ist hier gemeint.
    """
    keys = ("ichi_tenkan", "ichi_kijun", "ichi_senkou_a",
            "ichi_senkou_b", "ichi_chikou")
    empty = dict.fromkeys(keys, None)
    if len(df) < MIN_BARS_ICHIMOKU:
        return empty
    result = ta.ichimoku(df["High"], df["Low"], df["Close"])
    hist = result[0] if isinstance(result, tuple) else result
    if hist is None or hist.empty:
        return empty
    return {
        "ichi_tenkan":   _last_finite(hist["ITS_9"]),
        "ichi_kijun":    _last_finite(hist["IKS_26"]),
        "ichi_senkou_a": _last_finite(hist["ISA_9"]),
        "ichi_senkou_b": _last_finite(hist["ISB_26"]),
        "ichi_chikou":   _last_finite(hist["ICS_26"]),
    }
```

- [ ] **Step 4: Tests laufen lassen**

Run: `pytest tests/unit/test_indicators.py -v`

Erwartet: **alle PASS.**

- [ ] **Step 5: Commit**

```bash
git add src/indicators.py tests/unit/test_indicators.py
git commit -m "feat: Trend-Indikatoren EMA50, MACD-Rohwerte, ADX, PSAR, Ichimoku"
```

---

## Task 6: Neue Momentum-, Volatilitäts- und Volumen-Indikatoren

Stochastic, Williams %R, CCI(20), Momentum(12), TRIX(15,9), Bollinger-Bänder als Rohwerte,
ATR absolut, Donchian(20), OBV.

**Files:**
- Modify: `src/indicators.py`
- Test: `tests/unit/test_indicators.py`

**Interfaces:**
- Produces:
  - `compute_stochastic(df) -> dict` mit `stoch_k`, `stoch_d`
  - `compute_willr(df) -> float | None`
  - `compute_cci(df) -> float | None` (Länge 20)
  - `compute_momentum(df) -> float | None` (Länge 12)
  - `compute_trix(df) -> dict` mit `trix`, `trix_signal` (15, 9)
  - `compute_bollinger_raw(df) -> dict` mit `bb_upper`, `bb_lower`, `bb_width`
  - `compute_atr_abs(df) -> float | None`
  - `compute_donchian(df) -> dict` mit `donch_upper`, `donch_mid`, `donch_lower`
  - `compute_obv(df) -> float | None`

- [ ] **Step 1: Failing Tests schreiben**

```python
def test_stochastic_returns_k_and_d_in_range(ohlcv):
    out = ind.compute_stochastic(ohlcv)
    assert set(out) == {"stoch_k", "stoch_d"}
    assert 0.0 <= out["stoch_k"] <= 100.0
    assert 0.0 <= out["stoch_d"] <= 100.0


def test_willr_is_negative_by_definition(ohlcv):
    """Williams %R laeuft definitionsgemaess von -100 bis 0."""
    assert -100.0 <= ind.compute_willr(ohlcv) <= 0.0


def test_cci_uses_length_20_not_the_library_default(ohlcv):
    """Die Spec verlangt CCI(20); pandas_ta defaultet auf 14."""
    out = ind.compute_cci(ohlcv)
    assert isinstance(out, float)
    # Gegenprobe: mit Laenge 14 kommt ein anderer Wert heraus.
    import pandas_ta as ta
    other = ta.cci(ohlcv["High"], ohlcv["Low"], ohlcv["Close"], length=14)
    assert out != pytest.approx(float(other.iloc[-1]))


def test_momentum_uses_length_12(ohlcv):
    out = ind.compute_momentum(ohlcv)
    expected = ohlcv["Close"].iloc[-1] - ohlcv["Close"].iloc[-13]
    assert out == pytest.approx(expected, abs=1e-6)


def test_trix_returns_line_and_signal(ohlcv):
    out = ind.compute_trix(ohlcv)
    assert set(out) == {"trix", "trix_signal"}
    assert all(isinstance(v, float) for v in out.values())


def test_bollinger_width_is_upper_minus_lower(ohlcv):
    out = ind.compute_bollinger_raw(ohlcv)
    assert out["bb_width"] == pytest.approx(out["bb_upper"] - out["bb_lower"], abs=1e-6)


def test_donchian_mid_lies_between_the_channels(ohlcv):
    out = ind.compute_donchian(ohlcv)
    assert out["donch_lower"] <= out["donch_mid"] <= out["donch_upper"]


def test_obv_is_computed_from_the_broker_volume_proxy(ohlcv):
    """OBV beruht auf lastTradedVolume -- einem CFD-Broker-Proxy, nicht auf
    Boersenvolumen. Der Test haelt nur fest, dass ein Wert entsteht."""
    assert isinstance(ind.compute_obv(ohlcv), float)


def test_all_new_indicators_return_none_on_empty_history():
    empty_df = pd.DataFrame(
        {c: [] for c in ("Open", "High", "Low", "Close", "Volume")}
    )
    assert ind.compute_willr(empty_df) is None
    assert ind.compute_cci(empty_df) is None
    assert ind.compute_momentum(empty_df) is None
    assert ind.compute_atr_abs(empty_df) is None
    assert ind.compute_obv(empty_df) is None
    assert ind.compute_stochastic(empty_df) == {"stoch_k": None, "stoch_d": None}
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_indicators.py -k "stochastic or willr or cci or momentum or trix or bollinger or donchian or obv or empty_history" -v`

Erwartet: **alle FAIL** mit `AttributeError`.

- [ ] **Step 3: Implementieren**

```python
MIN_BARS_STOCH = 20
MIN_BARS_TRIX = 50
MIN_BARS_DONCHIAN = 20

_CCI_LENGTH, _MOM_LENGTH = 20, 12
_TRIX_LENGTH, _TRIX_SIGNAL = 15, 9


def compute_stochastic(df: pd.DataFrame) -> dict[str, float | None]:
    """Stochastik-Oszillator: %K und %D."""
    empty = {"stoch_k": None, "stoch_d": None}
    if len(df) < MIN_BARS_STOCH:
        return empty
    st = ta.stoch(df["High"], df["Low"], df["Close"])
    if st is None or st.empty:
        return empty
    return {
        "stoch_k": _last_finite(st["STOCHk_14_3_3"]),
        "stoch_d": _last_finite(st["STOCHd_14_3_3"]),
    }


def compute_willr(df: pd.DataFrame) -> float | None:
    """Williams %R(14). Laeuft definitionsgemaess von -100 bis 0."""
    if len(df) < 20:
        return None
    return _last_finite(ta.willr(df["High"], df["Low"], df["Close"]))


def compute_cci(df: pd.DataFrame) -> float | None:
    """CCI mit Laenge 20. pandas_ta defaultet auf 14 -- die Laenge wird
    ausdruecklich uebergeben, weil die Spec 20 verlangt."""
    if len(df) < _CCI_LENGTH:
        return None
    return _last_finite(
        ta.cci(df["High"], df["Low"], df["Close"], length=_CCI_LENGTH)
    )


def compute_momentum(df: pd.DataFrame) -> float | None:
    """Momentum(12): absolute Kursdifferenz zu vor 12 Bars. pandas_ta
    defaultet auf 10."""
    if len(df) <= _MOM_LENGTH:
        return None
    return _last_finite(ta.mom(df["Close"], length=_MOM_LENGTH))


def compute_trix(df: pd.DataFrame) -> dict[str, float | None]:
    """TRIX(15) mit Signallinie(9). pandas_ta defaultet auf 30."""
    empty = {"trix": None, "trix_signal": None}
    if len(df) < MIN_BARS_TRIX:
        return empty
    tr = ta.trix(df["Close"], length=_TRIX_LENGTH, signal=_TRIX_SIGNAL)
    if tr is None or tr.empty:
        return empty
    return {
        "trix":        _last_finite(tr[f"TRIX_{_TRIX_LENGTH}_{_TRIX_SIGNAL}"]),
        "trix_signal": _last_finite(tr[f"TRIXs_{_TRIX_LENGTH}_{_TRIX_SIGNAL}"]),
    }


def compute_bollinger_raw(df: pd.DataFrame) -> dict[str, float | None]:
    """Oberes und unteres Bollinger-Band als Kursniveaus plus deren Abstand.

    Ergaenzt compute_bb_position(), das nur die relative Lage im Band meldet
    und die Bandbreite -- also das Volatilitaetsniveau -- wegwirft.
    """
    empty = {"bb_upper": None, "bb_lower": None, "bb_width": None}
    if len(df) < MIN_BARS_BB:
        return empty
    bb = ta.bbands(df["Close"], length=20)
    if bb is None or bb.empty:
        return empty
    lower, upper = bb.iloc[-1, 0], bb.iloc[-1, 2]
    if pd.isna(lower) or pd.isna(upper):
        return empty
    return {
        "bb_upper": round(float(upper), 4),
        "bb_lower": round(float(lower), 4),
        "bb_width": round(float(upper - lower), 4),
    }


def compute_atr_abs(df: pd.DataFrame) -> float | None:
    """ATR(14) als absoluter Kursbetrag. compute_atr_pct() liefert denselben
    Wert relativ zum Schlusskurs; fuer Abstandsrechnungen wird der absolute
    gebraucht."""
    if len(df) < MIN_BARS_ATR:
        return None
    return _last_finite(ta.atr(df["High"], df["Low"], df["Close"], length=14))


def compute_donchian(df: pd.DataFrame) -> dict[str, float | None]:
    """Donchian-Kanal(20): oberes, mittleres und unteres Band."""
    empty = {"donch_upper": None, "donch_mid": None, "donch_lower": None}
    if len(df) < MIN_BARS_DONCHIAN:
        return empty
    dc = ta.donchian(df["High"], df["Low"])
    if dc is None or dc.empty:
        return empty
    return {
        "donch_lower": _last_finite(dc["DCL_20_20"]),
        "donch_mid":   _last_finite(dc["DCM_20_20"]),
        "donch_upper": _last_finite(dc["DCU_20_20"]),
    }


def compute_obv(df: pd.DataFrame) -> float | None:
    """On-Balance-Volume.

    WARNUNG: beruht auf `lastTradedVolume` von Capital.com -- einem
    CFD-Broker-Proxy, NICHT auf Boersenvolumen. Der Wert beschreibt Capital.coms
    eigenen Handelsfluss. Als Richtungsmass brauchbar, als Niveauaussage nicht.
    """
    if len(df) < MIN_BARS_VOL:
        return None
    return _last_finite(ta.obv(df["Close"], df["Volume"]))
```

- [ ] **Step 4: Tests laufen lassen**

Run: `pytest tests/unit/test_indicators.py -v`

Erwartet: **alle PASS.**

- [ ] **Step 5: Commit**

```bash
git add src/indicators.py tests/unit/test_indicators.py
git commit -m "feat: Momentum-, Volatilitaets- und Volumen-Indikatoren ergaenzt

Stochastic, Williams %R, CCI(20), Momentum(12), TRIX(15,9), Bollinger-
Rohwerte, ATR absolut, Donchian(20), OBV. CCI, Momentum und TRIX bekommen
die Laenge ausdruecklich uebergeben -- pandas_ta defaultet auf andere Werte
als die Spec verlangt."
```

---

## Task 7: Schema — 29 neue Spalten in `technical_indicators`

**Files:**
- Modify: `src/db.py` (`SCHEMA`-Konstante und `_apply_migrations`)
- Modify: `src/data_collector.py` (`_persist_indicators`, `_process_ticker`)
- Test: `tests/unit/test_db.py`, `tests/unit/test_data_collector.py`

**Interfaces:**
- Consumes: alle `compute_*`-Funktionen aus Task 5 und 6
- Produces: `technical_indicators` trägt die 29 neuen Spalten;
  `_process_ticker()` liefert sie im `td`-Dict unter denselben Namen

- [ ] **Step 1: Failing Test schreiben**

```python
NEW_INDICATOR_COLUMNS = [
    "ema_50_dist_pct",
    "macd_line", "macd_signal_line", "macd_hist",
    "adx_14", "di_plus", "di_minus",
    "psar_value", "psar_dir",
    "ichi_tenkan", "ichi_kijun", "ichi_senkou_a", "ichi_senkou_b", "ichi_chikou",
    "stoch_k", "stoch_d",
    "willr_14", "cci_20", "mom_12",
    "trix", "trix_signal",
    "bb_upper", "bb_lower", "bb_width",
    "atr_abs",
    "donch_upper", "donch_mid", "donch_lower",
    "obv",
]


def test_technical_indicators_carries_the_new_columns(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(technical_indicators)")}
    missing = set(NEW_INDICATOR_COLUMNS) - cols
    assert not missing, f"Fehlende Spalten: {sorted(missing)}"


def test_migration_adds_columns_to_an_existing_table(tmp_path):
    """Die Migration muss auf einer ALTEN Tabelle greifen, nicht nur auf einer
    frisch angelegten -- sonst bleibt die Produktions-DB zurueck."""
    path = str(tmp_path / "old.db")
    conn = db.connect(path)
    conn.executescript("""
        CREATE TABLE technical_indicators (
            ticker TEXT NOT NULL, date TEXT NOT NULL,
            rsi_14 REAL, macd_signal TEXT, atr_pct REAL,
            bb_position REAL, above_sma20 REAL, above_sma50 REAL,
            above_sma200 REAL, volume_ratio REAL,
            UNIQUE(ticker, date)
        );
    """)
    conn.commit()

    db.init_schema(conn)

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(technical_indicators)")}
    assert set(NEW_INDICATOR_COLUMNS) <= cols
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_db.py -k "new_columns or migration_adds" -v`

Erwartet: **beide FAIL** mit der Liste der fehlenden Spalten.

- [ ] **Step 3: Schema und Migration ergänzen**

In der `SCHEMA`-Konstante von `src/db.py` die `CREATE TABLE technical_indicators` um die
29 Spalten erweitern (alle `REAL` ausser `psar_dir TEXT`). Es sind 29 und nicht 17, weil
mehrere Indikatoren mehrwertig sind: MACD und ADX je drei Spalten, Ichimoku fünf,
Bollinger und Donchian je drei, PSAR, Stochastik und TRIX je zwei.

In `_apply_migrations()` nach dem bestehenden `intraday_range_pct`-Block:

```python
    # Sprint 3C / Analyse-Pipeline-Umbau: die 17 Indikatoren aus der Spec.
    # Additiv und NULL-faehig -- Altzeilen bleiben lesbar, sie tragen fuer die
    # neuen Spalten schlicht NULL.
    existing = {
        r["name"] for r in conn.execute("PRAGMA table_info(technical_indicators)")
    }
    for column, sql_type in (
        ("ema_50_dist_pct", "REAL"),
        ("macd_line", "REAL"), ("macd_signal_line", "REAL"), ("macd_hist", "REAL"),
        ("adx_14", "REAL"), ("di_plus", "REAL"), ("di_minus", "REAL"),
        ("psar_value", "REAL"), ("psar_dir", "TEXT"),
        ("ichi_tenkan", "REAL"), ("ichi_kijun", "REAL"),
        ("ichi_senkou_a", "REAL"), ("ichi_senkou_b", "REAL"), ("ichi_chikou", "REAL"),
        ("stoch_k", "REAL"), ("stoch_d", "REAL"),
        ("willr_14", "REAL"), ("cci_20", "REAL"), ("mom_12", "REAL"),
        ("trix", "REAL"), ("trix_signal", "REAL"),
        ("bb_upper", "REAL"), ("bb_lower", "REAL"), ("bb_width", "REAL"),
        ("atr_abs", "REAL"),
        ("donch_upper", "REAL"), ("donch_mid", "REAL"), ("donch_lower", "REAL"),
        ("obv", "REAL"),
    ):
        if column not in existing:
            conn.execute(
                f"ALTER TABLE technical_indicators ADD COLUMN {column} {sql_type}"
            )
```

- [ ] **Step 4: Berechnung und Persistenz verdrahten**

In `src/data_collector.py`, `_process_ticker()`, das `td`-Dict erweitern:

```python
        **compute_macd_raw(df),
        **compute_adx(df),
        **compute_psar(df),
        **compute_ichimoku(df),
        **compute_stochastic(df),
        **compute_trix(df),
        **compute_bollinger_raw(df),
        **compute_donchian(df),
        "ema_50_dist_pct": compute_ema_distance_pct(df, 50),
        "willr_14":        compute_willr(df),
        "cci_20":          compute_cci(df),
        "mom_12":          compute_momentum(df),
        "atr_abs":         compute_atr_abs(df),
        "obv":             compute_obv(df),
```

`_persist_indicators()` um dieselben Schlüssel erweitern. ⚠️ `upsert_technical_indicators()`
baut die Spaltenliste aus den Dict-Schlüsseln — jeder Schlüssel muss eine Spalte haben,
sonst schlägt das `INSERT` fehl.

- [ ] **Step 5: Test für die Persistenz schreiben und laufen lassen**

⚠️ **Die Helfer existieren bereits** in `tests/unit/test_data_collector.py` — keine neuen
erfinden: `_df_monotonic_up(rows)` (Zeile 12), `_seed_price_history(conn, ticker, df)`
(136), `_good_provider(df, fundamentals)` (156), `_earnings_provider(...)` (175), dazu die
Fixture `in_memory_db`.

```python
def test_process_ticker_persists_the_new_indicators(in_memory_db):
    """Ein Durchlauf muss die neuen Spalten tatsaechlich fuellen -- nicht nur
    die Tabelle anlegen."""
    conn = in_memory_db
    df = _df_monotonic_up(rows=250)
    _seed_price_history(conn, "AAPL", df)
    # Datum aus dem Fixture ableiten statt hart zu setzen: so bleibt der Test
    # unabhaengig davon, welche Kalendertage _df_monotonic_up erzeugt.
    as_of = df.index[-1].strftime("%Y-%m-%d")

    td = data_collector._process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(),
        conn=conn, date=as_of, run_type="pre_market",
    )

    assert td is not None
    row = conn.execute(
        "SELECT * FROM technical_indicators WHERE ticker=? AND date=?",
        ("AAPL", as_of),
    ).fetchone()
    assert row["macd_line"] is not None
    assert row["adx_14"] is not None
    assert row["obv"] is not None
    assert row["ichi_kijun"] is not None
```

Run: `pytest tests/unit/test_db.py tests/unit/test_data_collector.py -v`

Erwartet: **alle PASS.**

- [ ] **Step 6: Migration gegen eine Kopie der echten Datenbank prüfen**

⚠️ **Nie gegen `data/tracking.db` selbst.**

```bash
cp data/tracking.db /tmp/migrationstest.db
python -c "
from src import db
c = db.connect('/tmp/migrationstest.db'); db.init_schema(c)
cols = [r['name'] for r in c.execute('PRAGMA table_info(technical_indicators)')]
print(f'{len(cols)} Spalten'); assert 'macd_line' in cols and 'obv' in cols
print('OK')
"
```

Erwartet: `OK`, und die Zeilenzahl der Tabelle ist unverändert.

- [ ] **Step 7: Commit**

```bash
git add src/db.py src/data_collector.py tests/unit/test_db.py tests/unit/test_data_collector.py
git commit -m "feat: 26 Indikator-Spalten in technical_indicators, migrationsgeschuetzt

Nur vier der Indikatoren speisen zunaechst das Technik-Signal. Der Wert der
uebrigen entsteht dadurch, dass sie ab jetzt mitlaufen -- beginnt Sprint 3D
erst mit dem Schreiben, beginnt es mit null Historie."
```

---

## Task 8: `src/technical_signal.py` — Richtung und zählbare Stärke

Spec § 4.5. **Kein Konsument in diesem Plan** — das Signal wird berechnet, persistiert
(Plan 3) und getestet, steuert aber noch nichts.

**Files:**
- Create: `src/technical_signal.py`
- Create: `tests/unit/test_technical_signal.py`
- Modify: `config.py` (Schwellen)

**Interfaces:**
- Consumes: das `td`-Dict aus `_process_ticker()` (Schlüssel `rsi_14`, `rsi_trend`,
  `macd_line`, `macd_signal_line`, `above_sma50`, `above_sma200`, `adx_14`)
- Produces:
  ```python
  @dataclass(frozen=True)
  class TechnicalSignal:
      direction: str      # "long" | "short" | "neutral"
      agreement: int      # 0..3, Zahl der uebereinstimmenden Teilindikatoren
      adx_band: str       # "weak" | "normal" | "strong"
      strength: int       # 1..4, 0 bei direction == "neutral"

  def compute(td: dict) -> TechnicalSignal
  ```

- [ ] **Step 1: Failing Tests schreiben**

```python
import pytest

from src.technical_signal import TechnicalSignal, compute


def _td(**overrides) -> dict:
    """Neutraler Ausgangs-Snapshot; jeder Test setzt nur, was er braucht."""
    base = {
        "rsi_14": 50.0, "rsi_trend": "neutral",
        "macd_line": 0.0, "macd_signal_line": 0.0,
        "above_sma50": 0.0, "above_sma200": 0.0,
        "adx_14": 22.0,
    }
    base.update(overrides)
    return base


def _bullish(**overrides) -> dict:
    return _td(
        rsi_14=60.0, rsi_trend="rising",
        macd_line=1.0, macd_signal_line=0.5,
        above_sma50=2.0, above_sma200=5.0,
        **overrides,
    )


def _bearish(**overrides) -> dict:
    return _td(
        rsi_14=40.0, rsi_trend="falling",
        macd_line=-1.0, macd_signal_line=-0.5,
        above_sma50=-2.0, above_sma200=-5.0,
        **overrides,
    )


def test_all_three_agree_long():
    sig = compute(_bullish())
    assert sig.direction == "long"
    assert sig.agreement == 3


def test_all_three_agree_short():
    sig = compute(_bearish())
    assert sig.direction == "short"
    assert sig.agreement == 3


def test_majority_of_two_still_gives_a_direction():
    """RSI und MACD bullish, SMA-Trend neutral -> Mehrheit traegt."""
    sig = compute(_bullish(above_sma50=0.0, above_sma200=-1.0))
    assert sig.direction == "long"
    assert sig.agreement == 2


def test_no_majority_is_neutral():
    sig = compute(_td())
    assert sig.direction == "neutral"
    assert sig.strength == 0


def test_strong_adx_raises_strength_by_one():
    weak = compute(_bullish(adx_14=22.0))
    strong = compute(_bullish(adx_14=30.0))
    assert strong.adx_band == "strong"
    assert strong.strength == weak.strength + 1
    assert strong.strength <= 4


def test_weak_adx_caps_strength_at_one_without_removing_direction():
    """ADX ist Verstaerkungsfaktor, nicht Filter: die Richtung bleibt."""
    sig = compute(_bullish(adx_14=15.0))
    assert sig.adx_band == "weak"
    assert sig.direction == "long"
    assert sig.strength == 1


def test_missing_sma200_degrades_to_neutral_vote_not_to_failure():
    """Unter 200 Bars ist SMA200 None. Der Teilindikator stimmt dann neutral --
    nicht 'fehlend' -- und die Richtung entsteht aus RSI und MACD."""
    sig = compute(_bullish(above_sma200=None))
    assert sig.direction == "long"
    assert sig.agreement == 2


def test_missing_adx_is_treated_as_normal_band():
    sig = compute(_bullish(adx_14=None))
    assert sig.adx_band == "normal"


def test_completely_empty_snapshot_is_neutral():
    sig = compute({})
    assert sig.direction == "neutral"
    assert sig.agreement == 0
    assert sig.strength == 0
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_technical_signal.py -v`

Erwartet: **alle FAIL** mit `ModuleNotFoundError: No module named 'src.technical_signal'`

- [ ] **Step 3: Konstanten in `config.py` ergänzen**

```python
# Analyse-Pipeline-Umbau: Schwellen des deterministischen Technik-Signals.
# ADX misst Trendstaerke, nicht Richtung: unter 20 gilt der Markt als trendlos
# und die Signalstaerke wird gedeckelt, ueber 25 als klar trendend und die
# Staerke steigt. Bewusst Verstaerkungsfaktor, KEIN Filter -- ein Signal in
# einem trendlosen Markt landet weit unten, wird aber nicht verworfen.
ADX_WEAK_BELOW = 20.0
ADX_STRONG_ABOVE = 25.0
RSI_MIDLINE = 50.0
```

- [ ] **Step 4: Modul implementieren**

```python
"""Das deterministische technische Signal: Richtung plus zaehlbare Staerke.

Drei richtungsgebende Teilindikatoren stimmen ab (RSI mit Trend, MACD-Histogramm,
SMA-Trend); die Mehrheit bestimmt die Richtung. ADX moduliert die Staerke, ohne
die Richtung zu filtern.

Kein Claude-Call, kein Netz, keine Datenbank -- eine reine Funktion ueber das
Snapshot-Dict aus Phase 1. Damit ist das Signal reproduzierbar und
tabellengetrieben testbar.

Die drei Ablesungen sind bewusste Entscheidungen, keine Herleitungen -- welche
davon besser predictet, beantwortet Sprint 3D aus der Outcome-Historie:
  * RSI wird als MOMENTUM gelesen (ueber 50 und steigend = bullish), nicht als
    Mean-Reversion (ueberverkauft = Rebound). Gewaehlt, weil es zum bestehenden
    Guardrail momentum >= MOMENTUM_LONG_MIN passt.
  * MACD ueber das Vorzeichen des Histogramms, nicht ueber die Kreuzung. Eine
    Kreuzung feuert nur an zwei Bars und ist als Dauersignal wertlos.
  * Fehlt SMA200, stimmt der SMA-Teilindikator neutral -- nicht 'fehlend'.
"""
from dataclasses import dataclass

import config

_LONG, _SHORT, _NEUTRAL = "long", "short", "neutral"


@dataclass(frozen=True)
class TechnicalSignal:
    """Ergebnis der Signalrechnung fuer einen Ticker."""

    direction: str
    agreement: int
    adx_band: str
    strength: int


def _vote_rsi(td: dict) -> str:
    """RSI ueber/unter der Mittellinie, bestaetigt durch seinen Trend."""
    rsi, trend = td.get("rsi_14"), td.get("rsi_trend")
    if rsi is None:
        return _NEUTRAL
    if rsi > config.RSI_MIDLINE and trend == "rising":
        return _LONG
    if rsi < config.RSI_MIDLINE and trend == "falling":
        return _SHORT
    return _NEUTRAL


def _vote_macd(td: dict) -> str:
    """Vorzeichen des MACD-Histogramms (Linie minus Signallinie)."""
    line, signal = td.get("macd_line"), td.get("macd_signal_line")
    if line is None or signal is None:
        return _NEUTRAL
    if line > signal:
        return _LONG
    if line < signal:
        return _SHORT
    return _NEUTRAL


def _vote_sma(td: dict) -> str:
    """Kurs ueber SMA50 und SMA50 ueber SMA200 (beides als Distanz in Prozent).

    Fehlt SMA200 -- unter 200 Bars Historie --, stimmt dieser Teilindikator
    neutral. Die Richtung entsteht dann aus den beiden anderen, und die
    niedrigere agreement-Zahl macht die duennere Grundlage sichtbar.
    """
    d50, d200 = td.get("above_sma50"), td.get("above_sma200")
    if d50 is None or d200 is None:
        return _NEUTRAL
    if d50 > 0 and d200 > 0:
        return _LONG
    if d50 < 0 and d200 < 0:
        return _SHORT
    return _NEUTRAL


def _adx_band(td: dict) -> str:
    """weak | normal | strong. Ein fehlender ADX gilt als normal -- er soll die
    Staerke weder deckeln noch anheben, wenn er unbekannt ist."""
    adx = td.get("adx_14")
    if adx is None:
        return "normal"
    if adx < config.ADX_WEAK_BELOW:
        return "weak"
    if adx > config.ADX_STRONG_ABOVE:
        return "strong"
    return "normal"


def compute(td: dict) -> TechnicalSignal:
    """Leitet Richtung und Staerke aus einem Phase-1-Snapshot ab."""
    votes = [_vote_rsi(td), _vote_macd(td), _vote_sma(td)]
    longs, shorts = votes.count(_LONG), votes.count(_SHORT)

    if longs >= 2:
        direction, agreement = _LONG, longs
    elif shorts >= 2:
        direction, agreement = _SHORT, shorts
    else:
        return TechnicalSignal(
            direction=_NEUTRAL, agreement=max(longs, shorts),
            adx_band=_adx_band(td), strength=0,
        )

    band = _adx_band(td)
    strength = agreement
    if band == "strong":
        strength = min(4, strength + 1)
    elif band == "weak":
        strength = 1

    return TechnicalSignal(
        direction=direction, agreement=agreement,
        adx_band=band, strength=strength,
    )
```

- [ ] **Step 5: Tests laufen lassen**

Run: `pytest tests/unit/test_technical_signal.py -v`

Erwartet: **alle PASS.**

- [ ] **Step 6: Volle Suite und Coverage**

Run: `pytest tests/ --cov=src --cov-fail-under=80 -q`

Erwartet: **alle PASS**, Coverage über 80 %.

- [ ] **Step 7: Commit**

```bash
git add src/technical_signal.py tests/unit/test_technical_signal.py config.py
git commit -m "feat: deterministisches Technik-Signal (Richtung + zaehlbare Staerke)

Drei Teilindikatoren stimmen ab, ADX moduliert die Staerke ohne die Richtung
zu filtern. Noch ohne Konsument -- das Signal wird in Plan 3 verdrahtet."
```

---

## Task 9: Doku nachziehen

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/superpowers/specs/PROJECT_STATUS.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: `docs/ARCHITECTURE.md`**

Zwei neue Modul-Abschnitte, eingereiht in die bestehende Nummerierung:

```markdown
### N. `src/indicators.py`
Die 17 technischen Indikatoren als reine Funktionen über ein OHLCV-DataFrame.
Kein Provider-, DB- oder Netzzugriff. Aus `data_collector.py` herausgelöst, weil
dort Indikatormathematik mit Provider- und DB-Verdrahtung vermischt war.
⚠️ `obv` beruht auf `lastTradedVolume` — einem CFD-Broker-Proxy von Capital.com,
nicht auf Börsenvolumen. Als Richtungsmaß brauchbar, als Niveauaussage nicht.
⚠️ Fehlende Werte sind `None`, nie `0`.

### N+1. `src/technical_signal.py`
Richtung (`long`/`short`/`neutral`) und zählbare Stärke (0–4) aus drei
abstimmenden Teilindikatoren; ADX moduliert die Stärke, filtert nie die Richtung.
Deterministisch, kein Claude-Call. Wird ab Plan 3 vom Ranking konsumiert.
```

In der Invarianten-Liste ergänzen: **das Ladefenster von `load_price_history_from_db()`
muss mindestens die Länge des längsten Indikators plus Reserve tragen** (aktuell 220 für
SMA200).

- [ ] **Step 2: `docs/superpowers/specs/PROJECT_STATUS.md`**

Neuer Abschnitt unter Sprint 3C:

```markdown
### Analyse-Pipeline-Umbau, Plan 1 (Fundament) ✅ abgeschlossen [DATUM]

Spec: `docs/superpowers/specs/2026-08-11-analyse-pipeline-umbau-design.md`
Plan: `docs/superpowers/plans/2026-08-11-analyse-pipeline-plan1-fundament.md`

**Keine Verhaltensänderung.** 17 Indikatoren laufen mit und füllen 29 neue Spalten
in `technical_indicators`; das Technik-Signal ist berechenbar, steuert aber nichts.
[N] Tests, [X] % Coverage.

⚠️ **Befund: `cost_tracker` rechnete zu billig.** `fresh_input` zog die Cache-Treffer
ein zweites Mal ab, obwohl `input_tokens` von der API bereits der ungecachte Rest ist.
**Alle vor [DATUM] gemessenen Laufkosten sind damit zu niedrig ausgewiesen** — grob
5 % beim Lauf vom 2026-08-09, wachsend mit der Cache-Trefferquote. Dieselbe
Fehlannahme steckte in `cache_hit_rate`, die dadurch über 1 gehen konnte.
```

Dazu das Sonden-Ergebnis aus Task 1, Step 3.

- [ ] **Step 3: `CLAUDE.md`**

Zwei Zeilen unter „Wichtige Designentscheidungen":

```markdown
- Das technische Signal ist **deterministisch im Code** (`src/technical_signal.py`),
  kein Claude-Call: drei Teilindikatoren stimmen ab, ADX moduliert die Stärke,
  filtert aber nie die Richtung. Die drei Ablesungen (RSI als Momentum, MACD über
  das Histogramm, SMA200-Degradation) sind bewusste Entscheidungen — welche besser
  predictet, misst 3D.
- `technical_indicators` trägt 17 Indikatoren, von denen zunächst nur vier etwas
  steuern. Der Rest läuft mit, damit 3D später Historie hat statt bei null zu beginnen.
```

- [ ] **Step 4: Commit**

```bash
git add docs/ARCHITECTURE.md docs/superpowers/specs/PROJECT_STATUS.md CLAUDE.md
git commit -m "docs: Indikatoren und Technik-Signal in den lebenden Dokumenten"
```

---

## Abschluss von Plan 1

Nach Task 9 gilt:

- 17 Indikatoren werden je Lauf für jeden Ticker berechnet und persistiert
- das Technik-Signal ist berechenbar und getestet, **steuert aber nichts**
- die Kostenrechnung stimmt
- das Ergebnis der `epics=`-Sonde liegt vor und entscheidet den Sweep in Plan 2
- **kein einziges Pipeline-Verhalten hat sich geändert**

Damit ist der Stand gefahrlos einspielbar. Plan 2 (Trichter) setzt darauf auf.

**Was Plan 2 und 3 aus der Spec noch abdecken müssen** — hier festgehalten, damit beim
Schreiben nichts durchfällt:

| Spec | Plan |
|---|---|
| § 4.2 Skip-Gate vorziehen, § 4.3 Kurs-Sweep mit 429-Notbremse | 2 |
| § 4.6 Phase-2-Scan, § 4.7 Cutoff + Phase 2b, § 7.3 `cutoff_log` | 2 |
| § 8 wöchentlicher Fundamentals-Job mit Ratenbegrenzung | 2 |
| § 4.8 Batching, Streaming in `call_claude`, `web_search_20260209` | 3 |
| § 5.2–5.7 News-Stärke, Qualifikation, Ranking, Divergenz, `DIMENSION_WEIGHTS` | 3 |
| § 5.6 core/divergence in den Aggregatfunktionen | 3 |
| § 6 Rohstoff-Sonderregeln (Deaktivierungs-Ausnahme, B.3 aktienspezifisch) | 3 |
| § 7.2 `predictions`-Spalten + C.1-Fix, § 9 Prompts v2 | 3 |
| **§ 13.3 Kosten-Konstanten-Test** — Härtegrad ist in der Spec verbindlich geregelt | 3 |
| § 12 Testlauf | 3 |
