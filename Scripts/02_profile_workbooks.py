#!/usr/bin/env python3
"""
Stage 02: profile all discovered workbooks and selected sheets.
"""
from __future__ import annotations

import argparse

from fsa_build_utils import profile_workbooks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="External FSA_ROOT")
    args = ap.parse_args()
    frame = profile_workbooks(args.root)
    print(f"Wrote workbook profiles rows={len(frame)}")


if __name__ == "__main__":
    main()
