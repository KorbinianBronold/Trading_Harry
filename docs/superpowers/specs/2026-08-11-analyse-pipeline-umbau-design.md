# Analyse-Pipeline-Umbau — Design

**Status:** 🟡 **Spezifikation gültig, Umsetzung teilweise erfolgt** (Stand 2026-08-17)
**Erstellt:** 2026-08-11

- **Plan 1 (Fundament)** ✅ abgeschlossen — 17 Indikatoren, Technik-Signal, Schema.
  Keine Verhaltensänderung. PROJECT_STATUS **C.6**
- **Plan 2 (Trichter)** ✅ abgeschlossen — 13 von 13 Tasks plus Abschluss-Review mit vier
  behobenen Befunden. § 4.3 (Sammelabruf), § 4.4/4.5 (Phase 1 zerlegt, Technik-Signal im
  Sidecar), § 4.6 (`broad_scan.py`, verdrahtet), § 4.7 (Cutoff + `cutoff_log`,
  `TECH_MIN_FOR_DEEP`), § 8 (Finnhub-Ratenbegrenzung, Wochen-Vorlauf), § 18.1b–d.
  PROJECT_STATUS **C.7** und **C.8**
- **Plan 3a (Batch-Tiefenanalyse)** ✅ **abgeschlossen** — 11/11 Tasks, live verifiziert,
  Abschluss-Review durchgeführt. § 4.8 (Batch nach Sub-Sektor, Streaming), § 5.2 (`thin`,
  Polarität), § 9 (Prompts v2), § 10 (Fehlerpfad) sind umgesetzt. Der erste Testlauf hatte
  `MAX_TOKENS_DEEP` widerlegt (C.9); nach der Neukalibrierung (`TOKENS_PER_TICKER_DEEP`
  900 → 2500, `BATCH_TOKEN_RESERVE` 2000 → 200) trat `stop_reason=max_tokens` **kein
  einziges Mal** mehr auf, 12 von 12 Kandidaten analysiert. **Der Kostenhebel aus § 13.2
  ist unterboten:** 0,0204 EUR je Ticker gegen ein Ziel von 0,034 und ~0,12 im alten Weg.
  PROJECT_STATUS **C.9–C.12**
- **Plan 3b (Ranking)** ⏳ offen, Plan-Datei in Arbeit — § 5 (`rank_score`,
  `candidate_class`), Mail-Abschnitt. Die Designentscheidungen dazu stehen in **§ 20.5**;
  sie sind am Verifikationslauf des 3a-Abschlusses gemessen, nicht am Schreibtisch
  gewählt
**Betrifft:** Phasen 1c/2/3 sowie Ranking und Scoring in `pre_market`
**Nicht betroffen:** Preismodell und Snapshots, `final_close`, Evaluator, Cron-Struktur,
DB-Persistenz, R/R- und VIX-Logik, CFD-Eignungsregeln, Mail-Versandmechanik

> Diese Spec beschreibt den **Zielzustand**. Sie ersetzt die Teilschritte C.1–C.4 aus
> PROJECT_STATUS (Sprint 3C) und macht `MAX_DEEP_ANALYSIS` erstmals wirksam.
> Der Implementierungsplan entsteht getrennt unter `docs/superpowers/plans/`.

---

## 1. Ausgangslage

Die heutige Auswahlkette hat drei strukturelle Fehler.

**Es gibt keinen Deckel auf Phase 3.** `analyze_assets()` analysiert jeden nicht
ausgeschlossenen Ticker; `MAX_DEEP_ANALYSIS = 80` und `BATCH_SIZE_QUICK = 30` werden
nirgends gelesen. Begrenzt wird der Lauf allein durch `CostCapExceeded`.

**Der Quick-Filter kann keine Nachrichten sehen.** Phase 2 ist ein Haiku-Call **ohne**
Websuche über technische und gecachte Fundamentaldaten. Ein Ticker mit neutralen
Indikatoren, aber einer heute kursrelevanten Nachricht, erreicht Phase 3 nie.

**Das Ranking sortiert nach einer einzigen Modellzahl.** `probability_pct` ist Claudes
Selbsteinschätzung; die acht Score-Dimensionen fließen über `DIMENSION_WEIGHTS` in ein
`total_score`, das faktisch nur als Fallback berechnet wird und nichts steuert.

## 2. Ziel

Ein Trichter, der die Tiefenanalyse auf eine feste Obergrenze begrenzt, dabei aber jeden
Ticker des Universums einmal nachrichtenseitig anschaut — und ein Ranking, das auf zwei
unabhängig erhobenen, **zählbaren** Signalen beruht statt auf einer gemischten Zahl.

**Zielwerte** (gelten für den 3F-Vollausbau, ~500 Ticker):

| Größe | Ziel |
|---|---|
| Laufzeit `pre_market` + `trade_proposals` | unter 5–10 Minuten |
| Kosten | deutlich unter 90 EUR/Monat (Obergrenze, nicht Ziel) |
| Tiefenanalysen je Lauf | ≤ `MAX_DEEP_ANALYSIS` (Default 50), **nie** das volle Universum |

## 3. Begriffe

Die Arbeitsbegriffe „Stufe 1/Stufe 2" aus der Planungssession kollidieren mit den
`Phase`-Nummern im Code. Verbindlich ist ab hier **eine** Nummerierung:

| Arbeitsbegriff | Ab jetzt |
|---|---|
| Stufe 1 | Skip-Gate, Teil von Phase 1 |
| Stufe 2 | **Phase 2** (ersetzt `quick_filter.py`) |
| — | **Phase 2a** Cutoff · **Phase 2b** Fundamentaldaten |

---

## 4. Der neue Ablauf

| # | Schritt | API-Calls | Modell | Modul |
|---|---|---|---|---|
| 0 | Trend-Analyse | 1 | Sonnet | `trend_analyzer.py` |
| 0b | Marktkontext (VIX, A/D, Rotation) | 1 | Sonnet | `market_context.py` |
| **1a** | **Skip-Gate**: inaktiv, Historie < `MIN_BARS_RSI` | 0 | — | `data_collector.py` |
| **1b** | **Kurs-Sweep** über alle Überlebenden | ~n, ggf. deutlich weniger (§ 4.3.1) | — | `data_collector.py` |
| **1c** | **Indikatoren** aus `price_history` | 0 | — | `indicators.py` *(neu)* |
| **1d** | **Technik-Signal** | 0 | — | `technical_signal.py` *(neu)* |
| 1e | offene Capital.com-Positionen als Pflicht-Kandidaten | 1 | — | `main.py` |
| 1f | Sektor-Momentum (ETF live + DB) | ~21 | — | `sector_momentum.py` |
| **2** | **Nachrichten-Scan** über alle Überlebenden | 1 | Sonnet | `broad_scan.py` *(neu)* |
| **2a** | **Cutoff** → ≤ `MAX_DEEP_ANALYSIS` | 0 | — | `broad_scan.py` |
| **2b** | **Fundamentaldaten** der Kandidaten | 0–n | — | `data_collector.py` |
| 3 | Policy-Monitor + **Batch-Tiefenanalyse** | 1 + ⌈n/N⌉ | Sonnet | `deep_analysis.py` |
| 3b | Rohstoffe/Krypto — **alle 7, immer** | 7 | Sonnet | `commodities_crypto.py` |
| 4 | Qualifikation, Ranking, Divergenz, Persistenz | 0 | — | `ranking.py` |
| 4a | Portfolio-Check | 1 | Sonnet | `portfolio_check.py` |
| 5 | Mail | — | — | `email_sender.py` |

**Finnhub kommt im Tageslauf nicht mehr vor**, ausser als Selbstheilung in 2b (§ 4.7).

### 4.1 Modul-Zuschnitt

Ein Modul je Aufgabe, dem Muster von `signal_checks.py` und `sector_momentum.py` folgend:

| Modul | Inhalt |
|---|---|
| `src/indicators.py` | die 17 Indikator-Funktionen, herausgelöst aus `data_collector.py` |
| `src/technical_signal.py` | Richtung + zählbare Stärke, deterministisch, kein Claude |
| `src/broad_scan.py` | Phase-2-Scan **und** die Cutoff-Regel — ersetzt `src/quick_filter.py` |
| `src/deep_analysis.py` | `analyze_assets()` auf Batches umgestellt |
| `src/ranking.py` | Qualifikation, kombinierte Stärke, Divergenz, Deckel |

Mit `quick_filter.py` entfallen `quick_filter_v1.txt` und die tote Konstante
`BATCH_SIZE_QUICK` (wurde nie gelesen; Phase 2 machte schon bisher **einen** Call über
alle Ticker statt 30er-Batches).

Der Cutoff bleibt bewusst in `broad_scan.py`: die Regel liest ausschliesslich
Phase-2-Ausgaben. Getrennt gehalten exportierte sie ein Datenformat, das sonst niemand
liest. `data_collector.py` verliert die Indikator-Mathematik (537 Zeilen, 17 statt 9
Indikatoren trieben sie auf ~750) und behält Provider- und DB-Verdrahtung.

### 4.2 Phase 1a — Skip-Gate

Zwei Bedingungen, **beide existieren bereits** in `collect()` und `_process_ticker`. Sie
werden nur vorgezogen, damit der Kurs-Sweep sie nicht mitschleppt:

| Bedingung | Wirkung |
|---|---|
| `db.is_ticker_inactive()` | Ticker nach `TICKER_MAX_SKIPS` Skips deaktiviert (B.7) |
| Bars in `price_history` < `MIN_BARS_RSI` | ohne RSI kein Technik-Signal, keine Analyse |

> **Verworfen: Marktkapitalisierung und Mindestliquidität als Vorfilter.**
> Beide standen im ursprünglichen Entwurf, weil dieser Schritt 500 auf 150 reduzieren
> sollte. Diese Aufgabe hat der Cutoff übernommen. Innerhalb des S&P 500 trennt eine
> Marktkapitalisierungs-Hürde von 5 Mrd. praktisch nichts, und sie wäre nach dem
> Finnhub-Umbau der **einzige tägliche Leser** von `fundamentals_cache` — eine
> Kaltstart-Sonderbehandlung für null Nutzen. Ein Schwellwert auf `lastTradedVolume`
> misst Capital.coms Handelsfluss, nicht Handelbarkeit; für schlecht abgedeckte Ticker
> ist `TICKER_MAX_SKIPS` der dafür gebaute Mechanismus. `market_cap_b` erreicht Claude
> weiterhin über den Ticker-Snapshot aus 2b.

Die Eingangsmenge ist damit **das Universum minus dem, was nachweislich nicht auswertbar
ist** — bei gesunder Datenbank praktisch vollständig.

### 4.3 Phase 1b — Kurs-Sweep

Ein Live-Kurs je Überlebendem über `get_premarket_price()`
(`GET /api/v1/markets/{epic}`), daraus:

```
premarket_change_pct = (live − letzter finaler Close) / letzter finaler Close × 100
```

**Der Sweep ist kein Overhead, sondern die zweite Nachrichtenquelle.** Ein Wert, der 8 %
im Minus eröffnet, hat Nachrichten, ob er es in eine Mover-Liste geschafft hat oder
nicht. `premarket_change_pct` geht in den Phase-2-Prompt **und** als Sortierschlüssel in
den Cutoff.

⚠️ **Fehlender Live-Kurs ergibt `None`, niemals `0`.** Eine Null hiesse „eröffnet
unverändert" und wäre eine erfundene Beobachtung — dieselbe Klasse stiller Falschaussage
wie die eingefrorene Tagesbar (P2.8). `None` fällt im Cutoff hinter jeden gemessenen Wert
und erscheint im Prompt ausdrücklich als *unbekannt*. Übersteigt der Anteil ohne Kurs
20 %, warnt der Lauf von sich aus (Muster D3).

#### 4.3.1 ✅ Sammelabruf — beantwortet am 2026-08-12

`GET /api/v1/markets?epics=A,B,C` **funktioniert**: HTTP 200, Antwortfeld `marketDetails`,
mit 3, 10 und 20 Epics je vollständig beantwortet. Gemessen mit
`setup/probe_epics_batch.py` (read-only). Protokoll in PROJECT_STATUS, C.5.

**Der Kurs-Sweep nutzt Chunks zu 20.** Für 500 Ticker sind das **25 Calls statt ~500** —
Sekunden statt Minuten, ohne Phase 1 zu parallelisieren.

⚠️ **20 ist eine bestätigte Untergrenze, kein gemessenes Maximum.** Die Sonde blieb bei 20
stehen, weil das MVP-Universum genau 20 Ticker hat. Wo Capital.com wirklich abschneidet,
ist unbekannt — und **gleichgültig**: bei 25 Calls bringt eine grössere Chunk-Grösse nichts
mehr. Die echte Grenze wird nicht gesucht.

**Folgen für den Rest dieses Abschnitts:** die Taktungsfrage aus § 4.3.2 ist gegenstandslos
(25 Calls streifen das 600/min-Limit nicht); die 429-Notbremse aus § 4.3.3 bleibt als
Sicherheitsnetz, wird aber realistisch nie feuern.

⏳ **Bei der Umsetzung mitprüfen:** liefert `marketDetails` neben `bid` auch `offer`? Falls
ja, fällt der Spread beim Sweep kostenlos mit ab und der Backlog-Punkt „spread-bereinigtes
R/R" (§ 17) wird deutlich billiger.

#### 4.3.2 `CAPITAL_COM_BATCH_PAUSE` — die Pause entfällt im Sweep

⚠️ Die 12-Sekunden-Pause nach je 30 Tickern hat mit **keinem** der heutigen Provider zu
tun. Belegt über die Historie:

| Beleg | Fundstelle |
|---|---|
| `YFINANCE_PAUSE_SEC = 0.8` / `YFINANCE_BATCH_PAUSE = 12` | `408e8c9`, Scaffolding-Commit — vor jedem Provider |
| `BATCH_PAUSE_EVERY = 30  # spec §"Rate Limiting yfinance"` | `a60b8a0` |
| „*we sleep … to avoid **yfinance** rate limits*" | Docstring in `a60b8a0` |
| Beim Rename `d17c2f5` änderte sich **nur der Name**, nicht der Wert | Diff |

Der heutige Docstring in `collect()` behauptet, die Pause respektiere Capital.coms
Ratenlimit. Diese Begründung entstand beim Rename und war **nie wahr**: gegen 600/min
drosselt sie auf ~150/min.

**Konsequenz:** Die Taktung sitzt an der falschen Stelle. Der reine Capital.com-Sweep
braucht sie nicht. Das echte 60/min-Limit ist Finnhubs — und dort gibt es heute gar keine
Begrenzung (§ 8).

#### 4.3.3 Notbremse bei HTTP 429

| Ereignis | Verhalten |
|---|---|
| Erster 429 | Sweep schaltet **dauerhaft** in getakteten Modus (`Retry-After`, sonst 2 s); betroffener Ticker **einmal** wiederholt |
| Weiterer 429 im getakteten Modus | Ticker übersprungen, Zähler hoch, Sweep läuft weiter |
| 5 aufeinanderfolgende 429 | Sweep endet vorzeitig, Rest ohne Live-Kurs, WARNING mit Zahl |
| in allen Fällen | **Der Lauf läuft weiter.** Ein fehlender Live-Kurs ist nicht fatal. |

### 4.4 Phase 1c — Indikatoren

Berechnet für **alle** Überlebenden, nicht nur für spätere Kandidaten: es sind lokale
Rechnungen ohne API-Call, und das Technik-Signal ist Teil des Cutoff-Schlüssels.
`pandas_ta` ist bereits Abhängigkeit; **kein neues Paket**.

| Gruppe | Indikator | Neue Spalten | Min. Bars |
|---|---|---|---|
| Trend | SMA(50/200) | vorhanden (Distanz-%) | 200 |
| | EMA(50) | `ema_50_dist_pct` | 50 |
| | **MACD(12,26,9)** | `macd_line`, `macd_signal_line`, `macd_hist` | 35 |
| | ADX(14) | `adx_14`, `di_plus`, `di_minus` | 28 |
| | Parabolic SAR | `psar_value`, `psar_dir` | 10 |
| | Ichimoku | `ichi_tenkan`, `ichi_kijun`, `ichi_senkou_a`, `ichi_senkou_b`, `ichi_chikou` | 78 |
| Momentum | RSI(14) | vorhanden | 20 |
| | Stochastic | `stoch_k`, `stoch_d` | 20 |
| | Williams %R | `willr_14` | 20 |
| | CCI(20) | `cci_20` | 20 |
| | Momentum(12) | `mom_12` | 13 |
| | TRIX(15,9) | `trix`, `trix_signal` | 50 |
| Volatilität | Bollinger(20,2) | `bb_upper`, `bb_lower`, `bb_width` | 25 |
| | ATR(14) | `atr_abs` | 20 |
| | Donchian(20) | `donch_upper`, `donch_mid`, `donch_lower` | 20 |
| Volumen | OBV | `obv` | 25 |

⚠️ **`obv` beruht auf `lastTradedVolume` — dem CFD-Broker-Proxy von Capital.com, nicht
auf Börsenvolumen.** Der Wert beschreibt Capital.coms eigenen Handelsfluss. Als
Richtungsmass brauchbar, als Niveauaussage nicht. Gehört so in den Docstring und in
ARCHITECTURE.md.

**Fehlende Werte bleiben `None`, nie `0`.** Reicht die Historie für einen Indikator
nicht, ist er `None` — dieselbe Regel wie beim fehlenden Live-Kurs.

**Ladefenster von 200 auf 220 Bars.** `load_price_history_from_db()` lädt heute genau 200,
`compute_sma_distance_pct(df, 200)` braucht 200 — der Wert ist damit dauerhaft grenzwertig
und häufig `None`. Ohne die Anhebung fällt ein Drittel des Technik-Signals still aus.

> **Verworfen: Volume Profile.** Die Bedingung aus der Planung ist erfüllt —
> `get_intraday_ohlc()` liefert `MINUTE`-Auflösung, eine US-Sitzung hat 390 Minuten, ein
> Call je Ticker und Tag würde reichen. Der Einwand liegt woanders: ein Volume Profile
> beantwortet ausschliesslich die Frage, **auf welchen Kursniveaus der Markt viel
> umgesetzt hat**. Auf `lastTradedVolume` beantwortet es sie für Capital.coms CFD-Fluss.
> Bei OBV ist das verkraftbar, weil dort nur die Richtung zählt; beim Volume Profile ist
> die Mengenverteilung der ganze Inhalt. Dazu käme ein zusätzlicher API-Call je Ticker
> und Tag. **Gestrichen.**

### 4.5 Phase 1d — Technisches Signal

Deterministisch, kein Claude-Call. Drei richtungsgebende Teilindikatoren:

| Teilindikator | long | short |
|---|---|---|
| RSI(14) + Trend | RSI > 50 **und** steigend | RSI < 50 **und** fallend |
| MACD(12,26,9) | MACD-Linie > Signallinie | MACD-Linie < Signallinie |
| SMA-Trend | Close > SMA50 **und** SMA50 > SMA200 | invertiert |

**Richtung** = Mehrheit der drei; ohne Mehrheit `neutral`.
**Stärke** = Zahl der übereinstimmenden Teilindikatoren (0–3), moduliert durch **ADX(14)**:
`< 20` schwach (Stärke gedeckelt bei 1), `20–25` normal, `> 25` stark (Stärke +1, max. 4).

Drei offengelegte Entscheidungen:

1. **RSI wird als Momentum gelesen, nicht als Mean-Reversion.** Die Gegenlesart
   (überverkauft = Rebound-Chance) ist ebenso vertretbar. Gewählt wurde die, die zum
   bestehenden Guardrail passt (`momentum >= MOMENTUM_LONG_MIN` für long). Welche Lesart
   besser predictet, beantwortet 3D aus den persistierten Rohwerten.
2. **MACD als Vorzeichen des Histogramms, nicht als Kreuzung.** `compute_macd_signal()`
   liefert an den meisten Tagen `neutral`, weil eine Kreuzung nur an zwei Bars feuert. Das
   ist der konkrete Grund für die Rohwert-Speicherung.
3. **Degradation bei fehlendem SMA200:** der SMA-Teilindikator stimmt `neutral` — nicht
   „fehlend". Die Richtung entsteht dann aus RSI und MACD, `tech_agreement` ist
   entsprechend niedriger und macht das sichtbar.

### 4.6 Phase 2 — Nachrichten-Scan

**Ein** Sonnet-Call mit Websuche über **alle** Überlebenden. Ersetzt den Haiku-Quick-Filter.

Phase 0, 0b und der Policy-Monitor decken die breite Marktlage bereits ab; eine vierte
Marktrecherche wäre Wiederholung. Phase 2 leistet das, was nur sie leisten kann: die
**Ticker-Ebene**.

**Eingabe:** Trend-, Markt- und Policy-Kontext, dazu je Ticker eine kompakte Zeile
(Kurs, `premarket_change_pct`, 1d/5d-Änderung, RSI, ATR %, Sektor).

**Suchen:** 3–6 Listen-Abfragen für die gesamte Liste — grösste Pre-Market-Mover,
Earnings heute/morgen, Analyst-Upgrades und -Downgrades, Sektor-Ausreisser.

**Ausgabe:** striktes JSON, ausschliesslich zählbare Beobachtungen, keine Richtung und
keine „lohnt sich"-Einschätzung:

```json
{"results": [
  {"ticker": "MRNA", "news_strength": 3,
   "news_note": "Phase-3-Daten heute vorboerslich, -12% im Pre-Market"},
  {"ticker": "PG", "news_strength": 0, "news_note": ""}
]}
```

| `news_strength` | Bedeutung |
|---|---|
| 0 | keine Auffälligkeit |
| 1 | am Rande erwähnt |
| 2 | klarer Einzelticker-Katalysator |
| 3 | marktbewegend |

`news_note` ist **Pflicht ab Stärke 1** und trägt den Beleg. Fehlt er, setzt der Code die
Stärke auf 0 — eine Stärke ohne Beleg ist nicht überprüfbar.

> **Kein `technical_flag` vom Modell.** Der ursprüngliche Entwurf liess Phase 2 auch die
> technische Auffälligkeit melden. Das Technik-Signal ist reine Mathematik über
> `price_history`, kostet nichts und liegt für jeden Ticker vor. Wenn der Code den Wert
> exakt berechnen kann, ist Sonnets Einschätzung derselben Zahlen ein Rückschritt:
> teurer, ungenauer, und eine zweite Wahrheit für dieselbe Grösse.

⚠️ **Dokumentierte Grenze:** ein Ticker wird nachrichtenseitig nur sichtbar, soweit er es
in eine Mover-, Earnings- oder Upgrade-Liste schafft. Die zweite Quelle —
`premarket_change_pct` — fängt einen Teil dessen ab, was die Listen verfehlen.

### 4.7 Phase 2a — Cutoff und Phase 2b — Fundamentaldaten

**Cutoff**, deterministisch im Code:

```
Kandidat  ⟺  news_strength ≥ 1  ODER  tech_strength ≥ TECH_MIN_FOR_DEEP
Sortierung: (news_strength, |premarket_change_pct|, tech_strength, ticker), absteigend
Schnitt:    MAX_DEEP_ANALYSIS  (Default 50)
Pflicht-Kandidaten aus 1e stehen vorn und zählen gegen den Deckel
`premarket_change_pct = None` sortiert hinter jeden gemessenen Wert
```

**Kein Punktesystem, keine Multiplikatoren** — eine Tupel-Sortierung erfindet keine
Gewichte. `MAX_DEEP_ANALYSIS` wird damit erstmals gelesen und ist der einzige harte Deckel
auf Phase 3.

`TECH_MIN_FOR_DEEP` **= 2** (Default). Der Wert ist nicht frei gegriffen: eine Richtung
entsteht erst bei Mehrheit, also ab zwei übereinstimmenden Teilindikatoren, und der
Weak-ADX-Deckel drückt die Stärke auf 1. `tech_strength ≥ 2` heisst damit genau *„hat eine
Richtung **und** der Trend ist nicht als schwach eingestuft"*. Endgültig festzulegen nach
dem Testlauf gegen echte Verteilungen (§ 18).

⚠️ **Die Reihenfolge der Sortierschlüssel ist eine Vermutung, keine Herleitung.** Dass
News vor Technik sortiert, beruht auf dem Plausibilitätsargument „Nachrichtenlage ist die
knappe Information, Technik liegt ohnehin für jeden vor". Sie ist **genauso vorläufig wie
die Ranking-Formel in § 5.4** und in 3D datengetrieben zu ersetzen.

**Phase 2b** holt Fundamentaldaten und Earnings-Termine — im Normalfall aus
`fundamentals_cache` (0 Calls), bedarfsgetrieben nur für Kandidaten mit fehlendem oder
abgelaufenem Eintrag. Bei ~50 Kandidaten sind das ≤ 50 Finnhub-Calls, unter dem
Minutenlimit. Der Tageslauf bleibt Finnhub-frei, ohne Single Point of Failure.

### 4.8 Phase 3 — Batch-Tiefenanalyse

- **Batches nach Sub-Sektor**, wo möglich: der gemeinsame Markt- und Sektorkontext ist nur
  dann wirklich gemeinsam.
- **Recherche-Tiefe:** zuerst wenige breite Suchen für den Batch, dann **selektiv** nur für
  Ticker mit erkennbarer Auffälligkeit (Earnings anstehend, ungewöhnliche Bewegung, klarer
  Katalysator). Für unauffällige Ticker genügen Marktkontext plus die mitgelieferten
  Fakten. `max_uses` steigt batchgrössenabhängig (Vorschlag `4 + 2 × Batchgrösse`) — als
  **Obergrenze**, nicht als Vorgabe.
- **Technische Indikatoren werden als Fakten mitgegeben**, nicht selbst recherchiert oder
  geschätzt.
- **Claude bewertet alle Ticker des Batches** und wählt **nicht** selbst aus. Die Auswahl
  bleibt Aufgabe des Codes.

⚠️ **Die Batch-Grösse ist derzeit nicht von der Qualität begrenzt, sondern von der
Verdrahtung.** `call_claude()` ruft `messages.create()` ohne Streaming; über ~16 000
Output-Tokens greifen SDK-Timeouts. Bei ~800 Output-Tokens je Ticker ist bei ~15 Tickern
Schluss. **`call_claude()` bekommt einen Streaming-Pfad** (`messages.stream()` +
`get_final_message()`); danach ist die Batch-Grösse wieder eine Qualitätsfrage.

**`MAX_TOKENS_DEEP` steigt entsprechend.** Der heutige Wert 4096 ist für **einen** Ticker
ausgelegt. Neu wird er aus der Batch-Grösse abgeleitet (Richtwert ~900 Output-Tokens je
Ticker plus Reserve) statt fest zu stehen. `stop_reason == "max_tokens"` ist ein
Fehlerfall, kein akzeptables Ergebnis (§ 12).

**Dünne Dimensionen** werden mit `evidence_quality: "thin"` **behalten**, nie weggelassen —
stilles Weglassen hat sich in diesem Projekt wiederholt als Diagnose-Falle erwiesen
(vgl. `direction='none'`, früher lautlos verworfen). `check_analysis()` bekommt dafür eine
**schmale, gezielte Ausnahme**: `thin`-Dimensionen umgehen die Zwei-Belege-Pflicht, zählen
dafür nicht in die News-Stärke. **Keine generelle Aufweichung der Beleg-Pflicht.**

---

## 5. Signale, Qualifikation, Ranking

### 5.1 Technisches Signal

Richtung und Stärke aus § 4.5.

### 5.2 News-/Fundamental-Signal

**Richtung** = `direction` der Tiefenanalyse.
**Stärke** = `analysis_strength`, die Zahl der acht Dimensionen mit belegter,
richtungsübereinstimmender Evidenz:

```
zählt ⟺ evidence_quality != "thin"
     ∧ len(evidence) >= 2
     ∧ (direction == "long"  → value >= MOMENTUM_LONG_MIN)     # 6.0
     ∧ (direction == "short" → value <= MOMENTUM_SHORT_MAX)    # 4.0
```

Die Schwellen sind die **bereits existierenden** aus `config.py` — keine neuen erfundenen
Konstanten.

⚠️ **Der Wert heisst `analysis_strength`, nicht `news_strength`** — und das ist keine
Kosmetik. `news_strength` ist seit Plan 2 vergeben: es ist der **Nachrichten-Scan** aus
Phase 2 auf einer Skala von **0–3** (`broad_scan.py`, `cutoff_log`, und als
`news_scan.news_strength` in der Phase-3-Nutzlast). Der Wert hier ist eine andere Zahl auf
einer anderen Skala (**0–8**) aus einer anderen Phase. Beide unter demselben Namen zu
führen hiesse, in `predictions` eine Spalte zu haben, deren Bedeutung von der Tabelle
abhängt, in der man sie liest.

**`predictions` trägt beide Zahlen nebeneinander.** Das ist der eigentliche Grund für die
Trennung: nur so kann 3D die Frage stellen, ob der **billige Scan die teure Analyse
vorhersagt** — also ob sich der Cutoff überhaupt auf die richtige Grösse stützt. Mit einem
gemeinsamen Namen wäre genau diese Gegenüberstellung nicht formulierbar.

⚠️ **Polarität muss im Prompt festgeschrieben werden.** Bei `risk`, `policy_risk` und
`valuation` ist nirgends definiert, ob ein hoher Wert gut oder schlecht ist.
`DIMENSION_WEIGHTS` behandelte alle acht als positive Beiträge — die Konvention ist also
**höher = besser für den Trade**, sie steht aber in keinem Prompt. Ohne die ausdrückliche
Festlegung in `deep_analysis_v2.txt` und `commodities_crypto_v2.txt` zählt
`analysis_strength` bei drei von acht Dimensionen das Gegenteil.

⚠️ **Bekannte Schwäche:** `market_environment`, `policy_risk` und `sector_trend` sind
innerhalb eines Batches nahezu identisch und trennen kaum. Dafür wird **kein Sonderweg**
gebaut — die acht Einzelwerte liegen in `predictions`, 3D kann jede Teilmenge rückwirkend
nachrechnen.

### 5.3 Qualifikation

```
qualifiziert ⟺ tech_direction == news_direction ∈ {long, short}     # nur Aktien
```

Ein neutrales technisches Signal disqualifiziert automatisch. Danach unverändert: die
bestehenden Guardrails (R/R ≥ `RR_RATIO_MIN_HARD`, Beleg-Pflicht, TP/SL-Richtung,
Haltedauer, Intraday-Range) und die B.3-Checks (VIX, Sektor-Momentum, Klumpenrisiko).

⚠️ **Die Zwei-Signal-Hürde gilt nur für Aktien. Rohstoffe und Krypto werden nicht
disqualifiziert** — sie bekommen das Technik-Signal, aber es filtert bei ihnen nicht.

Der Grund ist eine Tatsache, keine Vorliebe: Rohstoffe und Krypto haben heute **gar kein
Technik-Signal**. `collect()` rechnet den Sidecar zwar auch für sie, `main.py` verwirft ihn
aber (`_cc_sidecar`), und `commodities_crypto.py` trägt kein `technical_signal` in seine
Nutzlast. Wörtlich angewandt fiele damit **jeder** Rohstoff und **jede** Kryptowährung
durch, weil `tech_direction` schlicht fehlt — im Verifikationslauf hätte das SI=F und GC=F
getroffen, die mit `analysis_strength` 6 und 5 die **stärksten Nachrichtensignale des
ganzen Laufs** trugen. Ein Filter, der die besten Signale wegen einer nicht verdrahteten
Datenleitung verwirft, misst die Datenleitung, nicht den Markt.

Daraus folgt für Plan 3b:

| | Aktien | Rohstoffe / Krypto |
|---|---|---|
| Technik-Signal berechnet und persistiert | ja | **ja** — `_cc_sidecar` wird verdrahtet |
| `rank_score` gebildet | ja | ja |
| fehlendes/neutrales Technik-Signal disqualifiziert | **ja** | **nein** — es rankt nur tiefer |
| bisheriges „always kept, regardless of score" | entfällt | **bleibt** |

Das Technik-Signal läuft bei ihnen also mit, ohne zu steuern — derselbe Rhythmus wie bei
den 29 Indikatoren aus § 7.5: **sein Wert entsteht dadurch, dass es ab heute mitläuft.**
Ob die Zwei-Signal-Regel auch für Rohstoffe trägt, ist eine 3D-Frage an die
Outcome-Historie, und die Historie entsteht nur, wenn die Zahl von jetzt an geschrieben
wird. `tech_strength` fliesst dabei in `rank_score` ein — ein Rohstoff ohne Technik-Bestätigung
landet damit korrekt weiter unten, statt zu verschwinden.

**Neu: `earnings_in_days` wird ein echter Check statt eines Modell-Attributs.** Heute
berechnet Claude `earnings_warning: true` selbst aus dem Snapshot, und es blockiert
nichts. Ein Bericht in ≤ 2 Tagen ist die einzige fundamentale Tatsache mit unmittelbarer
Intraday-Wirkung: er lässt den Kurs springen und entwertet damit das analytisch
hergeleitete TP/SL. Der Check zieht als Zeile in `src/signal_checks.py` — **erhoben in
beiden Läufen, durchgesetzt um 16:10**, nach dem bestehenden `enforce`-Muster aus
Entscheidung E4. Für Rohstoffe und Krypto ist `earnings_in_days` immer `None`, der Check
also trivial erfüllt.

⚠️ **Erwartetes Verhalten, ausdrücklich kein Bug** — und nach Universumsgrösse zu
unterscheiden:

| Szenario | Erwartung |
|---|---|
| **Heute, 20 MVP-Ticker** | Der Cutoff **greift nicht** (20 < 50). Alle 20 erreichen Phase 3 ohne jede Vorauswahl, die Zwei-Signal-Hürde trifft auf eine beliebige Stichprobe. Tage mit **null** qualifizierten Kandidaten sind erwartbar und normal. |
| **3F-Vollausbau, ~500 Ticker** | Der Cutoff bindet und wählt vor. Die Ausbeute sollte steigen — allerdings sortiert der Cutoff **primär nach `news_strength`**, `tech_strength` ist erst der dritte Schlüssel; die Vorauswahl wirkt also stark auf die Nachrichtenlage und nur schwach auf die Technik. Dass die Ausbeute steigt, ist eine Erwartung, keine Herleitung. |

**Prüfpunkt für einen späteren, grösseren Testlauf** (nicht für diesen Umbau): ob die
Zwei-Signal-Schwelle bei vollem Universum zu selten qualifiziert — und ob das dann als
„zu streng" oder als „korrekt konservativ" zu werten ist. Empirisch zu klären, nicht am
Schreibtisch.

### 5.4 Ranking der Qualifizierten

```
rank_score = analysis_strength (1..8) × tech_strength (1..4)      →  1..32
```

**Produkt, nicht Summe.** Eine Summe liesse eine Seite die andere tragen; das Produkt
verlangt, dass beide Signale beitragen — die These des Zwei-Signal-Designs.

⚠️ **Ausserhalb der angegebenen Wertebereiche ist `rank_score` `NULL`, niemals 0.**
Das gilt für **beide** Faktoren, und zwar unabhängig voneinander. Ein Produkt mit 0 löscht
die Aussage des jeweils anderen: SI=F mit `analysis_strength` 6 wäre von GC=F mit 5 nicht
mehr zu unterscheiden — die Zahl, die etwas aussagt, verschwände hinter der, die nichts
aussagt. `NULL` heisst „nicht rankbar", `0` hiesse „schlechtester Kandidat", und das wäre
schlicht falsch aufgezeichnet. Die Rangfolge fällt in diesem Fall auf `analysis_strength`
zurück.

| Nullfaktor | Wann erreichbar |
|---|---|
| `tech_strength = 0` | Bei Rohstoffen und Krypto, seit ein neutrales Signal sie nicht mehr disqualifiziert (§ 5.3), sowie bei **jedem** Divergenz-Kandidaten — dort ist das Technik-Signal per Definition neutral. |
| `analysis_strength = 0` | Auch bei einer **qualifizierten Aktie**. Die Guardrails prüfen den `momentum`-**Wert** gegen `MOMENTUM_LONG_MIN`, § 5.2 verlangt zusätzlich ≥ 2 Belege und `evidence_quality != "thin"`. Eine Analyse mit `momentum = 7.0`, `evidence_quality = "thin"` und acht schwachen Dimensionen besteht die Guardrails und zählt trotzdem 0. |

⚠️ Die zweite Zeile stand hier zunächst falsch — sie behauptete, der Fall könne bei Aktien
nicht eintreten, weil eine Richtung `tech_strength ≥ 1` erzwinge. Das stimmt für den
**technischen** Faktor, sagt aber nichts über den analytischen. Gefunden beim Review des
Plans 3b gegen den echten Guardrail-Code, bevor eine Zeile davon geschrieben war.

⚠️ `tech_strength` kann auch bei einem **qualifizierten** Kandidaten 1 betragen: die
Qualifikation verlangt nur eine Richtung (Mehrheit, also ≥ 2 übereinstimmende
Teilindikatoren), während schwacher ADX die Stärke auf 1 deckelt. Ein Kandidat mit klarer
Richtung in einem trendlosen Markt landet damit korrekt weit unten, ohne ausgeschlossen zu
werden — ADX bleibt Verstärkungsfaktor, nicht Filter.

Gleichstand: `analysis_strength` → `tech_strength` → Ticker alphabetisch. Deterministisch,
damit Tests reproduzierbar sind.

**R/R bleibt harte Guardrail, niemals Sortierkriterium** — sonst entsteht der Anreiz, TP
und SL für ein hübsches Verhältnis zu verbiegen.

⚠️ **Die Formel bleibt eine Vermutung — aber keine ungeprüfte mehr.** Sie ist wie die
Cutoff-Reihenfolge in § 4.7 ohne Datengrundlage *gewählt* worden, und **beide** sind in 3D
datengetrieben aus der Outcome-Historie zu ersetzen. Die von § 19 #4 geforderte
Plausibilitätsprüfung ist jedoch erfolgt, **bevor** die Formel hier festgeschrieben wurde:

> **Nachgerechnet am Verifikationslauf vom 2026-08-17** (C.11, 19 Analysen), § 5.2–5.5
> rückwirkend über die Phase-3-Logs:
>
> | Ticker | analysis_strength | tech_strength | **rank_score** | `probability_pct` |
> |---|---|---|---|---|
> | XOM | 8 | 3 | **24** | 60 |
> | NVDA | 6 | 3 | **18** | 55 |
> | BRK-B | 4 | 3 | **12** | 38 |
>
> Die Formel trennt sauber, erzeugt keinen Gleichstand, und ihre Reihenfolge ist
> **deckungsgleich mit `probability_pct`** — sie widerspricht Claudes Selbsteinschätzung
> also nicht, spreizt aber deutlich schärfer (24/18/12 gegen 60/55/38). Genau die
> Vergleichsgruppe, die § 5.7 für 3D aufheben will.

⚠️ **Die Stichprobe ist klein und die Ursache dafür ist selbst ein Befund:** von 19
Analysen kamen **16 mit `direction='none'`** zurück. Der dominierende Filter ist die
**Enthaltung der Tiefenanalyse**, nicht die Zwei-Signal-Hürde — die hatte überhaupt nur
drei Kandidaten zu bewerten. Die Erwartungstabelle in § 5.3 („Tage mit null qualifizierten
Kandidaten sind erwartbar") gilt damit verschärft: sie wird nicht die Ausnahme sein.

### 5.5 Divergenz-Kandidaten

| Fall | Ergebnis |
|---|---|
| Analyse hat Richtung, Technik **neutral** | **Divergenz** — persistiert, `candidate_class='divergence'` |
| Technik hat Richtung, Analyse `direction='none'` | **nicht persistierbar** — gezählt und geloggt, erscheint als Zahl in der Mail |
| Technik und Analyse **gegenläufig** | **Konflikt** — verworfen, als `guardrail_reject` gebucht |

Der mittlere Fall ist nicht persistierbar, weil Claude sich enthalten hat: es gibt kein
analytisch hergeleitetes TP/SL. Eines zu erfinden unterliefe die Guardrail-Grundregel —
dieselbe Begründung wie bei Entscheidung E5 (gedrehte Signale werden gemeldet, nicht
gehandelt).

**Deckel:** `DIVERGENCE_TOP_N = 5` je Richtung, sortiert nach demselben `rank_score`. Der
Rest wird gezählt, nicht persistiert.

⚠️ **`DIVERGENCE_TOP_N = 5` ist ein unbestätigter Startwert, kein Messergebnis** — dieselbe
Klasse Zahl wie `BATCH_SIZE_DEEP = 8` vor § 20.3. Der Verifikationslauf vom 2026-08-17
enthielt **null** Divergenzfälle: die drei Ticker mit neutraler Technik (AAPL, ABBV, GOOGL)
hatten allesamt auch eine Enthaltung der Analyse und fielen damit in die untere Zeile der
Tabelle, nicht in die obere. Der Deckel hat also noch nie gebunden und ist unbeobachtet.
Das ist kein Grund, ihn wegzulassen — ein fehlender Deckel fällt erst auf, wenn er fehlt —
wohl aber einer, ihn nicht für gemessen zu halten. Ob 5 zu eng oder zu weit ist, beantwortet
erst ein Lauf, in dem Divergenzen überhaupt auftreten.

⚠️ Ebenfalls beobachtet und **erwartungsgemäss**: der mittlere Fall der Tabelle (Technik
hat Richtung, Analyse enthält sich) traf **6 der 19** Ticker — er ist der häufigste
Sonderfall, nicht der seltene. Die Zahl gehört deshalb sichtbar in die Mail, sonst sieht
ein Leser an sechs von neunzehn Tickern vorbei.

**In der Mail** erscheinen sie in einem **eigenen, klar getrennten Abschnitt** —
„Divergenz-Kandidaten: starkes Signal in einer Dimension, noch keine Bestätigung in der
anderen" — niemals vermischt mit den Top-10-Listen. Das erhält die Top-10-Disziplin, ohne
die Information zu verlieren. Die Zahl der nicht persistierten Fälle (Deckel überschritten,
Konflikte, Enthaltungen bei starker Technik) steht als Kennzahl daneben, damit „nichts
gefunden" von „vieles verworfen" unterscheidbar bleibt.

Divergenz-Kandidaten werden **regulär ausgewertet**: `learnable=True`, der Evaluator
schliesst sie über TP/SL/Timeout wie Kern-Kandidaten, und `trade_proposals` löst sie
genauso über `superseded` ab — damit beide Gruppen denselben 16:10-Einstieg tragen und
vergleichbar bleiben.

Begründung: die Zwei-Signal-Pflicht verwirft künftig Kandidaten, die heute in die Top 10
kämen. Ob diese Regel Geld verdient oder kostet, lässt sich nur beantworten, wenn die
Verworfenen ein gemessenes Ergebnis bekommen. Das folgt der bestehenden Projektregel:
*ein hart verworfenes Signal bleibt offen und wird regulär ausgewertet; nur so lässt sich
messen, ob die Ablehnung richtig lag.*

### 5.6 Trennung in den Auswertungsfunktionen

⚠️ **Die core/divergence-Trennung sitzt in den Abfragen, nicht im Mail-Template.**
Der Weekly-Block-2-Join, der `superseded`-Zeilen auf `p.id` jointe und „Bestätigen"
dadurch als wertlos auswies (P2.8), ist die Lehre: eine falsche Gruppierung in der Abfrage
bleibt lange unbemerkt.

**Betroffen sind genau die Abfragen, die `predictions` lesen** — das sind drei, nicht
„alle fünf Weekly-Aggregate", wie es hier zuvor stand:

| Funktion | wo | gruppiert nach `candidate_class`? |
|---|---|---|
| `load_recent_outcomes_aggregate()` | `main.py` | **ja** |
| `db.load_revision_effectiveness()` | `src/db.py` | **ja** |
| `db.load_revision_verdict_stats()` | `src/db.py` | **ja** |
| `db.load_guardrail_reject_stats()` | `src/db.py` | nein — liest `guardrail_rejects`; eine verworfene Analyse wurde nie eine Prediction und hat folglich keine Klasse |
| `db.load_skipped_ticker_stats()` | `src/db.py` | nein — Datenqualitäts-Skips aus Phase 1, vor jeder Analyse |
| `db.load_sector_mapping_coverage()` | `src/db.py` | nein — Stammdaten, kein Lauf-Ereignis |

Die drei rechten Zeilen sind **nicht** vergessen worden: sie haben keine Spalte, nach der
sie gruppieren könnten. Sie hier aufzuführen ist billiger, als sie später erneut zu prüfen.

Ein Test hält das fest: eine `core`- und eine `divergence`-Zeile mit **gegenläufigem**
Ergebnis und die Zusicherung, dass keine Kennzahl sie vermischt.

### 5.7 `total_score`, `DIMENSION_WEIGHTS` und `probability_pct`

| Element | Entscheidung |
|---|---|
| `total_score` (von Claude geliefert) | **bleibt** — Pflichtfeld, persistiert, reine **Aufzeichnung** |
| `probability_pct` | **bleibt** — persistiert, in der Mail, und `probability_before`/`probability_after` in `trade_proposals` |
| **Sortierschlüssel** | war `probability_pct`, wird `rank_score` |
| `ranking.score_total()` und `config.DIMENSION_WEIGHTS` | **entfallen** |

`score_total()` wird heute genau einmal aufgerufen — als Fallback in
`analysis.get("total_score") or score_total(analysis)` (`ranking.py:110`). Da `total_score`
ein Pflichtfeld der Guardrails ist, greift der Fallback nur, wenn Claude exakt `0`
liefert. Eine Gewichtstabelle mit acht Prozentwerten, die nichts steuert, aber Wirkung
vortäuscht, ist dieselbe Klasse stiller Altlast wie `MAX_DEEP_ANALYSIS` vor diesem Umbau.

`total_score` und `probability_pct` bleiben erhalten, damit **3D messen kann, welcher
Massstab besser predictet** — Claudes Selbsteinschätzung oder die gezählte Stärke. Genau
die Vergleichsgruppe, die Entscheidung C.2 vom 2026-07-27 vorgesehen hat.

⚠️ **Folgeänderung in PROJECT_STATUS, Abschnitt 4.** Die Architektur-Invariante
*„8 Score-Dimensionen mit festem Gewicht … nicht ändern ohne A/B-Test"* wird
gegenstandslos — die Gewichte existieren danach nicht mehr. Sie ist umzuformulieren zu:
*die acht Dimensionen und ihre Einzelwerte bleiben erhalten und werden persistiert; eine
Gewichtung findet im Code nicht statt und ist Aufgabe von 3D.*

---

## 6. Rohstoffe und Krypto

**Gold, Silber, Öl, BTC, ETH, SOL und XRP werden JEDES MAL vollständig tief analysiert —
unverändert gegenüber heute, kein Trichter, kein Cutoff, keine Ausnahme.** Angeglichen
wird ausschliesslich die **Bewertungsqualität**.

> ⚠️ **Für diese sieben Assets darf kein Vorfilter gebaut werden.** Weder Stufe-1-Gate
> noch Cutoff noch eine spätere „Vereinheitlichung" dürfen sie reduzieren. Das ist eine
> bewusste Architektur-Entscheidung, keine Nachlässigkeit.

| Mechanismus | Aktien | Rohstoffe / Krypto |
|---|---|---|
| Skip-Bedingungen | ja | ja, **mit Ausnahme** (§ 6.1) |
| Kurs-Sweep, Indikatoren, Technik-Signal | ja | ja |
| **Phase-2-Scan** | ja | **nein** (§ 6.2) |
| Cutoff | ja | **nein** |
| **Phase 2b Fundamentaldaten** | ja | **nein** (§ 6.3) |
| Tiefenanalyse | Batch nach Sub-Sektor | eigener Prompt, ein Call je Asset |
| `thin` + Polaritäts-Klärung | Prompt v2 | **auch Prompt v2** |
| News-Stärke, Qualifikation, `rank_score`, Divergenz | ja | ja |
| **B.3-Checks** | ja | **nein** (§ 6.4) |
| `earnings_in_days`-Check | ja | trivial erfüllt (`None`) |

### 6.1 Ausnahme von der automatischen Deaktivierung

`collect()` prüft `is_ticker_inactive()` für alle Ticker. Lieferte Capital.com für Silber
zwanzigmal keine brauchbaren Daten, würde SI=F deaktiviert und verschwände **still** aus
einer Menge, die laut Architektur-Entscheidung immer analysiert wird.

**Die sieben sind von der automatischen Deaktivierung ausgenommen.** Fehlt eines von ihnen
in einem Lauf, ist das ein **WARNING**, kein stiller Skip.

### 6.2 Kein Phase-2-Scan

Sie umgehen den Cutoff, also konsumiert niemand ihr `news_strength` aus dem Scan; die
Nachrichtenlage erhebt Phase 3b ohnehin für sie. Sie mitzuschicken erzeugte eine Zahl, die
nirgends gelesen wird — dieselbe Klasse Attrappe wie die Tabelle `prompt_versions`.

### 6.3 Keine Fundamentaldaten

Finnhub hat für `GC=F` oder `BTC-USD` nichts. Phase 2b entfällt für sie ersatzlos.

⚠️ **Nebenwirkung, die heute schon besteht:** `_classify_data_quality()` zählt
`pe_ratio`, `market_cap_b` und `sector` als peripher — bei Rohstoffen sind alle drei immer
`None`. Sie erreichen damit **nie `data_quality='high'`**, sondern höchstens `'medium'`.
Funktional harmlos (der Guardrail blockt nur `'low'` + `confidence='high'`), aber 3D würde
beim Vergleich über Asset-Klassen hinweg darauf hereinfallen.

### 6.4 B.3-Checks bleiben aktienspezifisch

⚠️ **Diese Asymmetrie ist gewollt und darf nicht „vereinheitlicht" werden.**

Der VIX-Filter zeigt warum. Die Regel „ab VIX 35 keine neuen Longs" auf **Gold**
anzuwenden wäre nicht bloss unnötig, sondern **falsch herum**: Gold steigt typischerweise,
wenn der VIX springt. Ein Volatilitätsindex des Aktienmarktes ist kein Risikomass für ein
Krisenmetall. Wer die Checks später „der Einheitlichkeit halber" auf alle Asset-Klassen
ausdehnt, baut damit einen aktiv schädlichen Filter ein, der genau in den Marktphasen
zuschlägt, in denen Gold funktioniert.

Sektor-Momentum- und Klumpen-Check laufen für die sieben ohnehin ins Leere — sie haben
keinen Sub-Sektor.

### 6.5 Zwei semantische Unterschiede

- **`premarket_change_pct` bedeutet etwas anderes.** Krypto handelt durchgehend, die
  UTC-Bar schliesst um 00:00 — die Differenz zum letzten finalen Close ist „Veränderung
  seit Mitternacht UTC", keine vorbörsliche Lücke. Bei Rohstoff-Futures ähnlich. Das Feld
  wird für sie entsprechend benannt und im Prompt so erklärt.
- **Gleiche Indikatoren, andere Zeitspanne.** 220 Bars sind bei Aktien ~310 Kalendertage,
  bei Krypto ~220. SMA200 misst also nicht dasselbe Fenster. Kein Fehler, aber eine
  Asymmetrie, die 3D kennen muss, bevor es Aktien gegen Krypto vergleicht.

---

## 7. Datenbank

### 7.1 `technical_indicators`

**29 neue Spalten** aus § 4.4, alle `REAL` ausser `psar_dir` (`TEXT`). Bestehende Spalten
unverändert. (Die Zahl ergibt sich aus den mehrwertigen Indikatoren: MACD und ADX je drei
Spalten, Ichimoku fünf, Bollinger und Donchian je drei, PSAR, Stochastik und TRIX je zwei.)

### 7.2 `predictions`

| Spalte | Zweck |
|---|---|
| `candidate_class` TEXT DEFAULT `'core'` | `'core'` \| `'divergence'` |
| `tech_direction`, `tech_agreement`, `tech_adx_band`, `tech_strength` | das Technik-Signal zum Entscheidungszeitpunkt |
| `analysis_strength`, `rank_score` | die zwei Zahlen, nach denen sortiert wurde (0–8 bzw. 1–32, `rank_score` `NULL`-fähig, s. § 5.4) |
| `news_strength` | der **Scan**-Wert aus Phase 2 (0–3) — die andere Zahl, s. § 5.2. Steht daneben, damit 3D den billigen Scan gegen die teure Analyse messen kann |

Persistiert wird, **was tatsächlich entschieden hat** — auch wo es ableitbar wäre
(`tech_strength` aus Agreement und ADX-Band, `rank_score` aus beiden Stärken). Eine
spätere Formeländerung darf die Historie nicht rückwirkend uminterpretieren.

⚠️ **Zugleich der C.1-Fix aus Sprint 3C.** `_to_prediction_row()` schreibt heute
`"atr_pct": None, "rsi_at_entry": None, "volume_ratio": None` **hart**
(`ranking.py:121`), obwohl alle drei längst berechnet wurden. Da die Funktion ohnehin
umgebaut wird, wird das mitgenommen — es ist die Voraussetzung dafür, dass 3D auf diesen
Dimensionen überhaupt lernen kann.

### 7.3 Neue Tabelle `cutoff_log`

Die Cutoff-Eingangsdaten **aller** bewerteten Ticker je Lauf, nicht nur der Kandidaten:

```
date, run_type, ticker, news_strength, premarket_change_pct,
tech_direction, tech_agreement, rank_position, selected (bool)
```

**Ohne diese Tabelle ist die Cutoff-Reihenfolge in 3D nicht bewertbar** — es fehlte die
Kontrollgruppe für die Frage „hätte der 51. besser abgeschnitten als der 50.?". Sie ist
das Gegenstück zu der Kontrollgruppe, die bei den Divergenz-Kandidaten bewusst eingebaut
wurde. Unterliegt derselben Retention wie die übrigen Ereignis-Tabellen.

### 7.4 Migrationen

Über `_apply_migrations()` mit `PRAGMA table_info`- bzw. `sqlite_master`-Guard (Regel 5).
Alle Spalten sind additiv und `NULL`-fähig; Altzeilen bleiben lesbar, `candidate_class`
erhält per `DEFAULT` rückwirkend `'core'`.

### 7.5 Warum 29 Spalten jetzt

Nur vier der Indikatoren speisen das Technik-Signal. Die übrigen liegen zunächst ungenutzt
— und genau das ist der Punkt: **ihr Wert entsteht dadurch, dass sie ab heute mitlaufen.**
Beginnt 3D erst mit dem Schreiben, beginnt es mit null Historie. Die Rechnung kostet
nichts, der Speicher ist vernachlässigbar, die verlorene Zeit wäre nicht aufholbar.

---

## 8. Wöchentlicher Fundamentals-Job

`get_earnings_calendar()` hat heute **weder Cache noch Ratenbegrenzung** und lief täglich
je Ticker — bei Finnhubs 60 Calls/min im Free-Tier wäre das bei 500 Tickern in 429er
gelaufen. Die übrigen Fundamentaldaten haben längst eine 7-Tage-TTL.

`run_weekly()` bekommt einen Vorlauf, der `fundamentals_cache` **und** die
Earnings-Termine für das gesamte Universum füllt. Drei Auflagen:

- **Ratenbegrenzung ist Pflicht** — 500 Ticker bei 60 Calls/min sind ≥ 8,3 Minuten. Der
  Provider hat heute keine.
- **Nicht fatal**: schlägt der Abruf fehl, geht die Wochenmail trotzdem raus. Der Job ist
  heute reines DB-Aggregat plus Mail und darf das nicht verlieren.
- Earnings-Termine wandern in `fundamentals_cache` (dieselbe Zeile, dieselbe TTL), nicht
  in eine zweite Tabelle.

---

## 9. Prompts

Nach Regel 10 entstehen **neue Versionen**, die v1-Dateien bleiben unangetastet.

| Datei | Änderung |
|---|---|
| `prompts/broad_scan_v1.txt` | **neu** — der Phase-2-Scan |
| `prompts/deep_analysis_v2.txt` | Batch-Format, selektive Recherche, `evidence_quality`, Polaritäts-Festlegung, R/R-Ziel 1:2 (C.3) |
| `prompts/commodities_crypto_v2.txt` | `evidence_quality`, Polaritäts-Festlegung, R/R-Ziel, angepasste `premarket_change_pct`-Erklärung |
| `prompts/quick_filter_v1.txt` | entfällt mit `quick_filter.py` |

Der Analyse-Prompt folgt dem in der Planung erprobten Muster: acht Dimensionen je Aktie,
zuerst breite Marktlage, Auffälligkeiten der Vortage einbeziehen, mindestens zwei
Dimensionen mit konkreter Evidenz, klare Trennung zwischen kurzfristigem technischem
Rebound und struktureller Bewegung, Sektor-Auffälligkeiten ausdrücklich benennen.
Anpassungen für die Pipeline: striktes JSON statt Markdown-Tabelle, Entry/TP/SL/R-R je
Ticker, und **Claude wählt nicht selbst aus**.

---

## 10. Fehlerverhalten

| Fehler | Verhalten | Begründung |
|---|---|---|
| **Phase-2-Scan unparsebar / Ticker fehlen** | Lauf läuft weiter, Cutoff sortiert nur nach `tech_strength` und `premarket_change_pct`. WARNING. | Phase 2 speist nur die **Auswahl**, nicht die Qualifikation — `news_strength` kommt aus Phase 3. Die Predictions bleiben vollwertig, nur schlechter ausgewählt. |
| **Ein Batch schlägt fehl** | einmal wiederholen → dann **einmal halbieren**, beide Hälften versuchen → dann aufgeben, Ticker als übersprungen buchen | Ohne das kostet ein Fehler ~13 Ticker statt einen. Begrenzte Tiefe, damit ein kaputter Prompt nicht endlos retryt. |
| **Batch liefert nur einen Teil der Ticker** | die gelieferten werden übernommen, die fehlenden als `skipped` mit Grund gebucht | `quick_filter_batch` wirft heute bei fehlenden Tickern. Für die Tiefenanalyse wäre das falsch: zehn gute Analysen schlagen null. |
| **Stream bricht mitten in der Antwort ab** | wie Batch-Fehler | neuer Fehlerpfad durch das Streaming |
| **`CostCapExceeded`** | unverändert: Teilergebnis persistieren, Mail raus, Job rot | bestehende Invariante |
| **Kein Live-Kurs** | `premarket_change_pct = None`, nie `0`; ab 20 % Anteil WARNING | § 4.3 |

---

## 11. Tests

Alles ohne Netz — das Autouse-Fixture in `tests/conftest.py` bleibt unangetastet.
Coverage-Ziel unverändert ≥ 80 %. Keine bestehenden Tests löschen oder abschwächen.

| Bereich | Tests |
|---|---|
| `indicators.py` | je Indikator ein deterministisches DataFrame-Fixture; ausdrücklich der `None`-Fall bei zu kurzer Historie |
| `technical_signal.py` | tabellengetrieben über alle Kombinationen der drei Teilindikatoren × drei ADX-Bänder, **inklusive Degradation bei fehlendem SMA200** |
| Cutoff | Sortierung, Deckel, Pflicht-Kandidaten, `None`-Behandlung von `premarket_change_pct` (muss **hinter** jeden gemessenen Wert fallen, nicht als 0 gelten) |
| Qualifikation / Divergenz | vollständige Wahrheitstabelle: qualifiziert, divergent, Konflikt, Enthaltung |
| `rank_score` | Monotonie und Determinismus des Gleichstands; **`NULL` statt 0**, wenn `tech_strength` 0 oder fehlend ist (§ 5.4) |
| `analysis_strength` | tabellengetrieben über die drei Zählbedingungen aus § 5.2 — ausdrücklich `thin`, `< 2` Belege und die Richtungsschwellen je einzeln |
| Rohstoffe/Krypto im Ranking | Zusicherung, dass ein neutrales **und** ein fehlendes Technik-Signal sie **nicht** disqualifiziert (§ 5.3) |
| **core/divergence-Trennung** | eine `core`- und eine `divergence`-Zeile mit gegenläufigem Ergebnis; Zusicherung, dass keine der Aggregatfunktionen sie vermischt |
| Batch-Parsing | vollständig, unvollständig, unparsebar |
| Rohstoffe/Krypto | Zusicherung, dass sie Phase 2 und Cutoff **nicht** durchlaufen und von der Deaktivierung ausgenommen sind |
| **Kosten-Konstanten** | § 13.3 — bricht, wenn das Universum wächst, ohne dass die Konstanten mitgezogen wurden |
| Migration | gegen eine **Kopie** der Produktions-DB, nie das Original |

---

## 12. Testlauf

**Vorher, als Task 1 des Plans:** die `epics=`-Sonde (§ 4.3.1), read-only gegen die
Demo-API. Ihr Ergebnis entscheidet über die Sweep-Implementierung, bevor Code entsteht.

**Zweiter Schritt, vor jeder Messung:** der `fresh_input`-Fix (§ 13.1) — sonst misst der
Testlauf mit einem fehlerhaften Massstab.

**Der Testlauf selbst:** 1–2 Batches, echte Daten, **20 MVP-Ticker** (nicht ausgeweitet),
`cost_tracker` liest die tatsächlichen Zahlen.

| Prüffrage | Messgrösse |
|---|---|
| Wie skaliert die Laufzeit mit der Batch-Grösse? | Wanduhr je Batch bei zwei Grössen — **nicht linear annehmen** |
| Recherchiert Claude selektiv oder doch je Ticker? | `web_search_calls` je Batch ÷ Ticker im Batch. Nahe 1 ⇒ selektiv, nahe 5 ⇒ der Prompt greift nicht |
| Bleibt die Qualität bis zum **Ende** des Batches? | mittlere Belegzahl und Summary-Länge der ersten fünf gegen die letzten fünf Ticker |
| Reicht `MAX_TOKENS_DEEP`? | `stop_reason == "max_tokens"` darf nie auftreten |
| Ist `rank_score` plausibel? | Rangliste von Hand gegen die Analysen gelesen |
| Sind die MACD-Rohwerte da? | `macd_line` / `macd_hist` nicht `NULL` |

---

## 13. Kosten

Alle Zahlen mit dem Modell des `cost_tracker` (Sonnet 4.6, 3 $/15 $ je Mio. Token,
Websuche 0,01 $/Call, `USD_PER_EUR = 1.10`).

### 13.1 Befund: `fresh_input` zieht Cache-Treffer zweimal ab

⚠️ Die Anthropic-API liefert `input_tokens` bereits **als ungecachten Rest**; die
Gesamtgrösse ist `input_tokens + cache_read + cache_creation`. `cost_tracker.py:52`
rechnet `max(0, input_tokens - cache_read_tokens)` und subtrahiert damit ein zweites Mal.
Dieselbe Fehlannahme steckt in `cache_hit_rate = cache_read / input_tokens` (`:95`) — ein
Wert, der so über 1 gehen kann.

**Wirkung: die gemessenen Kosten sind zu niedrig, nicht zu hoch.** Bei ~2 k gecachtem
System-Prompt je Call und 27 Calls sind das grob 0,15 EUR auf die 3,13 EUR des
2026-08-09-Laufs — rund 5 %, wachsend mit der Cache-Trefferquote.

**Zu beheben, bevor der Testlauf misst.**

### 13.2 Hochrechnung für den 3F-Vollausbau

**Batch von 13 Tickern:** geteilter Input ~62 k (Kontexte + Suchergebnisse) + 2,6 k
Snapshots, Output ~10,4 k, ~12 Suchen → **≈ 0,43 EUR je Batch**, also **≈ 0,034 EUR je
Ticker** gegen die heute gemessenen **0,12 EUR** — Faktor ~3,5. 50 Kandidaten ergeben
vier Batches à ~13.

| Phase | Schätzung |
|---|---|
| 0 Trends | 0,13 (gemessen) |
| 0b Marktkontext | ~0,10 |
| 2 Scan über ~500 | ~0,32 |
| Policy-Monitor | ~0,10 |
| 3 Tiefenanalyse (50 in 4 Batches) | ~1,71 |
| 3b Rohstoffe/Krypto (7) | 0,60 (gemessen) |
| 4a Portfolio-Check | ~0,05 |
| **`pre_market` gesamt** | **~3,0 EUR** |
| `trade_proposals` (≤ 30 Revalidierungen) | ~0,70 EUR |
| **Monat (21 Handelstage)** | **~78 EUR** |

⚠️ **Das liegt unter 90, aber nicht komfortabel** — 13 % Luft, und die Eingangsgrössen
tragen leicht ±40 %. Der Wert kann ebenso bei 55 wie bei 105 landen. **Deshalb misst der
Testlauf, statt dass die Tabelle das letzte Wort hat.**

**Hebel, falls es hoch kommt**, in dieser Reihenfolge:

1. `MAX_DEEP_ANALYSIS` von 50 auf 35 — linear auf den grössten Posten, ~0,5 EUR/Lauf
2. Batch-Grösse hoch — mehr geteilter Kontext je Ticker
3. `trade_proposals` rein numerisch — ~15 EUR/Monat (§ 15)

### 13.3 Kosten-Konstanten

| Konstante | 20 MVP-Ticker | 3F-Vollausbau |
|---|---|---|
| `MAX_COST_PER_RUN_EUR` | 4,00 | **5,00** |
| `COST_WARN_THRESHOLD_EUR` | 3,00 | **4,00** |

Bei ~3,0 EUR je Lauf liesse der heutige Deckel nur 1,0 EUR Reserve — ein schlechter Tag
bräche mitten in Phase 3 ab. `COST_WARN_THRESHOLD_EUR = 3.00` würde bei praktisch jedem
3F-Lauf feuern und die Warnung wertlos machen.

⚠️ **Kein zweites fest verdrahtetes Wertepaar, das beim Übergang manuell umzustellen
ist.** Genau diese vergessene Handarbeit hat den `SP500_FULL_TICKERS`-Stub jahrelang still
falsch stehen lassen. Stattdessen ein **Test**, der aus `universe.full_universe()` die
Zahl der tatsächlich analysierten Assets rechnet
(`min(Aktien, MAX_DEEP_ANALYSIS) + Rohstoffe/Krypto`) und behauptet, dass
`MAX_COST_PER_RUN_EUR` dazu passt. Wächst das Universum oder ändert sich
`MAX_DEEP_ANALYSIS`, wird der Test rot, bis jemand hinsieht. Dazu die Herleitung als
Kommentar in `config.py`.

**Warum ein Test und keine Formel:** eine Kopplung `cap = Grundlast + Betrag × Analysen`
verlangt genau die Zahl, die der Testlauf erst ermitteln soll. Läge sie daneben, bräche
der Deckel echte Läufe ab. Ein fehlschlagender Test kostet eine Minute.

**Wie ernst der Test zu nehmen ist — verbindlich:**

- **Harter Test, kein Warnhinweis.** Kein `xfail`, kein `skip`, kein `pytest.warns`. Genau
  diese Mechanismen haben den `SP500_FULL_TICKERS`-Stub still falsch stehen lassen.
- **Er scheitert nur in einer Richtung.** Die Zusicherung lautet
  `MAX_COST_PER_RUN_EUR >= erwartete Kosten`. `MAX_DEEP_ANALYSIS` zu **senken** bricht ihn
  nie; er feuert ausschliesslich, wenn die Konfiguration Läufe am Deckel abbrechen liesse.
  Das ist ein Betriebsdefekt, kein Stilbefund.
- **Er blockiert keinen Commit.** Es gibt weder lokale Git-Hooks noch eine
  `pre-commit`-Konfiguration (geprüft 2026-08-11); `test.yml` läuft auf `push`, PRs nach
  `main` und `workflow_dispatch`. Ein roter Test heisst: **CI rot beim Pushen.**
- **Der Ausweg ist sichtbar, nicht still.** Übergehen heisst, `MAX_COST_PER_RUN_EUR` in
  `config.py` anzuheben — eine Zeile Diff, die in der Historie steht.
- **Die Fehlermeldung nennt die Rechnung**: erwartete Kosten, aktueller Deckel, Zahl der
  analysierten Assets und den Satz „entweder `MAX_COST_PER_RUN_EUR` auf X anheben oder
  `MAX_DEEP_ANALYSIS` senken". Ein Test, der nur `assert False` sagt, wird übergangen.
- **Der Betrag je Analyse steht in genau einer benannten Konstante mit Kommentar**, nicht
  verstreut im Test. Nach dem Testlauf ist die Anpassung eine bewusste Einzeiländerung.

`MODEL_PRICING` kennt `claude-sonnet-5` nicht: ein Modellwechsel scheiterte sauber mit
`ValueError`, statt still falsch zu rechnen. Als Sicherheitsnetz beabsichtigt.

---

## 14. Werkzeug-Entscheidungen

**Modell bleibt `claude-sonnet-4-6`.** `claude-sonnet-5` ist verfügbar, gleicher
Listenpreis, bis 2026-08-31 sogar günstiger, und deutlich stärker auf Agenten- und
Analysearbeit. **Trotzdem nicht in diesem Umbau:** Sonnet 5 bringt einen neuen Tokenizer
(~30 % mehr Tokens für denselben Text) und hat adaptives Denken standardmässig **an**, wo
4.6 es aus hat. Beides würde die Kostenmessung des Testlaufs unbrauchbar machen und kann
`MAX_TOKENS` unbemerkt sprengen. Ein Modellwechsel ist ein eigener Schritt mit eigener
Messung.

**Websuche auf `web_search_20260209` heben.** Die dynamische Filterung — das Modell filtert
Suchtreffer per Code, bevor sie ins Kontextfenster wandern — senkt genau die Input-Tokens,
die ein Batch-Design teuer machen. Läuft auf Sonnet 4.6, kein Beta-Header, und **kein
zusätzliches `code_execution` deklarieren** (eine zweite Ausführungsumgebung verwirrt das
Modell).

⚠️ `WEB_SEARCH_TOOL` steht heute auf `max_uses: 5` — das gilt **pro Call**, nicht pro
Ticker. Für einen Batch wären das fünf Suchen für alle Ticker zusammen (§ 4.8).

---

## 15. `trade_proposals`

Der 16:10-Lauf **behält seinen Sonnet-Call**. Punkt 7 der Planung ändert nur den Umfang —
welche Kandidaten frische Kurse bekommen —, nicht die Mechanik. `revision_verdict`, die
`superseded`-Ablösung, die sechs Ausgänge, Entscheidung E5 und Weekly-Block 2 bleiben
unberührt. Divergenz-Kandidaten laufen mit.

Begründung: dieser Pfad ist erst kurz fertig, dreifach reviewt (P2.8, Befunde C1–C3) und
**noch nie ausgeführt**. Ein Pfad wird nicht abgebaut, bevor er einmal gelaufen ist.

⚠️ **Bekannte, bewusst akzeptierte Einschränkung** (bestand bereits): eine Nachricht
zwischen `pre_market` und `trade_proposals`, die sich noch nicht im Kurs niederschlägt,
wird von den numerischen Checks nicht erkannt.

**Spätere Option:** die Revalidierung rein numerisch zu machen (Opening-Gap, VIX,
R/R-Neuberechnung ohne Claude-Call) spart ~15 EUR/Monat und senkt die Laufzeit deutlich.
Preis: `revision_verdict` und `probability_after` verlören ihre Datenquelle, Weekly-Block 2
würde zur toten Auswertung, E5 wäre nicht mehr umsetzbar. **Erst zu erwägen, wenn das
Budget drückt und der Pfad mindestens einmal produktiv gelaufen ist.**

---

## 16. Bekannte, bewusst akzeptierte Einschränkungen

1. **Earnings-Termine bis zu 7 Tage alt.** Mit dem wöchentlichen Finnhub-Rhythmus wird ein
   kurzfristig verschobener oder neu angekündigter Termin nicht gesehen. Selten,
   überschaubar, teilweise durch die Earnings-Listensuche in Phase 2 abgedeckt. **Keine
   zusätzliche Absicherung.**
2. **Nachrichtenlücke in `trade_proposals`** (§ 15).
3. **Phase 2 sieht nur, was in Listen auftaucht.** Teilweise abgefedert durch
   `premarket_change_pct` als zweite Quelle.
4. **Kalter `fundamentals_cache`:** beim allerersten Lauf lädt Phase 2b für alle Kandidaten
   nach — heute ≤ 20, im 3F-Ausbau ~50 Finnhub-Calls bei 60/min, also höchstens eine
   Minute Einmalaufwand. Danach greift der wöchentliche Job.
5. **Drei der acht Dimensionen trennen innerhalb eines Batches kaum** (§ 5.2).
6. **Fundamentaldaten wirken nur über die Dimensionen der Tiefenanalyse.** Eine
   deterministische Fundamental-Komponente analog zum Technik-Signal wurde geprüft und
   zurückgestellt: P/E, Forward-P/E, Debt/Equity, Analystenkonsens und Kursziel-Abstand
   sind Bewertungsgrössen mit einem Horizont von Monaten bis Jahren, während dieses System
   ausschliesslich intraday handelt. Ein sauber gerechneter Fundamental-Score sagte etwas
   gut vorher, das hier nicht gehandelt wird. Hinzu kommt: „P/E gegen Sektor-Median"
   braucht einen Median je Sub-Sektor — bei 20 MVP-Tickern erreichen **2 von 21**
   Sub-Sektoren überhaupt drei Mitglieder (P2.9). **3D beantwortet aus `score_valuation`
   und `score_company`, ob Fundamentaldaten stärker gewichtet gehören** — die Daten dafür
   werden bereits gesammelt.
7. **Rohstoffe/Krypto erreichen nie `data_quality='high'`** (§ 6.3).
8. **`obv` beruht auf Broker-Proxy-Volumen** (§ 4.4).

---

## 17. Nicht Teil dieses Umbaus — Backlog (PROJECT_STATUS 2b)

| Punkt | Notiz |
|---|---|
| **Ranking-Formel und Cutoff-Priorisierung datengetrieben** | **beide** in 3D aus der Outcome-Historie optimieren, nicht nur eine von beiden |
| Gewichtung aller 17 Indikatoren | 3D, datengetrieben; nicht fest raten — das wiederholte nur den `DIMENSION_WEIGHTS`-Fehler mit mehr Variablen |
| **Spread-bereinigtes R/R** | Der Spread aus dem `/markets`-Snapshot fliesst **in die R/R-Berechnung selbst** ein — **kein separater Guardrail** neben der bestehenden R/R-Prüfung, der ihr widersprechen könnte. `RR_RATIO_MIN_HARD` bleibt unverändert der Schwellwert |
| Modellwechsel auf `claude-sonnet-5` | eigener Schritt mit eigener Messung (§ 14) |
| Bündelung Rohstoffe/Krypto | 3 + 4 statt 7 Calls, ~0,4 EUR/Lauf bzw. ~8 EUR/Monat |
| Divergenz-Gegenfall | starke Technik + Enthaltung, messbar über eine dritte Klasse mit NULL-TP/SL und reiner Richtungsauswertung |
| Volume Profile | verworfen mit Begründung (§ 4.4) — nicht stillschweigend wieder aufnehmen |
| Fundamental-Komponente | verworfen mit Begründung (§ 16.6) |
| Geschäftsberichte / SEC EDGAR | eigener, späterer Task |
| „alle 500 sehen" fürs Lernmodul | braucht keinen Mechanismus: `final_close` deckt in 3F automatisch alle ab |
| Grep nach provider-spezifischen Begründungen | dritter Fall im Projekt (§ 4.3.2); prüfen, ob es weitere gibt |
| Tote Konstanten `CLAUDE_PARALLEL_CALLS`, `PAID_API_KEY`, `PAID_API_TYPE` | von diesem Umbau **nicht** berührt, daher nicht mitgenommen |
| `run_pipeline` / `run_trade_proposals`-Duplikat, doppelte E4-Durchsetzung | in der Planung als optionale Aufräumpunkte genannt („nur wenn ohnehin berührt"); ergeben sich nicht natürlich aus diesem Umbau und bleiben offen |

`MAX_DEEP_ANALYSIS` wechselt mit diesem Umbau von **80 (tot) auf 50 (wirksam)** — der
Wert ist neu gewählt, nicht übernommen.

---

## 18. Plan-2-Designentscheidungen (Ergänzung zu § 4.2–4.8)

Die Spec beschreibt den Zielzustand; diese Entscheidungen konkretisieren Punkte,
die die Spec offenlässt oder wo mehrere Umsetzungen möglich sind.

### 18.1 Phase 1: Reihenfolge, Fundamentals, Earnings

**a) Bar-Zählung nach Lückenfüllen.** Heute zählt `_process_ticker()` die Bars erst,
nachdem `_fill_price_gaps()` gelaufen ist. Diese Reihenfolge bleibt erhalten —
sonst würden Ticker übersprungen, die nach dem Nachladen genug Bars hätten. Das Gate
wird vorgezogen, der Rest der Reihenfolge bleibt unverändert.

**b) Fundamentals: Cache in Phase 1, Nachladung in 2b.** Die Spec zieht 2b aus
Phase 1 heraus. Ersatzlos ginge das nicht:
- `run_trade_proposals()` (16:10-Lauf) reicht dieselbe Snapshot-Liste in den
  Re-Validierungs-Prompt und den Portfolio-Check, beide brauchen den Sektor
- `broad_scan` (Phase 2) erhält den Sektor als Feldname

**Lösung:** Phase 1 liest `fundamentals_cache` (0 Calls, kein Finnhub-Overhead).
Phase 2b holt Fundamentals nach **nur für Kandidaten mit Cache-Miss** — der
teure Teil bleibt kandidaten-only, der Tageslauf im Normalfall Finnhub-frei.
Die Kostenaussage der Spec (§ 13.2) bleibt exakt erhalten.

**c) `get_earnings_calendar()` ins Wochenjob.** Läuft heute je Ticker je Lauf,
ungecacht. § 8 nimmt das raus und ratenbegrenzt. Der Tageslauf kennt
`earnings_in_days` nur aus dem Cache.

**d) Earnings als Datum speichern, nicht als Tageszahl.** `days_to_next` ist relativ
zum Abrufzeitpunkt; bei 7-Tage-TTL wäre ein gecachter Wert nach vier Tagen schlicht
falsch. Gespeichert wird `earnings_next_date` (ISO-String), `earnings_in_days` wird
beim Lesen gerechnet. § 16.1 akzeptiert damit 7 Tage alte *Termine*, nicht 7 Tage
alte *Countdowns*.

### 18.2 Phase 1: Persistenz und Prompt-Payload

**e) `premarket_change_pct` und `technical_signal` laufen neben `td`, nicht darin.**
Die Lehre aus dem Plan-1-Critical: `td` wird in vier Prompts serialisiert (`quick_filter`,
`deep_analysis`, `commodities_crypto`, `portfolio_check` über `main.py`'s `snapshots`).
Beide Werte erzengen nach der Spec täglich neue Informationen (Live-Kurs, Indikatoren),
die die Auswahl beeinflussen sollen — aber nicht die *bestehenden* Prompts. Sie laufen
in parallelen Strukturen neben `td` bis zur Persistierungs- bzw. Cutoff-Grenze.

**f) `data_quality` zerfällt sauber.** Der `'low'`-Skip (fehlendes RSI/ATR) bleibt in
Phase 1 — rein indikatorbasiert und keine Geheimnis-Abhängigkeit. Die
`medium`/`high`-Einstufung entsteht in Phase 2b, nachdem die Fundamentals da sind.

### 18.3 Rohstoffe / Krypto

Die sieben (Gold, Silber, Öl, BTC, ETH, SOL, XRP) umgehen den Trichter komplett —
sie werden **immer** tief analysiert. Plan 2 implementiert § 6.1–6.3:
- Automatische Deaktivierung aus `is_ticker_inactive()` ausgenommen (§ 6.1)
- Umgehen Phase-2-Scan, Cutoff, Phase 2b Fundamentals (§ 6.2/6.3)
- Ihre Tiefenanalyse läuft parallel zu (nicht statt) den Batch-Analysen der Aktien

---

## 19. Offene Punkte

| # | Punkt | Wann |
|---|---|---|
| ~~1~~ | ~~Akzeptiert `/api/v1/markets` eine `epics=`-Liste?~~ | ✅ **beantwortet 2026-08-12** — ja, Chunks zu 20 (§ 4.3.1) |
| 1a | Liefert `marketDetails` auch `offer` (Spread)? | ⏳ **nach Task 4 weiterhin offen** — die Sonde prüft es (`probe_epics_batch.py:144-147`), ein Ergebnis ist nirgends protokolliert, `get_premarket_prices_batch()` liest nur `bid`. Lauf mit `--run-live` nachzuholen |
| 2 | Endgültige Batch-Grösse der **Tiefenanalyse** | nach dem Testlauf — Startwert `BATCH_SIZE_DEEP = 8` festgelegt in § 20.3 |
| 3 | `TECH_MIN_FOR_DEEP` | nach dem Testlauf, gegen echte Verteilungen |
| ~~4~~ | ~~Plausibilität von `rank_score`~~ | ✅ **beantwortet 2026-08-17** — am C.11-Lauf rückwirkend nachgerechnet: 24/18/12, gleichstandsfrei, deckungsgleich sortiert mit `probability_pct` (§ 5.4). Stichprobe klein (3 von 19), weil 16 Analysen sich enthielten |
| 5 | `DIVERGENCE_TOP_N = 5` | offen — der Deckel hat noch nie gebunden, null Divergenzfälle im C.11-Lauf (§ 5.5) |

---

## 20. Plan-3-Designentscheidungen (Ergänzung zu § 4.8 und § 5)

Wie § 18 für Plan 2: die Spec beschreibt den Zielzustand, diese Entscheidungen
konkretisieren, was sie offenlässt. Getroffen am 2026-08-16.

### 20.1 Plan 3 zerfällt in 3a und 3b

Plan 3 umfasst Batching, Prompts v2, Streaming, Qualifikation, `rank_score`, Divergenz,
Mail und die Aggregat-Trennung — zusammen mehr als Plan 2 (13 Tasks). Er wird geteilt,
und die Grenze liegt **auf dem Testlauf aus § 12**:

| | Inhalt |
|---|---|
| **3a — Batch-Tiefenanalyse** | § 4.8 vollständig: Streaming in `call_claude()`, `deep_analysis_v2` + `commodities_crypto_v2`, Batch-Bildung, `MAX_TOKENS_DEEP` aus der Batchgrösse, Fehlerpfade aus § 10, `thin`-Ausnahme in `check_analysis()` |
| **→ Testlauf § 12** | beantwortet § 19 #2 (Batchgrösse) und liefert die Daten für #4 (`rank_score`) |
| **3b — Analyse & Ranking** | § 5 vollständig: `analysis_strength`, Qualifikation, `earnings_in_days`-Check, `rank_score` als Sortierschlüssel, `candidate_class` + `DIVERGENCE_TOP_N`, core/divergence in den Aggregaten, `score_total()`/`DIMENSION_WEIGHTS` raus, Mail-Abschnitt. Entscheidungen: **§ 20.5** |

**Begründung:** Die Spec verlangt in § 19, die Batchgrösse und die `rank_score`-Formel
**nach** dem Testlauf festzuschreiben. Läge der Testlauf mitten in einem einzigen Plan,
könnte sein Ergebnis Tasks rückwirkend ändern, die bereits geschrieben sind. An einer
Plan-Grenze ist er ein Prüfpunkt statt einer Störung. Zusätzlich landet der Kostenhebel
früher und unabhängig vom Ranking-Umbau — derselbe Rhythmus wie Plan 1 (kein
Verhaltenswechsel) gegen Plan 2 (Verhalten).

⚠️ **3a ist *fast*, aber nicht ganz verhaltensneutral.** Der Code-Pfad ändert nichts:
`evidence_quality` wird erhoben und persistiert, steuert aber nichts, und der
Sortierschlüssel bleibt bis 3b `probability_pct`. Die v2-Prompts bringen jedoch das
**R/R-Ziel 1:2 (C.3)** mit, und das verändert TP/SL — also die Analysen selbst. Eine
dritte Prompt-Version nur für diese eine Zielvorgabe wäre teurer als der Nutzen; die
Ausnahme wird bewusst in Kauf genommen und hier festgehalten, statt „keine
Verhaltensänderung" zu behaupten und es dann doch zu tun.

### 20.2 Batch-Bildung: ganze Sub-Sektoren packen

§ 4.8 sagt „Batches nach Sub-Sektor, **wo möglich**". Das „wo möglich" trägt mehr
Gewicht als es aussieht — gemessen an der echten Datenlage:

> Die **20 MVP-Aktien** zerfallen in **12 Sub-Sektoren**, der grösste hat **3** Ticker
> (Retail: AMZN/WMT/HD), sechs haben genau einen. Die 7 Rohstoffe/Krypto tragen gar
> keinen Sektor und laufen nach § 6 ohnehin als Einzelcalls. Striktes
> Sub-Sektor-Batching ergäbe **12 Batches für 20 Aktien** — gegenüber 20 Einzelcalls
> bliebe vom Kostenhebel fast nichts übrig.

**Regel:** Sub-Sektoren sind **unteilbare Einheiten**, die bis zur Ziel-Batchgrösse
gepackt werden (grösster zuerst, deterministisch sortiert). Ein Sub-Sektor wird nie über
zwei Batches zerrissen — **ausser** er überschreitet die Ziel-Grösse allein, dann wird
er aufgeteilt. Kleine Sub-Sektoren teilen sich einen Batch.

Die Regel braucht beide Richtungen, weil sich die Verteilung mit dem Universum dreht:

| | heute (20 Aktien) | 3F-Ausbau (~500 Ticker) |
|---|---|---|
| Sub-Sektoren im Topf | 12, die Hälfte davon Einzelstücke | ≤ 21, **konzentriert** — der Cutoff sortiert primär nach `news_strength`, und Nachrichten clustern nach Sektor |
| Wirksamer Mechanismus | **Zusammenlegen** | **Aufteilen** |
| Ergebnis bei `BATCH_SIZE_DEEP = 8` | 3 Batches (8/8/4), überwiegend gemischt | ~7 Batches, überwiegend sortenrein |

⚠️ **Phase 3 sieht nie 500 Ticker.** `MAX_DEEP_ANALYSIS = 50` ist seit Plan 2 der harte
Deckel; die Batch-Bildung arbeitet immer mit ≤ 50 Aktien plus den 7 Rohstoffen/Krypto,
unabhängig von der Universumsgrösse. Diese wirkt nur auf die *Verteilung*. Das Verfahren
wandert dadurch von selbst von „gemischt" nach „sortenrein" — dem Zielbild aus § 4.8 —
ohne dass am Code etwas geändert werden muss.

### 20.3 `BATCH_SIZE_DEEP = 8` als Startwert

Bewusst ein **Startwert**, den der Testlauf bestätigt oder kippt (§ 19 #2), kein
Endergebnis. Begründung:

- Bei 20 MVP-Aktien: **3 Batches (8/8/4) statt 20 Einzelcalls** — der Kostenhebel ist
  sofort messbar, und zwar mit demselben Faktor (~6,7×), den § 13.2 für den Vollausbau
  unterstellt
- `MAX_TOKENS_DEEP` landet bei ~8 × 900 + Reserve ≈ **9.000** — deutlich unter der Zone
  ab ~16.000, in der § 4.8 SDK-Timeouts erwartet, aber weit genug über der heutigen
  festen 4096, dass die Ableitung aus der Batchgrösse wirklich geprüft wird
- § 12 verlangt, die Laufzeit bei **zwei** Batchgrössen zu messen. 8 lässt nach oben
  und unten Raum zum Vergleichen; 20 (alle MVP-Aktien in einen Batch) liesse nur eine
  Richtung, machte die Sub-Sektor-Semantik bedeutungslos und läge mit ~18.000
  Output-Tokens bereits in der Timeout-Zone aus § 4.8

### 20.4 Streaming entschärft auch den `broad_scan`

§ 4.8 begründet den Streaming-Pfad in `call_claude()` allein mit der Batch-Grösse der
Tiefenanalyse. Er wirkt aber auf einen zweiten, bereits gebauten Aufrufer:
`broad_scan_batch()` ist **schon heute ein einziger Call über alle Phase-1-Überlebenden**
mit `MAX_TOKENS = 24000`, ausgelegt auf den 500-Ticker-Ausbau. Der Kommentar dort
(`src/broad_scan.py:28-50`) benennt den nicht gestreamten Pfad ausdrücklich als Risiko:
der httpx-Default-Timeout von 600s kann bei langer Generierung plus mehreren Websuchen
reissen.

Daraus folgt die Reihenfolge in Plan 3a: **Streaming ist Task 1**, nicht ein Nebenschritt
der Batch-Arbeit.

⚠️ **Anschlussbefund, in 3a mitzuerledigen:** derselbe Kommentar rechnet einen
Sicherheitsfaktor auf „~26.000–32.000" hoch und schliesst dann, 24.000 gebe „echten
Spielraum über der Worst-Case-Schätzung". 24.000 liegt **unter** der eigenen
Sicherheitsspanne. Beim 500-Ticker-Ausbau kann das kappen;
`_warn_if_possibly_truncated()` macht es sichtbar, verhindert es aber nicht. Die Rechnung
ist nachzuziehen und der Wert oder der Kommentar zu korrigieren.

### 20.5 Plan-3b-Entscheidungen

Getroffen am 2026-08-17, **nachdem** § 5 rückwirkend über die Logs des
C.11-Verifikationslaufs gerechnet wurde (19 Analysen). Alle vier Punkte sind Lücken oder
Fehler in § 5, die erst an echten Daten sichtbar wurden — keine nachträgliche
Geschmacksfrage.

| # | Entscheidung | Was sie behebt |
|---|---|---|
| 1 | Der gezählte Wert heisst **`analysis_strength`** (0–8); `news_strength` bleibt der Scan-Wert (0–3). `predictions` trägt **beide**. | § 5.2 vergab einen Namen, der seit Plan 2 belegt ist. Zwei Skalen unter einem Namen hätten eine Spalte erzeugt, deren Bedeutung von der Tabelle abhängt — und die 3D-Frage „sagt der billige Scan die teure Analyse vorher?" unformulierbar gemacht. |
| 2 | Die Zwei-Signal-Hürde gilt **nur für Aktien**. Rohstoffe/Krypto bekommen Technik-Signal und `rank_score`, werden davon aber nicht disqualifiziert. `_cc_sidecar` wird verdrahtet. | § 5.3 wörtlich angewandt hätte **jeden** Rohstoff verworfen, weil ihr Technik-Signal nie in die Nutzlast verdrahtet wurde — darunter die zwei stärksten Nachrichtensignale des Laufs. Der Filter hätte eine fehlende Datenleitung gemessen, nicht den Markt. |
| 3 | `rank_score` ist **`NULL`, nie 0**, wenn `tech_strength` 0 oder unbekannt ist. | Folgt zwingend aus #2: sobald ein neutrales Signal nicht mehr disqualifiziert, erreicht `tech_strength = 0` das Produkt und löscht `analysis_strength` aus. `0` behauptete „schlechtester Kandidat", wo „nicht vergleichbar" gilt. |
| 4 | Nach `candidate_class` gruppieren genau **drei** Abfragen, nicht „alle fünf Weekly-Aggregate". | § 5.6 verlangte die Gruppierung von drei Funktionen, die gar keine Predictions lesen. Die Tabelle in § 5.6 führt jetzt auch die nicht betroffenen auf — mit Begründung, damit sie nicht erneut geprüft werden. |

**Was der Lauf ausserdem gezeigt hat, ohne eine Entscheidung zu erzwingen:**

- **`rank_score` ist plausibel** (§ 19 #4 abgehakt): 24/18/12, gleichstandsfrei, gleiche
  Reihenfolge wie `probability_pct`, aber schärfer gespreizt.
- **Der dominierende Filter ist die Enthaltung, nicht die Zwei-Signal-Regel** — 16 von 19
  Analysen kamen mit `direction='none'`. Tage ohne jeden qualifizierten Kandidaten sind
  danach der Normalfall, nicht die Ausnahme. Das ist die wichtigste Erwartung, die der
  Mail-Abschnitt bedienen muss: „nichts gefunden" braucht eine Darstellung, die nicht wie
  ein Fehler aussieht.
- **`DIVERGENCE_TOP_N = 5` ist unbeobachtet** — null Divergenzfälle. Dieselbe Klasse
  unbestätigter Startwert wie `BATCH_SIZE_DEEP = 8` vor § 20.3, und genauso zu behandeln:
  eingebaut, aber nicht für gemessen gehalten.
