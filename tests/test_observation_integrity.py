from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import pandas as pd

from helpers import load_script_module, write_workbook
from fsa_observations import normalize_full_opeid, normalize_root_opeid, parse_measure, audit_source_observations, source_row_classes
from fsa_research_outputs import apply_descriptor_overrides

u = load_script_module("fsa_integrity_utils", "Scripts/fsa_build_utils.py")


class ObservationIntegrityTests(unittest.TestCase):
    def test_full_id_numeric_and_text_sources_merge_to_same_institution(self):
        for raw in (100200, 100200.0, "100200", "100200.0", "00100200"):
            self.assertEqual(normalize_full_opeid(raw), "00100200")
        self.assertEqual(normalize_full_opeid(105901), "00105901")
        self.assertEqual(normalize_root_opeid(1002), "001002")
        for raw in ("1e5", "100200.5", "00100200X", "123456789", -100200, "00000000", "id100200", True):
            self.assertIsNone(normalize_full_opeid(raw))
        left = pd.DataFrame({"opeid8": [u.standardize_opeid8(100200)], "award_year": ["1999-2000"], "pell": [100.12]})
        right = pd.DataFrame({"opeid8": [u.standardize_opeid8("00100200")], "award_year": ["1999-2000"], "loans": [200.23]})
        self.assertEqual(len(u.outer_merge_panels(left, right)), 1)

    def test_currency_and_suppression_are_not_rounded_or_imputed(self):
        money = parse_measure(pd.Series(["$1,234.56", "($12.34)", "-", "Privacy Redacted", "", "garbage"]), "pell_disbursements")
        self.assertEqual(money.value.iloc[0], 1234.56)
        self.assertEqual(money.value.iloc[1], -12.34)
        self.assertEqual(money.status.tolist(), ["observed", "observed", "source_symbol", "suppressed", "source_blank", "invalid_numeric"])
        counts = parse_measure(pd.Series(["<10", "0", "9", "1.2", "-2"]), "pell_recipients")
        self.assertTrue(pd.isna(counts.value.iloc[0]))
        self.assertEqual((counts.lower_bound.iloc[0], counts.upper_bound.iloc[0]), (0, 9))
        self.assertEqual(counts.status.iloc[3], "invalid_fractional_count")
        self.assertEqual(counts.status.iloc[4], "invalid_negative_count")

    def test_rejected_institution_amounts_account_for_raw_totals(self):
        mapped = pd.DataFrame({"opeid8": ["100200", "", ""], "school": ["A&M", "Unresolved branch", "TOTAL"],
                               "pell_disbursements": ["100.12", "25.23", "125.35"]})
        entry = {"family": "grants", "award_year": "1999-2000", "filename": "test.xls"}
        audit = audit_source_observations(mapped, entry, [10, 11, 12])
        self.assertEqual(len(audit["quarantine"]), 1)
        row = audit["reconciliation"].iloc[0]
        self.assertEqual(row.reconciliation_status, "pass")
        self.assertAlmostEqual(row.quarantined_known_sum, 25.23)
        self.assertEqual(audit["quarantine"].source_excel_row.iloc[0], 11)
        mapped.loc[2, "pell_disbursements"] = "130.35"
        self.assertEqual(audit_source_observations(mapped, entry, [10,11,12])["reconciliation"].iloc[0].reconciliation_status, "mismatch")

    def test_total_label_cannot_become_institution_from_numeric_id(self):
        frame = pd.DataFrame({"opeid8": ["12345600"], "school": ["TOTAL"]})
        self.assertEqual(source_row_classes(frame).iloc[0], "reported_total")

    def test_anonymous_final_numeric_row_is_candidate_not_published_total(self):
        mapped = pd.DataFrame({"opeid8": ["100200", "", ""], "school": ["A&M", "Unresolved branch", ""],
                               "pell_disbursements": ["100.12", "25.23", "125.35"]})
        entry = {"family": "grants", "award_year": "1999-2000", "filename": "test.xls"}
        audit = audit_source_observations(mapped, entry, [10, 11, 12])
        self.assertEqual(audit["row_ledger"].row_class.iloc[-1], "unlabeled_numeric_summary_candidate")
        self.assertEqual(len(audit["quarantine"]), 1)
        row = audit["reconciliation"].iloc[0]
        self.assertTrue(pd.isna(row.reported_total))
        self.assertEqual(row.reported_total_count, 0)
        self.assertEqual(row.reconciliation_status, "candidate_matches_known_sum")
        self.assertEqual(row.summary_candidate_excel_rows, "12")
        self.assertAlmostEqual(row.summary_candidate_value, 125.35)
        mapped.loc[2, "pell_disbursements"] = "130.35"
        bad = audit_source_observations(mapped, entry, [10, 11, 12])["reconciliation"].iloc[0]
        self.assertEqual(bad.reconciliation_status, "mismatch_candidate_complete")

    def test_anonymous_midtable_row_requires_review(self):
        mapped = pd.DataFrame({"opeid8": ["100200", "", "100300"], "school": ["A&M", "", "B"],
                               "pell_recipients": ["5", "20", "5"]})
        self.assertEqual(source_row_classes(mapped).iloc[1], "ambiguous_numeric_row")
        audit = audit_source_observations(mapped, {"family": "grants", "award_year": "1999-2000", "filename": "test.xls"}, [10, 11, 12])
        self.assertEqual(audit["reconciliation"].ambiguous_numeric_rows.iloc[0], 1)
        self.assertEqual(audit["reconciliation"].summary_candidate_count.iloc[0], 0)

    def test_candidate_requires_every_descriptor_blank(self):
        mapped = pd.DataFrame({"opeid8": ["100200", ""], "school": ["A&M", ""], "state": ["AL", "WY"],
                               "pell_recipients": ["5", "5"]})
        self.assertEqual(source_row_classes(mapped).iloc[-1], "ambiguous_numeric_row")

    def test_candidate_with_unknown_cells_never_certifies_complete_total(self):
        mapped = pd.DataFrame({"opeid8": ["100200", "100300", ""], "school": ["A&M", "B", ""],
                               "pell_recipients": ["5", "<10", "5"]})
        entry = {"family": "grants", "award_year": "1999-2000", "filename": "test.xls"}
        row = audit_source_observations(mapped, entry, [10, 11, 12])["reconciliation"].iloc[0]
        self.assertEqual(row.reconciliation_status, "candidate_incomplete_source_cells")
        mapped.loc[2, "pell_recipients"] = "20"
        bad = audit_source_observations(mapped, entry, [10, 11, 12])["reconciliation"].iloc[0]
        self.assertEqual(bad.reconciliation_status, "mismatch_candidate_count_bounds")

    def test_excel_row_provenance_survives_blank_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write_workbook(Path(tmp)/"source.xlsx", {"Data": [
                ["OPE ID", "School"], [100200, "A&M"], [], [105901, "Branch"]]})
            result = u.parse_selected_sheet(p, "grants", "annual")
            self.assertEqual(result.frame.attrs["excel_rows"], [2,4])

    def test_missing_workbook_profile_fails_source_qa(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = u.ensure_data_layout(tmp)
            source = Path(tmp)/"placeholder.xls"; source.write_text("placeholder")
            pd.DataFrame([{"family":"grants", "filename":"placeholder.xls", "local_path":str(source), "award_year_start":1999}]).to_csv(layout.checks/"download_qc/selected_panel_files.csv",index=False)
            pd.DataFrame([{"family":"grants", "filename":"different.xls", "selected_sheet":"Data", "parse_warnings_json":"[]"}]).to_csv(layout.checks/"source_qc/workbook_profiles.csv",index=False)
            result = u.source_qaqc(tmp).set_index("check")
            self.assertFalse(result.loc["selected_sheet_found_for_selected_files", "passed"])

    def test_override_requires_exact_target_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"overrides.csv"
            pd.DataFrame([{"opeid8":"00100200","award_year":"1999-2000","descriptor":"state","value":"AL",
                "evidence_url":"https://nces.ed.gov/example","reviewed_by":"reviewer","reviewed_at":"2026-09-22"}]).to_csv(p,index=False)
            panel=pd.DataFrame({"opeid8":["00100200"],"award_year":["1999-2000"],"state":["XX"],"state__review_required":[True]})
            result,audit=apply_descriptor_overrides(panel,p)
            self.assertEqual(result.state.iloc[0],"AL"); self.assertFalse(result.state__review_required.iloc[0])
            self.assertEqual(audit.previous_value.iloc[0],"XX")
            panel.loc[0,"opeid8"]="00100300"
            with self.assertRaises(ValueError): apply_descriptor_overrides(panel,p)


if __name__ == "__main__":
    unittest.main()
