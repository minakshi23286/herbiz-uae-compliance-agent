"""360 source-citation and uncertainty interface (championship MVP). Read-only.

Gives Workstream B's obligations dashboard, for each candidate obligation:
- the official sources behind it, with evidence level and retrieval date;
- the open gaps;
- one uncertainty indicator;
- plain user wording.

It also maps monitor alerts to affected obligations (impact analysis).

It holds NO applicability rules. Corporate-tax obligations are marked `substantive_rule_allowed: false`: the founder's
restriction (17 Oct 2026) allows only synthetic demonstration scenarios until a qualified corporate-tax reviewer approves
them (D3-CT). Nothing here is ever release-approved. Approval of a 360 source is not supported in this version: the
loader refuses any source marked approved or activated.

VAT keeps using interface.py (contract 1.1). This module has its own contract version, so B's 1.1 loader is unaffected."""
from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

from .discovery import norm_url
from .register import REGISTER

CONTRACT_VERSION = "0.2"   # 0.2 (17 Oct 2026): additive citation_chip; user_wording in short sentences
ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "knowledge_base" / "CL_360_source_candidates.json"
OBLIGATIONS = ROOT / "knowledge_base" / "CL_360_obligation_sources.json"

# Weakest first. "secondary" exists only so the loader can name it when it refuses it (never relied on).
EVIDENCE_ORDER = ("unresolved", "secondary", "snippet_only", "observed_listing_only", "observed")
ALLOWED_EVIDENCE = ("unresolved", "snippet_only", "observed_listing_only", "observed")
# "low" is reserved for reviewer-approved sources, which contract 0.1 cannot hold: an unreviewed source is never "low".
UNCERTAINTY = {"unresolved": "high", "snippet_only": "medium", "observed_listing_only": "medium", "observed": "medium"}
DOMAINS = ("vat", "corporate_tax", "bookkeeping", "e_invoicing", "licensing", "beneficial_ownership", "employment",
           "economic_substance", "free_zone")
GAP_STATES = ("open", "partly_resolved", "resolved", "blocked")
IMPACT_LEVELS = ("high", "medium", "low")
# VAT register gaps carry free-text status only; their impact level is fixed here (both block certification today).
REGISTER_GAP_IMPACT = {"G1": "high", "G3": "high"}
STALE_DAYS = 30          # a source not re-checked for 30 days is shown as stale (monitoring cadence: weekly or daily)
DISCLAIMER = "Not legal, tax or accounting advice. Not reviewed by a qualified professional. Not a compliance decision."
# Display text for each citation, so the UI never derives it (contract 0.2). Nothing in contract 0.2 can be reviewed.
CITATION_CHIP = {"observed": "Source found, not reviewed", "observed_listing_only": "Source listed, not opened or reviewed",
                 "snippet_only": "Source excerpt only, not reviewed", "unresolved": "Source not located"}
DEMO_PREFIX = "Demo scenario (fictional business)"


class Invalid(ValueError):
    pass


def _iso(value) -> bool:
    try:
        dt.date.fromisoformat(str(value)[:10]); return True
    except ValueError:
        return False


def _register(register_path: Path) -> tuple[dict, set]:
    """VAT register gaps (normalised to state/impact_level) and every source/candidate id it knows."""
    try:
        reg = json.loads(Path(register_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, set()
    gaps = {}
    for g in reg.get("gaps", []):
        st = str(g.get("status") or "open").lower()
        gaps[g["id"]] = {"id": g["id"], "what": g.get("what", ""), "state": st if st in GAP_STATES else "open",
                         "impact_level": REGISTER_GAP_IMPACT.get(g["id"], "medium"), "from": "VAT register"}
    ids = {x["source_id"] for x in reg.get("sources", [])} | {c["candidate_id"] for c in reg.get("candidates", [])}
    return gaps, ids


def _is_ct(source_id: str, source: dict | None) -> bool:
    return str(source_id).startswith("CT-") or (source or {}).get("domain") == "corporate_tax"


def load(sources_path: Path = SOURCES, obligations_path: Path = OBLIGATIONS, register_path: Path = REGISTER) -> dict:
    """Load and validate both files. Raises Invalid on anything that could overstate a source or let a corporate-tax
    item act as a rule."""
    src = json.loads(Path(sources_path).read_text(encoding="utf-8"))
    obl = json.loads(Path(obligations_path).read_text(encoding="utf-8"))
    problems, by_id = [], {}
    for s in src.get("sources", []):
        sid = s.get("source_id")
        if sid in by_id:
            problems.append(f"duplicate source {sid}")
        by_id[sid] = s
        if s.get("approved") is not False or s.get("activated") is not False:
            problems.append(f"{sid}: approved/activated must be false (no 360 approval route in contract {CONTRACT_VERSION})")
        if s.get("evidence_level") not in ALLOWED_EVIDENCE:
            problems.append(f"{sid}: evidence level {s.get('evidence_level')!r} not allowed (secondary sources are never relied on)")
        if s.get("domain") not in DOMAINS:
            problems.append(f"{sid}: unknown domain {s.get('domain')!r}")
        if s.get("content_stored") is not False:
            problems.append(f"{sid}: content_stored must be false until reuse terms are cleared (D4)")
        if s.get("evidence_level") != "unresolved" and not (s.get("official_url") or "").startswith(("http", "see ")):
            problems.append(f"{sid}: official_url missing")
        if s.get("retrieved_at") is not None and not _iso(s["retrieved_at"]):
            problems.append(f"{sid}: retrieved_at {s['retrieved_at']!r} is not an ISO date")
    reg_gaps, reg_ids = _register(register_path)
    gaps = dict(reg_gaps)
    for g in src.get("gaps", []):
        if g.get("state") not in GAP_STATES or g.get("impact_level") not in IMPACT_LEVELS:
            problems.append(f"gap {g.get('id')}: state must be one of {GAP_STATES} and impact_level one of {IMPACT_LEVELS}")
        gaps[g["id"]] = g
    seen = set()
    for o in obl.get("obligations", []):
        oid = o.get("obligation_id")
        if oid in seen:
            problems.append(f"duplicate obligation {oid}")
        seen.add(oid)
        if o.get("domain") not in DOMAINS:
            problems.append(f"{oid}: unknown domain {o.get('domain')!r}")
        for field in ("title", "mode"):
            if not o.get(field):
                problems.append(f"{oid}: {field} is required")
        if o.get("substantive_rule_allowed") is not False:
            problems.append(f"{oid}: substantive_rule_allowed must be false until the domain reviewer approves")
        ct = o.get("domain") == "corporate_tax" or str(oid).startswith("CT-")
        if ct and ("D3-CT" not in str(o.get("reviewer")) or o.get("mode") != "synthetic scenario only"):
            problems.append(f"{oid}: corporate tax must be 'synthetic scenario only' with reviewer D3-CT (founder restriction)")
        if any(_is_ct(x, by_id.get(x)) for x in o.get("sources", [])) and "D3-CT" not in str(o.get("reviewer")):
            problems.append(f"{oid}: cites a corporate-tax source, so it needs reviewer D3-CT whatever its domain label")
        for sid in o.get("sources", []):
            if sid not in by_id:
                problems.append(f"{oid}: unknown source {sid}")
        for sid in o.get("vat_register_sources", []):
            if sid not in reg_ids:
                problems.append(f"{oid}: unknown VAT register source {sid}")
        for gid in o.get("gaps", []):
            if gid not in gaps:
                problems.append(f"{oid}: unknown gap {gid}")
    if problems:
        raise Invalid("; ".join(problems))
    return copy.deepcopy({"contract": CONTRACT_VERSION, "sources": by_id,
                          "obligations": {o["obligation_id"]: o for o in obl["obligations"]}, "gaps": gaps})


def _age_days(retrieved_at: str | None, as_of: str) -> int | None:
    if not retrieved_at:
        return None
    return (dt.date.fromisoformat(as_of) - dt.date.fromisoformat(retrieved_at[:10])).days


def cites_corporate_tax(data: dict, o: dict) -> bool:
    return (o.get("domain") == "corporate_tax" or str(o.get("obligation_id", "")).startswith("CT-")
            or any(_is_ct(x, data["sources"].get(x)) for x in o.get("sources", [])))


def obligation_label(data: dict, obligation_id: str, as_of: str | None = None, profile_synthetic: bool | None = None) -> dict:
    """Citations, open gaps, one uncertainty indicator and user wording for one obligation. Never release-approved.
    Anything resting on corporate-tax sources is shown ONLY for a synthetic (fictional) profile: callers must pass
    profile_synthetic=True, otherwise the label refuses (founder restriction: no CT rules without qualified review)."""
    as_of = as_of or dt.date.today().isoformat()
    o = data["obligations"].get(obligation_id)
    if o is not None and cites_corporate_tax(data, o) and profile_synthetic is not True:
        return {"obligation_id": obligation_id, "known": True, "shown": False, "release_approved": False, "uncertainty": "high",
                "refused": "corporate_tax_real_profile",
                "user_wording": f"{DISCLAIMER} HerBiz shows corporate tax only in demonstration scenarios for fictional businesses. "
                                "Check with the FTA or an FTA-registered tax agent.", "contract": CONTRACT_VERSION}
    if o is None:
        return {"obligation_id": obligation_id, "known": False, "release_approved": False, "uncertainty": "high",
                "user_wording": f"{DISCLAIMER} HerBiz has no official source recorded for this item."}
    cites = []
    for sid in o.get("sources", []):
        s = data["sources"][sid]
        age = _age_days(s.get("retrieved_at"), as_of)
        cites.append({"source_id": sid, "title": s["title"], "authority": s["issuing_authority"], "url": s["official_url"],
                      "evidence_level": s["evidence_level"], "retrieved_at": s.get("retrieved_at"), "review_status": s["review_status"],
                      "stale": age is None or age > STALE_DAYS,
                      "citation_chip": CITATION_CHIP[s["evidence_level"]]})
    # Rule (one line each):
    #   1. start from the BEST evidence behind the obligation (observed, snippet or listing -> medium; unresolved -> high);
    #      VAT items rest on the VAT register and start at medium (no source approved yet). Never "low" (nothing reviewed);
    #   2. a gap that is open or blocked AND has impact_level "high" makes it high (partly resolved gaps do not).
    levels = [c["evidence_level"] for c in cites]
    if levels:
        uncertainty = UNCERTAINTY[max(levels, key=EVIDENCE_ORDER.index)]
    else:
        uncertainty = "medium" if o.get("vat_register_sources") else "high"
    gap_info = {g: data["gaps"][g] for g in o.get("gaps", [])}
    open_gaps = [g for g, i in gap_info.items() if i["state"] != "resolved"]
    if any(gap_info[g]["state"] in ("open", "blocked") and gap_info[g]["impact_level"] == "high" for g in open_gaps):
        uncertainty = "high"
    sentences = []
    ct = cites_corporate_tax(data, o)
    mode = "synthetic scenario only" if ct else o["mode"]          # recomputed: a mutated copy cannot upgrade a CT item
    if mode == "synthetic scenario only":
        sentences.append("Shown as a demonstration scenario only.")
    if open_gaps:
        sentences.append("Open questions: " + "; ".join(gap_info[g]["what"].split(":")[0].rstrip(".") for g in open_gaps) + ".")
    if any(c["stale"] for c in cites):
        sentences.append("An official source has not been re-checked recently.")
    if o.get("historical"):
        sentences.append("This applies to past periods only.")
    prefix = f"{DEMO_PREFIX}. " if profile_synthetic else ""
    return {"obligation_id": obligation_id, "known": True, "shown": True, "title": o["title"], "domain": o["domain"], "mode": mode,
            "reviewer_needed": o.get("reviewer"), "substantive_rule_allowed": False, "release_approved": False,
            "citations": cites, "vat_register_sources": o.get("vat_register_sources", []), "open_gaps": open_gaps,
            "uncertainty": uncertainty, "user_wording": " ".join([f"{prefix}{DISCLAIMER}"] + sentences),
            "contract": CONTRACT_VERSION}


def impact(data: dict, alerts: list[dict]) -> dict:
    """Map monitor alerts (rag_c.monitor format: url, source_id, kind) to affected 360 obligations. Report-only."""
    url_to_sid = {norm_url(s["official_url"]): sid for sid, s in data["sources"].items() if str(s.get("official_url", "")).startswith("http")}
    affected, unmapped = {}, []
    for al in alerts:
        if al.get("reviewed") is True:
            continue
        sid = al.get("source_id") if al.get("source_id") in data["sources"] else url_to_sid.get(norm_url(al.get("url") or ""))
        vat_sid = al.get("source_id")
        hits = [oid for oid, o in data["obligations"].items()
                if (sid and sid in o.get("sources", [])) or (vat_sid and vat_sid in o.get("vat_register_sources", []))]
        if not hits:
            unmapped.append({"url": al.get("url"), "kind": al.get("kind"), "detail": al.get("detail")})
        for oid in hits:
            affected.setdefault(oid, []).append({"source_id": sid or vat_sid, "kind": al.get("kind"), "at": al.get("at"),
                                                 "detail": al.get("detail")})
    return {"affected_obligations": affected, "unmapped_alerts": unmapped, "activation": "not activated",
            "human_review_required": bool(affected or unmapped), "contract": CONTRACT_VERSION}
