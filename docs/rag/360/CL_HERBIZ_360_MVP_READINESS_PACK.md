# HerBiz 360 MVP — Readiness pack (ITU AI for Good hackathon, submission 10 Nov 2026)

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** Sat 17 Oct 2026 · **By:** Workstream C (Claude Code) · **Baseline:** board-reviewed 360 plan, commits `3d8578b` and `9b48966`, plus this pack · **Founder approval:** 17 Oct 2026 (narrow MVP, restrictions below) · **Status words:** drafted · built · verified · awaiting approval · blocked · **Not legal, tax or accounting advice.**

**Restrictions in force:**
- no substantive corporate-tax rules without qualified review;
- no real-owner compliance decisions;
- no filing or payment;
- no certification claims;
- no authoritative database changes;
- no deployment;
- no merges without separate approval;
- no new paid services.

## 1. Integrated MVP readiness checklist
| # | Approved MVP item | Owner | Status today | Evidence | What is left |
|---|---|---|---|---|---|
| 1 | Synthetic business onboarding | **A** (UX), **B** (profile model) | **built** (base: `/api/onboard`, test_78); extension **not started** | audit row A; main tests 83 OK | add 8 profile facts (H360-01); persona card A/B |
| 2 | Profile-driven obligations dashboard | **B** (engine), **A** (screen) | engine **built** (6 outcomes, synthetic rules). **Update (WS B report, not checked by C):** B built an offline synthetic obligations engine under D-061 (ws-b-retrieval `0238590`), with CT items hard-blocked (`blocked_pending_legal_validation`). B pins C's VAT contract at `9b48966` and will adopt `sources360` later, as a separate step. 360 dashboard screen **not started** | `engine.assess` tests 01–15 | map engine obligations to C's 15 `obligation_id`s; show C labels |
| 3 | Synthetic VAT and corporate-tax scenarios | **B** (scenario data), **C** (citations) | VAT synthetic scenarios **built** (23); CT **fixed synthetic scenarios** **drafted** (oracle in 06 §1, wording per legal review) | eval scenarios; C `obligations360` | B encodes the variants A and B outcomes as data; no CT rules |
| 4 | Deadline and document-readiness checklists | **B** | **not started** | — | dates with their basis shown; CT registration documents from the FTA service card (C source `CT-REG-SERVICE`) |
| 5 | Draft financial-readiness workflows (synthetic records) | **B** (logic), **A** (screen) | **not started** | design in 02 §3 (board-reviewed) | three revenue bases, missing-document list, CSV export with `label_level` |
| 6 | Source citations and uncertainty indicators | **C** | **built and verified** | `sources360.py`; tests 178–195 (18 tests); labels snapshot in `docs/CL_evidence/ws_c/360/mvp/` | A renders them; B attaches them per row |
| 7 | Regulatory change detection and impact analysis | **C** (engine), **A** (replay screen) | **built and verified** | VAT chain test 170; 360 `impact()` tests 186, 194; **real** SBR amendment impact (MD 131/2026) recorded | A scripts the replay |
| 8 | Human-review and approval safeguards | **B/A** (gates exist), **C** (labels) | gates **built** (tests 19–23, 37); C labels never release-approved; CT refused for real profiles (test 188); demo banner **not started** | tests; legal review | banner on every screen (A); sign-off endpoint test (H360-13) |

**Overall:**
- **Built and verified:** WS C's parts (items 6 and 7).
- **WS B:** the engine is reported built (`0238590`). WS A is closed (16 Oct closure record) until you reopen it. The rest of items 1–5 and the banner are not started.
- **Not merged:** the C interface, which sits on C's branch; integration needs either a merge or a disposable integration branch (decision F2).

## 2. Workstream dependencies and ownership
| From → to | What | Needed by | Status |
|---|---|---|---|
| C → B | `sources360` interface + 2 JSON files (`CL_WS_C_TO_AB_360_INTERFACE.md`) | H360-02/03/04 | **ready** |
| C → A | label fields (frozen by test 195), uncertainty chip, citations, change-impact JSON | dashboard and replay screens | **ready** |
| B → A | extended profile model; obligations with labels; deadlines; revenue tests | onboarding and dashboard screens | not started |
| A → founder | demo script, persona card, banner | submission | not started |
| founder → B/C | merge or integration-branch decision | wiring C into the app | **awaiting approval (F2)** |
| founder → C | collection approval for the CT law and current DL texts (lowers uncertainty from high) | optional for the demo | **awaiting approval (F4)** |

**Sessions:**
- **WS B:** its session ("HerBiz3 – WS B") ended its last task with development stopped after the D3 package. It needs your go-ahead in that session to resume.
- **WS A:** its session ("HerBiz 1 – WSA") is idle.

C has sent both sessions a coordination note.

## 3. Championship demonstration scenario (about 6 minutes)
**Banner on every screen:** "Prototype · synthetic business data · simulated reviewer · Demonstration draft: not legal, tax or accounting advice, not reviewed, and not a compliance decision · HerBiz does not file or pay".

1. **Meet Amal** (fictional): a Dubai home-based design business. Onboarding asks plain questions. "I don't know" is allowed, and it shows up later as "needs clarification".
2. **Two variants side by side:** sole establishment vs small LLC. The dashboard shows how obligations differ. Every row has:
   - the "Demo scenario (fictional business)" wording;
   - an uncertainty chip;
   - official citations with retrieval dates;
   - "reviewer needed: D3-CT".
3. **Deadlines and documents:** computed dates with their rule shown (e.g. CT return = FY end + 9 months, from FTA notices), plus the CT registration document checklist from the FTA service card.
4. **Financial readiness:** synthetic transactions → three separate revenue tests (VAT, CT natural person, SBR), a missing-document list and a CSV export labelled A1/A2.
5. **Change detection, using real data:**
   - The 2023 Small Business Relief decision said "periods ending by 31 Dec 2026".
   - HerBiz's source intelligence found **MD 131/2026**, which moves this to **31 Dec 2029**.
   - Impact analysis flags the SBR scenario as "changed, pending review". Nothing changes until a person reviews it.
   - Optional second beat: the VAT chain (real portal text, synthetic edit, 36 earlier answers flagged).
6. **Safeguards:**
   - the reviewer queue (simulated reviewer);
   - "HerBiz does not file or pay", with a link to EmaraTax;
   - a real profile cannot see corporate-tax rows (the interface refuses).

## 4. Test evidence (17 Oct 2026, offline)
| Suite | Result | Notes |
|---|---|---|
| WS C (`ws-c-source-intelligence`) | **188 tests OK** | includes 360 interface tests 178–195 |
| WS B (`ws-b-retrieval`) | 164 OK (independent audit, 17 Oct) | unchanged by C |
| main (A) | 83 OK (independent audit, 17 Oct) | unchanged |
| Board review of the interface | CTO and GC: **conditional passes; all edits applied** | `docs/CL_evidence/ws_c/360/board2/` |
| CTO mutants | 2 survived at first (best-evidence rule, VAT start level); now killed by test 192 | — |
| Evidence files | `CL_sbr_amendment_impact_2026-10-17.json`; obligation labels for real vs synthetic profiles | `docs/CL_evidence/ws_c/360/mvp/` |
| Protected data | authoritative DB `26e202b8…` and ledger `59226cd0…` unchanged | checked |

## 5. Remaining legal and technical blockers
| Blocker | Type | Effect on the MVP | Unblocked by |
|---|---|---|---|
| No qualified reviewers (D3 VAT, D3-CT) | legal | everything stays "demonstration draft"; no release approval | founder engages reviewers (spend) |
| CT law text not collected (CT-G2) | legal/source | CT uncertainty stays high; no article citations | collection approval (F4) + D4 reuse terms |
| Outdated VAT law copy (G3); deregistration conflict (G1) | legal/source | VAT stays high; deregistration deadline never stated | D13, D3, FTA answer |
| E-invoicing dates for smaller businesses (EINV-G1) | source | e-invoicing row is awareness-only | a person opens the MoF page in a browser (Firecrawl failed twice) |
| Audited-accounts rule text (ACC-G1) | source | audit row is flag-and-get-help only | read MD 84/2025 (URL located) |
| Reuse terms (D4/G5) | legal | no stored full texts; links and short citations only | lawyer or publisher consent |
| B and C not merged into the app | technical | C's interface cannot be shown in the UI yet | F2 |
| WS B development stopped; WS A idle | delivery | items 1–5 not started | founder go-ahead in those sessions |
| Founder time: about 1 h per weekday; 6 h cap 16–22 Oct (D-055) | capacity | about 16 founder hours to 10 Nov | scope cuts listed in 06 §3 |

## 6. Founder decisions requiring approval
| Id | Decision | Recommendation |
|---|---|---|
| F1 | Tell WS B and WS A (in their sessions) to start the MVP tasks H360-01..06 using C's interface | yes, this week (within the 6-hour cap) |
| F2 | Integration: allow a **disposable integration branch** (not main; not a merge into main) combining A+B+C for the demo, or keep separate demos | integration branch; a main merge stays a separate decision |
| F3 | Accept the CT demo wording from the legal review ("Demo scenario (fictional business): on an unreviewed reading…") | accept |
| F4 | Approve collecting the CT law (portal 1582, EN+AR) and the current VAT DL into a **new** version file, not the authoritative DB (about 2–4 credits) | optional; improves citations |
| F5 | Reviewers D3 and D3-CT (both cost money) | decide before any pilot; not needed for the hackathon |
| F6 | A person (you) opens the MoF e-invoicing page in a browser and notes the small-business dates | 5 minutes, free |
