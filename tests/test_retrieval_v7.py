"""Retrieval v7 (Workstream B, one map-completion cycle). Offline, read-only database copy.
Sentences here are written for the tests; none is taken from an evaluation set."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compliance_agent.llm_lab import pipeline_v7 as P  # noqa: E402
from compliance_agent.llm_lab.retrieve import connect_ro, search as v5_search  # noqa: E402

MAIN = ROOT / "data" / "CL_compliance.sqlite3"
DL, ER = "FTA-VAT-DL8", "FTA-VAT-ER"


class MapV7(unittest.TestCase):
    def test_v7_01_every_article_is_reachable_and_new_concepts_are_mapped(self):
        T = P.tables()
        self.assertEqual(len([k for k in T["topics"] if k.startswith("art:")]), len(T["articles"]))
        C = T["curated"]
        self.assertEqual(C["vouchers"]["required"], [f"{DL}|40", f"{ER}|28"])
        self.assertEqual(C["composite_supply"]["required"], [f"{DL}|8", f"{ER}|4"])
        self.assertEqual(C["input_tax_before_registration"]["required"], [f"{DL}|56"])
        self.assertEqual(C["blocked_input_tax"]["required"], [f"{ER}|53"])
        self.assertIn(f"{DL}|23", C["deregistration"]["required"])
        self.assertTrue(all(v["status"] == "draft" and v["reviewed_by"] is None for v in T["topics"].values()))

    @unittest.skipUnless(MAIN.exists(), "main database not built")
    def test_v7_02_tables_rebuild_identically(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([sys.executable, str(ROOT / "experiments" / "ws_b" / "CL_build_v7_tables.py"), str(MAIN), d], check=True, capture_output=True)
            for n in ("CL_provision_map_v7.json", "CL_coverage_audit_v7.json"):
                self.assertEqual((Path(d) / n).read_bytes(), (P.DATA / n).read_bytes(), n)

    def test_v7_03_v6_files_unchanged(self):
        rec = json.loads((ROOT / "docs" / "CL_evidence" / "ws_b" / "CL_v6_code_freeze.json").read_text())
        for f, h in rec["files"].items():
            if f.endswith("CL_ws_b_eval_v6.py"):
                continue
            with self.subTest(f=f):
                self.assertEqual(hashlib.sha256((ROOT / f).read_bytes()).hexdigest(), h)


class ClassifyV7(unittest.TestCase):
    def test_v7_04_scope_rule(self):
        self.assertFalse(P.classify("My brother and I hold separate trade licences and keep our sales below 375k each. Will the FTA add them up?")["out_of_scope"])
        self.assertTrue(P.classify("Do I owe corporate tax on 400k profit from my salon?")["out_of_scope"])
        self.assertTrue(P.classify("What is the fine for hiring a nanny without a visa?")["out_of_scope"])

    def test_v7_05_missing_concepts_are_recognised(self):
        cases = {"vouchers": "I want to sell gift cards customers can redeem later. When is VAT due?",
                 "composite_supply": "My candle workshop comes with a take-home kit, is that one supply for VAT?",
                 "input_tax_before_registration": "I bought equipment in May but only got my TRN in July. Can I claim that VAT?",
                 "blocked_input_tax": "Can I claim back the VAT on a client dinner at a restaurant?",
                 "bad_debt": "A customer never paid my invoice from last year and I already paid the VAT. Can I get it back?"}
        for topic, q in cases.items():
            with self.subTest(topic=topic):
                c = P.classify(q)
                self.assertIn(topic, c["intents"] + c["secondary"])

    def test_v7_06_false_secondary_triggers_removed(self):
        c = P.classify("I sell gift cards for my salon, VAT registered, when do I charge VAT?")
        self.assertFalse({"capital_assets_threshold", "capital_assets_scheme", "deemed_supply"} & set(c["intents"] + c["secondary"]))
        c = P.classify("My home nursery charges fees, is nursery education zero-rated for VAT?")
        self.assertNotIn("healthcare", c["intents"] + c["secondary"])
        c = P.classify("My accountant cousin says I cannot claim back VAT on restaurant bills, is that right?")
        self.assertNotIn("related_parties", c["intents"] + c["secondary"])
        c = P.classify("I export spices to Oman, do I charge 5% or 0?")
        self.assertNotIn("vat_rate", c["intents"] + c["secondary"])


@unittest.skipUnless(MAIN.exists(), "main database not built")
class PipelineV7(unittest.TestCase):
    def setUp(self):
        self.con = connect_ro(MAIN)

    def tearDown(self):
        self.con.close()

    def test_v7_07_primary_topics_first_in_budget(self):
        r = P.retrieve(self.con, "I give away free samples and I'm worried about fines, do I pay VAT on samples?")
        added = [p["added_by"] for p in r["passages"] if p["added_by"] != "bm25"]
        first_secondary = next((i for i, a in enumerate(added) if "penalties" in a), len(added))
        first_primary = next((i for i, a in enumerate(added) if "deemed_supply" in a), len(added))
        self.assertLess(first_primary, first_secondary)

    def test_v7_08_g1_g3_stay_blocked(self):
        r = P.retrieve(self.con, "We are closing our VAT registered bakery next month. How do we cancel the VAT registration?")
        self.assertEqual(r["status"], "source_validity_unresolved")
        r = P.retrieve(self.con, "I import fabric for my VAT registered shop, how does the reverse charge work on imports?")
        self.assertEqual(r["status"], "source_validity_unresolved")

    def test_v7_09_invariants_on_every_development_question(self):
        for name in ("CL_llm_eval_questions", "CL_llm_eval_unseen_v1", "CL_llm_eval_unseen_v2", "CL_llm_eval_unseen_v3",
                     "CL_llm_eval_unseen_v4", "CL_llm_eval_unseen_v5"):
            data = json.loads((ROOT / "fixtures" / f"{name}.json").read_text())
            for q in (data["questions"] if isinstance(data, dict) else data):
                r = P.retrieve(self.con, q["text"])
                with self.subTest(q=q["id"]):
                    if r["status"] == "complete":
                        self.assertFalse(r["missing"] or r["issues"])
                    if r["status"] == "out_of_scope":
                        self.assertTrue(all(p["added_by"] == "bm25" for p in r["passages"]))
                    plain = [p["passage_id"] for p in v5_search(self.con, q["text"], heading_extra=0, core_pack=False)]
                    self.assertEqual([p["passage_id"] for p in r["passages"]][:len(plain)], plain)
                    self.assertLessEqual(len(r["passages"]), 12)


class FrozenV6Guard(unittest.TestCase):
    def test_v7_10_eval_set_v6_runs_only_with_final(self):
        out = subprocess.run([sys.executable, str(ROOT / "experiments" / "ws_b" / "CL_ws_b_eval_v7.py"), "--db", "x.sqlite3",
                              "--sets", "v6", "--label", "t"], capture_output=True, text=True)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("frozen independent set", out.stderr + out.stdout)
