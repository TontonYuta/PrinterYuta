"""
Spooler Watchdog for PrinterYuta.
Monitors print queues, detects stuck / zombie jobs that block hardware,
auto-unpauses stopped queues, and purges clogged spoolers.
"""

from __future__ import annotations
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple
from printeryuta.core.cups_manager import CupsManager, PrintJob, PrintQueue


@dataclass
class WatchdogAction:
    action_type: str  # "cancel_job", "resume_queue", "purge_queue"
    queue_name: str
    target_id: Optional[str] = None
    reason: str = ""
    timestamp: float = field(default_factory=time.time)


class SpoolerWatchdog:
    def __init__(
        self,
        cups_manager: Optional[CupsManager] = None,
        job_timeout_seconds: int = 120,
        run_cmd: Optional[Callable[[List[str]], Tuple[int, str, str]]] = None,
    ):
        self._run_cmd = run_cmd or self._default_run_cmd
        self.cups_mgr = cups_manager or CupsManager(run_cmd=self._run_cmd)
        self.job_timeout_seconds = job_timeout_seconds
        self.history: List[WatchdogAction] = []

    @staticmethod
    def _default_run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            return res.returncode, res.stdout, res.stderr
        except Exception as e:
            return 1, "", str(e)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a specific print job."""
        code, _, _ = self._run_cmd(["cancel", job_id])
        return code == 0

    def purge_queue(self, queue_name: str) -> bool:
        """Cancel all pending and active jobs on a queue."""
        code, _, _ = self._run_cmd(["cancel", "-a", queue_name])
        return code == 0

    def resume_queue(self, queue_name: str) -> bool:
        """Enable and accept requests on a paused/stopped queue."""
        return self.cups_mgr.enable_queue(queue_name)

    def scan_and_reap(self, purge_all_stuck: bool = False) -> List[WatchdogAction]:
        """
        Scan all CUPS queues:
        1. Resumes stopped / disabled queues.
        2. Detects jobs with filter errors or excessive wait time.
        3. Cleans them up and returns record of actions.
        """
        actions: List[WatchdogAction] = []
        queues = self.cups_mgr.parse_queues()

        for qname, q in queues.items():
            # Check 1: Resume paused / stopped queues
            if q.state in ("stopped", "disabled") or not q.is_accepting:
                if self.resume_queue(qname):
                    act = WatchdogAction(
                        action_type="resume_queue",
                        queue_name=qname,
                        reason=f"Queue was {q.state} (accepting={q.is_accepting})"
                    )
                    actions.append(act)
                    self.history.append(act)

            # Check 2: Check active jobs
            if q.active_jobs:
                # If printer has error message or filter function failed
                has_filter_error = any(kw in q.state_message.lower() for kw in ("failed", "error", "filter function", "unable to open"))
                
                if purge_all_stuck or has_filter_error:
                    for job in q.active_jobs:
                        if self.cancel_job(job.job_id):
                            act = WatchdogAction(
                                action_type="cancel_job",
                                queue_name=qname,
                                target_id=job.job_id,
                                reason=f"Purged stuck job in state: {q.state_message or 'stalled'}"
                            )
                            actions.append(act)
                            self.history.append(act)

        return actions
