#!/usr/bin/env python3
"""
Stage 00: orchestrate the end-to-end FSA Title IV volume-report pipeline.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent


def run(cmd: list[str], dry_run: bool) -> None:
    print("+", " ".join(cmd))
    if dry_run:
        return
    completed = subprocess.run(cmd, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    default_root = os.environ.get("FSA_ROOT", "/Users/markjaysonfarol13/Projects/FSAVolumeReports_Paneling")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=default_root, help="External FSA_ROOT")
    ap.add_argument("--page-html", default=None, help="Optional local HTML fixture for stage 01")
    ap.add_argument("--scope-config", default=None, help="Versioned release scope JSON")
    ap.add_argument("--ipeds-dir", default=None, help="Official annual HD/FLAGS sources; enables audited linkage stage")
    ap.add_argument("--ipeds-crosswalk-dir", default=None, help="Official annual NCES/FSA CW workbooks")
    ap.add_argument("--ipeds-anchor", choices=["start", "end"], default="start")
    ap.add_argument("--skip-preflight", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--preflight-only", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--strict-source-checks", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--skip-download", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--skip-profile", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--skip-dictionary", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--skip-grants", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--skip-campus", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--skip-loans", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--skip-merge", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--skip-review-package", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--skip-us-state-filter", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--skip-analysis-panel", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--skip-package", action=argparse.BooleanOptionalAction, default=False,
                    help="Build selected stages without certifying a complete research release")
    ap.add_argument("--run-qaqc", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.scope_config:
        os.environ["FSA_SCOPE_CONFIG"] = str(Path(args.scope_config).resolve())

    from fsa_build_utils import ensure_data_layout
    layout = ensure_data_layout(args.root)
    print(f"[fsa-volume] data root: {layout.root}")
    if not args.dry_run:
        from fsa_release_integrity import pipeline_fingerprints
        (layout.build / "run_started.json").write_text(json.dumps({
            "run_id": str(uuid.uuid4()),
            "started_utc": datetime.now(timezone.utc).isoformat(), "arguments": vars(args),
            "code_and_metadata": pipeline_fingerprints(),
        }, indent=2) + "\n")

    if not args.skip_download:
        if not args.skip_preflight:
            preflight_cmd = [
                sys.executable,
                str(SCRIPTS_DIR / "01_download_title_iv_reports.py"),
                "--root",
                str(layout.root),
                "--verify-only",
            ]
            if args.page_html:
                preflight_cmd += ["--page-html", str(args.page_html)]
            if not args.strict_source_checks:
                preflight_cmd += ["--no-strict-source-checks"]
            run(preflight_cmd, args.dry_run)
            if args.preflight_only:
                return
        cmd = [sys.executable, str(SCRIPTS_DIR / "01_download_title_iv_reports.py"), "--root", str(layout.root)]
        if args.page_html:
            cmd += ["--page-html", str(args.page_html)]
        if not args.strict_source_checks:
            cmd += ["--no-strict-source-checks"]
        run(cmd, args.dry_run)

    if not args.dry_run and not args.skip_package:
        import pandas as pd
        from fsa_release_integrity import require_release_scope
        selected = pd.read_csv(layout.checks / "download_qc/selected_panel_files.csv", dtype=str).fillna("")
        require_release_scope(selected).to_csv(layout.checks / "download_qc/release_scope_validation.csv", index=False)

    if not args.skip_profile:
        run([sys.executable, str(SCRIPTS_DIR / "02_profile_workbooks.py"), "--root", str(layout.root)], args.dry_run)

    if not args.skip_dictionary:
        run([sys.executable, str(SCRIPTS_DIR / "03_build_dictionary.py"), "--root", str(layout.root)], args.dry_run)

    if not args.skip_grants:
        run([sys.executable, str(SCRIPTS_DIR / "04_panelize_grants.py"), "--root", str(layout.root)], args.dry_run)

    if not args.skip_campus:
        run([sys.executable, str(SCRIPTS_DIR / "05_panelize_campus_based.py"), "--root", str(layout.root)], args.dry_run)

    if not args.skip_loans:
        run([sys.executable, str(SCRIPTS_DIR / "06_panelize_loans.py"), "--root", str(layout.root)], args.dry_run)

    if not args.skip_merge:
        run([sys.executable, str(SCRIPTS_DIR / "07_merge_fsa_panels.py"), "--root", str(layout.root)], args.dry_run)
        run([sys.executable, str(SCRIPTS_DIR / "08_build_panel_dictionary.py"), "--root", str(layout.root)], args.dry_run)
        if not args.skip_review_package:
            run([sys.executable, str(SCRIPTS_DIR / "09_build_manual_review_workbook.py"), "--root", str(layout.root)], args.dry_run)
        if not args.skip_us_state_filter:
            run([sys.executable, str(SCRIPTS_DIR / "10_filter_clean_panel_to_us_states.py"), "--root", str(layout.root)], args.dry_run)
        if not args.skip_analysis_panel:
            run([sys.executable, str(SCRIPTS_DIR / "11_build_analysis_ready_final_panel.py"), "--root", str(layout.root)], args.dry_run)

    if args.ipeds_dir:
        from fsa_build_utils import locate_analysis_ready_final_panel
        panel_path = locate_analysis_ready_final_panel(layout)
        if panel_path is None and not args.dry_run:
            raise SystemExit("No analysis master found for IPEDS linkage")
        command = [sys.executable, str(SCRIPTS_DIR / "13_link_ipeds.py"), "--input-parquet", str(panel_path or "<analysis-master>"),
             "--ipeds-dir", args.ipeds_dir, "--output-dir", str(layout.panels / "ipeds"), "--anchor", args.ipeds_anchor,
             "--research-root", str(layout.root)]
        if args.ipeds_crosswalk_dir:
            command += ["--crosswalk-dir", args.ipeds_crosswalk_dir]
        run(command, args.dry_run)

    if not args.dry_run:
        from fsa_release_integrity import write_transformation_completion
        write_transformation_completion(layout.root)

    if args.run_qaqc:
        run([sys.executable, str(SCRIPTS_DIR / "QA_QC" / "00_source_qaqc.py"), "--root", str(layout.root)], args.dry_run)
        run([sys.executable, str(SCRIPTS_DIR / "QA_QC" / "01_panel_qaqc.py"), "--root", str(layout.root)], args.dry_run)
        run([sys.executable, str(SCRIPTS_DIR / "QA_QC" / "02_acceptance_audit.py"), "--root", str(layout.root)], args.dry_run)

    if not args.skip_analysis_panel and not args.skip_package:
        run([sys.executable, str(SCRIPTS_DIR / "14_package_research_release.py"), "--root", str(layout.root)], args.dry_run)


if __name__ == "__main__":
    main()
