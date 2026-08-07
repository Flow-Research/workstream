# Chunk Contract: WS-AUTH-001-12F3 — Fixed-Service Policy Derivation

## Status and prerequisite

Implementation complete and ready for hosted CI/external review after merged
12F2. Risk: L1. Human merge remains required.

## Goal

Activate submission-policy derivation only for `workstream.project.setup`, cut
the Celery executor to a fresh fixed-service PREP command, and remove public inline
derivation.

## Allowed files

```text
backend/app/api/deps/authorization.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/modules/projects/router.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/service.py
backend/app/modules/projects/setup_queue.py
backend/app/modules/projects/submission_policy_mutation_service.py
backend/app/modules/projects/submission_policy_mutation_repository.py
backend/app/modules/projects/models.py
backend/app/modules/projects/sufficiency_mutation_service.py
backend/app/workers/project_setup.py
backend/tests/test_authorization.py
backend/tests/test_alembic.py
backend/tests/test_projects.py
backend/tests/conftest.py
backend/alembic/versions/0059_submission_policy_execution_claim.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
docs/operations_project_operating_manual.md
docs/spec_chunk_3_project_guide_foundation.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed

Human inline agent calls, serialized handles, approval/effective/pre-submit
mutation, post-submit policy, generic service authority, or ART behavior.

## Acceptance

- Activate only `project.submission_artifact_policy.derive` for the exact active
  fixed service profile/link/matrix membership; no matched human grant exists.
- The public derive route is removed from runtime/OpenAPI/import reachability.
  PM setup request/recovery continues through the already governed asynchronous
  setup dispatch and never calls the agent inline.
- Celery payloads contain identifiers only. After reload they validate exact
  project/draft guide/latest snapshot, active setup run, generation, expected
  persisted `submission_artifact_policy_derivation` product step, deterministic
  task/correlation identity, sufficiency output and stale-output digest. The
  typed AUTH custody selector is deliberately named `submission_artifact_policy`;
  12F3 maps that closed selector to the one longer persisted step and does not
  widen either enum or accept both names at either boundary.
- The exact authoritative sufficiency report must match the snapshot/generation
  and be `passed`, or `passed_with_warnings` with its warnings acknowledged.
  Missing, blocked, stale, diagnostic-only or unacknowledged-warning output
  denies before material or agent I/O.
- After an authorized warning acknowledgement, the same setup generation is
  deterministically requeued and resumes derivation without rerunning
  sufficiency; repeated recovery does not duplicate material access, agent
  invocation or the policy draft.
- Before material or agent I/O, the service acquires a deterministic execution
  fence and proves current fixed-service admission. No prepared handle crosses
  rollback, external material/agent work, Celery, serialization or transaction.
- After external work, it reloads and locks the full lineage, obtains and
  consumes fresh transaction-bound PREP, validates canonical output digest, and
  atomically persists one agent-derived draft plus replay/decision/provenance
  evidence and the bounded setup output transition to `policy_draft_ready`.
- Its post-agent transaction uses the shared total order for every applicable
  row: project, draft guide, latest source snapshot, setup run, sufficiency
  report, target draft policy, current approved submission policy, current
  effective policy, current pre-submit policy, then existing post-submit policy.
  Missing optional rows are checked in that sequence; no alternate acquisition
  order is allowed. Concurrency tests overlap derivation with 12F4 approval and
  12G mutations and prove convergence or stable denial without deadlock.
- Exact completed replay returns the canonical draft with zero material/agent
  calls. Pending, stale, revoked, wrong-step/task/correlation/service, changed
  output, cross-lineage and concurrent calls deny or converge with no duplicate.
- Agent-derived rows carry exact service profile/link/membership evidence, no
  fabricated grant, and cannot be edited through manual update.
- Tests instrument material loading and agent invocation. Revoked/inactive or
  wrong service/link, wrong step/task/correlation, stale generation/output,
  cross-lineage, pending replay, and completed replay all prove zero unauthorized
  material loads and zero unauthorized agent calls, with no draft mutation or
  allowed evidence. OpenAPI and import-reachability tests prove the old public
  derive endpoint is absent.
- Agent output validation preserves every non-bypassable Workstream default
  submission rule and cannot disable, replace, or weaken the fixed default
  policy/catalogue floor.

## Verification commands

```bash
cd backend
.venv/bin/ruff check app tests scripts
.venv/bin/pytest -q tests/test_authorization.py -k 'submission_artifact_policy and (derive or service or prepared)'
.venv/bin/pytest -q tests/test_projects.py -k 'submission_artifact_policy and (derive or agent or celery or stale_output)'
.venv/bin/pytest -q tests/test_ci_test_lanes.py
.venv/bin/coverage erase
.venv/bin/coverage run --source=app --concurrency=greenlet -m pytest -q tests/test_authorization.py -k 'submission_artifact_policy and (derive or service or prepared)'
.venv/bin/coverage run --source=app --concurrency=greenlet --append -m pytest -q tests/test_projects.py -k 'submission_artifact_policy and (derive or agent or celery or stale_output)'
.venv/bin/coverage report --include='app/modules/projects/submission_policy_mutation_*.py,app/**/project_setup.py,app/modules/authorization/catalogue.py,app/modules/authorization/kernel.py,app/modules/authorization/prepared.py,app/modules/authorization/runtime.py' --precision=2 --fail-under=90
.venv/bin/python scripts/api_contract_e2e.py
cd ..
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

Every selector must be non-zero; exact pushed head passes Agent Gates and full
hosted Backend. Required reviewers: all L1 tracks. Human focus: external-work
gap, fixed-service-only authority, no handle transport, and public route removal.
