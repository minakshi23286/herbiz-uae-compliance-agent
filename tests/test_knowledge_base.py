"""Knowledge-base pipeline tests. Offline: documents are generated in the test; no network is used.

Run: python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compliance_agent import kb as K  # noqa: E402
from compliance_agent import scenario as sc  # noqa: E402
from compliance_agent.clock import FixedClock  # noqa: E402
from compliance_agent.engine import Engine, WorkflowError  # noqa: E402
from compliance_agent.store import Store  # noqa: E402

REV = ("Test Reviewer", "qualified tax reviewer (test)", "test note")
_, PROF = sc.load_fixtures()


def make_pdf(pages: list[list[str]]) -> bytes:
    """Minimal valid PDF, one Helvetica text line per entry. Empty list = page with no text layer."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in pages:
        body = "BT /F1 10 Tf 14 TL 50 780 Td " + " ".join(
            "(" + ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for ln in lines) + " ET"
        objs.append(f"<< /Length {len(body.encode('latin-1'))} >>\nstream\n{body}\nendstream")
        content_no = len(objs)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents {content_no} 0 R /Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


HEADER = "Test Decree No. 1 of 2026 - Unofficial translation"
LAW_PAGES = [
    [HEADER, "1", "This is not an official translation.", "Article 1 - Definitions", "Threshold: the amount set by the Regulation."],
    [HEADER, "2", "Article 2 - Registration 4", "1. Every Person shall register where the total value of supplies",
     "exceeded the Threshold over the previous 12 -month period.", "4 Article amended as per Test Decision No. 9 of 2026."],
    [HEADER, "3", "Article 3 - Calculating the Threshold", "The value of taxable Goods and Services.", "Salaries are not mentioned here."],
    [HEADER, "4", "Article 4 - Penalties", "Penalties are set elsewhere.", "Article 4 of this text is short."],
]


def entry(sid="TEST-LAW", url="https://tax.gov.ae/test/law.pdf", **kw):
    return {"source_id": sid, "url": url, "issuing_authority": "Test authority (test document)", "authority_type": "primary",
            "jurisdiction": "AE", "document_title": "Test law", "publication_date": None, "effective_date": None, **kw}


class KBTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.e = Engine(Store(":memory:"), FixedClock("2026-10-16T10:00:00"))
        self.kb = K.KnowledgeBase(self.e, Path(self.tmp.name), fetch=self._fetch)
        self.served = {}

    def tearDown(self):
        self.tmp.cleanup()

    def _fetch(self, url):
        K.check_host(url)
        if url not in self.served:
            raise K.CollectError("unavailable after 2 attempts: test outage")
        return self.served[url]

    def test_30_allowlist_and_unavailable_sources_are_recorded(self):
        r = self.kb.collect(entry(url="https://evil.example.com/law.pdf"))
        self.assertEqual(r["outcome"], "refused")
        r = self.kb.collect(entry(url="http://tax.gov.ae/law.pdf"))
        self.assertEqual(r["outcome"], "refused")
        r = self.kb.collect(entry())
        self.assertEqual(r["outcome"], "failed")
        st = self.kb.status()
        self.assertEqual((st["documents"], st["collection_failures"]), (0, 1))
        self.assertEqual([a["outcome"] for a in st["attempts"]], ["refused", "refused", "failed"])

    def test_31_pdf_articles_headers_footnotes_and_locators(self):
        self.served[entry()["url"]] = (make_pdf(LAW_PAGES), "application/pdf")
        r = self.kb.collect(entry())
        self.assertEqual((r["outcome"], r["status"], r["extraction"]), ("new_version", "candidate", "ok"))
        locs = [p["locator"] for p in self.e.s.q("SELECT locator FROM passages ORDER BY seq")]
        self.assertEqual(locs, ["Front matter, p. 1", "Article 1, p. 1", "Article 2, p. 2", "Article 3, p. 3", "Article 4, p. 4"])
        allt = " ".join(p["text"] for p in self.e.s.q("SELECT text FROM passages"))
        self.assertNotIn("Unofficial translation", allt)  # running header removed
        doc = self.e.s.one("SELECT * FROM documents")
        self.assertIn("Running headers removed", doc["extraction_note"])
        self.assertTrue((Path(self.tmp.name) / doc["raw_path"]).exists())  # original kept on disk, referenced by path
        labels = {p["label"] for p in self.e.s.q("SELECT label FROM passages")}
        self.assertEqual(labels, {"UNVERIFIED_EXTRACTION"})
        v = self.e.s.one("SELECT * FROM source_versions")
        self.assertEqual((v["origin_label"], v["status"], v["fixture"]), ("REAL_OFFICIAL_SOURCE", "candidate", 0))
        self.assertEqual(self.e.s.one("SELECT kind FROM cases")["kind"], "source_update")

    def test_32_retries_do_not_duplicate(self):
        self.served[entry()["url"]] = (make_pdf(LAW_PAGES), "application/pdf")
        self.kb.collect(entry())
        n = lambda t: self.e.s.one(f"SELECT COUNT(*) n FROM {t}")["n"]
        before = (n("documents"), n("passages"), n("source_versions"), n("cases"))
        self.assertEqual(self.kb.collect(entry())["outcome"], "identical")       # same bytes
        self.assertEqual(before, (n("documents"), n("passages"), n("source_versions"), n("cases")))
        pages2 = copy.deepcopy(LAW_PAGES); pages2[0].append("")                   # different bytes, same text
        self.served[entry()["url"]] = (make_pdf(pages2) + b"\n% producer comment\n", "application/pdf")
        self.assertEqual(self.kb.collect(entry())["outcome"], "identical")
        self.assertEqual(n("passages"), before[1])
        self.assertEqual(n("source_versions"), before[2])

    def test_33_empty_page_is_flagged_not_guessed(self):
        self.served[entry()["url"]] = (make_pdf([LAW_PAGES[0], [], LAW_PAGES[2], LAW_PAGES[3]]), "application/pdf")
        r = self.kb.collect(entry())
        self.assertEqual((r["extraction"], r["empty_pages"]), ("partial", [2]))
        self.assertIn("OCR not available", self.e.s.one("SELECT extraction_note FROM documents")["extraction_note"])

    def test_34_unreadable_document_is_a_recorded_failure(self):
        self.served[entry()["url"]] = (b"%PDF-1.4 this is not really a pdf", "application/pdf")
        r = self.kb.collect(entry())
        self.assertEqual(r["outcome"], "failed")
        self.assertEqual(self.e.s.one("SELECT extraction_status FROM documents")["extraction_status"], "failed")
        self.assertEqual(self.e.s.one("SELECT COUNT(*) n FROM source_versions")["n"], 0)

    def test_35_html_extraction_and_full_text_search(self):
        html_doc = ("<html><body><form><nav>Menu Home VAT Taxes Contact</nav><div class='content'>"
                    "<p>Latest news: an unrelated awareness event attracted many participants this year.</p>"
                    "<span>A business must register for VAT if the taxable supplies and imports exceed the mandatory registration threshold of AED 375,000.</span>"
                    "<p>A business may choose to register voluntarily above the voluntary registration threshold of AED 187,500.</p>"
                    "<script>var x = 'ignore';</script></div></form></body></html>").encode()
        e2 = entry(sid="TEST-PAGE", url="https://tax.gov.ae/en/test.aspx", anchor="mandatory registration threshold")
        self.served[e2["url"]] = (html_doc, "text/html")
        r = self.kb.collect(e2)
        self.assertEqual(r["outcome"], "new_version")
        texts = [p["text"] for p in self.e.s.q("SELECT text FROM passages ORDER BY seq")]
        self.assertTrue(texts[0].startswith("A business must register"))           # news before the anchor dropped
        self.assertFalse(any("var x" in t for t in texts))
        hits = self.kb.search("registration threshold")["hits"]
        self.assertTrue(hits and hits[0]["source_id"] == "TEST-PAGE")
        self.assertEqual(self.kb.search('threshold" OR passages_fts MATCH "x')["hits"][0]["source_id"], "TEST-PAGE")  # no FTS injection
        self.assertEqual(self.kb.search("")["hits"], [])

    def test_36_real_source_never_preapproved_and_never_used_unreviewed(self):
        with self.assertRaises(WorkflowError):
            self.e.ingest_source({**entry(), "text": "x", "origin_label": "REAL_OFFICIAL_SOURCE", "preapproved_fixture": True})

    def test_37_citation_support_and_interpretation_review_gate(self):
        self.served[entry()["url"]] = (make_pdf(LAW_PAGES), "application/pdf")
        self.kb.collect(entry())
        ob = {"obligation_key": "TEST-REG", "title": "Test registration", "requirement": "required",
              "support_quotes": [{"source_id": "TEST-LAW", "quote": "exceeded the Threshold over the previous 12 -month period"}],
              "conditions": {"params": {"t": 100}, "all": [{"computed": "taxable_supplies_last_12m_aed", "op": "gt", "param": "t"}]},
              "action": {"label": "Register (test)", "evidence_required": ["confirmation"]}}
        bad = dict(ob, obligation_key="TEST-BAD", support_quotes=[{"source_id": "TEST-LAW", "quote": "salaries shall be added to supplies"}])
        out = self.kb.add_interpretations([{"source_id": "TEST-LAW", "obligation": ob}, {"source_id": "TEST-LAW", "obligation": bad}])
        self.assertEqual([o["support_status"] for o in out], ["supported", "unsupported"])
        self.assertEqual(self.kb.add_interpretations([{"source_id": "TEST-LAW", "obligation": ob}])[0]["outcome"], "exists (retry-safe)")
        self.e.upsert_profile({**copy.deepcopy(PROF["noor_stage1"])})
        key = lambda k: self.e.s.one("SELECT result FROM assessments WHERE obligation_key=? AND current=1", (k,))
        self.assertIsNone(key("TEST-REG"))                                   # source not approved yet
        self.e.review_source("TEST-LAW@v1", "approve", *REV)
        self.assertIsNone(key("TEST-REG"))                                   # interpretation not reviewed yet
        self.assertEqual(self.e.review_interpretation("TEST-BAD#TEST-LAW@v1", "approve", *REV)["outcome"], "refused")
        self.assertEqual(self.e.review_interpretation("TEST-REG#TEST-LAW@v1", "approve", *REV)["status"], "reviewed")
        self.assertEqual(key("TEST-REG")["result"], "applicable")             # 320,000 > 100 (salary still excluded)
        self.assertIsNone(key("TEST-BAD"))

    def test_38_version_comparison_separates_noise_from_wording(self):
        url = entry()["url"]
        self.served[url] = (make_pdf(LAW_PAGES), "application/pdf")
        self.kb.collect(entry())
        p2 = copy.deepcopy(LAW_PAGES)
        p2 = [[ln.replace("Unofficial translation", "As published by the Ministry") for ln in pg] for pg in p2]
        p2[1][2] = "Article 2 - Registration 7"                                # footnote renumbered only
        p2[1][5] = "7 Article amended as per Test Decision No. 9 of 2026."
        p2[2][3] = "The value of taxable Goods and Services and Concerned Goods."  # wording change
        self.served[url] = (make_pdf(p2), "application/pdf")
        r = self.kb.collect(entry())
        self.assertEqual((r["outcome"], r["status"]), ("new_version", "candidate"))
        cmp_ = self.kb.compare("TEST-LAW@v1", "TEST-LAW@v2")
        ch = {row["unit"]: row["change"] for row in cmp_["rows"]}
        self.assertEqual(ch.get("Article 3"), "substantive")
        self.assertNotEqual(ch.get("Article 2"), "substantive")
        self.assertIn("concerned goods", next(r for r in cmp_["rows"] if r["unit"] == "Article 3")["new"])


class RealVatReading(unittest.TestCase):
    """Uses the draft reading's conditions (not the real source text) to check the arithmetic deterministically."""

    def test_39_art19_value_excludes_salary_and_asks_for_concerned_goods(self):
        e = Engine(Store(":memory:"), FixedClock("2026-10-16T10:00:00"))
        interp = json.loads((ROOT / "knowledge_base" / "CL_draft_interpretations.json").read_text())["interpretations"][0]["obligation"]
        e.ingest_source({"source_id": "SYN-COPY", "issuing_authority": "test copy", "authority_type": "primary", "jurisdiction": "AE",
                         "document_title": "conditions-only copy for arithmetic test", "source_url": "https://fixture.invalid/x",
                         "text": "conditions-only copy", "preapproved_fixture": True,
                         "obligations": [{k: v for k, v in interp.items() if k not in ("support_quotes",)} | {"interpretation_status": "fixture_reviewed"}]})
        p = copy.deepcopy(PROF["noor_stage1"])
        p["facts"].update(uae_place_of_residence=True)
        e.upsert_profile(p)
        res = lambda: e.s.one("SELECT result, missing_json FROM assessments WHERE obligation_key='VAT-MANDATORY-REG-REAL' AND current=1")
        self.assertEqual(res()["result"], "needs_clarification")
        self.assertIn("acquired_business_or_related_party_supplies", res()["missing_json"])
        p["facts"].update(acquired_business_or_related_party_supplies=False)
        e.upsert_profile(p)
        self.assertIn("concerned_goods_services_last_12m_aed", res()["missing_json"])
        p["facts"].update(concerned_goods_services_last_12m_aed=0)
        e.upsert_profile(p)
        self.assertEqual(res()["result"], "not_applicable")                  # 320,000 + 0, salary 60,000 excluded
        p["facts"].update(concerned_goods_services_last_12m_aed=60000)
        e.upsert_profile(p)
        self.assertEqual(res()["result"], "applicable")                      # 380,000 > 375,000 via a real Art. 19 component
        p["facts"].update(acquired_business_or_related_party_supplies=True, concerned_goods_services_last_12m_aed=0)
        e.upsert_profile(p)
        self.assertEqual(res()["result"], "needs_clarification")
        self.assertIn("reviewer_calculation_art19_3_4", res()["missing_json"])


class RealCorpusIntegration(unittest.TestCase):
    """End to end on a COPY of the real database (skipped when data/CL_compliance.sqlite3 is absent, e.g. a fresh clone)."""

    def test_43_reviewed_real_reading_drives_owner_case_on_a_copy(self):
        import shutil
        live = ROOT / "data" / "CL_compliance.sqlite3"
        if not live.exists():
            self.skipTest("main database not built; run python3 -m compliance_agent.kb setup")
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "copy.sqlite3"
            shutil.copy2(live, db)
            e = Engine(Store(db), FixedClock("2026-10-16T12:00:00"))
            kb = K.KnowledgeBase(e, Path(d), lock_path=Path(d) / "lock.json")
            self.assertEqual(kb.status()["approved_real_versions"], 0)
            p = copy.deepcopy(PROF["noor_stage1"])
            p["facts"].update(uae_place_of_residence=True)
            e.upsert_profile(p)
            key = lambda: e.s.one("SELECT result, missing_json FROM assessments WHERE obligation_key='VAT-MANDATORY-REG-REAL' AND current=1")
            self.assertIsNone(key())                                            # nothing real is used before review
            e.review_source("FTA-VAT-DL8@v1", "approve", *REV)
            self.assertIsNone(key())                                            # interpretation still a draft
            self.assertEqual(e.review_interpretation("VAT-SALARY-NOT-SUPPLY-CHECK#FTA-VAT-DL8@v1", "approve", *REV)["outcome"], "refused")
            self.assertEqual(e.review_interpretation("VAT-MANDATORY-REG-REAL#FTA-VAT-DL8@v1", "approve", *REV)["status"], "reviewed")
            self.assertEqual(key()["result"], "needs_clarification")
            p["facts"].update(concerned_goods_services_last_12m_aed=0, acquired_business_or_related_party_supplies=False)
            e.upsert_profile(p)
            self.assertEqual(key()["result"], "not_applicable")                 # salary excluded on the real reading too
            p["facts"]["ledger_last_12m"] = [{"type": "sale_of_services", "amount_aed": 390000}, {"type": "salary_cost", "amount_aed": 60000}]
            e.upsert_profile(p)
            self.assertEqual(key()["result"], "applicable")
            c = e.s.one("SELECT * FROM cases WHERE dedupe_key='BP-0001:VAT-MANDATORY-REG-REAL'")
            self.assertEqual((c["kind"], c["status"], c["due_date"]), ("obligation_action", "open", None))
            cites = json.loads(e.s.one("SELECT citations_json FROM assessments WHERE obligation_key='VAT-MANDATORY-REG-REAL' AND current=1")["citations_json"])
            self.assertEqual((cites[0]["origin_label"], cites[0]["support_status"]), ("REAL_OFFICIAL_SOURCE", "supported"))
            e.s.close()
        self.assertEqual(Store(live).one("SELECT COUNT(*) n FROM reviews")["n"], 0)  # the real database was not touched


if __name__ == "__main__":
    unittest.main()
