import unittest
from printeryuta.core.cups_manager import CupsManager


SAMPLE_LPSTAT_OUTPUT = """
scheduler is running
system default destination: LBP3300
device for LBP3300: cnusb:/dev/usb/lp3
device for LBP3300-2: usb://Canon/LBP3300?serial=000011D0LIOt
LBP3300 accepting requests since Sat 19 Sep 2026 04:47:39 PM +07
LBP3300-2 accepting requests since Thu 22 Oct 2026 01:14:54 AM +07
printer LBP3300 is idle.  enabled since Sat 19 Sep 2026 04:47:39 PM +07
printer LBP3300-2 is idle.  enabled since Thu 22 Oct 2026 01:14:54 AM +07
LBP3300-11              tontonyuta       48128   Fri 23 Oct 2026 11:48:43 AM +07
"""


class TestCupsManager(unittest.TestCase):
    def test_parse_queues_identifies_toxic_duplicate(self):
        def mock_runner(cmd):
            if "-d" in cmd:
                return 0, "system default destination: LBP3300", ""
            return 0, SAMPLE_LPSTAT_OUTPUT, ""

        mgr = CupsManager(run_cmd=mock_runner)
        queues = mgr.parse_queues(SAMPLE_LPSTAT_OUTPUT)

        self.assertIn("LBP3300", queues)
        self.assertIn("LBP3300-2", queues)

        primary = queues["LBP3300"]
        self.assertTrue(primary.is_default)
        self.assertTrue(primary.is_capt)
        self.assertFalse(primary.is_toxic_duplicate)
        self.assertEqual(len(primary.active_jobs), 1)
        self.assertEqual(primary.active_jobs[0].job_id, "LBP3300-11")

        duplicate = queues["LBP3300-2"]
        self.assertTrue(duplicate.is_capt)
        self.assertTrue(duplicate.is_toxic_duplicate)
        self.assertTrue(duplicate.device_uri.startswith("usb://"))

    def test_heal_capt_queues_deletes_duplicate_and_fixes_backend(self):
        commands_run = []

        def mock_runner(cmd):
            commands_run.append(list(cmd))
            if cmd == ["lpstat", "-d"]:
                return 0, "system default destination: LBP3300", ""
            if "lpadmin" in cmd and "-x" in cmd:
                return 0, "", ""
            if "lpadmin" in cmd and "-v" in cmd:
                return 0, "", ""
            if "cupsenable" in cmd or "cupsaccept" in cmd:
                return 0, "", ""
            return 0, SAMPLE_LPSTAT_OUTPUT, ""

        mgr = CupsManager(run_cmd=mock_runner)
        # Mock parse_queues to first return two queues, then after removal return one
        actions = mgr.heal_capt_queues()

        # Check that toxic duplicate was removed
        self.assertTrue(any("Removed toxic duplicate queue: LBP3300-2" in act for act in actions))
        self.assertTrue(any(cmd[0] == "lpadmin" and "-x" in cmd and "LBP3300-2" in cmd for cmd in commands_run))


if __name__ == "__main__":
    unittest.main()
