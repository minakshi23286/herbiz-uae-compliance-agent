"""Retrieval v6 (Workstream B): structured five-stage pipeline. Offline, read-only database copy.
Sentences here are written for the tests; none is taken from an evaluation set."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compliance_agent.llm_lab import locators as L  # noqa: E402
from compliance_agent.llm_lab import pipeline_v6 as P  # noqa: E402
from compliance_agent.llm_lab.retrieve import connect_ro, search as v5_search  # noqa: E402

MAIN = ROOT / "data" / "CL_compliance.sqlite3"


class LocatorContract(unittest.TestCase):
    def test_v6_01_locator_grammar(self):
        self.assertEqual(L.article_key("FTA-VAT-DL8", "Article 79 (bis), pp. 38-39"), "FTA-VAT-DL8|79 (bis)")
        self.assertEqual(L.article_key("FTA-VAT-ER", "Article 1, pp. 2-7, part 3"), "FTA-VAT-ER|1")
        self.assertIsNone(L.article_key("FTA-VAT-REG-PAGE", "Paragraph 4"))
        self.assertTrue(L.matches("FTA-VAT-REG-PAGE", "Paragraph 4", "FTA-VAT-REG-PAGE|*"))
        self.assertFalse(L.matches("FTA-VAT-ER", "Article 14 (bis), p. 13", "FTA-VAT-ER|14"))


class Tables(unittest.TestCase):
    def test_v6_02_expansion_links_come_from_the_law(self):
        links = P.tables()["links"]
        why = lambda a, b: {x["why"] for x in links.get(a, []) if x["key"] == b}
        self.assertIn("sibling", why("FTA-VAT-DL8|25", "FTA-VAT-DL8|26"))
        self.assertIn("implementing_pair", why("FTA-VAT-DL8|13", "FTA-VAT-ER|7"))
        self.assertIn("implementing_pair", why("FTA-VAT-DL8|21", "FTA-VAT-ER|14"))

    def test_v6_03_provision_map_is_draft_and_unreviewed(self):
        topics = P.tables()["topics"]
        self.assertTrue(all(t["status"] == "draft" and t["reviewed_by"] is None for t in topics.values()))
        self.assertIn("FTA-VAT-DL8|71", topics["tax_return"]["required"])

    @unittest.skipUnless(MAIN.exists(), "main database not built")
    def test_v6_04_tables_rebuild_identically(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:   # never writes the committed tables
            subprocess.run([sys.executable, str(ROOT / "experiments" / "ws_b" / "CL_build_v6_tables.py"), str(MAIN), d], check=True, capture_output=True)
            for n in ("CL_provision_map_v6.json", "CL_expansion_v6.json", "CL_article_index_v6.json"):
                self.assertEqual((Path(d) / n).read_bytes(), (P.DATA / n).read_bytes(), n)


@unittest.skipUnless(MAIN.exists(), "main database not built")
class Pipeline(unittest.TestCase):
    def setUp(self):
        self.con = connect_ro(MAIN)

    def tearDown(self):
        self.con.close()

    def test_v6_05_outdated_provision_is_never_certified(self):
        r = P.retrieve(self.con, "I import fabric for my VAT registered shop, how does the reverse charge work on imports?")
        self.assertIn("FTA-VAT-DL8|48", r["required"])
        self.assertEqual(r["status"], "source_validity_unresolved")
        self.assertIn("G3", [i["id"] for i in r["issues"]])

    def test_v6_06_conflicting_deadline_is_never_certified(self):
        r = P.retrieve(self.con, "We are closing our VAT registered bakery next month. How do we cancel the VAT registration?")
        self.assertEqual(r["status"], "source_validity_unresolved")
        self.assertIn("G1", [i["id"] for i in r["issues"]])

    def test_v6_07_out_of_scope_gets_no_additions(self):
        for q in ("How much corporate tax will I pay on my home salon profit?", "What is the best bank for a small business account?",
                  "What is the fine for hiring someone without a work permit?"):
            with self.subTest(q=q):
                r = P.retrieve(self.con, q)
                self.assertEqual(r["status"], "out_of_scope")
                self.assertTrue(all(p["added_by"] == "bm25" for p in r["passages"]))

    def test_v6_08_complete_only_when_nothing_missing_and_no_issue(self):
        for name in ("CL_llm_eval_questions", "CL_llm_eval_unseen_v1", "CL_llm_eval_unseen_v2", "CL_llm_eval_unseen_v3", "CL_llm_eval_unseen_v4"):
            data = json.loads((ROOT / "fixtures" / f"{name}.json").read_text())
            for q in (data["questions"] if isinstance(data, dict) else data):
                r = P.retrieve(self.con, q["text"])
                with self.subTest(q=q["id"]):
                    if r["status"] == "complete":
                        self.assertFalse(r["missing"])
                        self.assertFalse(r["issues"])
                        self.assertTrue(all(P._present(r["passages"], x) for x in r["required"]))
                    plain = [p["passage_id"] for p in v5_search(self.con, q["text"], heading_extra=0, core_pack=False)]
                    self.assertEqual([p["passage_id"] for p in r["passages"]][:len(plain)], plain)   # BM25 top-6 unchanged
                    self.assertLessEqual(len(r["passages"]), 12)
                    self.assertEqual(len({p["passage_id"] for p in r["passages"]}), len(r["passages"]))

    def test_v6_09_second_method_adds_a_missed_topic(self):
        q = "Can our two VAT registered companies file as one group?"
        both = {"FTA-VAT-DL8|14"}
        self.assertEqual(P.promote_topics(q, both, [("FTA-VAT-DL8|14", 9.0)], ["related_parties"]), ["tax_group"])
        self.assertEqual(P.promote_topics(q, set(), [("FTA-VAT-DL8|14", 9.0)], ["related_parties"]), [])        # one method only
        self.assertEqual(P.promote_topics("Can our two companies file together?", both, [("FTA-VAT-DL8|14", 9.0)], []), [])  # no title word

    def test_v6_10_location_resolves_generic_ambiguity(self):
        r = P.retrieve(self.con, "I live in Jordan and sell candles to people in Dubai through my website. Do I need to register?")
        self.assertIn("non_resident", r["classification"]["intents"])
        self.assertFalse(r["classification"]["ambiguous"])

    def test_v6_11_stage5_note_and_guard(self):
        r = P.retrieve(self.con, "We are closing our VAT registered bakery next month. How do we cancel the VAT registration?")
        self.assertIn("SOURCE_VALIDITY_UNRESOLVED", P.coverage_note(r))
        g = P.answer_certifiable(r, {"answer_status": "answered"})
        self.assertFalse(g["certified"])
        self.assertIsNotNone(g["flag"])


class FrozenV5Guard(unittest.TestCase):
    def test_v6_12_v5_runs_only_with_final(self):
        out = subprocess.run([sys.executable, str(ROOT / "experiments" / "ws_b" / "CL_ws_b_eval_v6.py"), "--db", "x.sqlite3",
                              "--sets", "v5", "--label", "t"], capture_output=True, text=True)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("frozen independent set", out.stderr + out.stdout)
