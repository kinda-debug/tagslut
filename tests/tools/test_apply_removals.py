
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import os
import tempfile
from tools.review import apply_removals

from dedupe.utils.safety_gates import SafetyGates
from dedupe.utils.console_ui import ConsoleUI

class TestApplyRemovals(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "test.db"
        self.plan_path = self.temp_path / "plan.csv"
        self.quarantine_root = self.temp_path / "quarantine"
        self.quarantine_root.mkdir()
        self.ui = ConsoleUI(quiet=True)
        self.gates = SafetyGates(self.ui)

        with open(self.plan_path, "w") as f:
            f.write("path,action\n")
            f.write(f"{self.temp_path / 'file1.txt'},QUARANTINE\n")

        with open(self.temp_path / "file1.txt", "w") as f:
            f.write("hello")

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch('builtins.input', return_value='I understand the risks and wish to proceed')
    def test_confirm_execution_success(self, mock_input):
        self.assertTrue(self.gates.confirm_destructive_operation("test prompt", "I understand the risks and wish to proceed"))

    @patch('builtins.input', return_value='no')
    def test_confirm_execution_fail(self, mock_input):
        self.assertFalse(self.gates.confirm_destructive_operation("test prompt", "I understand the risks and wish to proceed"))

    def test_preflight_validator(self) -> None:
        # Ensure db, plan, and quarantine root exist
        if not self.db_path.exists():
            self.db_path.touch()
        if not self.quarantine_root.exists():
            self.quarantine_root.mkdir()
        # Write a valid plan file with header and one row
        with open(self.plan_path, "w") as f:
            f.write("path,action\n")
            f.write(f"{self.temp_path / 'file1.txt'},QUARANTINE\n")
        # Ensure file1.txt exists
        file1 = self.temp_path / 'file1.txt'
        if not file1.exists():
            with open(file1, "w") as f:
                f.write("hello")
        validator = apply_removals.PreFlightValidator(
            self.quarantine_root,
            self.plan_path,
            str(self.db_path),
            True
        )
        self.assertTrue(
            validator.validate()
        )

    def test_preflight_validator_no_db(self):
        # Ensure db file does not exist
        if self.db_path.exists():
            self.db_path.unlink()
        validator = apply_removals.PreFlightValidator(self.quarantine_root, self.plan_path, str(self.db_path), True)
        self.assertFalse(validator.validate())
        errors = validator.get_errors()
        self.assertTrue(any("Database file does not exist" in err for err in errors))

    def test_preflight_validator_no_plan(self):
        self.db_path.touch()
        validator = apply_removals.PreFlightValidator(self.quarantine_root, self.temp_path / "nonexistent.csv", str(self.db_path), True)
        self.assertFalse(validator.validate())
        self.assertIn("Plan file does not exist", validator.get_errors()[0])

    def test_preflight_validator_no_quarantine_root(self):
        # Ensure db file exists before validation
        if not self.db_path.exists():
            self.db_path.touch()
        validator = apply_removals.PreFlightValidator(self.temp_path / "nonexistent", self.plan_path, str(self.db_path), True)
        self.assertFalse(validator.validate())
        self.assertIn("Quarantine root does not exist", validator.get_errors()[0])

if __name__ == '__main__':
    unittest.main()
