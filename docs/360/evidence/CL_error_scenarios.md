# HerBiz 360 — error and controversy scenarios (generated evidence)

**Business line:** HomepreunerHub / HerBiz · **Pins:** WS B 89dc2b9 (ws-b-demo-0.4) · WS C aa50dd4 (sources360 0.2) · **Demo source snapshot: 17 October 2026.** · Synthetic, offline, no AI or network calls · Not legal, tax or accounting advice.

**Result: 13/13 PASS** · protected databases unchanged: True

| Id | Scenario | Input | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|---|
| E1 | Owner does not know several answers | made-up profile with 'Not sure' for jurisdiction and VAT status | states only 'Need more information' or 'Blocked: legal validation'; open questions listed | states=['Blocked: legal validation', 'Need more information']; questions=['Is your licence from a mainland authority or a free zone?', 'Roughly how much did the business sell in the last 12 months?'] | PASS | adapter.dashboard (live WS B engine) |
| E2 | Owner types an invalid number | employees_count = -3 | plain message naming the field; no result shown | employees_count: How many employees? — please enter a whole number of 0 or more, or tick "Not sure". | PASS | adapter.input_problem |
| E3 | Owner expects a VAT or corporate-tax deadline | Amal (LLC) overview | every real-law row: 'No date is shown until a qualified reviewer has checked the rule and its sources.' | distinct date texts on real-law rows: ['No date is shown until a qualified reviewer has checked the rule and its sources.'] | PASS | adapter.owner_view + WS B fdbe131 |
| E4 | Corporate-tax question for any business | CT demo for Amal (LLC); CT demo for another profile (SYN-P06) | Amal: 5 rows blocked, outcome withheld; others refused | 5 rows blocked=True withheld=True; SYN-P06 refused: KeyError: 'corporate tax is shown only for the two fictional demo businesses' | PASS | adapter.ct_journey; WS B D-064 fixture |
| E5 | A real business asks about corporate tax | sources360 label for CT-SBR with profile_synthetic=False | label refused (corporate_tax_real_profile) | shown=False refused=corporate_tax_real_profile | PASS | WS C sources360 0.2 @ aa50dd4 |
| E6 | Official text amended (MD 131/2026; unreviewed summary: SBR period to 2029) | WS C change-impact evidence | one item flagged 'changed — pending review'; status unchanged; not activated | flagged=True state='Blocked: legal validation' activation='not activated' review=True | PASS | adapter.change_replay |
| E7 | A later source change makes a demonstrated claim unsafe (simulated entry) | temporary suppressed_claims entry for C360-11 | claim withheld with reason; legal status unchanged; nothing edited silently | owner_text='Withheld while a recent change to an official source is revi…' state='Blocked: legal validation' | PASS | adapter.suppressed (temporary copy; shipped list is empty) |
| E8 | Data claims approval it does not have | owner text changed to 'This rule is approved.' | whole view refused (fail closed) | refused: Incompatible: owner-visible text contains approval wording: This rule is approved. | PASS | adapter.scan |
| E9 | Sources older than allowed | assessment dated 15 Dec 2026 | B validity unavailable (fail closed); C citations marked stale | validity_available=False; C stale=True | PASS | pins.run_b / pins.run_c |
| E10 | Answer rests on incomplete law (multi-article gap) | recorded answer Q35 (cancel voluntary registration) | warning 'may be incomplete' naming missing articles | guard=incomplete missing=['VAT Decree-Law No. 8 of 2017, Article 21', 'VAT Executive Regulation, Article 14'] | PASS | ask.guard; ledger read-only |
| E11 | Owner asks how to split sales to avoid VAT | recorded answer U22 | declined; tax-agent box shown | status=declined professional=True | PASS | ask (recorded answer) |
| E12 | Question outside the recorded set / outside VAT | free-typed bank question | 'No recorded answer'; passages labelled not an answer; tax-agent box | mode=no_recording professional=True | PASS | ask._no_recording |
| E13 | A command tries to write the authoritative database | run_all(--db authoritative) | refused before any work | refused: AuthoritativeDatabaseError: Refused: the scenario evaluation would write to a protected database (CL_compliance.sqlite3: the authoritative | PASS | dbsafety.refuse_authoritative |

Regenerate: `python3 experiments/ws_a/CL_error_scenarios.py` (also run by `tests/test_mvp360.py` test 115).
