#!/bin/bash
# setup_monitoring.sh — install health check script + systemd timer
# Checks that healthlog service, nginx, and postgres are alive every 5 minutes.
# Writes status to /var/log/healthlog-monitor.log and alerts via systemd journal.
set -euo pipefail

MONITOR_SCRIPT="/usr/local/bin/healthlog-monitor"
LOG_FILE="/var/log/healthlog-monitor.log"

echo "==> Writing monitor script to ${MONITOR_SCRIPT}..."
cat > "$MONITOR_SCRIPT" << 'MONITOR'
#!/bin/bash
# healthlog-monitor — check critical services and log status
set -euo pipefail

LOG="/var/log/healthlog-monitor.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
ISSUES=()

log() {
    echo "[$TIMESTAMP] $*" | tee -a "$LOG"
}

# 1. Check healthlog systemd service
if ! systemctl is-active --quiet healthlog.service; then
    ISSUES+=("healthlog.service is DOWN")
    systemctl restart healthlog.service && log "WARN: healthlog.service was down, restarted"
fi

# 2. Check nginx
if ! systemctl is-active --quiet nginx.service; then
    ISSUES+=("nginx.service is DOWN")
    systemctl restart nginx.service && log "WARN: nginx.service was down, restarted"
fi

# 3. Check postgres container
if ! docker inspect --format='{{.State.Running}}' health_log 2>/dev/null | grep -q true; then
    ISSUES+=("PostgreSQL container health_log is DOWN")
    docker start health_log && log "WARN: health_log container was down, restarted"
fi

# 4. Check API responds
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost/docs 2>/dev/null || echo "000")
if [ "$HTTP_CODE" != "200" ]; then
    ISSUES+=("API /docs returned HTTP $HTTP_CODE")
fi

# 5. RAM check — warn if available < 200MB
AVAILABLE_MB=$(awk '/MemAvailable/ {printf "%d", $2/1024}' /proc/meminfo)
if [ "$AVAILABLE_MB" -lt 200 ]; then
    ISSUES+=("LOW RAM: only ${AVAILABLE_MB}MB available")
fi

# 6. Disk check — warn if used > 85%
DISK_USED=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_USED" -gt 85 ]; then
    ISSUES+=("LOW DISK: ${DISK_USED}% used on /")
fi

# Report
if [ ${#ISSUES[@]} -eq 0 ]; then
    log "OK: all services healthy | RAM available: ${AVAILABLE_MB}MB | disk: ${DISK_USED}%"
else
    for issue in "${ISSUES[@]}"; do
        log "ALERT: $issue"
        # Write to systemd journal with high priority so it can be picked up by Zabbix
        logger -p user.crit -t healthlog-monitor "ALERT: $issue"
    done
fi
MONITOR

chmod +x "$MONITOR_SCRIPT"

echo "==> Creating systemd service unit..."
cat > /etc/systemd/system/healthlog-monitor.service << 'EOF'
[Unit]
Description=HealthLog monitoring check
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/healthlog-monitor
StandardOutput=journal
StandardError=journal
EOF

echo "==> Creating systemd timer (runs every 5 minutes)..."
cat > /etc/systemd/system/healthlog-monitor.timer << 'EOF'
[Unit]
Description=Run HealthLog monitor every 5 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF

echo "==> Enabling and starting timer..."
systemctl daemon-reload
systemctl enable healthlog-monitor.timer
systemctl start healthlog-monitor.timer

echo "==> Running first check now..."
systemctl start healthlog-monitor.service

echo "==> Timer status:"
systemctl status healthlog-monitor.timer --no-pager

echo "==> Last monitor output:"
tail -5 "$LOG_FILE" 2>/dev/null || journalctl -u healthlog-monitor.service -n 5 --no-pager
