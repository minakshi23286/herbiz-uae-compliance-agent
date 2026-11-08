"""Builds the stable, read-only demonstration fixture for Workstream A (founder decisions D-062, D-064). Offline, no spend.

Output (deterministic for a given --as-of): docs/360/demo/wsa/CL_WSA_DEMO_FIXTURE_v1.json and its .sha256.
WS-A reads these files; it never imports B's engine and B never edits WS-A's files.
Usage: python3 experiments/ws_b/CL_build_wsa_demo_fixture.py [--as-of 2026-10-17] [--out docs/360/demo/wsa]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from compliance_agent.obligations import ct_demo as D, engine as E, validity as V  # noqa: E402

FIXTURE_CONTRACT = "ws-b-demo-0.4"   # additive change -> 0.2 and WS-A told in writing; renamed/changed field -> 1.0
DB_COPY = ROOT / "data" / "CL_ws_b_exact_copy.sqlite3"
PERSONAS = ROOT / "fixtures" / "obligations" / "CL_ct_demo_personas_wsc.json"
OTHER = ROOT / "fixtures" / "obligations" / "CL_synthetic_profiles_360.json"


def build(as_of: dt.date, out: Path) -> dict:
    sv = V.load_pinned(DB_COPY, today=as_of.isoformat())
    c = D.load_c_labels(as_of.isoformat())
    personas = json.loads(PERSONAS.read_text(encoding="utf-8"))
    demo = [D.assess_demo(p, sv, as_of, c) for p in personas["profiles"]]
    other = [E.assess(p, sv, as_of, E.DEFAULT_POLICY) for p in json.loads(OTHER.read_text(encoding="utf-8"))["profiles"]]
    for rep in demo + other:
        rep["owner_rows"] = [dict(E.owner_row(r), **({"demo_scenario": r["demo_scenario"]} if "demo_scenario" in r else {}))
                             for r in rep["obligations"]]
    violations = [v for r in demo for v in D.demo_wording_violations(r)] + [v for r in other for v in E.wording_violations(r)]
    if violations:
        raise SystemExit(f"refusing to write the fixture: {len(violations)} wording violations, e.g. {violations[0]}")
    fixture = {
        "fixture_contract": FIXTURE_CONTRACT, "as_of": as_of.isoformat(), "business_line": "HomepreunerHub / HerBiz",
        "audience": "owner view (fail closed, D-062)", "banner": E.BANNER, "demo_scenario_label": D.DEMO_LABEL,
        "display_rules": [
            "Show the banner on every screen.",
            "Show demo_scenario.demo_label on every corporate-tax row; validated_guidance is always false.",
            "Show state 'Blocked: legal validation' for every corporate-tax row; never show an eligibility, relief or filing outcome.",
            "Show source_label.user_wording, the uncertainty chip and the citations with their retrieval dates.",
            "TEST RULE rows are invented examples; show their label 'TEST RULE — not law'.",
            "Never show 'approved', 'verified' or 'certified'. HerBiz does not file or pay anything.",
            "Owner screens show ONLY each report's banner, profile_gaps.questions and owner_rows (with their demo_scenario). "
            "The obligations array is a reviewer/developer view and must not be shown to owners.",
            "Show each citation's citation_chip exactly as given (from WS-C sources360 0.2).",
            "Show owner_rows.deadline_display as given: real-law rows always carry the standard no-date sentence; "
            "TEST RULE dates are prefixed 'TEST RULE date (made up): '."],
        "owner_fields": list(E.OWNER_FIELDS),
        "states": {s: E.STATE_TEXT[s] for s in E.STATES},
        "pins": {"ws_c_validity_contract_1_1": V.PINNED_COMMIT, "ws_c_sources360": D.SOURCES360_COMMIT,
                 "validity_available": sv.available, "sources360_available": c["available"]},
        "persona_source": personas["source"], "persona_mapping_notes": personas["mapping_notes"],
        "persona_facts_not_in_schema": {p["profile_id"]: p["persona_facts_not_in_schema"] for p in personas["profiles"]},
        "ct_demo_personas": demo, "other_synthetic_profiles": other,
    }
    out.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(fixture, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    path = out / "CL_WSA_DEMO_FIXTURE_v1.json"
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    (out / "CL_WSA_DEMO_FIXTURE_v1.json.sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return {"sha256": digest, "validity": sv.available, "sources360": c["available"], "personas": len(demo), "other": len(other)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default="2026-10-17")
    ap.add_argument("--out", default=str(ROOT / "docs" / "360" / "demo" / "wsa"))
    a = ap.parse_args()
    print(build(dt.date.fromisoformat(a.as_of), Path(a.out)))
