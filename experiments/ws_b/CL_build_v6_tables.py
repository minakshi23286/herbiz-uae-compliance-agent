"""Builds the v6 retrieval tables OFFLINE from a read-only corpus copy and the v5 topic index (Workstream B).

Outputs (deterministic, committed, regenerated only by this script):
  compliance_agent/llm_lab/data/CL_provision_map_v6.json   stage 2: topic -> required / supporting provisions (draft, unreviewed)
  compliance_agent/llm_lab/data/CL_expansion_v6.json       stage 3: provision -> partner provisions, with the reason for each link
  compliance_agent/llm_lab/data/CL_article_index_v6.json   stage 1: article titles + opening text for the article scorer
Usage: python3 experiments/ws_b/CL_build_v6_tables.py data/CL_ws_b_kb_copy.sqlite3 [out_dir]
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from compliance_agent.llm_lab.concepts_v5 import INTENT_PROVISIONS  # noqa: E402
from compliance_agent.llm_lab.locators import article_key, key  # noqa: E402
from compliance_agent.llm_lab.retrieve import article_heading, connect_ro  # noqa: E402

OUT = ROOT / "compliance_agent" / "llm_lab" / "data"
LATEST = ("SELECT version_id FROM source_versions sv WHERE status != 'rejected' AND seq = (SELECT MAX(seq) FROM source_versions s2"
          " WHERE s2.source_id = sv.source_id AND s2.status != 'rejected')")
FUNCTION = {"the", "of", "in", "on", "by", "a", "an", "to", "and", "or", "with", "from", "for", "case", "cases", "certain",
            "article", "regarding", "related", "relating", "connection", "respect", "this", "that", "its", "more", "than", "one"}
GENERIC = {"tax", "supply", "suppli", "suppl", "goods", "servic", "services"}   # too common in titles to pair articles by


def stem(w: str) -> str:
    return w[:6] if len(w) >= 6 else w


def clean_title(t: str) -> str:
    return re.sub(r"\s*\d+(,\d+)*\s*$", "", re.sub(r"(?<=[a-z])\d+(,\d+)*\b", "", t)).strip()   # footnote digits glued to titles


CONNECTOR_END = re.compile(r"\b(of|and|the|for|to|in|with|on|between|into|when|Tax|Issuing)$")
CONTINUATION = re.compile(r"^\s*((?:[A-Za-z][a-z]+ ){0,3}[A-Z]?[a-z]+)\s*\d*(?:\s+\d+)*\s+(?=\d+\.|[A-Z][a-z]* )")


def join_wrapped_title(title: str, body: str) -> str:
    """A title that wraps onto the next line ('Conditions and Requirements for Issuing Tax' + 'Invoices') is joined when the
    title ends in a connector word and the next line starts with up to four words before the article body."""
    if not CONNECTOR_END.search(title):
        return title
    m = CONTINUATION.match(body)
    return f"{title} {m.group(1)}" if m else title


def articles(con) -> dict:
    rows = con.execute("SELECT p.passage_id, p.locator, p.text, d.source_id FROM passages p JOIN documents d ON d.doc_id = p.doc_id"
                       f" WHERE p.version_id IN ({LATEST}) ORDER BY d.source_id, p.seq").fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        k = article_key(r["source_id"], r["locator"])
        if not k:
            continue
        a = out.setdefault(k, {"key": k, "source_id": r["source_id"], "title": clean_title(article_heading(r["text"], r["locator"])),
                               "opening": "", "passages": []})
        a["passages"].append(r["passage_id"])
        if len(a["passages"]) == 1:
            a["title"] = join_wrapped_title(a["title"], r["text"].split("\n", 1)[-1] if "\n" in r["text"] else "")
        if len(a["opening"]) < 600:
            body = r["text"].split("\n", 1)[-1] if r["text"].startswith("Article") else r["text"]
            a["opening"] = (a["opening"] + " " + re.sub(r"\s+", " ", body)).strip()[:600]
    return out


def title_stems(t: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z]{3,}", t.lower()) if w not in FUNCTION} - GENERIC


def num(k: str) -> int:
    return int(re.match(r"\d+", k.split("|")[1]).group())


def explicit_refs(arts: dict) -> list[tuple[str, str, str]]:
    """Cross-references written in the text. DL text: 'Article (N)' = DL. ER text: only 'Article (N) of the Decree-Law' (-> DL)
    and 'Article (N) of this Decision' (-> ER); a bare ER reference is ambiguous and skipped."""
    edges = []
    for k, a in arts.items():
        src = a["source_id"]
        text = " ".join(a["opening"].split())  # opening only: references in the first 600 characters name the article's own frame
        for m in re.finditer(r"Articles?\s*\(?(\d+)\)?((?:\s*(?:,|and)\s*\(?\d+\)?)*)\s*(of (?:the|this) (Decree-Law|Decision|Law))?", text):
            nums = [m.group(1)] + re.findall(r"\d+", m.group(2) or "")
            qual = (m.group(4) or "").lower()
            if src == "FTA-VAT-DL8":
                tgt_src = "FTA-VAT-DL8"
            elif qual.startswith("decree") or qual == "law":
                tgt_src = "FTA-VAT-DL8"
            elif qual == "decision":
                tgt_src = "FTA-VAT-ER"
            else:
                continue
            for n in nums:
                t = f"{tgt_src}|{n}"
                if t in arts and t != k:
                    edges.append((k, t, "explicit_reference"))
    return edges


def title_links(arts: dict) -> list[tuple[str, str, str]]:
    """(a) siblings: neighbouring articles (n±1, n±2) in the same source whose titles share a specific word stem
    (DL 25 'Date of Supply' / DL 26 'Date of Supply in Special Cases'); (b) implementing pairs: a Decree-Law article and an
    Executive Regulation article whose titles share every specific stem of the shorter title (DL 13 'Mandatory Tax
    Registration' / ER 7 'Mandatory Registration')."""
    stems = {k: title_stems(a["title"]) for k, a in arts.items()}
    df: dict[str, int] = {}
    for s in stems.values():
        for w in s:
            df[w] = df.get(w, 0) + 1
    edges = []
    keys = sorted(arts)
    for i, k1 in enumerate(keys):
        for k2 in keys[i + 1:]:
            s1, s2 = stems[k1], stems[k2]
            if not s1 or not s2:
                continue
            shared = s1 & s2
            if not shared:
                continue
            same = arts[k1]["source_id"] == arts[k2]["source_id"]
            if same and abs(num(k1) - num(k2)) <= 2 and any(df[w] <= 8 for w in shared):
                edges.append((k1, k2, "sibling")); edges.append((k2, k1, "sibling"))
            elif not same and {arts[k1]["source_id"], arts[k2]["source_id"]} == {"FTA-VAT-DL8", "FTA-VAT-ER"}:
                if shared == min(s1, s2, key=len) and any(df[w] <= 8 for w in shared):
                    edges.append((k1, k2, "implementing_pair")); edges.append((k2, k1, "implementing_pair"))
    return edges


# v6 provision-map changes relative to the v5 index (development data v3/v4 + the law's chapter structure); each is listed
# in the iteration log. concepts_v5.py stays unchanged because the frozen v5 retrieval and its v4 run depend on it.
V6_REQUIRED_OVERRIDES = {
    "tax_return": ["FTA-VAT-DL8|72", "FTA-VAT-ER|64", "FTA-VAT-DL8|71"],   # Returns chapter: filing (72), payment date (ER 64), period (71)
}


def main(db: str, out_dir: str | None = None) -> None:
    global OUT
    if out_dir:
        OUT = Path(out_dir)
    con = connect_ro(db)
    arts = articles(con)
    edges = sorted(set(explicit_refs(arts) + title_links(arts)))
    exp: dict[str, list] = {}
    for a, b, why in edges:
        exp.setdefault(a, [])
        if not any(x["key"] == b and x["why"] == why for x in exp[a]):
            exp[a].append({"key": b, "why": why, "title": arts[b]["title"]})
    pmap = {}
    for it, spec in INTENT_PROVISIONS.items():
        pmap[it] = {"required": V6_REQUIRED_OVERRIDES.get(it, [key(s, a) for s, a in spec["primary"]]), "supporting": [key(s, a) for s, a in spec["supporting"]],
                    "status": "draft", "reviewed_by": None}
    fp = hashlib.sha256()
    for a in sorted(arts):
        fp.update(a.encode()); fp.update(arts[a]["title"].encode()); fp.update(arts[a]["opening"].encode())
    meta = {"corpus_fingerprint": fp.hexdigest(), "built_by": "experiments/ws_b/CL_build_v6_tables.py",
            "locator_contract": "Workstream C interface contract v0.1", "not_legal_advice": True}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "CL_provision_map_v6.json").write_text(json.dumps({"_meta": dict(meta, note="Topic -> required provisions. Draft: no qualified reviewer has approved it (D3)."),
                                                              "topics": pmap}, indent=1, sort_keys=True) + "\n")
    (OUT / "CL_expansion_v6.json").write_text(json.dumps({"_meta": dict(meta, edges=len(edges)), "links": exp}, indent=1, sort_keys=True) + "\n")
    (OUT / "CL_article_index_v6.json").write_text(json.dumps({"_meta": meta, "articles": {k: {x: a[x] for x in ("title", "opening", "passages")} for k, a in arts.items()}},
                                                             indent=1, sort_keys=True) + "\n")
    print(len(arts), "articles;", len(edges), "links:", {w: sum(1 for e in edges if e[2] == w) for w in ("explicit_reference", "sibling", "implementing_pair")})


if __name__ == "__main__":
    main(*sys.argv[1:3])
