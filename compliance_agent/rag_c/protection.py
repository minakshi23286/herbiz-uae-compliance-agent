"""Database protection: read-only status inspection, and reversible hardening that is applied ONLY to copies.

Layers (see docs/rag/CL_HERBIZ_DB_PROTECTION_DESIGN.md):
  L1 code guards (dbsafety)          refuse protected files by name / path / hard link       in place (branch)
  L2 file mode 0444 (chmod)          writes fail with "attempt to write a readonly database"  reversible: chmod 644
  L3 macOS user-immutable flag       no write, rename, delete or replace, even by the owner   reversible: chflags nouchg
  L4 SQLite triggers (D16)           block REPLACE / UPDATE / DELETE of evidence rows          reversible: DROP the C_ triggers
  L5 read-only opens                 connect_ro (?mode=ro), and immutable=1 for frozen files    code
`status()` only reads (os.stat + a read-only connection). `apply_triggers()` refuses any protected database."""
from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

from ..dbsafety import AuthoritativeDatabaseError, is_authoritative

# Every trigger created here is named C_PROTECT_* so it can be listed and removed exactly (reversibility).
HARDENING_SQL = """
CREATE TRIGGER IF NOT EXISTS C_PROTECT_audit_no_replace BEFORE INSERT ON audit_events
  WHEN EXISTS (SELECT 1 FROM audit_events WHERE event_id = NEW.event_id)
  BEGIN SELECT RAISE(ABORT, 'audit_events is append-only (replace refused)'); END;
CREATE TRIGGER IF NOT EXISTS C_PROTECT_versions_no_delete BEFORE DELETE ON source_versions
  BEGIN SELECT RAISE(ABORT, 'source_versions rows are evidence and cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS C_PROTECT_versions_no_replace BEFORE INSERT ON source_versions
  WHEN EXISTS (SELECT 1 FROM source_versions WHERE version_id = NEW.version_id)
  BEGIN SELECT RAISE(ABORT, 'source_versions rows cannot be replaced'); END;
CREATE TRIGGER IF NOT EXISTS C_PROTECT_passages_text_frozen BEFORE UPDATE OF text, locator, doc_id, version_id, seq ON passages
  BEGIN SELECT RAISE(ABORT, 'passage text and identity are frozen'); END;
CREATE TRIGGER IF NOT EXISTS C_PROTECT_passages_no_delete BEFORE DELETE ON passages
  BEGIN SELECT RAISE(ABORT, 'passages cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS C_PROTECT_passages_no_replace BEFORE INSERT ON passages
  WHEN EXISTS (SELECT 1 FROM passages WHERE passage_id = NEW.passage_id)
  BEGIN SELECT RAISE(ABORT, 'passages cannot be replaced'); END;
CREATE TRIGGER IF NOT EXISTS C_PROTECT_documents_hash_frozen BEFORE UPDATE OF sha256, raw_path, url, bytes ON documents
  BEGIN SELECT RAISE(ABORT, 'document provenance (sha256, raw_path, url, bytes) is frozen'); END;
CREATE TRIGGER IF NOT EXISTS C_PROTECT_documents_no_delete BEFORE DELETE ON documents
  BEGIN SELECT RAISE(ABORT, 'documents cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS C_PROTECT_documents_no_replace BEFORE INSERT ON documents
  WHEN EXISTS (SELECT 1 FROM documents WHERE doc_id = NEW.doc_id) OR EXISTS (SELECT 1 FROM documents WHERE source_id = NEW.source_id AND sha256 = NEW.sha256)
  BEGIN SELECT RAISE(ABORT, 'documents cannot be replaced'); END;
CREATE TRIGGER IF NOT EXISTS C_PROTECT_documents_identity_frozen BEFORE UPDATE OF doc_id, source_id, origin_label, mime, retrieved_at ON documents
  BEGIN SELECT RAISE(ABORT, 'document identity and provenance are frozen'); END;
CREATE TRIGGER IF NOT EXISTS C_PROTECT_versions_identity_frozen BEFORE UPDATE OF version_id, source_id, seq, content_hash, normalized_hash, document_title, source_url, issuing_authority, retrieved_at, origin_label ON source_versions
  BEGIN SELECT RAISE(ABORT, 'source version identity and provenance are frozen (status changes stay allowed)'); END;
CREATE TRIGGER IF NOT EXISTS C_PROTECT_passages_id_frozen BEFORE UPDATE OF passage_id, label, page_start, page_end ON passages
  BEGIN SELECT RAISE(ABORT, 'passage identity is frozen'); END;
CREATE TRIGGER IF NOT EXISTS C_PROTECT_audit_identity_frozen BEFORE UPDATE OF event_id ON audit_events
  BEGIN SELECT RAISE(ABORT, 'audit identity is frozen'); END;
"""
# Every trigger name above, exactly; removal drops these names and nothing else (QA2: LIKE matched 'c_protectXmine').
import re as _re
TRIGGER_NAMES = _re.findall(r"CREATE TRIGGER IF NOT EXISTS (C_PROTECT_\w+)", HARDENING_SQL)
# Known limits (documented in the design): DROP TRIGGER, PRAGMA writable_schema, and an FTS5 index (virtual tables take
# no triggers) cannot be guarded from inside SQLite; L2/L3 file protection covers them, and validity checks FTS == passages.
REMOVE_SQL_TEMPLATE = "DROP TRIGGER IF EXISTS {name};"


def status(path) -> dict:
    """Read-only inspection of a database file's protection. Never opens it for writing."""
    p = Path(path)
    st = os.stat(p)
    flags = getattr(st, "st_flags", 0)
    out = {"path": str(p), "exists": True, "mode": oct(stat.S_IMODE(st.st_mode)),
           "owner_writable": bool(st.st_mode & stat.S_IWUSR), "user_immutable": bool(flags & getattr(stat, "UF_IMMUTABLE", 0)),
           "hard_links": st.st_nlink, "protected_by_code_guard": is_authoritative(p),
           "side_files": [s for s in ("-journal", "-wal", "-shm") if Path(str(p) + s).exists()]}
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        out["journal_mode"] = con.execute("PRAGMA journal_mode").fetchone()[0]
        trig = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name")]
    finally:
        con.close()
    out["triggers"] = trig
    out["hardening_triggers"] = [t for t in trig if t.startswith("C_PROTECT_")]
    return out


def _existing_db(path) -> Path:
    p = Path(path)
    if not p.is_file():                      # a mistyped path must not create a stray empty database (QA2)
        raise FileNotFoundError(p)
    return p


def apply_triggers(path) -> list[str]:
    """Add the C_PROTECT_* triggers to a COPY. Refuses protected databases (authoritative file, ledger)."""
    if is_authoritative(path):
        raise AuthoritativeDatabaseError("hardening is applied to copies only; the authoritative file needs decision D16 first")
    con = sqlite3.connect(_existing_db(path))
    try:
        con.executescript(HARDENING_SQL)
        present = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        return [n for n in TRIGGER_NAMES if n in present]
    finally:
        con.close()


def remove_triggers(path) -> list[str]:
    """Exact rollback of apply_triggers (drops only C_PROTECT_* triggers). Refuses protected databases."""
    if is_authoritative(path):
        raise AuthoritativeDatabaseError("refused on a protected database")
    con = sqlite3.connect(_existing_db(path))
    try:
        present = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        names = [n for n in TRIGGER_NAMES if n in present]
        con.executescript("".join(REMOVE_SQL_TEMPLATE.format(name=n) for n in names))
        return names
    finally:
        con.close()
