# HerBiz: Compliance Agent — Change chain and B + C integration test

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** Sat 17 Oct 2026 · **By:** Claude Code, Workstream C · **Not legal or tax advice.**

## In short
- **The change chain works end to end.** I used a real official text with one invented edit. The monitor found the one changed article out of 87. It named the affected provision and flagged 36 earlier answers that relied on it. It raised a high alert, and the change could not become certified knowledge until a person reviewed it.
- **B and C work together.** Workstream B's answer pipeline, running against C's current code, gives the same results B recorded. When the sources are made "approved and current" in a pretend world, 11 of 13 answers can be certified. An unreviewed change then blocks 7 of those again.
- **Everything ran on throwaway copies.** No real source was approved. The original database (md5 `26e202b8…`) and the ledger (md5 `59226cd0…`) are unchanged. B's files were not edited, and B's blind set v9 was not read.

## Part 1: the change chain (test 170, `tests/test_ws_c_change_impact.py`)
| Step | Real or invented | What happened |
|---|---|---|
| 1 Detect a change | **real** text: portal DL 8/2017 scraped 17 Oct; **invented** edit: Art. 13(1)(b) "(30) thirty days" → "(60) sixty days" in a copy | the monitor compared 87 articles and reported **only Article 13** as changed |
| 2 Identify the article | real | affected provision `FTA-VAT-DL8\|13` |
| 3 Flag earlier answers | answers from the experiment ledger (a copy) | **36 of 259** recorded answers cite DL Art. 13, for example Q01, Q03, Q04, Q45, U01 |
| 4 Review alert | generated | severity **high**, kind `changed_substantive_in_scope`; the monitor run exits with code 2 |
| 5 Block until reviewed | pretend world where every version is approved | Art. 13 answer **not certified**; reason `source_changed`; the user sees "… changed recently …". After a person marks the alert reviewed, the block is lifted; other blockers (G3) stay |

Evidence: `docs/CL_evidence/ws_c/firecrawl/CL_change_impact_demo_2026-10-17.json`.

## Part 2: B + C integration (disposable copy)
**Setup:**
- B's code came from a `git archive` of branch `ws-b-retrieval` into Claude's scratch folder, so B's checkout was not touched.
- The knowledge base was a byte copy (md5 `26e202b8…`), and C was the current worktree.
- B loads C's interface the way it was designed to, through `source_validity_c.load`, which needs contract 1.1.
- **Questions:** B's v8 set, using B's recorded classifier outputs. There were no model calls and no paid API.

**Baseline:** B's own offline evaluation, re-run against C's current code, reproduces B's recorded numbers:
- recall 0.84;
- 1 silent miss (Q824);
- 0 certifiable;
- statuses: complete 13 / incomplete 13 / ambiguous 1 / out of scope 1.

**What-if worlds** (only the validity export was edited, and only in disposable copies):
| World | Verified retrieval | Certifiable | Why |
|---|---|---|---|
| 1 As today | 13 | **0** | no source approved; stored DL outdated (G3) |
| 2 Every version marked approved | 13 | **0** | approval alone is not enough: the stored DL is **outdated**, and 3 answers also cite text that applies only from 2027 |
| 3 World 2 + an unreviewed change to ER Art. 7 | 13 | **0** | (as world 2) |
| 4 Approved **and** current text collected (G3 fixed, pretend) | 13 | **11** | Q809 still blocked: the G1 **conflict** (20 vs 30 days). Q807 still blocked: it cites the ER front matter, which is never certifiable |
| 5 World 4 + an unreviewed change to DL Art. 13 | 13 | **4** | 7 answers (Q801, Q803, Q808, Q819, Q824, Q825, Q826) blocked by `source_changed` |
| Any world | — | out-of-scope answers certified: **0** | |

**What this proves:**
1. **Two different questions.** Retrieval completeness (B) and legal approval (C) stay separate. "Complete" never turns into "certified" on its own.
2. **Approval is not enough.** Even an approved source is blocked when it is out of date, conflicting, not yet in force, or changed and unreviewed.
3. **The block is precise.** A change to Art. 13 blocks only the answers that use Art. 13.

**Found for B (not fixed here, because B owns the retrieval code):**
- **What blocks Q807:** `unparsed_locator`. B's retrieval included the passage `FTA-VAT-ER`, "Front matter, p. 1", among its evidence.
- **Why that is correct:** the contract never certifies front matter, because it is not an article and cannot be keyed.
- **Handoff item B9:** either leave front matter out of the evidence for an answer, or keep it as context only, not as a citation.

Evidence:
- `docs/CL_evidence/ws_c/integration/CL_bc_whatif_results_2026-10-17.json`;
- the harness: `docs/CL_evidence/ws_c/integration/CL_bc_whatif_harness.py`, run from a scratch copy, never from B's checkout.

## What is still needed for a real integration
| Step | Who |
|---|---|
| Merge decision for `ws-b-retrieval` and `ws-c-source-intelligence` | you |
| A reviewer (D3) and collection of the current DL text (D13) | you |
| B9: front-matter passages as citations (Q807) | Workstream B |
