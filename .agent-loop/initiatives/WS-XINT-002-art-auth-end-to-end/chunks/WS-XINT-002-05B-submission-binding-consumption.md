# Chunk Contract: WS-XINT-002-05B Submission Binding Consumption

Status: Non-executable coordination evidence. WS-ARCH-001-02 must replace this
file with split AUTH, ART, TASK, and composition contracts after 05A is
reconciled.

## Goal

Activate fresh human TASK-owned Submission creation and separate fixed
ART-owned artifact binding/admission consumption in one exactly-once
composition-owned transaction. It consumes the durable ready admission created
by 05A; it does not re-admit the work.

## Risk class

L1.

## Allowed files

None. The WS-ARCH-001-02 replacements must name exact capability-owned files,
use only `authorization.api`, `artifacts.api`, and `tasks.api` across module
boundaries, and wire concrete transaction-bound implementations only in the
application composition root.

## Not allowed

Revision obligations, checker/reviewer lifecycle changes, provider calls from
product modules, compatibility paths, or new catalogue values.
No private cross-module import, ART-created Submission, TASK-owned artifact
binding/admission mutation, or new boundary-ledger edge.

## Acceptance criteria

- Consume fresh human `submission.create` and independent fixed
  `artifact.submission.binding.create` capabilities in one transaction.
- Lock exact admission/task/assignment/context/content; TASKS creates one
  immutable Submission, ART creates one binding and consumes the admission,
  and the composition-owned transaction commits once through public ports.
- Wrong/revoked/stale/cross-resource/replayed/concurrent attempts create zero or
  exactly one complete result; denial precedes admission-state disclosure.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_submission_api.py tests/test_submission_concurrency.py tests/test_submission_history.py -q --cov=app.modules.authorization --cov=app.modules.artifacts --cov=app.modules.tasks --cov-report=term-missing --cov-fail-under=90)
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

Dual authority, module ownership, one transaction, concealment, and
exactly-once creation. This file must not start implementation.
