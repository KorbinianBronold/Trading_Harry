# Zirkularität beheben + Universum vergrössern — Design (2026-08-20)

**Status:** Entwurf, autonom erstellt; Umfang und Entscheidungen von Korbinian
delegiert. Eigene Entscheidungen als **F1–F7** benannt.

**Vorgänger:** `2026-08-20-trainingsdaten-fundament-design.md` (C.20). Dort wurde
der Wissensstand je Prediction eingefroren. Dieses Dokument behebt die letzte
*verfälschende* Aufzeichnung und vergrössert danach den Datendurchsatz.

⚠️ **Die Reihenfolge ist Teil des Designs.** Teil A repariert eine falsche
Aufzeichnung, Teil B vervielfacht sie. Erst A, dann B — sonst skaliert man den
Fehler mit.

---

## Teil A — `news_summaries.sentiment` ist kein Sentiment

### A.1 Das Problem

Die Spalte heisst `sentiment`, enthält aber keine Nachrichtenstimmung. Sie wird
aus der **vom Modell gewählten Handelsrichtung** rückabgeleitet:

```python
_SENTIMENT_FROM_DIRECTION = {"long": "bullish", "short": "bearish", "none": "neutral"}
```

Wer sie in Sprint 3D als unabhängiges Nachrichtensignal auswertet, korreliert das
Modell mit **seiner eigenen Ausgabe**. Das Ergebnis sähe nach starkem Signal aus
und wäre eine Tautologie. Bei `broad_scan`-Zeilen ist der Wert zusätzlich immer
`None`, weil `news_strength` eine Betrags- und keine Richtungsskala ist.

Der Wert selbst ist **nicht falsch und nicht wertlos** — er ist eine korrekte
Kodierung der Richtung. Falsch ist allein der Name, und zwar auf die
gefährlichste Art: er lädt zu genau der Fehlinterpretation ein.

### F1 — Umbenennen statt löschen
`sentiment` → **`derived_direction`**. Der Name sagt beides: abgeleitet, und
woraus. `market_impact` bleibt unverändert (dort ist der Name korrekt — er ist
aus `news_strength` bzw. `confidence` abgeleitet, aber beschreibt auch genau das).

**Warum nicht löschen:** Die Richtung *zum Zeitpunkt der Nachricht* ist ein
legitimes Merkmal, solange klar ist, woher sie kommt. Löschen würde Information
vernichten, um einen Namensfehler zu beheben.

**Warum jetzt:** Die Tabelle trägt heute 38 Zeilen aus zwei Testläufen. Nach der
Retention-Verlängerung auf 730 Tage (C.20) und einer Universumsvergrösserung
wären es hunderttausende. Der Umbenennungsaufwand steigt, der Nutzen sinkt.

### F2 — `ALTER TABLE ... RENAME COLUMN`, keine Tabellenkopie
SQLite 3.53 (lokal) und jede Version ab 3.25 unterstützen das direkt. Die
Alternative (neue Tabelle, Daten kopieren, alte droppen) wäre bei einer Tabelle
ohne Fremdschlüssel unnötig riskant.

Die Migration ist **idempotent** und introspektiv wie alle anderen im Projekt:
nur umbenennen, wenn `sentiment` existiert **und** `derived_direction` nicht.

### F3 — Prompt-Ausgaben bleiben unangetastet
Nur Spalte und die Python-Bezeichner ändern sich. Kein Prompt wird angefasst
(Regel 10), kein Modell sieht eine Änderung.

---

## Teil B — Universum auf ~100 Ticker

### B.1 Ausgangslage

`SP500_FULL_TICKERS` ist ein **Stub** auf `SP500_MVP_TICKERS` (20). Die übrige
Verdrahtung existiert bereits: `USE_FULL_SP500` (Env-Schalter), `--full-sp500`
im `historical_loader`, und `universe.full_universe()` liest beides korrekt.

Gemessene Phasenkosten (Lauf vom 2026-08-20, 20 Ticker) hochgerechnet:

| Universum | broad_scan | Phase 3 (bei 50 gedeckelt) | Lauf gesamt | pre_market/Jahr |
|---|---|---|---|---|
| 20 (heute) | 0,28 € | 0,88 € | **1,92 €** | 479 € |
| **100** | 1,39 € | 2,19 € | **4,34 €** | 1.085 € |
| 500 | 6,93 € | 2,19 € | 9,88 € | 2.470 € |

**`broad_scan` ist der einzige Posten, der linear mitskaliert** — Phase 3 deckelt
der Trichter bei `MAX_DEEP_ANALYSIS = 50`.

### F4 — 100 Ticker, nicht 500
5× Datendurchsatz für gut das Doppelte der Kosten, ohne die Voraussetzungen von
Sprint 3F (Parallelisierung, thread-sicherer `CostTracker`). 500 würde ~10 €/Lauf
kosten und eine ungemessene Laufzeit mit sich bringen — `pre_market` (15:00) muss
vor `trade_proposals` (16:10) fertig sein.

### F5 — Epic-Verifikation ist ein **Gate**, keine Formalie
Für Aktien gilt `epic == ticker` (ausser den Sonderfällen in `TICKER_MAP`). Ob
Capital.com ein Epic führt, ist damit **nicht garantiert**. Vor der Aufnahme
läuft deshalb ein read-only Sammelabruf gegen `/markets?epics=`; nur bestätigte
Symbole kommen in die Liste.

⚠️ **Nicht auflösende Ticker werden weggelassen, nicht "vorsichtshalber"
aufgenommen.** Ein Ticker ohne Kurse wird als `insufficient bars` übersprungen
und zählt Richtung `TICKER_MAX_SKIPS = 20` — er würde sich selbst deaktivieren
und dabei die Skip-Statistik verschmutzen.

### F6 — Backfill vor Aktivierung, in dieser Reihenfolge
CLAUDE.md ist eindeutig: *"Ein neuer Ticker braucht erst
`historical_loader.py --tickers <X>`, bevor er in die Config kommt."* Die
Reihenfolge ist deshalb: **Liste verifizieren → Historie laden → Abdeckung
prüfen (`--report-coverage`) → erst dann `USE_FULL_SP500=true`.**

Der Schalter bleibt eine **Env-Variable**, kein Code-Default: die Aktivierung ist
Korbinians Entscheidung und soll ohne Commit rückgängig zu machen sein.

### F7 — Kostendeckel auf 6,00 €
`MAX_COST_PER_RUN_EUR` 4,00 → **6,00**. Die Hochrechnung sagt 4,34 €; 6,00 gibt
Luft für die Streuung, die adaptives Denken erzeugt (C.18), ohne den Deckel als
Schutz zu entwerten. ⚠️ **Der Deckel ist die letzte Sicherung gegen einen
Kostenunfall** — er wird angehoben, weil die Grundlast steigt, nicht weil er
stört.

`COST_WARN_THRESHOLD_EUR` steigt entsprechend 3,00 → 4,50.

---

## Umfang

**Teil A:** Spalte umbenennen, Migration, drei Fundstellen in `main.py`, zwei in
`src/db.py`, Tests.

**Teil B:** Epic-Verifikation (Skript-Lauf, read-only), `SP500_FULL_TICKERS`
füllen, Kostendeckel, Backfill, Abdeckungsprüfung. **Keine Aktivierung** —
`USE_FULL_SP500` bleibt `false`, bis Korbinian sie setzt.

**Ausserhalb:** Parallelisierung (3F), TP/SL-Kalibrierung, `analyst_upside`.

## Tests

- Migration benennt um und erhält Daten; zweiter Aufruf ist ein No-Op (F2).
- `save_news_summaries()` / `load_news_summaries()` schreiben und lesen
  `derived_direction`.
- `_commodities_from_morning()` liest die neue Spalte (16:10-Mail).
- `SP500_FULL_TICKERS` enthält keine Duplikate und keinen Ticker ohne Epic-Weg.
- Kostendeckel-Konstanten sind konsistent (`WARN < MAX`).
