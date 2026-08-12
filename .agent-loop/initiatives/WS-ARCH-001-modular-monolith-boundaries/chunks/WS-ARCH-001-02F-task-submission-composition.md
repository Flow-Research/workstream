# Chunk Contract: WS-ARCH-001-02F — TASK Submission Command And Atomic Composition

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Implement the TASK-owned immutable Submission command and hidden application
composition that atomically consumes deny-only human AUTH, deny-only fixed
ART-binding AUTH, the already-ready ART admission/binding, and TASK persistence
through public ports.

## Why this chunk exists

One transaction must produce one complete Submission/binding/admission effect
without moving lifecycle ownership into ART, AUTH, or a generic orchestrator.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Entry gate

WS-ARCH-001-02E is merged with its exact admission/binding manifest, ART ports
hidden, and production contributor/binding authority unavailable.

## Allowed files

```text
backend/app/modules/tasks/api/**
backend/app/modules/tasks/models.py
backend/app/modules/tasks/repository.py
backend/app/modules/tasks/service.py
backend/app/modules/tasks/submission_composition.py
backend/app/adapters/tasks/submission_composition.py
backend/app/adapters/tasks/__init__.py
backend/app/main.py
backend/alembic/versions/<next-current-main-revision>.py
backend/tests/test_tasks.py
backend/tests/test_submission_concurrency.py
backend/tests/test_submission_history.py
backend/tests/test_alembic.py
backend/tests/architecture/test_module_boundaries.py
.ci/module-boundaries/private-edge-debt.v1.json
.ci/behavior-ownership/**
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-02F-task-submission-composition.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02F-transaction-manifest.md
docs/architecture_data_model.md
```

## Not allowed

Public route/schema cutover; AUTH availability; legacy guard removal; ART ORM/
repository imports in TASKS; business branching in composition; checker/review/
contribution dispatch; compatibility facade.

## Acceptance criteria

- [ ] TASKS allocates immutable Submission identity/version and predecessor
      lineage under lock; ART owns binding/consumption through its port.
- [ ] The command's public port shape places human `submission.create` and
      fixed `artifact.submission.binding.create` consumption in the same root
      transaction as every mutation and evidence row. Production wiring remains
      deny-only; this chunk proves denial/concealment and zero mutation, not a
      successful AUTH capability or complete business effect.
- [ ] The command accepts only typed TASK-owned authority ports. It never
      receives an AUTH prepared handle, raw authorization context, AUTH
      repository/session, or private ART service. The deny-only implementations
      conceal the unavailable capability before any protected mutation.
- [ ] Pre-submit evidence and the ready admission are immutable prerequisites
      produced by the earlier preparation path; 02F neither re-persists nor
      mutates checker evidence. An integration test proves a final-stage failure
      rolls back the Submission, binding, admission transition, and any
      transaction-local authorization evidence together.
- [ ] Composition opens one unit of work and wires ports only; TASK command owns
      sequencing and each owner enforces its invariants.
- [ ] Denial, cancellation and persistence failure roll back all effects;
      positive complete-effect and concurrency proof is deferred to 02H using
      the live AUTH adapters.
- [ ] Record the exact lock order, public port/fact shape, protected mutations,
      and authorization resource manifest in
      `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02F-transaction-manifest.md`.
- [ ] The new command remains hidden/unreachable pending 02G-02I.

## Required lock and operation order

1. Open one root transaction in the application composition adapter.
2. Consume/conceal the human `submission.create` authority through its typed
   deny-only TASK-facing port before protected state is revealed or mutated.
3. Lock TASK, active assignment, and latest predecessor through TASK ownership.
4. Allocate the immutable Submission id and next version from the locked facts.
5. Call the ART admission-consumption public port with that exact id, version,
   and TASK context; ART locks its lineage and consumes fixed binding authority.
6. Persist and flush the TASK-owned Submission with the exact predecessor and
   ART content/binding references required by the command contract.
7. Consume/record any final TASK-owned authority evidence inside the same root
   transaction, then let the composition adapter commit once.

No step may commit independently. Denial or failure at any step rolls back the
whole root transaction.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/tasks app/adapters app/main.py tests/test_submission_concurrency.py)
(cd backend && export WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?set WORKSTREAM_TEST_DATABASE_URL}" && .venv/bin/python -m pytest -q tests/test_tasks.py tests/test_submission_concurrency.py tests/test_submission_history.py tests/test_alembic.py --cov=app.modules.tasks --cov-fail-under=90)
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

One transaction shape, TASK lifecycle ownership, dual authority separation,
lock order, deny-only zero effect, and absence of orchestration-domain drift.

## Stop conditions

Stop if transaction atomicity requires public sessions/repositories, if ART
must create Submission, or if the live route must change early.

## Merge state

- Outcome on merge: `complete`
