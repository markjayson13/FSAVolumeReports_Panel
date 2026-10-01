# FSA Volume Reports panel

This repository panelizes Federal Student Aid volume reports at **full eight-character OPEID × award year**. It owns acquisition, workbook parsing, identity normalization, program harmonization, missingness and suppression handling, policy documentation, dictionaries, and FSA source-to-panel validation.

**IPEDS linkage and all UNITID, combined FSA–IPEDS, and aid-aligned research views now belong to [IPEDS-FSA_Panel](https://github.com/markjayson13/IPEDS-FSA_Panel).** IPEDS source-panel construction remains in [IPEDSDB_Panel](https://github.com/markjayson13/IPEDSDB_Panel). These projects consume reviewed source artifacts rather than duplicating each other's panelizers.

## Build the FSA panel

```sh
python3 -m pip install -r requirements.txt
python3 Scripts/00_run_all.py --root /path/to/FSA-data --run-qaqc
```

For frozen workbooks and the corresponding selected inventory already in a data root, add `--skip-download`. The default root is `FSA-data` in the current directory; `FSA_ROOT` or `--root` can override it. `--scope-config` selects a reviewed scope. `--skip-package` permits exploratory partial runs without certifying a release.

`Metadata/release_scope.json` pins grants and Direct Loans to AY1999–2000 through AY2024–25, Campus-Based reports to AY2001–02 through AY2023–24, and FFEL to AY1999–2000 through AY2009–10. Quarterly reports are cumulative: select Q4 once, never sum quarters. A frozen source vintage does not imply the latest upstream release.

## Outputs

- `Panels/final/fsa_volume_reports_panel_1999_2025.parquet`: unrestricted FSA reporting-unit master.
- `Dictionary/fsa_volume_panel_dictionary.parquet` and `.csv`: definitions, units, formulas, source and policy metadata.
- `Dictionary/variable_year_availability.csv`: annual schema availability and value-status counts.
- `Checks/observation_qc/`: rejected-row records, totals, exceptional tokens and schemas.
- `Checks/research_qc/`: conservation and research acceptance.
- `build/research_release_manifest.json`: selected input hashes, exact source snapshot, environment, output hashes and exclusions.

The optional states-plus-DC view never replaces the unrestricted master. FSA OPEIDs count reporting identities, not verified institutions. Keep OPEIDs as strings and keep measure-status companions. Missing, suppressed, absent-source and unavailable values are not globally zero-filled; recipient sums are not unique people. Parent totals are not allocated to campuses by this pipeline.

Read [research use](Documentation/research_use.md), [policy and reporting changes](Documentation/policy_and_reporting_changes.md), [loan harmonization](Documentation/loan_harmonization.md), and [source identity recovery](Documentation/source_identity_recovery.md). The 34 approved full-OPEID recoveries and their evidence remain intact. Citations to IPEDS in this source-cleaning evidence do not turn the FSA master into a UNITID panel.

## Reproduce a frozen FSA-only release

After extracting its replication bundle, one command rebuilds it in a new directory:

```sh
bash Scripts/bootstrap_reproduction.sh /path/to/replication /path/to/new-FSA-output --reference-root /path/to/canonical
```

It installs an isolated pinned environment, verifies every frozen input and source hash, rebuilds only FSA, and compares every master value and dtype with the reference. Set `FSA_PYTHON` to reuse an existing compatible interpreter offline. No new FSA-only public release assets are claimed by this migration. See [packaging and reproduction](Documentation/reproduce_release.md).

The previously published `fsa-research-v2-2026-09-22` tag remains an immutable **historical mixed FSA/linkage release**. Use its original tagged instructions for exact historical reproduction. Current scripts deliberately do not reinterpret it as a new FSA-only release. Existing local historical outputs are untouched.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests complement, rather than replace, the actual build's acceptance checks. Large inputs, environments and generated panels are excluded from Git.
