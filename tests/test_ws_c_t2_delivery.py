"""WS C Task 2 mandatory delivery (G3): C-1 link status, C-2 validity 1.2 export, C-3 manifest v0.2.1, C-4 scenario fixtures.

Read-only checks on committed outputs. No network: the link check itself is a script run (experiments/ws_c/CL_t2_link_check.py)."""
from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "knowledge_base"
LINKS = json.loads((KB / "t2" / "CL_link_status.json").read_text(encoding="utf-8"))
EXPORT = json.loads((KB / "t2" / "CL_source_validity_1.2.json").read_text(encoding="utf-8"))
MANIFEST_TEXT = (ROOT / "kb_export" / "CL_HERBIZ_KB_MANIFEST.json").read_text(encoding="utf-8")
MANIFEST = json.loads(MANIFEST_TEXT)
SCHEMA = json.loads((ROOT / "contracts" / "source_validity_1.2.schema.json").read_text(encoding="utf-8"))
_spec = importlib.util.spec_from_file_location("herbiz_validate", ROOT / "contracts" / "validate.py")
V = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(V)
BY_KEY = {p["key"]: p for p in EXPORT["payloads"]}
PORTAL_1227 = "https://uaelegislation.gov.ae/en/legislations/1227"


class LinkStatus(unittest.TestCase):
    def test_221_every_row_uses_the_contract_vocabulary_and_no_synthetic_hosts(self):
        for r in LINKS["urls"]:
            self.assertIn(r["link_status"], {"ok", "blocked_to_automation", "dead", "unchecked"})
            self.assertNotIn("fixture.invalid", r["url"])
            if r["link_status"] == "dead":
                self.assertTrue(r.get("reason"), r["url"])

    def test_222_researched_dead_links_carry_replacements(self):
        rows = {r["url"]: r for r in LINKS["urls"]}
        for u in ("https://mof.gov.ae/wp-content/uploads/2025/07/Federal-Decree-Law-No.-28-of-2022.pdf",
                  "https://elaws.moj.gov.ae/UAE-MOJ_LC-En/00_TAXES/UAE-LC-En_2017-08-23_00008_Markait.html?val=EL1"):
            self.assertEqual(rows[u]["link_status"], "dead")
            self.assertTrue(rows[u]["replacement_url"].startswith("https://uaelegislation.gov.ae/"))


class Validity12(unittest.TestCase):
    def test_223_every_payload_validates_and_keys_are_unique(self):
        keys = [p["key"] for p in EXPORT["payloads"]]
        self.assertEqual(len(keys), len(set(keys)))
        for p in EXPORT["payloads"]:
            self.assertEqual(V.errors(SCHEMA, p), [], p["key"])
            self.assertEqual(p["key"], f"{p['source_id']}|{p['article']}")

    def test_224_safety_constants(self):
        for p in EXPORT["payloads"]:
            self.assertIs(p["release_approved"], False)
            self.assertIn(p["review_status"], {"discovered", "candidate"})       # ACK §2: never reviewed/approved in Task 2
            for c in p["conflicts"]:
                self.assertIs(c["precedence_known"], False)
                self.assertEqual(c["resolution"], "escalate")

    def test_225_g3_outdated_decree_law_articles_and_pending_portal_link(self):
        for art, status in (("48", "outdated"), ("74", "outdated"), ("54 (bis)", "outdated"), ("79 (bis)", "superseded"), ("*", "outdated")):
            p = BY_KEY[f"FTA-VAT-DL8|{art}"]
            self.assertEqual(p["status"], status)
            self.assertTrue(any("No. 16 of 2025" in a["instrument"] and a["effective_date"] == "2026-01-01" for a in p["amendments"]))
            self.assertEqual(p["current_official_url"], PORTAL_1227)
            self.assertEqual(p["current_official_url_status"]["content_check"], "pending_founder_verification")   # founder, 18 Oct

    def test_226_g1_conflict_both_values_no_resolution(self):
        p = BY_KEY["FTA-VAT-ER|14"]
        self.assertEqual(p["status"], "conflict")
        vals = {v["value"] for v in p["conflicts"][0]["values"]}
        self.assertEqual(vals, {"20 business days", "30 business days"})
        self.assertEqual(BY_KEY["FTA-VAT-DEREG-SERVICE|*"]["conflicts"][0]["conflict_id"], "G1")

    def test_227_fta_reuse_terms_are_link_only(self):
        for p in EXPORT["payloads"]:
            if p["source_id"].startswith("FTA-VAT"):
                self.assertEqual(p["reuse_terms"]["redistribution"], "link_only")


class Manifest021(unittest.TestCase):
    def test_228_version_lock_and_metadata_only(self):
        self.assertEqual(MANIFEST["_meta"]["version"], "0.2.1")
        for v in MANIFEST["domain_a_business_compliance"]["collected_versions"]:
            self.assertTrue(v["lock_verified"], v["version_id"])
            self.assertFalse(v["approved"])
            for loc in v["article_locators"]:
                self.assertEqual(set(loc), {"locator", "passage_sha256"})       # no passage text
        self.assertNotRegex(MANIFEST_TEXT, r"<LOCAL_PATH>")

    def test_229_dead_links_in_the_manifest_are_marked_with_replacements(self):
        dead = re.findall(r'"link_status": "dead"', MANIFEST_TEXT)
        self.assertGreaterEqual(len(dead), 1)
        self.assertEqual(MANIFEST_TEXT.count('"link_status": "dead"'), MANIFEST_TEXT.count('"link_dead_reason"'))
        self.assertTrue(all(p["release_approved"] is False for p in MANIFEST["domain_a_business_compliance"]["validity_1_2"]))


class ScenarioFixtures(unittest.TestCase):
    def test_230_sc2_sc3_source_side_fixtures_validate_and_match_the_export(self):
        for name, sid in (("CL_SC2_source_side.json", "SC-2"), ("CL_SC3_source_side.json", "SC-3")):
            fx = json.loads((ROOT / "fixtures" / "t2" / name).read_text(encoding="utf-8"))
            self.assertEqual(fx["scenario_id"], sid)
            self.assertTrue(fx["synthetic"])
            for p in fx["payloads"]:
                self.assertEqual(V.errors(SCHEMA, p), [])
                self.assertEqual(p, BY_KEY[p["key"]])                              # copied unchanged from the C-2 export
        sc3 = json.loads((ROOT / "fixtures" / "t2" / "CL_SC3_source_side.json").read_text(encoding="utf-8"))
        self.assertIn("pending_unverified_link", sc3["source_side_expectations"]["flags"])
        self.assertFalse(sc3["source_side_expectations"]["fetched_by_app"])


if __name__ == "__main__":
    unittest.main()
