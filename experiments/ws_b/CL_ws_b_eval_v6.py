"""Workstream B v6 evaluation (offline, read-only DB copy). Retrieval metrics (unchanged retrieval_metrics.py) plus the
v6 gate measures: silent-incomplete rate, validity certification, out-of-scope handling, over-flagging.
Development sets only by default; v5 is refused unless --final is given (the one-time run after the code freeze)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from compliance_agent import dbsafety  # noqa: E402
from compliance_agent.llm_lab import freeze, retrieval_metrics as M  # noqa: E402
from compliance_agent.llm_lab import pipeline_v6 as P  # noqa: E402
from compliance_agent.llm_lab.locators import key  # noqa: E402
from compliance_agent.llm_lab.retrieve import connect_ro  # noqa: E402


def load(name: str) -> list[dict]:
    path = ROOT / "fixtures" / f"CL_llm_eval_unseen_{name}.json"
    freeze.verify(path)
    d = json.loads(path.read_text(encoding="utf-8"))
    return d["questions"] if isinstance(d, dict) else d


def evaluate(con, qs: list[dict]) -> dict:
    recs = [P.retrieve(con, q["text"]) for q in qs]
    ev = M.evaluate(qs, lambda t, it=iter(recs): next(it)["passages"])
    issues = P.tables()["issues"]
    rows = []
    for q, rec, row in zip(qs, recs, ev["rows"]):
        req = [key(s, a) for s, a in q.get("required_sources", [])]
        row.update(status=rec["status"], missing=rec["missing"], our_required=rec["required"],
                   category=q.get("category"), intents=rec["classification"]["intents"],
                   silent_incomplete=bool(req) and row["all_required"] is False and rec["status"] == "complete",
                   over_flagged=bool(req) and row["all_required"] is True and rec["status"] != "complete",
                   certified_with_issue=rec["status"] == "complete" and any(r in issues for r in req + rec["required"]),
                   retrieved=[f'{p["source_id"]}|{p["locator"].split(",")[0]}|{p["added_by"]}' for p in rec["passages"]])
        rows.append(row)
    s = ev["summary"]
    withreq = [r for r in rows if r["all_required"] is not None]
    oos = [r for r in rows if r["category"] in ("out_of_scope", "unsupported")]
    s.update(silent_incomplete_rate=round(sum(r["silent_incomplete"] for r in withreq) / max(1, len(withreq)), 3) if withreq else None,
             silent_incomplete_ids=[r["id"] for r in rows if r["silent_incomplete"]],
             certified_with_issue=sum(r["certified_with_issue"] for r in rows),
             certified_complete_share=round(sum(r["status"] == "complete" for r in withreq) / max(1, len(withreq)), 3) if withreq else None,
             over_flagged_ids=[r["id"] for r in rows if r["over_flagged"]],
             out_of_scope_labelled=f'{sum(r["status"] == "out_of_scope" for r in oos)}/{len(oos)}' if oos else None,
             statuses=dict(Counter(r["status"] for r in rows)))
    return {"summary": s, "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--sets", nargs="+", default=["v1", "v2", "v3", "v4"])
    ap.add_argument("--label", required=True)
    ap.add_argument("--out")
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args(argv)
    if dbsafety.is_authoritative(a.db):
        raise SystemExit("Refused: Workstream B evaluates on a database copy only")
    if "v5" in a.sets and not a.final:
        raise SystemExit("Refused: v5 is the frozen independent set; it runs once, with --final, after the code freeze")
    if a.final:
        import hashlib
        rec = json.loads((ROOT / "docs" / "CL_evidence" / "ws_b" / "CL_v6_code_freeze.json").read_text())
        for f, h in rec["files"].items():
            if f.endswith("CL_ws_b_eval_v6.py"):
                continue   # this runner itself gains only this check after the freeze
            if hashlib.sha256((ROOT / f).read_bytes()).hexdigest() != h:
                raise SystemExit(f"REFUSED: {f} changed after the v6 code freeze")
    con = connect_ro(a.db)
    out = {"label": a.label, "sets": {}}
    for s in a.sets:
        ev = evaluate(con, load(s))
        out["sets"][s] = ev
        m = ev["summary"]
        print(f'{a.label} {s}: any={m["any_expected"]} req={m["all_required"]} silent={m["silent_incomplete_rate"]} {m["silent_incomplete_ids"]} '
              f'certified={m["certified_complete_share"]} cert_issue={m["certified_with_issue"]} mrr={m["mrr"]} irr={m["irrelevant_added_share"]} '
              f'P={m["avg_passages"]} oos_add={m["added_on_no_source_questions"]} oos_lab={m["out_of_scope_labelled"]} st={m["statuses"]} miss={m["misses_required"]}')
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
