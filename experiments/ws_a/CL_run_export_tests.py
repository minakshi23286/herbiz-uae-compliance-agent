"""Run the HerBiz test suite and explain every result that is not a plain pass (HerBiz 360 submission export).

    python3 experiments/ws_a/CL_run_export_tests.py                    # the public manifest (tests/MANIFEST_PUBLIC.json)
    python3 experiments/ws_a/CL_run_export_tests.py --manifest all     # every test, with reasons for what cannot run here
    python3 experiments/ws_a/CL_run_export_tests.py --manifest all --json out.json   # per-test outcomes (builds the manifests)

Counting (A-7, founder-approved runner fix): TESTS and FAILURE RECORDS are reported separately. One test with several
failing sub-cases is one failed test but several failure records.

Public-manifest guard (A-7): while the public manifest runs, an audit hook records every file open (including attempts on
absent files) and SQLite connect on a restricted path: the databases and the experiment ledger, raw official files, the
held-back recorded answers, the held-back article table, and sibling WS B / WS C checkouts.
  --guard strict (default): any such read fails that test with RESTRICTED_READ. This is the mode for the clean export copy,
                            where it decides whether the public results stand.
  --guard report:           the development repository, where those files exist: several public tests deliberately use the
                            real data when it is present (stronger private checks) and pass without it. They are listed as
                            an inventory, not failed.
The hook sees this process only, not subprocesses a test starts.

The export ships no database (see README). In `--manifest all`, tests that need one SKIP with a stated reason, and a few
Workstream B tests FAIL instead; they are listed by name, reported, and never counted as passed.
"""
from __future__ import annotations

import argparse
import collections
import os
import io
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
PUBLIC_MANIFEST = TESTS / "MANIFEST_PUBLIC.json"

NEEDS_PRIVATE_COPY = {
    "test_obligations.Validity.test_20_pinned_export_loads_on_exact_copy": "WS B: needs data/CL_ws_b_exact_copy.sqlite3 (byte copy of the protected database)",
    "test_obligations.Validity.test_23_real_vat_provisions_not_certified_today": "WS B: needs data/CL_ws_b_exact_copy.sqlite3 (byte copy of the protected database)",
    "test_obligations.SafetyAndData.test_45_db_copies_unchanged": "WS B: checks the private database copies are unchanged",
    "test_obligations.CorporateTaxDemo.test_82_wsc_labels_attached_never_approved": "WS B: loads WS C labels with `git archive` from a sibling WS C checkout (../CL_compliance_agent_app_ws_c); the app itself uses the vendored copy",
}
MISSING_MARKERS = ("No such file or directory", "validity_unavailable", "not found",
                   "pinned WS-C artifacts unavailable", "CL_compliance_agent_app_ws_c")      # no sibling WS C checkout
# Held back from the export (official article text; reuse terms unconfirmed). While it is absent, Workstream B's offline
# classifier and retrieval-v7 tests that load it fail; each must name the file, except test_c1_02, whose classifier
# fails closed (returns "not ok") when the table cannot be loaded.
HELD_FILE = "compliance_agent/llm_lab/data/CL_article_index_v6.json"
HELD_FAIL_CLOSED = {"test_c1.Request.test_c1_02_every_failure_is_not_ok"}
RESTRICTED_FILES = {ROOT / HELD_FILE, ROOT / "fixtures" / "mvp360" / "CL_recorded_vat_answers.json"}


def restricted(path) -> str | None:
    """Why a path may not be read by a public test, or None."""
    if not isinstance(path, (str, bytes, Path)) or path in ("", b"", ":memory:"):
        return None
    try:
        s = os.fsdecode(path)
        if s.startswith("file:"):
            s = s[5:].split("?")[0]
        s = os.path.normpath(os.path.abspath(s))                  # no file-system access
    except Exception:
        return None
    rp = Path(s)
    data = str(ROOT / "data") + "/"
    if s.startswith(data) and (s.endswith((".sqlite3", ".sqlite", ".db")) or s.startswith(data + "raw/")):
        return "database, ledger or raw official file under data/"
    if rp in RESTRICTED_FILES:
        return "held-back file"
    sib = str(ROOT.parent) + "/"
    if s.startswith(sib) and not s.startswith(str(ROOT) + "/") and Path(s[len(sib):]).parts[:1] and \
            Path(s[len(sib):]).parts[0].startswith("CL_compliance_agent_app"):
        return "sibling checkout"
    return None


class GuardedResult(unittest.TextTestResult):
    """Tracks the running test so the audit hook can attribute restricted reads to it."""
    current: str | None = None
    violations: dict = collections.defaultdict(set)
    armed = False

    def startTest(self, test):
        GuardedResult.current = test.id()
        super().startTest(test)

    def stopTest(self, test):
        super().stopTest(test)
        GuardedResult.current = None


def _hook(event, args):
    if not GuardedResult.armed or GuardedResult.current is None:
        return
    if event in ("open", "sqlite3.connect") and args:
        why = restricted(args[0])
        if why:
            GuardedResult.violations[GuardedResult.current].add(f"{why}: {args[0]}")


def load(manifest: str) -> tuple[unittest.TestSuite, list[str] | None]:
    sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(TESTS))
    if manifest == "all":
        return unittest.defaultTestLoader.discover(str(TESTS), top_level_dir=str(TESTS)), None
    path = PUBLIC_MANIFEST if manifest == "public" else TESTS / "MANIFEST_INTERNAL.json"
    ids = json.loads(path.read_text(encoding="utf-8"))["tests"]
    return unittest.defaultTestLoader.loadTestsFromNames(ids), ids


def parent_id(t) -> str:
    return t.test_case.id() if hasattr(t, "test_case") else t.id()        # a failing sub-case belongs to its test


def run(manifest: str, json_out: str | None = None, guard: str = "strict") -> int:
    suite, ids = load(manifest)
    everything = [t.id() for t in _flatten(suite)]                  # before running: a run empties the suite
    if manifest == "public":
        sys.addaudithook(_hook)
        GuardedResult.armed = True
    stream = io.StringIO()
    res = unittest.TextTestRunner(stream=stream, verbosity=0, resultclass=GuardedResult).run(suite)
    GuardedResult.armed = False
    def expand(tid: str) -> list[str]:
        """A class- or module-level fixture result ("setUpClass (mod.Class)") applies to every test under it."""
        m = re.match(r"^(setUpClass|tearDownClass|setUpModule|tearDownModule) \((.+)\)$", tid)
        if not m:
            return [tid]
        return [i for i in everything if i.startswith(m.group(2) + ".")] or [tid]

    records = [(parent_id(t), t.id(), tb) for t, tb in res.failures + res.errors]
    by_test = collections.OrderedDict()
    for pid, _, tb in records:
        for i in expand(pid):
            by_test.setdefault(i, []).append(tb)
    if guard == "strict":
        for tid, v in GuardedResult.violations.items():              # guard failures count as failures of that test
            by_test.setdefault(tid, []).append("RESTRICTED_READ: " + "; ".join(sorted(v)))
    held_absent = not (ROOT / HELD_FILE).exists()
    held = [i for i, tbs in by_test.items() if manifest != "public" and held_absent and i not in NEEDS_PRIVATE_COPY
            and (any(Path(HELD_FILE).name in tb for tb in tbs) or i in HELD_FAIL_CLOSED)]
    known = [i for i in by_test if manifest != "public" and i in NEEDS_PRIVATE_COPY]
    unexpected = [i for i in by_test if i not in known and i not in held]
    wrong_reason = [i for i in known if not any(m in tb for tb in by_test[i] for m in MISSING_MARKERS)]
    skipped = {}
    for t, reason in res.skipped:
        for i in expand(t.id()):
            if i not in by_test:
                skipped[i] = reason
    passed = len([i for i in everything if i not in by_test and i not in skipped])
    n_records = len(records) + (sum(1 for v in GuardedResult.violations.values() if v) if guard == "strict" else 0)
    print(f"Manifest: {manifest}" + (f" ({len(ids)} tests listed)" if ids is not None else ""))
    print(f"Tests: {len(everything)} | passed: {passed} | skipped: {len(skipped)} | "
          f"need a private copy (not runnable here): {len(known)} | need the held-back table: {len(held)} | "
          f"other failures: {len(unexpected)}")
    print(f"Failure records: {n_records} (one test can have several; counted separately from tests)")
    if manifest == "public":
        nv = len(GuardedResult.violations)
        print(f"Restricted-file guard ({guard}): " + ("clean" if not nv else f"{nv} test(s) read restricted files"
              + (" (failed)" if guard == "strict" else " where present (inventory below; each passes without them in the export)")))
        if guard == "report" and nv:
            for tid, v in sorted(GuardedResult.violations.items()):
                kinds = sorted({x.split(":")[0] for x in v})
                print(f"  - {tid}: {', '.join(kinds)}")
    if skipped:
        print("\nSkipped, by stated reason:")
        for reason, n in collections.Counter(skipped.values()).most_common():
            print(f"  {n:4d}  {reason}")
    if known:
        print("\nNot runnable in this export (fail because a private file is absent; reported, not counted as passed):")
        for i in known:
            last = [ln for ln in by_test[i][0].strip().splitlines() if ln.strip()][-1][:160]
            print(f"  - {i}\n      why: {NEEDS_PRIVATE_COPY[i]}\n      error: {last}")
    if held:
        print(f"\nNeed the held-back table {HELD_FILE} (not in this export; see README). Reported, not counted as passed:")
        for i in held:
            print(f"  - {i}")
    for i in unexpected:
        print(f"\nFAILED: {i}\n" + "\n".join(by_test[i]))
    if wrong_reason:
        print("\nFAILED for a different reason than a missing private file:", wrong_reason)
    if json_out:
        out = {}
        for tid in everything:
            if tid in by_test:
                cat = "needs_private_copy" if tid in known else ("needs_held_table" if tid in held else "failed")
                out[tid] = {"outcome": cat, "reason": NEEDS_PRIVATE_COPY.get(tid) or (f"needs {HELD_FILE}" if tid in held else "failed")}
            elif tid in skipped:
                out[tid] = {"outcome": "skipped", "reason": skipped[tid]}
            else:
                out[tid] = {"outcome": "passed", "reason": None}
        Path(json_out).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return 0 if not unexpected and not wrong_reason else 1


def _flatten(s):
    for t in s:
        if isinstance(t, unittest.TestSuite):
            yield from _flatten(t)
        else:
            yield t


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", choices=["public", "internal", "all"], default="public" if PUBLIC_MANIFEST.exists() else "all")
    ap.add_argument("--json", default=None, help="write per-test outcomes here")
    ap.add_argument("--guard", choices=["strict", "report"], default="strict")
    a = ap.parse_args(argv)
    return run(a.manifest, a.json, a.guard)


if __name__ == "__main__":
    raise SystemExit(main())
