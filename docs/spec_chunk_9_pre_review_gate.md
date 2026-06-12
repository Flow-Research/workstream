# Chunk 9 Pre-Review Gate

## Purpose

Chunk 9 makes internal post-submit checks automatic.

When an operator locks the latest submission, Workstream immediately runs the durable checker framework against that exact submission version and artifact manifest. A task cannot move to human review until this gate has completed.

This matches the operating pattern we want from serious evaluation systems: the worker can run pre-submit feedback before sending work, but Workstream still owns the authoritative internal check after submission lock.

## Scope

- automatic checker run trigger from submission locking
- `submitted -> auto_checking` task transition when the gate starts
- `auto_checking -> review_pending` when blocking checks pass
- `auto_checking -> needs_revision` for worker-fixable blocking failures
- internal `task_setup_blocked` route for task setup defects owned by project managers
- checker run audit events for gate start, checker trigger, pass, needs-revision, and internal block outcomes
- latest locked submission enforcement
- manual checker retry after a completed run

## Non-Scope

- human review decision records
- reviewer queue UI
- revision replay enforcement
- contribution records
- payment records
- reputation records
- external checker worker infrastructure
- override endpoint

Chunk 9 does not add a public override endpoint. If override support is added later, it must require a trusted actor, reason, linked audit event, and a clear distinction from normal checker routing.

## Contract

The canonical flow is:

```text
worker submits packet
-> operator locks latest submission
-> Workstream runs CheckerRun with trigger_source = submission_locked
-> task moves submitted -> auto_checking
-> checker results determine the next route
```

Route outcomes:

- `allow_review`: task moves to `review_pending`
- `needs_revision`: task moves to user-facing `needs_revision`
- `task_setup_blocked`: task remains in `auto_checking` for project-manager repair
- `checker_retry`: task remains in `auto_checking` until a trusted retry or repair happens

`task_setup_blocked` and `checker_retry` are internal checker routing recommendations. They are not review decisions and they are not worker-facing task outcomes.

## Latest Submission Rule

Only the latest submission version can be locked or checked.

If a worker submits a new version after `needs_revision`, older locked versions stay immutable and cannot receive new checker runs.

## Policy Binding

The automatic run uses the policy context already stamped on the locked submission:

- locked guide version
- locked checker policy version
- locked review policy version
- locked revision policy version
- locked payment policy version

The worker does not provide or restate these policy versions.

The checker service loads required checker names and blocking severities from the locked checker policy. Unregistered checker names are policy errors and block the lock/gate path with a structured API error.

## Revision Boundary

Checker-caused revision uses the same user-facing task state as human review revision: `needs_revision`.

The source remains explicit:

- `outcome_source = auto_checker`
- `review_decision_id = null`
- `checker_run_id = <run id>`

Human review can later create `needs_revision`, but that will carry:

- `outcome_source = human_review`
- `review_decision_id = <review decision id>`

This keeps the user-facing language simple while preserving audit clarity.

## Audit Events

Chunk 9 writes task-level gate audit events:

- `pre_review_gate_started`
- `pre_review_gate_passed`
- `pre_review_gate_needs_revision`
- `pre_review_gate_blocked`

It also keeps the submission-level checker audit event:

- `checker_run_triggered`

Each event records actor identity, auth source, task id, submission id, submission version, locked policy versions, trigger source, and the checker routing context where applicable.

## Conditions Of Satisfaction

- locking a clean latest submission creates attempt 1 automatically
- automatic run uses `trigger_source = submission_locked`
- clean submission moves task to `review_pending`
- worker-fixable blocking result moves task to `needs_revision`
- task setup defect produces `task_setup_blocked` and keeps task internal in `auto_checking`
- worker-visible checker responses do not leak internal `task_setup_blocked` details
- manual checker retry supersedes the prior current run and increments attempt number
- older submission versions cannot receive checker runs after a newer submission exists
- checker-caused revision does not create a human review decision
- checker policy errors return structured API errors through the lock endpoint
- Postgres-backed integration tests cover the complete API flow
