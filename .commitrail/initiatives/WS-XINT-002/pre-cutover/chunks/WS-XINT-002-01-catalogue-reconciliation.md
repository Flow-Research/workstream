# Chunk Contract: WS-XINT-002-01 ART Catalogue Reconciliation

## Goal

Make AUTH's closed catalogue and fixed-service matrix contain the complete v0.1
ART surface before further ART implementation, with every added action planned.

## Risk class

L1.

## Allowed files

```text
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/admin_schemas.py
backend/alembic/versions/<then-current-next>_*.py
backend/tests/test_authorization.py
backend/tests/test_auth.py
backend/tests/test_alembic.py
backend/tests/conftest.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/STATUS.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/DECISIONS.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/chunks/WS-XINT-002-01-catalogue-reconciliation.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/reviews/WS-XINT-002-01-*.md
.agent-loop/merge-intents/WS-XINT-002-01.json
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/ACTIVATION_CUSTODY.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/AUTH_HANDOFF.md
.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/AUTH_ART_HANDOFF.md
docs/spec_review_lifecycle.md
```

## Not allowed

- action activation, evaluator/resource implementation, route or asynchronous-command changes;
- new service identity, grant, generic download permission, or compatibility alias;
- ART/REV/task/submission/checker lifecycle behavior.

## Acceptance criteria

- Add planned `artifact.submission_bundle.prepare -> submission.create`.
  Add exact ActionOwner `WS-XINT-002-05A`; this is activation custody only and
  does not make the action executable.
- Add planned ActionId `artifact.review_packet.materialize` mapped to distinct
  typed PermissionId `artifact.review_packet.materialize`; add that one new
  PermissionId and prove action/permission type parity despite equal values.
  Add exact ActionOwner `WS-XINT-002-07`.
- Add planned `artifact.review_evidence.binding.create ->
  artifact.binding.create` with exact ActionOwner `WS-XINT-002-07`.
- Remove the six ActionIds and PermissionIds formed from `artifact.upload_`
  plus `session.create`, `session.read`, `item.write`, `session.seal`,
  `session.cancel`, and `session.expire`, plus scheduler expiry membership. Prove no
  route, command, audit, idempotency, test, migration-head, or documentation
  contract retains them and no compatibility/unavailable row replaces them.
- Remove ActionOwner `WS-AUTH-001-ART-04A`, whose only six rows are deleted.
  Add only ActionOwners `WS-XINT-002-05A` with cardinality one and
  `WS-XINT-002-07` with cardinality two. Preserve every other owner and
  cardinality. The closed owner enum therefore changes by `-1/+2` values.
- Starting from 76 permissions, 81 actions, 22 active, 59 planned, seven service
  identities and eleven memberships, prove the exact resulting closed counts:
  71 permissions, 78 actions, 22 active, 56 planned, seven identities and twelve
  memberships. The delta is +1/-6 permissions, +3/-6 actions, +2/-1 memberships.
- Add review packet to `workstream.artifact.materializer` and review evidence
  binding to `workstream.artifact.binding`; preserve all-pairs denial.
- Update closed enum/count/owner/static-matrix and PostgreSQL migration parity.
- Migration `0036` must descend from `0035_project_read_evidence`, take an
  access-exclusive lock on `audit_events` and a write-excluding lock on
  `authority_idempotency_records`, and refuse upgrade if any immutable audit
  row references an obsolete action/permission through `action_id`,
  `permission_id`, permission-registry target/invalidation references, or
  linked idempotency evidence. It must never delete, rewrite, or orphan that
  evidence. A clean upgrade removes the six SQL pairs/permissions and adds the
  three planned pairs/one permission atomically. Tests prove populated refusal
  leaves revision `0035` and constraints/data unchanged, then clean upgrade,
  downgrade, and re-upgrade. Downgrade refuses when any of the three new actions
  or new review-packet permission has persisted evidence.
- Historical migrations `0021`-`0023` and merged superseded chunk/review
  artifacts remain immutable historical evidence and may retain the old
  identifiers. Active runtime code, current SQL head, current specification and
  operations docs, live handoffs/chunk maps, routes/commands, and non-historical
  tests must not retain them. Focused stale proof uses an explicit allowlist for
  those immutable historical files; it may not blanket-ignore a directory.
- Update the public permission-definition response total from typed literal 76
  to 71 and prove service response validation/catalogue reads retain exact
  closed count parity.
- `test_obsolete_artifact_upload_authority_is_historical_only` must scan the
  repository for all six identifiers, fail on any active runtime/current docs/
  live plan/non-historical test reference, and name each allowed historical
  migration or immutable merged artifact explicitly. Adding a directory-wide
  exclusion or an unreviewed allowlist entry fails the chunk.
- Every new action is planned/unavailable and no existing active action changes.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_alembic.py -q --cov=app.modules.authorization --cov-report=term-missing --cov-fail-under=90)
(cd backend && .venv/bin/pytest tests/test_authorization.py::test_obsolete_artifact_upload_authority_is_historical_only -q)
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
