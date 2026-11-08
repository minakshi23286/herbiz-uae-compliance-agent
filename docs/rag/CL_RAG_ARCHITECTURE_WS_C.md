# HerBiz: Compliance Agent — RAG architecture and Workstream B/C interface contract

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Prepared:** 16 Oct 2026, Workstream C (Claude Code), branch `ws-c-rag-foundation` · **Status:** drafted, not reviewed · **Not legal or tax advice.**

This describes the RAG pipeline **as built** (checked against code and a read-only database copy on 16 Oct 2026), what Workstream C added, and the agreed boundary with Workstream B. Each section marks what exists, what is missing, and what C can improve without touching B's retrieval files.

## 0. Ownership at a glance
| Layer | Files | Owner | C may change? |
|---|---|---|---|
| Collection, extraction, passages, FTS | `compliance_agent/kb.py`, `sources.py`, `store.py` | shared foundation (C for ingestion) | `kb.py`: CLI entry point and safety checks only (founder instruction, 16 Oct). Extraction changes are **proposals** (§3) |
| Source governance | `knowledge_base/CL_source_register.json`, `compliance_agent/rag_c/` | **C** | yes |
| Retrieval | `llm_lab/retrieve.py`, `concepts.py`, `retrieval_metrics.py`, `run.py` | **B** | no |
| Answering and checks | `llm_lab/answer.py`, `budget.py`, `report.py`, `freeze.py`, `fake.py` | B / closed experiment | no |
| Demo | `ask.py`, `ui.html`, `web.py` | A (closed) | no |
| DB safety | `dbsafety.py` | A, extended by C (approved P5) | yes, additions only |

## 1. Source discovery
- **Exists:** a hand-curated manifest (`knowledge_base/CL_source_manifest.json`, 6 entries / 4 source ids) and an allowlist of official hosts in `kb.py` (`tax.gov.ae`, `mof.gov.ae`, `u.ae`, `elaws.moj.gov.ae`, `uaelegislation.gov.ae`).
- **Added by C:** a versioned register (`CL_source_register.json`). It describes every source and captured version and lists researched sources under `candidates[]` (`activated: false`, `kb_status: not_ingested`). The register **does not replace the manifest**: `kb` still reads only the manifest and lock.
- **Missing:** a routine discovery check (is the FTA VAT legislation page linking a newer file?). A proposed rule is in §9.

## 2. Provenance and version control
- **Exists:** originals are stored unchanged at `data/raw/<source_id>/<sha16>.<ext>`. The lock (`CL_collected_lock.json`) records sha256, bytes, URL and time. `source_versions` rows are immutable (trigger `source_text_frozen`). `audit_events` is append-only (triggers `audit_no_update`, `audit_no_delete`). Status values are `candidate | approved | rejected | superseded`.
- **Checked by C on 16 Oct 2026:** 5/5 locked files match their sha256 (`rag_c hashes`). The 5 versions are all `candidate`, with 0 reviewer sign-offs.
- **Found:** 4 HTML captures of the FTA registration page are in `data/raw/FTA-VAT-REG-PAGE/` but **not in the lock** (`031e22a9…`, `437f6925…`, `649c1050…`, `c2bb7d89…`). They are left untouched and reported by `rag_c hashes` as `raw_files_not_in_lock`.
- **Found (incident evidence, §10):** the registration web page returns **different bytes on every fetch**. A raw-HTML sha256 therefore cannot detect content changes for web pages. Change detection must use the normalised extracted text (`normalized_hash`, which `source_versions` already stores).
- **Gap C3 (newest version):** B's retrieval treats the highest `seq` as newest. The register now records each version's amendment chain *as stated in the file*. The latest effective dates stated are ER v1 = 2024-11-15, v2 = 2025-09-29 and v3 = 2026-10-01, so **sequence order equals effective-date order today**. `rag_c validate` warns if that ever stops being true. These dates are `observed_in_file`, not verified against the Official Gazette.

## 3. Extraction
- **Exists:** `pypdf 6.8.0` for PDFs and `html.parser` for HTML. Running headers are removed, footnote-merged headings are repaired (`Article 8337` → Article 83), and empty pages are recorded, never filled.
- **Found by C (gap G2):** in all 3 ER versions, **Article 1 (Definitions) has no passage of its own**. Its heading is extracted as `Article 1 1` (footnote marker glued on, then a line break) and stays inside `Front matter, p. 1`/`p. 2`. Retrieval asking for "ER Article 1" cannot find it by locator. The DL8 file is not affected (Article 1 present, 4 parts).
  - *Proposed fix (not done; extraction lives in `kb.py`, outside the approved edit scope):* in `extract_pdf.heading_no`, accept `Article N <footnote-digits>` on its own line as a heading, as is already done for `Article 8337`. Build into a **new** DB and diff with `rag_c dryrun`: expected change is ER Article 1 split out of front matter, with no other passage text changed.
- **Not checked:** the extracted text has not been compared with the PDFs by a person. Every passage stays `UNVERIFIED_EXTRACTION`.

## 4. Article-level structuring
- **Exists:** split by Article (PDF) or Paragraph (HTML). Long articles are split into `part N`. Locators look like `Article 13, p. 11` / `Article 1, pp. 2-7, part 3` / `Paragraph 4` / `Front matter, p. 1`.
- **Coverage on 16 Oct 2026 (`rag_c inventory`):**

| Version | Passages | Distinct articles | Range | Missing numbers | Bis | Notes |
|---|---|---|---|---|---|---|
| FTA-VAT-DL8@v1 | 93 | 86 | 1–85 | none | 79 (bis) | |
| FTA-VAT-ER@v1 | 89 | 76 | 2–75 | **1** | 3 (bis), 14 (bis) | Art. 1 inside front matter |
| FTA-VAT-ER@v2 | 89 | 76 | 2–75 | **1** | 3 (bis), 14 (bis) | same |
| FTA-VAT-ER@v3 | 91 | 76 | 2–75 | **1** | 3 (bis), 14 (bis) | same |
| FTA-VAT-REG-PAGE@v1 | 9 | — | Paragraphs 1–9 | — | — | |

- **Version differences (`rag_c compare`, reusing `KnowledgeBase.compare`; advisory only):** ER v1→v2: 4 substantive units (Art. 59, 60, 66 and the front matter), 61 cosmetic. ER v2→v3: 15 substantive (Art. 4, 29, 31, 41, 51–57, 59, 60, 66 and the front matter), 47 cosmetic. For the in-scope registration and deregistration articles (ER 6–8, 14, 14 (bis), 15–18), the machine comparison found **no substantive change** between v1, v2 and v3. A reviewer still has to confirm this.

## 5. Indexing
- **Exists:** SQLite FTS5 (`porter unicode61`) over `locator` and `text`. 371 FTS rows = 371 passages (checked).
- **Added by C:** `rag_c dryrun` rebuilds the whole corpus offline, in a temporary folder, from **copies** of `data/raw/` and the lock, with network refused. It then compares every passage (doc, seq, locator, sha256 of text) with a reference copy. **Result 16 Oct 2026: reproducible, 371/371 identical, integrity ok.** `--out` keeps the build only in a new file. It refuses existing files and the authoritative path.

## 6. Retrieval (Workstream B — described, not changed)
- `retrieve.search` v4 (frozen `a2ac879`): BM25 top-6 over the newest non-rejected version of each source (`MAX(seq)` where `status != 'rejected'`), plus intent provisions (`concepts.INTENT_PROVISIONS`) and 3 rarity-weighted title matches. Read-only connection.
- The offline gate on unseen v3 is **blocked**: 44% all-required (R1). The diagnosis belongs to B (handoff §6).
- **What C can supply without touching B's code:**
  1. The G2 fix (Article 1 locator), as a new DB build B can point at.
  2. The register's effective-date evidence. B can then replace `MAX(seq)` with a verified-date rule later, if a reviewer wants that.
  3. The coverage table above, so B's provision maps can be checked against real article numbers.
  4. Article headings per version (register `scope_topics`) for the registration and deregistration articles.

## 7. Citation verification
- **Exists (B / experiment):** `answer.check` confirms every quote is found in the cited passage and every number appears in the sources. The demo guard (`ask.py`) checks that the intent's primary provisions are present. Over 98 recorded answers it produced 0 false "complete" verdicts (tests 84–85).
- **C's contribution:** a citation is traceable end to end. Locator → `passages.passage_id` → `documents.sha256` → lock entry → raw file (`rag_c hashes`) → register version (URL, amendment chain, verification status). `rag_c validate` fails if any captured version's hash, URL or raw path disagrees with the lock.
- **Missing:** a reviewer-signed reading per article (D3). Until then every citation is "candidate source, unverified extraction".

## 8. Evaluation
- **Exists:** 3 frozen sets (v1–v3, sha256 locks OK; all now development data), the frozen retrieval-v4 gate evidence, a 23/23 scenario evaluation on synthetic test rules, and an 83-test suite (now 100 with C's tests 86–102).
- **Not changed by C:** no evaluation re-run, no fixture edited, no ledger read except by existing tests.
- **Needed:** a new independent question set, written before the next retrieval change, with reviewer-approved expected articles (D3).

## 9. Source updates (proposed governance, needs founder decision)
| Step | Rule | Tool |
|---|---|---|
| Watch | Monthly, and on any FTA announcement: open the FTA VAT legislation page and compare linked file names and dates with the register | manual / `rag_c validate` |
| Capture | Only with founder approval: `kb collect --db <copy> --allow-network`, into a copy first | `kb` (guarded) |
| Verify bytes | lock sha256 vs raw file | `rag_c hashes` |
| Compare | new vs current version, article by article | `rag_c compare` |
| Rebuild check | offline rebuild reproduces | `rag_c dryrun` |
| Record | new register version (`register_version` + `changes[]` entry), never rewriting old entries | edit + `rag_c validate` |
| Approve | named qualified reviewer approves the version, then the old one becomes `superseded` | `engine.review_source` (D3) |
| Publish | hashes and links only until reuse terms are confirmed | D4 |

## 10. Incident recorded during this work (16 Oct 2026, ~22:38 +04:00)
To prove the new guard tests fail on unguarded code, C ran them against an export of `main` (`fcdfbb7`) in a scratch folder. On that old code, test 86 (`kb collect --db <stand-in>`) and test 88 **ran a real `kb collect`**. They fetched the 5 manifest URLs from tax.gov.ae twice (eLaws failed) into the scratch folder only. This network collection had not been approved.
- **Effect:** no protected file changed. The original database md5 is still `26e202b8…`, and the original lock and raw files are unchanged (checked).
- **Observation:** the 4 PDFs were byte-identical to the locked copies; the registration HTML differed on each fetch.
- **Prevention:** any future run of old code mocks `http_fetch`. The new `kb collect` needs `--allow-network`, and test 88 fails if the network is touched.

## 11. Workstream B / C interface contract (proposed v0.1)
**C provides** (ingestion side), in any database B is pointed at:
- `passages(passage_id, doc_id, version_id, seq, locator, page_start, page_end, text, label)` as in `store.py`. `passage_id = <doc_id>#<seq:04d>`. `doc_id = <source_id>:<sha256[:12]>`.
- Locator grammar: `Article <N>[ (bis|ter|quater)], p. <P>` or `pp. <P1>-<P2>`, optional `, part <K>`; `Paragraph <N>`; `Front matter, p. <P>`. A change to this grammar is a contract change: a new contract version, announced to B.
- `source_versions.status` is one of `candidate | approved | rejected | superseded`, and `seq` increases with collection order. C will not reorder `seq`.
- Every new build goes to a **new** DB file, with a dry-run report showing which passages changed. Existing passage ids are never reused for different text.

**B provides** (retrieval side): read-only access only (`connect_ro`); no writes to any C build. Any change to version selection (`MAX(seq)` rule) is announced to C, and B's provision maps cite locators in the grammar above.

**Shared files neither side edits alone:** `kb.py` (C: CLI and safety only on `ws-c-rag-foundation`; B: may edit search). Both branches are kept separately; conflicts are documented for a founder-approved merge, never resolved by discarding either side.
