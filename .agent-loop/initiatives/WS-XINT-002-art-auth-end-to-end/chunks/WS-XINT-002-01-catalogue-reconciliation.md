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
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/STATUS.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/chunks/WS-XINT-002-01-catalogue-reconciliation.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/reviews/WS-XINT-002-01-*.md
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
- Add planned ActionId `artifact.review_packet.materialize` mapped to distinct
  typed PermissionId `artifact.review_packet.materialize`; add that one new
  PermissionId and prove action/permission type parity despite equal values.
- Add planned `artifact.review_evidence.binding.create ->
  artifact.binding.create`.
- Remove ActionIds and PermissionIds `artifact.upload_session.create`,
  `artifact.upload_session.read`, `artifact.upload_item.write`,
  `artifact.upload_session.seal`, `artifact.upload_session.cancel`, and
  `artifact.upload_session.expire`, plus scheduler expiry membership. Prove no
  route, command, audit, idempotency, test, migration-head, or documentation
  contract retains them and no compatibility/unavailable row replaces them.
- Starting from 76 permissions, 81 actions, 22 active, 59 planned, seven service
  identities and eleven memberships, prove the exact resulting closed counts:
  71 permissions, 78 actions, 22 active, 56 planned, seven identities and twelve
  memberships. The delta is +1/-6 permissions, +3/-6 actions, +2/-1 memberships.
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
