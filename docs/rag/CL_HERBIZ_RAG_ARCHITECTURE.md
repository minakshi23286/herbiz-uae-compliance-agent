# HerBiz: Compliance Agent — RAG and source-intelligence architecture (v2)

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** 17 Oct 2026 (updated after the independent QA round) · **By:** Workstream C, branch `ws-c-source-intelligence` (contains `ws-c-rag-foundation` and `ws-c-d10-article1`; nothing merged) · **Supersedes** `CL_RAG_ARCHITECTURE_WS_C.md` (v1, kept unchanged) · **Not legal or tax advice.**

Legend: **[T]** implemented and tested · **[D]** designed, not implemented · **[B]** blocked (reason given).

## 1. Layers
```
            ┌────────────────────────── SOURCE INTELLIGENCE (Workstream C) ──────────────────────────┐
 official   │ discovery ─► candidate register ─► (approved) collection ─► lock + raw ─► extraction    │
 websites ──┤   [T]           [T] v1.5.0              [T] kb collect,         [T]       [T] pypdf    │
            │                                         guarded --allow-network            + D10 [T]   │
            │ monitor ─► alerts / report [T]          amendment map [T]   claims+conflicts [T]       │
            │ (fixture / Firecrawl import /           extraction validation [T] (structure +         │
            │  guarded local fetch)                   second extractor)                              │
            │                    └──────► VALIDITY EXPORT knowledge_base/CL_source_validity.json [T] │
            └───────────────────────────────────────────┬───────────────────────────────────────────┘
                                                        │ contract v1.0 (rag_c.interface) [T]
            ┌──────────────────────── RETRIEVAL + ANSWERS (Workstream B) ────────────────────────────┐
            │ passages (SQLite FTS5) ─► retrieval v4…v7/C1 ─► answer ─► citation check ─► guard     │
            │                     reads validity: no certification on outdated/conflict/missing      │
            └────────────────────────────────────────────────────────────────────────────────────────┘
                     traceability: answer citation ─► passage ─► document ─► raw sha256 ─► register
                     version ─► validity issues  (rag_c trace) [T]
```

## 2. Components
| # | Component | Where | Status | What it guarantees |
|---|---|---|---|---|
| 1 | Source discovery | `rag_c/discovery.py`, `rag_c discover` | [T] tests 109, 114, 115 | new official links on listing pages become proposals; never activated; `--write` makes a new register version |
| 2 | Candidate register | `knowledge_base/CL_source_register.json` (v1.6.0) | [T] validator (tests 94–95, 130) | 4 sources, 5 captured versions, 52 candidates (incl. 29 landscape entries), 14 instruments, 9 claims, 9 gaps; every date ISO or null with evidence; a URL-less candidate must say where it was seen; candidates `activated: false` |
| 3 | Provenance and versions | lock (sha256) + `data/raw/` + `source_versions` (immutable trigger) + register versions | [T] `rag_c hashes`, dry run 371/371 | any passage traces to the exact bytes collected and the URL |
| 4 | Collection | `kb collect` | [T] guarded (tests 86–93): test-workspace default, refuses the authoritative DB, needs `--allow-network` | no silent network use; no write to the authoritative DB |
| 5 | Extraction | `kb.extract_pdf` (+ D10 heading rule) | [T] tests 103–105 | ER Article 1 is its own passage in a D10 build; the DL8 extraction is unchanged |
| 6 | Article-level extraction validation | `rag_c/extraction_check.py` | [T] tests 127–129, 150 | locator grammar, numbering gaps, empty passages, page order; pdftotext cross-check with number sets **and counts**, excusing only real footnote markers: 0 unexplained mismatches in 316 of 317 articles; ER v1 Art. 70 'Article 8 0' (split number) found; a corrupted number is caught |
| 7 | Amendment and supersession map | `rag_c/amendments.py` | [T] tests 117–119, 144–147 | per version: included and missing in-force instruments (an unknown effective date counts as possibly in force), affected articles from the register **and from the documents' own footnotes** (`footnote_index`), type-exact instrument matching, newest by stated effective date |
| 8 | Source conflict detection | `rag_c/claims.py` | [T] tests 120–122 | topic-level value claims; quote and value checked in the cited passage; different values = conflict (never resolved automatically) |
| 9 | Validity export | `rag_c/validity.py` → `CL_source_validity.json` (schema 1.1) | [T] tests 123–124, 145–149 | B-compatible `SOURCE\|ARTICLE` keys, `SRC\|*` for whole sources and web pages; kinds outdated / repealed / missing / conflict / future_text / extraction / unverified; every issue carries version_id; current version per source with its basis; coverage disclaimer |
| 10 | Citation integrity | `rag_c/citations.py` | [T] test 125 | quote found (same normalisation as B's `answer.check`), version current?, source approved?, validity issues; `certifiable` only if approved and no issue |
| 11 | Source-to-answer traceability | `rag_c trace` | [T] test 126 | 259 recorded answers / 639 citations traced on 17 Oct: 635 quotes found, 4 not; 2 answers rest on repealed DL Art. 79 (bis); **0 certifiable** (nothing approved) |
| 12 | Candidate / verified / approved separation | register `kb_status`, `verification_status`; validity `approved_versions` | [T] validator + export | today: 5 candidate, 0 verified, 0 approved |
| 13 | Source-change monitoring | `rag_c/monitor.py`, `rag_c monitor` | [T] offline (tests 106–116, 131–140; hardened after QA) · [D] scheduling · **not run live, not scheduled** | see `CL_HERBIZ_SOURCE_MONITORING_DESIGN.md` |
| 14 | Interface for B | `rag_c/interface.py` | [T] tests 146, 148–149 | contract v1.0 (`CL_HERBIZ_RAG_INTEGRATION_HANDOFF.md`): stable article ids, provision status, certification blockers (approved + current + no issue), stale-export refusal, build-independent `resolve_by_article` |
| 15 | Human-readable docs from data | `rag_c render` | [T] | register and validity matrix regenerate from JSON |
| 16 | Reviewer approval workflow | `engine.review_source` / `review_interpretation` (existing) | **[B] D3**: no qualified UAE tax reviewer named | nothing can become approved |
| 17 | Current DL text | collection of the consolidated DL 8/2017 incl. DL 16/2025 | **[B] G3**: file not located; collection needs approval | DL Art. 48, 74, 54 (bis), 79 (bis) flagged |
| 18 | Deregistration deadline | — | **[B] G1**: ER (EN+AR) 20 vs FTA page 30 business days; FTA enquiry drafted, not sent | agent must not state a deadline |
| 19 | Arabic official text in the KB | — | [D] only (text layer scrambles letters; needs page rendering or a different extractor); reuse terms D4 | KB is English (unofficial translation) |
| 20 | Live monitoring schedule | launchd template / Claude scheduled task | [D] templates only, not installed | — |

## 3. Data contracts
- **Provision id:** `SOURCE|ARTICLE` (`FTA-VAT-DL8|48`, `FTA-VAT-ER|14 (bis)`); `SOURCE|Paragraph N` for web pages; `SOURCE|*` for the whole source. Stable across builds. **Passage ids are not stable** across builds (they include seq).
- **Version id:** `SOURCE@vN`, collection order. "Current" is chosen by the latest effective date stated in the file, falling back to sequence when no dates exist. The basis is recorded in the export.
- **Status vocabulary:** `candidate → verified → approved`, with `superseded` / `rejected` (existing `source_versions.status`). Only `approved` with no validity issue is certifiable.
- **Evidence levels** (register): observed, observed_listing_only, observed_in_file, snippet_only, supplied, unresolved.

## 4. What did not change (protected)
The authoritative DB (md5 `26e202b8…`), ledger, raw files, lock, manifest, frozen evaluation sets, B's files and branch, the A/CX demo files and the BOS are all unchanged. Every C build and tool opens databases read-only or writes to new files only.

## 5. Known limits
- **Coverage claim:** we know of 4 captured sources and 23 researched candidates. This is **not** complete legal coverage (see the landscape section of the register and the overnight report).
- **Instrument article lists:** incomplete for 6 of 12 instruments. The validity export then flags the whole source (`partial-scope`) only for versions that *miss* such an instrument. ER v3 misses none.
- **Monitor heuristics:** cosmetic vs substantive depends on normalisation; a reworded but equivalent clause is "substantive" (safe direction).
- **Second-extractor rule:** a number counts as layout noise only when it differs by a **footnote marker of that document glued to it** (`4615` = footnote 46 + `15`). Page numbers are no longer excused (QA E2). A legal number that equals a footnote marker plus a digit pair could still be excused; this is rare and documented.
- **Footnotes inside passages (G8)**, **3,000-character parts that cut mid-word**, **split words and numbers**: documented, not fixed (they touch extraction; proposal D14).
- **Guards** recognise protected databases by name in any checkout and by hard link in sibling checkouts; the **main checkout still runs the old, unguarded code until the merge** (QA D4). Schema-level immutability gaps (INSERT OR REPLACE on audit_events; passages not frozen) need a schema change, which is not allowed: proposal only (QA D2/D3).
