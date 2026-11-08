"""Audit-record sanitizer (Task 2 A-1, doc 16 r2 §4.1 safeguard 1). Independent of the code that builds records.

`check(record)` returns finding codes; an empty list means the record may be written. Nothing is redacted silently: a
record with any finding is REJECTED, the answer is withheld and the owner sees AUDIT_WRITE_FAILED (safeguard 3).

Checks: (1) no field named `text` or `passage_text` anywhere; (2) `request.query_text` only when the CR-29 gate allowed
the question (T2-D2); (3) no string matching the CR-29 personal-data detectors (Emirates ID, IBAN, UAE phone, e-mail,
passport with keyword); (4) no local file paths; (5) no long strings (official passages are never logged); (6) the record
validates against the frozen audit_record/1.0 schema. The offline scanner (`audit_log verify --scan`) re-checks stored logs
with its own, separate pattern list.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .rag_c import policy_gate as PG

VERSION = "a1-sanitizer-1.0"
MAX_STRING = 400                       # longer strings are refused: an audit record never carries passages or documents
MAX_QUERY = 500                        # the owner's own question (gate-allowed, capped at 500 by the app) may be up to 500
_FORBIDDEN_KEYS = {"text", "passage_text", "full_text", "raw_text"}
# "/" "Users/" is split so the submission export's local-path scrub (which rewrites that literal) leaves the detector intact
_PATH = re.compile(r"(/" r"Users/|/home/[a-z]|/" r"private/(tmp|var)/|[A-Za-z]:\\\\Users\\\\)")
_PII_DETECTORS = ("emirates_id", "iban_ae", "uae_phone", "email", "passport")
_SCHEMA = None
# Machine values are exempt from the personal-data patterns ONLY in these fields and ONLY in their strict formats: a random
# hex digest can contain digit runs that look like a phone number. Free text never gets this exemption.
_MACHINE = re.compile(r"^(?:[0-9a-f]{64}|[0-9a-f]{32}|[0-9a-f]{7,40}|[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$")
_MACHINE_KEYS = {"record_id", "record_sha256", "prev_record_sha256", "shown_text_sha256", "query_sha256", "config_sha256",
                 "db_md5", "kb_sha256", "integration_commit", "b_commit", "c_commit", "commit"}


def machine_value(key, parent_key, s: str) -> bool:
    return (key in _MACHINE_KEYS or parent_key == "files_sha256") and bool(_MACHINE.match(s))


def _schema() -> dict:
    global _SCHEMA
    if _SCHEMA is None:
        root = Path(__file__).resolve().parents[1]
        _SCHEMA = json.loads((root / "contracts" / "audit_record_1.0.schema.json").read_text(encoding="utf-8"))
    return _SCHEMA


def _validate(record: dict) -> list[str]:
    root = str(Path(__file__).resolve().parents[1] / "contracts")
    if root not in sys.path:
        sys.path.insert(0, root)
    import validate as V              # contracts/validate.py (stdlib)
    return V.errors(_schema(), record)


def _walk(x, path="$", key=None, parent=None):
    """Yields (path, key_event, string, owning_key, parent_key): key events have string None; strings have key_event None."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield path, k, None, None, None
            yield from _walk(v, f"{path}.{k}", k, key)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _walk(v, f"{path}[{i}]", key, parent)
    elif isinstance(x, str):
        yield path, None, x, key, parent


def check(record: dict) -> list[str]:
    findings: list[str] = []
    try:
        req = record.get("request") or {}
        gate = req.get("gate") or {}
        if req.get("query_text") is not None and gate.get("action") != "allow":
            findings.append("QUERY_TEXT_NOT_ALLOWED")
        for path, key, s, owner, parent in _walk(record):
            if key is not None:
                if key in _FORBIDDEN_KEYS:
                    findings.append(f"FIELD_{key.upper()}")
                continue
            if machine_value(owner, parent, s):
                continue
            if len(s) > (MAX_QUERY if path == "$.request.query_text" else MAX_STRING):
                findings.append("LONG_STRING")
            if _PATH.search(s):
                findings.append("LOCAL_PATH")
            t = PG.normalise(s)
            for d in _PII_DETECTORS:
                if PG.DETECTORS[d](t):
                    findings.append(f"PII_{d.upper()}")
        if _validate(record):
            findings.append("SCHEMA_INVALID")
    except Exception as ex:                       # the sanitizer itself failing is a finding (fail closed)
        findings.append(f"SANITIZER_ERROR_{type(ex).__name__}")
    return sorted(set(findings))
