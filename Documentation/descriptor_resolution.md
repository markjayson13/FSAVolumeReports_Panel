# Descriptor normalization and institutional identity review

The September 22, 2026 descriptor audit found a substantial formatting error in the earlier review queue: numeric ZIP+4 values that lost leading zeros in Excel were truncated to the wrong five-digit ZIP. The repair restores the postal width using domestic source context and preserves the original token. It also resolves a limited set of school-name typography and reversible character-encoding differences. It does **not** equate a shared name, ZIP, OPEID prefix, or historical address with a verified institution-level reporting scope.

This document reports a controlled comparison of the **15,125 institution-year keys** in the pre-repair review queue. The inputs and their SHA-256 hashes are recorded in [diagnostic_summary.json](evidence/descriptor_resolution/diagnostic_summary.json). Subsequent builds can add recovered source identities or apply separate IPEDS-linkage repairs, so these diagnostic counts are not a substitute for the final release's QA counts.

## Scope and results

The diagnostic recomputed all four descriptor comparisons from accepted source-row ledgers for grants, campus-based programs, Direct Loans, and FFEL. It did not use the preferred final display field as a substitute for the source-specific fields. It compared the prior review records with the bridge's unique eligible UNITID and the official IPEDS annual directory files for 1999–2024. The annual anchor used by the baseline bridge was the award-year start year; historical checks retain the individual matching HD years.

| Quantity | Before | After this repair |
|---|---:|---:|
| Institution-year keys with at least one descriptor conflict | 15,125 | 10,276 |
| Descriptor-level review records | 16,382 | 11,277 |
| School-name review records | 8,564 | 8,183 |
| ZIP/postal-code review records | 7,144 | 2,420 |
| School-type review records | 555 | 555 |
| State review records | 119 | 119 |

There are **5,111 resolved prior records**: 4,725 postal-code records and 386 school-name records. Six previously hidden problems are newly flagged, producing a net reduction of 5,105 descriptor records and 4,849 institution-year flags. These are reductions in formatting conflicts, not 4,849 newly established IPEDS identities. The postal repair restores **7,560 source cells** with numeric seven- or eight-digit ZIP+4 tokens; several source cells can belong to the same institution-year.

The evidence set includes every prior review record, every remaining review record, all restored numeric ZIP+4 cells, the six new conflicts, and annual counts:

- [Prior review records with annual and historical IPEDS evidence](evidence/descriptor_resolution/prior_review_rows_with_ipeds_evidence.csv)
- [Restored numeric ZIP+4 source cells](evidence/descriptor_resolution/restored_numeric_zip_plus4.csv)
- [Remaining review records](evidence/descriptor_resolution/remaining_review_rows.csv)
- [Newly exposed conflicts](evidence/descriptor_resolution/newly_exposed_conflicts.csv)
- [Annual counts by descriptor](evidence/descriptor_resolution/review_counts_by_year_and_descriptor.csv)
- [Annual-anchor IPEDS comparisons](evidence/descriptor_resolution/ipeds_comparison_summary.csv)

## Postal repair and provenance

USPS defines ZIP+4 as five digits, a hyphen, and four digits. Microsoft documents that importing postal values as numbers removes leading zeros and recommends storing postal codes as text. These explain why the numeric cell `88183050` is not safely interpreted by taking its first five digits. Sources: [USPS ZIP Code basics](https://faq.usps.com/articles/Knowledge/ZIP-Code-The-Basics), [Microsoft postal-code formats](https://support.microsoft.com/en-us/excel/display-numbers-as-postal-codes).

The implementation requires both a recognized US state, territory, freely associated postal jurisdiction, or military postal abbreviation **and no foreign-school marker** before inferring US numeric postal width. Under that condition, one through five digits are padded to five; seven through nine digits are padded to nine and rendered as ZIP+4. An explicit five-plus-four pattern can have its separator standardized. Unsupported lengths remain unchanged. Foreign or unknown-context postal codes retain their letters and digits; a Canadian or UK code is never reduced to its numeric characters. Whitespace and case can be normalized for comparison.

Every component retains `<source>__raw_zip_code` alongside `<source>__zip_code`, and its source filename, sheet, and Excel row identify the underlying workbook cell. The raw field preserves the parser's original cell token as text; it does not claim to reproduce an Excel display format that was not part of the cell value. The source ledger remains the complete raw-row record. ZIP+4 comparison uses the first five digits only for a correctly formed five-digit-plus-four code. It preserves malformed and foreign codes rather than turning them into plausible US ZIPs.

Two exact OPEID/annual-HD concordance checks are encoded in regression tests:

| Full OPEID | FSA award year / source | Raw numeric postal value | Repaired postal value | Official annual HD evidence |
|---|---|---:|---|---|
| `00204300` | 2006–2007, grants/campus-based; Husson | `44012999` | `04401-2999` | HD2006, UNITID `161165`, ZIP `04401-2999` |
| `00261500` | 2013–2014, Direct Loans; Middlesex County College | `88183050` | `08818-3050` | HD2013, UNITID `185536`, ZIP `08818-3050` |

The repair does not make every resulting address agree with IPEDS. For example, OPEID `02297700` has a domestic numeric token `9610000`, which restores to `00961-0000`, while HD2013 records `00957`. That discrepancy remains. USPS also notes that ZIP boundaries can change and do not necessarily coincide with municipal boundaries; a differing postal code is evidence to investigate, not an automatic different-institution determination. [USPS ZIP Code basics](https://faq.usps.com/articles/Knowledge/ZIP-Code-The-Basics)

## Name, state, and school-type rules

School names are compared after Unicode normalization, case/spacing normalization, treatment of apostrophes and periods, `&`/`AND` equivalence, and optional leading or terminal `THE`. Accents are folded for comparison while the source values remain available. A valid full UTF-8/Latin-1 reversal can repair mojibake such as `MÃ©ndez` to `Méndez`. Lost characters represented by `?` or an unrelated replacement character are not guessed.

The new comparison deliberately leaves renames, unverified abbreviations, campus qualifiers, administrative-office qualifiers, and truncated names under review. Examples remaining in the source data include Everest College/Bryman College; Concorde Career College/Concorde Career Institute; Kaplan College/Maric College; Herzing University/Herzing College; and Jacksonville College/Jacksonville College-Main Campus. These pairs can be historically related without establishing that the reported volume belongs to exactly the same annual IPEDS unit. `ST` is not globally expanded to `SAINT`, and a common prefix does not resolve a truncated institution name.

Five new school-name flags involve damaged Puerto Rico names that the older ASCII-only comparison obscured: OPEID `00393700` in 2016–2017 through 2018–2019 and OPEID `02569400` in 2015–2016 and 2016–2017. The sixth new flag is OPEID `02201800`, 2003–2004: malformed `46410 000` differs from `46410-0000`. Their full source values are in the new-conflict evidence file.

State comparison is case-insensitive. Different nonempty states remain disagreements. School-type comparisons distinguish public, private nonprofit, private for-profit, and foreign categories; `NOT FOR PROFIT` is checked before the `FOR PROFIT` substring. The 555 remaining school-type records are not removed by this ordering fix. Generic private/nonprofit aliases already recognized in the baseline should not be confused with contradictory private/public or nonprofit/proprietary classifications. Historical control changes can make both reported labels meaningful at different dates; they require dated evidence.

## What annual IPEDS corroborates

For the **prior** review queue, the following counts compare the newly normalized source values with the baseline bridge's annual-HD descriptor. A record can match some sources while disagreeing with the others. No-eligible-UNITID rows are kept as a separate outcome and are never converted into descriptor confirmation.

| Descriptor / outcome | Annual HD matches all sources | Matches some sources | Matches no source | No unique eligible UNITID |
|---|---:|---:|---:|---:|
| School, resolved by formatting | 302 | 0 | 84 | 0 |
| School, unresolved | 0 | 5,879 | 2,149 | 150 |
| ZIP, resolved by formatting | 4,216 | 0 | 401 | 108 |
| ZIP, unresolved | 0 | 2,238 | 144 | 37 |
| School type, unresolved | 0 | 540 | 0 | 15 |
| State, unresolved | 0 | 117 | 0 | 2 |

Source-to-source agreement can therefore resolve a formatting dispute while the annual IPEDS descriptor still differs. Conversely, annual HD agreeing with one source does not explain why another source differs. This is why preferred-display resolution and annual institutional identity are separate decisions.

Among unresolved **prior** records, every conflicting normalized source value appears somewhere in the same assigned UNITID's 1999–2024 HD history for 3,100 school-name records, 1,792 postal records, 256 school-type records, and 56 state records. The row-level evidence records the exact supporting HD years. These counts support a possible difference in reference dates; they do not prove it, establish the transition date, or establish an unchanged institutional boundary. No flags were removed merely because a value occurred somewhere in the historical directory.

FSA describes separate processes for updating school names and addresses, allows customized display names, and documents a name-field length limit for the Federal School Code list. This confirms a mechanism for directory/display differences; it does **not** establish that every historical Volume workbook used that exact field or length. A Volume report can also be produced after its award year, so the award year alone does not establish the reference date of its descriptors. Treat a vintage explanation for an individual conflict as an inference until the source dates and institutional history verify it. [FSA school-code update guidance](https://fsapartners.ed.gov/knowledge-center/library/electronic-announcements/2025-04-30/2025-26-federal-school-code-list-participating-schools-may-2025)

Examples requiring that distinction include Husson's historical College/University names and its different UNITIDs in the annual directory history; Marion Military Institute's private/public labels; and Grand Canyon's nonprofit/proprietary labels. A choice based on the present name or current control would erase the time dimension the panel is intended to preserve.

## Annual extent of the repair

Each cell below is a descriptor-record count, not a count of distinct institutions. An institution-year can occur in more than one descriptor column. Award year 2024–2025 had no records in this baseline cross-source descriptor review; absence from the queue is not proof of linkage or scope equivalence.

| Award year | School before | School after | ZIP before | ZIP after | Type before | Type after | State before | State after |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1999-2000 | 458 | 441 | 0 | 0 | 12 | 12 | 7 | 7 |
| 2000-2001 | 451 | 432 | 0 | 0 | 12 | 12 | 6 | 6 |
| 2001-2002 | 1582 | 1522 | 477 | 477 | 48 | 48 | 14 | 14 |
| 2002-2003 | 908 | 875 | 368 | 368 | 39 | 39 | 8 | 8 |
| 2003-2004 | 798 | 772 | 300 | 301 | 34 | 34 | 10 | 10 |
| 2004-2005 | 716 | 690 | 256 | 256 | 33 | 33 | 10 | 10 |
| 2005-2006 | 646 | 621 | 215 | 215 | 31 | 31 | 12 | 12 |
| 2006-2007 | 293 | 276 | 541 | 61 | 14 | 14 | 1 | 1 |
| 2007-2008 | 306 | 285 | 544 | 64 | 19 | 19 | 5 | 5 |
| 2008-2009 | 251 | 234 | 31 | 31 | 19 | 19 | 0 | 0 |
| 2009-2010 | 216 | 202 | 571 | 46 | 19 | 19 | 2 | 2 |
| 2010-2011 | 299 | 285 | 636 | 102 | 21 | 21 | 6 | 6 |
| 2011-2012 | 230 | 215 | 569 | 45 | 9 | 9 | 4 | 4 |
| 2012-2013 | 196 | 185 | 565 | 41 | 12 | 12 | 1 | 1 |
| 2013-2014 | 163 | 154 | 52 | 52 | 28 | 28 | 3 | 3 |
| 2014-2015 | 167 | 160 | 475 | 46 | 16 | 16 | 6 | 6 |
| 2015-2016 | 142 | 136 | 466 | 43 | 17 | 17 | 6 | 6 |
| 2016-2017 | 129 | 122 | 448 | 34 | 17 | 17 | 3 | 3 |
| 2017-2018 | 134 | 123 | 1 | 1 | 32 | 32 | 2 | 2 |
| 2018-2019 | 132 | 121 | 49 | 49 | 28 | 28 | 2 | 2 |
| 2019-2020 | 104 | 98 | 430 | 38 | 21 | 21 | 3 | 3 |
| 2020-2021 | 108 | 102 | 43 | 43 | 20 | 20 | 2 | 2 |
| 2021-2022 | 46 | 43 | 44 | 44 | 16 | 16 | 1 | 1 |
| 2022-2023 | 55 | 55 | 37 | 37 | 19 | 19 | 3 | 3 |
| 2023-2024 | 34 | 34 | 26 | 26 | 19 | 19 | 2 | 2 |

## Remaining research decisions and verification

Descriptor discrepancies and OPEID-to-UNITID discrepancies are related but not interchangeable. A parent institution and its additional locations can share a name, state, and address convention while having different reporting boundaries; a single continuing institution can also change all three descriptors. A zero descriptor-conflict flag establishes only the result of the available source comparison. It neither certifies one-to-one scope nor means that multiple independent descriptors were available. Use the annual bridge, candidate counts, aggregation/reporting-scope evidence, and temporal-linkage review described in [IPEDS linkage](ipeds_linkage.md) before selecting a UNITID research sample.

Remaining review records require evidence appropriate to the question: dated institutional-name/control history for genuine changes; original workbook or authoritative directory evidence for truncations/encoding damage; actual reporting relationships for campus/administrative-office differences; and annual identity candidates where no unique UNITID exists. Do not bulk approve them, use name similarity as an override, or assume all contradictory values have a harmless vintage explanation. Likewise, do not treat every descriptor flag as proof that the FSA quantitative observation is unusable. Preserve the source identity, measures, provenance, and review status so each research design can make an explicit inclusion decision.

The implementation is in `Scripts/fsa_build_utils.py`. The 14 tests in `tests/test_descriptor_resolution.py` cover valid and malformed domestic ZIPs, unknown and foreign contexts, original-token retention in a parsed component, exact annual-HD corroborating examples, cosmetic name equivalence, preservation of substantive qualifiers, reversible versus lost encoding, nonprofit classification, state case, and review-workbook output. Run:

```sh
/usr/local/bin/python3 -m unittest discover -s tests -p test_descriptor_resolution.py -v
```

The quantitative evidence is an exhaustive comparison of the specified baseline review queue, not an exhaustive historical adjudication of each remaining institution. Official-HD histories in the evidence were loaded from `ResearchBuild/IPEDS/official_hd`; source comparisons were reconstructed from accepted-row ledgers, keyed by full OPEID and award year, and passed through the same descriptor functions used by the build. The final release should regenerate its ordinary descriptor-review artifacts from raw inputs after integrating this repair.
