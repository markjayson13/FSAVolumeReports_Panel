#!/usr/bin/env python3
"""
Post-process the final clean panel to keep only the 50 U.S. states plus DC.
Territories, foreign schools, and blank/missing states are dropped.
"""
from __future__ import annotations

import argparse

from fsa_build_utils import filter_clean_panel_to_us_states


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="External FSA_ROOT")
    ap.add_argument("--input-parquet", default=None, help="Optional final clean panel path")
    ap.add_argument("--output-parquet", default=None, help="Optional filtered parquet path")
    ap.add_argument("--output-summary-csv", default=None, help="Optional summary CSV path")
    ap.add_argument("--output-dropped-counts-csv", default=None, help="Optional dropped-state counts CSV path")
    args = ap.parse_args()
    output_panel, summary_csv, dropped_counts_csv = filter_clean_panel_to_us_states(
        args.root,
        input_parquet=args.input_parquet,
        output_parquet=args.output_parquet,
        output_summary_csv=args.output_summary_csv,
        output_dropped_counts_csv=args.output_dropped_counts_csv,
    )
    print(f"Wrote filtered panel: {output_panel}")
    print(f"Wrote filter summary: {summary_csv}")
    print(f"Wrote dropped-state counts: {dropped_counts_csv}")


if __name__ == "__main__":
    main()
