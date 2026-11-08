"""Build the self-contained, history-free HerBiz 360 submission export (Workstream A). Local only: publishes nothing.

    python3 experiments/ws_a/CL_build_submission_export.py --out <new folder> --hold <new folder> [--ref HEAD]

- Takes the approved files of the integration branch with `git archive` (no history, so no commit author e-mails).
- Vendors WS B (fdbe131) and WS C (aa50dd4) as plain folders under vendor360/, with a sha256 manifest; the app checks
  every file before use (compliance_agent/mvp360/pins.py, vendored mode). Never touches the B or C worktrees.
- Replaces absolute local paths with <LOCAL_PATH> (WS B's rule) and lists every changed file in the manifest.
- Holds back what may not be redistributed yet: databases, raw official files, the experiment ledger. The recorded VAT
  answers (they quote official texts; reuse terms D4 unconfirmed) go to the separate --hold folder, never the export.
- Refuses an output folder inside this repository, inside a WS B / WS C worktree, or one that already has content.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from compliance_agent.mvp360 import pins as P  # noqa: E402

PROTECTED_DIRS = [ROOT, ROOT.parent / "CL_compliance_agent_app_ws_b", ROOT.parent / "CL_compliance_agent_app_ws_c"]

INCLUDE = ["compliance_agent/", "contracts/", "capabilities.json", "tests/", "fixtures/", "knowledge_base/", "experiments/ws_a/", "experiments/ws_b/",
           "experiments/llm/", "docs/360/", "docs/CL_evidence/", "docs/rag/", "docs/CL_ARCHITECTURE_AND_DATA.md",
           "docs/CL_EVALUATION_REPORT.md", ".gitignore", ".env.example", "requirements-optional.txt",
           "kb_export/"]
EXCLUDE = [
    ("docs/CL_evidence/ws_c/360/board/", "internal advisory-board reviews"),
    ("docs/CL_evidence/ws_c/360/board2/", "internal advisory-board reviews"),
    ("docs/360/submission/CL_HERBIZ360_SUBMISSION_PACKAGE.md", "internal submission checklist (founder tasks)"),
    ("docs/360/CL_RC3_CHANGE_LIST_PROPOSAL.md", "internal planning: rc3 change list"),
    ("docs/360/CL_HERBIZ360_READINESS_DASHBOARD.md", "internal planning: readiness dashboard"),
    ("docs/360/submission/CL_HERBIZ360_FOUNDER_WALKTHROUGH.md", "internal usability kit"),
    ("docs/360/submission/CL_HERBIZ360_PITCH_VIDEO_STORYBOARD.md", "internal pitch script"),
    ("docs/360/submission/CL_HERBIZ360_TECHNICAL_REPORT.", "draft report; the final report is submitted separately"),
    ("docs/360/CL_HERBIZ360_DEMO_SCRIPTS.md", "superseded internal script"),
    ("docs/360/export/", "export README (copied to README.md) and internal export reports"),
    ("docs/360/CL_HERBIZ360_INTEGRATION_REPORT.md", "internal integration report (advisory-board passes, decision references)"),
    ("docs/360/CL_WSB_360_RECONCILIATION_AND_PLAN_ADDENDUM.md", "internal plan (capacity, board dissent)"),
    ("docs/rag/CL_FTA_ENQUIRY_G1_DRAFT_2026-10-16.md", "unsent draft enquiry to a government authority"),
    ("docs/rag/360/CL_HERBIZ_360_08_BOARD_REVIEW.md", "internal advisory-board review"),
    ("docs/rag/360/CL_HERBIZ_360_FOUNDER_DECISION_REPORT.md", "internal founder decision report"),
    ("docs/rag/360/CL_HERBIZ_360_06_MVP_ROADMAP_BACKLOG.md", "internal roadmap and capacity notes"),
    ("docs/rag/360/CL_HERBIZ_360_04_FIRECRAWL_PLAN.md", "internal paid-tool plan (credits)"),
    ("docs/rag/CL_HERBIZ_FIRECRAWL_TRIAL_PLAN.md", "internal paid-tool trial plan (credits)"),
    ("docs/rag/CL_HERBIZ_FIRECRAWL_TRIAL_REPORT.md", "internal paid-tool trial report (credits)"),
    ("docs/rag/CL_HERBIZ_RAG_OVERNIGHT_REPORT.md", "internal session report"),
    ("docs/rag/CL_HERBIZ_CLAUDE_TOOLS_ASSESSMENT.md", "internal tool and subscription assessment"),
    ("docs/rag/CL_WS_B_REQUESTS_TO_WS_C.md", "internal workstream correspondence"),
    ("docs/CL_evidence/ws_c/qa/CL_QA_database.md", "internal QA note labelled with another business line"),
    ("compliance_agent/llm_lab/data/CL_article_index_v6.json", "HELD: contains the opening text of official articles (reuse terms unconfirmed); "
                                                              "regenerate with experiments/ws_b/CL_build_v6_tables.py after rebuilding the knowledge base"),
]
HOLD_FROM_REPO = ["compliance_agent/llm_lab/data/CL_article_index_v6.json"]   # copied to --hold, never to the export
VENDOR_EXCLUDE = {"compliance_agent/llm_lab/data/CL_article_index_v6.json"}
DATA_README = b"""# data/ (empty in this snapshot)

The app keeps its local working files here, for example `CL_test_workspace.sqlite3`, which is created on first start.
This snapshot ships no database, no official FTA files (`raw/`) and no experiment ledger. See README.md, sections 5 and 6.
"""
# Pinned dependency subsets: only what the app and its tests read from each pinned commit.
VENDOR = {
    ("ws_b", P.B_COMMIT): ["compliance_agent/", "fixtures/obligations/", "docs/360/demo/wsa/"],
    ("ws_c", P.C_COMMIT): ["compliance_agent/", "knowledge_base/", "docs/CL_evidence/ws_c/360/mvp/CL_sbr_amendment_impact_2026-10-17.json"],
    ("ws_c", P.C_GATE_COMMIT): list(P.C_GATE_FILES),                 # CR-29 gate files only
}
PATH_RE = re.compile(rb'/(?:Users|private)/[^\s"\'`)<>]+')
TEXT_EXT = {".py", ".md", ".json", ".txt", ".csv", ".html", ".svg", ".sha256", ".lock", ".example", ""}


def git(*args) -> bytes:
    p = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True)
    return p.stdout


def members(ref: str) -> dict[str, bytes]:
    out = {}
    with tarfile.open(fileobj=io.BytesIO(git("archive", ref))) as t:
        for m in t.getmembers():
            if m.isfile():
                out[m.name] = t.extractfile(m).read()
    return out


def picked(name: str, prefixes: list[str]) -> bool:
    return any(name == p or (p.endswith("/") and name.startswith(p)) or (p.endswith(".") and name.startswith(p)) for p in prefixes)


def scrub(name: str, data: bytes) -> tuple[bytes, int]:
    if Path(name).suffix not in TEXT_EXT:
        return data, 0
    new, n = PATH_RE.subn(P.LOCAL_PATH.encode(), data)
    return new, n


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def safe_target(p: Path) -> Path:
    p = p.resolve()
    for d in PROTECTED_DIRS:
        if p == d.resolve() or d.resolve() in p.parents:
            raise SystemExit(f"refused: {p} is inside a protected workstream folder ({d.name})")
    if p.exists() and any(p.iterdir()):
        raise SystemExit(f"refused: {p} already has content; choose a new folder")
    return p


def write(base: Path, rel: str, data: bytes) -> None:
    f = base / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)


def build(out: Path, hold: Path, ref: str) -> dict:
    out, hold = safe_target(out), safe_target(hold)
    commit = git("rev-parse", ref + "^{commit}").decode().strip()     # a tag name resolves to its commit, never the tag object
    files, excluded, changed = {}, [], []
    tracked = members(ref)
    for name, data in sorted(tracked.items()):
        reason = next((r for p, r in EXCLUDE if picked(name, [p])), None)
        if name.endswith((".sqlite3", ".sqlite", ".db")):
            reason = "database file: no database is published (synthetic demo-run state; regenerate with the classic demo)"
        if not picked(name, INCLUDE) or reason:
            excluded.append({"path": name, "reason": reason or "not on the export allow-list (internal handoff, plan or record)"})
            continue
        if name == P.B_FIXTURE:                            # same bytes as the vendored, scrubbed WS B copy (below)
            pub = P.scrub_fixture(data)
            changed.append({"path": name, "local_paths_replaced": len(re.findall(rb'/(?:Users|private)/[^\s"]+', data)),
                            "committed_sha256": sha(data), "note": "WS B scrub rule; identical to vendor360 copy"})
            data = pub
        new, n = scrub(name, data)
        if n:
            changed.append({"path": name, "local_paths_replaced": n, "committed_sha256": sha(data)})
        files[name] = new
    if "capabilities.json" in files:                     # A-5: declare the exact exported commit
        cap = json.loads(files["capabilities.json"])
        if cap["build"]["integration_commit"] != commit[:7]:
            old_sha = sha(files["capabilities.json"])
            cap["build"]["integration_commit"] = commit[:7]
            files["capabilities.json"] = (json.dumps(cap, indent=1, ensure_ascii=False) + "\n").encode()
            changed.append({"path": "capabilities.json", "local_paths_replaced": 0, "committed_sha256": old_sha,
                            "note": "build.integration_commit set to the exported commit"})
    files["README.md"] = tracked["docs/360/export/CL_EXPORT_README.md"]      # from the same commit, not the working tree
    files["data/CL_DATA_README.md"] = DATA_README
    # WS B's fixture checksum file must describe the scrubbed fixture (as in WS B's own publication export)
    fx = P.B_FIXTURE
    if fx in files:
        old = files.get(fx + ".sha256", b"")
        files[fx + ".sha256"] = (sha(files[fx]) + "  " + Path(fx).name + "\n").encode()
        changed.append({"path": fx + ".sha256", "local_paths_replaced": 0, "committed_sha256": sha(old),
                        "note": "rewritten to the checksum of the scrubbed fixture"})
    trees = {}
    for (ws, c), prefixes in VENDOR.items():
        full = git("rev-parse", c + "^{commit}").decode().strip()
        tf = {}
        for name, data in sorted(members(c).items()):
            if not picked(name, prefixes) or name in VENDOR_EXCLUDE:
                continue
            committed = sha(data)
            note = None
            if ws == "ws_b" and name == fx:
                data, note = P.scrub_fixture(data), "8 absolute local paths in origin values replaced with <LOCAL_PATH> (WS B rule)"
            elif ws == "ws_b" and name == fx + ".sha256":
                data, note = (P.B_FIXTURE_SHA256_PUBLIC + "  " + Path(fx).name + "\n").encode(), "checksum of the scrubbed fixture"
            else:
                data, n = scrub(name, data)
                note = f"{n} absolute local paths replaced with <LOCAL_PATH>" if n else None
            write(out / "vendor360" / f"{ws}_{c}", name, data)
            tf[name] = {"sha256": sha(data), **({"committed_sha256": committed, "change": note} if note else {})}
        trees[f"{ws}_{c}"] = {"workstream": ws, "commit": full, "branch": "ws-b-retrieval" if ws == "ws_b" else "ws-c-source-intelligence",
                               "subset": prefixes, "files": tf}
    if sha(Path(out / "vendor360" / f"ws_b_{P.B_COMMIT}" / fx).read_bytes()) != P.B_FIXTURE_SHA256_PUBLIC:
        raise SystemExit("scrubbed WS B fixture does not match WS B's published checksum")
    for name, data in files.items():
        write(out, name, data)
    vm = {"_notice": "Pinned WS B / WS C dependencies, vendored as plain files for a history-free export. The app checks "
                     "every file against this manifest before use and refuses on any difference.",
          "created": dt.date.today().isoformat(), "from_repository_commit": commit, "trees": trees}
    write(out, "vendor360/CL_VENDOR_MANIFEST.json", (json.dumps(vm, indent=1, sort_keys=True) + "\n").encode())
    # recorded VAT answers: held back by default (they quote official texts; reuse terms unconfirmed)
    sys.path.insert(0, str(ROOT / "experiments" / "ws_a"))
    import CL_export_recorded_answers as R
    rec = R.build()
    for name in HOLD_FROM_REPO:
        write(hold, name, tracked[name])
    write(hold, "fixtures/mvp360/CL_recorded_vat_answers.json",
          (json.dumps(rec, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode())
    return {"commit": commit, "files": files, "excluded": excluded, "changed": changed, "trees": trees,
            "recorded": sorted(rec["answers"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--hold", required=True)
    ap.add_argument("--ref", default="HEAD")
    a = ap.parse_args(argv)
    r = build(Path(a.out), Path(a.hold), a.ref)
    manifest = {"_notice": "HerBiz 360 submission export: every file with its sha256. Prepared locally; not published.",
                "from_repository_commit": r["commit"], "built": dt.date.today().isoformat(),
                "files": {n: sha(d) for n, d in sorted(r["files"].items())},
                "local_paths_replaced": r["changed"], "excluded_from_export": r["excluded"],
                "held_back_separately": {"fixtures/mvp360/CL_recorded_vat_answers.json": "recorded VAT answers " + ", ".join(r["recorded"]),
                                         "compliance_agent/llm_lab/data/CL_article_index_v6.json": "opening text of official articles (retrieval scorer table)"},
                "not_included": ["data/*.sqlite3 (protected database, workspace copies, experiment ledger)",
                                 "data/raw/ (official FTA files; rebuild with the collector)", "git history"]}
    write(Path(a.out).resolve(), "CL_EXPORT_FILE_MANIFEST.json", (json.dumps(manifest, indent=1) + "\n").encode())
    print(json.dumps({"commit": r["commit"], "files": len(r["files"]), "excluded": len(r["excluded"]),
                      "paths_scrubbed_files": len(r["changed"]), "vendored": {k: len(v["files"]) for k, v in r["trees"].items()},
                      "held_recorded_answers": r["recorded"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
