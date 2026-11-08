# WS-B competition technical evidence: HerBiz obligations engine

**Business line: HomepreunerHub / HerBiz** · Workstream B · ITU AI for Good UAE hackathon (submission 10 Nov 2026) · 17 Oct 2026

**Status**
- **Verified:** synthetic data only, offline.
- **Not done:** no merge to `main`, no deployment, no paid calls.

> Draft prototype, not reviewed by a qualified professional. It is not legal, tax or accounting advice. HerBiz does not file or pay anything. Nothing here claims formal conformance with ITU-T Y.3172.

**Scope.** WS-B owns:
- the engine;
- the legal-decision safeguards;
- fail-closed behaviour;
- the interface contracts;
- the technical test evidence.

WS-A owns the UX and the submission report. WS-C owns sources and source approval. The founder owns tax-agent engagement.

**Inputs reviewed**
- **The WS-B action plan, `09_HERBIZ_WORKSTREAM_B_ACTION_PLAN.md`:** the founder supplied its location on 17 Oct (`Compliance Operations Agent/CL_HERBIZ_Competition_Assessment/`). It was read after the first version of this document; its WS-B tasks are cross-checked in §9.
- **Competition requirements matrix:** `docs/release/CL_SUBMISSION_REQUIREMENTS_MATRIX.md` on WS-A's `int-herbiz360-champ`, which contains a draft Y.3172 mapping.
- **Architecture:** WS-C's `docs/rag/360/CL_HERBIZ_360_05_ARCHITECTURE.md`.
- **Standard:** Rec. ITU-T Y.3172 (06/2019), the local PDF in `AI For Good Documents/`: clause 8.1 "High-level architectural components" (ML pipeline nodes), with definitions 3.2.2 (MLFO) and 3.2.6 (ML sandbox).

---

## 1. Verified baseline

| Item | Value | How verified (17 Oct 2026) |
|---|---|---|
| Code commit | **`fdbe131`** (`ws-b-retrieval`; tag `ws-b-baseline-2026-10-17b`) | `git archive fdbe131` into a clean scratch folder |
| Later commits | `9d03551` (handoff note) and this document: documentation only | `git diff --stat fdbe131 HEAD` shows no code changes |
| Full test suite | **213 / 213 pass** (Python 3.11.9, about 20 s) | `python3 -m unittest discover -s tests` on the clean export |
| Engine tests | **49 / 49 pass** | `python3 -m unittest tests.test_obligations` |
| Demo interface | **`ws-b-demo-0.3`** | `fixture_contract` in the committed fixture |
| Fixture checksum | `1b8d2c3886e1227f9098a76c2976ac5e582c3221d5bfa482ad765f289f5dd138` | Committed file matches its `.sha256` |
| Fixture rebuild | Same content as the committed file. The only exception is the local WS-C folder path recorded in 8 `origin` lines (see §6, L1). | Rebuilt in scratch and compared after removing the path |
| Protected DB | Authoritative DB md5 `26e202b87a062288e56bcda1de9b0217`, unchanged; B's byte copy has the same md5 | `md5` on both files |
| WS-A integration | `int-herbiz360-champ` @ `2791c9b` pins `B_COMMIT = "fdbe131"`, `B_FIXTURE_CONTRACT = "ws-b-demo-0.3"` and the same sha256. B's engine, fixtures, demo files and tests are byte-identical to `fdbe131`. | `git diff --quiet fdbe131 int-herbiz360-champ -- <B paths>` |
| `main` | `fcdfbb7`, unchanged | `git rev-parse` |

## 2. Engine architecture

All code is in `compliance_agent/obligations/`, uses only the standard library, and makes no model calls, network calls or writes.

| Part | File | Role |
|---|---|---|
| Profile model | `profile_schema.json`, `profile.py` | 19 fields, each with a type, a requirement level and an owner question. `validate()` refuses malformed input. `evaluator_facts()` turns revenue bands into ranges and derives dates from an injected "as of" date. |
| Rule catalogues (data) | `catalogue/vat.json`, `catalogue/ct.json`, `catalogue/synthetic_test.json` | VAT C360-01..05 (drafts or blocked); corporate tax C360-07, 08, 10, 11, 14 (no rule; `no_reviewed_rule`); 2 TEST RULES (`SYN-LIC-RENEWAL`, `SYN-WPS-PAYROLL`) |
| Evaluator | `engine.py` `_Evaluator` (l.58) | Reuses the app engine's three-valued `Engine._eval` unchanged. It adds comparisons on ranges, and returns *unknown* rather than guessing. |
| State decision (one place) | `engine.py` `resolve_state()` (l.117) | Code-level guards: corporate tax is locked to blocked; TEST status is allowed only for `SYN-` ids in the synthetic domain; unknown statuses and policies are refused |
| Source validity | `validity.py` `load_pinned()` | WS-C contract 1.1, read from commit `9b48966` with `git archive` / `git show`. Fails closed. |
| Deadlines and documents | `engine.py` `deadline()` (l.149), `documents()` (l.177) | Dates are computed only when the state is `applicable` (TEST RULES, or a future reviewed and certified rule) |
| Owner projection | `engine.py` `owner_row()` (l.248), `OWNER_FIELDS` (l.54) | The only fields an owner screen may show. Real-law deadlines are always replaced with `NO_DATE`. |
| Corporate-tax demo layer | `ct_demo.py` | WS-C's fictional persona "Amal" A/B only. Adds a labelled demo block and keeps the blocked state. Attaches WS-C `sources360` 0.2 labels from `aa50dd4`, run in a separate process. |
| Wording guard | `engine.py` `wording_violations()` (l.270), `ct_demo.demo_wording_violations()` | Scans these engine text fields for definitive or certifying words: banner, questions, title, meaning, reason, owner text, deadline basis, why lines, owner actions and document labels. The `owner_row` fields (`state_chip`, `label`, `deadline_display`) are checked only in the committed fixture (test_85). |
| Change impact | `engine.py` `affected_by()` (l.263) | Maps changed provisions to obligations. Report only. |

### 2.1 Inputs

- **`assess(profile, sv=None, as_of=None, policy="blocked", catalogue=None)`:**
  - `profile` is `{"profile_id", "synthetic": true, "fields": {…}}`. Non-synthetic profiles are refused (`ProfileError`).
  - Values of `null` or `"not_sure"` mean unknown.
  - `sv` is a `ValiditySource` from `validity.load_pinned(db, commit, c_repo, today)`; `None` means no validity data, which fails closed.
  - `as_of` is the date used for every derived date.
- **`ct_demo.assess_demo(profile, sv, as_of, labels)`:** only for `SYN-AMAL-A` and `SYN-AMAL-B`. Any other profile raises `ValueError`.

### 2.2 Outputs

- **Report fields:**
  - `profile_id`, `as_of`, `policy`;
  - `audience` (`owner`, or `reviewer_only` for the `potential` preview);
  - `banner`;
  - `profile_gaps` (`missing_required`, `clarify`, `unknown`, `questions`);
  - `source_validity` (`available`, `origin`, `error`);
  - `summary` (a count for each state);
  - `obligations[]`.
- **Each obligation:**
  - identity and text: `id`, `domain`, `title`, `meaning`;
  - decision: `state`, `state_chip`, `already_done`, `reason`, `rule_status`, `draft_indication` (null when blocked);
  - reasoning: `why` (empty when blocked), `reviewer_trace`;
  - questions: `missing_information[]` (`fact`, `question`);
  - sources: `provisions`, `source_candidates`, `validity`;
  - timing and documents: `deadline` (`computed`, `due_date`, `basis`, `overdue`, plus `draft_basis_for_reviewer` when blocked), `documents` (`required`, `ready`, `missing`, `readiness`);
  - guidance: `owner_actions`, `professional_review`, `owner_text`, `label`.
- **Owner view:** `owner_row(result)` returns only `OWNER_FIELDS`, plus `deadline_display`. In the fixture, corporate-tax rows also carry `demo_scenario`.

### 2.3 Decision statuses

| State | When (`resolve_state`) | Owner chip |
|---|---|---|
| `applicable` / `not_applicable` | Only (a) TEST RULES, or (b) a `reviewed` rule whose sources WS-C certifies. Today there are no reviewed rules and no approved sources. | "Applies (TEST RULE)" / "Does not apply (TEST RULE)" |
| (owner fact) `not_applicable` + `already_done` | The owner says a step is already done (e.g. VAT registered). No legal judgement is made. | "Owner says done — not checked" |
| `potentially_applicable` | Only under the `potential` policy, which is a reviewer preview and never shown to owners (D-062) | "May apply (draft, not checked)" |
| `insufficient_information` | The rule result is unknown because facts are missing | "Need more information" |
| `blocked_pending_legal_validation` | No reviewed rule, a source conflict, an unapproved rule or sources, or the corporate-tax domain | "Blocked: legal validation" |

### 2.4 Missing information

- **Unknown answers stay unknown.** `null` and `"not_sure"` are never filled in with a default; they become owner questions (`profile.question()`).
- **Evaluator unknowns.** When a rule cannot be decided, the evaluator returns `None`, the state is `insufficient_information`, and the item lists the facts it needs. Derived facts are mapped back to the field the owner can answer (`DERIVED`).
- **Revenue near a threshold.** A revenue band that crosses a threshold asks for the exact amount; it never guesses.
- **Contradictions.** Contradictory answers (band vs amount, employees, legal form vs person type) go to `clarify`, and neither value is used.
- **Malformed input.** Malformed, NaN or infinite values and loose dates are refused.

### 2.5 Source-validity dependencies

**VAT validity (WS-C contract 1.1 @ `9b48966`).** The check fails closed when:
- the export is more than 7 days old;
- the commit is wrong or missing;
- the WS-C repository is missing;
- the database md5 differs (export bound to `26e202b…`).

**Corporate-tax labels (WS-C `sources360` 0.2 @ `aa50dd4`).** Labels are always `release_approved: false`. If they cannot be loaded, the label says "Source details unavailable; nothing is shown in their place."

**Approved official sources today: 0.**

### 2.6 Human-review requirements

- **Owner text.** Every non-TEST owner text ends with "Check with an FTA-registered tax agent before acting." (`CHECK`).
- **Professional review lists.** Each item lists what a professional must decide in `professional_review`, for example "Eligibility for Small Business Relief".
- **Corporate-tax labels** carry `reviewer_needed` (D3-CT) from WS-C.
- **Becoming definitive.** A rule can only become definitive through `rule_status: "reviewed"` plus WS-C certification. Today that route is exercised only with the test double `FakeCertified` (test_18, and test_50 for the corporate-tax lock). test_92 checks the owner-row date path with a hand-built row.
- **No escalation workflow in B.** B emits escalation *signals*. WS-A's application and WS-C's review process handle the routing.

### 2.7 Fail-closed behaviour (summary)

Each condition below has a code location and the tests that cover it.

- **No validity data, or stale / wrong data:** nothing is certified. Code: `validity.py` and `_source_status`. Tests: 20–23.
- **Unknown rule status or policy:** refused with `ValueError`. Code: `resolve_state`. Tests: 10 and 52.
- **Real-law rule relabelled as a TEST RULE:** refused. Code: `resolve_state`. Test: 51.
- **Corporate-tax entry tampered with:** in test_50, C360-07 is given a rule, `reviewed` status, a skip condition and a deadline all at once, and it is still blocked with no date. The other corporate-tax ids are covered untampered by test_12, under both policies. Code: `LOCKED_DOMAINS`.
- **Malformed provision id:** only that item fails closed; the rest of the report still runs. Code: `_source_status`. Test: 53.
- **Band compared with `eq`:** the result is unknown, never "no". Code: `_Evaluator`. Test: 54. The same guard covers `in`, but `in` is not tested.
- **Owner view:** the default policy is `blocked`, and `potential` reports are marked `audience: reviewer_only` with a REVIEWER PREVIEW banner. `owner_row()` does not itself refuse a reviewer-only report (L9). The control is the default policy plus tests 13, 70–72 and 85.

### 2.8 Synthetic versus real-law rules

**Synthetic rules**
- They use `rule_status: "synthetic_test"`, the `synthetic_test` domain, an `SYN-` id, a title starting "TEST RULE", the label "TEST RULE — not law", and no provisions.
- These are the only rules that compute dates.

**Real-law VAT rules**
- These are `draft_unreviewed`, read by AI from stored FTA texts; no qualified reviewer has checked them.
- C360-05 (deregistration) is `blocked_source_conflict` (WS-C gap G1).

### 2.9 Corporate-tax restrictions (D-061, D-062, D-064, D-066)

- No corporate-tax applicability, eligibility, relief or filing rule exists in code. Every corporate-tax catalogue entry has `rule: null`.
- `LOCKED_DOMAINS` makes the result blocked whatever the catalogue says.
- **The demo** covers only the WS-C persona variants and is labelled "Demo scenario — fictional business."
  - It shows: the profile questions, the document checklist and possible workflow steps.
  - It withholds: applicability, eligibility or relief, due dates and filing instructions.
- **Small Business Relief (C360-11):** the MD 131/2026 note is kept as a reviewer-only source note (`draft_basis_for_reviewer`), and the item stays blocked.

### 2.10 Deadline suppression

- **Engine level:** `deadline()` computes a date only when the state is `applicable`. For blocked or insufficient items the basis becomes `NO_DATE`, and the draft text is moved to `draft_basis_for_reviewer`.
- **Owner level (`owner_row`):**
  - Every real-law row shows `NO_DATE`, in every state, including "Owner says done". The one exception is a computed date from a `reviewed` rule.
  - TEST dates read "TEST RULE date (made up): YYYY-MM-DD".
  - TEST rows still waiting for answers read "TEST RULE: no date until the missing answers are given."
  - This is the founder-approved fix `fdbe131`.

### 2.11 Interface versions

| Interface | Version | Where |
|---|---|---|
| Python API (`assess`, `owner_row`, `assess_demo`, `load_pinned`, `load_c_labels`) | as at `fdbe131` | `compliance_agent/obligations/` |
| Demo fixture for WS-A | **`ws-b-demo-0.3`** | `docs/360/demo/wsa/CL_WSA_DEMO_FIXTURE_v1.json` + `.sha256` + `README.md` |
| WS-C VAT validity | contract 1.1 @ `9b48966` | `validity.PINNED_COMMIT` |
| WS-C 360 labels | `sources360` 0.2 @ `aa50dd4` | `ct_demo.SOURCES360_COMMIT` |

## 3. Safety-control evidence (scenarios A–E)

All five scenarios are supported by existing tests. I added no new tests or rules for this assurance step. Each listed test was run by name on the clean export of `fdbe131` on 17 Oct 2026, and every one passed.

| Scenario | What must hold | Tests (file `tests/test_obligations.py`) | Result |
|---|---|---|---|
| **A. Unsupported legal deadline** | No computed date unless the state is `applicable` (TEST RULE or a reviewed and certified rule). Owner rows show `NO_DATE` for every real-law row, and the draft basis is never shown. | test_30, test_32, test_70, test_90, test_91, test_92, test_50 (tampered corporate-tax deadline) | 7/7 pass |
| **B. Corporate-tax determination blocked** | Every corporate-tax item is blocked under both policies (test_12). C360-07 stays blocked when tampered with (test_50). The demo rows are labelled and withhold outcomes. | test_10, test_12, test_50, test_71, test_81 | 5/5 pass |
| **C. Missing business information** | "Not sure" stays unknown, the required gaps become questions, a band that crosses a threshold asks for the amount, contradictions are clarified, and bad values are refused | test_02, test_14, test_15, test_60, test_61 | 5/5 pass |
| **D. Unreviewed official source** | Real VAT provisions are not certified today (`source_not_approved`). Missing, stale or wrong validity data certifies nothing. WS-C labels are never release-approved; if they are missing, nothing is invented. The reviewed path is shown only with a test double. | test_11, test_18, test_20, test_21, test_22, test_23, test_82, test_83 | 8/8 pass |
| **E. Synthetic rule clearly labelled** | The TEST RULE label appears on every synthetic row. A real-law rule cannot pose as TEST. Fixtures are synthetic. There is no forbidden wording. The fixture matches its checksum and contract. | test_40, test_43, test_44, test_51, test_85 | 5/5 pass |

**Scenarios with no support:** none of A–E.

**Partly supported, reported rather than simulated:**
- **Scenario D, approved-source path:** this is only exercised with a test double. Real approved sources do not exist, by founder decision.
- **Scenario D, future-dated export:** a validity export dated in the future is not rejected (see §6, L3).

## 4. Test evidence

Run these from the root of a checkout or export of `fdbe131`.

```bash
python3 -m unittest discover -s tests
```

```bash
python3 -m unittest -v tests.test_obligations
```

```bash
python3 experiments/ws_b/CL_build_wsa_demo_fixture.py --as-of 2026-10-17 --out /tmp/fx
```

**Environment needed for the live tests (all read-only):**
- `data/CL_ws_b_exact_copy.sqlite3`: a byte copy of the authoritative DB, md5 `26e202b87a062288e56bcda1de9b0217`.
- `data/CL_ws_b_kb_copy.sqlite3`: md5 `c33160221efe42f2425a5725945a07af`.
- WS-C's repository as a sibling folder `CL_compliance_agent_app_ws_c`. A symbolic link is enough, because the commits are in the shared object store.

`data/*.sqlite3` is git-ignored. Without these items the affected tests fail closed, as designed.

| Run (17 Oct 2026) | Result |
|---|---|
| Full suite, clean export of `fdbe131` | 213 tests, OK |
| Engine suite | 49 tests, OK |
| Scenario tests A–E, by name | 30 test runs (some tests count for two scenarios), all OK |
| Fixture rebuild | Matches the committed fixture apart from the local WS-C folder path (§6, L1) |
| WS-A integration (reported by WS-A, not re-run by B) | `int-herbiz360-champ`: 347 tests, 0 failures, 1 skip (a WS-C environment item) |

Earlier independent technical review: 10 findings, all addressed or accepted in `CL_WS_B_360_BUILD_REPORT.md` §3.

Board reviews:
- legal-kalpu (D-064), on owner wording: conditional pass, fixes applied.
- legal-kalpu S1/S3, raised through WS-A's defect report: fixed in `fdbe131`.

## 5. ITU pipeline mapping (evidence for WS-A's diagram and report)

**Not formal conformance.** Y.3172 describes an *ML pipeline in telecommunication networks*. The node definitions below are from clause 8.1 of the local PDF (MLFO 3.2.2, sandbox 3.2.6). The HerBiz obligations engine uses **no machine-learning model**: its "reasoning" is deterministic rule evaluation over catalogue data. This is an analogy for explaining the architecture, not a claim of Y.3172 conformance. WS-A's requirements matrix already notes that a reviewer may find the fit poor.

| Requested role | Y.3172 node (clause 8.1 wording, paraphrased) | Actual WS-B component | Evidence |
|---|---|---|---|
| **Agent reasoning** | M (model): the model used in the pipeline. Here it is a deterministic stand-in, not ML. | `engine._Evaluator` (three-valued evaluation of the catalogue `rule` trees), `profile.evaluator_facts`, `engine.assess` | test_55 (range edges), test_54, test_14 |
| (inputs) | SRC / C / PP: data source, collector, preprocessor | SRC: the owner's synthetic profile and WS-C's source records. C: `profile.validate`. PP: `profile.evaluator_facts` (bands to ranges, derived dates) | test_02, test_04, test_60 |
| **Policy enforcement** | P (policy): applies policies to the model's output | `engine.resolve_state` (one decision point; `LOCKED_DOMAINS`; policy `blocked`), `_source_status` + `validity.load_pinned` (fail closed), `deadline()` suppression, `wording_violations` | test_10, 50–53, 20–23, 30, 90, 40, 41b |
| **Output distribution** | D (distributor): finds the SINKs and sends the output to them | `engine.owner_row` (owner sink: `OWNER_FIELDS` only), the `ws-b-demo-0.3` fixture (WS-A sink), `reviewer_trace` / `draft_basis_for_reviewer` (reviewer sink) | test_85, test_90, test_72 |
| **Human escalation** | No node of its own in Y.3172. The nearest is the SINK, which acts on the output. | Signals: `professional_review`, `CHECK` text, `missing_information` questions, WS-C `reviewer_needed` (D3-CT). The actual routing and sign-off are in WS-A's app and WS-C's review process, not in B. | test_14, test_40, test_82 |
| Orchestration (MLFO) and sandbox | MLFO: places and chains the nodes. Sandbox: an ML sandbox. | No orchestrator in B. The closest equivalents are the fixed demo date (`as_of`) and the synthetic-only fixtures, which work as a "sandbox". | test_44 |

**For WS-A's diagram:** Owner profile (SRC) → validate (C) → facts (PP) → rule evaluation (M, deterministic) → `resolve_state` + validity + deadline suppression (P) → `owner_row` / fixture (D) → owner screen, reviewer view (SINK). Every corporate-tax and unreviewed path ends at "Blocked: legal validation" with a professional-review signal.

## 6. Known limitations

| # | Limitation | Impact | Owner |
|---|---|---|---|
| L1 | The fixture records an absolute local WS-C folder path in 8 `source_validity.origin` lines, so a rebuild in a different folder gives a different sha256. The content is otherwise identical. The path also shows a local user folder name. | **Low.** WS-A verifies the committed file, not a rebuild. If the repository is ever published, the path would be visible. A fix would change the frozen baseline and needs founder approval. | B (if approved) |
| L2 | VAT validity data refuses exports older than 7 days (export dated 17 Oct) | None for the demo, which uses a fixed `as_of` of 17 Oct. A live run after 24 Oct shows validity "unavailable", which still fails closed. | WS-C regenerates and B re-pins, only with approval |
| L3 | **Partly covered behaviour (founder decision, 17 Oct).** A validity export dated in the future is not rejected, and staleness uses `load_pinned(today)` rather than `assess(as_of)` | None today, because no rule is `reviewed` | Must be closed before any source approval |
| L4 | The engine reasoning is deterministic. There is no model chain-of-thought; the trace is the rule lines. | Report the "audit logging and reasoning traces" requirement as deterministic traces | WS-A report |
| L5 | B has no escalation routing or reviewer queue; B only emits signals | WS-A and WS-C provide the workflow | WS-A / WS-C |
| L6 | 0 approved sources, and real VAT rules are drafts. Real-owner use is blocked. | By design (D-061, D-062) | Founder / reviewers |
| L7 | Temporary folders (`ws_b_c_iface_*`) are left by the older `source_validity_c` adapter | Housekeeping only | — |
| L9 | `owner_row()` does not refuse a `reviewer_only` (`potential`) report, so a caller could render "May apply" rows as owner rows | **Mitigated at the WS-A application boundary** (founder decision, 17 Oct). In WS-A's `compliance_agent/mvp360/adapter.py` @ `f0b9c5a`: l.115–116 refuses a fixture whose `audience` does not start with "owner view"; l.206 refuses live engine output unless `audience == "owner"`, `policy == "blocked"` and there are no wording violations. Either failure raises `Incompatible`. Test coverage: WS-A's `tests/test_mvp360.py::test_116_reviewer_only_or_potential_reports_are_refused` @ `40af29a` (added 17 Oct after WS-B flagged the gap; WS-A reports its full suite at 350 passed, 0 failed, 1 environment skip). | WS-A; B code unchanged |
| L10 | The wording guard does not scan the `owner_row` fields `state_chip`, `label` or `deadline_display`. They are fixed strings, checked only in the committed fixture (test_85). | Low. **Kept as a documented test-coverage limitation** (founder decision, 17 Oct). | B (if approved) |
| L8 | `09_HERBIZ_WORKSTREAM_B_ACTION_PLAN.md` was found after the first version of this document | Resolved: cross-checked in §9 | — |
| L11 | **Partly covered behaviour (founder decision, 17 Oct).** The "reviewed rule + certified sources → definitive answer" path is exercised only with the test double `FakeCertified` (test_18, test_50) and a hand-built row (test_92). No real approved source exists. | None today; it must be re-tested with real approved sources before any rule is marked `reviewed` | Reviewers / WS-C / B |
| L12 | **Public-export limitation (founder decision D-089, 17 Oct).** In the clean submission export, two groups of tests cannot run: (a) **3 database-dependent tests** (test_20, test_23, test_45), because the exact database copies are not published; (b) **31 official-text-dependent tests** (WS-B's retrieval and classifier suites, which score `CL_article_index_v6.json` titles and article opening text), because under D4 only metadata about FTA/MoF material is published and no full official texts or passages without verified redistribution rights. The engine code in the export is `fdbe131`, unchanged, with the 8 local-path removals kept. The 7 H360-13 tests (`4ef0bf9`) are approved for the championship branch and export (WS-A integrates them). | Accepted; the full 220 tests pass in the private repository with the data present | WS-A (export) / founder |

## 7. WS-A handoff

| Item | Value |
|---|---|
| Commit | `fdbe131` (tag `ws-b-baseline-2026-10-17b`), already pinned in `int-herbiz360-champ` |
| Interface | `ws-b-demo-0.3`; contract and display rules in `docs/360/demo/wsa/README.md` |
| Samples | `docs/360/demo/wsa/CL_WSA_DEMO_FIXTURE_v1.json` (Amal A/B plus 6 VAT profiles), `docs/360/demo/CL_OBLIGATIONS_DEMO_EVIDENCE.md`, `docs/360/demo/CL_obligations_demo_blocked.json` |
| Test commands | §4 |
| Compatibility | Confirmed. WS-A's adapter reads `fixture_contract`, `audience`, `owner_rows`, `state_chip`, `label`, `title`, `deadline_display` and `demo_scenario`, and all of these are present at `fdbe131`. The B files on the integration branch are byte-identical. No field changed after `30a6f9a` except `deadline_display` wording (0.3). |
| Limitations | §6 |
| Handoff note | `docs/360/CL_WS_B_TO_A_INTEGRATION_HANDOFF.md` (§0 covers `fdbe131`) |

## 8. Critical defects

**None found.** No safety scenario failed. No tested owner path (the 6 synthetic profiles, both demo personas and the committed fixture) shows a real-law decision, date, eligibility result or filing instruction. The B code in WS-A's integration branch is identical to `fdbe131`.

Low-severity findings L1 (local path in the fixture), L9 (no audience check in `owner_row`) and L10 (wording-guard coverage) are recorded and were not fixed, because the baseline is frozen. Fixing them needs founder approval.

**Board review:** tech-sonu (CTO), Conditional pass on 17 Oct 2026. All eight of its document corrections are applied here. Its re-run of the engine suite: 49/49 OK. It found no code change necessary.

**WS-B remains frozen at `fdbe131`.**

## 9. Acceptance and submission notes (17 Oct 2026)

**Founder acceptance.** This evidence (`ed83032`) is accepted for the championship submission. WS-A owns the technical report and uses it as follows:
- the verified 213-test baseline and scenarios A–E;
- deterministic rules, not an ML model;
- a Y.3172 clause 8.1 analogy, not conformance;
- human escalation as review *flags* only: WS-B does not assign cases to reviewers;
- partly covered behaviours L3 and L11;
- L9 mitigated at WS-A's boundary;
- L10 kept.

**Cross-check against `09_HERBIZ_WORKSTREAM_B_ACTION_PLAN.md`**

| 09 task | Status | Note |
|---|---|---|
| H360-14 (47 vs 48 topics) | open | Documentation only |
| H360-13 (reviewer sign-off endpoint test) | **done** (founder-approved, tests only) | `tests/test_signoff_endpoint.py`, commit `4ef0bf9`. 7 tests of the existing `/api/signoff`: one row and one append-only audit event per valid sign-off; missing fields, unknown decisions and non-UI requests refused with nothing written; listed by `/api/project`. Writes go only to a `dbsafety.ensure_workspace` throwaway copy, and the source DB md5 is checked. A mutation check (accepting "approved" and skipping the audit write) made 4 of the 7 fail. Full suite: **220 OK** (213 + 7). No engine, contract or rule change. |
| Fact sheet `CL_WS_B_FACTS_FOR_REPORT.md` | open | Documentation only |
| Scenario cross-reference (S1, S3, S5) | partly covered | §3 here. A mapping to WS-A's harness ids is not yet written. |
| CR-16 (optional) | not started | P2 |

09 says "limitations L1–L9". This document now has L1–L12.

**Publication-safe export and privacy scan:** see `docs/360/publication/` (prepared; not published).
