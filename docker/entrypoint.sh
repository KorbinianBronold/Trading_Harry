#!/bin/bash
set -e

mkdir -p /app/data
touch /app/data/cron.log

echo "Shares_Future cron container starting (TZ=$(cat /etc/timezone))..."
cron

echo "Cron daemon running. Tailing /app/data/cron.log (Ctrl+C stops the container)."
tail -f /app/data/cron.log
