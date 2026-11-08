"""Export the recorded VAT answers used by the HerBiz 360 demo into one JSON file (Workstream A; read-only; no AI call).

For the history-free submission export, which has no experiment ledger and no database. Copies, for each demo question
only, the ledger row that ask.Asker replays (latest successful Sonnet answer) and the official passages it cites, so the
replayed screen is byte-for-byte the same (test 119). The file quotes official FTA texts; whether it may be published is
a founder decision (reuse terms D4), so the export keeps it in a separate hold folder by default.

    python3 experiments/ws_a/CL_export_recorded_answers.py --out <file>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from compliance_agent import ask  # noqa: E402
from compliance_agent.mvp360 import adapter  # noqa: E402

AUTH = ROOT / "data" / "CL_compliance.sqlite3"


def demo_ids() -> list[str]:
    ids = [q for q, _, _ in ask.DEMO_EXAMPLES]
    for q in adapter.content().get("vat_questions", []):
        qid = q if isinstance(q, str) else q.get("id")
        if qid and qid not in ids:
            ids.append(qid)
    return ids


def build(main_db: Path = AUTH) -> dict:
    a = ask.Asker(main_db)                                   # read-only (mode=ro) on the ledger and the database
    answers = {}
    for qid in demo_ids():
        if qid not in a.recorded:
            continue
        r = dict(a.recorded[qid])
        cites = json.loads(r["parsed_json"]).get("citations", [])
        r["passages"] = a._passages(sorted({c["passage_id"] for c in cites}))
        answers[qid] = r
    return {"_notice": ("Recorded model answers from earlier HerBiz test runs (no AI is called when they are replayed). "
                        "They quote official FTA texts; none has been checked by a qualified tax professional. "
                        "Not legal or tax advice."),
            "source": "data/CL_llm_experiment.sqlite3 (read-only) and the cited passages", "answers": answers}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = build()
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(data['answers'])} recorded answers -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
