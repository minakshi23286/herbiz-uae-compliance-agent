"""Task 2 A-5: capability declaration (doc 16 r2 §6). Tests t2k_01-06. Synthetic only; no network.

capabilities.json validates against the frozen capability_declaration/1.0 schema, names evidence that exists, declares no
live inference, and every execution_mode the running app writes into an audit record is an ACTIVE declared class."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "contracts")); sys.path.insert(0, str(ROOT / "tests"))

import validate as V  # noqa: E402

DECL = json.loads((ROOT / "capabilities.json").read_text(encoding="utf-8"))
SCHEMA = json.loads((ROOT / "contracts" / "capability_declaration_1.0.schema.json").read_text(encoding="utf-8"))


class Capabilities(unittest.TestCase):
    def test_t2k_01_valid_against_the_frozen_contract(self):
        self.assertEqual(V.errors(SCHEMA, DECL), [])

    def test_t2k_02_evidence_exists_and_ids_are_unique(self):
        ids = [c["id"] for c in DECL["capabilities"]]
        self.assertEqual(len(ids), len(set(ids)))
        for c in DECL["capabilities"]:
            for e in c["evidence"]:
                self.assertTrue((ROOT / e).exists(), f"{c['id']}: {e}")
            if c["active"]:
                self.assertTrue(c["evidence"], c["id"])

    def test_t2k_03_no_live_inference_and_every_class_declared(self):
        live = [c for c in DECL["capabilities"] if c["class"] == "live_inference"]
        self.assertTrue(live and not any(c["active"] for c in live))
        self.assertEqual({c["class"] for c in DECL["capabilities"]},
                         {"deterministic", "recorded_model", "proxy_outputs", "live_inference", "tool_use", "simulated", "planned"})

    def test_t2k_04_metrics_carry_class_set_date_and_the_d106_figures_together(self):
        recall = [m for m in DECL["metrics"] if m["name"] == "all_required_recall_v8"]
        self.assertEqual(sorted(m["value"] for m in recall), [0.667, 0.685, 0.704])     # never one figure alone (D-106)
        self.assertTrue(any("not met" in m["set"] for m in recall))
        si = [m for m in DECL["metrics"] if m["name"] == "silent_incomplete_v8"]
        self.assertTrue(si and "by construction" in str(si[0]["value"]))
        self.assertTrue(all(m["class"] != "live_inference" for m in DECL["metrics"]))

    def test_t2k_05_audit_execution_modes_match_active_declared_classes(self):
        import test_audit_log as TA
        active = {c["class"] for c in DECL["capabilities"] if c["active"]}
        s = TA.Server()
        try:
            for _, path, body in TA.CHANNEL_CALLS:
                s.call(path, body)
            from compliance_agent import scenarios as SC
            outs, folder = SC.replay("SC-2")
            scen = [json.loads(x) for f in sorted(folder.glob("audit-*.jsonl")) for x in f.read_bytes().splitlines()]
            modes = {r["answer"]["execution_mode"] for r in s.records() + scen}
        finally:
            s.close()
        self.assertTrue(modes, "no audit records written")
        self.assertLessEqual(modes, active, f"undeclared execution modes: {modes - active}")
        self.assertNotIn("live_model", modes)

    def test_t2k_06_file_is_current(self):
        p = subprocess.run([sys.executable, str(ROOT / "experiments" / "ws_a" / "CL_build_capabilities.py"), "--check"],
                           capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
