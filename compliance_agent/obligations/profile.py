"""HerBiz business profile (360): validation, unknowns, clarifications and facts for the rule evaluator. Standard library only.

Unknown stays unknown: null and "not_sure" are never defaulted. Malformed input is refused, never repaired by guessing.
Only synthetic profiles are accepted in this build.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from pathlib import Path

SCHEMA = json.loads((Path(__file__).parent / "profile_schema.json").read_text(encoding="utf-8"))
FIELDS = SCHEMA["fields"]
NOT_SURE = "not_sure"
NATURAL_FORMS = {"sole_establishment", "freelance_permit", "home_business_licence"}
JURIDICAL_FORMS = {"llc", "civil_company", "branch"}


class ProfileError(ValueError):
    pass


def _check(name: str, spec: dict, v):
    t = spec["type"]
    if t == "enum" and v not in spec["values"]:
        raise ProfileError(f"{name}: '{v}' is not one of {spec['values']}")
    if t == "text" and not (isinstance(v, str) and v.strip()):
        raise ProfileError(f"{name} must be text")
    if t == "list" and not (isinstance(v, list) and all(isinstance(x, str) and x for x in v)):
        raise ProfileError(f"{name} must be a list of text")
    if t == "list" and spec["requirement"] == "required" and not v:
        raise ProfileError(f"{name} must not be empty")
    if t == "bool" and not isinstance(v, bool):
        raise ProfileError(f"{name} must be true or false")
    if t in ("int", "amount") and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0):
        raise ProfileError(f"{name} must be a number of 0 or more")
    if t == "int" and not isinstance(v, int):
        raise ProfileError(f"{name} must be a whole number")
    if t == "date":
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                raise ValueError
            dt.date.fromisoformat(v)
        except (TypeError, ValueError):
            raise ProfileError(f"{name} must be a date YYYY-MM-DD")
    if t == "month_day":
        try:
            if not re.fullmatch(r"\d{2}-\d{2}", v):
                raise ValueError
            dt.date.fromisoformat(f"2024-{v}")
        except (TypeError, ValueError):
            raise ProfileError(f"{name} must be MM-DD")


def validate(p: dict) -> dict:
    """Return {'facts', 'unknown', 'missing_required', 'clarify'} or raise ProfileError."""
    if not isinstance(p, dict) or not isinstance(p.get("profile_id"), str) or not p["profile_id"].strip():
        raise ProfileError("profile_id is required")
    if p.get("synthetic") is not True:
        raise ProfileError("only synthetic profiles are accepted in this build (synthetic: true)")
    raw = p.get("fields", {})
    if not isinstance(raw, dict):
        raise ProfileError("fields must be an object")
    facts, unknown = {}, []
    for k, v in raw.items():
        if k not in FIELDS:
            raise ProfileError(f"unknown field: {k}")
        if v is None or v == NOT_SURE:
            unknown.append(k)
            continue
        _check(k, FIELDS[k], v)
        facts[k] = v
    # derived: person type from legal form (never from anything else)
    if "person_type" not in facts and facts.get("legal_form") in NATURAL_FORMS:
        facts["person_type"] = "natural_person"
    elif "person_type" not in facts and facts.get("legal_form") in JURIDICAL_FORMS:
        facts["person_type"] = "juridical_person"
    missing = [k for k, s in FIELDS.items() if s["requirement"] == "required" and k not in facts]
    clarify = []
    if "person_type" not in facts:
        clarify.append("person_type")
    if facts.get("has_employees") is True and "employees_count" not in facts:
        clarify.append("employees_count")
    # contradictions are asked about, never settled silently
    if facts.get("has_employees") is False and facts.get("employees_count", 0) > 0:
        clarify.append("employees_count")
    form = facts.get("legal_form")
    if raw.get("person_type") not in (None, NOT_SURE) and (
            (form in NATURAL_FORMS and facts["person_type"] != "natural_person") or (form in JURIDICAL_FORMS and facts["person_type"] != "juridical_person")):
        clarify.append("person_type")
    amt, band = facts.get("taxable_supplies_last_12m_aed"), facts.get("revenue_band_last_12m")
    if amt is not None and band:
        lo, _, hi = band.partition("-")
        if not (float(lo.rstrip("+")) <= amt <= (float(hi) if hi else float("inf"))):
            clarify.append("taxable_supplies_last_12m_aed")
    if facts.get("jurisdiction_type") == "designated_zone":
        clarify.append("jurisdiction_type")
    return {"facts": facts, "unknown": sorted(set(unknown) - set(missing)), "missing_required": missing, "clarify": clarify}


def question(field: str) -> str:
    return FIELDS.get(field, {}).get("question") or f"Please tell us: {field.replace('_', ' ')}"


def evaluator_facts(facts: dict, as_of: dt.date) -> dict:
    """Facts as the rule evaluator sees them. Bands become intervals; derived date facts use the injected date."""
    out = dict(facts)
    band = facts.get("revenue_band_last_12m")
    if "taxable_supplies_last_12m_aed" in v_conflicts(facts):
        out.pop("taxable_supplies_last_12m_aed", None)   # contradiction: neither value is trusted until clarified
        out.pop("revenue_band_last_12m", None)
    elif "taxable_supplies_last_12m_aed" not in out and band:
        lo, _, hi = band.partition("-")
        out["taxable_supplies_last_12m_aed"] = (float(lo.rstrip("+")), float(hi) if hi else float("inf"))
    if facts.get("licence_expiry_date"):
        out["days_until_licence_expiry"] = (dt.date.fromisoformat(facts["licence_expiry_date"]) - as_of).days
    if facts.get("vat_registration_status"):
        out["vat_registered"] = facts["vat_registration_status"] == "registered"
    return out


def v_conflicts(facts: dict) -> set:
    """Fields whose supplied values contradict each other (same checks as validate)."""
    amt, band = facts.get("taxable_supplies_last_12m_aed"), facts.get("revenue_band_last_12m")
    if amt is None or not band:
        return set()
    lo, _, hi = band.partition("-")
    return set() if float(lo.rstrip("+")) <= amt <= (float(hi) if hi else float("inf")) else {"taxable_supplies_last_12m_aed"}
