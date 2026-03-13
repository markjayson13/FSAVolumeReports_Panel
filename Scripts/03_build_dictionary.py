#!/usr/bin/env python3
"""
Stage 03: build the stitched FSA dictionary and header crosswalk.
"""
from __future__ import annotations

import argparse

from fsa_build_utils import build_dictionary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="External FSA_ROOT")
    args = ap.parse_args()
    frame = build_dictionary(args.root)
    print(f"Wrote dictionary rows={len(frame)}")


if __name__ == "__main__":
    main()
