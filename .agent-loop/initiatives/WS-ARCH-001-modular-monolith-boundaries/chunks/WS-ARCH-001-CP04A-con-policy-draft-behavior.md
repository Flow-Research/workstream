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

- Outcome on merge: `planned`
- The later CP04A implementation PR changes this outcome to `complete`.

## Allowed files

```text
backend/app/modules/contributions/api/**
backend/app/modules/contributions/{schemas.py,models.py,repository.py,service.py}
backend/app/modules/compensation/api/{__init__.py,policy_bindings.py} (instrument type and locked binding facts only)
backend/app/modules/compensation/policy_binding_service.py (owner implementation only)
backend/app/modules/projects/api/{__init__.py,contribution_policy.py} (policy-project eligibility contract only)
backend/app/modules/projects/contribution_policy.py (owner implementation only)
backend/app/adapters/contributions/__init__.py (same-owner composition only)
backend/app/adapters/projects/__init__.py (PROJECTS-owned policy-project eligibility only)
backend/app/db/models.py (metadata parity only if required)
backend/alembic/versions/<next-current-head-policy-operation-migration>.py
backend/alembic/env.py (head parity only)
backend/tests/contributions/**
backend/tests/architecture/** (exact boundary/API proof only)
backend/tests/test_alembic.py (head/schema parity only)
backend/tests/test_contributions.py (preserved DB regressions only; no new primary behavior container)
backend/scripts/{behavior_ownership.py,module_boundaries.py,run_test_lanes.py} (exact parity only)
.ci/behavior-ownership/** (exact CP04A targets only)
.ci/module-boundaries/private-edge-debt.v1.json (remove touched contributions->compensation.schemas edge only)
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json (generated parity; no new debt)
docs/{architecture_data_model.md,roadmap_status.md,spec_contribution_compensation.md}
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/{CHUNK_MAP.md,STATUS.md,DISCOVERY.md}
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/{CHUNK_MAP.md,STATUS.md,AUTHORIZATION_HANDOFF.md}
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-CP04A-con-policy-draft-behavior.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP04A-*.md
```

Replace the migration placeholder with the then-current single Alembic
successor before implementation.

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
- Expose COMPENSATION's closed instrument enum and a transaction-held lookup
  for exact active same-project adapter-binding facts through its public API
  and owner-side service; remove the exact private schemas import from
  CONTRIBUTIONS. COMPENSATION remains the only owner of adapter-binding and
  instrument lifecycle truth. `ProjectCompensationUnit` stays
  CONTRIBUTIONS-owned and is locked by the policy repository.
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
  definitions with canonical positive quantities.
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
partial graph, event, reusable authority, or allowed evidence.

## Acceptance criteria

- [ ] Public API/implementation add no private cross-module edge.
- [ ] PROJECTS and COMPENSATION eligibility is consumed only through their
  public transaction-held ports, with owner fences retained through mutation.
- [ ] Read/create/update remain route-unreachable and production deny-default.
- [ ] Operation fencing proves duplicate recovery and distinct-operation races
  without double AUTH consumption.
- [ ] PREP denial/exception/wrong actor/session/transaction/copy/replay, close
  failure, and post-close database failure fail atomically.
- [ ] PostgreSQL proves immutable operation events, exact attribution,
  transition shape, operation uniqueness, and rejection of mutation/deletion/
  truncation.
- [ ] One primary behavior per test; no new test or production file reaches 500
  lines; touched frozen debt does not grow.
- [ ] Focused changed CONTRIBUTIONS/COMPENSATION coverage is at least 90%;
  hosted repository coverage is not weakened.

## Verification

```bash
cd backend && .venv/bin/ruff check app/modules/contributions app/modules/compensation/api app/modules/compensation/policy_binding_service.py app/modules/projects/api app/modules/projects/contribution_policy.py app/adapters/contributions app/adapters/projects tests/contributions
cd backend && .venv/bin/python -m pytest -q tests/contributions tests/architecture/test_module_boundaries.py tests/test_alembic.py
cd backend && .venv/bin/python -m pytest -q tests/contributions --cov=app.modules.contributions --cov=app.modules.compensation.api --cov=app.modules.compensation.policy_binding_service --cov-report=term-missing --cov-fail-under=90
cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base <base-sha>
cd backend && .venv/bin/python -m scripts.test_structure_boundary validate --policy ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_POLICY.md --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
python3 scripts/check_active_state_projections.py
python3 scripts/check_chunk_state_sync.py --base-ref <base-sha>
python3 scripts/check_markdown_links.py
git diff --check
```

Hosted CI owns complete PostgreSQL, semantic-lane, and repository aggregate
coverage proof; the focused command above owns the changed CP04A surface.

## Required reviewers

Architecture, security/auth, product/operations, QA, test-delta, CI integrity,
senior engineering, reuse/dedup, and documentation.

## Human review focus and stop conditions

Confirm aggregate ownership, complete replacement semantics, operation fencing,
PREP ordering, recovery, and absence of activation/routes. Stop and amend if
implementation needs another action, permission, route, foreign aggregate
write, or lifecycle state.
