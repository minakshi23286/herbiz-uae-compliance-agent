# WS-B privacy and secrets scan, before the publication request

**Business line: HomepreunerHub / HerBiz** · 17 Oct 2026 · scope: every tracked file on `ws-b-retrieval` at `ed83032` (254 files), plus that branch's git history and commit metadata · read-only scan with no network · **status: scan done; publication not requested**

## Results

| Check | Method | Result |
|---|---|---|
| API keys and tokens | Regex for `sk-ant-…`, `sk-…`, `AKIA…`, `ghp_…`, `xox[bp]-…`, `AIza…`, Firecrawl `fc-…`, private-key blocks | **None** |
| Hard-coded secret assignments | Regex for `api_key / secret / token / password = '…'` | 1 hit: `docs/ai/CL_LLM_REVISED_IMPLEMENTATION_PLAN.md:32` sets `ANTHROPIC_API_KEY='paste-your-new-key-here'`. It is a placeholder, not a key. |
| Secret files | `.env*`, `*.pem`, `*.key`, credentials | `.env.example` only, which contains "No secrets are needed" |
| Secrets in history | `git log -p -S"sk-ant-"` | **None** |
| Absolute local paths or user name | Regex `<LOCAL_PATH>`, `<LOCAL_PATH>`, user name | **9 files, 23 lines**, listed below |
| E-mail addresses in files | Regex | **None** |
| Phone numbers (UAE formats) | Regex | **None** |
| Binary metadata | xlsx `docProps` (creator "openpyxl"); demo sqlite strings; 15 jpg screenshots (EXIF and author) | **Clean** |
| **Commit author metadata** | `git log --format=%ae` | **55 commits carry the founder's personal Gmail address as author.** Publishing the repository *with history* would expose it. |
| Local paths in history | `git log -G"/Users/<user>"` | 11 commits introduced local paths. Publishing *with history* would expose them even after the files are fixed. |

## Files with local paths (at `ed83032`)

| File | Lines |
|---|---|
| `docs/360/demo/wsa/CL_WSA_DEMO_FIXTURE_v1.json` | 8 (limitation L1) |
| `docs/360/demo/CL_obligations_demo_blocked.json` | 6 |
| `CL_OVERNIGHT_WS_A_REPORT.md` | 2 |
| `CL_WS_A_TO_C_RAG_HANDOFF.md` | 2 |
| `MORNING_HANDOFF.md` | 1 |
| `docs/CL_BOS_CAPABILITY_AUDIT.md` | 1 |
| `docs/CL_evidence/ws_b/CL_c1p2_v9_offline_proxy_eval.json` | 1 |
| `docs/CL_evidence/ws_b/CL_c1p_v8_offline_proxy_eval.json` | 1 |
| `project/CL_project_status.json` | 1 |

The first two files are scrubbed in the WS-B export. The others are not part of the WS-B export; four of them come from `main`, WS-A or WS-C.

## WS-B publication-safe export

The export is at `Compliance Operations Agent/CL_HERBIZ_WSB_PUBLICATION_EXPORT_2026-10-17/` and is **not published**.
- 64 source files plus `EXPORT_README.md`.
- A re-scan after scrubbing found 0 path, user-name or e-mail hits and 0 secrets.
- There is no git history, so neither author e-mails nor path history are included.
- The scrubbed fixture's sha256 is `82b85c5d…`. This differs from WS-A's pinned `1b8d2c38…`, and only because of the scrubbed paths.

## Points to resolve before any publication (founder / WS-A, which owns CR-03)

1. **Publish without history.** Push a fresh snapshot (for example from `git archive`), not the existing branches. Otherwise the founder's personal e-mail (55 commits) and 11 path-introducing commits become public.
2. **Scrub paths across the whole repository.** The 7 remaining files with paths need the same scrub in the full repository export, which is owned by WS-A.
3. **Explain the fixture checksum.** If the published fixture is the scrubbed one, the published checksum is `82b85c5d…` and the submission should say why it differs from the pinned file.
