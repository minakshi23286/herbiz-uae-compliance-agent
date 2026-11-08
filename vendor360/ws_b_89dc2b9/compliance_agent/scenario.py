"""Staged demonstration with synthetic inputs. Stages release information progressively (research review, section 5).

Steps marked `human` are what a reviewer or owner does in the interface. The CLI demo performs them as a
SIMULATED REVIEWER so the run is reproducible; the web interface leaves them to the person using it.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .engine import Engine

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def load_fixtures() -> tuple[dict, dict]:
    sources = json.loads((FIXTURES / "CL_sources.json").read_text(encoding="utf-8"))["versions"]
    profiles = json.loads((FIXTURES / "CL_profiles.json").read_text(encoding="utf-8"))
    return sources, profiles


def stage0_baseline(e: Engine) -> list[str]:
    """Approved fixture corpus before the owner arrives (plus one hostile source that must stay quarantined)."""
    src, _ = load_fixtures()
    out = []
    for k in ("LIC_v1", "VAT_v1", "PRIV_A_v1", "FOOD_v1_irrelevant", "EINV_v1_future", "INJECT_v1_malicious"):
        r = e.ingest_source(src[k])
        out.append(f"{k}: {r['version_id']} {r['change_class']} -> {r['status']}")
    return out


def stage1_profile(e: Engine) -> list[str]:
    _, prof = load_fixtures()
    e.upsert_profile(prof["noor_stage1"])
    return ["Profile BP-0001 created without licensing context or licence expiry date."]


def stage2_owner_facts_and_source_update(e: Engine) -> list[str]:
    src, prof = load_fixtures()
    p = copy.deepcopy(prof["noor_stage1"])
    p["facts"].update(prof["noor_stage2_facts"])
    e.upsert_profile(p)
    r2 = e.ingest_source(src["LIC_v2_cosmetic"])
    r3 = e.ingest_source(src["LIC_v3_substantive"])
    return ["Owner supplied licensing context and the expiry date printed on the licence.",
            f"Cosmetic page change: {r2['version_id']} -> {r2['status']} (no action).",
            f"Substantive change: {r3['version_id']} -> {r3['status']}, review case {r3['case_id']}."]


def stage2_human_review(e: Engine) -> list[str]:
    r = e.review_source("SRC-FX-LIC@v3", "approve", "Demo Reviewer (simulated)", "domain reviewer (simulated)",
                        "SIMULATED: compared amended Section 2 with v1; new evidence item accepted.")
    return [f"SIMULATED REVIEWER approved SRC-FX-LIC@v3: {r}"]


def stage3_conflict(e: Engine) -> list[str]:
    src, _ = load_fixtures()
    r = e.ingest_source(src["PRIV_B_v1_conflict"])
    return [f"Second source on privacy notices: {r['version_id']} -> {r['status']}; conflicts with SRC-FX-PRIV-A."]


def stage4_clarification(e: Engine) -> list[str]:
    src, _ = load_fixtures()
    r = e.ingest_source(src["PRIV_B_v2_clarification"])
    return [f"Simulated authorised clarification: {r['version_id']} -> {r['status']}, review case {r['case_id']}."]


def stage4_human_review(e: Engine) -> list[str]:
    r = e.review_source("SRC-FX-PRIV-B@v2", "approve", "Demo Reviewer (simulated)", "domain reviewer (simulated)",
                        "SIMULATED: clarification withdraws FAQ 7; federal notice rule stands.")
    return [f"SIMULATED REVIEWER approved SRC-FX-PRIV-B@v2: {r}"]


def _case(e: Engine, key: str) -> dict:
    return e.s.one("SELECT * FROM cases WHERE dedupe_key = ?", (f"BP-0001:{key}",))


def stage5_incomplete_evidence(e: Engine) -> list[str]:
    c = _case(e, "LIC-RENEWAL")
    r = e.submit_evidence(c["case_id"], [{"requirement": "Copy of renewed licence showing the new expiry date",
                                         "description": "renewed_licence_2027.pdf (synthetic)", "provided": True}])
    return [f"Owner sent 1 of 2 evidence items for {c['case_id']}: status {r['status']}, still missing {r['missing']}."]


def stage5_human_attempt(e: Engine) -> list[str]:
    c = _case(e, "LIC-RENEWAL")
    r = e.review_case(c["case_id"], "approve", "Demo Reviewer (simulated)", "domain reviewer (simulated)",
                      "SIMULATED: tried to close with incomplete evidence.")
    return [f"SIMULATED REVIEWER tried to approve {c['case_id']} early: {r['outcome']} ({r.get('reason')})."]


def stage6_complete_and_resolve(e: Engine) -> list[str]:
    c = _case(e, "LIC-RENEWAL")
    e.submit_evidence(c["case_id"], [{"requirement": "Current tenancy or ownership document for the home address",
                                     "description": "tenancy_2026.pdf (synthetic)", "provided": True}])
    r = e.review_case(c["case_id"], "approve", "Demo Reviewer (simulated)", "domain reviewer (simulated)",
                      "SIMULATED: both evidence items checked against the amended Section 2.")
    return [f"Owner sent the second item; SIMULATED REVIEWER approved {c['case_id']}: {r}."]


STAGES = [
    ("0", "Approved fixture corpus loaded", stage0_baseline, None),
    ("1", "Owner profile lacks licensing details", stage1_profile, None),
    ("2", "Owner adds facts; a source update appears", stage2_owner_facts_and_source_update, stage2_human_review),
    ("3", "Another source is inconsistent", stage3_conflict, None),
    ("4", "Simulated authorised clarification arrives", stage4_clarification, stage4_human_review),
    ("5", "Owner supplies incomplete completion evidence", stage5_incomplete_evidence, stage5_human_attempt),
    ("6", "Owner completes evidence; reviewer resolves", stage6_complete_and_resolve, None),
]
