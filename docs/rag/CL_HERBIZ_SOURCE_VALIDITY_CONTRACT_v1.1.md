# HerBiz: Compliance Agent — Source-validity integration contract v1.1 (Workstream C ↔ Workstream B)

**Business line:** HomepreunerHub / HerBiz (Agent championship) · **Date:** 17 Oct 2026 · **Status:** final draft for B's agreement and founder approval · **Supersedes** v1.0 in `CL_HERBIZ_RAG_INTEGRATION_HANDOFF.md` §2 (v1.0 is kept; this file only adds to it) · **Not legal or tax advice.**

## 1. The separation (the core of v1.1)
Two different questions, owned by two different workstreams. They must never be merged into one word.

| Question | Owner | Values | Decided by |
|---|---|---|---|
| **Retrieval completeness:** did retrieval find every provision this question needs? | **B** | `complete` · `incomplete` · `not_covered` · `refusal` · `unchecked` | B's pipeline (deterministic coverage check) |
| **Legal-source approval:** are the sources used approved, current and free of known problems? | **C** (+ a qualified reviewer, D3) | `approved` · `not_approved`, plus validity issue kinds | the register, the validity export and the reviewer |
| **Certified** (the only word allowed to imply reliance) | neither alone | `true` / `false` | `interface.answer_label()`: true **only if** completeness is `complete` **and** every provision is approved + current version + no issue |

**Rule for B:**
- B may say "complete" only about retrieval.
- B must not show "certified", "verified" or "approved", or any equivalent, unless `answer_label(...)["certified"]` is true.
- When it is false, B shows `answer_label(...)["user_wording"]`, which always starts "Draft information, not legal or tax advice: …" and says why.

## 2. Truth table (tested: test 162; lifecycle test 160)
| Retrieval completeness | Sources approved + current | Validity issue on a provision used | certified | Wording (example) |
|---|---|---|---|---|
| complete | yes | none | **true** | "Based on reviewer-approved official sources that are current for the provisions used." |
| complete | **no** (today: every source) | none | false | "Draft …: the official sources used have not been approved by a qualified reviewer." |
| complete | yes | conflict (e.g. G1) | false | "… official sources disagree on a point used here; both are shown." |
| complete | yes | outdated / repealed / missing (e.g. G3 `SRC\|*`) | false | "… a provision used may be out of date." |
| complete | yes | future_text | false | "… part of the cited text applies only from a future date." |
| complete | yes, but a **superseded** version | — | false | (not current version) |
| incomplete / not_covered / refusal / unchecked | any | any | false | the completeness reason is listed first |
| any | no provisions given | — | false | "no_provisions" blocker |

## 3. What B calls (all read-only; `compliance_agent/rag_c/interface.py`, `CONTRACT_VERSION = "1.1"`)
```python
from compliance_agent.rag_c import interface as C
v = C.load_validity(db=DB_PATH)                     # refuses an export made for another build
label = C.answer_label(v, retrieval_completeness, [(source_id, locator, version_id), ...])
show(label["user_wording"]) ; certified = label["certified"]
```
Supporting calls (unchanged from v1.0):
- `provision_status`
- `certification_blockers`
- `resolve_citation`: same build.
- `resolve_by_article`: across builds. Passage ids are build-scoped.

## 4. Data guarantees from C
- **Identity:** every issue carries `id`, `kind` and `version_id` (null for cross-source conflicts), plus `provisions` as `SRC|ARTICLE` or `SRC|*`.
- **Build stamp:** the export records the database md5 it was built for (`_meta.database_md5`). C regenerates it whenever the register or the database changes; test 124 fails if the committed export is stale.
- **Nothing auto-approved:** an *approved* version requires a reviewer decision recorded in the database (`engine.review_source`) **and** a register version with `approval{by, approved_date, evidence}`. The validator refuses an approval without all three (tests 95, 160).
- **No assurance by omission:** "no issue" never means complete or correct (`_meta.coverage_disclaimer`).

## 5. What B must change (from the integration handoff; unchanged, B1 is now concrete)
- **B1 (critical):** replace B's `certify()` "certified: True" with `answer_label`.
- **B2–B8:** as listed in `CL_HERBIZ_RAG_INTEGRATION_HANDOFF.md` §1.

## 6. Versioning
- **Compatible changes:** a contract change that adds fields or kinds bumps the minor version (1.1 → 1.2).
- **Breaking changes:** a change to the key format, locator grammar or meaning bumps the major version and needs both workstreams and the founder.
- **Who reads what:** `load_validity` refuses a different major schema version. Today the schema is 1.1 and the contract is 1.1.

## 7. Hardening after the second independent review (17 Oct 2026)
The review found that `answer_label` could certify an **approved but superseded or outdated** version (FTA-VAT-ER@v1 Art. 7), a version of another source, or an unreadable locator. **Fixed:** `provision_status` now returns `reasons`; certifiable only when there are none.

| Reason | Meaning |
|---|---|
| `unparsed_locator` | locator not in the contract grammar (e.g. `Article (55)`, front matter) |
| `no_version_given` / `unknown_version` | version_id missing or not in the export |
| `version_of_other_source` | version belongs to a different source |
| `source_not_approved` | not approved in **register + database + audit** |
| `version_outdated` | the version misses an in-force amendment |
| `version_not_current` | not the current version, or superseded |
| issue kinds | conflict, outdated, repealed, missing, future_text, extraction, unverified |

`load_validity()` now **requires** `db=`. Without it, it raises, unless `allow_unchecked=True` for offline inspection, which must never be used for user answers. Tests 164–166.
