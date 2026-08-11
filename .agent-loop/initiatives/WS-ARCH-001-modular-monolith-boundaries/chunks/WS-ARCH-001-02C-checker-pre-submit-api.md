# Chunk Contract: WS-ARCH-001-02C — CHECKER Pre-Submit Public API

Merge disposition: this contract and its projections record `complete`, the
state that will become durable only if this pull request is human-merged. No
contributor preparation action or public route is activated by this chunk.

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Expose dependency-free CHECKER capabilities for deterministic effective-plan
compilation and bounded immutable execution-result facts used by ART
preparation. ART retains durable evidence identity and persistence.

## Why this chunk exists

ART and TASK currently import private CHECKER catalogue and execution types.
The single effective pre-submission checker must remain CHECKER-owned while ART
owns byte custody and evidence attachment.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Entry gate

WS-ARCH-001-02A and 02B are merged with exact immutable TASK and PROJECT fact
manifests.

## Allowed files

```text
backend/app/modules/checkers/api/**
backend/app/modules/checkers/catalogue.py
backend/app/modules/checkers/effective_plan.py
backend/app/modules/checkers/pre_submit_execution.py
backend/app/modules/tasks/pre_submit_context.py
backend/app/modules/artifacts/submission_admission.py
backend/scripts/behavior_ownership.py
backend/tests/architecture/test_module_boundaries.py
backend/tests/test_checker_catalogue.py
backend/tests/test_default_pre_submit_execution.py
backend/tests/test_submission_bundle_admission.py
.ci/module-boundaries/private-edge-debt.v1.json
.ci/behavior-ownership/**
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/STATUS.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-02C-checker-pre-submit-api.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02C-checker-manifest.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-02C-external-review-response.md
docs/architecture_lockdown.md
```

## Not allowed

Second checker catalogue/API; checker policy inference; artifact storage or
scratch ownership transfer; AUTH activation; agent invocation changes; ORM,
session, concrete executor, or mutable internal result leakage.

## Acceptance criteria

- [x] One typed CHECKER API accepts immutable PROJECT/TASK lineage and returns
      a deterministic immutable effective-plan contract.
- [x] Execution results expose bounded checker facts without
      `PreSubmissionExecutionCustody`, `custody`, `storage_scheme`, ART scratch,
      provider, or evidence-persistence details. An ART-owned adapter retains
      custody facts, and a contract test rejects them from the public result.
- [x] ART remains the sole owner of durable evidence identity/persistence, pass
      capability, and admission attachment; CHECKERS creates no parallel
      evidence aggregate.
- [x] Existing platform-default plus project-specific effective policy remains
      one checker plan and one execution path.
- [x] Touched ART/TASK private CHECKER edges are removed with no new edge.
- [x] Record the exact CHECKER fact/port manifest in
      `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02C-checker-manifest.md`.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/checkers app/modules/artifacts/submission_admission.py app/modules/tasks/pre_submit_context.py tests/architecture/test_module_boundaries.py)
(cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q -p pytest_asyncio.plugin -p pytest_cov.plugin tests/architecture/test_module_boundaries.py tests/test_submission_bundle_admission.py tests/test_checker_catalogue.py tests/test_effective_pre_submit_execution.py \
  --cov=app.modules.checkers.api \
  --cov=app.modules.checkers.catalogue \
  --cov=app.modules.checkers.effective_plan \
  --cov=app.modules.checkers.pre_submit_execution \
  --cov-report=term-missing --cov-fail-under=90)
(cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q -p pytest_asyncio.plugin tests/test_default_pre_submit_execution.py::test_disabled_mandatory_executor_state_fails_closed)
(cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base origin/main)
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
docs, reuse/dedup, and test delta.

## Human review focus

Single effective checker ownership, deterministic facts, and no artifact or
policy ownership drift.

## Stop conditions

Stop if the change invents another catalogue/executor, requires raw artifact
bytes in public types, or changes checker semantics.

## Merge state

- Outcome on merge: `complete`
