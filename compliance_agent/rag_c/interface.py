"""Read-only interface for Workstream B (retrieval) — contract v1.0 (docs/rag/CL_HERBIZ_RAG_INTEGRATION_HANDOFF.md).

B imports only these functions; it never opens C's files directly. Every function is read-only.

    from compliance_agent.rag_c import interface as C
    v = C.load_validity(db=DB)                              # refuses an export made for another build
    C.provision_status(v, "FTA-VAT-DL8", "Article 48, pp. 23-25, part 1")
    C.certification_blockers(v, [("FTA-VAT-ER", "Article 14, pp. 12-13, part 1"), ...])
    C.resolve_citation(con, {"passage_id": ..., "quote": ...}, v)
"""
from __future__ import annotations

import json
from pathlib import Path

from .citations import check_citation
from .inventory import article_key
from .validity import EXPORT, SCHEMA_VERSION, issues_for

CONTRACT_VERSION = "1.1"


def load_validity(path: Path = EXPORT, db=None, allow_unchecked: bool = False) -> dict:
    """Refuses an export generated for a different database build (stale export / wrong build). The database is
    required: pass the file you query, or allow_unchecked=True for offline inspection only (never for user answers)."""
    v = json.loads(Path(path).read_text(encoding="utf-8"))
    if db is None and not allow_unchecked:
        raise ValueError("load_validity needs db=<the database you answer from> so a stale export cannot be used")
    if db is not None:
        import hashlib
        md5 = hashlib.md5(Path(db).read_bytes()).hexdigest()
        if md5 != v["_meta"]["database_md5"]:
            raise ValueError(f"validity export was generated for database md5 {v['_meta']['database_md5'][:12]}…, not {md5[:12]}…; "
                             "regenerate it with `rag_c validity --db <this db> --write`")
    if v["_meta"]["schema_version"].split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        raise ValueError(f"validity schema {v['_meta']['schema_version']} is not compatible with {SCHEMA_VERSION}")
    return v


def article_id(source_id: str, locator: str) -> str | None:
    """Stable provision id across builds and versions: 'FTA-VAT-DL8|48', 'FTA-VAT-ER|14 (bis)'; 'SRC|Paragraph 3' for web
    pages; None for front matter. Passage ids are NOT stable across builds; use this id plus version_id instead."""
    k = article_key(locator)
    if k:
        return f"{source_id}|{k[0]}" + (f" ({k[1]})" if k[1] else "")
    if locator.startswith("Paragraph"):
        return f"{source_id}|{locator.split(',')[0]}"
    return None


def provision_status(validity: dict, source_id: str, locator: str, version_id: str | None = None) -> dict:
    """Everything B needs to label one retrieved passage. `reasons` lists every reason it is not certifiable."""
    aid = article_id(source_id, locator or "")
    art = aid.split("|", 1)[1] if aid else None
    issues = issues_for(validity, source_id, art)
    cur = validity["current_versions"].get(source_id, {})
    ver = next((v for v in validity["versions"] if v["version_id"] == version_id), None) if version_id else None
    reasons = []
    if aid is None:
        reasons.append("unparsed_locator")            # e.g. 'Article (55)', front matter: never certify what cannot be keyed
    if ver is None:
        reasons.append("unknown_version" if version_id else "no_version_given")
    else:
        if ver["source_id"] != source_id:
            reasons.append("version_of_other_source")
        if not ver["approved"]:
            reasons.append("source_not_approved")
        if ver.get("outdated"):
            reasons.append("version_outdated")
        if ver.get("superseded_by") or version_id != cur.get("version_id"):
            reasons.append("version_not_current")
    reasons += [i["kind"] for i in issues]
    return {"article_id": aid, "issues": [{"id": i["id"], "kind": i["kind"], "message": i["message"]} for i in issues],
            "kinds": sorted({i["kind"] for i in issues}), "conflict": any(i["kind"] == "conflict" for i in issues),
            "current_version": cur.get("version_id"), "is_current_version": (version_id == cur.get("version_id")) if version_id else None,
            "approved": bool(ver and ver["approved"] and ver["source_id"] == source_id),
            "verification_status": ver["verification_status"] if ver else None,
            "reasons": reasons, "certifiable": not reasons}


def certification_blockers(validity: dict, provisions: list[tuple]) -> list[dict]:
    """For an answer that needs these (source_id, locator, version_id) provisions: every reason it cannot be certified
    'complete'. Empty list = no C-side blocker (B's own completeness rules still apply)."""
    out = []
    for p in provisions:
        s = provision_status(validity, *p)
        by_issue = {i["kind"]: i for i in s["issues"]}
        for r in s["reasons"]:
            i = by_issue.get(r)
            out.append({"article_id": s["article_id"], "reason": r, **({"issue": i["id"], "message": i["message"]} if i else {})})
    return out


def resolve_citation(con, citation: dict, validity: dict) -> dict:
    """Citation integrity + provenance for one {passage_id, quote}; adds the stable article_id."""
    r = check_citation(con, citation, validity)
    if r.get("locator"):
        r["article_id"] = article_id(r["source_id"], r["locator"])
    return r


def resolve_by_article(con, source_id: str, version_id: str, article_id_: str, quote: str, validity: dict) -> dict:
    """Build-independent citation check (contract v1.0): passage ids are build-scoped and may point to different text in
    another build (e.g. #0002 in a D10 build). Resolve by (version_id, article_id) and verify the quote in that article."""
    from ..sources import normalize
    rows = con.execute("SELECT passage_id, locator, text FROM passages WHERE version_id = ? ORDER BY seq", (version_id,)).fetchall()
    hits = [r for r in rows if article_id(source_id, r["locator"]) == article_id_]
    found = next((r for r in hits if normalize(quote) and normalize(quote) in normalize(r["text"])), None)
    st = provision_status(validity, source_id, found["locator"] if found else (hits[0]["locator"] if hits else ""), version_id)
    return {"article_id": article_id_, "version_id": version_id, "passages_in_article": len(hits),
            "result": "quote_found" if found else ("ARTICLE_NOT_FOUND" if not hits else "QUOTE_NOT_FOUND"),
            "passage_id_in_this_build": found["passage_id"] if found else None, **{k: st[k] for k in ("issues", "kinds", "certifiable")}}


# ------------------------------------------------------------------ contract v1.1: completeness and approval are separate
RETRIEVAL_COMPLETENESS = ("complete", "incomplete", "not_covered", "refusal", "unchecked")   # Workstream B decides
SOURCE_APPROVAL = ("approved", "not_approved")                                                # Workstream C / reviewer decides


def answer_label(validity: dict, retrieval_completeness: str, provisions: list[tuple]) -> dict:
    """The one place that may combine B's retrieval completeness with C's legal-source status.

    retrieval_completeness: B's verdict on whether every required provision was retrieved (never about the law's validity).
    provisions: (source_id, locator, version_id) for every passage the answer relies on.
    'certified' is True ONLY when retrieval is complete AND every provision is from an approved, current version with no
    validity issue. Any other combination returns certified False and a user-facing wording that says why."""
    if retrieval_completeness not in RETRIEVAL_COMPLETENESS:
        raise ValueError(f"retrieval_completeness must be one of {RETRIEVAL_COMPLETENESS}")
    blockers = certification_blockers(validity, provisions) if provisions else [{"article_id": None, "reason": "no_provisions"}]
    approved = bool(provisions) and not any(b["reason"] in ("source_not_approved", "unknown_version", "no_version_given",
                                                            "version_of_other_source") for b in blockers)
    issue_kinds = sorted({b["reason"] for b in blockers if b["reason"] not in ("source_not_approved", "no_provisions")})
    certified = retrieval_completeness == "complete" and not blockers
    if certified:
        wording = "Based on reviewer-approved official sources that are current for the provisions used."
    else:
        parts = []
        if retrieval_completeness != "complete":
            parts.append({"incomplete": "may be incomplete: some provisions it needs were not found",
                          "not_covered": "this question is outside what the knowledge base covers",
                          "refusal": "the assistant declined to answer", "unchecked": "completeness was not checked"}[retrieval_completeness])
        if not approved:
            parts.append("the official sources used have not been approved by a qualified reviewer")
        if "conflict" in issue_kinds:
            parts.append("official sources disagree on a point used here; both are shown")
        if {"outdated", "repealed", "missing"} & set(issue_kinds):
            parts.append("a provision used may be out of date")
        if {"version_not_current", "version_outdated"} & set(issue_kinds):
            parts.append("an older or out-of-date version of an official text was used")
        if {"unparsed_locator", "unknown_version", "no_version_given", "version_of_other_source"} & set(issue_kinds):
            parts.append("a cited passage could not be matched to a known article and version")
        if "source_changed" in issue_kinds:
            parts.append("an official source used here changed recently and the change has not been reviewed yet")
        if "future_text" in issue_kinds:
            parts.append("part of the cited text applies only from a future date")
        wording = "Draft information, not legal or tax advice: " + "; ".join(parts) + "."
    return {"contract_version": "1.1", "retrieval_completeness": retrieval_completeness,
            "source_approval": "approved" if approved else "not_approved", "validity_issue_kinds": issue_kinds,
            "certified": certified, "blockers": blockers, "user_wording": wording}
