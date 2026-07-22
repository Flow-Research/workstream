# WS-ENG-001-04A Preimplementation Plan Review

## Reviewed scope

Planning artifacts and contracts for `WS-ENG-001-04A` and provisional
`WS-ENG-001-04B`, reviewed against protected-main state during 2026-07-20.

## Reviewer tracks

| Track | Result | Remaining blocker |
|---|---|---|
| Senior engineering | Pass after repair | None |
| QA/test | Pass after repair | None |
| Security/auth | Pass after repair | None |
| Product/ops | Pass after repair | None |
| Architecture | Pass after repair | None |
| CI integrity | Pass after repair | None |
| Docs | Pass at specification stage | None |
| Reuse/dedup | Pass | None |
| Test delta | Pass | None |

## Findings repaired

- Replaced an unexecutable exact deletion-list concept with authenticated fresh-
  tree construction using an empty output root and temporary Git index, a normal
  child commit, and fast-forward-only push. The design does not traverse or
  recursively delete the 626-file legacy checkout.
- Defined `.agent-loop/MANIFEST.json`, its ordered payload/digest entries, exact
  tree/type validation, signature input, and the sole self-referential
  `STATE.sig` exclusion.
- Defined compact projections at
  `.agent-loop/INITIATIVE_STATE/<initiative-id>.md`, deterministic ordering,
  required fields, and the warning that pre-04B conversational/unmerged starts
  are not represented.
- Made live replay bind dynamically to current protected `main` and immutable
  merge-intent/check evidence; AUTH-09E and custody transitions remain historical
  fixtures rather than stale live assumptions.
- Added fast-forward replay recovery for unexpected branch paths without manual
  edits or force-push.
- Required AGENTS, memory skill, policy, and runbook updates during
  implementation.
- Made authenticated cancel/correct events and active-chunk/merge matching
  mandatory 04B preimplementation gates.
- Clarified that projection timestamps come from authenticated source events,
  never render wall-clock time.
- Confined writes to fixed temporary roots, limited branch-controlled reads to
  authenticated canonical inputs, allowed trusted code/key and Git metadata
  reads, and required outside-sentinel preservation.

## Implementation review focus

- Extend the existing ledger validator, paired renderers/checker, signature
  payload, and preparation/replay flow; do not create parallel state machinery.
- Read retained canonical inputs through Git objects or equivalent no-follow
  safe handling before trusting hostile checkout path types.
- Prove the exact replacement tree, prior-tip parent, signature domain,
  deterministic timestamps, dynamic replay, and unchanged external sentinels.

## Gate

Planning review passes with no open blocker. No reviewer session remains needed
for planning. Implementation requires a separate explicit human approval and a
fresh exact-SHA implementation review across all nine tracks.
