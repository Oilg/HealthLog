#!/bin/bash
# test_server_hardening.sh — verify server hardening configuration
# Run on the server after applying all setup_*.sh scripts.
# Exit code 0 = all tests passed, non-zero = failures found.
set -uo pipefail

PASS=0
FAIL=0
FAILURES=()

pass() { echo "[PASS] $*"; ((PASS++)); }
fail() { echo "[FAIL] $*"; ((FAIL++)); FAILURES+=("$*"); }

echo "========================================"
echo " HealthLog Server Hardening Test Suite"
echo "========================================"
echo ""

# --- FIREWALL ---
echo "--- Firewall (ufw) ---"

if systemctl is-active --quiet ufw; then
    pass "ufw service is active"
else
    fail "ufw service is not active"
fi

UFW_STATUS=$(ufw status)
if echo "$UFW_STATUS" | grep -q "Status: active"; then
    pass "ufw is enabled"
else
    fail "ufw is not enabled"
fi

if echo "$UFW_STATUS" | grep -q "22/tcp.*ALLOW"; then
    pass "SSH port 22 is allowed"
else
    fail "SSH port 22 is not allowed (risk of lockout)"
fi

if echo "$UFW_STATUS" | grep -q "80/tcp.*ALLOW"; then
    pass "HTTP port 80 is allowed"
else
    fail "HTTP port 80 is not allowed"
fi

if echo "$UFW_STATUS" | grep -qE "5433.*DENY"; then
    pass "PostgreSQL port 5433 is denied from public"
else
    fail "PostgreSQL port 5433 is NOT denied (exposed to internet)"
fi

# Docker binds 0.0.0.0:5433 but ufw DENY rule blocks external access — verify rule exists
if ufw status | grep -qE "5433.*DENY"; then
    pass "ufw DENY rule for PostgreSQL port 5433 is in place"
else
    fail "No ufw DENY rule for PostgreSQL port 5433"
fi

# --- SWAP ---
echo ""
echo "--- Swap ---"

if swapon --show | grep -q "/swapfile"; then
    pass "Swap file /swapfile is active"
else
    fail "Swap file /swapfile is not active"
fi

SWAP_SIZE=$(swapon --show --bytes | awk '/swapfile/ {printf "%.0f", $3/1024/1024/1024}')
if [ "${SWAP_SIZE:-0}" -ge 1 ]; then
    pass "Swap size is ${SWAP_SIZE}GB (>= 1GB)"
else
    fail "Swap size is too small: ${SWAP_SIZE}GB"
fi

if grep -q "/swapfile" /etc/fstab; then
    pass "Swap is persisted in /etc/fstab"
else
    fail "Swap not in /etc/fstab (won't survive reboot)"
fi

SWAPPINESS=$(sysctl -n vm.swappiness)
if [ "$SWAPPINESS" -le 20 ]; then
    pass "vm.swappiness = $SWAPPINESS (low, good)"
else
    fail "vm.swappiness = $SWAPPINESS (too high, should be <= 20)"
fi

# --- FAIL2BAN ---
echo ""
echo "--- Fail2ban ---"

if systemctl is-active --quiet fail2ban; then
    pass "fail2ban service is active"
else
    fail "fail2ban service is not active"
fi

if fail2ban-client status sshd &>/dev/null; then
    pass "fail2ban sshd jail is active"
else
    fail "fail2ban sshd jail is not active"
fi

if fail2ban-client status nginx-botscan &>/dev/null; then
    pass "fail2ban nginx-botscan jail is active"
else
    fail "fail2ban nginx-botscan jail is not active"
fi

if [ -f /etc/fail2ban/jail.local ]; then
    pass "/etc/fail2ban/jail.local exists"
else
    fail "/etc/fail2ban/jail.local missing"
fi

# --- MONITORING ---
echo ""
echo "--- Monitoring ---"

if [ -x /usr/local/bin/healthlog-monitor ]; then
    pass "healthlog-monitor script exists and is executable"
else
    fail "healthlog-monitor script missing or not executable"
fi

if systemctl is-active --quiet healthlog-monitor.timer; then
    pass "healthlog-monitor.timer is active"
else
    fail "healthlog-monitor.timer is not active"
fi

if systemctl is-enabled --quiet healthlog-monitor.timer; then
    pass "healthlog-monitor.timer is enabled (survives reboot)"
else
    fail "healthlog-monitor.timer is not enabled"
fi

if [ -f /var/log/healthlog-monitor.log ]; then
    pass "/var/log/healthlog-monitor.log exists"
else
    fail "/var/log/healthlog-monitor.log not found (monitor may not have run yet)"
fi

# --- SERVICES STILL RUNNING ---
echo ""
echo "--- Core Services ---"

if systemctl is-active --quiet healthlog.service; then
    pass "healthlog.service is running"
else
    fail "healthlog.service is NOT running"
fi

if systemctl is-active --quiet nginx.service; then
    pass "nginx.service is running"
else
    fail "nginx.service is NOT running"
fi

if docker inspect --format='{{.State.Running}}' health_log 2>/dev/null | grep -q true; then
    pass "PostgreSQL container health_log is running"
else
    fail "PostgreSQL container health_log is NOT running"
fi

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost/docs 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    pass "API /docs responds with HTTP 200"
else
    fail "API /docs returned HTTP $HTTP_CODE"
fi

# --- SUMMARY ---
echo ""
echo "========================================"
echo " Results: $PASS passed, $FAIL failed"
echo "========================================"

if [ $FAIL -gt 0 ]; then
    echo ""
    echo "Failures:"
    for f in "${FAILURES[@]}"; do
        echo "  - $f"
    done
    exit 1
fi

echo "All tests passed."
exit 0
