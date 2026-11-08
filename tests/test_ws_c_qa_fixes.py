"""Fixes after the independent QA round of 17 Oct 2026: guard hardening (D1/D5/D8/D9), footnote-based amendment
evidence (C02/C08), partial-scope and future-text validity issues (C01/C03), instrument type matching (C05), unknown
effective dates (C06), certification needs the current version (C04), stale-export check, number-count cross-check (E2)."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock  # noqa: F401  (unittest.mock used below)
import unittest.mock  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent import dbsafety  # noqa: E402
from compliance_agent.rag_c import amendments as A, extraction_check as X, interface as I, validity as V  # noqa: E402
from compliance_agent.rag_c import dryrun as D  # noqa: E402

DB = next((p for p in (ROOT / "data" / "CL_c_readonly_copy.sqlite3",) if p.exists()), None)
MAIN = ROOT.parent / "CL_compliance_agent_app" / "data" / "CL_compliance.sqlite3"


class GuardHardening(unittest.TestCase):
    def test_141_protected_names_are_refused_from_any_checkout(self):
        self.assertTrue(dbsafety.is_authoritative(ROOT / "data" / "CL_llm_experiment.sqlite3"))
        self.assertTrue(dbsafety.is_authoritative("/tmp/anywhere/cl_compliance.SQLITE3"))
        self.assertFalse(dbsafety.is_authoritative("/tmp/anywhere/copy.sqlite3"))
        if MAIN.exists():
            self.assertTrue(dbsafety.is_authoritative(MAIN))      # the real main-checkout file, seen from a worktree

    def test_142_hard_link_to_a_sibling_checkout_file_and_errors_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "data") as d:
            fake = Path(d) / "renamed.sqlite3"
            target = ROOT / "data" / "CL_c_readonly_copy.sqlite3"
            if target.exists():
                with unittest.mock.patch.object(dbsafety, "_protected_files", return_value=[target]):
                    os.link(target, fake)
                    self.assertTrue(dbsafety.is_authoritative(fake))
                    fake.unlink()
        with unittest.mock.patch("os.path.samefile", side_effect=PermissionError("x")):
            p = ROOT / "tests" / "__init__.py"
            if p.exists():
                self.assertTrue(dbsafety.is_authoritative(p))

    @unittest.skipUnless(DB is not None, "no database copy")
    def test_143_dry_run_refuses_a_symlink_output(self):
        with tempfile.TemporaryDirectory() as d:
            link = Path(d) / "out.sqlite3"
            link.symlink_to(Path(d) / "dangling-target.sqlite3")
            with self.assertRaises(FileExistsError):
                D.dry_run(DB, out=link)
            self.assertFalse((Path(d) / "dangling-target.sqlite3").exists())


@unittest.skipUnless(DB is not None, "no database copy")
class AmendmentEvidence(unittest.TestCase):
    def test_144_footnotes_map_to_the_right_articles(self):
        er = A.footnote_index(DB, "FTA-VAT-ER@v3")["articles"]
        self.assertEqual([f["instruments"] for f in er["14"]], [["cabinet decision 100 2024"]])
        self.assertEqual([f["instruments"] for f in er["7"]], [["cabinet decision 100 2024"]])
        self.assertIn("cabinet decision 149 2026", {i for f in er["55"] for i in f["instruments"]})
        dl = A.footnote_index(DB, "FTA-VAT-DL8@v1")["articles"]
        self.assertEqual([f["instruments"] for f in dl["13"]], [["decree-law 18 2022"]])
        by_ins = A.instrument_articles_from_footnotes(DB, "FTA-VAT-ER@v3")
        self.assertEqual(by_ins["cabinet decision 100 2025"], ["59", "60"])
        self.assertFalse({"6", "7", "8", "14", "15", "16", "17", "18"} & set(by_ins["cabinet decision 149 2026"]))

    def test_145_future_effective_footnote_text_is_flagged(self):
        v = V.build_validity(DB, as_of="2026-10-17")
        fut = next(i for i in v["issues"] if i["kind"] == "future_text")
        self.assertIn("FTA-VAT-ER|55", fut["provisions"])
        self.assertIn("1 October 2027", fut["message"])

    def test_146_incomplete_amendment_list_flags_the_whole_outdated_source(self):
        v = V.build_validity(DB, as_of="2026-10-17")
        ps = next(i for i in v["issues"] if i["id"] == "FTA-VAT-DL8:partial-scope")
        self.assertEqual((ps["provisions"], ps["version_id"]), (["FTA-VAT-DL8|*"], "FTA-VAT-DL8@v1"))
        st = I.provision_status(v, "FTA-VAT-DL8", "Article 13, p. 11", "FTA-VAT-DL8@v1")
        self.assertIn("outdated", st["kinds"])                      # registration articles are no longer shown as clean
        self.assertTrue(all("version_id" in i for i in v["issues"]))

    def test_147_instrument_types_never_cross_match_and_unknown_dates_count(self):
        self.assertNotEqual(A._norm_instrument("Ministerial Decision No. 100 of 2024"), A._norm_instrument("Cabinet Decision No. 100 of 2024"))
        self.assertNotEqual(A._norm_instrument("FTA Decision No. 13 of 2026"), A._norm_instrument("Cabinet Decision No. 13 of 2026"))
        reg = json.loads((ROOT / "knowledge_base" / "CL_source_register.json").read_text(encoding="utf-8"))
        reg["instruments"].append({"instrument_id": "X-UNDATED", "title": "Cabinet Decision No. 999 of 2026", "type": "amending cabinet decision",
                                   "amends_source": "FTA-VAT-ER", "issued": None, "effective": None, "articles_affected": ["7"],
                                   "articles_list_complete": True, "status": "in force", "evidence": "test"})
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "reg.json"
            p.write_text(json.dumps(reg), encoding="utf-8")
            m = {v["version_id"]: v for v in A.amendment_map(p, "2026-10-17")["versions"]}
        self.assertIn("X-UNDATED", m["FTA-VAT-ER@v3"]["missing_with_unknown_effective_date"])


@unittest.skipUnless(DB is not None, "no database copy")
class InterfaceRules(unittest.TestCase):
    def test_148_superseded_versions_are_never_certifiable_and_stale_exports_are_refused(self):
        v = V.build_validity(DB, as_of="2026-10-17")
        v2 = json.loads(json.dumps(v))
        for x in v2["versions"]:
            x["approved"] = True                                      # pretend everything were approved
        old = I.provision_status(v2, "FTA-VAT-ER", "Article 8, p. 7", "FTA-VAT-ER@v1")
        cur = I.provision_status(v2, "FTA-VAT-ER", "Article 8, p. 7", "FTA-VAT-ER@v3")
        self.assertFalse(old["certifiable"])
        self.assertTrue(cur["certifiable"])
        with tempfile.TemporaryDirectory() as d:
            other = Path(d) / "other.sqlite3"
            other.write_bytes(b"not the same build")
            with self.assertRaises(ValueError):
                I.load_validity(db=other)
        self.assertEqual(I.load_validity(db=DB)["_meta"]["database_md5"], hashlib.md5(DB.read_bytes()).hexdigest())

    def test_149_web_page_conflicts_use_the_whole_page_key(self):
        v = {"issues": [{"id": "c", "kind": "conflict", "provisions": ["FTA-VAT-REG-PAGE|*"], "message": "m"}],
             "current_versions": {}, "versions": []}
        self.assertTrue(I.provision_status(v, "FTA-VAT-REG-PAGE", "Paragraph 4")["conflict"])


@unittest.skipUnless(DB is not None and (ROOT / "data" / "raw").exists(), "database or raw files missing")
class NumberCounts(unittest.TestCase):
    def test_150_page_numbers_no_longer_excuse_numbers_and_split_numbers_are_caught(self):
        self.assertTrue(X._unexplained({"30"}, {"15"}, set()))
        self.assertTrue(X._unexplained({"201"}, {"20"}, {"38"}))
        a = X.second_extractor_agreement(DB, "FTA-VAT-ER@v1")
        if a["status"] == "unavailable":
            self.skipTest("pdftotext not installed")
        self.assertEqual(a["number_mismatches"], [])
        self.assertIn("70", a["number_count_differences"])          # 'Article 8 0' in our v1 text vs '80' in the PDF


if __name__ == "__main__":
    import unittest.mock  # noqa: F401
    unittest.main()


@unittest.skipUnless(DB is not None, "no database copy")
class ContractV11(unittest.TestCase):
    def test_162_completeness_and_approval_are_separate_and_only_both_certify(self):
        v = I.load_validity(db=DB)
        p = [("FTA-VAT-ER", "Article 7, pp. 6-7", "FTA-VAT-ER@v3")]
        lab = I.answer_label(v, "complete", p)
        self.assertEqual((lab["retrieval_completeness"], lab["source_approval"], lab["certified"]), ("complete", "not_approved", False))
        self.assertIn("not been approved", lab["user_wording"])
        v2 = json.loads(json.dumps(v))
        for x in v2["versions"]:
            x["approved"] = True
        self.assertTrue(I.answer_label(v2, "complete", p)["certified"])
        for c in ("incomplete", "not_covered", "refusal", "unchecked"):
            self.assertFalse(I.answer_label(v2, c, p)["certified"], c)
        g1 = I.answer_label(v2, "complete", [("FTA-VAT-ER", "Article 14, pp. 12-13, part 1", "FTA-VAT-ER@v3")])
        self.assertFalse(g1["certified"])
        self.assertIn("disagree", g1["user_wording"])
        self.assertFalse(I.answer_label(v2, "complete", [])["certified"])
        with self.assertRaises(ValueError):
            I.answer_label(v2, "certified", p)


@unittest.skipUnless(DB is not None, "no database copy")
class ContractEdgeCases(unittest.TestCase):
    """Second independent review (QA2, 17 Oct 2026): cases where 'certified' was wrongly True."""

    def setUp(self):
        v = I.load_validity(db=DB)
        self.v = json.loads(json.dumps(v))
        for x in self.v["versions"]:
            x["approved"] = True                       # worst case: pretend every version were approved

    def blocked(self, *p):
        lab = I.answer_label(self.v, "complete", [p])
        self.assertFalse(lab["certified"], (p, lab))
        return {b["reason"] for b in lab["blockers"]}

    def test_164_only_current_known_parsed_versions_of_the_same_source_certify(self):
        self.assertTrue(I.answer_label(self.v, "complete", [("FTA-VAT-ER", "Article 7, pp. 6-7", "FTA-VAT-ER@v3")])["certified"])
        self.assertIn("version_not_current", self.blocked("FTA-VAT-ER", "Article 7, pp. 6-7", "FTA-VAT-ER@v1"))   # approved but superseded
        self.assertIn("version_outdated", self.blocked("FTA-VAT-ER", "Article 7, pp. 6-7", "FTA-VAT-ER@v1"))
        self.assertIn("version_of_other_source", self.blocked("FTA-VAT-ER", "Article 7, pp. 6-7", "FTA-VAT-DL8@v1"))
        for loc in ("Article (55)", "ARTICLE 55", "", "Front matter, p. 1"):
            self.assertIn("unparsed_locator", self.blocked("FTA-VAT-ER", loc, "FTA-VAT-ER@v3"))
        self.assertIn("no_version_given", self.blocked("FTA-VAT-ER", "Article 7, pp. 6-7", None))
        self.assertIn("unknown_version", self.blocked("FTA-VAT-ER", "Article 7, pp. 6-7", "FTA-VAT-ER@v9"))
        self.assertIn("outdated", self.blocked("FTA-VAT-DL8", "Article 13, p. 11", "FTA-VAT-DL8@v1"))                 # SRC|* issue
        self.assertIn("conflict", self.blocked("FTA-VAT-ER", "Article 14, pp. 12-13, part 1", "FTA-VAT-ER@v3"))

    def test_165_validity_must_be_loaded_against_the_database_it_describes(self):
        with self.assertRaises(ValueError):
            I.load_validity()                          # no database given
        self.assertTrue(I.load_validity(allow_unchecked=True))

    def test_166_register_approval_is_not_enough_without_database_approval(self):
        reg = json.loads((ROOT / "knowledge_base" / "CL_source_register.json").read_text(encoding="utf-8"))
        for s in reg["sources"]:
            for v in s["versions"]:
                if v["version_id"] == "FTA-VAT-ER@v3":
                    v.update(kb_status="approved", approval={"by": "x", "approved_date": "2026-10-17", "evidence": "x"})
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "reg.json"
            p.write_text(json.dumps(reg), encoding="utf-8")
            (Path(d) / "CL_collected_lock.json").write_text((ROOT / "knowledge_base" / "CL_collected_lock.json").read_text(encoding="utf-8"))
            from compliance_agent.rag_c.register import validate
            errs = validate(p, lock_path=Path(d) / "CL_collected_lock.json", data_dir=None, db=DB)["errors"]
            self.assertTrue(any("register says approved but the database says candidate" in e for e in errs), errs)
            self.assertEqual(V.build_validity(DB, p, "2026-10-17")["approved_versions"], [])
