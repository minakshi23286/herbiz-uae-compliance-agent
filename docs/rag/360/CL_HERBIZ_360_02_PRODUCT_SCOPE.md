# HerBiz 360 — Deliverable 3: 360-degree product scope

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** Sat 17 Oct 2026 · **Status:** draft scope for founder decision · **Not legal, tax or accounting advice.**

**Purpose:** HerBiz helps UAE microbusinesses, home-based entrepreneurs, freelancers and solo consultants *after* setup. It helps them:
- see which obligations apply to them;
- prepare documents and records;
- keep track of deadlines;
- know when to get a professional.

It never files, pays or certifies on anyone's behalf.

**User evidence: none yet.** The persona is provisional and no owner interviews have been held. Bookkeeping and financial readiness are a founder-supplied hypothesis.

## 1. Business profile (requirements model)
"Today" is what the code holds now (from the audit). Each fact drives rules: no rule may assume a fact that the profile does not hold.

| Fact | Values (examples) | Drives | Today |
|---|---|---|---|
| Emirate | AUH, DXB, SHJ, AJM, UAQ, RAK, FUJ | licensing authority, emirate rules | yes |
| Jurisdiction type | mainland · free zone (name) · designated zone · other | licence renewal authority, CT free-zone regime, VAT designated-zone rules, WPS/UBO route | **no** |
| Licensing authority | e.g. Dubai DET, DDA, a free-zone authority, a home-business permit issuer | renewal workflow, documents | free label only |
| Legal entity type | sole establishment · LLC · free-zone company (FZE/FZ-LLC) · civil company · branch · freelance permit | CT person type, UBO, audit rule | **no** |
| Legal personality | natural person · juridical person (derived from the entity type, confirmed by the owner) | CT registration test (AED 1m vs always) | **no** |
| Business activities | licence activities, plus tags (food, online sales, consulting) | permits, VAT supplies, CT exemptions | tags only |
| Licence issue and expiry dates | dates | renewal deadline; CT registration deadline (FTA Decision 3/2024 used licence months for older entities) | yes (copied, not computed) |
| Financial year and tax period | FY end month; VAT tax period (monthly or quarterly, as set by the FTA) | CT return deadline (9 months), VAT return dates | **no** |
| Revenue | calendar-year turnover (natural-person test), tax-period revenue history (SBR test), 12-month taxable supplies (VAT) | CT and VAT tests | VAT ledger only |
| Employees | count; MoHRE or free-zone sponsored; domestic workers separate | WPS, labour law, visas | stored, unused |
| VAT status | not registered · registered (TRN, tax period) · deregistering | VAT returns, e-invoicing | yes |
| CT status | not registered · registered (TRN) · exempt person · SBR elected per period | CT returns | **no** |
| Special circumstances | Qualifying Free Zone Person claim, related-party transactions, group membership, real-estate income | SBR exclusion, audit rule, professional escalation | **no** |
| Regulatory permissions | activity approvals, e.g. food or health | permits module | partial (tags) |

## 2. Domain scope
| Domain | In the 360 scope | Never in scope |
|---|---|---|
| VAT | registration, deregistration (G1 blocked), returns guidance, invoices and credit notes, input/output tax, exempt and zero-rated, records, amendments | computing or submitting a VAT return; issuing any approval of a tax position |
| Corporate tax | registration test and deadline, natural vs juridical person, SBR eligibility test and election reminder, return deadline, records, free-zone flag, penalties overview, when to get help | computing taxable income adjustments; filing; transfer-pricing opinions |
| Bookkeeping and financial readiness | see §3 | audit, assurance, signing accounts |
| Other obligations | licence renewal, UBO, WPS, labour basics, e-invoicing readiness, record retention, closure checklists, permits (as applicability flags), ESR (historical only) | immigration processing, legal advice on contracts |
| Help and cost | when the owner can do it, when software helps, when a professional is advisable or required | quoting fees or prices; recommending specific firms |

## 3. Bookkeeping and financial readiness: safe workflows
**Status:** a **new scope addition** and a **hypothesis**. No user evidence yet (no interviews held). Board decision (17 Oct): only the first three rows below go into the championship MVP. The rest waits until after the event.

**Hard rule (legal review):** no real bank statements, transactions or payroll data until a privacy review is done. The review must cover:
- the PDPL (Federal Decree-Law 45/2021), and DIFC/ADGM rules where they apply;
- the data map, lawful basis, retention, and deletion versus the append-only audit trail;
- hosting and processors.

No user data goes to Firecrawl, and none goes to an LLM without D5e.

| Workflow | What HerBiz does | Output label (ladder level) | MVP? |
|---|---|---|---|
| Revenue tests | computes **three separate bases** from one transaction list (see below) and flags a test result | A1 management estimate | **yes** |
| Missing-document list | checklist of documents per transaction; marks what is missing | A2 bookkeeping report | **yes** |
| Accountant-ready export | CSV with records, categories, missing items, open questions, and the `label_level` of every figure | A2 bookkeeping report | **yes** |
| Income and expense recording | owner enters or imports; HerBiz never invents an amount | A2 bookkeeping record | later |
| Categorisation | suggests a category from a fixed chart; the owner confirms; unknown items are asked about, not guessed | A2 | later |
| Bank reconciliation | matches records to an owner-uploaded statement; lists unmatched items | A2 bookkeeping report | later (privacy review first) |
| Chart of accounts | small starter chart; the accountant may change it | template | later |
| Profit and loss | totals from confirmed records; every report states **cash or accrual basis** | A2 bookkeeping report | later |
| Balance sheet | **only** with opening balances and owner equity supplied by the owner or accountant; otherwise not produced | A2 bookkeeping report | later |
| Cash-flow history and forecast | history from records; the forecast uses the owner's assumptions | A1 management estimate | later |
| CT computation preparation | pack of totals and questions for the preparer | A2 (it is **not** a tax computation, level T1) | later |
| VAT reconciliation | compares records with what the owner says was declared | A2 | later |
| Year-end checklist | records, reconciliation, documents, deadlines | checklist | later |

**Revenue tests use three different bases.** They are never interchangeable.

| Test | Basis | Notes |
|---|---|---|
| VAT registration | taxable supplies; exempt and out-of-scope supplies excluded | rolling 12 months, plus a 30-day forward test that needs the **owner's estimate**, not transactions |
| CT natural person (AED 1m) | business turnover in the **calendar year** | wages, personal investment income and real-estate investment income excluded (FTA, O) |
| Small Business Relief (AED 3m) | revenue of **every** tax period so far | the current period and all previous ones count |

**Safety rules for the tests:**
- **Unclassified items:** counted as included, never left out silently.
- **Near-threshold results:** within a band near the threshold, the answer is "need more information / get help".
- **Foreign currency:** converted at a documented rate.
- **Open gaps:** each result carries the gaps that apply (G3 for the AED 375,000 figure from the outdated stored text; SBR now runs to tax periods ending 31 Dec 2029 per MD 131/2026; CT-G1 resolved).
- **Why caution wins:** a wrong "does not apply" can cost the owner the AED 10,000 CT late-registration penalty (FTA, O), so the tests lean towards caution.

**Label ladder.** There are two tracks. HerBiz **never upgrades** a label. A figure can never carry a higher level than its inputs allow, and every stored figure has a `label_level` field.

| Track | Level | Meaning | Produced by HerBiz? |
|---|---|---|---|
| Accounts | A1 | management estimate | yes |
| Accounts | A2 | bookkeeping record or report | yes |
| Accounts | A3 | draft financial statements (owner or accountant) | no |
| Accounts | A4 | final financial statements (approved by owner or management) | no |
| Accounts | A5 | audited financial statements, **only where required**, by a licensed auditor | no |
| Tax | T1 | tax computation (by the preparer or an FTA-registered tax agent) | no |
| Tax | T2 | submitted tax return (on EmaraTax, by an authorised person) | no; HerBiz only records the owner's statement that it was submitted |

For natural persons, the tax track does not depend on financial statements. HerBiz never calls anything "audited", "certified" or "final".

## 4. Help and cost: who does what
These are categories, not legal advice. **Every "owner can usually" answer is an estimate and has not been reviewed.** Fees are never stated: none were collected, and none may be invented.

| Task | Owner can usually do it directly (estimate) | Software helps the owner | Accountant or FTA-registered tax-agent review is advisable | A licensed or qualified professional is required |
|---|---|---|---|---|
| CT registration on EmaraTax | yes: free service, "25 Minutes" estimated time (FTA service card, O, 17 Oct 2026) | document checklist | several licences, partnerships, free zone | — |
| CT return with SBR | often, for simple cases | revenue test, records pack | **first CT return**; doubt about eligibility (SBR period: to 31 Dec 2029 per MD 131/2026) | — |
| CT return with taxable income | possible, but complex | preparation pack | **yes** | depends on the case; never assumed |
| Qualifying Free Zone Person claim | no | — | **yes** | case-dependent |
| Related-party or transfer-pricing positions | no | flag only | **yes** | case-dependent |
| VAT registration and returns | yes, through EmaraTax | records and reconciliation | errors; **voluntary disclosure** | — |
| Draft or final financial statements | no | export pack | **yes: accountant** | — |
| Audited financial statements | no | export pack | — | **licensed auditor**, where the tax rule applies (revenue > AED 50m or QFZP: S, ACC-G1) **or** an authority requires it for licence renewal (check per authority) |
| Licence renewal | yes, through the authority portal (estimate) | reminder, document list | — | — |
| UBO filing | usually (estimate) | data checklist | complex ownership | — |
| WPS payroll | — | payroll checklist | — | pay through a **MoHRE-approved WPS agent or bank** (S); this is a payment channel, not a professional adviser |

## 5. Agent experience (applicability first)
```
Business profile → Applicable obligations → Deadline calendar → Required documents → Guided preparation
→ Calculations and validation → Draft outputs → Owner review → Professional review where needed
→ Official submission by an authorised person (outside HerBiz) → Evidence and audit trail → Ongoing monitoring
```
| Step | What the user sees | Safeguard |
|---|---|---|
| Profile | 10 to 14 plain questions; unknown is allowed | unknown facts give "needs clarification", never a guess |
| Obligations | a list with "applies / does not apply / need more information", each with its reason and an official source | every line has a citation and its review status |
| Calendar | dated tasks | each date shows the rule it came from; "estimated" when a fact is missing |
| Documents | a checklist per task | — |
| Preparation and calculations | worksheets; threshold tests | every number is labelled with its level (§3) |
| Draft outputs | checklists, packs, letters | marked DRAFT |
| Owner review | the owner confirms | owner confirmation recorded |
| Professional review | "get help" box with the reason | no reviewer name shown without a documented approval |
| Submission | a link to the official portal and the steps | **HerBiz never submits or pays** |
| Evidence | upload or record proof of submission | append-only trail |
| Monitoring | "this changed; these tasks are affected" | report-only until a person reviews |
