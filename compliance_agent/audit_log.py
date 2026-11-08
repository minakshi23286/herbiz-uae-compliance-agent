"""Per-response audit log (Task 2 A-1, doc 16 r2 §4 and §4.1). Workspace data only; never the authoritative database.

Storage: one JSON Lines file per day (audit-YYYY-MM-DD.jsonl, Asia/Dubai date of the record) in the app's audit folder,
next to the workspace database (git-ignored). Each record is a hash chain link: integrity = {seq, prev_record_sha256,
record_sha256}; the first record of a file has prev = 64 zeros. record_sha256 = sha256 of the canonical JSON of the record
without integrity.record_sha256. A pointer row in the workspace `audit_events` table stores the record id and its sha256.

Write path (safeguards 1, 3, 5): process-wide writer lock + OS file lock (fcntl.flock) around read-tail / sanitize / append /
pointer; the pointer row is inserted in a transaction that is committed only after the line is written and fsynced. Any
failure raises AuditWriteError and the caller withholds the answer (AUDIT_WRITE_FAILED).

    python3 -m compliance_agent.audit_log verify <file.jsonl> [--db <workspace.sqlite3>]   # OK, or the first broken seq
    python3 -m compliance_agent.audit_log verify --scan <file-or-folder>                    # offline scanner, own patterns
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
from pathlib import Path

from . import audit_sanitizer as S

GENESIS = "0" * 64
FAIL_TEXT = "HerBiz could not record this answer, so it is not shown. Please try again."


class AuditWriteError(RuntimeError):
    pass


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def record_hash(rec: dict) -> str:
    r = json.loads(json.dumps(rec))
    r["integrity"].pop("record_sha256", None)
    return hashlib.sha256(canonical(r)).hexdigest()


class AuditLog:
    def __init__(self, folder: Path, store=None):
        self.folder = Path(folder)
        self.store = store                    # workspace Store (pointer rows); None in offline tools
        self._lock = threading.Lock()

    def file_for(self, at: str) -> Path:
        return self.folder / f"audit-{at[:10]}.jsonl"

    def write(self, rec: dict) -> dict:
        """Sanitize, chain and append one record; return its integrity block. Raises AuditWriteError (fail closed)."""
        with self._lock:
            try:
                self.folder.mkdir(parents=True, exist_ok=True)
                path = self.file_for(rec["at"])
                with open(path, "a+b") as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)          # serialises other processes on the same folder
                    try:
                        seq, prev = self._tail(f)
                        rec["integrity"] = {"seq": seq + 1, "prev_record_sha256": prev, "record_sha256": GENESIS}
                        findings = S.check(rec)
                        if findings:
                            raise AuditWriteError(f"sanitizer rejected the record: {findings}")
                        rec["integrity"]["record_sha256"] = record_hash(rec)
                        line = canonical(rec) + b"\n"
                        if self.store is not None:
                            db = self.store.db
                            with db:              # pointer row commits only if the line was written and fsynced
                                db.execute("INSERT INTO audit_events (at, actor, event, entity, entity_id, payload_json) VALUES (?,?,?,?,?,?)",
                                           (rec["at"], "audit_log", "audit_record", "audit_file", rec["record_id"],
                                            json.dumps({"file": path.name, "seq": rec["integrity"]["seq"],
                                                        "record_sha256": rec["integrity"]["record_sha256"]}, sort_keys=True)))
                                f.seek(0, os.SEEK_END)
                                f.write(line); f.flush(); os.fsync(f.fileno())
                        else:
                            f.seek(0, os.SEEK_END)
                            f.write(line); f.flush(); os.fsync(f.fileno())
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return dict(rec["integrity"])
            except AuditWriteError:
                raise
            except Exception as ex:
                raise AuditWriteError(f"{type(ex).__name__}: {ex}") from None

    @staticmethod
    def _tail(f) -> tuple[int, str]:
        f.seek(0)
        data = f.read()
        if not data:
            return 0, GENESIS
        if not data.endswith(b"\n"):
            raise AuditWriteError("audit file does not end with a complete record (truncated); refusing to append")
        last = json.loads(data.rstrip(b"\n").rsplit(b"\n", 1)[-1])
        return last["integrity"]["seq"], last["integrity"]["record_sha256"]

    def files(self) -> list[Path]:
        return sorted(self.folder.glob("audit-*.jsonl")) if self.folder.exists() else []

    def records(self, path: Path, limit: int = 50) -> list[dict]:
        lines = Path(path).read_bytes().splitlines()
        return [json.loads(x) for x in lines[-limit:]]


# ------------------------------------------------------------------------------------------------ verification
def verify(path, db: str | None = None) -> tuple[bool, str]:
    """Check one daily file: complete lines, schema, contiguous seq, prev links, record hashes, optional pointer rows."""
    path = Path(path)
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        return False, "truncated: the last record is incomplete"
    prev, recs = GENESIS, []
    for i, raw in enumerate(data.splitlines(), 1):
        try:
            rec = json.loads(raw)
        except ValueError:
            return False, f"broken at seq {i}: not a JSON record"
        integ = rec.get("integrity") or {}
        if integ.get("seq") != i:
            return False, f"broken at seq {i}: found seq {integ.get('seq')} (record missing or out of order)"
        if integ.get("prev_record_sha256") != prev:
            return False, f"broken at seq {i}: prev_record_sha256 does not match the previous record"
        if record_hash(rec) != integ.get("record_sha256"):
            return False, f"broken at seq {i}: record content changed (hash mismatch)"
        if S._validate(rec):
            return False, f"broken at seq {i}: record does not validate against audit_record/1.0"
        prev = integ["record_sha256"]
        recs.append(rec)
    if db:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            rows = {r[0]: json.loads(r[1]) for r in con.execute(
                "SELECT entity_id, payload_json FROM audit_events WHERE event = 'audit_record' AND entity = 'audit_file'")}
        finally:
            con.close()
        for rec in recs:
            p = rows.get(rec["record_id"])
            if not p or p.get("record_sha256") != rec["integrity"]["record_sha256"] or p.get("file") != path.name:
                return False, f"pointer mismatch at seq {rec['integrity']['seq']}"
    return True, f"OK: {len(recs)} records, chain intact" + (", pointers match" if db else "")


# Offline scanner: its OWN patterns (independent of the sanitizer), applied to the raw file text.
SCAN_PATTERNS = {
    "SCAN_EMAIL": re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    "SCAN_EMIRATES_ID": re.compile(r"784[\s\-]?\d{4}[\s\-]?\d{7}[\s\-]?\d"),
    "SCAN_UAE_PHONE": re.compile(r"(?:\+971|00971|\b971)[\s\-]?\d{1,2}[\s\-]?\d{3}[\s\-]?\d{4}|\b05\d[\s\-]?\d{3}[\s\-]?\d{4}\b"),
    "SCAN_IBAN": re.compile(r"\bAE\d{2}\s?(?:\d{4}\s?){4}\d{3}\b", re.I),
    "SCAN_LOCAL_PATH": re.compile(r"/" r"Users/|/home/[a-z]|/" r"private/(?:tmp|var)/"),   # split: see audit_sanitizer._PATH
    "SCAN_TEXT_FIELD": re.compile(r"\"(?:text|passage_text|full_text)\"\s*:"),
    "SCAN_LONG_STRING": re.compile(r"\"[^\"]{501,}\""),          # owner questions are capped at 500 characters
}


def scan(target) -> list[str]:
    """Offline re-check of stored logs with SCAN_PATTERNS (independent of the sanitizer's checks). Unparseable lines are
    scanned as raw text. Machine fields (hashes, ids, commits in their strict formats) are exempt, as in the sanitizer."""
    target = Path(target)
    files = sorted(target.glob("audit-*.jsonl")) if target.is_dir() else [target]
    out = []
    for f in files:
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            try:
                strings = [(o, p, s) for _, k, s, o, p in S._walk(json.loads(line)) if k is None]
                keys = [k for _, k, s, o, p in S._walk(json.loads(line)) if k is not None]
            except ValueError:
                strings, keys = [(None, None, line)], []
            if any(k in ("text", "passage_text", "full_text") for k in keys):
                out.append(f"{f.name}:{n}:SCAN_TEXT_FIELD")
            for owner, parent, s in strings:
                if S.machine_value(owner, parent, s):
                    continue
                for code, rx in SCAN_PATTERNS.items():
                    if code != "SCAN_TEXT_FIELD" and rx.search(s if code != "SCAN_LONG_STRING" else json.dumps(s)):
                        out.append(f"{f.name}:{n}:{code}")
    return sorted(set(out))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m compliance_agent.audit_log")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("path")
    v.add_argument("--db", default=None)
    v.add_argument("--scan", action="store_true", help="offline scan for personal data, paths and passages instead")
    a = ap.parse_args(argv)
    if a.scan:
        found = scan(a.path)
        print("SCAN OK: no findings" if not found else "SCAN FINDINGS:\n" + "\n".join(found))
        return 1 if found else 0
    ok, msg = verify(a.path, a.db)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
