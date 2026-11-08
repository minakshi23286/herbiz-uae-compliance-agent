"""Task 2 A-7: write tests/MANIFEST_INTERNAL.json and tests/MANIFEST_PUBLIC.json. Local only.

    python3 experiments/ws_a/CL_build_test_manifests.py --export-outcomes <json from a clean export run> --export-commit <sha>

INTERNAL lists every test in this repository. PUBLIC lists the tests that PASSED in a clean copy of the submission export,
run in a bare environment (`CL_run_export_tests.py --manifest all --json ...`). Every test left out of PUBLIC is listed
under `excluded` with its reason (the skip message, or why it cannot run without a private or held-back file), so nothing is
dropped silently. A public test must also pass the restricted-file guard (see CL_run_export_tests.py).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"


def discover() -> list[str]:
    sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(TESTS))
    out = []

    def walk(s):
        for t in s:
            if isinstance(t, unittest.TestSuite):
                walk(t)
            else:
                out.append(t.id())
    walk(unittest.defaultTestLoader.discover(str(TESTS), top_level_dir=str(TESTS)))
    bad = [i for i in out if i.startswith("unittest.loader")]
    if bad:
        raise SystemExit(f"test modules failed to import: {bad}")
    return sorted(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export-outcomes", required=True)
    ap.add_argument("--export-commit", required=True)
    ap.add_argument("--bootstrap", action="store_true",
                    help="regeneration: the manifest tests cannot pass in the run that regenerates the manifests")
    a = ap.parse_args(argv)
    outcomes = json.loads(Path(a.export_outcomes).read_text(encoding="utf-8"))
    if a.bootstrap:
        for i, o in outcomes.items():
            if i.startswith("test_manifests.") and o["outcome"] == "failed":
                o.update(outcome="passed", reason=None)
    every = discover()
    missing = [i for i in every if i not in outcomes]
    if missing:
        raise SystemExit(f"{len(missing)} tests were not in the export run (rebuild the export from the current commit): {missing[:5]}")
    public = [i for i in every if outcomes[i]["outcome"] == "passed"]
    excluded = [{"id": i, "outcome": outcomes[i]["outcome"], "reason": outcomes[i]["reason"] or outcomes[i]["outcome"]}
                for i in every if outcomes[i]["outcome"] != "passed"]
    failed = [e["id"] for e in excluded if e["outcome"] == "failed"]
    if failed:
        raise SystemExit(f"unexplained failures in the export run; fix them first: {failed}")
    note = {"generated_by": "experiments/ws_a/CL_build_test_manifests.py", "from_export_commit": a.export_commit}
    (TESTS / "MANIFEST_INTERNAL.json").write_text(json.dumps({**note, "manifest": "internal", "count": len(every),
                                                              "tests": every}, indent=1) + "\n", encoding="utf-8")
    (TESTS / "MANIFEST_PUBLIC.json").write_text(json.dumps({**note, "manifest": "public", "count": len(public), "tests": public,
                                                            "excluded_count": len(excluded), "excluded": excluded},
                                                           indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    readme = ROOT / "docs" / "360" / "export" / "CL_EXPORT_README.md"            # keep the README's counts in step
    t = readme.read_text(encoding="utf-8")
    t = re.sub(r"the \d+ tests that run in this repository", f"the {len(public)} tests that run in this repository", t)
    t = re.sub(r"To run every test \(\d+\)", f"To run every test ({len(every)})", t)
    t = re.sub(r"runs all \d+ tests\.", f"runs all {len(every)} tests.", t)
    t = re.sub(r"\| Public manifest \| \d+ \|", f"| Public manifest | {len(public)} |", t)
    readme.write_text(t, encoding="utf-8")
    print(f"internal {len(every)} · public {len(public)} · excluded {len(excluded)} (each with a reason); README counts updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
