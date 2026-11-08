"""Retrieval v7 + Option C1 (Workstream B). Deterministic retrieval, mapping, validity and certification; C1 is an
independent second classification method.

    certified `complete` only if ALL hold:
      - deterministic v7 alone would certify (topic found, nothing missing, no G1/G3 issue, not ambiguous, passage search
        and article scorer agree, <= 3 primary topics)
      - C1 succeeded, says in scope, with `high` confidence
      - C1's topics equal v7's primary curated topics (v7 secondary topics may also appear in C1's list)
      - every required provision of the union of both methods' topics was retrieved, with no G1/G3 issue
    either method out of scope   -> no passages added; `out_of_scope` when both agree, otherwise `incomplete`
    C1 failure / low confidence / disagreement -> `incomplete` (never `complete`)

pipeline_v7.py, its tables and the v6 files are not changed. c1=None runs plain v7 (rollback switch).
"""
from __future__ import annotations

import sqlite3

from . import pipeline_v7 as P7
from .locators import article_key
from .retrieve import search as _search


def agreement(v7_cls: dict, c1: dict | None) -> tuple[bool, str]:
    if c1 is None:
        return False, "C1 not run"
    if not c1["ok"]:
        return False, f"C1 failed ({c1['error']})"
    if not c1["in_scope"]:
        return False, f"C1 says out of scope ({c1['oos_class']})"
    if v7_cls["out_of_scope"]:
        return False, "v7 says out of scope, C1 says in scope"
    if c1["confidence"] != "high":
        return False, "C1 confidence low"
    curated = set(P7.tables()["curated"])
    v7_primary = {t for t in v7_cls["intents"] if t in curated}
    c1_main = set(c1["topics"]) - {t for t in v7_cls.get("secondary", []) if t in curated}
    if not v7_primary or c1_main != v7_primary:
        return False, f"topics disagree (v7 {sorted(v7_primary)} vs C1 {sorted(set(c1['topics']))})"
    return True, "methods agree"


def retrieve(con: sqlite3.Connection, question: str, c1: dict | None) -> dict:
    """c1 = classifier_c1.classify(...) result, or None (plain v7)."""
    v7 = P7.retrieve(con, question)
    if c1 is None:
        v7["c1"] = None
        return v7
    cls = v7["classification"]
    rec = {"question": question, "classification": cls, "c1": c1, "v7_status": v7["status"], "required": [], "missing": [],
           "issues": [], "partners_added": [], "confirmed_by_scorer": v7["confirmed_by_scorer"]}
    got = [dict(r, added_by="bm25") for r in _search(con, question, k=P7.BM25_K, heading_extra=0, core_pack=False)]
    c1_oos = c1["ok"] and not c1["in_scope"]
    if cls["out_of_scope"] or c1_oos:
        both = cls["out_of_scope"] and c1_oos
        rec.update(passages=got, status="out_of_scope" if both else "incomplete", warnings=[],
                   agreement=(both, "both methods say out of scope" if both else "one method says out of scope"),
                   message=P7.PLAIN["out_of_scope" if both else "incomplete"] + ("" if both else " The two classification methods disagree on whether this is a UAE VAT question."),
                   oos_class=c1["oos_class"] if c1_oos else None)
        return rec
    # both in scope (or C1 failed): union of topics, ordered agreed -> C1-only -> v7-only, mapped deterministically
    T = P7.tables()["topics"]
    v7_its, v7_sec, amb = list(cls["intents"]), list(cls["secondary"]), cls["ambiguous"]
    c1_topics = [t for t in (c1["topics"] if c1["ok"] else []) if t in T]
    agreed = [t for t in c1_topics if t in v7_its]
    its = agreed + [t for t in c1_topics if t not in agreed and t not in v7_sec] + [t for t in v7_its if t not in c1_topics]
    sec = [t for t in v7_sec if t not in its]
    req, why = P7.required_for(question, its, amb, sec)
    rec["required"] = req
    added = 0

    def add(ref: str, label: str) -> bool:
        nonlocal added
        if added >= P7.MAX_ADD or P7._present(got, ref):
            return False
        r = P7._fetch(con, ref)
        if r is None:
            return False
        got.append(dict(r, added_by=label)); added += 1
        return True

    src_of = lambda t: "agreed" if t in agreed else ("c1" if t in c1_topics else "v7")
    primary_req = [r for r in req if why[r] in its]
    base_req = [r for r in req if why[r] == "base_rule"]
    for r in primary_req:
        add(r, f"c1:required:{why[r]}:{src_of(why[r])}" + (":ambiguous" if amb else ""))
    for r in base_req:
        add(r, "c1:required:base_rule")
    if not amb:
        for p, kind, src in P7.partners(primary_req):
            if kind == "implementing_pair" and add(p, f"c1:partner:{kind}:{src}"):
                rec["partners_added"].append(p)
    for r in req:
        if r not in primary_req and r not in base_req:
            add(r, f"c1:required:{why[r]}")
    if not amb:
        for p, kind, src in P7.partners(req):
            if p not in rec["partners_added"] and add(p, f"c1:partner:{kind}:{src}"):
                rec["partners_added"].append(p)
    if not its and not sec:
        for k, _ in cls["scorer"][:2]:
            add(k, "c1:scorer")
    rec["missing"] = [r for r in req if not P7._present(got, r)]
    ok, why_txt = agreement(cls, c1)
    rec["agreement"] = (ok, why_txt)
    # deterministic stages 4-5 on the union; then the agreement rule can only lower the status, never raise it
    rec["classification"] = dict(cls, intents=its, secondary=sec)
    rec["confirmed_by_scorer"] = v7["confirmed_by_scorer"] and v7["status"] == "complete"
    out = P7._finish(rec, got)
    if out["status"] == "complete" and not ok:
        out["status"] = "incomplete"
        out["message"] = P7.PLAIN["incomplete"] + f" Not certified: {why_txt}."
    return out


def bm25_keys(passages: list[dict]) -> set:
    return {article_key(p["source_id"], p["locator"]) for p in passages if p.get("added_by") == "bm25"}
