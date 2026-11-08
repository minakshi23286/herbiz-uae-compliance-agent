# HerBiz: Compliance Agent — Source-change monitoring design

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** 17 Oct 2026 · **By:** Workstream C, branch `ws-c-source-intelligence` · **Not legal or tax advice.**

**Status in one line:** the monitor is **implemented and tested offline** (synthetic fixtures, saved-Firecrawl input, local copies of the real files). It has **not been run against the live web**. It is **not scheduled**, and nothing runs continuously.

## 1. What it does
| Capability | How | Status |
|---|---|---|
| Check registered official URLs | `watchlist()` builds the list from the register: 26 URLs on 17 Oct (23 documents, 3 listing pages) | implemented, tested |
| Detect changed documents | per URL: article-level fingerprints (exact and layout-normalised hashes), using the knowledge base's own extractors (`kb.extract_pdf` / `extract_html`), or the same heading rule on Firecrawl markdown | implemented, tested (tests 107, 112, 116) |
| Tell substantive from cosmetic changes | the same normalisation idea as `kb.compare`: footnote lines removed, whitespace and case squashed | implemented, tested (107) |
| Detect removed documents | HTTP 404/410 → `removed` (alerted once, not every day) | implemented, tested (109, 110) |
| Detect newly published documents | listing pages are parsed for links; new official links on in-scope topics become **candidate proposals** (`activated: false`) | implemented, tested (109, 114, 115) |
| Detect "the URL now serves different bytes than we collected" | raw sha256 vs the collection lock | implemented, tested (116, with a real-file swap) |
| Identify potentially affected provisions | changed articles → `SOURCE\|ARTICLE` keys; cross-check with validity issues and recorded conflicts | implemented, tested (107, 108) |
| Generate review alerts | severities high / medium / low / info (table in §4) | implemented, tested |
| Daily report | `data/monitor/reports/CL_source_monitoring_report_<date>.md` + `..._alerts_<date>.json`; never overwrites; state written atomically | implemented, tested (111) |
| Compare versions in depth | after an approved collection: `rag_c compare` (reuses `KnowledgeBase.compare`), `rag_c dryrun`, `rag_c diff` | implemented (earlier) |
| Activate a source | **never.** The monitor writes only `data/monitor/` (git-ignored) | by design, tested |

## 2. Flow
```
register (watch list) ─┬─► Fetcher ─► observation {url, status, bytes | markdown, via}
                       │      ├ FixtureFetcher   (tests; no network)
                       │      ├ FirecrawlImport  (JSON saved by a Claude session from firecrawl_scrape; no network here)
                       │      └ LocalFetcher     (kb.http_fetch; allowlisted hosts, TLS on; refuses without allow_network)
                       ▼
             LOCAL VERIFICATION (always, whatever the fetcher)
             sha256 vs lock · extract units (same extractor as the KB) · article diff vs previous state
             · substantive vs cosmetic · links added/removed on listings · affected SOURCE|ARTICLE keys
                       ▼
             alerts + proposals + report + new state      ──►  person reviews  ──► (if needed) founder approves
             (data/monitor/, git-ignored)                                          kb collect --allow-network into a copy
                                                                                   → rag_c compare / dryrun / validate
                                                                                   → new register version → reviewer (D3)
```
**Design rule:** a fetcher only observes. The verdict (changed, substantive, affected) is always computed locally. Firecrawl's own `changeStatus` is recorded as `firecrawl_disagrees` when it differs, but never trusted over the local comparison (test 112).

## 3. Where Firecrawl adds value (and where it does not)
| Need | Existing tool | Firecrawl | Decision |
|---|---|---|---|
| Fetch FTA PDFs and pages | `kb.http_fetch` (allowlist, TLS, size cap) works from this Mac for tax.gov.ae | `firecrawl_scrape` (1 credit/page) | Local fetch is enough for **tax.gov.ae** (it worked on 16 Oct). Use Firecrawl only where local fetch fails |
| JS-heavy or blocked sites (uaelegislation.gov.ae returned 403 to WebFetch; eLaws refused connections) | none | rendering and proxy options | **Possible value**, but test one URL first. It is not used to get round a site's restriction: if the site forbids automated access, a person opens it in a browser |
| Paginated listings (the FTA listing returned only page 1 to WebFetch) | `parse_listing` on a saved page | `firecrawl_scrape` with actions, or `map` | **Possible value** for the listing pages only (3 URLs) |
| Change detection | local fingerprints and article diff (built, tested) | `changeTracking` (markdown compare; statuses new/same/changed/removed; no extra credit) | Use Firecrawl's status as a **second signal**, not the decision. Local article-level diff stays authoritative |
| Scheduled alerts | none yet | Firecrawl Monitor (1 credit/page/check) | **Not now.** Keeps a third-party copy of our watch list; our own scheduler (§6) does the same with local verification |
| Search for new instruments | WebSearch (no Firecrawl credit) | `firecrawl_search` (0.2 credit/result) | WebSearch first |

**No Firecrawl call has been made by Workstream C.** The connector is linked to your claude.ai account; credits and plan were not visible to me.

## 4. Alert severities
| Kind | Severity | Meaning / next step |
|---|---|---|
| `removed` | high | an official URL we rely on returns 404/410: find the replacement on the listing |
| `changed_substantive_in_scope` | high | wording changed in an in-scope article (registration, deregistration, thresholds, groups): review, then approve a collection |
| `conflict_provision_changed` | high | a provision under a recorded conflict changed (e.g. ER Art. 14): re-check G1 |
| `differs_from_collected_version` | high | the URL now serves bytes different from our locked copy |
| `changed_substantive` | medium | wording changed outside the in-scope articles |
| `new_document_on_listing` | medium | a new official document link: classify the proposed candidate |
| `removed_from_listing` | medium | a document dropped off a listing (often archived) |
| `fetch_error` | medium | 403/500/timeout: record; retry next run; never bypass |
| `changed_cosmetic` | low | layout-only change |

## 5. Commands
```
python3 -m compliance_agent.rag_c monitor --fixtures tests/…/day1                          # offline, synthetic
python3 -m compliance_agent.rag_c monitor --firecrawl-dir data/monitor/firecrawl/2026-10-18   # results saved by a Claude session
python3 -m compliance_agent.rag_c monitor --allow-network                                     # ONLY with founder approval
python3 -m compliance_agent.rag_c discover --listing saved_listing.html --listing-url https://tax.gov.ae/en/legislation.aspx [--write]
```
Outputs go to `data/monitor/` (state, reports, alerts), which is git-ignored and never inside `data/raw/`, the lock, the register or a database. `discover --write` adds proposals to the register as a new patch version; it is the only write, and it needs the flag.

## 6. Scheduling (designed, **not installed**)
| Option | How | Network needed | Cost | Fit |
|---|---|---|---|---|
| A. macOS launchd, local fetch | `docs/rag/templates/CL_launchd_source_monitor.plist.template` runs `rag_c monitor --allow-network` daily at 06:00 | yes (tax.gov.ae, mof.gov.ae) | none | best for the FTA files; Mac must be awake |
| B. Claude scheduled task with Firecrawl | a scheduled Claude session calls `firecrawl_scrape` (formats `markdown`, `changeTracking`; same options every time) for each watch URL, saves the JSON to `data/monitor/firecrawl/<date>/`, then runs `rag_c monitor --firecrawl-dir` | Firecrawl | ~26 credits per full run | for blocked or JS sites; uses Claude usage plus credits |
| C. Hybrid (recommended when approved) | A for tax.gov.ae and mof.gov.ae daily; B weekly for the 3 listing pages and any site A cannot reach | both | ~3–5 credits/week | lowest cost; local verification for everything |

**Credit estimate (Option B, everything):** 26 URLs × 30 days ≈ 780 credits/month. The tiered version (listings and service pages daily, ~8 URLs; PDFs weekly, ~18) is ≈ 240 + 80 = 320 credits/month. Firecrawl's free tier is 1,000 credits/month (pricing page, 17 Oct 2026). Your plan and balance were not visible to me.

**Before any unattended run:**
- founder approval for network access;
- check the Firecrawl dashboard balance (if B);
- one supervised run;
- a reviewer named for high alerts.

**Unattended-run risks:**
- the Mac is asleep;
- network failures (reported as `fetch_error`, not as changes);
- site layout changes (seen as cosmetic or as removed links);
- a stale validity export (rebuild it before each run).

## 7. Tests (offline)
| Test | What it proves |
|---|---|
| 106 | first run records a baseline and raises no change alerts |
| 107 | 20→30 days in Art. 14 = substantive and in scope (high); a whitespace edit in Art. 7 = cosmetic |
| 108 | a change to a conflicted provision raises its own alert |
| 109 | removed document; link removed from a listing; a new relevant link proposed as an inactive candidate; irrelevant or off-host links skipped; listing dates captured |
| 110 | an unchanged rerun is quiet; "removed" is not repeated daily |
| 111 | report never overwritten; state written atomically |
| 112 | Firecrawl JSON verified locally; Firecrawl "same" vs local "changed" recorded as a disagreement |
| 113 | the local fetcher cannot run without explicit network approval; urlopen never called |
| 114–115 | URL normalisation; known sources recognised; register additions bump the version and stay inactive; the register file is not written |
| 116 | the real register's 5 versions served from local copies match the lock; a swapped file at the 2026 URL is caught |

## 8. Independent QA round (17 Oct 2026) — what changed
An independent reviewer reproduced 24 findings (4 high, 15 medium, 5 low), with the verdict **"blocked for an unattended daily run; fine for supervised manual runs"** (`docs/CL_evidence/ws_c/qa/CL_QA_monitoring.md`). Fixed the same day, with tests 131–140:

| Finding | Fix |
|---|---|
| MON-01 one bad item stopped the run | per-item isolation; the error is recorded as `fetch_error` and the run continues |
| MON-02 state saved before the report | report and alerts written first, state last; a failed report does not advance the state |
| MON-03 URL already gone at baseline not alerted | alerted once, noting it was never seen working |
| MON-05/06 footnote renumbering and "Page X of N" flagged as substantive | both normalised away |
| MON-07 web pages compared by paragraph position | paragraphs keyed by normalised content; in-scope pages can raise high alerts; page changes keyed `SRC\|*` |
| MON-08 soft-404 / empty extraction became the new baseline | treated as an error; baseline kept |
| MON-10/11 JS-only listing flooded "removed"; menu and news links noise | empty listing = error; only document links (legislation and guide files) are tracked |
| MON-12 Firecrawl `links` ignored | used |
| MON-13 drift from collected bytes only on the first run, PDFs only | every run, any format, once per new bytes |
| MON-14 restored document not alerted | `restored` alert |
| MON-15 corrupt state stopped every run | moved aside (`*.corrupt-<time>.json`, never deleted); new baseline with a warning |
| MON-16 no run lock; report race | exclusive lock file; reports created with exclusive create |
| MON-17 persistent failures stayed medium; "removed" high even for archived files | 3 consecutive failures escalate to high; archived files' removal is medium |
| MON-18 conflict checks silently off without a DB | the report shows a warning |
| scheduling: nobody is told | heartbeat file `data/monitor/CL_monitor_heartbeat.json`; `rag_c monitor` exits **2** when there are high alerts; launchd logs moved out of `data/monitor/` |

**Still open before any unattended schedule:**
- MON-04: running-header removal can hide a change in a line repeated on most pages, e.g. a penalty table.
- `discover --write` is not atomic and has no backup (it is a manual, flagged step).
- A notification channel for exit code 2 is not built.
- The scheduled job must run from a permanent checkout, not a removable git worktree.
- One or two weeks of supervised runs are needed. **The monitor has never been run against the live web.**

## 9. Firecrawl trial (prepared, awaiting D15)
The exact 11-credit plan (cap 15), stop rules and success criteria: `CL_HERBIZ_FIRECRAWL_TRIAL_PLAN.md`; generator, guard and verifier: `rag_c firecrawl-plan` / `firecrawl-verify` (tests 154-155). The balance could not be read from Claude (no balance capability; one free discovery query, 0 credits).
