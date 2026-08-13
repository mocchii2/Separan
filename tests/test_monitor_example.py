import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.cli import execute


class MonitorExampleTests(unittest.TestCase):
    def test_monitor_decision_model(self):
        script = ROOT / "examples" / "monitor" / "main.sep"
        source = script.read_text(encoding="utf-8")
        output = execute(
            source,
            str(script),
            script_path=str(script),
            project_root=script.parent,
        )[1]

        self.assertIn("SENT | log_alert | WEB01 | NONE", output)
        self.assertIn("SUPPRESSED | log_alert | WEB01 | DUPLICATE", output)
        self.assertIn("SUPPRESSED | log_alert | WEB01 | TRANSITION_GRACE", output)
        self.assertIn("SUPPRESSED | log_alert | WEB01 | MAINTENANCE", output)
        self.assertIn("SUPPRESSED | log_alert | WEB01 | USER_RULE", output)
        self.assertIn("SENT | resource_started | BATCH01 | NONE", output)
        self.assertIn("SENT | job_overdue | BATCH01 | NONE", output)
        self.assertIn("History: detected=7, sent=3, suppressed=4", output)
        self.assertIn("State transitions recorded: 1", output)
        self.assertIn("Job observations recorded: 1", output)


if __name__ == "__main__":
    unittest.main()
