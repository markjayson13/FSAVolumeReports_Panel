# FSA loan and schema audit (read-only)

Audited repository: `/Users/markjaysonfarol13/Projects/FSA/FSAVolumeReports_Panel-main`.
Observed durable artifacts: `/Users/markjaysonfarol13/Projects/FSAVolumeReports_Paneling`.
Interpreter: `/usr/local/bin/python3` (all dependencies available). No source or durable data edited.

## Verification

Read raw loan workbooks including field definitions, component parquet files, merged loan file, final US panel, and dictionaries. Independently recomputed `outer_merge_panels -> harmonize_loan_panel -> consolidate_loan_programs` in memory from saved component panels: `pd.testing.assert_frame_equal` against saved merged loan parquet PASSED. Therefore the issues below are present in the current code AND observed durable merged data, not merely hypothetical.

Direct component: 95,645 rows, 54 columns (45 loan measures).
FFEL component: 49,415 rows, 34 columns (25 loan measures).
Merged loan: 137,396 rows, 24 columns (15 loan measures).
Analysis-ready US final: 186,353 rows, 43 columns.

## Confirmed: 2005-2006 Graduate PLUS is omitted from final PLUS totals

Code `Scripts/fsa_build_utils.py:1599-1610` prefers existing generic PLUS via `combine_first` instead of checking whether generic PLUS is an aggregate or the older Parent PLUS label; `:1624-1628` then drops split columns. `:99-104` encodes the problematic equivalence. Unit test `tests/test_loan_harmonization.py:14-49` reinforces generic preference but only has grad value 0 in the overlapping fixture.

Raw files:

- `Raw_Title_IV_Reports/Loan_Volume/Direct/2005/downloads/DL_AwardYr_Summary_AY2005_2006_All.xls`, sheet `AY2005-2006`, header rows 5-6: separate `DL PLUS` and `DL GRAD PLUS` column groups.
- `Raw_Title_IV_Reports/Loan_Volume/FFEL/2005/downloads/FFEL_AwardYr_Summary_AY2005_2006_All.xls`, sheet `AY2005-2006`: separate `FFEL PLUS` and `FFEL GRAD PLUS` groups.
- Both have `Field Definitions` sheets describing four loan types; generic PLUS cannot already be a sum since some positive Grad PLUS rows have PLUS=0.

Concrete example: Direct sheet Excel row 791, CUNY School of Law at Queens College, OPEID `03191300`, AY2005-2006. PLUS recipients=0, PLUS disbursements=$0. GRAD PLUS recipients=24, loans originated=29, originated amount=$253,554, disbursements count=61, disbursements=$245,726. Saved merged loan and US final both report `loan__plus_recipients=0`, `loan__plus_disbursements=0`.

Independent FFEL example: Excel row248, Southern California University of Health Sciences, OPEID `00122900`; PLUS recipients=0 and disbursements=$0, GRAD PLUS recipients=4 and disbursements=$8,329.

2005-2006 omitted Grad PLUS component sums:

| Scope | Direct disbursements | FFEL disbursements | Combined omitted disbursements |
|---|---:|---:|---:|
| Full source/merged panel | 6,624,868 | 69,458,072 | 76,082,940 |
| Institutions retained in final US-state panel | 6,624,868 | 67,110,997 | 73,735,865 |

Full-source recipient-count components omitted: Direct518, FFEL5431; total5949 (NOT asserted unique people). Positive Grad PLUS dollar rows: Direct27 and FFEL362 (component rows, not deduplicated institutions). US-only recipient-count components omitted: Direct518 and FFEL5254.

Existing `Checks/panel_qc/loan_harmonization_summary.csv` contains mismatch counts but they are not fatal: DL PLUS overlap1077/exact197; FFEL PLUS disbursement overlap4578/exact931. All those overlaps are AY2005-2006. Generic vs Grad alone mismatch is not itself proof of error; raw four-type headers and zero PLUS/positive Grad examples provide the proof.

## Confirmed: merged recipient fields are arithmetic sums, not deduplicated borrowers

Code `Scripts/fsa_build_utils.py:1666-1679` applies identical summation to recipients, dollar measures and transaction counts. `tests/test_loan_harmonization.py:51-79` tests 10+5=15 recipients with no borrower-level deduplication. No borrower identifiers exist in these institution aggregate files, so exact combined unique counts are unidentified.

Real overlap: 7,664 institution-year keys exist in both Direct and FFEL, across 3,586 OPEIDs; 2,805 keys overlap in AY2009-2010. In that year, both sources have positive subsidized recipients for 2,637 keys, unsubsidized for 2,612 keys, and harmonized PLUS for 1,774 keys.

Concrete AY2009-2010 University of Phoenix, OPEID `02098800`: Direct subsidized recipients149,695 plus FFEL330,631 -> merged480,326. Raw source evidence: `DL_Dashboard_AY2009_2010_Q4.xls`, `Award Year Summary`, Excel row131; `FL_Dashboard_AY2009_2010_Q4.xls`, same sheet, Excel row123. This proves coexistence and summation, not the unknown number of individuals overlapping. The valid unique range for this type/program combination is [330631,480326] absent further information.

2005/2006/2009/2010 raw `Field Definitions` explicitly states that recipients are students for subsidized/unsubsidized/Graduate PLUS and students on whose behalf Parent PLUS was taken, and that categories cannot be summed for accurate total unique recipients because students may have multiple types. Undergraduate/graduate split recipient sums also require a disjointness assumption, not documented in the pipeline.

The same definitions expressly exclude actual debt-consolidation loans. The pipeline's `consolidate_loan_programs` means combining Direct and FFEL columns; it does not produce consolidation-loan volume.

## Confirmed: symbol and structural missingness are conflated

`Scripts/fsa_build_utils.py:1318-1329` coerces any unrecognized token (including '-') to NA and rounds every numeric measure to Int64, without reason flags or coercion reporting. Literal zeros dominate relevant 2016-17 categories; raw Direct2017-18 onward uses literal '-' in those positions. Example subsidized recipient token counts: AY2016-17 contains376 literal zeros; AY2017-18 contains369 dashes; AY2024-25 contains333 dashes. The audit has not established official dash semantics, so do not categorically label these zeros until source guidance confirms.

Regardless of dash meaning, `sum(min_count=1)` at1601 and1677 implicitly treats one missing summand as zero whenever another is observed but all-missing staysNA. Observed Direct unsubsidized undergrad/graduate dollar one-side-missing cases:25,193 institution-years across2017-2024. Parent/Graduate PLUS one-side-missing cases excluding2005:21,900 across2017-2024. Thus scalar totals do not carry whether they were complete or partial.

The existing panel coverage matrix reports rows by family/year, not cell status or program availability. Panel has no per-cell observed-zero/source-blank/source-symbol/structurally-unavailable/nonparticipant flags or source membership flags.

Observed non-null program availability (award-year START values, not policy claims):

- Pell1999-2024; ACG2006-2010; SMART2006-2010; TEACH2008-2024; IASG2010-2023.
- FWS/FSEOG2001-2023; Perkins recipients/disbursements2001-2018. Perkins federal-award column2001-2015 is zero for all56,152 non-null observations.

## Confirmed: useful source dimensions disappear from final panel

`Scripts/fsa_build_utils.py:1624-1628` removes undergrad/grad and parent/grad splits after coalescing. `:1690-1696` drops every `loan_direct__` and `loan_ffel__` column after creating15 generic measures. Separate component artifacts preserve these data, so they are recoverable, but the final analysis file cannot distinguish funding channel or subtypes. Recommend preserve source components and add explicitly named harmonized measures, with provenance/completeness metadata and a versioned per-year semantic registry.

## Confirmed: final dictionary omits all15 loan measures

`Scripts/fsa_build_utils.py:2120-2127` tries each source-family prefix; no `loan__` prefix is in `COMPONENT_FAMILIES`, and synthetic dictionary cases at2103-2115 cover only keys and descriptors. Comparing final43 columns against saved `Dictionary/fsa_volume_panel_dictionary.csv` yields exactly15 missing columns: all three loan groups x five measures. The dictionary also attributes grant/campus descriptor fields to unrelated families because it loops every family rather than the row's family (e.g. `campus__school` gets direct_loans,ffel,grants sources). No final variable-level definitions, aggregation formulas, recipient caveats, zero rules or complete annual availability registry are supplied.

## Lower-priority latent issue (not an observed dropped amount in current loan artifacts)

Header parser can emit `disbursements_amt` if a header contains the literal word loan (`:1177-1178`), but loan harmonization's metric tuple at92-98 only recognizes `disbursements`. Unrecognized source-prefixed columns would then be dropped1690-1696. Current real loan artifacts consistently use `disbursements`, so this is a future schema fragility, not additional proven historic loss. Campus Perkins uses `disbursements_amt` and is unaffected by loan consolidation.
