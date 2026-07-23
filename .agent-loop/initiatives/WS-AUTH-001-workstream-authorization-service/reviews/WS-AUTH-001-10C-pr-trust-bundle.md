# PR Trust Bundle: WS-AUTH-001-10C

## Chunk And Goal

`WS-AUTH-001-10C` adds PREP-bound, idempotent, auditable issue and revoke
mutations for independent exact-project contributor roles. Risk is L1
authorization, concurrency, and audit integrity.

## Change, Design, And Scope

- A covered Project Manager can issue submitter, reviewer, or adjudicator for
  one exact project and revoke one exact stored grant.
- Issue captures a bounded immutable qualification snapshot. Revoke derives the
  target and role only from the locked grant and emits the closed typed
  future-obligation invalidation projection.
- Rate consumption, idempotency, the shared authority barrier, lexical
  profile/link locking, PM authority, project, advisory/grant locking, final
  fact recomposition, consume, evidence, and commit use the contract order.
- Replay reauthorizes and reloads canonical ownership/state. Conflict and
  concealment paths do not disclose private target or reservation facts.
- Hosted E2E uses only public APIs for issue, active read, revoke, history,
  replay/state-change conflicts, lifecycle-independent revoke, and authority loss.

All changed files are contract-allowed. There is no migration, durable schema
change, frontend work, automated role conversion, task assignment, review
reconciliation, or successor implementation.

## Proof And Review

Focused lint, compile, contract, ordering, schema, rate, invalidation, and
cancellation checks pass locally. PostgreSQL evidence exercises the real named
partial unique index, public fallback, full loser rollback, database-observed
lock wait, production cancellation rollback, and committed clean retry. The
GitHub Backend workflow must run the full shards, hosted API E2E, repository-wide
78 percent floor, and authorization-subsystem 90 percent floor.

All nine internal tracks pass reviewed implementation SHA
`0d05b7096eb7a2cf7c68a1770c0b35f07d5b55df` with no open finding.

## External Review, Risk, And Human Focus

GitHub CI, Agent Gates, CodeRabbit, and human review remain after publication.
Human review should focus on transaction/lock order, target concealment,
Project-Manager-only authority, replay reauthorization, partial-unique fallback,
revocation availability after lifecycle loss, and audit/invalidation atomicity.
The user retains merge ownership; do not merge without explicit approval of the
specific PR. The declared successor `WS-AUTH-001-11` requires a separate signed
explicit start and must not begin automatically.

