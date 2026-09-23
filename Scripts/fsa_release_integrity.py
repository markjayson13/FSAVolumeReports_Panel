"""Bind QA and release claims to the exact source, output, code and metadata bytes."""
from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pipeline_fingerprints() -> dict[str, str]:
    paths = [REPO / "requirements.txt"]
    for directory in ("Scripts", "Metadata"):
        paths.extend(p for p in (REPO / directory).rglob("*") if p.is_file() and p.suffix in {".py", ".json", ".csv", ".sh"})
    fingerprints = {str(p.relative_to(REPO)): sha256(p) for p in sorted(paths)}
    if os.environ.get("FSA_SCOPE_CONFIG"):
        scope = Path(os.environ["FSA_SCOPE_CONFIG"]).resolve()
        fingerprints[f"external_scope:{scope}"] = sha256(scope)
    return fingerprints


def data_fingerprints(root: Path) -> dict[str, str]:
    paths = [p for folder in ("Panels", "Dictionary", "Checks") for p in (root / folder).rglob("*")
             if p.is_file() and p.suffix in {".parquet", ".csv", ".json", ".xlsx"}
             and p.name not in {"qa_fingerprints.json", "release_input_hashes.csv"}]
    return {str(p.relative_to(root)): sha256(p) for p in sorted(paths) if p.exists()}


def transformation_fingerprints(root: Path) -> dict[str, str]:
    return {key: value for key, value in data_fingerprints(root).items()
            if key.startswith(("Panels/", "Dictionary/", "Checks/observation_qc/"))}


def write_transformation_completion(root: Path) -> None:
    start = json.loads((root / "build/run_started.json").read_text())
    (root / "build/transformations_completed.json").write_text(json.dumps({
        "run_id": start["run_id"], "code_and_metadata": pipeline_fingerprints(),
        "data": transformation_fingerprints(root)}, indent=2) + "\n")


def require_release_scope(selected):
    from fsa_build_utils import validate_inventory_scope
    for row in selected.to_dict("records"):
        if re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256", ""))) is None:
            raise ValueError(f"Selected source lacks a valid recorded SHA256: {row.get('filename')}")
    validation = validate_inventory_scope(selected.to_dict("records"))
    if not validation["passed"].all():
        raise ValueError("Selected reports do not match the configured release scope: " +
                         validation.loc[~validation["passed"], ["component_family", "check"]].to_json(orient="records"))
    return validation


def acceptance_all_passed(frame) -> bool:
    return not frame.empty and frame["passed"].notna().all() and frame["passed"].astype(str).eq("True").all()


def write_qa_fingerprints(root: Path) -> None:
    out = root / "Checks/acceptance_qc/qa_fingerprints.json"
    start_path = root / "build/run_started.json"
    run_id = json.loads(start_path.read_text()).get("run_id") if start_path.exists() else None
    out.write_text(json.dumps({"run_id": run_id, "code_and_metadata": pipeline_fingerprints(), "data": data_fingerprints(root)}, indent=2) + "\n")


def require_current_qa(root: Path) -> None:
    path = root / "Checks/acceptance_qc/qa_fingerprints.json"
    if not path.exists():
        raise ValueError("QA fingerprints missing; run fresh acceptance before packaging")
    recorded = json.loads(path.read_text())
    if recorded["code_and_metadata"] != pipeline_fingerprints() or recorded["data"] != data_fingerprints(root):
        raise ValueError("QA is stale relative to code, metadata or data; rerun affected stages and acceptance")
    start_path = root / "build/run_started.json"
    if not start_path.exists():
        raise ValueError("No orchestrator run provenance; rebuild through Scripts/00_run_all.py")
    start = json.loads(start_path.read_text())
    if start["code_and_metadata"] != pipeline_fingerprints():
        raise ValueError("Code or metadata changed during the build; rerun the complete release build")
    # A partial invocation may be useful, but cannot certify a complete rebuilt release.
    required = ["skip_profile", "skip_dictionary", "skip_grants", "skip_campus", "skip_loans", "skip_merge", "skip_analysis_panel"]
    if any(start["arguments"].get(flag, False) for flag in required):
        raise ValueError("Partial stage invocation cannot certify a complete release; use --skip-package or rerun all transformation stages")
    complete_path = root / "build/transformations_completed.json"
    if not complete_path.exists():
        raise ValueError("No completed transformation provenance for this run")
    completed = json.loads(complete_path.read_text())
    if not start.get("run_id") or completed.get("run_id") != start["run_id"] or recorded.get("run_id") != start["run_id"]:
        raise ValueError("Transformation and QA evidence belong to a different run")
    if completed["code_and_metadata"] != pipeline_fingerprints() or completed["data"] != transformation_fingerprints(root):
        raise ValueError("Transformed artifacts changed before QA; rerun transformations")


def require_current_linkage(root: Path, master: Path) -> dict | None:
    """Reject a stale bridge, changed directory input, or changed linkage artifact."""
    import pandas as pd
    path = root / "Panels/ipeds/ipeds_linkage_manifest.json"
    if not path.exists():
        return None
    manifest = json.loads(path.read_text())
    if manifest.get("source_panel_sha256") != sha256(master):
        raise ValueError("IPEDS linkage belongs to a different master; rerun stage 13")
    if manifest.get("linkage_code_sha256") != sha256(REPO / "Scripts/fsa_ipeds_linkage.py"):
        raise ValueError("IPEDS linkage code changed; rerun stage 13")
    if manifest.get("all_original_cells_preserved") is not True:
        raise ValueError("IPEDS linkage has not certified preservation of original FSA cells")
    for artifact in manifest["artifacts"].values():
        if sha256(Path(artifact["path"])) != artifact["sha256"]:
            raise ValueError("IPEDS artifact changed since linkage build; rerun stage 13")
    source_manifest = pd.read_csv(path.parent / "ipeds_source_manifest.csv", dtype=str).fillna("")
    verified = 0
    for source in source_manifest.to_dict("records"):
        if source.get("sha256"):
            if not source.get("path") or sha256(Path(source["path"])) != source["sha256"]:
                raise ValueError("IPEDS directory input changed since linkage build; rerun stage 13")
            verified += 1
    if not verified:
        raise ValueError("No hashed IPEDS source files in linkage provenance")
    if manifest.get("crosswalk_requested"):
        crosswalk = pd.read_csv(path.parent / "ipeds_crosswalk_source_manifest.csv", dtype=str).fillna("")
        for source in crosswalk.to_dict("records"):
            if source.get("status") == "loaded" and (not source.get("source_path") or
                    sha256(Path(source["source_path"])) != source.get("sha256")):
                raise ValueError("Official crosswalk input changed since linkage build; rerun stage 13")
    return manifest
