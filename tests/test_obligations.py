"""HerBiz 360 obligations engine (Workstream B, D-061): synthetic profiles only. No network, no model, no spend.
Validity comes from WS-C contract v1.1 pinned at a committed revision; C's working tree is never read."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compliance_agent.obligations import ct_demo as D, engine as E, profile as PR, validity as V  # noqa: E402

DB_COPY = ROOT / "data" / "CL_ws_b_exact_copy.sqlite3"
AUTH_MD5 = "26e202b87a062288e56bcda1de9b0217"
KB_MD5 = "c33160221efe42f2425a5725945a07af"
TODAY = dt.date(2026, 10, 17)
PROFILES = {p["profile_id"]: p for p in json.loads((ROOT / "fixtures/obligations/CL_synthetic_profiles_360.json").read_text())["profiles"]}
CT_IDS = ("C360-07", "C360-08", "C360-10", "C360-11", "C360-14")


def by_id(report):
    return {r["id"]: r for r in report["obligations"]}


class FakeCertified:
    """Stands in for a FUTURE approved WS-C export, to prove the reviewed path works. Not real data."""
    available, origin, error = True, "fake", None

    def current_version(self, src):
        return "v1"

    def label(self, kind, tuples):
        return {"certified": True, "blockers": [], "validity_issue_kinds": [], "user_wording": "test"}


SV = None


def setUpModule():
    global SV
    SV = V.load_pinned(DB_COPY, today=TODAY.isoformat())


class Profile(unittest.TestCase):
    def test_01_synthetic_flag_required(self):
        p = copy.deepcopy(PROFILES["SYN-P01"]); p["synthetic"] = False
        with self.assertRaises(ValueError):
            PR.validate(p)

    def test_02_not_sure_is_unknown_and_required_gaps_asked(self):
        v = PR.validate(PROFILES["SYN-P05"])
        self.assertIn("revenue_band_last_12m", v["missing_required"])
        self.assertIn("jurisdiction_type", v["missing_required"])
        self.assertNotIn("revenue_band_last_12m", v["facts"])
        for f in v["missing_required"]:
            self.assertTrue(PR.question(f))

    def test_03_person_type_derived(self):
        self.assertEqual(PR.validate(PROFILES["SYN-P06"])["facts"]["person_type"], "natural_person")
        self.assertEqual(PR.validate(PROFILES["SYN-P03"])["facts"]["person_type"], "juridical_person")

    def test_04_band_becomes_interval_and_dates_use_injected_day(self):
        f = PR.evaluator_facts(PR.validate(PROFILES["SYN-P02"])["facts"], TODAY)
        self.assertEqual(f["taxable_supplies_last_12m_aed"], (187500.0, 375000.0))
        self.assertEqual(f["days_until_licence_expiry"], (dt.date(2027, 3, 1) - TODAY).days)


class States(unittest.TestCase):
    def test_10_resolve_state_table(self):
        cert, unc = {"certified": True}, {"certified": False}
        R = E.resolve_state
        self.assertEqual(R("no_reviewed_rule", True, cert, "potential")[0], "blocked_pending_legal_validation")
        self.assertEqual(R("blocked_source_conflict", None, cert)[0], "blocked_pending_legal_validation")
        self.assertEqual(R("draft_unreviewed", None, unc)[0], "insufficient_information")
        self.assertEqual(R("draft_unreviewed", True, unc, "blocked")[0], "blocked_pending_legal_validation")
        self.assertEqual(R("draft_unreviewed", True, unc, "potential")[0], "potentially_applicable")
        self.assertEqual(R("draft_unreviewed", False, unc, "potential")[0], "blocked_pending_legal_validation")
        self.assertEqual(R("draft_unreviewed", True, cert, "potential")[0], "potentially_applicable")  # draft never certifies
        self.assertEqual(R("reviewed", True, unc)[0], "blocked_pending_legal_validation")
        self.assertEqual(R("reviewed", True, cert)[0], "applicable")
        self.assertEqual(R("reviewed", False, cert)[0], "not_applicable")
        self.assertEqual(R("synthetic_test", True, unc, "blocked", "synthetic_test", "SYN-X")[0], "applicable")
        self.assertEqual(R("reviewed", True, cert, "potential", "corporate_tax", "C360-07")[0], "blocked_pending_legal_validation")
        for bad in (("draft_unreviewed", True, unc, "yes"), ("made_up", True, unc), ("synthetic_test", True, unc, "blocked", "vat", "C360-01"),
                    ("synthetic_test", True, unc, "blocked", "synthetic_test", "C360-01")):
            with self.assertRaises(ValueError):
                R(*bad)

    def test_11_real_law_never_definitive_today(self):
        for p in PROFILES.values():
            for pol in E.POLICIES:
                for r in E.assess(p, SV, TODAY, pol)["obligations"]:
                    if r["domain"] != "synthetic_test" and r["state"] in ("applicable", "not_applicable"):
                        self.assertEqual(r["reason"].split(" ")[0], "already", (p["profile_id"], r["id"]))

    def test_12_corporate_tax_always_blocked(self):
        for p in PROFILES.values():
            for pol in E.POLICIES:
                rep = by_id(E.assess(p, SV, TODAY, pol))
                for i in CT_IDS:
                    self.assertEqual(rep[i]["state"], "blocked_pending_legal_validation")
                    self.assertIsNone(rep[i]["deadline"]["due_date"])
                    self.assertFalse(rep[i]["sources"]["validity"]["certified"])

    def test_13_policy_switch_only_changes_draft_met_rules(self):
        b, p = by_id(E.assess(PROFILES["SYN-P03"], SV, TODAY, "blocked")), by_id(E.assess(PROFILES["SYN-P03"], SV, TODAY, "potential"))
        self.assertEqual(b["C360-01"]["state"], "blocked_pending_legal_validation")
        self.assertEqual(p["C360-01"]["state"], "potentially_applicable")
        self.assertIsNone(b["C360-01"]["draft_indication"])          # a blocked draft result is not shown to the owner
        self.assertEqual(b["C360-01"]["why"], [])
        self.assertTrue(b["C360-01"]["reviewer_trace"])
        self.assertEqual(p["C360-01"]["draft_indication"], "may apply")
        self.assertTrue(all(w.startswith("Draft check: ") for w in p["C360-01"]["why"]))
        self.assertEqual(E.DEFAULT_POLICY, "blocked")
        self.assertEqual(E.OWNER_POLICIES, ("blocked",))
        self.assertEqual(E.assess(PROFILES["SYN-P03"], SV, TODAY)["audience"], "owner")
        prev = E.assess(PROFILES["SYN-P03"], SV, TODAY, "potential")
        self.assertEqual(prev["audience"], "reviewer_only")
        self.assertTrue(prev["banner"].startswith("REVIEWER PREVIEW"))

    def test_14_missing_facts_ask_owner_questions(self):
        rep = by_id(E.assess(PROFILES["SYN-P05"], SV, TODAY))
        self.assertEqual(rep["C360-03"]["state"], "insufficient_information")
        self.assertIn("draft", rep["C360-03"]["reason"])
        lic = rep["SYN-LIC-RENEWAL"]
        self.assertEqual(lic["state"], "insufficient_information")
        self.assertEqual([m["fact"] for m in lic["missing_information"]], ["licence_expiry_date"])  # derived fact mapped back
        self.assertTrue(all(m["question"] for m in lic["missing_information"]))

    def test_15_band_straddling_threshold_asks_exact_amount(self):
        r = by_id(E.assess(PROFILES["SYN-P02"], SV, TODAY))["C360-02"]
        self.assertEqual(r["state"], "insufficient_information")
        self.assertTrue(any("straddles" in m["fact"] for m in r["missing_information"]))

    def test_16_already_registered_is_owner_fact_not_judgement(self):
        r = by_id(E.assess(PROFILES["SYN-P04"], SV, TODAY))["C360-01"]
        self.assertEqual(r["state"], "not_applicable")
        self.assertIn("no legal judgement", r["reason"])
        self.assertIn(E.CHECK, r["owner_text"])

    def test_17_deregistration_blocked_by_source_conflict(self):
        r = by_id(E.assess(PROFILES["SYN-P04"], SV, TODAY, "potential"))["C360-05"]
        self.assertEqual((r["state"], r["reason"]), ("blocked_pending_legal_validation", "official sources conflict"))

    def test_18_reviewed_and_certified_path_works_with_fake_export(self):
        cat = copy.deepcopy(E.load_catalogues(("vat",)))
        for ob in cat:
            if ob["id"] == "C360-03":
                ob["rule_status"] = "reviewed"
        r = by_id(E.assess(PROFILES["SYN-P04"], FakeCertified(), TODAY, catalogue=cat))["C360-03"]
        self.assertEqual(r["state"], "applicable")
        self.assertIsNone(r["deadline"]["due_date"])   # its deadline is draft text: never computed


class Guards(unittest.TestCase):
    """Code-level guards hold even when catalogue data is tampered with (review finding 1)."""

    def tampered(self, ob_id, **changes):
        cat = copy.deepcopy(E.load_catalogues())
        for ob in cat:
            if ob["id"] == ob_id:
                ob.update(changes)
        return cat

    def test_50_ct_blocked_even_if_marked_reviewed_with_rule_and_skip(self):
        cat = self.tampered("C360-07", rule_status="reviewed", rule={"all": [{"fact": "has_employees", "op": "is_false"}]},
                            skip_if={"fact": "legal_form", "op": "eq", "value": "llc"},
                            deadline={"kind": "offset_from_fact", "fact": "licence_expiry_date", "days": 0, "basis": "x"})
        r = by_id(E.assess(PROFILES["SYN-P03"], FakeCertified(), TODAY, "potential", cat))["C360-07"]
        self.assertEqual(r["state"], "blocked_pending_legal_validation")
        self.assertIsNone(r["deadline"]["due_date"])

    def test_51_real_law_cannot_pose_as_test_rule(self):
        cat = self.tampered("C360-03", rule_status="synthetic_test")
        with self.assertRaises(ValueError):
            E.assess(PROFILES["SYN-P04"], SV, TODAY, catalogue=cat)

    def test_52_unknown_status_and_policy_refused(self):
        with self.assertRaises(ValueError):
            E.assess(PROFILES["SYN-P04"], SV, TODAY, catalogue=self.tampered("C360-03", rule_status="approved"))
        with self.assertRaises(ValueError):
            E.assess(PROFILES["SYN-P04"], SV, TODAY, policy="yes")

    def test_53_malformed_provision_fails_closed_for_that_item_only(self):
        rep = by_id(E.assess(PROFILES["SYN-P04"], SV, TODAY, catalogue=self.tampered("C360-03", provisions=["NOPIPE"])))
        self.assertFalse(rep["C360-03"]["sources"]["validity"]["certified"])
        self.assertEqual(rep["SYN-WPS-PAYROLL"]["state"], "applicable")

    def test_54_band_never_compared_with_eq(self):
        v, m, _ = E._EV._eval({"fact": "taxable_supplies_last_12m_aed", "op": "eq", "value": 375000},
                              {"taxable_supplies_last_12m_aed": (375000.0, 1000000.0)}, {})
        self.assertIsNone(v)

    def test_55_interval_edges(self):
        ev = lambda val, op, t=375000: E._EV._eval({"fact": "x", "op": op, "value": t}, {"x": val}, {})[0]
        self.assertFalse(ev(375000, "gt")); self.assertTrue(ev(375000, "gte")); self.assertTrue(ev(375001, "gt"))
        self.assertIsNone(ev((187500.0, 375000.0), "gte")); self.assertFalse(ev((187500.0, 375000.0), "gt"))
        self.assertTrue(ev((375000.0, 1000000.0), "gte")); self.assertIsNone(ev((375000.0, 1000000.0), "gt"))
        self.assertTrue(ev((3000000.0, float("inf")), "gt")); self.assertFalse(ev((0.0, 187500.0), "gte"))
        self.assertTrue(ev(100, "lt")); self.assertIsNone(ev((0.0, 400000.0), "lte"))


class ProfileStrictness(unittest.TestCase):
    def with_fields(self, **f):
        p = copy.deepcopy(PROFILES["SYN-P03"]); p["fields"].update(f)
        return p

    def test_60_bad_values_refused(self):
        for f in ({"taxable_supplies_last_12m_aed": float("nan")}, {"taxable_supplies_last_12m_aed": float("inf")},
                  {"licence_expiry_date": "20261201"}, {"licence_expiry_date": "2026-W49-1"}, {"employees_count": 2.5},
                  {"activities": []}, {"unknown_field": 1}):
            with self.assertRaises(PR.ProfileError, msg=f):
                PR.validate(self.with_fields(**f))
        PR.validate(self.with_fields(financial_year_end="02-29"))   # a valid month-day

    def test_61_contradictions_become_questions(self):
        v = PR.validate(self.with_fields(revenue_band_last_12m="0-187500", taxable_supplies_last_12m_aed=900000))
        self.assertIn("taxable_supplies_last_12m_aed", v["clarify"])
        r = by_id(E.assess(self.with_fields(revenue_band_last_12m="0-187500", taxable_supplies_last_12m_aed=900000), SV, TODAY, "potential"))
        self.assertEqual(r["C360-01"]["state"], "insufficient_information")
        self.assertIn("employees_count", PR.validate(self.with_fields(has_employees=False, employees_count=3))["clarify"])
        self.assertIn("person_type", PR.validate(self.with_fields(person_type="natural_person"))["clarify"])

    def test_62_overdue_test_date_told_to_owner(self):
        r = by_id(E.assess(self.with_fields(licence_expiry_date="2026-10-01"), SV, TODAY))["SYN-LIC-RENEWAL"]
        self.assertTrue(r["deadline"]["overdue"])
        self.assertIn("has passed", r["owner_text"])


class Validity(unittest.TestCase):
    def test_20_pinned_export_loads_on_exact_copy(self):
        self.assertTrue(SV.available, SV.error)
        self.assertTrue(SV.origin.endswith("@" + V.PINNED_COMMIT))

    def test_21_fail_closed_stale_wrong_commit_wrong_db(self):
        self.assertFalse(V.load_pinned(DB_COPY, today="2027-01-01").available)
        self.assertFalse(V.load_pinned(DB_COPY, commit="0000000").available)
        self.assertFalse(V.load_pinned(DB_COPY, c_repo=ROOT / "no_such_repo", today=TODAY.isoformat()).available)
        self.assertFalse(V.load_pinned(ROOT / "data" / "CL_ws_b_kb_copy.sqlite3", today=TODAY.isoformat()).available)

    def test_22_no_validity_means_nothing_certified(self):
        for sv in (None, V.load_pinned(DB_COPY, today="2027-01-01")):
            rep = E.assess(PROFILES["SYN-P04"], sv, TODAY, "potential")
            self.assertFalse(any(r["sources"]["validity"].get("certified") for r in rep["obligations"]))

    def test_23_real_vat_provisions_not_certified_today(self):
        r = by_id(E.assess(PROFILES["SYN-P04"], SV, TODAY))["C360-03"]
        self.assertTrue(r["sources"]["validity"]["checked"])
        self.assertFalse(r["sources"]["validity"]["certified"])
        self.assertIn("source_not_approved", r["sources"]["validity"]["blockers"])


class DeadlinesAndDocuments(unittest.TestCase):
    def test_30_deadlines_only_for_applicable_test_rules(self):
        for p in PROFILES.values():
            for pol in E.POLICIES:
                for r in E.assess(p, SV, TODAY, pol)["obligations"]:
                    if r["deadline"]["computed"]:
                        self.assertEqual((r["rule_status"], r["state"]), ("synthetic_test", "applicable"))

    def test_31_licence_and_payroll_dates(self):
        rep = by_id(E.assess(PROFILES["SYN-P03"], SV, TODAY))
        self.assertEqual(rep["SYN-LIC-RENEWAL"]["deadline"]["due_date"], "2026-12-01")
        self.assertEqual(rep["SYN-LIC-RENEWAL"]["deadline"]["prepare_from"], "2026-11-01")
        self.assertEqual(rep["SYN-WPS-PAYROLL"]["deadline"]["due_date"], "2026-11-10")
        self.assertEqual(E.deadline({"deadline": {"kind": "monthly_day", "day": 31, "basis": "t"}}, "applicable", {}, dt.date(2027, 1, 31))["due_date"], "2027-01-31")
        self.assertEqual(E.deadline({"deadline": {"kind": "monthly_day", "day": 31, "basis": "t"}}, "applicable", {}, dt.date(2027, 2, 1))["due_date"], "2027-02-28")

    def test_32_draft_text_deadline_never_computed(self):
        r = by_id(E.assess(PROFILES["SYN-P03"], SV, TODAY, "potential"))["C360-01"]
        self.assertFalse(r["deadline"]["computed"])
        self.assertIn("not a computed date", r["deadline"]["basis"])

    def test_33_document_readiness(self):
        r = by_id(E.assess(PROFILES["SYN-P01"], SV, TODAY))["SYN-LIC-RENEWAL"]
        self.assertEqual([d["id"] for d in r["documents"]["ready"]], ["trade_licence", "owner_id"])
        self.assertEqual([d["id"] for d in r["documents"]["missing"]], ["tenancy_or_noc"])
        self.assertEqual(r["documents"]["readiness"], 0.67)
        na = by_id(E.assess(PROFILES["SYN-P02"], SV, TODAY))["SYN-WPS-PAYROLL"]
        self.assertEqual(na["documents"]["required"], [])


class FailClosedOwnerView(unittest.TestCase):
    """D-062: in the owner view, no unreviewed legal rule gives a decision, date, eligibility or filing instruction."""

    def test_70_owner_view_has_no_unreviewed_answers(self):
        for p in PROFILES.values():
            for r in E.assess(p, SV, TODAY)["obligations"]:
                if r["rule_status"] == "synthetic_test":
                    self.assertIn("TEST RULE", r["label"]); continue
                self.assertNotEqual(r["state"], "potentially_applicable")
                self.assertIsNone(r["deadline"]["due_date"])
                self.assertIsNone(r["draft_indication"]) if r["state"] == "blocked_pending_legal_validation" else None
                if r["state"] in ("applicable", "not_applicable"):
                    self.assertIn("no legal judgement", r["reason"])

    def test_71_sbr_note_kept_and_blocked(self):
        r = by_id(E.assess(PROFILES["SYN-P06"], SV, TODAY))["C360-11"]
        self.assertEqual(r["state"], "blocked_pending_legal_validation")
        self.assertIn("CT-MD131-2026", r["sources"]["source_candidates"])
        self.assertIn("MD 131/2026", r["deadline"]["draft_basis_for_reviewer"])

    def test_72_owner_demo_files_are_fail_closed(self):
        demo = ROOT / "docs" / "360" / "demo"
        self.assertFalse((demo / "CL_obligations_demo_potential.json").exists())
        for rep in json.loads((demo / "CL_obligations_demo_blocked.json").read_text()):
            self.assertEqual(rep["audience"], "owner")


class CorporateTaxDemo(unittest.TestCase):
    """D-064: two-persona synthetic CT demonstration; WS-C persona only; fail closed; labelled; read-only fixture for WS-A."""

    @classmethod
    def setUpClass(cls):
        cls.personas = json.loads((ROOT / "fixtures/obligations/CL_ct_demo_personas_wsc.json").read_text())["profiles"]
        cls.c = D.load_c_labels(TODAY.isoformat())
        cls.reps = {p["profile_id"]: D.assess_demo(p, SV, TODAY, cls.c) for p in cls.personas}

    def test_80_only_wsc_persona_variants(self):
        self.assertEqual(sorted(self.reps), list(D.DEMO_PROFILES))
        with self.assertRaises(ValueError):
            D.assess_demo(PROFILES["SYN-P06"], SV, TODAY, self.c)

    def test_81_ct_rows_blocked_labelled_and_withheld(self):
        for rep in self.reps.values():
            ct = [r for r in rep["obligations"] if r["domain"] == "corporate_tax"]
            self.assertEqual(len(ct), 5)
            for r in ct:
                d = r["demo_scenario"]
                self.assertEqual(r["state"], "blocked_pending_legal_validation")
                self.assertEqual(d["demo_label"], "Demo scenario — fictional business.")
                self.assertIs(d["validated_guidance"], False); self.assertIs(d["release_approved"], False)
                self.assertIsNone(r["deadline"]["due_date"]); self.assertIsNone(r["draft_indication"])
                self.assertIn("due dates", d["withheld"])
                self.assertTrue(d["profile_walkthrough"]); self.assertTrue(d["possible_workflow_steps"])
            self.assertEqual(D.demo_wording_violations(rep), [])
            self.assertTrue(all("demo_scenario" not in r for r in rep["obligations"] if r["domain"] != "corporate_tax"))

    def test_82_wsc_labels_attached_never_approved(self):
        self.assertTrue(self.c["available"], self.c["error"])
        sbr = by_id(self.reps["SYN-AMAL-B"])["C360-11"]["demo_scenario"]["source_label"]
        self.assertEqual(sbr["obligation_id"], "CT-SBR")
        self.assertIs(sbr["release_approved"], False)
        self.assertIn("CT-MD131-2026", [c["source_id"] for c in sbr["citations"]])
        self.assertEqual(sbr["user_wording"], "Demo scenario (fictional business). Not legal, tax or accounting advice. Not reviewed by a "
                         "qualified professional. Not a compliance decision. Shown as a demonstration scenario only. Open questions: CT law "
                         "text not collected; article-level citations unavailable.")
        self.assertEqual(sbr["contract"], "0.2")
        self.assertTrue(all(c["citation_chip"] for c in sbr["citations"]))
        self.assertEqual({c["citation_chip"] for c in sbr["citations"] if c["evidence_level"] == "observed"}, {"Source found, not reviewed"})

    def test_83_labels_fail_closed(self):
        bad = D.load_c_labels(TODAY.isoformat(), commit="0000000")
        self.assertFalse(bad["available"])
        rep = D.assess_demo(self.personas[0], SV, TODAY, bad)
        for r in rep["obligations"]:
            if r["domain"] == "corporate_tax":
                self.assertIs(r["demo_scenario"]["source_label"]["available"], False)

    def test_84_variants_answer_from_wsc_persona_card(self):
        a = by_id(self.reps["SYN-AMAL-A"])["C360-08"]["demo_scenario"]["profile_walkthrough"]
        self.assertIn({"fact": "person_type", "question": PR.question("person_type"), "demo_answer": "natural_person"}, a)
        b = {w["fact"]: w["demo_answer"] for w in by_id(self.reps["SYN-AMAL-B"])["C360-07"]["demo_scenario"]["profile_walkthrough"]}
        self.assertEqual((b["person_type"], b["ct_registration_status"], b["licence_issue_date"]), ("juridical_person", "registered", "2025-02-10"))

    def test_85_wsa_fixture_is_current_and_checksummed(self):
        fx = ROOT / "docs/360/demo/wsa/CL_WSA_DEMO_FIXTURE_v1.json"
        data = fx.read_bytes()
        self.assertEqual((fx.parent / (fx.name + ".sha256")).read_text().split()[0], hashlib.sha256(data).hexdigest())
        f = json.loads(data)
        self.assertEqual(f["fixture_contract"], "ws-b-demo-0.4")
        self.assertEqual([r["profile_id"] for r in f["ct_demo_personas"]], list(D.DEMO_PROFILES))
        self.assertNotIn('"potentially_applicable": 1', data.decode())
        self.assertNotIn("reviewer_only", data.decode())
        bad = ("approved", "verified", "certified", "you must", "eligible", "exempt", "compliant")
        for rep in f["ct_demo_personas"] + f["other_synthetic_profiles"]:
            owner = json.dumps([rep["banner"], rep["profile_gaps"]["questions"], rep["owner_rows"]]).lower()
            for w in bad:
                self.assertNotIn(w, owner.replace("validated_guidance", "").replace("release_approved", "").replace("not reviewed", ""), (rep["profile_id"], w))
            for row in rep["owner_rows"]:
                self.assertTrue(set(row) <= set(E.OWNER_FIELDS) | {"demo_scenario"})
        for rep in f["ct_demo_personas"] + f["other_synthetic_profiles"]:
            for row in rep["owner_rows"]:
                if row["id"].startswith("SYN-"):
                    self.assertTrue(row["deadline_display"].startswith(("TEST RULE date (made up): ", "TEST RULE")), row)
                else:
                    self.assertEqual(row["deadline_display"], E.NO_DATE, (rep["profile_id"], row["id"]))
        done = [r for rep in f["ct_demo_personas"] for r in rep["owner_rows"] if r["id"] == "C360-01"]
        self.assertTrue(all(r["state_chip"] == "Owner says done — not checked" for r in done))


class OwnerRowDeadlines(unittest.TestCase):
    """WS-A defect report (legal-kalpu S1, S3): owner rows show no draft timing for real-law items, every profile and state."""

    def test_90_real_law_rows_show_only_standard_sentence(self):
        for p in PROFILES.values():
            for r in E.assess(p, SV, TODAY)["obligations"]:
                row = E.owner_row(r)
                if r["rule_status"] == "synthetic_test":
                    if r["deadline"]["computed"]:
                        self.assertEqual(row["deadline_display"], "TEST RULE date (made up): " + r["deadline"]["due_date"])
                else:
                    self.assertEqual(row["deadline_display"], E.NO_DATE, (p["profile_id"], r["id"], r["state"]))

    def test_91_already_done_row_hides_draft_reading(self):
        row = E.owner_row(by_id(E.assess(PROFILES["SYN-P04"], SV, TODAY))["C360-01"])
        self.assertEqual(row["state_chip"], "Owner says done — not checked")
        self.assertNotIn("Draft reading", row["deadline_display"])

    def test_92_reviewed_certified_rule_may_show_computed_date(self):
        r = {"id": "X", "rule_status": "reviewed", "documents": {"ready": [], "missing": []},
             "deadline": {"computed": True, "due_date": "2027-01-01", "basis": "b"}}
        self.assertEqual(E.owner_row(r)["deadline_display"], "2027-01-01")
        r["rule_status"] = "draft_unreviewed"
        self.assertEqual(E.owner_row(r)["deadline_display"], E.NO_DATE)


class SafetyAndData(unittest.TestCase):
    def test_40_no_forbidden_wording_and_banner_everywhere(self):
        for p in PROFILES.values():
            for pol in E.POLICIES:
                rep = E.assess(p, SV, TODAY, pol)
                self.assertEqual(E.wording_violations(rep), [])
                self.assertIn("Not legal, tax or accounting advice", rep["banner"])
                for r in rep["obligations"]:
                    if r["rule_status"] != "synthetic_test":
                        self.assertIn(E.CHECK, r["owner_text"])
                    else:
                        self.assertIn("TEST RULE", r["label"])

    def test_41_wording_check_catches_definitive_text(self):
        rep = E.assess(PROFILES["SYN-P01"], SV, TODAY)
        rep["obligations"][0]["owner_text"] = "You must register now."
        self.assertTrue(E.wording_violations(rep))

    def test_41b_wording_scan_covers_every_owner_string(self):
        for key in ("why", "owner_actions"):
            rep = E.assess(PROFILES["SYN-P03"], SV, TODAY, "potential")
            rep["obligations"][0][key] = ["Definitely register."]
            self.assertTrue(E.wording_violations(rep), key)
        rep = E.assess(PROFILES["SYN-P03"], SV, TODAY)
        rep["obligations"][0]["deadline"]["basis"] = "Guaranteed by law."
        self.assertTrue(E.wording_violations(rep))

    def test_42_affected_by(self):
        self.assertEqual(E.affected_by(["FTA-VAT-DL8|13"]), ["C360-01"])
        hit = E.affected_by(["FTA-VAT-DL8|*"])
        self.assertTrue({"C360-01", "C360-03", "C360-04"} <= set(hit))
        self.assertTrue(set(hit).isdisjoint(CT_IDS))

    def test_43_catalogue_schema(self):
        ids = set()
        for ob in E.load_catalogues():
            self.assertNotIn(ob["id"], ids); ids.add(ob["id"])
            self.assertIn(ob["rule_status"], ("draft_unreviewed", "no_reviewed_rule", "blocked_source_conflict", "synthetic_test"))
            if ob["domain"] == "corporate_tax":
                self.assertEqual(ob["rule_status"], "no_reviewed_rule"); self.assertIsNone(ob["rule"])
            if ob["rule_status"] == "synthetic_test":
                self.assertIn("TEST RULE", ob["title"]); self.assertFalse(ob.get("provisions"))
            for f in ob.get("facts_needed", []):
                self.assertTrue(f in PR.FIELDS or f == "person_type", f)

    def test_44_fixtures_are_synthetic(self):
        for p in PROFILES.values():
            self.assertTrue(p["synthetic"]); self.assertTrue(p["profile_id"].startswith("SYN-"))

    def test_45_db_copies_unchanged(self):
        self.assertEqual(hashlib.md5(DB_COPY.read_bytes()).hexdigest(), AUTH_MD5)
        self.assertEqual(hashlib.md5((ROOT / "data" / "CL_ws_b_kb_copy.sqlite3").read_bytes()).hexdigest(), KB_MD5)


if __name__ == "__main__":
    unittest.main()
