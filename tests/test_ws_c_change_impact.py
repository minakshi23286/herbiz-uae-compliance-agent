"""Founder demonstration (17 Oct 2026): detect a source change -> identify the affected legal article -> flag previously
generated answers that rely on it -> produce a review alert -> keep the unreviewed change from becoming certified knowledge.

Steps 1-2 use REAL data: the official UAE Legislation portal text of DL 8/2017 scraped with Firecrawl (founder-approved
trial, 17 Oct 2026), saved under data/monitor/ (git-ignored; the test skips if it is absent). The change itself is
SYNTHETIC: Art. 13(1)(b) "(30) thirty days" is edited to "(60) sixty days" in a COPY of that snapshot, because no
official text changed during the trial. Steps 3-5 run on copies of the knowledge base and the experiment ledger."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent.rag_c import citations as T, interface as I, monitor as M, validity as V  # noqa: E402

SNAP = ROOT / "data" / "monitor" / "firecrawl" / "phase3" / "snap2" / "dl8.json"
DB = ROOT / "data" / "CL_c_readonly_copy.sqlite3"
LEDGER = ROOT / "data" / "CL_llm_experiment.sqlite3"
EVIDENCE = ROOT / "docs" / "CL_evidence" / "ws_c" / "firecrawl" / "CL_change_impact_demo_2026-10-17.json"
URL = "https://uaelegislation.gov.ae/en/legislations/1227"
ITEM = {"url": URL, "kind": "document", "source_id": "FTA-VAT-DL8", "version_id": "UAELEG-DL8-2017 (portal)",
        "in_scope_articles": ["1", "13", "14", "15", "17", "19", "21", "22", "23", "24"]}


@unittest.skipUnless(SNAP.exists() and DB.exists() and LEDGER.exists(), "real portal snapshot, DB copy or ledger copy missing")
class ChangeImpact(unittest.TestCase):
    def test_170_detect_identify_flag_alert_block(self):
        real = json.loads(SNAP.read_text(encoding="utf-8"))
        md = real["data"]["markdown"]
        old = "will exceed the Mandatory Registration Threshold during the next (30) thirty days"
        self.assertIn(old, md)                                              # the real official wording, as scraped
        with tempfile.TemporaryDirectory() as d:
            base, changed = Path(d) / "base", Path(d) / "changed"
            base.mkdir(); changed.mkdir()
            (base / "dl8.json").write_text(json.dumps(real), encoding="utf-8")
            syn = json.loads(json.dumps(real))
            syn["data"]["markdown"] = md.replace(old, old.replace("(30) thirty", "(60) sixty"), 1)
            syn["data"]["SYNTHETIC_CHANGE"] = "Art. 13(1)(b): (30) thirty days -> (60) sixty days (test only; not the law)"
            (changed / "dl8.json").write_text(json.dumps(syn), encoding="utf-8")

            # 1. detect the change, 2. identify the affected article
            r1 = M.run(M.FirecrawlImport(base), {}, items=[ITEM], now="2026-10-17T12:00:00+04:00")
            r2 = M.run(M.FirecrawlImport(changed), r1["state"], items=[ITEM], now="2026-10-18T06:00:00+04:00")
            ev = r2["events"][0]
            self.assertEqual((ev["status"], ev["diff"]["substantive"]), ("changed", ["Article 13"]))   # only Art. 13, of 87
            alert = next(a for a in r2["alerts"] if a["kind"] == "changed_substantive_in_scope")
            self.assertEqual((alert["severity"], alert["provisions"]), ("high", ["FTA-VAT-DL8|13"]))

        # 3. flag previously generated answers that rely on that article
        before = V.build_validity(DB, as_of="2026-10-18")
        after = V.build_validity(DB, as_of="2026-10-18", alerts=r2["alerts"])
        changed_issue = next(i for i in after["issues"] if i["kind"] == "source_changed")
        self.assertEqual(changed_issue["provisions"], ["FTA-VAT-DL8|13"])
        t_before = T.trace_ledger(LEDGER, DB, before)
        t_after = T.trace_ledger(LEDGER, DB, after)
        flagged = [a for a in t_after["rows"] if changed_issue["id"] in a["validity_issues"]]
        self.assertGreater(len(flagged), 0)
        self.assertEqual(t_after["answers_by_issue"][changed_issue["id"]], len(flagged))

        # 4. review alert (the monitor's high alert above) + 5. the unreviewed change cannot be certified,
        #    even in a world where every version had been approved
        approved_world = json.loads(json.dumps(after))
        for v in approved_world["versions"]:
            v["approved"] = True
        lab13 = I.answer_label(approved_world, "complete", [("FTA-VAT-DL8", "Article 13, p. 11", "FTA-VAT-DL8@v1")])
        self.assertFalse(lab13["certified"])
        self.assertIn("source_changed", {b["reason"] for b in lab13["blockers"]})
        self.assertIn("changed recently", lab13["user_wording"])
        # after a person reviews the alert, the change no longer blocks (other blockers - here G3 partial scope - remain)
        reviewed = [dict(a, reviewed=True) for a in r2["alerts"]]
        after_review = V.build_validity(DB, as_of="2026-10-18", alerts=reviewed)
        self.assertFalse([i for i in after_review["issues"] if i["kind"] == "source_changed"])

        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps({
            "real_data": {"source": URL, "scraped": "2026-10-17 (Firecrawl, founder-approved trial)", "articles_compared": ev["units"],
                          "official_wording_checked": old},
            "synthetic_change": syn["data"]["SYNTHETIC_CHANGE"],
            "step1_detected": {"status": ev["status"], "substantive_units": ev["diff"]["substantive"]},
            "step2_affected_provision": alert["provisions"], "step4_alert": {k: alert[k] for k in ("severity", "kind", "detail")},
            "step3_answers": {"recorded_answers": t_after["answers"], "flagged_by_this_change": len(flagged),
                              "example_question_ids": sorted({a["question_id"] for a in flagged})[:10]},
            "step5_block": {"certified": lab13["certified"], "reasons": sorted({b["reason"] for b in lab13["blockers"]}),
                            "user_wording": lab13["user_wording"]},
            "after_review_source_changed_issues": 0}, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
