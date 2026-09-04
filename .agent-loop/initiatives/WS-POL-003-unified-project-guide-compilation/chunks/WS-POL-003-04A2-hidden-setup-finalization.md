# Chunk Contract: WS-POL-003-04A2 - Hidden Setup Finalization

Status: Planned after complete WS-POL-003-04A3; executable only after this
contract is merged. Risk: L1.

## Goal

Add the hidden, purpose-specific product boundary that atomically binds one
accepted unified compilation and its exact deterministic projections to the
current `ProjectSetupRun`. The boundary records immutable finalization custody
and moves the setup ledger to exactly one closed outcome. It remains unreachable
from HTTP and Celery until AUTH-12B2 and POL-04B merge.

## Required outcome

For one exact current setup generation:

```text
accepted ProjectGuideCompilation
-> exact guide-sufficiency projection operation
-> exact submission-artifact-policy projection operation when sufficiency passes
-> fresh setup-finalization authorization
-> immutable finalization receipt + one setup-ledger transition
```

| Compilation result | Required projections | Setup outcome |
|---|---|---|
| `guide_blocked` | Exact sufficiency report only; artifact-policy projection must not exist | `sufficiency_blocked` |
| `draft_ready` | Exact sufficiency report and exact artifact-policy draft | `policy_draft_ready` |
| `draft_ready_with_warnings` | Exact sufficiency report and exact artifact-policy draft | `policy_draft_ready` |

`current_step` remains diagnostic: it becomes `guide_sufficiency` for
`sufficiency_blocked` and `submission_artifact_policy_derivation` for
`policy_draft_ready`. It is not another lifecycle-status field.

Invalid, unsafe, provider-uncertain, stale, replaced, partial, mixed-generation,
or unprojectable results cannot finalize. Finalization is not Project Manager
approval, policy publication, guide activation, post-submit projection, or task
readiness.

## Exact allowed files

- `.agent-loop/CURRENT_STATE.md`
- `.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/CHUNK_MAP.md`
- `.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/STATUS.md`
- `.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/chunks/WS-POL-003-04A2-hidden-setup-finalization.md`
- `.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/reviews/WS-POL-003-04A2-*.md`
- `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-12B2-project-setup-service-cutover.md`
- `docs/architecture_data_model.md`
- `docs/roadmap_status.md`
- `docs/spec_authorization_service.md`
- `backend/alembic/env.py`
- `backend/alembic/versions/0010_project_guide_setup_finalization.py`
- `backend/app/db/models.py`
- `backend/app/modules/authorization/api/__init__.py`
- `backend/app/modules/authorization/api/project_setup_finalization.py`
- `backend/app/modules/projects/api/__init__.py`
- `backend/app/modules/projects/api/guide_compilation.py`
- `backend/app/modules/projects/guide_compilation/finalization.py`
- `backend/app/modules/projects/guide_compilation/finalization_payloads.py`
- `backend/app/modules/projects/guide_compilation/models.py`
- `backend/app/modules/projects/guide_compilation/repository.py`
- `backend/app/modules/projects/models.py`
- `backend/tests/architecture/test_authorization_boundary.py`
- `backend/tests/projects/guide_compilation/test_finalization_service.py`
- `backend/tests/projects/guide_compilation/test_finalization_postgresql.py`
- `backend/tests/test_alembic.py`
- `backend/tests/test_ci_test_lanes.py`
- `backend/TEST_STRUCTURE_DEBT.json`
- `scripts/behavior_ownership_catalogue.json`
- `scripts/ci_test_lane_manifest.json`

The debt ledger and CI/ownership manifests may change only if deterministic
repository checks require exact registration of new files. No threshold,
selection, or ownership weakening is allowed.

## Not allowed

- HTTP routes, Celery tasks, queue dispatch, or composition into a live setup path.
- Model/provider calls, another compilation, or another projection.
- Project Manager approval, policy publication, guide activation,
  ContributionPolicy behavior, task readiness, checker execution, artifact
  mutation, review, revision, compensation, or fulfillment.
- Raw `AuthorizationContext`, AUTH private imports, serialized/reconstructed
  prepared capabilities, or borrowed projection authority.
- Compatibility aliases, fallbacks, or writes through legacy inference services.

## Product-owned immutable custody

Add one `ProjectGuideSetupFinalization` row for one exact setup generation. Its
stable ID and operation ID are separate UUIDv5 values derived from
`setup_run_id`, `setup_generation`, and `compilation_id`. The row contains:

- `id`, `operation_id`, and `correlation_id`;
- project, guide/version, source snapshot ID/hash, setup run/generation, and
  Celery task ID;
- compilation attempt/request/provider identities, compilation ID, canonical
  input hash, result hash/schema, agent name/version, and component hashes;
- sufficiency operation ID, report ID, and output digest;
- nullable artifact-policy operation ID, policy ID, and output digest;
- result classification and closed setup outcome;
- finalization facts digest and authorization decision/resource digest;
- authorized actor profile, identity link, fixed service identity, action,
  permission, scope, and creation timestamp.

The artifact-policy triple is all-null only for `guide_blocked`; otherwise all
three values are required. Composite foreign keys bind the receipt to the exact
compilation, setup generation, and projection rows. There is exactly one receipt
per setup generation, compilation, operation, and authorization decision.

The receipt is append-only. PostgreSQL rejects update, delete, and truncate and
rejects any receipt whose classification, projection shape, output IDs, or
lineage disagree with the referenced immutable rows.

## Setup-row transition

The source setup row must still have the exact 04A3 projection source shape:

- latest setup generation and source snapshot for the locked draft guide;
- `status = queued`, `current_step = queued`, exact deterministic Celery task ID;
- no error, start, finish, post-submit summary, or setup output IDs;
- an internally consistent optional ART continuation pair; and
- no existing finalization receipt.

Finalization changes only:

- `output_sufficiency_report_id` to the exact receipt report;
- `output_submission_artifact_policy_id` to the receipt policy or `NULL`;
- `status` to the closed setup outcome and `current_step` to its exact
  diagnostic value defined above; and
- `finished_at` to PostgreSQL-owned transaction time.

Every other setup field remains unchanged. A transaction-deferred database
constraint guard requires the setup transition and matching receipt in the same
transaction in both directions. It permits the service's receipt-then-transition
statement order but rejects commit when either side is orphaned. It also rejects
partial output assignment, cross-resource output IDs, later mutation of a
finalized setup, and deletion/truncation of custody.

## Public authorization port

AUTH's dependency-free public API exposes exactly:

```text
with authorization.prepare_setup_finalization(locator) as capability:
    capability.consume_new(final_facts) -> authority_receipt
    capability.validate_replay(final_facts, stored_decision_id) -> None
```

The product service defaults to unavailable. AUTH-12B2 later provides the only
production adapter and activates only `project.setup_run.update` for fixed
service `workstream.project.setup` with permission `project.guide.manage`. This
chunk adds no catalogue row, evaluator, grant, service membership, or active
composition.

The locator contains only the non-locking project and operation locator needed
for AUTH preflight. PROJECTS then locks and recomposes every final fact. The
capability is nominal, process-local, non-serializable, single-use,
session-bound, root-transaction-bound, and closed exactly once in `finally`.

```text
root transaction
-> deterministic operation/facts identity
-> non-locking locator lookup
-> AUTH prepare
-> lock guide, latest snapshot, latest setup, compilation, and projections
-> validate exact source state and closed outcome
-> consume PREP with final facts
-> close PREP in finally
-> add immutable receipt
-> transition setup row
-> flush
-> caller-owned commit
```

Consume or close denial/exception occurs before product mutation. Any later
database failure rolls back the receipt, setup transition, and staged AUTH
evidence together.

## Canonical final facts

Domain `workstream.project_guide_setup_finalization.facts.v1` contains exactly:

```text
project_id, guide_id, guide_version, source_snapshot_id,
source_snapshot_hash, setup_run_id, setup_generation, celery_task_id,
source_state_digest, operation_id, correlation_id, finalization_id,
attempt_id, request_operation_id, provider_idempotency_key, compilation_id,
canonical_input_hash, result_hash, result_schema_version,
compilation_agent_name, compilation_agent_version, component_hashes,
result_classification, setup_outcome, sufficiency_operation_id,
sufficiency_report_id, sufficiency_output_digest,
artifact_policy_operation_id, artifact_policy_id,
artifact_policy_output_digest
```

Authority domain `workstream.project_guide_setup_finalization.authority.v1`
uses exact keys `action_id`, `permission_id`, `resource_type`, `resource_id`,
`scope_project_id`, `actor_profile_id`, `identity_link_id`, `service_identity`,
and `facts_digest`. Resource type is `project_guide_setup_finalization` and its
ID is the finalization ID.

Hashes are lowercase `sha256:<64 hex>` over canonical JSON with sorted keys,
compact separators, UTF-8, no non-finite values, explicit nulls, and no omitted
keys. Python/PostgreSQL vectors must match and one-field mutation must deny.

## Replay, concurrency, and recovery

Exact replay locks the immutable receipt, uses the receipt's stored
pre-finalization `source_state_digest` to reconstruct the original final facts,
and separately proves that the current setup row exactly matches the receipt's
post-finalization status, diagnostic step, output IDs, and `finished_at`
presence. It performs fresh current-service preflight, validates the stored
decision, and returns the same result without PREP consumption, new AUTH
evidence, or mutation. It must not recompute the pre-finalization source digest
from the already-mutated setup row. Replay after source-state transition is
recognized through the finalization operation before either 04A3 projection
method runs.

Concurrent identical calls produce one receipt and one setup effect; the loser
returns the same valid result. Same-operation different facts,
different-operation attempts on one generation, stale compilation/projection
lineage, replaced guide/snapshot/setup generation, and cross-resource requests
fail closed without another effect.

## Public result

`ProjectGuideSetupFinalizationReceipt` contains only `finalization_id`,
`operation_id`, `project_id`, `guide_id`, `setup_run_id`, `setup_generation`,
`result_classification`, `setup_outcome`, `sufficiency_report_id`, optional
`artifact_policy_id`, and `authorization_decision_event_id`. It exposes no
prepared object, raw result, provider response, credential, or ORM row.

## Acceptance-to-test matrix

| Criterion | Named proof | Boundary and custody |
|---|---|---|
| Deny-default | `test_unavailable_authorization_denies_before_product_lock` | Service; local + hosted |
| No live HTTP | `test_finalization_has_no_route` | Architecture AST/import proof; local + hosted |
| No queue composition | `test_finalization_has_no_queue_composition` | Architecture AST/import proof; local + hosted |
| Blocked output | `test_blocked_finalization_binds_only_sufficiency` | Service; local + hosted |
| Blocked forbids policy | `test_blocked_finalization_rejects_policy_projection` | Service; local + hosted |
| Ready requires policy | `test_ready_finalization_requires_exact_policy_projection` | Service; local + hosted |
| Warning classification | `test_ready_with_warnings_preserves_classification` | Service; local + hosted |
| Diagnostic blocked step | `test_blocked_finalization_sets_guide_sufficiency_step` | Service; local + hosted |
| Diagnostic ready step | `test_ready_finalization_sets_policy_derivation_step` | Service; local + hosted |
| PREP before mutation | `test_consume_observes_no_product_mutation` | Strict authorization fake; local + hosted |
| Consume denial | `test_consume_denial_has_no_product_effect` | Service; local + hosted |
| Consume exception | `test_consume_exception_has_no_product_effect` | Service; local + hosted |
| Wrong receipt | `test_wrong_authority_receipt_denies` | Service; local + hosted |
| Close once | `test_prepared_authority_closes_once_on_success` | Service; local + hosted |
| Close on failure | `test_prepared_authority_closes_once_on_consume_failure` | Service; local + hosted |
| Close failure ordering | `test_close_failure_precedes_product_mutation` | Service; local + hosted |
| Atomic rollback | `test_late_database_failure_rolls_back_finalization_setup_and_authorization` | Real PostgreSQL; hosted |
| Stable replay | `test_exact_replay_returns_stored_receipt_without_new_evidence` | Real PostgreSQL; hosted |
| Replay source facts | `test_replay_uses_stored_prefinalization_digest_and_validates_final_state` | Real PostgreSQL; hosted |
| Replay authorization | `test_replay_denies_when_current_service_authority_is_revoked` | Concrete AUTH adapter; hosted after AUTH-12B2 |
| Identical concurrency | `test_concurrent_identical_finalization_has_one_effect` | Independent PostgreSQL sessions; hosted |
| Fork prevention | `test_distinct_operations_cannot_finalize_one_setup_generation` | Independent PostgreSQL sessions; hosted |
| Canonical fact isolation | `test_each_finalization_fact_mutation_denies` | Parameterized one field per case; local + hosted |
| Stale snapshot | `test_stale_snapshot_denies_without_consumption` | Service; local + hosted |
| Stale setup generation | `test_stale_setup_generation_denies_without_consumption` | Service; local + hosted |
| Replaced compilation | `test_replaced_compilation_denies_without_consumption` | Service; local + hosted |
| Wrong projection order | `test_policy_projection_without_exact_sufficiency_predecessor_denies` | Service; local + hosted |
| Wrong output | `test_projection_output_identity_mismatch_denies` | Service; local + hosted |
| Wrong digest | `test_projection_output_digest_mismatch_denies` | Service; local + hosted |
| Cross-project | `test_cross_project_finalization_is_concealed` | Real rows/PostgreSQL; hosted |
| Cross-guide | `test_cross_guide_finalization_is_concealed` | Real rows/PostgreSQL; hosted |
| Missing receipt | `test_direct_setup_finalization_without_receipt_is_rejected` | Direct SQL/PostgreSQL; hosted |
| Partial transition | `test_direct_partial_setup_finalization_is_rejected` | Direct SQL/PostgreSQL; hosted |
| Null bypass | `test_nullable_finalization_custody_cannot_bypass_guards` | Direct SQL/PostgreSQL; hosted |
| Receipt without transition | `test_direct_finalization_receipt_without_setup_transition_is_rejected` | Deferred constraint/direct SQL/PostgreSQL; hosted |
| Compilation ownership | `test_receipt_compilation_attempt_setup_tuple_must_match` | Composite FK/direct SQL/PostgreSQL; hosted |
| Sufficiency ownership | `test_receipt_sufficiency_operation_report_tuple_must_match` | Constraint trigger/direct SQL/PostgreSQL; hosted |
| Policy ownership | `test_receipt_policy_operation_policy_tuple_must_match` | Constraint trigger/direct SQL/PostgreSQL; hosted |
| Blocked policy shape | `test_blocked_receipt_requires_all_null_policy_tuple` | Check constraint/direct SQL/PostgreSQL; hosted |
| Ready policy shape | `test_ready_receipt_requires_complete_policy_tuple` | Check constraint/direct SQL/PostgreSQL; hosted |
| Actor-link ownership | `test_receipt_actor_identity_link_must_belong_to_actor` | Composite FK/direct SQL/PostgreSQL; hosted |
| AUTH receipt integrity | `test_authority_receipt_fields_and_digest_must_match_finalization` | Concrete receipt/service plus database digest guard; hosted after AUTH-12B2 |
| Finalized rewrite | `test_finalized_setup_cannot_be_rewritten` | Direct SQL/PostgreSQL; hosted |
| Receipt update | `test_finalization_receipt_update_is_rejected` | Direct SQL/PostgreSQL; hosted |
| Receipt delete | `test_finalization_receipt_delete_is_rejected` | Direct SQL/PostgreSQL; hosted |
| Receipt truncate | `test_finalization_receipt_truncate_is_rejected` | Direct SQL/PostgreSQL; hosted |
| Digest parity | `test_finalization_digest_matches_postgresql` | Python/PostgreSQL vectors; hosted |
| Digest mutation | `test_each_finalization_digest_field_changes_hash` | Parameterized one field per case; local + hosted |
| No provider reachability | `test_finalization_cannot_import_or_call_provider` | Architecture AST/import proof; local + hosted |
| No legacy inference | `test_finalization_cannot_reach_legacy_inference` | Architecture AST/call proof; local + hosted |
| No approval/activation | `test_finalization_cannot_reach_approval_or_activation` | Architecture AST/import proof; local + hosted |
| No checker/task/REV/CON | `test_finalization_has_no_downstream_product_imports` | Architecture AST/import proof; local + hosted |
| Changed coverage | Dedicated finalization coverage command below | Branch coverage at least 90%; hosted |
| Global coverage | Complete hosted aggregate | Preserve repository floor separately; hosted |

Each test has one primary behavior. New test modules remain below 500 lines;
shared fixtures may carry setup but may not hide assertions.

## Verification commands

```bash
git diff --check
python3 scripts/check_chunk_state_sync.py --base-ref origin/main --head-ref HEAD
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
cd backend && .venv/bin/python -m scripts.behavior_ownership validate
cd backend && .venv/bin/ruff check app/modules/projects/guide_compilation app/modules/authorization/api tests/projects/guide_compilation tests/architecture/test_authorization_boundary.py
cd backend && .venv/bin/pytest tests/projects/guide_compilation/test_finalization_service.py tests/architecture/test_authorization_boundary.py
cd backend && .venv/bin/pytest tests/projects/guide_compilation/test_finalization_service.py --cov=app.modules.projects.guide_compilation.finalization --cov=app.modules.projects.guide_compilation.finalization_payloads --cov-branch --cov-report=term-missing --cov-fail-under=90
```

Hosted Actions owns PostgreSQL finalization tests, Alembic/schema parity,
independent-session races, rollback, all semantic lanes, full suite, and global
coverage. Do not run the multi-hour full suite locally.

## Required review

Before implementation, review this contract for architecture, security,
product/operations, QA, and senior-engineering correctness. During
implementation, run exact-head architecture, security, QA, test-delta,
senior-engineering, and reuse/dedup reviews. Add docs review when normative docs
change and CI-integrity review only for CI/test-infrastructure changes. Evaluate
external comments against this contract; do not apply them blindly.

## Merge state

- Planning-contract PR outcome: `planned`.
- Later implementation PR outcome: `complete`.
- Completion permits AUTH-12B2 planning; it does not start AUTH-12B2 or POL-04B.
