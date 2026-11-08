"""Firecrawl trial planner and post-run verifier. No Firecrawl call is made (the planner cannot make one)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent.rag_c import firecrawl_trial as F, monitor as M  # noqa: E402


class Trial(unittest.TestCase):
    def test_154_plan_stays_within_the_15_credit_cap_and_uses_safe_options(self):
        p = F.plan()
        self.assertLessEqual(p["worst_case_credits"], 15)
        self.assertTrue(all(not c["url"].lower().endswith(".pdf") for c in p["calls"]))
        self.assertTrue(all(F.check_options(c["options"]) == [] for c in p["calls"]))
        self.assertEqual(sum(1 for c in p["calls"] if "uaelegislation" in c["url"]), 1)   # the 403-prone site once only
        with self.assertRaises(ValueError):
            F.plan(runs=3)
        self.assertTrue(F.check_options({**F.OPTIONS, "proxy": "stealth"}))
        self.assertTrue(F.check_options({**F.OPTIONS, "formats": ["markdown", "json"]}))
        committed = json.loads((ROOT / "docs" / "rag" / "templates" / "CL_firecrawl_trial_plan.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, json.loads(json.dumps(p)))

    def test_155_verification_catches_unplanned_scrapes_and_overspend_then_feeds_the_monitor(self):
        p = F.plan()
        run1 = [c for c in p["calls"] if c["run"] == 1]
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for i, c in enumerate(run1):
                md = "## Article 14 - Tax Deregistration\nSYNTHETIC listing text for the trial verifier. " * 3
                (d / f"{i:02d}.json").write_text(json.dumps({"data": {"markdown": md, "links": [],
                    "metadata": {"sourceURL": c["url"], "statusCode": 200, "creditsUsed": 1}, "changeTracking": {"changeStatus": "new"}}}))
            ok = F.verify_results(d, p, 1)
            self.assertTrue(ok["within_plan"], ok)
            self.assertEqual((ok["missing"], ok["unplanned"]), ([], []))
            items = [{"url": c["url"], "kind": "document", "source_id": "TRIAL", "in_scope_articles": []} for c in run1]
            r = M.run(M.FirecrawlImport(d), {}, items=items, now="2026-10-18T06:00:00+04:00")
            self.assertEqual(r["status_counts"], {"new": len(run1)})
            (d / "99.json").write_text(json.dumps({"url": "https://tax.gov.ae/en/not-planned.aspx", "metadata": {"creditsUsed": 5}}))
            bad = F.verify_results(d, p, 1)
            self.assertFalse(bad["within_plan"])
            self.assertEqual(bad["unplanned"], ["https://tax.gov.ae/en/not-planned.aspx"])


if __name__ == "__main__":
    unittest.main()
