# FSA research limits

This repository owns FSA reporting-unit panelization. Institution-count reconciliation, parent/child reporting scope, annual OPEID-to-UNITID evidence and IPEDS timing belong to [IPEDS-FSA_Panel](https://github.com/markjayson13/IPEDS-FSA_Panel). The historical mixed review is preserved there.

The reviewed FSA inventory contains 86 selected workbooks and 1,515 header records. Exact observed measure-year sets are recorded in `Metadata/source_schema_inventory.csv`; `Metadata/program_policy_events.csv` distinguishes confirmed policy changes from unexplained source-schema changes. See [policy chronology and official evidence](policy_and_reporting_changes.md) and [loan harmonization](loan_harmonization.md).

Material limits remain:

- A full OPEID identifies an FSA reporting unit, not automatically an institution or a campus-exclusive aid population.
- Missing headers, unavailable reports, absent source rows, blanks, dashes, suppression and explicit zero are distinct. A policy end date does not authorize zero filling.
- Recipient counts overlap across programs, channels, institutions and years. Harmonized sums are not deduplicated people. Debt-consolidation loans are outside the examined volume definitions.
- The precise cause of Direct Loan dash reporting from 2017, the 2016 Perkins allocation-column removal, and Campus-Based suppression publication from 2021 remain unverified. Their unresolved causes remain explicit in the policy register.
- Seventy-six selected workbooks contain definition sheets; ten do not. Later definitions cannot serve as direct evidence for missing earlier documentation.
- Campus-Based allocations, payments, transfers and nonfederal shares differ. Available evidence does not supply a complete annual mapping to all individual FISAP accounting lines.
- The release does not supply a complete Pell eligibility/maximum, fee, appropriation or inflation series. Continuous columns do not imply constant eligibility or purchasing power.
- The source panel is unbalanced. Its files are a reviewed frozen vintage, not a guarantee of the latest official publication.

The [source identity ledger](../Metadata/source_identity_resolutions.csv) retains all 87 reviewed source-row cases: 34 approved full-OPEID repairs and 53 unresolved OPEIDs. The latter remain quarantined in the FSA master; UNITID-only evidence is preserved for downstream evaluation. No invented OPEID or parent aid allocation is used. Source-total reconciliation counts accepted and quarantined known values separately and records incompleteness.

Use actual build manifests and conservation checks for coverage counts. A successful software test suite alone does not establish that a particular dataset was rebuilt or validated.
