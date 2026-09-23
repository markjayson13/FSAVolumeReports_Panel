from __future__ import annotations

import unittest

import pandas as pd

from helpers import load_script_module


utils = load_script_module("fsa_build_utils_loan_harmonization", "Scripts/fsa_build_utils.py")


class LoanHarmonizationTests(unittest.TestCase):
    def test_harmonize_loan_panel_preserves_sources_and_uses_year_specific_plus(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "opeid8": "00100000",
                    "award_year": "2005-2006",
                    "loan_direct__plus_recipients": 10,
                    "loan_direct__parent_plus_recipients": pd.NA,
                    "loan_direct__grad_plus_recipients": 3,
                    "loan_direct__plus_loans_originated_n": 12,
                    "loan_direct__parent_plus_loans_originated_n": pd.NA,
                    "loan_direct__grad_plus_loans_originated_n": 4,
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
        self.assertEqual(harmonized["loan_direct_harmonized__plus_recipient_count_sum"].tolist(), [13, 10])
        self.assertEqual(harmonized["loan_direct_harmonized__plus_loans_originated_n"].tolist(), [16, 12])
        pd.testing.assert_frame_equal(frame, harmonized[frame.columns])

        summary_row = summary.loc[(summary["output_column"] == "loan_direct_harmonized__plus_recipient_count_sum") &
                                  (summary["award_year_start"] == 2005)].iloc[0]
        self.assertEqual(int(summary_row["rows_complete"]), 1)
        self.assertEqual(summary_row["source_columns"], "loan_direct__plus_recipients|loan_direct__grad_plus_recipients")

    def test_consolidate_loan_programs_preserves_channels_and_identifies_recipient_sum(self) -> None:
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
        self.assertIn("loan__subsidized_recipient_count_sum", consolidated.columns)
        self.assertEqual(consolidated.loc[0, "loan__subsidized_recipient_count_sum"], 15)
        self.assertIn("loan_direct__subsidized_recipients", consolidated.columns)
        self.assertIn("loan_ffel__subsidized_recipients", consolidated.columns)
        self.assertNotIn("loan__subsidized_recipients", consolidated.columns)
        self.assertEqual(consolidated.loc[0, "loan__subsidized_unique_recipient_lower_bound"], 10)
        self.assertEqual(consolidated.loc[0, "loan__subsidized_unique_recipient_upper_bound"], 15)

        summary_row = summary.loc[summary["output_column"] == "loan__subsidized_recipient_count_sum"].iloc[0]
        self.assertEqual(int(summary_row["rows_with_both_sources"]), 1)


if __name__ == "__main__":
    unittest.main()
