"""Build herbiz.audit_record/1.0 payloads for every owner-facing response channel (Task 2 A-1, doc 16 r2 §4).

The builder only assembles facts the app already computed (the WS B engine report behind the owner view, WS C source
labels, the CR-29 gate decision, recorded-answer metadata). It never copies passage text or the owner's question unless
the gate allowed it (T2-D2). Sanitizing, chaining and writing are done elsewhere (audit_sanitizer, audit_log).

A-4: unrecorded questions carry WS B v8 `retrieval` (no passage text) and WS C validity 1.2 per source; otherwise `retrieval` is null and
`sources[].validity` is null; decisions are built from the pinned engine report (fdbe131) behind the owner view.
"""
from __future__ import annotations

import datetime as dt
import functools
import hashlib
import json
import re
import subprocess
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

from .mvp360 import pins as P

ROOT = Path(__file__).resolve().parents[1]
DUBAI = ZoneInfo("Asia/Dubai")
CONTRACTS = {"herbiz.audit_record": "1.0", "herbiz.decision_explanation": "1.0", "herbiz.retrieval_result": "1.0",
             "herbiz.source_validity": "1.2"}
EVIDENCE = {"observed", "observed_in_file", "observed_listing_only", "snippet_only", "supplied", "unresolved"}
LEVEL = {"low": 0, "medium": 1, "high": 2}


def now_iso() -> str:
    return dt.datetime.now(DUBAI).isoformat(timespec="seconds")


def sha(b) -> str:
    return hashlib.sha256(b if isinstance(b, bytes) else str(b).encode("utf-8")).hexdigest()


def query_sha256(q: str) -> str:
    """I-3 (confirmed by WS B): sha256(utf8(re.sub(r"\\s+", " ", q.lower()).strip())), no NFC."""
    return sha(re.sub(r"\s+", " ", q.lower()).strip())


@functools.lru_cache(maxsize=1)
def build_info() -> dict:
    commit = None
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10)
        commit = r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        commit = None
    if not commit:                                    # history-free export: the source commit is in the export manifest
        try:
            commit = json.loads((ROOT / "CL_EXPORT_FILE_MANIFEST.json").read_text(encoding="utf-8"))["from_repository_commit"][:7]
        except Exception:
            commit = "0000000"
    return {"integration_commit": commit, "b_commit": P.B_COMMIT, "c_commit": P.C_COMMIT, "snapshot_date": P.DEMO_AS_OF,
            "contracts": dict(CONTRACTS)}


@functools.lru_cache(maxsize=1)
def _source_meta() -> dict:
    meta = {}
    for s in json.loads((ROOT / "knowledge_base" / "CL_source_manifest.json").read_text(encoding="utf-8"))["sources"]:
        meta.setdefault(s["source_id"], {"title": s["document_title"], "url": s["url"], "evidence_level": "observed",
                                         "retrieved_on": None, "review_status": "candidate"})
    try:
        for k, v in P.run_c(True)["sources"].items():
            meta[k] = {"title": v["title"], "url": v["url"], "evidence_level": v["evidence_level"],
                       "retrieved_on": (v.get("retrieved_at") or "")[:10] or None, "review_status": v["review_status"]}
    except P.Unavailable:
        pass
    return meta


def source_entry(source_id: str, article) -> dict | None:
    m = _source_meta().get(source_id)
    if not m or not str(m.get("url", "")).startswith("https://"):
        return None
    ev = m["evidence_level"] if m["evidence_level"] in EVIDENCE else "unresolved"
    return {"source_id": source_id, "article": None if article in (None, "") else str(article), "title": m["title"][:300],
            "url": m["url"], "evidence_level": ev, "retrieved_on": m["retrieved_on"], "review_status": m["review_status"],
            "validity": None}


def _confidence(level: str, basis) -> dict:
    return {"level": level, "basis": sorted(set(basis)), "numeric": None}


def decision(o: dict, execution_mode: str | None = None) -> dict:
    """decision_explanation/1.0 from one WS B engine obligation (fdbe131 report). Owner-visible vs reviewer-only steps."""
    blocked = str(o.get("state", "")).startswith("blocked")
    synthetic = o.get("rule_status") == "synthetic_test"
    val = (o.get("sources") or {}).get("validity") or {}
    blockers = [str(b) for b in (val.get("blockers") or [])]
    steps, n = [], 0
    for w in o.get("why") or []:
        n += 1; steps.append({"n": n, "kind": "rule_eval", "input_facts": [], "rule_ref": None, "outcome": str(w)[:300], "visible_to": "reviewer"})
    for t in o.get("reviewer_trace") or []:
        n += 1; steps.append({"n": n, "kind": "fact_check", "input_facts": [], "rule_ref": None, "outcome": str(t)[:300], "visible_to": "reviewer"})
    prov = (o.get("sources") or {}).get("provisions") or []
    if val:
        src, _, art = (prov[0].partition("|") if prov else ("", "", ""))
        n += 1; steps.append({"n": n, "kind": "validity_check", "input_facts": [],
                              "rule_ref": {"source_id": src, "article": art or None} if src else None,
                              "outcome": ("blockers: " + ", ".join(blockers)) if blockers else str(val.get("reason") or "not checked")[:300],
                              "visible_to": "reviewer"})
    n += 1; steps.append({"n": n, "kind": "block" if blocked else "rule_eval", "input_facts": [], "rule_ref": None,
                          "outcome": str(o.get("state_chip") or o.get("state")), "visible_to": "owner"})
    basis = []
    if blocked: basis.append("blocked_legal_validation")
    if synthetic: basis.append("test_rule")
    if not val.get("certified"): basis.append("source_not_current")
    if "conflict" in blockers: basis.append("source_conflict")
    if o.get("rule_status") in ("draft_unreviewed", "no_reviewed_rule", "blocked_source_conflict"): basis.append("rule_not_reviewed")
    level = "medium" if synthetic and not blocked else "low"
    return {
        "contract": "herbiz.decision_explanation/1.0", "engine": {"commit": P.B_COMMIT, "fixture_contract": P.B_FIXTURE_CONTRACT},
        "obligation_id": str(o["id"]), "state": str(o.get("state")), "state_chip": str(o.get("state_chip") or o.get("state")),
        "reason": o.get("reason"), "rule_status": o.get("rule_status"), "label": o.get("label"),
        "execution_mode": execution_mode or ("simulated" if synthetic else "deterministic"),
        "steps": steps, "missing_information": list(o.get("missing_information") or []),
        "professional_review": list(o.get("professional_review") or []),
        "confidence": _confidence(level, basis or ["rule_not_reviewed"]),
        "review": {"release_approved": False, "reviewer_needed": None, "human_review_required": True},
    }


def _sources_of(obligations: list[dict]) -> list[dict]:
    out, seen = [], set()
    for o in obligations:
        s = o.get("sources") or {}
        for key in (s.get("provisions") or []) + (s.get("source_candidates") or []):
            src, _, art = key.partition("|")
            if (src, art) in seen:
                continue
            seen.add((src, art))
            e = source_entry(src, art or None)
            if e:
                out.append(e)
    return out


def _worst(decisions: list[dict], default_level="low", default_basis=("rule_not_reviewed",)) -> dict:
    if not decisions:
        return _confidence(default_level, list(default_basis))
    lvl = min((d["confidence"]["level"] for d in decisions), key=LEVEL.get)
    return _confidence(lvl, [b for d in decisions for b in d["confidence"]["basis"]])


def _flags(decisions: list[dict]) -> list[str]:
    f = []
    if any(d["rule_status"] == "synthetic_test" for d in decisions): f.append("test_rule")
    if any(d["state"].startswith("blocked") for d in decisions): f.append("blocked_legal_validation")
    if any("source_conflict" in d["confidence"]["basis"] for d in decisions): f.append("conflict")
    return f


def base(channel: str, session_id: str, profile_id, request: dict) -> dict:
    return {"contract": "herbiz.audit_record/1.0", "record_id": str(uuid.uuid4()), "at": now_iso(), "build": build_info(),
            "channel": channel, "session_id": session_id, "profile_id": profile_id, "synthetic": True, "request": request,
            "retrieval": None, "decisions": [], "sources": [], "error": None,
            "sanitizer": {"version": "a1-sanitizer-1.0", "passed": True, "findings": []},
            "integrity": {"seq": 1, "prev_record_sha256": "0" * 64, "record_sha256": "0" * 64}}


def plain_request(kind: str) -> dict:
    return {"kind": kind, "query_sha256": None, "query_text": None, "gate": None}


def engine_record(channel: str, session_id: str, profile_id, kind: str, report: dict | None, shown: bytes, status: str,
                  execution_mode: str = "deterministic", only_ids=None, error: str | None = None, extra_flags=()) -> dict:
    """dashboard / ct records: decisions from the engine report behind the owner view."""
    obs = [o for o in (report or {}).get("obligations", []) if only_ids is None or o["id"] in only_ids]
    decs = [decision(o, "simulated" if channel == "ct" else None) for o in obs]
    rec = base(channel, session_id, profile_id, plain_request(kind))
    rec.update(decisions=decs, sources=_sources_of(obs), error=error,
               answer={"mode": "engine", "execution_mode": execution_mode, "status": status,
                       "shown_text_sha256": sha(shown), "flags": sorted(set(_flags(decs)) | set(extra_flags))},
               confidence=_worst(decs), review={"release_approved": False, "human_review_required": True,
                                                "reviewer_needed": "an FTA-registered tax agent" if decs else None})
    return rec


def simple_record(channel: str, session_id: str, kind: str, shown: bytes, status: str, execution_mode: str, basis,
                  reviewer: str | None, sources=(), flags=(), error: str | None = None, profile_id=None) -> dict:
    """finance / change_replay records (no engine decisions)."""
    rec = base(channel, session_id, profile_id, plain_request(kind))
    rec.update(sources=[s for s in sources if s], error=error,
               answer={"mode": "engine", "execution_mode": execution_mode, "status": status, "shown_text_sha256": sha(shown),
                       "flags": sorted(set(flags))},
               confidence=_confidence("low", basis), review={"release_approved": False, "human_review_required": True,
                                                             "reviewer_needed": reviewer})
    return rec


def ask_record(session_id: str, kind: str, question: str | None, gate: dict | None, result: dict | None, shown: bytes,
               error: str | None = None, retrieval: dict | None = None) -> dict:
    """ask records. T2-D2: query_text only when the gate allowed it; a blocked question leaves no text and no hash."""
    g = None if gate is None else {"action": gate["action"], "control_ids": list(gate.get("control_ids") or []),
                                   "detector_ids": list(gate.get("detector_ids") or []), "clause_ids": list(gate.get("clause_ids") or []),
                                   "kb_version": (gate.get("log_record") or {}).get("kb_version")}
    blocked = g is not None and g["action"] == "block"
    req = {"kind": kind, "query_sha256": None if (blocked or not question) else query_sha256(question),
           "query_text": question if (g is not None and g["action"] == "allow" and question) else None, "gate": g}
    rec = base("ask", session_id, None, req)
    r = result or {}
    mode = "blocked" if blocked else ("recorded" if r.get("mode") == "recorded" else "no_recording")
    level = (r.get("guard") or {}).get("level")
    flags = []
    if not blocked and level not in ("complete_for_map", "not_applicable"):
        flags.append("may_be_incomplete")                 # N-B1: incomplete or unknown/unchecked always carries the warning
    srcs = []
    for s in (r.get("sources") or []) + (r.get("passages") or []):
        sid = str(s.get("passage_id", "")).split(":")[0]
        m = re.match(r"Article (\d+(?: \(bis\))?)", s.get("locator") or "")
        e = source_entry(sid, m.group(1) if m else None)
        if e and (e["source_id"], e["article"]) not in {(x["source_id"], x["article"]) for x in srcs}:
            if s.get("validity") is not None:                 # A-4: unrecorded questions carry WS C validity 1.2 per source
                from . import t2_retrieval as R
                if r.get("mode") == "recorded":               # rc3 item 1: article-level only (M4); no whole-source inheritance
                    payload, kind = R.article_status(e["source_id"], e["article"])
                    e["validity"] = payload if kind in ("article", "amended") else None
                    if kind == "amended" and payload is not None:
                        flags.append("stale_source")
                else:
                    e["validity"] = R.validity(e["source_id"], e["article"] or "*")
            srcs.append(e)
    for e in srcs:
        v = e.get("validity") or {}
        if v.get("status") in ("outdated", "superseded"):
            flags.append("stale_source")
        if v.get("status") == "conflict":
            flags.append("conflict")
        if v.get("current_official_url") and (v.get("current_official_url_status") or {}).get("content_check") != "checked":
            flags.append("pending_unverified_link")
    flags = sorted(set(flags), key=flags.index)
    if blocked:
        retrieval = None                                      # CR-29: a blocked question is never searched
    basis = ["blocked"] if blocked else (["completeness_incomplete"] if "may_be_incomplete" in flags else []) + ["source_not_current", "rule_not_reviewed"]
    rec.update(sources=srcs, error=error, retrieval=retrieval,
               answer={"mode": mode, "execution_mode": "recorded_model" if mode == "recorded" else "deterministic",
                       "status": str(r.get("status") or ("blocked" if blocked else "no_recording")),
                       "shown_text_sha256": sha(shown), "flags": flags},
               confidence=_confidence("low", basis),
               review={"release_approved": False, "human_review_required": True,
                       "reviewer_needed": None if blocked else "an FTA-registered tax agent"})
    return rec
