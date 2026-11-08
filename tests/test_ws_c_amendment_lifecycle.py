"""End-to-end lifecycle of a newly published amendment, on a disposable workspace with SYNTHETIC documents:
discovery -> (approved) collection -> version comparison -> impact analysis -> review -> activation.

Everything happens in a temporary folder: a copy of the knowledge base, of the register and of the lock, and a
temporary raw folder. Source 'SYN-ER' and 'Cabinet Decision No. 999 of 2027' are invented; URLs under
/__SYNTHETIC_TEST__/ do not exist. At every stage the test also checks that NOTHING was activated automatically."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent import kb as K  # noqa: E402
from compliance_agent.clock import FixedClock  # noqa: E402
from compliance_agent.dbsafety import copy_readonly  # noqa: E402
from compliance_agent.engine import Engine  # noqa: E402
from compliance_agent.rag_c import amendments as A, claims as C, discovery as DI, interface as I, monitor as M  # noqa: E402
from compliance_agent.rag_c import validity as V  # noqa: E402
from compliance_agent.rag_c.register import validate  # noqa: E402
from compliance_agent.store import Store  # noqa: E402

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None

REF = ROOT / "data" / "CL_c_readonly_copy.sqlite3"
SYN = "https://tax.gov.ae/__SYNTHETIC_TEST__/"
V1_URL, V2_URL, LISTING = SYN + "syn-er-2026.pdf", SYN + "syn-er-2027-consolidated.pdf", SYN + "legislation.aspx"
CD999_URL = SYN + "Cabinet-Decision-No-999-of-2027-SYNTHETIC.pdf"
REVIEWER = ("Test Reviewer (SYNTHETIC)", "qualified UAE tax reviewer (TEST ONLY)", "lifecycle test approval")
ENTRY = {"source_id": "SYN-ER", "issuing_authority": "SYNTHETIC Cabinet (test only)", "authority_type": "primary",
         "jurisdiction": "AE", "document_title": "SYNTHETIC Executive Regulation (test only)", "split": "article"}


def pdf(path: Path, pages: list[str]) -> bytes:
    doc = fitz.open()
    for text in pages:
        doc.new_page().insert_text((60, 70), text, fontsize=10)
    doc.save(str(path))
    doc.close()
    return path.read_bytes()


FRONT_V1 = "SYNTHETIC TEST DOCUMENT - NOT LAW\nThe Executive Regulation (SYNTHETIC)\nCabinet Decision No. 52 of 2017 - Issued 26 Nov 2017\n"
ART7_V1 = "Article 7 - Mandatory Registration\n1. The Mandatory Registration Threshold shall be AED 375,000 (SYNTHETIC).\n" \
          "2. Further synthetic clause text for the registration article.\n"
ART14 = "Article 14 - Tax Deregistration\n1. The Registrant must apply within 20 (twenty) Business Days (SYNTHETIC).\n"
FRONT_V2 = FRONT_V1 + "Cabinet Decision No. 999 of 2027 - Issued 1 Jan 2027 (Effective from 1 Feb 2027)\n"
ART7_V2 = "Article 7 - Mandatory Registration 1\n1. The Mandatory Registration Threshold shall be AED 400,000 (SYNTHETIC).\n" \
          "2. Further synthetic clause text for the registration article.\n\n1 Article amended as per Cabinet Decision No. 999 of 2027.\n"


@unittest.skipUnless(fitz is not None and REF.exists(), "PyMuPDF or the reference copy is missing")
class AmendmentLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.d = Path(cls.tmp.name)
        cls.ref_md5 = hashlib.md5(REF.read_bytes()).hexdigest()
        cls.db = copy_readonly(REF, d / "kb.sqlite3")
        (d / "kb_dir").mkdir()
        cls.reg_path = d / "kb_dir" / "CL_source_register.json"
        shutil.copy2(ROOT / "knowledge_base" / "CL_source_register.json", cls.reg_path)
        cls.lock = d / "kb_dir" / "CL_collected_lock.json"
        shutil.copy2(ROOT / "knowledge_base" / "CL_collected_lock.json", cls.lock)
        cls.v1 = pdf(d / "v1.pdf", [FRONT_V1, ART7_V1, ART14])
        cls.v2 = pdf(d / "v2.pdf", [FRONT_V2, ART7_V2, ART14])
        cls.clock = FixedClock("2026-12-01T09:00:00")
        cls.served = {V1_URL: cls.v1}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    # helpers ---------------------------------------------------------------------------------------------------
    def kb(self, clock=None):
        e = Engine(Store(self.db), clock or self.clock)
        fetch = lambda url: (self.served[url], "application/pdf") if url in self.served else (_ for _ in ()).throw(K.CollectError("404"))
        return K.KnowledgeBase(e, data_dir=self.d / "kb_dir", fetch=fetch, lock_path=self.lock)

    def reg(self) -> dict:
        return json.loads(self.reg_path.read_text(encoding="utf-8"))

    def save(self, r: dict):
        self.reg_path.write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")

    def status(self, vid):
        con = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        try:
            row = con.execute("SELECT status FROM source_versions WHERE version_id = ?", (vid,)).fetchone()
            return row[0] if row else None
        finally:
            con.close()

    def register_version(self, vid, url, sha, amendments, latest_eff, kb_status="candidate", approval=None):
        lock = json.loads(self.lock.read_text(encoding="utf-8"))
        d = next(x for x in lock["documents"] if x["sha256"] == sha)
        return {"version_id": vid, "url": url, "sha256": sha, "bytes": d["bytes"], "mime": d["mime"], "raw_path": d["raw_path"],
                "retrieved_at": d["retrieved_at"], "file_label": "SYNTHETIC", "self_description": "SYNTHETIC",
                "publication_date": None, "amendments_as_stated": amendments,
                "amendments_evidence": "observed_in_file: SYNTHETIC front matter (lifecycle test)" if amendments else None,
                "latest_effective_as_stated": latest_eff, "kb_status": kb_status, "verification_status": "verified" if approval else "unverified",
                "verification": {"by": REVIEWER[0]} if approval else None, "extraction_label": "UNVERIFIED_EXTRACTION",
                "approval": approval, "currency_observations": []}

    # the lifecycle, in order -----------------------------------------------------------------------------------
    def test_160_full_lifecycle(self):
        # ---- stage 0: baseline. SYN-ER v1 collected, reviewed, approved and recorded (the "before" world) ----------
        k = self.kb()
        r1 = k.collect({**ENTRY, "url": V1_URL})
        self.assertEqual((r1["outcome"], r1["version_id"]), ("new_version", "SYN-ER@v1"))
        k.e.review_source("SYN-ER@v1", "approve", *REVIEWER)
        k.e.s.close()
        sha1 = hashlib.sha256(self.v1).hexdigest()
        r = self.reg()
        r["sources"].append({"source_id": "SYN-ER", "title": "SYNTHETIC Executive Regulation", "issuing_authority": ENTRY["issuing_authority"],
                             "document_type": "executive regulation (SYNTHETIC)", "jurisdiction": "AE", "language": "en",
                             "translation_status": "SYNTHETIC", "scope_topics": {"articles": {"7": "Mandatory Registration", "14": "Tax Deregistration"}},
                             "versions": [self.register_version("SYN-ER@v1", V1_URL, sha1,
                                          [{"instrument": "Cabinet Decision No. 52 of 2017", "issued": "2017-11-26", "effective": "2018-01-01"}],
                                          "2018-01-01", "approved", {"by": REVIEWER[0], "approved_date": "2026-12-01", "evidence": "lifecycle test"})]})
        r["claims"].append({"claim_id": "SYN-CL-THRESHOLD-V1", "topic": "syn.registration.threshold", "value": 375000, "unit": "AED",
                            "source_id": "SYN-ER", "version_id": "SYN-ER@v1", "article": "7", "quote": "AED 375,000",
                            "in_knowledge_base": True, "evidence": "observed_in_file: SYNTHETIC v1"})
        r["register_version"] = "9.0.0"
        r["changes"].append({"version": "9.0.0", "date": "2026-12-01", "by": "lifecycle test", "what": "SYNTHETIC baseline"})
        self.save(r)
        self.assertEqual(validate(self.reg_path, lock_path=self.lock, data_dir=self.d / "kb_dir")["errors"], [])
        val0 = V.build_validity(self.db, self.reg_path, "2026-12-01")
        label0 = I.answer_label(val0, "complete", [("SYN-ER", "Article 7, p. 2", "SYN-ER@v1")])
        self.assertTrue(label0["certified"], label0)                     # approved + current + no issue -> certifiable

        # ---- stage 1: discovery. The amendment and a new consolidation appear on the listing ----------------------
        listing = lambda links: ("<ul>" + "".join(f'<li><a href="{u}">{t}</a> Issue date: Jan 01, 2027</li>' for u, t in links) + "</ul>").encode()
        items = [{"url": LISTING, "kind": "listing", "candidate_id": "SYN-LISTING", "source_id": None, "in_scope_articles": []},
                 {"url": V1_URL, "kind": "document", "source_id": "SYN-ER", "version_id": "SYN-ER@v1",
                  "collected_sha256": sha1, "in_scope_articles": ["7", "14"]}]

        def fx(table):
            return lambda url: ({"url": url, "http_status": 200, "content_type": "x", "body": table[url], "markdown": None,
                                 "via": "fixture", "error": None, "extra": {}} if url in table else
                                {"url": url, "http_status": 404, "content_type": None, "body": None, "markdown": None,
                                 "via": "fixture", "error": None, "extra": {}})
        day1 = M.run(fx({LISTING: listing([(V1_URL, "SYNTHETIC Executive Regulation (consolidated 2026)")]), V1_URL: self.v1}),
                     {}, self.reg_path, now="2027-01-01T06:00:00+04:00", items=items)
        day2 = M.run(fx({LISTING: listing([(V1_URL, "SYNTHETIC Executive Regulation (consolidated 2026)"),
                                           (CD999_URL, "SYNTHETIC Cabinet Decision No. 999 of 2027 amending the Executive Regulation"),
                                           (V2_URL, "SYNTHETIC Executive Regulation (consolidated 2027)")]),
                         V1_URL: self.v2}),                               # the old URL now serves the new consolidation
                     day1["state"], self.reg_path, now="2027-01-02T06:00:00+04:00", items=items,
                     validity=V.build_validity(self.db, self.reg_path, "2027-01-02"))
        kinds = sorted(a["kind"] for a in day2["alerts"])
        self.assertEqual(sorted(p["url"] for p in day2["proposals"]), sorted([CD999_URL, V2_URL]))
        self.assertIn("new_document_on_listing", kinds)
        self.assertIn("differs_from_collected_version", kinds)
        self.assertIn("changed_substantive_in_scope", kinds)              # Art. 7 changed, and it is in scope
        a7 = next(a for a in day2["alerts"] if a["kind"] == "changed_substantive_in_scope")
        self.assertIn("SYN-ER|7", a7["provisions"])
        self.assertNotIn("SYN-ER|14", a7["provisions"])                 # unchanged article not reported (QA2 M5)
        self.assertEqual(self.status("SYN-ER@v1"), "approved")           # the monitor changed nothing
        new_reg = DI.add_proposals(self.reg_path, day2["proposals"], "2027-01-02")
        self.assertTrue(all(c["activated"] is False and c["kb_status"] == "not_ingested" for c in new_reg["candidates"]))
        self.save(new_reg)
        self.assertEqual(validate(self.reg_path, lock_path=self.lock, data_dir=self.d / "kb_dir")["errors"], [])

        # ---- stage 1b: the window "amendment known, new text not collected" ----------------------------------------
        r = self.reg()
        r["instruments"].append({"instrument_id": "SYN-CD-999-2027", "title": "Cabinet Decision No. 999 of 2027", "type": "amending cabinet decision",
                                 "amends_source": "SYN-ER", "issued": "2027-01-01", "effective": "2027-02-01", "articles_affected": ["7"],
                                 "articles_list_complete": True, "status": "in force",
                                 "evidence": "observed_listing_only: SYNTHETIC listing; article named in the decision title text"})
        r["register_version"] = "9.0.1"
        r["changes"].append({"version": "9.0.1", "date": "2027-01-02", "by": "lifecycle test", "what": "instrument recorded before collection"})
        self.save(r)
        win = V.build_validity(self.db, self.reg_path, "2027-03-01")
        self.assertIn("SYN-ER|7", next(i for i in win["issues"] if i["id"] == "SYN-ER:outdated")["provisions"])   # QA2 M6
        w7 = I.answer_label(win, "complete", [("SYN-ER", "Article 7, p. 2", "SYN-ER@v1")])
        self.assertFalse(w7["certified"])
        self.assertTrue({"outdated", "version_outdated"} <= {b["reason"] for b in w7["blockers"]}, w7["blockers"])
        self.assertIn("out of date", w7["user_wording"])

        # ---- stage 2: founder-approved collection of the new consolidation (into the disposable workspace) --------
        self.served[V2_URL] = self.v2
        k = self.kb(FixedClock("2027-01-03T09:00:00"))
        r2 = k.collect({**ENTRY, "url": V2_URL})
        self.assertEqual((r2["outcome"], r2["version_id"], r2["status"]), ("new_version", "SYN-ER@v2", "candidate"))
        self.assertEqual(self.status("SYN-ER@v1"), "approved")           # collection never activates or supersedes

        # ---- stage 3: version comparison -------------------------------------------------------------------------
        cmp = k.compare("SYN-ER@v1", "SYN-ER@v2")
        k.e.s.close()
        changed = {row["unit"]: row["change"] for row in cmp["rows"]}
        self.assertEqual(changed.get("Article 7"), "substantive")
        self.assertNotIn("Article 14", [u for u, c in changed.items() if c == "substantive"])

        # ---- stage 4: impact analysis ----------------------------------------------------------------------------
        sha2 = hashlib.sha256(self.v2).hexdigest()
        r = self.reg()
        ins = next(i for i in r["instruments"] if i["instrument_id"] == "SYN-CD-999-2027")
        ins.update(articles_affected=None, articles_list_complete=False, evidence="observed_in_file: SYNTHETIC v2 front matter")  # rely on footnotes now
        syn = next(s for s in r["sources"] if s["source_id"] == "SYN-ER")
        syn["versions"].append(self.register_version("SYN-ER@v2", V2_URL, sha2,
                               [{"instrument": "Cabinet Decision No. 52 of 2017", "issued": "2017-11-26", "effective": "2018-01-01"},
                                {"instrument": "Cabinet Decision No. 999 of 2027", "issued": "2027-01-01", "effective": "2027-02-01"}], "2027-02-01"))
        r["claims"].append({"claim_id": "SYN-CL-THRESHOLD-V2", "topic": "syn.registration.threshold", "value": 400000, "unit": "AED",
                            "source_id": "SYN-ER", "version_id": "SYN-ER@v2", "article": "7", "quote": "AED 400,000",
                            "in_knowledge_base": True, "evidence": "observed_in_file: SYNTHETIC v2"})
        r["register_version"] = "9.1.0"
        r["changes"].append({"version": "9.1.0", "date": "2027-01-03", "by": "lifecycle test", "what": "SYN-ER@v2 recorded as candidate; CD 999/2027"})
        self.save(r)
        self.assertEqual(validate(self.reg_path, lock_path=self.lock, data_dir=self.d / "kb_dir")["errors"], [])
        amap = {v["version_id"]: v for v in A.amendment_map(self.reg_path, "2027-03-01", db=self.db)["versions"]}
        self.assertEqual(amap["SYN-ER@v1"]["missing_in_force_instruments"], ["SYN-CD-999-2027"])
        self.assertIn("7", [x["article"] for x in amap["SYN-ER@v1"]["affected_articles"]])       # learnt from v2's footnote
        self.assertFalse(amap["SYN-ER@v2"]["outdated"])
        conflicts = C.check_claims(self.db, self.reg_path)["conflicts"]
        self.assertIn("syn.registration.threshold", [c["topic"] for c in conflicts])           # old vs new value surfaced
        val4 = V.build_validity(self.db, self.reg_path, "2027-03-01")
        self.assertEqual(val4["current_versions"]["SYN-ER"]["version_id"], "SYN-ER@v2")
        old = I.answer_label(val4, "complete", [("SYN-ER", "Article 7, p. 2", "SYN-ER@v1")])
        new = I.answer_label(val4, "complete", [("SYN-ER", "Article 7, p. 2", "SYN-ER@v2")])
        self.assertFalse(old["certified"])
        self.assertTrue({"version_not_current", "version_outdated"} <= {b["reason"] for b in old["blockers"]}, old["blockers"])   # not only the conflict (QA2)
        self.assertFalse(new["certified"])                               # v2 is not approved yet
        self.assertEqual(new["source_approval"], "not_approved")

        # ---- stage 5a: a register "approval" without a database review is refused (QA2 M9) -------------------------
        fake = copy.deepcopy(self.reg())
        for v in next(x for x in fake["sources"] if x["source_id"] == "SYN-ER")["versions"]:
            if v["version_id"] == "SYN-ER@v2":
                v.update(kb_status="approved", approval={"by": "someone", "approved_date": "2027-02-01", "evidence": "none"})
        fp = self.d / "kb_dir" / "fake_register.json"
        fp.write_text(json.dumps(fake), encoding="utf-8")
        errs = validate(fp, lock_path=self.lock, data_dir=self.d / "kb_dir", db=self.db)["errors"]
        self.assertTrue(any("register says approved but the database says candidate" in e for e in errs), errs)
        self.assertNotIn("SYN-ER@v2", V.build_validity(self.db, fp, "2027-03-01")["approved_versions"])

        # ---- stage 5: review. A named reviewer approves v2 in the knowledge base ---------------------------------
        e = Engine(Store(self.db), FixedClock("2027-02-02T09:00:00"))
        with self.assertRaises(Exception):
            e.review_source("SYN-ER@v2", "approve", "", "", "")                                   # anonymous approval refused
        self.assertEqual(e.review_source("SYN-ER@v2", "approve", *REVIEWER)["status"], "approved")
        e.s.close()
        self.assertEqual((self.status("SYN-ER@v1"), self.status("SYN-ER@v2")), ("superseded", "approved"))
        val5 = V.build_validity(self.db, self.reg_path, "2027-03-01")
        self.assertFalse(I.answer_label(val5, "complete", [("SYN-ER", "Article 7, p. 2", "SYN-ER@v2")])["certified"])   # register not yet updated
        warn = validate(self.reg_path, lock_path=self.lock, data_dir=self.d / "kb_dir", db=self.db)["warnings"]
        self.assertTrue(any("database status approved not yet recorded" in w for w in warn), warn)

        # ---- stage 6: activation = the register records the approval (new register version), then validation -----
        r = self.reg()
        syn = next(s for s in r["sources"] if s["source_id"] == "SYN-ER")
        for v in syn["versions"]:
            if v["version_id"] == "SYN-ER@v1":
                v["kb_status"] = "superseded"
            if v["version_id"] == "SYN-ER@v2":
                v.update(kb_status="approved", verification_status="verified", verification={"by": REVIEWER[0]},
                         approval={"by": REVIEWER[0], "approved_date": "2027-02-02", "evidence": "review_source accepted (lifecycle test)"})
        r["claims"] = [c for c in r["claims"] if c["claim_id"] != "SYN-CL-THRESHOLD-V1"]       # old value retired with v1
        r["register_version"] = "9.2.0"
        r["changes"].append({"version": "9.2.0", "date": "2027-02-02", "by": "lifecycle test", "what": "SYN-ER@v2 approved; v1 superseded"})
        self.save(r)
        self.assertEqual(validate(self.reg_path, lock_path=self.lock, data_dir=self.d / "kb_dir", db=self.db)["errors"], [])
        val6 = V.build_validity(self.db, self.reg_path, "2027-03-01")
        self.assertIn("SYN-ER@v2", val6["approved_versions"])
        ok = I.answer_label(val6, "complete", [("SYN-ER", "Article 7, p. 2", "SYN-ER@v2")])
        self.assertTrue(ok["certified"], ok)
        self.assertFalse(I.answer_label(val6, "incomplete", [("SYN-ER", "Article 7, p. 2", "SYN-ER@v2")])["certified"])   # completeness still matters
        self.assertFalse(I.answer_label(val6, "complete", [("SYN-ER", "Article 7, p. 2", "SYN-ER@v1")])["certified"])     # superseded never
        syn_issues = [i for i in val6["issues"] if any(p.startswith("SYN-ER|") for p in i["provisions"])]
        # the only SYN-ER issue left is the expected numbering gap (the synthetic text has only Art. 7 and 14); it does not
        # touch Art. 7, so the answer above is certifiable
        self.assertEqual([i["kind"] for i in syn_issues], ["extraction"])
        self.assertNotIn("SYN-ER|7", syn_issues[0]["provisions"])
        # real sources untouched by the whole lifecycle; the reference database unchanged
        self.assertTrue(all(v["kb_status"] == "candidate" for s in r["sources"] if not s["source_id"].startswith("SYN") for v in s["versions"]))
        self.assertEqual(hashlib.md5(REF.read_bytes()).hexdigest(), self.ref_md5)


if __name__ == "__main__":
    unittest.main()
