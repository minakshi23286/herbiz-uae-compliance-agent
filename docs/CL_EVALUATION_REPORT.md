# HerBiz: Compliance Agent — Evaluation report

**Business line:** HomepreunerHub / HerBiz · **Prepared by:** Claude Code · **Status:** verified (software checks only) · **Date:** 16 Oct 2026
**What this proves:** the software behaves as specified on synthetic inputs and handles real official documents without inventing content. **What it does not prove:** that any legal reading is right. No domain reviewer has checked anything.

## 1. Automated tests
Command: `python3 -m unittest discover -s tests -v` (from the app folder). Final recorded result: see `docs/CL_evidence/CL_test_run_final.txt`.

| Area | Tests |
|---|---|
| Missing facts | 01 jurisdiction · 02 licence context · 05 unknown ledger line |
| Invalid / malformed input | 03 invalid profiles · 29 malformed JSON, foreign host, missing UI header |
| Salary regression (VAT) | 04 fixture rule · 39 real-source reading (Art. 19) · scenario S04 · mutation check (salary counted → test fails) |
| Profile change | 06 rechecks dependent results and escalates instead of dropping |
| Renewal date | 07 never inferred from issue date |
| Irrelevant source | 08 |
| Conflicting evidence | 09 escalates, keeps both, cannot be approved away · 27 clarification updates only affected items |
| Superseded / withdrawn | 10 superseded version unused · 11 withdrawn rule |
| Future effective date / stale evidence | 12 |
| Cosmetic vs substantive change | 13 · 14 · 15 reopen resolved case · 38 article-level comparison |
| Malicious source text | 16 flagged, no effect, approval refused without acknowledgement |
| Fetch allowlist / unavailable source | 17 · 30 |
| Immutable evidence / append-only audit | 18 · 25 |
| Evidence gate and review | 19 incomplete stays open · 20 blank evidence ignored · 21 rejection records identity and time · 22 identity required · 23 resolution, no double close |
| Duplicate retries | 24 engine · 32 collector (same bytes; new bytes, same text) |
| Persistence after restart | 26 (and browser restart check below) |
| No numeric confidence | 28 |
| Extraction | 31 articles, headers, footnote repair, locators · 33 empty page flagged · 34 unreadable PDF recorded as failure · 35 HTML + FTS + query-injection guard |
| Real source rules | 36 never preapproved · 37 quote check + interpretation review gate |
| Evaluation runner | 40 suite passes and a wrong expectation fails · 41 results stored |
| Backup / restore | 42 |

Repairs made because tests failed (kept, not weakened): pypdf exception on a corrupt PDF crashed extraction (fixed: falls back, then records failure); page ranges spilled onto the next page (fixed); Art. 19 reading let a "below threshold" result hide related-party supplies (fixed: related-party/acquired-business "yes" makes the total unknown); tests wrote into the real lock file (fixed: lock path per knowledge base); SQLite connection used across server threads (fixed: one lock per request).

## 2. Scenario evaluation (synthetic)
Command: `python3 -m compliance_agent.evaluation`. Stored in the database and shown in the Evaluation tab.

| Metric | Value | Meaning |
|---|---|---|
| Scenarios | 23 (passed 23, failed 0) | expected values written by software from fixture rules |
| Expected-result agreement | 24/24 | engine matches its own specification |
| Clarification rate | 0.108 | share of assessments that asked for facts |
| Escalated cases | 4 | conflicts, stale evidence, changed profile |
| Unexpected cases (false alerts) | 0 | cases where the scenario said none |
| Applicable results with citation / with quote found in source | 37/37 / 37/37 | presence **and** quote check |
| Naive keyword-lookup baseline agreement | 13/23 | a weak stand-in, **not** a manual-lookup comparison (CPO review) |

## 3. Real official sources (knowledge base)
| Count | Value |
|---|---|
| Real official sources collected | 3 (Decree-Law; Executive Regulation; FTA topic page) |
| Captures (documents) | 5 (Executive Regulation in three versions: 04-10-2024, 18-09-2025, file dated 09-2026) |
| Extracted fully / partly / failed | 5 / 0 / 0 |
| Searchable passages | 371 (all UNVERIFIED_EXTRACTION) |
| Sources not collected | 1 (MOJ eLaws — host unreachable) |
| Real versions approved by a human | 0 |
| Interpretations: draft / reviewed | 1 real draft (all 7 quotes found) + 1 negative control (quote not found, correctly unusable) / 0 |
| Article coverage | Decree-Law Articles 1–85 all located; Executive Regulation Articles 2–75 located, Article 1 (definitions) not separated |
| Version comparison 18-09-2025 → 09-2026 | 15 wording changes, 47 layout-only; Article 7 (registration) layout-only |

## 4. Interface checks (browser, 16 Oct 2026)
Done: stage buttons; reviewer approval of a source change; refusal of a flagged source without the tick; owner sends 1 of 2 evidence items (case stays open); reload keeps reviewer name and data; server restart keeps cases, reviews and history; no console errors; no sideways scroll at 375 px; knowledge-base search, passage view, version comparison, evaluation and project tabs render.
Not done: screen-reader pass; keyboard-only pass; Arabic; slow-network behaviour; approving the real VAT interpretation in the main database (deliberately not done, so no test reviewer's approval sits in the real record).

## 5. Not measured
Legal accuracy; reviewer correction rate; owner time saved; comparison with real manual lookup; any real user behaviour.
