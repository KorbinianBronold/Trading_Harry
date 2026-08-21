# Outcome-Qualität: Stop-Distanz + Horizont-Labels — Design (2026-08-21)

**Status:** Autonom erstellt, Umfang von Korbinian delegiert. Eigene
Entscheidungen als **G1–G7**.

**Vorgänger:** C.20 (Wissensstand einfrieren), C.21 (Zirkularität, Universum).
Dort ging es darum, dass die **Merkmale** stimmen. Hier geht es darum, dass die
**Labels** stimmen — der zweite Teil derselben Voraussetzung für Sprint 3D.

---

## 1. Der Befund

Alle 7 vorliegenden Outcomes sind `sl_hit`, **6 davon an Tag 1**.

Zwei Diagnosen, die sich beim Nachrechnen als falsch erwiesen und hier
festgehalten werden, damit sie nicht wiederkehren:

- ❌ *„Der SL ist zu eng gesetzt."* Er ist intraday-eng **by design** — der
  v2-Prompt verlangt wörtlich „Intraday ist das einzige akzeptierte Ziel".
- ❌ *„Das 5-Tage-Fenster reisst intraday-enge Stopps."* 6 von 7 fielen an
  **Tag 1**; das Fenster ist nicht die Ursache.

✅ **Was tatsächlich zutrifft:** gemessen an `intraday_range_pct` — dem Maß, das
bereits in jeder Prediction steht — liegt der Stop bei **0,39–0,78 einer
typischen Tagesschwankung**. Kein einziger liegt darüber. Ein Einstieg mitten in
der Sitzung hat den Rest der Tagesspanne vor sich, und die deckt den Stop ab.
Der Stop wird also vom **Rauschen** erreicht, bevor die These sich bewähren kann.

Zusätzlich, unabhängig davon gefunden: **die 16:10-Freigabe belohnt Nähe zum
Stop.** Weil `R/R = Ertrag / Restrisiko` rechnet und der Guardrail nur eine
*Untergrenze* prüft, steigt die Kennzahl, je näher der Kurs an den Stop rückt:

| | Entry | SL | Restrisiko | R/R | Ergebnis |
|---|---|---|---|---|---|
| NVDA 15:00 | 221,06 | 218,94 | 2,12 | 2,2 | abgelöst |
| **NVDA 16:10** | 219,19 | 218,94 | **0,25** | **26,2** | `sl_hit` |
| GC=F 16:10 | 4380,60 | 4374,00 | 6,60 | 9,2 | `sl_hit` |

NVDA wurde mit „R/R 26,2" freigegeben und stand **0,11 % vor dem Stop**.

---

## 2. Teil A — Stop-Distanz beobachten (weich)

### G1 — Neuer Check `stop_inside_noise`, gemessen an `intraday_range_pct`
Nicht an ATR: ATR misst die Tagesspanne inklusive Übernacht-Lücken, der Stop
konkurriert aber gegen die **Intraday**-Bewegung. `intraday_range_pct` steht
bereits in jeder Prediction und im `td`.

Schwelle: `config.STOP_MIN_INTRADAY_RANGE_FRAC = 0.8`.

### G2 — **Weich**, nicht blockierend — und warum das keine Bequemlichkeit ist
Ein harter Check hätte in den vorliegenden Daten **alle 14 Signale verworfen**
(Spanne 0,39–0,78, keines über 0,8). Das wäre keine Kalibrierung, sondern eine
Abschaltung. Und die richtige Schwelle kennt heute niemand — genau die Sorte
Zahl, die dieses Projekt sonst misst statt annimmt (`BATCH_SIZE_DEEP`,
`TECH_MIN_FOR_DEEP`, `DIVERGENCE_TOP_N`).

Der Check schreibt deshalb `guardrail_rejects` mit `enforced=0` — dasselbe
Muster wie `SECTOR_GUARDRAIL_STRICT`. Die Wochenmail weist ihn dann aus, und
nach ~30 Outcomes ist die Schwelle eine **Messung**.

⚠️ **Wer ihn scharf stellt, ohne vorher die Verteilung anzusehen, schaltet die
Pipeline ab.** Der Kommentar an der Konstante sagt das.

### G3 — Erhoben in beiden Läufen, wie die B.3-Checks
Konsistent mit `enforce`-Muster: erhoben um 15:00 und 16:10, damit die
Statistik beide Entscheidungspunkte abdeckt.

---

## 3. Teil B — Restabstand zum Stop (hart)

### G4 — Neuer Check `stop_too_close`, nur im 16:10-Lauf, **enforced**
Prüft den **absoluten Restabstand** zwischen frischem Kurs und Stop, relativ zum
ursprünglich geplanten Risiko:

```
verbraucht = (entry_morgens - kurs_1610) / (entry_morgens - sl)      # long
```

Ab `config.STOP_BUDGET_SPENT_MAX = 0.75` gilt das Setup als aufgebraucht: drei
Viertel des Risikobudgets sind weg, bevor die Position überhaupt eröffnet wurde.

**Warum nicht die R/R-Obergrenze:** ein Deckel auf `rr_ratio` wäre ein Symptomfix
an einer abgeleiteten Kennzahl. Das verbrauchte Risikobudget beschreibt direkt,
was schiefgeht — und bleibt lesbar, wenn jemand später die R/R-Formel ändert.

**Warum hart:** anders als bei Teil A ist die Schwelle hier **nicht** die offene
Frage. Bei 75 % verbrauchtem Budget ist die Prämisse des Morgens widerlegt; das
ist kein Kalibrierungsspielraum, sondern eine Tatsache über das Setup. Und der
16:10-Lauf ist genau der Ort, an dem Checks durchgesetzt werden (B.3).

### G5 — Richtungsneutral
Für Shorts spiegelt sich die Rechnung. Ein Vorzeichenfehler wäre hier besonders
tückisch, weil er nur eine Richtung träfe — ein Test pinnt beide.

---

## 4. Teil C — Horizont-Labels

### G6 — Eigene Tabelle `outcome_horizons`, nicht Spalten in `outcomes`
Je Prediction und Horizont (1–`MAX_HOLD_DAYS`) eine Zeile:
`prediction_id, horizon_days, close_price, return_pct, tp_hit_by, sl_hit_by,
correct_direction`.

**Warum eine Tabelle statt 5×4 Spalten:** `outcomes` bliebe sonst mit 20 Spalten
zurück, deren Namen den Horizont kodieren (`return_d3`) — schlecht abzufragen und
starr gegenüber einem anderen `MAX_HOLD_DAYS`. Eine schmale Tabelle ist die
natürliche Form für „dieselbe Größe über mehrere Horizonte".

**Was das löst:** heute wird jede Prediction auf **einen** Ausgang reduziert. Von
den 6 Tag-1-Stopps weiss niemand, ob die These an Tag 3 aufgegangen wäre — die
Bars liegen in `price_history`, die Information wird nur weggeworfen. Mit
Horizont-Labels lernt 3D „richtig, aber Stop zu eng" statt „These falsch". Das
ist dieselbe Frage wie Teil A, nur aus den Daten heraus messbar statt per
Schwellwert gesetzt.

### G7 — Rückwirkend nachrüstbar, und deshalb ohne Eile-Malus
Anders als die Fundamental-Rohwerte (C.20, unwiederbringlich) sind die Bars da.
Ein Backfill-Skript labelt die 14 Bestands-Predictions vollständig nach.
`tp_hit_by`/`sl_hit_by` sind **kumulativ** („bis einschliesslich Tag N"), nicht
„an Tag N" — die Frage lautet „hätte ich bis dahin gehalten?".

⚠️ Die Labels sind **beobachtend**: sie ändern nichts an TP/SL, an der
Auswertung oder an `outcomes`. Sie beschreiben nur, was gewesen wäre.

---

## 5. Umfang

**A:** `config.STOP_MIN_INTRADAY_RANGE_FRAC`, `signal_checks.check_stop_distance()`,
verdrahtet in beiden Läufen, weich.
**B:** `config.STOP_BUDGET_SPENT_MAX`, `signal_checks.check_stop_budget_spent()`,
nur 16:10, hart.
**C:** Tabelle `outcome_horizons` + Migration, `evaluator.horizon_labels()`,
Aufruf in `run_final_close`, Backfill-Skript.

**Ausserhalb:** eigene Mehrtages-Setups (Weg B des Gesprächs) — verfrüht, solange
die Labels nicht zeigen, ob sie sich lohnen. TP/SL-Formel selbst.

## 6. Tests

- `check_stop_distance`: greift unter der Schwelle, schweigt darüber, **nie**
  `enforced=True`, `None` bei fehlender `intraday_range_pct`.
- `check_stop_budget_spent`: long **und** short (G5), Grenzfall genau auf der
  Schwelle, `None` bei fehlenden Preisen, `enforced=True`.
- Ein Test rechnet den echten NVDA-Fall nach (219,19 / 218,94 / 221,06) und
  erwartet Ablehnung — der Fall, der den Befund ausgelöst hat.
- `horizon_labels`: ein Horizont je Tag bis `MAX_HOLD_DAYS`, kumulative Treffer,
  kürzere Bar-Reihen liefern weniger Zeilen statt zu werfen.
- Migration additiv; Backfill ist idempotent (zweiter Lauf verdoppelt nicht).
