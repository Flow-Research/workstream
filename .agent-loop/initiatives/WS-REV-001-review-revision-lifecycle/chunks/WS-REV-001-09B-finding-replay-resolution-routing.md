# Chunk Contract: WS-REV-001-09B - Finding Replay, Resolution, And Preferred Return Routing

## Goal

Complete prior-finding replay, immutable resolution requirements, checker
readmission, and preferred return routing for a prepared revision.

## Risk class

L1 immutable history, contributor fairness, and routing.

## Allowed files

```text
backend/app/modules/reviews/{repository,schemas,service,router}.py
backend/tests/test_{reviews,tasks,checkers,authorization,artifacts}.py
docs/operations_revision_replay.md
docs/template_revision_replay.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-09B.json
```

## Not allowed

```text
mutation of prior submission, review, finding, response, or resolution
new revision preparation policy
automatic reject at limit/deadline
production `/api/v1` review-router registration
```

## Acceptance criteria

- Human-origin checker admission requires one immutable response and any
  policy-required verified evidence for every unresolved blocking finding from
  the immediate predecessor Review. Checker-origin remediation requires no fake
  ReviewFinding response or resolution and instead revalidates its exact
  contributor-safe CheckerRun failure lineage.
- The review-owned admission participant established in chunk 05 extends its
  behavior inside the existing durable checker transaction; no checker/task
  repository import, polling path, or second admission service is added.
- Human-origin admission creates at most one queue entry preferred to the prior reviewer,
  preserves original queue age across preference expiry/decline/invalidation,
  and preserves chain identity after takeover. Checker-origin admission creates
  one ordinary open entry with no fabricated preferred reviewer.
- A later Review records exactly one required immutable FindingResolution per
  prior blocking finding and cannot accept while any remains unresolved.
- Missing/duplicate/cross-chain responses or resolutions, quarantined evidence,
  and uncertain artifact state fail closed without queue, Review, CON, or task
  side effects.
- Prior reviewer suspension, grant loss, newly discovered self-review,
  corrected attribution, or policy ineligibility invalidates preference
  immediately, preserves age, and emits bounded audit evidence.
- Production OpenAPI remains free of lifecycle routes.

## Verification

```text
cd backend && pytest -q tests/test_reviews.py tests/test_tasks.py tests/test_checkers.py tests/test_authorization.py tests/test_artifacts.py
cd backend && ruff check app/modules/reviews app/modules/checkers app/modules/tasks tests/test_reviews.py
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
cd backend && coverage report --include='app/modules/reviews/*' --precision=2 --fail-under=90
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, and test-delta.

## Human review focus

Complete blocking-finding replay, preferred-return fairness, invalidation causes,
and no synthetic decision or history mutation.

## Stop condition

Merge, record automated memory, and stop. Do not start 10.
