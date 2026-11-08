"""Database safety: demo and evaluation commands never write to the authoritative database by accident.

The authoritative database (data/CL_compliance.sqlite3) holds the knowledge base, source evidence and audit history.
Demo and evaluation commands use a dedicated test workspace (data/CL_test_workspace.sqlite3) by default: a copy made
from the authoritative database through a read-only connection. Writing to the authoritative database needs an explicit
override flag. Nothing here deletes or rewrites records.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTHORITATIVE = ROOT / "data" / "CL_compliance.sqlite3"
WORKSPACE = ROOT / "data" / "CL_test_workspace.sqlite3"


class AuthoritativeDatabaseError(RuntimeError):
    pass


# Protected by NAME as well as by path (QA D1/D5, 17 Oct 2026): the path above only names this checkout's file, so a
# worktree would not recognise the main checkout's database. Any file with one of these names is refused, wherever it is,
# and so is any hard link to such a file in this checkout or a sibling checkout (e.g. ../CL_compliance_agent_app).
PROTECTED_NAMES = {"cl_compliance.sqlite3", "cl_llm_experiment.sqlite3"}


def _protected_files() -> list[Path]:
    found = []
    for base in [ROOT, *[d for d in ROOT.parent.iterdir() if d.is_dir()]] if ROOT.parent.exists() else [ROOT]:
        for name in ("CL_compliance.sqlite3", "CL_llm_experiment.sqlite3"):
            f = base / "data" / name
            if f.exists():
                found.append(f)
    extra = os.environ.get("HERBIZ_PROTECTED_DB_PATHS", "")
    return found + [Path(x) for x in extra.split(os.pathsep) if x]


def is_authoritative(path) -> bool:
    """True for a protected database: the authoritative file or the experiment ledger, in any checkout (matched by file
    name, case-insensitive), a symlink to one, or a hard link to one. Fails closed: an error counts as protected."""
    try:
        p = Path(path)
        r = p.resolve()
        if r == AUTHORITATIVE.resolve() or r.name.lower() in PROTECTED_NAMES or p.name.lower() in PROTECTED_NAMES:
            return True
        if p.exists():
            return any(os.path.samefile(p, f) for f in _protected_files())
        return False
    except OSError:
        return True


def refuse_authoritative(path, allow: bool = False, what: str = "this command") -> None:
    if is_authoritative(path) and not allow:
        raise AuthoritativeDatabaseError(
            f"Refused: {what} would write to a protected database ({Path(path).name}: the authoritative knowledge base or the experiment ledger). "
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
