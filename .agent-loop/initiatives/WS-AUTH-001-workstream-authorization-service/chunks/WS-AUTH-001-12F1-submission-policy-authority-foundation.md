# Chunk Contract: WS-AUTH-001-12F1 — Submission Policy Authority Foundation

## Status and prerequisite

Proposed and inactive after merged 12E. Risk: L1. Activates no action.

## Goal

Install the exact submission-policy PREP bindings, replay/provenance schema, and
flush-only orchestration contracts required by later 12F children.

## Allowed files

```text
backend/app/modules/projects/models.py
backend/app/modules/projects/submission_policy_mutation_service.py
backend/app/modules/projects/submission_policy_mutation_repository.py
backend/app/modules/projects/repository.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/alembic/versions/<then-current-next>_submission_policy_authority.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/tests/test_alembic.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed

Action activation, route/Celery cutover, agent/material calls, product-policy
mutation, post-submit behavior, or edits to historical migrations.

## Required design

- Add a dedicated 12F PREP binding/final matcher for exact project, guide and
  version, source snapshot ID/hash, target and execution kind, policy
  ID/version/status/hash, setup run/generation/task/correlation identity,
  stale-output digest, effective/pre-submit output digests, operation/request
  digest, identity link, matched grant-or-service membership, session/root
  transaction, and final resource-context digest.
- The approval binding also carries compiler and bundle schema versions,
  immutable default-catalogue ID/version/schema and manifest SHA-256, ordered
  entry identity/configuration hashes, disabled-catalogue startup-config digest
  and IDs, compiled bundle hash, and downstream effective-plan hash when one is
  produced. Replay and local provenance preserve the same canonical facts.
- Add one append-only replay ledger with UUID key, actor/link, action, request
  and resource digests, operation, lineage selectors, pending/committed state,
  bounded response, and exact target IDs. Human replay namespace is
  `(actor_profile_id, idempotency_key)`; service derivation uses the fixed
  service profile plus deterministic setup task/correlation identity.
- Add nullable local provenance columns and closed constraints for draft
  policy, effective policy, and pre-submit policy. Historical bootstrap rows
  remain readable and are never backfilled or rewritten. Newly authorized rows
  require complete actor/link/grant-or-service/scope/action/decision evidence.
- The new orchestrator is flush-only. Route/Celery owners commit or roll back;
  no wrapper calls a legacy self-committing mutation method.
- Reuse the merged `PreparedAuthorizationService`/runtime context and the 12E
  reserve/find/complete replay plus advisory-fence conventions. A dedicated
  repository may express submission-policy lineage, but it must not invent a
  second authorization protocol, replay state machine, UUID parser, or locking
  protocol; shared dependencies are extracted when their semantics are exact.
- The catalogue remains planned and database/runtime parity remains exact.

## Acceptance and proof

- Wrong action/link/session/transaction/resource/execution kind and copied or
  replayed handles deny.
- Replay constraints reject changed, pending, cross-action, and identity-link
  substitution; committed replay requires fresh reauthorization.
- Fault injection proves product rows, replay completion, allowed decision
  evidence, and local provenance roll back together.
- Seeded historical rows survive upgrade unchanged; populated authorized
  evidence blocks downgrade, empty downgrade succeeds, and re-upgrade restores
  the schema. Migration allocation is taken only from then-current main.
- No action becomes active and no route behavior changes.

## Verification commands

```bash
cd backend
.venv/bin/ruff check app tests scripts
.venv/bin/pytest -q tests/test_authorization.py -k 'submission_artifact_policy and (prepared or catalogue or service)'
.venv/bin/pytest -q tests/test_projects.py -k 'submission_artifact_policy and (authority or replay or provenance)'
.venv/bin/pytest -q tests/test_alembic.py -k 'submission_policy_authority'
.venv/bin/pytest -q tests/test_ci_test_lanes.py
.venv/bin/coverage erase
.venv/bin/coverage run --source=app.modules.projects,app.modules.authorization --concurrency=greenlet -m pytest -q tests/test_authorization.py -k 'submission_artifact_policy and (prepared or catalogue)'
.venv/bin/coverage run --source=app.modules.projects,app.modules.authorization --concurrency=greenlet --append -m pytest -q tests/test_projects.py -k 'submission_artifact_policy and (authority or replay or provenance)'
.venv/bin/coverage report --include='app/modules/projects/submission_policy_mutation_*.py,app/modules/authorization/kernel.py,app/modules/authorization/prepared.py,app/modules/authorization/runtime.py' --precision=2 --fail-under=90
.venv/bin/python scripts/run_test_lanes.py --collect-only --metadata-dir /tmp/ws-auth-12f1-lanes --summary-json /tmp/ws-auth-12f1-lanes.json
cd ..
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

Every selector must collect a non-zero child-owned test count. The exact pushed
head must pass Agent Gates and the full hosted Backend matrix/aggregate coverage.

## Required reviewers and human focus

All L1 tracks. Human focus: zero activation, exact binding equality, nullable
historical provenance, append-only replay, and flush-only transaction ownership.
