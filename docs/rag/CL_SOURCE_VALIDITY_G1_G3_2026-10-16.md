# HerBiz: Compliance Agent — Source-validity decision report (G1 deregistration deadline, G3 outdated VAT law, download incident)

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** Fri 16 Oct 2026 · **By:** Workstream C (Claude Code), branch `ws-c-rag-foundation` · **Status:** drafted; read-only investigation; nothing activated, collected or merged · **Not legal or tax advice. No deadline is chosen here.**

## Decisions for you (short)
| # | Decision | Recommendation |
|---|---|---|
| 1 | G1: which deregistration deadline may the agent state? | **None yet.** Until a qualified reviewer decides (D3), the agent shows both statements with their sources and says "check with the FTA or a tax agent". Practical guidance may say "the earlier of the two (20 business days) is the safe planning date", labelled as a precaution, not as the law |
| 2 | G1: ask the FTA? | Yes. Send one written question to the FTA (call centre or EmaraTax enquiry) quoting both texts. I can draft it; you send it |
| 3 | G3: collect the current consolidated VAT law? | Yes, after you locate the file by hand (it was not found by tools). Then approve one guarded `kb collect --allow-network` of that single URL into a copy |
| 4 | G3: until then | The agent must flag answers that rely on DL Art. 48, 54, 74 or 79 (bis) as "may be out of date (DL 16/2025 in force 1 Jan 2026)". Registration and deregistration articles are **not** affected |
| 5 | Arabic official text of ER Art. 14 | Approve reading the FTA's Arabic ER file (`…09-2026-arabic.pdf`) once, read-only, to see whether the official Arabic says 20 business days. This is a new download, so it needs your OK |

## 1. G1 — deregistration deadline: 20 vs 30 business days

### 1.1 The two statements, traced
| | Statement A: **20 business days** | Statement B: **30 business days** |
|---|---|---|
| Exact text | ER Art. 14(1): the Registrant "must apply … within 20 (twenty) Business Days of the occurrence of any of them" (the cases in the Decree-Law, i.e. DL Art. 21) | FTA service page, Terms & Conditions: where deregistration is mandatory, "the deregistration application must be submitted within 30 business days" of the obligation arising |
| Instrument | Cabinet Decision No. 52 of 2017 (Executive Regulation), Art. 14(1). Footnote on the article: "Article amended as per Cabinet Decision No. 100 of 2024" | FTA web page "VAT deregistration" (service description). Not legislation |
| Where seen | `FTA-VAT-ER@v3` raw PDF p. 12 (sha256 `7e0882e3…`), file of 09-2026 (issued 2026-09-01, FTA-published 2026-09-10). Same wording in `@v1` p. 12 and `@v2`. The live URL served the identical bytes on 16 Oct (the research cache file has the same sha256) | https://www.tax.gov.ae/en/services/vat.deregistration.aspx and the Arabic page `/ar/services/vat.deregistration.aspx` ("خلال 30 يوم عمل") |
| Dates | Consolidation includes amendments up to CD 149/2026 (effective 2026-10-01). Art. 14 last amended by CD 100/2024 (effective 2024-11-15), as stated in the file | "Page last updated: Thursday, September 24, 2026" (EN and AR) |
| Language status | English text self-describes as "not an official translation"; the official Arabic ER text was **not read** | FTA's own English and Arabic web pages |
| Evidence level | observed_in_file (raw PDF, read offline 16 Oct) | observed (re-read by me with WebFetch on 16 Oct, both languages) |

### 1.2 Cause analysis
| Possible cause | Evidence | Verdict |
|---|---|---|
| Extraction error in our knowledge base | Raw PDF text (pypdf, page 12) reads "20 (twenty) Business Days", with both digits and words. The KB passage matches | **Ruled out** |
| Translation error on the FTA website | The Arabic page also says 30 working days | **Ruled out** for the web page |
| Translation error in the English ER | The English ER is an unofficial translation; the Arabic ER was not read | **Open.** Settle by reading the Arabic ER file (decision 5) |
| A recent amendment not yet reflected | VATP040 (on CD 100/2024) lists Art. 14 changes to clauses (4), (5) and (9) and new Art. 14 (bis), not clause (1). ER@v3 consolidates up to CD 149/2026 and still says 20. Secondary summaries of CD 149/2026 do not mention deregistration. DL 16/2025 does not touch DL Art. 21–24 (VATP046) | **No evidence found.** Not ruled out: CD 149/2026's own text was not located |
| Different legal circumstances (two different deadlines) | Both statements cover the same case: a mandatory application after a DL Art. 21 trigger | **Unlikely** |
| Web page conflating its own processing time | The same page gives the FTA's processing time as 30 business days, and a further 30 after resubmission; the registration page gives about 20 days of processing | **Plausible but unproven** |
| Secondary sources | Every adviser page found gives 20 business days under ER Art. 14(1); none gives 30 as the application deadline | supports A; low weight (not official) |

**Conclusion:** the legislation text we hold (unofficial English ER, current consolidation) says 20 business days. An official FTA guidance page says 30. The hierarchy of norms favours the Cabinet Decision over a web page, and the FTA's own terms say its web content is "as is". But we have not read the official Arabic ER, and the FTA is the body that applies the rule. **The evidence is not sufficient to choose a deadline.** G1 stays open for the reviewer.

### 1.3 What else G1 touches
- **Frozen evaluation sets (not edited):**
  - `fixtures/CL_llm_eval_unseen_v3.json` requires "20 business days" in a deregistration answer (`must_include`, rationale "within 20 business days").
  - `fixtures/CL_llm_eval_questions.json` has a registration question whose `must_not_include` lists "20 business days".
  - If the reviewer decides on 30, or "both", these expectations are wrong. Record that as a reviewer note; do not edit frozen files.
- **Workstream B's v4 set** (on B's branch; read-only check): has a "deregistration on closing business" item citing DL Art. 21 and ER Art. 14.
- **Penalty context (secondary, not verified):** late deregistration application, AED 1,000 then AED 1,000 per month, up to AED 10,000. The current penalty table (CD 40/2017 as amended by CD 129/2025, effective 2026-04-14) was not checked for this item.

## 2. G3 — outdated VAT Decree-Law

### 2.1 What we have vs what is current
| | Our copy `FTA-VAT-DL8@v1` | Current law |
|---|---|---|
| File | `…/Legislation/2025/Federal-Decree-Law-No-8-of-2017-and-amendments.pdf`, sha256 `37159c64…`, 40 pages, collected 2026-10-16 04:58. The live URL still serves the identical bytes (research cache, same hash) | Consolidated English copy including DL 16/2025: **not located** |
| FTA listing | Legislation **Archive**; issue 2024-10-30, published 2025-07-07 | Not found on page 1 of the live listing; pagination not reachable with tools |
| Amendments included (front matter) | DL 8/2017 (eff 2018-01-01), DL 18/2022 (eff 2023-01-01), DL 16/2024 (eff 2024-10-30) | + **Federal Decree-Law No. 16 of 2025, effective 2026-01-01** |
| Evidence for DL 16/2025 | — | MoF news, 2025-12-03 (re-checked by me); FTA Public Clarification VATP046 (issued 2026-09-04), pp. 1, 6–10, read offline |
| Issue date of DL 16/2025 | — | not seen officially; secondary sources disagree (1 Oct / 14 Nov / 25 Nov 2025). **Left null** |
| Language | unofficial English translation ("This is not an official Translation") | official text is Arabic (Official Gazette); not located |

### 2.2 Provisions in our knowledge base that may be outdated (DL 16/2025, per VATP046)
| DL article | Change from 1 Jan 2026 | Our passage(s) | Effect on HerBiz scope |
|---|---|---|---|
| Art. 48(1) Reverse charge | No longer need to issue a Tax Invoice to yourself for imported Concerned Goods/Services; keep supporting documents instead. Applies to imports on or after 2026-01-01 | `FTA-VAT-DL8:37159c643e64#0054`, `#0055` (Article 48, pp. 23–25) | Outside registration scope; matters for non-resident or import questions (B's v4 cites Art. 48) |
| Art. 74(3) Excess recoverable tax | New five-year limit to request a refund, counted from the end of the tax period of the excess | `#0081` (Article 74, p. 35): no five-year limit in our text | outside registration scope |
| Art. 54 (bis) (new) | Input tax deduction rejected where the supply chain is linked to tax evasion; verification duty (FTA Decision 13/2026) | **absent** | outside registration scope |
| Art. 79 (bis) (repealed) | Statute of limitation moved to the Tax Procedures law (DL 28/2022) | `#0087` (Article 79 (bis), pp. 38–39) is **still present**: it would be cited as live law | outside registration scope, but a wrong-law citation risk |
| Art. 13–24 (registration, groups, exception, deregistration) | **not amended** by DL 16/2025 | DL8@v1 Art. 13–24 | **in scope: not affected** |

**Correction to earlier records:** the overnight report and register v1.1.0 said DL 16/2025 also changed Art. 1, 55, 65, 70 and 76. VATP046 shows those were changed by **DL 16/2024** (effective 2024-10-30), which our copy already contains: its Art. 1 has the Electronic Invoice definitions, and Art. 55, 65 and 70 mention the Electronic Invoicing System. Corrected in register v1.2.0 and in the reports (erratum).

### 2.3 Executive Regulation
`FTA-VAT-ER@v3` is the current file (live listing, 16 Oct). The ER passages that cite DL Art. 48 or 74 (ER Art. 27, 48, 55 part 2, 59 part 1, 67) are current ER text. They now sit next to an outdated DL Art. 48/74 in our knowledge base.

## 3. Unapproved download (16 Oct 2026, 22:38 +04:00) — evidence record
| Item | Detail |
|---|---|
| What ran | `python3 -m unittest tests.test_ws_c_db_safety` against an export of `main` (`fcdfbb7`, unguarded `kb`) in `…/scratchpad/mut/`. Test 86 (subtest `collect`) and test 88 each ran a real `kb collect` |
| URLs fetched (twice each) | `https://tax.gov.ae/Datafolder/Files/Legislation/2025/Federal-Decree-Law-No-8-of-2017-and-amendments.pdf` · `…/Legislation/Executive Regulation of Federal Decree Law No 8 of 2017 - Publish - 04 10 2024.pdf` · `…/Legislation/Executive-Regulation-of-Federal-Decree-Law-No-08-of-2017-Publish-18-09-2025.pdf` · `…/Legislation/2026/Law-No-8-of-2017-and-its-amendments--09-2026.pdf` · `https://tax.gov.ae/en/taxes/Vat/vat.topics/registration.for.vat.aspx`. eLaws attempted, failed (DNS) |
| Run 1 (22:38:27–36) | Wrote into the scratch stand-in DB: collection attempts 7–12. The 4 PDFs were "identical" (same sha256 as the lock; no file written). The registration HTML had new bytes (`a3f15286…`, 356,206 bytes) with extracted text identical to `FTA-VAT-REG-PAGE@v1`: a `documents` row was added, **no new passages, no new source version**. The scratch lock gained 1 entry |
| Same test, next subtests | `rebuild` and `setup` re-registered from the scratch lock (attempts 13–26, all "identical"); offline |
| Run 2 (~22:38:37–42, test 88) | Into a temporary DB deleted by the test. Wrote `4d00cf31…` (356,206 bytes) into scratch `data/raw/` and a second lock entry |
| Also (test 90, old code) | Old `backup restore` replaced the **scratch stand-in** and kept `CL_compliance_before_restore_20261016_223848.sqlite3`. Scratch only |
| Evidence preserved (read-only, git-ignored, not committed because of reuse terms D4) | `data/backups/CL_incident_2026-10-16/` in the C worktree: `raw/FTA-VAT-REG-PAGE/a3f15286d057f386.html` (sha256 `a3f15286d057f386115bc89bb731d6d8a724bc4505fc296c64e4f99244568569`), `raw/FTA-VAT-REG-PAGE/4d00cf310626dbbe.html` (`4d00cf310626dbbe4c3d545517a39df64525f13d064483c07ff8a3129e732b31`), `scratch_lock_after_incident.json` (`c42d084e…`), `scratch_standin_after_incident.sqlite3` and `CL_compliance_before_restore_20261016_223848.sqlite3` (both `dc8f0a7f…`). Originals also remain in the scratchpad until it is cleared |
| Not in the active knowledge base (checked read-only on the original, 16 Oct ~23:10) | `documents` rows with those hashes: 0. Lock entries: 0. Files in original `data/raw/`: 0. Last `collection_attempts` row is 2026-10-16T05:05:16 (6 rows, none from the incident). Original DB md5 `26e202b8…` unchanged; lock, manifest, raw, fixtures and git state unchanged (sorted md5 snapshot before/after) |
| Processing performed | Extraction only (html.parser), inside the scratch DB. No passages created, no index rows, no interpretation, nothing reviewed, nothing sent anywhere |
| Not repeated | No collection since. The test fix (below) blocks the network at `urllib.request.urlopen`. A check confirmed that mock sits on the real fetch path |
| Also found | Test 88 used to mock `kb.http_fetch`, which a real fetch bypasses (bound as a default argument). Fixed on this branch |
| Research-agent cache (approved read-only research, P6) | WebFetch stored 8 PDFs it read under Claude's own `~/.claude/projects/…/tool-results/` (VATP046, VATP040, DL8, ER 09-2026, an older DL8, CD 40/2017, the EmaraTax registration and deregistration manuals). These are tool caches, not project files. I read them offline for this report; nothing was copied into the project |

## 4. Recommended next actions (in order)
1. **You:** approve decision 5, so I can read the Arabic ER Art. 14 once, read-only.
2. **You:** locate the consolidated DL 8/2017 copy that includes DL 16/2025 on tax.gov.ae (Legislation → VAT filter) and paste the URL. Then approve one guarded collection into a copy.
3. **You (or I draft):** a one-question FTA enquiry on 20 vs 30 business days.
4. **Reviewer (D3):** decide G1. Note the frozen evaluation expectations in §1.3.
5. **Workstream B:** apply the interim rules in `CL_WS_C_TO_B_SOURCE_VALIDITY_HANDOFF.md` (no deadline statement; outdated flag on DL Art. 48/54/74/79 (bis)).
6. **D10** (Article 1 extraction): approved and built separately on its own branch, on disposable databases. It does not depend on G1 or G3, and the knowledge base it rebuilds is still the outdated DL copy.
