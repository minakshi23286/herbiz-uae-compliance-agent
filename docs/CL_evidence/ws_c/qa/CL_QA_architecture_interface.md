# HerBiz: Compliance Agent — QA review: RAG architecture and the Workstream B interface

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** 17 Oct 2026 · **Reviewer:** independent QA (architecture / interface), read-only · **Status:** drafted · **Not legal or tax advice.**

**Scope read:** C worktree `ws-c-source-intelligence` at `bb5ad2a` (+ untracked `compliance_agent/rag_c/interface.py`, being written by another session during this review). B read only through `git show ws-b-retrieval:<path>` at `a078e3a`. Nothing was edited in either worktree. All simulations ran on copies in `scratchpad/qa/arch/` (B tree from `git archive`, DB copies). No network was used.

## Evidence produced (observed 17 Oct 2026)
| # | Check | Result |
|---|---|---|
| E1 | B tests (v6, v7, c1) on a copy of B's tree + copy of the read-only DB (md5 `26e202b8…`) | baseline: 30 run, 1 failure (`test_c1_08`, already failing, unrelated) |
| E2 | Same, with C's `CL_source_validity.json` copied over B's `CL_source_validity_v6.json` | 3 more failures: `test_v6_05` (expects id `G3`, gets `FTA-VAT-DL8:outdated`), `test_v6_06` (expects `G1`, gets `conflict:vat.deregistration…`), `test_v7_03` (frozen sha256 of the v6 file) |
| E3 | B `pipeline_v7.retrieve` on 218 unique fixture questions, mirror vs C export (same DB) | **0 status changes** (82 complete / 60 incomplete / 26 ambiguous / 26 out_of_scope / 24 source_validity_unresolved in both) |
| E4 | Same 218 questions: ref DB + committed export vs D10 build + validity regenerated for D10 | 0 status changes |
| E5 | Passage ids, ref DB vs D10 build | 371 / 371 ids in both; **6 ids keep their id but change content**; 3 of them change locator: `FTA-VAT-ER:<doc>#0002` was `Front matter, p. 2`, is now `Article 1, pp. 1-2` (all 3 ER docs). The `#0001` front-matter passages change their text |
| E6 | `rag_c.citations.trace_ledger` over the experiment ledger (opened read-only), ref vs D10 | identical: 259 answers, 639 citations, 635 quote_found, 4 QUOTE_NOT_FOUND, 0 certifiable. No recorded citation points to a reused `#0002` id, so no harm **today**, by luck rather than by design |
| E7 | `build_validity` on the D10 build | the `FTA-VAT-ER:extraction` (ER Art. 1) issue disappears; md5 `4bb8ed9d…`. The committed export still carries it and is bound to `26e202b8…` |
| E8 | md5 of `data/CL_compliance.sqlite3` in C's worktree | `c3316022…` ≠ `26e202b8…`, the value the export and §10 cite. Not investigated further (B's own DB was not opened, per the read-only rule). Which file is "the" database is ambiguous |

## (1) Can B use C's export as a drop-in replacement?
**Structurally, almost yes. In behaviour today, yes (E3). As a literal file swap, no (E2).** B's pipelines (`pipeline_v6/_v7._finish`, `pipeline_c1` through `_finish`) read only `issues[].id`, `issues[].provisions` and `issues[].message`. C's export has all three, in the same `SOURCE|ARTICLE` key format, and covers the same provisions as B's mirror (DL8 48, 74, 79 (bis), 54 (bis); ER 14), plus ER Art. 1 (extraction).

Exact incompatibilities:
1. **Issue ids differ:** `G3` becomes `FTA-VAT-DL8:outdated` + `FTA-VAT-DL8:repealed`; `G3-missing` becomes `FTA-VAT-DL8:missing`; `G1` becomes `conflict:vat.deregistration.mandatory_application_deadline`. B's tests v6_05 and v6_06 fail on this.
2. **Path and freeze:** B loads the fixed file `llm_lab/data/CL_source_validity_v6.json` (cached with `lru_cache`), and `test_v7_03` freezes its sha256. B has no "load C's export" path. `interface.load_validity()` exists only in an untracked file.
3. **Whole-source keys are silently ignored.** B looks up issues by exact key (`I.get(required_key)`). C writes `SOURCE|*` for `partial-scope` (in-force amendment, article list incomplete) and for claim integrity failures. A `FTA-VAT-DL8|*` issue would never match a required `FTA-VAT-DL8|48`. The only time it matches is when B's map itself requires `SRC|*` (it does for `FTA-VAT-REG-PAGE|*`). There are none for current versions today, so the gap is latent, but it is the precise case "any provision may be affected".
4. **Paragraph key divergence.** `validity.py` turns a conflict claim's locator into `SRC|Paragraph N` (`locator.split(",")[0].replace("Article ","")`), and `interface.article_id` does the same. B's `locators.article_key` returns `None` for paragraphs, and B's maps use `FTA-VAT-REG-PAGE|*`. A conflict involving the registration page (the threshold claims sit on `Paragraph 1`) would be invisible to B. A `Front matter` locator would give the junk key `SRC|Front matter`.
5. **Fields B ignores:** the new `kind` values (`repealed`, `missing`, `extraction`, `unverified`), conflict `values`/`claims`, `current_versions`, `versions[].approved`, `_meta.database_md5`. B treats every kind the same (unresolved), which is safe but cannot say "sources disagree: 20 vs 30" (the reason for C-6) or "repealed".
6. **Issues are not version-scoped.** Keys carry no `version_id`. The export assumes C's choice of current version (effective date); B picks `MAX(seq)`. Today they agree. After any new capture, issues could attach to a version B is not using.
7. **The export is bound to one database** (`database_md5 26e202b8…`). Pointed at the D10 build, it wrongly keeps the ER Art. 1 extraction issue (E7). B never checks `database_md5`.

## (2) B requests C-1 … C-7
| # | Verdict | Evidence |
|---|---|---|
| C-1 contract v0.1 confirmed | **Partially met** | §11 is still "proposed v0.1" and names branch `ws-c-rag-foundation`. B's `locators.py` implements the grammar. C's own D10 build breaks the §11 promise "existing passage ids are never reused for different text" (E5). The validity export is not part of §11. A v1.0 is referenced in untracked `interface.py`, but its handoff document `CL_HERBIZ_RAG_INTEGRATION_HANDOFF.md` does not exist |
| C-2 G2 fix in a new DB with diff | **Met (not integrated)** | D10 build plus `CL_d10_build_diff_2026-10-16.json`. Corpus-only (no draft interpretations). The ER Art. 1 passage text starts "Article 1 1 Definitions". The committed export still flags ER\|1 because it was generated on the pre-D10 DB |
| C-3 consolidated DL incl. DL 16/2025 | **Not met** | candidate `CURRENT-DL8-CONSOL-INCL-DL16-2025` has `url: null`, evidence "unresolved". Needs a founder-approved network capture. Mitigation in place: the DL8 48/74/79 (bis)/54 (bis) issues |
| C-4 version selection by verified effective date | **Partially met** | `amendments.py` / `current_versions.basis` choose by the stated effective date. Dates are `observed_in_file`, not checked against the Gazette. B still uses `MAX(seq)`. The export carries no `seq`, so nothing tells either side when the two rules diverge |
| C-5 headings and chapters | **Mostly met** | `extraction_check.headings()` / `rag_c headings`. Only a CLI command: no committed data file or evidence JSON for B to read without importing C's code |
| C-6 register field for conflicts | **Partially met** | `register.claims[]` + `claims.check_claims` + export `kind: conflict` with `values`. Conflicts are found only between hand-registered claims (2 topic pairs), not across the `fact_inventory`. An external source (the DEREG service page) cannot be keyed. B does not read `values` |
| C-7 build path + dry-run report | **Partially met** | delivered as `data/CL_rag_c_d10_build.sqlite3` (git-ignored), not the requested `data/CL_rag_c_build.sqlite3`. Diff report exists. No validity export generated for that build |

## (3) Source-to-answer traceability across builds
- `check_citation` resolves **by `passage_id` only**. The detail text tells you to "resolve by source and locator", but no code does it.
- `passage_id = doc_id#seq` and `doc_id = source:sha256[:12]` of the raw file. When extraction changes but the raw file does not (D10), the `doc_id` stays the same, so **the same id can point to different text and a different locator** (E5). The quote check catches changed text only if the quote no longer appears. If the moved text still contains the quote, the citation shows the new locator with no warning.
- Today the ledger is unaffected (E6). That is coincidence: no recorded citation pointed to the reused ids.
- **Verdict:** a citation is **not reliably resolvable across builds.** It needs a stable provision id (`source|article`) **plus** `version_id` **plus** a passage text hash, with resolution done in that order.

## (4) Candidate / verified / approved separation
- C side: correct. All 5 versions are `candidate` / `unverified` / `UNVERIFIED_EXTRACTION`, `approved_versions: []`. `check_citation.certifiable` and `interface.provision_status.certifiable` both require `approved`, so C certifies 0 of 259 answers.
- **B side: a gap.** `pipeline_v7.certify()` returns `certified: True` whenever retrieval is `complete` (82 of 218 questions, E3). B selects `v.status AS source_status` but never uses it, and B's provision map is itself "draft until reviewer approves". Nothing is labelled "approved", and `ask.py` says "Nothing is ever labelled verified". Still, "certified" in B means *coverage-complete on unapproved sources*. If that word reaches a user, it reads as approval.
- **Can anything be shown as approved today?** No source or claim is approved. The only risk is the B "certified/complete" wording.

## Findings
| id | sev | finding | evidence | suggested fix |
|---|---|---|---|---|
| A-01 | **High** | Same passage id is reused for different text/locator across builds; violates §11 | E5: ER `#0002` Front matter p.2 → Article 1 pp.1-2 in all 3 ER docs | Contract v1.0: citations carry `article_id + version_id + text_sha256`; resolve by those; either derive `doc_id` from (raw sha + extractor version) or state that ids are only stable within one build `build_id` |
| A-02 | **High** | B ignores whole-source `SRC\|*` issues (exact-key lookup); C emits them for partial-scope amendments and claim failures | `pipeline_v7._finish` `I.get(r)`; `validity.py` `_key(sid, None)` | Contract: `SRC\|*` matches every provision of SRC; C `interface.certification_blockers` already does via `issues_for`; B must use it or implement wildcard; add a cross-branch test |
| A-03 | **High** | Paragraph/front-matter key divergence: C keys `SRC\|Paragraph N` / `SRC\|Front matter`; B uses `None`/`SRC\|*` | `validity.py` conflict loop; `interface.article_id`; B `locators.article_key` | One shared key function in the contract (grammar for paragraphs and front matter); C maps web-page issues to `SRC\|*` until B supports paragraph keys |
| A-04 | **High** (before users) | B's `certified: True` = coverage-complete on candidate, unverified sources; source status never checked | `pipeline_v7.certify`, unused `source_status`; 82/218 complete | Rename to `coverage_complete`; certification requires `approved` sources and an approved provision map; never show "certified" to users |
| A-05 | Med | Export bound to one DB md5; B never checks; committed export is wrong for D10 build (keeps ER\|1 extraction issue) | E7; `_meta.database_md5` | B refuses an export whose `database_md5` ≠ its DB, or C ships one export per build (`build_id` in name) |
| A-06 | Med | Single export file overwritten by `--write`; staleness (register edits, `as_of` passes an effective date) only caught by C's test 124 | `validity.EXPORT`, `generated_for_date` | Contract: export carries `register_version`, `as_of`, `valid_until` (next known effective date) and `build_id`; B rejects stale exports |
| A-07 | Med | Issues not version-scoped; C picks current version by effective date, B by `MAX(seq)`; no `seq` in export | `current_versions`, B `LATEST` SQL | Each issue carries `version_id`; export lists `seq`; contract fixes one selection rule, plus a check that both sides pick the same version |
| A-08 | Med | Issue ids not stable/contracted; drop-in breaks B tests | E2 | Contract fixes the id scheme; publish a mapping G1/G3/G3-missing → new ids; B tests assert on `kind`+provision, not id |
| A-09 | Med | Conflict detection only among hand-registered claims; external sources cannot be keyed; B cannot show both values | `claims.check_claims`; `CL-DEREG-DEADLINE-WEB` `in_knowledge_base: false` | Run claims over `fact_inventory` per topic; contract conflict object: topic, values[], per-value source/version/locator/url/evidence date; B must show all values |
| A-10 | Med | "missing" provisions (DL8 54 (bis)) never fire in B: no topic maps to them | B `CL_provision_map_v7.json` has 0 refs to 54 (bis) | Contract: `missing` issues come with topics/keywords; B maps them, or flags any question whose topic touches an amended article |
| A-11 | Med | C-3 open: DL8 copy outdated for 48/74/79 (bis)/54 (bis); consolidated source URL unresolved | register candidate `url: null` | Founder decision on an approved capture; until then those topics stay `source_validity_unresolved` |
| A-12 | Low | Contract still v0.1 "proposed" on an old branch name; v1.0 referenced only in untracked `interface.py`, whose handoff doc does not exist | docs/rag listing | Publish contract v1.0 as a document, versioned and signed off by B |
| A-13 | Low | C-7 path differs from request; build is git-ignored and corpus-only | D10 report | Agree the build path and naming (`build_id`); ship its validity export and diff together |
| A-14 | Low | C-5 headings available only through CLI/import | `rag_c headings` | Commit a headings JSON per build for B |
| A-15 | Low | Which DB is authoritative is unclear (`data/CL_compliance.sqlite3` md5 `c3316022…` ≠ `26e202b8…` in export and §10) | E8 | Contract names the DB by md5/`build_id`, not by path |
| A-16 | Low | `current` pick falls back to `vs[-1]` (register order) when no dates are stated | `validity.py` | Fall back to explicit `seq`, never list order |
| A-17 | Info | 4 recorded citations fail the quote check | E6 | Investigate as part of answer QA (B) |

## Contract v1.0 must include
1. **Provision id:** one key function shared by both sides: `SRC|N[ (bis|ter|quater)]`, `SRC|Paragraph N`, `SRC|Front matter`, `SRC|*` (matches every provision of SRC). Article identity is independent of `part`.
2. **Build identity:** `build_id` (DB sha256), extractor version, passage count. A statement that `passage_id` is stable **only within one build**. Diff reports keyed by (doc, locator).
3. **Citation metadata:** `source_id`, `version_id`, `article_id`, `locator`, `passage_text_sha256`, `doc sha256`, URL, `build_id`. Resolution order: id within the same build, otherwise (article_id, version_id, text hash).
4. **Versions:** `seq`, stated effective date and its evidence level, `kb_status`, `verification_status`, extraction label, `approved`. One agreed rule for choosing the current version, with a divergence check between the two sides.
5. **Validity issues:** stable id scheme, closed `kind` list (outdated, repealed, missing, conflict, extraction, unverified, partial-scope), `version_id`, provisions, instruments plus effective dates, message. Rule: any issue on a needed provision blocks certification, and wildcards apply.
6. **Conflicts:** topic, every value with source/version/locator/URL/observed date, plus the rule "show all values, a reviewer decides". External (not-ingested) sources allowed.
7. **Freshness:** `register_version`, `as_of`, `valid_until`, `database_md5`/`build_id`. The consumer must refuse a mismatched or expired export.
8. **Status vocabulary:** `candidate | verified | approved` (sources) kept separate from B's `coverage_complete`. "Certified" or "approved" only when the sources and the provision map are approved by a named reviewer.
9. **Completeness:** what "complete" means (all required provisions present, no blocking issue, sources approved), and how `missing` provisions and partial-scope amendments enter B's required set.
10. **Change control:** semver. A grammar, key or id change is a major version, announced in writing. A cross-branch compatibility test (B's pipeline run on C's export) runs before any merge.
