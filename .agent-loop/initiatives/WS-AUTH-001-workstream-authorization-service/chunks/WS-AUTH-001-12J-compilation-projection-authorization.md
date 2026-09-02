# Chunk Contract: WS-AUTH-001-12J - Compilation Projection Authorization

Status: Planned. Risk: L1. This is the executable contract for one future
implementation pull request.

## Goal

Install AUTH's production implementations of the two purpose-specific public
authorization ports merged by `WS-POL-003-04A3`:

- `GuideSufficiencyProjectionAuthorizationPort`; and
- `ArtifactPolicyProjectionAuthorizationPort`.

The implementations authorize only `workstream.project.setup` to cross the
exact transaction-bound boundary that creates or replays one deterministic
compilation-derived guide-sufficiency report or submission-artifact-policy
draft. The product service remains hidden and deny-default until its AUTH
adapter is supplied by a later composition/cutover chunk.

## Existing authority reused without aliases

This chunk creates no action, permission, role, service identity, or second
authorization protocol. It reuses the already-active catalogue and static
service-matrix rows:

| Port | Action | Permission | Exact service |
|---|---|---|---|
| guide-sufficiency projection | `project.guide_sufficiency.run` | `project.guide.manage` | `workstream.project.setup` |
| artifact-policy projection | `project.submission_artifact_policy.derive` | `project.effective_policy.manage` | `workstream.project.setup` |

The first action remains historically owned by AUTH-12E and the second by
AUTH-12F3. AUTH-12J adds a new purpose-specific resource shape behind each
existing action; it does not relabel historical evidence, duplicate an action,
or treat the older mutation contexts as interchangeable with a projection
context. POL-04B later removes the obsolete live inference paths. Until that
cutover, each existing action accepts only a closed union of its exact legacy
context and its exact projection context, and a handle prepared for one context
cannot be consumed as the other.

## Ownership and module boundary

- PROJECTS/POL owns compilation attempts, persisted compilation results,
  Project Guides, source snapshots, setup runs, material custody, reports,
  policies, projection operations, deterministic identities, and all product
  locks and mutations.
- AUTH owns actor/link/service admission, action/permission/service-matrix
  evaluation, prepared capability custody, resource-context hashing, and
  authorization decision evidence.
- AUTH consumes only the dependency-free types exported from
  `app.modules.authorization.api.project_guide_projections`. It must not import
  a PROJECTS model, repository, service, schema, or private module.
- PROJECTS imports AUTH only through `app.modules.authorization.api`. It keeps
  the existing deny-default factories. AUTH-12J exports request-local concrete
  factory functions from the approved `app.adapters.auth` composition root; a
  later POL composition/cutover chunk wires those factories into the hidden
  product service. 12J adds no route, background executor, model call, product
  mutation, or live setup behavior.
- No prepared handle, actor context, credentials, product payload, or extracted
  content may enter a Celery message. A Celery task obtains fresh authority after
  loading its identifier-only job and opening the owning transaction.

## Exact prepared-authority protocol

Each port uses the existing `PreparedAuthorizationService` and opaque
`PreparedAuthorizationHandle`; it must not introduce a parallel PREP type or
an AUTH-local product evaluator.

Preparation receives only `ProjectGuideProjectionLocator(project_id,
attempt_id)`. Within the caller's transaction AUTH must:

1. authenticate the exact active `workstream.project.setup` ActorProfile and
   active service identity link;
2. confirm the exact action is active, maps to the exact permission above, and
   is present in that service's current static matrix row;
3. deterministically derive the component-specific operation, correlation, and
   output identities using the public API helper and the admitted actor/link;
4. prepare one opaque, process-local, non-serializable capability bound to the
   action, permission, component, locator, actor, link, service identity,
   current session, current root transaction, and prepared generation; and
5. close the underlying prepared handle exactly once from the context
   manager's `finally` path on success, denial, replay, exception, cancellation,
   or rollback.

The public `PreparedGuideSufficiencyProjection` and
`PreparedArtifactPolicyProjection` wrappers are purpose-specific views over
that existing handle. They are not dataclasses or Pydantic/JSON models, cannot
be copied or reconstructed, and expose only their immutable identity plus
`consume_new` and `validate_replay`.

### New projection consumption

After PROJECTS locks and revalidates the complete product lineage, AUTH accepts
the matching immutable fact object and:

1. recomputes the appropriate public facts digest;
2. recomputes the public component-specific authority digest;
3. requires exact equality with the prepared actor, link, service, action,
   component, project, attempt, deterministic identities, session,
   transaction, generation, and every fact field;
4. consumes the existing handle once; and
5. returns `ProjectGuideProjectionAuthorityReceipt` containing the committed
   decision-event identity, exact actor/link/service identity, and exact
   resource-context digest.

The allowed decision evidence is staged in the same caller-owned transaction
as the protected projection operation and output. Rollback removes both.
Consumption occurs before any report, source-usage, policy, or projection
operation is staged.

### Exact replay

For an already-existing exact projection operation, `validate_replay` performs
fresh service admission and validates all current locked facts plus the stored
decision-event ID. It creates no new allowed evidence and consumes no new
mutation authority. An exact authorized replay returns the immutable original
product result. A changed fact, stale identity, missing/mismatched stored
decision, revoked/inactive service profile or link, unavailable action, or
matrix mismatch denies without product mutation.

## Exact fact separation

Guide-sufficiency authority binds every field in
`GuideSufficiencyProjectionFacts`, including the complete compilation and
guide/setup lineage, source-state digest, material digest/size, deterministic
report ID, and report content digest.

Artifact-policy authority independently binds every field in
`ArtifactPolicyProjectionFacts`, including the same immutable parent lineage,
the exact prior sufficiency operation/report/digest, deterministic policy ID,
and policy content digest.

The two components have distinct resource types and canonical digest domains
already frozen in the public API. Swapping the service action, component,
facts type, resource type, output identity, or digest always denies. The policy
projection cannot borrow sufficiency authority merely because both use the
same fixed service.

## Fail-closed requirements

Preparation, new consumption, and replay deny on every mismatched, malformed,
inactive, revoked, unavailable, stale, copied, reconstructed, cross-session,
cross-transaction, cross-action, cross-component, cross-project,
cross-attempt, cross-guide, cross-snapshot, cross-setup-run/generation,
cross-compilation, cross-output, cross-prior-operation, or fact-mutated input.
They also deny after close or first consumption.

Every denial must occur without a report, source usage, policy, projection
operation, allowed decision event, model/provider call, setup-row transition,
or other product side effect. AUTH errors cross the public boundary only as the
existing concealed authorization exceptions.

## Allowed files for the implementation PR

```text
backend/app/modules/authorization/api/__init__.py
backend/app/modules/authorization/api/project_guide_projections.py
backend/app/modules/authorization/guide_compilation_projections.py
backend/app/modules/authorization/domain/guide_compilation_projections.py
backend/app/modules/authorization/domain/prepared_service.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/adapters/auth/__init__.py
backend/tests/architecture/test_authorization_boundary.py
backend/tests/authorization/guide_compilation_projections/**
backend/tests/authorization/test_service_actor_runtime.py
backend/tests/authorization/test_service_prepared_runtime.py
backend/tests/test_authorization.py
backend/tests/test_behavior_ownership.py
backend/tests/test_ci_test_lanes.py
backend/scripts/authorization_boundary.py
backend/scripts/run_test_lanes.py
.ci/behavior-ownership/auth/**
.ci/behavior-ownership/partition.v1.json
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/STATUS.md
.agent-loop/CURRENT_STATE.md
docs/roadmap_status.md
```

The public projection API is frozen except for a dependency-free correction
that an exact-head review proves necessary for AUTH/POL digest parity. Broad
test, ownership, lane, or structural-debt files may change only for the exact
new AUTH surface and its focused tests; no gate or threshold may weaken. No
migration is expected because both actions, permissions, service identities,
matrix rows, and evidence tokens already exist. If implementation discovery
proves a schema change necessary, stop and amend this contract before coding it.

## Not allowed

- A new action, permission, alias, service identity, service-matrix grant,
  migration, generic project-setup permission, human grant, or admin bypass.
- Changes to PROJECTS/POL models, repositories, product services, routes,
  background executors, Celery payloads, compilation/projection facts, locks,
  or mutations.
- Live composition, setup finalization, approval, guide activation, checker,
  submission, ART, TASK, REV, CON, payment, fulfillment, or reputation work.
- Re-running inference, reading raw guide material, storing product facts in
  AUTH, serializing a prepared handle, carrying authority across transactions,
  compatibility fallbacks, or a second authorization/evaluator path.
- Weakening the existing legacy 12E/12F3 checks while those paths remain
  reachable. Their removal belongs to POL-04B.

## Acceptance criteria and named proof

| Criterion | Required focused proof |
|---|---|
| Exact fixed service, action, permission, active profile/link, and matrix row are required independently for each port | `test_sufficiency_projection_requires_exact_project_setup_authority`; `test_artifact_policy_projection_requires_exact_project_setup_authority`; parametrized inactive/revoked/wrong-service/action/matrix tests |
| Deterministic identities and both public digest helpers match AUTH's resource contexts byte-for-byte | `test_projection_identity_matches_public_contract`; `test_projection_resource_digests_match_public_contract` |
| Preparation is bound to the current session, root transaction, actor/link, locator, action, component, and generation | `test_projection_prepare_binds_complete_authority`; parametrized wrong-session/transaction/actor/link/locator/action/component/generation tests |
| New consumption occurs once, before product staging, and returns the exact receipt | `test_projection_consume_returns_exact_receipt`; `test_projection_consume_callback_observes_no_product_rows` |
| Context exit closes exactly once for success, denial, replay, exception, cancellation, and rollback; closed/copies/reconstructed handles deny | `test_projection_prepared_close_matrix`; `test_projection_closed_copied_and_reconstructed_handles_deny` |
| Every fact field is bound and cross-component/action/resource swaps deny | generated one-field mutation tests for both fact dataclasses plus `test_projection_components_cannot_swap_authority` |
| Exact replay validates the stored decision freshly without new evidence or mutation authority | `test_projection_exact_replay_uses_original_decision`; inactive/revoked/action-unavailable/mismatched-decision replay tests |
| Denial and late product failure leave no allowed evidence or product effect | `test_projection_denial_has_no_product_or_allowed_evidence`; PostgreSQL `test_projection_late_failure_rolls_back_authority_and_product` |
| Concurrent same-operation calls produce one product effect and one allowed decision; the loser performs authorized exact replay | hosted PostgreSQL `test_projection_same_operation_concurrency_is_single_effect` for both components |
| Existing legacy contexts remain exact and cannot consume projection handles; no action/count/availability delta occurs | `test_projection_and_legacy_contexts_are_not_interchangeable`; catalogue/matrix/runtime parity tests |
| The approved AUTH composition root exports only request-local public-port factories; no consumer imports private AUTH | `test_projection_factories_are_exposed_only_by_auth_composition_root`; import-aware authorization-boundary proof |
| No private cross-module imports, live route, serialized handle, model/provider call, or changed Celery payload exists | import-aware architecture test, route scan, serialization rejection test, and behavior-ownership proof |

Every behavior test has one primary failure reason. New test modules remain
under 500 lines; split by preparation, consumption/replay, integrity, and
PostgreSQL atomicity rather than building a monolithic scenario file.

## Verification commands

```bash
git diff --check
python3 scripts/check_chunk_state_sync.py --base-ref origin/main --head-ref HEAD
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
cd backend && .venv/bin/ruff check app/modules/authorization tests/authorization/guide_compilation_projections tests/architecture/test_authorization_boundary.py
cd backend && .venv/bin/pytest tests/authorization/guide_compilation_projections tests/authorization/test_service_actor_runtime.py tests/authorization/test_service_prepared_runtime.py tests/architecture/test_authorization_boundary.py tests/test_authorization.py
cd backend && .venv/bin/pytest tests/authorization/guide_compilation_projections --cov=app.modules.authorization.guide_compilation_projections --cov=app.modules.authorization.domain.guide_compilation_projections --cov-branch --cov-report=term-missing --cov-fail-under=90
```

Hosted GitHub Actions owns the complete PostgreSQL concurrency/rollback matrix,
the repository-wide suite and preserved global coverage floor, behavior-lane
integrity, and aggregate exact-head evidence. Local development must not run
the multi-hour full suite.

## Required review

Before the implementation PR is ready, run exact-head security, architecture,
QA, test-delta, senior-engineering, and reuse/dedup reviews. Add docs review
when normative docs change and CI-integrity review only if lane, workflow,
coverage, ownership, or test-infrastructure files change. Evaluate external
review comments against this contract; do not apply them blindly.

## Outcome on merge

`WS-AUTH-001-12J` is `Complete`: AUTH supplies the two exact concrete
projection adapters, but the unified setup flow remains hidden. After both
12J and `WS-POL-003-04A2` are complete, `WS-AUTH-001-12B2` may activate only
the exact setup-finalization boundary. `WS-POL-003-04B` remains the sole owner
of the later live cutover and legacy inference-path removal.
