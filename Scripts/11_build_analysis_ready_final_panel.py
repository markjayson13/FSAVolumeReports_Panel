#!/usr/bin/env python3
"""
Build a single analysis-ready final panel with one canonical descriptor set and
all grant, campus-based, and loan measures matched on opeid8 and award_year.
"""
from __future__ import annotations

import argparse

from fsa_build_utils import build_analysis_ready_final_panel


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="External FSA_ROOT")
    ap.add_argument("--input-parquet", default=None, help="Optional clean final panel input path")
    ap.add_argument("--output-parquet", default=None, help="Optional analysis-ready panel output path")
    ap.add_argument("--output-summary-csv", default=None, help="Optional panel summary CSV path")
    args = ap.parse_args()
    output_panel, summary_csv = build_analysis_ready_final_panel(
        args.root,
        input_parquet=args.input_parquet,
        output_parquet=args.output_parquet,
        output_summary_csv=args.output_summary_csv,
    )
    print(f"Wrote analysis-ready final panel: {output_panel}")
    print(f"Wrote analysis-ready panel summary: {summary_csv}")


if __name__ == "__main__":
    main()
