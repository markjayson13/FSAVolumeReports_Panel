#!/usr/bin/env python3
"""
Stage 08: build a dictionary scoped to the delivered final panel columns.
"""
from __future__ import annotations

import argparse

from fsa_build_utils import build_panel_dictionary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="External FSA_ROOT")
    ap.add_argument("--input", default=None, help="Optional input panel path")
    ap.add_argument("--output-csv", default=None, help="Optional output CSV path")
    ap.add_argument("--output-parquet", default=None, help="Optional output parquet path")
    args = ap.parse_args()
    csv_path, parquet_path = build_panel_dictionary(
        args.root,
        input_path=args.input,
        output_csv=args.output_csv,
        output_parquet=args.output_parquet,
    )
    print(f"Wrote panel dictionary CSV: {csv_path}")
    print(f"Wrote panel dictionary parquet: {parquet_path}")


if __name__ == "__main__":
    main()
