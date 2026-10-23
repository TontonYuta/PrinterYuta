import unittest
from click.testing import CliRunner
from printeryuta.cli import main


class TestCli(unittest.TestCase):
    def test_version_command(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("PrinterYuta", result.output)

    def test_status_command(self):
        runner = CliRunner()
        result = runner.invoke(main, ["status"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("CUPS Spooler Queues", result.output)

    def test_doctor_command(self):
        runner = CliRunner()
        result = runner.invoke(main, ["doctor"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("PrinterYuta Doctor", result.output)

    def test_install_daemon_command(self):
        runner = CliRunner()
        result = runner.invoke(main, ["install-daemon"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Generated system assets in repo", result.output)


if __name__ == "__main__":
    unittest.main()
