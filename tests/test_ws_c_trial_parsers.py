"""Regression tests for the parser and alert fixes made during the Firecrawl trial (17 Oct 2026). All inputs are small
synthetic strings shaped like the real FTA / UAE Legislation portal markdown; nothing is fetched."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent.rag_c import discovery as D, firecrawl_trial as F, monitor as M, validity as V  # noqa: E402

DB = ROOT / "data" / "CL_c_readonly_copy.sqlite3"


class TrimMain(unittest.TestCase):
    def test_171_footer_cut_without_h1(self):
        md = "#### Article (87) Entry\nThis Decree-Law shall come into force.\nTranslated in cooperation with X\nThe site was last updated on 1 Oct"
        out = F.trim_main(md)
        self.assertTrue(out.endswith("come into force.\n"))
        self.assertNotIn("Translated", out)

    def test_171b_h1_start_and_earliest_footer(self):
        md = "nav\n# Title\nbody\nThe site was last updated on X\n## Did you find this content useful?"
        self.assertEqual(F.trim_main(md), "# Title\nbody\n")


class ListingEntries(unittest.TestCase):
    def test_172_na_issue_date_and_missing_publish_date(self):
        md = ("\n\nCabinet Decision No. 153 of 2025 on Metal Scrap\n\nIssue Date : NA\n\nCabinet Decisions\n\n"
              "[![pdf](icon.png)\\\\\nPDF 1MB](https://tax.gov.ae/Datafolder/a.pdf)"
              "\n\n2026-04 - VAT - Life Insurance\n\nNew\n\nIssue Date : Jul 1, 2026\n\nPublish Date : Jul 9, 2026\n\nDecisions\n\n"
              "[![pdf](icon.png)\\\\\nPDF](https://tax.gov.ae/Datafolder/b.pdf)")
        e = F.fta_listing_entries(md)
        self.assertEqual([x["url"] for x in e], ["https://tax.gov.ae/Datafolder/a.pdf", "https://tax.gov.ae/Datafolder/b.pdf"])
        self.assertIsNone(e[0]["issue_date_shown"]); self.assertIsNone(e[0]["publish_date_shown"])
        self.assertEqual((e[1]["issue_date_shown"], e[1]["publish_date_shown"]), ("Jul 1, 2026", "Jul 9, 2026"))


class PortalHeadings(unittest.TestCase):
    def test_173_md_heading_bis_without_dash(self):
        md = "intro\n#### Article (54) Reverse Charge\ntext A\n#### Article (54) BIS\ntext B\n#### Article (55)\ntext C"
        u = M._markdown_units(md)
        self.assertEqual([k for k in u if k != "Front matter"], ["Article 54", "Article 54 (bis)", "Article 55"])
        self.assertIn("text B", u["Article 54 (bis)"]); self.assertNotIn("\n", "Article 54 (bis)")

    def test_173b_reference_in_body_is_not_a_heading(self):
        u = M._markdown_units("#### Article (1)\nsee Article (2) of this Law\n#### Article (2)\nx")
        self.assertEqual(sorted(k for k in u if k.startswith("Article")), ["Article 1", "Article 2"])


class Discovery(unittest.TestCase):
    def test_174_title_attribute_and_size_label(self):
        md = '[![pdf](i.png)\\\\\n2 MB](https://tax.gov.ae/f/VATP047.pdf "VATP047 - Reverse Charge on Metal Scrap.pdf")'
        e = D.parse_listing(md, "https://tax.gov.ae/en/x.aspx", "markdown")
        self.assertEqual(e[0]["title"], "VATP047 - Reverse Charge on Metal Scrap")

    def test_175_other_taxes_filtered_vat_kept(self):
        entries = [{"url": "https://tax.gov.ae/f/a.pdf", "title": "Cabinet Decision No. 137 of 2026 on Excise Price for Tobacco"},
                   {"url": "https://tax.gov.ae/f/b.pdf", "title": "Cabinet Decision No. 153 of 2025 on VAT reverse charge"}]
        p = D.propose(entries, listing_url="https://tax.gov.ae/en/legislation.aspx", observed_at="2026-10-17")
        self.assertEqual([x["url"] for x in p["proposals"]], ["https://tax.gov.ae/f/b.pdf"])
        self.assertEqual(p["skipped"].get("other_tax"), 1)


@unittest.skipUnless(DB.exists(), "read-only DB copy missing")
class SourceChangedIssues(unittest.TestCase):
    AL = {"kind": "changed_substantive_in_scope", "url": "https://x.test/dl8", "at": "2026-10-18T06:00:00+04:00",
          "provisions": ["FTA-VAT-DL8|13"], "detail": "Article 13", "source_id": "FTA-VAT-DL8", "version_id": None}

    def _changed(self, alerts):
        return [i for i in V.build_validity(DB, as_of="2026-10-18", alerts=alerts)["issues"] if i["kind"] == "source_changed"]

    def test_176_unreviewed_change_blocks_reviewed_does_not(self):
        self.assertEqual([i["provisions"] for i in self._changed([self.AL])], [["FTA-VAT-DL8|13"]])
        self.assertEqual(self._changed([dict(self.AL, reviewed=True)]), [])

    def test_177_no_article_means_whole_source_and_noise_kinds_ignored(self):
        whole = dict(self.AL, provisions=[])
        self.assertEqual(self._changed([whole])[0]["provisions"], ["FTA-VAT-DL8|*"])
        self.assertEqual(self._changed([dict(self.AL, kind="new_document_on_listing")]), [])


if __name__ == "__main__":
    unittest.main()
