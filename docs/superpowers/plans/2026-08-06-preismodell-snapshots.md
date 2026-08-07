# Preismodell: drei Entscheidungs-Snapshots + finale Tages-OHLC — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `price_history` enthält nur noch finale Tagesbars und hat genau einen Schreiber; Entscheidungskurse wandern als drei eigene Spalten in `predictions`; die Auswertung läuft auf finalen Daten ab dem Signal-Zeitpunkt.

**Architecture:** Ein neuer Run-Type `final_close` (00:15 UTC, täglich) holt die finale Tages-OHLC für Ticker, Commodities/Crypto und Sub-Sektor-ETFs und bewertet danach die offenen Predictions. `pre_market` und `trade_proposals` schreiben nicht mehr in `price_history`, sondern nur noch ihre Entscheidungs-Snapshots in `predictions`. Das Auswertungsfenster beginnt am Signal-Zeitpunkt: die MINUTE-Bars des Signaltags werden zu **einer** synthetischen Tagesbar verdichtet, damit `_walk_forward_hit` und damit `days_to_close` unverändert bleiben.

**Tech Stack:** Python 3.12, SQLite, pandas, `requests`, Capital.com REST API, pytest.

**Spec:** `docs/superpowers/specs/2026-08-06-preismodell-snapshots-design.md`

---

## Dateistruktur

| Datei | Verantwortung | Änderung |
|---|---|---|
| `src/providers/capital_provider.py` | REST-Zugriff, Resolution, `to`-Klemmung | modifiziert |
| `src/signal_window.py` | Signal-Zeitpunkt und Verdichtung der Intraday-Bars zu einer Tagesbar. Kein Netz, keine DB | **neu** |
| `src/db.py` | Migration, `load_sector_db_momentum`, `load_final_bar_date` | modifiziert |
| `src/evaluator.py` | Auswertung auf `price_history` + synthetischer Signaltag-Bar | modifiziert |
| `src/data_collector.py` | `_ensure_today_bar()` entfällt, Live-Snapshot statt DB-Close | modifiziert |
| `src/sector_momentum.py` | schreibt keine ETF-Bars mehr | modifiziert |
| `src/signal_checks.py` | `daily_change_pct` umbenannt/dokumentiert | modifiziert |
| `main.py` | `run_final_close()`, RUN_TYPES, Snapshot-Befüllung, Sichtbarkeitswarnung | modifiziert |
| `.github/workflows/analyze.yml` | Cron, Concurrency-Lock | modifiziert |

**Regeln für alle Tasks:** RED-GREEN. Ein Commit je Task. **Niemals pushen.** Tests ausserhalb `tests/live/` telefonieren nicht (Transport-Sperre in `tests/conftest.py`).

---

## Task 1: `to` darf nicht in der Zukunft liegen

Capital.com beantwortet ein `to` in der Zukunft mit HTTP 400 — fünf Minuten genügen (gemessen 2026-08-06). Undokumentiert. Ohne diesen Fix scheitert `final_close` strukturell, weil er im Fenster um Mitternacht läuft.

**Files:**
- Modify: `src/providers/capital_provider.py:6` (Import), neue Hilfsfunktion nach `MAX_BARS_PER_REQUEST`, `get_ohlc_after:169-199`
- Test: `tests/unit/test_capital_provider.py`

- [ ] **Step 1: Failing Test schreiben**

Ans Ende von `tests/unit/test_capital_provider.py` anfügen:

```python
def test_to_parameter_is_clamped_to_now(monkeypatch):
    """Capital.com wirft HTTP 400, wenn 'to' in der Zukunft liegt -- schon fuenf
    Minuten reichen (gemessen 2026-08-06). Das steht nicht in der API-Doku.

    Ausgeloest wird es davon, dass main.py das Laufdatum aus Europe/Berlin
    ableitet, die API aber auf snapshotTimeUTC filtert: zwischen 00:00 und 02:00
    Berlin laeuft das Berliner Datum dem UTC-Datum voraus."""
    from datetime import datetime, timedelta, timezone
    from src.providers.capital_provider import CapitalComProvider

    seen = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"prices": []}

    def _fake_get(url, headers=None, params=None, timeout=None):
        seen.update(params)
        return _Resp()

    monkeypatch.setattr("src.providers.capital_provider.requests.get", _fake_get)
    prov = CapitalComProvider()
    monkeypatch.setattr(prov, "_headers", lambda: {})
    monkeypatch.setattr(prov, "_map", lambda t: t)

    morgen = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
    prov.get_ohlc_after("AAPL", start_date=morgen, end_date=morgen)

    to_dt = datetime.fromisoformat(seen["to"])
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert to_dt <= now, f"'to' liegt in der Zukunft: {seen['to']}"
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `python -m pytest tests/unit/test_capital_provider.py::test_to_parameter_is_clamped_to_now -v`
Expected: FAIL — `'to' liegt in der Zukunft: 2026-08-07T00:00:00`

- [ ] **Step 3: Import erweitern**

In `src/providers/capital_provider.py` Zeile 6 ersetzen:

```python
from datetime import date as _date, datetime as _datetime, timedelta, timezone
```

- [ ] **Step 4: Hilfsfunktion einfügen**

Direkt nach `MAX_BARS_PER_REQUEST = 1000` einfügen:

```python
def _not_in_future(ts: str) -> str:
    """Klemmt einen 'to'-Zeitstempel auf 'jetzt' (UTC).

    Capital.com beantwortet ein 'to' in der Zukunft mit HTTP 400 -- gemessen am
    2026-08-06 genuegen fuenf Minuten. Das Verhalten steht NICHT in der API-Doku
    (CapitalcomPublicAPI.pdf S. 73 nennt nur das Format). Ausgeloest wird es
    davon, dass das Laufdatum aus Europe/Berlin stammt, die API aber laut Doku
    auf snapshotTimeUTC filtert: zwischen 00:00 und 02:00 Berlin laeuft das
    Berliner Datum dem UTC-Datum voraus."""
    now = _datetime.now(timezone.utc).replace(tzinfo=None)
    parsed = _datetime.fromisoformat(ts)
    return min(parsed, now).strftime("%Y-%m-%dT%H:%M:%S")
```

- [ ] **Step 5: In `get_ohlc_after` verwenden**

In `src/providers/capital_provider.py` den `params`-Block von `get_ohlc_after` ersetzen:

```python
                params={
                    "resolution": "DAY",
                    "max":        1000,
                    "from":       f"{start_dt.isoformat()}T00:00:00",
                    "to":         _not_in_future(f"{end_dt.isoformat()}T00:00:00"),
                },
```

- [ ] **Step 6: Tests laufen lassen**

Run: `python -m pytest tests/unit/test_capital_provider.py -v`
Expected: PASS, alle

- [ ] **Step 7: Commit**

```bash
git add src/providers/capital_provider.py tests/unit/test_capital_provider.py
git commit -m "fix: 'to' nie in der Zukunft an Capital.com schicken

Ein 'to' in der Zukunft beantwortet Capital.com mit HTTP 400 -- gemessen am
2026-08-06 genuegen fuenf Minuten. Undokumentiert. Bisher irrelevant, weil kein
Lauf im Fenster 00:00-02:00 Berlin lag; der neue final_close-Job laeuft genau
dort hinein und wuerde strukturell scheitern."
```

---

## Task 2: `resolution`-Parameter und Intraday-Abruf

`_parse_prices` schneidet `snapshotTime` auf `[:10]` und indiziert nach Datum — für MINUTE-Bars fielen alle Minuten eines Tages auf denselben Indexwert. Intraday braucht deshalb einen eigenen Parser.

**Files:**
- Modify: `src/providers/capital_provider.py` (neu: `_parse_intraday`, `get_intraday_ohlc`)
- Test: `tests/unit/test_capital_provider.py`

- [ ] **Step 1: Failing Test schreiben**

```python
def test_get_intraday_ohlc_keeps_the_full_timestamp(monkeypatch):
    """_parse_prices schneidet snapshotTime auf [:10] und indiziert nach Datum.
    Fuer MINUTE-Bars fielen damit alle Minuten eines Tages auf denselben
    Indexwert -- Intraday braucht einen eigenen Parser."""
    import pandas as pd
    from src.providers.capital_provider import CapitalComProvider

    payload = {"prices": [
        {"snapshotTime": "2026-08-05T13:30:00",
         "openPrice": {"bid": 309.09}, "highPrice": {"bid": 309.6},
         "lowPrice": {"bid": 307.8}, "closePrice": {"bid": 307.94},
         "lastTradedVolume": 431},
        {"snapshotTime": "2026-08-05T13:31:00",
         "openPrice": {"bid": 307.91}, "highPrice": {"bid": 308.9},
         "lowPrice": {"bid": 307.5}, "closePrice": {"bid": 308.78},
         "lastTradedVolume": 381},
    ]}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return payload

    monkeypatch.setattr("src.providers.capital_provider.requests.get",
                        lambda *a, **k: _Resp())
    prov = CapitalComProvider()
    monkeypatch.setattr(prov, "_headers", lambda: {})
    monkeypatch.setattr(prov, "_map", lambda t: t)

    df = prov.get_intraday_ohlc("AAPL", "2026-08-05T13:30:00", "2026-08-05T13:32:00")
    assert df is not None and len(df) == 2, "beide Minuten muessen erhalten bleiben"
    assert df.index[0] == pd.Timestamp("2026-08-05 13:30:00")
    assert df.index[1] == pd.Timestamp("2026-08-05 13:31:00")
    assert float(df["Open"].iloc[0]) == 309.09


def test_get_intraday_ohlc_passes_the_resolution(monkeypatch):
    """Laut PDF S.73 sind MINUTE, MINUTE_5, MINUTE_15, MINUTE_30, HOUR, HOUR_4,
    DAY und WEEK zulaessig. Der Code kannte bisher nur DAY."""
    from src.providers.capital_provider import CapitalComProvider
    seen = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"prices": []}

    def _fake_get(url, headers=None, params=None, timeout=None):
        seen.update(params)
        return _Resp()

    monkeypatch.setattr("src.providers.capital_provider.requests.get", _fake_get)
    prov = CapitalComProvider()
    monkeypatch.setattr(prov, "_headers", lambda: {})
    monkeypatch.setattr(prov, "_map", lambda t: t)

    prov.get_intraday_ohlc("AAPL", "2026-08-05T13:30:00", "2026-08-05T14:00:00",
                           resolution="MINUTE_5")
    assert seen["resolution"] == "MINUTE_5"
    assert seen["max"] == 1000
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python -m pytest tests/unit/test_capital_provider.py -k intraday -v`
Expected: FAIL — `AttributeError: 'CapitalComProvider' object has no attribute 'get_intraday_ohlc'`

- [ ] **Step 3: Parser und Methode implementieren**

In `src/providers/capital_provider.py` direkt nach `_parse_prices` einfügen:

```python
    def _parse_intraday(self, prices: list[dict]) -> pd.DataFrame | None:
        """Wie _parse_prices, aber mit vollem Zeitstempel als Index.

        _parse_prices schneidet snapshotTime auf [:10]; bei MINUTE-Bars fielen
        damit alle Minuten eines Tages auf denselben Indexwert."""
        if not prices:
            return None
        rows = []
        for p in prices:
            snap = (p.get("snapshotTimeUTC") or p.get("snapshotTime", "")).replace("/", "-")
            rows.append({
                "Ts":     snap[:19],
                "Open":   float(p["openPrice"]["bid"]),
                "High":   float(p["highPrice"]["bid"]),
                "Low":    float(p["lowPrice"]["bid"]),
                "Close":  float(p["closePrice"]["bid"]),
                "Volume": int(p.get("lastTradedVolume") or 0),
            })
        df = pd.DataFrame(rows)
        df["Ts"] = pd.to_datetime(df["Ts"])
        df = df.set_index("Ts").sort_index()
        return df if not df.empty else None

    def get_intraday_ohlc(
        self, ticker: str, start_utc: str, end_utc: str,
        resolution: str = "MINUTE",
    ) -> pd.DataFrame | None:
        """Intraday-Bars zwischen zwei UTC-Zeitstempeln (YYYY-MM-DDTHH:MM:SS).

        Zulaessige Resolutions laut CapitalcomPublicAPI.pdf S. 73: MINUTE,
        MINUTE_5, MINUTE_15, MINUTE_30, HOUR, HOUR_4, DAY, WEEK. max ist auf 1000
        gedeckelt -- das Fenster 14:10-00:00 UTC sind ~590 Minutenbars und passt
        damit in einen einzigen Call. Gibt None bei jedem Fehler zurueck."""
        epic = self._map(ticker)
        try:
            resp = requests.get(
                f"{config.CAPITAL_COM_BASE_URL}/api/v1/prices/{epic}",
                headers=self._headers(),
                params={
                    "resolution": resolution,
                    "max":        MAX_BARS_PER_REQUEST,
                    "from":       start_utc,
                    "to":         _not_in_future(end_utc),
                },
                timeout=30,
            )
            resp.raise_for_status()
            return self._parse_intraday(resp.json().get("prices", []))
        except Exception as e:
            log.warning(f"{ticker}: Capital.com intraday fetch failed: {e}")
            return None
```

- [ ] **Step 4: Tests laufen lassen**

Run: `python -m pytest tests/unit/test_capital_provider.py -v`
Expected: PASS, alle

- [ ] **Step 5: Commit**

```bash
git add src/providers/capital_provider.py tests/unit/test_capital_provider.py
git commit -m "feat: Intraday-Abruf mit Resolution-Parameter

Laut CapitalcomPublicAPI.pdf S.73 unterstuetzt /prices MINUTE, MINUTE_5,
MINUTE_15, MINUTE_30, HOUR, HOUR_4, DAY und WEEK; der Code kannte nur DAY.

Eigener Parser, weil _parse_prices snapshotTime auf [:10] schneidet -- bei
Minutenbars fielen sonst alle Minuten eines Tages auf denselben Index."
```

---

## Task 3: Schema — die vier neuen Spalten

Additiv. Keine bestehende Spalte wird angefasst, `entry_price` behält Bedeutung und Befüllung.

**Files:**
- Modify: `src/db.py:280-284` (Migrationsblock), `_insert_prediction` Spaltenliste
- Test: `tests/unit/test_db.py`

- [ ] **Step 1: Failing Test schreiben**

```python
def test_migration_adds_the_three_decision_snapshots(tmp_db_path):
    """Additiv und idempotent -- muss auch gegen eine bestehende tracking.db
    laufen. entry_price bleibt unangetastet."""
    conn = db.connect(str(tmp_db_path))
    db.init_schema(conn)
    db.init_schema(conn)  # zweimal: idempotent
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(predictions)").fetchall()}
    assert {"price_premarket", "price_open", "price_1610",
            "is_premarket"}.issubset(cols)
    assert "entry_price" in cols, "die bestehende Spalte bleibt"
    conn.close()


def test_save_prediction_persists_the_snapshots(in_memory_db):
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-08-06", "run_type": "trade_proposals",
        "ticker": "AAPL", "direction": "long", "entry_price": 310.0,
        "price_premarket": 308.5, "price_open": 309.09, "price_1610": 310.0,
        "is_premarket": 0,
    })
    row = in_memory_db.execute(
        "SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row["price_premarket"] == 308.5
    assert row["price_open"] == 309.09
    assert row["price_1610"] == 310.0
    assert row["is_premarket"] == 0
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python -m pytest tests/unit/test_db.py -k "decision_snapshots or persists_the_snapshots" -v`
Expected: FAIL — `assert {...}.issubset(cols)` schlägt fehl

- [ ] **Step 3: Migration ergänzen**

In `src/db.py` den Block bei Zeile 280 ersetzen (der `premarket_price`-Teil bleibt unverändert stehen):

```python
    ph_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(price_history)"
    ).fetchall()}
    if "premarket_price" not in ph_cols:
        # TOTE SPALTE -- nie geschrieben, nie gelesen. Der Vorboersenkurs gehoert
        # seit dem Preismodell-Umbau (2026-08-06) zur Entscheidung und steht in
        # predictions.price_premarket, nicht in der Kurshistorie. Bleibt nur
        # stehen, weil ein DROP COLUMN bestehende DBs anfassen wuerde.
        conn.execute("ALTER TABLE price_history ADD COLUMN premarket_price REAL")

    pred_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(predictions)"
    ).fetchall()}
    for col, coltype in (
        ("price_premarket", "REAL"),
        ("price_open",      "REAL"),
        ("price_1610",      "REAL"),
        ("is_premarket",    "INTEGER"),
    ):
        if col not in pred_cols:
            conn.execute(f"ALTER TABLE predictions ADD COLUMN {col} {coltype}")
    conn.commit()
```

- [ ] **Step 4: Spaltenliste in `_insert_prediction` erweitern**

In `src/db.py`, in der `cols`-Liste von `_insert_prediction` nach `"sector_etf_momentum", "sector_db_momentum",` ergänzen:

```python
        # Preismodell 2026-08-06: die drei Entscheidungs-Snapshots. entry_price
        # bleibt daneben unveraendert bestehen.
        "price_premarket", "price_open", "price_1610", "is_premarket",
```

- [ ] **Step 5: Tests laufen lassen**

Run: `python -m pytest tests/unit/test_db.py -v`
Expected: PASS, alle

- [ ] **Step 6: Commit**

```bash
git add src/db.py tests/unit/test_db.py
git commit -m "feat: drei Entscheidungs-Snapshots in predictions

price_premarket, price_open, price_1610 und is_premarket. Additiv ueber
_apply_migrations mit PRAGMA-Guard, idempotent gegen eine bestehende
tracking.db. entry_price bleibt unangetastet -- die neuen Spalten stehen
daneben, damit 3D vergleichen kann, welcher Zeitpunkt am besten prognostiziert.

price_history.premarket_price ist im Migrationsblock als tot markiert."
```

---

## Task 4: `src/signal_window.py` — Signal-Zeitpunkt und Verdichtung

Reine Funktionen: keine DB, kein Netz, kein Claude. Damit ohne Mocking testbar.

**Files:**
- Create: `src/signal_window.py`
- Test: `tests/unit/test_signal_window.py`

- [ ] **Step 1: Failing Test schreiben**

Neue Datei `tests/unit/test_signal_window.py`:

```python
"""Signal-Zeitpunkt und Verdichtung der Intraday-Bars.

Reine Funktionen -- keine DB, kein Netz, kein Claude. Deshalb ohne einen
einzigen Mock testbar."""
import pandas as pd
import pytest

from src.signal_window import signal_time_utc, collapse_to_daily_bar, day_end_utc


def test_signal_time_follows_us_dst_not_berlin():
    """Der Signal-Zeitpunkt haengt an der US-Sitzung. EU und USA schalten an
    verschiedenen Wochenenden um -- eine Berliner Rechnung ginge in den
    Zwischenwochen daneben."""
    # Sommer (EDT, UTC-4): 10:10 ET == 14:10 UTC
    assert signal_time_utc("trade_proposals", "2026-08-05") == "2026-08-05T14:10:00"
    # Winter (EST, UTC-5): 10:10 ET == 15:10 UTC
    assert signal_time_utc("trade_proposals", "2026-01-15") == "2026-01-15T15:10:00"


def test_pre_market_signal_is_before_the_open():
    """pre_market entsteht um 09:00 ET -- eine halbe Stunde VOR der Eroeffnung.
    Das Auswertungsfenster umfasst die Eroeffnung damit vollstaendig."""
    assert signal_time_utc("pre_market", "2026-08-05") == "2026-08-05T13:00:00"


def test_unknown_run_type_has_no_signal_time():
    assert signal_time_utc("weekly", "2026-08-05") is None


def test_day_end_is_the_utc_boundary():
    """openingHours der Instrumente endet auf 00:00 UTC (zone: UTC), deshalb ist
    die Tagesgrenze UTC-Mitternacht und nicht der US-Schluss."""
    assert day_end_utc("2026-08-05") == "2026-08-06T00:00:00"


def test_regular_open_follows_us_dst():
    """Der REGULAERE Open (09:30 ET) -- nicht zu verwechseln mit dem Beginn der
    Capital.com-Handelszeit (08:00 UTC, also vorboerslich)."""
    from src.signal_window import regular_open_utc
    assert regular_open_utc("2026-08-05") == "2026-08-05T13:30:00"   # EDT
    assert regular_open_utc("2026-01-15") == "2026-01-15T14:30:00"   # EST


def test_is_premarket_compares_against_the_regular_open():
    """marketStatus taugt dafuer nicht: es meldete um 08:37 ET TRADEABLE,
    mitten in der Vorboerse. Also die Uhr."""
    from src.signal_window import is_premarket
    assert is_premarket("2026-08-05", "2026-08-05T13:00:00") is True   # 09:00 ET
    assert is_premarket("2026-08-05", "2026-08-05T14:10:00") is False  # 10:10 ET


def _minute_df(rows):
    return pd.DataFrame(
        [{"Open": o, "High": h, "Low": l, "Close": c, "Volume": v}
         for o, h, l, c, v in rows],
        index=pd.to_datetime(
            [f"2026-08-05 14:{10 + i:02d}:00" for i in range(len(rows))]),
    )


def test_collapse_takes_extremes_and_last_close():
    """Der Kern: aus vielen Minutenbars wird EINE Tagesbar. Ohne diese
    Verdichtung zaehlte _walk_forward_hit jede Minute als eigenen 'Tag' und
    days_to_close waere zerstoert -- genau die Kennzahl, an der 3Ds hold_day
    haengt."""
    df = _minute_df([
        (100.0, 101.0,  99.5, 100.5, 10),
        (100.5, 104.0, 100.0, 103.0, 20),   # Tages-High
        (103.0, 103.5,  97.0,  98.0, 30),   # Tages-Low, letzter Close
    ])
    bar = collapse_to_daily_bar(df)
    assert bar == {"Open": 100.0, "High": 104.0, "Low": 97.0,
                   "Close": 98.0, "Volume": 60}


def test_collapse_of_nothing_is_none():
    """Feiertag, Handelsstopp oder Abruffehler: kein Fenster, keine Bar. Die
    Auswertung beginnt dann bei D+1 statt zu scheitern."""
    assert collapse_to_daily_bar(None) is None
    assert collapse_to_daily_bar(pd.DataFrame()) is None
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python -m pytest tests/unit/test_signal_window.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.signal_window'`

- [ ] **Step 3: Modul implementieren**

Neue Datei `src/signal_window.py`:

```python
"""Signal-Zeitpunkt und Verdichtung der Intraday-Bars zu einer Tagesbar.

Das Auswertungsfenster beginnt am Signal-Zeitpunkt, nicht am Tagesanfang: die
Tagesbar laeuft laut openingHours ab 08:00 UTC, das Signal entsteht aber erst um
09:00 ET (pre_market) beziehungsweise 10:10 ET (trade_proposals). TP/SL-Treffer
aus der Zeit davor sind Artefakte -- die Position gab es da noch nicht.

Den ganzen Prognosetag auszuschliessen waere jedoch das gespiegelte Artefakt:
Sprint 3D verfolgt die Trefferquote getrennt nach Intraday (hold_day = 1) und
Extended (2-5), und ohne Tag D koennte eine Intraday-These nie am selben Tag als
getroffen erfasst werden.

Reine Funktionen: keine DB, kein Netz, kein Claude."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

NEW_YORK = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# Wann das Signal des jeweiligen Laufs entsteht, in US-Ortszeit. Bewusst an
# America/New_York gehaengt und nicht an Europe/Berlin: EU und USA schalten die
# Sommerzeit an verschiedenen Wochenenden um.
SIGNAL_TIMES_ET: dict[str, time] = {
    "pre_market":      time(9, 0),    # vor der Eroeffnung (09:30 ET)
    "trade_proposals": time(10, 10),  # 40 min nach der Eroeffnung
}

# Regulaere US-Sitzung. NICHT zu verwechseln mit der Capital.com-Handelszeit:
# openingHours meldet 08:00-00:00 UTC, also erweiterte Zeiten. Der "Open" der
# Tagesbar ist deshalb NICHT der Eroeffnungskurs -- gemessen am 2026-08-05 lagen
# beide bei AAPL 0,47 % auseinander (310,54 gegen 309,09).
REGULAR_OPEN_ET = time(9, 30)


def regular_open_utc(date: str) -> str:
    """UTC-Zeitstempel der regulaeren US-Eroeffnung an `date`."""
    local = datetime.combine(
        datetime.fromisoformat(date).date(), REGULAR_OPEN_ET, tzinfo=NEW_YORK)
    return local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def is_premarket(date: str, now_utc: str) -> bool:
    """True, wenn `now_utc` vor der regulaeren Eroeffnung liegt.

    Aus der Uhr abgeleitet und nicht aus `marketStatus`: das Feld meldete am
    2026-08-06 um 08:37 ET `TRADEABLE` -- mitten in der Vorboerse. Es beschreibt
    die Handelbarkeit des CFDs einschliesslich erweiterter Zeiten, nicht die
    Sitzungsphase."""
    return datetime.fromisoformat(now_utc) < datetime.fromisoformat(
        regular_open_utc(date))


def signal_time_utc(run_type: str, date: str) -> str | None:
    """UTC-Zeitstempel des Signals fuer `run_type` an `date`, oder None, wenn der
    Run-Type keinen Entscheidungszeitpunkt hat."""
    et = SIGNAL_TIMES_ET.get(run_type)
    if et is None:
        return None
    local = datetime.combine(datetime.fromisoformat(date).date(), et, tzinfo=NEW_YORK)
    return local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def day_end_utc(date: str) -> str:
    """Ende des Handelstags als UTC-Zeitstempel.

    Die Instrumente laufen laut openingHours bis 00:00 UTC (`zone: UTC`), die
    Tagesgrenze ist also UTC-Mitternacht -- nicht der regulaere US-Schluss."""
    end = datetime.fromisoformat(date).date() + timedelta(days=1)
    return f"{end.isoformat()}T00:00:00"


def collapse_to_daily_bar(df: "pd.DataFrame | None") -> dict | None:
    """Verdichtet Intraday-Bars zu EINER Tagesbar.

    High ist das Maximum, Low das Minimum, Close der letzte Wert des Fensters.
    Genau diese Verdichtung haelt _walk_forward_hit unveraendert: die Funktion
    zaehlt day_offset je Bar, und daraus wird days_to_close. Minutenbars direkt
    in die Sequenz zu geben, wuerde jede Minute als eigenen Tag zaehlen.

    None, wenn kein Fenster vorliegt (Feiertag, Handelsstopp, Abruffehler) --
    die Auswertung beginnt dann bei D+1, statt zu scheitern."""
    if df is None or len(df) == 0:
        return None
    return {
        "Open":   float(df["Open"].iloc[0]),
        "High":   float(df["High"].max()),
        "Low":    float(df["Low"].min()),
        "Close":  float(df["Close"].iloc[-1]),
        "Volume": int(df["Volume"].sum()),
    }
```

- [ ] **Step 4: Tests laufen lassen**

Run: `python -m pytest tests/unit/test_signal_window.py -v`
Expected: PASS, 6 Tests

- [ ] **Step 5: Commit**

```bash
git add src/signal_window.py tests/unit/test_signal_window.py
git commit -m "feat: Signal-Zeitpunkt und Verdichtung zu einer Tagesbar

Das Auswertungsfenster beginnt am Signal, nicht am Tagesanfang -- die Tagesbar
laeuft ab 08:00 UTC, das Signal entsteht erst um 09:00 bzw. 10:10 ET.

Die Verdichtung ist der Kern: aus ~590 Minutenbars wird EINE Tagesbar
(High=max, Low=min, Close=letzter). Ohne sie zaehlte _walk_forward_hit jede
Minute als eigenen Tag und zerstoerte days_to_close -- die Kennzahl, an der
3Ds hold_day haengt.

Signalzeiten haengen an America/New_York, nicht an Europe/Berlin: EU und USA
schalten an verschiedenen Wochenenden um."
```

---

## Task 5: `final_close` — Run-Type und finale Tagesbars

**Files:**
- Modify: `main.py:42` (RUN_TYPES), neue Funktion `run_final_close()`, Dispatch bei `main.py:769-777`
- Test: `tests/unit/test_main.py`

- [ ] **Step 1: Failing Test schreiben**

```python
def test_final_close_writes_final_bars_for_tickers_and_etfs(tmp_db_path, mocker):
    """final_close ist der EINZIGE Schreiber von price_history -- inklusive der
    Sub-Sektor-ETFs. Nur mit genau einem Schreiber, der ausschliesslich finale
    Bars schreibt, kann der Frozen-Bar-Bug nicht wiederkehren."""
    import pandas as pd
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn); conn.close()

    def _bar(close):
        return pd.DataFrame(
            {"Open": [close - 1], "High": [close + 2], "Low": [close - 2],
             "Close": [close], "Volume": [1000]},
            index=pd.DatetimeIndex([pd.Timestamp("2026-08-05")]))

    prov = MagicMock()
    prov._source_name = "capital.com"
    prov.get_ohlc_after.side_effect = lambda t, *a, **k: _bar(100.0)
    mocker.patch("main.CapitalComProvider", return_value=prov)
    mocker.patch("main.evaluate_open_predictions", return_value=0)
    mocker.patch("main.config.SP500_MVP_TICKERS", ["AAPL"])
    mocker.patch("main.config.USE_FULL_SP500", False)
    mocker.patch("main.config.SUB_SECTOR_ETFS", {"Semis": "SOXX"})
    mocker.patch("main.build_commodity_crypto_inputs",
                 return_value=[{"ticker": "BTC-USD"}])

    from main import run_final_close
    run_final_close(date="2026-08-06", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    tickers = {r["ticker"] for r in conn.execute(
        "SELECT DISTINCT ticker FROM price_history").fetchall()}
    conn.close()
    assert tickers == {"AAPL", "BTC-USD", "SOXX"}


def test_final_close_treats_a_missing_bar_as_normal(tmp_db_path, mocker):
    """Wochenende und Feiertag: fuer Aktien gibt es keine neue Tagesbar, fuer
    Crypto schon. Das ist der erwartete Normalfall, kein Fehler -- der Job
    ueberspringt den Ticker und endet gruen."""
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn); conn.close()

    prov = MagicMock()
    prov._source_name = "capital.com"
    prov.get_ohlc_after.return_value = None          # keine Bar, kein Fehler
    mocker.patch("main.CapitalComProvider", return_value=prov)
    mocker.patch("main.evaluate_open_predictions", return_value=0)
    mocker.patch("main.config.SP500_MVP_TICKERS", ["AAPL"])
    mocker.patch("main.config.USE_FULL_SP500", False)
    mocker.patch("main.config.SUB_SECTOR_ETFS", {})
    mocker.patch("main.build_commodity_crypto_inputs", return_value=[])

    from main import run_final_close
    run_final_close(date="2026-08-06", db_path=str(tmp_db_path))   # darf nicht werfen

    conn = db.connect(str(tmp_db_path))
    n = conn.execute("SELECT COUNT(*) c FROM price_history").fetchone()["c"]
    conn.close()
    assert n == 0


def test_final_close_is_a_known_run_type():
    from main import RUN_TYPES
    assert "final_close" in RUN_TYPES
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python -m pytest tests/unit/test_main.py -k final_close -v`
Expected: FAIL — `ImportError: cannot import name 'run_final_close'`

- [ ] **Step 3: `RUN_TYPES` erweitern**

`main.py` Zeile 42 ersetzen:

```python
RUN_TYPES = ["pre_market", "trade_proposals", "close", "final_close", "weekly"]
```

- [ ] **Step 4: `run_final_close()` implementieren**

In `main.py` direkt vor `def run_weekly(` einfügen:

```python
def _write_final_bar(conn, price_provider, ticker: str, target: str) -> bool:
    """Holt die finale Tagesbar fuer `ticker` am Handelstag `target` und schreibt
    sie. True, wenn eine Bar geschrieben wurde.

    Eine fehlende Bar ist der erwartete Normalfall, kein Fehler: am Wochenende
    und an Feiertagen gibt es fuer Aktien keine neue Tagesbar, fuer Crypto
    schon."""
    try:
        df = price_provider.get_ohlc_after(ticker, target, target)
    except Exception as e:
        log.warning(f"{ticker}: finaler Abruf fehlgeschlagen: {e}")
        return False
    if df is None or df.empty:
        log.info(f"{ticker}: keine neue Tagesbar fuer {target} (Wochenende/Feiertag?)")
        return False

    _raw = getattr(price_provider, "_source_name", None)
    source = _raw if isinstance(_raw, str) else "capital.com"
    written = False
    for ts, row in df.iterrows():
        d = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        if d != target:
            continue
        db.upsert_price_history(
            conn, ticker=ticker, date=d,
            open_=float(row.get("Open", 0)), high=float(row.get("High", 0)),
            low=float(row.get("Low", 0)), close=float(row.get("Close", 0)),
            volume=int(row.get("Volume", 0) or 0), source=source,
        )
        written = True
    if not written:
        log.info(f"{ticker}: Antwort enthielt keine Bar fuer {target}")
    return written


def run_final_close(date: str, db_path: str) -> None:
    """Run-Type final_close (00:15 UTC, taeglich): holt die FINALE Tages-OHLC und
    bewertet danach die offenen Predictions.

    `date` ist das UTC-Laufdatum; ausgewertet wird der UTC-Vortag. Die Tagesbar
    wird laut openingHours (`zone: UTC`) um 00:00 UTC final -- vorher gelesen
    waere sie provisorisch, und High/Low koennen sich bis dahin nur ausweiten.
    Genau darauf beruhen TP- und SL-Pruefung.

    Der Lauf ist bewusst schlank: kein Claude-Call, keine Mail. Die Ergebnisse
    erscheinen in der Fussleiste der naechsten pre_market-Mail."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    price_provider = CapitalComProvider()

    target = (date_cls.fromisoformat(date) - timedelta(days=1)).isoformat()
    log.info(f"final_close: finalisiere Handelstag {target}")

    _tickers = (config.SP500_FULL_TICKERS if config.USE_FULL_SP500
                else config.SP500_MVP_TICKERS)
    cc_tickers = [d["ticker"] for d in build_commodity_crypto_inputs()]
    etfs = sorted(set(config.SUB_SECTOR_ETFS.values()))

    written = 0
    for ticker in list(_tickers) + cc_tickers + etfs:
        if _write_final_bar(conn, price_provider, ticker, target):
            written += 1
    conn.commit()
    log.info(f"final_close: {written} finale Bars fuer {target} geschrieben")

    n = evaluate_open_predictions(
        conn=conn, today=date, price_provider=price_provider)
    log.info(f"final_close: {n} Predictions bewertet")
    conn.close()
```

- [ ] **Step 5: Dispatch erweitern**

In `main.py` nach dem `close`-Zweig einfügen:

```python
        elif ns.run_type == "final_close":
            run_final_close(date=date, db_path=ns.db_path)
```

- [ ] **Step 6: Tests laufen lassen**

Run: `python -m pytest tests/unit/test_main.py -k final_close -v`
Expected: PASS, 3 Tests

- [ ] **Step 7: Volle Suite**

Run: `python -m pytest tests/ -q`
Expected: alle grün (`test_workflow_config.py` prüft `RUN_TYPES` gegen den Workflow — der neue Run-Type kommt in Task 9 dazu; sollte dieser Test hier rot werden, Task 9 vorziehen)

- [ ] **Step 8: Commit**

```bash
git add main.py tests/unit/test_main.py
git commit -m "feat: run_final_close holt die finalen Tagesbars

Neuer Run-Type, taeglich um 00:15 UTC. Holt die finale Tages-OHLC fuer
SP500-Ticker, Commodities/Crypto UND die Sub-Sektor-ETFs und schreibt sie ueber
upsert_price_history. Danach die Bewertung.

Die Bar wird laut openingHours (zone: UTC) erst um 00:00 UTC final; High und Low
koennen sich bis dahin nur ausweiten, und genau darauf beruht die TP/SL-Pruefung.

Eine fehlende Bar ist der erwartete Normalfall (Wochenende, Feiertag) und wird
auf INFO protokolliert, nicht als Fehler behandelt."
```

---

## Task 6: Evaluator auf `price_history` + Signaltag-Bar

**Files:**
- Modify: `src/evaluator.py:67-110`
- Test: `tests/unit/test_evaluator.py`

- [ ] **Step 1: Failing Test schreiben**

```python
def test_window_starts_at_the_signal_not_at_midnight(in_memory_db, mocker):
    """Der alte Fehler war nicht 'Tag D zaehlt', sondern 'der falsche Teil von
    Tag D zaehlt': die Tagesbar laeuft ab 08:00 UTC, das Signal entsteht erst um
    10:10 ET. Ein TP-Treffer davor ist ein Artefakt.

    Hier reisst der TP nur VOR dem Signal -- danach bleibt der Kurs darunter.
    Das darf nicht als Treffer zaehlen."""
    import pandas as pd
    from src import db
    from src.evaluator import evaluate_open_predictions
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-08-05", "run_type": "trade_proposals", "ticker": "AAPL",
        "direction": "long", "entry_price": 100.0,
        "tp_price": 110.0, "sl_price": 95.0})

    prov = mocker.MagicMock()
    # Fenster ab 14:10 UTC: Hoch nur 104 -- der TP bei 110 wird nicht erreicht.
    prov.get_intraday_ohlc.return_value = pd.DataFrame(
        {"Open": [100.0], "High": [104.0], "Low": [99.0],
         "Close": [103.0], "Volume": [500]},
        index=pd.to_datetime(["2026-08-05 14:10:00"]))

    evaluate_open_predictions(conn=in_memory_db, today="2026-08-06",
                              price_provider=prov)

    row = in_memory_db.execute(
        "SELECT * FROM outcomes WHERE prediction_id=?", (pid,)).fetchone()
    assert row["exit_reason"] != "tp_hit", (
        "ein TP-Treffer vor dem Signal darf nicht zaehlen")


def test_intraday_hit_closes_on_day_one(in_memory_db, mocker):
    """Und die Gegenprobe: reisst der TP NACH dem Signal am selben Tag, muss er
    mit days_to_close == 1 zaehlen. Genau daran haengt 3Ds hold_day=1."""
    import pandas as pd
    from src import db
    from src.evaluator import evaluate_open_predictions
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-08-05", "run_type": "trade_proposals", "ticker": "AAPL",
        "direction": "long", "entry_price": 100.0,
        "tp_price": 110.0, "sl_price": 95.0})

    prov = mocker.MagicMock()
    prov.get_intraday_ohlc.return_value = pd.DataFrame(
        {"Open": [100.0], "High": [112.0], "Low": [99.0],
         "Close": [111.0], "Volume": [500]},
        index=pd.to_datetime(["2026-08-05 14:10:00"]))

    evaluate_open_predictions(conn=in_memory_db, today="2026-08-06",
                              price_provider=prov)

    row = in_memory_db.execute(
        "SELECT * FROM outcomes WHERE prediction_id=?", (pid,)).fetchone()
    assert row["exit_reason"] == "tp_hit"
    assert row["days_to_close"] == 1, "Intraday-Treffer ist Tag 1"


def test_evaluated_date_is_the_trading_day_not_the_run_date(in_memory_db, mocker):
    """Sonst findet _aggregate_yesterday_outcomes (WHERE evaluated_date =
    today - 1) nichts mehr und die Fussleiste der Tagesmail zeigt stumm Nullen."""
    import pandas as pd
    from src import db
    from src.evaluator import evaluate_open_predictions
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-08-05", "run_type": "trade_proposals", "ticker": "AAPL",
        "direction": "long", "entry_price": 100.0,
        "tp_price": 110.0, "sl_price": 95.0})

    prov = mocker.MagicMock()
    prov.get_intraday_ohlc.return_value = pd.DataFrame(
        {"Open": [100.0], "High": [112.0], "Low": [99.0],
         "Close": [111.0], "Volume": [500]},
        index=pd.to_datetime(["2026-08-05 14:10:00"]))

    evaluate_open_predictions(conn=in_memory_db, today="2026-08-06",
                              price_provider=prov)

    row = in_memory_db.execute(
        "SELECT * FROM outcomes WHERE prediction_id=?", (pid,)).fetchone()
    assert row["evaluated_date"] == "2026-08-05", (
        "evaluated_date ist der Handelstag, dessen Bar geschlossen hat")


def test_missing_intraday_data_falls_back_to_the_next_day(in_memory_db, mocker):
    """Feiertag, Handelsstopp oder Abruffehler: ohne Fenster beginnt die
    Auswertung bei D+1, statt zu scheitern."""
    import pandas as pd
    from src import db
    from src.evaluator import evaluate_open_predictions
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-08-05", "run_type": "trade_proposals", "ticker": "AAPL",
        "direction": "long", "entry_price": 100.0,
        "tp_price": 110.0, "sl_price": 95.0})
    db.upsert_price_history(in_memory_db, "AAPL", "2026-08-06",
                            99.0, 115.0, 98.0, 114.0, 100)

    prov = mocker.MagicMock()
    prov.get_intraday_ohlc.return_value = None   # kein Fenster

    evaluate_open_predictions(conn=in_memory_db, today="2026-08-07",
                              price_provider=prov)

    row = in_memory_db.execute(
        "SELECT * FROM outcomes WHERE prediction_id=?", (pid,)).fetchone()
    assert row["exit_reason"] == "tp_hit", "der Tagesbar von D+1 traegt den Treffer"
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python -m pytest tests/unit/test_evaluator.py -k "window_starts or intraday_hit or evaluated_date_is or missing_intraday" -v`
Expected: FAIL — der Evaluator ruft noch `get_ohlc_after` und liest nicht `price_history`

- [ ] **Step 3: Imports in `src/evaluator.py` ergänzen**

Oben in `src/evaluator.py` ergänzen:

```python
import pandas as pd

from src import db
from src.signal_window import signal_time_utc, day_end_utc, collapse_to_daily_bar
```

- [ ] **Step 4: Bar-Sequenz-Helfer einfügen**

In `src/evaluator.py` vor `evaluate_open_predictions` einfügen:

```python
def _bar_sequence(conn, price_provider, pred) -> "pd.DataFrame | None":
    """Baut die Auswertungssequenz fuer eine Prediction.

    Element 1 ist die synthetische Tagesbar des SIGNALTAGS -- verdichtet aus den
    Minutenbars ab dem Signal-Zeitpunkt. Danach folgen die finalen Tagesbars aus
    price_history. Die Verdichtung ist noetig, damit _walk_forward_hit weiterhin
    je Bar einen Tag zaehlt: Minutenbars direkt in der Sequenz wuerden
    days_to_close zerstoeren, und daran haengt 3Ds hold_day.

    Fehlt das Intraday-Fenster (Feiertag, Handelsstopp, Abruffehler), beginnt die
    Sequenz bei D+1 -- die Prediction wird dadurch nicht schlechter behandelt."""
    frames = []
    start = signal_time_utc(pred["run_type"], pred["date"])
    if start is not None:
        try:
            intraday = price_provider.get_intraday_ohlc(
                pred["ticker"], start, day_end_utc(pred["date"]))
        except Exception as e:
            log.warning(f"{pred['ticker']}: Intraday-Abruf fehlgeschlagen: {e}")
            intraday = None
        bar = collapse_to_daily_bar(intraday)
        if bar is not None:
            frames.append(pd.DataFrame(
                [bar], index=pd.to_datetime([pred["date"]])))

    later = db.load_price_history_after(conn, pred["ticker"], pred["date"])
    if later is not None and not later.empty:
        frames.append(later)

    if not frames:
        return None
    return pd.concat(frames)
```

- [ ] **Step 5: `load_price_history_after` in `src/db.py` ergänzen**

Nach `load_price_history_from_db` in `src/db.py` einfügen:

```python
def load_price_history_after(
    conn: sqlite3.Connection, ticker: str, after_date: str, limit: int = 10,
) -> "pd.DataFrame | None":
    """Finale Tagesbars STRIKT NACH `after_date`, aufsteigend sortiert.

    Fuer die Walk-Forward-Auswertung: der Signaltag selbst kommt als verdichtete
    Intraday-Bar dazu (s. src/signal_window.py), hier folgen nur die Tage danach."""
    rows = conn.execute(
        """SELECT date, open, high, low, close, volume
           FROM price_history
           WHERE ticker = ? AND date > ?
           ORDER BY date ASC LIMIT ?""",
        (ticker, after_date, limit),
    ).fetchall()
    if not rows:
        return None
    df = pd.DataFrame([{
        "Open": r["open"], "High": r["high"], "Low": r["low"],
        "Close": r["close"], "Volume": r["volume"],
    } for r in rows], index=pd.to_datetime([r["date"] for r in rows]))
    return df
```

- [ ] **Step 6: `evaluate_open_predictions` umbauen**

In `src/evaluator.py` den `try/except`-Block um `get_ohlc_after` (Zeilen 84-90) ersetzen durch:

```python
        ohlc = _bar_sequence(conn, price_provider, pred)
```

und alle vier Vorkommen von `closed_date=today` beziehungsweise `evaluated_date=today` ersetzen durch `evaluated_day`, das direkt nach `for pred in rows:` gesetzt wird:

```python
    for pred in rows:
        ticker = pred["ticker"]
        # E7: evaluated_date ist der Handelstag, dessen Bar geschlossen hat --
        # nicht das Laufdatum. final_close laeuft am Folgetag; mit dem Laufdatum
        # faende _aggregate_yesterday_outcomes (WHERE evaluated_date = today - 1)
        # nichts mehr und die Fussleiste der Tagesmail zeigte stumm Nullen.
        evaluated_day = (date_cls.fromisoformat(today) - timedelta(days=1)).isoformat()
```

Dafür oben in `src/evaluator.py` ergänzen:

```python
from datetime import date as date_cls, timedelta
```

- [ ] **Step 7: Tests laufen lassen**

Run: `python -m pytest tests/unit/test_evaluator.py -v`
Expected: PASS, alle

- [ ] **Step 8: Volle Suite**

Run: `python -m pytest tests/ -q`
Expected: alle grün

- [ ] **Step 9: Commit**

```bash
git add src/evaluator.py src/db.py tests/unit/test_evaluator.py
git commit -m "feat: Auswertung ab dem Signal-Zeitpunkt auf finalen Bars

Der Evaluator liest jetzt price_history statt selbst live zu fetchen -- der
alte Abruf lief zum close-Zeitpunkt (20:30 UTC), also 3,5 h bevor die Tagesbar
final wird. High und Low koennen sich bis dahin nur ausweiten, und genau darauf
beruht die TP/SL-Pruefung: provisorische Bars melden systematisch zu wenige
Treffer.

Das Fenster beginnt am Signal-Zeitpunkt. Der Signaltag kommt als EINE
verdichtete Bar in die Sequenz, damit _walk_forward_hit weiterhin je Bar einen
Tag zaehlt und days_to_close == 1 'intraday getroffen' heisst.

evaluated_date ist ab jetzt der Handelstag, nicht das Laufdatum -- sonst findet
_aggregate_yesterday_outcomes nichts mehr."
```

### Umsetzung — zwei Commits

Task 6 ist bewusst in zwei Commits zerlegt worden, damit später trennbar bleibt,
welche der beiden Verhaltensänderungen welchen Effekt auf die Outcome-Historie
hatte.

- **`71e2db2`** — der geplante Teil. Das Auswertungsfenster beginnt am
  Signal-Zeitpunkt statt am Tagesbeginn, der Evaluator liest die finalen
  Tagesbars über das neue `db.load_price_history_after` statt sie selbst live zu
  holen, und `evaluated_date` ist der Handelstag statt des Laufdatums. Sieben
  bestehende Tests waren auf den alten Datenweg verdrahtet und hielten die von
  Spec 4.3 verworfene Annahme „der ganze Tag D zählt" fest; sie sind neu
  ausgedrückt (`days_to_close` fällt um eins, weil ein `close`-Lauf am
  Prognosetag keinen Signal-Zeitpunkt hat).

- **`efea2bd`** — der Hold-Days-Fix, ein bei der Umsetzung gefundener
  **vorbestehender** Defekt: `_walk_forward_hit` lieferte `timeout`, sobald in
  den *verfügbaren* Bars kein Treffer lag, ohne zu prüfen, ob das Fenster
  abgelaufen ist. Dadurch schloss jede Prediction beim ersten Auswertungslauf
  und `MAX_HOLD_DAYS = 5` war nie in Kraft. Neu: unvollständiges Fenster →
  `pending`, die Prediction bleibt offen und erzeugt keine `outcomes`-Zeile.
  Dazu die Notbremse `MAX_OPEN_CALENDAR_DAYS = 14` gegen Zombie-Zeilen von
  verstummten Tickern.

---

## Task 7: Snapshots befüllen, `_ensure_today_bar` zurückbauen

**Files:**
- Modify: `src/data_collector.py:269-330` (`_ensure_today_bar` entfernen), `_process_ticker`
- Modify: `src/sector_momentum.py:64-72` (ETF-Schreiber entfernen)
- Modify: `src/ranking.py:99`, `main.py` (`_persist_revision`)
- Test: `tests/unit/test_data_collector.py`, `tests/unit/test_ranking.py`

- [ ] **Step 1: Failing Test schreiben**

In `tests/unit/test_data_collector.py`:

```python
def test_collect_does_not_write_price_history(in_memory_db, mocker):
    """final_close ist der einzige Schreiber. Schreibt die Datensammlung weiter
    mit, kann die Teilbar des laufenden Tages wieder in die Historie geraten --
    genau der Frozen-Bar-Bug."""
    from src import db as _dbmod
    from src.data_collector import _process_ticker
    _dbmod.init_schema(in_memory_db)
    for d, o, h, l, c, v in _ohlcv_rows(90, "2026-08-05"):
        _dbmod.upsert_price_history(in_memory_db, "AAPL", d, o, h, l, c, v)
    before = in_memory_db.execute(
        "SELECT COUNT(*) c FROM price_history").fetchone()["c"]

    mock_price = mocker.MagicMock()
    mock_price.get_premarket_price.return_value = 321.5
    mock_earn = mocker.MagicMock()
    mock_earn.get_earnings_calendar.return_value = {}
    mock_earn.get_fundamentals.return_value = {}

    td = _process_ticker("AAPL", mock_price, mock_earn, in_memory_db,
                         "2026-08-06", "pre_market")

    after = in_memory_db.execute(
        "SELECT COUNT(*) c FROM price_history").fetchone()["c"]
    assert after == before, "collect() darf price_history nicht mehr anfassen"
    assert td is not None
    assert td["price"] == 321.5, "der Entscheidungskurs kommt live, nicht aus der DB"
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python -m pytest tests/unit/test_data_collector.py -k does_not_write -v`
Expected: FAIL — `_ensure_today_bar` schreibt weiterhin, und `td["price"]` ist der DB-Close

- [ ] **Step 3: `_ensure_today_bar` entfernen**

In `src/data_collector.py` die komplette Funktion `_ensure_today_bar` (Zeilen 269-330) löschen und den Aufruf in `_process_ticker` (Zeile 366) löschen.

- [ ] **Step 4: Live-Snapshot statt DB-Close**

In `src/data_collector.py` in `_process_ticker` die Zeile `"price": float(df["Close"].iloc[-1]),` ersetzen durch:

```python
        # Entscheidungskurs kommt LIVE, nicht aus price_history: die Historie
        # enthaelt seit dem Preismodell-Umbau nur noch finale Tagesbars und endet
        # damit bei D-1. Ohne diesen Abruf analysierte die Pipeline auf dem
        # Schluss von gestern.
        "price": _live_price(price_provider, ticker, df),
```

und vor `_process_ticker` einfügen:

```python
def _live_price(price_provider, ticker: str, df) -> float:
    """Aktueller Kurs fuer die Entscheidung. Faellt auf den letzten finalen Close
    zurueck, wenn der Live-Abruf nichts liefert -- ein alter Kurs ist besser als
    gar keine Analyse, und der Ticker wird dadurch nicht uebersprungen."""
    try:
        live = price_provider.get_premarket_price(ticker)
    except Exception as e:
        log.warning(f"{ticker}: Live-Kurs nicht abrufbar: {e}")
        live = None
    if live is not None:
        return float(live)
    log.warning(f"{ticker}: kein Live-Kurs, nutze letzten finalen Close")
    return float(df["Close"].iloc[-1])
```

- [ ] **Step 5: ETF-Schreiber in `src/sector_momentum.py` entfernen**

Die `for ts, row in df.iterrows():`-Schleife mit `db.insert_price_bar_if_missing` und das folgende `conn.commit()` löschen (Zeilen 64-72). Im Docstring des Moduls ergänzen:

```python
# Schreibt seit dem Preismodell-Umbau (2026-08-06) KEINE ETF-Bars mehr in
# price_history -- das macht final_close, und zwar mit finalen Bars. Vorher
# landete hier die Teilbar des laufenden Tages per INSERT OR IGNORE und fror
# damit die ETF-Seite der relativen Staerke ein.
```

- [ ] **Step 6: Snapshots in `src/ranking.py` befüllen**

In `src/ranking.py` in der Prediction-Zeile nach `"entry_price": analysis["current_price"],` ergänzen:

```python
        "price_premarket": analysis.get("price_premarket"),
        "is_premarket":    analysis.get("is_premarket"),
```

- [ ] **Step 7: Snapshots in `main.py:_persist_revision` befüllen**

In `main.py` in `_persist_revision`, im Dict für `supersede_prediction`, nach `"entry_price": entry,` ergänzen:

```python
        "price_premarket": pred["price_premarket"],
        "price_open":      snapshot.get("price_open"),
        "price_1610":      snapshot.get("price"),
        "is_premarket":    0,
```

- [ ] **Step 8: Tests laufen lassen**

Run: `python -m pytest tests/ -q`
Expected: alle grün. Die beiden Tests aus `e5e27c8`
(`test_todays_bar_is_refreshed_not_frozen`, `test_closed_days_are_never_overwritten`,
`test_todays_bar_is_refetched_even_when_a_row_exists`) betreffen die gelöschte
Funktion und werden mitgelöscht — s. Step 9.

- [ ] **Step 9: Die Tests zur entfallenen Funktion löschen**

Aus `tests/unit/test_data_collector.py` entfernen: `test_todays_bar_is_refreshed_not_frozen`, `test_closed_days_are_never_overwritten`, `test_todays_bar_is_refetched_even_when_a_row_exists` und den Helfer `_bar_df`. Das ist kein Abschwächen im Sinne von Regel 8, sondern das Mitziehen eines entfallenen Testgegenstands.

- [ ] **Step 10: Volle Suite**

Run: `python -m pytest tests/ --cov=src --cov-fail-under=80 -q`
Expected: alle grün, Coverage ≥ 80 %

- [ ] **Step 11: Commit**

```bash
git add src/data_collector.py src/sector_momentum.py src/ranking.py main.py tests/
git commit -m "refactor: price_history hat nur noch einen Schreiber

_ensure_today_bar() und der ETF-Schreiber in sector_momentum entfallen; beide
schrieben die Teilbar des laufenden Tages. Damit wird e5e27c8 gegenstandslos --
der Fix hat das Einfrieren entschaerft, jetzt kann es gar nicht mehr entstehen,
weil nur final_close schreibt und der nur finale Bars kennt.

Der Entscheidungskurs kommt jetzt live ueber get_premarket_price(), nicht mehr
aus dem letzten DB-Close: price_history endet seit dem Umbau bei D-1, sonst
analysierte die Pipeline auf dem Schluss von gestern.

Die drei Tests zur entfallenen Funktion sind mitgeloescht -- entfallener
Testgegenstand, kein abgeschwaechter Test."
```

---

## Task 7b: `price_open` und `is_premarket` tatsächlich befüllen

Task 7 liest beide Werte nur aus dem Snapshot — erzeugt werden sie hier. `price_open` ist der Grund, warum Task 2 überhaupt gebaut wurde: der „Open" der Tagesbar ist **nicht** der Eröffnungskurs (0,47 % Abweichung bei AAPL am 2026-08-05).

**Files:**
- Modify: `main.py` (`run_pipeline`: `is_premarket`; `run_trade_proposals`: `price_open`)
- Test: `tests/unit/test_main.py`

- [ ] **Step 1: Failing Test schreiben**

```python
def test_opening_price_comes_from_the_minute_bar_not_the_day_bar(tmp_db_path, mocker):
    """Der 'Open' der Tagesbar ist NICHT der Eroeffnungskurs: Capital.com laesst
    die Tagesbar um 08:00 UTC beginnen (openingHours, erweiterte Zeiten). Bei
    AAPL am 2026-08-05 lagen beide 0,47 % auseinander -- Tagesbar 310,54 gegen
    tatsaechlicher Open 309,09. Deshalb ein eigener MINUTE-Abruf."""
    import pandas as pd
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    pid = _pred_row(conn, ticker="AAPL")
    conn.commit(); conn.close()

    prov = MagicMock()
    prov.get_intraday_ohlc.return_value = pd.DataFrame(
        {"Open": [309.09], "High": [309.6], "Low": [307.8],
         "Close": [307.94], "Volume": [431]},
        index=pd.to_datetime(["2026-07-30 13:30:00"]))
    mocker.patch("main.CapitalComProvider", return_value=prov)

    mail = _tp_run_mocks(mocker, [{"ticker": "AAPL", "price": 311.0}])
    mocker.patch("main.CapitalComProvider", return_value=prov)
    mocker.patch("main.revalidate_one", return_value={
        "verdict": "bestaetigt", "probability_pct": 70, "reason": "ok",
        "entry_window_low": 310.0, "entry_window_high": 312.0})

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    row = conn.execute(
        "SELECT * FROM predictions WHERE run_type='trade_proposals'").fetchone()
    conn.close()
    assert row["price_open"] == 309.09, "der echte Eroeffnungskurs"
    assert row["price_1610"] == 311.0
    assert row["is_premarket"] == 0, "10:10 ET liegt nach der Eroeffnung"


def test_pre_market_marks_its_price_as_premarket(in_memory_db, mocker):
    """15:00 Berlin ist 09:00 ET -- eine halbe Stunde VOR der Eroeffnung. Der
    Kurs ist duenn gehandelt und darf in der Analyse nicht als regulaerer Kurs
    behandelt werden."""
    from main import _premarket_flag
    assert _premarket_flag("2026-08-05", "2026-08-05T13:00:00") == 1
    assert _premarket_flag("2026-08-05", "2026-08-05T14:10:00") == 0
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python -m pytest tests/unit/test_main.py -k "opening_price_comes or marks_its_price" -v`
Expected: FAIL — `ImportError: cannot import name '_premarket_flag'`

- [ ] **Step 3: `_premarket_flag` und `_opening_prices` in `main.py`**

Vor `run_pipeline` einfügen:

```python
def _premarket_flag(date: str, now_utc: str | None = None) -> int:
    """1, wenn der Erhebungszeitpunkt vor der regulaeren US-Eroeffnung liegt.

    Aus der Uhr, nicht aus marketStatus: das Feld meldete am 2026-08-06 um
    08:37 ET `TRADEABLE`, mitten in der Vorboerse."""
    now = now_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return 1 if signal_window.is_premarket(date, now) else 0


def _opening_prices(price_provider, tickers: list[str], date: str) -> dict[str, float]:
    """Tatsaechlicher Eroeffnungskurs je Ticker, minutengenau.

    Der 'Open' der Tagesbar taugt dafuer nicht: Capital.com laesst sie um
    08:00 UTC beginnen (openingHours, erweiterte Zeiten). Bei AAPL am 2026-08-05
    lagen Tagesbar-Open (310,54) und tatsaechlicher Open (309,09) 0,47 %
    auseinander.

    Zum Abrufzeitpunkt (10:10 ET) liegt die Eroeffnung bereits in der
    Vergangenheit, der Abruf ist also rein historisch. Commodities und Crypto
    haben keine Eroeffnung -- fuer sie bleibt der Wert schlicht aus (E6)."""
    start = signal_window.regular_open_utc(date)
    end = (datetime.fromisoformat(start) + timedelta(minutes=1)).strftime(
        "%Y-%m-%dT%H:%M:%S")
    out: dict[str, float] = {}
    for ticker in tickers:
        try:
            df = price_provider.get_intraday_ohlc(ticker, start, end)
        except Exception as e:
            log.warning(f"{ticker}: Eroeffnungskurs nicht abrufbar: {e}")
            continue
        if df is None or df.empty:
            log.info(f"{ticker}: kein Eroeffnungs-Bar (24/7-Instrument?)")
            continue
        out[ticker] = float(df["Open"].iloc[0])
    return out
```

Import oben in `main.py` ergänzen:

```python
from datetime import timezone
from src import signal_window
```

- [ ] **Step 4: In `run_trade_proposals` verdrahten**

In `main.py` in `run_trade_proposals` direkt nach dem Aufbau von `snapshots` einfügen:

```python
        opens = _opening_prices(price_provider, list(snapshots), date)
        for _t, _snap in snapshots.items():
            _snap["price_open"] = opens.get(_t)
```

- [ ] **Step 5: In `run_pipeline` verdrahten**

In `main.py` in `run_pipeline` nach dem Aufbau der Analysen, vor `rank_and_persist`, einfügen:

```python
        # Der 15:00-Kurs ist regulaer vorboerslich (09:00 ET). Die Markierung
        # geht in die Prediction-Zeile und in den Re-Validierungs-Prompt --
        # ein duenn gehandelter Vorboersenkurs ist kein Sitzungskurs.
        _pm = _premarket_flag(date)
        for _a in analyses:
            _a["price_premarket"] = _a.get("current_price")
            _a["is_premarket"] = _pm
```

- [ ] **Step 6: Tests laufen lassen**

Run: `python -m pytest tests/ -q`
Expected: alle grün

- [ ] **Step 7: Commit**

```bash
git add main.py tests/unit/test_main.py
git commit -m "feat: echten Eroeffnungskurs und Vorboersen-Markierung befuellen

price_open kommt aus einer MINUTE-Bar der regulaeren Eroeffnung, nicht aus dem
'Open' der Tagesbar: Capital.com laesst die Tagesbar um 08:00 UTC beginnen
(openingHours, erweiterte Zeiten). Bei AAPL am 2026-08-05 lagen beide 0,47 %
auseinander -- 310,54 gegen 309,09. Zum Abrufzeitpunkt 10:10 ET liegt die
Eroeffnung bereits in der Vergangenheit, der Abruf ist rein historisch.

Commodities und Crypto haben keine Eroeffnung; fuer sie bleibt price_open NULL
statt einen Wert zu erfinden (E6).

is_premarket kommt aus der Uhr und nicht aus marketStatus -- das Feld meldete
am 2026-08-06 um 08:37 ET TRADEABLE, mitten in der Vorboerse."
```

---

## Task 8: Die Sweep-Stellen nachziehen

`load_sector_db_momentum` zuerst — sie ist die einzige, die still einen Guardrail abschaltet.

**Files:**
- Modify: `src/db.py:369-383` (`load_sector_db_momentum`)
- Modify: `src/signal_checks.py:33-49` (`daily_change_pct`)
- Modify: `src/data_collector.py:220-235` (`_fill_price_gaps`)
- Test: `tests/unit/test_db.py`, `tests/unit/test_signal_checks.py`

- [ ] **Step 1: Failing Test schreiben**

```python
def test_sector_db_momentum_uses_the_last_final_day(in_memory_db):
    """Der Join lief auf cur.date = heute, also exakte Gleichheit. Seit
    price_history nur noch finale Bars enthaelt, existiert die heutige Zeile zur
    Laufzeit nicht -- der Join traefe nie, db_momentum bliebe dauerhaft NULL, D9
    koennte 'beide Signale vorhanden' nie erfuellen und der Sektor-Guardrail
    waere lautlos tot."""
    db.init_schema(in_memory_db)
    in_memory_db.execute(
        "INSERT INTO sectors (name, etf) VALUES ('Semis', 'SOXX')")
    sid = in_memory_db.execute(
        "SELECT id FROM sectors WHERE name='Semis'").fetchone()["id"]
    for t in ("AAPL", "MSFT", "NVDA"):
        in_memory_db.execute(
            "INSERT INTO ticker_sectors (ticker, sector_id) VALUES (?, ?)", (t, sid))
        db.upsert_price_history(in_memory_db, t, "2026-08-04", 100, 101, 99, 100, 10)
        db.upsert_price_history(in_memory_db, t, "2026-08-05", 100, 103, 100, 102, 10)
    in_memory_db.commit()

    # Lauf am 2026-08-06: fuer heute gibt es noch keine finale Bar.
    out = db.load_sector_db_momentum(in_memory_db, date="2026-08-06")
    assert sid in out, "der Sektor muss trotzdem einen Wert bekommen"
    assert out[sid]["momentum"] == pytest.approx(2.0), "102 gegen 100 sind +2 %"
    assert out[sid]["ticker_count"] == 3
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `python -m pytest tests/unit/test_db.py -k sector_db_momentum_uses -v`
Expected: FAIL — `assert sid in out` (leeres Ergebnis, weil `cur.date = '2026-08-06'` nicht trifft)

- [ ] **Step 3: `load_sector_db_momentum` umstellen**

In `src/db.py` die SQL ersetzen:

```python
    rows = conn.execute(
        """WITH last_two AS (
             SELECT ts.sector_id AS sector_id, ph.ticker AS ticker,
                    ph.close AS close, ph.date AS date,
                    ROW_NUMBER() OVER (PARTITION BY ph.ticker
                                       ORDER BY ph.date DESC) AS rn
             FROM ticker_sectors ts
             JOIN price_history ph ON ph.ticker = ts.ticker AND ph.date <= ?
           )
           SELECT cur.sector_id AS sector_id,
                  AVG((cur.close - prev.close) / prev.close * 100.0) AS momentum,
                  COUNT(*) AS n
           FROM last_two cur
           JOIN last_two prev
             ON prev.ticker = cur.ticker AND prev.rn = 2
           WHERE cur.rn = 1 AND prev.close > 0
           GROUP BY cur.sector_id""",
        (date,),
    ).fetchall()
```

Und den Docstring ergänzen:

```python
    """Berechnet je Sub-Sektor die durchschnittliche Tagesperformance aller
    zugeordneten Ticker aus price_history — reines SQL, keine API-Calls, 0 EUR.

    Nimmt die beiden letzten finalen Bars bis einschliesslich `date`, nicht
    'heute gegen gestern'. Seit dem Preismodell-Umbau (2026-08-06) enthaelt
    price_history nur finale Tagesbars und endet zur Laufzeit bei D-1; ein Join
    auf exakte Gleichheit mit heute traefe nie, db_momentum bliebe dauerhaft
    NULL und der D9-Guardrail waere lautlos tot.

    Gibt {sector_id: {"momentum": float | None, "ticker_count": int}} zurueck.
    `momentum` ist None, wenn weniger als `min_tickers` Ticker zwei Bars haben."""
```

- [ ] **Step 4: `daily_change_pct` dokumentieren**

In `src/signal_checks.py` den Docstring ersetzen (die SQL bleibt unverändert — sie nimmt bereits `date <= ?` mit `LIMIT 2`):

```python
    """Tagesperformance des letzten ABGESCHLOSSENEN Handelstags, in Prozent.

    Nimmt die beiden letzten Bars bis einschliesslich `date`. Seit dem
    Preismodell-Umbau (2026-08-06) enthaelt price_history nur finale Bars; der
    laufende Tag ist hier also bewusst NICHT enthalten. Das ist die richtige
    Grundlage: relative Staerke und D9 vergleichen abgeschlossene Tage, eine
    Teilbar waere kein Vergleichsmassstab.

    None, wenn weniger als zwei Bars vorliegen oder der Vortagesschluss 0 ist."""
```

- [ ] **Step 5: `_fill_price_gaps` stilllegen**

In `src/data_collector.py` am Anfang von `_fill_price_gaps` einfügen:

```python
    # Seit dem Preismodell-Umbau (2026-08-06) fuellt final_close die Historie
    # taeglich auf; echte Luecken entstehen nur noch bei laengeren Ausfaellen und
    # werden mit setup/historical_loader.py --all nachgeladen. Die Funktion
    # bleibt als Sicherheitsnetz stehen, greift aber im Normalbetrieb nicht mehr.
```

- [ ] **Step 6: Tests laufen lassen**

Run: `python -m pytest tests/ -q`
Expected: alle grün

- [ ] **Step 7: Commit**

```bash
git add src/db.py src/signal_checks.py src/data_collector.py tests/
git commit -m "fix: Sektor-Momentum ohne die Bar des laufenden Tages

load_sector_db_momentum jointe auf cur.date = heute, also exakte Gleichheit.
Seit price_history nur noch finale Bars enthaelt, existiert die heutige Zeile
zur Laufzeit nicht: der Join traefe nie, db_momentum bliebe dauerhaft NULL, D9
koennte 'beide Signale vorhanden' nie erfuellen -- der Sektor-Guardrail waere
lautlos tot. Kein Fehler, kein Log, nur ein Guardrail ohne Wirkung.

Nimmt jetzt die beiden letzten finalen Bars je Ticker.

daily_change_pct und _fill_price_gaps behalten ihr Verhalten und sagen im
Docstring, dass der laufende Tag bewusst nicht enthalten ist."
```

---

## Task 9: Cron, Concurrency-Lock, Sichtbarkeitswarnung

**Files:**
- Modify: `.github/workflows/analyze.yml`
- Modify: `main.py` (Warnung in `run_pipeline`), `src/db.py` (`load_final_bar_date`)
- Test: `tests/unit/test_workflow_config.py`, `tests/unit/test_main.py`

- [ ] **Step 1: Failing Test schreiben**

In `tests/unit/test_workflow_config.py`:

```python
def test_final_close_runs_daily_not_only_on_weekdays():
    """Der Samstagslauf holt Freitags Schlusskurs: openingHours schliesst
    freitags um 21:00 UTC, die Bar wird also erst nach Mitternacht final."""
    assert "'15 0 * * *'" in WORKFLOW
    assert 'T="final_close"' in WORKFLOW


def test_workflow_has_a_concurrency_lock():
    """Zwei Laeufe auf derselben DB gewinnen den Release-Upload nach
    Zufallsprinzip -- wer zuletzt hochlaedt, gewinnt."""
    assert "concurrency:" in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW, (
        "Ein laufender Job schreibt bereits phasenweise in die DB -- ihn "
        "abzuschneiden waere schlimmer als zu warten")
```

In `tests/unit/test_main.py`:

```python
def test_pre_market_warns_when_the_final_bar_is_missing(in_memory_db):
    """final_close verschickt keine Mail. Faellt er aus, wird nichts mehr
    bewertet -- und niemand merkt es. Deshalb prueft pre_market, ob die finale
    Bar des letzten Handelstags vorliegt."""
    from src import db
    from main import _final_bar_warning
    db.init_schema(in_memory_db)
    db.upsert_price_history(in_memory_db, "AAPL", "2026-08-03",
                            100, 101, 99, 100, 10)

    warn = _final_bar_warning(in_memory_db, date="2026-08-06")
    assert warn is not None and "final_close" in warn

    db.upsert_price_history(in_memory_db, "AAPL", "2026-08-05",
                            100, 101, 99, 100, 10)
    assert _final_bar_warning(in_memory_db, date="2026-08-06") is None
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python -m pytest tests/unit/test_workflow_config.py tests/unit/test_main.py -k "final_close or concurrency or final_bar" -v`
Expected: FAIL

- [ ] **Step 3: Cron und Lock in `analyze.yml`**

Nach der letzten `- cron:`-Zeile einfügen:

```yaml
    # final_close haengt an der BAR-GRENZE, nicht an einer Boersensitzung:
    # openingHours meldet `zone: UTC` und schliesst auf 00:00 UTC. Job und
    # Datenquelle liegen damit am selben Anker -- eine Zeitumstellung verschiebt
    # beide nicht gegeneinander, es gibt hier also KEINE DST-Kopplung (anders als
    # bei trade_proposals, der zwei Slots braucht).
    # Taeglich, nicht Mo-Fr: freitags schliesst der Handel um 21:00 UTC, die Bar
    # wird erst danach final -- erst der Samstagslauf holt sie.
    # 15 statt 0: Puffer auf die Bar-Grenze. Actions-Crons verspaeten sich nur.
    - cron: '15 0 * * *'      # final_close       00:15 UTC, taeglich
```

Nach dem `permissions:`-Block einfügen:

```yaml
concurrency:
  # Zwei gleichzeitige Laeufe arbeiten auf derselben tracking.db, und beim
  # Release-Upload gewinnt schlicht der, der zuletzt hochlaedt.
  # cancel-in-progress: false, weil ein laufender Job bereits phasenweise
  # persistiert -- ihn abzuschneiden waere schlimmer als zu warten.
  group: analyze-${{ github.repository }}
  cancel-in-progress: false
```

Im `case`-Block ergänzen:

```bash
            "15 0 * * *")    T="final_close" ;;
```

Und in den `workflow_dispatch`-Optionen:

```yaml
        options: [pre_market, trade_proposals, close, final_close, weekly]
```

- [ ] **Step 4: Warnung in `main.py` implementieren**

In `main.py` vor `run_pipeline` einfügen:

```python
def _final_bar_warning(conn, date: str) -> str | None:
    """Warnt, wenn fuer den letzten Werktag keine finale Tagesbar vorliegt.

    final_close verschickt bewusst keine Mail. Faellt er aus, wird nichts mehr
    bewertet und niemand merkt es -- die Weekly saehe nur duenner aus. Diese
    Pruefung macht den Ausfall in der Tagesmail sichtbar."""
    d = date_cls.fromisoformat(date) - timedelta(days=1)
    while d.weekday() >= 5:          # Sa/So ueberspringen
        d -= timedelta(days=1)
    newest = db.load_final_bar_date(conn)
    if newest is not None and newest >= d.isoformat():
        return None
    return (f"⚠️ Keine finale Tagesbar für {d.isoformat()} "
            f"(neueste: {newest or 'keine'}) — lief final_close?")
```

Und in `run_pipeline` nach dem Setzen von `payload["yesterday_outcomes"]`:

```python
    _warn = _final_bar_warning(conn, date=date)
    if _warn:
        payload["briefing"] = [*payload.get("briefing", []), _warn]
```

- [ ] **Step 5: `load_final_bar_date` in `src/db.py`**

```python
def load_final_bar_date(conn: sqlite3.Connection) -> str | None:
    """Datum der neuesten finalen Tagesbar in price_history, oder None."""
    row = conn.execute("SELECT MAX(date) AS d FROM price_history").fetchone()
    return row["d"] if row and row["d"] else None
```

- [ ] **Step 6: Tests laufen lassen**

Run: `python -m pytest tests/ -q`
Expected: alle grün

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/analyze.yml main.py src/db.py tests/
git commit -m "feat: final_close-Cron, Concurrency-Lock und Ausfallwarnung

Cron '15 0 * * *' -- taeglich, nicht Mo-Fr: freitags schliesst der Handel um
21:00 UTC, erst der Samstagslauf holt die finale Bar.

DST ist hier unkritisch und das soll nicht erneut in Frage gestellt werden:
final_close haengt an der Bar-Grenze, und die ist laut openingHours selbst
UTC-fix (zone: UTC). Job und Datenquelle liegen am selben Anker.

Der Concurrency-Lock existierte bisher in KEINEM Workflow. cancel-in-progress
bleibt false, weil ein laufender Job bereits phasenweise persistiert.

Da final_close keine Mail verschickt, wuerde sein Ausfall unbemerkt bleiben --
pre_market warnt jetzt sichtbar, wenn die finale Bar des letzten Werktags fehlt."
```

---

## Task 10: Doku

Kein Punkt gilt als fertig, solange die Doku den alten Stand beschreibt.

**Files:**
- Modify: `docs/superpowers/specs/PROJECT_STATUS.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`

- [ ] **Step 1: `PROJECT_STATUS.md`**

- Run-Type-Tabelle in B.1 um `final_close` (00:15 UTC, täglich, ~0,00 EUR) ergänzen.
- In **P2.8** beim Eintrag „Eingefrorene Tagesbar" ergänzen: *„Am 2026-08-06 durch den Preismodell-Umbau ersetzt — `_ensure_today_bar()` entfällt, `e5e27c8` ist zurückgebaut, `price_history` hat nur noch einen Schreiber."*
- In **Abschnitt 2b** die beiden zurückgestellten Ideen aufnehmen:

```markdown
| **Gap-Analyse Final-Close → nächster Open** | Mit `price_open` und der finalen Tages-OHLC liegen ab dem Preismodell-Umbau beide Seiten vor. Offen ist, ob die Lücke prognostisch etwas trägt. |
| **Fair-Value-Gap-Erkennung im Lernmodul** | Setzt die Gap-Analyse voraus. Gehört zu 3D, nicht davor. |
```

- [ ] **Step 2: `CLAUDE.md`**

- Run-Type-Liste um `final_close` ergänzen.
- Unter den Designentscheidungen den Frozen-Bar-Punkt ersetzen durch:

```markdown
- `price_history` enthält **ausschliesslich finale Tagesbars** und hat **genau einen
  Schreiber**: `final_close` (00:15 UTC). Entscheidungskurse gehören nicht dorthin,
  sondern in `predictions.price_premarket` / `price_open` / `price_1610`. Die
  Vermischung beider war der Frozen-Bar-Bug.
- ⚠️ Capital.com beantwortet ein `to` **in der Zukunft** (UTC) mit HTTP 400 — fünf
  Minuten genügen. Nicht dokumentiert. `_not_in_future()` klemmt es.
```

- [ ] **Step 3: `docs/ARCHITECTURE.md`**

- `src/signal_window.py` als neues Modul aufnehmen.
- Phasenfolge um `final_close` ergänzen.
- Die Trennung Indikator-Historie / Entscheidungs-Snapshot aus Spec Abschnitt 1 aufnehmen.

- [ ] **Step 4: Volle Suite**

Run: `python -m pytest tests/ --cov=src --cov-fail-under=80 -q`
Expected: alle grün

- [ ] **Step 5: Commit**

```bash
git add docs/ CLAUDE.md
git commit -m "docs: Preismodell-Umbau in den lebenden Dokumenten nachziehen

PROJECT_STATUS (Run-Types, P2.8, Backlog 2b), CLAUDE.md (ein Schreiber, der
400er-Merkposten) und ARCHITECTURE (signal_window, Phasenfolge, die Trennung von
Indikator-Historie und Entscheidungs-Snapshot).

Plandateien unter docs/superpowers/plans/ bleiben unangetastet -- sie sind
historische Protokolle (E5)."
```

---

## Selbstprüfung nach Abschluss

- [ ] `python -m pytest tests/ --cov=src --cov-fail-under=80 -q` grün
- [ ] `grep -rn "_ensure_today_bar" src/ main.py tests/` liefert nichts
- [ ] `grep -rn "insert_price_bar_if_missing" src/ main.py` nur noch in `setup/historical_loader.py` und der Definition
- [ ] `git log --oneline origin/main..HEAD` zeigt **elf** neue Commits (Tasks 1–10 inkl. 7b), **nichts gepusht**
- [ ] `grep -rn "price_open" main.py src/` zeigt sowohl die Befüllung (Task 7b) als auch die Persistenz (Task 7) — ein Wert, der nur gelesen und nie geschrieben wird, ist der Fehler, den die Selbstprüfung dieses Plans gefunden hat
- [ ] `analyze.yml` bleibt `disabled_manually` — die Aktivierung ist P2.4 und gehört Korbinian
