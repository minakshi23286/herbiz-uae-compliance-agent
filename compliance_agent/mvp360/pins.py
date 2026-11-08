"""Pinned, read-only access to Workstream B's engine and Workstream C's sources360 interface (HerBiz 360 MVP, WS A).

Nothing here edits WS B or WS C. Each pinned commit is exported with `git archive` from the shared object store into a
git-ignored cache (data/vendor360/<ws>_<commit>/) and run in a SEPARATE Python process, so B's and C's modules never mix
with A's. Every failure raises Unavailable; callers fail closed (show "unavailable", never a guess).

Vendored mode (history-free submission export): when vendor360/CL_VENDOR_MANIFEST.json exists, the pinned commits are
read from plain folders under vendor360/ instead of git. Every file is checked against the manifest's sha256 once per
process; a changed, missing or extra file raises Unavailable (never rebuilt, never trusted). The export holds no
database, so B's VAT source-validity check fails closed there (B's owner rows are unchanged by it; see test 118).
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tarfile
import hashlib
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "data" / "vendor360"
AUTHORITATIVE = ROOT / "data" / "CL_compliance.sqlite3"

B_COMMIT = "89dc2b9"        # t2-b-rc1 (A-4, D-101/D-102 interim candidate): engine fdbe131 + owner wording "HerBiz" (ws-b-demo-0.4), retrieve_v8; was fdbe131 (DV-002)
B_FIXTURE = "docs/360/demo/wsa/CL_WSA_DEMO_FIXTURE_v1.json"
B_FIXTURE_SHA256 = "d5e34672425e75aeca30af625e2cf7c147269edcc1e682b6f2fc3939d77517c3"   # = the committed .sha256 at t2-b-rc1 (ws-b-demo-0.4)
B_FIXTURE_CONTRACT = "ws-b-demo-0.4"
B_VALIDITY_PIN = "9b48966"      # WS C contract 1.1 export that B pins for VAT source validity
C_COMMIT = "aa50dd4"        # ws-c-source-intelligence: sources360 contract 0.2 (additive citation_chip; 0.1 introduced 37897a1)
C_CONTRACT = "0.2"
C_GATE_COMMIT = "e01c371"   # CR-29 / D-088: WS C personal-data intake gate. ONLY these files come from it; tax sources stay at C_COMMIT
C_GATE_FILES = ["compliance_agent/rag_c/policy_gate.py", "knowledge_base/policy/CL_policy_kb.json",
                "knowledge_base/policy/CL_ai_governance_references.json"]
C_KB_MANIFEST_COMMIT = "8f35b20"   # t2-c-rc2: KB manifest v0.2.1 (metadata only, D4 / D-089; link status; portal 1227/1972 "page loads, contents not yet checked"); was 79789fa v0.2.0 (DV-003)
C_KB_MANIFEST_FILES = ["kb_export/CL_HERBIZ_KB_MANIFEST.json", "kb_export/README.md"]
C_T2_COMMIT = "8f35b20"            # t2-c-rc2 (A-4, D-101 amended): WS C Task 2 data files only; C-5/C-6 outputs excluded; demo labels stay at C_COMMIT
C_T2_FILES = ["knowledge_base/t2/CL_source_validity_1.2.json", "knowledge_base/t2/CL_link_status.json",
              "fixtures/t2/CL_SC2_source_side.json", "fixtures/t2/CL_SC3_source_side.json"]
DEMO_AS_OF = "2026-10-17"   # fixed demo date: B's pinned validity data is from this day (B fails closed after 7 days)
SNAPSHOT_TEXT = "Demo source snapshot: 17 October 2026."    # founder approval 17 Oct 2026: fixed for 7 Nov demo and 10 Nov entry
SNAPSHOT_NOTE = ("This is the date HerBiz copied the official sources used in "
                 "this demo. It is not the date any law was published or amended, and it does not mean a qualified person has checked the law.")
SNAPSHOT_LOCK = ROOT / "docs" / "360" / "CL_DEMO_SNAPSHOT.lock.json"
TIMEOUT = 60

VENDOR_TREE = ROOT / "vendor360"          # only present in the submission export (never in the development repo)
VENDOR_MANIFEST = VENDOR_TREE / "CL_VENDOR_MANIFEST.json"
B_FIXTURE_SHA256_PUBLIC = "ad9b8e77114beba00e6fb2d8bf9947c4fc2f716045d35f9fd1bea1e40752348e"  # ws-b-demo-0.4 with the 8 origin paths scrubbed (WS B rule)
LOCAL_PATH = "<LOCAL_PATH>"
NO_DB_VALIDITY = ("validity_unavailable: this export contains no copy of the protected database, so the VAT source-validity "
                  "check cannot run and fails closed")


def vendored() -> bool:
    return VENDOR_MANIFEST.exists()


def fixture_sha256() -> str:
    """The fixture checksum this copy must have: the committed one, or WS B's path-scrubbed one in the export."""
    return B_FIXTURE_SHA256_PUBLIC if vendored() else B_FIXTURE_SHA256


def scrub_fixture(raw: bytes) -> bytes:
    """WS B's publication scrub (CL_HERBIZ_WSB_PUBLICATION_EXPORT_2026-10-17): each absolute local path, up to the first
    space or quote, becomes <LOCAL_PATH>. In this fixture only the 8 `origin` values contain one."""
    import re
    return re.sub(rb'/(?:Users|private)/[^\s"]+', LOCAL_PATH.encode(), raw)


class Unavailable(RuntimeError):
    pass


def _git(*args, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, timeout=TIMEOUT, **kw)


_LOCK = threading.Lock()
_CHECKED: set = set()


def export(commit: str, ws: str) -> Path:
    """Export a pinned commit read-only into the cache. The cache is re-verified (sha256 of the git archive) once per
    process, so a modified cache folder is rebuilt, never trusted. Never touches any worktree."""
    with _LOCK:
        try:
            return _vendored(commit, ws) if vendored() else _export(commit, ws)
        except OSError as ex:
            raise Unavailable(f"cache for {ws}@{commit} unusable: {ex}")


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _vendored(commit: str, ws: str) -> Path:
    dest = VENDOR_TREE / f"{ws}_{commit}"
    if dest in _CHECKED:
        return dest
    try:
        tree = json.loads(VENDOR_MANIFEST.read_text(encoding="utf-8"))["trees"][f"{ws}_{commit}"]
    except (KeyError, ValueError) as ex:
        raise Unavailable(f"vendor manifest has no usable entry for {ws}@{commit}: {ex}")
    files = tree["files"]
    for rel, meta in files.items():
        f = dest / rel
        if not f.is_file() or _sha_file(f) != meta["sha256"]:
            raise Unavailable(f"vendored {ws}@{commit} file does not match the manifest: {rel}")
    extra = [str(f.relative_to(dest)) for f in dest.rglob("*")
             if f.is_file() and "__pycache__" not in f.parts and str(f.relative_to(dest)) not in files]
    if extra:
        raise Unavailable(f"vendored {ws}@{commit} has files not in the manifest: {extra[:3]}")
    _CHECKED.add(dest)
    return dest


def _export(commit: str, ws: str) -> Path:
    dest = VENDOR / f"{ws}_{commit}"
    if dest in _CHECKED and (dest / ".complete").exists():
        return dest
    if _git("cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
        raise Unavailable(f"pinned {ws} commit {commit} is not in this repository")
    tar = _git("archive", commit)
    if tar.returncode != 0:
        raise Unavailable(f"git archive {commit} failed")
    digest = hashlib.sha256(tar.stdout).hexdigest()
    marker = dest / ".complete"
    if marker.exists() and marker.read_text().split()[-1:] == [digest] and _files_match(dest, tar.stdout):
        _CHECKED.add(dest)
        return dest
    tmp = dest.with_name(dest.name + ".partial")
    shutil.rmtree(tmp, ignore_errors=True)        # only ever our own partial cache folder
    tmp.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as t:
        t.extractall(tmp, filter="data")
    if ws == "ws_b":
        # B's pinned validity check requires a byte-identical copy of the authoritative DB (read, never written)
        (tmp / "data").mkdir(exist_ok=True)
        shutil.copyfile(AUTHORITATIVE, tmp / "data" / "CL_compliance.sqlite3")
    (tmp / ".complete").write_text(f"{commit} {digest}")
    shutil.rmtree(dest, ignore_errors=True)
    tmp.rename(dest)
    _CHECKED.add(dest)
    return dest


def _files_match(dest: Path, tar_bytes: bytes) -> bool:
    """Every file in the cache must equal the committed file (detects edits to cached engine or persona files)."""
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as t:
        for m in t.getmembers():
            if m.isfile():
                f = dest / m.name
                if not f.exists() or f.read_bytes() != t.extractfile(m).read():
                    return False
    return True


_B_RUNNER = r"""
import sys, json, datetime as dt
root = sys.argv[1]; sys.path.insert(0, root)
from compliance_agent.obligations import engine as E, validity as V
req = json.load(sys.stdin)
if req.get("no_db"):      # vendored export: no database copy, so B's own fail-closed validity object
    sv = V.SV.ValiditySource(error=req["no_db"], origin="vendored export (no database)")
else:
    sv = V.load_pinned(root + "/data/CL_compliance.sqlite3", c_repo=req["c_repo"], today=req["as_of"])
out = E.assess(req["profile"], sv, dt.date.fromisoformat(req["as_of"]), "blocked")
out["_wording_violations"] = E.wording_violations(out)
out["owner_rows"] = [E.owner_row(r) for r in out["obligations"]]      # B's own owner projection (same as its fixture)
print(json.dumps(out, default=str))
"""

_C_RUNNER = r"""
import sys, json
root = sys.argv[1]; sys.path.insert(0, root)
from compliance_agent.rag_c import sources360 as S
req = json.load(sys.stdin)
data = S.load()
obl = {k: {"sources": v.get("sources", []), "title": v["title"], "domain": v["domain"], "mode": v["mode"]}
       for k, v in data["obligations"].items()}
labels = {k: S.obligation_label(data, k, req["as_of"], profile_synthetic=req["synthetic"]) for k in data["obligations"]}
srcs = {k: {"title": v["title"], "authority": v["issuing_authority"], "url": v["official_url"],
            "evidence_level": v["evidence_level"], "retrieved_at": v.get("retrieved_at"), "review_status": v["review_status"]}
        for k, v in data["sources"].items()}
print(json.dumps({"contract": S.CONTRACT_VERSION, "obligations": obl, "labels": labels, "sources": srcs}))
"""


def _run(code: str, root: Path, payload: dict) -> dict:
    p = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(root)], input=json.dumps(payload), capture_output=True,
                       text=True, timeout=TIMEOUT, cwd=str(root))
    if p.returncode != 0:
        raise Unavailable((p.stderr or "runner failed").strip().splitlines()[-1][:300])
    try:
        return json.loads(p.stdout)
    except ValueError as ex:
        raise Unavailable(f"runner output is not JSON: {ex}")


_CACHE: dict = {}     # deterministic inputs -> identical outputs; keeps the demo fast and repeatable


def _cached(key: str, fn):
    if key not in _CACHE:
        if len(_CACHE) > 200:
            _CACHE.clear()
        _CACHE[key] = fn()
    return json.loads(json.dumps(_CACHE[key]))     # a fresh copy: callers can never change the cached result


def run_b(profile: dict, as_of: str = DEMO_AS_OF) -> dict:
    root = export(B_COMMIT, "ws_b")
    key = "b|" + as_of + "|" + json.dumps(profile, sort_keys=True)
    payload = {"profile": profile, "as_of": as_of, "c_repo": str(ROOT), "no_db": NO_DB_VALIDITY if vendored() else None}
    return _cached(key, lambda: _run(_B_RUNNER, root, payload))


def run_c(synthetic: bool, as_of: str = DEMO_AS_OF) -> dict:
    root = export(C_COMMIT, "ws_c")
    return _cached(f"c|{as_of}|{synthetic is True}", lambda: _run(_C_RUNNER, root, {"synthetic": synthetic is True, "as_of": as_of}))


def b_file(path: str) -> bytes:
    """A committed WS B file (fixture, persona data), read from the pinned export."""
    p = export(B_COMMIT, "ws_b") / path
    if not p.exists():
        raise Unavailable(f"{path} not in WS B @ {B_COMMIT}")
    return p.read_bytes()


def c_file(path: str) -> dict:
    """A committed WS C evidence file, read from the pinned export."""
    p = export(C_COMMIT, "ws_c") / path
    if not p.exists():
        raise Unavailable(f"{path} not in WS C @ {C_COMMIT}")
    return json.loads(p.read_text(encoding="utf-8"))
