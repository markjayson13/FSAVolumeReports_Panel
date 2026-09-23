from __future__ import annotations

import unittest

import pandas as pd

from helpers import load_script_module

loans = load_script_module("research_loans", "Scripts/fsa_loan_harmonization.py")


class ResearchLoanTests(unittest.TestCase):
    def test_2005_plus_includes_grad_and_preserves_source(self):
        frame = pd.DataFrame({"award_year": ["2005-2006"],
                              "loan_direct__plus_disbursements": [0.0],
                              "loan_direct__grad_plus_disbursements": [245726.25],
                              "loan_direct__plus_recipients": [0],
                              "loan_direct__grad_plus_recipients": [24]})
        out, _ = loans.harmonize_loan_panel(frame)
        self.assertEqual(out.loc[0, "loan_direct_harmonized__plus_disbursements"], 245726.25)
        self.assertEqual(out.loc[0, "loan_direct_harmonized__plus_recipient_count_sum"], 24)
        pd.testing.assert_frame_equal(frame, out[frame.columns])

    def test_schema_requires_missing_split_even_when_column_absent(self):
        frame = pd.DataFrame({"award_year": ["2006-2007"], "loan_direct__parent_plus_disbursements": [2.25]})
        out, _ = loans.harmonize_loan_panel(frame)
        name = "loan_direct_harmonized__plus_disbursements"
        self.assertTrue(pd.isna(out.loc[0, name]))
        self.assertEqual(out.loc[0, name + "__observed_partial_sum"], 2.25)
        self.assertEqual(out.loc[0, name + "__status"], "incomplete_component_sum")

    def test_recipient_overlap_bounds_across_channels(self):
        frame = pd.DataFrame({"award_year": ["2009-2010"],
                              "loan_direct__subsidized_recipients": [149695],
                              "loan_ffel__subsidized_recipients": [330631]})
        out, _ = loans.consolidate_loan_programs(frame)
        self.assertEqual(out.loc[0, "loan__subsidized_recipient_count_sum"], 480326)
        self.assertEqual(out.loc[0, "loan__subsidized_unique_recipient_lower_bound"], 330631)
        self.assertEqual(out.loc[0, "loan__subsidized_unique_recipient_upper_bound"], 480326)
        self.assertNotIn("loan__subsidized_recipients", out)
        self.assertIn("loan_direct__subsidized_recipients", out)

    def test_suppression_blocks_exact_sum_but_can_supply_bounds(self):
        frame = pd.DataFrame({"award_year": ["2018-2019"],
                              "loan_direct__parent_plus_recipients": [15],
                              "loan_direct__grad_plus_recipients": [pd.NA],
                              "loan_direct__grad_plus_recipients__status": ["suppressed_lt10"],
                              "loan_direct__grad_plus_recipients__lower_bound": [0],
                              "loan_direct__grad_plus_recipients__upper_bound": [9]})
        out, _ = loans.consolidate_loan_programs(frame)
        self.assertTrue(pd.isna(out.loc[0, "loan__plus_recipient_count_sum"]))
        self.assertEqual(out.loc[0, "loan__plus_recipient_count_sum__observed_partial_sum"], 15)
        self.assertEqual(out.loc[0, "loan__plus_unique_recipient_lower_bound"], 15)
        self.assertEqual(out.loc[0, "loan__plus_unique_recipient_upper_bound"], 24)

    def test_unknown_component_has_no_finite_upper_bound(self):
        frame = pd.DataFrame({"award_year": ["2018-2019"], "loan_direct__parent_plus_recipients": [15]})
        out, _ = loans.consolidate_loan_programs(frame)
        self.assertTrue(pd.isna(out.loc[0, "loan__plus_unique_recipient_upper_bound"]))

    def test_absent_source_does_not_become_zero(self):
        frame = pd.DataFrame({"award_year": ["2009-2010"], "loan_direct__subsidized_disbursements": [125.75]})
        out, _ = loans.consolidate_loan_programs(frame)
        self.assertTrue(pd.isna(out.loc[0, "loan__subsidized_disbursements"]))
        self.assertEqual(out.loc[0, "loan__subsidized_disbursements__observed_partial_sum"], 125.75)
        self.assertEqual(out.loc[0, "loan__program_scope"], "direct_and_ffel")

    def test_post_2010_scope_explicit_and_does_not_fabricate_ffel(self):
        frame = pd.DataFrame({"award_year": ["2012-2013"], "loan_direct__subsidized_disbursements": [125.75]})
        out, _ = loans.consolidate_loan_programs(frame)
        self.assertEqual(out.loc[0, "loan__subsidized_disbursements"], 125.75)
        self.assertEqual(out.loc[0, "loan__program_scope"], "direct_only_available_report")
        self.assertNotIn("loan_ffel__subsidized_disbursements", out)

    def test_subsidized_level_schema_changes_in_2012(self):
        frame = pd.DataFrame({"award_year": ["2011-2012", "2012-2013"],
                              "loan_direct__subsidized_undergraduate_disbursements": [10.25, pd.NA],
                              "loan_direct__subsidized_graduate_disbursements": [20.5, pd.NA],
                              "loan_direct__subsidized_disbursements": [pd.NA, 35.75]})
        out, _ = loans.consolidate_loan_programs(frame)
        self.assertEqual(out["loan__subsidized_disbursements"].tolist(), [30.75, 35.75])

    def test_unknown_measure_preserved_and_future_schema_flagged(self):
        frame = pd.DataFrame({"award_year": ["2025-2026"], "loan_direct__unexpected_measure": [8],
                              "loan_direct__subsidized_disbursements": [99.5]})
        out, _ = loans.consolidate_loan_programs(frame)
        self.assertEqual(out.loc[0, "loan_direct__unexpected_measure"], 8)
        self.assertTrue(pd.isna(out.loc[0, "loan__subsidized_disbursements"]))
        self.assertEqual(out.loc[0, "loan__subsidized_disbursements__status"], "schema_not_reviewed")

    def test_fractional_count_rejected_not_rounded(self):
        frame = pd.DataFrame({"award_year": ["2009-2010"], "loan_direct__subsidized_recipients": [1.5]})
        with self.assertRaises(ValueError):
            loans.harmonize_loan_panel(frame)

    def test_idempotent_and_all_derived_columns_have_metadata(self):
        frame = pd.DataFrame({"award_year": ["2009-2010"], "loan_direct__subsidized_disbursements": [1.25]})
        first, _ = loans.consolidate_loan_programs(frame)
        second, _ = loans.consolidate_loan_programs(first)
        pd.testing.assert_frame_equal(first, second)
        for col in first.columns.difference(frame.columns):
            self.assertIsNotNone(loans.derived_metadata(col), col)


if __name__ == "__main__":
    unittest.main()
