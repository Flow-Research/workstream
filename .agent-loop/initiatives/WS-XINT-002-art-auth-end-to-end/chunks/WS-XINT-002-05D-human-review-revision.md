# Chunk Contract: WS-XINT-002-05D Human-Review Revision Submission

## Goal

Activate the revision variant against one exact durable `needs_revision` obligation.

## Risk class

L1.

## Allowed files

```text
backend/app/modules/authorization/**
backend/app/modules/artifacts/authorization.py
backend/app/modules/artifacts/service.py
backend/app/modules/tasks/**
backend/app/modules/reviews/**
backend/tests/test_authorization.py
backend/tests/test_submission_concurrency.py
backend/tests/test_submission_history.py
backend/tests/test_review_revision.py
docs/spec_authorization_service.md
docs/spec_review_lifecycle.md
docs/reference_specs/WS-REV-001-review-lifecycle-specification.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/**
```

## Not allowed

Review decision semantics, reviewer-created revisions, checker remediation,
initial-submission behavior changes, provider redesign, or new catalogue values.

## Acceptance criteria

- Lock exact predecessor, active preparation head/digest, obligation/round,
  required finding responses/evidence, current/replacement assignment, limit,
  deadline, and predecessor advancement fence.
- Use the same public prepare/create actions with a closed revision context.
- Deny stale/missing/expired/over-limit/invalid-replacement/revoked/replayed or
  concurrent attempts. The durable `needs_revision` obligation remains open
  through preparation, storage, and retries. Only the transaction that creates
  the immutable successor and binding may atomically close that obligation and
  consume the exact admission; failure leaves it open without changing history.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_submission_concurrency.py tests/test_submission_history.py tests/test_review_revision.py -q --cov=app.modules.authorization --cov=app.modules.artifacts --cov=app.modules.tasks --cov=app.modules.reviews --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

The exact PR head must pass `Backend / test` and
`Agent Gates / agent-gates`, preserving the 78 percent global and 90 percent
materially changed subsystem coverage floors.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Exact obligation/predecessor fencing, replacement assignment, and immutable history.
