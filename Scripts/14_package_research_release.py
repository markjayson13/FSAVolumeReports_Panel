#!/usr/bin/env python3
"""Record exact inputs, code, exclusions and acceptance for a local research release."""
from __future__ import annotations

import argparse
import json
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path
import importlib.metadata
import pandas as pd

from fsa_build_utils import data_layout, locate_analysis_ready_final_panel, REPO_ROOT, compute_file_metadata
from fsa_policy import policy_registry_hash
from fsa_release_integrity import require_current_qa, require_current_linkage, require_release_scope, acceptance_all_passed


def package(root: str) -> Path:
    layout = data_layout(root)
    path = locate_analysis_ready_final_panel(layout)
    if path is None:
        raise ValueError("Missing unfiltered research master")
    if "us_states_only" in path.name:
        raise ValueError("A restricted geography view cannot be packaged as the unrestricted master")
    require_current_qa(layout.root)
    frame = pd.read_parquet(path)
    selected = pd.read_csv(layout.checks / "download_qc/selected_panel_files.csv", dtype=str).fillna("")
    scope_validation = require_release_scope(selected)
    inputs = []
    for row in selected.to_dict("records"):
        size, sha = compute_file_metadata(Path(row["local_path"]))
        if not size or (row.get("sha256") and row["sha256"] != sha):
            raise ValueError(f"Selected source missing or changed since inventory: {row['filename']}")
        inputs.append({**row, "verified_sha256": sha, "verified_size": size,
                       "content_verified_at": datetime.now(timezone.utc).isoformat()})
    code_inputs = []
    for folder in (REPO_ROOT / "Scripts", REPO_ROOT / "Metadata", REPO_ROOT / "Documentation", REPO_ROOT / "tests"):
        for source in sorted(folder.rglob("*")):
            if source.is_file() and source.suffix in {".py", ".csv", ".json", ".sh", ".md"}:
                code_inputs.append({"path": str(source.relative_to(REPO_ROOT)), "sha256": compute_file_metadata(source)[1]})
    for source in (REPO_ROOT / "requirements.txt", REPO_ROOT / "README.md"):
        code_inputs.append({"path": str(source.relative_to(REPO_ROOT)), "sha256": compute_file_metadata(source)[1]})
    # This checkout can be a downloaded archive without Git. Preserve the exact
    # executable source, tests and interpretive documentation with the release.
    for item in code_inputs:
        target = layout.build / "source_snapshot" / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / item["path"], target)
        if compute_file_metadata(target)[1] != item["sha256"]:
            raise ValueError("Release source snapshot changed during packaging")
    acceptance_path = layout.checks / "acceptance_qc/acceptance_summary.csv"
    acceptance = pd.read_csv(acceptance_path) if acceptance_path.exists() else pd.DataFrame(columns=["passed"])
    passed = bool(acceptance_all_passed(acceptance))
    quarantines = []
    for p in sorted((layout.checks / "observation_qc").glob("*_quarantine.parquet")):
        q = pd.read_parquet(p)
        quarantines.append({"family": p.name.removesuffix("_quarantine.parquet"), "rows": len(q), "path": str(p)})
    linkage = require_current_linkage(layout.root, path)
    artifacts = []
    release_artifacts = list(layout.panels.rglob("*.parquet"))
    release_artifacts += [p for p in layout.dictionary.glob("*") if p.suffix in {".parquet", ".csv"}]
    for p in sorted(release_artifacts):
        size, sha = compute_file_metadata(p)
        artifacts.append({"path": str(p.relative_to(layout.root)), "bytes": size, "sha256": sha})
    manifest = {"release_version": "fsa-research-v2", "built_utc": datetime.now(timezone.utc).isoformat(),
        "master": str(path), "rows": len(frame), "columns": len(frame.columns), "institutions": frame.opeid8.nunique(),
        "fsa_reporting_unit_ids": frame.opeid8.nunique(),
        "institution_count_note": "The legacy institutions key counts distinct FSA reporting IDs, including unverified/noninstitutional placeholders. Use the UNITID panel and annual reconciliation for institutional counts.",
        "award_years": sorted(frame.award_year.unique()), "unit_of_observation": "FSA full OPEID8 by award year; not automatically an IPEDS campus",
        "master_geography": "unrestricted; state filtering is an explicit separate view",
        "source_vintage": "frozen selected input bytes; input hashes verified; upstream freshness is not implied",
        "policy_registry_sha256": policy_registry_hash(), "acceptance_passed": passed, "acceptance_checks": len(acceptance),
        "scope_validation_passed": True, "scope_checks": len(scope_validation),
        "descriptor_review_rows": int(frame.descriptor_review_required.sum()), "quarantined_institution_rows": quarantines,
        "linkage": linkage, "inputs": inputs, "code_and_metadata": code_inputs, "artifacts": artifacts,
        "environment": {"python": platform.python_version(), **{p: importlib.metadata.version(p) for p in ["pandas","pyarrow","openpyxl","xlrd","requests","beautifulsoup4"]}}}
    out = layout.build / "research_release_manifest.json"
    out.write_text(json.dumps(manifest, indent=2, default=int) + "\n")
    pd.DataFrame(inputs).to_csv(layout.checks / "source_qc/release_input_hashes.csv", index=False)
    (layout.build / "environment-requirements.txt").write_text("\n".join(f"{k}=={v}" for k,v in manifest["environment"].items() if k != "python") + "\n")
    summary = ["FSA research release", "", f"Master: {path}", f"Rows: {len(frame):,}; FSA reporting IDs: {frame.opeid8.nunique():,}; columns: {len(frame.columns)}",
               f"Acceptance: {'PASS' if passed else 'NOT PASSED'} ({len(acceptance)} checks)",
               f"Unresolved descriptor-review rows: {int(frame.descriptor_review_required.sum()):,}",
               f"Quarantined source institution rows: {sum(q['rows'] for q in quarantines):,}",
               "", "Use the unrestricted master with its status fields. Do not treat NA as zero, recipient sums as unique people, or a UNITID tag as proof of campus-level scope.",
               "See Documentation/research_use.md and Documentation/policy_and_reporting_changes.md in the repository.",
               "Source identity failures are retained in quarantine; the strict IPEDS view intentionally excludes ambiguous/reporting-group/temporal cases."]
    if linkage:
        summary.extend(["", f"Strict IPEDS sensitivity rows: {linkage['strict_rows']:,}",
                        f"Annual identity-eligible FSA rows: {linkage.get('annual_identity_eligible_rows', 0):,}",
                        f"UNITID-year panel rows: {linkage.get('unitid_panel', {}).get('rows', 0):,}",
                        "Use the annual institution-count reconciliation and source-family eligibility flags; a resolved UNITID is not a certified campus aid allocation."])
    else:
        summary.append("IPEDS linkage not built in this invocation.")
    (layout.build / "RESEARCH_RELEASE.txt").write_text("\n".join(summary)+"\n")
    if not passed:
        raise SystemExit(f"Release is NOT accepted; inspect {acceptance_path}. Manifest recorded at {out}")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    print(package(parser.parse_args().root))
