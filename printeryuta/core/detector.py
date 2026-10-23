"""
Detector module for PrinterYuta.
Inspects USB topology, kernel modules (usblp), device nodes (/dev/usb/lp*),
and identifies Canon CAPT / GDI and standard printers.
"""

from __future__ import annotations
import glob
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable, List, Optional


# Known Canon CAPT vendor and product IDs
CANON_VENDOR_ID = "04a9"
KNOWN_CANON_CAPT_MODELS = {
    "267e": "Canon LBP3300",
    "2676": "Canon LBP2900",
    "266a": "Canon LBP3000",
    "261a": "Canon LBP3200",
    "26a4": "Canon LBP3050/LBP3018",
    "26a5": "Canon LBP3100/LBP3108",
    "26da": "Canon LBP6000/LBP6018",
    "26db": "Canon LBP6200",
    "26dc": "Canon LBP6300n",
    "26dd": "Canon LBP6300",
    "2714": "Canon LBP7010C/LBP7018C",
}


@dataclass
class PrinterDevice:
    bus: str
    device: str
    vendor_id: str
    product_id: str
    name: str
    is_capt: bool = False
    model_name: str = ""
    lp_node: Optional[str] = None
    symlink: Optional[str] = None
    driver_bound: str = "unknown"  # "usblp", "usbfs", "none", etc.


@dataclass
class DetectorReport:
    devices: List[PrinterDevice] = field(default_factory=list)
    usblp_loaded: bool = False
    active_lp_nodes: List[str] = field(default_factory=list)
    capt_symlinks: List[str] = field(default_factory=list)
    has_detached_usblp: bool = False
    summary: str = ""


class HardwareDetector:
    def __init__(self, run_cmd: Optional[Callable[[List[str]], str]] = None):
        self._run_cmd = run_cmd or self._default_run_cmd

    @staticmethod
    def _default_run_cmd(cmd: List[str]) -> str:
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            return res.stdout
        except Exception:
            return ""

    def check_usblp_module(self) -> bool:
        """Check if kernel module usblp is loaded."""
        lsmod_out = self._run_cmd(["lsmod"])
        return "usblp" in lsmod_out

    def get_lp_nodes(self) -> List[str]:
        """Find all active /dev/usb/lp* nodes."""
        nodes = sorted(glob.glob("/dev/usb/lp*"))
        return nodes

    def get_capt_symlinks(self) -> List[str]:
        """Find any /dev/canon* symlinks created by udev."""
        links = sorted(glob.glob("/dev/canon*"))
        return links

    def parse_lsusb(self, lsusb_text: Optional[str] = None) -> List[PrinterDevice]:
        """Parse lsusb output to find connected printers."""
        if lsusb_text is None:
            lsusb_text = self._run_cmd(["lsusb"])

        devices: List[PrinterDevice] = []
        # Example format: Bus 001 Device 005: ID 04a9:267e Canon, Inc. LBP3300
        pattern = re.compile(r"Bus\s+(\d+)\s+Device\s+(\d+):\s+ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s+(.+)")

        for line in lsusb_text.strip().splitlines():
            line = line.strip()
            match = pattern.match(line)
            if not match:
                continue

            bus, dev, vid, pid, name = match.groups()
            vid_lower = vid.lower()
            pid_lower = pid.lower()

            is_capt = False
            model_name = ""

            if vid_lower == CANON_VENDOR_ID:
                if pid_lower in KNOWN_CANON_CAPT_MODELS:
                    is_capt = True
                    model_name = KNOWN_CANON_CAPT_MODELS[pid_lower]
                elif "lbp" in name.lower() or "canon" in name.lower():
                    is_capt = True
                    model_name = name

            # Only collect printer devices or Canon CAPT devices
            is_printer = is_capt or ("print" in name.lower()) or ("printer" in name.lower())

            if is_printer:
                devices.append(PrinterDevice(
                    bus=bus,
                    device=dev,
                    vendor_id=vid_lower,
                    product_id=pid_lower,
                    name=name,
                    is_capt=is_capt,
                    model_name=model_name or name,
                ))

        return devices

    def detect_driver_binding(self, dev: PrinterDevice) -> str:
        """Inspect sysfs to check which driver is currently bound to the device interface."""
        # Search /sys/bus/usb/devices/* for matching idVendor and idProduct
        base_path = "/sys/bus/usb/devices"
        if not os.path.isdir(base_path):
            return "unknown"

        for entry in os.listdir(base_path):
            dev_dir = os.path.join(base_path, entry)
            vid_file = os.path.join(dev_dir, "idVendor")
            pid_file = os.path.join(dev_dir, "idProduct")

            if os.path.isfile(vid_file) and os.path.isfile(pid_file):
                try:
                    with open(vid_file, "r") as f:
                        cur_vid = f.read().strip().lower()
                    with open(pid_file, "r") as f:
                        cur_pid = f.read().strip().lower()

                    if cur_vid == dev.vendor_id and cur_pid == dev.product_id:
                        # Find interface directory (e.g. 1-8:1.0)
                        for sub in os.listdir(dev_dir):
                            if ":" in sub:
                                driver_link = os.path.join(dev_dir, sub, "driver")
                                if os.path.islink(driver_link):
                                    target = os.readlink(driver_link)
                                    driver_name = os.path.basename(target)
                                    return driver_name
                        return "unbound"
                except Exception:
                    pass
        return "unknown"

    def scan(self, lsusb_text: Optional[str] = None) -> DetectorReport:
        """Run full scan and return detailed report."""
        devices = self.parse_lsusb(lsusb_text)
        usblp_loaded = self.check_usblp_module()
        lp_nodes = self.get_lp_nodes()
        capt_links = self.get_capt_symlinks()

        has_detached = False

        for dev in devices:
            bound = self.detect_driver_binding(dev)
            dev.driver_bound = bound

            if dev.is_capt:
                # Correlate with active /dev/canon* symlinks
                for link in capt_links:
                    link_name = os.path.basename(link).lower()
                    if dev.product_id in link_name or "lbp" in link_name:
                        dev.symlink = link
                        if os.path.islink(link):
                            target = os.path.realpath(link)
                            dev.lp_node = target
                        break

                # If no symlink found but lp nodes exist
                if not dev.lp_node and lp_nodes:
                    dev.lp_node = lp_nodes[0]

                # Check if detached
                if bound == "usbfs" or (not lp_nodes and bound != "usblp"):
                    has_detached = True

        summary_parts = []
        if devices:
            summary_parts.append(f"Found {len(devices)} printer(s).")
            for d in devices:
                summary_parts.append(f"- {d.model_name} (USB ID {d.vendor_id}:{d.product_id}, Driver: {d.driver_bound})")
        else:
            summary_parts.append("No USB printers detected.")

        if has_detached:
            summary_parts.append("WARNING: Printer detected on USB bus, but kernel driver 'usblp' is detached (captured by usbfs or unhandled).")

        return DetectorReport(
            devices=devices,
            usblp_loaded=usblp_loaded,
            active_lp_nodes=lp_nodes,
            capt_symlinks=capt_links,
            has_detached_usblp=has_detached,
            summary="\n".join(summary_parts)
        )
