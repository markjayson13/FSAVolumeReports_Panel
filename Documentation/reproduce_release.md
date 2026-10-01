# Frozen FSA-only reproduction

The current repository produces an OPEID-by-award-year FSA master. Linkage and combined-panel reproduction are owned by [IPEDS-FSA_Panel](https://github.com/markjayson13/IPEDS-FSA_Panel).

To reproduce an extracted **FSA-only** replication bundle and compare every master cell with its canonical reference:

```sh
bash Scripts/bootstrap_reproduction.sh /path/to/replication /path/to/new-output --reference-root /path/to/canonical
```

The new output must not exist. Initial environment installation requires internet; subsequent builds use frozen inputs. Python 3.13.0 and package versions are pinned in the bundle. Set `FSA_PYTHON=/path/to/python` for an existing environment; the runner verifies versions. A supplied `--allow-environment-mismatch` explicitly records deviations. The runner verifies selected-source content, selection semantics, source hashes, inventory coverage, and output key/value/type equality. It refuses symlinks or path traversal in input manifests. Without `--reference-root`, pipeline QA runs but equality to a reference is not claimed.

To package a freshly accepted FSA-only build locally:

```sh
python3 Scripts/package_public_release.py --root /path/to/FSA-data --distribution /path/to/new-distribution
```

This produces canonical and replication ZIPs, manifests and checksums. It performs no GitHub publication. The build must have current acceptance fingerprints and the `fsa_reporting_unit_panel` repository scope. Downstream `Panels/ipeds` artifacts are excluded. Original government sources and source hashes remain recorded; packaging asserts no blanket license over all third-party material.

The previously published tag `fsa-research-v2-2026-09-22` predates repository separation and includes linkage. Its immutable [tagged reproduction instructions](https://github.com/markjayson13/FSAVolumeReports_Panel/blob/fsa-research-v2-2026-09-22/Documentation/reproduce_release.md) and runner remain the correct historical replay. Current code rejects a mixed legacy bundle rather than silently calling it an FSA-only build. No freshly published FSA-only assets are implied by this repository refactor.
