# Loan harmonization for research

The source reporting unit is an FSA school reporting under an eight-digit OPEID. These files are aggregates, not student records. The implementation preserves every original `loan_direct__*` and `loan_ffel__*` column, including unknown measures, and adds separately named harmonized measures. It never discards a source column after making a combined measure.

## Time and source scope

Award year is the start/end label carried by the workbook. It is not necessarily the calendar or fiscal year in which cash was disbursed. In the AY2005–2006 Direct and FFEL workbooks, the `Field Definitions` sheet assigns a loan to the award year containing the beginning of its loan period, and associates disbursements with that loan cohort. Consolidation loans are explicitly excluded. A school appears if it has at least one qualifying loan. Consequently, the script function called `consolidate_loan_programs` combines lending channels; it does not measure debt-consolidation lending.

The reviewed schema covers Direct AY1999–2000 through AY2024–2025 and FFEL AY1999–2000 through AY2009–2010. New years retain their source data but receive `schema_not_reviewed` for derived measures until their schema is reviewed. This is deliberately independent of whether a particular row happens to have nonmissing cells.

| Source and award-year start | Harmonized category | Required source categories |
|---|---|---|
| Both, 1999–2004 | PLUS | Generic PLUS |
| Both, 2005 | PLUS | Generic PLUS (parent) + Graduate PLUS |
| Both, 2006 onward within reviewed scope | PLUS | Parent PLUS + Graduate PLUS |
| Direct, 2010–2011 | Subsidized | Undergraduate + Graduate |
| Direct, all other reviewed years | Subsidized | Reported Subsidized |
| Direct, 2010 onward | Unsubsidized | Undergraduate + Graduate |
| Direct, 1999–2009; FFEL, all reviewed years | Unsubsidized | Reported Unsubsidized |
| FFEL, all reviewed years | Subsidized | Reported Subsidized |

The AY2005 exception is essential. The generic PLUS column is a parent component, not an already combined total. The original workbook has four categories, including a separate Grad PLUS column. Graduate PLUS eligibility began July 1, 2006, but the [June 23, 2006 FSA implementation announcement](https://fsapartners.ed.gov/knowledge-center/library/electronic-announcements/2006-06-23/summary-hera-operational-implementation-guidance-cps-cod-system-and-edexpress-suite-updated-guidance-direct-plus-loan-graduate-and-professional-students-supersedes-5162006-electronic) explicitly provided Direct Grad PLUS processing for the 2005–2006 award year. Combined with the loan-period definition, this means AY2005 Grad PLUS must not be erased by a rule based only on a July 2006 effective date. The Direct operational announcement does not independently establish FFEL processing rules; FFEL's retained amounts and category interpretation are established by its actual workbook.

The [June 16, 2010 FFEL implementation guidance](https://fsapartners.ed.gov/knowledge-center/library/dear-colleague-letters/2010-06-16/gen-10-10-subject-implementation-guidance-deadline-making-loans-under-federal-family-education-loan-ffel-program) prohibits first FFEL disbursements on or after July 1, 2010 but permits eligible subsequent disbursements on older loans. A disappeared FFEL report therefore does not prove no FFEL cash activity. `loan__program_scope` is `direct_and_ffel` for AY1999–2009 and `direct_only_available_report` for AY2010–2024. In the latter scope, combined measures use Direct only; the script does not fabricate zero FFEL values. Comparing these measures across 2010 requires this scope and cohort distinction.

## Names, missingness, and precision

`loan_direct_harmonized__*` and `loan_ffel_harmonized__*` contain measures within one lending channel. `loan__*` combines the reviewed channels within the explicitly stated reporting scope. Source-specific descriptors are retained; the convenience `loan__` descriptor prefers Direct, then FFEL, without resolving discrepancies.

Every derived numeric measure has `__status` and `__observed_partial_sum`. The unsuffixed measure is populated only when all schema-required components are observed. An absent component column, missing cell, source symbol, suppressed value, or absent source record never becomes zero. The partial sum retains the observed amounts, including when an exact total is unavailable; it must not be used as an exact total without checking status. When all components are unobserved, even the partial sum is missing. Known source zeros remain observed zeros.

Statuses are `complete_source_reported`, `complete_component_sum`, `complete_direct_only_scope`, `incomplete_component_sum`, `no_observed_components`, `absent_source_record`, and `schema_not_reviewed`. Source status fields, when present, determine which cells are observed. Legacy input without status fields is supported using nonmissing numeric values, but cannot recover the reasons older parsing lost.

Nominal dollar amounts use nullable floating-point columns without whole-dollar rounding. Counts use nullable integers; fractional and negative counts fail validation rather than being rounded. Do not assume nominal dollars are comparable purchasing-power measures over time. No deflation is performed.

## Recipients are overlapping populations

Derived counts are named `*_recipient_count_sum`, never `*_recipients`. They sum category counts; they are not unique borrower counts. The workbook defines Parent PLUS recipients as students on whose behalf borrowing occurred, whereas the other categories count student borrowers. Students can appear under more than one type, level, or channel. The current [FSA Data Center explanation](https://fsapartners.ed.gov/knowledge-center/library/electronic-announcements/2026-03-13/federal-student-aid-posts-updated-reports-fsa-data-center) also cautions that these reports do not supply a total of unique recipients across grants and loans.

Within a named category, `*_unique_recipient_lower_bound` is the maximum of known component lower bounds; `*_unique_recipient_upper_bound` is the sum of all required upper bounds and remains missing if any upper bound is unknown. These bounds describe the union of **student recipients**, not parent borrower accounts. They rely on nonnegative counts and do not assume different grade levels or loan programs contain disjoint people. If a source provides an explicit suppressed count interval, the interval can contribute to bounds but cannot make the exact count sum observed. Unknown missing counts can support a known lower bound from another component but never a finite upper bound.

For University of Phoenix, OPEID `02098800`, AY2009–2010 subsidized recipients are Direct 149,695 and FFEL 330,631. The arithmetic sum is 480,326; the identified interval for unique students is 330,631–480,326. Microdata or authoritative overlap information would be required to narrow it.

## Verification evidence

The module has independent tests for the AY2005 repair, historical level schemas, overlapping recipients, suppression bounds, missing columns, absent lending channels, explicit post-2010 scope, future unreviewed schemas, preservation of unknown columns, fractional counts, cents, metadata completeness, and idempotence.

Read-only verification on the pre-repair saved component panels reproduced these AY2005–2006 source-channel totals (the root pipeline rebuild separately corrects OPEIDs):

| Lending channel | Generic Parent PLUS disbursements | Retained Graduate PLUS | Corrected PLUS disbursements |
|---|---:|---:|---:|
| Direct | $2,151,722,500 | $6,624,868 | $2,158,347,368 |
| FFEL | $6,053,522,622 | $69,458,072 | $6,122,980,694 |
| Both source channels | $8,205,245,122 | $76,082,940 | $8,281,328,062 |

These are sums of observed source-channel amounts, not certified unduplicated UNITID totals. The repaired Direct value for CUNY School of Law, OPEID `03191300`, is $245,726 instead of $0. If the FFEL counterpart is absent, the both-channel exact measure stays missing and its observed partial sum is $245,726; the missing counterpart is visible rather than assumed to be zero. All original source columns compared equal before and after harmonization.

Raw verification files: `Loan_Volume/Direct/2005/downloads/DL_AwardYr_Summary_AY2005_2006_All.xls` and `Loan_Volume/FFEL/2005/downloads/FFEL_AwardYr_Summary_AY2005_2006_All.xls`, summary and `Field Definitions` sheets under the data root's `Raw_Title_IV_Reports`. The earlier audit details row-level examples in `Audit/2026-09-22/evidence/loan-details.md`.
