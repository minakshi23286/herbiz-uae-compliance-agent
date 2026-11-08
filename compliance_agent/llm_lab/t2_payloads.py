"""Task 2 B-3: WS-B payload builders for the frozen G1 contracts (semantics in contracts/ACK_B_v1.0.md).

  herbiz.retrieval_result/1.0      <- retrieve_v8.retrieve(...)
  herbiz.decision_explanation/1.0  <- one obligations-engine result (engine unchanged apart from B-5 wording)

Pure functions: no writes, no network, no model. Validation against WS-A's canonical schemas is done in the tests.
"""
from __future__ import annotations

import hashlib
import re

from . import retrieve_v8 as V8

RETRIEVAL_CONTRACT = "herbiz.retrieval_result/1.0"
DECISION_CONTRACT = "herbiz.decision_explanation/1.0"
EXECUTION_MODES = ("deterministic", "recorded_model", "proxy_outputs")   # WS-B never emits live_model (ACK_B I-1)
BASIS = ("blocked", "source_not_current", "test_rule", "completeness_incomplete", "no_reviewed_rule", "owner_reported_fact")


def query_sha256(question: str) -> str:
    """ACK_B I-3: lower-case, collapse whitespace runs to one space, trim; UTF-8; sha256 hex. No other normalisation."""
    return hashlib.sha256(re.sub(r"\s+", " ", question.lower()).strip().encode("utf-8")).hexdigest()


def retrieval_result(con, question: str, code_freeze: dict, kb_snapshot: dict, execution_mode: str = "deterministic",
                     include_text: bool = True) -> dict:
    if execution_mode not in EXECUTION_MODES:
        raise ValueError(f"execution_mode must be one of {EXECUTION_MODES}")
    r = V8.retrieve(con, question)
    items = [dict(i) for i in r["items"]]
    if not include_text:
        for i in items:
            i.pop("text", None)
    return {"contract": RETRIEVAL_CONTRACT, "retrieval_version": r["retrieval_version"], "code_freeze": code_freeze,
            "execution_mode": execution_mode, "query_sha256": query_sha256(question), "kb_snapshot": kb_snapshot,
            "items": items, "budget": r["budget"], "required_provisions": r["required_provisions"],
            "completeness": r["completeness"], "scope": r["scope"], "trace": r["trace"]}


def _rule_ref(provision: str | None):
    if not provision:
        return None
    src, _, art = provision.partition("|")
    return {"source_id": src, "article": None if art in ("", "*", "None") else art}


def decision_explanation(result: dict, engine_commit: str, fixture_contract: str) -> dict:
    """Wraps one engine obligation result (as returned in assess()["obligations"]) without changing it."""
    synthetic = result["rule_status"] == "synthetic_test"
    blocked = result["state"] == "blocked_pending_legal_validation"
    validity = result["sources"]["validity"] if isinstance(result["sources"].get("validity"), dict) else {}
    provisions = result["sources"].get("provisions") or []
    steps = []

    def step(kind, input_facts, rule_ref, outcome, visible_to):
        steps.append({"n": len(steps) + 1, "kind": kind, "input_facts": input_facts, "rule_ref": rule_ref,
                      "outcome": outcome, "visible_to": visible_to})

    missing = [m["fact"] for m in result["missing_information"]]
    step("fact_check", {"missing": missing}, None, "facts missing" if missing else "facts present", "owner")
    if result.get("already_done"):
        step("fact_check", {"owner_answer": "already done"}, None, "owner reported this step as done; no legal judgement", "owner")
    if result["rule_status"] not in ("no_reviewed_rule", "blocked_source_conflict") and not result.get("already_done"):
        trace = result.get("reviewer_trace") or result.get("why") or []
        outcome = "; ".join(trace)[:500] or "rule evaluated"
        step("rule_eval", [], _rule_ref(provisions[0] if provisions else None), outcome,
             "owner" if synthetic else "reviewer")             # draft real-law evaluations stay reviewer-only (D-062)
    if validity.get("checked"):
        outcome = "sources certified" if validity.get("certified") else "sources not approved: " + ", ".join(validity.get("blockers") or ["unknown"])
        step("validity_check", [], _rule_ref(provisions[0] if provisions else None), outcome, "reviewer")
    if blocked:
        step("policy", [], None, f"fail-closed policy: {result['reason']}", "reviewer")
        step("block", [], None, "blocked pending legal validation", "owner")

    basis = []
    if blocked:
        basis.append("blocked")
    if result["rule_status"] == "no_reviewed_rule":
        basis.append("no_reviewed_rule")
    if not synthetic and (validity.get("issue_kinds") or (validity.get("checked") and not validity.get("certified"))):
        basis.append("source_not_current")
    if result.get("already_done"):
        basis.append("owner_reported_fact")
    if synthetic:
        basis.append("test_rule")
    level = "low" if (blocked or "source_not_current" in basis or (not synthetic and not validity.get("certified"))) else "medium"
    return {"contract": DECISION_CONTRACT, "engine": {"commit": engine_commit, "fixture_contract": fixture_contract},
            "obligation_id": result["id"], "state": result["state"], "state_chip": result["state_chip"], "reason": result["reason"],
            "rule_status": result["rule_status"], "label": result["label"],
            "execution_mode": "simulated" if synthetic else "deterministic", "steps": steps,
            "missing_information": result["missing_information"], "professional_review": result["professional_review"],
            "confidence": {"level": level, "basis": basis, "numeric": None},
            "review": {"release_approved": False, "reviewer_needed": None if synthetic else "an FTA-registered tax agent",
                       "human_review_required": not synthetic}}
