# Chunk Contract: WS-REV-001-03A - Queue And Lease Base Persistence

## Status

Proposed only. Not started and not implementation authorization. After 03P
merges, refresh/review this contract on exact current main and start it only
through a signed `Loop Memory Explicit Event`.

## Parent

`WS-REV-001-03` Review Queue And Lease Persistence.

## Goal

Persist the smallest REV-owned queue-entry and lease foundation for an existing
finalized Submission whose durable final current checker outcome is exactly
`allow_review`.

## Risk

L1: concurrent admission, reviewer authorization, immutable intake identity,
and audit lineage.

## Required owner handoffs before start

- Submission owner: finalized Submission identity, Task/contributor lineage,
  immediate predecessor semantics, and submitted artifact membership.
- Checker owner: durable final/current status and exact `allow_review` outcome.
- ART owner: typed read access to the same submitted/verified artifact set;
  REV does not copy, finalize, or mutate artifact custody.
- AUTH owner: canonical reviewer ActorProfile and permission facts.
Each handoff must be named by merged owner chunk, PR/SHA, typed symbol or
manifest, migration head where relevant, and focused proof. Any gap is reported
to the human and implemented by its owner, never by REV.

## Allowed files

To be fixed during the required current-main refresh. They may include only
REV-owned queue/lease models, migration, repository/service ports, focused
tests, and this initiative's evidence and merge-intent files.

## Not allowed

- Project Guide setup, publication, activation, chronology, or reactivation.
- Task intake/context stamping, Submission creation/finalization, CheckerRun
  production, artifact custody, AUTH policy, or CON contribution implementation.
- Review decisions, findings, revision preparation, FinalAcceptance, routes,
  adjudication, reputation, or frontend work.
- Starting implementation from this proposed contract.

## Acceptance criteria

- Persistence links only to an exact finalized Submission identity and preserves
  its artifact membership identity; it implements no admission transition.
- Database constraints prevent multiple live queue identities for the same
  reviewable Submission; online checker-triggered admission and its race
  behavior remain owned by 05A.
- Lease persistence cannot authorize self-review and retains auditable actor and
  timing facts without yet implementing claim/release behavior.
- Queue records link to the exact Submission and Task so later Review and
  Submission predecessor chains remain fully traversable.
- No upstream-owned row or lifecycle transition is mutated.
- CON is not a 03A dependency. Its completed-review participant is required only
  by the later canonical decision composition.

## Verification

To be made exact at start: focused model/migration/service tests, PostgreSQL
concurrency proof, downgrade/refusal proof, repository regression tests, the
agent gates, and full coverage through GitHub Actions.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
reuse/dedup, docs, test-delta, and CI integrity.

## Human review focus

Confirm that every input is an owner-proven handoff, that REV begins only at
`allow_review`, and that this chunk adds persistence without decision behavior.

## Stop

Do not implement without a signed start on the refreshed exact-current-main contract.
