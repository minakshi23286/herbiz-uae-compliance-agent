"""Read-only inventory of the knowledge base: versions, passages, article coverage, locator problems, duplicates."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
LOCK = ROOT / "knowledge_base" / "CL_collected_lock.json"

ARTICLE = re.compile(r"^Article (\d+)(?: \((bis|ter|quater)\))?")
# A heading whose footnote marker was glued on ("Article 1 1") is not split out and stays inside another passage.
MERGED_HEADING = re.compile(r"^Article (\d+) \d+\s*$", re.M)


def connect_ro(path) -> sqlite3.Connection:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def article_key(locator: str):
    m = ARTICLE.match(locator or "")
    return (int(m.group(1)), m.group(2) or "") if m else None


def coverage(con: sqlite3.Connection, version_id: str) -> dict:
    rows = con.execute("SELECT locator, text FROM passages WHERE version_id = ? ORDER BY seq", (version_id,)).fetchall()
    keys = [k for k in (article_key(r["locator"]) for r in rows) if k]
    nums = sorted({n for n, _ in keys})
    gaps = [n for n in range(1, nums[-1] + 1) if n not in set(nums)] if nums else []
    merged = []
    for r in rows:
        if article_key(r["locator"]) is None:
            merged += [{"article": int(n), "inside": r["locator"]} for n in MERGED_HEADING.findall(r["text"])]
    return {
        "version_id": version_id, "passages": len(rows),
        "article_passages": len(keys), "other_passages": len(rows) - len(keys),
        "articles_distinct": len(set(keys)), "first_article": nums[0] if nums else None,
        "last_article": nums[-1] if nums else None,
        "bis_articles": sorted(f"{n} ({s})" for n, s in set(keys) if s),
        "missing_article_numbers": gaps,
        "headings_merged_into_other_passages": merged,
        "split_articles": sorted({n for n, _ in keys if sum(1 for k in keys if k[0] == n) > 1}),
    }


def inventory(db) -> dict:
    con = connect_ro(db)
    try:
        versions = [dict(r) for r in con.execute(
            "SELECT v.version_id, v.source_id, v.status, v.publication_date, v.effective_date, v.document_title, "
            "d.doc_id, d.sha256, d.raw_path, d.url, d.retrieved_at, d.extraction_status, d.extractor, d.pages, d.extraction_note "
            "FROM source_versions v LEFT JOIN documents d ON d.version_id = v.version_id "
            "WHERE v.origin_label = 'REAL_OFFICIAL_SOURCE' ORDER BY v.source_id, v.version_id")]
        for v in versions:
            v["coverage"] = coverage(con, v["version_id"])
        attempts = [dict(r) for r in con.execute(
            "SELECT source_id, outcome, COUNT(*) n, MAX(at) last_at FROM collection_attempts GROUP BY source_id, outcome ORDER BY source_id")]
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("source_versions", "documents", "passages", "obligations", "reviewer_signoffs", "audit_events")}
        statuses = dict(con.execute("SELECT status, COUNT(*) FROM source_versions WHERE origin_label='REAL_OFFICIAL_SOURCE' GROUP BY status").fetchall())
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fts_rows = con.execute("SELECT COUNT(*) FROM passages_fts").fetchone()[0]
        triggers = sorted(r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='trigger'"))
    finally:
        con.close()
    return {"database": str(db), "integrity": integrity, "counts": counts, "fts_rows": fts_rows,
            "real_version_status": statuses, "triggers": triggers, "versions": versions, "collection_attempts": attempts}


def duplicates(db) -> dict:
    """Same raw bytes under two documents, same passage text in two places, same URL captured more than once."""
    con = connect_ro(db)
    try:
        same_bytes = [dict(r) for r in con.execute(
            "SELECT sha256, group_concat(doc_id, ', ') docs, COUNT(*) n FROM documents GROUP BY sha256 HAVING n > 1")]
        same_url = [dict(r) for r in con.execute(
            "SELECT url, group_concat(doc_id, ', ') docs, COUNT(*) n FROM documents GROUP BY url HAVING n > 1")]
        by_text: dict[str, list[str]] = {}
        for r in con.execute("SELECT passage_id, version_id, text FROM passages"):
            norm = re.sub(r"\s+", " ", r["text"]).strip().lower()
            by_text.setdefault(hashlib.sha256(norm.encode()).hexdigest(), []).append(f"{r['version_id']}|{r['passage_id']}")
        within, across = [], 0
        for ids in by_text.values():
            if len(ids) < 2:
                continue
            versions = {i.split("|")[0] for i in ids}
            if len(versions) < len(ids):        # repeated inside one version: a real duplicate passage
                within.append(ids)
            else:
                across += 1                       # unchanged text carried into a later version: expected
    finally:
        con.close()
    return {"same_raw_bytes": same_bytes, "same_url_multiple_captures": same_url,
            "identical_passages_within_one_version": within, "passages_unchanged_across_versions": across}


def hashes(lock_path: Path = LOCK, data_dir: Path = DATA) -> dict:
    lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    rows, seen = [], {}
    for d in lock["documents"]:
        p = Path(data_dir) / d["raw_path"]
        actual = sha256_file(p) if p.exists() else None
        rows.append({"source_id": d["source_id"], "raw_path": d["raw_path"], "expected": d["sha256"],
                     "status": "missing" if actual is None else ("ok" if actual == d["sha256"] else "MISMATCH")})
        seen.setdefault(d["sha256"], []).append(d["raw_path"])
    on_disk = {str(p.relative_to(data_dir)) for p in (Path(data_dir) / "raw").rglob("*") if p.is_file()}
    unlocked = sorted(on_disk - {d["raw_path"] for d in lock["documents"]})
    return {"files": rows, "ok": sum(r["status"] == "ok" for r in rows), "total": len(rows),
            "duplicate_hashes_in_lock": {k: v for k, v in seen.items() if len(v) > 1},
            "raw_files_not_in_lock": unlocked}


def compare(db, old: str, new: str) -> dict:
    """Article-level difference between two versions, using the existing KnowledgeBase.compare (cosmetic vs substantive,
    footnote-aware). It runs on a throwaway copy because Store() opens its file for writing."""
    import tempfile
    from ..clock import SystemClock
    from ..dbsafety import copy_readonly
    from ..engine import Engine
    from ..kb import KnowledgeBase
    from ..store import Store
    with tempfile.TemporaryDirectory() as d:
        tmp = copy_readonly(Path(db), Path(d) / "compare.sqlite3")
        e = Engine(Store(tmp), SystemClock())
        try:
            for v in (old, new):
                if not e.s.one("SELECT 1 AS x FROM passages WHERE version_id = ?", (v,)):
                    raise ValueError(f"unknown version: {v}")
            res = KnowledgeBase(e, data_dir=Path(d), lock_path=Path(d) / "lock.json").compare(old, new)
        finally:
            e.s.close()
    res["substantive_units"] = sorted((r["unit"] for r in res["rows"] if r["change"] == "substantive"), key=_order)
    return res


def _order(key: str):
    m = re.match(r"Article (\d+)", key)
    return (0, int(m.group(1)), key) if m else (1, 0, key)
