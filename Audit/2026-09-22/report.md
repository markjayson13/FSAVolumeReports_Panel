**FSA Volume Reports panel gap audit — September 22, 2026**

Post-repair clarification: this is the historical, pre-repair audit. The early grant rows described below as “TOTAL” are unlabeled final numeric rows, not literally labeled published totals. Their numeric values are source evidence, but their interpretation requires that qualification. The repaired pipeline retains them as `unlabeled_numeric_summary_candidate`, compares them separately with known institutional values, and does not certify complete reconciliation when source cells are unknown. See [research-use documentation](../../Documentation/research_use.md) for the delivered treatment.

The repository reproducibly assembles FSA report data, but the current analysis-ready panel is not yet a valid institution-level longitudinal panel or a reliable input to an IPEDS match. The most urgent problem is observed OPEID corruption, followed by omitted source observations, a specific Graduate PLUS aggregation error, and loss of missingness and reporting-unit distinctions.

This audit did not change pipeline code, raw workbooks, or saved datasets. This directory contains the audit report and supporting evidence only. Counterfactual ID normalization and the IPEDS join below are diagnostics, not a delivered corrected panel.

**What was verified**

- Retrieved public GitHub commit `1e9aca67935e7d76cd4602cf614a32f63b6de827` (March 14, 2026). The local directory is an archive without `.git`; a downloaded commit snapshot matched all repository content before audit artifacts were added, excluding generated Python caches.
- Inspected the actual external data root: `/Users/markjaysonfarol13/Projects/FSAVolumeReports_Paneling`.
- Recomputed and verified all 216 cached raw-file hashes against their manifests. This establishes local integrity, not current equality to files served by FSA.
- Audited all 86 selected workbooks: 26 grants, 23 campus-based, 26 Direct Loan, 11 FFEL. Reparsed all selected IDs and independently rebuilt the 49 grants/campus cross-sections.
- Ran all 22 existing tests successfully using `/usr/local/bin/python3`.
- Ran the full offline pipeline, including profiling, dictionaries, component construction, merge, review workbooks, state filtering, analysis output and QA, in `/tmp/fsa-audit-rebuild`. All nine generated Parquet panels exactly equaled their saved counterparts using `pandas.testing.assert_frame_equal`. All 23 acceptance checks passed despite the defects below.
- Consulted official FSA and NCES sources for identifier semantics, cumulative Q4 interpretation, revisions, borrower counting and the FFEL transition.

The existing US-only analysis file has 186,353 rows, 10,955 OPEIDs, 26 award years and 43 columns. Its keys are unique as strings, but that does not establish correct institutional identity. The unrestricted clean file has 200,057 rows.

**1. Critical: numeric full OPEIDs are expanded on the wrong side.**

`Scripts/fsa_build_utils.py:370-383` assumes any ID of six or fewer digits is a six-digit root and appends `00`. However, many raw workbooks store the full eight-digit OPEID numerically, losing leading zeros. The field's source definition, rather than the observed string length, must determine whether it is a full ID or a root ID.

In `AY1999-00Pell.xls`, sheet `AY 1999-2000`, Excel row 16, Alabama A&M has numeric OPEID `100200.0`. The field-definition sheet explicitly describes an eight-digit school ID. Its correct normalized full ID is `00100200`; the pipeline generates `10020000`. The same year's loan source already supplies `00100200`.

| Actual AY 1999–2000 output | Pell disbursements | Unsubsidized loan disbursements |
| --- | ---: | ---: |
| `00100200` — Alabama A&M | missing | $7,045,574 |
| `10020000` — Alabama A&M | $5,520,921 | missing |

This produces artificial institutions, false entries/exits and false program missingness. It also corrupts the derived `opeid6`.

| Family | Accepted source observations | Incorrect IDs |
| --- | ---: | ---: |
| Grants | 136,222 | 42,559 |
| Campus-based | 89,038 | 10,261 |
| Direct Loan | 95,645 | 2,749 |
| FFEL | 49,415 | 0 |

Total: **55,569 component observations across 20 source files**. The saved unrestricted final panel has 47,927 malformed-ID rows; the US-only analysis panel has 47,559. These are different denominators because component rows are merged into final rows.

Restoring full-ID leading zeros in the selected-source key diagnostic reduces unique unrestricted institution-year keys from **200,057 to 157,160**, removing **42,897 artificial extra keys**. Distinct IDs fall from 11,916 to 8,743. There are no resulting within-family/year duplicates in this diagnostic. A complete repaired build must still remerge values, resolve descriptors and reconcile amounts.

Required repair: source-aware full-ID normalization, separate full-ID/root-ID parsers, preserved raw IDs, strict numeric/integer validation, explicit invalid-ID rejection reasons and regression cases for numeric `100200`, numeric branch `105901`, padded strings and invalid tokens. Do not apply the current FSA normalizer to numeric IPEDS OPEIDs.

**2. Critical: there is no historical IPEDS linkage, and matching is not universally one-to-one.**

The repository has no UNITID crosswalk or linking stage. Zero-padding makes an OPEID representation compatible; it does not make the FSA reporting unit equivalent to an IPEDS institution. NCES specifically documents this mismatch and notes that some FSA data are effectively reported at the six-digit institution-group level, whereas IPEDS distinguishes reporting units. See [NCES financial-aid data report, appendix A](https://nces.ed.gov/pubs2012/2012834.pdf).

A diagnostic used the available local IPEDS `panel_clean_analysis_2004_2023.parquet`, normalizing positive integral full OPEIDs and joining award-year start to IPEDS year. The IPEDS pipeline was not independently audited or rebuilt here; the year convention is a trial, not an approved rule.

| Trial FSA keys, 2004–2023 | Total keys | No match | Exactly one UNITID | Multiple UNITIDs |
| --- | ---: | ---: | ---: | ---: |
| Current FSA IDs | 150,323 | 43,813 | 105,998 | 512 |
| Full-ID normalization diagnostic | 120,717 | 10,595 | 109,573 | 549 |

Concrete ambiguity: OPEID `00109000`, IPEDS year 2011, maps to Arkansas State University–Main Campus (`106458`) and Arkansas State University–System Office (`448336`). A blind join duplicates aid values. Root-six matching is even less specific and must not be an automatic fallback.

Required output: a versioned historical bridge with FSA ID, IPEDS OPEID, UNITID, award-year bounds, IPEDS reference year, match method, candidate count, reporting-unit scope and resolution status. Audit exact matches, unmatched records, one-to-many and many-to-one cases, mergers, closures and changes over time. Preserve the original FSA reporting unit. Where amounts cover several campuses, retain a group-level panel or explicitly aggregate IPEDS covariates to that group; assigning the full amount to every campus would be incorrect.

An unbalanced institution panel is acceptable. Do not manufacture observations or zero aid simply to create a balanced rectangle.

**3. High: source institutions without usable OPEIDs are silently removed.**

`prepare_component_panel_frame`, lines 1410-1415, removes all rows whose parsed OPEID is invalid. There is no row rejection ledger distinguishing named institutions from totals or footnotes.

Across grants, 66 named institution-year rows are removed. Their raw values include **$189,747,039.38 in Pell disbursements and 53,495 Pell recipient counts**, plus ACG and SMART amounts. Examples include Pittsburgh branch campuses and Louisiana Technical College campuses. These totals span years and are not unique students.

Independent reconciliation confirms actual source-total differences. For AY 2009–2010, the raw Pell TOTAL is 8,341,564 recipients and $29,949,872,587.11; the saved grant panel contains 8,306,621 and $29,798,767,984. Dropped ID-less rows explain the recipient difference and dollar difference apart from integer rounding.

Preserve these observations in a quarantine table and adjudicate IDs from authoritative contemporaneous evidence. Do not assign IDs by name alone or add branch amounts to parent amounts without checking reporting overlap. Reconcile both retained and excluded values to each workbook's published totals.

**4. High: AY 2005–2006 Graduate PLUS amounts are omitted.**

`harmonize_loan_panel`, lines 1599-1610, prefers an existing generic PLUS column using `combine_first`, then drops the split columns at 1624-1628. In the 2005–2006 workbooks, PLUS and GRAD PLUS are separate types, rather than total and components.

The full merged panel consequently omits **$76,082,940** in Grad PLUS disbursements: $6,624,868 Direct and $69,458,072 FFEL. Among institutions retained in the US-only final panel, the omitted amount is $73,735,865.

Direct workbook `DL_AwardYr_Summary_AY2005_2006_All.xls`, sheet `AY2005-2006`, row 791, provides a concrete case: CUNY School of Law (`03191300`) has PLUS $0 and GRAD PLUS $245,726, but the final PLUS disbursement field is $0.

Required: mappings conditional on source schema and award year, distinguishing historical Parent PLUS labels from true totals. Preserve parent/graduate and undergraduate/graduate components and construct validated additive totals. Any overlap between a supposed total and components needs a reconciliation rule, not unconditional preference.

**5. High: disappearing variables, suppressed values and missing observations have indistinguishable NA values.**

`sanitize_numeric_series`, lines 1318-1324, uses `errors='coerce'`; no raw-token or missingness reason survives. Across campus reports for AY 2021–2022 through 2023–2024, **1,138 `<10` recipient cells and 1,138 paired privacy-redacted dollar cells** become ordinary NA. A suppression bound is therefore lost.

Direct reports also change from explicit zeros to dashes in many positions from AY 2017–2018 onward. The audit does not establish that every dash means zero. Nevertheless, `sum(min_count=1)` treats missing components as zero whenever another component is observed; 25,193 Direct undergraduate/graduate unsubsidized-dollar rows have one missing component in 2017–2024. Totals lack a complete/partial flag.

Raw header availability is itself informative:

| Measure family | Observed header availability in selected sources |
| --- | --- |
| Pell | AY 1999–2000 through 2024–2025 |
| ACG and SMART | AY 2006–2007 through 2010–2011 |
| TEACH | AY 2008–2009 onward |
| IASG | AY 2010–2011 through 2023–2024 |
| Perkins recipients/disbursements | AY 2001–2002 through 2018–2019 |
| Perkins federal-award field | Through AY 2015–2016 |

These are source-observation windows, not assertions that legal eligibility dates equal report-column dates. For example, policy termination and late reporting can have different boundaries. The selected campus family ends a year before grants/Direct, so its absence in 2024–2025 is not institution-level zero aid.

Required: exact variable-by-year schema registry, reporting definitions, units and aggregation formulas, plus explicit states for observed value, observed zero, suppressed, source symbol, absent institution record, absent report, not collected and structurally not applicable. Preserve suppression bounds when justified. Do not globally fill NA with zero. Count variables should retain integer types; currency should retain source precision. Current code rounds 68,288 grant dollar cells with cents to integers.

**6. High: final loan measures hide important distinctions and are incompletely documented.**

The final merge drops every `loan_direct__*` and `loan_ffel__*` column after making 15 generic loan measures. Parent/Graduate PLUS and undergraduate/graduate detail are also removed. The intermediate component panels preserve them, so this information can be recovered, but not from the final file alone.

New FFEL originations ended after June 30, 2010; this does not mean all outstanding FFEL loans disappeared. Keep source-specific Direct and FFEL flows, and define any combined origination/disbursement measure separately. See [FSA's explanation of the transition](https://fsapartners.ed.gov/knowledge-center/library/electronic-announcements/2017-09-21/general-subject-federal-student-aid-posts-new-reports-fsa-data-center).

Recipient counts are not automatically additive unique people. For example, University of Phoenix (`02098800`), AY 2009–2010, has Direct subsidized recipients 149,695 and FFEL 330,631; the final field is their sum, 480,326. The available aggregates do not identify the overlap. Raw definitions also warn against adding recipients across loan types, and Parent PLUS counts represent students on whose behalf parents borrowed. Retain source-specific counts and label arithmetic sums accurately. [FSA confirms that these reports do not provide a school-level unique grant-or-loan recipient total](https://fsapartners.ed.gov/knowledge-center/library/electronic-announcements/2026-03-13/federal-student-aid-posts-updated-reports-fsa-data-center).

Actual debt-consolidation loans are explicitly excluded in the examined source definitions. The function name `consolidate_loan_programs` refers to combining dataset columns; it does not measure refinancing/consolidation-loan volume.

The saved panel dictionary omits **all 15 final loan measures** because its prefix logic only knows source-family prefixes (`build_panel_dictionary`, lines 2120-2127). It also attaches some descriptor mappings to unrelated families. A complete final dictionary must include every final column, lineage, formulas, units, validity windows and counting caveats.

**7. High: geography and unresolved descriptor decisions change the sample.**

The default final output is 50 states plus DC. It drops 13,704 unrestricted rows, including 2,943 Puerto Rico rows and 4,453 blank-state rows. Blank state does not establish that an institution is outside the intended research universe. The missing-ID and ID-format defects must be fixed before interpreting these row counts as substantive sample changes.

There are 13,097 descriptor review records across 11,957 institution-years, including 115 state conflicts. Code chooses a provisional value on substantive conflicts and still labels the resulting output clean. A review workbook exists, but no reviewed-decision application stage was found. Acceptance checks pass because the review artifacts exist, not because decisions were completed.

Retain an unrestricted canonical panel. Create geography-specific research views only after an explicit sample rule and identity resolution. Keep unresolved status visible and support versioned, auditable overrides.

**8. Medium: Q4 selection is sensible, but current release coverage and source vintage remain unverified.**

The use of cumulative Q4 for annual grant/loan activity is correct; summing quarterly cumulative reports would double count. FSA also warns that later activity and reporting delays change prior award-year amounts. Q4 means full-year coverage, not necessarily final vintage. The examined historical definitions explicitly describe refreshing at least seven previous quarters.

The downloader defaults to skipping existing paths without checking revisions, and rewrites `downloaded_at` even when a file was merely reused (lines 827-848). One cached nonselected Q1 workbook, `Q11415AY.xls`, is a plain-text placeholder; selected Q4 output is unaffected, but the all-quarter provenance claim is incomplete.

Selection limits are hard-coded to grant/Direct start year 2024 and campus start year 2023. A new complete award year will remain excluded unless the rules change. Define a reproducible vintage cutoff and configurable release scope, preserve original fetch times, and record verification/as-of dates and immutable hashes for revisions.

Live freshness limitation: the FSA JSON inventory endpoint failed/timed out during this audit; its HTML fallback returned an application shell with zero downloadable report links. Therefore, this audit verifies the cached declared scope, not that it is the complete latest official inventory as of September 22, 2026. The public GitHub revision was verified live.

**Required acceptance criteria and repair order**

1. Repair full-ID parsing and retain rejected institutional rows. Rebuild all families from raw sources; reconcile counts and dollars before and after each transformation.
2. Correct the historical PLUS mapping, preserve source channel/subtype fields, and enforce complete-versus-partial aggregation rules and recipient semantics.
3. Build the variable-year schema/definition registry and explicit missingness/suppression statuses. Ensure every final column is documented.
4. Build and validate the historical OPEID-to-UNITID bridge, including temporal alignment and reporting-unit scope. Release unambiguous links separately from unresolved cases; prove that joins neither multiply rows nor change additive totals unexpectedly.
5. Apply reviewed identity/descriptor decisions, then derive explicitly scoped geography views. Keep the unrestricted canonical data available.
6. Replace shape-only acceptance with numerical source reconciliation, invalid-ID/reject accounting, merge conservation, schema coverage, suppression preservation, ID continuity/crosswalk cardinality, dictionary completeness and revision-vintage checks. Retain the existing structural tests as part of that broader suite.

The usable deliverables should be an auditable FSA reporting-unit-by-award-year master, an historical institution bridge with match statuses, and a separately defined UNITID-by-award-year research view where institutional scope supports it. A long program/measure fact table can preserve changing schemas cleanly; a wide analysis view can be generated from it. Neither a balanced panel nor a forced one-to-one match is a prerequisite for sound research.

Supporting evidence is in the adjacent `evidence/` directory: detailed identity/loan/ingestion findings, raw-source ID counts, trial IPEDS matching output, excluded raw institution observations, all-year measure nonmissing counts, reproducible read-only probes, passing test output and exact nine-panel rebuild comparisons.
