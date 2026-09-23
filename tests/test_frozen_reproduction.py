"""Fail-closed portability and exact-value checks for the frozen release runner."""
import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Scripts"))
import reproduce_frozen_release as runner


class FrozenReproductionTests(unittest.TestCase):
    def fixture(self, root):
        bundle = root / "replication"
        paths = {
            "source/Scripts/00_run_all.py": b"# frozen\n",
            "source/requirements.txt": b"pandas==2.2.3\n",
            "inputs/ipeds_crosswalks/download_manifest.json": b"{}\n",
            "environment-requirements.txt": b"pandas==2.2.3\n",
            "inputs/fsa/Grant_Volume/2000/downloads/example.xls": b"original workbook bytes",
        }
        for relative, content in paths.items():
            path = bundle / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        raw = bundle / "inputs/fsa/Grant_Volume/2000/downloads/example.xls"
        row = {"family": "grants", "award_year": "2000-2001", "filename": "example.xls",
               "selected_for_panel": "True", "sha256": runner.sha256(raw),
               "filesize_bytes": str(raw.stat().st_size),
               "local_path": "/old/computer/Raw_Title_IV_Reports/Grant_Volume/2000/downloads/example.xls"}
        runner.write_csv(bundle / "selected_panel_files.csv", list(row), [row])
        original = {"inputs": [row], "environment": {"python": "3.13.0", "pandas": "2.2.3"},
                    "code_and_metadata": [{"path": "Scripts/00_run_all.py", "sha256": runner.sha256(bundle / "source/Scripts/00_run_all.py")}],
                    "artifacts": []}
        (bundle / "original_release_manifest.json").write_text(json.dumps(original))
        files = [{"path": p.relative_to(bundle).as_posix(), "sha256": runner.sha256(p),
                  "bytes": p.stat().st_size} for p in bundle.rglob("*") if p.is_file()]
        (bundle / "input_manifest.json").write_text(json.dumps({"schema_version": 1, "files": files}))
        return bundle, original

    def test_rebases_all_runtime_manifests_without_changing_originals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle, _ = self.fixture(root)
            old_hash = runner.sha256(bundle / "selected_panel_files.csv")
            original, records = runner.verify_bundle(bundle)
            output = root / "new machine" / "rebuild"
            fields, rows = runner.staged_inventory(bundle, output, records, original)
            runner.stage_inputs(bundle, output, fields, rows)
            expected = output / "Raw_Title_IV_Reports/Grant_Volume/2000/downloads/example.xls"
            self.assertEqual(rows[0]["local_path"], str(expected))
            self.assertEqual(expected.read_bytes(), b"original workbook bytes")
            manifest = expected.parent.parent / "manifest.csv"
            with manifest.open() as handle:
                self.assertEqual(next(csv.DictReader(handle))["local_path"], str(expected))
            self.assertEqual(runner.sha256(bundle / "selected_panel_files.csv"), old_hash)
            runner.verify_bundle(bundle)

    def test_changed_input_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle, _ = self.fixture(Path(temporary))
            raw = bundle / "inputs/fsa/Grant_Volume/2000/downloads/example.xls"
            raw.write_bytes(b"changed workbook bytes!")
            with self.assertRaisesRegex(ValueError, "mismatch"):
                runner.verify_bundle(bundle)

    def test_unmanifested_selection_input_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle, _ = self.fixture(Path(temporary))
            (bundle / "inputs/ipeds_crosswalks/CW2025.xlsx").write_text("extra")
            with self.assertRaisesRegex(ValueError, "Unmanifested"):
                runner.verify_bundle(bundle)

    def test_frozen_source_must_match_original_release_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle, _ = self.fixture(Path(temporary))
            source = bundle / "source/Scripts/00_run_all.py"
            source.write_text("# substituted pipeline\n")
            manifest = json.loads((bundle / "input_manifest.json").read_text())
            for item in manifest["files"]:
                if item["path"] == "source/Scripts/00_run_all.py":
                    item.update(sha256=runner.sha256(source), bytes=source.stat().st_size)
            (bundle / "input_manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Frozen source differs"):
                runner.verify_bundle(bundle)

    def test_manifest_path_traversal_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for value in ["../escape", "/absolute", "a/../b", "a\\b", "C:/file", "a//b"]:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    runner.safe_member(root, value)
            (root / "link").symlink_to(root.parent, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "Symlink"):
                runner.safe_member(root, "link/target")

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "nonexistent"):
                runner.stage_inputs(root, root, [], [])

    def test_selected_input_metadata_changes_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle, _ = self.fixture(root)
            original, records = runner.verify_bundle(bundle)
            with (bundle / "selected_panel_files.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["selected_for_panel"] = "False"
            runner.write_csv(bundle / "selected_panel_files.csv", list(rows[0]), rows)
            with self.assertRaisesRegex(ValueError, "unselected"):
                runner.staged_inventory(bundle, root / "out", records, original)

    def test_environment_difference_is_explicit(self):
        with patch.object(runner.platform, "python_version", return_value="3.13.1"):
            report = runner.environment_report({"environment": {"python": "3.13.0"}})
        self.assertFalse(report["matches_original_environment"])
        self.assertEqual(report["differences"]["python"]["actual"], "3.13.1")

    def test_verify_only_can_run_inside_bundle_without_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle, _ = self.fixture(Path(temporary))
            previous = Path.cwd()
            try:
                os.chdir(bundle)
                with patch.object(sys, "argv", ["runner", "--bundle", ".", "--verify-only"]), \
                        patch.object(runner, "environment_report", return_value={"differences": {}}):
                    runner.main()
                self.assertFalse((bundle / "unused-verification-output").exists())
            finally:
                os.chdir(previous)

    def test_semantic_compare_only_normalizes_provenance_directories(self):
        import pandas as pd
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            relative = "Panels/example.parquet"
            old, new = root / "original" / relative, root / "rebuilt" / relative
            old.parent.mkdir(parents=True)
            new.parent.mkdir(parents=True)
            frame = pd.DataFrame({"unitid": [123456], "award_year": ["2000-2001"],
                                  "ipeds_source_path": ["/old/HD2000.zip"], "amount": [10.25]})
            frame.to_parquet(old, index=False)
            frame["ipeds_source_path"] = "/new/HD2000.zip"
            frame.to_parquet(new, index=False)
            original = {"artifacts": [{"path": relative, "sha256": runner.sha256(old)}]}
            with patch.object(runner, "COMPARISONS", {relative: ["unitid", "award_year"]}):
                result = runner.compare_reference(root / "rebuilt", root / "original", original)
                self.assertTrue(result["passed"])
                self.assertEqual(result["artifacts"][0]["normalized_path_columns"], ["ipeds_source_path"])
                frame["amount"] = 10.250000001
                frame.to_parquet(new, index=False)
                with self.assertRaises(AssertionError):
                    runner.compare_reference(root / "rebuilt", root / "original", original)


if __name__ == "__main__":
    unittest.main()
