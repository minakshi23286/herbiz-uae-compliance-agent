"""Task 2 A-1: per-response audit records and their safeguards (doc 16 r2 §4, §4.1). Tests t2a_01-15. Synthetic only.

Every owner channel writes one valid audit_record/1.0 before its response is sent; blocked question text never reaches a
record; the sanitizer rejects (never silently redacts); the answer is withheld if the record cannot be written; the audit
view exists only in reviewer mode; the hash chain detects edits, deletions, reordering, truncation and pointer mismatches;
parallel requests and a second process produce one contiguous chain."""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import os
import shutil
import stat
import subprocess
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

from compliance_agent import ask as ASK, audit_log as AL, audit_records as AR, audit_sanitizer as S, web  # noqa: E402
from compliance_agent.clock import FixedClock  # noqa: E402
import validate as V  # noqa: E402

LEDGER = ROOT / "data" / "CL_llm_experiment.sqlite3"
SCHEMA = json.loads((ROOT / "contracts" / "audit_record_1.0.schema.json").read_text(encoding="utf-8"))
H = {"Content-Type": "application/json", "X-Requested-With": "compliance-ui", "X-HerBiz-Session": "tta-session"}
PII_Q = "My customer Fatima, Emirates ID 784-1990-1234567-1, owes me AED 5,000 — do I charge VAT?"
ALLOW_Q = "Do I need to register for VAT if my sales were AED 400,000 last year?"
WARN_Q = "Is a medical clinic supply zero-rated for VAT?"
CHANNEL_CALLS = [  # (channel, method path, body)
    ("ask", "/api/ask?id=Q35", None), ("ask", "/api/ask", {"q": ALLOW_Q}), ("ask", "/api/ask", {"q": PII_Q}),
    ("ask", "/api/ask", {"q": WARN_Q}),
    ("dashboard", "/api/360/dashboard", {"profile_id": "SYN-AMAL-B"}),
    ("dashboard", "/api/360/dashboard", {"fields": {"emirate": "AE-DU", "legal_form": "llc", "activities": ["design"],
                                                    "licence_expiry_date": "2027-01-01"}}),
    ("dashboard", "/api/360/dashboard", {"fields": {"emirate": "Atlantis"}}),
    ("ct", "/api/360/ct?profile=SYN-AMAL-A", None), ("ct", "/api/360/ct?profile=SYN-P01", None),
    ("finance", "/api/360/finance", None), ("finance", "/api/360/finance.csv", None),
    ("change_replay", "/api/360/change", None),
]
REVIEWER_ONLY_KEYS = ("reviewer_trace", "visible_to", "record_sha256", "integrity", "decisions", "why", "draft_basis_for_reviewer")


class Server:
    def __init__(self, reviewer_mode=False, audit_dir=None, ledger=True):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.app = web.App(d / "w.sqlite3", FixedClock("2026-10-17T10:00:00"), LEDGER if ledger else d / "none.sqlite3",
                           audit_dir=audit_dir, reviewer_mode=reviewer_mode)
        if not ledger:
            self.app._asker = ASK.Asker(d / "w.sqlite3", d / "none.sqlite3", d / "none.json")
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(self.app))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None, headers=H)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.headers.get("X-HerBiz-Audit-Record"), r.read()
        except urllib.error.HTTPError as ex:
            with ex:
                return ex.code, ex.headers.get("X-HerBiz-Audit-Record"), ex.read()

    def records(self):
        return [r for f in self.app.audit.files() for r in self.app.audit.records(f, limit=100000)]

    def close(self):
        self.srv.shutdown(); self.srv.server_close(); self.app.engine.s.close(); self.tmp.cleanup()


class AuditLogTests(unittest.TestCase):
    def setUp(self):
        self.s = Server(ledger=LEDGER.exists())
        self.err = open(os.devnull, "w"); self._old = sys.stderr; sys.stderr = self.err     # gate log lines

    def tearDown(self):
        sys.stderr = self._old; self.err.close(); self.s.close()

    def test_t2a_01_every_owner_channel_writes_one_valid_record_matching_the_response(self):
        seen = set()
        for channel, path, body in CHANNEL_CALLS:
            code, rid, resp = self.s.call(path, body)
            self.assertIsNotNone(rid, path)
            rec = next(r for r in self.s.records() if r["record_id"] == rid)
            self.assertEqual(rec["channel"], channel)
            self.assertEqual(V.errors(SCHEMA, rec), [], path)
            self.assertEqual(rec["answer"]["shown_text_sha256"], hashlib.sha256(resp).hexdigest(), path)
            self.assertEqual(rec["session_id"], "tta-session")
            self.assertTrue(rec["sanitizer"]["passed"])
            seen.add(channel)
        start = json.loads(self.s.call("/api/scenario/start", {"scenario_id": "SC-3"})[2])
        code, rid, resp = self.s.call("/api/scenario/next", {"run_id": start["run_id"]})
        rec = next(r for r in self.s.records() if r["record_id"] == rid)
        self.assertEqual((code, rec["channel"], V.errors(SCHEMA, rec)), (200, "scenario", []))
        self.assertEqual(rec["answer"]["shown_text_sha256"], hashlib.sha256(resp).hexdigest())
        seen.add("scenario")
        self.assertEqual(seen, {"ask", "dashboard", "ct", "finance", "change_replay", "scenario"})   # every channel in the contract
        self.assertEqual(len(self.s.records()), len(CHANNEL_CALLS) + 1)
        for f in self.s.app.audit.files():
            ok, msg = AL.verify(f, str(self.s.app.db_path))
            self.assertTrue(ok, msg)

    def test_t2a_02_decisions_and_sources_come_from_the_engine_report(self):
        _, rid, _ = self.s.call("/api/360/dashboard", {"profile_id": "SYN-AMAL-B"})
        rec = next(r for r in self.s.records() if r["record_id"] == rid)
        self.assertEqual(len(rec["decisions"]), 12)
        d = {x["obligation_id"]: x for x in rec["decisions"]}
        self.assertEqual(d["C360-05"]["rule_status"], "blocked_source_conflict")
        self.assertIn("conflict", rec["answer"]["flags"])
        self.assertEqual(d["SYN-LIC-RENEWAL"]["execution_mode"], "simulated")
        self.assertTrue(all(x["review"]["release_approved"] is False and x["confidence"]["numeric"] is None for x in rec["decisions"]))
        self.assertTrue({"FTA-VAT-DL8", "CT-DL47-2022"} <= {s["source_id"] for s in rec["sources"]})
        self.assertTrue(all(s["url"].startswith("https://") for s in rec["sources"]))

    def test_t2a_03_T2_D2_blocked_and_warned_question_text_never_reaches_a_record(self):
        for q, action in ((PII_Q, "block"), (WARN_Q, "warn"), (ALLOW_Q, "allow")):
            _, rid, _ = self.s.call("/api/ask", {"q": q})
            rec = next(r for r in self.s.records() if r["record_id"] == rid)
            self.assertEqual(rec["request"]["gate"]["action"], action)
            if action == "allow":
                self.assertEqual(rec["request"]["query_text"], ALLOW_Q)
            else:
                self.assertIsNone(rec["request"]["query_text"])
        rec = next(r for r in self.s.records() if r["request"]["gate"] and r["request"]["gate"]["action"] == "block")
        self.assertIsNone(rec["request"]["query_sha256"])        # not even a hash of a blocked input
        self.assertIsNone(rec["retrieval"])
        raw = b"".join(f.read_bytes() for f in self.s.app.audit.files())
        # fragments that cannot occur inside a hex digest (a bare "784" can, by chance, in a random record hash)
        for frag in (b"784-1990-1234567-1", b"784199012345671", b"Fatima", b"medical clinic", b"Emirates ID"):
            self.assertNotIn(frag, raw)
        self.assertNotIn(hashlib.sha256(PII_Q.encode()).hexdigest().encode(), raw)

    def test_t2a_04_N_B1_may_be_incomplete_unless_complete_for_map(self):
        for qid in ("Q35", "Q13", "U10", "U22"):
            _, rid, resp = self.s.call(f"/api/ask?id={qid}")
            level = (json.loads(resp).get("guard") or {}).get("level")
            rec = next(r for r in self.s.records() if r["record_id"] == rid)
            if level in ("complete_for_map", "not_applicable"):
                self.assertNotIn("may_be_incomplete", rec["answer"]["flags"], qid)
            else:
                self.assertIn("may_be_incomplete", rec["answer"]["flags"], qid)
        _, rid, _ = self.s.call("/api/ask", {"q": ALLOW_Q})                       # no recording -> unchecked
        self.assertIn("may_be_incomplete", next(r for r in self.s.records() if r["record_id"] == rid)["answer"]["flags"])

    def test_t2a_05_sanitizer_rejects_rather_than_redacts(self):
        good = json.loads((ROOT / "contracts" / "fixtures" / "audit_record.valid_allow.json").read_text())
        self.assertEqual(S.check(good), [])
        cases = {"FIELD_TEXT": lambda r: r["retrieval"]["items"][0].__setitem__("text", "passage"),
                 "QUERY_TEXT_NOT_ALLOWED": lambda r: r["request"]["gate"].__setitem__("action", "warn"),
                 "PII_EMAIL": lambda r: r.__setitem__("error", "contact fatima.example@mail.test"),
                 "PII_UAE_PHONE": lambda r: r["answer"].__setitem__("status", "call 050 123 4567"),
                 "LOCAL_PATH": lambda r: r.__setitem__("error", "/" "Users/someone/file"),
                 "LONG_STRING": lambda r: r.__setitem__("error", "x" * 500)}
        for code, mutate in cases.items():
            r = json.loads(json.dumps(good)); mutate(r)
            self.assertIn(code, S.check(r), code)

    def test_t2a_06_fail_closed_when_the_record_is_rejected_or_cannot_be_written(self):
        before = len(self.s.records())
        with mock.patch.object(AR, "simple_record", side_effect=lambda *a, **k: {"bad": "record"}):
            code, rid, body = self.s.call("/api/360/finance")
        self.assertEqual((code, rid), (500, None))
        j = json.loads(body)
        self.assertEqual(j["error"], "AUDIT_WRITE_FAILED")
        self.assertEqual(set(j), {"error", "unavailable"})                       # no answer payload
        self.assertIn("could not record this answer", j["unavailable"])
        real = AR.simple_record
        with mock.patch.object(AR, "simple_record", side_effect=lambda *a, **k: {**real(*a, **k), "error": "write to fatima.example@mail.test"}):
            code, _, body = self.s.call("/api/360/finance")
        self.assertEqual(code, 500)
        self.assertEqual(len(self.s.records()), before)                         # nothing written
        folder = self.s.app.audit.folder
        os.chmod(folder, stat.S_IRUSR | stat.S_IXUSR)
        try:
            for f in folder.glob("*.jsonl"):
                os.chmod(f, stat.S_IRUSR)
            code, _, body = self.s.call("/api/360/finance")
            self.assertEqual((code, json.loads(body)["error"]), (500, "AUDIT_WRITE_FAILED"))
        finally:
            os.chmod(folder, stat.S_IRWXU)
            for f in folder.glob("*.jsonl"):
                os.chmod(f, stat.S_IRUSR | stat.S_IWUSR)

    def test_t2a_07_audit_view_only_in_reviewer_mode_and_owner_responses_hold_no_reviewer_fields(self):
        for path in ("/api/audit/files", "/api/audit/records?file=x", "/api/audit/verify?file=x"):
            self.assertEqual(self.s.call(path)[0], 404, path)
        for _, path, body in CHANNEL_CALLS:
            _, _, resp = self.s.call(path, body)
            low = resp.decode("utf-8", "replace")
            for k in REVIEWER_ONLY_KEYS:
                self.assertNotIn(f'"{k}"', low, (path, k))
        r = Server(reviewer_mode=True)
        try:
            r.call("/api/360/finance")
            files = json.loads(r.call("/api/audit/files")[2])["files"]
            self.assertEqual(len(files), 1)
            self.assertEqual(len(json.loads(r.call(f"/api/audit/records?file={files[0]}")[2])["records"]), 1)
            self.assertTrue(json.loads(r.call(f"/api/audit/verify?file={files[0]}")[2])["ok"])
        finally:
            r.close()

    def _chain(self, n=4):
        for _ in range(n):
            self.s.call("/api/360/finance")
        f = self.s.app.audit.files()[0]
        return f, f.read_bytes().splitlines(keepends=True)

    def test_t2a_08_hash_chain_detects_edit_delete_reorder_truncate_and_pointer_mismatch(self):
        f, lines = self._chain()
        db = str(self.s.app.db_path)
        self.assertTrue(AL.verify(f, db)[0])
        tmp = Path(tempfile.mkdtemp())
        try:
            def variant(name, data):
                p = tmp / f.name
                p.write_bytes(data)
                return AL.verify(p, None)
            edited = json.loads(lines[1]); edited["answer"]["status"] = "changed"
            self.assertIn("seq 2", variant("edit", lines[0] + (json.dumps(edited) + "\n").encode() + b"".join(lines[2:]))[1])
            self.assertFalse(variant("delete", lines[0] + b"".join(lines[2:]))[0])
            self.assertFalse(variant("reorder", lines[1] + lines[0] + b"".join(lines[2:]))[0])
            self.assertIn("truncated", variant("truncate", b"".join(lines)[:-20])[1])
            p = tmp / f.name; p.write_bytes(b"".join(lines))
            con = __import__("sqlite3").connect(db)
            con.execute("DROP TRIGGER IF EXISTS audit_no_delete"); con.execute("DELETE FROM audit_events WHERE event_id = (SELECT MAX(event_id) FROM audit_events WHERE event='audit_record')"); con.commit(); con.close()
            ok, msg = AL.verify(p, db)
            self.assertFalse(ok); self.assertIn("pointer mismatch", msg)
        finally:
            shutil.rmtree(tmp)

    def test_t2a_09_writer_refuses_to_append_to_a_broken_file(self):
        f, lines = self._chain(2)
        f.write_bytes(b"".join(lines)[:-5])
        code, _, body = self.s.call("/api/360/finance")
        self.assertEqual((code, json.loads(body)["error"]), (500, "AUDIT_WRITE_FAILED"))

    def test_t2a_10_fifty_plus_parallel_requests_one_record_each_contiguous_chain(self):
        calls = [CHANNEL_CALLS[i % len(CHANNEL_CALLS)] for i in range(60)]
        with cf.ThreadPoolExecutor(max_workers=16) as ex:
            res = list(ex.map(lambda c: self.s.call(c[1], c[2]), calls))
        rids = [r[1] for r in res]
        self.assertTrue(all(rids), [(c[1], r[0], r[2][:200]) for c, r in zip(calls, res) if not r[1]][:3])
        self.assertEqual(len(set(rids)), 60)
        recs = self.s.records()
        self.assertEqual(sorted(r["record_id"] for r in recs), sorted(rids))
        self.assertEqual([r["integrity"]["seq"] for r in recs], list(range(1, 61)))
        self.assertTrue(AL.verify(self.s.app.audit.files()[0], str(self.s.app.db_path))[0])

    def test_t2a_11_a_second_process_on_the_same_folder_is_serialised(self):
        folder = self.s.app.audit.folder
        script = (f"import sys, json; sys.path.insert(0, {str(ROOT)!r});\n"
                  "from compliance_agent import audit_log as AL, audit_records as AR\n"
                  f"log = AL.AuditLog(__import__('pathlib').Path({str(folder)!r}))\n"
                  "for i in range(25):\n"
                  "    log.write(AR.simple_record('finance', 'proc-two', 'finance_checklist', b'x', 'ok', 'simulated', ['simulated_data'], None))\n")
        p = subprocess.Popen([sys.executable, "-c", script])
        for _ in range(25):
            self.s.call("/api/360/finance")
        self.assertEqual(p.wait(timeout=120), 0)
        f = self.s.app.audit.files()[0]
        lines = f.read_bytes().splitlines()
        self.assertEqual(len(lines), 50)
        self.assertTrue(AL.verify(f)[0])                                        # chain intact across both processes
        self.assertEqual([json.loads(x)["integrity"]["seq"] for x in lines], list(range(1, 51)))

    def test_t2a_12_offline_scanner_has_its_own_patterns_and_catches_injected_data(self):
        f, lines = self._chain(2)
        self.assertEqual(AL.scan(f.parent), [])
        tmp = Path(tempfile.mkdtemp())
        try:
            for name, inject in (("e", b'"x":"fatima.example@mail.test"'), ("i", b'"x":"784-1990-1234567-1"'),
                                 ("p", b'"x":"/' b'Users/someone"'), ("t", b'"text":"passage"'), ("l", b'"x":"' + b"y" * 600 + b'"')):
                p = tmp / f"audit-2026-10-17-{name}.jsonl"
                p.write_bytes(lines[0].rstrip(b"}\n") + b"," + inject + b"}\n")
                self.assertTrue(AL.scan(p), name)
            out = subprocess.run([sys.executable, "-m", "compliance_agent.audit_log", "verify", "--scan", str(tmp)],
                                 cwd=str(ROOT), capture_output=True, text=True)
            self.assertEqual(out.returncode, 1)
            ok = subprocess.run([sys.executable, "-m", "compliance_agent.audit_log", "verify", str(f)], cwd=str(ROOT),
                                capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0); self.assertIn("chain intact", ok.stdout)
        finally:
            shutil.rmtree(tmp)
        self.assertNotEqual(set(AL.SCAN_PATTERNS), set())                       # independent list (not the sanitizer's)

    def test_t2a_13_logs_live_in_the_workspace_folder_never_beside_the_authoritative_db(self):
        self.assertEqual(self.s.app.audit.folder, (self.s.app.db_path.resolve().parent / "audit-logs"))
        self.assertNotIn("CL_compliance.sqlite3", str(self.s.app.audit.folder))
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("data/audit-logs/", gi)

    def test_t2a_14_owner_responses_are_unchanged_by_auditing(self):
        from compliance_agent.mvp360 import adapter as A
        _, _, body = self.s.call("/api/360/dashboard", {"profile_id": "SYN-AMAL-B"})
        self.assertEqual(json.loads(body), json.loads(json.dumps(A.dashboard("SYN-AMAL-B"), default=str)))
        _, _, body = self.s.call("/api/360/finance")
        self.assertEqual(json.loads(body), A.finance())

    def test_t2a_15_machine_values_never_trigger_personal_data_rules_but_free_text_does(self):
        # regression (18 Oct): a random hex digest can contain "05" + 8 digits; that is not a phone number
        good = json.loads((ROOT / "contracts" / "fixtures" / "audit_record.valid_allow.json").read_text())
        good["answer"]["shown_text_sha256"] = "ab0512345678" + "c" * 52
        good["integrity"]["record_sha256"] = "d784199012345671" + "e" * 48
        good["record_id"] = "10512345-6789-4abc-8def-0512345678ab"
        self.assertEqual(S.check(good), [])
        bad = json.loads(json.dumps(good)); bad["answer"]["status"] = "ab0512345678"         # same digits in free text
        self.assertIn("PII_UAE_PHONE", S.check(bad))
        bad = json.loads(json.dumps(good)); bad["answer"]["shown_text_sha256"] = "call 0512345678"   # wrong format: not exempt
        self.assertTrue(S.check(bad))
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "audit-2026-10-18.jsonl").write_text(json.dumps(good) + "\n", encoding="utf-8")
            self.assertEqual(AL.scan(tmp), [])
        finally:
            shutil.rmtree(tmp)
        req = urllib.request.Request(self.s.base + "/api/360/finance", headers={**H, "X-HerBiz-Session": "s-0512345678"})
        with urllib.request.urlopen(req) as r:
            rid = r.headers.get("X-HerBiz-Audit-Record")
        self.assertEqual(next(x for x in self.s.records() if x["record_id"] == rid)["session_id"], "no-session")


if __name__ == "__main__":
    unittest.main()
