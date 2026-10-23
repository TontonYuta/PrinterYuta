"""
Background Watchdog Service for PrinterYuta.
Runs an event-driven loop that automatically detects printer state changes,
heals queues, removes rogue duplicate printers, and restarts dead daemons.
"""

from __future__ import annotations
import logging
import time
from typing import Callable, Optional
from printeryuta.core.detector import HardwareDetector
from printeryuta.core.cups_manager import CupsManager
from printeryuta.core.ccpd_manager import CcpdManager
from printeryuta.core.spooler_watchdog import SpoolerWatchdog

logger = logging.getLogger("PrinterYutaDaemon")


class PrinterYutaDaemon:
    def __init__(
        self,
        interval_seconds: int = 10,
        detector: Optional[HardwareDetector] = None,
        cups_mgr: Optional[CupsManager] = None,
        ccpd_mgr: Optional[CcpdManager] = None,
        watchdog: Optional[SpoolerWatchdog] = None,
        on_heal_event: Optional[Callable[[str], None]] = None,
    ):
        self.interval = interval_seconds
        self.detector = detector or HardwareDetector()
        self.cups_mgr = cups_mgr or CupsManager()
        self.ccpd_mgr = ccpd_mgr or CcpdManager()
        self.watchdog = watchdog or SpoolerWatchdog(cups_manager=self.cups_mgr)
        self.on_heal_event = on_heal_event
        self._running = False

    def emit(self, msg: str):
        logger.info(msg)
        if self.on_heal_event:
            self.on_heal_event(msg)

    def run_one_cycle(self) -> int:
        """
        Executes one health check cycle:
        1. Checks hardware connectivity.
        2. Nukes toxic duplicate queues that hijack usblp.
        3. Cleans stalled jobs.
        4. Re-enables disabled queues.
        Returns the number of corrective actions taken.
        """
        actions_count = 0

        # Check CUPS daemon
        if not self.cups_mgr.is_cups_running():
            self.emit("Warning: CUPS daemon is not running!")
            return 0

        # Check and heal CUPS queues
        heal_actions = self.cups_mgr.heal_capt_queues()
        for act in heal_actions:
            self.emit(f"[CUPS Guard] {act}")
            actions_count += 1

        # Check and reap stalled jobs
        reaped = self.watchdog.scan_and_reap(purge_all_stuck=False)
        for wact in reaped:
            self.emit(f"[Spooler Guard] {wact.action_type} on {wact.queue_name}: {wact.reason}")
            actions_count += 1

        # Check hardware
        report = self.detector.scan()
        if report.has_detached_usblp:
            self.emit("[Hardware Guard] Alert: Printer is connected but kernel driver 'usblp' is detached!")

        return actions_count

    def start(self):
        """Starts the daemon loop."""
        self._running = True
        self.emit(f"PrinterYuta Daemon started (poll interval: {self.interval}s)")

        while self._running:
            try:
                self.run_one_cycle()
            except Exception as e:
                self.emit(f"Daemon error during cycle: {e}")

            time.sleep(self.interval)

    def stop(self):
        """Stops the daemon loop."""
        self._running = False
        self.emit("PrinterYuta Daemon stopped.")
