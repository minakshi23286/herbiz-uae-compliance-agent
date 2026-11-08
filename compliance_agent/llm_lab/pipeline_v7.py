"""Retrieval v7 (Workstream B, one approved map-completion cycle): v6's five stages, plus a law-wide provision map
(curated topics for the concepts the v6 report found missing + one article topic for every article), corrected
out-of-scope rule, false secondary-topic triggers removed, and primary topics first in the retrieval budget.
pipeline_v6.py and its tables are unchanged.

Retrieval v6 (Workstream B): structured five-stage, deterministic retrieval. Read-only; no network; no new dependencies.

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
# signals that a question is about VAT even when it also names another regime ("tax" alone is not enough: corporate tax)
VAT_STRONG = re.compile(r"\b(vat|value added|fta|federal tax authority|trn|emaratax|tax invoices?|tax registration|zero[- ]?rat\w*|input tax|output tax)\b", re.I)
THRESHOLD_AMOUNT = re.compile(r"\b(375|187[.,]?5)\s*(?:,000|k)\b|\b(?:375|187),?(?:000|500)\b", re.I)
TITLE_GENERIC = {"tax", "the", "and", "for", "suppl", "supply", "servic", "goods", "of", "in"}
PLAIN = {"complete": "All provisions this topic needs were found.",
         "incomplete": "Some provisions this question needs were not found, or the topic could not be confirmed. Do not rely on an answer built from these passages alone.",
         "ambiguous": "The question could mean more than one thing. The alternatives were retrieved; a clarifying question is needed before answering.",
         "source_validity_unresolved": "A provision this question needs has an unresolved source problem (outdated text or conflicting official statements). The answer cannot be certified.",
         "out_of_scope": "This does not look like a UAE VAT law question, which is the only topic these texts cover."}


@lru_cache(maxsize=1)
def tables() -> dict:
    load = lambda n: json.loads((DATA / n).read_text(encoding="utf-8"))
    pm, ex, ai, sv = (load("CL_provision_map_v7.json"), load("CL_expansion_v6.json"), load("CL_article_index_v6.json"),
                      load("CL_source_validity_v6.json"))
    issues = {}
    for i in sv["issues"]:
        for p in i["provisions"]:
            issues.setdefault(p, []).append(i)
    return {"topics": {**pm["topics"], **pm["article_topics"]}, "curated": pm["topics"], "links": ex["links"],
            "articles": ai["articles"], "issues": issues}


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
LOCATION_RULES = [
    (["non_resident"], re.compile(r"\b(?:i|we)\s+(?:live|am based|are based|reside|am located|are located)\s+in\s+(?!" + UAE_PLACES + r"\b)[a-z]+"
                                  r"|\bno (?:office|branch|company|establishment|presence) in " + UAE_PLACES, re.I)),
    (["zero_rated_or_exports"], re.compile(r"\b(?:orders?|customers?|buyers?|clients?)\s+(?:from|in)\s+" + ABROAD + r"\b"
                                           r"|\b(?:ship|send|deliver|export)\w*\s+(?:\w+\s+){0,3}(?:to\s+)?" + ABROAD + r"\b"
                                           r"|\b(?:left|leaves|leave|leaving)\s+the\s+(?:uae|country)\b", re.I)),
    # v7: a client located abroad is both a place-of-supply and an export question
    (["place_of_supply", "zero_rated_or_exports"],
     re.compile(r"\b(?:students?|clients?|customers?|subscribers?|users?|company|companies)\b[^.?!]{0,40}\b(?:in|from|based in)\s+" + ABROAD + r"\b", re.I)),
]
# v7 concept rules for the legal concepts the v6 report found missing (owner wording -> topic)
INPUT_CONTEXT = re.compile(r"\b(claim\w*|reclaim\w*|recover\w*|get (?:the |that |my )?vat back|vat back|input (?:vat|tax)|deduct\w*)\b", re.I)
V7_CONCEPT_RULES = [
    ("vouchers", re.compile(r"\b(vouchers?|gift ?cards?|gift certificates?|coupons?|pre-?paid cards?|store credit|redeem\w*)\b", re.I), None),
    ("composite_supply", re.compile(r"\b(comes? with|bundl\w*|package deal|combo|together with (?:a|an|the)|includes? (?:a|an) [a-z]+ (?:box|kit|pack)|"
                                    r"one price for|split it into|service \+ goods|goods \+ service|goods and (?:a )?service|one thing for vat)\b", re.I), None),
    ("input_tax_before_registration", re.compile(r"\b(?:before|prior to)\s+(?:i |we )?(?:was |were |got |had |getting )?(?:vat[- ])?(?:registered|registering|registration|(?:my|our|the) trn)\b"
                                                 r"|\bonly got (?:my|our|the) trn\b|\b(?:got|received) (?:my|our|the) trn (?:in|on|after|later|only)\b", re.I), INPUT_CONTEXT),
    ("blocked_input_tax", re.compile(r"\b(entertain\w*|client (?:dinner|lunch)|dinner with|lunch with|restaurant|hospitality|staff party|"
                                     r"employee (?:party|meals?)|personal car|private car|motor vehicle|petrol|fuel)\b", re.I), INPUT_CONTEXT),
    ("bad_debt", re.compile(r"\b(owes? me|owed|hasn'?t paid|has not paid|not paying|won'?t pay|never paid|ghost\w*|unpaid|written off|write (?:it )?off|"
                            r"bad debts?|chasing (?:her|him|them|payment))\b", re.I), None),
]
CAPITAL_RX = re.compile(r"\b(ovens?|mixers?|machines?|machinery|equipment|laptops?|cameras?|cars?|vans?|vehicles?|furniture|printers?|"
                        r"assets?|desks?|fridges?|freezers?|sewing machine)\b", re.I)
REG_WORDS = re.compile(r"\b(regist\w*|deregist\w*|unregist\w*|trn|threshold|limit|375|187|turnover)\b", re.I)
RATE_QUESTION = re.compile(r"\b(what (?:is the )?(?:vat )?rate|which rate|how much vat|what percent\w*|is it 5 ?%)\b", re.I)
HEALTH_RX = re.compile(r"\b(clinic|health\w*|medical|therap\w*|physio\w*|nurse|nurses|nursing|doctor|dentist)\b", re.I)
FREE_GIFT_RX = re.compile(r"\b(free|samples?|give ?away|giveaways?|personal use|own use|for my family)\b", re.I)
BUSINESS_SPLIT_RX = re.compile(r"\bsplit (?:the |my |our )?(?:business|bookings|orders|sales|turnover|income|work|company|customers)\b|"
                               r"\btrade names?\b|\blicen[cs]es\b|\btwo (?:businesses|companies|licen[cs]es)\b|\bseparate (?:businesses|companies|licen[cs]es)\b", re.I)
RELATIVE_RX = re.compile(r"\b(sister|brother|husband|wife|cousin|uncle|aunt|mother|father|son|daughter|in-law|family member|relative|friend)'?s?\b", re.I)
RELATED_BUSINESS_RX = re.compile(r"\b(shop|store|company|business|licen[cs]e|restaurant|salon|supply|supplies|sell\w*|buy\w*|bookings|orders|sales|income|turnover|revenue|name|"
                                 r"customer|client|bakery|boutique|firm|llc)\b", re.I)
REGISTRATION_ALTS = {"mandatory_registration", "voluntary_registration", "deregistration", "threshold_calculation"}
SECONDARY_TOPICS = {"penalties", "payment", "vat_rate", "capital_assets_scheme"}
DIGITAL_RX = re.compile(r"\b(download\w*|e-?books?|apps?|streaming|software|subscriptions?|online (?:course|class|classes|lesson)s?|"
                        r"recorded (?:course|class)\w*|zoom|webinar\w*|printables?|digital)\b", re.I)


def location_intents(question: str) -> list[str]:
    """Owner-wording rules for where the parties are (general location patterns)."""
    return [t for ts, rx in LOCATION_RULES if rx.search(question) for t in ts]


def v7_concepts(question: str) -> list[str]:
    return [t for t, rx, ctx in V7_CONCEPT_RULES if rx.search(question) and (ctx is None or ctx.search(question))]


def _related_in_business(question: str) -> bool:
    """A relative counts as a related party only when a business word is near the relative (not 'my accountant cousin says')."""
    for m in RELATIVE_RX.finditer(question):
        window = question[max(0, m.start() - 60): m.end() + 60]
        if RELATED_BUSINESS_RX.search(window) and not re.search(r"\b(accountant|lawyer|advis\w*|says|said|told)\b", window, re.I):
            return True
    return False


def classify(question: str) -> dict:
    """Stage 1. v7: another regime is out of scope only when the question carries no VAT signal at all (FTA, TRN or a
    threshold amount count); false secondary triggers are removed; topics are split into primary and secondary."""
    if C.OTHER_REGIME_RX.search(question) and not VAT_STRONG.search(question) and not THRESHOLD_AMOUNT.search(question):
        return {"out_of_scope": True, "intents": [], "secondary": [], "ambiguous": False, "scorer": [], "reason": "another tax or legal regime"}
    # the question carries a VAT signal: mention of another regime (e.g. "trade licence") must not hide its VAT topics
    its, amb = C.intents(C.OTHER_REGIME_RX.sub(" ", question))
    loc, extra = location_intents(question), v7_concepts(question)
    specific = [t for t in loc + extra]
    if amb and (specific or set(its) - REGISTRATION_ALTS) and (not REG_WORDS.search(question) or loc):
        # an ambiguity that came only from amounts or hedging ("not sure") is resolved by the specific topics
        its, amb = [t for t in its if t not in REGISTRATION_ALTS], False
    if amb and specific:
        # registration words present: keep the registration alternatives (ambiguous) but do not lose the specific topic
        pass
    if not amb:
        its = list(dict.fromkeys(specific + its))         # the more specific v7 topics first in the budget
    # false secondary triggers (v6 report §4)
    drop = set()
    if "records" in its and not RECORDS_RX.search(question):
        drop.add("records")                               # "recorded courses" is not record-keeping
    if "healthcare" in its and not HEALTH_RX.search(question):
        drop.add("healthcare")                            # "nursery" is not a health service
    if "deemed_supply" in its and "vouchers" in its and not FREE_GIFT_RX.search(question):
        drop.add("deemed_supply")                         # "gift card" is a voucher, not a free gift
    if "vat_rate" in its and len(its) > 1 and not RATE_QUESTION.search(question):
        drop.add("vat_rate")                              # "5% or 0?" inside another topic is not a rate question
    if "related_parties" in its and not (_related_in_business(question) or BUSINESS_SPLIT_RX.search(question) or
                                         re.search(r"\b(related part|tax group|group registration|connected)\b", question, re.I)):
        drop |= {"related_parties", "related_value"}
    if "composite_supply" in its and not BUSINESS_SPLIT_RX.search(question) and "related_parties" not in its:
        drop.add("threshold_calculation") if not REG_WORDS.search(question) else None
    if {"capital_assets_threshold", "capital_assets_scheme"} & set(its) and not CAPITAL_RX.search(question):
        drop |= {"capital_assets_threshold", "capital_assets_scheme"}   # the v5 trigger "car" also matches "card"
    if {"capital_assets_threshold", "capital_assets_scheme"} & set(its) and "input_tax" in its and not REG_WORDS.search(question):
        drop |= {"capital_assets_threshold", "capital_assets_scheme"}
    its = [t for t in its if t not in drop]
    if "electronic_services" in its and not DIGITAL_RX.search(question):
        its.remove("electronic_services")                 # "sell candles online" is goods, not an electronic service
    if "place_of_supply" in its and DIGITAL_RX.search(question) and "electronic_services" not in its:
        its.append("electronic_services")
    scorer = score_articles(question)
    if not VAT_SIGNAL.search(question) and not THRESHOLD_AMOUNT.search(question) and set(its) <= GENERIC_TOPICS:
        return {"out_of_scope": True, "intents": [], "secondary": [], "ambiguous": False, "scorer": scorer,
                "reason": "no VAT word and no VAT-specific topic" + (f" (generic: {', '.join(its)})" if its else "")}
    primary = [t for t in its if t not in SECONDARY_TOPICS] or its
    secondary = [t for t in its if t not in primary]
    return {"out_of_scope": False, "intents": primary, "secondary": secondary, "ambiguous": amb, "scorer": scorer, "reason": ""}


@lru_cache(maxsize=1)
def anchor_topics() -> dict[str, str]:
    """Anchor article -> curated topic: each curated topic's first required provision (first topic wins on ties)."""
    out: dict[str, str] = {}
    for t, spec in tables()["curated"].items():
        if spec["required"] and spec["required"][0].split("|")[1] != "*":
            out.setdefault(spec["required"][0], t)
    return out


def _title_overlap(question: str, k: str) -> set:
    title = {_stem(w) for w in re.findall(r"[a-z]{3,}", tables()["articles"].get(k, {}).get("title", "").lower())} - TITLE_GENERIC
    return set(_terms(question)) & title


def promote_topics(question: str, bm_keys: set, scorer: list, its: list[str]) -> list[str]:
    """Stage 1, second methods: a curated topic's anchor article found by BOTH the passage search (top-6) and the article
    scorer (top-3) adds that topic, provided the owner's own words share a specific word with the article's title."""
    out = []
    for k, _ in scorer[:3]:
        t = anchor_topics().get(k)
        if t and k in bm_keys and t not in its and t not in out and _title_overlap(question, k):
            out.append(t)
    return out


def article_topics_for(question: str, bm_keys: set, scorer: list, family: set) -> list[str]:
    """v7 law-wide coverage: the scorer's best article, when it lies outside every chosen topic, becomes an article topic
    (the article + its implementing-pair articles) if the passage search also found it, or the owner's words share at least
    two specific words with its title. This is how provisions without a curated topic are reached."""
    out = []
    for k, _ in scorer[:2]:
        if k in family or f"art:{k}" not in tables()["topics"]:
            continue
        if k in bm_keys or len(_title_overlap(question, k)) >= 2:
            out.append(f"art:{k}")
    return out[:1]


def required_for(question: str, its: list[str], ambiguous: bool, secondary: list[str] | None = None) -> tuple[list[str], dict[str, str]]:
    """Stage 2. Required provisions: primary topics first (round-robin), then the base registration rule, then secondary
    topics (v7 budget priority). Returns the ordered list and which topic asked for each."""
    T = tables()["topics"]
    req, why = [], {}

    def take(topics, label=None):
        depth = max((len(T[i]["required"]) for i in topics), default=0)
        for d in range(depth):
            for i in topics:
                r = T[i]["required"]
                if d < len(r) and r[d] not in why:
                    req.append(r[d]); why[r[d]] = label or i
    take(its)
    if C.needs_base_rule(question, [t for t in its if not t.startswith("art:")] + (secondary or []), ambiguous):
        extra = list(T["mandatory_registration"]["required"]) + (["FTA-VAT-DL8|19"] if C.turnover_stated(question) else [])
        for r in extra:
            if r not in why:
                req.append(r); why[r] = "base_rule"
    take(secondary or [])
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
    its, sec, amb = list(cls["intents"]), list(cls["secondary"]), cls["ambiguous"]
    bm_keys = {article_key(p["source_id"], p["locator"]) for p in got}
    T = tables()["topics"]
    if not amb:
        promoted = promote_topics(question, bm_keys, cls["scorer"], its + sec)
        its += promoted
        if promoted:
            cls["promoted"] = promoted
        fam0 = {r for i in its + sec for r in T[i]["required"] + T[i]["supporting"]}
        fam0 |= {p for p, _, _ in partners(sorted(fam0))}
        arts = article_topics_for(question, bm_keys, cls["scorer"], fam0)
        if arts:
            # weaker evidence than a curated topic: primary only when nothing else was found, otherwise secondary
            (sec if its else its).extend(arts)
            cls["article_topics"] = arts
    cls["intents"], cls["secondary"] = its, sec
    req, why = required_for(question, its, amb, sec)
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

    primary_req = [r for r in req if why[r] in its]
    base_req = [r for r in req if why[r] == "base_rule"]
    # v7 budget priority: primary required -> base rule -> implementing pairs of primary -> secondary -> other partners
    for r in primary_req:
        add(r, f"v7:required:{why[r]}" + (":ambiguous" if amb else ""))
    for r in base_req:
        add(r, "v7:required:base_rule")
    if not amb:
        for p, kind, src in partners(primary_req):
            if kind == "implementing_pair" and add(p, f"v7:partner:{kind}:{src}"):
                rec["partners_added"].append(p)
    for r in req:
        if r not in primary_req and r not in base_req:
            add(r, f"v7:required:{why[r]}")
    if not amb:
        for p, kind, src in partners(req):
            if p not in rec["partners_added"] and add(p, f"v7:partner:{kind}:{src}"):
                rec["partners_added"].append(p)
    family = set(req) | {p for p, _, _ in partners(req)} | {s for i in its + sec for s in T[i]["supporting"]}
    # certification needs agreement: the passage search AND the article scorer must each land in the topic family, and a
    # question spanning more than MAX_CERT_TOPICS primary topics is never certified
    rec["confirmed_by_scorer"] = (bool(bm_keys & family) and any(k in family for k, _ in cls["scorer"][:3])
                                  and len(its) <= MAX_CERT_TOPICS)
    if not its and not sec:
        for k, _ in cls["scorer"][:2]:
            add(k, "v7:scorer")
    elif not amb and len(its) == 1:
        for s in T[its[0]]["supporting"][:1]:
            add(s, f"v7:supporting:{its[0]}")
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
