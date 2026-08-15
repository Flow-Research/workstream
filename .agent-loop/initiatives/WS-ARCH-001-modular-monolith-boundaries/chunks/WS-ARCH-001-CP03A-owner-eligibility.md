# Chunk Contract: WS-ARCH-001-CP03A — Adapter Target Identity And Owner Eligibility

## Merge state

- Outcome on merge: `planned`
- Future implementation target: complete while binding actions remain unavailable.

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Register one closed compensation-adapter target identity and implement the real
PROJECTS- and ACTORS-owned eligibility adapters required by CP02 create/resume,
through their owner modules' public APIs and without activating any
adapter-binding action.

## Why this chunk exists

CP02 intentionally used strict fakes because current main has only public owner
protocols. Its contract requires an active service actor explicitly eligible
for compensation-adapter binding and rejects generic service kind or reuse of
ART, REV, checker, dispatcher, and other internal identities. The ActorProfile
schema requires every service actor to carry a closed ServiceIdentity. CP03A
therefore establishes that target identity and owner-held locks before CP03B
can activate AUTH.

## Risk class

L1 — actor identity, authorization prerequisite, and transaction custody.

## SLA

P1

## Exact identity rule

`workstream.compensation.adapter` is a closed service ActorProfile identity
used only as the eligible target of a ProjectCompensationAdapterBinding. It is
not the Finance Authority caller and receives no action, permission, service
matrix row, database grant, route, callback, provider credential, or implicit
feature authority.

Eligibility requires, under ACTORS-owned transaction-held row locks:

- exact `adapter_actor_id`;
- `actor_kind=service`;
- `status=active`;
- `service_identity=workstream.compensation.adapter`;
- the actor's exact service ActorIdentityLink exists, is active, and has
  `subject_kind=service`.

ACTORS exposes these facts only through
`app.modules.actors.api.CompensationAdapterActorEligibilityPort`; its concrete
implementation remains private to ACTORS. CON consumes that injected public
port. AUTH may register/provision the closed identity through existing public
composition surfaces, but AUTH must not import the ACTORS implementation or
create an AUTH-to-ACTORS domain adapter.

PROJECTS independently locks the exact project and validates only
PROJECTS-owned binding eligibility through
`app.modules.projects.api.ProjectCompensationBindingEligibilityPort`. PROJECTS
does not inspect or decide a CON binding lifecycle state. CON owns the binding
lifecycle and decides that create and resume require the PROJECTS and ACTORS
eligibility ports, while suspend remains possible after owner ineligibility.
Both owner adapters flush nothing, commit nothing, and return only their public
immutable facts. CP02 retains the locks through the caller-owned root
transaction.

## Allowed files

```text
backend/app/modules/actors/service_identities.py
backend/app/modules/actors/models.py (constraint parity only)
backend/app/modules/actors/compensation_adapter.py
backend/app/modules/actors/api/compensation_adapter.py (fact/port parity only)
backend/app/modules/actors/api/__init__.py
backend/app/modules/projects/compensation_binding.py
backend/app/modules/projects/api/compensation_binding.py (fact/port parity only)
backend/app/modules/projects/api/__init__.py
backend/app/modules/authorization/service_actor_schemas.py (closed identity parity only)
backend/app/modules/authorization/service_actor_service.py (provisioning admission parity only)
backend/app/modules/authorization/catalogue.py (separate target-only identities from action-bearing fixed services)
backend/app/modules/compensation/service.py (owner-adapter injection only)
backend/app/api/deps/authorization.py (composition only; no route)
backend/app/main.py (composition only; no route)
backend/alembic/env.py
backend/alembic/versions/0005_compensation_adapter_identity.py
backend/tests/actors/test_compensation_adapter_eligibility.py
backend/tests/projects/test_compensation_binding_eligibility.py
backend/tests/compensation/test_adapter_binding_owner_fences.py
backend/tests/compensation/test_adapter_binding_authorization_integration.py
backend/tests/test_auth.py (controlled provisioning parity only)
backend/tests/test_authorization.py (closed identity/matrix separation only)
backend/tests/test_alembic.py
backend/tests/test_database_reset.py
backend/tests/conftest.py (exact current-schema fingerprint/reset parity only)
backend/alembic/baseline/v01_approved_manifest_delta.json (generated current-head parity only; do not rewrite 0001)
backend/alembic/baseline/v01_baseline_manifest.json (generated current-head parity only; do not rewrite 0001)
backend/alembic/baseline/v01_pre_reset_source_manifest.json (generated current-head parity only; do not rewrite 0001)
backend/alembic/baseline/v01_schema.sql (generated current-head parity only; do not rewrite 0001)
backend/scripts/behavior_ownership.py
backend/scripts/run_test_lanes.py
.ci/behavior-ownership/partition.v1.json
.ci/behavior-ownership/actors/compensation-adapter-eligibility.json
.ci/behavior-ownership/projects/compensation-binding-eligibility.json
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json (generated parity only)
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/STATUS.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-CP03-auth-binding-activation.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-CP03A-owner-eligibility.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-CP03B-auth-binding-activation.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP03A-plan-review-evidence.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP03A-implementation-review-evidence.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP03A-external-review-response.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP03A-pr-trust-bundle.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/ACTIVATION_CUSTODY.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/STATUS.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/AUTHORIZATION_HANDOFF.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/CHUNK_MAP.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/STATUS.md
docs/architecture_data_model.md
docs/spec_authorization_service.md
docs/operations_authorization_service.md
docs/spec_contribution_compensation.md
docs/roadmap_status.md
```

## Not allowed

```text
adapter-binding action activation or evaluator
Finance Authority grant/evaluation changes
service action matrix row for workstream.compensation.adapter
public route, provider adapter, credential, endpoint, account, or network I/O
binding lifecycle, repository, event, recovery, or idempotency changes
ContributionPolicy, retirement, award, fulfillment, callback, delivery, dispatcher, reconciliation, or reputation behavior
generic service eligibility, prefix matching, runtime plugin discovery, or reuse of another fixed identity
private cross-module imports or a second owner-adapter path
compatibility support for old identities or deployed rows
```

## Acceptance criteria

- [ ] Exactly one closed identity, `workstream.compensation.adapter`, is added;
      all existing identities and matrix memberships are unchanged.
- [ ] Closed ActorProfile service identities and action-bearing fixed-service
      identities are explicit separate sets. The target identity belongs only
      to the former; catalogue import succeeds without an empty or invented
      matrix row, and runtime service-action admission rejects it.
- [ ] Migration `0005_compensation_adapter_identity` updates only the closed
      ActorProfile service-identity constraint and refuses downgrade without
      mutation when the new identity is referenced.
- [ ] Existing controlled service provisioning can create the exact profile and
      identity link but grants it no role, permission, matrix membership, or
      feature authority.
- [ ] ACTORS locks and validates the exact active profile and active service
      identity link; human actors, generic service kind, missing/revoked links,
      inactive profiles, and every existing ART/REV/project/checker identity
      deny with one concealed unavailable result.
- [ ] ACTORS exposes and CP02/CON consumes only the immutable public
      `CompensationAdapterActorEligibilityPort`; AUTH and CON import no ACTORS
      private model, repository, service, or concrete adapter.
- [ ] PROJECTS locks and validates only the exact project's PROJECTS-owned
      binding eligibility through the immutable public
      `ProjectCompensationBindingEligibilityPort`; absent, ineligible, and
      cross-project targets deny, and PROJECTS contains no CON lifecycle rule.
- [ ] CON alone decides that create/resume invoke both owner eligibility ports
      and that suspend does not; no owner module interprets binding status or
      lifecycle version.
- [ ] Owner locks remain held through CP02 authorization and mutation for
      create/resume; a competing revocation or project-ineligibility commit
      cannot enter between validation and product transition.
- [ ] If revocation/ineligibility commits first, create/resume denies before
      AUTH consumption and creates no binding, lifecycle event, or allowed
      evidence.
- [ ] Suspend remains possible after target/project ineligibility once CP03B
      provides Finance Authority; CP03A does not weaken that recovery rule.
- [ ] All four adapter-binding actions remain planned/unavailable; no route or
      product behavior becomes reachable.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/actors/service_identities.py app/modules/actors/compensation_adapter.py app/modules/projects/compensation_binding.py app/modules/authorization/catalogue.py tests/actors/test_compensation_adapter_eligibility.py tests/projects/test_compensation_binding_eligibility.py tests/compensation/test_adapter_binding_owner_fences.py tests/test_auth.py tests/test_authorization.py tests/test_alembic.py tests/test_database_reset.py)
(cd backend && export WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?set WORKSTREAM_TEST_DATABASE_URL}" && .venv/bin/python -m pytest -q tests/actors/test_compensation_adapter_eligibility.py tests/projects/test_compensation_binding_eligibility.py tests/compensation/test_adapter_binding_owner_fences.py tests/compensation/test_adapter_binding_authorization_integration.py tests/test_alembic.py tests/test_database_reset.py --cov=app.modules.actors.compensation_adapter --cov=app.modules.projects.compensation_binding --cov-fail-under=90)
(cd backend && export WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?set WORKSTREAM_TEST_DATABASE_URL}" && .venv/bin/python -m pytest -q tests/test_auth.py -k service_actor)
(cd backend && .venv/bin/python -m pytest -q tests/test_authorization.py -k "service_actor or service_identity or service_action_matrix")
(cd backend && .venv/bin/python -m scripts.test_structure_boundary validate --policy ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_POLICY.md --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json)
(cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base origin/main)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
python3 scripts/check_markdown_links.py
git diff --check
gh pr checks <PR-number> --watch
```

Hosted GitHub Actions owns the full PostgreSQL matrix and repository coverage.
The local machine must not run the full suite.

## Required reviewers

Architecture, security/auth, product/operations, QA, test delta, CI integrity,
senior engineering, reuse/dedup, and documentation.

## Human review focus

Confirm the exact target-only identity, absence of a service matrix grant,
owner-module lock custody, denial of every existing fixed identity, migration
safety, and continued unavailability of all binding actions.

## Stop conditions

Stop and amend/re-review if another identity, permission, action, matrix row,
provider behavior, owner fact, schema surface, or cross-module private import is
required.
