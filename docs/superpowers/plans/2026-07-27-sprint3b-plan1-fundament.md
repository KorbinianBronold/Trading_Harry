# Sprint 3B / Plan 1: Fundament (Sektor-DB, ticker_status, Markt-Kontext, Gap-Erkennung)

> ⚠️ **HISTORISCH — abgeschlossen 2026-07-29, alle 14 Tasks.** Nicht als Ist-Zustand lesen
> und nicht mehr bearbeiten. Aktueller Stand: `docs/superpowers/specs/PROJECT_STATUS.md`
> (Sprint 3B, Abschnitt B / B.12).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alle additiven Bausteine für Sprint 3B bauen — Sub-Sektor-Datenbank mit Finnhub-Normalisierung, kumulativer `ticker_status`-Zähler mit Auto-Retry, persistierte Guardrail-Rejects, echter Markt-Kontext statt hardcodiertem `None`-Dict, Gap-Erkennung in Phase 1 und der B-05-Fix.

> **Stand 2026-07-27:** Tasks 1 und 2 sind bereits implementiert und committet
> (`7a11a00`, Branch `sprint3b/plan1-fundament`). Offen ist dort nur noch der
> `TICKER_MAP`-Abgleich, der den `verify_epics`-Output braucht. Tasks 3–14 sind
> unverändert offen.

**Architecture:** Ausschliesslich **additive** Änderungen. Die bestehende Pipeline (`pre_market`, `midday`, `evaluate`, `close`, `weekly`, `position_check`) läuft nach diesem Plan unverändert weiter — es kommen nur neue Tabellen, neue Helper und ein neuer Claude-Call dazu. Der eigentliche Cron-/Pipeline-Umbau (B.1, B.2, B.4, B.5, B.6, B.9 sowie die B.3-Checks) ist **nicht** Teil dieses Plans und wird in einem separaten Plan 2 geplant, sobald das Fundament steht und der `verify_epics`-Output vorliegt.

**Tech Stack:** Python 3.12, SQLite (stdlib `sqlite3`), pandas, requests, Anthropic Claude API (`claude-sonnet-4-6` + `web_search`), Capital.com REST API, pytest + pytest-mock.

**Spec reference:** `docs/superpowers/specs/PROJECT_STATUS.md`, Abschnitte B.3, B.7, B.8, B.10, B.11 — inklusive der in der Planungssession vom 2026-07-27 getroffenen Entscheidungen D1–D6 (s. „Entscheidungen" unten).

---

## Entscheidungen aus der Planungssession (2026-07-27)

Diese Entscheidungen schliessen die in PROJECT_STATUS.md offen markierten Punkte:

| # | Offener Punkt | Entscheidung |
|---|---|---|
| D1 | B.3 — Datenquelle Sektor-ETFs + VIX | Capital.com, aber mit vorgeschaltetem Verify-Skript (`setup/verify_epics.py`). Die echten Epic-Namen kommen aus einem echten Lauf gegen die Demo-API, nicht aus Annahmen. |
| D7 | B.10 — Sektor-Granularität | **21 Sub-Sektoren statt 11 GICS-Sektoren** (Entscheidung 2026-07-27). Ein Halbleiter-Setup wird gegen SOXX geprüft, nicht gegen den breiten XLK, in dem Software und Hardware das Signal verwässern. Liste s. `config.SUB_SECTOR_ETFS`. |
| D2 | B.3 — Marktbreite (A/D-Ratio) | Eigener Claude-Call mit `web_search` (`src/market_context.py`), liefert strukturiertes JSON. Befüllt die bereits existierende, aber leere `market_context`-Tabelle **und** ersetzt das hardcodierte `market_ctx`-Dict in `main.py:226`. Läuft in `pre_market` **und** `trade_proposals` (also in `run_pipeline`). |
| D3 | B.7 — Reset des `inactive`-Flags | Zweigleisig: automatischer Retry nach 30 Tagen über `ticker_status.retry_after` **plus** manuelles CLI-Kommando `--reactivate`. |
| D4 | B.7 — Retention | `news_summaries` 90 → 30 Tage, `trend_analyses` unverändert 180, `skipped_tickers`-Events 30 → 90 Tage, `ticker_status` nie automatisch zurückgesetzt. |
| D5 | B.10 — Finnhub → Sub-Sektor Normalisierung | Alias-Dict `config.SECTOR_ALIASES` im Code (in git versioniert, unit-testbar). Unauflösbare Werte: `sector_id` NULL + WARN-Log mit dem Rohwert. **Bewusst ungemappt**, weil Capital.com keinen passenden ETF führt: Communication-Werte (`Communication Services`, `Media`, `Entertainment`, `Interactive Media & Services`, `Telecommunication*`) sowie Chemie/Verpackung/Papier (`Chemicals`, `Packaging`, `Paper & Forest*`, `Construction Materials`). Grundregel: lieber ungemappt als falsch gemappt. |
| D9 | B.3 — Sektor-Momentum | **Hybrid aus zwei unabhängigen Signalen** (Entscheidung 2026-07-27): `etf_momentum` aus dem Sub-Sektor-ETF von Capital.com, `db_momentum` als Ø Tagesperformance aller Ticker des Sub-Sektors per SQL über `price_history` × `ticker_sectors` (min. 3 Ticker, sonst NULL). Getrennt gespeichert in neuer Tabelle `sector_momentum`, zusätzlich als Spalten an `predictions` und `guardrail_rejects`. Hartes Reject nur, wenn beide vorliegen **und** übereinstimmen; sonst weiche Warnung mit `enforced=0`. Kosten des DB-Signals: 0 EUR. |
| D8 | B.3 — Epic-Verifikation | Lauf vom 2026-07-27: von den ursprünglich 21 gewünschten ETFs führt Capital.com **8 nicht** (IGV, IHI, IYT, KBE, KIE, XLB, XLC, XPH). Ersetzt durch verifizierte Alternativen (VGT, XLV, XTN, KBWB, XLF, XME); Communication ersatzlos gestrichen. Endstand: 21 Sub-Sektoren auf 19 ETFs, **20/20 Epics bestätigt**, alle TRADEABLE, kein `TICKER_MAP`-Eintrag nötig. |
| D6 | B.10 — Guardrail bei unbekanntem Sektor | `config.SECTOR_GUARDRAIL_STRICT`, initial `False` (weich: durchlassen + Reject-Row mit `enforced=0`). **Die Durchsetzung selbst gehört in Plan 2** — dieser Plan legt nur die Infrastruktur (`guardrail_rejects`) und den Sektor-Lookup. |

---

## Global Constraints

Diese Regeln gelten für **jeden** Task in diesem Plan. Sie stammen aus `CLAUDE.md` und PROJECT_STATUS.md Abschnitt 5:

- **Migrations-Guards Pflicht:** Neue Spalten/Tabellen immer per `PRAGMA table_info(...)` bzw. `sqlite_master`-Abfrage prüfen, bevor `ALTER TABLE` / `CREATE TABLE` läuft. Nie direkt ausführen. (Regel 5)
- **Timezone:** Kein `datetime.now()` ohne Timezone. Immer `ZoneInfo("Europe/Berlin")`. (Regel 7)
- **Dokumentation Pflicht:** Jede neue Datei bekommt eine Modul-Beschreibung als Docstring, jede neue Funktion einen 1-2-Satz-Docstring. (Regel 13)
- **Capital.com ist alleiniger OHLC-Provider:** Kein neuer Code darf `yfinance` importieren oder als Fallback einführen. Kein `if config.CAPITAL_COM_API_KEY else ...`-Pattern. (Regel 4)
- **`SIMULATION_ONLY = True` ist sakrosankt:** Kein Code darf je `requests.post(...positions...)` für echte Orders aufrufen. Alle Capital.com-Aufrufe in diesem Plan sind **ausschliesslich lesend** (`GET`). (Regel 3)
- **Claude-Antworten immer über `extract_json_blob()`** parsen, nie `json.loads(result.text)` direkt. (Regel 11)
- **Kosten:** `config.MAX_COST_PER_RUN_EUR = 4.00`. Jeder neue Claude-Call muss über den `CostTracker` laufen. (Regel 12)
- **Tests nicht abschwächen:** Coverage-Ziel 80%. Bei Refactoring erst Tests anpassen, dann Code. (Regel 8)
- **`config.py` bleibt funktionsfrei** — nur Modul-Level-Konstanten (siehe Modul-Docstring). Logik gehört in `src/`.
- **Prompt-Versionierung:** Neue Prompts als `*_v1.txt` in `prompts/`, nie bestehende überschreiben. (Regel 10)
- **Doku-Pflege:** `README.md`, `docs/WORKFLOW.md`, `docs/SPECIFICATION.md` und `docs/superpowers/specs/2026-05-19-shares-future-mvp-design.md` sind bekannt veraltet und werden **nicht** angefasst. `CLAUDE.md`, `PROJECT_STATUS.md` und `docs/ARCHITECTURE.md` dagegen aktuell halten. (Regel 14)

**Test-Fixtures** (bereits vorhanden in `tests/conftest.py`, nicht neu anlegen):
- `in_memory_db` — frische `sqlite3.connect(":memory:")` mit `row_factory=sqlite3.Row`
- `tmp_db_path` — dateibasierter SQLite-Pfad unter `tmp_path`
- `sample_ticker_data` — realistisches TickerData-Dict wie von `data_collector` erzeugt

**Testlauf-Kommando:** `pytest tests/ --cov=src --cov-fail-under=80`

---

## File Structure

```
Trading_Harry/
├── config.py                                  [✅ SUB_SECTOR_ETFS, VIX_TICKER, SECTOR_ALIASES
│                                                modify — TICKER_MAX_SKIPS, TICKER_RETRY_AFTER_DAYS]
├── main.py                                    [modify — Markt-Kontext-Call statt hardcodiertem Dict,
│                                                        current_phase-Tracking für B-05]
├── prompts/
│   └── market_context_v1.txt                  [create — System-Prompt für den Markt-Kontext-Call]
├── src/
│   ├── db.py                                  [modify — sectors, ticker_sectors, ticker_status,
│   │                                                    guardrail_rejects, sector_momentum, Retention,
│   │                                                    Sektor-/Status-Helper, save_market_context]
│   ├── market_context.py                      [create — Phase 0b: Markt-Kontext via Claude + web_search]
│   ├── sector_momentum.py                     [create — D9: ETF- + DB-Momentum je Sub-Sektor]
│   ├── data_collector.py                      [modify — ticker_sectors organisch füllen, inaktive Ticker
│   │                                                    überspringen, Gap-Erkennung]
│   ├── ranking.py                             [modify — guardrail_rejects persistieren, Sektor aus DB]
│   └── providers/
│       └── capital_provider.py                [modify — search_markets(), TICKER_MAP-Ergänzung]
├── setup/
│   ├── verify_epics.py                        [create — einmaliges Verify-Tool für Sektor-ETF-/VIX-Epics]
│   └── historical_loader.py                   [modify — --reactivate CLI-Flag]
└── tests/
    └── unit/
        ├── test_verify_epics.py               [create]
        ├── test_market_context.py             [create]
        ├── test_sector_momentum.py            [create]
        ├── test_capital_provider.py           [modify — search_markets, TICKER_MAP-Abdeckung]
        ├── test_db.py                         [modify — neue Tabellen, Sektor-/Status-Helper, Retention]
        ├── test_data_collector.py             [modify — ticker_sectors, inactive-Skip, Gap-Erkennung]
        ├── test_ranking.py                    [modify — guardrail_rejects, Sektor aus DB]
        ├── test_historical_loader.py          [modify — --reactivate]
        └── test_main.py                       [modify — Markt-Kontext-Wiring, B-05]
```

**Verantwortlichkeiten der neuen Dateien:**
- `src/market_context.py` — **eine** Aufgabe: den tagesaktuellen Marktkontext (VIX, A/D-Ratio, Regime, Sektor-Rotation) beschaffen und als validiertes Dict zurückgeben. Kennt weder DB noch E-Mail; der Aufrufer persistiert.
- `setup/verify_epics.py` — **eine** Aufgabe: Capital.com nach Epics durchsuchen und einen kopierfertigen Report ausgeben. Kein Pipeline-Code, wird nie automatisch aufgerufen.
- `src/sector_momentum.py` — **eine** Aufgabe: beide Momentum-Signale je Sub-Sektor erheben und persistieren. Bewertet nichts; die Guardrail-Logik lebt in Plan 2.

---

## Task 1: Capital.com Market-Suche + Verify-Skript ✅ ERLEDIGT (`7a11a00`)

Grundlage für D1. Ohne dieses Tool stünden die Sub-Sektor-ETF-Epics auf geratenen Namen.

**Geliefert:**

| Datei | Inhalt |
|---|---|
| `src/providers/capital_provider.py` | `search_markets(search_term) -> list[dict]` — wrappt `GET /api/v1/markets?searchTerm=`, rein lesend, `[]` bei jedem Fehler |
| `setup/verify_epics.py` | `search_terms()`, `pick_best()`, `resolve()`, `format_report()`, `main(argv)` |
| `tests/unit/test_verify_epics.py` | 15 Tests, komplett offline gegen einen gemockten Provider |
| `tests/unit/test_capital_provider.py` | 3 Tests für `search_markets` + 3 für die Sub-Sektor-Konstanten |

**Abweichungen vom ursprünglichen Entwurf** (bewusst, beim Implementieren entschieden):
- `pick_best()` ergänzt: exaktes Epic schlägt Präfix-Treffer, handelbar schlägt ausgesetzt.
  Capital.coms Suche liefert zu kurzen Symbolen viele Fehltreffer.
- `--symbols`-Flag, um einzelne Symbole nachzuprüfen ohne alle 22 abzufragen.
- `sys.path`-Bootstrap, damit **beide** Aufrufvarianten funktionieren.
- Report weist zusätzlich `marketStatus` aus — ein gefundenes, aber nicht handelbares
  Epic ist für den Momentum-Check genauso wertlos wie gar keins.
- `main()` gibt einen Exit-Code zurück (1 bei fehlendem Key oder Session-Fehler).

**Nebenbefund (nicht behoben, gehört nicht in diesen Plan):** `python setup/historical_loader.py`
scheitert mit `ModuleNotFoundError: No module named 'config'`, obwohl `CLAUDE.md` genau
diesen Aufruf dokumentiert — dem Loader fehlt derselbe Bootstrap. Funktioniert aktuell
nur als `python -m setup.historical_loader`. Kandidat für Plan 2 oder einen eigenen Fix.

## Task 2: Sub-Sektor-ETF- und VIX-Konstanten + TICKER_MAP-Abgleich ✅ ERLEDIGT

> **Erledigt am 2026-07-27.** `config.SUB_SECTOR_ETFS` (21 Sub-Sektoren auf 19
> ETFs), `config.VIX_TICKER` und `config.SECTOR_ALIASES` (104 Einträge) stehen.
> Der Verify-Lauf meldet **20/20 bestätigt, alle TRADEABLE** — `TICKER_MAP`
> bleibt unverändert, weil jedes Symbol bei Capital.com exakt so heisst.
>
> Die Schritte unten sind historisch. Der ursprüngliche Entwurf ging von 21
> Wunsch-ETFs aus; acht davon existieren nicht (s. D8). Maßgeblich ist `config.py`.

**Files:**
- Modify: `config.py`
- Modify: `src/providers/capital_provider.py` (`TICKER_MAP`)
- Test: `tests/unit/test_capital_provider.py` (ergänzen)

**Interfaces:**
- Consumes: `verify_epics.main()`-Output aus Task 1
- Produces:
  - `config.SUB_SECTOR_ETFS: dict[str, str]` — Sub-Sektorname → ETF-Symbol, exakt 21 Einträge
  - `config.VIX_TICKER: str` — internes Ticker-Symbol für den Volatilitätsindex

- [x] **Step 2.1: Konstanten in `config.py` ergänzen** — erledigt in `7a11a00`

`config.SUB_SECTOR_ETFS` (21 Sub-Sektoren), `config.VIX_TICKER` und
`config.SECTOR_ALIASES` stehen in `config.py` zwischen `CRYPTO_TICKERS` und
`SP500_MIN_MARKET_CAP_B`. Maßgeblich ist die Datei, nicht dieser Plan.

- [x] **Step 2.2/2.3: Tests für die Epic-Abdeckung** — erledigt in `7a11a00`

In `tests/unit/test_capital_provider.py`:
`test_every_sub_sector_etf_and_vix_maps_to_a_non_empty_epic`,
`test_sub_sector_etfs_are_complete_and_consistent` (21 Einträge, jeder Sub-Sektor
löst sich über `SECTOR_ALIASES` selbst auf) und
`test_every_sector_alias_target_is_a_known_sub_sector` (kein Alias zeigt ins Leere).

- [ ] **Step 2.4: Verify-Skript ausführen**

Die Credentials liegen lokal in `.env` und funktionieren — das Skript läuft direkt:

```bash
./venv/bin/python -m setup.verify_epics
```

Erwartete Ausgabe: eine Zeile je Symbol mit `exakt` / `ABWEICHEND` / `KEIN TREFFER`,
eine Zusammenfassung und der kopierfertige TICKER_MAP-Block.

**Ergebnis dokumentieren** — den vollständigen Report in den Commit-Body von
Step 2.7 aufnehmen, damit nachvollziehbar bleibt, welche Epics wann bestätigt wurden.

- [ ] **Step 2.5: TICKER_MAP nach Report-Ergebnis ergänzen**

Nur die im Report unter „In capital_provider.TICKER_MAP eintragen" ausgegebenen
Zeilen übernehmen:

```python
# src/providers/capital_provider.py — TICKER_MAP erweitern, Beispiel-Form.
# Die konkreten Werte stammen 1:1 aus dem verify_epics-Report aus Step 2.4;
# steht dort "(nichts)", bleibt TICKER_MAP unverändert.
TICKER_MAP: dict[str, str] = {
    "GC=F":    "GOLD",
    "SI=F":    "SILVER",
    "CL=F":    "OIL_CRUDE",   # Capital.com epic (not CRUDE_OIL)
    "BTC-USD": "BTCUSD",
    "ETH-USD": "ETHUSD",
    "SOL-USD": "SOLUSD",
    "XRP-USD": "XRPUSD",
    "BRK-B":   "BRKB",        # Capital.com epic for Berkshire B
    # --- Sektor-ETFs + VIX: nur Symbole mit abweichendem Epic eintragen ---
    # (aus setup/verify_epics.py, Lauf vom <DATUM AUS STEP 2.4>)
}
```

**Bei `KEIN TREFFER` für ein Symbol:** Den betroffenen Sektor in
`config.SUB_SECTOR_ETFS` belassen, aber im Commit-Body festhalten. Der
Sektor-ETF-Check in Plan 2 behandelt einen nicht abrufbaren ETF wie einen
unbekannten Sektor (D6, weiches Verhalten). Kein Blocker für diesen Plan.

- [ ] **Step 2.6: Tests laufen lassen, grün bestätigen**

Run: `pytest tests/unit/test_capital_provider.py -v`
Expected: PASS

- [ ] **Step 2.7: Commit**

```bash
git add config.py src/providers/capital_provider.py tests/unit/test_capital_provider.py
git commit -m "feat: add GICS sector ETF + VIX constants, verified epics

Sprint 3B / Plan 1, Task 2. TICKER_MAP extended with the epics confirmed by
setup/verify_epics.py against the Capital.com demo API.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Sektor-Tabellen + Finnhub-Normalisierung ✅ ERLEDIGT (`a4211d5`, Schnitt 1)

Setzt B.10 und D5 um.

**Files:**
- Modify: `config.py` (`SECTOR_ALIASES`)
- Modify: `src/db.py` (`SCHEMA_SQL`, `_apply_migrations`, `init_schema`, neue Helper)
- Test: `tests/unit/test_db.py` (ergänzen)

**Interfaces:**
- Consumes: `config.SUB_SECTOR_ETFS` (Task 2), `config.SECTOR_ALIASES` (Task 2)
- Produces:
  - `db.resolve_sector_id(conn, raw_sector: str | None) -> int | None`
  - `db.upsert_ticker_sector(conn, ticker: str, sector_id: int, source: str = "finnhub") -> None`
  - `db.get_ticker_sector(conn, ticker: str) -> sqlite3.Row | None` — Row mit den Keys `sector_id`, `name`, `etf`
  - Tabellen `sectors` (21 Zeilen vorbefüllt) und `ticker_sectors`

- [x] **Step 3.1: `SECTOR_ALIASES` in `config.py` ergänzen** — erledigt in `7a11a00`

`config.SECTOR_ALIASES` bildet das gemischte Finnhub-Vokabular auf die 21
Sub-Sektoren aus `config.SUB_SECTOR_ETFS` ab. Maßgeblich ist die Datei.

Bewusst **nicht** gemappt (kein passender ETF vorhanden, s. D5):
`Financial Services`, `Diversified Financial Services`, `Health Care`,
`Health Care Providers & Services`. Diese Ticker laufen ohne Sektor-Guardrail.
Bei den 20 MVP-Tickern betrifft das V, MA, BRK-B und UNH — also 4 von 20.

- [ ] **Step 3.2: Failing Tests für Schema und Helper schreiben**

```python
# tests/unit/test_db.py — anhängen:
from src.db import (
    resolve_sector_id, upsert_ticker_sector, get_ticker_sector,
)


def test_init_schema_creates_sector_tables(in_memory_db):
    init_schema(in_memory_db)
    tables = set(get_tables(in_memory_db))
    assert {"sectors", "ticker_sectors"}.issubset(tables)


def test_sectors_table_is_seeded_with_all_sub_sectors(in_memory_db):
    import config
    init_schema(in_memory_db)
    rows = in_memory_db.execute("SELECT name, etf FROM sectors ORDER BY name").fetchall()
    assert len(rows) == 21
    assert {r["name"]: r["etf"] for r in rows} == config.SUB_SECTOR_ETFS


def test_sector_seeding_is_idempotent(in_memory_db):
    init_schema(in_memory_db)
    init_schema(in_memory_db)
    n = in_memory_db.execute("SELECT COUNT(*) AS n FROM sectors").fetchone()["n"]
    assert n == 21


def test_resolve_sector_id_maps_exact_sub_sector_name(in_memory_db):
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Semiconductors")
    assert sid is not None
    row = in_memory_db.execute("SELECT name FROM sectors WHERE id=?", (sid,)).fetchone()
    assert row["name"] == "Semiconductors"


def test_resolve_sector_id_maps_finnhub_alias(in_memory_db):
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Consumer Cyclical")
    row = in_memory_db.execute("SELECT name FROM sectors WHERE id=?", (sid,)).fetchone()
    assert row["name"] == "Consumer Discretionary Rest"


def test_resolve_sector_id_splits_broad_finnhub_values_into_sub_sectors(in_memory_db):
    """Der Kern von D7: 'Software' und 'Semiconductors' dürfen NICHT beide im
    breiten Technologie-Eimer landen."""
    init_schema(in_memory_db)
    soft = resolve_sector_id(in_memory_db, "Software")
    semi = resolve_sector_id(in_memory_db, "Semiconductors")
    assert soft != semi
    etfs = {
        r["etf"] for r in in_memory_db.execute(
            "SELECT etf FROM sectors WHERE id IN (?, ?)", (soft, semi)).fetchall()
    }
    assert etfs == {"VGT", "SOXX"}


def test_resolve_sector_id_returns_none_for_deliberately_unmapped_values(in_memory_db):
    """D5: Werte ohne passenden ETF bleiben ungemappt statt falsch geroutet."""
    init_schema(in_memory_db)
    for raw in ("Financial Services", "Health Care Providers & Services"):
        assert resolve_sector_id(in_memory_db, raw) is None


def test_resolve_sector_id_is_case_and_whitespace_insensitive(in_memory_db):
    init_schema(in_memory_db)
    assert resolve_sector_id(in_memory_db, "  semiconductors ") == \
           resolve_sector_id(in_memory_db, "Semiconductors")


def test_resolve_sector_id_returns_none_for_unknown_and_logs(in_memory_db, caplog):
    init_schema(in_memory_db)
    with caplog.at_level("WARNING"):
        assert resolve_sector_id(in_memory_db, "Underwater Basket Weaving") is None
    assert "Underwater Basket Weaving" in caplog.text


def test_resolve_sector_id_returns_none_for_none_without_logging(in_memory_db, caplog):
    init_schema(in_memory_db)
    with caplog.at_level("WARNING"):
        assert resolve_sector_id(in_memory_db, None) is None
    assert "unknown sector" not in caplog.text


def test_upsert_ticker_sector_inserts_then_updates(in_memory_db):
    init_schema(in_memory_db)
    hardware = resolve_sector_id(in_memory_db, "Technology Hardware")
    semi = resolve_sector_id(in_memory_db, "Semiconductors")
    upsert_ticker_sector(in_memory_db, "AAPL", hardware)
    upsert_ticker_sector(in_memory_db, "AAPL", semi)
    rows = in_memory_db.execute("SELECT * FROM ticker_sectors WHERE ticker='AAPL'").fetchall()
    assert len(rows) == 1
    assert rows[0]["sector_id"] == semi


def test_get_ticker_sector_joins_name_and_etf(in_memory_db):
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Semiconductors")
    upsert_ticker_sector(in_memory_db, "NVDA", sid)
    row = get_ticker_sector(in_memory_db, "NVDA")
    assert row["name"] == "Semiconductors"
    assert row["etf"] == "SOXX"


def test_get_ticker_sector_returns_none_when_unmapped(in_memory_db):
    init_schema(in_memory_db)
    assert get_ticker_sector(in_memory_db, "NOPE") is None
```

- [ ] **Step 3.3: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_db.py -k sector -v`
Expected: FAIL mit `ImportError: cannot import name 'resolve_sector_id' from 'src.db'`

- [ ] **Step 3.4: Schema + Seeding + Helper implementieren**

```python
# src/db.py — SCHEMA_SQL erweitern (ans Ende des SQL-Strings, vor dem schliessenden """):

CREATE TABLE IF NOT EXISTS sectors (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    etf  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ticker_sectors (
    ticker     TEXT PRIMARY KEY,
    sector_id  INTEGER REFERENCES sectors(id),
    source     TEXT DEFAULT 'finnhub',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

```python
# src/db.py — Modul-Level, nach den bestehenden Imports einfügen:

# Case-insensitiver Lookup über config.SECTOR_ALIASES. Einmal beim Import gebaut,
# damit resolve_sector_id() nicht bei jedem Ticker neu normalisieren muss.
_SECTOR_ALIAS_LOOKUP: dict[str, str] = {
    raw.strip().casefold(): gics for raw, gics in config.SECTOR_ALIASES.items()
}
```

```python
# src/db.py — neue Funktionen, nach init_schema() einfügen:

def _seed_sectors(conn: sqlite3.Connection) -> None:
    """Befüllt die sectors-Tabelle einmalig mit den 21 Sub-Sektoren aus
    config.SUB_SECTOR_ETFS. Idempotent über ON CONFLICT auf name UNIQUE;
    ein geänderter ETF wird nachgezogen."""
    for name, etf in config.SUB_SECTOR_ETFS.items():
        conn.execute(
            "INSERT INTO sectors (name, etf) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET etf = excluded.etf",
            (name, etf),
        )
    conn.commit()


def resolve_sector_id(conn: sqlite3.Connection, raw_sector: str | None) -> int | None:
    """Normalisiert einen Finnhub-Sektorwert über config.SECTOR_ALIASES auf einen
    GICS-Namen und gibt dessen sectors.id zurück. Nicht auflösbare Werte ergeben
    None und werden mit WARN geloggt, damit die Alias-Liste iterativ wachsen kann."""
    if not raw_sector:
        return None
    gics = _SECTOR_ALIAS_LOOKUP.get(raw_sector.strip().casefold())
    if gics is None:
        log.warning(f"unknown sector value from provider: {raw_sector!r}")
        return None
    row = conn.execute("SELECT id FROM sectors WHERE name = ?", (gics,)).fetchone()
    return int(row["id"]) if row else None


def upsert_ticker_sector(
    conn: sqlite3.Connection, ticker: str, sector_id: int, source: str = "finnhub",
) -> None:
    """Schreibt oder aktualisiert die Sektor-Zuordnung eines Tickers."""
    conn.execute(
        """INSERT INTO ticker_sectors (ticker, sector_id, source, updated_at)
           VALUES (?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(ticker) DO UPDATE SET
               sector_id  = excluded.sector_id,
               source     = excluded.source,
               updated_at = CURRENT_TIMESTAMP""",
        (ticker, sector_id, source),
    )
    conn.commit()


def get_ticker_sector(conn: sqlite3.Connection, ticker: str) -> sqlite3.Row | None:
    """Gibt sector_id, GICS-Name und Sektor-ETF für `ticker` zurück (JOIN über
    ticker_sectors -> sectors), oder None wenn kein Mapping existiert."""
    return conn.execute(
        """SELECT ts.sector_id AS sector_id, s.name AS name, s.etf AS etf
           FROM ticker_sectors ts JOIN sectors s ON s.id = ts.sector_id
           WHERE ts.ticker = ?""",
        (ticker,),
    ).fetchone()
```

```python
# src/db.py — init_schema() erweitern:

def init_schema(conn: sqlite3.Connection) -> None:
    """Creates every table/index if missing, seeds reference data, and applies
    pending migrations. Safe to call on every run — idempotent."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    _apply_migrations(conn)
    _seed_sectors(conn)
```

**Pflicht-Ergänzung:** `src/db.py` hat aktuell **kein** Logging (Imports sind nur
`sqlite3`, `Path`, `Any`, `config`). `resolve_sector_id()` und Task 5 brauchen es.
Oben in der Datei ergänzen:

```python
# src/db.py — zu den bestehenden Imports hinzufügen:
import logging

log = logging.getLogger("shares_future.db")
```

- [ ] **Step 3.5: Tests laufen lassen, grün bestätigen**

Run: `pytest tests/unit/test_db.py -v`
Expected: PASS

- [ ] **Step 3.6: Commit**

```bash
git add config.py src/db.py tests/unit/test_db.py
git commit -m "feat: add sectors + ticker_sectors tables with Finnhub normalisation

Sprint 3B / Plan 1, Task 3 (spec B.10, decision D5). SECTOR_ALIASES maps
Finnhub's finnhubIndustry vocabulary (sector- and industry-level) onto the
21 sub-sector names. Unresolvable values yield sector_id NULL and a WARN
log carrying the raw value, so the alias list grows deliberately.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: `ticker_sectors` organisch in Phase 1 befüllen ✅ ERLEDIGT (`990597f`, Schnitt 1)

**Files:**
- Modify: `src/data_collector.py` (`_process_ticker`, ~Zeile 325)
- Test: `tests/unit/test_data_collector.py` (ergänzen)

**Interfaces:**
- Consumes: `db.resolve_sector_id()`, `db.upsert_ticker_sector()` (Task 3)
- Produces: keine neue öffentliche Signatur — Seiteneffekt auf `ticker_sectors`

- [ ] **Step 4.1: Failing Tests schreiben**

```python
# tests/unit/test_data_collector.py — anhängen:

def test_process_ticker_links_sector_from_fundamentals(in_memory_db, mocker):
    """Der Finnhub-Sektor eines Tickers landet normalisiert in ticker_sectors."""
    from src import db
    db.init_schema(in_memory_db)

    price_provider = mocker.MagicMock()
    price_provider._source_name = "capital.com"
    earnings_provider = mocker.MagicMock()
    earnings_provider.get_fundamentals.return_value = {
        "pe_ratio": 28.0, "sector": "Semiconductors",
    }
    earnings_provider.get_earnings_calendar.return_value = {}

    _seed_price_history(in_memory_db, "NVDA", days=210)

    from src.data_collector import _process_ticker
    _process_ticker(
        ticker="NVDA", price_provider=price_provider,
        earnings_provider=earnings_provider, conn=in_memory_db,
        date="2026-07-27", run_type="pre_market",
    )

    row = db.get_ticker_sector(in_memory_db, "NVDA")
    assert row is not None
    assert row["name"] == "Semiconductors"
    assert row["etf"] == "SOXX"


def test_process_ticker_leaves_sector_unmapped_when_unknown(in_memory_db, mocker):
    from src import db
    db.init_schema(in_memory_db)

    price_provider = mocker.MagicMock()
    price_provider._source_name = "capital.com"
    earnings_provider = mocker.MagicMock()
    earnings_provider.get_fundamentals.return_value = {"sector": "Quantum Basketry"}
    earnings_provider.get_earnings_calendar.return_value = {}

    _seed_price_history(in_memory_db, "WEIRD", days=210)

    from src.data_collector import _process_ticker
    _process_ticker(
        ticker="WEIRD", price_provider=price_provider,
        earnings_provider=earnings_provider, conn=in_memory_db,
        date="2026-07-27", run_type="pre_market",
    )
    assert db.get_ticker_sector(in_memory_db, "WEIRD") is None
```

**Helper für die Tests** — falls `_seed_price_history` noch nicht in
`tests/unit/test_data_collector.py` existiert, oben in der Datei ergänzen:

```python
def _seed_price_history(conn, ticker: str, days: int = 210) -> None:
    """Füllt price_history mit `days` synthetischen Tagesbars, damit die
    Indikator-Berechnung genug Datenpunkte hat."""
    from datetime import date as _d, timedelta as _td
    from src import db
    start = _d(2026, 7, 27) - _td(days=days)
    for i in range(days):
        d = (start + _td(days=i)).isoformat()
        base = 100.0 + (i % 20)
        db.insert_price_bar_if_missing(
            conn, ticker=ticker, date=d,
            open_=base, high=base + 2, low=base - 2, close=base + 1,
            volume=1_000_000, source="capital.com",
        )
    conn.commit()
```

- [ ] **Step 4.2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_data_collector.py -k sector -v`
Expected: FAIL — `db.get_ticker_sector(...)` liefert `None`, weil noch nichts geschrieben wird.

- [ ] **Step 4.3: Sektor-Verknüpfung in `_process_ticker` implementieren**

```python
# src/data_collector.py — direkt nach dem bestehenden td.update({...}) Block
# (endet mit "analyst_consensus": fundamentals.get("consensus"), }) einfügen:

    # Sektor-Mapping organisch pflegen (Sprint 3B / B.10): der Finnhub-Rohwert
    # wird normalisiert und in ticker_sectors geschrieben. Unbekannte Werte
    # loggt db.resolve_sector_id() — hier bleibt der Ticker schlicht ungemappt.
    _sector_id = db.resolve_sector_id(conn, fundamentals.get("sector"))
    if _sector_id is not None:
        db.upsert_ticker_sector(conn, ticker, _sector_id, source="finnhub")
```

- [ ] **Step 4.4: Tests laufen lassen, grün bestätigen**

Run: `pytest tests/unit/test_data_collector.py -v`
Expected: PASS

- [ ] **Step 4.5: Commit**

```bash
git add src/data_collector.py tests/unit/test_data_collector.py
git commit -m "feat: populate ticker_sectors organically in Phase 1

Sprint 3B / Plan 1, Task 4 (spec B.10). Every fundamentals fetch now
normalises finnhubIndustry and upserts the ticker's sector mapping.
No static ticker->sector table in code.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: `ticker_status` — kumulativer Skip-Zähler ✅ ERLEDIGT (`c035f6c`, Schnitt 2)

Setzt B.7 und D3 um (Datenschicht).

**Files:**
- Modify: `config.py` (`TICKER_MAX_SKIPS`, `TICKER_RETRY_AFTER_DAYS`)
- Modify: `src/db.py` (`SCHEMA_SQL`, `log_skipped_ticker`, neue Helper)
- Test: `tests/unit/test_db.py` (ergänzen)

**Interfaces:**
- Consumes: `config.TICKER_MAX_SKIPS`, `config.TICKER_RETRY_AFTER_DAYS`
- Produces:
  - `db.get_ticker_status(conn, ticker) -> sqlite3.Row | None`
  - `db.is_ticker_inactive(conn, ticker, today: str) -> bool`
  - `db.reactivate_ticker(conn, ticker) -> bool` — True wenn eine Zeile zurückgesetzt wurde
  - `db.list_inactive_tickers(conn) -> list[sqlite3.Row]`
  - Tabelle `ticker_status`

- [ ] **Step 5.1: Konstanten in `config.py` ergänzen**

```python
# config.py — nach MAX_DEEP_ANALYSIS / BATCH_SIZE_QUICK (Zeile 45) einfügen:

# Ticker-Deaktivierung (Sprint 3B / B.7): ein Ticker, der wiederholt keine
# brauchbaren Daten liefert, wird nach TICKER_MAX_SKIPS Skips deaktiviert und
# erst nach TICKER_RETRY_AFTER_DAYS Tagen automatisch erneut versucht.
TICKER_MAX_SKIPS = 20
TICKER_RETRY_AFTER_DAYS = 30
```

- [ ] **Step 5.2: Failing Tests schreiben**

```python
# tests/unit/test_db.py — anhängen:
from src.db import (
    log_skipped_ticker, get_ticker_status, is_ticker_inactive,
    reactivate_ticker, list_inactive_tickers,
)


def test_init_schema_creates_ticker_status(in_memory_db):
    init_schema(in_memory_db)
    assert "ticker_status" in get_tables(in_memory_db)


def test_log_skipped_ticker_still_writes_event_row(in_memory_db):
    init_schema(in_memory_db)
    log_skipped_ticker(in_memory_db, ticker="XYZ", date="2026-07-27",
                       run_type="pre_market", reason="insufficient bars")
    rows = in_memory_db.execute("SELECT * FROM skipped_tickers WHERE ticker='XYZ'").fetchall()
    assert len(rows) == 1
    assert rows[0]["reason"] == "insufficient bars"


def test_log_skipped_ticker_accumulates_skip_count(in_memory_db):
    init_schema(in_memory_db)
    for d in ("2026-07-25", "2026-07-26", "2026-07-27"):
        log_skipped_ticker(in_memory_db, ticker="XYZ", date=d,
                           run_type="pre_market", reason="insufficient bars")
    st = get_ticker_status(in_memory_db, "XYZ")
    assert st["skip_count"] == 3
    assert st["first_skip_date"] == "2026-07-25"
    assert st["last_skip_date"] == "2026-07-27"
    assert st["inactive"] == 0


def test_ticker_becomes_inactive_past_threshold(in_memory_db):
    import config
    init_schema(in_memory_db)
    for i in range(config.TICKER_MAX_SKIPS + 1):
        log_skipped_ticker(in_memory_db, ticker="DEAD", date="2026-07-27",
                           run_type="pre_market", reason="data_quality=low")
    st = get_ticker_status(in_memory_db, "DEAD")
    assert st["skip_count"] == config.TICKER_MAX_SKIPS + 1
    assert st["inactive"] == 1
    assert st["retry_after"] == "2026-08-26"   # 2026-07-27 + 30 Tage


def test_is_ticker_inactive_true_before_retry_date(in_memory_db):
    import config
    init_schema(in_memory_db)
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        log_skipped_ticker(in_memory_db, ticker="DEAD", date="2026-07-27",
                           run_type="pre_market", reason="x")
    assert is_ticker_inactive(in_memory_db, "DEAD", today="2026-08-01") is True


def test_is_ticker_inactive_false_on_and_after_retry_date(in_memory_db):
    import config
    init_schema(in_memory_db)
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        log_skipped_ticker(in_memory_db, ticker="DEAD", date="2026-07-27",
                           run_type="pre_market", reason="x")
    assert is_ticker_inactive(in_memory_db, "DEAD", today="2026-08-26") is False
    assert is_ticker_inactive(in_memory_db, "DEAD", today="2026-09-30") is False


def test_is_ticker_inactive_false_for_unknown_ticker(in_memory_db):
    init_schema(in_memory_db)
    assert is_ticker_inactive(in_memory_db, "AAPL", today="2026-07-27") is False


def test_failed_retry_pushes_retry_after_forward(in_memory_db):
    """Schlägt der Retry erneut fehl, verlängert sich die Sperre um weitere 30 Tage."""
    import config
    init_schema(in_memory_db)
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        log_skipped_ticker(in_memory_db, ticker="DEAD", date="2026-07-27",
                           run_type="pre_market", reason="x")
    log_skipped_ticker(in_memory_db, ticker="DEAD", date="2026-08-26",
                       run_type="pre_market", reason="x")
    st = get_ticker_status(in_memory_db, "DEAD")
    assert st["retry_after"] == "2026-09-25"   # 2026-08-26 + 30 Tage


def test_reactivate_ticker_resets_counter_and_flag(in_memory_db):
    import config
    init_schema(in_memory_db)
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        log_skipped_ticker(in_memory_db, ticker="DEAD", date="2026-07-27",
                           run_type="pre_market", reason="x")
    assert reactivate_ticker(in_memory_db, "DEAD") is True
    st = get_ticker_status(in_memory_db, "DEAD")
    assert st["skip_count"] == 0
    assert st["inactive"] == 0
    assert st["retry_after"] is None


def test_reactivate_ticker_returns_false_when_nothing_to_reset(in_memory_db):
    init_schema(in_memory_db)
    assert reactivate_ticker(in_memory_db, "AAPL") is False


def test_list_inactive_tickers(in_memory_db):
    import config
    init_schema(in_memory_db)
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        log_skipped_ticker(in_memory_db, ticker="DEAD", date="2026-07-27",
                           run_type="pre_market", reason="x")
    log_skipped_ticker(in_memory_db, ticker="OK", date="2026-07-27",
                       run_type="pre_market", reason="x")
    names = [r["ticker"] for r in list_inactive_tickers(in_memory_db)]
    assert names == ["DEAD"]
```

- [ ] **Step 5.3: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_db.py -k ticker_status -v`
Expected: FAIL mit `ImportError: cannot import name 'get_ticker_status' from 'src.db'`

- [ ] **Step 5.4: Schema + Helper implementieren**

```python
# src/db.py — SCHEMA_SQL erweitern:

CREATE TABLE IF NOT EXISTS ticker_status (
    ticker          TEXT PRIMARY KEY,
    skip_count      INTEGER NOT NULL DEFAULT 0,
    inactive        INTEGER NOT NULL DEFAULT 0,
    first_skip_date TEXT,
    last_skip_date  TEXT,
    retry_after     TEXT
);
```

```python
# src/db.py — log_skipped_ticker() ERSETZEN:

def log_skipped_ticker(
    conn: sqlite3.Connection,
    ticker: str, date: str, run_type: str,
    reason: str, learnable: bool = False,
) -> None:
    """Records that `ticker` was skipped on `date` and why, so it's excluded
    from the learning module unless learnable=True. Zusätzlich wird der
    kumulative Zähler in ticker_status hochgezählt; ab config.TICKER_MAX_SKIPS
    wird der Ticker deaktiviert und ein Retry-Datum gesetzt (Sprint 3B / B.7)."""
    conn.execute(
        """INSERT INTO skipped_tickers
           (ticker, date, run_type, reason, learnable)
           VALUES (?, ?, ?, ?, ?)""",
        (ticker, date, run_type, reason, 1 if learnable else 0),
    )
    conn.execute(
        """INSERT INTO ticker_status
               (ticker, skip_count, first_skip_date, last_skip_date)
           VALUES (?, 1, ?, ?)
           ON CONFLICT(ticker) DO UPDATE SET
               skip_count     = ticker_status.skip_count + 1,
               last_skip_date = excluded.last_skip_date""",
        (ticker, date, date),
    )
    row = conn.execute(
        "SELECT skip_count FROM ticker_status WHERE ticker = ?", (ticker,),
    ).fetchone()
    if row and int(row["skip_count"]) > config.TICKER_MAX_SKIPS:
        retry_after = (
            _date_cls.fromisoformat(date)
            + timedelta(days=config.TICKER_RETRY_AFTER_DAYS)
        ).isoformat()
        conn.execute(
            "UPDATE ticker_status SET inactive = 1, retry_after = ? WHERE ticker = ?",
            (retry_after, ticker),
        )
        log.warning(
            f"{ticker}: deaktiviert nach {row['skip_count']} Skips "
            f"(> {config.TICKER_MAX_SKIPS}), Retry ab {retry_after}"
        )
    conn.commit()


def get_ticker_status(conn: sqlite3.Connection, ticker: str) -> sqlite3.Row | None:
    """Gibt die ticker_status-Zeile eines Tickers zurück, oder None wenn er noch
    nie übersprungen wurde."""
    return conn.execute(
        "SELECT * FROM ticker_status WHERE ticker = ?", (ticker,),
    ).fetchone()


def is_ticker_inactive(conn: sqlite3.Connection, ticker: str, today: str) -> bool:
    """True, wenn `ticker` deaktiviert ist UND sein Retry-Datum noch in der
    Zukunft liegt. Ab dem Retry-Datum gilt er wieder als aktiv, damit die
    Pipeline ihn erneut versucht."""
    row = conn.execute(
        "SELECT inactive, retry_after FROM ticker_status WHERE ticker = ?", (ticker,),
    ).fetchone()
    if row is None or not row["inactive"]:
        return False
    retry_after = row["retry_after"]
    if retry_after is None:
        return True
    return today < retry_after


def reactivate_ticker(conn: sqlite3.Connection, ticker: str) -> bool:
    """Setzt skip_count, inactive und retry_after für `ticker` zurück. Gibt True
    zurück, wenn eine Zeile geändert wurde (also überhaupt ein Status existierte)."""
    cur = conn.execute(
        """UPDATE ticker_status
           SET skip_count = 0, inactive = 0, retry_after = NULL
           WHERE ticker = ? AND (skip_count > 0 OR inactive = 1)""",
        (ticker,),
    )
    conn.commit()
    return cur.rowcount > 0


def list_inactive_tickers(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Gibt alle aktuell deaktivierten Ticker zurück, alphabetisch sortiert."""
    return conn.execute(
        "SELECT * FROM ticker_status WHERE inactive = 1 ORDER BY ticker"
    ).fetchall()
```

**Pflicht-Ergänzung:** `src/db.py` importiert aktuell **nichts** aus `datetime`.
Für die Retry-Datums-Berechnung oben ergänzen:

```python
# src/db.py — zu den bestehenden Imports hinzufügen:
from datetime import date as _date_cls, timedelta
```

- [ ] **Step 5.5: Tests laufen lassen, grün bestätigen**

Run: `pytest tests/unit/test_db.py -v`
Expected: PASS

- [ ] **Step 5.6: Commit**

```bash
git add config.py src/db.py tests/unit/test_db.py
git commit -m "feat: add ticker_status with cumulative skip counter + auto-retry

Sprint 3B / Plan 1, Task 5 (spec B.7, decision D3). log_skipped_ticker now
also upserts a cumulative counter; past TICKER_MAX_SKIPS (20) the ticker is
deactivated with a retry_after date 30 days out. The skipped_tickers event
log is untouched — the weekly mail still needs per-day rows.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: Inaktive Ticker in Phase 1 überspringen + bei Erfolg reaktivieren ✅ ERLEDIGT (`031868d`, Schnitt 2)

**Files:**
- Modify: `src/data_collector.py` (`collect`)
- Test: `tests/unit/test_data_collector.py` (ergänzen)

**Interfaces:**
- Consumes: `db.is_ticker_inactive()`, `db.reactivate_ticker()` (Task 5)
- Produces: keine neue Signatur — `collect()` behält `(list[dict], int)` als Rückgabe

- [ ] **Step 6.1: Failing Tests schreiben**

```python
# tests/unit/test_data_collector.py — anhängen:

def test_collect_skips_inactive_tickers_without_api_call(in_memory_db, mocker):
    import config
    from src import db
    db.init_schema(in_memory_db)
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        db.log_skipped_ticker(in_memory_db, ticker="DEAD", date="2026-07-01",
                              run_type="pre_market", reason="x")

    price_provider = mocker.MagicMock()
    price_provider._source_name = "capital.com"
    earnings_provider = mocker.MagicMock()

    from src.data_collector import collect
    results, skipped = collect(
        tickers=["DEAD"], price_provider=price_provider,
        earnings_provider=earnings_provider, conn=in_memory_db,
        date="2026-07-27", run_type="pre_market",
    )
    assert results == []
    assert skipped == 1
    price_provider.get_ohlc_after.assert_not_called()
    price_provider.get_price_history.assert_not_called()


def test_collect_reactivates_ticker_after_successful_run(in_memory_db, mocker):
    from src import db
    db.init_schema(in_memory_db)
    db.log_skipped_ticker(in_memory_db, ticker="AAPL", date="2026-07-01",
                          run_type="pre_market", reason="x")
    assert db.get_ticker_status(in_memory_db, "AAPL")["skip_count"] == 1

    _seed_price_history(in_memory_db, "AAPL", days=210)
    price_provider = mocker.MagicMock()
    price_provider._source_name = "capital.com"
    earnings_provider = mocker.MagicMock()
    earnings_provider.get_fundamentals.return_value = {"sector": "Technology"}
    earnings_provider.get_earnings_calendar.return_value = {}

    from src.data_collector import collect
    results, _ = collect(
        tickers=["AAPL"], price_provider=price_provider,
        earnings_provider=earnings_provider, conn=in_memory_db,
        date="2026-07-27", run_type="pre_market",
    )
    assert len(results) == 1
    assert db.get_ticker_status(in_memory_db, "AAPL")["skip_count"] == 0
```

- [ ] **Step 6.2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_data_collector.py -k "inactive or reactivates" -v`
Expected: FAIL — `price_provider.get_ohlc_after` wurde doch aufgerufen bzw. `skip_count` bleibt 1.

- [ ] **Step 6.3: `collect()` anpassen**

```python
# src/data_collector.py — die for-Schleife in collect() ERSETZEN:

    for i, t in enumerate(tickers):
        # Sprint 3B / B.7: dauerhaft datenlose Ticker kosten keine API-Calls mehr,
        # bis ihr Retry-Datum erreicht ist.
        if db.is_ticker_inactive(conn, t, today=date):
            log.info(f"{t}: inaktiv (>{config.TICKER_MAX_SKIPS} Skips) — übersprungen")
            skipped += 1
            continue

        td = _process_ticker(
            ticker=t,
            price_provider=price_provider,
            earnings_provider=earnings_provider,
            conn=conn,
            date=date,
            run_type=run_type,
        )
        if td is None:
            skipped += 1
        else:
            # Erfolgreicher Abruf heilt den Zähler — sonst würde ein Ticker durch
            # verstreute Einzelausfälle über Monate hinweg in die Deaktivierung laufen.
            db.reactivate_ticker(conn, t)
            results.append(td)

        if (i + 1) % BATCH_PAUSE_EVERY == 0 and (i + 1) < len(tickers):
            log.info(
                f"Batch pause: processed {i + 1}/{len(tickers)} tickers, "
                f"sleeping {config.CAPITAL_COM_BATCH_PAUSE}s"
            )
            time.sleep(config.CAPITAL_COM_BATCH_PAUSE)
```

- [ ] **Step 6.4: Tests laufen lassen, grün bestätigen**

Run: `pytest tests/unit/test_data_collector.py -v`
Expected: PASS

- [ ] **Step 6.5: Commit**

```bash
git add src/data_collector.py tests/unit/test_data_collector.py
git commit -m "feat: skip inactive tickers in Phase 1, heal counter on success

Sprint 3B / Plan 1, Task 6 (spec B.7). Deactivated tickers cost zero API
calls until their retry_after date; a successful collect resets the skip
counter so sporadic outages never accumulate into a deactivation.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: `--reactivate` CLI-Flag im historical_loader ✅ ERLEDIGT (`18aa1cb`, Schnitt 2)

Zweiter Teil von D3: der manuelle Override.

**Files:**
- Modify: `setup/historical_loader.py` (`main`)
- Test: `tests/unit/test_historical_loader.py` (ergänzen)

**Interfaces:**
- Consumes: `db.reactivate_ticker()`, `db.list_inactive_tickers()` (Task 5)
- Produces: CLI `python setup/historical_loader.py --reactivate TICKER [TICKER ...]`
  und `python setup/historical_loader.py --list-inactive`

- [ ] **Step 7.1: Failing Tests schreiben**

```python
# tests/unit/test_historical_loader.py — anhängen:

def test_reactivate_flag_resets_named_tickers(tmp_db_path, capsys):
    import config
    from src import db
    conn = db.connect(str(tmp_db_path))
    db.init_schema(conn)
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        db.log_skipped_ticker(conn, ticker="DEAD", date="2026-07-27",
                              run_type="pre_market", reason="x")
    conn.close()

    from setup.historical_loader import main
    main(["--reactivate", "DEAD", "--db-path", str(tmp_db_path)])

    conn = db.connect(str(tmp_db_path))
    assert db.is_ticker_inactive(conn, "DEAD", today="2026-07-28") is False
    assert db.get_ticker_status(conn, "DEAD")["skip_count"] == 0
    conn.close()
    assert "DEAD" in capsys.readouterr().out


def test_list_inactive_flag_prints_deactivated_tickers(tmp_db_path, capsys):
    import config
    from src import db
    conn = db.connect(str(tmp_db_path))
    db.init_schema(conn)
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        db.log_skipped_ticker(conn, ticker="DEAD", date="2026-07-27",
                              run_type="pre_market", reason="x")
    conn.close()

    from setup.historical_loader import main
    main(["--list-inactive", "--db-path", str(tmp_db_path)])
    out = capsys.readouterr().out
    assert "DEAD" in out
    assert "2026-08-26" in out   # retry_after
```

- [ ] **Step 7.2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_historical_loader.py -k "reactivate or inactive" -v`
Expected: FAIL — entweder `TypeError: main() takes 0 positional arguments` oder
`argparse` bricht mit `unrecognized arguments: --reactivate` ab.

- [ ] **Step 7.3: CLI erweitern**

```python
# setup/historical_loader.py — main() ERSETZEN.
# Wichtig: main() nimmt jetzt argv entgegen, damit Tests es ohne sys.argv-Patching
# aufrufen können. Der __main__-Block bleibt unverändert (main() ohne Argument).

def main(argv: list[str] | None = None) -> None:
    """CLI-Einstiegspunkt: lädt historische Bars oder verwaltet den Ticker-Status.
    Genau eine der Modus-Optionen ist Pflicht."""
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tickers",    nargs="+", help="Specific tickers to load")
    group.add_argument("--all",        action="store_true", help="Load SP500_MVP_TICKERS")
    group.add_argument("--full-sp500", action="store_true", help="Load SP500_FULL_TICKERS (~500)")
    group.add_argument("--reactivate", nargs="+", metavar="TICKER",
                       help="Reset skip_count/inactive for these tickers (Sprint 3B / B.7)")
    group.add_argument("--list-inactive", action="store_true",
                       help="List all currently deactivated tickers and their retry date")
    parser.add_argument("--db-path", default=str(config.DB_PATH))
    parser.add_argument("--days",    type=int, default=DAYS_3_YEARS)
    ns = parser.parse_args(argv)

    if ns.list_inactive:
        conn = db.connect(ns.db_path)
        db.init_schema(conn)
        rows = db.list_inactive_tickers(conn)
        if not rows:
            print("Keine deaktivierten Ticker.")
        for r in rows:
            print(
                f"{r['ticker']:<8} skips={r['skip_count']:<4} "
                f"letzter Skip={r['last_skip_date']}  Retry ab={r['retry_after']}"
            )
        conn.close()
        return

    if ns.reactivate:
        conn = db.connect(ns.db_path)
        db.init_schema(conn)
        for t in ns.reactivate:
            changed = db.reactivate_ticker(conn, t)
            print(f"{t}: {'reaktiviert' if changed else 'kein Status vorhanden — nichts zu tun'}")
        conn.close()
        return

    # ... bestehende Lade-Logik unverändert weiter (--tickers / --all / --full-sp500)
```

**Wichtig:** Der Rest von `main()` (die bestehende Lade-Logik) bleibt unverändert;
lediglich `ns = parser.parse_args()` wird zu `ns = parser.parse_args(argv)` und die
beiden neuen Zweige kommen davor. `setup/historical_loader.py` muss `from src import db`
importieren — prüfen und ggf. ergänzen.

- [ ] **Step 7.4: Tests laufen lassen, grün bestätigen**

Run: `pytest tests/unit/test_historical_loader.py -v`
Expected: PASS

- [ ] **Step 7.5: Commit**

```bash
git add setup/historical_loader.py tests/unit/test_historical_loader.py
git commit -m "feat: add --reactivate and --list-inactive to historical_loader

Sprint 3B / Plan 1, Task 7 (spec B.7, decision D3). Manual override for the
30-day auto-retry, plus a listing so deactivated tickers are visible without
opening SQLite.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: `guardrail_rejects` persistieren + Sektor aus der DB ins Prediction-Row ✅ ERLEDIGT (`6ab199d`, Schnitt 3)

Legt die Datenbasis für die Guardrail-Reject-Statistik der Weekly-Mail (B.9) und
für den weichen Sektor-Guardrail aus D6. Behebt gleichzeitig, dass `predictions.sector`
bisher immer NULL war.

**Files:**
- Modify: `src/db.py` (`SCHEMA_SQL`, `log_guardrail_reject`)
- Modify: `src/ranking.py` (`_guardrail_filter`, `_to_prediction_row`, `rank_and_persist`)
- Test: `tests/unit/test_db.py`, `tests/unit/test_ranking.py` (ergänzen)

**Interfaces:**
- Consumes: `db.get_ticker_sector()` (Task 3)
- Produces:
  - `db.log_guardrail_reject(conn, row: dict) -> None` — Keys: `date`, `run_type`,
    `ticker`, `direction`, `rule`, `detail`, `enforced`
  - `db.load_guardrail_rejects_since(conn, since: str) -> list[sqlite3.Row]`
  - `ranking._guardrail_filter(analyses, conn, date, run_type) -> list[dict]` (geänderte Signatur)
  - `ranking._to_prediction_row(analysis, date, run_type, market_context, conn) -> dict` (geänderte Signatur)

- [ ] **Step 8.1: Failing Tests für die DB-Seite schreiben**

```python
# tests/unit/test_db.py — anhängen:
from src.db import log_guardrail_reject, load_guardrail_rejects_since


def test_init_schema_creates_guardrail_rejects(in_memory_db):
    init_schema(in_memory_db)
    assert "guardrail_rejects" in get_tables(in_memory_db)


def test_log_and_load_guardrail_rejects(in_memory_db):
    init_schema(in_memory_db)
    log_guardrail_reject(in_memory_db, {
        "date": "2026-07-27", "run_type": "pre_market", "ticker": "AAPL",
        "direction": "long", "rule": "rr_ratio",
        "detail": "R/R 1.2 below hard minimum 1.5", "enforced": 1,
    })
    log_guardrail_reject(in_memory_db, {
        "date": "2026-07-20", "run_type": "pre_market", "ticker": "MSFT",
        "direction": "short", "rule": "sector_unknown",
        "detail": "no sector mapping", "enforced": 0,
    })
    rows = load_guardrail_rejects_since(in_memory_db, since="2026-07-25")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["rule"] == "rr_ratio"
    assert rows[0]["enforced"] == 1
```

- [ ] **Step 8.2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_db.py -k guardrail -v`
Expected: FAIL mit `ImportError: cannot import name 'log_guardrail_reject' from 'src.db'`

- [ ] **Step 8.3: DB-Seite implementieren**

```python
# src/db.py — SCHEMA_SQL erweitern:

CREATE TABLE IF NOT EXISTS guardrail_rejects (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    date                 TEXT NOT NULL,
    run_type             TEXT NOT NULL,
    ticker               TEXT NOT NULL,
    direction            TEXT,
    rule                 TEXT NOT NULL,
    detail               TEXT,
    enforced             INTEGER NOT NULL DEFAULT 1,
    sector_etf_momentum  REAL,   -- D9: Momentum-Snapshot zum Reject-Zeitpunkt
    sector_db_momentum   REAL,   -- D9: dito, DB-basiert
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_guardrail_rejects_date ON guardrail_rejects(date);
```

```python
# src/db.py — neue Funktionen, nach log_skipped_ticker() einfügen:

def log_guardrail_reject(conn: sqlite3.Connection, row: dict) -> None:
    """Persistiert eine verworfene (oder bei enforced=0: nur markierte) Analyse mit
    Regel und Detailtext, damit die Weekly-Mail auswerten kann, welche Guardrails
    wie oft greifen."""
    cols = ["date", "run_type", "ticker", "direction", "rule", "detail", "enforced"]
    placeholders = ", ".join(["?"] * len(cols))
    conn.execute(
        f"INSERT INTO guardrail_rejects ({', '.join(cols)}) VALUES ({placeholders})",
        [row.get(c) for c in cols],
    )
    conn.commit()


def load_guardrail_rejects_since(
    conn: sqlite3.Connection, since: str,
) -> list[sqlite3.Row]:
    """Gibt alle Guardrail-Rejects ab (einschliesslich) `since` zurück, neueste zuerst."""
    return conn.execute(
        "SELECT * FROM guardrail_rejects WHERE date >= ? ORDER BY date DESC, ticker",
        (since,),
    ).fetchall()
```

- [ ] **Step 8.4: Failing Tests für `ranking.py` schreiben**

```python
# tests/unit/test_ranking.py — anhängen:

def _analysis(ticker: str, direction: str = "long", **over) -> dict:
    """Vollständige, guardrail-taugliche Analyse. Einzelne Felder per kwargs
    überschreibbar, um gezielt einen Guardrail zu verletzen."""
    a = {
        "ticker": ticker, "direction": direction, "confidence": "medium",
        "current_price": 100.0, "tp_price": 104.0, "sl_price": 98.0,
        "rr_ratio": 2.0, "total_score": 7.5, "probability_pct": 70,
        "summary": "test", "sources_used": ["a", "b"],
        "signal_consistency_check": "ok",
        "hold_days_recommended": 1, "intraday_range_pct": 2.0,
        "asset_class": "stock",
        "scores": {
            dim: {"value": 7.0, "evidence": ["e1", "e2"]}
            for dim in (
                "market_environment", "company_quality", "valuation", "momentum",
                "risk", "sector_trend", "catalyst", "policy_risk",
            )
        },
    }
    a.update(over)
    return a


def test_guardrail_reject_is_persisted(in_memory_db):
    from src import db
    from src.ranking import rank_and_persist
    db.init_schema(in_memory_db)

    bad = _analysis("BAD", rr_ratio=1.0)   # unter RR_RATIO_MIN_HARD
    rank_and_persist(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        stock_analyses=[bad], commodity_crypto_analyses=[],
        market_context={"vix_level": 18.0, "market_regime": "risk_on"},
    )
    rows = db.load_guardrail_rejects_since(in_memory_db, since="2026-07-27")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "BAD"
    assert rows[0]["enforced"] == 1
    assert "R/R" in rows[0]["detail"]


def test_direction_none_is_not_logged_as_guardrail_reject(in_memory_db):
    from src import db
    from src.ranking import rank_and_persist
    db.init_schema(in_memory_db)
    rank_and_persist(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        stock_analyses=[_analysis("NEUTRAL", direction="none")],
        commodity_crypto_analyses=[], market_context={},
    )
    assert db.load_guardrail_rejects_since(in_memory_db, since="2026-07-27") == []


def test_prediction_row_takes_sector_from_ticker_sectors(in_memory_db):
    from src import db
    from src.ranking import rank_and_persist
    db.init_schema(in_memory_db)
    sid = db.resolve_sector_id(in_memory_db, "Semiconductors")
    db.upsert_ticker_sector(in_memory_db, "NVDA", sid)

    rank_and_persist(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        stock_analyses=[_analysis("NVDA")], commodity_crypto_analyses=[],
        market_context={"vix_level": 18.0, "market_regime": "risk_on"},
    )
    row = in_memory_db.execute(
        "SELECT sector, vix_at_prediction, market_regime FROM predictions WHERE ticker='NVDA'"
    ).fetchone()
    assert row["sector"] == "Semiconductors"
    assert row["vix_at_prediction"] == 18.0
    assert row["market_regime"] == "risk_on"


def test_prediction_row_sector_is_none_when_unmapped(in_memory_db):
    from src import db
    from src.ranking import rank_and_persist
    db.init_schema(in_memory_db)
    rank_and_persist(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        stock_analyses=[_analysis("UNMAPPED")], commodity_crypto_analyses=[],
        market_context={},
    )
    row = in_memory_db.execute(
        "SELECT sector FROM predictions WHERE ticker='UNMAPPED'"
    ).fetchone()
    assert row["sector"] is None
```

- [ ] **Step 8.5: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_ranking.py -k "guardrail_reject or sector" -v`
Expected: FAIL — keine `guardrail_rejects`-Zeilen bzw. `sector` ist `None` statt `"Technology"`.

- [ ] **Step 8.6: `ranking.py` anpassen**

```python
# src/ranking.py — _guardrail_filter() ERSETZEN:

def _guardrail_filter(
    analyses: Iterable[dict], conn, date: str, run_type: str,
) -> list[dict]:
    """Drops analyses with direction='none' or that fail GuardrailsChecker. Jede
    Ablehnung wird zusätzlich als guardrail_rejects-Zeile persistiert, damit die
    Weekly-Mail auswerten kann, welche Regeln wie oft greifen (Sprint 3B / B.9).
    direction='none' ist kein Reject, sondern eine bewusste Enthaltung."""
    checker = GuardrailsChecker()
    kept: list[dict] = []
    for a in analyses:
        if a.get("direction") == "none":
            continue
        ok, errs = checker.check_analysis(a)
        if not ok:
            ticker = a.get("ticker", "?")
            log.info(f"{ticker}: dropped by guardrails: {'; '.join(errs)}")
            db.log_guardrail_reject(conn, {
                "date": date, "run_type": run_type, "ticker": ticker,
                "direction": a.get("direction"),
                "rule": _rule_name(errs[0]),
                "detail": "; ".join(errs),
                "enforced": 1,
            })
            continue
        kept.append(a)
    return kept


def _rule_name(error_message: str) -> str:
    """Leitet aus einer Guardrail-Fehlermeldung einen kurzen, gruppierbaren
    Regelnamen ab, damit die Weekly-Mail nach Regel aggregieren kann."""
    msg = error_message.lower()
    if msg.startswith("required field missing"):
        return "required_field"
    if msg.startswith("too few sources"):
        return "sources"
    if "too few evidence" in msg:
        return "evidence"
    if msg.startswith("r/r"):
        return "rr_ratio"
    if "signal consistency" in msg:
        return "momentum_consistency"
    if "haltedauer" in msg:
        return "hold_days"
    if "intraday-range" in msg:
        return "intraday_range"
    if "confidence" in msg:
        return "confidence_data_quality"
    if "not above entry" in msg or "not below entry" in msg:
        return "tp_sl_direction"
    return "other"
```

```python
# src/ranking.py — _to_prediction_row(): Signatur + zwei Zeilen ändern.
# Neuer Parameter conn; die Zeile "sector": market_context.get("sector") wird ersetzt.

def _to_prediction_row(
    analysis: dict, date: str, run_type: str, market_context: dict, conn,
) -> dict:
    """Maps one guardrail-passing analysis dict onto the flat column layout
    expected by db.save_prediction(). Der Sektor kommt aus ticker_sectors
    (Sprint 3B / B.10), nicht mehr aus dem markt-weiten market_context-Dict."""
    scores = analysis.get("scores", {})
    _sector_row = db.get_ticker_sector(conn, analysis["ticker"])
    return {
        # ... alle bestehenden Felder unverändert ...
        "sector": _sector_row["name"] if _sector_row else None,
        # ... Rest unverändert ...
    }
```

```python
# src/ranking.py — rank_and_persist(): die drei Aufrufstellen anpassen.

    kept_stocks = _guardrail_filter(stock_analyses, conn, date, run_type)
    kept_cc     = _guardrail_filter(commodity_crypto_analyses, conn, date, run_type)

    # ... sortieren unverändert ...

    for a in (*longs, *shorts, *kept_cc):
        db.save_prediction(conn, _to_prediction_row(
            a, date=date, run_type=run_type, market_context=market_context, conn=conn,
        ))
```

- [ ] **Step 8.7: Tests laufen lassen, grün bestätigen**

Run: `pytest tests/unit/test_ranking.py tests/unit/test_db.py -v`
Expected: PASS

- [ ] **Step 8.8: Commit**

```bash
git add src/db.py src/ranking.py tests/unit/test_db.py tests/unit/test_ranking.py
git commit -m "feat: persist guardrail rejects, resolve prediction sector from DB

Sprint 3B / Plan 1, Task 8 (spec B.9, B.10). Guardrail rejections now land in
a guardrail_rejects table with a grouped rule name, so the weekly mail can
show which filters fire how often. predictions.sector is read from
ticker_sectors instead of the market-wide context dict, where it was always
NULL.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: Retention-Regeln anpassen ✅ ERLEDIGT (`6c42cc2`, Schnitt 3)

Setzt D4 um.

**Files:**
- Modify: `src/db.py` (`cleanup_old_data`)
- Test: `tests/unit/test_db.py` (ergänzen)

**Interfaces:**
- Produces: `db.cleanup_old_data(conn)` — Signatur unverändert, Verhalten geändert

- [ ] **Step 9.1: Failing Tests schreiben**

```python
# tests/unit/test_db.py — anhängen:
from src.db import cleanup_old_data


def test_cleanup_deletes_news_older_than_30_days(in_memory_db):
    init_schema(in_memory_db)
    # news_summaries.summary ist NOT NULL — muss mitgegeben werden.
    in_memory_db.execute(
        "INSERT INTO news_summaries (ticker, date, summary) "
        "VALUES ('AAPL', date('now','-45 days'), 'alt')"
    )
    in_memory_db.execute(
        "INSERT INTO news_summaries (ticker, date, summary) "
        "VALUES ('MSFT', date('now','-10 days'), 'frisch')"
    )
    in_memory_db.commit()
    cleanup_old_data(in_memory_db)
    left = [r["ticker"] for r in in_memory_db.execute(
        "SELECT ticker FROM news_summaries").fetchall()]
    assert left == ["MSFT"]


def test_cleanup_keeps_skipped_events_for_90_days(in_memory_db):
    init_schema(in_memory_db)
    in_memory_db.execute(
        "INSERT INTO skipped_tickers (ticker, date, run_type, reason) "
        "VALUES ('OLD', date('now','-100 days'), 'pre_market', 'x')"
    )
    in_memory_db.execute(
        "INSERT INTO skipped_tickers (ticker, date, run_type, reason) "
        "VALUES ('RECENT', date('now','-60 days'), 'pre_market', 'x')"
    )
    in_memory_db.commit()
    cleanup_old_data(in_memory_db)
    left = [r["ticker"] for r in in_memory_db.execute(
        "SELECT ticker FROM skipped_tickers ORDER BY ticker").fetchall()]
    assert left == ["RECENT"]


def test_cleanup_never_touches_ticker_status(in_memory_db):
    import config
    init_schema(in_memory_db)
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        log_skipped_ticker(in_memory_db, ticker="DEAD", date="2020-01-01",
                           run_type="pre_market", reason="x")
    cleanup_old_data(in_memory_db)
    st = get_ticker_status(in_memory_db, "DEAD")
    assert st is not None
    assert st["skip_count"] == config.TICKER_MAX_SKIPS + 1
    assert st["inactive"] == 1
```

- [ ] **Step 9.2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_db.py -k cleanup -v`
Expected: FAIL — `news_summaries` behält den 45-Tage-Eintrag (Grenze steht noch auf 90),
`skipped_tickers` verliert beide Zeilen (Grenze steht noch auf 30).

- [ ] **Step 9.3: `cleanup_old_data()` anpassen**

```python
# src/db.py — cleanup_old_data() ERSETZEN:

def cleanup_old_data(conn: sqlite3.Connection) -> None:
    """Löscht abgelaufene Zeilen: news_summaries > 30 Tage, trend_analyses > 180 Tage,
    skipped_tickers-Events > 90 Tage (Sprint 3B / B.7).

    ticker_status wird bewusst NIE angefasst — der kumulative Skip-Zähler und das
    inactive-Flag müssen die Event-Retention überleben. Zurückgesetzt wird nur über
    reactivate_ticker() oder das automatische retry_after-Datum."""
    conn.executescript(
        """
        DELETE FROM news_summaries WHERE date < date('now', '-30 days');
        DELETE FROM trend_analyses WHERE date < date('now', '-180 days');
        DELETE FROM skipped_tickers WHERE date < date('now', '-90 days');
        """
    )
    conn.commit()
```

- [ ] **Step 9.4: Tests laufen lassen, grün bestätigen**

Run: `pytest tests/unit/test_db.py -v`
Expected: PASS

- [ ] **Step 9.5: Commit**

```bash
git add src/db.py tests/unit/test_db.py
git commit -m "feat: adjust retention windows per spec B.7

Sprint 3B / Plan 1, Task 9 (decision D4). news_summaries 90->30 days,
skipped_tickers events 30->90 days, trend_analyses unchanged at 180.
ticker_status is explicitly never purged — the cumulative counter has to
outlive the event rows.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9a: Sektor-Momentum (Hybrid, D9) ✅ ERLEDIGT (`6fb3290`, Schnitt 3)

Erhebt beide Momentum-Signale je Sub-Sektor und persistiert sie getrennt. **Nur die
Datenerhebung** — die Guardrail-Auswertung (hart/weich) gehört zu B.3 und damit in Plan 2.

**Files:**
- Modify: `config.py` (`SECTOR_DB_MOMENTUM_MIN_TICKERS`)
- Modify: `src/db.py` (`SCHEMA_SQL`, `_apply_migrations`, neue Helper)
- Create: `src/sector_momentum.py`
- Test: `tests/unit/test_db.py`, `tests/unit/test_sector_momentum.py` (neu)

**Interfaces:**
- Consumes: `db.get_ticker_sector()` (Task 3), `config.SUB_SECTOR_ETFS`,
  `price_provider.get_price_history()`, `db.insert_price_bar_if_missing()`
- Produces:
  - `db.compute_sector_db_momentum(conn, date, min_tickers=3) -> dict[int, dict]`
    — `{sector_id: {"momentum": float | None, "ticker_count": int}}`
  - `db.save_sector_momentum(conn, row: dict) -> None` — Keys `date`, `run_type`,
    `sector_id`, `etf_momentum`, `db_momentum`, `ticker_count`
  - `db.load_sector_momentum(conn, date, run_type) -> dict[int, sqlite3.Row]`
  - `sector_momentum.collect_sector_momentum(conn, date, run_type, price_provider) -> dict[int, dict]`
  - Tabelle `sector_momentum`; neue Spalten `sector_etf_momentum` / `sector_db_momentum`
    in `predictions`

**Wichtig — Datenvoraussetzung:** Das ETF-Signal braucht die ETF-Bars in `price_history`.
Die 19 ETF-Symbole stehen **nicht** in den Ticker-Listen der Phase 1. `collect_sector_momentum()`
holt sie deshalb selbst per `get_price_history(etf, days=5)` und schreibt sie über
`insert_price_bar_if_missing()` weg — 19 zusätzliche Capital.com-Calls pro Run, bei 600
Calls/Min kostenlos und unkritisch.

- [ ] **Step 9a.1: Konstante in `config.py` ergänzen**

```python
# config.py — direkt nach VIX_TICKER einfügen:

# Mindestzahl Ticker in einem Sub-Sektor, damit das DB-basierte Momentum-Signal
# (D9) berechnet wird. Darunter ist der Durchschnitt statistisch wertlos und
# sector_momentum.db_momentum bleibt NULL.
SECTOR_DB_MOMENTUM_MIN_TICKERS = 3
```

- [ ] **Step 9a.2: Failing Tests für die DB-Seite schreiben**

```python
# tests/unit/test_db.py — anhängen:
from src.db import (
    compute_sector_db_momentum, save_sector_momentum, load_sector_momentum,
)


def _bar(conn, ticker: str, date: str, close: float) -> None:
    from src import db as _db
    _db.insert_price_bar_if_missing(
        conn, ticker=ticker, date=date, open_=close, high=close,
        low=close, close=close, volume=1000, source="capital.com",
    )


def test_init_schema_creates_sector_momentum(in_memory_db):
    init_schema(in_memory_db)
    assert "sector_momentum" in get_tables(in_memory_db)


def test_predictions_has_sector_momentum_columns(in_memory_db):
    init_schema(in_memory_db)
    cols = {r["name"] for r in in_memory_db.execute(
        "PRAGMA table_info(predictions)").fetchall()}
    assert {"sector_etf_momentum", "sector_db_momentum"}.issubset(cols)


def test_compute_sector_db_momentum_averages_daily_change(in_memory_db):
    """Drei Pharma-Ticker mit +2%, +4% und +6% ergeben +4% Sektor-Momentum."""
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Pharmaceuticals")
    for t, prev, today in (("JNJ", 100.0, 102.0), ("LLY", 100.0, 104.0),
                           ("ABBV", 100.0, 106.0)):
        upsert_ticker_sector(in_memory_db, t, sid)
        _bar(in_memory_db, t, "2026-07-24", prev)
        _bar(in_memory_db, t, "2026-07-27", today)
    in_memory_db.commit()

    out = compute_sector_db_momentum(in_memory_db, date="2026-07-27")
    assert out[sid]["ticker_count"] == 3
    assert round(out[sid]["momentum"], 4) == 4.0


def test_compute_sector_db_momentum_is_none_below_minimum(in_memory_db):
    """Zwei Ticker reichen nicht — der Durchschnitt waere statistisch wertlos."""
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Semiconductors")
    for t in ("NVDA", "AVGO"):
        upsert_ticker_sector(in_memory_db, t, sid)
        _bar(in_memory_db, t, "2026-07-24", 100.0)
        _bar(in_memory_db, t, "2026-07-27", 105.0)
    in_memory_db.commit()

    out = compute_sector_db_momentum(in_memory_db, date="2026-07-27")
    assert out[sid]["momentum"] is None
    assert out[sid]["ticker_count"] == 2


def test_compute_sector_db_momentum_honours_custom_minimum(in_memory_db):
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Semiconductors")
    for t in ("NVDA", "AVGO"):
        upsert_ticker_sector(in_memory_db, t, sid)
        _bar(in_memory_db, t, "2026-07-24", 100.0)
        _bar(in_memory_db, t, "2026-07-27", 105.0)
    in_memory_db.commit()
    out = compute_sector_db_momentum(in_memory_db, date="2026-07-27", min_tickers=2)
    assert round(out[sid]["momentum"], 4) == 5.0


def test_compute_sector_db_momentum_skips_tickers_without_previous_bar(in_memory_db):
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Pharmaceuticals")
    for t in ("JNJ", "LLY", "ABBV"):
        upsert_ticker_sector(in_memory_db, t, sid)
        _bar(in_memory_db, t, "2026-07-27", 105.0)
    _bar(in_memory_db, "JNJ", "2026-07-24", 100.0)
    in_memory_db.commit()
    out = compute_sector_db_momentum(in_memory_db, date="2026-07-27")
    assert out.get(sid, {}).get("ticker_count", 0) == 1


def test_save_and_load_sector_momentum_upserts(in_memory_db):
    init_schema(in_memory_db)
    sid = resolve_sector_id(in_memory_db, "Semiconductors")
    row = {"date": "2026-07-27", "run_type": "pre_market", "sector_id": sid,
           "etf_momentum": 1.5, "db_momentum": None, "ticker_count": 2}
    save_sector_momentum(in_memory_db, row)
    save_sector_momentum(in_memory_db, {**row, "etf_momentum": 2.5})
    loaded = load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")
    assert len(loaded) == 1
    assert loaded[sid]["etf_momentum"] == 2.5
    assert loaded[sid]["db_momentum"] is None
```

- [ ] **Step 9a.3: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_db.py -k sector_momentum -v`
Expected: FAIL mit `ImportError: cannot import name 'compute_sector_db_momentum' from 'src.db'`

- [ ] **Step 9a.4: Schema, Migration und DB-Helper implementieren**

```python
# src/db.py — SCHEMA_SQL erweitern:

CREATE TABLE IF NOT EXISTS sector_momentum (
    date         TEXT NOT NULL,
    run_type     TEXT NOT NULL,
    sector_id    INTEGER NOT NULL REFERENCES sectors(id),
    etf_momentum REAL,
    db_momentum  REAL,
    ticker_count INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, run_type, sector_id)
);
```

```python
# src/db.py — in _apply_migrations() ergänzen (zum bestehenden pred_cols-Block):

    if "sector_etf_momentum" not in pred_cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN sector_etf_momentum REAL")
    if "sector_db_momentum" not in pred_cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN sector_db_momentum REAL")

    gr_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(guardrail_rejects)"
    ).fetchall()}
    if gr_cols and "sector_etf_momentum" not in gr_cols:
        conn.execute("ALTER TABLE guardrail_rejects ADD COLUMN sector_etf_momentum REAL")
    if gr_cols and "sector_db_momentum" not in gr_cols:
        conn.execute("ALTER TABLE guardrail_rejects ADD COLUMN sector_db_momentum REAL")
```

```python
# src/db.py — neue Funktionen, nach get_ticker_sector() einfügen:

def compute_sector_db_momentum(
    conn: sqlite3.Connection,
    date: str,
    min_tickers: int = config.SECTOR_DB_MOMENTUM_MIN_TICKERS,
) -> dict[int, dict]:
    """Berechnet je Sub-Sektor die durchschnittliche Tagesperformance aller
    zugeordneten Ticker aus price_history — reines SQL, keine API-Calls, 0 EUR.

    Gibt {sector_id: {"momentum": float | None, "ticker_count": int}} zurück.
    `momentum` ist None, wenn weniger als `min_tickers` Ticker des Sub-Sektors
    einen Vortagesbar haben; der Durchschnitt wäre dann statistisch wertlos.
    Ticker ohne Vortagesbar zählen nicht mit."""
    rows = conn.execute(
        """SELECT ts.sector_id AS sector_id,
                  AVG((cur.close - prev.close) / prev.close * 100.0) AS momentum,
                  COUNT(*) AS n
           FROM ticker_sectors ts
           JOIN price_history cur
             ON cur.ticker = ts.ticker AND cur.date = ?
           JOIN price_history prev
             ON prev.ticker = ts.ticker
            AND prev.date = (SELECT MAX(p.date) FROM price_history p
                             WHERE p.ticker = ts.ticker AND p.date < ?)
           WHERE prev.close > 0
           GROUP BY ts.sector_id""",
        (date, date),
    ).fetchall()
    out: dict[int, dict] = {}
    for r in rows:
        n = int(r["n"])
        out[int(r["sector_id"])] = {
            "momentum": float(r["momentum"]) if n >= min_tickers else None,
            "ticker_count": n,
        }
    return out


def save_sector_momentum(conn: sqlite3.Connection, row: dict) -> None:
    """Schreibt oder überschreibt die beiden Momentum-Signale eines Sub-Sektors
    für einen Run (UNIQUE date+run_type+sector_id)."""
    cols = ["date", "run_type", "sector_id", "etf_momentum",
            "db_momentum", "ticker_count"]
    placeholders = ", ".join(["?"] * len(cols))
    conn.execute(
        f"INSERT OR REPLACE INTO sector_momentum ({', '.join(cols)}) "
        f"VALUES ({placeholders})",
        [row.get(c) for c in cols],
    )
    conn.commit()


def load_sector_momentum(
    conn: sqlite3.Connection, date: str, run_type: str,
) -> dict[int, sqlite3.Row]:
    """Gibt die gespeicherten Momentum-Zeilen eines Runs als {sector_id: Row} zurück."""
    rows = conn.execute(
        "SELECT * FROM sector_momentum WHERE date = ? AND run_type = ?",
        (date, run_type),
    ).fetchall()
    return {int(r["sector_id"]): r for r in rows}
```

- [ ] **Step 9a.5: Tests laufen lassen, grün bestätigen**

Run: `pytest tests/unit/test_db.py -v`
Expected: PASS

- [ ] **Step 9a.6: Failing Tests für `src/sector_momentum.py` schreiben**

```python
# tests/unit/test_sector_momentum.py — neue Datei:
from unittest.mock import MagicMock

import pandas as pd

from src import db


def _etf_frame(prev_close: float, close: float) -> pd.DataFrame:
    return pd.DataFrame(
        {"Open": [prev_close, close], "High": [prev_close, close],
         "Low": [prev_close, close], "Close": [prev_close, close],
         "Volume": [0, 0]},
        index=pd.to_datetime(["2026-07-24", "2026-07-27"]),
    )


def _bar(conn, ticker, date, close):
    db.insert_price_bar_if_missing(
        conn, ticker=ticker, date=date, open_=close, high=close,
        low=close, close=close, volume=1000, source="capital.com",
    )


def test_collect_writes_one_row_per_sub_sector(in_memory_db):
    import config
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)
    provider = MagicMock()
    provider._source_name = "capital.com"
    provider.get_price_history.return_value = _etf_frame(100.0, 101.0)

    out = collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=provider,
    )
    assert len(out) == len(config.SUB_SECTOR_ETFS)
    stored = db.load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")
    assert len(stored) == len(config.SUB_SECTOR_ETFS)


def test_collect_computes_etf_momentum_from_fetched_bars(in_memory_db):
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)
    provider = MagicMock()
    provider._source_name = "capital.com"
    provider.get_price_history.return_value = _etf_frame(100.0, 102.0)

    collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=provider,
    )
    sid = db.resolve_sector_id(in_memory_db, "Semiconductors")
    stored = db.load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")
    assert round(stored[sid]["etf_momentum"], 4) == 2.0


def test_collect_leaves_etf_momentum_none_when_fetch_fails(in_memory_db):
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)
    provider = MagicMock()
    provider._source_name = "capital.com"
    provider.get_price_history.return_value = None

    collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=provider,
    )
    sid = db.resolve_sector_id(in_memory_db, "Semiconductors")
    stored = db.load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")
    assert stored[sid]["etf_momentum"] is None


def test_collect_fetches_each_etf_only_once(in_memory_db):
    """MedTech, Pharma und Healthcare Rest teilen sich XLV — ein Call genuegt."""
    import config
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)
    provider = MagicMock()
    provider._source_name = "capital.com"
    provider.get_price_history.return_value = _etf_frame(100.0, 101.0)

    collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=provider,
    )
    assert provider.get_price_history.call_count == len(set(config.SUB_SECTOR_ETFS.values()))


def test_collect_fills_db_momentum_when_enough_tickers(in_memory_db):
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)
    sid = db.resolve_sector_id(in_memory_db, "Pharmaceuticals")
    for t, today in (("JNJ", 102.0), ("LLY", 104.0), ("ABBV", 106.0)):
        db.upsert_ticker_sector(in_memory_db, t, sid)
        _bar(in_memory_db, t, "2026-07-24", 100.0)
        _bar(in_memory_db, t, "2026-07-27", today)
    in_memory_db.commit()

    provider = MagicMock()
    provider._source_name = "capital.com"
    provider.get_price_history.return_value = _etf_frame(100.0, 101.0)

    collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=provider,
    )
    stored = db.load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")
    assert round(stored[sid]["db_momentum"], 4) == 4.0
    assert stored[sid]["ticker_count"] == 3
```

- [ ] **Step 9a.7: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_sector_momentum.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'src.sector_momentum'`

- [ ] **Step 9a.8: `src/sector_momentum.py` implementieren**

```python
# src/sector_momentum.py — neue Datei:
"""Sektor-Momentum: zwei unabhaengige Signale je Sub-Sektor.

Der ETF-Pfad holt die Tagesperformance des Sub-Sektor-ETF von Capital.com. Der
DB-Pfad mittelt die Tagesperformance aller Ticker desselben Sub-Sektors aus
price_history — reines SQL, kostenlos, aber erst ab config.SECTOR_DB_MOMENTUM_MIN_TICKERS
Tickern aussagekraeftig. Beide Werte werden getrennt gespeichert, nie verrechnet:
Sprint 3D soll datenbasiert messen koennen, welches Signal besser predictet.

Das Modul erhebt und persistiert nur. Die Guardrail-Auswertung (hartes Reject nur
bei uebereinstimmenden Signalen, sonst weiche Warnung) gehoert zu Phase B.3.
Eingefuehrt in Sprint 3B / Plan 1 (Entscheidung D9)."""
import logging

import pandas as pd

import config
from src import db
from src.providers.base import DataProvider

log = logging.getLogger("shares_future.sector_momentum")


def _daily_change_pct(df: pd.DataFrame | None) -> float | None:
    """Tagesperformance in Prozent aus den letzten zwei Bars, oder None wenn
    weniger als zwei Bars vorliegen bzw. der Vortagesschluss 0 ist."""
    if df is None or len(df) < 2:
        return None
    prev = float(df["Close"].iloc[-2])
    cur = float(df["Close"].iloc[-1])
    if prev <= 0:
        return None
    return (cur - prev) / prev * 100.0


def _fetch_etf_momentum(
    price_provider: DataProvider, conn, etf: str, date: str,
) -> float | None:
    """Holt die letzten Bars des Sektor-ETF, schreibt sie in price_history und
    gibt die Tagesperformance zurueck. None bei jedem Abruf- oder Datenproblem."""
    try:
        df = price_provider.get_price_history(etf, days=5)
    except Exception as e:
        log.warning(f"{etf}: ETF-Momentum-Abruf fehlgeschlagen: {e}")
        return None
    if df is None or df.empty:
        log.warning(f"{etf}: keine Bars fuer ETF-Momentum")
        return None

    _raw = getattr(price_provider, "_source_name", None)
    source = _raw if isinstance(_raw, str) else "capital.com"
    for ts, row in df.iterrows():
        d = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        if d > date:
            continue
        db.insert_price_bar_if_missing(
            conn, ticker=etf, date=d,
            open_=float(row.get("Open", 0)), high=float(row.get("High", 0)),
            low=float(row.get("Low", 0)), close=float(row.get("Close", 0)),
            volume=int(row.get("Volume", 0) or 0), source=source,
        )
    conn.commit()
    return _daily_change_pct(df)


def collect_sector_momentum(
    conn, date: str, run_type: str, price_provider: DataProvider,
) -> dict[int, dict]:
    """Erhebt beide Momentum-Signale fuer jeden Sub-Sektor und persistiert sie.

    Gibt {sector_id: {"etf_momentum": ..., "db_momentum": ..., "ticker_count": ...}}
    zurueck. Jeder ETF wird nur einmal abgerufen, auch wenn sich mehrere
    Sub-Sektoren einen teilen (MedTech/Pharma/Healthcare Rest -> XLV)."""
    db_by_sector = db.compute_sector_db_momentum(conn, date=date)

    etf_cache: dict[str, float | None] = {}
    out: dict[int, dict] = {}

    for name, etf in config.SUB_SECTOR_ETFS.items():
        row = conn.execute(
            "SELECT id FROM sectors WHERE name = ?", (name,),
        ).fetchone()
        if row is None:
            log.warning(f"Sub-Sektor {name!r} fehlt in der sectors-Tabelle")
            continue
        sector_id = int(row["id"])

        if etf not in etf_cache:
            etf_cache[etf] = _fetch_etf_momentum(price_provider, conn, etf, date)

        agg = db_by_sector.get(sector_id, {"momentum": None, "ticker_count": 0})
        entry = {
            "etf_momentum": etf_cache[etf],
            "db_momentum":  agg["momentum"],
            "ticker_count": agg["ticker_count"],
        }
        db.save_sector_momentum(conn, {
            "date": date, "run_type": run_type, "sector_id": sector_id, **entry,
        })
        out[sector_id] = entry

    both = sum(1 for e in out.values()
               if e["etf_momentum"] is not None and e["db_momentum"] is not None)
    log.info(
        f"Sektor-Momentum: {len(out)} Sub-Sektoren, {both} mit beiden Signalen "
        f"(nur dort kann der Guardrail hart greifen)"
    )
    return out
```

- [ ] **Step 9a.9: Tests laufen lassen, grün bestätigen**

Run: `pytest tests/unit/test_sector_momentum.py tests/unit/test_db.py -v`
Expected: PASS

- [ ] **Step 9a.10: Commit**

```bash
git add config.py src/db.py src/sector_momentum.py \
        tests/unit/test_sector_momentum.py tests/unit/test_db.py
git commit -m "feat: collect hybrid sector momentum (ETF + DB)

Sprint 3B / Plan 1, Task 9a (decision D9). Two independent signals per
sub-sector, stored separately and never merged: etf_momentum from the
sub-sector ETF, db_momentum as the average daily change of all tickers in
that sub-sector (pure SQL, no API cost, NULL below 3 tickers). Sprint 3D
decides which one predicts better; the guardrail logic itself is Plan 2.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---


## Task 10: Markt-Kontext-Modul ✅ ERLEDIGT (`e53fd18`, Schnitt 4)

Setzt D2 um. Neues Modul mit genau einer Aufgabe.

**Files:**
- Create: `prompts/market_context_v1.txt`
- Create: `src/market_context.py`
- Modify: `src/db.py` (`_apply_migrations`, `save_market_context`)
- Test: `tests/unit/test_market_context.py` (neu)
- Test: `tests/unit/test_db.py` (ergänzen)

**Interfaces:**
- Consumes: `src.utils.call_claude`, `src.utils.extract_json_blob`, `src.utils.WEB_SEARCH_TOOL`,
  `CostTracker.add_from_result()`, `CapitalComProvider.get_price_history()`, `config.VIX_TICKER`
- Produces:
  - `market_context.fetch_market_context(date, run_type, cost_tracker, price_provider) -> dict`
    mit den Keys `vix_level` (float|None), `advance_decline_ratio` (float|None),
    `market_regime` (str|None), `sector_rotation_in` (str|None),
    `sector_rotation_out` (str|None), `macro_summary` (str|None), `vix_source` (str)
  - `market_context.MarketContextError`
  - `db.save_market_context(conn, row: dict) -> None`

- [ ] **Step 10.1: Prompt-Datei anlegen**

```text
# prompts/market_context_v1.txt — neue Datei:
Du bist ein Marktdaten-Analyst. Deine Aufgabe ist es, den aktuellen Zustand des
US-Aktienmarkts in harten Zahlen zu erfassen — keine Handelsempfehlungen, keine
Einzeltitel-Analyse.

Nutze die Websuche, um für den angefragten Handelstag die folgenden Werte zu
ermitteln. Suche gezielt nach aktuellen Marktdaten-Quellen.

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt in genau dieser Struktur:

{
  "vix_level": 18.4,
  "advance_decline_ratio": 1.35,
  "market_regime": "risk_on",
  "sector_rotation_in": "Technology, Financials",
  "sector_rotation_out": "Utilities, Real Estate",
  "macro_summary": "Ein bis zwei Sätze zur Marktlage."
}

Feldregeln:
- vix_level: aktueller CBOE-VIX-Stand als Zahl. Nicht ermittelbar -> null.
- advance_decline_ratio: Verhältnis gestiegener zu gefallenen S&P-500-Titeln des
  letzten Handelstags (z.B. 350 gestiegen / 150 gefallen -> 2.33). Nicht
  ermittelbar -> null. Niemals schätzen oder erfinden.
- market_regime: genau einer von "risk_on", "risk_off", "neutral".
- sector_rotation_in / sector_rotation_out: kommaseparierte Sektornamen, in
  die Kapital fliesst bzw. aus denen es abfliesst. Unklar -> null.
- macro_summary: maximal zwei Sätze, deutsch.

Wenn du einen Wert nicht mit einer belastbaren Quelle belegen kannst, setze ihn
auf null. Ein null-Wert ist ausdrücklich besser als eine geratene Zahl — diese
Werte steuern nachgelagert harte Risikofilter.
```

- [ ] **Step 10.2: Failing Tests für `market_context.py` schreiben**

```python
# tests/unit/test_market_context.py — neue Datei:
from unittest.mock import MagicMock

import pandas as pd
import pytest


def _claude_result(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    return r


_GOOD_JSON = """
{"vix_level": 21.5, "advance_decline_ratio": 1.4, "market_regime": "neutral",
 "sector_rotation_in": "Technology", "sector_rotation_out": "Utilities",
 "macro_summary": "Ruhiger Handelstag."}
"""


def test_fetch_market_context_parses_claude_json(mocker):
    mocker.patch("src.market_context.call_claude",
                 return_value=_claude_result(_GOOD_JSON))
    from src.market_context import fetch_market_context
    tracker = MagicMock()
    out = fetch_market_context(
        date="2026-07-27", run_type="pre_market",
        cost_tracker=tracker, price_provider=None,
    )
    assert out["advance_decline_ratio"] == 1.4
    assert out["market_regime"] == "neutral"
    assert out["vix_level"] == 21.5
    assert out["vix_source"] == "claude"
    tracker.add_from_result.assert_called_once()


def test_capital_vix_overrides_claude_value(mocker):
    mocker.patch("src.market_context.call_claude",
                 return_value=_claude_result(_GOOD_JSON))
    provider = MagicMock()
    provider.get_price_history.return_value = pd.DataFrame(
        {"Open": [19.0], "High": [20.0], "Low": [18.0],
         "Close": [19.2], "Volume": [0]},
        index=pd.to_datetime(["2026-07-27"]),
    )
    from src.market_context import fetch_market_context
    out = fetch_market_context(
        date="2026-07-27", run_type="pre_market",
        cost_tracker=MagicMock(), price_provider=provider,
    )
    assert out["vix_level"] == 19.2
    assert out["vix_source"] == "capital.com"


def test_claude_vix_used_when_capital_returns_nothing(mocker):
    mocker.patch("src.market_context.call_claude",
                 return_value=_claude_result(_GOOD_JSON))
    provider = MagicMock()
    provider.get_price_history.return_value = None
    from src.market_context import fetch_market_context
    out = fetch_market_context(
        date="2026-07-27", run_type="pre_market",
        cost_tracker=MagicMock(), price_provider=provider,
    )
    assert out["vix_level"] == 21.5
    assert out["vix_source"] == "claude"


def test_invalid_market_regime_falls_back_to_none(mocker):
    mocker.patch(
        "src.market_context.call_claude",
        return_value=_claude_result('{"market_regime": "euphorisch"}'),
    )
    from src.market_context import fetch_market_context
    out = fetch_market_context(
        date="2026-07-27", run_type="pre_market",
        cost_tracker=MagicMock(), price_provider=None,
    )
    assert out["market_regime"] is None


def test_unparseable_response_raises(mocker):
    mocker.patch("src.market_context.call_claude",
                 return_value=_claude_result("kein JSON hier"))
    from src.market_context import fetch_market_context, MarketContextError
    with pytest.raises(MarketContextError):
        fetch_market_context(
            date="2026-07-27", run_type="pre_market",
            cost_tracker=MagicMock(), price_provider=None,
        )


def test_non_numeric_values_become_none(mocker):
    mocker.patch(
        "src.market_context.call_claude",
        return_value=_claude_result('{"vix_level": "keine Ahnung", '
                                    '"advance_decline_ratio": null}'),
    )
    from src.market_context import fetch_market_context
    out = fetch_market_context(
        date="2026-07-27", run_type="pre_market",
        cost_tracker=MagicMock(), price_provider=None,
    )
    assert out["vix_level"] is None
    assert out["advance_decline_ratio"] is None
```

- [ ] **Step 10.3: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_market_context.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'src.market_context'`

- [ ] **Step 10.4: `src/market_context.py` implementieren**

```python
# src/market_context.py — neue Datei:
"""Phase 0b: tagesaktueller Marktkontext.

Ein Claude-Call mit Websuche liefert VIX, Advance/Decline-Ratio, Marktregime und
Sektor-Rotation als strukturiertes JSON. Der VIX wird bevorzugt numerisch von
Capital.com genommen (deterministisch); Claudes Wert dient nur als Rückfallebene,
falls das Epic keine Bars liefert.

Das Modul kennt weder Datenbank noch E-Mail — es beschafft und validiert nur.
Persistiert wird vom Aufrufer (main.py) über db.save_market_context().
Eingeführt in Sprint 3B / Plan 1 (Spec B.3, Entscheidung D2)."""
import logging
from pathlib import Path

import config
from src.cost_tracker import CostTracker
from src.utils import call_claude, extract_json_blob, WEB_SEARCH_TOOL

log = logging.getLogger("shares_future.market_context")

SYSTEM_PROMPT = (Path(__file__).resolve().parent.parent
                 / "prompts" / "market_context_v1.txt").read_text()

MODEL = config.CLAUDE_MODEL_SONNET
MAX_TOKENS = 1024
VALID_REGIMES = {"risk_on", "risk_off", "neutral"}


class MarketContextError(RuntimeError):
    """Der Markt-Kontext-Call lieferte keine parsebare Antwort."""


def _as_float(value) -> float | None:
    """Konvertiert einen Claude-Wert nach float; alles Nicht-Numerische wird None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _vix_from_capital(price_provider, date: str) -> float | None:
    """Liest den letzten VIX-Schlusskurs über das Capital.com-Epic. Gibt None
    zurück, wenn kein Provider übergeben wurde oder keine Bars ankommen."""
    if price_provider is None:
        return None
    try:
        df = price_provider.get_price_history(config.VIX_TICKER, days=5)
    except Exception as e:
        log.warning(f"VIX-Abruf über Capital.com fehlgeschlagen: {e}")
        return None
    if df is None or getattr(df, "empty", True):
        return None
    try:
        return float(df["Close"].iloc[-1])
    except Exception as e:
        log.warning(f"VIX-Bar nicht lesbar: {e}")
        return None


def fetch_market_context(
    date: str,
    run_type: str,
    cost_tracker: CostTracker,
    price_provider=None,
) -> dict:
    """Ermittelt den Marktkontext für `date` und gibt ein validiertes Dict zurück.

    Keys: vix_level, advance_decline_ratio, market_regime, sector_rotation_in,
    sector_rotation_out, macro_summary, vix_source. Nicht belegbare Werte sind
    None — geraten wird nichts, weil diese Zahlen nachgelagert harte Filter steuern.
    Raises MarketContextError, wenn die Antwort nicht als JSON lesbar ist."""
    user_msg = (
        f"Heutiges Datum: {date} (Run: {run_type}).\n"
        "Ermittle den aktuellen US-Marktkontext und antworte mit dem JSON-Objekt "
        "aus deinem System-Prompt."
    )
    result = call_claude(
        model=MODEL, system=SYSTEM_PROMPT, user=user_msg,
        max_tokens=MAX_TOKENS, tools=[WEB_SEARCH_TOOL],
    )
    cost_tracker.add_from_result(result)
    parsed = extract_json_blob(result.text, MarketContextError)

    regime = parsed.get("market_regime")
    if regime not in VALID_REGIMES:
        if regime is not None:
            log.warning(f"unbekanntes market_regime {regime!r} — auf None gesetzt")
        regime = None

    vix_capital = _vix_from_capital(price_provider, date)
    vix_claude = _as_float(parsed.get("vix_level"))
    vix_level = vix_capital if vix_capital is not None else vix_claude
    vix_source = "capital.com" if vix_capital is not None else "claude"

    out = {
        "vix_level":             vix_level,
        "vix_source":            vix_source,
        "advance_decline_ratio": _as_float(parsed.get("advance_decline_ratio")),
        "market_regime":         regime,
        "sector_rotation_in":    parsed.get("sector_rotation_in"),
        "sector_rotation_out":   parsed.get("sector_rotation_out"),
        "macro_summary":         parsed.get("macro_summary"),
    }
    log.info(
        f"Markt-Kontext: VIX={out['vix_level']} ({vix_source}), "
        f"A/D={out['advance_decline_ratio']}, Regime={out['market_regime']}"
    )
    return out
```

- [ ] **Step 10.5: Tests laufen lassen, grün bestätigen**

Run: `pytest tests/unit/test_market_context.py -v`
Expected: PASS

- [ ] **Step 10.6: Failing Test für `db.save_market_context()` schreiben**

```python
# tests/unit/test_db.py — anhängen:
from src.db import save_market_context


def test_market_context_has_advance_decline_column(in_memory_db):
    init_schema(in_memory_db)
    cols = {r["name"] for r in in_memory_db.execute(
        "PRAGMA table_info(market_context)").fetchall()}
    assert "advance_decline_ratio" in cols


def test_save_market_context_upserts_on_date_and_run_type(in_memory_db):
    init_schema(in_memory_db)
    row = {
        "date": "2026-07-27", "run_type": "pre_market", "vix_level": 18.0,
        "advance_decline_ratio": 1.4, "market_regime": "risk_on",
        "sector_rotation_in": "Technology", "sector_rotation_out": "Utilities",
        "macro_summary": "ruhig",
    }
    save_market_context(in_memory_db, row)
    save_market_context(in_memory_db, {**row, "vix_level": 22.0})
    rows = in_memory_db.execute("SELECT * FROM market_context").fetchall()
    assert len(rows) == 1
    assert rows[0]["vix_level"] == 22.0
    assert rows[0]["advance_decline_ratio"] == 1.4
```

- [ ] **Step 10.7: Test laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_db.py -k market_context -v`
Expected: FAIL — Spalte `advance_decline_ratio` fehlt, `save_market_context` nicht importierbar.

- [ ] **Step 10.8: Migration + `save_market_context` implementieren**

```python
# src/db.py — in _apply_migrations() ergänzen (ans Ende der Funktion, vor conn.commit()):

    mc_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(market_context)"
    ).fetchall()}
    if "advance_decline_ratio" not in mc_cols:
        conn.execute("ALTER TABLE market_context ADD COLUMN advance_decline_ratio REAL")
```

```python
# src/db.py — neue Funktion, nach save_trend_analysis() einfügen:

def save_market_context(conn: sqlite3.Connection, row: dict) -> None:
    """Schreibt oder überschreibt den Marktkontext eines Run (UNIQUE date+run_type)."""
    cols = [
        "date", "run_type", "sp500_change_pct", "vix_level", "market_regime",
        "oil_price", "gold_price", "btc_price", "fear_greed_value",
        "policy_risk_level", "sector_rotation_in", "sector_rotation_out",
        "macro_summary", "advance_decline_ratio",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    conn.execute(
        f"INSERT OR REPLACE INTO market_context ({', '.join(cols)}) "
        f"VALUES ({placeholders})",
        [row.get(c) for c in cols],
    )
    conn.commit()
```

**Achtung:** `_apply_migrations()` läuft in `init_schema()` **nach**
`conn.executescript(SCHEMA_SQL)`, die Tabelle existiert dort also bereits.
Bestehende DBs bekommen die Spalte über den `PRAGMA`-Guard nachgezogen.

- [ ] **Step 10.9: Tests laufen lassen, grün bestätigen**

Run: `pytest tests/unit/test_db.py tests/unit/test_market_context.py -v`
Expected: PASS

- [ ] **Step 10.10: Commit**

```bash
git add prompts/market_context_v1.txt src/market_context.py src/db.py \
        tests/unit/test_market_context.py tests/unit/test_db.py
git commit -m "feat: add market context module (VIX, A/D ratio, regime)

Sprint 3B / Plan 1, Task 10 (spec B.3, decision D2). A dedicated Claude call
with web search fills the market_context table, which existed but was never
written to. VIX prefers the numeric Capital.com value; Claude's number is the
fallback. Unverifiable values stay null by design.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 11: Markt-Kontext in die Pipeline verdrahten ✅ ERLEDIGT (`ccb3010`, Schnitt 4)

Ersetzt das hardcodierte `None`-Dict in `main.py:226`.

**Files:**
- Modify: `main.py` (`run_pipeline`)
- Test: `tests/unit/test_main.py` (ergänzen)

**Interfaces:**
- Consumes: `market_context.fetch_market_context()` (Task 10), `db.save_market_context()` (Task 10)
- Produces: `payload["market_context"]` im Daily-Mail-Payload (von Plan 2 genutzt)

- [ ] **Step 11.1: Failing Tests schreiben**

```python
# tests/unit/test_main.py — anhängen:

def test_pipeline_persists_market_context_and_passes_it_to_ranking(tmp_db_path, mocker):
    """Der Markt-Kontext landet in der DB und im Ranking — nicht mehr hardcoded None."""
    mocker.patch("main.analyze_trends", return_value={"trends": []})
    mocker.patch("main.collect", return_value=([], 0))
    mocker.patch("main.quick_filter_batch", return_value=[])
    mocker.patch("main.run_policy_monitor", return_value={})
    mocker.patch("main.analyze_assets", return_value=[])
    mocker.patch("main.analyze_commodities_and_crypto", return_value=[])
    mocker.patch("main.fetch_fear_greed", return_value={})
    mocker.patch("main.check_open_positions", return_value=[])
    mocker.patch("main.generate_daily_briefing", return_value=[])
    mocker.patch("main.send_daily_email")
    mocker.patch("main.fetch_market_context", return_value={
        "vix_level": 23.4, "vix_source": "capital.com",
        "advance_decline_ratio": 0.8, "market_regime": "risk_off",
        "sector_rotation_in": "Utilities", "sector_rotation_out": "Technology",
        "macro_summary": "nervoes",
    })
    mock_rank = mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
    })

    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))

    passed = mock_rank.call_args.kwargs["market_context"]
    assert passed["vix_level"] == 23.4
    assert passed["market_regime"] == "risk_off"

    from src import db
    conn = db.connect(str(tmp_db_path))
    row = conn.execute(
        "SELECT * FROM market_context WHERE date='2026-07-27'").fetchone()
    assert row["vix_level"] == 23.4
    assert row["advance_decline_ratio"] == 0.8
    conn.close()


def test_pipeline_survives_market_context_failure(tmp_db_path, mocker):
    """Ein fehlgeschlagener Markt-Kontext-Call darf den Run nicht abbrechen."""
    from src.market_context import MarketContextError
    mocker.patch("main.analyze_trends", return_value={"trends": []})
    mocker.patch("main.collect", return_value=([], 0))
    mocker.patch("main.quick_filter_batch", return_value=[])
    mocker.patch("main.run_policy_monitor", return_value={})
    mocker.patch("main.analyze_assets", return_value=[])
    mocker.patch("main.analyze_commodities_and_crypto", return_value=[])
    mocker.patch("main.fetch_fear_greed", return_value={})
    mocker.patch("main.check_open_positions", return_value=[])
    mocker.patch("main.generate_daily_briefing", return_value=[])
    mocker.patch("main.send_daily_email")
    mocker.patch("main.fetch_market_context",
                 side_effect=MarketContextError("no json"))
    mock_rank = mocker.patch("main.rank_and_persist", return_value={
        "top_long": [], "top_short": [], "commodities_crypto": [],
    })

    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))

    passed = mock_rank.call_args.kwargs["market_context"]
    assert passed["vix_level"] is None
    assert passed["market_regime"] is None
```

- [ ] **Step 11.2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_main.py -k market_context -v`
Expected: FAIL mit `AttributeError: <module 'main'> does not have the attribute 'fetch_market_context'`

- [ ] **Step 11.3: `main.py` verdrahten**

```python
# main.py — Import ergänzen (nach der commodities_crypto-Import-Gruppe):
from src.market_context import fetch_market_context, MarketContextError
```

```python
# main.py — run_pipeline(): den Payload-Dict-Initialwert um einen Key erweitern:
        "skipped_tickers": [],
        "market_context": {},
        "yesterday_outcomes": {},
```

```python
# main.py — run_pipeline(): als ERSTEN Block INNERHALB des try (direkt nach "try:",
# vor "# Phase 1 — Stocks data") einfügen:

        # Phase 0b — Markt-Kontext (VIX, A/D-Ratio, Regime). Nicht fatal: schlägt
        # der Call fehl, läuft der Run mit leerem Kontext weiter.
        market_ctx = {
            "vix_level": None, "vix_source": None, "advance_decline_ratio": None,
            "market_regime": None, "sector_rotation_in": None,
            "sector_rotation_out": None, "macro_summary": None,
        }
        try:
            market_ctx = fetch_market_context(
                date=date, run_type=run_type, cost_tracker=cost_tracker,
                price_provider=price_provider,
            )
            db.save_market_context(conn, {**market_ctx, "date": date, "run_type": run_type})
        except MarketContextError as e:
            log.warning(f"Markt-Kontext nicht ermittelbar, Run läuft ohne: {e}")
        payload["market_context"] = market_ctx
```

```python
# main.py — run_pipeline(): den hardcodierten Block bei Phase 4 ENTFERNEN.
# Vorher:
#         market_ctx = {
#             "vix_level": None, "market_regime": None, "sector": None,
#         }
#         ranked = rank_and_persist(...)
# Nachher (nur noch der Aufruf, market_ctx kommt aus Phase 0b):
        ranked = rank_and_persist(
            conn=conn, date=date, run_type=run_type,
            stock_analyses=deep_stocks,
            commodity_crypto_analyses=deep_cc,
            market_context=market_ctx,
        )
```

**Hinweis:** `CostCapExceeded` aus `fetch_market_context` wird **nicht** vom
`except MarketContextError` gefangen und propagiert wie gewohnt zum äusseren
`except CostCapExceeded` — das ist gewollt (Regel: Kosten-Abbruch schickt trotzdem Mail).

- [ ] **Step 11.4: Tests laufen lassen, grün bestätigen**

Run: `pytest tests/unit/test_main.py -v`
Expected: PASS

- [ ] **Step 11.5: Commit**

```bash
git add main.py tests/unit/test_main.py
git commit -m "feat: wire market context into the pipeline

Sprint 3B / Plan 1, Task 11 (decision D2). Replaces the hardcoded
{vix_level: None, market_regime: None, sector: None} dict at main.py:226.
predictions.vix_at_prediction and market_regime now carry real values, and
market_context rows are written per run. A failed context call degrades to
an empty context instead of aborting the run.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 12: Gap-Erkennung in Phase 1 ✅ ERLEDIGT (`7698276`, Schnitt 4)

Setzt B.8 um.

**Files:**
- Modify: `src/data_collector.py` (neue Helper + Aufruf in `_process_ticker`)
- Test: `tests/unit/test_data_collector.py` (ergänzen)

**Interfaces:**
- Consumes: `price_provider.get_ohlc_after()`, `db.insert_price_bar_if_missing()`
- Produces:
  - `data_collector._expected_trading_days(from_date: str, to_date: str) -> list[str]`
    — Handelstage (Mo–Fr) **nach** `from_date` bis einschliesslich `to_date`
  - `data_collector._fill_price_gaps(ticker, price_provider, conn, date) -> int`
    — Anzahl nachgeladener Bars

- [ ] **Step 12.1: Failing Tests schreiben**

```python
# tests/unit/test_data_collector.py — anhängen:
import pandas as pd


def test_expected_trading_days_skips_weekend():
    from src.data_collector import _expected_trading_days
    # Freitag 2026-07-24 -> Montag 2026-07-27: kein fehlender Handelstag dazwischen
    assert _expected_trading_days("2026-07-24", "2026-07-27") == ["2026-07-27"]


def test_expected_trading_days_lists_real_gap():
    from src.data_collector import _expected_trading_days
    # Montag 2026-07-20 -> Freitag 2026-07-24: Di/Mi/Do/Fr fehlen
    assert _expected_trading_days("2026-07-20", "2026-07-24") == [
        "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24",
    ]


def test_expected_trading_days_empty_when_up_to_date():
    from src.data_collector import _expected_trading_days
    assert _expected_trading_days("2026-07-27", "2026-07-27") == []


def test_fill_price_gaps_backfills_missing_bars(in_memory_db, mocker):
    from src import db
    from src.data_collector import _fill_price_gaps
    db.init_schema(in_memory_db)
    db.insert_price_bar_if_missing(
        in_memory_db, ticker="AAPL", date="2026-07-20",
        open_=100, high=101, low=99, close=100.5, volume=1000,
        source="capital.com",
    )
    in_memory_db.commit()

    provider = mocker.MagicMock()
    provider._source_name = "capital.com"
    provider.get_ohlc_after.return_value = pd.DataFrame(
        {"Open": [101.0, 102.0], "High": [103.0, 104.0],
         "Low": [100.0, 101.0], "Close": [102.0, 103.0], "Volume": [900, 950]},
        index=pd.to_datetime(["2026-07-21", "2026-07-22"]),
    )

    n = _fill_price_gaps("AAPL", provider, in_memory_db, date="2026-07-22")
    assert n == 2
    dates = [r["date"] for r in in_memory_db.execute(
        "SELECT date FROM price_history WHERE ticker='AAPL' ORDER BY date").fetchall()]
    assert dates == ["2026-07-20", "2026-07-21", "2026-07-22"]


def test_fill_price_gaps_noop_over_weekend(in_memory_db, mocker):
    from src import db
    from src.data_collector import _fill_price_gaps
    db.init_schema(in_memory_db)
    db.insert_price_bar_if_missing(
        in_memory_db, ticker="AAPL", date="2026-07-24",  # Freitag
        open_=100, high=101, low=99, close=100.5, volume=1000,
        source="capital.com",
    )
    in_memory_db.commit()
    provider = mocker.MagicMock()
    # Montag: nur der heutige Bar fehlt, den holt _ensure_today_bar — kein Gap-Fetch
    assert _fill_price_gaps("AAPL", provider, in_memory_db, date="2026-07-27") == 0
    provider.get_ohlc_after.assert_not_called()


def test_fill_price_gaps_noop_on_empty_history(in_memory_db, mocker):
    from src import db
    from src.data_collector import _fill_price_gaps
    db.init_schema(in_memory_db)
    provider = mocker.MagicMock()
    assert _fill_price_gaps("NEW", provider, in_memory_db, date="2026-07-27") == 0
    provider.get_ohlc_after.assert_not_called()
```

- [ ] **Step 12.2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_data_collector.py -k "trading_days or price_gaps" -v`
Expected: FAIL mit `ImportError: cannot import name '_expected_trading_days' from 'src.data_collector'`

- [ ] **Step 12.3: Gap-Erkennung implementieren**

```python
# src/data_collector.py — neue Funktionen, direkt VOR _ensure_today_bar() einfügen:

def _expected_trading_days(from_date: str, to_date: str) -> list[str]:
    """Listet alle Wochentage (Mo-Fr) NACH `from_date` bis einschliesslich `to_date`.

    Bekannte Einschränkung (Spec B.8): ohne Börsen-Feiertagskalender gelten
    US-Feiertage wie Thanksgiving fälschlich als Handelstag. Der Nachladeversuch
    liefert dann schlicht keine Bars — funktional unkritisch, kostet je einen
    leeren API-Call."""
    start = _date_cls.fromisoformat(from_date)
    end = _date_cls.fromisoformat(to_date)
    out: list[str] = []
    cur = start + timedelta(days=1)
    while cur <= end:
        if cur.weekday() < 5:          # 0=Montag ... 4=Freitag
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def _fill_price_gaps(
    ticker: str, price_provider: DataProvider, conn, date: str,
) -> int:
    """Lädt fehlende Bars zwischen dem letzten DB-Datum und `date` nach und gibt
    die Anzahl neu eingefügter Zeilen zurück.

    Kein Nachladen, wenn der Ticker noch gar keine Historie hat (das übernimmt
    setup/historical_loader.py bzw. der Fallback in _ensure_today_bar) oder wenn
    nur der heutige Bar fehlt — dafür ist _ensure_today_bar zuständig."""
    row = conn.execute(
        "SELECT MAX(date) AS last_date FROM price_history WHERE ticker = ?",
        (ticker,),
    ).fetchone()
    last_date = row["last_date"] if row else None
    if not last_date or last_date >= date:
        return 0

    missing = _expected_trading_days(last_date, date)
    # Nur der heutige Bar fehlt -> _ensure_today_bar erledigt das ohne Extra-Call.
    if len(missing) <= 1:
        return 0

    log.info(
        f"{ticker}: Lücke erkannt — letzter Bar {last_date}, "
        f"{len(missing)} Handelstage bis {date} fehlen. Lade nach."
    )
    try:
        df = price_provider.get_ohlc_after(ticker, last_date, date)
    except Exception as e:
        log.warning(f"{ticker}: Gap-Nachladen fehlgeschlagen: {e}")
        return 0
    if df is None or df.empty:
        log.warning(f"{ticker}: Gap-Nachladen lieferte keine Bars")
        return 0

    _raw_source = getattr(price_provider, "_source_name", None)
    source = _raw_source if isinstance(_raw_source, str) else "capital.com"
    inserted = 0
    for ts, r in df.iterrows():
        d = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        if d <= last_date or d > date:
            continue
        db.insert_price_bar_if_missing(
            conn, ticker=ticker, date=d,
            open_=float(r.get("Open", 0)), high=float(r.get("High", 0)),
            low=float(r.get("Low", 0)), close=float(r.get("Close", 0)),
            volume=int(r.get("Volume", 0) or 0), source=source,
        )
        inserted += 1
    conn.commit()
    log.info(f"{ticker}: {inserted} fehlende Bars nachgeladen")
    return inserted
```

```python
# src/data_collector.py — _process_ticker(): Step 1 erweitern.
# Vorher:
#     # Step 1: Ensure today's bar is in DB
#     _ensure_today_bar(ticker, price_provider, conn, date)
# Nachher:
    # Step 1: Lücken schliessen, dann den heutigen Bar sicherstellen (Spec B.8)
    _fill_price_gaps(ticker, price_provider, conn, date)
    _ensure_today_bar(ticker, price_provider, conn, date)
```

**Pflicht-Ergänzung:** `src/data_collector.py` importiert aktuell **nichts** aus
`datetime` (Imports: `logging`, `math`, `time`, `Any`, `pandas`, `pandas_ta` oben,
sowie `DataProvider`, `db`, `config` ab Zeile 178). Ergänzen:

```python
# src/data_collector.py — zu den bestehenden Imports oben hinzufügen:
from datetime import date as _date_cls, timedelta
```

- [ ] **Step 12.4: Tests laufen lassen, grün bestätigen**

Run: `pytest tests/unit/test_data_collector.py -v`
Expected: PASS

- [ ] **Step 12.5: Commit**

```bash
git add src/data_collector.py tests/unit/test_data_collector.py
git commit -m "feat: detect and backfill price history gaps in Phase 1

Sprint 3B / Plan 1, Task 12 (spec B.8). Weekends are handled correctly (no
gap Friday->Monday); a real gap triggers one get_ohlc_after backfill.
Known limitation: without a market-holiday calendar, US holidays read as
gaps and cost one empty API call each.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 13: Bug B-05 — echte Abbruch-Phase melden ✅ ERLEDIGT (`7c4c311`, Schnitt 4)

**Files:**
- Modify: `main.py` (`run_pipeline`, `_guess_aborted_phase` entfernen)
- Test: `tests/unit/test_main.py` (ergänzen)

**Interfaces:**
- Produces: `cost_tracker.aborted_at_phase` trägt den tatsächlichen Phasennamen.
  `_guess_aborted_phase()` entfällt ersatzlos.

- [ ] **Step 13.1: Failing Test schreiben**

```python
# tests/unit/test_main.py — anhängen:

def test_cost_cap_abort_reports_the_actual_phase(tmp_db_path, mocker):
    """B-05: Bricht der Run in Phase 3 ab, darf nicht 'policy_monitor' gemeldet werden."""
    from src.cost_tracker import CostCapExceeded
    mocker.patch("main.analyze_trends", return_value={"trends": []})
    mocker.patch("main.fetch_market_context", return_value={
        "vix_level": None, "vix_source": None, "advance_decline_ratio": None,
        "market_regime": None, "sector_rotation_in": None,
        "sector_rotation_out": None, "macro_summary": None,
    })
    mocker.patch("main.collect", return_value=([], 0))
    mocker.patch("main.quick_filter_batch", return_value=[])
    mocker.patch("main.run_policy_monitor", return_value={})
    mocker.patch("main.generate_daily_briefing", return_value=[])
    mocker.patch("main.analyze_assets", side_effect=CostCapExceeded("cap hit"))
    mocker.patch("main.send_daily_email")

    from main import run_pipeline
    run_pipeline(run_type="pre_market", date="2026-07-27", db_path=str(tmp_db_path))

    from src import db
    conn = db.connect(str(tmp_db_path))
    row = conn.execute(
        "SELECT aborted_at_phase FROM cost_tracking WHERE date='2026-07-27'").fetchone()
    conn.close()
    assert row["aborted_at_phase"] == "deep_analysis"


def test_guess_aborted_phase_is_gone():
    import main
    assert not hasattr(main, "_guess_aborted_phase")
```

- [ ] **Step 13.2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `pytest tests/unit/test_main.py -k aborted -v`
Expected: FAIL — `aborted_at_phase` ist `"policy_monitor"` statt `"deep_analysis"`.

- [ ] **Step 13.3: Phasen-Tracking implementieren**

```python
# main.py — run_pipeline(): vor dem try-Block eine Variable anlegen:
    current_phase = "trend_analysis"
```

Dann **vor jedem Phasenblock** innerhalb des `try` die Variable setzen. Die
vollständige Zuordnung:

```python
    try:
        current_phase = "market_context"
        # ... Phase 0b Block aus Task 11 ...

        current_phase = "data_collection"
        # ... Phase 1 collect(...) ...

        current_phase = "data_collection_cc"
        # ... Phase 1b collect(...) für Commodities/Crypto ...

        current_phase = "quick_filter"
        # ... Phase 2 quick_filter_batch(...) ...

        current_phase = "policy_monitor"
        # ... run_policy_monitor(...) + generate_daily_briefing(...) ...

        current_phase = "deep_analysis"
        # ... analyze_assets(...) ...

        current_phase = "commodities_crypto"
        # ... fetch_fear_greed() + analyze_commodities_and_crypto(...) ...

        current_phase = "portfolio_check"
        # ... check_open_positions(...) ...

        current_phase = "ranking"
        # ... rank_and_persist(...) ...

    except CostCapExceeded as e:
        log.warning(f"Run aborted in phase '{current_phase}': {e}")
        cost_tracker.aborted_at_phase = current_phase
        aborted_at = current_phase
```

```python
# main.py — _guess_aborted_phase() KOMPLETT LÖSCHEN (Zeilen 257-260):
# def _guess_aborted_phase(_exc: CostCapExceeded) -> str:
#     """We don't have a precise phase from the exception — return a stable
#     placeholder. The orchestrator could thread a phase name in later."""
#     return "policy_monitor"
```

**Hinweis:** Die lokale Variable `aborted_at` wird im bestehenden Code gesetzt,
aber nirgends weiter gelesen (`payload["cost_summary"]` bezieht die Phase über
`cost_tracker.summary()`). Sie bleibt der Klarheit halber erhalten — nicht
entfernen, das wäre eine unabhängige Aufräumaktion ausserhalb dieses Plans.

- [ ] **Step 13.4: Tests laufen lassen, grün bestätigen**

Run: `pytest tests/unit/test_main.py -v`
Expected: PASS

- [ ] **Step 13.5: Commit**

```bash
git add main.py tests/unit/test_main.py
git commit -m "fix: report the actual aborted phase on cost-cap abort (B-05)

Sprint 3B / Plan 1, Task 13. run_pipeline now threads a current_phase
variable through the try block; _guess_aborted_phase(), which always
returned 'policy_monitor' regardless of where the run died, is removed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 14: Gesamtlauf, Coverage und Doku ✅ ERLEDIGT (Schnitt 4) — PLAN 1 ABGESCHLOSSEN

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/specs/PROJECT_STATUS.md`
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 14.1: Vollständige Test-Suite mit Coverage laufen lassen**

Run: `pytest tests/ --cov=src --cov-fail-under=80`
Expected: PASS, Coverage >= 80%. Bei Unterschreitung fehlende Zweige in
`src/market_context.py` und den neuen `src/db.py`-Helpern gezielt nachtesten —
**keine** Absenkung der Schwelle (Regel 8).

- [ ] **Step 14.2: Docker-Smoke-Test**

```bash
docker compose build
docker compose run --rm trading-harry --run-type close
```
Expected: Läuft durch, legt die neuen Tabellen an, keine Migrations-Fehler auf
einer bestehenden `tracking.db`.

- [ ] **Step 14.3: Migration gegen eine echte Alt-DB prüfen**

```bash
gh release download db-latest --pattern "tracking.db" --dir /tmp/dbcheck
python -c "
from src import db
conn = db.connect('/tmp/dbcheck/tracking.db')
db.init_schema(conn)
print(sorted(db.get_tables(conn)))
print([r['name'] for r in conn.execute('PRAGMA table_info(market_context)')])
conn.close()
"
```
Expected: `sectors`, `ticker_sectors`, `ticker_status`, `guardrail_rejects` sind
vorhanden, `market_context` hat `advance_decline_ratio`, keine Exception.

- [ ] **Step 14.4: `CLAUDE.md` aktualisieren**

In der Projektstruktur `src/market_context.py` und `setup/verify_epics.py` ergänzen.
Bei „Wichtige Designentscheidungen" aufnehmen:
- `SECTOR_ALIASES` normalisiert Finnhub-Werte auf 21 Sub-Sektoren (feiner als GICS: SOXX statt XLK für Halbleiter); unbekannte Werte werden geloggt, nie stillschweigend verworfen
- Ticker werden nach `TICKER_MAX_SKIPS = 20` Datenqualitäts-Skips deaktiviert, Auto-Retry nach 30 Tagen, manueller Reset via `--reactivate`

Bei „Wichtige Befehle" ergänzen:
```bash
# Capital.com-Epics für Sektor-ETFs + VIX verifizieren (einmalig, manuell)
python setup/verify_epics.py

# Deaktivierte Ticker anzeigen / reaktivieren
python setup/historical_loader.py --list-inactive
python setup/historical_loader.py --reactivate AAPL MSFT
```

- [ ] **Step 14.5: `PROJECT_STATUS.md` aktualisieren**

- In Abschnitt 1 eine Zeile „Sprint 3B / Plan 1 — Fundament (abgeschlossen, <DATUM>)" mit Modul-Tabelle ergänzen
- In B.3, B.7 und B.10 die als **offen** markierten Fragen durch die Entscheidungen D1–D6 ersetzen (die Fragen nicht löschen, sondern als beantwortet kennzeichnen — die Begründung ist später wertvoll)
- B.11: B-05 als erledigt markieren; die verbleibende Teilaufgabe („`hold_days_recommended` als Spalte in der Mail-Tabelle") ausdrücklich Plan 2 zuordnen
- In Abschnitt 3 (Bekannte Bugs) B-05 aus der offenen Tabelle in die Behoben-Tabelle verschieben
- Neuen Hinweis: Plan 2 (Pipeline-Umbau) ist noch nicht geschrieben und braucht den `verify_epics`-Output aus Task 2, Step 2.4 als Eingangsvoraussetzung

- [ ] **Step 14.6: `docs/ARCHITECTURE.md` aktualisieren**

Die fünf neuen Tabellen (`sectors`, `ticker_sectors`, `ticker_status`,
`guardrail_rejects`, `sector_momentum`), die neuen Spalten
(`market_context.advance_decline_ratio`, `predictions.sector_etf_momentum`,
`predictions.sector_db_momentum` und die beiden gleichnamigen in
`guardrail_rejects`) sowie die neuen Module `src/market_context.py` und
`src/sector_momentum.py` im Datenmodell- bzw. Modul-Abschnitt ergänzen.

> **Nicht anfassen:** `README.md`, `docs/WORKFLOW.md`, `docs/SPECIFICATION.md`,
> `docs/superpowers/specs/2026-05-19-shares-future-mvp-design.md` — bekannt
> veraltet, werden erst nach Sprint 3 in einem eigenen Durchgang aktualisiert
> (Regel 14).

- [ ] **Step 14.7: Commit**

```bash
git add CLAUDE.md docs/superpowers/specs/PROJECT_STATUS.md docs/ARCHITECTURE.md
git commit -m "docs: record Sprint 3B / Plan 1 outcomes and decisions D1-D6

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Ausdrücklich NICHT in diesem Plan

Diese Punkte gehören zu Sprint 3B, werden aber erst in Plan 2 geplant — **nachdem**
das Fundament steht und der `verify_epics`-Output aus Task 2 / Step 2.4 vorliegt:

| Spec | Inhalt | Warum später |
|---|---|---|
| B.1 | `midday` + `position_check` entfernen, Cron-Umbau in `analyze.yml` | Destruktiv; erst sinnvoll, wenn `trade_proposals` existiert |
| B.2 | Run-Type `trade_proposals` (16:10) | Braucht die B.3-Checks, die wiederum die verifizierten ETF-Epics brauchen |
| B.3 | Die sieben Checks (Sektor-Momentum, Relative Stärke, VIX-Filter, Opening-Gap, Entry-Fenster, Korrelation) | Plan 1 **beschafft** die Daten (Markt-Kontext, beide Momentum-Signale), **wendet sie aber nicht an**. Insbesondere die D9-Guardrail-Logik — hartes Reject nur bei zwei übereinstimmenden Signalen, sonst weiche Warnung mit `enforced=0` — gehört vollständig in Plan 2 |
| B.4 | Phase 1c — offene Positionen als Pflicht-Kandidaten | Teil des Pipeline-Umbaus |
| B.5 | Phase 4 / 4a tauschen, `portfolio_check` ohne `web_search` | Teil des Pipeline-Umbaus |
| B.6 | `close` vereinfachen | Teil des Pipeline-Umbaus |
| B.9 | Weekly-Mail erweitern | Datenbasis (`guardrail_rejects`, `ticker_status`) entsteht hier, die Auswertung kommt in Plan 2 |
| B.11 | `hold_days_recommended` als Mail-Spalte | Reine Mail-Änderung, gehört zu den übrigen Mail-Arbeiten |
| D6/D9 | `config.SECTOR_GUARDRAIL_STRICT` + Auswertung der beiden Momentum-Signale | Das Flag wird dort eingeführt, wo es auch gelesen wird. Plan 2 füllt dabei auch `predictions.sector_etf_momentum` / `sector_db_momentum` und die gleichnamigen Spalten in `guardrail_rejects` — Plan 1 legt nur die Spalten an |

---

## Self-Review

**1. Spec-Abdeckung** (gegen PROJECT_STATUS.md, Sprint-3B-Abschnitte):

| Spec-Punkt | Task | Status |
|---|---|---|
| B.3 — Datenquelle Sektor-ETFs / VIX (offene Frage) | 1, 2 | ✅ als D1 entschieden, Tool implementiert (`7a11a00`); TICKER_MAP offen bis `verify_epics`-Lauf |
| B.10 — Sektor-Granularität | 2, 3 | ✅ als D7 entschieden: 21 Sub-Sektoren, Konstanten implementiert (`7a11a00`) |
| B.3 — Marktbreite A/D-Ratio (offene Frage) | 10, 11 | ✅ als D2 entschieden und umgesetzt |
| B.7 — `skipped_tickers` Schema-Annahme | 5 | ✅ bestätigt (`db.py:87`, reines Event-Log) und umgesetzt |
| B.7 — `ticker_status` Aggregat-Tabelle | 5, 6 | ✅ |
| B.7 — `inactive`-Reset (offene Frage) | 5, 7 | ✅ als D3 entschieden und umgesetzt |
| B.7 — Retention / unbegrenztes Wachstum | 9 | ✅ als D4 entschieden und umgesetzt |
| B.8 — Gap-Erkennung | 12 | ✅ inkl. dokumentierter Feiertags-Einschränkung |
| B.9 — Guardrail-Reject-Persistenz | 8 | ✅ Datenbasis gelegt (Auswertung → Plan 2) |
| B.3 — Sektor-Momentum hybrid | 9a | ✅ als D9 entschieden; Erhebung + Persistenz hier, Guardrail-Auswertung → Plan 2 |
| B.10 — `sectors` + `ticker_sectors` | 3 | ✅ |
| B.10 — organische Befüllung in Phase 1 | 4 | ✅ |
| B.10 — Finnhub↔GICS-Normalisierung (offene Frage) | 3 | ✅ als D5 entschieden und umgesetzt |
| B.10 — Guardrail-Verhalten bei NULL-Sektor (offene Frage) | — | ✅ als D6 entschieden, Umsetzung bewusst in Plan 2 (dokumentiert) |
| B.11 — B-05 | 13 | ✅ |
| B.11 — `hold_days_recommended` in Mail | — | ⏭ bewusst Plan 2 (dokumentiert) |
| B.1, B.2, B.4, B.5, B.6 | — | ⏭ bewusst Plan 2 (dokumentiert) |

**2. Placeholder-Scan:** Keine „TBD"/„TODO"/„implement later"-Stellen. Jeder Code-Schritt
enthält lauffähigen Code. Der einzige nicht vorab bestimmbare Wert ist der
TICKER_MAP-Inhalt in Task 2 / Step 2.5 — dort ist das kein Platzhalter, sondern ein
explizites manuelles Gate mit definiertem Verfahren, weil die Credentials nur in den
GitHub Secrets liegen.

**3. Typ-Konsistenz:**
- `db.resolve_sector_id(conn, raw) -> int | None` — konsistent in Task 3 (Definition), Task 4 (Aufruf), Task 8 (Test-Setup)
- `db.get_ticker_sector(conn, ticker) -> sqlite3.Row | None` mit Keys `sector_id`/`name`/`etf` — konsistent in Task 3 und Task 8
- `db.reactivate_ticker(conn, ticker) -> bool` — konsistent in Task 5, 6, 7
- `db.is_ticker_inactive(conn, ticker, today)` — Keyword `today` konsistent in Task 5 und 6
- `market_context.fetch_market_context(date, run_type, cost_tracker, price_provider)` — konsistent in Task 10 (Definition), Task 11 (Aufruf und Mocks), Task 13 (Mock)
- `_guardrail_filter(analyses, conn, date, run_type)` und `_to_prediction_row(..., conn)` — beide Signaturänderungen in Task 8 Step 8.6 an allen Aufrufstellen mitgezogen
- `historical_loader.main(argv=None)` — Signaturänderung in Task 7 eingeführt, Tests rufen sie mit Liste auf, `__main__`-Block bleibt gültig
