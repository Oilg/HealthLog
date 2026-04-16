#!/bin/bash
# setup_swap.sh — create 2GB swap file on HealthLog server
# Prevents OOM kills when RAM spikes (server has 1.9GB RAM, no swap).
set -euo pipefail

SWAP_FILE="/swapfile"
SWAP_SIZE="2G"

if swapon --show | grep -q "$SWAP_FILE"; then
    echo "==> Swap already active at $SWAP_FILE, skipping."
    free -h
    exit 0
fi

echo "==> Creating ${SWAP_SIZE} swap file at ${SWAP_FILE}..."
fallocate -l "$SWAP_SIZE" "$SWAP_FILE"

echo "==> Setting permissions (root only)..."
chmod 600 "$SWAP_FILE"

echo "==> Formatting as swap..."
mkswap "$SWAP_FILE"

echo "==> Activating swap..."
swapon "$SWAP_FILE"

echo "==> Persisting swap in /etc/fstab..."
if ! grep -q "$SWAP_FILE" /etc/fstab; then
    echo "${SWAP_FILE} none swap sw 0 0" >> /etc/fstab
fi

echo "==> Tuning swappiness (10 = use swap only when really needed)..."
sysctl vm.swappiness=10
if ! grep -q "vm.swappiness" /etc/sysctl.conf; then
    echo "vm.swappiness=10" >> /etc/sysctl.conf
fi

echo "==> Done. Current memory:"
free -h
