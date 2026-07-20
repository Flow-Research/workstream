# Chunk Contract: WS-AUTH-001-REV-CUSTODY - REV Activation Custody Transfer

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Atomically transfer all 19 current planned REV actions from historical feature
owner labels to the seven exact AUTH activation custodians in
`ACTIVATION_CUSTODY.md` without changing mappings or availability.

## Why this chunk exists

Merged XINT makes `ActionOwner` an AUTH activation custodian, while the current
19 REV rows still name historical feature owners. The metadata must be corrected
atomically without registering or activating later REV lifecycle actions.

## Risk class

L1.

## SLA

P1. No REV activation may proceed while feature owner values remain in the
closed activation-custody registry.

## Allowed files

```text
backend/app/modules/authorization/catalogue.py
backend/tests/test_authorization.py
backend/tests/test_auth.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-REV-CUSTODY.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
ActionId, PermissionId, mapping, or availability changes
registration of the four proposed lifecycle actions
database migration or audit-history rewrite
REV resource, evaluator, route, job, or lifecycle behavior changes
service identity invention or action activation
partial transfer or retained REV activation-owner enum
```

## Acceptance criteria

- Exactly the 19 canonical rows move to the seven AUTH owner values.
- All seven REV owner enum values are removed atomically.
- Catalogue counts, mappings, active/planned state, PostgreSQL audit parity,
  and denial behavior remain unchanged.
- Every REV action remains unavailable through the real kernel.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_auth.py --cov=app.modules.authorization --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
CI integrity, docs, reuse/dedup, and test delta.

## Human review focus

Verify exact 19-row custody transfer, unchanged mappings/counts, and zero
activation.

## Stop conditions

Stop if any mapping or availability must change, or if REV runtime behavior is
required.
