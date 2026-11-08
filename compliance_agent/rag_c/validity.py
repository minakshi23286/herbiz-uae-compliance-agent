"""Source-validity export: the one file Workstream B reads to know which provisions it may not certify.

Format is a superset of B's own mirror (llm_lab/data/CL_source_validity_v6.json on ws-b-retrieval): issues[] with
id / kind / provisions ("SOURCE|ARTICLE" keys, "SOURCE|*" for a whole source) / message. Added: per-version status
flags, the selected current version per source with its basis, conflicts and claims. Generated from the register and a
read-only database; it changes no status. Kinds: outdated | repealed | missing | conflict | extraction | unverified."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from .amendments import amendment_map, footnote_index
from .claims import check_claims
from .inventory import ROOT, inventory
from .register import REGISTER

EXPORT = ROOT / "knowledge_base" / "CL_source_validity.json"
SCHEMA_VERSION = "1.1"


def _key(source_id: str, article: str | None) -> str:
    return f"{source_id}|{article}" if article else f"{source_id}|*"


def build_validity(db, register_path: Path = REGISTER, as_of: str | None = None, alerts: list | None = None) -> dict:
    as_of = as_of or dt.date.today().isoformat()
    reg = json.loads(Path(register_path).read_text(encoding="utf-8"))
    amap = amendment_map(register_path, as_of, db=db)
    claims = check_claims(db, register_path)
    inv = inventory(db)
    issues: list[dict] = []

    current = {}
    for sid in sorted({v["source_id"] for v in amap["versions"]}):
        vs = [v for v in amap["versions"] if v["source_id"] == sid]
        pick = next((v for v in vs if v["newest_by_effective_date"]), None) or vs[-1]
        current[sid] = {"version_id": pick["version_id"],
                        "basis": "latest effective date stated in the file" if pick["newest_by_effective_date"] else "highest collection sequence (no stated dates)",
                        "fta_currency": pick["fta_currency"], "outdated": pick["outdated"]}
        by_kind: dict[str, list[dict]] = {}
        for a in pick["affected_articles"]:
            kind = {"amends": "outdated", "repeals": "repealed", "adds": "missing"}[a["effect"]]
            by_kind.setdefault(kind, []).append(a)
        for kind, arts in sorted(by_kind.items()):
            ins = sorted({a["instrument_id"] for a in arts})
            eff = sorted({a["effective"] for a in arts if a["effective"]})
            verb = {"outdated": "changed", "repealed": "repealed", "missing": "added"}[kind]
            issues.append({"id": f"{sid}:{kind}", "kind": kind, "version_id": pick["version_id"], "provisions": sorted({_key(sid, a["article"]) for a in arts}),
                           "instruments": ins, "effective": eff,
                           "message": f"{pick['version_id']} predates {', '.join(ins)} (in force {', '.join(eff)}), which {verb} these provisions; "
                                      f"the current text has not been collected."})
        if pick["missing_instruments_with_unknown_scope"]:
            issues.append({"id": f"{sid}:partial-scope", "kind": "outdated", "version_id": pick["version_id"], "provisions": [_key(sid, None)],
                           "instruments": pick["missing_instruments_with_unknown_scope"],
                           "message": f"{pick['version_id']} lacks in-force amendment(s) {', '.join(pick['missing_instruments_with_unknown_scope'])} whose full list of "
                                      "changed articles is not known; ANY provision of this version may be out of date, including ones not named elsewhere."})
        fi = footnote_index(db, pick["version_id"])
        fut = {}
        for art, fns in fi["articles"].items():
            for f in fns:
                if f.get("future_effect"):
                    for a in {art, f.get("line_in")} - {None}:
                        fut.setdefault(a, set()).add(f["future_effect"])
        if fut:
            issues.append({"id": f"{sid}:future-text", "kind": "future_text", "version_id": pick["version_id"],
                           "provisions": sorted(_key(sid, a) for a in fut if not a.startswith("Front")),
                           "message": "Footnotes inside these passages contain amended text that applies only later ("
                                      + "; ".join(sorted({x for v in fut.values() for x in v})) + "). Quote the article body as in force today; "
                                      "never present the footnote text as current law."})

    for c in claims["conflicts"]:
        provs = sorted({_key(x["source_id"], None) if (x.get("locator") or "").startswith("Paragraph")       # web pages: whole page
                        else _key(x["source_id"], (x.get("locator") or "").split(",")[0].replace("Article ", "") or None)
                        for x in c["claims"] if x["integrity"] == "quote_found"})
        issues.append({"id": f"conflict:{c['topic']}", "kind": "conflict", "version_id": None, "provisions": provs, "topic": c["topic"],
                       "values": c["values"], "claims": [x["claim_id"] for x in c["claims"]],
                       "message": "Official sources state different values ("
                                  + "; ".join(f"{x['source_id']}: {x['value']} {x['unit']}" for x in c["claims"])
                                  + "). Do not state one value; show both with sources; a qualified reviewer decides."})
    # Monitor alerts (rag_c monitor): an official source changed and nobody has reviewed it yet. Until a person reviews
    # the change (and, if needed, a new version is collected and approved), the affected provisions cannot be certified.
    CHANGE_KINDS = {"changed_substantive_in_scope", "changed_substantive", "conflict_provision_changed",
                    "differs_from_collected_version", "removed"}
    for al in alerts or []:
        if al.get("kind") not in CHANGE_KINDS or al.get("reviewed"):
            continue
        provs = sorted(set(al.get("provisions") or []) or ({_key(al["source_id"], None)} if al.get("source_id") else set()))
        if not provs:
            continue
        issues.append({"id": f"monitor:{al['kind']}:{al.get('at', '')}:{al['url']}", "kind": "source_changed", "version_id": al.get("version_id"),
                       "provisions": provs, "alert_kind": al["kind"], "detected_at": al.get("at"),
                       "message": f"The official source changed ({al['kind']}, detected {al.get('at')}): {al.get('detail', '')}. "
                                  "Pending review; do not rely on the stored text until a person has reviewed the change."})
    for f in claims["integrity_failures"]:
        issues.append({"id": f"claim:{f['claim_id']}", "kind": "unverified", "version_id": None, "provisions": [_key(f["source_id"], None)],
                       "message": f"Registered claim {f['claim_id']} could not be verified in the knowledge base: {f['integrity']}."})

    for v in inv["versions"]:
        c = v["coverage"]
        if v["version_id"] == current.get(v["source_id"], {}).get("version_id") and (c["missing_article_numbers"] or c["headings_merged_into_other_passages"]):
            arts = sorted({str(n) for n in c["missing_article_numbers"]} | {str(m["article"]) for m in c["headings_merged_into_other_passages"]})
            issues.append({"id": f"{v['source_id']}:extraction", "kind": "extraction", "version_id": v["version_id"],
                           "provisions": [_key(v["source_id"], a) for a in arts],
                           "message": f"In this database, {', '.join('Art. ' + a for a in arts)} of {v['version_id']} has no passage of its own "
                                      "(heading merged into another passage). Cite by text, not by locator, or use a D10 build."})

    from .inventory import connect_ro
    con = connect_ro(db)
    try:
        db_status = dict(con.execute("SELECT version_id, status FROM source_versions").fetchall())
        approved_in_audit = {r[0] for r in con.execute("SELECT entity_id FROM audit_events WHERE event = 'source_approved'")}
        fts_ok = con.execute("SELECT COUNT(*) FROM passages p JOIN passages_fts f ON f.passage_id = p.passage_id "
                             "WHERE f.text = p.text AND f.locator = p.locator").fetchone()[0] == inv["counts"]["passages"] == inv["fts_rows"]
    finally:
        con.close()
    if not fts_ok:
        issues.append({"id": "integrity:fts", "kind": "extraction", "version_id": None, "provisions": [_key(s, None) for s in current],
                       "message": "The search index does not match the passages (rows missing, extra or altered). Rebuild into a new file."})
    versions = []
    for v in amap["versions"]:
        reg_v = next(x for s in reg["sources"] for x in s.get("versions", []) if x["version_id"] == v["version_id"])
        src = next(x for x in reg["sources"] if x["source_id"] == v["source_id"])
        versions.append({"version_id": v["version_id"], "source_id": v["source_id"], "kb_status": v["kb_status"],
                         "language": src.get("language"), "translation_status": src.get("translation_status"),
                         "verification_status": reg_v.get("verification_status"), "extraction_label": reg_v.get("extraction_label"),
                         # approved only when the register, the database status AND the audit trail agree (QA2 item 2)
                         "approved": v["kb_status"] == "approved" and db_status.get(v["version_id"]) == "approved"
                                     and v["version_id"] in approved_in_audit,
                         "register_status": v["kb_status"], "database_status": db_status.get(v["version_id"]),
                         "selected_as_current": current[v["source_id"]]["version_id"] == v["version_id"],
                         "outdated": v["outdated"], "fta_currency": v["fta_currency"], "superseded_by": v["superseded_by_effective_date"]})
    db_md5 = hashlib.md5(Path(db).read_bytes()).hexdigest()
    return {"_meta": {"schema_version": SCHEMA_VERSION, "maintained_by": "Workstream C (generated by compliance_agent.rag_c validity)",
                      "generated_for_date": as_of, "register_version": reg.get("register_version"),
                      "database_md5": db_md5, "database_passages": inv["counts"]["passages"],
                      "rule": "A retrieval result that needs any provision listed in issues[] can never be certified 'complete'. "
                              "Nothing in this file is approved by a qualified reviewer.",
                      "coverage_disclaimer": "No issue for a provision does NOT mean the provision is complete, current or correct: it only "
                                             "means Workstream C has no recorded problem. The source landscape is not known to be complete.",
                      "known_caveats": ["Footnote lines sit inside article passages, sometimes in the wrong article (gap G8).",
                                        "English texts are self-described unofficial translations; the Arabic text prevails (gap G9)."],
                      "key_format": "SOURCE|ARTICLE, e.g. FTA-VAT-DL8|48, FTA-VAT-DL8|79 (bis); SOURCE|* = the whole source",
                      "not_legal_advice": True},
            "current_versions": current, "versions": versions, "issues": issues,
            "claims": claims["claims"], "approved_versions": [v["version_id"] for v in versions if v["approved"]]}


def issues_for(validity: dict, source_id: str, article: str | None) -> list[dict]:
    """Issues touching one provision (exact key or the whole-source key)."""
    keys = {_key(source_id, article), _key(source_id, None)}
    if article and article.startswith("Paragraph"):
        keys.add(_key(source_id, None))
    return [i for i in validity["issues"] if keys & set(i["provisions"])]
