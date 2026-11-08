"""Source-change monitoring: check registered official URLs, detect changed / removed / newly published documents,
compare versions article by article, name potentially affected provisions, raise review alerts, write a daily report.

Fetching is pluggable and separated from verification:
  * FixtureFetcher   - files on disk (tests, synthetic fixtures)                         no network
  * FirecrawlImport  - JSON results saved from Firecrawl scrapes by a Claude session    no network here
  * LocalFetcher     - kb.http_fetch (allowlisted official hosts, TLS on); refuses unless allow_network=True
Every observation is verified locally (hash, extraction, article diff) against the monitor state and the collection
lock. The monitor writes only its own state, alerts and report. It never activates a source, never writes the knowledge
base, data/raw/ or the lock. A changed document is a signal for a founder-approved `kb collect`, not a collection."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from ..sources import normalize
from .discovery import norm_url, parse_listing, propose
from .register import REGISTER

SEVERITY = {"restored": "medium", "removed": "high", "changed_substantive_in_scope": "high", "conflict_provision_changed": "high",
            "differs_from_collected_version": "high", "changed_substantive": "medium", "new_document_on_listing": "medium",
            "fetch_error": "medium", "removed_from_listing": "medium", "changed_cosmetic": "low", "new": "info"}


# ------------------------------------------------------------------ observations (fetcher output, one per URL)
def _obs(url, status, content_type=None, body=None, markdown=None, via="", error=None, extra=None):
    return {"url": url, "http_status": status, "content_type": content_type, "body": body, "markdown": markdown,
            "via": via, "error": error, "extra": extra or {}}


class FixtureFetcher:
    """index.json: {url: {"file": "name", "status": 200, "content_type": "text/html"}}; a missing url = 404."""
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.index = {norm_url(k): v for k, v in json.loads((self.folder / "index.json").read_text(encoding="utf-8")).items()}

    def __call__(self, url: str) -> dict:
        e = self.index.get(norm_url(url))
        if e is None:
            return _obs(url, 404, via="fixture")
        if e.get("status", 200) != 200:
            return _obs(url, e["status"], via="fixture")
        body = (self.folder / e["file"]).read_bytes()
        return _obs(url, 200, e.get("content_type") or ("application/pdf" if body[:5] == b"%PDF-" else "text/html"), body=body, via="fixture")


class FirecrawlImport:
    """Folder of Firecrawl scrape results saved as JSON by a Claude session (one file per URL).
    Accepted shape (Firecrawl scrape response): {"url" | "metadata": {"sourceURL", "statusCode"}, "markdown", "links",
    "changeTracking": {"changeStatus", "previousScrapeAt", "visibility"}}. Firecrawl's own change status is kept as a
    hint; the decision is made locally from the markdown."""
    def __init__(self, folder: Path):
        self.by_url = {}
        for f in sorted(Path(folder).glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            d = d.get("data", d)
            url = d.get("url") or (d.get("metadata") or {}).get("sourceURL")
            if url:
                self.by_url[norm_url(url)] = d

    def __call__(self, url: str) -> dict:
        d = self.by_url.get(norm_url(url))
        if d is None:
            return _obs(url, None, via="firecrawl", error="no Firecrawl result for this URL in the import folder")
        code = (d.get("metadata") or {}).get("statusCode", 200)
        ct = d.get("changeTracking") or {}
        return _obs(url, code, "text/markdown", markdown=d.get("markdown") or "", via="firecrawl",
                    extra={"firecrawl_change_status": ct.get("changeStatus"), "firecrawl_visibility": ct.get("visibility"),
                           "firecrawl_previous_scrape_at": ct.get("previousScrapeAt"), "links": d.get("links")})


class LocalFetcher:
    def __init__(self, allow_network: bool = False):
        if not allow_network:
            raise PermissionError("LocalFetcher needs allow_network=True (founder approval for network access)")

    def __call__(self, url: str) -> dict:
        from ..kb import CollectError, http_fetch
        try:
            data, mime = http_fetch(url)
        except CollectError as ex:
            m = re.search(r"HTTP Error (\d{3})", str(ex))
            return _obs(url, int(m.group(1)) if m else None, via="urllib", error=str(ex)[:300])
        return _obs(url, 200, mime, body=data, via="urllib")


# ------------------------------------------------------------------ local verification
def _units_from_text_blocks(units: list[dict]) -> dict[str, str]:
    from .inventory import article_key
    out: dict[str, str] = {}
    for u in units:
        k = article_key(u["locator"])
        key = (f"Article {k[0]}{' (' + k[1] + ')' if k[1] else ''}" if k else re.sub(r",.*", "", u["locator"]))
        out[key] = out.get(key, "") + " " + u["text"]
    return out


MD_HEADING = re.compile(r"^#{1,6}[ \t]*Article[ \t]*\(?[ \t]*(\d+)[ \t]*\)?[ \t]*(\(?[ \t]*(?:bis|ter|quater)[ \t]*\)?)?(?![\w(])", re.I | re.M)


def _markdown_units(md: str) -> dict[str, str]:
    """Split Firecrawl markdown into article units. Two heading styles: markdown headings as used by the UAE
    Legislation portal ('#### Article (48) Reverse Charge', '#### Article (54) BIS'), and the knowledge base's own rule
    (kb.ARTICLE_RX) for plain-text headings. Keys match the knowledge base: 'Article 48', 'Article 54 (bis)'."""
    from ..kb import ARTICLE_RX
    marks = [(m.start(), int(m.group(1)), (m.group(2) or "").strip("() \t").lower()) for m in MD_HEADING.finditer(md)]
    if not marks:
        text = "\n".join(re.sub(r"^[#>*\s]+|[*_]+", "", line).strip() for line in md.splitlines())
        marks = [(m.start(), int(m.group(1)), (m.group(2) or "").strip("() \t").lower()) for m in ARTICLE_RX.finditer(text)]
        md = text
    units, cur, pos = {}, "Front matter", 0
    for start, n, suffix in marks:
        units[cur] = units.get(cur, "") + md[pos:start]
        cur = f"Article {n}" + (f" ({suffix})" if suffix else "")
        pos = start
    units[cur] = units.get(cur, "") + md[pos:]
    return {k: v for k, v in units.items() if v.strip()}


def extract_units(obs: dict, kind: str = "document") -> dict[str, str]:
    """Article units for legal documents; for web pages, paragraphs keyed by their normalised content (so an inserted
    banner shifts nothing and only paragraphs that really changed are reported)."""
    from ..kb import extract_html, extract_pdf
    if obs.get("markdown") is not None:
        units = _markdown_units(obs["markdown"])
        if any(k.startswith("Article") for k in units):
            return units
        return _paragraph_units([l for l in obs["markdown"].splitlines() if l.strip()])
    body = obs["body"] or b""
    if body[:5] == b"%PDF-":
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:   # temporary; deleted on close; never under data/raw/
            f.write(body)
            f.flush()
            return _units_from_text_blocks(extract_pdf(Path(f.name))["units"])
    html = extract_html(body)
    blocks = _units_from_text_blocks(html["units"])
    if any(k.startswith("Article") for k in blocks):
        return blocks
    return _paragraph_units([u["text"] for u in html["units"]])


def _paragraph_units(texts: list[str]) -> dict[str, str]:
    out = {}
    for t in texts:
        sq = _squash(t)
        if len(sq) >= 12:
            out[f"Paragraph#{_h(sq)[:12]}"] = t
    return out


FOOTER_RX = re.compile(r"^\s*(?:page\s+)?\d{1,4}\s*(?:of|/)\s*\d{1,4}\s*$", re.I | re.M)


def _squash(t: str) -> str:
    t = re.sub(r"^\s*\d{1,3}\s+(?:Article|Clause|Paragraph|Item|Definition)\b.*?(?:amended|added|repealed|replaced|inserted).*$",
               " ", t, flags=re.M | re.I)                                    # footnote lines
    t = FOOTER_RX.sub(" ", t)                                                # "Page 3 of 12" footers (MON-06)
    t = re.sub(r"^(Article\s*\(?\d+\)?(?:\s*\(\w+\))?\s*[–—-]\s*[^\n]*?)\s*\d{1,3}\s*$", r"\1", t, flags=re.M)  # heading footnote marks (MON-05)
    return re.sub(r"[\s​]+", "", normalize(t))


def _h(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def diff_units(old: dict[str, dict], new: dict[str, str]) -> dict:
    """old: {unit: {"exact": hash, "squash": hash}}; new: {unit: text}. Cosmetic = equal after layout normalisation."""
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    substantive, cosmetic = [], []
    for k in sorted(set(old) & set(new)):
        if old[k]["exact"] == _h(new[k]):
            continue
        (cosmetic if old[k]["squash"] == _h(_squash(new[k])) else substantive).append(k)
    return {"added": added, "removed": removed, "substantive": substantive, "cosmetic": cosmetic}


def _fingerprint(units: dict[str, str]) -> dict[str, dict]:
    return {k: {"exact": _h(v), "squash": _h(_squash(v))} for k, v in units.items()}


# ------------------------------------------------------------------ watch list from the register
def watchlist(register_path: Path = REGISTER) -> list[dict]:
    reg = json.loads(Path(register_path).read_text(encoding="utf-8"))
    lock_sha = {}
    try:
        lock = json.loads((Path(register_path).parent / "CL_collected_lock.json").read_text(encoding="utf-8"))
        lock_sha = {norm_url(d["url"]): d["sha256"] for d in lock["documents"]}
    except (OSError, ValueError, KeyError):
        pass
    items, seen = [], set()

    def add(item):
        u = norm_url(item["url"])
        if u not in seen:
            seen.add(u)
            items.append(item)

    for s in reg.get("sources", []):
        arts = [a for a in (s.get("scope_topics") or {}).get("articles", {}) if not a.startswith("Paragraph")]
        for v in s.get("versions", []):
            cur = ((v.get("currency_observations") or [{}])[-1].get("currency") or "").lower()
            add({"url": v["url"], "kind": "document", "source_id": s["source_id"], "version_id": v["version_id"],
                 "collected_sha256": lock_sha.get(norm_url(v["url"])), "in_scope_articles": arts,
                 "page_in_scope": not arts, "archived": "archived" in cur})
    for c in reg.get("candidates", []):
        is_listing = (c.get("document_type") or "") == "listing page"
        if c.get("url") and c.get("verification_status") != "unresolved" and not c.get("dates_shown_on_listing"):
            add({"url": c["url"], "kind": "listing" if is_listing else "document", "candidate_id": c["candidate_id"],
                 "source_id": c["candidate_id"], "in_scope_articles": [],
                 "page_in_scope": (c.get("scope") or "").startswith("in scope"), "archived": False})
        if c.get("listing_page_url") and is_listing:
            add({"url": c["listing_page_url"], "kind": "listing", "candidate_id": c["candidate_id"], "source_id": None,
                 "in_scope_articles": [], "page_in_scope": False, "archived": False})
    return items


# ------------------------------------------------------------------ one monitoring run
def _relevant_doc_link(url: str) -> bool:
    from .discovery import DOC_EXT, RELEVANT
    from urllib.parse import urlparse, unquote
    path = unquote(urlparse(url).path)
    words = re.sub(r"[-_./]+", " ", path)            # 'Cabinet-Decision-No.-149' -> 'Cabinet Decision No 149' (MoF file names)
    return path.lower().endswith(DOC_EXT) and ("/datafolder/" in path.lower() or "/wp-content/uploads/" in path.lower()
                                                or bool(RELEVANT.search(words)))


def run(fetcher, state: dict, register_path: Path = REGISTER, now: str | None = None, validity: dict | None = None,
        items: list[dict] | None = None) -> dict:
    now = now or dt.datetime.now().astimezone().isoformat(timespec="seconds")
    items = items if items is not None else watchlist(register_path)
    conflict_keys = {p for i in (validity or {}).get("issues", []) if i["kind"] == "conflict" for p in i["provisions"]}
    issue_keys = {p for i in (validity or {}).get("issues", []) for p in i["provisions"]}
    new_state = {"urls": dict(state.get("urls", {})), "last_run": now}
    events, alerts, proposals, warnings = [], [], [], []
    if validity is None:
        warnings.append("validity export unavailable: conflict and validity cross-checks were skipped")

    def alert(kind, item, detail, provisions=(), severity=None):
        alerts.append({"severity": severity or SEVERITY[kind], "kind": kind, "url": item["url"], "source_id": item.get("source_id"),
                       "version_id": item.get("version_id"), "candidate_id": item.get("candidate_id"),
                       "provisions": sorted(provisions), "detail": detail, "at": now})

    for it in items:
        key = norm_url(it["url"])
        prev = state.get("urls", {}).get(key) or {}
        ev = {"url": it["url"], "kind": it["kind"], "via": None, "http_status": None, "source_id": it.get("source_id"),
              "version_id": it.get("version_id"), "candidate_id": it.get("candidate_id")}
        try:                                                     # one bad item never stops the run (MON-01)
            obs = fetcher(it["url"])
            ev.update(via=obs["via"], http_status=obs["http_status"])
            _one(it, obs, prev, key, ev, new_state, alert, proposals, register_path, now, conflict_keys, issue_keys)
        except Exception as ex:                                  # noqa: BLE001 - recorded, never swallowed silently
            ev["status"] = "error"
            fails = int(prev.get("consecutive_errors", 0)) + 1
            alert("fetch_error", it, f"{type(ex).__name__}: {str(ex)[:200]}", severity="high" if fails >= 3 else None)
            new_state["urls"][key] = {**prev, "last_error": f"{type(ex).__name__}: {str(ex)[:200]}", "checked_at": now,
                                      "consecutive_errors": fails}
        events.append(ev)
    counts = {}
    for e in events:
        counts[e.get("status", "error")] = counts.get(e.get("status", "error"), 0) + 1
    return {"run_at": now, "checked": len(events), "status_counts": counts, "events": events, "alerts": alerts,
            "proposals": proposals, "warnings": warnings, "state": new_state,
            "activation": "none (monitoring never activates or collects sources)"}


def _one(it, obs, prev, key, ev, new_state, alert, proposals, register_path, now, conflict_keys, issue_keys):
    status = obs["http_status"]
    if status in (404, 410):
        ev["status"] = "removed"
        if prev.get("status") != "removed":                      # alert once, also when already gone at baseline (MON-03)
            alert("removed", it, f"HTTP {status}: the official URL does not serve the document"
                                 + (" (it was never seen working by the monitor)" if not prev.get("checked_ok_at") else ""),
                  severity="medium" if it.get("archived") else None)
        new_state["urls"][key] = {**prev, "status": "removed", "checked_at": now, "consecutive_errors": 0}
        return
    if status != 200 or obs.get("error"):
        ev["status"] = "error"
        fails = int(prev.get("consecutive_errors", 0)) + 1      # a failure that persists escalates (MON-17)
        alert("fetch_error", it, (obs.get("error") or f"HTTP {status}") + f" (consecutive failures: {fails})",
              severity="high" if fails >= 3 else None)
        new_state["urls"][key] = {**prev, "last_error": obs.get("error") or status, "checked_at": now, "consecutive_errors": fails}
        return
    if prev.get("status") == "removed":
        alert("restored", it, "the URL serves a document again after being removed (MON-14)")
    raw_sha = hashlib.sha256(obs["body"]).hexdigest() if obs.get("body") is not None else None
    if it["kind"] == "listing":
        _listing(it, obs, prev, key, ev, new_state, alert, proposals, register_path, now, raw_sha)
        return
    units = extract_units(obs, "document")
    if not units or sum(len(v) for v in units.values()) < 50:   # empty / soft-404 page served with 200 (MON-08)
        ev["status"] = "error"
        alert("fetch_error", it, f"suspiciously little text extracted ({sum(len(v) for v in units.values())} chars); baseline kept")
        new_state["urls"][key] = {**prev, "last_error": "empty extraction", "checked_at": now}
        return
    fp = _fingerprint(units)
    ev["units"] = len(units)
    if it.get("collected_sha256") and raw_sha and raw_sha != it["collected_sha256"]:
        ev["differs_from_collected_version"] = True
        if prev.get("drift_alerted_sha") != raw_sha:             # every new drift, any format, once per new bytes (MON-13)
            alert("differs_from_collected_version", it, "the file now served differs from the collected (locked) bytes")
    if "units" not in prev:
        ev["status"] = "new"
    else:
        d = diff_units(prev["units"], units)
        ev["diff"] = d
        src = it.get("source_id") or ""
        changed = d["substantive"] + d["added"] + d["removed"]
        page_like = all(k.startswith("Paragraph") for k in list(units) + list(prev["units"]))
        touched = sorted({f"{src}|*" if (u.startswith("Paragraph") or page_like) else f"{src}|{u.replace('Article ', '')}"
                          for u in changed}) if src else []
        in_scope = [u for u in changed if u.replace("Article ", "") in set(it.get("in_scope_articles") or [])]
        if page_like and changed and it.get("page_in_scope"):
            in_scope = changed
        if changed:
            ev["status"] = "changed"
            kind = "changed_substantive_in_scope" if in_scope else "changed_substantive"
            what = f"{len(changed)} paragraph(s)" if page_like else ", ".join(changed)
            alert(kind, it, f"substantive change in {what}" + (" (in scope)" if in_scope else ""), touched)
            hit = sorted(set(touched) & conflict_keys) or (sorted(conflict_keys & {k for k in conflict_keys if k.startswith(src + "|")})
                                                           if page_like and src else [])
            if hit:
                alert("conflict_provision_changed", it, "a provision under a recorded source conflict changed; re-check the conflict", hit)
            ev["affected_provisions"] = touched
            ev["affected_provisions_with_validity_issues"] = sorted(set(touched) & issue_keys)
        elif d["cosmetic"]:
            ev["status"] = "cosmetic"
            alert("changed_cosmetic", it, f"layout-only change in {len(d['cosmetic'])} unit(s)")
        else:
            ev["status"] = "same"
        fc = obs["extra"].get("firecrawl_change_status")
        local = {"changed": "changed", "cosmetic": "changed", "same": "same"}[ev["status"]]
        if fc and fc != local:
            ev["firecrawl_disagrees"] = fc       # recorded, never trusted over the local comparison
    new_state["urls"][key] = {"status": "ok", "units": fp, "raw_sha256": raw_sha, "checked_at": now, "checked_ok_at": now,
                              "via": obs["via"], "consecutive_errors": 0,
                              "drift_alerted_sha": raw_sha if ev.get("differs_from_collected_version") else prev.get("drift_alerted_sha")}


def _listing(it, obs, prev, key, ev, new_state, alert, proposals, register_path, now, raw_sha):
    is_md = obs.get("markdown") is not None
    content = obs["markdown"] if is_md else obs["body"].decode("utf-8", "replace")
    entries = parse_listing(content, it["url"], "markdown" if is_md else "html")
    titled = {norm_url(e["url"]) for e in entries if e.get("title")}
    for l in (obs["extra"].get("links") or []):                  # Firecrawl's own link list (MON-12), untitled: last
        if isinstance(l, str) and norm_url(l) not in titled:
            entries.append({"url": l, "title": "", "context": ""})
    from .discovery import DOC_EXT, RELEVANT
    from urllib.parse import urlparse as _up
    FILE_EXT = (".pdf", ".doc", ".docx", ".xls", ".xlsx")      # a legislation listing lists FILES; .aspx links are site navigation
    entries = [e for e in entries if _up(e["url"]).path.lower().endswith(FILE_EXT)]
    docs = sorted({norm_url(e["url"]) for e in entries if _relevant_doc_link(e["url"]) or RELEVANT.search(e.get("title") or "")})
    if not docs:                                                 # JS-only / empty listing: not "everything removed" (MON-10)
        ev["status"] = "error"
        alert("fetch_error", it, "no document links found on the listing (JavaScript-only page or layout change); baseline kept")
        new_state["urls"][key] = {**prev, "last_error": "empty listing", "checked_at": now}
        return
    have_baseline = prev.get("links") is not None
    added = sorted(set(docs) - set(prev.get("links") or [])) if have_baseline else docs
    gone = sorted(set(prev.get("links") or []) - set(docs)) if have_baseline else []
    prop = propose([e for e in entries if norm_url(e["url"]) in set(added)], register_path, it["url"], now)
    seen = {norm_url(x["url"]) for x in proposals}
    for p in prop["proposals"]:
        if norm_url(p["url"]) in seen:                          # the same file on several listings: one proposal
            continue
        seen.add(norm_url(p["url"]))
        proposals.append(p)
        alert("new_document_on_listing", it, f"new official document link: {p['title'] or p['url']}")
    for g in gone:
        alert("removed_from_listing", it, f"document link no longer on the listing: {g}")
    ev.update(status="new" if not have_baseline else ("changed" if added or gone else "same"),
              links=len(docs), links_added=len(added) if have_baseline else 0, links_removed=len(gone), proposals=len(prop["proposals"]))
    new_state["urls"][key] = {"status": "ok", "links": docs, "checked_at": now, "checked_ok_at": now, "raw_sha256": raw_sha,
                              "consecutive_errors": 0}


def report_markdown(result: dict, title_date: str) -> str:
    sev_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    lines = [f"# HerBiz: Compliance Agent — source monitoring report {title_date}", "",
             f"**Business line:** HomepreunerHub / HerBiz · **Run:** {result['run_at']} · **Checked:** {result['checked']} URLs · "
             f"**Statuses:** {', '.join(f'{k} {v}' for k, v in sorted(result['status_counts'].items()))} · "
             "**Activation:** none (a person reviews every alert) · **Not legal or tax advice.**", ""]
    for w in result.get("warnings", []):
        lines += [f"> **Warning:** {w}", ""]
    al = sorted(result["alerts"], key=lambda a: (sev_order[a["severity"]], a["kind"]))
    esc = lambda x: str(x).replace("|", "\\|")
    lines += ["## Alerts", ""] + (["| Severity | Kind | Source | URL | Provisions | Detail |", "|---|---|---|---|---|---|"] +
              [f"| {a['severity']} | {a['kind']} | {a.get('version_id') or a.get('candidate_id') or ''} | {a['url']} | "
               f"{esc(', '.join(a['provisions']))} | {esc(a['detail'])} |" for a in al] if al else ["No alerts."])
    if result["proposals"]:
        lines += ["", "## New documents proposed as candidates (not activated)", "",
                  "| Candidate id | Title | URL | Dates shown |", "|---|---|---|---|"] + \
                 [f"| {p['candidate_id']} | {esc(p['title'] or '')} | {p['url']} | {p.get('dates_shown_on_listing') or ''} |" for p in result["proposals"]]
    lines += ["", "## Per-URL results", "", "| Status | Kind | Via | URL | Detail |", "|---|---|---|---|---|"]
    for e in result["events"]:
        detail = e.get("diff") and {k: v for k, v in e["diff"].items() if v} or ""
        if e.get("differs_from_collected_version"):
            detail = f"{detail} differs from collected bytes".strip()
        lines.append(f"| {e.get('status', 'error')} | {e['kind']} | {e.get('via')} | {e['url']} | {esc(detail)} |")
    lines += ["", "**Next step for any high alert:** a person reviews it; if a document changed, the founder approves a "
                  "`kb collect --allow-network` into a copy, then `rag_c compare`, `rag_c dryrun` and a new register version."]
    return "\n".join(lines) + "\n"


def load_state(state_path: Path) -> tuple[dict, str | None]:
    """A corrupt state file is moved aside (never deleted) and the run starts from an empty baseline (MON-15)."""
    if not state_path.exists():
        return {}, None
    try:
        return json.loads(state_path.read_text(encoding="utf-8")), None
    except (ValueError, OSError) as ex:
        aside = state_path.with_name(f"{state_path.stem}.corrupt-{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        state_path.replace(aside)
        return {}, f"state file was unreadable ({type(ex).__name__}); moved to {aside.name}; this run is a new baseline"


class RunLock:
    """One monitoring run at a time (MON-16): an exclusive lock file next to the state."""
    def __init__(self, state_path: Path):
        self.path = state_path.with_suffix(".lock")

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise RuntimeError(f"another monitoring run holds {self.path}; remove it only if no run is active")
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return self

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)


def write_outputs(result: dict, state_path: Path, report_dir: Path, date: str) -> dict:
    """Report and alerts first, then the state (MON-02): if a report cannot be written, the state is not advanced and the
    next run repeats the alerts. Reports are never overwritten (exclusive create). A heartbeat file records the run."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    n, rep = 1, report_dir / f"CL_source_monitoring_report_{date}.md"
    while True:
        try:
            fd = os.open(rep, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            n += 1
            rep = report_dir / f"CL_source_monitoring_report_{date}_run{n}.md"
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(report_markdown(result, date))
    alerts = rep.with_name(rep.stem.replace("report", "alerts") + ".json")
    alerts.write_text(json.dumps({"run_at": result["run_at"], "alerts": result["alerts"], "proposals": result["proposals"],
                                  "warnings": result.get("warnings", [])}, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result["state"], indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(state_path)                      # atomic: a crashed run never leaves a half-written state
    beat = state_path.with_name("CL_monitor_heartbeat.json")
    beat.write_text(json.dumps({"last_run": result["run_at"], "checked": result["checked"],
                                "high_alerts": sum(a["severity"] == "high" for a in result["alerts"]),
                                "report": rep.name}, indent=1), encoding="utf-8")
    return {"state": str(state_path), "report": str(rep), "alerts": str(alerts), "heartbeat": str(beat)}
