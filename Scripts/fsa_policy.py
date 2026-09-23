"""Source-backed interpretation metadata; never modifies observed panel values.

Observed header years are evidence from a fixed selected inventory, not a promise
that every institution has a value and not program legal eligibility bounds.
"""
from __future__ import annotations

import csv
import hashlib
import json
from functools import lru_cache
from pathlib import Path

METADATA_DIR = Path(__file__).resolve().parents[1] / "Metadata"
REGISTRY_FILES = ("program_policy_events.csv", "measure_definitions.json", "source_schema_inventory.csv")


@lru_cache(maxsize=1)
def load_policy_registry() -> dict:
    return json.loads((METADATA_DIR / "measure_definitions.json").read_text())


@lru_cache(maxsize=1)
def load_policy_events() -> tuple[dict, ...]:
    with (METADATA_DIR / "program_policy_events.csv").open(newline="") as stream:
        return tuple(csv.DictReader(stream))


@lru_cache(maxsize=1)
def policy_registry_hash() -> str:
    """Hash names and exact bytes of all three interpretation inputs."""
    digest = hashlib.sha256()
    for name in REGISTRY_FILES:
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update((METADATA_DIR / name).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def metadata_for_measure(column: str) -> dict[str, str]:
    """Return scalar/JSON-text fields suitable for a CSV/Parquet dictionary row.

    Empty dict means unknown metadata, never an undocumented best guess. Derived
    aggregation formulas should be supplied by the module that computes them.
    The function accepts canonical names and grant__/campus__/loan_*__ names.
    """
    prefixes = {
        "grant__": "grants", "grants__": "grants", "campus__": "campus_based",
        "loan_direct__": "direct_loans", "loan_ffel__": "ffel", "loan__": "combined_loans",
        "loan_direct_harmonized__": "direct_loans", "loan_ffel_harmonized__": "ffel",
    }
    family = ""
    canonical = column
    for prefix, candidate in prefixes.items():
        if column.startswith(prefix):
            family, canonical = candidate, column[len(prefix):]
            break
    # Status fields do not inherit their parent's numeric unit or definition.
    if "__" in canonical:
        return {}
    is_recipient_sum = canonical.endswith(("_recipient_records", "_recipient_count_sum"))
    recipient_aliases = ("recipient_records", "recipient_count_sum", "unique_recipient_lower_bound", "unique_recipient_upper_bound")
    for alias in recipient_aliases:
        if canonical.endswith("_" + alias):
            canonical = canonical.removesuffix("_" + alias) + "_recipients"
            break
    measure = load_policy_registry()["measures"].get(canonical)
    if measure is None:
        return {}
    applicable_events = []
    for event in load_policy_events():
        if event["event_id"] not in measure["policy_event_ids"]:
            continue
        # Scope-limited delivery-channel event still contextualizes totals, but
        # never implies a direct-only measure is itself an FFEL observation.
        applicable_events.append(event)
    years = measure["observed_header_award_year_starts_by_family"]
    source_years = years.get(family, []) if family in prefixes.values() and family != "combined_loans" else years
    counting = measure["caveat"]
    definition = measure["definition"]
    unit = measure["unit"]
    if is_recipient_sum:
        unit = "recipient_records_not_unique_people"
        definition = "Arithmetic sum of source-specific recipient counts; overlap between groups is unknown."
        counting += " Recipient-record sums are not estimates of unique people."
    return {
        "program": measure["program"],
        "unit": unit,
        "definition": definition,
        "counting_caveat": counting,
        "currency": measure["currency"],
        "price_basis": measure["price_basis"],
        "aggregation_rule": (
            "Do not sum to unique recipients; retain source scope and channel."
            if canonical.endswith("_recipients")
            else "Sum only complete, nonoverlapping source components or verified disjoint reporting units; never turn missing components into zero."
        ),
        "observed_header_years_json": json.dumps(source_years, sort_keys=True),
        "policy_event_ids_json": json.dumps([event["event_id"] for event in applicable_events]),
        "policy_source_urls_json": json.dumps(sorted(
            {event["source_url"] for event in applicable_events}
            | {url for event in applicable_events for url in json.loads(event.get("supporting_source_urls_json", "[]"))}
        )),
        "policy_registry_sha256": policy_registry_hash(),
        "policy_reviewed_on": load_policy_registry()["reviewed_on"],
        "missing_value_rule": measure["missing_value_rule"],
        "metadata_status": "source_backed_with_explicit_caveats",
    }


def observed_header_years(family: str, canonical_column: str) -> tuple[int, ...]:
    """Exact observed years, not just min/max (which could hide gaps)."""
    measure = load_policy_registry()["measures"].get(canonical_column, {})
    return tuple(measure.get("observed_header_award_year_starts_by_family", {}).get(family, []))


def events_for_year(award_year_start: int, program: str | None = None) -> list[dict]:
    """Context events in force by year; does not classify an observed cell.

    First/last affected award years are coarse research annotations. Exact legal
    application may depend on first disbursement, credit-check or loan-period
    dates and individual exceptions, documented in each event.
    """
    found = []
    for row in load_policy_events():
        if program and program not in row["programs"].split(";") and "all" not in row["programs"].split(";"):
            continue
        first = row["first_affected_award_year_start"]
        last = row["last_affected_award_year_start"]
        if first and int(first) > award_year_start:
            continue
        if last and int(last) < award_year_start:
            continue
        found.append(dict(row))
    return found
