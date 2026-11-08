"""Retrieval v5 (Workstream B): general behaviour of the law-wide provision index. Offline, read-only database copy.
Sentences here are written for the tests; none is taken from an evaluation set."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compliance_agent.llm_lab import concepts_v5 as C  # noqa: E402
from compliance_agent.llm_lab.retrieve import connect_ro, search, MAX_INTENT_ADD, MAX_TOTAL_ADD  # noqa: E402

MAIN = ROOT / "data" / "CL_compliance.sqlite3"
V4_CONCEPTS_SHA = "5dd350a321e368c29997c68087126cd5316767e5aa311a91af3bf04488c9c6ad"   # concepts.py at fcdfbb7


class IntentRulesV5(unittest.TestCase):
    def test_86_owner_wording_for_deregistration_and_voluntary(self):
        self.assertIn("deregistration", C.intents("We are shutting down the shop and moving abroad in March, what about our VAT?")[0])
        self.assertIn("deregistration", C.intents("How do I unregister from VAT?")[0])
        self.assertIn("voluntary_registration", C.intents("I have no sales yet, only expenses. Can I get a VAT number?")[0])

    def test_87_falling_turnover_and_hesitation_get_all_registration_alternatives(self):
        its, amb = C.intents("Our turnover went down to 150k this year, do I have to change anything about VAT registration?")
        self.assertTrue(amb)
        self.assertTrue({"deregistration", "voluntary_registration", "mandatory_registration"} <= set(its))
        its, amb = C.intents("I'm not sure whether I should register or cancel, my sales are around 3 lakh")
        self.assertTrue(amb)
        self.assertTrue({"deregistration", "voluntary_registration", "mandatory_registration"} <= set(its))

    def test_88_precision_guards(self):
        self.assertNotIn("exempt_residential", C.intents("I bake cakes in my villa kitchen and sell about 20k a month")[0])
        self.assertNotIn("penalties", C.intents("My sales are 90k, I'm fine without VAT, right?")[0])
        self.assertEqual(C.intents("Do I owe corporate tax on 400k profit?"), ([], False))
        found, _ = C.detect("My accountant charges 300 a month, is that normal?")
        self.assertNotIn("threshold", found)                       # an amount that is not the owner's income
        found, _ = C.detect("I make about 30 a month from cakes")
        self.assertIn("threshold", found)

    def test_89_value_and_related_party_rules(self):
        self.assertIn("related_value", C.intents("I sell to my uncle's restaurant at a discount, what value do I use?")[0])
        self.assertIn("agent", C.intents("I collect the courier fee from buyers and pass it on to the courier")[0])

    def test_90_provision_map_fixes(self):
        P = C.INTENT_PROVISIONS
        self.assertIn(("FTA-VAT-ER", 30), P["zero_rated_or_exports"]["primary"])
        self.assertNotIn(("FTA-VAT-ER", 16), P["zero_rated_or_exports"]["primary"])     # v4 mapping error
        self.assertIn(("FTA-VAT-DL8", 22), P["deregistration"]["primary"])
        titles_ok = all(src in ("FTA-VAT-DL8", "FTA-VAT-ER", "FTA-VAT-REG-PAGE") for v in P.values() for src, _ in v["primary"] + v["supporting"])
        self.assertTrue(titles_ok)

    def test_91_demo_guard_map_unchanged(self):
        """The Workstream A demo guard (ask.py) reads concepts.py; v5 lives in concepts_v5.py so the demo is unchanged."""
        self.assertEqual(hashlib.sha256((ROOT / "compliance_agent" / "llm_lab" / "concepts.py").read_bytes()).hexdigest(), V4_CONCEPTS_SHA)


@unittest.skipUnless(MAIN.exists(), "main database not built")
class SearchBudgetV5(unittest.TestCase):
    def test_92_additions_only_and_within_budget_on_every_dev_question(self):
        con = connect_ro(MAIN)
        n = 0
        for name in ("CL_llm_eval_questions", "CL_llm_eval_unseen_v1", "CL_llm_eval_unseen_v2", "CL_llm_eval_unseen_v3"):
            data = json.loads((ROOT / "fixtures" / f"{name}.json").read_text())
            for q in (data["questions"] if isinstance(data, dict) else data):
                plain = [p["passage_id"] for p in search(con, q["text"], heading_extra=0, core_pack=False)]
                full = search(con, q["text"])
                with self.subTest(q=q["id"]):
                    self.assertEqual([p["passage_id"] for p in full][:len(plain)], plain)
                    added = full[len(plain):]
                    self.assertLessEqual(sum(p["added_by"].startswith("intent:") for p in added), MAX_INTENT_ADD)
                    self.assertLessEqual(len(added), MAX_TOTAL_ADD)
                    self.assertEqual(len({p["passage_id"] for p in full}), len(full))
                n += 1
        con.close()
        self.assertGreater(n, 90)

    def test_93_other_regime_question_gets_no_additions(self):
        con = connect_ro(MAIN)
        got = search(con, "How much corporate tax do I pay on my home bakery profit?")
        con.close()
        self.assertFalse(any(p["added_by"].startswith("intent:") for p in got))


class Iteration2V5(unittest.TestCase):
    def test_94_turnover_and_calculation_wording(self):
        self.assertTrue(C.turnover_stated("I made about 32k a month last year"))
        self.assertFalse(C.turnover_stated("The courier charges 15 a parcel"))
        self.assertIn("threshold_calculation", C.intents("Do I deduct returned orders when working out the VAT threshold?")[0])

    @unittest.skipUnless(MAIN.exists(), "main database not built")
    def test_95_title_matches_only_as_fallback(self):
        con = connect_ro(MAIN)
        got = search(con, "I export dates to Oman and my total sales are 400k, do the exports count for the VAT threshold?")
        con.close()
        intent_added = [p for p in got if p["added_by"].startswith("intent:")]
        self.assertGreaterEqual(len(intent_added), 2)
        self.assertFalse(any(p["added_by"] == "heading" for p in got))
        self.assertTrue(any(p["source_id"] == "FTA-VAT-DL8" and p["locator"].startswith("Article 19,") for p in got))
