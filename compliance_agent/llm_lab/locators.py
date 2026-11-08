"""Locator grammar from the Workstream C interface contract v0.1 (docs/rag/CL_RAG_ARCHITECTURE_WS_C.md §11, branch
ws-c-rag-foundation):  Article <N>[ (bis|ter|quater)], p. <P> | pp. <P1>-<P2> [, part <K>] · Paragraph <N> · Front matter, p. <P>.
Workstream B parses locators only through this module, so a contract change is a change in one place."""
from __future__ import annotations

import re

ARTICLE_RX = re.compile(r"^Article (\d+)(?: \((bis|ter|quater)\))?(?:,|$)")
PARAGRAPH_RX = re.compile(r"^Paragraph (\d+)$")


def parse(locator: str) -> dict:
    m = ARTICLE_RX.match(locator)
    if m:
        part = re.search(r", part (\d+)$", locator)
        return {"kind": "article", "number": int(m.group(1)), "suffix": m.group(2), "part": int(part.group(1)) if part else 1}
    m = PARAGRAPH_RX.match(locator)
    if m:
        return {"kind": "paragraph", "number": int(m.group(1)), "suffix": None, "part": 1}
    return {"kind": "other", "number": None, "suffix": None, "part": 1}


def article_key(source_id: str, locator: str) -> str | None:
    """'FTA-VAT-DL8|13' or 'FTA-VAT-DL8|79 (bis)'; None for non-article passages."""
    p = parse(locator)
    if p["kind"] != "article":
        return None
    return f"{source_id}|{p['number']}" + (f" ({p['suffix']})" if p["suffix"] else "")


def key(source_id: str, article) -> str:
    """Key for a provision reference (source_id, number|'79 (bis)'|None). None = the whole source (e.g. the FTA page)."""
    return f"{source_id}|{article}" if article is not None else f"{source_id}|*"


def matches(source_id: str, locator: str, ref_key: str) -> bool:
    src, art = ref_key.split("|", 1)
    if src != source_id:
        return False
    return art == "*" or article_key(source_id, locator) == ref_key
