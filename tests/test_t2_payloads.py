"""Task 2 B-1/B-3: retrieve_v8 safeguards and WS-B payloads validated against WS-A's frozen G1 schemas (byte copy at
b4eb7bb, identical to dbed01c). Development questions and synthetic profiles only; the holdout v10 is never read here."""
from __future__ import annotations

import datetime as dt
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compliance_agent.llm_lab import retrieve_v8 as V8, t2_payloads as T  # noqa: E402
from compliance_agent.llm_lab.retrieve import connect_ro  # noqa: E402
from compliance_agent.obligations import engine as E  # noqa: E402

try:
    import jsonschema
except ImportError:                                       # validation tests skip, never pass silently
    jsonschema = None

DB = ROOT / "data" / "CL_ws_b_exact_copy.sqlite3"
SCHEMAS = ROOT / "contracts" / "ws_a_canonical_b4eb7bb"
FREEZE = {"commit": "0000000", "files_sha256": {"compliance_agent/llm_lab/retrieve_v8.py": "0" * 64}, "config_sha256": "0" * 64}
SNAP = {"snapshot_date": "2026-10-17", "db_md5": "26e202b87a062288e56bcda1de9b0217", "manifest_version": "0.2.0"}
DEV = ["v3", "v4", "v8", "v9"]


def schema(name):
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def dev_questions():
    for s in DEV:
        d = json.loads((ROOT / "fixtures" / f"CL_llm_eval_unseen_{s}.json").read_text(encoding="utf-8"))
        yield from (d["questions"] if isinstance(d, dict) else d)


@unittest.skipUnless(DB.exists(), "needs the exact DB copy (read-only)")
class RetrievalV8(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con = connect_ro(DB)
        cls.qs = list(dev_questions())
        cls.res = {q["id"]: T.retrieval_result(cls.con, q["text"], FREEZE, SNAP) for q in cls.qs}

    def test_t2_b3_01_every_payload_validates(self):
        if jsonschema is None:
            self.skipTest("jsonschema not available")
        sch = schema("retrieval_result_1.0.schema.json")
        for qid, r in self.res.items():
            jsonschema.validate(r, sch)

    def test_t2_b1_02_budget_and_completeness_invariants(self):
        for qid, r in self.res.items():
            self.assertEqual(r["budget"]["returned"], len(r["items"]), qid)
            self.assertLessEqual(r["budget"]["returned"], V8.MAX_PASSAGES, qid)
            c = r["completeness"]
            if c["status"] == "complete_for_map":
                self.assertEqual(c["missing_required"], [], qid)
            if c["status"] == "incomplete":
                self.assertTrue(c["missing_required"], qid)
            if not r["scope"]["in_scope"]:
                self.assertEqual((c["status"], r["required_provisions"]), ("unknown", []), qid)
            self.assertEqual(c["map_review_status"], "draft-unreviewed")
            self.assertEqual([i["rank"] for i in r["items"]], list(range(1, len(r["items"]) + 1)))
            self.assertTrue({i["added_by"] for i in r["items"]} <= set(V8.ADDED_BY.values()), qid)
            self.assertNotEqual(c["status"], "complete_for_map", qid)      # Task 2: certification is off (CERTIFY False)

    def test_t2_b1_03_no_silent_incomplete_on_development_sets(self):
        for q in self.qs:
            req = q.get("required_sources") or []
            r = self.res[q["id"]]
            if req and r["completeness"]["status"] == "complete_for_map":
                have = {(i["source_id"], i["article"]) for i in r["items"]}
                for s, a in req:
                    self.assertIn((s, None if a is None else str(a)), have, q["id"])

    def test_t2_b1_04_other_regimes_never_answered_from_vat_texts(self):
        for text in ("Do I need to register for corporate tax?", "What is the GST rate in India for my resin art?",
                     "My sister in Riyadh got a ZATCA notice about e-invoicing."):
            r = T.retrieval_result(self.con, text, FREEZE, SNAP)
            self.assertFalse(r["scope"]["in_scope"], text)
            self.assertEqual(r["completeness"]["status"], "unknown")

    def test_t2_b1_04b_mixed_questions_keep_vat_part_and_review_examples(self):
        for text in ("My customers pay with Visa. Do I charge 5% VAT on cakes?", "VAT and customs duty when importing fabric",
                     "I took a bank loan to buy an oven, can I reclaim the VAT on the oven?",
                     "Do I need UAE VAT and corporate tax registration with the FTA for my bakery?"):
            self.assertTrue(T.retrieval_result(self.con, text, FREEZE, SNAP)["scope"]["in_scope"], text)
        for text in ("what is the fine for not wearing a seatbelt", "Do I need to register for UK VAT with HMRC?",
                     "Can I deduct zakat from the VAT I owe?", "how much does it cost to renew a home business licence?"):
            self.assertFalse(T.retrieval_result(self.con, text, FREEZE, SNAP)["scope"]["in_scope"], text)
        self.assertFalse(V8.CERTIFY)

    def test_t2_b1_05_query_hash_normalisation(self):
        self.assertEqual(T.query_sha256("  Do I  need\tVAT?\n"), T.query_sha256("do i need vat?"))
        self.assertNotEqual(T.query_sha256("do i need vat?"), T.query_sha256("do i need vat"))

    def test_t2_b3_06_live_model_refused_and_text_can_be_dropped(self):
        with self.assertRaises(ValueError):
            T.retrieval_result(self.con, "vat on cakes", FREEZE, SNAP, execution_mode="live_model")
        r = T.retrieval_result(self.con, "vat on cakes", FREEZE, SNAP, include_text=False)
        self.assertTrue(all("text" not in i for i in r["items"]))


class DecisionExplanation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        profs = []
        for f in ("CL_synthetic_profiles_360.json", "CL_ct_demo_personas_wsc.json"):
            profs += json.loads((ROOT / "fixtures" / "obligations" / f).read_text(encoding="utf-8"))["profiles"]
        cls.out = [T.decision_explanation(o, "05843b2", "ws-b-demo-0.4")
                   for p in profs for o in E.assess(p, None, dt.date(2026, 10, 17))["obligations"]]

    def test_t2_b3_07_every_payload_validates(self):
        if jsonschema is None:
            self.skipTest("jsonschema not available")
        sch = schema("decision_explanation_1.0.schema.json")
        for d in self.out:
            jsonschema.validate(d, sch)

    def test_t2_b3_08_semantics(self):
        self.assertGreater(len(self.out), 80)
        for d in self.out:
            self.assertIsNone(d["confidence"]["numeric"])
            self.assertNotEqual(d["confidence"]["level"], "high")              # impossible today: 0 reviewed rules
            self.assertTrue(set(d["confidence"]["basis"]) <= set(T.BASIS))
            self.assertIs(d["review"]["release_approved"], False)
            self.assertEqual(d["execution_mode"], "simulated" if d["rule_status"] == "synthetic_test" else "deterministic")
            self.assertEqual([s["n"] for s in d["steps"]], list(range(1, len(d["steps"]) + 1)))
            if d["state"] == "blocked_pending_legal_validation":
                self.assertEqual(d["confidence"]["level"], "low")
                self.assertIn("blocked", d["confidence"]["basis"])
                self.assertTrue(all(s["visible_to"] == "reviewer" for s in d["steps"] if s["kind"] == "rule_eval"))
            if d["rule_status"] == "synthetic_test":
                self.assertIn("test_rule", d["confidence"]["basis"])


if __name__ == "__main__":
    unittest.main()
