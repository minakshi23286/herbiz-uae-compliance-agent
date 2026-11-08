"""Workstream A presentation adapter for the HerBiz 360 MVP (read-only, fail-closed).

Inputs (both verified against their committed files):
  * WS B fixture `ws-b-demo-0.3` @ fdbe131 (sha256-checked): the fixed fictional businesses, their owner rows and the
    D-064 two-persona corporate-tax demo blocks (with WS C sources360 0.2 labels inside).
  * WS B engine @ fdbe131, run in an isolated process, ONLY for an owner's own made-up answers ("start blank"); its
    rows are projected with B's own `owner_row()`. Such profiles never get a corporate-tax demo block.
  * WS C sources360 0.2 @ aa50dd4 evidence for the rule-change replay.

Display rules (B fixture `display_rules`, D-062, D-064): owner screens show only the banner, profile questions and
owner rows (with demo_scenario). Corporate-tax rows always read "Blocked: legal validation". Nothing is approved,
verified or certified. Anything unexpected -> Incompatible -> the screen shows "unavailable", never a guess.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path

from . import pins

CONTENT = Path(__file__).resolve().parents[2] / "fixtures" / "mvp360" / "CL_mvp360_demo_content.json"
CT_BLOCKED = "Blocked: legal validation"
CT_IDS = {"C360-07", "C360-08", "C360-10", "C360-11", "C360-14"}       # B ct_demo.CT_TO_C keys @ fdbe131 (unchanged since 30a6f9a)
FORBIDDEN = re.compile(r"\b(approved|verified|certified)\b", re.I)        # B README rule 5: never shown, not even negated
NO_DATE = "No date is shown until a qualified reviewer has checked the rule and its sources."
EXTRA_ROW_FIELDS = {"demo_scenario"}
PERSONA_FILES = {"amal": "fixtures/obligations/CL_ct_demo_personas_wsc.json", "other": "fixtures/obligations/CL_synthetic_profiles_360.json"}


class Incompatible(pins.Unavailable):
    pass


class InputProblem(ValueError):
    """An answer in the owner's form that WS B's profile check refused. Plain words for the owner; never a guess."""
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field, self.message = field, message


FIELD_PLAIN = {
    "emirate": "Emirate", "jurisdiction_type": "Mainland or free zone", "licensing_authority": "Licensing authority",
    "legal_form": "Legal structure", "person_type": "Is the business you, or a separate company?", "activities": "Main activity",
    "licence_issue_date": "Licence issue date", "licence_expiry_date": "Licence expiry date", "financial_year_end": "Financial year ends on",
    "revenue_band_last_12m": "Sales in the last 12 months", "taxable_supplies_last_12m_aed": "Taxable sales in the last 12 months",
    "expected_taxable_supplies_next_30d_aed": "Expected sales in the next 30 days", "taxable_expenses_last_12m_aed": "Taxable expenses in the last 12 months",
    "vat_registration_status": "Registered for VAT?", "ct_registration_status": "Registered for corporate tax?",
    "has_employees": "Do you employ anyone?", "employees_count": "How many employees?",
    "keeps_accounting_records": "Do you keep records of sales and expenses?", "documents_available": "Documents you already have"}


def input_problem(message: str) -> InputProblem | None:
    """Turn WS B's ProfileError text into a plain message tied to one form field (None if it is not an input problem)."""
    if "ProfileError:" not in message:
        return None
    detail = message.split("ProfileError:", 1)[1].strip()
    if detail.startswith("unknown field"):
        return InputProblem("", "One answer in the form was not recognised. Please reset the form and try again.")
    field = detail.split(":")[0].split(" ")[0]
    label = FIELD_PLAIN.get(field, "One answer")
    if "is not one of" in detail:
        text = f"{label} — please choose one of the options, or tick \"Not sure\"."
    elif "must be a date" in detail:
        text = f"{label} — please enter a full date (day, month and year), or tick \"Not sure\"."
    elif "number" in detail:
        text = f"{label} — please enter a whole number of 0 or more, or tick \"Not sure\"."
    elif "MM-DD" in detail:
        text = f"{label} — please choose a date from the list, or \"Not sure\"."
    else:
        text = f"{label} — please fill this in, or tick \"Not sure\"."
    return InputProblem(field if field in FIELD_PLAIN else "", text)


def content() -> dict:
    return json.loads(CONTENT.read_text(encoding="utf-8"))


WITHHELD_TEXT = "Withheld while a recent change to an official source is reviewed. Nothing here has been updated automatically."


def suppressed() -> dict:
    """Claims withheld after review of a post-snapshot source change (founder approval 17 Oct 2026). Empty by default."""
    out = {}
    for e in content().get("suppressed_claims", []):
        if not all(e.get(k) for k in ("claim_id", "reason", "change_report_entry", "since")):
            raise Incompatible("a suppressed claim needs claim_id, reason, change_report_entry and since")
        out[e["claim_id"]] = e
    return out


def _apply_suppression(rows: list[dict]) -> list[dict]:
    sup = suppressed()
    out = []
    for r in rows:
        e = sup.get(r.get("id"))
        if e:
            r = {"id": r["id"], "title": r.get("title"), "state_chip": r.get("state_chip"), "label": r.get("label"),
                 "owner_text": WITHHELD_TEXT, "deadline_display": r.get("deadline_display"),
                 "suppressed": {"reason": e["reason"], "change_report_entry": e["change_report_entry"], "since": e["since"]}}
        out.append(r)
    return out


def fixture() -> dict:
    raw = pins.b_file(pins.B_FIXTURE)
    sha = hashlib.sha256(raw).hexdigest()
    committed = pins.b_file(pins.B_FIXTURE + ".sha256").decode().split()[0]
    if sha != pins.fixture_sha256() or sha != committed:
        raise Incompatible(f"WS B fixture checksum mismatch ({sha[:12]})")
    fx = json.loads(raw)
    if fx.get("fixture_contract") != pins.B_FIXTURE_CONTRACT or not str(fx.get("audience", "")).startswith("owner view"):
        raise Incompatible(f"WS B fixture contract {fx.get('fixture_contract')!r} / audience not supported")
    return fx


def _strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


def owner_view(report: dict, owner_fields: list[str]) -> dict:
    """Keep only owner-visible fields; enforce the corporate-tax and wording rules (fail closed)."""
    allowed = set(owner_fields) | EXTRA_ROW_FIELDS
    rows = []
    for r in report.get("owner_rows", []):
        row = {k: v for k, v in r.items() if k in allowed}
        rid = str(row.get("id", ""))
        ds = row.get("demo_scenario")
        if ds is not None and not isinstance(ds, dict):
            raise Incompatible(f"{rid}: demo_scenario is not an object")
        is_ct = rid in CT_IDS or ds is not None or "corporate tax" in str(row.get("title", "")).lower()
        if is_ct and row.get("state_chip") != CT_BLOCKED:
            raise Incompatible(f"{rid}: corporate tax must read '{CT_BLOCKED}'")
        if ds is not None:
            if ds.get("validated_guidance", False) is not False or ds.get("release_approved") is not False:
                raise Incompatible(f"{rid}: a demo scenario may never be validated or released")
            lab = ds.get("source_label")
            cites = (lab or {}).get("citations") or []
            if (not isinstance(lab, dict) or not lab.get("user_wording") or lab.get("uncertainty") not in ("high", "medium")
                    or not cites or any(not c.get("citation_chip") or not c.get("retrieved_at") or not c.get("url") for c in cites)):
                raise Incompatible(f"{rid}: source label, uncertainty or citations missing (B display rule 3)")
        # Legal review (17 Oct): no draft deadline text for real-law items; test-rule dates are labelled as made up.
        if rid.startswith("SYN-"):
            dd = str(row.get("deadline_display") or "")
            if dd and not dd.startswith("TEST RULE"):               # B labels its own test-rule dates from ws-b-demo-0.3
                row["deadline_display"] = "TEST RULE date (made up): " + dd
        else:
            row["deadline_display"] = NO_DATE
        rows.append(row)
    gaps = report.get("profile_gaps") or {}
    out = {"profile_id": report.get("profile_id"), "as_of": report.get("as_of"), "banner_b": report.get("banner"),
            "questions": list((gaps.get("questions") or {}).values()), "rows": rows}
    scan(out)
    return out


def scan(obj) -> None:
    """Whole-response wording scan (no negation exemption): any 'approved/verified/certified' fails closed."""
    bad = [x for x in _strings(obj) if FORBIDDEN.search(x)]
    if bad:
        raise Incompatible(f"owner-visible text contains approval wording: {bad[0][:80]}")


def _profiles() -> dict:
    out = {}
    for kind, path in PERSONA_FILES.items():
        for p in json.loads(pins.b_file(path))["profiles"]:
            out[p["profile_id"]] = {"id": p["profile_id"], "kind": kind, "name": p.get("persona") or p["profile_id"],
                                    "fields": p["fields"], "extra": p.get("persona_facts_not_in_schema", {})}
    return out


def personas() -> list[dict]:
    fx = fixture()
    have = {r["profile_id"] for r in fx["ct_demo_personas"] + fx["other_synthetic_profiles"]}
    ps = [p for p in _profiles().values() if p["id"] in have]
    return sorted(ps, key=lambda p: (p["kind"] != "amal", p["id"]))


def dashboard(profile_id: str | None = None, fields: dict | None = None, changed: set | None = None, with_report: bool = False):
    """A fixed fictional business from B's fixture, or the owner's own made-up answers through B's pinned engine."""
    fx = fixture()
    if profile_id:
        rep = next((r for r in fx["ct_demo_personas"] + fx["other_synthetic_profiles"] if r["profile_id"] == profile_id), None)
        if rep is None:
            raise KeyError("unknown demo business")
        view, source = owner_view(rep, fx["owner_fields"]), f"WS B fixture {pins.B_FIXTURE_CONTRACT} @ {pins.B_COMMIT}"
    else:
        try:
            out = pins.run_b({"profile_id": "SYN-A360-OWNER", "synthetic": True, "fields": fields or {}})
        except pins.Unavailable as ex:
            problem = input_problem(str(ex))
            if problem:
                raise problem from None
            raise
        if out.get("audience") != "owner" or out.get("policy") != "blocked" or out.get("_wording_violations"):
            raise Incompatible("B engine output is not the fail-closed owner view")
        view, source = owner_view(out, fx["owner_fields"]), f"WS B engine @ {pins.B_COMMIT} (live, your made-up answers)"
        rep = out
    view["rows"] = _apply_suppression(view["rows"])
    for r in view["rows"]:
        lab = (r.get("demo_scenario") or {}).get("source_label") or {}
        r["changed_pending_review"] = bool(changed and lab.get("obligation_id") in changed)
    view.update(source=source, demo_label=fx["demo_scenario_label"], banner_fixture=fx["banner"], data_as_of=fx["as_of"],
                snapshot=pins.SNAPSHOT_TEXT, snapshot_note=pins.SNAPSHOT_NOTE,
                pins={"b": pins.B_COMMIT, "b_fixture": pins.B_FIXTURE_CONTRACT, "b_validity": pins.B_VALIDITY_PIN,
                      "c": pins.C_COMMIT, "c_contract": pins.C_CONTRACT})
    scan(view)
    return (view, rep) if with_report else view       # the report is for the audit record only, never for the owner


def ct_journey(profile_id: str, with_report: bool = False):
    """The D-064 two-persona corporate-tax demo, exactly as B's fixture gives it (questions, documents, steps only)."""
    fx = fixture()
    rep = next((r for r in fx["ct_demo_personas"] if r["profile_id"] == profile_id), None)
    if rep is None:
        raise KeyError("corporate tax is shown only for the two fictional demo businesses")
    sup = suppressed()
    rows = [r for r in owner_view(rep, fx["owner_fields"])["rows"] if r.get("demo_scenario") and r["id"] not in sup]
    out = {"profile_id": profile_id, "label": fx["demo_scenario_label"], "rows": rows}
    return (out, rep) if with_report else out


BASIS = "Which income counts, and over which period: confirm with a tax agent (draft reading of stored texts, not reviewed)"


def finance() -> dict:
    """Financial-readiness checklist from synthetic transactions. Arithmetic only; no eligibility verdicts (D-062)."""
    f = content()["finance"]
    tx = f["transactions"]
    inc = [t for t in tx if t["type"] == "income"]
    exp = [t for t in tx if t["type"] == "expense"]
    missing = [t for t in tx if not t["has_document"]]
    unclassified = [t for t in tx if not t["category"]]
    total_in, total_out = sum(t["amount_aed"] for t in inc), sum(t["amount_aed"] for t in exp)
    check = [
        {"item": "Income records", "state": "ok" if inc else "missing", "note": f"{len(inc)} income lines this quarter"},
        {"item": "Sales invoices", "state": "gaps" if any(not t["has_document"] for t in inc) else "ok",
         "note": f"{sum(not t['has_document'] for t in inc)} income line(s) without an invoice"},
        {"item": "Expense records", "state": "ok" if exp else "missing", "note": f"{len(exp)} expense lines this quarter"},
        {"item": "Receipts", "state": "gaps" if any(not t["has_document"] for t in exp) else "ok",
         "note": f"{sum(not t['has_document'] for t in exp)} expense line(s) without a receipt"},
        {"item": "Bank records", "state": "needed", "note": "Bank statements for the quarter are needed to check every line"},
        {"item": "Unclear items", "state": "gaps" if unclassified else "ok", "note": f"{len(unclassified)} line(s) need a category — counted, not dropped"},
        {"item": "Draft money in minus money out", "state": "draft", "note": "A1 estimate below — not a profit-and-loss statement"},
    ]
    revenue_tests = [
        {"test": "VAT registration", "basis": BASIS,
         "this_sample": f"AED {total_in:,} in one quarter", "result": "Need more records: one quarter is not enough"},
        {"test": "Corporate tax — natural person", "basis": BASIS,
         "this_sample": f"AED {total_in:,} in one quarter", "result": "Need more records: one quarter is not enough"},
        {"test": "Small Business Relief", "basis": BASIS,
         "this_sample": f"AED {total_in:,} in one quarter", "result": "Need more records: one quarter is not enough"},
    ]
    return {"period": f["period"], "fx_note": f["fx_note"], "checklist": check, "transactions": tx,
            "pnl": {"income": total_in, "expenses": total_out, "result": total_in - total_out, "label_level": "A1",
                    "title": "Draft money in minus money out",
                    "label": "A1 estimate, cash basis: not a profit-and-loss statement, not financial statements and not a tax computation"},
            "missing_documents": [f"{t['date']} · {t['description']} · AED {t['amount_aed']:,} — {t['document']} missing" for t in missing],
            "revenue_tests": revenue_tests, "ladder": f["ladder"]}


def finance_csv() -> str:
    f = finance()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "type", "description", "amount_aed", "category", "document", "document_status", "label_level", "open_question"])
    for t in f["transactions"]:
        q = "" if t["category"] else "What is this item? (counted until classified)"
        if not t["has_document"]:
            q = (q + " " if q else "") + f"Attach the {t['document']}"
        w.writerow([t["date"], t["type"], t["description"], t["amount_aed"], t["category"] or "unclassified", t["document"],
                    "present" if t["has_document"] else "missing", "A2", q])
    w.writerow([])
    w.writerow(["draft_income_total", "", "", f["pnl"]["income"], "", "", "", "A1", "management estimate"])
    w.writerow(["draft_expense_total", "", "", f["pnl"]["expenses"], "", "", "", "A1", "management estimate"])
    w.writerow(["draft_result", "", "", f["pnl"]["result"], "", "", "", "A1", "management estimate; not financial statements"])
    return buf.getvalue()


def change_replay(as_of: str = pins.DEMO_AS_OF) -> dict:
    """Replay of WS C's REAL source-change evidence (SBR period extension). Report-only: nothing is activated."""
    if "step:7" in suppressed():
        raise KeyError("the rule-change demonstration is withheld while a newer source change is reviewed")
    imp = pins.c_file("docs/CL_evidence/ws_c/360/mvp/CL_sbr_amendment_impact_2026-10-17.json")
    c = pins.run_c(True, as_of)
    if c.get("contract") != pins.C_CONTRACT or imp.get("activation") != "not activated":
        raise Incompatible("WS C contract or change-impact evidence is not as pinned")
    for sid in ("CT-MD73-2023", "CT-MD131-2026"):
        s_ = c["sources"].get(sid) or {}
        if not s_.get("url") or not s_.get("retrieved_at"):
            raise Incompatible(f"WS C source {sid} has no official URL or retrieval date")
    affected = sorted(imp.get("affected_obligations", {}))
    events = [e for v in imp.get("affected_obligations", {}).values() for e in v]
    rows = [r["title"] for r in dashboard("SYN-AMAL-B", changed=set(affected))["rows"] if r["changed_pending_review"]]
    return {"activation": imp.get("activation"), "human_review_required": imp.get("human_review_required"),
            "affected_c": affected, "affected_titles": [c["obligations"].get(a, {}).get("title", a) for a in affected],
            "affected_rows": rows, "events": events,
            "sources": {sid: c["sources"].get(sid, {}) for sid in ("CT-MD73-2023", "CT-MD131-2026")},
            "evidence": f"ws-c-source-intelligence@{pins.C_COMMIT}:docs/CL_evidence/ws_c/360/mvp/CL_sbr_amendment_impact_2026-10-17.json"}
