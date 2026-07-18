# Chunk Contract: WS-REV-001-12

## Goal

Deliver deterministic review snapshot projection, notification events,
artifact-reference reconciliation, and bounded operational observability.

## Risk class

L1 asynchronous delivery, privacy, and operations.

## Allowed files

```text
backend/app/modules/reviews/{ports,repository,schemas,service,projection}.py
backend/app/workers/{celery_app,reviews}.py
backend/app/core/config.py only for bounded job settings
backend/tests/test_{reviews,artifacts,audit,config}.py
docs/operations_reviewer_workflow.md
docs/operations_operator_workflow.md
docs/operations_queue_policy.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-12.json
```

## Not allowed

```text
remote storage call in decision transaction
projection as canonical Review truth
unbounded reviewer IDs or finding text in public metric labels/logs
notification provider implementation beyond existing adapter convention
review decision changes on projection failure
production `/api/v1` review-router registration
```

## Acceptance criteria

- Projection bytes are deterministic for Review ID and schema version.
- Every projection represents the immutable Review and submitted
  finding and resolution history for its decision. An accept projection includes
  bounded FinalAcceptance identity, source-Review identity, and acceptance time;
  `needs_revision` and `reject` projections contain no inferred or synthetic
  FinalAcceptance. Projection content never becomes the acceptance source.
- Same operation/bytes replay one logical receipt; changed bytes conflict.
- Projection-job retry/dead-letter/reconciliation changes only delivery status.
- The shared outbox dispatcher remains the sole event claimant and owner of
  attempt, retry, dead-letter, and delivery status. Reviews registers only a
  typed deterministic projection handler and relies on ART receipts; no review
  polling loop, attempt table, or dead-letter ledger is created.
- Search/projection reads are reauthorized through Workstream.
- Artifact-reference reconciliation declares
  `review.artifact_reference.reconcile`; an authorized projection rebuild
  declares `review.projection.rebuild`. Artifact-reference reconciliation runs
  only as `workstream.review.artifact_reference_reconciliation`; projection
  rebuild runs only as `workstream.review.projection`. Each requires its exact
  static ActionId row, an AUTH-09A-compatible identity/matrix extension,
  AUTH-09B-provisioned ActorProfile/link, AUTH-09E admission, AUTH
  prepare for the mutation and final REV facts, followed by AUTH-owned exact
  binding/current-authority validation, single consumption, evaluation, and
  evidence staging. The opaque, non-Pydantic, single-use handle binds exact
  session, ActionId, service actor-reference kind and ID, idempotency key, and
  canonical request digest. Wrong-binding, serialized, forged, or
  caller-constructed attempts against an unconsumed handle fail before feature
  mutation, stage no AuthorizationDecision/evidence, preserve the legitimate
  handle, and permit its later exact first use. Stale/already-consumed and
  concurrent duplicate attempts remain invalid and stage no new state. Current-authority
  or policy denial after valid consumption follows AUTH's clean denial-evidence
  protocol. Human Operator or reviewer authority cannot substitute.
  AUTH-09A's seven-identity ART set contains neither identity. Generic AUTH-09E
  admission creates neither identity; AUTH provisions each exact identity and
  static membership only from this reviewed service manifest.
- Artifact relation reconciliation covers verification, project/task scope,
  missing projection, receipt mismatch, uncertainty, and unavailable content
  through ART-owned typed facts without importing ART repositories, invoking v1
  retain/release, or editing canonical history.
- Required queue, lease, decision, authorization, evidence, projection, and lag
  metrics exist with bounded cardinality.
- Reviews exposes a typed, same-session `ReviewLifecycleDrainObservationPort`
  that returns server-derived active-lease and review-maintenance counts under
  canonical review locks. It is read-only, never commits, advances no lifecycle
  phase, imports no lifecycle-control type, and is named in chunk 12 evidence so
  12A can consume it through composition.
- Administrative read models include open/preferred depth, oldest preferred
  age, approaching-expiry leases, expired/released/invalidation counts, and
  bounded turnaround distributions.
- Notification events explicitly cover preference nearing expiry, lease nearing
  expiry, lease expired, preferred routing, decisions, and every authority
  invalidation cause without coupling lifecycle to a delivery provider.
- Audit, shared outbox, dead-letter, alerts, errors, logs, and metrics retain
  only bounded typed identifiers/reasons and never finding text, private
  artifact metadata, signed access, provider paths, or secrets.
- Production OpenAPI remains free of lifecycle routes.
- Operator docs enumerate every projection/notification job variable,
  bounded default, schedule/execution command, retry/dead-letter alert, rollout,
  drain, and rollback behavior in the same chunk.
- Projection handlers reuse `run_async_task`, fresh execution engine/session
  disposal, stable task IDs, and `sync_task_settings`; no second async bridge,
  session factory, or queue helper is introduced.
- This chunk supplies hidden behavior, service resource facts, and feature-
  manifest deltas while both review actions remain planned. AUTH separately
  activates them through `WS-AUTH-001-REV-12` after merge; product release waits
  for REV-13.

## Verification

```text
cd backend && pytest -q tests/test_reviews.py tests/test_artifacts.py tests/test_audit.py tests/test_config.py
cd backend && ruff check app/modules/reviews app/workers/reviews.py tests/test_reviews.py
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
cd backend && for path in 'app/modules/reviews/*' app/workers/reviews.py app/workers/celery_app.py app/core/config.py; do coverage report --include="$path" --precision=2 --fail-under=90 || exit 1; done
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, and test-delta.

## Human review focus

Canonical/projection separation, deterministic bytes, privacy, dead-letter
operations, and metric usefulness.

## Stop condition

Merge, record automated memory, and stop. Do not start 12A.
