"""Task 2 A-7: write scanner-clean sample audit logs for the export (docs/360/evidence/audit-logs/). Local only; no network.

    python3 experiments/ws_a/CL_build_audit_samples.py

Runs one synthetic session against a temporary workspace (a copy of the knowledge-base database, read once): every owner
channel (ask: recorded, allowed, warned, blocked; dashboard; ct; finance JSON and CSV; change replay) and the three error
scenarios. The hash chain is verified and the offline scanner must report no findings before anything is written; the
samples carry hashes and metadata only (no question text except gate-allowed synthetic questions, no passage text).
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from compliance_agent import audit_log as AL, scenarios as SC, web  # noqa: E402
from compliance_agent.clock import FixedClock  # noqa: E402

OUT = ROOT / "docs" / "360" / "evidence" / "audit-logs"
KB = ROOT / "data" / "CL_compliance.sqlite3"
LEDGER = ROOT / "data" / "CL_llm_experiment.sqlite3"
H = {"Content-Type": "application/json", "X-Requested-With": "compliance-ui", "X-HerBiz-Session": "sample-session"}
CALLS = [
    ("/api/ask?id=Q35", None),                                                            # recorded answer (replayed)
    ("/api/ask", {"q": "What penalty applies if I file my VAT return late?"}),            # allowed: v8 retrieval, validity 1.2
    ("/api/ask", {"q": "Is a medical clinic supply zero-rated for VAT?"}),                # warned: no question text kept
    ("/api/ask", {"q": "My customer Fatima, Emirates ID 784-1990-1234567-1, owes me AED 5,000 — do I charge VAT?"}),  # blocked
    ("/api/ask", {"q": "How do I renew my trade licence?"}),                              # out of scope: no passages
    ("/api/360/dashboard", {"profile_id": "SYN-AMAL-B"}),
    ("/api/360/ct?profile=SYN-AMAL-A", None),
    ("/api/360/finance", None), ("/api/360/finance.csv", None), ("/api/360/change", None),
]


def main() -> int:
    if not KB.exists():
        raise SystemExit("needs the local knowledge-base database (development repository only)")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        shutil.copyfile(KB, d / "w.sqlite3")
        logs = d / "audit-logs"
        app = web.App(d / "w.sqlite3", FixedClock("2026-10-17T10:00:00"), LEDGER if LEDGER.exists() else d / "none.sqlite3",
                      audit_dir=logs)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(app))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            for path, body in CALLS:
                req = urllib.request.Request(base + path, method="POST" if body is not None else "GET",
                                             data=json.dumps(body).encode() if body is not None else None, headers=H)
                try:
                    with urllib.request.urlopen(req) as r:
                        r.read()
                except urllib.error.HTTPError as ex:
                    with ex:
                        ex.read()
            for sid in ("SC-1", "SC-2", "SC-3"):
                SC.replay(sid, logs, "sample-session")
        finally:
            srv.shutdown(); srv.server_close(); app.engine.s.close()
        files = sorted(logs.glob("audit-*.jsonl"))
        for f in files:
            ok, msg = AL.verify(f)[:2]
            if not ok:
                raise SystemExit(f"chain check failed: {msg}")
        findings = AL.scan(logs)
        if findings:
            raise SystemExit(f"scanner findings, nothing written: {findings[:3]}")
        OUT.mkdir(parents=True, exist_ok=True)
        for old in OUT.glob("audit-*.jsonl"):
            old.unlink()
        counts = {}
        for f in files:
            shutil.copyfile(f, OUT / f.name)
            for line in f.read_bytes().splitlines():
                ch = json.loads(line)["channel"]
                counts[ch] = counts.get(ch, 0) + 1
    print(f"wrote {len(files)} file(s), {sum(counts.values())} records {counts}; chain intact; scan clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
