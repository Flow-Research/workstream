# Chunk Contract: WS-XINT-002-01 ART Catalogue Reconciliation

## Goal

Make AUTH's closed catalogue and fixed-service matrix contain the complete v0.1
ART surface before further ART implementation, with every added action planned.

## Risk class

L1.

## Allowed files

```text
backend/app/modules/authorization/catalogue.py
backend/alembic/versions/<then-current-next>_*.py
backend/tests/test_authorization.py
backend/tests/test_alembic.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/**
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/ACTIVATION_CUSTODY.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/AUTH_HANDOFF.md
```

## Not allowed

- action activation, evaluator/resource implementation, route or asynchronous-command changes;
- new service identity, grant, generic download permission, or compatibility alias;
- ART/REV/task/submission/checker lifecycle behavior.

## Acceptance criteria

- Add planned `artifact.submission_bundle.prepare -> submission.create`.
- Add planned `artifact.review_packet.materialize ->
  artifact.review_packet.materialize` and its one new PermissionId.
- Add planned `artifact.review_evidence.binding.create ->
  artifact.binding.create`.
- Remove all six upload-session ActionIds and PermissionIds and scheduler expiry
  membership; prove no route, command, audit, idempotency, test, migration-head,
  or documentation contract retains them.
- Add review packet to `workstream.artifact.materializer` and review evidence
  binding to `workstream.artifact.binding`; preserve all-pairs denial.
- Update closed enum/count/owner/static-matrix and PostgreSQL migration parity.
- Every new action is planned/unavailable and no existing active action changes.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_alembic.py -q --cov=app.modules.authorization --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

The exact PR head must pass GitHub checks `Backend / test` and
`Agent Gates / agent-gates`, preserving the 78 percent global and 90 percent
materially changed subsystem coverage floors.

Full backend coverage runs in GitHub Actions.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Exact removals/additions, mapping correctness, least-privilege matrix, and zero
availability changes.
