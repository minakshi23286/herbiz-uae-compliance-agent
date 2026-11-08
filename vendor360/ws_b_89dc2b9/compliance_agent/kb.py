"""Knowledge base pipeline: collect -> snapshot -> extract -> passages -> full-text index -> source version (candidate).

    python3 -m compliance_agent.kb collect  [--db data/CL_compliance.sqlite3] [--manifest knowledge_base/CL_source_manifest.json]
    python3 -m compliance_agent.kb status   [--db ...]
    python3 -m compliance_agent.kb search "mandatory registration threshold" [--db ...]
    python3 -m compliance_agent.kb interpret [--db ...] [--file knowledge_base/CL_draft_interpretations.json]

Rules: only allowlisted official hosts; originals stored unchanged under data/raw/ and referenced by hash; extraction
failures and empty pages recorded, never filled in; every capture becomes a CANDIDATE source version that a human must
approve; extracted text is labelled UNVERIFIED_EXTRACTION until a person checks it against the original.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from .clock import SystemClock, iso
from . import sources as S
from .engine import Engine, WorkflowError
from .store import Store

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OFFICIAL_HOSTS = {"tax.gov.ae", "mof.gov.ae", "u.ae", "elaws.moj.gov.ae", "uaelegislation.gov.ae"}
USER_AGENT = "HerBizComplianceAgent/0.1 (local research prototype; contact via project owner)"
MAX_BYTES = 40 * 1024 * 1024
MIN_PAGE_CHARS = 40          # a page with less text than this is treated as having no text layer


class CollectError(Exception):
    pass


# ------------------------------------------------------------------ fetch
def check_host(url: str) -> None:
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS):
        raise CollectError(f"refused: {url} is not on the official-source allowlist {sorted(OFFICIAL_HOSTS)}")


def _tls_context() -> ssl.SSLContext:
    """Certificate checks stay ON. python.org builds on macOS ship without a CA bundle, so use certifi when present."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def http_fetch(url: str, attempts: int = 2) -> tuple[bytes, str]:
    check_host(url)
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url.replace(" ", "%20"), headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60, context=_tls_context()) as r:
                final = r.geturl()
                check_host(final)  # redirects must stay on the allowlist
                data = r.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise CollectError("document larger than the 40 MB limit")
                return data, r.headers.get_content_type()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as ex:
            last = ex
            time.sleep(2 * (i + 1))
    raise CollectError(f"unavailable after {attempts} attempts: {last}")


# ------------------------------------------------------------------ extract
class _TextHTML(HTMLParser):
    SKIP = {"script", "style", "nav", "header", "footer", "noscript", "svg", "button", "select"}  # not "form": ASP.NET wraps whole pages in one
    BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "td", "th", "div", "section", "article", "br", "tr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.blocks: list[str] = []
        self.cur: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self._flush()

    def handle_data(self, data):
        if not self.skip:
            self.cur.append(data)

    def _flush(self):
        t = re.sub(r"\s+", " ", "".join(self.cur)).strip()
        if t:
            self.blocks.append(t)
        self.cur = []


def extract_html(data: bytes, must_contain: str | None = None) -> dict:
    p = _TextHTML()
    p.feed(data.decode("utf-8", errors="replace"))
    p._flush()
    blocks = [b for b in p.blocks if len(b) >= 60]
    seen, uniq = set(), []
    for b in blocks:  # navigation repeats; keep first occurrence
        if b not in seen:
            seen.add(b)
            uniq.append(b)
    if must_contain:  # keep the content region around the anchor phrase, drop site-wide news and menus
        idx = next((i for i, b in enumerate(uniq) if must_contain.lower() in b.lower()), None)
        if idx is None:
            return {"status": "failed", "extractor": "html.parser", "pages": None, "empty_pages": [],
                    "note": f"anchor phrase not found: {must_contain!r}", "units": []}
        uniq = uniq[idx: idx + 12]
    units = [{"locator": f"Paragraph {i + 1}", "page_start": None, "page_end": None, "text": b} for i, b in enumerate(uniq)]
    return {"status": "ok" if units else "failed", "extractor": "html.parser (stdlib)", "pages": None,
            "empty_pages": [], "note": "" if units else "no text blocks found", "units": units}


def _pdf_pages(path: Path) -> tuple[list[str], str]:
    pypdf_error = None
    try:
        import pypdf  # optional; see requirements-optional.txt
        try:
            reader = pypdf.PdfReader(str(path))
            return [(pg.extract_text() or "") for pg in reader.pages], f"pypdf {pypdf.__version__}"
        except Exception as ex:  # malformed or encrypted PDF: try the second extractor, then report
            pypdf_error = f"pypdf: {type(ex).__name__}: {ex}"
    except ImportError:
        pass
    exe = shutil.which("pdftotext")
    if not exe:
        raise CollectError("no PDF text extractor available (install pypdf or poppler pdftotext)")
    out = subprocess.run([exe, "-layout", str(path), "-"], capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        raise CollectError(f"pdftotext failed: {out.stderr.strip()[:200]}" + (f"; {pypdf_error}" if pypdf_error else ""))
    return out.stdout.split("\f"), "pdftotext (poppler)"


# Headings seen in FTA publications: "Article 7 – Mandatory Registration", "Article 14 (bis) - Title", "Article (13)".
# In-text references ("Article 21 of the Decree-Law") are not headings: a heading has a dash title or nothing after it.
ARTICLE_RX = re.compile(r"^[ \t]*Article[ \t]*\(?[ \t]*(\d+)[ \t]*\)?((?:[ \t]*\((?:bis|repeated|\d+)\))?)[ \t]*(?:[–—-][ \t]*(.*)|[ \t]*)$", re.I | re.M)


def strip_running_headers(pages: list[str]) -> tuple[list[str], list[str]]:
    """Remove lines repeated on most pages (running headers/footers, page numbers). Returns cleaned pages + removed lines."""
    from collections import Counter
    key = lambda ln: re.sub(r"\d+", "#", ln.strip())
    counts = Counter(k for pg in pages for k in {key(ln) for ln in pg.splitlines() if ln.strip()})
    common = {k for k, n in counts.items() if len(pages) >= 4 and n >= 0.6 * len(pages) and k not in ("#", "")}
    common |= {"#"}  # bare page numbers
    cleaned = ["\n".join(ln for ln in pg.splitlines() if key(ln) not in common) for pg in pages]
    return cleaned, sorted(common - {"#"})


def extract_pdf(path: Path, split: str = "article") -> dict:
    pages, extractor = _pdf_pages(path)
    pages, removed_headers = strip_running_headers(pages)
    empty = [i + 1 for i, t in enumerate(pages) if len(t.strip()) < MIN_PAGE_CHARS]
    units: list[dict] = []
    repairs: list[str] = []
    prev_no = 0

    def heading_no(raw: str) -> str:
        """Footnote markers can merge into the heading number ("Article 83" + footnote 37 -> "8337").
        Accept the number if it follows on; otherwise, if it starts with the expected next number, use that and record it."""
        nonlocal prev_no
        n = int(raw)
        if prev_no and not (prev_no <= n <= prev_no + 3) and raw.startswith(str(prev_no + 1)):
            repairs.append(f"heading 'Article {raw}' read as Article {prev_no + 1} (footnote marker merged)")
            n = prev_no + 1
        prev_no = max(prev_no, n) if n <= prev_no + 3 or not prev_no else prev_no
        return str(n)

    if split == "article":
        cur = None
        for pno, text in enumerate(pages, start=1):
            pos = 0
            for m in ARTICLE_RX.finditer(text):
                if cur is not None:
                    cur["text"] += text[pos:m.start()]
                    if text[pos:m.start()].strip():
                        cur["page_end"] = pno
                    units.append(cur)
                elif text[pos:m.start()].strip():
                    units.append({"locator": f"Front matter, p. {pno}", "page_start": pno, "page_end": pno, "text": text[pos:m.start()]})
                cur = {"locator": f"Article {heading_no(m.group(1))}{(' ' + m.group(2).strip()) if m.group(2).strip() else ''}",
                       "page_start": pno, "page_end": pno, "text": ""}
                pos = m.start()
            if cur is not None:
                cur["text"] += text[pos:]
                if text[pos:].strip():
                    cur["page_end"] = pno
            elif text[pos:].strip():
                units.append({"locator": f"Front matter, p. {pno}", "page_start": pno, "page_end": pno, "text": text[pos:]})
        if cur is not None:
            units.append(cur)
    if not units or split == "page":
        units = [{"locator": f"Page {i + 1}", "page_start": i + 1, "page_end": i + 1, "text": t} for i, t in enumerate(pages)]
    final = []
    for u in units:
        t = re.sub(r"[ \t]+", " ", u["text"]).strip()
        if not t:
            continue
        pg = f"p. {u['page_start']}" if u["page_start"] == u["page_end"] else f"pp. {u['page_start']}-{u['page_end']}"
        loc = u["locator"] if u["locator"].startswith(("Front", "Page")) else f"{u['locator']}, {pg}"
        parts = [t[i:i + 3000] for i in range(0, len(t), 3000)] or [t]
        for k, part in enumerate(parts):
            final.append({"locator": loc + (f", part {k + 1}" if len(parts) > 1 else ""), "page_start": u["page_start"],
                          "page_end": u["page_end"], "text": part})
    status = "ok" if not empty else ("partial" if len(empty) < len(pages) else "failed")
    note = ("Locator repairs: " + "; ".join(repairs) + ". ") if repairs else ""
    if removed_headers:
        note += "Running headers removed: " + " | ".join(h[:80] for h in removed_headers) + ". "
    if empty:
        note += (f"{len(empty)} of {len(pages)} pages have no usable text layer; OCR not available on this machine "
                "(tesseract absent). Those pages are NOT in the knowledge base.")
    return {"status": status, "extractor": extractor, "pages": len(pages), "empty_pages": empty, "note": note, "units": final}


# ------------------------------------------------------------------ pipeline
class KnowledgeBase:
    def __init__(self, engine: Engine, data_dir: Path = DATA, fetch=http_fetch, lock_path: Path | None = None):
        self.e = engine
        # The lock file lives next to the corpus it describes; tests pass a temporary folder and never touch the real one.
        self.LOCK = Path(lock_path) if lock_path else (ROOT / "knowledge_base" / "CL_collected_lock.json" if Path(data_dir) == DATA
                                                       else Path(data_dir) / "CL_collected_lock.json")
        self.s = engine.s
        self.data_dir = Path(data_dir)
        self.fetch = fetch

    def _attempt(self, source_id: str, url: str, outcome: str, detail: str) -> None:
        with self.s.db:
            self.s.db.execute("INSERT INTO collection_attempts (source_id, url, at, outcome, detail) VALUES (?,?,?,?,?)",
                              (source_id, url, self.e.now(), outcome, detail[:1000]))
            self.e._audit("collector", f"collection_{outcome}", "source", source_id, {"url": url, "detail": detail[:300]})

    def collect(self, entry: dict) -> dict:
        sid, url = entry["source_id"], entry["url"]
        try:
            data, mime = self.fetch(url)
        except CollectError as ex:
            outcome = "refused" if str(ex).startswith("refused") else "failed"
            self._attempt(sid, url, outcome, str(ex))
            return {"source_id": sid, "outcome": outcome, "detail": str(ex)}
        res = self.register(entry, data, mime)
        if res.get("doc_id") and res["outcome"] != "failed":
            self._lock(entry, data, mime)
        return res

    def _lock(self, entry: dict, data: bytes, mime: str) -> None:
        """Record what was collected (hash, size, time) so the corpus can be rebuilt offline. No document text here."""
        lock = json.loads(self.LOCK.read_text(encoding="utf-8")) if self.LOCK.exists() else {"documents": []}
        sha = hashlib.sha256(data).hexdigest()
        if any(d["sha256"] == sha and d["source_id"] == entry["source_id"] for d in lock["documents"]):
            return
        doc = self.s.one("SELECT retrieved_at, raw_path FROM documents WHERE source_id = ? AND sha256 = ?", (entry["source_id"], sha))
        lock["documents"].append({"source_id": entry["source_id"], "url": entry["url"], "sha256": sha, "bytes": len(data),
                                  "mime": mime, "retrieved_at": doc["retrieved_at"], "raw_path": doc["raw_path"]})
        self.LOCK.write_text(json.dumps(lock, indent=1) + "\n", encoding="utf-8")

    def rebuild(self, manifest: dict) -> list[dict]:
        """Offline: re-register every locked snapshot, in collection order, from data/raw/. Missing or altered files are reported."""
        lock = json.loads(self.LOCK.read_text(encoding="utf-8"))
        by_key = {(m["source_id"], m["url"]): m for m in manifest["sources"]}
        out = []
        for d in lock["documents"]:
            path = self.data_dir / d["raw_path"]
            entry = by_key.get((d["source_id"], d["url"])) or next((m for m in manifest["sources"] if m["source_id"] == d["source_id"]), None)
            if not path.exists():
                self._attempt(d["source_id"], d["url"], "failed", f"raw snapshot missing: {d['raw_path']}")
                out.append({"source_id": d["source_id"], "outcome": "failed", "detail": "raw snapshot missing"})
                continue
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != d["sha256"]:
                self._attempt(d["source_id"], d["url"], "failed", "raw snapshot hash mismatch (file altered)")
                out.append({"source_id": d["source_id"], "outcome": "failed", "detail": "hash mismatch"})
                continue
            out.append(self.register(dict(entry, url=d["url"]), data, d["mime"], d["retrieved_at"]))
        return out

    def register(self, entry: dict, data: bytes, mime: str, retrieved_at: str | None = None) -> dict:
        sid, url = entry["source_id"], entry["url"]
        sha = hashlib.sha256(data).hexdigest()
        retrieved_at = retrieved_at or self.e.now()
        dup = self.s.one("SELECT * FROM documents WHERE source_id = ? AND sha256 = ?", (sid, sha))
        if dup:
            self._attempt(sid, url, "identical", f"same bytes as {dup['doc_id']}; nothing new stored")
            return {"source_id": sid, "outcome": "identical", "doc_id": dup["doc_id"]}
        is_pdf = data[:5] == b"%PDF-" or mime == "application/pdf"
        ext = "pdf" if is_pdf else "html"
        rel = Path("raw") / sid / f"{sha[:16]}.{ext}"
        dest = self.data_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(data)
        try:
            ex = extract_pdf(dest, entry.get("split", "article")) if is_pdf else extract_html(data, entry.get("anchor"))
        except CollectError as err:
            ex = {"status": "failed", "extractor": "none", "pages": None, "empty_pages": [], "note": str(err), "units": []}
        doc_id = f"{sid}:{sha[:12]}"
        full_text = "\n\n".join(f"[{u['locator']}]\n{u['text']}" for u in ex["units"])
        with self.s.db:
            self.s.db.execute(
                "INSERT INTO documents (doc_id, source_id, origin_label, url, retrieved_at, sha256, bytes, mime, raw_path,"
                " extraction_status, extractor, pages, empty_pages_json, extraction_note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (doc_id, sid, "REAL_OFFICIAL_SOURCE", url, retrieved_at, sha, len(data), "application/pdf" if is_pdf else mime,
                 str(rel), ex["status"], ex["extractor"], ex["pages"], json.dumps(ex["empty_pages"]), ex["note"]))
        if ex["status"] == "failed":
            self._attempt(sid, url, "failed", f"extraction failed: {ex['note']}")
            return {"source_id": sid, "outcome": "failed", "doc_id": doc_id, "detail": ex["note"]}
        try:
            res = self.e.ingest_source({
                "source_id": sid, "origin_label": "REAL_OFFICIAL_SOURCE", "doc_id": doc_id,
                "issuing_authority": entry["issuing_authority"], "authority_type": entry["authority_type"],
                "jurisdiction": entry["jurisdiction"], "document_title": entry["document_title"], "source_url": url,
                "locator": "see passages", "publication_date": entry.get("publication_date"),
                "effective_date": entry.get("effective_date"), "retrieved_at": retrieved_at, "text": full_text,
                "obligations": []}, actor="collector")
        except WorkflowError as err:
            self._attempt(sid, url, "failed", f"registration refused: {err}")
            return {"source_id": sid, "outcome": "failed", "doc_id": doc_id, "detail": str(err)}
        vid = res["version_id"]
        with self.s.db:
            self.s.db.execute("UPDATE documents SET version_id = ? WHERE doc_id = ?", (vid, doc_id))
        if res["change_class"] == "identical":  # new bytes, same extracted text: keep the snapshot, index nothing twice
            self._attempt(sid, url, "identical", f"bytes changed but extracted text is identical to {vid}; no new passages")
            return {"source_id": sid, "outcome": "identical", "doc_id": doc_id, "version_id": vid}
        with self.s.db:
            for i, u in enumerate(ex["units"], start=1):
                pid = f"{doc_id}#{i:04d}"
                self.s.db.execute("INSERT INTO passages VALUES (?,?,?,?,?,?,?,?,?)",
                                  (pid, doc_id, vid, i, u["locator"], u["page_start"], u["page_end"], u["text"], "UNVERIFIED_EXTRACTION"))
                self.s.db.execute("INSERT INTO passages_fts (passage_id, locator, text) VALUES (?,?,?)", (pid, u["locator"], u["text"]))
        outcome = {"first_version": "new_version", "substantive": "new_version", "cosmetic": "cosmetic", "identical": "identical"}[res["change_class"]]
        self._attempt(sid, url, outcome, f"{vid} {res['status']}; {len(ex['units'])} passages; extraction {ex['status']} ({ex['extractor']}) {ex['note']}")
        return {"source_id": sid, "outcome": outcome, "doc_id": doc_id, "version_id": vid, "status": res["status"],
                "passages": len(ex["units"]), "extraction": ex["status"], "empty_pages": ex["empty_pages"]}

    # -------------------------------------------------------------- read side
    def search(self, query: str, limit: int = 20, all_versions: bool = False) -> dict:
        terms = re.findall(r"[A-Za-z0-9]{2,}", query)
        if not terms:
            return {"mode": "SQLite FTS5 full-text search (BM25), no AI model", "query": query, "hits": []}
        quoted = [f'"{t}"' for t in terms]  # quoted terms: user text never becomes FTS syntax
        rows, seen = [], set()
        for match in (" ".join(quoted), " OR ".join(quoted)):  # passages with every word first, then any word
            for r in self._fts(match, limit, all_versions):
                if r["passage_id"] not in seen and len(rows) < limit:
                    seen.add(r["passage_id"])
                    r["matched"] = "all words" if match == " ".join(quoted) else "some words"
                    rows.append(r)
        return {"mode": "SQLite FTS5 full-text search (BM25), no AI model", "query": query, "hits": rows}

    def _fts(self, match: str, limit: int, all_versions: bool = False) -> list[dict]:
        latest = "" if all_versions else (
            " AND p.version_id IN (SELECT version_id FROM source_versions sv WHERE status != 'rejected' AND seq ="
            " (SELECT MAX(seq) FROM source_versions s2 WHERE s2.source_id = sv.source_id AND s2.status != 'rejected'))")
        return self.s.q(
            "SELECT f.passage_id, bm25(passages_fts) AS rank, snippet(passages_fts, 2, '[', ']', ' … ', 18) AS snip,"
            " p.locator, p.label, p.doc_id, d.source_id, d.origin_label, d.url, v.status AS source_status, v.document_title"
            " FROM passages_fts f JOIN passages p ON p.passage_id = f.passage_id JOIN documents d ON d.doc_id = p.doc_id"
            " LEFT JOIN source_versions v ON v.version_id = p.version_id"
            " WHERE passages_fts MATCH ?" + latest + " ORDER BY rank LIMIT ?", (match, limit))

    def compare(self, old_version: str, new_version: str) -> dict:
        """Article-by-article comparison of two captured versions of one source.
        cosmetic = equal after removing layout noise and footnote markers; substantive = wording differs. Advisory only:
        a person decides whether a wording change matters."""
        def units(vid):
            out: dict[str, str] = {}
            for r in self.s.q("SELECT locator, text FROM passages WHERE version_id = ? ORDER BY seq", (vid,)):
                m = re.match(r"(Article \d+(?: \(\w+\))?|Paragraph \d+|Page \d+|Front matter)", r["locator"])
                k = m.group(1) if m else r["locator"]
                out[k] = out.get(k, "") + " " + r["text"]
            return out

        def defoot(t: str) -> str:
            t = re.sub(r"^\s*\d{1,3}\s+(?:Article|Clause|Paragraph|Item|Definition|Point|This|The)\b.*?(?:amended|added|repealed|replaced|inserted).*$",
                       " ", t, flags=re.M | re.I)                      # footnote lines: "8 Article amended as per ..."
            t = re.sub(r"(?<=[A-Za-z\)])[ \t]?\d{1,3}[ \t]*$", " ", t, flags=re.M)  # footnote markers at line ends
            return t

        squash = lambda t: re.sub(r"[\s\u200b]+", "", S.normalize(defoot(t)))     # PDF word breaks differ between versions
        words = lambda t: S.normalize(defoot(t)).split()

        a, b = units(old_version), units(new_version)
        rows = []
        for k in list(dict.fromkeys(list(a) + list(b))):
            if k not in a:
                rows.append({"unit": k, "change": "added", "old": "", "new": b[k][:600]})
            elif k not in b:
                rows.append({"unit": k, "change": "removed", "old": a[k][:600], "new": ""})
            elif S.normalize(a[k]) == S.normalize(b[k]):
                continue
            elif squash(a[k]) == squash(b[k]):
                rows.append({"unit": k, "change": "cosmetic", "old": "", "new": ""})
            else:
                import difflib
                wa, wb = words(a[k]), words(b[k])
                sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
                ops = [(" ".join(wa[i1:i2])[:200], " ".join(wb[j1:j2])[:200]) for t, i1, i2, j1, j2 in sm.get_opcodes()
                       if t != "equal" and "".join(wa[i1:i2]) != "".join(wb[j1:j2])]
                if not ops:  # only word-break differences
                    rows.append({"unit": k, "change": "cosmetic", "old": "", "new": ""})
                    continue
                rows.append({"unit": k, "change": "substantive", "old": " / ".join(o for o, _ in ops[:4]),
                             "new": " / ".join(n for _, n in ops[:4]), "edits": len(ops)})
        summary = {c: sum(1 for r in rows if r["change"] == c) for c in ("added", "removed", "cosmetic", "substantive")}
        return {"old": old_version, "new": new_version, "summary": summary, "rows": rows,
                "note": "Machine comparison to help a reviewer. It does not decide what changed in law."}

    def passage(self, passage_id: str) -> dict | None:
        return self.s.one("SELECT * FROM passages WHERE passage_id = ?", (passage_id,))

    def status(self) -> dict:
        q = lambda sql: self.s.one(sql)["n"]
        return {
            "real_sources": q("SELECT COUNT(DISTINCT source_id) n FROM documents WHERE origin_label='REAL_OFFICIAL_SOURCE'"),
            "documents": q("SELECT COUNT(*) n FROM documents"),
            "extracted_ok": q("SELECT COUNT(*) n FROM documents WHERE extraction_status='ok'"),
            "extracted_partial": q("SELECT COUNT(*) n FROM documents WHERE extraction_status='partial'"),
            "extraction_failed": q("SELECT COUNT(*) n FROM documents WHERE extraction_status='failed'"),
            "collection_failures": q("SELECT COUNT(DISTINCT source_id) n FROM collection_attempts WHERE outcome IN ('failed','refused')"
                                     " AND source_id NOT IN (SELECT source_id FROM documents)"),
            "passages": q("SELECT COUNT(*) n FROM passages"),
            "approved_real_versions": q("SELECT COUNT(*) n FROM source_versions WHERE origin_label='REAL_OFFICIAL_SOURCE' AND status='approved'"),
            "draft_interpretations": q("SELECT COUNT(*) n FROM obligations o JOIN source_versions v ON v.version_id=o.version_id"
                                       " WHERE v.origin_label='REAL_OFFICIAL_SOURCE' AND o.interpretation_status='unreviewed'"),
            "reviewed_interpretations_real": q("SELECT COUNT(*) n FROM obligations o JOIN source_versions v ON v.version_id=o.version_id"
                                               " WHERE v.origin_label='REAL_OFFICIAL_SOURCE' AND o.interpretation_status='reviewed'"),
            "attempts": self.s.q("SELECT source_id, url, at, outcome, detail FROM collection_attempts ORDER BY attempt_id"),
            "documents_list": self.s.q("SELECT doc_id, source_id, origin_label, url, retrieved_at, substr(sha256,1,16) AS sha, bytes,"
                                       " raw_path, extraction_status, extractor, pages, empty_pages_json, extraction_note, version_id FROM documents ORDER BY doc_id"),
        }

    def add_interpretations(self, items: list[dict]) -> list[dict]:
        """Attach draft (unreviewed) obligations to the latest captured version of a real source."""
        out = []
        for it in items:
            v = self.s.one("SELECT * FROM source_versions WHERE source_id = ? ORDER BY seq DESC LIMIT 1", (it["source_id"],))
            if not v:
                out.append({"obligation_key": it["obligation"]["obligation_key"], "outcome": "skipped: source not collected"})
                continue
            oid = f"{it['obligation']['obligation_key']}#{v['version_id']}"
            if self.s.one("SELECT 1 AS x FROM obligations WHERE obligation_id = ?", (oid,)):
                out.append({"obligation_id": oid, "outcome": "exists (retry-safe)"})
                continue
            ob = dict(it["obligation"], interpretation_status="unreviewed")
            with self.s.db:
                self.e._insert_obligation(v["version_id"], ob, v["text"])
            row = self.s.one("SELECT support_status FROM obligations WHERE obligation_id = ?", (oid,))
            out.append({"obligation_id": oid, "outcome": "draft recorded", "support_status": row["support_status"]})
        return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["collect", "rebuild", "setup", "status", "search", "interpret"])
    ap.add_argument("query", nargs="?")
    ap.add_argument("--db", default=str(DATA / "CL_compliance.sqlite3"))
    ap.add_argument("--manifest", default=str(ROOT / "knowledge_base" / "CL_source_manifest.json"))
    ap.add_argument("--file", default=str(ROOT / "knowledge_base" / "CL_draft_interpretations.json"))
    a = ap.parse_args(argv)
    kb = KnowledgeBase(Engine(Store(a.db), SystemClock()))
    if a.cmd == "setup":  # offline: rebuild the corpus from data/raw + record draft interpretations (both retry-safe)
        man = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
        for r in kb.rebuild(man):
            print(json.dumps({k: r.get(k) for k in ("source_id", "outcome", "version_id", "passages")}, ensure_ascii=False))
        for m in man["sources"]:  # sources never captured stay visible as failures
            if not kb.s.one("SELECT 1 AS x FROM documents WHERE source_id = ?", (m["source_id"],)):
                kb._attempt(m["source_id"], m["url"], "failed", "never collected successfully (see CL_collected_lock.json)")
        items = json.loads(Path(a.file).read_text(encoding="utf-8"))["interpretations"]
        print(json.dumps(kb.add_interpretations(items), ensure_ascii=False))
        st = kb.status()
        print(json.dumps({k: v for k, v in st.items() if not isinstance(v, list)}, ensure_ascii=False))
        return 0
    if a.cmd == "collect":
        man = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
        for entry in man["sources"]:
            print(json.dumps(kb.collect(entry), ensure_ascii=False))
    elif a.cmd == "rebuild":
        man = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
        for r in kb.rebuild(man):
            print(json.dumps(r, ensure_ascii=False))
        for m in man["sources"]:  # sources never captured stay visible as failures
            if not kb.s.one("SELECT 1 AS x FROM documents WHERE source_id = ?", (m["source_id"],)):
                kb._attempt(m["source_id"], m["url"], "failed", "never collected successfully (see CL_collected_lock.json)")
    elif a.cmd == "status":
        st = kb.status()
        st.pop("documents_list")
        print(json.dumps(st, indent=1, ensure_ascii=False))
    elif a.cmd == "search":
        print(json.dumps(kb.search(a.query or ""), indent=1, ensure_ascii=False))
    elif a.cmd == "interpret":
        items = json.loads(Path(a.file).read_text(encoding="utf-8"))["interpretations"]
        print(json.dumps(kb.add_interpretations(items), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
