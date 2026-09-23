# Reproduce the frozen research release

The downloadable research exports provide the original data bytes, labels,
codebooks, and import scripts. The **replication** archive separately preserves
the exact selected FSA workbooks, annual IPEDS HD/FLAGS files, annual official
crosswalks, source documentation, selection inventory, and original pipeline
snapshot needed to rebuild the canonical panels without fetching changing
upstream data. Download the release assets from the repository's
[GitHub Releases page](https://github.com/markjayson13/FSAVolumeReports_Panel/releases).

## One-command installation and reproduction

Run this in a terminal with Bash and curl (macOS, Linux, or Windows WSL):

```sh
curl -fsSL https://raw.githubusercontent.com/markjayson13/FSAVolumeReports_Panel/fsa-research-v2-2026-09-22/Scripts/bootstrap_reproduction.sh | bash
```

This downloads all five dataset/replication archives and their checksum manifest, verifies the downloaded bytes, creates an isolated Python 3.13.0 environment with pinned dependencies, rebuilds the canonical panels, and checks them against the reference release. No preinstalled Python, Git, Stata, or Excel is required to reproduce the panels. The computer needs sufficient storage for the downloads, extracted data, environment and rebuilt outputs; keep at least 10 GB available. Network access is needed for installation and downloads; the panel build then uses local frozen inputs.

The default destination is a new `FSA-reproduction/` directory. For another location, set the variable on the Bash side of the pipe:

```sh
curl -fsSL https://raw.githubusercontent.com/markjayson13/FSAVolumeReports_Panel/fsa-research-v2-2026-09-22/Scripts/bootstrap_reproduction.sh | FSA_DEST="$PWD/my-fsa-replication" bash
```

The bootstrap refuses a nonempty destination, including an interrupted run's directory; select a new destination for a retry. It preserves existing work and does not modify shell profiles. Its local environment/tools are under `.venv/` and `.tools/` within the destination. Output folders are `rebuilt/` (new panels and comparison report), `canonical/` (exact reference data), `unitid/` (labeled exports and codebooks), and `replication/` (frozen inputs and code). Downloads remain under `downloads/`.

The bootstrap and assets are pinned to the release tag, rather than a changing `main` branch. The frozen pipeline remains the original validated snapshot; the portable runner only relocates runtime file paths. The [reviewable bootstrap source](../Scripts/bootstrap_reproduction.sh) records the pinned uv installer used to provide Python and the isolated environment. Native Windows PowerShell/CMD is not supported by this Bash command; use WSL.

## Manual reproduction

Extract the replication and canonical archives alongside one another. Their
top-level directories are `replication/` and `canonical/`. Use Python **3.13.0**
and install the exact versions in `replication/environment-lock.txt`
into a dedicated environment. Installing Python and dependencies can require
network access; the subsequent frozen rebuild uses only local inputs.

```sh
python -m pip install -r replication/environment-lock.txt
python replication/reproduce_frozen_release.py --bundle replication --output rebuilt-release --reference-root canonical
```

The repository copy of the runner is
[`Scripts/reproduce_frozen_release.py`](../Scripts/reproduce_frozen_release.py).
The standalone copy inside the release performs the same work and does not
require cloning GitHub. `rebuilt-release` must not already exist; choose a new
directory for each attempt. Paths containing spaces are supported when quoted.

The runner verifies SHA256 hashes and lengths for every bundled file and checks
the frozen source against the original release manifest. It rejects unexpected
source/input files, duplicate inventory entries, missing selected workbooks,
path traversal, symlinks, changed selection metadata, and environment version
differences. `--verify-only` checks the bundle without rebuilding.
`--allow-environment-mismatch` is an explicit exploratory override; the report
records every differing package or Python version.

It copies the selected workbooks into the new output directory, rebases their
runtime inventory paths, recreates the per-year manifests used by profiling,
then runs the frozen pipeline with `--skip-download` and `--run-qaqc`. Original
input, metadata, and source bytes remain unchanged. The pipeline regenerates
its dictionary, family panels, unrestricted OPEID panel, annual bridge,
conservative UNITID panel, review outputs, and acceptance reports. It records
fresh build provenance. The original acquisition paths remain in the preserved
original manifests; they are provenance, not required local paths.

With `--reference-root canonical`, the runner first validates the three
reference panels against the original release artifact hashes, then compares
**every cell and dtype**, keyed by OPEID or UNITID and award year, in:

- the unrestricted OPEID master;
- the annual FSA–IPEDS bridge;
- the UNITID award-year research panel.

Comparison normalizes only the directory portion of the explicitly named
IPEDS HD and crosswalk provenance path columns. It retains their basenames,
source SHA256 fields, all identifiers, outcomes, missing values, statuses, and
scope flags. No numeric tolerance is used. The report lists each normalized
column and both artifact hashes. Rebuilt byte hashes can differ because local
source paths and build timestamps differ; a passing cell comparison does not
claim byte-identical newly generated files. Without a reference directory, the
runner reports that reference equivalence was **not checked**.

Inspect `rebuilt-release/build/reproduction_report.json` and
`rebuilt-release/build/reproduction_log.txt`. The former records input manifest
hashes, the interpreter and package versions, command, exit status, and exact
cell comparison. Pipeline acceptance outputs are under `Checks/acceptance_qc/`.
The release includes its original validation evidence separately. Existing
published Stata/CSV/Excel/Parquet exports remain available as exact downloadable
bytes; rebuilding these large format exports is separate from the canonical
pipeline. Follow their bundled export README for labels, import scripts,
missing-value handling, and panel setup.

Reproducibility preserves the documented scope and limitations; it does not
turn unresolved parent/child reporting units into campus-level aid allocations.
Use the eligibility and scope flags described in
[`research_use.md`](research_use.md) and
[`ipeds_linkage.md`](ipeds_linkage.md).
