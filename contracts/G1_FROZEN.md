# G1 — HerBiz Task 2 interface contract v1.0: FROZEN

**Business line:** HomepreunerHub / HerBiz · **Date:** 18 Oct 2026 (Asia/Dubai) · **Gate:** G1 (doc 15 r2; founder D-097/D-098) · **Frozen by:** Workstream A, canonical schema owner · **Branch:** `t2-integration`.

**This file is the G1 signal.** Contract-dependent work may now start in all workstreams: WS A A-1…A-8, WS B B-1…, WS C C-2…. Restrictions are unchanged: no publication, deployment, merge to main, paid calls, protected-database writes or source activation.

## Frozen schemas (bytes as of `713f368`; schema bytes unchanged since `b4eb7bb`)
| Contract | File | sha256 | Semantics owner |
|---|---|---|---|
| `herbiz.audit_record/1.0` | `audit_record_1.0.schema.json` | `cc2aebeae9ff0ad54670c2d75e50cd68a6be3eab342c15a8c514d5100989e061` | WS A |
| `herbiz.capability_declaration/1.0` | `capability_declaration_1.0.schema.json` | `5bde1f9ed4814a253c2081c1c59094cca7429c53c103ee96bc5c5b1c72b0a50f` | WS A |
| `herbiz.decision_explanation/1.0` | `decision_explanation_1.0.schema.json` | `388e98545b88d19b6b3719cc94099efd07318fdedf4154158755694f013e1f7f` | WS B |
| `herbiz.retrieval_result/1.0` | `retrieval_result_1.0.schema.json` | `f878a0af5cab43095ed5ef1b587db2f36ea9fa3cd3ea9cf062cf14d32202f3a5` | WS B |
| `herbiz.scenario/1.0` | `scenario_1.0.schema.json` | `4f445bea14520ae415bafd6f5c574010202c39db4c736698c3f5db7d8e502883` | WS A |
| `herbiz.source_validity/1.2` | `source_validity_1.2.schema.json` | `5ebe5f98e5514f37de62cfed608d38ddc2a21921010bca33e143c14b1035b948` | WS C |

`contracts/CONTRACTS_INDEX.json` sha256: `237dfe2333044d6299992e1881a255d36a4ece88ec603e8622ff72dc2410b24f`.

## Acknowledgements (both without open reservations)
| Workstream | Branch @ commit | File | Reservations |
|---|---|---|---|
| WS B | `t2-ws-b` @ `1bb4b2d` | `contracts/ACK_B_v1.0.md` | R-B1 and R-B2 raised at `0b52068` and closed, resolved in fixtures at `713f368` |
| WS C | `t2-ws-c` @ `61b5578` | `contracts/ACK_C_v1.0.md` | R-C1 raised at `b8455d9` and closed, resolved in the schema at `b4eb7bb` |

WS B and WS C keep byte-identical read-only copies of the schemas they use, with sha256 tests (verified by WS A on 18 Oct).

## Golden fixtures (frozen with the schemas)
| File | sha256 |
|---|---|
| `audit_record.invalid_query_text_when_blocked_T2-D2.json` | `6c266f1f532bc1af8cccc23194ab352e22dd67598c1e508fd3cb575f14a3c853` |
| `audit_record.valid_allow.json` | `bb5c377a07cf8a41fd2dcbdba224632e66355564a5afffdcacbebfb6c9ffb395` |
| `audit_record.valid_blocked.json` | `62ca31856863cdcdb8153a48680e3064ff8cd9bf80687e3c6b7fcae8041abb0d` |
| `capability_declaration.invalid_live_inference_active.json` | `60906a03bf8ad8090d0f4856b6115cd41a8c8adee48bc1131e143561a1ae811d` |
| `capability_declaration.valid.json` | `0bfd1a18c99b433cb4b0b2c8d3d2cb19229a32c696092835343483d6de981372` |
| `decision_explanation.invalid_numeric_confidence_T2-D3.json` | `74b4ecc17b0ca095390ef708ac4bdb75100cfd5006f48a8ebf65128d9c0bbaaa` |
| `decision_explanation.valid.json` | `cd56420a2971192fbc99fd7fa9b0ce39ea81316e1d32eff4301b9d7d05491ba7` |
| `retrieval_result.invalid_complete_with_missing_required.json` | `3cafbfb286e30cb33c73330ef712eb53896e7c3b0327268d599f8c981ac4116a` |
| `retrieval_result.valid.json` | `e465fc1007bc94fac193c35110f067040e6bbd538ca11514127c34de0b85eca9` |
| `scenario.invalid_unknown_scenario.json` | `191a4be6ba15020efab6899f723770ef99047d104cd5f4d16fafe75f79a045a9` |
| `scenario.valid_SC-1.json` | `9b94834836466fe762746d47aa860eaff5a4a5cf67fc0bc1e4ee21f1362962bb` |
| `scenario.valid_SC-2.json` | `09d3f83f1eb6c89745895c107449c45af2fb8884b236b84c5bd3ec3ef6be0535` |
| `scenario.valid_SC-3.json` | `ce802916957a3b20f0b695f78f8b956c3156417249457f9d4fc41c9cd51651a5` |
| `source_validity.invalid_review_status_approved.json` | `beb67db0d5603f4266d3e01a25d53f917902c957ea3404c6df5699c3edf2ee46` |
| `source_validity.invalid_url_without_status_R-C1.json` | `ceae29af71dd6f2b5faa98a5cdcb666292b1462b3dea946a2cc84b35203f7433` |
| `source_validity.valid_conflict.json` | `e3ce2d6c99e791aa42482264c5da60bf5ffa253bdbbb9f9d5b7c7fd68de0121c` |
| `source_validity.valid_outdated.json` | `97ec95144845b2e781b8d271e6dd10dfebfdac43eac3231cf8a2088773a6d276` |

Placeholders that are expected to be replaced by owner data in Phase 2, without a contract change:
- SC-1 `input.obligation_id` "SYN-OB-VAT-REGISTRATION" and its expected states: WS B, B-6 (from the frozen engine's output).
- SC-2 and SC-3 source data: WS C.

## Rules after the freeze (doc 16 r2 §0.1)
- **Minor (additive) versions:** written request from the semantics owner → WS A publishes a new schema with a new sha256 → the affected workstreams re-acknowledge.
- **Major (breaking) versions:** WS A sign-off and a founder note.
- **Validation:** stdlib `contracts/validate.py`; tests `tests/test_contracts.py` (14).
- **Fail closed:** payloads that do not validate are shown as "unavailable", and their audit record carries `error`.
