# Chunk Contract: WS-XINT-003-02 — Review And Revision Policy Mutation Activation

## Status

Non-implementable planning skeleton after 01. Before implementation, refresh on
current main with exact allowed files and commands, then require an explicit
user request for this chunk.

## Goal

Implement one immutable/versioned policy persistence path and authorize the two
covered-project policy mutation routes through the existing PREP protocol.

## Risk class

L1 policy and authorization mutation.

## Allowed files

Must be enumerated exactly at current-main start. Only policy-owned project/REV
models, repository/service/routes, AUTH typed contexts/catalogue parity,
migration, focused tests, docs, and this initiative's evidence may be included.

## Not allowed

Queue, lease, Review, finding, revision execution, artifact, CON, adjudication,
reputation, frontend, duplicate policy tables, or legacy writer compatibility.

## Acceptance criteria

- Only a covered Project Manager with the exact project grant may update the
  review or revision policy for that project and guide lineage.
- The actions remain distinct: `project.review_policy.update` and
  `project.revision_policy.update`.
- Final PREP consumption binds actor/link/grant, project, guide/version,
  existing/reserved policy identity, operation, request digest, idempotency,
  session, transaction, and server-validated policy facts.
- Cross-project, stale guide, wrong policy/action, revoked, replayed, copied, or
  concurrent changed requests deny with no policy/audit partial state.
- The previous embedded or duplicate writer path is removed without backward
  compatibility.
- No review lifecycle action is activated.

## Verification

Focused PostgreSQL policy/authorization/migration/concurrency tests, Ruff,
90-percent changed-subsystem coverage, hosted full coverage, API contract proof,
and all required L1 reviewers.

## Stop condition

Merge and stop before queue/lease activation.
