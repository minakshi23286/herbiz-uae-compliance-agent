# HerBiz 360 — Deliverables 4 and 5: Regulatory domain and obligation inventory, and official-source coverage matrix

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** Sat 17 Oct 2026 · **By:** Claude Code, Workstream C · **Status:** draft for review · **Not legal, tax or accounting advice.**

**How to read this.** Every obligation below is a **candidate** obligation. It only applies when the business profile meets its condition. Every fact carries its evidence level:

| Evidence level | Meaning |
|---|---|
| **O** | observed: the official page was opened on 17 Oct 2026 |
| **S** | snippet: a search excerpt of an official page; the page itself was not opened |
| **L** | listed: the title was seen on an official listing; the document was not opened |
| **U** | unresolved |
| **2nd** | secondary source only; never relied on |

Nothing here is verified by a person or approved by a reviewer. The full source data is in `knowledge_base/CL_360_source_candidates.json`.

## 1. Obligation inventory (applicability-first)
| # | Domain | Obligation | Applies when (profile condition) | Key rule as found | Evidence | Status |
|---|---|---|---|---|---|---|
| 1 | VAT | Mandatory registration | taxable supplies/imports exceed the mandatory threshold (AED 375,000 in the stored DL Art. 13; 12 months back or 30 days ahead) | existing VAT knowledge base | O (FTA files, collected) | VAT module exists; **confirm the threshold against the current DL text (G3)** |
| 2 | VAT | Voluntary registration | supplies or expenses exceed the voluntary threshold | existing VAT knowledge base | O | exists |
| 3 | VAT | Returns and payment | VAT-registered | per tax period, by the 28th day after the period end (existing KB) | O | exists; return preparation not built |
| 4 | VAT | Tax invoices, credit notes, records | VAT-registered | existing KB; FTA Decision 4/2026 on accounting records is listed | O / L | partly mapped |
| 5 | VAT | Deregistration | registered and stops supplies, or below threshold | ER Art. 14(1) 20 business days vs FTA page 30 | O | **G1 blocked** |
| 6 | E-invoicing | Appoint an accredited service provider; issue structured e-invoices | VAT registrant in scope of MD 244/2025 (phased by size) | MD 243/2025, 244/2025, 64/2025; MR 66/2026 moved a deadline (title) | O (FTA page) / L | **EINV-G1**: small-business dates not verified |
| 7 | Corporate tax | Registration: juridical person | any resident company or free-zone entity | within 3 months of incorporation (incorporated on or after 1 Mar 2024; FTA Decision 3/2024) | O (FTA news) | candidate |
| 8 | Corporate tax | Registration: natural person | business in the UAE with turnover > AED 1m in a calendar year (wages, personal investment, real-estate investment excluded) | by 31 March of the following year | O | candidate |
| 9 | Corporate tax | Late-registration penalty and waiver | missed registration | AED 10,000; waiver if the first return is filed within 7 months of the first tax period end | O | candidate |
| 10 | Corporate tax | Tax return and payment | every taxable person (also SBR users: simplified return) | within 9 months of the tax period end | S (several FTA notices) | candidate; article in law not read |
| 11 | Corporate tax | Small Business Relief election | resident; revenue ≤ AED 3,000,000 in current and all previous periods; not QFZP; not large MNE | election per period; treated as no taxable income | O (FTA topic page) | CT-G1 resolved: MD 73/2023 as amended by **MD 131/2026** (O): tax periods ending on or before 31 Dec 2029 |
| 12 | Corporate tax | Annual declaration | exempt persons required to register | 9 months from financial year end | S | candidate |
| 13 | Corporate tax | Free-zone person regime | free-zone licence; QFZP conditions | TAXP010 (Oct 2026) listed; QFZP cannot use SBR | L / O | not researched in depth |
| 14 | Accounting | Keep accounting records | all taxable persons | FTA Decision 4/2026 (listed); CT and VAT record rules in law | L | **CT-G2** |
| 15 | Accounting | Audited financial statements | tax rule: revenue > AED 50m or QFZP (S, ACC-G1: MD 82/2023 for periods before 2025; MD 84/2025 for later periods, secondary only). **Separately**, a licensing or free-zone authority may require audited accounts for renewal whatever the tax rule (estimate; check per authority) | MoF PDF excerpt; MD 84/2025 only in secondary sources | S / 2nd | **ACC-G1**. Being below the tax threshold does **not** mean no audit is needed |
| 16 | Licensing | Trade licence renewal | every licensed business; authority by emirate or free zone | e.g. Dubai DET (Invest in Dubai), DDA (free zone) | S | **OBL-G1**: per-authority data needed; fees never invented |
| 17 | Ownership | Beneficial-owner register and filing | licensed legal persons (mainland; free zones via their registrar) | CD 109/2023 | S | applicability by entity type to confirm |
| 18 | Employment | Pay wages through WPS | private-sector employer under MoHRE with ≥ 1 worker | MoHRE WPS; Ministerial Resolution 340 of 2026 (title) | S | free-zone and domestic-worker rules differ |
| 19 | Employment | Labour-law obligations (contracts, end of service) | employs ≥ 1 worker | DL 33/2021 as amended | S | not researched in depth |
| 20 | Immigration | Establishment card, visas | business sponsors staff or partners | not researched this cycle | U | post-championship |
| 21 | Economic substance | ESR notification and report | historical periods only | reporting cancelled for later periods per CD 98/2024 (S); the exact cut-off (financial year starting vs ending) is **still to be checked**; duties and penalties for past years may still apply | S | mark "cancelled for later periods (to verify)", not "repealed" |
| 22 | Closure | VAT deregistration, CT deregistration, licence cancellation | business stops | VAT part G1; CT and licence not researched | U | post-championship |
| 23 | Activity permits | Activity-specific approvals (food, health, education and similar) | activity on licence needs an approval | not researched this cycle | U | applicability flag only |

**Top three applicability rules for HerBiz users** (most are natural persons or small companies). **Draft, unreviewed; evidence O/S as marked above. Not advice.**
1. **A freelancer or sole establishment (natural person)** with turnover of AED 1m or less in a calendar year has no corporate tax registration duty.
2. **Any company** (juridical person) must register for corporate tax and file returns, whatever its revenue, unless an exemption applies. Small Business Relief may reduce the tax to zero, but **not** the filing duty. The return duty rests on S-level FTA notices, and SBR availability after 2026 is unverified (CT-G1).
3. **VAT** depends only on the VAT thresholds, not on corporate tax status.

## 2. Official-source coverage matrix
| Domain | Primary law located | Implementing decisions located | FTA/authority guidance located | Text collected in KB | Monitoring baseline | Reviewer |
|---|---|---|---|---|---|---|
| VAT | yes (portal 1227; current text found, G3) | yes (ER portal 1226; FTA decisions) | yes (guides, clarifications) | yes, but outdated DL (G3) | yes (trial snapshots) | D3 pending |
| Corporate tax | yes (portal 1582, metadata) | partly (CR 75/2023, 49/2023, 116/2022; FTA Decision 3/2024; MD 73/2023 **not located**) | partly (SBR, natural person, registration card, guides listing page 1) | **no** | no | **none proposed yet** (see Deliverable 10) |
| E-invoicing | MD 243/2025 (observed in VAT work) | MD 244/2025, 64/2025, MR 66/2026 (titles) | FTA page | no | no | none |
| Accounting / financial statements | CT law articles (not read) | MD 82/2023 (excerpt), MD 84/2025 (secondary), FTA Decision 4/2026 (title) | no | no | no | none |
| Licensing | per emirate/zone; not located | — | Dubai DET and DDA renewal pages (excerpts) | no | no | none |
| Beneficial ownership | CD 109/2023 (excerpt) | — | — | no | no | none |
| Employment / WPS | DL 33/2021 (excerpt) | MR 340/2026 (title) | MoHRE WPS (excerpt; scrape blocked) | no | no | none |
| Economic substance | CD 57/2020 as amended by CD 98/2024 (excerpt) | — | MoF news | no | not needed (historical) | none |
| Immigration, permits, closure | not located | — | — | no | no | none |

**Reuse note (D4/G5):** any full-text collection or monitoring snapshot is a copy. Until the reuse terms are cleared, copies stay private and internal (hashes and diffs only); users see links and short citations; nothing is redistributed. The existing VAT knowledge base already holds FTA text under G5.

**Conclusion:** VAT is the only domain with collected official text, a version register, monitoring and a validity layer. Corporate tax has located primary sources but **no collected text**, so the agent cannot cite corporate-tax articles yet. Every other domain is at the discovery stage.
