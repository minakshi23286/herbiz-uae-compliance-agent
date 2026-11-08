# HerBiz 360 — Deliverable 7: Modular architecture proposal

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** Sat 17 Oct 2026 · **Status:** proposal; nothing built yet beyond what the audit lists

## Principle
Keep the existing **deterministic engine + governed sources + human gates** design and add domains as modules. The VAT provision map does **not** cover corporate tax or anything else. Each domain gets its own sources, provision map, rules and reviewer.

## Modules
| # | Module | Responsibility | Reuses (existing, tested) | New work |
|---|---|---|---|---|
| 1 | Business Profile | the facts in Deliverable 3 §1, versioned | `profiles.py`, `store.py` business_profiles, `/api/profile` | 8 new facts; validation; owner questions |
| 2 | Obligation Applicability Engine | rules × profile → applies / does not apply / needs clarification / conflict / not yet in force | `engine.assess` (6 outcomes, no model) | an obligation catalogue file per domain; rules use only profile facts and cited provisions |
| 3 | VAT Module | VAT obligations, retrieval, provision map | B pipelines (v7 / C1P2), provision map v7, C validity contract v1.1 | merge into the app (decision); D13, D3 |
| 4 | Corporate Tax Module | CT obligations and guidance | the same retrieval and validity design | CT source collection, a CT provision map (new; reviewed separately), rules (natural person AED 1m; juridical always; SBR test; deadlines) |
| 5 | Accounting and Financial Readiness | transactions, categories, receipts, reconciliation, draft reports, export | VAT ledger types and the refuse-unknowns rule | new store tables; label ladder enforced in code (an output cannot carry a higher label than its inputs allow) |
| 6 | Licensing and Other Compliance | licence renewal, UBO, WPS, e-invoicing readiness, ESR (historical), closure | synthetic rule patterns (LIC-RENEWAL, EINV-START) | per-authority data; official sources |
| 7 | Deadline and Task Engine | compute due dates from rules (e.g. FY end + 9 months), show their basis, create owner cases | `engine._sync_case`, owner cases | date arithmetic with business-day rules; "estimated" when a fact is missing; reminders later |
| 8 | Source Intelligence and Monitoring | register, versions, validity, amendment map, monitor, change impact | all of `rag_c` (register, validity, interface, monitor, discovery, change impact test 170) | register per domain (CT, e-invoicing, licensing…); `CL_360_source_candidates.json` becomes the CT/other register after review |
| 9 | Document Preparation | checklists, packs, letters, accountant export | — | templates; DRAFT marking |
| 10 | Professional Review and Escalation | reviewer roles per domain, sign-off, "get help" rules | `review_source`, `review_interpretation`, `reviewer_signoffs`, D3 package | add a test for sign-off (missing today); domain reviewers (Deliverable 10) |
| 11 | Audit Trail and Evidence | append-only events, evidence, ledger | `store.py` triggers, C protection triggers | extend to new tables |

## Data flow
```
Profile (1) ──► Applicability (2) ◄── Rules per domain (3, 4, 5, 6) ◄── Approved provisions only (8)
     │                 │
     ▼                 ▼
Deadlines (7) ──► Owner cases ──► Documents (9) ──► Owner review ──► Professional review (10) ──► [official portal, outside HerBiz]
     ▲                                                                                              │
Monitoring (8): change → affected provisions → affected rules, cases and answers → review alert ──────┘ (evidence: 11)
```

## Reuse of Workstream C mechanisms
- **Validity contract v1.1** (`answer_label`): use it for every domain. Retrieval completeness and source approval stay separate.
- **Change impact (test 170):** source change → article → answers and **cases** affected → alert → block until reviewed. For CT and the other domains, a change to a rule's cited provision also re-runs `engine.assess` for every affected profile. The engine does this already for synthetic rules (tests 14–15).
- **Register discipline:** discovered ≠ verified ≠ approved; versioned register; approval needs both a reviewer record and a register entry.

## What must not happen
- One shared "provision map" across tax types.
- Corporate-tax answers built from VAT texts.
- A deadline shown without its rule and source.
- Any module that submits, pays or signs.
