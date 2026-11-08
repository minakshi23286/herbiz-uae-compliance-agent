# HerBiz 360: Workstream B → Workstream A integration handoff

**Business line: HomepreunerHub / HerBiz** · 17 Oct 2026 · founder decision D-066 (T-040) · WS-A owns the championship integration branch; WS-B does not edit WS-A files · Not legal, tax or accounting advice.

## 0. Update (17 Oct 2026): defect fix `fdbe131`, approved by the founder under D-066

**Change**
- WS-A reported a defect (legal-kalpu S1/S3): some owner rows showed draft deadline readings.
- Fix: every real-law row in `owner_rows.deadline_display` now shows "No date is shown until a qualified reviewer has checked the rule and its sources."
- Computed TEST RULE dates now read "TEST RULE date (made up): YYYY-MM-DD".
- A TEST row that is waiting for answers reads "TEST RULE: no date until the missing answers are given."

**New reference**
- Code commit: **`fdbe131`**.
- Tests: 213/213 pass.
- Fixture contract: `ws-b-demo-0.3`, a wording change only; no field was renamed or added.
- Fixture sha256: `1b8d2c3886e1227f9098a76c2976ac5e582c3221d5bfa482ad765f289f5dd138`.

**For WS-A**
- Re-pin from `30a6f9a` to `fdbe131`.
- WS-A's own safeguard (test_104) can stay; it now agrees with B.

The tables below still describe `30a6f9a`, apart from this change.

## 1. Exact reference (frozen baseline)

| Item | Value |
|---|---|
| Branch | `ws-b-retrieval` |
| Frozen code commit | **`30a6f9a`**, also tagged `ws-b-baseline-2026-10-17` |
| Tests at that commit | 210/210 pass on Python 3.11.9 |
| Base | `main` @ `fcdfbb7` is an ancestor (42 commits ahead) |
| Interface | `ws-b-demo-0.2` (fixture) and the Python API below. Neither changes without coordinating with WS-A. |
| Pins inside B | WS-C VAT validity contract 1.1 @ `9b48966`; WS-C sources360 contract 0.2 @ `aa50dd4` |

Any commit on `ws-b-retrieval` after `30a6f9a` is documentation only, such as this handoff. WS-B feature work has stopped. Further changes happen only for a specific integration defect that WS-A reports.

## 2. Two ways to consume B (pick one)

**A. Fixture only (simplest; recommended for the demo).**
- Read `docs/360/demo/wsa/CL_WSA_DEMO_FIXTURE_v1.json` at `30a6f9a`.
- Check it with `CL_WSA_DEMO_FIXTURE_v1.json.sha256`.
- You need no B code, no DB and no WS-C repo at runtime.
- The contract is in `docs/360/demo/wsa/README.md`. Owner screens show only `banner`, `profile_gaps.questions` and `owner_rows` (with `demo_scenario`).

**B. Live engine (WS-A's current `pins.py` approach).**
- Export `30a6f9a` with `git archive` and run it in a separate process.
- The API:
  - `engine.assess(profile, sv, as_of, policy="blocked")`
  - `engine.owner_row(result)`
  - `validity.load_pinned(db, c_repo=…, today=…)`
  - `ct_demo.load_c_labels(as_of, c_repo=…)`
  - `ct_demo.assess_demo(profile, sv, as_of, labels)`, for `SYN-AMAL-A` and `SYN-AMAL-B` only.

## 3. Sample outputs (all at `30a6f9a`)

| File | Content |
|---|---|
| `docs/360/demo/wsa/CL_WSA_DEMO_FIXTURE_v1.json` | Amal A and B with corporate-tax demo blocks, plus 6 VAT-focused synthetic profiles. Owner view, fail-closed. as_of 2026-10-17. sha256 `25ca9939…` |
| `docs/360/demo/CL_OBLIGATIONS_DEMO_EVIDENCE.md` | Human-readable tables for the 6 synthetic profiles |
| `docs/360/demo/CL_obligations_demo_blocked.json` | Raw `assess()` output for the 6 profiles (developer view) |
| `fixtures/obligations/CL_ct_demo_personas_wsc.json` | The Amal A and B profiles: WS-C's persona card mapped to B's schema, with notes |

## 4. Test commands (from the repository root of an export or checkout of `30a6f9a`)

```bash
python3 -m unittest tests.test_obligations
```

```bash
python3 -m unittest discover -s tests
```

```bash
python3 experiments/ws_b/CL_build_wsa_demo_fixture.py --as-of 2026-10-17 --out /tmp/fx && shasum -a 256 /tmp/fx/CL_WSA_DEMO_FIXTURE_v1.json
```

The last command must reproduce sha256 `25ca9939e0889c0f0c715fca9f24300d4773710b8b543b9c32ea4a6e590c49ed`. The build is deterministic.

The live tests need three environment items, all read-only:
- `data/CL_ws_b_exact_copy.sqlite3`: a byte copy of the authoritative DB, md5 `26e202b87a062288e56bcda1de9b0217`.
- `data/CL_ws_b_kb_copy.sqlite3`: md5 `c33160221efe42f2425a5725945a07af`. It is used only by one fail-closed test.
- WS-C's repository at `../CL_compliance_agent_app_ws_c`, or pass `c_repo=` to the functions. Any worktree of this repository works, because commits `9b48966` and `aa50dd4` are in the shared object store.

`data/*.sqlite3` is git-ignored, so the two database copies have to be placed by hand. Without them the tests fail closed, as designed. The fixture itself needs none of this.

## 5. Compatibility notes: WS-A's pin `a54db87` → `30a6f9a`

| Change | Effect on WS-A |
|---|---|
| `CHECK` text changed from "Check with an accountant or tax agent before acting." to "Check with an FTA-registered tax agent before acting." | Update any WS-A test or snapshot that matches the old text |
| Reason strings changed from "…not approved" to "…not checked by a reviewer". The blocked-deadline basis now says "…has checked…" | Reasons are not owner fields. Update snapshots only. |
| `STATE_TEXT["potentially_applicable"]` changed from "approved" to "checked" | Reviewer view only |
| New result fields `state_chip` and `already_done`; new `engine.owner_row()` and `OWNER_FIELDS` | Additive. Use `state_chip` for the chip. "Owner says done — not checked" replaces a "Not applicable" chip for owner-reported facts. |
| C360-11 `meaning` now reads "A revenue-based relief exists; whether it fits a business needs a tax agent's review." | Text only |
| New `ct_demo.py`, persona fixture and WS-A fixture | Additive |
| No field renamed or removed in `assess()` output; states and policies unchanged | — |

**Overlap to resolve inside WS-A, which is WS-A's call:**
- WS-A's dependency note (§E) transcribes the Amal corporate-tax scenario itself. B's fixture already does this from the same WS-C persona card, using the same B→C id join as WS-A's adapter (C360-07→CT-REG-JURIDICAL, C360-08→CT-REG-NATURAL, C360-10→CT-RETURN, C360-11→CT-SBR, C360-14→ACC-RECORDS).
- B's version also carries legal-kalpu's fixes (D-064 conditional pass): wording, owner-field projection and chips.
- Using one source avoids two versions of the same corporate-tax rows.

## 6. Known blockers and limits

1. **Validity freshness.** B's VAT validity check refuses exports older than 7 days. The pinned export is dated 17 Oct, so a live run with today's date after 24 Oct shows validity "unavailable": VAT rows stay blocked, and nothing opens.
   - Options: keep the fixed demo date of 17 Oct (WS-A's `DEMO_AS_OF` already does this), or have WS-C regenerate the export with B re-pinning. Re-pinning changes B, so it needs the founder or WS-A to ask.
2. **Validity edge gaps (known, accepted).** An export dated in the future is not rejected, and the staleness check uses `load_pinned(today=…)` rather than `assess(as_of)`. Neither matters while no rule is `reviewed`.
3. **Corporate-tax review.** No source is approved. WS-C is preparing the citation review package (D-066). Until a paid review is approved and completed, every corporate-tax row stays blocked and labelled as a demo.
4. **Leftover temp folders.** The older `source_validity_c` adapter leaves `ws_b_c_iface_*` folders in `$TMPDIR`. This is harmless.
5. **WS-A environment.** Running the live engine needs the DB copies and WS-C commits listed in §4. The fixture route avoids this.

## 7. Restrictions (unchanged)

- No merge into `main`.
- No changes to the authoritative DB.
- No legal-source activation.
- No production deployment.
- No paid API calls.
- No change to the blocked corporate-tax determinations.
