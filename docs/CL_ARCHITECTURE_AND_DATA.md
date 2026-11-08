# HerBiz: Compliance Agent — Architecture, data, backup and restore

**Business line:** HomepreunerHub / HerBiz · **Prepared by:** Claude Code · **Status:** built · **Date:** 16 Oct 2026

## Stack (chosen after inspecting the BOS)
- Python 3.11 standard library + SQLite 3.45 with FTS5. Same approach as the BOS Control Center generator (stdlib only).
- Optional PDF text extractor: `pypdf` (6.8.0 found installed); fallback `pdftotext` (poppler). See `requirements-optional.txt`. Certificate checks use `certifi` when present (python.org builds on macOS ship without a CA bundle).
- No n8n, Pinecone, Supabase, messaging or model API. The BOS Supabase schema exists only as files and was never executed (BOS Stage 3 report); the BOS database was **not** migrated or reused.

## Database
| Item | Value |
|---|---|
| Engine | SQLite (single file) |
| App database | `data/CL_compliance.sqlite3` (git-ignored) |
| Built by | `python3 -m compliance_agent.kb setup` (offline, from `data/raw/` + `knowledge_base/CL_collected_lock.json`) then `python3 -m compliance_agent.evaluation` |
| Original documents | `data/raw/<source_id>/<sha256-16>.pdf|html` (git-ignored; reuse terms unconfirmed). Hashes, sizes, URLs, times in `knowledge_base/CL_collected_lock.json` (committed) |
| Schema version | `meta.schema_version = 2`; columns added idempotently on open (older databases keep working) |

### Tables
| Table | Holds | Notes |
|---|---|---|
| business_profiles | versioned synthetic profiles | `synthetic` must be 1 |
| source_versions | original/extracted text per captured version, status, change class, flags, origin label | text and hash frozen by trigger |
| documents | each captured file: URL, time, sha256, path, extractor, empty pages, extraction note | |
| passages + passages_fts | extracted units with article/page locators; FTS5 index (porter) | label UNVERIFIED_EXTRACTION |
| collection_attempts | every fetch outcome incl. refused/failed | |
| obligations | interpretations: conditions, action, interpretation status, quote-check status | separate from source text |
| assessments | per profile version and obligation: result, rationale, missing facts, citations | `current` flag |
| cases | actions, clarifications, conflicts, source and interpretation reviews | unique `dedupe_key` (retry-safe) |
| reviews | every human decision incl. refused attempts | name, role, note, time |
| alerts | de-duplicated notices | unique key |
| audit_events | append-only history | update/delete refused by trigger |
| evaluation_runs / evaluation_results | stored scenario runs | |
| reviewer_signoffs | domain-reviewer sign-off register | empty until a real reviewer acts |

## Flow
collect (allowlisted official hosts) → snapshot + hash → extract (pypdf / pdftotext / html.parser; running headers removed; footnote-merge repairs recorded) → passages + FTS → source version **candidate** → reviewer approves source → draft interpretation with quotes → quote check → reviewer approves interpretation → used in applicability → cases → evidence → reviewer → history.

## Security (local foundation only)
- Binds to 127.0.0.1; rejects non-local Host headers (DNS-rebinding guard) and POSTs without the UI header; 64 KB body limit; strict CSP; no authentication (single local user) — **blocker to any external use**.
- Source text is data: instruction-like text is flagged and blocks approval unless acknowledged; nothing in source text is executed.
- Fetch allowlist: tax.gov.ae, mof.gov.ae, u.ae, elaws.moj.gov.ae, uaelegislation.gov.ae; https only; redirects re-checked; 40 MB cap; certificate verification on.
- No secrets exist in this project; `.env.example` lists none needed.
- Time: Asia/Dubai, injectable clock (`--clock`) for demos and tests.

## Backup and restore
```bash
python3 -m compliance_agent.backup backup
```
```bash
python3 -m compliance_agent.backup verify data/backups/<file>.sqlite3
```
```bash
python3 -m compliance_agent.backup restore data/backups/<file>.sqlite3 --yes
```
Restore keeps the current database as `*_before_restore_<time>.sqlite3`. Stop the app first. Copy `data/raw/` separately (or re-collect). Rebuild from scratch, offline: `python3 -m compliance_agent.kb setup --db data/<new>.sqlite3`.
