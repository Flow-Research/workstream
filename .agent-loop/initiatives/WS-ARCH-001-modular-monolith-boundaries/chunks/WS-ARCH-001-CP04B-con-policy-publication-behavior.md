# Chunk Contract: WS-ARCH-001-CP04B — Hidden ContributionPolicy Publication

## Goal

Implement hidden publish and retire behavior using CP04A's public API,
operation/recovery custody, and opaque authorization port. Keep all policy
actions unavailable and add no route or downstream product behavior.

## Preconditions, risk and outcome

- CP04A is merged and current-main discovery is replayed.
- Risk: L1.

## Merge state

- Outcome on merge: `complete`
- CP05 then becomes the next policy boundary.

## Allowed files

```text
backend/app/modules/contributions/api/**
backend/app/modules/contributions/{models.py,repository.py,service.py,policy_graph.py,policy_publication.py,policy_mutation_support.py}
backend/app/adapters/contributions/__init__.py
backend/alembic/versions/0007_contribution_policy_publication_custody.py
backend/alembic/env.py
backend/tests/contributions/**
backend/tests/architecture/** (exact boundary proof only)
backend/tests/authorization/test_contribution_policy_registration.py (negative activation parity only)
backend/tests/authorization/guide_compilation/test_migration_contract.py (head parity only)
backend/tests/projects/guide_compilation/test_migration_contract.py (head parity only)
backend/tests/conftest.py (database reset inventory only)
backend/tests/test_alembic.py (only with migration)
backend/scripts/{behavior_ownership.py,run_test_lanes.py} (exact parity only)
.ci/behavior-ownership/** (exact CP04B targets only)
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json (generated parity; no new debt)
docs/{architecture_data_model.md,roadmap_status.md,spec_contribution_compensation.md}
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/{CHUNK_MAP.md,STATUS.md,DISCOVERY.md}
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/{CHUNK_MAP.md,STATUS.md,AUTHORIZATION_HANDOFF.md}
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-CP04B-con-policy-publication-behavior.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP04B-*.md
```

## Not allowed

```text
AUTH activation/evaluator/grant/catalogue changes
public routes, ProjectGuide/TASK/Submission/REV mutations
ContributionRecord, CompensationAward creation, fulfillment, callback, delivery or reputation behavior
caller-supplied publication truth, compatibility paths, service commits or serialized PREP handles
```

The new modules have one owner each: `policy_graph.py` owns canonical graph
serialization and digest construction; `policy_mutation_support.py` owns shared
operation recovery and prepare/consume/close ordering; and
`policy_publication.py` owns publish/retire orchestration. `service.py` exposes
the existing public service boundary and delegates to these modules. No file
may reach 500 lines and no alternate service, repository, authorization, or
factory path may be introduced.

## Exact public API and AUTH parity

- Extend the closed `PolicyAction` with only `contribution.policy.publish` and
  `contribution.policy.retire`, and add exact typed publish and retire request
  types to the existing CONTRIBUTIONS public API.
- Publication mutation facts contain the existing common identities plus the
  server-owned `rules_and_definitions_digest`, sorted unique
  `adapter_binding_ids`, and exact expected draft status. Retirement mutation
  facts contain the exact current published version and expected published
  status. The CONTRIBUTIONS adapter constructs the existing AUTH public
  same values required by public AUTH `ContributionPolicyPublishFacts` or
  `ContributionPolicyRetireFacts`, without importing AUTH models,
  repositories, services, or private helpers. CP04B implements only
  CONTRIBUTIONS-owned domain facts and public-schema parity tests. CP05 alone
  installs the real CONTRIBUTIONS-to-AUTH adapter and prepared-handle behavior.
- `policy_graph.py` serializes the locked rules in ascending
  `(contribution_type, rule_id)` order and each rule's definitions in ascending
  `(instrument_type, unit_code, adapter_binding_id, definition_id)` order. It
  uses canonical UTF-8 JSON with sorted keys, `(',', ':')` separators, no
  caller-controlled whitespace, UUID strings, and canonical stored quantity
  strings. The digest is lowercase `sha256:` plus 64 hexadecimal characters.
  Binding ids are taken from those same locked definitions, deduplicated, and
  sorted by UUID string exactly as AUTH requires.
- Parity tests must compare the CONTRIBUTIONS-produced facts and digest to the
  public AUTH resource-digest contract. There is no second digest protocol and
  no translation of domain values.

## Total lock and authorization order

Every publish and retire mutation uses this order and holds every acquired
owner fence through flush:

1. caller-owned root transaction and canonical request digest;
2. transaction advisory `operation_id` fence and immutable recovery check;
3. PROJECTS public project-eligibility fence;
4. project-scoped publication advisory fence;
5. exact policy aggregate row;
6. exact target version row;
7. rules, then definitions, in the canonical order defined above;
8. referenced CONTRIBUTIONS-owned project units in ascending
   `(instrument_type, unit_code)` order;
9. referenced COMPENSATION-owned adapter bindings through its public owner
   port in ascending binding-id order;
10. construct server-owned facts, prepare AUTH, consume AUTH, and close exactly
    once in `finally`;
11. only after successful close, create the database transition anchor, mutate
    product rows, insert the lifecycle event, and flush.

Retire has no graph/unit/binding locks, but preserves the same relative order
for every applicable step. Reverse caller ordering may not change this order.
Duplicate recovery performs no mutation authorization or product write; exact
duplicates require a fresh authorized read and return immutable event facts.

## Publish contract

- Fence operation recovery before product locks or AUTH.
- Lock exact aggregate, draft version, both rules, definitions, referenced
  project units, and adapter bindings through the CP04A public owner ports;
  retain all owner fences through publication.
- Require a complete graph and active same-project units/bindings with exact
  instrument alignment.
- Recompute canonical rules/definitions digest and sorted unique binding ids
  from locked rows; require exact equality with typed AUTH facts.
- Consume and close PREP before changing version/policy state.
- Publish the version and make it current atomically. If another version is
  currently published, retire that prior version in the same transaction with
  exact actor/time attribution before installing the new current version.
  Prior content and every downstream frozen reference remain immutable.
- One `published` operation event represents that entire atomic replacement.
  Its nullable `prior_current_version_id` and
  `prior_current_version_number` identify the automatically retired version;
  the event's `actor_profile_id` and database-owned `occurred_at` are also the
  exact `retired_by` and `retired_at` attribution stored on that prior version;
  no second `retired` operation event is emitted. An explicit retire command
  emits one `retired` event. Recovery returns only these immutable event facts,
  never mutable aggregate state.
- Serialize same-project publication so the one-active-policy race has a
  deterministic winner before AUTH consumption.

## Migration and database custody

- Add revision `0007_contribution_policy_publication_custody`, with
  `down_revision = "0006_contribution_policy_operations"`; update
  `_CURRENT_HEAD_REVISION` and the existing Alembic head/schema tests.
- Add `contribution_policy_transition_custody` with exact columns
  `operation_id` (UUID primary key), `request_digest`, `event_type`,
  `actor_profile_id`, `project_id`, `contribution_policy_id`,
  `contribution_policy_version_id`, nullable
  `prior_current_version_id`, and `occurred_at` (database generated and not
  caller supplied). Composite foreign keys enforce policy/project,
  version/policy/project, and nullable prior-version/policy/project ownership;
  the event type is closed to `published` and `retired`.
- Add nullable `last_transition_operation_id` custody foreign keys to
  `contribution_policies` and `contribution_policy_versions`. Publication
  writes its unique operation id to the aggregate, target version, and any
  automatically retired prior version; explicit retirement writes it to the
  aggregate and retiring version. Draft create/update never writes this field.
- After successful PREP close, the service inserts custody with all immutable
  identities except time and reads back the database-generated `occurred_at`.
  It uses that exact value for the target publication/retirement fields, the
  automatic prior-version retirement fields, aggregate retirement fields when
  applicable, and the lifecycle event. Add nullable unique
  `publication_custody_operation_id` to lifecycle events: it must be null for
  `draft_created`/`draft_updated`, must equal `operation_id` for
  `published`/`retired`, and has the foreign key to custody. Thus draft events
  never require publication custody.
- Deferred constraint triggers run at transaction end in this order of proof:
  custody requires exactly one matching event; the event requires the matching
  final policy/version state and pre-mutation prior-current identity; every
  affected aggregate/version row must carry that unique custody operation id,
  actor, state, and time. A later custody/event inserted against already-final
  rows cannot match their earlier transition operation and must fail.
  Replacement
  publication additionally requires the prior version to be retired by the
  same actor at the same time. Explicit retirement requires both the aggregate
  and current version to be retired by the same actor at the same time.
  Orphaned, duplicated, stale, or mismatched custody/row/event combinations
  fail commit. Application credentials cannot update/delete/truncate custody
  or events. Database-superuser compromise is outside this application
  contract; the contract does not claim cryptographic proof against a trusted
  administrator forging an entire mutually consistent transaction.
- Custody and lifecycle events are immutable and reject update, delete, and
  truncate. Rollback removes custody, row changes, event, and staged AUTH
  evidence together.
- Correct the 0006 prior-current semantics for replacement publication: the
  `published` event records the locked pre-mutation current version, not the
  aggregate's post-mutation current version. Explicit retirement records the
  exact retiring current version.
- PostgreSQL guards make published rule/definition graphs immutable, require
  exactly one complete `accepted_submission` rule and one complete
  `completed_review` rule at publication, and enforce instrument/unit/binding
  ownership parity. Application validation is additional evidence, never the
  database authority.

## Retire contract

- Target only the aggregate's exact current published version.
- Lock and verify expected state before AUTH; consume/close PREP, then retire
  policy and version with exact actor/time attribution and one immutable event.
- Block future guide selection without rewriting any guide, task, assignment,
  Submission, ReviewLease, ContributionRecord, or award history.
- A retired aggregate is terminal. A later policy requires a new aggregate and
  normal draft/publish flow; no compatibility resurrection path exists.

## Acceptance criteria

- [ ] Publish/retire remain hidden and production deny-default.
- [ ] Publish facts equal digest/binding facts recomputed from locked rows.
- [ ] Concurrent child mutation, binding suspension, unit retirement,
  competing publication, opaque-port denial, close failure, and
  rollback fail closed without mutation. Genuine prepared-handle session,
  transaction, copy, and replay enforcement remains CP05/AUTH-owned.
- [ ] Replacement publication retires exactly the prior current version while
  preserving its content and frozen downstream references; aggregate retirement
  is terminal.
- [ ] Exact duplicate recovery requires current read authorization and creates
  no new evidence/effect.
- [ ] PostgreSQL rejects immutable graph mutation, lifecycle skips, forged
  attribution/events, event mutation/deletion/truncation, and incomplete publish.
- [ ] No new file reaches 500 lines; one primary behavior per test; no frozen
  debt growth; focused coverage remains at least 90%.
- [ ] CP05 alone becomes the next activation boundary.

## Verification

### Acceptance-to-test map

| Criterion | Required future proof | Execution custody |
|---|---|---|
| Publish/retire remain concealed, route-unreachable, and production deny-default | `tests/contributions/test_policy_publication_authorization.py::{test_publish_denies_without_composed_authority,test_retire_denies_without_composed_authority}` and `tests/contributions/test_policy_routes_absent.py::test_policy_routes_are_not_registered` | focused local command and hosted CI |
| Publish consumes exact server-recomputed graph digest and binding ids | `tests/contributions/test_policy_publish.py::{test_publish_uses_locked_server_owned_graph,test_caller_supplied_graph_mismatch_denies}` | focused local command and hosted CI |
| PREP denial occurs before lifecycle mutation | `tests/contributions/test_policy_publication_authorization.py::test_publish_prepare_denial_has_no_product_effect` | focused local command and hosted CI |
| PREP consume exception occurs before lifecycle mutation | `tests/contributions/test_policy_publication_authorization.py::test_publish_consume_exception_has_no_product_effect` | focused local command and hosted CI |
| PREP returns the wrong actor before lifecycle mutation | `tests/contributions/test_policy_publication_authorization.py::test_publish_wrong_consumed_actor_has_no_product_effect` | focused local command and hosted CI |
| PREP close failure occurs before lifecycle mutation | `tests/contributions/test_policy_publication_authorization.py::test_publish_close_failure_has_no_product_effect` | focused local command and hosted CI |
| PREP is closed exactly once on success and every failure | `tests/contributions/test_policy_publication_authorization.py::test_publish_closes_prepared_authority_exactly_once` and `test_retire_closes_prepared_authority_exactly_once` | focused local command and hosted CI |
| CONTRIBUTIONS never stages lifecycle state before consume/close | `tests/contributions/test_policy_publication_authorization.py::test_publish_consume_observes_no_staged_product_state` and `test_retire_consume_observes_no_staged_product_state` | focused local command and hosted PostgreSQL lane |
| Replacement publication atomically retires the prior current version with matching actor/time and emits one recoverable `published` event | `tests/contributions/test_policy_publish.py::{test_replacement_publication_is_one_atomic_event,test_replacement_preserves_prior_content_and_frozen_references}` | focused local command and hosted PostgreSQL lane |
| Exact duplicate publish returns immutable original event facts after current read authorization | `tests/contributions/test_policy_publication_recovery.py::test_duplicate_publish_returns_original_event_after_authorized_read` | focused local command and hosted CI |
| Exact duplicate retire returns immutable original event facts after current read authorization | `tests/contributions/test_policy_publication_recovery.py::test_duplicate_retire_returns_original_event_after_authorized_read` | focused local command and hosted CI |
| Duplicate request-digest mismatch is concealed | `tests/contributions/test_policy_publication_recovery.py::test_duplicate_digest_mismatch_is_concealed` | focused local command and hosted CI |
| Duplicate recovery read denial is concealed | `tests/contributions/test_policy_publication_recovery.py::test_duplicate_recovery_read_denial_is_concealed` | focused local command and hosted CI |
| Duplicate recovery creates no second product effect | `tests/contributions/test_policy_publication_recovery.py::test_duplicate_recovery_creates_no_second_product_effect` | focused local command and hosted PostgreSQL lane |
| Duplicate recovery performs no mutation authorization | `tests/contributions/test_policy_publication_recovery.py::test_duplicate_recovery_skips_mutation_authorization` | focused local command and hosted CI |
| Duplicate recovery creates no second authorization evidence | `tests/contributions/test_policy_publication_recovery.py::test_duplicate_recovery_creates_no_second_authorization_evidence` | hosted PostgreSQL lane only |
| Duplicate recovery creates no second lifecycle event | `tests/contributions/test_policy_publication_recovery.py::test_duplicate_recovery_creates_no_second_lifecycle_event` | focused local command and hosted PostgreSQL lane |
| Cross-project publish facts (policy, version, unit, or adapter binding) and retire targets (policy or exact current version) fail closed with concealed denial, no lifecycle mutation, and no staged AUTH evidence or other side effect | Focused service proof in `tests/contributions/test_policy_publication_authorization.py::{test_cross_project_policy_publish_is_concealed_without_effect,test_cross_project_version_publish_is_concealed_without_effect,test_cross_project_unit_publish_is_concealed_without_effect,test_cross_project_binding_publish_is_concealed_without_effect,test_cross_project_policy_retire_is_concealed_without_effect,test_cross_project_current_version_retire_is_concealed_without_effect}`; transaction/row-custody proof in `tests/contributions/test_policy_publication_cross_project_postgresql.py` using independently committed cross-project rows and direct assertions that lifecycle state/events and AUTH evidence remain absent | named focused tests run locally and in hosted CI; `test_policy_publication_cross_project_postgresql.py` runs in the hosted PostgreSQL lane only |
| Child mutation cannot cross the held graph fence | `tests/contributions/test_policy_publication_concurrency.py::test_child_mutation_waits_for_publication_graph_fence` | hosted PostgreSQL lane only |
| Binding suspension cannot cross its held owner fence | `tests/contributions/test_policy_publication_concurrency.py::test_binding_suspension_waits_for_publication_owner_fence` | hosted PostgreSQL lane only |
| Unit retirement cannot cross its held owner fence | `tests/contributions/test_policy_publication_concurrency.py::test_unit_retirement_waits_for_publication_owner_fence` | hosted PostgreSQL lane only |
| Competing same-project publications have one deterministic winner before AUTH | `tests/contributions/test_policy_publication_concurrency.py::test_competing_publications_serialize_before_authorization` | hosted PostgreSQL lane only |
| Reverse input ordering follows the canonical lock order without deadlock | `tests/contributions/test_policy_publication_concurrency.py::test_reverse_ordered_graphs_use_one_lock_order` | hosted PostgreSQL lane only |
| PostgreSQL rejects an incomplete publish graph | `tests/contributions/test_policy_lifecycle_postgresql.py::test_database_rejects_incomplete_publication_graph` | hosted PostgreSQL lane only |
| PostgreSQL rejects lifecycle skips | `tests/contributions/test_policy_lifecycle_postgresql.py::test_database_rejects_publication_lifecycle_skip` | hosted PostgreSQL lane only |
| PostgreSQL rejects mismatched or forged attribution custody | `tests/contributions/test_policy_lifecycle_postgresql.py::test_database_rejects_forged_publication_attribution` and `test_database_rejects_forged_retirement_attribution` | hosted PostgreSQL lane only |
| PostgreSQL rejects stale replacement prior-current identity | `tests/contributions/test_policy_lifecycle_postgresql.py::test_database_rejects_stale_replacement_identity` | hosted PostgreSQL lane only |
| PostgreSQL rejects a new custody/event pair against already-final rows when no matching row transition occurred | `tests/contributions/test_policy_lifecycle_postgresql.py::test_database_rejects_event_without_matching_row_transition` | hosted PostgreSQL lane only |
| PostgreSQL rejects graph mutation after publication | `tests/contributions/test_policy_lifecycle_postgresql.py::test_database_rejects_published_graph_mutation` | hosted PostgreSQL lane only |
| PostgreSQL rejects lifecycle custody/event update, deletion, and truncation | `tests/contributions/test_policy_lifecycle_postgresql.py::{test_database_rejects_lifecycle_update,test_database_rejects_lifecycle_delete,test_database_rejects_lifecycle_truncate}` | hosted PostgreSQL lane only |
| Explicit retirement is terminal and cannot rewrite frozen downstream lineage or resurrect the aggregate | `tests/contributions/test_policy_retire.py::{test_retire_blocks_future_selection_without_rewriting_history,test_retired_aggregate_cannot_be_resurrected}` | focused local command and hosted CI |
| Database failure after close rolls back lifecycle state and staged AUTH evidence | `tests/contributions/test_policy_publication_authorization.py::test_post_close_database_failure_rolls_back_all_effects` | hosted PostgreSQL lane only |
| A closed opaque authority cannot be reused by CONTRIBUTIONS | `tests/contributions/test_policy_publication_authorization.py::test_closed_publication_authority_cannot_be_reused` | focused local command and hosted CI |
| CONTRIBUTIONS publication facts have exact public AUTH digest parity | `tests/contributions/test_policy_publication_auth_parity.py::{test_publish_facts_match_public_auth_digest,test_retire_facts_match_public_auth_digest}` | focused local command and hosted CI |
| All ContributionPolicy actions remain planned and unavailable | `tests/authorization/test_contribution_policy_registration.py` | focused local command and hosted CI |
| CP04B files remain bounded and every test has one primary behavior | `tests/contributions/test_cp04b_file_structure.py` | focused local command and hosted CI |
| Every CP04B acceptance atom projects to an exact test name | `tests/contributions/test_cp04b_contract_projection.py` | focused local command and hosted CI |

The focused pytest command must name every non-hosted-only module above. Hosted
CI must additionally run `test_policy_publication_concurrency.py` and
`test_policy_publication_cross_project_postgresql.py` and
`test_policy_lifecycle_postgresql.py` against real PostgreSQL; mock locks or an
in-memory database do not satisfy the contract.

```bash
cd backend && .venv/bin/ruff check app/modules/contributions app/modules/compensation/api app/modules/compensation/policy_binding_service.py app/adapters/contributions tests/contributions
cd backend && .venv/bin/python -m pytest -q tests/contributions/test_policy_publication_authorization.py tests/contributions/test_policy_routes_absent.py tests/contributions/test_policy_publish.py tests/contributions/test_policy_publication_recovery.py tests/contributions/test_policy_retire.py tests/contributions/test_policy_publication_auth_parity.py tests/contributions/test_cp04b_file_structure.py tests/contributions/test_cp04b_contract_projection.py tests/authorization/test_contribution_policy_registration.py tests/authorization/guide_compilation/test_migration_contract.py tests/projects/guide_compilation/test_migration_contract.py tests/architecture/test_module_boundaries.py tests/test_alembic.py
cd backend && .venv/bin/python -m pytest -q tests/contributions --cov=app.modules.contributions --cov=app.adapters.contributions --cov-report=term-missing --cov-fail-under=90
cd backend && .venv/bin/coverage report --include='app/modules/contributions/api/policies.py' --precision=2 --fail-under=90
cd backend && .venv/bin/coverage report --include='app/modules/contributions/models.py' --precision=2 --fail-under=90
cd backend && .venv/bin/coverage report --include='app/modules/contributions/repository.py' --precision=2 --fail-under=90
cd backend && .venv/bin/coverage report --include='app/modules/contributions/service.py' --precision=2 --fail-under=90
cd backend && .venv/bin/coverage report --include='app/modules/contributions/policy_graph.py' --precision=2 --fail-under=90
cd backend && .venv/bin/coverage report --include='app/modules/contributions/policy_publication.py' --precision=2 --fail-under=90
cd backend && .venv/bin/coverage report --include='app/modules/contributions/policy_mutation_support.py' --precision=2 --fail-under=90
cd backend && .venv/bin/coverage report --include='app/adapters/contributions/*' --precision=2 --fail-under=90
cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base <base-sha>
cd backend && .venv/bin/python -m scripts.test_structure_boundary validate --policy ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_POLICY.md --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
python3 scripts/check_active_state_projections.py
python3 scripts/check_chunk_state_sync.py --base-ref <base-sha>
python3 scripts/check_markdown_links.py
git diff --check
```

Hosted CI additionally runs
`tests/contributions/test_policy_publication_concurrency.py` and
`tests/contributions/test_policy_publication_cross_project_postgresql.py` and
`tests/contributions/test_policy_lifecycle_postgresql.py` with real PostgreSQL,
then owns complete semantic-lane and repository aggregate coverage proof.

## Required reviewers

Architecture, security/auth, product/operations, QA, test-delta, CI integrity,
senior engineering, reuse/dedup, and documentation.

## Human review focus and stop conditions

Confirm server-owned publication truth, complete lock order, PREP-before-effect,
immutable history, and no activation/downstream behavior. Stop and amend if a
new action, permission, lifecycle state, foreign write, or compatibility path
is required.
