from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from helpers import load_script_module

integrity = load_script_module("fsa_release_integrity_test", "Scripts/fsa_release_integrity.py")


class ReleaseIntegrityTests(unittest.TestCase):
    def prepare(self, root: Path) -> Path:
        (root / "Checks/acceptance_qc").mkdir(parents=True)
        (root / "Panels/final").mkdir(parents=True)
        (root / "build").mkdir()
        master = root / "Panels/final/master.parquet"
        master.write_bytes(b"original data")
        (root / "build/run_started.json").write_text(json.dumps({"run_id": "run1", "code_and_metadata": {"code": "v1"}, "arguments": {}}))
        integrity.write_transformation_completion(root)
        integrity.write_qa_fingerprints(root)
        return master

    @patch.object(integrity, "pipeline_fingerprints", return_value={"code": "v1"})
    def test_changed_output_rejects_previous_qa(self, _):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = self.prepare(root)
            integrity.require_current_qa(root)
            master.write_bytes(b"changed data")
            with self.assertRaisesRegex(ValueError, "QA is stale"):
                integrity.require_current_qa(root)

    @patch.object(integrity, "pipeline_fingerprints", return_value={"code": "v1"})
    def test_fresh_qa_cannot_certify_code_changed_mid_build(self, mock):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare(root)
            mock.return_value = {"code": "v2"}
            integrity.write_qa_fingerprints(root)
            with self.assertRaisesRegex(ValueError, "changed during the build"):
                integrity.require_current_qa(root)

    @patch.object(integrity, "pipeline_fingerprints", return_value={"code": "v1"})
    def test_partial_or_missing_run_provenance_rejected(self, _):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare(root)
            start = root / "build/run_started.json"
            start.write_text(json.dumps({"code_and_metadata": {"code": "v1"}, "arguments": {"skip_loans": True}}))
            with self.assertRaisesRegex(ValueError, "Partial stage"):
                integrity.require_current_qa(root)
            start.unlink()
            with self.assertRaisesRegex(ValueError, "No orchestrator"):
                integrity.require_current_qa(root)

    @patch.object(integrity, "pipeline_fingerprints", return_value={"code": "v1"})
    def test_new_failed_run_cannot_reuse_old_completion(self, _):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare(root)
            (root / "build/run_started.json").write_text(json.dumps({"run_id": "failed_run2", "code_and_metadata": {"code": "v1"}, "arguments": {}}))
            integrity.write_qa_fingerprints(root)
            with self.assertRaisesRegex(ValueError, "different run"):
                integrity.require_current_qa(root)

    def test_acceptance_requires_explicit_true(self):
        for tokens in ([True, False], ["True", "False "], ["True", "ERROR"], [True, None], []):
            self.assertFalse(integrity.acceptance_all_passed(pd.DataFrame({"passed": tokens})))
        self.assertTrue(integrity.acceptance_all_passed(pd.DataFrame({"passed": [True, True]})))

    def test_scope_requires_complete_inventory_and_recorded_hashes(self):
        with self.assertRaisesRegex(ValueError, "valid recorded SHA256"):
            integrity.require_release_scope(pd.DataFrame([{"filename": "source.xlsx", "sha256": ""}]))
        with self.assertRaisesRegex(ValueError, "configured release scope"):
            integrity.require_release_scope(pd.DataFrame([{"family": "grants", "filename": "source.xlsx", "sha256": "a" * 64,
                "award_year_start": 1999, "award_year": "1999-2000", "selected_for_panel": True, "quarter": ""}]))

    def test_stale_linkage_and_changed_directory_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "Panels/ipeds"
            directory.mkdir(parents=True)
            master = root / "master.parquet"
            master.write_bytes(b"master")
            source = root / "hd.zip"
            source.write_bytes(b"directory")
            artifact = directory / "linked.parquet"
            artifact.write_bytes(b"linked")
            manifest = {"source_panel_sha256": integrity.sha256(master),
                        "linkage_code_sha256": integrity.sha256(integrity.REPO / "Scripts/fsa_ipeds_linkage.py"),
                        "all_original_cells_preserved": True,
                        "artifacts": {"linked": {"path": str(artifact), "sha256": integrity.sha256(artifact)}}}
            (directory / "ipeds_linkage_manifest.json").write_text(json.dumps(manifest))
            pd.DataFrame([{"path": str(source), "sha256": integrity.sha256(source)}]).to_csv(directory / "ipeds_source_manifest.csv", index=False)
            integrity.require_current_linkage(root, master)
            source.write_bytes(b"revised directory")
            with self.assertRaisesRegex(ValueError, "directory input changed"):
                integrity.require_current_linkage(root, master)
            source.write_bytes(b"directory")
            master.write_bytes(b"revised master")
            with self.assertRaisesRegex(ValueError, "different master"):
                integrity.require_current_linkage(root, master)


if __name__ == "__main__":
    unittest.main()
