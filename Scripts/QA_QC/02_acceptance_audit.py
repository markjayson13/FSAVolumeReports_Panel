#!/usr/bin/env python3
"""
QA stage 02: run the top-level acceptance audit over generated FSA artifacts.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fsa_build_utils import acceptance_audit
from fsa_build_utils import data_layout
from fsa_release_integrity import write_qa_fingerprints, acceptance_all_passed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="External FSA_ROOT")
    args = ap.parse_args()
    layout = data_layout(args.root)
    source_summary = layout.checks / "source_qc/source_qaqc_summary.csv"
    if source_summary.exists() and not acceptance_all_passed(pd.read_csv(source_summary)):
        # Do not let bool('False'), missing values or arbitrary tokens become a
        # fresh passing acceptance/fingerprint through a permissive wrapper.
        raise SystemExit("Source QA did not contain exclusively explicit True results")
    frame = acceptance_audit(args.root)
    failed = int((~frame["passed"].astype(str).eq("True")).sum())
    print(f"Wrote acceptance audit rows={len(frame)} failed={failed}")
    if not acceptance_all_passed(frame):
        raise SystemExit(1)
    write_qa_fingerprints(layout.root)


if __name__ == "__main__":
    main()
