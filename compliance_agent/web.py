"""Local web interface. Binds to 127.0.0.1 only. No authentication: for a single local user with synthetic data.

    python3 -m compliance_agent.web [--db data/CL_compliance.sqlite3] [--port 8765] [--clock 2026-10-16T10:00:00]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import MODE_LABEL, scenario
from .clock import FixedClock, SystemClock
from .engine import Engine, WorkflowError
from .kb import KnowledgeBase
from . import evaluation
from .dbsafety import AuthoritativeDatabaseError
from .profiles import ProfileError
from .store import Store

from . import audit_records as AR       # Task 2 A-1: one audit record per owner-facing response
from .audit_log import AuditLog, AuditWriteError, FAIL_TEXT as AUDIT_FAIL_TEXT
from .rag_c import policy_gate as PG   # CR-29 / D-088: WS C's personal-data intake gate, pinned at C e01c371 (gate files only)

HERE = Path(__file__).resolve().parent
UI = HERE / "ui.html"
UI360 = HERE / "ui360.html"
MAX_BODY = 64 * 1024
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


class App:
    def __init__(self, db_path: Path, clock: SystemClock, ledger_path: Path | None = None,
                 audit_dir: Path | None = None, reviewer_mode: bool = False):
        self.db_path = db_path
        self.clock = clock
        self.ledger_path = ledger_path
        self._asker = None
        self.engine = Engine(Store(db_path), clock)
        self.kb = KnowledgeBase(self.engine)
        self.lock = threading.Lock()  # one request touches the database at a time
        self.gate_log = deque(maxlen=500)   # CR-29 R4: identifiers only (never the text, a matched value or its hash)
        # A-1: audit log in the workspace data folder (never the authoritative DB); audit view only in reviewer mode
        self.audit = AuditLog(Path(audit_dir) if audit_dir else Path(db_path).resolve().parent / "audit-logs", self.engine.s)
        self.reviewer_mode = bool(reviewer_mode)
        self.scenario_runs: dict = {}         # A-2: run_id -> scenarios.Run (in memory; synthetic events only)

    def gate(self, text, entry: str) -> dict:
        """CR-29 R1: run WS C's policy gate FIRST, on the server, for free text an owner or reviewer types.
        Fails closed: if the gate itself fails, the input is not processed."""
        try:
            d = PG.policy_gate(text)
            if not isinstance(d, dict) or d.get("action") not in ("allow", "warn", "block"):
                raise ValueError("unexpected gate result")
        except Exception:
            d = {"action": "block", "process": False, "control_ids": [PG.FAIL_CONTROL], "detector_ids": [],
                 "clause_ids": ["HERBIZ-FAIL-CLOSED"],
                 "owner_message": "HerBiz could not check this input for personal details, so it was not processed. Please try again later.",
                 "log_record": {"action": "block", "control_ids": [PG.FAIL_CONTROL], "detector_ids": [],
                                "clause_ids": ["HERBIZ-FAIL-CLOSED"], "kb_version": None, "kb_sha256": None}}
        if d["action"] != "allow":
            rec = {"event": "policy_gate", "entry": entry, **{k: d["log_record"].get(k) for k in
                   ("action", "control_ids", "detector_ids", "clause_ids", "kb_version", "kb_sha256")}}
            self.gate_log.append(rec)
            print(json.dumps(rec), file=sys.stderr)
        return d

    def stages_done(self) -> list[str]:
        return json.loads(self.engine.s.get_meta("stages_done", "[]"))

    def run_stage(self, sid: str, human: bool) -> list[str]:
        st = {s[0]: s for s in scenario.STAGES}
        if sid not in st:
            raise WorkflowError("unknown stage")
        done = self.stages_done()
        key = f"{sid}{'h' if human else ''}"
        if key in done:
            return [f"Stage {sid} already run; nothing repeated (retry-safe)."]
        expected = [s[0] for s in scenario.STAGES]
        prior = expected[: expected.index(sid)]
        if any(p not in done for p in prior):
            raise WorkflowError(f"run earlier stages first: {', '.join(p for p in prior if p not in done)}")
        fn = st[sid][3] if human else st[sid][2]
        if fn is None:
            raise WorkflowError("this stage has no simulated reviewer step")
        if human and sid not in done:
            raise WorkflowError("run the stage's system step first")
        out = fn(self.engine)
        with self.engine.s.db:
            self.engine.s.set_meta("stages_done", json.dumps(done + [key]))
        return out

    @property
    def asker(self):
        if self._asker is None:
            from .ask import Asker
            self._asker = Asker(self.db_path, self.ledger_path)
        return self._asker

    def onboard(self, body: dict) -> dict:
        """Owner onboarding (synthetic demo business only). Creates the single demo profile or updates its facts.
        Loads the test rules first if they are not loaded yet. Unknown answers stay unknown (null)."""
        done = self.stages_done()
        if "0" not in done:
            self.run_stage("0", False)
            done = self.stages_done()
        e = self.engine
        cur = e.latest_profile("BP-0001")
        facts = dict(cur["facts"]) if cur else {}
        num = lambda k: None if body.get(k) in (None, "") else int(body[k])
        tri = lambda v: None if v in (None, "", "unsure") else (v is True or v == "true")
        activity = str(body.get("activity") or "").strip() or None
        tags = {"home_food": ["food"], "beauty": ["beauty"], "design_online": ["design", "online_services"],
                "handmade_goods": ["handmade_goods"], "tutoring": ["education"]}.get(activity or "", [])
        sales = num("sales_last_12m_aed")
        facts.update({
            "jurisdiction": body.get("jurisdiction") or None,
            "activity": activity, "activity_tags": tags,
            "licensing_context": body.get("licensing_context") or None,
            "vat_registered": tri(body.get("vat_registered")),
            "expected_taxable_supplies_next_30d_aed": num("expected_next_30d_aed"),
            "ledger_last_12m": None if sales is None else [{"type": "sale_of_services", "amount_aed": sales,
                                                            "note": "total sales entered by the owner (demo)"}],
        })
        name = (str(body.get("display_name") or "").strip()[:60] or (cur["display_name"] if cur else "My home business")) 
        if "(synthetic)" not in name:
            name += " (synthetic)"
        prof = {"profile_id": "BP-0001", "project_id": "CA-PRJ-001", "business_id": "HHB-SYN-0001",
                "display_name": name, "synthetic": True, "facts": facts}
        v = e.upsert_profile(prof, actor="owner (onboarding)")
        if "1" not in done:
            with e.s.db:
                e.s.set_meta("stages_done", json.dumps(done + ["1"]))
        return {"version": v["version"]}

    def reset(self) -> str:
        """Keep the old demo database as a dated backup; never delete it."""
        self.engine.s.close()
        backup = None
        if self.db_path.exists():
            backup = self.db_path.with_name(self.db_path.stem + "_backup_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S") + ".sqlite3")
            shutil.move(str(self.db_path), backup)
        self.engine = Engine(Store(self.db_path), self.clock)
        self.kb = KnowledgeBase(self.engine)
        self._asker = None
        return str(backup) if backup else "no previous database"


def design_refs(d: dict) -> dict:
    """Clause ids are shown only as design references (R1), never as a violation or legal finding."""
    return {"design_references": d.get("clause_ids", []),
            "design_references_note": "Design references: principles HerBiz's checks are modelled on. Not a legal finding."}


def blocked_answer(d: dict) -> dict:
    """The answer screen for a blocked question: no question text, no search, no passages."""
    return {"mode": "blocked", "status": "blocked", "status_plain": "Not processed: please remove personal details",
            "answer": d["owner_message"], "question": "", "guard": {"level": "not_applicable", "missing": [], "message": ""},
            "professional": True, **design_refs(d)}


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        server_version = "HerBizComplianceLocal/0.1"

        def log_message(self, fmt, *args):  # quiet; the audit table is the record
            pass

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ALLOWED_HOSTS

        def _send(self, code: int, body: bytes, ctype: str = "application/json", headers: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

        def _session(self) -> str:
            sid = (self.headers.get("X-HerBiz-Session") or "").strip()
            # letters, "-" and "_" only: a session id can never carry an ID number, a phone number or an e-mail
            return sid[:64] if sid and all(("a" <= c.lower() <= "z") or c in "-_" for c in sid) else "no-session"

        def _audited(self, code: int, payload, make_record, ctype: str = "application/json", headers: dict | None = None):
            """Send an owner-facing response only after its audit record is written (A-1 safeguard 3: fail closed)."""
            body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            try:
                rec = make_record(body)
                app.audit.write(rec)
            except (AuditWriteError, Exception):
                return self._json(500, {"error": "AUDIT_WRITE_FAILED", "unavailable": AUDIT_FAIL_TEXT})
            return self._send(code, body, ctype, {**(headers or {}), "X-HerBiz-Audit-Record": rec["record_id"]})

        def do_GET(self):
            with app.lock:
                return self._get()

        def do_POST(self):
            with app.lock:
                return self._post()

        def _get(self):
            if not self._host_ok():
                return self._json(403, {"error": "local access only"})
            u = urlparse(self.path)
            if u.path == "/":
                return self._send(200, UI.read_bytes(), "text/html")
            if u.path == "/360":
                return self._send(200, UI360.read_bytes(), "text/html")
            if u.path.startswith("/api/360/"):
                return self._get360(u)
            if u.path.startswith("/api/audit/"):
                return self._get_audit(u)
            if u.path == "/api/state":
                st = app.engine.state()
                st["mode"] = MODE_LABEL
                st["stages"] = [{"id": s[0], "name": s[1], "has_human": s[3] is not None} for s in scenario.STAGES]
                st["stages_done"] = app.stages_done()
                # full text of each cited source (the engine keeps a 280-character excerpt), for "show full text"
                vids = {c["version_id"] for a in st.get("assessments", []) for c in (a.get("citations") or [])}
                if vids:
                    full = {r["version_id"]: r["text"] for r in app.engine.s.q(
                        f"SELECT version_id, text FROM source_versions WHERE version_id IN ({','.join('?' * len(vids))})", tuple(vids))}
                    for a in st["assessments"]:
                        for c in a.get("citations") or []:
                            c["full_text"] = full.get(c["version_id"], c.get("passage", ""))
                return self._json(200, st)
            if u.path == "/api/search":
                q = parse_qs(u.query).get("q", [""])[0][:200]
                return self._json(200, app.engine.search(q, "BP-0001"))
            qs = parse_qs(u.query)
            arg = lambda k: (qs.get(k, [""])[0] or "")[:300]
            if u.path == "/api/ask":
                # CR-29 R2: free text never travels in a URL. GET serves only the fixed example ids; a question is refused
                # unprocessed (and request lines are never logged: log_message is silent).
                if any(k != "id" for k in qs):
                    return self._json(400, {"error": "Questions are accepted only in the request body (POST), not in the address."})
                out = app.asker.ask("", arg("id") or None)
                ret = out.pop("_retrieval", None)
                return self._audited(200, out, lambda b: AR.ask_record(self._session(), "example", out.get("question"), None, out, b,
                                                                     retrieval=ret))
            if u.path == "/api/scenario/list":
                from . import scenarios as SC
                return self._json(200, {"scenarios": SC.list_scenarios()})
            if u.path == "/api/ask/examples":
                return self._json(200, {"examples": app.asker.examples(), "recorded": len(app.asker.recorded)})
            if u.path == "/api/kb/status":
                return self._json(200, app.kb.status())
            if u.path == "/api/kb/search":
                return self._json(200, app.kb.search(arg("q"), all_versions=arg("all") == "1"))
            if u.path == "/api/kb/passage":
                return self._json(200, app.kb.passage(arg("id")) or {"error": "not found"})
            if u.path == "/api/kb/compare":
                return self._json(200, app.kb.compare(arg("old"), arg("new")))
            if u.path == "/api/kb/interpretations":
                rows = app.engine.s.q(
                    "SELECT o.obligation_id, o.obligation_key, o.title, o.requirement, o.interpretation_status, o.support_status,"
                    " o.support_quote, o.conditions_json, o.action_json, v.version_id, v.origin_label, v.status AS source_status"
                    " FROM obligations o JOIN source_versions v ON v.version_id = o.version_id ORDER BY v.origin_label DESC, o.obligation_id")
                return self._json(200, rows)
            if u.path == "/api/eval":
                run = app.engine.s.one("SELECT * FROM evaluation_runs ORDER BY at DESC, run_id DESC LIMIT 1")
                res = app.engine.s.q("SELECT * FROM evaluation_results WHERE run_id = ? ORDER BY scenario_id", (run["run_id"],)) if run else []
                return self._json(200, {"run": run, "results": res})
            if u.path == "/api/project":
                pf = HERE.parent / "project" / "CL_project_status.json"
                proj = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {   # internal record; not in the export
                    "business_line": "HomepreunerHub / HerBiz", "project_id": "-", "bos_card": "not included in this copy",
                    "updated": "-", "tasks": [], "decisions": [], "release_blockers": [],
                    "task_status_scope": "The internal project-status record is not part of this copy."}
                ev = (HERE.parent / "docs" / "CL_evidence")
                proj["evidence_files"] = sorted(p.name for p in ev.glob("*.txt")) if ev.exists() else []
                proj["kb"] = {k: v for k, v in app.kb.status().items() if not isinstance(v, list)}
                proj["signoffs"] = app.engine.s.q("SELECT * FROM reviewer_signoffs ORDER BY signoff_id")
                return self._json(200, proj)
            if u.path == "/api/history":
                eid = parse_qs(u.query).get("id", [None])[0]
                return self._json(200, app.engine.history(eid))
            return self._json(404, {"error": "not found"})

        def _get360(self, u):
            """HerBiz 360 MVP (WS A): read-only views over pinned WS B / WS C outputs. Fails closed with 503."""
            from .mvp360 import adapter as A, pins as PN
            q = parse_qs(u.query)
            try:
                if u.path == "/api/360/content":
                    k, fx = A.content(), A.fixture()
                    sup = A.suppressed()
                    out = {k2: k[k2] for k2 in ("banner", "who_does_what")} | {
                        # only questions with a recorded answer here; none in an export without the answers file
                        "vat_questions": [q for q in k["vat_questions"] if q not in sup and q in app.asker.recorded],
                        "vat_recorded": bool(app.asker.recorded),
                        "suppressed_steps": sorted(c2 for c2 in sup if c2.startswith("step:")),
                        "snapshot": PN.SNAPSHOT_TEXT, "snapshot_note": PN.SNAPSHOT_NOTE,
                        "personas": A.personas(), "demo_label": fx["demo_scenario_label"], "as_of": PN.DEMO_AS_OF,
                        "pins": {"b": PN.B_COMMIT, "b_fixture": PN.B_FIXTURE_CONTRACT, "c": PN.C_COMMIT, "c_contract": PN.C_CONTRACT}}
                    A.scan(out)
                    return self._json(200, out)
                ch = {"/api/360/ct": "ct", "/api/360/finance": "finance", "/api/360/finance.csv": "finance",
                      "/api/360/change": "change_replay"}.get(u.path)
                sid = self._session()
                if u.path == "/api/360/ct":
                    pid = (q.get("profile") or [""])[0]
                    out, rep = A.ct_journey(pid, with_report=True)
                    ids = {r["id"] for r in out["rows"]}
                    return self._audited(200, out, lambda b: AR.engine_record("ct", sid, pid, "ct_demo", rep, b, "ok",
                                                                             "simulated", only_ids=ids))
                if u.path == "/api/360/finance":
                    out = A.finance(); A.scan(out)
                    return self._audited(200, out, lambda b: AR.simple_record(
                        "finance", sid, "finance_checklist", b, "ok", "simulated", ["simulated_data", "management_estimate"],
                        "an accountant"))
                if u.path == "/api/360/finance.csv":
                    body = A.finance_csv().encode("utf-8")
                    return self._audited(200, body, lambda b: AR.simple_record(
                        "finance", sid, "finance_csv", b, "ok", "simulated", ["simulated_data", "management_estimate"],
                        "an accountant"), ctype="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="CL_herbiz360_demo_records_A2.csv"'})
                if u.path == "/api/360/change":
                    out = A.change_replay(); A.scan(out)
                    srcs = [AR.source_entry(k, None) for k in (out.get("sources") or {})]
                    return self._audited(200, out, lambda b: AR.simple_record(
                        "change_replay", sid, "change_replay", b, "ok", "simulated", ["change_pending_review", "rule_not_reviewed"],
                        "a qualified corporate-tax reviewer", sources=srcs, flags=["simulated_reviewer"]))
            except KeyError as ex:
                out = {"error": str(ex).strip("'")}
                if ch:
                    return self._audited(400, out, lambda b: AR.simple_record(ch, self._session(), "refused", b, "refused",
                                                                              "deterministic", ["not_a_demo_business"], None,
                                                                              error="NOT_A_DEMO_BUSINESS"))
                return self._json(400, out)
            except PN.Unavailable as ex:
                out = {"unavailable": str(ex)}
                if ch:
                    return self._audited(503, out, lambda b: AR.simple_record(ch, self._session(), "unavailable", b, "unavailable",
                                                                              "deterministic", ["unavailable"], None,
                                                                              error="UNAVAILABLE"))
                return self._json(503, out)
            return self._json(404, {"error": "not found"})

        def _get_audit(self, u):
            """Reviewer-only audit view (A-1 safeguard 2): 404 unless the server was started with --reviewer-mode."""
            if not app.reviewer_mode:
                return self._json(404, {"error": "not found"})
            from . import audit_log as AL
            q = parse_qs(u.query)
            name = (q.get("file") or [""])[0]
            files = {f.name: f for f in app.audit.files()}
            if u.path == "/api/audit/files":
                return self._json(200, {"files": sorted(files)})
            if name not in files:
                return self._json(404, {"error": "no such audit file"})
            if u.path == "/api/audit/records":
                return self._json(200, {"records": app.audit.records(files[name], limit=50)})
            if u.path == "/api/audit/verify":
                ok, msg = AL.verify(files[name], str(app.db_path))
                return self._json(200, {"ok": ok, "message": msg})
            return self._json(404, {"error": "not found"})

        def _post(self):
            if not self._host_ok() or self.headers.get("X-Requested-With") != "compliance-ui":
                return self._json(403, {"error": "local interface requests only"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._json(413, {"error": "request too large"})
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("body must be an object")
            except ValueError as ex:
                return self._json(400, {"error": f"malformed JSON: {ex}"})
            p = urlparse(self.path).path
            e = app.engine
            if p == "/api/ask":                  # CR-29 R1/R2: gate first; a blocked question is not searched, echoed, stored or logged
                q = body.get("q")
                sid = self._session()
                if q is None or q == "":
                    out = app.asker.ask("", str(body.get("id") or "")[:40] or None)
                    ret = out.pop("_retrieval", None)
                    return self._audited(200, out, lambda b: AR.ask_record(sid, "example", out.get("question"), None, out, b,
                                                                         retrieval=ret))
                d = app.gate(q, "ask")
                if not d["process"]:
                    out = blocked_answer(d)
                    return self._audited(200, out, lambda b: AR.ask_record(sid, "question", None, d, None, b))
                out = app.asker.ask(str(q)[:500], None)
                ret = out.pop("_retrieval", None)            # reviewer-level detail (trace, ranks): audit record only
                if d["action"] == "warn":
                    out["caution"] = d["owner_message"]
                return self._audited(200, out, lambda b: AR.ask_record(sid, "question", str(q)[:500], d, out, b, retrieval=ret))
            if p in ("/api/scenario/start", "/api/scenario/next"):     # A-2: events released one at a time; each step audited
                from . import scenarios as SC
                if p == "/api/scenario/start":
                    sid_ = str(body.get("scenario_id") or "")
                    if sid_ not in ("SC-1", "SC-2", "SC-3"):
                        return self._json(400, {"error": "scenario_id must be SC-1, SC-2 or SC-3"})
                    run = SC.Run(sid_)
                    if len(app.scenario_runs) > 50:
                        app.scenario_runs.clear()
                    app.scenario_runs[run.run_id] = run
                    return self._json(200, {"run_id": run.run_id, "scenario_id": sid_, "title": run.scenario["title"],
                                            "steps_total": len(run.scenario["steps"]), "released": 0})
                run = app.scenario_runs.get(str(body.get("run_id") or ""))
                if run is None:
                    return self._json(404, {"error": "unknown scenario run"})
                if run.done:
                    return self._json(400, {"error": "all events of this scenario have been released"})
                o = run.next()
                sess = self._session()
                return self._audited(200, SC.public(o), lambda b: SC.record_for(o, sess, b))
            for field, entry in (("note", "signoff_note"), ("context", "review_note")):
                if p in ("/api/signoff", "/api/review") and str(body.get(field) or "").strip():
                    d = app.gate(body[field], entry)          # CR-29 R3: gate reviewer notes before anything is stored
                    if not d["process"]:
                        return self._json(400, {"blocked": True, "error": d["owner_message"], **design_refs(d)})
            try:
                if p == "/api/stage":
                    return self._json(200, {"log": app.run_stage(str(body.get("stage")), bool(body.get("human")))})
                if p == "/api/review":
                    if body.get("kind") == "interpretation":
                        r = e.review_interpretation(body["obligation_id"], body["decision"], body.get("reviewer", ""),
                                                    body.get("role", ""), body.get("context", ""))
                    elif body.get("kind") == "source":
                        r = e.review_source(body["version_id"], body["decision"], body.get("reviewer", ""), body.get("role", ""),
                                            body.get("context", ""), bool(body.get("acknowledge_flags")))
                    else:
                        r = e.review_case(body["case_id"], body["decision"], body.get("reviewer", ""), body.get("role", ""),
                                          body.get("context", ""))
                    return self._json(200, r)
                if p == "/api/eval/run":
                    app.engine.s.db.commit()
                    out = evaluation.run_all(str(app.db_path), app.clock)   # refuses the authoritative database
                    return self._json(200, out["metrics"])
                if p == "/api/signoff":
                    for k in ("item_type", "item_id", "reviewer", "qualification", "decision", "note"):
                        if not str(body.get(k, "")).strip():
                            raise WorkflowError(f"sign-off needs {k}")
                    if body["decision"] not in ("agree", "disagree", "needs_source"):
                        raise WorkflowError("decision must be agree, disagree or needs_source")
                    with e.s.db:
                        e.s.db.execute("INSERT INTO reviewer_signoffs (item_type, item_id, reviewer, qualification, decision, note, at)"
                                       " VALUES (?,?,?,?,?,?,?)", (body["item_type"], body["item_id"], body["reviewer"], body["qualification"],
                                                                  body["decision"], body["note"], e.now()))
                        e._audit(body["reviewer"], "reviewer_signoff", body["item_type"], body["item_id"],
                                 {"decision": body["decision"], "qualification": body["qualification"]})
                    return self._json(200, {"outcome": "recorded"})
                if p == "/api/evidence":
                    return self._json(200, e.submit_evidence(body["case_id"], body.get("items", []), actor="owner (local UI)"))
                if p == "/api/profile":
                    cur = e.latest_profile(body["profile_id"])
                    if not cur:
                        raise WorkflowError("unknown profile")
                    facts = dict(cur["facts"])
                    for k, v in (body.get("facts") or {}).items():
                        facts[k] = v
                    prof = {k: cur[k] for k in ("profile_id", "project_id", "business_id", "display_name")}
                    prof.update(synthetic=True, facts=facts)
                    return self._json(200, {"version": e.upsert_profile(prof, actor="owner (local UI)")["version"]})
                if p == "/api/360/dashboard":
                    from .mvp360 import adapter as A, pins as PN
                    pid, fields = body.get("profile_id"), body.get("fields")
                    if pid is not None and not str(pid).startswith("SYN-"):
                        raise WorkflowError("only the fixed fictional demo businesses (SYN-…) are accepted")
                    if pid is None and not isinstance(fields, dict):
                        raise WorkflowError("choose a demo business or send made-up answers (fields)")
                    sid, kind = self._session(), ("dashboard_profile" if pid else "dashboard_fields")
                    who = pid if pid else "SYN-A360-OWNER"
                    try:
                        changed = set(A.change_replay()["affected_c"]) if body.get("show_change") else None
                        view, rep = A.dashboard(profile_id=pid, fields=None if pid else fields, changed=changed, with_report=True)
                        return self._audited(200, view, lambda b: AR.engine_record("dashboard", sid, who, kind, rep, b, "ok"))
                    except A.InputProblem as ex:
                        out = {"input_problem": {"field": ex.field, "message": ex.message}}
                        return self._audited(400, out, lambda b: AR.engine_record("dashboard", sid, who, kind, None, b, "input_problem",
                                                                                  error="INPUT_PROBLEM"))
                    except PN.Unavailable as ex:
                        out = {"unavailable": str(ex)}
                        return self._audited(503, out, lambda b: AR.engine_record("dashboard", sid, who, kind, None, b, "unavailable",
                                                                                  error="UNAVAILABLE"))
                if p == "/api/onboard":
                    return self._json(200, app.onboard(body))
                if p == "/api/reset":
                    if body.get("confirm") != "RESET DEMO":
                        raise WorkflowError("type RESET DEMO to confirm")
                    return self._json(200, {"backup": app.reset()})
            except (WorkflowError, ProfileError, KeyError, ValueError, AuthoritativeDatabaseError) as ex:   # KeyError: unknown demo business
                return self._json(400, {"error": str(ex)})
            return self._json(404, {"error": "not found"})

    return H


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    root = HERE.parent
    ap.add_argument("--db", default=None, help="database (default: the test workspace copy, data/CL_test_workspace.sqlite3)")
    ap.add_argument("--allow-authoritative", action="store_true",
                    help="explicit override: let the app write to data/CL_compliance.sqlite3 (not for demos)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--clock", default=None, help="fixed demo time, ISO format, Asia/Dubai")
    ap.add_argument("--reviewer-mode", action="store_true",
                    help="start in reviewer mode: enables the audit view /api/audit/* (owner mode returns 404)")
    ap.add_argument("--ledger", default=str(root / "data" / "CL_llm_experiment.sqlite3"),
                    help="experiment ledger with recorded answers (read-only; no AI is called)")
    a = ap.parse_args(argv)
    from .dbsafety import AuthoritativeDatabaseError, ensure_workspace, refuse_authoritative
    db = Path(a.db) if a.db else ensure_workspace()
    try:
        refuse_authoritative(db, a.allow_authoritative, "the local web app")
    except AuthoritativeDatabaseError as ex:
        print(ex)
        return 2
    clock = FixedClock(a.clock) if a.clock else SystemClock()
    app = App(db, clock, Path(a.ledger), reviewer_mode=a.reviewer_mode)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(app))
    print(f"HerBiz Compliance Agent (local) on http://127.0.0.1:{a.port}  [{MODE_LABEL}]  db={db}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
