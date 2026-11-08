# HerBiz: Compliance Agent — End-to-end amendment lifecycle test

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** 17 Oct 2026 · **Test:** `tests/test_ws_c_amendment_lifecycle.py::test_160_full_lifecycle` · **Status:** implemented, passing; independent adversarial review requested · **Not legal or tax advice.**

**Setup:** everything runs in a temporary folder.
- **Copies:** a byte copy of the knowledge base, the register, the lock, and a new raw folder.
- **Synthetic content:** source `SYN-ER` and "Cabinet Decision No. 999 of 2027" are invented. URLs under `/__SYNTHETIC_TEST__/` do not exist.
- **Real files:** the real register, database, raw files and lock are not touched. The test checks that the reference DB md5 is unchanged at the end.

| Stage | What happens | Done by | Automatic? | What the test proves |
|---|---|---|---|---|
| 0 Baseline | SYN-ER v1 (threshold AED 375,000) collected, approved by a named test reviewer, recorded in a register version with approval evidence | test (stands in for founder + reviewer) | no | an approved, current provision **is** certifiable when retrieval is complete |
| 1 Discovery | day 1 vs day 2 listing. Day 2 adds "Cabinet Decision No. 999 of 2027" and a new consolidation; the old URL now serves new bytes | `rag_c.monitor` + `discovery` | **yes** | both new documents proposed as **inactive** candidates; alerts `new_document_on_listing`, `differs_from_collected_version`, `changed_substantive_in_scope` on `SYN-ER\|7`; DB status unchanged |
| 2 Collection | the new consolidation collected into the disposable workspace | `kb collect` (in real life: founder-approved `--allow-network`) | no (approval) | new version `SYN-ER@v2` is a **candidate**; v1 stays approved |
| 3 Version comparison | v1 → v2 article diff | `KnowledgeBase.compare` | yes | Art. 7 substantive; Art. 14 not |
| 4 Impact analysis | v2 and the instrument recorded in a new register version | person records; tools analyse | analysis yes | v1 marked outdated, with Art. 7 learnt **from v2's own footnote**; the old vs new threshold surfaces as a conflict; v2 becomes current by effective date; **neither v1 nor v2 is certifiable** (v1 outdated / not current; v2 not approved) |
| 5 Review | anonymous approval refused; named reviewer approves v2 | `engine.review_source` | no (reviewer) | v1 automatically **superseded** in the DB; still **not certifiable** until the register records the approval |
| 6 Activation | the register version records v2 approved and v1 superseded; the old claim is retired; the validator passes | person | no | v2 Art. 7 **certifiable** with complete retrieval; not with incomplete retrieval; v1 never; real sources still all candidate |

**Boundary by design:**
- **Automatic:** discovery, comparison and impact analysis, all of which only report.
- **Manual (a person with authority):** collection, review and activation.
- **Activation needs two records:** the reviewer's decision in the database, and an approval entry in the register. Either alone is not enough (asserted in stages 5 and 6).

**A real bug this test found (fixed the same day):**
- **What went wrong:** after the QA hardening, the monitor's document-link filter matched keywords against the raw URL path.
- **Effect:** hyphenated Ministry of Finance file names (`Cabinet-Decision-No.-149-…`) and links with generic file names but relevant titles were silently dropped, so new MoF decisions would never have been proposed.
- **Fix:** hyphens, underscores and `%20` are normalised before matching, and the link title also counts. Regression test 161.

## Independent mutation testing (17 Oct 2026)
**First run:** the second reviewer applied 11 deliberate faults (mutants) to the code and the test; test_160 caught 8.

**Escaped and closed:**

| Mutant | What it did | Now caught by |
|---|---|---|
| M5 | the monitor flags every in-scope article | assert Art. 14 is not in the change alert |
| M6 | outdated issues never generated | new stage 1b, "amendment known, new text not collected": v1 Art. 7 blocked for `outdated` + `version_outdated` |
| M9 | register approval without the database review | `validate(db=…)` refuses it; the validity export does not count it |

The stage 4 and stage 6 checks now assert the **specific** reasons (`version_not_current`, `version_outdated`), not only the threshold conflict.

**Re-run on the fixed code: 11 of 11 mutants caught** (harness: `docs/CL_evidence/ws_c/qa/CL_QA2_mutation_harness.py`, run on a scratch copy).
