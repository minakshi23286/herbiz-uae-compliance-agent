"""Read-only retrieval from the existing knowledge base. Opens SQLite with mode=ro: this module cannot write.

Deliberately does not use the app's Store class, which applies schema updates when it opens a database.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

MAX_INTENT_ADD = 6   # intent passages added after the BM25 results (v5)
MAX_TOTAL_ADD = 7    # intent + title passages together (v5): keeps the average under the 12-passage gate
TITLE_FUNCTION_WORDS = {"when", "into", "for", "the", "of", "in", "on", "by", "a", "an", "to", "and", "or", "with", "from",
                        "between", "before", "after", "under", "its", "their", "this", "that", "as", "at", "case"}
STOP = {"the", "and", "for", "what", "does", "need", "with", "my", "is", "are", "do", "to", "of", "in", "on", "a",
        "an", "i", "me", "how", "it", "this", "that", "be", "or", "if", "can", "will", "have", "has", "at", "by"}


def file_md5(path: str | Path) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def connect_ro(path: str | Path) -> sqlite3.Connection:
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(p)
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _stem(w: str) -> str:
    """Word root for heading matching: the first 6 letters of longer words, so register / registered / registration
    and voluntary / voluntarily match. Short words must match exactly."""
    return w[:6] if len(w) >= 6 else w


# Owner wording -> the law's wording. Used ONLY to choose the extra heading passages (never the main results).
# Kept small and explicit; every entry is a concept the Decree-Law / Executive Regulation names in an article title.
OWNER_TO_LAW = {
    "cancel": ["deregistration"], "cancelled": ["deregistration"], "cancellation": ["deregistration"],
    "deregister": ["deregistration"],
    "count": ["calculating"], "counts": ["calculating"], "counted": ["calculating"], "counting": ["calculating"],
    "include": ["calculating"], "included": ["calculating"], "add": ["calculating"], "added": ["calculating"],
    "threshold": ["registration"],
    "foreign": ["non", "resident"], "overseas": ["non", "resident"], "abroad": ["non", "resident"],
    "related": ["related", "parties"], "sister": ["related"], "partner": ["related"],
    "group": ["group"],
    "based": ["resident"],   # "a business not based in the UAE" -> "Non-Resident"
}


def article_heading(text: str, locator: str) -> str:
    """The article's own title, e.g. 'Calculating the Tax Registration Threshold'. Empty for non-article passages."""
    if not locator.startswith("Article"):
        return ""
    first = text.strip().splitlines()[0] if text.strip() else ""
    return re.sub(r"^Article\s*\d+\s*(\(\w+\))?\s*[–—-]\s*", "", first)


def search(con: sqlite3.Connection, question: str, k: int = 6, heading_extra: int = 3, pool: int = 40,
           use_concepts: bool = True, core_pack: bool = True) -> list[dict]:
    """BM25 over passages of the newest non-rejected version of each source; all words first, then any word.

    Owners describe their situation in their own words ("does my salary count towards the threshold"); the law
    uses its own ("Calculating the Tax Registration Threshold"). The first k results are the plain BM25 results,
    unchanged. Then up to `heading_extra` further passages are ADDED (never swapped in) when their article title
    shares at least two content words with the question — the law's own titles act as its index.
    Each added passage carries `added_by: "heading"` so the ledger shows why it was retrieved."""
    terms = [t for t in re.findall(r"[A-Za-z0-9]{2,}", question.lower()) if t not in STOP]
    if not terms:
        return []
    quoted = [f'"{t}"' for t in terms]
    latest = (" AND p.version_id IN (SELECT version_id FROM source_versions sv WHERE status != 'rejected' AND seq ="
              " (SELECT MAX(seq) FROM source_versions s2 WHERE s2.source_id = sv.source_id AND s2.status != 'rejected'))")
    base, seen = [], set()
    for match in (" ".join(quoted), " OR ".join(quoted)):
        rows = con.execute(
            "SELECT p.passage_id, p.locator, p.text, d.source_id, d.url, v.document_title, v.status AS source_status"
            " FROM passages_fts f JOIN passages p ON p.passage_id = f.passage_id JOIN documents d ON d.doc_id = p.doc_id"
            " JOIN source_versions v ON v.version_id = p.version_id WHERE passages_fts MATCH ?" + latest +
            " ORDER BY bm25(passages_fts) LIMIT ?", (match, max(k, pool))).fetchall()
        for r in rows:
            if r["passage_id"] not in seen:
                seen.add(r["passage_id"])
                base.append(dict(r, added_by="bm25"))
    out = base[:k]
    if heading_extra:
        words = [t for t in terms if t.isalpha()]
        words += [x for t in words for x in OWNER_TO_LAW.get(t, [])]
        concepts: set[str] = set()
        if use_concepts:  # plain-English -> legal-term index (concepts.py); affects only the title step
            from .concepts_v5 import detect
            concepts, law_words = detect(question)
            words += law_words
        qstems = {_stem(t) for t in words}
        taken = {r["passage_id"] for r in out}
        rank = {r["passage_id"]: i for i, r in enumerate(base)}
        # every article of the newest versions is a candidate (about 150 titles), not only the BM25 pool
        arts = con.execute(
            "SELECT p.passage_id, p.locator, p.text, d.source_id, d.url, v.document_title, v.status AS source_status"
            " FROM passages p JOIN documents d ON d.doc_id = p.doc_id JOIN source_versions v ON v.version_id = p.version_id"
            " WHERE p.locator LIKE 'Article %'" + latest.replace("p.version_id IN", "p.version_id IN", 1) +
            " ORDER BY p.passage_id").fetchall()
        import math
        titles = {r["passage_id"]: {_stem(w) for w in re.findall(r"[a-z]{2,}", article_heading(r["text"], r["locator"]).lower())
                                    if w not in TITLE_FUNCTION_WORDS}
                  for r in arts}
        qstems -= {_stem(w) for w in TITLE_FUNCTION_WORDS}
        # (b) intent-specific primary provisions go in first (they replace the earlier blanket ER Art. 7 pack),
        #     so title slots are spent on OTHER articles; ambiguous questions get the alternatives.
        if core_pack and use_concepts:
            from .concepts_v5 import INTENT_PROVISIONS, intents as _intents, needs_base_rule, turnover_stated
            its, ambiguous = _intents(question)
            # v5 budget: primaries round-robin across intents (so every intent gets its first article before any
            # intent gets its second), then the base registration rule when needed, then one supporting article per
            # intent (not for ambiguous questions). At most MAX_INTENT_ADD intent passages; title slots fill the rest.
            wanted = []
            depth = max((len(INTENT_PROVISIONS[it]["primary"]) for it in its), default=0)
            for i in range(depth):
                for it in its:
                    prim = INTENT_PROVISIONS[it]["primary"]
                    if i < len(prim):
                        wanted.append(("primary", it, prim[i]))
            if needs_base_rule(question, its, ambiguous):
                wanted += [("base", "mandatory_registration", x) for x in INTENT_PROVISIONS["mandatory_registration"]["primary"]]
                if turnover_stated(question):   # v5 iter 2: a stated turnover is checked with the calculation article
                    wanted.append(("base", "threshold_calculation", ("FTA-VAT-DL8", 19)))
            if not ambiguous and len(its) == 1:   # v5 iter 2: supporting guidance only for single-topic questions
                wanted += [("supporting", it, x) for it in its for x in INTENT_PROVISIONS[it]["supporting"][:1]]
            added = 0
            for role, it, (src, art) in wanted:
                if added >= MAX_INTENT_ADD:
                    break
                if src == "FTA-VAT-REG-PAGE":
                    cond, args = "d.source_id = 'FTA-VAT-REG-PAGE' AND p.text LIKE ?", ("%registration threshold of AED%",)
                else:
                    cond, args = "d.source_id = ? AND (p.locator LIKE ? OR p.locator LIKE ?)", (src, f"Article {art},%", f"Article {art} (%")
                r = con.execute(
                    "SELECT p.passage_id, p.locator, p.text, d.source_id, d.url, v.document_title, v.status AS source_status"
                    " FROM passages p JOIN documents d ON d.doc_id = p.doc_id JOIN source_versions v ON v.version_id = p.version_id"
                    " WHERE " + cond + latest + " ORDER BY p.seq LIMIT 1", args).fetchone()
                if r and r["passage_id"] not in taken:
                    out.append(dict(r, added_by=f"intent:{it}:{role}" + (":ambiguous" if ambiguous else "")))
                    taken.add(r["passage_id"])
                    added += 1
                elif r:
                    pass   # already among the BM25 results: no slot spent
            # v5 iter 2: title matches are a fallback only (89% of them were irrelevant on the development sets)
            heading_extra = min(heading_extra, max(0, MAX_TOTAL_ADD - added)) if added < 2 else 0
        df: dict[str, int] = {}
        for hw in titles.values():
            for w in hw:
                df[w] = df.get(w, 0) + 1
        n_titles = max(1, len(titles))
        idf = lambda w: math.log(1 + n_titles / df.get(w, 1))   # rare title words (e.g. "deregistration") weigh more
        scored = []
        for r in arts:
            if r["passage_id"] in taken:
                continue
            hw = titles[r["passage_id"]]
            matched = qstems & hw
            if len(matched) >= 2:
                weight = sum(idf(w) for w in matched)
                precision = len(matched) / max(1, len(hw))
                scored.append((-weight, -precision, rank.get(r["passage_id"], 10_000), r["passage_id"], dict(r)))
        for *_, r in sorted(scored, key=lambda x: x[:4])[:heading_extra]:
            out.append(dict(r, added_by="heading"))
            taken.add(r["passage_id"])
    return out
