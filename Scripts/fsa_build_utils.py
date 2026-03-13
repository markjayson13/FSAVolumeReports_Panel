#!/usr/bin/env python3
"""
Shared helpers for the FSA Title IV volume-report panel pipeline.

The design mirrors the newer IPEDSDB_Panel repository:
- repo-local code and tests
- durable data and QA artifacts outside git under FSA_ROOT
- stage scripts that mostly coordinate shared logic from this module
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import unquote, urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup


DEFAULT_FSA_ROOT = Path("/Users/markjaysonfarol13/Projects/FSAVolumeReports_Paneling")
REPO_ROOT = Path(__file__).resolve().parents[1]
TITLE_IV_PAGE_URL = "https://studentaid.gov/data-center/student/title-iv"
TITLE_IV_JSON_URL = f"{TITLE_IV_PAGE_URL}.json"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

VALID_DOWNLOAD_SUFFIXES = {".xls", ".xlsx", ".csv"}
DEFINITION_SHEET_HINTS = ("definition", "field definitions")
SUMMARY_SHEET_HINTS = ("award year summary", "summary", "ytd", "cumulative")
DESCRIPTOR_COLUMN_TOKENS = {
    "ope_id",
    "opeid",
    "school",
    "state",
    "zip_code",
    "school_type",
}

COMPONENT_FAMILIES = {
    "grants": {
        "display": "Grant Volume",
        "download_dir": "Grant_Volume",
        "cross_sections_dir": "grants",
        "panel_dir": "grants",
        "prefix": "grant__",
    },
    "campus_based": {
        "display": "Campus-Based Volume",
        "download_dir": "Campus_Based_Volume",
        "cross_sections_dir": "campus_based",
        "panel_dir": "campus_based",
        "prefix": "campus__",
    },
    "direct_loans": {
        "display": "Loan Volume / Direct",
        "download_dir": "Loan_Volume/Direct",
        "cross_sections_dir": "loans_direct",
        "panel_dir": "loans",
        "prefix": "loan_direct__",
    },
    "ffel": {
        "display": "Loan Volume / FFEL",
        "download_dir": "Loan_Volume/FFEL",
        "cross_sections_dir": "loans_ffel",
        "panel_dir": "loans",
        "prefix": "loan_ffel__",
    },
}

AWARD_YEAR_PATTERNS: Sequence[re.Pattern[str]] = [
    re.compile(r"AY(?P<start>\d{4})[-_](?P<end>\d{2,4})", flags=re.IGNORECASE),
    re.compile(r"AY(?P<start>\d{2})[-_](?P<end>\d{2})", flags=re.IGNORECASE),
    re.compile(r"(?P<start>\d{4})[-_](?P<end>\d{2,4})"),
    re.compile(r"(?P<start>\d{2})[-_](?P<end>\d{2})"),
]

COMPONENT_ORDER = ["grants", "campus_based", "direct_loans", "ffel"]

EXPECTED_SELECTED_SCOPE = {
    "grants": {
        "annual_years": tuple(range(1999, 2006)),
        "q4_years": tuple(range(2006, 2025)),
    },
    "campus_based": {
        "annual_years": tuple(range(2001, 2024)),
        "q4_years": (),
    },
    "direct_loans": {
        "annual_years": tuple(range(1999, 2006)),
        "q4_years": tuple(range(2006, 2025)),
    },
    "ffel": {
        "annual_years": tuple(range(1999, 2006)),
        "q4_years": tuple(range(2006, 2010)),
    },
}

INVENTORY_FIELDS = [
    "family",
    "family_display",
    "link_text",
    "url",
    "filename",
    "award_year",
    "award_year_start",
    "award_year_end",
    "quarter",
    "period_type",
    "selected_for_panel",
    "selection_reason",
]


@dataclass(frozen=True)
class DataRootLayout:
    root: Path
    raw_title_iv_reports: Path
    cross_sections: Path
    dictionary: Path
    panels: Path
    checks: Path
    build: Path


@dataclass
class WorkbookParseResult:
    workbook_path: Path
    selected_sheet: str
    sheet_names: list[str]
    header_row_index: int | None
    flattened_headers: list[str]
    frame: pd.DataFrame
    warnings: list[str]


def repo_root() -> Path:
    return REPO_ROOT


def data_root() -> Path:
    return Path(os.environ.get("FSA_ROOT", str(DEFAULT_FSA_ROOT))).expanduser()


def data_layout(root: str | Path | None = None) -> DataRootLayout:
    base = Path(root).expanduser() if root is not None else data_root()
    return DataRootLayout(
        root=base,
        raw_title_iv_reports=base / "Raw_Title_IV_Reports",
        cross_sections=base / "Cross_sections",
        dictionary=base / "Dictionary",
        panels=base / "Panels",
        checks=base / "Checks",
        build=base / "build",
    )


def ensure_data_layout(root: str | Path | None = None) -> DataRootLayout:
    layout = data_layout(root)
    for path in (
        layout.root,
        layout.raw_title_iv_reports,
        layout.cross_sections,
        layout.dictionary,
        layout.panels,
        layout.checks,
        layout.build,
        layout.checks / "download_qc",
        layout.checks / "source_qc",
        layout.checks / "dictionary_qc",
        layout.checks / "panel_qc",
        layout.checks / "acceptance_qc",
        layout.checks / "logs",
    ):
        path.mkdir(parents=True, exist_ok=True)
    for family in COMPONENT_FAMILIES:
        component_download_root(layout, family).mkdir(parents=True, exist_ok=True)
        component_cross_sections_dir(layout, family).mkdir(parents=True, exist_ok=True)
        component_panel_dir(layout, family).mkdir(parents=True, exist_ok=True)
    (layout.panels / "final").mkdir(parents=True, exist_ok=True)
    return layout


def component_download_root(layout: DataRootLayout, family: str) -> Path:
    return layout.raw_title_iv_reports / COMPONENT_FAMILIES[family]["download_dir"]


def component_year_dir(layout: DataRootLayout, family: str, start_year: int) -> Path:
    return component_download_root(layout, family) / str(int(start_year))


def component_cross_sections_dir(layout: DataRootLayout, family: str) -> Path:
    return layout.cross_sections / COMPONENT_FAMILIES[family]["cross_sections_dir"]


def component_panel_dir(layout: DataRootLayout, family: str) -> Path:
    if family == "loans":
        return layout.panels / "loans"
    return layout.panels / COMPONENT_FAMILIES[family]["panel_dir"]


def write_rows(path: Path, rows: list[dict], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fieldnames))
        writer.writeheader()
        if rows:
            writer.writerows(rows)


def compute_file_metadata(path: Path) -> tuple[int, str]:
    if not path.exists():
        return 0, ""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            if chunk:
                digest.update(chunk)
    return path.stat().st_size, digest.hexdigest()


def normalize_token(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def normalize_year_component(value: object, reference: int | None = None) -> int | None:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return None
    if len(digits) == 4:
        return int(digits)
    if len(digits) == 2:
        yy = int(digits)
        if reference is not None:
            century = reference // 100
            candidate = (century * 100) + yy
            if candidate < reference:
                candidate += 100
            return candidate
        return 1900 + yy if yy >= 90 else 2000 + yy
    return None


def normalize_award_year_string(label: object) -> str | None:
    text = str(label or "").strip()
    if not text:
        return None
    for pattern in AWARD_YEAR_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        start_year = normalize_year_component(match.group("start"))
        end_year = normalize_year_component(match.group("end"), reference=start_year)
        if start_year is None or end_year is None:
            continue
        return f"{start_year:04d}-{end_year:04d}"
    return None


def explode_award_year_bounds(label: object) -> tuple[int | None, int | None]:
    normalized = normalize_award_year_string(label)
    if normalized is None:
        return None, None
    start_txt, end_txt = normalized.split("-", 1)
    return int(start_txt), int(end_txt)


def infer_quarter(text: object) -> int | None:
    match = re.search(r"(?:^|[^0-9A-Z])Q(?P<q>[1-4])(?:[^0-9A-Z]|$)", str(text or ""), flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group("q"))


def standardize_opeid8(raw: object) -> str | None:
    digits = re.sub(r"\D", "", str(raw or ""))
    if not digits:
        return None
    if len(digits) >= 8:
        return digits[:8]
    if len(digits) == 7:
        return digits.zfill(8)
    return f"{digits.zfill(6)}00"


def derive_opeid6(opeid8: object) -> str | None:
    standardized = standardize_opeid8(opeid8)
    if standardized is None:
        return None
    return standardized[:6]


def sanitize_href(href: str) -> str:
    cleaned = str(href or "").strip().strip('"').strip("'")
    return cleaned


def basename_from_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path)).name
    return Path(parsed.path).name


def classify_report_family(url: str, link_text: str) -> str | None:
    filename = basename_from_url(url)
    suffix = Path(filename).suffix.lower()
    if suffix not in VALID_DOWNLOAD_SUFFIXES:
        return None
    haystack = normalize_token(f"{filename} {link_text}")
    if any(token in haystack for token in ("campus_based", "campusbased", "cbdashboard", "cbdata")):
        return "campus_based"
    if any(token in haystack for token in ("ffel_awardyr", "ffel_award", "fl_dashboard")):
        return "ffel"
    if any(token in haystack for token in ("dl_dashboard", "dl_awardyr", "dl_award")):
        return "direct_loans"
    if any(token in haystack for token in ("grants_ay", "pell", "q4", "q3", "q2", "q1")) and (
        "grant" in haystack or "pell" in haystack or re.search(r"q[1-4]\d{4}ay", filename, flags=re.IGNORECASE)
    ):
        return "grants"
    return None


def append_title_iv_entry(
    rows: list[dict],
    seen: set[tuple[str, str]],
    *,
    url: str,
    text: str,
) -> None:
    family = classify_report_family(url, text)
    if family is None:
        return
    filename = basename_from_url(url)
    award_year = normalize_award_year_string(f"{text} {filename}")
    if award_year is None:
        return
    quarter = infer_quarter(f"{text} {filename}")
    key = (family, url)
    if key in seen:
        return
    seen.add(key)
    start_year, end_year = explode_award_year_bounds(award_year)
    period_type = "quarterly" if quarter is not None else "annual"
    rows.append(
        {
            "family": family,
            "family_display": COMPONENT_FAMILIES[family]["display"],
            "link_text": text,
            "url": url,
            "filename": filename,
            "award_year": award_year,
            "award_year_start": start_year,
            "award_year_end": end_year,
            "quarter": quarter or "",
            "period_type": period_type,
        }
    )


def sort_inventory_rows(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: (
            COMPONENT_ORDER.index(row["family"]),
            int(row["award_year_start"]),
            0 if row["quarter"] == "" else int(row["quarter"]),
            row["filename"],
        ),
    )


def parse_title_iv_entries(html: str, base_url: str = TITLE_IV_PAGE_URL) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for anchor in soup.find_all("a", href=True):
        href = sanitize_href(anchor["href"])
        if not href:
            continue
        url = urljoin(base_url, href)
        text = anchor.get_text(" ", strip=True) or basename_from_url(url)
        append_title_iv_entry(rows, seen, url=url, text=text)
    return sort_inventory_rows(rows)


def parse_title_iv_json(payload: object, base_url: str = TITLE_IV_PAGE_URL) -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("widgetType") == "anchor" and node.get("href"):
                url = urljoin(base_url, sanitize_href(str(node.get("href", ""))))
                text = str(node.get("value", "")).strip() or basename_from_url(url)
                append_title_iv_entry(rows, seen, url=url, text=text)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return sort_inventory_rows(rows)


def annotate_panel_selection(entries: Iterable[dict]) -> list[dict]:
    annotated: list[dict] = []
    for row in entries:
        entry = dict(row)
        family = entry["family"]
        start_year = int(entry["award_year_start"])
        quarter = int(entry["quarter"]) if str(entry["quarter"]).strip() else None
        selected = False
        reason = ""
        if family == "campus_based":
            if quarter is not None:
                selected = False
                reason = "quarterly_not_expected_for_campus_based"
            elif start_year <= 2023:
                selected = True
                reason = "annual_campus_based_selected"
            else:
                selected = False
                reason = "award_year_not_complete"
        elif family == "ffel":
            if quarter is None and start_year <= 2005:
                selected = True
                reason = "annual_summary_selected"
            elif quarter == 4 and 2006 <= start_year <= 2009:
                selected = True
                reason = "q4_cumulative_selected"
            elif quarter in {1, 2, 3}:
                selected = False
                reason = "non_q4_quarter_excluded"
            else:
                selected = False
                reason = "award_year_not_complete"
        else:
            if quarter is None and start_year <= 2005:
                selected = True
                reason = "annual_summary_selected"
            elif quarter == 4 and start_year <= 2024:
                selected = True
                reason = "q4_cumulative_selected"
            elif quarter in {1, 2, 3}:
                selected = False
                reason = "non_q4_quarter_excluded"
            else:
                selected = False
                reason = "award_year_not_complete"
        entry["selected_for_panel"] = selected
        entry["selection_reason"] = reason
        annotated.append(entry)
    return annotated


def load_title_iv_page_html(page_html: str | Path | None = None, timeout: int = 120) -> tuple[str, str]:
    if page_html is not None:
        path = Path(page_html).expanduser()
        return path.read_text(encoding="utf-8"), path.parent.as_uri() + "/"
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    response = session.get(TITLE_IV_PAGE_URL, timeout=timeout)
    response.raise_for_status()
    return response.text, TITLE_IV_PAGE_URL


def load_title_iv_page_json(timeout: int = 120) -> object:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    response = session.get(TITLE_IV_JSON_URL, timeout=timeout)
    response.raise_for_status()
    return response.json()


def local_source_path_from_url(url: str) -> Path | None:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path))
    if parsed.scheme == "" and Path(url).exists():
        return Path(url)
    return None


def download_file(session: requests.Session, url: str, destination: Path, timeout: int) -> None:
    source_path = local_source_path_from_url(url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source_path is not None:
        shutil.copyfile(source_path, destination)
        return
    with session.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with destination.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    fh.write(chunk)


def manifest_rows(layout: DataRootLayout) -> list[dict]:
    rows: list[dict] = []
    for manifest_path in sorted(layout.raw_title_iv_reports.glob("**/manifest.csv")):
        frame = pd.read_csv(manifest_path, dtype=str).fillna("")
        rows.extend(frame.to_dict("records"))
    return rows


def release_inventory_path(layout: DataRootLayout) -> Path:
    return layout.checks / "download_qc" / "release_inventory.csv"


def selected_panel_files_path(layout: DataRootLayout) -> Path:
    return layout.checks / "download_qc" / "selected_panel_files.csv"


def preflight_release_inventory_path(layout: DataRootLayout) -> Path:
    return layout.checks / "download_qc" / "preflight_release_inventory.csv"


def preflight_selected_panel_files_path(layout: DataRootLayout) -> Path:
    return layout.checks / "download_qc" / "preflight_selected_panel_files.csv"


def preflight_summary_path(layout: DataRootLayout) -> Path:
    return layout.checks / "download_qc" / "preflight_inventory_summary.csv"


def preflight_validation_path(layout: DataRootLayout) -> Path:
    return layout.checks / "download_qc" / "preflight_validation.csv"


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "t", "yes", "y"}


def discover_title_iv_inventory(*, page_html: str | Path | None = None, timeout: int = 120) -> list[dict]:
    if page_html is not None:
        path = Path(page_html).expanduser()
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            return annotate_panel_selection(parse_title_iv_json(payload, base_url=TITLE_IV_PAGE_URL))
        html, base_url = load_title_iv_page_html(page_html=page_html, timeout=timeout)
        return annotate_panel_selection(parse_title_iv_entries(html, base_url=base_url))
    try:
        payload = load_title_iv_page_json(timeout=timeout)
        rows = parse_title_iv_json(payload, base_url=TITLE_IV_PAGE_URL)
        if rows:
            return annotate_panel_selection(rows)
    except Exception:  # noqa: BLE001
        pass
    html, base_url = load_title_iv_page_html(page_html=None, timeout=timeout)
    return annotate_panel_selection(parse_title_iv_entries(html, base_url=base_url))


def selected_inventory_rows(entries: Iterable[dict]) -> list[dict]:
    return [dict(row) for row in entries if as_bool(row.get("selected_for_panel"))]


def expected_selected_start_years(family: str) -> list[int]:
    scope = EXPECTED_SELECTED_SCOPE[family]
    return sorted({*scope["annual_years"], *scope["q4_years"]})


def expected_selected_file_count(family: str) -> int:
    scope = EXPECTED_SELECTED_SCOPE[family]
    return len(scope["annual_years"]) + len(scope["q4_years"])


def summarize_inventory(entries: Iterable[dict]) -> pd.DataFrame:
    rows: list[dict] = []
    for family in COMPONENT_ORDER:
        family_entries = [row for row in entries if row["family"] == family]
        selected = selected_inventory_rows(family_entries)
        discovered_years = sorted({int(row["award_year_start"]) for row in family_entries})
        selected_years = sorted(int(row["award_year_start"]) for row in selected)
        selected_quarters = sorted(
            {int(row["quarter"]) for row in selected if str(row.get("quarter", "")).strip()}
        )
        rows.append(
            {
                "family": family,
                "family_display": COMPONENT_FAMILIES[family]["display"],
                "discovered_files": int(len(family_entries)),
                "selected_files": int(len(selected)),
                "expected_selected_files": int(expected_selected_file_count(family)),
                "discovered_start_year_min": "" if not discovered_years else int(discovered_years[0]),
                "discovered_start_year_max": "" if not discovered_years else int(discovered_years[-1]),
                "selected_start_year_min": "" if not selected_years else int(min(selected_years)),
                "selected_start_year_max": "" if not selected_years else int(max(selected_years)),
                "selected_quarters": json.dumps(selected_quarters),
                "selected_years_json": json.dumps(selected_years),
                "expected_selected_years_json": json.dumps(expected_selected_start_years(family)),
            }
        )
    return pd.DataFrame(rows)


def validate_inventory_scope(entries: Iterable[dict]) -> pd.DataFrame:
    rows: list[dict] = []
    for family in COMPONENT_ORDER:
        family_entries = [row for row in entries if row["family"] == family]
        selected = selected_inventory_rows(family_entries)
        actual_selected_years = sorted(int(row["award_year_start"]) for row in selected)
        expected_years = expected_selected_start_years(family)
        duplicate_years = sorted(
            {
                year
                for year in actual_selected_years
                if actual_selected_years.count(year) > 1
            }
        )
        invalid_selected_quarters = sorted(
            {
                f"{row['award_year']}::Q{row['quarter']}"
                for row in selected
                if str(row.get("quarter", "")).strip() and int(row["quarter"]) != 4
            }
        )
        out_of_scope_selected_years = sorted(set(actual_selected_years) - set(expected_years))
        rows.extend(
            [
                {
                    "check": "family_present_in_discovery",
                    "component_family": family,
                    "passed": bool(family_entries),
                    "details": f"discovered_files={len(family_entries)}",
                },
                {
                    "check": "selected_award_years_match_expected_scope",
                    "component_family": family,
                    "passed": actual_selected_years == expected_years,
                    "details": f"expected={expected_years}; actual={actual_selected_years}",
                },
                {
                    "check": "selected_file_count_matches_expected_scope",
                    "component_family": family,
                    "passed": len(selected) == expected_selected_file_count(family),
                    "details": f"expected={expected_selected_file_count(family)}; actual={len(selected)}",
                },
                {
                    "check": "selected_rows_unique_by_award_year",
                    "component_family": family,
                    "passed": not duplicate_years,
                    "details": f"duplicate_start_years={duplicate_years}",
                },
                {
                    "check": "selected_rows_use_only_annual_or_q4_files",
                    "component_family": family,
                    "passed": not invalid_selected_quarters,
                    "details": f"invalid_selected_quarters={invalid_selected_quarters}",
                },
                {
                    "check": "selected_rows_do_not_include_out_of_scope_years",
                    "component_family": family,
                    "passed": not out_of_scope_selected_years,
                    "details": f"out_of_scope_selected_start_years={out_of_scope_selected_years}",
                },
            ]
        )
    return pd.DataFrame(rows)


def write_preflight_inventory(layout: DataRootLayout, entries: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    write_rows(preflight_release_inventory_path(layout), entries, INVENTORY_FIELDS)
    selected = selected_inventory_rows(entries)
    write_rows(preflight_selected_panel_files_path(layout), selected, INVENTORY_FIELDS)
    summary = summarize_inventory(entries)
    summary.to_csv(preflight_summary_path(layout), index=False)
    validation = validate_inventory_scope(entries)
    validation.to_csv(preflight_validation_path(layout), index=False)
    return summary, validation


def preflight_title_iv_inventory(
    root: str | Path | None = None,
    *,
    page_html: str | Path | None = None,
    timeout: int = 120,
    strict: bool = True,
) -> tuple[list[dict], pd.DataFrame, pd.DataFrame]:
    layout = ensure_data_layout(root)
    entries = discover_title_iv_inventory(page_html=page_html, timeout=timeout)
    summary, validation = write_preflight_inventory(layout, entries)
    failed = validation.loc[~validation["passed"].astype(bool)]
    if strict and not failed.empty:
        raise SystemExit(
            "Preflight inventory validation failed. Inspect "
            f"{preflight_validation_path(layout)} and {preflight_selected_panel_files_path(layout)}."
        )
    return entries, summary, validation


def download_title_iv_reports(
    root: str | Path | None = None,
    *,
    page_html: str | Path | None = None,
    skip_existing: bool = True,
    timeout: int = 120,
    strict_source_checks: bool = True,
    verify_only: bool = False,
) -> list[dict]:
    layout = ensure_data_layout(root)
    entries, _, _ = preflight_title_iv_inventory(
        layout.root,
        page_html=page_html,
        timeout=timeout,
        strict=strict_source_checks,
    )
    if verify_only:
        return entries
    write_rows(release_inventory_path(layout), entries, INVENTORY_FIELDS)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    failures: list[dict] = []
    manifest_map: dict[tuple[str, int], list[dict]] = {}
    for entry in entries:
        family = entry["family"]
        start_year = int(entry["award_year_start"])
        year_dir = component_year_dir(layout, family, start_year)
        download_dir = year_dir / "downloads"
        download_dir.mkdir(parents=True, exist_ok=True)
        destination = download_dir / entry["filename"]
        status = "existing"
        try:
            if not (skip_existing and destination.exists()):
                download_file(session, entry["url"], destination, timeout)
                status = "downloaded"
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            failures.append(
                {
                    "family": family,
                    "award_year_start": start_year,
                    "filename": entry["filename"],
                    "error": str(exc),
                }
            )
        size_bytes, sha256 = compute_file_metadata(destination)
        manifest_row = {
            **entry,
            "local_path": str(destination),
            "download_status": status,
            "filesize_bytes": size_bytes,
            "sha256": sha256,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest_map.setdefault((family, start_year), []).append(manifest_row)
    manifest_fields = [
        *INVENTORY_FIELDS,
        "local_path",
        "download_status",
        "filesize_bytes",
        "sha256",
        "downloaded_at",
    ]
    for (family, start_year), rows in manifest_map.items():
        write_rows(component_year_dir(layout, family, start_year) / "manifest.csv", rows, manifest_fields)
    write_rows(
        layout.checks / "download_qc" / "download_failures.csv",
        failures,
        ["family", "award_year_start", "filename", "error"],
    )
    selected_rows = [row for row in manifest_rows(layout) if str(row.get("selected_for_panel", "")).lower() == "true"]
    write_rows(selected_panel_files_path(layout), selected_rows, manifest_fields)
    if failures:
        raise SystemExit(f"Download failures encountered for {len(failures)} files.")
    return entries


def load_selected_panel_entries(layout: DataRootLayout, family: str | None = None) -> list[dict]:
    path = selected_panel_files_path(layout)
    if not path.exists():
        raise SystemExit(f"Missing selected panel manifest: {path}")
    frame = pd.read_csv(path, dtype=str).fillna("")
    if family is not None:
        frame = frame[frame["family"] == family].copy()
    return frame.to_dict("records")


def choose_selected_sheet(
    sheet_names: Sequence[str],
    family: str,
    period_type: str,
) -> str:
    if not sheet_names:
        raise ValueError("Workbook has no sheets.")
    candidates = [name for name in sheet_names if normalize_token(name) not in {"", "sheet1"}]
    if not candidates:
        candidates = list(sheet_names)
    filtered = [
        name
        for name in candidates
        if not any(hint in normalize_token(name) for hint in ("definitions", "field_definitions", "definition"))
    ]
    candidates = filtered or candidates
    if family == "campus_based":
        return candidates[0]
    if period_type == "quarterly":
        for name in candidates:
            normalized = normalize_token(name)
            if any(hint in normalized for hint in ("award_year_summary", "summary", "ytd", "cumulative")):
                return name
    return candidates[0]


def read_workbook_raw(path: Path, sheet_name: str | None = None) -> tuple[list[str], pd.DataFrame, str]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path, header=None, dtype=str, keep_default_na=False)
        return ["__csv__"], frame, "__csv__"
    with pd.ExcelFile(path) as workbook:
        selected_sheet = choose_selected_sheet(
            workbook.sheet_names,
            family="campus_based" if sheet_name == "__campus_first__" else "grants",
            period_type="annual",
        )
        if sheet_name and sheet_name not in {"__campus_first__", ""}:
            selected_sheet = sheet_name
        raw = pd.read_excel(path, sheet_name=selected_sheet, header=None, dtype=str)
        return workbook.sheet_names, raw.fillna(""), selected_sheet


def find_header_row(frame: pd.DataFrame) -> int | None:
    for idx in range(min(len(frame), 20)):
        tokens = {normalize_token(value) for value in frame.iloc[idx].tolist()}
        if "ope_id" in tokens or "opeid" in tokens:
            return idx
    return None


def propagated_group_labels(values: Sequence[object]) -> list[str]:
    propagated: list[str] = []
    current = ""
    for value in values:
        normalized = str(value or "").strip()
        if normalized:
            current = normalized
        propagated.append(current)
    return propagated


def flattened_headers_from_rows(
    group_row: Sequence[object] | None,
    header_row: Sequence[object],
) -> list[str]:
    group_labels = propagated_group_labels(group_row or [""] * len(header_row))
    headers: list[str] = []
    seen: dict[str, int] = {}
    for group_label, header_label in zip(group_labels, header_row):
        group_label = str(group_label or "").strip()
        header_label = str(header_label or "").strip()
        header_norm = normalize_token(header_label)
        base = ""
        if header_norm in DESCRIPTOR_COLUMN_TOKENS or group_label == "":
            base = header_label or group_label or "unnamed"
        elif header_label == "":
            base = group_label
        elif normalize_token(group_label) == normalize_token(header_label):
            base = group_label
        else:
            base = f"{group_label} | {header_label}"
        base = re.sub(r"\s+", " ", base).strip()
        if not base:
            base = "unnamed"
        count = seen.get(base, 0)
        seen[base] = count + 1
        if count:
            base = f"{base}_{count}"
        headers.append(base)
    return headers


def parse_selected_sheet(
    workbook_path: Path,
    family: str,
    period_type: str,
) -> WorkbookParseResult:
    warnings: list[str] = []
    suffix = workbook_path.suffix.lower()
    if suffix == ".csv":
        raw = pd.read_csv(workbook_path, header=None, dtype=str, keep_default_na=False).fillna("")
        selected_sheet = "__csv__"
        sheet_names = [selected_sheet]
    else:
        with pd.ExcelFile(workbook_path) as workbook:
            sheet_names = workbook.sheet_names
            try:
                selected_sheet = choose_selected_sheet(sheet_names, family=family, period_type=period_type)
            except ValueError as exc:
                warnings.append(str(exc))
                return WorkbookParseResult(
                    workbook_path=workbook_path,
                    selected_sheet="",
                    sheet_names=sheet_names,
                    header_row_index=None,
                    flattened_headers=[],
                    frame=pd.DataFrame(),
                    warnings=warnings,
                )
            raw = pd.read_excel(workbook_path, sheet_name=selected_sheet, header=None, dtype=str).fillna("")
    header_row_index = find_header_row(raw)
    if header_row_index is None:
        warnings.append("header_row_not_found")
        return WorkbookParseResult(
            workbook_path=workbook_path,
            selected_sheet=selected_sheet,
            sheet_names=sheet_names,
            header_row_index=None,
            flattened_headers=[],
            frame=pd.DataFrame(),
            warnings=warnings,
        )
    group_row = raw.iloc[header_row_index - 1].tolist() if header_row_index > 0 else None
    header_row = raw.iloc[header_row_index].tolist()
    flattened_headers = flattened_headers_from_rows(group_row, header_row)
    frame = raw.iloc[header_row_index + 1 :].copy()
    frame.columns = flattened_headers
    frame = frame.replace({"": pd.NA}).dropna(how="all").reset_index(drop=True)
    return WorkbookParseResult(
        workbook_path=workbook_path,
        selected_sheet=selected_sheet,
        sheet_names=sheet_names,
        header_row_index=header_row_index,
        flattened_headers=flattened_headers,
        frame=frame,
        warnings=warnings,
    )


def profile_workbooks(root: str | Path | None = None) -> pd.DataFrame:
    layout = ensure_data_layout(root)
    rows: list[dict] = []
    for manifest_row in manifest_rows(layout):
        local_path = Path(manifest_row["local_path"])
        result = parse_selected_sheet(local_path, manifest_row["family"], manifest_row["period_type"])
        opeids = pd.Series(dtype="string")
        non00_rows = 0
        if not result.frame.empty:
            opeid_col = next(
                (col for col in result.frame.columns if normalize_token(col) in {"ope_id", "opeid"}),
                None,
            )
            if opeid_col is not None:
                opeids = result.frame[opeid_col].apply(standardize_opeid8).astype("string")
                opeids = opeids.dropna()
                non00_rows = int((opeids.str[-2:] != "00").sum())
        signature = hashlib.sha256(
            "|".join(normalize_token(col) for col in result.flattened_headers).encode("utf-8")
        ).hexdigest()
        rows.append(
            {
                "family": manifest_row["family"],
                "award_year": manifest_row["award_year"],
                "award_year_start": manifest_row["award_year_start"],
                "filename": manifest_row["filename"],
                "local_path": manifest_row["local_path"],
                "selected_for_panel": manifest_row["selected_for_panel"],
                "selected_sheet": result.selected_sheet,
                "sheet_names_json": json.dumps(result.sheet_names),
                "header_row_index": "" if result.header_row_index is None else result.header_row_index,
                "flattened_header_signature": signature,
                "flattened_headers_json": json.dumps(result.flattened_headers),
                "row_count": int(len(result.frame)),
                "opeid_count": int(len(opeids)),
                "non00_opeid_count": non00_rows,
                "parse_warnings_json": json.dumps(result.warnings),
            }
        )
    profile_path = layout.checks / "source_qc" / "workbook_profiles.csv"
    write_rows(
        profile_path,
        rows,
        [
            "family",
            "award_year",
            "award_year_start",
            "filename",
            "local_path",
            "selected_for_panel",
            "selected_sheet",
            "sheet_names_json",
            "header_row_index",
            "flattened_header_signature",
            "flattened_headers_json",
            "row_count",
            "opeid_count",
            "non00_opeid_count",
            "parse_warnings_json",
        ],
    )
    return pd.DataFrame(rows)


def normalize_metric_header(header: str) -> str:
    text = str(header or "").strip()
    text = text.replace("#", " number ")
    text = text.replace("$", " amount ")
    normalized = normalize_token(text)
    normalized = normalized.replace("sum_of_", "")
    normalized = normalized.replace("ytd_", "")
    normalized = normalized.replace("federal_", "federal_")
    return normalized


def metric_kind_from_header(normalized_header: str) -> str | None:
    if "recipient" in normalized_header:
        return "recipients"
    if "federal_award" in normalized_header:
        return "federal_award"
    if "number_of_loans_originated" in normalized_header or "num_of_loans_originated" in normalized_header:
        return "loans_originated_n"
    if "of_loans_originated" in normalized_header or "amount_of_loans_originated" in normalized_header:
        return "loans_originated_amt"
    if "number_of_disbursements" in normalized_header or "num_of_disbursements" in normalized_header:
        return "disbursements_n"
    if "of_disbursements" in normalized_header or "amount_of_disbursements" in normalized_header or "disbursement" in normalized_header or "disbursements" in normalized_header or "total_disbursed" in normalized_header:
        if "number_of_" in normalized_header or "num_of_" in normalized_header:
            return "disbursements_n"
        return "disbursements_amt" if "loan" in normalized_header else "disbursements"
    return None


def program_slug_from_header(family: str, normalized_header: str) -> str | None:
    if family == "grants":
        if "federal_pell_grant" in normalized_header:
            return "pell"
        if "academic_competitiveness" in normalized_header:
            return "acg"
        if "national_smart" in normalized_header or "smart_program" in normalized_header:
            return "smart"
        if "teach_program" in normalized_header or normalized_header.startswith("teach_"):
            return "teach"
        if "iraq" in normalized_header or "afghanistan" in normalized_header or "iasg" in normalized_header:
            return "iasg"
    elif family == "campus_based":
        if "fseog" in normalized_header or "federal_supplemental_educational_opportunity_grants" in normalized_header:
            return "fseog"
        if "fws" in normalized_header or "federal_work_study" in normalized_header:
            return "fws"
        if "perkins" in normalized_header:
            return "perkins"
    elif family in {"direct_loans", "ffel"}:
        if "unsubsidized_undergraduate" in normalized_header:
            return "unsubsidized_undergraduate"
        if "unsubsidized_graduate" in normalized_header:
            return "unsubsidized_graduate"
        if "unsubsidized" in normalized_header:
            return "unsubsidized"
        if "subsidized" in normalized_header:
            return "subsidized"
        if "parent_plus" in normalized_header:
            return "parent_plus"
        if "grad_plus" in normalized_header or "graduate_plus" in normalized_header:
            return "grad_plus"
        if re.search(r"(^|_)plus($|_)", normalized_header):
            return "plus"
    return None


def canonicalize_component_header(family: str, original_header: str) -> str | None:
    normalized = normalize_metric_header(original_header)
    if normalized in {"ope_id", "opeid"}:
        return "opeid8"
    if normalized == "school":
        return "school"
    if normalized == "state":
        return "state"
    if normalized == "zip_code":
        return "zip_code"
    if normalized == "school_type":
        return "school_type"
    metric_kind = metric_kind_from_header(normalized)
    program_slug = program_slug_from_header(family, normalized)
    if metric_kind is None or program_slug is None:
        return None
    return f"{program_slug}_{metric_kind}"


def series_has_nonempty_values(series: pd.Series) -> bool:
    cleaned = series.astype("string").str.strip().replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    return bool(cleaned.notna().any())


def build_dictionary(root: str | Path | None = None) -> pd.DataFrame:
    layout = ensure_data_layout(root)
    entries = load_selected_panel_entries(layout)
    rows: list[dict] = []
    unmapped_rows: list[dict] = []
    for entry in entries:
        path = Path(entry["local_path"])
        result = parse_selected_sheet(path, entry["family"], entry["period_type"])
        for header in result.flattened_headers:
            series = result.frame[header] if header in result.frame.columns else pd.Series(dtype="string")
            canonical_column = canonicalize_component_header(entry["family"], header)
            normalized_header = normalize_metric_header(header)
            actionable = series_has_nonempty_values(series) and normalized_header != "unnamed"
            mapping_status = "mapped" if canonical_column else ("unmapped_actionable" if actionable else "nonactionable")
            row = {
                "component_family": entry["family"],
                "source_filename": entry["filename"],
                "sheet_name": result.selected_sheet,
                "original_header": header,
                "normalized_header": normalized_header,
                "canonical_column": canonical_column or "",
                "mapping_status": mapping_status,
                "first_year": int(entry["award_year_start"]),
                "last_year": int(entry["award_year_end"]),
            }
            rows.append(row)
            if mapping_status == "unmapped_actionable":
                unmapped_rows.append(row)
    detail = pd.DataFrame(rows)
    if detail.empty:
        raise SystemExit("Dictionary build found no selected panel files.")
    aggregated = (
        detail.groupby(["component_family", "original_header", "normalized_header", "canonical_column", "mapping_status"], dropna=False)
        .agg(
            source_filename=("source_filename", lambda s: ";".join(sorted(set(str(v) for v in s if str(v).strip())))),
            sheet_name=("sheet_name", lambda s: ";".join(sorted(set(str(v) for v in s if str(v).strip())))),
            first_year=("first_year", "min"),
            last_year=("last_year", "max"),
        )
        .reset_index()
        .sort_values(["component_family", "canonical_column", "original_header"])
        .reset_index(drop=True)
    )
    dict_path = layout.dictionary / "fsa_volume_dictionary.parquet"
    aggregated.to_parquet(dict_path, index=False)
    aggregated.to_csv(layout.dictionary / "fsa_volume_dictionary.csv", index=False)
    unmapped = pd.DataFrame(unmapped_rows)
    if unmapped.empty:
        unmapped = pd.DataFrame(columns=aggregated.columns)
    unmapped.to_csv(layout.checks / "dictionary_qc" / "unmapped_actionable_headers.csv", index=False)
    summary_rows = [
        {"metric": "dictionary_rows", "value": int(len(aggregated))},
        {"metric": "mapped_rows", "value": int((aggregated["mapping_status"] == "mapped").sum())},
        {"metric": "unmapped_actionable_rows", "value": int((aggregated["mapping_status"] == "unmapped_actionable").sum())},
        {"metric": "nonactionable_rows", "value": int((aggregated["mapping_status"] == "nonactionable").sum())},
    ]
    write_rows(layout.checks / "dictionary_qc" / "dictionary_qaqc_summary.csv", summary_rows, ["metric", "value"])
    return aggregated


def load_dictionary_map(layout: DataRootLayout) -> dict[tuple[str, str], str]:
    path = layout.dictionary / "fsa_volume_dictionary.parquet"
    if not path.exists():
        raise SystemExit(f"Missing dictionary artifact: {path}")
    frame = pd.read_parquet(path)
    mapping: dict[tuple[str, str], str] = {}
    for row in frame.to_dict("records"):
        if row.get("canonical_column"):
            mapping[(row["component_family"], row["normalized_header"])] = row["canonical_column"]
    return mapping


def sanitize_numeric_series(series: pd.Series) -> pd.Series:
    cleaned = series.astype("string").str.strip()
    cleaned = cleaned.str.replace(",", "", regex=False)
    cleaned = cleaned.str.replace("$", "", regex=False)
    cleaned = cleaned.str.replace("(", "-", regex=False).str.replace(")", "", regex=False)
    cleaned = cleaned.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    return pd.to_numeric(cleaned, errors="coerce")


def format_integer_series(series: pd.Series) -> pd.Series:
    numeric = sanitize_numeric_series(series)
    return numeric.round().astype("Int64")


def format_string_series(series: pd.Series, formatter: str | None = None) -> pd.Series:
    cleaned = series.astype("string").str.strip()
    cleaned = cleaned.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    if formatter == "upper":
        cleaned = cleaned.str.upper()
    elif formatter == "title":
        cleaned = cleaned.str.title()
    return cleaned


def format_zip_series(series: pd.Series) -> pd.Series:
    def _format(value: object) -> object:
        if pd.isna(value):
            return pd.NA
        digits = re.sub(r"\D", "", str(value))
        if not digits:
            return pd.NA
        if len(digits) >= 9:
            digits = digits[:9]
            return f"{digits[:5]}-{digits[5:]}"
        return digits[:5].zfill(5)

    return series.apply(_format).astype("string")


def combine_duplicate_series(existing: pd.Series, incoming: pd.Series, *, label: str) -> pd.Series:
    existing = existing.reset_index(drop=True)
    incoming = incoming.reset_index(drop=True)
    overlap = existing.notna() & incoming.notna()
    if overlap.any():
        left = existing[overlap].astype("string")
        right = incoming[overlap].astype("string")
        if not left.equals(right):
            raise ValueError(f"Conflicting duplicate values encountered for {label}.")
    return existing.combine_first(incoming)


def apply_component_mapping(
    family: str,
    frame: pd.DataFrame,
    dictionary_map: dict[tuple[str, str], str],
) -> tuple[pd.DataFrame, list[dict]]:
    mapped: dict[str, pd.Series] = {}
    unmapped_actionable: list[dict] = []
    for original_header in frame.columns:
        normalized_header = normalize_metric_header(original_header)
        canonical = dictionary_map.get((family, normalized_header))
        series = frame[original_header]
        if canonical is None:
            if series_has_nonempty_values(series) and normalized_header != "unnamed":
                unmapped_actionable.append(
                    {
                        "component_family": family,
                        "original_header": original_header,
                        "normalized_header": normalized_header,
                    }
                )
            continue
        if canonical in mapped:
            mapped[canonical] = combine_duplicate_series(mapped[canonical], series, label=f"{family}:{canonical}")
        else:
            mapped[canonical] = series.copy()
    return pd.DataFrame(mapped), unmapped_actionable


def component_prefix(family: str) -> str:
    return COMPONENT_FAMILIES[family]["prefix"]


def prepare_component_panel_frame(
    family: str,
    entry: dict,
    parse_result: WorkbookParseResult,
    dictionary_map: dict[tuple[str, str], str],
) -> tuple[pd.DataFrame, list[dict]]:
    mapped, unmapped_actionable = apply_component_mapping(family, parse_result.frame, dictionary_map)
    if mapped.empty:
        return pd.DataFrame(), unmapped_actionable
    opeid_series = mapped.get("opeid8", pd.Series(dtype="string")).apply(standardize_opeid8).astype("string")
    valid_mask = opeid_series.notna()
    out = pd.DataFrame()
    out["opeid8"] = opeid_series[valid_mask].reset_index(drop=True)
    if out.empty:
        return out, unmapped_actionable
    out["opeid6"] = out["opeid8"].apply(derive_opeid6).astype("string")
    out["award_year"] = pd.Series([entry["award_year"]] * len(out), dtype="string")
    out["award_year_start"] = pd.Series([int(entry["award_year_start"])] * len(out), dtype="Int64")
    out["award_year_end"] = pd.Series([int(entry["award_year_end"])] * len(out), dtype="Int64")

    prefix = component_prefix(family)
    for descriptor in ("school", "state", "zip_code", "school_type"):
        series = mapped.get(descriptor)
        if series is None:
            continue
        series = series[valid_mask].reset_index(drop=True)
        if descriptor == "state":
            out[f"{prefix}{descriptor}"] = format_string_series(series, formatter="upper")
        elif descriptor == "school_type":
            out[f"{prefix}{descriptor}"] = format_string_series(series, formatter="title")
        elif descriptor == "zip_code":
            out[f"{prefix}{descriptor}"] = format_zip_series(series)
        else:
            out[f"{prefix}{descriptor}"] = format_string_series(series)

    measure_columns = [col for col in mapped.columns if col not in {"opeid8", "school", "state", "zip_code", "school_type"}]
    for measure in measure_columns:
        series = mapped[measure][valid_mask].reset_index(drop=True)
        out[f"{prefix}{measure}"] = format_integer_series(series)
    out = out.sort_values(["opeid8", "award_year"]).reset_index(drop=True)
    return out, unmapped_actionable


def panel_file_name(stem: str, entries: Sequence[dict]) -> str:
    starts = sorted(int(entry["award_year_start"]) for entry in entries)
    ends = sorted(int(entry["award_year_end"]) for entry in entries)
    return f"{stem}_{starts[0]}_{ends[-1]}.parquet"


def assert_unique_panel_keys(frame: pd.DataFrame, label: str) -> None:
    duplicate_mask = frame.duplicated(["opeid8", "award_year"], keep=False)
    if duplicate_mask.any():
        raise SystemExit(f"{label} contains duplicate (opeid8, award_year) keys.")


def build_component_panel(root: str | Path | None, family: str) -> Path:
    layout = ensure_data_layout(root)
    dictionary_map = load_dictionary_map(layout)
    entries = load_selected_panel_entries(layout, family=family)
    if not entries:
        raise SystemExit(f"No selected panel entries found for {family}.")
    year_frames: list[pd.DataFrame] = []
    summary_rows: list[dict] = []
    branch_rows: list[dict] = []
    unmapped_rows: list[dict] = []
    for entry in entries:
        workbook_path = Path(entry["local_path"])
        parse_result = parse_selected_sheet(workbook_path, family, entry["period_type"])
        panel_frame, unmapped = prepare_component_panel_frame(family, entry, parse_result, dictionary_map)
        unmapped_rows.extend(
            [
                {
                    **row,
                    "filename": entry["filename"],
                    "award_year": entry["award_year"],
                }
                for row in unmapped
            ]
        )
        if panel_frame.empty:
            continue
        assert_unique_panel_keys(panel_frame, f"{family} {entry['award_year']}")
        year_path = component_cross_sections_dir(layout, family) / f"panel_{family}_{int(entry['award_year_start'])}.parquet"
        panel_frame.to_parquet(year_path, index=False)
        year_frames.append(panel_frame)
        branch_count = int((panel_frame["opeid8"].astype("string").str[-2:] != "00").sum())
        branch_rows.append(
            {
                "family": family,
                "award_year": entry["award_year"],
                "rows": int(len(panel_frame)),
                "branch_opeid_rows": branch_count,
            }
        )
        summary_rows.append(
            {
                "family": family,
                "award_year": entry["award_year"],
                "rows": int(len(panel_frame)),
                "columns": int(len(panel_frame.columns)),
                "branch_opeid_rows": branch_count,
            }
        )
    if unmapped_rows:
        pd.DataFrame(unmapped_rows).to_csv(
            layout.checks / "panel_qc" / f"{family}_unmapped_actionable_headers.csv",
            index=False,
        )
        raise SystemExit(f"Unmapped actionable headers encountered while building {family}.")
    stitched = pd.concat(year_frames, ignore_index=True) if year_frames else pd.DataFrame()
    if stitched.empty:
        raise SystemExit(f"No stitched rows produced for {family}.")
    assert_unique_panel_keys(stitched, f"{family} stitched panel")
    if family == "grants":
        filename = panel_file_name("panel_grant_volume", entries)
    elif family == "campus_based":
        filename = panel_file_name("panel_campus_based_volume", entries)
    elif family == "direct_loans":
        filename = panel_file_name("panel_direct_loan_volume", entries)
    else:
        filename = panel_file_name("panel_ffel_loan_volume", entries)
    output_path = component_panel_dir(layout, family) / filename
    stitched.to_parquet(output_path, index=False)
    write_rows(
        layout.checks / "panel_qc" / f"{family}_year_summary.csv",
        summary_rows,
        ["family", "award_year", "rows", "columns", "branch_opeid_rows"],
    )
    write_rows(
        layout.checks / "panel_qc" / f"{family}_branch_opeid_summary.csv",
        branch_rows,
        ["family", "award_year", "rows", "branch_opeid_rows"],
    )
    return output_path


def locate_component_panel(layout: DataRootLayout, family: str) -> Path:
    patterns = {
        "grants": "panel_grant_volume_*.parquet",
        "campus_based": "panel_campus_based_volume_*.parquet",
        "direct_loans": "panel_direct_loan_volume_*.parquet",
        "ffel": "panel_ffel_loan_volume_*.parquet",
        "loans": "panel_loan_volume_*.parquet",
    }
    matches = sorted(component_panel_dir(layout, family).glob(patterns[family]))
    if not matches:
        raise SystemExit(f"Unable to locate component panel for {family}.")
    return matches[-1]


def coalesce_duplicate_metadata_columns(frame: pd.DataFrame, column_name: str) -> pd.DataFrame:
    left = f"{column_name}_x"
    right = f"{column_name}_y"
    if left in frame.columns and right in frame.columns:
        frame[column_name] = frame[left].combine_first(frame[right])
        frame = frame.drop(columns=[left, right])
    elif left in frame.columns:
        frame = frame.rename(columns={left: column_name})
    elif right in frame.columns:
        frame = frame.rename(columns={right: column_name})
    return frame


def outer_merge_panels(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    merged = left.merge(right, on=["opeid8", "award_year"], how="outer")
    for column in ("opeid6", "award_year_start", "award_year_end"):
        merged = coalesce_duplicate_metadata_columns(merged, column)
    return merged


def merge_loan_panels(root: str | Path | None = None) -> Path:
    layout = ensure_data_layout(root)
    direct = pd.read_parquet(locate_component_panel(layout, "direct_loans"))
    ffel = pd.read_parquet(locate_component_panel(layout, "ffel"))
    merged = outer_merge_panels(direct, ffel)
    assert_unique_panel_keys(merged, "merged loan panel")
    entries = load_selected_panel_entries(layout, family="direct_loans") + load_selected_panel_entries(layout, family="ffel")
    output_path = component_panel_dir(layout, "direct_loans") / panel_file_name("panel_loan_volume", entries)
    merged.to_parquet(output_path, index=False)
    return output_path


def coalesce_columns(frame: pd.DataFrame, columns: Sequence[str], *, formatter: str | None = None) -> pd.Series:
    series = pd.Series([pd.NA] * len(frame), dtype="string")
    for column in columns:
        if column not in frame.columns:
            continue
        candidate = frame[column]
        if formatter == "state":
            candidate = format_string_series(candidate, formatter="upper")
        elif formatter == "school_type":
            candidate = format_string_series(candidate, formatter="title")
        elif formatter == "zip_code":
            candidate = format_zip_series(candidate)
        else:
            candidate = format_string_series(candidate)
        series = series.combine_first(candidate)
    return series


def descriptor_conflicts(frame: pd.DataFrame, raw_descriptor_columns: Sequence[str], label: str) -> pd.DataFrame:
    rows: list[dict] = []
    for _, row in frame.iterrows():
        values = []
        for column in raw_descriptor_columns:
            if column not in frame.columns:
                continue
            value = row[column]
            if pd.notna(value) and str(value).strip():
                values.append(str(value).strip())
        unique_values = sorted(set(values))
        if len(unique_values) > 1:
            rows.append(
                {
                    "opeid8": row["opeid8"],
                    "award_year": row["award_year"],
                    "descriptor": label,
                    "values": " | ".join(unique_values),
                }
            )
    return pd.DataFrame(rows)


def merge_final_panels(root: str | Path | None = None) -> tuple[Path, Path]:
    layout = ensure_data_layout(root)
    grant = pd.read_parquet(locate_component_panel(layout, "grants"))
    campus = pd.read_parquet(locate_component_panel(layout, "campus_based"))
    loans = pd.read_parquet(locate_component_panel(layout, "loans"))
    raw = outer_merge_panels(outer_merge_panels(grant, campus), loans)
    assert_unique_panel_keys(raw, "final raw panel")
    span_entries = (
        load_selected_panel_entries(layout, family="grants")
        + load_selected_panel_entries(layout, family="campus_based")
        + load_selected_panel_entries(layout, family="direct_loans")
        + load_selected_panel_entries(layout, family="ffel")
    )
    raw_path = layout.panels / "final" / panel_file_name("fsa_volume_reports_raw", span_entries)
    raw.to_parquet(raw_path, index=False)

    clean = raw.copy()
    clean["school"] = coalesce_columns(
        clean,
        ["grant__school", "campus__school", "loan_direct__school", "loan_ffel__school"],
    )
    clean["state"] = coalesce_columns(
        clean,
        ["grant__state", "campus__state", "loan_direct__state", "loan_ffel__state"],
        formatter="state",
    )
    clean["zip_code"] = coalesce_columns(
        clean,
        ["grant__zip_code", "campus__zip_code", "loan_direct__zip_code", "loan_ffel__zip_code"],
        formatter="zip_code",
    )
    clean["school_type"] = coalesce_columns(
        clean,
        ["grant__school_type", "campus__school_type", "loan_direct__school_type", "loan_ffel__school_type"],
        formatter="school_type",
    )
    assert_unique_panel_keys(clean, "final clean panel")
    clean_path = layout.panels / "final" / panel_file_name("fsa_volume_reports_clean", span_entries)
    clean.to_parquet(clean_path, index=False)

    conflict_frames = [
        descriptor_conflicts(raw, ["grant__school", "campus__school", "loan_direct__school", "loan_ffel__school"], "school"),
        descriptor_conflicts(raw, ["grant__state", "campus__state", "loan_direct__state", "loan_ffel__state"], "state"),
        descriptor_conflicts(raw, ["grant__zip_code", "campus__zip_code", "loan_direct__zip_code", "loan_ffel__zip_code"], "zip_code"),
        descriptor_conflicts(raw, ["grant__school_type", "campus__school_type", "loan_direct__school_type", "loan_ffel__school_type"], "school_type"),
    ]
    conflicts = pd.concat([frame for frame in conflict_frames if not frame.empty], ignore_index=True) if any(
        not frame.empty for frame in conflict_frames
    ) else pd.DataFrame(columns=["opeid8", "award_year", "descriptor", "values"])
    conflicts.to_csv(layout.checks / "panel_qc" / "final_descriptor_conflicts.csv", index=False)
    return raw_path, clean_path


def build_panel_dictionary(
    root: str | Path | None = None,
    *,
    input_path: str | Path | None = None,
    output_csv: str | Path | None = None,
    output_parquet: str | Path | None = None,
) -> tuple[Path, Path]:
    layout = ensure_data_layout(root)
    if input_path:
        panel_path = Path(input_path)
    else:
        matches = sorted((layout.panels / "final").glob("fsa_volume_reports_clean_*.parquet"))
        if not matches:
            raise SystemExit("No final clean panel found for panel dictionary build.")
        panel_path = matches[-1]
    dictionary = pd.read_parquet(layout.dictionary / "fsa_volume_dictionary.parquet")
    panel = pd.read_parquet(panel_path)
    rows = []
    for column in panel.columns:
        if column in {"opeid8", "opeid6", "award_year", "award_year_start", "award_year_end", "school", "state", "zip_code", "school_type"}:
            rows.append(
                {
                    "panel_column": column,
                    "component_family": "synthetic" if column in {"school", "state", "zip_code", "school_type"} else "key",
                    "canonical_column": column,
                    "mapping_status": "synthetic_coalesced" if column in {"school", "state", "zip_code", "school_type"} else "panel_key",
                    "source_filename": "",
                    "sheet_name": "",
                    "first_year": int(panel["award_year_start"].min()) if "award_year_start" in panel.columns else pd.NA,
                    "last_year": int(panel["award_year_end"].max()) if "award_year_end" in panel.columns else pd.NA,
                }
            )
            continue
    # Build rows deterministically without relying on fragile vector matching.
    mapped_rows = []
    for _, row in dictionary.iterrows():
        canonical = str(row["canonical_column"] or "")
        if not canonical:
            continue
        for family in COMPONENT_FAMILIES:
            prefix = component_prefix(family)
            panel_column = f"{prefix}{canonical}"
            if panel_column in panel.columns:
                mapped_rows.append(
                    {
                        "panel_column": panel_column,
                        **row.to_dict(),
                    }
                )
    rows.extend(mapped_rows)
    out = pd.DataFrame(rows).drop_duplicates().sort_values(["panel_column", "component_family"]).reset_index(drop=True)
    csv_path = Path(output_csv) if output_csv else layout.dictionary / "fsa_volume_panel_dictionary.csv"
    parquet_path = Path(output_parquet) if output_parquet else layout.dictionary / "fsa_volume_panel_dictionary.parquet"
    out.to_csv(csv_path, index=False)
    out.to_parquet(parquet_path, index=False)
    return csv_path, parquet_path


def source_qaqc(root: str | Path | None = None) -> pd.DataFrame:
    layout = ensure_data_layout(root)
    selected_path = selected_panel_files_path(layout)
    profile_path = layout.checks / "source_qc" / "workbook_profiles.csv"
    results: list[dict] = []
    selected_exists = selected_path.exists()
    results.append({"check": "selected_panel_files_exists", "passed": selected_exists, "details": str(selected_path)})
    if selected_exists:
        selected = pd.read_csv(selected_path, dtype=str).fillna("")
        missing_files = selected[~selected["local_path"].apply(lambda p: Path(p).exists())]
        results.append(
            {
                "check": "selected_files_exist",
                "passed": missing_files.empty,
                "details": "" if missing_files.empty else f"missing={len(missing_files)}",
            }
        )
    else:
        selected = pd.DataFrame()
        results.append({"check": "selected_files_exist", "passed": False, "details": "selected_panel_files.csv missing"})
    profile_exists = profile_path.exists()
    results.append({"check": "workbook_profiles_exists", "passed": profile_exists, "details": str(profile_path)})
    if profile_exists and not selected.empty:
        profiles = pd.read_csv(profile_path, dtype=str).fillna("")
        profiled = selected.merge(
            profiles[["family", "filename", "selected_sheet", "parse_warnings_json"]],
            on=["family", "filename"],
            how="left",
        )
        missing_sheet = profiled["selected_sheet"].eq("")
        results.append(
            {
                "check": "selected_sheet_found_for_selected_files",
                "passed": not bool(missing_sheet.any()),
                "details": "" if not bool(missing_sheet.any()) else f"missing={int(missing_sheet.sum())}",
            }
        )
        year_gap_rows = []
        for family, group in selected.groupby("family"):
            years = sorted(group["award_year_start"].astype(int).unique().tolist())
            expected = list(range(years[0], years[-1] + 1))
            gaps = [year for year in expected if year not in years]
            if gaps:
                year_gap_rows.append({"family": family, "gaps": ",".join(str(year) for year in gaps)})
        results.append(
            {
                "check": "selected_years_contiguous_within_family",
                "passed": len(year_gap_rows) == 0,
                "details": "" if not year_gap_rows else json.dumps(year_gap_rows),
            }
        )
    else:
        results.append({"check": "selected_sheet_found_for_selected_files", "passed": False, "details": "profiles missing"})
        results.append({"check": "selected_years_contiguous_within_family", "passed": False, "details": "profiles or selected files missing"})
    out = pd.DataFrame(results)
    out.to_csv(layout.checks / "source_qc" / "source_qaqc_summary.csv", index=False)
    return out


def summarize_panel(path: Path) -> dict:
    frame = pd.read_parquet(path)
    duplicate_keys = int(frame.duplicated(["opeid8", "award_year"]).sum()) if {"opeid8", "award_year"}.issubset(frame.columns) else pd.NA
    return {
        "path": str(path),
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "duplicate_keys": duplicate_keys,
        "min_award_year_start": int(frame["award_year_start"].min()) if "award_year_start" in frame.columns else pd.NA,
        "max_award_year_end": int(frame["award_year_end"].max()) if "award_year_end" in frame.columns else pd.NA,
    }


def panel_qaqc(root: str | Path | None = None) -> pd.DataFrame:
    layout = ensure_data_layout(root)
    panel_paths = [
        locate_component_panel(layout, "grants"),
        locate_component_panel(layout, "campus_based"),
        locate_component_panel(layout, "direct_loans"),
        locate_component_panel(layout, "ffel"),
        locate_component_panel(layout, "loans"),
    ]
    panel_paths.extend(sorted((layout.panels / "final").glob("fsa_volume_reports_*.parquet")))
    rows = [summarize_panel(path) for path in panel_paths if path.exists()]
    summary = pd.DataFrame(rows)
    summary.to_csv(layout.checks / "panel_qc" / "panel_qaqc_summary.csv", index=False)

    coverage_rows = []
    for path in panel_paths:
        if not path.exists():
            continue
        frame = pd.read_parquet(path)
        if "award_year" not in frame.columns:
            continue
        counts = frame["award_year"].value_counts().sort_index()
        for award_year, count in counts.items():
            coverage_rows.append({"panel": path.name, "award_year": award_year, "rows": int(count)})
    pd.DataFrame(coverage_rows).to_csv(layout.checks / "panel_qc" / "panel_coverage_matrix.csv", index=False)
    return summary


def acceptance_audit(root: str | Path | None = None) -> pd.DataFrame:
    layout = ensure_data_layout(root)
    results: list[dict] = []

    source_summary_path = layout.checks / "source_qc" / "source_qaqc_summary.csv"
    results.append(
        {
            "check": "source_qaqc_summary_exists",
            "passed": source_summary_path.exists(),
            "details": str(source_summary_path),
        }
    )
    if source_summary_path.exists():
        source_summary = pd.read_csv(source_summary_path)
        for row in source_summary.to_dict("records"):
            results.append(
                {
                    "check": f"source::{row['check']}",
                    "passed": bool(row["passed"]),
                    "details": row.get("details", ""),
                }
            )

    dictionary_summary_path = layout.checks / "dictionary_qc" / "dictionary_qaqc_summary.csv"
    results.append(
        {
            "check": "dictionary_qaqc_summary_exists",
            "passed": dictionary_summary_path.exists(),
            "details": str(dictionary_summary_path),
        }
    )
    if dictionary_summary_path.exists():
        dictionary_summary = pd.read_csv(dictionary_summary_path)
        unmapped = int(
            dictionary_summary.loc[dictionary_summary["metric"] == "unmapped_actionable_rows", "value"].astype(int).sum()
        )
        results.append(
            {
                "check": "dictionary_has_no_unmapped_actionable_headers",
                "passed": unmapped == 0,
                "details": f"unmapped_actionable_rows={unmapped}",
            }
        )

    panel_summary_path = layout.checks / "panel_qc" / "panel_qaqc_summary.csv"
    results.append({"check": "panel_qaqc_summary_exists", "passed": panel_summary_path.exists(), "details": str(panel_summary_path)})
    if panel_summary_path.exists():
        panel_summary = pd.read_csv(panel_summary_path)
        duplicate_failures = int(panel_summary["duplicate_keys"].fillna(0).astype(int).sum())
        results.append(
            {
                "check": "no_duplicate_panel_keys",
                "passed": duplicate_failures == 0,
                "details": f"duplicate_keys={duplicate_failures}",
            }
        )

    conflict_path = layout.checks / "panel_qc" / "final_descriptor_conflicts.csv"
    results.append({"check": "descriptor_conflict_artifact_exists", "passed": conflict_path.exists(), "details": str(conflict_path)})
    if conflict_path.exists():
        conflicts = pd.read_csv(conflict_path)
        results.append(
            {
                "check": "descriptor_conflicts_are_auditable",
                "passed": True,
                "details": f"conflict_rows={len(conflicts)}",
            }
        )

    selected_path = selected_panel_files_path(layout)
    if selected_path.exists():
        selected = pd.read_csv(selected_path, dtype=str).fillna("")
        family_to_panel = {
            "grants": locate_component_panel(layout, "grants"),
            "campus_based": locate_component_panel(layout, "campus_based"),
            "direct_loans": locate_component_panel(layout, "direct_loans"),
            "ffel": locate_component_panel(layout, "ffel"),
        }
        for family, panel_path in family_to_panel.items():
            panel = pd.read_parquet(panel_path)
            expected_years = sorted(selected.loc[selected["family"] == family, "award_year"].unique().tolist())
            actual_years = sorted(panel["award_year"].dropna().astype(str).unique().tolist())
            results.append(
                {
                    "check": f"{family}::year_coverage_matches_selected_files",
                    "passed": expected_years == actual_years,
                    "details": f"expected={expected_years} actual={actual_years}",
                }
            )

    acceptance = pd.DataFrame(results)
    out_csv = layout.checks / "acceptance_qc" / "acceptance_summary.csv"
    acceptance.to_csv(out_csv, index=False)
    passed = int(acceptance["passed"].astype(bool).sum())
    failed = int((~acceptance["passed"].astype(bool)).sum())
    md_lines = [
        "# Acceptance Audit",
        "",
        f"- Checks passed: `{passed}`",
        f"- Checks failed: `{failed}`",
        "",
        "| Check | Passed | Details |",
        "| --- | --- | --- |",
    ]
    for row in acceptance.to_dict("records"):
        md_lines.append(f"| {row['check']} | {bool(row['passed'])} | {row.get('details', '')} |")
    (layout.checks / "acceptance_qc" / "acceptance_summary.md").write_text("\n".join(md_lines), encoding="utf-8")
    return acceptance
