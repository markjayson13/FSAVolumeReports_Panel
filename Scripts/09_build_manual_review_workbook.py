#!/usr/bin/env python3
"""
Stage 09: build a reviewer-facing workbook and CSV package for descriptor manual review.
"""
from __future__ import annotations

import argparse

from fsa_build_utils import build_manual_review_workbook


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="External FSA_ROOT")
    ap.add_argument("--input-csv", default=None, help="Optional manual review CSV")
    ap.add_argument("--summary-csv", default=None, help="Optional resolution summary CSV")
    ap.add_argument("--output-xlsx", default=None, help="Optional output workbook path")
    ap.add_argument("--output-dir", default=None, help="Optional output package directory")
    args = ap.parse_args()
    workbook_path, package_dir = build_manual_review_workbook(
        args.root,
        input_csv=args.input_csv,
        summary_csv=args.summary_csv,
        output_xlsx=args.output_xlsx,
        output_dir=args.output_dir,
    )
    print(f"Wrote manual review workbook: {workbook_path}")
    print(f"Wrote manual review package dir: {package_dir}")


if __name__ == "__main__":
    main()
