# Trainingsdaten-Fundament Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Für jede Prediction dauerhaft rekonstruierbar machen, was das System zum Zeitpunkt der Entscheidung wusste — Voraussetzung für Sprint 3D.

**Architecture:** Rein additiv. Eine benannte Retention-Konstante ersetzt vier SQL-Literale; sieben neue `predictions`-Spalten frieren Fundamental-Rohwerte, Analysten-Aktualität und relative Stärke ein. Kein DROP, keine Umbenennung, kein Backfill.

**Tech Stack:** Python 3.12, SQLite, pytest. Migration nach dem bestehenden `init_schema()`-Muster (PRAGMA-Prüfung → `ALTER TABLE ADD COLUMN`).

**Spec:** `docs/superpowers/specs/2026-08-20-trainingsdaten-fundament-design.md`

## Global Constraints

- **Additiv only (E7):** ausschliesslich `ALTER TABLE ... ADD COLUMN`. Kein DROP, kein RENAME, kein UPDATE bestehender Zeilen.
- **Kein Backfill (E6):** neue Spalten bleiben für die 14 Bestands-Predictions `NULL`.
- **Testlauf:** `pytest tests/ --ignore=tests/live -q`, Baseline **900 grün**.
- **Netz-Sperre:** Tests ausserhalb `tests/live/` dürfen nicht nach draussen telefonieren.
- **Fixture-Muster:** `in_memory_db` liefert eine LEERE DB — jeder Test ruft `init_schema()` selbst.
- **`save_prediction()` muss fehlende neue Keys als `None` tolerieren**, sonst brechen Bestandsaufrufer.
- **Commit-Nachrichten** enden mit `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. **Niemals pushen.**

---

### Task 1: Retention-Konstante für Trainingsdaten

**Files:**
- Modify: `config.py` (neue Konstante ans Ende des Retention-Blocks)
- Modify: `src/db.py` — `cleanup_old_data()`
- Test: `tests/unit/test_db.py`

**Interfaces:**
- Produces: `config.LEARNING_RETENTION_DAYS: int = 730`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_db.py  (ans Ende anhaengen)

# ---------- LEARNING_RETENTION_DAYS (Spec E1) ----------
import config as _cfg


def _seed_row(conn, table, date):
    cols = {
        "news_summaries": "(ticker, date, summary) VALUES ('AAPL', ?, 's')",
        "trend_analyses": "(date, trend_name) VALUES (?, 'ai')",
        "skipped_tickers": "(ticker, date, reason) VALUES ('AAPL', ?, 'r')",
        "cutoff_log": "(ticker, date) VALUES ('AAPL', ?)",
    }[table]
    conn.execute(f"INSERT INTO {table} {cols}", (date,))
    conn.commit()


@pytest.mark.parametrize("table", [
    "news_summaries", "trend_analyses", "skipped_tickers", "cutoff_log",
])
def test_training_tables_share_one_retention_and_keep_recent_rows(in_memory_db, table):
    """Der news_summaries-Fehler war, dass EINE Tabelle still auf einer
    kuerzeren Frist stand. Deshalb je Tabelle ein Test."""
    init_schema(in_memory_db)
    recent = (date_cls.today() - timedelta(days=_cfg.LEARNING_RETENTION_DAYS - 5)).isoformat()
    _seed_row(in_memory_db, table, recent)

    cleanup_old_data(in_memory_db)

    n = in_memory_db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    assert n == 1, f"{table}: Zeile innerhalb der Frist wurde geloescht"


@pytest.mark.parametrize("table", [
    "news_summaries", "trend_analyses", "skipped_tickers", "cutoff_log",
])
def test_training_tables_drop_rows_beyond_retention(in_memory_db, table):
    init_schema(in_memory_db)
    old = (date_cls.today() - timedelta(days=_cfg.LEARNING_RETENTION_DAYS + 5)).isoformat()
    _seed_row(in_memory_db, table, old)

    cleanup_old_data(in_memory_db)

    n = in_memory_db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    assert n == 0, f"{table}: Zeile jenseits der Frist blieb stehen"
```

Prüfe zuerst, ob `date_cls`, `timedelta`, `cleanup_old_data`, `init_schema` und `pytest` in `tests/unit/test_db.py` bereits importiert sind — falls nicht, ergänze:
```python
from datetime import date as date_cls, timedelta
from src.db import cleanup_old_data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_db.py -k retention -q`
Expected: FAIL — `AttributeError: module 'config' has no attribute 'LEARNING_RETENTION_DAYS'`

- [ ] **Step 3: Konstante anlegen**

In `config.py` hinter `TICKER_RETRY_AFTER_DAYS` einfügen:

```python
# Sprint 3D / Trainingsdaten-Fundament (Spec E1): gemeinsame Aufbewahrungsfrist
# fuer die vier Tabellen, aus denen das Lernmodul spaeter Merkmale zieht.
#
# ⚠️ Bis 2026-08-20 standen hier VIER verschiedene Literale direkt im SQL von
# cleanup_old_data() -- und news_summaries stand als einzige auf 30 Tagen, weil
# sie als Logtabelle angelegt wurde, bevor C.16 sie zur Trainingsdatenquelle
# machte. Man behielt das Label (outcomes) und verlor die Begruendung. Eine
# benannte Konstante macht die Frist zu einer bewussten Entscheidung.
#
# Zwei Jahre, weil Saisonalitaet und Regimewechsel mehr als einen Jahreszyklus
# brauchen -- sonst lernt 3D ein einzelnes Marktjahr auswendig.
# ⚠️ GROESSE: bei 20 Tickern ~27 news_summaries-Zeilen/Tag (~20k in 2 Jahren,
# wenige MB). Bei 500 Tickern waeren es ~370k Zeilen mit Volltext (grob 300 MB) --
# die DB reist ueber GitHub-Release-Artefakte, also bei einer Universums-
# vergroesserung diese Frist erneut pruefen.
LEARNING_RETENTION_DAYS = 730
```

- [ ] **Step 4: `cleanup_old_data()` umstellen**

In `src/db.py` die vier `DELETE`-Zeilen ersetzen. Die Funktion nutzt bisher ein
`executescript`-artiges SQL mit Literalen; ersetze die vier Zeilen durch
parametrisierte Einzelaufrufe:

```python
    # Spec E1: eine gemeinsame Frist statt vier Literalen -- s. Kommentar an
    # config.LEARNING_RETENTION_DAYS.
    for _table in ("news_summaries", "trend_analyses", "skipped_tickers",
                   "cutoff_log"):
        conn.execute(
            f"DELETE FROM {_table} WHERE date < date('now', ?)",
            (f"-{config.LEARNING_RETENTION_DAYS} days",),
        )
```

Stelle sicher, dass `import config` in `src/db.py` vorhanden ist (ist es).
Entferne die vier alten `DELETE FROM ...`-Zeilen aus dem SQL-Block.

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_db.py -q && pytest tests/ --ignore=tests/live -q`
Expected: alle grün, Gesamtzahl 900 + 8 neue = 908

- [ ] **Step 6: Commit**

```bash
git add config.py src/db.py tests/unit/test_db.py
git commit -m "$(cat <<'EOF'
feat: gemeinsame Retention-Frist fuer Trainingsdaten-Tabellen

news_summaries stand als einzige auf 30 Tagen -- vergeben, als sie noch
Logtabelle war, bevor C.16 sie zur Trainingsdatenquelle machte. Damit ging
die Begruendung einer Prediction verloren, waehrend das Label blieb.

Vier SQL-Literale -> config.LEARNING_RETENTION_DAYS = 730.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Analysten-Periode aus Finnhub durchreichen

**Files:**
- Modify: `src/providers/finnhub_provider.py:83-105`
- Test: `tests/unit/test_finnhub_provider.py`

**Interfaces:**
- Produces: `get_fundamentals()` liefert zusätzlich `"analyst_consensus_period": str | None` (Finnhubs `period`, ISO-Datum)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_finnhub_provider.py  (ans Ende anhaengen)

# ---------- Analysten-Aktualitaet (Spec E3) ----------

def test_get_fundamentals_passes_through_the_consensus_period(monkeypatch):
    """Bis 2026-08-20 wurde recs[0] ohne jede Datumspruefung genommen -- ein
    Konsens von vor drei Monaten war im Prompt nicht von einem tagesaktuellen
    zu unterscheiden. Fuer 3D ist ein Feature ohne Zeitbezug Rauschen."""
    from src.providers import finnhub_provider as fp

    fake = MagicMock()
    fake.company_profile2.return_value = {"finnhubIndustry": "Tech",
                                          "marketCapitalization": 3_000_000}
    fake.company_basic_financials.return_value = {"metric": {}}
    fake.recommendation_trends.return_value = [
        {"period": "2026-08-01", "buy": 8, "hold": 2, "sell": 0},
    ]
    monkeypatch.setattr(fp, "_client", fake)

    out = fp.FinnhubProvider().get_fundamentals("AAPL")

    assert out["analyst_consensus_period"] == "2026-08-01"
    assert out["consensus"] == "buy"


def test_get_fundamentals_period_is_none_when_finnhub_omits_it(monkeypatch):
    from src.providers import finnhub_provider as fp

    fake = MagicMock()
    fake.company_profile2.return_value = {}
    fake.company_basic_financials.return_value = {"metric": {}}
    fake.recommendation_trends.return_value = [{"buy": 5, "hold": 5, "sell": 0}]
    monkeypatch.setattr(fp, "_client", fake)

    out = fp.FinnhubProvider().get_fundamentals("AAPL")

    assert out["analyst_consensus_period"] is None
```

Falls `MagicMock` dort noch nicht importiert ist: `from unittest.mock import MagicMock`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_finnhub_provider.py -k consensus_period -q`
Expected: FAIL — `KeyError: 'analyst_consensus_period'`

- [ ] **Step 3: Provider erweitern**

In `src/providers/finnhub_provider.py`, im `consensus`-Block:

```python
        consensus = None
        consensus_period = None
        if recs:
            r     = recs[0]
            # Spec E3: die Periode mitschreiben. recs[0] ist die juengste
            # Meldung, sagt aber nichts darueber, WIE jung -- ohne dieses Feld
            # ist ein drei Monate alter Konsens nicht von einem taggleichen zu
            # unterscheiden. Bewusst NICHT hier verwerfen: welche Frist richtig
            # ist, soll Sprint 3D messen, nicht diese Zeile entscheiden.
            consensus_period = r.get("period")
            total = (r.get("buy") or 0) + (r.get("hold") or 0) + (r.get("sell") or 0)
            if total > 0:
                ratio     = (r.get("buy") or 0) / total
                consensus = "buy" if ratio >= 0.6 else ("sell" if ratio <= 0.3 else "hold")
```

und im Rückgabe-Dict:

```python
            "analyst_upside": None,   # Spec E5: bewusst leer -- Finnhub liefert
                                      # hier kein Kursziel. Die Spalte bleibt als
                                      # Landestelle fuer eine spaetere Quelle.
            "consensus":      consensus,
            "analyst_consensus_period": consensus_period,
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_finnhub_provider.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/providers/finnhub_provider.py tests/unit/test_finnhub_provider.py
git commit -m "$(cat <<'EOF'
feat: Analysten-Konsens traegt jetzt seine Periode

recs[0] wurde ohne Datumspruefung genommen; ein Konsens von vor drei Monaten
war im Prompt nicht von einem tagesaktuellen zu unterscheiden. Die Periode
wird aufgezeichnet, nicht durchgesetzt -- welche Frist richtig ist, misst 3D.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Periode durch Cache und `td` reichen

**Files:**
- Modify: `src/db.py` — `fundamentals_cache`-Schema, Migration, `save_fundamentals_cache()`
- Modify: `src/data_collector.py:70-82` — `_apply_fundamentals_to_td()`
- Test: `tests/unit/test_db.py`, `tests/unit/test_data_collector.py`

**Interfaces:**
- Consumes: `get_fundamentals()["analyst_consensus_period"]` (Task 2)
- Produces: `td["analyst_consensus_period"]`, Spalte `fundamentals_cache.analyst_consensus_period`

⚠️ **Sidecar-Invariante:** `td` wandert in drei Claude-Prompts. Ein neuer Schlüssel ändert sie alle. Das ist hier **gewollt** (die Periode ist echte Entscheidungsinformation) — aber der Test, der die Schlüsselmenge von `_process_ticker()` pinnt, muss mitgezogen werden.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_db.py

def test_fundamentals_cache_roundtrips_the_consensus_period(in_memory_db):
    init_schema(in_memory_db)
    save_fundamentals_cache(in_memory_db, "AAPL", {
        "pe_ratio": 25.0, "consensus": "buy",
        "analyst_consensus_period": "2026-08-01",
    }, fetched_date="2026-08-20")

    row = get_cached_fundamentals(in_memory_db, "AAPL", today="2026-08-20")

    assert row["analyst_consensus_period"] == "2026-08-01"
```

```python
# tests/unit/test_data_collector.py

def test_fundamentals_period_reaches_the_ticker_data():
    from src.data_collector import _apply_fundamentals_to_td
    td = {}
    _apply_fundamentals_to_td(td, {
        "pe_ratio": 25.0, "consensus": "buy",
        "analyst_consensus_period": "2026-08-01",
    }, "2026-08-20")

    assert td["analyst_consensus_period"] == "2026-08-01"
```

Passe die Signatur im Test an die echte von `_apply_fundamentals_to_td()` an (siehe `src/data_collector.py`) — falls sie `(td, fundamentals, date)` lautet, passt der Test so.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_db.py -k consensus_period tests/unit/test_data_collector.py -k period -q`
Expected: FAIL

- [ ] **Step 3: Schema, Migration und Schreiber erweitern**

In `src/db.py` im `CREATE TABLE IF NOT EXISTS fundamentals_cache`-Block die Spalte ergänzen:
```sql
    analyst_consensus_period TEXT,
```

In `init_schema()` beim bestehenden PRAGMA-Migrationsblock ergänzen:
```python
    # Spec E7: additive Migration -- Bestands-DBs bekommen die Spalte, behalten
    # ihre Daten.
    _fc_cols = {r["name"] for r in conn.execute("PRAGMA table_info(fundamentals_cache)")}
    if "analyst_consensus_period" not in _fc_cols:
        conn.execute(
            "ALTER TABLE fundamentals_cache ADD COLUMN analyst_consensus_period TEXT")
```

In `save_fundamentals_cache()` die feste Spaltenliste um `analyst_consensus_period` erweitern (R13: die Liste ist bewusst fest) und den Wert aus `data.get("analyst_consensus_period")` ziehen.

In `src/data_collector.py:_apply_fundamentals_to_td()`:
```python
        "analyst_consensus":     fundamentals.get("consensus"),
        "analyst_consensus_period": fundamentals.get("analyst_consensus_period"),
```

- [ ] **Step 4: Sidecar-Test nachziehen**

Suche den Test, der die Schlüsselmenge pinnt:
`grep -rn "Schluesselmenge\|exact key set\|_process_ticker" tests/unit/test_data_collector.py`
Ergänze `analyst_consensus_period` in der erwarteten Menge, mit Kommentar:
```python
    # Spec E3: bewusst im td -- die Periode ist echte Entscheidungsinformation
    # und darf im Prompt sichtbar sein, anders als die 29 Plan-1-Indikatoren.
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/ --ignore=tests/live -q`
Expected: alle grün

- [ ] **Step 6: Commit**

```bash
git add src/db.py src/data_collector.py tests/unit/test_db.py tests/unit/test_data_collector.py
git commit -m "$(cat <<'EOF'
feat: Analysten-Periode durch Cache und Ticker-Daten reichen

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Sieben neue `predictions`-Spalten + Migration

**Files:**
- Modify: `src/db.py` — `predictions`-Schema, Migration, `_insert_prediction()`
- Test: `tests/unit/test_db.py`

**Interfaces:**
- Produces: `predictions` trägt `pe_ratio`, `forward_pe`, `market_cap_b`, `debt_equity`, `analyst_consensus`, `analyst_consensus_period`, `relative_strength`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_db.py

_FROZEN_FIELDS = {
    "pe_ratio": 25.0, "forward_pe": 23.0, "market_cap_b": 3000.0,
    "debt_equity": 1.4, "analyst_consensus": "buy",
    "analyst_consensus_period": "2026-08-01", "relative_strength": 1.25,
}


def test_prediction_freezes_what_the_system_knew(in_memory_db):
    """Spec 1: die Rohwerte gehoeren zur ENTSCHEIDUNG, nicht zum Ticker --
    fundamentals_cache haelt nur eine Zeile je Ticker und ueberschreibt sie."""
    init_schema(in_memory_db)
    pred = _insert_test_prediction(in_memory_db, extra=_FROZEN_FIELDS)

    row = in_memory_db.execute(
        "SELECT * FROM predictions WHERE id=?", (pred,)).fetchone()

    for k, v in _FROZEN_FIELDS.items():
        assert row[k] == v, f"{k} wurde nicht eingefroren"


def test_prediction_tolerates_missing_frozen_fields(in_memory_db):
    """Spec E6: Bestandsaufrufer duerfen die neuen Keys weglassen."""
    init_schema(in_memory_db)
    pred = _insert_test_prediction(in_memory_db)   # ohne extra

    row = in_memory_db.execute(
        "SELECT * FROM predictions WHERE id=?", (pred,)).fetchone()

    assert row["pe_ratio"] is None
    assert row["relative_strength"] is None


def test_init_schema_migrates_an_old_predictions_table(in_memory_db):
    """Spec E7: additive Migration, Daten bleiben."""
    in_memory_db.execute(
        "CREATE TABLE predictions (id INTEGER PRIMARY KEY, date TEXT, "
        "ticker TEXT, direction TEXT, status TEXT)")
    in_memory_db.execute(
        "INSERT INTO predictions (date,ticker,direction,status) "
        "VALUES ('2026-01-01','AAPL','long','open')")
    in_memory_db.commit()

    init_schema(in_memory_db)

    cols = {r["name"] for r in in_memory_db.execute("PRAGMA table_info(predictions)")}
    assert {"pe_ratio", "relative_strength", "analyst_consensus_period"} <= cols
    assert in_memory_db.execute(
        "SELECT COUNT(*) FROM predictions").fetchone()[0] == 1
```

Prüfe die Signatur von `_insert_test_prediction` in `tests/unit/test_db.py`. Nimmt sie noch kein `extra`-Dict, erweitere sie:
```python
def _insert_test_prediction(conn, extra: dict | None = None):
    pred = { ...bestehende Pflichtfelder... }
    if extra:
        pred.update(extra)
    return save_prediction(conn, pred)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_db.py -k "froze or frozen or migrates_an_old" -q`
Expected: FAIL — `no such column: pe_ratio`

- [ ] **Step 3: Schema + Migration + Insert**

Im `CREATE TABLE IF NOT EXISTS predictions`-Block ergänzen:
```sql
    -- Spec E2/E3/E4: was das System zum Zeitpunkt der Entscheidung wusste.
    -- fundamentals_cache haelt nur EINE Zeile je Ticker (INSERT OR REPLACE),
    -- hat also keine Historie -- ohne diese Spalten ist der PE-Wert einer
    -- Prediction vom Vormonat nicht mehr rekonstruierbar.
    pe_ratio REAL, forward_pe REAL, market_cap_b REAL, debt_equity REAL,
    analyst_consensus TEXT, analyst_consensus_period TEXT,
    relative_strength REAL,
```

In `init_schema()` beim `predictions`-Migrationsblock:
```python
    _p_cols = {r["name"] for r in conn.execute("PRAGMA table_info(predictions)")}
    for _col, _type in (
        ("pe_ratio", "REAL"), ("forward_pe", "REAL"),
        ("market_cap_b", "REAL"), ("debt_equity", "REAL"),
        ("analyst_consensus", "TEXT"), ("analyst_consensus_period", "TEXT"),
        ("relative_strength", "REAL"),
    ):
        if _col not in _p_cols:
            conn.execute(f"ALTER TABLE predictions ADD COLUMN {_col} {_type}")
```

In `_insert_prediction()` die feste Spaltenliste um die sieben Namen erweitern und die Werte per `pred.get(...)` ziehen (liefert `None`, wenn der Aufrufer sie weglässt).

- [ ] **Step 4: Run tests**

Run: `pytest tests/ --ignore=tests/live -q`
Expected: alle grün

- [ ] **Step 5: Commit**

```bash
git add src/db.py tests/unit/test_db.py
git commit -m "$(cat <<'EOF'
feat: predictions frieren Fundamental-Rohwerte und relative Staerke ein

fundamentals_cache haelt nur eine Zeile je Ticker und ueberschreibt sie alle
7 Tage -- der PE-Wert einer Prediction vom Vormonat war nicht mehr
rekonstruierbar. Additive Migration, kein Backfill (Spec E6).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Werte in der Pipeline befüllen

**Files:**
- Modify: `main.py` — `run_pipeline()`, Phase 4 (Ranking → `save_prediction`)
- Modify: `src/ranking.py` — dort, wo die Prediction-Dicts gebaut werden
- Test: `tests/unit/test_ranking.py`

**Interfaces:**
- Consumes: `td`-Felder aus Task 3, `signal_checks.compute_relative_strength(conn, ticker, date)`
- Produces: gefüllte Spalten aus Task 4 in echten Läufen

- [ ] **Step 1: Herausfinden, wo das Prediction-Dict entsteht**

Run: `grep -n "save_prediction\|def _to_prediction\|\"entry_price\"" src/ranking.py | head`
Das Dict, das `entry_price`/`tp_price` setzt, ist die Stelle. Es hat Zugriff auf die Analyse; die `td`-Werte kommen über `signal_context` oder ein Snapshot-Dict — prüfe, was dort verfügbar ist, bevor du schreibst.

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_ranking.py

def test_prediction_rows_carry_the_frozen_fundamentals(in_memory_db):
    """Spec E2/E4: die Rohwerte und die relative Staerke muessen aus dem
    pre_market-Lauf in die Zeile wandern, nicht nur um 16:10."""
    # Baue den minimalen rank_and_select()-Aufruf nach dem Muster der
    # bestehenden Tests in dieser Datei; der Snapshot traegt:
    #   pe_ratio=25.0, analyst_consensus="buy",
    #   analyst_consensus_period="2026-08-01"
    # Erwartung: die persistierte Zeile traegt dieselben Werte und ein
    # relative_strength, das nicht None ist.
    ...
```

⚠️ Schreibe diesen Test nach dem konkreten Muster der bestehenden `test_ranking.py`-Tests (Fixtures, `rank_and_select`-Signatur), nicht nach dieser Skizze.

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/unit/test_ranking.py -k frozen_fundamentals -q`
Expected: FAIL

- [ ] **Step 4: Werte durchreichen**

Im Prediction-Dict ergänzen:
```python
        # Spec E2: die Rohwerte gehoeren zur Entscheidung, nicht zum Ticker.
        "pe_ratio":                 snap.get("pe_ratio"),
        "forward_pe":               snap.get("forward_pe"),
        "market_cap_b":             snap.get("market_cap_b"),
        "debt_equity":              snap.get("debt_equity"),
        "analyst_consensus":        snap.get("analyst_consensus"),
        "analyst_consensus_period": snap.get("analyst_consensus_period"),
        # Spec E4: in BEIDEN Laeufen, sonst korreliert das Merkmal mit dem
        # run_type und ist fuer 3D schlimmer als keins. Reine DB-Rechnung.
        "relative_strength": signal_checks.compute_relative_strength(
            conn, ticker, date),
```

Falls `signal_checks` in `ranking.py` noch nicht importiert ist, ergänze `from src import signal_checks`. Achte auf Zirkelimporte — importiere notfalls lokal in der Funktion.

- [ ] **Step 5: Run tests**

Run: `pytest tests/ --ignore=tests/live -q`
Expected: alle grün

- [ ] **Step 6: Commit**

```bash
git add src/ranking.py main.py tests/unit/test_ranking.py
git commit -m "$(cat <<'EOF'
feat: Rohwerte und relative Staerke in jede Prediction schreiben

relative_strength entstand bisher nur um 16:10 und wurde weggeworfen -- als
Merkmal waere es systematisch mit dem run_type korreliert gewesen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Doku

**Files:**
- Modify: `CLAUDE.md` (Kopf + Designentscheidungen)
- Modify: `docs/superpowers/specs/PROJECT_STATUS.md` (neuer Abschnitt C.20)
- Modify: `docs/ARCHITECTURE.md` (Retention-Absatz, `predictions`-Beschreibung)

- [ ] **Step 1: PROJECT_STATUS C.20 schreiben**

Abschnitt vor `## Sprint 3D — Learning Modul` einfügen mit: Anlass, den drei
Verlustarten (§ 2 der Spec), den Entscheidungen E1–E7 in Kurzform, der
Grössenrechnung für 730 Tage und dem Hinweis, dass bei 500 Tickern neu zu
prüfen ist.

- [ ] **Step 2: CLAUDE.md ergänzen**

Kopfeintrag plus einen Designentscheidungs-Punkt:
```markdown
- ⚠️ **Was eine Prediction wusste, steht IN der Prediction — nicht im Cache.**
  `fundamentals_cache` hält nur eine Zeile je Ticker (`INSERT OR REPLACE`,
  7-Tage-TTL) und hat keine Historie. Fundamental-Rohwerte, Analysten-Konsens
  **samt Periode** und `relative_strength` werden deshalb seit 2026-08-20 in
  `predictions` eingefroren. Wer ein neues Merkmal einführt, das in die
  Entscheidung einfliesst, friert es dort mit ein — sonst ist es für Sprint 3D
  nicht vorhanden, und zwar rückwirkend unheilbar.
- ⚠️ **`config.LEARNING_RETENTION_DAYS` gilt für vier Tabellen gemeinsam.**
  Wer eine davon auf eine eigene Frist setzt, wiederholt den
  `news_summaries`-Fehler (30 Tage, während das Label dauerhaft blieb).
```

- [ ] **Step 3: ARCHITECTURE.md nachziehen**

Retention-Absatz auf die Konstante umstellen, `predictions` als „friert den
Wissensstand ein" beschreiben.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/
git commit -m "$(cat <<'EOF'
docs: Trainingsdaten-Fundament (C.20)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Verifikation zum Schluss

- [ ] `pytest tests/ --ignore=tests/live -q` → alle grün
- [ ] Migration gegen eine **Kopie** der echten DB:
```bash
cp data/tracking.db "$SCRATCH/migration.db"
venv/bin/python -c "
from src import db
c = db.connect('$SCRATCH/migration.db'); db.init_schema(c)
cols = {r['name'] for r in c.execute('PRAGMA table_info(predictions)')}
assert {'pe_ratio','relative_strength','analyst_consensus_period'} <= cols
print('Migration ok, Predictions:', c.execute('SELECT COUNT(*) FROM predictions').fetchone()[0])
"
```
  Erwartung: Spalten da, **14 Predictions unverändert**.
- [ ] `graphify update .`
- [ ] Wegwerf-Kopie löschen
