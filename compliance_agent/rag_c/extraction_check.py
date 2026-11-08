"""Article-level extraction validation (read-only, offline).

1. Structure: locator grammar (B/C contract), article numbering gaps, merged headings, page ranges, empty passages,
   duplicate article blocks.
2. Second-extractor agreement: the same raw PDF is extracted again with poppler `pdftotext` (already installed; not
   used to build the knowledge base) and compared with the stored passages article by article: word similarity and,
   above all, the set of numbers (amounts, days, article cross-references) in each article.
3. Headings and chapter ("Title"/"Chapter") boundaries per version, for Workstream B (request C-5).
Arabic: the knowledge base holds English only. Arabic PDFs are not processed here: their text layer comes out with
letters out of order (seen on the FTA Arabic ER, 16 Oct 2026), so Arabic checks must use the rendered page."""
from __future__ import annotations

import difflib
import re
import shutil
import subprocess
from pathlib import Path

from .inventory import DATA, article_key, connect_ro

LOCATOR_RX = re.compile(r"^(?:Article \d+(?: \((?:bis|ter|quater)\))?, (?:p\. \d+|pp\. \d+-\d+)(?:, part \d+)?"
                        r"|Paragraph \d+|Front matter, p\. \d+|Page \d+)$")
HEADING_LINE = re.compile(r"^Article\s*\(?\s*(\d+)\s*\)?((?:\s*\((?:bis|repeated)\))?)\s*[–—-]\s*(.+?)\s*\d{0,2}\s*$", re.M)
TITLE_LINE = re.compile(r"^\s*((?:Title|Chapter|Part)\s+[A-Za-z]+(?:\s*[–—-]\s*[^\n]+)?)\s*$", re.M)
NUM_RX = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _key_str(locator: str) -> str | None:
    k = article_key(locator)
    return f"{k[0]}{' (' + k[1] + ')' if k[1] else ''}" if k else None


def structure(db, version_id: str) -> dict:
    con = connect_ro(db)
    try:
        rows = con.execute("SELECT seq, locator, page_start, page_end, text FROM passages WHERE version_id = ? ORDER BY seq",
                           (version_id,)).fetchall()
    finally:
        con.close()
    bad_locators = [r["locator"] for r in rows if not LOCATOR_RX.match(r["locator"])]
    empty = [r["locator"] for r in rows if len(r["text"].strip()) < 20]
    pages_backwards = [r["locator"] for prev, r in zip(rows, rows[1:]) if (r["page_start"] or 0) < (prev["page_start"] or 0)]
    seen, non_contiguous, last = {}, [], None
    for r in rows:
        k = _key_str(r["locator"])
        if k is None:
            last = None
            continue
        if k in seen and last != k:
            non_contiguous.append(k)
        seen[k] = True
        last = k
    nums = sorted({int(re.match(r"\d+", k).group()) for k in seen})
    gaps = [n for n in range(1, nums[-1] + 1) if n not in nums] if nums else []
    return {"version_id": version_id, "passages": len(rows), "articles": len(seen), "missing_article_numbers": gaps,
            "locator_grammar_violations": bad_locators, "near_empty_passages": empty,
            "page_order_violations": pages_backwards, "article_split_non_contiguous": sorted(set(non_contiguous)),
            "pass": not (bad_locators or empty or pages_backwards or non_contiguous)}


def _pdftotext(path: Path) -> list[str] | None:
    exe = shutil.which("pdftotext")
    if not exe:
        return None
    # reading order (no -layout), then the knowledge base's own running-header removal, so both sides are cleaned alike
    out = subprocess.run([exe, str(path), "-"], capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        return None
    from ..kb import strip_running_headers
    pages, _ = strip_running_headers(out.stdout.split("\f"))
    return pages


def _second_units(pages: list[str]) -> dict[str, str]:
    """Split the pdftotext output by the same heading rule as the knowledge base (kb.ARTICLE_RX)."""
    from ..kb import ARTICLE_RX, footnote_on_page
    units: dict[str, str] = {}
    cur = None
    for page in pages:
        page = "\n".join(l.strip() for l in page.splitlines())
        pos = 0
        for m in ARTICLE_RX.finditer(page):
            if m.group(4) and not footnote_on_page(page, m.group(4)):
                continue
            if cur:
                units[cur] = units.get(cur, "") + page[pos:m.start()]
            suffix = m.group(2).strip()
            cur = f"{int(m.group(1))}{' ' + suffix if suffix else ''}"
            pos = m.start()
        if cur:
            units[cur] = units.get(cur, "") + page[pos:]
    return units


def _unexplained(extra: set[str], other: set[str], markers: set[str]) -> set[str]:
    """A number counts as layout noise only when it differs from a number in the other text by a KNOWN footnote marker of
    this document glued at the start or end ('4615' = footnote 46 + '15'), or when it is itself a known footnote marker.
    Anything else (e.g. 20 vs 200) stays a mismatch."""
    keep = set()
    for n in extra:
        if n in markers:
            continue
        glued = False
        for o in other:
            if n != o and n.endswith(o) and n[:-len(o)] in markers:
                glued = True
            if n != o and n.startswith(o) and n[len(o):] in markers:
                glued = True
            if o != n and o.endswith(n) and o[:-len(n)] in markers:
                glued = True
            if o != n and o.startswith(n) and o[len(n):] in markers:
                glued = True
        if not glued:
            keep.add(n)
    return keep


def second_extractor_agreement(db, version_id: str, data_dir: Path = DATA, min_ratio: float = 0.95) -> dict:
    con = connect_ro(db)
    try:
        d = con.execute("SELECT raw_path FROM documents WHERE version_id = ?", (version_id,)).fetchone()
        rows = con.execute("SELECT locator, text FROM passages WHERE version_id = ? ORDER BY seq", (version_id,)).fetchall()
    finally:
        con.close()
    if not d or not d["raw_path"].endswith(".pdf"):
        return {"version_id": version_id, "status": "not_applicable", "detail": "not a PDF"}
    pages = _pdftotext(Path(data_dir) / d["raw_path"])
    if pages is None:
        return {"version_id": version_id, "status": "unavailable", "detail": "pdftotext not installed or failed"}
    kb_units: dict[str, str] = {}
    for r in rows:
        k = _key_str(r["locator"])
        if k:
            kb_units[k] = kb_units.get(k, "") + " " + r["text"]
    other = _second_units(pages)
    words = lambda t: re.findall(r"[a-z]+", t.lower())
    footnote_lines = re.compile(r"^\s*\d{1,3}\s+(?:Article|Clause|Paragraph|Item|Definition)\b.*$", re.M | re.I)
    numbers = lambda t: sorted(n.replace(",", "") for n in NUM_RX.findall(footnote_lines.sub(" ", t)) if len(n.replace(",", "")) >= 2)
    marker_rx = re.compile(r"^\s*(\d{1,3})\s+(?:Article|Clause|Paragraph|Item|Definition|This|The)\b.*?(?:amended|added|repealed|replaced|inserted)", re.M | re.I)
    # ONLY real footnote markers (QA E2, 17 Oct 2026): page numbers are no longer excused, they are stripped as running
    # headers. A marker excuses a number only when glued to it, so 30 vs 15 or 12 vs 6 can never be explained away.
    markers = {m for t in pages for m in marker_rx.findall(t)}
    rows_out, low, num_diff, count_issues = [], [], [], []
    for k, text in kb_units.items():
        o = other.get(k)
        if o is None:
            rows_out.append({"article": k, "status": "missing_in_second_extractor"})
            continue
        ratio = difflib.SequenceMatcher(None, words(text), words(o), autojunk=False).ratio()
        from collections import Counter
        ca, cb = Counter(numbers(text)), Counter(numbers(o))
        na, nb = set(ca), set(cb)
        only_a, only_b = _unexplained(na - nb, nb, markers), _unexplained(nb - na, na, markers)
        count_diff = sorted(n for n in na & nb if ca[n] != cb[n] and n not in markers)   # same number, different count
        row = {"article": k, "word_similarity": round(ratio, 4), "numbers_only_in_kb": sorted(only_a), "numbers_only_in_second": sorted(only_b),
               "explained_by_footnote_markers": sorted((na ^ nb) - only_a - only_b), "count_differences": count_diff}
        if ratio < min_ratio:
            low.append(k)
        if only_a or only_b:
            num_diff.append(k)
        if count_diff:
            count_issues.append(k)
        rows_out.append(row)
    return {"version_id": version_id, "status": "checked", "second_extractor": "pdftotext (poppler)",
            "articles_compared": len(rows_out), "articles_only_in_second": sorted(set(other) - set(kb_units)),
            "below_similarity_threshold": low, "number_mismatches": num_diff, "number_count_differences": count_issues,
            "threshold": min_ratio,
            "pass": not low and not num_diff and all(r.get("status") != "missing_in_second_extractor" for r in rows_out),
            "rows": rows_out}


def headings(db, version_id: str) -> dict:
    """Article titles and Title/Chapter boundaries per version (Workstream B request C-5)."""
    con = connect_ro(db)
    try:
        rows = con.execute("SELECT locator, text FROM passages WHERE version_id = ? ORDER BY seq", (version_id,)).fetchall()
    finally:
        con.close()
    out, chapter = [], None
    for r in rows:
        for t in TITLE_LINE.finditer(r["text"]):
            chapter = re.sub(r"\s+", " ", t.group(1)).strip()
        k = _key_str(r["locator"])
        if not k or any(x["article"] == k for x in out):
            continue
        m = HEADING_LINE.search(r["text"])
        title = re.sub(r"\s+", " ", m.group(3)).strip() if m and f"{int(m.group(1))}{' ' + m.group(2).strip() if m.group(2).strip() else ''}" == k else None
        out.append({"article": k, "title": title, "chapter": chapter, "first_locator": r["locator"]})
    return {"version_id": version_id, "articles": out, "untitled": [x["article"] for x in out if not x["title"]]}
