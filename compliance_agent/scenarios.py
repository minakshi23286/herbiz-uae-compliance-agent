"""Error-scenario runner SC-1, SC-2, SC-3 (Task 2 A-2, doc 16 r2 §5; contract herbiz.scenario/1.0, G1-frozen).

Events are released ONE AT A TIME: a run starts with nothing released; each `next()` releases the next step (its
`released_after` must equal the number already released), produces HerBiz's response, checks it against the step's expected
state, flags, must_show and must_not, and returns the result for the caller to audit (channel "scenario").

Data: the G1 golden fixtures (contracts/fixtures/scenario.valid_SC-n.json and the source_validity fixtures), all synthetic.
SC-1 runs through WS B's pinned engine on WS B's delivered SC-1 data (A-4; obligation C360-03). SC-2 and SC-3 use the
source-validity payloads by key. An expected state for a placeholder obligation (SYN-OB-…) is still reported as
PENDING_DATA, never as PASS. HerBiz explains conflicts but never resolves them, never gives a deadline it cannot stand
behind, and never fetches a link.

    python3 -m compliance_agent.scenarios replay SC-2 [--audit-dir DIR]     # all steps, one command; exit 1 on any FAIL
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import uuid
from pathlib import Path

from . import audit_records as AR
from .mvp360 import adapter as A

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "contracts" / "fixtures"
NO_DATE = A.NO_DATE if hasattr(A, "NO_DATE") else "No date is shown until a qualified reviewer has checked the rule and its sources."
TAX_AGENT = "an FTA-registered tax agent"


def _contract_errors(schema_name: str, payload) -> list[str]:
    sys.path.insert(0, str(ROOT / "contracts")) if str(ROOT / "contracts") not in sys.path else None
    import validate as V
    schema = json.loads((ROOT / "contracts" / schema_name).read_text(encoding="utf-8"))
    return V.errors(schema, payload)


# A-4 (D-101 condition 6): SC-1 runs on WS B's delivered scenario data (t2-b-rc1, engine obligation C360-03) instead of the
# golden placeholder. Same frozen contract; WS B's copy adds must_not "deadline" to every step. Pinned by sha256: a changed
# file is refused, never silently used.
DELIVERED = {"SC-1": (ROOT / "fixtures" / "t2" / "CL_SC-1_decision.json", "6b4ac7ab825d7d73bd6423c3627771d955a0290416d3352ff510b3d6680cd64e")}


def load(scenario_id: str) -> dict:
    path = FX / f"scenario.valid_{scenario_id}.json"
    if scenario_id in DELIVERED:
        path, pin = DELIVERED[scenario_id]
        if hashlib.sha256(path.read_bytes()).hexdigest() != pin:
            raise ValueError(f"scenario {scenario_id} data differs from the pinned WS B delivery")
    s = json.loads(path.read_text(encoding="utf-8"))
    errs = _contract_errors("scenario_1.0.schema.json", s)
    if errs:
        raise ValueError(f"scenario {scenario_id} does not validate: {errs[:2]}")
    return s


def validity(key: str) -> dict:
    for p in sorted(FX.glob("source_validity.valid_*.json")):
        v = json.loads(p.read_text(encoding="utf-8"))
        if v["key"] == key:
            return v
    raise KeyError(f"no source-validity payload for {key}")


def list_scenarios() -> list[dict]:
    return [{"scenario_id": s, "title": load(s)["title"], "steps": len(load(s)["steps"])} for s in ("SC-1", "SC-2", "SC-3")]


def _what_you_can_do_now(row: dict) -> str:
    parts = []
    if (row.get("documents") or {}).get("missing"):
        parts.append("gather the documents listed")
    if row.get("missing_information"):
        parts.append("answer the open questions")
    parts.append(f"then ask {TAX_AGENT} about this item")
    return "What you can do now: " + ", ".join(parts) + "."


# ------------------------------------------------------------------------------------------------ predicates
def _pred(name: str, resp: dict, run: "Run"):
    """True / False, or None when the check needs data that is not there yet. Unknown names fail (never pass silently)."""
    ob = resp.get("obligation") or {}
    table = {
        "questions": lambda: bool(resp.get("questions")),
        "fewer questions": lambda: (run.prev_questions is not None and len(resp.get("questions") or []) < run.prev_questions),
        "what you can do now": lambda: (None if not ob else bool(resp.get("what_you_can_do_now"))),
        "both values with sources": lambda: len(resp.get("values") or []) >= 2 and all(v.get("source_id") and v.get("url") for v in resp["values"]),
        "no precedence rule known": lambda: resp.get("precedence_known") is False,
        "FTA-registered tax agent": lambda: "FTA-registered tax agent" in (resp.get("message") or "") or resp.get("escalate_to") == TAX_AGENT,
        "current official link": lambda: str(resp.get("current_official_url") or "").startswith("https://"),
        "link not yet verified": lambda: resp.get("content_check") == "pending_founder_verification" and "not been checked" in (resp.get("message") or ""),
        "review required": lambda: resp.get("review_required") is True,
    }
    not_table = {
        "deadline": lambda: resp.get("deadline") is None and (not ob or ob.get("deadline_display") in (None, NO_DATE)),
        "resolved": lambda: resp.get("precedence_known") is False and resp.get("resolution") in (None, "escalate"),
        "answer for the affected article": lambda: resp.get("answer") is None,
        "fetched": lambda: resp.get("link_fetched") is False,
    }
    return table, not_table


def check(step: dict, resp: dict, flags: list[str], run: "Run") -> dict:
    exp, details, pending = step["expected"], [], False
    placeholder = str(step["input"].get("obligation_id", "")).startswith("SYN-OB") and not resp.get("obligation")
    ok = sorted(flags) == sorted(exp["flags"])
    if not ok and placeholder:                  # obligation-dependent flags cannot be judged before WS B's data (A-4)
        ok = None; pending = True
    details.append({"check": "flags", "expected": exp["flags"], "actual": sorted(flags), "ok": ok,
                    **({"note": "depends on the placeholder obligation"} if ok is None else {})})
    table, not_table = _pred("", resp, run)
    for name in exp["must_show"]:
        f = table.get(name)
        r = f() if f else False
        details.append({"check": f"must_show: {name}", "ok": r}); pending |= r is None
    for name in exp["must_not"]:
        f = not_table.get(name)
        r = f() if f else False
        details.append({"check": f"must_not: {name}", "ok": r}); pending |= r is None
    if exp["state"] is not None:
        oid = step["input"].get("obligation_id")
        actual = (resp.get("obligation") or {}).get("state")
        if actual is None and str(oid).startswith("SYN-OB"):
            details.append({"check": "state", "expected": exp["state"], "actual": None, "ok": None,
                            "note": f"placeholder obligation {oid}: WS B scenario data arrives at A-4"})
            pending = True
        else:
            details.append({"check": "state", "expected": exp["state"], "actual": actual, "ok": actual == exp["state"]})
    failed = any(d["ok"] is False for d in details)
    return {"result": "FAIL" if failed else ("PENDING_DATA" if pending else "PASS"), "details": details}


# ------------------------------------------------------------------------------------------------ runs
class Run:
    def __init__(self, scenario_id: str):
        self.run_id = "run-" + uuid.uuid4().hex[:12]
        self.scenario = load(scenario_id)
        self.sid = scenario_id
        self.released = 0
        self.fields: dict = {}
        self.prev_questions = None
        self.validity = None
        self.results: list[dict] = []

    @property
    def done(self) -> bool:
        return self.released >= len(self.scenario["steps"])

    def next(self) -> dict:
        """Release the next event and return {n, event, response, flags, check, decisions, sources}."""
        if self.done:
            raise IndexError("all events of this scenario have been released")
        step = self.scenario["steps"][self.released]
        if (step["released_after"] or 0) != self.released:
            raise ValueError("events must be released in order")
        resp, flags, decisions, sources = getattr(self, "_" + self.sid.replace("-", "").lower())(step)
        result = check(step, resp, flags, self)
        if "questions" in resp:
            self.prev_questions = len(resp["questions"])
        self.released += 1
        out = {"run_id": self.run_id, "scenario_id": self.sid, "n": step["n"], "event": step["event"], "synthetic": True,
               "response": resp, "flags": sorted(flags), "check": result, "steps_total": len(self.scenario["steps"]),
               "done": self.done}
        self.results.append(out)
        return {**out, "_decisions": decisions, "_sources": sources}

    # SC-1 missing information: the profile grows step by step through WS B's pinned engine
    def _sc1(self, step):
        self.fields.update({k: v for k, v in step["input"].items() if k not in ("obligation_id", "profile_id")})
        view, rep = A.dashboard(fields=self.fields, with_report=True)
        oid = step["input"].get("obligation_id")
        row = next((r for r in view["rows"] if r["id"] == oid), None)
        ob = next((o for o in rep["obligations"] if o["id"] == oid), None)
        obligation = None if row is None else {"id": oid, "title": row["title"], "state": ob["state"] if ob else None,
                                              "state_chip": row["state_chip"], "deadline_display": row.get("deadline_display"),
                                              "owner_text": row.get("owner_text")}
        resp = {"kind": "profile_overview", "questions": view["questions"], "obligation": obligation,
                "what_you_can_do_now": _what_you_can_do_now(row) if row and str(ob and ob["state"]).startswith(("blocked", "insufficient")) else None}
        flags = ["blocked_legal_validation"] if ob and str(ob["state"]).startswith("blocked") else []
        decisions = [AR.decision(ob, "simulated")] if ob else []
        return resp, flags, decisions, []

    # SC-2 conflicting rules: HerBiz states both values with their sources, knows no precedence, gives no deadline
    def _sc2(self, step):
        return self._source_step(step, self._sc2_answer)

    def _sc2_answer(self, v):
        values = [{"value": x["value"], "source_id": x["source_id"], "url": x["url"], "locator": x["locator"]}
                  for c in v["conflicts"] for x in c["values"]]
        listed = "; ".join(f"{x['value']} ({x['source_id']}, {x['locator']})" for x in values)
        msg = (f"Two official sources give different values for this: {listed}. HerBiz knows no rule that says which one "
               "applies (the English texts are translations, and the Arabic text prevails), so HerBiz gives no deadline. "
               f"Please ask {TAX_AGENT} before you act.")
        return {"kind": "conflict_explained", "values": values, "precedence_known": False, "resolution": "escalate",
                "deadline": None, "message": msg, "escalate_to": TAX_AGENT}, ["conflict"]

    # SC-3 outdated source: answer withheld, current official link shown (never fetched), review required
    def _sc3(self, step):
        return self._source_step(step, self._sc3_answer)

    def _sc3_answer(self, v):
        st = v.get("current_official_url_status") or {}
        am = (v.get("amendments") or [{}])[0]
        msg = (f"HerBiz has withheld the answer for {v['key'].replace('|', ', Article ')}: the stored copy is older than an "
               f"amendment ({am.get('instrument', 'an amending instrument')}, effective {am.get('effective_date') or 'date not known'}). "
               "The current official text is listed below, but HerBiz has not fetched it and its content has not been checked "
               "by a person yet. Review required.")
        flags = ["stale_source"] + (["pending_unverified_link"] if st.get("content_check") == "pending_founder_verification" else [])
        return {"kind": "answer_withheld", "answer": None, "affected": v["key"], "current_official_url": v["current_official_url"],
                "link_status": st.get("link_status"), "content_check": st.get("content_check"), "link_fetched": False,
                "review_required": True, "message": msg, "deadline": None}, flags

    def _source_step(self, step, answer):
        ev, inp = step["event"], step["input"]
        if "validity_key" in inp:
            self.validity = validity(inp["validity_key"])
            v = self.validity
            flags = {"conflict": ["conflict"], "outdated": ["stale_source"], "superseded": ["stale_source"]}.get(v["status"], [])
            resp = {"kind": "validity", "key": v["key"], "status": v["status"], "review_status": v["review_status"]}
            return resp, flags, [], self._sources(v)
        if ev == "owner_question":
            return {"kind": "question_received", "question_id": inp.get("question_id"), "status": "checking the sources"}, [], [], []
        resp, flags = answer(self.validity)
        return resp, flags, [], self._sources(self.validity)

    @staticmethod
    def _sources(v) -> list[dict]:
        src, _, art = v["key"].partition("|")
        e = AR.source_entry(src, None if art == "*" else art)
        if e:
            e["validity"] = v                      # the full source_validity/1.2 payload (I-6)
        return [e] if e else []


def record_for(run_out: dict, session_id: str, shown: bytes) -> dict:
    """herbiz.audit_record/1.0 for one released scenario step (channel "scenario")."""
    decs = run_out.get("_decisions") or []
    rec = AR.base("scenario", session_id, "SYN-SC1" if run_out["scenario_id"] == "SC-1" else None,
                  AR.plain_request(f"scenario:{run_out['scenario_id']}:step{run_out['n']}"))
    level_basis = ["simulated_data"] + [b for d in decs for b in d["confidence"]["basis"]]
    rec.update(decisions=decs, sources=run_out.get("_sources") or [],
               answer={"mode": "scenario", "execution_mode": "simulated", "status": run_out["check"]["result"],
                       "shown_text_sha256": AR.sha(shown), "flags": sorted(set(run_out["flags"]))},
               confidence={"level": "low", "basis": sorted(set(level_basis)), "numeric": None},
               review={"release_approved": False, "human_review_required": True, "reviewer_needed": TAX_AGENT})
    return rec


def public(run_out: dict) -> dict:
    return {k: v for k, v in run_out.items() if not k.startswith("_")}


def replay(scenario_id: str, audit_dir: Path | None = None, session_id: str = "cli-replay") -> tuple[list[dict], Path]:
    from .audit_log import AuditLog
    folder = Path(audit_dir) if audit_dir else Path(tempfile.mkdtemp(prefix="herbiz-scenario-audit-"))
    log = AuditLog(folder)
    run, outs = Run(scenario_id), []
    while not run.done:
        o = run.next()
        body = json.dumps(public(o), ensure_ascii=False, default=str).encode("utf-8")
        rec = record_for(o, session_id, body)
        log.write(rec)
        outs.append({**public(o), "record_id": rec["record_id"]})
    return outs, folder


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m compliance_agent.scenarios")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay")
    r.add_argument("scenario_id", choices=["SC-1", "SC-2", "SC-3"])
    r.add_argument("--audit-dir", default=None)
    a = ap.parse_args(argv)
    outs, folder = replay(a.scenario_id, a.audit_dir)
    from . import audit_log as AL
    for o in outs:
        print(f"{o['scenario_id']} step {o['n']} {o['event']}: {o['check']['result']}  flags={o['flags']}  record={o['record_id']}")
        for d in o["check"]["details"]:
            if d["ok"] is not True:
                print(f"    {d['check']}: {'PENDING' if d['ok'] is None else 'FAIL'} {d.get('note', '')}")
    for f in sorted(folder.glob("audit-*.jsonl")):
        print(f"audit: {AL.verify(f)[1]} ({f})")
    worst = [o["check"]["result"] for o in outs]
    print("RESULT:", "FAIL" if "FAIL" in worst else ("PASS with PENDING_DATA" if "PENDING_DATA" in worst else "PASS"))
    return 1 if "FAIL" in worst else 0


if __name__ == "__main__":
    sys.exit(main())
