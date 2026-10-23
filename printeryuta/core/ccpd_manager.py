"""
CCPD Manager for PrinterYuta.
Manages the Canon CAPT Communication Protocol Daemon (ccpd),
supervises named pipe /var/ccpd/fifo0, configuration mappings (/etc/ccpd.conf),
and socket listening states.
"""

from __future__ import annotations
import os
import re
import socket
import stat
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple


@dataclass
class CcpdStatus:
    is_installed: bool = False
    is_running: bool = False
    service_state: str = "inactive"
    pid: Optional[int] = None
    captmon_running: bool = False
    captmon_pid: Optional[int] = None
    captmon_proc_name: str = ""
    ui_port_listening: bool = False      # Port 59787
    pdata_port_listening: bool = False   # Port 59687
    fifo_exists: bool = False
    fifo_is_valid: bool = False
    fifo_path: str = "/var/ccpd/fifo0"
    configured_printers: Dict[str, str] = field(default_factory=dict)
    health_issues: List[str] = field(default_factory=list)


class CcpdManager:
    def __init__(
        self,
        run_cmd: Optional[Callable[[List[str]], Tuple[int, str, str]]] = None,
        fifo_path: str = "/var/ccpd/fifo0",
        conf_path: str = "/etc/ccpd.conf"
    ):
        self._run_cmd = run_cmd or self._default_run_cmd
        self.fifo_path = fifo_path
        self.conf_path = conf_path

    @staticmethod
    def _default_run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            return res.returncode, res.stdout, res.stderr
        except Exception as e:
            return 1, "", str(e)

    def is_port_open(self, port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
        """Check if a local TCP port is open and listening."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                return s.connect_ex((host, port)) == 0
        except Exception:
            return False

    def parse_ccpd_conf(self) -> Dict[str, str]:
        """Parse printer mappings in /etc/ccpd.conf."""
        mappings: Dict[str, str] = {}
        if not os.path.isfile(self.conf_path):
            return mappings

        try:
            with open(self.conf_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Matches: <Printer LBP3300>\nDevicePath /dev/canonLBP3300\n</Printer>
            pattern = re.compile(r"<Printer\s+([^>]+)>\s*DevicePath\s+([^\n\r<]+)", re.IGNORECASE)
            for m in pattern.finditer(content):
                pname = m.group(1).strip()
                devpath = m.group(2).strip()
                mappings[pname] = devpath
        except Exception:
            pass

        return mappings

    def check_fifo(self) -> Tuple[bool, bool, str]:
        """
        Check /var/ccpd/fifo0.
        Returns (exists, is_valid_fifo, detail_msg)
        """
        if not os.path.exists(self.fifo_path):
            return False, False, f"Named pipe {self.fifo_path} does not exist"

        try:
            st = os.stat(self.fifo_path)
            is_fifo = stat.S_ISFIFO(st.st_mode)
            if not is_fifo:
                return True, False, f"{self.fifo_path} exists but is not a FIFO special file"
            return True, True, "FIFO valid"
        except Exception as e:
            return True, False, str(e)

    def get_status(self) -> CcpdStatus:
        """Perform comprehensive check on CCPD daemon and environment."""
        status = CcpdStatus(fifo_path=self.fifo_path)

        # Check binary installation
        code, out, _ = self._run_cmd(["which", "ccpd"])
        status.is_installed = (code == 0 and bool(out.strip())) or os.path.exists("/usr/sbin/ccpd")

        if not status.is_installed:
            status.health_issues.append("CCPD binary (/usr/sbin/ccpd) is not installed.")
            return status

        # Check systemd status
        code, out, _ = self._run_cmd(["systemctl", "is-active", "ccpd"])
        status.service_state = out.strip()
        status.is_running = (status.service_state == "active")

        # Check running processes
        _, ps_out, _ = self._run_cmd(["ps", "-eo", "pid,comm,args"])
        for line in ps_out.splitlines():
            line_str = line.strip()
            if "ccpd" in line_str and not status.pid:
                parts = line_str.split(None, 2)
                if parts and parts[0].isdigit():
                    status.pid = int(parts[0])

            if "captmon" in line_str:
                parts = line_str.split(None, 2)
                if parts and parts[0].isdigit():
                    status.captmon_running = True
                    status.captmon_pid = int(parts[0])
                    status.captmon_proc_name = parts[1] if len(parts) > 1 else "captmon"

        # Check ports
        status.ui_port_listening = self.is_port_open(59787)
        status.pdata_port_listening = self.is_port_open(59687)

        # Check FIFO
        exists, is_fifo, msg = self.check_fifo()
        status.fifo_exists = exists
        status.fifo_is_valid = is_fifo

        # Parse config
        status.configured_printers = self.parse_ccpd_conf()

        # Health evaluations
        if not status.is_running:
            status.health_issues.append("ccpd.service is NOT running.")
        else:
            if not status.captmon_running:
                status.health_issues.append("ccpd is running, but captmon backend is NOT active (hardware communication broken).")
            if not status.pdata_port_listening:
                status.health_issues.append("Print data port 59687 is NOT listening.")

        if not status.fifo_exists:
            status.health_issues.append(f"Missing spool FIFO pipe at {self.fifo_path}.")
        elif not status.fifo_is_valid:
            status.health_issues.append(f"{self.fifo_path} is corrupted (not a valid FIFO pipe).")

        for pname, devpath in status.configured_printers.items():
            if not os.path.exists(devpath):
                status.health_issues.append(f"Printer '{pname}' device path '{devpath}' does not exist.")

        return status

    def get_restart_script_content(self, printer_name: str = "LBP3300", device_path: str = "/dev/canonLBP3300") -> str:
        """Generate clean, self-healing bash script to restart CCPD safely."""
        return f"""#!/bin/bash
# Autonomous CCPD Self-Healing Script generated by PrinterYuta
set -e

PRINTER_NAME="{printer_name}"
DEVICE_PATH="{device_path}"
FIFO_PATH="{self.fifo_path}"

# 1. Stop CCPD and CUPS cleanly
systemctl stop ccpd 2>/dev/null || true
killall -9 ccpd 2>/dev/null || true
killall -9 captmon{printer_name.lower()} 2>/dev/null || true

# 2. Ensure FIFO exists with proper permissions
mkdir -p "$(dirname "$FIFO_PATH")"
if [ -e "$FIFO_PATH" ]; then
    rm -f "$FIFO_PATH"
fi
mkfifo "$FIFO_PATH"
chown lp:lp "$FIFO_PATH" 2>/dev/null || true
chmod 666 "$FIFO_PATH"

# 3. Ensure device path or symlink exists
if [ ! -e "$DEVICE_PATH" ]; then
    # Fallback to first available /dev/usb/lp*
    ACTIVE_LP=$(ls /dev/usb/lp* 2>/dev/null | head -n 1 || true)
    if [ -n "$ACTIVE_LP" ]; then
        ln -sf "$ACTIVE_LP" "$DEVICE_PATH"
    fi
fi

# 4. Restart CUPS first, then CCPD
systemctl restart cups
systemctl restart ccpd
"""
