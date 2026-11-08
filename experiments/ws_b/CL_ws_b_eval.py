"""Workstream B offline retrieval evaluation (no network, no spend, read-only DB copy).

Runs compliance_agent.llm_lab.retrieve.search over frozen question sets and writes metrics JSON.
Every set's sha256 is checked against its .FROZEN.json lock before use; the runner refuses a modified set.
Usage: python3 experiments/ws_b/CL_ws_b_eval.py --db data/CL_ws_b_kb_copy.sqlite3 --sets v1 v2 v3 --label baseline --out <file>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from compliance_agent import dbsafety  # noqa: E402
from compliance_agent.llm_lab import freeze, retrieval_metrics  # noqa: E402
from compliance_agent.llm_lab.retrieve import connect_ro, search  # noqa: E402


def load_set(name: str) -> list[dict]:
    path = ROOT / "fixtures" / f"CL_llm_eval_unseen_{name}.json"
    freeze.verify(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["questions"] if isinstance(data, dict) else data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--sets", nargs="+", default=["v1", "v2", "v3"])
    ap.add_argument("--label", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if dbsafety.is_authoritative(a.db):
        raise SystemExit("Refused: Workstream B evaluates on a database copy only")
    con = connect_ro(a.db)
    result = {"label": a.label, "db": Path(a.db).name, "sets": {}}
    for s in a.sets:
        qs = load_set(s)
        ev = retrieval_metrics.evaluate(qs, lambda t: search(con, t))
        for row, q in zip(ev["rows"], qs):
            got = search(con, q["text"])
            row["retrieved"] = [f'{p["source_id"]}|{p["locator"].split(",")[0]}|{p.get("added_by", "bm25")}' for p in got]
        result["sets"][s] = ev
        sm = ev["summary"]
        print(f'{a.label:<10} {s:<3} n={sm["questions"]:>2} any={sm["any_expected"]} all_req={sm["all_required"]} '
              f'mrr={sm["mrr"]} irr={sm["irrelevant_added_share"]} avgP={sm["avg_passages"]} '
              f'oos_add={sm["added_on_no_source_questions"]} miss_req={sm["misses_required"]}')
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
