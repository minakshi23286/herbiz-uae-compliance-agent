"""C1-PRIMARY v2 (final cycle) paid evaluation harness (Workstream B). Same guards as the C1 harness; uses classifier_c1p + pipeline_c1p
with the Workstream C source-validity interface (fail closed). Prepared offline; refuses to run without a new approval.

Option C1 evaluation harness (Workstream B).

    Offline dry run (default; mocked API, no network, no spend):
        python3 experiments/ws_b/CL_ws_b_c1_run.py --db data/CL_ws_b_kb_copy.sqlite3 --sets v1 v2 v3 v4 v5 v6 --mock oracle
    Paid run (ONLY after the founder approves the exact item in experiments/ws_b/CL_c1_authorisation.json):
        ../CL_compliance_agent_app/.venv-llm/bin/python experiments/ws_b/CL_ws_b_c1p2_paid_run.py --db data/CL_ws_b_exact_copy.sqlite3 --sets v9 --repeats 3 --live --out docs/CL_evidence/ws_b/CL_c1p2_v9_paid_run.json

Live-run guards: authorisation file must be approved with a positive cap; hard per-run cap; worst-case reservation per call
before sending (budget.Ledger, NEW ledger file data/CL_c1_experiment.sqlite3 - never the protected experiment ledger);
stop after 3 consecutive failures; refuses if the C1 code or the v7 set changed after its freeze; authoritative DB md5 is
checked before and after. max_retries=0 (no silent repeat billing).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from compliance_agent import dbsafety  # noqa: E402
from compliance_agent.llm_lab import classifier_c1p2 as K, freeze, pipeline_c1p2 as PC, retrieval_metrics as M, source_validity_c as SV  # noqa: E402
from compliance_agent.llm_lab.budget import Ledger, worst_case  # noqa: E402
from compliance_agent.llm_lab.locators import key  # noqa: E402
from compliance_agent.llm_lab.retrieve import connect_ro, file_md5  # noqa: E402

AUTH = ROOT / "experiments" / "ws_b" / "CL_c1p2_authorisation.json"
FREEZE = ROOT / "docs" / "CL_evidence" / "ws_b" / "CL_c1p2_paid_freeze.json"
LEDGER = ROOT / "data" / "CL_c1p2_experiment.sqlite3"
PRICE = {"input": 0.10, "output": 0.50, "cache_write": 0.125, "cache_read": 0.01}   # USD per million tokens, Haiku 5.5, prompts <= 100K
CHARS_PER_TOKEN = 2.0     # measured in run c1-078891c6: about 2.2 characters per token for this prompt; 2.0 is conservative


def est_input_tokens(question: str) -> int:
    """Upper estimate of input tokens from the exact request body (system prompt + schema + question)."""
    return int(len(json.dumps(K.request(question))) / CHARS_PER_TOKEN) + 200


def load(name: str) -> list[dict]:
    path = ROOT / "fixtures" / f"CL_llm_eval_unseen_{name}.json"
    freeze.verify(path)
    d = json.loads(path.read_text(encoding="utf-8"))
    return d["questions"] if isinstance(d, dict) else d


def mock_client(kind: str):
    from compliance_agent.llm_lab import classifier_c1 as K1
    if kind == "oracle":
        return K1.FakeC1Client(K1.oracle_from_v7)
    if kind == "fail":
        return K1.FakeC1Client(lambda q: RuntimeError("mock outage"))
    if kind == "low":
        return K1.FakeC1Client(lambda q: {**K1.oracle_from_v7(q), "confidence": "low"})
    if kind == "oos":
        return K1.FakeC1Client(lambda q: {"in_scope": False, "out_of_scope_class": "not_tax", "topics": [], "confidence": "high"})
    raise SystemExit(f"unknown mock {kind}")


def check_live_preconditions(sets: list[str], repeats: int) -> dict:
    auth = json.loads(AUTH.read_text())
    if auth.get("status") != "approved" or not auth.get("approved_by") or float(auth.get("authorized_usd", 0)) <= 0:
        raise SystemExit("REFUSED: the paid C1P v2 run is not approved (experiments/ws_b/CL_c1p2_authorisation.json)")
    if sets != auth["sets"] or repeats != auth["repeats"]:
        raise SystemExit(f"REFUSED: run differs from the approved item (sets {auth['sets']}, repeats {auth['repeats']})")
    rec = json.loads(FREEZE.read_text())
    for f, h in rec["files"].items():
        if hashlib.sha256((ROOT / f).read_bytes()).hexdigest() != h:
            raise SystemExit(f"REFUSED: {f} changed after the C1 code freeze")
    return auth


def summarise(qs: list[dict], recs: list[dict]) -> dict:
    ev = M.evaluate(qs, lambda t, it=iter(recs): next(it)["passages"])
    rows = ev["rows"]
    for q, r, row in zip(qs, recs, rows):
        req = [key(s, a) for s, a in q.get("required_sources", [])]
        row.update(status=r["status"], category=q.get("category"),
                   silent_incomplete=bool(req) and row["all_required"] is False and r["status"] == "complete",
                   false_incomplete=bool(req) and row["all_required"] is True and r["status"] != "complete",
                   oos_certified=q.get("category") in ("out_of_scope", "unsupported") and (r["status"] == "complete" or bool(r.get("answer_certifiable"))),
                   answer_certifiable=bool(r.get("answer_certifiable")), source_approved=bool(r.get("source_approved")),
                   agreement=r.get("agreement"), c1=r.get("c1"))
    withreq = [r for r in rows if r["all_required"] is not None]
    full = [r for r in withreq if r["all_required"]]
    s = ev["summary"]
    s.update(silent_incomplete=sum(r["silent_incomplete"] for r in rows), false_incomplete_rate=round(sum(r["false_incomplete"] for r in full) / max(1, len(full)), 3),
             oos_certified=sum(r["oos_certified"] for r in rows), statuses=dict(Counter(r["status"] for r in rows)),
             answer_certifiable=sum(r["answer_certifiable"] for r in rows))
    return {"summary": s, "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--sets", nargs="+", default=["v1", "v2", "v3", "v4", "v5", "v6"])
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--mock", default=None)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if dbsafety.is_authoritative(a.db):
        raise SystemExit("Refused: Workstream B evaluates on a database copy only")
    if "v9" in a.sets and not a.live:
        raise SystemExit("Refused: v9 runs live only in the approved paid run (offline evaluation uses CL_ws_b_c1p2_offline_eval.py)")
    if a.live == bool(a.mock):
        raise SystemExit("Choose exactly one of --mock <kind> or --live")
    ledger = run_id = None
    if a.live:
        auth = check_live_preconditions(a.sets, a.repeats)
        import anthropic  # only inside .venv-llm
        client = anthropic.Anthropic(max_retries=0, timeout=60.0)
        ledger = Ledger(LEDGER, float(auth["authorized_usd"]), float(auth["authorized_usd"]))
        run_id = "c1-" + uuid.uuid4().hex[:8]
    else:
        client = mock_client(a.mock)
    main_db = ROOT / "data" / "CL_compliance.sqlite3"
    md5_before = file_md5(main_db) if main_db.exists() else None
    con = connect_ro(a.db)
    sv = SV.load(a.db)   # fails closed when C's interface or export is unavailable, stale or for another build
    out = {"mode": "live" if a.live else f"mock:{a.mock}", "run_id": run_id, "sets": {}}
    fails = 0
    for s in a.sets:
        qs = load(s)
        per_repeat, c1_log = [], []
        for rep in range(a.repeats):
            recs = []
            for q in qs:
                call_id = None
                if ledger:
                    call_id = ledger.reserve(run_id, f"c1:{s}:r{rep}", q["id"], "haiku", K.MODEL, worst_case(est_input_tokens(q["text"]), K.MAX_TOKENS, PRICE))
                c1 = K.classify(q["text"], client)
                if ledger:
                    u = c1["usage"] or {}
                    cost = round((u.get("input_tokens") or 0) * PRICE["input"] / 1e6 + (u.get("output_tokens") or 0) * PRICE["output"] / 1e6, 6)
                    ledger.complete(call_id, status="ok" if c1["ok"] else "error", cost_usd=cost if c1["usage"] else 0.0,
                                    latency_ms=c1["latency_ms"], input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
                                    model_returned=c1["model_returned"], stop_reason=c1["stop_reason"], error=c1["error"],
                                    parsed_json=json.dumps({k: c1[k] for k in ("in_scope", "oos_class", "topics", "confidence")}))
                fails = 0 if c1["ok"] else fails + 1
                if a.live and fails >= 3:
                    raise SystemExit("STOPPED: 3 consecutive C1 failures")
                c1_log.append({"id": q["id"], "repeat": rep, **{k: c1[k] for k in ("ok", "in_scope", "oos_class", "topics", "confidence", "latency_ms", "error")}})
                recs.append(PC.retrieve(con, q["text"], c1, sv))
            per_repeat.append(summarise(qs, recs))
        baseline = summarise(qs, [PC.retrieve(con, q["text"], None, sv) for q in qs])   # C1 disabled = deterministic v7 fallback
        by_q: dict[str, list] = {}
        for x in c1_log:
            by_q.setdefault(x["id"], []).append((tuple(sorted(x["topics"])), x["oos_class"], x["ok"]))
        lat = [x["latency_ms"] for x in c1_log if x["latency_ms"] is not None]
        out["sets"][s] = {"repeats": per_repeat, "baseline_v7": baseline, "c1_calls": c1_log,
                          "consistency": round(sum(len(set(v)) == 1 for v in by_q.values()) / max(1, len(by_q)), 3),
                          "latency_ms": {"median": statistics.median(lat) if lat else None, "max": max(lat) if lat else None}}
        for i, r in enumerate(per_repeat):
            m = r["summary"]
            print(f'{out["mode"]} {s} r{i}: any={m["any_expected"]} req={m["all_required"]} silent={m["silent_incomplete"]} oos_cert={m["oos_certified"]} '
                  f'FI={m["false_incomplete_rate"]} irr={m["irrelevant_added_share"]} P={m["avg_passages"]} oos_add={m["added_on_no_source_questions"]} st={m["statuses"]}')
        b = baseline["summary"]
        print(f'  v7-only {s}: req={b["all_required"]} silent={b["silent_incomplete"]} oos_cert={b["oos_certified"]}; consistency={out["sets"][s]["consistency"]}')
    if md5_before and file_md5(main_db) != md5_before:
        raise SystemExit("STOPPED: the main database changed during the run")
    if ledger:
        out["spent_usd"] = ledger.committed_usd()
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
