"""Source discovery: find official documents on listing pages that the register does not know yet, and propose them as
candidates (activated: false, kb_status: not_ingested, evidence observed_listing_only). Input is any listing page:
HTML (local fetch or fixture) or a Firecrawl scrape result (markdown + links). Writing the proposals into the register
is a separate, explicit step that creates a new register version; nothing is ever activated or collected here."""
from __future__ import annotations

import copy
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

from ..kb import OFFICIAL_HOSTS
from .register import REGISTER

RELEVANT = re.compile(r"\bVAT\b|value added tax|decree[- ]law no\.? ?\(?8\)? of 2017|executive regulation|cabinet decision"
                      r"|\bVATP\d+|\bVATG\w+|deregist|registration|tax procedures|administrative penalt", re.I)
DOC_EXT = (".pdf", ".aspx", ".html", ".htm")
# Other taxes on the same FTA listings: not HerBiz's VAT scope (excise goods, corporate tax, top-up tax, tobacco marking)
OUT_OF_SCOPE = re.compile(r"\bexcise\b|corporate tax|top-?up tax|tobacco|non-resident person.?s nexus|\bCT\b|economic substance", re.I)
DATE_RX = re.compile(r"(Issue|Publish(?:ed)?)\s*date\s*:?\s*([A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})", re.I)


def norm_url(url: str) -> str:
    """Compare URLs the way the FTA site serves them: case-insensitive host, '//' collapsed, %20 == space, no trailing '/'."""
    p = urlparse(url.strip())
    path = re.sub(r"/{2,}", "/", unquote(p.path)).rstrip("/").lower()
    return f"{(p.hostname or '').lower().removeprefix('www.')}{path}" + (f"?{p.query.lower()}" if p.query else "")


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self._href, self._text, self.after = [], None, [], []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._text = dict(attrs).get("href"), []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)
        elif self.links:
            self.after.append((len(self.links) - 1, data))

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append({"href": self._href, "text": " ".join("".join(self._text).split())})
            self._href = None


def parse_listing(content: str, base_url: str, kind: str = "html") -> list[dict]:
    """Links on a listing page with their text and any 'Issue date' / 'Publish date' shown right after them."""
    entries = []
    if kind == "html":
        p = _Links()
        p.feed(content)
        trailing: dict[int, str] = {}
        for i, t in p.after:
            trailing[i] = trailing.get(i, "") + " " + t
        for i, a in enumerate(p.links):
            if not a["href"]:
                continue
            entries.append({"url": urljoin(base_url, a["href"]), "title": a["text"], "context": " ".join(trailing.get(i, "").split())[:300]})
    else:  # markdown from Firecrawl: [text](url "title attribute") followed by text
        for m in re.finditer(r"\[((?:[^\[\]]|\[[^\]]*\])*)\]\((https?://[^)\s]+)(?:\s+\"([^\"]*)\")?\)([^\[]{0,300})", content, re.S):
            text = " ".join(re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", m.group(1)).replace("\\", " ").split())
            title = (m.group(3) or "").strip()
            if title.lower().endswith((".pdf", ".docx", ".doc")):
                title = title.rsplit(".", 1)[0]
            useful = text if len(text) > 12 and not re.fullmatch(r"[\d.,]+\s*[KM]B", text) else ""
            entries.append({"url": m.group(2), "title": title or useful, "context": " ".join(m.group(4).split())})
    out = []
    for e in entries:
        dates = {k.lower().startswith("issue") and "issue_date_shown" or "publish_date_shown": v for k, v in DATE_RX.findall(e["context"])}
        out.append({**e, **dates})
    return out


def known_urls(reg: dict) -> set[str]:
    urls = set()
    for s in reg.get("sources", []):
        for v in s.get("versions", []):
            urls.add(norm_url(v["url"]))
    for c in reg.get("candidates", []):
        for k in ("url", "listing_page_url"):
            if c.get(k):
                urls.add(norm_url(c[k]))
    return urls


def propose(entries: list[dict], register_path: Path = REGISTER, listing_url: str = "", observed_at: str = "") -> dict:
    reg = json.loads(Path(register_path).read_text(encoding="utf-8"))
    known = known_urls(reg)
    proposals, skipped = [], {"known": 0, "not_official_host": 0, "not_a_document": 0, "not_relevant": 0}
    seen = set()
    for e in entries:
        u = norm_url(e["url"])
        host = (urlparse(e["url"]).hostname or "").lower()
        if u in seen:
            continue
        seen.add(u)
        if u in known:
            skipped["known"] += 1
        elif not any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS):
            skipped["not_official_host"] += 1
        elif not urlparse(e["url"]).path.lower().endswith(DOC_EXT):
            skipped["not_a_document"] += 1
        elif not RELEVANT.search(e["title"] + " " + re.sub(r"[-_./]+", " ", unquote(e["url"]))):
            skipped["not_relevant"] += 1
        elif OUT_OF_SCOPE.search(e["title"] or "") and not re.search(r"\bVAT\b|value added", e["title"] or "", re.I):
            skipped.setdefault("other_tax", 0)
            skipped["other_tax"] += 1
        else:
            proposals.append({
                "candidate_id": "DISC-" + re.sub(r"[^A-Z0-9]+", "-", unquote(urlparse(e["url"]).path.rsplit("/", 1)[-1]).upper())[:60].strip("-"),
                "title": e["title"] or None, "issuing_authority": None, "document_type": None, "scope": "to classify",
                "language": "ar" if "arabic" in e["url"].lower() or "/ar/" in e["url"].lower() else None,
                "translation_status": "unknown", "url": e["url"], "listing_page_url": listing_url or None,
                "issue_date": None, "effective_date": None, "reference_code": None, "version_label": None,
                "dates_shown_on_listing": {k: e[k] for k in ("issue_date_shown", "publish_date_shown") if k in e} or None,
                "articles_relevant": None, "relation_to_existing": "new (discovered on listing)",
                "evidence": f"observed_listing_only: {listing_url or 'listing'} {observed_at}".strip(),
                "confidence": "low", "notes": "Proposed by rag_c discovery. A person must classify it before any collection.",
                "open_questions": None, "verification_status": "pending_verification", "activated": False,
                "kb_status": "not_ingested", "researched_by": "rag_c discovery"})
    return {"listing_url": listing_url, "entries": len(entries), "proposals": proposals, "skipped": skipped}


def add_proposals(register_path: Path, proposals: list[dict], date: str, by: str = "rag_c discovery") -> dict:
    """New register content with the proposals appended and a PATCH version bump. Returns the dict; the caller writes it."""
    reg = json.loads(Path(register_path).read_text(encoding="utf-8"))
    new = copy.deepcopy(reg)
    have = {c["candidate_id"] for c in new.get("candidates", [])}
    added = []
    for p in proposals:
        cid, n = p["candidate_id"], 2
        while cid in have:
            cid, n = f"{p['candidate_id']}-{n}", n + 1
        have.add(cid)
        new.setdefault("candidates", []).append({**p, "candidate_id": cid})
        added.append(cid)
    if added:
        major, minor, patch = (int(x) for x in new["register_version"].split("."))
        new["register_version"] = f"{major}.{minor}.{patch + 1}"
        new["changes"].append({"version": new["register_version"], "date": date, "by": by,
                               "what": f"Discovery proposals added as candidates (not activated): {', '.join(added)}"})
    return new
