# PR Trust Bundle: WS-ENG-007-PLAN

## Goal

Plan a deterministic way for concurrent PRs to preserve still-valid internal
agent review while always rerunning CI on the exact latest combined tree.

## What Changed

- Added intent, discovery, decisions, risks, plan, status, and a three-chunk
  implementation map for concurrent PR review reconciliation.
- Added exact contracts for reviewed-patch/base-delta proof, finding and track
  reconciliation, and merge-group CI parity.
- Added the one required merge intent naming `WS-ENG-007-01` as the same-
  initiative successor behind a separate explicit start.

## Design

The design reconstructs and verifies an exact candidate tree from canonical Git
objects. A repository-owned boundary graph decides which internal reviewer
tracks an upstream delta can affect. Structured resolution predicates classify
findings as resolved, still valid, or unknown; uncertainty always invalidates.
Human GitHub approval is never preserved or automated by this mechanism.

## Scope Control

This is planning evidence only. It changes no runtime, workflow, test,
dependency, coverage threshold, branch protection, merge queue setting, signed
loop-memory generator, or authorization behavior.

## Reviewer Results

All nine required internal tracks passed exact planning commit
`fd153b0ee7c62d3b6fe1ad157f243cc34aadacbe` after valid findings were repaired.
The evidence-only files added afterward are this trust bundle and the adjacent
internal-review record. No reviewer session remains open.

## CI Integrity And Test Delta

No CI or test file changed. The plan explicitly preserves the repository-wide
78 percent and protected-subsystem 90 percent coverage floors and prohibits
skips, deselection, weakened assertions, or changed required-check semantics.

## Remaining Risks

- Unknown or ambiguous deltas deliberately rerun more reviewer tracks.
- Real merge-group evidence cannot exist until a human administrator enables
  the queue after chunk 03; mismatch requires immediate disablement.
- The design has no effect until all separately reviewed chunks are implemented
  and merged.

## Human Review Focus

Confirm that only internal agent review can be preserved, exact combined-tree
CI always reruns, overlap and uncertainty invalidate conservatively, and no
implementation starts from this planning PR.

## Human Merge Ownership

Only the user may approve and merge this PR. After merge, the initiative remains
stopped until the user explicitly starts `WS-ENG-007-01` through signed loop
memory on exact current `main`.
