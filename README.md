# HerBiz 360 — compliance assistant prototype for UAE home businesses

> **Prototype with fictional businesses and synthetic data.** It is not legal, tax or accounting advice. No qualified professional has reviewed it, and it does not make compliance decisions. HerBiz does not file or pay anything. It is an independent project, not affiliated with or endorsed by the Federal Tax Authority (FTA), the Ministry of Finance or any UAE authority.

HerBiz helps a person who runs a small business from home in the UAE see what may apply to them, such as VAT, corporate tax, records and licence renewal. For each item it shows:
- what is missing;
- which documents help;
- which official source the item comes from;
- when to ask a professional.

Where the law has not been checked by a qualified person, it refuses to give a definite answer or deadline.

This repository is a snapshot of an entry to the ITU AI for Good Sandbox Hackathon (UAE). It has no git history. Demo source snapshot: 17 October 2026. The exact source commit is in `CL_EXPORT_FILE_MANIFEST.json` and `capabilities.json`.

## 1. Requirements
- **Python 3.11.4 or newer.** This snapshot was tested with 3.11.9 on macOS. The Python 3.9.6 that ships with macOS does not work. Running the demo and the tests needs only the Python standard library.
- **No API keys, no paid services and no internet connection** are needed for the demo or the tests. The demo never calls an AI model.
- **Optional:**
  - **Node.js:** one test checks that the page scripts parse. Without Node it is skipped.
  - **pypdf:** improves PDF text extraction if you rebuild the knowledge base (see section 5). It is listed in `requirements-optional.txt`.

## 2. Quick start
Run every command from the repository folder.

```bash
python3 experiments/ws_a/CL_run_export_tests.py
```

This runs the **public test manifest** (`tests/MANIFEST_PUBLIC.json`): the 336 tests that run in this repository as shipped. They should all pass. While they run, a guard fails any test that opens a restricted file (a database, the experiment ledger, raw official files, held-back files or a sibling checkout). Tests and failure records are counted separately: one test with several failing sub-cases is one failed test.

To run every test (507), with the reason for each one that cannot run here, use `--manifest all`. See section 7.

```bash
python3 -m compliance_agent.web --port 8772
```

Then open **http://127.0.0.1:8772/360** in a browser. The server binds to your own computer only (127.0.0.1). On first start it creates an empty local workspace database at `data/CL_test_workspace.sqlite3`.

To replay the 13 error and controversy scenarios and write the results to a folder of your choice:

```bash
python3 experiments/ws_a/CL_error_scenarios.py --out /tmp/herbiz_scenarios --synthetic-answers
```

Without the held-back recorded answers, scenarios E10 and E11 run on a synthetic test fixture with no legal text (`tests/fixtures/CL_synthetic_vat_answers.json`), and their result says **"PASS (synthetic fixture)"**. They prove that the warning and refusal logic works. They say nothing about the quality of the real recorded answers. Without `--synthetic-answers`, E10 and E11 are skipped.

To replay one of the three Task 2 error scenarios step by step, with an audit record per step:

```bash
python3 -m compliance_agent.scenarios replay SC-3
```

## 3. The demo journey
The demo has a start screen and seven steps. Use **Presenter controls → Reset demo** before each run.

| Step | What you see |
|---|---|
| 0. Start | What HerBiz is, the banner and the snapshot date. |
| 1. Your business | Answer plain questions about a fictional business. "Not sure" is always allowed; it becomes a question, never a guess. Invalid input gets a message under the field. You can also use one of the fixed fictional businesses. |
| 2. Overview | Each obligation shows a status, the reason, missing facts, documents and the next step. Most items read **"Blocked: legal validation"** on purpose. VAT items show **no date**: "No date is shown until a qualified reviewer has checked the rule and its sources." Each item has its official source, its uncertainty, "Source found, not reviewed" and the date it was copied. |
| 3. VAT | The VAT items for this business, and recorded answers to fixed questions if the answers file is present (see section 6). Otherwise the step says the answers are not included. It never invents an answer. Each source of a recorded answer shows its validity. A recorded answer that relies on an article recorded as repealed, amended or in conflict is **withheld**: no answer text and no quotes. Today this affects one recorded question (V24). |
| Ask a question (classic page `/`) | A free-typed question with no recorded answer gets the most relevant official passages, never an answer, each with its source's validity (current, outdated, conflicting) and, where one exists, the current official link (shown, never opened). Every such answer is marked "may be incomplete". This needs the knowledge-base database; without it HerBiz says the search is unavailable. |
| 4. Corporate tax | **Demo scenario — fictional business.** Questions, a document checklist and possible steps only. Corporate tax stays blocked until a qualified reviewer checks the rules, and the withheld items are listed. |
| 5. Money and records | Synthetic transactions, missing receipts, a draft "money in minus money out" labelled as a management estimate (not financial statements and not a tax computation), and a CSV download for an accountant. |
| 6. Getting help | What the owner can do, and when an accountant or an FTA-registered tax agent is needed. |
| 7. Rule changes | A real official amendment (Ministerial Decision No. 131 of 2026, which amends the Small Business Relief decision). An unreviewed summary flags the affected item **"changed — pending review"**. Nothing changes automatically. |

## 4. How it is built (ITU-T Y.3172 view)
| Y.3172 node | Here |
|---|---|
| SRC | Official UAE sources (register: `knowledge_base/`) and the owner's answers |
| C | Collector restricted to official hosts, with a hash lock (`compliance_agent/kb.py`, `knowledge_base/CL_collected_lock.json`) |
| PP | Text extraction with article locators; SQLite FTS5 search; profile validation (`compliance_agent/llm_lab/`, `compliance_agent/profiles.py`) |
| M | Obligations engine, deterministic, with rules as data (`compliance_agent/obligations/`, Workstream B); recorded model answers (`compliance_agent/ask.py`) |
| P | Policy and safety checks: fail closed, corporate tax blocked, wording scan, "may be incomplete" guard, protected-database refusal, personal-data intake check (`compliance_agent/mvp360/adapter.py`, `compliance_agent/dbsafety.py`, `compliance_agent/rag_c/policy_gate.py`, `knowledge_base/policy/`) |
| D / SINK | Owner dashboard (`compliance_agent/ui360.html`, `compliance_agent/web.py`) |

The architecture diagram is `docs/360/submission/CL_HERBIZ360_ARCHITECTURE.png`. The mapping explains the design; it does not claim conformance with the standard.

**Pinned parts.** The engine (Workstream B, commit `89dc2b9` = `t2-b-rc1`, fixture `ws-b-demo-0.4`) and the source interface (Workstream C, commit `aa50dd4`, contract `sources360 0.2`) are included as plain folders under `vendor360/`. Workstream C's Task 2 data (source validity 1.2, link status, scenario source sides, knowledge-base manifest v0.2.1) come from commit `8f35b20` (`t2-c-rc2`).
- `vendor360/CL_VENDOR_MANIFEST.json` lists every file with its sha256.
- The app checks every file before using it. It refuses to run if any file is changed, missing or extra.
- One file differs from its commit: the engine's demo fixture. Eight local folder paths were replaced with `<LOCAL_PATH>`. The manifest records both checksums, and test 117 checks that nothing else changed.
- The personal-data intake check (`policy_gate.py` and `knowledge_base/policy/`) comes from Workstream C commit `e01c371`. Only those files come from that commit; the tax sources stay at `aa50dd4`. Both pins are in `docs/360/CL_DEMO_SNAPSHOT.lock.json`.

**Personal-data intake check.** HerBiz checks owner questions and reviewer notes for common UAE personal-data formats and does not pass inputs containing them to search, storage or logs; which checks run and what happens comes from its policy knowledge base. Pattern checks miss names, addresses and unusual formats.
- Questions are accepted only in the body of a POST request. A question in a web address is refused.
- When an input is refused, HerBiz returns the policy message and the clause ids, labelled "Design references". It does not search, echo, store or audit the input.
- The check log keeps identifiers only: the action, control, detector and clause ids, and the policy version. It never keeps the text, the matched value or a hash of it.
- If the check or its policy file fails, the input is refused (fail closed). Tests 123–133 and Workstream C's tests 197–216 cover this.
- The four governance references in `knowledge_base/policy/` (UAE PDPL, Federal Decree-Law No. 45 of 2021; UAE AI Charter; UAE National Strategy for AI 2031; Dubai AI Ethics) are collected, not activated or legally assessed.

## 4a. Audit records, error scenarios and capability declaration
- **Audit records.** Every answer shown to an owner (questions, overview, corporate tax, money and records, rule changes, scenario steps) writes one record (`contracts/audit_record_1.0.schema.json`) to a daily, hash-chained log next to the workspace database. An independent sanitizer refuses any record with passage text, personal-data patterns, local paths or long strings. If the record cannot be written, the answer is withheld ("HerBiz could not record this answer, so it is not shown."). A blocked question leaves no text and no hash. The audit view exists only when the server is started with `--reviewer-mode`. Check a log with `python3 -m compliance_agent.audit_log verify <file> --scan`. Sample logs: `docs/360/evidence/audit-logs/`.
- **Error scenarios SC-1 to SC-3** (synthetic): missing information, conflicting rules and an outdated source. Events are released one at a time (**Presenter controls → Error scenarios**, or the command in section 2), and each step is checked against its expected flags.
- **Capability declaration.** `capabilities.json` (`contracts/capability_declaration_1.0.schema.json`) separates what the agent actually does:
  - **deterministic:** rules, search, validity checks, the intake gate, audit;
  - **recorded model output:** VAT answers from `claude-sonnet-5-5`, recorded 16 Oct 2026 and replayed;
  - **proxy outputs:** offline evaluation only;
  - **live inference: none**;
  - **tool use:** reads local files and writes its own log; never browses, fetches, files, pays or sends;
  - **simulated:** fictional businesses, test rules, reviewer, scenarios;
  - **planned:** not built.

  Every `execution_mode` in an audit record is one of the active declared classes (`tests/test_capabilities.py`).
- **Contracts.** `contracts/` holds the six frozen JSON Schemas (index sha256 `237dfe23…`), golden fixtures and a standard-library validator.

## 5. Knowledge base
**Included:**
- `kb_export/CL_HERBIZ_KB_MANIFEST.json` (version 0.2.1, from Workstream C commit `8f35b20`, built from the pinned sources at `aa50dd4`): a publication-safe manifest of the knowledge base. It lists official URLs, titles, issuers, dates, article locators and content and passage hashes, but no official text. Its 5 version fingerprints and 371 passage fingerprints match the database the agent was tested with. Its builder lives in Workstream C's repository and needs the private database, so it is not included here.
- the source register (official URLs, issuing authority, evidence level, review status);
- `knowledge_base/t2/CL_source_validity_1.2.json`: validity status for 110 source records (current, outdated, superseded, conflict or not collected). These records are Workstream C's working evidence, not independently verified legal content. Where a current official page is listed but its contents have not been checked by a person (for example portal entries 1227 and 1972), HerBiz says so;
- the sha256 lock of every collected official file;
- the article-heading map;
- the synthetic test questions and profiles.

**Not included:**
- the official FTA files and the database built from them. The reuse terms for redistributing those files are not confirmed;
- `compliance_agent/llm_lab/data/CL_article_index_v6.json`, a retrieval table that holds the opening text of each official article, for the same reason. The retrieval evaluation scripts need it. Regenerate it after the rebuild below:

```bash
python3 experiments/ws_b/CL_build_v6_tables.py data/CL_test_workspace.sqlite3 /tmp/herbiz_tables
```

Then copy `CL_article_index_v6.json` from that folder into `compliance_agent/llm_lab/data/`.

**Rebuild the knowledge base yourself (optional; downloads public files from the FTA site):**

```bash
python3 -m compliance_agent.kb collect --allow-network
python3 -m compliance_agent.kb setup
```

`collect` only downloads from the official hosts on the allow-list, and records each file's sha256. `setup` builds the search index offline from the downloaded files and refuses any file whose hash does not match the lock. If the FTA has changed a file since 16–17 October 2026, its hash will differ. In that case the rebuilt text is not the one this snapshot was tested on, and `setup` reports it. Older captures of a web page cannot be downloaded again; they are reported as missing.

**Reproducibility of the fingerprints.** A rebuild from the locked official files matches the manifest exactly for the Decree-Law and the registration page. The three Executive Regulation versions differ only in their first two pages, because the current extractor splits out Article 1 (a fix made after the tested database was built). 365 of the 371 passage hashes match.

**Reproducibility of the retrieval figures.** The retrieval results (L1) were measured on the development team's private copy of the knowledge base, which has 162 articles. A rebuild from the locked official files has 163: it also includes Executive Regulation Article 1. Every other article is identical, and the rebuilt retrieval tables have one extra cross-reference. So re-running the evaluation on a rebuilt knowledge base may not give exactly the same figures.

**What works without the knowledge base:**
- the whole owner journey: steps 0–2 and 4–7, and the VAT items in step 3;
- the tests, which skip the cases that need the texts, each with a reason.

**Effect of the missing database on the engine.** The engine's VAT source-validity check is tied to one specific database file, so here it reports "unavailable" and fails closed. The owner view is the same with or without it; test 118 checks this.

## 6. Recorded VAT answers (step 3)
The VAT answers in the demo were recorded from a large language model (Claude) in earlier test runs. They are replayed, and no model is called. They quote official FTA texts, so they are **not included in this snapshot** until redistribution is confirmed.

**Without the answers file, step 3:**
- says there is no recorded answer;
- shows official passages only if you rebuilt the knowledge base;
- never shows a made-up answer.

If the answers file is added at `fixtures/mvp360/CL_recorded_vat_answers.json`, step 3 replays exactly what the development version shows. Test 119 checks this where the original ledger exists.

## 7. Tests that cannot run here
`python3 experiments/ws_a/CL_run_export_tests.py --manifest all` runs all 507 tests. On this repository as shipped:

| Group | Tests | Why |
|---|---|---|
| Public manifest | 336 | Run and pass here (the default run) |
| Skipped | 155 (154 where Node.js is installed: one test checks the page scripts with Node) | Each states its reason, for example "main database not built" |
| Need the held-back retrieval table | 13 | Workstream B's offline classifier and retrieval-v7 tests load `CL_article_index_v6.json`, which is not in this snapshot (section 5). One of them, `test_c1_02`, fails closed when the table is missing |
| Need a private database copy | 3 | `test_obligations` tests 20, 23 and 45 |
| Need a Workstream C checkout beside this folder | 1 | `test_obligations` test 82 loads WS C's labels with `git archive`; the app itself uses the vendored copy, which test 88 covers |

The 17 tests in the last three groups give 35 failure records, because one test can fail on several sub-cases. Tests and records are counted separately. None of these tests is counted as passed. `tests/MANIFEST_PUBLIC.json` lists every test left out of the public manifest, with its reason.

## 8. Known limitations (stated, not hidden)
| # | Limitation | Effect |
|---|---|---|
| L1 | **Retrieval performance exception (open).** For free-typed questions, the interim retrieval (v8; deterministic; frozen code) found **all** required VAT provisions for **66.7%** of one independent test set (v10), **70.4%** of a second (v11) and **68.5% pooled (37/54)**, against a 70% target, which is **not met**. It classified 4 of 27 (v10) and 1 of 27 (v11) valid VAT questions as out of scope. It never claims completeness, so **every answer is marked "may be incomplete"**. Zero silent-incomplete answers holds by that construction; it is not evidence that HerBiz detects complete answers. The recorded answers were retrieved with an earlier method (44% on an older unseen set). | Every answer is warned and names missing provisions where known. Treat everything as possibly incomplete. |
| L2 | No qualified UAE VAT or corporate-tax reviewer has checked any rule, summary or citation. The sources are official but **unreviewed**. | Everything is a demonstration draft. Corporate tax is always blocked. No dates are shown for real-law items. |
| L3 | VAT answers are **recorded model outputs**, not live AI, and are not included here (section 6). | The demo is repeatable. Free-typed questions get "No recorded answer". |
| L4 | The reviewer in the demo is **simulated**. | The review queue shows the process only. No real review has taken place. |
| L5 | Licence and payroll items use synthetic test rules. | They are labelled "TEST RULE — not law". |
| L6 | No privacy review under the UAE Personal Data Protection Law has been done. The intake check is a pattern check: it misses names, addresses and unusual formats. Real data is not accepted. | Fictional businesses only. |
| L7 | Fixed source snapshot: 17 October 2026. The pinned copy of the VAT Decree-Law predates its 2026 amendments (Federal Decree-Law No. 16 of 2025), so Articles 48 and 74, among others, are **outdated** in this copy. The current official text has not been checked by a person. | Passages from outdated sources are labelled "Outdated: amended since", with the current official link shown, never opened. Recorded answers that rely on an amended or repealed article are withheld. Later official changes are tracked separately and are never added silently. |
| L11 | **Free-typed questions use the whole-source status (deferred change 1b).** A passage from an unamended VAT Decree-Law article is labelled "Outdated: amended since", because the whole pinned copy predates the 2026 amendments. Recorded answers use the article-level rule instead. So the two paths can label the same article differently. | Both labels are cautious; nothing is shown that should be withheld. Founder/CTO decision D-124: deferred. |
| L12 | **The "not checked by a person yet" note cannot clear yet (deferred change 3, DEF-T2-01).** The note and the audit flag `pending_unverified_link` test for a status value the data never uses, so they would stay even after the founder's check of a page is recorded. No such check is recorded in this snapshot. | Correct and cautious today. It must be fixed before any founder page check is added to the data. D-124: deferred. |
| L8 | VAT items on the overview have no per-item citation (no shared identifier yet between the engine and the source register). | VAT sources are shown in step 3. |
| L9 | Reviewer notes and the audit logs are kept in append-only records. Their retention is unresolved. The intake check stops common personal-data formats, but notes cannot be deleted, and no deletion or retention limit is claimed. The app has no login or roles. | Synthetic notes only. Before any real use, a retention option is chosen after review by a UAE-licensed lawyer. |
| L10 | No real-user testing yet. | No usability claims. |

## 9. Folder guide
| Path | Contents |
|---|---|
| `compliance_agent/` | App code: web server, pages, owner adapter (`mvp360/`), engine (`obligations/`), source tools (`rag_c/`), retrieval and model lab (`llm_lab/`) |
| `vendor360/` | Pinned Workstream B and C copies with the sha256 manifest |
| `tests/` | Automated tests (unittest); `MANIFEST_PUBLIC.json` and `MANIFEST_INTERNAL.json` |
| `contracts/` | Six frozen JSON Schemas, golden fixtures and a validator |
| `capabilities.json` | Capability declaration (what is deterministic, recorded, simulated, planned; no live inference) |
| `fixtures/` | Synthetic profiles, test questions and demo content |
| `knowledge_base/` | Source register, collection lock and metadata (no official texts) |
| `experiments/` | Scripts for evidence, scenarios and evaluations. Scripts that can call a paid model need your own API key and stop at the spending cap in their authorisation file; the demo and the tests never call a model |
| `docs/` | Architecture, evaluation evidence, snapshot lock, change report, screenshots |
| `CL_EXPORT_FILE_MANIFEST.json` | Every file in this snapshot with its sha256; what was excluded and why |

## 10. Licence and ownership
- **Code:** Apache License 2.0 (see `LICENSE`). Copyright 2026 Connect 360 Advisory FZE LLC.
- **Official texts are not included** and are not covered by this licence. FTA and MoF texts are referenced by link, article and hash only.
- **Published:** for the ITU AI for Good Lab Hackathon (UAE), November 2026. Essential code only, synthetic data only.
- **Known test exception (9 Nov 2026):** in the full private suite, six internal lab tests (`test_c1p`/`test_c1p2` 03, 05, 06) fail after 24 Oct 2026, because a safety rule refuses a source-status export older than 7 days (the export is dated 17 Oct 2026). They pass with the original clock. They are not part of the public test set, which passes 336/336.
