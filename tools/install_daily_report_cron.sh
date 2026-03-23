#!/bin/bash
# Install cron jobs for Planegraph daily report and weekly FAA registry refresh.
# Daily report runs at 00:15 UTC; FAA refresh runs Sundays at 03:00 UTC.
# Requires DATABASE_URL in the environment (sourced from docker/.env).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
VENV="/opt/planegraph/venv"
LOG_DIR="/opt/planegraph/logs"

mkdir -p "$LOG_DIR"

CRON_DAILY="15 0 * * * . $REPO_ROOT/docker/.env && PATH=$VENV/bin:\$PATH python $REPO_ROOT/tools/daily_report.py >> $LOG_DIR/daily-report.log 2>&1"
CRON_FAA="0 3 * * 0 . $REPO_ROOT/docker/.env && PATH=$VENV/bin:\$PATH python $REPO_ROOT/tools/faa_registry_refresh.py >> $LOG_DIR/faa-registry.log 2>&1"

# Idempotent: remove any existing entries for these scripts, then add both
(
  crontab -l 2>/dev/null | grep -v 'daily_report.py' | grep -v 'faa_registry_refresh.py' || true
  echo "$CRON_DAILY"
  echo "$CRON_FAA"
) | crontab -

echo "Installed daily report cron job (00:15 UTC daily)."
echo "Installed FAA registry refresh cron job (03:00 UTC Sundays)."
echo "Daily report log: $LOG_DIR/daily-report.log"
echo "FAA registry log: $LOG_DIR/faa-registry.log"
echo "Reports: /opt/planegraph/reports/daily/<YYYY>/<MM>/"
