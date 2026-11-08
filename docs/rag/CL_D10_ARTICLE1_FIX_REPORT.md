# HerBiz: Compliance Agent — D10 report: ER Article 1 extraction fix

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** 16 Oct 2026 · **Branch:** `ws-c-d10-article1` (cut from `ws-c-rag-foundation` at `57d12c1`; not merged) · **Approved:** founder, 16 Oct 2026 ("isolated Article 1 extraction fix using a new disposable database") · **Status:** built and verified on disposable databases; **not integrated** · **Not legal or tax advice.**

## What changed
| File | Change |
|---|---|
| `compliance_agent/kb.py` | `ARTICLE_RX` gains an optional group 4 for a footnote marker after a title-less heading (`Article 1 1`). New `footnote_on_page()`. `extract_pdf` accepts that heading only if the footnote line ("1 Article amended as per …") is on the same page. Groups 1–3 and every other heading rule are unchanged. No change to search, ranking or the CLI |
| `compliance_agent/rag_c/dryrun.py`, `__main__.py`, `__init__.py` | new `diff_builds` / `rag_c diff BUILD_DB --db REF`: content diff matched by (doc, locator), because seq and passage ids shift |
| `tests/test_ws_c_d10_article1.py` (new) | tests 103–105 |
| `tests/test_ws_c_rag_tools.py` | test 101 now checks build-against-build reproducibility (the reference copy is pre-D10) and blocks the network at `urlopen` |

## Result (disposable build `data/CL_rag_c_d10_build.sqlite3`, sha256 `a84d9806…`, git-ignored)
| Check | Result |
|---|---|
| Passages | 371 → 371; FTS rows 371; integrity ok |
| ER v1 / v2 / v3 | Article 1 now its own passage `Article 1, pp. 1-2` in all three; articles 1–75 complete, none merged |
| What moved | per ER document: `Front matter, p. 2` (old) → `Article 1, pp. 1-2` (new); `Front matter, p. 1` shortened (the Article 1 opening moved out). Same text overall (whitespace-insensitive check) |
| Unchanged | 365 of 371 passages identical by (doc, locator, text hash); the DL8 extraction is identical to the reference |
| Reproducible | two offline rebuilds identical (test 101) |
| Retrieval smoke check (unchanged v4 code, read-only, one question about "Legal Representative") | old build cites ER `Front matter, p. 2`; D10 build cites ER `Article 1, pp. 1-2` first. One query, not an evaluation |
| Tests | **103/103 pass** |
| Originals | authoritative DB md5 `26e202b8…` unchanged; raw files, lock, manifest and frozen sets untouched |
| Evidence | `docs/CL_evidence/ws_c/CL_d10_build_diff_2026-10-16.json`, `CL_d10_build_inventory_2026-10-16.json` |

## Limits and integration notes (for the founder and Workstream B)
- The build is **corpus-only**: no draft interpretations (the original has 2) and no copy of the original audit history. It is fit for retrieval experiments only, not as an app database.
- **Passage ids shift for ER documents.** Anything that stores ER passage ids (recorded answers in the ledger, frozen evidence) will not match a D10 build. Match by `(source_id, locator)`.
- The ER Article 1 passage starts "Article 1 1 Definitions …". B's `article_heading()` would read its title as "1 Definitions…", a cosmetic point for B.
- The rebuilt corpus still has the **outdated DL copy (G3)** and the **unresolved deadline conflict (G1)**. D10 does not fix either.
- **Conflict risk:** `kb.py` line ~160 (`ARTICLE_RX`) and the `extract_pdf` loop. B's branch has not changed these lines as of 16 Oct ~23:20. If it does, keep both changes at merge time (founder decision).
- **Not done (needs approval):** integration into any shared database, rebuild of the test workspace, merge.
