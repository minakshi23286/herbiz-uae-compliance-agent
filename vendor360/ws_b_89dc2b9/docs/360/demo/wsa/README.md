# HerBiz demo fixture for Workstream A (read-only)

**Business line: HomepreunerHub / HerBiz** · Workstream B → A · contract `ws-b-demo-0.4` · as of 17 Oct 2026 · founder decisions D-062 (fail closed) and D-064 (two-persona corporate-tax demo)

> Draft — synthetic prototype, not reviewed by a qualified professional. It is not legal, tax or accounting advice. HerBiz does not file or pay anything.

## Files

| File | Use |
|---|---|
| `CL_WSA_DEMO_FIXTURE_v1.json` | Everything the demo screens need. Read it; do not edit it. |
| `CL_WSA_DEMO_FIXTURE_v1.json.sha256` | Checksum. If it does not match, the file has changed. |

- WS-B rebuilds the fixture with `python3 experiments/ws_b/CL_build_wsa_demo_fixture.py`. The output is the same every time for the same date.
- WS-A reads the fixture only. WS-A does not import WS-B's code, and WS-B does not edit WS-A's files.

## What is inside

**`ct_demo_personas`:** WS-C's fictional persona "Amal", a Dubai mainland design business, in two variants:
- **SYN-AMAL-A:** sole establishment (a natural person).
- **SYN-AMAL-B:** small LLC (a juridical person).

The facts are copied from WS-C's persona card at commit `37897a1`. `persona_mapping_notes` lists every mapping choice.

**`other_synthetic_profiles`:** six invented VAT-focused profiles.

**Every report has:**
- the banner;
- `summary`, a count of items by state;
- `obligations`, the rows;
- `profile_gaps`, the questions to ask the owner.

**Every corporate-tax row also carries `demo_scenario`, which holds:**
- the label: "Demo scenario — fictional business.";
- `validated_guidance: false` and `release_approved: false`;
- `profile_walkthrough`: each question, with the persona's answer;
- `documents`: the checklist, showing what is ready and what is missing;
- `possible_workflow_steps`;
- `withheld`, with `withheld_why`: the items not shown, which are applicability, eligibility or relief, dates and filing instructions;
- `source_label`, from WS-C: wording, an uncertainty level, and citations with retrieval dates.

## Display rules (also stored in the fixture as `display_rules`)

**Fixture only:** the owner screen must show only the fields allowed by these rules. On each report, use `banner`, `profile_gaps.questions` and `owner_rows`, including each row's `demo_scenario`. The full `obligations` array is a reviewer and developer view: never show it to owners.

1. Show the banner on every screen.
2. Use `state_chip` for the state. An item the owner says is done shows "Owner says done — not checked". On every corporate-tax row, show the demo label and "Blocked: legal validation". Never show an eligibility, relief or filing outcome.
3. Show `source_label.user_wording`, the uncertainty chip and the citations with their dates, each with its `citation_chip` shown exactly as given (for example "Source found, not reviewed").
4. Make simulated and validated content look different. Today nothing is validated: every row is either blocked, a request for information, or an invented TEST RULE (labelled "TEST RULE — not law").
5. Never show the words "approved", "verified" or "certified". Never show a fee.

## Changes

- **0.4 (18 Oct 2026), wording only, Task 2 B-5 (T2-D6, D-098), on branch `t2-ws-b`:** two owner sentences now say "HerBiz" instead of "We". `insufficient_information` reads "HerBiz needs more information before it can say whether this may apply." `blocked_pending_legal_validation` reads "HerBiz can't answer this yet: the rule or its official sources have not been validated by a qualified reviewer." States, reasons, deadlines, documents and fields are identical to `fdbe131`; `tests/test_t2_wording_differential.py` proves it. The frozen 0.3 fixture at `fdbe131` is unchanged.

- **0.3 (17 Oct 2026), wording only, founder-approved fix for WS-A's defect report (legal-kalpu S1, S3):** `owner_rows.deadline_display` on every real-law row is now always "No date is shown until a qualified reviewer has checked the rule and its sources." Draft readings such as "apply within 30 days…", "No deadline: this is an option, not a duty." and "Ongoing." no longer appear. Computed TEST RULE dates read "TEST RULE date (made up): YYYY-MM-DD". No field was renamed or added.

- **0.2 (17 Oct 2026), additive:** each citation now has `citation_chip`, and `user_wording` is in short sentences (WS-C `sources360` 0.2 @ `aa50dd4`). No display field was renamed. One metadata key was renamed: `pins.ws_c_sources360_0_1` is now `pins.ws_c_sources360`. It is not a display field.

- **Additive change** (new fields or rows): the contract becomes `ws-b-demo-0.2`, and WS-A is told in writing.
- **Renamed or changed field:** the contract becomes `1.0`, which needs WS-A and the founder to agree first.
