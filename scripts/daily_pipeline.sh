#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$ROOT_DIR/logs/daily_pipeline.log"
LOCK_DIR="/tmp/healthlog_daily_pipeline.lockdir"

mkdir -p "$ROOT_DIR/logs"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] skip: previous run still active"
  } >> "$LOG_FILE" 2>&1
  exit 0
fi

cleanup() {
  rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] daily pipeline started"
  "$ROOT_DIR/.venv/bin/python" -m health_log.services.detect_sleep_apnea
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] daily pipeline finished"
} >> "$LOG_FILE" 2>&1
