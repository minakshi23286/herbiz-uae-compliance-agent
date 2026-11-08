"""Legal value claims (deadlines, thresholds) and source-conflict detection. Read-only.

A claim is a value a source states for a topic ("vat.deregistration.mandatory_application_deadline" = 20 business_days,
ER Art. 14). Registered claims live in the source register. This module
  * checks each claim's quote is really in the cited knowledge-base passage (claim integrity),
  * finds every number+unit statement in the knowledge base (fact inventory) so a claim can be cross-checked,
  * reports a CONFLICT when two claims on one topic give different values. It never picks a winner."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..sources import normalize
from .inventory import article_key, connect_ro
from .register import REGISTER

WORD_NUM = {"ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "sixty": 60, "ninety": 90}
DAYS_RX = re.compile(r"(\d{1,3})\s*(?:\((\w+)\)\s*)?(business|working)\s+days", re.I)
AED_RX = re.compile(r"AED\s*([\d,]{3,})", re.I)


def _passages(con, version_id: str, article: str | None):
    rows = con.execute("SELECT passage_id, locator, text FROM passages WHERE version_id = ? ORDER BY seq", (version_id,)).fetchall()
    if article is None:
        return rows
    if article.startswith("Paragraph"):
        return [r for r in rows if r["locator"] == article]
    m = re.match(r"(\d+)(?: \((\w+)\))?$", article)
    want = (int(m.group(1)), m.group(2) or "") if m else None
    return [r for r in rows if article_key(r["locator"]) == want]


def fact_inventory(db, version_ids: list[str] | None = None) -> list[dict]:
    """Every '<N> (<words>) business/working days' and 'AED <amount>' statement, with its passage and locator."""
    con = connect_ro(db)
    try:
        q = "SELECT version_id, passage_id, locator, text FROM passages"
        rows = con.execute(q).fetchall()
    finally:
        con.close()
    facts = []
    for r in rows:
        if version_ids and r["version_id"] not in version_ids:
            continue
        text = re.sub(r"\s+", " ", r["text"])
        for m in DAYS_RX.finditer(text):
            n, word = int(m.group(1)), (m.group(2) or "").lower()
            facts.append({"version_id": r["version_id"], "passage_id": r["passage_id"], "locator": r["locator"],
                          "value": n, "unit": "business_days", "words": word or None,
                          "digits_words_agree": (WORD_NUM.get(word) == n) if word in WORD_NUM else None,
                          "context": text[max(0, m.start() - 90):m.end() + 40]})
        for m in AED_RX.finditer(text):
            facts.append({"version_id": r["version_id"], "passage_id": r["passage_id"], "locator": r["locator"],
                          "value": int(m.group(1).replace(",", "")), "unit": "AED", "words": None, "digits_words_agree": None,
                          "context": text[max(0, m.start() - 90):m.end() + 40]})
    return facts


def check_claims(db, register_path: Path = REGISTER) -> dict:
    reg = json.loads(Path(register_path).read_text(encoding="utf-8"))
    claims = reg.get("claims", [])
    con = connect_ro(db)
    checked = []
    try:
        for c in claims:
            row = {"claim_id": c["claim_id"], "topic": c["topic"], "value": c["value"], "unit": c["unit"],
                   "source_id": c["source_id"], "in_knowledge_base": c.get("in_knowledge_base", True)}
            if not c.get("in_knowledge_base", True):
                row.update(integrity="external", detail="source not in the knowledge base; quote recorded with evidence only")
            else:
                ps = _passages(con, c["version_id"], c.get("article"))
                hit = next((p for p in ps if normalize(c["quote"]) in normalize(p["text"])), None)
                row.update(integrity="quote_found" if hit else "QUOTE_NOT_FOUND",
                           passage_id=hit["passage_id"] if hit else None, locator=hit["locator"] if hit else None,
                           detail=None if hit else f"quote not in {c['version_id']} article {c.get('article')} ({len(ps)} passages searched)")
                if hit and str(c["value"]) not in re.sub(r"[,\s]", "", hit["text"]):
                    row.update(integrity="VALUE_NOT_IN_PASSAGE")
            checked.append(row)
    finally:
        con.close()
    topics: dict[str, list[dict]] = {}
    for r in checked:
        topics.setdefault(r["topic"], []).append(r)
    conflicts = []
    for topic, rows in sorted(topics.items()):
        values = {(r["value"], r["unit"]) for r in rows}
        if len(values) > 1:
            conflicts.append({"topic": topic, "values": sorted([list(v) for v in values]),
                              "claims": [{k: r.get(k) for k in ("claim_id", "source_id", "value", "unit", "locator", "integrity")} for r in rows],
                              "rule": "sources disagree: do not state one value; show both with sources; reviewer decides"})
    return {"claims": checked, "conflicts": conflicts,
            "integrity_failures": [r for r in checked if r["integrity"] not in ("quote_found", "external")],
            "topics": sorted(topics)}
