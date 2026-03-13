# FSAVolumeReports_Panel

Pipeline for panelizing Federal Student Aid Title IV volume reports with exact `opeid8` + `award_year` keys.

## Scope

- Grants: `AY 1999-2000` through `AY 2024-2025 Q4`
- Campus-based: `AY 2001-2002` through `AY 2023-2024`
- Direct loans: `AY 1999-2000` through `AY 2024-2025 Q4`
- FFEL: `AY 1999-2000` through `AY 2009-2010 Q4`

Quarterly families are downloaded in full for provenance, but panel construction only uses the cumulative `Q4` workbook for complete award years. `AY 2025-2026` is intentionally excluded from panel outputs until `Q4` exists.

## Data Root

Large raw files and panel artifacts live outside the repo:

```bash
export FSA_ROOT=/Users/markjaysonfarol13/Projects/FSAVolumeReports_Paneling
```

The pipeline creates:

- `Raw_Title_IV_Reports/`
- `Cross_sections/`
- `Dictionary/`
- `Panels/`
- `Checks/`
- `build/`

## Entry Points

Run the full pipeline:

```bash
python3 Scripts/00_run_all.py --root "$FSA_ROOT" --run-qaqc
```

Or use the repo shell wrapper for a safer live run with venv bootstrap, dependency install, unittest smoke test, strict source preflight, and then the full pipeline:

```bash
bash Scripts/run_live_pipeline.sh
```

Run only the source preflight and inspect the exact files that would be selected:

```bash
python3 Scripts/00_run_all.py --root "$FSA_ROOT" --preflight-only
```

Wrapper version:

```bash
bash Scripts/run_live_pipeline.sh --preflight-only
```

Or call stage `01` directly:

```bash
python3 Scripts/01_download_title_iv_reports.py --root "$FSA_ROOT" --verify-only
```

The preflight writes:

- `Checks/download_qc/preflight_release_inventory.csv`
- `Checks/download_qc/preflight_selected_panel_files.csv`
- `Checks/download_qc/preflight_inventory_summary.csv`
- `Checks/download_qc/preflight_validation.csv`

By default, the pipeline is strict: it will fail before downloading if the live source inventory does not match the expected panel scope.

Run individual stages:

```bash
python3 Scripts/01_download_title_iv_reports.py --root "$FSA_ROOT"
python3 Scripts/02_profile_workbooks.py --root "$FSA_ROOT"
python3 Scripts/03_build_dictionary.py --root "$FSA_ROOT"
python3 Scripts/04_panelize_grants.py --root "$FSA_ROOT"
python3 Scripts/05_panelize_campus_based.py --root "$FSA_ROOT"
python3 Scripts/06_panelize_loans.py --root "$FSA_ROOT"
python3 Scripts/07_merge_fsa_panels.py --root "$FSA_ROOT"
python3 Scripts/08_build_panel_dictionary.py --root "$FSA_ROOT"
python3 Scripts/QA_QC/00_source_qaqc.py --root "$FSA_ROOT"
python3 Scripts/QA_QC/01_panel_qaqc.py --root "$FSA_ROOT"
python3 Scripts/QA_QC/02_acceptance_audit.py --root "$FSA_ROOT"
```

For offline testing, stage `01` also accepts `--page-html /path/to/title_iv_page.html`.
For reduced fixture tests, you can bypass strict live-scope validation with `--no-strict-source-checks`.

## Canonical Outputs

- `Panels/grants/panel_grant_volume_1999_2025.parquet`
- `Panels/campus_based/panel_campus_based_volume_2001_2024.parquet`
- `Panels/loans/panel_direct_loan_volume_1999_2025.parquet`
- `Panels/loans/panel_ffel_loan_volume_1999_2010.parquet`
- `Panels/loans/panel_loan_volume_1999_2025.parquet`
- `Panels/final/fsa_volume_reports_raw_1999_2025.parquet`
- `Panels/final/fsa_volume_reports_clean_1999_2025.parquet`
- `Dictionary/fsa_volume_dictionary.parquet`
- `Dictionary/fsa_volume_dictionary.csv`

## QA/QC

The pipeline writes auditable checks for:

- release inventory and selected panel files
- workbook profiling and header signatures
- unmapped actionable headers
- duplicate `opeid8` + `award_year` keys
- year coverage gaps inside the selected official inventory
- descriptor conflicts in the merged final panel
- top-level acceptance checks

## Tests

The repo currently uses `unittest`:

```bash
python3 -m unittest discover -s tests -v
```
