# HerBiz / HomepreunerHub Compliance Agent — capability audit (raw, read-only)

Business line: HomepreunerHub / HerBiz. Audit date: 17 Oct 2026. Method: code read in all three checkouts, test suites run, fixtures and docs grepped. No file in the project folders was changed. The three database files were hashed (md5) before and after the test runs, and the hashes did not change. `git status` was clean before and after. No `*v9*` file was opened.

Paths are relative to `<LOCAL_PATH> championship/Compliance Operations Agent/`. A = `CL_compliance_agent_app` (main), B = `CL_compliance_agent_app_ws_b` (ws-b-retrieval), C = `CL_compliance_agent_app_ws_c` (ws-c-source-intelligence).

## 1. Summary

I classified 89 capabilities: **31 implemented and tested (1), 18 partially implemented (2), 17 documented but not implemented (3), 16 not previously considered (4), 7 blocked by a legal or technical dependency (5).**

What the code actually does today:
- It is a **local, VAT-centred, synthetic-data compliance workflow engine**. It takes a business profile, checks it against rules, opens action cases, sends them to a human reviewer, and keeps an append-only audit trail.
- It adds a **real-text retrieval layer for one law family**: the FTA-hosted UAE VAT Decree-Law, the Executive Regulation and the FTA registration page. There are 371 passages.
- It adds **source-intelligence tooling**: a source register, validity checks, amendment tracking and change monitoring.

What it does not do:
- **Corporate tax:** none. The code deliberately refuses it as out of scope.
- **Bookkeeping and financial readiness:** none, beyond one AED turnover ledger used only for the VAT threshold.
- **Other obligations:** UBO, WPS/payroll, ESR, free zone and AML have no code. Licence renewal, privacy and e-invoicing exist only as synthetic "FX" fixtures.
- **Time features:** no calendar or reminders, and no computed deadlines.
- **Arabic:** no Arabic in the interface or the knowledge base.
- **Deployment:** none. It runs only on the local machine.

Every owner-facing rule is synthetic (release blocker R5). The one real VAT reading is a draft that no qualified reviewer has checked (D3). The validity export has `approved_versions: []`, so nothing can be certified today. Workstreams B and C are **not merged** into main. The web app does not use their retrieval pipelines.

## 2. Capability table

| Area | Capability | Class | Evidence (paths, tests) | Real or synthetic data | Notes |
|---|---|---|---|---|---|
| A Profile | Emirate | 1 | `A/compliance_agent/profiles.py` `KNOWN_JURISDICTIONS`, `validate_profile`; tests `test_01_missing_jurisdiction_needs_clarification`, `test_03_invalid_profiles_are_refused` | Synthetic profiles only (DB `CHECK (synthetic = 1)`, `store.py` business_profiles) | 7 emirate codes. Used to filter emirate-specific rules (`engine.assess`). |
| A Profile | Mainland / free zone / jurisdiction type | 3 | No field in `FACT_TYPES`. Vision: `AI for Good HAckathon top 2 .md:67` | — | MVP explicitly excludes "other emirates and free zones" (`A/docs/CL_MVP_SCOPE_AND_ACCEPTANCE.md:16`). |
| A Profile | Licensing authority | 3 | No field. Only `licensing_context` (free label, e.g. `home_based_licence`, "name of licence UNVERIFIED", `profiles.py:14`). Vision lists DET/DED/free zones (`CL_Compliance Operations Agent — Full Build Plan_v1.md:86`) | Synthetic | — |
| A Profile | Legal entity type | 4 | Searched `profiles.py`, fixtures, `ui.html`, build plan, hackathon docs: no trace | — | — |
| A Profile | Natural vs juridical person | 4 | Not in profile or vision docs. Only `uae_place_of_residence` (bool, for VAT Art. 13) | — | Matters for CT and VAT; never modelled. |
| A Profile | Activities | 1 | `activity`, `activity_tags` facts. Onboarding maps 5 choices to tags (`web.py` `App.onboard`); tests `test_02`, `test_08_irrelevant_source_not_applicable`, `test_78_onboarding_creates_profile_and_runs_checks` | Synthetic | Not official activity codes. The vision promised "your activity codes" (build plan v1:65). |
| A Profile | Licence issue / expiry dates | 1 | `licence_issue_date`, `licence_expiry_date`; `test_07_renewal_date_never_inferred_from_issue_date` | Synthetic | Expiry is copied, never computed. |
| A Profile | Financial year and tax period | 4 | No fact or rule. "tax period" appears only as retrieval vocabulary (`B/compliance_agent/llm_lab/concepts_v5.py`) | — | — |
| A Profile | Revenue and thresholds | 1 | `ledger_last_12m`, `expected_taxable_supplies_next_30d_aed`, `profiles.taxable_supplies`; `test_04_regression_salary_never_added_to_taxable_turnover`, `test_05_unknown_ledger_line_is_not_guessed`, `test_39_art19_value_excludes_salary_and_asks_for_concerned_goods` | Synthetic amounts. Threshold AED 375,000 quoted from the real ER (draft interpretation) | Onboarding takes one "total sales" figure. |
| A Profile | Employees | 2 | `employees` int validated (`profiles.py:19`). **No rule uses it** (grep of conditions in `fixtures/CL_sources.json`, `knowledge_base/CL_draft_interpretations.json`) | Synthetic | Stored only. |
| A Profile | VAT registration status | 1 | `vat_registered`, used in VAT rules; scenario tests `test_26_staged_demo_and_restart_persistence`, `test_40_scenario_suite_passes_and_runner_can_fail` | Synthetic | — |
| A Profile | Corporate tax registration status | 3 | No field. Vision: build plan v1:52 | — | — |
| A Profile | Free-zone / designated-zone special circumstances | 3 | No profile fact. `designated_zone` exists only as a retrieval topic (`B/compliance_agent/llm_lab/data/CL_provision_map_v7.json`) | Real VAT text (retrieval only) | — |
| A Profile | Regulatory permissions (food, MOHRE, etc.) | 3 | Only `collects_customer_personal_data`, `sells_online`. Vision: build plan v1:49-51, 87-90 | — | Hiring/MOHRE excluded in the MVP (`CL_MVP_SCOPE_AND_ACCEPTANCE.md:16`). |
| A Profile | Profile storage, versioning, editing UI | 1 | `store.py` business_profiles (versioned), `engine.upsert_profile`; `/api/onboard`, `/api/profile` (`web.py`); `test_06_profile_change_rechecks_dependent_assessments`, `test_79_ask_and_onboard_endpoints` | Synthetic. One demo profile `BP-0001` | "Download/Load my details" saves reviewer fields from localStorage only (`ui.html:95,168`). |
| B Engine | Obligation applicability engine | 1 | `A/compliance_agent/engine.py` `assess`, `_eval` (three-valued: applicable / not_applicable / needs_clarification / conflict / stale_evidence / not_yet_in_force); tests `test_01`–`test_15`, `test_27_conflict_clarification_updates_only_affected`, `test_28_no_numeric_confidence_anywhere` | Rules: 5 synthetic obligation keys (LIC-RENEWAL, PRIV-NOTICE, VAT-MANDATORY-REG, EINV-START, FOOD-HYGIENE) plus 1 real draft (VAT-MANDATORY-REG-REAL, unreviewed) | Deterministic, no model. R5: the owner to-do list runs on synthetic rules. |
| C VAT | Mandatory registration rule | 1 | Real draft in `knowledge_base/CL_draft_interpretations.json` (DL Art. 13/19, ER Art. 7); `test_37_citation_support_and_interpretation_review_gate`, `test_43_reviewed_real_reading_drives_owner_case_on_a_copy` | Real FTA text; interpretation is a software draft, unreviewed | Reaches owners only after reviewer approval. D3 has no named reviewer. |
| C VAT | Voluntary registration | 2 | Retrieval topic `voluntary_registration` (provision map v7); `test_86_owner_wording_for_deregistration_and_voluntary` | Real text | No applicability rule. |
| C VAT | Deregistration | 5 | Retrieval topic only; G1 conflict (ER Art. 14(1) 20 vs FTA page 30 business days) `C/knowledge_base/CL_source_register.json` gaps; `test_v7_08_g1_g3_stay_blocked`, `test_120_the_deregistration_conflict_is_detected_and_thresholds_agree` | Real text | Blocked by G1 / D3. FTA enquiry drafted, not sent (`CL_FTA_ENQUIRY_G1_DRAFT_2026-10-16.md`). |
| C VAT | Returns and payments | 2 | Topics `tax_return`, `payment` (retrieval only) | Real text | No return preparation, no period or due-date computation. |
| C VAT | Tax invoices and credit notes | 2 | Topics `tax_invoice`, `credit_note` | Real text | D3 package lists a credit-note gap (DL 70) (B commit 93f6e44). |
| C VAT | Input / output VAT | 2 | Topics `input_tax`, `blocked_input_tax`, `input_tax_before_registration` | Real text | No computation. |
| C VAT | Exempt / zero-rated | 2 | Topics `exempt_*`, `zero_rated*`; `test_c1p2_fix1_exemption_questions_get_zero_rate_and_exempt_lists` | Real text | Retrieval only. |
| C VAT | Record-keeping | 2 | Topic `records`; `RECORDS_RX` in `B/compliance_agent/llm_lab/pipeline_v7.py:114` | Real text | Retrieval only. |
| C VAT | Amendments tracking (instruments, supersession) | 1 | `C/compliance_agent/rag_c/amendments.py`, register instruments (14); `test_117_decree_law_copy_is_outdated_by_dl_16_2025_and_er_v3_is_current`, `test_146_incomplete_amendment_list_flags_the_whole_outdated_source`, `test_160_full_lifecycle` | Real metadata | DL 8 copy is outdated (G3). |
| C VAT | Public clarifications / guides (VATP, user guides) | 2 | 69 register candidates, all inactive (`CL_source_register.json` candidates); `test_115_adding_proposals_bumps_the_register_and_keeps_everything_inactive` | Real URLs, not ingested | Collection needs approval. Reuse terms in D4/G5. |
| C VAT | Retrieval over official texts | 1 | `B/compliance_agent/llm_lab/pipeline_v6.py`, `pipeline_v7.py`, `pipeline_c1p2.py`; tests `test_v6_*`, `test_v7_*`, `test_c1p2_*` | Real FTA text, 371 passages | Quality gate not met: R1 (44% all-required on unseen v3). C1P v2 offline: recall 88.9%, legally certifiable 0 (B commit b61a7e4). **Not wired into the web app.** |
| C VAT | Provision map | 1 | `B/compliance_agent/llm_lab/data/CL_provision_map_v7.json` (47 topic keys, all 162 articles); `test_v6_03_provision_map_is_draft_and_unreviewed`, `test_v7_01_every_article_is_reachable_and_new_concepts_are_mapped` | Real article references; mapping is a draft | Waiting for the D3 review package (`B/docs/review_d3/`). |
| C VAT | Source validity and certification gating | 1 | `C/compliance_agent/rag_c/validity.py`, `interface.py`; `B/compliance_agent/llm_lab/source_validity_c.py`; tests `test_c1p2_04_fail_closed_...`, `test_162_completeness_and_approval_are_separate_and_only_both_certify`, `test_164`–`test_166` | Real | `approved_versions: []` in `C/knowledge_base/CL_source_validity.json`, so nothing is certifiable. |
| C VAT | G1 / G3 handling (never certify) | 1 | `test_v6_05_outdated_provision_is_never_certified`, `test_v6_06_conflicting_deadline_is_never_certified`, `test_c1_07_g1_g3_stay_blocked_even_when_both_agree` | Real | Handling works. Resolution is blocked (next row). |
| C VAT | G1 / G3 resolution | 5 | G1 owner "qualified reviewer (D3)". G3 needs the newer consolidated DL copy located by hand (register gaps) | Real | Blocked by D3 and the source location. |
| C VAT | VAT threshold calculator | 1 | `profiles.taxable_supplies`, `engine._value` (`art19_registration_value_last_12m_aed`); `test_04`, `test_05`, `test_39` | Synthetic ledgers, real threshold quote | Refuses Art. 19(3)-(4) related-party cases ("reviewer must calculate"). |
| D CT | Corporate tax: registration, SBR, returns, deadlines, free-zone persons, natural persons, penalties | 3 | Vision only: build plan v1:52, :89. No rules, sources or fields | — | Register discovery filters CT out (`C/compliance_agent/rag_c/discovery.py:20-21`). |
| D CT | CT recognised as out of scope (refusal) | 1 | `B/compliance_agent/llm_lab/classifier_c1.py:20` (`corporate_tax` class), `concepts_v5.py:108`; tests `test_c1p_09_scope_agreement_and_corporate_tax`, `test_c1p2_09_...` | — | The system refuses CT questions on purpose. |
| E Books | Income / expense recording | 2 | `ledger_last_12m` lines {type, amount_aed, note}, used only for the VAT threshold | Synthetic | No transaction UI. Onboarding takes one total. |
| E Books | Categorisation | 2 | `TAXABLE_SUPPLY_TYPES`, `NON_SUPPLY_TYPES` (`profiles.py:37-38`); `test_05` | Synthetic | 8 line types. Unknown types are refused, not guessed. |
| E Books | Receipts / invoices capture | 4 | No upload or storage. Evidence is text descriptions (`engine.submit_evidence`) | — | — |
| E Books | Bank reconciliation | 4 | None in code | — | Only in a different, rejected concept ("Income Evidence Reconciliation Agent", `AI_for_Good_Two_Concepts_Research_Review.md:108`). |
| E Books | Chart of accounts | 4 | None | — | — |
| E Books | P&L | 4 | None | — | — |
| E Books | Balance sheet | 4 | None | — | — |
| E Books | Cash flow / forecast | 4 | None | — | — |
| E Books | CT computation preparation | 4 | None | — | — |
| E Books | VAT reconciliation | 4 | None | — | — |
| E Books | Missing-document detection | 2 | Case evidence gaps only: `engine.evidence_gaps`; `test_19_insufficient_completion_evidence_keeps_case_open`, `test_20_empty_description_does_not_count_as_evidence` | Synthetic | Compliance-proof checklist, not bookkeeping documents. |
| E Books | Year-end checklist | 4 | None | — | — |
| E Books | Accountant export | 4 | None (only a reviewer-details JSON download) | — | — |
| E Books | Draft vs reviewed labelling | 1 | Legal info is labelled draft or unreviewed: `test_85_never_described_as_legally_verified`, `test_v6_03`, `test_126_every_recorded_answer_is_traced_and_none_is_certifiable` | — | No financial statements exist to label as draft or audited. |
| F Other | Trade licence renewal | 1 | Synthetic `LIC-RENEWAL` (FX authority, `fixture.invalid` URL); `test_07`, `test_14_substantive_change_proposes_then_updates_action`, `test_15_resolved_case_reopens_when_rule_changes` | **Synthetic only** | D2 (first real domain: VAT or licence) is pending. |
| F Other | Beneficial ownership (UBO) | 3 | Build plan v1:100 | — | — |
| F Other | Immigration / work permits / establishment card | 3 | Build plan v1:51 ("work permits"); establishment card not mentioned | — | MVP excludes hiring/MOHRE. |
| F Other | Employment / payroll / WPS | 3 | Build plan v1:51, :90. Code only excludes `salary_cost` from turnover | — | — |
| F Other | Permits (food safety / municipality) | 2 | Synthetic `FOOD-HYGIENE` rule; only the not-applicable path is tested (`test_08`) | Synthetic | Food is excluded as a product domain (MVP:16). |
| F Other | Economic Substance (ESR) | 4 | Appears only in an out-of-scope regex (`C/compliance_agent/rag_c/discovery.py:21`). Not in the vision docs | — | — |
| F Other | E-invoicing | 2 | Synthetic `EINV-START` (future effective 2027-07-01); `test_12_future_effective_date_raises_no_action`. Real MD 243/244 of 2025 only inactive candidates | Synthetic rule; real sources not ingested | Vision: build plan v1:53, :97. |
| F Other | Record retention | 2 | VAT `records` retrieval topic only. App-data retention only drafted (`A/docs/pilot/`) | Real text (retrieval) | — |
| F Other | Notifications | 2 | `alerts` table, deduplicated (`engine._alert`); `test_24_duplicate_retry_does_not_duplicate_case_or_alert` | Synthetic | In-app rows only. Messaging excluded (MVP:16). |
| F Other | Privacy notice (PDPL) | 1 | Synthetic `PRIV-NOTICE` conflict pair; `test_09_conflicting_evidence_escalates_and_keeps_both` | Synthetic | Used as a conflict demo. |
| F Other | AML / CFT | 3 | Build plan v1:98 | — | — |
| F Other | Free-zone obligations | 3 | Hackathon md:59, :66 | — | — |
| F Other | Business closure / licence cancellation | 4 | No trace (VAT deregistration is in C) | — | — |
| G Time | Deadline engine | 2 | `engine._due`: the due date is copied from one profile fact. VAT 30-day period explicitly "software does not compute it" (draft interpretation action); `test_07` | Synthetic | No computed deadlines anywhere. |
| G Time | Calendar | 3 | Build plan v1:126, :356 ("Build Compliance Calendar") | — | — |
| G Time | Reminders | 3 | Build plan v1:138 | — | No scheduler. |
| G Time | Owner to-do list (cases) | 1 | Owner view `#owner-cases` (`ui.html`); `engine._sync_case`; tests `test_19`–`test_23`, `test_78` | **Synthetic rules** | R5 in `project/CL_project_status.json`. |
| G Time | Owner to-do list on real FTA rules | 5 | Needs reviewer approval of the real reading (`test_43` works only on a copy with a simulated review) | Real text, unreviewed | Blocked by D3 (R2). |
| H Output | Document preparation / drafts for the owner (letters, checklists, guides) | 3 | Build plan v1:133, :526 (`document_drafter`) | — | The D3 reviewer package is for the reviewer, not owner documents. |
| H Output | Owner evidence submission | 1 | `engine.submit_evidence`, `/api/evidence`; `test_19`, `test_20` | Synthetic | Text only, no files. |
| H Review | In-app professional review and escalation | 1 | `review_case`, `review_source`, `review_interpretation`; `test_21`–`test_23`, `test_37`; tax-agent box `test_76_other_questions_get_no_answer_and_professional_box` | Synthetic | Simulated reviewer in the demo stages. |
| H Review | Real qualified reviewer | 5 | CA-T08 pending; package `B/docs/review_d3/`; cover email DRAFT (B commit 295f0e7) | — | Blocked by D3. |
| H Audit | Audit trail (append-only) | 1 | `store.py:130-135` triggers; `test_25_audit_log_is_append_only`, `test_18_source_evidence_is_immutable`; C `test_151_triggers_block_evidence_tampering_and_roll_back_exactly` | — | — |
| H Audit | Experiment ledger (LLM) | 1 | `A/compliance_agent/llm_lab/budget.py`, `run.py`; `test_44_grounded_run_logs_everything_and_keeps_main_db`, `test_45`–`test_50` | Synthetic questions | — |
| H Audit | Reviewer sign-off register | 2 | `/api/signoff` + `reviewer_signoffs` table (`web.py`) | — | **No test** references signoff. |
| H Sources | Monitoring of official sources (tooling) | 1 | `C/compliance_agent/rag_c/monitor.py`, `discovery.py`, `firecrawl_trial.py`; `test_106`–`test_116`, `test_131`–`test_140`, `test_154`, `test_155` | Real FTA/MoF pages (fixtures and local copies) | — |
| H Sources | Scheduled / live monitoring | 3 | "Scheduling (designed, **not installed**)" (`CL_HERBIZ_SOURCE_MONITORING_DESIGN_v2.md:74`) | — | Runs by hand only. |
| H Sources | Change impact on answers and cases | 1 | Engine reassessment (`test_14`, `test_15`, `test_11_withdrawn_rule_escalates_open_case`); C `test_170_detect_identify_flag_alert_block` | Synthetic + real | B `experiments/ws_b/CL_amendment_impact.py` has no test. |
| H UI | User-facing UI / demo | 1 | Local web app, 127.0.0.1 only, no authentication (`web.py`, `ui.html`): owner/team mode, Ask, onboarding, profile, owner cases, reviewer queue, KB search/compare/interpretations, evaluation, project, sign-offs, sources, history, demo stages, reset. CLIs: `kb`, `evaluation`, `demo`, `backup`, `rag_c`. Tests `test_29_local_api_rejects_foreign_requests_and_serves_state`, `test_79` | Synthetic profile | Identical code in A, B and C. |
| H AI | Ask panel answers | 1 | `A/compliance_agent/ask.py`: replays recorded Sonnet answers for exact-match development questions, otherwise offline passages; tests `test_70`–`test_77`, `test_84`, `test_85` | Recorded answers over real text | No live AI. Uses v4-era retrieval, not v7/C1P2. |
| H AI | LLM usage gating | 1 | `llm_lab` off by default; budget caps, approval files (`B/experiments/ws_b/CL_c1*_authorisation.json`); `test_46_hard_ceiling_cannot_exceed_60`, `test_49`, `test_c1_08_paid_run_refused_without_approval_and_v7_only_live`, `test_c1p2_07_llm_cannot_override_source_validity` | Synthetic questions | — |
| H AI | Live LLM in product / demo | 5 | D5e pending: "Not before ... R1 is fixed and ... D3 is named" | — | Blocked by D5e, R1 and D3. |
| H Lang | Arabic UI | 4 | No `dir="rtl"` or `lang="ar"` in `ui.html`. Not in any vision doc searched | — | — |
| H Lang | Arabic official texts | 5 | Gaps G4 and G9 (no official Arabic text; English copies are self-described unofficial translations) | — | Blocked by D4 and source access. |
| H Privacy | Privacy / data handling | 2 | Synthetic-only enforced (`validate_profile`, DB CHECK; `test_03`); localhost Host check (`test_29`); no authentication; consent/retention drafts in `A/docs/pilot/` | Synthetic | Not ready for real owners (R4, pilot Blocked). |
| H Release | Deployment | 3 | `A/docs/release/CL_DEPLOYMENT_AND_ROLLBACK.md`; MVP excludes public deployment | — | Local only. B and C are unmerged. |
| H Release | Backup / restore / DB protection | 1 | `backup.py`, `dbsafety.py`, C `rag_c/protection.py`; `test_42`, `test_80`–`test_83`, `test_90`–`test_93`, `test_151`–`test_153` | — | — |
| H Release | Evaluation runner | 1 | `evaluation.py`, 23 scenarios (`fixtures/CL_eval_scenarios.json`); `test_40`, `test_41` | Synthetic | — |
| H Safety | Instruction-like (injection) source screening | 1 | `sources.screen_untrusted`; `test_16_malicious_source_text_is_data_only` | Synthetic | — |
| H Release | Publication / reuse of FTA texts | 5 | D4 pending; R3; G5 (FTA terms need written consent) | Real | Blocked by D4. |
| H Ops | BOS integration | 3 | `A/docs/CL_BOS_INTEGRATION_GAP.md`; MVP acceptance "Not met" | — | One manual task card (TSK-0006). |

Class counts: 1 = 31, 2 = 18, 3 = 17, 4 = 16, 5 = 7 (total 89).

## 3. Original vision evidence

I found **no document** in `Agent championship/` that describes a "360° post-setup operations, financial-readiness and compliance assistant" with bookkeeping. I searched for "bookkeep" and "financial readiness" across all `.md` files and found no match. I also extracted the text of the three `.docx` files. The original vision is a **post-setup regulatory compliance agent**:

- "A post-setup regulatory compliance AI agent for home-based women entrepreneurs" — `CL_Compliance Operations Agent — Full Build Plan_v1.md:5` (the `.docx` and `GPT_..._v2.md` carry the same text; v2 is identical to v1)
- "Corporate Tax registration and filing, VAT if turnover exceeds AED 375,000" — build plan v1:52
- "your activity codes, emirate, licence type, home-based status" — build plan v1:65
- "crawls official gazettes and portals, alerts you" — build plan v1:66
- "Generates compliance checklists — customised to your business profile and upcoming deadlines" — build plan v1:68
- "full audit trail of every question asked, every regulation cited" — build plan v1:69
- "Ultimate Beneficial Owner register, annual maintenance" — build plan v1:100
- "MOHRE pre-approval, health cards, work permits, WPS salary transfers" — build plan v1:51
- "Compliance Calendar (structured JSON)" — build plan v1:126; "document drafter, regulation lookup" — :133; "WhatsApp/Telegram bot → alerts, reminders" — :138
- "free zone vs. mainland, home-based status, number of employees" — `AI for Good HAckathon top 2 .md:67`
- "tracks UAE federal, emirate-level, and free zone regulation updates" — hackathon md:59

The scope was then narrowed on purpose:
- "Proceed with a narrower, redesigned Compliance Operations concept" — `AI_for_Good_Two_Concepts_Research_Review.md:7`
- "Choose one emirate, one licensing context, one activity" — research review:75
- MVP out of scope: "other emirates and free zones; hiring/MOHRE; penalty calculation" — `A/docs/CL_MVP_SCOPE_AND_ACCEPTANCE.md:16`

## 4. Test-suite results (`python3 -m unittest discover -s tests`, run with `PYTHONDONTWRITEBYTECODE=1`)

| Checkout | Tests | Result | Time |
|---|---|---|---|
| A main | 83 | OK | 4.0 s |
| B ws-b-retrieval | 164 | OK | 19.0 s |
| C ws-c-source-intelligence | 170 | OK | 29.7 s |

There were harmless ResourceWarnings (unclosed sockets) and one "EOF marker not found" message from a deliberate unreadable-PDF test. The DB md5 hashes were identical before and after the runs, and `git status` stayed clean. No test file references v9.

Git state:
- Main is at `fcdfbb7`.
- `ws-b-retrieval` is 36 commits ahead of main and `ws-c-source-intelligence` 21 commits ahead.
- Only `main` appears in `git branch --merged main`, so neither workstream branch is merged.
- `engine.py`, `web.py`, `ask.py`, `profiles.py` and `ui.html` are byte-identical across A, B and C.

## 5. Scope and requirements documents

- `CL_Compliance Operations Agent — Full Build Plan_v1.md` / `.docx` / `GPT_..._v2.md`: the original broad plan (licence, food, PDPL, hiring, CT, VAT, UBO, AML, e-invoicing; n8n + RAG + Claude; calendar, reminders, drafter).
- `AI for Good HAckathon top 2 .md` / `.docx`: two concepts (Proof of Livelihood; Compliance co-pilot with profile engine, change crawler, audit trail).
- `AI_for_Good_Two_Concepts_Research_Review.md`: critical review. It narrows the work to a "Microbusiness Change-to-Action Agent" with one bounded scenario.
- `Compliance_Agent_Claude_Code_Prompt_Pack.md`: build prompts (profile, source versions, applicability, cases, review, audit; synthetic data; local UI).
- `Dubai_AI_Agent_Championship_22_Ideas.md`, `AI agent ideas.docx`: idea lists (not HerBiz-specific).
- `A/docs/CL_DISCOVERY_BRIEF.md`: provisional persona (Dubai home-based design business), VAT as the first real domain, no interviews yet.
- `A/docs/CL_MVP_SCOPE_AND_ACCEPTANCE.md`: in and out of scope for the MVP, plus acceptance (BOS exposure "Not met").
- `A/docs/CL_ARCHITECTURE_AND_DATA.md`, `CL_HerBiz_Architecture_Review_and_Improvement_Plan_2026-10-16.md`: architecture and the 13-item improvement plan.
- `CL_HERBIZ_RAG_ARCHITECTURE.md`, `CL_HERBIZ_SOURCE_VALIDITY_CONTRACT_v1.1.md`, `CL_HERBIZ_SOURCE_MONITORING_DESIGN_v2.md`, `CL_HERBIZ_SOURCE_OPERATING_MODEL.md`: RAG and source-governance design (VAT only).
- `B/docs/review_d3/*`: D3 reviewer package (provision map review, decision register xlsx, briefing, amendment procedure).
- `B/project/CL_project_status.json`: tasks CA-T01–T09, decisions D1–D9, release blockers R1–R5.
- `A/docs/release/*` (release readiness, deployment and rollback, user guide, submission matrix) and `A/docs/pilot/*`: drafts.

## 6. Surprising points or contradictions with earlier claims

1. **The "360° operations / financial-readiness / bookkeeping" vision is not written down** in any project or championship file I found. The documented original is regulatory compliance. Bookkeeping, P&L, reconciliation and accountant export were never planned (class 4).
2. **Corporate tax was in the original plan** (build plan v1:52, :89), but the code now **refuses CT as out of scope**: there is a classifier class and a discovery filter.
3. **B and C are not merged.** The user-facing app, including the Ask panel, uses the earlier retrieval and recorded answers. The v6/v7/C1P2 pipelines and the WS-C validity interface are not reachable from the UI.
4. The MVP scope lists "any AI model call" as out of scope (`CL_MVP_SCOPE_AND_ACCEPTANCE.md:16`). Paid LLM experiments did run: about $5.03 of a $6 cap in A's change log, plus $0.0275 for the C1 run in B. That document is stale.
5. **No answer or rule is approved:**
   - `approved_versions: []`.
   - The DL 8 copy is outdated (G3: DL 16/2025 missing).
   - D3 has no reviewer.
   - The owner to-do list is fully synthetic (R5).
   - "verified" in the tracker means tests only (`task_status_scope`).
6. **Retrieval** passes its tests but fails its gate:
   - R1: 44% on unseen v3.
   - The final C1P v2 run is "offline proxy outputs, not Haiku" and gives 0 legally certifiable answers.
7. The **`employees` fact is collected but unused**. The licence name behind `home_based_licence` is marked UNVERIFIED.
8. **Monitoring is built and tested but not scheduled.** The Firecrawl trial used 21 of 100 credits. Confirm this fits the zero-spend and never-buy-credits rule (it appears to be a free allowance, which I have not verified).
9. **The reviewer sign-off endpoint has no automated test.**
10. Minor: commit 81ad77c describes a "48-topic provision map", but `CL_provision_map_v7.json` has 47 topic keys. The package may count differently (low confidence).
