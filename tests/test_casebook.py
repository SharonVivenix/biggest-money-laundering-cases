import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import casebook as cb  # noqa: E402

SAMPLE = ROOT / "examples" / "transactions.example.csv"
CTX = {"home": "US", "high_risk": {"ZZ"}}


def fired(alerts):
    out = {}
    for a in alerts:
        out.setdefault(a["customer_id"], set()).add(a["rule"])
    return out


class PlantedCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.txns = cb.load_transactions(SAMPLE)
        cls.hits = fired(cb.scan(cls.txns, cb.RULES, CTX))

    def test_each_planted_customer_trips_its_case_rule(self):
        expected = {"C-WACH": "R1", "C-HSBC": "R2", "C-DANS": "R3", "C-1MDB": "R4",
                    "C-TDBK": "R5", "C-BCCI": "R6", "C-CAPO": "R7", "C-BOWY": "R8"}
        for cid, rule in expected.items():
            self.assertIn(rule, self.hits.get(cid, set()), cid)

    def test_background_customers_stay_quiet(self):
        noisy = [c for c in self.hits if not c.startswith("C-") or c[2:].isdigit()]
        self.assertEqual(noisy, [])

    def test_front_business_beats_the_profile_rule(self):
        # The laundromat declares its inflated takings, so only the peer rule sees it.
        self.assertEqual(self.hits["C-CAPO"], {"R7"})

    def test_high_risk_list_is_configurable(self):
        alerts = cb.scan(self.txns, [cb.RULE_BY_ID["R6"]], {"home": "US", "high_risk": set()})
        self.assertEqual(alerts, [])


class Coverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.txns = cb.load_transactions(SAMPLE)

    def test_excluding_a_channel_lowers_coverage(self):
        full = cb.coverage(self.txns, cb.RULES, None)["coverage"]
        narrow = cb.coverage(self.txns, cb.RULES, {"cash_deposit", "wire_in", "wire_out"})
        self.assertLess(narrow["coverage"], full)
        status = {r["channel"]: r["covered"] for r in narrow["channels"]}
        self.assertFalse(status["casino_buyin"])
        self.assertTrue(status["wire_in"])

    def test_channels_without_rules_are_reported(self):
        report = cb.coverage(self.txns, cb.RULES, None)
        uncovered = {r["channel"] for r in report["channels"] if not r["covered"]}
        self.assertEqual(uncovered, {"ach", "check", "card"})


class Inputs(unittest.TestCase):
    def test_unknown_rule_id(self):
        with self.assertRaises(cb.InputError):
            cb.pick_rules("R1,R99")

    def test_missing_column(self):
        bad = ROOT / "tests" / "missing_column.csv"
        with self.assertRaises(cb.InputError):
            cb.load_transactions(bad)

    def test_exit_code_three_on_bad_input(self):
        self.assertEqual(cb.main(["scan", str(ROOT / "tests" / "missing_column.csv")]), 3)


class CaseTable(unittest.TestCase):
    def test_every_case_maps_to_a_known_rule(self):
        for case in json.loads(cb.CASES_FILE.read_text(encoding="utf-8")):
            for rule in case["rules"]:
                self.assertTrue(rule == "coverage" or rule in cb.RULE_BY_ID, case["id"])

    def test_readme_table_in_sync(self):
        self.assertEqual(cb.main(["table", "--check"]), 0)


if __name__ == "__main__":
    unittest.main()
