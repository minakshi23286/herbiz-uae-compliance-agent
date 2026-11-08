"""Validation of the versioned source register (knowledge_base/CL_source_register.json). Read-only.

Errors break a rule the register exists to enforce (provenance, no silent activation, no invented dates).
Warnings are gaps a person should look at; they do not fail validation."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from ..kb import OFFICIAL_HOSTS
from .inventory import DATA, LOCK, ROOT, connect_ro, sha256_file

REGISTER = ROOT / "knowledge_base" / "CL_source_register.json"
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
VERSION_KB_STATUS = {"candidate", "approved", "rejected", "superseded"}
CANDIDATE_KB_STATUS = {"not_ingested"}
CANDIDATE_VERIFICATION = {"pending_verification", "unresolved"}
EVIDENCE_LEVELS = ("observed_listing_only", "observed_in_file", "observed", "snippet_only", "unresolved", "supplied")


def _dates(obj, path, errors):
    """Every *_date / effective / issued value is ISO or null, and a non-null one needs evidence next to it."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}"
            if (k.endswith("_date") or k in ("effective", "issued", "effective_date_as_stated")) and v is not None:
                if not (isinstance(v, str) and ISO.match(v)):
                    errors.append(f"{here}: date must be YYYY-MM-DD or null, got {v!r}")
            _dates(v, here, errors)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _dates(v, f"{path}[{i}]", errors)


def _host_ok(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS)


def validate(register_path: Path = REGISTER, lock_path: Path = LOCK, data_dir: Path | None = DATA, db=None) -> dict:
    reg = json.loads(Path(register_path).read_text(encoding="utf-8"))
    lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []

    if not SEMVER.match(str(reg.get("register_version", ""))):
        errors.append("register_version must be MAJOR.MINOR.PATCH")
    if not any(c.get("version") == reg.get("register_version") for c in reg.get("changes", [])):
        errors.append("changes[] has no entry for the current register_version")

    ids, vids = set(), set()
    locked = {(d["source_id"], d["sha256"]): d for d in lock["documents"]}
    in_register = set()
    for s in reg.get("sources", []):
        sid = s.get("source_id")
        if sid in ids:
            errors.append(f"duplicate source_id {sid}")
        ids.add(sid)
        for f in ("title", "issuing_authority", "document_type", "translation_status", "language"):
            if not s.get(f):
                warnings.append(f"{sid}: {f} missing")
        approved_versions = []
        for i, v in enumerate(s.get("versions", [])):
            vid = v.get("version_id")
            if vid in vids:
                errors.append(f"duplicate version_id {vid}")
            vids.add(vid)
            if v.get("kb_status") not in VERSION_KB_STATUS:
                errors.append(f"{vid}: kb_status {v.get('kb_status')!r} not allowed")
            if v.get("kb_status") == "approved":
                ap = v.get("approval") or {}
                if not (ap.get("by") and ap.get("approved_date") and ap.get("evidence")):
                    errors.append(f"{vid}: approved without approver, date and evidence")
                approved_versions.append(vid)
            url = v.get("url") or ""
            if not url.startswith("https://"):
                errors.append(f"{vid}: url must be https")
            elif not _host_ok(url):
                warnings.append(f"{vid}: host not in the official allowlist")
            if v.get("sha256"):
                d = locked.get((sid, v["sha256"]))
                if not d:
                    errors.append(f"{vid}: sha256 not in the collection lock")
                else:
                    in_register.add((sid, v["sha256"]))
                    if d["raw_path"] != v.get("raw_path"):
                        errors.append(f"{vid}: raw_path differs from the lock")
                    if d["url"] != url:
                        errors.append(f"{vid}: url differs from the lock")
                    if data_dir is not None:
                        p = Path(data_dir) / d["raw_path"]
                        if not p.exists():
                            warnings.append(f"{vid}: raw file not present in {data_dir} (cannot check hash here)")
                        elif sha256_file(p) != v["sha256"]:
                            errors.append(f"{vid}: raw file hash MISMATCH")
            else:
                warnings.append(f"{vid}: no sha256 (not captured)")
            for a in v.get("amendments_as_stated", []):
                if a.get("effective") and not v.get("amendments_evidence"):
                    errors.append(f"{vid}: amendment dates without amendments_evidence")
            if v.get("verification_status") not in ("unverified", "verified"):
                errors.append(f"{vid}: verification_status must be unverified or verified")
            if v.get("verification_status") == "verified" and not (v.get("verification") or {}).get("by"):
                errors.append(f"{vid}: verified without a named verifier")
        # C3: the version used as "newest" should also be the one with the latest stated effective date
        seq = [v for v in s.get("versions", []) if v.get("kb_status") in ("candidate", "approved")]
        eff = [v.get("latest_effective_as_stated") for v in seq]
        if len(seq) > 1:
            if None in eff:
                warnings.append(f"{sid}: some versions have no stated effective date; newest-by-sequence cannot be checked")
            elif eff != sorted(eff):
                warnings.append(f"{sid}: version sequence order differs from stated effective-date order {eff}")
        if len(approved_versions) > 1:
            warnings.append(f"{sid}: more than one approved version; mark older ones superseded")

    for d in lock["documents"]:
        if (d["source_id"], d["sha256"]) not in in_register:
            errors.append(f"lock document {d['raw_path']} ({d['source_id']}) is not in the register")

    cids = set()
    for c in reg.get("candidates", []):
        cid = c.get("candidate_id")
        if cid in cids or cid in ids:
            errors.append(f"duplicate candidate_id {cid}")
        cids.add(cid)
        if c.get("activated") is not False:
            errors.append(f"{cid}: candidates must have activated: false")
        if c.get("kb_status") not in CANDIDATE_KB_STATUS:
            errors.append(f"{cid}: kb_status must be not_ingested")
        if c.get("verification_status") not in CANDIDATE_VERIFICATION:
            errors.append(f"{cid}: verification_status must be pending_verification or unresolved")
        ev = c.get("evidence") or ""
        if not ev.startswith(EVIDENCE_LEVELS):
            errors.append(f"{cid}: evidence must start with one of {EVIDENCE_LEVELS}")
        if c.get("url"):
            if not c["url"].startswith("https://"):
                warnings.append(f"{cid}: url is not https")
            elif not _host_ok(c["url"]):
                warnings.append(f"{cid}: host not in the official allowlist ({urlparse(c['url']).hostname})")
        elif not ev.startswith("unresolved") and not c.get("seen_in"):
            errors.append(f"{cid}: no url: evidence must be 'unresolved' or the candidate must say where it was seen (seen_in)")
        if ev.startswith("snippet_only") and c.get("confidence") == "high":
            errors.append(f"{cid}: snippet-only evidence cannot be high confidence")

    _dates(reg, "register", errors)

    if db is not None:
        con = connect_ro(db)
        try:
            counts = dict(con.execute("SELECT version_id, COUNT(*) FROM passages GROUP BY version_id").fetchall())
            db_status = dict(con.execute("SELECT version_id, status FROM source_versions").fetchall())
            audited = {r[0] for r in con.execute("SELECT entity_id FROM audit_events WHERE event = 'source_approved'")}
        finally:
            con.close()
        for s in reg.get("sources", []):            # the register may not claim more than the database records (QA2 item 2)
            for v in s.get("versions", []):
                st, ds = v.get("kb_status"), db_status.get(v["version_id"])
                if ds is None:
                    errors.append(f"{v['version_id']}: not in the database")
                elif st == "approved" and (ds != "approved" or v["version_id"] not in audited):
                    errors.append(f"{v['version_id']}: register says approved but the database says {ds}"
                                  + ("" if v["version_id"] in audited else " and no source_approved audit event exists"))
                elif st == "superseded" and ds != "superseded":
                    errors.append(f"{v['version_id']}: register says superseded but the database says {ds}")
                elif ds in ("approved", "superseded", "rejected") and st != ds:
                    warnings.append(f"{v['version_id']}: database status {ds} not yet recorded in the register ({st})")
        for s in reg.get("sources", []):
            for v in s.get("versions", []):
                want = (v.get("article_coverage") or {}).get("passages")
                if want is not None and counts.get(v["version_id"]) != want:
                    errors.append(f"{v['version_id']}: register says {want} passages, database has {counts.get(v['version_id'])}")

    return {"register": str(register_path), "register_version": reg.get("register_version"),
            "sources": len(ids), "versions": len(vids), "candidates": len(cids),
            "errors": errors, "warnings": warnings, "valid": not errors}
