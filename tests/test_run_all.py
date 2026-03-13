from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import run_script


class RunAllTests(unittest.TestCase):
    def test_run_all_dry_run_lists_stage_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "dummy.html"
            html_path.write_text("<html></html>", encoding="utf-8")
            result = run_script(
                "Scripts/00_run_all.py",
                "--root",
                Path(tmp) / "fsa-root",
                "--page-html",
                html_path,
                "--dry-run",
                "--run-qaqc",
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout)
            stdout = result.stdout
            self.assertIn("--verify-only", stdout)
            self.assertIn("01_download_title_iv_reports.py", stdout)
            self.assertIn("02_profile_workbooks.py", stdout)
            self.assertIn("03_build_dictionary.py", stdout)
            self.assertIn("04_panelize_grants.py", stdout)
            self.assertIn("05_panelize_campus_based.py", stdout)
            self.assertIn("06_panelize_loans.py", stdout)
            self.assertIn("07_merge_fsa_panels.py", stdout)
            self.assertIn("08_build_panel_dictionary.py", stdout)
            self.assertIn("00_source_qaqc.py", stdout)
            self.assertIn("01_panel_qaqc.py", stdout)
            self.assertIn("02_acceptance_audit.py", stdout)


if __name__ == "__main__":
    unittest.main()
