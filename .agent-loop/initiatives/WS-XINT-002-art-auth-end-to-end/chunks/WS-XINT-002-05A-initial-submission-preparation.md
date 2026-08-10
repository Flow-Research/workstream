# Chunk Contract: WS-XINT-002-05A Initial Submission Preparation

Status: Requires modular-boundary reconciliation under WS-ARCH-001-02 before
implementation. This existing file is not executable authority.

Entry gate: merged `WS-XINT-002-06A` pre-submit materializer activation,
complete hidden ART-04A1 through ART-04C2 evidence, and merged
WS-ARCH-001-01 boundary foundation.

## Goal

Activate one-ZIP preparation through one durable ready admission for an
initial submission using only module public APIs. AUTH owns preparation
authority; ART owns admission preparation; TASKS owns task/assignment context.

## Risk class

L1.

## Allowed files

None until WS-ARCH-001-02 replaces this file with an exact split contract.
The replacement must use `authorization.api`, `artifacts.api`, and `tasks.api`
for cross-module imports and name exact capability-owned internal files and
composition-root wiring.

## Not allowed

Submission creation/binding, revisions, reviewer behavior, upload sessions,
provider I/O before committed intent, compatibility aliases, or new catalogue values.
No private cross-module imports or new boundary-ledger edges.

## Acceptance criteria

- Require exact active assignment, task/project, no predecessor, locked
  guide/policy/checker context, request digest, operation generation, and key.
- Consume final prepared authority before capacity/put intent and provider I/O.
- Revoked, stale, cross-project, replayed, and concurrent attempts create no
  partial or duplicate ready admission; denial evidence is atomic and concealed.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_submission_bundle_admission.py tests/test_submission_concurrency.py -q --cov=app.modules.authorization --cov=app.modules.artifacts --cov-report=term-missing --cov-fail-under=90)
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

Assignment scope, final revalidation, provider-I/O ordering, and admission uniqueness.
