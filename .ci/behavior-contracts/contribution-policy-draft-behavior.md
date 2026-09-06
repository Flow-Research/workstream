# Chunk Contract: WS-ARCH-001-CP04A — Hidden ContributionPolicy Draft Behavior

## Goal

Expose the CONTRIBUTIONS-owned public policy capability and implement hidden,
route-unreachable read, create-draft, and complete update-draft behavior. Add
the shared durable mutation-operation/event foundation used by CP04A and CP04B.
Production authorization denies by default and all five policy actions remain
planned/unavailable.

## Preconditions, risk and outcome

- CP01B unavailable policy registration and CP03B adapter-binding activation
  are merged.
- Current main still contains the discovered structural policy graph and guards.
- Risk: L1.

## Merge state

- Outcome on merge: `complete`
- CP04B becomes the next bounded policy-behavior implementation.

## Allowed files

```text
backend/app/modules/contributions/api/**
backend/app/modules/contributions/{schemas.py,models.py,repository.py,service.py,policy_validation.py}
backend/app/modules/compensation/api/{__init__.py,instruments.py,policy_bindings.py} (canonical instrument type and locked binding facts only)
backend/app/modules/compensation/schemas.py (same-owner import of the canonical public instrument enum only)
backend/app/modules/compensation/policy_binding_service.py (owner implementation only)
backend/app/modules/projects/api/{__init__.py,contribution_policy.py} (policy-project eligibility contract only)
backend/app/modules/projects/contribution_policy.py (owner implementation only)
backend/app/adapters/contributions/__init__.py (same-owner composition only)
backend/app/adapters/compensation/__init__.py (COMPENSATION-owned public-port construction only)
backend/app/adapters/projects/__init__.py (PROJECTS-owned policy-project eligibility only)
backend/app/db/models.py (metadata parity only if required)
backend/alembic/versions/0006_contribution_policy_operations.py
backend/alembic/env.py (head parity only)
backend/tests/contributions/**
backend/tests/conftest.py (resettable lifecycle-event table and exact schema-fingerprint parity only)
backend/tests/{projects,authorization}/guide_compilation/test_migration_contract.py (current-head parity only)
backend/tests/architecture/** (exact boundary/API proof only)
backend/tests/test_alembic.py (head/schema parity only)
backend/tests/test_contributions.py (preserved DB regressions only; no new primary behavior container)
backend/tests/migrations/test_compensation_adapter_identity.py (schema-isolation custody for the `0005` predecessor only)
backend/tests/test_behavior_ownership.py (exact CP04A partition transition proof only)
backend/scripts/{behavior_ownership.py,module_boundaries.py,run_test_lanes.py} (exact parity only)
.github/workflows/backend.yml (exact CP04A changed-surface coverage gates only)
.ci/behavior-ownership/** (exact CP04A targets only)
.ci/module-boundaries/private-edge-debt.v1.json (remove touched contributions->compensation.schemas edge only)
.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json (generated parity; no new debt)
docs/{architecture_data_model.md,roadmap_status.md,spec_contribution_compensation.md}
.commitrail/INDEX.md
.commitrail/initiatives/WS-ARCH-001/OVERVIEW.md
.commitrail/initiatives/WS-CON-001/OVERVIEW.md
.ci/behavior-contracts/contribution-policy-draft-behavior.md
Git history for the exact reviewed change
```

Migration `0006_contribution_policy_operations` is the single successor to
current head `0005_compensation_adapter_identity`. Stop and amend this contract
if another migration lands first; do not create a branch or compatibility head.

## Not allowed

```text
AUTH catalogue/evaluator/grant/action activation changes
public routes or Celery jobs
publish or retire behavior
ProjectGuide, TASK, Submission, REV, ContributionRecord, CompensationAward, fulfillment, callback, delivery or reputation behavior
cross-module private imports, compatibility aliases, generic service locators or a second authorization protocol
commits inside repositories/services or serialized prepared handles
```

## Public contract and behavior

- Add immutable requests/results/views, stable concealed errors, and Protocol
  ports under `app.modules.contributions.api`; expose no ORM/session/repository.
- Move COMPENSATION's closed `CompensationInstrumentType` enum to the dedicated
  public module `app.modules.compensation.api.instruments` as the single
  canonical definition. The public package initializer re-exports it;
  COMPENSATION private schemas import the dedicated public module and
  CONTRIBUTIONS consumes it only through the public API.
  Do not duplicate or translate the enum. Expose a transaction-held lookup
  for exact active same-project adapter-binding facts through its public API
  and owner-side service; remove the exact private schemas import from
  CONTRIBUTIONS. COMPENSATION remains the only owner of adapter-binding and
  instrument lifecycle truth. `ProjectCompensationUnit` stays
  CONTRIBUTIONS-owned and is locked by the policy repository.
- Construct the COMPENSATION lookup through
  `app.adapters.compensation`; the adapter root may import the same-owner
  implementation and returns only the public port. CONTRIBUTIONS composition
  receives that port and never imports COMPENSATION implementation.
- Add and consume a PROJECTS-owned public transaction-held policy-project
  eligibility port. CONTRIBUTIONS decides when policy lifecycle requires that
  fence; PROJECTS only validates and retains its own eligibility state.
- Read requires exact project/policy/optional-version authorization and returns
  immutable server-owned graph facts.
- Create-draft holds a project policy fence. It creates version 1 on a new
  aggregate when none is reusable, otherwise the next version on the current
  non-retired aggregate. Reject more than one open draft per project.
- Update-draft locks the exact project/policy/version and replaces the entire
  graph: one `accepted_submission` and one `completed_review` rule; unpaid has
  zero definitions; compensated has one or two unique money/project-points
  definitions with canonical positive quantities. Project-points quantities
  use integer scale; values such as `1.0` are rejected before owner locks or
  authorization.
- Update locks its CONTRIBUTIONS-owned same-project active units and consumes
  the COMPENSATION public lookup for active adapter-binding identities as early
  validation; CP04B revalidates both under publication locks. It never imports
  COMPENSATION models, repository, service, or private schemas.
- Every mutation carries `operation_id` and `request_digest`, acquires a
  transaction advisory fence before product locks/AUTH, and persists one
  immutable recoverable event.
- Event types are exactly `draft_created`, `draft_updated`, `published`, and
  `retired`. Each event stores `event_id`, `operation_id`, `request_digest`,
  `event_type`, `actor_profile_id`, `project_id`, `policy_id`, `version_id`,
  `version_number`, nullable `prior_current_version_id`, nullable
  `prior_current_version_number`, `from_policy_status`, `to_policy_status`,
  `from_version_status`, `to_version_status`, and database-owned `occurred_at`.
  The immutable mutation result contains the same fields, so recovery never
  reconstructs success from mutable current state.
- Exact duplicate recovery returns the immutable original result only after
  current read authorization. Mismatch or failed authorization is concealed.
- The domain-facing authorization port is opaque and production deny-default;
  test fakes may prove hidden behavior without activating an action.

## Mandatory mutation order

```text
caller-owned root transaction -> request digest -> operation fence
-> recovery check -> owner and eligibility locks -> prepare -> consume
-> close exactly once in finally -> product mutation + immutable event
-> flush, never commit
```

Denial, conflict, close failure, database failure, and rollback produce no
partial graph, event, or allowed evidence. CP04A proves the opaque port is
closed exactly once and that a port rejection has no product effect; CP05/AUTH
owns genuine session, transaction, copy, and replay handle-binding proof.

## Acceptance criteria

The acceptance-to-test map below is the governing acceptance checklist. Every
row is independently required. No grouped summary criterion may substitute for
one row's named proof and execution custody.

## Verification

### Acceptance-to-test map

Every row is one material behavior atom and an independently required
acceptance criterion. A module-level pytest invocation is execution
convenience, not acceptance evidence for an unlisted behavior.

#### Public boundaries and read behavior

| Behavior atom | Owner and implementation surface | Required future proof | Execution custody |
|---|---|---|---|
| Public policy API exports immutable requests, results, views and ports | CONTRIBUTIONS; `app.modules.contributions.api` | `tests/architecture/test_module_boundaries.py::test_policy_public_api_exports_immutable_contracts` | focused local command and hosted CI; architecture reviewer owns verdict |
| Public policy API exports no ORM, session or repository values | CONTRIBUTIONS; `app.modules.contributions.api` | `tests/architecture/test_module_boundaries.py::test_policy_public_api_exports_no_private_persistence_values` | focused local command and hosted CI; architecture reviewer owns verdict |
| CONTRIBUTIONS has no private COMPENSATION import | CONTRIBUTIONS/COMPENSATION; public APIs plus adapter roots | `tests/architecture/test_module_boundaries.py::test_cp04a_public_policy_api_has_no_private_cross_module_edge` | focused local command and hosted CI; architecture reviewer owns verdict |
| One canonical public instrument enum lives in `compensation.api.instruments` without duplication or translation | COMPENSATION public API and private schema parity | `tests/architecture/test_module_boundaries.py::test_policy_uses_public_compensation_instrument_enum_only` | focused local command and hosted CI; architecture reviewer owns verdict |
| COMPENSATION lookup retains its transaction fence through mutation | COMPENSATION public port, owner service and adapter root | `tests/contributions/test_policy_owner_ports.py::test_compensation_policy_binding_lookup_retains_transaction_fence` | focused local command and hosted PostgreSQL CI |
| COMPENSATION lookup returns only active binding facts | COMPENSATION public port and owner service | `tests/contributions/test_policy_owner_ports.py::test_compensation_policy_binding_lookup_rejects_inactive_binding` | focused local command and hosted CI |
| COMPENSATION lookup returns only same-project binding facts | COMPENSATION public port and owner service | `tests/contributions/test_policy_owner_ports.py::test_compensation_policy_binding_lookup_conceals_cross_project_binding` | focused local command and hosted CI |
| CONTRIBUTIONS has no private PROJECTS eligibility import | PROJECTS public port and adapter root | `tests/architecture/test_module_boundaries.py::test_cp04a_uses_only_public_projects_policy_eligibility_port` | focused local command and hosted CI; architecture reviewer owns verdict |
| PROJECTS eligibility port retains its transaction fence through mutation | PROJECTS owner implementation and CONTRIBUTIONS consumer | `tests/contributions/test_policy_owner_ports.py::test_projects_policy_eligibility_port_retains_transaction_fence` | focused local command and hosted PostgreSQL CI |
| Read denies without composed production authority | CONTRIBUTIONS deny-default authorization port | `tests/contributions/test_policy_read.py::test_read_denies_without_composed_authority` | focused local command and hosted CI |
| Read conceals a missing policy identity | CONTRIBUTIONS read service | `tests/contributions/test_policy_read.py::test_read_conceals_missing_policy` | focused local command and hosted CI |
| Read conceals a persisted cross-project policy identity through the real repository | CONTRIBUTIONS read service/repository | `tests/contributions/test_policy_integration_postgresql.py::test_real_repository_conceals_foreign_project_policy` | hosted PostgreSQL CI |
| Optional version selects only the exact requested version | CONTRIBUTIONS repository/service | `tests/contributions/test_policy_read.py::test_read_returns_requested_version_only` | focused local command and hosted CI |
| Read returns immutable server-owned graph facts | CONTRIBUTIONS public views | `tests/contributions/test_policy_read.py::test_read_view_contains_immutable_server_owned_graph_facts` | focused local command and hosted CI |
| Read returns no ORM rows | CONTRIBUTIONS public views | `tests/contributions/test_policy_read.py::test_read_view_contains_no_orm_rows` | focused local command and hosted CI |
| No ContributionPolicy route is registered | Delivery API registry | `tests/contributions/test_policy_routes_absent.py::test_policy_routes_are_not_registered` | focused local command and hosted CI |

#### Create- and update-draft behavior

| Behavior atom | Owner and implementation surface | Required future proof | Execution custody |
|---|---|---|---|
| Create denies without composed authority and stages no policy/event/evidence | CONTRIBUTIONS service and deny-default authorization port | `tests/contributions/test_policy_draft_create.py::test_create_draft_denies_without_composed_authority` | focused local command and hosted CI |
| Create retains the PROJECTS eligibility fence through mutation | PROJECTS public port and CONTRIBUTIONS service | `tests/contributions/test_policy_draft_create.py::test_create_draft_retains_project_policy_fence_through_mutation` | focused local command and hosted PostgreSQL CI |
| New policy aggregate starts at version 1 | CONTRIBUTIONS repository/service | `tests/contributions/test_policy_draft_create.py::test_create_draft_creates_version_one_for_new_policy` | focused local command and hosted CI |
| Current non-retired aggregate receives its next monotonic version | CONTRIBUTIONS repository/service | `tests/contributions/test_policy_draft_create.py::test_create_draft_creates_next_version_on_current_non_retired_policy` | focused local command and hosted CI |
| A retired aggregate is not reused | CONTRIBUTIONS repository/service | `tests/contributions/test_policy_draft_create.py::test_create_draft_does_not_reuse_retired_policy` | focused local command and hosted CI |
| A second open draft for one project is concealed and creates no effect/evidence | CONTRIBUTIONS repository/service | `tests/contributions/test_policy_draft_create.py::test_create_draft_rejects_second_open_draft_for_project_without_effect` | focused local command and hosted CI |
| Update denies without composed authority and stages no graph/event/evidence | CONTRIBUTIONS service and deny-default authorization port | `tests/contributions/test_policy_draft_update.py::test_update_draft_denies_without_composed_authority` | focused local command and hosted CI |
| Update locks and mutates only the exact project/policy/version draft | CONTRIBUTIONS repository/service | `tests/contributions/test_policy_draft_update.py::test_update_draft_locks_exact_project_policy_version` | focused local command and hosted PostgreSQL CI |
| Update replaces the complete rule-definition graph | CONTRIBUTIONS repository/service | `tests/contributions/test_policy_draft_update.py::test_update_draft_replaces_entire_rule_definition_graph` | focused local command and hosted CI |
| Complete graph replacement leaves no stale or orphan child | CONTRIBUTIONS repository/service | `tests/contributions/test_policy_draft_update.py::test_update_draft_leaves_no_stale_or_orphan_child` | focused local command and hosted CI |
| Graph contains exactly one accepted-submission rule | CONTRIBUTIONS policy graph | `tests/contributions/test_policy_draft_rules.py::test_update_requires_exactly_one_accepted_submission_rule` | focused local command and hosted CI |
| Graph contains exactly one completed-review rule | CONTRIBUTIONS policy graph | `tests/contributions/test_policy_draft_rules.py::test_update_requires_exactly_one_completed_review_rule` | focused local command and hosted CI |
| A missing completed-review rule is rejected | CONTRIBUTIONS policy graph | `tests/contributions/test_policy_draft_rules.py::test_update_requires_exactly_one_completed_review_rule` | focused local command and hosted CI |
| A duplicate required rule is rejected without effect | CONTRIBUTIONS policy graph | `tests/contributions/test_policy_draft_rules.py::test_update_rejects_duplicate_required_rule_without_effect` | focused local command and hosted CI |
| Unpaid rules contain zero instrument definitions | CONTRIBUTIONS policy graph | `tests/contributions/test_policy_draft_rules.py::test_update_rejects_instrument_definition_for_unpaid_rule` | focused local command and hosted CI |
| Compensated rules accept one or two unique money/project-points definitions | CONTRIBUTIONS policy graph | `tests/contributions/test_policy_draft_rules.py::test_update_accepts_one_or_two_unique_compensated_definitions` | focused local command and hosted CI |
| Compensated rules reject a duplicate instrument definition | CONTRIBUTIONS policy graph | `tests/contributions/test_policy_draft_rules.py::test_update_rejects_duplicate_instrument_definition` | focused local command and hosted CI |
| Non-positive instrument quantities are rejected | CONTRIBUTIONS policy graph | `tests/contributions/test_policy_draft_rules.py::test_update_rejects_non_positive_quantity` | focused local command and hosted CI |
| Non-canonical instrument quantities are rejected | CONTRIBUTIONS policy graph | `tests/contributions/test_policy_draft_rules.py::test_update_rejects_non_canonical_quantity` | focused local command and hosted CI |
| Overflow and over-scale quantities are rejected before owner locks or authorization | CONTRIBUTIONS canonical award quantity | `tests/contributions/test_policy_draft_rules.py::test_update_rejects_out_of_bounds_quantity_before_authorization` | focused local command and hosted CI |
| Project-points quantities require integer scale, including rejection of `1.0` | CONTRIBUTIONS policy graph | `tests/contributions/test_policy_draft_rules.py::test_update_rejects_non_integer_scale_project_points` | focused local command and hosted CI |
| Malformed rule objects produce the concealed domain conflict | CONTRIBUTIONS policy graph | `tests/contributions/test_policy_draft_rules.py::test_update_conceals_malformed_rule_input` | focused local command and hosted CI |
| Retired units are rejected without effect | CONTRIBUTIONS-owned units | `tests/contributions/test_policy_draft_resources.py::test_update_rejects_retired_unit_without_effect` | focused local command and hosted PostgreSQL CI |
| Cross-project units are concealed without effect | CONTRIBUTIONS-owned units | `tests/contributions/test_policy_draft_resources.py::test_update_conceals_cross_project_unit_without_effect` | focused local command and hosted PostgreSQL CI |
| Inactive adapter bindings are rejected without effect | COMPENSATION public held lookup | `tests/contributions/test_policy_draft_resources.py::test_update_rejects_inactive_adapter_binding_without_effect` | focused local command and hosted PostgreSQL CI |
| Cross-project adapter bindings are concealed without effect | COMPENSATION public held lookup | `tests/contributions/test_policy_draft_resources.py::test_update_conceals_cross_project_adapter_binding_without_effect` | focused local command and hosted PostgreSQL CI |
| Returned binding identity and instrument facts must exactly match the request | COMPENSATION public held lookup | `tests/contributions/test_policy_draft_resources.py::test_update_rejects_mismatched_adapter_binding_owner_facts` | focused local command and hosted CI |
| Create conceals a mismatched PROJECTS owner fact before AUTH | PROJECTS public held lookup | `tests/contributions/test_policy_draft_create.py::test_create_draft_conceals_project_owner_mismatch` | focused local command and hosted CI |
| Update rejects a missing required version selector before repository access | CONTRIBUTIONS request boundary | `tests/contributions/test_policy_draft_update.py::test_update_draft_rejects_missing_required_version_selector` | focused local command and hosted CI |
| Foreign policy substitution is concealed before AUTH or mutation | PROJECTS and CONTRIBUTIONS owner fences | `tests/contributions/test_policy_draft_resources.py::test_update_conceals_cross_project_policy_before_authorization` | focused local command and hosted PostgreSQL CI |
| Foreign version substitution is concealed before AUTH or mutation | PROJECTS and CONTRIBUTIONS owner fences | `tests/contributions/test_policy_draft_resources.py::test_update_conceals_cross_project_version_before_authorization` | focused local command and hosted PostgreSQL CI |
| A cross-project update request is concealed before AUTH or mutation | PROJECTS and CONTRIBUTIONS owner fences | `tests/contributions/test_policy_draft_resources.py::test_update_conceals_cross_project_request_before_authorization` | focused local command and hosted PostgreSQL CI |

#### Authorization, operation recovery and database custody

| Behavior atom | Owner and implementation surface | Required future proof | Execution custody |
|---|---|---|---|
| Operation fence precedes owner locks and AUTH | CONTRIBUTIONS service/repository | `tests/contributions/test_policy_authorization_atomicity.py::test_operation_fence_precedes_owner_locks_and_authorization` | focused local command and hosted PostgreSQL CI |
| Prepare denial creates no product/event/evidence | CONTRIBUTIONS authorization port | `tests/contributions/test_policy_authorization_atomicity.py::test_prepare_denial_creates_no_effect` | focused local command and hosted CI |
| Prepare exception creates no product/event/evidence or reusable authority | CONTRIBUTIONS authorization port | `tests/contributions/test_policy_authorization_atomicity.py::test_prepare_exception_creates_no_effect` | focused local command and hosted CI |
| Consume denial creates no product/event/evidence | CONTRIBUTIONS authorization port | `tests/contributions/test_policy_authorization_atomicity.py::test_consume_denial_creates_no_effect` | focused local command and hosted CI |
| Consume exception creates no product/event/evidence | CONTRIBUTIONS authorization port | `tests/contributions/test_policy_authorization_atomicity.py::test_consume_exception_creates_no_effect` | focused local command and hosted CI |
| Wrong actor returned from consume creates no effect | CONTRIBUTIONS authorization port | `tests/contributions/test_policy_authorization_atomicity.py::test_wrong_consumed_actor_creates_no_effect` | focused local command and hosted CI |
| Prepared object closes exactly once on success | CONTRIBUTIONS authorization port | `tests/contributions/test_policy_authorization_atomicity.py::test_prepared_authority_closes_once_on_success` | focused local command and hosted CI |
| Authorization-port rejection creates no product effect and closes the prepared object once | CONTRIBUTIONS authorization port | `tests/contributions/test_policy_authorization_atomicity.py::test_prepared_authority_closes_once_after_port_rejection` | focused local command and hosted CI |
| Close failure precedes product mutation and rolls back staged AUTH evidence | CONTRIBUTIONS authorization port | `tests/contributions/test_policy_authorization_atomicity.py::test_close_failure_rolls_back_staged_authorization_evidence_before_product_effect` | focused local command and hosted CI |
| Late post-close database failure rolls back policy, version, graph, event, and staged participant effects | CONTRIBUTIONS transaction | `tests/contributions/test_policy_integration_postgresql.py::test_late_database_failure_rolls_back_product_and_authorization_effects` | hosted PostgreSQL CI |
| Exact duplicate recovery requires current read authorization | CONTRIBUTIONS operation recovery | `tests/contributions/test_policy_operation_recovery.py::test_exact_duplicate_requires_current_read_authorization` | focused local command and hosted CI |
| Authorized exact duplicate returns the immutable original result | CONTRIBUTIONS operation recovery | `tests/contributions/test_policy_operation_recovery.py::test_exact_duplicate_returns_immutable_original_result` | focused local command and hosted CI |
| Digest mismatch is concealed | CONTRIBUTIONS operation recovery | `tests/contributions/test_policy_operation_recovery.py::test_digest_mismatch_is_concealed` | focused local command and hosted CI |
| Revoked current read cannot recover | CONTRIBUTIONS operation recovery | `tests/contributions/test_policy_operation_recovery.py::test_revoked_read_cannot_recover` | focused local command and hosted CI |
| Recovery creates no second mutation authorization | CONTRIBUTIONS operation recovery | `tests/contributions/test_policy_operation_recovery.py::test_recovery_creates_no_second_mutation_authorization` | focused local command and hosted CI |
| Recovery creates no second event | CONTRIBUTIONS operation recovery | `tests/contributions/test_policy_operation_recovery.py::test_recovery_creates_no_second_event` | focused local command and hosted CI |
| Recovery creates no second authorization evidence | CONTRIBUTIONS operation recovery | `tests/contributions/test_policy_operation_recovery.py::test_recovery_creates_no_second_authorization_evidence` | focused local command and hosted CI |
| Distinct create operations race to one open draft | CONTRIBUTIONS operation fence | `tests/contributions/test_policy_draft_concurrency.py::test_distinct_create_race_allows_one_open_draft` | hosted PostgreSQL lane only |
| Distinct create operations race to one AUTH consumption | CONTRIBUTIONS operation fence | `tests/contributions/test_policy_draft_concurrency.py::test_distinct_create_race_allows_one_authorization_consumption` | hosted PostgreSQL lane only |
| Event stores the exact immutable mutation-result shape | CONTRIBUTIONS event model/migration | `tests/contributions/test_policy_event_postgresql.py::test_event_matches_immutable_mutation_result` | hosted PostgreSQL lane only |
| Event actor attribution matches the authorized actor | CONTRIBUTIONS event model/migration | `tests/contributions/test_policy_event_postgresql.py::test_event_actor_matches_authorized_actor` | hosted PostgreSQL lane only |
| Invalid event transition shape is rejected | CONTRIBUTIONS migration guards | `tests/contributions/test_policy_event_postgresql.py::test_event_rejects_invalid_transition_shape` | hosted PostgreSQL lane only |
| Duplicate event operation identity is rejected | CONTRIBUTIONS migration guards | `tests/contributions/test_policy_event_postgresql.py::test_event_rejects_duplicate_operation_id` | hosted PostgreSQL lane only |
| Nullable prior policy state cannot bypass event validation | CONTRIBUTIONS migration guards | `tests/contributions/test_policy_event_postgresql.py::test_event_rejects_null_prior_policy_status` | hosted PostgreSQL lane only |
| Nullable mutation attribution cannot bypass event validation | CONTRIBUTIONS migration guards | `tests/contributions/test_policy_event_postgresql.py::test_event_rejects_null_mutation_actor_anchor` | hosted PostgreSQL lane only |
| Event schema contains composite policy and version ownership constraints | CONTRIBUTIONS event model/migration | `tests/contributions/test_policy_event_postgresql.py::test_event_schema_has_composite_ownership_constraints` | hosted PostgreSQL lane only |
| Cross-project policy/version event ownership is rejected | CONTRIBUTIONS migration guards | `tests/contributions/test_policy_event_postgresql.py::test_event_rejects_cross_project_policy_version_ownership` | hosted PostgreSQL lane only |
| Event update is rejected | CONTRIBUTIONS migration guards | `tests/contributions/test_policy_event_postgresql.py::test_event_update_is_rejected` | hosted PostgreSQL lane only |
| Event delete is rejected | CONTRIBUTIONS migration guards | `tests/contributions/test_policy_event_postgresql.py::test_event_delete_is_rejected` | hosted PostgreSQL lane only |
| Event truncate is rejected | CONTRIBUTIONS migration guards | `tests/contributions/test_policy_event_postgresql.py::test_event_truncate_is_rejected` | hosted PostgreSQL lane only |

#### Negative scope and structural custody

| Behavior atom | Owner and implementation surface | Required future proof | Execution custody |
|---|---|---|---|
| The hidden policy service exposes exactly create_draft, update_draft, read, publish and retire, with no direct downstream commands | CONTRIBUTIONS static public API shape only; not runtime side-effect proof | `tests/contributions/test_policy_negative_scope.py::test_cp04b_exposes_only_hidden_policy_commands` | focused local command and hosted CI |
| All five AUTH policy actions remain planned/unavailable | AUTH catalogue | `tests/authorization/test_contribution_policy_registration.py::test_cp01b_registers_only_exact_planned_policy_actions` | focused local command and hosted CI; security reviewer owns verdict |
| No production or test behavior container reaches 500 lines | CP04A production/tests | `tests/architecture/test_cp04a_file_structure.py::test_cp04a_changed_behavior_files_remain_below_500_lines` | focused local preflight and hosted CI |
| Every test has one primary behavior | CP04A tests and structural-debt ledger | `tests/architecture/test_cp04a_file_structure.py::test_cp04a_tests_map_one_to_one_to_contract_behavior_atoms` plus `scripts.test_structure_boundary validate` | focused local preflight and hosted CI; test-delta reviewer owns verdict |
| Each changed CP04A application surface remains at least 90% covered | CP04A focused test lane | one coverage collection followed by a separate `coverage report --include ... --fail-under=90` command for every changed application surface | local focused proof and hosted CI; CI-integrity reviewer owns verdict |
| Repository-wide coverage remains at or above the protected 78% baseline | Hosted aggregate test job and unchanged CI threshold | hosted repository aggregate coverage report | hosted CI only; CI-integrity reviewer owns verdict |

The focused pytest command must name every non-hosted-only module above. Hosted
CI must additionally run `test_policy_draft_concurrency.py` and
`test_policy_event_postgresql.py` against real PostgreSQL; SQLite or mocked-lock
substitution is not acceptance evidence.

```bash
cd backend && .venv/bin/ruff check app/modules/contributions app/modules/compensation/api app/modules/compensation/schemas.py app/modules/compensation/policy_binding_service.py app/modules/projects/api app/modules/projects/contribution_policy.py app/adapters/contributions app/adapters/compensation app/adapters/projects tests/contributions
cd backend && .venv/bin/python -m pytest -q tests/contributions/test_policy_read.py tests/contributions/test_policy_routes_absent.py tests/contributions/test_policy_owner_ports.py tests/contributions/test_policy_draft_create.py tests/contributions/test_policy_draft_update.py tests/contributions/test_policy_draft_rules.py tests/contributions/test_policy_draft_resources.py tests/contributions/test_policy_authorization_atomicity.py tests/contributions/test_policy_operation_recovery.py tests/contributions/test_policy_negative_scope.py tests/architecture/test_module_boundaries.py tests/architecture/test_cp04a_file_structure.py tests/authorization/test_contribution_policy_registration.py
cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-url> .venv/bin/python -m scripts.run_isolated_tests --metadata-json /tmp/cp04a-postgresql.json --timeout-seconds 1800 --lane cp04a_postgresql -- .venv/bin/python -m pytest -q tests/contributions/test_policy_integration_postgresql.py tests/contributions/test_policy_draft_concurrency.py tests/contributions/test_policy_event_postgresql.py tests/migrations/test_compensation_adapter_identity.py tests/test_alembic.py
cd backend && .venv/bin/python -m coverage erase && .venv/bin/python -m pytest -q tests/contributions tests/test_contributions.py tests/architecture/test_module_boundaries.py tests/architecture/test_cp04a_file_structure.py tests/authorization/test_contribution_policy_registration.py --cov=app.modules.contributions --cov=app.modules.compensation.api --cov=app.modules.compensation.schemas --cov=app.modules.compensation.policy_binding_service --cov=app.modules.projects.api --cov=app.modules.projects.contribution_policy --cov=app.adapters.contributions --cov=app.adapters.compensation --cov=app.adapters.projects --cov-report=
cd backend && .venv/bin/python -m coverage report --include='app/modules/contributions/api/*' --fail-under=90
cd backend && .venv/bin/python -m coverage report --include='app/modules/contributions/models.py' --fail-under=90
cd backend && .venv/bin/python -m coverage report --include='app/modules/contributions/schemas.py' --fail-under=90
cd backend && .venv/bin/python -m coverage report --include='app/modules/contributions/repository.py' --fail-under=90
cd backend && .venv/bin/python -m coverage report --include='app/modules/contributions/service.py' --fail-under=90
cd backend && .venv/bin/python -m coverage report --include='app/modules/contributions/policy_validation.py' --fail-under=90
cd backend && .venv/bin/python -m coverage report --include='app/modules/compensation/api/__init__.py,app/modules/compensation/api/instruments.py,app/modules/compensation/api/policy_bindings.py' --fail-under=90
cd backend && .venv/bin/python -m coverage report --include='app/modules/compensation/schemas.py' --fail-under=90
cd backend && .venv/bin/python -m coverage report --include='app/modules/compensation/policy_binding_service.py' --fail-under=90
cd backend && .venv/bin/python -m coverage report --include='app/modules/projects/api/__init__.py,app/modules/projects/api/contribution_policy.py' --fail-under=90
cd backend && .venv/bin/python -m coverage report --include='app/modules/projects/contribution_policy.py' --fail-under=90
cd backend && .venv/bin/python -m coverage report --include='app/adapters/contributions/__init__.py' --fail-under=90
cd backend && .venv/bin/python -m coverage report --include='app/adapters/compensation/__init__.py' --fail-under=90
cd backend && .venv/bin/python -m coverage report --include='app/adapters/projects/__init__.py' --fail-under=90
cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base <base-sha>
cd backend && .venv/bin/python -m scripts.test_structure_boundary validate --policy ../.ci/auth-boundaries/TEST_STRUCTURE_POLICY.md --ledger ../.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json
python3 scripts/check_commitrail_records.py --base-ref <base-sha>
python3 scripts/check_markdown_links.py
git diff --check
```

Hosted CI additionally runs `tests/contributions/test_policy_draft_concurrency.py`
and `tests/contributions/test_policy_event_postgresql.py` with real PostgreSQL.
The focused coverage collection plus separate per-surface reports independently
own the at-least-90-percent proof for every changed CP04A application surface.
Alembic and metadata-only parity are owned by the named schema tests rather than
Python line coverage. The hosted aggregate test job
independently owns the unchanged repository-wide 78-percent baseline and full
semantic-lane proof.

## Required reviewers

Architecture, security/auth, product/operations, QA, test-delta, CI integrity,
senior engineering, reuse/dedup, and documentation.

## Human review focus and stop conditions

Confirm aggregate ownership, complete replacement semantics, operation fencing,
PREP ordering, recovery, and absence of activation/routes. Stop and amend if
implementation needs another action, permission, route, foreign aggregate
write, or lifecycle state.
