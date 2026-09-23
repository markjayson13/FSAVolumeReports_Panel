import csv
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Scripts"))
from fsa_policy import (METADATA_DIR, events_for_year, load_policy_events,
                        load_policy_registry, metadata_for_measure,
                        observed_header_years, policy_registry_hash)


class PolicyRegistryTests(unittest.TestCase):
    def test_every_observed_measure_is_documented_with_exact_year_sets(self):
        with (METADATA_DIR / "source_schema_inventory.csv").open() as stream:
            inventory = list(csv.DictReader(stream))
        descriptors = {"", "opeid8", "school", "state", "zip_code", "school_type"}
        groups = {}
        for row in inventory:
            if row["canonical_column"] in descriptors:
                continue
            groups.setdefault((row["family"], row["canonical_column"]), set()).add(int(row["award_year_start"]))
        for (family, canonical), expected in groups.items():
            self.assertEqual(tuple(sorted(expected)), observed_header_years(family, canonical))
            self.assertTrue(metadata_for_measure(canonical)["definition"])

    def test_policy_and_observation_bounds_are_distinct(self):
        self.assertIn(2005, observed_header_years("direct_loans", "grad_plus_disbursements"))
        event = next(e for e in load_policy_events() if e["event_id"] == "grad_plus_start")
        self.assertEqual("2006-07-01", event["effective_date"])
        self.assertEqual(2015, max(observed_header_years("campus_based", "perkins_federal_award")))
        self.assertEqual(2023, max(observed_header_years("grants", "iasg_disbursements")))
        self.assertTrue(any(e["event_id"] == "iasg_into_pell_2024" for e in events_for_year(2024, "pell")))

    def test_recipients_not_unique_across_components(self):
        result = metadata_for_measure("loan__plus_recipient_records")
        self.assertEqual("recipient_records_not_unique_people", result["unit"])
        self.assertIn("not estimates of unique people", result["counting_caveat"])
        self.assertIn("supported students", metadata_for_measure("loan_direct__parent_plus_recipients")["counting_caveat"])

    def test_registry_integrity_and_unknown_fields(self):
        event_ids = [e["event_id"] for e in load_policy_events()]
        self.assertEqual(len(event_ids), len(set(event_ids)))
        for measure in load_policy_registry()["measures"].values():
            self.assertTrue(set(measure["policy_event_ids"]).issubset(event_ids))
        self.assertEqual(64, len(policy_registry_hash()))
        self.assertEqual({}, metadata_for_measure("unreviewed_measure"))
        self.assertEqual({}, metadata_for_measure("grant__pell_disbursements__status"))
        self.assertEqual("USD_nominal", metadata_for_measure("campus__fws_disbursements")["unit"])


if __name__ == "__main__":
    unittest.main()
