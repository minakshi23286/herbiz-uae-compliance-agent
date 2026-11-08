"""H360-13 (WS-B, tests only; founder-approved 17 Oct 2026): the EXISTING reviewer sign-off endpoint.

Exercises `/api/signoff` in compliance_agent/web.py as it already is. No app, engine, contract or rule code is changed.
Every write goes to a throwaway workspace copy made by `dbsafety.ensure_workspace`; the source database is opened
read-only and its md5 is checked before and after. Synthetic reviewer names only.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compliance_agent import dbsafety, web  # noqa: E402
from compliance_agent.clock import FixedClock  # noqa: E402

UI = {"Content-Type": "application/json", "X-Requested-With": "compliance-ui"}
GOOD = {"item_type": "obligation", "item_id": "SYN-OB-1", "reviewer": "Test Reviewer (synthetic)",
        "qualification": "synthetic test role", "decision": "agree", "note": "test only"}


def md5(p: Path) -> str | None:
    return hashlib.md5(p.read_bytes()).hexdigest() if p.exists() else None


class SignoffEndpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src_md5 = md5(dbsafety.AUTHORITATIVE)
        ws = dbsafety.ensure_workspace(fresh=True, dest=Path(self.tmp.name) / "CL_signoff_workspace.sqlite3")
        self.assertFalse(dbsafety.is_authoritative(ws))
        self.app = web.App(ws, FixedClock("2026-10-16T10:00:00"))
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(self.app))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close()
        self.app.engine.s.close()
        self.tmp.cleanup()
        self.assertEqual(md5(dbsafety.AUTHORITATIVE), self.src_md5)   # source database never written

    def post(self, body, headers=UI):
        req = urllib.request.Request(self.base + "/api/signoff", method="POST", data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as ex:
            with ex:
                return ex.code, json.loads(ex.read())

    def counts(self):
        q = self.app.engine.s.q
        return (q("SELECT COUNT(*) AS n FROM reviewer_signoffs")[0]["n"],
                q("SELECT COUNT(*) AS n FROM audit_events WHERE event = 'reviewer_signoff'")[0]["n"])

    def test_h13_01_valid_signoff_writes_one_row_and_one_audit_event(self):
        before = self.counts()
        self.assertEqual(self.post(GOOD), (200, {"outcome": "recorded"}))
        self.assertEqual(self.counts(), (before[0] + 1, before[1] + 1))
        row = self.app.engine.s.q("SELECT * FROM reviewer_signoffs ORDER BY signoff_id DESC LIMIT 1")[0]
        for k in ("item_type", "item_id", "reviewer", "qualification", "decision", "note"):
            self.assertEqual(row[k], GOOD[k])
        self.assertEqual(row["at"], self.app.engine.now())
        ev = self.app.engine.s.q("SELECT * FROM audit_events WHERE event = 'reviewer_signoff' ORDER BY event_id DESC LIMIT 1")[0]
        self.assertEqual((ev["actor"], ev["entity"], ev["entity_id"]), (GOOD["reviewer"], GOOD["item_type"], GOOD["item_id"]))
        self.assertEqual(json.loads(ev["payload_json"]), {"decision": "agree", "qualification": GOOD["qualification"]})

    def test_h13_02_each_missing_field_is_refused_and_nothing_written(self):
        before = self.counts()
        for k in GOOD:
            for bad in (None, "", "   "):
                body = dict(GOOD)
                if bad is None:
                    body.pop(k)
                else:
                    body[k] = bad
                code, out = self.post(body)
                self.assertEqual(code, 400, (k, bad))
                self.assertIn(k, out["error"])
        self.assertEqual(self.counts(), before)

    def test_h13_03_unknown_decision_is_refused(self):
        before = self.counts()
        for d in ("approved", "certified", "AGREE", "yes"):
            code, out = self.post(dict(GOOD, decision=d))
            self.assertEqual(code, 400, d)
            self.assertIn("decision must be", out["error"])
        self.assertEqual(self.counts(), before)

    def test_h13_04_all_three_allowed_decisions_are_recorded(self):
        before = self.counts()
        for d in ("agree", "disagree", "needs_source"):
            self.assertEqual(self.post(dict(GOOD, decision=d))[0], 200)
        self.assertEqual(self.counts(), (before[0] + 3, before[1] + 3))

    def test_h13_05_request_without_local_ui_header_is_refused(self):
        before = self.counts()
        code, _ = self.post(GOOD, headers={"Content-Type": "application/json"})
        self.assertEqual(code, 403)
        self.assertEqual(self.counts(), before)

    def test_h13_06_signoff_listed_by_project_endpoint(self):
        self.post(GOOD)
        with urllib.request.urlopen(self.base + "/api/project") as r:
            proj = json.loads(r.read())
        self.assertTrue(any(s["item_id"] == "SYN-OB-1" and s["decision"] == "agree" for s in proj["signoffs"]))

    def test_h13_07_signoff_audit_event_is_append_only(self):
        self.post(GOOD)
        db = self.app.engine.s.db
        eid = db.execute("SELECT MAX(event_id) FROM audit_events WHERE event = 'reviewer_signoff'").fetchone()[0]
        for sql in ("UPDATE audit_events SET actor = 'x' WHERE event_id = ?", "DELETE FROM audit_events WHERE event_id = ?"):
            with self.assertRaises(Exception) as cm:
                db.execute(sql, (eid,))
            self.assertIn("append-only", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
