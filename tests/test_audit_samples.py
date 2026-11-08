"""Task 2 A-7: the shipped sample audit logs (docs/360/evidence/audit-logs/) verify and are scanner-clean. Tests t2e_01-02.
Runs in the public export: it needs no database."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "contracts"))

from compliance_agent import audit_log as AL, audit_sanitizer as S  # noqa: E402
import validate as V  # noqa: E402

FOLDER = ROOT / "docs" / "360" / "evidence" / "audit-logs"
SCHEMA = json.loads((ROOT / "contracts" / "audit_record_1.0.schema.json").read_text(encoding="utf-8"))


class Samples(unittest.TestCase):
    def test_t2e_01_chain_intact_scan_clean_every_record_valid_and_sanitized(self):
        files = sorted(FOLDER.glob("audit-*.jsonl"))
        self.assertTrue(files)
        for f in files:
            self.assertTrue(AL.verify(f)[0], f.name)
            for line in f.read_bytes().splitlines():
                rec = json.loads(line)
                self.assertEqual(V.errors(SCHEMA, rec), [])
                self.assertEqual(S.check(rec), [])
                self.assertNotIn('"text"', line.decode("utf-8"))
        self.assertEqual(AL.scan(FOLDER), [])

    def test_t2e_02_every_owner_channel_and_scenario_is_sampled(self):
        recs = [json.loads(x) for f in sorted(FOLDER.glob("audit-*.jsonl")) for x in f.read_bytes().splitlines()]
        self.assertEqual({r["channel"] for r in recs}, {"ask", "dashboard", "ct", "finance", "change_replay", "scenario"})
        modes = {r["answer"]["mode"] for r in recs if r["channel"] == "ask"}
        self.assertTrue({"recorded", "no_recording", "blocked"} <= modes, modes)
        blocked = [r for r in recs if r["answer"]["mode"] == "blocked"]
        self.assertTrue(all(r["request"]["query_text"] is None and r["request"]["query_sha256"] is None for r in blocked))
        self.assertTrue(any(r["retrieval"] and r["retrieval"]["retrieval_version"] == "v8" for r in recs))


if __name__ == "__main__":
    unittest.main()
