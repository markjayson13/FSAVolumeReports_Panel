#!/usr/bin/env python3
"""
QA stage 02: run the top-level acceptance audit over generated FSA artifacts.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fsa_build_utils import acceptance_audit


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="External FSA_ROOT")
    args = ap.parse_args()
    frame = acceptance_audit(args.root)
    failed = int((~frame["passed"].astype(bool)).sum())
    print(f"Wrote acceptance audit rows={len(frame)} failed={failed}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
