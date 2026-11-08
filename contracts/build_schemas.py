"""Build the canonical HerBiz Task 2 contract schemas (WS A owns the bytes; semantics per doc 16 r2 §0.1).

    python3 contracts/build_schemas.py          # writes contracts/*.schema.json and contracts/CONTRACTS_INDEX.json
    python3 contracts/build_schemas.py --check  # exits 1 if the committed files differ from what this script builds

JSON Schema draft 2020-12, restricted to the keywords that contracts/validate.py implements (standard library only), so
the public export can validate payloads without third-party packages. No $ref: shared parts are inlined by this script.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRAFT = "https://json-schema.org/draft/2020-12/schema"

SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
MD5 = {"type": "string", "pattern": "^[0-9a-f]{32}$"}
COMMIT = {"type": "string", "pattern": "^[0-9a-f]{7,40}$"}
DATE = {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}
DATETIME_DUBAI = {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?\\+04:00$"}
URL = {"type": "string", "pattern": "^https://"}
UUID4 = {"type": "string", "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"}
STR = {"type": "string", "minLength": 1}
STR_OR_NULL = {"type": ["string", "null"]}
STR_LIST = {"type": "array", "items": {"type": "string"}}
ARTICLE = {"type": ["string", "null"]}
EVIDENCE_LEVEL = {"enum": ["observed", "observed_in_file", "observed_listing_only", "snippet_only", "supplied", "unresolved"]}  # WS C (N-C1)          # e.g. "21", "14(1)", "*"; null for a web page without articles


def obj(props: dict, required: list | None = None, extra: dict | None = None) -> dict:
    o = {"type": "object", "properties": props, "required": list(props) if required is None else required,
         "additionalProperties": False}
    if extra:
        o.update(extra)
    return o


def contract_const(name: str) -> dict:
    return {"const": name}


# ---------------------------------------------------------------- retrieval_result/1.0 (semantics: WS B)
def retrieval_item(with_text: bool) -> dict:
    props = {"rank": {"type": "integer", "minimum": 1}, "passage_id": STR, "source_id": STR, "article": ARTICLE,
             "locator": STR, "version_id": STR, "url": URL, "added_by": STR, "score": {"type": ["number", "null"]}}
    req = list(props)
    if with_text:
        props["text"] = {"type": "string"}      # internal only; never in audit records or exports (doc 16 §0.1, D4)
    return obj(props, req)


def retrieval_result(with_text: bool = True) -> dict:
    completeness = obj({
        "status": {"enum": ["complete_for_map", "incomplete", "unknown"]},
        "missing_required": {"type": "array", "items": obj({"source_id": STR, "article": ARTICLE})},
        "map_version": STR,
        "map_review_status": {"const": "draft-unreviewed"},
    }, extra={"if": {"properties": {"status": {"const": "complete_for_map"}}, "required": ["status"]},
              "then": {"properties": {"missing_required": {"maxItems": 0}}}})
    return obj({
        "contract": contract_const("herbiz.retrieval_result/1.0"),
        "retrieval_version": STR,
        "code_freeze": obj({"commit": COMMIT, "files_sha256": {"type": "object", "additionalProperties": SHA256},
                            "config_sha256": SHA256}),
        "execution_mode": {"enum": ["deterministic", "recorded_model", "proxy_outputs", "live_model"]},
        "query_sha256": SHA256,
        "kb_snapshot": obj({"snapshot_date": DATE, "db_md5": MD5, "manifest_version": STR}),
        "items": {"type": "array", "items": retrieval_item(with_text)},
        "budget": obj({"max_passages": {"type": "integer", "minimum": 1}, "returned": {"type": "integer", "minimum": 0}}),
        "required_provisions": {"type": "array", "items": obj({
            "source_id": STR, "article": ARTICLE, "role": {"enum": ["primary", "base", "supporting"]},
            "from": {"type": "string", "pattern": "^provision_map_v[0-9]+$"}})},
        "completeness": completeness,
        "scope": obj({"in_scope": {"type": "boolean"}, "class": {"enum": ["in_scope", "out_of_scope", "unsupported"]},
                      "reason": {"type": "string"}}),
        "trace": {"type": "array", "items": obj({"step": STR, "detail": {"type": "string"}})},
    })


# ---------------------------------------------------------------- decision_explanation/1.0 (semantics: WS B)
CONFIDENCE = obj({"level": {"enum": ["low", "medium", "high"]}, "basis": STR_LIST,
                  "numeric": {"const": None}})                      # T2-D3: categorical only; numeric always null
REVIEW = obj({"release_approved": {"const": False}, "reviewer_needed": STR_OR_NULL,
              "human_review_required": {"type": "boolean"}})


def decision_explanation() -> dict:
    return obj({
        "contract": contract_const("herbiz.decision_explanation/1.0"),
        "engine": obj({"commit": COMMIT, "fixture_contract": STR}),
        "obligation_id": STR, "state": STR, "state_chip": STR,
        "reason": STR_OR_NULL, "rule_status": STR_OR_NULL, "label": STR_OR_NULL,
        "execution_mode": {"enum": ["deterministic", "simulated"]},
        "steps": {"type": "array", "items": obj({
            "n": {"type": "integer", "minimum": 1},
            "kind": {"enum": ["fact_check", "rule_eval", "validity_check", "policy", "block"]},
            "input_facts": {"type": ["object", "array"]},
            "rule_ref": {"type": ["object", "null"], "properties": {"source_id": STR, "article": ARTICLE},
                         "required": ["source_id", "article"], "additionalProperties": False},
            "outcome": STR, "visible_to": {"enum": ["owner", "reviewer"]}})},
        "missing_information": {"type": "array"},
        "professional_review": {"type": "array"},
        "confidence": CONFIDENCE,
        "review": REVIEW,
    })


# ---------------------------------------------------------------- source_validity/1.2 (semantics: WS C)
def source_validity() -> dict:
    return obj({
        "contract": contract_const("herbiz.source_validity/1.2"),
        "key": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+\\|.+$"},          # "SRC|ART" or "SRC|*"
        "source_id": STR, "article": {"type": "string", "minLength": 1},
        "status": {"enum": ["current", "outdated", "superseded", "conflict", "not_collected", "unknown"]},
        "snapshot_date": DATE,
        "amendments": {"type": "array", "items": obj({"instrument": STR, "effective_date": {"type": ["string", "null"],
                       "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}, "articles_affected": STR_LIST, "evidence_level": EVIDENCE_LEVEL,
                       "url": URL})},
        "current_official_url": {"type": ["string", "null"], "pattern": "^https://"},   # displayed, never fetched
        # R-C1 (WS C, 18 Oct): whether that link was reachable and whether a person has checked its content
        "current_official_url_status": {"type": ["object", "null"], "additionalProperties": False,
                                        "required": ["link_status", "checked_on", "content_check"],
                                        "properties": {"link_status": {"enum": ["ok", "blocked_to_automation", "dead", "unchecked"]},
                                                       "checked_on": {"type": ["string", "null"], "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
                                                       "content_check": {"enum": ["pending_founder_verification", "founder_opened",
                                                                                  "not_checked"]}}},
        "conflicts": {"type": "array", "items": obj({
            "conflict_id": STR, "claim": STR,
            "values": {"type": "array", "minItems": 2, "items": obj({"source_id": STR, "url": URL, "value": STR,
                                                                    "locator": STR})},
            "precedence_known": {"const": False}, "resolution": {"const": "escalate"}})},
        "link_status": {"enum": ["ok", "blocked_to_automation", "dead", "unchecked"]},
        "link_checked_on": {"type": ["string", "null"], "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
        "review_status": {"enum": ["discovered", "candidate", "reviewed"]},            # never "approved" in Task 2
        "reuse_terms": obj({"publisher_terms_url": {"type": ["string", "null"], "pattern": "^https://"},
                            "redistribution": {"enum": ["unknown", "link_only", "permitted"]}, "note": {"type": "string"}}),
        "release_approved": {"const": False},
    }, extra={"allOf": [
        {"if": {"properties": {"status": {"const": "conflict"}}, "required": ["status"]},
         "then": {"properties": {"conflicts": {"minItems": 1}}}},
        {"if": {"properties": {"status": {"enum": ["outdated", "superseded"]}}, "required": ["status"]},
         "then": {"properties": {"amendments": {"minItems": 1}}}},
        # R-C1: the status block is present exactly when there is a current official URL
        {"if": {"properties": {"current_official_url": {"type": "string"}}, "required": ["current_official_url"]},
         "then": {"properties": {"current_official_url_status": {"type": "object"}}}},
        {"if": {"properties": {"current_official_url": {"type": "null"}}, "required": ["current_official_url"]},
         "then": {"properties": {"current_official_url_status": {"type": "null"}}}},
    ]})


# ---------------------------------------------------------------- audit_record/1.0 (semantics: WS A)
EXECUTION_CLASSES_RUNTIME = ["deterministic", "recorded_model", "proxy_outputs", "simulated"]   # no live inference in Task 2
FLAGS = ["may_be_incomplete", "stale_source", "conflict", "test_rule", "blocked_legal_validation", "simulated_reviewer",
         "pending_unverified_link"]          # R-C1: a current official link whose content no person has checked yet


def audit_record() -> dict:
    gate = {"type": ["object", "null"], "additionalProperties": False,
            "required": ["action", "control_ids", "detector_ids", "clause_ids", "kb_version"],
            "properties": {"action": {"enum": ["allow", "warn", "block"]}, "control_ids": STR_LIST,
                           "detector_ids": STR_LIST, "clause_ids": STR_LIST, "kb_version": STR_OR_NULL}}
    request = obj({"kind": STR, "query_sha256": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"},
                   "query_text": STR_OR_NULL, "gate": gate},
                  # T2-D2: question text only when the CR-29 gate allowed it (and the profile is synthetic: top level)
                  extra={"if": {"properties": {"query_text": {"type": "string"}}, "required": ["query_text"]},
                         "then": {"properties": {"gate": {"type": "object", "properties": {"action": {"const": "allow"}},
                                                          "required": ["action"]}}}})
    retrieval_in_audit = retrieval_result(with_text=False)
    retrieval_in_audit["type"] = ["object", "null"]
    source_entry = obj({"source_id": STR, "article": ARTICLE, "title": STR, "url": URL, "evidence_level": EVIDENCE_LEVEL,
                        "retrieved_on": {"type": ["string", "null"], "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
                        "review_status": STR, "validity": {"oneOf": [{"type": "null"}, source_validity()]}})
    return obj({
        "contract": contract_const("herbiz.audit_record/1.0"),
        "record_id": UUID4, "at": DATETIME_DUBAI,
        "build": obj({"integration_commit": COMMIT, "b_commit": COMMIT, "c_commit": COMMIT, "snapshot_date": DATE,
                      "contracts": {"type": "object", "additionalProperties": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+$"}}}),
        "channel": {"enum": ["ask", "dashboard", "ct", "finance", "change_replay", "scenario"]},
        "session_id": STR, "profile_id": STR_OR_NULL,
        "synthetic": {"const": True},                                  # Task 2: synthetic only
        "request": request,
        "retrieval": retrieval_in_audit,                               # retrieval_result minus items[].text
        "decisions": {"type": "array", "items": decision_explanation()},
        "sources": {"type": "array", "items": source_entry},
        "answer": obj({"mode": {"enum": ["recorded", "no_recording", "engine", "blocked", "scenario"]},
                       "execution_mode": {"enum": EXECUTION_CLASSES_RUNTIME},
                       "status": STR, "shown_text_sha256": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"},
                       "flags": {"type": "array", "uniqueItems": True, "items": {"enum": FLAGS}}}),
        "confidence": CONFIDENCE, "review": REVIEW,
        "error": STR_OR_NULL,
        "sanitizer": obj({"version": STR, "passed": {"type": "boolean"}, "findings": STR_LIST}),
        "integrity": obj({"seq": {"type": "integer", "minimum": 1}, "prev_record_sha256": SHA256, "record_sha256": SHA256}),
    }, extra={"allOf": [
        # a blocked answer never carries retrieval output; an audit-write failure never carries an answer status
        {"if": {"properties": {"answer": {"properties": {"mode": {"const": "blocked"}}, "required": ["mode"]}},
                "required": ["answer"]},
         "then": {"properties": {"retrieval": {"type": "null"}, "request": {"properties": {"query_text": {"type": "null"}}}}}},
    ]})


# ---------------------------------------------------------------- scenario/1.0 (semantics: WS A; data B and C)
def scenario() -> dict:
    return obj({
        "contract": contract_const("herbiz.scenario/1.0"),
        "scenario_id": {"enum": ["SC-1", "SC-2", "SC-3"]},
        "title": STR, "synthetic": {"const": True},
        "steps": {"type": "array", "minItems": 3, "items": obj({
            "n": {"type": "integer", "minimum": 1}, "event": STR, "input": {"type": "object"},
            "expected": obj({"state": STR_OR_NULL, "flags": {"type": "array", "uniqueItems": True, "items": {"enum": FLAGS}},
                             "must_not": STR_LIST, "must_show": STR_LIST}),
            "released_after": {"type": ["integer", "null"], "minimum": 1}})},
        "run": {"type": "array", "items": obj({"n": {"type": "integer", "minimum": 1}, "record_id": UUID4,
                                               "response_sha256": SHA256})},
    }, required=["contract", "scenario_id", "title", "synthetic", "steps"])


# ---------------------------------------------------------------- capability_declaration/1.0 (semantics: WS A)
CLASSES = ["deterministic", "recorded_model", "proxy_outputs", "live_inference", "tool_use", "simulated", "planned"]


def capability_declaration() -> dict:
    return obj({
        "contract": contract_const("herbiz.capability_declaration/1.0"),
        "declared_on": DATE,
        "build": obj({"integration_commit": COMMIT, "b_commit": COMMIT, "c_commit": COMMIT}),
        "capabilities": {"type": "array", "minItems": 1, "items": obj({
            "id": {"type": "string", "pattern": "^CAP-[A-Z0-9-]+$"}, "class": {"enum": CLASSES},
            "owner": {"enum": ["A", "B", "C"]}, "description": STR, "active": {"type": "boolean"},
            "evidence": STR_LIST},
            # live inference may only be declared inactive in Task 2 (D5e)
            extra={"allOf": [{"if": {"properties": {"class": {"const": "live_inference"}}, "required": ["class"]},
                              "then": {"properties": {"active": {"const": False}}}},
                             {"if": {"properties": {"class": {"const": "planned"}}, "required": ["class"]},
                              "then": {"properties": {"active": {"const": False}}}}]})},
        "metrics": {"type": "array", "items": obj({"name": STR, "value": {"type": ["number", "string"]},
                                                   "class": {"enum": CLASSES}, "set": STR, "date": DATE})},
    }, required=["contract", "declared_on", "build", "capabilities"])


CONTRACTS = {
    "herbiz.retrieval_result/1.0": ("retrieval_result_1.0.schema.json", retrieval_result, "WS B"),
    "herbiz.decision_explanation/1.0": ("decision_explanation_1.0.schema.json", decision_explanation, "WS B"),
    "herbiz.source_validity/1.2": ("source_validity_1.2.schema.json", source_validity, "WS C"),
    "herbiz.audit_record/1.0": ("audit_record_1.0.schema.json", audit_record, "WS A"),
    "herbiz.scenario/1.0": ("scenario_1.0.schema.json", scenario, "WS A"),
    "herbiz.capability_declaration/1.0": ("capability_declaration_1.0.schema.json", capability_declaration, "WS A"),
}


def render(name: str, fn) -> bytes:
    s = copy.deepcopy(fn())
    s = {"$schema": DRAFT, "$id": f"https://herbiz.invalid/contracts/{CONTRACTS[name][0]}", "title": name, **s}
    return (json.dumps(s, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def build() -> dict[str, bytes]:
    out = {fname: render(name, fn) for name, (fname, fn, _) in CONTRACTS.items()}
    index = {"_notice": "HerBiz Task 2 canonical contract schemas (doc 16 r2). WS A owns the bytes; semantics owners named per "
                        "contract. WS B and WS C keep byte-identical read-only copies and check these sha256 values.",
             "contracts": {name: {"file": fname, "sha256": hashlib.sha256(out[fname]).hexdigest(), "semantics_owner": owner}
                           for name, (fname, _, owner) in CONTRACTS.items()}}
    out["CONTRACTS_INDEX.json"] = (json.dumps(index, indent=1, sort_keys=True) + "\n").encode("utf-8")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    files = build()
    if a.check:
        bad = [f for f, b in files.items() if not (HERE / f).exists() or (HERE / f).read_bytes() != b]
        print("OK" if not bad else f"DIFFERS: {bad}")
        return 1 if bad else 0
    for f, b in files.items():
        (HERE / f).write_bytes(b)
    print(json.dumps(json.loads(files["CONTRACTS_INDEX.json"])["contracts"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
