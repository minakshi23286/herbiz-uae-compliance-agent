"""Task 2 A-4: WS B v8 retrieval + WS C validity 1.2 on the unrecorded-question path. Tests t2i_01-12. Synthetic questions only.

D-102: v8 is an interim candidate; it never certifies completeness, so every unrecorded answer carries the incompleteness
warning. Fail closed on drifted frozen code or a missing database. Links are shown, never fetched. Recorded answers and
blocked questions are unchanged (CR-29: a blocked question is never searched)."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "contracts"))

from compliance_agent import ask as ASK, audit_log as AL, audit_sanitizer as S, t2_retrieval as R, web  # noqa: E402
from compliance_agent.clock import FixedClock  # noqa: E402
import validate as V  # noqa: E402

MAIN = ROOT / "data" / "CL_compliance.sqlite3"
LEDGER = ROOT / "data" / "CL_llm_experiment.sqlite3"
RET_SCHEMA = json.loads((ROOT / "contracts" / "retrieval_result_1.0.schema.json").read_text(encoding="utf-8"))
SV_SCHEMA = json.loads((ROOT / "contracts" / "source_validity_1.2.schema.json").read_text(encoding="utf-8"))
AUDIT_SCHEMA = json.loads((ROOT / "contracts" / "audit_record_1.0.schema.json").read_text(encoding="utf-8"))
H = {"Content-Type": "application/json", "X-Requested-With": "compliance-ui", "X-HerBiz-Session": "tti-session"}
VAT_Q = "What penalty applies if I file my VAT return late?"
OOS_Q = "How do I renew my trade licence?"
PII_Q = "My Emirates ID is 784-1990-1234567-1, do I need to register for VAT?"


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


@unittest.skipUnless(MAIN.exists(), "knowledge-base database not present on this computer")
class Retrieval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.tmp.name) / "kb.sqlite3"
        shutil.copyfile(MAIN, cls.db)                      # read the protected copy once; every test uses this copy
        cls.asker = ASK.Asker(cls.db, Path(cls.tmp.name) / "none.sqlite3", Path(cls.tmp.name) / "none.json")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_t2i_01_frozen_code_matches_ws_b_freeze_record(self):
        rec = json.loads((ROOT / "docs" / "CL_evidence" / "ws_b" / "t2" / "CL_t2_code_freeze.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["commit"], R.FREEZE_COMMIT); self.assertEqual(rec["config_sha256"], R.FREEZE_CONFIG_SHA256)
        for f, h in R.FROZEN_FILES.items():
            self.assertEqual(rec["files_sha256"][f], h, f)
        self.assertEqual(R.code_freeze()["files_sha256"], R.FROZEN_FILES)

    def test_t2i_02_payload_validates_and_never_certifies(self):
        out = self.asker.ask(VAT_Q)
        p = out["_retrieval"]
        self.assertEqual(V.errors(RET_SCHEMA, p), [])
        self.assertNotEqual(p["completeness"]["status"], "complete_for_map")
        self.assertTrue(all("text" not in i for i in p["items"]))                 # the audit copy never carries text
        self.assertEqual((p["retrieval_version"], p["execution_mode"]), ("v8", "deterministic"))
        self.assertLessEqual(len(p["items"]), p["budget"]["max_passages"])
        self.assertEqual(p["kb_snapshot"], {"snapshot_date": "2026-10-17", "db_md5": "26e202b87a062288e56bcda1de9b0217",
                                            "manifest_version": "0.2.1"})
        self.assertNotEqual(out["guard"]["level"], "complete_for_map")
        self.assertIn("may be incomplete", out["guard"]["message"])
        for n in ("68.5%", "66.7%", "70.4%", "70% target"):
            self.assertIn(n, out["interim_notice"])

    def test_t2i_03_passages_carry_ws_c_validity_and_links_are_not_fetched(self):
        def no_network(*a, **k):
            raise AssertionError("retrieval must never fetch a link")
        with mock.patch("urllib.request.urlopen", side_effect=no_network), mock.patch("http.client.HTTPConnection.connect", side_effect=no_network):
            out = self.asker.ask(VAT_Q)
        self.assertTrue(out["passages"])
        self.assertLessEqual(len(out["passages"]), R.SHOWN)
        statuses = {x["validity"]["status"] for x in out["passages"]}
        self.assertTrue(statuses & {"outdated", "conflict"}, statuses)          # this question hits amended / conflicting texts
        for x in out["passages"]:
            v = x["validity"]
            if v["current_official_url"]:
                self.assertTrue(v["current_official_url"].startswith("https://"))
                self.assertIn("not been checked by a person", v["note"])     # portal 1227/1972: contents not checked (D-101 amended)

    def test_t2i_04_validity_lookup_is_the_ws_c_rc2_export(self):
        data = json.loads(R.VALIDITY_FILE.read_text(encoding="utf-8"))
        self.assertEqual(len(data["payloads"]), 110)
        for p in data["payloads"]:
            self.assertEqual(V.errors(SV_SCHEMA, p), [], p["key"])
        self.assertEqual(R.validity("FTA-VAT-DL8", "48")["status"], "outdated")   # falls back to the whole-source payload
        self.assertNotEqual(R.validity("FTA-VAT-DL8", "48")["review_status"], "approved")

    def test_t2i_05_out_of_scope_shows_no_passages_and_says_the_check_can_be_wrong(self):
        out = self.asker.ask(OOS_Q)
        self.assertEqual((out["scope"], out["passages"]), ("out_of_scope", []))
        self.assertIn("can be wrong", out["answer"]); self.assertIn("not an answer", out["answer"])
        self.assertEqual(out["_retrieval"]["scope"]["class"], "out_of_scope")

    def test_t2i_06_fail_closed_on_drifted_code_or_missing_database(self):
        with mock.patch.dict(R.FROZEN_FILES, {"compliance_agent/llm_lab/retrieve_v8.py": "0" * 64}):
            out = self.asker.ask(VAT_Q)
        self.assertEqual((out["status"], out["passages"], out["_retrieval"]), ("retrieval_unavailable", [], None))
        gone = ASK.Asker(Path(self.tmp.name) / "absent.sqlite3", Path(self.tmp.name) / "none.sqlite3", Path(self.tmp.name) / "none.json")
        out = gone.ask(VAT_Q)
        self.assertEqual((out["status"], out["passages"]), ("retrieval_unavailable", []))
        self.assertTrue(out["professional"])

    @unittest.skipUnless(LEDGER.exists(), "experiment ledger not present on this computer")
    def test_t2i_07_recorded_answers_are_unchanged(self):
        a = ASK.Asker(self.db, LEDGER)
        r = a.ask(qid="Q35")
        self.assertEqual(r["mode"], "recorded"); self.assertNotIn("_retrieval", r)


@unittest.skipUnless(MAIN.exists(), "knowledge-base database not present on this computer")
class Web(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        shutil.copyfile(MAIN, d / "w.sqlite3")
        self.app = web.App(d / "w.sqlite3", FixedClock("2026-10-17T10:00:00"), d / "none.sqlite3")
        self.app._asker = ASK.Asker(d / "w.sqlite3", d / "none.sqlite3", d / "none.json")
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(self.app))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.app.engine.s.close(); self.tmp.cleanup()

    def post(self, q):
        req = urllib.request.Request(self.base + "/api/ask", method="POST", data=json.dumps({"q": q}).encode(), headers=H)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.headers.get("X-HerBiz-Audit-Record"), r.read()
        except urllib.error.HTTPError as ex:
            with ex:
                return ex.code, None, ex.read()

    def records(self):
        f = self.app.audit.files()[0]
        return {json.loads(x)["record_id"]: json.loads(x) for x in f.read_bytes().splitlines()}

    def test_t2i_08_owner_response_has_no_reviewer_detail_and_the_record_has_the_payload(self):
        code, rid, body = self.post(VAT_Q)
        self.assertEqual(code, 200)
        out = json.loads(body)
        for k in ("_retrieval", "trace", "required_provisions", "code_freeze"):
            self.assertNotIn(f'"{k}"', body.decode("utf-8"))
        rec = self.records()[rid]
        self.assertEqual(V.errors(AUDIT_SCHEMA, rec), []); self.assertEqual(S.check(rec), [])
        self.assertEqual(rec["retrieval"]["retrieval_version"], "v8")
        self.assertNotIn('"text"', json.dumps(rec))
        self.assertIn("may_be_incomplete", rec["answer"]["flags"])
        self.assertTrue(any(s["validity"] for s in rec["sources"]))
        if any(p["validity"]["status"] == "outdated" for p in out["passages"]):
            self.assertIn("stale_source", rec["answer"]["flags"])
        self.assertTrue(AL.verify(self.app.audit.files()[0], str(self.app.db_path))[0])
        self.assertEqual(AL.scan(self.app.audit.folder), [])

    def test_t2i_09_blocked_question_is_never_searched(self):
        with mock.patch.object(R, "retrieve", side_effect=AssertionError("a blocked question must not be searched")):
            code, rid, body = self.post(PII_Q)
        self.assertEqual(code, 200)
        rec = self.records()[rid]
        self.assertEqual((rec["retrieval"], rec["request"]["query_text"], rec["request"]["query_sha256"]), (None, None, None))
        self.assertNotIn("1234567", json.dumps(rec))                      # t2a_03 has the full personal-data sweep

    def test_t2i_10_out_of_scope_is_audited_with_its_classification(self):
        code, rid, body = self.post(OOS_Q)
        rec = self.records()[rid]
        self.assertEqual(rec["retrieval"]["scope"]["class"], "out_of_scope")
        self.assertEqual(json.loads(body)["passages"], [])
        self.assertEqual(rec["sources"], [])


@unittest.skipUnless(MAIN.exists(), "protected database not present on this computer")
class Protected(unittest.TestCase):
    def test_t2i_11_protected_databases_unchanged(self):
        self.assertEqual(md5(MAIN), "26e202b87a062288e56bcda1de9b0217")
        if LEDGER.exists():
            self.assertEqual(md5(LEDGER), "59226cd03eb7105d635538d7da738949")


class Export(unittest.TestCase):
    def test_t2i_12_export_scrub_never_alters_app_code_and_ships_the_contracts(self):
        # the submission export rewrites absolute local paths; app code must contain none, or the export breaks (A-4 defect)
        sys.path.insert(0, str(ROOT / "experiments" / "ws_a"))
        import CL_build_submission_export as B
        hits = [str(p.relative_to(ROOT)) for p in sorted((ROOT / "compliance_agent").rglob("*.py")) if B.PATH_RE.search(p.read_bytes())]
        self.assertEqual(hits, [])
        self.assertIn("contracts/", B.INCLUDE)


if __name__ == "__main__":
    unittest.main()
