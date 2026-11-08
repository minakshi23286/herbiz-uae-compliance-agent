"""C1-primary retrieval (Workstream B): the LLM classifier leads topic selection; everything else is deterministic.

Three results are kept separate (Workstream C contract v1.1):
  retrieval_complete   B: every required provision of the chosen topics (plus the base registration rule where it
                       applies) AND the main topic's supporting articles were retrieved from C's current version, and
                       Workstream C lists none of them as missing. Needs C's data: unavailable -> not complete.
  source_approved      C: EVERY passage the answer may rely on (all retrieved passages, BM25 included) is from an approved,
                       current version with no validity issue, and nothing required is missing
                       (C's interface.answer_label; unavailable, stale or wrong-build data fails closed)
  answer_certifiable   retrieval_verified AND source_approved AND in scope by both classifiers AND no conflict.
                       Only this may ever be shown as legally certified.
plus retrieval_verified = retrieval_complete AND cross-check AND in scope: a retrieval claim only (the earlier "complete").

Cross-check (an LLM topic alone never verifies anything): C1 succeeded with high confidence; v7 says in scope and is not
ambiguous; v7 found at least one curated topic and it shares the legal area of the C1 topics; deterministic evidence
(passage search top-6 or article scorer top-3) lands on a required, supporting or implementing-pair provision of the C1
topics.

Decision table:
  C1 missing / failed / malformed  -> v7 retrieval (pipeline_v7, with its own G1/G3 notes), never verified or certifiable
  either classifier out of scope   -> nothing added; out_of_scope if both agree, else incomplete
  C1 low confidence                -> C1 topics, then v7 topics; not verified
  required provision missing       -> retrieval_complete false
  G1 / G3 / any C issue            -> source_approved false (classifier output cannot change this)
  `con` is not the database the validity export was loaded for -> source data unusable -> fails closed
Independent review findings 1-11 (17 Oct 2026) are addressed here; see the C1-primary report.
"""
from __future__ import annotations

import sqlite3

from . import classifier_c1p as K
from . import concepts_v5 as C5
from . import pipeline_v7 as P7
from .locators import article_key
from .retrieve import search as _search
from .source_validity_c import ValiditySource

MAX_ADD = P7.MAX_ADD


def _evidence_family(topic_names: list[str]) -> set:
    """Required, supporting and implementing-pair provisions only (no siblings or loose cross-references)."""
    T = K.topics()
    req = {r for t in topic_names if t in T for r in T[t]["required"] + T[t]["supporting"]}
    return req | {p for p, kind, _ in P7.partners(sorted(req)) if kind == "implementing_pair"}


def _required(question: str, its: list[str], ambiguous: bool) -> tuple[list[str], dict]:
    T = K.topics()
    req, why = [], {}
    if its and its[0] in T:   # the classifier lists topics most important first: the main topic is taken in full first
        for r in T[its[0]]["required"]:
            if r not in why:
                req.append(r); why[r] = its[0]
    depth = max((len(T[i]["required"]) for i in its if i in T), default=0)
    for d in range(depth):
        for i in its:
            r = T.get(i, {}).get("required", [])
            if d < len(r) and r[d] not in why:
                req.append(r[d]); why[r[d]] = i
    if C5.needs_base_rule(question, [t for t in its if t in T], ambiguous):
        for r in list(T["mandatory_registration"]["required"]) + (["FTA-VAT-DL8|19"] if C5.turnover_stated(question) else []):
            if r not in why:
                req.append(r); why[r] = "base_rule"
    return req, why


def _locator(key_: str) -> str:
    art = key_.split("|", 1)[1]
    return "Paragraph 1" if art == "*" else f"Article {art}"


def _version_of(con, passage_id: str) -> str | None:
    r = con.execute("SELECT version_id FROM passages WHERE passage_id = ?", (passage_id,)).fetchone()
    return r[0] if r else None


def _blank(question, c1, cls7) -> dict:
    return {"question": question, "c1": c1, "v7_classification": cls7, "topics": [], "required": [], "coverage_extra": [],
            "missing": [], "missing_in_source": [], "not_current": [], "reasons": [], "cross_check": {},
            "retrieval_complete": False, "retrieval_verified": False, "in_scope": False, "oos_class": None}


def retrieve(con: sqlite3.Connection, question: str, c1: dict | None, sv: ValiditySource | None) -> dict:
    """c1: classifier output (live, mocked or pre-recorded) or None; sv: source_validity_c.ValiditySource (None = unavailable)."""
    sv = sv if isinstance(sv, ValiditySource) else ValiditySource(error="no validity source given")
    if sv.available and not sv.bound_to(con):
        sv = ValiditySource(error="the queried database is not the build the validity export was loaded for")
    raw_c1, c1 = c1, K.normalise(c1)
    cls7 = P7.classify(question)
    got = [dict(r, added_by="bm25") for r in _search(con, question, k=P7.BM25_K, heading_extra=0, core_pack=False)]
    bm = {article_key(p["source_id"], p["locator"]) for p in got}
    rec = _blank(question, raw_c1, cls7)
    if c1 is None:
        v7 = P7.retrieve(con, question)
        rec.update(topics=v7["classification"]["intents"], required=v7["required"], missing=v7["missing"],
                   retrieval_status="out_of_scope" if v7["status"] == "out_of_scope" else "incomplete",
                   in_scope=v7["status"] != "out_of_scope", v7_status=v7["status"], v7_issues=v7.get("issues", []),
                   v7_warnings=v7.get("warnings", []), v7_message=v7.get("message"))
        rec["reasons"].append(f"C1 unavailable ({(raw_c1 or {}).get('error') if isinstance(raw_c1, dict) else 'not run'}): "
                              "deterministic v7 retrieval, not verified")
        return _finalise(con, rec, v7["passages"], sv)
    if not c1["in_scope"] or cls7["out_of_scope"]:
        both = (not c1["in_scope"]) and cls7["out_of_scope"]
        rec.update(retrieval_status="out_of_scope" if both else "incomplete", oos_class=c1["oos_class"])
        rec["reasons"].append("both classifiers: out of scope" if both else
                              f"scope disagreement (C1 in scope: {c1['in_scope']}, v7 in scope: {not cls7['out_of_scope']}): nothing added")
        return _finalise(con, rec, got, sv)
    T = K.topics()
    c1_topics = [t for t in c1["topics"] if t in T]
    v7_topics = [t for t in cls7["intents"] + cls7.get("secondary", []) if t in T and t not in c1_topics]
    req, why = _required(question, c1_topics, cls7["ambiguous"])
    main_support = [x for x in T[c1_topics[0]]["supporting"] if x not in req] if c1_topics else []
    added = 0

    def add(ref: str, label: str) -> None:
        nonlocal added
        if added >= MAX_ADD or P7._present(got, ref):
            return
        r = P7._fetch(con, ref)
        if r is not None:
            got.append(dict(r, added_by=label)); added += 1

    for r in [r for r in req if why[r] != "base_rule"]:
        add(r, f"c1p:required:{why[r]}")
    for r in [r for r in req if why[r] == "base_rule"]:
        add(r, "c1p:required:base_rule")
    for x in main_support:   # verification also needs the main topic's supporting articles
        add(x, f"c1p:supporting_main:{c1_topics[0]}")
    for p, kind, src in P7.partners(req):
        if kind == "implementing_pair":
            add(p, f"c1p:partner:{kind}:{src}")
    v7_req, _ = _required(question, v7_topics, cls7["ambiguous"])
    for r in v7_req:
        add(r, "c1p:v7_topic")
    coverage = req + main_support
    rec.update(topics=c1_topics, required=req, coverage_extra=main_support, in_scope=True)
    rec["missing"] = [r for r in coverage if not P7._present(got, r)]
    # B5: a provision C lists as missing from our copy can never be retrieved, so retrieval cannot be complete
    rec["missing_in_source"] = [r for r in coverage if any(i.get("kind") in ("missing", "unavailable")
                                                          for i in sv.provision_issues(r.split("|")[0], _locator(r), None))]
    # B6: covered provisions must come from C's current version; without C's data this cannot be checked -> not complete
    for r in coverage:
        cur = sv.current_version(r.split("|")[0])
        p = next((p for p in got if P7._present([p], r)), None)
        if p is not None and (cur is None or _version_of(con, p["passage_id"]) != cur):
            rec["not_current"].append(r)
    complete = bool(req) and not rec["missing"] and not rec["missing_in_source"] and not rec["not_current"]
    fam = _evidence_family(c1_topics)
    v7_primary = [t for t in cls7["intents"] if t in T]
    checks = {"c1_high_confidence": c1["confidence"] == "high", "v7_in_scope": not cls7["out_of_scope"],
              "v7_not_ambiguous": not cls7["ambiguous"],
              "deterministic_evidence": bool(bm & fam) or any(k in fam for k, _ in cls7["scorer"][:3]),
              "v7_same_legal_area": bool(v7_primary) and bool(_evidence_family(v7_primary) & fam)}
    rec["cross_check"] = checks
    verified = complete and all(checks.values())
    rec.update(retrieval_complete=complete, retrieval_verified=verified,
               retrieval_status="complete" if verified else ("ambiguous" if cls7["ambiguous"] else "incomplete"))
    rec["reasons"] += [f"cross-check failed: {k}" for k, ok in checks.items() if not ok]
    for name in ("missing", "missing_in_source", "not_current"):
        if rec[name]:
            rec["reasons"].append(f"{name}: " + ", ".join(rec[name]))
    return _finalise(con, rec, got, sv)


def _finalise(con, rec: dict, got: list[dict], sv: ValiditySource) -> dict:
    """Legal-source status from Workstream C over EVERY retrieved passage (fail closed) and the final decision."""
    provs = sorted({(p["source_id"], p["locator"], _version_of(con, p["passage_id"])) for p in got}, key=str)
    completeness = ("complete" if rec.get("retrieval_complete") else
                    "not_covered" if rec.get("retrieval_status") == "out_of_scope" else "incomplete")
    label = sv.label(completeness, provs)
    kinds = set(label.get("validity_issue_kinds", []))
    rec["source_label"] = label
    rec["source_approved"] = (label.get("source_approval") == "approved" and not kinds and not label.get("blockers")
                              and not rec["missing"] and not rec["missing_in_source"])
    rec["answer_certifiable"] = bool(rec.get("retrieval_verified") and rec["source_approved"] and rec.get("in_scope")
                                     and "conflict" not in kinds and label.get("certified") is True)
    rec["user_wording"] = ("Based on reviewer-approved official sources that are current for the provisions used."
                           if rec["answer_certifiable"] else label.get("user_wording"))
    rec["passages"] = got
    rec["status"] = rec.get("retrieval_status")     # retrieval metric only; never a legal statement
    return rec


def search(con, question: str, c1: dict | None, sv) -> list[dict]:
    return retrieve(con, question, c1, sv)["passages"]
