"""Acceptance tests for the HerBiz Compliance Agent foundation (synthetic fixtures only).

Run:  python3 -m unittest discover -s tests -v      (from CL_compliance_agent_app/)
Each test name maps to a row in docs/CL_EVALUATION_REPORT.md.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compliance_agent import profiles as P  # noqa: E402
from compliance_agent import scenario as sc  # noqa: E402
from compliance_agent import sources as S  # noqa: E402
from compliance_agent.clock import FixedClock  # noqa: E402
from compliance_agent.engine import Engine, WorkflowError  # noqa: E402
from compliance_agent.store import Store  # noqa: E402

SRC, PROF = sc.load_fixtures()
REV = ("Test Reviewer", "domain reviewer (test)", "test note")


def new_engine(path=":memory:", when="2026-10-16T10:00:00"):
    return Engine(Store(path), FixedClock(when))


def profile(**facts):
    p = copy.deepcopy(PROF["noor_stage1"])
    p["facts"].update(facts)
    return p


def result(e, key, pid="BP-0001"):
    r = e.s.one("SELECT result FROM assessments WHERE profile_id=? AND obligation_key=? AND current=1", (pid, key))
    return r and r["result"]


def case(e, key, pid="BP-0001"):
    c = e.s.one("SELECT * FROM cases WHERE dedupe_key=?", (f"{pid}:{key}",))
    if c:
        c["evidence_required"] = json.loads(c["evidence_required_json"])
    return c


def baseline(e, *keys):
    for k in keys or ("LIC_v1", "VAT_v1", "PRIV_A_v1", "FOOD_v1_irrelevant", "EINV_v1_future"):
        e.ingest_source(SRC[k])


class ProfileAndFacts(unittest.TestCase):
    def test_01_missing_jurisdiction_needs_clarification(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile(jurisdiction=None, licensing_context="home_based_licence"))
        self.assertEqual(result(e, "LIC-RENEWAL"), "needs_clarification")
        self.assertIn("jurisdiction", json.loads(e.s.one("SELECT missing_json FROM assessments WHERE obligation_key='LIC-RENEWAL' AND current=1")["missing_json"]))
        self.assertIn("jurisdiction", P.missing_material_facts(e.latest_profile("BP-0001")["facts"]))

    def test_02_missing_licence_context_needs_clarification(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile())
        self.assertEqual(result(e, "LIC-RENEWAL"), "needs_clarification")
        self.assertEqual(case(e, "LIC-RENEWAL")["kind"], "clarification")

    def test_03_invalid_profiles_are_refused(self):
        e = new_engine(); baseline(e)
        for bad in (profile(jurisdiction="AE-XX"), profile(employees=-1), profile(vat_registered="no"),
                    profile(licence_expiry_date="30/11/2026"), {**profile(), "synthetic": False}, {"profile_id": ""}):
            with self.assertRaises(P.ProfileError):
                e.upsert_profile(bad)
        bad_ledger = profile(); bad_ledger["facts"]["ledger_last_12m"] = [{"type": "sale_of_services", "amount_aed": "lots"}]
        with self.assertRaises(P.ProfileError):
            e.upsert_profile(bad_ledger)
        self.assertEqual(e.s.one("SELECT COUNT(*) n FROM business_profiles")["n"], 0)

    def test_04_regression_salary_never_added_to_taxable_turnover(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile())  # 320,000 sales + 60,000 salary: draft plan's method would give 380,000 > 375,000
        ts = P.taxable_supplies(e.latest_profile("BP-0001")["facts"]["ledger_last_12m"])
        self.assertEqual(ts["total_aed"], 320000)
        self.assertEqual([x["type"] for x in ts["excluded"]], ["salary_cost"])
        self.assertEqual(result(e, "VAT-MANDATORY-REG"), "not_applicable")
        self.assertIsNone(case(e, "VAT-MANDATORY-REG"))

    def test_05_unknown_ledger_line_is_not_guessed(self):
        e = new_engine(); baseline(e)
        p = profile(expected_taxable_supplies_next_30d_aed=None)
        p["facts"]["ledger_last_12m"].append({"type": "misc_income", "amount_aed": 90000})
        e.upsert_profile(p)
        self.assertEqual(result(e, "VAT-MANDATORY-REG"), "needs_clarification")

    def test_06_profile_change_rechecks_dependent_assessments(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile(licensing_context="home_based_licence", licence_expiry_date="2026-11-30"))
        self.assertEqual(result(e, "PRIV-NOTICE"), "applicable")
        e.upsert_profile(profile(licensing_context="home_based_licence", licence_expiry_date="2026-11-30",
                                 collects_customer_personal_data=False))
        self.assertEqual(result(e, "PRIV-NOTICE"), "not_applicable")
        c = case(e, "PRIV-NOTICE")
        self.assertEqual(c["status"], "escalated")  # a human confirms withdrawal; nothing silently disappears
        self.assertEqual(e.review_case(c["case_id"], "approve", *REV)["status"], "withdrawn")
        events = [h["event"] for h in e.history("BP-0001")]
        self.assertEqual(events, ["profile_created", "profile_changed"])

    def test_07_renewal_date_never_inferred_from_issue_date(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile(licensing_context="home_based_licence"))  # issue date present, expiry unknown
        c = case(e, "LIC-RENEWAL")
        self.assertEqual(c["kind"], "obligation_action")
        self.assertIsNone(c["due_date"])
        self.assertIn("never inferred", c["due_basis"])
        e.upsert_profile(profile(licensing_context="home_based_licence", licence_expiry_date="2026-11-30"))
        self.assertEqual(case(e, "LIC-RENEWAL")["due_date"], "2026-11-30")


class Sources(unittest.TestCase):
    def test_08_irrelevant_source_not_applicable(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile(licensing_context="home_based_licence"))
        self.assertEqual(result(e, "FOOD-HYGIENE"), "not_applicable")
        self.assertIsNone(case(e, "FOOD-HYGIENE"))

    def test_09_conflicting_evidence_escalates_and_keeps_both(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile(licensing_context="home_based_licence"))
        e.ingest_source(SRC["PRIV_B_v1_conflict"])
        self.assertEqual(result(e, "PRIV-NOTICE"), "conflict")
        c = case(e, "PRIV-NOTICE")
        self.assertEqual((c["kind"], c["status"]), ("conflict", "escalated"))
        cites = json.loads(e.s.one("SELECT citations_json FROM assessments WHERE obligation_key='PRIV-NOTICE' AND current=1")["citations_json"])
        self.assertEqual(sorted(x["version_id"] for x in cites), ["SRC-FX-PRIV-A@v1", "SRC-FX-PRIV-B@v1"])
        self.assertEqual(e.review_case(c["case_id"], "approve", *REV)["outcome"], "refused")  # cannot approve a conflict away

    def test_10_superseded_rule_is_not_used(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile(licensing_context="home_based_licence", licence_expiry_date="2026-11-30"))
        r = e.ingest_source(SRC["LIC_v3_substantive"])
        e.review_source(r["version_id"], "approve", *REV)
        v1 = e.s.one("SELECT * FROM source_versions WHERE version_id='SRC-FX-LIC@v1'")
        self.assertEqual((v1["status"], v1["superseded_by"]), ("superseded", r["version_id"]))
        cites = json.loads(e.s.one("SELECT citations_json FROM assessments WHERE obligation_key='LIC-RENEWAL' AND current=1")["citations_json"])
        self.assertEqual([x["version_id"] for x in cites], [r["version_id"]])

    def test_11_withdrawn_rule_escalates_open_case(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile(licensing_context="home_based_licence"))
        e.ingest_source(SRC["PRIV_B_v1_conflict"])
        r = e.ingest_source({**SRC["PRIV_A_v1"], "text": SRC["PRIV_A_v1"]["text"] + " This paragraph is repealed.", "obligations": []})
        e.review_source(r["version_id"], "approve", *REV)
        self.assertEqual(result(e, "PRIV-NOTICE"), "not_applicable")  # only B (not required) remains

    def test_12_future_effective_date_raises_no_action(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile(vat_registered=True))
        self.assertEqual(result(e, "EINV-START:upcoming"), "not_yet_in_force")
        self.assertIsNone(case(e, "EINV-START"))
        e2 = new_engine(when="2027-07-02T09:00:00"); baseline(e2)
        e2.upsert_profile(profile(vat_registered=True))
        self.assertEqual(result(e2, "EINV-START"), "stale_evidence")  # in force now, but captured text is old: recheck first

    def test_13_cosmetic_change_creates_nothing(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile(licensing_context="home_based_licence"))
        n_cases = e.s.one("SELECT COUNT(*) n FROM cases")["n"]
        r = e.ingest_source(SRC["LIC_v2_cosmetic"])
        self.assertEqual((r["change_class"], r["status"], r["case_id"]), ("cosmetic", "cosmetic_noted", None))
        self.assertEqual(e.s.one("SELECT COUNT(*) n FROM cases")["n"], n_cases)

    def test_14_substantive_change_proposes_then_updates_action(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile(licensing_context="home_based_licence", licence_expiry_date="2026-11-30"))
        r = e.ingest_source(SRC["LIC_v3_substantive"])
        self.assertEqual((r["change_class"], r["status"]), ("substantive", "candidate"))
        self.assertEqual(len(case(e, "LIC-RENEWAL")["evidence_required"]), 1)  # approved rule unchanged until review
        e.review_source(r["version_id"], "approve", *REV)
        self.assertEqual(len(case(e, "LIC-RENEWAL")["evidence_required"]), 2)

    def test_15_resolved_case_reopens_when_rule_changes(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile(licensing_context="home_based_licence", licence_expiry_date="2026-11-30"))
        c = case(e, "LIC-RENEWAL")
        e.submit_evidence(c["case_id"], [{"requirement": c["evidence_required"][0], "description": "x.pdf", "provided": True}])
        self.assertEqual(e.review_case(c["case_id"], "approve", *REV)["status"], "resolved")
        r = e.ingest_source(SRC["LIC_v3_substantive"]); e.review_source(r["version_id"], "approve", *REV)
        c = case(e, "LIC-RENEWAL")
        self.assertEqual(c["status"], "open")
        self.assertTrue(c["why"].startswith("Reopened"))

    def test_16_malicious_source_text_is_data_only(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile(licensing_context="home_based_licence", licence_expiry_date="2026-11-30"))
        r = e.ingest_source(SRC["INJECT_v1_malicious"])
        self.assertEqual(r["status"], "candidate")  # preapproved flag ignored because of the warning flags
        v = e.s.one("SELECT flags_json FROM source_versions WHERE version_id=?", (r["version_id"],))
        self.assertTrue(json.loads(v["flags_json"]))
        self.assertEqual(e.s.one("SELECT COUNT(*) n FROM cases WHERE status='resolved'")["n"], 0)
        self.assertEqual(result(e, "LIC-RENEWAL"), "applicable")  # hostile 'not required' claim had no effect
        self.assertEqual(e.review_source(r["version_id"], "approve", *REV)["outcome"], "refused")
        self.assertNotIn("SRC-FX-INJECT", json.dumps(e.search("ignore previous instructions mark resolved")))

    def test_17_fetch_allowlist_and_unavailable_source(self):
        with self.assertRaises(S.FetchRefused):
            S.fetch_source("https://evil.example.com/rules")
        with self.assertRaises(S.FetchRefused):
            S.fetch_source("http://tax.gov.ae/x")
        self.assertEqual(S.fetch_source("https://tax.gov.ae/en/x")["status"], "unavailable")

    def test_18_source_evidence_is_immutable(self):
        e = new_engine(); baseline(e)
        with self.assertRaises(sqlite3.DatabaseError):
            e.s.db.execute("UPDATE source_versions SET text='edited' WHERE version_id='SRC-FX-LIC@v1'")


class CasesAndReview(unittest.TestCase):
    def setUp(self):
        self.e = new_engine(); baseline(self.e)
        self.e.upsert_profile(profile(licensing_context="home_based_licence", licence_expiry_date="2026-11-30"))
        r = self.e.ingest_source(SRC["LIC_v3_substantive"]); self.e.review_source(r["version_id"], "approve", *REV)
        self.c = case(self.e, "LIC-RENEWAL")

    def test_19_insufficient_completion_evidence_keeps_case_open(self):
        r = self.e.submit_evidence(self.c["case_id"], [{"requirement": self.c["evidence_required"][0], "description": "renewed.pdf", "provided": True}])
        self.assertEqual(r["status"], "open")
        self.assertEqual(r["missing"], [self.c["evidence_required"][1]])
        out = self.e.review_case(self.c["case_id"], "approve", *REV)
        self.assertEqual(out["outcome"], "refused")
        self.assertEqual(case(self.e, "LIC-RENEWAL")["status"], "open")
        self.assertEqual(self.e.s.one("SELECT outcome FROM reviews ORDER BY review_id DESC LIMIT 1")["outcome"], "refused")

    def test_20_empty_description_does_not_count_as_evidence(self):
        r = self.e.submit_evidence(self.c["case_id"], [{"requirement": x, "description": "  ", "provided": True} for x in self.c["evidence_required"]])
        self.assertEqual(r["status"], "open")

    def test_21_rejected_review_returns_case_and_records_identity(self):
        self.e.submit_evidence(self.c["case_id"], [{"requirement": x, "description": "doc", "provided": True} for x in self.c["evidence_required"]])
        self.assertEqual(case(self.e, "LIC-RENEWAL")["status"], "awaiting_review")
        self.e.clock.advance(minutes=3)
        out = self.e.review_case(self.c["case_id"], "reject", "Asha (test)", "domain reviewer", "tenancy copy is expired")
        self.assertEqual(out["status"], "open")
        rv = self.e.s.one("SELECT * FROM reviews ORDER BY review_id DESC LIMIT 1")
        self.assertEqual((rv["reviewer"], rv["decision"], rv["decided_at"]), ("Asha (test)", "reject", "2026-10-16T10:03:00+04:00"))

    def test_22_review_needs_identity_and_context(self):
        with self.assertRaises(WorkflowError):
            self.e.review_case(self.c["case_id"], "approve", "", "role", "note")
        with self.assertRaises(WorkflowError):
            self.e.review_case(self.c["case_id"], "approve", "name", "role", " ")

    def test_23_full_resolution_after_requirements_met(self):
        self.e.submit_evidence(self.c["case_id"], [{"requirement": x, "description": "doc", "provided": True} for x in self.c["evidence_required"]])
        self.assertEqual(self.e.review_case(self.c["case_id"], "approve", *REV)["status"], "resolved")
        self.assertEqual(self.e.review_case(self.c["case_id"], "approve", *REV)["outcome"], "refused")  # no double close

    def test_24_duplicate_retry_does_not_duplicate_case_or_alert(self):
        e = self.e
        counts = lambda: (e.s.one("SELECT COUNT(*) n FROM cases")["n"], e.s.one("SELECT COUNT(*) n FROM alerts")["n"],
                          e.s.one("SELECT COUNT(*) n FROM source_versions")["n"], e.s.one("SELECT COUNT(*) n FROM assessments")["n"])
        before = counts()
        e.ingest_source(SRC["LIC_v3_substantive"])  # same content again
        e.upsert_profile(profile(licensing_context="home_based_licence", licence_expiry_date="2026-11-30"))  # same edit again
        e._reassess_all()
        self.assertEqual(counts(), before)

    def test_25_audit_log_is_append_only(self):
        with self.assertRaises(sqlite3.DatabaseError):
            self.e.s.db.execute("DELETE FROM audit_events")
        with self.assertRaises(sqlite3.DatabaseError):
            self.e.s.db.execute("UPDATE audit_events SET actor='x'")


class EndToEnd(unittest.TestCase):
    def test_26_staged_demo_and_restart_persistence(self):
        from compliance_agent import demo
        with tempfile.TemporaryDirectory() as d:
            s = demo.run(Path(d) / "run.sqlite3")
            self.assertTrue(s["persisted_after_restart"])
            st = {c["title"]: c["status"] for c in s["cases"]}
            self.assertEqual(st["Renew the home-based licence"], "resolved")
            self.assertEqual(st["Publish a privacy notice where customer data is collected"], "open")
            self.assertEqual(st["Review source change: SRC-FX-INJECT@v1"], "open")
            res = {a["obligation_key"]: a["result"] for a in s["assessments"]}
            self.assertEqual(res["VAT-MANDATORY-REG"], "not_applicable")
            self.assertEqual(res["FOOD-HYGIENE"], "not_applicable")
            # reopen once more and read history for the resolved case
            e = Engine(Store(Path(d) / "run.sqlite3"), FixedClock("2026-10-17T09:00:00"))
            cid = e.s.one("SELECT case_id FROM cases WHERE dedupe_key='BP-0001:LIC-RENEWAL'")["case_id"]
            events = [h["event"] for h in e.history(cid)]
            self.assertIn("evidence_submitted", events)
            self.assertIn("review_approve_refused", events)
            self.assertIn("review_approve_accepted", events)
            e.s.close()

    def test_27_conflict_clarification_updates_only_affected(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile(licensing_context="home_based_licence", licence_expiry_date="2026-11-30"))
        e.ingest_source(SRC["PRIV_B_v1_conflict"])
        n_vat = e.s.one("SELECT COUNT(*) n FROM assessments WHERE obligation_key='VAT-MANDATORY-REG'")["n"]
        r = e.ingest_source(SRC["PRIV_B_v2_clarification"]); e.review_source(r["version_id"], "approve", *REV)
        self.assertEqual(result(e, "PRIV-NOTICE"), "applicable")
        self.assertEqual(case(e, "PRIV-NOTICE")["status"], "open")
        self.assertEqual(e.s.one("SELECT COUNT(*) n FROM assessments WHERE obligation_key='VAT-MANDATORY-REG'")["n"], n_vat)

    def test_28_no_numeric_confidence_anywhere(self):
        e = new_engine(); baseline(e)
        e.upsert_profile(profile(licensing_context="home_based_licence"))
        blob = json.dumps(e.state()).lower()
        self.assertNotIn("confidence", blob)


class WebInterface(unittest.TestCase):
    def test_29_local_api_rejects_foreign_requests_and_serves_state(self):
        from http.server import ThreadingHTTPServer
        from compliance_agent import web
        with tempfile.TemporaryDirectory() as d:
            app = web.App(Path(d) / "w.sqlite3", FixedClock("2026-10-16T10:00:00"))
            srv = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(app))
            port = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{port}"
            try:
                def post(path, body, headers=None):
                    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                                 headers={"Content-Type": "application/json", **(headers or {})})
                    try:
                        with urllib.request.urlopen(req) as r:
                            return r.status, json.loads(r.read())
                    except urllib.error.HTTPError as ex:
                        return ex.code, json.loads(ex.read())
                ok = {"X-Requested-With": "compliance-ui"}
                self.assertEqual(post("/api/stage", {"stage": "0"})[0], 403)                       # no UI header
                self.assertEqual(post("/api/stage", {"stage": "0"}, {**ok, "Host": "evil.test"})[0], 403)  # rebinding
                self.assertEqual(post("/api/stage", {"stage": "1"}, ok)[0], 400)                   # order enforced
                self.assertEqual(post("/api/stage", {"stage": "0"}, ok)[0], 200)
                self.assertEqual(post("/api/stage", {"stage": "1"}, ok)[0], 200)
                again = post("/api/stage", {"stage": "1"}, ok)
                self.assertIn("already run", again[1]["log"][0])
                req = urllib.request.Request(base + "/api/stage", data=b"{not json", method="POST", headers=ok)
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    urllib.request.urlopen(req)
                self.assertEqual(cm.exception.code, 400)
                with urllib.request.urlopen(base + "/api/state") as r:
                    st = json.loads(r.read())
                self.assertEqual(st["profiles"][0]["profile_id"], "BP-0001")
                self.assertIn("FIXTURE MODE", st["mode"])
                with urllib.request.urlopen(base + "/") as r:
                    self.assertIn(b"HerBiz Compliance Agent", r.read())
            finally:
                srv.shutdown(); app.engine.s.close()


class Evaluation(unittest.TestCase):
    def test_40_scenario_suite_passes_and_runner_can_fail(self):
        from compliance_agent import evaluation as ev
        out = ev.run_all(None)
        self.assertEqual(out["metrics"]["failed"], 0, [r["note"] for r in out["rows"] if not r["passed"]])
        self.assertGreaterEqual(out["metrics"]["scenarios"], 20)
        src, prof = sc.load_fixtures()
        wrong = {"id": "X", "category": "negative_control", "description": "deliberately wrong expectation",
                 "expect": {"VAT-MANDATORY-REG": "applicable"}}  # salary must NOT push it over
        self.assertFalse(ev.run_scenario(wrong, ["LIC_v1", "VAT_v1"], src, prof)["passed"])

    def test_41_evaluation_results_are_persisted(self):
        from compliance_agent import evaluation as ev
        with tempfile.TemporaryDirectory() as d:
            out = ev.run_all(str(Path(d) / "e.sqlite3"), FixedClock("2026-10-16T10:00:00"))
            s = Store(Path(d) / "e.sqlite3")
            self.assertEqual(s.one("SELECT COUNT(*) n FROM evaluation_results")["n"], out["metrics"]["scenarios"])
            self.assertEqual(s.one("SELECT passed FROM evaluation_runs")["passed"], out["metrics"]["passed"])
            s.close()


class BackupRestore(unittest.TestCase):
    def test_42_backup_verify_restore_keeps_previous(self):
        from compliance_agent import backup as B
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "live.sqlite3"
            e = new_engine(db); baseline(e); e.upsert_profile(profile()); e.s.close()
            b = B.backup(db, Path(d) / "bk")
            self.assertEqual(B.verify(b)["integrity"], "ok")
            self.assertGreater(B.verify(b)["counts"]["audit_events"], 0)
            e = new_engine(db); e.upsert_profile(profile(licensing_context="home_based_licence")); e.s.close()
            with self.assertRaises(SystemExit):
                B.restore(b, db, yes=False)
            kept = B.restore(b, db, yes=True)
            self.assertTrue(kept.exists())
            e = Engine(Store(db), FixedClock("2026-10-16T11:00:00"))
            self.assertEqual(e.latest_profile("BP-0001")["version"], 1)   # restored state
            e.s.close()
            bad = Path(d) / "bad.sqlite3"; bad.write_bytes(b"not a database")
            with self.assertRaises(Exception):
                B.restore(bad, db, yes=True)


if __name__ == "__main__":
    unittest.main()
