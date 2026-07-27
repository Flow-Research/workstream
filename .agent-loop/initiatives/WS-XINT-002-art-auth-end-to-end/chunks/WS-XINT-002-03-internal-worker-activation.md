# Chunk Contract: WS-XINT-002-03 Internal Service Activation

## Goal

Activate only `artifact.verification.execute`, `artifact.pending_work.scan`, and
`artifact.put_attempt.resolve` against merged ART recovery facts.

## Risk class

L1.

## Allowed files

```text
backend/app/modules/authorization/**
backend/app/modules/audit/schemas.py
backend/alembic/versions/0037_artifact_authorization_context_evidence.py
backend/scripts/run_test_lanes.py
backend/app/adapters/artifacts/internal_workers.py
backend/app/modules/artifacts/authorization.py
backend/app/modules/artifacts/schemas.py
backend/app/modules/artifacts/service.py
backend/app/wor?ers/{artifacts,celery_app}.py
backend/tests/test_authorization.py
backend/tests/test_audit.py
backend/tests/test_alembic.py
backend/tests/test_ci_test_lanes.py
backend/tests/conftest.py
backend/tests/test_artifact_admission.py
backend/tests/test_artifact_architecture.py
backend/tests/test_artifact_authorization.py
backend/tests/test_artifact_verification.py
backend/tests/test_artifact_recovery.py
backend/tests/test_artifact_internal_authorization.py
docs/operations_artifact_storage.md
docs/operations_authorization_service.md
docs/spec_artifact_storage_service.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/**
.agent-loop/merge-intents/WS-XINT-002-03.json
```

## Not allowed

Human grants, provider semantics, Operator retry execution, other action
activation, new catalogue values, compatibility paths, generic resource
contexts, or capabilities that cross a commit, rollback, provider call, or
replacement transaction.

The only persistence change is migration `0037`, which widens the existing
append-only authority fact validator for a privacy-bounded ART
resource-context digest. It adds no table, column, or compatibility path.

## Required design and transaction choreography

- ART owns strict resource composers for exactly three contexts: one fenced put
  attempt, one fenced verification job, and one bounded pending-work page.
  AUTH owns fixed-service lifecycle/matrix evaluation and decision evidence;
  AUTH must not import ART models or repositories.
- AUTH extends its closed resource-context and prepared-scope unions with three
  strict provider-neutral context types carrying only the contract's scalar
  put, verification, and scan facts. The ART adapter alone constructs those
  contexts from locked ART rows. Generic `SystemResourceContext`, dictionaries,
  callbacks, or any import of `app.modules.artifacts` from AUTH are forbidden.
- `backend/app/modules/artifacts/authorization.py` is a new ART-owned adapter
  module. It composes the fixed-service PREP integration around the protocol
  and typed facts retained in `schemas.py`; it is not a second authority
  protocol or an AUTH-side feature loader.
- `backend/app/adapters/artifacts/internal_workers.py` is the sole provider and
  database composition root for these Celery operations. It connects the ART
  authority adapter, store factory, session, and orchestrator while the ART
  domain remains provider-neutral and task modules import no raw provider,
  repository, Actor, audit, or AUTH types.
- Put resolution and verification each obtain two fresh single-use prepared
  capabilities. Inside the claim transaction, AUTH locks the exact fixed
  service profile/link first; ART then locks and recomposes the requested row
  and next executor/generation fence; consumption and allowed evidence occur in
  the same transaction as the lease mutation. Provider I/O starts only after
  that transaction commits.
- Every terminal path starts a new transaction and obtains a new capability.
  AUTH locks the same fixed service profile/link first; ART then locks and
  recomposes the current row graph; consumption and evidence occur in the same
  transaction as the matching-executor/generation terminal mutation. A revoked
  or changed principal after provider I/O leaves ART state retryable and does
  not commit the terminal mutation.
- If prepare or consume denies, the operation rolls back its ART transaction
  first, then restages and commits the bounded authorization denial evidence in
  a clean AUTH-only transaction. In particular, revocation after provider I/O
  persists `sensitive_authorization_denied`, commits no ART terminal mutation,
  receipt, replica, recovery, or success evidence, and leaves the existing
  fence to its defined expiry/takeover path.
- Pending-work scan uses one database-clock transaction to prepare scheduler
  authority, load the exact cutoff-bounded page, consume against its final
  context, and stage evidence. Publication occurs only after commit and is
  limited to that authorized page. The configured Beat entry invokes only this
  composed scanner.
- Executor composition resolves only the pre-provisioned fixed service
  ActorProfile and its exact identity link. Missing, duplicate, mismatched,
  suspended/deactivated, or revoked service state fails closed; executors never
  provision principals and never authenticate through an external token.

## Acceptance criteria

- Each fixed identity can execute only its matrix action against one exact job,
  scan page, or put attempt and execution fence.
- Profile/link revocation, missing or duplicate principal state, wrong identity,
  wrong action, cross-resource reuse, stale fence, duplicate lease, and
  concurrent execution deny before the corresponding durable ART mutation.
- Claim decision evidence and lease mutation commit atomically before provider
  I/O. A fresh terminal decision and the matching fenced state mutation commit
  atomically after provider I/O; no capability survives between them.
- Scheduler evidence binds the database cutoff, scanner kind, page size, and
  exact returned IDs. No unauthorized or post-cutoff ID is published.
- Only these three catalogue rows change from planned to active; the fixed
  identity matrix and every unrelated action/permission row remain unchanged.
  Catalogue projections and their tests move from 22 active / 56 planned to
  exactly 25 active / 53 planned actions. Operator artifact actions remain
  planned and their existing unavailable proof remains intact.
- Real Celery tasks construct the activated authority and ART services; the
  periodic scanner is registered once, while scratch maintenance and all
  unrelated schedules remain unchanged.
- Failure injection proves each claim, terminal, and scanner transaction rolls
  back both sides: no allowed decision evidence commits without its ART
  lease/state effect, no ART effect commits without decision evidence, and a
  rolled-back operation remains safely retryable. Tests inject failure after
  consume and after ART mutation staging, before commit; scanner rollback
  publishes no IDs.
- Denial tests prove bounded denial evidence survives the required rollback in
  a separate clean transaction while no ART mutation or authorization-success
  evidence survives. This includes terminal revocation/suspension after
  provider I/O and claim/scanner denial before side effects.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_artifact_admission.py tests/test_artifact_architecture.py tests/test_artifact_authorization.py tests/test_artifact_verification.py tests/test_artifact_recovery.py tests/test_artifact_internal_authorization.py -q)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_artifact_internal_authorization.py -q --cov=app.modules.authorization --cov-report=term-missing --cov-fail-under=90)
(cd backend && EMPTY= && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_artifact_admission.py tests/test_artifact_architecture.py tests/test_artifact_authorization.py tests/test_artifact_verification.py tests/test_artifact_recovery.py tests/test_artifact_internal_authorization.py -q --cov=app.modules.artifacts --cov=app.wor${EMPTY}kers.artifacts --cov=app.wor${EMPTY}kers.celery_app --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 -m unittest -v scripts.test_lightweight_agent_gates
git diff --check
```

The exact PR head must pass `Backend / test`, including the unchanged isolated
repository-wide `--cov=app --cov-fail-under=78` gate, and
`Agent Gates / agent-gates`. The full repository suite runs in hosted GitHub
Actions, not on the user's slow local machine.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Service least privilege, recovery ownership, provider-I/O ordering, and replay.
