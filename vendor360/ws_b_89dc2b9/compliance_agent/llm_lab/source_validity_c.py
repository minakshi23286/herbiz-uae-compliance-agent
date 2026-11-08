"""Workstream C source-validity interface, used by Workstream B WITHOUT merging C's branch (contract v1.1,
CL_HERBIZ_RAG_INTEGRATION_HANDOFF.md + CL_HERBIZ_SOURCE_VALIDITY_CONTRACT_v1.1.md).

C's package is copied read-only into a throwaway directory and imported under a separate name, so B never edits or
imports from C's worktree in place. Every failure FAILS CLOSED: no interface, no export, wrong build (database md5), wrong
schema, unreadable data or an exception in C's code all give `source_approved = False` and `certified = False`.

The LLM classifier never reaches this module: certification depends only on retrieval completeness (B) and C's data.
"""
from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
from pathlib import Path

DEFAULT_C_ROOT = Path(__file__).resolve().parents[3] / "CL_compliance_agent_app_ws_c"
ALIAS = "wsc_compliance_agent"


class ValiditySource:
    """`label(completeness, provisions)` -> C's answer_label dict, or a fail-closed equivalent."""

    def __init__(self, interface=None, validity: dict | None = None, error: str | None = None, origin: str = "", db_md5: str | None = None):
        self.interface, self.validity, self.error, self.origin, self.db_md5 = interface, validity, error, origin, db_md5

    def bound_to(self, con) -> bool:
        """True only if `con` is the very database file this validity export was loaded for (same md5)."""
        try:
            path = next(r[2] for r in con.execute("PRAGMA database_list") if r[1] == "main")
            return bool(path) and self.db_md5 is not None and _md5(path) == self.db_md5
        except Exception:
            return False

    @property
    def available(self) -> bool:
        return self.interface is not None and self.validity is not None and self.error is None

    def label(self, completeness: str, provisions: list[tuple]) -> dict:
        if not self.available:
            return fail_closed(completeness, f"validity_unavailable: {self.error or 'no interface'}")
        try:
            out = self.interface.answer_label(self.validity, completeness, provisions)
        except Exception as e:   # anything unexpected in C's code or data fails closed
            return fail_closed(completeness, f"validity_error: {type(e).__name__}: {e}")
        if not isinstance(out, dict) or "certified" not in out:
            return fail_closed(completeness, "validity_error: malformed answer_label result")
        return out

    def provision_issues(self, source_id: str, locator: str, version_id: str | None) -> list[dict]:
        if not self.available:
            return [{"id": "validity_unavailable", "kind": "unavailable", "message": self.error or "no interface"}]
        try:
            return self.interface.provision_status(self.validity, source_id, locator, version_id)["issues"]
        except Exception as e:
            return [{"id": "validity_error", "kind": "unavailable", "message": str(e)}]

    def current_version(self, source_id: str) -> str | None:
        try:
            return self.validity["current_versions"][source_id]["version_id"] if self.available else None
        except Exception:
            return None


def _md5(path) -> str:
    import hashlib
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


MAX_EXPORT_AGE_DAYS = 7


def fail_closed(completeness: str, reason: str) -> dict:
    return {"contract_version": "1.1", "retrieval_completeness": completeness, "source_approval": "not_approved",
            "validity_issue_kinds": [], "certified": False, "blockers": [{"article_id": None, "reason": reason}],
            "user_wording": "Draft information, not legal or tax advice: the status of the official sources could not be checked."}


def load(db: str | Path, c_root: str | Path = DEFAULT_C_ROOT, export: str | Path | None = None,
         today: str | None = None, max_age_days: int = MAX_EXPORT_AGE_DAYS) -> ValiditySource:
    """Copy C's package and export into a disposable directory, import the interface there, load the export for `db`.
    `export` overrides C's committed export (used by negative tests with edited disposable copies)."""
    c_root = Path(c_root)
    src_pkg = c_root / "compliance_agent"
    exp = Path(export) if export else c_root / "knowledge_base" / "CL_source_validity.json"
    if not (src_pkg / "rag_c" / "interface.py").exists():
        return ValiditySource(error=f"Workstream C interface not found at {src_pkg}")
    if not exp.exists():
        return ValiditySource(error=f"validity export not found: {exp}")
    tmp = Path(tempfile.mkdtemp(prefix="ws_b_c_iface_"))   # always a fresh copy of C's current code
    dest = tmp / ALIAS
    try:
        shutil.copytree(src_pkg, dest, ignore=shutil.ignore_patterns("__pycache__"))
        exp_copy = tmp / "CL_source_validity.json"
        shutil.copyfile(exp, exp_copy)
        if str(tmp) not in sys.path:
            sys.path.insert(0, str(tmp))
        for name in [m for m in sys.modules if m == ALIAS or m.startswith(ALIAS + ".")]:
            del sys.modules[name]       # a fresh import per load (tests load several variants)
        iface = importlib.import_module(f"{ALIAS}.rag_c.interface")
        validity = iface.load_validity(path=exp_copy, db=db)   # refuses an export built for another database
    except Exception as e:
        return ValiditySource(error=f"{type(e).__name__}: {e}", origin=str(c_root))
    if getattr(iface, "CONTRACT_VERSION", "") != "1.1":
        return ValiditySource(error=f"unexpected contract version {getattr(iface, 'CONTRACT_VERSION', None)}", origin=str(c_root))
    import datetime as dt
    try:
        gen = dt.date.fromisoformat(validity["_meta"]["generated_for_date"])
        now = dt.date.fromisoformat(today) if today else dt.date.today()
        if (now - gen).days > max_age_days:
            return ValiditySource(error=f"validity export is stale: generated for {gen}, older than {max_age_days} days", origin=str(c_root))
    except Exception as e:
        return ValiditySource(error=f"validity export has no usable date: {e}", origin=str(c_root))
    return ValiditySource(iface, validity, None, origin=str(c_root), db_md5=_md5(db))
