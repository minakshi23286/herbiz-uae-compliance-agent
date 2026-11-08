"""Back up and restore the local database. Uses SQLite's online backup, so it is safe while the app is running.

    python3 -m compliance_agent.backup backup  [--db data/CL_compliance.sqlite3]          -> data/backups/CL_compliance_<time>.sqlite3
    python3 -m compliance_agent.backup verify  data/backups/<file>.sqlite3
    python3 -m compliance_agent.backup restore data/backups/<file>.sqlite3 [--db data/CL_compliance.sqlite3] --yes

Restore keeps the current database as a dated copy first; nothing is deleted. Stop the app before restoring.
Raw official-source files (data/raw/) are not inside the database: copy that folder too, or re-collect.
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "CL_compliance.sqlite3"
BACKUPS = ROOT / "data" / "backups"


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def verify(path: Path) -> dict:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("business_profiles", "source_versions", "passages", "cases", "reviews", "audit_events")}
        return {"integrity": ok, "counts": counts}
    finally:
        con.close()


def backup(db: Path, dest_dir: Path = BACKUPS) -> Path:
    if not db.exists():
        raise SystemExit(f"no database at {db}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{db.stem}_{stamp()}.sqlite3"
    src, out = sqlite3.connect(db), sqlite3.connect(dest)
    with out:
        src.backup(out)
    src.close(); out.close()
    v = verify(dest)
    if v["integrity"] != "ok":
        raise SystemExit(f"backup written but integrity check failed: {v}")
    return dest


def restore(backup_file: Path, db: Path, yes: bool) -> Path | None:
    v = verify(backup_file)
    if v["integrity"] != "ok":
        raise SystemExit(f"refused: backup fails integrity check: {v}")
    if not yes:
        raise SystemExit("refused: add --yes to confirm (the current database is kept as a dated copy)")
    kept = None
    if db.exists():
        kept = db.with_name(f"{db.stem}_before_restore_{stamp()}.sqlite3")
        shutil.move(str(db), kept)
    shutil.copy2(backup_file, db)
    return kept


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["backup", "verify", "restore"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "backup":
        d = backup(Path(a.db)); print(f"backup: {d}\n{verify(d)}")
    elif a.cmd == "verify":
        print(verify(Path(a.file)))
    else:
        kept = restore(Path(a.file), Path(a.db), a.yes)
        print(f"restored {a.file} -> {a.db}; previous database kept at {kept}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
