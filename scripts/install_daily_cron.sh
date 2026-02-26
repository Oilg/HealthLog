#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CRON_CMD="bash $ROOT_DIR/scripts/daily_pipeline.sh"
CRON_EXPR="0 7 * * *"
LINE="$CRON_EXPR $CRON_CMD"

( crontab -l 2>/dev/null | grep -Fv "$CRON_CMD"; echo "$LINE" ) | crontab -

echo "Installed cron job: $LINE"
echo "Check with: crontab -l"
