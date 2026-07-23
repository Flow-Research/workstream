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
`da29deafd13b1f7fdacaf5aa32af2c26adeef0d0` after trusted AUTH-10B2 main head
`73b45792` was merged and all valid internal and CodeRabbit findings were
repaired. The only changes after that reviewed combined head are this trust
bundle and the adjacent internal-review record. No reviewer session remains
open. PR #187 itself changes no backend, test, workflow, or coverage file; the
combined tree contains already-merged AUTH tests that fresh exact-head Backend
CI must revalidate.

## External Review

CodeRabbit raised six actionable planning findings. All were accepted and
closed: versioned canonical finding identity, deterministic linked/contradiction
outcomes, an explicit merge-group synthetic test command, universal all-track
invalidation for unknown impact, immutable diagnostic-checker identity, and
initiative-specific explanation of inherited reviewer session IDs. Its PR-
description warning is addressed in the complete trust-bundle PR body. The
reported Checkov import failure is CodeRabbit tool-environment output, not a
repository check failure and not a reason to weaken or add repository CI.
The first repaired exact-head Agent Gates run then identified the slash-form
schema marker as a noncanonical API prefix. The marker is now route-neutral,
the stale authorization documentation scan passes, and all internal tracks
reapproved the exact repair.

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
