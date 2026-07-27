# Chunk Contract: WS-XINT-002-05C Checker Remediation Submission

## Goal

Activate the submission variant rooted in one exact final `needs_revision` CheckerRun.

## Risk class

L1.

## Allowed files

```text
backend/app/modules/authorization/**
backend/app/modules/artifacts/authorization.py
backend/app/modules/artifacts/service.py
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/tests/test_authorization.py
backend/tests/test_submission_concurrency.py
backend/tests/test_submission_history.py
backend/tests/test_checkers.py
docs/spec_authorization_service.md
docs/spec_review_lifecycle.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/**
```

## Not allowed

ReviewFinding responses, revision preparation/deadline/round consumption,
reviewer contribution, synthetic human actors, review decision changes, or new catalogue values.

## Acceptance criteria

- Bind exact final CheckerRun, server-derived immutable
  `remediation_source_checker_run_id`, immediate same-task predecessor, existing
  locked task context, assignment, and current `allow_review` before routing.
- Use the same prepare/create actions and dual binding transaction as 05A/05B.
- Reject stale/non-final/wrong-task CheckerRun, predecessor advancement,
  revocation, replay, and concurrency; success returns to open routing.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_submission_concurrency.py tests/test_submission_history.py tests/test_checkers.py -q --cov=app.modules.authorization --cov=app.modules.artifacts --cov=app.modules.tasks --cov=app.modules.checkers --cov-report=term-missing --cov-fail-under=90)
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

Checker provenance, absence of human-review facts, and open routing.
