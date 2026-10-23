"""
Systemd and Udev Rules Generator for PrinterYuta.
Enables plug-and-play zero-touch printing on modern Ubuntu by automatically
handling USB hotplug events and daemon recovery.
"""

from __future__ import annotations
import os
import sys
from typing import Dict, List


class SystemdGenerator:
    def __init__(self, python_bin: str = sys.executable, install_prefix: str = "/etc"):
        self.python_bin = python_bin
        self.install_prefix = install_prefix

    def generate_udev_rules(self) -> str:
        """
        Generates /etc/udev/rules.d/85-printeryuta-canon.rules
        Hooks both USB and usbmisc subsystems to automatically create the symlink
        and trigger the hotplug auto-healing service.
        """
        rules = [
            "# ==========================================================",
            "# PrinterYuta - Autonomous Udev Hardware Guard for Canon CAPT",
            "# ==========================================================",
            "",
            "# Create persistent device symlink for Canon LBP3300",
            'KERNEL=="lp[0-9]*", SUBSYSTEMS=="usb", ATTRS{idVendor}=="04a9", ATTRS{idProduct}=="267e", SYMLINK+="canonLBP3300", TAG+="systemd", ENV{SYSTEMD_WANTS}+="printeryuta-hotplug.service"',
            "",
            "# Create persistent device symlink for Canon LBP2900",
            'KERNEL=="lp[0-9]*", SUBSYSTEMS=="usb", ATTRS{idVendor}=="04a9", ATTRS{idProduct}=="2676", SYMLINK+="canonLBP2900", TAG+="systemd", ENV{SYSTEMD_WANTS}+="printeryuta-hotplug.service"',
            "",
            "# Create persistent device symlink for Canon LBP3000",
            'KERNEL=="lp[0-9]*", SUBSYSTEMS=="usb", ATTRS{idVendor}=="04a9", ATTRS{idProduct}=="266a", SYMLINK+="canonLBP3000", TAG+="systemd", ENV{SYSTEMD_WANTS}+="printeryuta-hotplug.service"',
            "",
            "# Fallback wildcard for any Canon CAPT USB device addition",
            'ACTION=="add", SUBSYSTEM=="usb", ATTRS{idVendor}=="04a9", TAG+="systemd", ENV{SYSTEMD_WANTS}+="printeryuta-hotplug.service"',
            "",
        ]
        return "\n".join(rules)

    def generate_hotplug_service(self) -> str:
        """
        Generates /etc/systemd/system/printeryuta-hotplug.service
        A oneshot service triggered by udev whenever the printer is plugged in
        or turned on.
        """
        return f"""[Unit]
Description=PrinterYuta Hotplug Self-Healing Handler
After=cups.service
Wants=cups.service

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 2
ExecStart={self.python_bin} -m printeryuta.cli heal --quiet
RemainAfterExit=no

[Install]
WantedBy=multi-user.target
"""

    def generate_watchdog_service(self) -> str:
        """
        Generates /etc/systemd/system/printeryuta-watchdog.service
        Continuous background supervisor daemon.
        """
        return f"""[Unit]
Description=PrinterYuta Printing Stack Supervisor & Watchdog
After=network.target cups.service
Wants=cups.service

[Service]
Type=simple
ExecStart={self.python_bin} -m printeryuta.cli daemon --interval 10
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

    def get_asset_paths(self) -> Dict[str, str]:
        return {
            "udev_rule": os.path.join(self.install_prefix, "udev/rules.d/85-printeryuta-canon.rules"),
            "hotplug_service": os.path.join(self.install_prefix, "systemd/system/printeryuta-hotplug.service"),
            "watchdog_service": os.path.join(self.install_prefix, "systemd/system/printeryuta-watchdog.service"),
        }
