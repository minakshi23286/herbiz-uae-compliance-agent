"""Offline retrieval metrics (no network, no spend).

For each question the expected articles are split into REQUIRED (a correct answer must rest on them) and SUPPORTING.
Sets that only list "expected_sources" (any-of) are measured on the metrics that need no split.

    any_expected     at least one required-or-supporting article reached the model
    all_required     every required article reached the model                      (needs a required/supporting split)
    first_rank       position (1 = top) of the first required (else expected) article in what the model receives
    mrr              mean reciprocal rank of that first relevant article
    irrelevant_added share of ADDED passages (title / intent steps, not the original BM25 six) that are not expected;
                     for questions that expect no source (out of scope, declined), every added passage is irrelevant
"""
from __future__ import annotations

import re
from statistics import median


def _match(p: dict, src: str, art) -> bool:
    if p["source_id"] != src:
        return False
    return art is None or bool(re.match(rf"Article {art}(,| \()", p["locator"]))


def per_question(q: dict, got: list[dict]) -> dict:
    req = [tuple(x) for x in q.get("required_sources", [])]
    sup = [tuple(x) for x in q.get("supporting_sources", [])]
    anyof = [tuple(x) for x in q.get("expected_sources", [])] or (req + sup)
    relevant = req or anyof
    pos = next((i + 1 for i, p in enumerate(got) if any(_match(p, s, a) for s, a in relevant)), None)
    added = [p for p in got if p.get("added_by", "bm25") != "bm25"]
    expected_all = set(anyof) | set(req) | set(sup)
    irr = [p for p in added if not any(_match(p, s, a) for s, a in expected_all)]
    return {
        "id": q["id"],
        "has_expected": bool(anyof),
        "any_expected": any(_match(p, s, a) for p in got for s, a in anyof) if anyof else None,
        "all_required": all(any(_match(p, s, a) for p in got) for s, a in req) if req else None,
        "first_rank": pos,
        "added": len(added), "irrelevant_added": len(irr), "passages": len(got),
    }


def summarise(rows: list[dict]) -> dict:
    with_exp = [r for r in rows if r["has_expected"]]
    req = [r for r in rows if r["all_required"] is not None]
    ranks = [r["first_rank"] for r in with_exp if r["first_rank"]]
    added = sum(r["added"] for r in rows)
    share = lambda xs: round(sum(xs) / len(xs), 3) if xs else None
    return {
        "questions": len(rows),
        "any_expected": share([bool(r["any_expected"]) for r in with_exp]),
        "all_required": share([bool(r["all_required"]) for r in req]),
        "median_first_rank": median(ranks) if ranks else None,
        "mrr": round(sum(1 / r["first_rank"] if r["first_rank"] else 0 for r in with_exp) / max(1, len(with_exp)), 3),
        "irrelevant_added_share": round(sum(r["irrelevant_added"] for r in rows) / added, 3) if added else 0.0,
        "added_on_no_source_questions": sum(r["added"] for r in rows if not r["has_expected"]),
        "avg_passages": round(sum(r["passages"] for r in rows) / max(1, len(rows)), 1),
        "misses_any": [r["id"] for r in with_exp if not r["any_expected"]],
        "misses_required": [r["id"] for r in req if not r["all_required"]],
    }


def evaluate(questions: list[dict], search_fn) -> dict:
    rows = [per_question(q, search_fn(q["text"])) for q in questions]
    return {"summary": summarise(rows), "rows": rows}
