"""Builds the v7 retrieval tables OFFLINE (Workstream B, one map-completion cycle approved 16 Oct 2026).

v7 = v6 tables + (1) curated topics for the legal concepts the v6 report found missing, (2) one "article topic" for EVERY
article of the corpus (required = the article + its implementing-pair articles), so every provision is reachable from
stage 1's article scorer, and (3) a coverage audit listing which topics require each article.
v6 files are not touched. Usage: python3 experiments/ws_b/CL_build_v7_tables.py <corpus copy> [out_dir]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments" / "ws_b"))
import CL_build_v6_tables as V6  # noqa: E402
from compliance_agent.llm_lab.retrieve import connect_ro  # noqa: E402

DL, ER = "FTA-VAT-DL8", "FTA-VAT-ER"
# Missing concepts named in CL_WS_B_V6_REPORT.md §4, mapped by article title (law structure), plus chapter completeness.
V7_CURATED = {
    "vouchers":                   {"required": [f"{DL}|40", f"{ER}|28"], "supporting": [f"{DL}|26"]},
    "composite_supply":           {"required": [f"{DL}|8", f"{ER}|4"], "supporting": [f"{DL}|47", f"{ER}|46"]},
    "input_tax_before_registration": {"required": [f"{DL}|56"], "supporting": [f"{DL}|54"]},
    "blocked_input_tax":          {"required": [f"{ER}|53"], "supporting": [f"{DL}|54"]},
    # Deregistration chapter as a whole (cases, application, voluntary deregistration) + its implementing article
    "deregistration":             {"required": [f"{DL}|21", f"{ER}|14", f"{DL}|22", f"{DL}|23"], "supporting": [f"{ER}|18"]},
    "bad_debt":                   {"required": [f"{DL}|64"], "supporting": [f"{DL}|61", f"{DL}|62"]},
}
MAX_PAIRS = 2


def main(db: str, out_dir: str | None = None) -> None:
    out = Path(out_dir) if out_dir else V6.OUT
    con = connect_ro(db)
    arts = V6.articles(con)
    links = json.loads((V6.OUT / "CL_expansion_v6.json").read_text())["links"]   # v6 links are reused unchanged
    pm6 = json.loads((V6.OUT / "CL_provision_map_v6.json").read_text())
    topics = {k: dict(v) for k, v in pm6["topics"].items()}
    for k, v in V7_CURATED.items():
        topics[k] = {"required": v["required"], "supporting": v["supporting"], "status": "draft", "reviewed_by": None, "origin": "v7 curated"}
    for k, v in topics.items():
        v.setdefault("origin", "v5 index (v6 map)")
    article_topics = {}
    for k in sorted(arts):
        pairs = [x["key"] for x in links.get(k, []) if x["why"] == "implementing_pair"][:MAX_PAIRS]
        article_topics[f"art:{k}"] = {"required": [k] + pairs, "supporting": [], "status": "draft", "reviewed_by": None,
                                      "origin": "v7 article topic (article + implementing pairs)", "title": arts[k]["title"]}
    coverage = {k: sorted(t for t, v in {**topics, **article_topics}.items() if k in v["required"]) for k in sorted(arts)}
    curated_cov = {k: [t for t in v if not t.startswith("art:")] for k, v in coverage.items()}
    meta = {"built_by": "experiments/ws_b/CL_build_v7_tables.py", "base": "v6 provision map + v6 expansion links",
            "locator_contract": "Workstream C interface contract v0.1", "not_legal_advice": True,
            "articles": len(arts), "curated_topics": len(topics), "article_topics": len(article_topics),
            "articles_in_a_curated_topic": sum(1 for v in curated_cov.values() if v)}
    out.mkdir(parents=True, exist_ok=True)
    (out / "CL_provision_map_v7.json").write_text(json.dumps({"_meta": dict(meta, note="Draft: no qualified reviewer has approved it (D3)."),
                                                              "topics": topics, "article_topics": article_topics}, indent=1, sort_keys=True) + "\n")
    (out / "CL_coverage_audit_v7.json").write_text(json.dumps({"_meta": meta, "article_to_topics": coverage}, indent=1, sort_keys=True) + "\n")
    print(meta)


if __name__ == "__main__":
    main(*sys.argv[1:3])
