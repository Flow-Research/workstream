# Internal Review Evidence

Machine-readable session receipts use
`INTERNAL_REVIEW_RECEIPT.schema.json`. They are advisory evidence, not durable
GitHub evidence or contribution/merge authority.

## Chunk

`<chunk-id>`

## Required Statements

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Base SHA: <40-character commit sha>

Merge-base SHA: <40-character commit sha>

Reviewed head SHA: <40-character commit sha>

Start worktree: clean / dirty

End worktree: clean / dirty

Reviewed at: <UTC timestamp, for example 2026-06-18T00:00:00Z>

Reviewer run IDs: <agent ids, CI run IDs, or local reviewer run references>

When this optional template is used, record the exact revision that reviewers
examined. Later changes require proportionate re-review of the affected delta.

- `.agent-loop/initiatives/**/reviews/**`
- `.agent-loop/initiatives/**/STATUS.md`
- `docs/internal_reviews/**`

## Reviewer Results

Allowed result values:

- `PASS`
- `PASS AFTER FIXES`
- `PASS WITH LOW RISKS`
- `N/A - with approved reason`

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | Pending | | |
| QA/test | Pending | | |
| security/auth | Pending | | |
| product/ops | Pending | | |
| architecture | Pending / N/A - with approved reason | | |
| CI integrity | Pending / N/A - with approved reason | | |
| docs | Pending / N/A - with approved reason | | |
| reuse/dedup | Pending / N/A - with approved reason | | |
| test delta | Pending / N/A - with approved reason | | |

## Valid Findings Addressed

List each Critical, High, and Medium finding and how it was fixed, accepted, or
deferred by the human reviewer.

Record stable finding IDs, source target, disposition, verification, and
final-target replay. Record the matching target once; start/end inspection
states bind to it and must both be clean for a final verdict.

## Commands Run

```bash

```

## Remaining Risks
