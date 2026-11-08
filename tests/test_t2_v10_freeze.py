"""Task 2 B-0: the independent holdout set v10 is frozen by sha256 (structure checks only; question text is not inspected)."""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V10 = ROOT / "fixtures" / "CL_llm_eval_unseen_v10.json"
LOCK = ROOT / "fixtures" / "CL_llm_eval_unseen_v10.FROZEN.json"


class V10Freeze(unittest.TestCase):
    def test_t2_b0_01_hash_matches_lock(self):
        self.assertEqual(hashlib.sha256(V10.read_bytes()).hexdigest(), json.loads(LOCK.read_text())["sha256"])

    def test_t2_b0_02_coverage_minimums(self):
        qs = json.loads(V10.read_text())["questions"]
        cats = [q["category"] for q in qs]
        self.assertEqual(len(qs), 30)
        self.assertGreaterEqual(cats.count("paraphrase"), 5)
        self.assertGreaterEqual(cats.count("out_of_scope"), 3)
        self.assertGreaterEqual(sum(len(q["required_sources"]) >= 2 for q in qs), 3)
        self.assertGreaterEqual(sum(any(s == "FTA-VAT-DL8" and a in ("48", "74") for s, a in q["required_sources"]) for q in qs), 2)
        self.assertTrue(all(q["required_sources"] == [] for q in qs if q["category"] == "out_of_scope"))


if __name__ == "__main__":
    unittest.main()
