# Lokales Test-Image fuer Shares_Future -- fuehrt einzelne Run-Types manuell
# aus (z.B. `docker compose run --rm trading-harry --run-type pre_market`).
# Kein Scheduler/Cron enthalten: automatisierte Ausfuehrung laeuft ueber
# .github/workflows/analyze.yml (GitHub Actions), nicht hierueber.
FROM python:3.12-slim

ENV TZ=Europe/Berlin
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data

ENTRYPOINT ["python", "main.py"]
