# HerBiz 360 — technical report: claim-to-evidence appendix

**Business line:** HomepreunerHub / HerBiz · **Report:** `docs/360/submission/CL_HERBIZ360_TECHNICAL_REPORT.md` (5 pages) · **This appendix is outside the 5 pages.** · **Release candidate:** tag `t2-a-rc1` (branch `t2-integration`) · Synthetic demonstration only; not legal, tax or accounting advice.

Each claim in the report resolves to a file, a test or a count. Paths are relative to the repository root. Tests run with `python3 -m unittest <module>`. Items marked "private" need the development repository, because the evidence is a database or a file not published. Items marked "other workstream" sit on another branch or folder, named in full.

## Introduction and use case
| # | Claim in the report | Evidence |
|---|---|---|
| E-01 | Private suite: 498 tests run, 0 failures, 1 environment-only skip | `python3 -m unittest discover -s tests` at the release-candidate commit; log in the RC evidence folder (`CL_HERBIZ360_T2_RC1_2026-10-18/evidence/`, private) |
| E-02 | All 329 public-manifest tests pass in a clean copy of the public export | `tests/MANIFEST_PUBLIC.json`; `python3 experiments/ws_a/CL_run_export_tests.py` (strict guard) on the export; RC evidence `clean_A_public.txt` |
| E-03 | Demo source snapshot 17 October 2026 | `docs/360/CL_DEMO_SNAPSHOT.lock.json`; `tests/test_mvp360.py` test_109, test_110 |
| E-04 | Six customer scenarios UC-01 to UC-06, Demonstrated with fictional businesses | `docs/360/CL_HERBIZ360_DEMO_SCRIPTS.md`; owner page `compliance_agent/ui360.html`; fixtures `docs/360/demo/wsa/CL_WSA_DEMO_FIXTURE_v1.json` |
| E-05 | Corporate tax always blocked; demo labels only for the two fictional Amal variants | `tests/test_obligations.py` test_12, test_50; `tests/test_mvp360.py` test_90, test_91 |
| E-06 | Capability declaration: seven classes, live inference none, audit execution modes match | `capabilities.json`; `tests/test_capabilities.py` t2k_01–t2k_06 |
| E-07 | Recorded answers from claude-sonnet-5-5, recorded 16 Oct 2026, replayed only for an exactly matching question | `compliance_agent/ask.py` (`Asker._load_recorded`, exact-text match); ledger `data/CL_llm_experiment.sqlite3` (private; 206 successful Sonnet calls, 16 Oct 18:19–19:55 +04:00); `tests/test_cx_demo.py` |
| E-08 | No external calls at run time | `tests/test_mvp360.py` test_114 (no network modules in app code) |

## Use case requirement (controls)
| # | Claim | Evidence |
|---|---|---|
| E-09 | Official texts only, allow-listed hosts, SHA-256 per file, locked snapshot | `compliance_agent/kb.py`; `knowledge_base/CL_collected_lock.json`; `tests/test_mvp360.py` test_110 |
| E-10 | Fail closed for unreviewed legal rules; no deadline, decision or filing instruction | `tests/test_obligations.py` test_70; `tests/test_mvp360.py` test_92, test_102, test_104 |
| E-11 | Protected databases cannot be written; tampered components refused | `compliance_agent/dbsafety.py`; `tests/test_mvp360.py` test_106, test_120; scenario E13 in `docs/360/evidence/CL_error_scenarios.json` |
| E-12 | Source validity per passage from 110 working records, not independently verified legal content | `knowledge_base/t2/CL_source_validity_1.2.json` (WS C `t2-c-rc2` `8f35b20`); `tests/test_a4_integration.py` t2i_03, t2i_04; `tests/test_ws_c_t2_delivery.py` |
| E-12b | A recorded answer that relies on a repealed, amended or conflicting article is withheld (rc3; today V24) | `compliance_agent/ask.py` (`Asker._recorded`), `compliance_agent/t2_retrieval.py` (`article_status`); `tests/test_recorded_validity.py` t3r_01–t3r_08 |
| E-13 | Current official link shown, never fetched; "not checked by a person yet" | `compliance_agent/t2_retrieval.py` (`owner_validity`); `tests/test_a4_integration.py` t2i_03 (network blocked); `tests/test_scenarios.py` t2s_03 |
| E-14 | Personal-data intake check; pattern checks miss names, addresses and unusual formats | `compliance_agent/rag_c/policy_gate.py`; `tests/test_privacy_gate_app.py` 123–133; `tests/test_ws_c_policy_gate.py` |
| E-15 | One audit record per owner-facing response, contract audit_record/1.0 | `compliance_agent/audit_log.py`, `audit_records.py`; `tests/test_audit_log.py` t2a_01; samples `docs/360/evidence/audit-logs/` (`tests/test_audit_samples.py`) |
| E-16 | Daily SHA-256 hash chain with pointer row; tampering detected | `tests/test_audit_log.py` t2a_08, t2a_09; `python3 -m compliance_agent.audit_log verify <file> --scan` |
| E-17 | Independent sanitizer rejects (never redacts); offline scanner | `compliance_agent/audit_sanitizer.py`; `tests/test_audit_log.py` t2a_05, t2a_12, t2a_15 |
| E-18 | Answer withheld if the record cannot be written | `tests/test_audit_log.py` t2a_06; `tests/test_privacy_gate_app.py` test_130 |
| E-19 | Audit view only in reviewer mode | `tests/test_audit_log.py` t2a_07 |
| E-20 | A blocked question leaves no text and no hash | `tests/test_audit_log.py` t2a_03; `tests/test_a4_integration.py` t2i_09 |
| E-21 | 60 parallel requests | `tests/test_audit_log.py` t2a_10 (60 requests, contiguous chain); t2a_11 (second process) |

## Mapping (section 4)
| # | Claim | Evidence |
|---|---|---|
| E-22 | VAT: 3 sources, 5 captures, 371 passages; 27 further sources inventoried as metadata | `kb_export/CL_HERBIZ_KB_MANIFEST.json` and `kb_export/README.md` (v0.2.1) |
| E-23 | 0 legal sources have qualified approval | `kb_export/CL_HERBIZ_KB_MANIFEST.json` (`review_status_note`: approved_versions is empty) |
| E-24 | Four governance references collected, not activated or legally assessed | `knowledge_base/policy/CL_ai_governance_references.json` |
| E-25 | Interim retrieval v8 in the PP row (68.5% pooled; target not met) | E-31 |
| E-26 | ITU reference code evaluated for compatibility, not adopted: 0 of 18 vs 8 of 18 (comparative, non-independent set) | Other workstream: WS C tag `t2-c-opt1` (branch `t2-ws-c-opt`, not integrated), `docs/t2/opt/` in `CL_compliance_agent_app_ws_c`; recorded in `Compliance Operations Agent/CL_Change_Log.md` (18 Oct, WS C C-5) |

## Error scenarios (section 5)
| # | Claim | Evidence |
|---|---|---|
| E-27 | SC-1, SC-2, SC-3 released one event at a time, checked and audited; all pass | `compliance_agent/scenarios.py`; `python3 -m compliance_agent.scenarios replay SC-n`; `tests/test_scenarios.py` t2s_01–t2s_09 |
| E-28 | SC-1 questions 8, then 5, then 0; blocked with "What you can do now"; no deadline | `tests/test_scenarios.py` t2s_04, t2s_05 (WS B data `fixtures/t2/CL_SC-1_decision.json`, obligation C360-03) |
| E-29 | SC-2 both values with sources, no precedence, no deadline, tax-agent referral | `tests/test_scenarios.py` t2s_02 |
| E-30 | 13 of 13 controversy scenarios Tested | `docs/360/evidence/CL_error_scenarios.json`; `tests/test_mvp360.py` test_115; in the export, E10/E11 on the synthetic fixture (`tests/test_synthetic_vat_warning.py`) |
| E-31 | Retrieval: v10 66.7% (18/27), v11 70.4% (19/27), pooled 68.5% (37/54); 70% target not met; false refusals 4/27 and 1/27; no out-of-scope question answered; every answer warned; silent-incomplete 0 by construction | v10: `docs/CL_evidence/ws_b/t2/` (code-freeze record and metrics; WS B `t2-b-rc1`). v11: other workstream, WS B tag `t2-b-rc2` (branch `t2-ws-b-r2`), `B_T2R2_V11_FINDINGS.md` and `docs/CL_evidence/ws_b/t2r2/`. Reproduced identically by WS A (`docs/t2/CL_A4_INTEGRATION_REPORT.md` §9) and by the assessment session. Founder decision D-106. Declared in `capabilities.json` metrics |
| E-32 | Pinned VAT Decree-Law copy outdated (Articles 48 and 74); provision map lacks Article 79 | `knowledge_base/t2/CL_source_validity_1.2.json` key `FTA-VAT-DL8\|*` (status outdated; Federal Decree-Law No. 16 of 2025); WS B findings (E-31) |
| E-33 | Notes and audit logs append-only; retention unresolved | `compliance_agent/audit_log.py`; README limitation L9 |

## Policy and standards gaps (section 6)
| # | Claim | Evidence |
|---|---|---|
| E-34 | Event-page quotation (unweighted criteria) | `docs/itu/CL_WSC_POLICY_AND_STANDARDS_GAPS.md`, "Criterion wording" (page re-read 18 Oct 2026) |
| E-35 | G-T2-1 to G-T2-4: UAE titles, articles and URLs; global examples | `docs/itu/CL_WSC_POLICY_AND_STANDARDS_GAPS.md` (WS C `t2-c-rc3` `d9af9d4`; change report `docs/t2/CL_C_RC3_CHANGE_REPORT.md`) |
| E-36 | PDPL sentence (Executive Regulation status not determinable; no applicability claim; article numbers omitted until confirmed) | Assessment folder: `CL_compliance_agent_app_assessment/docs/assessment/board/CL_review_legal-kalpu_PDPL_ER_2026-10-18.md`; founder D-107; `docs/t2/CL_A6_INPUTS.md` §4 |
| E-37 | MoHRE Resolution (0340) of 2026: Art. 1(1), Annex 1 item 2, in force 1 June 2026 | `docs/itu/CL_WSC_POLICY_AND_STANDARDS_GAPS.md` G-T2-3 (official MoHRE PDF sha256 `11d0544e…`, read 18 Oct 2026); D-103 |
| E-38 | Small Business Relief amendment MD 131/2026 found by reading decisions | `docs/360/CL_HERBIZ360_POST_SNAPSHOT_CHANGE_REPORT.md`; demo step 7 (`tests/test_mvp360.py` test_111) |
| E-39 | I publish metadata, hashes and links only | `kb_export/README.md` ("excludes"); `CL_EXPORT_FILE_MANIFEST.json` (held-back files listed) |
