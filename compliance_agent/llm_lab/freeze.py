"""Freeze guard for the independent unseen question set: the runner refuses to use it if its hash changed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNSEEN = ROOT / "fixtures" / "CL_llm_eval_unseen_v1.json"
LOCK = ROOT / "fixtures" / "CL_llm_eval_unseen_v1.FROZEN.json"


def sha(path: Path | None = None) -> str:
    return hashlib.sha256(Path(path or UNSEEN).read_bytes()).hexdigest()   # resolved at call time


def verify(path: Path | None = None) -> str:
    target = Path(path or UNSEEN)
    lock_file = target.with_name(target.stem + ".FROZEN.json")
    lock = json.loads(lock_file.read_text(encoding="utf-8"))
    now = sha(target)
    if now != lock["sha256"]:
        raise SystemExit(f"REFUSED: the frozen unseen set was modified (sha256 {now[:12]} != {lock['sha256'][:12]})")
    return now
