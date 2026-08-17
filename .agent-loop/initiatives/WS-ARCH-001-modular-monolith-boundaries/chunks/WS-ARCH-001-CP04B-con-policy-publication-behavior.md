# Chunk Contract: WS-ARCH-001-CP04B — Hidden ContributionPolicy Publication

## Goal

Implement hidden publish and retire behavior using CP04A's public API,
operation/recovery custody, and opaque authorization port. Keep all policy
actions unavailable and add no route or downstream product behavior.

## Preconditions, risk and outcome

- CP04A is merged and current-main discovery is replayed.
- Risk: L1.

## Merge state

- Outcome on merge: `planned`
- The later CP04B implementation PR changes this outcome to `complete`; CP05
  then becomes next.

## Allowed files

```text
backend/app/modules/contributions/api/**
backend/app/modules/contributions/{models.py,repository.py,service.py}
backend/app/adapters/contributions/__init__.py
backend/alembic/versions/<next-current-head-policy-lifecycle-migration>.py (only if schema proof requires correction)
backend/alembic/env.py (head parity only if migration exists)
backend/tests/contributions/**
backend/tests/architecture/** (exact boundary proof only)
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
  competing publication, revocation, replay, cross-project use, wrong session/
  transaction, close failure, and rollback fail closed without mutation.
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
| PREP denial/exception/wrong actor/session/transaction/copy/replay/close failure occurs before lifecycle mutation | `tests/contributions/test_policy_publication_authorization.py` with one primary failure behavior per test and an in-consume assertion that no lifecycle change/event is staged | focused local command and hosted CI |
| Replacement publication atomically retires the prior current version with matching actor/time and emits one recoverable `published` event | `tests/contributions/test_policy_publish.py::{test_replacement_publication_is_one_atomic_event,test_replacement_preserves_prior_content_and_frozen_references}` | focused local command and hosted PostgreSQL lane |
| Exact duplicate recovery returns immutable event facts only after current read authorization | `tests/contributions/test_policy_publication_recovery.py` covering publish and retire duplicates, digest mismatch, revoked read, and no second effect/evidence | focused local command and hosted CI |
| Cross-project publish facts (policy, version, unit, or adapter binding) and retire targets (policy or exact current version) fail closed with concealed denial, no lifecycle mutation, and no staged AUTH evidence or other side effect | Focused service proof in `tests/contributions/test_policy_publication_authorization.py::{test_cross_project_policy_publish_is_concealed_without_effect,test_cross_project_version_publish_is_concealed_without_effect,test_cross_project_unit_publish_is_concealed_without_effect,test_cross_project_binding_publish_is_concealed_without_effect,test_cross_project_policy_retire_is_concealed_without_effect,test_cross_project_current_version_retire_is_concealed_without_effect}`; transaction/row-custody proof in `tests/contributions/test_policy_publication_cross_project_postgresql.py` using independently committed cross-project rows and direct assertions that lifecycle state/events and AUTH evidence remain absent | named focused tests run locally and in hosted CI; `test_policy_publication_cross_project_postgresql.py` runs in the hosted PostgreSQL lane only |
| Child mutation, binding suspension, unit retirement, and competing publication cannot cross held owner fences | `tests/contributions/test_policy_publication_concurrency.py` using independent PostgreSQL sessions and deterministic commit ordering | hosted PostgreSQL lane only |
| PostgreSQL rejects incomplete publication, lifecycle skips, forged attribution, event mutation/deletion/truncation, and stale prior-current identity | `tests/contributions/test_policy_lifecycle_postgresql.py` using direct SQL negative cases | hosted PostgreSQL lane only |
| Explicit retirement is terminal and cannot rewrite frozen downstream lineage or resurrect the aggregate | `tests/contributions/test_policy_retire.py::{test_retire_blocks_future_selection_without_rewriting_history,test_retired_aggregate_cannot_be_resurrected}` | focused local command and hosted CI |
| Database failure after close rolls back lifecycle state and staged AUTH evidence; closed authority remains unusable | `tests/contributions/test_policy_publication_authorization.py::{test_post_close_failure_rolls_back_all_effects,test_closed_publication_authority_cannot_be_reused}` | focused local command and hosted PostgreSQL lane |

The focused pytest command must name every non-hosted-only module above. Hosted
CI must additionally run `test_policy_publication_concurrency.py` and
`test_policy_publication_cross_project_postgresql.py` and
`test_policy_lifecycle_postgresql.py` against real PostgreSQL; mock locks or an
in-memory database do not satisfy the contract.

```bash
cd backend && .venv/bin/ruff check app/modules/contributions app/modules/compensation/api app/modules/compensation/policy_binding_service.py app/adapters/contributions tests/contributions
cd backend && .venv/bin/python -m pytest -q tests/contributions/test_policy_publication_authorization.py tests/contributions/test_policy_routes_absent.py tests/contributions/test_policy_publish.py tests/contributions/test_policy_publication_recovery.py tests/contributions/test_policy_retire.py tests/architecture/test_module_boundaries.py tests/test_alembic.py
cd backend && .venv/bin/python -m pytest -q tests/contributions --cov=app.modules.contributions --cov-report=term-missing --cov-fail-under=90
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
