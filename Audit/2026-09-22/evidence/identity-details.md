# FSA identity and IPEDS gap audit (read-only, 2026-09-22)

## Verified critical defect: six-digit parsed full OPEIDs receive two zeros on the wrong side

`Scripts/fsa_build_utils.py:370-383` strips nondigits, accepts/truncates >=8, zero-pads7, but converts <=6 to root6+00. `prepare_component_panel_frame` applies it to every OPE ID without a source-schema width distinction (1410-1416). This is a current-data defect, not a hypothetical formatting concern.

Source proof: `/Users/markjaysonfarol13/Projects/FSAVolumeReports_Paneling/Raw_Title_IV_Reports/Grant_Volume/1999/downloads/AY1999-00Pell.xls`, sheet `AY 1999-2000`, Excel row16, stores Alabama Agricultural & Mechanical University OPEID as numeric100200.0; pandas dtype=str reads `100200`. Same workbook `Field Definitions` Excel row9 defines OPEID as `An 8-digit code identifying the school at its main branch`. Full value must be00100200, not10020000. Direct-loan and FFEL1999 sheets, and campus2001, already contain textual00100200 for this institution.

Actual final clean1999 data split this institution:00100200 has loan subsidized recipients3532 and disbursements11628350 but no Pell;10020000 has Pell recipients2369 and disbursements5520921 but no loans. Actual local IPEDS clean panel2004–2023 shows UNITID100654 and numericOPEID100200.0 for Alabama A&M in every year.

All86 selected local workbooks were reparsed; all370,320 accepted component rows are strict digit IDs after whitespace trim, widths6–8. Under an eight-digit full-ID interpretation:

| Family | Source rows | Incorrect IDs | Files/years |
|---|---:|---:|---|
| Grants |136222|42559|15 files, AY1999–2000 through2013–2014|
| Campus |89038|10261|4 files, AY2012–2013,2013–2014,2015–2016,2019–2020|
| DL |95645|2749|1 file, AY2013–2014|
| FFEL |49415|0|0|

Total55,569 component observations have malformed IDs across20 files. The source-derived CURRENT key union exactly equals the saved unfiltered final panel's200,057 keys. There are47,927 bad-ID rows in that unfiltered panel, and47,559 in the saved186,353-row US-only analysis panel;3,416 distinct malformed IDs.

Strict full-ID zero-padding creates157,160 unique OPEID8+awardyear keys, versus200,057 current:42,897 false splits. Distinct IDs become8,743 versus11,916. No corrected within-family/year duplicate keys and no current-ID->corrected-ID ambiguity. These are key diagnostics, not a rebuilt or certified corrected panel. Measures and descriptors require remerge/reconciliation after repair.

Artifacts: `/tmp/fsa_identity_audit.py`, `/tmp/fsa_identity_audit/source_id_audit.csv`, `/tmp/fsa_identity_audit/source_id_summary.csv`, `/tmp/fsa_identity_audit_run.log`. Scripts read sources and write only /tmp.

## IPEDS linkage is absent and a simple join is insufficient

No UNITID/OPEID crosswalk/linkage implementation is present in this FSA repo. Analysis-ready builder2258-2271 only reorders keys/descriptors and drops source descriptors; final output has noUNITID.

Read-only diagnostic using existing local IPEDS artifact `/Users/markjaysonfarol13/Projects/IPEDSDB_Paneling/Panels/panel_clean_analysis_2004_2023.parquet` selected only year,UNITID,INSTNM,OPEID. Numeric positive integral OPEID padded to8. This IPEDS artifact was not independently rebuilt/validated in this audit. No longitudinal/year alignment policy is established. The following is explicitly an award-year START-to-IPEDS-year trial (2004–2023 overlap), not approved linkage:

| FSA keys |Total|No IPEDS match|Exactly1 UNITID|Multiple UNITIDs|
|---|---:|---:|---:|---:|
|Current IDs|150323|43813|105998|512|
|Full8 normalized source-key diagnostic|120717|10595|109573|549|

IPEDS artifact itself has641 OPEID8+year keys with>1UNITID(max3), versus9,624 OPEID6+year keys with>1UNITID(max88). Concrete same8-digit/year ambiguity:2011,OPEID00109000 hasUNITID106458 Arkansas State University-Main Campus andUNITID448336 Arkansas State University-System Office. Blind join multiplies amounts; attaching the same group-level amounts to campuses also changes their meaning. Across2004–23,283 OPEID8s map to>1 distinctUNITID over time, and896 UNITIDs have>1OPEID8 over time. Require time-aware crosswalk with cardinality/status/reason and explicit institution versus branch/system scope; never treat six-digit root as unique UNITID.

Probe script `/tmp/fsa_ipeds_join_probe.py`; output `/tmp/fsa_identity_audit/ipeds_join_probe.txt`.

## Descriptor and geography gaps (verified)

Unfiltered clean panel has200,057 rows,11,916 current IDs,258 branch-ID rows across95 distinct branch IDs. Collapsing toOPEID6 now creates257 excess repeated keys (413 rows in repeatedOPEID6+year groups); these numbers are contaminated by the ID defect and must be recomputed after repair.

Saved review summary:school6775,zip5686,school_type521,state115 manual-review flags;11957 unique institution-years have at least one review flag. `resolve_descriptor_values` picks first ordered value even on substantive/manual conflict:school1841-1846,state1864-1869,ZIP1895-1900,type1928-1933. Source priority is grant,campus,loan1721-1725. Review workbook builder2518+ exports decisions; no feedback/apply-reviewed-decisions pipeline found. Acceptance2800-2802,2825-2827 explicitly passes any count of auditable conflicts/manual reviews. Thus 'clean/analysis-ready' does not imply unresolved identity/descriptor issues resolved.

Loan descriptor consolidation coalescesDL overFFEL at1654-1655 before final descriptor audit sees onlyloan__ fields1721-1725; internalDL-vsFFEL descriptor disagreements can be hidden (code-level design gap; not quantified here).

US-only filter2168-2170 drops everything outside50states+DC, including blanks. Default builder2249-2252 prefers any existing US-only output. Saved drops:FC6040,blank4453,PR2943,GU93,VI46,AS26,FM26,MP26,PW26,MH24,NR1. Hence IPEDS-compatible US-territory institutions are excluded by default. A geography target must be explicit; blank states should be investigated/enriched, not implicitly equated with out of scope. The4,453 blank states occur2013–2024 starts; not asserted here to beUS institutions.

Tests/test_workbook_parsing.py53-78 tests only pre-padded string00105901;97-98 tests allzero rejection. No numeric/full-ID-length regression test catches actual numeric105901/100200 conversion.
