from __future__ import annotations

import tempfile
import unittest
import hashlib
import json
from pathlib import Path

import pandas as pd

from helpers import load_script_module

observations = load_script_module("adversarial_observations", "Scripts/fsa_observations.py")
outputs = load_script_module("adversarial_outputs", "Scripts/fsa_research_outputs.py")
loans = load_script_module("adversarial_loans", "Scripts/fsa_loan_harmonization.py")


class ResearchAcceptanceAdversarialTests(unittest.TestCase):
    def build_fixture(self, root: Path) -> Path:
        panel = pd.DataFrame({"opeid8": ["00100200"], "opeid6": ["001002"], "award_year": ["2009-2010"],
                              "grant__school": ["Fixture College"], "descriptor_review_required": [False]})
        for descriptor in outputs.DESCRIPTORS:
            panel[descriptor + "__review_required"] = False
        measures = {"grants": "pell_recipients", "campus_based": "fws_recipients",
                    "direct_loans": "subsidized_recipients", "ffel": "subsidized_recipients"}
        for family, prefix in outputs.SOURCE_PREFIXES.items():
            canonical = measures[family]
            value = "<10" if family == "grants" else "5"
            mapped = pd.DataFrame({"opeid8": ["100200", None], "school": ["Fixture College", "TOTAL"], canonical: [value, "5"]})
            entry = {"family": family, "award_year": "2009-2010", "filename": family + ".xls"}
            audit = observations.audit_source_observations(mapped, entry, [5, 6])
            observations.write_family_audits(root, family, [audit])
            column = prefix + canonical
            parsed = observations.parse_measure(pd.Series([value]), canonical)
            panel[column] = parsed.value
            panel[prefix + "source_record_present"] = True
            for metadata in ("status", "raw_token", "lower_bound", "upper_bound"):
                panel[column + "__" + metadata] = parsed[metadata]
            pd.DataFrame({"column": [column], "award_year": ["2009-2010"]}).to_csv(
                root / "Checks/observation_qc" / (family + "_schema_availability.csv"), index=False)
        panel, _ = loans.consolidate_loan_programs(panel)
        out = root / "panel.parquet"
        panel.to_parquet(out, index=False)
        (root / "Dictionary").mkdir()
        pd.DataFrame({"panel_column": list(panel), "column_role": [outputs.column_role(c) for c in panel],
                      "definition": ["Fixture definition"] * len(panel.columns)}).to_parquet(
            root / "Dictionary/fsa_volume_panel_dictionary.parquet", index=False)
        (root / "Checks/panel_qc").mkdir()
        for name in ("final_descriptor_manual_review", "descriptor_overrides_applied"):
            pd.DataFrame(columns=["opeid8", "award_year", "descriptor"]).to_csv(root / "Checks/panel_qc" / (name + ".csv"), index=False)
        return out

    def assert_rejected_after_mutation(self, column: str, value: object):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.build_fixture(root)
            baseline = outputs.research_acceptance(root, path)
            self.assertTrue(baseline.passed.all(), baseline.loc[~baseline.passed].to_dict("records"))
            panel = pd.read_parquet(path)
            panel.loc[0, column] = value
            panel.to_parquet(path, index=False)
            result = outputs.research_acceptance(root, path)
            self.assertFalse(result.passed.all(), column)

    def test_acceptance_rejects_corrupted_suppression_bound(self):
        self.assert_rejected_after_mutation("grant__pell_recipients__upper_bound", 100)

    def test_acceptance_rejects_disappeared_exceptional_raw_token(self):
        self.assert_rejected_after_mutation("grant__pell_recipients__raw_token", pd.NA)

    def test_acceptance_rejects_corrupted_derived_total(self):
        self.assert_rejected_after_mutation("loan__subsidized_recipient_count_sum", 0)

    def test_acceptance_rejects_corrupted_derived_overlap_bound(self):
        self.assert_rejected_after_mutation("loan__subsidized_unique_recipient_lower_bound", 10)

    def test_acceptance_rejects_unpopulated_value_status(self):
        self.assert_rejected_after_mutation("loan__subsidized_recipient_count_sum__status", pd.NA)

    def test_acceptance_rejects_inconsistent_descriptor_flag(self):
        self.assert_rejected_after_mutation("state__review_required", True)

    def test_acceptance_rejects_uncleared_review_marked_clear(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.build_fixture(root)
            pd.DataFrame({"opeid8": ["00100200"], "award_year": ["2009-2010"], "descriptor": ["state"]}).to_csv(
                root / "Checks/panel_qc/final_descriptor_manual_review.csv", index=False)
            result = outputs.research_acceptance(root, path).set_index("check")
            self.assertFalse(result.loc["research::descriptor_review_flags_match_ledgers", "passed"])

    def test_acceptance_rejects_unaccounted_anonymous_numeric_row(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.build_fixture(root)
            ledger_path = root / "Checks/observation_qc/grants_row_ledger.parquet"
            ledger = pd.read_parquet(ledger_path)
            extra = ledger.iloc[[-1]].copy()
            extra["row_class"] = "ambiguous_numeric_row"
            extra["school"] = None
            extra["source_excel_row"] = 7
            pd.concat([ledger, extra], ignore_index=True).to_parquet(ledger_path, index=False)
            result = outputs.research_acceptance(root, path).set_index("check")
            self.assertFalse(result.loc["research::grants_no_unresolved_anonymous_numeric_rows", "passed"])

    def test_suppression_does_not_hide_impossible_count_total(self):
        for total in (100, 130):
            with self.subTest(total=total):
                mapped = pd.DataFrame({"opeid8": [100200, 100300, None], "school": ["A", "B", "TOTAL"],
                                       "pell_recipients": [120, "<10", total]})
                audit = observations.audit_source_observations(mapped, {"family": "grants", "award_year": "2009-2010", "filename": "test.xls"}, [1, 2, 3])
                self.assertEqual(audit["reconciliation"].iloc[0].reconciliation_status, "mismatch_count_bounds")

    def test_unknown_count_has_unbounded_upper_total(self):
        mapped = pd.DataFrame({"opeid8": [100200, 100300, None], "school": ["A", "B", "TOTAL"],
                               "pell_recipients": [120, "-", 10000]})
        audit = observations.audit_source_observations(mapped, {"family": "grants", "award_year": "2009-2010", "filename": "test.xls"}, [1, 2, 3])
        self.assertEqual(audit["reconciliation"].iloc[0].reconciliation_status, "incomplete_source_cells")
        self.assertTrue(pd.isna(audit["reconciliation"].iloc[0].institution_count_upper_bound))

    def test_recovered_missing_raw_id_requires_evidence_and_final_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "Checks/download_qc").mkdir(parents=True)
            source_path = root / "raw.xls"
            source_path.write_bytes(b"immutable source fixture")
            digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
            entry = {"family": "grants", "award_year": "2009-2010", "filename": "raw.xls",
                     "local_path": str(source_path), "sha256": digest}
            pd.DataFrame([entry]).to_csv(root / "Checks/download_qc/selected_panel_files.csv", index=False)
            evidence = [{"kind": "same_award_year_fsa_full_opeid", "family": "direct_loans", "award_year": "2009-2010", "opeid8": "00100200", "url": "https://example.test/fsa", "sha256": "a" * 64},
                        {"kind": "same_year_official_ipeds_directory", "ipeds_year": 2009, "opeid8": "00100200", "url": "https://example.test/hd", "sha256": "b" * 64}]
            registry = root / "resolutions.csv"
            pd.DataFrame([{**entry, "resolution_id": "verified_5", "source_sha256": digest, "source_sheet": "Aid",
                           "source_excel_row": 5, "resolution_status": "approved", "recovered_opeid8": "00100200",
                           "expected_raw_opeid": "", "expected_school": "Fixture College", "expected_state": "AL", "expected_zip_code": "",
                           "evidence_json": json.dumps(evidence)}]).to_csv(registry, index=False)
            mapped = pd.DataFrame({"opeid8": [None], "school": ["Fixture College"], "state": ["AL"], "pell_recipients": [5]})
            audit = observations.audit_source_observations(mapped, entry, [5], resolved_ids=pd.Series(["00100200"], dtype="string"),
                                                           resolution_ids=pd.Series(["verified_5"], dtype="string"))
            panel = pd.DataFrame({"opeid8": ["00100200"], "award_year": ["2009-2010"], "grant__raw_opeid": [None],
                                  "grant__source_identity_resolution": ["verified_5"]})
            schema = pd.DataFrame({"award_year": ["2009-2010"], "column": ["grant__pell_recipients"], "filename": ["raw.xls"], "sheet": ["Aid"]})
            result = outputs.audit_source_identity_conservation(audit["row_ledger"], panel, "grants", root, schema, identity_ledger_path=registry)
            self.assertTrue(result.passed.all(), result.to_dict("records"))
            panel.loc[0, "grant__source_identity_resolution"] = "invented"
            result = outputs.audit_source_identity_conservation(audit["row_ledger"], panel, "grants", root, schema, identity_ledger_path=registry)
            self.assertFalse(result.passed.all())
            panel.loc[0, "grant__source_identity_resolution"] = "verified_5"
            source_path.write_bytes(b"altered source")
            result = outputs.audit_source_identity_conservation(audit["row_ledger"], panel, "grants", root, schema, identity_ledger_path=registry)
            self.assertFalse(result.passed.all())

    def test_unsupported_normalized_id_in_saved_ledger_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.build_fixture(root)
            ledger_path = root / "Checks/observation_qc/grants_row_ledger.parquet"
            ledger = pd.read_parquet(ledger_path)
            ledger.loc[0, "normalized_opeid8"] = "00999900"
            ledger.to_parquet(ledger_path, index=False)
            results = outputs.research_acceptance(root, path)
            identity_checks = results[results.check.str.contains("grants.*source_identity_evidence_conserved", regex=True)]
            self.assertFalse(identity_checks.passed.all())


if __name__ == "__main__":
    unittest.main()
