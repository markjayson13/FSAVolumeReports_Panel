# FSA ingestion, grants/campus and QA audit

Read-only review of repository and actual external artifacts at `/Users/markjaysonfarol13/Projects/FSAVolumeReports_Paneling`; all scratch outputs under `/tmp`.

## Verified good

- Existing inventory: 216 downloaded manifest entries; 86 selected reports (26 grants, 23 campus, 26 Direct Loan, 11 FFEL).
- Independently recomputed SHA256 for all 216 raw files, all match saved manifest SHA. This verifies local integrity, not source freshness. All manifests say `download_status=existing`, timestamps March 14 2026.
- Parsed and rebuilt all 49 selected grants/campus cross-sections with current code in memory. `pd.testing.assert_frame_equal` passes for all 49 saved Parquets, zero unmapped headers and no parse warnings in these selected files.
- Grant panel 136,222 rows, campus panel 89,038. Actual year coverage matches declared 26/23 report scope. Quarterly selection uses cumulative Q4, preserving annual-vs-quarter distinction. No invented zero-fill for absent program columns.

## Material findings

1. **Raw institution observations are silently discarded for invalid/missing OPEID.** `Scripts/fsa_build_utils.py:1410-1415` masks missing/invalid OPEID and returns only valid keys, with no row reject ledger. In grants: 66 named institution-year rows excluded, containing $189,747,039.38 Pell disbursements, 53,495 Pell recipient counts, $5,834,476.12 ACG and $3,796,378.75 SMART disbursements. Examples include University of Pittsburgh branch campuses and Louisiana Technical College campuses. Campus: 21 named rows with `00000000` excluded, all measures zero. Values are gross raw excluded values; overlapping branch/main reporting must be resolved before recovery or aggregation.

   Independently checked source workbook TOTAL rows against institution sums and saved panel:
   - AY1999-2000 Pell recipients source TOTAL 3,912,018, saved 3,908,874; missing-OPEID rows explain 3,144 difference. Source dollars $7,211,832,511.51, saved $7,206,311,978; dropped values $5,520,533.25 plus rounding difference.
   - AY2009-2010 Pell recipients source TOTAL 8,341,564, saved 8,306,621; missing-OPEID rows explain 34,943 difference. Source dollars $29,949,872,587.11, saved $29,798,767,984; dropped dollars $151,104,628.97 plus rounding difference.

   Required: quarantine named invalid-ID rows separately from totals/footnotes, preserve raw row identity and values, adjudicate source-specific IDs, and reconcile both full raw and retained panel totals.

2. **Suppression, source dash, absent schema, blank cell and absent institution are collapsed into the same NA.** `sanitize_numeric_series`, lines 1318-1324, uses numeric coercion without audit/status. In campus AY2021-2022 to AY2023-2024 there are 1,138 actual `<10` recipient cells and 1,138 paired privacy-redacted dollar cells. All suppression information disappears. Counts by year: FSEOG/FWS 52/331, 73/324, 78/280. `<10` supports a bound, never an exact count or an ordinary missing label. There are also 4,086 `$ -` Perkins federal award cells in AY2010-2011 that become NA (adjacent-year series is all zero); the dash meaning needs documented source rules, not guessing. Across all selected grant/campus cells, 216,145 nonempty raw numeric fields become NA: 208,796 grants and 7,349 campus. Most are dash tokens, not necessarily errors; the failure is loss of distinctions and no diagnostics.

   Required: per-observation value status (observed / suppressed / source dash / missing / not reported / not applicable), exact variable-year availability matrix, report-presence flags, raw token preservation, suppression bounds where justified.

3. **Currency precision is discarded.** Lines 1327-1329 round every measure to Int64, and lines 1436-1439 apply it to dollars and counts alike. Verified 68,288 grant dollar cells had nonzero cents; all are rounded. Net aggregate difference across these cells is only +$223.77, so this is lower priority than ID/missingness. Use decimal cents or retain numeric precision; integer type for counts only.

4. **Q4 is cumulative full award-year reporting, not final source vintage.** Download code lines 827-849 defaults to accepting every existing path without remote checks and rewrites downloaded_at to current run time even if never downloaded that run. Old grant workbook Definitions explicitly state seven prior quarters are refreshed for adjustments (Q40607AY.xls) and at least seven prior quarters (Q40910AY.xls). Current pipeline does not compare content, ETag, Last-Modified or source revision date when a file exists. Needs original fetched time, verification time, source data-run/as-of time and immutable versions/checksums, plus controlled refresh for revisable vintages.

5. **All-quarter provenance claim is false for one cached file.** Nonselected `Q11415AY.xls` is a plain-text placeholder: `File cleared temporarily to save space. Alternate solution in progress.` Profiling flags it, but selected-source acceptance passes. Q4 grant panel is unaffected. Default existing-file skip would perpetuate the placeholder.

6. **Acceptance gates prove shape and artifact existence, not statistical validity.** `acceptance_audit` lines 2737-2902 checks saved summaries, duplicates, output presence and year labels. Conflicts/manual-review rows always pass when artifacts exist (2797-2803 and 2821-2827). No reconciliation to source totals, raw parse-token loss, numeric validity/nonnegativity, missingness classification, source-vintage coverage, or IPEDS link cardinality gate. Saved acceptance is all pass despite findings above.

   A direct isolated negative probe also demonstrates `source_qaqc` lines 2661-2671 will mark `selected_sheet_found_for_selected_files=True` for a selected file entirely absent from the profiles table: left join produces NaN; `.eq("")` does not catch NaN. The probe used a placeholder file and unrelated profile row; every source-QA check still passed. Current actual selected files were successfully parsed independently, so this is a testable latent gate defect, not a claim those 86 profiles are absent.

## Observed schema changes (raw local headers, not inferred policy definitions)

- Pell columns throughout 1999-2000 to 2024-2025.
- ACG and SMART columns only 2006-2007 to 2010-2011.
- TEACH columns start 2008-2009.
- IASG columns 2010-2011 to 2023-2024, absent in 2024-2025.
- Perkins federal award header stops after 2015-2016; recipient/disbursement headers stop after 2018-2019. The 2019-2020 onward workbook footnote explicitly says these columns were removed because new Perkins loans are no longer made.
- Campus privacy suppression visible from 2021-2022.
- Current dictionary aggregates first_year / last_year at 1277-1286, which does not encode year gaps, source measurement definitions, suppression or program lifecycle.

## Rebuild performance

`profile_workbooks` 1086-1091 reads every manifest local_path and calls local Excel parsing. No network calls occur in this routine. No need to redownload when `--skip-download`; 216 workbook profiling plus large review workbook generation may take time, especially per-cell style loops in stage09.

## Audit files

- `/tmp/fsa_grants_campus_audit.py`: independent 49-file read/rebuild/check script.
- `/tmp/fsa_grants_campus_audit.json`: exact per-file equality, coercion counts/tokens, rounding and excluded-row records.
- `/tmp/fsa_dropped_grants_campus_institutions.json`: full named invalid-ID rows and original numeric measures.
- This report: `/tmp/fsa_ingestion_audit.md`.
