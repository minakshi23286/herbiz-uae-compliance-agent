"""CX backlog (Workstream A, approved 16 Oct 2026): recorded-answer Ask panel, incompleteness guard, onboarding.
No network, no AI calls, no spend. The real database is only ever opened read-only here."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent.ask import Asker, guard  # noqa: E402
from compliance_agent.clock import FixedClock  # noqa: E402

MAIN = ROOT / "data" / "CL_compliance.sqlite3"
DL, ER, PAGE = "FTA-VAT-DL8", "FTA-VAT-ER", "FTA-VAT-REG-PAGE"
P = lambda src, art: {"source_id": src, "locator": f"Article {art}, p. 1" if art else "Paragraph 1"}


def fake_ledger(path: Path, rows: list[tuple]) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE llm_calls (call_id INTEGER PRIMARY KEY, run_id TEXT, at TEXT, question_id TEXT, model_alias TEXT,"
                " model_returned TEXT, status TEXT, retrieved_json TEXT, parsed_json TEXT, checks_json TEXT)")
    for qid, parsed, seen, supported in rows:
        con.execute("INSERT INTO llm_calls (run_id, at, question_id, model_alias, model_returned, status, retrieved_json, parsed_json, checks_json)"
                    " VALUES ('RUN-T', '2026-10-16T19:00:00', ?, 'sonnet', 'claude-sonnet-5-5', 'ok', ?, ?, ?)",
                    (qid, json.dumps(seen), json.dumps(parsed), json.dumps({"supported": supported})))
    con.commit(); con.close()


class Guard(unittest.TestCase):
    def test_70_complete_when_primary_provisions_seen(self):
        g = guard("How do I cancel my VAT number?", [P(DL, 21), P(ER, 14)], "answered")
        self.assertEqual(g["level"], "complete_for_map")
        self.assertNotIn("verified", g["message"].lower())

    def test_71_incomplete_names_missing_provisions(self):
        g = guard("How do I cancel my VAT number?", [P(DL, 21), P(DL, 13)], "answered")
        self.assertEqual(g["level"], "incomplete")
        self.assertEqual(g["missing"], ["VAT Executive Regulation, Article 14"])

    def test_72_ambiguous_needs_all_alternatives(self):
        g = guard("my sales are about 350k, am I ok?", [P(DL, 13), P(ER, 7)], "needs_facts")
        self.assertEqual(g["level"], "incomplete")          # voluntary alternative (DL 17, ER 8) missing

    def test_73_unmapped_topic_is_unchecked_and_refusals_not_applicable(self):
        self.assertEqual(guard("Is my perfume halal certified?", [], "answered")["level"], "unchecked")
        self.assertEqual(guard("cancel my VAT number", [], "declined")["level"], "not_applicable")


class Recorded(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.tmp.name) / "ledger.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_74_exact_question_replays_recorded_answer_with_provenance(self):
        fake_ledger(self.ledger, [("Q18", {"answer_status": "answered", "answer": "Two routes.", "citations": [], "missing_facts": []},
                                   [P(DL, 21)], True)])
        a = Asker(MAIN, self.ledger)
        r = a.ask("  in what cases can my VAT registration be CANCELLED ")
        self.assertEqual((r["mode"], r["question_id"], r["status"]), ("recorded", "Q18", "answered"))
        self.assertIn("No AI was called", r["provenance"]["note"])
        self.assertEqual(r["guard"]["level"], "incomplete")     # ER Art. 14 was not in what the model saw
        self.assertTrue(r["professional"])

    def test_75_unsupported_answer_is_never_shown_as_complete(self):
        fake_ledger(self.ledger, [("Q18", {"answer_status": "answered", "answer": "x", "citations": [], "missing_facts": []},
                                   [P(DL, 21), P(ER, 14)], False)])
        r = Asker(MAIN, self.ledger).ask(qid="Q18")
        self.assertEqual(r["guard"]["level"], "incomplete")

    def test_76_other_questions_get_no_answer_and_professional_box(self):
        fake_ledger(self.ledger, [])
        r = Asker(MAIN, self.ledger).ask("Which bank is best for my business account?")
        self.assertEqual(r["mode"], "no_recording")
        self.assertIn("not an answer", r["answer"].lower())
        self.assertTrue(r["professional"])

    def test_77_missing_ledger_is_handled(self):
        a = Asker(MAIN, Path(self.tmp.name) / "absent.sqlite3", Path(self.tmp.name) / "absent.json")   # no ledger, no answers file
        self.assertEqual(a.examples(), [])
        self.assertEqual(a.ask("anything")["mode"], "no_recording")


class Onboarding(unittest.TestCase):
    def test_78_onboarding_creates_profile_and_runs_checks(self):
        from compliance_agent.web import App
        with tempfile.TemporaryDirectory() as d:
            app = App(Path(d) / "cx.sqlite3", FixedClock("2026-10-16T10:00:00"), Path(d) / "none.sqlite3")
            try:
                app.onboard({"display_name": "Fatima Henna", "jurisdiction": "AE-DU", "activity": "beauty",
                             "sales_last_12m_aed": "400000", "expected_next_30d_aed": "", "vat_registered": "false",
                             "licensing_context": "home_based_licence"})
                st = app.engine.state()
                p = st["profiles"][0]
                self.assertEqual(p["display_name"], "Fatima Henna (synthetic)")
                self.assertEqual(p["taxable_supplies"]["total_aed"], 400000)
                self.assertIsNone(p["facts"].get("expected_taxable_supplies_next_30d_aed"))   # unknown stays unknown
                self.assertIn("0", app.stages_done()); self.assertIn("1", app.stages_done())
                keys = {a["obligation_key"]: a["result"] for a in st["assessments"]}
                self.assertNotEqual(keys.get("VAT-MANDATORY-REG"), "not_applicable")
                app.onboard({"jurisdiction": "AE-DU", "activity": "beauty", "sales_last_12m_aed": "100000", "vat_registered": "unsure"})
                p = app.engine.state()["profiles"][0]
                self.assertEqual((p["version"], p["facts"].get("vat_registered")), (2, None))
            finally:
                app.engine.s.close()


class Endpoints(unittest.TestCase):
    def test_79_ask_and_onboard_endpoints(self):
        from http.server import ThreadingHTTPServer
        from compliance_agent.web import App, make_handler
        with tempfile.TemporaryDirectory() as d:
            ledger = Path(d) / "ledger.sqlite3"
            fake_ledger(ledger, [("U10", {"answer_status": "needs_facts", "answer": "Over what period?", "citations": [],
                                          "missing_facts": ["period"]}, [], True)])
            app = App(Path(d) / "cx.sqlite3", FixedClock("2026-10-16T10:00:00"), ledger)
            srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            try:
                with urllib.request.urlopen(base + "/api/ask?id=U10") as r:
                    j = json.loads(r.read())
                self.assertEqual((j["status"], j["status_plain"]), ("needs_facts", "I need a few facts first"))
                with urllib.request.urlopen(base + "/api/ask/examples") as r:
                    self.assertEqual([x["id"] for x in json.loads(r.read())["examples"]], ["U10"])
                req = urllib.request.Request(base + "/api/onboard", method="POST",
                                             data=json.dumps({"jurisdiction": "AE-SH", "activity": "home_food", "sales_last_12m_aed": "abc"}).encode(),
                                             headers={"Content-Type": "application/json", "X-Requested-With": "compliance-ui"})
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    urllib.request.urlopen(req)
                self.assertEqual(cm.exception.code, 400)                     # bad number is refused, not guessed
                with urllib.request.urlopen(base + "/") as r:
                    page = r.read().decode()
                self.assertIn("Ask a question", page); self.assertIn("TEST RULE — made up, not the law", page)
            finally:
                srv.shutdown(); app.engine.s.close()


if __name__ == "__main__":
    unittest.main()


LEDGER = ROOT / "data" / "CL_llm_experiment.sqlite3"


@unittest.skipUnless(LEDGER.exists() and MAIN.exists(), "recorded answers not present on this computer")
class SafetyOverRecordedAnswers(unittest.TestCase):
    """P0 safety (16 Oct): every recorded answer that lacks a mandatory (primary) provision is flagged incomplete."""

    def test_84_missing_primary_provision_always_flagged(self):
        from compliance_agent.ask import _art
        from compliance_agent.llm_lab.concepts import INTENT_PROVISIONS, intents
        a = Asker(MAIN, LEDGER)
        for qid, rec in a.recorded.items():
            with self.subTest(q=qid):
                r = a.ask(qid=qid)
                if r["status"] in ("declined", "not_covered", "withheld_source_status"):   # rc3: withheld shows no answer
                    continue
                its, _ = intents(r["question"])
                seen = json.loads(rec["retrieved_json"] or "[]")
                have = {(p["source_id"], _art(p["locator"])) for p in seen}
                page = any(p["source_id"] == PAGE for p in seen)
                lacks = any(not (page if s == PAGE else (s, str(art)) in have)
                            for it in its for s, art in INTENT_PROVISIONS[it]["primary"])
                if lacks or not json.loads(rec["checks_json"] or "{}").get("supported", False):
                    self.assertEqual(r["guard"]["level"], "incomplete")
                if not its:
                    self.assertNotEqual(r["guard"]["level"], "complete_for_map")


class WordingWithoutLedger(unittest.TestCase):
    """A-7 (D-098): test 85 checks page wording only, so it no longer sits in the ledger-dependent class above."""

    def test_85_never_described_as_legally_verified(self):
        ui = (ROOT / "compliance_agent" / "ui.html").read_text(encoding="utf-8").lower()
        for bad in ("legally verified", "verified answer", "verified by a", "verified advice", "approved source"):
            self.assertNotIn(bad, ui.replace("never means legally", "").replace("/the approved source/g", ""))   # the regex that rewrites it
        self.assertIn("still not checked by a qualified tax professional", (ROOT / "compliance_agent" / "ask.py").read_text().lower())
