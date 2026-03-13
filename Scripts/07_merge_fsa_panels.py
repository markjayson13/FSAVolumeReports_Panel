#!/usr/bin/env python3
"""
Stage 07: merge grant, campus-based, and loan panels into final raw/clean outputs.
"""
from __future__ import annotations

import argparse

from fsa_build_utils import merge_final_panels


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="External FSA_ROOT")
    args = ap.parse_args()
    raw_path, clean_path = merge_final_panels(args.root)
    print(f"Wrote final raw panel: {raw_path}")
    print(f"Wrote final clean panel: {clean_path}")


if __name__ == "__main__":
    main()
