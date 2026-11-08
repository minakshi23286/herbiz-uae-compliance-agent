"""Builds the D3 legal review package for a qualified UAE VAT reviewer (Workstream B). READ-ONLY on every input.

Inputs (never modified): the draft provision map (classifier_c1p2.topics(): 48 topics), the article index and link table
(data/CL_article_index_v6.json, data/CL_expansion_v6.json), the read-only DB copy (locators, pages, versions), Workstream C's
COMMITTED source register and validity export (pinned commit, read with `git show`), and the frozen v8/v9 label reviews.
Outputs: docs/review_d3/ (package markdown, decision register xlsx, machine-readable data json).
Every relationship in the output is labelled AI-GENERATED DRAFT - NOT LEGALLY APPROVED.

    python3 experiments/ws_b/CL_build_d3_review_pack.py --c-commit e04f2dc
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from compliance_agent.llm_lab import classifier_c1p2 as K, pipeline_v7 as P7  # noqa: E402

OUT = ROOT / "docs" / "review_d3"
C_REPO = ROOT.parent / "CL_compliance_agent_app_ws_c"
DB = ROOT / "data" / "CL_ws_b_exact_copy.sqlite3"
DRAFT = "AI-generated draft — not legally approved"
SHORT = {"FTA-VAT-DL8": "DL", "FTA-VAT-ER": "ER", "FTA-VAT-REG-PAGE": "FTA page"}

MEANING = {   # plain-language business meaning + a typical owner question (AI-written; part of what the reviewer checks)
    "mandatory_registration": ("When a business must register for VAT (taxable supplies above AED 375,000 in 12 months or expected in the next 30 days).", "My sales passed 380k this year — do I have to register?"),
    "voluntary_registration": ("When a business may choose to register (supplies or expenses above AED 187,500).", "I'm below 375k but spend a lot on supplies — can I register anyway?"),
    "deregistration": ("When a registrant must or may cancel registration, how to apply, and the restrictions on voluntary deregistration.", "I'm closing my home bakery — how do I cancel my TRN?"),
    "threshold_calculation": ("What counts towards the registration threshold (which supplies, imports, related persons, capital assets).", "Do my export sales count towards the 375k limit?"),
    "related_parties": ("When related persons' businesses are added together for the threshold (aggregation) and who counts as related.", "My sister and I each have a licence — will the FTA add our sales together?"),
    "tax_group": ("Registering two or more related businesses as one tax group, and its conditions and effects.", "Can my husband's company and mine file one VAT return?"),
    "non_resident": ("Registration of a seller with no place of establishment in the UAE.", "I live in Oman and sell to buyers in Dubai — do I need a UAE TRN?"),
    "registration_exception": ("Exception from registration for a person whose supplies are all zero-rated.", "All my sales are exports — can I ask not to be registered?"),
    "capital_assets_threshold": ("Whether selling capital assets counts towards the registration threshold.", "Does selling my old oven count towards the limit?"),
    "zero_rated_or_exports": ("Zero-rating of exports of goods (and services) and the conditions/evidence for it.", "Do I charge 5% on orders I ship to Oman?"),
    "export_of_services": ("Zero-rating of services supplied to recipients outside the UAE.", "My client in London has no UAE office — 5% or 0%?"),
    "zero_rated": ("The list of zero-rated supplies in general.", "Is my supply zero-rated?"),
    "education": ("Zero-rating of qualifying education services.", "Do I charge VAT on my after-school tutoring?"),
    "healthcare": ("Zero-rating of qualifying healthcare services.", "Is my physiotherapy at home zero-rated?"),
    "exempt_supplies": ("The list of exempt supplies (no VAT charged, input tax generally not recoverable).", "Is home-made food exempt?"),
    "exempt_residential": ("Exemption of residential building rent/sale (other than zero-rated first supplies).", "Do I charge VAT on the flat I rent out?"),
    "exempt_land": ("Exemption of bare land.", "Is selling my empty plot exempt?"),
    "exempt_passenger": ("Exemption of local passenger transport.", "Do I charge VAT on my school-run driving service?"),
    "financial_services": ("Treatment of financial services (exempt vs taxable/margin-based).", "Is interest on my business loan subject to VAT?"),
    "deemed_supply": ("Goods/services treated as supplied without payment (gifts, own use, samples) and the exceptions.", "Do I pay VAT on free samples I give away?"),
    "agent": ("Supplies made through an agent / on someone's behalf and who accounts for VAT.", "My friend's shop sells my items for 20% — who charges VAT?"),
    "value_of_supply": ("How the taxable value of a supply is determined.", "Is the delivery fee part of the price I charge VAT on?"),
    "discount": ("Value of supply where discounts or subsidies are given.", "I give a 20% discount — VAT on the full or reduced price?"),
    "related_value": ("Value of supplies between related parties (market value rule).", "I sell to my cousin's shop at a big discount — which value counts?"),
    "tax_inclusive": ("Whether displayed prices must include VAT (tax-inclusive pricing).", "Must my Instagram prices include VAT?"),
    "profit_margin": ("The profit-margin scheme for second-hand goods.", "I resell pre-loved bags — VAT on the full price or only my margin?"),
    "place_of_supply": ("Where a supply of goods/services is treated as made (UAE or abroad).", "My customers are in Saudi — is my supply in the UAE?"),
    "electronic_services": ("Place of supply and rules for telecommunications and electronic services (downloads, online courses).", "Do I charge VAT on printable downloads bought from the USA?"),
    "date_of_supply": ("When VAT becomes due (date of supply), including deposits and advance payments.", "Bride pays a deposit 3 months ahead — when is VAT due?"),
    "imports": ("VAT on imports, including the reverse-charge mechanism.", "I import fabric from China — VAT at customs or reverse charge?"),
    "designated_zone": ("Treatment of supplies in designated (free) zones.", "My warehouse is in JAFZA — is it outside the UAE for VAT?"),
    "capital_assets_scheme": ("Input-tax adjustments for capital assets over time (capital assets scheme).", "I bought an expensive machine — do I adjust input tax later?"),
    "input_tax": ("Recovery of input tax paid on business purchases.", "Can I claim back the VAT on my packaging?"),
    "input_tax_before_registration": ("Recovery of input tax paid before registration.", "I bought equipment before my TRN came — can I still claim it?"),
    "blocked_input_tax": ("Input tax that cannot be recovered (e.g. entertainment, certain motor vehicles).", "Can I recover VAT on a client dinner?"),
    "bad_debt": ("Bad-debt relief: adjusting output tax when a customer never pays.", "A client never paid — can I get the VAT back?"),
    "tax_invoice": ("When a tax invoice must be issued and what it must contain.", "What must be on my tax invoice?"),
    "credit_note": ("Tax credit notes and output-tax adjustments after refunds or price reductions.", "A customer returned items — do I issue a credit note?"),
    "tax_return": ("Tax periods, filing VAT returns and their deadlines.", "Do I file monthly or quarterly, and by when?"),
    "payment": ("Paying (settling) the VAT due.", "When do I have to pay the VAT?"),
    "records": ("Record-keeping duties and retention periods.", "How long must I keep my receipts?"),
    "penalties": ("Administrative penalties (amounts are in a separate Cabinet Decision on tax administrative penalties - per Workstream C's register CD 40/2017 as amended by CD 129/2025, in force 2026-04-14 - not held in the knowledge base).", "What is the fine for registering late?"),
    "evasion": ("Tax evasion and its consequences.", "What if I hide cash sales?"),
    "vat_rate": ("The standard VAT rate and scope of the tax.", "What is the VAT rate in the UAE?"),
    "tourist": ("VAT refunds for tourists.", "Can my tourist customers get the VAT back?"),
    "new_residence": ("VAT refund for UAE nationals building a new residence.", "Can I get VAT back on building my house?"),
    "vouchers": ("Value and timing of supplies of vouchers / gift cards.", "When do I charge VAT on gift cards?"),
    "composite_supply": ("Single supplies with more than one component (bundles) vs separate supplies.", "My class comes with an ingredients box — one supply or two?"),
}

KNOWN_GAPS = [   # (id, topic, gap, evidence, question, provisions it concerns) - evidence-backed, from B reports and the independent check
    ("GAP-01", "deemed_supply", "Deemed-supply topic does not require DL Art. 37 (Value of Deemed Supply).", "v9 Q914: retrieval verified while DL 37 was missing (silent-incomplete).", "Add DL 37 as required?", ["FTA-VAT-DL8|37", "FTA-VAT-DL8|11"]),
    ("GAP-02", "(no topic)", "No topic for refunds of excess recoverable tax (DL Art. 74, ER Art. 65). DL 74 is also outdated (G3).", "v9 Q916: required articles never retrieved.", "Create a topic; confirm articles.", ["FTA-VAT-DL8|74", "FTA-VAT-ER|65"]),
    ("GAP-03", "composite_supply", "Bundled-supply topic does not include ER Art. 26 (Apportionment of Single Consideration).", "v9 Q924 missed ER 26.", "Add ER 26 as required or supporting?", ["FTA-VAT-ER|26"]),
    ("GAP-04", "mandatory_registration", "Mandatory-registration topic does not require DL Art. 19 (calculating the threshold) when an amount is stated; a separate 'base rule' adds it only in some cases.", "v9 Q922 (independent label reviewer requires DL 19).", "Decide when DL 19 is required.", ["FTA-VAT-DL8|19", "FTA-VAT-DL8|13"]),
    ("GAP-05", "11 rate-category topics", "AI-designed rule: every rate-category topic requires both DL Art. 45 (zero rate) and DL Art. 46 (exempt supplies).", "Added after v8 Q824 (an 'is it exempt?' question also needed the zero-rate list).", "Approve the rule or limit it.", ["FTA-VAT-DL8|45", "FTA-VAT-DL8|46"]),
    ("GAP-06", "export_of_services / electronic_services", "AI-designed: export of services = DL 45 + ER 31; ER 31 supports electronic services.", "v7 Q703/Q718, v8 Q718.", "Confirm.", ["FTA-VAT-ER|31", "FTA-VAT-DL8|31"]),
    ("GAP-07", "deregistration", "AI-designed: the whole deregistration chapter (DL 21, 22, 23 + ER 14) is required for any deregistration question.", "v5 Y03, v7 Q710. ER 14 carries the unresolved G1 deadline conflict.", "Confirm or narrow.", ["FTA-VAT-DL8|21", "FTA-VAT-DL8|22", "FTA-VAT-DL8|23", "FTA-VAT-ER|14"]),
    ("GAP-08", "base rule (several topics)", "AI-designed companion rule: when a specific topic (exempt, export, related parties, invoices, evasion...) is asked in a registration context, DL 13 + ER 7 (+ DL 19 if an amount is stated) are also required.", "v3/v4 diagnosis (a specific topic displaced the base rule).", "Approve the rule or its trigger list.", ["FTA-VAT-DL8|13", "FTA-VAT-ER|7", "FTA-VAT-DL8|19"]),
    ("GAP-09", "implementing-pair links", "Decree-Law <-> Executive Regulation 'implementing pair' links were generated automatically from article-title similarity: 46 pairs (92 directed links). Some may be wrong (e.g. DL 46 <-> ER 52, DL 7 <-> ER 50/54, DL 8 <-> ER 46).", "Link table in the decision register (sheet 'Links').", "Approve / correct each link.", []),
    ("GAP-10", "sibling links / cross-references", "Sibling links (neighbouring articles with a shared title word) and explicit cross-references were extracted automatically; bare 'Article (N)' references in the Executive Regulation were skipped as ambiguous.", "Link table.", "Spot-check.", []),
    ("GAP-11", "162 article topics", "Every article also has an automatic 'article topic' (the article + up to 2 implementing-pair articles), used when no curated topic fits.", "Map design.", "Accept as fallback or not.", []),
    ("GAP-12", "penalties", "Penalty amounts are set by the Cabinet Decision on tax administrative penalties (per Workstream C's register: CD 40/2017 as amended by CD 129/2025, in force 2026-04-14; observed by C, not collected, not verified here); the topic rests on DL Art. 76 only.", "C register / validity reports.", "Decide whether answers may cite amounts; confirm the current instrument.", ["FTA-VAT-DL8|76"]),
    ("GAP-13", "credit_note", "Credit-note topic requires DL 63 + ER 60 but not DL Art. 70 (Conditions and Requirements for Issuing the Tax Credit Note); DL 70 is in no topic.", "v8 Q814 (independent label reviewer requires DL 70).", "Add DL 70 as required?", ["FTA-VAT-DL8|70"]),
    ("GAP-14", "input_tax / blocked_input_tax / refunds", "New or changed law not mapped: DL Art. 54 (bis) (added by DL 16/2025; not in our copy) is in no topic; DL 74 (changed) has no topic (GAP-02); DL 79 (bis) (repealed) must not be used as live law.", "C validity export (G3).", "Map DL 54 (bis) once collected; confirm the treatment of repealed articles.", ["FTA-VAT-DL8|54 (bis)", "FTA-VAT-DL8|74", "FTA-VAT-DL8|79 (bis)"]),
    ("GAP-15", "tax_return", "Map defect: DL Art. 71 appears as both required and supporting in the tax-return topic (duplicate in the draft data).", "Independent package check.", "Confirm DL 71 as required; remove from supporting.", ["FTA-VAT-DL8|71"]),
    ("GAP-16", "tax_return", "ER Art. 62 (Length of tax period) is only supporting; the independent label reviewer would require it for 'monthly or quarterly?' questions.", "v8 Q806.", "Make ER 62 required?", ["FTA-VAT-ER|62"]),
    ("GAP-17", "imports", "Imports topic (DL 48 + ER 47) omits ER Art. 48 (Calculation of Tax under the Reverse Charge) although the topic is about reverse charge.", "Independent package check (title family).", "Add ER 48?", ["FTA-VAT-ER|48", "FTA-VAT-DL8|48"]),
    ("GAP-18", "input_tax", "Input-tax topic (DL 54 + DL 55) omits DL Art. 58 (Calculating the Input Tax that may be Recovered) and ER Art. 55 (Apportionment of Input Tax).", "Independent package check (title family).", "Add DL 58 / ER 55?", ["FTA-VAT-DL8|58", "FTA-VAT-ER|55"]),
    ("GAP-19", "(no topic)", "Articles needed by test questions but in no curated topic: ER Art. 36 (Zero-rating of precious metals; v9 Q921) and DL Art. 7 (Supply in Special Cases, e.g. transfer of a whole business; v9 Q917).", "v9 Q917, Q921.", "Add to zero_rated / create a topic?", ["FTA-VAT-ER|36", "FTA-VAT-DL8|7"]),
]


def git_show(commit: str, path: str) -> dict:
    return json.loads(subprocess.check_output(["git", "-C", str(C_REPO), "show", f"{commit}:{path}"], text=True))


def provision_issues(validity: dict, key: str) -> list[dict]:
    src, art = key.split("|", 1)
    out = []
    for i in validity["issues"]:
        for p in i["provisions"]:
            if p == key or p == f"{src}|*":
                out.append({"id": i["id"], "kind": i["kind"], "message": i["message"]})
                break
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--c-commit", required=True)
    a = ap.parse_args(argv)
    validity = git_show(a.c_commit, "knowledge_base/CL_source_validity.json")
    register = git_show(a.c_commit, "knowledge_base/CL_source_register.json")
    cur = {s: v["version_id"] for s, v in validity["current_versions"].items()}
    url = {v["version_id"]: v["url"] for s in register["sources"] for v in s["versions"]}
    titles = {s["source_id"]: s["title"] for s in register["sources"]}
    T, A, L = K.topics(), P7.tables()["articles"], P7.tables()["links"]
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    def locate(key: str) -> dict:
        src, art = key.split("|", 1)
        ver = cur.get(src)
        if art == "*":
            row = con.execute("SELECT locator FROM passages WHERE version_id = ? AND text LIKE ? ORDER BY seq LIMIT 1",
                              (ver, "%registration threshold of AED%")).fetchone()
            loc = row[0] if row else "web page"
            title = "Registration for VAT (FTA web page)"
        else:
            num, _, suf = art.partition(" ")
            base = f"Article {num} {suf}" if suf else f"Article {num}"
            row = con.execute("SELECT locator FROM passages WHERE version_id = ? AND (locator LIKE ? OR locator = ?) ORDER BY seq LIMIT 1",
                              (ver, base + ",%", base)).fetchone()
            loc = re.sub(r", part \d+$", "", row[0]) if row else "NOT FOUND IN CURRENT VERSION"
            title = A.get(key, {}).get("title", "")
        return {"key": key, "label": f"{SHORT[src]} Art. {art}" if art != "*" else SHORT[src], "title": title,
                "source_title": titles.get(src, src), "version_id": ver, "locator": loc, "url": url.get(ver),
                "issues": provision_issues(validity, key)}

    topics = []
    for name in sorted(T):
        t = T[name]
        req, sup = t["required"], t["supporting"]
        links = []
        for r in req + sup:
            for x in L.get(r, []):
                links.append({"from": r, "to": x["key"], "why": x["why"], "to_title": x["title"]})
        exceptions = sorted({x["to"] for x in links if re.search(r"exception|exempt", x["to_title"], re.I)} - set(req) - set(sup))
        topics.append({"id": f"T{len(topics) + 1:02d}", "topic": name, "meaning": MEANING.get(name, ("(missing)", ""))[0],
                       "example_question": MEANING.get(name, ("", ""))[1], "status": DRAFT, "origin": t.get("origin", "v5 index"),
                       "required": [locate(k) for k in req], "supporting": [locate(k) for k in sup],
                       "exceptions": [locate(k) for k in exceptions],
                       "cross_references": [{**x, "to_label": locate(x["to"])["label"]} for x in links if x["why"] == "explicit_reference"],
                       "implementing_pairs": [{**x, "to_label": locate(x["to"])["label"]} for x in links if x["why"] == "implementing_pair"],
                       "siblings": [{**x, "to_label": locate(x["to"])["label"]} for x in links if x["why"] == "sibling"]})
    # flagged evaluation labels: reviewer needs_legal_review OR partly_agree (v8, v9)
    flagged = []
    for v in ("v8", "v9"):
        qs = {q["id"]: q for q in json.loads((ROOT / "fixtures" / f"CL_llm_eval_unseen_{v}.json").read_text())["questions"]}
        rv = json.loads((ROOT / "fixtures" / f"CL_llm_eval_unseen_{v}_label_review.json").read_text())["reviews"]
        for r in rv:
            if r["needs_legal_review"] or r["verdict"] == "partly_agree":
                q = qs[r["id"]]
                flagged.append({"id": r["id"], "set": v, "category": q["category"], "question": q["text"],
                                "author_required": [f"{s}|{x}" if x is not None else f"{s}|*" for s, x in q["required_sources"]],
                                "author_justification": q.get("label_justification", ""), "author_flag": q.get("needs_legal_review"),
                                "author_flag_reason": q.get("needs_legal_review_reason", ""),
                                "reviewer_verdict": r["verdict"], "reviewer_required": [f"{s}|{x}" if x is not None else f"{s}|*" for s, x in r["reviewer_required"]],
                                "reviewer_flag": r["needs_legal_review"], "reviewer_reason": r.get("reason", ""),
                                "missing_from_author": r.get("missing_from_author", []), "not_needed_in_author": r.get("not_needed_in_author", [])})
    all_links = []
    seen = set()
    for k, xs in sorted(L.items()):
        for x in xs:
            pair = tuple(sorted((k, x["key"]))) + (x["why"],)
            if x["why"] != "explicit_reference" and pair in seen:
                continue
            seen.add(pair)
            all_links.append({"id": f"L{len(all_links) + 1:03d}", "from": k, "from_title": A.get(k, {}).get("title", ""),
                              "to": x["key"], "to_title": x["title"], "type": x["why"]})
    inputs = {"provision_map": "compliance_agent/llm_lab/classifier_c1p2.py topics() over compliance_agent/llm_lab/data/CL_provision_map_v7.json",
              "provision_map_sha256": hashlib.sha256((ROOT / "compliance_agent/llm_lab/data/CL_provision_map_v7.json").read_bytes()).hexdigest(),
              "classifier_c1p2_sha256": hashlib.sha256((ROOT / "compliance_agent/llm_lab/classifier_c1p2.py").read_bytes()).hexdigest(),
              "links_sha256": hashlib.sha256((ROOT / "compliance_agent/llm_lab/data/CL_expansion_v6.json").read_bytes()).hexdigest(),
              "ws_c_commit": a.c_commit, "ws_c_register_version": register.get("register_version"),
              "ws_c_validity_generated_for": validity["_meta"]["generated_for_date"], "database_md5": validity["_meta"]["database_md5"],
              "current_versions": cur}
    data = {"_notice": f"HerBiz D3 legal review data. Every relationship: {DRAFT}. Not legal or tax advice.", "inputs": inputs,
            "topics": topics, "known_gaps": [dict(zip(("id", "topic", "gap", "evidence", "question", "provisions"), g)) for g in KNOWN_GAPS],
            "flagged_labels": flagged, "links": all_links, "validity_issues": validity["issues"],
            "sources": [{"version_id": ver, "source_title": titles.get(src), "url": url.get(ver),
                         "latest_effective_as_stated": next((v.get("latest_effective_as_stated") for s2 in register["sources"] for v in s2["versions"] if v["version_id"] == ver), None),
                         "file_label": next((v.get("file_label") for s2 in register["sources"] for v in s2["versions"] if v["version_id"] == ver), None)} for src, ver in cur.items()],
            "versions": [{k: v.get(k) for k in ("version_id", "approved", "outdated", "fta_currency", "verification_status", "translation_status")} for v in validity["versions"]]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "CL_D3_review_data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(data)
    write_register(data)
    print(len(topics), "topics;", len(flagged), "flagged labels;", len(all_links), "links;", len(KNOWN_GAPS), "gaps")
    return 0


def fmt(p: dict) -> str:
    warn = "; ".join(f"⚠ {i['kind']} ({i['id']})" for i in p["issues"])
    return f"{p['label']} — {p['title']} [{p['version_id']}, {p['locator']}]" + (f" — {warn}" if warn else "")


def write_markdown(d: dict) -> None:
    I = d["inputs"]
    L = ["# HerBiz: D3 legal review package — VAT provision map (48 topics)", "",
         "**Business line:** HomepreunerHub / HerBiz · **Prepared:** 17 Oct 2026 by Workstream B (Claude Code) for a qualified UAE VAT reviewer · "
         "**Status of every relationship below: AI-generated draft — NOT legally approved.** Not legal or tax advice.", "",
         "Read the reviewer briefing first (`CL_D3_REVIEWER_BRIEFING.md`). Record decisions in `CL_D3_REVIEWER_DECISION_REGISTER.xlsx` (one row per item ID below).", "",
         "## Inputs (traceability)", "", "| Item | Value |", "|---|---|"]
    L += [f"| {k} | `{v}` |" for k, v in I.items()]
    L += ["", "## Official sources cited (current versions)", "", "| Version | Title | Effective (as stated in file) | File label | URL |", "|---|---|---|---|---|"]
    L += [f"| {x['version_id']} | {x['source_title']} | {x['latest_effective_as_stated']} | {x['file_label']} | {x['url']} |" for x in d["sources"]]
    L += ["", "Note: the current Executive Regulation file (FTA-VAT-ER@v3) has a file name beginning 'Law-No-8-of-2017…09-2026', but page 1 is the Executive Regulation (Workstream C register). All texts are self-described unofficial English translations; the Arabic text prevails.",
          "", "## Validity of sources (from Workstream C, committed register)", "",
          "| Version | Approved | Outdated | FTA currency | Verification | Translation |", "|---|---|---|---|---|---|"]
    L += [f"| {v['version_id']} | {v['approved']} | {v['outdated']} | {v['fta_currency']} | {v['verification_status']} | {v['translation_status']} |" for v in d["versions"]]
    L += ["", "| Issue | Kind | Provisions | Message |", "|---|---|---|---|"]
    L += [f"| {i['id']} | {i['kind']} | {', '.join(i['provisions'])} | {i['message']} |" for i in d["validity_issues"]]
    L += ["", "## Known gaps and disputed relationships (please decide each)", "", "| ID | Topic | Gap / disputed relationship | Evidence | Question for you | Provisions |", "|---|---|---|---|---|---|"]
    L += [f"| {g['id']} | {g['topic']} | {g['gap']} | {g['evidence']} | {g['question']} | {', '.join(g['provisions']) or '—'} |" for g in d["known_gaps"]]
    L += ["", "## The 48 topics", "", "Each topic: business meaning, example owner question, required articles (an answer must rest on all of them), supporting articles, "
          "related exception articles, and automatically generated cross-references / implementing pairs / siblings. Citations show the current version and page; ⚠ marks a Workstream C validity issue.", ""]
    for t in d["topics"]:
        L += [f"### {t['id']} — `{t['topic']}`", "", f"- **Meaning:** {t['meaning']}", f"- **Example owner question:** {t['example_question']}",
              f"- **Status:** {t['status']} · origin: {t['origin']}", "- **Required:**"]
        L += [f"  - {fmt(p)}" for p in t["required"]] or ["  - (none)"]
        L += ["- **Supporting:**"] + ([f"  - {fmt(p)}" for p in t["supporting"]] or ["  - (none)"])
        L += ["- **Candidate exception articles (keyword match on titles; not required/supporting):**"] + ([f"  - {fmt(p)}" for p in t["exceptions"]] or ["  - (none found)"])
        for name, key in (("Cross-references (explicit)", "cross_references"), ("Implementing pairs (auto, title-based)", "implementing_pairs"), ("Siblings (auto)", "siblings")):
            xs = t[key]
            L.append(f"- **{name}:** " + ("; ".join(f"{x['from'].split('|')[0].replace('FTA-VAT-', '')} {x['from'].split('|')[1]} → {x['to_label']} ({x['to_title']})" for x in xs) if xs else "(none)"))
        L += [f"- **Decision:** register row `{t['id']}` — Approve / Correct / Needs clarification", ""]
    L += ["## Flagged evaluation labels (independent label reviewer — an AI agent, NOT tax-qualified: needs legal review or partly agrees)", "",
          "These are test labels (which articles a correct answer needs). Your view decides whether the test or the map is right.", ""]
    for f in d["flagged_labels"]:
        L += [f"### {f['id']} ({f['set']}, {f['category']}) — AI label reviewer (not tax-qualified): {f['reviewer_verdict']}{' · flagged for legal review' if f['reviewer_flag'] else ''}", "",
              f"> {f['question']}", "", f"- **Author's required:** {', '.join(f['author_required']) or '(none)'} — {f['author_justification']}",
              f"- **AI label reviewer's required (not tax-qualified):** {', '.join(f['reviewer_required']) or '(none)'} — {f['reviewer_reason']}",
              f"- **Difference:** missing from author {f['missing_from_author'] or '—'}; not needed in author {f['not_needed_in_author'] or '—'}",
              f"- **Decision:** register row `{f['id']}`", ""]
    L += ["## Link table", "", f"All {len(d['links'])} automatically generated links are in the register (sheet `Links`) with a decision column.", ""]
    (OUT / "CL_D3_PROVISION_MAP_REVIEW_PACKAGE.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def write_register(d: dict) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    wb = Workbook()
    ws = wb.active
    ws.title = "Read me"
    for r in (["HerBiz — D3 reviewer decision register (VAT provision map)"],
              ["Every relationship is an AI-generated draft and is NOT legally approved until a qualified reviewer records a decision here."],
              ["Decision values: Approve / Correct / Needs clarification. For 'Correct', write the corrected articles in 'Correction'."],
              ["Sheets: Topics (48), Known gaps (12), Flagged labels, Links (auto-generated relationships)."],
              [f"Inputs: WS-C commit {d['inputs']['ws_c_commit']}, register {d['inputs']['ws_c_register_version']}, map sha256 {d['inputs']['provision_map_sha256'][:16]}…"],
              ["Not legal or tax advice. Reviewer name and date are required for each decision to count."]):
        ws.append(r)
    ws["A1"].font = Font(bold=True, size=14)
    ws.column_dimensions["A"].width = 140
    dv_text = '"Approve,Correct,Needs clarification"'
    head_fill = PatternFill("solid", fgColor="DDE7F0")

    def sheet(title, headers, rows, decision_col):
        s = wb.create_sheet(title)
        s.append(headers)
        for c in s[1]:
            c.font, c.fill = Font(bold=True), head_fill
        for r in rows:
            s.append(r)
        dv = DataValidation(type="list", formula1=dv_text, allow_blank=True, showErrorMessage=True,
                            errorTitle="Decision", error="Choose Approve, Correct or Needs clarification.")
        s.add_data_validation(dv)
        col = chr(ord("A") + decision_col)
        dv.add(f"{col}2:{col}{max(2, len(rows) + 1)}")
        dcol = chr(ord("A") + decision_col + 4)
        dd = DataValidation(type="date", operator="greaterThan", formula1="DATE(2026,1,1)", allow_blank=True, showErrorMessage=True,
                            errorTitle="Decision date", error="Enter a date (after 1 Jan 2026).")
        s.add_data_validation(dd)
        dd.add(f"{dcol}2:{dcol}{max(2, len(rows) + 1)}")
        for i, h in enumerate(headers):
            s.column_dimensions[chr(ord("A") + i)].width = 18 if i != len(headers) - 6 else 30
        for row in s.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        s.freeze_panes = "B2"

    tail = ["Decision", "Correction (articles)", "Reviewer notes", "Reviewer name", "Decision date"]
    sheet("Topics", ["ID", "Topic", "Meaning", "Required (draft)", "Supporting (draft)", "Candidate exceptions (keyword)", "Cross-references",
                     "Validity warnings (issue id)", "Status"] + tail,
          [[t["id"], t["topic"], t["meaning"], "; ".join(p["label"] for p in t["required"]), "; ".join(p["label"] for p in t["supporting"]),
            "; ".join(p["label"] for p in t["exceptions"]), "; ".join(f"{x['from']} -> {x['to_label']}" for x in t["cross_references"]),
            "; ".join(sorted({f"{p['label']}: {i['kind']} [{i['id']}]" for p in t['required'] + t['supporting'] for i in p['issues']})), t["status"], "", "", "", "", ""]
           for t in d["topics"]], 9)
    sheet("Known gaps", ["ID", "Topic", "Gap / disputed relationship", "Evidence", "Question", "Provisions", "Status"] + tail,
          [[g["id"], g["topic"], g["gap"], g["evidence"], g["question"], ", ".join(g["provisions"]), DRAFT, "", "", "", "", ""] for g in d["known_gaps"]], 7)
    sheet("Flagged labels", ["ID", "Set", "Category", "Question", "Author required (AI test author)", "AI label reviewer required (not tax-qualified)", "AI label reviewer verdict / flag"] + tail,
          [[f["id"], f["set"], f["category"], f["question"], ", ".join(f["author_required"]), ", ".join(f["reviewer_required"]),
            f"{f['reviewer_verdict']}{' / legal review' if f['reviewer_flag'] else ''}: {f['reviewer_reason']}", "", "", "", "", ""] for f in d["flagged_labels"]], 7)
    sheet("Links", ["ID", "From", "From title", "To", "To title", "Type", "Status"] + tail,
          [[x["id"], x["from"], x["from_title"], x["to"], x["to_title"], x["type"], DRAFT, "", "", "", "", ""] for x in d["links"]], 7)
    wb.save(OUT / "CL_D3_REVIEWER_DECISION_REGISTER.xlsx")


if __name__ == "__main__":
    raise SystemExit(main())
