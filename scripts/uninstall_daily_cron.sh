#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CRON_CMD="bash $ROOT_DIR/scripts/daily_pipeline.sh"

( crontab -l 2>/dev/null | grep -Fv "$CRON_CMD" ) | crontab -

echo "Removed cron job for: $CRON_CMD"
