"""Workstream C source discovery and change monitoring, on SYNTHETIC fixtures generated here (no network) and on the
local raw copies of the real FTA files. URLs under /__SYNTHETIC_TEST__/ do not exist; their text is invented."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent.rag_c import discovery as DI, monitor as M  # noqa: E402

SYN = "https://tax.gov.ae/__SYNTHETIC_TEST__/"
LAW = SYN + "synthetic-vat-law.pdf"
LISTING = SYN + "legislation-listing.aspx"
GONE = SYN + "synthetic-guide-to-be-removed.pdf"
FC_URL = SYN + "synthetic-service-page.aspx"

try:
    import fitz  # PyMuPDF, already installed; used only to make synthetic PDFs
except ImportError:  # pragma: no cover
    fitz = None

ARTICLES_V1 = {
    "7": "Article 7 - Mandatory Registration\n1. The Mandatory Registration Threshold shall be AED 375,000 (SYNTHETIC).",
    "14": "Article 14 - Tax Deregistration\n1. The Registrant must apply within 20 (twenty) Business Days (SYNTHETIC).",
    "30": "Article 30 - Place of Supply\n1. Synthetic text about the place of supply.",
}


def make_pdf(path: Path, articles: dict[str, str]) -> None:
    doc = fitz.open()
    for text in articles.values():
        page = doc.new_page()
        page.insert_text((72, 72), "SYNTHETIC TEST DOCUMENT - NOT LAW", fontsize=9)
        page.insert_text((72, 110), text, fontsize=11)
    doc.save(str(path))
    doc.close()


def listing_html(links: list[tuple[str, str]]) -> str:
    rows = "".join(f'<li><a href="{u}">{t}</a> Issue date: Sep 01, 2026 Publish date: Sep 10, 2026</li>' for u, t in links)
    return f"<html><body><h1>Legislation (SYNTHETIC)</h1><ul>{rows}</ul></body></html>"


def write_day(folder: Path, files: dict[str, tuple[str, bytes | str]]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    index = {}
    for i, (url, (name, body)) in enumerate(files.items()):
        (folder / name).write_bytes(body if isinstance(body, bytes) else body.encode())
        index[url] = {"file": name, "status": 200}
    (folder / "index.json").write_text(json.dumps(index), encoding="utf-8")


ITEMS = [{"url": LAW, "kind": "document", "source_id": "SYN-LAW", "version_id": "SYN-LAW@v1", "in_scope_articles": ["14"]},
         {"url": GONE, "kind": "document", "source_id": "SYN-GUIDE", "version_id": None, "in_scope_articles": []},
         {"url": LISTING, "kind": "listing", "candidate_id": "SYN-LISTING", "source_id": None, "in_scope_articles": []}]
VALIDITY = {"issues": [{"id": "conflict:syn", "kind": "conflict", "provisions": ["SYN-LAW|14"]}]}


@unittest.skipUnless(fitz is not None, "PyMuPDF not available to build synthetic PDFs")
class MonitorOnSyntheticFixtures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        v1, v2 = d / "law_v1.pdf", d / "law_v2.pdf"
        make_pdf(v1, ARTICLES_V1)
        v2_articles = dict(ARTICLES_V1)
        v2_articles["14"] = v2_articles["14"].replace("20 (twenty)", "30 (thirty)")                       # substantive
        v2_articles["7"] = v2_articles["7"].replace("shall be AED", "shall  be\nAED")                      # layout only
        make_pdf(v2, v2_articles)
        self.law_v1, self.law_v2 = v1.read_bytes(), v2.read_bytes()
        guide = b"%PDF-1.4 synthetic"  # unreadable on purpose is fine: day 2 removes it
        make_pdf(d / "guide.pdf", {"1": "Article 1 - Synthetic guide\ntext"})
        day1_links = [(SYN + "vat-decree-law-amendment-synthetic.pdf", "VAT Decree-Law amendment (SYNTHETIC)"),
                      (SYN + "old-vat-guide-synthetic.pdf", "VAT guide (SYNTHETIC)")]
        day2_links = [day1_links[0], (SYN + "VATP099-synthetic-clarification.pdf", "VAT Public Clarification VATP099 (SYNTHETIC)"),
                      (SYN + "careers.aspx", "Careers at the authority"), ("https://example.com/vat-news.pdf", "VAT news elsewhere")]
        write_day(d / "day1", {LAW: ("law.pdf", self.law_v1), GONE: ("guide.pdf", (d / "guide.pdf").read_bytes()),
                               LISTING: ("listing.html", listing_html(day1_links))})
        write_day(d / "day2", {LAW: ("law.pdf", self.law_v2), LISTING: ("listing.html", listing_html(day2_links))})
        self.d = d
        self.r1 = M.run(M.FixtureFetcher(d / "day1"), {}, items=ITEMS, now="2026-10-17T06:00:00+04:00", validity=VALIDITY)
        self.r2 = M.run(M.FixtureFetcher(d / "day2"), self.r1["state"], items=ITEMS, now="2026-10-18T06:00:00+04:00", validity=VALIDITY)

    def tearDown(self):
        self.tmp.cleanup()

    def kinds(self, r):
        return sorted(a["kind"] for a in r["alerts"])

    def test_106_first_run_records_baseline_without_change_alerts(self):
        self.assertEqual(self.r1["status_counts"], {"new": 3})
        self.assertNotIn("changed_substantive_in_scope", self.kinds(self.r1))
        self.assertEqual(self.r1["activation"], "none (monitoring never activates or collects sources)")

    def test_107_substantive_in_scope_change_is_high_and_names_the_provision(self):
        ev = next(e for e in self.r2["events"] if e["url"] == LAW)
        self.assertEqual(ev["status"], "changed")
        self.assertEqual(ev["diff"]["substantive"], ["Article 14"])
        self.assertIn("Article 7", ev["diff"]["cosmetic"])                     # layout-only change is not substantive
        a = next(a for a in self.r2["alerts"] if a["kind"] == "changed_substantive_in_scope")
        self.assertEqual((a["severity"], a["provisions"]), ("high", ["SYN-LAW|14"]))

    def test_108_change_to_a_conflicted_provision_raises_its_own_alert(self):
        self.assertIn("conflict_provision_changed", self.kinds(self.r2))

    def test_109_removed_document_and_listing_changes_are_detected(self):
        self.assertEqual(next(e for e in self.r2["events"] if e["url"] == GONE)["status"], "removed")
        self.assertIn("removed", self.kinds(self.r2))
        self.assertIn("removed_from_listing", self.kinds(self.r2))
        props = self.r2["proposals"]
        self.assertEqual([p["url"] for p in props], [SYN + "VATP099-synthetic-clarification.pdf"])   # careers / other host skipped
        p = props[0]
        self.assertEqual((p["activated"], p["kb_status"], p["verification_status"]), (False, "not_ingested", "pending_verification"))
        self.assertTrue(p["evidence"].startswith("observed_listing_only"))
        self.assertEqual(p["dates_shown_on_listing"], {"issue_date_shown": "Sep 01, 2026", "publish_date_shown": "Sep 10, 2026"})

    def test_110_unchanged_rerun_is_quiet(self):
        r3 = M.run(M.FixtureFetcher(self.d / "day2"), self.r2["state"], items=ITEMS, now="2026-10-19T06:00:00+04:00")
        self.assertEqual(r3["status_counts"].get("changed", 0), 0)
        self.assertEqual([a for a in r3["alerts"] if a["severity"] in ("high", "medium")], [])   # removed is reported once

    def test_111_outputs_are_atomic_and_never_overwrite_a_report(self):
        out = self.d / "out"
        a = M.write_outputs(self.r2, out / "state.json", out / "reports", "2026-10-18")
        b = M.write_outputs(self.r2, out / "state.json", out / "reports", "2026-10-18")
        self.assertNotEqual(a["report"], b["report"])
        self.assertTrue(Path(a["report"]).read_text().startswith("# HerBiz: Compliance Agent — source monitoring report"))
        self.assertFalse((out / "state.tmp").exists())
        self.assertIn("SYN-LAW\\|14", Path(a["report"]).read_text())


class FirecrawlImportAndSafety(unittest.TestCase):
    def test_112_firecrawl_results_are_verified_locally_and_disagreement_is_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            md1 = "# Synthetic service page (SYNTHETIC)\n## Article 14 – Tax Deregistration\nApply within 20 business days.\n"
            md2 = md1.replace("20 business days", "30 business days")
            (d / "a").mkdir(); (d / "b").mkdir()
            (d / "a" / "r.json").write_text(json.dumps({"data": {"markdown": md1, "metadata": {"sourceURL": FC_URL, "statusCode": 200},
                                                                  "changeTracking": {"changeStatus": "new"}}}))
            (d / "b" / "r.json").write_text(json.dumps({"markdown": md2, "metadata": {"sourceURL": FC_URL, "statusCode": 200},
                                                        "changeTracking": {"changeStatus": "same"}}))
            items = [{"url": FC_URL, "kind": "document", "source_id": "SYN-PAGE", "in_scope_articles": ["14"]}]
            r1 = M.run(M.FirecrawlImport(d / "a"), {}, items=items, now="2026-10-17T06:00:00+04:00")
            r2 = M.run(M.FirecrawlImport(d / "b"), r1["state"], items=items, now="2026-10-18T06:00:00+04:00")
            ev = r2["events"][0]
            self.assertEqual((ev["status"], ev["diff"]["substantive"], ev["firecrawl_disagrees"]), ("changed", ["Article 14"], "same"))
            missing = M.run(M.FirecrawlImport(d / "a"), {}, items=[{"url": SYN + "not-scraped.aspx", "kind": "document"}])
            self.assertEqual(missing["events"][0]["status"], "error")

    def test_113_local_fetcher_needs_explicit_network_approval(self):
        with self.assertRaises(PermissionError):
            M.LocalFetcher()
        with mock.patch("compliance_agent.kb.urllib.request.urlopen", side_effect=AssertionError("network used")) as net:
            with self.assertRaises(PermissionError):
                M.run(M.LocalFetcher(), {}, items=ITEMS)
        net.assert_not_called()

    def test_114_discovery_url_normalisation_and_known_sources(self):
        self.assertEqual(DI.norm_url("https://TAX.gov.ae//Datafolder/Files/A%20B.pdf/"), DI.norm_url("https://www.tax.gov.ae/Datafolder/Files/A B.pdf"))
        reg = json.loads((ROOT / "knowledge_base" / "CL_source_register.json").read_text(encoding="utf-8"))
        known = DI.known_urls(reg)
        for s in reg["sources"]:
            for v in s["versions"]:
                self.assertIn(DI.norm_url(v["url"]), known)
        out = DI.propose([{"url": reg["sources"][0]["versions"][0]["url"], "title": "VAT law", "context": ""}])
        self.assertEqual((out["proposals"], out["skipped"]["known"]), ([], 1))

    def test_115_adding_proposals_bumps_the_register_and_keeps_everything_inactive(self):
        reg_path = ROOT / "knowledge_base" / "CL_source_register.json"
        before = hashlib.md5(reg_path.read_bytes()).hexdigest()
        prop = DI.propose([{"url": SYN + "VATP099-synthetic.pdf", "title": "VATP099 (SYNTHETIC)", "context": ""}], reg_path, LISTING, "2026-10-17")
        new = DI.add_proposals(reg_path, prop["proposals"] * 2, "2026-10-17")
        old = json.loads(reg_path.read_text(encoding="utf-8"))
        self.assertEqual(len(new["candidates"]), len(old["candidates"]) + 2)
        ids = [c["candidate_id"] for c in new["candidates"]]
        self.assertEqual(len(ids), len(set(ids)))                                  # duplicate ids are renamed
        self.assertNotEqual(new["register_version"], old["register_version"])
        self.assertTrue(all(c["activated"] is False for c in new["candidates"]))
        self.assertEqual(hashlib.md5(reg_path.read_bytes()).hexdigest(), before)    # add_proposals never writes the file


@unittest.skipUnless((ROOT / "data" / "raw").exists(), "data/raw not present")
class MonitorOnRealRegister(unittest.TestCase):
    def test_116_registered_versions_served_from_local_copies_match_the_lock(self):
        lock = json.loads((ROOT / "knowledge_base" / "CL_collected_lock.json").read_text(encoding="utf-8"))
        items = [i for i in M.watchlist() if i["kind"] == "document" and i.get("version_id")]
        self.assertEqual(len(items), len(lock["documents"]))
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            idx = {}
            for i, doc in enumerate(lock["documents"]):
                (d / f"{i}.bin").write_bytes((ROOT / "data" / doc["raw_path"]).read_bytes())
                idx[doc["url"]] = {"file": f"{i}.bin"}
            (d / "index.json").write_text(json.dumps(idx))
            r = M.run(M.FixtureFetcher(d), {}, items=items, now="2026-10-17T06:00:00+04:00")
            self.assertFalse(any(e.get("differs_from_collected_version") for e in r["events"]))
            # serve the 2024 ER file at the 2026 URL: the monitor must say the served bytes differ from the collected ones
            er26 = next(doc for doc in lock["documents"] if doc["url"].endswith("09-2026.pdf"))
            er24 = next(doc for doc in lock["documents"] if "04 10 2024" in doc["url"])
            (d / "swap.bin").write_bytes((ROOT / "data" / er24["raw_path"]).read_bytes())
            idx[er26["url"]] = {"file": "swap.bin"}
            (d / "index.json").write_text(json.dumps(idx))
            r2 = M.run(M.FixtureFetcher(d), r["state"], items=items, now="2026-10-18T06:00:00+04:00")
            ev = next(e for e in r2["events"] if e["url"] == er26["url"])
            self.assertTrue(ev["differs_from_collected_version"])
            self.assertEqual(ev["status"], "changed")
            self.assertTrue(ev["diff"]["substantive"])


if __name__ == "__main__":
    unittest.main()
