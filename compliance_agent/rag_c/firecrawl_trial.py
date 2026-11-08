"""Controlled Firecrawl monitoring trial: plan, budget guard and post-run verification. This module NEVER calls
Firecrawl (it cannot: Firecrawl is an MCP connector used by a Claude session). It produces the exact call list a
founder-approved session may run, checks the budget before and after, and verifies the saved results locally.

Budget rule: worst case = URLs x runs x 1 credit (a 403/404 page still costs 1 credit; PDF pages are excluded because
their per-page price was not confirmed). The plan is refused if the worst case exceeds the cap (default 15)."""
from __future__ import annotations

import json
from pathlib import Path

from .discovery import norm_url
from .register import REGISTER

CAP = 15
# Fixed scrape options: identical every run (Firecrawl change tracking is unreliable if options change between scrapes).
OPTIONS = {"formats": ["markdown", "changeTracking", "links"], "onlyMainContent": False, "maxAge": 0,
           "proxy": "basic"}   # basic only: never stealth/enhanced proxies; a 403 is recorded, not worked around
FORBIDDEN_OPTIONS = {"proxy": ("stealth", "enhanced", "auto"), "formats": ("json", "screenshot", "summary", "query", "audio")}

# Trial set: HTML pages only, chosen to answer three questions:
#   Q1 can Firecrawl read the paginated FTA listings beyond page 1?   Q2 is change tracking stable on official pages?
#   Q3 does uaelegislation.gov.ae allow normal automated access (403 = no; then a person browses it)?
TRIAL = [
    ("https://tax.gov.ae/en/legislation.aspx", "listing", "Q1/Q2: live legislation listing (EN)"),
    ("https://tax.gov.ae/en/legislation/vat.aspx", "listing", "Q1/Q2: VAT-only legislation listing"),
    ("https://tax.gov.ae/en/Legislation.archive.aspx", "listing", "Q1/Q2: legislation archive"),
    ("https://tax.gov.ae/en/taxes/Vat/guides.references.aspx", "listing", "Q1/Q2: VAT guides and public clarifications"),
    ("https://www.tax.gov.ae/en/services/vat.deregistration.aspx", "document", "Q2: G1 page (30 business days)"),
    ("https://uaelegislation.gov.ae/en/legislations/1227", "document", "Q3: official portal entry for DL 8/2017 (run 1 only)"),
]


def plan(runs: int = 2, cap: int = CAP, register_path: Path = REGISTER) -> dict:
    reg = json.loads(Path(register_path).read_text(encoding="utf-8"))
    known = {norm_url(v["url"]) for s in reg["sources"] for v in s.get("versions", [])} | \
            {norm_url(c[k]) for c in reg.get("candidates", []) for k in ("url", "listing_page_url") if c.get(k)}
    calls = []
    for run in range(1, runs + 1):
        for url, kind, why in TRIAL:
            if run > 1 and "run 1 only" in why:
                continue
            calls.append({"run": run, "url": url, "kind": kind, "purpose": why, "options": OPTIONS,
                          "registered": norm_url(url) in known, "save_as": f"data/monitor/firecrawl/trial-run{run}/{len(calls) + 1:02d}.json"})
    worst = len(calls)          # 1 credit per page, including failed pages
    if worst > cap:
        raise ValueError(f"trial worst case {worst} credits exceeds the cap of {cap}")
    return {"cap": cap, "worst_case_credits": worst, "reserve": cap - worst, "runs": runs, "calls": calls,
            "excluded": "PDF documents (per-page PDF pricing not confirmed); crawl, map, search, json/summary formats; stealth proxies",
            "preconditions": ["founder approval of this exact plan (decision D15)",
                              "founder checks the Firecrawl dashboard balance first (not readable from Claude: find_tools has no balance capability; checked 17 Oct 2026, 0 credits used)",
                              "run 2 at least 24 hours after run 1, with identical options"],
            "stop_rules": ["stop the whole trial if any call reports more than 1 credit",
                           "do not retry a failed URL in the same run",
                           "a 403 on uaelegislation.gov.ae is recorded and not retried; a person opens the page in a browser"]}


def check_options(options: dict) -> list[str]:
    problems = []
    for k, bad in FORBIDDEN_OPTIONS.items():
        v = options.get(k)
        vals = v if isinstance(v, list) else [v]
        problems += [f"{k}={x} is not allowed in the trial" for x in vals if x in bad]
    for k, v in OPTIONS.items():
        if options.get(k) != v:
            problems.append(f"{k} must be {v!r} (got {options.get(k)!r})")
    return problems


def verify_results(folder: Path, the_plan: dict, run: int) -> dict:
    """After a run: every saved result is a planned URL, nothing extra was scraped, and credits stayed within the plan."""
    planned = {norm_url(c["url"]) for c in the_plan["calls"] if c["run"] == run}
    seen, extra, credits, statuses = set(), [], 0, {}
    for f in sorted(Path(folder).glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        d = d.get("data", d)
        meta = d.get("metadata") or {}
        url = d.get("url") or meta.get("sourceURL") or ""
        u = norm_url(url)
        if u not in planned:
            extra.append(url)
        seen.add(u)
        used = meta.get("creditsUsed", d.get("creditsUsed"))
        credits += int(used) if isinstance(used, (int, float)) else 1      # unknown -> count the worst case
        statuses[url] = {"http": meta.get("statusCode"), "change": (d.get("changeTracking") or {}).get("changeStatus"),
                         "credits": used}
    return {"run": run, "results": len(seen), "planned": len(planned), "missing": sorted(planned - seen), "unplanned": extra,
            "credits_counted": credits, "within_plan": not extra and credits <= len(planned), "per_url": statuses}


# ------------------------------------------------------------------ import of saved results (deterministic trim)
import hashlib as _hashlib
import re as _re

END_MARK = "## Did you find this content useful?"
# Site footers that must never be glued onto the last article: FTA, UAE Legislation portal (EN/AR), MoF
END_MARKS = (END_MARK, "Translated in cooperation with", "The site was last updated on", "تم تحديث الموقع", "Did you find this content useful?")


def trim_main(markdown: str) -> str:
    """Verbatim main section: from the first '# ' (H1) line, if any, up to (not including) the first known site footer
    (END_MARKS). Navigation, rotating news, counters and footers are dropped the same way for every run."""
    lines = markdown.splitlines(keepends=True)
    start = next((i for i, l in enumerate(lines) if l.startswith("# ")), 0)
    body = "".join(lines[start:])
    cuts = [c for c in (body.find(m) for m in END_MARKS) if c >= 0]
    return body[:min(cuts)] if cuts else body


def import_result(src: Path, dest: Path, ledger: Path, phase: int, run: int | None, note: str = "") -> dict:
    """Copy one saved Firecrawl scrape result into the trial folder (trimmed markdown, full metadata, all links) and
    append it to the credit ledger. The untrimmed original stays in Claude's tool-results cache (sha256 recorded)."""
    raw = Path(src).read_bytes()
    d = json.loads(raw)
    d = d.get("data", d)
    meta = d.get("metadata") or {}
    out = {"data": {"url": meta.get("sourceURL") or meta.get("url"), "metadata": meta, "changeTracking": d.get("changeTracking"),
                    "links": d.get("links") or [], "markdown": trim_main(d.get("markdown") or ""),
                    "trimmed_by": "rag_c.firecrawl_trial.trim_main (first H1 .. FTA feedback footer)",
                    "original": {"path": str(src), "sha256": _hashlib.sha256(raw).hexdigest(), "markdown_chars": len(d.get("markdown") or "")}}}
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(dest).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    led = json.loads(Path(ledger).read_text(encoding="utf-8"))
    led["calls"].append({"n": len(led["calls"]) + 1, "phase": phase, "run": run, "tool": "firecrawl_scrape", "url": out["data"]["url"],
                         "status": meta.get("statusCode"), "credits_used": meta.get("creditsUsed"),
                         "change_status": (d.get("changeTracking") or {}).get("changeStatus"), "scrape_id": meta.get("scrapeId"), "note": note})
    led["credits_used_total"] = sum(int(c.get("credits_used") or 1) for c in led["calls"])
    Path(ledger).write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"saved": str(dest), "status": meta.get("statusCode"), "credits": meta.get("creditsUsed"),
            "change": (d.get("changeTracking") or {}).get("changeStatus"), "links": len(out["data"]["links"]),
            "trimmed_chars": len(out["data"]["markdown"]), "credits_used_total": led["credits_used_total"]}


ENTRY_RX = _re.compile(r"\n\n([^\n\[!][^\n]{8,300})\n+(?:New\n+)?Issue Date :\s*([A-Za-z]{3} \d{1,2}, \d{4}|NA)(?:\n+Publish Date :\s*([A-Za-z]{3} \d{1,2}, \d{4}))?"
                       r"\n+([^\n]{2,60})\n+\[!\[pdf\]\([^)]*\)\\\\\n[^\]]*\]\((https?://[^ )]+)")


def fta_listing_entries(markdown: str) -> list[dict]:
    """Entries of an FTA legislation listing page: title, issue date, publish date, category, file URL (as shown)."""
    return [{"title": " ".join(t.split()), "issue_date_shown": None if i == "NA" else i, "publish_date_shown": p or None, "category": c.strip(), "url": u}
            for t, i, p, c, u in ENTRY_RX.findall(markdown)]
