from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from helpers import load_script_module

identity = load_script_module("fsa_identity_resolution_tests", "Scripts/fsa_identity_resolutions.py")


class IdentityResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "resolutions.csv"
        self.entry = {"family": "grants", "award_year": "2002-2003", "filename": "grants.xls", "sha256": "a" * 64}
        self.frame = pd.DataFrame({"opeid8": ["", "100200"], "school": ["Branch College", "Other College"],
                                   "state": ["PA", "AL"], "zip_code": ["", "35811"],
                                   "pell_disbursements": ["1234.56", "25.23"]}, index=[4, 8])
        self.evidence = [
            {"kind": "same_award_year_fsa_full_opeid", "family": "ffel", "award_year": "2002-2003",
             "opeid8": "00338000", "url": "https://studentaid.gov/sites/default/files/loans.xls", "sha256": "b" * 64},
            {"kind": "same_year_official_ipeds_directory", "ipeds_year": 2002, "unitid": 215266,
             "opeid8": "00338000", "url": "https://nces.ed.gov/ipeds/datacenter/data/HD2002.zip", "sha256": "c" * 64},
        ]
        self.record = {"resolution_id": "grants_2002_10", **{k: self.entry[k] for k in ["family", "award_year", "filename"]},
                       "source_sha256": "a" * 64, "source_sheet": "AY 2002-2003", "source_excel_row": "10",
                       "expected_raw_opeid": "", "expected_school": "Branch College", "expected_state": "PA",
                       "expected_zip_code": "", "resolution_status": "approved", "recovered_opeid8": "00338000",
                       "evidence_json": json.dumps(self.evidence)}

    def resolve(self, records=None, frame=None, entry=None, rows=None, sheet="AY 2002-2003"):
        pd.DataFrame(records or [self.record]).to_csv(self.path, index=False)
        return identity.resolve_source_identities(self.frame if frame is None else frame,
                                                  self.entry if entry is None else entry,
                                                  [10, 11] if rows is None else rows, sheet, self.path)

    def test_recovery_preserves_raw_id_and_every_measure_cell(self):
        original = self.frame.copy(deep=True)
        ids, references = self.resolve()
        self.assertEqual(ids.tolist(), ["00338000", "00100200"])
        self.assertEqual(references.loc[4], "grants_2002_10")
        self.assertTrue(pd.isna(references.loc[8]))
        pd.testing.assert_frame_equal(self.frame, original)

    def test_stale_source_hash_sheet_and_row_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "source vintage changed"):
            self.resolve(entry={**self.entry, "sha256": "d" * 64})
        with self.assertRaisesRegex(ValueError, "source vintage changed"):
            self.resolve(sheet="Quarterly activity")
        for rows in ([12, 13], [10, 10]):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, "one source row"):
                self.resolve(rows=rows)

    def test_raw_descriptor_change_cannot_reuse_reviewed_identity(self):
        for column, value in [("opeid8", "0"), ("school", "A different campus"), ("state", "NY"), ("zip_code", "12345")]:
            changed = self.frame.copy()
            changed.loc[4, column] = value
            with self.subTest(column=column), self.assertRaisesRegex(ValueError, "raw .* changed"):
                self.resolve(frame=changed)

    def test_recovery_cannot_collide_with_existing_or_second_recovered_row(self):
        changed = self.frame.copy()
        changed.loc[8, "opeid8"] = "338000"
        with self.assertRaisesRegex(ValueError, "collides"):
            self.resolve(frame=changed)
        changed = self.frame.copy()
        changed.loc[8, ["opeid8", "school", "state", "zip_code"]] = ["", "Another branch", "PA", ""]
        second = {**self.record, "resolution_id": "grants_2002_11", "source_excel_row": "11", "expected_school": "Another branch"}
        with self.assertRaisesRegex(ValueError, "collides"):
            self.resolve(records=[self.record, second], frame=changed)

    def test_existing_valid_identifier_cannot_be_overwritten(self):
        changed = self.frame.copy()
        changed.loc[4, "opeid8"] = "338100"
        reviewed = {**self.record, "expected_raw_opeid": "338100"}
        with self.assertRaisesRegex(ValueError, "replace a valid"):
            self.resolve(records=[reviewed], frame=changed)

    def test_both_sources_must_support_same_full_id_and_same_award_year(self):
        changes = [(0, "opeid8", "00338100"), (1, "opeid8", "00338100"),
                   (0, "family", "grants"), (1, "ipeds_year", 2003),
                   (0, "award_year", "2001-2002"), (0, "award_year", None),
                   (0, "sha256", "bad digest"), (1, "url", "")]
        for index, field, value in changes:
            ev = copy.deepcopy(self.evidence)
            if value is None:
                ev[index].pop(field)
            else:
                ev[index][field] = value
            record = {**self.record, "evidence_json": json.dumps(ev)}
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.resolve(records=[record])
        for missing in [0, 1]:
            ev = copy.deepcopy(self.evidence)
            ev.pop(missing)
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, "requires contemporaneous"):
                self.resolve(records=[{**self.record, "evidence_json": json.dumps(ev)}])

    def test_unresolved_unitid_evidence_does_not_invent_an_opeid(self):
        orphan = {**self.record, "resolution_status": "unresolved", "recovered_opeid8": "",
                  "verified_unitid": "215266", "unitid_resolution_status": "verified_component_identity_opeid_unresolved"}
        ids, references = self.resolve(records=[orphan])
        self.assertTrue(pd.isna(ids.loc[4]))
        self.assertTrue(references.isna().all())

    def test_frozen_recovery_ledger_has_distinct_evidence_levels(self):
        ledger = pd.read_csv(identity.LEDGER, dtype=str, keep_default_na=False)
        self.assertFalse(ledger.duplicated(["family", "award_year", "filename", "source_excel_row"]).any())
        approved = ledger[ledger.resolution_status.eq("approved")]
        self.assertEqual(len(approved), 34)
        self.assertAlmostEqual(pd.to_numeric(approved.pell_disbursements).sum(), 29648694.58, places=2)
        for row in approved.to_dict("records"):
            ev = json.loads(row["evidence_json"])
            corroboration = [x for x in ev if x["kind"] == "same_award_year_fsa_full_opeid"]
            self.assertTrue(corroboration)
            for item in corroboration:
                self.assertEqual(item["award_year"], row["award_year"])
                self.assertEqual(item["opeid8"], row["recovered_opeid8"])
                self.assertNotEqual(item["family"], row["family"])
                self.assertGreater(int(item["excel_row"]), 0)
        orphan = ledger[ledger.unitid_resolution_status.eq("verified_component_identity_opeid_unresolved")]
        self.assertEqual(len(orphan), 16)
        self.assertTrue(orphan.recovered_opeid8.eq("").all())
        self.assertTrue(orphan.resolution_status.eq("unresolved").all())
        self.assertTrue(orphan.existing_grant_unitid_collision_count.eq("0").all())
        self.assertFalse(orphan.duplicated(["verified_unitid", "award_year", "family"]).any())


if __name__ == "__main__":
    unittest.main()
