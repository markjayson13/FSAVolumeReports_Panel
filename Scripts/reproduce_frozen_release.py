#!/usr/bin/env python3
"""Verify a frozen replication bundle and rebuild it in a new local directory.

This wrapper uses the original, unmodified pipeline inside ``bundle/source``.
It does not download or refresh data, rewrite cached source bytes, or modify an
existing output directory. See Documentation/reproduce_release.md.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

COMPARISONS = {
    "Panels/final/fsa_volume_reports_panel_1999_2025.parquet": ["opeid8", "award_year"],
    "Panels/ipeds/fsa_ipeds_bridge.parquet": ["opeid8", "award_year"],
    "Panels/ipeds/unitid_research/fsa_unitid_award_year_panel.parquet": ["unitid", "award_year"],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_member(root: Path, value: str) -> Path:
    """Accept only portable, nonsymlink paths strictly below a bundle root."""
    relative = PurePosixPath(value)
    if (not value or relative.is_absolute() or ".." in relative.parts
            or "\\" in value or ":" in value or relative.as_posix() != value):
        raise ValueError(f"Unsafe or noncanonical bundle path: {value!r}")
    result = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Symlink is not allowed in bundle: {value}")
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Bundle path escapes root: {value}")
    return result


def verify_bundle(bundle: Path) -> tuple[dict, dict[str, dict]]:
    manifest = json.loads((bundle / "input_manifest.json").read_text())
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), list):
        raise ValueError("Unsupported input_manifest.json schema")
    records = {}
    for item in manifest["files"]:
        relative = item["path"]
        path = safe_member(bundle, relative)
        if relative in records:
            raise ValueError(f"Duplicate manifest path: {relative}")
        if not path.is_file():
            raise ValueError(f"Missing bundle file: {relative}")
        if (isinstance(item.get("bytes"), bool) or not isinstance(item.get("bytes"), int)
                or item["bytes"] != path.stat().st_size):
            raise ValueError(f"Size mismatch: {relative}")
        if re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))) is None:
            raise ValueError(f"Invalid recorded SHA256: {relative}")
        if sha256(path) != item["sha256"]:
            raise ValueError(f"SHA256 mismatch: {relative}")
        records[relative] = item
    required = {"original_release_manifest.json", "selected_panel_files.csv",
                "source/Scripts/00_run_all.py", "source/requirements.txt",
                "environment-requirements.txt", "inputs/ipeds_crosswalks/download_manifest.json"}
    if required - records.keys():
        raise ValueError(f"Missing required manifest entries: {sorted(required - records.keys())}")
    # Extra source/input files can change glob-based source selection. Require
    # coverage of every input and frozen-source file, excluding Python caches.
    for directory in ("inputs", "source"):
        for path in (bundle / directory).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                relative = path.relative_to(bundle).as_posix()
                if relative not in records:
                    raise ValueError(f"Unmanifested bundle file: {relative}")
    original = json.loads((bundle / "original_release_manifest.json").read_text())
    for item in original["code_and_metadata"]:
        record = records.get("source/" + item["path"])
        if record is None or record["sha256"] != item["sha256"]:
            raise ValueError(f"Frozen source differs from original release: {item['path']}")
    return original, records


def environment_report(original: dict) -> dict:
    expected = original["environment"]
    actual = {"python": platform.python_version()}
    for package in expected:
        if package != "python":
            try:
                actual[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                actual[package] = None
    differences = {k: {"expected": v, "actual": actual[k]}
                   for k, v in expected.items() if actual[k] != v}
    return {"expected": expected, "actual": actual, "differences": differences,
            "matches_original_environment": not differences}


def fsa_relative_path(value: str) -> PurePosixPath:
    """Extract the preserved location below the old Raw_Title_IV_Reports root."""
    parts = PurePosixPath(value.replace("\\", "/")).parts
    if parts.count("Raw_Title_IV_Reports") != 1:
        raise ValueError(f"Inventory path lacks one Raw_Title_IV_Reports anchor: {value}")
    relative = PurePosixPath(*parts[parts.index("Raw_Title_IV_Reports") + 1:])
    if not relative.parts or ".." in relative.parts:
        raise ValueError(f"Unsafe FSA inventory path: {value}")
    return relative


def staged_inventory(bundle: Path, output: Path, records: dict[str, dict], original: dict) -> tuple[list[str], list[dict]]:
    with (bundle / "selected_panel_files.csv").open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    if not fields or "local_path" not in fields:
        raise ValueError("Selected inventory has no local_path column")
    original_inputs = {(r["family"], r["award_year"], r["filename"]): r for r in original["inputs"]}
    seen = set()
    for row in rows:
        key = (row["family"], row["award_year"], row["filename"])
        if key in seen or key not in original_inputs:
            raise ValueError(f"Duplicate or unexpected selected input: {key}")
        seen.add(key)
        if str(row["selected_for_panel"]).lower() != "true":
            raise ValueError(f"Inventory includes an unselected input: {key}")
        relative = fsa_relative_path(row["local_path"])
        record = records.get("inputs/fsa/" + relative.as_posix())
        old = original_inputs[key]
        if (record is None or record["sha256"] != row["sha256"]
                or record["sha256"] != old["sha256"]
                or record["bytes"] != int(row["filesize_bytes"])):
            raise ValueError(f"Selected input does not match original bytes: {key}")
        # All selection semantics must match, not just the chosen file hash.
        for field in fields:
            if field != "local_path" and str(old.get(field, "")) != row[field]:
                raise ValueError(f"Selected inventory changed {field} for {key}")
        row["local_path"] = str(output / "Raw_Title_IV_Reports" / relative)
    if seen != set(original_inputs):
        raise ValueError("Selected inventory does not cover all original release inputs")
    return fields, rows


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def stage_inputs(bundle: Path, output: Path, fields: list[str], rows: list[dict]) -> None:
    if output.exists():
        raise ValueError(f"Output must be a new, nonexistent directory: {output}")
    output.mkdir(parents=True)
    groups = defaultdict(list)
    for row in rows:
        destination = Path(row["local_path"])
        relative = destination.relative_to(output / "Raw_Title_IV_Reports")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundle / "inputs/fsa" / relative, destination)
        # Profiles read these per-year manifests; subsequent stages use the
        # selected inventory. Neither requires unselected upstream workbooks.
        groups[destination.parent.parent / "manifest.csv"].append(row)
    for path, group in groups.items():
        write_csv(path, fields, group)
    write_csv(output / "Checks/download_qc/selected_panel_files.csv", fields, rows)


def compare_reference(output: Path, reference: Path, original: dict) -> dict:
    """Check every canonical panel cell; normalize only two provenance paths."""
    import pandas as pd

    expected_hashes = {r["path"]: r["sha256"] for r in original["artifacts"]}
    results = []
    for relative, keys in COMPARISONS.items():
        old_path, new_path = reference / relative, output / relative
        if sha256(old_path) != expected_hashes[relative]:
            raise ValueError(f"Reference is not the published original artifact: {relative}")
        left, right = pd.read_parquet(old_path), pd.read_parquet(new_path)
        if left.duplicated(keys).any() or right.duplicated(keys).any():
            raise ValueError(f"Duplicate comparison keys in {relative}")
        left = left.sort_values(keys).reset_index(drop=True)
        right = right.sort_values(keys).reset_index(drop=True)
        pd.testing.assert_series_equal(left.dtypes, right.dtypes)
        normalized = []
        for column in left.columns:
            if column in right and (column in {"ipeds_source_path", "cw_source_path"}
                                    or column.endswith(("__ipeds_source_path", "__cw_source_path"))):
                normalized.append(column)
                for frame in (left, right):
                    frame[column] = frame[column].map(
                        lambda x: Path(x).name if isinstance(x, str) and x else x)
        pd.testing.assert_frame_equal(left, right, check_exact=True, check_dtype=True)
        results.append({"path": relative, "rows": len(left), "columns": len(left.columns),
                        "keys": keys, "all_cells_equal": True,
                        "normalized_path_columns": normalized,
                        "reference_sha256": sha256(old_path), "rebuilt_sha256": sha256(new_path),
                        "byte_identical": sha256(old_path) == sha256(new_path)})
    return {"passed": True, "comparison": "all cells, exact dtypes and values; only HD/CW path directories normalized",
            "artifacts": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True, help="Extracted replication directory")
    parser.add_argument("--output", type=Path, help="New directory for the rebuilt release")
    parser.add_argument("--reference-root", type=Path, help="Optional original core directory containing Panels/")
    parser.add_argument("--verify-only", action="store_true", help="Check frozen bytes and environment without rebuilding")
    parser.add_argument("--allow-environment-mismatch", action="store_true",
                        help="Explicitly permit and record a nonidentical environment")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    original, records = verify_bundle(bundle)
    environment = environment_report(original)
    print(json.dumps({"verified_bundle_files": len(records), "environment": environment}, indent=2), flush=True)
    if environment["differences"] and not args.allow_environment_mismatch:
        raise SystemExit("Environment differs from the release. Install its pinned requirements with the recorded Python version, or explicitly use --allow-environment-mismatch.")
    if not args.output and not args.verify_only:
        parser.error("--output is required unless --verify-only is used")
    output = (args.output or Path.cwd() / "unused-verification-output").resolve()
    if not args.verify_only and (output.is_relative_to(bundle) or bundle.is_relative_to(output)):
        raise ValueError("Output and bundle must be separate directory trees")
    fields, rows = staged_inventory(bundle, output, records, original)
    if args.verify_only:
        print(f"Verified {len(rows)} selected FSA inputs and the frozen code snapshot; no rebuild performed.")
        return
    stage_inputs(bundle, output, fields, rows)
    build = output / "build"
    build.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(bundle / "source/Scripts/00_run_all.py"), "--root", str(output),
               "--skip-download", "--ipeds-dir", str(bundle / "inputs/ipeds_hd"),
               "--ipeds-crosswalk-dir", str(bundle / "inputs/ipeds_crosswalks"), "--run-qaqc"]
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "command": command,
              "bundle_manifest_sha256": sha256(bundle / "input_manifest.json"),
              "original_release_manifest_sha256": sha256(bundle / "original_release_manifest.json"),
              "verified_bundle_files": len(records), "selected_fsa_inputs": len(rows),
              "environment": environment, "runner_sha256": sha256(Path(__file__)),
              "offline_inputs": True, "completed": False}
    report_path = build / "reproduction_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    env = os.environ.copy()
    env.pop("FSA_SCOPE_CONFIG", None)
    env["FSA_ROOT"] = str(output)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    print("Running frozen pipeline; complete output is in", build / "reproduction_log.txt", flush=True)
    with (build / "reproduction_log.txt").open("w") as log:
        result = subprocess.run(command, cwd=bundle / "source", env=env, stdout=log, stderr=subprocess.STDOUT)
    report["pipeline_returncode"] = result.returncode
    if result.returncode:
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        raise SystemExit(f"Frozen build failed ({result.returncode}); inspect {build / 'reproduction_log.txt'}")
    # Verify that execution did not mutate any frozen original inputs or code.
    if sha256(bundle / "input_manifest.json") != report["bundle_manifest_sha256"]:
        raise ValueError("Bundle manifest changed during execution; preserve the failed run and retry with a new output directory")
    verify_bundle(bundle)
    if args.reference_root:
        try:
            report["reference_comparison"] = compare_reference(output, args.reference_root.resolve(), original)
        except (AssertionError, OSError, ValueError) as exc:
            report["reference_comparison"] = {"passed": False, "error": str(exc)}
            report_path.write_text(json.dumps(report, indent=2) + "\n")
            raise
    else:
        report["reference_comparison"] = {"passed": None, "reason": "No --reference-root supplied; frozen pipeline QA does not establish equality to the downloadable original."}
    report.update(completed=True, finished_utc=datetime.now(timezone.utc).isoformat())
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Completed frozen release rebuild: {report_path}")


if __name__ == "__main__":
    main()
