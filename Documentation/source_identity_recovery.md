# Missing source identity review

The first release retained 87 institution-like source rows without valid full OPEIDs: 66 grant rows with blank IDs and 21 Campus-Based rows with the invalid placeholder `00000000`. This review examines every one. The [resolution ledger](../Metadata/source_identity_resolutions.csv) records the original workbook hash, URL, selected sheet and Excel row, expected raw descriptors, independent evidence, decision and unresolved reason. A source-row recovery is distinct from an IPEDS UNITID assignment or a claim that program reporting boundaries coincide.

## Recoveries supported by independent full-ID evidence

34 grant rows qualify for explicit, reproducible identity repair. Every repair requires all of the following:

1. The original grant workbook actually has a blank OPEID at the recorded row; its bytes and raw descriptors match the reviewed ledger.
2. Another FSA program report for the **same award year** prints a full OPEID for the same named institution and state. The ledger records that report's URL, hash, sheet, Excel row and ZIP.
3. The annual official IPEDS directory has exactly one record for that full OPEID, with compatible institution and location evidence. The precise directory member, hash and UNITID are recorded as corroboration.
4. No other grant row already carries the proposed full OPEID in that award year. The repair restores the original source measures once; it neither copies parent aid nor allocates aid among campuses.

| Published institution rows | Award-year starts | Rows | Pell dollars restored | Pell recipient counts restored |
| --- | --- | ---: | ---: | ---: |
| Pittsburgh's Bradford, Greensburg, Johnstown and Titusville campuses | 1999–2004 | 24 | $27,001,505.09 | 12,681 |
| NEI College of Technology | 1999–2003 | 5 | $1,862,121.44 | 1,122 |
| Southwest Kansas Technical School | 2002–2005 | 4 | $763,018.05 | 300 |
| Butera School of Art | 2009 | 1 | $22,050.00 | 5 |
| **Total** | | **34** | **$29,648,694.58** | **14,108** |

The row-level evidence is more authoritative than a current name search. Pittsburgh's branch OPEIDs in HD2004 are `00338000`–`00338300`; HD2005 changes them to locations under `003379`. The same-year FFEL reports explicitly identify the older full IDs for the repaired observations. Those historically bounded repairs do not authorize carrying either version across years. In the grant workbooks the Pittsburgh main-campus row is separately identified as `00337900`; it is not substituted for the named branch rows.

NEI's 2003 record uses `00735300` but HD2003 names the NEI Center at Dunwoody and carries merger evidence. Dunwoody's own history confirms the 2003 merger. Its winter 2004 newsletter dates the opening of the new NEI Center to January 5, 2004. The repaired source identity therefore retains the merger/scope limitation; it does not establish institutional continuity for a regression. [Dunwoody history](https://dunwoody.edu/about/about-us/history/), [winter 2004 institutional newsletter](https://www.dunwoody.edu/pdfs/TheCompass_2004_Winter.pdf).

Southwest Kansas's same-year Campus-Based full ID and annual HD agree on the institution and state, but ZIP5 varies between `67901` and `67905` in some records. The grant workbooks have no ZIP. The evidence resolves the full source ID; it does not silently overwrite address disagreements.

All 34 repaired keys already occur in another program family in the master. Thus this repair increases grant coverage, **not the count of FSA institution-year keys**. Recipient sums in this table count published program observations across years; they are not a unique-person count.

## Cases still lacking defensible full-ID recovery

53 rows retain unresolved **FSA OPEIDs**: 32 grants and 21 Campus-Based rows. The remaining grant rows contain $160,098,344.80 in Pell disbursements, $5,834,476.12 in ACG disbursements and $3,796,378.75 in SMART disbursements. Their measures stay in the source quarantine rather than becoming zero or being silently lost. Sixteen of these grant rows now have independently verified **component-level UNITID identities**, described below, and can also appear in an explicitly separate supplement without an invented OPEID. All nine Campus-Based measures are observed numeric zero on each of the 21 unresolved Campus-Based rows.

| Cases | Rows | Evidence reviewed and reason not to assign |
| --- | ---: | --- |
| Foothills Technical Institute | 4 | Annual HD name/state and candidate `00531900` are available, but no same-year other-program full-ID corroboration was found. A later successor cannot supply the historical reporting ID. |
| Quapaw Technical Institute | 4 | Annual HD candidate `02120500` conflicts with the assumption that its FAFSA school code can be padded: the official 2001–02 FAFSA directory uses `010848`. The two identifier systems must remain distinct. |
| Louisiana Technical College–Sowela | 5 | HD changes from `00546700` in 1999/2000 to `00548836` in 2001/2002. A name match cannot select a grant reporting identity across that transition. |
| Herzing College, Minnesota | 3 | Each workbook already contains another identified Herzing row (`01101700`) with different Pell amounts. The blank row has no ZIP. Assigning the existing ID would collapse or duplicate distinct published rows. |
| Six Louisiana Technical College campuses in AY2009–10 | 6 | The selected report and its underlying COD query and Schools worksheet all leave OPEID blank. HD2009 still reports older `005488xx` locations while FSA2009 uses reorganized regional roots. Candidate campuses are recorded, but neither the old nor new ID is established for the blank observation. |
| Ten University of Puerto Rico campuses in AY2009–10 | 10 | The original report, COD query and Schools worksheet all omit the full IDs. Several rows share the central administration ZIP. HD2009 uses older `003942xx` locations while FSA2009 already identifies Mayaguez as `00394400`; Campus-Based and FFEL still report central `00394200`. This is a concrete program/year scope conflict. |
| Zero-only Campus-Based rows | 21 | Same-year eligibility and reporting identity are unverified. Several names only enter annual HD later; two zero-ID Yeshiva Machzikei Hadath entries may duplicate already identified `01302600` rows in the same workbook. Name correction or backdating would change institution counts without sufficient evidence. |

Foothills merged with Arkansas State University–Beebe effective July 1, 2003. Quapaw merged with Garland County Community College into National Park Community College effective July 1, 2003. These documented reorganizations help explain why a current institution lookup is unsafe; they do not prove why a historical FSA ID cell is blank. [ASU-Beebe history](https://www.asub.edu/mission-and-history/), [National Park College history](https://np.edu/about/history).

Sowela's official institutional history dates its change to a technical community college to July 1, 2003. That validates a substantive historical boundary change, but the grant record's precise identifier still requires independent evidence. [Sowela fact book, institutional history](https://www.sowela.edu/wp-content/uploads/fact-book-15-16.pdf).

The federal school-code distinction is directly observable, not hypothetical. The Department of Education's **Federal School Code List, 2001–2002** lists Quapaw as `010848` (printed page 6), whereas annual HD lists full OPEID `02120500`. Current Pitt admissions materials give FAFSA `008815` for all campuses. None of these FAFSA values is mechanically converted into a historical full OPEID. [Official archived 2001–02 list](https://files.eric.ed.gov/fulltext/ED446591.pdf), [Pitt's institutional FAFSA guidance](https://www.upb.pitt.edu/admissions-aid/financial-aid).

## Documentation and source review coverage

The review used all 87 original quarantine records; the relevant selected grant, Campus-Based, Direct Loan and FFEL row ledgers; raw workbook sheets at every approved source/corroborating Excel row; annual official HD directories covering the affected years; and annual identity histories through 2024 for unresolved Campus-Based names. For the 2009 grant blanks it also inspected the non-selected **Actual Q40910 Query** and **Schools** worksheets, and the other cached 2009 quarterly grant workbooks. Their hidden/source tables do not repair the missing OPEIDs. The ledger stores the underlying COD system school IDs as evidence of this check, **not as substitutes for OPEIDs**. Official FSA–NCES crosswalk workbooks and their Variable Labels and Value Labels & Notes were additionally reviewed for 2000–2004 and 2009–2010; the exact CW2009 records used for the component supplement are preserved in `unitid_evidence_json`.

This review does not equate a source row with an IPEDS institution count. The repaired rows preserve the FSA observation unit. Exact ID matches, historical alias/crosswalk matches, parent/child groups, geography and IPEDS universe eligibility must be summarized separately. Expanding the count by inventing IDs for zero rows or copying a parent amount to its children would increase apparent coverage while reducing research validity.

## Verified grant-component UNITIDs with unresolved OPEIDs

The official FSA–NCES crosswalk in the [College Scorecard archive](https://collegescorecard.ed.gov/data/) supplies a second, carefully bounded recovery level. All ten UPR and six Louisiana grant locations in AY2009–10 have an exact PEPS location-name match in CW2009 (apart from the documented La Montaña character-encoding difference), `Source=1`, one primary UNITID and no `AddMatch`. The corresponding annual HD agrees on the UNITID. Each campus also has a separately identified AY2008–09 FSA grant row with the same published location name and the candidate historical OPEID. All UPR ZIPs agree after preserving leading zeroes; Louisiana contact ZIPs change and are retained as reporting-address differences.

No identified AY2009–10 grant row maps to any of these sixteen UNITIDs through either CW2009's primary or additional matches. The ledger records that collision check, the exact crosswalk Excel row/member/hash, the prior FSA workbook row/hash, and the annual HD evidence. This establishes the identity of the **published grant component** without assigning a full OPEID to the blank source cell. It supports a separate UNITID supplement, with `opeid8` null and `unitid_resolution_status=verified_component_identity_opeid_unresolved`. The sixteen rows contain **$151,082,578.97 Pell, $5,834,476.12 ACG and $3,796,378.75 SMART disbursements**. It does not certify that centralized Campus-Based/loan amounts belong exclusively to these campuses.

CW2009 records UPR's ten old-to-new OPEID changes on July 27, 2010. That explains a real identifier transition, but the selected FSA workbook was refreshed in April 2012. Its names/IDs need not be a frozen July 2009 directory. Consequently the old OPEID is evidence, not an imputed source value. CW2000 also contains a Searcy relationship established from later years, although Foothills' institutional merger occurred in 2003; `Source=3` is explicitly labeled a relationship continued from other years. A crosswalk filename alone therefore does not establish the effective date of a PEPS name, eligibility status or OPEID. These distinctions are required when using the supplemental identities.

After the 34 full-ID recoveries and the sixteen separately verified component identities, sixteen grant rows containing **$9,015,765.83 Pell disbursements** and 21 zero-only Campus-Based rows still lack an approved usable source identity. The full original 87-row ledger remains available; recovery changes neither the original data nor the audit trail.
