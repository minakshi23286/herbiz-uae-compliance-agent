"""Scripted end-to-end demo (synthetic). Runs every stage, closes the database, reopens it and prints the record.

    python3 -m compliance_agent.demo --db data/CL_demo_run.sqlite3
Refuses to run against an existing database file, so a previous run is never overwritten.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import MODE_LABEL, scenario
from .clock import FixedClock
from .engine import Engine
from .store import Store


def run(db: Path, clock_iso: str = "2026-10-16T10:00:00") -> dict:
    clock = FixedClock(clock_iso)
    e = Engine(Store(db), clock)
    log = []
    for sid, name, sys_step, human_step in scenario.STAGES:
        log.append(f"--- Stage {sid}: {name}")
        log += ["  " + l for l in sys_step(e)]
        clock.advance(minutes=5)
        if human_step:
            log += ["  " + l for l in human_step(e)]
            clock.advance(minutes=5)
    before = e.state()
    e.s.close()
    e2 = Engine(Store(db), clock)  # "restart"
    after = e2.state()
    summary = {
        "mode": MODE_LABEL,
        "log": log,
        "cases": [{k: c[k] for k in ("case_id", "kind", "status", "title", "due_date", "missing_evidence")} for c in after["cases"]],
        "assessments": [{k: a[k] for k in ("obligation_key", "result")} for a in after["assessments"]],
        "audit_events": len(e2.history(limit=100000)),
        "persisted_after_restart": [c["case_id"] + ":" + c["status"] for c in before["cases"]] == [c["case_id"] + ":" + c["status"] for c in after["cases"]],
    }
    e2.s.close()
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(Path(__file__).resolve().parent.parent / "data" / "CL_demo_run.sqlite3"))
    a = ap.parse_args(argv)
    db = Path(a.db)
    if db.exists():
        print(f"REFUSED: {db} exists. Choose a new --db path; earlier runs are kept as evidence.")
        return 2
    s = run(db)
    print("\n".join(s.pop("log")))
    print(json.dumps(s, indent=1, ensure_ascii=False))
    return 0 if s["persisted_after_restart"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
