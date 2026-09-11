# Chunk Contract: WS-ARCH-001-03B TASK Assignment API

Status: non-executable planning skeleton after 03A. Risk: L1. Outcome: TASKS exposes claim, active
assignment, contributor, predecessor and immutable locked-context commands and
facts without importing PROJECTS or AUTH internals.

The bounded [project-grant repair](../../../../changes/task-project-grant-authorization.md)
already owns canonical contributor claim/start/work-context, separate management
work-context and system-Operator start authority. Reuse its command/port and
assignment transaction, not a second claim implementation. This skeleton still
owns the missing contribution-policy attempt locks, queues, broader projections
and invalidation behavior below; it is not completed by that repair.

The TASK readiness command inherits the ContributionPolicyVersion already
bound to the active Project Guide and locks it once as
`WorkstreamTask.locked_contribution_policy_version_id` before the task becomes
claimable. The later claim command performs no CON lookup: it copies that exact
locked identifier to
`TaskAssignment.submitter_contribution_policy_version_id` inside the TASK-owned
assignment transaction. TASK does not select, evaluate, or own
ContributionPolicy rules. `SubmissionCreationCommand` stamps the assignment's
current attempt version as immutable
`Submission.contribution_policy_version_id`.

Preserve the existing readiness transition boundary: draft-to-screening may
stamp the guide-bound version; screening-to-READY verifies that persisted
complete lock. Neither READY nor claim selects a current CON version. A stale
lineage means a mismatch within the attempt's locked context, not merely a
new policy publication elsewhere. Remove retired economic reads/writes from
these replacement commands and their public projections before ARCH-03C;
physical columns remain until CP09 proves all other consumers are gone.

Allowed: `backend/app/modules/tasks/api/**`, the smallest TASKS-owned
claim/assignment/service extraction, focused TASK tests, composition adapters,
`backend/app/modules/tasks/router.py` for deny-only route declarations,
boundary ledgers and initiative evidence/status. Not allowed: project-policy
evaluation, checker planning, artifact custody, AUTH decisions, legacy
eligibility fallback, public route cutover or revision semantics.

Declare the missing ready queue and replacement task surfaces against hidden
owner commands; ARCH-03C owns their exact activation and live route switch.
Do not leave an unowned route step between public ports and user-visible
behavior. The queue must filter project/visibility before counts and cursors.
Own the distinct management, operational and audit locked-context projections
and their field contracts, plus management task detail/work-context/submission
requirements reads. 03C supplies their separate action/permission declarations;
also own the management/operational queue and covered Audit task-evidence
projections enumerated there. Scope filtering precedes counts, cursors and
serialization; operational status never includes contributor-private detail.
For every one of these surfaces,
no projection selects a permission using a token role or leaks another
principal's fields. Preserve authorized PM reads when replacing old routes.

Preserve pre-submit authority invalidation: exact submitter-grant revocation
or actor/link suspension/deactivation closes claimed/in-progress assignments
as `authority_revoked`, returns the task to READY, clears `assigned_to` and
retains history. The operation verifies exact cause event, actor, grant/link,
project and role, is idempotent, and does not restore work on reactivation.
Another eligible submitter may then claim normally. Wrong-role events and
already-submitted/evaluation/review history cannot be rewritten. Downstream
needs-revision obligations and manager reassignment remain REV-owned work;
there is no new direct manager assignment feature here.

Build this as a hidden TASK-owned event handler with exact fixed-service
authority supplied by 03C, using the shared outbox's committed claim contract.
03C must wire AUTH invalidation events durably in their originating transaction;
a response hint such as `auth13_assignment` is not a delivered reconciliation.

Reuse and extend `TaskSubmissionContextPort`, `TaskSubmissionContextFacts`, and
`SubmissionCreationCommand`. Do not introduce parallel assignment,
contributor, predecessor, locked-context, or Submission vocabulary unless a
reviewed current-main delta proves the existing public type cannot carry it.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head and reviewers.

Acceptance: acquiring the task's lock fails when the then-active guide has
no same-project published, complete, binding-valid immutable
ContributionPolicyVersion; a newer publication alone cannot mutate an existing
task or assignment. The later human-revision contract is the only controlled
same-Task/TaskAssignment rebase boundary. Concurrent claims have one
winner; inactive/replaced assignment,
wrong contributor, internally inconsistent locked generation and invalid
predecessor deny; a newer current guide does not stale-deny a frozen task;
the assignment version must equal the task lock and any missing, cross-project,
stale, or changed lineage denies before assignment creation; claim performs no
policy selection and later publication cannot mutate either current-attempt
lock; Submission creation stamps the exact attempt version before any later
human-revision rebase;
facts contain no ORM/session object; touched debt shrinks. Verify focused unit
and PostgreSQL race tests, boundary validators, Ruff and hosted coverage.
Required reviews: architecture, security, product/ops, QA, senior and test
delta.

## Merge state

- Outcome on merge: `planned`
