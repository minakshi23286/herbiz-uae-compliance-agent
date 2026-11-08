"""Local web interface. Binds to 127.0.0.1 only. No authentication: for a single local user with synthetic data.

    python3 -m compliance_agent.web [--db data/CL_compliance.sqlite3] [--port 8765] [--clock 2026-10-16T10:00:00]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import threading
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

HERE = Path(__file__).resolve().parent
UI = HERE / "ui.html"
MAX_BODY = 64 * 1024
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


class App:
    def __init__(self, db_path: Path, clock: SystemClock, ledger_path: Path | None = None):
        self.db_path = db_path
        self.clock = clock
        self.ledger_path = ledger_path
        self._asker = None
        self.engine = Engine(Store(db_path), clock)
        self.kb = KnowledgeBase(self.engine)
        self.lock = threading.Lock()  # one request touches the database at a time

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


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        server_version = "HerBizComplianceLocal/0.1"

        def log_message(self, fmt, *args):  # quiet; the audit table is the record
            pass

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ALLOWED_HOSTS

        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

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
                return self._json(200, app.asker.ask(arg("q"), arg("id") or None))
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
                proj = json.loads((HERE.parent / "project" / "CL_project_status.json").read_text(encoding="utf-8"))
                ev = (HERE.parent / "docs" / "CL_evidence")
                proj["evidence_files"] = sorted(p.name for p in ev.glob("*.txt")) if ev.exists() else []
                proj["kb"] = {k: v for k, v in app.kb.status().items() if not isinstance(v, list)}
                proj["signoffs"] = app.engine.s.q("SELECT * FROM reviewer_signoffs ORDER BY signoff_id")
                return self._json(200, proj)
            if u.path == "/api/history":
                eid = parse_qs(u.query).get("id", [None])[0]
                return self._json(200, app.engine.history(eid))
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
                if p == "/api/onboard":
                    return self._json(200, app.onboard(body))
                if p == "/api/reset":
                    if body.get("confirm") != "RESET DEMO":
                        raise WorkflowError("type RESET DEMO to confirm")
                    return self._json(200, {"backup": app.reset()})
            except (WorkflowError, ProfileError, KeyError, ValueError, AuthoritativeDatabaseError) as ex:
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
    app = App(db, clock, Path(a.ledger))
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(app))
    print(f"HerBiz Compliance Agent (local) on http://127.0.0.1:{a.port}  [{MODE_LABEL}]  db={db}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
