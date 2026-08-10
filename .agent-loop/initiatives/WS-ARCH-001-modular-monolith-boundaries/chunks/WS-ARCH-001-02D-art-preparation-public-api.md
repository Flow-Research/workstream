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

## SLA

P1

## Entry gate

WS-ARCH-001-02A through 02C are merged and current `main` matches their TASK,
PROJECT, and CHECKER public fact manifests.

## Allowed files

```text
backend/app/modules/artifacts/api/**
backend/app/modules/artifacts/submission_admission.py
backend/app/modules/artifacts/submission_authorization.py
backend/app/modules/artifacts/schemas.py
backend/app/adapters/artifacts/__init__.py
backend/app/interfaces/artifact_operations.py
backend/app/modules/tasks/router.py
backend/tests/architecture/test_module_boundaries.py
backend/tests/test_submission_bundle_admission.py
backend/tests/test_default_pre_submit_execution.py
.ci/module-boundaries/private-edge-debt.v1.json
.ci/behavior-ownership/**
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/**
docs/spec_artifact_storage_service.md
```

## Not allowed

Action activation; public OpenAPI exposure; Submission creation/binding;
provider or checker semantic changes; raw `AuthorizationContext`; private
cross-module imports; serialized prepared handles; compatibility facades.

## Acceptance criteria

- [ ] The route and composition code depend on `artifacts.api`; ART depends on
      owner public APIs only.
- [ ] The public port shape places preflight before byte acceptance and final
      prepared-authority consumption in the durable-intent transaction before
      capacity, put attempt, or provider I/O, but production remains deny-only
      and no successful prepared handle is issued or consumed in this chunk.
- [ ] Planned-action denial, concealment, exact replay, stale lineage, and
      cross-resource attempts preserve zero partial effect and zero provider I/O.
- [ ] `artifact.submission_bundle.prepare` remains planned/unavailable and the
      route remains hidden.
- [ ] Every touched private edge is removed.
- [ ] Submission-preparation types in
      `app.interfaces.artifact_operations` migrate to `artifacts.api`; no
      parallel legacy/public ART contract remains.
- [ ] Record the exact preparation resource/port manifest in
      `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02D-resource-manifest.md`.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/artifacts app/modules/tasks/router.py app/adapters/artifacts tests/test_submission_bundle_admission.py)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_submission_bundle_admission.py tests/test_default_pre_submit_execution.py tests/architecture/test_module_boundaries.py --cov=app.modules.artifacts --cov-fail-under=90)
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
