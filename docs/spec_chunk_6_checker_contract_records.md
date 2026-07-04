# Chunk 6: Checker Contract And Records

## Purpose

Chunk 6 creates the durable checker run and checker result contract for Week 2.

This chunk does not run the full checker framework yet. It defines the durable post-submit checker records, the pre-submit intake feedback response contract, schemas, service boundaries, and read APIs that later chunks use for static checks, internal auto checks, and review gating.

## Scope

- checker run model
- checker result model
- checker run status values
- checker result status and severity values
- trigger source fields
- routing recommendation fields
- source tracking for checker-caused `needs_revision`
- pre-submit intake feedback response contract
- backend read APIs for checker runs and results
- internal service method for creating checker runs/results
- migration and ORM metadata
- tests for persistence, visibility, and immutability expectations

## Non-Scope

- real checker registry
- real checker execution
- automatic background trigger after submission locking
- task lifecycle movement to `EVALUATION_PENDING`, `REVIEW_PENDING`, or `NEEDS_REVISION`
- readiness certificate creation; deferred to Chunk 9 when the pre-review gate is implemented
- product frontend
- reviewer queue UI
- human review decisions
- revision replay enforcement
- contribution, payment, or reputation records

## Required Model

`checker_runs`

- `id`
- `task_id`
- `submission_id`
- `submission_version`
- `trigger_source`
- `status`
- `routing_recommendation`
- `outcome_source`
- `triggered_by`
- `triggered_by_subject`
- `triggered_by_issuer`
- `trigger_auth_source`
- `trigger_reason`
- `audit_event_id`
- `attempt_number`
- `supersedes_checker_run_id`
- `is_current_for_submission`
- `locked_guide_version`
- `locked_post_submit_checker_policy_version`
- `locked_review_policy_version`
- `locked_revision_policy_version`
- `locked_payment_policy_version`
- `package_hash`
- `artifact_hash_manifest`
- `artifact_manifest_hash`
- `blocking_failure_count`
- `warning_count`
- `started_at`
- `completed_at`
- `failure_message`
- `created_at`
- `updated_at`

`checker_results`

- `id`
- `checker_run_id`
- `checker_id`
- `checker_name`
- `checker_version`
- `phase`
- `status`
- `severity`
- `blocks_review`
- `message`
- `suggested_fix`
- `worker_message`
- `worker_suggested_fix`
- `evidence_refs`
- `worker_evidence_refs`
- `metadata`
- `worker_visible`
- `created_at`

## Canonical Values

`checker_runs.trigger_source`

- `submission_locked`
- `manual_checker_trigger`
- `retry`

`checker_runs.status`

- `queued`
- `running`
- `completed`
- `failed`

`checker_runs.routing_recommendation`

- `not_evaluated`
- `allow_review`
- `needs_revision`
- `checker_retry`
- `task_setup_blocked`

`routing_recommendation` is not a human review decision field. It is a checker-side routing recommendation used before human review.

`allow_review` means the checker run found no blocking issue and the submission may proceed to human review. It must not be stored as `accept`, because no human reviewer has accepted the work yet.

`task_setup_blocked` means the task's locked contract or policy context is incomplete, stale, or unsafe to review. The fix belongs to a project manager, not the worker.

`needs_revision` from a checker run must carry `outcome_source = auto_checker` and no review decision id. `needs_revision` from a human reviewer must carry `outcome_source = human_review` and a review decision id.

`checker_runs.outcome_source`

- `none`
- `auto_checker`

`checker_results.status`

- `passed`
- `warning`
- `failed`

`checker_results.severity`

- `info`
- `low`
- `medium`
- `high`
- `critical`

## Record Binding

Durable `checker_runs` are authoritative post-submit records only. They must bind to one locked submission version.

The run snapshots:

- `task_id`
- `submission_id`
- `submission_version`
- `package_hash`
- `artifact_hash_manifest`
- deterministic `artifact_manifest_hash`
- locked project guide version
- locked post-submit checker policy version
- locked review policy version
- locked revision policy version
- locked payment policy version

Post-submit checker runs must be created only from a loaded, locked submission. The service must copy `task_id`, `submission_version`, `package_hash`, `artifact_hash_manifest`, `artifact_manifest_hash`, and locked policy versions from that submission. The client does not provide locked guide or policy versions for checker runs.

The migration must add enough constraints or service-level tests to prove a checker run cannot bind `submission_id` to a different task, submission version, or package hash. Prefer a composite foreign key or unique binding where practical; otherwise add explicit service validation and integration tests that fail on mismatched context.

Only the current completed post-submit checker run can be used by Chunk 9's pre-review gate. Chunk 6 stores the provenance needed for that later gate:

- `attempt_number`
- `supersedes_checker_run_id`
- `is_current_for_submission`
- `completed_at`
- `artifact_manifest_hash`
- `package_hash`

## Artifact Manifest Hash

`artifact_manifest_hash` is SHA-256 over canonical UTF-8 JSON.

Normalization rules:

- validate every entry against `ArtifactHashEntry`
- sort entries by `artifact`, then `hash`
- reject duplicate `artifact` values
- serialize with sorted object keys and compact separators
- preserve all persisted fields that affect artifact identity: `artifact`, `hash`, `size_bytes`, and `notes`
- equivalent manifests with different JSON key order or entry order must produce the same hash
- any changed artifact hash, size, path, or notes must produce a different hash

## Pre-Submit Intake Feedback Contract

Pre-submit checks run before a submission is created. They are authoritative for submission intake and return immediate API feedback without creating an authoritative post-submit checker run.

Workstream loads the locked generated project pre-submit checker compiled bundle hash
for the task's guide version. Workers submit only draft packet fields. They
cannot choose checker names, policy versions, blocking rules, severities,
results, or outcomes.

Response fields:

- `run_type = pre_submit`
- `task_id`
- `actor_id`
- `request_hash`
- `eligible_to_submit`
- `artifact_manifest_hash`
- `blocking_failure_count`
- `warning_count`
- `results`
- `submission_created = false`
- `durable_checker_run_id = null`
- `created_at`
- `expires_at`

Pre-submit feedback binds to `task_id`, the task's locked guide source snapshot,
effective project submission artifact policy hash, pre-submit checker bundle hash,
draft packet fields, package hash, and artifact manifest shape. It does not
require a locked `submission_id` or locked submission version because those do
not exist before submission creation.

Blocking pre-submit failures prevent submission creation. Preflight failures
return `PreSubmitCheckResponse(status="failed", eligible_to_submit=false,
results=[...])`. Blocked submission-create attempts return
`DomainError(code="pre_submission_checker_failed")` with structured
pass/fail/warning details, create no submission row, no submission version, no
task transition to `submitted`, and no submission-created audit event.

Pre-submit results are not authoritative for `REVIEW_PENDING`, cannot create
`NEEDS_REVISION`, and do not return review decision values: `accept`,
`needs_revision`, or `reject`. Only post-submit runs against locked submissions
can produce routing recommendations for `REVIEW_PENDING` or user-facing
`needs_revision`.

## User-Facing Revision Rule

User-facing outcomes remain simple:

- `accepted`
- `rejected`
- `needs_revision`

Checker-caused revision uses the same user-facing `needs_revision` state, but records the source internally:

- `routing_recommendation = needs_revision`
- `outcome_source = auto_checker`
- `review_decision_id = null` when that field exists in later review work

Human reviewer revision remains separate later:

- `outcome = needs_revision`
- `outcome_source = human_review`
- `review_decision_id` present

Chunk 6 stores the checker-side source fields but does not implement human review decisions.

## API Contract

Read APIs:

- GET `/api/v1/submissions/{submission_id}/checker-runs`
- GET `/api/v1/checker-runs/{checker_run_id}`

Checker read and trigger APIs use the existing external Flow authentication boundary. Workstream verifies Flow-issued tokens, resolves actor context, and applies object-level authorization. Chunk 6 must not introduce Workstream-owned login, password, session, or API key auth.

Public APIs must not create, update, or delete durable checker results.

Durable `CheckerRun` and `CheckerResult` records are written only by Workstream-owned checker services using server-derived checker output. External Flow actors may request allowed pre-submit checks or authorized retry triggers in later chunks, but they must never provide checker names, result status, severity, `blocks_review`, metadata, routing recommendation, locked policy context, or pass/fail payloads.

Any future trigger endpoint creates only a run request. The checker service computes and persists all results.

Write behavior is internal service/repository only in Chunk 6. Chunk 7 and Chunk 9 can expose controlled trigger paths that still do not accept caller-supplied result payloads.

## Visibility Rules

Read authorization must be object-scoped, not role-only.

- workers can read worker-visible checker output only for submissions on tasks assigned to them
- project managers can read operational checker output only for projects they manage
- admins can read operational checker output globally
- reviewers can read checker output only after the submission is assigned to them for review in later review work
- auditors can read according to the audit/read-only policy, but cannot see worker-hidden sensitive metadata unless explicitly allowed by audit policy

Worker responses include only result rows where `worker_visible = true`. For hidden operational results, worker responses may expose aggregate counts but must not expose checker id, metadata, internal rule ids, logs, stack traces, or unsafe evidence refs.

Worker-visible responses are built from sanitized worker-facing fields, not raw checker metadata. They may include:

- checker name
- status
- severity
- `worker_message`
- `worker_suggested_fix`
- safe `worker_evidence_refs`

Raw `metadata`, internal rule IDs, stack traces, hidden-test details, reviewer-simulation prompts, private storage paths, secrets, and security heuristics are never returned to workers.

Project managers and admins can see operational metadata.

## Manual And Retry Audit Rules

`manual_checker_trigger` and `retry` trigger sources require:

- `triggered_by`
- Flow auth subject
- Flow auth issuer
- auth source
- reason
- `audit_event_id`

System-triggered runs use a Workstream service principal. Manual runs must be attributable to an authorized admin or project manager and must not overwrite prior checker results.

## Immutability Rules

Checker results are append-only after persistence. No public API can update or delete checker results.

Internal services may only create new runs/results or transition a run status through allowed states. Checker runs may update only lifecycle fields before terminal status: `status`, counts, `started_at`, `completed_at`, and `failure_message`. After `completed` or `failed`, run records are immutable except for explicit audited retry records in later chunks. Corrections require a new checker run linked to the prior run.

## Conditions Of Satisfaction

- migration creates checker run and checker result tables
- ORM models match migration metadata
- checker runs reference existing task and submission records
- migration upgrade/downgrade passes against Postgres
- post-submit checker run creation snapshots locked submission context server-side
- creating run for an unlocked submission fails
- creating run with mismatched task/submission context fails
- later project policy changes or audited task-context rebases do not mutate historical checker run context
- artifact manifest hash follows the canonical SHA-256 JSON algorithm
- equivalent manifests with different entry or key order hash identically
- duplicate artifact names are rejected
- pre-submit invalid packet returns structured feedback without creating a submission
- pre-submit result cannot be reused as post-submit gate proof
- checker results are tied to one checker run
- canonical status/severity values are enforced by schemas/service constants
- read APIs return checker run and checker result records
- workers cannot read unrelated checker runs
- workers do not receive hidden result rows, raw metadata, internal rule ids, logs, stack traces, unsafe evidence refs, secrets, or security heuristics
- project managers and admins can read operational checker output
- clients cannot create, update, delete, or spoof checker results through public APIs
- tests cover persistence, visibility, and locked-context snapshotting
- API integration tests use real Postgres-backed data and authenticated Flow actor headers
- tests do not rely only on monkeypatch/unit-only paths for checker run creation, visibility, or binding
- no public update/delete endpoints exist for checker results
- docstring coverage remains above threshold

## Verifier Agents

- senior engineering
- QA/test
- security/auth
- product/ops
