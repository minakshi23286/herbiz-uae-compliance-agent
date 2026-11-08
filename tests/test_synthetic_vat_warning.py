"""Task 2 A-7: the VAT "may be incomplete" warning on a synthetic, redistribution-safe fixture (D-098). Tests t2v_01-06.

Runs in the public export, where the real recorded answers are held back. The fixture holds no legal text (a fixed synthetic
label, source ids and article locators only). What it proves: the warning and refusal logic works on safe data for the
defined cases. What it does not prove: anything about the quality of the real recorded answers or about retrieval recall."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent import ask as ASK  # noqa: E402
from compliance_agent.ask import _art  # noqa: E402
from compliance_agent.llm_lab.concepts import INTENT_PROVISIONS, intents  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "CL_synthetic_vat_answers.json"
PAGE = "FTA-VAT-REG-PAGE"


class SyntheticWarning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.a = ASK.Asker(d / "absent.sqlite3", d / "absent_ledger.sqlite3", FIXTURE)    # no database, no ledger: fixture only

    def tearDown(self):
        self.tmp.cleanup()

    def test_t2v_01_fixture_is_current_and_holds_no_legal_text(self):
        p = subprocess.run([sys.executable, str(ROOT / "experiments" / "ws_a" / "CL_build_synthetic_vat_fixture.py"), "--check"],
                           capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(p.returncode, 0, p.stdout)
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for qid, r in data["answers"].items():
            parsed = json.loads(r["parsed_json"])
            self.assertTrue(parsed["answer"].startswith("SYNTHETIC TEST ANSWER"))
            for c in parsed["citations"]:                                  # rc3 cases: a synthetic label, never official text
                self.assertTrue(c["quote"].startswith("SYNTHETIC QUOTE"))
            self.assertTrue(all(p["text"] == "" for p in r["passages"].values()))
            self.assertEqual(r["model_returned"], "none (synthetic fixture)")
            for p_ in json.loads(r["retrieved_json"]):
                self.assertNotIn("text", p_)
        self.assertNotIn("tests/fixtures", (ROOT / "compliance_agent" / "ask.py").read_text(encoding="utf-8"))   # demo never loads it

    def test_t2v_02_test84_rule_holds_on_every_synthetic_record(self):
        for qid, rec in self.a.recorded.items():
            with self.subTest(q=qid):
                r = self.a.ask(qid=qid)
                if r["status"] in ("declined", "not_covered", "withheld_source_status"):
                    continue
                its, _ = intents(r["question"])
                seen = json.loads(rec["retrieved_json"] or "[]")
                have = {(p["source_id"], _art(p["locator"])) for p in seen}
                page = any(p["source_id"] == PAGE for p in seen)
                lacks = any(not (page if s == PAGE else (s, str(art)) in have)
                            for it in its for s, art in INTENT_PROVISIONS[it]["primary"])
                if lacks or not json.loads(rec["checks_json"] or "{}").get("supported", False):
                    self.assertEqual(r["guard"]["level"], "incomplete")

    def test_t2v_03_missing_articles_are_named(self):
        r = self.a.ask(qid="Q35")
        self.assertEqual(r["guard"]["level"], "incomplete")
        self.assertTrue(any("Article 21" in m for m in r["guard"]["missing"]), r["guard"]["missing"])
        self.assertTrue(r["professional"])

    def test_t2v_04_declined_and_unreliable_quote(self):
        u22 = self.a.ask(qid="U22")
        self.assertEqual((u22["status"], u22["professional"]), ("declined", True))
        u10 = self.a.ask(qid="U10")
        self.assertEqual(u10["guard"]["level"], "incomplete")
        self.assertIn("unreliable", u10["guard"]["message"])

    def test_t2v_05_control_case_complete_for_map_is_still_not_checked(self):
        r = self.a.ask(qid="Q13")
        self.assertEqual(r["guard"]["level"], "complete_for_map")
        self.assertIn("Still not checked by a qualified tax professional", r["guard"]["message"])

    def test_t2v_06_scenarios_E10_E11_run_on_the_fixture_and_say_so(self):
        from unittest import mock
        sys.path.insert(0, str(ROOT / "experiments" / "ws_a"))
        import CL_error_scenarios as ES
        absent = Path(self.tmp.name)
        with mock.patch.object(ES, "LEDGER", absent / "no_ledger.sqlite3"), mock.patch.object(ASK, "RECORDED_FILE", absent / "none.json"):
            plain = {r["id"]: r["result"] for r in ES.scenarios()}
            synth = {r["id"]: r for r in ES.scenarios(synthetic_answers=True)}
        self.assertEqual((plain["E10"], plain["E11"]), ("SKIPPED", "SKIPPED"))           # never silently synthetic
        self.assertEqual((synth["E10"]["result"], synth["E11"]["result"]), (ES.SYNTH_PASS, ES.SYNTH_PASS))
        self.assertIn("synthetic fixture", synth["E10"]["evidence"])
        self.assertNotIn("FAIL", {r["result"] for r in synth.values()})


if __name__ == "__main__":
    unittest.main()
