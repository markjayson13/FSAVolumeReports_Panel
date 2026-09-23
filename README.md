# FSA Volume Reports research panel

A reproducible, loss-aware FSA reporting-unit-by-award-year dataset, with a historical IPEDS bridge and a separately screened UNITID research view. **OPEID8 is the source observation key; a UNITID match does not automatically establish campus-level aid scope.**

The repaired pipeline restores full eight-digit OPEIDs from numeric Excel cells, retains source program/channel/level measures and currency cents, flags suppression and missingness, accounts for rejected source rows, and validates raw-to-final conservation. Historical loan mappings fix the AY2005–06 PLUS/Graduate PLUS omission. Derived recipient sums are explicitly not unique people.

Start with [research use and reproducibility](Documentation/research_use.md), [IPEDS linkage and reporting units](Documentation/ipeds_linkage.md), [policy and schema changes](Documentation/policy_and_reporting_changes.md), and [loan definitions](Documentation/loan_harmonization.md). The initial [gap audit](Audit/2026-09-22/report.md) is retained as historical evidence; it describes the pre-repair pipeline.

## Versioned scope

`Metadata/release_scope.json` pins the reviewed release:

- Grants and Direct Loans: AY1999–2000 through AY2024–2025.
- Campus-based programs: AY2001–2002 through AY2023–2024.
- FFEL: AY1999–2000 through AY2009–2010.

Quarterly families use the cumulative Q4 report, never a sum of cumulative quarters. Full-year coverage is not a claim of final data vintage. Updates require a new reviewed scope and source hashes. Program policy dates, observed header availability and reporting periods are distinct. This snapshot makes no claim that it contains every latest upstream release.

## Run

Install dependencies and run tests:

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
```

For an existing frozen data root with raw workbooks and selected inventory:

```sh
python3 Scripts/00_run_all.py \
  --root ResearchBuild/2026-09-22-v2 \
  --skip-download \
  --ipeds-dir ResearchBuild/IPEDS/official_hd_v2 \
  --ipeds-crosswalk-dir ResearchBuild/IPEDS/official_crosswalks \
  --run-qaqc
```

Without `--skip-download`, the downloader discovers official FSA files and validates newly retrieved bytes before atomically replacing a file, preserving changed prior bytes in `revisions/`. Downloading through a raw-data symlink is refused. `--skip-existing` on stage01 explicitly reuses cached bytes without upstream refresh. `--preflight-only` inventories sources; `--page-html` accepts local HTML/JSON fixtures. Reduced test inventories require a matching `--scope-config` to package successfully; `--no-strict-source-checks` relaxes discovery checks only.

`--scope-config` specifies another reviewed release scope. `--ipeds-anchor start|end` declares the directory-year convention and always computes start/end sensitivity. `--ipeds-dir` enables the linkage stage using cached annual official HD/FLAGS files; stage13 offers `--download-missing` separately. A complete frozen rebuild requires those inputs. `--skip-package` permits exploratory partial-stage runs without certification. Packaging requires completed transformations and QA from the same run, verifies all selected FSA and IPEDS source hashes, checks configured family/year coverage, and refuses stale data, dictionaries, QA or code/metadata.

Large inputs and generated panels live under the selected root and are excluded from Git. The historical external root `/Users/markjaysonfarol13/Projects/FSAVolumeReports_Paneling` remains supported by `--root`/`FSA_ROOT`; the repair release is built separately under `ResearchBuild/2026-09-22-v2` so original datasets remain intact.

## Outputs

- `Panels/final/fsa_volume_reports_panel_1999_2025.parquet`: unrestricted source-preserving research master.
- `Panels/ipeds/fsa_ipeds_linked_panel.parquet`: all master records with annual directory/official-crosswalk identity and scope/time flags.
- `Panels/ipeds/unitid_research/fsa_unitid_award_year_panel.parquet`: UNITID × award-year panel; source-family identities, collision statuses and conservation ledger.
- `Panels/ipeds/ipeds_institution_count_reconciliation.csv`: annual counts with explicit FSA/IPEDS universes and mismatch reasons.
- `Panels/ipeds/fsa_ipeds_strict_panel.parquet`: conservative unbalanced sensitivity subset.
- `Panels/ipeds/fsa_ipeds_bridge.parquet`: unique FSA-key bridge; candidate ledger is separate and contains no aid measures.
- `Dictionary/fsa_volume_panel_dictionary.parquet` and `.csv`: every master column, definitions, units, formulas and policy/source metadata.
- `Dictionary/variable_year_availability.csv`: exact schema availability and value-status counts.
- `Checks/observation_qc/`: rejected-row ledger, source totals, raw exceptional-token counts and schema inventory.
- `Checks/research_qc/`: quantitative conservation and research acceptance.
- `build/research_release_manifest.json`: exact inputs, code/metadata, output hashes, environment and explicit exclusions.

Source-specific panels and cross-sections remain available. The states-plus-DC view is optional for sample design; it never replaces the unrestricted master. Parquet is canonical; full-width exports to legacy XLS are rejected because of its 256-column limit.

Read the status columns. Missing, suppressed, absent-source and structurally unavailable values are not globally zero-filled. Unresolved source IDs remain in quarantine; unresolved matches remain nullable. Descriptor overrides require evidence and reviewer metadata. The annual institution panel preserves source-specific OPEIDs and blocks ambiguous family records. The conservative IPEDS sensitivity view screens reporting-unit ambiguity and temporal instability; it is not a representative national sample or certification of all institutional boundaries.

The second repair reviews [all annual IPEDS dictionaries](Documentation/ipeds_documentation_review.md), the official historical crosswalks, [identity recoveries](Documentation/source_identity_recovery.md), [descriptor corrections](Documentation/descriptor_resolution.md), and [remaining research limits](Documentation/research_limits_review.md). A release includes an executable source snapshot under `build/source_snapshot/`.
