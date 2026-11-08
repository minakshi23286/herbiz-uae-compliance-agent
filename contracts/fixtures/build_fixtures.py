"""Build the golden fixtures for the HerBiz Task 2 contracts (doc 16 r2 §7). All synthetic; no official legal text.

    python3 contracts/fixtures/build_fixtures.py          # writes contracts/fixtures/*.json
    python3 contracts/fixtures/build_fixtures.py --check  # exit 1 if the committed fixtures differ

Naming: <contract>.valid[_<case>].json must validate; <contract>.invalid_<rule>.json must fail (for the named rule).
Scenario fixtures SC-1..SC-3 carry the expected flags that the A-2 scenario runner will check.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sha = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()
GENESIS = "0" * 64
PLACEHOLDER = "SYNTHETIC FIXTURE PASSAGE (no official text)"
Q_ALLOW = "SYNTHETIC: I registered for VAT voluntarily last year. Can I cancel my registration now?"


def retrieval() -> dict:
    return {
        "contract": "herbiz.retrieval_result/1.0", "retrieval_version": "fixture",
        "code_freeze": {"commit": "fdbe131", "files_sha256": {"compliance_agent/llm_lab/retrieve.py": sha("fixture-file")},
                        "config_sha256": sha("fixture-config")},
        "execution_mode": "deterministic", "query_sha256": sha(Q_ALLOW.lower()),
        "kb_snapshot": {"snapshot_date": "2026-10-17", "db_md5": "26e202b87a062288e56bcda1de9b0217", "manifest_version": "0.2.0"},
        "items": [
            {"rank": 1, "passage_id": "FIXTURE:DL8:17", "source_id": "FTA-VAT-DL8", "article": "17", "locator": "Article 17, p. 1",
             "version_id": "FTA-VAT-DL8@v1", "url": "https://tax.gov.ae/", "added_by": "fixture", "score": None, "text": PLACEHOLDER},
            {"rank": 2, "passage_id": "FIXTURE:ER:8", "source_id": "FTA-VAT-ER", "article": "8", "locator": "Article 8, p. 1",
             "version_id": "FTA-VAT-ER@v3", "url": "https://tax.gov.ae/", "added_by": "fixture", "score": 1.5, "text": PLACEHOLDER}],
        "budget": {"max_passages": 8, "returned": 2},
        "required_provisions": [
            {"source_id": "FTA-VAT-DL8", "article": "21", "role": "primary", "from": "provision_map_v7"},
            {"source_id": "FTA-VAT-ER", "article": "14", "role": "primary", "from": "provision_map_v7"},
            {"source_id": "FTA-VAT-DL8", "article": "17", "role": "base", "from": "provision_map_v7"}],
        "completeness": {"status": "incomplete", "missing_required": [{"source_id": "FTA-VAT-DL8", "article": "21"},
                         {"source_id": "FTA-VAT-ER", "article": "14"}], "map_version": "provision_map_v7",
                         "map_review_status": "draft-unreviewed"},
        "scope": {"in_scope": True, "class": "in_scope", "reason": "VAT registration topic"},
        "trace": [{"step": "normalise", "detail": "fixture"}, {"step": "lexical_search", "detail": "fixture"}],
    }


def decision() -> dict:
    return {
        "contract": "herbiz.decision_explanation/1.0", "engine": {"commit": "fdbe131", "fixture_contract": "ws-b-demo-0.3"},
        "obligation_id": "SYN-OB-VAT-RETURN", "state": "blocked_pending_legal_validation", "state_chip": "Blocked: legal validation",
        "reason": "rule or sources not checked by a reviewer",          # internal, reviewer-facing (R-B1); owner text: owner_rows[].owner_text
        "rule_status": "draft_unreviewed", "label": "Draft — not reviewed", "execution_mode": "deterministic",
        "steps": [
            {"n": 1, "kind": "fact_check", "input_facts": {"vat_registration_status": "registered"}, "rule_ref": None,
             "outcome": "fact present", "visible_to": "owner"},
            {"n": 2, "kind": "validity_check", "input_facts": [], "rule_ref": {"source_id": "FTA-VAT-DL8", "article": "*"},
             "outcome": "source not reviewed", "visible_to": "reviewer"},
            {"n": 3, "kind": "block", "input_facts": [], "rule_ref": None, "outcome": "blocked pending legal validation",
             "visible_to": "owner"}],
        "missing_information": [], "professional_review": ["an FTA-registered tax agent"],
        "confidence": {"level": "low", "basis": ["blocked", "source_not_current"], "numeric": None},
        "review": {"release_approved": False, "reviewer_needed": "a qualified VAT reviewer", "human_review_required": True},
    }


def validity_conflict() -> dict:
    return {
        "contract": "herbiz.source_validity/1.2", "key": "FTA-VAT-ER|14", "source_id": "FTA-VAT-ER", "article": "14",
        "status": "conflict", "snapshot_date": "2026-10-17", "amendments": [], "current_official_url": None,
        "current_official_url_status": None,
        "conflicts": [{"conflict_id": "FIXTURE-CONFLICT-1", "claim": "deregistration application deadline (fixture)",
                       "values": [{"source_id": "FTA-VAT-ER", "url": "https://tax.gov.ae/", "value": "FIXTURE-VALUE-A",
                                   "locator": "Article 14(1)"},
                                  {"source_id": "FTA-VAT-REG-PAGE", "url": "https://tax.gov.ae/", "value": "FIXTURE-VALUE-B",
                                   "locator": "Paragraph 1"}],
                       "precedence_known": False, "resolution": "escalate"}],
        "link_status": "unchecked", "link_checked_on": None, "review_status": "candidate",
        "reuse_terms": {"publisher_terms_url": None, "redistribution": "unknown", "note": "fixture"},
        "release_approved": False,
    }


def validity_outdated() -> dict:
    v = validity_conflict()
    v.update({"key": "FTA-VAT-DL8|48", "source_id": "FTA-VAT-DL8", "article": "48", "status": "outdated", "conflicts": [],
              "amendments": [{"instrument": "FIXTURE amending instrument", "effective_date": "2026-01-01",
                              "articles_affected": ["48"], "evidence_level": "observed_listing_only", "url": "https://uaelegislation.gov.ae/"}],
              "current_official_url": "https://uaelegislation.gov.ae/",
              "current_official_url_status": {"link_status": "blocked_to_automation", "checked_on": "2026-10-18",
                                              "content_check": "pending_founder_verification"}})
    return v


def audit(blocked: bool = False) -> dict:
    r = retrieval()
    for it in r["items"]:
        del it["text"]                                        # audit records never carry passage text
    gate_allow = {"action": "allow", "control_ids": [], "detector_ids": [], "clause_ids": [], "kb_version": "0.1.1"}
    gate_block = {"action": "block", "control_ids": ["CTRL-NO-RAW-LOG", "CTRL-PD-MINIMISE"], "detector_ids": ["emirates_id"],
                  "clause_ids": ["CHARTER-P4", "HERBIZ-NO-RAW-LOG", "HERBIZ-SYNTHETIC-ONLY", "PDPL-ART4", "PDPL-ART5"],
                  "kb_version": "0.1.1"}
    rec = {
        "contract": "herbiz.audit_record/1.0", "record_id": "1b4e28ba-2fa1-4d3b-a3f5-ef19b5a7633b",
        "at": "2026-10-17T10:00:00+04:00",
        "build": {"integration_commit": "e42e37a", "b_commit": "fdbe131", "c_commit": "aa50dd4", "snapshot_date": "2026-10-17",
                  "contracts": {"herbiz.retrieval_result": "1.0", "herbiz.decision_explanation": "1.0",
                                "herbiz.source_validity": "1.2", "herbiz.audit_record": "1.0"}},
        "channel": "ask", "session_id": "SYN-SESSION-0001", "profile_id": "SYN-AMAL-B", "synthetic": True,
        "request": {"kind": "question", "query_sha256": sha(Q_ALLOW.lower()), "query_text": Q_ALLOW, "gate": gate_allow},
        "retrieval": r, "decisions": [decision()],
        "sources": [{"source_id": "FTA-VAT-ER", "article": "14", "title": "VAT Executive Regulation (fixture title)",
                     "url": "https://tax.gov.ae/", "evidence_level": "observed", "retrieved_on": "2026-10-16",
                     "review_status": "candidate", "validity": validity_conflict()}],
        "answer": {"mode": "recorded", "execution_mode": "recorded_model", "status": "answered",
                   "shown_text_sha256": sha("fixture answer"), "flags": ["may_be_incomplete", "conflict"]},
        "confidence": {"level": "low", "basis": ["incomplete", "conflict"], "numeric": None},
        "review": {"release_approved": False, "reviewer_needed": "a qualified VAT reviewer", "human_review_required": True},
        "error": None, "sanitizer": {"version": "fixture", "passed": True, "findings": []},
        "integrity": {"seq": 1, "prev_record_sha256": GENESIS, "record_sha256": sha("fixture record 1")},
    }
    if blocked:
        rec.update({"record_id": "6fa459ea-ee8a-4ca4-894e-db77e160355e", "decisions": [], "sources": [], "retrieval": None,
                    "request": {"kind": "question", "query_sha256": None, "query_text": None, "gate": gate_block},
                    "answer": {"mode": "blocked", "execution_mode": "deterministic", "status": "blocked",
                               "shown_text_sha256": sha("fixture block message"), "flags": []},
                    "confidence": {"level": "low", "basis": ["blocked"], "numeric": None},
                    "integrity": {"seq": 2, "prev_record_sha256": sha("fixture record 1"), "record_sha256": sha("fixture record 2")}})
    return rec


# R-B2 (WS B, 18 Oct): a step with a non-null expected.state names the obligation it is about in input.obligation_id; the
# scenario runner compares expected.state with that obligation's state. WS B's SC-1 data (B-6) replaces these placeholders.
SC1_OBLIGATION = "SYN-OB-VAT-REGISTRATION"
SC1_COMPLETE_PROFILE = {"emirate": "AE-DU", "jurisdiction_type": "mainland", "legal_form": "llc", "person_type": "juridical_person",
                        "activities": ["design"], "licence_issue_date": "2026-01-10", "licence_expiry_date": "2027-01-09",
                        "financial_year_end": "12-31", "revenue_band_last_12m": "187500-375000",
                        "vat_registration_status": "not_registered", "ct_registration_status": "not_registered",
                        "has_employees": False, "keeps_accounting_records": True}   # values checked with WS B's profile.validate


def scenarios() -> dict[str, dict]:
    base = lambda sid, title, steps: {"contract": "herbiz.scenario/1.0", "scenario_id": sid, "title": title, "synthetic": True,
                                      "steps": [{**s, "released_after": (s["n"] - 1) or None} for s in steps]}
    e = lambda state=None, flags=(), must_not=(), must_show=(): {"state": state, "flags": list(flags), "must_not": list(must_not),
                                                                 "must_show": list(must_show)}
    return {
        "SC-1": base("SC-1", "Missing information", [
            {"n": 1, "event": "profile_submitted", "input": {"obligation_id": SC1_OBLIGATION, "profile_id": "SYN-SC1", "legal_form": "not_sure",
                                                            "jurisdiction_type": "not_sure", "vat_registration_status": "not_sure"},
             "expected": e("insufficient_information", must_show=["questions"])},
            {"n": 2, "event": "owner_answers", "input": {"obligation_id": SC1_OBLIGATION, "legal_form": "llc", "jurisdiction_type": "mainland"},
             "expected": e("insufficient_information", must_show=["fewer questions"])},
            {"n": 3, "event": "profile_completed", "input": {"obligation_id": SC1_OBLIGATION, **SC1_COMPLETE_PROFILE},
             "expected": e("blocked_pending_legal_validation", flags=["blocked_legal_validation"],
                           must_show=["what you can do now"], must_not=["deadline"])}]),
        "SC-2": base("SC-2", "Conflicting rules", [
            {"n": 1, "event": "owner_question", "input": {"question_id": "SYN-SC2-Q", "topic": "vat_deregistration_deadline"},
             "expected": e(None)},
            {"n": 2, "event": "retrieval_and_validity", "input": {"validity_key": "FTA-VAT-ER|14", "validity_status": "conflict"},
             "expected": e(None, flags=["conflict"])},
            {"n": 3, "event": "agent_response", "input": {},
             "expected": e(None, flags=["conflict"], must_show=["both values with sources", "no precedence rule known",
                                                                "FTA-registered tax agent"], must_not=["deadline", "resolved"])}]),
        "SC-3": base("SC-3", "Outdated source", [
            {"n": 1, "event": "owner_question", "input": {"question_id": "SYN-SC3-Q", "touches": "FTA-VAT-DL8|48"},
             "expected": e(None)},
            {"n": 2, "event": "validity_result", "input": {"validity_key": "FTA-VAT-DL8|48", "validity_status": "outdated"},
             "expected": e(None, flags=["stale_source"])},
            {"n": 3, "event": "agent_response", "input": {},
             "expected": e(None, flags=["stale_source", "pending_unverified_link"],
                           must_show=["current official link", "link not yet verified", "review required"],
                           must_not=["answer for the affected article", "fetched"])}]),
    }


def capabilities() -> dict:
    c = lambda i, cls, owner, d, active, ev: {"id": i, "class": cls, "owner": owner, "description": d, "active": active, "evidence": ev}
    return {
        "contract": "herbiz.capability_declaration/1.0", "declared_on": "2026-10-18",
        "build": {"integration_commit": "e42e37a", "b_commit": "fdbe131", "c_commit": "aa50dd4"},
        "capabilities": [
            c("CAP-ENGINE", "deterministic", "B", "Obligations engine: rules as data, fixed states, no model", True, ["tests/test_obligations.py"]),
            c("CAP-SEARCH", "deterministic", "B", "Offline lexical full-text search over the pinned VAT texts", True, ["compliance_agent/llm_lab/retrieve.py"]),
            c("CAP-VALIDITY", "deterministic", "C", "Source validity and conflict checks (no fetching)", True, ["compliance_agent/rag_c/"]),
            c("CAP-GATE", "deterministic", "C", "Personal-data intake gate (pattern checks from the policy KB)", True, ["tests/test_ws_c_policy_gate.py", "tests/test_privacy_gate_app.py"]),
            c("CAP-AUDIT", "deterministic", "A", "Per-response audit records (Task 2, planned until A-1)", False, ["contracts/audit_record_1.0.schema.json"]),
            c("CAP-RECORDED", "recorded_model", "A", "VAT answers produced by a language model in earlier offline runs and replayed", True, ["compliance_agent/ask.py"]),
            c("CAP-PROXY", "proxy_outputs", "B", "Classifier outputs written by an independent agent for offline evaluation; not model performance", True, ["docs/CL_evidence/ws_b/"]),
            c("CAP-LIVE", "live_inference", "A", "Language model called at run time: none in Task 2", False, []),
            c("CAP-TOOLS", "tool_use", "A", "Reads the local knowledge base and fixtures; writes its own logs. Does not browse, fetch, file, pay or send", True, ["compliance_agent/web.py"]),
            c("CAP-SIM", "simulated", "A", "Fictional businesses, TEST RULES, the simulated reviewer, scenario events, the change replay", True, ["fixtures/"]),
            c("CAP-PLANNED", "planned", "A", "Live model answers, six-domain coverage, scheduled monitoring, Arabic, real users, qualified review", False, []),
        ],
        "metrics": [{"name": "all_required_recall_unseen_v3", "value": 0.444, "class": "deterministic", "set": "unseen v3 (8 of 18)",
                     "date": "2026-10-16"}],
    }


def build() -> dict[str, dict]:
    out = {}
    out["retrieval_result.valid.json"] = retrieval()
    bad = retrieval(); bad["completeness"]["status"] = "complete_for_map"
    out["retrieval_result.invalid_complete_with_missing_required.json"] = bad
    out["decision_explanation.valid.json"] = decision()
    bad = decision(); bad["confidence"]["numeric"] = 0.82
    out["decision_explanation.invalid_numeric_confidence_T2-D3.json"] = bad
    out["source_validity.valid_conflict.json"] = validity_conflict()
    out["source_validity.valid_outdated.json"] = validity_outdated()
    bad = validity_conflict(); bad["review_status"] = "approved"
    out["source_validity.invalid_review_status_approved.json"] = bad
    bad = validity_outdated(); bad["current_official_url_status"] = None
    out["source_validity.invalid_url_without_status_R-C1.json"] = bad
    out["audit_record.valid_allow.json"] = audit()
    out["audit_record.valid_blocked.json"] = audit(blocked=True)
    bad = audit(blocked=True); bad["request"]["query_text"] = "SYNTHETIC question text that the gate blocked"
    out["audit_record.invalid_query_text_when_blocked_T2-D2.json"] = bad
    for sid, s in scenarios().items():
        out[f"scenario.valid_{sid}.json"] = s
    bad = copy.deepcopy(scenarios()["SC-1"]); bad["scenario_id"] = "SC-4"
    out["scenario.invalid_unknown_scenario.json"] = bad
    out["capability_declaration.valid.json"] = capabilities()
    bad = capabilities(); bad["capabilities"][7]["active"] = True
    out["capability_declaration.invalid_live_inference_active.json"] = bad
    return out


def render(obj) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    files = {f: render(o) for f, o in build().items()}
    if a.check:
        bad = [f for f, b in files.items() if not (HERE / f).exists() or (HERE / f).read_bytes() != b]
        extra = [p.name for p in HERE.glob("*.json") if p.name not in files]
        print("OK" if not bad and not extra else f"DIFFERS: {bad} EXTRA: {extra}")
        return 1 if bad or extra else 0
    for f, b in files.items():
        (HERE / f).write_bytes(b)
    print(f"{len(files)} fixtures written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
