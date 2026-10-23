import os
import tempfile
import unittest
from printeryuta.core.ccpd_manager import CcpdManager


SAMPLE_CCPD_CONF = """
# Canon CCPD configuration file
<Path>
CUPS_ConfigPath   /etc/cups/
</Path>

<Printer LBP3300>
DevicePath /dev/canonLBP3300
</Printer>

<Printer LBP2900>
DevicePath /dev/canonLBP2900
</Printer>

<Ports>
UI_Port  59787
PDATA_Port  59687
</Ports>
"""


class TestCcpdManager(unittest.TestCase):
    def setUp(self):
        self.tmp_conf = tempfile.NamedTemporaryFile(mode="w", delete=False)
        self.tmp_conf.write(SAMPLE_CCPD_CONF)
        self.tmp_conf.close()

    def tearDown(self):
        if os.path.exists(self.tmp_conf.name):
            os.remove(self.tmp_conf.name)

    def test_parse_ccpd_conf(self):
        mgr = CcpdManager(conf_path=self.tmp_conf.name)
        mappings = mgr.parse_ccpd_conf()
        self.assertEqual(len(mappings), 2)
        self.assertEqual(mappings["LBP3300"], "/dev/canonLBP3300")
        self.assertEqual(mappings["LBP2900"], "/dev/canonLBP2900")

    def test_restart_script_content(self):
        mgr = CcpdManager(fifo_path="/var/ccpd/fifo0")
        script = mgr.get_restart_script_content(printer_name="LBP3300")
        self.assertIn("PRINTER_NAME=\"LBP3300\"", script)
        self.assertIn("systemctl restart ccpd", script)
        self.assertIn("mkfifo", script)
        self.assertIn("systemctl restart cups", script)


if __name__ == "__main__":
    unittest.main()
