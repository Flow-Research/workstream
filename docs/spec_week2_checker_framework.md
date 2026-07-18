# Week 2 Checker Framework Specification

## Purpose

Week 2 adds the automated checker boundary between locked submissions and human review.

The checker framework protects reviewer time by proving that the latest locked submission is structurally valid, evidence-backed, policy-complete, and tied to the exact artifact hashes that were checked.

## Scope

- `CheckerRun` records
- `CheckerResult` records
- checker status and severity model
- pre-submit static checker path
- post-submit internal auto-check path
- checker registry and runner service
- project-required checker policy enforcement
- blocking versus warning calculation
- user-facing `needs_revision` routing from checker failures
- backend API access to checker runs and results
- backend API drill/debug output for checker visibility
- pre-review gate enforcement for `REVIEW_PENDING`

## Non-Scope

- product frontend implementation
- reviewer queue UI
- review decision form
- human review decision records/forms for `accept`, `needs_revision`, or `reject`
- revision replay enforcement
- contribution records
- payment records
- reputation updates
- external source adapters
- blockchain, x402, escrow, or settlement rails

## Core Invariant

```text
Draft packet -> project PreSubmitCheckerPolicy -> pre-submit checks -> submit -> automatic submission lock -> Celery pre-review CheckerRun -> CheckerResults -> routing recommendation
```

A task cannot reach `REVIEW_PENDING` unless the latest locked submission has a completed checker run for the exact submission version and artifact context.

`allow_review` can move the task toward `REVIEW_PENDING`. `needs_revision` is the worker-facing route for worker-fixable submission failures. `task_setup_blocked` is an internal checker routing recommendation for locked task setup defects owned by a project manager; it is not a task lifecycle state.

The checker binding includes:

- `task_id`
- `submission_id`
- `submission_version`
- `package_hash`
- `artifact_hash_manifest`
- locked project guide version
- locked post-submit checker policy version
- locked review policy version
- locked revision policy version
- locked payment policy version

## Two-Stage Checker Model

Workstream has two checker moments.

Pre-submit static checks run before Workstream creates a submission. They execute the task's locked project `PreSubmitCheckerPolicy`, which was generated from the effective project submission artifact policy during project setup, and give immediate feedback on packet shape and policy issues:

- required field presence
- package hash presence
- artifact hash manifest shape
- evidence references
- worker attestation
- storage reference safety
- task assignment and state compatibility

Blocking pre-submit failures prevent submission creation. Preflight failures
return `PreSubmitCheckResponse(status="failed", eligible_to_submit=false,
results=[...])`. Blocked submission-create attempts return
`DomainError(code="pre_submission_checker_failed")` with structured
pass/fail/warning details, create no submission row, no submission version, no
task transition to `submitted`, and no submission-created audit event.

Pre-submit failures do not create review decisions, do not return `accept`,
`needs_revision`, or `reject`, and do not create durable post-submit checker
runs.

Post-submit internal checks run after Workstream creates and locks a submission
packet that passed authoritative pre-submit validation. These checks are the
source of truth for review gating. They run
from Workstream-owned services, use locked task guide and policy context, and
persist durable checker runs/results.

## User-Facing Outcome Boundary

Users see the same simple outcome language everywhere:

- `accepted`
- `rejected`
- `needs_revision`

Automated checker failures may route the task to `needs_revision` when the
failure is worker-fixable. The submitted packet remains an immutable submitted
version. This is user-facing revision, not a human review decision.

Week 2 may set a checker-caused task outcome of `needs_revision`, but it does
not create a human review decision record.

Internally Workstream records the source:

- `outcome = needs_revision`
- `outcome_source = auto_checker`
- `checker_run_id = <run id>`
- `review_decision_id = null`

Human reviewer revision remains:

- `outcome = needs_revision`
- `outcome_source = human_review`
- `review_decision_id = <review decision id>`

Checkers can route to `needs_revision`, but they must not create fake human review decisions.

Checkers decide:

- passing required checks can allow `REVIEW_PENDING`
- warning checks can still allow `REVIEW_PENDING` with visible context
- worker-fixable blocking failures route to `needs_revision`
- platform/infrastructure failures stay in checker retry handling or audited admin intervention

Checker routing recommendations are not human review decisions. `allow_review` means "ready for human review", not `accept`. A checker must never write `accept` or `reject`.

Human review decisions remain only:

- `accept`
- `needs_revision`
- `reject`

Stored human review decision tokens are `accept`, `needs_revision`, and `reject`. User-facing task outcomes are displayed as Accepted, Rejected, and Needs revision. Internal lifecycle constants may use uppercase enum names, but persisted workflow values and API payloads should use canonical lowercase tokens.

Checker routing recommendation tokens are separate: `not_evaluated`, `allow_review`, `needs_revision`, `checker_retry`, and `task_setup_blocked`.

## Week 2 Visibility Boundary

Checker results are exposed through backend contracts and operational output:

- checker run API responses
- checker result API responses
- task/submission API expansion where needed
- backend API contract drills
- operational debug output when useful

Week 2 does not build the product frontend page for checker results. The planned React + Vite operations dashboard consumes these backend contracts later.

## Chunk Breakdown

### Chunk 6: Checker Contract And Records

Creates the durable checker run/result model, pre-submit response contract, API schemas, service boundaries, and migration.

Conditions of satisfaction:

- checker runs are tied to one submission version
- checker results are immutable after persistence
- status and severity values are canonical
- pre-submit feedback has a response contract but is not authoritative review-gate proof
- post-submit checker runs can record `allow_review`, `needs_revision`, `checker_retry`, or `task_setup_blocked` as routing recommendations
- `allow_review` is not stored as `accept`; it only means the submission can proceed to human review
- checker-caused `needs_revision` stores `outcome_source = auto_checker`
- checker output can be read through backend APIs

### Chunk 7: Checker Runner And Registry

Creates the checker interface, registry, pre-submit static checker path, runner service, and first structural checkers.

Detailed spec: [Chunk 7 Checker Runner And Registry](spec_chunk_7_checker_runner_registry.md).

Conditions of satisfaction:

- registered checker names cannot drift from policy names
- pre-submit checks return immediate feedback before final submission
- `check_submission_packet` runs against real submission data
- failed structural checks produce stored checker results
- worker-fixable submission failures and locked task setup failures are blocked before human review with distinct routing recommendations

### Chunk 8: Submission Artifact And Policy Checkers

Adds submission artifact, evidence, integrity, acceptance criteria, policy context, forbidden file, confidentiality, and generated-artifact checks.

Detailed spec: [Chunk 8 Submission Artifact And Policy Checkers](spec_chunk_8_submission_artifact_policy_checkers.md).

Conditions of satisfaction:

- missing evidence blocks `REVIEW_PENDING`
- malformed or missing artifact/evidence hash references block `REVIEW_PENDING`
- missing locked policy context blocks `REVIEW_PENDING`
- worker-visible messages do not leak sensitive internals

### Chunk 9: Pre-Review Gate

Automatically triggers internal post-submit checks after Workstream locks a submission and calculates whether a checked submission moves to `REVIEW_PENDING`, user-facing `needs_revision`, or an internal `task_setup_blocked` repair route.

Detailed spec: [Chunk 9 Pre-Review Gate](spec_chunk_9_pre_review_gate.md).

Conditions of satisfaction:

- the gate uses the latest locked submission only
- required checker list comes from locked post-submit checker policy
- blocking severities come from locked post-submit checker policy
- checker-caused revision does not create a human review decision
- no override endpoint exists in this chunk; any future override requires actor, reason, and audit event

### Chunk 10: Checker Trial

Runs real sample submissions through the checker framework.

Detailed spec: [Chunk 10 Checker Trial](spec_chunk_10_checker_trial.md).

Conditions of satisfaction:

- at least one clean submission reaches `REVIEW_PENDING`
- at least one worker-fixable submission failure is blocked
- locked task setup failures and worker-fixable submission failures use distinct routing recommendations
- trusted checker retry from internal blocked or retryable gate states is documented
- checker failures are documented in a failure catalog
- false-positive and missing-checker notes are recorded

## Verifier Agents

- senior engineering
- QA/test
- security/auth
- product/ops
