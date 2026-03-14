from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import load_script_module, write_workbook


utils = load_script_module("fsa_build_utils_workbook", "Scripts/fsa_build_utils.py")


class WorkbookParsingTests(unittest.TestCase):
    def test_parse_selected_sheet_prefers_summary_for_quarterly_workbooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workbook_path = Path(tmp) / "dl-dashboard-ay2024-2025-q4.xlsx"
            write_workbook(
                workbook_path,
                {
                    "Quarterly Activity": [
                        ["2024-2025 Award Year Direct Loan Volume by School"],
                        ["Award Year Quarterly Activity"],
                        [],
                        ["", "", "", "", "DL SUBSIDIZED", "", "", "", "", "", "DL UNSUBSIDIZED - UNDERGRADUATE", ""],
                        ["OPE ID", "School", "State", "Zip Code", "Recipients", "# of Loans Originated", "$ of Loans Originated", "# of Disbursements", "$ of Disbursements", "", "Recipients", "# of Loans Originated"],
                        ["00262923", "RUTGERS", "NJ", "08901", "10", "12", "1000", "12", "1000", "", "20", "22"],
                    ],
                    "Award Year Summary": [
                        ["2024-2025 Award Year Direct Loan Volume by School"],
                        ["Award Year Cumulative Activity through Quarter ending (6/30/2025)"],
                        [],
                        [],
                        ["", "", "", "", "DL SUBSIDIZED", "", "", "", "", "DL UNSUBSIDIZED - UNDERGRADUATE", "", "", "", ""],
                        ["OPE ID", "School", "State", "Zip Code", "School Type", "Recipients", "# of Loans Originated", "$ of Loans Originated", "# of Disbursements", "$ of Disbursements", "Recipients", "# of Loans Originated", "$ of Loans Originated", "# of Disbursements", "$ of Disbursements"],
                        ["00262923", "RUTGERS", "NJ", "08901", "Public", "10", "12", "1000", "12", "1000", "20", "22", "2000", "22", "2000"],
                    ],
                    "Definitions": [["Definitions"]],
                },
            )
            result = utils.parse_selected_sheet(workbook_path, "direct_loans", "quarterly")
            self.assertEqual(result.selected_sheet, "Award Year Summary")
            self.assertIn("DL SUBSIDIZED | # of Loans Originated", result.flattened_headers)
            self.assertIn("DL UNSUBSIDIZED - UNDERGRADUATE | $ of Disbursements", result.flattened_headers)
            self.assertEqual(
                utils.canonicalize_component_header("direct_loans", "DL UNSUBSIDIZED - UNDERGRADUATE | # of Loans Originated"),
                "unsubsidized_undergraduate_loans_originated_n",
            )
            self.assertEqual(
                utils.canonicalize_component_header("direct_loans", "DL SUBSIDIZED- GRADUATE | Recipients"),
                "subsidized_graduate_recipients",
            )

    def test_grant_header_mapping_and_opeid_standardization_preserve_branch_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workbook_path = Path(tmp) / "AY2005-06Pell.xlsx"
            write_workbook(
                workbook_path,
                {
                    "AY 2005-2006": [
                        ["2005-2006 Grant Volume by School"],
                        ["Award Year Cumulative Activity Through June 30, 2006"],
                        [],
                        [],
                        ["", "", "", "", "FEDERAL PELL GRANT PROGRAM", ""],
                        ["OPE ID", "School", "State", "School Type", "Recipients", "Total Disbursed"],
                        ["00105901", "LAWSON STATE COMMUNITY COLLEGE - BESSEMER CAMPUS", "AL", "Public", "100", "500000"],
                    ],
                    "Field Definitions": [["Definitions"]],
                },
            )
            result = utils.parse_selected_sheet(workbook_path, "grants", "annual")
            self.assertIn("FEDERAL PELL GRANT PROGRAM | Recipients", result.flattened_headers)
            self.assertEqual(
                utils.canonicalize_component_header("grants", "FEDERAL PELL GRANT PROGRAM | Total Disbursed"),
                "pell_disbursements",
            )
            self.assertEqual(utils.standardize_opeid8("00105901"), "00105901")
            self.assertEqual(utils.derive_opeid6("00105901"), "001059")

    def test_campus_old_layout_maps_to_expected_canonical_columns(self) -> None:
        self.assertEqual(
            utils.canonicalize_component_header("campus_based", "FEDERAL WORK-STUDY | $ Federal Award"),
            "fws_federal_award",
        )
        self.assertEqual(
            utils.canonicalize_component_header("campus_based", "FEDERAL SUPPLEMENTAL EDUCATIONAL OPPORTUNITY GRANTS | Disbursements"),
            "fseog_disbursements",
        )
        self.assertEqual(
            utils.canonicalize_component_header("campus_based", "FWS Recipents"),
            "fws_recipients",
        )
        self.assertEqual(
            utils.canonicalize_component_header("campus_based", "Perkins Loan Recipents"),
            "perkins_recipients",
        )
        self.assertIsNone(utils.standardize_opeid8("00000000"))
        self.assertIsNone(utils.standardize_opeid8("0"))

    def test_parse_selected_sheet_falls_back_to_html_table_disguised_as_xls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workbook_path = Path(tmp) / "Q11415AY.xls"
            workbook_path.write_text(
                """
                <html><body>
                <table>
                  <tr><td></td><td></td><td>FEDERAL PELL GRANT PROGRAM</td><td></td></tr>
                  <tr><td>OPE ID</td><td>School</td><td>Recipients</td><td>Total Disbursed</td></tr>
                  <tr><td>00105901</td><td>LAWSON STATE COMMUNITY COLLEGE - BESSEMER CAMPUS</td><td>100</td><td>500000</td></tr>
                </table>
                </body></html>
                """,
                encoding="utf-8",
            )
            result = utils.parse_selected_sheet(workbook_path, "grants", "quarterly")
            self.assertEqual(result.selected_sheet, "__html_table__")
            self.assertIn("FEDERAL PELL GRANT PROGRAM | Recipients", result.flattened_headers)
            self.assertTrue(any("html_table_fallback" in warning for warning in result.warnings))

    def test_parse_selected_sheet_returns_warning_for_plain_text_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workbook_path = Path(tmp) / "Q11415AY.xls"
            workbook_path.write_text(
                "File cleared temporarily to save space. Alternate solution in progress.\n",
                encoding="utf-8",
            )
            result = utils.parse_selected_sheet(workbook_path, "grants", "quarterly")
            self.assertTrue(result.frame.empty)
            self.assertEqual(result.selected_sheet, "")
            self.assertTrue(any("text_file_hint:" in warning for warning in result.warnings))
            self.assertTrue(any("excel_open_failed:" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
