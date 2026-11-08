# HerBiz 360 — Deliverables 1 and 2: Current-state capability audit and original-vision gap analysis

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** Sat 17 Oct 2026 · **By:** Claude Code, Workstream C, with an independent read-only audit agent · **Evidence:** `docs/CL_evidence/ws_c/360/CL_capability_audit_raw_2026-10-17.md` (89 rows, each with file and test references) · **Not legal, tax or accounting advice.**

## In short
- **User evidence:** none. The persona is provisional and no owner interviews have been held.
- **Wording:** in this package, "certified" means **release-approved (internal)**. That is HerBiz's own gate: retrieval complete **and** sources reviewer-approved. It is never a legal, tax or accounting certification.
- **What HerBiz is today:** a local, VAT-centred compliance workflow engine running on **synthetic** data. It has a business profile, a deterministic applicability engine, owner cases, reviewer gates and an append-only audit trail. It also has a real-text VAT retrieval layer (371 FTA passages) and source-intelligence tooling (register, validity, monitoring).
- **Counts:** of 89 capabilities checked, **31** are implemented and tested, **18** partial, **17** documented only, **16** never considered, **7** blocked.
- **Tests:** all pass: main 83, Workstream B 164, Workstream C 170.
- **Corporate tax:** none. The code currently **refuses** corporate-tax questions on purpose.
- **Bookkeeping and financial readiness:** none, apart from one turnover ledger used for the VAT threshold.
- **Not connected:** Workstreams B and C are **not merged**. The app's Ask panel still uses older retrieval and recorded answers. Nothing is release-approved (`approved_versions: []`).

## Conflict with the brief (flagged, as you asked)
| Brief says | Records show | How I proceed |
|---|---|---|
| The original vision is a "360-degree post-business-setup operations, **financial-readiness** and compliance assistant" | No project document mentions bookkeeping or financial readiness. The documented original is a **post-setup regulatory compliance** agent: licence, food, privacy, hiring/WPS, corporate tax, VAT, UBO, AML, e-invoicing, calendar, reminders, document drafter (`CL_Compliance Operations Agent — Full Build Plan_v1.md`). It was later narrowed on purpose to one emirate, one licence and one activity (`CL_MVP_SCOPE_AND_ACCEPTANCE.md:16`) | I treat your brief as the **current founder-supplied vision** (evidence: supplied). Corporate tax and the other obligations restore the documented original; bookkeeping and financial readiness are a **new scope addition** |
| The "48-topic VAT provision map" (D3 task) | `CL_provision_map_v7.json` has **47** topic keys; the D3 package says 48 (it may count differently) | flagged for Workstream B to reconcile before the package is sent |
| The MVP excludes "any AI model call" | about US$5 of approved, capped LLM experiments ran | the scope document is stale; it does not affect this work |

## 1. Capability audit by area
**Classes:** 1 implemented and tested · 2 partial · 3 documented only · 4 not previously considered · 5 blocked.

| Area | 1 | 2 | 3 | 4 | 5 | What exists, in one line |
|---|---|---|---|---|---|---|
| A Business profile | 6 | 1 | 5 | 3 | 0 | emirate, activities, licence dates, revenue ledger, VAT status, versioned profile. **Missing:** mainland/free zone, licensing authority, entity type, natural vs juridical person, financial year, CT status |
| B Applicability engine | 1 | 0 | 0 | 0 | 0 | deterministic engine with 6 outcomes (applicable, not applicable, needs clarification, conflict, stale, not yet in force); rules are synthetic, plus one real, unreviewed VAT draft |
| C VAT | 7 | 7 | 0 | 0 | 2 | retrieval, provision map, validity and release-approval gate, amendment tracking, threshold calculator. **Partial:** returns, invoices, input tax, exempt/zero-rated, records (retrieval only, no computation). **Blocked:** deregistration (G1), G1/G3 resolution |
| D Corporate tax | 1 | 0 | 1 | 0 | 0 | only a **refusal** classifier; the original plan included CT |
| E Bookkeeping | 1 | 3 | 0 | 10 | 0 | one turnover ledger with 8 line types; draft labelling. **None:** receipts, reconciliation, chart of accounts, P&L, balance sheet, cash flow, CT computation, VAT reconciliation, year-end, accountant export |
| F Other obligations | 2 | 4 | 5 | 2 | 0 | licence renewal, privacy, e-invoicing and food exist only as **synthetic** rules. UBO, WPS, immigration, AML and free zone are documented only. ESR and closure were never considered |
| G Deadlines and tasks | 1 | 1 | 2 | 0 | 1 | owner to-do list (synthetic rules); due dates copied from the profile, **never computed**; no calendar, no reminders |
| H Output, review, audit, sources, UI, AI | 12 | 2 | 4 | 1 | 4 | audit trail, review gates, evidence submission, monitoring tooling, change impact, local web UI, LLM gating, backups. **Gaps:** document drafting, scheduling, Arabic UI, deployment. **Blocked:** real reviewer (D3), live LLM (D5e), Arabic texts, reuse terms (D4) |

## 2. Gap analysis against the 360 vision
| Vision element | Today | Gap | Size |
|---|---|---|---|
| Business profile and applicability | engine solid; profile thin | add 8 profile facts (jurisdiction type, authority, entity type, legal personality, financial year, CT status, permissions, employees used) and rules that use them | medium |
| Personalised obligations across domains | VAT only (real), others synthetic | obligation catalogue for CT, e-invoicing, licence, UBO, WPS, ESR (historical); applicability rules from official sources | large |
| VAT guidance | strong retrieval and governance; not wired to the app; G1/G3/D3 | merge B and C into the app; collect the current DL text (D13); reviewer (D3) | medium |
| Corporate tax guidance | none; refusal | sources located (metadata). Needed: collection, a CT provision map, applicability (natural person AED 1m, juridical person always, SBR), deadlines | large |
| Deadline calendar | none (dates copied) | deadline engine: rules × profile → dated tasks (CT return 9 months, CT registration 3 months / 31 March, VAT returns, licence expiry) | medium |
| Required documents | evidence text only | document checklist per obligation (e.g. CT registration documents from the FTA service card) | small–medium |
| Bookkeeping and financial readiness | turnover ledger only | transaction log, categories, receipt list, simple P&L, revenue tests for thresholds, accountant export; strict labels (estimate / bookkeeping report / draft) | large |
| Calculations and validation | VAT threshold only | SBR revenue test, CT natural-person test, VAT threshold; no tax computation in the MVP | medium |
| Draft outputs and owner review | owner cases | generated checklists and summaries labelled draft | small |
| Professional review and escalation | review gates, simulated reviewer | specialist reviewer roles per domain (Deliverable 10); "when to get help" rules | small (design), blocked (people) |
| Official submission by an authorised person | not applicable (no filing) | keep it that way: hand-off pages to EmaraTax and licensing portals, never autonomous | none to build |
| Evidence and audit trail | strong | extend to new domains | small |
| Ongoing monitoring | VAT tooling, not scheduled | extend the register and monitor to CT and other sources; schedule after approval (D18) | medium |

**Biggest risks if nothing changes** (draft, unreviewed; evidence O/S per Deliverables 4–5):
1. **Corporate tax.** Corporate-tax questions are refused, yet every HerBiz company user appears to have a corporate-tax filing duty (FTA pages, O/S; unless an exemption applies).
2. **Small Business Relief.** ~~It may end with tax periods ending in 2026.~~ **Correction (17 Oct, later):** MD 131/2026 (official MoF text, observed, not reviewed) extends it to tax periods ending on or before 31 Dec 2029. The risk is now a stale answer, not the end of the relief. This is a live example of why monitoring matters.
3. **Demo gap.** The demo shows synthetic obligations as if they were the product, while the real VAT work sits on unmerged branches.
