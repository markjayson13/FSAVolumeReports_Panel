from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from helpers import run_script, write_workbook


def grant_annual_rows(branch_opeid: str, school: str) -> list[list[object]]:
    return [
        ["2005-2006 Grant Volume by School"],
        ["Award Year Cumulative Activity Through June 30, 2006"],
        [],
        [],
        ["", "", "", "", "FEDERAL PELL GRANT PROGRAM", ""],
        ["OPE ID", "School", "State", "School Type", "Recipients", "Total Disbursed"],
        [branch_opeid, school, "AL", "Public", "100", "500000"],
        ["00105900", "LAWSON STATE COMMUNITY COLLEGE", "AL", "Public", "200", "700000"],
    ]


def grant_q4_rows() -> list[list[object]]:
    return [
        ["2006-2007 Award Year Grant Volume by School"],
        ["Award Year Cumulative Activity through Quarter ending June 30, 2007"],
        [],
        ["", "", "", "", "", "FEDERAL PELL GRANT PROGRAM", "", "ACADEMIC COMPETITIVENESS", ""],
        ["OPE ID", "School", "State", "Zip Code", "School Type", "YTD Recipients", "YTD Disbursements", "YTD Recipients", "YTD Disbursements"],
        ["00105901", "LAWSON STATE COMMUNITY COLLEGE - BESSEMER CAMPUS", "AL", "35224", "Public", "110", "550000", "5", "10000"],
    ]


def campus_rows(label: str) -> list[list[object]]:
    return [
        [f"{label} Award Year Campus-Based Program Data by School"],
        [],
        ["", "", "", "", "", "FEDERAL WORK-STUDY", "", "", "PERKINS LOAN", "", "", "FEDERAL SUPPLEMENTAL EDUCATIONAL OPPORTUNITY GRANTS", "", ""],
        ["OPE ID", "School", "State", "Zip Code", "School Type", "Recipients", "$ Federal Award", "Disbursements", "Recipients", "$ Federal Award", "Disbursements", "Recipients", "$ Federal Award", "Disbursements"],
        ["00105900", "LAWSON STATE COMMUNITY COLLEGE", "AL", "35224", "Public", "25", "25000", "20000", "10", "10000", "8000", "30", "15000", "12000"],
    ]


def loan_annual_rows(title: str, prefix: str, opeid: str) -> list[list[object]]:
    return [
        [title],
        ["Award Year Cumulative Activity"],
        [],
        [],
        ["", "", "", "", "", f"{prefix} SUBSIDIZED", "", "", "", "", f"{prefix} UNSUBSIDIZED", "", "", "", "", f"{prefix} PLUS", "", "", "", ""],
        ["OPE ID", "School", "State", "Zip Code", "School Type", "Recipients", "# of Loans Originated", "$ of Loans Originated", "# of Disbursements", "$ of Disbursements", "Recipients", "# of Loans Originated", "$ of Loans Originated", "# of Disbursements", "$ of Disbursements", "Recipients", "# of Loans Originated", "$ of Loans Originated", "# of Disbursements", "$ of Disbursements"],
        [opeid, "RUTGERS", "NJ", "08901", "Public", "10", "12", "1000", "12", "1000", "20", "22", "2000", "22", "2000", "5", "5", "1500", "5", "1500"],
    ]


class PipelineIntegrationTests(unittest.TestCase):
    def test_offline_pipeline_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_dir = tmp_path / "source"
            root = tmp_path / "fsa-root"

            grant_annual = write_workbook(source_dir / "AY2005-06Pell.xlsx", {"AY 2005-2006": grant_annual_rows("00105901", "LAWSON STATE COMMUNITY COLLEGE - BESSEMER CAMPUS"), "Field Definitions": [["Definitions"]]})
            grant_q4 = write_workbook(source_dir / "Q40607AY.xlsx", {"Q4 0607 YTD": grant_q4_rows(), "Field Definitions": [["Definitions"]]})
            grant_q3 = write_workbook(source_dir / "Q30607AY.xlsx", {"Q3 0607 YTD": grant_q4_rows(), "Field Definitions": [["Definitions"]]})

            campus_2001 = write_workbook(source_dir / "CBDashboard0102.xlsx", {"AY2001-02": campus_rows("2001-2002"), "Field Definitions": [["Definitions"]]})
            campus_2002 = write_workbook(source_dir / "CBDashboard0203.xlsx", {"AY2002-03": campus_rows("2002-2003"), "Field Definitions": [["Definitions"]]})

            direct_1999 = write_workbook(source_dir / "DL_AwardYr_Summary_AY1999_2000_All.xlsx", {"AY1999-2000": loan_annual_rows("1999-2000 Award Year Direct Loan Volume by School", "DL", "00262923"), "Field Definitions": [["Definitions"]]})
            direct_2000 = write_workbook(source_dir / "DL_AwardYr_Summary_AY2000_2001_All.xlsx", {"AY2000-2001": loan_annual_rows("2000-2001 Award Year Direct Loan Volume by School", "DL", "00262923"), "Field Definitions": [["Definitions"]]})
            direct_q2_2025 = write_workbook(source_dir / "dl-dashboard-ay2025-2026-q2.xlsx", {"Award Year Summary": loan_annual_rows("2025-2026 Award Year Direct Loan Volume by School", "DL", "00262923"), "Definitions": [["Definitions"]]})

            ffel_1999 = write_workbook(source_dir / "FFEL_AwardYr_Summary_AY1999_2000_All.xlsx", {"AY1999-2000": loan_annual_rows("1999-2000 Award Year FFEL Volume by School", "FFEL", "00262923"), "Field Definitions": [["Definitions"]]})
            ffel_2000 = write_workbook(source_dir / "FFEL_AwardYr_Summary_AY2000_2001_All.xlsx", {"AY2000-2001": loan_annual_rows("2000-2001 Award Year FFEL Volume by School", "FFEL", "00262923"), "Field Definitions": [["Definitions"]]})

            html = f"""
            <html><body>
              <a href="{grant_annual.as_uri()}">AY 2005-2006</a>
              <a href="{grant_q4.as_uri()}">AY 2006-2007, Q4</a>
              <a href="{grant_q3.as_uri()}">AY 2006-2007, Q3</a>

              <a href="{campus_2001.as_uri()}">AY 2001-2002</a>
              <a href="{campus_2002.as_uri()}">AY 2002-2003</a>

              <a href="{direct_1999.as_uri()}">AY 1999-2000</a>
              <a href="{direct_2000.as_uri()}">AY 2000-2001</a>
              <a href="{direct_q2_2025.as_uri()}">AY 2025-2026 Q2</a>

              <a href="{ffel_1999.as_uri()}">AY 1999-2000</a>
              <a href="{ffel_2000.as_uri()}">AY 2000-2001</a>
            </body></html>
            """
            html_path = tmp_path / "title_iv_page.html"
            html_path.write_text(html, encoding="utf-8")

            stages = [
                ("Scripts/01_download_title_iv_reports.py", "--root", root, "--page-html", html_path, "--no-strict-source-checks"),
                ("Scripts/02_profile_workbooks.py", "--root", root),
                ("Scripts/03_build_dictionary.py", "--root", root),
                ("Scripts/04_panelize_grants.py", "--root", root),
                ("Scripts/05_panelize_campus_based.py", "--root", root),
                ("Scripts/06_panelize_loans.py", "--root", root),
                ("Scripts/07_merge_fsa_panels.py", "--root", root),
                ("Scripts/08_build_panel_dictionary.py", "--root", root),
                ("Scripts/09_build_manual_review_workbook.py", "--root", root),
                ("Scripts/QA_QC/00_source_qaqc.py", "--root", root),
                ("Scripts/QA_QC/01_panel_qaqc.py", "--root", root),
                ("Scripts/QA_QC/02_acceptance_audit.py", "--root", root),
            ]
            for stage in stages:
                result = run_script(stage[0], *stage[1:], timeout=120)
                self.assertEqual(result.returncode, 0, msg=f"{stage[0]} failed:\n{result.stdout}")

            grant_panel_path = next((root / "Panels" / "grants").glob("panel_grant_volume_*.parquet"))
            grant_panel = pd.read_parquet(grant_panel_path)
            self.assertIn("00105901", grant_panel["opeid8"].astype(str).tolist())
            self.assertEqual(int(grant_panel.duplicated(["opeid8", "award_year"]).sum()), 0)

            final_clean_path = next((root / "Panels" / "final").glob("fsa_volume_reports_clean_*.parquet"))
            final_clean = pd.read_parquet(final_clean_path)
            self.assertEqual(int(final_clean.duplicated(["opeid8", "award_year"]).sum()), 0)
            self.assertIn("school", final_clean.columns)
            self.assertIn("grant__pell_recipients", final_clean.columns)
            self.assertIn("loan_direct__subsidized_recipients", final_clean.columns)

            acceptance = pd.read_csv(root / "Checks" / "acceptance_qc" / "acceptance_summary.csv")
            self.assertTrue(bool(acceptance["passed"].all()))
            self.assertTrue((root / "Checks" / "panel_qc" / "final_descriptor_manual_review.csv").exists())
            self.assertTrue((root / "Checks" / "panel_qc" / "final_descriptor_resolution_summary.csv").exists())
            self.assertTrue((root / "Checks" / "panel_qc" / "manual_review_package" / "final_descriptor_manual_review_workbook.xlsx").exists())
            self.assertTrue((root / "Checks" / "panel_qc" / "manual_review_package" / "priority_manual_review_workbook.xlsx").exists())


if __name__ == "__main__":
    unittest.main()
