#!/usr/bin/env python3
"""
Export the canonical analysis-ready final panel to a legacy `.xls` workbook.

Because legacy Excel workbooks only support 65,536 rows per sheet, the export
is split across multiple `part_##` sheets. The script writes a temporary `.xlsx`
workbook first and then converts it to a true `.xls` using LibreOffice.
"""
from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
from openpyxl import Workbook

from fsa_build_utils import data_layout, locate_analysis_ready_final_panel

XLS_MAX_ROWS = 65_536
XLS_MAX_COLUMNS = 256
DATA_ROWS_PER_SHEET = XLS_MAX_ROWS - 1


def excel_safe_value(value: object) -> object:
    if pd.isna(value):
        return None
    scalar = getattr(value, "item", None)
    if callable(scalar):
        try:
            return scalar()
        except Exception:
            return value
    return value


def export_legacy_xls(
    input_parquet: Path,
    output_xls: Path,
    max_rows_per_sheet: int = DATA_ROWS_PER_SHEET,
) -> tuple[Path, int, int, int]:
    frame = pd.read_parquet(input_parquet)
    if len(frame.columns) > XLS_MAX_COLUMNS:
        raise ValueError("The research master exceeds legacy XLS's 256-column limit. Use canonical Parquet or an explicitly selected research extract; no columns will be silently truncated.")
    output_xls.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="fsa-legacy-xls-") as tmpdir_name:
        tmpdir = Path(tmpdir_name)
        staging_xlsx = tmpdir / f"{output_xls.stem}.xlsx"
        converted_xls = tmpdir / output_xls.name

        workbook = Workbook(write_only=True)
        total_rows = len(frame)
        total_sheets = max(1, math.ceil(total_rows / max_rows_per_sheet))
        header = list(frame.columns)

        for index in range(total_sheets):
            start = index * max_rows_per_sheet
            stop = min(start + max_rows_per_sheet, total_rows)
            sheet = workbook.create_sheet(title=f"part_{index + 1:02d}")
            sheet.append(header)
            for row in frame.iloc[start:stop].itertuples(index=False, name=None):
                sheet.append([excel_safe_value(value) for value in row])

        workbook.save(staging_xlsx)

        subprocess.run(
            [
                "soffice",
                "--headless",
                "--convert-to",
                "xls:MS Excel 97",
                "--outdir",
                str(tmpdir),
                str(staging_xlsx),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if not converted_xls.exists():
            raise FileNotFoundError(f"LibreOffice did not produce expected file: {converted_xls}")

        shutil.move(str(converted_xls), str(output_xls))

    return output_xls, total_rows, len(frame.columns), total_sheets


def default_output_path(input_parquet: Path) -> Path:
    return input_parquet.with_suffix(".xls")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="External FSA_ROOT")
    ap.add_argument("--input-parquet", default=None, help="Canonical analysis-ready panel parquet")
    ap.add_argument("--output-xls", default=None, help="Legacy XLS output path")
    ap.add_argument(
        "--max-rows-per-sheet",
        type=int,
        default=DATA_ROWS_PER_SHEET,
        help=f"Maximum data rows per sheet (default: {DATA_ROWS_PER_SHEET})",
    )
    args = ap.parse_args()

    layout = data_layout(args.root)
    input_parquet = Path(args.input_parquet) if args.input_parquet else locate_analysis_ready_final_panel(layout)
    if input_parquet is None:
        raise FileNotFoundError("Could not locate the canonical analysis-ready final panel.")
    output_xls = Path(args.output_xls) if args.output_xls else default_output_path(input_parquet)

    written_path, row_count, column_count, sheet_count = export_legacy_xls(
        input_parquet=input_parquet,
        output_xls=output_xls,
        max_rows_per_sheet=args.max_rows_per_sheet,
    )
    print(f"Wrote legacy XLS: {written_path}")
    print(f"Rows: {row_count}")
    print(f"Columns: {column_count}")
    print(f"Sheets: {sheet_count}")


if __name__ == "__main__":
    main()
