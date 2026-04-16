#!/bin/bash
# test_monitoring_stack.sh — verify Prometheus + Grafana are running on server
# Run after deploy. Exit 0 = all passed.
set -uo pipefail

PASS=0
FAIL=0
FAILURES=()

pass() { echo "[PASS] $*"; ((PASS++)); }
fail() { echo "[FAIL] $*"; ((FAIL++)); FAILURES+=("$*"); }

echo "========================================"
echo " HealthLog Monitoring Stack Test Suite"
echo "========================================"
echo ""

# --- CONTAINERS ---
echo "--- Docker containers ---"

if docker inspect --format='{{.State.Running}}' healthlog_prometheus 2>/dev/null | grep -q true; then
    pass "Prometheus container is running"
else
    fail "Prometheus container is NOT running"
fi

if docker inspect --format='{{.State.Running}}' healthlog_grafana 2>/dev/null | grep -q true; then
    pass "Grafana container is running"
else
    fail "Grafana container is NOT running"
fi

# --- PROMETHEUS ---
echo ""
echo "--- Prometheus ---"

PROM_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:9090/-/healthy 2>/dev/null || echo "000")
if [ "$PROM_HTTP" = "200" ]; then
    pass "Prometheus /healthy returns HTTP 200"
else
    fail "Prometheus /healthy returned HTTP $PROM_HTTP"
fi

# Check that healthlog_api target is UP
TARGETS=$(curl -s --max-time 5 http://localhost:9090/api/v1/targets 2>/dev/null)
if echo "$TARGETS" | grep -q '"job":"healthlog_api"'; then
    pass "Prometheus has healthlog_api scrape job configured"
else
    fail "healthlog_api scrape job not found in Prometheus targets"
fi

if echo "$TARGETS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
targets = data.get('data', {}).get('activeTargets', [])
api_targets = [t for t in targets if t.get('labels', {}).get('job') == 'healthlog_api']
up = [t for t in api_targets if t.get('health') == 'up']
sys.exit(0 if up else 1)
" 2>/dev/null; then
    pass "healthlog_api target health is UP"
else
    fail "healthlog_api target is not UP (scrape may have failed)"
fi

# --- APP METRICS ENDPOINT ---
echo ""
echo "--- App /metrics endpoint ---"

METRICS_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:8080/metrics 2>/dev/null || echo "000")
if [ "$METRICS_HTTP" = "200" ]; then
    pass "App /metrics returns HTTP 200"
else
    fail "App /metrics returned HTTP $METRICS_HTTP"
fi

METRICS_BODY=$(curl -s --max-time 5 http://localhost:8080/metrics 2>/dev/null)
if echo "$METRICS_BODY" | grep -q "http_requests_total"; then
    pass "App /metrics contains http_requests_total"
else
    fail "http_requests_total not found in /metrics"
fi

# --- GRAFANA ---
echo ""
echo "--- Grafana ---"

GRAFANA_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:3000/api/health 2>/dev/null || echo "000")
if [ "$GRAFANA_HTTP" = "200" ]; then
    pass "Grafana /api/health returns HTTP 200"
else
    fail "Grafana /api/health returned HTTP $GRAFANA_HTTP"
fi

# Check Grafana accessible via nginx at /grafana/
NGINX_GRAFANA=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost/grafana/ 2>/dev/null || echo "000")
if [ "$NGINX_GRAFANA" = "200" ]; then
    pass "Grafana accessible via nginx at /grafana/"
else
    fail "Grafana /grafana/ via nginx returned HTTP $NGINX_GRAFANA"
fi

# Check datasource is provisioned
DS=$(curl -s --max-time 5 -u admin:healthlog_admin http://localhost:3000/api/datasources 2>/dev/null)
if echo "$DS" | grep -q "Prometheus"; then
    pass "Grafana Prometheus datasource is provisioned"
else
    fail "Grafana Prometheus datasource not found"
fi

# Check dashboard is provisioned
DASH=$(curl -s --max-time 5 -u admin:healthlog_admin "http://localhost:3000/api/dashboards/uid/healthlog-api" 2>/dev/null)
if echo "$DASH" | grep -q "HealthLog API"; then
    pass "Grafana HealthLog API dashboard is provisioned"
else
    fail "Grafana HealthLog API dashboard not found"
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
