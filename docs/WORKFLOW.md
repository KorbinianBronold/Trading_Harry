# Shares_Future – Live Workflow & Operationen

## Overview

Shares_Future läuft täglich auf GitHub Actions mit **4 Cron-Auslösungen** (UTC) und produziert **E-Mails, DB-Backups und Cost-Reports**.

```
┌─────────────────────────────────────────────────────────────────┐
│              DAILY WORKFLOW (Montag–Freitag)                    │
│                                                                  │
│  14:00 UTC  →  pre_market (Phase 0-5)    →  E-Mail 1           │
│  14:15 UTC  →  (Fetch 4h später)                               │
│  14:45 UTC  →  midday (Phase 4a-5, re-score)  →  E-Mail 2      │
│  21:30 UTC  →  close (Phase 0-5, Final)      →  E-Mail 3       │
│                                                                  │
│              EVALUATE (nach 21:30)                              │
│  22:30 UTC  →  evaluate (Walk-Forward Hits)                    │
│                                                                  │
│              WEEKLY (Sonntag 20:00 UTC)                         │
│  20:00 UTC  →  weekly (7-Tage Aggregate)     →  E-Mail 4       │
│                                                                  │
│  RELEASE ASSET DB PERSISTENCE                                  │
│  Nach jedem Run: tracking.db → GitHub Release Asset "db-latest"│
└─────────────────────────────────────────────────────────────────┘
```

---

## Cron-Jobs (in `.github/workflows/analyze.yml`)

### Pre-Market (14:00 UTC = 15:00 CET/CEST)

```bash
python main.py --run-type pre_market --date $(date +%Y-%m-%d)
```

**Zweck:** Vor US-Markt-Open (21:30 CET) erste Analyse.

**Output:**
- Phase 0: Trend-Analyse (Overnight-News)
- Phase 1: Aktuelle yfinance-Daten
- Phase 2-5: Vollständiges Ranking
- E-Mail an `EMAIL_TO` (Sektion: Portfolio → Stocks → Trends → Commodities)
- DB: predictions-Rows für heute schreiben

**Kosten:** ~3.50 EUR (Tendenz: höher wegen Policy-Monitor)

---

### Midday (14:45 UTC = 15:45 CET/CEST)

```bash
python main.py --run-type midday --date $(date +%Y-%m-%d)
```

**Zweck:** 45 Min nach Markt-Open, neue OHLC-Daten, Portfolio-Rebalance.

**Output:**
- Phase 0: Skipped (Cache-Trend von 14:00)
- Phase 1: Frische yfinance-Daten (15 Min. OHLC)
- Phase 4a: Portfolio-Check (offene Positionen HALTEN/SCHLIESSEN/ANPASSEN)
- Phase 4-5: Update Rankings mit neuen P&Ls
- E-Mail: Portfolio-Update

**Kosten:** ~2.50 EUR (kein Policy-Monitor, kürzere Deep-Analysis)

---

### Close (21:30 UTC = 22:30 CET = 16:30 EDT)

```bash
python main.py --run-type close --date $(date +%Y-%m-%d)
```

**Zweck:** **Wichtigste des Tages.** Final Analysis für den nächsten Handelstag.

**Output:**
- Phase 0-5: Vollständig wie pre_market
- Policy-Monitor: Fresh, post-US-Close News (Tariffs, Fed, Geopolitik)
- Deep-Analysis: Top 80 neu bewertet
- Portfolio-Check: Alle offenen Positionen evaluiert
- E-Mail: Final Daily Report

**Kosten:** ~3.50 EUR

---

### Evaluate (22:30 UTC, täglich)

```bash
python main.py --run-type evaluate --date $(date +%Y-%m-%d)
```

**Zweck:** Walk-Forward OHLC-Hit-Check für Setups aus gestrigen `close`-Run.

**Logik:**
1. Load db.predictions where date < today AND status='open'
2. Fetch OHLC [pred.date → today] via yfinance
3. Walk 1-3 Bars: TP-Hit? SL-Hit? Overlap? Timeout? Missing-Data?
4. Atomisch: db.outcomes schreiben + db.predictions.status update
5. Berechne Profit/Loss (CFD Simulation @ 5:1 Hebel, 500 EUR Margin)

**Output:**
- db.outcomes: exit_reason, exit_price, days_to_close, p&l_eur
- Cost Tracking: 0 EUR (nur DB-Queries)

**E-Mail:** Kein E-Mail (evaluate ist Background-Job)

---

### Weekly (Sonntag 20:00 UTC)

```bash
python main.py --run-type weekly --date $(date +%Y-%m-%d)
```

**Zweck:** 7-Tage-Summary + Long/Short Statistik.

**Logik:**
1. Load db.outcomes from last 7 days
2. Aggregate by direction: long_correct/long_total, short_correct/short_total
3. Sum profit_loss_eur (all positions)
4. Win rate, Sharpe-like metric

**Output:**
- E-Mail: Weekly Summary
  - 7-Tage Win-Rate (Long & Short getrennt)
  - Top 3 Winners / Top 3 Losers (letzte Woche)
  - Cumulative P&L (EUR)
  - Cost Summary (API + Email)
  - Trends für nächste Woche

**Kosten:** ~0.00 EUR (nur DB-Queries)

---

## GitHub Secrets Setup (Einmalig)

In GitHub Repo Settings → Secrets and variables → Actions:

| Secret | Value | Quelle |
|--------|-------|--------|
| `ANTHROPIC_API_KEY` | sk-ant-... | https://console.anthropic.com |
| `SENDGRID_API_KEY` | SG.xxx... | https://app.sendgrid.com/settings/api_keys |
| `EMAIL_TO` | korbinian.bronold@gmail.com | Deine E-Mail |
| `EMAIL_FROM` | noreply@shares-future.com | SendGrid Verified Sender |

**NICHT:** FINNHUB_API_KEY (wird nicht benutzt, nur yfinance + Paid API in Sprint 2)

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

Jeder Run hat ein **Hard Cap: 4 EUR**.

**Kostenverteilung:**
- Phase 0 (Trend): 0.20 EUR
- Phase 1 (Daten): 0.00 EUR
- Phase 2 (Quick-Filter): 0.15 EUR
- Phase 3 (Policy + Deep): 2.50–3.00 EUR ← **Biggest cost**
- Phase 3b (Commodities): 0.35 EUR
- Phase 4a (Portfolio): 0.20 EUR
- Phase 4 (Ranking): 0.00 EUR
- Phase 5 (Email): 0.00 EUR

**Total per Run:** 3.40–3.85 EUR (typical)

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

## Tagesablauf (Beispiel: Montag 2026-05-20)

```
14:00 UTC (15:00 CEST)
  ↓
[GitHub Actions trigger: analyze.yml → pre_market]
  ↓
main.py --run-type pre_market --date 2026-05-20
  Phase 0: Trend-Analyse (über Nacht News)
  Phase 1: yfinance Daten für 500 Tickers
  Phase 2: Quick-Filter Top 80
  Phase 3: Policy-Monitor + Deep-Analysis
  Phase 3b: Commodities/Crypto
  Phase 4a: Portfolio-Check (offene von Fr/Do)
  Phase 4: Ranking Top-10
  Phase 5: HTML-Render + SendGrid
  ↓
  tracking.db: predictions-Rows schreiben
  GitHub Release: db-latest aktualisieren
  E-Mail: Ausgang 14:10 UTC
  Cost: 3.50 EUR

---

14:45 UTC (15:45 CEST)
  ↓
[GitHub Actions trigger: analyze.yml → midday]
  ↓
main.py --run-type midday --date 2026-05-20
  Phase 0: Skipped (Trend-Cache)
  Phase 1: Frische OHLC (seit 14:00)
  Phase 4a: Portfolio-Check (neue Prices)
  Phase 5: Email (Rebalance-Empfehlungen)
  ↓
  Cost: 2.50 EUR
  E-Mail: Ausgang 14:55 UTC

---

21:30 UTC (22:30 CEST)
  ↓
[GitHub Actions trigger: analyze.yml → close]
  ↓
main.py --run-type close --date 2026-05-20
  Phase 0-5: Full Analysis (Post-US-Close)
  ↓
  Cost: 3.50 EUR
  E-Mail: Ausgang 21:40 UTC
  tracking.db: Updated (DB Release Asset)

---

22:30 UTC (23:30 CEST)
  ↓
[GitHub Actions trigger: analyze.yml → evaluate]
  ↓
main.py --run-type evaluate --date 2026-05-20
  Load db.predictions[date < 2026-05-20 & status='open']
  For each: Fetch OHLC, Walk-Forward Hit-Check
  Update db.outcomes (exit_reason, exit_price, p&l_eur)
  ↓
  Cost: 0.00 EUR
  No E-Mail (Background Job)

---

Sonntag 20:00 UTC (21:00 CEST)
  ↓
[GitHub Actions trigger: analyze.yml → weekly]
  ↓
main.py --run-type weekly --date 2026-05-26
  Load db.outcomes[last 7 days]
  Aggregate: Win-Rate, P&L, Cost
  ↓
  Cost: 0.00 EUR
  E-Mail: Weekly Summary (1 E-Mail pro Woche)
```

---

## Sprint 1 Definition of Done (Checklist)

Das MVP ist erst **production-ready**, wenn folgende Kriterien erfüllt sind:

**Code-Seite (✅ abgehakt):**
- [ ] ✅ 159 Unit+Integration Tests grün
- [ ] ✅ 89.62% Code Coverage
- [ ] ✅ Alle 13 Plan-3-Tasks implementiert + reviewed
- [ ] ✅ Guardrails für CFD-Kurzfristfokus (hold_days ≤ 3, intraday_range ≥ 1%)
- [ ] ✅ Cost-Tracker mit Hard-Cap (4 EUR)
- [ ] ✅ Walk-Forward Evaluator (4 exit reasons)
- [ ] ✅ E-Mail mit 4 Sektionen
- [ ] ✅ GitHub Actions Workflows (test.yml + analyze.yml)

**Live-Seite (⏳ ausstehend):**
- [ ] GitHub Secrets konfiguriert (ANTHROPIC_API_KEY, SENDGRID_API_KEY, EMAIL_TO, EMAIL_FROM)
- [ ] Erste `workflow_dispatch` Auslösung auf analyze.yml erfolgreich
- [ ] 3 aufeinanderfolgende Werktage à 4 Runs (pre_market, midday, close, evaluate) laufen
- [ ] 1 Weekly-Mail generiert + versendet (Sonntag 20:00 UTC)
- [ ] Tracking DB (`db-latest` Release Asset) überlebt alle Runs
- [ ] E-Mails ankommen in EMAIL_TO (täglich + wöchentlich)
- [ ] Kosten pro Run ≤ 4 EUR (Cost-Tracker in db verifizieren)
- [ ] Keine unerwarteten Fehler in GitHub Actions Logs

**Akzeptanzkriterien:**
- Mindestens 1 Woche durchgehend fehlerfreier Betrieb
- Evaluator: ≥ 3 Walk-Forward Outcomes (tp_hit, sl_hit, oder timeout)
- Learning Module ready für Sprint 2 (aber noch nicht aktiv)

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
   - Sonnet + web_search × 80 Calls = 2.50–3.00 EUR allein
   - Wenn auch Policy-Monitor + Commodities + Portfolio-Check: Kann 4 EUR überschreiten

2. **Lösungen für Sprint 2:**
   - Reduce Top-N (statt 80, nur 50)
   - Weaker Claude Model für Phase 3 (Sonnet → Haiku, aber dann Quality leidet)
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

2. **Timezone Check:** UTC in `.github/workflows/analyze.yml`
   - `14:00 * * 1-5` = Montag–Freitag, 14:00 UTC
   - Wenn du CET bist: 14:00 UTC = 15:00 CEST (Sommer)

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
sqlite3 tracking.db "SELECT * FROM cost_tracking WHERE date='2026-05-20' ORDER BY phase DESC;"
```

**Claude API Logs:**
- Token usage: `cost_tracker.summary()`
- Web-search Calls: `result.web_search_calls`

---

## Next Steps (Sprint 2)

1. **Paid API Aktivierung** (Polygon/FMP)
   - 500 SP500 Tickers (statt MVP-Subset)
   - Historischer 3-Jahres-Pull (einmalig)
   - Monthly Auto-Update

2. **Learning Module** (Long/Short getrennt)
   - Prompt-Optimizer A/B-Testing
   - Gewichtungs-Optimierung basierend auf Outcomes

3. **Extended Weekly Mail**
   - Multi-week Trends
   - Sector Rotation Tracking
   - Cost Analysis per Phase

---

Siehe auch:
- **`docs/SPECIFICATION.md`** – Technische Details
- **`docs/ARCHITECTURE.md`** – Module & Design
- **`CLAUDE.md`** – Developer Guidelines
- **`.github/workflows/`** – YAML-Quelle der Wahrheit

