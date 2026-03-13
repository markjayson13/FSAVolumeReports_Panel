#!/usr/bin/env python3
"""
QA stage 00: audit source discovery, downloads, and workbook profiling.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fsa_build_utils import source_qaqc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="External FSA_ROOT")
    args = ap.parse_args()
    frame = source_qaqc(args.root)
    print(f"Wrote source QA rows={len(frame)}")


if __name__ == "__main__":
    main()
