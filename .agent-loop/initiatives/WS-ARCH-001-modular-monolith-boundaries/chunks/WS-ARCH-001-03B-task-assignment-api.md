# Chunk Contract: WS-ARCH-001-03B TASK Assignment API

Status: non-executable planning skeleton after 03A. Risk: L1. Outcome: TASKS exposes claim, active
assignment, contributor, predecessor and immutable locked-context commands and
facts without importing PROJECTS or AUTH internals.

The TASK readiness command inherits the ContributionPolicyVersion already
bound to the active Project Guide and locks it once as
`WorkstreamTask.locked_contribution_policy_version_id` before the task becomes
claimable. The later claim command performs no CON lookup: it copies that exact
locked identifier to
`TaskAssignment.submitter_contribution_policy_version_id` inside the TASK-owned
assignment transaction. TASK does not select, evaluate, or own
ContributionPolicy rules.

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

Acceptance: task readiness fails before claimability when the active guide has
no same-project published, complete, binding-valid immutable
ContributionPolicyVersion; a newer publication affects only a later task
readiness lock and cannot mutate an existing task. Concurrent claims have one
winner; inactive/replaced assignment,
wrong contributor, stale project generation and invalid predecessor deny;
the assignment version must equal the task lock and any missing, cross-project,
stale, or changed lineage denies before assignment creation; claim performs no
policy selection and later publication cannot mutate either freeze;
facts contain no ORM/session object; touched debt shrinks. Verify focused unit
and PostgreSQL race tests, boundary validators, Ruff and hosted coverage.
Required reviews: architecture, security, product/ops, QA, senior and test
delta.

## Merge state

- Outcome on merge: `planned`
