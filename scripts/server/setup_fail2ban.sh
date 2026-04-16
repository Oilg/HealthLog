#!/bin/bash
# setup_fail2ban.sh — install and configure fail2ban for HealthLog server
# Bans IPs after repeated 404s / exploit attempts seen in nginx logs.
set -euo pipefail

echo "==> Installing fail2ban..."
apt-get install -y fail2ban

echo "==> Writing fail2ban local config..."
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
backend  = systemd

[sshd]
enabled  = true
port     = ssh
maxretry = 3
bantime  = 24h

[nginx-http-auth]
enabled  = true

[nginx-botscan]
enabled  = true
port     = http,https
filter   = nginx-botscan
logpath  = /var/log/nginx/access.log
maxretry = 10
findtime = 5m
bantime  = 6h
EOF

echo "==> Writing nginx-botscan filter (catches exploit scanners)..."
mkdir -p /etc/fail2ban/filter.d
cat > /etc/fail2ban/filter.d/nginx-botscan.conf << 'EOF'
[Definition]
# Match IPs that hit known exploit/scan paths
failregex = ^<HOST> .* "(GET|POST|HEAD) /(\.env|device\.rsp|boaform|manager/text|\.git|xmlrpc|phpmyadmin|wp-login|adminer|setup\.php|config\.php) .* 404
            ^<HOST> .* "(GET|POST) /device\.rsp.* 404
ignoreregex =
EOF

echo "==> Enabling and restarting fail2ban..."
systemctl enable fail2ban
systemctl restart fail2ban

sleep 2
echo "==> fail2ban status:"
fail2ban-client status
