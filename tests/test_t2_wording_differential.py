"""Task 2 B-5 (T2-D6, D-098): differential proof that the t2-ws-b engine differs from the frozen fdbe131 engine ONLY in
two owner-facing sentences ("We need more information..." / "We can't answer this yet..." -> "HerBiz ...").

The frozen engine is exported with `git archive fdbe131` into a temporary folder and both engines run in separate
processes over every fixture profile, under both policies, with no validity data and a fixed date. Every state,
reason, deadline, document list and field must be identical once those two sentences are mapped old -> new.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FROZEN = "fdbe131"
OLD_NEW = [
    ("We need more information before we can say whether this may apply.",
     "HerBiz needs more information before it can say whether this may apply."),
    ("We can't answer this yet: the rule or its official sources have not been validated by a qualified reviewer.",
     "HerBiz can't answer this yet: the rule or its official sources have not been validated by a qualified reviewer."),
]
RUN = r"""
import datetime as dt, json, sys
sys.path.insert(0, sys.argv[1])
from compliance_agent.obligations import engine as E
out = {}
for path in sys.argv[3:]:
    for p in json.load(open(path))["profiles"]:
        for pol in E.POLICIES:
            r = E.assess(p, None, dt.date(2026, 10, 17), pol)
            r["owner_rows"] = [E.owner_row(x) for x in r["obligations"]]
            out[p["profile_id"] + "|" + pol] = r
print(json.dumps(out, sort_keys=True, ensure_ascii=False))
"""
PROFILE_FILES = ["fixtures/obligations/CL_synthetic_profiles_360.json", "fixtures/obligations/CL_ct_demo_personas_wsc.json"]


def run(root: Path) -> str:
    files = [str(ROOT / f) for f in PROFILE_FILES]
    return subprocess.run([sys.executable, "-I", "-c", RUN, str(root), "x", *files], capture_output=True, text=True,
                          check=True, timeout=120).stdout


class WordingDifferential(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{FROZEN}^{{commit}}"]).returncode != 0:
            raise unittest.SkipTest(f"frozen commit {FROZEN} not in this repository")
        cls.tmp = tempfile.TemporaryDirectory()
        tar = subprocess.run(["git", "-C", str(ROOT), "archive", FROZEN, "compliance_agent"], capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(tar)) as t:
            t.extractall(cls.tmp.name, filter="data")
        cls.old = run(Path(cls.tmp.name))
        cls.new = run(ROOT)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_t2_b5_01_only_the_two_sentences_differ(self):
        mapped = self.old
        for old, new in OLD_NEW:
            mapped = mapped.replace(old, new)
        self.assertEqual(json.loads(mapped), json.loads(self.new))

    def test_t2_b5_02_both_sentences_actually_changed_and_no_we_left(self):
        for old, new in OLD_NEW:
            self.assertIn(old, self.old)
            self.assertNotIn(old, self.new)
            self.assertIn(new, self.new)
        for key, r in json.loads(self.new).items():
            for row in r["owner_rows"]:
                self.assertNotRegex(row["owner_text"], r"\b[Ww]e\b", key)

    def test_t2_b5_03_states_reasons_deadlines_documents_identical(self):
        old, new = json.loads(self.old), json.loads(self.new)
        self.assertEqual(sorted(old), sorted(new))
        self.assertGreaterEqual(len(new), 16)   # 8 profiles x 2 policies
        for k in old:
            for a, b in zip(old[k]["obligations"], new[k]["obligations"]):
                for f in ("id", "state", "state_chip", "reason", "rule_status", "deadline", "documents", "why",
                          "missing_information", "sources", "label", "draft_indication", "already_done"):
                    self.assertEqual(a[f], b[f], (k, a["id"], f))
            self.assertEqual(old[k]["summary"], new[k]["summary"], k)


if __name__ == "__main__":
    unittest.main()
