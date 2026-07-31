### Start Claude
# Startet eine interaktive Claude-Sitzung ohne Berechtigungsabfragen
claude --dangerously-skip-permissions

# Führt einen einzelnen Befehl direkt im Hintergrund aus (Unattended Mode)
claude -p "Fix all lint errors in the src folder" --dangerously-skip-permissions

Alternative: Der neue auto Modus
Wenn dir der komplette Blindflug zu gefährlich ist, kannst du stattdessen den sichereren Auto-Modus nutzen (verfügbar in neueren Claude Code Versionen). Hierbei bewertet ein kleineres KI-Modell im Hintergrund, ob die Aktion harmlos ist, und fragt nur bei potenziell riskanten Aktionen nach:
Bash
claude --permission-mode auto

### Docker
Nutzung:
docker compose up -d --build              # Cron-Container im Hintergrund
docker compose run --rm trading-harry-cron python main.py --run-type pre_market   # einzelner Run
tail -f data/cron.log                     # Logs verfolgen