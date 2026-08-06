# Preismodell: drei Entscheidungs-Snapshots + finale Tages-OHLC (Design)

**Erstellt:** 2026-08-06
**Status:** Spezifikation — Implementierung folgt über eine eigene Plan-Datei unter `docs/superpowers/plans/`
**Vorgänger:** Sprint 3B / Plan 2 (abgeschlossen), Task-20-Review (2026-08-05/06, s. PROJECT_STATUS P2.8)

---

## 1. Ziel

Das Preismodell trennt künftig zwei Dinge, die heute dieselbe Quelle haben und
deshalb ständig miteinander verwechselt werden:

| | Was | Quelle |
|---|---|---|
| **Indikator-Historie** | RSI, ATR, SMA, MACD — braucht abgeschlossene Tage | `price_history`, **nur finale Bars** |
| **Entscheidungs-Snapshot** | Der Kurs, zu dem eine Aussage getroffen wurde | `predictions`, drei neue Spalten |

Genau diese Vermischung war der Frozen-Bar-Bug (P2.8): der 15:00-Lauf schrieb eine
Pre-Market-Quote als „Tagesbar" fest, und alles Spätere las sie als Tatsache.

**Im Umfang:** neue Provider-Methode mit `resolution`-Parameter, der 400er-Fix, drei
neue `predictions`-Spalten, der neue Run-Type `final_close`, Umzug des Evaluators,
Rückbau von `_ensure_today_bar()`, Concurrency-Lock, Doku-Nachzug.

**Nicht im Umfang:** Gap-Analyse zwischen Final-Close und nächstem Open,
Fair-Value-Gap-Erkennung im Lernmodul. Beides geht in PROJECT_STATUS Abschnitt 2b.

---

## 2. Verifizierte Befunde

Alles gegen die echte Capital.com-API bzw. `docs/CapitalcomPublicAPI.pdf` geprüft,
nichts aus dem Gedächtnis. Datum der Messungen: 2026-08-05/06.

### 2.1 Was die API kann (PDF S. 73, `GET /api/v1/prices/{epic}`)

- **Resolutions:** `MINUTE`, `MINUTE_5`, `MINUTE_15`, `MINUTE_30`, `HOUR`, `HOUR_4`,
  `DAY`, `WEEK`. Der Code kennt bisher nur `DAY`.
- `max`: Default 10, **Maximum 1000**.
- `from`/`to`: Format `YYYY-MM-DDTHH:MM:SS`, **Filterung über `snapshotTimeUTC`**.

Ein einzelner `DAY`-Abruf liefert Open, High, Low, Close und Volumen gemeinsam —
für die finale Tagesbar sind **keine vier Einzelabfragen** nötig.

### 2.2 Der 400er ist ein Zeitstempel-, kein Datumsproblem

Gemessen am 2026-08-06, 10:47 UTC:

| `to` | Ergebnis |
|---|---|
| heute 00:00 UTC (Vergangenheit) | HTTP 200, 4 Bars |
| morgen 00:00 UTC (Zukunft) | **HTTP 400** |
| jetzt, exakt | HTTP 200, 4 Bars |
| jetzt + 5 Minuten | **HTTP 400** |

**`to` darf in UTC nicht in der Zukunft liegen — fünf Minuten genügen für den 400er.**
Das steht **nicht** im PDF; es ist undokumentiertes Verhalten.

Ursache im Code: `main.py:767` leitet das Laufdatum aus
`datetime.now(BERLIN).date()` ab, während die API auf `snapshotTimeUTC` filtert.
Zwischen 00:00 und 02:00 Berlin (CEST) läuft das Berliner Datum dem UTC-Datum voraus.

### 2.3 Warum die Tagesbar erst um 00:00 UTC final ist

`instrument.openingHours` für AAPL: **Mo–Do `08:00 - 00:00`, Fr `08:00 - 21:00`,
`zone: UTC`**. Das sind 04:00–20:00 ET, also volle erweiterte Handelszeiten.

Dazu die Messung: die Bar vom 2026-08-05 bewegte sich um 22:47 UTC noch
(AAPL `C` 312,3 → 312,9, Volumen 63028 → 63363; ebenso BTC, ETH, GOLD), während die
Bar vom 2026-08-04 bei allen vier **exakt stillstand**. Der `close`-Lauf um 20:30 UTC
liegt damit **3 h 30 min** vor der Finalisierung.

### 2.4 Die Tagesbar öffnet vorbörslich

AAPL, 2026-08-05:

| Quelle | Open |
|---|---|
| `DAY`-Bar | 310,54 |
| `MINUTE`-Bar 13:30 UTC (= 09:30 ET, regulärer Open) | **309,09** |

**0,47 % Unterschied.** Der „Open" der Tagesbar ist nicht der Eröffnungskurs. Ein
separater minutengenauer Abruf ist deshalb nicht nur genauer, sondern notwendig.

### 2.5 `marketStatus` taugt nicht zur Vorbörslich-Erkennung

Um 08:37 ET — mitten in der Vorbörse — meldet `/markets/{epic}` für AAPL
`marketStatus: TRADEABLE`. Das Feld beschreibt die Handelbarkeit des CFDs
einschliesslich erweiterter Zeiten, nicht die Sitzungsphase.

### 2.6 Drei tote Bausteine, die genau hier gebraucht werden

| Baustein | Zustand |
|---|---|
| `db.upsert_price_history()` | war bis 2026-08-06 ohne Aufrufer |
| `CapitalComProvider.get_premarket_price()` | **hat bis heute keinen Aufrufer** — liefert Live-Bid aus `/markets/{epic}` |
| `price_history.premarket_price` (Spalte, `db.py:283`) | per Migration angelegt, **nie geschrieben, nie gelesen** |

---

## 3. Entscheidungen

| # | Entscheidung | Begründung |
|---|---|---|
| **E1** | Der Evaluator wandert in `final_close` und liest `price_history` | `_walk_forward_hit` prüft TP **und** SL gegen `bar["High"]`/`bar["Low"]` (`evaluator.py:35-39`). Beide können sich im Tagesverlauf nur ausweiten — eine provisorische Bar meldet systematisch **zu wenige** Treffer und schiebt Outcomes Richtung `timeout`. |
| **E2** | `final_close` ist **alleiniger Schreiber** von `price_history`, inklusive Sub-Sektor-ETFs | Nur mit einem einzigen Schreiber, der ausschliesslich finale Bars schreibt, kann der Frozen-Bar-Bug strukturell nicht wiederkehren. |
| **E3** | Der Live-Entscheidungskurs kommt aus `/markets/{epic}` | Ein Call, liefert bid/offer/high/low/`updateTime`. `get_premarket_price()` existiert bereits. |
| **E4** | „Vorbörslich" wird aus der Uhr abgeleitet (`America/New_York`, 09:30–16:00) | `marketStatus` ist dafür nachweislich unbrauchbar (2.5). Die Uhr ist deterministisch und ohne Netz testbar. |
| **E5** | Plandateien unter `docs/superpowers/plans/` bleiben unangetastet | Sie sind historische Protokolle des jeweiligen Stands. Lebende Dokumente sind `PROJECT_STATUS.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`. |
| **E6** | Commodities/Crypto bekommen `price_premarket` und `price_1610`, aber `price_open = NULL` | 24/7-Instrumente haben keinen Eröffnungskurs. NULL ist ehrlicher als ein erfundener Wert. |
| **E7** | `evaluated_date` bezeichnet den **Handelstag, dessen Bar die Position geschlossen hat** — nicht das Laufdatum | Ohne das zeigt `_aggregate_yesterday_outcomes` (`main.py:110`, `WHERE o.evaluated_date = today − 1`) stumm Nullen, sobald der Job auf D+1 läuft. |

---

## 4. Architektur und Datenfluss

### 4.1 Die drei Entscheidungs-Snapshots

| Spalte | Erhoben von | Quelle | Bedeutung |
|---|---|---|---|
| `price_premarket` | `pre_market` (13:00 UTC) | `/markets/{epic}` live-Bid | Kurs zum Zeitpunkt des Research-Briefings. **Regulär vorbörslich** — die US-Börse öffnet erst 13:30/14:30 UTC. |
| `price_open` | `trade_proposals` (14:10/15:10 UTC) | `MINUTE`-Bar des regulären Opens, historisch | Der tatsächliche Eröffnungskurs. Liegt zum Abrufzeitpunkt bereits in der Vergangenheit. |
| `price_1610` | `trade_proposals` | `/markets/{epic}` live-Bid | Kurs zum Zeitpunkt der finalen Prognose. |

`is_premarket` (INTEGER, 0/1) markiert, ob `price_premarket` ausserhalb der regulären
Sitzung erhoben wurde. **Der Re-Validierungs-Prompt bekommt die Markierung mitgeliefert**
und muss den Wert entsprechend behandeln — ein vorbörslicher Kurs ist dünn gehandelt und
nicht gleichwertig mit einem Sitzungskurs.

`entry_price` bleibt **unverändert** in Bedeutung und Befüllung. Die drei neuen Spalten
stehen daneben, damit Sprint 3D vergleichen kann, welcher Zeitpunkt am besten prognostiziert.

### 4.2 Läufe

```
pre_market (13:00 UTC)
  ├─ price_premarket  ← /markets/{epic}
  ├─ is_premarket     ← Uhr (America/New_York)
  └─ Indikatoren      ← price_history (bis D-1, final)

trade_proposals (14:10 UTC EDT / 15:10 UTC EST)
  ├─ price_open       ← MINUTE-Bar 13:30/14:30 UTC (historisch)
  ├─ price_1610       ← /markets/{epic}
  └─ alle drei Preise + News → finale 16:10-Prognose

final_close (00:15 UTC, täglich)          ← NEU
  ├─ DAY-OHLC je Ticker + ETF → upsert_price_history()
  └─ evaluate_open_predictions()          ← liest price_history

close (20:30 UTC)
  └─ nur noch cleanup_old_data()
```

### 4.3 Das Auswertungsfenster — ab dem Signal, nicht ab dem Tag

**Der Defekt.** Heute ruft der Evaluator `get_ohlc_after(start_date=pred["date"], …)`
auf, und `_walk_forward_hit` beginnt bei `bars.iloc[0]` — beim Bar des **Prognosetags
selbst**. Dessen Spanne läuft ab 08:00 UTC (`openingHours`, s. 2.3), das Signal entsteht
aber erst um 09:00 ET (`pre_market`) beziehungsweise 10:10 ET (`trade_proposals`).
TP/SL-Treffer aus den Stunden davor sind Artefakte: die Position gab es da noch nicht.

**Was NICHT die Lösung ist.** Den ganzen Tag D auszuschliessen wäre kein beseitigtes
Artefakt, sondern ein gespiegeltes. Sprint 3D verfolgt die Trefferquote getrennt nach
Intraday (`hold_day = 1`) und Extended (`hold_day 2–5`); ohne Tag D könnte eine
Intraday-These **nie** am selben Tag als getroffen erfasst werden. Der Fehler ist nicht
„Tag D zählt", sondern „der falsche Teil von Tag D zählt".

**Die Festlegung.** Das Fenster beginnt am **Signal-Zeitpunkt** und läuft bis zum Ende
des Handelstags D, danach folgen die Tagesbars D+1 … D+MAX_HOLD_DAYS.

Umsetzung über dieselbe `resolution`-Fähigkeit, die für `price_open` ohnehin entsteht:

1. `MINUTE`-Bars von `signal_time` bis Tagesende abrufen. Das Fenster 14:10–00:00 UTC
   sind ~590 Bars und passt mit `max = 1000` in **einen** Call.
2. Diese Bars zu **einer synthetischen Tagesbar für D** verdichten:
   `High = max(highs)`, `Low = min(lows)`, `Close = letzter Close`.
3. Sie wird Element 1 der Sequenz, danach die finalen Tagesbars aus `price_history`.

**`_walk_forward_hit` bleibt dadurch unverändert.** Das ist der Punkt der Verdichtung:
die Funktion zählt `day_offset` je Bar, und daraus wird `days_to_close`. Minutenbars
direkt in die Sequenz zu geben, würde jede Minute als „Tag" zählen und genau die
Kennzahl zerstören, die 3D braucht. Nach der Verdichtung heisst `days_to_close == 1`
exakt „am Signaltag getroffen".

**`signal_time`** ergibt sich aus dem `run_type` der Zeile: `pre_market` → 09:00 ET,
`trade_proposals` → 10:10 ET, jeweils über `America/New_York` in UTC umgerechnet (nicht
hartkodiert, damit die US-Zeitumstellung nicht erneut zum Thema wird).

**Kosten und Aufwand** (geprüft, nicht geschätzt): Capital.com berechnet nichts pro
Call — das Kostentracking des Projekts erfasst ausschliesslich Claude. Das Rate-Limit
liegt laut PDF (S. 6, S. 39) bei **10 Requests/Sekunde**. Ein Zusatz-Call je offener
Prediction je Lauf bedeutet bei ~27 Predictions und maximal 5 Haltetagen ≤ 135 Calls
pro Nacht, also rund 14 Sekunden.

Die Minutendaten von Tag D ändern sich nach dessen Abschluss nie mehr, werden aber bei
jeder Auswertung erneut geholt — bis zu fünfmal je Prediction. Das ist **bewusst in Kauf
genommen**: der Evaluator bleibt zustandslos und selbstheilend, und ein fehlgeschlagener
Lauf braucht keinen Nachhol-Pfad. Bei 3F-Grösse (500 Ticker → ~2 500 Calls/Nacht) lohnt
es, die synthetische Bar einmalig in `final_close` zu berechnen und auf der
Prediction-Zeile zu speichern; das ist der Skalierungspfad, nicht der jetzige Bau.

**Randfälle.** Liegen für das Fenster keine Minutendaten vor (Feiertag, Handelsstopp,
Abruffehler), entfällt die synthetische Bar und die Auswertung beginnt bei D+1 — die
Prediction wird also nicht schlechter behandelt als heute. Für Commodities/Crypto gilt
dasselbe Verfahren; dort ist das Tagesende ebenfalls 00:00 UTC.

**Folge für die Daten:** Outcomes ändern sich gegenüber heute — die Rückwärts-Artefakte
verschwinden, die Intraday-Treffer bleiben erhalten. Alte und neue Outcomes sind nicht
direkt vergleichbar; 3D muss den Umstellungstag kennen.

### 4.4 Sichtbarkeit und Reihenfolge

`final_close` am UTC-Tag **X** kennt finale Bars bis einschliesslich **X-1**.

- `evaluate_open_predictions(today=X)` filtert weiterhin `date < X`; das schliesst D ein.
- Eine Prediction vom Tag D ist damit bereits im Lauf **X = D+1** auswertbar — über die
  synthetische Bar aus 4.3. Ohne sie wäre es frühestens D+2.
- `evaluated_date` ist der Tag des Bars, der geschlossen hat (E7).

---

## 5. Der Sweep: alles, was `price_history` liest

Vollständige Durchsicht, weil `price_history` den aktuellen Tag künftig erst nach
00:15 UTC des Folgetags enthält. Jede Stelle, die stillschweigend „heute steht schon
drin" annimmt, ändert ihr Verhalten.

| # | Stelle | Annahme heute | Verhalten im neuen Modell |
|---|---|---|---|
| 1 | **`db.load_sector_db_momentum`** (`db.py:375`) | `JOIN price_history cur ON cur.date = ?` — **exakte Gleichheit** auf heute | ⚠️ **Bricht still.** Kein Treffer → `db_momentum` immer NULL → D9 kann „beide Signale vorhanden" nie erfüllen → der Sektor-Guardrail wird faktisch tot. **Muss auf den letzten finalen Tag umgestellt werden.** |
| 2 | `signal_checks.daily_change_pct` (`signal_checks.py:38`) | `date <= ?` `ORDER BY date DESC LIMIT 2` | Vergleicht künftig D-1 gegen D-2 statt D gegen D-1. Kein Absturz. **Festlegung:** die Funktion behält dieses Verhalten und wird in „Tagesperformance des letzten abgeschlossenen Handelstags" umbenannt — sie speist relative Stärke und D9, und beide sind als Vergleich abgeschlossener Tage sinnvoller als auf einer Teilbar. Der Docstring hält fest, dass der aktuelle Tag bewusst nicht enthalten ist. |
| 3 | `signal_checks.compute_relative_strength` | baut auf #2 für Ticker **und** ETF | Beide Seiten verschieben sich gemeinsam, die Differenz bleibt aussagekräftig. Nebeneffekt: die bisher mögliche Fehlpaarung (Ticker heute vs. ETF gestern) verschwindet. |
| 4 | `data_collector._fill_price_gaps` (`data_collector.py:225`) | `MAX(date)`, dann `if last_date >= date: return 0` | Wird faktisch wirkungslos (`len(missing) <= 1`). Die Lückenfüllung übernimmt `final_close`. Entweder anpassen oder bewusst stilllegen. |
| 5 | `db.load_price_history_from_db` (`db.py:1040`) | letzte 200 Bars bis `date` | Endet künftig bei D-1. Indikatoren auf abgeschlossenen Tagen sind **korrekter** als auf einer Teilbar. ⚠️ Aber `_process_ticker` setzt `"price": df["Close"].iloc[-1]` (`data_collector.py:384`) — **das muss auf den Live-Snapshot umgestellt werden**, sonst analysiert die Pipeline auf dem Schluss von gestern. Ebenso zu prüfen: `intraday_range_pct` und `volume_ratio` beschreiben dann D-1. |

**Ergebnis:** Es gibt genau **eine** bisher unentdeckte Stelle mit der falschen Annahme
(#1, `load_sector_db_momentum`) — und sie ist die schwerste, weil sie lautlos einen
Guardrail abschaltet. Die übrigen sind bekannt oder unkritisch.

---

## 6. Schema

Additiv, keine bestehende Spalte wird angefasst. Migration über `_apply_migrations()`
mit `PRAGMA table_info()`-Guard (Regel 5), idempotent gegen eine bestehende
`tracking.db`.

```sql
ALTER TABLE predictions ADD COLUMN price_premarket REAL;
ALTER TABLE predictions ADD COLUMN price_open      REAL;
ALTER TABLE predictions ADD COLUMN price_1610      REAL;
ALTER TABLE predictions ADD COLUMN is_premarket    INTEGER;
```

`price_history.premarket_price` (2.6) bleibt ungenutzt und wird **nicht** befüllt — der
Vorbörsenkurs gehört zur Entscheidung, nicht zur Kurshistorie. Die Spalte wird im
Schema-Kommentar als tot markiert, damit sie nicht erneut jemanden beschäftigt.

---

## 7. Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| **Wochenende / Feiertag: keine neue Bar** | **Erwarteter Normalfall, kein Fehler.** Samstags gibt es für Aktien keine neue Tagesbar, für Crypto schon. `final_close` protokolliert „keine neue Bar" auf INFO, überspringt den Ticker und läuft weiter. Der Job endet grün. Ein eigener Test deckt das ab. |
| **Freitagsbar** | `openingHours` schliesst freitags um 21:00 UTC. Der Samstagslauf um 00:15 UTC holt sie. **Deshalb läuft der Cron täglich, nicht Mo–Fr.** |
| Einzelner Ticker-Abruf schlägt fehl | Nur dieser Ticker wird übersprungen, mit WARN. Der Lauf bricht nicht ab. |
| `final_close` fällt komplett aus | Nichts wird bewertet — und niemand merkt es, weil der Job keine Mail schickt. **`pre_market` prüft deshalb, ob für den letzten Handelstag eine finale Bar vorliegt, und warnt sonst sichtbar in der Tagesmail.** |
| 400er vom Provider | Kann nach dem Fix aus 8.1 nicht mehr durch ein Zukunfts-`to` entstehen. Ein trotzdem auftretender 400er wird als normaler Abruffehler behandelt. |

Sichtbarkeit der Bewertung: `final_close` verschickt **keine** Mail. Die Ergebnisse
erscheinen wie bisher in der Fussleiste der nächsten `pre_market`-Mail
(`_section_footer`, „Vortags-Performance"), gespeist aus `_aggregate_yesterday_outcomes`.
Damit das trägt, ist E7 zwingend.

---

## 8. Cron und Nebenläufigkeit

### 8.1 Zeitpunkt

Cron: **`15 0 * * *`** — täglich, nicht Mo–Fr. Der Samstagslauf holt Freitags
Schlusskurs. Der Job zielt auf den **UTC-Vortag**, nicht auf ein Berliner Datum.

Die 15 Minuten gegenüber dem naheliegenden `0 0 * * *` sind Puffer auf die Bar-Grenze:
die Bar wird um 00:00 UTC final, und ein Lauf exakt auf der Kante riskiert ein Rennen
mit der Finalisierung. GitHub-Actions-Crons verspäten sich nur, nie früher — das Risiko
liegt damit einseitig auf der sicheren Seite.

### 8.2 DST — warum hier nichts zu bedenken ist

Anders als `trade_proposals`, der an der **US-Sitzung** hängt und deshalb zwei Slots
braucht, hängt `final_close` an der **Bar-Grenze**. Die ist laut `openingHours` selbst
UTC-fix (`zone: UTC`, s. 2.3). Job und Datenquelle liegen am selben Anker; eine
Zeitumstellung verschiebt beide nicht gegeneinander. **Es gibt keine DST-Kopplung.**

### 8.3 Concurrency-Lock

Existiert bisher **nicht** — in keinem Workflow steht ein `concurrency:`-Block.
(`b9e381b` ist die Test-Netzsperre, kein Lock.) Er wird hier neu angelegt:

```yaml
concurrency:
  group: analyze-${{ github.repository }}
  cancel-in-progress: false
```

`cancel-in-progress: false`, weil ein laufender Lauf bereits phasenweise in die DB
schreibt — ihn abzuschneiden wäre schlimmer als zu warten. Das entschärft zugleich den
in F.1 beschriebenen Cron-Konflikt.

---

## 9. Tests

- Provider: `resolution` wird durchgereicht; `MINUTE` liefert den Open-Bar.
- **400er:** Aufruf mit einem `to` in der Zukunft klemmt auf „jetzt" statt zu scheitern.
- Migration gegen eine bestehende DB; zweimaliges `init_schema` ist idempotent.
- `final_close`: schreibt finale Bars für Ticker **und** ETFs.
- **Wochenende:** kein neuer Bar → INFO, kein Fehler, Job grün.
- Evaluator liest `price_history` für D+1 aufwärts.
- **Das Fenster beginnt am Signal-Zeitpunkt:** ein TP-Treffer *vor* dem Signal am selben
  Tag zählt **nicht**, einer *danach* zählt mit `days_to_close == 1` (Intraday für 3D).
- Die synthetische Tagesbar verdichtet korrekt: `High` = Maximum, `Low` = Minimum,
  `Close` = letzter Wert des Fensters.
- Fehlen Minutendaten für das Fenster, beginnt die Auswertung bei D+1, ohne Fehler.
- `evaluated_date` = Handelstag, und `_aggregate_yesterday_outcomes` findet ihn (E7).
- `load_sector_db_momentum` liefert auch dann Werte, wenn für heute keine Bar existiert.
- `pre_market` warnt, wenn die finale Bar des letzten Handelstags fehlt.
- Kein Test ausserhalb `tests/live/` telefoniert (bestehende Transport-Sperre).

Coverage-Ziel bleibt 80 % (Stand jetzt: 93,20 % bei 541 Tests).

---

## 10. Was dieser Plan bewusst nicht tut

| Ausgelassen | Gehört zu |
|---|---|
| Gap-Analyse Final-Close → nächster Open | Backlog, PROJECT_STATUS 2b |
| Fair-Value-Gap-Erkennung im Lernmodul | Backlog, PROJECT_STATUS 2b |
| `price_history.premarket_price` befüllen | bleibt tot, s. 6 |
| Kombinierter `ranking_score` | 3C / C.2 |

---

## 11. Schnitt-Struktur

Nach jedem Schnitt ist der Stand grün und in sich konsistent.

| # | Inhalt |
|---|---|
| 1 | 400er-Fix (`to` klemmen) + `resolution`-Parameter im Provider — Voraussetzung für alles Weitere |
| 2 | Schema-Migration: die vier neuen Spalten |
| 3 | `final_close`: Run-Type, Preisabruf für Ticker + ETFs, `upsert_price_history`, Wochenend-Fall |
| 4a | Synthetische Signaltag-Bar: `signal_time` je `run_type`, `MINUTE`-Abruf, Verdichtung zu einer Tagesbar. Rein funktional, ohne Evaluator-Umbau testbar |
| 4b | Evaluator wandert nach `final_close`, liest `price_history`, stellt die Bar aus 4a voran; `evaluated_date`-Semantik (E7) und Footer-Verbindung |
| 5 | `pre_market`/`trade_proposals` auf Snapshots umstellen; `_ensure_today_bar()` und der ETF-Schreiber in `sector_momentum` entfallen; `e5e27c8` wird zurückgebaut |
| 6 | Die fünf Sweep-Stellen aus Abschnitt 5 nachziehen, `load_sector_db_momentum` zuerst |
| 7 | Cron, Concurrency-Lock, Sichtbarkeitswarnung |
| 8 | Doku |

**Arbeitsweise:** RED-GREEN, ein Commit je zusammenhängendem Schritt, niemals pushen.

---

## 12. Doku-Nachzug (Schnitt 8, je ein eigener Schritt)

Kein Punkt gilt als fertig, solange die Doku den alten Stand beschreibt.

- **`PROJECT_STATUS.md`** — neues Preismodell, `final_close` in der Run-Type-Tabelle,
  P2.8 um den Rückbau von `e5e27c8` ergänzen, die beiden Gap-Ideen in Abschnitt 2b.
- **`CLAUDE.md`** — Run-Type-Liste, die Regel „`price_history` enthält nur finale Bars,
  ein Schreiber", der 400er-Merkposten, DST-Begründung für `final_close`.
- **`docs/ARCHITECTURE.md`** — Phasenfolge, der neue Job, die Trennung aus Abschnitt 1.
- **Regel 14 unverändert:** `README.md`, `docs/WORKFLOW.md`, `docs/SPECIFICATION.md` und
  `mvp-design.md` bleiben dem finalen Durchgang nach Sprint 3 vorbehalten.
- **Plandateien** unter `docs/superpowers/plans/` werden **nicht** angefasst (E5).
