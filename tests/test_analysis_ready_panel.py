from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from helpers import load_script_module


utils = load_script_module("fsa_build_utils_analysis_panel", "Scripts/fsa_build_utils.py")


class AnalysisReadyPanelTests(unittest.TestCase):
    def test_build_analysis_ready_final_panel_drops_source_descriptor_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            final_dir = root / "Panels" / "final"
            final_dir.mkdir(parents=True, exist_ok=True)
            panel_path = final_dir / "fsa_volume_reports_clean_us_states_only_1999_2025.parquet"
            frame = pd.DataFrame(
                [
                    {
                        "opeid8": "00100000",
                        "opeid6": "001000",
                        "award_year": "2001-2002",
                        "award_year_start": 2001,
                        "award_year_end": 2002,
                        "school": "Alpha College",
                        "state": "CA",
                        "zip_code": "90001",
                        "school_type": "Public",
                        "grant__school": "ALPHA COLLEGE",
                        "grant__state": "CA",
                        "grant__zip_code": "90001",
                        "grant__school_type": "Public",
                        "campus__school": "Alpha College",
                        "campus__state": "CA",
                        "campus__zip_code": "90001",
                        "campus__school_type": "Public",
                        "loan__school": "ALPHA COLLEGE",
                        "loan__state": "CA",
                        "loan__zip_code": "90001",
                        "loan__school_type": "Public",
                        "grant__pell_recipients": 10,
                        "campus__fws_recipients": 5,
                        "loan__subsidized_recipients": 7,
                    }
                ]
            )
            frame.to_parquet(panel_path, index=False)

            output_panel, summary_csv = utils.build_analysis_ready_final_panel(root)
            self.assertTrue(output_panel.exists())
            self.assertTrue(summary_csv.exists())

            analysis_panel = pd.read_parquet(output_panel)
            self.assertEqual(len(analysis_panel), 1)
            self.assertEqual(int(analysis_panel.duplicated(["opeid8", "award_year"]).sum()), 0)
            self.assertIn("school", analysis_panel.columns)
            self.assertIn("grant__pell_recipients", analysis_panel.columns)
            self.assertIn("campus__fws_recipients", analysis_panel.columns)
            self.assertIn("loan__subsidized_recipients", analysis_panel.columns)
            self.assertNotIn("grant__school", analysis_panel.columns)
            self.assertNotIn("campus__school", analysis_panel.columns)
            self.assertNotIn("loan__school", analysis_panel.columns)


if __name__ == "__main__":
    unittest.main()
