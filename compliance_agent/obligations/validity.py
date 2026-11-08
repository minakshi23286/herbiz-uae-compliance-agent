"""Source validity for the obligations engine, through Workstream C's contract v1.1 PINNED to a committed C revision.

C's package and validity export are taken from the pinned commit with `git archive` / `git show` into a throwaway folder
(C's working tree, which may hold uncommitted edits, is never used), then loaded with source_validity_c.load (unchanged).
Every failure fails closed: no certification is possible without a usable, current, same-build export.
"""
from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from ..llm_lab import source_validity_c as SV

C_REPO = Path(__file__).resolve().parents[3] / "CL_compliance_agent_app_ws_c"
PINNED_COMMIT = "9b48966"   # ws-c-source-intelligence, 17 Oct 2026 (HerBiz 360 package pointer; contract v1.1)


def load_pinned(db: str | Path, commit: str = PINNED_COMMIT, c_repo: str | Path = C_REPO, today: str | None = None) -> SV.ValiditySource:
    tmp = Path(tempfile.mkdtemp(prefix="ws_b_c_pinned_"))
    try:
        tar = subprocess.run(["git", "-C", str(c_repo), "archive", commit, "compliance_agent"], capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(tar)) as t:
            t.extractall(tmp, filter="data")   # refuses absolute paths, links outside tmp, devices
        export = subprocess.run(["git", "-C", str(c_repo), "show", f"{commit}:knowledge_base/CL_source_validity.json"],
                                capture_output=True, check=True).stdout
        (tmp / "knowledge_base").mkdir()
        (tmp / "knowledge_base" / "CL_source_validity.json").write_bytes(export)
        sv = SV.load(db, c_root=tmp, today=today)
    except Exception as e:
        return SV.ValiditySource(error=f"pinned WS-C artifacts unavailable ({commit}): {type(e).__name__}: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)   # the adapter has already imported and copied what it needs
    sv.origin = f"{c_repo}@{commit}"
    return sv
