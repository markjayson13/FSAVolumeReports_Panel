"""Apply source-row identity recoveries with immutable, contemporaneous evidence."""
from __future__ import annotations
import json
import re
from pathlib import Path
import pandas as pd
from fsa_observations import normalize_full_opeid, text

LEDGER = Path(__file__).resolve().parents[1] / "Metadata/source_identity_resolutions.csv"


def resolve_source_identities(mapped: pd.DataFrame, entry: dict, excel_rows: list[int], sheet: str,
                              ledger_path: Path = LEDGER) -> tuple[pd.Series, pd.Series]:
    """Return resolved full IDs and resolution references; never alter raw cells.

    A row number alone is insufficient: file digest, sheet, year and original
    descriptors must agree. Recovery cannot replace a valid ID or create a
    duplicate within the same report. Unknown rows remain unknown.
    """
    ids = mapped["opeid8"].map(normalize_full_opeid).astype("string")
    resolution = pd.Series(pd.NA, index=mapped.index, dtype="string")
    if not ledger_path.exists():
        return ids, resolution
    ledger = pd.read_csv(ledger_path, dtype=str, keep_default_na=False)
    needed = {"resolution_id", "family", "award_year", "filename", "source_sha256", "source_sheet",
              "source_excel_row", "resolution_status", "recovered_opeid8", "evidence_json"}
    if not needed.issubset(ledger):
        raise ValueError("Identity-resolution ledger lacks required fields")
    if ledger.resolution_id.duplicated().any():
        raise ValueError("Identity resolution IDs are not unique")
    chosen = ledger.loc[(ledger.family == entry["family"]) & (ledger.award_year == entry["award_year"])
                        & (ledger.filename == entry["filename"]) & (ledger.resolution_status == "approved")]
    excel = pd.Series(excel_rows, index=mapped.index)
    for row in chosen.to_dict("records"):
        if row["source_sha256"] != entry.get("sha256") or row["source_sheet"] != sheet:
            raise ValueError(f"Identity recovery source vintage changed: {row['resolution_id']}")
        target = excel.eq(int(row["source_excel_row"]))
        if target.sum() != 1:
            raise ValueError(f"Identity recovery does not identify one source row: {row['resolution_id']}")
        index = target.index[target][0]
        for field, expected in [("opeid8", "expected_raw_opeid"), ("school", "expected_school"),
                                ("state", "expected_state"), ("zip_code", "expected_zip_code")]:
            actual = text(mapped.loc[index, field]) if field in mapped else ""
            if actual != row.get(expected, "").strip():
                raise ValueError(f"Identity recovery raw {field} changed: {row['resolution_id']}")
        recovered = row["recovered_opeid8"]
        if re.fullmatch(r"[0-9]{8}", recovered) is None or normalize_full_opeid(recovered) != recovered:
            raise ValueError("Recovered OPEID must be a valid eight-digit string")
        if pd.notna(ids.loc[index]) or pd.notna(resolution.loc[index]):
            raise ValueError("Recovery cannot replace a valid or already recovered identity")
        if ids.eq(recovered).any():
            raise ValueError(f"Identity recovery collides with another report row: {recovered}")
        evidence = json.loads(row["evidence_json"])
        independent = [e for e in evidence if e.get("kind") == "same_award_year_fsa_full_opeid"]
        directory = [e for e in evidence if e.get("kind") == "same_year_official_ipeds_directory"]
        if not independent or not directory:
            raise ValueError("Recovery requires contemporaneous independent FSA and official directory evidence")
        for e in independent + directory:
            if e.get("opeid8") != recovered or not e.get("url") or re.fullmatch(r"[0-9a-f]{64}", e.get("sha256", "")) is None:
                raise ValueError("Identity recovery evidence does not support the recovered full ID")
        if any(e.get("family") == entry["family"] for e in independent):
            raise ValueError("Identity corroboration must come from an independent FSA report family")
        if any(e.get("award_year") != entry["award_year"] for e in independent):
            raise ValueError("Independent FSA identity evidence is not contemporaneous")
        if any(int(e.get("ipeds_year", -1)) != int(entry["award_year"][:4]) for e in directory):
            raise ValueError("Identity evidence is not contemporaneous")
        ids.loc[index] = recovered
        resolution.loc[index] = row["resolution_id"]
    return ids, resolution
