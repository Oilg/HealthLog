#!/bin/bash
# setup_firewall.sh — configure ufw for HealthLog server
# Closes PostgreSQL port 5433 from public internet, keeps app ports open.
set -euo pipefail

echo "==> Installing ufw..."
apt-get install -y ufw

echo "==> Resetting ufw to defaults..."
ufw --force reset

echo "==> Setting default policies..."
ufw default deny incoming
ufw default allow outgoing

echo "==> Allowing SSH (port 22)..."
ufw allow 22/tcp

echo "==> Allowing HTTP (port 80)..."
ufw allow 80/tcp

echo "==> Allowing HTTPS (port 443)..."
ufw allow 443/tcp

echo "==> Blocking public access to PostgreSQL (port 5433)..."
# Port 5433 must only be accessible from localhost (app connects internally)
ufw deny 5433/tcp

echo "==> Allowing Zabbix agent (port 10050) from monitoring network only..."
# Timeweb Zabbix server subnets
ufw allow from 185.69.152.0/22 to any port 10050
ufw allow from 185.69.156.0/22 to any port 10050

echo "==> Enabling ufw..."
ufw --force enable

echo "==> Current ufw status:"
ufw status verbose
