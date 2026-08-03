# Sprint 3B / Plan 2: Pipeline-Umbau (Cron, trade_proposals, Checks, Mails)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Pipeline auf die Ziel-Cron-Struktur umbauen — `midday`, `evaluate` und `position_check` entfernen, den neuen Run-Type `trade_proposals` (16:10 Berlin) einführen, die sieben B.3-Checks verdrahten, Phase 1c und die getauschte Phase-4/4a-Reihenfolge einbauen und die Mails nachziehen.

**Architecture:** Im Gegensatz zu Plan 1 ist dieser Plan **destruktiv**: Run-Types, Funktionen, Prompts und Tests verschwinden. Der neue 16:10-Lauf prüft die Morgensignale **billig ohne Websuche** gegen frische Kurse und löst die `pre_market`-Prediction über `status='superseded'` ab, statt eine zweite offene Zeile daneben zu legen. Zwei neue Module: `src/signal_checks.py` (rein rechnerisch, netzwerkfrei) und `src/revalidation.py` (der eine Claude-Call).

**Tech Stack:** Python 3.12, SQLite (stdlib `sqlite3`), pandas, requests, Anthropic Claude API (`claude-sonnet-4-6`), Capital.com REST API, Resend, pytest + pytest-mock.

**Spec reference:** `docs/superpowers/specs/2026-07-30-sprint3b-plan2-pipeline-umbau-design.md` (freigegeben 2026-07-30). Dort stehen die fünf Entscheidungen E1–E5, die die Vorgaben aus PROJECT_STATUS an mehreren Stellen korrigieren.

---

## Die fünf Entscheidungen aus der Planungssession (2026-07-30)

| # | Entscheidung | Wirkung auf diesen Plan |
|---|---|---|
| **E1** | `trade_proposals` prüft **billig ohne Websuche** statt voller Phase 3 | Task 12/13 — ein Sonnet-Call ohne `WEB_SEARCH_TOOL` je Asset; Breaking News deckt der eine Policy-Monitor-Call ab |
| **E2** | B.13 (Parallelisierung von Phase 3) wandert zurück nach **3F** | Kein Task in diesem Plan. `analyze_assets()` bleibt sequenziell. |
| **E3** | `pre_market`-Predictions werden **abgelöst**, nicht dupliziert | Task 11/13 — `superseded_by` + `revision_verdict`; Evaluator und Phase 4a bleiben unangetastet |
| **E4** | Checks werden in **beiden** Runs erhoben, **nur um 16:10** durchgesetzt | Task 8 — ein `enforce: bool`-Parameter, gesetzt vom Aufrufer |
| **E5** | Gedrehte Signale werden **gemeldet, nicht gehandelt** | Task 13 — kein neuer Prediction-Row bei `verdict='gedreht'` |

---

## Global Constraints

Diese Regeln gelten für **jeden** Task. Quelle: `CLAUDE.md` und PROJECT_STATUS.md Abschnitt 5.

- **Migrations-Guards Pflicht:** Neue Spalten/Tabellen immer per `PRAGMA table_info(...)` bzw. `sqlite_master`-Abfrage prüfen, bevor `ALTER TABLE` / `CREATE TABLE` läuft. (Regel 5)
- **Timezone:** Kein `datetime.now()` ohne Timezone. Immer `ZoneInfo("Europe/Berlin")`. (Regel 7)
- **Dokumentation Pflicht:** Jede neue Datei bekommt einen Modul-Docstring, jede neue Funktion einen 1-2-Satz-Docstring. (Regel 13)
- **Capital.com ist alleiniger OHLC-Provider:** Kein neuer Code darf `yfinance` importieren. Kein `if config.CAPITAL_COM_API_KEY else ...`-Pattern. (Regel 4)
- **`SIMULATION_ONLY = True` ist sakrosankt:** Alle Capital.com-Aufrufe in diesem Plan sind ausschliesslich lesend (`GET`). (Regel 3)
- **Claude-Antworten immer über `extract_json_blob()`** parsen. (Regel 11)
- **Kosten:** `config.MAX_COST_PER_RUN_EUR = 4.00`. Jeder neue Claude-Call läuft über den `CostTracker`. (Regel 12)
- **Tests nicht abschwächen:** Coverage-Ziel 80 %. Ausnahme in Task 3 — dort werden Tests gelöscht, **weil ihr Testgegenstand entfällt**; das ist kein Abschwächen. Steht dort nochmal explizit.
- **`config.py` bleibt funktionsfrei** — nur Modul-Level-Konstanten.
- **Prompt-Versionierung:** Neue Prompts als `*_v1.txt`, nie bestehende überschreiben. (Regel 10)
- **Doku-Pflege:** `README.md`, `docs/WORKFLOW.md`, `docs/SPECIFICATION.md` und `mvp-design.md` **nicht** anfassen. `CLAUDE.md`, `PROJECT_STATUS.md` und `docs/ARCHITECTURE.md` aktuell halten. (Regel 14)
- **Nie pushen.** Commit nach jedem Task, `git push` macht Korbinian selbst.

**Vorhandene Test-Fixtures** (in `tests/conftest.py`, nicht neu anlegen):
`in_memory_db`, `tmp_db_path`, `sample_ticker_data`.

**Testlauf:** `pytest tests/ --cov=src --cov-fail-under=80`

---

## Datei-Struktur

| Datei | Verantwortung | Tasks |
|---|---|---|
| `src/signal_checks.py` *(neu)* | Die fünf rechnerischen Checks, relative Stärke, Momentum-Lookup und Klumpen-Zählung. Rein funktional, kein Netz, kein Claude — von `ranking.py` **und** `main.py` genutzt. | 7, 8, 10, 13, 15 |
| `src/revalidation.py` *(neu)* | Der eine billige Claude-Call ohne Websuche. Eine öffentliche Funktion. | 12 |
| `prompts/trade_proposals_v1.txt` *(neu)* | System-Prompt der Re-Validierung. | 12 |
| `main.py` | Orchestrator: `run_trade_proposals()`, Phasenreihenfolge, Dispatch. | 1, 2, 3, 5, 6, 9, 13, 17 |
| `src/db.py` | Schema, Migration, `record_revision()`, Weekly-Aggregate. | 10, 11, 18 |
| `src/ranking.py` | Check-Ergebnisse entgegennehmen, Momentum-Spalten schreiben. | 10, 15 |
| `src/portfolio_check.py` | Input = Phase-3-Analysen, ohne Websuche. | 6 |
| `src/email_sender.py` | 16:10-Mail, Weekly-Blöcke, `hold_days_recommended`-Spalte. | 3, 14, 19 |
| `src/providers/capital_provider.py` | Reverse-Map zu `TICKER_MAP`. | 4 |
| `config.py` | `SECTOR_GUARDRAIL_STRICT`, VIX-Schwellen, Warnschwellen. | 8 |
| `.github/workflows/analyze.yml` | Crons, `workflow_dispatch`, `case`-Matching. | 2 |

**Konsistenz-Regel:** Nach **jedem Task** ist das Repo in sich konsistent und die Testsuite grün. Die Reihenfolge in Schnitt 1 ist deshalb bewusst „erst das Neue anlegen, dann umschalten, dann das Alte löschen" — nie umgekehrt.

---

# Schnitt 1 — Abriss und neues Cron-Gerüst

Ziel: `midday`, `evaluate` und `position_check` sind vollständig weg, `trade_proposals` läuft als Gerüst, das die Kurse aller Ticker zieht und **noch keine Mail** verschickt (wie `close`).

---

### Task 1: `run_trade_proposals()` als Gerüst anlegen

**Files:**
- Modify: `main.py` (neue Funktion nach `run_close()`, ca. Zeile 318)
- Test: `tests/unit/test_main.py`

**Interfaces:**
- Consumes: `db.connect`, `db.init_schema`, `src.data_collector.collect`, `CapitalComProvider`, `FinnhubProvider`, `build_commodity_crypto_inputs()`
- Produces: `main.run_trade_proposals(date: str, db_path: str) -> None` — Task 2 hängt es in den Dispatch, Task 13 baut es aus.

Die Funktion zieht in diesem Task **nur** frische Kurse für alle Ticker (SP500 + Commodities/Crypto) und schreibt sie über den bestehenden `collect()`-Pfad in `price_history`. Kein Claude, keine Mail.

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_main.py` ergänzen:

```python
def test_run_trade_proposals_collects_all_tickers(tmp_db_path, mocker):
    """B.2/Schritt 1: der 16:10-Lauf zieht frische Kurse fuer ALLE Ticker,
    nicht nur fuer die Top-Listen."""
    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    collect_mock = mocker.patch("main.collect", return_value=([], 0))

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    # zwei Aufrufe: SP500 und Commodities/Crypto
    assert collect_mock.call_count == 2
    passed = [set(c.kwargs["tickers"]) for c in collect_mock.call_args_list]
    assert set(config.SP500_MVP_TICKERS) in passed
    cc = set(config.COMMODITY_TICKERS.values()) | set(config.CRYPTO_TICKERS.values())
    assert cc in passed


def test_run_trade_proposals_sends_no_mail_yet(tmp_db_path, mocker):
    """Das Geruest verschickt bewusst noch nichts — wie close."""
    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.collect", return_value=([], 0))
    send = mocker.patch("main.send_daily_email")

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    send.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_main.py -k trade_proposals -v`
Expected: FAIL mit `ImportError: cannot import name 'run_trade_proposals' from 'main'`

- [ ] **Step 3: Write minimal implementation**

In `main.py` direkt nach `run_close()` einfügen:

```python
def run_trade_proposals(date: str, db_path: str) -> None:
    """Run-Type trade_proposals (16:10 Berlin): prueft die pre_market-Signale
    nach dem Opening-Rauschen erneut. In diesem Ausbaustand zieht er nur frische
    Kurse fuer alle Ticker; die Re-Validierung kommt in Task 13 dazu."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    price_provider = CapitalComProvider()
    earnings_provider = FinnhubProvider()

    _tickers = (config.SP500_FULL_TICKERS if config.USE_FULL_SP500
                else config.SP500_MVP_TICKERS)
    collect(
        tickers=_tickers, price_provider=price_provider,
        earnings_provider=earnings_provider,
        conn=conn, date=date, run_type="trade_proposals",
    )
    cc_tickers = [d["ticker"] for d in build_commodity_crypto_inputs()]
    collect(
        tickers=cc_tickers, price_provider=price_provider,
        earnings_provider=earnings_provider,
        conn=conn, date=date, run_type="trade_proposals",
    )
    log.info(f"trade_proposals: Kurse fuer {len(_tickers) + len(cc_tickers)} Ticker aktualisiert")
    conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_main.py -k trade_proposals -v`
Expected: PASS (2 Tests)

- [ ] **Step 5: Commit**

```bash
git add main.py tests/unit/test_main.py
git commit -m "feat: run_trade_proposals als Geruest (B.2/Schritt 1)"
```

---

### Task 2: Cron und Run-Type-Liste umstellen

**Files:**
- Modify: `main.py:42` (`RUN_TYPES`), `main.py:404-421` (`main()`-Dispatch)
- Modify: `.github/workflows/analyze.yml:3-16` (Crons + `workflow_dispatch`), `:55-71` (`case`-Matching)
- Test: `tests/unit/test_main.py`, `tests/unit/test_workflow_config.py`

**Interfaces:**
- Consumes: `main.run_trade_proposals()` aus Task 1
- Produces: `RUN_TYPES == ["pre_market", "trade_proposals", "close", "weekly"]`

Dieser Task schaltet `analyze.yml` und `main.py` **gemeinsam** um. Getrennt geht es nicht: ruft der Workflow einen Run-Type auf, den `argparse` nicht mehr kennt, bricht der Job mit Exit 2 ab.

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_main.py` den bestehenden `test_parse_args_accepts_all_run_types` **ersetzen** und zwei Tests ergänzen:

```python
def test_parse_args_accepts_all_run_types():
    for rt in ["pre_market", "trade_proposals", "close", "weekly"]:
        ns = parse_args(["--run-type", rt])
        assert ns.run_type == rt


@pytest.mark.parametrize("removed", ["midday", "evaluate", "position_check"])
def test_parse_args_rejects_removed_run_types(removed):
    """B.1: die drei Run-Types sind vollstaendig entfernt, keine Leichen."""
    with pytest.raises(SystemExit):
        parse_args(["--run-type", removed])


def test_main_dispatches_trade_proposals(mocker):
    fn = mocker.patch("main.run_trade_proposals")
    from main import main as main_fn
    main_fn(["--run-type", "trade_proposals", "--date", "2026-07-30"])
    fn.assert_called_once()
```

In `tests/unit/test_workflow_config.py` ergänzen:

```python
REMOVED_RUN_TYPES = ("midday", "evaluate", "position_check")


@pytest.mark.parametrize("removed", REMOVED_RUN_TYPES)
def test_workflow_has_no_removed_run_types(removed):
    """B.1: kein Cron, keine workflow_dispatch-Option, kein case-Zweig darf
    einen entfernten Run-Type noch nennen — sonst laeuft der Job in Exit 2."""
    assert removed not in WORKFLOW


def test_workflow_schedules_trade_proposals_at_1410_utc():
    """16:10 Berlin (CEST) == 14:10 UTC."""
    assert "'10 14 * * 1-5'" in WORKFLOW
    assert 'T="trade_proposals"' in WORKFLOW


def test_every_cron_has_a_matching_case_branch():
    """Ein Cron ohne case-Zweig fiele still auf den close-Default zurueck."""
    crons = set(re.findall(r"- cron: '([^']+)'", WORKFLOW))
    cases = set(re.findall(r'"([0-9*/, -]+)"\)\s+T=', WORKFLOW))
    assert crons == cases, f"Cron/case-Mismatch: {crons ^ cases}"
```

`import pytest` oben in `test_workflow_config.py` ergänzen.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_main.py tests/unit/test_workflow_config.py -v`
Expected: FAIL — `parse_args(["--run-type", "midday"])` wirft kein `SystemExit`, und `'10 14 * * 1-5'` fehlt in `analyze.yml`

- [ ] **Step 3: Write minimal implementation**

`main.py:42`:

```python
RUN_TYPES = ["pre_market", "trade_proposals", "close", "weekly"]
```

`main.py`, Dispatch in `main()` — den `try`-Block ersetzen durch:

```python
        if ns.run_type == "pre_market":
            run_pipeline(run_type=ns.run_type, date=date, db_path=ns.db_path)
        elif ns.run_type == "trade_proposals":
            run_trade_proposals(date=date, db_path=ns.db_path)
        elif ns.run_type == "close":
            run_close(date=date, db_path=ns.db_path)
        elif ns.run_type == "weekly":
            run_weekly(date=date, db_path=ns.db_path)
        else:  # pragma: no cover — argparse validated
            sys.exit(2)
```

`.github/workflows/analyze.yml`, Zeilen 3–16 ersetzen:

```yaml
  schedule:
    - cron: '0 13 * * 1-5'    # pre_market       15:00 Berlin (CEST)
    - cron: '10 14 * * 1-5'   # trade_proposals  16:10 Berlin (CEST)
    - cron: '30 20 * * 1-5'   # close            22:30 Berlin (CEST)
    - cron: '0 18 * * 0'      # weekly           So 20:00 Berlin (CEST)

  workflow_dispatch:
    inputs:
      run_type:
        type: choice
        options: [pre_market, trade_proposals, close, weekly]
        default: close
```

Das `case`-Matching (Zeilen 62–70) ersetzen:

```bash
          case "${{ github.event.schedule }}" in
            "0 13 * * 1-5")  T="pre_market" ;;
            "10 14 * * 1-5") T="trade_proposals" ;;
            "30 20 * * 1-5") T="close" ;;
            "0 18 * * 0")    T="weekly" ;;
            *)               T="close" ;;
          esac
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_main.py tests/unit/test_workflow_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add main.py .github/workflows/analyze.yml tests/unit/test_main.py tests/unit/test_workflow_config.py
git commit -m "feat: Cron auf die Ziel-Struktur umstellen (B.1)"
```

---

### Task 3: Toten Code der drei Run-Types entfernen

**Files:**
- Modify: `main.py` — `run_position_check()` und `run_evaluate()` löschen, Imports aufräumen
- Modify: `src/email_sender.py:388-427` — `render_position_check_html()` und `send_position_check_email()` löschen
- Delete: `prompts/position_check_v1.txt`
- Modify: `tests/unit/test_main.py`, `tests/unit/test_email_sender.py`, `tests/integration/test_email_render.py`

**Interfaces:**
- Consumes: nichts
- Produces: nichts — reiner Abriss

> **Regel-8-Ausnahme, hier bewusst festgehalten:** Die Tests zu `run_position_check`,
> `run_evaluate` und den beiden `position_check`-Mail-Funktionen werden **gelöscht**.
> Das ist kein Abschwächen der Suite, sondern das Mitziehen eines entfallenen
> Testgegenstands. Es dürfen **nur** Tests entfernt werden, deren Testobjekt in diesem
> Task verschwindet — kein einziger anderer.

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_main.py` ergänzen — der Test, der beweist, dass nichts zurückkommt:

```python
def test_removed_functions_are_gone():
    """B.1: 'vollstaendig, keine Leichen'. Ein spaeterer Reflex-Import wuerde
    hier auffliegen."""
    import main
    import src.email_sender as es
    for name in ("run_position_check", "run_evaluate"):
        assert not hasattr(main, name), f"main.{name} existiert noch"
    for name in ("render_position_check_html", "send_position_check_email"):
        assert not hasattr(es, name), f"email_sender.{name} existiert noch"


def test_position_check_prompt_file_is_deleted():
    from pathlib import Path
    assert not (Path("prompts") / "position_check_v1.txt").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_main.py -k removed -v`
Expected: FAIL — `main.run_position_check existiert noch`

- [ ] **Step 3: Write minimal implementation**

1. In `main.py` die Funktionen `run_position_check()` (Zeilen 321–370) und `run_evaluate()` (373–383) **ersatzlos löschen**.
2. Import-Zeile 30–33 in `main.py` bereinigen:

```python
from src.email_sender import (
    send_daily_email, send_weekly_email, generate_daily_briefing,
    send_error_email,
)
```

3. In `main.py` sind `json`, `Path`, `call_claude` und `extract_json_blob` danach ungenutzt — Imports entfernen. `evaluate_open_predictions` **bleibt** (wird von `run_close()` gebraucht).
4. In `src/email_sender.py` die Funktionen `render_position_check_html()` und `send_position_check_email()` löschen.
5. `git rm prompts/position_check_v1.txt`
6. Alle Tests löschen, die diese Objekte testen: in `tests/unit/test_main.py` die Tests mit `position_check` bzw. `run_evaluate` im Namen, in `tests/unit/test_email_sender.py` und `tests/integration/test_email_render.py` die `position_check`-Renderer-Tests.

- [ ] **Step 4: Run the full suite**

Run: `pytest tests/ --cov=src --cov-fail-under=80`
Expected: PASS, keine `ImportError`, Coverage ≥ 80 %

- [ ] **Step 5: Commit**

```bash
git add -A main.py src/email_sender.py prompts tests/
git commit -m "refactor: midday, evaluate und position_check restlos entfernen (B.1)"
```

---

# Schnitt 2 — Phase 1c und die getauschte Phase-4/4a-Reihenfolge

Ziel: Offene Capital.com-Positionen erzwingen eine Tiefenanalyse, und der Portfolio-Check
arbeitet auf den fertigen Phase-3-Ergebnissen statt auf Rohsnapshots — ohne Websuche.

---

### Task 4: Reverse-Map zu `TICKER_MAP`

**Files:**
- Modify: `src/providers/capital_provider.py` (nach `TICKER_MAP`, ca. Zeile 32)
- Test: `tests/unit/test_capital_provider.py`

**Interfaces:**
- Consumes: `capital_provider.TICKER_MAP`
- Produces: `capital_provider.epic_to_ticker(epic: str) -> str | None` — Task 5 nutzt es in Phase 1c.

`get_open_positions()` liefert Capital.com-**Epics** (`market["epic"]`), nicht unsere
internen Ticker. Für den Abgleich braucht es die Rückrichtung. Epics ohne Gegenstück
(manuell eröffnete Fremdpositionen) geben `None` zurück.

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_capital_provider.py` ergänzen:

```python
def test_epic_to_ticker_maps_back():
    from src.providers.capital_provider import epic_to_ticker
    assert epic_to_ticker("GOLD") == "GC=F"
    assert epic_to_ticker("BRKB") == "BRK-B"


def test_epic_to_ticker_passes_through_unmapped_known_symbols():
    """Aktien-Epics sind identisch mit dem Ticker — AAPL bleibt AAPL."""
    from src.providers.capital_provider import epic_to_ticker
    assert epic_to_ticker("AAPL") == "AAPL"


def test_epic_to_ticker_is_none_for_foreign_epics():
    """B.4: Fremdpositionen ohne Gegenstueck werden uebersprungen, nicht geraten."""
    from src.providers.capital_provider import epic_to_ticker
    assert epic_to_ticker("PPHE") is None


def test_ticker_map_is_injective():
    """Zwei Ticker auf dasselbe Epic wuerden die Rueckabbildung still falsch
    machen — genau ein Ticker gewaenne, der andere verschwaende lautlos."""
    from src.providers.capital_provider import TICKER_MAP
    assert len(set(TICKER_MAP.values())) == len(TICKER_MAP)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_capital_provider.py -k epic_to_ticker -v`
Expected: FAIL mit `ImportError: cannot import name 'epic_to_ticker'`

- [ ] **Step 3: Write minimal implementation**

In `src/providers/capital_provider.py` direkt nach `TICKER_MAP` einfügen:

```python
# Rueckrichtung fuer Phase 1c (B.4): get_open_positions() liefert Epics, wir
# rechnen intern in Tickern. Beim Import einmal gebaut statt bei jedem Aufruf.
_EPIC_TO_TICKER: dict[str, str] = {v: k for k, v in TICKER_MAP.items()}


def epic_to_ticker(epic: str) -> str | None:
    """Uebersetzt ein Capital.com-Epic zurueck in unser internes Ticker-Symbol.

    Gibt None zurueck, wenn das Epic zu keinem Ticker unserer Universen gehoert —
    typisch fuer von Hand eroeffnete Fremdpositionen. Fuer sie existieren keine
    Indikator-Daten, sie werden vom Aufrufer geloggt und uebersprungen."""
    if epic in _EPIC_TO_TICKER:
        return _EPIC_TO_TICKER[epic]
    known = set(config.SP500_FULL_TICKERS if config.USE_FULL_SP500
                else config.SP500_MVP_TICKERS)
    return epic if epic in known else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_capital_provider.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/providers/capital_provider.py tests/unit/test_capital_provider.py
git commit -m "feat: Reverse-Map Epic zu Ticker fuer Phase 1c (B.4)"
```

---

### Task 5: Phase 1c — offene Positionen als Pflicht-Kandidaten

**Files:**
- Modify: `main.py` — neuer Helper `_forced_candidates()` + Einbau in `run_pipeline()` nach Phase 1b
- Test: `tests/unit/test_main.py`

**Interfaces:**
- Consumes: `capital_provider.epic_to_ticker()` (Task 4), `CapitalComProvider.get_open_positions()`
- Produces: `main._forced_candidates(price_provider) -> set[str]` — Task 13 nutzt es auch im 16:10-Lauf.

Pflicht-Kandidaten überspringen den Quick-Filter-Ausschluss: ihr `exclude` wird nach
Phase 2 auf `False` gesetzt, damit Phase 3 sie garantiert analysiert.

- [ ] **Step 1: Write the failing test**

```python
def test_forced_candidates_maps_epics_and_skips_foreign(mocker):
    """B.4: bekannte Epics werden zu Tickern, fremde geloggt und uebersprungen."""
    provider = MagicMock()
    provider.get_open_positions.return_value = [
        {"ticker": "GOLD"}, {"ticker": "AAPL"}, {"ticker": "PPHE"},
    ]
    from main import _forced_candidates
    assert _forced_candidates(provider) == {"GC=F", "AAPL"}


def test_forced_candidates_is_empty_when_provider_fails(mocker):
    """get_open_positions() gibt bei Fehlern [] zurueck — kein Absturz."""
    provider = MagicMock()
    provider.get_open_positions.return_value = []
    from main import _forced_candidates
    assert _forced_candidates(provider) == set()


def test_forced_candidates_override_quick_filter_exclude():
    """Der Kern von B.4: ein Ticker mit offener Position darf nicht am
    Quick-Filter haengenbleiben."""
    from main import _apply_forced_candidates
    quick = [{"ticker": "AAPL", "exclude": True},
             {"ticker": "MSFT", "exclude": True}]
    out = _apply_forced_candidates(quick, forced={"AAPL"})
    by_t = {q["ticker"]: q for q in out}
    assert by_t["AAPL"]["exclude"] is False
    assert by_t["MSFT"]["exclude"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_main.py -k forced -v`
Expected: FAIL mit `ImportError: cannot import name '_forced_candidates'`

- [ ] **Step 3: Write minimal implementation**

In `main.py` nach `build_commodity_crypto_inputs()` einfügen:

```python
def _forced_candidates(price_provider) -> set[str]:
    """Phase 1c (B.4): Ticker mit offener Capital.com-Position. Sie muessen in
    Phase 3, egal was der Quick-Filter sagt — es haengt echtes Geld daran.

    Epics ohne Gegenstueck in unserer Ticker-Liste (von Hand eroeffnete
    Fremdpositionen) werden geloggt und uebersprungen: fuer sie gibt es keine
    Indikator-Daten."""
    from src.providers.capital_provider import epic_to_ticker
    forced: set[str] = set()
    for pos in price_provider.get_open_positions():
        epic = pos.get("ticker")
        if not epic:
            continue
        ticker = epic_to_ticker(epic)
        if ticker is None:
            log.info(f"Offene Position {epic}: kein Ticker-Gegenstueck, uebersprungen")
            continue
        forced.add(ticker)
    if forced:
        log.info(f"Phase 1c: {len(forced)} Pflicht-Kandidaten aus offenen Positionen: "
                 f"{sorted(forced)}")
    return forced


def _apply_forced_candidates(
    quick_results: list[dict], forced: set[str],
) -> list[dict]:
    """Setzt exclude=False fuer jeden Pflicht-Kandidaten aus Phase 1c, damit
    Phase 3 ihn garantiert analysiert."""
    for q in quick_results:
        if q.get("ticker") in forced:
            q["exclude"] = False
    return quick_results
```

In `run_pipeline()` nach dem `payload["skipped_tickers"]`-Block (ca. Zeile 213) einfügen:

```python
        current_phase = "open_positions"
        # Phase 1c — offene Positionen als Pflicht-Kandidaten (B.4)
        forced = _forced_candidates(price_provider)
```

und den Quick-Filter-Block (ca. Zeile 217) ersetzen durch:

```python
        current_phase = "quick_filter"
        # Phase 2 — quick filter (stocks only)
        quick = quick_filter_batch(
            batch=sp500_tds, trend_context=trend_context,
            cost_tracker=cost_tracker,
        )
        quick = _apply_forced_candidates(quick, forced)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add main.py tests/unit/test_main.py
git commit -m "feat: Phase 1c — offene Positionen als Pflicht-Kandidaten (B.4)"
```

---

### Task 6: Phase 4 vor 4a, Portfolio-Check ohne Websuche

**Files:**
- Modify: `main.py:252-273` (Reihenfolge tauschen)
- Modify: `src/portfolio_check.py` (Signatur `analyses_by_ticker`, `tools=[]`)
- Test: `tests/unit/test_portfolio_check.py`, `tests/unit/test_main.py`

**Interfaces:**
- Consumes: `analyze_assets()`-Ergebnis + `analyze_commodities_and_crypto()`-Ergebnis
- Produces: `check_open_positions(conn, today, run_type, analyses_by_ticker, trend_context, policy_context, cost_tracker) -> list[dict]` — Parameter `snapshots_by_ticker` heisst jetzt `analyses_by_ticker`.

B.5-Entscheidung: Phase 4a bleibt ein Claude-Call, aber **ohne** `web_search`. Input ist
die fertige Phase-3-Analyse plus die Original-These aus der DB.

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_portfolio_check.py` ergänzen:

```python
def test_check_one_position_uses_no_web_search(mocker):
    """B.5: der Portfolio-Check verzichtet auf eine eigene Websuche — die
    Phase-3-Analyse hat die Recherche bereits bezahlt."""
    call = mocker.patch("src.portfolio_check.call_claude")
    call.return_value = MagicMock(
        text='{"action": "HALTEN", "reason": "ok"}',
        model="claude-sonnet-4-6", input_tokens=10, output_tokens=5,
        cache_read_tokens=0, cache_creation_tokens=0, web_search_calls=0,
    )
    from src.portfolio_check import check_one_position
    from src.cost_tracker import CostTracker
    pred = {"id": 1, "ticker": "AAPL", "direction": "long", "entry_price": 178.0,
            "tp_price": 184.0, "sl_price": 176.0}
    check_one_position(
        prediction=pred, current_snapshot={"ticker": "AAPL"},
        trend_context={}, policy_context={}, cost_tracker=CostTracker(),
    )
    assert call.call_args.kwargs["tools"] == []
```

In `tests/unit/test_main.py` den Reihenfolge-Test ergänzen:

```python
def test_ranking_runs_before_portfolio_check(mocker):
    """B.5: Phase 4 vor Phase 4a. Phase 4a soll auf den fertigen
    Phase-3-Analysen arbeiten, nicht auf Rohsnapshots."""
    order: list[str] = []
    mocker.patch("main.rank_and_persist",
                 side_effect=lambda **kw: order.append("ranking") or
                 {"top_long": [], "top_short": [], "commodities_crypto": []})
    mocker.patch("main.check_open_positions",
                 side_effect=lambda **kw: order.append("portfolio") or [])
    # uebrige Phasen wie in test_run_pipeline_calls_phases_in_order mocken
    _mock_all_other_phases(mocker)
    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-30", db_path=":memory:")
    assert order == ["ranking", "portfolio"]
```

> Der Helper `_mock_all_other_phases(mocker)` wird in diesem Task aus dem bestehenden
> `test_run_pipeline_calls_phases_in_order` herausgezogen, damit beide Tests dieselben
> Fakes benutzen. Die Fake-Dicts stehen dort bereits vollständig — nur verschieben,
> nichts neu erfinden.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_portfolio_check.py tests/unit/test_main.py -k "web_search or before_portfolio" -v`
Expected: FAIL — `tools` ist `[WEB_SEARCH_TOOL]`, und `order == ["portfolio", "ranking"]`

- [ ] **Step 3: Write minimal implementation**

In `src/portfolio_check.py`:

```python
from src.utils import call_claude, extract_json_blob   # WEB_SEARCH_TOOL entfernen
```

In `check_one_position()` den Aufruf ändern:

```python
    result = call_claude(
        model=MODEL, system=SYSTEM_PROMPT, user=user_msg,
        max_tokens=MAX_TOKENS, tools=[],
    )
```

Den Modul-Docstring um einen Satz ergänzen:

```
Seit Sprint 3B / Plan 2 (B.5) laeuft der Check OHNE web_search und nach Phase 4:
Input ist die fertige Phase-3-Analyse plus die Original-These aus der DB. Das spart
die Recherchekosten, behaelt aber Urteilsvermoegen und Begruendungstext fuer die Mail.
```

`check_open_positions()`: Parameter `snapshots_by_ticker` in `analyses_by_ticker`
umbenennen (Signatur, Docstring, `snapshot = analyses_by_ticker.get(ticker)`).

In `main.py` die Blöcke 252–273 in dieser Reihenfolge neu setzen:

```python
        current_phase = "ranking"
        # Phase 4 — Ranking + persist predictions (market_ctx kommt aus Phase 0b)
        ranked = rank_and_persist(
            conn=conn, date=date, run_type=run_type,
            stock_analyses=deep_stocks,
            commodity_crypto_analyses=deep_cc,
            market_context=market_ctx,
        )
        payload["top_long"]           = ranked["top_long"]
        payload["top_short"]          = ranked["top_short"]
        payload["commodities_crypto"] = ranked["commodities_crypto"]

        current_phase = "portfolio_check"
        # Phase 4a — Portfolio-Check auf den FERTIGEN Phase-3-Analysen (B.5).
        # Die Mail-Reihenfolge bleibt davon unberuehrt: die Portfolio-Sektion ist
        # weiterhin die erste Sektion der Tagesmail (dokumentierte Invariante).
        analyses_by_ticker = {a["ticker"]: a for a in (deep_stocks + deep_cc)}
        payload["portfolio_recs"] = check_open_positions(
            conn=conn, today=date, run_type=run_type,
            analyses_by_ticker=analyses_by_ticker,
            trend_context=trend_context, policy_context=policy_context,
            cost_tracker=cost_tracker,
        )
```

- [ ] **Step 4: Run the full suite**

Run: `pytest tests/ --cov=src --cov-fail-under=80`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add main.py src/portfolio_check.py tests/
git commit -m "refactor: Phase 4 vor 4a, Portfolio-Check ohne Websuche (B.5)"
```

---

# Schnitt 3 — Sektor-Momentum verdrahten und die weichen Checks

Ziel: `src/sector_momentum.py` ist kein toter Code mehr, die beiden Momentum-Spalten in
`predictions` und `guardrail_rejects` werden befüllt, und alle Checks laufen — in
**beiden** Runs, aber durchweg weich (`enforced=0`). Die harte Durchsetzung kommt in
Schnitt 5.

---

### Task 7: `src/signal_checks.py` — Grundgerüst, relative Stärke, Klumpenrisiko

**Files:**
- Create: `src/signal_checks.py`
- Test: `tests/unit/test_signal_checks.py` *(neu)*

**Interfaces:**
- Consumes: `db.get_ticker_sector()`, `price_history`
- Produces:
  - `signal_checks.CheckResult` — Dataclass mit `rule: str`, `detail: str`, `enforced: bool`
  - `signal_checks.compute_relative_strength(conn, ticker, date) -> float | None`
  - `signal_checks.check_cluster(sector_name, count) -> CheckResult | None`
  - `signal_checks.daily_change_pct(conn, ticker, date) -> float | None`

`CheckResult` existiert nur, wenn ein Check **anschlägt** — ein bestandener Check gibt
`None` zurück und erzeugt keine Zeile. Das entspricht B.3.1: „keines vorhanden → kein
Check, **kein** Log-Eintrag".

- [ ] **Step 1: Write the failing test**

Neue Datei `tests/unit/test_signal_checks.py`:

```python
"""Tests fuer src/signal_checks.py — die rechnerischen B.3-Checks.

Bewusst ohne jedes Mocking: das Modul spricht weder mit Claude noch mit dem Netz.
Faellt hier etwas um, liegt es an der Logik und nicht an einer Fremd-API."""
import pytest

from src import db


def _seed_sector(conn, ticker="AAPL", sector="Technology Hardware", etf="XLK"):
    """Legt einen Sub-Sektor an und ordnet ihm den Ticker zu."""
    db.init_schema(conn)
    sid = conn.execute("SELECT id FROM sectors WHERE name=?", (sector,)).fetchone()["id"]
    conn.execute("INSERT OR REPLACE INTO ticker_sectors (ticker, sector_id) VALUES (?, ?)",
                 (ticker, sid))
    conn.commit()
    return sid


def _bar(conn, ticker, date, close):
    conn.execute(
        "INSERT OR REPLACE INTO price_history (ticker, date, close) VALUES (?, ?, ?)",
        (ticker, date, close))
    conn.commit()


def test_daily_change_pct_uses_the_two_most_recent_bars(in_memory_db):
    db.init_schema(in_memory_db)
    _bar(in_memory_db, "AAPL", "2026-07-29", 100.0)
    _bar(in_memory_db, "AAPL", "2026-07-30", 102.0)
    from src.signal_checks import daily_change_pct
    assert daily_change_pct(in_memory_db, "AAPL", "2026-07-30") == pytest.approx(2.0)


def test_daily_change_pct_ignores_bars_after_the_date(in_memory_db):
    """Sonst misst der 16:10-Lauf gegen einen Kurs, den es noch nicht gab."""
    db.init_schema(in_memory_db)
    _bar(in_memory_db, "AAPL", "2026-07-29", 100.0)
    _bar(in_memory_db, "AAPL", "2026-07-30", 102.0)
    _bar(in_memory_db, "AAPL", "2026-07-31", 200.0)
    from src.signal_checks import daily_change_pct
    assert daily_change_pct(in_memory_db, "AAPL", "2026-07-30") == pytest.approx(2.0)


def test_daily_change_pct_is_none_with_a_single_bar(in_memory_db):
    db.init_schema(in_memory_db)
    _bar(in_memory_db, "AAPL", "2026-07-30", 102.0)
    from src.signal_checks import daily_change_pct
    assert daily_change_pct(in_memory_db, "AAPL", "2026-07-30") is None


def test_relative_strength_is_ticker_minus_sector_etf(in_memory_db):
    """+3% Ticker gegen +1% ETF ergibt +2 Punkte relative Staerke."""
    _seed_sector(in_memory_db)
    _bar(in_memory_db, "AAPL", "2026-07-29", 100.0)
    _bar(in_memory_db, "AAPL", "2026-07-30", 103.0)
    _bar(in_memory_db, "XLK", "2026-07-29", 100.0)
    _bar(in_memory_db, "XLK", "2026-07-30", 101.0)
    from src.signal_checks import compute_relative_strength
    assert compute_relative_strength(
        in_memory_db, "AAPL", "2026-07-30") == pytest.approx(2.0)


def test_relative_strength_is_none_without_sector_mapping(in_memory_db):
    """Grundregel: lieber kein Wert als ein Wert gegen ein fremdes Instrument."""
    db.init_schema(in_memory_db)
    _bar(in_memory_db, "GOOGL", "2026-07-29", 100.0)
    _bar(in_memory_db, "GOOGL", "2026-07-30", 103.0)
    from src.signal_checks import compute_relative_strength
    assert compute_relative_strength(in_memory_db, "GOOGL", "2026-07-30") is None


def test_cluster_check_is_silent_below_the_threshold():
    from src.signal_checks import check_cluster
    assert check_cluster("Semiconductors", 2) is None


def test_cluster_check_warns_at_the_threshold():
    from src.signal_checks import check_cluster
    r = check_cluster("Semiconductors", 3)
    assert r is not None
    assert r.rule == "sector_cluster"
    assert r.enforced is False, "Klumpenrisiko ist immer nur eine Warnung"
    assert "Semiconductors" in r.detail
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_signal_checks.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'src.signal_checks'`

- [ ] **Step 3: Write minimal implementation**

Neue Datei `src/signal_checks.py`:

```python
"""Die rechnerischen Checks aus Sprint 3B / B.3.

Bewusst netzwerk- und Claude-frei: jede Funktion nimmt Werte entgegen, die
anderswo bereits erhoben wurden (Markt-Kontext aus Phase 0b, Sektor-Momentum aus
Phase 1d, Kurse aus price_history), und gibt ein Urteil zurueck. Dadurch ist das
Modul ohne Mocking testbar.

Ein Check, der NICHT anschlaegt, gibt None zurueck und erzeugt keine Zeile — das
ist B.3.1 woertlich: "keines vorhanden -> kein Check, kein Log-Eintrag".

Ob ein anschlagender Check das Signal auch blockiert, entscheidet NICHT dieses
Modul, sondern der Aufrufer ueber den enforce-Parameter (Entscheidung E4):
run_pipeline() uebergibt False, run_trade_proposals() uebergibt True."""
import logging
import sqlite3
from dataclasses import dataclass

import config
from src import db

log = logging.getLogger("shares_future.signal_checks")


@dataclass(frozen=True)
class CheckResult:
    """Ein angeschlagener Check. `enforced=True` heisst: das Signal wird verworfen;
    `False` heisst: Warnung in der Mail, Signal geht durch."""
    rule: str
    detail: str
    enforced: bool


def daily_change_pct(
    conn: sqlite3.Connection, ticker: str, date: str,
) -> float | None:
    """Tagesperformance in Prozent aus den letzten zwei Bars bis einschliesslich
    `date`. None, wenn weniger als zwei Bars vorliegen oder der Vortagesschluss 0 ist."""
    rows = conn.execute(
        """SELECT close FROM price_history
           WHERE ticker = ? AND date <= ?
           ORDER BY date DESC LIMIT 2""",
        (ticker, date),
    ).fetchall()
    if len(rows) < 2:
        return None
    cur, prev = float(rows[0]["close"]), float(rows[1]["close"])
    if prev <= 0:
        return None
    return (cur - prev) / prev * 100.0


def compute_relative_strength(
    conn: sqlite3.Connection, ticker: str, date: str,
) -> float | None:
    """Tagesperformance des Tickers minus die seines Sub-Sektor-ETF, in
    Prozentpunkten. None, wenn der Ticker keinem Sub-Sektor zugeordnet ist oder
    einer der beiden Werte fehlt.

    Kein Score und kein Guardrail (die 8-Dimensionen-Gewichtung ist eingefroren):
    der Wert geht als Input in den Re-Validierungs-Prompt und als Spalte in die Mail."""
    sector = db.get_ticker_sector(conn, ticker)
    if sector is None:
        return None
    own = daily_change_pct(conn, ticker, date)
    etf = daily_change_pct(conn, sector["etf"], date)
    if own is None or etf is None:
        return None
    return own - etf


def check_cluster(sector_name: str | None, count: int) -> CheckResult | None:
    """Warnt, wenn ab config.SECTOR_CLUSTER_WARN_AT Signale im selben Sub-Sektor
    liegen. Immer weich: Klumpenrisiko ist eine Positionsgroessen-Frage, keine
    Aussage ueber die Qualitaet des einzelnen Setups."""
    if sector_name is None or count < config.SECTOR_CLUSTER_WARN_AT:
        return None
    return CheckResult(
        rule="sector_cluster",
        detail=f"{count} Signale im Sub-Sektor {sector_name} — Klumpenrisiko",
        enforced=False,
    )
```

In `config.py` bei den übrigen Schwellenwerten ergänzen:

```python
# Sprint 3B / Plan 2 (B.3): ab wie vielen Signalen im selben Sub-Sektor die Mail
# vor Klumpenrisiko warnt. Reine Warnung, blockiert nie.
SECTOR_CLUSTER_WARN_AT = 3
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_signal_checks.py -v`
Expected: PASS (8 Tests)

- [ ] **Step 5: Commit**

```bash
git add src/signal_checks.py config.py tests/unit/test_signal_checks.py
git commit -m "feat: signal_checks mit relativer Staerke und Klumpen-Check (B.3)"
```

---

### Task 8: VIX-Regel, D9-Guardrail und der `enforce`-Schalter

**Files:**
- Modify: `src/signal_checks.py`
- Modify: `config.py`
- Test: `tests/unit/test_signal_checks.py`

**Interfaces:**
- Consumes: `CheckResult` (Task 7)
- Produces:
  - `signal_checks.check_vix(direction, confidence, vix_level, enforce) -> CheckResult | None`
  - `signal_checks.check_sector_momentum(direction, etf_momentum, db_momentum, enforce) -> CheckResult | None`
  - `signal_checks.blocks(results: list[CheckResult]) -> bool`

Das ist der Task, der **E4 festnagelt**: derselbe Check liefert bei `enforce=False` ein
`CheckResult` mit `enforced=False` und bei `enforce=True` eines mit `enforced=True`.

D9-Logik nach B.3.1 — verglichen wird die **Richtung**, nie der Betrag:

| Lage | Verhalten |
|---|---|
| beide vorhanden, gleiches Vorzeichen, **stützt** die Richtung | kein Check, kein Eintrag |
| beide vorhanden, gleiches Vorzeichen, **widerspricht** der Richtung | `enforced = enforce and SECTOR_GUARDRAIL_STRICT` |
| beide vorhanden, **widersprüchliche Vorzeichen** | weiche Warnung, immer `enforced=False` |
| nur eines vorhanden, widerspricht | weiche Warnung, immer `enforced=False` |
| nur eines vorhanden, stützt | kein Check |
| keines vorhanden | kein Check, kein Eintrag |

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_signal_checks.py` ergänzen:

```python
# ---------- VIX (B.3, hartes Filterkriterium) ----------

def test_vix_below_thresholds_is_silent():
    from src.signal_checks import check_vix
    assert check_vix("long", "medium", 18.0, enforce=True) is None


def test_vix_above_35_blocks_new_longs():
    from src.signal_checks import check_vix
    r = check_vix("long", "high", 40.0, enforce=True)
    assert r is not None and r.rule == "vix_no_new_longs" and r.enforced is True


def test_vix_above_35_leaves_shorts_alone():
    """Die Regel lautet 'keine neuen LONG-Signale' — Shorts sind nicht gemeint."""
    from src.signal_checks import check_vix
    assert check_vix("short", "medium", 40.0, enforce=True) is None


def test_vix_between_25_and_35_blocks_only_low_confidence():
    from src.signal_checks import check_vix
    assert check_vix("long", "high", 28.0, enforce=True) is None
    r = check_vix("long", "medium", 28.0, enforce=True)
    assert r is not None and r.rule == "vix_high_confidence_only"


def test_vix_is_silent_when_the_level_is_unknown():
    """Phase 0b darf ausfallen — dann filtert der VIX-Check eben nicht."""
    from src.signal_checks import check_vix
    assert check_vix("long", "medium", None, enforce=True) is None


# ---------- E4: derselbe Check, zwei Runs ----------

def test_same_check_blocks_only_when_enforce_is_true():
    """Entscheidung E4 in einem Test: pre_market erhebt und warnt,
    trade_proposals setzt durch."""
    from src.signal_checks import check_vix
    weich = check_vix("long", "medium", 40.0, enforce=False)
    hart = check_vix("long", "medium", 40.0, enforce=True)
    assert weich is not None and hart is not None
    assert weich.rule == hart.rule, "gleicher Befund"
    assert weich.enforced is False and hart.enforced is True


# ---------- D9: Sektor-Momentum (B.3.1) ----------

def test_d9_silent_when_both_signals_support_the_direction():
    from src.signal_checks import check_sector_momentum
    assert check_sector_momentum("long", 1.2, 0.8, enforce=True) is None


def test_d9_silent_when_no_signal_exists():
    """B.3.1 woertlich: 'keines vorhanden -> kein Check, KEIN Log-Eintrag'."""
    from src.signal_checks import check_sector_momentum
    assert check_sector_momentum("long", None, None, enforce=True) is None


def test_d9_hard_only_when_both_agree_and_strict_is_on(monkeypatch):
    import config
    from src.signal_checks import check_sector_momentum
    monkeypatch.setattr(config, "SECTOR_GUARDRAIL_STRICT", True)
    r = check_sector_momentum("long", -1.5, -0.9, enforce=True)
    assert r is not None and r.rule == "sector_momentum" and r.enforced is True


def test_d9_stays_soft_while_strict_is_off(monkeypatch):
    import config
    from src.signal_checks import check_sector_momentum
    monkeypatch.setattr(config, "SECTOR_GUARDRAIL_STRICT", False)
    r = check_sector_momentum("long", -1.5, -0.9, enforce=True)
    assert r is not None and r.enforced is False


def test_d9_conflicting_signals_stay_soft_even_with_strict(monkeypatch):
    """Widerspruechliche Signale duerfen NIE hart blocken — auch nicht mit STRICT."""
    import config
    from src.signal_checks import check_sector_momentum
    monkeypatch.setattr(config, "SECTOR_GUARDRAIL_STRICT", True)
    r = check_sector_momentum("long", -1.5, +0.9, enforce=True)
    assert r is not None and r.rule == "sector_momentum_conflict"
    assert r.enforced is False


def test_d9_single_signal_stays_soft_even_with_strict(monkeypatch):
    """Der MVP-Normalfall: 19 von 21 Sub-Sektoren haben nur das ETF-Signal."""
    import config
    from src.signal_checks import check_sector_momentum
    monkeypatch.setattr(config, "SECTOR_GUARDRAIL_STRICT", True)
    r = check_sector_momentum("long", -1.5, None, enforce=True)
    assert r is not None and r.rule == "sector_momentum_partial"
    assert r.enforced is False


def test_d9_compares_direction_not_magnitude(monkeypatch):
    """Live-Befund 2026-07-28: Retail lag bei +2,89% ETF gegen +1,17% DB.
    Faktor ~2,5 bei gleichem Vorzeichen ist KEIN Widerspruch."""
    import config
    from src.signal_checks import check_sector_momentum
    monkeypatch.setattr(config, "SECTOR_GUARDRAIL_STRICT", True)
    assert check_sector_momentum("long", 2.89, 1.17, enforce=True) is None


def test_blocks_is_true_only_for_enforced_results():
    from src.signal_checks import CheckResult, blocks
    assert blocks([CheckResult("a", "x", enforced=False)]) is False
    assert blocks([CheckResult("a", "x", enforced=False),
                   CheckResult("b", "y", enforced=True)]) is True
    assert blocks([]) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_signal_checks.py -v`
Expected: FAIL mit `ImportError: cannot import name 'check_vix'`

- [ ] **Step 3: Write minimal implementation**

In `config.py` ergänzen:

```python
# Sprint 3B / Plan 2 (B.3): VIX-Schwellen. Ueber HIGH_CONFIDENCE_ONLY gehen nur
# noch Signale mit confidence='high' durch, ueber NO_NEW_LONGS gar keine Longs mehr.
VIX_HIGH_CONFIDENCE_ONLY = 25.0
VIX_NO_NEW_LONGS = 35.0

# D9 (B.3.1): solange False, blockiert der Sektor-Guardrail nie — er schreibt nur
# guardrail_rejects-Zeilen mit enforced=0. Erst auf True stellen, wenn die
# Sub-Sektor-Mapping-Abdeckung in der Weekly-Mail stabil hoch ist.
SECTOR_GUARDRAIL_STRICT = False
```

In `src/signal_checks.py` ergänzen:

```python
def blocks(results: list[CheckResult]) -> bool:
    """True, wenn mindestens ein Check das Signal tatsaechlich verwirft."""
    return any(r.enforced for r in results)


def check_vix(
    direction: str, confidence: str | None, vix_level: float | None, *,
    enforce: bool,
) -> CheckResult | None:
    """VIX-Filter aus B.3. Ueber VIX_NO_NEW_LONGS keine neuen Long-Signale mehr,
    ueber VIX_HIGH_CONFIDENCE_ONLY nur noch confidence='high'.

    Faellt Phase 0b aus und bleibt vix_level None, filtert der Check nicht — ein
    fehlender Messwert ist kein Grund, alle Signale zu verwerfen."""
    if vix_level is None:
        return None
    if vix_level > config.VIX_NO_NEW_LONGS and direction == "long":
        return CheckResult(
            rule="vix_no_new_longs",
            detail=f"VIX {vix_level:.1f} > {config.VIX_NO_NEW_LONGS:.0f} — "
                   f"keine neuen Long-Signale",
            enforced=enforce,
        )
    if vix_level > config.VIX_HIGH_CONFIDENCE_ONLY and confidence != "high":
        return CheckResult(
            rule="vix_high_confidence_only",
            detail=f"VIX {vix_level:.1f} > {config.VIX_HIGH_CONFIDENCE_ONLY:.0f} — "
                   f"nur confidence='high', hier '{confidence}'",
            enforced=enforce,
        )
    return None


def _supports(direction: str, momentum: float) -> bool:
    """True, wenn das Sektor-Momentum in dieselbe Richtung zeigt wie der Trade."""
    return momentum > 0 if direction == "long" else momentum < 0


def check_sector_momentum(
    direction: str, etf_momentum: float | None, db_momentum: float | None, *,
    enforce: bool,
) -> CheckResult | None:
    """D9-Guardrail nach B.3.1. Verglichen wird die RICHTUNG, nie der Betrag.

    Der Live-Lauf vom 2026-07-28 zeigt Abweichungen um Faktor ~2,5 zwischen ETF-
    und DB-Signal bei identischem Vorzeichen (Retail +2,89% gegen +1,17%): XRT ist
    gleichgewichtet und small-cap-lastig, unsere Retail-Ticker sind AMZN/WMT/HD.
    Ein Schwellenwert auf der Differenz waere damit reines Rauschen.

    Hart verworfen wird nur, wenn BEIDE Signale vorliegen, in dieselbe Richtung
    zeigen, der Trade-Richtung widersprechen — und SECTOR_GUARDRAIL_STRICT an ist."""
    if etf_momentum is None and db_momentum is None:
        return None

    if etf_momentum is not None and db_momentum is not None:
        if (etf_momentum > 0) != (db_momentum > 0):
            return CheckResult(
                rule="sector_momentum_conflict",
                detail=f"Sektor-Momentum widerspruechlich: ETF {etf_momentum:+.2f}%, "
                       f"DB {db_momentum:+.2f}%",
                enforced=False,
            )
        if _supports(direction, etf_momentum):
            return None
        return CheckResult(
            rule="sector_momentum",
            detail=f"Beide Sektor-Signale gegen {direction}: "
                   f"ETF {etf_momentum:+.2f}%, DB {db_momentum:+.2f}%",
            enforced=enforce and config.SECTOR_GUARDRAIL_STRICT,
        )

    value = etf_momentum if etf_momentum is not None else db_momentum
    source = "ETF" if etf_momentum is not None else "DB"
    if _supports(direction, value):
        return None
    return CheckResult(
        rule="sector_momentum_partial",
        detail=f"Nur das {source}-Signal vorhanden ({value:+.2f}%) und gegen "
               f"{direction} — kein Gegencheck moeglich",
        enforced=False,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_signal_checks.py -v`
Expected: PASS (alle Tests aus Task 7 + 14 neue)

- [ ] **Step 5: Commit**

```bash
git add src/signal_checks.py config.py tests/unit/test_signal_checks.py
git commit -m "feat: VIX-Filter und D9-Guardrail mit enforce-Schalter (B.3, E4)"
```

---

### Task 9: Phase 1d — `collect_sector_momentum()` verdrahten

**Files:**
- Modify: `main.py` — Import + Aufruf in `run_pipeline()` nach Phase 1c
- Test: `tests/unit/test_main.py`

**Interfaces:**
- Consumes: `src.sector_momentum.collect_sector_momentum(conn, date, run_type, price_provider)`
- Produces: `sector_mom: dict[int, dict]` im Ablauf von `run_pipeline()` — Task 10 liest es.

`src/sector_momentum.py` wurde in Plan 1 gebaut, aber von niemandem aufgerufen. Dieser
Task hängt es ein. Es muss **nach** Phase 1 laufen: `db_momentum` mittelt die heutigen
Bars aus `price_history`, die Phase 1 erst schreibt.

- [ ] **Step 1: Write the failing test**

```python
def test_sector_momentum_is_collected_after_data_collection(mocker):
    """Plan 1 hat collect_sector_momentum gebaut, aber nie aufgerufen. Ohne
    diesen Test faellt ein spaeteres Herausfallen nicht auf."""
    order: list[str] = []
    mocker.patch("main.collect",
                 side_effect=lambda **kw: order.append("collect") or ([], 0))
    mocker.patch("main.collect_sector_momentum",
                 side_effect=lambda **kw: order.append("sector_momentum") or {})
    _mock_all_other_phases(mocker)
    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-30", db_path=":memory:")
    assert "sector_momentum" in order, "Phase 1d laeuft gar nicht"
    assert order.index("collect") < order.index("sector_momentum"), (
        "db_momentum mittelt die heutigen Bars — die schreibt erst Phase 1"
    )


def test_sector_momentum_failure_does_not_abort_the_run(mocker):
    """Ein Sektor-ETF-Ausfall darf keinen 3-EUR-Lauf kosten."""
    mocker.patch("main.collect_sector_momentum", side_effect=RuntimeError("boom"))
    _mock_all_other_phases(mocker)
    mocker.patch("main.collect", return_value=([], 0))
    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-30", db_path=":memory:")
    # kein raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_main.py -k sector_momentum -v`
Expected: FAIL — `main` hat kein Attribut `collect_sector_momentum`

- [ ] **Step 3: Write minimal implementation**

In `main.py` bei den übrigen `src`-Imports:

```python
from src.sector_momentum import collect_sector_momentum
```

In `run_pipeline()` direkt nach dem Phase-1c-Block einfügen:

```python
        current_phase = "sector_momentum"
        # Phase 1d — beide Momentum-Signale je Sub-Sektor (B.3.1 / D9). Muss NACH
        # Phase 1 laufen: db_momentum mittelt die heutigen Bars aus price_history.
        # Nicht fatal — ein ETF-Ausfall darf keinen bezahlten Lauf kosten.
        sector_mom: dict[int, dict] = {}
        try:
            sector_mom = collect_sector_momentum(
                conn=conn, date=date, run_type=run_type,
                price_provider=price_provider,
            )
        except CostCapExceeded:
            # Muss vor dem blanken except stehen, sonst frisst der Auffang-Zweig
            # den Kosten-Abbruch und der Lauf laeuft ueber den Deckel hinaus weiter.
            raise
        except Exception as e:
            log.warning(f"Sektor-Momentum nicht ermittelbar, Run laeuft ohne: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add main.py tests/unit/test_main.py
git commit -m "feat: Phase 1d — Sektor-Momentum verdrahten (D9, war toter Code)"
```

---

### Task 10: Momentum-Spalten befüllen und die Checks weich laufen lassen

**Files:**
- Modify: `src/db.py` — `save_prediction()` und `log_guardrail_reject()` um die zwei Momentum-Spalten erweitern
- Modify: `src/ranking.py` — Checks ausführen, Ergebnisse persistieren
- Modify: `main.py` — `sector_mom` an `rank_and_persist()` durchreichen
- Test: `tests/unit/test_db.py`, `tests/unit/test_ranking.py`

**Interfaces:**
- Consumes: `signal_checks.check_sector_momentum/check_vix/check_cluster/compute_relative_strength` (Tasks 7–8), `sector_mom` (Task 9)
- Produces:
  - `signal_checks.momentum_for(conn, ticker, sector_momentum) -> tuple[float | None, float | None]`
  - `signal_checks.cluster_counts(conn, tickers: list[str]) -> dict[str, int]`
  - `ranking.rank_and_persist(conn, date, run_type, stock_analyses, commodity_crypto_analyses, market_context, sector_momentum, enforce_checks=False) -> dict`

  Task 13 nutzt alle drei aus dem 16:10-Lauf.

> **Wichtig:** `save_prediction()` und `log_guardrail_reject()` führen ihre Spalten in
> einer expliziten `cols`-Liste. Die beiden Momentum-Spalten existieren zwar im Schema,
> stehen aber in **keiner** der beiden Listen — genau deshalb wurden sie bisher nie
> befüllt. Beide Listen müssen ergänzt werden, nicht nur eine.

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_db.py` ergänzen:

```python
def test_save_prediction_persists_sector_momentum(in_memory_db):
    """Die Spalten existierten seit Plan 1, wurden aber nie geschrieben."""
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market", "ticker": "AAPL",
        "direction": "long", "sector_etf_momentum": -1.5, "sector_db_momentum": -0.9,
    })
    row = in_memory_db.execute(
        "SELECT sector_etf_momentum, sector_db_momentum FROM predictions WHERE id=?",
        (pid,)).fetchone()
    assert row["sector_etf_momentum"] == -1.5
    assert row["sector_db_momentum"] == -0.9


def test_log_guardrail_reject_persists_sector_momentum(in_memory_db):
    db.init_schema(in_memory_db)
    db.log_guardrail_reject(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market", "ticker": "AAPL",
        "direction": "long", "rule": "sector_momentum", "detail": "x",
        "enforced": 0, "sector_etf_momentum": -1.5, "sector_db_momentum": -0.9,
    })
    row = in_memory_db.execute(
        "SELECT sector_etf_momentum, sector_db_momentum FROM guardrail_rejects"
    ).fetchone()
    assert row["sector_etf_momentum"] == -1.5
    assert row["sector_db_momentum"] == -0.9
```

Neue Tests in `tests/unit/test_ranking.py`:

```python
def _seed_sector_for(conn, ticker="AAPL", sector="Technology Hardware"):
    sid = conn.execute("SELECT id FROM sectors WHERE name=?", (sector,)).fetchone()["id"]
    conn.execute("INSERT OR REPLACE INTO ticker_sectors (ticker, sector_id) VALUES (?,?)",
                 (ticker, sid))
    conn.commit()
    return sid


def test_ranking_writes_sector_momentum_onto_the_prediction(in_memory_db, valid_analysis):
    """3D kann die Korrelation nur ueber predictions rechnen — verworfene Signale
    haben nie ein Outcome."""
    db.init_schema(in_memory_db)
    sid = _seed_sector_for(in_memory_db)
    from src.ranking import rank_and_persist
    rank_and_persist(
        conn=in_memory_db, date="2026-07-30", run_type="pre_market",
        stock_analyses=[valid_analysis], commodity_crypto_analyses=[],
        market_context={}, sector_momentum={sid: {"etf_momentum": 1.2,
                                                  "db_momentum": 0.8,
                                                  "ticker_count": 4}},
    )
    row = in_memory_db.execute(
        "SELECT sector_etf_momentum, sector_db_momentum FROM predictions").fetchone()
    assert row["sector_etf_momentum"] == 1.2
    assert row["sector_db_momentum"] == 0.8


def test_soft_check_writes_reject_row_but_keeps_the_signal(in_memory_db, valid_analysis):
    """E4: pre_market erhebt und warnt, blockiert aber nicht."""
    db.init_schema(in_memory_db)
    sid = _seed_sector_for(in_memory_db)
    from src.ranking import rank_and_persist
    out = rank_and_persist(
        conn=in_memory_db, date="2026-07-30", run_type="pre_market",
        stock_analyses=[valid_analysis], commodity_crypto_analyses=[],
        market_context={"vix_level": 40.0},
        sector_momentum={sid: {"etf_momentum": -1.2, "db_momentum": None,
                               "ticker_count": 1}},
        enforce_checks=False,
    )
    assert len(out["top_long"]) == 1, "weicher Check darf nicht blockieren"
    rejects = in_memory_db.execute(
        "SELECT rule, enforced FROM guardrail_rejects").fetchall()
    rules = {r["rule"] for r in rejects}
    assert "vix_no_new_longs" in rules
    assert "sector_momentum_partial" in rules
    assert all(r["enforced"] == 0 for r in rejects)


def test_no_reject_row_when_no_check_fires(in_memory_db, valid_analysis):
    """B.3.1: kein Signal vorhanden -> kein Check, KEIN Log-Eintrag."""
    db.init_schema(in_memory_db)
    from src.ranking import rank_and_persist
    rank_and_persist(
        conn=in_memory_db, date="2026-07-30", run_type="pre_market",
        stock_analyses=[valid_analysis], commodity_crypto_analyses=[],
        market_context={}, sector_momentum={},
    )
    n = in_memory_db.execute(
        "SELECT COUNT(*) AS n FROM guardrail_rejects").fetchone()["n"]
    assert n == 0
```

> `valid_analysis` ist eine neue Fixture in `tests/unit/test_ranking.py` — ein
> guardrail-taugliches Analyse-Dict für AAPL long. Die bestehenden Ranking-Tests bauen
> dieses Dict bereits inline; in diesem Task wird es einmal als Fixture herausgezogen
> und von den bestehenden Tests mitbenutzt.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_db.py tests/unit/test_ranking.py -k "sector_momentum or soft_check or no_reject" -v`
Expected: FAIL — die Spalten bleiben `None`, und `rank_and_persist()` kennt `sector_momentum` nicht

- [ ] **Step 3: Write minimal implementation**

In `src/db.py`, `save_prediction()` — die `cols`-Liste am Ende ergänzen:

```python
        "hold_days_recommended", "intraday_range_pct",
        # D9 (Plan 2 / Task 10): standen seit Plan 1 im Schema, aber nicht in
        # dieser Liste — deshalb blieben sie bis hierher immer NULL.
        "sector_etf_momentum", "sector_db_momentum",
    ]
```

In `log_guardrail_reject()` ebenso:

```python
    cols = ["date", "run_type", "ticker", "direction", "rule", "detail", "enforced",
            "sector_etf_momentum", "sector_db_momentum"]
```

**Erst `src/signal_checks.py` ergänzen.** Die beiden folgenden Funktionen gehören dorthin
und **nicht** nach `ranking.py`: `main.py` braucht sie in Task 13 im 16:10-Lauf ebenfalls,
und ein modulübergreifender Import privater Namen (`from src.ranking import _momentum_for`)
wäre genau die Falle, die beim nächsten Refactoring reisst.

```python
def momentum_for(
    conn: sqlite3.Connection, ticker: str, sector_momentum: dict[int, dict],
) -> tuple[float | None, float | None]:
    """Liefert (etf_momentum, db_momentum) fuer den Sub-Sektor des Tickers.
    (None, None), wenn der Ticker keinem Sub-Sektor zugeordnet ist."""
    sector = db.get_ticker_sector(conn, ticker)
    if sector is None:
        return None, None
    entry = sector_momentum.get(sector["sector_id"]) or {}
    return entry.get("etf_momentum"), entry.get("db_momentum")


def cluster_counts(
    conn: sqlite3.Connection, tickers: list[str],
) -> dict[str, int]:
    """Zaehlt, wie viele der uebergebenen Ticker je Sub-Sektor anfallen —
    Grundlage fuer die Klumpenrisiko-Warnung. Ungemappte Ticker zaehlen nicht mit."""
    counts: dict[str, int] = {}
    for t in tickers:
        sector = db.get_ticker_sector(conn, t)
        if sector is None:
            continue
        counts[sector["name"]] = counts.get(sector["name"], 0) + 1
    return counts
```

Dann in `src/ranking.py` importieren und ergänzen:

```python
from src import signal_checks
from src.signal_checks import momentum_for, cluster_counts
```

```python
def _run_checks(
    analysis: dict, conn, date: str, run_type: str,
    market_context: dict, sector_momentum: dict[int, dict],
    cluster_counts: dict[str, int], enforce: bool,
) -> list[signal_checks.CheckResult]:
    """Fuehrt die B.3-Checks fuer EINE Analyse aus und persistiert jeden
    angeschlagenen Check als guardrail_rejects-Zeile — mit dem Momentum-Snapshot,
    damit 3D auswerten kann, ob die weichen Warnungen richtig lagen.

    Gibt die angeschlagenen Checks zurueck; ob sie blockieren, entscheidet der
    Aufrufer ueber signal_checks.blocks()."""
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

`_to_prediction_row()` bekommt zwei Parameter und zwei Felder:

```python
def _to_prediction_row(
    analysis: dict, date: str, run_type: str, market_context: dict, conn,
    etf_momentum: float | None = None, db_momentum: float | None = None,
) -> dict:
```

und im zurückgegebenen Dict, direkt vor `"learnable": True`:

```python
        "sector_etf_momentum": etf_momentum,
        "sector_db_momentum": db_momentum,
```

`rank_and_persist()` bekommt die neue Signatur und den Check-Durchlauf:

```python
def rank_and_persist(
    conn,
    date: str,
    run_type: str,
    stock_analyses: list[dict],
    commodity_crypto_analyses: list[dict],
    market_context: dict,
    sector_momentum: dict[int, dict] | None = None,
    enforce_checks: bool = False,
) -> dict:
    """Returns {top_long, top_short, commodities_crypto} und schreibt je Auswahl
    eine predictions-Zeile.

    `enforce_checks` steuert Entscheidung E4: run_pipeline() uebergibt False
    (erheben und warnen), run_trade_proposals() uebergibt True (durchsetzen)."""
    sector_momentum = sector_momentum or {}
    kept_stocks = _guardrail_filter(stock_analyses, conn, date, run_type)
    kept_cc     = _guardrail_filter(commodity_crypto_analyses, conn, date, run_type)

    counts = cluster_counts(conn, [a["ticker"] for a in kept_stocks])
    surviving: list[dict] = []
    for a in kept_stocks:
        results = _run_checks(
            a, conn, date, run_type, market_context, sector_momentum,
            counts, enforce_checks,
        )
        if signal_checks.blocks(results):
            log.info(f"{a['ticker']}: durch B.3-Check verworfen "
                     f"({', '.join(r.rule for r in results if r.enforced)})")
            continue
        surviving.append(a)

    longs  = sorted(
        [a for a in surviving if a["direction"] == "long"],
        key=lambda a: a.get("probability_pct") or 0, reverse=True,
    )[:TOP_N]
    shorts = sorted(
        [a for a in surviving if a["direction"] == "short"],
        key=lambda a: a.get("probability_pct") or 0, reverse=True,
    )[:TOP_N]

    for a in (*longs, *shorts, *kept_cc):
        etf_mom, db_mom = momentum_for(conn, a["ticker"], sector_momentum)
        db.save_prediction(conn, _to_prediction_row(
            a, date=date, run_type=run_type, market_context=market_context,
            conn=conn, etf_momentum=etf_mom, db_momentum=db_mom,
        ))

    log.info(
        f"Phase 4 done: {len(longs)} long, {len(shorts)} short, "
        f"{len(kept_cc)} commodity/crypto persisted"
    )
    return {"top_long": longs, "top_short": shorts, "commodities_crypto": kept_cc}
```

In `main.py` den `rank_and_persist()`-Aufruf um `sector_momentum=sector_mom` ergänzen
(`enforce_checks` bleibt beim Default `False` — `pre_market` warnt nur).

- [ ] **Step 4: Run the full suite**

Run: `pytest tests/ --cov=src --cov-fail-under=80`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/db.py src/ranking.py main.py tests/
git commit -m "feat: Momentum-Spalten befuellen, B.3-Checks weich in beiden Runs (E4)"
```

---

# Schnitt 4 — `trade_proposals` inhaltlich

Ziel: Der 16:10-Lauf prüft die Morgensignale billig nach, löst die `pre_market`-Zeile ab
und verschickt die Vorher/Nachher-Mail.

---

### Task 11: `superseded_by` und `revision_verdict` in `predictions`

**Files:**
- Modify: `src/db.py` — Schema, `_apply_migrations()`, zwei neue Funktionen
- Test: `tests/unit/test_db.py`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `db.record_revision(conn, pred_id, verdict, superseded_by=None) -> None`
  - `db.load_predictions_for_revalidation(conn, date) -> list[sqlite3.Row]`

**Warum `revision_verdict` auf der `pre_market`-Zeile sitzt:** In drei von sechs Ausgängen
(`gedreht`, `verworfen`, Fehlerfall) entsteht gar keine neue Zeile. Auf der neuen Zeile
wäre das Urteil dort schlicht nirgends. B.9s Veränderungs-Statistik wird so ein simples
`GROUP BY revision_verdict`.

- [ ] **Step 1: Write the failing test**

```python
# ---------- E3: Ablösung statt Dopplung ----------

def test_predictions_has_supersede_columns(in_memory_db):
    db.init_schema(in_memory_db)
    cols = {r["name"] for r in in_memory_db.execute(
        "PRAGMA table_info(predictions)").fetchall()}
    assert {"superseded_by", "revision_verdict"}.issubset(cols)


def test_migration_adds_supersede_columns_to_an_existing_db(tmp_db_path):
    """Migration gegen eine DB, die die Spalten noch nicht kennt (Regel 5)."""
    import sqlite3
    conn = sqlite3.connect(tmp_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
        run_type TEXT NOT NULL, ticker TEXT NOT NULL, direction TEXT NOT NULL,
        status TEXT DEFAULT 'open', learnable BOOLEAN DEFAULT 1)""")
    conn.commit()
    db.init_schema(conn)
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(predictions)").fetchall()}
    assert {"superseded_by", "revision_verdict"}.issubset(cols)
    conn.close()


def test_record_revision_with_successor_marks_superseded(in_memory_db):
    db.init_schema(in_memory_db)
    old = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "long"})
    new = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "trade_proposals",
        "ticker": "AAPL", "direction": "long"})
    db.record_revision(in_memory_db, old, verdict="bestaetigt", superseded_by=new)
    row = in_memory_db.execute(
        "SELECT status, superseded_by, revision_verdict FROM predictions WHERE id=?",
        (old,)).fetchone()
    assert row["status"] == "superseded"
    assert row["superseded_by"] == new
    assert row["revision_verdict"] == "bestaetigt"


def test_record_revision_without_successor_keeps_it_open(in_memory_db):
    """E5: ein gedrehtes Signal bleibt offen und wird regulaer ausgewertet —
    genau das beantwortet, ob die Drehung richtig lag."""
    db.init_schema(in_memory_db)
    pid = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "long"})
    db.record_revision(in_memory_db, pid, verdict="gedreht")
    row = in_memory_db.execute(
        "SELECT status, superseded_by, revision_verdict FROM predictions WHERE id=?",
        (pid,)).fetchone()
    assert row["status"] == "open"
    assert row["superseded_by"] is None
    assert row["revision_verdict"] == "gedreht"


def test_superseded_predictions_are_invisible_to_the_evaluator(in_memory_db):
    """Der Kern von E3: eine Trade-Idee, genau EIN Outcome. Ohne das zaehlt
    jede Kennzahl doppelt."""
    db.init_schema(in_memory_db)
    old = db.save_prediction(in_memory_db, {
        "date": "2026-07-29", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "long"})
    new = db.save_prediction(in_memory_db, {
        "date": "2026-07-29", "run_type": "trade_proposals",
        "ticker": "AAPL", "direction": "long"})
    db.record_revision(in_memory_db, old, verdict="bestaetigt", superseded_by=new)
    open_ids = {r["id"] for r in db.load_open_predictions(in_memory_db)}
    assert open_ids == {new}
    within = {r["id"] for r in db.load_open_predictions_within_max_age_days(
        in_memory_db, today="2026-07-30")}
    assert within == {new}, "auch Phase 4a darf den Ticker nur einmal sehen"


def test_load_predictions_for_revalidation_is_scoped(in_memory_db):
    db.init_schema(in_memory_db)
    keep = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "long"})
    db.save_prediction(in_memory_db, {          # falscher Tag
        "date": "2026-07-29", "run_type": "pre_market",
        "ticker": "MSFT", "direction": "long"})
    db.save_prediction(in_memory_db, {          # falscher run_type
        "date": "2026-07-30", "run_type": "trade_proposals",
        "ticker": "NVDA", "direction": "long"})
    rows = db.load_predictions_for_revalidation(in_memory_db, "2026-07-30")
    assert {r["id"] for r in rows} == {keep}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_db.py -k "supersede or revision or revalidation" -v`
Expected: FAIL — Spalten fehlen, `db.record_revision` existiert nicht

- [ ] **Step 3: Write minimal implementation**

Im `SCHEMA_SQL`-Block für `predictions` (nach `hold_days_recommended INTEGER, intraday_range_pct REAL,`) ergänzen:

```sql
    superseded_by INTEGER REFERENCES predictions(id),
    revision_verdict TEXT,
```

In `_apply_migrations()` beim `pred_cols`-Block ergänzen:

```python
    # E3 (Plan 2): der 16:10-Lauf loest die pre_market-Zeile ab, statt eine
    # zweite offene Zeile daneben zu legen. Ohne das schliesst der Evaluator
    # beide und jede Kennzahl zaehlt doppelt.
    if "superseded_by" not in pred_cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN superseded_by INTEGER")
    if "revision_verdict" not in pred_cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN revision_verdict TEXT")
```

Zwei neue Funktionen in `src/db.py`:

```python
def record_revision(
    conn: sqlite3.Connection, pred_id: int, verdict: str,
    superseded_by: int | None = None,
) -> None:
    """Schreibt das Urteil des 16:10-Laufs auf die pre_market-Zeile (E3).

    Mit `superseded_by` wird die Zeile abgeloest: status='superseded', damit der
    Evaluator und Phase 4a sie nicht mehr sehen — beide filtern auf status='open'.
    Ohne `superseded_by` (Urteil 'gedreht' oder 'verworfen') bleibt sie offen und
    wird regulaer ausgewertet; nur so laesst sich messen, ob die Ablehnung richtig lag.

    Das Urteil sitzt bewusst auf der ALTEN Zeile: in drei von sechs Ausgaengen
    entsteht gar keine neue, dort waere es sonst nirgends."""
    if superseded_by is None:
        conn.execute(
            "UPDATE predictions SET revision_verdict = ? WHERE id = ?",
            (verdict, pred_id),
        )
    else:
        conn.execute(
            """UPDATE predictions
               SET revision_verdict = ?, superseded_by = ?, status = 'superseded'
               WHERE id = ?""",
            (verdict, superseded_by, pred_id),
        )
    conn.commit()


def load_predictions_for_revalidation(
    conn: sqlite3.Connection, date: str,
) -> list[sqlite3.Row]:
    """Die heutigen offenen pre_market-Predictions — Eingangsmenge der
    Re-Validierung im 16:10-Lauf."""
    return conn.execute(
        """SELECT * FROM predictions
           WHERE date = ? AND run_type = 'pre_market'
             AND status = 'open' AND learnable = 1
           ORDER BY probability_pct DESC""",
        (date,),
    ).fetchall()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/db.py tests/unit/test_db.py
git commit -m "feat: superseded_by + revision_verdict fuer die Ablösung (E3)"
```

---

### Task 12: Re-Validierungs-Prompt und `src/revalidation.py`

**Files:**
- Create: `prompts/trade_proposals_v1.txt`
- Create: `src/revalidation.py`
- Test: `tests/unit/test_revalidation.py` *(neu)*

**Interfaces:**
- Consumes: `utils.call_claude`, `utils.extract_json_blob`, `CostTracker`
- Produces:
  - `revalidation.VERDICTS: frozenset[str]`
  - `revalidation.RevalidationError`
  - `revalidation.revalidate_one(prediction, snapshot, checks, relative_strength, policy_context, cost_tracker) -> dict`

**E1:** Sonnet **ohne** `WEB_SEARCH_TOOL`. Die Recherche hat der `pre_market`-Lauf bereits
bezahlt; Breaking News zwischen 15:00 und 16:10 deckt der eine Policy-Monitor-Call ab.

- [ ] **Step 1: Write the failing test**

Neue Datei `tests/unit/test_revalidation.py`:

```python
"""Tests fuer src/revalidation.py — der billige 16:10-Check (Entscheidung E1)."""
from unittest.mock import MagicMock
import pytest

from src.cost_tracker import CostTracker


def _claude(text: str) -> MagicMock:
    return MagicMock(text=text, model="claude-sonnet-4-6",
                     input_tokens=800, output_tokens=200,
                     cache_read_tokens=0, cache_creation_tokens=0,
                     web_search_calls=0)


PRED = {"id": 7, "ticker": "AAPL", "direction": "long", "entry_price": 178.0,
        "tp_price": 184.0, "sl_price": 176.0, "probability_pct": 65,
        "confidence": "high", "summary": "Momentum-Setup"}
OK_JSON = ('{"verdict": "bestaetigt", "probability_pct": 71, '
           '"entry_window_low": 178.2, "entry_window_high": 179.0, '
           '"reason": "haelt nach Opening"}')


def test_revalidation_uses_no_web_search(mocker):
    """E1: die 27 Einzelrecherchen sind gestrichen — genau das spart die Kosten."""
    call = mocker.patch("src.revalidation.call_claude", return_value=_claude(OK_JSON))
    from src.revalidation import revalidate_one
    revalidate_one(prediction=PRED, snapshot={"ticker": "AAPL", "price": 179.0},
                   checks=[], relative_strength=1.4, policy_context={},
                   cost_tracker=CostTracker())
    assert call.call_args.kwargs["tools"] == []


def test_revalidation_returns_verdict_and_probability(mocker):
    mocker.patch("src.revalidation.call_claude", return_value=_claude(OK_JSON))
    from src.revalidation import revalidate_one
    out = revalidate_one(prediction=PRED, snapshot={"ticker": "AAPL", "price": 179.0},
                         checks=[], relative_strength=1.4, policy_context={},
                         cost_tracker=CostTracker())
    assert out["verdict"] == "bestaetigt"
    assert out["probability_pct"] == 71
    assert out["entry_window_low"] == 178.2
    assert out["ticker"] == "AAPL"


def test_revalidation_rejects_an_unknown_verdict(mocker):
    """Ein erfundenes Urteil darf nicht still als 'bestaetigt' durchgehen."""
    mocker.patch("src.revalidation.call_claude",
                 return_value=_claude('{"verdict": "super", "probability_pct": 71}'))
    from src.revalidation import revalidate_one, RevalidationError
    with pytest.raises(RevalidationError):
        revalidate_one(prediction=PRED, snapshot={}, checks=[],
                       relative_strength=None, policy_context={},
                       cost_tracker=CostTracker())


def test_revalidation_raises_on_unparseable_output(mocker):
    mocker.patch("src.revalidation.call_claude", return_value=_claude("kein JSON"))
    from src.revalidation import revalidate_one, RevalidationError
    with pytest.raises(RevalidationError):
        revalidate_one(prediction=PRED, snapshot={}, checks=[],
                       relative_strength=None, policy_context={},
                       cost_tracker=CostTracker())


def test_revalidation_books_its_cost(mocker):
    mocker.patch("src.revalidation.call_claude", return_value=_claude(OK_JSON))
    from src.revalidation import revalidate_one
    tracker = CostTracker()
    revalidate_one(prediction=PRED, snapshot={}, checks=[],
                   relative_strength=None, policy_context={},
                   cost_tracker=tracker)
    assert tracker.total_eur > 0


def test_fired_checks_reach_the_model(mocker):
    """Der Prompt muss die Warnungen kennen, sonst kann er sie nicht wuerdigen."""
    call = mocker.patch("src.revalidation.call_claude", return_value=_claude(OK_JSON))
    from src.revalidation import revalidate_one
    from src.signal_checks import CheckResult
    revalidate_one(
        prediction=PRED, snapshot={}, relative_strength=None, policy_context={},
        checks=[CheckResult("vix_high_confidence_only", "VIX 28.4 zu hoch", False)],
        cost_tracker=CostTracker(),
    )
    assert "VIX 28.4 zu hoch" in call.call_args.kwargs["user"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_revalidation.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'src.revalidation'`

- [ ] **Step 3: Write minimal implementation**

Neue Datei `prompts/trade_proposals_v1.txt`:

```
Du pruefst ein bereits vollstaendig analysiertes Handelssignal ein zweites Mal —
rund 40 Minuten nach der US-Eroeffnung, gegen frische Kurse.

Du fuehrst KEINE neue Recherche durch und hast bewusst kein Websuch-Werkzeug. Die
Tiefenanalyse mit Recherche ist am Morgen gelaufen; marktbewegende Nachrichten der
letzten 48 Stunden stehen dir im POLICY CONTEXT bereits zusammengefasst zur Verfuegung.
Deine Aufgabe ist ausschliesslich: haelt die Morgen-These gegen das, was der Markt seit
der Eroeffnung tatsaechlich getan hat?

Du bekommst:
- ORIGINAL PREDICTION: die Morgen-These inkl. Einstieg, TP, SL und probability_pct
- CURRENT SNAPSHOT: frische Kurse und technische Indikatoren von jetzt
- RELATIVE STRENGTH: Tagesperformance des Tickers minus die seines Sub-Sektor-ETF,
  in Prozentpunkten. Positiv heisst: laeuft besser als sein Sektor.
- FIRED CHECKS: rechnerische Warnungen, die bereits angeschlagen haben
- POLICY CONTEXT: marktbewegende Ereignisse

Antworte mit GENAU diesem JSON-Objekt und nichts sonst:

{
  "verdict": "bestaetigt" | "geschwaecht" | "unveraendert" | "gedreht",
  "probability_pct": <int 0-100>,
  "entry_window_low": <float>,
  "entry_window_high": <float>,
  "reason": "<max. 240 Zeichen, deutsch>"
}

Bedeutung der Urteile:
- "bestaetigt": die These traegt, die Kursbewegung seit Eroeffnung stuetzt sie
- "geschwaecht": die These traegt noch, aber schwaecher als am Morgen
- "unveraendert": nichts Relevantes hat sich seit der Morgenanalyse getan
- "gedreht": die These ist gekippt, die Gegenrichtung waere jetzt plausibler

Zum Entry-Fenster: nenne eine Spanne, in der ein Einstieg noch sinnvoll ist, statt
blind zum aktuellen Kurs zu kaufen. Bei Long liegt sie typischerweise leicht unter
dem aktuellen Kurs (Pullback abwarten), bei Short leicht darueber.

Setze probability_pct ehrlich neu an. Sie darf deutlich unter dem Morgenwert liegen.
Ein "gedreht" ist ausdruecklich erwuenscht, wenn die Lage es hergibt — es fuehrt zu
keiner Gegenposition, sondern nur zu einer klaren Warnung.
```

Neue Datei `src/revalidation.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_revalidation.py -v`
Expected: PASS (6 Tests)

- [ ] **Step 5: Commit**

```bash
git add src/revalidation.py prompts/trade_proposals_v1.txt tests/unit/test_revalidation.py
git commit -m "feat: billige Re-Validierung ohne Websuche (E1)"
```

---

### Task 13: `run_trade_proposals()` ausbauen — Re-Validierung und Persistenz

**Files:**
- Modify: `src/signal_checks.py` — `recompute_rr_ratio()`
- Modify: `main.py` — `run_trade_proposals()` vollständig, neuer Helper `_persist_revision()`
- Test: `tests/unit/test_signal_checks.py`, `tests/unit/test_main.py`

**Interfaces:**
- Consumes: `db.load_predictions_for_revalidation()`, `db.record_revision()` (Task 11), `revalidation.revalidate_one()` (Task 12), `signal_checks.*` (Tasks 7–8), `_forced_candidates()` (Task 5)
- Produces:
  - `signal_checks.recompute_rr_ratio(entry, tp, sl, direction) -> float | None`
  - `main._persist_revision(conn, pred, verdict, snapshot, date, checks, momentum) -> int | None` — gibt die neue Prediction-ID zurück oder `None`, wenn keine entstand
  - `payload["signal_changes"]` — Task 14 rendert es

**TP/SL bleiben absolut.** Die Kursziele der Morgen-These wandern nicht, nur weil der
Einstieg 40 Minuten später erfolgt. Neu berechnet wird deshalb allein die R/R-Ratio gegen
den neuen Einstiegskurs — und rutscht sie unter `RR_RATIO_MIN_HARD`, ist das Signal
`verworfen`. Damit ist auch der Randfall abgedeckt, dass der Kurs seit 15:00 bereits
durch TP oder SL gelaufen ist.

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_signal_checks.py`:

```python
def test_recompute_rr_ratio_long():
    from src.signal_checks import recompute_rr_ratio
    # Einstieg 100, TP 106, SL 98 -> Chance 6, Risiko 2 -> 3.0
    assert recompute_rr_ratio(100.0, 106.0, 98.0, "long") == pytest.approx(3.0)


def test_recompute_rr_ratio_short():
    from src.signal_checks import recompute_rr_ratio
    assert recompute_rr_ratio(100.0, 94.0, 102.0, "short") == pytest.approx(3.0)


def test_recompute_rr_ratio_shrinks_when_the_entry_drifted():
    """Nach dem Opening naeher am TP: dasselbe Ziel, schlechteres Verhaeltnis."""
    from src.signal_checks import recompute_rr_ratio
    assert recompute_rr_ratio(104.0, 106.0, 98.0, "long") == pytest.approx(1/3)


def test_recompute_rr_ratio_is_none_past_the_stop():
    """Kurs schon durch den SL — kein sinnvolles Verhaeltnis mehr."""
    from src.signal_checks import recompute_rr_ratio
    assert recompute_rr_ratio(97.0, 106.0, 98.0, "long") is None
```

In `tests/unit/test_main.py`:

```python
def _pred_row(conn, **over):
    base = {"date": "2026-07-30", "run_type": "pre_market", "ticker": "AAPL",
            "direction": "long", "entry_price": 100.0, "tp_price": 106.0,
            "sl_price": 98.0, "probability_pct": 65, "confidence": "high"}
    from src import db
    return db.save_prediction(conn, {**base, **over})


def test_confirmed_signal_supersedes_the_morning_row(in_memory_db):
    from src import db
    from main import _persist_revision
    db.init_schema(in_memory_db)
    pid = _pred_row(in_memory_db)
    pred = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()

    new_id = _persist_revision(
        conn=in_memory_db, pred=pred,
        verdict={"verdict": "bestaetigt", "probability_pct": 71,
                 "reason": "haelt", "entry_window_low": 100.2,
                 "entry_window_high": 101.0},
        snapshot={"price": 101.0}, date="2026-07-30", checks=[],
        momentum=(1.2, 0.8),
    )
    assert new_id is not None
    old = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    assert old["status"] == "superseded" and old["superseded_by"] == new_id
    new = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (new_id,)).fetchone()
    assert new["run_type"] == "trade_proposals"
    assert new["entry_price"] == 101.0, "Einstieg ist der 16:10-Kurs"
    assert new["tp_price"] == 106.0, "TP bleibt absolut — das Ziel wandert nicht"
    assert new["probability_pct"] == 71


def test_flipped_signal_creates_no_counter_position(in_memory_db):
    """E5: melden, nicht handeln."""
    from src import db
    from main import _persist_revision
    db.init_schema(in_memory_db)
    pid = _pred_row(in_memory_db)
    pred = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()

    new_id = _persist_revision(
        conn=in_memory_db, pred=pred,
        verdict={"verdict": "gedreht", "probability_pct": 30, "reason": "gekippt"},
        snapshot={"price": 99.0}, date="2026-07-30", checks=[], momentum=(None, None),
    )
    assert new_id is None
    rows = in_memory_db.execute("SELECT * FROM predictions").fetchall()
    assert len(rows) == 1, "keine Gegenposition"
    assert rows[0]["status"] == "open", "bleibt offen und wird ausgewertet"
    assert rows[0]["revision_verdict"] == "gedreht"


def test_hard_check_marks_the_signal_verworfen(in_memory_db):
    from src import db
    from main import _persist_revision
    from src.signal_checks import CheckResult
    db.init_schema(in_memory_db)
    pid = _pred_row(in_memory_db)
    pred = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()

    new_id = _persist_revision(
        conn=in_memory_db, pred=pred,
        verdict={"verdict": "bestaetigt", "probability_pct": 71, "reason": "x"},
        snapshot={"price": 101.0}, date="2026-07-30",
        checks=[CheckResult("vix_no_new_longs", "VIX 41", enforced=True)],
        momentum=(None, None),
    )
    assert new_id is None
    row = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row["revision_verdict"] == "verworfen" and row["status"] == "open"


def test_entry_past_the_stop_is_verworfen(in_memory_db):
    """Der Kurs ist seit 15:00 durch den SL gelaufen — kein Einstieg mehr."""
    from src import db
    from main import _persist_revision
    db.init_schema(in_memory_db)
    pid = _pred_row(in_memory_db)
    pred = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()

    new_id = _persist_revision(
        conn=in_memory_db, pred=pred,
        verdict={"verdict": "bestaetigt", "probability_pct": 71, "reason": "x"},
        snapshot={"price": 97.0}, date="2026-07-30", checks=[], momentum=(None, None),
    )
    assert new_id is None
    row = in_memory_db.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row["revision_verdict"] == "verworfen"


def test_revalidation_failure_leaves_the_row_untouched(tmp_db_path, mocker):
    """Nie auf Basis eines Fehlers abloesen — sonst verschwindet ein gutes
    Signal, weil ein Call einmal unlesbar antwortete."""
    from src import db
    from src.revalidation import RevalidationError
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    pid = _pred_row(conn)
    conn.commit(); conn.close()

    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.collect", return_value=([{"ticker": "AAPL", "price": 101.0}], 0))
    mocker.patch("main.fetch_market_context", return_value={"vix_level": 18.0})
    mocker.patch("main.collect_sector_momentum", return_value={})
    mocker.patch("main.run_policy_monitor", return_value={"policy_risk_level": "low",
                                                         "events": []})
    mocker.patch("main.check_open_positions", return_value=[])
    mocker.patch("main.revalidate_one", side_effect=RevalidationError("kaputt"))

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    row = conn.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row["status"] == "open"
    assert row["revision_verdict"] is None
    conn.close()


@pytest.mark.parametrize("phase,target", [
    ("market_context",  "main.fetch_market_context"),
    ("data_collection", "main.collect"),
    ("sector_momentum", "main.collect_sector_momentum"),
    ("policy_monitor",  "main.run_policy_monitor"),
    ("revalidation",    "main.revalidate_one"),
    ("portfolio_check", "main.check_open_positions"),
])
def test_cost_abort_reports_the_right_phase(tmp_db_path, mocker, phase, target):
    """B-05 fuer den neuen Run-Type: bricht der Lauf am Kosten-Deckel ab, muss die
    Kostenzeile die TATSAECHLICHE Phase nennen. Der alte Bug gab hier systematisch
    'policy_monitor' zurueck, egal wo es knallte. Eine kuenftig ergaenzte Phase ohne
    current_phase-Zuweisung faellt hier auf."""
    from src import db
    from src.cost_tracker import CostCapExceeded
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    _pred_row(conn); conn.commit(); conn.close()

    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.fetch_market_context", return_value={"vix_level": 18.0})
    mocker.patch("main.collect", return_value=([{"ticker": "AAPL", "price": 101.0}], 0))
    mocker.patch("main.collect_sector_momentum", return_value={})
    mocker.patch("main.run_policy_monitor",
                 return_value={"policy_risk_level": "low", "events": []})
    mocker.patch("main.revalidate_one", return_value={
        "verdict": "bestaetigt", "probability_pct": 71, "reason": "ok"})
    mocker.patch("main.check_open_positions", return_value=[])
    mocker.patch(target, side_effect=CostCapExceeded("Deckel"))

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    row = conn.execute(
        "SELECT aborted_at_phase FROM cost_tracking WHERE run_type='trade_proposals'"
    ).fetchone()
    assert row["aborted_at_phase"] == phase
    conn.close()
```

> **Zur `sector_momentum`-Zeile:** `run_trade_proposals()` fängt dort ein blankes
> `Exception`, damit ein ETF-Ausfall keinen bezahlten Lauf kostet. `CostCapExceeded`
> darf davon **nicht** verschluckt werden — der `except`-Zweig muss es erneut werfen:
> ```python
> except CostCapExceeded:
>     raise
> except Exception as e:
>     log.warning(f"Sektor-Momentum nicht ermittelbar, Run laeuft ohne: {e}")
> ```
> Dieselbe Reihenfolge gilt für den Policy-Monitor-Block. Ohne sie liefe der Run über
> den Deckel hinaus weiter und die Kostenzeile nennte die falsche Phase — genau der
> Fehler, den B-05 beseitigt hat.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_signal_checks.py tests/unit/test_main.py -k "rr_ratio or supersedes or counter_position or verworfen or untouched" -v`
Expected: FAIL — `recompute_rr_ratio` und `_persist_revision` existieren nicht

- [ ] **Step 3: Write minimal implementation**

In `src/signal_checks.py` ergänzen:

```python
def recompute_rr_ratio(
    entry: float, tp: float, sl: float, direction: str,
) -> float | None:
    """Chance/Risiko-Verhaeltnis gegen einen NEUEN Einstiegskurs.

    Die Kursziele der Morgen-These bleiben absolut — sie wandern nicht, nur weil der
    Einstieg 40 Minuten spaeter erfolgt. Verschiebt sich der Einstieg aber Richtung TP,
    schrumpft das Verhaeltnis. None, wenn der Kurs bereits durch TP oder SL gelaufen
    ist; dann gibt es kein sinnvolles Verhaeltnis mehr."""
    if direction == "long":
        reward, risk = tp - entry, entry - sl
    else:
        reward, risk = entry - tp, sl - entry
    if reward <= 0 or risk <= 0:
        return None
    return reward / risk
```

In `main.py` die Imports ergänzen:

```python
from src import signal_checks
from src.revalidation import revalidate_one, RevalidationError
```

Neuer Helper in `main.py`:

```python
def _persist_revision(
    conn, pred, verdict: dict, snapshot: dict, date: str,
    checks: list, momentum: tuple[float | None, float | None],
) -> int | None:
    """Setzt das Urteil des 16:10-Laufs nach der Tabelle aus Spec 6.3 um.

    Gibt die ID der neuen trade_proposals-Zeile zurueck, oder None, wenn keine
    entstand (Urteil 'gedreht' oder ein hart greifender Check). In beiden
    None-Faellen bleibt die pre_market-Zeile offen und wird regulaer ausgewertet —
    nur so laesst sich messen, ob die Ablehnung richtig lag."""
    etf_mom, db_mom = momentum
    ticker, direction = pred["ticker"], pred["direction"]

    if verdict["verdict"] == "gedreht":
        # E5: melden, nicht handeln. Das Gegensignal ist nie durch Phase 3
        # gelaufen — es haette keine Belege und kein analytisch hergeleitetes TP/SL.
        db.record_revision(conn, pred["id"], "gedreht")
        return None

    if signal_checks.blocks(checks):
        db.record_revision(conn, pred["id"], "verworfen")
        return None

    entry = snapshot.get("price") or pred["entry_price"]
    rr = signal_checks.recompute_rr_ratio(
        entry, pred["tp_price"], pred["sl_price"], direction)
    if rr is None or rr < config.RR_RATIO_MIN_HARD:
        db.log_guardrail_reject(conn, {
            "date": date, "run_type": "trade_proposals", "ticker": ticker,
            "direction": direction, "rule": "rr_ratio",
            "detail": f"R/R nach Opening {rr} < {config.RR_RATIO_MIN_HARD} "
                      f"(Einstieg {entry} statt {pred['entry_price']})",
            "enforced": 1,
            "sector_etf_momentum": etf_mom, "sector_db_momentum": db_mom,
        })
        db.record_revision(conn, pred["id"], "verworfen")
        return None

    new_id = db.save_prediction(conn, {
        "date": date, "run_type": "trade_proposals",
        "asset_class": pred["asset_class"], "ticker": ticker, "direction": direction,
        "entry_price": entry,
        "tp_price": pred["tp_price"], "tp_pct": pred["tp_pct"],
        "sl_price": pred["sl_price"], "sl_pct": pred["sl_pct"],
        "rr_ratio": round(rr, 2),
        "total_score": pred["total_score"],
        "probability_pct": verdict.get("probability_pct"),
        "confidence": pred["confidence"],
        "score_market_env": pred["score_market_env"],
        "score_company": pred["score_company"],
        "score_valuation": pred["score_valuation"],
        "score_momentum": pred["score_momentum"],
        "score_risk": pred["score_risk"],
        "score_sector": pred["score_sector"],
        "score_catalyst": pred["score_catalyst"],
        "score_policy": pred["score_policy"],
        "market_regime": pred["market_regime"],
        "vix_at_prediction": pred["vix_at_prediction"],
        "sector": pred["sector"],
        "earnings_warning": pred["earnings_warning"],
        "summary": verdict.get("reason") or pred["summary"],
        "learnable": True,
        "hold_days_recommended": pred["hold_days_recommended"],
        "intraday_range_pct": pred["intraday_range_pct"],
        "sector_etf_momentum": etf_mom, "sector_db_momentum": db_mom,
    })
    db.record_revision(conn, pred["id"], verdict["verdict"], superseded_by=new_id)
    return new_id
```

`run_trade_proposals()` aus Task 1 vollständig ersetzen:

```python
def run_trade_proposals(date: str, db_path: str) -> None:
    """Run-Type trade_proposals (16:10 Berlin): prueft die pre_market-Signale nach
    dem Opening-Rauschen billig nach und loest sie ab.

    Kein Phase 0 — die Megatrend-Analyse aendert sich nicht in 70 Minuten, der Run
    liest sie aus der DB. Der Policy-Monitor laeuft dagegen MIT Websuche: seit E1
    ist er die einzige Recherche des Laufs."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    cost_tracker = CostTracker()
    price_provider = CapitalComProvider()
    earnings_provider = FinnhubProvider()

    aborted_at: str | None = None
    current_phase = "market_context"
    payload = {
        "date": date, "run_type": "trade_proposals",
        "briefing": [], "portfolio_recs": [], "signal_changes": [],
        "commodities_crypto": [], "market_context": {},
        "cost_summary": {},
    }

    try:
        market_ctx = {"vix_level": None, "advance_decline_ratio": None,
                      "market_regime": None}
        try:
            market_ctx = fetch_market_context(
                date=date, run_type="trade_proposals", cost_tracker=cost_tracker,
                price_provider=price_provider,
            )
            db.save_market_context(
                conn, {**market_ctx, "date": date, "run_type": "trade_proposals"})
        except MarketContextError as e:
            log.warning(f"Markt-Kontext nicht ermittelbar, Run laeuft ohne: {e}")
        payload["market_context"] = market_ctx

        current_phase = "data_collection"
        _tickers = (config.SP500_FULL_TICKERS if config.USE_FULL_SP500
                    else config.SP500_MVP_TICKERS)
        sp_tds, _ = collect(
            tickers=_tickers, price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn, date=date, run_type="trade_proposals")
        cc_tickers = [d["ticker"] for d in build_commodity_crypto_inputs()]
        cc_tds, _ = collect(
            tickers=cc_tickers, price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn, date=date, run_type="trade_proposals")
        snapshots = {td["ticker"]: td for td in (sp_tds + cc_tds)}

        current_phase = "open_positions"
        _forced_candidates(price_provider)   # nur fuer den Log — Phase 4a sieht sie ohnehin

        current_phase = "sector_momentum"
        sector_mom: dict[int, dict] = {}
        try:
            sector_mom = collect_sector_momentum(
                conn=conn, date=date, run_type="trade_proposals",
                price_provider=price_provider)
        except Exception as e:
            log.warning(f"Sektor-Momentum nicht ermittelbar, Run laeuft ohne: {e}")

        current_phase = "policy_monitor"
        # Seit E1 die einzige Websuche des Laufs. Faellt sie aus, ist die
        # Re-Validierung rein preisbasiert — immer noch besser als gar keine.
        policy_context: dict = {"policy_risk_level": "unknown", "events": []}
        try:
            policy_context = run_policy_monitor(
                date=date, run_type="trade_proposals", cost_tracker=cost_tracker)
        except Exception as e:
            log.warning(f"Policy-Monitor ausgefallen, Re-Validierung laeuft "
                        f"rein preisbasiert weiter: {e}")
            payload["briefing"] = ["⚠️ Policy-Monitor ausgefallen — "
                                   "keine Nachrichtenlage in dieser Prüfung."]

        current_phase = "revalidation"
        payload["signal_changes"] = _revalidate_all(
            conn=conn, date=date, snapshots=snapshots, sector_mom=sector_mom,
            market_ctx=market_ctx, policy_context=policy_context,
            cost_tracker=cost_tracker,
        )

        current_phase = "portfolio_check"
        payload["portfolio_recs"] = check_open_positions(
            conn=conn, today=date, run_type="trade_proposals",
            analyses_by_ticker=snapshots,
            trend_context=db.load_trend_context(conn, date) or {},
            policy_context=policy_context, cost_tracker=cost_tracker,
        )

    except CostCapExceeded as e:
        log.warning(f"Run aborted in phase '{current_phase}': {e}")
        cost_tracker.aborted_at_phase = current_phase
        aborted_at = current_phase

    payload["cost_summary"] = cost_tracker.summary(
        run_type="trade_proposals", date=date)
    db.save_cost_tracking(conn, payload["cost_summary"])
    log.info(f"trade_proposals fertig: {len(payload['signal_changes'])} Signale "
             f"geprueft, {payload['cost_summary']['total_eur']} EUR"
             + (f", abgebrochen in {aborted_at}" if aborted_at else ""))
    conn.close()


def _revalidate_all(
    conn, date: str, snapshots: dict, sector_mom: dict,
    market_ctx: dict, policy_context: dict, cost_tracker: CostTracker,
) -> list[dict]:
    """Prueft jedes heutige offene pre_market-Signal nach und persistiert das
    Ergebnis. Gibt die Zeilen fuer die Mail zurueck.

    Ein Fehlschlag betrifft immer nur EIN Signal: die zugehoerige Zeile bleibt dann
    unangetastet offen und erscheint in der Mail als 'nicht geprueft'."""
    open_preds = db.load_predictions_for_revalidation(conn, date)
    log.info(f"Re-Validierung: {len(open_preds)} offene pre_market-Signale")

    counts = signal_checks.cluster_counts(conn, [p["ticker"] for p in open_preds])
    out: list[dict] = []
    for pred in open_preds:
        ticker = pred["ticker"]
        snapshot = snapshots.get(ticker, {})
        etf_mom, db_mom = signal_checks.momentum_for(conn, ticker, sector_mom)
        sector = db.get_ticker_sector(conn, ticker)
        sector_name = sector["name"] if sector else None
        checks = [c for c in (
            signal_checks.check_vix(pred["direction"], pred["confidence"],
                                    market_ctx.get("vix_level"), enforce=True),
            signal_checks.check_sector_momentum(pred["direction"], etf_mom, db_mom,
                                                enforce=True),
            signal_checks.check_cluster(sector_name,
                                        counts.get(sector_name or "", 0)),
        ) if c is not None]

        # E4: auch der 16:10-Lauf persistiert JEDEN angeschlagenen Check — sonst
        # zeigt die Guardrail-Statistik der Weekly-Mail nur die weiche Haelfte und
        # die enforced-Spalte waere wertlos.
        for c in checks:
            db.log_guardrail_reject(conn, {
                "date": date, "run_type": "trade_proposals", "ticker": ticker,
                "direction": pred["direction"], "rule": c.rule, "detail": c.detail,
                "enforced": 1 if c.enforced else 0,
                "sector_etf_momentum": etf_mom, "sector_db_momentum": db_mom,
            })

        try:
            verdict = revalidate_one(
                prediction=pred, snapshot=snapshot, checks=checks,
                relative_strength=signal_checks.compute_relative_strength(
                    conn, ticker, date),
                policy_context=policy_context, cost_tracker=cost_tracker,
            )
        except RevalidationError as e:
            log.warning(f"{ticker}: Re-Validierung fehlgeschlagen, Zeile bleibt "
                        f"unveraendert offen: {e}")
            out.append({"ticker": ticker, "direction": pred["direction"],
                        "verdict": "nicht_geprueft",
                        "probability_before": pred["probability_pct"],
                        "probability_after": None, "reason": str(e), "checks": []})
            continue

        new_id = _persist_revision(
            conn=conn, pred=pred, verdict=verdict, snapshot=snapshot,
            date=date, checks=checks, momentum=(etf_mom, db_mom),
        )
        out.append({
            "ticker": ticker, "direction": pred["direction"],
            "verdict": "verworfen" if (new_id is None and
                                       verdict["verdict"] != "gedreht")
                       else verdict["verdict"],
            "probability_before": pred["probability_pct"],
            "probability_after": verdict.get("probability_pct"),
            "entry_window_low": verdict.get("entry_window_low"),
            "entry_window_high": verdict.get("entry_window_high"),
            "reason": verdict.get("reason"),
            "checks": [f"{c.rule}: {c.detail}" for c in checks],
        })
    return out
```

> **Falls `db.load_trend_context(conn, date)` noch nicht existiert:** eine dünne
> Lesefunktion auf `trend_analyses` für den heutigen Tag ergänzen, die bei fehlendem
> Eintrag `{}` zurückgibt. Der Portfolio-Check verträgt einen leeren Trend-Kontext.

- [ ] **Step 4: Run the full suite**

Run: `pytest tests/ --cov=src --cov-fail-under=80`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add main.py src/signal_checks.py src/db.py tests/
git commit -m "feat: trade_proposals validiert nach und loest die Morgenzeile ab (E1, E3, E5)"
```

---

### Task 14: Die 16:10-Mail

**Files:**
- Modify: `src/email_sender.py` — `_section_signal_changes()`, `render_trade_proposals_html()`, `send_trade_proposals_email()`
- Modify: `main.py` — Versand in `run_trade_proposals()`
- Test: `tests/unit/test_email_sender.py`, `tests/integration/test_email_render.py`

**Interfaces:**
- Consumes: `payload["signal_changes"]` (Task 13), vorhandene `_section_portfolio()`, `_section_commodities_crypto()`, `_section_footer()`, `_send()`
- Produces: `email_sender.send_trade_proposals_email(payload, api_key, email_from, email_to) -> None`

**Invariante:** Die Portfolio-Sektion bleibt die **erste** Sektion — auch in dieser Mail.

- [ ] **Step 1: Write the failing test**

```python
VERDICT_PAYLOAD = {
    "date": "2026-07-30", "run_type": "trade_proposals",
    "briefing": [], "portfolio_recs": [], "commodities_crypto": [],
    "market_context": {"vix_level": 28.4, "advance_decline_ratio": 0.7},
    "cost_summary": {"total_eur": 0.61, "cache_hit_rate": 0.0, "input_tokens": 1,
                     "output_tokens": 1, "web_search_calls": 2,
                     "aborted_at_phase": None},
    "signal_changes": [
        {"ticker": "AAPL", "direction": "long", "verdict": "bestaetigt",
         "probability_before": 65, "probability_after": 71,
         "entry_window_low": 178.2, "entry_window_high": 179.0,
         "reason": "haelt nach Opening", "checks": []},
        {"ticker": "NVDA", "direction": "long", "verdict": "gedreht",
         "probability_before": 70, "probability_after": 28,
         "reason": "Sektor dreht", "checks": ["sector_momentum: SOXX -2.5%"]},
        {"ticker": "MSFT", "direction": "short", "verdict": "nicht_geprueft",
         "probability_before": 60, "probability_after": None,
         "reason": "Call unlesbar", "checks": []},
    ],
}


def test_trade_proposals_mail_shows_before_and_after():
    from src.email_sender import render_trade_proposals_html
    html = render_trade_proposals_html(VERDICT_PAYLOAD)
    assert "65" in html and "71" in html
    assert "AAPL" in html and "bestaetigt" in html


def test_trade_proposals_mail_marks_flipped_and_unchecked():
    from src.email_sender import render_trade_proposals_html
    html = render_trade_proposals_html(VERDICT_PAYLOAD)
    assert "gedreht" in html
    assert "nicht geprüft" in html or "nicht_geprueft" in html


def test_trade_proposals_mail_lists_fired_checks():
    from src.email_sender import render_trade_proposals_html
    assert "SOXX -2.5%" in render_trade_proposals_html(VERDICT_PAYLOAD)


def test_portfolio_stays_the_first_section():
    """Dokumentierte Invariante — gilt auch fuer die 16:10-Mail."""
    from src.email_sender import render_trade_proposals_html
    html = render_trade_proposals_html(VERDICT_PAYLOAD)
    assert html.index("Portfolio") < html.index("Signal")


def test_trade_proposals_mail_shows_market_warnings():
    from src.email_sender import render_trade_proposals_html
    html = render_trade_proposals_html(VERDICT_PAYLOAD)
    assert "28.4" in html or "28,4" in html


def test_send_trade_proposals_email_uses_the_shared_sender(mocker):
    send = mocker.patch("src.email_sender._send")
    from src.email_sender import send_trade_proposals_email
    send_trade_proposals_email(VERDICT_PAYLOAD, api_key="k",
                               email_from="a@b.c", email_to="d@e.f")
    send.assert_called_once()
    assert "trade_proposals" in send.call_args[0][3] or "16:10" in send.call_args[0][3]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_email_sender.py -k trade_proposals -v`
Expected: FAIL mit `ImportError: cannot import name 'render_trade_proposals_html'`

- [ ] **Step 3: Write minimal implementation**

In `src/email_sender.py` ergänzen:

```python
_VERDICT_LABEL = {
    "bestaetigt":    "✅ bestätigt",
    "geschwaecht":   "🔸 geschwächt",
    "unveraendert":  "➖ unverändert",
    "gedreht":       "🔁 gedreht",
    "verworfen":     "⛔ verworfen",
    "nicht_geprueft": "❔ nicht geprüft",
}


def _section_signal_changes(changes: list[dict]) -> str:
    """Kernsektion der 16:10-Mail: was ist seit der Morgenanalyse mit jedem Signal
    passiert (B.2/Schritt 5)."""
    if not changes:
        return ('<h2>Signal-Prüfung 16:10</h2>'
                '<p><i>Keine offenen Morgensignale zu prüfen.</i></p>')
    rows = []
    for c in changes:
        before, after = c.get("probability_before"), c.get("probability_after")
        arrow = f'{_h(before)}% → {_h(after)}%' if after is not None else f'{_h(before)}% → —'
        window = ""
        if c.get("entry_window_low") is not None:
            window = f'{_h(c["entry_window_low"])} – {_h(c["entry_window_high"])}'
        rows.append(
            f'<tr><td>{_h(c["ticker"])}</td>'
            f'<td>{_h(c.get("direction"))}</td>'
            f'<td>{_VERDICT_LABEL.get(c.get("verdict"), _h(c.get("verdict")))}</td>'
            f'<td>{arrow}</td><td>{window}</td>'
            f'<td>{_h("; ".join(c.get("checks") or []))}</td>'
            f'<td>{_h(c.get("reason", ""))[:200]}</td></tr>'
        )
    return (
        '<h2>Signal-Prüfung 16:10</h2>'
        '<table border="1" cellpadding="4" cellspacing="0">'
        '<tr><th>Ticker</th><th>Dir</th><th>Urteil</th><th>Wahrsch.</th>'
        '<th>Entry-Fenster</th><th>Checks</th><th>Begründung</th></tr>'
        + "".join(rows) + '</table>'
    )


def _section_market_warnings(ctx: dict) -> str:
    """VIX und Marktbreite als Kontextzeile. Die Marktbreite wird nur
    durchgereicht — B.3 weist ihr ausdruecklich nur 'Kontext / Warnung' zu."""
    vix, ad = ctx.get("vix_level"), ctx.get("advance_decline_ratio")
    if vix is None and ad is None:
        return ""
    parts = []
    if vix is not None:
        parts.append(f'VIX {_h(vix)}')
    if ad is not None:
        parts.append(f'A/D-Ratio {_h(ad)}')
    return f'<h2>Marktlage</h2><p>{" &middot; ".join(parts)}</p>'


def render_trade_proposals_html(payload: dict) -> str:
    """16:10-Mail. Portfolio bleibt die erste Sektion (dokumentierte Invariante)."""
    return (
        '<html><body style="font-family:sans-serif;font-size:14px;">'
        f'<h1>Shares_Future — {_h(payload.get("date"))} (16:10 Signal-Prüfung)</h1>'
        + _section_briefing(payload.get("briefing") or [])
        + _section_portfolio(payload.get("portfolio_recs") or [])
        + _section_signal_changes(payload.get("signal_changes") or [])
        + _section_commodities_crypto(payload.get("commodities_crypto") or [])
        + _section_market_warnings(payload.get("market_context") or {})
        + _section_footer(payload)
        + '</body></html>'
    )


def send_trade_proposals_email(
    payload: dict, api_key: str, email_from: str, email_to: str,
) -> None:
    """Rendert und versendet die 16:10-Mail ueber Resend."""
    changes = payload.get("signal_changes") or []
    confirmed = sum(1 for c in changes if c.get("verdict") == "bestaetigt")
    subject = (f"[Shares_Future] {payload.get('date')} trade_proposals — "
               f"{confirmed}/{len(changes)} bestätigt")
    _send(api_key, email_from, email_to, subject, render_trade_proposals_html(payload))
```

In `main.py` den Import ergänzen und `run_trade_proposals()` vor `conn.close()`
abschliessen — mit derselben B-10-Trennung wie `run_pipeline()`:

```python
    try:
        send_trade_proposals_email(
            payload=payload, api_key=config.RESEND_API_KEY,
            email_from=config.EMAIL_FROM, email_to=config.EMAIL_TO,
        )
    except Exception as e:
        log.error(
            f"Re-Validierung vollstaendig persistiert "
            f"({len(payload['signal_changes'])} Signale, "
            f"{payload['cost_summary'].get('total_eur')} EUR) — "
            f"nur der Mailversand scheiterte: {e}"
        )
        raise MailDeliveryError(str(e)) from e
    finally:
        conn.close()
```

**Zwei Testanpassungen, die dieser Task mitziehen muss:**

1. `test_run_trade_proposals_sends_no_mail_yet` aus Task 1 **ersetzen** durch einen Test,
   der den Versand jetzt erwartet.
2. Jeder Test aus Task 13, der `run_trade_proposals()` komplett durchlaufen lässt
   (`test_revalidation_failure_leaves_the_row_untouched`, die sechs Fälle von
   `test_cost_abort_reports_the_right_phase`), braucht ab jetzt
   `mocker.patch("main.send_trade_proposals_email")`. Ohne das versucht der Lauf einen
   echten Versand und scheitert mit `MailDeliveryError`. In Task 13 war der Patch noch
   nicht möglich — die Funktion existierte dort noch nicht.

- [ ] **Step 4: Run the full suite**

Run: `pytest tests/ --cov=src --cov-fail-under=80`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/email_sender.py main.py tests/
git commit -m "feat: 16:10-Mail mit Vorher/Nachher-Vergleich (B.2/Schritt 5)"
```

---

# Schnitt 5 — Opening-Gap und Verifikation der harten Durchsetzung

> **Hinweis zur Abweichung von der Spec-Schnittliste:** Die harte Durchsetzung von
> VIX-Filter und D9 ist bereits in **Task 13** gelandet — `_persist_revision()` braucht
> `signal_checks.blocks()`, um den `verworfen`-Pfad überhaupt gehen zu können. Sie hier
> nachzureichen hätte bedeutet, Task 13 mit einem toten Zweig auszuliefern. Schnitt 5
> liefert deshalb den letzten fehlenden Check und weist die Durchsetzung im
> Zusammenspiel nach.

---

### Task 15: Opening-Gap-Check

**Files:**
- Modify: `src/signal_checks.py` — `check_opening_gap()`
- Modify: `config.py` — `OPENING_GAP_WARN_PCT`
- Modify: `main.py` — Einbau in `_revalidate_all()`
- Test: `tests/unit/test_signal_checks.py`, `tests/unit/test_main.py`

**Interfaces:**
- Consumes: `CheckResult`
- Produces: `signal_checks.check_opening_gap(pre_market_price, current_price) -> CheckResult | None`

**Datenquelle ohne neuen Abruf:** Der `pre_market`-Kurs steht bereits als `entry_price` auf
der Morgen-Prediction. Genau das meint B.3 mit „Gap zwischen `pre_market`-Kurs und
aktuellem Kurs" — es braucht weder `premarket_price` noch einen zusätzlichen API-Call.

Immer weich: ein Gap ist eine Information für den Einstiegszeitpunkt, kein Urteil über die
These. Ob das Signal trotzdem durchfällt, entscheidet die neu berechnete R/R-Ratio aus
Task 13.

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_signal_checks.py`:

```python
def test_opening_gap_is_silent_below_the_threshold():
    from src.signal_checks import check_opening_gap
    assert check_opening_gap(100.0, 101.0) is None


def test_opening_gap_warns_on_a_large_move_up():
    from src.signal_checks import check_opening_gap
    r = check_opening_gap(100.0, 103.0)
    assert r is not None and r.rule == "opening_gap"
    assert r.enforced is False, "ein Gap ist eine Information, kein Urteil"
    assert "+3.0" in r.detail


def test_opening_gap_warns_on_a_large_move_down():
    from src.signal_checks import check_opening_gap
    r = check_opening_gap(100.0, 97.0)
    assert r is not None and "-3.0" in r.detail


def test_opening_gap_is_silent_without_data():
    from src.signal_checks import check_opening_gap
    assert check_opening_gap(None, 103.0) is None
    assert check_opening_gap(100.0, None) is None
    assert check_opening_gap(0.0, 103.0) is None
```

In `tests/unit/test_main.py`:

```python
def test_opening_gap_reaches_the_revalidation_prompt(tmp_db_path, mocker):
    """Der Gap muss beim Modell ankommen, sonst kann es ihn nicht wuerdigen."""
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    _pred_row(conn, entry_price=100.0)
    conn.commit(); conn.close()

    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.collect", return_value=([{"ticker": "AAPL", "price": 104.0}], 0))
    mocker.patch("main.fetch_market_context", return_value={"vix_level": 18.0})
    mocker.patch("main.collect_sector_momentum", return_value={})
    mocker.patch("main.run_policy_monitor", return_value={"policy_risk_level": "low",
                                                          "events": []})
    mocker.patch("main.check_open_positions", return_value=[])
    mocker.patch("main.send_trade_proposals_email")
    reval = mocker.patch("main.revalidate_one", return_value={
        "verdict": "geschwaecht", "probability_pct": 50, "reason": "Gap"})

    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    fired = {c.rule for c in reval.call_args.kwargs["checks"]}
    assert "opening_gap" in fired
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_signal_checks.py tests/unit/test_main.py -k opening_gap -v`
Expected: FAIL mit `ImportError: cannot import name 'check_opening_gap'`

- [ ] **Step 3: Write minimal implementation**

In `config.py`:

```python
# Sprint 3B / Plan 2 (B.3): ab welcher Kursluecke zwischen dem 15:00-Kurs und dem
# 16:10-Kurs die Mail warnt. Reine Warnung — ob das Signal durchfaellt, entscheidet
# die neu berechnete R/R-Ratio.
OPENING_GAP_WARN_PCT = 1.5
```

In `src/signal_checks.py`:

```python
def check_opening_gap(
    pre_market_price: float | None, current_price: float | None,
) -> CheckResult | None:
    """Warnt bei einer grossen Luecke zwischen dem 15:00-Kurs und dem aktuellen.

    Als 15:00-Kurs dient der entry_price der Morgen-Prediction — genau der Wert, den
    B.3 mit 'pre_market-Kurs' meint. Kein zusaetzlicher Abruf noetig.

    Immer weich: ein Gap sagt etwas ueber den Einstiegszeitpunkt, nicht ueber die
    These. Ob das Setup dadurch unbrauchbar wird, faengt die neu berechnete
    R/R-Ratio in main._persist_revision() ab."""
    if not pre_market_price or current_price is None:
        return None
    gap = (current_price - pre_market_price) / pre_market_price * 100.0
    if abs(gap) < config.OPENING_GAP_WARN_PCT:
        return None
    return CheckResult(
        rule="opening_gap",
        detail=f"Gap seit 15:00: {gap:+.1f}% "
               f"({pre_market_price} → {current_price})",
        enforced=False,
    )
```

In `main.py`, `_revalidate_all()` — die `checks`-Liste um einen Eintrag erweitern:

```python
            signal_checks.check_opening_gap(
                pred["entry_price"], snapshot.get("price")),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_signal_checks.py tests/unit/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/signal_checks.py config.py main.py tests/
git commit -m "feat: Opening-Gap-Check im 16:10-Lauf (B.3)"
```

---

### Task 16: Durchsetzung im Zusammenspiel nachweisen

**Files:**
- Test: `tests/integration/test_trade_proposals_flow.py` *(neu)*

**Interfaces:**
- Consumes: alles aus den Tasks 1–15
- Produces: nichts — reiner Nachweis

Dieser Task schreibt **keinen Produktivcode**. Er weist die beiden Eigenschaften nach, die
sich nur im Zusammenspiel zeigen und deren Bruch später still falsche Zahlen erzeugen
würde: dass um 16:10 tatsächlich hart gefiltert wird und dass danach **kein** Aggregat
doppelt zählt.

- [ ] **Step 1: Write the failing test**

Neue Datei `tests/integration/test_trade_proposals_flow.py`:

```python
"""End-to-End-Nachweis fuer den 16:10-Lauf (Sprint 3B / Plan 2).

Zwei Eigenschaften, die sich nur im Zusammenspiel zeigen:
  1. E4 — derselbe Check warnt um 15:00 und blockiert um 16:10
  2. E3 — nach der Abloesung existiert je Trade-Idee genau EIN offenes Signal
Beide wuerden bei einem Bruch keine Exception werfen, sondern still falsche
Kennzahlen liefern."""
from unittest.mock import MagicMock
import pytest

from src import db


def _mock_16_10(mocker, price: float, verdict: dict):
    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.collect", return_value=([{"ticker": "AAPL", "price": price}], 0))
    mocker.patch("main.collect_sector_momentum", return_value={})
    mocker.patch("main.run_policy_monitor",
                 return_value={"policy_risk_level": "low", "events": []})
    mocker.patch("main.check_open_positions", return_value=[])
    mocker.patch("main.send_trade_proposals_email")
    mocker.patch("main.revalidate_one", return_value=verdict)


def _morning_long(conn, prob=65):
    return db.save_prediction(conn, {
        "date": "2026-07-30", "run_type": "pre_market", "ticker": "AAPL",
        "direction": "long", "entry_price": 100.0, "tp_price": 106.0,
        "sl_price": 98.0, "probability_pct": prob, "confidence": "medium"})


def test_vix_blocks_at_1610_but_not_at_1500(tmp_db_path, mocker):
    """E4 in einem Durchlauf: derselbe VIX von 40 laesst das Morgensignal
    stehen und verwirft es um 16:10."""
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    pid = _morning_long(conn)
    conn.commit(); conn.close()

    mocker.patch("main.fetch_market_context", return_value={"vix_level": 40.0})
    _mock_16_10(mocker, price=101.0,
                verdict={"verdict": "bestaetigt", "probability_pct": 71,
                         "reason": "ok"})
    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    row = conn.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row["revision_verdict"] == "verworfen"
    assert row["status"] == "open", "verworfene Signale bleiben auswertbar"
    n = conn.execute("SELECT COUNT(*) AS n FROM predictions").fetchone()["n"]
    assert n == 1, "ein hart verworfenes Signal erzeugt keine neue Zeile"
    rej = conn.execute(
        "SELECT rule, enforced FROM guardrail_rejects").fetchall()
    assert any(r["rule"] == "vix_no_new_longs" and r["enforced"] == 1 for r in rej)
    conn.close()


def test_exactly_one_open_signal_survives_the_revision(tmp_db_path, mocker):
    """E3: die Grundlage dafuer, dass kein Aggregat doppelt zaehlt."""
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    _morning_long(conn)
    conn.commit(); conn.close()

    mocker.patch("main.fetch_market_context", return_value={"vix_level": 18.0})
    _mock_16_10(mocker, price=101.0,
                verdict={"verdict": "bestaetigt", "probability_pct": 71,
                         "reason": "ok"})
    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    conn = db.connect(str(tmp_db_path))
    assert conn.execute("SELECT COUNT(*) AS n FROM predictions").fetchone()["n"] == 2
    open_rows = db.load_open_predictions(conn)
    assert len(open_rows) == 1
    assert open_rows[0]["run_type"] == "trade_proposals"
    conn.close()


def test_evaluator_closes_exactly_one_outcome(tmp_db_path, mocker):
    """Der eigentliche Schaden waere hier sichtbar: zwei Outcomes fuer eine Idee
    verdoppeln Trefferquote und P&L in jeder Auswertung."""
    import pandas as pd
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    _morning_long(conn)
    conn.commit(); conn.close()

    mocker.patch("main.fetch_market_context", return_value={"vix_level": 18.0})
    _mock_16_10(mocker, price=101.0,
                verdict={"verdict": "bestaetigt", "probability_pct": 71,
                         "reason": "ok"})
    from main import run_trade_proposals
    run_trade_proposals(date="2026-07-30", db_path=str(tmp_db_path))

    provider = MagicMock()
    provider.get_ohlc_after.return_value = pd.DataFrame(
        {"High": [107.0], "Low": [100.5], "Close": [106.5]},
        index=["2026-07-31"])
    from src.evaluator import evaluate_open_predictions
    conn = db.connect(str(tmp_db_path))
    closed = evaluate_open_predictions(conn=conn, today="2026-07-31",
                                       price_provider=provider)
    assert closed == 1
    assert conn.execute("SELECT COUNT(*) AS n FROM outcomes").fetchone()["n"] == 1
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_trade_proposals_flow.py -v`
Expected: Erwartet wird **PASS** — der Produktivcode steht bereits. Schlägt hier etwas
fehl, ist es ein echter Fehler aus Task 13/15 und wird dort behoben, nicht durch
Abschwächen des Tests.

- [ ] **Step 3: Live-Verifikation**

Wie bei Plan 1 gegen die echten Systeme:

```bash
# 1. Migration gegen eine bestehende DB (Kopie, nie das Original)
cp data/tracking.db /tmp/migrationstest.db
python -c "from src import db; c = db.connect('/tmp/migrationstest.db'); db.init_schema(c); \
print([r['name'] for r in c.execute('PRAGMA table_info(predictions)')])"
# erwartet: superseded_by und revision_verdict in der Liste

# 2. Docker-Smoke-Test gegen eine Wegwerf-DB, NICHT gegen data/
docker compose run --rm -v /tmp/dbtest:/app/data trading-harry --run-type trade_proposals

# 3. Echter Lauf gegen Capital.com, nachdem ein pre_market-Lauf Signale erzeugt hat
python main.py --run-type pre_market
python main.py --run-type trade_proposals
```

Zu prüfen: die 16:10-Mail kommt an, `predictions` enthält je Ticker genau eine offene
Zeile, `guardrail_rejects` hat Zeilen mit `enforced=0` aus dem Morgenlauf und ggf.
`enforced=1` aus dem 16:10-Lauf, und `cost_tracking` weist den 16:10-Lauf mit
**deutlich unter 1 EUR** aus. Liegt er höher, stimmt E1 nicht und der Prompt oder die
Eingabemenge muss nachgesehen werden.

- [ ] **Step 4: Run the full suite**

Run: `pytest tests/ --cov=src --cov-fail-under=80`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_trade_proposals_flow.py
git commit -m "test: End-to-End-Nachweis fuer harte Durchsetzung und Abloesung (E3, E4)"
```

---

# Schnitt 6 — `close`, Weekly-Mail und Doku

---

### Task 17: `close` holt die Schlusskurse aller Ticker

**Files:**
- Modify: `main.py` — `run_close()`
- Test: `tests/unit/test_main.py`

**Interfaces:**
- Consumes: `collect()`, `evaluate_open_predictions()`, `cleanup_old_data()`
- Produces: nichts Neues

B.6: die Schlusskurse landeten bisher nur implizit über den Evaluator in der DB — und auch
das nur für Ticker mit offener Prediction. Für `db_momentum` und die relative Stärke am
Folgetag braucht es sie lückenlos.

**Punkt 2 aus B.6 bleibt bewusst stehen:** `evaluate_open_predictions()` wird **nicht**
entfernt. Da `evaluate` als Run-Type entfällt, schriebe sonst zwischen 3B und 3D niemand
mehr `outcomes`-Zeilen, und das Learning Modul hätte keine Trainingsdaten aus dieser Zeit.
Erst 3D übernimmt die Auswertung.

- [ ] **Step 1: Write the failing test**

```python
def test_close_pulls_closing_prices_for_all_tickers(tmp_db_path, mocker):
    """B.6: sonst fehlen Schlusskurse fuer jeden Ticker ohne offene Position —
    und damit die Basis fuer db_momentum und relative Staerke am Folgetag."""
    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.evaluate_open_predictions", return_value=0)
    collect_mock = mocker.patch("main.collect", return_value=([], 0))

    from main import run_close
    run_close(date="2026-07-30", db_path=str(tmp_db_path))

    assert collect_mock.call_count == 2
    passed = [set(c.kwargs["tickers"]) for c in collect_mock.call_args_list]
    assert set(config.SP500_MVP_TICKERS) in passed


def test_close_still_evaluates_open_predictions(tmp_db_path, mocker):
    """B.6/Punkt 2: bis 3D das Lernmodul uebernimmt, ist close die EINZIGE
    Stelle, die outcomes-Zeilen schreibt."""
    mocker.patch("main.CapitalComProvider", return_value=MagicMock())
    mocker.patch("main.FinnhubProvider", return_value=MagicMock())
    mocker.patch("main.collect", return_value=([], 0))
    ev = mocker.patch("main.evaluate_open_predictions", return_value=3)

    from main import run_close
    run_close(date="2026-07-30", db_path=str(tmp_db_path))
    ev.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_main.py -k close -v`
Expected: FAIL — `collect_mock.call_count == 0`

- [ ] **Step 3: Write minimal implementation**

`run_close()` in `main.py` ersetzen:

```python
def run_close(date: str, db_path: str) -> None:
    """Close-Run (22:30 Berlin): Schlusskurse aller Ticker holen, offene
    Predictions auswerten, DB aufraeumen. Kein Claude, keine Mail.

    Die Schlusskurse kommen seit Sprint 3B / Plan 2 (B.6) fuer ALLE Ticker, nicht
    mehr nur implizit ueber den Evaluator fuer die mit offener Position: db_momentum
    und die relative Staerke mitteln am Folgetag ueber die gesamte Ticker-Liste.

    evaluate_open_predictions() bleibt hier, bis das Learning Modul (3D) die
    Auswertung uebernimmt — mit dem entfallenen evaluate-Run ist close sonst die
    einzige Stelle, die ueberhaupt noch outcomes-Zeilen schreibt."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    price_provider = CapitalComProvider()
    earnings_provider = FinnhubProvider()

    _tickers = (config.SP500_FULL_TICKERS if config.USE_FULL_SP500
                else config.SP500_MVP_TICKERS)
    collect(tickers=_tickers, price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn, date=date, run_type="close")
    cc_tickers = [d["ticker"] for d in build_commodity_crypto_inputs()]
    collect(tickers=cc_tickers, price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn, date=date, run_type="close")

    n = evaluate_open_predictions(conn=conn, today=date, price_provider=price_provider)
    log.info(f"Close run: {n} predictions evaluated")
    db.cleanup_old_data(conn)
    conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add main.py tests/unit/test_main.py
git commit -m "feat: close holt Schlusskurse aller Ticker (B.6)"
```

---

### Task 18: Weekly-Aggregate in `src/db.py`

**Files:**
- Modify: `src/db.py` — fünf neue Lesefunktionen
- Test: `tests/unit/test_db.py`

**Interfaces:**
- Consumes: `predictions`, `outcomes`, `guardrail_rejects`, `skipped_tickers`, `ticker_status`, `ticker_sectors`
- Produces:
  - `db.load_revision_effectiveness(conn, since_date) -> dict`
  - `db.load_revision_verdict_stats(conn, since_date) -> list[sqlite3.Row]`
  - `db.load_guardrail_reject_stats(conn, since_date) -> list[sqlite3.Row]`
  - `db.load_skipped_ticker_stats(conn, since_date) -> list[sqlite3.Row]`
  - `db.load_sector_mapping_coverage(conn) -> dict`

**Block 1 ist gegenüber B.9 neu formuliert** (Spec 7.3): „Trefferquote getrennt nach
`run_type`" geht durch E3 nicht mehr, weil jede Trade-Idee genau ein Outcome hat. Der
Ersatz vergleicht **bestätigte gegen abgelehnte** Signale — das beantwortet direkter, ob
der 16:10-Lauf seine Kosten verdient.

**Datumsgrenze:** Die Gruppe „nie geprüft" enthält sonst auch alle Predictions von vor dem
ersten `trade_proposals`-Lauf. `load_revision_effectiveness()` grenzt deshalb auf
`MIN(date) FROM predictions WHERE run_type='trade_proposals'` ein und gibt bei fehlendem
16:10-Lauf leere Gruppen zurück.

- [ ] **Step 1: Write the failing test**

```python
def _outcome(conn, pred_id, correct, pl):
    conn.execute(
        """INSERT INTO outcomes (prediction_id, evaluated_date,
                                 correct_direction_eod, profit_loss_eur)
           VALUES (?, '2026-07-31', ?, ?)""",
        (pred_id, 1 if correct else 0, pl))
    conn.commit()


def test_revision_effectiveness_splits_confirmed_from_rejected(in_memory_db):
    """Der Kern von B.9/Block 1 in der Fassung nach E3."""
    db.init_schema(in_memory_db)
    good = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "trade_proposals",
        "ticker": "AAPL", "direction": "long"})
    bad = db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "ticker": "NVDA", "direction": "long"})
    db.record_revision(in_memory_db, bad, verdict="gedreht")
    _outcome(in_memory_db, good, correct=True, pl=25.0)
    _outcome(in_memory_db, bad, correct=False, pl=-30.0)

    out = db.load_revision_effectiveness(in_memory_db, since_date="2026-07-01")
    assert out["confirmed"]["total"] == 1 and out["confirmed"]["correct"] == 1
    assert out["rejected"]["total"] == 1 and out["rejected"]["correct"] == 0
    assert out["confirmed"]["pl_eur"] == 25.0
    assert out["rejected"]["pl_eur"] == -30.0


def test_revision_effectiveness_excludes_rows_before_the_first_1610_run(in_memory_db):
    """Sonst waechst 'nie geprueft' auf Dauer als Altlast mit."""
    db.init_schema(in_memory_db)
    old = db.save_prediction(in_memory_db, {
        "date": "2026-07-01", "run_type": "pre_market",
        "ticker": "MSFT", "direction": "long"})
    _outcome(in_memory_db, old, correct=False, pl=-10.0)
    db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "trade_proposals",
        "ticker": "AAPL", "direction": "long"})

    out = db.load_revision_effectiveness(in_memory_db, since_date="2026-06-01")
    assert out["unchecked"]["total"] == 0, "Altlast vor dem ersten 16:10-Lauf"


def test_revision_effectiveness_is_empty_without_any_1610_run(in_memory_db):
    db.init_schema(in_memory_db)
    db.save_prediction(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market",
        "ticker": "AAPL", "direction": "long"})
    out = db.load_revision_effectiveness(in_memory_db, since_date="2026-07-01")
    assert out["confirmed"]["total"] == 0
    assert out["rejected"]["total"] == 0


def test_revision_verdict_stats_group_by_verdict(in_memory_db):
    db.init_schema(in_memory_db)
    for verdict in ("bestaetigt", "bestaetigt", "gedreht"):
        pid = db.save_prediction(in_memory_db, {
            "date": "2026-07-30", "run_type": "pre_market",
            "ticker": "AAPL", "direction": "long"})
        db.record_revision(in_memory_db, pid, verdict=verdict)
    rows = {r["revision_verdict"]: r["n"]
            for r in db.load_revision_verdict_stats(in_memory_db, "2026-07-01")}
    assert rows == {"bestaetigt": 2, "gedreht": 1}


def test_guardrail_reject_stats_split_soft_from_hard(in_memory_db):
    """enforced trennt jetzt sinnvoll: 0 = Warnung aus pre_market,
    1 = Ablehnung aus trade_proposals."""
    db.init_schema(in_memory_db)
    db.log_guardrail_reject(in_memory_db, {
        "date": "2026-07-30", "run_type": "pre_market", "ticker": "AAPL",
        "direction": "long", "rule": "vix_no_new_longs", "detail": "x", "enforced": 0})
    db.log_guardrail_reject(in_memory_db, {
        "date": "2026-07-30", "run_type": "trade_proposals", "ticker": "AAPL",
        "direction": "long", "rule": "vix_no_new_longs", "detail": "x", "enforced": 1})
    rows = db.load_guardrail_reject_stats(in_memory_db, "2026-07-01")
    by_key = {(r["rule"], r["enforced"]): r["n"] for r in rows}
    assert by_key[("vix_no_new_longs", 0)] == 1
    assert by_key[("vix_no_new_longs", 1)] == 1


def test_sector_mapping_coverage_counts_mapped_tickers(in_memory_db):
    """B.10 nennt die Abdeckung als Voraussetzung dafuer,
    SECTOR_GUARDRAIL_STRICT irgendwann auf True zu stellen."""
    db.init_schema(in_memory_db)
    sid = in_memory_db.execute(
        "SELECT id FROM sectors WHERE name='Retail'").fetchone()["id"]
    in_memory_db.execute(
        "INSERT INTO ticker_sectors (ticker, sector_id) VALUES ('AMZN', ?)", (sid,))
    in_memory_db.commit()
    out = db.load_sector_mapping_coverage(in_memory_db)
    assert out["mapped"] == 1
    assert out["total"] == len(config.SP500_MVP_TICKERS)
    assert 0.0 <= out["pct"] <= 100.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_db.py -k "revision_effectiveness or verdict_stats or reject_stats or mapping_coverage" -v`
Expected: FAIL mit `AttributeError: module 'src.db' has no attribute 'load_revision_effectiveness'`

- [ ] **Step 3: Write minimal implementation**

In `src/db.py` ergänzen:

```python
def _first_trade_proposals_date(conn: sqlite3.Connection) -> str | None:
    """Tag des ersten trade_proposals-Laufs. Davor kann es kein revision_verdict
    gegeben haben — ohne diese Grenze waechst die Gruppe 'nie geprueft' auf Dauer
    als Altlast mit und die Auswertung wird unbrauchbar."""
    row = conn.execute(
        "SELECT MIN(date) AS d FROM predictions WHERE run_type = 'trade_proposals'"
    ).fetchone()
    return row["d"] if row and row["d"] else None


def load_revision_effectiveness(
    conn: sqlite3.Connection, since_date: str,
) -> dict:
    """B.9/Block 1 in der Fassung nach E3: verdient der 16:10-Lauf seine Kosten?

    Durch die Abloesung hat jede Trade-Idee genau EIN Outcome — 'Trefferquote nach
    run_type' waere damit sinnlos. Verglichen werden stattdessen drei Gruppen:
      confirmed — vom 16:10-Lauf bestaetigte Signale (run_type='trade_proposals')
      rejected  — vom 16:10-Lauf abgelehnte (revision_verdict gedreht/verworfen)
      unchecked — nie geprueft (z.B. weil der Lauf ausfiel)

    Liegt die Trefferquote der abgelehnten unter der der bestaetigten, filtert der
    Lauf richtig."""
    start = _first_trade_proposals_date(conn)
    empty = {"total": 0, "correct": 0, "pl_eur": 0.0}
    if start is None:
        return {"confirmed": dict(empty), "rejected": dict(empty),
                "unchecked": dict(empty), "since": since_date}
    floor = max(since_date, start)

    def _agg(where: str) -> dict:
        r = conn.execute(
            f"""SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN o.correct_direction_eod
                                         THEN 1 ELSE 0 END), 0) AS correct,
                       COALESCE(SUM(o.profit_loss_eur), 0) AS pl
                FROM outcomes o JOIN predictions p ON p.id = o.prediction_id
                WHERE p.date >= ? AND {where}""",
            (floor,),
        ).fetchone()
        return {"total": int(r["total"]), "correct": int(r["correct"]),
                "pl_eur": round(float(r["pl"]), 2)}

    return {
        "confirmed": _agg("p.run_type = 'trade_proposals'"),
        "rejected":  _agg("p.run_type = 'pre_market' AND "
                          "p.revision_verdict IN ('gedreht', 'verworfen')"),
        "unchecked": _agg("p.run_type = 'pre_market' AND "
                          "p.revision_verdict IS NULL"),
        "since": floor,
    }


def load_revision_verdict_stats(
    conn: sqlite3.Connection, since_date: str,
) -> list[sqlite3.Row]:
    """B.9/Block 2: wie oft wurde bestaetigt / geschwaecht / gedreht / verworfen,
    und wie liefen die Gruppen danach."""
    return conn.execute(
        """SELECT p.revision_verdict AS revision_verdict, COUNT(*) AS n,
                  ROUND(AVG(COALESCE(o.profit_loss_eur, 0)), 2) AS avg_pl
           FROM predictions p
           LEFT JOIN outcomes o ON o.prediction_id = p.id
           WHERE p.date >= ? AND p.revision_verdict IS NOT NULL
           GROUP BY p.revision_verdict
           ORDER BY n DESC""",
        (since_date,),
    ).fetchall()


def load_guardrail_reject_stats(
    conn: sqlite3.Connection, since_date: str,
) -> list[sqlite3.Row]:
    """B.9/Block 3: welche Guardrails greifen wie oft — getrennt nach weicher
    Warnung (enforced=0, pre_market) und harter Ablehnung (enforced=1, 16:10)."""
    return conn.execute(
        """SELECT rule, enforced, COUNT(*) AS n
           FROM guardrail_rejects
           WHERE date >= ?
           GROUP BY rule, enforced
           ORDER BY n DESC""",
        (since_date,),
    ).fetchall()


def load_skipped_ticker_stats(
    conn: sqlite3.Connection, since_date: str,
) -> list[sqlite3.Row]:
    """B.9/Block 4: welcher Ticker wurde diese Woche wie oft und warum
    uebersprungen, plus sein kumulativer Stand aus ticker_status."""
    return conn.execute(
        """SELECT s.ticker, COUNT(*) AS n_week,
                  GROUP_CONCAT(DISTINCT s.reason) AS reasons,
                  ts.skip_count AS skip_total, ts.inactive, ts.retry_after
           FROM skipped_tickers s
           LEFT JOIN ticker_status ts ON ts.ticker = s.ticker
           WHERE s.date >= ?
           GROUP BY s.ticker
           ORDER BY n_week DESC""",
        (since_date,),
    ).fetchall()


def load_sector_mapping_coverage(conn: sqlite3.Connection) -> dict:
    """Anteil der Ticker mit Sub-Sektor-Zuordnung. B.10 nennt eine stabil hohe
    Quote als Voraussetzung dafuer, SECTOR_GUARDRAIL_STRICT auf True zu stellen."""
    universe = (config.SP500_FULL_TICKERS if config.USE_FULL_SP500
                else config.SP500_MVP_TICKERS)
    marks = ",".join("?" * len(universe))
    row = conn.execute(
        f"""SELECT COUNT(*) AS n FROM ticker_sectors
            WHERE sector_id IS NOT NULL AND ticker IN ({marks})""",
        universe,
    ).fetchone()
    mapped, total = int(row["n"]), len(universe)
    return {"mapped": mapped, "total": total,
            "pct": round(mapped / total * 100, 1) if total else 0.0}
```

> **Vor dem Schreiben prüfen:** ob `skipped_tickers` die Spalte `reason` führt und
> `ticker_status` die Spalten `skip_count`, `inactive`, `retry_after`. Beides wurde in
> Plan 1 angelegt; weichen die Namen ab, hier anpassen statt raten.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/db.py tests/unit/test_db.py
git commit -m "feat: Weekly-Aggregate fuer die vier B.9-Bloecke"
```

---

### Task 19: Weekly-Mail erweitern und `hold_days_recommended` in der Tagesmail

**Files:**
- Modify: `src/email_sender.py` — `render_weekly_html()`, `_row_for_setup()`, `_section_stocks()`
- Modify: `main.py` — `run_weekly()` lädt die neuen Aggregate
- Test: `tests/unit/test_email_sender.py`

**Interfaces:**
- Consumes: die fünf Lesefunktionen aus Task 18
- Produces: nichts Neues

- [ ] **Step 1: Write the failing test**

```python
def test_daily_table_has_a_hold_days_column():
    """B.11: hold_days_recommended ist Pflichtfeld der Analyse, stand aber nie
    in der Mail."""
    from src.email_sender import render_daily_html
    html = render_daily_html({
        "date": "2026-07-30", "run_type": "pre_market",
        "top_long": [{"ticker": "AAPL", "total_score": 7.6, "probability_pct": 65,
                      "current_price": 178.0, "tp_price": 184.0, "sl_price": 176.0,
                      "rr_ratio": 3.0, "hold_days_recommended": 2,
                      "summary": "ok", "scores": {}}],
        "top_short": [], "commodities_crypto": [], "trends": [],
        "briefing": [], "portfolio_recs": [],
        "cost_summary": {"total_eur": 3.3}, "yesterday_outcomes": {},
    })
    assert "Haltedauer" in html
    assert "<td>2</td>" in html


WEEKLY_PAYLOAD = {
    "week_label": "KW31", "long_total": 4, "long_correct": 3, "long_avg_pl": 12.0,
    "short_total": 2, "short_correct": 1, "short_avg_pl": -4.0,
    "total_pl_eur": 28.0, "trades": [],
    "cost_summary": {"total_eur": 18.4},
    "revision_effectiveness": {
        "confirmed": {"total": 6, "correct": 4, "pl_eur": 55.0},
        "rejected":  {"total": 3, "correct": 0, "pl_eur": -41.0},
        "unchecked": {"total": 1, "correct": 1, "pl_eur": 9.0},
        "since": "2026-07-25"},
    "verdict_stats": [{"revision_verdict": "bestaetigt", "n": 6, "avg_pl": 9.2},
                      {"revision_verdict": "gedreht", "n": 3, "avg_pl": -13.7}],
    "guardrail_stats": [{"rule": "vix_no_new_longs", "enforced": 1, "n": 2},
                        {"rule": "sector_momentum_partial", "enforced": 0, "n": 9}],
    "skipped_stats": [{"ticker": "FAKE", "n_week": 4, "reasons": "no data",
                       "skip_total": 12, "inactive": 0, "retry_after": None}],
    "sector_coverage": {"mapped": 18, "total": 20, "pct": 90.0},
}


def test_weekly_shows_confirmed_versus_rejected():
    from src.email_sender import render_weekly_html
    html = render_weekly_html(WEEKLY_PAYLOAD)
    assert "bestätigt" in html and "abgelehnt" in html
    assert "4/6" in html and "0/3" in html


def test_weekly_shows_all_four_blocks():
    from src.email_sender import render_weekly_html
    html = render_weekly_html(WEEKLY_PAYLOAD)
    assert "gedreht" in html                    # Block 2
    assert "vix_no_new_longs" in html           # Block 3
    assert "FAKE" in html                       # Block 4
    assert "90.0" in html or "90,0" in html     # Mapping-Abdeckung


def test_weekly_survives_a_week_without_any_1610_run():
    """Erste Woche nach dem Umbau: alle neuen Bloecke sind leer."""
    from src.email_sender import render_weekly_html
    payload = {**WEEKLY_PAYLOAD, "revision_effectiveness": None,
               "verdict_stats": [], "guardrail_stats": [], "skipped_stats": [],
               "sector_coverage": None}
    html = render_weekly_html(payload)
    assert "KW31" in html          # kein Absturz, Grundgeruest steht
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_email_sender.py -k "hold_days or weekly" -v`
Expected: FAIL — „Haltedauer" fehlt, die neuen Blöcke fehlen

- [ ] **Step 3: Write minimal implementation**

In `_row_for_setup()` eine Zelle vor der Begründung ergänzen:

```python
        f'<td>{_h(a.get("hold_days_recommended"))}</td>'
```

In `_section_stocks()` den `head`-String erweitern:

```python
        '<th>ATR/Tag</th><th>Range/Tag</th><th>Haltedauer</th>'
        '<th>Flags</th><th>Begründung</th></tr>'
```

> Die Spaltenzahl in `head` und `_row_for_setup()` muss übereinstimmen — `Haltedauer`
> kommt in beiden **vor** `Flags`.

In `render_weekly_html()` vor dem Disclaimer die neuen Blöcke einhängen:

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


def _weekly_simple_table(title: str, headers: list[str],
                         rows: list[dict], keys: list[str]) -> str:
    """Generische Tabelle fuer die Weekly-Bloecke 2-4."""
    if not rows:
        return f'<h2>{title}</h2><p><i>Keine Einträge.</i></p>'
    head = "".join(f'<th>{h}</th>' for h in headers)
    body = "".join(
        '<tr>' + "".join(f'<td>{_h(r[k] if k in r.keys() else None)}</td>'
                         for k in keys) + '</tr>'
        for r in rows
    )
    return (f'<h2>{title}</h2>'
            '<table border="1" cellpadding="4" cellspacing="0">'
            f'<tr>{head}</tr>{body}</table>')
```

und in `render_weekly_html()` unmittelbar vor der Disclaimer-Zeile:

```python
        + _weekly_revision_block(payload.get("revision_effectiveness"))
        + _weekly_simple_table(
            "Signal-Veränderungen", ["Urteil", "Anzahl", "Ø P/L"],
            payload.get("verdict_stats") or [],
            ["revision_verdict", "n", "avg_pl"])
        + _weekly_simple_table(
            "Guardrails", ["Regel", "hart?", "Anzahl"],
            payload.get("guardrail_stats") or [], ["rule", "enforced", "n"])
        + _weekly_simple_table(
            "Übersprungene Ticker", ["Ticker", "diese Woche", "Gründe",
                                     "gesamt", "inaktiv", "Retry ab"],
            payload.get("skipped_stats") or [],
            ["ticker", "n_week", "reasons", "skip_total", "inactive", "retry_after"])
        + (f'<h2>Sub-Sektor-Abdeckung</h2><p>'
           f'{_h((payload.get("sector_coverage") or {}).get("mapped"))} von '
           f'{_h((payload.get("sector_coverage") or {}).get("total"))} Tickern '
           f'gemappt ({_h((payload.get("sector_coverage") or {}).get("pct"))} %)</p>'
           if payload.get("sector_coverage") else "")
```

In `main.py`, `run_weekly()` das Payload erweitern:

```python
    since = (date_cls.fromisoformat(date) - timedelta(days=7)).isoformat()
    payload = {
        "week_label": week_label, **agg,
        "revision_effectiveness": db.load_revision_effectiveness(conn, since),
        "verdict_stats":   db.load_revision_verdict_stats(conn, since),
        "guardrail_stats": db.load_guardrail_reject_stats(conn, since),
        "skipped_stats":   db.load_skipped_ticker_stats(conn, since),
        "sector_coverage": db.load_sector_mapping_coverage(conn),
        "cost_summary": {"total_eur": 0.0, "cache_hit_rate": 0.0,
                         "input_tokens": 0, "output_tokens": 0,
                         "web_search_calls": 0, "aborted_at_phase": None},
    }
```

- [ ] **Step 4: Run the full suite**

Run: `pytest tests/ --cov=src --cov-fail-under=80`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/email_sender.py main.py tests/
git commit -m "feat: Weekly um vier Bloecke, Haltedauer in der Tagesmail (B.9, B.11)"
```

---

### Task 20: Dokumentation nachziehen

**Files:**
- Modify: `docs/superpowers/specs/PROJECT_STATUS.md`
- Modify: `CLAUDE.md`
- Modify: `docs/ARCHITECTURE.md`

**Interfaces:** keine — reine Doku.

- [ ] **Step 1: PROJECT_STATUS.md korrigieren**

1. **Abschnitt F.1 richtigstellen.** Die Hochrechnung „80 Slots aus `MAX_DEEP_ANALYSIS`"
   beschreibt einen Deckel, den es nicht gibt: `MAX_DEEP_ANALYSIS` und `BATCH_SIZE_QUICK`
   werden **nirgends** referenziert. `quick_filter_batch()` bekommt alle Ticker in *einem*
   Haiku-Call, und `analyze_assets()` analysiert jeden nicht-`exclude`ten Ticker.
   Ergänzen: bei 500 Tickern begrenzt nichts ausser `CostCapExceeded`; der Fix gehört
   zu C.4.
2. **B.13 nach 3F verschieben** mit der Begründung aus E2 samt korrigierter
   Actions-Minuten-Tabelle (~790 statt ~1 100 ohne Parallelisierung).
3. **B.2, B.3 und B.9 auf E1–E5 umschreiben** — insbesondere B.9/Block 1, der in der
   alten Fassung nicht mehr berechenbar ist.
4. **B.12 auf „Plan 2 umgesetzt"** setzen, mit Verweis auf diese Plan-Datei.
5. **Sprint-Tabelle in Abschnitt 2:** 3B auf ✅ setzen.

- [ ] **Step 2: `CLAUDE.md` nachziehen**

- Run-Type-Liste in „Wichtige Befehle" und im Docker-Abschnitt auf `pre_market`,
  `trade_proposals`, `close`, `weekly` aktualisieren
- Unter „Wichtige Designentscheidungen" zwei Zeilen ergänzen:
  - `trade_proposals` prüft ohne Websuche nach und löst die `pre_market`-Prediction über
    `status='superseded'` ab — je Trade-Idee existiert immer genau **ein** offenes Signal
  - B.3-Checks werden in beiden Runs erhoben, aber nur um 16:10 durchgesetzt
    (`enforce`-Parameter in `signal_checks`)
- **Nicht** ergänzen: Verzeichnisbäume, Abhängigkeitslisten, Env-Variablen,
  Scoring-Gewichte oder Sprint-Historie — die Datei ist bewusst schlank.

- [ ] **Step 3: `docs/ARCHITECTURE.md` nachziehen**

- `src/signal_checks.py` und `src/revalidation.py` als Module aufnehmen
- Phasenreihenfolge korrigieren: 1c und 1d neu, Ranking (4) **vor** Portfolio-Check (4a)
- `position_check` als Modulbeschreibung entfernen

- [ ] **Step 4: Verifikation**

```bash
grep -rn "midday\|position_check\|run_evaluate" --include="*.md" \
  CLAUDE.md docs/ARCHITECTURE.md docs/superpowers/specs/PROJECT_STATUS.md
```

Erwartet: Treffer nur noch in historischen Abschnitten (Sprint-1/2-Tabellen, Bug-Historie)
— nirgends als Beschreibung des **aktuellen** Stands.

```bash
pytest tests/ --cov=src --cov-fail-under=80
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/ARCHITECTURE.md docs/superpowers/specs/PROJECT_STATUS.md
git commit -m "docs: Sprint 3B / Plan 2 abschliessen, F.1-Rechnung korrigieren"
```

---

## Abschluss-Checkliste

Vor der Meldung „Plan 2 fertig":

- [ ] `pytest tests/ --cov=src --cov-fail-under=80` grün
- [ ] `grep -rn "midday\|position_check" --include="*.py" --include="*.yml" .` liefert
      ausserhalb von `venv/` keinen Treffer
- [ ] Migration gegen eine **Kopie** der produktiven `data/tracking.db` verifiziert
- [ ] Docker-Smoke-Test gegen eine Wegwerf-DB gelaufen
      (`docker compose run --rm -v /tmp/dbtest:/app/data trading-harry --run-type trade_proposals`)
- [ ] Ein echter `pre_market`-Lauf, gefolgt von einem echten `trade_proposals`-Lauf;
      16:10-Mail angekommen, Kosten des 16:10-Laufs **unter 1 EUR**
- [ ] In `predictions` existiert je Ticker und Tag genau **eine** offene Zeile
- [ ] `git log --oneline` zeigt einen Commit je Task
- [x] ~~**Nicht gepusht** — das macht Korbinian selbst~~
      → **überholt (Nachtrag 2026-08-03, präzisiert 2026-08-04):** Die 25 Commits sind
      bereits auf `main` gepusht; ein Feature-Branch existierte nie. Ausgeführt wurde der
      Code aber nie — `analyze.yml` steht auf `disabled_manually`, letzter Pipeline-Lauf
      2026-07-13. Die offenen Haken oben bleiben damit ein Gate vor der ersten
      Ausführung. Migration ✅ am 2026-08-04. S. PROJECT_STATUS.md, P2.4.
