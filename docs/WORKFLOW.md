# Shares_Future – Live Workflow & Operationen

**Zuletzt aktualisiert:** 2026-08-09 — vollständig auf den Ist-Stand gezogen.

> ℹ️ Das Produkt heisst **Shares_Future**, das GitHub-Repo **`KorbinianBronold/Trading_Harry`**.
> Ältere Dokumente nannten als Repo fälschlich `Shares_Future` — `gh`-Befehle mit
> `--repo KorbinianBronold/Shares_Future` liefen daher ins Leere.

> Dieses Dokument beschreibt den **Betrieb**: was wann läuft, was es kostet, was zu tun
> ist, wenn etwas klemmt. Der verbindliche Projektstand steht in
> `docs/superpowers/specs/PROJECT_STATUS.md`, die Architektur in `docs/ARCHITECTURE.md`.
>
> **Quelle der Wahrheit für Zeitpläne ist `.github/workflows/analyze.yml`.** Wo dieses
> Dokument davon abweicht, gilt der Workflow.

⚠️ **`analyze.yml` steht derzeit auf `disabled_manually`.** Nichts läuft automatisch.

---

## Overview

Fünf Run-Types. `midday`, `evaluate` und `position_check` gibt es **nicht mehr** — sie
wurden in Sprint 3B / Plan 2 restlos entfernt (Run-Type, Cron, Funktionen, Prompts,
Mail-Renderer, Tests).

| Run-Type | Cron (UTC) | Berlin (CEST) | Zweck | Mail? | Kosten |
|---|---|---|---|---|---|
| `pre_market` | `0 13 * * 1-5` | 15:00 | volle Pipeline Phase 0–5 | ja | **3,13 EUR** gemessen |
| `trade_proposals` | `10 14 * * 1-5`¹ | 16:10 | Re-Validierung der Morgensignale | ja | ~0,5–0,7 EUR |
| `final_close` | `15 0 * * *` | 02:15 | **schreibt die finalen Tagesbars**, bewertet offene Predictions | nein | ~0 EUR |
| `weekly` | `0 18 * * 0` | So 20:00 | Wochenauswertung | ja | ~0 EUR |

¹ Nur der EDT-Slot ist geplant; der Workflow fährt vorerst ausschliesslich die
Berliner Sommerzeit (TODO im `schedule`-Block). Siehe „Die zwei Cron-Fallen".

⚠️ **`close` (22:30) ist am 2026-08-18 ersatzlos entfallen.** Die TP/SL-Auswertung
gehört seit dem Preismodell-Umbau in `final_close` — um 22:30 ist die Tagesbar noch
nicht final, und TP/SL werden gegen Tages-High/Low geprüft, das sich bis 00:00 UTC
nur ausweiten kann. Nach dem Entfernen der Auswertung blieb nichts übrig, das
`pre_market` um 15:00 nicht ohnehin täte (`cleanup_old_data()`, Gap-Fill, und
Indikator-Zeilen mit identischen Werten). Details: PROJECT_STATUS **C.14**.

---

## Die zwei Cron-Fallen

**DST.** Cron ist UTC-fix, GitHub Actions rechnet keine Sommerzeit. Die Berlin-Zeiten oben
gelten für CEST; im Winter (CET) läuft alles 1 h früher.

**`trade_proposals` hängt an der US-Eröffnung, nicht an Berlin.** Er soll 40 min nach
Handelsbeginn liegen, also 10:10 America/New_York — das sind 14:10 UTC unter EDT und
15:10 UTC unter EST. Deshalb existieren **beide** Slots ganzjährig; der Schritt
„Determine run_type" verwirft den falschen anhand von `TZ=America/New_York date +%z`.

Maßgeblich ist bewusst die US-Zeitzone: EU und USA schalten an verschiedenen Wochenenden
um. Mit nur dem Sommer-Slot lief der Lauf von November bis März **vor** der Eröffnung —
der Opening-Gap-Check verglich dort zwei Pre-Open-Kurse und feuerte nie.

**`final_close` hat keine DST-Kopplung.** Er hängt an der Bar-Grenze (00:00 UTC laut
`openingHours`), nicht an einer Börsensitzung. Er läuft **täglich**, nicht Mo–Fr: freitags
schliesst der Handel um 21:00 UTC, die Bar wird erst danach final — erst der Samstagslauf
holt sie.

---

## Voraussetzung: die Datenbank braucht Historie

⚠️ **Das ist der Betriebsfehler, der dieses Projekt zwei Tage gekostet hat.**

Am 2026-08-04 liefen drei Läufe technisch erfolgreich durch und erzeugten **keine einzige
Prediction**. Grund: die CI-Datenbank hatte 19 Bars je Aktie — eine unter
`MIN_BARS_RSI = 20`. `db-latest` war nie mit `historical_loader` bestückt worden und
sammelte nur die Bars ein, die die Läufe selbst schrieben.

**Vor dem ersten Lauf:**

```bash
# In CI: Workflow "bootstrap-db" auslösen (nur workflow_dispatch, kein Cron).
gh workflow run bootstrap-db.yml

# Lokal:
python setup/historical_loader.py --universe

# Prüfen — reine DB-Abfrage, keine API-Calls:
python setup/historical_loader.py --report-coverage
```

Seit `9394e8f` bricht ein `pre_market`- oder `trade_proposals`-Lauf **laut ab**, wenn mehr
als die Hälfte des Universums zu wenig Historie hat. `close`, `final_close` und `weekly`
sind ausgenommen — `final_close` schreibt die Historie selbst und wäre sonst blockiert.

Danach hält `final_close` die Historie täglich fort.

---

## GitHub Secrets (einmalig)

Repo Settings → Secrets and variables → Actions:

| Secret | Quelle |
|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com |
| `RESEND_API_KEY` | https://resend.com/api-keys |
| `EMAIL_TO` | Zieladresse |
| `EMAIL_FROM` | Adresse auf der bei Resend verifizierten Domain |
| `CAPITAL_COM_API_KEY` | Capital.com Demo-Account |
| `CAPITAL_COM_IDENTIFIER` | Capital.com Demo-Account |
| `CAPITAL_COM_PASSWORD` | Capital.com Demo-Account |
| `FINNHUB_API_KEY` | https://finnhub.io |

`GH_TOKEN` kommt aus `secrets.GITHUB_TOKEN` und muss nicht angelegt werden.

---

## DB-Persistenz über Release-Assets

Der Actions-Runner hat ein ephemeres Dateisystem. `tracking.db` überlebt zwischen Läufen
nur als Release-Asset `db-latest`:

```
Download (best effort) → Lauf → Upload --clobber
```

⚠️ **Der Upload läuft unter `always()`, nicht `success()`** (B-10). Die Analyse committet
phasenweise; bricht ein späterer Schritt ab — etwa der Mailversand —, wäre bei `success()`
die gesamte Arbeit verloren. Der hochgeladene Stand ist schlimmstenfalls unvollständig,
aber nie schlechter als der vorherige. Der Job bleibt trotzdem rot.

⚠️ **`bootstrap-db` teilt die `concurrency`-Gruppe mit `analyze`.** Beide schreiben
dasselbe Asset; ohne gemeinsame Gruppe könnte ein Bootstrap mitten in einen Pipelinelauf
laufen und dessen DB überschreiben.

```bash
gh release download db-latest --pattern "tracking.db"   # lokal holen
```

⚠️ **`db-latest` ist nicht automatisch ein guter Datenstand.** Vor Verwendung immer
`--report-coverage` laufen lassen.

---

## Kosten

**Hard Cap: `MAX_COST_PER_RUN_EUR = 4.00`.** Bei Überschreitung wirft der CostTracker
`CostCapExceeded`; der Lauf bricht ab, `aborted_at_phase` wird gesetzt und die Mail geht
mit Warnbanner raus.

**Gemessen am 2026-08-09, `pre_market` mit 20 Tickern: 3,1318 EUR**
(101.648 Input-, 62.976 Output-Tokens).

| Phase | kumuliert |
|---|---|
| Phase 0 (Trends) | 0,13 EUR |
| Phase 2 (Quick-Filter) | 0,24 EUR |
| **Phase 3 (Tiefenanalyse)** | **2,53 EUR** |
| Phase 3b (Rohstoffe/Krypto) | 3,13 EUR |

⚠️ **Bei 20 Tickern sind 78 % des Caps verbraucht.** Der Puffer ist dünn.

⚠️ **Es gibt keinen Deckel auf die Zahl der Tiefenanalysen.** `MAX_DEEP_ANALYSIS = 80` und
`BATCH_SIZE_QUICK = 30` sind **tote Konstanten** — nirgends im Code gelesen. Alle 20 Ticker
gingen in Phase 3, je ~0,11 EUR. Hochgerechnet auf 500 Ticker wären das ~55 EUR pro Lauf.
Der technische Pre-Filter (Sprint 3C / C.4) ist damit keine Optimierung, sondern die
Voraussetzung für jede Skalierung.

```bash
sqlite3 data/tracking.db \
  "SELECT date, run_type, total_eur, aborted_at_phase FROM cost_tracking ORDER BY date DESC LIMIT 10;"
```

---

## Troubleshooting

### E-Mail kommt nicht an

⚠️ **Ein `2xx` von Resend heisst nur „angenommen".** Die Zustellung läuft asynchron und
kann später scheitern. Erfolg nie am Statuscode festmachen:

```bash
curl -s -H "Authorization: Bearer $RESEND_API_KEY" \
  https://api.resend.com/emails/<ID> | python3 -m json.tool
# last_event: "delivered" = wirklich zugestellt; "failed" = nicht
```

Die Message-ID steht im Log (`Resend accepted message (status=200, id=…)`).

Weiter: Secrets prüfen (`gh secret list`), Spam-Ordner, und

```bash
pytest tests/live -m live_api --run-live   # nur lesend, verschickt nichts
pytest tests/live --run-live               # inkl. echtem Versand
```

### Ein Lauf ist grün, aber leer

Genau der Fall vom 2026-08-04. Seit `a5b5548`/`ab6b5d2`/`ccdf5a6` erklärt sich das Log
selbst — im Log nachsehen:

- `Phase 1: N von M Tickern uebersprungen — …` nennt die Gründe gebündelt (D1)
- `Phase 4 done: … (aus N Analysen, davon M enthalten)` schliesst die Lücke zwischen
  Eingang und Ergebnis (D2)
- `Phase 4: KEINE Prediction persistiert …` feuert unabhängig von der Ursache (D3)

Häufigste Ursache: zu wenig Historie → `--report-coverage`.

### Cron feuert nicht

```bash
gh workflow list --all       # steht analyze auf disabled_manually?
gh workflow enable analyze.yml
gh workflow run analyze.yml --ref main -f run_type=final_close
```

⚠️ Das alte Doppel-Cron-Modell mit Sommer-/Winter-Einträgen je Run-Type ist **weg**
(`d17c2f5`). Die Run-Type-Erkennung matcht den `github.event.schedule`-String direkt per
`case`. Nur `trade_proposals` hat weiterhin zwei Slots — aus dem oben genannten Grund.

### DB-Persistenz fehlgeschlagen

```bash
gh release list
gh release create db-latest data/tracking.db --title "DB latest" --notes "manuell"
```

Danach übernimmt `--clobber` automatisch.

---

## Logs & Debugging

```bash
gh run list --limit 10
gh run view <RUN_ID> --log
gh run view <RUN_ID> --log-failed
```

Lokale Läufe protokollieren nach `*.log` im Wurzelverzeichnis (gitignored):

```bash
python main.py --run-type pre_market --db-path /tmp/wegwerf.db > pre_market.log 2>&1
```

⚠️ Auf **INFO** loggen, nicht DEBUG. INFO protokolliert jeden HTTP-Request mit URL und
Status; DEBUG schreibt zusätzlich die Header — und damit API-Keys in die Datei.

---

## Sicherheitsnetze im Code

| Netz | Wirkung |
|---|---|
| `SIMULATION_ONLY=True` | niemals echte Orders |
| Historien-Guard | Abbruch vor Phase 0 bei zu dünner Datenlage |
| `CostCapExceeded` | Abbruch bei 4 EUR, Teilmail mit Banner |
| Netzsperre in Tests | Tests ausserhalb `tests/live/` können nicht nach draussen telefonieren (Transport-Ebene) |
| Docker ohne Argument | gibt die Hilfe aus, startet **keine** Pipeline |
| `concurrency`-Gruppe | zwei Läufe können sich die DB nicht gegenseitig überschreiben |

---

Siehe auch: `CLAUDE.md` (Direktiven und Fallen) · `docs/ARCHITECTURE.md` (Module) ·
`docs/superpowers/specs/PROJECT_STATUS.md` (Ist-Stand) · `.github/workflows/` (Quelle der Wahrheit)
