from __future__ import annotations

import unittest
from collections import Counter
from pathlib import Path

from helpers import REPO_ROOT, load_script_module


utils = load_script_module("fsa_build_utils_download", "Scripts/fsa_build_utils.py")


class DownloadParserTests(unittest.TestCase):
    def test_parse_title_iv_json_discovers_expected_links(self) -> None:
        payload = {
            "mainContent": [
                {
                    "widgetType": "accordion",
                    "data": [
                        {
                            "widgetType": "accordion_item",
                            "title": "Grant Programs",
                            "data": [
                                {
                                    "widgetType": "list",
                                    "data": [
                                        {
                                            "widgetType": "anchor",
                                            "href": "/sites/default/files/AY2005-06Pell.xls",
                                            "value": "AY 2005-2006",
                                        },
                                        {
                                            "widgetType": "anchor",
                                            "href": "/sites/default/files/fsawg/datacenter/library/dl-dashboard-ay2024-2025-q4.xls",
                                            "value": "AY 2024-2025 Q4",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        rows = utils.parse_title_iv_json(payload, base_url="https://studentaid.gov/data-center/student/title-iv")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["family"], "grants")
        self.assertEqual(rows[1]["family"], "direct_loans")

    def test_parse_title_iv_entries_discovers_expected_families(self) -> None:
        html = (REPO_ROOT / "tests" / "fixtures" / "title_iv_page.html").read_text(encoding="utf-8")
        rows = utils.parse_title_iv_entries(html, base_url="https://studentaid.gov/data-center/student/title-iv")
        counts = Counter(row["family"] for row in rows)
        self.assertEqual(counts["grants"], 4)
        self.assertEqual(counts["campus_based"], 2)
        self.assertEqual(counts["direct_loans"], 3)
        self.assertEqual(counts["ffel"], 3)

    def test_selection_rules_only_keep_complete_panel_files(self) -> None:
        html = (REPO_ROOT / "tests" / "fixtures" / "title_iv_page.html").read_text(encoding="utf-8")
        rows = utils.annotate_panel_selection(utils.parse_title_iv_entries(html, base_url="https://studentaid.gov/data-center/student/title-iv"))
        lookup = {(row["family"], row["award_year"], str(row["quarter"])): row for row in rows}

        self.assertTrue(lookup[("grants", "2005-2006", "")]["selected_for_panel"])
        self.assertTrue(lookup[("grants", "2006-2007", "4")]["selected_for_panel"])
        self.assertFalse(lookup[("grants", "2006-2007", "3")]["selected_for_panel"])
        self.assertFalse(lookup[("grants", "2025-2026", "2")]["selected_for_panel"])

        self.assertTrue(lookup[("campus_based", "2001-2002", "")]["selected_for_panel"])
        self.assertTrue(lookup[("campus_based", "2023-2024", "")]["selected_for_panel"])

        self.assertTrue(lookup[("direct_loans", "1999-2000", "")]["selected_for_panel"])
        self.assertTrue(lookup[("direct_loans", "2024-2025", "4")]["selected_for_panel"])
        self.assertFalse(lookup[("direct_loans", "2025-2026", "2")]["selected_for_panel"])

        self.assertTrue(lookup[("ffel", "1999-2000", "")]["selected_for_panel"])
        self.assertTrue(lookup[("ffel", "2009-2010", "4")]["selected_for_panel"])
        self.assertFalse(lookup[("ffel", "2009-2010", "3")]["selected_for_panel"])

    def test_preflight_validation_flags_incomplete_fixture_scope(self) -> None:
        html = (REPO_ROOT / "tests" / "fixtures" / "title_iv_page.html").read_text(encoding="utf-8")
        rows = utils.annotate_panel_selection(utils.parse_title_iv_entries(html, base_url="https://studentaid.gov/data-center/student/title-iv"))
        validation = utils.validate_inventory_scope(rows)
        failed = validation.loc[~validation["passed"].astype(bool)]
        self.assertFalse(failed.empty)
        self.assertTrue(
            (
                (failed["component_family"] == "grants")
                & (failed["check"] == "selected_award_years_match_expected_scope")
            ).any()
        )

    def test_preflight_validation_accepts_full_expected_selected_scope(self) -> None:
        rows = []
        for family in utils.COMPONENT_ORDER:
            scope = utils.EXPECTED_SELECTED_SCOPE[family]
            for start_year in scope["annual_years"]:
                rows.append(
                    {
                        "family": family,
                        "family_display": utils.COMPONENT_FAMILIES[family]["display"],
                        "link_text": f"AY {start_year}-{start_year + 1}",
                        "url": f"https://example.com/{family}/{start_year}.xls",
                        "filename": f"{family}-{start_year}.xls",
                        "award_year": f"{start_year:04d}-{start_year + 1:04d}",
                        "award_year_start": start_year,
                        "award_year_end": start_year + 1,
                        "quarter": "",
                        "period_type": "annual",
                        "selected_for_panel": True,
                        "selection_reason": "annual_summary_selected",
                    }
                )
            for start_year in scope["q4_years"]:
                rows.append(
                    {
                        "family": family,
                        "family_display": utils.COMPONENT_FAMILIES[family]["display"],
                        "link_text": f"AY {start_year}-{start_year + 1} Q4",
                        "url": f"https://example.com/{family}/{start_year}-q4.xls",
                        "filename": f"{family}-{start_year}-q4.xls",
                        "award_year": f"{start_year:04d}-{start_year + 1:04d}",
                        "award_year_start": start_year,
                        "award_year_end": start_year + 1,
                        "quarter": 4,
                        "period_type": "quarterly",
                        "selected_for_panel": True,
                        "selection_reason": "q4_cumulative_selected",
                    }
                )
        validation = utils.validate_inventory_scope(rows)
        self.assertTrue(bool(validation["passed"].all()))


if __name__ == "__main__":
    unittest.main()
