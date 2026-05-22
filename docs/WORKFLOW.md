# Shares_Future – Live Workflow & Operationen

## Overview

Shares_Future läuft täglich auf GitHub Actions mit **6 Run-Types** (Berliner Zeit) und produziert **E-Mails, DB-Backups und Cost-Reports**.

```
┌──────────────────────────────────────────────────────────────────────┐
│              DAILY WORKFLOW (Montag–Freitag)                         │
│                                                                       │
│  14:00 Berlin  →  pre_market      (~3,20 EUR)  →  E-Mail 1          │
│  15:00 Berlin  →  evaluate        (~0,00 EUR)  →  kein Mail          │
│  16:15 Berlin  →  midday          (~3,20 EUR)  →  E-Mail 2          │
│  17:30 Berlin  →  position_check  (~0,20 EUR)  →  Status-Mail (NEU) │
│  22:30 Berlin  →  close           (~0,00 EUR)  →  kein Mail          │
│                                                                       │
│              WEEKLY (Sonntag 20:00 Berlin)                           │
│  20:00 Berlin  →  weekly          (~0,00 EUR)  →  E-Mail 3          │
│                                                                       │
│  RELEASE ASSET DB PERSISTENCE                                        │
│  Nach jedem Run: tracking.db → GitHub Release Asset "db-latest"     │
└──────────────────────────────────────────────────────────────────────┘
```

**Kosten/Tag:** ~6,60 EUR | **Kosten/Monat (500 Ticker):** ~145 EUR | **MVP (20 Ticker):** ~29 EUR

---

## Cron-Jobs (in `.github/workflows/analyze.yml`)

Jeder Run-Type hat **zwei Cron-Einträge** (Sommer UTC+2 / Winter UTC+1), damit die Berliner Zeit das ganze Jahr stimmt.

```yaml
schedule:
  # pre_market 14:00 Berlin
  - cron: '0 12 * * 1-5'   # Sommer (MESZ, UTC+2)
  - cron: '0 13 * * 1-5'   # Winter (MEZ,  UTC+1)

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

**Bash-Logik zur Run-Type-Bestimmung** (IMMER `TZ="Europe/Berlin"`):

```bash
HOUR=$(TZ="Europe/Berlin" date +%H)
MIN=$(TZ="Europe/Berlin" date +%M)
DOW=$(TZ="Europe/Berlin" date +%u)

if [ "$DOW" = "7" ] && [ "$HOUR" = "20" ]; then T="weekly"
elif [ "$HOUR" = "15" ] && [ "$MIN" -ge "0" ] && [ "$MIN" -lt "30" ]; then T="evaluate"
elif [ "$HOUR" = "14" ] && [ "$MIN" -lt "30" ]; then T="pre_market"
elif [ "$HOUR" = "16" ] && [ "$MIN" -ge "10" ]; then T="midday"
elif [ "$HOUR" = "17" ] && [ "$MIN" -ge "30" ]; then T="position_check"
elif [ "$HOUR" = "22" ] || [ "$HOUR" = "21" ]; then T="close"
else T="close"; fi
```

**Python-Code:** IMMER `zoneinfo.ZoneInfo("Europe/Berlin")` verwenden:

```python
from zoneinfo import ZoneInfo
from datetime import datetime
BERLIN = ZoneInfo("Europe/Berlin")
now = datetime.now(BERLIN)
```

---

## Pre-Market (14:00 Berlin, ~3,20 EUR)

```bash
python main.py --run-type pre_market --date $(TZ="Europe/Berlin" date +%Y-%m-%d)
```

**Zweck:** Erste vollständige Analyse des Tages vor US-Markt-Open (15:30 Berlin).

**Pipeline:**
- Phase 0: Trend-Analyse (Overnight-News, 1× Sonnet + web_search)
- Phase 1: Capital.com OHLCV (1 Bar täglich) + Indikatoren aus DB
- Phase 1: Vorbörslicher Kurs via Capital.com `get_premarket_price()` falls verfügbar
- Phase 2–4: Vollständiges Ranking (Quick-Filter → Deep-Analysis → Portfolio-Check → Ranking)
- Phase 5: HTML-Mail (Portfolio → Stocks → Trends → Commodities)

**Output:**
- E-Mail an `EMAIL_TO`
- DB: predictions-Rows für heute
- DB: price_history + technical_indicators Update

**Kosten:** ~3,20 EUR

---

## Evaluate (15:00 Berlin, ~0,00 EUR)

```bash
python main.py --run-type evaluate --date $(TZ="Europe/Berlin" date +%Y-%m-%d)
```

**Zweck:** Walk-Forward OHLC-Hit-Check für gestrige und ältere offene Setups.

**Logik:**
1. Lade `db.predictions` where `date < today` AND `status='open'`
2. Hole Tages-High/Low via Capital.com (1 Candle)
3. Walk-Forward Bar für Bar (max 5 Bars):
   - Long: Low ≤ SL → sl_hit; High ≥ TP → tp_hit
   - Short: High ≥ SL → sl_hit; Low ≤ TP → tp_hit
   - Beide an einem Tag → pessimistic_overlap → SL gewertet
   - Tag 5 ohne Hit → timeout_forced (Zwangsschluss zum Close)
4. Atomisch: `db.outcomes` schreiben + `db.predictions.status` update
5. Berechne P/L (CFD Simulation @ 5:1 Hebel, 500 EUR Margin)

**Output:**
- `db.outcomes`: exit_reason, exit_price, days_to_close, hold_day, extended_hold, p&l_eur
- Kein E-Mail (Background-Job)

**Kosten:** ~0,00 EUR

---

## Midday (16:15 Berlin, ~3,20 EUR)

```bash
python main.py --run-type midday --date $(TZ="Europe/Berlin" date +%Y-%m-%d)
```

**Zweck:** 45 Min nach US-Eröffnung (15:30 Berlin). Eröffnungsvolatilität abgeklungen, frische OHLC-Daten.

**Pipeline:** Identisch zu pre_market — vollständige Phase 0–4 Pipeline.

**Output:**
- E-Mail an `EMAIL_TO` (Midday-Update)
- DB: aktualisierte predictions + Indikatoren

**Kosten:** ~3,20 EUR

---

## Position Check (17:30 Berlin, ~0,20 EUR) — NEU

```bash
python main.py --run-type position_check --date $(TZ="Europe/Berlin" date +%Y-%m-%d)
```

**Zweck:** Abgleich eigener Capital.com-Positionen mit heutigen Vorhersagen.

**Logik:**
1. Capital.com `GET /api/v1/positions` → offene Trades abrufen (nur lesend)
2. Abgleich: Vorhersage ↔ echter Trade
   - Vorhersage + echter Trade → echten Exit-Grund verwenden
   - Vorhersage ohne Trade → simuliert weiterführen
   - Trade ohne Vorhersage → ignorieren
3. Kurzer Claude-Call (1× Sonnet): hat sich etwas wesentlich verändert?
4. Status-Mail: ✅ auf Kurs / ⚠ nahe SL / ❌ Signal gefallen

**Invariante:** `SIMULATION_ONLY = True` — niemals Orders platzieren, nur GET-Aufrufe.

**Output:**
- Kurze Status-Mail
- DB: `position_recommendations` Update

**Kosten:** ~0,20 EUR

---

## Close (22:30 Berlin, ~0,00 EUR) — vereinfacht

```bash
python main.py --run-type close --date $(TZ="Europe/Berlin" date +%Y-%m-%d)
```

**Zweck:** NUR Datenpflege nach US-Close. Kein Claude-Call, kein Mail.

**Logik:**
1. Capital.com Schlusskurs + Tages-High + Tages-Low abrufen (1 Candle pro Ticker)
2. In `price_history` speichern (INSERT OR IGNORE)
3. Finaler TP/SL-Check für noch offene Positionen (`evaluate_open_predictions`)
4. `cleanup_old_data()` (90-Tage news_summaries, 180-Tage trend_analyses, etc.)

**Output:**
- Keine E-Mail
- DB: aktualisierte price_history + outcomes
- DB Release Asset: tracking.db hochladen

**Kosten:** ~0,00 EUR

---

## Weekly (Sonntag 20:00 Berlin, ~0,00 EUR)

```bash
python main.py --run-type weekly --date $(TZ="Europe/Berlin" date +%Y-%m-%d)
```

**Zweck:** 7-Tage-Summary + Long/Short Statistik.

**Logik:**
1. Lade `db.outcomes` der letzten 7 Tage
2. Aggregiere nach direction: long_correct/long_total, short_correct/short_total
3. Summiere profit_loss_eur (alle Positionen)
4. Win-Rate, Sharpe-like Metric

**Output:**
- E-Mail: Weekly Summary
  - 7-Tage Win-Rate (Long & Short getrennt)
  - Top 3 Winners / Top 3 Losers (letzte Woche)
  - Kumulatives P&L (EUR)
  - Cost Summary (API + Email)
  - Trends für nächste Woche

**Kosten:** ~0,00 EUR (nur DB-Queries)

---

## GitHub Secrets Setup (Einmalig)

In GitHub Repo Settings → Secrets and variables → Actions:

| Secret | Value | Quelle |
|--------|-------|--------|
| `ANTHROPIC_API_KEY` | sk-ant-... | https://console.anthropic.com |
| `SENDGRID_API_KEY` | SG.xxx... | https://app.sendgrid.com/settings/api_keys |
| `EMAIL_TO` | korbinian.bronold@gmail.com | Deine E-Mail |
| `EMAIL_FROM` | noreply@shares-future.com | SendGrid Verified Sender |
| `CAPITAL_COM_API_KEY` | ... | Capital.com Demo Account |
| `CAPITAL_COM_PASSWORD` | ... | Capital.com Demo Account |
| `FINNHUB_API_KEY` | ... | https://finnhub.io |

---

## Release-Asset DB-Persistenz

Nach jedem erfolgreichen Run wird `tracking.db` automatisch als Release-Asset gespeichert:

```bash
# In analyze.yml (Step: Upload DB to Release)
gh release upload db-latest tracking.db \
  --clobber \
  --repo ${{ github.repository }}
```

**Warum?**
- GitHub Actions-Runner hat ephemeres Filesystem (nur 1 Run)
- Nach Run → Cleanup
- DB muss zwischen Runs persistent sein
- Release-Asset = permanente Speicherung

**Backup-Logik:**
1. First run: `gh release create db-latest`
2. Subsequent runs: `gh release upload db-latest --clobber`

**Zugriff:**
```bash
# Lokal die neueste DB pullen
gh release download db-latest --pattern "tracking.db"
```

---

## Cost Tracking & Cap

Jeder Analyse-Run hat ein **Hard Cap: 4 EUR**.

**Kostenverteilung pro Analyse-Run (pre_market / midday):**
- Phase 0 (Trend): ~0,20 EUR
- Phase 1 (Daten): ~0,00 EUR
- Phase 2 (Quick-Filter): ~0,15 EUR
- Phase 3 (Policy + Deep): ~2,50–3,00 EUR ← **Größter Posten**
- Phase 3b (Commodities): ~0,35 EUR
- Phase 4a (Portfolio): ~0,20 EUR
- Phase 4 (Ranking): ~0,00 EUR
- Phase 5 (Email): ~0,00 EUR

**Total pro Analyse-Run:** ~3,20 EUR (typisch)

**Tageskosten gesamt:** ~6,60 EUR (2 Analyse-Runs + position_check + stille Runs)

**Wenn Cap überschritten:**
```python
try:
    run_pipeline(cost_tracker)
except CostCapExceeded as e:
    cost_tracker.aborted_at_phase = "policy_monitor"  # placeholder
    cost_summary["aborted_at_phase"] = "policy_monitor"
    send_partial_email(cost_summary)  # Still send, with warning bar
    log.error("Cost cap exceeded, partial email sent")
```

**E-Mail Warning:** Wenn `aborted_at_phase` gesetzt, HTML zeigt rotes Banner:
```
⚠️  RUN ABORTED: Cost cap hit at policy_monitor phase.
    Check cost_tracking table for details.
    Next run continues tomorrow.
```

---

## Tagesablauf (Beispiel: Montag 2026-05-25, Berliner Zeit)

```
14:00 Berlin
  ↓
[GitHub Actions trigger: analyze.yml → pre_market]
  ↓
main.py --run-type pre_market --date 2026-05-25
  Phase 0: Trend-Analyse (Overnight-News)
  Phase 1: Capital.com OHLCV für 500 Tickers + premarket_price
  Phase 2: Quick-Filter Top 80
  Phase 3: Policy-Monitor + Deep-Analysis
  Phase 3b: Commodities/Crypto
  Phase 4a: Portfolio-Check (offene von Fr/Do)
  Phase 4: Ranking Top-10
  Phase 5: HTML-Render + SendGrid
  ↓
  tracking.db: predictions-Rows schreiben
  GitHub Release: db-latest aktualisieren
  E-Mail: Ausgang ~14:10 Berlin
  Cost: ~3,20 EUR

---

15:00 Berlin
  ↓
[GitHub Actions trigger: analyze.yml → evaluate]
  ↓
main.py --run-type evaluate --date 2026-05-25
  Lade db.predictions[date < 2026-05-25 & status='open']
  For each: Hole OHLC, Walk-Forward Hit-Check (max 5 Bars)
  Update db.outcomes (exit_reason, exit_price, hold_day, p&l_eur)
  ↓
  Cost: 0,00 EUR
  Kein Mail (Background Job)

---

16:15 Berlin
  ↓
[GitHub Actions trigger: analyze.yml → midday]
  ↓
main.py --run-type midday --date 2026-05-25
  Phase 0–4: Full Analysis (45 Min nach US-Open)
  ↓
  Cost: ~3,20 EUR
  E-Mail: Ausgang ~16:25 Berlin

---

17:30 Berlin
  ↓
[GitHub Actions trigger: analyze.yml → position_check]
  ↓
main.py --run-type position_check --date 2026-05-25
  Capital.com GET /positions → offene Trades
  Abgleich Vorhersage ↔ echter Trade
  Claude: Signal noch gültig?
  Status-Mail senden
  ↓
  Cost: ~0,20 EUR
  Status-Mail: Ausgang ~17:35 Berlin

---

22:30 Berlin
  ↓
[GitHub Actions trigger: analyze.yml → close]
  ↓
main.py --run-type close --date 2026-05-25
  Capital.com Schlusskurs + High + Low für alle Ticker
  price_history Update (INSERT OR IGNORE)
  evaluate_open_predictions (finaler TP/SL-Check)
  cleanup_old_data()
  ↓
  Cost: 0,00 EUR
  Kein Mail
  tracking.db: Updated (DB Release Asset)

---

Sonntag 20:00 Berlin
  ↓
[GitHub Actions trigger: analyze.yml → weekly]
  ↓
main.py --run-type weekly --date 2026-05-31
  Lade db.outcomes[last 7 days]
  Aggregiere: Win-Rate, P&L, Cost
  ↓
  Cost: 0,00 EUR
  E-Mail: Weekly Summary (1 E-Mail pro Woche)
```

---

## Sprint 1 Definition of Done (Checklist)

Das MVP ist erst **production-ready**, wenn folgende Kriterien erfüllt sind:

**Code-Seite (✅ abgehakt):**
- [x] 159 Unit+Integration Tests grün
- [x] 89.62% Code Coverage
- [x] Alle 13 Plan-3-Tasks implementiert + reviewed
- [x] Guardrails für CFD-Kurzfristfokus (hold_days ≤ 5, intraday_range ≥ 1%)
- [x] Cost-Tracker mit Hard-Cap (4 EUR)
- [x] Walk-Forward Evaluator (4 exit reasons)
- [x] E-Mail mit 4 Sektionen
- [x] GitHub Actions Workflows (test.yml + analyze.yml)

**Live-Seite (ausstehend):**
- [ ] GitHub Secrets konfiguriert (alle 7 Secrets)
- [ ] Erste `workflow_dispatch` Auslösung auf analyze.yml erfolgreich
- [ ] 3 aufeinanderfolgende Werktage à 5 Runs laufen fehlerfrei
- [ ] 1 Weekly-Mail generiert + versendet (Sonntag 20:00 Berlin)
- [ ] Tracking DB (`db-latest` Release Asset) überlebt alle Runs
- [ ] E-Mails ankommen in EMAIL_TO (täglich + wöchentlich)
- [ ] Kosten pro Analyse-Run ≤ 4 EUR (Cost-Tracker in DB verifizieren)
- [ ] Keine unerwarteten Fehler in GitHub Actions Logs

**Akzeptanzkriterien:**
- Mindestens 1 Woche durchgehend fehlerfreier Betrieb
- Evaluator: ≥ 3 Walk-Forward Outcomes (tp_hit, sl_hit, oder timeout)
- Learning Module ready für Sprint 3 (aber noch nicht aktiv)

---

## Troubleshooting

### E-Mail kommt nicht an

1. **GitHub Secret `EMAIL_TO` korrekt?**
   ```bash
   gh secret list --repo KorbinianBronold/Shares_Future | grep EMAIL
   ```

2. **GitHub Secret `SENDGRID_API_KEY` gültig?**
   - Login sendgrid.com → Settings → API Keys
   - Test: `curl -X POST https://api.sendgrid.com/v3/mail/send ... -H "Authorization: Bearer $SENDGRID_API_KEY"`

3. **Spam-Ordner?** SendGrid kann im Spam landen – whitelisten.

4. **Logs in GitHub Actions:**
   ```bash
   gh run view <RUN_ID> --log
   ```

---

### Cost Cap überschritten (Hard Cap 4 EUR)

1. **Phase 3 (Deep-Analysis) ist der Culprit.**
   - Sonnet + web_search × 80 Calls = 2,50–3,00 EUR allein
   - Wenn auch Policy-Monitor + Commodities + Portfolio-Check: Kann 4 EUR überschreiten

2. **Lösungen:**
   - Reduce Top-N (statt 80, nur 50)
   - Web-Search Limit auf 3 pro Call (statt 5)

3. **Current Behavior:**
   - Run continues, truncates Phase 3
   - Partial email sent with warning bar
   - Check cost_tracking table: `SELECT * FROM cost_tracking WHERE aborted_at_phase IS NOT NULL`

---

### DB-Persistierung fehlgeschlagen

1. **Release Asset nicht angelegt?**
   ```bash
   gh release list --repo KorbinianBronold/Shares_Future
   ```

2. **Erste Release muss manuell angelegt werden:**
   ```bash
   gh release create db-latest tracking.db \
     --title "Database Latest" \
     --notes "Automated backup of tracking.db"
   ```

3. **Danach:** `--clobber` Flag überschreibt automatisch.

---

### Cron-Job feuert nicht

1. **GitHub Actions aktiviert?**
   ```bash
   gh workflow list --repo KorbinianBronold/Shares_Future
   ```

2. **Timezone Check:** Doppelte Cron-Einträge in `.github/workflows/analyze.yml`
   - Sommer (MESZ, UTC+2): z.B. `0 12 * * 1-5` = 14:00 Berlin
   - Winter (MEZ, UTC+1): z.B. `0 13 * * 1-5` = 14:00 Berlin
   - Bash-Logik verwendet `TZ="Europe/Berlin"` zur Run-Type-Bestimmung

3. **Force Test (manuell):**
   ```bash
   gh workflow run analyze.yml --ref main
   ```

---

## Logs & Debugging

**GitHub Actions Logs:**
```bash
# Neuester Run
gh run view --repo KorbinianBronold/Shares_Future -L 100

# Spezifischer Job
gh run view <RUN_ID> --log-failed
```

**Lokale Logs (wenn du tracking.db hast):**
```bash
sqlite3 tracking.db "SELECT * FROM cost_tracking WHERE date='2026-05-25' ORDER BY phase DESC;"
```

**Claude API Logs:**
- Token usage: `cost_tracker.summary()`
- Web-search Calls: `result.web_search_calls`

---

## Next Steps (Sprint 2)

1. **Capital.com Provider** (`capital_provider.py`)
   - CapitalComProvider: `get_price_history`, `get_premarket_price`, `get_open_positions`
   - Ticker-Mapping für Rohstoffe + Crypto

2. **DB Incremental Update**
   - Täglich nur 1 Bar fetchen (statt 90 Tage)
   - Indikatoren aus DB berechnen (letzte 200 Tage)
   - `historical_loader.py` für 3-Jahres-Pull via Capital.com (`--all`, `--full-sp500`, `--tickers`)

3. **position_check Run-Type**
   - `main.py`: neuer `run_type = "position_check"`
   - Capital.com GET /positions + Claude 1× + Status-Mail

4. **Timezone-Fix**
   - Doppelte Crons in `analyze.yml`
   - `ZoneInfo("Europe/Berlin")` in allen Python datetime-Berechnungen

5. **500-Ticker Scaling**
   - `USE_FULL_SP500` Flag in config.py
   - `fundamentals_cache` mit 7-Tage TTL

Plan: `docs/superpowers/plans/2026-05-21-sprint2-plan1-capital-provider-db-incremental.md`

---

Siehe auch:
- **`docs/SPECIFICATION.md`** – Technische Details
- **`docs/ARCHITECTURE.md`** – Module & Design
- **`CLAUDE.md`** – Developer Guidelines
- **`.github/workflows/`** – YAML-Quelle der Wahrheit
