"""Citation integrity and source-to-answer traceability. Read-only.

check_citation: one {passage_id, quote} -> passage exists? quote found (same normalisation as answer.check)? which
document, captured version, raw file hash, register entry and validity issues it rests on.
trace_ledger: the same for every citation in every recorded answer of the experiment ledger (opened read-only)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ..sources import normalize
from .inventory import article_key, connect_ro
from .validity import issues_for


def _article_label(locator: str) -> str | None:
    k = article_key(locator)
    if k:
        return f"{k[0]}{' (' + k[1] + ')' if k[1] else ''}"
    return locator.split(",")[0] if locator.startswith("Paragraph") else None


def check_citation(con, citation: dict, validity: dict | None = None) -> dict:
    pid, quote = citation.get("passage_id"), citation.get("quote") or ""
    row = con.execute(
        "SELECT p.passage_id, p.locator, p.text, p.label, p.version_id, d.doc_id, d.source_id, d.sha256, d.raw_path, d.url, "
        "v.status FROM passages p JOIN documents d ON d.doc_id = p.doc_id LEFT JOIN source_versions v ON v.version_id = p.version_id "
        "WHERE p.passage_id = ?", (pid,)).fetchone()
    if row is None:
        return {"passage_id": pid, "result": "PASSAGE_NOT_FOUND", "issues": [],
                "detail": "passage id not in this database (ids differ between builds: resolve by source and locator)"}
    found = bool(normalize(quote)) and normalize(quote) in normalize(row["text"])
    art = _article_label(row["locator"])
    issues = issues_for(validity, row["source_id"], art) if validity else []
    current = (validity or {}).get("current_versions", {}).get(row["source_id"], {}).get("version_id")
    flags = []
    if not found:
        flags.append("QUOTE_NOT_FOUND")
    if row["status"] != "approved":
        flags.append(f"source_{row['status']}")
    if row["label"] == "UNVERIFIED_EXTRACTION":
        flags.append("unverified_extraction")
    if current and row["version_id"] != current:
        flags.append(f"not_current_version (current: {current})")
    flags += [f"{i['kind']}:{i['id']}" for i in issues]
    return {"passage_id": pid, "result": "quote_found" if found else "QUOTE_NOT_FOUND", "source_id": row["source_id"],
            "version_id": row["version_id"], "locator": row["locator"], "article": art, "doc_id": row["doc_id"],
            "raw_sha256": row["sha256"], "raw_path": row["raw_path"], "url": row["url"], "source_status": row["status"],
            "issues": [i["id"] for i in issues], "flags": flags,
            "certifiable": found and row["status"] == "approved" and not issues and (not current or row["version_id"] == current)}


def trace_ledger(ledger_db, kb_db, validity: dict | None = None) -> dict:
    led = connect_ro(ledger_db)
    con = connect_ro(kb_db)
    try:
        rows = led.execute("SELECT call_id, run_id, question_id, model_alias, parsed_json FROM llm_calls "
                           "WHERE status = 'ok' AND parsed_json IS NOT NULL ORDER BY call_id").fetchall()
        answers, results = [], Counter()
        for r in rows:
            try:
                parsed = json.loads(r["parsed_json"])
            except (TypeError, ValueError):
                results["unparseable_answer"] += 1
                continue
            cites = [check_citation(con, c, validity) for c in parsed.get("citations") or []]
            for c in cites:
                results[c["result"]] += 1
            touched = sorted({i for c in cites for i in c.get("issues", [])})
            answers.append({"call_id": r["call_id"], "question_id": r["question_id"], "model": r["model_alias"],
                            "answer_status": parsed.get("answer_status"), "citations": len(cites),
                            "quotes_not_found": sum(c["result"] != "quote_found" for c in cites),
                            "validity_issues": touched, "certifiable": bool(cites) and all(c["certifiable"] for c in cites)})
    finally:
        led.close()
        con.close()
    by_issue = Counter(i for a in answers for i in a["validity_issues"])
    return {"answers": len(answers), "citations": sum(results.values()), "citation_results": dict(results),
            "answers_touching_validity_issues": sum(bool(a["validity_issues"]) for a in answers),
            "answers_by_issue": dict(by_issue), "certifiable_answers": sum(a["certifiable"] for a in answers),
            "rows": answers}
