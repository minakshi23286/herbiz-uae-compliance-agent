# WS-B final sign-off note: HerBiz obligations engine

**Business line: HomepreunerHub / HerBiz** · Workstream B · 17 Oct 2026 · founder decisions D-066 and D-089

**Status**
- **WS-B is closed.** It reopens only if WS-A reports a verified integration defect.
- **Not done:** no merge to `main`, no deployment, no publication.

> Draft prototype, not reviewed by a qualified professional. It is not legal, tax or accounting advice.

## 1. The engine is unchanged (verified 17 Oct 2026)

| Check | Result |
|---|---|
| Engine, catalogues, fixtures, demo outputs, scripts | **Unchanged since `fdbe131`**: `git diff --quiet fdbe131 HEAD -- compliance_agent fixtures experiments` passes |
| Non-documentation change since `fdbe131` | **One file added:** `tests/test_signoff_endpoint.py` (commit `4ef0bf9`). Every other commit after `fdbe131` is documentation only. |
| Interface | `ws-b-demo-0.3`; fixture sha256 `1b8d2c38…` (private) and `82b85c5d…` (8 local paths removed, for the public export) |
| Protected database | md5 `26e202b87a062288e56bcda1de9b0217`, unchanged |

## 2. Latest test results

| Environment | Ran | Passed | Skipped by design | Not runnable (reason) |
|---|---|---|---|---|
| **Private repository** (`ws-b-retrieval` @ `4ef0bf9`, with the DB copies and the WS-C repository) | 220 | **220** | 0 | 0 |
| **Public-like copy** (`4ef0bf9`, without `data/*.sqlite3` and without `CL_article_index_v6.json`; WS-C repository present) | 220 | **102** | 84 | **34:** 3 need a private DB copy; 31 need withheld official text |

The 102 tests that pass in the public-like copy include **all 7 H360-13 tests** and the engine's safety tests. The exceptions are test_20, test_23 and test_45, listed below.

**The 34 tests that cannot run publicly are not reported as passed.**

1. **Database-dependent (3):** `test_obligations.Validity.test_20_pinned_export_loads_on_exact_copy`, `test_obligations.Validity.test_23_real_vat_provisions_not_certified_today`, `test_obligations.SafetyAndData.test_45_db_copies_unchanged`. They need the byte copies of the protected database, which are never published.
2. **Dependent on withheld official text (31 results):** the `test_c1`, `test_c1p`, `test_c1p2`, `test_retrieval_v6` and `test_retrieval_v7` classifier and retrieval tests (subtests count separately). They load `compliance_agent/llm_lab/data/CL_article_index_v6.json`, which holds article titles and opening text from FTA texts. That file is withheld under D4 (metadata-only publication).

**The 84 skips** are existing guards in older WS-B suites. They skip themselves when the exact DB copy and WS-C's worktree are absent ("needs the exact DB copy and Workstream C's worktree (read-only)").

**Cross-check with WS-A.** WS-A's `docs/360/export/CL_HERBIZ360_PUBLICATION_READINESS_REPORT.md` and `CL_HERBIZ360_CLEAN_CLONE_VERIFICATION_REPORT.md` (@ `a4a9390`) report the same 3 + 31 for the export. WS-A's whole-export totals cover all workstreams, so its counts are not comparable to WS-B's.

**WS-C repository.** If the public copy also lacks it, one more test cannot run: `test_83`, which loads WS-C labels through `git archive` and fails closed. WS-A's export supplies the WS-C files.

## 3. H360-13 integration instructions for WS-A (approved under D-089)

| Item | Value |
|---|---|
| Commit | `4ef0bf9` on `ws-b-retrieval` |
| File to add | `tests/test_signoff_endpoint.py` (new file; it replaces nothing) |
| Code it tests | the existing `/api/signoff` in `compliance_agent/web.py` and `dbsafety.ensure_workspace`. No app or engine change is needed. |
| Get the file | `git show 4ef0bf9:tests/test_signoff_endpoint.py > tests/test_signoff_endpoint.py` (run in WS-A's checkout) |
| Run | `python3 -m unittest -v tests.test_signoff_endpoint`. Expect 7 tests OK. It needs no private DB: when the source DB is missing, the workspace is created empty. |
| Safety | All writes go to a temporary workspace. Each test checks that the source DB md5 is unchanged. |
| Expected totals | One run of the whole suite gains 7 tests: the private repository +7 and the public export +7. Update the report figures (WS-A P5). |
| Engine and fixture | Unchanged. No re-pin and no new fixture checksum. |

## 4. References

- Evidence: `docs/360/WSB_COMPETITION_TECHNICAL_EVIDENCE.md`, latest documentation commit on `ws-b-retrieval`. It covers L1–L12; L12 is the public-export limitation.
- Privacy scan: `docs/360/publication/CL_WSB_PRIVACY_AND_SECRETS_SCAN.md`.
- Scrubbed WS-B export (not published): `Compliance Operations Agent/CL_HERBIZ_WSB_PUBLICATION_EXPORT_2026-10-17/`.
- Handoff: `docs/360/CL_WS_B_TO_A_INTEGRATION_HANDOFF.md`.
- Register entries: D-061, D-062, D-064, D-066 and D-089.

## 5. Closure

WS-B work is complete. No new product development will start. Any further WS-B work is limited to:
- privacy;
- evidence;
- reproducibility;
- competition requirements;
- verified defects reported by WS-A.
