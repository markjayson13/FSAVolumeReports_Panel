"""Conservative, schema-aware loan measures; source columns are immutable.

The reviewed schema is award-year-start 1999--2024 (Direct), 1999--2009
(FFEL). See Documentation/loan_harmonization.md for scope and definitions.
"""
from __future__ import annotations

import re

import pandas as pd

METRICS = (
    "recipients", "loans_originated_n", "loans_originated_amt",
    "disbursements_n", "disbursements",
)
BASES = ("subsidized", "unsubsidized", "plus")
SCHEMA_VERSION = "fsa-loan-schema-2026-09-22-v1"


def _years(frame: pd.DataFrame) -> pd.Series:
    parsed = pd.to_numeric(frame["award_year"].astype("string").str[:4], errors="coerce").astype("Int64")
    if "award_year_start" in frame:
        return pd.to_numeric(frame["award_year_start"], errors="coerce").astype("Int64").combine_first(parsed)
    return parsed


def _empty(index: pd.Index, dtype: str = "Float64") -> pd.Series:
    return pd.Series(pd.NA, index=index, dtype=dtype)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return _empty(frame.index)
    return pd.to_numeric(frame[column], errors="raise").astype("Float64")


def _known(frame: pd.DataFrame, column: str) -> pd.Series:
    values = _numeric(frame, column)
    status_column = column + "__status"
    if status_column not in frame:
        return values.notna()
    status = frame[status_column].astype("string")
    return (values.notna() & (
        status.str.startswith("observed") | status.str.startswith("complete_")
    )).fillna(False)


def _cast(values: pd.Series, metric: str) -> pd.Series:
    values = values.astype("Float64")
    if metric == "recipients" or metric.endswith("_n"):
        invalid = values.notna() & ((values < 0) | (values % 1 != 0))
        if invalid.any():
            raise ValueError(f"Nonintegral or negative loan count in {metric}")
        return values.astype("Int64")
    # No rounding to whole dollars: raw cents are retained.
    return values


def _source_present(frame: pd.DataFrame, source: str) -> pd.Series:
    explicit = source + "__source_record_present"
    if explicit in frame:
        return frame[explicit].fillna(False).astype(bool)
    cols = [c for c in frame if c.startswith(source + "__") and "__" not in c[len(source) + 2:]]
    return frame[cols].notna().any(axis=1) if cols else pd.Series(False, index=frame.index)


def _components(source: str, base: str, year: int) -> tuple[str, ...] | None:
    """Explicit source-year schema, never inferred from a row's nonnull cells."""
    last_year = 2024 if source == "loan_direct" else 2009
    if not 1999 <= year <= last_year:
        return None
    if base == "plus":
        if year < 2005:
            return ("plus",)
        if year == 2005:
            # Generic PLUS here is Parent PLUS; Grad PLUS is a separate column.
            return ("plus", "grad_plus")
        return ("parent_plus", "grad_plus")
    if source == "loan_direct" and (
        (base == "subsidized" and year in (2010, 2011))
        or (base == "unsubsidized" and year >= 2010)
    ):
        return (base + "_undergraduate", base + "_graduate")
    return (base,)


def _summarize_components(frame: pd.DataFrame, columns: list[str], metric: str) -> dict[str, pd.Series]:
    pieces = pd.concat([_cast(_numeric(frame, c).where(_known(frame, c)), metric) for c in columns], axis=1)
    complete = pieces.notna().all(axis=1)
    partial = pieces.sum(axis=1, min_count=1).astype("Float64")
    status = pd.Series("no_observed_components", index=frame.index, dtype="string")
    status.loc[pieces.notna().any(axis=1)] = "incomplete_component_sum"
    status.loc[complete] = "complete_source_reported" if len(columns) == 1 else "complete_component_sum"
    result = {"value": _cast(partial.where(complete), metric), "partial": _cast(partial, metric), "status": status}
    if metric == "recipients":
        # Bounds describe the union of student recipients, not borrower accounts.
        # With unknown overlap, max(component counts) <= union <= sum(counts).
        lows, highs = [], []
        for c in columns:
            observed = _numeric(frame, c).where(_known(frame, c))
            low = observed.combine_first(_numeric(frame, c + "__lower_bound"))
            high = observed.combine_first(_numeric(frame, c + "__upper_bound"))
            for series in (low, high):
                _cast(series, "recipients")
            if ((low > high) & low.notna() & high.notna()).any():
                raise ValueError(f"Reversed recipient bounds for {c}")
            lows.append(low)
            highs.append(high)
        lower = pd.concat(lows, axis=1)
        upper = pd.concat(highs, axis=1)
        result["lower"] = _cast(lower.max(axis=1, skipna=True), metric)
        result["upper"] = _cast(upper.sum(axis=1, min_count=len(columns)), metric)
    return result


def _output_name(source: str, base: str, metric: str) -> str:
    suffix = "recipient_count_sum" if metric == "recipients" else metric
    return f"{source}__{base}_{suffix}"


def harmonize_loan_panel(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add source-specific harmonized measures without overwriting any source cell."""
    additions: dict[str, pd.Series] = {}
    summary = []
    years = _years(frame)
    for source in ("loan_direct", "loan_ffel"):
        present = _source_present(frame, source)
        for base in BASES:
            for metric in METRICS:
                # Avoid fabricating variables not supplied at all (small fixture or subset).
                candidates = [c for c in frame if c.startswith(source + "__") and c.endswith("_" + metric)
                              and (c.startswith(source + "__" + base + "_") or
                                   (base == "plus" and ("__parent_plus_" in c or "__grad_plus_" in c)))]
                if not candidates:
                    continue
                name = _output_name(source + "_harmonized", base, metric)
                value, partial = _empty(frame.index), _empty(frame.index)
                status = pd.Series("schema_not_reviewed", index=frame.index, dtype="string")
                lower, upper = _empty(frame.index), _empty(frame.index)
                for year in sorted(years.dropna().unique()):
                    cols = _components(source, base, int(year))
                    if cols is None:
                        continue
                    mask = years.eq(year).fillna(False)
                    source_cols = [f"{source}__{part}_{metric}" for part in cols]
                    result = _summarize_components(frame.loc[mask], source_cols, metric)
                    value.loc[mask] = result["value"]
                    partial.loc[mask] = result["partial"]
                    status.loc[mask] = result["status"]
                    if metric == "recipients":
                        lower.loc[mask], upper.loc[mask] = result["lower"], result["upper"]
                    summary.append({
                        "output_column": name, "award_year_start": int(year),
                        "source_columns": "|".join(source_cols), "schema_version": SCHEMA_VERSION,
                        "rows_complete": int(result["value"].notna().sum()),
                        "rows_partial": int((result["partial"].notna() & result["value"].isna()).sum()),
                        "observed_component_sum": (float(result["partial"].sum()) if result["partial"].notna().any() else None),
                    })
                status.loc[~present] = "absent_source_record"
                additions[name] = _cast(value.where(present), metric)
                additions[name + "__observed_partial_sum"] = _cast(partial.where(present), metric)
                additions[name + "__status"] = status
                if metric == "recipients":
                    additions[name.replace("recipient_count_sum", "unique_recipient_lower_bound")] = _cast(lower.where(present), metric)
                    additions[name.replace("recipient_count_sum", "unique_recipient_upper_bound")] = _cast(upper.where(present), metric)
    # Re-running is idempotent; no _x/_y variants and no changed source columns.
    panel = pd.concat([frame.drop(columns=list(additions), errors="ignore"), pd.DataFrame(additions)], axis=1)
    return panel, pd.DataFrame(summary)


def consolidate_loan_programs(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Combine channels within explicit scope; this never measures consolidation loans."""
    if not any(c.startswith("loan_direct_harmonized__") or c.startswith("loan_ffel_harmonized__") for c in frame):
        frame, _ = harmonize_loan_panel(frame)
    additions: dict[str, pd.Series] = {}
    summary = []
    years = _years(frame)
    both_scope = years.between(1999, 2009).fillna(False)
    direct_scope = years.between(2010, 2024).fillna(False)
    scope = pd.Series("schema_not_reviewed", index=frame.index, dtype="string")
    scope.loc[both_scope] = "direct_and_ffel"
    scope.loc[direct_scope] = "direct_only_available_report"
    additions["loan__program_scope"] = scope
    for descriptor in ("school", "state", "zip_code", "school_type"):
        value = _empty(frame.index, "string")
        for source in ("loan_direct", "loan_ffel"):
            col = f"{source}__{descriptor}"
            if col in frame:
                value = value.combine_first(frame[col].astype("string"))
        additions["loan__" + descriptor] = value
    for base in BASES:
        for metric in METRICS:
            direct = _output_name("loan_direct_harmonized", base, metric)
            ffel = _output_name("loan_ffel_harmonized", base, metric)
            if direct not in frame and ffel not in frame:
                continue
            name = _output_name("loan", base, metric)
            d, f = _numeric(frame, direct), _numeric(frame, ffel)
            exact = (d + f).where(both_scope)
            exact.loc[direct_scope] = d.loc[direct_scope]
            partials = pd.concat([_numeric(frame, direct + "__observed_partial_sum"),
                                  _numeric(frame, ffel + "__observed_partial_sum")], axis=1)
            partial = partials.sum(axis=1, min_count=1).where(both_scope)
            partial.loc[direct_scope] = partials.iloc[:, 0].loc[direct_scope]
            status = pd.Series("schema_not_reviewed", index=frame.index, dtype="string")
            status.loc[both_scope | direct_scope] = "no_observed_components"
            status.loc[partial.notna()] = "incomplete_component_sum"
            status.loc[exact.notna() & both_scope] = "complete_component_sum"
            status.loc[exact.notna() & direct_scope] = "complete_direct_only_scope"
            additions[name] = _cast(exact, metric)
            additions[name + "__observed_partial_sum"] = _cast(partial, metric)
            additions[name + "__status"] = status
            if metric == "recipients":
                lo_cols = [c.replace("recipient_count_sum", "unique_recipient_lower_bound") for c in (direct, ffel)]
                hi_cols = [c.replace("recipient_count_sum", "unique_recipient_upper_bound") for c in (direct, ffel)]
                lows = pd.concat([_numeric(frame, c) for c in lo_cols], axis=1)
                highs = pd.concat([_numeric(frame, c) for c in hi_cols], axis=1)
                lower = lows.max(axis=1, skipna=True).where(both_scope)
                upper = highs.sum(axis=1, min_count=2).where(both_scope)
                lower.loc[direct_scope] = lows.iloc[:, 0].loc[direct_scope]
                upper.loc[direct_scope] = highs.iloc[:, 0].loc[direct_scope]
                additions[name.replace("recipient_count_sum", "unique_recipient_lower_bound")] = _cast(lower, metric)
                additions[name.replace("recipient_count_sum", "unique_recipient_upper_bound")] = _cast(upper, metric)
            summary.append({
                "output_column": name, "rows_with_both_sources": int((d.notna() & f.notna()).sum()),
                "rows_complete": int(exact.notna().sum()),
                "rows_partial": int((partial.notna() & exact.isna()).sum()),
                "direct_nonnull": int(d.notna().sum()), "ffel_nonnull": int(f.notna().sum()),
                "rows_output_nonnull": int(exact.notna().sum()), "schema_version": SCHEMA_VERSION,
            })
    panel = pd.concat([frame.drop(columns=list(additions), errors="ignore"), pd.DataFrame(additions)], axis=1)
    return panel, pd.DataFrame(summary)


def derived_metadata(column: str) -> dict[str, str] | None:
    """Dictionary metadata for every column produced by this module."""
    prefixes = ("loan__", "loan_direct_harmonized__", "loan_ffel_harmonized__")
    prefix = next((p for p in prefixes if column.startswith(p)), None)
    if prefix is None:
        return None
    token = column[len(prefix):]
    base = re.split(r"__(?:status|observed_partial_sum)$", token)[0]
    scope = "Direct and FFEL through AY2009; Direct-only available report from AY2010" if prefix == "loan__" else prefix.split("__")[0].replace("_harmonized", "")
    caveat = "No missing or suppressed component is silently zero-filled. Scope follows loan__program_scope. Source-specific measures retained."
    unit = "USD nominal" if base.endswith(("_amt", "_disbursements")) else "count"
    definition = "Complete sum of the reviewed source-year component measures."
    formula = "Sum all required components only when each is observed; otherwise missing."
    if base.endswith("recipient_count_sum"):
        definition = "Sum of reported student recipient counts; not a deduplicated count of unique recipients or parent borrowers."
        caveat += " Students can occur in multiple loan types, levels, or lending channels."
    if base.endswith("unique_recipient_lower_bound"):
        definition, formula = "Lower bound on unique student recipients within the named loan category and reporting scope.", "Maximum of known component lower bounds (nonnegative counts)."
    if base.endswith("unique_recipient_upper_bound"):
        definition, formula = "Upper bound on unique student recipients within the named loan category and reporting scope.", "Sum of component upper bounds only if every required upper bound is known."
    if token.endswith("__observed_partial_sum"):
        definition, formula = "Sum of observed components, which may omit unknown or suppressed components; consult the corresponding status.", "Sum observed components; all-unobserved remains missing. Never an exact total unless status is complete."
    if token.endswith("__status"):
        unit, definition, formula = "category", "Completeness of the corresponding derived measure.", "complete_source_reported | complete_component_sum | complete_direct_only_scope | incomplete_component_sum | no_observed_components | absent_source_record | schema_not_reviewed"
    if token == "program_scope":
        unit, definition, formula = "category", "Available reporting universe used for combined loan measures, not proof of zero FFEL activity after 2010.", "AY1999--2009: direct_and_ffel; AY2010--2024: direct_only_available_report; otherwise schema_not_reviewed."
    if token in ("school", "state", "zip_code", "school_type"):
        unit, definition, formula = "text", "Loan institution descriptor; raw channel-specific descriptors remain available.", "First nonmissing Direct descriptor, then FFEL."
    return {"definition": definition, "formula": formula, "unit": unit, "caveat": caveat,
            "reporting_scope": scope, "source": "Documentation/loan_harmonization.md", "schema_version": SCHEMA_VERSION}
