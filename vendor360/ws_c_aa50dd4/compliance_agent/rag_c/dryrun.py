"""Safe ingestion dry run: rebuild the corpus offline from copies of data/raw/ and the lock, in a temporary folder,
then check it reproduces the reference database passage for passage (same documents, locators and text hashes).

The real data/raw/, lock and databases are only read. Network access is refused. The build is thrown away unless
--out names a NEW file (never an existing file, never the authoritative database)."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

from ..clock import SystemClock
from ..dbsafety import AuthoritativeDatabaseError, copy_readonly, is_authoritative
from ..engine import Engine
from ..kb import CollectError, KnowledgeBase
from ..store import Store
from .inventory import DATA, LOCK, ROOT, connect_ro

MANIFEST = ROOT / "knowledge_base" / "CL_source_manifest.json"


def _no_network(url):
    raise CollectError(f"refused: dry run is offline ({url})")


def passage_fingerprints(db) -> dict:
    con = connect_ro(db)
    try:
        return {(r["doc_id"], r["seq"]): (r["locator"], hashlib.sha256(r["text"].encode()).hexdigest())
                for r in con.execute("SELECT p.doc_id, p.seq, p.locator, p.text FROM passages p JOIN source_versions v "
                                     "ON v.version_id = p.version_id WHERE v.origin_label = 'REAL_OFFICIAL_SOURCE'")}
    finally:
        con.close()


def diff_builds(reference_db, build_db) -> dict:
    """Content diff between two builds, matched by (doc_id, locator) — passage ids and seq can shift when splitting changes.
    Reports passages only in one build, passages whose text changed, and documents whose passage count changed."""
    def load(db):
        con = connect_ro(db)
        try:
            rows = con.execute("SELECT p.doc_id, p.locator, p.text FROM passages p JOIN source_versions v "
                               "ON v.version_id = p.version_id WHERE v.origin_label = 'REAL_OFFICIAL_SOURCE' ORDER BY p.doc_id, p.seq").fetchall()
        finally:
            con.close()
        out, per_doc = {}, {}
        for r in rows:
            out[(r["doc_id"], r["locator"])] = hashlib.sha256(r["text"].encode()).hexdigest()
            per_doc[r["doc_id"]] = per_doc.get(r["doc_id"], 0) + 1
        return out, per_doc
    (a, ca), (b, cb) = load(reference_db), load(build_db)
    return {"only_in_reference": sorted(map(list, a.keys() - b.keys())), "only_in_build": sorted(map(list, b.keys() - a.keys())),
            "text_changed": sorted(list(k) for k in a.keys() & b.keys() if a[k] != b[k]),
            "unchanged": sum(1 for k in a.keys() & b.keys() if a[k] == b[k]),
            "passage_counts": {d: {"reference": ca.get(d), "build": cb.get(d)} for d in sorted(set(ca) | set(cb)) if ca.get(d) != cb.get(d)}}


def dry_run(reference_db, out: Path | None = None, raw_dir: Path = DATA / "raw", lock_path: Path = LOCK,
            manifest_path: Path = MANIFEST) -> dict:
    if out is not None:
        out = Path(out)
        if is_authoritative(out):
            raise AuthoritativeDatabaseError("the dry-run output cannot be the authoritative database")
        if out.is_symlink():
            raise FileExistsError(f"refused: {out} is a symlink; give a plain new file path")
        if out.exists():
            raise FileExistsError(f"refused: {out} exists; choose a new file (earlier builds are kept as evidence)")
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        shutil.copytree(raw_dir, work / "raw")
        shutil.copy2(lock_path, work / "lock.json")
        build = work / "build.sqlite3"
        e = Engine(Store(build), SystemClock())
        kb = KnowledgeBase(e, data_dir=work, fetch=_no_network, lock_path=work / "lock.json")
        results = kb.rebuild(json.loads(Path(manifest_path).read_text(encoding="utf-8")))
        e.s.close()
        new, ref = passage_fingerprints(build), passage_fingerprints(reference_db)
        diff_locator = sorted(k for k in new.keys() & ref.keys() if new[k][0] != ref[k][0])
        diff_text = sorted(k for k in new.keys() & ref.keys() if new[k][1] != ref[k][1])
        con = sqlite3.connect(build)
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
        kept = None
        if out is not None:
            kept = str(copy_readonly(build, out))
    report = {
        "outcomes": [{k: r.get(k) for k in ("source_id", "outcome", "version_id", "passages")} for r in results],
        "build_passages": len(new), "reference_passages": len(ref),
        "only_in_build": [list(k) for k in sorted(new.keys() - ref.keys())][:20],
        "only_in_reference": [list(k) for k in sorted(ref.keys() - new.keys())][:20],
        "locator_differences": [list(k) for k in diff_locator][:20],
        "text_differences": [list(k) for k in diff_text][:20],
        "integrity": integrity, "kept_build": kept,
    }
    report["reproducible"] = (not report["only_in_build"] and not report["only_in_reference"]
                              and not diff_locator and not diff_text and integrity == "ok")
    return report
