# HerBiz: Compliance Agent — Source-validity addendum v1.1: Arabic Executive Regulation, Article 14(1)

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** Fri 16 Oct 2026, ~23:45 +04:00 · **By:** Workstream C (Claude Code), branch `ws-c-d10-article1` · **Adds to** `CL_SOURCE_VALIDITY_G1_G3_2026-10-16.md` (v1.0, unchanged) · **Approval:** founder, 16 Oct 2026: read the FTA Arabic ER once, read-only, to check Art. 14(1) · **Status:** verified (wording only); **G1 stays BLOCKED** · **Not legal or tax advice.**

## 1. Result in one line
The FTA's Arabic Executive Regulation also says **20 working days** ("(20) عشرين يوم عمل") in Article 14(1). The Arabic and English ER texts agree, so the 20/30 conflict is **not** a translation error in the regulation. The only source that says 30 is still the FTA service page.

## 2. Source record
| Field | Value |
|---|---|
| Document | اللائحة التنفيذية للمرسوم بقانون اتحادي رقم (8) لسنة 2017 في شأن ضريبة القيمة المضافة, i.e. Cabinet Decision No. 52 of 2017 and its amendments, Arabic consolidated text |
| URL | https://tax.gov.ae//Datafolder/Files/Legislation/2026/Law-No-8-of-2017-and-its-amendments--09-2026-arabic.pdf (listed on https://tax.gov.ae/ar/legislation.aspx: issued 2026-09-01, published 2026-09-10, per the research listing) |
| Version | consolidation up to **Cabinet Decision No. 149 of 2026** (issued 1 Sep 2026, effective 1 Oct 2026). Page 1 lists the same 8 amending decisions with the same issue and effective dates as the English `FTA-VAT-ER@v3` |
| File | 54 pages, 1,296,567 bytes, sha256 `52d94bb016cf14ed76a899daa9242cc8f8cfd582025c2b23a120464d0895845d`. PDF metadata: Author "FTA", created 2026-09-09 14:36 +04:00 (Microsoft Word) |
| Official status | Page 1 carries **no** "unofficial translation" notice (the English file does). It is the FTA's Arabic consolidated text, **not** the Official Gazette; the Gazette was not checked |
| Article / page | **Article 14 – Tax Deregistration, clause 1, page 10** of 54. Footnote 10 on the article: "تم تعديل المادة بموجب قرار مجلس الوزراء رقم (100) لسنة 2024." ("The article was amended by Cabinet Decision No. (100) of 2024") |
| How read | one WebFetch of the URL, 16 Oct 2026 ~23:39. The fetch tool could not decode the PDF, but saved it to Claude's own cache (`~/.claude/projects/…/tool-results/webfetch-1792179567808-t1zprx.pdf`, not a project folder). The text was read offline with pypdf, and **page 10 and page 1 were checked visually as rendered images**, because the PDF text layer scrambles some Arabic letters. Nothing was saved into the project, the knowledge base or any database |
| Evidence level | observed_in_file (rendered page read, 16 Oct 2026) |

## 3. Exact wording (Article 14(1), as rendered on page 10)
> **المادة (14) – إلغاء التسجيل الضريبي**
> 1. على المسجل التقدم بطلب إلغاء التسجيل الضريبي في الحالات المنصوص عليها في المرسوم بقانون خلال (20) عشرين يوم عمل من وقوع أي منها.

Transcribed from the rendered page image. The raw text layer reads the same words, with letter-order artefacts such as "فر" for "في" and "الضريت ي" for "الضريبي". The number appears as digits "(20)" and in words "عشرين" (twenty).

**AI-assisted translation (not an authoritative legal translation or interpretation):**
"Article (14) – Tax Deregistration. 1. The Registrant must submit an application for tax deregistration, in the cases stipulated in the Decree-Law, within (20) twenty working days of the occurrence of any of them."

## 4. Comparison
| Source | Language | Article 14(1) / deadline wording | Number | Date of the version |
|---|---|---|---|---|
| ER Arabic consolidation (this addendum) | ar | "خلال (20) عشرين يوم عمل من وقوع أي منها" | **20 working days** | up to CD 149/2026 (eff. 2026-10-01); file created 2026-09-09 |
| ER English consolidation `FTA-VAT-ER@v3` (p. 12) | en (self-described unofficial translation) | "within 20 (twenty) Business Days of the occurrence of any of them" | **20 business days** | same amendment list |
| ER English `@v1` (04-10-2024), `@v2` (18-09-2025) | en | same wording | 20 | up to CD 100/2024 and CD 100/2025 |
| FTA VAT deregistration service page | en | "the deregistration application must be submitted within 30 business days" (where deregistration is mandatory) | **30** | page updated 2026-09-24 |
| FTA VAT deregistration service page | ar | "يجب تقديم الطلب خلال 30 يوم عمل من تاريخ نشوء التزام إلغاء التسجيل" | **30** | page updated 2026-09-24 |

**Observation (not a conclusion):** page 10 of the Arabic ER has another "30" in Art. 14(2)(b): "خلال فترة (30) الثلاثين يوماً القادمة", the forward-looking test that taxable supplies are not expected to exceed the voluntary threshold within the **next 30 days**. That is 30 calendar days for a different test, not a filing deadline. The service page also gives the FTA's own processing time as 30 business days. Either could explain how a "30" reached the service page, but **nothing proves it**.

## 5. Updated cause table for G1 (changes from v1.0 in bold)
| Possible cause | Verdict |
|---|---|
| Extraction error in our knowledge base | ruled out (v1.0) |
| Translation error on the FTA web page | ruled out (v1.0: Arabic page also says 30) |
| Translation error in the English ER | **ruled out: the Arabic ER also says 20 working days** |
| Amendment not yet reflected | no evidence: the Arabic consolidation includes CD 149/2026 and still says 20. The standalone text of CD 149/2026 was not located (secondary summaries do not mention deregistration) |
| Service page error or conflation (Art. 14(2)(b) "next 30 days", or the FTA's 30-business-day processing time) | **plausible, unproven** |
| A rule outside the VAT ER (e.g. Tax Procedures law) setting 30 days | not found; not ruled out |

**Status: G1 remains BLOCKED.** Both language versions of the regulation say 20 working days; the FTA's own service page says 30. Choosing between them is a legal judgement for a qualified reviewer (D3), possibly after asking the FTA. No deadline is selected here.

## 6. Recommended next actions (unchanged order, updated content)
1. **Reviewer (D3):** decide G1 with this table. The regulation text in both languages is now on record.
2. **FTA enquiry (you send; I can draft):** "ER Art. 14(1) says 20 business days; your deregistration service page says 30. Which applies to a mandatory deregistration application?"
3. **Agent behaviour until then (B):** unchanged. Show both statements with their sources; never state one deadline as the law.
4. **G3:** still unresolved. Two more read-only searches on 16 Oct (~23:45) found no consolidated DL 8/2017 copy that includes DL 16/2025. The only tax.gov.ae consolidated file returned is the older "For Publishing" copy (`FTA-VAT-DL8-2023-CONSOL-OLD`, already in the register). You still need to locate it by hand.
