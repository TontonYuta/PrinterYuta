import unittest
from printeryuta.core.detector import HardwareDetector, KNOWN_CANON_CAPT_MODELS


SAMPLE_LSUSB = """
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
Bus 001 Device 002: ID 260d:1026 Compx 2.4G Wireless Receiver
Bus 001 Device 005: ID 04a9:267e Canon, Inc. LBP3300
Bus 001 Device 006: ID 3151:4015 ROYUAN Gaming Keyboard
Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
"""

SAMPLE_LSUSB_NO_PRINTER = """
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
Bus 001 Device 002: ID 260d:1026 Compx 2.4G Wireless Receiver
"""


class TestHardwareDetector(unittest.TestCase):
    def test_parse_lsusb_finds_canon_lbp3300(self):
        detector = HardwareDetector()
        devices = detector.parse_lsusb(SAMPLE_LSUSB)
        self.assertEqual(len(devices), 1)
        dev = devices[0]
        self.assertEqual(dev.vendor_id, "04a9")
        self.assertEqual(dev.product_id, "267e")
        self.assertTrue(dev.is_capt)
        self.assertEqual(dev.model_name, "Canon LBP3300")

    def test_parse_lsusb_no_printers(self):
        detector = HardwareDetector()
        devices = detector.parse_lsusb(SAMPLE_LSUSB_NO_PRINTER)
        self.assertEqual(len(devices), 0)

    def test_known_models_mapping(self):
        self.assertIn("267e", KNOWN_CANON_CAPT_MODELS)
        self.assertIn("2676", KNOWN_CANON_CAPT_MODELS)
        self.assertEqual(KNOWN_CANON_CAPT_MODELS["2676"], "Canon LBP2900")

    def test_scan_with_mock_runner(self):
        def mock_runner(cmd):
            if "lsmod" in cmd:
                return "Module usblp 28672 0"
            if "lsusb" in cmd:
                return SAMPLE_LSUSB
            return ""

        detector = HardwareDetector(run_cmd=mock_runner)
        report = detector.scan(SAMPLE_LSUSB)
        self.assertTrue(report.usblp_loaded)
        self.assertEqual(len(report.devices), 1)
        self.assertIn("Canon LBP3300", report.summary)


if __name__ == "__main__":
    unittest.main()
