"""HerBiz 360 obligations engine (Workstream B): applicability-first, configurable, deterministic. No model calls.

Rule catalogues are data (catalogue/*.json). Rules are evaluated with the existing three-valued evaluator of the app
engine (compliance_agent.engine.Engine._eval, reused unchanged through a subclass). One function, `resolve_state`, turns
a rule result into one of five states:

  applicable · not_applicable · potentially_applicable · insufficient_information · blocked_pending_legal_validation

Safety rules (board findings A1-A4, founder decision D-061):
  - "applicable" / "not_applicable" only for (a) clearly labelled synthetic TEST RULES, or (b) a reviewed rule whose
    provisions WS-C certifies (contract v1.1 answer_label). Today no rule is reviewed and no source is approved.
  - draft rules over real law: policy "blocked" (default, ai-mins) -> blocked_pending_legal_validation;
    policy "potential" (tech-sonu) -> potentially_applicable when the draft rule is met, otherwise blocked.
  - no reviewed rule (all corporate tax) -> blocked_pending_legal_validation + the facts a rule would need.
  - missing facts -> insufficient_information with the owner questions (no guessing).
  - deadlines are COMPUTED only for test rules (or reviewed + certified rules); otherwise the draft basis is shown.
  - unavailable or stale source-validity data fails closed.
"""
from __future__ import annotations

import calendar
import datetime as dt
import json
from pathlib import Path

from ..engine import Engine
from . import profile as PR

CATALOGUE_DIR = Path(__file__).parent / "catalogue"
STATES = ("applicable", "not_applicable", "potentially_applicable", "insufficient_information", "blocked_pending_legal_validation")
POLICIES = ("blocked", "potential")
DEFAULT_POLICY = "blocked"   # founder decision D-062: fail closed for every unreviewed legal rule
OWNER_POLICIES = ("blocked",)   # "potential" is a reviewer preview only; never shown to owners or in the owner demo
REVIEWER_BANNER = "REVIEWER PREVIEW — not for business owners. Draft rules shown as 'may apply' for review only. "
RULE_STATUSES = ("draft_unreviewed", "reviewed", "no_reviewed_rule", "blocked_source_conflict", "synthetic_test")
LOCKED_DOMAINS = ("corporate_tax",)   # D-061: no substantive CT decision from unreviewed rules, whatever the catalogue says
BANNER = "Draft — synthetic prototype, not reviewed by a qualified professional. Not legal, tax or accounting advice. HerBiz does not file or pay anything."
FORBIDDEN = ("you must", "you are compliant", "you are exempt", "certified", "guaranteed", "definitely")
STATE_TEXT = {
    "applicable": "This applies to your synthetic test profile (TEST RULE).",
    "not_applicable": "This does not apply to your synthetic test profile (TEST RULE).",
    "potentially_applicable": "Based on what you told us, this may apply. The rule is a draft that no qualified reviewer has checked.",
    "insufficient_information": "HerBiz needs more information before it can say whether this may apply.",
    "blocked_pending_legal_validation": "HerBiz can't answer this yet: the rule or its official sources have not been validated by a qualified reviewer.",
}
CHECK = "Check with an FTA-registered tax agent before acting."
STATE_CHIP = {"applicable": "Applies (TEST RULE)", "not_applicable": "Does not apply (TEST RULE)",
              "potentially_applicable": "May apply (draft, not checked)", "insufficient_information": "Need more information",
              "blocked_pending_legal_validation": "Blocked: legal validation"}
ALREADY_DONE_CHIP = "Owner says done — not checked"
NO_DATE = "No date is shown until a qualified reviewer has checked the rule and its sources."
TEST_DATE_PREFIX = "TEST RULE date (made up): "
# the only fields an owner screen may show (legal-kalpu review, D-064); everything else is for reviewers and developers
OWNER_FIELDS = ("id", "title", "meaning", "state_chip", "owner_text", "label", "missing_information", "documents", "deadline_display")
DERIVED = {"days_until_licence_expiry": "licence_expiry_date", "vat_registered": "vat_registration_status"}   # ask the source field


class _Evaluator(Engine):
    """Reuses Engine._eval unchanged; adds intervals (revenue bands) and lt/lte. No store, no writes."""

    def __init__(self):   # deliberately no database
        pass

    def _eval(self, node, facts, params):
        if "op" in node and node.get("op") in ("gt", "gte", "lt", "lte") and "fact" in node:
            val = facts.get(node["fact"])
            target = params[node["param"]] if "param" in node else node.get("value")
            label = node.get("label") or node["fact"]
            if val is None:
                return None, [node["fact"]], [f"{label}: unknown"]
            if not (isinstance(val, tuple) or (isinstance(val, (int, float)) and not isinstance(val, bool))):
                return None, [node["fact"]], [f"{label}: not a number"]
            lo, hi = (val if isinstance(val, tuple) else (val, val))
            op = node["op"]
            if op in ("gt", "gte"):
                yes = lo > target if op == "gt" else lo >= target
                no = hi <= target if op == "gt" else hi < target
            else:
                yes = hi < target if op == "lt" else hi <= target
                no = lo >= target if op == "lt" else lo > target
            res = True if yes else (False if no else None)
            shown = (f"{lo:,.0f} or more (band)" if hi == float("inf") else f"{lo:,.0f}–{hi:,.0f} (band)") if isinstance(val, tuple) else (f"{val:,.0f}" if isinstance(val, (int, float)) else val)
            if res is None:
                return None, [f"{node['fact']} (exact amount; the band straddles {target:,})"], [f"{label}: {shown} vs {target:,} -> undecided"]
            return res, [], [f"{label}: {shown} {op} {target:,} -> {'met' if res else 'not met'}"]
        if "fact" in node and isinstance(facts.get(node["fact"]), tuple):
            return None, [node["fact"]], [f"{node.get('label') or node['fact']}: only a band is known"]   # never compare a band with eq/in
        return super()._eval(node, facts, params)


_EV = _Evaluator()


def load_catalogues(names=("vat", "ct", "synthetic_test")) -> list[dict]:
    out = []
    for n in names:
        out += json.loads((CATALOGUE_DIR / f"{n}.json").read_text(encoding="utf-8"))["obligations"]
    return out


def _source_status(ob: dict, sv) -> dict:
    """WS-C label for the obligation's real provisions (fail closed). Synthetic rules have no sources."""
    provs = ob.get("provisions") or []
    if not provs:
        return {"checked": False, "certified": False, "reason": "no collected official provisions" if ob.get("source_candidates") else "synthetic test rule"}
    tuples = []
    for k in provs:
        if "|" not in k:
            return {"checked": False, "certified": False, "reason": f"malformed provision id {k!r}"}
        src, art = k.split("|", 1)
        tuples.append((src, f"Article {art}", sv.current_version(src) if sv else None))
    lab = sv.label("complete", tuples) if sv else {"certified": False, "blockers": [{"reason": "validity_unavailable"}], "validity_issue_kinds": []}
    return {"checked": True, "certified": bool(lab.get("certified")), "issue_kinds": lab.get("validity_issue_kinds", []),
            "blockers": sorted({b.get("reason") for b in lab.get("blockers", [])}), "wording": lab.get("user_wording")}


def resolve_state(rule_status: str, rule_result, source: dict, policy: str = DEFAULT_POLICY, domain: str | None = None,
                  ob_id: str = "") -> tuple[str, str]:
    """The ONE place that decides the state. Returns (state, reason). Code-level guards do not trust catalogue data."""
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}")
    if rule_status not in RULE_STATUSES:
        raise ValueError(f"unknown rule_status {rule_status!r}")
    if domain in LOCKED_DOMAINS:
        return "blocked_pending_legal_validation", "no reviewed rule"
    if rule_status == "synthetic_test" and not (domain == "synthetic_test" and ob_id.startswith("SYN-")):
        raise ValueError(f"{ob_id}: synthetic_test is allowed only for domain synthetic_test with a SYN- id")
    if rule_status in ("no_reviewed_rule", "blocked_source_conflict"):
        return "blocked_pending_legal_validation", "no reviewed rule" if rule_status == "no_reviewed_rule" else "official sources conflict"
    if rule_result is None:
        return "insufficient_information", "facts missing"
    if rule_status == "synthetic_test":
        return ("applicable" if rule_result else "not_applicable"), "synthetic TEST RULE"
    if rule_status == "reviewed" and source.get("certified"):
        return ("applicable" if rule_result else "not_applicable"), "reviewed rule, certified sources"
    # draft or reviewed-but-uncertified rule over real law
    if policy == "potential" and rule_result is True:
        return "potentially_applicable", "draft rule met; sources or rule not checked by a reviewer"
    return "blocked_pending_legal_validation", "rule or sources not checked by a reviewer"


def _add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod(d.month - 1 + months, 12)
    y += d.year
    m += 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def deadline(ob: dict, state: str, facts: dict, as_of: dt.date) -> dict:
    d = ob.get("deadline") or {"kind": "none", "basis": "No deadline recorded."}
    computable = state == "applicable"   # only test rules or reviewed + certified rules reach "applicable"
    out = {"kind": d["kind"], "basis": d["basis"], "computed": False, "due_date": None, "prepare_from": None, "overdue": None}
    if not computable or d["kind"] in ("none", "draft_text", "blocked"):
        if state in ("blocked_pending_legal_validation", "insufficient_information") and d["kind"] != "none":
            out["basis"] = NO_DATE
            out["draft_basis_for_reviewer"] = d["basis"]
        elif d["kind"] == "draft_text":
            out["basis"] = d["basis"] + " Shown as text only; not a computed date."
        return out
    if d["kind"] == "offset_from_fact":
        v = facts.get(d["fact"])
        if v is None:
            out["basis"] += f" Date unknown until '{d['fact']}' is supplied."
            return out
        due = dt.date.fromisoformat(v) + dt.timedelta(days=d.get("days", 0))
        out.update(computed=True, due_date=due.isoformat(),
                   prepare_from=(due - dt.timedelta(days=d.get("prepare_days_before", 0))).isoformat(),
                   overdue=due < as_of)
    elif d["kind"] == "monthly_day":
        nxt = as_of.replace(day=min(d["day"], calendar.monthrange(as_of.year, as_of.month)[1]))
        if nxt < as_of:
            nxt = _add_months(nxt, 1)
        out.update(computed=True, due_date=nxt.isoformat(), prepare_from=None, overdue=False)
    return out


def documents(ob: dict, state: str, facts: dict) -> dict:
    req = ob.get("documents") or []
    have = set(facts.get("documents_available") or [])
    if state == "not_applicable":
        return {"required": [], "ready": [], "missing": [], "readiness": None}
    ready = [d for d in req if d["id"] in have]
    missing = [d for d in req if d["id"] not in have]
    return {"required": req, "ready": ready, "missing": missing,
            "readiness": round(len(ready) / len(req), 2) if req else None, "draft_list": ob["domain"] != "synthetic_test"}


def assess(profile: dict, sv=None, as_of: dt.date | None = None, policy: str = DEFAULT_POLICY, catalogue: list[dict] | None = None) -> dict:
    """Evaluate every obligation for one synthetic profile. Pure function: no writes, no network, no model."""
    as_of = as_of or dt.date.today()
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}")
    v = PR.validate(profile)
    facts = PR.evaluator_facts(v["facts"], as_of)
    results = []
    for ob in catalogue or load_catalogues():
        lines, missing, rule_result = [], [], None
        if ob.get("skip_if") is not None and ob["domain"] not in LOCKED_DOMAINS:
            sk, _, _ = _EV._eval(ob["skip_if"], facts, ob.get("params", {}))
            if sk is True:
                # a fact the owner gave (e.g. already registered), not a legal judgement: the step is satisfied
                results.append(_result(ob, "not_applicable", "already done according to your answer (no legal judgement made)",
                                       ["already done (per your profile)"], [], facts, as_of,
                                       {"checked": False, "certified": False, "reason": "satisfied by the owner's answer"}, already_done=True))
                continue
        if ob.get("rule") is not None and ob["domain"] not in LOCKED_DOMAINS:
            rule_result, missing, lines = _EV._eval(ob["rule"], facts, ob.get("params", {}))
            missing = list(dict.fromkeys(DERIVED.get(m, m) for m in missing))
        else:
            missing = [f for f in ob.get("facts_needed", []) if f not in v["facts"]]
        src = _source_status(ob, sv)
        state, reason = resolve_state(ob["rule_status"], rule_result, src, policy, ob["domain"], ob["id"])
        if state == "insufficient_information" and ob["rule_status"] != "synthetic_test":
            reason += "; even when answered, the result stays a draft until a reviewer has checked the rule and sources"
        results.append(_result(ob, state, reason, lines, missing, facts, as_of, src, draft_indication=rule_result))
    summary = {s: sum(1 for r in results if r["state"] == s) for s in STATES}
    return {"profile_id": profile["profile_id"], "as_of": as_of.isoformat(), "policy": policy,
            "audience": "owner" if policy in OWNER_POLICIES else "reviewer_only",
            "banner": BANNER if policy in OWNER_POLICIES else REVIEWER_BANNER + BANNER,
            "profile_gaps": {"missing_required": v["missing_required"], "clarify": v["clarify"], "unknown": v["unknown"],
                             "questions": {f: PR.question(f) for f in v["missing_required"] + v["clarify"]}},
            "source_validity": {"available": bool(sv and sv.available), "origin": getattr(sv, "origin", None), "error": getattr(sv, "error", None)},
            "summary": summary, "obligations": results}


def _result(ob, state, reason, lines, missing, facts, as_of, src, draft_indication=None, already_done=False) -> dict:
    owner_text = STATE_TEXT[state] + ("" if ob["rule_status"] == "synthetic_test" else " " + CHECK)
    if already_done:
        owner_text = "Your profile says this is already done. " + CHECK
    dl = deadline(ob, state, facts, as_of)
    if dl.get("overdue"):
        owner_text += " The test date has passed."
    # a blocked draft result is never shown to the owner as an answer; the trace stays for reviewers only
    hide = state == "blocked_pending_legal_validation"
    trace, lines = lines, ([] if hide else [("Draft check: " + l) if ob["rule_status"] != "synthetic_test" else l for l in lines])
    if hide:
        draft_indication = None
    return {"id": ob["id"], "domain": ob["domain"], "title": ob["title"], "meaning": ob["meaning"], "state": state, "reason": reason,
            "rule_status": ob["rule_status"], "draft_indication": None if draft_indication is None else ("may apply" if draft_indication else "may not apply"),
            "why": lines, "reviewer_trace": trace, "missing_information": [{"fact": m, "question": PR.question(m.split(" ")[0])} for m in missing],
            "sources": {"provisions": ob.get("provisions", []), "source_candidates": ob.get("source_candidates", []), "validity": src},
            "deadline": dl, "documents": documents(ob, state, facts),
            "owner_actions": ob.get("owner_actions", []), "professional_review": ob.get("professional_review", []),
            "already_done": already_done, "state_chip": ALREADY_DONE_CHIP if already_done else STATE_CHIP[state],
            "owner_text": owner_text, "label": "TEST RULE — not law" if ob["rule_status"] == "synthetic_test" else "Draft — not reviewed"}


def owner_row(r: dict) -> dict:
    """Projection of one result to the fields an owner screen may show. No reasons, traces, validity internals."""
    dl = r["deadline"]
    row = {k: r[k] for k in OWNER_FIELDS if k in r}
    row["documents"] = {"ready": [d["label"] for d in r["documents"]["ready"]], "missing": [d["label"] for d in r["documents"]["missing"]]}
    # WS-A defect report / legal-kalpu S1, S3 (founder-approved fix after D-066): a real-law row never shows a draft
    # deadline reading or a legal characterisation of timing; only a computed date from a reviewed, certified rule.
    if r["rule_status"] == "synthetic_test":
        row["deadline_display"] = (TEST_DATE_PREFIX + dl["due_date"] if dl["computed"] else
                                   dl["basis"] if dl["basis"].startswith("TEST RULE") else "TEST RULE: no date until the missing answers are given.")
    else:
        row["deadline_display"] = dl["due_date"] if dl["computed"] and r["rule_status"] == "reviewed" else NO_DATE
    return row


def affected_by(changed_provisions: list[str], catalogue: list[dict] | None = None) -> list[str]:
    """Obligations that cite a changed provision (input from WS-C's change-impact chain); SRC|* matches the whole source."""
    whole = {p.split("|")[0] for p in changed_provisions if p.endswith("|*")}
    hit = lambda k: k in changed_provisions or k.split("|")[0] in whole
    return [ob["id"] for ob in (catalogue or load_catalogues()) if any(hit(k) for k in ob.get("provisions", []))]


def wording_violations(report: dict) -> list[str]:
    """Owner-facing text must never contain definitive or certification wording (board finding A4)."""
    texts = [report["banner"]] + list(report["profile_gaps"]["questions"].values())
    for r in report["obligations"]:
        texts += [r["title"], r["meaning"], r["reason"], r["owner_text"], r["deadline"]["basis"], *r["why"], *r["owner_actions"],
                  *(m["question"] for m in r["missing_information"]), *(d["label"] for d in r["documents"]["required"])]
    return [f"{p!r} in: {t}" for t in texts for p in FORBIDDEN if p in t.lower()]
