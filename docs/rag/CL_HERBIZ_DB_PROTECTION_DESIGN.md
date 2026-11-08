# HerBiz: Compliance Agent — Reversible database-protection design

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** 17 Oct 2026 · **By:** Workstream C, branch `ws-c-source-intelligence` · **Status:** designed; layers L1 and L5 implemented; L2–L4 **tested on copies only**. **Nothing applied to the original** (D17 deferred, D16 pending) · **Not legal or tax advice.**

Protected files:
- the authoritative knowledge base `CL_compliance_agent_app/data/CL_compliance.sqlite3` (md5 `26e202b8…` on 17 Oct);
- the experiment ledger `CL_llm_experiment.sqlite3` (`59226cd0…`).

Evidence for every "measured" statement: `docs/CL_evidence/ws_c/CL_db_protection_experiments_2026-10-17.json` (script alongside), run on byte copies; the original was only inspected read-only.

## 1. Layers
| Layer | What it stops | What it does not stop | How to reverse | Measured on a copy, 17 Oct |
|---|---|---|---|---|
| **L1 code guards** (`dbsafety`) | any `kb`, `backup restore`, evaluation, web or dry-run command aimed at a protected file: by path, by name in any checkout, by symlink or hard link; errors fail closed | code that ignores the guard (sqlite3 shell, other scripts); the **main checkout still runs the old code** | revert the commit | QA tried 12 bypass variants, all refused |
| **L2 file mode 0444** | every write by any program (SQLite: "attempt to write a readonly database"); the app's `Store()` fails closed on open | delete, rename or replace of the file (the folder is writable); `chmod` back | `chmod 644 <file>` | write refused; read-only reads OK; no side files; revert OK |
| **L3 macOS user-immutable flag** (`chflags uchg`) | writes **and** delete, rename, chmod, even by the owner | `chflags nouchg` by the owner (deliberate step); root | `chflags nouchg <file>` | write, rm, rename and chmod all refused; read OK; revert OK |
| **L4 hardening triggers** (`C_PROTECT_*`, decision D16) | inside SQLite: `INSERT OR REPLACE` forgery of audit rows (the QA D2 attack); UPDATE or DELETE of passages; DELETE of documents and source versions; changes to a document's sha256, raw_path, url or bytes | `DROP TRIGGER` (so L4 needs L2/L3); a status change (allowed on purpose: review and approval must work) | `rag_c.protection.remove_triggers()` drops exactly the 8 `C_PROTECT_*` triggers | 4 attacks blocked; legitimate `kb rebuild` and `review_source` approval still work; rollback exact |
| **L5 read-only opens** | accidental writes by readers | — | — | `connect_ro` (`?mode=ro`) everywhere in `rag_c` |

**Recommended combination:**
- **Day to day:** L1 + L2, plus L3 when nobody is working on the database.
- **After D16 is approved:** add L4.

All of these are reversible in seconds and none changes the database content.

## 2. SQLite journal and WAL behaviour (measured)
| Mode | Read-only open (`?mode=ro`) of a writable file | File mode 0444 | `?immutable=1` |
|---|---|---|---|
| **rollback journal, `journal_mode=delete`** (the original's mode today) | creates **no** side file | reads OK | not needed |
| **WAL** | creates `-wal` and `-shm` beside the file **even for a read-only open** | reads OK when no `-shm` is needed; otherwise may fail | reads OK, with no side files, but SQLite then assumes the file never changes |

**Rules:**
- **Never switch the authoritative file to WAL.** Readers would create side files next to evidence, and a protected (0444 or immutable) WAL database can fail to open.
- Keep `journal_mode=delete`. `rag_c protect-status <file>` reports it.
- Use `immutable=1` only for frozen, read-only snapshots (e.g. a published read copy), never for a file that may still be written.
- A crash during an authorised write leaves a `-journal` file. **Do not delete it**: SQLite uses it to roll back on the next open. `status()` lists side files so a person sees them.

## 3. Authorised maintenance operations
| Operation | Needs | Steps (each logged in the change log and `audit_events` where the app writes) |
|---|---|---|
| Re-ingest or rebuild the knowledge base | founder approval + named reason | build into a **new** file (`rag_c dryrun --out`), diff, review; replacing the authoritative file is a *restore* (below) |
| Reviewer approval of a source version (D3) | qualified reviewer | 1. backup (read-only source); 2. lift L3/L2 for the window; 3. run the app command with `--write-authoritative`; 4. verify (`integrity_check`, expected row changes only); 5. re-apply L2/L3; 6. record the new md5 |
| Restore from backup | founder approval | `backup verify` the file; lift L3/L2; `backup restore … --db <authoritative> --write-authoritative --yes` (keeps a `_before_restore_` copy); verify; re-protect |
| Apply L4 (D16) | founder approval | test on a copy (done 17 Oct), backup, lift L3/L2, apply, run the test suite against a copy of the result, re-protect |
| Schema migration | founder approval + reviewer for content | the same as L4, plus a rollback script prepared in advance |

**Window rule:** protection is lifted for one named operation, by the founder or with the founder's approval, and re-applied straight away. "Before" and "after" md5s are recorded. **No automated job** (monitor, scheduler, agent) ever lifts protection.

## 4. Tooling
- **Built:** `compliance_agent/rag_c/protection.py`:
  - `status(path)`: read-only report of mode, immutable flag, hard links, code-guard result, journal mode, side files and triggers;
  - `apply_triggers` / `remove_triggers`: copies only; they **refuse** protected files, so D16 cannot be applied by accident.
- **Tests:** 151–153.
- **Not built (on purpose):** any command that lifts or applies OS protection on the original. Those are manual, founder-run steps:
```bash
chmod 444 data/CL_compliance.sqlite3 data/CL_llm_experiment.sqlite3          # L2 on
chflags uchg data/CL_compliance.sqlite3 data/CL_llm_experiment.sqlite3       # L3 on
chflags nouchg data/CL_compliance.sqlite3 data/CL_llm_experiment.sqlite3     # L3 off (maintenance window)
chmod 644 data/CL_compliance.sqlite3 data/CL_llm_experiment.sqlite3          # L2 off
```
(run inside `CL_compliance_agent_app/`; **D17 is deferred, so none of this has been run**).

## 5. Effect of L2/L3 on other workstreams (checked by reading code)
- **The demo web app and evaluation:** already use the test workspace copy, so no effect.
- **B's tests:** open the DB read-only, so no effect. B's `budget.py` writes its **own** ledger file, so no effect unless pointed at the protected ledger.
- **A scheduled monitor:** writes only `data/monitor/`, so no effect.
- **What would fail on purpose:** `kb` and `backup restore` against the original (also refused by L1).

## 6. Second independent review (17 Oct 2026) — changes
The review (`docs/CL_evidence/ws_c/qa/CL_QA2_lifecycle_contract_protection.md`) confirmed that L2 (0444), L3 (`chflags uchg`) and the read-only-open measurements reproduce and are reversible. It found that L4 could be bypassed:
- `INSERT OR REPLACE` into `documents` forged a url;
- `UPDATE OR REPLACE` re-keyed a row onto another row's id, which silently deleted that other row;
- removal used `LIKE`.

**Fixed:**
- **13 triggers now:** replace guards on `documents`, plus identity freezes on `documents`, `source_versions`, `passages` and `audit_events`.
- **Exact-name removal:** only the 13 `C_PROTECT_*` names listed in `TRIGGER_NAMES` are dropped.
- **No stray files:** a missing path is refused instead of creating an empty database.
- **Application writes still work:** test 163 checks rebuild, interpretations and reviewer approval under all 13 triggers.

**Known limits** (SQLite cannot guard these from inside; L2/L3 must sit underneath, and checks catch the result):
- `DROP TRIGGER`, `PRAGMA writable_schema`;
- the FTS5 search index, since virtual tables take no triggers. The validity export now checks that the index equals the passages (`integrity:fts`).
- A status set to `approved` without a reviewer is not blocked inside SQLite. It is caught because an approval counts only when the register, the database status **and** a `source_approved` audit event agree (`validate()` and the validity export).

**WAL nuance:**
- A 0444 WAL-mode file in a writable folder still gets `-wal` and `-shm` files created by a read-only open.
- This is one more reason to keep the authoritative file in rollback-journal mode.
