# HerBiz: Compliance Agent — Source discovery report (Firecrawl, 17 Oct 2026)

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** Sat 17 Oct 2026 · **Register:** `knowledge_base/CL_source_register.json` **v1.7.0** (validates: 0 errors) · **Not legal or tax advice.**

## Three words that must not be mixed up
| Word | Meaning | How many today |
|---|---|---|
| **Discovered** | a tool saw the document or its link on an official site | 17 new in this trial (69 candidates in total) |
| **Verified** | a person opened it and confirmed what it is, its date and status | **0** of the new ones |
| **Approved** | a named, qualified UAE tax reviewer approved it for use (D3) and it is recorded in the register **and** the database | **0** sources of any kind |

Nothing discovered was downloaded, collected into the knowledge base or activated. Every new entry has `activated: false`, `kb_status: not_ingested`, `verification_status: pending_verification`, `discovery_status: discovered`.

## 1. Top priority: the current VAT Decree-Law (with the 2025 amendments)
| Item | Status |
|---|---|
| Where | https://uaelegislation.gov.ae/en/legislations/1227 (register `UAELEG-DL8-2017`) |
| What the page shows | Active · last update 01 Oct 2025 · Official Gazette 621 · 3 amendments (2022, 2024, 2025) |
| Does it include DL 16/2025? | **Yes, by observation**: Art. 48(1) "except for issuing a tax invoice to itself", new Art. 54 bis, Art. 74(3) five years, Art. 79 bis removed |
| Status | **discovered + observed.** Not collected (needs **D13**), reuse terms not cleared (**D4**), not reviewed (**D3**) |
| Effect on G3 | G3 stays **open**. Our stored DL (`FTA-VAT-DL8@v1`) is still the outdated version, and answers citing it stay blocked |
| Arabic original | https://uaelegislation.gov.ae/ar/legislations/1227 (`UAELEG-DL8-1227-AR`); the portal says the Arabic text prevails |

## 2. New FTA VAT documents found on listings (not in the register before)
All have evidence `observed_listing_only`: the link was seen on page 1 of the listing; the PDF itself was **not** opened.
| Register id | Title as listed | Scope for home businesses |
|---|---|---|
| FC-VAT-DIR-2026-05 | 2026-5 – VAT – Valuation of Deemed Supplies – 07 2026 | in scope |
| FC-VAT-DIR-2026-04 | 2026-04 – VAT – Life Insurance – 07 2026 | related |
| FC-VAT-DIR-2026-03 | 2026-03 – VAT – Converting Consideration Received in Digital Currency into AED | related |
| FC-VAT-DIR-2026-01 | 2026-01 – VAT – Judicial Expert Services | related |
| FC-CD153-2025 | Cabinet Decision No. 153 of 2025, reverse charge on metal scrap | related |
| FC-VATP047 | VATP047 – Reverse Charge Mechanism on Metal Scrap – 10 2026 | related |
| FC-VATP045 | VATP045 – Concerned Goods – Tax Invoices and Input Tax recovery | related |
| FC-VAT-EDU-GUIDE-2026 | VAT Education Guide – 29 06 2026 | related |
| FC-VAT-REFUND-NATIONALS-2026-06 / -04 | VAT refund for UAE nationals building new residences (two editions both still linked) | out of scope (listed for completeness) |

**Filtered as other taxes, not added:** a Cabinet Decision on excise prices for tobacco, and a Cabinet Decision on the corporate-tax nexus of non-resident persons.

## 3. Official-portal entries (UAE Legislation platform)
| Register id | What | Evidence |
|---|---|---|
| UAELEG-ER-1226 | VAT Executive Regulation, consolidated: Active, last update 01 Sep 2026, Gazette 624, 7 amendments; **Art. 14(1) 20 working days** | observed |
| UAELEG-TPL-1625 | Tax Procedures Decree-Law 28/2022: last update 01 Oct 2025, Gazette 737, 2 amendments (text not captured) | observed |
| UAELEG-CD153-2025-3860 | Cabinet Decision 153/2025 on the portal | listed only |
| UAELEG-1230, -1229, -2572 | related legislation of DL 8/2017, titles not yet recorded | listed only |

## 4. Gaps updated
| Gap | Change |
|---|---|
| G1 deregistration deadline | portal ER also says 20 (new claim `CL-DEREG-DEADLINE-PORTAL`); FTA page still says 30. **Still blocked**, needs the reviewer; FTA enquiry drafted, not sent |
| G3 outdated DL text | current text **located**; not collected; still open |
| G7 amendment texts | DL 16/2025 corroborated by the portal's modification history; separate texts of CD 100/2025 and CD 149/2026 still not located |
| G9 Arabic text | readable on the portal; not collected (D4, extraction method) |

## 5. How documents are discovered, and the update mechanism observed
- **FTA:** new items appear at the top of the listings, with issue and publish dates and a "New" tag. Older items move to later pages, which Firecrawl cannot reach.
- **Portal:** each law has a "last update" date, an amendment list and a modifications page. These are good, cheap signals of change.
- **Provenance recorded for every item:** the URL, the listing page, the scrape date, the tool and the evidence level. The full Firecrawl output stays in Claude's cache, with its sha256 in the saved file.

## 6. What a person must do next
1. **D13:** approve a one-time collection of the portal DL 8/2017 text (English + Arabic), once the reuse terms (D4) are clear.
2. **D3:** name the reviewer. Without one, nothing becomes "verified" or "approved".
3. **Optional, free:** open the three untitled portal entries (1230, 1229, 2572) in a browser and record their titles.
