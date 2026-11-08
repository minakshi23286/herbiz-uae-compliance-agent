"""Task 2 B-6: SC-1/SC-2 decision fixtures are valid herbiz.scenario/1.0 and their expected states equal the engine's
own output (rebuilt here into a temporary folder and compared byte for byte)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments" / "ws_b"))

import CL_t2_build_scenarios as B  # noqa: E402

try:
    import jsonschema
except ImportError:
    jsonschema = None

FILES = ("CL_SC-1_decision.json", "CL_SC-2_decision.json")


class Scenarios(unittest.TestCase):
    def test_t2_b6_01_committed_fixtures_equal_engine_output(self):
        with tempfile.TemporaryDirectory() as d:
            B.build(Path(d))
            for f in FILES:
                self.assertEqual((Path(d) / f).read_bytes(), (ROOT / "fixtures" / "t2" / f).read_bytes(), f)

    def test_t2_b6_02_valid_and_named_obligations(self):
        sch = json.loads((ROOT / "contracts" / "ws_a_canonical_b4eb7bb" / "scenario_1.0.schema.json").read_text())
        for f in FILES:
            fx = json.loads((ROOT / "fixtures" / "t2" / f).read_text())
            if jsonschema:
                jsonschema.validate(fx, sch)
            for s in fx["steps"]:
                if s["expected"]["state"] is not None:
                    self.assertTrue(s["input"].get("obligation_id"), (f, s["n"]))   # R-B2 convention
                self.assertIn("deadline", s["expected"]["must_not"]) if f.startswith("CL_SC-1") else None

    def test_t2_b6_03_sc1_story(self):
        fx = json.loads((ROOT / "fixtures" / "t2" / FILES[0]).read_text())
        st = [s["expected"]["state"] for s in fx["steps"]]
        self.assertEqual(st, ["insufficient_information", "insufficient_information", "blocked_pending_legal_validation"])
        self.assertEqual(fx["steps"][1]["expected"]["must_show"][0], "fewer questions")
        self.assertIn("what you can do now", fx["steps"][2]["expected"]["must_show"])


if __name__ == "__main__":
    unittest.main()
