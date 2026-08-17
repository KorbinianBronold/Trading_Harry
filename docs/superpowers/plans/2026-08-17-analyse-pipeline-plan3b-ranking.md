# Plan 3b (Ranking) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `probability_pct`-sorted ranking with the two-signal design from Spec § 5:
qualification (`tech_direction == direction`), `rank_score = analysis_strength × tech_strength`
as the sort key, a separate `candidate_class='divergence'` list for signals where only one
side has a direction, and a mail section for it. Retire `score_total()`/`DIMENSION_WEIGHTS`.

**Architecture:** A new pure function `analysis_strength()` mirrors the existing
`technical_signal.compute()` — same shape (dict in, count out), same "reads from a snapshot,
touches no DB" contract. `main.py` gains a `_signal_context()` builder that bundles, per
ticker, everything Phase 4 needs but that neither the Claude response nor `td` carries alone
(the sidecar's tech signal, three raw indicators for the C.1 fix, the Phase-2 scan value).
`ranking.py`'s `rank_and_persist()` takes this bundle as a new `signal_context` parameter and
classifies each surviving analysis into `core` / `divergence` / `conflict` before sorting and
persisting. Two `db.py` read functions and one `main.py` aggregate gain a `candidate_class`
split so 3D's outcome comparisons never blend the two groups silently.

**Tech Stack:** Python 3, sqlite3, pytest (+ pytest-mock's `mocker` fixture). No new
dependencies.

**Spec:** `docs/superpowers/specs/2026-08-11-analyse-pipeline-umbau-design.md` — § 5
(Signale, Qualifikation, Ranking), § 7.2 (predictions-Spalten), § 20.1 (Plan-3-Aufteilung),
§ 20.5 (Plan-3b-Entscheidungen 1–4, getroffen am Verifikationslauf vom 2026-08-17).
Executors should read § 5 and § 20.5 in full before Task 7 — they carry the reasoning behind
every threshold and edge case below.

## Global Constraints

- Tests outside `tests/live/` must never touch the network — the autouse fixture in
  `tests/conftest.py` already blocks it at the transport layer; don't work around it.
- Coverage floor stays ≥ 80 % (`pytest tests/ --cov=src --cov=main --cov-fail-under=80`).
- Never overwrite an existing prompt file (Regel 10 aus CLAUDE.md) — not applicable in this
  plan; the polarity fix Spec § 5.2 warns about is **already present** in both
  `deep_analysis_v2.txt` and `commodities_crypto_v2.txt` (verified 2026-08-17, both carry an
  identical "SCORE POLARITY" block). No prompt file changes in this plan.
- `td` (the Phase-1 snapshot dict) must never gain a new key — it is `json.dumps`'d into three
  live Claude prompts unchanged (R1 / Spec 18.1e). All new per-ticker context in this plan
  travels in `signal_context`, a sibling dict, never inside `td`.
- `rank_score` is `NULL`, never `0`, whenever `tech_strength` is `0` or unknown (Spec § 5.4,
  § 20.5 #3) — a `0` there would silently outrank a real "no confirmation yet".
- The Zwei-Signal-Qualifikationshürde (§ 5.3) applies to **stocks only**. Commodities/crypto
  keep "always kept, regardless of score" — they get a `rank_score` for display, but a
  mismatched or missing technical signal never drops them (§ 20.5 #2).
- `analysis_strength` (0–8, the count from § 5.2) and `news_strength` (0–3, the Phase-2 scan
  value) are two different numbers and get two different `predictions` columns (§ 20.5 #1).
  Never conflate them.

---

### Task 1: `analysis_strength()` — the second signal

**Files:**
- Create: `src/analysis_signal.py`
- Test: `tests/unit/test_analysis_signal.py`

**Interfaces:**
- Consumes: nothing from other tasks — reads `config.MOMENTUM_LONG_MIN` (6.0) and
  `config.MOMENTUM_SHORT_MAX` (4.0), both already in `config.py`.
- Produces: `analysis_strength(analysis: dict) -> int`, used by Task 7/8 in `src/ranking.py`.

This is the § 5.2 signal: how many of the eight score dimensions carry belief-worthy,
direction-confirming evidence. It mirrors `src/technical_signal.py` in spirit — a pure
function over one dict, no I/O, table-driven tests.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests fuer src/analysis_signal.py -- Spec 5.2, reine Zaehlfunktion."""
import pytest

from src.analysis_signal import analysis_strength


def _dim(value, evidence=("a concrete line", "a second line"), quality="ok"):
    return {"value": value, "evidence": list(evidence), "evidence_quality": quality}


def _analysis(direction="long", **dim_overrides):
    """Acht Dimensionen, alle standardmaessig auf einem Wert, der fuer die
    gegebene Richtung zaehlt (long: 7.0 >= MOMENTUM_LONG_MIN=6.0)."""
    base_value = 7.0 if direction == "long" else 3.0
    dims = ["market_environment", "company_quality", "valuation", "momentum",
            "risk", "sector_trend", "catalyst", "policy_risk"]
    scores = {d: _dim(base_value) for d in dims}
    scores.update(dim_overrides)
    return {"direction": direction, "scores": scores}


def test_all_eight_dimensions_count_when_all_confirm():
    assert analysis_strength(_analysis("long")) == 8


def test_direction_none_scores_zero_regardless_of_dimensions():
    a = _analysis("long")
    a["direction"] = "none"
    assert analysis_strength(a) == 0


def test_unknown_direction_scores_zero():
    a = _analysis("long")
    a["direction"] = "sideways"
    assert analysis_strength(a) == 0


def test_thin_evidence_quality_does_not_count_even_with_two_lines():
    a = _analysis("long", momentum=_dim(9.0, quality="thin"))
    assert analysis_strength(a) == 7


def test_fewer_than_two_evidence_lines_does_not_count():
    a = _analysis("long", momentum=_dim(9.0, evidence=("only one line",)))
    assert analysis_strength(a) == 7


def test_value_on_wrong_side_of_threshold_does_not_count_for_long():
    # momentum_long_min = 6.0 -- 5.9 is just under it
    a = _analysis("long", momentum=_dim(5.9))
    assert analysis_strength(a) == 7


def test_value_exactly_at_threshold_counts_for_long():
    a = _analysis("long", momentum=_dim(6.0))
    assert analysis_strength(a) == 8


def test_short_uses_the_short_threshold():
    # momentum_short_max = 4.0 -- base_value fuer short ist 3.0, zaehlt
    assert analysis_strength(_analysis("short")) == 8


def test_short_value_above_threshold_does_not_count():
    a = _analysis("short", momentum=_dim(4.1))
    assert analysis_strength(a) == 7


def test_missing_value_does_not_count():
    a = _analysis("long")
    a["scores"]["risk"] = {"evidence": ["x", "y"], "evidence_quality": "ok"}
    assert analysis_strength(a) == 7


def test_missing_dimension_does_not_count():
    a = _analysis("long")
    del a["scores"]["catalyst"]
    assert analysis_strength(a) == 7


def test_missing_scores_dict_scores_zero():
    assert analysis_strength({"direction": "long"}) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_analysis_signal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.analysis_signal'`

- [ ] **Step 3: Write the implementation**

```python
"""Analysis-Strength-Signal (Spec 5.2): das zweite der zwei Ranking-Signale.

Zaehlt, wie viele der acht Score-Dimensionen belegte, richtungsuebereinstimmende
Evidenz tragen -- das Gegenstueck zum deterministischen Technik-Signal aus
technical_signal.py. Reine Funktion ueber das Analyse-Dict aus Phase 3, kein
Netz, keine Datenbank.

Heisst bewusst NICHT news_strength: der Name ist seit Plan 2 als Scan-Wert aus
Phase 2 (0-3) vergeben (broad_scan.py, cutoff_log). Zwei Skalen unter einem
Namen wuerden eine Spalte erzeugen, deren Bedeutung von der Tabelle abhaengt --
und die 3D-Frage 'sagt der billige Scan die teure Analyse vorher?' unformulierbar
machen (Spec 20.5 #1)."""
import config

DIMENSIONS = (
    "market_environment", "company_quality", "valuation", "momentum",
    "risk", "sector_trend", "catalyst", "policy_risk",
)


def analysis_strength(analysis: dict) -> int:
    """Spec 5.2: zaehlt Dimensionen mit evidence_quality != 'thin', >= 2 Belegen
    und einem Wert auf der Trade-Richtung-Seite der bestehenden Momentum-
    Schwellen (config.MOMENTUM_LONG_MIN / MOMENTUM_SHORT_MAX -- keine neuen
    Konstanten). direction='none' oder eine unbekannte Richtung liefert 0: ein
    Ranking ohne Richtung ist sinnlos."""
    direction = analysis.get("direction")
    if direction not in ("long", "short"):
        return 0
    scores = analysis.get("scores", {})
    n = 0
    for dim in DIMENSIONS:
        sd = scores.get(dim)
        if not sd:
            continue
        if sd.get("evidence_quality") == "thin":
            continue
        if len(sd.get("evidence") or []) < 2:
            continue
        value = sd.get("value")
        if value is None:
            continue
        if direction == "long" and value >= config.MOMENTUM_LONG_MIN:
            n += 1
        elif direction == "short" and value <= config.MOMENTUM_SHORT_MAX:
            n += 1
    return n
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_analysis_signal.py -v`
Expected: PASS, all 11 tests

- [ ] **Step 5: Commit**

```bash
git add src/analysis_signal.py tests/unit/test_analysis_signal.py
git commit -m "feat: analysis_strength() -- das zweite Ranking-Signal (Spec 5.2)"
```

---

### Task 2: Two new config constants

**Files:**
- Modify: `config.py:283` (near `TECH_MIN_FOR_DEEP`)

**Interfaces:**
- Produces: `config.EARNINGS_WARNING_DAYS` (used by Task 4), `config.DIVERGENCE_TOP_N`
  (used by Task 8).

- [ ] **Step 1: Add the constants**

In `config.py`, immediately after line 283 (`TECH_MIN_FOR_DEEP = 2`):

```python
TECH_MIN_FOR_DEEP = 2

# Sprint 3C / Analyse-Pipeline-Umbau, Plan 3b (Spec 5.3): ein Earnings-Termin
# in <= EARNINGS_WARNING_DAYS ist die einzige fundamentale Tatsache mit
# unmittelbarer Intraday-Wirkung -- er kann den Kurs springen lassen und
# entwertet damit das analytisch hergeleitete TP/SL. Fuer Rohstoffe/Krypto ist
# earnings_in_days immer None (Spec 4.7), der Check dort trivial erfuellt.
EARNINGS_WARNING_DAYS = 2

# Spec 5.5: Deckel fuer Divergenz-Kandidaten je Richtung, sortiert nach
# rank_score. UNBESTAETIGTER STARTWERT, kein Messergebnis -- der
# Verifikationslauf vom 2026-08-17 enthielt null Divergenzfaelle, der Deckel
# hat also noch nie gebunden (Spec 20.5). Dieselbe Klasse Zahl wie
# BATCH_SIZE_DEEP vor seiner eigenen Kalibrierung.
DIVERGENCE_TOP_N = 5
```

- [ ] **Step 2: Verify the module still imports cleanly**

Run: `python3 -c "import config; print(config.EARNINGS_WARNING_DAYS, config.DIVERGENCE_TOP_N)"`
Expected: `2 5`

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "feat: config-Konstanten fuer Plan 3b (EARNINGS_WARNING_DAYS, DIVERGENCE_TOP_N)"
```

---

### Task 3: `predictions` schema — 8 new columns

**Files:**
- Modify: `src/db.py:82-102` (CREATE TABLE predictions)
- Modify: `src/db.py:395-405` (`_apply_migrations()`, existing column-add loop)
- Modify: `src/db.py:674-691` (`_insert_prediction()` cols list)
- Test: `tests/unit/test_db.py`

**Interfaces:**
- Produces: `predictions` rows now accept and return `candidate_class`, `tech_direction`,
  `tech_agreement`, `tech_adx_band`, `tech_strength`, `analysis_strength`, `rank_score`,
  `news_strength`. Task 8 will populate all eight when building the row dict.

Eight columns from Spec § 7.2, § 20.5 #1/#3: the four tech-signal fields "as decided", the
two ranking numbers (`analysis_strength` 0–8, `rank_score` 1–32 or `NULL`), `candidate_class`
(`'core'` default), and `news_strength` (the Phase-2 scan value, kept separate from
`analysis_strength` per § 20.5 #1).

- [ ] **Step 1: Write the failing migration test**

Add to `tests/unit/test_db.py` (append near other migration tests — search the file for
`_apply_migrations` or `"ALTER TABLE predictions"` to place it next to its siblings):

```python
def test_predictions_migration_adds_plan3b_columns(in_memory_db):
    """Eine Bestands-DB ohne die Plan-3b-Spalten bekommt sie beim naechsten
    init_schema()-Lauf nachgezogen, candidate_class faellt auf 'core' zurueck."""
    conn = in_memory_db
    db.init_schema(conn)
    conn.execute("ALTER TABLE predictions DROP COLUMN candidate_class") \
        if False else None  # SQLite < 3.35 kennt kein DROP COLUMN -- stattdessen:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(predictions)")}
    for col in ("candidate_class", "tech_direction", "tech_agreement",
                "tech_adx_band", "tech_strength", "analysis_strength",
                "rank_score", "news_strength"):
        assert col in cols, f"{col} fehlt in predictions"

    # init_schema() auf derselben Connection ein zweites Mal ist idempotent
    db.init_schema(conn)
    cols_again = {r["name"] for r in conn.execute("PRAGMA table_info(predictions)")}
    assert cols_again == cols


def test_insert_prediction_defaults_candidate_class_to_core(in_memory_db):
    """_insert_prediction() liefert 'core' zurueck, wenn der Aufrufer den
    Schluessel weglaesst -- derselbe Rueckfall-Mechanismus wie 'learnable'."""
    conn = in_memory_db
    db.init_schema(conn)
    pred = {
        "date": "2026-08-17", "run_type": "pre_market", "ticker": "AAPL",
        "direction": "long", "entry_price": 100.0, "tp_price": 105.0,
        "sl_price": 98.0, "rr_ratio": 2.5,
    }
    new_id = db.save_prediction(conn, pred)
    row = conn.execute("SELECT * FROM predictions WHERE id=?", (new_id,)).fetchone()
    assert row["candidate_class"] == "core"
    assert row["rank_score"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_db.py -k "plan3b_columns or defaults_candidate_class" -v`
Expected: FAIL — `KeyError`/`AssertionError`, columns don't exist yet

- [ ] **Step 3: Extend the CREATE TABLE block**

In `src/db.py`, the `predictions` table definition (lines 82–102) — add the eight columns
right before the closing paren, keeping `created_at` last:

```python
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL, run_type TEXT NOT NULL, asset_class TEXT,
    ticker TEXT NOT NULL, direction TEXT NOT NULL,
    entry_price REAL, tp_price REAL, tp_pct REAL,
    sl_price REAL, sl_pct REAL, rr_ratio REAL,
    total_score REAL, probability_pct INTEGER, confidence TEXT,
    score_market_env REAL, score_company REAL, score_valuation REAL,
    score_momentum REAL, score_risk REAL, score_sector REAL,
    score_catalyst REAL, score_policy REAL,
    atr_pct REAL, rsi_at_entry REAL, volume_ratio REAL,
    market_regime TEXT, vix_at_prediction REAL, sector TEXT,
    trend_boost TEXT, earnings_warning BOOLEAN, summary TEXT,
    learnable BOOLEAN DEFAULT 1,
    status TEXT DEFAULT 'open',
    closed_date TEXT, closed_price REAL,
    hold_days_recommended INTEGER, intraday_range_pct REAL,
    superseded_by INTEGER REFERENCES predictions(id),
    revision_verdict TEXT,
    candidate_class TEXT DEFAULT 'core',
    tech_direction TEXT, tech_agreement INTEGER,
    tech_adx_band TEXT, tech_strength INTEGER,
    analysis_strength INTEGER, rank_score INTEGER,
    news_strength INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

(Fresh DBs get the columns straight from this block; the migration below handles DBs that
already ran `init_schema()` before this task.)

- [ ] **Step 4: Extend `_apply_migrations()`**

Find the existing loop at `src/db.py:395-405` (adds `price_premarket`/`price_open`/
`price_1610`/`is_premarket`) and extend its tuple:

```python
    pred_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(predictions)"
    ).fetchall()}
    for col, coltype in (
        ("price_premarket", "REAL"),
        ("price_open",      "REAL"),
        ("price_1610",      "REAL"),
        ("is_premarket",    "INTEGER"),
        # Sprint 3C / Analyse-Pipeline-Umbau, Plan 3b (Spec 7.2, 20.5):
        ("candidate_class",   "TEXT DEFAULT 'core'"),
        ("tech_direction",    "TEXT"),
        ("tech_agreement",    "INTEGER"),
        ("tech_adx_band",     "TEXT"),
        ("tech_strength",     "INTEGER"),
        ("analysis_strength", "INTEGER"),
        ("rank_score",        "INTEGER"),
        ("news_strength",     "INTEGER"),
    ):
        if col not in pred_cols:
            conn.execute(f"ALTER TABLE predictions ADD COLUMN {col} {coltype}")
    conn.commit()
```

- [ ] **Step 5: Extend `_insert_prediction()`**

In `src/db.py`, update the default-merge and the `cols` list (lines ~673–691):

```python
    pred = {"learnable": True, "candidate_class": "core", **pred}
    cols = [
        "date", "run_type", "asset_class", "ticker", "direction",
        "entry_price", "tp_price", "tp_pct", "sl_price", "sl_pct", "rr_ratio",
        "total_score", "probability_pct", "confidence",
        "score_market_env", "score_company", "score_valuation",
        "score_momentum", "score_risk", "score_sector",
        "score_catalyst", "score_policy",
        "atr_pct", "rsi_at_entry", "volume_ratio",
        "market_regime", "vix_at_prediction", "sector",
        "trend_boost", "earnings_warning", "summary", "learnable",
        "hold_days_recommended", "intraday_range_pct",
        "sector_etf_momentum", "sector_db_momentum",
        "price_premarket", "price_open", "price_1610", "is_premarket",
        # Sprint 3C / Analyse-Pipeline-Umbau, Plan 3b:
        "candidate_class", "tech_direction", "tech_agreement",
        "tech_adx_band", "tech_strength", "analysis_strength",
        "rank_score", "news_strength",
    ]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_db.py -k "plan3b_columns or defaults_candidate_class" -v`
Expected: PASS

- [ ] **Step 7: Run the full DB test suite to check nothing else broke**

Run: `pytest tests/unit/test_db.py -v`
Expected: PASS, all tests

- [ ] **Step 8: Commit**

```bash
git add src/db.py tests/unit/test_db.py
git commit -m "feat: predictions-Schema um 8 Plan-3b-Spalten erweitert"
```

---

### Task 4: `signal_checks.check_earnings()`

**Files:**
- Modify: `src/signal_checks.py` (add function, near `check_vix`/`check_sector_momentum`)
- Test: `tests/unit/test_signal_checks.py`

**Interfaces:**
- Consumes: `config.EARNINGS_WARNING_DAYS` (Task 2), `CheckResult` (already in
  `src/signal_checks.py`).
- Produces: `check_earnings(direction: str, earnings_in_days: int | None, *, enforce: bool)
  -> CheckResult | None`, wired into `ranking.py::_run_checks()` in Task 8.

Follows the exact shape of `check_vix()`/`check_sector_momentum()`: a plain function, no I/O,
`None` when the check doesn't fire, a `CheckResult` when it does, and `enforce` decides
whether `enforced=True` (blocks) or `False` (mail warning only) — same E4 pattern used
everywhere else in this module.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_signal_checks.py`:

```python
from src.signal_checks import check_earnings


def test_check_earnings_none_when_no_earnings_date():
    """Rohstoffe/Krypto: earnings_in_days ist immer None (Spec 4.7) -- trivial erfuellt."""
    assert check_earnings("long", None, enforce=True) is None


def test_check_earnings_none_when_far_out():
    assert check_earnings("long", 5, enforce=True) is None


def test_check_earnings_fires_at_the_threshold():
    result = check_earnings("long", 2, enforce=True)
    assert result is not None
    assert result.rule == "earnings_imminent"
    assert result.enforced is True


def test_check_earnings_fires_when_imminent():
    result = check_earnings("short", 0, enforce=True)
    assert result is not None
    assert result.enforced is True


def test_check_earnings_respects_enforce_false():
    result = check_earnings("long", 1, enforce=False)
    assert result is not None
    assert result.enforced is False


def test_check_earnings_just_outside_threshold_does_not_fire():
    assert check_earnings("long", 3, enforce=True) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_signal_checks.py -k check_earnings -v`
Expected: FAIL with `ImportError: cannot import name 'check_earnings'`

- [ ] **Step 3: Implement `check_earnings()`**

In `src/signal_checks.py`, add after `check_vix()` (before `def _supports`):

```python
def check_earnings(
    direction: str, earnings_in_days: int | None, *, enforce: bool,
) -> CheckResult | None:
    """Spec 5.3: ein Earnings-Termin in <= EARNINGS_WARNING_DAYS ist die
    einzige fundamentale Tatsache mit unmittelbarer Intraday-Wirkung -- er
    kann den Kurs springen lassen und entwertet damit das analytisch
    hergeleitete TP/SL. Ersetzt das reine Modell-Attribut 'earnings_warning'
    (das blockierte nichts) durch einen echten Check.

    earnings_in_days ist fuer Rohstoffe/Krypto immer None -- der Check ist
    dort trivial erfuellt, kein Sonderfall im Code noetig."""
    if earnings_in_days is None:
        return None
    if earnings_in_days > config.EARNINGS_WARNING_DAYS:
        return None
    return CheckResult(
        rule="earnings_imminent",
        detail=f"Earnings in {earnings_in_days} Tag(en) "
               f"(<= {config.EARNINGS_WARNING_DAYS}) — TP/SL-Basis unsicher",
        enforced=enforce,
    )
```

`direction` is accepted but unused today — kept in the signature to match the other
`check_*` functions' shape and because a directional earnings rule (e.g. only warn on
longs into a beat-heavy sector) is a plausible 3D refinement, not because it does anything
yet.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_signal_checks.py -k check_earnings -v`
Expected: PASS, all 6 tests

- [ ] **Step 5: Commit**

```bash
git add src/signal_checks.py tests/unit/test_signal_checks.py
git commit -m "feat: check_earnings() -- earnings_in_days wird ein echter Check (Spec 5.3)"
```

---

### Task 5: `candidate_class` in `load_recent_outcomes()` + `load_revision_verdict_stats()`

**Files:**
- Modify: `src/db.py:1247-1260` (`load_recent_outcomes`)
- Modify: `src/db.py:1442-1467` (`load_revision_verdict_stats`)
- Test: `tests/unit/test_db.py`

**Interfaces:**
- Consumes: the `candidate_class` column from Task 3.
- Produces: rows from both functions now carry a `candidate_class` field. Task 10 relies on
  `load_recent_outcomes()` carrying it.

Two of the three functions named in Spec § 5.6 / § 20.5 #4. The third
(`load_revision_effectiveness()`) is a bigger rework and gets its own task next.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_db.py`:

```python
def _seed_prediction_with_outcome(
    conn, ticker, direction, candidate_class, pl_eur, evaluated_date="2026-08-17",
    revision_verdict=None, run_type="pre_market",
):
    """Legt eine Prediction plus zugehoeriges Outcome an, fuer Aggregat-Tests."""
    pred_id = db.save_prediction(conn, {
        "date": "2026-08-16", "run_type": run_type, "ticker": ticker,
        "direction": direction, "entry_price": 100.0, "tp_price": 105.0,
        "sl_price": 98.0, "rr_ratio": 2.5, "candidate_class": candidate_class,
        "revision_verdict": revision_verdict,
    })
    conn.execute(
        """INSERT INTO outcomes
           (prediction_id, direction, evaluated_date, correct_direction_eod, profit_loss_eur)
           VALUES (?, ?, ?, ?, ?)""",
        (pred_id, direction, evaluated_date, pl_eur > 0, pl_eur),
    )
    conn.commit()
    return pred_id


def test_load_recent_outcomes_carries_candidate_class(in_memory_db):
    conn = in_memory_db
    db.init_schema(conn)
    _seed_prediction_with_outcome(conn, "AAPL", "long", "core", 10.0)
    _seed_prediction_with_outcome(conn, "GC=F", "long", "divergence", -5.0)
    rows = db.load_recent_outcomes(conn, "2026-08-01")
    classes = {r["ticker"]: r["candidate_class"] for r in rows}
    assert classes == {"AAPL": "core", "GC=F": "divergence"}


def test_load_revision_verdict_stats_groups_by_candidate_class(in_memory_db):
    """Eine core- und eine divergence-Zeile mit demselben revision_verdict duerfen
    sich nicht zu einer Gruppe vermischen (Spec 5.6)."""
    conn = in_memory_db
    db.init_schema(conn)
    _seed_prediction_with_outcome(
        conn, "AAPL", "long", "core", 10.0, revision_verdict="bestaetigt")
    _seed_prediction_with_outcome(
        conn, "GC=F", "long", "divergence", -20.0, revision_verdict="bestaetigt")
    rows = db.load_revision_verdict_stats(conn, "2026-08-01")
    by_class = {(r["revision_verdict"], r["candidate_class"]): r for r in rows}
    assert by_class[("bestaetigt", "core")]["n"] == 1
    assert by_class[("bestaetigt", "divergence")]["n"] == 1
    # Kein vermischter avg_pl ueber beide Klassen:
    assert by_class[("bestaetigt", "core")]["avg_pl"] != \
           by_class[("bestaetigt", "divergence")]["avg_pl"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_db.py -k "carries_candidate_class or groups_by_candidate_class" -v`
Expected: FAIL — `KeyError: 'candidate_class'`

- [ ] **Step 3: Extend `load_recent_outcomes()`**

In `src/db.py` (~line 1247):

```python
def load_recent_outcomes(
    conn: sqlite3.Connection, since_date: str,
) -> list[sqlite3.Row]:
    """Returns outcomes evaluated on/after since_date, joined with their
    prediction's ticker/direction/score/entry price/candidate_class, newest
    first. candidate_class ist dabei (Spec 5.6): core und divergence duerfen
    sich in keiner Auswertung stromabwaerts vermischen."""
    return conn.execute(
        """SELECT o.*, p.ticker, p.direction AS pred_direction,
                  p.total_score, p.entry_price, p.candidate_class
           FROM outcomes o
           JOIN predictions p ON p.id = o.prediction_id
           WHERE o.evaluated_date >= ?
           ORDER BY o.evaluated_date DESC""",
        (since_date,),
    ).fetchall()
```

- [ ] **Step 4: Extend `load_revision_verdict_stats()`**

In `src/db.py` (~line 1442):

```python
def load_revision_verdict_stats(
    conn: sqlite3.Connection, since_date: str,
) -> list[sqlite3.Row]:
    """B.9/Block 2: wie oft wurde bestaetigt / geschwaecht / gedreht / verworfen,
    und wie liefen die Gruppen danach -- getrennt nach candidate_class (Spec
    5.6, 20.5 #4), damit eine core- und eine divergence-Zeile mit demselben
    Verdikt nicht in einer gemeinsamen avg_pl verschwinden.

    [... bestehender Docstring-Text zum COALESCE(superseded_by, id)-Join und
    zum bewusst NULL bleibenden avg_pl unveraendert ...]"""
    return conn.execute(
        """SELECT p.revision_verdict AS revision_verdict,
                  p.candidate_class AS candidate_class,
                  COUNT(*) AS n,
                  COUNT(o.id) AS n_evaluated,
                  ROUND(AVG(o.profit_loss_eur), 2) AS avg_pl
           FROM predictions p
           LEFT JOIN outcomes o
                  ON o.prediction_id = COALESCE(p.superseded_by, p.id)
           WHERE p.date >= ? AND p.revision_verdict IS NOT NULL
           GROUP BY p.revision_verdict, p.candidate_class
           ORDER BY n DESC""",
        (since_date,),
    ).fetchall()
```

(Keep the existing docstring prose about the `COALESCE` join and the `NULL`-vs-`0` avg_pl
reasoning — only the `GROUP BY` and the added column change.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_db.py -k "carries_candidate_class or groups_by_candidate_class or revision_verdict" -v`
Expected: PASS

- [ ] **Step 6: Run the full DB suite**

Run: `pytest tests/unit/test_db.py -v`
Expected: PASS, all tests (watch for other callers of `load_revision_verdict_stats()` in
`email_sender.py`'s weekly renderer — they iterate rows generically and tolerate an extra
column, but confirm with `grep -rn "load_revision_verdict_stats\|revision_verdict\b" src/email_sender.py`)

- [ ] **Step 7: Commit**

```bash
git add src/db.py tests/unit/test_db.py
git commit -m "feat: candidate_class in load_recent_outcomes/load_revision_verdict_stats (Spec 5.6)"
```

---

### Task 6: `candidate_class` split in `load_revision_effectiveness()`

**Files:**
- Modify: `src/db.py:1399-1437` (`load_revision_effectiveness`)
- Test: `tests/unit/test_db.py`

**Interfaces:**
- Consumes: `candidate_class` column (Task 3).
- Produces: `load_revision_effectiveness()` now returns
  `{"core": {...}, "divergence": {...}, "since": ...}` instead of the flat
  `{"confirmed": ..., "rejected": ..., "unchecked": ..., "since": ...}`. **Breaking change** —
  Task 11 updates `email_sender.py`'s weekly renderer to match.

The third of the three § 5.6 functions, and the one whose return shape actually needs to
change: the existing `confirmed`/`rejected`/`unchecked` breakdown must exist **per class**,
not once — otherwise a core signal's rejection rate and a divergence signal's rejection rate
average into one number.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_db.py`:

```python
def test_load_revision_effectiveness_splits_by_candidate_class(in_memory_db):
    conn = in_memory_db
    db.init_schema(conn)
    # confirmed core: ein trade_proposals-Lauf, candidate_class core
    db.save_prediction(conn, {
        "date": "2026-08-17", "run_type": "trade_proposals", "ticker": "AAPL",
        "direction": "long", "entry_price": 100.0, "tp_price": 105.0,
        "sl_price": 98.0, "rr_ratio": 2.5, "candidate_class": "core",
    })
    # confirmed divergence: derselbe Lauftyp, aber divergence
    db.save_prediction(conn, {
        "date": "2026-08-17", "run_type": "trade_proposals", "ticker": "GC=F",
        "direction": "long", "entry_price": 2000.0, "tp_price": 2050.0,
        "sl_price": 1980.0, "rr_ratio": 2.5, "candidate_class": "divergence",
    })
    result = db.load_revision_effectiveness(conn, "2026-08-01")
    assert set(result.keys()) >= {"core", "divergence", "since"}
    assert result["core"]["confirmed"]["total"] == 1
    assert result["divergence"]["confirmed"]["total"] == 1
    # core und divergence sind unabhaengige Zaehler, keine gemeinsame Summe:
    assert result["core"]["rejected"]["total"] == 0
    assert result["divergence"]["rejected"]["total"] == 0


def test_load_revision_effectiveness_empty_before_any_trade_proposals_run(in_memory_db):
    conn = in_memory_db
    db.init_schema(conn)
    result = db.load_revision_effectiveness(conn, "2026-08-01")
    for cls in ("core", "divergence"):
        assert result[cls]["confirmed"] == {"total": 0, "correct": 0, "pl_eur": 0.0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_db.py -k load_revision_effectiveness -v`
Expected: FAIL — `KeyError: 'core'` (current shape has `confirmed` at the top level)

- [ ] **Step 3: Rework `load_revision_effectiveness()`**

In `src/db.py` (~line 1399), replace the body:

```python
def load_revision_effectiveness(
    conn: sqlite3.Connection, since_date: str,
) -> dict:
    """B.9/Block 1 in der Fassung nach E3: verdient der 16:10-Lauf seine Kosten?

    Durch die Abloesung hat jede Trade-Idee genau EIN Outcome — 'Trefferquote nach
    run_type' waere damit sinnlos. Verglichen werden stattdessen drei Gruppen:
      confirmed — vom 16:10-Lauf bestaetigte Signale (run_type='trade_proposals')
      rejected  — vom 16:10-Lauf abgelehnte (revision_verdict gedreht/verworfen)
      unchecked — nie geprueft (z.B. weil der Lauf ausfiel)

    Seit Plan 3b (Spec 5.6, 20.5 #4) getrennt nach candidate_class: eine
    core- und eine divergence-Trefferquote in einer gemeinsamen Zahl wuerde
    genau die Frage verdecken, die die Klassentrennung beantworten soll --
    schlaegt die Zwei-Signal-Huerde tatsaechlich an. Rueckgabe:
    {'core': {...}, 'divergence': {...}, 'since': str}, je Klasse dieselben
    drei Gruppen wie zuvor auf oberster Ebene."""
    start = _first_trade_proposals_date(conn)
    empty = {"total": 0, "correct": 0, "pl_eur": 0.0}
    if start is None:
        return {
            cls: {"confirmed": dict(empty), "rejected": dict(empty),
                  "unchecked": dict(empty)}
            for cls in ("core", "divergence")
        } | {"since": since_date}
    floor = max(since_date, start)

    def _agg(where: str, candidate_class: str) -> dict:
        r = conn.execute(
            f"""SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN o.correct_direction_eod
                                         THEN 1 ELSE 0 END), 0) AS correct,
                       COALESCE(SUM(o.profit_loss_eur), 0) AS pl
                FROM outcomes o JOIN predictions p ON p.id = o.prediction_id
                WHERE p.date >= ? AND p.candidate_class = ? AND {where}""",
            (floor, candidate_class),
        ).fetchone()
        return {"total": int(r["total"]), "correct": int(r["correct"]),
                "pl_eur": round(float(r["pl"]), 2)}

    return {
        cls: {
            "confirmed": _agg("p.run_type = 'trade_proposals'", cls),
            "rejected":  _agg("p.run_type = 'pre_market' AND "
                              "p.revision_verdict IN ('gedreht', 'verworfen')", cls),
            "unchecked": _agg("p.run_type = 'pre_market' AND "
                              "p.revision_verdict IS NULL", cls),
        }
        for cls in ("core", "divergence")
    } | {"since": floor}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_db.py -k load_revision_effectiveness -v`
Expected: PASS

- [ ] **Step 5: Find and note downstream callers**

Run: `grep -rn "load_revision_effectiveness" src/ main.py`
Expected output includes `main.py`'s `run_weekly()` (`payload["revision_effectiveness"] =
db.load_revision_effectiveness(...)`) and `src/email_sender.py`'s
`_weekly_revision_block()`. Do not change them yet — Task 11 updates the renderer once the
mail section for divergence exists; note the call site here so Task 11 doesn't have to
rediscover it.

- [ ] **Step 6: Run the full DB suite**

Run: `pytest tests/unit/test_db.py -v`
Expected: PASS. `tests/unit/test_email_sender.py`'s weekly tests will likely FAIL now
(shape changed) — that's expected and Task 11 fixes it; don't fix it here.

- [ ] **Step 7: Commit**

```bash
git add src/db.py tests/unit/test_db.py
git commit -m "feat: load_revision_effectiveness() nach candidate_class getrennt (Spec 5.6, breaking)"
```

---

### Task 7: `_classify()` and `_rank_key()` in `ranking.py`

**Files:**
- Modify: `src/ranking.py` (add two helpers, no wiring into `rank_and_persist()` yet)
- Test: `tests/unit/test_ranking.py`

**Interfaces:**
- Consumes: `analysis_strength()` (Task 1).
- Produces: `_classify(analysis: dict, signal_ctx: dict, *, cc: bool) -> tuple[str, int, int | None]`
  returning `(candidate_class, analysis_strength, rank_score)`, and
  `_rank_key(strength: int, rank_score: int | None, ticker: str) -> tuple` for sorting.
  Both consumed by Task 8's rewrite of `rank_and_persist()`.

Isolating classification and sort-key logic as standalone functions makes them testable
against synthetic `signal_ctx` dicts without building a full pipeline run — the "smallest
unit worth a fresh reviewer's gate" for the two trickiest rules in § 5: the `cc=True`
exemption (§ 20.5 #2) and the `NULL`-fallback (§ 20.5 #3).

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_ranking.py` (near the top, after imports — add
`from src.ranking import _classify, _rank_key` to the existing `from src.ranking import
rank_and_persist, score_total` line, which Task 9 will later strip `score_total` from):

```python
def _stock_analysis(direction="long"):
    return {"ticker": "AAPL", "direction": direction, "scores": {
        dim: {"value": 7.0 if direction == "long" else 3.0,
              "evidence": ["a", "b"], "evidence_quality": "ok"}
        for dim in ["market_environment", "company_quality", "valuation",
                    "momentum", "risk", "sector_trend", "catalyst", "policy_risk"]
    }}


def test_classify_core_when_tech_matches():
    a = _stock_analysis("long")
    ctx = {"tech_direction": "long", "tech_strength": 3}
    klasse, strength, rank_score = _classify(a, ctx, cc=False)
    assert klasse == "core"
    assert strength == 8
    assert rank_score == 24


def test_classify_divergence_when_tech_neutral():
    a = _stock_analysis("long")
    ctx = {"tech_direction": "neutral", "tech_strength": 0}
    klasse, strength, rank_score = _classify(a, ctx, cc=False)
    assert klasse == "divergence"
    assert rank_score is None  # tech_strength=0 -> NULL, nie 0 (Spec 20.5 #3)


def test_classify_conflict_when_tech_opposes():
    a = _stock_analysis("long")
    ctx = {"tech_direction": "short", "tech_strength": 3}
    klasse, strength, rank_score = _classify(a, ctx, cc=False)
    assert klasse == "conflict"


def test_classify_missing_sidecar_entry_treated_as_divergence():
    """Kein Sidecar-Eintrag (leeres ctx) -- konservativ wie neutral, nicht
    blockierend wie ein Konflikt."""
    a = _stock_analysis("long")
    klasse, strength, rank_score = _classify(a, {}, cc=False)
    assert klasse == "divergence"


def test_classify_commodity_never_conflicts(cc=True):
    """Spec 20.5 #2: Rohstoffe/Krypto werden nie disqualifiziert, auch nicht
    bei gegenlaeufigem Technik-Signal."""
    a = _stock_analysis("long")
    a["ticker"] = "GC=F"
    ctx = {"tech_direction": "short", "tech_strength": 3}
    klasse, strength, rank_score = _classify(a, ctx, cc=True)
    assert klasse == "core"
    assert rank_score == 24  # trotzdem gebildet, fuer die Sortierung


def test_classify_commodity_without_tech_signal_gets_null_rank_score():
    a = _stock_analysis("long")
    a["ticker"] = "SI=F"
    klasse, strength, rank_score = _classify(a, {}, cc=True)
    assert klasse == "core"
    assert rank_score is None


def test_rank_key_sorts_by_rank_score_descending():
    high = _rank_key(strength=6, rank_score=18, ticker="NVDA")
    low = _rank_key(strength=4, rank_score=12, ticker="BRK-B")
    assert high < low  # tuple-Vergleich: kleinerer Schluessel = weiter vorn


def test_rank_key_falls_back_to_strength_when_rank_score_is_none():
    """Zwei Divergenz-Kandidaten (rank_score immer None) sortieren nach
    analysis_strength, nicht per Zufall gleich (Spec 5.4-Fussnote)."""
    stronger = _rank_key(strength=6, rank_score=None, ticker="AAPL")
    weaker = _rank_key(strength=2, rank_score=None, ticker="ZZZZ")
    assert stronger < weaker


def test_rank_key_ticker_breaks_ties_deterministically():
    a = _rank_key(strength=4, rank_score=12, ticker="AAA")
    b = _rank_key(strength=4, rank_score=12, ticker="ZZZ")
    assert a < b
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_ranking.py -k "classify or rank_key" -v`
Expected: FAIL with `ImportError: cannot import name '_classify'`

- [ ] **Step 3: Implement the two helpers**

In `src/ranking.py`, add after the `_rule_name()` function and before `_guardrail_filter()`:

```python
from src.analysis_signal import analysis_strength


def _classify(
    analysis: dict, signal_ctx: dict, *, cc: bool,
) -> tuple[str, int, int | None]:
    """Klassifiziert eine guardrail- und B.3-check-bestandene Analyse nach
    Spec 5.3-5.5. Gibt (candidate_class, analysis_strength, rank_score)
    zurueck. direction='none' ist hier bereits durch _guardrail_filter()
    ausgefiltert -- nur long/short erreichen diese Funktion.

    rank_score ist NULL, wenn tech_strength 0 oder unbekannt ist (Spec 5.4,
    20.5 #3): sonst loescht der Faktor 0 die Aussage von analysis_strength.
    technical_signal.compute() liefert strength=0 NUR beim neutralen Fall
    (src/technical_signal.py:103-106) -- ein echtes long/short-Technik-Signal
    hat immer staerke >= 1. rank_score ist deshalb fuer STOCK-'core' immer
    gesetzt und fuer jeden Divergenz-Fall (tech_direction='neutral') immer
    NULL; die Sortierung faellt dort auf analysis_strength zurueck (_rank_key).

    cc=True (Rohstoffe/Krypto, Spec 20.5 #2): die Zwei-Signal-Huerde gilt
    nicht. Ein fehlendes oder gegenlaeufiges Technik-Signal disqualifiziert
    nicht -- 'always kept, regardless of score' bleibt bestehen, das
    Technik-Signal traegt nur noch zum rank_score bei, wenn es da ist."""
    strength = analysis_strength(analysis)
    tech_direction = signal_ctx.get("tech_direction")
    tech_strength = signal_ctx.get("tech_strength")
    direction = analysis["direction"]

    rank_score = strength * tech_strength if tech_strength else None

    if cc:
        return "core", strength, rank_score

    if tech_direction == direction:
        return "core", strength, rank_score
    if tech_direction in ("long", "short"):
        return "conflict", strength, rank_score
    # tech_direction ist 'neutral' ODER fehlt (kein Sidecar-Eintrag) --
    # beides konservativ wie eine Divergenz behandeln, nie wie ein Konflikt.
    return "divergence", strength, rank_score


def _rank_key(strength: int, rank_score: int | None, ticker: str) -> tuple:
    """Sortierschluessel fuer Top-10 und Divergenz-Listen: rank_score
    absteigend, faellt bei NULL auf analysis_strength zurueck (Spec 5.4),
    Ticker alphabetisch als deterministischer Tie-Break (Spec 5.4)."""
    primary = rank_score if rank_score is not None else strength
    return (-primary, -strength, ticker)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_ranking.py -k "classify or rank_key" -v`
Expected: PASS, all 9 tests

- [ ] **Step 5: Run the full ranking suite to confirm nothing existing broke**

Run: `pytest tests/unit/test_ranking.py -v`
Expected: PASS (this task only adds functions, doesn't wire them in yet)

- [ ] **Step 6: Commit**

```bash
git add src/ranking.py tests/unit/test_ranking.py
git commit -m "feat: _classify()/_rank_key() -- Qualifikation und Sortierung (Spec 5.3-5.5)"
```

---

### Task 8: Rework `rank_and_persist()` — qualification, rank_score, divergence, C.1 fix

**Files:**
- Modify: `src/ranking.py` (`_to_prediction_row()`, `_run_checks()`, `rank_and_persist()`;
  remove `score_total()` and the `TOP_N`-only sort)
- Test: `tests/unit/test_ranking.py`

**Interfaces:**
- Consumes: `_classify()`/`_rank_key()` (Task 7), `check_earnings()` (Task 4),
  `config.DIVERGENCE_TOP_N` (Task 2), the 8 new `predictions` columns (Task 3).
- Produces: `rank_and_persist(..., signal_context: dict[str, dict], ...)` — **new required
  keyword parameter**. Return dict gains two keys: `"divergence": list[dict]` and
  `"divergence_stats": {"tech_only_abstentions": int, "conflicts": int, "overflow": int}`.
  Task 9 (main.py) builds and passes `signal_context`; Task 11 (email_sender.py) reads
  `"divergence"`/`"divergence_stats"`.

This is the core rewrite. `signal_context` is a `dict[str, dict]` keyed by ticker, each value
shaped like:

```python
{
    "tech_direction": str | None, "tech_agreement": int | None,
    "tech_adx_band": str | None, "tech_strength": int | None,
    "atr_pct": float | None, "rsi_14": float | None, "volume_ratio": float | None,
    "earnings_in_days": int | None, "news_strength": int | None,
}
```

Task 9 builds this shape; this task only consumes it (tests here construct it by hand).

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_ranking.py`. These replace the old `probability_pct`-based sort
assumption baked into `test_rank_and_persist_top_10_long_and_short` — update that existing
test too (shown in Step 1b).

```python
def _ctx(tech_direction="long", tech_strength=3, **overrides):
    base = {
        "tech_direction": tech_direction, "tech_agreement": 2,
        "tech_adx_band": "normal", "tech_strength": tech_strength,
        "atr_pct": 2.5, "rsi_14": 55.0, "volume_ratio": 0.9,
        "earnings_in_days": None, "news_strength": 2,
    }
    base.update(overrides)
    return base


def test_rank_and_persist_sorts_by_rank_score_not_probability(in_memory_db):
    """Ein Ticker mit niedrigerem probability_pct aber hoeherem rank_score
    (mehr belegte Dimensionen * staerkerem Technik-Signal) landet vorn."""
    conn = in_memory_db
    db.init_schema(conn)
    weak_evidence = _analysis("AAA", momentum=9.0, prob=90)
    for dim in ("company_quality", "valuation", "risk"):
        weak_evidence["scores"][dim]["evidence_quality"] = "thin"
    strong_evidence = _analysis("ZZZ", momentum=8.0, prob=50)
    signal_context = {
        "AAA": _ctx(tech_strength=1),   # analysis_strength=5, rank_score=5
        "ZZZ": _ctx(tech_strength=4),   # analysis_strength=8, rank_score=32
    }
    result = rank_and_persist(
        conn=conn, date="2026-08-17", run_type="pre_market",
        stock_analyses=[weak_evidence, strong_evidence],
        commodity_crypto_analyses=[], market_context=_market_ctx(),
        signal_context=signal_context,
    )
    assert [a["ticker"] for a in result["top_long"]] == ["ZZZ", "AAA"]


def test_rank_and_persist_persists_rank_score_and_candidate_class(in_memory_db):
    conn = in_memory_db
    db.init_schema(conn)
    a = _analysis("AAPL", momentum=8.0)
    result = rank_and_persist(
        conn=conn, date="2026-08-17", run_type="pre_market",
        stock_analyses=[a], commodity_crypto_analyses=[],
        market_context=_market_ctx(),
        signal_context={"AAPL": _ctx(tech_direction="long", tech_strength=3)},
    )
    assert len(result["top_long"]) == 1
    row = conn.execute(
        "SELECT * FROM predictions WHERE ticker='AAPL'").fetchone()
    assert row["candidate_class"] == "core"
    assert row["tech_direction"] == "long"
    assert row["tech_strength"] == 3
    assert row["rank_score"] == row["analysis_strength"] * 3
    # C.1-Fix: standen vorher hart auf None
    assert row["atr_pct"] == 2.5
    assert row["rsi_at_entry"] == 55.0
    assert row["volume_ratio"] == 0.9


def test_rank_and_persist_drops_conflicting_signals_as_guardrail_reject(in_memory_db):
    conn = in_memory_db
    db.init_schema(conn)
    a = _analysis("AAPL", momentum=8.0)
    result = rank_and_persist(
        conn=conn, date="2026-08-17", run_type="pre_market",
        stock_analyses=[a], commodity_crypto_analyses=[],
        market_context=_market_ctx(),
        signal_context={"AAPL": _ctx(tech_direction="short", tech_strength=3)},
    )
    assert result["top_long"] == []
    row = conn.execute(
        "SELECT * FROM predictions WHERE ticker='AAPL'").fetchone()
    assert row is None
    reject = conn.execute(
        "SELECT * FROM guardrail_rejects WHERE ticker='AAPL'").fetchone()
    assert reject["rule"] == "tech_news_conflict"


def test_rank_and_persist_puts_divergent_signals_in_their_own_list(in_memory_db):
    conn = in_memory_db
    db.init_schema(conn)
    a = _analysis("AAPL", momentum=8.0)
    result = rank_and_persist(
        conn=conn, date="2026-08-17", run_type="pre_market",
        stock_analyses=[a], commodity_crypto_analyses=[],
        market_context=_market_ctx(),
        signal_context={"AAPL": _ctx(tech_direction="neutral", tech_strength=0)},
    )
    assert result["top_long"] == []
    assert [d["ticker"] for d in result["divergence"]] == ["AAPL"]
    row = conn.execute(
        "SELECT * FROM predictions WHERE ticker='AAPL'").fetchone()
    assert row is not None
    assert row["candidate_class"] == "divergence"
    assert row["rank_score"] is None


def test_rank_and_persist_caps_divergence_at_divergence_top_n(in_memory_db, monkeypatch):
    conn = in_memory_db
    db.init_schema(conn)
    monkeypatch.setattr(config, "DIVERGENCE_TOP_N", 2)
    analyses = [_analysis(f"T{i}", momentum=8.0) for i in range(4)]
    signal_context = {f"T{i}": _ctx(tech_direction="neutral", tech_strength=0)
                      for i in range(4)}
    result = rank_and_persist(
        conn=conn, date="2026-08-17", run_type="pre_market",
        stock_analyses=analyses, commodity_crypto_analyses=[],
        market_context=_market_ctx(), signal_context=signal_context,
    )
    assert len(result["divergence"]) == 2
    assert result["divergence_stats"]["overflow"] == 2


def test_rank_and_persist_commodity_survives_opposing_tech_signal(in_memory_db):
    """Spec 20.5 #2: Rohstoffe/Krypto werden vom Technik-Signal nie verworfen."""
    conn = in_memory_db
    db.init_schema(conn)
    cc = _analysis("GC=F", momentum=8.0, asset_class="commodity")
    result = rank_and_persist(
        conn=conn, date="2026-08-17", run_type="pre_market",
        stock_analyses=[], commodity_crypto_analyses=[cc],
        market_context=_market_ctx(),
        signal_context={"GC=F": _ctx(tech_direction="short", tech_strength=2)},
    )
    assert [a["ticker"] for a in result["commodities_crypto"]] == ["GC=F"]
    row = conn.execute("SELECT * FROM predictions WHERE ticker='GC=F'").fetchone()
    assert row["candidate_class"] == "core"


def test_rank_and_persist_counts_tech_only_abstentions(in_memory_db):
    """Spec 5.5, mittlere Zeile: Technik hat Richtung, Analyse enthaelt sich."""
    conn = in_memory_db
    db.init_schema(conn)
    abstained = _analysis("AAPL", momentum=8.0)
    abstained["direction"] = "none"
    result = rank_and_persist(
        conn=conn, date="2026-08-17", run_type="pre_market",
        stock_analyses=[abstained], commodity_crypto_analyses=[],
        market_context=_market_ctx(),
        signal_context={"AAPL": _ctx(tech_direction="long", tech_strength=2)},
    )
    assert result["divergence_stats"]["tech_only_abstentions"] == 1


def test_score_total_and_dimension_weights_are_gone():
    """score_total()/config.DIMENSION_WEIGHTS entfallen (Spec 5.7)."""
    import src.ranking as ranking_module
    assert not hasattr(ranking_module, "score_total")
    assert not hasattr(config, "DIMENSION_WEIGHTS")
```

- [ ] **Step 1b: Update the existing top-10 test for the new sort key**

`test_rank_and_persist_top_10_long_and_short` currently asserts an order derived from
`probability_pct`/`momentum`. Update its call to pass `signal_context` with matching
`tech_direction`/`tech_strength` for every ticker it constructs, so qualification passes and
the assertion reflects `rank_score` order instead. Read the test body first
(`tests/unit/test_ranking.py:69-92`) before editing — its fixture tickers and expected order
must be adjusted together, not just the call signature.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_ranking.py -v`
Expected: Multiple FAILs — `TypeError: rank_and_persist() missing 1 required keyword-only
argument: 'signal_context'` and `score_total` import errors once Step 3 removes it.

- [ ] **Step 3: Remove `score_total()` and the `DIMENSION_WEIGHTS` import path**

In `src/ranking.py`, delete the `score_total()` function entirely (lines 20-28). Its only
use of `config` was `config.DIMENSION_WEIGHTS`; keep the `import config` line itself —
Step 6 below adds `config.DIVERGENCE_TOP_N`, so the import stays required.

In `config.py`, delete the `DIMENSION_WEIGHTS` dict (lines 321-330).

- [ ] **Step 4: Update `_to_prediction_row()` — C.1 fix + new columns**

Replace the function body in `src/ranking.py`:

```python
def _to_prediction_row(
    analysis: dict, date: str, run_type: str, market_context: dict, conn,
    signal_ctx: dict,
    etf_momentum: float | None = None, db_momentum: float | None = None,
) -> dict:
    """Maps one classified analysis dict onto the flat column layout expected
    by db.save_prediction(). Der Sektor kommt aus ticker_sectors, nicht mehr
    aus dem marktweiten market_context-Dict.

    signal_ctx traegt (Spec 20.5, Task 7/8): das Technik-Signal zum
    Entscheidungszeitpunkt, die drei C.1-Indikatoren (vorher hart auf None),
    den Phase-2-Scan-Wert. analysis traegt zusaetzlich die drei Schluessel
    _candidate_class/_analysis_strength/_rank_score, die rank_and_persist()
    beim Klassifizieren aufklebt (s. dort)."""
    scores = analysis.get("scores", {})
    sector_row = db.get_ticker_sector(conn, analysis["ticker"])
    return {
        "date": date, "run_type": run_type,
        "asset_class": analysis.get("asset_class"),
        "ticker": analysis["ticker"], "direction": analysis["direction"],
        "entry_price": analysis["current_price"],
        "price_premarket": analysis.get("price_premarket"),
        "is_premarket":    analysis.get("is_premarket"),
        "tp_price": analysis["tp_price"], "tp_pct": analysis.get("tp_pct"),
        "sl_price": analysis["sl_price"], "sl_pct": analysis.get("sl_pct"),
        "rr_ratio": analysis["rr_ratio"],
        "total_score": analysis.get("total_score"),
        "probability_pct": analysis.get("probability_pct"),
        "confidence": analysis.get("confidence"),
        "score_market_env": scores.get("market_environment", {}).get("value"),
        "score_company":    scores.get("company_quality", {}).get("value"),
        "score_valuation":  scores.get("valuation", {}).get("value"),
        "score_momentum":   scores.get("momentum", {}).get("value"),
        "score_risk":       scores.get("risk", {}).get("value"),
        "score_sector":     scores.get("sector_trend", {}).get("value"),
        "score_catalyst":   scores.get("catalyst", {}).get("value"),
        "score_policy":     scores.get("policy_risk", {}).get("value"),
        # C.1-Fix (Abschluss-Review Sprint 3C): standen hart auf None, obwohl
        # laengst berechnet -- Voraussetzung dafuer, dass 3D auf diesen drei
        # Dimensionen ueberhaupt lernen kann.
        "atr_pct": signal_ctx.get("atr_pct"),
        "rsi_at_entry": signal_ctx.get("rsi_14"),
        "volume_ratio": signal_ctx.get("volume_ratio"),
        "market_regime": market_context.get("market_regime"),
        "vix_at_prediction": market_context.get("vix_level"),
        "sector": sector_row["name"] if sector_row else None,
        "trend_boost": None,
        "earnings_warning": bool(analysis.get("earnings_warning")),
        "summary": analysis.get("summary"),
        "sector_etf_momentum": etf_momentum,
        "sector_db_momentum": db_momentum,
        "learnable": True,
        "hold_days_recommended": analysis.get("hold_days_recommended"),
        "intraday_range_pct": analysis.get("intraday_range_pct"),
        "candidate_class": analysis.get("_candidate_class", "core"),
        "tech_direction": signal_ctx.get("tech_direction"),
        "tech_agreement": signal_ctx.get("tech_agreement"),
        "tech_adx_band": signal_ctx.get("tech_adx_band"),
        "tech_strength": signal_ctx.get("tech_strength"),
        "analysis_strength": analysis.get("_analysis_strength"),
        "rank_score": analysis.get("_rank_score"),
        "news_strength": signal_ctx.get("news_strength"),
    }
```

- [ ] **Step 5: Add `earnings_in_days` to `_run_checks()`**

In `src/ranking.py`, update the signature and body:

```python
def _run_checks(
    analysis: dict, conn, date: str, run_type: str,
    market_context: dict, sector_momentum: dict[int, dict],
    cluster_counts: dict[str, int], enforce: bool,
    earnings_in_days: int | None = None,
) -> list[signal_checks.CheckResult]:
    """Fuehrt die B.3-Checks fuer EINE Analyse aus [... bestehender Docstring
    unveraendert ...]."""
    ticker = analysis["ticker"]
    direction = analysis.get("direction")
    etf_mom, db_mom = momentum_for(conn, ticker, sector_momentum)
    sector = db.get_ticker_sector(conn, ticker)
    sector_name = sector["name"] if sector else None

    results = [
        r for r in (
            signal_checks.check_vix(
                direction, analysis.get("confidence"),
                market_context.get("vix_level"), enforce=enforce),
            signal_checks.check_sector_momentum(
                direction, etf_mom, db_mom, enforce=enforce),
            signal_checks.check_cluster(
                sector_name, cluster_counts.get(sector_name or "", 0)),
            signal_checks.check_earnings(
                direction, earnings_in_days, enforce=enforce),
        ) if r is not None
    ]

    for r in results:
        db.log_guardrail_reject(conn, {
            "date": date, "run_type": run_type, "ticker": ticker,
            "direction": direction, "rule": r.rule, "detail": r.detail,
            "enforced": 1 if r.enforced else 0,
            "sector_etf_momentum": etf_mom, "sector_db_momentum": db_mom,
        })
    return results
```

- [ ] **Step 6: Rewrite `rank_and_persist()`**

Replace the whole function body in `src/ranking.py`:

```python
def rank_and_persist(
    conn,
    date: str,
    run_type: str,
    stock_analyses: list[dict],
    commodity_crypto_analyses: list[dict],
    market_context: dict,
    signal_context: dict[str, dict],
    sector_momentum: dict[int, dict] | None = None,
    enforce_checks: bool = False,
) -> dict:
    """Returns {top_long, top_short, commodities_crypto, divergence,
    divergence_stats} und schreibt je Auswahl eine predictions-Zeile.

    signal_context: dict[ticker -> dict] mit dem Technik-Signal, den drei
    C.1-Indikatoren und dem Phase-2-Scan-Wert je Ticker (main.py baut das ueber
    _signal_context()). Fehlt ein Ticker darin, verhaelt sich das wie ein
    fehlendes Technik-Signal (_classify() faellt auf 'divergence').

    enforce_checks steuert Entscheidung E4: run_pipeline() uebergibt False
    (erheben und warnen), run_trade_proposals() uebergibt True (durchsetzen).

    Klassifikation (Spec 5.3-5.5): core -> Top-10 nach rank_score, divergence
    -> eigene, auf DIVERGENCE_TOP_N je Richtung gedeckelte Liste, conflict ->
    verworfen als guardrail_reject (rule='tech_news_conflict'). Rohstoffe/
    Krypto (cc=True in _classify) werden nie als conflict verworfen (Spec
    20.5 #2)."""
    sector_momentum = sector_momentum or {}
    kept_stocks, abstained_stocks = _guardrail_filter(
        stock_analyses, conn, date, run_type)
    kept_cc, abstained_cc = _guardrail_filter(
        commodity_crypto_analyses, conn, date, run_type)
    abstained = abstained_stocks + abstained_cc

    # Spec 5.5, mittlere Tabellenzeile: Technik hat Richtung, Analyse enthielt
    # sich. _guardrail_filter() hat direction='none' oben bereits verworfen --
    # hier nur zaehlen, wie viele davon eine Technik-Richtung hatten, fuer die
    # Mail-Kennzahl. Nicht persistierbar (Claude hat sich enthalten, es gibt
    # kein TP/SL), deshalb ausschliesslich ein Zaehler.
    tech_only_abstentions = sum(
        1 for a in stock_analyses
        if a.get("direction") == "none"
        and signal_context.get(a.get("ticker", ""), {}).get("tech_direction")
            in ("long", "short")
    )

    counts = cluster_counts(conn, [a["ticker"] for a in kept_stocks])
    surviving_stocks: list[dict] = []
    for a in kept_stocks:
        ctx = signal_context.get(a["ticker"], {})
        results = _run_checks(
            a, conn, date, run_type, market_context, sector_momentum,
            counts, enforce_checks,
            earnings_in_days=ctx.get("earnings_in_days"),
        )
        if signal_checks.blocks(results):
            log.info(f"{a['ticker']}: durch B.3-Check verworfen "
                     f"({', '.join(r.rule for r in results if r.enforced)})")
            continue
        surviving_stocks.append(a)

    core: list[dict] = []
    divergence: list[dict] = []
    conflicts = 0
    for a in surviving_stocks:
        ctx = signal_context.get(a["ticker"], {})
        klasse, strength, rank_score = _classify(a, ctx, cc=False)
        a["_candidate_class"] = klasse
        a["_analysis_strength"] = strength
        a["_rank_score"] = rank_score
        if klasse == "core":
            core.append(a)
        elif klasse == "divergence":
            divergence.append(a)
        else:  # conflict
            conflicts += 1
            db.log_guardrail_reject(conn, {
                "date": date, "run_type": run_type, "ticker": a["ticker"],
                "direction": a["direction"], "rule": "tech_news_conflict",
                "detail": f"Analyse={a['direction']}, "
                          f"Technik={ctx.get('tech_direction')}",
                "enforced": 1,
            })

    cc_classified: list[dict] = []
    for a in kept_cc:
        ctx = signal_context.get(a["ticker"], {})
        klasse, strength, rank_score = _classify(a, ctx, cc=True)
        a["_candidate_class"] = klasse
        a["_analysis_strength"] = strength
        a["_rank_score"] = rank_score
        cc_classified.append(a)

    def _key(a: dict) -> tuple:
        return _rank_key(a["_analysis_strength"], a["_rank_score"], a["ticker"])

    longs  = sorted((a for a in core if a["direction"] == "long"),  key=_key)[:TOP_N]
    shorts = sorted((a for a in core if a["direction"] == "short"), key=_key)[:TOP_N]

    div_long  = sorted((a for a in divergence if a["direction"] == "long"),  key=_key)
    div_short = sorted((a for a in divergence if a["direction"] == "short"), key=_key)
    overflow = (max(0, len(div_long) - config.DIVERGENCE_TOP_N)
               + max(0, len(div_short) - config.DIVERGENCE_TOP_N))
    div_long  = div_long[:config.DIVERGENCE_TOP_N]
    div_short = div_short[:config.DIVERGENCE_TOP_N]
    divergence_kept = div_long + div_short

    cc_sorted = sorted(cc_classified, key=_key)

    for a in (*longs, *shorts, *divergence_kept, *cc_sorted):
        ctx = signal_context.get(a["ticker"], {})
        etf_mom, db_mom = momentum_for(conn, a["ticker"], sector_momentum)
        db.save_prediction(conn, _to_prediction_row(
            a, date=date, run_type=run_type, market_context=market_context,
            conn=conn, signal_ctx=ctx, etf_momentum=etf_mom, db_momentum=db_mom,
        ))

    n_in = len(list(stock_analyses)) + len(list(commodity_crypto_analyses))
    n_out = len(longs) + len(shorts) + len(divergence_kept) + len(cc_sorted)
    log.info(
        f"Phase 4 done: {len(longs)} long, {len(shorts)} short, "
        f"{len(divergence_kept)} divergence, {len(cc_sorted)} commodity/crypto "
        f"persisted (aus {n_in} Analysen, davon {abstained} enthalten, "
        f"{conflicts} Technik-Konflikte, {overflow} Divergenz-Deckel-Ueberlauf)"
    )

    if n_out == 0:
        log.warning(
            f"Phase 4: KEINE Prediction persistiert (aus {n_in} Analysen, "
            f"{abstained} Enthaltungen). Der Lauf bleibt ohne Ergebnis — "
            f"Ursache pruefen: zu wenig Historie, Guardrails oder Enthaltungen."
        )
    return {
        "top_long": longs, "top_short": shorts,
        "commodities_crypto": cc_sorted,
        "divergence": divergence_kept,
        "divergence_stats": {
            "tech_only_abstentions": tech_only_abstentions,
            "conflicts": conflicts,
            "overflow": overflow,
        },
    }
```

No new import is needed here: `_classify()` and `_rank_key()` were defined directly in
`src/ranking.py` by Task 7, placed above `_guardrail_filter()` and therefore above
`rank_and_persist()` — already in scope.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/unit/test_ranking.py -v`
Expected: PASS, all tests including the ones updated in Step 1b

- [ ] **Step 8: Run the full test suite to check for collateral damage**

Run: `pytest tests/ --cov=src --cov=main --cov-fail-under=80`
Expected: `tests/unit/test_main.py` will FAIL — `rank_and_persist()` now requires
`signal_context`, and `main.py` doesn't pass it yet. That's Task 9. Confirm the failures are
confined to `test_main.py` and `test_email_sender.py` (the latter from Task 6's
`load_revision_effectiveness()` shape change) — nothing else should break.

- [ ] **Step 9: Commit**

```bash
git add src/ranking.py config.py tests/unit/test_ranking.py
git commit -m "feat: rank_and_persist() nach Spec 5 -- rank_score, candidate_class, Divergenz"
```

---

### Task 9: Wire `signal_context` through `main.py`

**Files:**
- Modify: `main.py` (rename `_cc_sidecar` → `cc_sidecar`, add `_signal_context()`, wire into
  the `rank_and_persist()` call)
- Test: `tests/unit/test_main.py`

**Interfaces:**
- Consumes: `rank_and_persist(..., signal_context=...)` (Task 8).
- Produces: `_signal_context(tds: list[dict], sidecar: dict[str, dict], news_strength_by_ticker:
  dict[str, int] | None = None) -> dict[str, dict]`, used only within `main.py`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_main.py`:

```python
def test_signal_context_bundles_tech_signal_and_c1_indicators():
    from main import _signal_context
    tds = [{"ticker": "AAPL", "atr_pct": 2.5, "rsi_14": 55.0,
            "volume_ratio": 0.9, "earnings_in_days": 3}]
    sidecar = {"AAPL": {"tech_direction": "long", "tech_agreement": 2,
                        "tech_adx_band": "normal", "tech_strength": 3}}
    ctx = _signal_context(tds, sidecar, news_strength_by_ticker={"AAPL": 2})
    assert ctx["AAPL"] == {
        "tech_direction": "long", "tech_agreement": 2,
        "tech_adx_band": "normal", "tech_strength": 3,
        "atr_pct": 2.5, "rsi_14": 55.0, "volume_ratio": 0.9,
        "earnings_in_days": 3, "news_strength": 2,
    }


def test_signal_context_defaults_news_strength_to_none_without_a_map():
    from main import _signal_context
    tds = [{"ticker": "GC=F", "atr_pct": None, "rsi_14": None,
            "volume_ratio": None, "earnings_in_days": None}]
    ctx = _signal_context(tds, {})
    assert ctx["GC=F"]["news_strength"] is None
    assert ctx["GC=F"]["tech_direction"] is None


def test_run_pipeline_passes_signal_context_to_ranking(tmp_db_path, mocker):
    _stub_pipeline(mocker)
    mock_rank = mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    })
    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))
    assert "signal_context" in mock_rank.call_args.kwargs
```

`test_run_pipeline_passes_signal_context_to_ranking` uses the existing `_stub_pipeline(mocker)`
helper (defined at `tests/unit/test_main.py:290`, used by every test from line 316 onward).
It stubs `collect` to return `([], 0, {})` — empty ticker list and empty sidecar — so
`_signal_context()` builds an empty dict in this test; that's fine, the assertion only checks
that `rank_and_persist()` receives a `signal_context` keyword argument at all, not its
content. No new helper needed. Note `_stub_pipeline()` does **not** stub `broad_scan_batch`
or `cutoff_candidates` — those aren't in `run_pipeline()`'s early-return path when `collect`
returns an empty ticker list, so this test doesn't need to touch them either.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_main.py -k "signal_context" -v`
Expected: FAIL — `ImportError: cannot import name '_signal_context'`

- [ ] **Step 3: Rename `_cc_sidecar` to `cc_sidecar`**

In `main.py`, find (around line 323–330, in the Phase 1b block):

```python
        cc_tds_raw, skipped_cc, _cc_sidecar = collect(
```

Rename the third return value to `cc_sidecar` (drop the leading underscore — it's no longer
discarded):

```python
        cc_tds_raw, skipped_cc, cc_sidecar = collect(
```

- [ ] **Step 4: Add `_signal_context()`**

In `main.py`, add near `_forced_candidates()` / `_aggregate_yesterday_outcomes()` (both
private helpers already live near the top of the file):

```python
def _signal_context(
    tds: list[dict], sidecar: dict[str, dict],
    news_strength_by_ticker: dict[str, int] | None = None,
) -> dict[str, dict]:
    """Buendelt je Ticker die Werte, die Phase 4 (Ranking) braucht, aber weder
    im Claude-Analyse-Dict noch im td-Snapshot allein stehen: das
    Technik-Signal aus dem Sidecar, die drei C.1-Indikatoren, und (nur bei
    Aktien, ueber news_strength_by_ticker) den Phase-2-Scan-Wert.

    Getrennt von td gehalten aus demselben Grund wie der Sidecar selbst (R1):
    kein zusaetzlicher Key landet in einem der Claude-Prompts."""
    news_strength_by_ticker = news_strength_by_ticker or {}
    out: dict[str, dict] = {}
    for td in tds:
        t = td["ticker"]
        side = sidecar.get(t, {})
        out[t] = {
            "tech_direction": side.get("tech_direction"),
            "tech_agreement": side.get("tech_agreement"),
            "tech_adx_band":  side.get("tech_adx_band"),
            "tech_strength":  side.get("tech_strength"),
            "atr_pct":        td.get("atr_pct"),
            "rsi_14":         td.get("rsi_14"),
            "volume_ratio":   td.get("volume_ratio"),
            "earnings_in_days": td.get("earnings_in_days"),
            "news_strength":  news_strength_by_ticker.get(t),
        }
    return out
```

- [ ] **Step 5: Build and pass `signal_context` in `run_pipeline()`**

In `main.py`, find the `rank_and_persist()` call (in the `current_phase = "ranking"` block,
around line 458–465) and the block just above it. Insert the `signal_context` build right
before the call and pass it through:

```python
        current_phase = "ranking"
        # Phase 4 — Ranking + persist predictions (market_ctx kommt aus Phase 0b).
        # signal_context buendelt Technik-Signal, C.1-Indikatoren und den
        # Phase-2-Scan-Wert je Ticker (Spec 20.5) -- weder im Claude-Dict noch
        # in td allein vorhanden.
        signal_context = {
            **_signal_context(
                sp500_tds, sp500_sidecar,
                news_strength_by_ticker={
                    c["ticker"]: c["news_strength"] for c in selected
                },
            ),
            **_signal_context(cc_tds, cc_sidecar),
        }
        ranked = rank_and_persist(
            conn=conn, date=date, run_type=run_type,
            stock_analyses=deep_stocks,
            commodity_crypto_analyses=deep_cc,
            market_context=market_ctx,
            signal_context=signal_context,
            sector_momentum=sector_mom,
        )
        payload["top_long"]            = ranked["top_long"]
        payload["top_short"]           = ranked["top_short"]
        payload["commodities_crypto"]  = ranked["commodities_crypto"]
        payload["divergence"]          = ranked["divergence"]
        payload["divergence_stats"]    = ranked["divergence_stats"]
```

- [ ] **Step 6: Update every other mocked `rank_and_persist()` return value in `test_main.py`**

Run: `grep -n '"top_long": \[\], "top_short": \[\], "commodities_crypto": \[\]' tests/unit/test_main.py`

Every match needs `"divergence": [], "divergence_stats": {"tech_only_abstentions": 0,
"conflicts": 0, "overflow": 0}` added to the dict literal — `main.py` now reads
`ranked["divergence"]`/`ranked["divergence_stats"]` unconditionally, so a fake missing them
raises `KeyError` the moment any of those tests runs `run_pipeline()`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/unit/test_main.py -v`
Expected: PASS, all tests

- [ ] **Step 8: Run the full suite**

Run: `pytest tests/ --cov=src --cov=main --cov-fail-under=80`
Expected: PASS except `tests/unit/test_email_sender.py`'s weekly-effectiveness tests
(Task 6's shape change — fixed in Task 11) and any divergence-section assertions not yet
implemented (Task 11).

- [ ] **Step 9: Commit**

```bash
git add main.py tests/unit/test_main.py
git commit -m "feat: signal_context durch main.py verdrahtet, cc_sidecar nicht mehr verworfen"
```

---

### Task 10: `candidate_class` split in `load_recent_outcomes_aggregate()`

**Files:**
- Modify: `main.py:128-152` (`load_recent_outcomes_aggregate`)
- Test: `tests/unit/test_main.py`

**Interfaces:**
- Consumes: `load_recent_outcomes()` now carrying `candidate_class` (Task 5).
- Produces: return dict gains a `"divergence_summary"` key with the same shape as the
  top-level dict. Existing keys (`long_total`, `short_total`, ...) stay `core`-only, so
  `render_weekly_html()`'s existing consumers keep working unchanged — this is additive, not
  breaking, unlike Task 6.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_main.py`:

```python
def test_load_recent_outcomes_aggregate_separates_divergence(tmp_db_path):
    from main import load_recent_outcomes_aggregate
    from src import db
    conn = db.connect(str(tmp_db_path))
    db.init_schema(conn)
    core_id = db.save_prediction(conn, {
        "date": "2026-08-16", "run_type": "pre_market", "ticker": "AAPL",
        "direction": "long", "entry_price": 100.0, "tp_price": 105.0,
        "sl_price": 98.0, "rr_ratio": 2.5, "candidate_class": "core",
    })
    conn.execute(
        """INSERT INTO outcomes (prediction_id, direction, evaluated_date,
                                  correct_direction_eod, profit_loss_eur)
           VALUES (?, 'long', '2026-08-17', 1, 15.0)""", (core_id,))
    div_id = db.save_prediction(conn, {
        "date": "2026-08-16", "run_type": "pre_market", "ticker": "GC=F",
        "direction": "long", "entry_price": 2000.0, "tp_price": 2050.0,
        "sl_price": 1980.0, "rr_ratio": 2.5, "candidate_class": "divergence",
    })
    conn.execute(
        """INSERT INTO outcomes (prediction_id, direction, evaluated_date,
                                  correct_direction_eod, profit_loss_eur)
           VALUES (?, 'long', '2026-08-17', 0, -20.0)""", (div_id,))
    conn.commit()

    agg = load_recent_outcomes_aggregate(conn, today="2026-08-17")
    assert agg["long_total"] == 1
    assert agg["total_pl_eur"] == 15.0
    assert agg["divergence_summary"]["long_total"] == 1
    assert agg["divergence_summary"]["total_pl_eur"] == -20.0
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_main.py -k separates_divergence -v`
Expected: FAIL — the divergence row's P&L (-20.0) currently blends into `total_pl_eur`
(`AssertionError: assert -5.0 == 15.0`)

- [ ] **Step 3: Rework `load_recent_outcomes_aggregate()`**

In `main.py`, replace the function body:

```python
def _direction_split(rows: list) -> dict:
    """Baut die long/short-Zusammenfassung fuer eine Zeilenmenge -- extrahiert
    aus load_recent_outcomes_aggregate(), damit core und divergence dieselbe
    Rechnung nutzen, ohne sich zu vermischen (Spec 5.6)."""
    long_t = [r for r in rows if r["pred_direction"] == "long"]
    short_t = [r for r in rows if r["pred_direction"] == "short"]

    def _agg(items):
        n = len(items)
        correct = sum(1 for r in items if r["correct_direction_eod"])
        pl = sum(r["profit_loss_eur"] or 0.0 for r in items)
        avg = round(pl / n, 2) if n else 0.0
        return n, correct, avg, pl

    ln, lc, la, lp = _agg(long_t)
    sn, sc, sa, sp = _agg(short_t)
    return {
        "long_total": ln, "long_correct": lc, "long_avg_pl": la,
        "short_total": sn, "short_correct": sc, "short_avg_pl": sa,
        "total_pl_eur": round(lp + sp, 2),
        "trades": [{
            "date": r["evaluated_date"], "ticker": r["ticker"],
            "direction": r["pred_direction"],
            "entry_price": r["entry_price"], "exit_price": r["price_after_eod"],
            "exit_reason": r["exit_reason"],
            "profit_loss_eur": r["profit_loss_eur"],
        } for r in rows],
    }


def load_recent_outcomes_aggregate(conn, today: str) -> dict:
    """7-day window for the weekly mail. Seit Plan 3b (Spec 5.6) getrennt nach
    candidate_class: die Top-Level-Kennzahlen bleiben 'core' (unveraendertes
    Verhalten fuer bestehende Mail-Konsumenten), 'divergence_summary' traegt
    dieselbe Struktur fuer die Divergenz-Kandidaten -- nie vermischt in einer
    gemeinsamen Zahl."""
    since = (date_cls.fromisoformat(today) - timedelta(days=7)).isoformat()
    rows = db.load_recent_outcomes(conn, since)
    core_rows = [r for r in rows if r["candidate_class"] == "core"]
    div_rows  = [r for r in rows if r["candidate_class"] == "divergence"]
    result = _direction_split(core_rows)
    result["divergence_summary"] = _direction_split(div_rows)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_main.py -k separates_divergence -v`
Expected: PASS

- [ ] **Step 5: Run the full main.py test suite**

Run: `pytest tests/unit/test_main.py -v`
Expected: PASS, all tests

- [ ] **Step 6: Commit**

```bash
git add main.py tests/unit/test_main.py
git commit -m "feat: load_recent_outcomes_aggregate() trennt divergence_summary (Spec 5.6)"
```

---

### Task 11: Divergence mail section + weekly renderer fix

**Files:**
- Modify: `src/email_sender.py` (`_section_stocks()` or a new `_section_divergence()`,
  `render_daily_html()`, `_weekly_revision_block()`)
- Test: `tests/unit/test_email_sender.py`

**Interfaces:**
- Consumes: `payload["divergence"]` / `payload["divergence_stats"]` (Task 9),
  `db.load_revision_effectiveness()`'s new `{"core": ..., "divergence": ...}` shape (Task 6).

Two independent fixes in one task because both touch `email_sender.py` and both are needed
before the full suite goes green: the new daily-mail section, and the weekly renderer that
Task 6 broke by changing `load_revision_effectiveness()`'s return shape.

- [ ] **Step 1: Read the current weekly renderer before touching it**

`_weekly_revision_block()` (`src/email_sender.py:274-293`) is the function Task 6 broke. Its
current body, for reference before Step 5 replaces it:

```python
def _weekly_revision_block(eff: dict | None) -> str:
    """B.9/Block 1: verdient der 16:10-Lauf seine Kosten? Liegt die Trefferquote
    der abgelehnten Signale unter der der bestaetigten, filtert er richtig."""
    if not eff or not (eff["confirmed"]["total"] or eff["rejected"]["total"]):
        return ('<h2>16:10-Prüfung</h2>'
                '<p><i>Noch keine ausgewerteten Signale seit dem Umbau.</i></p>')

    def _line(label: str, g: dict) -> str:
        return (f'<tr><td>{label}</td><td>{g["correct"]}/{g["total"]}</td>'
                f'<td>{g["pl_eur"]} EUR</td></tr>')
    return (
        '<h2>16:10-Prüfung</h2>'
        '<table border="1" cellpadding="4" cellspacing="0">'
        '<tr><th>Gruppe</th><th>Treffer</th><th>P/L</th></tr>'
        + _line("um 16:10 bestätigt", eff["confirmed"])
        + _line("um 16:10 abgelehnt", eff["rejected"])
        + _line("nie geprüft", eff["unchecked"])
        + '</table>'
        f'<p><small>ausgewertet ab {_h(eff.get("since"))}</small></p>'
    )
```

It's called at `src/email_sender.py:341` as
`+ _weekly_revision_block(payload.get("revision_effectiveness"))` — that call site does not
change.

- [ ] **Step 2: Write the failing tests**

Add to `tests/unit/test_email_sender.py`:

```python
def test_daily_mail_has_a_divergence_section_when_present():
    from src.email_sender import render_daily_html
    payload = {
        "date": "2026-08-17", "run_type": "pre_market",
        "divergence": [{
            "ticker": "AAPL", "direction": "long", "current_price": 230.0,
            "tp_price": 235.0, "sl_price": 228.0, "rr_ratio": 2.5,
            "_analysis_strength": 6, "summary": "Strong news, neutral technicals",
        }],
        "divergence_stats": {"tech_only_abstentions": 3, "conflicts": 1, "overflow": 0},
    }
    html = render_daily_html(payload)
    assert "Divergenz" in html
    assert "AAPL" in html
    assert "3" in html  # tech_only_abstentions sichtbar


def test_daily_mail_divergence_section_handles_empty_list():
    from src.email_sender import render_daily_html
    payload = {
        "date": "2026-08-17", "run_type": "pre_market",
        "divergence": [], "divergence_stats": {
            "tech_only_abstentions": 0, "conflicts": 0, "overflow": 0},
    }
    html = render_daily_html(payload)
    assert "Divergenz" in html


def test_weekly_revision_block_reads_the_split_shape():
    from src.email_sender import render_weekly_html
    empty_group = {"total": 0, "correct": 0, "pl_eur": 0.0}
    payload = {
        "week_label": "KW34",
        "revision_effectiveness": {
            "core": {"confirmed": dict(empty_group), "rejected": dict(empty_group),
                     "unchecked": dict(empty_group)},
            "divergence": {"confirmed": dict(empty_group), "rejected": dict(empty_group),
                           "unchecked": dict(empty_group)},
            "since": "2026-08-10",
        },
        "verdict_stats": [], "guardrail_stats": [], "skipped_stats": [],
        "sector_coverage": [],
        "long_total": 0, "long_correct": 0, "long_avg_pl": 0.0,
        "short_total": 0, "short_correct": 0, "short_avg_pl": 0.0,
        "total_pl_eur": 0.0, "trades": [],
        "divergence_summary": {"long_total": 0, "long_correct": 0, "long_avg_pl": 0.0,
                               "short_total": 0, "short_correct": 0, "short_avg_pl": 0.0,
                               "total_pl_eur": 0.0, "trades": []},
        "cost_summary": {"total_eur": 0.0, "cache_hit_rate": 0.0,
                         "input_tokens": 0, "output_tokens": 0,
                         "web_search_calls": 0, "aborted_at_phase": None},
    }
    html = render_weekly_html(payload)  # darf nicht werfen
    assert "KW34" in html
```

Adjust the payload keys in the third test to whatever `render_weekly_html()` actually reads
end-to-end (check with `grep -n "payload\[" src/email_sender.py` around
`render_weekly_html` and `_weekly_revision_block`/`_weekly_simple_table` if the test needs
more keys than listed here) — the point is a full render with the new
`revision_effectiveness` shape must not raise.

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_email_sender.py -k "divergence" -v`
Expected: FAIL — `render_daily_html()` has no "Divergenz" section yet, and
`render_weekly_html()` raises `KeyError: 'confirmed'` on the new nested shape.

- [ ] **Step 4: Add `_section_divergence()`**

In `src/email_sender.py`, add near `_section_commodities_crypto()`:

```python
def _row_for_divergence(a: dict) -> str:
    """Renders one <tr> for a divergence candidate -- dieselben Kernspalten wie
    _row_for_setup(), aber ohne Rang (die Liste ist nicht nach Top-N sortiert
    im selben Sinn) und ohne rank_score (der ist per Konstruktion immer NULL
    fuer Divergenz-Kandidaten, s. Spec 5.4-Fussnote)."""
    return (
        f'<tr><td>{_h(a["ticker"])}</td><td>{_h(a["direction"])}</td>'
        f'<td>{_h(a.get("_analysis_strength"))}</td>'
        f'<td>{_h(a.get("current_price"))}</td>'
        f'<td>{_h(a.get("tp_price"))}</td>'
        f'<td>{_h(a.get("sl_price"))}</td>'
        f'<td>{_h(a.get("rr_ratio"))}</td>'
        f'<td>{_h(a.get("summary", ""))[:160]}</td></tr>'
    )


def _section_divergence(divergence: list[dict], stats: dict) -> str:
    """Spec 5.5: eigener, klar getrennter Abschnitt -- niemals vermischt mit
    den Top-10-Listen. Die Zaehler stehen daneben, damit 'nichts gefunden' von
    'vieles verworfen' unterscheidbar bleibt (der dominierende Fall laut dem
    Verifikationslauf vom 2026-08-17: 16 von 19 Analysen enthielten sich)."""
    stats = stats or {}
    counters = (
        f'<p><i>Enthaltungen mit Technik-Richtung: '
        f'{_h(stats.get("tech_only_abstentions", 0))} · '
        f'Technik-Konflikte verworfen: {_h(stats.get("conflicts", 0))} · '
        f'Deckel-Ueberlauf: {_h(stats.get("overflow", 0))}</i></p>'
    )
    if not divergence:
        return ('<h2>Divergenz-Kandidaten</h2>'
                '<p><i>Keine.</i></p>' + counters)
    head = (
        '<tr><th>Ticker</th><th>Richtung</th><th>Analysis-Strength</th>'
        '<th>Kurs</th><th>TP</th><th>SL</th><th>R/R</th><th>Begründung</th></tr>'
    )
    rows = "".join(_row_for_divergence(a) for a in divergence)
    return (
        '<h2>Divergenz-Kandidaten</h2>'
        '<p><i>Starkes Signal in einer Dimension, noch keine Bestätigung in '
        'der anderen.</i></p>'
        '<table border="1" cellpadding="4" cellspacing="0">' + head + rows +
        '</table>' + counters
    )
```

Wire it into `render_daily_html()` — insert after `_section_stocks()`, before `_section_trends()`:

```python
def render_daily_html(payload: dict) -> str:
    """Build the 5-section daily e-mail body."""
    return (
        '<html><body style="font-family:sans-serif;font-size:14px;">'
        f'<h1>Shares_Future — {_h(payload.get("date"))} '
        f'({_h(payload.get("run_type"))})</h1>'
        + _section_briefing(payload.get("briefing") or [])
        + _section_portfolio(payload.get("portfolio_recs") or [])
        + _section_stocks(
            payload.get("top_long") or [], payload.get("top_short") or [],
        )
        + _section_divergence(
            payload.get("divergence") or [], payload.get("divergence_stats"),
        )
        + _section_trends(payload.get("trends") or [])
        + _section_commodities_crypto(payload.get("commodities_crypto") or [])
        + _section_footer(payload)
        + '</body></html>'
    )
```

- [ ] **Step 5: Fix `_weekly_revision_block()` for the split shape**

Replace the function body from Step 1 with:

```python
def _weekly_revision_block(eff: dict | None) -> str:
    """B.9/Block 1: verdient der 16:10-Lauf seine Kosten? Liegt die Trefferquote
    der abgelehnten Signale unter der der bestaetigten, filtert er richtig.

    Seit Plan 3b (Spec 5.6) liefert load_revision_effectiveness() core und
    divergence getrennt -- ein Unterblock je Klasse, nie eine gemeinsame
    Zahl, damit eine schwache Divergenz-Trefferquote keine starke Core-Quote
    verwaessert oder umgekehrt."""
    if not eff:
        return ('<h2>16:10-Prüfung</h2>'
                '<p><i>Noch keine ausgewerteten Signale seit dem Umbau.</i></p>')

    def _line(label: str, g: dict) -> str:
        return (f'<tr><td>{label}</td><td>{g["correct"]}/{g["total"]}</td>'
                f'<td>{g["pl_eur"]} EUR</td></tr>')

    empty = {"total": 0, "correct": 0, "pl_eur": 0.0}
    blocks = []
    for cls, cls_label in (("core", "Core"), ("divergence", "Divergenz")):
        group = eff.get(cls, {})
        confirmed = group.get("confirmed", empty)
        rejected  = group.get("rejected", empty)
        unchecked = group.get("unchecked", empty)
        if not (confirmed["total"] or rejected["total"]):
            blocks.append(
                f'<h3>{cls_label}</h3>'
                '<p><i>Noch keine ausgewerteten Signale seit dem Umbau.</i></p>'
            )
            continue
        blocks.append(
            f'<h3>{cls_label}</h3>'
            '<table border="1" cellpadding="4" cellspacing="0">'
            '<tr><th>Gruppe</th><th>Treffer</th><th>P/L</th></tr>'
            + _line("um 16:10 bestätigt", confirmed)
            + _line("um 16:10 abgelehnt", rejected)
            + _line("nie geprüft", unchecked)
            + '</table>'
        )
    return (
        '<h2>16:10-Prüfung</h2>'
        + "".join(blocks)
        + f'<p><small>ausgewertet ab {_h(eff.get("since"))}</small></p>'
    )
```

This keeps `_line()`'s exact original shape (no `_h()` on `label` — matches the original,
which never escaped it either) and the same call site
(`+ _weekly_revision_block(payload.get("revision_effectiveness"))` at line 341, unchanged).

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_email_sender.py -v`
Expected: PASS, all tests

- [ ] **Step 7: Run the full suite**

Run: `pytest tests/ --cov=src --cov=main --cov-fail-under=80`
Expected: PASS. This should be the first fully green run since Task 6.

- [ ] **Step 8: Commit**

```bash
git add src/email_sender.py tests/unit/test_email_sender.py
git commit -m "feat: Divergenz-Mail-Sektion + Weekly-Renderer auf candidate_class-Split (Spec 5.5-5.6)"
```

---

### Task 12: Live test run + documentation

**Files:**
- Modify: `docs/superpowers/specs/PROJECT_STATUS.md` (new entry)
- Modify: `CLAUDE.md` (Sprint-Stand section, `DIMENSION_WEIGHTS` architecture invariant per
  Spec § 5.7's own note)
- Modify: `docs/ARCHITECTURE.md` (Modul 4 / Ranking description, if it documents
  `probability_pct`-sorting or `DIMENSION_WEIGHTS`)

**Interfaces:** None — this task doesn't touch application code.

- [ ] **Step 1: Run the full test suite one more time as a baseline**

Run: `pytest tests/ --cov=src --cov=main --cov-fail-under=80`
Expected: PASS, note the exact test count and coverage percentage for the doc entries below.

- [ ] **Step 2: Live test run against a throwaway DB copy**

Follow the same procedure as Plan 3a's Task 10 (documented in PROJECT_STATUS C.9/C.11):
copy `data/tracking.db` to a scratch location, run `pre_market` against it with real
Capital.com/Finnhub/Anthropic calls but a deliberately invalid `RESEND_API_KEY` so no mail
sends, and inspect the resulting `predictions` rows.

```bash
cp data/tracking.db /tmp/plan3b_verify.db
RESEND_API_KEY=invalid python main.py --run-type pre_market --db-path /tmp/plan3b_verify.db
```

Check, against Spec § 12's prompt questions adapted for this plan:

| Prüffrage | Wie prüfen |
|---|---|
| Verteilen sich `candidate_class`-Werte plausibel (core/divergence, kein leeres Ergebnis wegen eines Bugs)? | `sqlite3 /tmp/plan3b_verify.db "SELECT candidate_class, COUNT(*) FROM predictions WHERE date=date('now') GROUP BY candidate_class"` |
| Ist `rank_score` NULL nur dort, wo `tech_strength` 0/NULL ist? | `sqlite3 /tmp/plan3b_verify.db "SELECT ticker, tech_strength, rank_score FROM predictions WHERE date=date('now')"` — jede Zeile mit `rank_score IS NULL` muss `tech_strength IN (0, NULL)` haben |
| Ist die Top-10-Sortierung plausibel? | Von Hand gegen `analysis_strength * tech_strength` nachrechnen für die ersten 3 Zeilen |
| Feuert `check_earnings` überhaupt (falls ein Kandidat zufällig <=2 Tage vor Earnings steht)? | `guardrail_rejects` nach `rule='earnings_imminent'` filtern |
| Kommt die Divergenz-Sektion in der (unterdrückten) Mail korrekt gerendert an? | Render-Ergebnis lokal inspizieren, z.B. über einen Python-Einzeiler, der `render_daily_html()` mit dem geloggten Payload aufruft |

- [ ] **Step 3: Update PROJECT_STATUS.md**

Add a new entry at the top of the file (after the header, before the current top entry),
following the exact style of existing entries (see the C.9–C.12 entries for tone/format):

```markdown
**Zuletzt aktualisiert:** <YYYY-MM-DD> — ✅ **Plan 3b (Ranking) abgeschlossen
(12/12 Tasks).** rank_score (analysis_strength × tech_strength) ersetzt probability_pct
als Sortierschlüssel, candidate_class trennt core/divergence in Persistierung und
Aggregaten, der C.1-Fix (atr_pct/rsi_at_entry/volume_ratio) ist mitgenommen,
score_total()/DIMENSION_WEIGHTS sind entfernt. Live-Testlauf gegen eine Wegwerf-Kopie:
<Ergebnis aus Step 2 eintragen — Verteilung candidate_class, ob rank_score plausibel
war>. <N> Tests grün, <X>% Coverage. Details: PROJECT_STATUS <neuer Abschnittsname,
z.B. C.13>.
```

Add a corresponding `## C.13` (or the next free letter/number) section below with the
findings from Step 2 in full detail, matching the depth of the C.9–C.12 sections.

- [ ] **Step 4: Update CLAUDE.md**

Two changes:

1. In the "Zuletzt aktualisiert" header block, add a new entry above the current top one
   summarizing Plan 3b's completion (2-4 sentences, matching the terse style of existing
   entries).
2. Find the architecture-invariant note about the 8 score dimensions and
   `DIMENSION_WEIGHTS` (search: `grep -n "DIMENSION_WEIGHTS\|8 Score-Dimensionen"
   CLAUDE.md`) and replace it per Spec § 5.7's own instruction: *die acht Dimensionen und
   ihre Einzelwerte bleiben erhalten und werden persistiert; eine Gewichtung findet im Code
   nicht statt und ist Aufgabe von 3D.*
3. Update the "Sprint-Stand" section's Plan-3b bullet (`⏳ offen, noch keine Plan-Datei`) to
   reflect completion, matching how Plan 3a's line was updated after its own completion.

- [ ] **Step 5: Update ARCHITECTURE.md if needed**

Run: `grep -n "probability_pct\|DIMENSION_WEIGHTS\|score_total\|Ranking" docs/ARCHITECTURE.md`

If any of these describe the now-removed sort behavior, update them to describe
`rank_score`/`candidate_class` instead, following the file's existing level of detail (check
how Plan 2's Task 13 updated this file, referenced in PROJECT_STATUS, for the expected
tone/depth).

- [ ] **Step 6: Final full-suite run**

Run: `pytest tests/ --cov=src --cov=main --cov-fail-under=80`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/specs/PROJECT_STATUS.md CLAUDE.md docs/ARCHITECTURE.md
git commit -m "docs: Plan 3b abgeschlossen -- Live-Testlauf, Sprint-Stand nachgezogen"
```
