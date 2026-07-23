# Decisions: WS-ENG-007 - Concurrent PR Review Reconciliation

## D1 - CI always reruns on the combined tree

Review preservation never preserves CI results across a base advance.

## D2 - Preserve internal tracks, not human approval

GitHub approval and explicit human merge ownership remain governed by branch
protection and repository policy.

## D3 - Effective patch identity is mandatory

File-path disjointness is insufficient. Preservation requires the same
canonical PR-authored delta and declared boundary non-impact.

## D4 - Unknown means stale

Missing objects, ambiguous dependencies, conflicts, or unsupported merge shapes
invalidate conservatively.

## D5 - Upstream resolution requires a predicate

A finding is resolved upstream only when its closed resolution predicate is
deterministically `true` on the exact candidate tree. `false` remains
`still_valid`; `unknown` makes every reviewer track stale because the affected
set is not proven.

## D6 - Merge queue comes last

Do not enable merge queue until both required workflows and evidence gates prove
`merge_group` parity.

## D7 - One shared Git evidence implementation

Extract strict tree/delta primitives for reuse; do not create a second parser
or rely on fuzzy patch application.

## D8 - Closed repository-owned boundaries

PRs cannot declare their review surface. A versioned policy graph derives path
classes, transitive impacts, and reviewer escalation.

## D9 - Detection and lifecycle states differ

`unknown` is a reconciliation result; `track_stale` for every track is its
mandatory reviewer lifecycle consequence. Neither is a claimant override.
