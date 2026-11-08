"""Business profiles: validation, material missing facts and taxable-supply arithmetic.

Unknown stays unknown: a fact that is absent or null is never defaulted.
"""
from __future__ import annotations

import datetime as dt

KNOWN_JURISDICTIONS = {"AE-DU", "AE-SH", "AE-AJ", "AE-AZ", "AE-RK", "AE-FU", "AE-UQ"}

# Facts the engine knows about. type: str | bool | int | date | ledger | list
FACT_TYPES = {
    "jurisdiction": "str",                 # emirate code, e.g. AE-DU
    "licensing_context": "str",            # e.g. home_based_licence (provisional label; name of licence UNVERIFIED)
    "activity": "str",                     # e.g. graphic_design_services
    "activity_tags": "list",
    "licence_issue_date": "date",          # recorded, but never used to infer a renewal date
    "licence_expiry_date": "date",         # as printed on the licence document
    "employees": "int",
    "collects_customer_personal_data": "bool",
    "sells_online": "bool",
    "vat_registered": "bool",
    "ledger_last_12m": "ledger",           # list of {type, amount_aed, note}
    "expected_taxable_supplies_next_30d_aed": "int",
    # Added for the draft reading of Decree-Law Article 13/19 (real source). Unknown until the owner answers.
    "uae_place_of_residence": "bool",
    "concerned_goods_services_last_12m_aed": "int",          # imports / reverse-charge items (Article 19(2)); 0 if none
    "acquired_business_or_related_party_supplies": "bool",   # Article 19(3)-(4): needs a reviewer's calculation if true
}

# Material facts: without them no definitive obligation list is produced.
MATERIAL_FACTS = ["jurisdiction", "licensing_context", "activity"]

# Ledger line types. Only TAXABLE_SUPPLY types count towards taxable supplies.
# Costs (salaries, rent, purchases) are never supplies. Regression guard for the draft plan's error
# of adding payroll costs to turnover for a VAT registration test.
TAXABLE_SUPPLY_TYPES = {"sale_of_services", "sale_of_goods"}
NON_SUPPLY_TYPES = {"salary_cost", "rent_cost", "purchase_cost", "owner_drawings", "refund_paid", "loan_received"}


class ProfileError(ValueError):
    pass


def validate_profile(p: dict) -> dict:
    """Return a cleaned copy or raise ProfileError. Malformed input is refused, never repaired by guessing."""
    if not isinstance(p, dict):
        raise ProfileError("profile must be an object")
    for k in ("profile_id", "project_id", "business_id", "display_name"):
        if not isinstance(p.get(k), str) or not p[k].strip():
            raise ProfileError(f"missing or empty field: {k}")
    if p.get("synthetic") is not True:
        raise ProfileError("only synthetic profiles are accepted in this build (synthetic: true)")
    facts = p.get("facts", {})
    if not isinstance(facts, dict):
        raise ProfileError("facts must be an object")
    clean: dict = {}
    for k, v in facts.items():
        if k not in FACT_TYPES:
            raise ProfileError(f"unknown fact: {k}")
        if v is None:
            continue  # unknown stays unknown
        t = FACT_TYPES[k]
        if t == "str" and not (isinstance(v, str) and v.strip()):
            raise ProfileError(f"{k} must be text")
        if t == "bool" and not isinstance(v, bool):
            raise ProfileError(f"{k} must be true or false")
        if t == "int" and (isinstance(v, bool) or not isinstance(v, int) or v < 0):
            raise ProfileError(f"{k} must be a whole number of 0 or more")
        if t == "list" and not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            raise ProfileError(f"{k} must be a list of text")
        if t == "date":
            try:
                dt.date.fromisoformat(v)
            except (TypeError, ValueError):
                raise ProfileError(f"{k} must be a date YYYY-MM-DD")
        if t == "ledger":
            if not isinstance(v, list):
                raise ProfileError(f"{k} must be a list of ledger lines")
            for i, line in enumerate(v):
                if not isinstance(line, dict) or not isinstance(line.get("type"), str):
                    raise ProfileError(f"{k}[{i}] needs a type")
                amt = line.get("amount_aed")
                if isinstance(amt, bool) or not isinstance(amt, (int, float)) or amt < 0:
                    raise ProfileError(f"{k}[{i}] amount_aed must be a number of 0 or more")
        clean[k] = v
    if "jurisdiction" in clean and clean["jurisdiction"] not in KNOWN_JURISDICTIONS:
        raise ProfileError(f"jurisdiction must be one of {sorted(KNOWN_JURISDICTIONS)}")
    out = {k: p[k] for k in ("profile_id", "project_id", "business_id", "display_name")}
    out["synthetic"] = True
    out["facts"] = clean
    return out


def missing_material_facts(facts: dict) -> list[str]:
    return [k for k in MATERIAL_FACTS if facts.get(k) is None]


def taxable_supplies(ledger: list[dict] | None) -> dict:
    """Sum taxable supplies only. Returns total (or None if unknown) plus what was excluded and why."""
    if ledger is None:
        return {"total_aed": None, "included": [], "excluded": [], "unknown_types": [], "basis": "ledger not supplied"}
    included, excluded, unknown = [], [], []
    for line in ledger:
        t = line["type"]
        if t in TAXABLE_SUPPLY_TYPES:
            included.append(line)
        elif t in NON_SUPPLY_TYPES:
            excluded.append({**line, "reason": f"{t} is a cost or non-supply item, not a taxable supply"})
        else:
            unknown.append(line)
    total = sum(float(x["amount_aed"]) for x in included)
    basis = "sum of sale_of_services and sale_of_goods lines; costs excluded"
    if unknown:
        return {"total_aed": None, "included": included, "excluded": excluded, "unknown_types": unknown,
                "basis": "cannot total: ledger has line types that need classification by a reviewer"}
    return {"total_aed": total, "included": included, "excluded": excluded, "unknown_types": [], "basis": basis}
