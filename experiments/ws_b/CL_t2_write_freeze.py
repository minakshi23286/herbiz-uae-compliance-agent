"""Task 2 B-4: write the code_freeze record BEFORE the single v10 run (commit, file sha256 values, configuration sha256, DB md5).
Refuses if the working tree has uncommitted changes in any frozen file, or if a record already exists.

    python3 experiments/ws_b/CL_t2_write_freeze.py --db data/CL_ws_b_exact_copy.sqlite3
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments" / "ws_b"))
import CL_t2_eval as EV  # noqa: E402
from compliance_agent.llm_lab import retrieve_v8 as V8  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    a = ap.parse_args(argv)
    if EV.FREEZE_RECORD.exists():
        raise SystemExit(f"REFUSED: {EV.FREEZE_RECORD.name} already exists; the freeze is written once")
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", *EV.REQUIRED_FROZEN], capture_output=True, text=True).stdout
    if dirty.strip():
        raise SystemExit(f"REFUSED: uncommitted changes in frozen files:\n{dirty}")
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    config = {"retrieval_version": V8.VERSION, "max_passages": V8.MAX_PASSAGES, "certify": V8.CERTIFY, "trigger_cap": V8.TRIGGER_CAP,
              "map_version": V8.MAP_VERSION, "lexicon_topics": sorted(V8.LEXICON), "generic_triggers": sorted(V8.GENERIC_TRIGGERS),
              "added_by_codes": sorted(set(V8.ADDED_BY.values())), "methods_for_v10": ["v8", "v7", "v5_search"]}
    cfg_bytes = json.dumps(config, sort_keys=True).encode("utf-8")
    rec = {"record": "WS-B Task 2 code freeze (B-4), written before the single v10 run", "written_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
           "commit": commit, "branch": "t2-ws-b",
           "files_sha256": {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in EV.REQUIRED_FROZEN},
           "config": config, "config_sha256": hashlib.sha256(cfg_bytes).hexdigest(),
           "db_md5": hashlib.md5(Path(a.db).read_bytes()).hexdigest(),
           "reproduce": "python3 experiments/ws_b/CL_t2_eval.py --db data/CL_ws_b_exact_copy.sqlite3 --methods v8 v7 v5_search "
                        "--sets v1 v2 v3 v4 v5 v6 v7 v8 v9 v10 --final --out docs/CL_evidence/ws_b/t2/CL_t2_v10_and_dev_metrics.json",
           "rule": "v10 runs once. No tuning after the run; any change needs a new independent set v11."}
    EV.FREEZE_RECORD.parent.mkdir(parents=True, exist_ok=True)
    EV.FREEZE_RECORD.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(EV.FREEZE_RECORD, hashlib.sha256(EV.FREEZE_RECORD.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
