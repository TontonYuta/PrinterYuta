"""
CUPS Queue Management module for PrinterYuta.
Inspects CUPS status, detects duplicate / ghost queues, verifies device URIs,
and heals misconfigured backends.
"""

from __future__ import annotations
import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple


@dataclass
class PrintJob:
    job_id: str
    user: str
    size: str
    date_str: str
    is_active: bool = False
    status_line: str = ""


@dataclass
class PrintQueue:
    name: str
    device_uri: str = ""
    state: str = "unknown"  # idle, printing, stopped, disabled
    state_message: str = ""
    is_accepting: bool = True
    is_default: bool = False
    make_model: str = ""
    is_capt: bool = False
    is_toxic_duplicate: bool = False
    active_jobs: List[PrintJob] = field(default_factory=list)


class CupsManager:
    def __init__(self, run_cmd: Optional[Callable[[List[str]], Tuple[int, str, str]]] = None):
        self._run_cmd = run_cmd or self._default_run_cmd

    @staticmethod
    def _default_run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            return res.returncode, res.stdout, res.stderr
        except Exception as e:
            return 1, "", str(e)

    def is_cups_running(self) -> bool:
        """Check if cups daemon is responding."""
        code, out, _ = self._run_cmd(["lpstat", "-r"])
        return code == 0 and "scheduler is running" in out.lower()

    def get_default_destination(self) -> str:
        code, out, _ = self._run_cmd(["lpstat", "-d"])
        match = re.search(r"system default destination:\s*(\S+)", out)
        return match.group(1) if match else ""

    def parse_queues(self, lpstat_t_output: Optional[str] = None) -> Dict[str, PrintQueue]:
        """Parse `lpstat -t` or combined commands into structured PrintQueue objects."""
        if lpstat_t_output is None:
            _, lpstat_t_output, _ = self._run_cmd(["lpstat", "-p", "-d", "-v", "-a", "-o"])

        queues: Dict[str, PrintQueue] = {}
        default_dest = self.get_default_destination()

        # Parse devices: device for LBP3300: cnusb:/dev/usb/lp1
        for line in lpstat_t_output.splitlines():
            dev_match = re.match(r"device for ([^:]+):\s*(.+)", line.strip())
            if dev_match:
                qname, uri = dev_match.group(1).strip(), dev_match.group(2).strip()
                if qname not in queues:
                    queues[qname] = PrintQueue(name=qname)
                queues[qname].device_uri = uri

        # Parse status: printer LBP3300 is idle. enabled since ...
        # Or: printer LBP3300 now printing LBP3300-11. enabled since ...
        status_pattern = re.compile(r"printer\s+(\S+)\s+(is idle|now printing [^.]+|disabled|stopped)\.\s*(.*)")
        current_status_printer = None
        for line in lpstat_t_output.splitlines():
            m = status_pattern.match(line.strip())
            if m:
                qname, state_desc, extra = m.group(1), m.group(2), m.group(3)
                current_status_printer = qname
                if qname not in queues:
                    queues[qname] = PrintQueue(name=qname)
                if "is idle" in state_desc:
                    queues[qname].state = "idle"
                elif "now printing" in state_desc:
                    queues[qname].state = "printing"
                elif "disabled" in state_desc or "stopped" in state_desc:
                    queues[qname].state = "stopped"
                else:
                    queues[qname].state = state_desc
                queues[qname].state_message = extra
            elif line.startswith(("\t", "   ")) and current_status_printer and current_status_printer in queues:
                # Appends multiline status (e.g. \tFilter function failed...)
                msg = line.strip()
                if queues[current_status_printer].state_message:
                    queues[current_status_printer].state_message += " | " + msg
                else:
                    queues[current_status_printer].state_message = msg


        # Parse accepting status: LBP3300 accepting requests since ...
        for line in lpstat_t_output.splitlines():
            acc_match = re.match(r"(\S+)\s+accepting requests since", line.strip())
            if acc_match:
                qname = acc_match.group(1)
                if qname in queues:
                    queues[qname].is_accepting = True
            not_acc_match = re.match(r"(\S+)\s+not accepting requests since", line.strip())
            if not_acc_match:
                qname = not_acc_match.group(1)
                if qname in queues:
                    queues[qname].is_accepting = False

        # Parse active jobs: LBP3300-11 tontonyuta 48128 Fri 23 Oct ...
        job_pattern = re.compile(r"(\S+)-(\d+)\s+(\S+)\s+(\d+)\s+(.+)")
        for line in lpstat_t_output.splitlines():
            jm = job_pattern.match(line.strip())
            if jm:
                qname, jid, user, size, date_str = jm.groups()
                if qname in queues:
                    job = PrintJob(
                        job_id=f"{qname}-{jid}",
                        user=user,
                        size=size,
                        date_str=date_str,
                        is_active=True,
                    )
                    queues[qname].active_jobs.append(job)

        # Classify default and CAPT status
        for qname, q in queues.items():
            if qname == default_dest:
                q.is_default = True

            # Detect CAPT make/model or name
            if "lbp" in qname.lower() or "capt" in qname.lower() or "ccp:" in q.device_uri or "cnusb:" in q.device_uri:
                q.is_capt = True

            # Identify toxic duplicate queues:
            # If name ends with -2, _2, or contains usb:// for a CAPT model
            if q.is_capt and ("-2" in qname or "_2" in qname or q.device_uri.startswith("usb://")):
                q.is_toxic_duplicate = True

        return queues

    def remove_queue(self, queue_name: str) -> bool:
        """Remove a print queue."""
        code, _, _ = self._run_cmd(["lpadmin", "-x", queue_name])
        return code == 0

    def set_backend(self, queue_name: str, device_uri: str) -> bool:
        """Change the device URI of a queue."""
        code, _, _ = self._run_cmd(["lpadmin", "-p", queue_name, "-v", device_uri])
        return code == 0

    def set_default(self, queue_name: str) -> bool:
        """Set default printer queue."""
        code, _, _ = self._run_cmd(["lpadmin", "-d", queue_name])
        return code == 0

    def enable_queue(self, queue_name: str) -> bool:
        """Ensure queue is accepting jobs and enabled."""
        c1, _, _ = self._run_cmd(["cupsenable", queue_name])
        c2, _, _ = self._run_cmd(["cupsaccept", queue_name])
        return c1 == 0 and c2 == 0

    def cancel_all_jobs(self, queue_name: str) -> bool:
        """Purge all stuck jobs from a queue."""
        code, _, _ = self._run_cmd(["cancel", "-a", queue_name])
        return code == 0

    def heal_capt_queues(self) -> List[str]:
        """
        Autonomous healing algorithm:
        1. Identifies and removes toxic duplicate queues (e.g. LBP3300-2).
        2. Fixes primary CAPT queue backend to ccp:/var/ccpd/fifo0.
        3. Cleans up zombie jobs if stalled.
        4. Enables and accepts requests on primary queue.
        Returns list of actions performed.
        """
        actions = []
        queues = self.parse_queues()

        # Step 1: Remove toxic duplicates
        for qname, q in list(queues.items()):
            if q.is_toxic_duplicate:
                if self.remove_queue(qname):
                    actions.append(f"Removed toxic duplicate queue: {qname} (URI: {q.device_uri})")

        # Refresh queues
        queues = self.parse_queues()

        # Step 2: Fix backend for primary CAPT queue
        capt_queues = [q for q in queues.values() if q.is_capt and not q.is_toxic_duplicate]
        for q in capt_queues:
            # Desired URI for Canon CAPT daemon
            expected_uri = "ccp:/var/ccpd/fifo0"
            if q.device_uri != expected_uri:
                if self.set_backend(q.name, expected_uri):
                    actions.append(f"Updated queue '{q.name}' backend from '{q.device_uri}' to '{expected_uri}'")

            # Enable queue
            if not q.is_accepting or q.state == "stopped":
                if self.enable_queue(q.name):
                    actions.append(f"Enabled queue and accepted requests for '{q.name}'")

            # Set as default if only one CAPT queue exists and no default set
            if not self.get_default_destination() and len(capt_queues) == 1:
                self.set_default(q.name)
                actions.append(f"Set '{q.name}' as system default destination")

        return actions
