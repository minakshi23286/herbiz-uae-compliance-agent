"""Task 2 (WS-B) retrieval evaluation: one protocol for every method (offline, read-only DB copy, zero spend).

Metrics per set: all-required, any-expected, silent-incomplete (doc 16 r2 §1: completeness says complete_for_map
while an independently labelled required article is missing), out-of-scope handling, irrelevant share, passages per
question. Every metric carries its class (deterministic / proxy_outputs).

Development sets v1–v9 only. The holdout v10 is REFUSED unless --final is given AND the B-4 code_freeze record
matches the files on disk (no tuning on v10; it runs once).
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
from compliance_agent import dbsafety  # noqa: E402
from compliance_agent.llm_lab import freeze, retrieval_metrics as M  # noqa: E402
from compliance_agent.llm_lab.retrieve import connect_ro  # noqa: E402

DEV_SETS = ["v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9"]
HOLDOUT = "v10"
FREEZE_RECORD = ROOT / "docs" / "CL_evidence" / "ws_b" / "t2" / "CL_t2_code_freeze.json"
OOS = ("out_of_scope", "unsupported")


def load(name: str) -> list[dict]:
    path = ROOT / "fixtures" / f"CL_llm_eval_unseen_{name}.json"
    freeze.verify(path)
    d = json.loads(path.read_text(encoding="utf-8"))
    return d["questions"] if isinstance(d, dict) else d


def method(name: str):
    """Returns fn(con, question) -> {"passages", "completeness": complete_for_map|incomplete|unknown, "scope": in_scope|out_of_scope}."""
    if name == "v5_search":                     # the current demo path: passages only, no completeness claim
        from compliance_agent.llm_lab import retrieve as R
        return "deterministic", lambda con, q: {"passages": R.search(con, q["text"]), "completeness": "unknown", "scope": "in_scope"}
    if name == "v7":
        from compliance_agent.llm_lab import pipeline_v7 as P
        def f(con, q):
            r = P.retrieve(con, q["text"])
            return {"passages": r["passages"], "scope": "out_of_scope" if r["status"] == "out_of_scope" else "in_scope",
                    "completeness": "complete_for_map" if r["status"] == "complete" else ("unknown" if r["status"] == "out_of_scope" else "incomplete")}
        return "deterministic", f
    if name == "v8":
        from compliance_agent.llm_lab import retrieve_v8 as V8
        def g(con, q):
            r = V8.retrieve(con, q["text"])
            # retrieval_metrics counts every added_by != "bm25" as an added passage: map the contract code back
            items = [dict(i, added_by="bm25" if i["added_by"] == "lexical_search" else i["added_by"]) for i in r["items"]]
            return {"passages": items, "completeness": r["completeness"]["status"], "scope": r["scope"]["class"]}
        return "deterministic", g
    if name == "c1p2_proxy":                     # C1-primary v2 replayed with PROXY classifier outputs (agent-written; not a model)
        from compliance_agent.llm_lab import classifier_c1p2 as K, pipeline_c1p2 as PP, source_validity_c as SV
        rec = {}
        for s in ("v8", "v9"):
            f = ROOT / "docs" / "CL_evidence" / "ws_b" / f"CL_{s}_proxy_classifier_outputs.json"
            rec.update(json.loads(f.read_text(encoding="utf-8")))
        sv = SV.load(ROOT / "data" / "CL_ws_b_exact_copy.sqlite3")
        def h(con, q):
            if q["id"] not in rec:
                raise SystemExit(f"c1p2_proxy: no recorded proxy output for {q['id']} (proxy outputs exist for v8 and v9 only)")
            r = PP.retrieve(con, q["text"], K.parse(rec[q["id"]]), sv)
            oos = r.get("status") == "out_of_scope"
            return {"passages": r["passages"], "scope": "out_of_scope" if oos else "in_scope",
                    "completeness": "complete_for_map" if r.get("retrieval_verified") else ("unknown" if oos else "incomplete")}
        return "proxy_outputs", h
    raise SystemExit(f"unknown method {name}")


def evaluate(con, qs: list[dict], fn) -> dict:
    recs = [fn(con, q) for q in qs]
    ev = M.evaluate(qs, lambda t, it=iter(recs): next(it)["passages"])
    rows = []
    for q, rec, row in zip(qs, recs, ev["rows"]):
        has_req = bool(q.get("required_sources"))
        row.update(category=q.get("category"), completeness=rec["completeness"], scope=rec["scope"],
                   silent_incomplete=has_req and row["all_required"] is False and rec["completeness"] == "complete_for_map")
        rows.append(row)
    s = ev["summary"]
    withreq = [r for r in rows if r["all_required"] is not None]
    oos = [r for r in rows if r["category"] in OOS]
    s.update(silent_incomplete=sum(r["silent_incomplete"] for r in rows),
             silent_incomplete_ids=[r["id"] for r in rows if r["silent_incomplete"]],
             complete_for_map_share=round(sum(r["completeness"] == "complete_for_map" for r in withreq) / max(1, len(withreq)), 3),
             out_of_scope_detected=f'{sum(r["scope"] in OOS for r in oos)}/{len(oos)}',
             in_scope_marked_out_of_scope=[r["id"] for r in rows if r["category"] not in OOS and r["scope"] in OOS],
             completeness=dict(Counter(r["completeness"] for r in rows)))
    return {"summary": s, "rows": rows}


REQUIRED_FROZEN = ["compliance_agent/llm_lab/retrieve_v8.py", "compliance_agent/llm_lab/pipeline_v7.py", "compliance_agent/llm_lab/retrieve.py",
                   "compliance_agent/llm_lab/concepts_v5.py", "experiments/ws_b/CL_t2_write_freeze.py",
                   "compliance_agent/llm_lab/retrieval_metrics.py", "compliance_agent/llm_lab/locators.py", "compliance_agent/llm_lab/t2_payloads.py",
                   "compliance_agent/llm_lab/data/CL_provision_map_v7.json", "compliance_agent/llm_lab/data/CL_expansion_v6.json",
                   "compliance_agent/llm_lab/data/CL_article_index_v6.json", "compliance_agent/llm_lab/data/CL_source_validity_v6.json",
                   "experiments/ws_b/CL_t2_eval.py", "fixtures/CL_llm_eval_unseen_v10.json"]
RUN_MARKER = ROOT / "docs" / "CL_evidence" / "ws_b" / "t2" / "CL_t2_v10_RUN_DONE.json"


def check_freeze(db: str, reproduce: bool = False) -> dict:
    """Refuses unless the code_freeze record covers every required file and the DB, all hashes match, and v10 never ran
    (or, with --reproduce, it ran exactly once and this run only verifies that the recorded metrics are reproduced)."""
    if RUN_MARKER.exists() and not reproduce:
        raise SystemExit(f"REFUSED: v10 already ran once ({RUN_MARKER.name}); use --reproduce to verify, or a new independent set v11")
    if reproduce and not RUN_MARKER.exists():
        raise SystemExit("REFUSED: --reproduce needs the recorded first run")
    rec = json.loads(FREEZE_RECORD.read_text(encoding="utf-8"))
    missing = [f for f in REQUIRED_FROZEN if f not in rec.get("files_sha256", {})]
    if missing:
        raise SystemExit(f"REFUSED: the code_freeze record does not cover {missing}")
    for f, h in rec["files_sha256"].items():
        if f == "experiments/ws_b/CL_t2_eval.py":
            continue   # verified below against config: this runner is frozen too, but checked by the config hash
        if hashlib.sha256((ROOT / f).read_bytes()).hexdigest() != h:
            raise SystemExit(f"REFUSED: {f} changed after the code freeze")
    if hashlib.sha256((ROOT / "experiments/ws_b/CL_t2_eval.py").read_bytes()).hexdigest() != rec["files_sha256"]["experiments/ws_b/CL_t2_eval.py"]:
        raise SystemExit("REFUSED: the evaluator changed after the code freeze")
    if hashlib.md5(Path(db).read_bytes()).hexdigest() != rec["db_md5"]:
        raise SystemExit("REFUSED: not the frozen database build")
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--methods", nargs="+", default=["v5_search", "v7"])
    ap.add_argument("--sets", nargs="+", default=DEV_SETS)
    ap.add_argument("--out")
    ap.add_argument("--final", action="store_true", help="the single holdout run (v10), only after the code freeze")
    ap.add_argument("--reproduce", action="store_true", help="re-run after the recorded v10 run and verify identical metrics (writes nothing)")
    a = ap.parse_args(argv)
    if dbsafety.is_authoritative(a.db):
        raise SystemExit("Refused: WS-B evaluates on a database copy only")
    freeze_rec = None
    if a.final and not a.out and not a.reproduce:
        raise SystemExit("Refused: the single v10 run must write its result file (--out)")
    if HOLDOUT in a.sets:
        if not a.final:
            raise SystemExit("Refused: v10 is the frozen holdout; it runs once, with --final, after the code freeze")
        freeze_rec = check_freeze(a.db, a.reproduce)
    if freeze_rec is not None and not a.reproduce:
        # written BEFORE any v10 question is evaluated: a crash after this point still counts as the one run
        RUN_MARKER.write_text(json.dumps({"ran": "v10", "status": "started", "output": a.out,
                                          "freeze_record_sha256": hashlib.sha256(FREEZE_RECORD.read_bytes()).hexdigest()}, indent=1), encoding="utf-8")
    con = connect_ro(a.db)
    out = {"protocol": "CL_t2_eval.py", "db_md5": hashlib.md5(Path(a.db).read_bytes()).hexdigest(), "code_freeze": freeze_rec,
           "methods": {}}
    for m in a.methods:
        cls, fn = method(m)
        out["methods"][m] = {"class": cls, "sets": {}}
        for s in a.sets:
            ev = evaluate(con, load(s), fn)
            out["methods"][m]["sets"][s] = ev
            x = ev["summary"]
            print(f'{m} [{cls}] {s}: req={x["all_required"]} any={x["any_expected"]} silent={x["silent_incomplete"]} {x["silent_incomplete_ids"]} '
                  f'cfm={x["complete_for_map_share"]} oos={x["out_of_scope_detected"]} inscope_as_oos={x["in_scope_marked_out_of_scope"]} '
                  f'irr={x["irrelevant_added_share"]} P={x["avg_passages"]}')
    if a.reproduce:
        first = json.loads(Path(json.loads(RUN_MARKER.read_text())["output"]).read_text(encoding="utf-8"))
        strip = lambda o: {m: {s: v["summary"] for s, v in d["sets"].items()} for m, d in o["methods"].items()}
        same = strip(first) == strip(out)
        print("REPRODUCED: identical metrics" if same else "NOT REPRODUCED: metrics differ")
        return 0 if same else 1
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    if freeze_rec is not None:
        RUN_MARKER.write_text(json.dumps({"ran": "v10", "status": "completed", "output": a.out,
                                          "freeze_record_sha256": hashlib.sha256(FREEZE_RECORD.read_bytes()).hexdigest()}, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
