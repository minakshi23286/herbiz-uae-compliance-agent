"""Personal-data intake gate (Domain B; founder approval D-088, with conditions). Offline, deterministic, no network.

The gate decides, BEFORE an owner's text reaches retrieval, logs or any downstream step, whether HerBiz will process it:
  allow  - process normally
  warn   - process, and show a caution (sensitive topic words; never blocks)
  block  - do NOT process, echo, search or log the text

Its rules come from the policy knowledge base (knowledge_base/policy/CL_policy_kb.json, table "controls"): only the
detectors listed there run, and every decision carries the control and clause ids that drove it. If the KB is missing,
corrupt, lacks a required control, or the input cannot be checked, the gate blocks (fail closed).

The result never contains the input text or any matched value; `log_record` holds identifiers only. Pattern checks catch
common UAE formats only. They miss names, addresses and unusual formats. The demo uses synthetic data only.
Not legal advice: PDPL principles are used as a design benchmark; applicability to HerBiz is not determined."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KB_PATH = ROOT / "knowledge_base" / "policy" / "CL_policy_kb.json"
MAX_CHARS = 10_000          # longer inputs are not checked piecemeal: they are blocked (fail closed)
FAIL_CONTROL = "CTRL-FAIL-CLOSED"

# ------------------------------------------------------------------ normalisation (bypass resistance)
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­᠎‎‏"), None)
_DASHES = re.compile("[\u2010-\u2015\u2212\ufe58\ufe63\uff0d]")     # hyphen/en/em dashes, minus signs -> "-"
_SEP_BETWEEN_DIGITS = re.compile(r"(?<=\d)[\s\-./_()]+(?=\d)")


def normalise(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)          # full-width digits/letters -> ASCII
    t = t.translate(_ZERO_WIDTH)
    t = "".join(str(unicodedata.decimal(ch)) if ch.isdigit() and unicodedata.category(ch) == "Nd" else ch for ch in t)   # any script's digits
    t = _DASHES.sub("-", t)
    return t


def squeeze(t: str) -> str:
    """Join digit groups split by spaces, dashes, dots, slashes, underscores, brackets or line breaks."""
    return _SEP_BETWEEN_DIGITS.sub("", t)


# ------------------------------------------------------------------ detectors (identifiers only; never return matches)
def _iban_ok(iban: str) -> bool:
    s = iban[4:] + iban[:4]
    num = "".join(str(int(c, 36)) for c in s)
    return int(num) % 97 == 1


def _emirates_id(t: str) -> bool:
    return re.search(r"(?<!\d)784\d{12}(?!\d)", squeeze(t)) is not None


def _iban_ae(t: str) -> bool:
    compact = re.sub(r"[\s\-]", "", t).upper()
    return any(_iban_ok(m) for m in re.findall(r"AE\d{21}", compact))


_PHONE_SEP = re.compile(r"(?<=\d)[\s\-()]+(?=\d)")        # phones: spaces, dashes, brackets only (not / or ., so dates stay dates)


def _uae_phone(t: str) -> bool:
    s = _PHONE_SEP.sub("", t.replace("(+", "+").replace("+ ", "+"))
    return re.search(r"(?:\+|(?<![\d/.])00)971\d{8,9}(?!\d)|(?<![\d/.])05\d{8}(?![\d/.])|(?<![\d/.])9715\d{8}(?!\d)", s) is not None


def _email(t: str) -> bool:
    return re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", t) is not None


def _passport(t: str) -> bool:
    return re.search(r"(passport|جواز)[^\n]{0,40}?\b[A-Za-z]{0,2}\d{6,9}\b", squeeze(t), re.I) is not None


_SENSITIVE = re.compile(r"\b(health|medical|diagnos\w*|illness|disability|pregnan\w*|religio\w*|criminal record|ethnic\w*|biometric)\b", re.I)


def _sensitive_words(t: str) -> bool:
    return _SENSITIVE.search(t) is not None


DETECTORS = {"emirates_id": _emirates_id, "iban_ae": _iban_ae, "uae_phone": _uae_phone, "email": _email,
             "passport": _passport, "sensitive_words": _sensitive_words}
ACTIONS = {"block", "warn", "log_ids_only", "block_on_error"}


class KBError(ValueError):
    pass


# ------------------------------------------------------------------ KB loading
def load(path: Path = KB_PATH) -> dict:
    """Load and validate the policy KB. Raises KBError on anything that would make the gate unreliable."""
    try:
        raw = Path(path).read_bytes()
        kb = json.loads(raw)
        if not isinstance(kb, dict) or not isinstance(kb.get("_meta"), dict):
            raise KBError("policy KB is not an object with _meta")
        for key in ("clauses", "controls"):
            if not isinstance(kb.get(key), list) or not all(isinstance(x, dict) for x in kb[key]):
                raise KBError(f"policy KB '{key}' must be a list of objects")
        clauses = {c.get("clause_id"): c for c in kb["clauses"]}
        controls = {c.get("control_id"): c for c in kb["controls"]}
    except KBError:
        raise
    except Exception as ex:                          # unreadable, invalid JSON, wrong shapes: never let it through
        raise KBError(f"policy KB unreadable: {type(ex).__name__}")
    problems = []
    for rc in kb.get("_meta", {}).get("required_controls", []) or ["<none listed>"]:
        if rc not in controls:
            problems.append(f"required control missing: {rc}")
    for cid, c in controls.items():
        if c.get("action") not in ACTIONS:
            problems.append(f"{cid}: unknown action")
        if c.get("action") in ("block", "warn", "block_on_error") and not (c.get("owner_message") or "").strip():
            problems.append(f"{cid}: owner_message required for action {c.get('action')}")
        if not isinstance(c.get("detector_ids", []), list) or not isinstance(c.get("clause_ids", []), list):
            problems.append(f"{cid}: detector_ids and clause_ids must be lists")
            continue
        for d in c.get("detector_ids", []):
            if d not in DETECTORS:
                problems.append(f"{cid}: unknown detector {d}")
        if not c.get("clause_ids"):
            problems.append(f"{cid}: no clause ids")
        for cl in c.get("clause_ids", []):
            if cl not in clauses:
                problems.append(f"{cid}: unknown clause {cl}")
    if problems:
        raise KBError("; ".join(problems))
    return {"version": kb["_meta"].get("version"), "sha256": hashlib.sha256(raw).hexdigest(),
            "clauses": copy.deepcopy(clauses), "controls": copy.deepcopy(controls)}


# ------------------------------------------------------------------ the gate
def _decision(action, controls, detectors, kb, message, failed=False):
    clause_ids = sorted({cl for c in controls for cl in (kb["controls"][c]["clause_ids"] if kb and c in kb["controls"] else [])})
    if failed and not clause_ids:
        clause_ids = ["HERBIZ-FAIL-CLOSED"]
    rec = {"action": action, "control_ids": sorted(controls), "detector_ids": sorted(detectors), "clause_ids": clause_ids,
           "kb_version": kb["version"] if kb else None, "kb_sha256": kb["sha256"] if kb else None}
    return {**rec, "process": action in ("allow", "warn"), "owner_message": message, "log_record": dict(rec)}


def policy_gate(text, kb: dict | None = None, kb_path: Path = KB_PATH) -> dict:
    """Decide whether HerBiz will process `text`. Never raises; never returns or logs the text."""
    fail_msg = "HerBiz could not check this input for personal details, so it was not processed. Please try again later."
    try:
        kb = kb if kb is not None else load(kb_path)
    except KBError:
        return _decision("block", [FAIL_CONTROL], [], None, fail_msg, failed=True)
    try:
        if FAIL_CONTROL in kb["controls"] and kb["controls"][FAIL_CONTROL].get("owner_message"):
            fail_msg = kb["controls"][FAIL_CONTROL]["owner_message"]
        if not isinstance(text, str) or len(text) > MAX_CHARS:
            return _decision("block", [FAIL_CONTROL], [], kb, fail_msg, failed=True)
        try:
            t = normalise(text)
            hits = {}                                    # control_id -> detector ids that fired
            for cid, c in kb["controls"].items():
                fired = [d for d in c.get("detector_ids", []) if DETECTORS[d](t)]
                if fired:
                    hits[cid] = fired
        except Exception:                                # any detector failure -> do not process
            return _decision("block", [FAIL_CONTROL], [], kb, fail_msg, failed=True)
        blocking = [c for c in hits if kb["controls"][c]["action"] == "block"]
        if blocking:
            dets = [d for c in blocking for d in hits[c]]
            msg = kb["controls"][blocking[0]].get("owner_message")
            return _decision("block", blocking + ["CTRL-NO-RAW-LOG"], dets, kb, msg)
        warning = [c for c in hits if kb["controls"][c]["action"] == "warn"]
        if warning:
            dets = [d for c in warning for d in hits[c]]
            return _decision("warn", warning, dets, kb, kb["controls"][warning[0]].get("owner_message"))
        return _decision("allow", [], [], kb, None)
    except Exception:                                    # malformed kb dict or any other fault: fail closed
        return _decision("block", [FAIL_CONTROL], [], None, fail_msg, failed=True)
