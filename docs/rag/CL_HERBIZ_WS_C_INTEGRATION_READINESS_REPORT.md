# HerBiz: Compliance Agent — Workstream C integration-readiness report

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** Sat 17 Oct 2026 · **By:** Claude Code, Workstream C · **Branch:** `ws-c-source-intelligence` (not merged; no remote) · **Follows** `CL_HERBIZ_RAG_OVERNIGHT_REPORT.md` · **Not legal or tax advice.**

## In short
- **All six tasks are done.**
- **One independent review changed the result.** It found that the B contract could certify an out-of-date version, that the lifecycle test passed for partly wrong reasons, and that the protection triggers could be bypassed. All three are fixed, and the reviewer's mutation test now catches **11 of 11** deliberate faults (it was 8).
- **Tests:** 160 pass, all offline.
- **Firecrawl:** the trial is ready at 11 credits worst case (cap 15). The balance **cannot be read from Claude**, so you need to check it before approving.
- **Not done:** no charge, no source activated, no merge, no change to main-checkout permissions (D17 deferred). The original database is unchanged (md5 `26e202b8…`).

## 1. Ready for integration (technically complete, tested, needs only the merge decision)
| Item | Evidence |
|---|---|
| **Source-validity contract v1.1**: `answer_label()` keeps retrieval completeness (B) and legal-source approval (C) apart; "certified" only if both hold; reasons for every block; strict on version, source, locator and freshness | `CL_HERBIZ_SOURCE_VALIDITY_CONTRACT_v1.1.md`; tests 146–149, 162, 164–166 |
| **Validity export** (schema 1.1) with build stamp, version-scoped issues, `SRC\|*`, FTS integrity check, approval only when register + database + audit agree | `knowledge_base/CL_source_validity.json`; tests 123–124, 145–146, 166 |
| **Register validation** with a database cross-check (it refuses an approval the database does not record) | tests 94–95, 130, 160, 166 |
| **Amendment map** incl. footnote evidence; claims and conflicts; citation integrity; traceability; extraction cross-check | tests 117–129, 144–150 |
| **Discovery + monitor** (offline) incl. the MoF file-name fix found by the lifecycle test | tests 106–116, 131–140, 161 |
| **End-to-end amendment lifecycle**: discovery → collection → comparison → impact → review → activation, on a disposable synthetic workspace; manual steps exactly where a person must decide | `CL_HERBIZ_AMENDMENT_LIFECYCLE_TEST.md`; test 160; 11/11 mutants caught |
| **Code guards** for protected databases (any checkout, links, fail-closed) | tests 86–93, 141–143 |

## 2. Ready, but each needs your approval to use
| Item | Approval | What is prepared |
|---|---|---|
| **Firecrawl trial** (D15) | you check the dashboard balance (≥ 15), then approve the exact plan | `CL_HERBIZ_FIRECRAWL_TRIAL_PLAN.md`; `rag_c firecrawl-plan` (11 credits worst case), stop rules, `firecrawl-verify`, local verification through the monitor (tests 154–155) |
| **Database protection L2/L3** (D17, deferred by you) | your go-ahead, when you want it | reversible commands and a measured effect table in `CL_HERBIZ_DB_PROTECTION_DESIGN.md` |
| **Hardening triggers L4** (D16) | approval of a schema change to the authoritative DB | 13 triggers tested on copies; the app's writes still work (test 163); exact rollback; known limits documented |
| **Scheduled monitoring** | network approval; Firecrawl credits for option B | templates (launchd, Firecrawl session prompt); 1–2 weeks of supervised runs first |
| **Merge of B and C** | your decision | conflicts expected only in `project/CL_project_status.json` and test numbering; keep both sides |
| **B adopts contract v1.1** | B's own work, plus your approval of B's architecture | B1 (critical: B's `certify()`) to B8 in `CL_HERBIZ_RAG_INTEGRATION_HANDOFF.md` |

## 3. Blocked
| Item | Blocked on |
|---|---|
| Any legal source approved, so any answer certified | **D3**: no qualified UAE tax reviewer named |
| G1 deregistration deadline (20 vs 30 business days) | the reviewer, plus the FTA answer (enquiry drafted, not sent) |
| G3 current VAT Decree-Law text | you locating the consolidated file, then an approved collection (D13) |
| Official Arabic texts in the knowledge base | reuse terms (D4) and an extraction method (QA A2) |
| Monitor on the live web | network and credits approval |

## 4. What each task produced
| # | Task | Result |
|---|---|---|
| 1 | Reversible DB protection, incl. journal/WAL and maintenance | `CL_HERBIZ_DB_PROTECTION_DESIGN.md` + `rag_c/protection.py` (`protect-status` is read-only). Measured on copies: 0444 blocks writes; the immutable flag also blocks delete, rename and chmod; WAL creates side files even on read-only opens, so **stay in rollback-journal mode**; authorised maintenance windows defined |
| 2 | Contract: completeness vs approval | v1.1 with truth table; hardened after review |
| 3 | Firecrawl trial ≤ 15 credits | plan of 11 credits: 4 listings + the G1 page twice, uaelegislation once; no PDFs, no stealth proxies |
| 4 | Verify credits | **Not possible from Claude.** No balance capability (one free discovery call, 0 credits). You check the dashboard |
| 5 | Independent lifecycle test | test 160 + an independent adversarial review + mutation testing (11/11 caught) |
| 6 | Offline tests and docs | 148 → 160 tests; 6 new documents; originals unchanged |

## 5. Second independent review (17 Oct; `docs/CL_evidence/ws_c/qa/CL_QA2_lifecycle_contract_protection.md`)
| Finding | Severity | Status |
|---|---|---|
| `answer_label` certified approved but superseded or outdated versions, other-source versions, unparsed locators; stale export unchecked | critical | **fixed** (tests 164–165) |
| A register approval took effect without database review or audit | high | **fixed**: three-way agreement (tests 160, 166) |
| test_160 passed for partly wrong reasons; 3 of 11 mutants escaped | high | **fixed**: 11/11 |
| Triggers bypassed by INSERT/UPDATE OR REPLACE; LIKE removal; stray files | high | **fixed** (13 triggers; tests 151, 163) |
| WAL 0444 nuance | low | documented |

## 6. Decisions waiting for you (unchanged unless noted)
| Id | Decision | Recommendation |
|---|---|---|
| D3 | Name a qualified UAE tax reviewer | needed for everything "approved" |
| — | Send the FTA enquiry (G1) | send |
| D13 | Collect the current DL consolidation once you have its URL | approve |
| **D15** | Firecrawl trial (11 credits, cap 15) after checking the balance | approve |
| D16 | Hardening triggers on the authoritative DB | approve as a separate, reviewed change |
| D17 | chmod / immutable flag on the main checkout | **deferred by you**; nothing done |
| D14, D11 | Extraction improvements; source-update rule | as before |

## 7. Where things are
| Document | Path |
|---|---|
| DB protection design | `docs/rag/CL_HERBIZ_DB_PROTECTION_DESIGN.md` |
| Contract v1.1 | `docs/rag/CL_HERBIZ_SOURCE_VALIDITY_CONTRACT_v1.1.md` |
| Firecrawl trial | `docs/rag/CL_HERBIZ_FIRECRAWL_TRIAL_PLAN.md`, `docs/rag/templates/CL_firecrawl_trial_plan.json` |
| Lifecycle test | `docs/rag/CL_HERBIZ_AMENDMENT_LIFECYCLE_TEST.md`, `tests/test_ws_c_amendment_lifecycle.py` |
| Evidence | `docs/CL_evidence/ws_c/CL_db_protection_experiments_2026-10-17.json`, `docs/CL_evidence/ws_c/qa/CL_QA2_*` |
Copies of this report and the new documents are in the `Compliance Operations Agent/` folder.
