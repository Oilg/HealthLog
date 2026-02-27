#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CRON_CMD="bash $ROOT_DIR/scripts/daily_pipeline.sh"
WEEKDAY_EXPR="0 8 * * 1-5"
WEEKEND_EXPR="0 10 * * 6,0"
WEEKDAY_LINE="$WEEKDAY_EXPR $CRON_CMD"
WEEKEND_LINE="$WEEKEND_EXPR $CRON_CMD"

(
  { crontab -l 2>/dev/null || true; } | grep -Fv "$CRON_CMD" || true
  echo "$WEEKDAY_LINE"
  echo "$WEEKEND_LINE"
) | crontab -

echo "Installed cron jobs:"
echo "  - $WEEKDAY_LINE"
echo "  - $WEEKEND_LINE"
echo "Check with: crontab -l"
