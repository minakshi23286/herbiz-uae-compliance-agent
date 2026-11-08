# HerBiz: Workstream C → Workstream A — 360 MVP handoff

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** 17 Oct 2026 · **From:** Workstream C (branch `ws-c-source-intelligence`) · **To:** Workstream A (reopened by the founder for the narrow 360 MVP; target: working demo by **7 Nov 2026**, submission **10 Nov 2026**) · **Not legal, tax or accounting advice.**

## 1. Ownership (founder, 17 Oct 2026)
| Workstream | Owns | Does not do |
|---|---|---|
| **A** | business-owner onboarding, UX, all MVP screens, the integrated demo and demo mode | build obligations rules or source monitoring |
| **B** | profile model, obligations engine, workflow logic (deadlines, document readiness) | UI; source intelligence |
| **C** | source intelligence, provenance, regulatory monitoring, the source-validity interfaces | **never edits A's application or demo files**, or B's code |

## 2. Authoritative plan and commits
| What | Where | Commit |
|---|---|---|
| Board-reviewed HerBiz 360 plan (deliverables 1–11 + board record + founder report) | `docs/rag/360/CL_HERBIZ_360_01…08_*.md`, `CL_HERBIZ_360_FOUNDER_DECISION_REPORT.md` | `3d8578b`, `9b48966` |
| MVP readiness pack (checklist, owners, demo scenario, test evidence, blockers, decisions F1–F6) | `docs/rag/360/CL_HERBIZ_360_MVP_READINESS_PACK.md` | `37897a1`, updated `6cfcaff` |
| C interface (citations, uncertainty, change impact) | `compliance_agent/rag_c/sources360.py` + `knowledge_base/CL_360_obligation_sources.json` + `CL_360_source_candidates.json` | `37897a1` (latest C: `6cfcaff`) |
| C interface note for A and B | `docs/rag/360/CL_WS_C_TO_AB_360_INTERFACE.md` | `37897a1` |
| B's obligations engine (from B's commit message; **A must verify by running B's tests**) | `ws-b-retrieval`: `compliance_agent/obligations/` (profile schema, five-state engine, VAT/CT/synthetic catalogues, deadline and document-readiness workflows, 37 tests); `CL_WS_B_360_BUILD_REPORT.md` | `0238590`, plus `b63f69a` (SBR note) |

Copies of the C documents are in the `Compliance Operations Agent/` folder. Read C files with `git show <commit>:<path>` or `git archive`, never from C's working tree (the same rule B uses).

## 3. Interface contracts
| Contract | Version | Use by A |
|---|---|---|
| **sources360** (C) | **0.1** | `obligations360 [IDS] --as-of DATE` returns one label per obligation. The fields are frozen by test 195: `user_wording`, `uncertainty` (high or medium; never low while unreviewed), `citations[]` (url, authority, evidence level, retrieved_at, stale), `reviewer_needed`, `open_gaps`, `shown`, `release_approved` (always false). Corporate-tax rows need `profile_synthetic=True`, otherwise they are refused. `impact360 --alerts FILE` returns the affected obligations ("changed, pending review"; never activated) |
| **VAT source validity** (C) | **1.1** | used by B (pinned at `9b48966`); A shows B's VAT labels as they are |
| B's engine output | B's contract | A renders it. A does **not** re-implement rules. Mapping B's obligations to C's `obligation_id`s is the minimum integration work (ask B, or show C's label next to B's row) |

**Required wording:**
- Banner on every screen: "Prototype · synthetic business data · simulated reviewer · Demonstration draft: not legal, tax or accounting advice, not reviewed, and not a compliance decision · HerBiz does not file or pay".
- Corporate-tax rows: prefix "Demo scenario (fictional business)".
- No fees or prices.

## 4. Ready-made demo material from C
| Item | Path |
|---|---|
| Labels for a real profile vs the synthetic persona (CT refused vs shown) | `docs/CL_evidence/ws_c/360/mvp/CL_obligation_labels_*_2026-10-18.json` |
| **Real** change-impact example: SBR window extended from 31 Dec 2026 to **31 Dec 2029** by MD 131/2026 (official MoF text) | `docs/CL_evidence/ws_c/360/mvp/CL_sbr_amendment_impact_2026-10-17.json` |
| VAT change chain (real portal text, synthetic edit, 36 earlier answers flagged) | test 170; `docs/CL_evidence/ws_c/firecrawl/CL_change_impact_demo_2026-10-17.json` |
| Persona card (variants A and B) and the expected-outcome oracle | `CL_HERBIZ_360_06_MVP_ROADMAP_BACKLOG.md` §1 |
| "Do I need an agency?": the who-does-what table, marked estimate and not reviewed, with no fees | `CL_HERBIZ_360_02_PRODUCT_SCOPE.md` §4 |

## 5. Known blockers (what A must not paper over)
| Blocker | Effect on the demo |
|---|---|
| No qualified reviewers (D3 VAT, D3-CT) | everything stays "demonstration draft"; the reviewer is **simulated** |
| B hard-blocks CT in its engine (`blocked_pending_legal_validation`) | the CT journey uses the **fixed two-persona scenario** only; no CT determination for any other profile |
| CT law text not collected (CT-G2); outdated VAT text (G3); deregistration conflict (G1) | uncertainty shows **high** on most rows. This is honest and is part of the demo story |
| E-invoicing small-business dates (EINV-G1); audited-accounts text (ACC-G1) | e-invoicing is awareness-only; audit is flag-and-get-help only |
| A, B and C are on separate branches; no merges without founder approval | integrate on a disposable branch only if the founder approves (decision F2); otherwise show C's labels from the CLI output |
| Reuse terms (D4/G5) | links and short citations only; never full official texts |
| No paid API or Firecrawl calls for A | use C's saved evidence; ask C for any new source facts in writing |

**Requests to C:** in writing (message or document). C answers within its own scope and changes its interface only additively (0.1 → 0.2), with notice.

## Contract 0.2 (17 Oct 2026, on WS B's written request after a legal-kalpu review under D-064)
- **Additive:** every citation now has `citation_chip`. The UI shows it as it is and never derives it:

  | Evidence level | Chip |
  |---|---|
  | observed | "Source found, not reviewed" |
  | listing only | "Source listed, not opened or reviewed" |
  | excerpt | "Source excerpt only, not reviewed" |
  | unresolved | "Source not located" |

- **Wording:** `user_wording` is now short sentences. Example: "Demo scenario (fictional business). Not legal, tax or accounting advice. Not reviewed by a qualified professional. Not a compliance decision. Shown as a demonstration scenario only. Open questions: CT law text not collected; article-level citations unavailable."
- **Unchanged:** the field names and meanings. Test 195 freezes the fields; test 196 checks the wording and chips.
- **Recommendation passed to the founder:** an FTA-registered tax agent checks the CT citation list (including MD 131/2026) before 10 Nov.
