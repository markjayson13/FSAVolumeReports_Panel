"""Research metadata and conservation checks, separate from permissive shape-only QA."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pandas as pd

from fsa_observations import normalize_full_opeid, is_count_measure, OBSERVED_STATUSES

SOURCE_PREFIXES = {"grants": "grant__", "campus_based": "campus__",
                   "direct_loans": "loan_direct__", "ffel": "loan_ffel__"}
KEYS = ["opeid8", "award_year"]
DESCRIPTORS = ("school", "state", "zip_code", "school_type")


def apply_descriptor_overrides(panel: pd.DataFrame, path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    fields = ["opeid8", "award_year", "descriptor", "value", "evidence_url", "reviewed_by", "reviewed_at"]
    applied = []
    if not path.exists():
        return panel, pd.DataFrame(columns=fields + ["previous_value"])
    overrides = pd.read_csv(path, dtype=str).fillna("")
    if overrides.empty:
        return panel, pd.DataFrame(columns=fields + ["previous_value"])
    if set(fields) - set(overrides):
        raise ValueError("Descriptor override ledger is missing required evidence/reviewer fields")
    if overrides.duplicated(KEYS + ["descriptor"]).any():
        raise ValueError("Duplicate descriptor overrides")
    panel = panel.copy()
    for row in overrides.to_dict("records"):
        if any(not row[f].strip() for f in fields) or row["descriptor"] not in DESCRIPTORS:
            raise ValueError(f"Incomplete or unsupported descriptor override: {row}")
        if normalize_full_opeid(row["opeid8"]) != row["opeid8"]:
            raise ValueError("Overrides must use validated full eight-digit OPEID")
        mask = panel.opeid8.eq(row["opeid8"]) & panel.award_year.eq(row["award_year"])
        if mask.sum() != 1:
            raise ValueError(f"Override target must exist exactly once: {row['opeid8']} {row['award_year']}")
        descriptor = row["descriptor"]
        applied.append({**row, "previous_value": panel.loc[mask, descriptor].iloc[0]})
        panel.loc[mask, descriptor] = row["value"]
        panel.loc[mask, descriptor + "__review_required"] = False
    return panel, pd.DataFrame(applied, columns=fields + ["previous_value"])


def column_role(column: str) -> str:
    if column in {"opeid8", "opeid6", "award_year", "award_year_start", "award_year_end", "UNITID", "unitid"}:
        return "identifier_or_time"
    if column in DESCRIPTORS or any(column.endswith("__" + d) for d in DESCRIPTORS):
        return "descriptor"
    if column.endswith("__status") or column.endswith("__review_required") or column == "descriptor_review_required":
        return "quality_status"
    if column.endswith("__raw_token") or "source_" in column or column.endswith(("raw_opeid", "raw_zip_code")):
        return "provenance"
    if any(column.endswith("__" + suffix) for suffix in ("lower_bound", "upper_bound", "observed_partial_sum", "unique_lower_bound", "unique_upper_bound")) or "_unique_recipient_" in column:
        return "bound_or_partial_measure"
    if "scope" in column:
        return "reporting_scope"
    return "measure" if "__" in column else "metadata"


def base_measure(column: str) -> str:
    for suffix in ("__status", "__raw_token", "__lower_bound", "__upper_bound", "__observed_partial_sum",
                   "__unique_lower_bound", "__unique_upper_bound"):
        if column.endswith(suffix):
            return column[:-len(suffix)]
    return column


def build_research_dictionary(panel: pd.DataFrame, source_dictionary: pd.DataFrame, root: Path) -> pd.DataFrame:
    from fsa_policy import metadata_for_measure
    from fsa_loan_harmonization import derived_metadata
    rows = []
    dense = []
    selected = pd.read_csv(root / "Checks/download_qc/selected_panel_files.csv", dtype=str)
    years = sorted(panel.award_year.unique())
    year_indexes = panel.groupby("award_year").groups
    schemas = {}
    for family in SOURCE_PREFIXES:
        p = root / "Checks/observation_qc" / f"{family}_schema_availability.csv"
        if p.exists():
            schemas[family] = pd.read_csv(p, dtype=str)
    for column in panel:
        role = column_role(column)
        base = base_measure(column)
        family = next((f for f, prefix in SOURCE_PREFIXES.items() if base.startswith(prefix)), "derived")
        canonical = base.removeprefix(SOURCE_PREFIXES.get(family, ""))
        source_rows = source_dictionary.loc[
            source_dictionary.component_family.eq(family) & source_dictionary.canonical_column.eq(canonical)
        ] if family != "derived" else pd.DataFrame()
        metadata = {**metadata_for_measure(base), **(derived_metadata(column) or {})} if role in {"measure", "bound_or_partial_measure", "quality_status", "provenance", "reporting_scope"} else {}
        # Keep unknowns explicit, and always enumerate every output column exactly once.
        entry = {"panel_column": column, "column_role": role, "component_family": family,
                 "dtype": str(panel[column].dtype), "canonical_column": canonical,
                 "units": ("count" if is_count_measure(base) or "recipient_count" in base else "nominal_usd") if role in {"measure", "bound_or_partial_measure"} else "not_applicable",
                 "source_mappings_json": json.dumps(source_rows.fillna("").to_dict("records")),
                 **metadata}
        entry["units"] = metadata.get("unit", metadata.get("units", entry["units"]))
        if role == "provenance":
            entry["definition"] = "Original source token, workbook, sheet, Excel row or report/record availability; not an aid measure."
        if column.endswith("source_identity_resolution"):
            entry["definition"] = "Evidence-ledger resolution ID for a recovered full OPEID. Original raw_opeid remains unchanged; recovery is bound to source digest, sheet, Excel row, original descriptors and contemporaneous independent FSA/IPEDS evidence. Missing means no OPEID recovery applied."
        if column.endswith("__status") and family != "derived":
            entry["definition"] = "Value status: observed, observed_zero, source_blank, source_symbol, suppressed_lt10, suppressed, unavailable_in_schema, absent_source_record, report_not_available. Invalid tokens fail acceptance."
        if column.endswith("__lower_bound") or column.endswith("__upper_bound"):
            entry["definition"] = "Bound equals an observed value; suppressed count <10 has bounds 0 and 9; otherwise unknown."
        rows.append({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list, tuple)) else v for k, v in entry.items()})
        if role != "measure":
            continue
        schema = schemas.get(family, pd.DataFrame(columns=["column", "award_year"]))
        for year in years:
            indexes = year_indexes[year]
            source_exists = bool(((selected.family == family) & (selected.award_year == year)).any()) if family != "derived" else None
            header_exists = bool(((schema.column == column) & (schema.award_year == year)).any()) if family != "derived" else None
            statuses = panel.loc[indexes, column + "__status"].value_counts().to_dict() if column + "__status" in panel else {}
            dense.append({"panel_column": column, "award_year": year, "component_family": family,
                          "source_report_available": source_exists, "source_header_available": header_exists,
                          "observed_value_count": int(panel.loc[indexes, column].notna().sum()),
                          "status_counts_json": json.dumps(statuses, sort_keys=True)})
    pd.DataFrame(dense).to_csv(root / "Dictionary/variable_year_availability.csv", index=False)
    return pd.DataFrame(rows)


def _cell_equality(actual: pd.Series, expected: pd.Series, *, numeric: bool) -> pd.Series:
    actual, expected = actual.reset_index(drop=True), expected.reset_index(drop=True)
    both_missing = actual.isna() & expected.isna()
    if numeric:
        a = pd.to_numeric(actual, errors="coerce")
        e = pd.to_numeric(expected, errors="coerce")
        return (both_missing | (a.notna() & e.notna() & a.sub(e).abs().le(.00001))).fillna(False)
    return (both_missing | actual.astype("string").eq(expected.astype("string"))).fillna(False)


def audit_derived_loan_conservation(panel: pd.DataFrame) -> pd.DataFrame:
    """Recompute derived columns exclusively from preserved raw lending channels.

    The historical semantics have independent regression tests. This release
    check additionally catches corrupted, stale, omitted, or partially rebuilt
    derived outputs, including partial sums, bounds and completeness statuses.
    """
    from fsa_loan_harmonization import harmonize_loan_panel, consolidate_loan_programs
    source_cols = [c for c in panel if c.startswith(("loan_direct__", "loan_ffel__"))]
    key_cols = [c for c in (*KEYS, "award_year_start", "award_year_end", "opeid6") if c in panel]
    present = pd.Series(False, index=panel.index)
    for prefix in ("loan_direct__", "loan_ffel__"):
        present_col = prefix + "source_record_present"
        if present_col in panel:
            present |= panel[present_col].fillna(False).astype(bool)
        else:
            cols = [c for c in source_cols if c.startswith(prefix) and c.endswith("_recipients")]
            if cols:
                present |= panel[cols].notna().any(axis=1)
    source = panel.loc[present, key_cols + source_cols].copy()
    expected, _ = harmonize_loan_panel(source)
    expected, _ = consolidate_loan_programs(expected)
    expected = expected.reindex(panel.index)
    derived_cols = [c for c in expected if c not in key_cols + source_cols]
    rows = []
    for column in derived_cols:
        target = expected[column]
        if column.endswith("__status"):
            target = target.fillna("absent_source_record")
        elif column == "loan__program_scope":
            target = target.fillna("no_loan_source_record")
        numeric = column_role(column) in {"measure", "bound_or_partial_measure"}
        equal = (_cell_equality(panel[column], target, numeric=numeric) if column in panel
                 else pd.Series(False, index=panel.index))
        rows.append({"column": column, "passed": bool(equal.all()), "differing_cells": int((~equal).sum()),
                     "missing_column": column not in panel})
    extra = [c for c in panel if c.startswith(("loan__", "loan_direct_harmonized__", "loan_ffel_harmonized__"))
             and c not in derived_cols]
    for column in extra:
        rows.append({"column": column, "passed": False, "differing_cells": len(panel), "missing_column": False})
    return pd.DataFrame(rows, columns=["column", "passed", "differing_cells", "missing_column"])


def audit_source_identity_conservation(ledger: pd.DataFrame, panel: pd.DataFrame, family: str,
                                       root: Path, schemas: pd.DataFrame, *, identity_ledger_path: Path | None = None) -> pd.DataFrame:
    """Re-derive accepted IDs from raw tokens plus the same evidence-only resolver.

    Re-normalizing a blank raw ID alone would erase an approved recovery. Trusting
    the saved normalized ID alone would permit an unsupported assignment. Check
    both the resolver result and its source-to-final provenance instead.
    """
    from fsa_identity_resolutions import resolve_source_identities, LEDGER
    from fsa_observations import source_row_classes
    registry_path = identity_ledger_path or LEDGER
    registry = pd.read_csv(registry_path, dtype=str, keep_default_na=False) if registry_path.exists() else pd.DataFrame()
    selected_path = root / "Checks/download_qc/selected_panel_files.csv"
    selected = pd.read_csv(selected_path, dtype=str).fillna("") if selected_path.exists() else pd.DataFrame()
    prefix = SOURCE_PREFIXES[family]
    provenance_columns = [prefix + suffix for suffix in ("raw_opeid", "source_identity_resolution") if prefix + suffix in panel]
    target = panel[KEYS + provenance_columns].set_index(KEYS)
    checks = []
    for (year, filename), source in ledger.groupby(["award_year", "filename"], sort=False):
        source = source.reset_index(drop=True)
        mapped = source.rename(columns={"raw_opeid": "opeid8"}).copy()
        # Classification must see raw mapped measures/descriptors, not audit metadata.
        measure_columns = schemas.loc[schemas.award_year.eq(year), "column"].str.removeprefix(prefix).tolist()
        mapped = mapped[[c for c in ["opeid8", *DESCRIPTORS, *measure_columns] if c in mapped]].copy()
        expected_ids = mapped.opeid8.map(normalize_full_opeid).astype("string")
        expected_refs = pd.Series(pd.NA, index=mapped.index, dtype="string")
        decisions = registry.loc[registry.family.eq(family) & registry.award_year.eq(year)
            & registry.filename.eq(filename) & registry.resolution_status.eq("approved")] if not registry.empty else pd.DataFrame()
        passed, details = True, []
        try:
            if not decisions.empty:
                entry = selected.loc[selected.family.eq(family) & selected.award_year.eq(year) & selected.filename.eq(filename)] if not selected.empty else pd.DataFrame()
                if len(entry) != 1:
                    raise ValueError("Recovered source identity requires exactly one selected source file")
                entry = entry.iloc[0].to_dict()
                actual_digest = hashlib.sha256(Path(entry["local_path"]).read_bytes()).hexdigest()
                if actual_digest != entry.get("sha256"):
                    raise ValueError("Recovered source file no longer matches selected SHA-256")
                sheet_rows = schemas.loc[schemas.award_year.eq(year)]
                if "filename" in sheet_rows:
                    sheet_rows = sheet_rows.loc[sheet_rows.filename.eq(filename)]
                sheets = sheet_rows["sheet"].dropna().unique() if "sheet" in sheet_rows else []
                if len(sheets) != 1:
                    raise ValueError("Recovered source identity requires one recorded source sheet")
                expected_ids, expected_refs = resolve_source_identities(mapped, entry,
                    source.source_excel_row.tolist(), str(sheets[0]), ledger_path=registry_path)
            id_equal = _cell_equality(source.normalized_opeid8, expected_ids, numeric=False)
            saved_refs = source.get("source_identity_resolution", pd.Series(pd.NA, index=source.index, dtype="string"))
            refs_equal = _cell_equality(saved_refs, expected_refs, numeric=False)
            expected_classes = source_row_classes(mapped, expected_ids)
            classes_equal = source.row_class.reset_index(drop=True).eq(expected_classes.reset_index(drop=True))
            passed = bool(id_equal.all() and refs_equal.all() and classes_equal.all())
            details.extend([f"id_mismatches={int((~id_equal).sum())}", f"resolution_mismatches={int((~refs_equal).sum())}",
                            f"classification_mismatches={int((~classes_equal).sum())}", f"verified_recoveries={int(expected_refs.notna().sum())}"])
            accepted = expected_classes.eq("accepted_institution")
            index = pd.MultiIndex.from_arrays([expected_ids.loc[accepted], source.loc[accepted, "award_year"]], names=KEYS)
            for suffix, expected in [("raw_opeid", source.loc[accepted, "raw_opeid"]),
                                     ("source_identity_resolution", expected_refs.loc[accepted])]:
                column = prefix + suffix
                if column not in target:
                    if expected_refs.notna().any():
                        passed = False
                        details.append("missing_final_provenance=" + column)
                    continue
                equal = _cell_equality(target[column].reindex(index), expected, numeric=False)
                if not equal.all():
                    passed = False
                    details.append(f"{suffix}_final_mismatches={int((~equal).sum())}")
        except (ValueError, KeyError, OSError) as exc:
            passed = False
            details.append(str(exc))
        checks.append({"check": f"{family}_{year}_{filename}_source_identity_evidence_conserved", "passed": passed,
                       "details": "; ".join(details)})
    return pd.DataFrame(checks, columns=["check", "passed", "details"])


def research_acceptance(root: Path, panel_path: Path) -> pd.DataFrame:
    """Checks that can actually fail on corrupt IDs, lost source values or dropped suppression."""
    panel = pd.read_parquet(panel_path)
    results = []
    def check(name, passed, details):
        results.append({"check": "research::" + name, "passed": bool(passed), "details": str(details)})
    check("valid_full_opeids", panel.opeid8.map(normalize_full_opeid).eq(panel.opeid8).all(), len(panel))
    check("root_id_consistency", panel.opeid6.eq(panel.opeid8.str[:6]).all(), len(panel))
    dictionary_path = root / "Dictionary/fsa_volume_panel_dictionary.parquet"
    if dictionary_path.exists():
        dictionary = pd.read_parquet(dictionary_path)
        missing = set(panel) - set(dictionary.panel_column)
        check("every_final_column_documented", not missing and not dictionary.panel_column.duplicated().any(), sorted(missing))
        measure_rows = dictionary.loc[dictionary.column_role.eq("measure")]
        undefined = measure_rows.loc[measure_rows.get("definition", pd.Series(index=measure_rows.index,dtype=str)).fillna("").eq(""), "panel_column"].tolist()
        check("all_measure_definitions_available", not undefined, undefined)
    else:
        check("every_final_column_documented", False, "dictionary missing")
    check("source_descriptors_and_review_flags_retained", "descriptor_review_required" in panel and "grant__school" in panel, "Master retains source evidence; unresolved reviews remain flagged")
    status_columns = [c for c in panel if c.endswith("__status")]
    missing_statuses = {c: int(panel[c].isna().sum()) for c in status_columns if panel[c].isna().any()}
    unreviewed = {c: int(panel[c].eq("schema_not_reviewed").sum()) for c in status_columns
                  if panel[c].eq("schema_not_reviewed").any()}
    check("every_value_status_populated", bool(status_columns) and not missing_statuses, missing_statuses)
    check("derived_source_schemas_reviewed", not unreviewed, unreviewed)
    manual_path = root / "Checks/panel_qc/final_descriptor_manual_review.csv"
    override_path = root / "Checks/panel_qc/descriptor_overrides_applied.csv"
    descriptor_errors = []
    if manual_path.exists() and override_path.exists():
        manual = pd.read_csv(manual_path, dtype=str).fillna("")
        overrides = pd.read_csv(override_path, dtype=str).fillna("")
        key_index = pd.MultiIndex.from_frame(panel[KEYS])
        for descriptor in DESCRIPTORS:
            flag = descriptor + "__review_required"
            pending = manual.loc[manual.descriptor.eq(descriptor), KEYS]
            resolved = overrides.loc[overrides.descriptor.eq(descriptor), KEYS]
            pending_index = pd.MultiIndex.from_frame(pending).difference(pd.MultiIndex.from_frame(resolved))
            expected_flag = pd.Series(key_index.isin(pending_index), index=panel.index)
            if flag not in panel or not panel[flag].fillna(False).eq(expected_flag).all():
                descriptor_errors.append(descriptor)
        flags = [d + "__review_required" for d in DESCRIPTORS]
        if set(flags).issubset(panel):
            if "descriptor_review_required" not in panel or not panel.descriptor_review_required.eq(panel[flags].any(axis=1)).all():
                descriptor_errors.append("aggregate_flag")
    else:
        descriptor_errors.append("missing_manual_or_applied_override_ledger")
    check("descriptor_review_flags_match_ledgers", not descriptor_errors, descriptor_errors)
    indexed = panel.set_index(KEYS).sort_index()
    source_checks = []
    for family, prefix in SOURCE_PREFIXES.items():
        schemas_path = root / "Checks/observation_qc" / f"{family}_schema_availability.csv"
        ledger_path = root / "Checks/observation_qc" / f"{family}_row_ledger.parquet"
        check(f"{family}_source_accounting_exists", schemas_path.exists() and ledger_path.exists(), family)
        if not schemas_path.exists() or not ledger_path.exists():
            continue
        schemas = pd.read_csv(schemas_path)
        ledger = pd.read_parquet(ledger_path)
        identity_checks = audit_source_identity_conservation(ledger, panel, family, root, schemas)
        for identity_check in identity_checks.to_dict("records"):
            check(identity_check["check"], identity_check["passed"], identity_check["details"])
        ambiguous_numeric_rows = ledger.loc[ledger.row_class.eq("ambiguous_numeric_row")]
        check(f"{family}_no_unresolved_anonymous_numeric_rows", ambiguous_numeric_rows.empty,
              ambiguous_numeric_rows[["filename", "source_excel_row"]].to_json(orient="records"))
        quarantine_path = root / "Checks/observation_qc" / f"{family}_quarantine.parquet"
        quarantine_equal = False
        if quarantine_path.exists():
            quarantine = pd.read_parquet(quarantine_path)
            expected_quarantine = ledger.loc[ledger.row_class.eq("quarantined_institution")].reset_index(drop=True)
            quarantine_equal = quarantine.reset_index(drop=True).equals(expected_quarantine)
        check(f"{family}_quarantine_ledger_preserved", quarantine_equal, str(quarantine_path))
        for year, group in ledger.groupby("award_year"):
            accepted = group.loc[group.row_class.eq("accepted_institution")]
            expected_ids = accepted.normalized_opeid8.tolist()
            actual = panel.loc[panel.award_year.eq(year) & panel[prefix + "source_record_present"].fillna(False)]
            check(f"{family}_{year}_source_rows_preserved", sorted(expected_ids) == sorted(actual.opeid8.tolist()),
                  f"accepted={len(expected_ids)} quarantined={int(group.row_class.eq('quarantined_institution').sum())}")
        from fsa_observations import parse_measure
        for column, schema in schemas.groupby("column"):
            canonical = column.removeprefix(prefix)
            source = ledger.loc[ledger.row_class.eq("accepted_institution") & ledger.award_year.isin(schema.award_year)].copy()
            parsed = parse_measure(source[canonical], canonical)
            source_index = pd.MultiIndex.from_arrays([source.normalized_opeid8, source.award_year], names=KEYS)
            required = [column] + [column + "__" + m for m in ("status", "raw_token", "lower_bound", "upper_bound")]
            missing_columns = [c for c in required if c not in indexed]
            if missing_columns:
                check(f"{column}_raw_to_final_conservation", False, f"Missing source value or metadata columns: {missing_columns}")
                continue
            actual = indexed[column].reindex(source_index).reset_index(drop=True)
            expected = parsed.value.reset_index(drop=True)
            numeric_equal = _cell_equality(actual, expected, numeric=True)
            statuses = indexed[column + "__status"].reindex(source_index).reset_index(drop=True)
            status_equal = _cell_equality(statuses, parsed.status, numeric=False)
            all_equal = numeric_equal & status_equal
            metadata_differences = {}
            for metadata in ("raw_token", "lower_bound", "upper_bound"):
                observed_metadata = indexed[column + "__" + metadata].reindex(source_index)
                equal = _cell_equality(observed_metadata, parsed[metadata], numeric=metadata != "raw_token")
                all_equal &= equal
                metadata_differences[metadata] = int((~equal).sum())
            passed = bool(all_equal.all())
            check(f"{column}_raw_to_final_conservation", passed,
                  f"cells={len(source)} differing={int((~all_equal).sum())}; metadata={metadata_differences}")
            source_checks.append({"column": column, "source_cells": len(source), "source_known_sum": float(expected.sum()),
                                  "final_known_sum": float(actual.sum()), "passed": passed})
        token_file = root / "Checks/observation_qc" / f"{family}_tokens.csv"
        tokens = pd.read_csv(token_file)
        invalid = tokens.status.astype(str).str.startswith("invalid")
        check(f"{family}_no_unclassified_numeric_tokens", not invalid.any(), tokens.loc[invalid].to_json(orient="records"))
        rec = pd.read_csv(root / "Checks/observation_qc" / f"{family}_reconciliation.csv")
        # Missing/suppressed cells and absent TOTAL rows are not claimed reconciled.
        failures = rec.reconciliation_status.astype(str).str.startswith("mismatch")
        check(f"{family}_complete_reported_totals_reconcile", not failures.any(),
              f"mismatches={int(failures.sum())}; other statuses={rec.reconciliation_status.value_counts().to_dict()}")
    out = root / "Checks/research_qc"
    out.mkdir(parents=True, exist_ok=True)
    loan_conservation = audit_derived_loan_conservation(panel)
    loan_failures = loan_conservation.loc[~loan_conservation.passed]
    check("derived_loan_conservation", not loan_conservation.empty and loan_failures.empty,
          f"columns={len(loan_conservation)}; failures={loan_failures.to_dict('records')}")
    loan_conservation.to_csv(out / "derived_loan_conservation.csv", index=False)
    pd.DataFrame(source_checks).to_csv(out / "raw_to_final_conservation.csv", index=False)
    pd.DataFrame(results).to_csv(out / "research_acceptance.csv", index=False)
    return pd.DataFrame(results)
