"""One-time run of the frozen independent set v4: frozen v5 code vs the v4-era retrieval (fcdfbb7). Offline, read-only copy.
Refuses to run if the v5 code hashes differ from the freeze record or the v4 set differs from its lock."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from compliance_agent.llm_lab import freeze, retrieval_metrics as M  # noqa: E402
from compliance_agent.llm_lab import retrieve as v5  # noqa: E402

FROZEN = {"compliance_agent/llm_lab/retrieve.py": "827876d4eda13ad8764b3d410ae2e5e1b72f5ef607562ce8886d5df15636f3ab",
          "compliance_agent/llm_lab/concepts_v5.py": "8eadc88009b870b9e2600f4860cf305df0067025abb826924c64b37798c05a49"}


def main(db: str, out: str, scratch: str) -> None:
    for f, h in FROZEN.items():
        if hashlib.sha256((ROOT / f).read_bytes()).hexdigest() != h:
            raise SystemExit(f"REFUSED: {f} changed after the code freeze")
    path = ROOT / "fixtures" / "CL_llm_eval_unseen_v4.json"
    freeze.verify(path)
    qs = json.loads(path.read_text())["questions"]
    old_src = Path(scratch) / "retrieve_v4_fcdfbb7.py"
    old_src.write_text(subprocess.check_output(["git", "-C", str(ROOT), "show", "fcdfbb7:compliance_agent/llm_lab/retrieve.py"], text=True))
    spec = importlib.util.spec_from_file_location("compliance_agent.llm_lab.retrieve_v4", old_src)
    v4 = importlib.util.module_from_spec(spec); v4.__package__ = "compliance_agent.llm_lab"; spec.loader.exec_module(v4)
    result = {}
    for label, mod in (("v4_retrieval_fcdfbb7", v4), ("v5_retrieval_a766a50", v5)):
        con = mod.connect_ro(db)
        ev = M.evaluate(qs, lambda t: mod.search(con, t))
        for row, q in zip(ev["rows"], qs):
            row["retrieved"] = [f'{p["source_id"]}|{p["locator"].split(",")[0]}|{p.get("added_by", "bm25")}' for p in mod.search(con, q["text"])]
            plain = [p["passage_id"] for p in mod.search(con, q["text"], heading_extra=0, core_pack=False)]
            row["bm25_prefix_unchanged"] = [p["passage_id"] for p in mod.search(con, q["text"])][:len(plain)] == plain
        result[label] = ev
        s = ev["summary"]
        print(label, {k: s[k] for k in ("any_expected", "all_required", "mrr", "median_first_rank", "irrelevant_added_share",
                                         "avg_passages", "added_on_no_source_questions", "misses_any", "misses_required")})
    result["set_sha256"] = freeze.sha(path)
    result["code_sha256"] = FROZEN
    Path(out).write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
