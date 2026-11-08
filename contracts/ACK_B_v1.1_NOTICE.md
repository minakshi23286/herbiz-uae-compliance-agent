# ACK_B v1.1 notice: semantics clarification (no schema change)

**Business line: HomepreunerHub / HerBiz** · Workstream B → Workstream A · 18 Oct 2026 · branch `t2-ws-b`

**Reason:** tech-sonu's pre-freeze review, finding 6. The frozen G1 schema bytes (index `237dfe23…`) are **unchanged**. This notice records how WS-B fills `herbiz.retrieval_result/1.0` in Task 2, so WS-A's UI and audit code read it correctly.

## 1. `completeness.status`

| Value | Meaning in Task 2 (v8) |
|---|---|
| `complete_for_map` | **Never emitted in Task 2.** Wrong certifications appeared across many topics on the development sets, so no safe topic allow-list exists while the provision map is an unreviewed AI draft. `retrieve_v8.CERTIFY = False`. This value comes back only after the map has been reviewed (D3), and only after another written notice to WS-A. |
| `incomplete` | At least one mapped primary or base provision is missing; `missing_required` is never empty. *(Unchanged.)* |
| `unknown` | **Widened.** It still covers the original cases: out-of-scope or unsupported questions, and questions with no map entry. It now also covers questions where **every mapped provision is present but HerBiz cannot confirm the question needs nothing else.** |

**Consequence for WS-A (N-B1, already accepted):**
- Every owner answer carries the `may_be_incomplete` flag and warning in Task 2.
- Silent-incomplete is impossible by construction. It is still measured on v1–v9 and on the single v10 run.

## 2. `scope`

- A question about another tax system (corporate tax alone, GST, ZATCA, HMRC, UK or Saudi VAT, zakat and similar) is `out_of_scope`.
- A question that mixes another tax with a UAE VAT need is `in_scope` only when "VAT" sits next to an explicit UAE marker (UAE, FTA, TRN or EmaraTax) **and** no foreign tax (GST, ZATCA, HMRC, UK or Saudi VAT) is named. Only the VAT part is answered, and the trace has a `scope_mixed` step. All other mixed questions are `out_of_scope` (tech-sonu re-check, 18 Oct).
- A licence, bank-loan or tenancy question with no tax word is `unsupported`.
- Portal "which button" questions, bookkeeper-fee questions and e-invoicing questions are `unsupported`.
- Questions about fine amounts stay `in_scope`. The penalty article is added, and the stored texts do not contain the penalty schedule.

## 3. `items[].added_by`: the fixed code list

`lexical_search`, `title_match`, `map_completion`, `xref_expansion`, `article_scorer`, `map_supporting`, and `other` as a fallback that should not occur.

## 4. `trace[].step`: the fixed list

`v7_pipeline`, `scope_mixed`, `scope_guard`, `scope_override`, `owner_language_triggers`, `budget`, `completeness`.

WS-A: please confirm you have read this. No contract version change is requested.
