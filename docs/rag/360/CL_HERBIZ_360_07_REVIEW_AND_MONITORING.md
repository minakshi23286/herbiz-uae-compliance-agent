# HerBiz 360 — Deliverables 10 and 11: Review and approval register; monitoring and source-update operating model

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** Sat 17 Oct 2026 · **Not legal, tax or accounting advice.**

## 1. Review and approval register
**Rule:** no reviewer is represented as having approved anything until a documented approval exists. It must record the name, qualification, date, the exact versions reviewed and the decision.

| Id | Role | Scope | Status | Approvals recorded |
|---|---|---|---|---|
| **D3** (kept) | Qualified UAE VAT reviewer | VAT provision map, flagged labels, source versions, G1 opinion, amendment procedure | pending reviewer identification (task CA-T08; doc `CL_HERBIZ_D3_TAX_REVIEWER.md` on ws-b-retrieval) | **none** |
| **D3-CT** (proposed) | Qualified UAE corporate tax reviewer (may be the same person if qualified) | CT applicability rules (natural/juridical, SBR, free zone), CT deadlines, CT provision map, CT sources | proposed | none |
| **D3-ACC** (proposed) | Accountant (a qualified accounting professional) | chart of accounts, categorisation rules, label ladder, draft-report templates, accountant export, year-end checklist | proposed | none |
| **D3-JUR** (proposed) | Jurisdiction specialist(s) | licensing per emirate and free zone, UBO, WPS and labour basics, e-invoicing readiness | proposed; one per area as needed | none |
| D4 | Reuse-terms decision (founder, with a UAE-qualified lawyer or written publisher consent) | storing official texts (FTA, portal, MoF, MoHRE) | pending | none |

**For each review, record:**
- the reviewer's identity and qualification evidence;
- the engagement terms (agreed by the founder; fees need your approval);
- the reviewed items and versions (commit hash, register version);
- one decision per item: approve, correct or unresolved;
- citations for every correction.

A review approves only what it covers, and only those exact versions. A later version needs a new decision.

**Before engagement, also record:** an independence and conflict-of-interest check, and professional-indemnity cover.

## 2. Monitoring and source-update operating model (extends `CL_HERBIZ_SOURCE_OPERATING_MODEL.md`)
| Tier | Sources | Purpose | Credits per month (est.) |
|---|---|---|---|
| **Daily** (working days) | FTA legislation listing (all taxes), FTA VAT guides listing, FTA CT guides listing | new decisions, guides, clarifications | 66 |
| **Weekly** | portal DL 8/2017 and ER (VAT); portal CT law 1582 and its modifications page; FTA CT registration card; SBR and natural-person topic pages; FTA e-invoicing page; G1 page | changed provisions, effective dates | ≈ 39 (9 pages × 4.3) |
| **Monthly** | MoF financial-legislation listing; MoHRE resolutions; MoET UBO page; licensing renewal pages (per MVP authority); portal related-legislations pages | wider inventory | ≈ 8 |
| **Event-triggered** | when an alert names a provision: re-fetch that page once; find dependent rules, cases and answers | impact | ≤ 30 reserve |
| **Total** | | | **≈ 113 normal, ≤ 145 with reserve** (was ≈ 87 for VAT alone). This is an **unvalidated share of an unknown monthly allowance**: only a balance (593 on 17 Oct, resets 11 Nov) is on record. At that size it would be about a quarter of the observed balance each month |

**Every alert reports:**
- new source, changed source or changed provision;
- effective date, if shown;
- potentially affected obligations (rules citing it);
- potentially affected historical answers and open owner cases;
- the human review required;
- activation status (always "not activated").

**Article-level comparison** is used where the page is legislation (portal). Paragraph comparison is used for guidance pages. Firecrawl's own change flag is ignored (5/5 false alarms in the trial).

**Report-only:**
- An alert blocks internal release approval (`answer_label`) of the affected provisions (`source_changed`). It never changes the knowledge base, rules or cases by itself.
- Activation needs both a reviewer record and a register entry, as for VAT.

**Not yet approved:**
- **D18:** any schedule. **Post-event**, and only after you confirm the monthly allowance.
- **D19:** who triages alerts.

Nothing is scheduled today.

## 3. Copies and retention (legal review)
- **Snapshots are copies.** Monitoring snapshots and any full-text collection stay private and internal (hashes and diffs) until D4/G5 is cleared.
- **What users see:** only links and short citations. Nothing is redistributed.
- **Existing VAT text:** the VAT knowledge base already holds FTA text under G5. This is flagged for D4.
