#!/usr/bin/env python3
"""
Stage 01: discover and download Title IV volume-report workbooks.
"""
from __future__ import annotations

import argparse

from fsa_build_utils import download_title_iv_reports


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="External FSA_ROOT")
    ap.add_argument("--page-html", default=None, help="Optional local HTML fixture")
    ap.add_argument("--skip-existing", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--strict-source-checks", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--verify-only", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()
    entries = download_title_iv_reports(
        args.root,
        page_html=args.page_html,
        skip_existing=args.skip_existing,
        timeout=args.timeout,
        strict_source_checks=args.strict_source_checks,
        verify_only=args.verify_only,
    )
    mode = "preflight inventory" if args.verify_only else "release inventory"
    print(f"Wrote {mode} rows={len(entries)}")


if __name__ == "__main__":
    main()
