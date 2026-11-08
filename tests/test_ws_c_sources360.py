"""360 source-citation and uncertainty interface (championship MVP), offline. Tests 178-187."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent.rag_c import interface as I, sources360 as S  # noqa: E402


def _copy(mutate_src=None, mutate_obl=None):
    d = Path(tempfile.mkdtemp())
    src = json.loads(S.SOURCES.read_text(encoding="utf-8")); obl = json.loads(S.OBLIGATIONS.read_text(encoding="utf-8"))
    if mutate_src: mutate_src(src)
    if mutate_obl: mutate_obl(obl)
    (d / "s.json").write_text(json.dumps(src), encoding="utf-8"); (d / "o.json").write_text(json.dumps(obl), encoding="utf-8")
    return d / "s.json", d / "o.json"


class Sources360(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = S.load()

    def test_178_committed_files_validate_and_nothing_is_approved(self):
        self.assertTrue(all(s["approved"] is False and s["activated"] is False for s in self.data["sources"].values()))
        self.assertTrue(all(o["substantive_rule_allowed"] is False for o in self.data["obligations"].values()))
        self.assertEqual(I.CONTRACT_VERSION, "1.1")                      # B's VAT contract untouched

    def test_179_loader_refuses_approved_activated_stored_or_unknown_level(self):
        for mut in (lambda s: s["sources"][0].update(approved=True), lambda s: s["sources"][0].update(activated=True),
                    lambda s: s["sources"][0].update(content_stored=True), lambda s: s["sources"][0].update(evidence_level="certain")):
            sp, op = _copy(mutate_src=mut)
            with self.assertRaises(S.Invalid):
                S.load(sp, op)

    def test_180_corporate_tax_must_stay_synthetic_with_d3ct(self):
        def real_rule(o):
            next(x for x in o["obligations"] if x["obligation_id"] == "CT-SBR").update(mode="rule", substantive_rule_allowed=True)
        sp, op = _copy(mutate_obl=real_rule)
        with self.assertRaises(S.Invalid) as e:
            S.load(sp, op)
        self.assertIn("synthetic scenario only", str(e.exception))

    def test_181_unknown_source_or_gap_is_refused(self):
        for mut in (lambda o: o["obligations"][3]["sources"].append("NOPE"), lambda o: o["obligations"][3]["gaps"].append("G99")):
            sp, op = _copy(mutate_obl=mut)
            with self.assertRaises(S.Invalid):
                S.load(sp, op)

    def test_182_sbr_label_cites_md73_shows_gap_and_is_never_release_approved(self):
        lab = S.obligation_label(self.data, "CT-SBR", as_of="2026-10-18", profile_synthetic=True)
        self.assertIn("CT-MD131-2026", [c["source_id"] for c in lab["citations"]])     # the 2026 amendment (SBR to 2029)
        self.assertNotIn("CT-G1", lab["open_gaps"])                                      # resolved by MD 131/2026
        self.assertIn("CT-MD73-2023", [c["source_id"] for c in lab["citations"]])
        self.assertFalse(lab["release_approved"]); self.assertFalse(lab["substantive_rule_allowed"])
        self.assertTrue(lab["user_wording"].startswith(S.DEMO_PREFIX + ". " + S.DISCLAIMER))
        self.assertIn("Open questions: CT law text not collected", lab["user_wording"])
        self.assertNotIn("CT-G2", lab["user_wording"])                                   # plain text, not gap ids
        self.assertIn("demonstration scenario", lab["user_wording"])
        self.assertEqual(lab["reviewer_needed"], "D3-CT")

    def test_183_uncertainty_rules(self):
        lab = lambda d, o: S.obligation_label(d, o, as_of="2026-10-18", profile_synthetic=True)["uncertainty"]
        self.assertEqual(lab(self.data, "CT-SBR"), "high")                 # CT-G2 (CT law text not collected) is open, high
        self.assertEqual(lab(self.data, "EINV-READINESS"), "high")
        self.assertEqual(lab(self.data, "VAT-MANDATORY-REG"), "high")      # G3 (outdated DL) from the VAT register, high impact
        self.assertEqual(lab(self.data, "ESR-HISTORICAL"), "medium")       # snippet evidence, no gap
        self.assertEqual(S.obligation_label(self.data, "NOT-AN-OBLIGATION")["uncertainty"], "high")
        # once the CT law text is collected (CT-G2 resolved), SBR rests on observed decisions and no open gap -> medium (never "low" unreviewed)
        def resolve_g2(s):
            next(g for g in s["gaps"] if g["id"] == "CT-G2")["state"] = "resolved"
        sp, op = _copy(mutate_src=resolve_g2)
        self.assertEqual(lab(S.load(sp, op), "CT-SBR"), "medium")

    def test_184_sources_go_stale_after_30_days(self):
        fresh = S.obligation_label(self.data, "CT-SBR", as_of="2026-10-18", profile_synthetic=True)
        old = S.obligation_label(self.data, "CT-SBR", as_of="2026-12-31", profile_synthetic=True)
        self.assertFalse(any(c["stale"] for c in fresh["citations"] if c["retrieved_at"]))
        self.assertTrue(all(c["stale"] for c in old["citations"]))
        self.assertIn("re-checked", old["user_wording"])

    def test_185_esr_is_labelled_historical(self):
        self.assertIn("past periods only", S.obligation_label(self.data, "ESR-HISTORICAL", as_of="2026-10-18")["user_wording"])

    def test_186_impact_maps_alerts_to_obligations_and_reports_unmapped(self):
        sbr = self.data["sources"]["CT-SBR-TOPIC"]["official_url"]
        alerts = [{"kind": "changed_substantive", "url": sbr, "at": "2026-10-20T06:00:00+04:00", "detail": "SYNTHETIC"},
                  {"kind": "changed_substantive_in_scope", "url": "https://x.test", "source_id": "FTA-VAT-ER", "detail": "ER Art. 14"},
                  {"kind": "new_document_on_listing", "url": "https://tax.gov.ae/unknown.pdf", "detail": "new"},
                  {"kind": "changed_substantive", "url": sbr, "reviewed": True}]
        r = S.impact(self.data, alerts)
        self.assertEqual(sorted(r["affected_obligations"]["CT-SBR"][0].keys()), ["at", "detail", "kind", "source_id"])
        self.assertIn("VAT-DEREG", r["affected_obligations"])
        self.assertEqual(len(r["unmapped_alerts"]), 1)
        self.assertEqual(len(r["affected_obligations"]["CT-SBR"]), 1)      # the reviewed alert is ignored
        self.assertEqual(r["activation"], "not activated"); self.assertTrue(r["human_review_required"])

    def test_188_corporate_tax_is_refused_for_a_real_profile(self):
        for oid in ("CT-SBR", "CT-REG-NATURAL", "ACC-AUDITED-FS"):            # ACC-AUDITED-FS cites MD 84/2025 (a CT decision)
            for flag in (None, False):
                lab = S.obligation_label(self.data, oid, as_of="2026-10-18", profile_synthetic=flag)
                self.assertFalse(lab["shown"]); self.assertEqual(lab["refused"], "corporate_tax_real_profile")
                self.assertNotIn("citations", lab)
        self.assertTrue(S.obligation_label(self.data, "VAT-MANDATORY-REG", as_of="2026-10-18")["shown"])

    def test_189_ct_sources_need_d3ct_whatever_the_domain_label(self):
        def relabel(o):
            next(x for x in o["obligations"] if x["obligation_id"] == "ACC-AUDITED-FS")["reviewer"] = "D3-ACC"
        sp, op = _copy(mutate_obl=relabel)
        with self.assertRaises(S.Invalid) as e:
            S.load(sp, op)
        self.assertIn("cites a corporate-tax source", str(e.exception))

    def test_190_no_unreviewed_source_is_ever_low(self):
        for oid in self.data["obligations"]:
            self.assertNotEqual(S.obligation_label(self.data, oid, as_of="2026-10-18", profile_synthetic=True)["uncertainty"], "low")

    def test_191_cto_bypasses_are_refused(self):
        muts_src = [lambda s: s["sources"][0].update(evidence_level="secondary"),
                    lambda s: s["sources"][0].update(domain="corporate-tax"),
                    lambda s: s["sources"][0].update(retrieved_at="17/10/2026"),
                    lambda s: s["gaps"][0].update(state="largely resolved")]
        muts_obl = [lambda o: o["obligations"].append({"obligation_id": "CT-NEW", "domain": "corporate-tax", "mode": "rule",
                                                        "reviewer": None, "sources": [], "gaps": [], "substantive_rule_allowed": False}),
                    lambda o: o["obligations"][0]["vat_register_sources"].append("NOPE")]
        for m in muts_src:
            with self.assertRaises(S.Invalid):
                S.load(*_copy(mutate_src=m))
        for m in muts_obl:
            with self.assertRaises(S.Invalid):
                S.load(*_copy(mutate_obl=m))

    def test_192_best_evidence_rule_and_vat_start_level(self):
        def mixed(o):
            o["obligations"].append({"obligation_id": "LIC-MIXED", "title": "t", "domain": "licensing", "mode": "test", "reviewer": "D3-JUR",
                                     "sources": ["LIC-DDA-FZ", "EINV-MOF-PAGE"], "gaps": [], "substantive_rule_allowed": False})
            o["obligations"].append({"obligation_id": "VAT-NOGAP", "title": "t", "domain": "vat", "mode": "test", "reviewer": "D3",
                                     "sources": [], "vat_register_sources": ["FTA-VAT-ER"], "gaps": [], "substantive_rule_allowed": False})
        d = S.load(*_copy(mutate_obl=mixed))
        self.assertEqual(S.obligation_label(d, "LIC-MIXED", as_of="2026-10-18")["uncertainty"], "medium")   # best = snippet
        self.assertEqual(S.obligation_label(d, "VAT-NOGAP", as_of="2026-10-18")["uncertainty"], "medium")

    def test_193_mutating_loaded_data_cannot_upgrade_a_ct_item(self):
        d = S.load()
        d["obligations"]["CT-SBR"]["mode"] = "rule"
        lab = S.obligation_label(d, "CT-SBR", as_of="2026-10-18", profile_synthetic=True)
        self.assertEqual(lab["mode"], "synthetic scenario only"); self.assertIn("demonstration scenario", lab["user_wording"])
        self.assertEqual(S.load()["obligations"]["CT-SBR"]["mode"], "synthetic scenario only")             # fresh load unaffected

    def test_194_only_reviewed_true_hides_an_alert(self):
        url = self.data["sources"]["CT-SBR-TOPIC"]["official_url"]
        r = S.impact(self.data, [{"kind": "changed_substantive", "url": url, "reviewed": "no"}])
        self.assertIn("CT-SBR", r["affected_obligations"])

    def test_195_output_fields_are_frozen_for_the_ui(self):
        lab = S.obligation_label(self.data, "CT-SBR", as_of="2026-10-18", profile_synthetic=True)
        self.assertEqual(sorted(lab), sorted(["obligation_id", "known", "shown", "title", "domain", "mode", "reviewer_needed",
                                              "substantive_rule_allowed", "release_approved", "citations", "vat_register_sources",
                                              "open_gaps", "uncertainty", "user_wording", "contract"]))
        self.assertEqual(sorted(lab["citations"][0]), sorted(["source_id", "title", "authority", "url", "evidence_level",
                                                             "retrieved_at", "review_status", "stale", "citation_chip"]))
        self.assertEqual(lab["contract"], "0.2")

    def test_196_wording_is_short_sentences_and_chips_never_claim_review(self):
        for oid in self.data["obligations"]:
            for flag in (True, None):
                lab = S.obligation_label(self.data, oid, as_of="2026-10-18", profile_synthetic=flag)
                w = lab["user_wording"]
                self.assertNotIn(": ", w.split("Open questions")[0])            # no run-on "...: a; b; c" sentence
                self.assertTrue(w.endswith("."))
                for c in lab.get("citations", []):
                    self.assertIn(c["citation_chip"], S.CITATION_CHIP.values())
                    self.assertRegex(c["citation_chip"], r"not (opened or )?reviewed|not located")
        self.assertEqual(set(S.CITATION_CHIP), set(S.ALLOWED_EVIDENCE))      # every allowed level has a chip

    def test_187_no_prices_or_fees_in_the_360_files(self):
        import re
        text = S.SOURCES.read_text(encoding="utf-8") + S.OBLIGATIONS.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\bfee(s)? (of|is|are)\b|\bcosts? AED\b|\bprice\b", text, re.I))


if __name__ == "__main__":
    unittest.main()
