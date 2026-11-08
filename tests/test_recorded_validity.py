"""rc3 item 1 (founder/CTO 19 Oct 2026, Option A): article-level source status on RECORDED answers. Tests t3r_01-08.

Rule M4 (WS A + WS C): an article-level record decides; a whole-source amendment counts only for the articles it lists; a
whole-source status is never inherited by an unlisted article. superseded / outdated -> the answer is withheld (no answer
text, no quotes, no passage text); conflict -> withheld and escalated; otherwise shown, with a source-level note. The
free-typed path (item 1b) and the link-check rule (item 3) are deliberately unchanged in rc3."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "contracts"))

from compliance_agent import ask as ASK, audit_sanitizer as S, t2_retrieval as R, web  # noqa: E402
from compliance_agent.clock import FixedClock  # noqa: E402
import validate as V  # noqa: E402

MAIN = ROOT / "data" / "CL_compliance.sqlite3"
LEDGER = ROOT / "data" / "CL_llm_experiment.sqlite3"
FIXTURE = ROOT / "tests" / "fixtures" / "CL_synthetic_vat_answers.json"
AUDIT_SCHEMA = json.loads((ROOT / "contracts" / "audit_record_1.0.schema.json").read_text(encoding="utf-8"))
CHIPS = ["Q13", "U10", "Q35", "U14", "U18", "U22"]
H = {"Content-Type": "application/json", "X-Requested-With": "compliance-ui", "X-HerBiz-Session": "rc-three"}


def no_network(*a, **k):
    raise AssertionError("a source link must never be fetched")


class Synthetic(unittest.TestCase):                       # public: needs no database and no ledger
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); d = Path(self.tmp.name)
        self.a = ASK.Asker(d / "absent.sqlite3", d / "absent_ledger.sqlite3", FIXTURE)

    def tearDown(self):
        self.tmp.cleanup()

    def test_t3r_01_superseded_amended_and_conflict_articles_withhold_the_answer(self):
        with mock.patch("urllib.request.urlopen", side_effect=no_network):
            for qid, st, word in (("SYN-79BIS", "superseded", "repealed or replaced"), ("SYN-ART48", "outdated", "amended"),
                                  ("SYN-ER14", "conflict", "disagree")):
                r = self.a.ask(qid=qid)
                self.assertEqual(r["status"], "withheld_source_status", qid)
                self.assertIn(word, r["answer"]); self.assertNotIn("SYNTHETIC TEST ANSWER", r["answer"])
                self.assertTrue(all(s["quote"] == "" and s["text"] == "" for s in r["sources"]), qid)   # nothing replayed
                self.assertEqual(r["sources"][0]["validity"]["status"], st)
                self.assertTrue(r["professional"])
        self.assertIn("FTA-registered tax agent", self.a.ask(qid="SYN-ER14")["answer"])

    def test_t3r_02_whole_source_status_is_not_inherited_by_an_unlisted_article(self):
        r = self.a.ask(qid="SYN-ART13")
        self.assertEqual(r["status"], "answered")
        v = r["sources"][0]["validity"]
        self.assertEqual(v["status"], "not_listed_as_amended")
        self.assertIn("48, 54 (bis), 74, 79 (bis)", v["plain"]); self.assertIn("not listed as changed", v["plain"])

    def test_t3r_03_rule_m4_lookup(self):
        self.assertEqual(R.article_status("FTA-VAT-DL8", "79 (bis)")[1], "article")
        self.assertEqual(R.article_status("FTA-VAT-DL8", "13")[1], "source")
        self.assertIsNone(R.effective_status(*R.article_status("FTA-VAT-DL8", "13")))
        self.assertEqual(R.effective_status(*R.article_status("FTA-VAT-DL8", "79 (bis)")), "superseded")
        self.assertEqual(R.article_status("NO-SUCH-SOURCE", "1"), (None, "none"))

    def test_t3r_04_free_typed_path_and_link_rule_unchanged_in_rc3(self):
        # items 1b and 3 deferred (CTO 19 Oct): validity() still falls back to the whole source, and the link note is unchanged
        self.assertEqual(R.validity("FTA-VAT-DL8", "13")["status"], "outdated")
        v = R.owner_validity(R.validity("FTA-VAT-DL8", "79 (bis)"))
        self.assertEqual(v["note"], "The current official page has not been checked by a person yet.")

    def test_t3r_05_withheld_answer_audit_record_is_valid_clean_and_flagged(self):
        d = Path(self.tmp.name)
        app = web.App(d / "w.sqlite3", FixedClock("2026-10-17T10:00:00"), d / "none.sqlite3", audit_dir=d / "logs")
        app._asker = self.a
        srv = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(app))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/ask?id=SYN-79BIS", headers=H)
            with urllib.request.urlopen(req) as resp:
                rid = resp.headers.get("X-HerBiz-Audit-Record"); body = json.loads(resp.read())
        finally:
            srv.shutdown(); srv.server_close(); app.engine.s.close()
        self.assertEqual(body["status"], "withheld_source_status")
        rec = {json.loads(x)["record_id"]: json.loads(x) for f in app.audit.files() for x in f.read_bytes().splitlines()}[rid]
        self.assertEqual(V.errors(AUDIT_SCHEMA, rec), []); self.assertEqual(S.check(rec), [])
        self.assertEqual((rec["answer"]["mode"], rec["answer"]["status"]), ("recorded", "withheld_source_status"))
        self.assertIn("stale_source", rec["answer"]["flags"])
        self.assertEqual(rec["sources"][0]["validity"]["status"], "superseded")


@unittest.skipUnless(MAIN.exists() and LEDGER.exists(), "recorded answers not present on this computer")
class Recorded(unittest.TestCase):                        # internal: the real recorded answers (ledger)
    @classmethod
    def setUpClass(cls):
        cls.a = ASK.Asker(MAIN, LEDGER)

    def test_t3r_06_V24_is_withheld_without_its_text_and_the_link_is_not_fetched(self):
        with mock.patch("urllib.request.urlopen", side_effect=no_network):
            r = self.a.ask(qid="V24")
        self.assertEqual(r["status"], "withheld_source_status")
        self.assertIn("Article 79 (bis)", r["answer"]); self.assertIn("2026-01-01", r["answer"])
        self.assertTrue(all(s["quote"] == "" and s["text"] == "" for s in r["sources"]))
        bis = [s for s in r["sources"] if "79 (bis)" in s["where"]][0]["validity"]
        self.assertEqual(bis["status"], "superseded"); self.assertTrue(bis["current_official_url"].startswith("https://"))

    def test_t3r_07_before_after_only_V24_changes(self):
        changed = []
        for qid, rec in self.a.recorded.items():
            before = json.loads(rec["parsed_json"]).get("answer_status")
            after = self.a.ask(qid=qid)["status"]
            if before != after:
                changed.append(qid)
        self.assertEqual(changed, ["V24"])
        self.assertEqual(len(self.a.recorded), 98)

    def test_t3r_08_demo_chips_are_not_withheld(self):
        for q in CHIPS:
            r = self.a.ask(qid=q)
            self.assertNotEqual(r["status"], "withheld_source_status", q)
            self.assertTrue(r["answer"])


if __name__ == "__main__":
    unittest.main()
