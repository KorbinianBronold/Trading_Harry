# Sprint 3B / Plan 2 — Pipeline-Umbau (Design)

**Erstellt:** 2026-07-30
**Status:** ✅ **umgesetzt und live verifiziert** — Plan `…/plans/2026-07-30-sprint3b-plan2-pipeline-umbau.md`, 20 von 20 Tasks, alles auf `main`. `pre_market`, `trade_proposals` (inkl. E3/E5), `close` und `final_close` sind gelaufen und geprüft. Ist-Stand und Befunde: PROJECT_STATUS **P2.2–P2.13**. ⏳ Nur `weekly` ist zugestellt, aber nie inhaltlich verifiziert
**Vorgänger:** Sprint 3B / Plan 1 (Fundament, abgeschlossen 2026-07-29), Sprint 3B-M (Resend, abgeschlossen 2026-07-30)

---

## 1. Ziel und Abgrenzung

Plan 1 war rein additiv: neue Tabellen, neue Helfer, ein zusätzlicher Phase-0b-Call.
Die Pipeline lief unverändert weiter. Plan 2 ist das Gegenteil — Run-Types
verschwinden, `analyze.yml` wird umgebaut, Module und Prompts werden gelöscht.

**Im Umfang:** B.1 (Cron-Umbau), B.2 (`trade_proposals`), B.3 (die sieben Checks
inkl. D9-Guardrail-Logik), B.4 (Phase 1c), B.5 (Phase 4/4a tauschen), B.6 (`close`
vereinfachen), B.9 (Weekly-Mail), B.11 (`hold_days_recommended` als Mail-Spalte).

**Nicht im Umfang** — Begründung jeweils in Abschnitt 9:
B.13 (Parallelisierung von Phase 3), der fehlende Deckel auf Phase 3, der
kombinierte `ranking_score` (3C), das Learning Modul (3D).

Plan 2 verdrahtet ausserdem drei Dinge, die Plan 1 gebaut, aber bewusst nicht
angeschlossen hat: `src/sector_momentum.py`, `predictions.sector_etf_momentum` /
`sector_db_momentum` und die gleichnamigen Spalten in `guardrail_rejects`.

---

## 2. Befunde am Code (Stand 2026-07-30)

Verifiziert vor Beginn der Planung. Punkte 4 bis 7 stehen bisher nirgends
dokumentiert.

1. **`src/sector_momentum.py` ist toter Code.** Einziger Importeur ist
   `tests/unit/test_sector_momentum.py`. `main.py` kennt das Modul nicht.
2. **Beide Momentum-Spaltenpaare sind unbefüllt.** `sector_etf_momentum` und
   `sector_db_momentum` existieren in `predictions` und `guardrail_rejects`
   inklusive Migration, es gibt aber keinen einzigen Schreibzugriff.
3. **`config.CLAUDE_PARALLEL_CALLS = 5` ist ungenutzt.** Die Konstante liegt seit
   Sprint 1 in `config.py`, wird aber von keinem Modul gelesen.
4. **`MAX_DEEP_ANALYSIS = 80` und `BATCH_SIZE_QUICK = 30` sind tote Konstanten.**
   Beide werden nirgends referenziert. `main.py` übergibt *alle* Ticker in **einem**
   Haiku-Call an `quick_filter_batch()` — das 30er-Batching existiert nicht —, und
   `analyze_assets()` analysiert **jeden** nicht-`exclude`ten Ticker. Es gibt keinen
   Deckel auf Phase 3 ausser `CostCapExceeded`.
   **Folge:** die F.1-Hochrechnung in PROJECT_STATUS („80 Slots → ~9,55 EUR") ist zu
   optimistisch. Bei 500 Tickern begrenzt nichts die Zahl der Tiefenanalysen.
5. **`run_close()` und `run_evaluate()` sind fast identisch.** Beide rufen
   `evaluate_open_predictions()`; `run_close()` macht zusätzlich `cleanup_old_data()`.
   Der `evaluate`-Cron um 16:00 Berlin läuft mitten in der US-Session und liefert
   keinen eigenen Beitrag. B.2 wirft mit ihm nichts weg.
6. **Die Phasenreihenfolge ist heute 4a vor 4.** `run_pipeline()` ruft
   `check_open_positions()` vor `rank_and_persist()`. Phase 4a arbeitet auf
   Phase-1-Snapshots und hat `WEB_SEARCH_TOOL` aktiv. B.5 trifft also zu.
7. **B.4s Annahme ist bestätigt.** `CapitalComProvider.get_open_positions()` schreibt
   `market["epic"]` in das Feld `ticker`. Für den Abgleich mit internen Tickern
   braucht es die Reverse-Map zu `TICKER_MAP`.
8. **`predictions` hat kein UNIQUE über (date, ticker, direction).** Der Evaluator
   greift jede Zeile mit `status='open' AND learnable=1 AND date < today`, ohne nach
   `run_type` zu unterscheiden. Das ist die Grundlage für Entscheidung 3.

---

## 3. Die fünf Entscheidungen dieser Session

### E1 — `trade_proposals` prüft billig, nicht tief

B.2/Schritt 2 sah vor, die Top 10 Long + Top 10 Short + 7 Commodities/Crypto erneut
durch die volle Phase 3 (Sonnet + `web_search`) zu schicken. Gemessen kostet eine
Tiefenanalyse **~0,12 EUR und ~54 s**; 27 Stück wären ~3,24 EUR und ~24 min rein
sequentiell — gegen die ~1,00 EUR aus der B.1-Schätzung und gegen
`MAX_COST_PER_RUN_EUR = 4,00`.

**Entschieden:** ein Claude-Call je Asset **ohne Websuche**. Input ist die persistierte
`pre_market`-Analyse aus der DB, der frische Phase-1-Snapshot und die Ergebnisse der
rechnerischen Checks. Output ist Urteil, revidierte `probability_pct` und ein
Entry-Fenster.

Breaking News zwischen 15:00 und 16:10 deckt der **eine** Policy-Monitor-Call mit
Websuche ab, der ohnehin je Run läuft — einmal statt 27-mal. Geschätzter Gesamtaufwand
des Runs: **~0,5–0,7 EUR und ~10 min**.

### E2 — B.13 wandert zurück nach 3F

Die Entscheidung vom 2026-07-29, die Parallelisierung von Phase 3 in Plan 2 zu ziehen,
beruhte darauf, dass `trade_proposals` mit ~530 Actions-Minuten/Monat die Einsparung
aus dem entfallenden `midday` wieder auffrisst. **E1 zieht dieser Begründung den Boden
weg:**

| | heute | 3B ohne Parallelisierung | 3B mit 5 parallel |
|---|---|---|---|
| `pre_market` | 550 | 550 | ~180 |
| `midday` | 550 | entfällt | entfällt |
| `trade_proposals` | — (`evaluate` 22) | **~220** *(B.13 rechnete mit ~530)* | ~200 |
| Rest | ~70 | ~22 | ~22 |
| **Summe/Monat** | **~1 190** | **~790** | **~400** |

~790 Minuten liegen deutlich unter den 2 000 des Free-Tarifs. Auch die Cron-Kollision
aus F.1 ist bei MVP-Grösse entschärft: ~25 min Laufzeit gegen 70 min Abstand.

**Entschieden:** B.13 gehört zu Sprint 3F, wo es gemeinsam mit dem Kostenproblem gelöst
wird. Plan 2 bleibt frei von Nebenläufigkeit.

### E3 — `pre_market`-Predictions werden abgelöst, nicht dupliziert

B.2/Schritt 6 wollte alle `trade_proposals`-Signale zusätzlich in `predictions`
schreiben. Wegen Befund 8 entstünden für AAPL long am selben Tag zwei offene Zeilen —
der Evaluator schlösse beide, Weekly-Gesamt-P&L und Tagesmail-Footer zählten doppelt,
und Phase 4a prüfte den Ticker zweimal (doppelte Claude-Kosten, Dubletten in der Mail).

Dazu kommt: um 15:00 Berlin ist es 9:00 ET. Die US-Börse öffnet erst 15:30, die
`pre_market`-Signale sind zum Zeitpunkt ihrer Mail also gar nicht handelbar. Der erste
reale Einstiegsmoment ist der 16:10-Run.

**Entschieden:** `trade_proposals` schreibt eine eigene vollständige Zeile, die passende
`pre_market`-Zeile bekommt `status='superseded'` und `superseded_by=<neue id>`. Beide
Zeilen behalten ihre acht Score-Dimensionen und ihre `probability_pct` — 3D kann die
Schätzungen vergleichen —, aber nur **eine** wird evaluiert.

`evaluate_open_predictions()` und `load_open_predictions_within_max_age_days()` filtern
schon heute auf `status='open'` und brauchen **keine** Änderung. Kein Aggregat kann
doppelt zählen.

### E4 — Erheben in beiden Runs, hart durchsetzen nur um 16:10

B.3 verortet die sieben Checks im `trade_proposals`-Run. Technisch sind aber nur zwei
davon an diesen Zeitpunkt gebunden:

| Check | Quelle | Braucht 16:10? |
|---|---|---|
| Sektor-Momentum (D9) | `src/sector_momentum.py` (existiert) | nein |
| VIX-Level | `market_context` (Phase 0b, existiert) | nein |
| Marktbreite (A/D-Ratio) | `market_context` (Phase 0b, existiert) | nein |
| Relative Stärke | neu: SQL über `price_history` × `ticker_sectors` | nein |
| Korrelations-/Klumpen-Check | neu: Abzählen über `ticker_sectors` | nein |
| Opening-Gap | neu: `pre_market`-Kurs vs. aktueller Kurs | **ja** |
| Entry-Fenster | Ausgabefeld des Claude-Calls | nein |

**Entschieden:** `pre_market` erhebt **alle** Checks, schreibt sie in `predictions` und
`guardrail_rejects` (`enforced=0`) und weist sie in der Mail als Warnung aus — blockiert
aber nichts. `trade_proposals` erhebt dieselben Checks und **setzt sie hart durch**.

Begründung: um 15:00 ist die Börse zu, die Morgenmail ist ein Research-Briefing und
keine Handelsentscheidung. 3D bekommt trotzdem aus beiden Runs vollständige Messwerte —
einschliesslich der Fälle, in denen ein weich gewarntes Signal am Ende doch funktioniert
hätte.

### E5 — Gedrehte Signale werden gemeldet, nicht gehandelt

**Entschieden:** kippt die 16:10-Prüfung ein `pre_market`-Long in ein Short-Urteil, wird
das Urteil protokolliert und in der Mail deutlich ausgewiesen — es entsteht **keine**
neue Prediction in Gegenrichtung.

Begründung: das Gegensignal ist nie durch Phase 3 gelaufen. Es hätte keine Belege, keine
acht Score-Dimensionen und kein aus einer Analyse abgeleitetes TP/SL. Eine Position
darauf zu eröffnen unterliefe die Guardrail-Grundregel „min. 2 Belege je
Score-Dimension".

Die ursprüngliche Long-Zeile bleibt offen und wird regulär ausgewertet — sie beantwortet
damit, ob die Drehung richtig lag.

---

## 4. Drei Festlegungen ohne eigene Entscheidungsfrage

1. **„Relative Stärke → Score-Input" hat kein gültiges Ziel.** `total_score` ist eine
   eingefrorene Architektur-Invariante, `ranking_score` gehört zu 3C. Die relative
   Stärke wird deshalb **Input für den Re-Validierungs-Prompt und eine Spalte in der
   Mail** — kein neuer Score, keine Änderung an `DIMENSION_WEIGHTS`.
2. **`MAX_DEEP_ANALYSIS` und `BATCH_SIZE_QUICK` bleiben tot.** Der Fix gehört zu C.4
   (technischer Pre-Filter). Plan 2 dokumentiert den Befund und korrigiert die
   F.1-Rechnung in PROJECT_STATUS, baut ihn aber nicht.
3. **Neue Prompt-Datei `prompts/trade_proposals_v1.txt`.** Ein eigener Prompt, kein
   `deep_analysis_v2.txt`. `deep_analysis_v1.txt` bleibt unangetastet, Regel 10 ist
   erfüllt, ein Eintrag in `prompt_versions` kommt dazu.

---

## 5. Architektur und Modulschnitt

### 5.1 Zwei neue Module

**`src/signal_checks.py`** — die fünf rechnerischen Checks als reine Funktionen:
relative Stärke, Klumpenrisiko, Opening-Gap, VIX-Regel und die D9-Auswertung. Kein
Claude, kein HTTP, keine Netzwerkabhängigkeit: `dict`/SQL rein, Urteil raus.

Die Durchsetzung steuert ein Parameter `enforce: bool`, den der Aufrufer setzt —
`run_pipeline()` übergibt `False`, `run_trade_proposals()` übergibt `True`. Damit steht
E4 an genau **einer** Stelle im Code statt verstreut in fünf Checks.

**`src/revalidation.py`** — der eine Claude-Call ohne Websuche, mit einer einzigen
öffentlichen Funktion. Input: persistierte `pre_market`-Analyse, frischer
Phase-1-Snapshot, Check-Ergebnisse. Output: Urteil, revidierte `probability_pct`,
Entry-Fenster.

Die Trennung ist Absicht: alles Prüfbare ist ohne Mocking testbar, der teure und
nichtdeterministische Teil liegt isoliert.

**Wo die sieben B.3-Checks landen.** Fünf werden in `signal_checks.py` *ausgewertet* —
relative Stärke und Klumpenrisiko rechnet das Modul selbst, Opening-Gap bekommt den
`pre_market`-Kurs übergeben, VIX-Regel und D9 werten Daten aus, die `market_context`
(Phase 0b) beziehungsweise `sector_momentum` (Phase 1d) bereits erhoben haben. Die
**Marktbreite** wird nicht ausgewertet, sondern nur aus `market_context` in die Mail
durchgereicht — B.3 weist ihr ausdrücklich nur „Kontext / Warnung" zu. Das
**Entry-Fenster** ist kein Check, sondern ein Ausgabefeld von `revalidation.py`.

### 5.2 Geänderte Dateien

| Datei | Was |
|---|---|
| `main.py` | `RUN_TYPES`, Dispatch, neues `run_trade_proposals()`; Phasenreihenfolge in `run_pipeline()`; `run_position_check()` und `run_evaluate()` entfernt |
| `src/db.py` | `predictions.superseded_by` und `predictions.revision_verdict` + Migration, `supersede_prediction()`, Weekly-Aggregate |
| `src/ranking.py` | nimmt Check-Ergebnisse entgegen, schreibt beide Momentum-Spalten in die Prediction-Zeile |
| `src/portfolio_check.py` | Input = fertige Phase-3-Analysen statt Phase-1-Snapshots, `WEB_SEARCH_TOOL` entfernt |
| `src/email_sender.py` | `render_trade_proposals_html()` + `_section_signal_changes()`; Weekly um vier Blöcke; `hold_days_recommended`-Spalte; beide `position_check`-Funktionen entfernt |
| `src/providers/capital_provider.py` | Reverse-Map zu `TICKER_MAP` für Phase 1c |
| `config.py` | `SECTOR_GUARDRAIL_STRICT = False`, `VIX_HIGH_CONFIDENCE_ONLY = 25.0`, `VIX_NO_NEW_LONGS = 35.0` |
| `.github/workflows/analyze.yml` | Crons, `workflow_dispatch`-Optionen, `case`-Matching |

### 5.3 Gelöscht

`prompts/position_check_v1.txt`, `run_position_check()`, `run_evaluate()`,
`render_position_check_html()`, `send_position_check_email()` und die zugehörigen Tests.

`main.py` wächst dabei nicht nennenswert: `run_trade_proposals()` bringt ~70 Zeilen, die
beiden entfernten Funktionen nehmen ~60 mit. Der Renderer für die 16:10-Mail nutzt die
vorhandenen `_section_*`-Bausteine — es entsteht kein zweiter Mail-Renderer von Grund
auf.

**Erhalten bleibt** `CapitalComProvider.get_open_positions()` — Phase 1c braucht es.

---

## 6. Datenfluss

### 6.1 `pre_market` (15:00 Berlin) — neue Phasenfolge

| Phase | | Änderung |
|---|---|---|
| 0 | Trend-Analyse | — |
| 0b | Markt-Kontext (VIX, A/D, Regime) | — |
| 1 / 1b | Datensammlung SP500 / Commodities+Crypto | — |
| **1c** | **Offene Capital.com-Positionen → Pflicht-Kandidaten** | **neu** (B.4) |
| **1d** | **Sektor-Momentum erheben** | **neu** |
| 2 | Quick-Filter | Pflicht-Kandidaten aus 1c übersteuern `exclude` |
| 3 | Policy-Monitor + Tiefenanalyse | — |
| 3b | Commodities + Crypto | — |
| **4** | **Ranking** | war 4a — `signal_checks(enforce=False)` |
| **4a** | **Portfolio-Check** | war 4 — Input jetzt Phase-3-Analysen, ohne Websuche |
| — | Tagesmail | `hold_days_recommended`-Spalte, weiche Warnungen |

**Warum 1d nach Phase 1:** `db_momentum` mittelt die heutigen Bars aus `price_history`.
Vor Phase 1 sind sie noch nicht geschrieben.

**Phase 1c im Detail:** `get_open_positions()` liefert Epics; die Reverse-Map ist
`{v: k for k, v in TICKER_MAP.items()}`. Epics ohne Gegenstück in unserer Ticker-Liste
(manuell eröffnete Fremdpositionen) werden geloggt und übersprungen — für sie gibt es
keine Indikator-Daten. Ein Test sichert ab, dass `TICKER_MAP` injektiv bleibt: zwei
Ticker auf dasselbe Epic würden die Rückabbildung still falsch machen.

### 6.2 `trade_proposals` (16:10 Berlin)

**Kein Phase 0.** Die Megatrend-Analyse ändert sich nicht in 70 Minuten; der Run lädt
`trend_analyses` von heute aus der DB. Der Policy-Monitor läuft dagegen **mit**
Websuche — genau er fängt ab, wofür in E1 die 27 Einzelrecherchen gestrichen wurden.

1. Phase 0b — Markt-Kontext frisch (nach dem Opening)
2. Kurse **aller** Ticker (SP500 + Commodities/Crypto) → `price_history` *(B.2/1)*
3. Phase 1c — offene Positionen (für Phase 4a)
4. Phase 1d — Sektor-Momentum mit `run_type='trade_proposals'`
5. Policy-Monitor (1×, mit Websuche)
6. **Re-Validierung** der heutigen offenen `pre_market`-Predictions, ein billiger Call
   je Ticker (`current_phase='revalidation'` — bewusst keine neue Phasennummer, die
   bestehenden Namen sind sprechend und werden von der B-05-Abbruchmeldung gelesen)
7. `signal_checks(enforce=True)`
8. Persistieren nach Abschnitt 6.3
9. Phase 4a — Portfolio-Check
10. 16:10-Mail

### 6.3 Der `superseded`-Mechanismus

Zugeordnet wird über `(date, ticker, direction, run_type='pre_market', status='open')`.

Zwei neue Spalten in `predictions`, beide nullable, beide über `_apply_migrations()` mit
`PRAGMA table_info()`-Guard (Regel 5):

```sql
ALTER TABLE predictions ADD COLUMN superseded_by INTEGER;
ALTER TABLE predictions ADD COLUMN revision_verdict TEXT;
```

| Urteil | Neue Zeile? | `pre_market`-Zeile danach |
|---|---|---|
| `bestaetigt` / `geschwaecht` / `unveraendert` | ja — 16:10-Kurs, TP/SL, revidierte `probability_pct` | `status='superseded'`, `superseded_by=<neue id>`, `revision_verdict` gesetzt |
| `gedreht` | **nein** (E5) | bleibt `status='open'`, `revision_verdict='gedreht'` |
| `verworfen` (harter Check gerissen) | **nein** | bleibt `status='open'`, `revision_verdict='verworfen'`, dazu `guardrail_rejects`-Zeile mit `enforced=1` |
| Re-Validierung schlug fehl | **nein** | bleibt `status='open'`, `revision_verdict` bleibt `NULL` |

**`revision_verdict` sitzt bewusst auf der `pre_market`-Zeile**, nicht auf der neuen:
nur so ist es auch in den drei Fällen vorhanden, in denen gar keine neue Zeile entsteht.
B.9s Veränderungs-Statistik wird damit ein `GROUP BY revision_verdict`. Weil gedrehte und
verworfene Signale offen bleiben und regulär evaluiert werden, beantwortet dieselbe
Abfrage direkt, ob die Ablehnung richtig lag.

### 6.4 `close` (22:30 Berlin) — B.6

1. **Schlusskurse aller Ticker** (SP500 + Commodities/Crypto) von Capital.com holen und
   in `price_history` schreiben *(neu)*
2. `evaluate_open_predictions()` **bleibt** — sonst schriebe zwischen 3B und 3D niemand
   mehr `outcomes`-Zeilen, und das Learning Modul hätte keine Trainingsdaten aus dieser
   Zeit. Wird erst entfernt, wenn 3D die Auswertung übernimmt.
3. `cleanup_old_data()` mit den Retention-Regeln aus Plan 1 (30/180/90) — bereits
   umgesetzt, keine Änderung.

### 6.5 Ziel-Cron-Struktur (B.1)

| Run-Type | Zeit (Berlin, CEST) | Änderung |
|---|---|---|
| `pre_market` | 15:00 Mo–Fr | unverändert |
| `trade_proposals` | 16:10 Mo–Fr | **neu**, ersetzt `evaluate` |
| `close` | 22:30 Mo–Fr | vereinfacht (6.4) |
| `weekly` | So 20:00 | Inhalt erweitert (7.3) |
| ~~`midday`~~ | — | entfernt |
| ~~`evaluate`~~ | — | entfernt |
| ~~`position_check`~~ | — | entfernt |

`analyze.yml` und `main.py:RUN_TYPES` müssen **zusammen** wechseln: ruft der Workflow
einen Run-Type auf, den `argparse` nicht mehr kennt, bricht der Job ab. Daraus folgt die
Schnitt-Struktur in Abschnitt 10.

**DST-Hinweis unverändert:** Cron ist UTC-fix, im Winter (CET) läuft alles 1 h früher.

---

## 7. Fehlerbehandlung, Mails, Tests

### 7.1 Fehlerbehandlung

`run_trade_proposals()` führt dieselbe `current_phase`-Variable wie `run_pipeline()`
(B-05-Muster), bekommt einen eigenen `CostTracker` und dieselbe B-10-Trennung: der
Mailversand wird gefangen und wirft `MailDeliveryError`, nachdem alles persistiert ist.

| Fall | Verhalten |
|---|---|
| Re-Validierung scheitert für **einen** Ticker | Die `pre_market`-Zeile wird **nicht** superseded und bleibt offen; die Mail weist den Ticker als „nicht geprüft" aus. Nie auf Basis eines Fehlers ablösen. |
| **Policy-Monitor** scheitert im 16:10-Run | Nicht fatal: Lauf geht mit leerem Policy-Kontext weiter, Hinweis in der Mail. Bewusst anders als in `pre_market` — seit E1 ist er die einzige Websuche des Runs, aber eine preisbasierte Re-Validierung ist besser als gar keine. |
| **Markt-Kontext** scheitert | Wie bisher: Warnung, leerer Kontext, Lauf läuft weiter. |
| **Kosten-Deckel** | Wie bisher: Teilergebnis plus Warnbalken in der Mail. |

### 7.2 Tagesmail und 16:10-Mail

Die 16:10-Mail nutzt die vorhandenen `_section_*`-Bausteine:

1. **Portfolio** — bleibt erste Sektion (dokumentierte Invariante)
2. **`_section_signal_changes()`** *(neu)* — je Ticker: Urteil, `probability_pct`
   vorher → nachher, Entry-Fenster, gefeuerte Checks
3. Commodities + Crypto
4. Markt-Warnungen (VIX, Marktbreite, Klumpenrisiko)
5. Footer (Kosten)

Die Tagesmail bekommt `hold_days_recommended` als eigene Spalte in den
Top-10-Long/Short-Tabellen (B.11) und weist die weichen Warnungen aus E4 sichtbar aus.

### 7.3 Weekly-Mail (B.9)

**Block 1 muss gegenüber B.9 neu formuliert werden.** „Trefferquote getrennt nach
`run_type`" geht durch E3 nicht mehr — jede Trade-Idee hat genau ein Outcome. Was
stattdessen geht, ist schärfer:

| Gruppe | Abfrage |
|---|---|
| um 16:10 **bestätigt** | Outcomes mit `run_type='trade_proposals'` |
| um 16:10 **abgelehnt** | Outcomes mit `run_type='pre_market'` und `revision_verdict IN ('gedreht','verworfen')` |
| **nie geprüft** | `run_type='pre_market'`, `revision_verdict IS NULL` |

**Achtung bei Gruppe 3:** dort liegen auch alle `pre_market`-Predictions, die vor dem
ersten `trade_proposals`-Lauf entstanden sind — für sie konnte es kein Urteil geben. Die
Gruppe ist erst ab dem ersten vollständigen 16:10-Lauf aussagekräftig; die Weekly-Query
grenzt deshalb auf `date >= <erster trade_proposals-Lauf>` ein.

Liegt die Trefferquote der abgelehnten Signale unter der der bestätigten, hat der
16:10-Lauf seine Kosten verdient — direkt messbar, statt über zwei parallele
Simulationen derselben Idee.

**Block 2 — Signal-Veränderungs-Statistik:** `GROUP BY revision_verdict`, dazu Ø P&L je
Gruppe.

**Block 3 — Guardrail-Reject-Statistik:** `GROUP BY rule, enforced` über
`guardrail_rejects`. Die Dimension `enforced` trennt jetzt sinnvoll: `0` sind die weichen
Warnungen aus `pre_market`, `1` die harten Ablehnungen aus `trade_proposals`.

**Block 4 — Skipped-Ticker-Übersicht:** aus `skipped_tickers` (Event-Log) und
`ticker_status` (kumulativer Zähler, Inaktiv-Flag, `retry_after`).

**Zusätzlich — Sub-Sektor-Mapping-Abdeckung.** B.10 nennt sie als Voraussetzung dafür,
`SECTOR_GUARDRAIL_STRICT` irgendwann auf `True` zu stellen.

### 7.4 Tests

Die Tests zu `midday`, `position_check` und `evaluate` werden **gelöscht**. Das ist kein
Abschwächen im Sinne von Regel 8, sondern das Mitziehen eines entfallenen
Testgegenstands — hier festgehalten, damit es später nicht wie ein Regelverstoss
aussieht.

Neu:

- `signal_checks` rein funktional, inklusive je eines Falls pro D9-Lage aus B.3.1
  (beide Signale gleich / widersprüchlich / nur eines / keines)
- **derselbe Check blockiert mit `enforce=True` und blockiert nicht mit
  `enforce=False`** — der Test, der E4 festnagelt
- **jeder** Ausgang des `superseded`-Mechanismus aus 6.3: die drei ablösenden Urteile,
  `gedreht`, `verworfen` und der Fehlerfall
- **kein Aggregat zählt doppelt:** zwei Zeilen für denselben Ticker, eine superseded →
  der Evaluator schliesst genau eine
- Phase-1c-Reverse-Map inklusive Injektivität von `TICKER_MAP`
- Reihenfolge-Test: Ranking läuft vor Portfolio-Check
- B-05-Test um die `trade_proposals`-Phasen erweitern
- `revalidation` mit gemocktem Claude-Call (Urteil, Parse-Fehler, Teilausfall)

**Verifikation wie bei Plan 1:** echter `trade_proposals`-Lauf gegen Capital.com,
Docker-Smoke-Test, Migration gegen eine bestehende `tracking.db`. Coverage-Ziel bleibt
80 % (Stand nach Plan 1: 92,42 % bei 380 Tests).

---

## 8. Neue Konfigurationskonstanten

```python
SECTOR_GUARDRAIL_STRICT = False   # D9: hart rejecten erst, wenn die Mapping-
                                  # Abdeckung stabil hoch ist (s. B.10)
VIX_HIGH_CONFIDENCE_ONLY = 25.0   # darüber nur noch confidence='high'
VIX_NO_NEW_LONGS         = 35.0   # darüber keine neuen Long-Signale
```

Zur Erinnerung aus B.3.1: hartes Rejecten über das Sektor-Momentum bleibt auch bei
`SECTOR_GUARDRAIL_STRICT = True` auf den Fall beschränkt, dass **beide** Signale
vorliegen **und** in dieselbe Richtung zeigen. Verglichen wird die **Richtung**, nie der
Betrag — die Live-Messung vom 2026-07-28 zeigt Abweichungen um Faktor ~2,5 zwischen ETF-
und DB-Signal bei identischem Vorzeichen.

---

## 9. Was Plan 2 bewusst nicht tut

| Ausgelassen | Warum | Gehört zu |
|---|---|---|
| Parallelisierung von Phase 3 | E2 — die Actions-Minuten-Begründung trägt nach E1 nicht mehr; Nebenläufigkeit gehört nicht in einen destruktiven Umbau | 3F |
| Deckel auf die Zahl der Tiefenanalysen | Befund 4 — der Fix ist der technische Pre-Filter, nicht eine Notbremse in `analyze_assets()` | 3C / C.4 |
| 30er-Batching im Quick-Filter | dito; bei 20 MVP-Tickern unkritisch | 3C / C.4 |
| Kombinierter `ranking_score` | eigene Spalte, eigene Gewichtung, eigener A/B-Vergleich | 3C / C.2 |
| `atr_pct`, `rsi_at_entry`, `volume_ratio` in `predictions` | derzeit hart `None` in `_to_prediction_row()` | 3C / C.1 |
| Übernahme der TP/SL-Auswertung aus `close` | siehe 6.4 Punkt 2 | 3D |

---

## 10. Schnitt-Struktur

**Ansatz: Abriss zuerst.** Nach jedem Schnitt ist der Stand grün, in sich konsistent und
pushbar. Der destruktive Teil ist mechanisch und liegt vorn; alles danach ist additiv.

| # | Inhalt | Spec |
|---|---|---|
| 1 | Abriss von `midday`, `position_check`, `evaluate` inkl. `run_position_check()`, `run_evaluate()`, `position_check_v1.txt`, beider Mail-Funktionen und Tests; `trade_proposals` als Gerüst — zieht die Kurse aller Ticker und schreibt sie in `price_history`, verschickt aber noch **keine** Mail (wie `close`); `analyze.yml` komplett | B.1, B.2/1 |
| 2 | Phase 1c (offene Positionen als Pflicht-Kandidaten via Reverse-`TICKER_MAP`); Phase 4 vor 4a; `portfolio_check` auf Phase-3-Analysen umstellen und `web_search` entfernen | B.4, B.5 |
| 3 | `sector_momentum.py` verdrahten; relative Stärke + Klumpen-Check; beide Momentum-Spalten in `predictions` **und** `guardrail_rejects` befüllen; `SECTOR_GUARDRAIL_STRICT`. Alles weich, `enforced=0`, in **beiden** Runs | B.3 (weich) |
| 4 | `trade_proposals` inhaltlich: Re-Validierung ohne Websuche, `superseded`/`superseded_by`/`revision_verdict`, Vorher-Nachher-Mail | B.2/2–6 |
| 5 | Harte Durchsetzung **nur** im 16:10-Run: VIX-Filter, D9-Guardrail bei zwei übereinstimmenden Signalen, Opening-Gap | B.3 (hart) |
| 6 | `close` vereinfachen; Weekly-Mail um vier Blöcke erweitern; `hold_days_recommended` als Mail-Spalte; Doku nachziehen | B.6, B.9, B.11 |

**Arbeitsweise:** Commit nach jedem Task, niemals pushen.

---

## 11. Doku-Nachzug (Schnitt 6)

- **PROJECT_STATUS.md:** korrigierte F.1-Rechnung (die 80 Slots existieren nicht,
  Befund 4); B.13 wandert nach 3F (E2); B.2, B.3 und B.9 werden auf E1–E5
  umgeschrieben; Abschnitt B.12 auf „Plan 2 umgesetzt" gesetzt
- **CLAUDE.md:** neue Run-Type-Liste, Hinweis auf `signal_checks`/`revalidation`
- **docs/ARCHITECTURE.md:** die beiden neuen Module, geänderte Phasenreihenfolge
- **Regel 14 unverändert:** `README.md`, `docs/WORKFLOW.md`, `docs/SPECIFICATION.md` und
  `mvp-design.md` bleiben dem finalen Durchgang nach Sprint 3 vorbehalten
