# Chunk Contract: WS-ARCH-001-02E — ART Admission Consumption And Binding API

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Expose ART-owned transaction-bound capabilities to lock/validate one verified
ready admission, mark proven incompatibility stale, create one exact Submission
binding, and consume the admission exactly once.

## Why this chunk exists

TASKS must create the Submission without importing ART persistence. ART must
enforce admission/binding invariants without creating or querying TASK rows.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Entry gate

WS-ARCH-001-02D is merged with contributor preparation still unavailable and
its exact resource manifest recorded. The merged 02A TASK API supplies the
immutable task, assignment, predecessor-Submission, project, guide, snapshot,
and policy lineage capability; ART must not remove its locked recheck until it
can consume that capability instead of TASK persistence.

## Allowed files

```text
backend/app/modules/artifacts/api/**
backend/app/modules/artifacts/models.py
backend/app/modules/artifacts/repository.py
backend/app/modules/artifacts/submission_admission.py
backend/app/modules/artifacts/submission_bindings.py
backend/app/modules/artifacts/guide_bindings.py
backend/app/interfaces/artifact_operations.py
backend/alembic/versions/<next-current-main-revision>.py
backend/tests/test_submission_bundle_admission.py
backend/tests/test_artifact_bindings.py
backend/tests/test_alembic.py
backend/tests/architecture/test_module_boundaries.py
.ci/module-boundaries/private-edge-debt.v1.json
.ci/behavior-ownership/**
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-02E-art-admission-binding-api.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02E-admission-binding-manifest.md
docs/spec_artifact_storage_service.md
docs/architecture_data_model.md
```

## Not allowed

TASK ORM/repository/imports; Submission creation; route or AUTH availability;
provider I/O; deletion/expiry/retention; compatibility path; new private edge.

## Acceptance criteria

- [ ] Public inputs/outputs are immutable identifiers, digests, sizes, status,
      and stable errors only.
- [ ] The ART port consumes the typed 02A TASK lineage capability and locks the
      exact task, assignment, predecessor-Submission, project, guide, snapshot,
      and policy facts without querying TASK persistence.
- [ ] ART locks and validates ready admission/content/manifest/evidence lineage
      and accepts a server-owned Submission identity supplied by TASKS.
- [ ] `ready -> consumed|stale` is terminal, unique, concurrency-safe, and
      rollback-safe; authority loss alone never marks stale.
- [ ] Binding identity is exact and provider-neutral; no provider I/O occurs.
- [ ] Reuse the existing generic `ArtifactBinding` model and the established
      guide-binding replay/authority-consumption convention unless a separately
      reviewed schema finding proves it insufficient; do not create a parallel
      binding aggregate.
- [ ] Submission-binding types in `app.interfaces.artifact_operations` migrate
      to `artifacts.api`; no parallel legacy/public ART contract remains.
- [ ] Capability remains unreachable from the public route pending 02F-02I.
- [ ] Record the exact admission/binding port, state, error, and resource
      manifest, including the complete TASK lineage resource facts, in
      `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02E-admission-binding-manifest.md`.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/artifacts tests/test_submission_bundle_admission.py tests/test_artifact_bindings.py)
(cd backend && export WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?set WORKSTREAM_TEST_DATABASE_URL}" && .venv/bin/python -m pytest -q tests/test_submission_bundle_admission.py tests/test_artifact_bindings.py tests/test_alembic.py --cov=app.modules.artifacts --cov-fail-under=90)
(cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base origin/main)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
docs, reuse/dedup, and test delta.

## Human review focus

Admission state machine, immutable binding identity, concurrency, staleness,
and absence of TASK/provider ownership in ART.

## Stop conditions

Stop if ART must read TASK persistence, create a Submission, perform provider
I/O, or activate binding authority.
