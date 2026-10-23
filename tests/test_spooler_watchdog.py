import unittest
from printeryuta.core.cups_manager import CupsManager
from printeryuta.core.spooler_watchdog import SpoolerWatchdog


SAMPLE_LPSTAT_ERROR_OUTPUT = """
scheduler is running
system default destination: LBP3300
device for LBP3300: ccp:/var/ccpd/fifo0
LBP3300 accepting requests since Sat 19 Sep 2026
printer LBP3300 now printing LBP3300-99.  enabled since Fri 23 Oct 2026
	Filter function (PID 12345) failed: No such file or directory
LBP3300-99              tontonyuta       12000   Fri 23 Oct 2026
"""


class TestSpoolerWatchdog(unittest.TestCase):
    def test_scan_and_reap_cancels_failed_job(self):
        cancelled_jobs = []

        def mock_runner(cmd):
            if "cancel" in cmd:
                cancelled_jobs.append(cmd[1])
                return 0, "", ""
            if cmd == ["lpstat", "-d"]:
                return 0, "system default destination: LBP3300", ""
            return 0, SAMPLE_LPSTAT_ERROR_OUTPUT, ""

        cups_mgr = CupsManager(run_cmd=mock_runner)
        watchdog = SpoolerWatchdog(cups_manager=cups_mgr, run_cmd=mock_runner)

        actions = watchdog.scan_and_reap(purge_all_stuck=False)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action_type, "cancel_job")
        self.assertEqual(actions[0].target_id, "LBP3300-99")
        self.assertIn("LBP3300-99", cancelled_jobs)


if __name__ == "__main__":
    unittest.main()
