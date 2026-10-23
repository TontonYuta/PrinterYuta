import os
import tempfile
import unittest
from printeryuta.core.optimizer import DocumentOptimizer


class TestDocumentOptimizer(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    def test_generate_diagnostic_page(self):
        optimizer = DocumentOptimizer()
        output_pdf = os.path.join(self.tmp_dir, "test.pdf")
        result_path = optimizer.generate_diagnostic_page(
            output_path=output_pdf,
            printer_name="Canon LBP3300",
            device_uri="ccp:/var/ccpd/fifo0"
        )
        self.assertTrue(os.path.exists(result_path))
        self.assertGreater(os.path.getsize(result_path), 0)

    def test_optimize_fallback_when_gs_fails(self):
        dummy_file = os.path.join(self.tmp_dir, "dummy.pdf")
        with open(dummy_file, "w") as f:
            f.write("%PDF-1.4 dummy content")

        def failing_runner(cmd):
            return 1, "", "Ghostscript error"

        optimizer = DocumentOptimizer(run_cmd=failing_runner)
        res = optimizer.optimize_pdf(dummy_file)
        self.assertTrue(os.path.exists(res.output_path))
        self.assertFalse(res.is_modified)


if __name__ == "__main__":
    unittest.main()
