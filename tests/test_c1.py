"""Option C1 (Workstream B): classifier + agreement pipeline with MOCKED API responses only. No network, no spend.
Sentences here are written for the tests; none is taken from an evaluation set."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compliance_agent.llm_lab import classifier_c1 as K, pipeline_c1 as PC, pipeline_v7 as P7  # noqa: E402
from compliance_agent.llm_lab.retrieve import connect_ro  # noqa: E402

MAIN = ROOT / "data" / "CL_compliance.sqlite3"
Q_REG = "My sales passed 400k last year, must I register for VAT now?"


def fake(resp, stop="end_turn"):
    return K.FakeC1Client(lambda q: resp, stop_reason=stop)


class Request(unittest.TestCase):
    def test_c1_01_request_is_minimal_and_fixed(self):
        r = K.request("Do I charge VAT on my cakes?")
        self.assertEqual(r["model"], "claude-haiku-5-5")
        self.assertEqual(r["output_config"]["effort"], "low")
        self.assertEqual(r["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(len(r["messages"]), 1)
        self.assertIn("Do I charge VAT on my cakes?", r["messages"][0]["content"])
        self.assertNotIn("passage", json.dumps(r).lower())          # no legal passages or database content are sent
        names = {n for n, _ in K.topic_catalogue()}
        self.assertEqual(set(r["output_config"]["format"]["schema"]["properties"]["topics"]["items"]["enum"]), names)

    def test_c1_02_every_failure_is_not_ok(self):
        good = {"in_scope": True, "out_of_scope_class": "none", "topics": ["mandatory_registration"], "confidence": "high"}
        self.assertTrue(K.classify(Q_REG, fake(good))["ok"])
        for name, client in {"exception": K.FakeC1Client(lambda q: TimeoutError("t")), "refusal": fake(good, "refusal"),
                             "truncated": fake(good, "max_tokens"), "bad_json": fake("{nope"),
                             "unknown_topic": fake({**good, "topics": ["invented_topic"]}),
                             "contradiction": fake({**good, "out_of_scope_class": "corporate_tax"})}.items():
            with self.subTest(name=name):
                self.assertFalse(K.classify(Q_REG, client)["ok"])


@unittest.skipUnless(MAIN.exists(), "main database not built")
class Agreement(unittest.TestCase):
    def setUp(self):
        self.con = connect_ro(MAIN)

    def tearDown(self):
        self.con.close()

    def run_c1(self, q, resp, stop="end_turn"):
        return PC.retrieve(self.con, q, K.classify(q, fake(resp, stop)))

    def test_c1_03_none_is_plain_v7(self):
        a, b = PC.retrieve(self.con, Q_REG, None), P7.retrieve(self.con, Q_REG)
        self.assertEqual([p["passage_id"] for p in a["passages"]], [p["passage_id"] for p in b["passages"]])
        self.assertEqual(a["status"], b["status"])

    def test_c1_04_never_complete_unless_both_agree(self):
        v7 = P7.retrieve(self.con, Q_REG)
        agree = K.oracle_from_v7(Q_REG)
        bad = {"failure": RuntimeError("x"), "low": {**agree, "confidence": "low"},
               "disagree": {**agree, "topics": ["vouchers"]}, "oos": {"in_scope": False, "out_of_scope_class": "not_tax", "topics": [], "confidence": "high"}}
        for name, resp in bad.items():
            with self.subTest(name=name):
                r = PC.retrieve(self.con, Q_REG, K.classify(Q_REG, K.FakeC1Client(lambda q, resp=resp: resp)))
                self.assertNotEqual(r["status"], "complete")
        if v7["status"] == "complete":
            self.assertEqual(self.run_c1(Q_REG, agree)["status"], "complete")

    def test_c1_05_out_of_scope_needs_both_and_adds_nothing(self):
        q = "How do I register my salon for corporate tax with the FTA?"
        oos = {"in_scope": False, "out_of_scope_class": "corporate_tax", "topics": [], "confidence": "high"}
        r = self.run_c1(q, oos)
        self.assertIn(r["status"], ("out_of_scope", "incomplete"))
        self.assertTrue(all(p["added_by"] == "bm25" for p in r["passages"]))
        r = self.run_c1(Q_REG, oos)                              # v7 in scope, C1 out of scope -> incomplete, nothing added
        self.assertEqual(r["status"], "incomplete")
        self.assertTrue(all(p["added_by"] == "bm25" for p in r["passages"]))

    def test_c1_06_c1_topic_adds_provisions_but_cannot_certify_alone(self):
        q = "Can I claim the VAT on things I bought before getting registered?"
        r = self.run_c1(q, {"in_scope": True, "out_of_scope_class": "none", "topics": ["input_tax_before_registration"], "confidence": "high"})
        self.assertTrue(PC.P7._present(r["passages"], "FTA-VAT-DL8|56"))
        if P7.retrieve(self.con, q)["status"] != "complete":
            self.assertNotEqual(r["status"], "complete")

    def test_c1_07_g1_g3_stay_blocked_even_when_both_agree(self):
        for q in ("We are closing our VAT registered bakery next month. How do we cancel the VAT registration?",
                  "I import fabric for my VAT registered shop, how does the reverse charge work on imports?"):
            with self.subTest(q=q):
                r = self.run_c1(q, K.oracle_from_v7(q))
                self.assertEqual(r["status"], "source_validity_unresolved")


class Harness(unittest.TestCase):
    def test_c1_08_paid_run_refused_without_approval_and_v7_only_live(self):
        h = ROOT / "experiments" / "ws_b" / "CL_ws_b_c1_run.py"
        auth = json.loads((ROOT / "experiments" / "ws_b" / "CL_c1_authorisation.json").read_text())
        self.assertNotEqual(auth["status"], "approved")
        out = subprocess.run([sys.executable, str(h), "--db", "x.sqlite3", "--sets", "v7", "--repeats", "3", "--live"], capture_output=True, text=True)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("not approved", out.stderr + out.stdout)
        out = subprocess.run([sys.executable, str(h), "--db", "x.sqlite3", "--sets", "v7", "--mock", "oracle"], capture_output=True, text=True)
        self.assertIn("runs once", out.stderr + out.stdout)
