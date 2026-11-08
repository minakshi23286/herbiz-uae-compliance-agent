# WS-B written G1 sign-off: HerBiz Task 2 interface contract v1.0

**Business line: HomepreunerHub / HerBiz** · Workstream B · 18 Oct 2026 · founder resume authorisation (18 Oct) under D-098

**Result: PASS. WS-B signs off G1 with no material defect.**

> Synthetic prototype. Not legal, tax or accounting advice.

## 1. Exact references (checked fresh from the latest canonical commit, not from an earlier local copy)

| Item | Value |
|---|---|
| WS-A canonical commit | **`t2-integration` @ `dbed01c`** (G1 freeze commit, latest on 18 Oct) |
| `G1_FROZEN.md` | sha256 `7d0591df8cdd79fcbcbd157b4419a5526fc7f932b85ccd131282ccba89552410`; cites ACK_B `1bb4b2d` and ACK_C `61b5578` |
| WS-B commit signing off | `t2-ws-b` @ `1bb4b2d` (ACK_B v1.0, no open reservations); this sign-off is committed on top of it |

**Schema sha256 at `dbed01c`.** Each one is byte-identical to WS-B's read-only copy in `contracts/ws_a_canonical_b4eb7bb/`.

| Schema | sha256 |
|---|---|
| `retrieval_result_1.0.schema.json` (WS-B semantics) | `f878a0af5cab43095ed5ef1b587db2f36ea9fa3cd3ea9cf062cf14d32202f3a5` |
| `decision_explanation_1.0.schema.json` (WS-B semantics) | `388e98545b88d19b6b3719cc94099efd07318fdedf4154158755694f013e1f7f` |
| `audit_record_1.0.schema.json` | `cc2aebeae9ff0ad54670c2d75e50cd68a6be3eab342c15a8c514d5100989e061` |
| `scenario_1.0.schema.json` | `4f445bea14520ae415bafd6f5c574010202c39db4c736698c3f5db7d8e502883` |
| `capability_declaration_1.0.schema.json` | `5bde1f9ed4814a253c2081c1c59094cca7429c53c103ee96bc5c5b1c72b0a50f` |
| `source_validity_1.2.schema.json` (WS-C semantics, not reviewed by WS-B) | `5ebe5f98e5514f37de62cfed608d38ddc2a21921010bca33e143c14b1035b948` |
| `CONTRACTS_INDEX.json` | `237dfe2333044d6299992e1881a255d36a4ece88ec603e8622ff72dc2410b24f` |

**Golden fixtures carrying WS-B semantics, at `dbed01c`**

| Fixture | sha256 |
|---|---|
| `retrieval_result.valid.json` | `e465fc1007bc94fac193c35110f067040e6bbd538ca11514127c34de0b85eca9` |
| `retrieval_result.invalid_complete_with_missing_required.json` | `3cafbfb286e30cb33c73330ef712eb53896e7c3b0327268d599f8c981ac4116a` |
| `decision_explanation.valid.json` | `cd56420a2971192fbc99fd7fa9b0ce39ea81316e1d32eff4301b9d7d05491ba7` |
| `decision_explanation.invalid_numeric_confidence_T2-D3.json` | `74b4ecc17b0ca095390ef708ac4bdb75100cfd5006f48a8ebf65128d9c0bbaaa` |
| `audit_record.valid_allow.json` | `bb5c377a07cf8a41fd2dcbdba224632e66355564a5afffdcacbebfb6c9ffb395` |
| `audit_record.valid_blocked.json` | `62ca31856863cdcdb8153a48680e3064ff8cd9bf80687e3c6b7fcae8041abb0d` |
| `scenario.valid_SC-1.json` | `9b94834836466fe762746d47aa860eaff5a4a5cf67fc0bc1e4ee21f1362962bb` |
| `scenario.valid_SC-2.json` | `09d3f83f1eb6c89745895c107449c45af2fb8884b236b84c5bd3ec3ef6be0535` |

## 2. Review of WS-B-owned semantics

| Area | Finding |
|---|---|
| `retrieval_result` | Matches ACK_B §2: completeness statuses, `complete_for_map` ⇒ no missing items (schema if/then), budget, scope, execution modes (never `live_model` from WS-B), and query normalisation I-3 |
| Completeness safeguard | The invalid fixture "complete_for_map with missing_required" is rejected. Silent-incomplete is defined as in doc 16 r2 §1. |
| `decision_explanation` | The golden fixture now uses real `fdbe131` engine values (R-B1 closed). `numeric` is always null, `release_approved` is always false, `execution_mode` is `deterministic` or `simulated` only. |
| Confidence labels | Categorical only; a numeric value is rejected (T2-D3 fixture). |
| Audit metadata | `audit_record.retrieval` equals `retrieval_result` minus `items[].text`, and is null when the answer is blocked (T2-D2). `audit_record.decisions[]` equals `decision_explanation`. Both are checked by WS-B tests. Release is never approved and a reviewer is always named. |
| Scenarios | Steps that expect a state name `input.obligation_id` (R-B2 closed). The SC-1 placeholder is replaced by WS-B in B-6 without any contract change. |

## 3. Tests run (18 Oct 2026)

| Run | Result |
|---|---|
| WS-A `tests/test_contracts.py` on a full export of `dbed01c` (`jsonschema` installed, so its cross-check also ran) | **14 / 14 OK** |
| `contracts/validate.py` on all 17 golden fixtures at `dbed01c` | **17 / 17 as expected**: 10 valid accepted, 7 invalid rejected |
| WS-B full suite on `t2-ws-b` @ `1bb4b2d` (includes schema-copy, embedding and v10-freeze tests) | **226 / 226 OK** |
| Frozen engine | `compliance_agent`, `fixtures/obligations` and `experiments` are unchanged since `fdbe131`; protected DB md5 `26e202b8…` unchanged |

## 4. Non-blocking notes for WS-A (implementation, not contract)

- **N-B1 (consumer obligation for A-1).** Every audit record and owner screen whose `retrieval.completeness.status` is `incomplete` or `unknown` must carry the `may_be_incomplete` flag, and show the warning. Only `complete_for_map` may omit it. The schema cannot express this rule across objects, and I found no Task 2 test for it at `dbed01c`. This is the user-facing half of the silent-incomplete safeguard. Please add a test in A-1.
- **N-B2.** The audit-level `confidence.basis` codes in the allow fixture (`incomplete`, `conflict`) differ from WS-B's decision-level codes (`completeness_incomplete`, `source_not_current`, …). Both are free strings and valid. Aligning the names later would help readers; no change is needed for G1.

## 5. What happens next

G1 is frozen by WS-A (`dbed01c`). WS-B continues the approved Task 2 Phase 2 work (B-1 onward) on `t2-ws-b` only:
- the frozen baselines stay untouched;
- there is no tuning on the frozen holdout set v10, which stays unread until the B-4 code_freeze record exists;
- no paid calls, merges, publication, deployment or source activation.
