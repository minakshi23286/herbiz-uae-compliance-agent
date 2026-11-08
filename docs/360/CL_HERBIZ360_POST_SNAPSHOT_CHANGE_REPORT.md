# HerBiz 360 — post-snapshot source change report

**Business line:** HomepreunerHub / HerBiz · **Opened:** Sat 17 Oct 2026 · **Owner:** Workstream A (records and demo impact); Workstream C (monitoring and source facts) · **Not legal, tax or accounting advice.**

**Founder approval (17 Oct 2026):**
- The demo keeps **"Demo source snapshot: 17 October 2026."** for the 7 Nov internal demo and the 10 Nov championship.
- Changes found after 17 Oct are recorded **here**. They never change the demo silently.
- A material change that makes a demonstrated claim misleading or unsafe is **escalated**. After review, the claim is **corrected or suppressed**.

## 1. How a change is handled
1. **WS C monitors** official sources independently and sends WS A, **in writing**: what changed, the official URL, the date found, and C's evidence file and commit.
2. **WS A records** it in §3 the same day, and checks it against the claims register in §2.
3. **Material?** It is material if it changes a fact, date, threshold, relief, period or obligation that a register claim states or relies on. If so, WS A **escalates to the founder** that day and recommends one of:
   - (a) suppress the claim;
   - (b) correct the demo, which needs a new pinned snapshot and a founder decision;
   - (c) explain the change in the demo narration.
4. **After review:**
   - **Suppress:** add an entry to `fixtures/mvp360/CL_mvp360_demo_content.json` → `suppressed_claims`, with `claim_id`, `reason`, `change_report_entry` and `since`. The app then shows "Withheld while a recent change to an official source is reviewed". Legal status chips stay as they are.
   - **Correct:** only with a founder decision. Update `docs/360/CL_DEMO_SNAPSHOT.lock.json`, the pins and the tests together, and record it here.
5. **Never:**
   - silently change source data, citations or obligations;
   - remove a corporate-tax block;
   - drop an "unreviewed" label.

## 2. Claims the demo makes (register)
| Claim id | Where shown | Claim (as shown) | Rests on (snapshot 17 Oct 2026) |
|---|---|---|---|
| `step:7` | Rule changes | MD 131/2026 replaced Art. 2(2) of MD 73/2023, so the SBR period runs to tax periods ending on or before 31 Dec 2029 (was 31 Dec 2026). Not activated; human review required | C `CT-MD131-2026`, `CT-MD73-2023`; C evidence `CL_sbr_amendment_impact_2026-10-17.json` @ aa50dd4 |
| `C360-11` | Overview, corporate tax | Small Business Relief: blocked, with demo questions, documents and steps; sources found, not reviewed | B fixture `ws-b-demo-0.3` @ fdbe131; C `CT-SBR` label (0.2) |
| `C360-07`, `C360-08`, `C360-10`, `C360-14` | Overview, corporate tax | CT registration (company or natural person), CT return, accounting records: blocked; demo questions, documents and steps only | B fixture @ fdbe131; C `CT-REG-JURIDICAL`, `CT-REG-NATURAL`, `CT-RETURN`, `ACC-RECORDS` |
| `C360-01`…`C360-05` | Overview, VAT | VAT items: "Owner says done — not checked", or blocked; no dates | B fixture @ fdbe131; B validity export @ 9b48966 (C contract 1.1) |
| `Q01`, `Q13`, `U10`, `Q35`, `U14` | VAT step | Recorded answers quoting the FTA texts (e.g. the AED 375,000 mandatory threshold, the 30-day application period), with an incompleteness flag | FTA texts in the authoritative DB (unchanged); recorded answers in the experiment ledger |
| `help` | Getting help | Who-does-what categories (estimates, not reviewed) | C `CL_HERBIZ_360_02_PRODUCT_SCOPE.md` §4 @ 6cfcaff (unchanged at aa50dd4) |

## 3. Changes found after 17 October 2026
| Entry | Date found | Source (official URL) | What changed | Claims affected | Material? | Escalated | Decision and action |
|---|---|---|---|---|---|---|---|
| — | — | — | **No changes recorded as of 17 Oct 2026.** | — | — | — | — |

## 4. Demo data and version changes (not regulatory changes)
| Entry | Date | Change | Effect on source data, citations, obligations | Approved | Evidence |
|---|---|---|---|---|---|
| DV-001 | 17 Oct 2026 | WS B re-pinned from `30a6f9a` to `fdbe131`; the fixture moves from `ws-b-demo-0.2` (sha256 `25ca9939…`) to `ws-b-demo-0.3` (`1b8d2c38…`) | **Owner-row wording only:** real-law rows say "No date is shown until a qualified reviewer has checked the rule and its sources."; test-rule rows are labelled by B. The snapshot date (17 Oct 2026), the C pins (`aa50dd4`, validity `9b48966`), citations, states and obligations are unchanged | Founder, chat 17 Oct 2026 | B 213/213 on an isolated checkout; the lock file updated; full regression re-run (see the integration report) |
| DV-002 | 18 Oct 2026 | WS B re-pinned from `fdbe131` to `89dc2b9` (`t2-b-rc1`). The fixture moves from `ws-b-demo-0.3` (`1b8d2c38…`) to `ws-b-demo-0.4` (`d5e34672…`; public scrubbed copy `ad9b8e77…`) | **Owner wording only, in the engine:** "We need more information…" becomes "HerBiz needs more information…", and "We can't answer this yet…" becomes "HerBiz can't answer this yet…". WS B's differential test shows only these two sentences differ. Catalogues, profile, validity and corporate-tax demo code are unchanged. Also adds WS B's `retrieve_v8` as the **interim** retrieval candidate (D-102): required-article recall 66.7% on frozen v10; the 70% threshold is unmet | Founder/CTO, D-101 and D-102 (18 Oct 2026) | B suite 241/241 on `t2-ws-b`; full regression on `t2-integration` (A-4 integration report) |
| DV-003 | 18 Oct 2026 | WS C Task 2 data from `t2-c-rc2` (`8f35b20`): the source-validity 1.2 export (110 records), link status, and the SC-2/SC-3 source sides. KB manifest v0.2.0 (`954f9056…`) becomes v0.2.1 (`c6d59d88…`) | **No change to the demo's source data:** labels and citations stay at `aa50dd4`, and the 17 Oct snapshot is unchanged. The 110 records are WS C's status metadata, not independently verified legal content. Portal entries 1227 and 1972: the page loads (founder, 18 Oct), but the contents are **not yet checked**. The outdated VAT source (G3) is **not** resolved. C-5 and C-6 outputs are excluded | Founder/CTO, D-101 amended to rc2 (18 Oct 2026) | WS C delivery tests on `t2-integration`; full regression |

## 5. Before the 7 November demo
- Run the final regression suite on `int-herbiz360-champ`:
  ```bash
  python3 -m unittest discover -s tests
  ```
  Expected: all pass except the one C real-portal skip.
- Confirm that the protected database md5s are unchanged.
- Read §3. Every material entry must have a founder decision before the demo.
