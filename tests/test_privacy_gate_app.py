"""CR-29 / D-088 (WS A): the personal-data intake gate wired into the app. Tests 123-133 (WS C acceptance tests AT-1..AT-10). Synthetic values only.

R1 gate first on the server for the Ask question and reviewer notes; R2 no free text in URLs; R3 notes gated and never in
the owner view or exports; R4 logs hold identifiers only; R5 fail closed when the gate or its KB fails."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
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
sys.path.insert(0, str(ROOT))

from compliance_agent import ask as ASK, web  # noqa: E402
from compliance_agent.clock import FixedClock  # noqa: E402
from compliance_agent.rag_c import policy_gate as PG  # noqa: E402

UI = {"Content-Type": "application/json", "X-Requested-With": "compliance-ui"}
PD_QUESTION = "My customer Fatima, Emirates ID 784-1990-1234567-1, still owes me AED 5,000 — do I charge VAT?"
CLEAN_QUESTION = "My customer still owes me AED 5,000 — do I charge VAT?"
FRAGMENTS = ("784", "1990", "1234567", "Fatima", "fatima.example", "0501234567")
LOG_KEYS = {"event", "entry", "action", "control_ids", "detector_ids", "clause_ids", "kb_version", "kb_sha256"}


class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.app = web.App(d / "w.sqlite3", FixedClock("2026-10-17T10:00:00"), d / "no_ledger.sqlite3")
        self.app._asker = ASK.Asker(d / "w.sqlite3", d / "no_ledger.sqlite3", d / "no_answers.json")
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(self.app))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.err = io.StringIO()
        self._redirect = contextlib.redirect_stderr(self.err)
        self._redirect.__enter__()

    def tearDown(self):
        self._redirect.__exit__(None, None, None)
        self.srv.shutdown(); self.srv.server_close()
        self.app.engine.s.close()
        self.tmp.cleanup()

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None, headers=UI)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as ex:
            with ex:
                return ex.code, ex.read().decode()

    def assert_no_fragment(self, text):
        for f in FRAGMENTS:
            self.assertNotIn(f, text)

    def test_123_blocked_question_never_reaches_search_and_is_not_echoed(self):
        with mock.patch.object(self.app.asker, "ask", wraps=self.app.asker.ask) as spy:
            code, body = self.call("/api/ask", {"q": PD_QUESTION})
            self.assertEqual(code, 200)
            spy.assert_not_called()                                    # R1: no search, no answer step
        r = json.loads(body)
        self.assertEqual((r["mode"], r["question"]), ("blocked", ""))
        self.assertIn("Please remove personal details", r["answer"])
        self.assertIn("PDPL-ART4", r["design_references"])             # shown only as design references
        self.assertIn("Not a legal finding", r["design_references_note"])
        for word in ("violation", "breach", "not allowed by law"):
            self.assertNotIn(word, body.lower())
        self.assert_no_fragment(body)
        code, body = self.call("/api/ask", {"q": CLEAN_QUESTION})     # the cleaned question is processed normally
        self.assertEqual(json.loads(body)["mode"], "no_recording")

    def test_124_free_text_in_the_url_is_refused_and_fixed_ids_still_work(self):
        with mock.patch.object(self.app.asker, "ask", wraps=self.app.asker.ask) as spy:
            code, body = self.call("/api/ask?q=" + urllib.request.quote(PD_QUESTION))
            self.assertEqual(code, 400)
            self.assertIn("request body", body)
            spy.assert_not_called()
            for extra in ("?id=Q35&q=hello", "?question=hello"):
                self.assertEqual(self.call("/api/ask" + extra)[0], 400)
        self.assert_no_fragment(body)
        code, body = self.call("/api/ask?id=Q35")                      # fixed example ids (the demo) keep working
        self.assertEqual(code, 200)
        self.assertEqual(self.call("/api/ask", {"id": "Q35"})[0], 200)
        self.assertEqual(len(self.app.gate_log), 0)                    # refused before the gate: nothing logged
        page = (ROOT / "compliance_agent" / "ui.html").read_text(encoding="utf-8")
        self.assertNotIn('"q=" + encodeURIComponent', page)            # the client never puts a question in a URL
        self.assertIn('api("/api/ask", {q})', page)

    def test_125_blocked_reviewer_note_is_not_stored_and_notes_never_reach_the_owner(self):
        e = self.app.engine
        n0 = e.s.db.execute("SELECT COUNT(*) FROM reviewer_signoffs").fetchone()[0]
        a0 = e.s.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
        bad = {"item_type": "obligation", "item_id": "SYN-OB-1", "reviewer": "Test Reviewer (synthetic)",
               "qualification": "synthetic test role", "decision": "agree", "note": "Owner's phone 0501234567, call her"}
        code, body = self.call("/api/signoff", bad)
        self.assertEqual(code, 400)
        self.assertTrue(json.loads(body)["blocked"])
        self.assert_no_fragment(body)
        self.assertEqual(e.s.db.execute("SELECT COUNT(*) FROM reviewer_signoffs").fetchone()[0], n0)   # nothing written
        self.assertEqual(e.s.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], a0)        # nothing audited
        ok = dict(bad, note="SYNTHETIC-NOTE-7Q: source wording checked against the copy")
        self.assertEqual(self.call("/api/signoff", ok)[0], 200)
        for path in ("/api/360/content", "/api/360/finance", "/api/360/finance.csv", "/api/360/change"):
            code, body = self.call(path)
            self.assertNotIn("SYNTHETIC-NOTE-7Q", body, path)                                         # owner view and export
        code, body = self.call("/api/360/dashboard", {"profile_id": "SYN-AMAL-B"})
        self.assertNotIn("SYNTHETIC-NOTE-7Q", body)

    def test_126_review_context_note_is_gated(self):
        code, body = self.call("/api/review", {"kind": "case", "case_id": "CASE-0001", "decision": "approve",
                                                "reviewer": "x", "role": "y", "context": "email fatima.example@mail.test"})
        self.assertEqual(code, 400)
        self.assertTrue(json.loads(body)["blocked"])
        self.assert_no_fragment(body)

    def test_127_logs_hold_identifiers_only(self):
        self.call("/api/ask", {"q": PD_QUESTION})
        self.call("/api/ask", {"q": "Reach me at fatima.example@mail.test about VAT"})
        self.call("/api/signoff", {"item_type": "o", "item_id": "SYN", "reviewer": "r", "qualification": "q", "decision": "agree",
                                   "note": "0501234567"})
        self.assertEqual(len(self.app.gate_log), 3)
        for rec in self.app.gate_log:
            self.assertLessEqual(set(rec), LOG_KEYS)
            self.assertEqual(rec["action"], "block")
        logged = self.err.getvalue() + json.dumps(list(self.app.gate_log))
        self.assert_no_fragment(logged)
        for s in (PD_QUESTION, "0501234567", "784199012345671"):
            self.assertNotIn(hashlib.sha256(s.encode()).hexdigest(), logged)                          # no hash of the value

    def test_128_fail_closed_when_the_kb_or_the_gate_fails(self):
        with mock.patch.object(self.app.asker, "ask", wraps=self.app.asker.ask) as spy:
            with mock.patch.object(PG, "load", side_effect=PG.KBError("missing")):
                r = json.loads(self.call("/api/ask", {"q": CLEAN_QUESTION})[1])
                self.assertEqual(r["mode"], "blocked")
                self.assertIn("HERBIZ-FAIL-CLOSED", r["design_references"])
            with mock.patch.object(PG, "policy_gate", side_effect=RuntimeError("boom")):
                r = json.loads(self.call("/api/ask", {"q": CLEAN_QUESTION})[1])
                self.assertEqual(r["mode"], "blocked")
                code, _ = self.call("/api/signoff", {"item_type": "o", "item_id": "SYN", "reviewer": "r", "qualification": "q",
                                                      "decision": "agree", "note": "plain note"})
                self.assertEqual(code, 400)
            with mock.patch.object(PG, "policy_gate", return_value={"action": "maybe"}):
                self.assertEqual(json.loads(self.call("/api/ask", {"q": CLEAN_QUESTION})[1])["mode"], "blocked")
            spy.assert_not_called()

    def test_129_sensitive_topic_is_processed_with_a_caution(self):
        r = json.loads(self.call("/api/ask", {"q": "Is a medical clinic supply zero-rated for VAT?"})[1])
        self.assertNotEqual(r["mode"], "blocked")
        self.assertIn("sensitive topic", r["caution"])

    def test_130_kb_ablation_changes_behaviour(self):
        # The policy KB drives the decision: without the Emirates ID detector the same input is no longer blocked.
        kb = json.loads(PG.KB_PATH.read_text(encoding="utf-8"))
        for c in kb["controls"]:
            c["detector_ids"] = [x for x in c.get("detector_ids", []) if x != "emirates_id"]
        alt = Path(self.tmp.name) / "kb.json"
        alt.write_text(json.dumps(kb), encoding="utf-8")
        real = PG.policy_gate
        with mock.patch.object(PG, "policy_gate", side_effect=lambda t, kb=None, kb_path=None: real(t, kb_path=alt)):
            code, body = self.call("/api/ask", {"q": "ID 784-1990-1234567-1, do I charge VAT?"})
            r = json.loads(body)
        self.assertNotEqual(r.get("mode"), "blocked")                            # the gate no longer blocks it ...
        # ... and since Task 2 A-1 the independent audit sanitizer is a second layer: the record would hold the ID, so the
        # answer is withheld (fail closed) instead of being shown without an audit record
        self.assertEqual((code, r.get("error")), (500, "AUDIT_WRITE_FAILED"))
        self.assertEqual(json.loads(self.call("/api/ask", {"q": "ID 784-1990-1234567-1, do I charge VAT?"})[1])["mode"], "blocked")

    def test_131_gate_files_match_the_pinned_ws_c_commit(self):
        from compliance_agent.mvp360 import pins as P
        lock = json.loads(P.SNAPSHOT_LOCK.read_text(encoding="utf-8"))
        self.assertEqual(lock["c_gate_commit"], P.C_GATE_COMMIT)
        self.assertEqual(lock["c_commit"], P.C_COMMIT)                                                  # tax sources unchanged
        for path in P.C_GATE_FILES:
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), lock["c_gate_files_sha256"][path], path)

    def test_132_fixture_sets_through_the_app_endpoints(self):
        # AT-1..AT-4 (WS C handoff): WS C's own test sets, sent through POST /api/ask and the reviewer-note endpoint.
        sys.path.insert(0, str(ROOT / "tests"))
        import test_ws_c_policy_gate as CT
        blocked_clean = []
        for q in CT._clean_questions():
            if json.loads(self.call("/api/ask", {"q": q})[1])["mode"] == "blocked":
                blocked_clean.append(q[:40])
        self.assertEqual(len(blocked_clean), 1, blocked_clean)       # only U23, which holds a synthetic Emirates ID
        for q in CT.HARD_NEGATIVES:
            self.assertNotEqual(json.loads(self.call("/api/ask", {"q": q})[1])["mode"], "blocked", q)
        n = 0
        for det, values in CT.POSITIVES.items():
            for v in values:
                code, body = self.call("/api/ask", {"q": f"{v} - do I charge VAT?"})
                r = json.loads(body)
                self.assertEqual(r["mode"], "blocked", (det, v))
                self.assertTrue(r["design_references"])
                self.assertNotIn(v, body)
                code, body = self.call("/api/signoff", {"item_type": "o", "item_id": "SYN", "reviewer": "r", "qualification": "q",
                                                        "decision": "agree", "note": v})
                self.assertEqual(code, 400, (det, v))
                self.assertNotIn(v, body)
                n += 1
        self.assertGreaterEqual(n, 22)
        self.assertEqual(self.app.engine.s.db.execute("SELECT COUNT(*) FROM reviewer_signoffs").fetchone()[0], 0)

    def test_133_corrupt_kb_file_fails_closed(self):
        bad = Path(self.tmp.name) / "corrupt.json"
        bad.write_text("{not json", encoding="utf-8")
        real = PG.policy_gate
        with mock.patch.object(PG, "policy_gate", side_effect=lambda t, kb=None, kb_path=None: real(t, kb_path=bad)):
            r = json.loads(self.call("/api/ask", {"q": CLEAN_QUESTION})[1])
        self.assertEqual(r["mode"], "blocked")
        self.assertIn("HERBIZ-FAIL-CLOSED", r["design_references"])


if __name__ == "__main__":
    unittest.main()
