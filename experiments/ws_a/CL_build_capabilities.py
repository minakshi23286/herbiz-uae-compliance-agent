"""Task 2 A-5: write capabilities.json (herbiz.capability_declaration/1.0, doc 16 r2 §6). Local only; no network.

    python3 experiments/ws_a/CL_build_capabilities.py [--check]

Every capability belongs to exactly one class; audit records carry the class in `execution_mode` (tests/test_capabilities.py
checks both directions). Metrics always carry class, set and date (D-106: the three recall figures are given together;
silent-incomplete 0 is by construction, never a completeness claim). `build.integration_commit` names the commit the code
was declared from; the submission export rewrites it to the exported commit and lists the change in its manifest.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from compliance_agent.mvp360 import pins as P  # noqa: E402

OUT = ROOT / "capabilities.json"
DECLARED_ON = "2026-10-18"


def cap(id_, cls, owner, desc, active, evidence):
    return {"id": id_, "class": cls, "owner": owner, "description": desc, "active": active, "evidence": evidence}


CAPABILITIES = [
    cap("CAP-ENGINE", "deterministic", "B", "Obligations engine: rules as data, fixed states, fail-closed owner view (D-062); no model",
        True, ["compliance_agent/obligations/engine.py", "tests/test_obligations.py"]),
    cap("CAP-RETRIEVAL", "deterministic", "B",
        "Task 2 retrieval v8 (interim candidate, D-102/D-106) for questions with no recorded answer: lexical search, provision "
        "map and expansion; never certifies completeness, so every answer is warned. Fails closed if its frozen code drifts",
        True, ["compliance_agent/llm_lab/retrieve_v8.py", "compliance_agent/t2_retrieval.py", "tests/test_a4_integration.py"]),
    cap("CAP-VALIDITY", "deterministic", "C",
        "Source validity and conflict status per passage from the WS C validity 1.2 export (110 records, not independently "
        "verified legal content); current official links are shown, never fetched. A recorded answer citing an article recorded as "
        "repealed, amended or in conflict is withheld (rc3)",
        True, ["knowledge_base/t2/CL_source_validity_1.2.json", "tests/test_ws_c_t2_delivery.py", "tests/test_recorded_validity.py"]),
    cap("CAP-GATE", "deterministic", "C", "Personal-data intake gate (CR-29): pattern checks from the policy KB before any search or log",
        True, ["compliance_agent/rag_c/policy_gate.py", "tests/test_ws_c_policy_gate.py", "tests/test_privacy_gate_app.py"]),
    cap("CAP-AUDIT", "deterministic", "A",
        "Per-response audit records on every owner channel: independent sanitizer, hash chain, reviewer-only view, fail closed",
        True, ["compliance_agent/audit_log.py", "compliance_agent/audit_sanitizer.py", "tests/test_audit_log.py"]),
    cap("CAP-SCENARIOS", "simulated", "A", "Error scenarios SC-1 to SC-3: synthetic events released one at a time and checked",
        True, ["compliance_agent/scenarios.py", "tests/test_scenarios.py"]),
    cap("CAP-RECORDED", "recorded_model", "A",
        "VAT answers produced by claude-sonnet-5-5 in offline runs on 16 Oct 2026 and replayed only for an exactly matching "
        "question; no model is called at run time",
        True, ["compliance_agent/ask.py", "tests/test_cx_demo.py"]),
    cap("CAP-PROXY", "proxy_outputs", "B",
        "Classifier outputs written by an independent agent for offline evaluation only; not model performance and not used by the app",
        True, ["docs/CL_evidence/ws_b/"]),
    cap("CAP-LIVE", "live_inference", "A", "Language model called at run time: none in Task 2 (D5e)", False, []),
    cap("CAP-TOOLS", "tool_use", "A",
        "Reads the local knowledge base and fixtures; writes its own audit log. Does not browse, fetch sources, file, pay or send",
        True, ["compliance_agent/web.py"]),
    cap("CAP-SIM", "simulated", "A",
        "Fictional businesses, TEST RULES, the simulated reviewer and the change replay; synthetic data only",
        True, ["fixtures/", "docs/360/demo/"]),
    cap("CAP-PLANNED", "planned", "A",
        "Not built: live model answers, six-domain coverage, scheduled source monitoring, Arabic, real users, qualified tax review",
        False, []),
]

METRICS = [
    {"name": "all_required_recall_v8", "value": 0.667, "class": "deterministic", "set": "independent holdout v10 (18/27), frozen code baefe25", "date": "2026-10-18"},
    {"name": "all_required_recall_v8", "value": 0.704, "class": "deterministic", "set": "independent holdout v11 (19/27), frozen code", "date": "2026-10-18"},
    {"name": "all_required_recall_v8", "value": 0.685, "class": "deterministic", "set": "v10 + v11 pooled (37/54); 70% target not met", "date": "2026-10-18"},
    {"name": "false_refusals_v8", "value": "4/27 (v10); 1/27 (v11)", "class": "deterministic", "set": "valid VAT questions classified out of scope", "date": "2026-10-18"},
    {"name": "warning_rate_v8", "value": 1.0, "class": "deterministic", "set": "v10 and v11: every answer carries the incompleteness warning", "date": "2026-10-18"},
    {"name": "silent_incomplete_v8", "value": "0 by construction (every answer warned); not completeness detection", "class": "deterministic",
     "set": "v10 and v11", "date": "2026-10-18"},
]


def build(commit: str) -> dict:
    return {"contract": "herbiz.capability_declaration/1.0", "declared_on": DECLARED_ON,
            "build": {"integration_commit": commit, "b_commit": P.B_COMMIT, "c_commit": P.C_T2_COMMIT},
            "capabilities": CAPABILITIES, "metrics": METRICS}


def render(d: dict) -> str:
    return json.dumps(d, indent=1, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if capabilities.json differs (ignoring integration_commit)")
    a = ap.parse_args(argv)
    if a.check:
        cur = json.loads(OUT.read_text(encoding="utf-8"))
        same = render(build(cur["build"]["integration_commit"])) == OUT.read_text(encoding="utf-8")
        print("OK" if same else "capabilities.json is out of date: run without --check")
        return 0 if same else 1
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    OUT.write_text(render(build(head)), encoding="utf-8")
    print(f"wrote {OUT.name} (declared from {head})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
