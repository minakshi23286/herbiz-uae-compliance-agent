"""Task 2 A-7: public / internal test manifests and the restricted-file guard. Tests t2m_01-07.

Every test is in the internal manifest exactly once; the public manifest is a subset; every test left out of it is listed
with a reason; the guard flags reads of databases, the ledger, raw official files, held-back files and sibling checkouts."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "ws_a"))

import CL_run_export_tests as R  # noqa: E402

INTERNAL = json.loads((ROOT / "tests" / "MANIFEST_INTERNAL.json").read_text(encoding="utf-8"))
PUBLIC = json.loads((ROOT / "tests" / "MANIFEST_PUBLIC.json").read_text(encoding="utf-8"))


class Manifests(unittest.TestCase):
    def test_t2m_01_internal_lists_every_discovered_test_once(self):
        import CL_build_test_manifests as B
        found = B.discover()
        self.assertEqual(len(INTERNAL["tests"]), len(set(INTERNAL["tests"])))
        self.assertEqual(sorted(INTERNAL["tests"]), found, "regenerate the manifests (A-7 runbook)")

    def test_t2m_02_public_is_a_subset_and_every_exclusion_has_a_reason(self):
        pub, internal = set(PUBLIC["tests"]), set(INTERNAL["tests"])
        self.assertLessEqual(pub, internal)
        excl = {e["id"]: e for e in PUBLIC["excluded"]}
        self.assertEqual(set(excl), internal - pub)
        for e in excl.values():
            self.assertTrue(e["reason"] and e["outcome"] in ("skipped", "needs_private_copy", "needs_held_table"), e)

    def test_t2m_03_guard_flags_restricted_paths_only(self):
        for p in (ROOT / "data" / "CL_compliance.sqlite3", ROOT / "data" / "CL_llm_experiment.sqlite3",
                  "file:" + str(ROOT / "data" / "CL_compliance.sqlite3") + "?mode=ro", ROOT / "data" / "raw" / "x.pdf",
                  ROOT / R.HELD_FILE, ROOT / "fixtures" / "mvp360" / "CL_recorded_vat_answers.json",
                  ROOT.parent / "CL_compliance_agent_app_ws_c" / "x.json"):
            self.assertIsNotNone(R.restricted(str(p)), p)
        for p in (ROOT / "compliance_agent" / "web.py", ROOT / "tests" / "fixtures" / "CL_synthetic_vat_answers.json",
                  "/tmp/x/w.sqlite3", ":memory:", 7):
            self.assertIsNone(R.restricted(p if isinstance(p, int) else str(p)), p)

    def test_t2m_04_guard_attributes_a_read_to_the_running_test(self):
        R.GuardedResult.violations.clear()
        R.GuardedResult.armed, R.GuardedResult.current = True, "probe.Test.test_x"
        try:
            R._hook("open", (str(ROOT / "data" / "CL_compliance.sqlite3"), "rb", 0))
            R._hook("sqlite3.connect", (str(ROOT / "compliance_agent" / "web.py"),))
        finally:
            R.GuardedResult.armed, R.GuardedResult.current = False, None
        self.assertEqual(list(R.GuardedResult.violations), ["probe.Test.test_x"])
        R.GuardedResult.violations.clear()

    def test_t2m_05_public_manifest_names_no_test_that_needs_a_private_or_held_file(self):
        pub = set(PUBLIC["tests"])
        self.assertFalse(pub & set(R.NEEDS_PRIVATE_COPY))
        self.assertFalse(pub & R.HELD_FAIL_CLOSED)

    def test_t2m_06_readme_counts_match_the_manifests(self):
        export = (ROOT / "CL_EXPORT_FILE_MANIFEST.json").exists()           # in the export the README is at the root
        readme = (ROOT / "README.md" if export else ROOT / "docs" / "360" / "export" / "CL_EXPORT_README.md").read_text(encoding="utf-8")
        self.assertIn(f"the {PUBLIC['count']} tests that run in this repository", readme)
        self.assertIn(f"runs all {INTERNAL['count']} tests", readme)
        self.assertIn(f"| Public manifest | {PUBLIC['count']} |", readme)

    def test_t2m_07_architecture_figure_matches_the_evidence(self):
        # rc3 item 2 (DEF-T2-03): the exported figure carries no stale metric and states what the manifests and D-106 state
        import re
        svg = (ROOT / "docs" / "360" / "submission" / "CL_HERBIZ360_ARCHITECTURE.svg").read_text(encoding="utf-8")
        text = " ".join(re.sub("<[^>]+>", " ", m) for m in re.findall(r"<text[^>]*>.*?</text>", svg, re.S))
        for stale in ("44%", "80%", "Prototype"):
            self.assertNotIn(stale, text)
        for need in ("66.7", "70.4", "68.5", "37/54", "target 70% not met", "live_model, evaluated offline 18 Oct 2026",
                     "None (declared off)", f"{PUBLIC['count']}/{PUBLIC['count']} public tests"):
            self.assertIn(need, text, need)
        self.assertTrue((ROOT / "docs" / "360" / "submission" / "CL_HERBIZ360_ARCHITECTURE.png").exists())


if __name__ == "__main__":
    unittest.main()
