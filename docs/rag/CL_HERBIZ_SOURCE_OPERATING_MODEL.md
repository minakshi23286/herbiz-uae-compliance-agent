# HerBiz: Compliance Agent — Recommended source operating model

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** Sat 17 Oct 2026 · **Status:** recommendation, awaiting your approval; nothing scheduled · **Not legal or tax advice.**

## The rule in one line
Tools **find and compare**. A person **decides**. Nothing reaches users as "certified" until a named reviewer has approved a current, conflict-free, reviewed text.

## 1. Who does what
| Stage | Done by | Automatic? | Output |
|---|---|---|---|
| Watch official pages | Firecrawl scrape in a Claude session (or the local monitor, once network use is approved) | yes, on schedule | saved page + credit-ledger row |
| Compare | `rag_c monitor` (article- and paragraph-level; Firecrawl's own change flag is ignored) | yes | alerts: new document, changed article, removed, error |
| Block | `rag_c validity --alerts` | yes | `source_changed` issues; the affected answers cannot be certified |
| Triage the alert | you, or a person you name | **no** | "noise", "real change", or "needs the reviewer" |
| Collect a new version | you approve (D13-type decision) | **no** | new version as *candidate* |
| Approve | qualified UAE tax reviewer (D3) | **no** | database review **and** register approval entry |
| Activate | register update + validation | **no** | version becomes current; the old one is superseded |

## 2. Schedule and credits
| How often | Pages | Credits a month |
|---|---|---|
| Every working day (≈ 22) | FTA VAT legislation listing; FTA VAT guides listing; FTA deregistration service page (G1) | 66 |
| Weekly | portal DL 8/2017 (EN); portal ER (EN); FTA legislation listing; FTA archive listing | 17 |
| Monthly | portal DL 8/2017 (AR); DL modifications page; related-legislations page; portal Tax Procedures | 4 |
| Re-checks after an alert (reserve) | the alerted page, once | ≤ 30 |
| **Total** | | **≈ 87 normal, ≤ 120 with reserve** |

**Not used:**
- Firecrawl **search** (2 credits per 10 results; it found nothing useful);
- crawl or map;
- PDFs (pricing not confirmed);
- stealth or enhanced proxies.

**Before starting:**
- **Monthly allowance:** confirm your plan's monthly credit allowance on the Firecrawl dashboard. Claude cannot read the balance.
- **Budget rule:** keep monitoring at no more than **25%** of that allowance.

## 3. Alert handling (target times)
| Alert | Severity | Who | Target |
|---|---|---|---|
| Changed article in scope (for example DL Art. 13) | high | you triage; the reviewer if real | triage within 2 working days; answers using it stay blocked meanwhile |
| New VAT document on a listing | medium | you | record as *discovered*; decide on collection within 1 week |
| Changed page outside scope / layout change | low | you | weekly look |
| Fetch error / page empty (JavaScript-only) | low | Claude | retry next scheduled run; never retry in the same run |

## 4. What the trial showed this model must handle
- **FTA listings only show page 1 to tools.** Once a month, a person scrolls the older pages in a browser. This is free and takes about 10 minutes.
- **English is a translation.** For any high alert on DL or ER, the reviewer checks the Arabic text on the portal.
- **Wording-only changes** are caught by paragraph comparison of same-language snapshots, not by the numbers-only cross-language check.

## 5. Decisions needed before going live
| Id | Decision | Recommendation |
|---|---|---|
| D3 | name the qualified UAE tax reviewer | needed for anything "approved" |
| D13 | collect the current portal DL text (EN + AR) once | approve after D4 |
| D4 | reuse terms for portal and FTA texts | ask the FTA / portal (draft can be prepared) |
| D18 (new) | schedule: the table above, about 87 credits a month, report-only | approve for 2 supervised weeks first |
| D19 (new) | who triages alerts (you, or a named person) | you, for the first month |
