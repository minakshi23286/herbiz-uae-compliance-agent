"""Command line for the Workstream C tools (see the package docstring). Databases, data/raw/, the lock and the B files are never written.
File outputs: `render` (docs/rag/*.md, generated), `monitor` (data/monitor/ only), `validity --write` (the export),
`discover --write` (a new register version), `dryrun --out` (a new file only)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import inventory as I
from .dryrun import diff_builds, dry_run
from .register import REGISTER, validate

DEFAULT_DB = I.DATA / "CL_test_workspace.sqlite3"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m compliance_agent.rag_c")
    ap.add_argument("cmd", choices=["inventory", "validate", "hashes", "duplicates", "compare", "dryrun", "diff", "amendments", "claims", "facts", "validity",
                                       "trace", "extraction", "headings", "discover", "monitor", "render", "protect-status", "firecrawl-plan", "firecrawl-verify",
                                       "obligations360", "impact360"])
    ap.add_argument("versions", nargs="*", help="compare: OLD_VERSION NEW_VERSION; diff: BUILD_DB (compared with --db)")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="database to read (opened read-only; default: test workspace)")
    ap.add_argument("--register", default=str(REGISTER))
    ap.add_argument("--out", default=None, help="dryrun: keep the build in this NEW file")
    ap.add_argument("--alerts", default=None, help="validity: a monitor alerts JSON; unreviewed change alerts become 'source_changed' issues")
    ap.add_argument("--as-of", default=None, help="amendments/validity: date for 'in force' (default today)")
    ap.add_argument("--write", action="store_true", help="validity: write knowledge_base/CL_source_validity.json; discover: add proposals to the register")
    ap.add_argument("--ledger", default=str(I.DATA / "CL_llm_experiment.sqlite3"), help="trace: experiment ledger (opened read-only)")
    ap.add_argument("--version", dest="version_id", default=None, help="extraction/headings: one version (default: all)")
    ap.add_argument("--listing", default=None, help="discover: listing file (.html or Firecrawl .json/.md)")
    ap.add_argument("--listing-url", default="", help="discover: the official URL the listing file came from")
    ap.add_argument("--fixtures", default=None, help="monitor: FixtureFetcher folder (index.json)")
    ap.add_argument("--firecrawl-dir", default=None, help="monitor: folder of saved Firecrawl scrape JSON results")
    ap.add_argument("--allow-network", action="store_true", help="monitor: LocalFetcher (founder approval required)")
    ap.add_argument("--state", default=str(I.DATA / "monitor" / "CL_monitor_state.json"))
    ap.add_argument("--report-dir", default=str(I.DATA / "monitor" / "reports"))
    a = ap.parse_args(argv)
    if a.cmd == "inventory":
        out = I.inventory(a.db)
    elif a.cmd == "validate":
        out = validate(Path(a.register), db=a.db if Path(a.db).exists() else None)
    elif a.cmd == "hashes":
        out = I.hashes()
    elif a.cmd == "duplicates":
        out = I.duplicates(a.db)
    elif a.cmd == "compare":
        if len(a.versions) != 2:
            ap.error("compare needs OLD_VERSION NEW_VERSION")
        out = I.compare(a.db, *a.versions)
    elif a.cmd == "diff":
        if len(a.versions) != 1:
            ap.error("diff needs BUILD_DB")
        out = diff_builds(a.db, a.versions[0])
    elif a.cmd == "dryrun":
        out = dry_run(a.db, out=Path(a.out) if a.out else None)
    else:
        out = _more(a)
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    if a.cmd == "validate":
        return 0 if out["valid"] else 1
    if a.cmd == "dryrun":
        return 0 if out["reproducible"] else 1
    if a.cmd == "monitor":
        return 2 if out["high_alerts"] else 0          # a scheduler can notify on exit code 2
    if a.cmd == "hashes":
        return 0 if out["ok"] == out["total"] else 1
    return 0


def _versions(db, one):
    con = I.connect_ro(db)
    try:
        return [one] if one else [r[0] for r in con.execute("SELECT version_id FROM source_versions WHERE origin_label = 'REAL_OFFICIAL_SOURCE' ORDER BY version_id")]
    finally:
        con.close()


def _more(a):
    import datetime as dt
    from . import amendments, citations, claims, discovery, extraction_check, monitor, validity
    today = a.as_of or dt.date.today().isoformat()
    if a.cmd == "amendments":
        return amendments.amendment_map(Path(a.register), today)
    if a.cmd == "claims":
        return claims.check_claims(a.db, Path(a.register))
    if a.cmd == "facts":
        return claims.fact_inventory(a.db)
    if a.cmd == "validity":
        al = json.loads(Path(a.alerts).read_text(encoding="utf-8"))["alerts"] if a.alerts else None
        v = validity.build_validity(a.db, Path(a.register), today, alerts=al)
        if a.write:
            validity.EXPORT.write_text(json.dumps(v, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            v = {"written": str(validity.EXPORT), "issues": len(v["issues"])}
        return v
    if a.cmd == "trace":
        t = citations.trace_ledger(a.ledger, a.db, validity.build_validity(a.db, Path(a.register), today))
        t.pop("rows")
        return t
    if a.cmd == "extraction":
        return [{"structure": extraction_check.structure(a.db, v),
                 "second_extractor": {k: x for k, x in extraction_check.second_extractor_agreement(a.db, v).items() if k != "rows"}}
                for v in _versions(a.db, a.version_id)]
    if a.cmd == "headings":
        return [extraction_check.headings(a.db, v) for v in _versions(a.db, a.version_id)]
    if a.cmd == "firecrawl-plan":
        from . import firecrawl_trial
        return firecrawl_trial.plan()
    if a.cmd == "firecrawl-verify":
        from . import firecrawl_trial
        if len(a.versions) != 2:
            raise SystemExit("firecrawl-verify needs RUN_NUMBER FOLDER")
        return firecrawl_trial.verify_results(Path(a.versions[1]), firecrawl_trial.plan(), int(a.versions[0]))
    if a.cmd in ("obligations360", "impact360"):
        from . import sources360
        data = sources360.load()
        if a.cmd == "impact360":
            if not a.alerts:
                raise SystemExit("impact360 needs --alerts FILE (a monitor alerts JSON)")
            al = json.loads(Path(a.alerts).read_text(encoding="utf-8"))
            return sources360.impact(data, al.get("alerts", al) if isinstance(al, dict) else al)
        ids = a.versions or sorted(data["obligations"])
        return {"contract": sources360.CONTRACT_VERSION, "labels": [sources360.obligation_label(data, o, a.as_of or today) for o in ids]}
    if a.cmd == "protect-status":
        from . import protection
        return protection.status(Path(a.versions[0]) if a.versions else Path(a.db))
    if a.cmd == "render":
        from . import render
        out_dir = Path(a.out or (I.ROOT / "docs" / "rag"))
        v = validity.build_validity(a.db, Path(a.register), today)
        files = {out_dir / "CL_HERBIZ_OFFICIAL_SOURCE_REGISTER.md": render.register_md(Path(a.register)),
                 out_dir / "CL_HERBIZ_SOURCE_VALIDITY_MATRIX.md": render.validity_md(v, amendments.amendment_map(Path(a.register), today),
                                                                                   claims.check_claims(a.db, Path(a.register)))}
        for f, text in files.items():
            f.write_text(text, encoding="utf-8")
        return {"written": [str(f) for f in files]}
    if a.cmd == "discover":
        if not a.listing:
            raise SystemExit("discover needs --listing FILE (saved listing page or Firecrawl result)")
        raw = Path(a.listing).read_text(encoding="utf-8")
        if a.listing.endswith(".json"):
            d = json.loads(raw)
            d = d.get("data", d)
            content, kind, url = d.get("markdown", ""), "markdown", a.listing_url or (d.get("metadata") or {}).get("sourceURL", "")
        else:
            content, kind, url = raw, ("markdown" if a.listing.endswith(".md") else "html"), a.listing_url
        prop = discovery.propose(discovery.parse_listing(content, url or "https://tax.gov.ae/", kind), Path(a.register), url, today)
        if a.write and prop["proposals"]:
            new = discovery.add_proposals(Path(a.register), prop["proposals"], today)
            Path(a.register).write_text(json.dumps(new, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            prop["register_version_written"] = new["register_version"]
        return prop
    # monitor
    if sum(bool(x) for x in (a.fixtures, a.firecrawl_dir, a.allow_network)) != 1:
        raise SystemExit("monitor needs exactly one of --fixtures DIR, --firecrawl-dir DIR, --allow-network")
    fetcher = (monitor.FixtureFetcher(Path(a.fixtures)) if a.fixtures else
               monitor.FirecrawlImport(Path(a.firecrawl_dir)) if a.firecrawl_dir else monitor.LocalFetcher(allow_network=True))
    state_path = Path(a.state)
    with monitor.RunLock(state_path):
        state, warning = monitor.load_state(state_path)
        v = validity.build_validity(a.db, Path(a.register), today) if Path(a.db).exists() else None
        res = monitor.run(fetcher, state, Path(a.register), validity=v)
        if warning:
            res["warnings"].append(warning)
        paths = monitor.write_outputs(res, state_path, Path(a.report_dir), today)
    return {"checked": res["checked"], "status_counts": res["status_counts"], "alerts": len(res["alerts"]),
            "high_alerts": sum(x["severity"] == "high" for x in res["alerts"]), "proposals": len(res["proposals"]),
            "warnings": res["warnings"], **paths}


if __name__ == "__main__":
    sys.exit(main())
