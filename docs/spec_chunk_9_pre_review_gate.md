# Chunk 9 Pre-Review Gate

## Purpose

Chunk 9 makes internal post-submit checks automatic.

When the assigned contributor submits a packet that passes authoritative server-side pre-submit validation, Workstream immediately locks that submission version and queues the durable checker framework against the exact submission version and artifact manifest. A task cannot move to human review until this gate has completed.

This matches the operating pattern we want from serious evaluation systems: the worker can run pre-submit feedback before sending work, but Workstream still owns the authoritative internal check after it locks the submitted packet.

## Scope

- automatic checker run trigger from the locked submission boundary
- `submitted -> evaluation_pending` task transition when the gate starts
- `evaluation_pending -> review_pending` when blocking checks pass
- `evaluation_pending -> needs_revision` for worker-fixable blocking failures
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
-> Workstream locks the latest submission version
-> Celery runs CheckerRun with trigger_source = submission_finalized
-> task moves submitted -> evaluation_pending
-> checker results determine the next route
```

Route outcomes:

- `allow_review`: task moves to `review_pending`
- `needs_revision`: task moves to user-facing `needs_revision`
- `task_setup_blocked`: task remains in `evaluation_pending` for project-manager repair
- `checker_retry`: task remains in `evaluation_pending` until a trusted checker retry or repair happens

`task_setup_blocked` and `checker_retry` are internal checker routing recommendations. They are not review decisions and they are not worker-facing task outcomes.

## Latest Submission Rule

Only the latest submission version can be locked for post-submit evaluation or checked.

If a worker submits a new version after `needs_revision`, older locked versions stay immutable and cannot receive new checker runs.

## Policy Binding

The automatic run uses the policy context already stamped on the locked submission:

- locked guide version
- locked post-submit checker policy id
- locked post-submit checker policy version
- locked post-submit checker policy hash
- locked post-submit checker policy body
- locked review policy version
- locked revision policy version
- locked payment policy version

The worker does not provide or restate these policy versions.

The checker service first creates a durable queued automatic-gate `CheckerRun`
claim, then the Celery worker validates the locked `PostSubmitCheckerPolicy`
id/version/hash/body stamped on the submission and executes from that locked
body. Missing, mismatched, deleted, stale, malformed, or unregistered
post-submit policy context marks the queued claim `failed` with a structured
failure code and no `CheckerResult` rows. Operator repair may requeue the same
claim after the setup defect is fixed; it must not create duplicate current
checker runs.

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

Automatic pre-review gate events are attributed to the server-owned
`workstream-system:pre-review-gate` actor. That actor is never accepted from
client input and cannot authorize HTTP requests. The verified requester remains
visible in audit payloads through requester actor id, external subject, external
issuer, and auth source fields.

Each event records actor identity, auth source, task id, submission id,
submission version, locked policy versions, trigger source, requester
provenance, and the checker routing context where applicable.

## Conditions Of Satisfaction

- creating a clean latest submission locks it and creates attempt 1 automatically
- automatic run uses `trigger_source = submission_finalized`
- clean submission moves task to `review_pending`
- worker-fixable blocking result moves task to `needs_revision`
- task setup defect produces `task_setup_blocked` and keeps task internal in `evaluation_pending`
- worker-visible checker responses do not expose `routing_recommendation`,
  `outcome_source`, internal `task_setup_blocked` details, or other internal
  route tokens
- manual checker retry supersedes the prior current run and increments attempt number
- older submission versions cannot receive checker runs after a newer submission exists
- checker-caused revision does not create a human review decision
- checker policy errors are structured in the automatic gate path; the repair
  endpoint is idempotent and may requeue a repairable locked submission claim
- dispatch and eager-dispatch failures are recorded as
  `pre_review_gate_enqueue_failed`, keep the locked packet in
  `evaluation_pending`, and are repairable through `/finalize`
- `unknown_checker` automatic gate failures are repairable after the missing
  checker registration/setup issue is corrected
- `requester_provenance_mismatch` automatic gate failures are terminal
  integrity failures; operators inspect the locked submission audit,
  checker-run failure details, and retained worker logs if available instead
  of requeueing through `/finalize`
- non-repairable failed automatic gate claims return HTTP 409 from `/finalize`
  with an operator-visible next action instead of reporting false success
- Postgres-backed integration tests cover the complete API flow
