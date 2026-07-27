# Chunk Contract: WS-XINT-002-02 Prepared Feature Boundaries

## Goal

Extend the existing opaque transaction-local PREP protocol once for all durable
ART boundaries using closed typed feature-owned composition contracts.

## Risk class

L1.

## Allowed files

```text
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/modules/authorization/repository.py
backend/app/interfaces/artifact_operations.py
backend/app/modules/artifacts/authorization.py
backend/tests/test_authorization.py
backend/tests/test_auth.py
backend/tests/test_artifact_authorization.py
docs/spec_authorization_service.md
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/**
```

## Not allowed

- action activation or catalogue/migration changes;
- feature repository imports in AUTH, caller callbacks, open dictionaries,
  generic service locators, or a second capability implementation;
- provider I/O, ART durable writes, or product lifecycle mutation.

## Acceptance criteria

- Define closed typed contexts and authority plans for guide ingest, submission
  preparation/create, artifact binding, checker materialization/output, review
  packet, and review evidence binding.
- Preserve exact service/session/root-transaction/action/actor/scope/key/digest
  binding, opacity, non-copyability, non-serialization, and single use.
- Human plans lock exact actor/link plus effective project grant/assignment;
  service plans lock exact profile/link and validate immutable identity, matrix,
  and availability.
- Feature modules own row loading/locking and final context composition through
  typed ports; AUTH owns no feature repository and accepts no caller assertion
  as authority.
- Initial, checker-remediation, and human-review revision contexts are closed
  variants. Checker remediation binds the final `needs_revision` CheckerRun,
  server-derived remediation source, immediate predecessor, locked task context,
  and current `allow_review`, without human-review facts. Revision binds exact
  predecessor, preparation head/digest, obligation/findings/responses,
  replacement assignment, limits, deadline, and advancement fence.
- Consume stages one final decision in the caller transaction; denial and any
  participant failure roll back with no reusable handle.
- PostgreSQL tests cover revoke/suspend, wrong action/resource/session/service,
  replay/concurrent consume, transaction replacement, stale feature facts, and
  evidence failure.
- No planned ART action becomes executable in this chunk.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_auth.py tests/test_artifact_authorization.py -q --cov=app.modules.authorization --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
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

No feature truth in AUTH, no caller-asserted authority, exact lock order, and
atomic evidence/mutation semantics.
