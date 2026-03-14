from __future__ import annotations

import unittest

import pandas as pd

from helpers import load_script_module


utils = load_script_module("fsa_build_utils_loan_harmonization", "Scripts/fsa_build_utils.py")


class LoanHarmonizationTests(unittest.TestCase):
    def test_harmonize_loan_panel_prefers_generic_total_and_drops_split_columns(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "opeid8": "00100000",
                    "award_year": "2005-2006",
                    "loan_direct__plus_recipients": 10,
                    "loan_direct__parent_plus_recipients": pd.NA,
                    "loan_direct__grad_plus_recipients": 0,
                    "loan_direct__plus_loans_originated_n": 12,
                    "loan_direct__parent_plus_loans_originated_n": pd.NA,
                    "loan_direct__grad_plus_loans_originated_n": 0,
                },
                {
                    "opeid8": "00100001",
                    "award_year": "2006-2007",
                    "loan_direct__plus_recipients": pd.NA,
                    "loan_direct__parent_plus_recipients": 4,
                    "loan_direct__grad_plus_recipients": 6,
                    "loan_direct__plus_loans_originated_n": pd.NA,
                    "loan_direct__parent_plus_loans_originated_n": 5,
                    "loan_direct__grad_plus_loans_originated_n": 7,
                },
            ]
        )

        harmonized, summary = utils.harmonize_loan_panel(frame)
        self.assertEqual(harmonized["loan_direct__plus_recipients"].tolist(), [10, 10])
        self.assertEqual(harmonized["loan_direct__plus_loans_originated_n"].tolist(), [12, 12])
        self.assertNotIn("loan_direct__parent_plus_recipients", harmonized.columns)
        self.assertNotIn("loan_direct__grad_plus_recipients", harmonized.columns)

        summary_row = summary.loc[summary["generic_column"] == "loan_direct__plus_recipients"].iloc[0]
        self.assertEqual(int(summary_row["rows_generic_and_split_overlap"]), 1)
        self.assertEqual(int(summary_row["rows_overlap_exact_match"]), 0)
        self.assertEqual(int(summary_row["rows_using_split_sum"]), 1)

    def test_consolidate_loan_programs_sums_direct_and_ffel_into_single_loan_block(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "opeid8": "00100000",
                    "award_year": "2005-2006",
                    "loan_direct__school": "Alpha College",
                    "loan_direct__state": "CA",
                    "loan_direct__zip_code": "90001",
                    "loan_direct__school_type": "Public",
                    "loan_direct__subsidized_recipients": 10,
                    "loan_ffel__school": "Alpha College",
                    "loan_ffel__state": "CA",
                    "loan_ffel__zip_code": "90001",
                    "loan_ffel__school_type": "Public",
                    "loan_ffel__subsidized_recipients": 5,
                }
            ]
        )

        consolidated, summary = utils.consolidate_loan_programs(frame)
        self.assertIn("loan__school", consolidated.columns)
        self.assertIn("loan__subsidized_recipients", consolidated.columns)
        self.assertEqual(consolidated.loc[0, "loan__subsidized_recipients"], 15)
        self.assertNotIn("loan_direct__subsidized_recipients", consolidated.columns)
        self.assertNotIn("loan_ffel__subsidized_recipients", consolidated.columns)

        summary_row = summary.loc[summary["output_column"] == "loan__subsidized_recipients"].iloc[0]
        self.assertEqual(int(summary_row["rows_with_both_sources"]), 1)


if __name__ == "__main__":
    unittest.main()
