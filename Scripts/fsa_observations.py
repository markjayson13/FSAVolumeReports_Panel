"""Loss-aware source parsing. IDs are identifiers; unknown/suppressed values are not zero."""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

DESCRIPTORS = {"opeid8", "school", "state", "zip_code", "school_type"}
OBSERVED_STATUSES = {"observed", "observed_zero"}


def text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def normalize_full_opeid(value: object) -> str | None:
    """Normalize a FULL eight-digit OPEID, including numeric Excel storage.

    A six-character input is never assumed to be an OPEID6 root. Reject decorated,
    fractional, negative, overlong and scientific-notation strings rather than
    silently stripping or truncating significant characters.
    """
    token = text(value)
    if not re.fullmatch(r"\d{1,8}(?:\.0+)?", token):
        return None
    digits = token.split(".")[0]
    if int(digits) == 0:
        return None
    return digits.zfill(8)


def normalize_root_opeid(value: object) -> str | None:
    """Explicit parser for fields documented as OPEID6. Never used on full IDs."""
    token = text(value)
    if not re.fullmatch(r"\d{1,6}(?:\.0+)?", token):
        return None
    digits = token.split(".")[0]
    return digits.zfill(6) if int(digits) else None


def is_count_measure(measure: str) -> bool:
    return measure.endswith("recipients") or measure.endswith("_n")


def parse_measure(series: pd.Series, measure: str) -> pd.DataFrame:
    """Preserve values, currency cents, raw exceptional tokens and bounded suppression."""
    raw = series.map(text).astype("string")
    cleaned = raw.str.replace(",", "", regex=False).str.replace("$", "", regex=False).str.strip()
    cleaned = cleaned.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    number_pattern = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
    numeric_token = cleaned.str.fullmatch(number_pattern).fillna(False)
    values = pd.to_numeric(cleaned.where(numeric_token), errors="coerce").astype("Float64")
    status = pd.Series("invalid_numeric", index=series.index, dtype="string")
    status.loc[numeric_token & values.notna()] = "observed"
    status.loc[values.eq(0).fillna(False)] = "observed_zero"
    blank = raw.str.lower().isin(["", "nan", "none", "null", "<na>"])
    status.loc[blank] = "source_blank"
    status.loc[cleaned.isin(["-", "—", "–", ".", "N/A", "n/a", "NA"])] = "source_symbol"
    status.loc[raw.str.contains(r"privacy|redact|suppress", case=False, regex=True, na=False)] = "suppressed"
    less_than_10 = cleaned.str.fullmatch(r"<\s*10").fillna(False)
    status.loc[less_than_10] = "suppressed_lt10"
    if is_count_measure(measure):
        fractional = values.notna() & values.mod(1).ne(0).fillna(False)
        negative = values.lt(0).fillna(False)
        status.loc[fractional] = "invalid_fractional_count"
        status.loc[negative] = "invalid_negative_count"
        values = values.mask(fractional | negative).astype("Int64")
    values = values.where(status.isin(OBSERVED_STATUSES))
    lower = values.astype("Float64").copy()
    upper = values.astype("Float64").copy()
    if is_count_measure(measure):
        lower.loc[less_than_10] = 0
        upper.loc[less_than_10] = 9
    return pd.DataFrame({"value": values, "status": status,
                         "raw_token": raw.where(~status.isin(OBSERVED_STATUSES), pd.NA),
                         "lower_bound": lower, "upper_bound": upper})


def source_row_classes(mapped: pd.DataFrame, resolved_ids: pd.Series | None = None) -> pd.Series:
    ids = (mapped.get("opeid8", pd.Series("", index=mapped.index)).map(normalize_full_opeid)
           if resolved_ids is None else resolved_ids)
    school = mapped.get("school", pd.Series("", index=mapped.index)).map(text)
    rawid = mapped.get("opeid8", pd.Series("", index=mapped.index)).map(text)
    total = (school.str.fullmatch(r"(?i)(?:grand\s+)?totals?\s*:?", na=False)
             | rawid.str.fullmatch(r"(?i)(?:grand\s+)?totals?\s*:?", na=False))
    kind = pd.Series("noninstitution", index=mapped.index, dtype="string")
    kind.loc[school.ne("")] = "quarantined_institution"
    kind.loc[ids.notna()] = "accepted_institution"
    kind.loc[total] = "reported_total"
    # Some early grant sheets end in an unlabeled row of numeric constants.
    # Preserve it as a candidate control, never as a published TOTAL or a
    # silently rejected institution. An equivalent mid-table row is ambiguous.
    numeric = pd.Series(False, index=mapped.index)
    for column in mapped.columns:
        if column in DESCRIPTORS:
            continue
        token = mapped[column].map(text).str.replace(",", "", regex=False).str.replace("$", "", regex=False).str.strip()
        token = token.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
        numeric |= token.str.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)").fillna(False)
    unidentified = kind.eq("noninstitution") & numeric
    kind.loc[unidentified] = "ambiguous_numeric_row"
    descriptors_blank = pd.Series(True, index=mapped.index)
    for descriptor in DESCRIPTORS:
        if descriptor in mapped:
            descriptors_blank &= mapped[descriptor].map(text).eq("")
    if numeric.any() and not total.any():
        positions = pd.Series(range(len(mapped)), index=mapped.index)
        final_numeric = positions.eq(positions.loc[numeric].max())
        candidate = unidentified & descriptors_blank & final_numeric
        kind.loc[candidate] = "unlabeled_numeric_summary_candidate"
    return kind


def audit_source_observations(mapped: pd.DataFrame, entry: dict, excel_rows: list[int], *,
                              resolved_ids: pd.Series | None = None,
                              resolution_ids: pd.Series | None = None) -> dict[str, pd.DataFrame]:
    """Account for every raw row and every monetary/count measure before any merge."""
    classification = source_row_classes(mapped, resolved_ids)
    accepted = classification.eq("accepted_institution")
    quarantined = classification.eq("quarantined_institution")
    totals = classification.eq("reported_total")
    candidates = classification.eq("unlabeled_numeric_summary_candidate")
    ambiguous = classification.eq("ambiguous_numeric_row")
    base = {"family": entry["family"], "award_year": entry["award_year"], "filename": entry["filename"]}
    row_ledger = mapped.copy().rename(columns={"opeid8": "raw_opeid"})
    row_ledger.insert(0, "source_excel_row", excel_rows)
    row_ledger.insert(0, "row_class", classification)
    for key, value in reversed(list(base.items())):
        row_ledger.insert(0, key, value)
    row_ledger["normalized_opeid8"] = (mapped["opeid8"].map(normalize_full_opeid).astype("string")
                                        if resolved_ids is None else resolved_ids)
    row_ledger["source_identity_resolution"] = (pd.Series(pd.NA, index=mapped.index, dtype="string")
                                                if resolution_ids is None else resolution_ids)
    row_ledger["reason"] = classification.map({"accepted_institution": "valid_full_opeid",
        "quarantined_institution": "missing_or_invalid_full_opeid", "reported_total": "summary_not_institution",
        "unlabeled_numeric_summary_candidate": "final_numeric_row_all_descriptors_blank_not_a_labeled_total",
        "ambiguous_numeric_row": "numeric_values_without_identifiable_institution_or_explicit_summary_require_review",
        "noninstitution": "blank_or_footnote"})
    row_ledger.loc[row_ledger.source_identity_resolution.notna(), "reason"] = "full_opeid_recovered_from_corroborated_contemporaneous_sources"
    reconciliation = []
    token_counts = []
    measures = [c for c in mapped if c not in DESCRIPTORS]
    for measure in measures:
        parsed = parse_measure(mapped[measure], measure)
        value = parsed.value
        known_total = float(value[accepted | quarantined].sum())
        reported = value[totals].dropna()
        # Multiple totals cannot safely be added: preserve all and report ambiguity.
        reported_total = float(reported.iloc[0]) if len(reported) == 1 else None
        incomplete = int((~parsed.status.isin(OBSERVED_STATUSES) & (accepted | quarantined)).sum())
        residual = None if reported_total is None else reported_total - known_total
        lower_total = None
        upper_total = None
        impossible_count_total = False
        if is_count_measure(measure):
            institution_bounds = parsed.loc[accepted | quarantined, ["lower_bound", "upper_bound"]]
            # Counts are nonnegative. Unknown counts contribute a lower bound of
            # zero, but cannot contribute a finite upper bound. Suppressed <10
            # counts contribute their documented interval [0, 9].
            lower_total = float(institution_bounds.lower_bound.fillna(0).sum())
            if institution_bounds.upper_bound.notna().all():
                upper_total = float(institution_bounds.upper_bound.sum())
            if reported_total is not None:
                impossible_count_total = reported_total < lower_total - .011 or (
                    upper_total is not None and reported_total > upper_total + .011)
        result = ("not_reported" if not len(reported) else "multiple_totals" if len(reported) > 1
                  else "mismatch_count_bounds" if impossible_count_total
                  else "incomplete_source_cells" if incomplete else "pass" if abs(residual) <= .011 else "mismatch")
        candidate_values = value[candidates].dropna()
        candidate_value = float(candidate_values.iloc[0]) if len(candidate_values) == 1 else None
        candidate_residual = None if candidate_value is None else candidate_value - known_total
        candidate_result = "no_candidate"
        if candidates.any():
            if ambiguous.any():
                candidate_result = "candidate_with_ambiguous_numeric_rows"
            elif len(candidate_values) != 1:
                candidate_result = "candidate_measure_unobserved_or_ambiguous"
            elif is_count_measure(measure) and (candidate_value < lower_total - .011 or (
                    upper_total is not None and candidate_value > upper_total + .011)):
                candidate_result = "mismatch_candidate_count_bounds"
            elif incomplete:
                candidate_result = "candidate_incomplete_source_cells"
            elif abs(candidate_residual) <= .011:
                candidate_result = "candidate_matches_known_sum"
            else:
                candidate_result = "mismatch_candidate_complete"
            # Keep candidate controls distinct from labeled reported totals in
            # both fields and status. A candidate match does not establish its
            # official meaning, nor convert missing source values to zero.
            if not totals.any():
                result = candidate_result
        reconciliation.append({**base, "measure": measure, "accepted_known_sum": float(value[accepted].sum()),
            "quarantined_known_sum": float(value[quarantined].sum()), "institution_known_sum": known_total,
            "reported_total": reported_total, "reported_total_count": len(reported), "residual": residual,
            "institution_count_lower_bound": lower_total, "institution_count_upper_bound": upper_total,
            "summary_candidate_value": candidate_value, "summary_candidate_count": int(candidates.sum()),
            "summary_candidate_excel_rows": "|".join(str(r) for r in row_ledger.loc[candidates, "source_excel_row"]),
            "summary_candidate_residual": candidate_residual, "summary_candidate_status": candidate_result,
            "ambiguous_numeric_rows": int(ambiguous.sum()),
            "nonobserved_institution_cells": incomplete, "reconciliation_status": result})
        counts = parsed.loc[accepted | quarantined | totals | candidates | ambiguous].groupby(["status", "raw_token"], dropna=False).size()
        for (status, raw_token), count in counts.items():
            token_counts.append({**base, "measure": measure, "status": status, "raw_token": raw_token, "cells": int(count)})
    return {"row_ledger": row_ledger, "quarantine": row_ledger[quarantined].copy(),
            "reconciliation": pd.DataFrame(reconciliation), "tokens": pd.DataFrame(token_counts)}


def write_family_audits(root: Path, family: str, audits: list[dict[str, pd.DataFrame]]) -> None:
    out = root / "Checks" / "observation_qc"
    out.mkdir(parents=True, exist_ok=True)
    for kind in ("row_ledger", "quarantine", "reconciliation", "tokens"):
        frames = [audit[kind] for audit in audits]
        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        combined.to_parquet(out / f"{family}_{kind}.parquet", index=False)
        if kind != "row_ledger":
            combined.to_csv(out / f"{family}_{kind}.csv", index=False)


def complete_source_statuses(panel: pd.DataFrame, prefix: str, availability: dict[str, set[str]]) -> pd.DataFrame:
    """Distinguish absent fields in a report from a missing institution observation."""
    present_col = prefix + "source_record_present"
    present = panel.get(present_col, pd.Series(False, index=panel.index)).fillna(False).astype(bool)
    panel[present_col] = present
    for column, years in availability.items():
        status_col = column + "__status"
        if status_col not in panel:
            panel[status_col] = pd.Series(pd.NA, index=panel.index, dtype="string")
        missing = panel[status_col].isna()
        available = panel.award_year.astype(str).isin(years)
        panel.loc[missing & ~available, status_col] = "unavailable_in_schema"
        panel.loc[missing & available & ~present, status_col] = "absent_source_record"
        panel.loc[missing & available & present, status_col] = "source_blank"
    return panel
