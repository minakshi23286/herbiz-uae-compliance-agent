"""Amendment impact for the D3-reviewed provision map (Workstream B). Read-only; no network; no spend.

Given the provisions that a legal change affects (normally Workstream C's change-impact output, e.g. "FTA-VAT-DL8|13",
or "FTA-VAT-DL8|*" for an unknown scope), list ONLY what the reviewer must look at again:
  - topics whose required or supporting articles include an affected provision            (re-review: required)
  - topics one link away (implementing pair / explicit reference / sibling)              (re-review: check)
  - links that touch an affected provision                                                (re-review: check)
  - frozen evaluation questions whose labels cite an affected provision                   (labels to re-confirm)
Everything else keeps its recorded decision.

    python3 experiments/ws_b/CL_amendment_impact.py FTA-VAT-DL8|13 [more provisions] [--out docs/review_d3/impact_<date>.md]
    python3 experiments/ws_b/CL_amendment_impact.py --from-c-impact <C's change-impact json>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "docs" / "review_d3" / "CL_D3_review_data.json"


def check_fresh(data: dict) -> None:
    """Refuse a stale snapshot: the review data must have been built from the CURRENT map and links (review defect 7)."""
    import hashlib
    i = data["inputs"]
    now = {"provision_map_sha256": ROOT / "compliance_agent/llm_lab/data/CL_provision_map_v7.json",
           "classifier_c1p2_sha256": ROOT / "compliance_agent/llm_lab/classifier_c1p2.py",
           "links_sha256": ROOT / "compliance_agent/llm_lab/data/CL_expansion_v6.json"}
    for k, path in now.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != i.get(k):
            raise SystemExit(f"REFUSED: {DATA.name} is stale ({k} changed). Re-run experiments/ws_b/CL_build_d3_review_pack.py first.")


def impact(affected: list[str], data: dict) -> dict:
    whole = {a.split("|")[0] for a in affected if a.endswith("|*")}
    hit = lambda k: k in affected or k.split("|")[0] in whole
    direct, near = [], []
    for t in data["topics"]:
        keys = [p["key"] for p in t["required"] + t["supporting"]]
        linked = [x["to"] for name in ("cross_references", "implementing_pairs", "siblings") for x in t[name]]
        if any(hit(k) for k in keys):
            direct.append({"id": t["id"], "topic": t["topic"], "affected": sorted(k for k in keys if hit(k))})
        elif any(hit(k) for k in linked):
            near.append({"id": t["id"], "topic": t["topic"], "via": sorted(k for k in linked if hit(k))})
    # topics that take the base registration rule (DL 13 + ER 7, + DL 19 when an amount is stated) at run time (gap GAP-08)
    sys.path.insert(0, str(ROOT))
    from compliance_agent.llm_lab.concepts_v5 import BASE_RULE_WITH
    if any(hit(k) for k in ("FTA-VAT-DL8|13", "FTA-VAT-ER|7", "FTA-VAT-DL8|19")):
        seen = {x["id"] for x in direct + near}
        for t in data["topics"]:
            if t["topic"] in BASE_RULE_WITH and t["id"] not in seen:
                near.append({"id": t["id"], "topic": t["topic"], "via": ["base registration rule"]})
    links = [x for x in data["links"] if hit(x["from"]) or hit(x["to"])]
    questions = []
    for v in ("v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9"):
        p = ROOT / "fixtures" / f"CL_llm_eval_unseen_{v}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        for q in (d["questions"] if isinstance(d, dict) else d):
            refs = [f"{s}|{a}" if a is not None else f"{s}|*" for s, a in q.get("required_sources", []) + q.get("supporting_sources", []) + q.get("expected_sources", [])]
            if any(hit(r) for r in refs):
                questions.append(f"{v}:{q['id']}")
    gaps = [g["id"] for g in data.get("known_gaps", []) if any(hit(k) for k in g.get("provisions", []))]
    for f in data.get("flagged_labels", []):
        if any(hit(k) for k in f["author_required"] + f["reviewer_required"]):
            questions.append(f"{f['set']}:{f['id']}")
    questions = sorted(set(questions))
    unmapped = [a for a in affected if not a.endswith("|*") and not any(a in [p["key"] for p in t["required"] + t["supporting"]] for t in data["topics"])]
    return {"affected": affected, "topics_rereview": direct, "known_gaps": gaps, "unmapped_affected": unmapped, "topics_check": near, "links_check": [x["id"] for x in links],
            "eval_labels_to_reconfirm": questions,
            "unchanged_topics": [t["id"] for t in data["topics"] if t["id"] not in {x["id"] for x in direct + near}]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("provisions", nargs="*")
    ap.add_argument("--from-c-impact")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    affected = list(a.provisions)
    if a.from_c_impact:
        affected += json.loads(Path(a.from_c_impact).read_text()).get("step2_affected_provision", [])
    if not affected:
        raise SystemExit("give at least one provision, e.g. FTA-VAT-DL8|13")
    data = json.loads(DATA.read_text())
    check_fresh(data)
    r = impact(affected, data)
    rr = ", ".join("{} {} ({})".format(x["id"], x["topic"], ", ".join(x["affected"])) for x in r["topics_rereview"]) or "none"
    ck = ", ".join("{} {}".format(x["id"], x["topic"]) for x in r["topics_check"]) or "none"
    ql = r["eval_labels_to_reconfirm"]
    total = len(r["unchanged_topics"]) + len(r["topics_rereview"]) + len(r["topics_check"])
    lines = ["# HerBiz: amendment impact on the provision map — " + ", ".join(affected), "",
             "Not legal or tax advice. Generated read-only from `docs/review_d3/CL_D3_review_data.json`.", "",
             "- **Re-review (topic uses an affected article):** " + rr,
             "- **Check (one link away):** " + ck,
             "- **Links to check:** " + (", ".join(r["links_check"]) or "none"),
             "- **Known gaps touching these provisions:** " + (", ".join(r["known_gaps"]) or "none"),
             "- **Affected provisions in no topic (need a mapping decision):** " + (", ".join(r["unmapped_affected"]) or "none"),
             "- **Evaluation labels to re-confirm:** {} ({}{})".format(len(ql), ", ".join(ql[:30]), " …" if len(ql) > 30 else ""),
             "- **Unchanged topics (keep their decisions):** {} of {}".format(len(r["unchanged_topics"]), total)]
    text = "\n".join(lines) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
