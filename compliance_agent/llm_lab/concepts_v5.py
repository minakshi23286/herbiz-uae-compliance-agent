"""Retrieval v5 (Workstream B, 16 Oct 2026). Copy of concepts.py (v4) extended into a law-wide index; concepts.py stays
unchanged because the Workstream A demo guard (ask.py) reads its v4 provision map.

Plain-English -> legal-term concept index for UAE VAT (Decree-Law No. 8 of 2017 and its Executive Regulation).

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
    "voluntary":      {"triggers": ["voluntar", "optional", "choose to", "allowed to register", "can i register", "register anyway", "even though", "want to register",
                                    "even without", "without income", "without any income", "no income", "no sales", "no revenue", "not earning", "before i start",
                                    "haven't started", "have not started", "not started selling", "only expenses", "my expenses", "spent"],
                       "law_terms": ["voluntary", "registration"]},
    "deregistration": {"triggers": ["cancel", "deregist", "de-regist", "unregist", "un-regist", "close my vat", "stop being registered", "remove my registration", "give up my trn",
                                    "no longer need", "closing the business", "closing my business", "closing down", "close down", "close the business", "close my business",
                                    "shut down", "shutting down", "winding up", "wind up", "stop trading", "stopped trading", "stop the business",
                                    "relocat", "moving abroad", "moving back", "leaving the uae", "leaving uae", "leave the uae", "move out of the uae"],
                       "law_terms": ["deregistration", "cases", "voluntary", "application"]},
    "deadline":       {"triggers": ["deadline", "how long", "how many days", "late", "when do i", "when should", "by when", "time limit", "backdate", "back date"],
                       "law_terms": ["mandatory", "registration", "application", "date"]},
    "related":        {"triggers": ["sister", "brother", "husband", "wife", "family member", "family business", "my family's", "relative", "partner", "my mother", "my father", "cousin", "uncle", "aunt",
                                    "my son", "my daughter", "in-law", "another company", "related", "friend's shop", "friends shop", "my friend's"],
                       "law_terms": ["related", "parties", "aggregation"]},
    "split_business": {"triggers": ["split", "divide", "two businesses", "both businesses", "separate businesses", "combine", "trade names", "two names", "different names",
                                    "two licences", "two licenses", "second licence", "second license", "separate licence", "separate license", "another licence"],
                       "law_terms": ["related", "parties", "aggregation", "calculating"]},
    "tax_group":      {"triggers": ["tax group", "group registration", "register together", "joint registration", "one registration for"],
                       "law_terms": ["group", "registration"]},
    "imports":        {"triggers": ["import", "bring in", "buy from abroad", "from china", "from turkey", "from india", "shipping in", "customs"],
                       "law_terms": ["import", "concerned", "calculating", "threshold"]},
    "exports":        {"triggers": ["export", "abroad", "overseas", "outside the uae", "outside uae", "foreign customers", "international customers", "ship to",
                                    "customers in oman", "customers in saudi", "to oman", "to saudi", "to the uk", "to europe", "gcc countr", "other countries"],
                       "law_terms": ["zero", "rate", "export"]},
    "zero_rated":     {"triggers": ["zero rate", "zero-rate", "zero rated", "0%", "zero percent"],
                       "law_terms": ["zero", "rate"]},
    "exempt":         {"triggers": ["exempt", "no vat on", "vat free", "vat-free"],
                       "law_terms": ["exempt", "exemption"]},
    "reg_exception":  {"triggers": ["exempt from registration", "exemption from registration", "exception from registration", "excepted from registration",
                                    "only zero-rated", "only zero rated", "all my sales are zero"],
                       "law_terms": ["exception", "registration"]},
    # a dwelling is only a residential-supply signal when it is rented or sold, not when it is where the owner works
    "residential":    {"triggers": ["rent out", "renting out", "rent my", "tenant", "landlord", "lease my", "leasing", "rental income", "residential building",
                                    "residential property", "sell my flat", "sell my apartment", "sell my villa"],
                       "law_terms": ["residential", "buildings", "exemption"]},
    "land":           {"triggers": ["bare land", "empty land", "vacant land", "plot of land", "a plot", "my land"], "law_terms": ["bare", "land", "exemption"]},
    "passenger":      {"triggers": ["taxi", "passenger", "school run", "drive people", "driving people", "ferry people", "car pool", "carpool", "transport people"],
                       "law_terms": ["local", "passenger", "transport", "exemption"]},
    "financial":      {"triggers": ["loan", "interest", "insurance", "bank fee", "lending", "money transfer", "remittance"],
                       "law_terms": ["financial", "services"]},
    "capital_assets": {"triggers": ["oven", "mixer", "machine", "equipment", "laptop", "camera", "car", "van", "furniture", "printer", "sell my old", "used equipment", "asset"],
                       "law_terms": ["capital", "assets"]},
    "non_resident":   {"triggers": ["not based", "foreign company", "non resident", "non-resident", "not a uae resident", "not resident", "outside the country",
                                    "abroad company", "live outside", "i live in muscat", "i live in oman", "i live in saudi", "based in oman", "based in saudi", "based in the uk"],
                       "law_terms": ["non", "resident", "registration"]},
    "education":      {"triggers": ["tutor", "tuition", "teaching", "teach ", "course", "classes", "education", "nursery"],   # not "school": a school is often the customer
                       "law_terms": ["education", "zero"]},
    "healthcare":     {"triggers": ["clinic", "health", "medical", "therapy", "physio", "nurse", "doctor"], "law_terms": ["healthcare", "zero"]},
    "free_zone":      {"triggers": ["free zone", "freezone", "designated zone", "jafza", "jebel ali free", "kizad", "saif zone", "hamriyah free"], "law_terms": ["designated", "zone"]},
    "second_hand":    {"triggers": ["second hand", "second-hand", "used goods", "pre-loved", "preloved", "resell used", "thrift", "vintage", "used clothes", "used phones",
                                    "profit margin", "margin scheme"],
                       "law_terms": ["profit", "margin"]},
    "invoices":       {"triggers": ["invoice", "receipt", "bill"], "law_terms": ["tax", "invoice"]},
    "credit_note":    {"triggers": ["credit note", "refund", "return the goods", "returned the goods", "cancelled order", "canceled order", "money back"],
                       "law_terms": ["credit", "note"]},
    "returns":        {"triggers": ["vat return", "file vat", "filing", "file my vat", "submit my vat", "quarterly", "tax period", "every quarter", "monthly return"],
                       "law_terms": ["tax", "return", "period"]},
    "payment":        {"triggers": ["pay the vat", "pay vat", "payment of vat", "pay my vat", "settle", "owe the fta", "vat i owe", "vat payable", "pay the fta"],
                       "law_terms": ["settlement", "payment"]},
    "records":        {"triggers": ["record", "keep documents", "bookkeeping", "books", "how long do i keep", "keep receipts", "keep invoices", "archive", "five years", "5 years"],
                       "law_terms": ["record", "keeping"]},
    "evasion":        {"triggers": ["hide", "cash sales", "not declare", "don't declare", "avoid vat", "evade", "under the table", "under the radar", "without anyone noticing",
                                    "not record", "don't record", "dont record"],
                       "law_terms": ["evasion", "penalties"]},
    "penalties":      {"triggers": ["the fine", "a fine", "fines", "fined", "fine for", "fine if", "fine of", "penalty", "penalties", "punish"], "law_terms": ["administrative", "penalties"]},
    "gifts_samples":  {"triggers": ["free sample", "gift", "giveaway", "for free", "give away", "personal use", "my own use", "use at home", "for my family"],
                       "law_terms": ["deemed", "supply"]},
    "agent":          {"triggers": ["agent", "on behalf", "commission", "marketplace", "noon", "amazon", "talabat", "deliveroo", "careem", "etsy", "pass it to", "pass it on",
                                    "passed on to", "reimburs", "recharge", "disbursement", "collect for", "pay the courier"],
                       "law_terms": ["agent", "supply"]},
    "value":          {"triggers": ["discount", "on top", "delivery charge", "delivery fee", "shipping fee", "price i charge", "what price", "market value", "below cost",
                                    "at cost", "voucher", "coupon", "gift card", "bundle", "package price", "inclusive of vat", "including vat", "vat included", "vat inclusive"],
                       "law_terms": ["value", "supply"]},
    "place_supply":   {"triggers": ["place of supply", "where is the supply", "which country's vat", "customer is in", "client is in", "clients abroad", "client abroad",
                                    "online service", "digital product", "e-book", "ebook", "download", "online course", "app subscription", "electronic service"],
                       "law_terms": ["place", "supply"]},
    "date_supply":    {"triggers": ["date of supply", "deposit", "advance payment", "paid in advance", "paid upfront", "upfront", "pre-order", "preorder", "when do i charge",
                                    "which month", "tax point"],
                       "law_terms": ["date", "supply"]},
    "input_tax":      {"triggers": ["input tax", "input vat", "claim back", "claim the vat", "reclaim", "recover the vat", "vat on my purchases", "vat i paid", "vat on expenses"],
                       "law_terms": ["input", "tax", "recoverable"]},
    "bad_debt":       {"triggers": ["never paid", "didn't pay", "did not pay", "unpaid invoice", "bad debt", "won't pay", "customer disappeared"], "law_terms": ["bad", "debts"]},
    "tourist":        {"triggers": ["tourist", "visitor refund", "planet tax", "tax free shopping", "tax-free shopping"], "law_terms": ["tourist", "visitors"]},
    "new_home":       {"triggers": ["build my house", "building my home", "new home", "new residence", "construct my house"], "law_terms": ["new", "residence"]},
    "vat_rate":       {"triggers": ["what rate", "how much vat", "5%", "percent vat", "vat rate", "rate of vat"], "law_terms": ["tax", "rate"]},
}

# Other tax or legal regimes: a question about these is not a VAT-law question, so no provisions are added for it.
OTHER_REGIME_RX = re.compile(r"\b(corporate tax|corporation tax|excise|zakat|income tax|saudi (?:vat )?rules|under saudi|trade licen[cs]e|visa|municipality|"
                             r"pdpl|data protection)\b", re.I)

# Concepts for which the base registration rule (ER Art. 7 + FTA registration page) is always given to the model.
REGISTRATION_CORE = {"threshold", "registration", "voluntary", "deregistration", "deadline", "related", "imports", "exports", "capital_assets", "non_resident"}

MONEY_RX = re.compile(r"(?:aed|dhs?|dirhams?)\s*\d[\d,\.]*\s*k?|\d[\d,\.]*\s*(?:k|aed|dhs?|dirhams?|lakhs?|lacs?|million|mn)\b"
                      r"|\b\d[\d,\.]*\s*(?:a|per|each|every)\s*(?:month|year|week)\b|\b\d[\d,\.]*\s*(?:monthly|yearly|annually)\b"
                      r"|\b(?:one|two|three|four|five|six|seven|eight|nine|ten)\s+lakhs?\b", re.I)


INCOME_RX = re.compile(r"\b(make|makes|made|making|earn\w*|sales?|sell\w*|sold|turnover|revenue|income|takings|bring(?:s)? in|brought in|"
                       r"orders?|total|last year|this year|12 months|twelve months|a year|per year|annual\w*|business does|business did)\b", re.I)


def detect(question: str) -> tuple[set[str], list[str]]:
    """Concepts triggered by the question, and the law words they contribute. Money amounts imply 'threshold'."""
    low = " " + re.sub(r"\s+", " ", question.lower()) + " "
    found: set[str] = set()
    for name, c in CONCEPTS.items():
        for t in c["triggers"]:
            if re.search(r"(?<![a-z])" + re.escape(t), low):
                found.add(name)
                break
    if MONEY_RX.search(question) and INCOME_RX.search(question):   # v5: an amount is turnover only when it is the owner's income
        found.add("threshold")
    words = [w for n in sorted(found) for w in CONCEPTS[n]["law_terms"]]
    return found, words


# Intent -> primary provisions (the articles a correct answer must rest on) and supporting guidance.
# Built from the law's own structure (its chapters and article titles) as a back-of-book index of the whole Decree-Law
# and Executive Regulation, not from test questions. ("FTA-VAT-REG-PAGE", None) = the FTA registration web page.
# Retrieval v5 (Workstream B): v4 covered only registration topics; it also pointed exports at ER Art. 16
# (Exception from Registration) instead of ER Art. 30/31 (zero-rating exports) and lacked DL Art. 22 (deregistration).
DL, ER, PAGE = "FTA-VAT-DL8", "FTA-VAT-ER", "FTA-VAT-REG-PAGE"
INTENT_PROVISIONS: dict[str, dict] = {
    # registration chapter
    "mandatory_registration": {"primary": [(DL, 13), (ER, 7)], "supporting": [(PAGE, None)]},
    "voluntary_registration": {"primary": [(DL, 17), (ER, 8)], "supporting": [(PAGE, None)]},
    "deregistration":         {"primary": [(DL, 21), (DL, 22), (ER, 14)], "supporting": [(DL, 23), (ER, 18)]},
    "threshold_calculation":  {"primary": [(DL, 19), (DL, 13)], "supporting": [(ER, 7)]},
    "related_parties":        {"primary": [(ER, 13), (ER, 9)], "supporting": [(DL, 14)]},
    "tax_group":              {"primary": [(DL, 14), (ER, 10)], "supporting": [(ER, 12)]},
    "non_resident":           {"primary": [(DL, 18)], "supporting": [(DL, 13)]},
    "registration_exception": {"primary": [(DL, 15), (ER, 16)], "supporting": [(DL, 13)]},
    "capital_assets_threshold": {"primary": [(DL, 19), (DL, 20)], "supporting": [(ER, 57)]},
    # zero rate and exemptions
    "zero_rated_or_exports":  {"primary": [(DL, 45), (ER, 30), (ER, 31)], "supporting": [(DL, 44)]},
    "zero_rated":             {"primary": [(DL, 45)], "supporting": [(DL, 44)]},
    "education":              {"primary": [(DL, 45), (ER, 40)], "supporting": []},
    "healthcare":             {"primary": [(DL, 45), (ER, 41)], "supporting": []},
    "exempt_supplies":        {"primary": [(DL, 46)], "supporting": [(ER, 43)]},
    "exempt_residential":     {"primary": [(DL, 46), (ER, 43)], "supporting": [(ER, 37)]},
    "exempt_land":            {"primary": [(DL, 46), (ER, 44)], "supporting": []},
    "exempt_passenger":       {"primary": [(DL, 46), (ER, 45)], "supporting": []},
    "financial_services":     {"primary": [(DL, 46), (ER, 42)], "supporting": []},
    # supply rules and value
    "deemed_supply":          {"primary": [(DL, 11), (DL, 12)], "supporting": [(ER, 5)]},
    "agent":                  {"primary": [(DL, 9), (DL, 33)], "supporting": [(DL, 34)]},
    "value_of_supply":        {"primary": [(DL, 34)], "supporting": [(ER, 25)]},
    "discount":               {"primary": [(DL, 39), (ER, 28)], "supporting": [(DL, 34)]},
    "related_value":          {"primary": [(DL, 36), (ER, 9)], "supporting": [(ER, 25)]},
    "tax_inclusive":          {"primary": [(DL, 38), (ER, 27)], "supporting": []},
    "profit_margin":          {"primary": [(DL, 43), (ER, 29)], "supporting": []},
    "place_of_supply":        {"primary": [(DL, 29), (DL, 27)], "supporting": [(DL, 30)]},
    "electronic_services":    {"primary": [(DL, 31), (ER, 23)], "supporting": [(DL, 29)]},
    "date_of_supply":         {"primary": [(DL, 25), (ER, 19)], "supporting": [(DL, 26)]},
    "imports":                {"primary": [(DL, 48), (ER, 47)], "supporting": [(DL, 35)]},
    "designated_zone":        {"primary": [(DL, 50), (ER, 51)], "supporting": [(DL, 51)]},
    "capital_assets_scheme":  {"primary": [(DL, 60), (ER, 57)], "supporting": [(ER, 58)]},
    # input tax
    "input_tax":              {"primary": [(DL, 54), (DL, 55)], "supporting": [(ER, 53)]},
    "bad_debt":               {"primary": [(DL, 64)], "supporting": [(DL, 61)]},
    # compliance obligations
    "tax_invoice":            {"primary": [(DL, 65), (ER, 59)], "supporting": [(DL, 67)]},
    "credit_note":            {"primary": [(DL, 63), (ER, 60)], "supporting": [(DL, 61)]},
    "tax_return":             {"primary": [(DL, 72), (ER, 64)], "supporting": [(DL, 71), (ER, 62)]},
    "payment":                {"primary": [(DL, 73), (ER, 64)], "supporting": []},
    "records":                {"primary": [(DL, 78), (ER, 71)], "supporting": [(ER, 72)]},
    "penalties":              {"primary": [(DL, 76)], "supporting": [(DL, 77)]},
    "evasion":                {"primary": [(DL, 77)], "supporting": [(DL, 76)]},
    "vat_rate":               {"primary": [(DL, 3)], "supporting": [(DL, 2)]},
    "tourist":                {"primary": [(ER, 68)], "supporting": []},
    "new_residence":          {"primary": [(ER, 66)], "supporting": []},
}

# Which concepts signal which intent. Generic registration / threshold signals alone are AMBIGUOUS.
CONCEPT_TO_INTENT = {
    "deregistration": "deregistration", "voluntary": "voluntary_registration",
    "related": "related_parties", "split_business": "related_parties", "tax_group": "tax_group",
    "exports": "zero_rated_or_exports", "zero_rated": "zero_rated", "education": "education", "healthcare": "healthcare",
    "exempt": "exempt_supplies", "residential": "exempt_residential", "land": "exempt_land", "passenger": "exempt_passenger",
    "financial": "financial_services", "non_resident": "non_resident", "reg_exception": "registration_exception",
    "gifts_samples": "deemed_supply", "agent": "agent", "value": "value_of_supply", "second_hand": "profit_margin",
    "place_supply": "place_of_supply", "date_supply": "date_of_supply", "free_zone": "designated_zone",
    "input_tax": "input_tax", "bad_debt": "bad_debt", "invoices": "tax_invoice", "credit_note": "credit_note",
    "returns": "tax_return", "payment": "payment", "records": "records", "penalties": "penalties", "evasion": "evasion",
    "vat_rate": "vat_rate", "tourist": "tourist", "new_home": "new_residence",
}
REGISTRATION_FAMILY = {"mandatory_registration", "voluntary_registration", "deregistration", "threshold_calculation",
                       "related_parties", "tax_group", "non_resident", "registration_exception", "capital_assets_threshold"}
COUNT_RX = re.compile(r"\b(count|counts|counted|include|included|add|added|towards|toward|part of|go into|calculate|calculating|"
                      r"subtract\w*|deduct\w*|minus|exclud\w*|leave out|left out|work(?:ing)? out)\b", re.I)
EXCEED_RX = re.compile(r"\b(over|above|exceed|exceeded|crossed|passed|more than|went over)\b", re.I)
DECLINE_RX = re.compile(r"\b(dropp?ed|fell|fallen|falling|decreas\w*|declin\w*|went down|gone down|reduced|shrunk|slow(?:ed)? down|lower now|less now)\b", re.I)
HEDGE_RX = re.compile(r"\b(not sure|don'?t know|do not know|unsure|confused|no idea)\b", re.I)
DISCOUNT_RX = re.compile(r"\b(discount\w*|cheaper|below (?:market|cost)|at cost|lower price|special price|for free|free of charge)\b", re.I)
SERVICE_RX = re.compile(r"\b(online|digital|download|e-?book|app|subscription|streaming|software)\b", re.I)
REGISTRATION_ALTERNATIVES = ["mandatory_registration", "voluntary_registration", "deregistration"]


def intents(question: str) -> tuple[list[str], bool]:
    """Return (intents, ambiguous). Specific concepts decide the intent; generic registration/threshold signals with
    no specific concept are ambiguous between registration alternatives (all alternatives are retrieved).

    Retrieval v5 rules (general, from the law's structure): a falling turnover or an owner who says they do not know
    whether to register or cancel gets every registration alternative, including deregistration; a value question
    about a relative's business gets the related-party value rule; a stated turnover amount on an open registration
    question also gets the calculation article; questions about other tax regimes get nothing."""
    if OTHER_REGIME_RX.search(question) and not re.search(r"\bvat\b", question, re.I):
        return [], False
    found, _ = detect(question)
    money = bool(MONEY_RX.search(question))
    out: list[str] = []
    for c in sorted(found):
        it = CONCEPT_TO_INTENT.get(c)
        if it and it not in out:
            out.append(it)
    generic = bool(found & {"threshold", "registration"}) or (money and bool(found & {"deadline"}))
    if "split_business" in found and "threshold_calculation" not in out:
        out.append("threshold_calculation")       # aggregation is a question about what counts toward the threshold
    if "related" in found and (DISCOUNT_RX.search(question) or "value" in found):
        out.append("related_value")
    if "value" in found and DISCOUNT_RX.search(question) and "related_value" not in out:
        out.append("discount")
    if "place_of_supply" in out and SERVICE_RX.search(question):
        out.append("electronic_services")
    if "imports" in found:
        out.append("threshold_calculation" if (generic or COUNT_RX.search(question)) else "imports")
    if "capital_assets" in found:
        out.append("capital_assets_threshold" if generic else "capital_assets_scheme")
    if "value" in found and DISCOUNT_RX.search(question) is None and "inclusive" in question.lower():
        out.append("tax_inclusive")
    if generic and COUNT_RX.search(question) and "threshold_calculation" not in out:
        out.append("threshold_calculation")
    reg_specific = [i for i in out if i in REGISTRATION_FAMILY]
    if (generic or reg_specific) and (HEDGE_RX.search(question) or (DECLINE_RX.search(question) and not reg_specific)):
        alts = (["deregistration", "voluntary_registration", "mandatory_registration"] if DECLINE_RX.search(question)
                else REGISTRATION_ALTERNATIVES)
        rest = [i for i in out if i not in REGISTRATION_ALTERNATIVES]
        return list(dict.fromkeys(alts + rest)), True
    if "deadline" in found and not reg_specific and generic:
        out.append("mandatory_registration")
    if generic and not out:
        if EXCEED_RX.search(question):
            return ["mandatory_registration"], False
        alts = ["mandatory_registration", "voluntary_registration"] + (["threshold_calculation"] if money else [])
        return alts, True
    return list(dict.fromkeys(out)), False


# Intents whose questions also rest on the base registration rule (DL Art. 13 / ER Art. 7) when the owner asks about
# registering or the threshold: whether an exempt, export or related-party supply changes the registration answer.
BASE_RULE_WITH = {"threshold_calculation", "related_parties", "registration_exception", "capital_assets_threshold",
                  "exempt_supplies", "exempt_residential", "exempt_land", "exempt_passenger", "financial_services",
                  "zero_rated_or_exports", "zero_rated", "education", "healthcare", "evasion", "tax_invoice"}


def needs_base_rule(question: str, its: list[str], ambiguous: bool) -> bool:
    """True when the base registration rule should accompany the specific intents (registration context present,
    no registration alternative already chosen, and no deregistration / voluntary / non-resident intent)."""
    if ambiguous or not its:
        return False
    found, _ = detect(question)
    context = bool(found & {"threshold", "registration", "reg_exception"})
    blocked = {"mandatory_registration", "voluntary_registration", "deregistration", "non_resident"}
    return context and not (set(its) & blocked) and bool(set(its) & BASE_RULE_WITH)


def turnover_stated(question: str) -> bool:
    """The owner quotes their own sales or income as an amount (so the calculation article is needed to check it)."""
    return bool(MONEY_RX.search(question) and INCOME_RX.search(question))
