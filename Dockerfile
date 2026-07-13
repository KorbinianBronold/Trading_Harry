# Lokaler Cron-Runner fuer Shares_Future -- spiegelt .github/workflows/analyze.yml
# fuer lokales Testen ohne GitHub Actions. Bei Cron-/Run-Type-Aenderungen auch
# docker/crontab aktualisieren (s. Sync-Hinweis dort).
FROM python:3.12-slim

ENV TZ=Europe/Berlin
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN apt-get update \
    && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data

COPY docker/crontab /etc/cron.d/shares-future-cron
RUN chmod 0644 /etc/cron.d/shares-future-cron \
    && crontab /etc/cron.d/shares-future-cron

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
