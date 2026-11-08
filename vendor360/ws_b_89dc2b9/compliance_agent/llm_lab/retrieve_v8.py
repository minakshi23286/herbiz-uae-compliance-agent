"""Task 2 retrieval v8 (WS-B, deterministic, zero spend). New versioned module; retrieve.py and pipeline_v7.py unchanged.

v8 = v7 (BM25 + curated provision-map topics + implementing pairs) + two additions, under a declared passage budget:
  1. owner-language topic triggers (LEXICON): plain phrases owners use, mapped to existing provision-map topics, so a
     topic v7's classifier did not detect still has its required provisions completed from the map;
  2. cross-reference completion: the implementing pair (Decree-Law <-> Executive Regulation) of every added provision.
Completeness (silent-incomplete hard gate, tech-sonu review 18 Oct): v8 NEVER returns `complete_for_map` in Task 2.
Dev-set analysis showed wrong certifications spread across many topics, so no topic allow-list is safe while the map is an
unreviewed AI draft. Status is `incomplete` when a mapped required provision is missing, otherwise `unknown`
("every mapped provision present, but HerBiz cannot confirm the question needs nothing else"). Owners always see the
"may be incomplete" warning (WS-A N-B1). Certification can return only after reviewers check the map (D3).

"Complete for the map" is NOT legal completeness: the provision map is an AI-generated, unreviewed draft.
Tuned on development sets v1–v9 only; never on the holdout v10.
"""
from __future__ import annotations

import re
import sqlite3

from . import pipeline_v7 as P

VERSION = "v8"
MAX_PASSAGES = 14            # declared budget: never more passages than this per question
MAP_VERSION = "provision_map_v7"
CERTIFY = False              # Task 2: never certify complete_for_map (see module docstring)
ADDED_BY = {"bm25": "lexical_search", "heading": "title_match", "v7:required": "map_completion", "v8:map_completion": "map_completion",
            "v7:partner": "xref_expansion", "v8:xref_pair": "xref_expansion", "v7:scorer": "article_scorer",
            "v7:supporting": "map_supporting"}          # the fixed WS-B list promised in ACK_B section 2
OUTSIDE_UAE = (r"(?:abroad|overseas|international\w*|foreign|outside (?:the )?(?:uae|country|gcc|emirates)|"
               r"oman|muscat|saudi|ksa|riyadh|jeddah|qatar|doha|kuwait|bahrain|egypt|cairo|jordan|lebanon|india|mumbai|delhi|"
               r"pune|bangalore|pakistan|karachi|lahore|bangladesh|sri lanka|nepal|philippines|manila|china|turkey|istanbul|"
               r"uk|britain|england|london|ireland|france|paris|germany|berlin|spain|italy|europe|eu|netherlands|"
               r"the us|usa|america|canada|toronto|australia|sydney|new zealand|singapore|malaysia|japan|korea|africa|nigeria|kenya)")

# Owner phrases -> existing map topics. General vocabulary only (no question text copied from any evaluation set).
LEXICON: dict[str, re.Pattern] = {k: re.compile(v, re.I) for k, v in {
    "voluntary_registration": r"\bcan i register\b|\bshould i register\b|\bworth (?:it )?(?:to )?regist\w*|\bvoluntar\w*|\boptional(?:ly)?\b|\bchoose to register|\bregister (?:early|anyway|before)|\bnot (?:yet )?(?:required|obliged) to register|\bbelow the (?:mandatory )?threshold",
    "mandatory_registration": r"\b(?:crossed|passed|pass|over|above|exceeded|exceed|reached|hit) (?:the )?375|\bget on the government|\bmust i register|\bhave to register|\bneed to register|\brequired to register|\bobliged to register|\bmandatory registration",
    "deregistration": r"\bderegist\w*|\bcancel\w* (?:my |the |our )?(?:vat |tax )?registration|\bclos\w* (?:my |the |our )?(?:business|shop|company)|\bstop(?:ped|ping)? (?:trading|selling|the business)|\bunregister",
    "composite_supply": r"\bhampers?\b|\bgift ?box(?:es)?\b|\b\w+ box (?:with|has|contains|of)\b|\bkits?\b.*\band\b|\bbundl\w*|\bpackage(?:s|d)?\b|\bcombo\b|\btogether with\b|\bincluding (?:delivery|installation|setup)|\bmore than one (?:item|component|part)|\bmixed (?:supply|basket)",
    "zero_rated_or_exports": r"\b(?:buyers|customers|clients?|people|company|startup|lady|man|shop|someone)\b[^.?!]{0,60}\b(?:in|from)\b[^.?!]{0,30}\b" + OUTSIDE_UAE + r"\b|\b(?:ship\w*|send\w*|courier|deliver\w*|ordered|export\w*|sell\w*)\b[^.?!]{0,80}\b" + OUTSIDE_UAE + r"\b|\b" + OUTSIDE_UAE + r"\b[^.?!]{0,80}\b(?:ship\w*|send\w*|courier|deliver\w*|ordered|buy\w*)\b|\bexport\w*",
    "tax_return": r"\b(?:vat |tax )?returns?\b|\bfil(?:e|ing) (?:my |the |our )?(?:vat|tax|return)|\bsubmit\w* (?:my |the )?(?:vat|return)",
    "payment": r"\bpay(?:ing)? (?:the )?vat\b|\bdue date|\bdeadline to pay|\bhow (?:do|to) (?:i )?pay\b",
    "evasion": r"\boff the books|\bso (?:the )?fta (?:doesn'?t|does not|won'?t|wont|can'?t) (?:see|find|know|notice)|\bsplit (?:my |the |our )?(?:sales|orders|turnover|business|bookings)\b[^.?!]*\b(?:under|below|stays?)\b|\bhid(?:e|ing)\b|\bnot declar\w*|\bunder the table|\bcash only|\bfake invoice|\bavoid (?:paying )?vat|\bnot (?:report|record)\w* (?:some|my|the) (?:sales|income)",
    "agent": r"\bkeeps? \d{1,2} ?%|\bsells? (?:my|our) \w+ (?:on|through|via)\b|\bon (?:my |his |her |their )?behalf|\bas an? agent\b|\bcommission\b|\bmarketplace\b|\bplatform (?:sells|collects)|\bconsign\w*",
    "vat_rate": r"\bvat (?:to|of|is|at) \d{1,2} ?%|\b\d{1,2} ?% vat\b|\bmust be (?:zero|exempt)|\bwhat (?:is the )?(?:vat )?rate|\bhow much vat\b|\bwhich rate\b|\b5 ?%|\bfive percent",
    "registration_exception": r"\b(?:all|every|100 ?%)[^.?!]{0,40}\b(?:sales?|orders?|customers?)\b[^.?!]{0,40}\b(?:exports?|abroad|overseas|outside)\b|\bskip (?:vat )?registration|\ball (?:my )?sales are (?:exports?|zero)|\b100 ?% (?:to |exports?)|\bonly (?:export|sell abroad)\w*|\bonly zero[- ]?rated|\bexception from registration|\bexempt(?:ion)? from registering|\bdo not have to register .*zero",
    "deemed_supply": r"\bfrom (?:my )?(?:own )?stock\b|\bas gifts\b|\bnobody pa(?:id|ys)\b|\bfree (?:\w+ )?(?:boxes|samples?|gifts?|items?|products?)|\bgiv\w* away|\bgifts? to (?:staff|employees|family)|\bown (?:personal )?use|\bfor (?:my )?family\b",
    "records": r"\brecords?\b|\bbook-?keeping|\bhow long .*keep|\bkeep (?:my |the )?(?:receipts|invoices|books)",
    "tax_invoice": r"\btax invoice|\binvoice (?:must|should) (?:show|include)|\bwhat (?:goes|must go) on (?:an |my )?invoice",
    "input_tax": r"\bclaim (?:back )?(?:the )?vat|\breclaim\w*|\brecover\w* (?:the )?vat|\binput (?:vat|tax)|\bvat back\b",
    "input_tax_before_registration": r"\b(?:only|just) (?:got|became) registered|\bregistration (?:only )?came through|\bbefore (?:i was|i got|my|the) (?:vat )?regist\w*|\bbefore (?:i |we )?(?:registered|registering|registration)\b.*\b(?:vat|claim|recover)|\bpre-?registration (?:costs|purchases|expenses)",
    "imports": r"\bsuppliers? (?:in|from) (?:china|india|turkey|abroad|overseas|the uk|the us)|\bfrom china\b|\bimport\w*|\bcustoms\b|\bshipp\w* (?:in|from) (?:abroad|overseas|china|india)",
    "tax_inclusive": r"\binclud\w* (?:the )?vat|\+ ?vat\b|\bplus vat|\bon top\b|\bprice with vat|\binclusive of vat|\bvat[- ]inclusive|\bprice (?:includes|including) vat|\bshow (?:prices )?(?:with|including) vat",
    "date_of_supply": r"\badvance\b|\bwhen (?:do|does|is) (?:the )?vat (?:due|charged|apply)|\bdate of supply|\badvance payment|\bdeposit\b|\bpaid (?:in )?advance",
    "place_of_supply": r"\bplace of supply|\bwhere (?:is|are) (?:the )?(?:supply|service) (?:made|supplied)",
    "electronic_services": r"\bonline (?:course|class|classes|lessons?|subscriptions?)|\bdownload\w*|\bstreaming|\bapps?\b|\bsoftware\b|\be-?books?",
    "credit_note": r"\bcredit note|\brefund(?:ed|s)?\b|\breturned (?:goods|items|products)",
    "bad_debt": r"\bnever paid|\bdid(?:n't| not) pay\b|\bbad debt|\bunpaid invoice|\bcustomer (?:won't|will not|refuses to) pay",
    "penalties": r"\bpenalt\w*|\bfine(?:s|d)?\b|\blate (?:filing|payment|registration)",
    "discount": r"\bdiscount\w*|\bprice reduction|\bpromo\w*",
    "vouchers": r"\bvouchers?\b|\bgift cards?\b|\bgift certificates?",
    "healthcare": r"\bclinic\b|\bmedical\b|\bhealth ?care|\bdoctor\b|\bdentist\b|\bphysio\w*|\bnurs\w*",
    "education": r"\btutor\w*|\bschool fees|\bnursery\b|\bkindergarten|\buniversity\b|\beducation\w*",
    "exempt_residential": r"\brent(?:ing)? (?:out )?(?:a |my |the )?(?:flat|apartment|villa|house|home)|\bresidential (?:rent|lease|property)",
    "tax_group": r"\btax group|\bgroup registration|\bregister (?:both|two|my) companies together",
    "non_resident": r"\bnon-?resident|\bnot (?:based|resident) in (?:the )?uae|\bforeign (?:business|company) selling",
    "capital_assets_scheme": r"\bcapital assets? scheme|\bexpensive (?:equipment|machine|asset)",
    "zero_rated": r"\bzero[- ]?rat\w*|\bexempt\w*|\b0 ?% vat",
    # article-level topics of the same map (art:...), for needs with no curated topic
    "art:FTA-VAT-ER|62": r"\bhow often\b[^.?!]*\b(?:file|return|submit)|\bmonthly or (?:quarterly|every (?:3|three) months)|\btax period",
    "art:FTA-VAT-DL8|74": r"\bmore than (?:the )?(?:vat|5 ?%|tax) i (?:charged|collected)|\bexcess (?:recoverable )?(?:vat|tax)|\bpaid more (?:vat|tax|5 ?%) than|\bis more than (?:the|what) i (?:charged|collected)",
}.items()}
# Questions about another tax or legal regime, or that the stored VAT texts cannot support. They are never answered
# from the VAT texts and never certified, whatever v7 classified.
OTHER_REGIME = re.compile(r"\bcorporate tax|\bzatca\b|\bgst\b|\bhmrc\b|\b(?:uk|saudi|ksa|indian?|german|european|eu) vat\b|"
                          r"\bunder (?:saudi|uk|indian|omani) (?:rules|law)|\bzakat\b|\bemiratis(?:ation|ization)|\bincome tax\b|"
                          r"\bemployment contract|\bgratuity\b", re.I)
# Non-tax matters: out of scope only when the question has no VAT word at all
NON_TAX = re.compile(r"\blicen[cs]e (?:renew\w*|expir\w*|cost|fee)|\brenew\w* (?:a |my |the |it|our )?(?:home )?(?:business )?licen[cs]e|"
                     r"\bbank loans?\b|\bvisa (?:renewal|application|status)\b|\btenancy contract|\blandlord noc", re.I)
# Explicit UAE marker next to "vat" (tech-sonu re-check): only then is a question about another tax regime "mixed"
UAE_VAT = re.compile(r"\b(?:uae|emirates?|fta|emaratax|trn|federal tax authority)\b[^.?!]{0,40}\bvat\b|\bvat\b[^.?!]{0,40}\b(?:uae|emirates?|fta|emaratax|trn)\b", re.I)
FOREIGN_TAX = re.compile(r"\bzatca\b|\bgst\b|\bhmrc\b|\b(?:uk|saudi|ksa|indian?|german|european|eu) vat\b|\bunder (?:saudi|uk|indian|omani) (?:rules|law)", re.I)
# Triggers too generic to override v7's "no VAT word" out-of-scope verdict on their own
GENERIC_TRIGGERS = {"penalties", "credit_note", "electronic_services", "healthcare", "education", "date_of_supply", "discount",
                    "records", "vouchers", "payment", "bad_debt", "agent", "non_resident"}
# Penalty AMOUNTS are not in the stored texts: such questions stay in scope (penalty article added) but are never certified.
PENALTY_AMOUNT = re.compile(r"\b(?:how much|what) (?:is|'s|will be) the (?:fine|penalty)\b|\bwhats? the (?:fine|penalty)\b|\bfine (?:is|of) (?:aed )?\d", re.I)
UNSUPPORTED = re.compile(r"\bwhich button|\bwhat (?:screen|button)|\bemaratax screens?|\bhow much should i pay (?:a|my) (?:bookkeeper|accountant)|"
                         r"\be-?invoicing\b", re.I)
TRIGGER_CAP = 4              # more triggered topics than this: trigger nothing (too vague to complete from the map)


_VERSIONS: dict = {}


def _added_by(raw: str) -> str:
    for prefix, code in ADDED_BY.items():
        if raw == prefix or raw.startswith(prefix + ":"):
            return code
    return "other"


def _version_of(con: sqlite3.Connection, passage_id: str) -> str:
    db = con.execute("PRAGMA database_list").fetchone()[2]          # cache per database file, never shared across builds
    cache = _VERSIONS.setdefault(db, {})
    doc = passage_id.split("#", 1)[0]
    if doc not in cache:
        row = con.execute("SELECT version_id FROM documents WHERE doc_id = ?", (doc,)).fetchone()
        cache[doc] = row[0] if row else "unknown"
    return cache[doc]


def triggered_topics(question: str) -> list[str]:
    """Owner-language topics, at most TRIGGER_CAP (in LEXICON order). Certification is off, so extra topics only add recall."""
    hits = [t for t, rx in LEXICON.items() if rx.search(question)]
    return hits[:TRIGGER_CAP]


def _split(ref: str) -> tuple[str, str | None]:
    src, art = ref.split("|", 1)
    return src, (None if art in ("*", "None") else art)


def retrieve(con: sqlite3.Connection, question: str) -> dict:
    """Returns the WS-B retrieval core: items, required provisions with roles, completeness, scope and an ordered trace."""
    r7 = P.retrieve(con, question)
    T = P.tables()["topics"]
    trace = [{"step": "v7_pipeline", "detail": f"status={r7['status']} intents={r7['classification']['intents']}"}]
    got = list(r7["passages"])[:MAX_PASSAGES]
    oos = r7["status"] == "out_of_scope"
    regime, unsupported = bool(OTHER_REGIME.search(question)), bool(UNSUPPORTED.search(question))
    foreign = bool(FOREIGN_TAX.search(question))
    mixed = regime and not foreign and bool(UAE_VAT.search(question))
    if NON_TAX.search(question) and not re.search(r"\bvat\b|\btax\b", question, re.I):
        unsupported = True                                    # a licence, loan or tenancy question with no tax word
    if mixed:
        regime = False
        trace.append({"step": "scope_mixed", "detail": "another regime mentioned alongside a UAE VAT need; VAT part only"})
    trig = triggered_topics(question)
    penalty_amount = bool(PENALTY_AMOUNT.search(question))
    if penalty_amount and "penalties" not in trig:
        trig = trig + ["penalties"]
    specific = [t for t in trig if t not in GENERIC_TRIGGERS]
    if oos and not (regime or unsupported) and r7["classification"].get("reason", "").startswith("no VAT word") and specific:
        oos = False                                           # owner language names a VAT topic: answer it, never certify
        trace.append({"step": "scope_override", "detail": "v7 found no VAT word; owner-language triggers matched VAT topics"})
    if regime or unsupported:
        oos = True
        trace.append({"step": "scope_guard", "detail": "another regime" if regime else "not supported by the stored VAT texts"})
    known = set(r7["classification"]["intents"]) | set(r7["classification"]["secondary"])
    extra = [] if oos else [t for t in trig if t not in known and t in T]
    trace.append({"step": "owner_language_triggers", "detail": ",".join(extra) or "none"})

    def add(ref: str, label: str) -> bool:
        if len(got) >= MAX_PASSAGES or P._present(got, ref):
            return False
        row = P._fetch(con, ref)
        if row is None:
            return False
        got.append(dict(row, added_by=label))
        return True

    extra_req = []
    for t in extra:                                           # map completion for triggered topics (round-robin depth)
        for ref in T[t]["required"]:
            if ref not in r7["required"] and ref not in extra_req:
                extra_req.append(ref)
    for ref in extra_req:
        add(ref, "v8:map_completion")
    for p, kind, _src in P.partners(extra_req):              # cross-reference completion: implementing pairs only
        if kind == "implementing_pair":
            add(p, "v8:xref_pair")
    trace.append({"step": "budget", "detail": f"{len(got)}/{MAX_PASSAGES}"})

    roles = []
    for ref in ([] if oos else r7["required"]):
        roles.append((ref, "primary"))
    for ref in extra_req:
        roles.append((ref, "primary"))
    required = [{"source_id": _split(r)[0], "article": _split(r)[1], "role": role, "from": MAP_VERSION} for r, role in roles]
    missing = [r for r, _ in roles if not P._present(got, r)]
    if oos:
        status = "unknown"
    elif CERTIFY and r7["status"] == "complete" and r7["classification"]["intents"] and not extra and not missing and not penalty_amount and not mixed:
        status = "complete_for_map"
    elif missing:
        status = "incomplete"
    else:
        status = "unknown"        # every mapped provision is present but the topic match is uncertain: never certified
    trace.append({"step": "completeness", "detail": f"{status}; missing={missing}"})
    items = []
    for i, p in enumerate(got, 1):
        art = P.article_key(p["source_id"], p["locator"])
        items.append({"rank": i, "passage_id": p["passage_id"], "source_id": p["source_id"],
                      "article": _split(art)[1] if art else None, "locator": p["locator"],
                      "version_id": _version_of(con, p["passage_id"]), "url": p["url"], "added_by": _added_by(p.get("added_by", "bm25")),
                      "score": None, "text": p["text"]})
    return {"retrieval_version": VERSION, "items": items, "budget": {"max_passages": MAX_PASSAGES, "returned": len(items)},
            "required_provisions": required,
            "completeness": {"status": status, "missing_required": [{"source_id": _split(r)[0], "article": _split(r)[1]} for r in missing],
                             "map_version": MAP_VERSION, "map_review_status": "draft-unreviewed"},
            "scope": {"in_scope": not oos, "class": ("unsupported" if unsupported and not regime else "out_of_scope") if oos else "in_scope",
                      "reason": r7["classification"].get("reason") or ("outside the VAT texts" if oos else "VAT question")},
            "trace": trace, "v7_status": r7["status"]}
