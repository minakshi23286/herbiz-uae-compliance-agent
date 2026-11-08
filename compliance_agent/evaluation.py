"""Scenario evaluation for pilot preparation. Each scenario runs in a fresh in-memory engine; results are stored in the
main database (evaluation_runs / evaluation_results) so the interface and the handoff read real numbers.

    python3 -m compliance_agent.evaluation [--db data/CL_compliance.sqlite3]

Metrics (definitions in docs/CL_BASELINE_AND_METRICS.md). A naive keyword-lookup baseline runs on the same scenarios.
Nothing here measures legal accuracy: expected values come from the synthetic fixture rules.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path

from . import scenario as sc
from .clock import FixedClock, SystemClock
from .engine import Engine
from .store import Store

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "fixtures" / "CL_eval_scenarios.json"
REV = ("Evaluation runner (simulated reviewer)", "simulated reviewer", "scripted evaluation step")


def _case(e: Engine, key: str) -> dict | None:
    c = e.s.one("SELECT * FROM cases WHERE dedupe_key = ?", (f"BP-0001:{key}",))
    if c:
        c["evidence_required"] = json.loads(c["evidence_required_json"])
    return c


def run_scenario(sdef: dict, base: list[str], src: dict, prof: dict) -> dict:
    e = Engine(Store(":memory:"), FixedClock(sdef.get("clock", "2026-10-16T10:00:00")))
    for k in base:
        e.ingest_source(src[k])
    p = copy.deepcopy(prof["noor_stage1"])
    p["facts"].update(sdef.get("profile_patch", {}))
    e.upsert_profile(p)
    for step in sdef.get("then", []):
        e.clock.advance(minutes=1)
        if "source" in step:
            e.ingest_source(src[step["source"]])
        elif "approve_source" in step:
            e.review_source(step["approve_source"], "approve", *REV)
        elif "profile_patch" in step:
            p["facts"].update(step["profile_patch"])
            e.upsert_profile(p)
        elif "evidence" in step:
            key, reqs = step["evidence"]
            e.submit_evidence(_case(e, key)["case_id"], [{"requirement": r, "description": "synthetic.pdf", "provided": True} for r in reqs])
        elif "review" in step:
            key, decision = step["review"]
            e.review_case(_case(e, key)["case_id"], decision, *REV)
    assessments = {a["obligation_key"]: a for a in e.s.q("SELECT * FROM assessments WHERE profile_id='BP-0001' AND current=1")}
    checks = []
    for key, want in sdef.get("expect", {}).items():
        got = assessments.get(key, {}).get("result")
        checks.append((f"result {key}", want, got))
    for key, (kind, status) in sdef.get("expect_cases", {}).items():
        c = _case(e, key)
        checks.append((f"case {key}", f"{kind}/{status}", f"{c['kind']}/{c['status']}" if c else None))
    for key in sdef.get("expect_no_case", []):
        checks.append((f"no case {key}", None, _case(e, key) and _case(e, key)["case_id"]))
    for key, n in sdef.get("expect_evidence_count", {}).items():
        c = _case(e, key)
        checks.append((f"evidence items {key}", n, len(c["evidence_required"]) if c else None))
    for key, d in sdef.get("expect_due", {}).items():
        c = _case(e, key)
        checks.append((f"due date {key}", d, c and c["due_date"]))
    if "expect_case_total" in sdef:
        checks.append(("case total", sdef["expect_case_total"], e.s.one("SELECT COUNT(*) n FROM cases")["n"]))
    if "expect_resolved" in sdef:
        checks.append(("resolved cases", sdef["expect_resolved"], e.s.one("SELECT COUNT(*) n FROM cases WHERE status='resolved'")["n"]))
    failed = [c for c in checks if c[1] != c[2]]
    results = [a["result"] for a in assessments.values() if not a["obligation_key"].endswith(":upcoming")]
    cases = e.s.q("SELECT * FROM cases WHERE profile_id = 'BP-0001'")
    expected_case_keys = set(sdef.get("expect_cases", {})) | {k for k, v in sdef.get("expect", {}).items() if v in ("applicable", "conflict", "stale_evidence", "needs_clarification")}
    cited = [json.loads(a["citations_json"]) for a in assessments.values() if a["result"] == "applicable"]
    out = {
        "scenario_id": sdef["id"], "category": sdef["category"], "passed": not failed,
        "expected": json.dumps([[c[0], c[1]] for c in checks]), "actual": json.dumps([[c[0], c[2]] for c in checks]),
        "note": "; ".join(f"{c[0]}: expected {c[1]!r}, got {c[2]!r}" for c in failed) or sdef["description"],
        "n_assessments": len(results), "n_clarify": results.count("needs_clarification"),
        "n_escalated": sum(1 for c in cases if c["status"] == "escalated"),
        "n_unexpected_cases": sum(1 for c in cases if c["obligation_key"] in set(sdef.get("expect_no_case", []))),
        "n_open_cases": sum(1 for c in cases if c["status"] in ("open", "escalated", "awaiting_review")),
        "n_applicable": len(cited), "n_applicable_with_citation": sum(1 for c in cited if c),
        "n_applicable_supported": sum(1 for c in cited if c and all(x.get("support_status") == "supported" for x in c)),
        "baseline": baseline(sdef, e),
    }
    e.s.close()
    return out


def baseline(sdef: dict, e: Engine) -> dict:
    """Naive 'search and read' stand-in: an obligation applies if any word from the business activity or licensing
    context appears in the approved source text. It cannot say 'needs clarification' or 'conflict'."""
    prof = e.latest_profile("BP-0001")["facts"]
    words = {w for v in (prof.get("activity"), prof.get("licensing_context"), " ".join(prof.get("activity_tags") or []))
             if v for w in re.findall(r"[a-z]{4,}", str(v).replace("_", " ").lower())}
    rows = e.s.q("SELECT o.obligation_key, v.text FROM obligations o JOIN source_versions v ON v.version_id=o.version_id WHERE v.status='approved'")
    guess = {}
    for r in rows:
        hit = any(w in r["text"].lower() for w in words)
        guess[r["obligation_key"]] = "applicable" if hit or guess.get(r["obligation_key"]) == "applicable" else "not_applicable"
    exp = {k: v for k, v in sdef.get("expect", {}).items() if not k.endswith(":upcoming")}
    agree = sum(1 for k, v in exp.items() if guess.get(k.split(":")[0]) == v)
    return {"agree": agree, "total": len(exp)}


def run_all(db_path: str | None = None, clock=None, allow_authoritative: bool = False) -> dict:
    if db_path:
        from .dbsafety import refuse_authoritative
        refuse_authoritative(db_path, allow_authoritative, "the scenario evaluation")   # checked before any work
    defs = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    src, prof = sc.load_fixtures()
    rows = [run_scenario(s, defs["base_sources"], src, prof) for s in defs["scenarios"]]
    tot = lambda k: sum(r[k] for r in rows)
    metrics = {
        "scenarios": len(rows), "passed": sum(r["passed"] for r in rows), "failed": sum(not r["passed"] for r in rows),
        "clarification_rate": round(tot("n_clarify") / max(1, tot("n_assessments")), 3),
        "escalated_cases": tot("n_escalated"), "unexpected_cases_false_alerts": tot("n_unexpected_cases"),
        "open_cases_at_end": tot("n_open_cases"),
        "applicable_with_citation": f"{tot('n_applicable_with_citation')}/{tot('n_applicable')}",
        "applicable_with_quote_found_in_source": f"{tot('n_applicable_supported')}/{tot('n_applicable')}",
        "baseline_keyword_lookup_agreement": f"{sum(r['baseline']['agree'] for r in rows)}/{sum(r['baseline']['total'] for r in rows)}",
        "engine_expected_result_agreement": None,
        "basis": "synthetic fixtures; expected values written by software, not a domain reviewer",
    }
    res_checks = [json.loads(r["expected"]) for r in rows]
    act_checks = [json.loads(r["actual"]) for r in rows]
    n_res = sum(1 for ex in res_checks for c in ex if c[0].startswith("result "))
    ok_res = sum(1 for ex, ac in zip(res_checks, act_checks) for c, d in zip(ex, ac) if c[0].startswith("result ") and c[1] == d[1])
    metrics["engine_expected_result_agreement"] = f"{ok_res}/{n_res}"
    if db_path:
        e = Engine(Store(db_path), clock or SystemClock())
        rid = f"EVAL-{e.now().replace(':', '').replace('-', '')[:15]}-{e._next_id('RUN')}"
        with e.s.db:
            e.s.db.execute("INSERT INTO evaluation_runs VALUES (?,?,?,?,?,?)",
                           (rid, e.now(), "CL_eval_scenarios.json", metrics["passed"], metrics["failed"], json.dumps(metrics)))
            for r in rows:
                e.s.db.execute("INSERT INTO evaluation_results VALUES (?,?,?,?,?,?,?)",
                               (rid, r["scenario_id"], r["category"], r["expected"], r["actual"], int(r["passed"]), r["note"]))
            e._audit("evaluation", "evaluation_run", "evaluation", rid, {"passed": metrics["passed"], "failed": metrics["failed"]})
        e.s.close()
        metrics["run_id"] = rid
    return {"metrics": metrics, "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None, help="database to store the run in (default: the test workspace copy)")
    ap.add_argument("--write-authoritative", action="store_true",
                    help="explicit override: allow storing the run in data/CL_compliance.sqlite3 (reviewer-approved only)")
    a = ap.parse_args(argv)
    from .dbsafety import AuthoritativeDatabaseError, ensure_workspace
    db = a.db or str(ensure_workspace())
    try:
        out = run_all(db, allow_authoritative=a.write_authoritative)
    except AuthoritativeDatabaseError as ex:
        print(ex)
        return 2
    print(f"stored in: {db}")
    for r in out["rows"]:
        print(f"{'PASS' if r['passed'] else 'FAIL'} {r['scenario_id']} {r['category']}: {r['note']}  (baseline {r['baseline']['agree']}/{r['baseline']['total']})")
    print(json.dumps(out["metrics"], indent=1))
    return 0 if out["metrics"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
