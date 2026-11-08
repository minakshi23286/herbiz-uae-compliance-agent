"""Database safety: demo and evaluation commands never write to the authoritative database by accident.

The authoritative database (data/CL_compliance.sqlite3) holds the knowledge base, source evidence and audit history.
Demo and evaluation commands use a dedicated test workspace (data/CL_test_workspace.sqlite3) by default: a copy made
from the authoritative database through a read-only connection. Writing to the authoritative database needs an explicit
override flag. Nothing here deletes or rewrites records.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTHORITATIVE = ROOT / "data" / "CL_compliance.sqlite3"
WORKSPACE = ROOT / "data" / "CL_test_workspace.sqlite3"


class AuthoritativeDatabaseError(RuntimeError):
    pass


def is_authoritative(path) -> bool:
    try:
        return Path(path).resolve() == AUTHORITATIVE.resolve()
    except OSError:
        return False


def refuse_authoritative(path, allow: bool = False, what: str = "this command") -> None:
    if is_authoritative(path) and not allow:
        raise AuthoritativeDatabaseError(
            f"Refused: {what} would write to the authoritative database ({AUTHORITATIVE.name}). "
            f"It uses the test workspace by default; pass an explicit override only if a reviewer has approved it.")


def copy_readonly(src: Path, dest: Path) -> Path:
    """Copy a SQLite database by opening the source read-only (the source file is never written)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    d = sqlite3.connect(dest)
    try:
        s.backup(d)
    finally:
        d.close(); s.close()
    return dest


def ensure_workspace(fresh: bool = False, src: Path | None = None, dest: Path | None = None) -> Path:
    """Return the test workspace, creating it from the authoritative database if missing (or when fresh=True).
    An existing workspace is replaced only when fresh=True; it holds demo state, never authoritative evidence."""
    src, dest = Path(src or AUTHORITATIVE), Path(dest or WORKSPACE)
    if fresh or not dest.exists():
        if is_authoritative(dest):
            raise AuthoritativeDatabaseError("the workspace cannot be the authoritative database")
        if dest.exists():
            dest.unlink()   # only ever the test workspace, never the authoritative file (checked above)
        if src.exists():
            copy_readonly(src, dest)
    return dest
