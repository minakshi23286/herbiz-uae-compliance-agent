"""Workstream C read-only tools: source register validation, hashes, duplicates, inventory, version comparison and the
offline ingestion dry run. Each test checks the database it reads is byte-identical afterwards."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent import dbsafety  # noqa: E402
from compliance_agent.rag_c import dryrun as D, inventory as I, register as R  # noqa: E402

REG = R.REGISTER
md5 = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest()
# Prefer the read-only copy; fall back to the authoritative path (a stand-in copy inside a worktree).
DB = next((p for p in (ROOT / "data" / "CL_c_readonly_copy.sqlite3", dbsafety.AUTHORITATIVE) if p.exists()), None)


class RegisterRules(unittest.TestCase):
    def setUp(self):
        self.reg = json.loads(REG.read_text(encoding="utf-8"))
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, reg) -> dict:
        p = Path(self.tmp.name) / "reg.json"
        p.write_text(json.dumps(reg), encoding="utf-8")
        return R.validate(p, data_dir=None)

    def test_94_committed_register_is_valid_and_covers_every_locked_file(self):
        out = R.validate(REG, db=DB)
        self.assertEqual(out["errors"], [])
        lock = json.loads(I.LOCK.read_text(encoding="utf-8"))
        self.assertEqual(out["versions"], len(lock["documents"]))
        for s in self.reg["sources"]:
            for v in s["versions"]:
                self.assertEqual(v["kb_status"], "candidate")          # nothing approved without a reviewer (D3)
        for c in self.reg["candidates"]:
            self.assertIs(c["activated"], False)

    def test_95_register_rejects_activation_invented_dates_and_broken_provenance(self):
        cases = []
        r = copy.deepcopy(self.reg); r["sources"][0]["versions"][0]["kb_status"] = "approved"
        cases.append((r, "approved without approver"))
        r = copy.deepcopy(self.reg); r["sources"][0]["versions"][0]["sha256"] = "0" * 64
        cases.append((r, "not in the collection lock"))
        r = copy.deepcopy(self.reg); r["sources"][1]["versions"].pop()
        cases.append((r, "is not in the register"))
        r = copy.deepcopy(self.reg); r["sources"][0]["versions"][0]["amendments_as_stated"][0]["effective"] = "1 Jan 2018"
        cases.append((r, "date must be YYYY-MM-DD"))
        r = copy.deepcopy(self.reg); r["sources"][0]["versions"][0]["amendments_evidence"] = None
        cases.append((r, "without amendments_evidence"))
        r = copy.deepcopy(self.reg); r["register_version"] = "9.9.9"
        cases.append((r, "no entry for the current register_version"))
        cand = {"candidate_id": "X", "activated": True, "kb_status": "active", "verification_status": "verified",
                "evidence": "snippet_only: search result", "confidence": "high", "url": "https://tax.gov.ae/x"}
        r = copy.deepcopy(self.reg); r["candidates"] = [cand]
        cases.append((r, "activated: false"))
        cases.append((r, "kb_status must be not_ingested"))
        cases.append((r, "snippet-only evidence cannot be high confidence"))
        r = copy.deepcopy(self.reg); r["candidates"] = [dict(cand, candidate_id=r["sources"][0]["source_id"])]
        cases.append((r, "duplicate candidate_id"))
        for reg, msg in cases:
            with self.subTest(msg=msg):
                errs = self.check(reg)["errors"]
                self.assertTrue(any(msg in e for e in errs), errs)


class RawFiles(unittest.TestCase):
    @unittest.skipUnless((I.DATA / "raw").exists(), "data/raw not present")
    def test_96_raw_files_match_the_lock(self):
        h = I.hashes()
        self.assertEqual(h["ok"], h["total"], h["files"])
        self.assertEqual(h["duplicate_hashes_in_lock"], {})

    def test_97_tampered_raw_file_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            lock = json.loads(I.LOCK.read_text(encoding="utf-8"))
            first = lock["documents"][0]
            p = Path(d) / first["raw_path"]; p.parent.mkdir(parents=True)
            p.write_bytes(b"altered")
            (Path(d) / "raw" / "stray.pdf").write_bytes(b"x")
            h = I.hashes(data_dir=Path(d))
            status = {r["raw_path"]: r["status"] for r in h["files"]}
            self.assertEqual(status[first["raw_path"]], "MISMATCH")
            self.assertIn("missing", status.values())
            self.assertIn("raw/stray.pdf", h["raw_files_not_in_lock"])


@unittest.skipUnless(DB is not None, "no database copy present")
class ReadOnlyCorpusTools(unittest.TestCase):
    def setUp(self):
        self.before = md5(DB)

    def tearDown(self):
        self.assertEqual(md5(DB), self.before, "a read-only tool changed the database")

    def test_98_inventory_reports_coverage_and_the_merged_article_1_heading(self):
        inv = I.inventory(DB)
        self.assertEqual(inv["integrity"], "ok")
        self.assertEqual(inv["counts"]["passages"], inv["fts_rows"])
        cov = {v["version_id"]: v["coverage"] for v in inv["versions"]}
        er = [k for k in cov if k.startswith("FTA-VAT-ER@")]
        self.assertTrue(er)
        for k in er:
            self.assertEqual(cov[k]["missing_article_numbers"], [1])
            self.assertEqual(cov[k]["headings_merged_into_other_passages"][0]["article"], 1)

    def test_99_no_duplicate_passages_inside_a_version(self):
        dup = I.duplicates(DB)
        self.assertEqual(dup["identical_passages_within_one_version"], [])
        self.assertEqual(dup["same_raw_bytes"], [])

    def test_100_compare_reuses_the_existing_kb_compare(self):
        from compliance_agent import kb
        with mock.patch.object(kb.KnowledgeBase, "compare", autospec=True,
                               return_value={"rows": [{"unit": "Article 7", "change": "substantive"}]}) as m:
            out = I.compare(DB, "FTA-VAT-ER@v2", "FTA-VAT-ER@v3")
        m.assert_called_once()
        self.assertEqual(out["substantive_units"], ["Article 7"])
        with self.assertRaises(ValueError):
            I.compare(DB, "FTA-VAT-ER@v2", "FTA-VAT-ER@v99")

    @unittest.skipUnless((I.DATA / "raw").exists(), "data/raw not present")
    def test_101_dry_run_is_offline_reproducible_and_never_overwrites(self):
        raw_before = {p: md5(p) for p in (I.DATA / "raw").rglob("*") if p.is_file()}
        lock_before = md5(I.LOCK)
        # The reference copy predates D10 (Article 1 split), so reproducibility is checked build-against-build:
        # two offline rebuilds from the same raw files and lock must be identical passage for passage.
        with tempfile.TemporaryDirectory() as d, \
                mock.patch("compliance_agent.kb.urllib.request.urlopen", side_effect=AssertionError("network used")):
            first = D.dry_run(DB, out=Path(d) / "first.sqlite3")
            rep = D.dry_run(Path(first["kept_build"]))
        self.assertTrue(rep["reproducible"], rep)
        self.assertEqual(rep["build_passages"], rep["reference_passages"])
        self.assertEqual({p: md5(p) for p in (I.DATA / "raw").rglob("*") if p.is_file()}, raw_before)
        self.assertEqual(md5(I.LOCK), lock_before)
        with tempfile.TemporaryDirectory() as d:
            existing = Path(d) / "exists.sqlite3"; existing.write_bytes(b"keep")
            with self.assertRaises(FileExistsError):
                D.dry_run(DB, out=existing)
            self.assertEqual(existing.read_bytes(), b"keep")
        with self.assertRaises(dbsafety.AuthoritativeDatabaseError):
            D.dry_run(DB, out=dbsafety.AUTHORITATIVE)


class Boundaries(unittest.TestCase):
    def test_102_workstream_c_tools_do_not_import_workstream_b_retrieval(self):
        pkg = ROOT / "compliance_agent" / "rag_c"
        for f in pkg.glob("*.py"):
            imports = re.findall(r"^\s*(?:from|import)\s+(\S+)", f.read_text(encoding="utf-8"), re.M)
            self.assertFalse([m for m in imports if re.search(r"llm_lab|retrieve|concepts", m)], f.name)


if __name__ == "__main__":
    unittest.main()
