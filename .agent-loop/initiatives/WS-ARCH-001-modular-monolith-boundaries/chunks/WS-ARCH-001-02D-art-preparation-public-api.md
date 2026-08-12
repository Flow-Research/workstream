# Chunk Contract: WS-ARCH-001-02D — ART Hidden Preparation Public API Migration

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Make the complete hidden submission-bundle preparation command consume only
AUTH, TASKS, PROJECTS, and CHECKERS public capabilities while preserving the
existing deny-only route and exact ART custody behavior.

## Why this chunk exists

The hidden path is behaviorally complete through ART-04C2 but still crosses
private module seams. AUTH cannot activate contributor preparation until those
edges are removed and final authority remains transaction-bound.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md`

## Risk class

L1

## Merge state

- Outcome on merge: `complete`

## SLA

P1

## Entry gate

WS-ARCH-001-02A through 02C are merged and current `main` matches their TASK,
PROJECT, and CHECKER public fact manifests.

## Allowed files

```text
backend/app/modules/artifacts/api/**
backend/app/modules/artifacts/authorization.py
backend/app/modules/artifacts/router.py
backend/app/modules/artifacts/pre_submit_evidence.py
backend/app/modules/artifacts/submission_admission.py
backend/app/modules/artifacts/submission_authorization.py
backend/app/modules/artifacts/submission_materialization.py
backend/app/modules/artifacts/schemas.py
backend/app/adapters/artifacts/__init__.py
backend/app/adapters/checkers/__init__.py
backend/app/adapters/projects/__init__.py
backend/app/adapters/tasks/__init__.py
backend/app/api/deps/authorization.py
backend/app/interfaces/artifact_operations.py
backend/app/modules/tasks/router.py
backend/app/api/router.py
backend/app/api/routes/artifact_submissions.py
backend/tests/architecture/test_module_boundaries.py
backend/scripts/module_boundaries.py
backend/tests/test_artifact_architecture.py
backend/tests/test_submission_bundle_admission.py
backend/tests/test_default_pre_submit_execution.py
backend/tests/test_effective_pre_submit_execution.py
backend/tests/test_authorization.py
backend/tests/test_pre_submit_evidence_relock.py
backend/tests/pre_submit_test_helpers.py
.ci/module-boundaries/private-edge-debt.v1.json
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
.ci/behavior-ownership/**
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-02D-art-preparation-public-api.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/STATUS.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02D-resource-manifest.md
docs/spec_artifact_storage_service.md
.agent-loop/policies/architecture-boundaries.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/INTENT.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/PLAN.md
docs/architecture_lockdown.md
docs/operations_backend_testing.md
backend/app/adapters/README.md
```

## Public and private contract split

- `artifacts.api` owns only dependency-safe route-facing request/result/error
  values and capability ports. It does not re-export private ART scratch,
  inspection, custody, manifest, pass-capability, repository, session, or
  provider types.
- Process-local sealed preparation and materialization values move out of the
  repository-global `app.interfaces.artifact_operations` surface and remain
  ART-private with one physical definition.
- AUTH handles remain opaque `object` values at ART seams. ART does not import,
  reconstruct, serialize, or inspect AUTH's private handle class; the concrete
  transaction-bound AUTH adapter owns validation and consumption.
- The composition root may import concrete TASK, PROJECT, CHECKER, AUTH, and
  ART implementations to construct public ports. Route-facing and product
  module code may depend only on owner public APIs.

## Not allowed

Action activation; public OpenAPI exposure; Submission creation/binding;
provider or checker semantic changes; raw `AuthorizationContext`; private
cross-module imports; serialized prepared handles; compatibility facades.

## Acceptance criteria

- [x] The route and composition code depend on `artifacts.api`; ART depends on
      owner public APIs only. The composition root may instantiate concrete
      implementations but may not hide a service locator or second factory
      behind the public API.
- [x] The public port shape places preflight before byte acceptance and final
      prepared-authority consumption in the durable-intent transaction before
      capacity, put attempt, or provider I/O, but production remains deny-only
      and no successful prepared handle is issued or consumed in this chunk.
- [x] Planned-action denial, concealment, exact replay, stale lineage, and
      cross-resource attempts preserve zero partial effect and zero provider I/O.
- [x] `artifact.submission_bundle.prepare` remains planned/unavailable and the
      route remains hidden.
- [x] Every touched private edge is removed.
- [x] Route-facing submission-preparation types in
      `app.interfaces.artifact_operations` migrate to `artifacts.api`.
      Process-local sealed types become ART-private; no parallel legacy/public
      ART contract remains.
- [x] After byte materialization and before evidence persistence, ART re-locks
      TASK assignment/predecessor facts and PROJECT locked-policy facts through
      their public ports and compares them with the original CHECKER plan
      lineage. Stale lineage fails before durable evidence or provider I/O.
- [x] CHECKER execution is injected at the composition root and returns only
      public CHECKER result facts. ART constructs and retains its own custody
      facts; neither module imports the other's private implementation.
- [x] `artifacts.api` imports no private module and exposes no ORM, session,
      repository, provider, scratch path, byte buffer, or serialized handle.
- [x] Record the exact preparation resource/port manifest in
      `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02D-resource-manifest.md`.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/artifacts app/modules/tasks/router.py app/adapters/artifacts tests/test_submission_bundle_admission.py)
(cd backend && export WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?set WORKSTREAM_TEST_DATABASE_URL}" && .venv/bin/python -m pytest -q tests/test_submission_bundle_admission.py tests/test_default_pre_submit_execution.py tests/architecture/test_module_boundaries.py --cov=app.modules.artifacts --cov-fail-under=90)
(cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base origin/main)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
docs, reuse/dedup, and test delta.

## Human review focus

Authority call ordering and resource shape, public-edge completeness,
byte/provider ordering, and proof that availability did not change or rely on
a successful AUTH stub.

## Stop conditions

Stop if any required public owner capability is absent, AUTH facts differ from
the merged manifest, or provider I/O must precede committed authority.
