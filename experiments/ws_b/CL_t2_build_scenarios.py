"""Task 2 B-6: decision-side golden fixtures for SC-1 (missing information) and SC-2 (conflicting rules), contract
herbiz.scenario/1.0. Every expected state is TAKEN FROM THE ENGINE'S OWN OUTPUT (t2-ws-b engine = fdbe131 + B-5 wording,
owner policy "blocked"), never typed by hand. Synthetic data only.

Usage: python3 experiments/ws_b/CL_t2_build_scenarios.py [--out fixtures/t2]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from compliance_agent.obligations import engine as E  # noqa: E402

AS_OF = dt.date(2026, 10, 17)
SC1_OBLIGATION = "C360-03"          # VAT returns and payment: has a draft deadline that must never be shown
SC2_OBLIGATION = "C360-05"          # VAT deregistration: blocked_source_conflict (WS-C gap G1)
SC1_STEPS = [
    ("profile_submitted", {"profile_id": "SYN-SC1", "legal_form": "not_sure", "jurisdiction_type": "not_sure", "vat_registration_status": "not_sure"}),
    ("owner_answers", {"legal_form": "llc", "jurisdiction_type": "mainland"}),
    ("profile_completed", {"activities": ["design"], "ct_registration_status": "not_registered", "emirate": "AE-DU",
                           "financial_year_end": "12-31", "has_employees": False, "keeps_accounting_records": True,
                           "licence_expiry_date": "2027-01-09", "licence_issue_date": "2026-01-10",
                           "revenue_band_last_12m": "375000-1000000", "vat_registration_status": "registered"}),
]


def _engine(fields: dict, obligation_id: str) -> tuple[dict, dict]:
    rep = E.assess({"profile_id": "SYN-SC", "synthetic": True, "fields": fields}, None, AS_OF, E.DEFAULT_POLICY)
    ob = next(o for o in rep["obligations"] if o["id"] == obligation_id)
    return rep, ob


def sc1() -> dict:
    fields, steps, prev_q = {}, [], None
    for n, (event, delta) in enumerate(SC1_STEPS, 1):
        fields.update({k: v for k, v in delta.items() if k != "profile_id"})
        rep, ob = _engine(fields, SC1_OBLIGATION)
        row = E.owner_row(ob)
        questions = len(rep["profile_gaps"]["questions"]) + len(ob["missing_information"])
        must_show = []
        if questions:
            must_show.append("questions" if prev_q is None else "fewer questions")
        if ob["state"] == "blocked_pending_legal_validation" and ob["owner_actions"]:
            must_show.append("what you can do now")
        flags = ["blocked_legal_validation"] if ob["state"] == "blocked_pending_legal_validation" else []
        if prev_q is not None and questions >= prev_q and questions:
            raise SystemExit("SC-1 step does not reduce the questions; scenario data is wrong")
        prev_q = questions
        assert row["deadline_display"] == E.NO_DATE          # a draft deadline is never shown (D-062)
        steps.append({"n": n, "event": event, "input": dict(delta, obligation_id=SC1_OBLIGATION),
                      "expected": {"state": ob["state"], "flags": flags, "must_show": must_show, "must_not": ["deadline"]},
                      "released_after": None if n == 1 else n - 1})
    return {"contract": "herbiz.scenario/1.0", "scenario_id": "SC-1", "title": "Missing information", "synthetic": True, "steps": steps}


def sc2() -> dict:
    fields = dict(SC1_STEPS[2][1], legal_form="llc", jurisdiction_type="mainland")
    _rep, ob = _engine(fields, SC2_OBLIGATION)
    assert ob["state"] == "blocked_pending_legal_validation" and ob["reason"] == "official sources conflict"
    steps = [
        {"n": 1, "event": "owner_question", "input": {"question_id": "SYN-SC2-Q", "topic": "vat_deregistration_deadline"},
         "expected": {"state": None, "flags": [], "must_show": [], "must_not": []}, "released_after": None},
        {"n": 2, "event": "retrieval_and_validity", "input": {"validity_key": "FTA-VAT-ER|14", "validity_status": "conflict",
                                                               "required_provisions": ["FTA-VAT-DL8|21", "FTA-VAT-ER|14"]},
         "expected": {"state": None, "flags": ["conflict"], "must_show": [], "must_not": []}, "released_after": 1},
        {"n": 3, "event": "agent_response", "input": {"obligation_id": SC2_OBLIGATION, "profile_fields": fields},
         "expected": {"state": ob["state"], "flags": ["conflict", "blocked_legal_validation"],
                      "must_show": ["both values with sources", "no precedence rule known", "FTA-registered tax agent"],
                      "must_not": ["deadline", "resolved"]}, "released_after": 2},
    ]
    return {"contract": "herbiz.scenario/1.0", "scenario_id": "SC-2", "title": "Conflicting rules", "synthetic": True, "steps": steps}


def build(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    res = {}
    for name, fx in (("CL_SC-1_decision.json", sc1()), ("CL_SC-2_decision.json", sc2())):
        (out / name).write_text(json.dumps(fx, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        res[name] = [s["expected"]["state"] for s in fx["steps"]]
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "fixtures" / "t2"))
    print(build(Path(ap.parse_args().out)))
