# Chunk Contract: WS-ARCH-001-03C AUTH Task Readiness Activation

Status: Planned. The exact feature-authority boundary is adopted by
[03C1](../../WS-ARCH-001-03C1.md). The remaining public surface manifest below
remains a planning skeleton requiring a current-source contract before execution.
Risk: L1. Outcome: the exact
task/claim/assignment actions below become usable only through the owner
public APIs and one integrated readiness proof.

Execution sequence: 03C1 real fixed-service assignment authority and exact
decision receipts; 03C2 originating atomic producer fan-out plus first handler
registration with enforced prefork topology; then bounded public task activation.
03C1 does not publish or dispatch retained invalidations. Combining the first
producer with handler registration keeps newly emitted events drainable.

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
Reuse those registrations and extend their exact locked-context proof with the
CP08-delivered contribution-policy attempt lineage. The other rows below remain
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

03C1 delivers the pre-submit invalidation handler's fixed identity
`workstream.task.assignment_reconciler` and sole action/permission
`task.assignment.authority_reconcile`. It consumes only an exact committed
AUTH invalidation event and the TASK-owned 03B handler manifest; no human,
dispatcher or unrelated service receives it. The [03B9 hidden operation](../../WS-ARCH-001-03B9.md) supplies exact cause
validation, assignment release, replay and a same-transaction OUTBOX fence.
Shared dispatch authority is delivered by AUTH-OUTBOX-02. 03C1 supplies exact feature AUTH and decision-bound receipt custody. Production
reconciliation still requires 03C2 producer wiring and first registration. Originating authority changes
stage exact per-assignment events atomically through bounded actor/project
fan-out. Publish only from the originating mutation transaction; never backfill
or dispatch retained invalidation rows. Pre-repair transaction-start timestamps
cannot establish assignment/cause chronology. Capture original assignment IDs through a nonlocking TASK owner
projection while AUTH locks serialize claim; never acquire TASK locks after
AUTH locks. Enforce prefork worker/routing topology before the first production
handler registration. Every foreground claim/start/
submission still revalidates current authority; no worker wait grants access.
Prove crash/redelivery and wrong-role preservation.

The [suspension and task-retry repair](../../../../changes/auth-suspension-task-retry.md)
owns durable claim/start/Operator-start replay on the existing command path.
Reuse that receipt, current-authority recheck and atomic transaction; do not
create a second retry implementation during activation. Other proposed actions
still require their own exact operation proofs when implemented.

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

03C1 has its adopted exact contract. Before each remaining activation, replace
the relevant skeleton rows with a current-main contract enumerating exact files,
commands, migration head and reviewers.

## Merge state

- Outcome on merge: `Planned`
