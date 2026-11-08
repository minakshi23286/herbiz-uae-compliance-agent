"""D10 (founder-approved 16 Oct 2026): a title-less article heading carrying a footnote marker ("Article 1 1", ER Definitions)
is split out as its own article, only when that footnote exists on the same page. Built into disposable databases only."""
from __future__ import annotations

import hashlib
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent import kb  # noqa: E402
from compliance_agent.rag_c import dryrun as D, inventory as I  # noqa: E402

RAW = ROOT / "data" / "raw"
REF = ROOT / "data" / "CL_c_readonly_copy.sqlite3"   # pre-D10 build (byte copy of the authoritative database)
ER_FILES = ["FTA-VAT-ER/b87b4c2c0a60d209.pdf", "FTA-VAT-ER/11de7a2063f2ee75.pdf", "FTA-VAT-ER/7e0882e3d6f9e4ba.pdf"]
md5 = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest()


def headings(page: str) -> list[str]:
    return [m.group(1) for m in kb.ARTICLE_RX.finditer(page) if not (m.group(4) and not kb.footnote_on_page(page, m.group(4)))]


class HeadingRule(unittest.TestCase):
    def test_103_footnoted_title_less_heading_needs_its_footnote_on_the_page(self):
        with_note = "Title One – Definitions\nArticle 1 1\nDefinitions in the Decree-Law apply.\n1 Article amended as per Cabinet Decision No. 100 of 2024.\n"
        self.assertEqual(headings(with_note), ["1"])
        without_note = "as set out in\nArticle 30 3\nof this Decision the supplier shall\n"
        self.assertEqual(headings(without_note), [])               # a wrapped reference is not a heading
        self.assertEqual(headings("Article 21 of the Decree-Law applies.\n"), [])
        self.assertEqual(headings("Article 14 – Tax Deregistration 10\ntext\n"), ["14"])   # titled headings unchanged
        self.assertEqual(headings("Article (13)\n"), ["13"])
        self.assertEqual(headings("Article 3 (bis) - Exceptions of Supplies 4\n"), ["3"])


@unittest.skipUnless(all((RAW / f).exists() for f in ER_FILES) and REF.exists(), "raw files or reference copy not present")
class RealFiles(unittest.TestCase):
    def test_104_every_er_version_now_has_article_1_and_the_decree_law_is_unchanged(self):
        for f in ER_FILES:
            locs = [u["locator"] for u in kb.extract_pdf(RAW / f)["units"]]
            nums = {int(m.group(1)) for m in (re.match(r"Article (\d+)", l) for l in locs) if m}
            with self.subTest(file=f):
                self.assertIn(1, nums)
                self.assertEqual([n for n in range(1, max(nums) + 1) if n not in nums], [])
        dl = [(u["locator"], u["text"]) for u in kb.extract_pdf(RAW / "FTA-VAT-DL8/37159c643e64ef2e.pdf")["units"]]
        con = I.connect_ro(REF)
        ref = [(r["locator"], r["text"]) for r in con.execute(
            "SELECT locator, text FROM passages WHERE doc_id = 'FTA-VAT-DL8:37159c643e64' ORDER BY seq")]
        con.close()
        self.assertEqual(dl, ref)

    def test_105_rebuild_changes_only_the_er_article_1_split_and_keeps_all_text(self):
        before = md5(REF)
        with tempfile.TemporaryDirectory() as d:
            build = Path(D.dry_run(REF, out=Path(d) / "d10.sqlite3")["kept_build"])
            diff = D.diff_builds(REF, build)
            con_a, con_b = I.connect_ro(REF), I.connect_ro(build)
            squash = lambda con, doc: re.sub(r"\s+", "", "".join(r[0] for r in con.execute(
                "SELECT text FROM passages WHERE doc_id = ? ORDER BY seq", (doc,))))
            docs = [r[0] for r in con_a.execute("SELECT doc_id FROM documents")]
            same_text = all(squash(con_a, doc) == squash(con_b, doc) for doc in docs)
            con_a.close(); con_b.close()
        er_docs = {"FTA-VAT-ER:b87b4c2c0a60", "FTA-VAT-ER:11de7a2063f2", "FTA-VAT-ER:7e0882e3d6f9"}
        self.assertEqual({tuple(k) for k in diff["only_in_reference"]}, {(doc, "Front matter, p. 2") for doc in er_docs})
        self.assertEqual({tuple(k) for k in diff["only_in_build"]}, {(doc, "Article 1, pp. 1-2") for doc in er_docs})
        self.assertEqual({tuple(k) for k in diff["text_changed"]}, {(doc, "Front matter, p. 1") for doc in er_docs})
        self.assertEqual(diff["passage_counts"], {})
        self.assertTrue(same_text)                                  # text only moves between passages; nothing lost or added
        self.assertEqual(md5(REF), before)


if __name__ == "__main__":
    unittest.main()
