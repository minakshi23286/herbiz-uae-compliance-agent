"""Retrieval v6 (Workstream B): structured five-stage, deterministic retrieval. Read-only; no network; no new dependencies.

  1. classify     owner question -> topics (v5 keyword index) + an article scorer over titles and opening text (second
                  method) + out-of-scope detection
  2. map          topics -> required provisions (data/CL_provision_map_v6.json, draft until a reviewer approves it)
  3. expand       required provisions -> partners that travel with them (data/CL_expansion_v6.json, built from the corpus:
                  implementing pairs DL<->ER, sibling articles, explicit cross-references)
  4. verify       are all required provisions present? does any needed provision have an unresolved source-validity issue
                  (data/CL_source_validity_v6.json: outdated text, conflicting deadline)?
  5. status       complete | incomplete | ambiguous | source_validity_unresolved | out_of_scope, with the missing provisions
                  and issues named in plain language. Only "complete" is a certified result.

The plain BM25 top-6 is never changed (additions only, as in v4/v5). retrieve.py, concepts.py and concepts_v5.py are not
modified. Locators are parsed only through locators.py (Workstream C interface contract v0.1).
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

from . import concepts_v5 as C
from .locators import article_key, matches
from .retrieve import search as _search

DATA = Path(__file__).resolve().parent / "data"
BM25_K = 6
MAX_ADD = 6                 # at most 12 passages per question
SCORER_TOP = 5              # articles the second method may confirm
MAX_CERT_TOPICS = 3         # more topics than this: never certified complete
LATEST = (" AND p.version_id IN (SELECT version_id FROM source_versions sv WHERE status != 'rejected' AND seq ="
          " (SELECT MAX(seq) FROM source_versions s2 WHERE s2.source_id = sv.source_id AND s2.status != 'rejected'))")
VAT_SIGNAL = re.compile(r"\b(vat|value added|tax\w*|fta|trn|emaratax|invoic\w*|zero[- ]?rat\w*|exempt\w*|regist\w*|deregist\w*|"
                        r"input tax|output tax|reverse charge|designated zone|free zone)\b", re.I)
STOP = {"the", "and", "for", "what", "does", "need", "with", "my", "is", "are", "do", "to", "of", "in", "on", "a", "an", "i",
        "me", "how", "it", "this", "that", "be", "or", "if", "can", "will", "have", "has", "at", "by", "we", "our", "you",
        "your", "so", "but", "not", "just", "about", "from", "they", "them", "she", "her", "he", "his", "was", "am", "im",
        "should", "would", "could", "there", "any", "also", "only", "like", "get", "got", "some", "all", "when", "which"}
# topics whose trigger words are ordinary business words (fines, records, payment...): without any VAT word they do not
# make a question a VAT question
GENERIC_TOPICS = {"penalties", "records", "payment", "evasion", "credit_note", "bad_debt", "vat_rate", "tourist", "new_residence",
                  "value_of_supply", "agent", "date_of_supply", "place_of_supply", "deemed_supply", "tax_invoice"}
TITLE_GENERIC = {"tax", "the", "and", "for", "suppl", "supply", "servic", "goods", "of", "in"}
PLAIN = {"complete": "All provisions this topic needs were found.",
         "incomplete": "Some provisions this question needs were not found, or the topic could not be confirmed. Do not rely on an answer built from these passages alone.",
         "ambiguous": "The question could mean more than one thing. The alternatives were retrieved; a clarifying question is needed before answering.",
         "source_validity_unresolved": "A provision this question needs has an unresolved source problem (outdated text or conflicting official statements). The answer cannot be certified.",
         "out_of_scope": "This does not look like a UAE VAT law question, which is the only topic these texts cover."}


@lru_cache(maxsize=1)
def tables() -> dict:
    load = lambda n: json.loads((DATA / n).read_text(encoding="utf-8"))
    pm, ex, ai, sv = (load("CL_provision_map_v6.json"), load("CL_expansion_v6.json"), load("CL_article_index_v6.json"),
                      load("CL_source_validity_v6.json"))
    issues = {}
    for i in sv["issues"]:
        for p in i["provisions"]:
            issues.setdefault(p, []).append(i)
    return {"topics": pm["topics"], "links": ex["links"], "articles": ai["articles"], "issues": issues}


def _stem(w: str) -> str:
    return w[:6] if len(w) >= 6 else w


def _terms(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in STOP]


@lru_cache(maxsize=1)
def _scorer_index():
    arts = tables()["articles"]
    docs = {k: _terms(a["title"]) * 3 + _terms(a["opening"]) for k, a in arts.items()}
    df: dict[str, int] = {}
    for d in docs.values():
        for w in set(d):
            df[w] = df.get(w, 0) + 1
    n = len(docs)
    avg = sum(len(d) for d in docs.values()) / n
    return docs, df, n, avg


def score_articles(question: str, top: int = SCORER_TOP) -> list[tuple[str, float]]:
    """Second method for stage 1: BM25 over each article's title (weighted x3) and opening text, with the owner's words
    plus the law words of the topics the keyword index found. Independent of the passage-level BM25 search."""
    docs, df, n, avg = _scorer_index()
    found, law = C.detect(question)
    q = set(_terms(question)) | {_stem(w) for w in law}
    out = []
    for k, d in docs.items():
        tf: dict[str, int] = {}
        for w in d:
            if w in q:
                tf[w] = tf.get(w, 0) + 1
        s = sum(math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5)) * (c * 2.2) / (c + 1.2 * (0.25 + 0.75 * len(d) / avg)) for w, c in tf.items())
        if s > 0:
            out.append((k, round(s, 3)))
    return sorted(out, key=lambda x: (-x[1], x[0]))[:top]


RECORDS_RX = re.compile(r"\b(records|record[- ]?keeping|keep\w*|bookkeeping|books|archiv\w*|how long)\b", re.I)
UAE_PLACES = r"(?:the uae|uae|the emirates|dubai|abu dhabi|sharjah|ajman|ras al khaimah|rak|fujairah|umm al quwain|uaq|al ain|here)"
ABROAD = (r"(?:oman|muscat|saudi|ksa|riyadh|jeddah|kuwait|qatar|doha|bahrain|india|pakistan|egypt|jordan|lebanon|uk|britain|london|"
          r"europe|usa|us|america|canada|australia|turkey|iran|china|philippines|abroad|overseas|outside the uae|other countries|gcc)")
V6_LOCATION_RULES = [
    ("non_resident", re.compile(r"\b(?:i|we)\s+(?:live|am based|are based|reside|am located|are located)\s+in\s+(?!" + UAE_PLACES + r"\b)[a-z]+"
                                r"|\bno (?:office|branch|company|establishment|presence) in " + UAE_PLACES, re.I)),
    ("zero_rated_or_exports", re.compile(r"\b(?:orders?|customers?|buyers?|clients?)\s+(?:from|in)\s+" + ABROAD + r"\b"
                                         r"|\b(?:ship|send|deliver|export)\w*\s+(?:\w+\s+){0,3}(?:to\s+)?" + ABROAD + r"\b"
                                         r"|\b(?:left|leaves|leave|leaving)\s+the\s+(?:uae|country)\b", re.I)),
    ("place_of_supply", re.compile(r"\b(?:students?|clients?|customers?|subscribers?|users?)\b[^.?!]{0,40}\b(?:in|from)\s+" + ABROAD + r"\b", re.I)),
]


def v6_location_intents(question: str) -> list[str]:
    """v6 owner-wording rules for where the parties are (general location patterns, not country-by-country topics)."""
    return [t for t, rx in V6_LOCATION_RULES if rx.search(question)]


def classify(question: str) -> dict:
    """Stage 1. Out of scope when the question names another regime without VAT, or carries no VAT signal and no topic."""
    if C.OTHER_REGIME_RX.search(question) and not re.search(r"\bvat\b", question, re.I):
        return {"out_of_scope": True, "intents": [], "ambiguous": False, "scorer": [], "reason": "another tax or legal regime"}
    its, amb = C.intents(question)
    loc = v6_location_intents(question)
    if amb and loc and set(its) <= {"mandatory_registration", "voluntary_registration", "threshold_calculation"}:
        its, amb = loc, False        # a specific reading (e.g. a non-resident seller) resolves the generic registration ambiguity
    if not amb:
        its = list(dict.fromkeys(its + loc))
        if "records" in its and not RECORDS_RX.search(question):
            its.remove("records")     # "recorded courses" is not record-keeping
        if "place_of_supply" in its and C.SERVICE_RX.search(question) and "electronic_services" not in its:
            its.append("electronic_services")
    found, _ = C.detect(question)
    scorer = score_articles(question)
    if not VAT_SIGNAL.search(question) and set(its) <= GENERIC_TOPICS:
        return {"out_of_scope": True, "intents": [], "ambiguous": False, "scorer": scorer,
                "reason": "no VAT word and no VAT-specific topic" + (f" (generic: {', '.join(its)})" if its else "")}
    return {"out_of_scope": False, "intents": its, "ambiguous": amb, "scorer": scorer, "reason": ""}


@lru_cache(maxsize=1)
def anchor_topics() -> dict[str, str]:
    """Anchor article -> topic: each topic's first required provision (first topic wins on ties)."""
    out: dict[str, str] = {}
    for t, spec in tables()["topics"].items():
        if spec["required"] and spec["required"][0].split("|")[1] != "*":
            out.setdefault(spec["required"][0], t)
    return out


def promote_topics(question: str, bm_keys: set, scorer: list, its: list[str]) -> list[str]:
    """Stage 1, second methods: a topic's anchor article found by BOTH the passage search (top-6) and the article scorer
    (top-3) adds that topic, provided the owner's own words share a specific word with the article's title."""
    own, out = set(_terms(question)), []
    for k, _ in scorer[:3]:
        t = anchor_topics().get(k)
        title = {_stem(w) for w in re.findall(r"[a-z]{3,}", tables()["articles"].get(k, {}).get("title", "").lower())} - TITLE_GENERIC
        if t and k in bm_keys and t not in its and t not in out and own & title:
            out.append(t)
    return out


def required_for(question: str, its: list[str], ambiguous: bool) -> tuple[list[str], dict[str, str]]:
    """Stage 2. Required provisions (ordered round-robin across topics) and which topic asked for each."""
    T = tables()["topics"]
    req, why = [], {}
    depth = max((len(T[i]["required"]) for i in its), default=0)
    for d in range(depth):
        for i in its:
            r = T[i]["required"]
            if d < len(r) and r[d] not in why:
                req.append(r[d]); why[r[d]] = i
    if C.needs_base_rule(question, its, ambiguous):
        extra = list(T["mandatory_registration"]["required"]) + (["FTA-VAT-DL8|19"] if C.turnover_stated(question) else [])
        for r in extra:
            if r not in why:
                req.append(r); why[r] = "base_rule"
    return req, why


def partners(req: list[str]) -> list[tuple[str, str, str]]:
    """Stage 3. Partners of required provisions: implementing pairs first, then siblings, then explicit references."""
    L = tables()["links"]
    out, seen = [], set(req)
    for order in ("implementing_pair", "sibling", "explicit_reference"):
        for r in req:
            for x in L.get(r, []):
                if x["why"] == order and x["key"] not in seen:
                    out.append((x["key"], order, r)); seen.add(x["key"])
    return out


def _fetch(con: sqlite3.Connection, ref: str):
    src, art = ref.split("|", 1)
    sel = ("SELECT p.passage_id, p.locator, p.text, d.source_id, d.url, v.document_title, v.status AS source_status"
           " FROM passages p JOIN documents d ON d.doc_id = p.doc_id JOIN source_versions v ON v.version_id = p.version_id WHERE ")
    if art == "*":
        return con.execute(sel + "d.source_id = ? AND p.text LIKE ?" + LATEST + " ORDER BY p.seq LIMIT 1",
                           (src, "%registration threshold of AED%")).fetchone()
    num, _, suf = art.partition(" ")
    loc = f"Article {num} {suf}" if suf else f"Article {num}"
    return con.execute(sel + "d.source_id = ? AND (p.locator LIKE ? OR p.locator = ?)" + LATEST + " ORDER BY p.seq LIMIT 1",
                       (src, loc + ",%", loc)).fetchone()


def _present(got: list[dict], ref: str) -> bool:
    src = ref.split("|", 1)[0]
    return any(matches(p["source_id"], p["locator"], ref) for p in got if p["source_id"] == src)


def retrieve(con: sqlite3.Connection, question: str) -> dict:
    """All five stages. Returns passages (BM25 top-6 first, unchanged) plus a coverage record and a status."""
    got = [dict(r, added_by="bm25") for r in _search(con, question, k=BM25_K, heading_extra=0, core_pack=False)]
    cls = classify(question)
    rec = {"question": question, "classification": cls, "required": [], "missing": [], "issues": [], "partners_added": [],
           "status": "out_of_scope", "confirmed_by_scorer": False}
    if cls["out_of_scope"]:
        return _finish(rec, got)
    its, amb = list(cls["intents"]), cls["ambiguous"]
    # stage 1, second methods: a topic's anchor article (its first required provision) found by BOTH the passage search
    # (top-6) and the article scorer (top-3) adds that topic, even when the owner's wording did not trigger it
    bm_keys = {article_key(p["source_id"], p["locator"]) for p in got}
    if not amb:
        promoted = promote_topics(question, bm_keys, cls["scorer"], its)
        its += promoted
        if promoted:
            cls["promoted"] = promoted
    cls["intents"] = its
    req, why = required_for(question, its, amb)
    rec["required"] = req
    added = 0

    def add(ref: str, label: str) -> bool:
        nonlocal added
        if added >= MAX_ADD or _present(got, ref):
            return False
        r = _fetch(con, ref)
        if r is None:
            return False
        got.append(dict(r, added_by=label)); added += 1
        return True

    for r in req:
        add(r, f"v6:required:{why[r]}" + (":ambiguous" if amb else ""))
    if not amb:
        for p, kind, src in partners(req):
            if add(p, f"v6:partner:{kind}:{src}"):
                rec["partners_added"].append(p)
    family = set(req) | {p for p, _, _ in partners(req)} | {s for i in its for s in tables()["topics"][i]["supporting"]}
    # certification needs agreement: the passage search AND the article scorer must each land in the topic family, and a
    # question spanning more than MAX_CERT_TOPICS topics is never certified (it needs a reviewer-level composition)
    rec["confirmed_by_scorer"] = (bool(bm_keys & family) and any(k in family for k, _ in cls["scorer"][:3])
                                  and len(its) <= MAX_CERT_TOPICS)
    if not its:
        for k, _ in cls["scorer"][:2]:            # no keyword topic: the scorer's best articles are the only additions
            add(k, "v6:scorer")
    elif not amb and len(its) == 1:
        for s in tables()["topics"][its[0]]["supporting"][:1]:
            add(s, f"v6:supporting:{its[0]}")
    rec["missing"] = [r for r in req if not _present(got, r)]
    return _finish(rec, got)


def _finish(rec: dict, got: list[dict]) -> dict:
    """Stages 4 and 5: validity check and status."""
    I = tables()["issues"]
    needed = set(rec["required"]) | set(rec["partners_added"])
    rec["issues"] = sorted({i["id"]: i for r in needed for i in I.get(r, [])}.values(), key=lambda i: i["id"])
    warn = sorted({i["id"] for p in got for k in [article_key(p["source_id"], p["locator"])] if k and k not in needed for i in I.get(k, [])})
    cls = rec["classification"]
    if cls["out_of_scope"]:
        status = "out_of_scope"
    elif rec["issues"]:
        status = "source_validity_unresolved"
    elif cls["ambiguous"]:
        status = "ambiguous"
    elif not cls["intents"] or rec["missing"] or not rec["confirmed_by_scorer"]:
        status = "incomplete"
    else:
        status = "complete"
    rec["status"] = status
    rec["message"] = PLAIN[status] + "".join(" " + i["message"] for i in rec["issues"])
    rec["warnings"] = [f"A retrieved passage is affected by source issue {w}; do not cite it as current law." for w in warn]
    rec["passages"] = got
    return rec


def search(con: sqlite3.Connection, question: str) -> list[dict]:
    """Passages only (same shape as retrieve.search), for metric runners."""
    return retrieve(con, question)["passages"]


def coverage_note(rec: dict) -> str:
    """Stage 5 for the answering step: a plain note to give the model with the passages, so an uncertified retrieval is never
    answered as if it were complete. (Not yet wired into run.py: the paid answering path needs founder approval.)"""
    lines = [f"RETRIEVAL STATUS: {rec['status'].upper()}. {rec['message']}"]
    if rec.get("missing"):
        lines.append("Missing provisions: " + ", ".join(rec["missing"]) + ". Say that the answer is incomplete and name them.")
    if rec.get("issues"):
        lines.append("Do not state these provisions as current law; say the source must be checked by a qualified reviewer.")
    lines += rec.get("warnings", [])
    return "\n".join(lines)


def answer_certifiable(rec: dict, parsed_answer: dict) -> dict:
    """Stage 5 guard after answering: an 'answered' result is certified only when retrieval was complete."""
    status = parsed_answer.get("answer_status", "")
    ok = rec["status"] == "complete" or status != "answered"
    return {"certified": ok and rec["status"] == "complete", "flag": None if ok else
            f"Answered although retrieval was {rec['status']}: show the answer as incomplete / not verified."}
