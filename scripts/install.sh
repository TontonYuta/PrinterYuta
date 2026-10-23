#!/usr/bin/env bash
# ==========================================================
# PrinterYuta - One-Click Zero-Touch Installer for Ubuntu
# ==========================================================
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$(which python3)"

echo "[PrinterYuta] Installing systemd services and udev hardware guards..."

# 1. Generate assets using CLI
cd "$REPO_DIR"
"$PYTHON_BIN" -m printeryuta.cli install-daemon

# 2. Check if running with sudo
if [ "$EUID" -ne 0 ]; then
    echo "[PrinterYuta] Root privileges required to copy files to /etc."
    echo "Please run: sudo bash $0"
    exit 1
fi

# 3. Copy udev rule
cp "$REPO_DIR/printeryuta/assets/udev/85-printeryuta-canon.rules" /etc/udev/rules.d/
udevadm control --reload-rules
udevadm trigger

# 4. Copy systemd services
cp "$REPO_DIR/printeryuta/assets/systemd/"*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now printeryuta-watchdog.service

echo "[PrinterYuta] Installation successful! System-wide autonomous print guard is now ACTIVE."
