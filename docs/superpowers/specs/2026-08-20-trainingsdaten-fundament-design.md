# Trainingsdaten-Fundament für Sprint 3D — Design (2026-08-20)

**Status:** Entwurf, autonom erstellt. Korbinian hat Umfang und Entscheidungen
ausdrücklich delegiert ("entscheide selbst was das sinnvollste ist"). Jede eigene
Entscheidung ist unten unter **E1–E7** benannt und begründet.

---

## 1. Das Ziel, aus dem alles folgt

Korbinians Ziel: aus **Kursen + technischen Indikatoren + News + Marktlage +
Fundamentaldaten + Risikoabwägung + Marktrendite + Über-/Unterkauft +
Branchenstimmung** eine Kursprognose errechnen. Sprint 3D soll die Gewichtung
dieser Größen **messen**, nicht setzen — deshalb sind die acht Dimensionen
einzeln persistiert und `score_total()` wurde bewusst entfernt.

Daraus folgt die einzige Anforderung, die dieses Dokument behandelt:

> **Für jede Prediction muss später rekonstruierbar sein, was das System zum
> Zeitpunkt der Entscheidung wusste — dauerhaft und ohne Rückgriff auf
> veränderliche Tabellen.**

Ein Feature, das zum Trainingszeitpunkt nicht mehr rekonstruierbar ist, ist für
3D nicht vorhanden. Rückwirkend lässt sich das nicht heilen: jeder Tag, an dem
eine Lücke offen bleibt, kostet endgültig Daten.

## 2. Befund (Audit vom 2026-08-20)

Der Bestand ist besser als erwartet — `predictions` friert bereits 55 Spalten je
Signal ein, darunter alle acht Dimensions-Scores, das Technik-Signal und **beide**
Sektor-Momentum-Signale getrennt. Sieben von neun Zielgrößen sind sauber.

Drei Verlustarten wurden gefunden:

### 2.1 Befristete Tabellen (Löschung)

| Tabelle | Frist heute | Was 3D verliert |
|---|---|---|
| `news_summaries` | **30 Tage** | News-Belege je Ticker **und** die Einschätzungen zu allen 7 Rohstoffen/Kryptos |
| `skipped_tickers` | 90 Tage | warum ein Ticker ausfiel |
| `cutoff_log` | 180 Tage | **warum ein Ticker es nicht in die Tiefenanalyse schaffte** |
| `trend_analyses` | 180 Tage | der Megatrend-Kontext, der in die Prediction einfloss |

`news_summaries` hat die **kürzeste** Frist im ganzen Projekt — vergeben, als die
Tabelle noch eine Logtabelle war, bevor C.16 sie zur Trainingsdatenquelle machte.
Man behält das Label (`outcomes`) und verliert die Begründung.

`cutoff_log` ist der **Selektions-Bias-Nachweis**: ohne ihn trainiert 3D nur auf
Tickern, die den Trichter passiert haben, ohne die Verworfenen rekonstruieren zu
können.

### 2.2 Überschreiben ohne Historie

`fundamentals_cache` hält **genau eine Zeile je Ticker** (`INSERT OR REPLACE`,
7-Tage-TTL). Es gibt nie eine Historie. Der PE-Wert, der bei einer Prediction vom
15.08. galt, ist heute nicht mehr rekonstruierbar. In `predictions` stehen nur die
**abgeleiteten** Scores (`score_company`, `score_valuation`), nicht die Rohwerte.

### 2.3 Berechnet und weggeworfen

`signal_checks.compute_relative_strength()` (Tagesperformance des Tickers minus
die seines Sub-Sektor-ETF) wird ausschliesslich im 16:10-Prompt verwendet und
**nirgends persistiert**. Es ist eine reine DB-Rechnung, kostet also nichts.

### 2.4 Kein Verlust, aber irreführend

`news_summaries.sentiment` ist **kein** Sentiment, sondern aus der gewählten
Handelsrichtung rückabgeleitet (`long`→bullish). Wer es als unabhängiges
Nachrichtensignal auswertet, korreliert das Modell mit seiner eigenen Ausgabe.
**Nicht Teil dieses Umbaus** (s. § 7), aber hier festgehalten.

---

## 3. Entscheidungen

### E1 — Eine benannte Retention-Konstante statt vier SQL-Literalen
`config.LEARNING_RETENTION_DAYS = 730` (2 Jahre) gilt für alle vier
trainingsrelevanten Tabellen. Bisher standen die Fristen als vier verschiedene
Literale direkt im SQL von `cleanup_old_data()` — genau deshalb konnte
`news_summaries` bei 30 Tagen stehen bleiben, ohne dass es jemandem auffiel.
Eine benannte Konstante macht die Frist zu einer bewussten Entscheidung.

**Warum 730 und nicht „nie löschen":** Die DB wird über GitHub-Release-Artefakte
transportiert; unbegrenztes Wachstum ist ein reales Risiko. Rechnung bei heutigen
20 Tickern: ~27 `news_summaries`-Zeilen/Tag → ~20.000 Zeilen in 2 Jahren, wenige
MB. Bei 100 Tickern ~78.000 Zeilen. ⚠️ **Bei 500 Tickern wären es ~370.000 Zeilen
mit Volltext (grob 300 MB)** — dann ist die Frist erneut zu prüfen; der Hinweis
steht als Kommentar an der Konstante.

**Warum zwei Jahre:** Saisonalität und Regimewechsel braucht mehr als einen
Jahreszyklus, sonst lernt 3D ein einzelnes Marktjahr auswendig.

### E2 — Fundamental-Rohwerte je Prediction einfrieren
Neue Spalten in `predictions`: `pe_ratio`, `forward_pe`, `market_cap_b`,
`debt_equity`, `analyst_consensus`. Sie stehen bereits im `td`-Dict und müssen
nur mitgeschrieben werden.

**Warum in `predictions` und nicht als Historientabelle im Cache:** Der Wert
gehört zur *Entscheidung*, nicht zum Ticker. Eine Prediction ist die Einheit, die
3D lädt; ein Join über `(ticker, gültig_von, gültig_bis)` wäre eine zweite
Wahrheitsquelle mit Zeitfenster-Logik — genau die Sorte Komplexität, die später
Leakage-Fehler produziert. Der Cache bleibt Cache.

### E3 — Analysten-Aktualität mitschreiben
Neue Spalte `analyst_consensus_period` (Finnhubs `period`-Feld, ISO-Datum),
durchgereicht von `FinnhubProvider.get_fundamentals()` über
`fundamentals_cache` bis in `predictions`.

**Warum:** Heute wird `recs[0]` ohne jede Datumsprüfung genommen. Ein Konsens von
vor drei Monaten ist im Prompt nicht von einem tagesaktuellen zu unterscheiden.
Für 3D ist ein Feature ohne Zeitbezug bestenfalls Rauschen.

**Bewusst NICHT:** automatisches Verwerfen alter Perioden. Das wäre eine
Verhaltensänderung an der Analyse, und welche Frist richtig ist, weiss heute
niemand — **genau das soll 3D messen.** Wir zeichnen die Altersinformation auf
und lassen die Entscheidung dem Lernmodul.

### E4 — `relative_strength` in beiden Läufen berechnen und persistieren
Neue Spalte `relative_strength` in `predictions`; die Berechnung wandert
zusätzlich in den `pre_market`-Pfad.

**Warum in beiden Läufen:** Heute entsteht der Wert nur um 16:10. Stünde er nur
dort, wäre er für die Mehrheit der Predictions `NULL` — ein Feature, das
systematisch mit dem Run-Type korreliert, ist für 3D schlimmer als keins.
Die Berechnung ist eine reine DB-Abfrage, kostet also nichts.

### E5 — `analyst_upside` bleibt leer und wird NICHT entfernt
Der Finnhub-Provider gibt das Feld hart als `None` zurück; DB-Spalte und
`td`-Feld existieren.

**Warum stehen lassen:** Ein Entfernen wäre eine Schema-Migration an einer
produktiven Tabelle ohne jeden Gewinn — die Spalte kostet nichts und ist die
natürliche Landestelle, falls der Wert später aus einer anderen Quelle kommt.
Ein Kommentar an der Provider-Zeile hält fest, dass die Leere Absicht ist und
kein vergessener Fix. **Abwesenheit ist ehrlich; falsche Daten wären es nicht.**

### E6 — Kein Backfill für Bestandsdaten
Die neuen Spalten bleiben für die 14 bestehenden Predictions `NULL`.

**Warum:** Die Rohwerte von damals existieren nicht mehr (§ 2.2) — sie zu
rekonstruieren hiesse, sie zu erfinden. Der heutige Bestand ist 14 Predictions
aus 2 Handelstagen; der Verlust ist vernachlässigbar, eine erfundene Historie
wäre dauerhaft schädlich.

### E7 — Migration additiv, keine Umbenennung, kein DROP
Alle Änderungen sind `ALTER TABLE ... ADD COLUMN` nach dem bestehenden Muster in
`init_schema()` (PRAGMA-Prüfung, dann ADD). Kein bestehendes Verhalten ändert
sich, kein Wert wird gelöscht. Die produktive DB überlebt die Migration
unverändert.

---

## 4. Umfang

**Im Umfang:**
- `config.LEARNING_RETENTION_DAYS`, angewandt auf die vier Tabellen (E1)
- 7 neue `predictions`-Spalten: 5 Fundamental-Rohwerte + `analyst_consensus_period`
  + `relative_strength` (E2, E3, E4)
- 1 neue `fundamentals_cache`-Spalte: `analyst_consensus_period` (E3)
- `FinnhubProvider.get_fundamentals()` reicht die Periode durch (E3)
- `relative_strength` im `pre_market`-Pfad berechnen (E4)
- Migration in `init_schema()` (E7)

**Ausserhalb:** `sentiment`-Umbenennung, Universumsvergrösserung,
`analyst_upside` befüllen, TP/SL-Kalibrierung. Alle in § 7 notiert.

---

## 5. Datenfluss

```
FinnhubProvider.get_fundamentals()
  └─ + analyst_consensus_period            (E3, neu)
       ↓
   fundamentals_cache  (1 Zeile je Ticker, 7-Tage-TTL — bleibt Cache)
       ↓
   _apply_fundamentals_to_td()  →  td{pe_ratio, forward_pe, market_cap_b,
                                      debt_equity, analyst_consensus,
                                      analyst_consensus_period}
       ↓
   ranking → save_prediction()
       └─ friert die Rohwerte + relative_strength DAUERHAFT ein   (E2/E3/E4)
```

Der Cache bleibt veränderlich, die Prediction wird unveränderlich. Das ist die
Trennung, die § 1 verlangt.

## 6. Tests

- `cleanup_old_data()` löscht nichts innerhalb `LEARNING_RETENTION_DAYS` und
  löscht ausserhalb — je Tabelle ein Test, damit keine still auf einer eigenen
  Frist zurückbleibt (das war der `news_summaries`-Fehler).
- `save_prediction()` schreibt die sieben neuen Felder und toleriert ihr Fehlen
  (`None`), damit Bestandsaufrufer nicht brechen (E6).
- `get_fundamentals()` reicht `period` durch; fehlendes Feld → `None`.
- `relative_strength` landet aus dem `pre_market`-Pfad in der Zeile.
- Migration: eine DB **ohne** die neuen Spalten bekommt sie durch `init_schema()`
  und behält ihre Daten (E7).

## 7. Bewusst aufgeschoben

| Punkt | Warum nicht jetzt |
|---|---|
| `news_summaries.sentiment` umbenennen | Eigene Migration mit Lese-/Schreib-Umstellung; verfälscht Daten, aber verliert keine — nach diesem Umbau |
| Universum auf ~100 Ticker | Erst die Aufzeichnung reparieren, sonst skaliert man die Lücken mit |
| `analyst_upside` befüllen | Braucht eine neue Datenquelle (Kursziele), eigener Umfang |
| TP/SL-Kalibrierung | 7 von 7 Outcomes sind `sl_hit`; bei n=7 nicht entscheidbar — ab ~30 Outcomes prüfen |
