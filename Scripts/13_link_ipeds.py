#!/usr/bin/env python3
"""Create an audited historical FSA-to-IPEDS bridge and conservative research view."""
from __future__ import annotations

import argparse
import json

from fsa_ipeds_linkage import run_ipeds_linkage


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-parquet", required=True, help="Corrected, unfiltered FSA reporting-unit panel")
    parser.add_argument("--ipeds-dir", required=True, help="Annual official HD/FLAGS ZIPs or raw CSV directory")
    parser.add_argument("--crosswalk-dir", default=None, help="Official annual NCES/FSA CW workbooks")
    parser.add_argument("--research-root", default=None, help="Root containing raw-row quarantine and source inventory")
    parser.add_argument("--output-dir", required=True, help="Separate linkage artifact directory")
    parser.add_argument("--anchor", choices=["start", "end"], default="start")
    parser.add_argument("--download-missing", action="store_true", help="Retrieve missing official annual sources")
    parser.add_argument("--refresh-sources", action="store_true", help="Explicitly refresh official sources (changes input vintage)")
    args = parser.parse_args()
    manifest = run_ipeds_linkage(args.input_parquet, args.ipeds_dir, args.output_dir,
                                 anchor=args.anchor, download_missing=args.download_missing,
                                 refresh_sources=args.refresh_sources, crosswalk_dir=args.crosswalk_dir,
                                 research_root=args.research_root)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
