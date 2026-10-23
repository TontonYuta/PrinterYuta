#!/usr/bin/env bash
# ==========================================================
# PrinterYuta - Uninstaller Script
# ==========================================================
set -e

if [ "$EUID" -ne 0 ]; then
    echo "[PrinterYuta] Please run with root privileges: sudo bash $0"
    exit 1
fi

echo "[PrinterYuta] Stopping and removing services..."
systemctl stop printeryuta-watchdog.service 2>/dev/null || true
systemctl disable printeryuta-watchdog.service 2>/dev/null || true

rm -f /etc/systemd/system/printeryuta-*.service
rm -f /etc/udev/rules.d/85-printeryuta-canon.rules

udevadm control --reload-rules
systemctl daemon-reload

echo "[PrinterYuta] Uninstalled successfully."
