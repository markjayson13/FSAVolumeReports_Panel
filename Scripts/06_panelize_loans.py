#!/usr/bin/env python3
"""
Stage 06: panelize Direct and FFEL loan volume reports, then merge them.
"""
from __future__ import annotations

import argparse

from fsa_build_utils import build_component_panel, merge_loan_panels


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="External FSA_ROOT")
    args = ap.parse_args()
    direct = build_component_panel(args.root, "direct_loans")
    ffel = build_component_panel(args.root, "ffel")
    merged = merge_loan_panels(args.root)
    print(f"Wrote direct panel: {direct}")
    print(f"Wrote FFEL panel: {ffel}")
    print(f"Wrote merged loan panel: {merged}")


if __name__ == "__main__":
    main()
