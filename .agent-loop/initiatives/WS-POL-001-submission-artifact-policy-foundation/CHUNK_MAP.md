# Chunk Map: WS-POL-001 - Submission Artifact Policy Foundation

## Rules

- One chunk fits in one reviewable PR.
- No chunk mixes policy modeling, pre-submit runtime rewiring, and post-submit
  checker splitting unless explicitly approved.
- Every implementation chunk must use Postgres-backed tests.
- Worker-facing outcomes remain simple; internal route names stay internal.
- Project guides are open-ended project material. Workstream uses async
  `ProjectGuideSufficiencyAgent` and
  `SubmissionArtifactPolicyDerivationAgent` outputs to create the locked policy
  bundle.
- Project owner material is untrusted input. Implementation chunks must reject
  unsafe source refs and prevent guide text or imported docs from granting tool
  authority or weakening Workstream defaults.
- Agents derive constrained project policy. Workstream's trusted compiler builds
  and validates checker specifications, then compiles deterministic checker
  bundles. Unrestricted generated checker code is not the default path.
- Reports, derived policies, acknowledgements, effective policies, task locked
  references, and checker bundles bind to immutable `GuideSourceSnapshot`
  bundle id/hash, not only to `guide_version`.

## Chunks

### WS-POL-001-01: Guide Policy Bundle Foundation

Goal:

Add first-class guide-source snapshot, guide sufficiency,
`SubmissionArtifactPolicy`, effective project policy, and activation guard
backend records and schemas. Define Workstream default submission artifact rules
and the deterministic project-policy merge contract. Do not move task runtime or
checker compiler behavior yet.

Risk:

L1

Depends on:

Approved intent, discovery, plan, and this chunk contract.

Allowed files:

```text
backend/alembic/versions/**
backend/app/db/models.py
backend/app/modules/projects/**
backend/tests/test_projects.py
backend/tests/test_tasks.py
backend/tests/test_checkers.py
backend/scripts/api_contract_e2e.py
docs/architecture_data_model.md
docs/decision_0011_submission_artifact_policy_drives_pre_submit.md
docs/operations_project_operating_manual.md
docs/spec_chunk_3_project_guide_foundation.md
docs/template_submission_artifact_policy.md
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

Not allowed:

```text
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/app/modules/submissions/**
.github/workflows/**
frontend or demos
payment/reputation/blockchain code
full async agent execution runtime
```

Acceptance criteria:

- Dedicated submission artifact policy model/table exists.
- Dedicated immutable guide source snapshot bundle model/table exists.
- Dedicated guide source snapshot item model/table exists, or the snapshot
  table stores an equivalent canonical manifest for every source item.
- `GuideSourceSnapshot.bundle_hash` is computed as
  `sha256(canonical_json(manifest_json))` with deterministic key ordering,
  source-item ordering, UTF-8 encoding, duplicate handling, and volatile-field
  exclusions. Non-finite numbers such as `NaN` or `Infinity` are rejected before
  hashing.
- Dedicated guide sufficiency report model/table exists.
- Guide sufficiency report supports `passed`, `blocked`, and
  `passed_with_warnings`.
- Project policy is scoped to project id + guide version.
- Guide sufficiency report, project policy, and effective project policy bind to
  `source_snapshot_id` and server-derived `source_snapshot_hash`.
- Project policy records are Workstream-derived and approved by `admin` or
  `project_manager`, not direct project owner-authored schema.
- Workstream default policy is represented in code.
- Deterministic merge rules are represented in code for union, intersection,
  logical OR, minimum limit, platform-locked hash algorithm, and restrictive
  packaging merges.
- Effective project policy merge rejects attempts to weaken defaults.
- Required artifacts or evidence that match forbidden rules block project setup.
- Effective project submission artifact policy hash is persisted for the guide version.
- Approved and superseded policy rows are immutable; changes create a new
  revision with a supersedes pointer.
- Guide activation requires passing or acknowledged guide sufficiency, approved
  submission artifact policy, and effective project submission artifact policy hash bound to the
  current guide source snapshot.
- Chunk 1 models and enforces the activation dependency on compiled project
  `PreSubmitCheckerPolicy` fields. Chunk 2 adds the trusted compiler path that
  writes those fields.
- Project-owner source refs persist as sanitized snapshot item refs and cannot store
  signed URLs, credential-bearing refs, token-bearing refs, or local filesystem
  paths. Approved adapters can use ordinary URL query parameters only as
  temporary fetch locators.
- Embedded instructions in guide material cannot grant tool authority or weaken
  Workstream default policy.
- Legacy guide-field artifact rules and task-level artifact/evidence shortcuts
  are not treated as compatibility contracts. Runtime removal happens in the
  task locked-context and submission migration chunk.

Verification:

- Postgres-backed FastAPI/API tests cover policy create/update, guide
  sufficiency activation blocking, warning acknowledgement, default weakening
  rejection, source snapshot binding, source-ref sanitization, append-only
  approved rows, and effective project submission artifact policy hash persistence.
- Unit/service tests may cover deterministic merge helpers, but API-visible
  behavior must be proven through the FastAPI path.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Guide sufficiency report fields, persisted provenance field names, and keeping
Chunk 1 limited to records/contracts/activation guards.

### WS-POL-001-02: Async Guide Analysis And Policy Derivation

Goal:

Run `ProjectGuideSufficiencyAgent`,
`SubmissionArtifactPolicyDerivationAgent`, and project pre-submit
checker compilation asynchronously against immutable guide-source snapshots.

Risk:

L1

Depends on:

`WS-POL-001-01`

Allowed files:

```text
backend/pyproject.toml
backend/app/main.py
backend/app/core/config.py
backend/app/core/hashing.py
backend/app/core/project_agents.py
backend/app/interfaces/project_agents.py
backend/app/adapters/project_agents/**
backend/app/modules/projects/**
backend/app/modules/checkers/**
backend/tests/test_projects.py
backend/tests/test_checkers.py
backend/tests/test_tasks.py
backend/scripts/api_contract_e2e.py
README.md
docs/architecture_checker_framework.md
docs/architecture_data_model.md
docs/architecture_lockdown.md
docs/decision_0011_submission_artifact_policy_drives_pre_submit.md
docs/glossary.md
docs/internal_reviews/2026-06-16_submission_artifact_policy_architecture.md
docs/operations_workspace_packet_convention.md
docs/spec_chunk_3_project_guide_foundation.md
docs/spec_chunk_7_checker_runner_registry.md
docs/spec_chunk_8_submission_artifact_policy_checkers.md
docs/template_checker_policy.md
docs/template_project_guide.md
docs/template_submission_artifact_policy.md
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

Not allowed:

```text
backend/app/adapters/auth/**
submission creation runtime rewiring
post-submit lifecycle changes
payment/reputation/blockchain code
```

Acceptance criteria:

- `ProjectGuideSufficiencyAgent` runs async and produces a persisted
  sufficiency report for a guide source snapshot.
- Blocking guide gaps stop activation and create project-owner clarification
  requests.
- Warnings can be acknowledged only by `admin` or `project_manager`.
- `SubmissionArtifactPolicyDerivationAgent` runs async after sufficiency passes
  or passes with warnings. Warning acknowledgement is required before policy
  approval and guide activation.
- Agent derivation requires a Workstream-agent sufficiency report for the same
  immutable snapshot; manual sufficiency reports can clear manual policy
  creation but do not create agent-derivation provenance.
- Persisted sufficiency-agent and derivation-agent names and versions are
  server-owned; runtime/provider identity fields cannot spoof audit records.
- Agent-derived policy provenance is revalidated before approval and guide
  activation.
- Derived policy cannot weaken Workstream defaults.
- Workstream's trusted checker compiler builds a constrained checker
  specification using only approved Workstream primitives.
- Trusted checker compiler validates that specification and persists a
  deterministic project `PreSubmitCheckerPolicy` bundle and hash. The default
  path compiles once per effective project submission artifact policy hash plus
  compiler version, not once per task.
- Guide activation requires the compiled project `PreSubmitCheckerPolicy` once
  Chunk 2 is complete.
- Compiler rejects any checker specification that omits an enforceable
  effective project policy rule, weakens severity, skips an evidence rule, or
  omits a Workstream default.
- Task runtime parameters come only from trusted task-contract fields and cannot
  override required checks, severity, allowed storage, forbidden artifacts, hash
  algorithm, or platform defaults.
- Derived report, project policy, effective project policy, and pre-submit checker bundle
  are invalidated by a new guide source snapshot.
- Malicious guide text, embedded prompt-injection instructions, and unsafe
  source refs cannot influence agent authority, fetch behavior, compiler
  behavior, server-side policy validation, or default policy strength.
- Workers and project owners cannot provide checker names, severities,
  versions, or outcomes.

Verification:

- Postgres-backed async tests cover sufficiency report creation, blocking
  clarification requests, warning acknowledgement, derivation route output,
  unsafe source-ref rejection, and default weakening rejection.
- Async API/service tests prove the routes are awaitable and idempotent for a
  guide source snapshot.
- Compiler tests prove allowed primitive emission, unknown primitive rejection,
  byte-stable same-input same-compiler-version bundle hashing, hash binding to
  `effective_project_submission_artifact_policy_hash`, and client/worker
  inability to supply checker names, severities, versions, outcomes, compiler
  version, or compiled bundles.
- Compiler semantic rejection tests prove omitted required artifact coverage,
  skipped evidence coverage, weakened severity, omitted Workstream defaults, and
  untraceable compiled bundle rules are rejected.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta, CI integrity.

Human review focus:

Async service boundaries, sufficiency severity behavior, and clarification
request shape.

### WS-POL-001-03: Task Locked Context And Submission Creation

Goal:

Lock each task to the applicable guide snapshot, effective project submission artifact policy hash,
and project pre-submit checker bundle. Move submission creation from
transitional task fields to that locked context.

Risk:

L1

Depends on:

`WS-POL-001-02`

Allowed files:

```text
backend/alembic/versions/**
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/tests/test_submissions.py
backend/tests/test_checkers.py
backend/scripts/week2_api_e2e.py
docs/spec_chunk_5_submission_packet_foundation.md
```

Not allowed:

```text
human review implementation
payment/reputation/blockchain code
frontend
```

Acceptance criteria:

- Tasks lock `locked_guide_source_snapshot_id`,
  `locked_guide_source_snapshot_hash`,
  `locked_effective_project_submission_artifact_policy_hash`,
  and `locked_pre_submit_checker_bundle_hash` during screening before `READY`.
- Every task under the same active project guide version shares that guide
  version's project `PreSubmitCheckerPolicy`; tasks do not run policy
  derivation or checker compilation.
- If a guide version does not cover the task set, activation is blocked and the
  guide is improved or the work is split into another project/guide.
- Task-specific values are constrained parameters consumed by the locked
  checker bundle, not a newly generated checker policy.
- Runtime parameters are sourced only from trusted task-contract fields; no
  free-form parameter map is introduced.
- Transitional `required_files` and `required_evidence` are replaced for
  submission runtime and are not compatibility aliases.
- Blocking pre-submit failure creates no submission row, submission version,
  submitted transition, or durable checker run.
- `POST /tasks/{id}/submission-precheck` returns `200 PreSubmitCheckResponse`
  with `status`, `eligible_to_submit`, and `results`.
- `POST /tasks/{id}/submissions` returns
  `422 DomainError(code="pre_submission_checker_failed")` with structured
  pass/fail/warning details when blocking pre-submit fails.
- Passing pre-submit creates a submission stamped with locked policy context.

Verification:

- Postgres-backed FastAPI/API tests cover clean submission, blocking pre-submit
  failure, no-row/no-version/no-transition/no-durable-checker side effects, and
  stamped locked policy context.
- Postgres-backed task tests cover locked context stamping, shared checker reuse
  for every task under the same active project guide version, blocked activation
  for uncovered task sets, and removal of transitional task-field authority.
- API/schema negative tests reject client-supplied free-form task runtime
  parameter maps and attempted runtime overrides of required checks, severity,
  allowed storage, forbidden artifacts, hash algorithm, or platform defaults.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Task locked context, shared checker reuse, no-row/no-version/no-transition
guarantee, and preflight-versus-submission-create failure shape.

### WS-POL-001-04: PostSubmitCheckerPolicy Split

Goal:

Separate post-submit checker policy naming/provenance from generated pre-submit
policy and transitional `locked_checker_policy_version`.

Risk:

L1

Depends on:

`WS-POL-001-03`

Allowed files:

```text
backend/alembic/versions/**
backend/app/modules/projects/**
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/tests/**
docs/spec_chunk_8_submission_artifact_policy_checkers.md
docs/spec_chunk_9_pre_review_gate.md
```

Not allowed:

```text
human review decisions
payment/reputation/blockchain code
frontend
```

Acceptance criteria:

- Pre-submit policy provenance and post-submit policy provenance are distinct.
- Durable checker runs use locked post-submit checker policy.
- Pre-submit feedback does not create durable checker records.
- Pre-submit feedback persistence cannot store review decision fields, or
  enforces review decision fields empty when a shared shape is unavoidable.
- API responses do not expose internal-only routes to workers.

Verification:

- Postgres-backed checker tests cover pre-submit feedback without durable
  `CheckerRun` and post-submit `CheckerRun` creation against locked
  `PostSubmitCheckerPolicy`.
- Postgres-backed schema/persistence tests prove pre-submit feedback cannot
  store review decision values.
- Postgres-backed FastAPI/API tests cover post-submit policy locking and
  worker-facing response filtering.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Field naming and migration safety.

Follow-up:

- A future frontend/demo chunk must prove any UI or demo surface that renders
  pre-submit results uses pass/fail/warning language instead of review decision
  terminology before ADR 0011 is marked fully implemented.
- A future executable-checker extension chunk, if ever approved, must prove
  static validation, generated tests, sandbox policy checks, no network, no
  shell, no secrets, no database access, and `admin` or `project_manager`
  approval of the exact locked code hash after those checks pass.

### WS-POL-001-05: Revision Resubmission And Real API Drill

Goal:

Prove a worker can receive `needs_revision`, run pre-submit feedback again, and
submit a new version using the same policy-driven path.

Risk:

L1

Depends on:

`WS-POL-001-04`

Allowed files:

```text
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/tests/**
backend/scripts/week2_api_e2e.py
examples/terminal_benchmark/**
docs/spec_chunk_9_pre_review_gate.md
```

Not allowed:

```text
human review decision implementation
payment/reputation/blockchain code
frontend
```

Acceptance criteria:

- Worker pre-submit feedback is allowed for `in_progress` and `needs_revision`
  where the worker owns the task.
- Replacement submission creates a new version.
- Older submission versions remain immutable.
- Internal checker-caused `needs_revision` remains distinguishable from future
  human-review-caused `needs_revision`.
- Real API drill covers clean pass, blocking pre-submit, post-submit
  `needs_revision`, and fixed resubmission.

Verification:

- Real API drill runs against Postgres and covers clean pass, blocking
  pre-submit failure, post-submit checker-caused `needs_revision`, fixed
  resubmission, immutable older submissions, and locked policy context.
- Postgres-backed tests prove replacement submission versioning and
  `outcome_source` separation.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Fair worker experience during revision and audit clarity.

### WS-POL-001-06: Terminal Benchmark Real Fixture Drill

Goal:

Use a real Terminal Benchmark reviewer fixture from the local Termius workspace
to prove the current Workstream setup-agent route, project policy bundle, task
locked context, pre-submit feedback, submission versioning, post-submit checker
gate, and fixed revision path over live manual HTTP calls and local Postgres.

Risk:

L1

Depends on:

`WS-POL-001-05`

Allowed files:

```text
examples/terminal_benchmark/**
backend/app/adapters/project_agents/openai_agent_sdk.py
backend/app/interfaces/project_agents.py
backend/app/modules/projects/models.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/app/modules/tasks/service.py
backend/alembic/versions/0010_remove_legacy_project_guide_fields.py
backend/tests/test_checkers.py
backend/tests/test_projects.py
backend/tests/test_tasks.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
README.md
docs/architecture_lockdown.md
docs/architecture_data_model.md
docs/architecture_system_architecture.md
docs/operations_project_operating_manual.md
docs/operations_operator_workflow.md
docs/operations_queue_policy.md
docs/operations_reviewer_workflow.md
docs/product_first_user_flows.md
docs/roadmap_implementation_backlog.md
docs/spec_chunk_3_project_guide_foundation.md
docs/spec_chunk_4_task_queue_assignment.md
docs/template_project_guide.md
docs/template_task.md
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

Not allowed:

```text
backend/app/** except listed adapter/interface/project/task files
backend/alembic/** except `backend/alembic/versions/0010_remove_legacy_project_guide_fields.py`
backend/tests/** except `backend/tests/test_projects.py`, `backend/tests/test_tasks.py`, `backend/tests/test_checkers.py`, and `backend/tests/test_alembic.py`
backend/scripts/** except `backend/scripts/api_contract_e2e.py`
.github/workflows/**
demos/**
frontend/**
payment/reputation/blockchain code
production secrets or committed .env files
Terminal Benchmark-specific product runtime code
```

Acceptance criteria:

- The Terminal Benchmark drill uses guide source snapshots, guide sufficiency
  reports, project `SubmissionArtifactPolicy`, effective project submission
  artifact policy, and compiled project `PreSubmitCheckerPolicy`.
- The guide sufficiency and submission artifact policy derivation endpoints run
  through the configured OpenAI Agents SDK adapter during the live manual API
  drill.
- The OpenAI Agents SDK adapter can return Workstream's open `policy_body`
  contract without weakening server-side `SubmissionArtifactPolicyInput`
  validation.
- The agent-derived policy row remains immutable; exact admin adjustments create
  a separate manual policy before approval.
- The drill uses `SubmissionArtifactPolicy` and the compiled project
  `PreSubmitCheckerPolicy` as the intake contract.
- The drill does not rely on task `required_files` or `required_evidence` as
  the source of pre-submit truth.
- The project submission artifact policy is Terminal Benchmark-shaped but
  project-scoped, compiled once, and reused by all tasks in the drill.
- Real fixture hashes feed artifact and evidence manifests without persisting
  absolute local paths.
- Pre-submit feedback creates no durable submission or checker rows.
- The clean path reaches `review_pending`, the checker-caused v1 path reaches
  `needs_revision`, and the fixed v2 path supersedes v1 and reaches
  `review_pending`.

Verification:

- Manual live API drill runs against local Postgres and one explicit Termius
  reviewer fixture path.
- Targeted adapter regression tests, stale wording scan, ruff, docstring
  coverage, markdown link check, and diff whitespace checks pass.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

The example remains proof harness code, uses current policy-bundle APIs, keeps
fixture paths and secrets local, and does not add Terminal Benchmark behavior to
Workstream runtime.

### WS-POL-001-07: Task Contract Artifact Field Cleanup

Goal:

Remove task-owned `required_files` and `required_evidence` from task creation,
task responses, and `workstream_tasks`. Submission artifact requirements are
project-policy authority through `SubmissionArtifactPolicy`,
`EffectiveProjectSubmissionArtifactPolicy`, and the project
`PreSubmitCheckerPolicy`.

Risk:

L1

Depends on:

`WS-POL-001-06`

Allowed files:

```text
backend/alembic/versions/**
backend/app/modules/tasks/**
backend/tests/test_tasks.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
backend/scripts/week2_api_e2e.py
docs/architecture_data_model.md
docs/operations_project_operating_manual.md
docs/operations_queue_policy.md
docs/product_first_user_flows.md
docs/spec_chunk_4_task_queue_assignment.md
docs/spec_chunk_8_submission_artifact_policy_checkers.md
docs/template_task.md
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

Not allowed:

```text
backend/app/modules/projects/**
backend/app/modules/checkers/**
backend/app/modules/submissions/**
examples/terminal_benchmark/**
demos/**
frontend/**
.github/workflows/**
human review implementation
payment/reputation/blockchain code
project-agent runtime redesign
new checker derivation or compilation per task
```

Acceptance criteria:

- `TaskCreate` no longer exposes `required_files` or `required_evidence`.
- `TaskResponse` no longer exposes `required_files` or `required_evidence`.
- `WorkstreamTask` no longer maps `required_files` or `required_evidence`.
- Alembic removes `workstream_tasks.required_files` and
  `workstream_tasks.required_evidence`.
- Task creation with either stale field returns 422.
- Pre-submit required artifact/evidence behavior remains driven by locked
  project policy and project `PreSubmitCheckerPolicy`.
- Real API helper scripts create tasks using the current task request body.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta, CI integrity.

Human review focus:

Task contract cleanup without weakening project-policy driven submission
intake.

### WS-POL-001-09: OpenAI Agents SDK Only Project Setup Runtime

Goal:

Remove the production `local_fixture` project setup runtime and the runtime
selector that made fixture-derived output look like real agent SDK output.
Automatic project guide sufficiency and submission artifact policy derivation
now run only through the OpenAI Agents SDK runtime behind Workstream's
project-agent port.

Risk:

L1

Depends on:

`WS-POL-001-08`

Allowed files:

```text
backend/app/core/config.py
backend/app/adapters/project_agents/**
backend/tests/test_projects.py
backend/tests/test_config.py
README.md
examples/terminal_benchmark/**
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/STATUS.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/CHUNK_MAP.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-09-openai-agent-sdk-only-project-setup.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-09-*
```

Not allowed:

```text
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/app/modules/projects/** except project-agent adapter imports if needed
backend/alembic/**
.github/workflows/**
demos/**
frontend/**
payment/reputation/blockchain code
object-storage implementation
new agent runtime provider implementation
production secrets or committed .env files
```

Acceptance criteria:

- Production project setup has no `local_fixture` runtime adapter.
- `WORKSTREAM_PROJECT_AGENT_RUNTIME_ADAPTER` is removed from active code and
  current operator docs.
- The project-agent runtime factory builds the OpenAI Agents SDK runtime and
  fails closed when the required model setting is missing.
- Setting the old runtime selector to `local_fixture` does not re-enable a
  fixture runtime.
- Tests use explicit test-local fakes for deterministic project-agent behavior.
- Terminal Benchmark example docs and script do not describe a removed runtime
  selector, fixture runtime, or fallback.
- README explains that automatic project setup needs OpenAI Agents SDK model and
  API-key settings.
- Local API contract drills do not enable setup autostart without the required
  OpenAI worker configuration.

Verification:

- Ruff, focused project-agent tests, docstring coverage, stale wording scan,
  Markdown link check, and diff whitespace checks pass.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

The removed fixture path cannot be used as a production project setup runtime;
test fakes stay visibly test-local; operator docs do not imply fallback
behavior; and the project-agent port remains available for deliberate future
runtime providers.

### WS-POL-001-10: Pre-Submit Live Drill Hardening

Goal:

Harden the concrete pre-submit setup and intake gaps found during the real
Terminal Benchmark API drill.

Risk:

L1

Depends on:

`WS-POL-001-09`

Status:

Merged through PR #72.

Scope:

Duplicate guide-version conflict mapping, guide-create source snapshot capture,
active-guide checker summary visibility, worker self-profile onboarding through
authenticated API, and durable failed-pre-submit audit evidence without creating
a submission.

Human review focus:

Worker profile setup is a real authenticated API path, active-guide checker
visibility does not expose compiled bundle bodies, and failed pre-submit
attempts remain outside product review decisions.

### WS-POL-001-11: Actor Identity And Profile Registry

Goal:

Create local `ActorIdentity` and shared `ActorProfile` registries for verified
Flow actors before the next Terminal Benchmark live API drill.

Risk:

L1

Depends on:

`WS-POL-001-10`

Allowed files:

```text
backend/alembic/versions/*_actor_identity_profile_registry.py
.github/workflows/backend.yml
backend/app/api/router.py
backend/app/api/deps/auth.py
backend/app/api/routes/auth.py
backend/app/core/config.py
backend/app/db/models.py
backend/app/modules/actors/__init__.py
backend/app/modules/actors/models.py
backend/app/modules/actors/repository.py
backend/app/modules/actors/schemas.py
backend/app/modules/actors/service.py
backend/app/modules/tasks/models.py
backend/app/modules/tasks/repository.py
backend/app/modules/tasks/router.py
backend/app/modules/tasks/schemas.py
backend/app/modules/tasks/service.py
backend/tests/test_actors.py
backend/tests/test_alembic.py
backend/tests/test_auth.py
backend/tests/test_tasks.py
backend/scripts/api_contract_e2e.py
backend/scripts/week2_api_e2e.py
examples/terminal_benchmark/terminal_benchmark_api_e2e.py
README.md
docs/architecture_data_model.md
docs/architecture_brief/workstream_architecture_brief.md
docs/architecture_lockdown.md
docs/architecture_system_architecture.md
docs/diagrams/workstream_v01_container.md
docs/glossary.md
docs/operations_roles_permissions.md
docs/roadmap_day_by_day_execution_plan.md
docs/roadmap_status.md
docs/spec_chunk_2_auth_actor_boundary.md
docs/spec_chunk_4_task_queue_assignment.md
scripts/check_internal_review_evidence.py
scripts/test_agent_gates.py
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/CHUNK_MAP.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/STATUS.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-11-actor-identity-profile-registry.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-11-*
```

Not allowed:

```text
Workstream-owned login, signup, password reset, password storage, primary auth sessions, or API-key auth
Flow token verifier replacement
route access from persisted profile rows instead of verified token roles
task/submission/checker/review/revision/payment/reputation behavior changes
agent runtime, project setup pipeline, Celery, storage, frontend, demo feature, or blockchain changes
```

Acceptance criteria:

- `ActorIdentity` and `ActorProfile` models/tables exist with unique identity
  and profile constraints.
- The separate worker/reviewer profile tables, ORM models, and repository
  authority paths stop owning profile state. This build-phase migration does
  not preserve obsolete experimental profile rows through a compatibility
  backfill.
- Migration tests prove the current schema exposes the shared profile authority
  and old worker/reviewer profile tables are absent.
- Flow token verification remains pure. Actor registration uses a separate
  actors service/repository boundary.
- Route authorization remains token-derived.
- Profile status values are explicit. `observed` is audit/display metadata,
  `active` is explicit workflow eligibility, and profile status is never route
  permission.
- Observation refresh preserves existing `active` and `disabled` profile
  status unless an explicit audited profile workflow changes status.
- Worker claim requires both verified worker token role and active worker
  profile.
- Stored profiles without matching token roles do not grant operator, worker,
  reviewer, or project-manager access.
- Stale backend script imports of old worker/reviewer profile models are
  removed or retired so the shared actor profile model is the only profile
  authority.
- Stale backend script/example calls to local demo profile endpoints are
  removed; current drills use `POST /api/v1/workers/me/profile`.
- Verification includes a stale helper scan for old profile model imports,
  removed Week 1 entry points, and removed demo worker-profile endpoints.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

The shared actor/profile model removes duplicated profile storage without
turning persisted profiles into auth or permission authority.

### WS-POL-001-12: Project Setup And Policy Visibility APIs

Goal:

Expose project setup and project policy state needed to continue a real setup
drill without database inspection. This chunk covers APIs 1-7 only.

Risk:

L1

Depends on:

`WS-POL-001-11` and the post-merge Terminal Benchmark live API drill findings.

Allowed files:

```text
backend/alembic/versions/**
backend/app/db/models.py
backend/app/modules/projects/**
backend/app/workers/project_setup.py
backend/tests/test_projects.py
backend/scripts/api_contract_e2e.py
docs/architecture_data_model.md
docs/architecture_system_architecture.md
docs/glossary.md
docs/operations_project_operating_manual.md
docs/roadmap_status.md
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

Not allowed:

```text
backend/app/modules/tasks/**
backend/app/modules/checkers/**
Workstream-owned login, signup, password reset, password storage, primary auth sessions, or API-key auth
Flow token verifier replacement
frontend/demo UI work
payment/reputation/blockchain settlement
agent prompt redesign or new project setup agent behavior
unrestricted generated checker code
review decision token changes
project owner-authored SubmissionArtifactPolicy schema
DB-only drill steps as accepted proof
```

API contract:

```text
1. GET /api/v1/projects/{project_id}/guides/{guide_id}/setup-runs/latest
2. GET /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports
3. GET /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}
4. GET /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies
5. GET /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}
6. GET /api/v1/projects/{project_id}/guides/{guide_id}/effective-submission-artifact-policy
7. GET /api/v1/projects/{project_id}/guides/{guide_id}/pre-submit-checker-policy
```

Authorization:

- All endpoints require verified token auth.
- All endpoints require project setup operator access: `admin` or
  `project_manager`.
- Worker, reviewer, finance, and auditor roles do not gain these project setup
  endpoints in v0.1.

Acceptance criteria:

- `ProjectSetupRun` persistence exists for automatic project setup jobs.
- `ProjectSetupRun` is a non-authoritative orchestration ledger. It references
  downstream truth by id/hash but does not replace sufficiency report, policy,
  effective policy, or pre-submit checker policy records.
- Creating a guide/source snapshot with automatic setup enabled creates a setup
  run before enqueue.
- Successful enqueue records the Celery task id. Enqueue failure records
  `enqueue_failed` with a bounded error summary.
- The project setup worker updates setup-run status and current step as it runs
  guide sufficiency and policy derivation.
- Setup-run statuses are explicit: `queued`, `enqueue_failed`,
  `running_sufficiency_agent`, `sufficiency_blocked`,
  `running_policy_derivation_agent`, `policy_draft_ready`, `setup_blocked`,
  and `failed`.
- `GET .../setup-runs/latest` returns the latest setup run scoped to the
  requested project and guide with source snapshot id/hash, Celery task id,
  status, current step, output ids, bounded error code/summary, and timestamps.
- Setup-run errors must not expose signed URLs, credential-bearing refs,
  token-bearing refs, local filesystem paths, private object keys, or raw stack
  traces.
- Sufficiency report list/get endpoints return only reports for the requested
  project and guide.
- Submission artifact policy list/get endpoints return only policies for the
  requested project and guide.
- Effective policy GET returns the current approved effective project
  submission artifact policy for the guide/source snapshot.
- Pre-submit checker policy GET returns the current compiled project
  `PreSubmitCheckerPolicy` summary for the guide/effective policy.
- The pre-submit checker policy response can include checker names, compiler
  version, compiled bundle hash, lifecycle status, source snapshot id/hash, and
  effective policy id/hash. It must not expose mutable authority beyond the
  persisted compiled bundle summary.

Verification:

- Postgres-backed project tests cover setup-run creation, enqueue task id,
  enqueue failure, worker status updates, latest setup-run reads,
  sufficiency report list/get, submission artifact policy list/get, effective
  policy GET, pre-submit checker policy GET, scoping, and unauthorized roles.
- `backend/scripts/api_contract_e2e.py` may be updated only to consume the new
  APIs through HTTP, not to add DB inspection as proof.
- Stale wording scan covers DB-inspection instructions in docs, scripts, and
  examples.
- Markdown link check passes for changed docs.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Setup-run status names, project setup operator access, redaction, and keeping
`ProjectSetupRun` as a ledger rather than a policy source of truth.

### WS-POL-001-13: Task Context And Submission Requirement APIs

Goal:

Expose worker-safe task context, exact submission requirements, and
operator-only locked provenance. This chunk covers APIs 8-10 only.

Risk:

L1

Depends on:

`WS-POL-001-12`

Allowed files:

```text
backend/app/modules/tasks/**
backend/app/modules/projects/schemas.py
backend/tests/test_tasks.py
backend/scripts/api_contract_e2e.py
docs/architecture_data_model.md
docs/architecture_system_architecture.md
docs/glossary.md
docs/operations_project_operating_manual.md
docs/roadmap_status.md
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

Not allowed:

```text
backend/alembic/versions/**
backend/app/modules/checkers/**
backend/app/workers/project_setup.py
Workstream-owned login, signup, password reset, password storage, primary auth sessions, or API-key auth
Flow token verifier replacement
frontend/demo UI work
payment/reputation/blockchain settlement
agent prompt redesign or new project setup agent behavior
review decision token changes
DB-only drill steps as accepted proof
```

API contract:

```text
8.  GET /api/v1/tasks/{task_id}/work-context
9.  GET /api/v1/tasks/{task_id}/submission-requirements
10. GET /api/v1/tasks/{task_id}/locked-context
```

Authorization:

- `work-context` and `submission-requirements` require existing task visibility
  for `admin`, `project_manager`, or the worker currently allowed to work the
  task.
- `locked-context` is operator-only for `admin` or `project_manager`.
- Persisted actor profiles do not grant route authorization. Token-derived role
  checks remain the route gate.

Acceptance criteria:

- `work-context` returns the task, project/guide summary, active locked guide
  content, review/revision/payment summary, and worker-facing lifecycle state.
- `submission-requirements` returns exact required artifacts, required evidence
  keys/labels/descriptions, forbidden artifact rules, allowed storage schemes,
  packaging rules, hash algorithm, storage reference rules, and required
  attestation concepts from the task's locked effective project policy.
- Worker-facing responses omit raw compiled checker bundles, checker configs,
  internal route tokens, private source refs, full source snapshot hashes,
  Celery task ids, and internal setup errors.
- `locked-context` returns full operator provenance: guide source snapshot
  id/hash, effective policy id/hash, pre-submit checker policy id/hash,
  post-submit checker policy id/hash/body summary, review policy version,
  revision policy version, and payment policy version.
- All task context APIs read already-stamped task locked context. They must not
  recompute policy from the current active guide or current project policy.
- If required locked context is missing or inconsistent, task context endpoints
  fail closed with a structured setup/locked-context error.
- Tests prove guide v2 activation does not silently change work-context or
  submission requirements for a task already locked to v1.

Verification:

- Postgres-backed task tests cover worker/operator visibility, redaction,
  missing locked context, stale active-guide drift, and unauthorized roles.
- API-contract script updates use only HTTP responses for task context proof.
- Stale wording scan covers `task binding`, task-owned policy, and DB-only
  proof wording in changed files.
- Markdown link check passes for changed docs.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Whether worker-facing requirements are complete enough for a real submitter
without exposing internal compiler authority.

### WS-POL-001-14: Submission Finalize And No-DB Drill Proof

Goal:

Replace the public submission `lock` route with `finalize`, clarify system
actor audit semantics, and prove the full 14-API Terminal Benchmark drill
through HTTP only.

Risk:

L1

Depends on:

`WS-POL-001-13`

Allowed files:

```text
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/tests/test_tasks.py
backend/tests/test_checkers.py
backend/scripts/api_contract_e2e.py
examples/terminal_benchmark/terminal_benchmark_api_e2e.py
docs/architecture_data_model.md
docs/architecture_system_architecture.md
docs/glossary.md
docs/operations_project_operating_manual.md
docs/roadmap_status.md
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

Not allowed:

```text
backend/alembic/versions/**
backend/app/modules/projects/**
backend/app/workers/project_setup.py
Workstream-owned login, signup, password reset, password storage, primary auth sessions, or API-key auth
Flow token verifier replacement
frontend/demo UI work
payment/reputation/blockchain settlement
agent prompt redesign or new project setup agent behavior
review decision token changes
DB-only drill steps as accepted proof
```

API contract:

```text
11. POST /api/v1/submissions/{submission_id}/finalize
12. GET  /api/v1/submissions/{submission_id}/checker-runs
13. GET  /api/v1/checker-runs/{checker_run_id}
14. GET  /api/v1/tasks/{task_id}/audit-events
```

The existing `POST /api/v1/tasks/{task_id}/submission-precheck` remains part of
the no-DB drill proof.

Authorization:

- `finalize` requires verified `admin` or `project_manager`.
- The requester must be authorized against the submission's project/task.
- The internal pre-review gate system actor cannot authorize HTTP requests and
  cannot be supplied by the client.
- Checker-run and audit reads retain their existing route permissions unless a
  test proves a visibility mismatch.

Acceptance criteria:

- Public `POST /submissions/{submission_id}/finalize` replaces public
  `POST /submissions/{submission_id}/lock` in code, tests, scripts, examples,
  and docs. No v0.1 compatibility alias is kept.
- `finalize` is idempotent for the latest submitted version and returns the
  existing finalized response on repeat calls.
- `finalize` fails for non-latest submission versions, unfinished submissions,
  unauthorized roles, and submissions whose task locked context is missing or
  inconsistent.
- Persistence may keep `locked_at` as the internal timestamp field.
- Public audit event wording uses `submission_finalized` for the requester
  handoff. Old public `submission_locked` wording is removed from current docs,
  scripts, and tests.
- Pre-review checker execution is audited under
  `workstream-system:pre-review-gate` and includes requester actor id, issuer,
  subject, and auth source in the event payload.
- Existing checker-run list/get endpoints remain stable and expose durable
  post-submit checker results for the finalized submission.
- Existing task audit-event endpoint remains stable and exposes the finalization
  and pre-review gate path.
- The Terminal Benchmark drill proceeds from guide creation through
  `review_pending` using HTTP API responses only. Direct DB reads are allowed
  only for test setup/cleanup and migration reset, not for proving lifecycle
  state or finding ids.
- The drill explicitly proves both paths: pre-submit preflight failure returns
  `200 PreSubmitCheckResponse` with `eligible_to_submit: false`, and blocked
  submission creation returns `pre_submission_checker_failed` without creating
  a submission.

Verification:

- Postgres-backed task/checker tests cover finalize success, idempotency,
  authorization, non-latest rejection, system actor audit, checker-run reads,
  and audit-event reads.
- `backend/scripts/api_contract_e2e.py` uses `/finalize`, not `/lock`.
- `examples/terminal_benchmark/terminal_benchmark_api_e2e.py` uses APIs 1-14
  plus pre-submit preflight and contains no DB inspection as proof.
- Stale wording scan covers `/submissions/.*/lock`, `submission_locked`,
  `lock endpoint`, and DB-inspection proof wording in backend, docs, scripts,
  examples, and `.agent-loop`.
- Markdown link check passes for changed docs.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Public `finalize` wording, operator-only authorization, system actor audit
provenance, and whether the live drill is genuinely API-only.
