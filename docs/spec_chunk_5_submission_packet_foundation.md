# Chunk 5: Submission Packet Foundation

## Purpose

This chunk adds the backend record for Contributor submission packets. A
Contributor submits against a task id, Workstream runs pre-submit intake checks
from the locked project pre-submit checker policy, stamps the task's locked
guide source snapshot, effective project submission artifact policy, project
pre-submit checker bundle, post-submit checker, review, revision, and payment
context, and every submitted packet version becomes immutable during successful
submission creation before checker execution is queued.

This completes the Week 1 backend lifecycle through `SUBMITTED`.

## Scope

- submission packet model
- evidence item model
- generated pre-submit intake gate before submission creation
- package URI and package hash metadata
- artifact hash manifest
- worker attestation
- submission versioning
- task transition from `IN_PROGRESS` to `SUBMITTED`
- submission audit events
- API paths for creating, reading, listing, and repair-checking locked submission packets

## Non-Scope

- new post-submit checker execution behavior beyond the automatic pre-review gate
- new checker run record schema
- human review decisions
- revision replay enforcement
- contribution, payment, or reputation records
- direct file upload or object storage implementation

Chunk 5 stores package and evidence references. Actual file storage still belongs behind the later object-storage abstraction.

## Data Model

`submissions`

- `id`
- `task_id`
- `contributor_id`
- `version`
- `status`
- `summary`
- `package_uri`
- `package_hash`
- `artifact_hash_manifest`
- `worker_attestation`
- `locked_guide_version`
- `locked_guide_source_snapshot_id`
- `locked_guide_source_snapshot_hash`
- `locked_effective_project_submission_artifact_policy_id`
- `locked_effective_project_submission_artifact_policy_hash`
- `locked_pre_submit_checker_policy_id`
- `locked_pre_submit_checker_bundle_hash`
- `locked_post_submit_checker_policy_id`
- `locked_post_submit_checker_policy_version`
- `locked_post_submit_checker_policy_hash`
- `locked_post_submit_checker_policy_body`
- `locked_review_policy_version`
- `locked_revision_policy_version`
- `locked_payment_policy_version`
- `submitted_at`
- `locked_at`
- `supersedes_submission_id`

Submissions intentionally reference the task's locked guide and policy fields,
including guide-source snapshot provenance, effective project submission
artifact policy provenance, project pre-submit checker compiled bundle hash
provenance, and explicit post-submit checker policy provenance. The locked
post-submit checker policy body is internal runtime provenance, copied from the
task and hidden from Contributor-facing responses. This prevents task-owned locked
context from changing silently after a submission has been recorded.

`evidence_items`

- `id`
- `submission_id`
- `type`
- `label`
- `uri`
- `hash`
- `size_bytes`
- `locked_at`
- `metadata`
- `created_at`

## API Contract

POST `/api/v1/tasks/{task_id}/submission-precheck`

Runs non-authoritative pre-submit feedback against the task's locked project
`PreSubmitCheckerPolicy`. This endpoint does not create a submission row,
submission version, durable checker run, task transition, or submission-created
audit event.

Request body:

- `submission`
  - `summary`
  - `package_uri`
  - `package_hash`
  - `artifact_hash_manifest`
  - `worker_attestation`
  - `evidence_items`

Response body:

- `task_id`
- `authoritative` set to `false`
- `status` as `passed` or `failed`
- `eligible_to_submit`
- `results`

POST `/api/v1/tasks/{task_id}/submissions`

Runs pre-submit checks from the locked project pre-submit checker policy for the
assigned Contributor's draft packet. Creates and locks a new submission version
only when blocking pre-submit checks pass, then enqueues the automatic Celery
pre-review checker gate.

Request body:

- `summary`
- `package_uri`
- `package_hash`
- `artifact_hash_manifest`
- `worker_attestation`
- `evidence_items`

The request body must not accept guide source snapshot ids or hashes, effective project submission artifact policy ids or hashes, project pre-submit checker policy ids or bundle hashes, or guide/checker/review/revision/payment policy version fields. Those fields come from the task.

The request body must not accept checker names, checker severities, checker outcomes, submission version, evidence ids, or checker run ids. Workstream owns those values.

GET `/api/v1/tasks/{task_id}/submissions`

Lists submission versions for a task visible to the current actor.

GET `/api/v1/submissions/{submission_id}`

Returns one visible submission packet.

POST `/api/v1/submissions/{submission_id}/finalize`

Repairs or idempotently re-checks the automatic pre-review checker gate for an
already locked latest submission. Normal submission creation already makes the
packet immutable and binds durable checker runs to the locked
`PostSubmitCheckerPolicy` id, version, hash, and body. The finalize endpoint is
not the normal handoff from contributor work to evaluation.

Repair outcomes:

- no existing automatic gate run: enqueue the locked latest submission
- queued automatic gate run: redispatch the existing queued claim without
  creating another checker run
- running automatic gate run: return the existing run without creating another
  claim
- timed-out running automatic gate run: fence the stale claim and create a
  replacement automatic gate attempt for the same locked latest submission
- `pre_review_gate_enqueue_failed`: requeue the same locked submission after the
  queue/broker/eager-dispatch problem is corrected
- `pre_review_gate_execution_failed`: requeue after the task/checker setup
  defect that blocked automatic execution is corrected
- `unknown_checker`: requeue after the missing checker registration or setup
  defect is corrected
- `requester_provenance_mismatch`: terminal integrity failure; inspect the
  locked submission audit, checker-run failure details, and retained worker
  logs if available; do not requeue automatically
- non-repairable failed automatic gate claim: return HTTP 409 with an
  operator-visible repair-blocked message and no false success response

## Versioning Rules

- the first packet for a task is version `1`
- each later packet for that task creates version `2`, `3`, and so on
- Workstream assigns submission versions server-side
- client-provided submission versions are rejected
- a later packet sets `supersedes_submission_id` to the previous latest submission id
- `supersedes_submission_id` must point to the previous latest submission for the same task
- existing submission rows are never edited to replace artifacts
- artifact changes require a new submission version
- evidence rows belong to exactly one submission version
- finalized submission packets cannot be mutated in place
- concurrent version conflicts return a controlled conflict response instead of a server error

## Lifecycle Rules

- a Contributor can submit only when assigned to the task
- first submission requires task status `IN_PROGRESS`
- Workstream loads the locked effective project submission artifact policy hash before creating a submission
- Workstream loads the locked generated project pre-submit checker compiled bundle hash before creating a submission
- blocking pre-submit failures prevent submission creation
- when blocking pre-submit fails, no submission row is created, no submission version is assigned, no task transition to `SUBMITTED` occurs, and no submission-created audit event is written
- first submission moves the task to `SUBMITTED`
- later replacement submissions are allowed only after the task reaches `NEEDS_REVISION`
- submission packet content must satisfy the locked project pre-submit checker policy
- every submission creation writes a task audit event
- the audit event includes submission id, submission version, contributor id,
  package hash, and artifact hash manifest
- successful submission creation writes both `submission_created` and
  `submission_finalized` audit events in the same server-owned handoff
- only the latest submission version for a task can enter or repair the automatic
  pre-review checker gate
- queue or eager-dispatch failures after successful packet locking move the task
  to `EVALUATION_PENDING`, record `pre_review_gate_enqueue_failed`, and preserve
  requester provenance for repair
- Chunk 5 submission status is `submitted`; automatic locking sets internal
  `locked_at` and does not change status

## Security And Auth

- Workstream still verifies external Flow auth only
- no Workstream-owned login or primary auth session is added
- only the assigned Contributor can create a submission for the task
- admins can read submissions and can repair the automatic pre-review checker gate
  for operational recovery
- project managers can read submissions and repair the automatic pre-review
  checker gate only for tasks they created in v0.1; assigned submitters lock
  their own submitted packet through the normal submission flow
- Contributors can read their own task submissions
- response payloads are role-sensitive: operators can inspect server-stamped
  locked provenance for source snapshots and policy context, while
  Contributor-facing payloads hide internal policy ids, hashes, and bodies
- package and evidence URIs are stored as object references, not signed URLs or credentials
- persisted storage references are Workstream-issued opaque object references or validated object-storage adapter references
- raw signed URLs, credential-bearing URLs, query strings, local filesystem paths, bucket secrets, and token-bearing references are rejected before persistence
- normalization is allowed only for already-approved adapter references that contain no secrets, credentials, or query material

## Evidence Identity

Workstream generates evidence item ids at persistence time. Contributor-provided manifest rows may include artifact paths or URIs, but the persisted evidence item id is the stable Workstream evidence id for later checker and review records.

## Audit Scope

Chunk 5 writes task audit events with submission identifiers in `event_payload`. Direct submission audit streams are deferred until a dedicated submission-review surface needs them.

## Conditions Of Satisfaction

- Contributor submits a draft packet against `task_id` and Workstream assigns
  version `1` after blocking pre-submit checks pass
- Contributor does not provide locked guide source snapshot, effective project
  submission artifact policy, project pre-submit checker, or
  guide/checker/review/revision/payment policy context
- Contributor-provided locked guide source snapshot, effective project
  submission artifact policy, project pre-submit checker, or
  guide/checker/review/revision/payment policy context fields are rejected by
  the API schema
- Contributor-provided submission version fields are rejected by the API schema
- Contributor-provided checker names, checker outcomes, evidence ids, and
  checker run ids are rejected by the API schema
- preflight failures return `PreSubmitCheckResponse(status="failed", eligible_to_submit=false, results=[...])`
- blocked submission-create attempts return `DomainError(code="pre_submission_checker_failed")` with structured pass/fail/warning details and create no submission row, no submission version, no task transition to `SUBMITTED`, and no submission-created audit event
- Workstream stamps locked guide source snapshot ids/hashes, effective project submission artifact policy ids/hashes, project pre-submit checker policy ids/bundle hashes, and guide/checker/review/revision/payment policy versions from task context
- task moves to `SUBMITTED`
- submitted packet is automatically locked and enters the current post-submit checker gate
- dispatch failures after packet locking are visible as repairable automatic
  gate failures rather than failed contributor submissions
- replacing an artifact creates a new submission version instead of mutating v1
- submission audit events include task, contributor, version, package, and
  artifact context
- submission and immutability tests pass

## Verifier Agents

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- docs
- reuse/dedup
- test delta
