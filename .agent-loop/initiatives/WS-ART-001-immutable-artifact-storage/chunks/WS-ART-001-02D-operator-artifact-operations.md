# Chunk Contract: WS-ART-001-02D Operator Artifact Operations

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 02C3, AUTH-09E, and `WS-AUTH-001-ART-CUSTODY`

Artifact contract phase: `artifact_store_cutover`

## Goal

Implement exact hidden Operator read/retry/recovery/audit APIs, internal resource
composition, and static production-readiness status while every affected action
remains planned. AUTH activates the exact actions only after this behavior
merges. This chunk activates neither authorization, a provider profile, nor a
product cutover. Chunk 07 owns every live AWS provider inspection.

## Allowed Files

- artifact router and public/internal schemas
- `ArtifactOperatorReadPort` read/admission-usage implementation and
  `ArtifactOperatorRecoveryPort.retry_verification` implementation
- API router composition root
- static provider-profile readiness prerequisites/status; profiles remain
  inactive and this chunk performs no AWS policy/lifecycle API inspection
- artifact call sites consuming the exact existing Authorization Service
  permissions mapped below; no Authorization Service owner files
- focused route, authorization, redaction, readiness, and real-API tests
- `.github/workflows/backend.yml` only to expand the exact 90 percent scoped gate
- `scripts/test_agent_gates.py` only to assert the exact workflow command,
  source set, threshold, and cumulative retention
- directly related operations docs and chunk memory

## Not Allowed

- contributor, reviewer, or project-owner artifact operations;
- guide, task, submission, checker, review, contribution, payment, or
  reputation cutover;
- database-inspection-only operational proof;
- provider object references, endpoints, credentials, signed URLs, or raw
  provider bodies in responses;
- provider delete/retain/release or Flow Node.
- Authorization Service implementation, permission registration, or policy
  changes.

## Acceptance Criteria

- exact Operator APIs exist for resource-scoped binding discovery, replicas,
  receipts, verification job, retry, recovery-attempt read, artifact audit
  listing, and read-only admission usage.
- AUTH-07A/07B, AUTH-08, AUTH-09A through AUTH-09E, and
  `WS-AUTH-001-ART-CUSTODY` are merged before this chunk starts. They
  provide the complete typed/SQL planned action registry, Operator grants,
  static service-action matrix, provisioned service ActorProfiles and
  ActorIdentityLinks, fixed service runtime admission, and AUTH activation
  custodians. This feature chunk supplies hidden canonical artifact resources,
  guards, surfaces, and decision calls; it registers no permission, evaluator,
  or availability change and creates no fallback.
- binding, replica, receipt, verification-job, and recovery-attempt reads use,
  respectively, `artifact.binding.read`, `artifact.replica.read`,
  `artifact.receipt.read`, `artifact.verification_job.read`, and
  `artifact.recovery_attempt.read`; provider-job retry uses
  `artifact.verification_job.retry`, and artifact audit listing uses
  `artifact.audit.read`. The retry route creates the recovery-attempt envelope
  and retry job; Celery verification uses only
  `artifact.verification.execute`, and ambiguous put resolution uses only
  `artifact.put_attempt.resolve`.
- `GET /api/v1/operator/artifacts/admission-usage` uses the exact
  `operations.artifact_storage_admission.read` ActionId mapped to existing
  `operations.status.read`; it exposes bounded current usage/limits and cannot
  release charges, mutate configuration, or create work.
- internal verification uses a provisioned service principal with
  `artifact.verification.execute`; periodic scan publication uses
  `artifact.pending_work.scan`. These permissions remain separate and do not
  imply one another.
- every route calls an exact Authorization Service action/resource decision;
  broad role checks are not authority.
- immediately before the retry transaction commits, Workstream revalidates the
  actor state, identity link, Operator grant, exact permission/resource, and
  expected source-job state inside that transaction. Revocation or suspension
  rolls back with no recovery attempt, retry job, or initiation-success audit;
  race tests cover each authority input;
- verification and put-resolution workers revalidate current fixed service
  actor, identity link, exact action/resource, executor, and generation inside
  every terminal mutation transaction; suspension/revocation races write no
  terminal state, receipt, replica/attempt, recovery, or audit fact;
- retry requires a reason, client idempotency key, and expected source-job CAS
  version, accepts
  only exhausted terminal `provider_unavailable`, and returns `202` with
  recovery-attempt, source-job, and retry-job IDs. Exact request replay returns
  those original IDs; altered replay conflicts. Every other job state fails
  without side effects.
- recovery-attempt GET returns immutable source-job status, current retry-job
  status, terminal mapping, chain identity, and audit IDs.
- binding discovery starts from an exact known product resource and exposes the
  stable Workstream IDs needed for diagnosis/recovery; audit filters are exact.
- cross-project and unauthorized callers are denied without leaking existence.
- responses are bounded, paginated where needed, and contain no provider
  internals or secrets.
- LocalStorage and MinIO instantiate through the typed factory in their allowed
  environments. AWS S3 production remains uninstantiable with
  `artifact_provider_live_proof_required`; the activation schema and production
  composition guard do not exist until Chunk 07. Invalid profiles fail closed.
- after this hidden behavior merges, separate AUTH activation checkpoints make
  the three internal service actions and eight Operator actions executable.
  `artifact.verification_job.retry` remains independently evaluated and is not
  implied by internal service activation. No 02C1, 02C2, or 02C3 mechanic runs
  before the internal AUTH gate.
- readiness exposes static configured prerequisites and remains inactive.
  Chunk 07's deployment-only harness owns bucket-policy/principal-boundary,
  credential, anonymous-read-negative, completed-prefix lifecycle, and AWS
  activation proof; neither `ArtifactStore` nor a product service gains a
  provider-administration method. Chunk 07 alone creates a matching immutable
  activation record and enables production composition after live proof.
- readiness does not write or mutate provider objects.
- real HTTP tests prove the full Operator path without direct database reads.
- metrics and alerts cover admission pressure at each configured scope; the
  operations runbook defines configuration-driven quota expansion and incident
  rollback without charge deletion or database editing.
- changed subsystem coverage is at least 90 percent and repository coverage
  does not decrease.
- backend CI installs this chunk's exact focused 90 percent gate, preserves
  every earlier scoped 90 percent gate, and retains the exact 78 percent
  repository command below; `scripts/test_agent_gates.py` fails on workflow
  command, source-set, threshold, or cumulative-retention drift.

## Exact CI Coverage Gates

```bash
coverage report --include='app/adapters/artifacts/*,app/core/cancellation.py,app/core/file_locks.py,app/interfaces/artifact_operations.py,app/interfaces/artifacts.py,app/modules/artifacts/*' --precision=2 --fail-under=90
coverage report --include='app/interfaces/external_services.py' --precision=2 --fail-under=90
coverage report --include='app/core/config.py' --precision=2 --fail-under=90
coverage report --include='app/workers/*' --precision=2 --fail-under=90
coverage report --include='app/main.py' --precision=2 --fail-under=90
coverage report --include='app/adapters/artifacts/s3_compatible.py' --precision=2 --fail-under=90
coverage report --include='app/core/s3_validation.py' --precision=2 --fail-under=90
coverage report --include='app/modules/audit/*' --precision=2 --fail-under=90
coverage report --include='app/api/router.py' --precision=2 --fail-under=90
```

## Verification

```bash
docker compose up -d --wait postgres redis minio
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_artifact_operator_api.py tests/test_artifact_authorization.py tests/test_config.py -q --cov=app.interfaces.artifact_operations --cov=app.modules.artifacts --cov=app.adapters.artifacts --cov=app.api.router --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Are the Operator actions and resources exact?
- Can operations be understood without database access?
- Do readiness results keep AWS S3 inactive until its live proof succeeds?
