"""Workstream C source intelligence: amendment map, claims and conflicts, validity export, citation integrity and
traceability, extraction validation. Read-only on copies; adversarial cases use temporary registers and databases."""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent.dbsafety import copy_readonly  # noqa: E402
from compliance_agent.rag_c import amendments as A, citations as T, claims as C, extraction_check as X, validity as V  # noqa: E402
from compliance_agent.rag_c.register import REGISTER, validate  # noqa: E402

DB = next((p for p in (ROOT / "data" / "CL_c_readonly_copy.sqlite3", ROOT / "data" / "CL_compliance.sqlite3") if p.exists()), None)
LEDGER = ROOT / "data" / "CL_llm_experiment.sqlite3"
md5 = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest()
REG = json.loads(REGISTER.read_text(encoding="utf-8"))


def tmp_register(d: Path, mutate) -> Path:
    r = copy.deepcopy(REG)
    mutate(r)
    p = d / "reg.json"
    p.write_text(json.dumps(r), encoding="utf-8")
    (d / "CL_collected_lock.json").write_text((ROOT / "knowledge_base" / "CL_collected_lock.json").read_text(encoding="utf-8"))
    return p


class AmendmentMap(unittest.TestCase):
    def test_117_decree_law_copy_is_outdated_by_dl_16_2025_and_er_v3_is_current(self):
        m = {v["version_id"]: v for v in A.amendment_map(as_of="2026-10-17")["versions"]}
        dl = m["FTA-VAT-DL8@v1"]
        self.assertEqual(dl["missing_in_force_instruments"], ["DL-16-2025"])
        self.assertEqual(sorted((a["article"], a["effect"]) for a in dl["affected_articles"]),
                         [("48", "amends"), ("54 (bis)", "adds"), ("74", "amends"), ("79 (bis)", "repeals")])
        self.assertIn("DL-16-2024", dl["includes"])
        self.assertFalse(m["FTA-VAT-ER@v3"]["outdated"])
        self.assertEqual(m["FTA-VAT-ER@v1"]["superseded_by_effective_date"], "FTA-VAT-ER@v3")

    def test_118_in_force_date_matters(self):
        m = {v["version_id"]: v for v in A.amendment_map(as_of="2025-12-31")["versions"]}
        self.assertFalse(m["FTA-VAT-DL8@v1"]["outdated"])          # DL 16/2025 not yet in force on 31 Dec 2025
        self.assertIn("CD-149-2026", A.amendment_map(as_of="2026-10-01")["versions"][1]["missing_in_force_instruments"])

    def test_119_instrument_name_variants_match(self):
        self.assertEqual(A._norm_instrument("Cabinet Decision No. (100) of 2024"), A._norm_instrument("Cabinet Decision No. 100 of 2024"))
        self.assertEqual(A._norm_instrument("Federal Decree-Law No. 16 of 2025"), A._norm_instrument("Decree-Law No. (16) of 2025"))
        self.assertNotEqual(A._norm_instrument("Cabinet Decision No. 100 of 2024"), A._norm_instrument("Cabinet Decision No. 100 of 2025"))


@unittest.skipUnless(DB is not None, "no database copy present")
class ClaimsAndConflicts(unittest.TestCase):
    def setUp(self):
        self.before = md5(DB)

    def tearDown(self):
        self.assertEqual(md5(DB), self.before)

    def test_120_the_deregistration_conflict_is_detected_and_thresholds_agree(self):
        r = C.check_claims(DB)
        self.assertEqual([c["topic"] for c in r["conflicts"]], ["vat.deregistration.mandatory_application_deadline"])
        self.assertEqual(r["conflicts"][0]["values"], [[20, "business_days"], [30, "business_days"]])
        self.assertEqual(r["integrity_failures"], [])

    def test_121_a_fabricated_quote_or_value_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            def bad(r):
                r["claims"].append({"claim_id": "X-FAKE", "topic": "vat.registration.mandatory_threshold", "value": 300000, "unit": "AED",
                                    "source_id": "FTA-VAT-ER", "version_id": "FTA-VAT-ER@v3", "article": "7",
                                    "quote": "AED 300,000", "in_knowledge_base": True, "evidence": "test"})
                r["claims"].append({"claim_id": "X-WRONGVAL", "topic": "vat.registration.voluntary_threshold", "value": 999, "unit": "AED",
                                    "source_id": "FTA-VAT-ER", "version_id": "FTA-VAT-ER@v3", "article": "8",
                                    "quote": "AED 187,500", "in_knowledge_base": True, "evidence": "test"})
            r = C.check_claims(DB, tmp_register(Path(d), bad))
            fails = {f["claim_id"]: f["integrity"] for f in r["integrity_failures"]}
            self.assertEqual(fails, {"X-FAKE": "QUOTE_NOT_FOUND", "X-WRONGVAL": "VALUE_NOT_IN_PASSAGE"})
            self.assertIn("vat.registration.mandatory_threshold", [c["topic"] for c in r["conflicts"]])

    def test_122_fact_inventory_finds_every_er_business_day_deadline_with_matching_words(self):
        facts = C.fact_inventory(DB, ["FTA-VAT-ER@v3"])
        art14 = [f for f in facts if f["locator"].startswith("Article 14,") and f["unit"] == "business_days"]
        self.assertIn(20, [f["value"] for f in art14])
        self.assertFalse([f for f in facts if f["digits_words_agree"] is False])


@unittest.skipUnless(DB is not None, "no database copy present")
class ValidityAndCitations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = V.build_validity(DB, as_of="2026-10-17")

    def test_123_validity_export_matches_workstream_b_keys(self):
        got = {i["id"]: sorted(i["provisions"]) for i in self.v["issues"]}
        self.assertEqual(got["FTA-VAT-DL8:outdated"], ["FTA-VAT-DL8|48", "FTA-VAT-DL8|74"])
        self.assertEqual(got["FTA-VAT-DL8:repealed"], ["FTA-VAT-DL8|79 (bis)"])
        self.assertEqual(got["FTA-VAT-DL8:missing"], ["FTA-VAT-DL8|54 (bis)"])
        self.assertEqual(got["conflict:vat.deregistration.mandatory_application_deadline"], ["FTA-VAT-ER|14"])
        self.assertEqual(self.v["approved_versions"], [])
        self.assertEqual(self.v["current_versions"]["FTA-VAT-ER"]["version_id"], "FTA-VAT-ER@v3")

    def test_124_committed_export_is_current(self):
        exp = json.loads(V.EXPORT.read_text(encoding="utf-8"))
        fresh = V.build_validity(DB, as_of=exp["_meta"]["generated_for_date"])
        strip = lambda x: {k: v for k, v in x.items() if k != "_meta"}
        self.assertEqual(strip(exp), strip(json.loads(json.dumps(fresh))))

    def test_125_citation_checks_flag_fakes_wrong_versions_and_validity_issues(self):
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            row = con.execute("SELECT passage_id, text FROM passages WHERE version_id='FTA-VAT-DL8@v1' AND locator LIKE 'Article 79 (bis)%'").fetchone()
            ok = T.check_citation(con, {"passage_id": row["passage_id"], "quote": " ".join(row["text"].split()[3:12])}, self.v)
            self.assertEqual(ok["result"], "quote_found")
            self.assertIn("FTA-VAT-DL8:repealed", ok["issues"])
            self.assertFalse(ok["certifiable"])
            fake = T.check_citation(con, {"passage_id": row["passage_id"], "quote": "the limitation period is ten years"}, self.v)
            self.assertEqual(fake["result"], "QUOTE_NOT_FOUND")
            old = con.execute("SELECT passage_id, text FROM passages WHERE version_id='FTA-VAT-ER@v1' AND locator LIKE 'Article 7,%'").fetchone()
            o = T.check_citation(con, {"passage_id": old["passage_id"], "quote": "AED 375,000"}, self.v)
            self.assertTrue(any(f.startswith("not_current_version") for f in o["flags"]))
            self.assertEqual(T.check_citation(con, {"passage_id": "NOPE#0001", "quote": "x"}, self.v)["result"], "PASSAGE_NOT_FOUND")
        finally:
            con.close()

    @unittest.skipUnless(LEDGER.exists(), "ledger copy not present")
    def test_126_every_recorded_answer_is_traced_and_none_is_certifiable(self):
        before = md5(LEDGER)
        t = T.trace_ledger(LEDGER, DB, self.v)
        self.assertEqual(md5(LEDGER), before)
        self.assertGreater(t["answers"], 200)
        self.assertEqual(sum(t["citation_results"].values()), t["citations"])
        self.assertEqual(t["certifiable_answers"], 0)                     # nothing is approved by a reviewer yet
        self.assertGreaterEqual(t["answers_by_issue"].get("FTA-VAT-DL8:repealed", 0), 1)


@unittest.skipUnless(DB is not None and (ROOT / "data" / "raw").exists(), "database copy or raw files not present")
class Extraction(unittest.TestCase):
    def test_127_structure_and_second_extractor_numbers_agree_on_every_pdf_article(self):
        for v in ("FTA-VAT-DL8@v1", "FTA-VAT-ER@v3"):
            with self.subTest(version=v):
                s = X.structure(DB, v)
                self.assertEqual(s["locator_grammar_violations"], [])
                a = X.second_extractor_agreement(DB, v)
                if a["status"] == "unavailable":
                    self.skipTest("pdftotext not installed")
                self.assertEqual(a["number_mismatches"], [])
                self.assertGreater(a["articles_compared"], 70)

    def test_128_a_corrupted_number_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            db = copy_readonly(DB, Path(d) / "corrupt.sqlite3")
            con = sqlite3.connect(db)
            con.execute("DROP TRIGGER IF EXISTS source_text_frozen")   # disposable copy only
            con.execute("UPDATE passages SET text = replace(text, '375,000', '357,000') WHERE version_id='FTA-VAT-ER@v3' AND locator LIKE 'Article 7,%'")
            con.commit(); con.close()
            a = X.second_extractor_agreement(db, "FTA-VAT-ER@v3")
            if a["status"] == "unavailable":
                self.skipTest("pdftotext not installed")
            self.assertIn("7", a["number_mismatches"])
        self.assertTrue(X._unexplained({"200"}, {"20"}, {"46"}))
        self.assertFalse(X._unexplained({"4615"}, {"15"}, {"46"}))

    def test_129_headings_give_titles_and_chapters_for_retrieval(self):
        h = {x["article"]: x for x in X.headings(DB, "FTA-VAT-ER@v3")["articles"]}
        self.assertEqual(h["14"]["title"], "Tax Deregistration")
        self.assertIn("Registration", h["14"]["chapter"])


class RegisterStillValid(unittest.TestCase):
    def test_130_register_with_instruments_and_claims_validates(self):
        out = validate(REGISTER, db=DB)
        self.assertEqual(out["errors"], [])
        self.assertTrue(REG["instruments"] and REG["claims"])


if __name__ == "__main__":
    unittest.main()
