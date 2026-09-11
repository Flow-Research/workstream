# Chunk Contract: WS-ARCH-001-03C AUTH Task Readiness Activation

Status: non-executable planning skeleton after reviewed 03A/03B manifests.
Risk: L1. Outcome: the exact
task/claim/assignment actions below become usable only through the owner
public APIs and one integrated readiness proof.

Allowed: AUTH public API/catalogue/evaluator/PREP composition, delivery-root
wiring, exact `tasks/router.py` route switch/declarations, focused AUTH/TASK
integration tests, boundary/debt ledgers and
initiative evidence/status. Not allowed: TASK lifecycle ownership, private
PROJECT/TASK imports, ART/checker/review activation, generic task permission,
role-only fallback or public Submission cutover.

## Proposed exact surface/action manifest

The bounded [project-grant repair](../../../../changes/task-project-grant-authorization.md)
owns the active `task.claim`, `task.start`, `task.work_context.read`,
`project.task.work_context.read` and `operations.task.start_override` actions.
Reuse those registrations and extend their exact locked-context proof when
03B delivers contribution-policy attempt lineage. The other rows below remain
proposed registrations, not claims of usable actions. This repair does not
activate the queue, remaining projections or invalidation handler.

| Surface | Proposed action | Permission / principal |
|---|---|---|
| Create project task | `project.task.create` | `project.task.manage`; covered Project Manager |
| Screen task / acquire full context lock | `project.task.screen` | `project.task.manage`; covered Project Manager |
| Release screened task to READY | `project.task.release` | `project.task.manage`; covered Project Manager |
| Project ready queue | `task.queue.read` | `task.queue.read`; exact-project Submitter |
| Management task queue | `project.task.queue.read` | `project.task.manage`; covered Project Manager |
| Operational task queue | `operations.task.queue.read` | `operations.status.read`; system Operator, bounded operational fields |
| Task evidence projection | `audit.task.evidence.read` | `audit.read`; covered Audit Authority, read-only evidence |
| Task detail | `task.read` | `task.queue.read`; exact-project Submitter with visibility/state guards |
| Work context | `task.work_context.read` | `task.queue.read`; exact-project Submitter with assignment/state guards |
| Submission requirements | `task.submission_requirements.read` | `task.queue.read`; same exact context/concealment guards |
| Claim | `task.claim` | `task.claim`; exact-project Submitter |
| Normal start | `task.start` | `task.claim`; exact-project Submitter and active own assignment |
| Reasoned recovery start | Existing `operations.task.start_override` | `operations.task.start_override`; human Operator with system-scoped grant |
| Management task detail | `project.task.read` | `project.task.manage`; covered Project Manager |
| Management work context | `project.task.work_context.read` | `project.task.manage`; covered Project Manager |
| Management submission requirements | `project.task.submission_requirements.read` | `project.task.manage`; covered Project Manager |
| Management locked-context projection | `project.task.locked_context.read` | `project.task.manage`; covered Project Manager |
| Operational locked-context projection | `operations.task.locked_context.read` | `operations.status.read`; system Operator |
| Audit locked-context projection | `audit.task.locked_context.read` | `audit.read`; covered Audit Authority |

Normal start reuses the existing submitter claim entitlement, with a separate
action and stricter active-assignment guard; this proposes no separately
grantable start permission. Security/product review must check that mapping
against the canonical role matrix when extending the attempt lineage. Give the three
locked-context projections separate declared surfaces under project,
operations and audit routing, with permission-appropriate fields; do not make
one action switch permission according to a token role.
Retain existing Project Manager detail/context/requirements capabilities
through those separate project-management projections; the submitter action
mapping must not silently remove management reads or grant managers a
Submitter identity. 03B owns all projection fields and concealment guards.

The pre-submit invalidation handler proposes fixed identity
`workstream.task.assignment_reconciler` and sole action/permission
`task.assignment.authority_reconcile`. It consumes only an exact committed
AUTH invalidation event and the TASK-owned 03B handler manifest; no human,
dispatcher or unrelated service receives it. Live reconciliation depends on
CON-02B dispatch plus its exact AUTH activation. Originating authority changes
stage their invalidation event atomically, while every foreground claim/start/
submission still revalidates current authority and never waits for that worker
to deny a revoked actor. Prove crash/redelivery and wrong-role preservation.

Acceptance: actor, identity link, project grant, task, assignment, contributor,
locked generation, transaction and idempotency are exact. Mismatched replay,
revocation and internally stale context deny with atomic evidence; exact valid
replay reuses the stored operation after fresh authority validation. Duplicate
claims converge to one winner. A newer global guide/policy alone does not
invalidate an earlier valid locked attempt.
Task readiness requires the exact guide-bound
`ContributionPolicyVersion` and `WorkstreamTask.locked_contribution_policy_version_id`.
Assignment activation requires equality between that task lock and
`TaskAssignment.submitter_contribution_policy_version_id`. AUTH never selects
or evaluates ContributionPolicy, and neither readiness nor claim may perform a
claim-time policy lookup.
Verify focused tests, PostgreSQL races, catalogue/database parity, boundary
validators, Ruff and hosted coverage. Required reviews: authorization
architecture, security, product/ops, QA, senior, CI and test delta.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head and reviewers.

## Merge state

- Outcome on merge: `planned`
