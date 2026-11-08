"""Offline evaluation of C1-primary on a frozen set with PRE-RECORDED classifier outputs (no API call, no spend).

    python3 experiments/ws_b/CL_ws_b_c1p_offline_eval.py --set v8 --outputs <recorded outputs json> --source "<who produced them>" --out <file>

The recorded outputs are {question_id: {in_scope, out_of_scope_class, topics, confidence}} written by an independent agent
from the frozen classifier prompt. They are NOT Claude Haiku 5.5 outputs and say nothing about Haiku's real performance.
Compared on the same questions: deterministic v7, C1-agreement (pipeline_c1, same outputs) and C1-primary (pipeline_c1p).
Refuses to run if the C1-primary code changed after its freeze or the set changed after its freeze.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from compliance_agent.llm_lab import classifier_c1 as K1, classifier_c1p as K, freeze, pipeline_c1 as PC, pipeline_c1p as PP  # noqa: E402
from compliance_agent.llm_lab import pipeline_v7 as P7, retrieval_metrics as M, source_validity_c as SV  # noqa: E402
from compliance_agent.llm_lab.locators import key  # noqa: E402
from compliance_agent.llm_lab.retrieve import connect_ro  # noqa: E402

FREEZE = ROOT / "docs" / "CL_evidence" / "ws_b" / "CL_c1p_code_freeze.json"
EXACT = ROOT / "data" / "CL_ws_b_exact_copy.sqlite3"
OOS = ("out_of_scope", "unsupported")


def check_freeze() -> None:
    rec = json.loads(FREEZE.read_text())
    for f, h in rec["files"].items():
        if hashlib.sha256((ROOT / f).read_bytes()).hexdigest() != h:
            raise SystemExit(f"REFUSED: {f} changed after the C1-primary code freeze")


def measures(qs, recs, verified_key, cert_key=None, labels=None) -> dict:
    ev = M.evaluate(qs, lambda t, it=iter(recs): next(it)["passages"])
    rows = []
    for q, r, row in zip(qs, recs, ev["rows"]):
        req = [key(s, a) for s, a in (labels or {}).get(q["id"], q.get("required_sources", []))]
        allreq = all(P7._present(r["passages"], k) for k in req) if req else None
        v = bool(r.get(verified_key)) if verified_key != "status" else r.get("status") == "complete"
        rows.append({"id": q["id"], "category": q.get("category"), "all_required": allreq, "verified": v,
                     "certifiable": bool(r.get(cert_key)) if cert_key else None, "status": r.get("status"),
                     "legal_review": bool(q.get("needs_legal_review"))})
    wr = [x for x in rows if x["all_required"] is not None]
    full = [x for x in wr if x["all_required"]]
    oos = [x for x in rows if x["category"] in OOS]
    return {"recall": round(len(full) / max(1, len(wr)), 3), "answerable": len(wr), "any_expected": ev["summary"]["any_expected"],
            "silent_incomplete": sum(1 for x in wr if x["verified"] and not x["all_required"]),
            "silent_ids": [x["id"] for x in wr if x["verified"] and not x["all_required"]],
            "oos_verified_or_certified": sum(1 for x in oos if x["verified"] or x["certifiable"]),
            "false_incomplete": round(sum(1 for x in full if not x["verified"]) / max(1, len(full)), 3),
            "irrelevant_added": ev["summary"]["irrelevant_added_share"], "avg_passages": ev["summary"]["avg_passages"],
            "added_on_oos": sum(r["added"] for r, x in zip(ev["rows"], rows) if x["category"] in OOS),
            "certifiable": sum(1 for x in rows if x["certifiable"]) if cert_key else None,
            "misses": [x["id"] for x in wr if not x["all_required"]],
            "recall_on_legal_review_flagged": round(sum(1 for x in wr if x["legal_review"] and x["all_required"]) / max(1, sum(1 for x in wr if x["legal_review"])), 3),
            "statuses": dict(Counter(x["status"] for x in rows)), "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    ap.add_argument("--outputs", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--review", default=None, help="independent label review file (sensitivity analysis)")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    check_freeze()
    path = ROOT / "fixtures" / f"CL_llm_eval_unseen_{a.set}.json"
    freeze.verify(path)
    qs = json.loads(path.read_text())["questions"]
    recorded = json.loads(Path(a.outputs).read_text())
    con, sv = connect_ro(EXACT), SV.load(EXACT)
    if not sv.available:
        print("NOTE: Workstream C interface unavailable -> every answer fails closed:", sv.error)
    c1p = [PP.retrieve(con, q["text"], K.parse(recorded.get(q["id"], {})) if q["id"] in recorded else None, sv) for q in qs]
    names1 = {n for n, _ in K1.topic_catalogue()}

    def c1_out(qid):
        d = recorded.get(qid)
        if d is None:
            return None
        p = K.parse(d)
        if not p["ok"]:
            return {**p}
        return {**p, "topics": [t for t in p["topics"] if t in names1]}
    agree = [PC.retrieve(con, q["text"], c1_out(q["id"])) for q in qs]
    v7 = [P7.retrieve(con, q["text"]) for q in qs]
    out = {"set": a.set, "classifier_outputs": a.source, "warning": "Pre-recorded outputs from an independent agent, NOT Claude Haiku 5.5.",
           "validity_interface": {"available": sv.available, "error": sv.error, "origin": sv.origin},
           "c1_primary": measures(qs, c1p, "retrieval_verified", "answer_certifiable"),
           "c1_agreement": measures(qs, agree, "status"), "v7_only": measures(qs, v7, "status")}
    if a.review:
        rv = json.loads((ROOT / "fixtures" / a.review).read_text())
        labels = {r["id"]: r["reviewer_required"] for r in rv["reviews"] if r["verdict"] != "not_applicable"}
        out["c1_primary_reviewer_labels"] = measures(qs, c1p, "retrieval_verified", "answer_certifiable", labels=labels)
    for name in [k for k in out if k.startswith(("c1_", "v7_"))]:
        m = out[name]
        print(f'{name:28} recall={m["recall"]} any={m["any_expected"]} silent={m["silent_incomplete"]} {m["silent_ids"]} oos_verif={m["oos_verified_or_certified"]} '
              f'FI={m["false_incomplete"]} irr={m["irrelevant_added"]} P={m["avg_passages"]} oos_add={m["added_on_oos"]} cert={m["certifiable"]} miss={m["misses"]}')
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
