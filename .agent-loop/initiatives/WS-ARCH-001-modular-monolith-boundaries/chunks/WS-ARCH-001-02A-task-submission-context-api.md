# Chunk Contract: WS-ARCH-001-02A — TASK Submission Context Public API

Implementation state: merged through PR #314. This contract is historical
scope evidence; current sequencing lives in `STATUS.md` and `CHUNK_MAP.md`.

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Expose dependency-free immutable TASK facts and transaction-bound ports for
task, assignment, predecessor, and Submission lifecycle context. Keep all live
submission behavior unchanged.

## Why this chunk exists

ART currently imports TASK's private pre-submit context, which also mixes
PROJECT, CHECKER, and ACTOR concerns. Later chunks need a TASK-owned seam that
does not leak ORM rows or absorb other modules' ownership.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Entry gate

WS-ARCH-001-01 and this reviewed split are merged; current `main` is rebased
before implementation.

## Allowed files

```text
backend/app/modules/tasks/api/**
backend/app/modules/tasks/pre_submit_context.py
backend/app/modules/tasks/repository.py
backend/app/modules/tasks/service.py
backend/tests/architecture/test_module_boundaries.py
backend/tests/test_tasks.py
backend/tests/test_submission_bundle_admission.py
backend/scripts/behavior_ownership.py
.ci/module-boundaries/private-edge-debt.v1.json
.ci/behavior-ownership/**
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-02A-task-submission-context-api.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02A-task-manifest.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-02A-external-review-response.md
docs/architecture_lockdown.md
```

## Not allowed

AUTH or ART activation; public route/schema changes; Submission persistence
changes; PROJECT/CHECKER facts in TASK public types; ORM/session/repository or
mutable dictionaries in the public API; new private edges.

## Acceptance criteria

- [ ] `tasks.api` exposes immutable identifiers and lineage facts only.
- [ ] Owner-local adapters lock/reload TASK, assignment and predecessor state
      without reading ACTOR, PROJECT, CHECKER or ART persistence.
- [ ] Initial and revision predecessor rules are explicit and fail closed.
- [ ] Existing behavior is unchanged and touched TASK private edges shrink.
- [ ] Public API dependency/leak/cycle tests pass.
- [ ] Record the exact TASK fact/port manifest in
      `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02A-task-manifest.md`.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/tasks tests/architecture/test_module_boundaries.py tests/test_tasks.py)
(cd backend && export WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?set WORKSTREAM_TEST_DATABASE_URL}" && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q -p pytest_asyncio.plugin -p pytest_cov.plugin tests/architecture/test_module_boundaries.py tests/test_tasks.py tests/test_submission_bundle_admission.py --cov=app.modules.tasks.api --cov-report=term-missing --cov-fail-under=90)
(cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base origin/main)
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
docs, reuse/dedup, and test delta.

## Human review focus

Confirm TASK ownership is narrow and the public seam cannot become a facade for
PROJECT/CHECKER/ACTOR persistence.

## Stop conditions

Stop if TASK facts cannot be produced without another owner capability, a
public type would expose persistence, or behavior/route activation is required.
