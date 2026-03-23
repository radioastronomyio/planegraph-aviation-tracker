#!/bin/bash
# Install cron job for daily Planegraph report generation.
# Runs at 00:15 UTC daily to report on the previous day.
# Requires DATABASE_URL in the environment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
VENV="/opt/planegraph/venv"
LOG_DIR="/opt/planegraph/logs"

mkdir -p "$LOG_DIR"

# Build cron line — sources .env for DATABASE_URL, activates venv, runs script
CRON_LINE="15 0 * * * . $REPO_ROOT/docker/.env && PATH=$VENV/bin:\$PATH python $REPO_ROOT/tools/daily_report.py >> $LOG_DIR/daily-report.log 2>&1"

# Idempotent: remove existing planegraph-daily-report entry, then add
(crontab -l 2>/dev/null | grep -v 'daily_report.py' || true; echo "$CRON_LINE") | crontab -

echo "Installed daily report cron job (00:15 UTC)."
echo "Log: $LOG_DIR/daily-report.log"
echo "Reports: /opt/planegraph/reports/daily/<YYYY>/<MM>/"
