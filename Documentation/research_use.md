**Using the repaired FSA panel**

The source master preserves FSA reporting records identified by a full eight-digit OPEID and an award year. One source record (FFEL AY2009, OPEID `88888800`, a default-school placeholder) is explicitly noninstitutional in the bridge and excluded from UNITID assignment. Therefore distinct master OPEIDs are reporting-ID counts, not verified institution counts. A tagged UNITID is an annual IPEDS identity relation, not proof that a parent institution's aid belongs to one campus. Preserve both IDs and the linkage flags in analysis extracts. Award years remain unbalanced; missing rows are never automatically created or filled with zero.

Use the versioned release manifest and the output dictionaries with every extract. The unrestricted master retains territories, foreign institutions, uncertain locations, all source descriptors, original OPEID tokens, workbook/sheet/Excel-row provenance, and quality flags. The US states-plus-DC output is a separately named sample view. Unknown geography does not imply foreign geography.

**Files and their purposes**

| File or directory under the build root | Purpose |
| --- | --- |
| `Panels/final/fsa_volume_reports_panel_1999_2025.parquet` | Unrestricted FSA master, unique OPEID8 × award year. |
| `Panels/ipeds/fsa_ipeds_linked_panel.parquet` | All FSA master records plus annual directory matches and scope/time flags; source measures unchanged. |
| `Panels/ipeds/unitid_research/fsa_unitid_award_year_panel.parquet` | Institution-year panel with separate family OPEIDs, usable/blocked statuses, source ledgers and exact conservation. |
| `Panels/ipeds/ipeds_institution_count_reconciliation.csv` | Annual reporting-unit and institution counts, geography, ambiguities and explicit IPEDS comparison universes. |
| `Panels/ipeds/fsa_ipeds_strict_panel.parquet` | Conservative, unbalanced UNITID × award-year subset passing documented identity/scope screens. |
| `Panels/ipeds/fsa_ipeds_bridge.parquet` | One row per FSA key; suitable for a validated one-to-one join. |
| `Panels/ipeds/fsa_ipeds_candidates.parquet` | Candidate ledger only, without FSA aid measures. Never directly merge it into an aid panel. |
| `Checks/observation_qc/*_quarantine.parquet` | Named source rows with invalid/missing IDs and all original measures. They are accounted for, not assigned invented IDs. |
| `Checks/observation_qc/*_reconciliation.csv` | Accepted plus quarantined known values versus published source totals when available; unknown cells and absent totals are explicit. |
| `Checks/research_qc/raw_to_final_conservation.csv` | Raw accepted source cells versus final source-specific measures. |
| `Dictionary/fsa_volume_panel_dictionary.parquet` | Every master column, its role, units, definition, derivation and source/policy metadata. |
| `Dictionary/variable_year_availability.csv` | Dense measure-by-award-year schema availability and status counts. |
| `build/research_release_manifest.json` | Exact input/code/metadata/output hashes, environment versions, scope, exclusions and acceptance results. |

**Values and statuses**

Every source measure has a companion `__status`, `__raw_token`, `__lower_bound`, and `__upper_bound`. The raw token is stored for exceptional values; observed numeric tokens remain recoverable from the hashed source workbook and Excel-row pointer. All source dollars retain cents as nullable numeric values. Counts must be nonnegative integers; malformed numeric tokens, negative counts and fractional counts fail acceptance. Negative source dollar adjustments are preserved.

The grants workbooks for 1999–2010 start years contain twelve final numeric rows with all institution descriptors blank. They have no literal TOTAL label; examined BIFF cells contain numeric constants rather than SUM formulas. The ledger therefore calls them `unlabeled_numeric_summary_candidate`, and the reconciliation retains their values, row pointers and comparison with accepted plus quarantined observations separately from explicitly labeled totals. A matching candidate is corroborating numerical evidence, not proof of an official total definition. A complete mismatch or impossible count bound fails acceptance. An anonymous numeric row inside the institution table is ambiguous and fails acceptance until reviewed. Reports without a total or such a candidate are explicitly marked `not_reported`; raw-to-final conservation still applies.

| Status | Meaning and handling |
| --- | --- |
| `observed`, `observed_zero` | Source supplies a usable numeric value, including an explicit zero. |
| `source_blank` | The source row exists and the variable is present, but its cell is blank. |
| `source_symbol` | A dash or other nonnumeric marker; do not infer zero without a documented source rule. |
| `suppressed_lt10` | A count is less than ten. Value remains missing; conservative bounds are 0–9. |
| `suppressed` | Privacy-redacted/suppressed value without identified numeric bounds. |
| `unavailable_in_schema` | This report exists, but the measure is not in its schema. Consult policy/reporting chronology. |
| `absent_source_record` | The measure/report is available in this year, but this FSA ID has no row in that source family. |
| `report_not_available` | The selected release has no source-family report for this year. This is not evidence of zero aid. |

Policy eligibility dates are not automatic imputation rules. For example, new Grad PLUS eligibility began in July 2006, but legitimate loans appear in the 2005–2006 reporting schema. Perkins activity/reporting columns persist beyond the origination phaseout. See the policy chronology and exact observed header inventory.

Source loan fields remain under `loan_direct__*` and `loan_ffel__*`, including parent/graduate PLUS and undergraduate/graduate splits where reported. `loan_direct_harmonized__*`, `loan_ffel_harmonized__*`, and `loan__*` are additional derived measures. Exact additive amounts require every reviewed component to be observed. A `__observed_partial_sum` is a sum of available pieces, not necessarily a total. Its companion status identifies completeness. Do not mix an exact series with a partial series without a declared analysis rule and sensitivity checks.

Derived `recipient_count_sum` fields are arithmetic sums of reported student counts, not deduplicated people. Parent PLUS recipients denote students on whose behalf a parent borrowed. Source reports cannot identify all overlap between programs/channels/levels. Unique-recipient bounds are supplied only as mathematically defensible bounds; they are not estimates. Debt-consolidation loans are outside the examined volume-report definitions.

From AY2010 onward the combined loan field is explicitly the Direct-only available reporting scope. It does not assert that FFEL balances or all later FFEL disbursements are zero. Before that transition, a missing channel does not silently become zero; consult exact versus partial fields.

**Institution matching and sample design**

Read `Documentation/ipeds_linkage.md` before using UNITID. The default directory convention is award-year start, with the end-year directory checked separately. IPEDS component collection years do not all describe the same measurement period. Select finance, enrollment, completions or aid periods using each component's documentation.

The linked master keeps ambiguous, unmatched, administrative-office, parent/child, branch, closure, merger and changing-ID cases visible. It does not allocate group-level amounts to campuses or carry the latest mapping backward. The institution panel uses annual identity eligibility and keeps scope restrictions explicit. A family with multiple FSA records for the same UNITID/year has missing measures and a collision status; its source values remain in the ledger. Rows with no included source families are not usable aid observations. The strict sensitivity subset screens conservatively for those issues and unresolved FSA descriptor conflicts. It is not a nationally representative sample or a guarantee that institutional boundaries are invariant. Report annual coverage and exclusions; excluded records can be reviewed for a study-specific sample.

School names, state, ZIP and school type can disagree among sources. `descriptor_review_required` and the individual `*__review_required` flags remain in the master. Reviewed corrections belong in `Metadata/descriptor_overrides.csv` with an exact OPEID/year/descriptor target, replacement value, evidence URL, reviewer and review date. Rebuilds apply the ledger and record previous values. The pipeline does not invent a reviewer decision. The source identity ledger recovers 34 full FSA OPEIDs using same-year independent FSA and HD evidence. Sixteen additional grant rows have verified UNITIDs but unknown FSA OPEIDs; they enter only the institution view after a direct-membership collision check. Remaining missing identities stay quarantined; a name-only candidate is not an approved assignment. See `Documentation/source_identity_recovery.md`.

Master-only aggregates exclude the quarantined observations. For source-wide totals, use the source reconciliation ledgers, which account for accepted plus quarantined known values and identify incomplete cells. Do not append anonymous rows under fabricated IDs or merge the same unidentified institution across programs by name. Institution-level analysis and a national source-total calculation have different inclusion rules.

**Reproduce a frozen build**

The completed release uses cached FSA workbook bytes from the previously downloaded source root, whose hashes are verified against the inventory. Legacy FSA cache timestamps cannot establish the original retrieval date: the earlier downloader refreshed those timestamps even when reusing a file. The repaired release certifies the selected bytes and preserves available workbook run dates; it does not reconstruct an unobserved retrieval history. Official IPEDS directories were retrieved separately with URLs, response metadata and hashes. Upstream FSA freshness is not implied by an offline build.

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 Scripts/00_run_all.py \
  --root ResearchBuild/2026-09-22-v2 \
  --skip-download \
  --ipeds-dir ResearchBuild/IPEDS/official_hd_v2 \
  --ipeds-crosswalk-dir ResearchBuild/IPEDS/official_crosswalks \
  --run-qaqc
```

The root must already contain a selected source inventory and raw files. `Raw_Title_IV_Reports` may be a read-only symlink for an offline rebuild; downloading through that symlink is deliberately refused. New independent source roots can use stage 01 to discover and download reports. It validates newly retrieved workbooks before replacement and archives changed prior bytes. `--skip-existing` explicitly reuses a frozen cached vintage and does not claim remote revalidation. `Metadata/release_scope.json` pins the requested annual/Q4 scope; `--scope-config` selects another reviewed scope.

Use `build/environment-requirements.txt` to reproduce the validated package versions. The source files, IPEDS downloads and generated artifacts in `ResearchBuild/` are excluded from Git; code, metadata, research documentation and tests are versionable. A successful test suite alone does not certify a dataset: the full build must also pass quantitative acceptance and record its exclusions.

Parquet is the canonical export; it preserves nullable numbers, booleans and string IDs. Legacy XLS cannot represent this full-width research master and must not be used as a canonical export. To open in Python, use `pandas.read_parquet`; in R use `arrow::read_parquet`. Keep OPEIDs as strings. A study-specific CSV extract should retain the corresponding value-status columns and the release identifier.
