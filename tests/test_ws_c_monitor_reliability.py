"""Monitor reliability fixes after independent QA (17 Oct 2026, findings MON-01..MON-17). SYNTHETIC fixtures only;
no network. URLs under /__SYNTHETIC_TEST__/ do not exist."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent.rag_c import monitor as M  # noqa: E402

SYN = "https://tax.gov.ae/__SYNTHETIC_TEST__/"
LAWTXT = "Article 14 - Tax Deregistration{fn}\n1. The Registrant must apply within 20 (twenty) Business Days of the occurrence (SYNTHETIC).\n" \
         "2. Further synthetic text so that the article is long enough to be meaningful for the monitor comparison.\n"


def md_obs(url, md, status=200):
    return {"url": url, "http_status": status, "content_type": "text/markdown", "body": None, "markdown": md, "via": "test",
            "error": None, "extra": {}}


def html_obs(url, html, status=200):
    return {"url": url, "http_status": status, "content_type": "text/html", "body": html.encode(), "markdown": None,
            "via": "test", "error": None, "extra": {}}


class Fake:
    def __init__(self, table):
        self.table = table

    def __call__(self, url):
        v = self.table.get(url)
        if isinstance(v, Exception):
            raise v
        if v is None:
            return {"url": url, "http_status": 404, "content_type": None, "body": None, "markdown": None, "via": "test", "error": None, "extra": {}}
        return v


DOC = {"url": SYN + "law.aspx", "kind": "document", "source_id": "SYN", "version_id": "SYN@v1", "in_scope_articles": ["14"]}
PAGE = {"url": SYN + "service.aspx", "kind": "document", "source_id": "SYN-PAGE", "in_scope_articles": [], "page_in_scope": True}
LIST = {"url": SYN + "listing.aspx", "kind": "listing", "candidate_id": "SYN-L", "source_id": None, "in_scope_articles": []}
BAD = {"url": SYN + "broken.pdf", "kind": "document", "source_id": "SYN-B", "in_scope_articles": []}


class Reliability(unittest.TestCase):
    def test_131_one_failing_item_does_not_stop_the_run(self):
        f = Fake({DOC["url"]: md_obs(DOC["url"], LAWTXT.format(fn="")), BAD["url"]: ValueError("corrupt PDF")})
        r = M.run(f, {}, items=[BAD, DOC], now="t1")
        self.assertEqual([e["status"] for e in r["events"]], ["error", "new"])
        self.assertIn("fetch_error", [a["kind"] for a in r["alerts"]])

    def test_132_already_missing_at_baseline_is_alerted_once(self):
        r1 = M.run(Fake({}), {}, items=[DOC], now="t1")
        self.assertEqual([a["kind"] for a in r1["alerts"]], ["removed"])
        r2 = M.run(Fake({}), r1["state"], items=[DOC], now="t2")
        self.assertEqual(r2["alerts"], [])
        r3 = M.run(Fake({DOC["url"]: md_obs(DOC["url"], LAWTXT.format(fn=""))}), r2["state"], items=[DOC], now="t3")
        self.assertIn("restored", [a["kind"] for a in r3["alerts"]])

    def test_133_soft_404_or_empty_page_keeps_the_baseline(self):
        r1 = M.run(Fake({DOC["url"]: md_obs(DOC["url"], LAWTXT.format(fn=""))}), {}, items=[DOC], now="t1")
        r2 = M.run(Fake({DOC["url"]: md_obs(DOC["url"], "Not found")}), r1["state"], items=[DOC], now="t2")
        self.assertEqual(r2["events"][0]["status"], "error")
        self.assertEqual(r2["state"]["urls"], {**r2["state"]["urls"]})
        key = next(iter(r2["state"]["urls"]))
        self.assertEqual(r2["state"]["urls"][key]["units"], r1["state"]["urls"][key]["units"])   # baseline kept

    def test_134_footnote_renumbering_and_page_footers_are_cosmetic(self):
        r1 = M.run(Fake({DOC["url"]: md_obs(DOC["url"], LAWTXT.format(fn="10") + "Page 3 of 12\n")}), {}, items=[DOC], now="t1")
        r2 = M.run(Fake({DOC["url"]: md_obs(DOC["url"], LAWTXT.format(fn="11") + "Page 4 of 13\n")}), r1["state"], items=[DOC], now="t2")
        self.assertEqual(r2["events"][0]["status"], "cosmetic")
        self.assertFalse([a for a in r2["alerts"] if a["severity"] == "high"])

    def test_135_web_page_paragraphs_compare_by_content_not_position(self):
        base = "<p>A business must register if supplies exceed AED 375,000 (SYNTHETIC).</p><p>Voluntary above AED 187,500 (SYNTHETIC).</p>"
        r1 = M.run(Fake({PAGE["url"]: html_obs(PAGE["url"], base)}), {}, items=[PAGE], now="t1")
        banner = "<p>New: our offices are closed on the national holiday (SYNTHETIC banner).</p>" + base
        r2 = M.run(Fake({PAGE["url"]: html_obs(PAGE["url"], banner)}), r1["state"], items=[PAGE], now="t2")
        self.assertEqual(r2["events"][0]["diff"]["added"].__len__(), 1)          # only the banner paragraph is new
        self.assertEqual(r2["events"][0]["diff"]["removed"], [])
        changed = base.replace("375,000", "400,000")
        r3 = M.run(Fake({PAGE["url"]: html_obs(PAGE["url"], changed)}), r1["state"], items=[PAGE], now="t3")
        a = [x for x in r3["alerts"] if x["kind"] == "changed_substantive_in_scope"]
        self.assertEqual((len(a), a[0]["provisions"]), (1, ["SYN-PAGE|*"]))         # in-scope page can raise a high alert

    def test_136_empty_or_js_only_listing_is_an_error_not_mass_removal(self):
        good = '<a href="/__SYNTHETIC_TEST__/Datafolder/VAT-law-synthetic.pdf">VAT law (SYNTHETIC)</a>'
        r1 = M.run(Fake({LIST["url"]: html_obs(LIST["url"], good)}), {}, items=[LIST], now="t1")
        r2 = M.run(Fake({LIST["url"]: html_obs(LIST["url"], "<div id='app'></div><script>load()</script>")}), r1["state"], items=[LIST], now="t2")
        self.assertEqual(r2["events"][0]["status"], "error")
        self.assertNotIn("removed_from_listing", [a["kind"] for a in r2["alerts"]])
        menu = good + '<a href="/__SYNTHETIC_TEST__/en/news/latest.aspx">News</a><a href="/__SYNTHETIC_TEST__/en/careers.aspx">Careers</a>'
        r3 = M.run(Fake({LIST["url"]: html_obs(LIST["url"], menu)}), r1["state"], items=[LIST], now="t3")
        self.assertEqual([a["kind"] for a in r3["alerts"]], [])                    # menu/news links are not documents

    def test_137_persistent_fetch_failure_escalates(self):
        err = {"url": DOC["url"], "http_status": 503, "content_type": None, "body": None, "markdown": None, "via": "test",
               "error": "HTTP Error 503", "extra": {}}
        state = {}
        for i in range(3):
            r = M.run(Fake({DOC["url"]: err}), state, items=[DOC], now=f"t{i}")
            state = r["state"]
        self.assertEqual(r["alerts"][0]["severity"], "high")

    def test_138_corrupt_state_is_set_aside_and_runs_are_locked(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "state.json"
            sp.write_text("{not json")
            state, warn = M.load_state(sp)
            self.assertEqual(state, {})
            self.assertIn("moved to", warn)
            self.assertTrue(list(Path(d).glob("state.corrupt-*.json")))
            with M.RunLock(sp):
                with self.assertRaises(RuntimeError):
                    with M.RunLock(sp):
                        pass
            self.assertFalse(sp.with_suffix(".lock").exists())

    def test_139_report_is_written_before_state_so_alerts_are_not_lost(self):
        r = M.run(Fake({}), {}, items=[DOC], now="t1")
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "state.json"
            with mock.patch.object(M, "report_markdown", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    M.write_outputs(r, sp, Path(d) / "reports", "2026-10-17")
            self.assertFalse(sp.exists())                                          # state not advanced
            out = M.write_outputs(r, sp, Path(d) / "reports", "2026-10-17")
            beat = json.loads(Path(out["heartbeat"]).read_text())
            self.assertEqual((beat["last_run"], beat["high_alerts"]), ("t1", 1))

    def test_140_drift_from_collected_bytes_is_alerted_on_any_run_once_per_new_bytes(self):
        item = {**DOC, "collected_sha256": "0" * 64}
        o = html_obs(item["url"], "<p>" + "Synthetic legal text about registration thresholds. " * 5 + "</p>")
        r1 = M.run(Fake({item["url"]: o}), {}, items=[item], now="t1")
        self.assertIn("differs_from_collected_version", [a["kind"] for a in r1["alerts"]])
        r2 = M.run(Fake({item["url"]: o}), r1["state"], items=[item], now="t2")
        self.assertNotIn("differs_from_collected_version", [a["kind"] for a in r2["alerts"]])


if __name__ == "__main__":
    unittest.main()


class LinkRelevance(unittest.TestCase):
    def test_161_hyphenated_mof_file_names_and_titled_links_are_not_dropped(self):
        listing = {"url": SYN + "mof-listing.aspx", "kind": "listing", "candidate_id": "SYN-L2", "source_id": None, "in_scope_articles": []}
        html = ('<a href="https://mof.gov.ae/wp-content/uploads/2027/01/Cabinet-Decision-No.-999-of-2027-SYNTHETIC.pdf">Decision (SYNTHETIC)</a>'
                f'<a href="{SYN}files/abc123.pdf">VAT Executive Regulation consolidated (SYNTHETIC)</a>'
                f'<a href="{SYN}files/menu.pdf">Annual report</a>')
        r = M.run(Fake({listing["url"]: html_obs(listing["url"], html)}), {}, items=[listing], now="t1")
        urls = sorted(p["url"] for p in r["proposals"])
        self.assertEqual(urls, sorted(["https://mof.gov.ae/wp-content/uploads/2027/01/Cabinet-Decision-No.-999-of-2027-SYNTHETIC.pdf",
                                       f"{SYN}files/abc123.pdf"]))
