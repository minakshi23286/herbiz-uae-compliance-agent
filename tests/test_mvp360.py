"""HerBiz 360 MVP — Workstream A regression tests (synthetic only; no network, no AI, no writes to protected data).

Covers: pinned WS B fixture (ws-b-demo-0.4 @ 89dc2b9, A-4 DV-002; earlier ws-b-demo-0.3 @ fdbe131; re-pinned from 30a6f9a on 17 Oct 2026) and engine, WS C sources360 0.2 @ aa50dd4, owner-view filtering,
corporate-tax blocking (D-062, D-064), unknown answers, stale sources, change replay, financial readiness, endpoints,
deterministic replay and no real-owner leakage."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent.mvp360 import adapter as A, pins as P  # noqa: E402

AUTH = ROOT / "data" / "CL_compliance.sqlite3"
md5 = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest() if Path(p).exists() else None   # no DB in the export
BANNER = ("Prototype · synthetic business data · simulated reviewer · Demonstration draft: not legal, tax or accounting advice, "
          "not reviewed, and not a compliance decision · HerBiz does not file or pay")
REVIEWER_ONLY = ("reviewer_trace", "draft_basis_for_reviewer", "why", "rule_status", "sources")


def _available() -> bool:
    try:
        A.fixture(); return AUTH.exists() or P.vendored()     # the vendored export runs without any database
    except P.Unavailable:
        return False


def _pinned_bytes(commit: str, ws: str, path: str) -> bytes:
    """A file as pinned: from git (development repo) or from the checked vendored copy (submission export)."""
    if P.vendored():
        return (P.export(commit, ws) / path).read_bytes()
    import subprocess
    return subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{path}"], capture_output=True, check=True).stdout


@unittest.skipUnless(_available(), "pinned WS B / WS C commits or the authoritative DB not present")
class Mvp360(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = md5(AUTH)

    @classmethod
    def tearDownClass(cls):
        assert md5(AUTH) == cls.before, "the authoritative database changed"

    # --- interfaces ---------------------------------------------------------------------------------------------------
    def test_86_pinned_fixture_matches_committed_checksum_and_contract(self):
        fx = A.fixture()
        self.assertEqual(fx["fixture_contract"], "ws-b-demo-0.4")            # DV-002 (A-4, D-101): was ws-b-demo-0.3
        self.assertEqual(fx["pins"]["ws_c_sources360"], P.C_COMMIT)          # B's fixture uses the same C commit as A
        self.assertEqual(P.B_COMMIT, "89dc2b9")                              # t2-b-rc1; was fdbe131

    def test_87_tampered_fixture_fails_closed(self):
        orig, orig_pub = P.B_FIXTURE_SHA256, P.B_FIXTURE_SHA256_PUBLIC
        try:
            P.B_FIXTURE_SHA256 = P.B_FIXTURE_SHA256_PUBLIC = "0" * 64
            with self.assertRaises(A.Incompatible):
                A.fixture()
        finally:
            P.B_FIXTURE_SHA256, P.B_FIXTURE_SHA256_PUBLIC = orig, orig_pub

    def test_88_c_contract_0_2_labels(self):
        c = P.run_c(True)
        self.assertEqual(c["contract"], "0.2")
        lab = c["labels"]["CT-SBR"]
        self.assertTrue(lab["shown"]); self.assertFalse(lab["release_approved"]); self.assertIn(lab["uncertainty"], ("high", "medium"))
        self.assertTrue(all(x.get("citation_chip") for x in lab["citations"]))
        self.assertEqual(P.run_c(False)["labels"]["CT-SBR"].get("refused"), "corporate_tax_real_profile")

    # --- personas and owner view --------------------------------------------------------------------------------------
    def test_89_personas_are_bs_fixed_fictional_businesses(self):
        ids = [p["id"] for p in A.personas()]
        self.assertEqual(ids[:2], ["SYN-AMAL-A", "SYN-AMAL-B"])
        self.assertEqual(len(ids), 8)
        self.assertTrue(all(i.startswith("SYN-") for i in ids))

    def test_90_owner_view_hides_reviewer_fields_and_keeps_ct_blocked(self):
        for pid in ("SYN-AMAL-A", "SYN-AMAL-B", "SYN-P03", "SYN-P06"):
            with self.subTest(p=pid):
                d = A.dashboard(pid)
                text = json.dumps(d)
                for k in REVIEWER_ONLY:
                    self.assertNotIn(f'"{k}"', text)
                for r in d["rows"]:
                    if r["id"] in A.CT_IDS:
                        self.assertEqual(r["state_chip"], "Blocked: legal validation")

    def test_91_ct_demo_only_for_the_two_amal_variants_and_never_validated(self):
        for pid in ("SYN-AMAL-A", "SYN-AMAL-B"):
            rows = A.ct_journey(pid)["rows"]
            self.assertEqual(len(rows), 5)
            for r in rows:
                ds = r["demo_scenario"]
                self.assertEqual(ds["demo_label"], "Demo scenario — fictional business.")
                self.assertFalse(ds["validated_guidance"]); self.assertFalse(ds["release_approved"])
                self.assertIn("eligibility or relief outcome", ds["withheld"])
        for pid in ("SYN-P01", "SYN-A360-OWNER", "REAL-1"):
            with self.assertRaises(KeyError):
                A.ct_journey(pid)
        self.assertFalse(any("demo_scenario" in r for r in A.dashboard("SYN-P06")["rows"]))

    def test_92_injected_ct_outcome_or_approval_wording_fails_closed(self):
        fx = A.fixture()
        rep = copy.deepcopy(fx["ct_demo_personas"][0])
        bad = copy.deepcopy(rep); next(r for r in bad["owner_rows"] if r["id"] == "C360-08")["state_chip"] = "Applies"
        with self.assertRaises(A.Incompatible):
            A.owner_view(bad, fx["owner_fields"])
        bad = copy.deepcopy(rep); next(r for r in bad["owner_rows"] if r.get("demo_scenario"))["demo_scenario"]["validated_guidance"] = True
        with self.assertRaises(A.Incompatible):
            A.owner_view(bad, fx["owner_fields"])
        bad = copy.deepcopy(rep); bad["owner_rows"][0]["owner_text"] = "This rule is approved."
        with self.assertRaises(A.Incompatible):
            A.owner_view(bad, fx["owner_fields"])

    # --- live engine for made-up answers --------------------------------------------------------------------------------
    def test_93_unknown_answers_become_questions_not_guesses(self):
        d = A.dashboard(fields={"emirate": "AE-SH", "jurisdiction_type": "not_sure", "legal_form": "freelance_permit",
                                "activities": ["design"], "licence_expiry_date": "2027-03-01", "vat_registration_status": "not_sure"})
        self.assertIn("Is your licence from a mainland authority or a free zone?", d["questions"])
        self.assertTrue(all(r["state_chip"] in ("Need more information", "Blocked: legal validation") or r["id"].startswith("SYN-")
                            for r in d["rows"]))
        self.assertFalse(any("demo_scenario" in r for r in d["rows"]))

    def test_94_malformed_answers_get_a_plain_field_message(self):
        cases = {("emirate", "Atlantis"): "please choose one of the options",
                 ("licence_expiry_date", "31/12/2026"): "please enter a full date",
                 ("employees_count", -3): "whole number of 0 or more"}
        for (field, value), words in cases.items():
            with self.subTest(field=field):
                with self.assertRaises(A.InputProblem) as cm:
                    A.dashboard(fields={field: value})
                self.assertEqual(cm.exception.field, field)
                self.assertIn(words, cm.exception.message)
                self.assertNotIn("ProfileError", cm.exception.message)
        self.assertIsNone(A.input_problem("pinned WS B commit is not in this repository"))   # engine trouble still fails closed

    def test_95_stale_sources_fail_closed_or_are_flagged(self):
        prof = {"profile_id": "SYN-A360-OWNER", "synthetic": True, "fields": {"emirate": "AE-DU", "legal_form": "llc", "activities": ["design"],
                                                                            "licence_expiry_date": "2027-01-01"}}
        out = P.run_b(prof, "2026-12-15")                                   # B's validity data is older than 7 days by then
        self.assertFalse(out["source_validity"]["available"])
        self.assertTrue(all(o["state"] in ("blocked_pending_legal_validation", "insufficient_information") for o in out["obligations"]
                            if o["domain"] != "synthetic_test"))
        c = P.run_c(True, "2026-12-15")                                      # C marks sources not re-checked for 30 days as stale
        self.assertTrue(all(x["stale"] for x in c["labels"]["CT-SBR"]["citations"]))

    # --- change replay, finance, determinism --------------------------------------------------------------------------
    def test_96_rule_change_replay_is_report_only(self):
        r = A.change_replay()
        self.assertEqual(r["activation"], "not activated"); self.assertTrue(r["human_review_required"])
        self.assertEqual(r["affected_c"], ["CT-SBR"]); self.assertEqual(r["affected_rows"], ["Small Business Relief (election)"])
        self.assertIn("Ministerial Decision No. 131 of 2026", r["events"][0]["detail"])
        flagged = [x["id"] for x in A.dashboard("SYN-AMAL-B", changed={"CT-SBR"})["rows"] if x["changed_pending_review"]]
        self.assertEqual(flagged, ["C360-11"])
        self.assertTrue(all(x["state_chip"] == "Blocked: legal validation" for x in A.dashboard("SYN-AMAL-B", changed={"CT-SBR"})["rows"]
                            if x["id"] == "C360-11"))                         # flagging never changes the legal status

    def test_97_finance_labels_and_export(self):
        f = A.finance()
        A.scan(f); A.scan(A.content())                                    # what the web endpoints return must pass the wording scan
        self.assertEqual(f["pnl"]["label_level"], "A1")
        self.assertTrue(all("Need more records" in t["result"] for t in f["revenue_tests"]))   # no eligibility verdicts
        csv_text = A.finance_csv().lower()
        for w in ("final", "audited", "certified", "approved", "verified"):
            self.assertNotIn(w, csv_text)
        rows = [l for l in A.finance_csv().splitlines()[1:] if l.strip()]
        self.assertTrue(all(",A1," in l or ",A2," in l for l in rows))

    def test_98_demo_replay_is_deterministic(self):
        self.assertEqual(A.dashboard("SYN-AMAL-A"), A.dashboard("SYN-AMAL-A"))
        self.assertEqual(A.change_replay(), A.change_replay())

    def test_99_who_does_what_keeps_estimate_status_and_no_fees(self):
        w = A.content()["who_does_what"]
        self.assertIn("estimate", w["caption"]); self.assertIn("not been reviewed", w["caption"])
        self.assertNotRegex(json.dumps(w), r"AED\s?\d|\$\d|fee:")

    # --- web ----------------------------------------------------------------------------------------------------------
    def test_100_endpoints_banner_and_real_owner_refusal(self):
        from http.server import ThreadingHTTPServer
        from compliance_agent.clock import FixedClock
        from compliance_agent.web import App, make_handler
        with tempfile.TemporaryDirectory() as d:
            app = App(Path(d) / "w.sqlite3", FixedClock("2026-10-17T10:00:00"), Path(d) / "none.sqlite3")
            srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            post = lambda b: urllib.request.urlopen(urllib.request.Request(base + "/api/360/dashboard", method="POST", data=json.dumps(b).encode(),
                                                    headers={"Content-Type": "application/json", "X-Requested-With": "compliance-ui"}))
            try:
                page = urllib.request.urlopen(base + "/360").read().decode()
                self.assertIn(BANNER, page)
                c = json.loads(urllib.request.urlopen(base + "/api/360/content").read())
                self.assertEqual(c["banner"], BANNER)
                rows = {r["id"]: r for r in json.loads(post({"profile_id": "SYN-AMAL-B", "show_change": True}).read())["rows"]}
                self.assertTrue(rows["C360-11"]["changed_pending_review"])
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    post({"fields": {"emirate": "Atlantis"}})
                self.assertEqual(json.loads(cm.exception.read())["input_problem"]["field"], "emirate")
                for body in ({"profile_id": "REAL-OWNER-1"}, {}):
                    with self.assertRaises(urllib.error.HTTPError) as cm:
                        post(body)
                    self.assertEqual(cm.exception.code, 400)
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    urllib.request.urlopen(base + "/api/360/ct?profile=SYN-P01")
                self.assertEqual(cm.exception.code, 400)
            finally:
                srv.shutdown(); app.engine.s.close()


    # --- board review fixes (17 Oct 2026: tech-sonu, legal-kalpu, product-minakshi, creative-viaan) -------------------
    def _amal(self):
        fx = A.fixture()
        return fx, copy.deepcopy(fx["ct_demo_personas"][1])

    def test_101_missing_citation_or_chip_fails_closed(self):
        fx, rep = self._amal()
        ds = next(r for r in rep["owner_rows"] if r.get("demo_scenario"))["demo_scenario"]
        ds["source_label"]["citations"] = []
        with self.assertRaises(A.Incompatible):
            A.owner_view(rep, fx["owner_fields"])
        fx, rep = self._amal()
        next(r for r in rep["owner_rows"] if r.get("demo_scenario"))["demo_scenario"]["source_label"]["citations"][0].pop("citation_chip")
        with self.assertRaises(A.Incompatible):
            A.owner_view(rep, fx["owner_fields"])

    def test_102_negated_approval_words_also_fail_closed(self):
        fx, rep = self._amal()
        rep["owner_rows"][0]["owner_text"] = "This has not been approved."
        with self.assertRaises(A.Incompatible):
            A.owner_view(rep, fx["owner_fields"])
        with self.assertRaises(A.Incompatible):
            A.scan({"anything": ["fine", {"deep": "certified figures"}]})

    def test_103_ct_detected_by_title_and_bad_demo_block_fails_closed(self):
        fx, rep = self._amal()
        rep["owner_rows"].append({"id": "C360-99", "title": "Corporate tax something new", "state_chip": "Need more information"})
        with self.assertRaises(A.Incompatible):
            A.owner_view(rep, fx["owner_fields"])
        fx, rep = self._amal()
        next(r for r in rep["owner_rows"] if r.get("demo_scenario"))["demo_scenario"] = "oops"
        with self.assertRaises(A.Incompatible):
            A.owner_view(rep, fx["owner_fields"])

    def test_104_no_draft_dates_for_real_law_rows_and_test_dates_labelled(self):
        for pid in ("SYN-AMAL-A", "SYN-P01", "SYN-P03"):
            for r in A.dashboard(pid)["rows"]:
                if r["id"].startswith("SYN-"):
                    if r.get("deadline_display"):
                        self.assertTrue(r["deadline_display"].startswith("TEST RULE"))
                        self.assertNotIn("TEST RULE date (made up): TEST RULE", r["deadline_display"])
                else:
                    self.assertEqual(r["deadline_display"], A.NO_DATE)
                    self.assertNotIn("within 30 days", r["deadline_display"])   # B's draft deadline reading is never shown

    def test_105_replay_checks_c_contract(self):
        orig = P.C_CONTRACT
        try:
            P.C_CONTRACT = "9.9"
            with self.assertRaises(A.Incompatible):
                A.change_replay()
        finally:
            P.C_CONTRACT = orig

    def test_106_tampered_cache_is_rebuilt_not_trusted(self):
        root = P.export(P.B_COMMIT, "ws_b")
        f = root / "compliance_agent" / "obligations" / "engine.py"
        original = f.read_bytes()
        try:
            f.write_bytes(original + b"\n# tampered\n")
            P._CHECKED.clear()
            if P.vendored():          # export: a changed vendored file is refused, never repaired or trusted
                with self.assertRaises(P.Unavailable):
                    P.export(P.B_COMMIT, "ws_b")
            else:
                root2 = P.export(P.B_COMMIT, "ws_b")
                self.assertEqual((root2 / "compliance_agent" / "obligations" / "engine.py").read_bytes(), original)
        finally:
            if f.exists() and f.read_bytes() != original:
                f.write_bytes(original)
            P._CHECKED.clear()

    def test_107_in_tree_b_and_c_match_the_pins_on_the_integration_branch(self):
        import subprocess
        paths = {P.B_COMMIT: ["compliance_agent/obligations", "docs/360/demo/wsa", "fixtures/obligations"],
                 P.C_COMMIT: ["compliance_agent/rag_c", "knowledge_base/CL_360_obligation_sources.json", "knowledge_base/CL_360_source_candidates.json"]}
        gate_only = lambda p: {str(x.relative_to(ROOT)) for x in (ROOT / p).rglob("*.py")} <= set(P.C_GATE_FILES)
        present = [p for ps in paths.values() for p in ps if (ROOT / p).exists() and not ((ROOT / p).is_dir() and gate_only(p))]
        if not present:
            self.skipTest("WS B / WS C code not merged here (Workstream A branch)")
        gate = set(P.C_GATE_FILES)      # CR-29: these come from the gate pin, not from C_COMMIT
        if P.vendored():          # export: every in-tree file equals its checked vendored copy
            for (commit, ws) in ((P.B_COMMIT, "ws_b"), (P.C_COMMIT, "ws_c")):
                base = P.export(commit, ws)
                for prefix in paths[commit]:
                    for f in sorted((ROOT / prefix).rglob("*") if (ROOT / prefix).is_dir() else [ROOT / prefix]):
                        rel = f.relative_to(ROOT)
                        if f.is_file() and "__pycache__" not in f.parts and str(rel) not in gate:
                            self.assertEqual(f.read_bytes(), (base / rel).read_bytes(), f"{rel} differs from vendored {commit}")
            gbase = P.export(P.C_GATE_COMMIT, "ws_c")
            for rel in gate:
                self.assertEqual((ROOT / rel).read_bytes(), (gbase / rel).read_bytes(), f"{rel} differs from vendored {P.C_GATE_COMMIT}")
            return
        for commit, ps in paths.items():
            excl = [f":(exclude){g}" for g in gate] if commit == P.C_COMMIT else []
            r = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", commit, "HEAD", "--", *ps, *excl])
            self.assertEqual(r.returncode, 0, f"in-tree files differ from pinned {commit}: {ps}")
        r = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", P.C_GATE_COMMIT, "HEAD", "--", *P.C_GATE_FILES])
        self.assertEqual(r.returncode, 0, f"gate files differ from pinned {P.C_GATE_COMMIT}")

    def test_108_who_does_what_has_no_time_or_fee_claims(self):
        text = json.dumps(A.content()["who_does_what"]).lower()
        for bad in ("free service", "25 minutes", "minutes", "often, for simple cases", "mohre-approved"):
            self.assertNotIn(bad, text)
        self.assertNotIn("draft profit and loss", json.dumps(A.finance()).lower())


    # --- demo source snapshot (founder approval 17 Oct 2026) -------------------------------------------------------------
    def test_109_snapshot_text_shown_and_distinguished_from_legal_dates(self):
        self.assertEqual(P.SNAPSHOT_TEXT, "Demo source snapshot: 17 October 2026.")
        d = A.dashboard("SYN-AMAL-B")
        self.assertEqual(d["snapshot"], P.SNAPSHOT_TEXT)
        self.assertIn("not the date any law was published or amended", d["snapshot_note"])
        page = (ROOT / "compliance_agent" / "ui360.html").read_text(encoding="utf-8")
        self.assertIn("Demo source snapshot: 17 October 2026.", page)
        self.assertIn("copied for this demo on", page)
        self.assertNotIn("· retrieved ${", page)

    def test_110_snapshot_lock_matches_pins_and_committed_files(self):
        import subprocess
        lock = json.loads(P.SNAPSHOT_LOCK.read_text(encoding="utf-8"))
        self.assertEqual((lock["b_commit"], lock["c_commit"], lock["c_contract"], lock["b_validity_pin"], lock["snapshot_date"]),
                         (P.B_COMMIT, P.C_COMMIT, P.C_CONTRACT, P.B_VALIDITY_PIN, P.DEMO_AS_OF))
        self.assertEqual(lock["b_fixture_sha256"], P.B_FIXTURE_SHA256)
        show = lambda ref, path: _pinned_bytes(ref, "ws_c", path)
        self.assertEqual(hashlib.sha256(show(P.C_COMMIT, "docs/CL_evidence/ws_c/360/mvp/CL_sbr_amendment_impact_2026-10-17.json")).hexdigest(),
                         lock["c_sbr_evidence_sha256"])
        self.assertEqual(hashlib.sha256(show(P.C_COMMIT, "knowledge_base/CL_360_obligation_sources.json")).hexdigest(), lock["c_obligation_sources_sha256"])
        self.assertEqual(hashlib.sha256(show(P.C_COMMIT, "knowledge_base/CL_360_source_candidates.json")).hexdigest(), lock["c_source_candidates_sha256"])

    def _with_suppressed(self, entries):
        data = json.loads(A.CONTENT.read_text(encoding="utf-8"))
        data["suppressed_claims"] = entries
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(data, tmp); tmp.close()
        orig = A.CONTENT
        A.CONTENT = Path(tmp.name)
        return orig, Path(tmp.name)

    def test_111_suppressed_claims_are_withheld_not_silently_changed(self):
        self.assertEqual(A.suppressed(), {})                                      # nothing suppressed in the shipped demo
        e = {"since": "2026-11-01", "reason": "newer official text under review", "change_report_entry": "PSC-001"}
        orig, tmp = self._with_suppressed([dict(e, claim_id="C360-11"), dict(e, claim_id="step:7"), dict(e, claim_id="Q13")])
        try:
            rows = {r["id"]: r for r in A.dashboard("SYN-AMAL-B")["rows"]}
            r = rows["C360-11"]
            self.assertEqual(r["owner_text"], A.WITHHELD_TEXT)
            self.assertEqual(r["state_chip"], "Blocked: legal validation")         # legal status untouched
            self.assertNotIn("demo_scenario", r); self.assertEqual(r["suppressed"]["change_report_entry"], "PSC-001")
            self.assertNotIn("C360-11", [x["id"] for x in A.ct_journey("SYN-AMAL-B")["rows"]])
            with self.assertRaises(KeyError):
                A.change_replay()
        finally:
            A.CONTENT = orig; tmp.unlink()

    def test_112_malformed_suppression_entry_fails_closed(self):
        orig, tmp = self._with_suppressed([{"claim_id": "C360-11"}])
        try:
            with self.assertRaises(A.Incompatible):
                A.dashboard("SYN-AMAL-B")
        finally:
            A.CONTENT = orig; tmp.unlink()


    def test_113_page_scripts_parse(self):
        import shutil, subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        for page in ("ui360.html", "ui.html"):
            html = (ROOT / "compliance_agent" / page).read_text(encoding="utf-8")
            js = html[html.index("<script>") + 8: html.rindex("</script>")]
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
                f.write(js)
            try:
                r = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, f"{page}: {r.stderr[:300]}")
            finally:
                Path(f.name).unlink()


    # --- championship quality gate (17 Oct 2026) ------------------------------------------------------------------------
    def test_114_no_unapproved_external_calls(self):
        import ast, re as _re
        page = (ROOT / "compliance_agent" / "ui360.html").read_text(encoding="utf-8")
        self.assertIsNone(_re.search(r'<(script|link|img|iframe)[^>]+(src|href)="https?://', page))    # nothing loaded from outside
        self.assertNotRegex(page, r"fetch\(\s*[\"'`]https?://")                                       # the page only calls its own server
        for f in (ROOT / "compliance_agent" / "mvp360").glob("*.py"):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            mods = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)} | \
                   {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
            self.assertFalse(mods & {"urllib", "http", "requests", "socket", "anthropic", "httpx"}, f"{f.name} imports {mods}")

    def test_115_error_scenarios_all_pass(self):
        sys.path.insert(0, str(ROOT / "experiments" / "ws_a"))
        import CL_error_scenarios as ES
        rows = ES.scenarios()
        self.assertEqual([r["id"] for r in rows if r["result"] == "FAIL"], [])
        skipped = [r["id"] for r in rows if r["result"] == "SKIPPED"]
        # only the two recorded-answer scenarios may be skipped, and only where no recorded answers exist (the export)
        self.assertEqual(skipped, [] if ES.Asker(ES.AUTH, ES.LEDGER).recorded else ["E10", "E11"])
        self.assertGreaterEqual(len(rows), 13)


    def test_116_reviewer_only_or_potential_reports_are_refused(self):
        # WS B limitation L9: owner_row() does not refuse a reviewer-only ("potential") report, so A must (fail closed).
        from unittest import mock
        base = {"profile_id": "SYN-A360-OWNER", "as_of": P.DEMO_AS_OF, "obligations": [], "owner_rows": [],
                "profile_gaps": {}, "_wording_violations": [], "summary": {}}
        for audience, policy in (("reviewer_only", "potential"), ("owner", "potential"), ("reviewer_only", "blocked")):
            with self.subTest(audience=audience, policy=policy):
                fake = dict(base, audience=audience, policy=policy)
                with mock.patch.object(P, "run_b", return_value=fake):
                    with self.assertRaises(A.Incompatible):
                        A.dashboard(fields={"emirate": "AE-DU"})
        # the fixture path: a fixture whose checksum is consistent but whose audience is not the owner view is refused
        raw = json.loads(P.b_file(P.B_FIXTURE))
        raw["audience"] = "reviewer preview"
        body = json.dumps(raw).encode()
        digest = hashlib.sha256(body).hexdigest()
        real = P.b_file
        fake_file = lambda path: body if path == P.B_FIXTURE else (f"{digest}  x\n".encode() if path == P.B_FIXTURE + ".sha256" else real(path))
        with mock.patch.object(P, "b_file", side_effect=fake_file), mock.patch.object(P, "B_FIXTURE_SHA256", digest), \
                mock.patch.object(P, "B_FIXTURE_SHA256_PUBLIC", digest):
            with self.assertRaises(A.Incompatible) as cm:
                A.fixture()
            self.assertIn("audience", str(cm.exception))

    # --- history-free submission export (founder approval 17 Oct 2026: local export preparation only) -------------------
    def test_117_public_fixture_differs_from_the_committed_one_only_in_local_paths(self):
        raw = _pinned_bytes(P.B_COMMIT, "ws_b", P.B_FIXTURE)
        if P.vendored():
            self.assertEqual(hashlib.sha256(raw).hexdigest(), P.B_FIXTURE_SHA256_PUBLIC)
            man = json.loads(P.VENDOR_MANIFEST.read_text(encoding="utf-8"))["trees"][f"ws_b_{P.B_COMMIT}"]["files"][P.B_FIXTURE]
            self.assertEqual(man["committed_sha256"], P.B_FIXTURE_SHA256)
            return
        self.assertEqual(hashlib.sha256(raw).hexdigest(), P.B_FIXTURE_SHA256)
        pub = P.scrub_fixture(raw)
        self.assertEqual(hashlib.sha256(pub).hexdigest(), P.B_FIXTURE_SHA256_PUBLIC)    # = WS B's own scrubbed export

        def diff(a, b, path=""):
            if isinstance(a, dict):
                return [d for k in a for d in diff(a[k], b[k], f"{path}.{k}")]
            if isinstance(a, list):
                return [d for i, (x, y) in enumerate(zip(a, b)) for d in diff(x, y, f"{path}[{i}]")]
            return [] if a == b else [path]
        changed = diff(json.loads(raw), json.loads(pub))
        self.assertEqual(len(changed), 8)
        self.assertTrue(all(c.endswith(".origin") for c in changed), changed)
        self.assertNotIn(b"/Users/", pub)

    def test_118_owner_rows_do_not_depend_on_the_protected_database(self):
        # The export has no database, so B's VAT source-validity check fails closed there. The owner view must be the same.
        prof = {"profile_id": "SYN-A360-OWNER", "synthetic": True, "fields": {"emirate": "AE-DU", "legal_form": "llc",
                "activities": ["design"], "licence_expiry_date": "2027-01-01", "vat_registration_status": "not_sure"}}
        out = P.run_b(prof)
        self.assertTrue(out["owner_rows"])
        if P.vendored():
            self.assertFalse(out["source_validity"]["available"])
            self.assertIn("no copy of the protected database", out["source_validity"]["error"])
            return
        orig = P.vendored
        try:
            P.vendored = lambda: True                       # same B engine, validity forced to "no database"
            P._CACHE.clear()
            root = P._export(P.B_COMMIT, "ws_b")
            forced = P._run(P._B_RUNNER, root, {"profile": prof, "as_of": P.DEMO_AS_OF, "c_repo": str(ROOT), "no_db": P.NO_DB_VALIDITY})
        finally:
            P.vendored = orig
            P._CACHE.clear()
        self.assertTrue(out["source_validity"]["available"])
        self.assertFalse(forced["source_validity"]["available"])
        self.assertEqual(forced["owner_rows"], out["owner_rows"])
        for pid in [p["id"] for p in A.personas()]:
            self.assertTrue(A.dashboard(pid)["rows"])

    def test_119_recorded_answers_file_replays_the_same_screen_as_the_ledger(self):
        from compliance_agent import ask
        led = ROOT / "data" / "CL_llm_experiment.sqlite3"
        if not led.exists():
            self.skipTest("experiment ledger not present (submission export): nothing to compare the file with")
        sys.path.insert(0, str(ROOT / "experiments" / "ws_a"))
        import CL_export_recorded_answers as R
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "rec.json"
            f.write_text(json.dumps(R.build(AUTH)), encoding="utf-8")
            live = ask.Asker(AUTH)
            replay = ask.Asker(Path(d) / "no.db", Path(d) / "no_ledger.db", f)
            self.assertEqual(replay.examples(), live.examples())
            for qid in R.demo_ids():
                self.assertEqual(replay.ask(qid=qid), live.ask(qid=qid), qid)
            none = ask.Asker(Path(d) / "no.db", Path(d) / "no_ledger.db", Path(d) / "absent.json")
            self.assertEqual((none.recorded, none.examples()), ({}, []))
            self.assertEqual(none.ask(qid="Q35")["mode"], "no_recording")      # never an invented answer

    def test_120_vendored_mode_refuses_missing_extra_or_changed_files(self):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            tree = Path(d) / "vendor360"
            src = P.export(P.C_COMMIT, "ws_c")
            dest = tree / f"ws_c_{P.C_COMMIT}"
            files = {}
            for f in sorted(src.rglob("*")):
                if f.is_file() and "__pycache__" not in f.parts:
                    rel = str(f.relative_to(src))
                    (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(f, dest / rel)
                    files[rel] = {"sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
            (tree / "CL_VENDOR_MANIFEST.json").write_text(json.dumps({"trees": {f"ws_c_{P.C_COMMIT}": {"files": files}}}))
            saved = (P.VENDOR_TREE, P.VENDOR_MANIFEST, set(P._CHECKED))
            try:
                P.VENDOR_TREE, P.VENDOR_MANIFEST = tree, tree / "CL_VENDOR_MANIFEST.json"
                P._CHECKED.clear()
                self.assertEqual(P.export(P.C_COMMIT, "ws_c"), dest)
                for attack in ("change", "extra", "missing"):
                    target = dest / "knowledge_base" / "CL_360_obligation_sources.json"
                    keep = target.read_bytes()
                    if attack == "change":
                        target.write_bytes(keep + b" ")
                    elif attack == "extra":
                        (dest / "compliance_agent" / "planted.py").write_text("x = 1\n")
                    else:
                        target.unlink()
                    P._CHECKED.clear()
                    with self.assertRaises(P.Unavailable, msg=attack):
                        P.export(P.C_COMMIT, "ws_c")
                    target.write_bytes(keep)
                    (dest / "compliance_agent" / "planted.py").unlink(missing_ok=True)
                with self.assertRaises(P.Unavailable):
                    P.export(P.B_COMMIT, "ws_b")              # no entry in this manifest
            finally:
                P.VENDOR_TREE, P.VENDOR_MANIFEST = saved[0], saved[1]
                P._CHECKED.clear(); P._CHECKED.update(saved[2])

    def test_121_vat_step_says_answers_are_absent_instead_of_inventing_them(self):
        from http.server import ThreadingHTTPServer
        from compliance_agent.clock import FixedClock
        from compliance_agent.web import App, make_handler
        with tempfile.TemporaryDirectory() as d:
            app = App(Path(d) / "w.sqlite3", FixedClock("2026-10-17T10:00:00"), Path(d) / "none.sqlite3")
            app._asker = __import__("compliance_agent.ask", fromlist=["x"]).Asker(Path(d) / "w.sqlite3", Path(d) / "none.sqlite3", Path(d) / "absent.json")
            srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            try:
                c = json.loads(urllib.request.urlopen(base + "/api/360/content").read())
                self.assertEqual((c["vat_questions"], c["vat_recorded"]), ([], False))
                r = json.loads(urllib.request.urlopen(base + "/api/ask?id=Q35").read())
                self.assertEqual(r["mode"], "no_recording")
                self.assertTrue(r["professional"])
            finally:
                srv.shutdown(); app.engine.s.close()
        page = (ROOT / "compliance_agent" / "ui360.html").read_text(encoding="utf-8")
        self.assertIn("The recorded VAT answers are not included in this copy of HerBiz.", page)
        self.assertIn("C.vat_recorded === false", page)

    def test_122_team_tools_page_works_without_the_internal_project_record(self):
        from http.server import ThreadingHTTPServer
        from unittest import mock
        from compliance_agent import web
        from compliance_agent.clock import FixedClock
        with tempfile.TemporaryDirectory() as d:
            app = web.App(Path(d) / "w.sqlite3", FixedClock("2026-10-17T10:00:00"), Path(d) / "none.sqlite3")
            srv = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(app))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                with mock.patch.object(web, "HERE", Path(d) / "compliance_agent"):      # no project/ folder there
                    proj = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/api/project").read())
                self.assertEqual((proj["tasks"], proj["decisions"], proj["evidence_files"]), ([], [], []))
                self.assertIn("not part of this copy", proj["task_status_scope"])
            finally:
                srv.shutdown(); app.engine.s.close()

    def test_134_kb_manifest_matches_the_pins_and_has_no_official_text(self):
        lock = json.loads(P.SNAPSHOT_LOCK.read_text(encoding="utf-8"))
        self.assertEqual(lock["c_kb_manifest_commit"], P.C_KB_MANIFEST_COMMIT)
        for f in P.C_KB_MANIFEST_FILES:
            self.assertEqual(hashlib.sha256((ROOT / f).read_bytes()).hexdigest(), lock["c_kb_manifest_sha256"][f], f)
        m = json.loads((ROOT / "kb_export" / "CL_HERBIZ_KB_MANIFEST.json").read_text(encoding="utf-8"))
        self.assertIn(P.C_COMMIT, m["_meta"]["built_from"]); self.assertIn(P.C_GATE_COMMIT, m["_meta"]["built_from"])
        versions = m["domain_a_business_compliance"]["collected_versions"]
        self.assertEqual(sum(v["passage_count"] for v in versions), 371)
        self.assertFalse(any(v["approved"] for v in versions))
        text_keys = {"text", "passage", "quote", "excerpt", "full_text"}
        def keys(x):
            if isinstance(x, dict):
                for k, val in x.items():
                    yield k; yield from keys(val)
            elif isinstance(x, list):
                for val in x: yield from keys(val)
        self.assertFalse(text_keys & set(keys(m)))


if __name__ == "__main__":
    unittest.main()
