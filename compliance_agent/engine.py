"""Compliance workflow engine: sources -> applicability -> action cases -> human review -> history.

Deterministic. No model calls. Every state change writes an audit event in the same transaction.
Results never carry a numeric "confidence"; they carry the evidence used and the facts still missing.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections import defaultdict

from . import profiles as P
from . import sources as S
from .clock import SystemClock, iso
from .store import Store

STALE_AFTER_DAYS = 120          # project default for re-checking captured evidence; not a legal rule
USABLE_INTERPRETATIONS = ("fixture_reviewed", "reviewed")
ORIGIN_LABELS = ("REAL_OFFICIAL_SOURCE", "SYNTHETIC_FIXTURE")
CASE_OPEN_STATES = {"open", "awaiting_review", "escalated"}
DEFAULT_PROJECT = "CA-PRJ-001"


class WorkflowError(Exception):
    pass


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


class Engine:
    def __init__(self, store: Store, clock: SystemClock | None = None):
        self.s = store
        self.clock = clock or SystemClock()

    # ------------------------------------------------------------ basics
    def now(self) -> str:
        return iso(self.clock.now())

    def today(self) -> dt.date:
        return self.clock.now().date()

    def _next_id(self, prefix: str) -> str:
        n = int(self.s.get_meta(f"seq:{prefix}", "0")) + 1
        self.s.set_meta(f"seq:{prefix}", str(n))
        return f"{prefix}-{n:04d}"

    def _audit(self, actor: str, event: str, entity: str, entity_id: str, payload: dict | None = None) -> None:
        self.s.audit(self.now(), actor, event, entity, entity_id, payload)

    # ------------------------------------------------------------ profiles
    def latest_profile(self, profile_id: str) -> dict | None:
        r = self.s.one("SELECT * FROM business_profiles WHERE profile_id = ? ORDER BY version DESC LIMIT 1", (profile_id,))
        if r:
            r["facts"] = json.loads(r.pop("facts_json"))
        return r

    def upsert_profile(self, profile: dict, actor: str = "owner") -> dict:
        """Create a profile or a new version of it. Dependent assessments are re-run immediately."""
        p = P.validate_profile(profile)
        prev = self.latest_profile(p["profile_id"])
        if prev and prev["facts"] == p["facts"] and prev["display_name"] == p["display_name"]:
            return prev  # retry of the same edit: no new version, no new events
        version = (prev["version"] + 1) if prev else 1
        with self.s.db:
            self.s.db.execute(
                "INSERT INTO business_profiles VALUES (?,?,?,?,?,?,1,?)",
                (p["profile_id"], version, p["project_id"], p["business_id"], p["display_name"], _j(p["facts"]), self.now()))
            changed = sorted(set(p["facts"]) ^ set(prev["facts"]) | {k for k in p["facts"] if prev and prev["facts"].get(k) != p["facts"][k]}) if prev else sorted(p["facts"])
            self._audit(actor, "profile_created" if not prev else "profile_changed", "profile", p["profile_id"],
                        {"version": version, "changed_facts": changed,
                         "missing_material_facts": P.missing_material_facts(p["facts"])})
            self._assess_profile(p["profile_id"], actor="engine")
        return self.latest_profile(p["profile_id"])

    # ------------------------------------------------------------ sources
    def latest_version(self, source_id: str, statuses: tuple[str, ...] | None = None) -> dict | None:
        sql = "SELECT * FROM source_versions WHERE source_id = ?"
        args: list = [source_id]
        if statuses:
            sql += f" AND status IN ({','.join('?' * len(statuses))})"
            args += list(statuses)
        return self.s.one(sql + " ORDER BY seq DESC LIMIT 1", tuple(args))

    def ingest_source(self, rec: dict, actor: str = "collector") -> dict:
        """Register a captured source version. Returns {version_id, change_class, status, case_id}.

        identical -> no-op (retry-safe); cosmetic -> recorded, no action; substantive or new -> candidate + review case,
        unless it is a fixture first version marked preapproved (a stand-in for an already reviewed source).
        """
        for k in ("source_id", "issuing_authority", "authority_type", "jurisdiction", "document_title", "source_url", "text"):
            if not isinstance(rec.get(k), str) or not rec[k].strip():
                raise WorkflowError(f"source record missing {k}")
        if rec["authority_type"] not in ("primary", "secondary"):
            raise WorkflowError("authority_type must be primary or secondary")
        origin = rec.get("origin_label", "SYNTHETIC_FIXTURE")
        if origin not in ORIGIN_LABELS:
            raise WorkflowError(f"origin_label must be one of {ORIGIN_LABELS}")
        if origin == "REAL_OFFICIAL_SOURCE" and rec.get("preapproved_fixture"):
            raise WorkflowError("a real official source can never be preapproved; a human reviewer approves it")
        text = rec["text"]
        h = S.content_hash(text)
        dup = self.s.one("SELECT * FROM source_versions WHERE source_id = ? AND content_hash = ?", (rec["source_id"], h))
        if dup:
            return {"version_id": dup["version_id"], "change_class": "identical", "status": dup["status"], "case_id": None}
        prev = self.latest_version(rec["source_id"], ("approved", "candidate", "cosmetic_noted"))
        approved_prev = self.latest_version(rec["source_id"], ("approved",))
        cls = S.classify_change(approved_prev["text"] if approved_prev else (prev["text"] if prev else None), text)
        flags = S.screen_untrusted(text)
        seq = (self.s.one("SELECT MAX(seq) AS m FROM source_versions WHERE source_id = ?", (rec["source_id"],))["m"] or 0) + 1
        vid = f"{rec['source_id']}@v{seq}"
        if cls == "cosmetic":
            status = "cosmetic_noted"
        elif cls == "first_version" and rec.get("preapproved_fixture") and not flags and origin == "SYNTHETIC_FIXTURE":
            status = "approved"
        else:
            status = "candidate"
        case_id = None
        with self.s.db:
            self.s.db.execute(
                "INSERT INTO source_versions (version_id, source_id, seq, issuing_authority, authority_type, jurisdiction,"
                " document_title, source_url, locator, publication_date, effective_date, retrieved_at, content_hash,"
                " normalized_hash, text, status, change_class, flags_json, fixture, origin_label, doc_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (vid, rec["source_id"], seq, rec["issuing_authority"], rec["authority_type"], rec["jurisdiction"],
                 rec["document_title"], rec["source_url"], rec.get("locator") or "UNKNOWN", rec.get("publication_date"),
                 rec.get("effective_date"), rec.get("retrieved_at") or self.now(), h, S.normalized_hash(text), text,
                 status, cls, _j(flags), 0 if origin == "REAL_OFFICIAL_SOURCE" else 1, origin, rec.get("doc_id")))
            for ob in rec.get("obligations", []):
                self._insert_obligation(vid, ob, text)
            self._audit(actor, f"source_{cls}", "source_version", vid,
                        {"status": status, "flags": flags, "content_hash": h[:16]})
            if status == "candidate":
                case_id = self._open_source_case(vid, cls, flags, approved_prev)
            if status == "approved":
                self._reassess_all()
        return {"version_id": vid, "change_class": cls, "status": status, "case_id": case_id}

    def _reassess_all(self) -> None:
        for pid in [r["profile_id"] for r in self.s.q("SELECT DISTINCT profile_id FROM business_profiles")]:
            self._assess_profile(pid, actor="engine")

    @staticmethod
    def support_check(quotes, source_text: str) -> str:
        """Citation presence is not support. Every supporting quote must appear in the cited text (after removing
        formatting noise). Returns supported | unsupported | not_checked (no quote given)."""
        if not quotes:
            return "not_checked"
        quotes = [quotes] if isinstance(quotes, str) else quotes
        norm = S.normalize(source_text)
        return "supported" if all(S.normalize(q) in norm for q in quotes) else "unsupported"

    def _support_multi(self, quotes: list, vid: str, source_text: str) -> str:
        """Quotes may be plain text (checked against this version) or {source_id, quote} (checked against the newest
        captured version of that source). All must be found."""
        if not quotes:
            return "not_checked"
        for q in quotes:
            if isinstance(q, dict):
                v = self.s.one("SELECT text FROM source_versions WHERE source_id = ? AND status != 'rejected' ORDER BY seq DESC LIMIT 1",
                               (q["source_id"],))
                if not v or self.support_check(q["quote"], v["text"]) != "supported":
                    return "unsupported"
            elif self.support_check(q, source_text) != "supported":
                return "unsupported"
        return "supported"

    def _insert_obligation(self, vid: str, ob: dict, source_text: str) -> None:
        for k in ("obligation_key", "title", "requirement", "conditions", "action"):
            if k not in ob:
                raise WorkflowError(f"obligation missing {k}")
        if ob["requirement"] not in ("required", "not_required"):
            raise WorkflowError("requirement must be required or not_required")
        quotes = ob.get("support_quotes") or ([ob["support_quote"]] if ob.get("support_quote") else [])
        support = self._support_multi(quotes, vid, source_text)
        oid = f"{ob['obligation_key']}#{vid}"
        self.s.db.execute(
            "INSERT INTO obligations (obligation_id, obligation_key, version_id, title, requirement, conditions_json,"
            " action_json, interpretation_status, support_quote, support_status, support_passage_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (oid, ob["obligation_key"], vid, ob["title"], ob["requirement"], _j(ob["conditions"]), _j(ob["action"]),
             ob.get("interpretation_status", "unreviewed"), _j(quotes) if quotes else None, support, ob.get("support_passage_id")))
        self._audit("engine", "interpretation_recorded", "obligation", oid,
                    {"interpretation_status": ob.get("interpretation_status", "unreviewed"), "support_status": support})
        if ob.get("interpretation_status", "unreviewed") == "unreviewed" and ob.get("request_review", True) \
                and self.s.one("SELECT origin_label FROM source_versions WHERE version_id = ?", (vid,))["origin_label"] == "REAL_OFFICIAL_SOURCE":
            self._create_case(
                dedupe_key=f"interpretation:{oid}", kind="interpretation_review", profile=None, obligation_key=ob["obligation_key"],
                source_version_id=vid, assessment_id=None, title=f"Review draft interpretation: {ob['title']}", status="open",
                why=("Draft reading of an official source, prepared by software. It is not used for any business until a "
                     "qualified reviewer approves it. Quote check: " + support + "."),
                owner="domain reviewer", reviewer="qualified domain reviewer", due_basis="Before any owner sees this obligation",
                due_date=None, evidence_required=[])

    def review_interpretation(self, obligation_id: str, decision: str, reviewer: str, role: str, context: str) -> dict:
        self._require_reviewer(reviewer, role, context)
        ob = self.s.one("SELECT * FROM obligations WHERE obligation_id = ?", (obligation_id,))
        if not ob:
            raise WorkflowError("unknown obligation")
        case = self.s.one("SELECT * FROM cases WHERE dedupe_key = ?", (f"interpretation:{obligation_id}",))

        def record(decision, outcome):
            if case:
                self._record_review(case["case_id"], decision, reviewer, role, context, outcome)
            else:  # no review case (e.g. a negative control): the decision still goes into the append-only history
                self._audit(reviewer, f"review_{decision}_{outcome}", "obligation", obligation_id, {"role": role, "context": context})

        with self.s.db:
            if ob["interpretation_status"] != "unreviewed":
                record(decision, "refused")
                return {"outcome": "refused", "reason": f"interpretation is already {ob['interpretation_status']}"}
            if decision == "approve" and ob["support_status"] != "supported":
                record(decision, "refused")
                return {"outcome": "refused", "reason": "supporting quote not found in the cited source text"}
            if decision not in ("approve", "reject"):
                raise WorkflowError("decision must be approve or reject")
            new = "reviewed" if decision == "approve" else "rejected"
            self.s.db.execute("UPDATE obligations SET interpretation_status = ? WHERE obligation_id = ?", (new, obligation_id))
            self._audit(reviewer, f"interpretation_{new}", "obligation", obligation_id, {"role": role, "context": context})
            record(decision, "accepted")
            if case:
                self._set_case(case["case_id"], reviewer, status="resolved" if decision == "approve" else "rejected",
                               why=f"Reviewer decision: {decision}. {context}")
            self._reassess_all()
        return {"outcome": "accepted", "status": new}

    def _open_source_case(self, vid: str, cls: str, flags: list[str], approved_prev: dict | None) -> str:
        why = ("New source version differs in substance from the approved one; it does not replace it until reviewed."
               if cls == "substantive" else "New source; not used for any assessment until reviewed.")
        if flags:
            why += " Text contains instruction-like wording; treated as data and held for review."
        return self._create_case(
            dedupe_key=f"source_update:{vid}", kind="source_update", profile=None, obligation_key=None,
            source_version_id=vid, assessment_id=None, title=f"Review source change: {vid}", status="open", why=why,
            owner="source maintainer", reviewer="domain reviewer", due_basis="Before the version can be used",
            due_date=None, evidence_required=["Reviewer compares the new text with the approved version and the official source"])

    def review_source(self, version_id: str, decision: str, reviewer: str, role: str, context: str,
                      acknowledge_flags: bool = False) -> dict:
        v = self.s.one("SELECT * FROM source_versions WHERE version_id = ?", (version_id,))
        if not v:
            raise WorkflowError("unknown source version")
        case = self.s.one("SELECT * FROM cases WHERE dedupe_key = ?", (f"source_update:{version_id}",))
        if v["status"] != "candidate":
            raise WorkflowError(f"version is {v['status']}, not a candidate")
        self._require_reviewer(reviewer, role, context)
        flags = json.loads(v["flags_json"])
        with self.s.db:
            if decision == "approve" and flags and not acknowledge_flags:
                self._record_review(case["case_id"] if case else version_id, decision, reviewer, role, context, "refused")
                self._audit(reviewer, "source_approval_refused", "source_version", version_id, {"reason": "flags not acknowledged", "flags": flags})
                return {"outcome": "refused", "reason": "Source has instruction-like text; reviewer must acknowledge the flags explicitly."}
            if decision == "approve":
                old = self.latest_version(v["source_id"], ("approved",))
                if old:
                    self.s.db.execute("UPDATE source_versions SET status='superseded', superseded_by=? WHERE version_id=?", (version_id, old["version_id"]))
                self.s.db.execute("UPDATE source_versions SET status='approved' WHERE version_id=?", (version_id,))
                self._audit(reviewer, "source_approved", "source_version", version_id,
                            {"supersedes": old["version_id"] if old else None, "context": context})
                outcome = "resolved"
            elif decision == "reject":
                self.s.db.execute("UPDATE source_versions SET status='rejected' WHERE version_id=?", (version_id,))
                self._audit(reviewer, "source_rejected", "source_version", version_id, {"context": context})
                outcome = "rejected"
            else:
                raise WorkflowError("decision must be approve or reject")
            if case:
                self._record_review(case["case_id"], decision, reviewer, role, context, "accepted")
                self._set_case(case["case_id"], status=outcome, actor=reviewer, why=f"Reviewer decision: {decision}. {context}")
            self._reassess_all()
        return {"outcome": "accepted", "status": "approved" if decision == "approve" else "rejected"}

    # ------------------------------------------------------------ retrieval
    def usable_obligations(self, as_of: dt.date | None = None) -> tuple[list[dict], list[dict]]:
        """Approved, current, in-force obligations, plus approved ones with a future effective date (upcoming)."""
        as_of = as_of or self.today()
        rows = self.s.q(
            "SELECT o.*, v.source_id, v.issuing_authority, v.authority_type, v.jurisdiction, v.document_title, v.source_url,"
            " v.locator, v.publication_date, v.effective_date, v.retrieved_at, v.text, v.seq, v.origin_label FROM obligations o"
            " JOIN source_versions v ON v.version_id = o.version_id WHERE v.status = 'approved'"
            f" AND o.interpretation_status IN ({','.join('?' * len(USABLE_INTERPRETATIONS))}) AND o.support_status != 'unsupported'"
            " ORDER BY o.obligation_key, v.source_id", USABLE_INTERPRETATIONS)
        now, upcoming = [], []
        for r in rows:
            r["conditions"] = json.loads(r.pop("conditions_json"))
            r["action"] = json.loads(r.pop("action_json"))
            eff = r["effective_date"]
            if eff and dt.date.fromisoformat(eff) > as_of:
                upcoming.append(r)
            else:
                now.append(r)
        return now, upcoming

    def search(self, query: str, profile_id: str | None = None) -> dict:
        """Transparent keyword search over approved sources. Shows matched words; no embeddings, no model."""
        terms = {t for t in re.findall(r"[a-z0-9]{3,}", query.lower())} - {"the", "and", "for", "what", "does", "need", "with", "my"}
        obligations, upcoming = self.usable_obligations()
        prof = self.latest_profile(profile_id) if profile_id else None
        hits = []
        for r in obligations + upcoming:
            if prof and prof["facts"].get("jurisdiction") and r["jurisdiction"] not in ("AE", prof["facts"]["jurisdiction"]):
                continue
            words = set(re.findall(r"[a-z0-9]{3,}", (r["title"] + " " + r["text"]).lower()))
            matched = sorted(terms & words)
            if matched:
                hits.append({"obligation_key": r["obligation_key"], "title": r["title"], "version_id": r["version_id"],
                             "jurisdiction": r["jurisdiction"], "matched_terms": matched, "score": len(matched),
                             "upcoming": r in upcoming, "locator": r["locator"], "source_url": r["source_url"]})
        hits.sort(key=lambda h: (-h["score"], h["obligation_key"]))
        return {"mode": "deterministic keyword match over approved fixture sources (no AI model)", "terms": sorted(terms), "hits": hits}

    # ------------------------------------------------------------ applicability
    def _value(self, facts: dict, cond: dict):
        """Return (value, missing_fact_or_None)."""
        if "computed" in cond:
            if cond["computed"] == "taxable_supplies_last_12m_aed":
                ts = P.taxable_supplies(facts.get("ledger_last_12m"))
                return ts["total_aed"], (None if ts["total_aed"] is not None else "ledger_last_12m")
            if cond["computed"] == "art19_registration_value_last_12m_aed":
                ts = P.taxable_supplies(facts.get("ledger_last_12m"))
                cg = facts.get("concerned_goods_services_last_12m_aed")
                rp = facts.get("acquired_business_or_related_party_supplies")
                if rp is None:
                    return None, "acquired_business_or_related_party_supplies"
                if rp is True:  # Art. 19(3)-(4) amounts are added to the total; software cannot value them
                    return None, "reviewer_calculation_art19_3_4"
                if ts["total_aed"] is None:
                    return None, "ledger_last_12m"
                if cg is None:
                    return None, "concerned_goods_services_last_12m_aed"
                return ts["total_aed"] + cg, None
            raise WorkflowError(f"unknown computed value {cond['computed']}")
        f = cond["fact"]
        return facts.get(f), (f if facts.get(f) is None else None)

    def _eval(self, node: dict, facts: dict, params: dict) -> tuple[bool | None, list[str], list[str]]:
        """Three-valued evaluation. Returns (result, missing facts, explanation lines)."""
        if "all" in node or "any" in node:
            mode = "all" if "all" in node else "any"
            parts = [self._eval(c, facts, params) for c in node[mode]]
            vals = [p[0] for p in parts]
            missing = sorted({m for p in parts for m in p[1]})
            lines = [l for p in parts for l in p[2]]
            if mode == "all":
                res = False if False in vals else (None if None in vals else True)
            else:
                res = True if True in vals else (None if None in vals else False)
            if res is not None:
                missing = []  # a decided branch does not need the unknown facts
            return res, missing, lines
        val, missing = self._value(facts, node)
        label = node.get("label") or node.get("fact") or node.get("computed")
        if missing:
            return None, [missing], [f"{label}: unknown"]
        op = node["op"]
        target = params[node["param"]] if "param" in node else node.get("value")
        if op == "eq":
            res = val == target
        elif op == "in":
            res = val in target
        elif op == "contains":
            res = target in (val or [])
        elif op == "is_true":
            res = val is True
        elif op == "is_false":
            res = val is False
        elif op == "clarify_if_true":   # a 'yes' cannot be decided by software: a reviewer must calculate
            if val is True:
                return None, [node.get("clarify_as", f"reviewer_calculation:{label}")], [f"{label}: yes -> reviewer must calculate"]
            res = True
        elif op == "gt":
            res = float(val) > float(target)
        elif op == "gte":
            res = float(val) >= float(target)
        else:
            raise WorkflowError(f"unknown op {op}")
        shown = f"{val:,.0f}" if isinstance(val, (int, float)) and not isinstance(val, bool) else val
        return res, [], [f"{label}: {shown} {op} {target} -> {'yes' if res else 'no'}"]

    def _citation(self, r: dict, stale: bool) -> dict:
        return {"version_id": r["version_id"], "authority": r["issuing_authority"], "authority_type": r["authority_type"],
                "title": r["document_title"], "locator": r["locator"], "url": r["source_url"],
                "effective_date": r["effective_date"], "retrieved_at": r["retrieved_at"], "stale": stale,
                "origin_label": r.get("origin_label"), "interpretation": r.get("interpretation_status"),
                "support_status": r.get("support_status"), "support_quote": json.loads(r["support_quote"]) if r.get("support_quote") else None,
                "passage": r["text"][:280]}

    def assess(self, profile: dict, as_of: dt.date | None = None) -> list[dict]:
        """Pure assessment (no writes). One result per obligation_key."""
        as_of = as_of or self.today()
        facts = profile["facts"]
        obligations, upcoming = self.usable_obligations(as_of)
        by_key: dict[str, list[dict]] = defaultdict(list)
        for r in obligations:
            by_key[r["obligation_key"]].append(r)
        out = []
        missing_material = P.missing_material_facts(facts)
        for key, rows in sorted(by_key.items()):
            per_source = []
            for r in rows:
                juris = facts.get("jurisdiction")
                if r["jurisdiction"] != "AE" and juris is not None and juris != r["jurisdiction"]:
                    per_source.append(("not_applicable", [], [f"jurisdiction {juris} is outside {r['jurisdiction']}"], r))
                    continue
                params = r["conditions"].get("params", {})
                res, missing, lines = self._eval({"all": r["conditions"]["all"]}, facts, params)
                if r["jurisdiction"] != "AE" and juris is None:
                    res, missing = (None, sorted(set(missing) | {"jurisdiction"})) if res is not False else (res, missing)
                    lines.append("jurisdiction: unknown (rule is emirate-specific)")
                if res is True:
                    verdict = "applicable" if r["requirement"] == "required" else "not_required"
                elif res is False:
                    verdict = "not_applicable"
                else:
                    verdict = "needs_clarification"
                per_source.append((verdict, missing, lines, r))
            verdicts = {v for v, *_ in per_source}
            stale = {r["version_id"] for *_, r in per_source
                     if (as_of - dt.datetime.fromisoformat(r["retrieved_at"]).date()).days > STALE_AFTER_DAYS}
            cites = [self._citation(r, r["version_id"] in stale) for *_, r in per_source]
            missing = sorted({m for _, ms, _, _ in per_source for m in ms})
            lines = [f"[{r['version_id']}] " + "; ".join(ls) for _, _, ls, r in per_source]
            first = per_source[0][3]
            if "applicable" in verdicts and "not_required" in verdicts:
                result = "conflict"
                why = "Sources disagree on whether this is required for this profile. Both are kept; a reviewer must decide."
            elif "applicable" in verdicts and stale & {r["version_id"] for v, _, _, r in per_source if v == "applicable"}:
                result = "stale_evidence"
                why = f"Applies on the captured text, but that text is older than {STALE_AFTER_DAYS} days; re-check the source first."
            elif "applicable" in verdicts:
                result = "applicable"
                why = "All conditions in the approved source are met by the profile facts."
            elif "needs_clarification" in verdicts:
                result = "needs_clarification"
                why = "Cannot decide: these facts are missing: " + ", ".join(missing)
            else:
                result = "not_applicable"
                why = "At least one condition in the approved source is not met by the profile facts."
            if missing_material and result == "applicable":
                why += " Note: material facts still missing (" + ", ".join(missing_material) + "); other rules may apply."
            out.append({"obligation_key": key, "title": first["title"], "result": result, "rationale": why,
                        "explanation": lines, "missing": missing, "citations": cites,
                        "action": first["action"], "source_versions": sorted(r["version_id"] for *_, r in per_source)})
        for r in upcoming:
            out.append({"obligation_key": r["obligation_key"] + ":upcoming", "title": r["title"], "result": "not_yet_in_force",
                        "rationale": f"Approved source takes effect on {r['effective_date']}; no action is raised before then.",
                        "explanation": [], "missing": [], "citations": [self._citation(r, False)], "action": r["action"],
                        "source_versions": [r["version_id"]]})
        return out

    def _assess_profile(self, profile_id: str, actor: str) -> None:
        prof = self.latest_profile(profile_id)
        results = self.assess(prof)
        current = {r["obligation_key"]: r for r in self.s.q(
            "SELECT * FROM assessments WHERE profile_id = ? AND current = 1", (profile_id,))}
        for res in results:
            key = res["obligation_key"]
            sig = _j([res["result"], res["missing"], res["source_versions"], prof["version"]])
            old = current.pop(key, None)
            if old and _j([old["result"], json.loads(old["missing_json"]), sorted(c["version_id"] for c in json.loads(old["citations_json"])), old["profile_version"]]) == sig:
                continue  # unchanged: retry-safe
            if old:
                self.s.db.execute("UPDATE assessments SET current = 0 WHERE assessment_id = ?", (old["assessment_id"],))
            aid = self._next_id("ASM")
            self.s.db.execute("INSERT INTO assessments VALUES (?,?,?,?,?,?,?,?,1,?)",
                              (aid, profile_id, prof["version"], key, res["result"], res["rationale"] + "\n" + "\n".join(res["explanation"]),
                               _j(res["missing"]), _j(res["citations"]), self.now()))
            self._audit(actor, "assessment_recorded", "assessment", aid,
                        {"profile_id": profile_id, "profile_version": prof["version"], "obligation_key": key,
                         "result": res["result"], "previous": old["result"] if old else None, "sources": res["source_versions"]})
            if not key.endswith(":upcoming"):
                self._sync_case(prof, res, aid)
        for key, old in current.items():  # obligation no longer in force (e.g. superseded with no replacement)
            self.s.db.execute("UPDATE assessments SET current = 0 WHERE assessment_id = ?", (old["assessment_id"],))
            if key.endswith(":upcoming") or old["result"] == "not_applicable":
                continue
            aid = self._next_id("ASM")
            why = "No approved source is in force for this obligation any more (superseded, withdrawn or rejected)."
            self.s.db.execute("INSERT INTO assessments VALUES (?,?,?,?,?,?,?,?,1,?)",
                              (aid, profile_id, prof["version"], key, "not_applicable", why, "[]", "[]", self.now()))
            self._audit(actor, "assessment_recorded", "assessment", aid,
                        {"profile_id": profile_id, "obligation_key": key, "result": "not_applicable", "previous": old["result"]})
            self._sync_case(prof, {"obligation_key": key, "result": "not_applicable", "action": {}, "title": key,
                                   "source_versions": []}, aid)

    # ------------------------------------------------------------ cases
    def _create_case(self, *, dedupe_key, kind, profile, obligation_key, source_version_id, assessment_id, title, status,
                     why, owner, reviewer, due_basis, due_date, evidence_required) -> str:
        existing = self.s.one("SELECT case_id FROM cases WHERE dedupe_key = ?", (dedupe_key,))
        if existing:
            return existing["case_id"]
        cid = self._next_id("CASE")
        now = self.now()
        self.s.db.execute(
            "INSERT INTO cases (case_id, dedupe_key, kind, project_id, business_id, profile_id, obligation_key,"
            " source_version_id, assessment_id, title, status, why, owner, reviewer, due_basis, due_date,"
            " evidence_required_json, evidence_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'[]',?,?)",
            (cid, dedupe_key, kind, profile["project_id"] if profile else DEFAULT_PROJECT, profile["business_id"] if profile else None,
             profile["profile_id"] if profile else None, obligation_key, source_version_id, assessment_id, title, status, why,
             owner, reviewer, due_basis, due_date, _j(evidence_required), now, now))
        self._audit("engine", "case_created", "case", cid, {"kind": kind, "status": status, "why": why})
        self._alert(cid, status, why)
        return cid

    def _alert(self, case_id: str, status: str, why: str) -> None:
        key = f"{case_id}:{status}:{S.content_hash(why)[:12]}"
        self.s.db.execute("INSERT OR IGNORE INTO alerts (dedupe_key, case_id, message, created_at) VALUES (?,?,?,?)",
                          (key, case_id, why, self.now()))

    def _set_case(self, case_id: str, actor: str, **fields) -> None:
        old = self.s.one("SELECT * FROM cases WHERE case_id = ?", (case_id,))
        changes = {k: v for k, v in fields.items() if old.get(k) != v}
        if not changes:
            return
        changes["updated_at"] = self.now()
        self.s.db.execute(f"UPDATE cases SET {', '.join(f'{k} = ?' for k in changes)} WHERE case_id = ?",
                          (*changes.values(), case_id))
        self._audit(actor, "case_updated", "case", case_id,
                    {k: {"from": old.get(k), "to": v} for k, v in changes.items() if k not in ("updated_at",)})
        if "status" in changes:
            self._alert(case_id, changes["status"], fields.get("why", old["why"]))

    def _due(self, action: dict, facts: dict) -> tuple[str, str | None]:
        due = action.get("due", {})
        basis = due.get("basis_text", "No due date stated in the approved source; reviewer to confirm.")
        f = due.get("basis_fact")
        if f:
            v = facts.get(f)
            if v is None:
                return basis + f" Date unknown until '{f}' is supplied (it is never inferred from other dates).", None
            return basis, v
        return basis, None

    def _sync_case(self, prof: dict, res: dict, aid: str) -> None:
        key = res["obligation_key"]
        dkey = f"{prof['profile_id']}:{key}"
        case = self.s.one("SELECT * FROM cases WHERE dedupe_key = ?", (dkey,))
        r = res["result"]
        action = res["action"]
        due_basis, due_date = self._due(action, prof["facts"])
        evidence = action.get("evidence_required", [])
        if r == "not_applicable":
            if case and case["status"] in CASE_OPEN_STATES:
                self._set_case(case["case_id"], "engine", status="escalated", assessment_id=aid,
                               why="Now assessed as not applicable after a change. A reviewer must confirm before the case is withdrawn.")
            return
        kind, status, why, title = {
            "applicable": ("obligation_action", "open", res["rationale"], action.get("label", res["title"])),
            "needs_clarification": ("clarification", "open", res["rationale"], f"Missing facts for: {res['title']}"),
            "conflict": ("conflict", "escalated", res["rationale"], f"Conflicting sources: {res['title']}"),
            "stale_evidence": ("obligation_action", "escalated", res["rationale"], action.get("label", res["title"])),
        }[r]
        owner = "business owner" if kind in ("obligation_action", "clarification") else "domain reviewer"
        reviewer = action.get("reviewer", "domain reviewer")
        if not case:
            self._create_case(dedupe_key=dkey, kind=kind, profile=prof, obligation_key=key,
                              source_version_id=",".join(res["source_versions"]), assessment_id=aid, title=title,
                              status=status, why=why, owner=owner, reviewer=reviewer, due_basis=due_basis,
                              due_date=due_date, evidence_required=evidence)
            return
        old_req = json.loads(case["evidence_required_json"])
        if case["status"] == "resolved" and kind == "obligation_action" and old_req == evidence and r == "applicable":
            self._set_case(case["case_id"], "engine", assessment_id=aid, source_version_id=",".join(res["source_versions"]))
            return
        if case["status"] == "awaiting_review" and kind == "obligation_action" and old_req == evidence and r == "applicable":
            status = "awaiting_review"
        if case["status"] in ("resolved", "withdrawn"):
            why = "Reopened: " + why
        self._set_case(case["case_id"], "engine", kind=kind, status=status, why=why, title=title, owner=owner,
                       reviewer=reviewer, assessment_id=aid, source_version_id=",".join(res["source_versions"]),
                       due_basis=due_basis, due_date=due_date, evidence_required_json=_j(evidence))

    @staticmethod
    def _require_reviewer(reviewer: str, role: str, context: str) -> None:
        if not (reviewer or "").strip() or not (role or "").strip() or not (context or "").strip():
            raise WorkflowError("a review needs the reviewer's name, role and a short context note")

    def _record_review(self, case_id, decision, reviewer, role, context, outcome) -> None:
        self.s.db.execute("INSERT INTO reviews (case_id, decision, reviewer, role, context, outcome, decided_at) VALUES (?,?,?,?,?,?,?)",
                          (case_id, decision, reviewer.strip(), role.strip(), context.strip(), outcome, self.now()))
        self._audit(reviewer, f"review_{decision}_{outcome}", "case", case_id, {"role": role, "context": context})

    def evidence_gaps(self, case: dict) -> list[str]:
        req = json.loads(case["evidence_required_json"])
        got = {e["requirement"] for e in json.loads(case["evidence_json"]) if e.get("provided") and (e.get("description") or "").strip()}
        return [r for r in req if r not in got]

    def submit_evidence(self, case_id: str, items: list[dict], actor: str = "owner") -> dict:
        case = self.s.one("SELECT * FROM cases WHERE case_id = ?", (case_id,))
        if not case:
            raise WorkflowError("unknown case")
        if case["kind"] != "obligation_action" or case["status"] not in ("open", "awaiting_review"):
            raise WorkflowError(f"evidence can only be added to an open action case (this one is {case['kind']}/{case['status']})")
        req = set(json.loads(case["evidence_required_json"]))
        for it in items:
            if it.get("requirement") not in req:
                raise WorkflowError(f"not a requirement of this case: {it.get('requirement')}")
        merged = {e["requirement"]: e for e in json.loads(case["evidence_json"])}
        for it in items:
            merged[it["requirement"]] = {"requirement": it["requirement"], "description": (it.get("description") or "").strip(),
                                         "provided": bool(it.get("provided")), "submitted_at": self.now(), "by": actor}
        with self.s.db:
            self.s.db.execute("UPDATE cases SET evidence_json = ?, updated_at = ? WHERE case_id = ?",
                              (_j(list(merged.values())), self.now(), case_id))
            self._audit(actor, "evidence_submitted", "case", case_id, {"items": items})
            case = self.s.one("SELECT * FROM cases WHERE case_id = ?", (case_id,))
            gaps = self.evidence_gaps(case)
            if gaps:
                self._set_case(case_id, "engine", status="open", why="Evidence incomplete. Still needed: " + "; ".join(gaps))
            else:
                self._set_case(case_id, "engine", status="awaiting_review", why="All listed evidence supplied; waiting for reviewer.")
        return {"status": "awaiting_review" if not gaps else "open", "missing": gaps}

    def review_case(self, case_id: str, decision: str, reviewer: str, role: str, context: str) -> dict:
        """Human decision on a case. Approval is refused unless every evidence requirement is satisfied."""
        self._require_reviewer(reviewer, role, context)
        case = self.s.one("SELECT * FROM cases WHERE case_id = ?", (case_id,))
        if not case:
            raise WorkflowError("unknown case")
        if case["kind"] == "source_update":
            return self.review_source(case["source_version_id"], decision, reviewer, role, context)
        if decision not in ("approve", "reject"):
            raise WorkflowError("decision must be approve or reject")
        with self.s.db:
            if case["status"] in ("resolved", "withdrawn"):
                self._record_review(case_id, decision, reviewer, role, context, "refused")
                return {"outcome": "refused", "reason": f"case is already {case['status']}"}
            if decision == "reject":
                self._record_review(case_id, decision, reviewer, role, context, "accepted")
                self._set_case(case_id, reviewer, status="open", why=f"Reviewer sent back: {context}")
                return {"outcome": "accepted", "status": "open"}
            # approve
            current = self.s.one("SELECT result FROM assessments WHERE assessment_id = ?", (case["assessment_id"],))
            if current and current["result"] == "not_applicable":
                self._record_review(case_id, decision, reviewer, role, context, "accepted")
                self._set_case(case_id, reviewer, status="withdrawn", why=f"Withdrawn by {reviewer}: {context}")
                return {"outcome": "accepted", "status": "withdrawn"}
            if case["kind"] == "obligation_action":
                gaps = self.evidence_gaps(case)
                if gaps or case["status"] != "awaiting_review":
                    self._record_review(case_id, decision, reviewer, role, context, "refused")
                    self._set_case(case_id, "engine", status="open",
                                   why="Cannot resolve: evidence missing: " + ("; ".join(gaps) if gaps else "not yet submitted"))
                    return {"outcome": "refused", "reason": "evidence incomplete", "missing": gaps}
                self._record_review(case_id, decision, reviewer, role, context, "accepted")
                self._set_case(case_id, reviewer, status="resolved", why=f"Resolved by {reviewer} ({role}): {context}")
                return {"outcome": "accepted", "status": "resolved"}
            # conflict / clarification / stale cannot be approved away: the underlying source or fact must change
            self._record_review(case_id, decision, reviewer, role, context, "refused")
            return {"outcome": "refused", "reason": "resolve the conflict or missing facts through a source review or a profile update first"}

    # ------------------------------------------------------------ views
    def history(self, entity_id: str | None = None, limit: int = 500) -> list[dict]:
        if entity_id:
            rows = self.s.q("SELECT * FROM audit_events WHERE entity_id = ? ORDER BY event_id", (entity_id,))
        else:
            rows = self.s.q("SELECT * FROM audit_events ORDER BY event_id DESC LIMIT ?", (limit,))
        for r in rows:
            r["payload"] = json.loads(r.pop("payload_json"))
        return rows

    def state(self, profile_id: str | None = None) -> dict:
        profs = []
        for r in self.s.q("SELECT DISTINCT profile_id FROM business_profiles ORDER BY profile_id"):
            p = self.latest_profile(r["profile_id"])
            p["missing_material_facts"] = P.missing_material_facts(p["facts"])
            p["taxable_supplies"] = P.taxable_supplies(p["facts"].get("ledger_last_12m"))
            profs.append(p)
        sources = self.s.q("SELECT version_id, source_id, seq, issuing_authority, authority_type, jurisdiction, document_title,"
                           " source_url, locator, publication_date, effective_date, retrieved_at, status, superseded_by,"
                           " change_class, flags_json, fixture, substr(content_hash,1,12) AS hash FROM source_versions ORDER BY source_id, seq")
        for s_ in sources:
            s_["flags"] = json.loads(s_.pop("flags_json"))
        assessments = self.s.q("SELECT * FROM assessments WHERE current = 1 ORDER BY obligation_key")
        for a in assessments:
            a["missing"] = json.loads(a.pop("missing_json"))
            a["citations"] = json.loads(a.pop("citations_json"))
        cases = self.s.q("SELECT * FROM cases ORDER BY case_id")
        for c in cases:
            c["evidence_required"] = json.loads(c.pop("evidence_required_json"))
            c["evidence"] = json.loads(c.pop("evidence_json"))
            c["missing_evidence"] = (self.evidence_gaps({"evidence_required_json": _j(c["evidence_required"]),
                                                         "evidence_json": _j(c["evidence"])})
                                     if c["kind"] == "obligation_action" else [])
            c["reviews"] = self.s.q("SELECT * FROM reviews WHERE case_id = ? ORDER BY review_id", (c["case_id"],))
        return {"profiles": profs, "sources": sources, "assessments": assessments, "cases": cases,
                "alerts": self.s.q("SELECT * FROM alerts ORDER BY alert_id"), "history": self.history(limit=300),
                "now": self.now()}
