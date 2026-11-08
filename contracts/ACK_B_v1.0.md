# ACK_B v1.0: Workstream B acknowledgement of the Task 2 canonical contracts

**Business line: HomepreunerHub / HerBiz** · Workstream B · 18 Oct 2026 · branch `t2-ws-b` · founder decision D-098 · based on WS-A `t2-integration` @ **`b4eb7bb`**

**Status: semantics confirmed; no open reservations** (18 Oct 2026, after WS-A `t2-integration` @ `713f368`). Schema bytes are unchanged since `b4eb7bb`.

> Synthetic prototype. Not legal, tax or accounting advice.

## 1. Contracts acknowledged (sha256 checked against my byte-identical copies in `contracts/ws_a_canonical_b4eb7bb/`)

| Contract | File | sha256 | WS-B role | Result |
|---|---|---|---|---|
| `herbiz.retrieval_result/1.0` | `retrieval_result_1.0.schema.json` | `f878a0af5cab43095ed5ef1b587db2f36ea9fa3cd3ea9cf062cf14d32202f3a5` | semantics owner | **Confirmed** (§2) |
| `herbiz.decision_explanation/1.0` | `decision_explanation_1.0.schema.json` | `388e98545b88d19b6b3719cc94099efd07318fdedf4154158755694f013e1f7f` | semantics owner | **Confirmed**, with reservation R-B1 on its golden fixture |
| `herbiz.audit_record/1.0` | `audit_record_1.0.schema.json` | `cc2aebeae9ff0ad54670c2d75e50cd68a6be3eab342c15a8c514d5100989e061` | embedded payloads | **Confirmed unchanged** (checked programmatically, see below) |
| `herbiz.scenario/1.0` | `scenario_1.0.schema.json` | `4f445bea14520ae415bafd6f5c574010202c39db4c736698c3f5db7d8e502883` | SC-1/SC-2 decision data | **Confirmed**, with reservation R-B2 |
| `herbiz.capability_declaration/1.0` | `capability_declaration_1.0.schema.json` | `5bde1f9ed4814a253c2081c1c59094cca7429c53c103ee96bc5c5b1c72b0a50f` | entries CAP-ENGINE, CAP-SEARCH, CAP-PROXY | **Confirmed** |
| Index | `CONTRACTS_INDEX.json` | `237dfe2333044d6299992e1881a255d36a4ece88ec603e8622ff72dc2410b24f` | — | matches |

**Embedding check (18 Oct).**
- `audit_record.retrieval` equals `retrieval_result` with `items[].text` removed. It is nullable, as required for blocked answers.
- `audit_record.decisions[]` equals `decision_explanation`.
- The test `tests/test_t2_contract_copy.py` checks both equalities and the sha256 values.

## 2. Semantics WS-B confirms (and will implement in Phase 2 after G1)

**`retrieval_result/1.0`**
- **`completeness.status`:**
  - `complete_for_map` only when every `required_provisions` entry with role `primary` or `base` has at least one item in `items[]` (same `source_id` and `article`). Role `supporting` never affects completeness.
  - `incomplete` when at least one primary or base provision is missing. All missing ones are then listed in `missing_required`, which is never empty for `incomplete`; WS-B tests enforce this because the schema cannot.
  - `unknown` when the provision map has no entry for the question, and for every `out_of_scope` or `unsupported` result.
  - "Complete for the map" is **not** legal completeness. The map is an AI-generated, unreviewed draft (`map_review_status: "draft-unreviewed"`).
- **Silent-incomplete:** defined exactly as in doc 16 r2 §1. It is measured against independent labels, never against the map.
- **`budget`:** `returned == len(items) <= max_passages`, enforced by WS-B tests.
- **`scope`:** `out_of_scope` and `unsupported` give `in_scope: false`, `required_provisions: []` and `completeness.status: "unknown"`; `items` may be empty.
- **`items[].added_by`:** a short code from a fixed WS-B list (for example `lexical_search`, `article_aggregation`, `xref_expansion`, `map_completion`). The list will be published in the Phase 2 handoff.
- **`items[].text`:** internal only. It never goes into audit records.
- **`trace[].step`:** ordered stage names from a fixed WS-B list, published in the Phase 2 handoff.

**`decision_explanation/1.0`**
- The engine fields are copied verbatim from the engine result at the declared `engine.commit`.
- `execution_mode` is `simulated` when `rule_status == "synthetic_test"`, otherwise `deterministic`.
- `steps[].visible_to`:
  - steps built from `reviewer_trace` and `draft_basis_for_reviewer` are always `reviewer`;
  - for blocked items, no rule-evaluation outcome is `owner`-visible, matching D-062 and the engine's empty `why`.
- `confidence`:
  - follows doc 16 r2 §2, and `numeric` is always null;
  - `basis` codes come from a fixed list: `blocked`, `source_not_current`, `test_rule`, `completeness_incomplete`, `no_reviewed_rule`, `owner_reported_fact`;
  - `high` cannot occur today.
- `review.release_approved` is always false.

## 3. Interpretation points

| # | WS-B answer |
|---|---|
| **I-1** | **Confirmed.** WS-B emits `deterministic` (demo path), `proxy_outputs` (evaluation only, labelled as such) or `recorded_model`. It **never** emits `live_model` in Task 2. Keeping the §1 enum value in the schema is fine. |
| **I-2** | **Confirmed.** `article: null` means the source has no articles (e.g. `FTA-VAT-REG-PAGE`). `"*"` (used in `source_validity` and in `decision_explanation.steps[].rule_ref`) means "the whole source". These are two different meanings, and WS-B will not mix them. |
| **I-3** | **Confirmed, with the exact definition.** `query_sha256 = sha256(utf8(re.sub(r"\s+", " ", q.lower()).strip())).hexdigest()`, using Python 3 `str.lower()` and Unicode `\s`. No other normalisation; in particular no NFC, and punctuation is kept. A future change would be a new contract minor version. |
| **I-4** | **Confirmed.** These stay free strings. The values at `fdbe131`: `state` is one of the five engine states; `rule_status` is one of `draft_unreviewed`, `reviewed`, `no_reviewed_rule`, `blocked_source_conflict` or `synthetic_test`; `label` is "TEST RULE — not law" or "Draft — not reviewed". |
| **I-7** | **Confirmed shape `{state, flags, must_show, must_not}`, subject to R-B2.** |

## 4. Reservations: both CLOSED at WS-A `713f368` (verified by WS-B, 18 Oct 2026)

| # | Resolution | How WS-B checked it |
|---|---|---|
| R-B1 | `decision_explanation.valid.json` now uses `rule_status: "draft_unreviewed"` and the internal `reason` "rule or sources not checked by a reviewer". Owner text stays in `owner_rows[].owner_text`. Fixture sha256 is `cd56420a2971192fbc99fd7fa9b0ce39ea81316e1d32eff4301b9d7d05491ba7`. | `git show 713f368:contracts/fixtures/decision_explanation.valid.json`: values checked, and the hash matches |
| R-B2 | Convention adopted: a step with a non-null `expected.state` names `input.obligation_id`, and the runner compares against that obligation. SC-1 uses the placeholder `SYN-OB-VAT-REGISTRATION`, which WS-B's B-6 data replaces. SC-1 step 3 is a complete synthetic profile. SC-2 keeps `state: null`. `scenario.valid_SC-1.json` sha256 is `9b94834836466fe762746d47aa860eaff5a4a5cf67fc0bc1e4ee21f1362962bb`. | Steps 1–3 all carry `input.obligation_id`, and the hash matches |
| — | Schema bytes and `CONTRACTS_INDEX.json` (`237dfe23…`) are unchanged since `b4eb7bb` | The six files at `713f368` were hashed and equal WS-B's copy |

**Carried to B-6 (Phase 2), not a reservation.** WS-B will replace the SC-1 placeholder with a real engine obligation id. The expected states will be derived from the frozen engine's actual output for the complete synthetic profile; the current placeholder expects `blocked_pending_legal_validation` at step 3.

### Original reservation text (kept for the record)

**R-B1: the `decision_explanation.valid.json` golden fixture uses values the engine never produces.**
- `rule_status: "draft"` should be `"draft_unreviewed"`.
- `reason` holds an owner-facing sentence ("HerBiz can't answer this yet: …"). The engine's `reason` is the internal, reviewer-facing reason, for example "rule or sources not checked by a reviewer"; the owner sentence is the engine's `owner_text`.
- **Request:** correct the fixture to real engine values. Owner screens keep taking the owner sentence from `owner_rows[].owner_text` (B's fixture or `engine.owner_row`), not from `decision_explanation.reason`.
- No schema change. If WS-A wants the owner sentence inside `decision_explanation`, that is a separate additive request for WS-A to raise.

**R-B2: `scenario.expected.state` needs to name an obligation.**
- One profile gives about 12 obligation results, so a single expected `state` is ambiguous for SC-1. For example, SC-1 step 3 in the current fixture still lacks several required profile fields, so most VAT items would be `insufficient_information`, not `blocked_pending_legal_validation`.
- **Proposal:** WS-B's SC-1 data (B-6, Phase 2) puts `obligation_id` in each step's `input`, which is free-form. The runner compares `expected.state` with that obligation's state, and SC-1 step 3 uses a complete synthetic profile.
- For SC-2, `state: null` is correct, because it is a retrieval and conflict scenario.
- **Request:** WS-A confirms that the runner reads `input.obligation_id`, or proposes another convention. No schema change.

## 5. What WS-B has not done (Phase 1 limits)

- No retrieval or payload code; that waits for `contracts/G1_FROZEN.md`.
- No edits to WS-A or WS-C files.
- The holdout set v10 is frozen (`fixtures/CL_llm_eval_unseen_v10.FROZEN.json`, sha256 `89d4156b…`, commit `86ca637`) and has **not been read**.

Change requests go to WS-A in writing. This file is updated once the reservations are settled.
