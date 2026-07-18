# Chunk Contract: WS-REV-001-06

## Goal

Implement atomic claim, reviewer release, preferred decline, preference expiry,
lease expiry, and lazy recovery with one global active reviewer lease.

## Risk class

L1 authorization and concurrency.

## Allowed files

```text
backend/app/modules/reviews/{repository,schemas,service,router}.py
backend/app/composition/review_lifecycle.py only to install the exact merged CON lease-freeze capability
backend/app/workers/{celery_app,reviews}.py
backend/app/core/config.py only for bounded timer settings
backend/tests/test_{reviews,authorization,artifacts,config}.py
docs/operations_queue_policy.md
docs/operations_reviewer_workflow.md only for timer/configuration rollout
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-06.json
```

## Not allowed

```text
review decision or finding writes
admin override or force release
new authorization or artifact semantics
remote provider call while queue/lease rows are locked
reviewer capacity greater than one
production `/api/v1` review-router registration
```

## Acceptance criteria

- A preliminary request-scoped authority and concealment gate precedes bounded
  evidence preflight outside row locks. It exposes no packet or binding facts.
  The final claim transaction then follows AUTH authority lock -> REV selected
  queue and canonical packet-row locks -> final fact recomposition -> one AUTH
  evaluation -> lease/manifest/participant flush -> one caller commit. It
  revalidates the preflight identity without treating preflight as authority.
- Claim eligibility is re-evaluated inside the transaction before any private
  context is disclosed: canonical active human actor, exact active independent
  project `reviewer` grant,
  required permissions, project match, no self-review against submitter,
  creator, or current/prior task assignees, eligible queue state, and no global
  active lease. Cross-project, suspended/revoked, self, creator, and assigned
  reviewer negatives create no lease or artifact mutation.
- The claim transaction reselects and locks the reviewer's canonical
  preferred-first/FIFO current offer and requires any submitted queue ID to
  match it. Arbitrary, guessed, stale, lower-priority open, and concurrently
  superseded IDs fail without disclosure or mutation.
- Concurrent claims create exactly one lease per entry and per reviewer.
- Lease `ContributionPolicyVersion` freeze required by WS-CON is present and is
  resolved for the newly created lease through the merged WS-CON capability.
  It is independent of decision outcome and any forward/backward Project Guide
  rebase. A later lease may freeze a newer reviewer contribution-policy version, but a
  prior lease is never rewritten.
- Claim creates one immutable `ReviewPacketManifest` atomically with the lease
  from locked queue, Submission/version, admitting CheckerRun/results, locked
  context, response-evidence relations, and ART binding IDs. Manifest creation
  failure rolls back the lease and AuthorizationDecision.
- Release, decline, preference expiry, and lease expiry use distinct immutable
  audit facts and preserve `first_queued_at`.
- Claim, release, decline, preference expiry, and lease expiry declare,
  respectively, `review.claim`, `review.release`,
  `review.decline_preference`, `review.preference_expiry.run`, and
  `review.lease_expiry.run`. Every mutation uses AUTH's prepared protocol:
  authority first; an opaque, non-Pydantic, single-use handle binds exact
  session, ActionId, actor-reference kind and ID, idempotency key, and canonical
  request digest; REV locks/recomposes final facts and calls AUTH; AUTH validates
  every binding/current authority, consumes the handle once, evaluates once, and
  stages evidence before the first feature mutation; then participants flush.
  Wrong-session/action/actor/request binding, serialized, forged, or
  caller-constructed attempts against an unconsumed handle stage no
  AuthorizationDecision/evidence, preserve the legitimate handle, and permit its
  later exact first use. Stale/already-consumed and concurrent duplicate attempts
  remain invalid and stage no new evidence or feature state. Current-authority or policy denial after
  valid consumption leaves no lease/routing or feature audit/outbox effect. The
  request route or service command rolls back the dirty transaction; AUTH
  restages the unchanged bounded denial evidence in a clean transaction; and the
  request route or service command commits that evidence once. Evidence,
  participant, cancellation, commit, or denial-restaging failure leaves no
  partial feature state or authority evidence.
- Preference expiry runs only as fixed service
  `workstream.review.preference_expiry`; lease expiry runs only as
  `workstream.review.lease_expiry`. Each requires its exact static action row,
  an AUTH-09A-compatible enum/constraint/matrix extension, AUTH-09B-provisioned
  service ActorProfile/link, AUTH-09E admission, and cross-service/human-path
  denial. Neither is one of AUTH-09A's seven ART identities or borrows Operator
  or reviewer authority.
- Lease expiry clears stickiness and uses PostgreSQL time.
- Sweeps are idempotent and lazy recovery invokes the same transition service.
- Expected uniqueness races map to stable 409 codes, never 500.
- Claim, release, decline, preference expiry, and lease expiry follow the
  canonical lock order; real-Postgres tests use independent sessions/barriers,
  both operation permutations, and rollback fault injection.
- Services and internal route tests exist, but production OpenAPI remains free
  of every lifecycle mutation through chunk 09B.
- All five actions remain planned while this chunk supplies hidden behavior,
  composers, guards, static-service requirements, and a feature-manifest delta.
  `WS-AUTH-001-REV-06` activates them only after the chunk merges; route exposure
  still waits for REV-13. The exact preference-expiry and lease-expiry service
  identity extensions build on AUTH-09A and are separately provisioned from the
  published manifest through AUTH-09B/09E; generic admission creates no catch-all
  review service.
- Operator docs enumerate every timer environment variable, bounded default,
  Celery beat/execution command, lazy-recovery behavior, alert, and rollout rule.
- Timer jobs reuse `run_async_task`, the existing fresh engine/session disposal
  pattern, stable Celery task IDs, and `sync_task_settings`; no second async
  bridge, session factory helper, queue configuration, or fallback execution
  path is introduced.

## Verification

```text
cd backend && pytest -q tests/test_reviews.py tests/test_authorization.py tests/test_artifacts.py tests/test_config.py
cd backend && ruff check app/modules/reviews app/workers/reviews.py tests/test_reviews.py
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
cd backend && for path in 'app/modules/reviews/*' app/composition/review_lifecycle.py app/workers/reviews.py app/workers/celery_app.py app/core/config.py; do coverage report --include="$path" --precision=2 --fail-under=90 || exit 1; done
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, and test-delta.

## Human review focus

Database-time races, lock ordering, preflight freshness, compensation freeze,
and retry-safe job behavior.

## Stop condition

Merge, record automated memory, and stop. Do not start 07.
