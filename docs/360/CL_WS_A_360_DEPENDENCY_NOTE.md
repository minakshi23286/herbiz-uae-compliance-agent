# HerBiz 360 MVP — Workstream A dependency verification note

**Business line:** HomepreunerHub / HerBiz · **Date:** Sat 17 Oct 2026 · **Branch:** `ws-a-360-mvp` (local, cut from `main` @ `fcdfbb7`; no merge) · **Not legal, tax or accounting advice.**
Everything below was checked against the committed files; WS B and WS C worktrees were never edited.

## A. WS B obligations engine — VERIFIED (pinned `a54db87`)
| Item | Finding |
|---|---|
| Commit | Founder named `b63f69a`; the branch is now at **`a54db87`** ("apply **D-062** fail-closed owner view"). A pins `a54db87` because D-062 (founder, 17 Oct) governs what owners may see |
| Interface | `compliance_agent.obligations.engine.assess(profile, sv, as_of, policy)`; `sv` from `validity.load_pinned(db, c_repo=…, today=…)` (C contract 1.1 pinned at `9b48966`). Python only, no CLI |
| Input | profile `{"profile_id", "synthetic": true, "fields": {…19 fields…}}` (`profile_schema.json`); `"not_sure"` = unknown |
| Output | `profile_id, as_of, policy, audience, banner, profile_gaps, source_validity, summary, obligations[]`; each obligation: `id, domain, title, meaning, state, reason, rule_status, why, reviewer_trace, missing_information, sources, deadline, documents, owner_actions, owner_text, professional_review, label, draft_indication` |
| States | `applicable · not_applicable · potentially_applicable · insufficient_information · blocked_pending_legal_validation`. Owner policy `blocked` (D-062): real-law items are only **blocked** or **insufficient information**; `applicable/not_applicable` only for `SYN-` TEST RULES; `potential` is reviewer-only |
| CT | all CT items `blocked_pending_legal_validation` in code (tampering-tested) |
| Tests | **204/204 pass** on an isolated detached checkout of `a54db87` (scratchpad), with byte copies of the DBs B expects (`CL_ws_b_exact_copy.sqlite3` md5 `26e202b8…`, `CL_ws_b_kb_copy.sqlite3` md5 `c3316022…`) and a read-only link to C's repo for B's pinned `git archive 9b48966`. First attempts failed only on these environment files (fail-closed, as designed) |
| Error handling | validity unavailable/stale (> 7 days) → fail closed; malformed answers refused; contradictory answers → clarification |

## B. WS C sources360 — VERIFIED (pinned `6cfcaff`; contract 0.1 introduced at `37897a1`)
| Item | Finding |
|---|---|
| API | `sources360.load()`, `obligation_label(data, id, as_of, profile_synthetic)`, `impact(data, alerts)` |
| CLI | `python3 -m compliance_agent.rag_c obligations360 [IDS…] --as-of DATE` (never passes `profile_synthetic`, so **CT labels are always refused via the CLI**); `impact360 --alerts FILE` (required) |
| Label fields | `obligation_id, known, shown, title, domain, mode, reviewer_needed, substantive_rule_allowed (false), release_approved (false), citations[source_id, title, authority, url, evidence_level, retrieved_at, review_status, stale], vat_register_sources, open_gaps, uncertainty (high/medium; never low), user_wording, contract` |
| Source states | 26 candidates; **none approved or activated** (loader refuses); `content_stored: false`; stale after 30 days |
| Change impact | `CL_sbr_amendment_impact_2026-10-17.json`: CT-SBR affected by MD 131/2026 (real); `activation: not activated`; `human_review_required: true` |

## C. B ↔ C join (no shared id field)
- B ids `C360-xx`; C ids `VAT-…`, `CT-…`, `ACC-…`. B's CT/accounting catalogue lists C **source ids** (`source_candidates`).
- A's adapter joins **only** on these sets:
  - an exact set match first;
  - otherwise a unique C obligation whose sources contain all of B's;
  - otherwise "source label not linked".
- Result: C360-07→CT-REG-JURIDICAL, C360-08→CT-REG-NATURAL, C360-10→CT-RETURN, C360-11→CT-SBR, C360-14→ACC-RECORDS.
- VAT rows (`C360-01…05`) have **no** shared id. They show B's own source-validity wording, which already comes from C's contract 1.1.

## D. Existing WS A app (main @ `fcdfbb7`)
- Local web app: `web.py` and `ui.html`.
- Recorded-answer Ask panel (`ask.py`), DB safety (`dbsafety.py`), and a test workspace by default.
- 83 tests pass and 23/23 scenarios.
- Reused for the VAT journey (recorded answers + incompleteness guard).

## E. Gaps that A fills with labelled, isolated items (no rule logic)
- **CT fixed two-persona scenario** (C 06 §1, persona "Amal" A/B). It exists only as a document, so A transcribes it into a demo fixture with provenance. Every line is prefixed "Demo scenario (fictional business)". It is never taken from B's blocked engine.
- **Financial readiness** (C 02 §3): synthetic transactions; arithmetic totals with `label_level` A1/A2; no eligibility verdicts (D-062).
- **Who-does-what** (C 02 §4): transcribed as written, with "estimate, not reviewed" and no fees.
