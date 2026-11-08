"""Task 2 A-2: error scenarios SC-1, SC-2, SC-3 (doc 16 r2 §5). Tests t2s_01-11 (t2s_11: A-3 owner wording). Synthetic only; no network.

Events are released one at a time; every released step is checked against the frozen scenario fixture and audited
(channel "scenario"). HerBiz explains a conflict without resolving it, withholds an answer resting on an outdated source,
shows the current official link without fetching it, and never reports a placeholder as passed."""
from __future__ import annotations

import copy
import json
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

from compliance_agent import audit_log as AL, scenarios as SC, web  # noqa: E402
from compliance_agent.clock import FixedClock  # noqa: E402
import validate as V  # noqa: E402

AUDIT_SCHEMA = json.loads((ROOT / "contracts" / "audit_record_1.0.schema.json").read_text(encoding="utf-8"))
H = {"Content-Type": "application/json", "X-Requested-With": "compliance-ui", "X-HerBiz-Session": "tts-session"}


def run_all(sid):
    r = SC.Run(sid)
    out = []
    while not r.done:
        out.append(r.next())
    return out


class Scenarios(unittest.TestCase):
    def test_t2s_01_events_are_released_one_at_a_time(self):
        r = SC.Run("SC-2")
        self.assertEqual(r.released, 0)
        a = r.next(); self.assertEqual((a["n"], r.released, a["done"]), (1, 1, False))
        b = r.next(); self.assertEqual(b["n"], 2)
        c = r.next(); self.assertTrue(c["done"])
        with self.assertRaises(IndexError):
            r.next()
        bad = SC.Run("SC-3"); bad.scenario["steps"][0]["released_after"] = 1
        with self.assertRaises(ValueError):
            bad.next()

    def test_t2s_02_SC2_conflict_is_explained_never_resolved(self):
        out = run_all("SC-2")
        self.assertEqual([o["check"]["result"] for o in out], ["PASS", "PASS", "PASS"])
        last = out[-1]["response"]
        self.assertEqual(len(last["values"]), 2)
        self.assertTrue(all(v["source_id"] and v["url"].startswith("https://") for v in last["values"]))
        self.assertIs(last["precedence_known"], False)
        self.assertIsNone(last["deadline"])
        self.assertIn("FTA-registered tax agent", last["message"])
        self.assertIn("no deadline", last["message"])
        self.assertEqual(out[-1]["flags"], ["conflict"])

    def test_t2s_03_SC3_answer_withheld_link_shown_not_fetched(self):
        def no_network(*a, **k):
            raise AssertionError("the scenario must never fetch a link")
        with mock.patch("urllib.request.urlopen", side_effect=no_network), mock.patch("http.client.HTTPConnection.connect", side_effect=no_network):
            out = run_all("SC-3")
        self.assertEqual([o["check"]["result"] for o in out], ["PASS", "PASS", "PASS"])
        last = out[-1]["response"]
        self.assertIsNone(last["answer"])
        self.assertIs(last["link_fetched"], False)
        self.assertTrue(last["current_official_url"].startswith("https://"))
        self.assertEqual(last["content_check"], "pending_founder_verification")
        self.assertEqual(out[-1]["flags"], ["pending_unverified_link", "stale_source"])
        self.assertIn("Review required", last["message"])

    def test_t2s_04_SC1_placeholder_is_pending_never_passed(self):
        # the G1 golden fixture still names the placeholder obligation: it must stay PENDING_DATA, never PASS
        golden = json.loads((ROOT / "contracts" / "fixtures" / "scenario.valid_SC-1.json").read_text(encoding="utf-8"))
        with mock.patch.object(SC, "load", return_value=golden):
            out = run_all("SC-1")
        self.assertEqual([o["check"]["result"] for o in out], ["PENDING_DATA"] * 3)
        self.assertLess(len(out[1]["response"]["questions"]), len(out[0]["response"]["questions"]))   # fewer questions: checked
        self.assertEqual(out[2]["response"]["questions"], [])

    def test_t2s_05_SC1_passes_on_ws_b_delivered_data(self):
        # A-4: WS B's SC-1 data (t2-b-rc1, engine obligation C360-03), pinned by sha256
        s = SC.load("SC-1")
        self.assertEqual({st["input"]["obligation_id"] for st in s["steps"]}, {"C360-03"})
        self.assertTrue(all("deadline" in st["expected"]["must_not"] for st in s["steps"]))
        out = run_all("SC-1")
        self.assertEqual([o["check"]["result"] for o in out], ["PASS", "PASS", "PASS"])
        self.assertEqual([o["response"]["obligation"]["state"] for o in out],
                         ["insufficient_information", "insufficient_information", "blocked_pending_legal_validation"])
        self.assertIn("What you can do now", out[2]["response"]["what_you_can_do_now"])
        self.assertEqual(out[2]["flags"], ["blocked_legal_validation"])
        with mock.patch.dict(SC.DELIVERED, {"SC-1": (SC.DELIVERED["SC-1"][0], "0" * 64)}):
            with self.assertRaises(ValueError):                                  # a changed delivery is refused
                SC.load("SC-1")

    def test_t2s_06_checks_fail_when_behaviour_deviates(self):
        orig = SC.Run._sc2_answer
        def with_deadline(self, v):
            resp, flags = orig(self, v); resp["deadline"] = "2026-11-30"; resp["precedence_known"] = True
            return resp, flags
        with mock.patch.object(SC.Run, "_sc2_answer", with_deadline):
            out = run_all("SC-2")
        self.assertEqual(out[-1]["check"]["result"], "FAIL")
        step = copy.deepcopy(SC.load("SC-3")["steps"][2]); step["expected"]["must_show"].append("an unknown promise")
        r = SC.Run("SC-3"); r.next(); r.next()
        resp, flags = r._sc3_answer(r.validity)
        self.assertEqual(SC.check(step, resp, flags, r)["result"], "FAIL")              # unknown checks never pass silently

    def test_t2s_07_scenario_records_are_valid_and_embed_the_validity_payload(self):
        outs, folder = SC.replay("SC-3")
        f = sorted(folder.glob("audit-*.jsonl"))[0]
        self.assertTrue(AL.verify(f)[0])
        recs = [json.loads(x) for x in f.read_bytes().splitlines()]
        self.assertEqual(len(recs), 3)
        for rec in recs:
            self.assertEqual(V.errors(AUDIT_SCHEMA, rec), [])
            self.assertEqual((rec["channel"], rec["answer"]["mode"], rec["answer"]["execution_mode"]), ("scenario", "scenario", "simulated"))
            self.assertIsNone(rec["request"]["query_text"])
        self.assertEqual(recs[2]["sources"][0]["validity"]["status"], "outdated")
        self.assertEqual(AL.scan(folder), [])

    def test_t2s_08_api_releases_and_audits_each_step(self):
        with tempfile.TemporaryDirectory() as d:
            app = web.App(Path(d) / "w.sqlite3", FixedClock("2026-10-17T10:00:00"), Path(d) / "none.sqlite3")
            srv = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(app))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            def call(path, body=None):
                req = urllib.request.Request(base + path, method="POST" if body is not None else "GET",
                                             data=json.dumps(body).encode() if body is not None else None, headers=H)
                try:
                    with urllib.request.urlopen(req) as r:
                        return r.status, r.headers.get("X-HerBiz-Audit-Record"), json.loads(r.read())
                except urllib.error.HTTPError as ex:
                    with ex:
                        return ex.code, None, json.loads(ex.read())
            try:
                self.assertEqual(len(call("/api/scenario/list")[2]["scenarios"]), 3)
                _, _, start = call("/api/scenario/start", {"scenario_id": "SC-2"})
                rids = []
                for n in (1, 2, 3):
                    code, rid, step = call("/api/scenario/next", {"run_id": start["run_id"]})
                    self.assertEqual((code, step["n"]), (200, n)); self.assertTrue(rid); rids.append(rid)
                self.assertEqual(call("/api/scenario/next", {"run_id": start["run_id"]})[0], 400)
                self.assertEqual(call("/api/scenario/next", {"run_id": "nope"})[0], 404)
                self.assertEqual(call("/api/scenario/start", {"scenario_id": "SC-9"})[0], 400)
                f = app.audit.files()[0]
                self.assertTrue(AL.verify(f, str(app.db_path))[0])
                recs = {json.loads(x)["record_id"]: json.loads(x) for x in f.read_bytes().splitlines()}
                self.assertTrue(all(recs[r]["channel"] == "scenario" for r in rids))
            finally:
                srv.shutdown(); srv.server_close(); app.engine.s.close()

    def test_t2s_09_one_command_per_scenario(self):
        for sid in ("SC-1", "SC-2", "SC-3"):
            p = subprocess.run([sys.executable, "-m", "compliance_agent.scenarios", "replay", sid], cwd=str(ROOT),
                               capture_output=True, text=True, timeout=300)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("chain intact", p.stdout)
            self.assertIn("RESULT: PASS\n", p.stdout)

    def test_t2s_10_page_has_the_next_event_control_and_no_we_wording_in_it(self):
        page = (ROOT / "compliance_agent" / "ui360.html").read_text(encoding="utf-8")
        self.assertIn('id="scNext"', page); self.assertIn("/api/scenario/next", page)
        block = page[page.index("// ---------- error scenarios"):page.index("// ---------- VAT ----------")]
        for w in (" we ", " our ", " us "):
            self.assertNotIn(w, block.lower())

    def test_t2s_11_A3_owner_pages_never_say_we_our_or_us(self):
        import re
        for page in ("ui360.html", "ui.html"):
            text = (ROOT / "compliance_agent" / page).read_text(encoding="utf-8")
            hits = re.findall(r"(?<![A-Za-z])(we|our|us|we're|we'll|we've|ours|ourselves)(?![A-Za-z])", text, re.I)
            self.assertEqual(hits, [], page)
        page = (ROOT / "compliance_agent" / "ui360.html").read_text(encoding="utf-8")
        self.assertIn("HerBiz needs to know", page)


if __name__ == "__main__":
    unittest.main()
