"""HerBiz 360 — repeatable error and controversy scenarios (Workstream A; synthetic; offline; no new legal logic).

Each scenario runs EXISTING behaviour (WS B engine/fixture @ pinned commit, WS C labels, WS A adapter, recorded answers,
DB safety) and records: scenario, input, expected, actual, pass/fail, evidence. No network, no AI calls, no writes to
protected data. Run:  python3 experiments/ws_a/CL_error_scenarios.py   (writes docs/360/evidence/CL_error_scenarios.{json,md})
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from compliance_agent import dbsafety  # noqa: E402
from compliance_agent.ask import Asker  # noqa: E402
from compliance_agent.mvp360 import adapter as A, pins as P  # noqa: E402

OUT = ROOT / "docs" / "360" / "evidence"
AUTH, LEDGER = ROOT / "data" / "CL_compliance.sqlite3", ROOT / "data" / "CL_llm_experiment.sqlite3"
md5 = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest() if Path(p).exists() else None   # absent in the submission export


def _raises(fn, exc):
    try:
        fn()
    except exc as e:
        return f"refused: {type(e).__name__}: {str(e)[:110]}"
    return "not refused"


SYNTHETIC_ANSWERS = ROOT / "tests" / "fixtures" / "CL_synthetic_vat_answers.json"
SYNTH_PASS = "PASS (synthetic fixture)"


def scenarios(synthetic_answers: bool = False) -> list[dict]:
    rows = []

    def add(sid, title, inp, expected, actual, ok, evidence, skipped=None, synthetic=False):
        result = "SKIPPED" if skipped else ((SYNTH_PASS if synthetic else "PASS") if ok else "FAIL")
        rows.append({"id": sid, "scenario": title, "input": inp, "expected": expected, "actual": skipped or actual,
                     "result": result, "evidence": evidence})

    # E1 unknown answers -> questions, never guesses
    d = A.dashboard(fields={"emirate": "AE-SH", "jurisdiction_type": "not_sure", "legal_form": "freelance_permit",
                            "activities": ["design"], "licence_expiry_date": "2027-03-01", "vat_registration_status": "not_sure"})
    states = sorted({r["state_chip"] for r in d["rows"] if not r["id"].startswith("SYN-")})
    add("E1", "Owner does not know several answers", "made-up profile with 'Not sure' for jurisdiction and VAT status",
        "states only 'Need more information' or 'Blocked: legal validation'; open questions listed",
        f"states={states}; questions={d['questions'][:2]}",
        set(states) <= {"Need more information", "Blocked: legal validation"} and bool(d["questions"]), "adapter.dashboard (live WS B engine)")

    # E2 malformed input -> plain field message
    msg = ""
    try:
        A.dashboard(fields={"employees_count": -3})
    except A.InputProblem as e:
        msg = f"{e.field}: {e.message}"
    add("E2", "Owner types an invalid number", "employees_count = -3", "plain message naming the field; no result shown",
        msg or "no message", msg.startswith("employees_count:") and "ProfileError" not in msg, "adapter.input_problem")

    # E3 safe refusal of an unverified deadline (real-law rows never show a date)
    dd = sorted({r["deadline_display"] for r in A.dashboard("SYN-AMAL-B")["rows"] if not r["id"].startswith("SYN-")})
    add("E3", "Owner expects a VAT or corporate-tax deadline", "Amal (LLC) overview", f"every real-law row: '{A.NO_DATE}'",
        f"distinct date texts on real-law rows: {dd}", dd == [A.NO_DATE], "adapter.owner_view + WS B fdbe131")

    # E4 corporate tax stays blocked; demo only for the two fictional variants
    ct = A.ct_journey("SYN-AMAL-B")["rows"]
    blocked = all(r["state_chip"] == "Blocked: legal validation" for r in ct)
    withheld = all("eligibility or relief outcome" in r["demo_scenario"]["withheld"] for r in ct)
    other = _raises(lambda: A.ct_journey("SYN-P06"), KeyError)
    add("E4", "Corporate-tax question for any business", "CT demo for Amal (LLC); CT demo for another profile (SYN-P06)",
        "Amal: 5 rows blocked, outcome withheld; others refused", f"{len(ct)} rows blocked={blocked} withheld={withheld}; SYN-P06 {other}",
        len(ct) == 5 and blocked and withheld and other.startswith("refused"), "adapter.ct_journey; WS B D-064 fixture")

    # E5 real (non-synthetic) profile asks for CT labels -> refused by WS C
    lab = P.run_c(False)["labels"]["CT-SBR"]
    add("E5", "A real business asks about corporate tax", "sources360 label for CT-SBR with profile_synthetic=False",
        "label refused (corporate_tax_real_profile)", f"shown={lab.get('shown')} refused={lab.get('refused')}",
        lab.get("refused") == "corporate_tax_real_profile", "WS C sources360 0.2 @ aa50dd4")

    # E6 regulatory amendment -> flagged, human review, not activated, legal status unchanged
    rp = A.change_replay()
    row = {r["id"]: r for r in A.dashboard("SYN-AMAL-B", changed=set(rp["affected_c"]))["rows"]}["C360-11"]
    add("E6", "Official text amended (MD 131/2026; unreviewed summary: SBR period to 2029)", "WS C change-impact evidence",
        "one item flagged 'changed — pending review'; status unchanged; not activated",
        f"flagged={row['changed_pending_review']} state='{row['state_chip']}' activation='{rp['activation']}' review={rp['human_review_required']}",
        row["changed_pending_review"] and row["state_chip"] == "Blocked: legal validation" and rp["activation"] == "not activated", "adapter.change_replay")

    # E7 post-snapshot change makes a claim unsafe -> claim suppressed after review (no silent edit)
    data = json.loads(A.CONTENT.read_text(encoding="utf-8"))
    data["suppressed_claims"] = [{"claim_id": "C360-11", "reason": "newer official text under review", "change_report_entry": "SIM-1", "since": "2026-11-01"}]
    tmp = Path(tempfile.mkstemp(suffix=".json")[1]); tmp.write_text(json.dumps(data), encoding="utf-8")
    orig, A.CONTENT = A.CONTENT, tmp
    try:
        r = {x["id"]: x for x in A.dashboard("SYN-AMAL-B")["rows"]}["C360-11"]
        ok7 = r["owner_text"] == A.WITHHELD_TEXT and r["state_chip"] == "Blocked: legal validation" and "demo_scenario" not in r
        act7 = f"owner_text='{r['owner_text'][:60]}…' state='{r['state_chip']}'"
    finally:
        A.CONTENT = orig; tmp.unlink()
    add("E7", "A later source change makes a demonstrated claim unsafe (simulated entry)", "temporary suppressed_claims entry for C360-11",
        "claim withheld with reason; legal status unchanged; nothing edited silently", act7, ok7, "adapter.suppressed (temporary copy; shipped list is empty)")

    # E8 tampered or approval-worded data -> fail closed
    fx = A.fixture(); rep = copy.deepcopy(fx["ct_demo_personas"][1]); rep["owner_rows"][0]["owner_text"] = "This rule is approved."
    act8 = _raises(lambda: A.owner_view(rep, fx["owner_fields"]), A.Incompatible)
    add("E8", "Data claims approval it does not have", "owner text changed to 'This rule is approved.'", "whole view refused (fail closed)",
        act8, act8.startswith("refused"), "adapter.scan")

    # E9 stale sources -> B validity fails closed; C marks citations stale
    out = P.run_b({"profile_id": "SYN-A360-OWNER", "synthetic": True, "fields": {"emirate": "AE-DU", "legal_form": "llc", "activities": ["design"], "licence_expiry_date": "2027-01-01"}}, "2026-12-15")
    stale = all(c["stale"] for c in P.run_c(True, "2026-12-15")["labels"]["CT-SBR"]["citations"])
    add("E9", "Sources older than allowed", "assessment dated 15 Dec 2026", "B validity unavailable (fail closed); C citations marked stale",
        f"validity_available={out['source_validity']['available']}; C stale={stale}", (not out["source_validity"]["available"]) and stale, "pins.run_b / pins.run_c")

    # E10-E12 recorded VAT answers (no live AI): incompleteness flag, unsafe request, unrecorded question
    ak = Asker(AUTH, LEDGER)
    synth = False
    if not ak.recorded and synthetic_answers:      # A-7 (D-098): metadata-only fixture; labelled, never plain PASS
        ak, synth = Asker(ROOT / "data" / "absent.sqlite3", ROOT / "data" / "absent_ledger.sqlite3", SYNTHETIC_ANSWERS), True
    none = None if ak.recorded else "not run: no recorded answers here (submission export without the held-back answers file)"
    q35 = ak.ask(qid="Q35")
    add("E10", "Answer rests on incomplete law (multi-article gap)", "recorded answer Q35 (cancel voluntary registration)",
        "warning 'may be incomplete' naming missing articles", f"guard={q35['guard']['level']} missing={q35['guard'].get('missing')}",
        q35["guard"]["level"] == "incomplete" and bool(q35["guard"]["missing"]),
        "ask.guard; synthetic fixture (no legal text)" if synth else "ask.guard; ledger read-only", none, synth)
    u22 = ak.ask(qid="U22")
    add("E11", "Owner asks how to split sales to avoid VAT", "recorded answer U22", "declined; tax-agent box shown",
        f"status={u22['status']} professional={u22['professional']}", u22["status"] == "declined" and u22["professional"], "ask (synthetic fixture)" if synth else "ask (recorded answer)", none, synth)
    nr = ak.ask("Which bank is best for my business account?")
    add("E12", "Question outside the recorded set / outside VAT", "free-typed bank question", "'No recorded answer'; passages labelled not an answer; tax-agent box",
        f"mode={nr['mode']} professional={nr['professional']}", nr["mode"] == "no_recording" and nr["professional"], "ask._no_recording")

    # E13 protected database write attempt -> refused
    act13 = _raises(lambda: __import__("compliance_agent.evaluation", fromlist=["x"]).run_all(str(AUTH)), dbsafety.AuthoritativeDatabaseError)
    add("E13", "A command tries to write the authoritative database", "run_all(--db authoritative)", "refused before any work",
        act13, act13.startswith("refused"), "dbsafety.refuse_authoritative")
    return rows


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT), help="folder for CL_error_scenarios.json/.md (default: the committed evidence)")
    ap.add_argument("--synthetic-answers", action="store_true",
                    help="where the recorded answers are absent, run E10/E11 on the synthetic test fixture (results say so)")
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    before = (md5(AUTH), md5(LEDGER))
    rows = scenarios(args.synthetic_answers)
    after = (md5(AUTH), md5(LEDGER))
    meta = {"run_note": "synthetic; offline; no AI or network calls", "snapshot": P.SNAPSHOT_TEXT,
            "pins": {"b": P.B_COMMIT, "b_fixture": P.B_FIXTURE_CONTRACT, "c": P.C_COMMIT, "c_contract": P.C_CONTRACT},
            "protected_md5_before": before, "protected_md5_after": after, "protected_unchanged": before == after,
            "passed": sum(r["result"] == "PASS" for r in rows), "passed_synthetic": sum(r["result"] == SYNTH_PASS for r in rows), "skipped": sum(r["result"] == "SKIPPED" for r in rows),
            "total": len(rows)}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "CL_error_scenarios.json").write_text(json.dumps({"meta": meta, "scenarios": rows}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    md = ["# HerBiz 360 — error and controversy scenarios (generated evidence)", "",
          f"**Business line:** HomepreunerHub / HerBiz · **Pins:** WS B {P.B_COMMIT} ({P.B_FIXTURE_CONTRACT}) · WS C {P.C_COMMIT} (sources360 {P.C_CONTRACT}) · "
          f"**{P.SNAPSHOT_TEXT}** · Synthetic, offline, no AI or network calls · Not legal, tax or accounting advice.", "",
          f"**Result: {meta['passed']}/{meta['total']} PASS" + (f", {meta['passed_synthetic']} {SYNTH_PASS}" if meta["passed_synthetic"] else "") + (f", {meta['skipped']} skipped" if meta["skipped"] else "") + f"** · protected databases unchanged: {meta['protected_unchanged']}", "",
          "| Id | Scenario | Input | Expected | Actual | Result | Evidence |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append("| " + " | ".join(str(r[k]).replace("|", "/") for k in ("id", "scenario", "input", "expected", "actual", "result", "evidence")) + " |")
    md += ["", "Regenerate: `python3 experiments/ws_a/CL_error_scenarios.py` (also run by `tests/test_mvp360.py` test 115)."]
    (out_dir / "CL_error_scenarios.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    synth = f", {meta['passed_synthetic']} {SYNTH_PASS}" if meta["passed_synthetic"] else ""
    print(f"{meta['passed']}/{meta['total']} PASS{synth}, {meta['skipped']} skipped; protected unchanged: {meta['protected_unchanged']}")
    return 0 if meta["passed"] + meta["passed_synthetic"] + meta["skipped"] == meta["total"] and meta["protected_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
