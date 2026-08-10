# Chunk Contract: WS-ARCH-001-02B — PROJECT Locked Policy Public API

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Expose dependency-free immutable PROJECT facts and ports for the locked guide,
source snapshot, effective submission-artifact policy, and pre-submit policy
lineage referenced by one TASK context.

## Why this chunk exists

TASK's private pre-submit loader currently reads PROJECT ORM rows. Preparation
must obtain server-owned locked-policy facts from PROJECTS without transferring
PROJECT persistence or policy ownership to TASKS or ART.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Entry gate

WS-ARCH-001-02A is merged and its exact TASK fact manifest is recorded.

## Allowed files

```text
backend/app/modules/projects/api/**
backend/app/modules/projects/repository.py
backend/app/modules/projects/service.py
backend/app/modules/tasks/pre_submit_context.py
backend/tests/architecture/test_module_boundaries.py
backend/tests/test_projects.py
backend/tests/test_tasks.py
.ci/module-boundaries/private-edge-debt.v1.json
.ci/behavior-ownership/**
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/**
docs/architecture_lockdown.md
```

## Not allowed

Policy recompilation or approval changes; AUTH/ART activation; CHECKER plan
ownership; ORM/session/repository or mutable policy bodies in `projects.api`;
new private edges.

## Acceptance criteria

- [ ] PROJECTS validates exact project/guide/snapshot/policy lineage under its
      own locks and returns immutable canonical facts/digests.
- [ ] Cross-project, replaced, draft, and hash-mismatched context fails closed.
- [ ] TASK consumes `projects.api` only; no PROJECT model/repository import
      remains in the touched pre-submit path.
- [ ] Public API dependency/leak/cycle and protected-ledger checks pass.
- [ ] Record the exact PROJECT fact/port manifest in
      `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02B-project-manifest.md`.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/projects app/modules/tasks/pre_submit_context.py tests/architecture/test_module_boundaries.py)
(cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q -p pytest_asyncio.plugin -p pytest_cov.plugin tests/architecture/test_module_boundaries.py tests/test_projects.py tests/test_tasks.py tests/test_submission_bundle_admission.py --cov=app.modules.projects.api --cov-report=term-missing --cov-fail-under=90)
(cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base origin/main)
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
docs, reuse/dedup, and test delta.

## Human review focus

Exact locked-policy lineage, immutable output, and absence of PROJECT behavior
inside TASK or ART.

## Stop conditions

Stop if the seam needs mutable policy payloads, bypasses locked lineage, or
changes guide/policy lifecycle.
