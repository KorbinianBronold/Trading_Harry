# Shares_Future – Sprint 2 Änderungen
## Doc-Update-Anweisung für Claude Code
## Datum: 2026-05-21

---

## Aufgabe

Aktualisiere alle Projektdokumentationen für Shares_Future.
Kein Code ändern – nur Docs. Nach dem Update liest Superpowers die
aktualisierten Docs und erstellt den Sprint-2-Implementierungsplan.

## Dateien die aktualisiert werden

1. docs/SPECIFICATION.md
2. docs/ARCHITECTURE.md
3. docs/WORKFLOW.md
4. CLAUDE.md
5. docs/superpowers/specs/2026-05-19-shares-future-mvp-design.md
6. docs/superpowers/plans/ → neue Datei erstellen

---

## Änderung A – Run-Types überarbeiten

### Neue Run-Type Übersicht

**pre_market (14:00 MEZ)**
- Vollständige Pipeline Phase 0–4
- Inkludiert vorbörslichen Kurs von Capital.com falls verfügbar
- Schickt Mail (Hauptanalyse des Tages)
- Kosten: ~3,20 EUR

**evaluate (15:00 MEZ)**
- Nur Evaluator: Tages-High/Low prüfen ob TP/SL getroffen
- Abgleich mit Capital.com echten Positionen (GET /positions)
- Kein Claude-Call, kein Mail
- Kosten: ~0,00 EUR

**midday (16:15 MEZ)**
- Vollständige Pipeline Phase 0–4
- Läuft nach Eröffnungsvolatilität (US-Börse öffnet 15:30 MEZ)
- Eröffnungspanik abgeklungen, Kurssprünge abgefangen
- Schickt Mail (Midday-Update)
- Kosten: ~3,20 EUR

**position_check (17:30 MEZ) – NEU**
- Capital.com GET /positions: eigene offene Trades abrufen (nur lesen)
- Vergleich mit heutiger Vorhersage
- Kurzer Claude-Call: hat sich etwas wesentlich verändert?
- Schickt kurze Status-Mail: ✅ auf Kurs / ⚠ nahe SL / ❌ Signal gefallen
- Kosten: ~0,20 EUR

**close (22:30 MEZ) – vereinfacht**
- NUR Datenpflege, kein Claude, kein Mail
- Capital.com Schlusskurs + Tages-High + Tages-Low abrufen
- In DB speichern
- Finaler TP/SL-Check für noch offene Positionen
- Kosten: ~0,00 EUR

**weekly (Sonntag 20:00 MEZ)**
- Unverändert: nur DB-Auswertung, kein Claude
- Schickt Wochenperformance-Mail
- Kosten: ~0,00 EUR

### Kosten-Übersicht pro Tag
- 2 volle Analyse-Runs (pre_market + midday): ~6,40 EUR
- Position Check: ~0,20 EUR
- Evaluate + Close: ~0,00 EUR
- **Gesamt/Tag: ~6,60 EUR**
- **Gesamt/Monat (500 Ticker): ~145 EUR**
- **Gesamt/Monat (MVP 20 Ticker): ~29 EUR**

---

## Änderung B – Timezone-Handling (Sommer/Winterzeit)

### Problem
GitHub Actions läuft immer in UTC. Cron-Zeiten verschieben sich
bei Zeitumstellung um 1 Stunde.
- Sommerzeit MESZ: UTC+2 → cron '0 12' = 14:00 Berlin ✅
- Winterzeit MEZ:  UTC+1 → cron '0 12' = 13:00 Berlin ❌

### Lösung: Doppelte Crons + TZ-Prüfung in Bash

Jeder Run-Type bekommt zwei Cron-Einträge in analyze.yml:
```yaml
schedule:
  # pre_market 14:00 Berlin (Sommer UTC+2 / Winter UTC+1)
  - cron: '0 12 * * 1-5'   # Sommer
  - cron: '0 13 * * 1-5'   # Winter

  # evaluate 15:00 Berlin
  - cron: '0 13 * * 1-5'   # Sommer
  - cron: '0 14 * * 1-5'   # Winter

  # midday 16:15 Berlin
  - cron: '15 14 * * 1-5'  # Sommer
  - cron: '15 15 * * 1-5'  # Winter

  # position_check 17:30 Berlin
  - cron: '30 15 * * 1-5'  # Sommer
  - cron: '30 16 * * 1-5'  # Winter

  # close 22:30 Berlin
  - cron: '30 20 * * 1-5'  # Sommer
  - cron: '30 21 * * 1-5'  # Winter

  # weekly Sonntag 20:00 Berlin
  - cron: '0 18 * * 0'     # Sommer
  - cron: '0 19 * * 0'     # Winter
```

Bash-Skript zur Run-Type-Bestimmung (IMMER TZ="Europe/Berlin"):
```bash
HOUR=$(TZ="Europe/Berlin" date +%H)
MIN=$(TZ="Europe/Berlin" date +%M)
DOW=$(TZ="Europe/Berlin" date +%u)

if [ "$DOW" = "7" ] && [ "$HOUR" = "20" ]; then T="weekly"
elif [ "$HOUR" = "15" ] && [ "$MIN" -ge "0" ] && [ "$MIN" -lt" 30" ]; then T="evaluate"
elif [ "$HOUR" = "14" ] && [ "$MIN" -lt "30" ]; then T="pre_market"
elif [ "$HOUR" = "16" ] && [ "$MIN" -ge "10" ]; then T="midday"
elif [ "$HOUR" = "17" ] && [ "$MIN" -ge "30" ]; then T="position_check"
elif [ "$HOUR" = "22" ] || [ "$HOUR" = "21" ]; then T="close"
else T="close"; fi
```

Python-Code: IMMER `zoneinfo.ZoneInfo("Europe/Berlin")` verwenden:
```python
from zoneinfo import ZoneInfo
from datetime import datetime
BERLIN = ZoneInfo("Europe/Berlin")
now = datetime.now(BERLIN)
```

---

## Änderung C – Provider-Architektur

### Neue Hierarchie

**Preisdaten (OHLCV, täglich):**
- Primär: Capital.com Demo API
  - Base URL: https://demo-api-capital.backend-capital.com/
  - Package: capitalcom-python (PyPI)
  - ENV: CAPITAL_COM_API_KEY, CAPITAL_COM_PASSWORD
  - Kapazität: kostenlos, 600 Calls/Min
  - Zuständig für: Aktien, Rohstoffe, Crypto, Pre-Market-Kurs
- Fallback: yfinance (wenn Capital.com nicht verfügbar)

**Fundamentaldaten (wöchentlich gecacht):**
- Primär: Finnhub Free
  - ENV: FINNHUB_API_KEY
  - Felder: pe_ratio, forward_pe, market_cap_b, debt_equity,
    sector, analyst_upside, consensus
  - Cache-TTL: 7 Tage (Tabelle fundamentals_cache)
  - Im Run aus DB lesen, nicht live abrufen
  - Nur neu laden wenn > 7 Tage alt
  - Ziel: 1-2 API-Calls/Ticker/Woche statt 3-4/Tag

**Earnings-Kalender (wöchentlich gecacht):**
- Primär: Finnhub Free
  - Felder: days_to_next, last_beat_pct
  - Gleiche Cache-Logik wie Fundamentals

**Alpha Vantage:** komplett entfernen aus allen Docs

### Neue Datei: src/providers/capital_provider.py
Klasse CapitalComProvider(DataProvider):
- get_price_history(ticker, days) → pd.DataFrame OHLCV
- get_ohlc_after(ticker, start_date, end_date) → pd.DataFrame
- get_premarket_price(ticker) → float | None
- get_open_positions() → list[dict]
- get_closed_positions(date) → list[dict]
- get_fundamentals() → {} (nicht zuständig)
- get_earnings_calendar() → {} (nicht zuständig)

Ticker-Mapping Capital.com:
- SP500-Ticker: direkt übergeben
- Gold="GOLD", Silber="SILVER", Öl="CRUDE_OIL"
- BTC="BITCOIN", ETH="ETHEREUM", SOL="SOLANA", XRP="XRP"

### Neue ENV-Variablen (in .env.example + CLAUDE.md ergänzen)
```
CAPITAL_COM_API_KEY=
CAPITAL_COM_PASSWORD=
```

---

## Änderung D – Datenabruf-Strategie Phase 1

### Bisherige Strategie (falsch)
Täglich 90 Tage OHLCV fetchen → ineffizient, zu viele API-Calls

### Neue Strategie

**Einmalig Setup (Sprint 2):**
historical_loader.py lädt 3-Jahres-Historie via Capital.com
→ in price_history Tabelle speichern

**Täglich (jeder Run):**
Nur den neuen Tag abrufen (1 Candle pro Ticker)
→ in price_history anhängen (INSERT OR IGNORE)

**Indikatoren berechnen:**
Aus DB lesen (letzte 200 Tage für SMA200, letzte 90 für Rest)
→ Indikatoren berechnen → in technical_indicators speichern
→ Täglich jeden Snapshot speichern (für Lernmodul + späteres ML)

### Täglich gespeicherte OHLCV-Felder
ticker, date, open, high, low, close, volume,
premarket_price (neu, nullable), source

### Täglich gespeicherte Indikatoren
ticker, date, rsi_14, macd_signal, atr_pct, bb_position,
above_sma20, above_sma50, above_sma200, volume_ratio,
intraday_range_pct

### Warum Indikatoren täglich speichern?
1. Lernmodul (Sprint 3): Muster erkennen welche Indikatoren
   bei korrekten Vorhersagen hoch/niedrig waren
2. ML-Projekt (später, separates Projekt): sauberer täglicher
   Feature-Snapshot pro Ticker als Grundlage

---

## Änderung E – CFD-Kurzfrist-Kalibrierung

### config.py Änderungen
```python
SP500_MIN_ATR_PCT = 2.0        # war 0.8
MAX_HOLD_DAYS = 5              # max Haltedauer wenn kein TP/SL
HOLD_TARGET = "intraday"       # Primärziel
```

### Intraday-first Logik
- Jede Vorhersage gilt für den aktuellen Tag (Intraday-Primärziel)
- Am nächsten Tag wird eine neue unabhängige Vorhersage erstellt
- Kein Carry-over von Vorhersagen zwischen Tagen
- TP/SL auf Tagesbasis kalibriert

### Haltezeit-Logik wenn TP/SL nicht getroffen
- Täglich via Tages-High/Low prüfen
- Long:  High >= TP → tp_hit | Low <= SL → sl_hit
- Short: Low <= TP → tp_hit | High >= SL → sl_hit
- Tag 5: Zwangsschluss zum Schlusskurs (exit_reason="timeout_forced")
- Beides an einem Tag getroffen → pessimistic_overlap → SL gewertet

### Neue DB-Felder predictions
```sql
hold_day INTEGER DEFAULT 0       -- aktueller Haltetag, täglich +1
extended_hold BOOLEAN DEFAULT 0  -- True ab Tag 2
exit_reason TEXT                 -- tp_hit/sl_hit/timeout_forced/pessimistic_overlap
```

### Neue DB-Felder outcomes
```sql
hold_day INTEGER
extended_hold BOOLEAN
exit_reason TEXT
```

### Prompts anpassen
In allen prompts/*.txt ergänzen:
"Analysiere ausschließlich was heute preisrelevant ist (Intraday-Horizont).
TP und SL müssen innerhalb eines Handelstages erreichbar sein.
Katalysatoren müssen heute oder vorbörslich morgen wirken."

### E-Mail: Spalte Haltezeit
In Long/Short-Tabelle: Spalte "Haltezeit" ergänzen
Wert: immer "Intraday (max. 5T)"
Overnight-Warnung ⚠ im Footer wenn offene Trades aus Vortag existieren

---

## Änderung F – E-Mail: "Was heute zählt"-Box

### Neue Funktion: generate_daily_briefing()
```python
def generate_daily_briefing(
    trend_context: dict,
    policy_context: dict
) -> list[str]:
    """Generiert 4-6 Bulletpoints für die Was-heute-zählt-Box."""
```

### Logik
- Top-2 Trends mit strength >= 7 → je 1 Bullet
- Policy-Risk "high" → 1 Bullet mit konkretem Event
- Stärkster Beneficiary-Ticker → 1 Bullet
- Nächster Earnings-Katalysator → 1 Bullet

### Position in E-Mail
Ganz oben, vor allen anderen Sektionen

### Design
Dunkler Hintergrund (#1a1a2e), weiße Schrift
Überschrift: "Was heute zählt"
Format: Bulletpoints mit • Zeichen, max. 1 Zeile je Punkt

---

## Änderung G – Capital.com eigene Positionen (GET)

### position_check Run
Capital.com API Endpoints (nur GET, kein Trading):
- GET /api/v1/positions          → offene Positionen
- GET /api/v1/history/activity   → heute geschlossene Trades

### Felder je Position
ticker, direction (buy/sell → long/short), entry_price,
current_price, tp_price, sl_price, profit_loss, status

### Abgleich-Logik
- Vorhersage + echter Trade → echten Exit-Grund verwenden (reales Lernen)
- Vorhersage ohne Trade → simuliert weiterführen wie bisher
- Trade ohne Vorhersage → ignorieren

### SIMULATION_ONLY bleibt True
Niemals Orders platzieren. Nur lesende GET-Aufrufe.

---

## Neue DB-Tabelle: fundamentals_cache

```sql
CREATE TABLE IF NOT EXISTS fundamentals_cache (
    ticker TEXT NOT NULL,
    fetched_date TEXT NOT NULL,
    pe_ratio REAL,
    forward_pe REAL,
    market_cap_b REAL,
    debt_equity REAL,
    sector TEXT,
    analyst_upside REAL,
    consensus TEXT,
    UNIQUE(ticker)
);
```

---

## Sprint-Zuordnung

### Sprint 1 Fixes (am bestehenden Code)
- ATR-Mindest auf 2.0 setzen
- Intraday-Fokus in allen Prompts
- "Was heute zählt"-Box in E-Mail (generate_daily_briefing)
- Close-Run vereinfachen: kein Claude, kein Mail
- Timezone-Fix: TZ="Europe/Berlin" in analyze.yml + zoneinfo in Python
- Doppelte Cron-Einträge für Sommer/Winterzeit

### Sprint 2 Neubauten
- capital_provider.py (inkl. get_open_positions, get_closed_positions,
  get_premarket_price)
- fundamentals_cache Tabelle + Finnhub-Caching (7-Tage TTL)
- DB-Incremental-Update: täglich nur neuen Tag fetchen
- position_check Run-Type in main.py
- historical_loader.py (3-Jahres Pull via Capital.com)
- 500 Ticker Skalierung

### Sprint 3 (unverändert)
- Learning Module mit dynamischen Schwellwerten
- Prompt-Optimizer mit A/B-Testing
- Extended-Hold-Performance Tracking

---

## Was in jedem Doc geändert werden soll

### docs/SPECIFICATION.md
- Version auf 5.0, Datum 2026-05-21
- Tech Stack: Capital.com ergänzen, Alpha Vantage entfernen
- Alle Änderungen A-G einarbeiten
- Run-Types Übersicht mit Kosten aktualisieren
- Neue DB-Tabelle fundamentals_cache ergänzen
- Provider-Hierarchie aktualisieren

### docs/ARCHITECTURE.md
- Provider-Hierarchie: Capital.com → Finnhub → yfinance
- capital_provider.py als neues Modul dokumentieren
- fundamentals_cache Tabelle ergänzen
- Run-Types mit Kosten aktualisieren
- Timezone-Handling dokumentieren

### docs/WORKFLOW.md
- Tagesablauf mit allen 6 Run-Types + Kosten
- Doppelte Cron-Einträge dokumentieren
- Timezone-Handling mit TZ="Europe/Berlin" erklären
- Capital.com Position Check Ablauf dokumentieren

### CLAUDE.md
- Neue ENV-Variablen: CAPITAL_COM_API_KEY, CAPITAL_COM_PASSWORD
- Neuer Befehl: python main.py --run-type position_check
- Provider-Reihenfolge: Capital.com → Finnhub → yfinance
- Sprint-Übersicht aktualisieren (Sprint 1 Fix / Sprint 2 / Sprint 3)

### docs/superpowers/specs/2026-05-19-shares-future-mvp-design.md
- Sprint-1-Fix-Scope ergänzen (Änderungen A partial, B, D, E, F)
- Sprint-2-Scope ergänzen (Änderungen A partial, C, D partial, G)
- Neue Tabellen und Provider dokumentieren
- Kosten-Übersicht aktualisieren

### docs/superpowers/plans/ – NEUE DATEI erstellen
Dateiname: 2026-05-21-sprint2-plan1-capital-provider-db-incremental.md

Inhalt im Superpowers-Format (mit Checkboxen wie bestehende Pläne):
Sprint-2-Implementierungsplan für:
1. capital_provider.py
   - CapitalComProvider Klasse
   - Demo Base URL: https://demo-api-capital.backend-capital.com/
   - get_price_history, get_ohlc_after, get_premarket_price
   - get_open_positions, get_closed_positions
   - Ticker-Mapping (SP500 direkt, Rohstoffe/Crypto gemappt)
   - Tests: mock Capital.com API responses

2. fundamentals_cache + Finnhub-Caching
   - Neue Tabelle in db.py
   - FinnhubProvider.get_fundamentals() implementieren
   - Cache-Prüfung in data_collector.py (< 7 Tage → aus DB)
   - Tests: Cache-Hit / Cache-Miss

3. DB-Incremental-Update
   - data_collector.py: nur neuen Tag fetchen
   - Indikatoren aus DB berechnen (letzte 200 Tage)
   - historical_loader.py: 3-Jahres Pull via Capital.com
   - Tests: incremental insert, indicator calculation from DB

4. position_check Run-Type
   - main.py: neuer run_type "position_check"
   - Abgleich Vorhersage ↔ echte Position
   - Kurze Status-Mail
   - Tests: mock Capital.com positions response

5. Timezone-Fix
   - analyze.yml: doppelte Crons + TZ="Europe/Berlin" in Bash
   - Alle Python datetime → zoneinfo.ZoneInfo("Europe/Berlin")
   - Tests: freezegun mit Berlin-Timezone

Nach jedem Schritt: pytest tests/ --cov=src --cov-fail-under=80
