# Intent: WS-ENG-007 - Concurrent PR Review Reconciliation

## Problem being solved

When one concurrent PR merges, another open PR must be validated against the
new `main`. Today the repository correctly reruns strict CI, but its internal
review evidence is invalidated coarsely by commit ancestry. Unrelated upstream
changes can therefore trigger full reviewer fanout, while a finding already
fixed upstream can remain misleadingly open.

## Why this work matters

Workstream permits distinct initiatives to run concurrently. That concurrency
must remain safe without making every merge restart every other initiative's
human-agent review loop.

## Current behavior

- Required GitHub checks are strict and require an up-to-date branch.
- GitHub dismisses stale approvals after new commits.
- Internal evidence binds one reviewed code SHA and rejects any later
  non-evidence path.
- The repository has no `merge_group` workflow support, reviewed-patch identity,
  base-delta classifier, or structured upstream-finding disposition.

## Target behavior

- CI always validates the exact combined tree proposed for merge.
- A base advance that provably leaves the reviewed patch and risk boundaries
  unchanged preserves unaffected internal reviewer tracks.
- Findings fixed by trusted `main` are recorded as resolved upstream, not
  repeated against the PR.
- Deterministically known overlap, dependency impact, or effective-diff change
  reruns the derived affected tracks. Ambiguity, conflict, or any unknown
  impact fails closed and stales every track.
- Human approval remains the final merge checkpoint.

## Design chosen

Bind reviews to an immutable base tree, head tree, effective patch manifest,
declared boundary manifest, and reviewer-track impact manifest. Reconcile each
new trusted-main base deterministically. Add merge-group CI only after the
classifier and evidence model are proven.

## Alternatives considered

- Always rerun every reviewer: safe but defeats useful concurrency.
- Preserve reviews whenever changed file paths are disjoint: insufficient for
  dependencies, generated contracts, migrations, and shared interfaces.
- Trust GitHub comments or chat to close findings: mutable and not canonical.
- Allow an AI-only semantic judgment to preserve approval: not deterministic
  enough for a merge gate.

## Boundaries preserved

Signed starts, one active chunk per initiative, required CI, coverage floors,
internal reviewer independence, CodeRabbit's supplementary role, explicit
human merge approval, and automated post-merge memory remain unchanged.

## Expected risks

False preservation is more dangerous than redundant review. Any unclassified
dependency or changed effective patch must invalidate conservatively.

## What must not change

No product behavior, auth/payment/data policy, coverage threshold, contributor
permission, automatic merge authority, or bypass for conflicts and failed CI.

## How this will be proven

Deterministic synthetic Git histories will cover disjoint base changes,
overlapping files, dependency-boundary changes, upstream-resolved findings,
conflicts, rebases, merge commits, squash-equivalent patches, missing objects,
forged manifests, and merge-group combined trees.

## Human decisions required

Approve each implementation chunk and the later repository-setting change that
enables GitHub merge queue. No queue or automatic merge setting changes in the
planning intake.

## Recovery reliability addendum — WS-ENG-007-00R2

### Problem being solved

Signed reconciliation treats legitimate same-name GitHub Actions reruns as
ambiguity. PR #187 therefore cannot enter signed history even though both
`agent-gates` runs and its `test` run are trusted and successful.

### Target behavior

Rerun count is harmless. A deterministic latest trusted run controls each
protected result, later failures cannot be hidden by older successes, and the
exact three-merge backlog is reconciled atomically without reusable authority.

### Boundaries preserved

Required checks, branch protection, signing keys, permissions, human merge
approval, coverage floors, product behavior, and successor start gates do not
change.

### Proof strategy

Adversarial check histories, permutation invariance, exact production policy
pinning, ordered recovery consumption, replay rejection, and byte-identical
idempotency evidence.

### Human decision

The user's explicit `start` instruction approves planning and execution of this
bounded reliability repair only. Successor starts remain separately gated.
