"""Plain-English -> legal-term concept index for UAE VAT (Decree-Law No. 8 of 2017 and its Executive Regulation).

A general back-of-book style index: each concept lists words or phrases an owner might use (triggers) and the words the
law uses for the same idea (law_terms). It covers the main VAT topics across the whole law, not individual test
questions. Law terms are matched against ARTICLE TITLES only, so nothing here can add a passage whose title does not
carry the concept. Original source text and the main search results are unchanged.
"""
from __future__ import annotations

import re

CONCEPTS: dict[str, dict] = {
    "threshold":      {"triggers": ["limit", "cap", "ceiling", "threshold", "turnover", "how much can i", "below", "under the", "over the", "exceed", "crossed", "passed the"],
                       "law_terms": ["registration", "threshold", "calculating", "mandatory"]},
    "registration":   {"triggers": ["register", "registration", "registered", "sign up", "get vat", "vat number", "trn", "tax number"],
                       "law_terms": ["registration", "mandatory", "application"]},
    "voluntary":      {"triggers": ["voluntar", "optional", "choose to", "allowed to register", "can i register", "register anyway", "even though", "want to register"],
                       "law_terms": ["voluntary", "registration"]},
    "deregistration": {"triggers": ["cancel", "deregist", "de-regist", "close my vat", "stop being registered", "remove my registration", "give up my trn", "no longer need"],
                       "law_terms": ["deregistration", "cases", "voluntary", "application"]},
    "deadline":       {"triggers": ["deadline", "how long", "how many days", "late", "when do i", "when should", "by when", "time limit", "backdate", "back date"],
                       "law_terms": ["mandatory", "registration", "application", "date"]},
    "related":        {"triggers": ["sister", "brother", "husband", "wife", "family", "relative", "partner", "my mother", "my father", "two businesses", "both businesses",
                                    "split", "divide", "separate businesses", "combine", "together", "another company", "related"],
                       "law_terms": ["related", "parties", "aggregation", "group"]},
    "tax_group":      {"triggers": ["tax group", "group registration", "register together", "joint registration"],
                       "law_terms": ["group", "registration"]},
    "imports":        {"triggers": ["import", "bring in", "buy from abroad", "from china", "from turkey", "from india", "shipping in", "customs"],
                       "law_terms": ["import", "concerned", "calculating", "threshold"]},
    "exports":        {"triggers": ["export", "abroad", "overseas", "outside the uae", "outside uae", "foreign customers", "international customers", "ship to"],
                       "law_terms": ["zero", "rate", "export", "exception"]},
    "zero_rated":     {"triggers": ["zero rate", "zero-rate", "zero rated", "0%", "zero percent"],
                       "law_terms": ["zero", "rate", "exception"]},
    "exempt":         {"triggers": ["exempt", "no vat on", "vat free", "vat-free"],
                       "law_terms": ["exempt", "exemption"]},
    "residential":    {"triggers": ["flat", "apartment", "villa", "house i rent", "rent out", "tenant", "landlord", "residential"],
                       "law_terms": ["residential", "buildings", "exemption"]},
    "land":           {"triggers": ["land", "plot"], "law_terms": ["bare", "land", "exemption"]},
    "capital_assets": {"triggers": ["oven", "mixer", "machine", "equipment", "laptop", "camera", "car", "van", "furniture", "printer", "sell my old", "used equipment", "asset"],
                       "law_terms": ["capital", "assets"]},
    "non_resident":   {"triggers": ["not based", "foreign company", "non resident", "non-resident", "outside the country", "abroad company", "live outside"],
                       "law_terms": ["non", "resident", "registration"]},
    "education":      {"triggers": ["tutor", "tuition", "teaching", "school", "course", "classes", "education"],
                       "law_terms": ["education", "zero"]},
    "healthcare":     {"triggers": ["clinic", "health", "medical", "therapy", "physio"], "law_terms": ["healthcare", "zero"]},
    "free_zone":      {"triggers": ["free zone", "freezone", "designated zone"], "law_terms": ["designated", "zone"]},
    "second_hand":    {"triggers": ["second hand", "second-hand", "used goods", "pre-loved", "preloved", "resell used", "thrift"],
                       "law_terms": ["profit", "margin"]},
    "invoices":       {"triggers": ["invoice", "receipt", "bill"], "law_terms": ["tax", "invoice"]},
    "returns":        {"triggers": ["return", "file vat", "filing", "quarterly", "tax period"], "law_terms": ["tax", "return", "period"]},
    "records":        {"triggers": ["record", "keep documents", "bookkeeping", "books"], "law_terms": ["record", "keeping"]},
    "evasion":        {"triggers": ["hide", "cash sales", "not declare", "don't declare", "avoid vat", "evade", "under the table"],
                       "law_terms": ["evasion", "penalties"]},
    "penalties":      {"triggers": ["fine", "penalty", "penalties"], "law_terms": ["administrative", "penalties"]},
    "gifts_samples":  {"triggers": ["free sample", "gift", "giveaway", "for free"], "law_terms": ["deemed", "supply"]},
    "agent":          {"triggers": ["agent", "on behalf", "commission", "marketplace", "noon", "amazon"], "law_terms": ["agent", "supply"]},
    "vat_rate":       {"triggers": ["what rate", "how much vat", "5%", "percent vat"], "law_terms": ["tax", "rate"]},
}

# Concepts for which the base registration rule (ER Art. 7 + FTA registration page) is always given to the model.
REGISTRATION_CORE = {"threshold", "registration", "voluntary", "deregistration", "deadline", "related", "imports", "exports", "capital_assets", "non_resident"}

MONEY_RX = re.compile(r"(?:aed|dhs?|dirhams?)\s*\d[\d,\.]*\s*k?|\d[\d,\.]*\s*(?:k|aed|dhs?|dirhams?)\b", re.I)


def detect(question: str) -> tuple[set[str], list[str]]:
    """Concepts triggered by the question, and the law words they contribute. Money amounts imply 'threshold'."""
    low = " " + re.sub(r"\s+", " ", question.lower()) + " "
    found: set[str] = set()
    for name, c in CONCEPTS.items():
        for t in c["triggers"]:
            if re.search(r"(?<![a-z])" + re.escape(t), low):
                found.add(name)
                break
    if MONEY_RX.search(question):
        found.add("threshold")
    words = [w for n in sorted(found) for w in CONCEPTS[n]["law_terms"]]
    return found, words


# Intent -> primary provisions (the articles a correct answer must rest on) and supporting guidance.
# Built from the law's own structure (article titles), not from test questions. ("FTA-VAT-REG-PAGE", None) = FTA page.
INTENT_PROVISIONS: dict[str, dict] = {
    "mandatory_registration": {"primary": [("FTA-VAT-DL8", 13), ("FTA-VAT-ER", 7)], "supporting": [("FTA-VAT-REG-PAGE", None)]},
    "voluntary_registration": {"primary": [("FTA-VAT-DL8", 17), ("FTA-VAT-ER", 8)], "supporting": [("FTA-VAT-REG-PAGE", None)]},
    "deregistration":         {"primary": [("FTA-VAT-DL8", 21), ("FTA-VAT-ER", 14)], "supporting": [("FTA-VAT-DL8", 23)]},
    "threshold_calculation":  {"primary": [("FTA-VAT-DL8", 19)], "supporting": [("FTA-VAT-DL8", 13)]},
    "related_parties":        {"primary": [("FTA-VAT-ER", 13), ("FTA-VAT-ER", 9)], "supporting": [("FTA-VAT-DL8", 14)]},
    "zero_rated_or_exports":  {"primary": [("FTA-VAT-DL8", 15), ("FTA-VAT-ER", 16)], "supporting": [("FTA-VAT-DL8", 45)]},
    "exempt_supplies":        {"primary": [("FTA-VAT-DL8", 46)], "supporting": [("FTA-VAT-ER", 43)]},
    "non_resident":           {"primary": [("FTA-VAT-DL8", 18)], "supporting": [("FTA-VAT-DL8", 13)]},
}

# Which concepts signal which intent. Generic registration / threshold signals alone are AMBIGUOUS.
CONCEPT_TO_INTENT = {
    "deregistration": "deregistration", "voluntary": "voluntary_registration", "deadline": "mandatory_registration",
    "related": "related_parties", "tax_group": "related_parties", "exports": "zero_rated_or_exports",
    "zero_rated": "zero_rated_or_exports", "residential": "exempt_supplies", "exempt": "exempt_supplies", "land": "exempt_supplies",
    "non_resident": "non_resident", "imports": "threshold_calculation", "capital_assets": "threshold_calculation",
}
COUNT_RX = re.compile(r"\b(count|counts|counted|include|included|add|added|towards|toward|part of|go into|calculate)\b", re.I)
EXCEED_RX = re.compile(r"\b(over|above|exceed|exceeded|crossed|passed|more than|went over)\b", re.I)


def intents(question: str) -> tuple[list[str], bool]:
    """Return (intents, ambiguous). Specific concepts decide the intent; generic registration/threshold signals with
    no specific concept are ambiguous between mandatory and voluntary registration (alternatives are retrieved)."""
    found, _ = detect(question)
    out = sorted({CONCEPT_TO_INTENT[c] for c in found if c in CONCEPT_TO_INTENT})
    generic = bool(found & {"threshold", "registration"})
    if generic and COUNT_RX.search(question) and "threshold_calculation" not in out:
        out.append("threshold_calculation")
    if generic and not out:
        if EXCEED_RX.search(question):
            return ["mandatory_registration"], False
        return ["mandatory_registration", "voluntary_registration"], True
    return out, False
