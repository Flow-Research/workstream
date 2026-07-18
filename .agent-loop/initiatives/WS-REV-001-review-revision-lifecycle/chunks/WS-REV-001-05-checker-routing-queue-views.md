# Chunk Contract: WS-REV-001-05

## Goal

Create one review queue entry from authoritative checker admission and expose
authorized server-selected reviewer work plus administrative inspection.

## Risk class

L1 authorization, routing, and intake integration.

## Allowed files

```text
backend/app/modules/reviews/{repository,schemas,service,router}.py
backend/app/modules/checkers/{ports,service,repository,router}.py
backend/app/modules/tasks/{models,lifecycle,service}.py only for atomic handoff/composition use
backend/app/modules/tasks/router.py only to use the explicit TaskService composition constructor
backend/app/workers/checkers.py only to use the explicit composition constructor
backend/app/composition/{__init__,review_lifecycle}.py
backend/tests/test_{reviews,checkers,tasks,app,authorization,artifacts,api_contract_e2e}.py
backend/scripts/api_contract_e2e.py
docs/operations_reviewer_workflow.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-05.json
```

## Not allowed

```text
claim or decision mutations
full reviewer-visible backlog or queue depth
direct grant queries or provider imports
caller-supplied project/resource ownership
checker outcome stored as Review
production `/api/v1` review-router registration
```

## Acceptance criteria

- `allow_review`, retained verified binding facts, task transition, queue entry,
  and audit are idempotent and cannot orphan each other.
- The admission transaction writes the exact finalized successful
  `allow_review` CheckerRun ID into the queue entry atomically. Retry,
  supersession, reconciliation, or later checker execution never silently
  changes that immutable packet anchor.
- The existing durable CheckerRun transaction invokes an injected review-owned
  admission participant from `_apply_pre_review_gate_result`; reviews never
  polls/recomputes `allow_review` or imports CheckerRepository. Review context
  uses the checker-owned typed reader, not direct checker repository access.
- Every concrete CheckerService construction in checker routes, TaskService,
  and checker execution processes is replaced by the single explicit composition assembly;
  no optional participant, fallback constructor, or runtime service locator
  exists. Import-boundary tests prohibit checker/review repository cycles.
- Every public task route replaces direct `TaskService(session)` construction
  with the same explicit TaskService assembly; route tests prove there is no
  constructor path that omits the checker admission participant.
- Version 1 routes open; later-admitted version routes preferred to the prior
  needs-revision reviewer.
- Reviewer current endpoint returns active lease, one eligible preferred/open
  offer, or none and reveals no alternative work.
- A reviewer with a global active lease in project A receives `none` when
  requesting current work for project B. The response exposes neither the
  project-A lease nor a project-B offer that global capacity makes unclaimable;
  an independent cross-project test proves both suppression and concealment.
- Admin inspection is separately authorized and distinguishes open depth from
  preferred backlog.
- Reviewer and administrative reads declare, respectively,
  `review.queue.read` and `review.queue.inspect`, use canonical project resource
  contexts, and call the centralized `AuthorizationService.require` boundary.
- Reviewer current requires the exact active independent project `reviewer`
  grant. Submitter, adjudicator, and administrative grants cannot substitute;
  no-self-review remains a separate lifecycle guard.
- This chunk supplies hidden read behavior, canonical resource composers,
  guards, surface declarations, and a feature-manifest delta while both actions
  remain planned and real-kernel requests return `action_unavailable`.
  `WS-AUTH-001-REV-05` separately integrates evaluators and activates them after
  merge; this chunk changes no activation custodian or availability.
- Merged AUTH-08 dependency tests prove successful teardown cannot commit an
  uncommitted queue/checker/review mutation, decision evidence SQL failure
  returns the stable retryable 503 with no partial state, and canonical actor
  verification timestamps retain their AUTH-defined allowed-access behavior.
  Missing or regressed proof on the chunk-start main SHA blocks this chunk.
- FIFO ordering is deterministic and preserves original age.
- Historical admission follows D13: only latest, finalized, current
  `allow_review`, artifact-ready rows are reconciled; ambiguous rows receive an
  auditable remediation state and are not queued.
- An idempotent deployment admission scan covers existing `review_pending` rows, reports
  admitted/skipped/ambiguous counts in the admin view, and classifies legacy
  revision chains lacking structured responses for explicit operator handling.
- Internal HTTP contract tests cover the routes while production OpenAPI proves
  the lifecycle router is still absent.
- Independent-session PostgreSQL barriers race queue admission against checker
  retry/supersession in both commit orders. Admission-first retains the exact
  then-current successful `allow_review` anchor after later supersession.
  Supersession-first makes stale admission fail/reselect and cannot queue an
  incomplete, denied, or non-current run. Duplicate delivery still yields one
  queue entry with one immutable anchor.
- Checker retry/supersession and review admission lock Submission, CheckerRun,
  then ReviewQueueEntry in the canonical PLAN order; tests assert the checker
  subsystem's owner order is reconciled to that shared sequence.

## Verification

```text
cd backend && pytest -q tests/test_reviews.py tests/test_checkers.py tests/test_tasks.py tests/test_app.py tests/test_authorization.py tests/test_artifacts.py tests/test_api_contract_e2e.py
cd backend && ruff check app/modules/reviews app/modules/checkers app/modules/tasks/router.py app/workers/checkers.py app/composition tests/test_reviews.py tests/test_checkers.py tests/test_tasks.py tests/test_app.py
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
cd backend && for path in 'app/modules/reviews/*' app/modules/checkers/ports.py app/modules/checkers/service.py app/modules/checkers/repository.py app/modules/checkers/router.py app/modules/tasks/models.py app/modules/tasks/lifecycle.py app/modules/tasks/service.py app/modules/tasks/router.py app/workers/checkers.py app/composition/__init__.py app/composition/review_lifecycle.py; do coverage report --include="$path" --precision=2 --fail-under=90 || exit 1; done
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, and test-delta.

## Human review focus

Atomic checker handoff, no queue leakage, routing correctness, and artifact
readiness without provider coupling.

## Stop condition

Merge, record automated memory, and stop. Do not start 06.
