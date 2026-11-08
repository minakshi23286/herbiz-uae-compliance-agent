# HerBiz: Compliance Agent — RAG integration handoff, Workstream C → Workstream B (interface contract v1.0)

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** 17 Oct 2026 · **From:** Workstream C, branch `ws-c-source-intelligence` · **To:** Workstream B, branch `ws-b-retrieval` · **Status:** drafted, proposed; **no branch merged, no B file edited** · **Supersedes** contract v0.1 (`CL_RAG_ARCHITECTURE_WS_C.md` §11) · **Not legal or tax advice.**

> Read with: `knowledge_base/CL_source_validity.json` (generated), `compliance_agent/rag_c/interface.py` (the only entry point B needs), `docs/rag/CL_HERBIZ_SOURCE_VALIDITY_MATRIX.md`. An independent architecture QA (17 Oct) ran B's `pipeline_v7` over 218 fixture questions with C's export in place of B's mirror: **0 status changes**. A plain file swap still breaks 3 B tests (renamed issue ids, a frozen sha256). Details in `docs/CL_evidence/ws_c/qa/CL_QA_architecture_interface.md`.

## 1. What B should change on its own branch (C will not touch B's files)
| # | Change | Why | Priority |
|---|---|---|---|
| B1 | **Never label an answer "certified" unless every cited provision is from an *approved* version with no C issue.** QA found B's `certify()` returns `certified: True` for every coverage-complete retrieval (82/218 fixtures) without checking source status. Use `interface.certification_blockers()` | today **nothing is approved** (D3); the word must not reach users | **critical, before any user sees it** |
| B2 | Read validity through `interface.load_validity(db=<the DB you query>)`; it refuses an export generated for another build | stale or wrong-build export | high |
| B3 | Match issues with `interface.provision_status()`: it applies whole-source `SRC\|*` issues and treats web-page paragraphs as `SRC\|*` | B's exact-key lookup misses `SRC\|*` (e.g. `FTA-VAT-DL8:partial-scope`) | high |
| B4 | Cite by `(article_id, version_id, quote)` and verify with `interface.resolve_by_article()`; treat `passage_id` as build-scoped | passage ids are reused for different text across builds (D10: `#0002` changes from front matter to ER Art. 1) | high |
| B5 | Before "complete", check required provisions against `missing` issues (e.g. `FTA-VAT-DL8\|54 (bis)`) | a missing article is never retrieved, so a retrieval-only check cannot see it | medium |
| B6 | Use `validity.current_versions[source]` for version selection, or record why `MAX(seq)` differs | C uses latest stated effective date; same result today (ER@v3) | medium |
| B7 | Do not present footnote text as current law (`future_text` issue on ER Art. 55/56: CD 149/2026 text applies from the first tax year after 1 Oct 2027) | footnotes sit inside passages (gap G8) | medium |
| B8 | Deregistration deadline (G1): show ER Art. 14(1) (20 business days) **and** the FTA page (30), and recommend confirming with the FTA or a tax agent. Never choose | G1 blocked; FTA enquiry drafted, not sent | high |

## 2. Contract v1.0
### 2.1 Identifiers
| Item | Format | Stable across builds? |
|---|---|---|
| Source | `FTA-VAT-DL8`, `FTA-VAT-ER`, `FTA-VAT-REG-PAGE` | yes |
| Version | `SOURCE@vN` (collection order; never renumbered) | yes |
| Article id | `SOURCE|N`, `SOURCE|N (bis)`, `SOURCE|Paragraph N` (web pages), `SOURCE|*` (whole source) via `interface.article_id(source, locator)` | **yes** |
| Locator | `Article N[ (bis\|ter\|quater)], p. P \| pp. P1-P2[, part K]` · `Paragraph N` · `Front matter, p. P` (unchanged from v0.1) | yes (grammar) |
| Passage id | `<source>:<sha12>#<seq>` | **no: build-scoped** (changed from v0.1) |
| Build id | md5 of the database file, in `validity._meta.database_md5` | identifies one build |

### 2.2 Validity export (`schema_version` 1.1)
`issues[]`: `{id, kind, version_id, provisions[], message, …}`. Kinds:
- `outdated`: the version predates an in-force amendment. `SRC|*` means *any* provision may be affected.
- `repealed`
- `missing`: an article exists in law but not in our copy.
- `conflict`: official sources disagree. It carries `topic`, `values` and `claims`.
- `future_text`: a footnote holds text not yet in force.
- `extraction`: an article has no own passage in this build.
- `unverified`: a registered claim failed verification.

Also in the export:
- `current_versions{source: {version_id, basis, fta_currency, outdated}}`
- `versions[]`: status, verification, language, translation status, approved, current, superseded_by
- `claims[]`
- `_meta`: `rule`, `coverage_disclaimer` (**"no issue" ≠ complete or correct**), `known_caveats`, `database_md5`

### 2.3 Status words (must stay distinct)
- **Source status** (C): `candidate` → `verified` → `approved`, plus `superseded` and `rejected`. Today: 5 candidate, 0 verified, 0 approved.
- **Retrieval coverage** (B): `complete` / `incomplete` / `refusal` and so on. This is never the same thing as approval.
- **Certifiable** = approved + current version + no issue + B's own coverage complete. Today nothing is certifiable.

### 2.4 Functions (`compliance_agent/rag_c/interface.py`, all read-only)
| Function | Returns |
|---|---|
| `load_validity(path=EXPORT, db=None)` | the export; with `db`, raises if it was built for another database |
| `article_id(source, locator)` | stable provision id |
| `provision_status(validity, source, locator, version_id=None)` | issues, kinds, conflict, current version, approved, certifiable |
| `certification_blockers(validity, [(source, locator, version_id), …])` | every C-side reason an answer cannot be certified |
| `resolve_citation(con, {passage_id, quote}, validity)` | provenance (raw sha256, URL, version) + integrity for a same-build citation |
| `resolve_by_article(con, source, version_id, article_id, quote, validity)` | build-independent citation check |

### 2.5 Data files B may read (read-only)
| File | Content |
|---|---|
| `knowledge_base/CL_source_validity.json` | the export, regenerated by `rag_c validity --write` |
| `knowledge_base/CL_article_headings.json` | article titles and Title/Chapter per version (request C-5) |
| `knowledge_base/CL_source_register.json` | sources, versions, candidates, instruments, claims, gaps |
| `data/CL_rag_c_d10_build.sqlite3` (C worktree, disposable) | D10 build (ER Art. 1 split out); git-ignored. Copy it, never open it read-write |

### 2.6 Rules both sides keep
1. **Reading:** B opens C's databases read-only; C never writes B's files.
2. **Builds:** a new build always goes to a new file, with a `rag_c diff` report.
3. **Version selection:** a change in the rule is announced in writing.
4. **Contract changes:** a locator-grammar or key-format change needs a new contract version.
5. **Integration:** both branches are merged together, with the founder's approval. Conflicts are expected in `project/CL_project_status.json` (both append) and in test numbering (both use 86+); keep both sides.

## 3. B's requests C-1 to C-7: status
| # | Request | Status 17 Oct |
|---|---|---|
| C-1 | Confirm contract | **met as v1.0** (this document). Changes from v0.1: passage ids build-scoped; issues carry version_id; `SRC\|*` keys |
| C-2 | G2 fix into a new DB | **met**: D10 build, diff 365/371 unchanged; not integrated |
| C-3 | Consolidated DL incl. DL 16/2025 | **not met**: file not located; collection needs approval. Interim: `FTA-VAT-DL8:partial-scope` flags every DL8 provision |
| C-4 | Version selection by effective date | **met in C's export** (`current_versions` with basis); B to adopt (B6) |
| C-5 | Headings and chapters | **met**: `CL_article_headings.json` |
| C-6 | Conflict field | **met**: `conflict` issues and `claims[]` (G1 detected automatically from claims) |
| C-7 | Next build path and report | **met**: `data/CL_rag_c_d10_build.sqlite3` + `docs/CL_evidence/ws_c/CL_d10_build_diff_2026-10-16.json` |

## 4. Known issues B should know about
- **G1:** deregistration deadline conflict (blocked).
- **G3:** the DL copy is outdated.
- **G8:** footnotes sit inside passages, sometimes in the wrong article.
- **G9:** the knowledge base is English only (unofficial translation).
- **Broken words:** pypdf splits some words ("Au thority") and even numbers (ER v1 Art. 70: "Article 8 0"). Exact-quote checks can fail on them. Normalise before matching.
- **Long articles** are cut into 3,000-character parts, sometimes mid-word, e.g. inside ER Art. 14(9).

> **Update 17 Oct 2026:** contract **v1.1** adds `interface.answer_label()` and makes the completeness vs approval separation explicit: see `CL_HERBIZ_SOURCE_VALIDITY_CONTRACT_v1.1.md`. B1 now means: replace `certify()` with `answer_label()`.
