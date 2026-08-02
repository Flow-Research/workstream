# Chunk Contract: WS-XINT-002-07A — Reviewer Artifact Activation

## Goal

Activate exact lease-scoped packet materialization only.

## Boundary

This activates `artifact.review_packet.materialize` for the fixed reviewer-reader
service after ART-07A exists. Human review actions remain with XINT-003.
`artifact.review_evidence.binding.create` remains planned and unavailable; the
approved v0.1 reviewer workflow records a decision plus note/findings and does
not upload a reviewer revision artifact.

## Acceptance criteria

- Packet materialization binds reviewer reference, active lease, packet manifest, Submission, checker, guide/policy, verified content, session, transaction, request, and decision evidence.
- Reviewer evidence binding and contributor-response artifacts remain denied.
- Wrong, stale, revoked, replayed, copied, or cross-resource facts deny before byte disclosure or durable mutation.
- Human and fixed-service evidence commits atomically with the protected REV/ART operation. Prepared handles never enter a job payload.

## Stop

Do not add response-slot evaluation or activate human REV actions.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_review_artifacts.py tests/test_artifact_materialization.py -q --cov=app.modules.authorization --cov=app.modules.artifacts --cov=app.modules.reviews --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

Tests must cover stale/expired lease, revoked reviewer/link, wrong fixed service,
copied/replayed handle, cross-Submission request, and denial before byte
disclosure. The exact PR head must pass hosted `Backend / test` and
`Agent Gates / agent-gates` without lowering the 78/90 coverage floors.

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
reuse/dedup, test delta, and docs.
