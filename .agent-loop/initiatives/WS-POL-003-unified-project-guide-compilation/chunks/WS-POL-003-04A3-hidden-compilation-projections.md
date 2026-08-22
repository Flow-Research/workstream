# Chunk Contract: WS-POL-003-04A3 - Hidden Compilation-Derived Projections

## Status and authority

Status: executable against protected-main base
`a95a0b02d7c546b2440f6b8dd8215a4be07671ff`, where `WS-POL-003-04A` is
merged through PR #356. Risk: L1.

## Merge state

- Outcome on merge: `complete`

This chunk creates hidden PROJECTS behavior only. It activates no action and
changes no route, queue, provider call, or setup ledger.

## Goal

Project the immutable unified-compilation result into the two canonical product
objects needed by setup completion:

```text
project_guide_sufficiency(attempt_id)
project_submission_artifact_policy(attempt_id)
```

The methods are separate purpose-specific operations. There is no generic
component selector and no caller-supplied status, hash, output, action, actor,
or service identity.

## Closed behavior

| Compilation result | Sufficiency projection | Artifact-policy projection |
|---|---|---|
| `guide_blocked` | required | forbidden |
| `draft_ready` | required | required |
| `draft_ready_with_warnings` | required | required |
| `compilation_invalid_terminal` | forbidden | forbidden |
| `compilation_provider_uncertain` | forbidden | forbidden |

Each projection is deterministic from the exact validated component stored in
the compilation. It performs zero model calls. It preserves bounded safe text,
uses the existing canonical product model, and stores immutable provenance for
the exact project, guide/version, source snapshot/hash, setup run/generation,
attempt, compilation, result hash, component hash, schema, and derived object
ID/content digest.

The trusted transforms are closed:

- `guide_blocked` maps to a `blocked` report, `draft_ready` to `passed`, and
  `draft_ready_with_warnings` to `passed_with_warnings`. Finding severity,
  code, and message are preserved; the immutable compilation remains the
  source for evidence references and the rest of the complete result.
- The artifact proposal maps to the existing submission-policy body without
  invention: file/package limits are copied; `zip` becomes the sole package
  format; named required artifacts/evidence and forbidden artifacts become
  bounded deterministic rules; attestation terms are copied; manifest and
  SHA-256 checks remain required; and the platform-owned storage backends
  remain the existing `local`, `s3`, and `r2` values. The canonical body is
  validated by the existing policy schema and default compiler before write.
- A blocked compilation has no artifact proposal and the policy method denies
  before authorization or product writes.

Add one closed custody table,
`project_guide_component_projection_operations`, with component constrained to
`guide_sufficiency` or `submission_artifact_policy`. One exact operation exists
per setup generation and component. Update/delete/truncate and changed replay
fail closed. The existing business rows remain canonical; the operation row is
their provenance and replay receipt.

## Exact setup precondition

Both projection methods lock and require the latest active setup generation in
exact unified source state:

```text
status = queued
current_step = queued
celery_task_id = deterministic task ID for the attempt/setup generation
error_code = null
error_summary = null
every setup-row output ID = null
```

Legacy `running_*`, `dispatch_pending`, enqueue failure/mismatch, terminal,
error-bearing, wrong-task, stale-generation, or setup-output-bearing rows deny
before authorization consumption or projection creation. 04A3 never writes
setup-row output IDs. When the artifact-policy projection follows sufficiency,
it may observe only the exact first 04A3 custody row and its canonical report;
all setup-row output fields must remain null. Any foreign, changed, partial, or
unreceipted first component denies. POL-04A2 later binds the canonical output
IDs into the terminal setup transition.

A pre-existing legacy report or policy row without the exact immutable 04A3
operation is not reusable and denies. Component replay is valid only while the
setup remains in the exact source state and the own operation/decision/output
tuple is unchanged. A whole-task replay after setup finalization must return
through the finalization receipt before calling either projection method.

## Authorization and lock order

AUTH's dependency-free public API exposes two distinct semantic ports, one for
each existing action boundary. Each follows the same AUTH-first pattern:

```text
with authorization.prepare_sufficiency_projection(locator) as capability:
    capability.consume_new(final_facts) -> authority_receipt
    capability.validate_replay(final_facts, stored_decision_id) -> None

with authorization.prepare_artifact_policy_projection(locator) as capability:
    capability.consume_new(final_facts) -> authority_receipt
    capability.validate_replay(final_facts, stored_decision_id) -> None
```

A non-locking attempt lookup provides only the project locator. AUTH prepares
before PROJECTS locks product rows. PROJECTS then recomposes final facts and
chooses exactly one mutually exclusive terminal method. Capabilities are
nominal, process-local, single-use, non-serializable, and closed in `finally`.
Replay performs current service preflight and validates the stored decision
without PREP consumption or new evidence.

Production implementations remain deny-default until `WS-AUTH-001-12J`.
Following POL-03A, this chunk may add only the exact inactive audit/resource
vocabulary for compilation-derived sufficiency and artifact-policy projections.
Vocabulary does not activate an action, evaluator, or service membership.
Test adapters may stage vocabulary-valid decisions to prove atomic PostgreSQL
custody and may not borrow another resource type.

## Boundary and reuse

- Reuse the validated `ProjectGuideCompilationResult`, existing canonical
  report/policy models, and existing sanitizers.
- Do not call the legacy sufficiency or policy agents.
- Do not require legacy `running_*` setup states or mutate `ProjectSetupRun`.
- Do not approve the draft policy, compile effective policy, or project the
  post-submit component.
- Do not reuse the broad mutation services if they require caller-selected
  state or legacy step truth. Extract only pure canonical construction helpers
  proven reusable by tests.

## Allowed files

The complete implementation surface is:

```text
backend/app/modules/projects/api/__init__.py
backend/app/modules/projects/api/guide_compilation_projections.py
backend/app/modules/projects/guide_compilation/projections.py
backend/app/modules/projects/guide_compilation/models.py
backend/app/modules/projects/guide_compilation/repository.py
backend/app/modules/authorization/api/__init__.py
backend/app/modules/authorization/api/project_guide_projections.py
backend/app/modules/audit/schemas.py
backend/app/db/models.py
backend/alembic/versions/0009_guide_compilation_projections.py
backend/alembic/env.py
backend/tests/projects/guide_compilation/helpers.py
backend/tests/projects/guide_compilation/test_projection_contracts.py
backend/tests/projects/guide_compilation/test_projection_service.py
backend/tests/projects/guide_compilation/test_projection_postgresql.py
backend/tests/projects/guide_compilation/test_projection_migration.py
backend/tests/projects/guide_compilation/test_projection_call_graph.py
backend/tests/projects/guide_compilation/test_migration_contract.py
backend/tests/authorization/guide_compilation/test_migration_contract.py
backend/tests/architecture/test_authorization_boundary.py
backend/tests/test_alembic.py
backend/scripts/run_test_lanes.py
backend/tests/test_ci_test_lanes.py
backend/scripts/behavior_ownership.py
backend/tests/test_behavior_ownership.py
.ci/behavior-ownership/partition.v1.json
.ci/behavior-ownership/auth/project-guide-compilation-projection-ports.json
.ci/behavior-ownership/lifecycle/project-guide-compilation-projections.json
.github/workflows/backend.yml
docs/architecture_data_model.md
docs/operations_project_operating_manual.md
.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/**
.agent-loop/CURRENT_STATE.md
```

No directory wildcard is implicit except the initiative documents. Migration
`0009` is valid only while `0008_guide_compilation_authorized_persistence` is
the sole protected-main head. If any other runtime, schema, test, CI, ownership,
or documentation path becomes necessary, stop and amend/re-review this
contract before editing it.

## Not allowed

- Any provider/model call, route, task, queue, outbox, live composition, setup
  state/output mutation, approval, effective policy, checker policy, guide
  activation, or post-submit projection.
- Any AUTH evaluator, catalogue availability, fixed-service membership,
  permission, action, grant, private import, generic authorization method, or
  serializable prepared handle.
- Any generic component selector, generic operation framework, new canonical
  report/policy model, compatibility fallback, or legacy inference reuse.
- Any caller-supplied actor, service, action, project, guide, setup state,
  output ID, content, hash, or policy truth. The public command contains only
  the immutable compilation attempt ID.
- Any transaction, row lock, ORM object, or authorization capability crossing
  external I/O. ART material is loaded as an immutable DTO before the
  AUTH-first product transaction and is revalidated against locked canonical
  rows before authority consumption.

## Acceptance and trustworthy tests

- Unit tests prove the closed outcome table, exact canonical transforms,
  sanitization, digest vectors, extra-field denial, and mutually exclusive
  component methods.
- Real PostgreSQL tests prove exact creation, immutable provenance, exact
  replay with zero new event, changed replay denial, two-request concurrency,
  cross-lineage denial, rollback after authorization/product flush, and
  migration upgrade/downgrade guards.
- Every disallowed setup status/step/error/output/task/generation shape denies
  with zero product/event rows. Cross-component tests prove only the exact
  first 04A3 receipt can precede the second projection and rollback removes
  partial effects.
- Negative-effect assertions prove zero model calls, setup writes, approval,
  post-submit output, or wrong component rows.
- Architecture tests prove route-unreachability, deny-default production,
  public-boundary direction, and no call to the three legacy inference methods.
- Seeded faults remove one source/generation/result/component/task/correlation
  guard, swap the two authorization ports, create output before validation,
  permit a legacy/error/output-bearing setup, accept a foreign first component,
  consume on replay, or restore a legacy-state dependency; each exact test
  must fail.
- Every materially changed production file has at least 90 percent branch
  coverage, repository coverage remains at least 78 percent, all seven
  semantic lanes reconcile with zero skips/retries, and exact-head nine-lens
  review plus hosted CI pass.

## Verification commands

```bash
cd backend
uv run ruff check \
  app/modules/audit/schemas.py app/modules/authorization/api \
  app/modules/projects/api app/modules/projects/guide_compilation \
  tests/projects/guide_compilation/test_projection_*.py \
  tests/authorization/guide_compilation/test_migration_contract.py \
  tests/architecture/test_authorization_boundary.py tests/test_alembic.py \
  tests/test_behavior_ownership.py tests/test_ci_test_lanes.py
uv run pytest -q \
  tests/projects/guide_compilation/test_projection_contracts.py \
  tests/projects/guide_compilation/test_projection_service.py \
  tests/projects/guide_compilation/test_projection_postgresql.py \
  tests/projects/guide_compilation/test_projection_migration.py \
  tests/projects/guide_compilation/test_projection_call_graph.py \
  tests/projects/guide_compilation/test_migration_contract.py \
  tests/authorization/guide_compilation/test_migration_contract.py \
  tests/architecture/test_authorization_boundary.py tests/test_alembic.py \
  tests/test_behavior_ownership.py tests/test_ci_test_lanes.py \
  --cov=app --cov-branch --cov-report=
for source in \
  app/modules/audit/schemas.py \
  app/modules/authorization/api/__init__.py \
  app/modules/authorization/api/project_guide_projections.py \
  app/modules/projects/api/__init__.py \
  app/modules/projects/api/guide_compilation_projections.py \
  app/modules/projects/guide_compilation/models.py \
  app/modules/projects/guide_compilation/repository.py \
  app/modules/projects/guide_compilation/projections.py
do
  uv run coverage report --include="${source}" --precision=2 --fail-under=90
done
uv run python -m scripts.authorization_boundary validate \
  --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md
uv run python -m scripts.behavior_ownership validate
cd ..
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_chunk_state_sync.py \
  --base-ref a95a0b02d7c546b2440f6b8dd8215a4be07671ff
git diff --check a95a0b02d7c546b2440f6b8dd8215a4be07671ff
```

The final implementation runs all seven canonical semantic lanes against the
repository's pinned PostgreSQL, Redis, and MinIO services and independently
reconciles exact node custody. Hosted CI must enforce the same exact per-file
90 percent floors; aggregate coverage cannot hide a weak changed file.

## Required reviews

Preimplementation and exact-final-head review require nine tracks:

1. architecture and module ownership;
2. simplicity, reuse, and deduplication;
3. security and authorization;
4. QA and lifecycle correctness;
5. test-delta and false-green resistance;
6. senior engineering feasibility;
7. CI and evidence integrity;
8. product and operations truth; and
9. documentation and state consistency.

## Stop conditions

Stop and re-plan if a projection requires a model call, generic selector,
caller-supplied truth, setup-row mutation, cross-component authority, legacy
step, AUTH-private import, held lock across external I/O, second canonical
business object, a source state broader than exact `queued/queued`, or
provenance that cannot be enforced from immutable rows.
