# HerBiz: Workstream C → Workstreams A and B — 360 source-citation and uncertainty interface (championship MVP)

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** 17 Oct 2026 · **From:** Workstream C (branch `ws-c-source-intelligence`) · **Status:** built and tested (tests 178–187); board-reviewed (see the readiness pack); not merged · **Not legal, tax or accounting advice.**

## What C provides (read-only; nothing to copy or re-implement)
| Item | Path | Use |
|---|---|---|
| Module | `compliance_agent/rag_c/sources360.py` (contract **0.1**) | `load()`, `obligation_label(data, obligation_id, as_of)`, `impact(data, alerts)` |
| Obligation → source map | `knowledge_base/CL_360_obligation_sources.json` | 15 candidate obligation ids (VAT, CT, accounting, e-invoicing, licence, UBO, WPS, ESR) with sources, gaps and reviewer |
| Source inventory | `knowledge_base/CL_360_source_candidates.json` | 26 official sources: evidence level, retrieval date, review status; **none approved** |
| CLI | `python3 -m compliance_agent.rag_c obligations360 [IDS…] --as-of YYYY-MM-DD` · `… impact360 --alerts FILE` | JSON for the UI or a demo script |
| VAT (unchanged) | `interface.py`, contract **1.1**, `answer_label` | B keeps using it for VAT |

## Rules that come with it (from the founder and the board)
1. **No corporate-tax rules.** Corporate tax in the MVP is a **fixed synthetic scenario** (persona variants A and B), not a rule evaluating arbitrary profiles. Every CT obligation has `substantive_rule_allowed: false` and reviewer `D3-CT`. The loader refuses a CT entry that says otherwise.
2. **Always display** `user_wording` (it starts "Draft information, not legal, tax or accounting advice"), the `uncertainty` indicator and the citations, each with its retrieval date. Never show "approved", "verified" or "certified": `release_approved` is always false.
3. **Changes are report-only.** `impact()` lists the affected obligations. It never changes data, rules or cases. B may re-run its engine for the affected obligations, and the UI shows "changed, pending review".
4. **No fees or prices** anywhere. No real owner data. No filing or payment.

## Who uses what
| Workstream | Uses | Does not do |
|---|---|---|
| **B** (profile model, obligations engine, workflow) | maps each engine obligation to an `obligation_id` here; attaches `obligation_label()` to each dashboard row; feeds `impact()` output into its re-assessment | duplicate the source data; write CT rules beyond the two fixed scenario variants |
| **A** (onboarding, UX, demo) | renders the label: wording, uncertainty chip (high / medium / low), citation list with dates, "reviewer needed: D3-CT"; plays the change-impact replay | hide the wording or the banner; state a fee |

**Contract changes:**
- **Additive change** (new fields or obligations): C bumps to 0.2 and tells A and B in writing.
- **Breaking change:** a renamed field or a changed meaning becomes 1.0, and needs A, B and the founder to agree.

## Contract 0.2 (17 Oct 2026, on WS B's written request after a legal-kalpu review under D-064)
- **Additive:** every citation now has `citation_chip`. The UI shows it as it is and never derives it:

  | Evidence level | Chip |
  |---|---|
  | observed | "Source found, not reviewed" |
  | listing only | "Source listed, not opened or reviewed" |
  | excerpt | "Source excerpt only, not reviewed" |
  | unresolved | "Source not located" |

- **Wording:** `user_wording` is now short sentences. Example: "Demo scenario (fictional business). Not legal, tax or accounting advice. Not reviewed by a qualified professional. Not a compliance decision. Shown as a demonstration scenario only. Open questions: CT law text not collected; article-level citations unavailable."
- **Unchanged:** the field names and meanings. Test 195 freezes the fields; test 196 checks the wording and chips.
- **Recommendation passed to the founder:** an FTA-registered tax agent checks the CT citation list (including MD 131/2026) before 10 Nov.
