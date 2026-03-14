from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from helpers import load_script_module


utils = load_script_module("fsa_build_utils_final_filters", "Scripts/fsa_build_utils.py")


class FinalFilterTests(unittest.TestCase):
    def test_filter_clean_panel_to_us_states_keeps_states_and_dc_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            final_dir = root / "Panels" / "final"
            final_dir.mkdir(parents=True, exist_ok=True)
            panel_path = final_dir / "fsa_volume_reports_clean_1999_2025.parquet"
            panel = pd.DataFrame(
                [
                    {"opeid8": "00100000", "award_year": "2001-2002", "state": "CA", "school": "Alpha"},
                    {"opeid8": "00100001", "award_year": "2001-2002", "state": "dc", "school": "Bravo"},
                    {"opeid8": "00100002", "award_year": "2001-2002", "state": "PR", "school": "Charlie"},
                    {"opeid8": "00100003", "award_year": "2001-2002", "state": "FC", "school": "Delta"},
                    {"opeid8": "00100004", "award_year": "2001-2002", "state": "", "school": "Echo"},
                ]
            )
            panel.to_parquet(panel_path, index=False)

            output_panel, summary_csv, dropped_counts_csv = utils.filter_clean_panel_to_us_states(root)
            self.assertTrue(output_panel.exists())
            self.assertTrue(summary_csv.exists())
            self.assertTrue(dropped_counts_csv.exists())

            filtered = pd.read_parquet(output_panel)
            self.assertEqual(filtered["state"].tolist(), ["CA", "DC"])
            self.assertEqual(len(filtered), 2)

            dropped = pd.read_csv(dropped_counts_csv)
            self.assertEqual(dropped["state"].tolist(), ["<blank>", "FC", "PR"])
            self.assertEqual(dropped["rows_dropped"].tolist(), [1, 1, 1])


if __name__ == "__main__":
    unittest.main()
