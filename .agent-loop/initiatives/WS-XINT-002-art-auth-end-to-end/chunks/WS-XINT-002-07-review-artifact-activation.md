# Split Record: WS-XINT-002-07 Review Artifact Authorization

## Status

Superseded before implementation by `WS-XINT-002-07A` and
`WS-XINT-002-07B`. This record is not an activation path.

## Split invariant

07A is the only approved v0.1 availability transition and activates packet
materialization only. `artifact.review_evidence.binding.create` remains planned
and unavailable. 07B is reserved pending a separately approved REV-owned
evidence-upload intent. Human REV actions stay with XINT-003; shared submission
actions stay with XINT-002-05D.

Everything below is historical combined design input. It is retained for
provenance and is not executable as one chunk or approved v0.1 behavior.

## Risk class

L1.

## Allowed files

```text
backend/app/modules/authorization/**
backend/app/modules/artifacts/authorization.py
backend/app/modules/artifacts/service.py
backend/app/modules/reviews/**
backend/tests/test_authorization.py
backend/tests/test_review_artifacts.py
backend/tests/test_review_revision.py
docs/spec_authorization_service.md
docs/spec_artifact_storage_service.md
docs/spec_review_lifecycle.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/**
```

## Not allowed

Review lifecycle redesign, generic downloads, reviewer authority for artifact
binding, service authority for review decisions, or new catalogue values.

## Acceptance criteria

- Human `review.context.read` independently authorizes the exact reviewer actor
  and link, active lease/generation/deadline, exact Submission, guide/policy/
  checker context, request digest, and key. Fixed
  `artifact.review_packet.materialize` independently permits byte access.
- Packet facts bind reviewer actor/link reference, lease, Submission, checker
  run, guide/policy context, and immutable binding IDs.
- Expiry, release, reassignment, revocation, version advancement, digest/size
  mismatch, replay, materializer-only, wrong-reviewer, and cross-submission
  access deny and disclose no bytes.
- Finding evidence binds exact review/lease/finding slot, Submission, verified
  commitment, and guide/policy context. Response evidence binds exact assigned
  contributor, response/obligation slot, revision round, predecessor/current
  Submission, preparation head/digest, verified commitment, and supersession
  denial. Both require their existing human actions plus separate
  `artifact.review_evidence.binding.create` service authority.
- Human and service evidence plus protected review/evidence mutation commit or
  roll back together. No service can decide review or create Submission.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_review_artifacts.py tests/test_review_revision.py -q --cov=app.modules.authorization --cov=app.modules.artifacts --cov=app.modules.reviews --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

The exact PR head must pass `Backend / test` and `Agent Gates / agent-gates`.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Lease scope, version freshness, dual authority, and absence of generic byte access.
