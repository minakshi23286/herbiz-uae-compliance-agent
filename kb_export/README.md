# HerBiz knowledge-base manifest (publication-safe proposal)

**Status:** proposal; **not published** (repository private initially, D-086). **Manifest sha256:** `c6d59d88a29305fc0493935e6243de883f75e3ef4848dc7f6acfafa3d111706c`

## Included
- Domain A (business compliance): 5 collected source versions (371 passages, listed by article locator and passage sha256 only; 193 searched by the agent); 69 register candidates; 27 further sources in the 360 inventory; validity summary (approved versions: 0).
- 360 view: 15 obligations with their linked source ids; 7 later metadata changes listed but not applied to the demo.
- Domain B (agent governance): 4 references shipped with the agent (metadata and HerBiz notes), 1 located only, plus 2 ITU documents as link-only titles. None is activated.
- Synthetic demonstration examples: 6 Ask examples and 8 fictional dashboard businesses.

## Links and validity (v0.2.1)
Link status from the C-1 re-check (blocked_to_automation 19, dead 3, ok 83; checked 2026-10-18). Dead links carry their reason and the researched replacement. Pages blocked to automation are listed for a person to open; portal entries 1227 and 1972 load in the founder's browser (18 Oct 2026), but their **contents are not yet checked**, so nothing relies on their text. Raw-file hashes match the collected lock for 5 of 5 versions. Validity 1.2 statuses: conflict 2, current 2, outdated 6, superseded 2; `release_approved` is false everywhere.

## Does this match the submitted agent?
Built from the commits the agent pins (aa50dd4 for tax sources, e01c371 for the gate). Agent database check: match (5 versions compared by content hash). The agent searches FTA-VAT-DL8@v1, FTA-VAT-ER@v3, FTA-VAT-REG-PAGE@v1.
**The submission demonstrates synthetic retrieval only:** recorded answers and offline search over unreviewed texts, for fictional businesses.

## Excluded (and why)
- Official legal texts and passages: redistribution rights not confirmed (FTA terms require consent; portal and MoF terms not reviewed) — D4 / D-089.
- Quotes and search excerpts; reviewer packages and decision sheets; credit records and crawl identifiers; database files; local file paths.

## Rebuilding the passages yourself
The passages can be rebuilt locally from the official URLs listed here by downloading each document from its official host (HerBiz's collection tools). Users must check each site's terms first. A lawyer should confirm this method before it is offered publicly.

## Verify
`python3 experiments/ws_c/CL_build_kb_manifest.py` regenerates this folder read-only and refuses to write if restricted content appears.

Not legal advice. No legal source has qualified approval.
