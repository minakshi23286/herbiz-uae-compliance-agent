"""Task 2 A-4: WS B v8 retrieval and WS C source validity 1.2 for questions with no recorded answer (D-101, D-102).

WS B t2-b-rc1 (89dc2b9, code frozen at baefe25) is integrated as an INTERIM CANDIDATE (D-102), with these limits stated
without qualification wherever it is described: required-article recall 66.7% on v10, 70.4% on v11, 68.5% pooled (70% target not
met pooled); silent-incomplete 0 holds by construction (every answer warned), not completeness detection; 4 of 27 (v10) and 1 of 27 (v11) valid VAT questions classified out of
scope. Nothing here certifies completeness: v8 never returns complete_for_map.

Fail closed: if any runtime file covered by WS B's code-freeze record no longer matches its frozen sha256, or the database
is missing, retrieval is unavailable and the owner sees no passages. Links are shown, never fetched.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEZE_COMMIT = "baefe2582cff920316295a567f622a5f5f306d01"     # WS B B-4 code freeze (docs/CL_evidence/ws_b/t2/CL_t2_code_freeze.json)
FREEZE_CONFIG_SHA256 = "67f5aa9d9cb6f401fbc41bdeee4bb6b1e0cf9971a8dcdd446e1cfd9dc805c2fa"
FROZEN_FILES = {                                             # runtime files only; the eval scripts and v10 holdout are not shipped
    "compliance_agent/llm_lab/retrieve_v8.py": "4da6eef629ada059af459f342d17a2e8ea1a461447e5bd0268a49873a7258aba",
    "compliance_agent/llm_lab/pipeline_v7.py": "c703911038cfa7b69c47c48e40e8ef4a34e8946221da2b26925c62c5e68ebb97",
    "compliance_agent/llm_lab/retrieve.py": "827876d4eda13ad8764b3d410ae2e5e1b72f5ef607562ce8886d5df15636f3ab",
    "compliance_agent/llm_lab/concepts_v5.py": "8eadc88009b870b9e2600f4860cf305df0067025abb826924c64b37798c05a49",
    "compliance_agent/llm_lab/locators.py": "3bc1cee1649f1befd2c1f5ed975b752577bb6983953e700d906ae5bce4882810",
    "compliance_agent/llm_lab/t2_payloads.py": "0e52488758e55d3c497cc3e7630246d7c7a54577492e54ea3ee368f52d7666ce",
    "compliance_agent/llm_lab/data/CL_provision_map_v7.json": "6c926baf0893c3a0a8333407969747631b1f71445501f962195021497c7fca1a",
    "compliance_agent/llm_lab/data/CL_expansion_v6.json": "bf36ce5deb81410beba2f7dfb0502e692d7600b4ba334ecc75340c07d9184a36",
    "compliance_agent/llm_lab/data/CL_article_index_v6.json": "d235e7bfd0d7eae04d8c76aa0d1c5250340f2211c1302b53291b085c7cdbb573",
    "compliance_agent/llm_lab/data/CL_source_validity_v6.json": "debcaf7bcb6d5c15e371a9e9298d25a11d5b31880a5f2573cd8d1b5ccae22ea3",
}
SNAPSHOT_DB_MD5 = "26e202b87a062288e56bcda1de9b0217"   # the protected 17 Oct 2026 snapshot the workspace copy is made from
SNAPSHOT_DATE = "2026-10-17"
VALIDITY_FILE = ROOT / "knowledge_base" / "t2" / "CL_source_validity_1.2.json"     # WS C t2-c-rc2 (8f35b20)
MANIFEST_FILE = ROOT / "kb_export" / "CL_HERBIZ_KB_MANIFEST.json"
SHOWN = 5                                              # passages shown to the owner; the audit record keeps every item
INTERIM = ("Interim search method: on two held-out tests it found every required article for 68.5% of questions "
           "(66.7% and 70.4%), below the 70% target overall. Treat every answer as possibly incomplete.")
STATUS_PLAIN = {"current": "Current on 17 Oct 2026 (not checked by a person yet)", "outdated": "Outdated: amended since",
                "superseded": "Replaced by a newer text", "conflict": "Sources disagree", "not_collected": "Status not collected"}


class Unavailable(Exception):
    pass


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def code_freeze() -> dict:
    """The frozen-code record for retrieval_result/1.0. Raises Unavailable if any runtime file drifted (fail closed)."""
    drift = [f for f, h in FROZEN_FILES.items() if not (ROOT / f).exists() or _sha(ROOT / f) != h]
    if drift:
        raise Unavailable("retrieval code differs from the WS B code freeze: " + ", ".join(drift))
    return {"commit": FREEZE_COMMIT, "files_sha256": dict(FROZEN_FILES), "config_sha256": FREEZE_CONFIG_SHA256}


def kb_snapshot() -> dict:
    version = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))["_meta"]["version"] if MANIFEST_FILE.exists() else "unknown"
    return {"snapshot_date": SNAPSHOT_DATE, "db_md5": SNAPSHOT_DB_MD5, "manifest_version": version}


_VALIDITY: dict | None = None


def validity(source_id: str, article) -> dict | None:
    """WS C source_validity/1.2 payload for one provision (article-level first, then the whole source). None if absent."""
    global _VALIDITY
    if _VALIDITY is None:
        _VALIDITY = {}
        if VALIDITY_FILE.exists():
            for p in json.loads(VALIDITY_FILE.read_text(encoding="utf-8"))["payloads"]:
                _VALIDITY[p["key"]] = p
    return _VALIDITY.get(f"{source_id}|{article}") or _VALIDITY.get(f"{source_id}|*")


SEVERITY = ("superseded", "outdated", "conflict")       # rc3 item 1: statuses that withhold a recorded answer, most severe first


def article_status(source_id: str, article) -> tuple[dict | None, str]:
    """rc3 item 1 (founder/CTO 19 Oct; WS A + WS C rule M4) for RECORDED answers only. Returns (payload, kind):
    "article"  - an article-level record exists (its status counts);
    "amended"  - no article record, but a whole-source amendment lists this article: treated as outdated;
    "source"   - only a whole-source record, and this article is NOT listed as amended: a note, never a withhold;
    "none"     - nothing recorded.  A whole-source status is never inherited by an article its amendments do not list."""
    validity("", "")                                      # loads the export once
    art = None if article in (None, "", "*") else str(article)
    if art is not None and f"{source_id}|{art}" in _VALIDITY:
        return _VALIDITY[f"{source_id}|{art}"], "article"
    whole = _VALIDITY.get(f"{source_id}|*")
    if whole is None:
        return None, "none"
    listed = {a for am in whole.get("amendments") or [] for a in am.get("articles_affected") or []}
    return whole, ("amended" if art is not None and art in listed else "source")


def effective_status(payload: dict | None, kind: str) -> str | None:
    """The status a recorded answer acts on: the article's own, "outdated" when listed as amended, else None (no withhold)."""
    if kind == "article":
        return payload["status"]
    return "outdated" if kind == "amended" else None


def amended_articles(source_id: str) -> list[str]:
    whole = (_VALIDITY or {}).get(f"{source_id}|*") or {}
    return sorted({a for am in whole.get("amendments") or [] for a in am.get("articles_affected") or []},
                  key=lambda x: (int("".join(c for c in x if c.isdigit()) or 0), x))


def owner_validity(v: dict | None) -> dict:
    """What the owner sees about a source's validity. The current official link is shown, never fetched or followed."""
    if not v:
        return {"status": "unknown", "plain": "Validity not recorded for this source", "current_official_url": None, "note": None}
    cs = (v.get("current_official_url_status") or {})
    note = None
    if v.get("current_official_url"):
        note = ("The current official page has not been checked by a person yet." if cs.get("content_check") != "checked"
                else "Current official page.")
    return {"status": v["status"], "plain": STATUS_PLAIN.get(v["status"], v["status"]),
            "current_official_url": v.get("current_official_url"), "note": note,
            "conflicts": len(v.get("conflicts") or []), "review_status": v.get("review_status")}


def retrieve(db: Path, question: str) -> tuple[dict, list[dict]]:
    """(retrieval_result/1.0 payload WITH passage text, owner passages). Raises Unavailable (fail closed)."""
    if not Path(db).exists():
        raise Unavailable("no knowledge-base database")
    freeze = code_freeze()
    from .llm_lab import t2_payloads as T
    from .llm_lab.retrieve import connect_ro
    con = connect_ro(Path(db))
    try:
        payload = T.retrieval_result(con, question, freeze, kb_snapshot(), "deterministic", include_text=True)
    except Exception as ex:                     # any retrieval error: no passages rather than a partial answer
        raise Unavailable(f"retrieval failed: {type(ex).__name__}") from None
    finally:
        con.close()
    return payload, payload["items"]


def without_text(payload: dict) -> dict:
    """The audit copy: passage text is never logged (audit sanitizer rule 1)."""
    out = dict(payload)
    out["items"] = [{k: v for k, v in i.items() if k != "text"} for i in payload["items"]]
    return out
