# WS-ENG-005-01 PR Trust Bundle

## Goal

Allow maximum safe concurrent work across distinct initiatives while retaining
exactly one active planning or implementation chunk inside each initiative.

## Human-approved intent

The user explicitly rejected repository-global serialization and approved
initiative-local concurrency. Separate worktrees enable execution but are not
canonical authority.

## What changed

- Removed the global-active predicate from event application, ledger replay,
  and the independent checker.
- Retained target-initiative active exclusion in all three trust layers.
- Updated policies and operator guidance for concurrent initiatives.
- Added mixed AUTH/ART/CI proof, both close orders, cross-initiative isolation,
  exact projections, bootstrap recovery, and real signed-state drill evidence.

## Boundaries preserved

Exact main and prior tip, immutable reviewed contract selection, current writer
permission, one active chunk per initiative, duplicate/completed/replay denial,
cancellation approval, signed ledger/manifest, CI, internal review, and explicit
human merge ownership remain.

## Conflict model

Parallel start is not conflict-free merge. Branches rebase onto current main and
rerun proof/review. Rebase never replaces signed contract authority or permits
scope drift. Once parallel history exists, later restriction must use a
forward-compatible repair rather than restoring the old replay invariant.

## Proof

- 209 focused tests and 89 agent gates pass.
- Updater/checker branch coverage: 90.22/90.81 percent against unchanged 90
  percent floors.
- Three initiatives remain active with mixed planning/implementation phases.
- Successful merge and cancellation in both orders preserve unrelated work.
- Real signed AUTH-10A state accepts exact ART-02C3 in a temporary drill.
- All nine internal review tracks pass exact SHA `49afb7db`.

## Bootstrap

The old global rule cannot sign its own replacement while AUTH is active. A
schema-v2 exact-single-target certificate binds only WS-ENG-005-01, exact first
parent, target identity, and plan `[target]`; it is consumed before publication
and cannot replay.

## External review

Fresh GitHub checks and CodeRabbit are pending after publication. CodeRabbit
free-tier rate limiting is recorded separately from actual findings.

## Human review focus

Verify only global-idle predicates disappeared, same-initiative exclusion is
unchanged, close operations are initiative-local, generated views show all
activity, and bootstrap recovery is exact and self-consuming.

## Human merge ownership

Only the user may approve merging this specific PR. Automation must not merge it.
