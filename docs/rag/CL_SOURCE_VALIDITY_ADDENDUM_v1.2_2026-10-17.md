# HerBiz: Compliance Agent — Source-validity addendum v1.2 (G3 correction, new G1 evidence, footnote evidence)

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** 17 Oct 2026 · **By:** Workstream C · **Adds to** `CL_SOURCE_VALIDITY_G1_G3_2026-10-16.md` (v1.0) and `CL_SOURCE_VALIDITY_G1_ADDENDUM_v1.1_2026-10-16.md` (both unchanged) · **Not legal or tax advice. No deadline is chosen.**

## 1. Correction: G3 (independent QA finding C01)
v1.0 §2.2 said the registration and deregistration articles (DL Art. 13–24) are **"not affected"** by DL 16/2025. That was stated too strongly.
- **What VATP046 does:** it "highlight[s] the main changes"; it does not promise a complete list. It names Art. 48, 54 (bis), 74 and 79 (bis) for DL 16/2025 and does not name Art. 13–24.
- **Correct statement:** DL Art. 13–24 are **not listed** among the main changes. We do not know they are unchanged, because the current consolidated text has not been read.
- **System change:** register v1.6.0 marks DL-16-2025's article list as incomplete. The validity export now raises `FTA-VAT-DL8:partial-scope` on `FTA-VAT-DL8|*`, so **every provision of our DL copy is flagged as possibly out of date** until the current text is collected (C-3 / D13).

## 2. New G1 evidence (landscape research, 17 Oct 2026, read-only)
| Source | Statement | Evidence |
|---|---|---|
| ER Art. 14(1) (EN 09-2026 file, p. 12; AR file, p. 10) | 20 business days | observed_in_file (16 Oct) |
| DL Art. 21 (as amended by DL 18/2022) | no deadline in the article | observed (research agent, 17 Oct) |
| Tax Procedures Executive Regulation (CD 74/2023 as amended by CD 17/2026, consolidated 01-04-2026), Art. 6(5)–(6) | no applicant deadline, no FTA processing period for deregistration; no "30" business-day figure in the full text | observed (research agent, 17 Oct; full-text search) |
| FTA *Deregistration of Tax Groups* service page (updated 30 Sep 2026) | 20 business days to apply (tax groups); FTA review 20 business days | observed (research agent, 17 Oct) |
| FTA *VAT Deregistration* service page (updated 24 Sep 2026) | "must be submitted within 30 business days"; FTA processing 30 business days (+30 after resubmission) | observed (re-checked by me, 16 Oct) |

**Reading (research opinion, not a decision):** every legal text found says 20 business days or gives no deadline. The only "30" is the VAT deregistration service page, and the same page uses 30 business days for the FTA's own processing time. A drafting slip on that page is plausible but **unproven**.

**Status: G1 stays BLOCKED.** The qualified reviewer (D3) decides, ideally with the FTA's written answer (enquiry drafted, not sent: `CL_FTA_ENQUIRY_G1_DRAFT_2026-10-16.md`).

## 3. Amendment evidence from the documents' own footnotes (new tool)
`rag_c amendments` now reads each captured version's footnotes ("38 Clause amended as per Cabinet Decision No. 149 of 2026 …") and maps them to articles. On 17 Oct (observed_in_file):
- **CD 149/2026 → ER Art. 4, 29, 41, 52, 54, 55, 57, 60.** This replaces the search-snippet list (29, 41, 55). Two markers could not be assigned (43, 45).
- **CD 100/2025 → ER Art. 59, 60.**
- **In-scope ER Art. 6–18:** the only footnotes say CD 100/2024. **No CD 100/2025 or CD 149/2026 footnote** appears on Art. 7, 8, 14, 14 (bis), 15 or 16.
- **ER Art. 55 (and 56):** CD 149/2026 text applies only **from the first tax year commencing after 1 October 2027**. The consolidated file keeps today's text in the body and the future text in footnotes, and footnotes sit inside our passages (gap G8). New validity issue: `FTA-VAT-ER:future-text`.
- **DL copy:** footnotes show DL 18/2022 and DL 16/2024 amendments (e.g. Art. 13 ← DL 18/2022; Art. 1, 55, 70, 76 ← DL 16/2024). By definition, nothing shows DL 16/2025.

## 4. Extraction finding (cross-check with a second extractor)
- **Defect found:** in ER v1 (superseded) Art. 70, our text reads "Article 8 0" where the PDF has "Article 80". pypdf broke the number apart. The stricter cross-check (counts, and page numbers no longer excused) found it.
- **Rest of the corpus:** no unexplained number mismatch in the other 316 articles across the 4 PDFs.
