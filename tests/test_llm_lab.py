"""LLM lab tests with a fake client: no network, no spend. Uses a temporary COPY of the main database."""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compliance_agent.llm_lab import answer as A  # noqa: E402
from compliance_agent.llm_lab.budget import Ledger  # noqa: E402
from compliance_agent.llm_lab.fake import FakeClient  # noqa: E402
from compliance_agent.llm_lab.retrieve import connect_ro, file_md5  # noqa: E402
from compliance_agent.llm_lab.run import run  # noqa: E402

MAIN = ROOT / "data" / "CL_compliance.sqlite3"
CFG = json.loads((ROOT / "experiments" / "llm" / "CL_llm_experiment.json").read_text())


@unittest.skipUnless(MAIN.exists(), "main database not built")
class LLMLab(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        shutil.copy2(MAIN, d / "main.sqlite3")
        self.cfg = dict(CFG, main_db=str(d / "main.sqlite3"), experiment_db=str(d / "exp.sqlite3"))
        self.real_md5 = file_md5(MAIN)

    def tearDown(self):
        self.tmp.cleanup()
        self.assertEqual(file_md5(MAIN), self.real_md5)  # the real database is never touched

    def go(self, client, model="sonnet", qset="smoke", **cfg):
        return run(model, qset, client=client, cfg=dict(self.cfg, **cfg), log=lambda *_: None)

    def rows(self):
        con = sqlite3.connect(self.cfg["experiment_db"])
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute("SELECT * FROM llm_calls ORDER BY call_id")]

    def test_44_grounded_run_logs_everything_and_keeps_main_db(self):
        s = self.go(FakeClient("grounded"))
        self.assertIsNone(s["stop_reason"])
        self.assertTrue(s["main_db_unchanged"])
        rows = self.rows()
        self.assertEqual(len(rows), 10)
        r = rows[0]
        for k in ("model_returned", "retrieved_json", "response_text", "checks_json", "latency_ms", "input_tokens", "output_tokens", "cost_usd"):
            self.assertIsNotNone(r[k], k)
        self.assertEqual(r["model_returned"], "claude-sonnet-5-5")
        self.assertTrue(json.loads(r["checks_json"])["supported"])

    def test_45_budget_refuses_before_sending(self):
        fc = FakeClient("grounded")
        s = self.go(fc, authorized_usd=0.001)
        self.assertIn("budget", s["stop_reason"])
        self.assertEqual(fc.calls, 0)
        self.assertEqual(self.rows()[0]["status"], "refused_budget")

    def test_46_hard_ceiling_cannot_exceed_60(self):
        with self.assertRaises(ValueError):
            Ledger(Path(self.tmp.name) / "x.sqlite3", 100, 61)
        self.assertEqual(Ledger(Path(self.tmp.name) / "y.sqlite3", 100, 60).limit, 60)

    def test_47_invented_citations_and_numbers_are_caught_and_stop(self):
        s = self.go(FakeClient("invented"), stop_rules=dict(CFG["stop_rules"], unsupported_check_after_n=2))
        self.assertIn("unsupported-answer rate", s["stop_reason"])
        c = json.loads(self.rows()[0]["checks_json"])
        self.assertEqual(c["citations"][0]["result"], "unknown_passage")
        self.assertEqual(c["unsupported_numbers"], ["99,999"])

    def test_48_repeated_failures_and_billing_stop(self):
        self.assertIn("3 failed requests", self.go(FakeClient("error"))["stop_reason"])
        self.assertIn("402", self.go(FakeClient("billing"))["stop_reason"])

    def test_53_malformed_request_stops_at_first_400_with_message(self):
        fc = FakeClient("badrequest")
        s = self.go(fc)
        self.assertIn("malformed (400)", s["stop_reason"])
        self.assertIn("example problem", s["stop_reason"])
        self.assertEqual(fc.calls, 1)
        self.assertIn("example problem", self.rows()[0]["error"])

    def test_49_unknown_model_stops_before_any_spend(self):
        fc = FakeClient("unknown_model")
        s = self.go(fc)
        self.assertIn("not available", s["stop_reason"])
        self.assertEqual((fc.calls, len(self.rows())), (0, 0))

    def test_50_model_mismatch_stops(self):
        s = self.go(FakeClient("grounded", model_override="claude-other-model"))
        self.assertIn("not the requested", s["stop_reason"])

    def test_51_retrieval_connection_is_read_only(self):
        con = connect_ro(self.cfg["main_db"])
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("DELETE FROM passages")
        con.close()

    def test_52_citation_check_rules(self):
        passages = [{"passage_id": "P1", "text": "The Mandatory Registration Threshold shall be AED 375,000 (three hundred)."}]
        ok = A.check({"answer_status": "answered", "answer": "It is AED 375,000.", "citations": [{"passage_id": "P1", "quote": "Mandatory Registration Threshold shall be AED 375,000"}]}, passages)
        self.assertTrue(ok["supported"])
        spacing = A.check({"answer_status": "answered", "answer": "x", "citations": [{"passage_id": "P1", "quote": "MandatoryRegistration Threshold"}]}, passages)
        self.assertEqual(spacing["citations"][0]["result"], "spacing_only")
        bad = A.check({"answer_status": "answered", "answer": "It is AED 400,000.", "citations": [{"passage_id": "P1", "quote": "threshold is 400,000"}]}, passages)
        self.assertFalse(bad["supported"])
        self.assertEqual(bad["unsupported_numbers"], ["400,000"])
        echo = A.check({"answer_status": "answered", "answer": "Your AED 320,000 is below it; see Article 19, and Article 13.", "citations": [{"passage_id": "P1", "quote": "Mandatory Registration Threshold"}]}, passages, "I made AED 320,000.")
        self.assertEqual(echo["unsupported_numbers"], [])          # from the question / article references
        trail = A.check({"answer_status": "answered", "answer": "It is 187,500, and 999,999.", "citations": [{"passage_id": "P1", "quote": "Mandatory Registration Threshold"}]}, passages)
        self.assertEqual(trail["numbers_in_answer"], ["187,500", "999,999"])
        self.assertEqual(trail["unsupported_numbers"], ["187,500", "999,999"])  # still caught when not in a cited passage
        none = A.check({"answer_status": "answered", "answer": "Yes.", "citations": []}, passages)
        self.assertTrue(none["answered_without_citation"])
        self.assertFalse(none["supported"])


if __name__ == "__main__":
    unittest.main()


class GradingRules(unittest.TestCase):
    """Conditional explanations vs unsupported definitive advice (regression cases for D5)."""
    PH = ["you must register", "you have to register", "you do not need to register", "salary counts", "10,000"]
    CASES = [
        ("Whether you must register depends on a few facts we do not have.", False),
        ("If your supplies exceed AED 375,000, you must register.", False),
        ("You must register if your taxable supplies exceed the threshold.", False),
        ("The passages do not say whether salary counts towards the threshold.", False),
        ("This may mean you have to register; please confirm your figures.", False),
        ("It is unclear whether you have to register.", False),
        ("You must register.", True),
        ("Yes, you must register within 30 days.", True),
        ("Based on these figures, you have to register now.", True),
        ("You do not need to register.", True),
        ("Salary counts towards the threshold, not your expenses.", True),
        ("The penalty is AED 10,000.", True),
        ("If you are late, the penalty is AED 10,000.", True),
    ]

    def test_54_conditional_vs_definitive(self):
        for sentence, definitive in self.CASES:
            with self.subTest(sentence=sentence):
                self.assertEqual(bool(A.definitive_hits(sentence, self.PH)), definitive)

    def test_55_mixed_answer_flags_only_the_definitive_sentence(self):
        hits = A.definitive_hits("Whether you must register depends on your imports. Yes, you must register today.", self.PH)
        self.assertEqual([h["sentence"] for h in hits], ["Yes, you must register today."])

    def test_56_grade_uses_sentence_rule(self):
        q = {"expect_status": ["needs_facts"], "must_include": [], "must_not_include": ["you must register"]}
        ok = A.grade(q, {"answer_status": "needs_facts", "answer": "Whether you must register depends on facts."}, {"supported": True})
        bad = A.grade(q, {"answer_status": "needs_facts", "answer": "You must register."}, {"supported": True})
        self.assertTrue(ok["pass"])
        self.assertFalse(bad["pass"])


@unittest.skipUnless(MAIN.exists(), "main database not built")
class RetrievalFix(unittest.TestCase):
    def setUp(self):
        self.con = connect_ro(MAIN)
        self.qs = {q["id"]: q["text"] for q in json.loads((ROOT / "fixtures" / "CL_llm_eval_questions.json").read_text())["questions"]}

    def tearDown(self):
        self.con.close()

    def test_57_salary_question_now_retrieves_article_19(self):
        from compliance_agent.llm_lab.retrieve import search
        got = search(self.con, self.qs["Q04"])
        art19 = [p for p in got if p["source_id"] == "FTA-VAT-DL8" and p["locator"].startswith("Article 19,")]
        self.assertTrue(art19)
        self.assertTrue(art19[0]["added_by"] in ("heading", "bm25") or art19[0]["added_by"].startswith("intent:threshold_calculation"))
        self.assertIn("Calculating the Tax Registration Threshold", art19[0]["text"])

    def test_58_heading_retrieval_only_adds_never_replaces(self):
        from compliance_agent.llm_lab.retrieve import search
        for qid, text in self.qs.items():
            with self.subTest(q=qid):
                plain = [p["passage_id"] for p in search(self.con, text, heading_extra=0)]
                full = search(self.con, text)
                self.assertEqual([p["passage_id"] for p in full][:len(plain)], plain)   # original results never replaced
                added = full[len(plain):]
                self.assertLessEqual(sum(p["added_by"] == "heading" for p in added), 3)
                self.assertLessEqual(sum(p["added_by"].startswith("intent:") for p in added), 6)
                self.assertTrue(all(p["added_by"] == "heading" or p["added_by"].startswith("intent:") for p in added))


@unittest.skipUnless(MAIN.exists(), "main database not built")
class RetrievalVocabulary(unittest.TestCase):
    """Owner wording -> legal wording (D6 class). Each case failed before the fix."""
    CASES = {"Q11": ("FTA-VAT-DL8", (13, 18)), "Q25": ("FTA-VAT-DL8", (19,)),
             "Q26": ("FTA-VAT-DL8", (19,)), "Q28": ("FTA-VAT-DL8", (19,)), "Q35": ("FTA-VAT-DL8", (21, 23))}

    def test_59_vocabulary_cases_and_recall_gate(self):
        import re
        from compliance_agent.llm_lab.retrieve import search
        con = connect_ro(MAIN)
        qs = {q["id"]: q for q in json.loads((ROOT / "fixtures" / "CL_llm_eval_questions.json").read_text())["questions"]}
        for qid, (src, arts) in self.CASES.items():
            with self.subTest(q=qid):
                got = search(con, qs[qid]["text"])
                self.assertTrue(any(p["source_id"] == src and re.match(rf"Article ({'|'.join(map(str, arts))}),", p["locator"]) for p in got))
        hit = lambda p, s, a: p["source_id"] == s and (a is None or re.match(rf"Article {a}(,| \()", p["locator"]))
        with_src = [q for q in qs.values() if q.get("expected_sources")]
        ok = sum(any(hit(p, s, a) for p in search(con, q["text"]) for s, a in q["expected_sources"]) for q in with_src)
        self.assertGreaterEqual(ok / len(with_src), 0.90)   # gate before any paid evaluation
        con.close()


@unittest.skipUnless(MAIN.exists(), "main database not built")
class EvaluationReport(unittest.TestCase):
    def test_60_report_from_fake_runs_with_repeats(self):
        from compliance_agent.llm_lab import report as R
        with tempfile.TemporaryDirectory() as d:
            shutil.copy2(MAIN, Path(d) / "m.sqlite3")
            cfg = dict(CFG, main_db=str(Path(d) / "m.sqlite3"), experiment_db=str(Path(d) / "e.sqlite3"))
            for _ in range(2):
                run("sonnet", "evaluation_v2", client=FakeClient("grounded"), cfg=cfg, log=lambda *_: None)
            out = R.evaluate(R.load(Path(d) / "e.sqlite3", "2000-01-01"))
            s = out["sonnet"]
            self.assertEqual(s["answers"], 100)
            self.assertEqual(s["repeat_agreement"], 1.0)
            self.assertIn("retrieval_recall", s["verdict"])
            self.assertEqual(s["verdict"]["out_of_scope_declined"], "FAIL")   # the fake answers everything: must be caught


class FrozenUnseen(unittest.TestCase):
    def test_61_frozen_set_is_intact_and_guarded(self):
        from compliance_agent.llm_lab import freeze as F
        F.verify()                                             # the committed file matches its lock
        with tempfile.TemporaryDirectory() as d:
            changed = Path(d) / "u.json"
            changed.write_text(F.UNSEEN.read_text().replace("U24", "U99"))
            shutil.copy2(F.LOCK, Path(d) / "u.FROZEN.json")       # the original lock, the edited questions
            with self.assertRaises(SystemExit):
                F.verify(changed)
        F.verify(ROOT / "fixtures" / "CL_llm_eval_unseen_v2.json")  # v2 lock also intact
        data = json.loads(F.UNSEEN.read_text())
        self.assertEqual(len(data["questions"]), 24)
        self.assertTrue(set(data["unseen_opus"]) <= set(data["unseen_all"]))


@unittest.skipUnless(MAIN.exists(), "main database not built")
class KnownRegressions(unittest.TestCase):
    # was a known regression under v3 (marked expectedFailure); fixed by intent-specific retrieval (v4, 16 Oct)
    def test_62_Q18_deregistration_cases_KNOWN_REGRESSION(self):
        """Known regression (16 Oct, retrieval v3): Q18 'In what cases can my VAT registration be cancelled?' no longer
        retrieves Decree-Law Art. 21 / ER Art. 14 (it gets Art. 22/23, related deregistration articles). Reported, not hidden:
        this test is expected to fail until fixed; an unexpected pass will be reported by the test runner."""
        import re
        from compliance_agent.llm_lab.retrieve import search
        con = connect_ro(MAIN)
        q = [x for x in json.loads((ROOT / "fixtures" / "CL_llm_eval_questions.json").read_text())["questions"] if x["id"] == "Q18"][0]
        got = search(con, q["text"])
        con.close()
        self.assertTrue(any((p["source_id"] == "FTA-VAT-DL8" and re.match(r"Article 21,", p["locator"])) or
                            (p["source_id"] == "FTA-VAT-ER" and re.match(r"Article 14,", p["locator"])) for p in got))


@unittest.skipUnless(MAIN.exists(), "main database not built")
class RetrievalV3(unittest.TestCase):
    def test_63_amounts_and_concepts_detected(self):
        from compliance_agent.llm_lab.concepts import detect
        c, _ = detect("my sales are about 350k, am I ok?")
        self.assertIn("threshold", c)
        c, _ = detect("Can I cancel my VAT number?")
        self.assertIn("deregistration", c)

    def test_64_intent_provisions_only_for_registration_topics(self):
        from compliance_agent.llm_lab.retrieve import search
        con = connect_ro(MAIN)
        reg = search(con, "my sales are about 350k, am I ok?")
        off = search(con, "Do I need a privacy policy on my website under UAE law?")
        con.close()
        self.assertTrue(any(p["added_by"].startswith("intent:") for p in reg))
        self.assertFalse(any(p["added_by"].startswith("intent:") for p in off))

    def test_65_no_blanket_art7_for_deregistration_or_voluntary(self):
        # Adjustment 1 (16 Oct): ER Art. 7 (mandatory) is not injected into every registration question
        from compliance_agent.llm_lab.retrieve import search
        con = connect_ro(MAIN)
        for q in ("How do I cancel my VAT number?", "Can I register even though my sales are small?"):
            with self.subTest(q=q):
                inj = [p for p in search(con, q) if p["added_by"].startswith("intent:")]
                self.assertFalse(any(p["source_id"] == "FTA-VAT-ER" and p["locator"].startswith("Article 7,") for p in inj))
        con.close()

    def test_66_intent_detection_and_ambiguity(self):
        from compliance_agent.llm_lab.concepts import intents
        self.assertEqual(intents("How do I cancel my VAT number?"), (["deregistration"], False))
        self.assertEqual(intents("I crossed the limit last month"), (["mandatory_registration"], False))
        self.assertEqual(intents("Can I register even though my sales are small?")[0], ["voluntary_registration"])
        its, amb = intents("my sales are about 350k, am I ok?")
        self.assertTrue(amb)
        self.assertEqual(set(its), {"mandatory_registration", "voluntary_registration"})
        self.assertEqual(intents("Do I need a privacy policy?"), ([], False))

    def test_67_ambiguous_questions_get_alternatives_without_supporting(self):
        from compliance_agent.llm_lab.retrieve import search
        con = connect_ro(MAIN)
        inj = [p["added_by"] for p in search(con, "my sales are about 350k, am I ok?") if p["added_by"].startswith("intent:")]
        con.close()
        self.assertTrue(any("mandatory_registration" in a for a in inj) and any("voluntary_registration" in a for a in inj))
        self.assertTrue(all(a.endswith(":ambiguous") and ":primary" in a for a in inj))
