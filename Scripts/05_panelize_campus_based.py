#!/usr/bin/env python3
"""
Stage 05: panelize campus-based volume reports.
"""
from __future__ import annotations

import argparse

from fsa_build_utils import build_component_panel


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="External FSA_ROOT")
    args = ap.parse_args()
    output = build_component_panel(args.root, "campus_based")
    print(f"Wrote campus-based panel: {output}")


if __name__ == "__main__":
    main()
