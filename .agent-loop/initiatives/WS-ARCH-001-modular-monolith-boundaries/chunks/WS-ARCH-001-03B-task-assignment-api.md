# Chunk Contract: WS-ARCH-001-03B TASK Assignment API

Status: non-executable planning skeleton after 03A. Risk: L1. Outcome: TASKS exposes claim, active
assignment, contributor, predecessor and immutable locked-context commands and
facts without importing PROJECTS or AUTH internals.

Allowed: `backend/app/modules/tasks/api/**`, the smallest TASKS-owned
claim/assignment/service extraction, focused TASK tests, composition adapters,
boundary ledgers and initiative evidence/status. Not allowed: project-policy
evaluation, checker planning, artifact custody, AUTH decisions, legacy
eligibility fallback, public route cutover or revision semantics.

Reuse and extend `TaskSubmissionContextPort`, `TaskSubmissionContextFacts`, and
`SubmissionCreationCommand`. Do not introduce parallel assignment,
contributor, predecessor, locked-context, or Submission vocabulary unless a
reviewed current-main delta proves the existing public type cannot carry it.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head and reviewers.

Acceptance: concurrent claims have one winner; inactive/replaced assignment,
wrong contributor, stale project generation and invalid predecessor deny;
facts contain no ORM/session object; touched debt shrinks. Verify focused unit
and PostgreSQL race tests, boundary validators, Ruff and hosted coverage.
Required reviews: architecture, security, product/ops, QA, senior and test
delta.

## Merge state

- Outcome on merge: `planned`
