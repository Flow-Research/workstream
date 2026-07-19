# Chunk Contract: WS-ART-001-02C2 - Verification Publication And Fencing

Initiative: `WS-ART-001` | Risk: L1 | Status: Active after explicit start on 2026-07-19

Artifact contract phase: `artifact_store_cutover`

Plan review: `PASS WITH CONDITIONS`; all four bounded conditions are encoded
below before implementation.

## Goal

Claim committed put attempts, perform provider writes and read-only outcome
observation, publish complete-object verification, and fence Celery execution.
Do not add recovery attempts, Operator routes, or product cutovers.

## Allowed Files

- one verification/fencing migration;
- artifact verification models, schemas, repository, service, and contracts;
- artifact-owned typed internal-action resource facts and a fail-closed
  authority/revalidation port; no AUTH evaluator, catalogue, matrix, or
  availability change;
- artifact orchestration execution for committed put attempts;
- Celery put-resolution/verification tasks and periodic publication scanner;
- `backend/app/core/config.py` for scanner SLA, execution lease,
  complete-read deadline, and persistence margin;
- focused PostgreSQL/Celery/artifact tests;
- `.github/workflows/backend.yml` only to expand the exact 90 percent scoped gate;
- `scripts/test_agent_gates.py` only to assert that backend CI retains this
  chunk's exact scoped coverage sources and fail-closed 90 percent threshold;
- directly related operations docs and chunk memory.

## Not Allowed

- recovery-attempt models, Operator/public routes, or manual retry contracts;
- guide, task, submission, checker, or review cutover;
- provider mutation replay, overwrite, delete, retain, or release;
- task-claim or reviewer-lease changes;
- production dispatch before AUTH registers the exact planned actions and
  static service-action matrix, provisions the exact service ActorProfiles and
  ActorIdentityLinks, admits them through AUTH-09E, 02C2/02D merge hidden
  behavior/resource composition, and the later AUTH activation checkpoint
  integrates their evaluators.

## Acceptance Criteria

- only artifact orchestration can claim a committed `ArtifactPutAttempt` and
  invoke writable `ArtifactStore`; architecture tests reject raw-port imports,
  broad orchestrator injection, and provider calls from product modules;
- provider acknowledgement yields `stored_pending_verification`, never a
  bindable replica;
- a claimed attempt gains a fresh executor UUID, PostgreSQL-clock lease expiry,
  and atomically incremented execution generation before provider I/O;
- provider acknowledgement or a fresh complete-object observation completes
  provisional charges; ambiguous outcomes remain provisional, authoritative
  absence releases charges and requires caller replay, and replay atomically
  reacquires released capacity before a later provider write;
- confirmed, quarantined, or integrity-mismatched content remains completed and
  charged because v0.1 has no physical deletion;
- a bounded scanner publishes prepared, acknowledgement-unknown, and expired
  in-flight attempts; duplicate publication is harmless;
- the resolver calls only read-only `observe_put_result` with the persisted
  commitment and then performs a fresh complete-object read and Workstream
  SHA-256/byte-count verification; no background path replays a write;
- matching bytes complete Transaction B once; absence releases charges and
  requires caller replay; mismatch quarantines;
- terminal put-resolution and verification writes require matching executor and
  generation plus current service actor/link/action/resource authority
  revalidated in the same terminal transaction; stale or revoked executors
  write no state, receipt, replica, recovery, or audit fact;
- the result matrix handles verified, missing, integrity mismatch, provider
  unavailable, conflict, and stale executor outcomes;
- missing yields `missing/unavailable/unknown`; integrity mismatch yields
  `integrity_mismatch/available/invalid` and cannot reset;
- complete reads enforce a total deadline shorter than the lease by a tested
  persistence margin, including continuously progressing slow streams;
- mechanics remain inactive through 02D while ART builds and tests hidden
  resource/behavior composition; only the later AUTH internal-action activation
  checkpoint can make them executable;
- migrations prove fresh, prior-head, populated, and empty round-trip behavior;
- changed subsystem coverage is at least 90 percent and repository coverage
  remains at least 78 percent;
- backend CI preserves every earlier scoped 90 percent gate and the exact 78
  percent repository command; gate tests fail on command, source-set,
  threshold, phase, or cumulative-retention drift.

## Resolved Execution Design

### Activation and authority seam

02C2 publishes three closed, artifact-owned resource fact types and one
transaction-scoped authority port:

| Action | Fixed service identity | Resource type | Resource ID | Locked immutable facts |
|---|---|---|---|---|
| `artifact.put_attempt.resolve` | `workstream.artifact.put_resolver` | `artifact_put_attempt` | put-attempt UUID | operation identity, namespace fingerprint, SHA-256, byte count, executor UUID, generation |
| `artifact.verification.execute` | `workstream.artifact.verifier` | `artifact_verification_job` | verification-job UUID | replica ID, namespace fingerprint, provider object reference, SHA-256, byte count, executor UUID, generation |
| `artifact.pending_work.scan` | `workstream.artifact.scheduler` | `artifact_pending_work` | `workstream:artifact_pending_work` | scanner kind, database-clock cutoff, bounded page size |

The port exposes two distinct operations over the exact fixed identity, closed
`ActionId`, and matching typed facts: preflight must allow before any claim,
provider I/O, broker publication, or mutation; terminal revalidation must lock
and revalidate the current
service ActorProfile and exact active ActorIdentityLink, recompose the facts
from the already locked artifact rows, and stage authority evidence in the same
caller-owned transaction. It must never inspect the static matrix, invent a
principal, evaluate a human grant, or change action availability.

The only production implementation added by this chunk denies before claim,
provider I/O, broker publication, or database mutation because all three
actions remain `planned`. An explicit test-only authority implementation may
exercise hidden behavior. AUTH-09E, AUTH-PREP, and
`WS-AUTH-001-ART-02D-INTERNAL` later replace that deny-only seam with the real
prepared protocol and evaluator integration. Tests must prove the real kernel
continues to return `action_unavailable` for all three actions.

Celery may register resolver and verifier task names for contract testing, but
the production Beat schedule contains no 02C2 scanner entry and production
composition cannot construct an allowing port. Direct production task
invocation therefore fails before a claim or side effect. Later AUTH activation
owns both allowing composition and scanner scheduling.

### Separate caller write and background observation flows

- The caller path alone supplies a nonserializable `CommittedArtifactSource`,
  claims a `prepared` attempt, changes it to `put_in_flight`, and invokes
  `ArtifactStore.put` once. Neither Celery nor the scanner carries bytes.
- The scanner may publish `prepared`, `acknowledgement_unknown`, or lease-expired
  `put_in_flight` attempt IDs to the resolver. Every resolver claim changes the
  attempt to observation mode and may call only `observe_put_result` followed,
  when committed, by a fresh complete read. A published `prepared` row never
  authorizes `put`; it is observed only, and authoritative absence returns it
  to caller-owned replay.
- A replay after authoritative absence remains a caller path. It first locks
  every linked admission scope and charge, reacquires released capacity
  atomically, and only then claims a new generation for writable provider I/O.

### Polymorphic operation receipts

The migration makes `ArtifactOperationReceipt` belong uniquely to one
`ArtifactPutAttempt`, not uniquely to a contributor upload item. It adds a
unique `put_attempt_id` required for new contract-v2 receipts; keeps
`upload_item_id` nullable for contributor
compatibility; and adds mutually exclusive nullable `guide_source_item_id` and
`checker_run_id` plus nullable `logical_role`. Exactly one producer reference
must match the attempt's closed producer kind. Existing contract-v1 contributor
receipts remain readable with a null `put_attempt_id`; rows linked by the unique
attempt `receipt_id` relationship are upgraded to v2. Downgrade
refuses without mutation if a receipt cannot be represented by the prior
contributor-only shape. One attempt can publish Transaction B and its operation
receipt at most once.

`ArtifactVerificationJob` is uniquely linked to the replica and originating
put attempt for this first verification generation. Verification receipts are
append-only and unique by `(verification_job_id, execution_generation)`; only a
terminal matching fence may create one. Recovery-generated jobs remain 02C3.

Read-only put resolution uses a separate append-only
`ArtifactPutObservationReceipt`, unique by `(put_attempt_id,
execution_generation)`. Its closed outcomes are `observed_confirmed`,
`observed_missing`, `observed_integrity_mismatch`, and `conflict`; it records
only typed digest/size/existence evidence and may not carry arbitrary details.
Provider acknowledgement uses `ArtifactOperationReceipt` with its existing
`stored_pending_verification` outcome. A pre-verification mismatch or conflict
therefore never overloads the acknowledgement receipt, and unavailable/stale
observations create no receipt.

### Put-attempt transition matrix

| Current/claim | Provider result | Persisted result | Charges | Replica/receipt/job | Scheduling and fence |
|---|---|---|---|---|---|
| `prepared` caller claim | before I/O | `put_in_flight` | provisional | none | fresh executor, generation +1, DB lease, CAS +1 |
| `put_in_flight` | acknowledgement or fresh matching full observation | `object_confirmed` | complete once | pending/unknown/unknown replica, operation receipt, pending verification job once; contributor item becomes `stored_pending_verification` | clear executor/lease/next-run; terminal timestamp/result; CAS +1 |
| `put_in_flight` | ambiguous/unavailable | `acknowledgement_unknown` | provisional | none | clear executor/lease; set bounded `next_run_at`; CAS +1 |
| eligible scanner claim (`prepared`, `acknowledgement_unknown`, expired `put_in_flight`) | before observation | `put_in_flight` in observation mode | unchanged | unchanged | fresh executor, generation +1, DB lease, CAS +1 |
| observation claim | authoritative absence | `absent_replay_required` | release provisional once and decrement counters | no new replica/receipt/job; contributor item becomes `replay_required` | clear fence/schedule; terminal result; CAS +1 |
| observation claim | object exists but digest/size differs | `integrity_mismatch` | complete once | quarantined `integrity_mismatch/available/invalid` replica and put-observation receipt; no reset | clear fence/schedule; terminal result; CAS +1 |
| any matching claim | contradictory persisted/provider facts | `conflict` | never release completed charge | conflict evidence only | clear fence/schedule; terminal result; CAS +1 |
| any claim | executor/generation/authority/resource mismatch | unchanged (`stale`) | unchanged | no facts | zero-row terminal update |

Guide and checker source rows are immutable provenance and receive no lifecycle
mutation in 02C2. Only contributor `ArtifactUploadItem` has the existing
`stored_pending_verification` and `replay_required` transitions. Confirmed,
integrity-mismatched, and conflict results are immutable. Automatic attempt
resolution has a configured maximum observation count; `provider_unavailable`
means the budget is exhausted and is terminal until 02C3 creates a new job or
caller flow. Before exhaustion, unavailability is represented only by
`acknowledgement_unknown` plus `next_run_at`.

### Verification-job transition matrix

| Current/claim | Observation | Job result | Replica result | Scheduling and fence |
|---|---|---|---|---|
| `pending`, retryable `provider_unavailable`, or expired `running` | before read | `running` | unchanged | fresh executor, generation +1, attempt count +1, DB lease, CAS +1 |
| `running` | exact complete hash and size | `verified` | `verified/available/valid`; contributor item may become `ready` | clear fence/schedule; terminal receipt/result; CAS +1 |
| `running` | authoritative missing | `missing` | `missing/unavailable/unknown`; contributor item becomes `replay_required` only while unbound | clear fence/schedule; terminal receipt/result; CAS +1 |
| `running` | digest/size mismatch | `integrity_mismatch` | `integrity_mismatch/available/invalid` permanently | clear fence/schedule; terminal receipt/result; CAS +1 |
| `running` | provider unavailable below budget | `provider_unavailable` retryable | unchanged | clear fence; bounded `next_run_at`; CAS +1 |
| `running` | provider unavailable at budget | `provider_unavailable` exhausted | unchanged | clear fence/schedule; terminal timestamp/result; CAS +1 |
| `running` | contradictory immutable facts | `conflict` | never reset missing or mismatch | clear fence/schedule; terminal receipt/result; CAS +1 |
| any claim | executor/generation/authority/resource mismatch | unchanged (`stale`) | unchanged | zero terminal facts |

`provider_unavailable` is retryable exactly when `next_run_at` is non-null,
`terminal_at` is null, and observation/attempt count is below its configured
maximum. It is exhausted exactly when `next_run_at` is null, `terminal_at` is
non-null, and the count has reached the maximum. Database checks and tests
enforce both directions; no row can be ambiguously retryable and terminal.

Post-acknowledgement verification `missing` records the replica/job/receipt and
marks an unbound contributor item `replay_required`, but 02C2 provides no
writable replay transition for the immutable `object_confirmed` attempt. It
does not release or reacquire completed charges, reset the replica, append a new
operation receipt, or create a replacement verification job. The later caller
and product cutover chunk must define that separate replay generation before it
can execute.

The scanner orders by due time then UUID, uses a configured hard page bound,
and publishes identifiers only after its read transaction commits. Duplicate
publication is harmless because claims are fenced. Publication failure leaves
the row due for a later scan and does not alter domain state.

### Deadline and concurrency proof

The configured complete-read deadline wraps provider-open acquisition and the
entire async-stream consumption, not per-chunk idle time. It is strictly less
than `execution_lease - persistence_margin`; the persistence margin is reserved
for the terminal transaction. A continuously progressing slow stream still
times out at the total deadline.

Focused PostgreSQL tests must cover duplicate delivery, simultaneous claims,
expired-lease takeover, stale completion after takeover, actor suspension or
deactivation, link revocation, resource drift, scanner pagination and duplicate
publication, acknowledgement loss, authoritative absence, mismatch
immutability, and charge reacquisition before caller replay. Every stale or
revoked case asserts zero terminal state, operation receipt, verification
receipt, replica, job, recovery, or audit facts.

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
```

## Verification

```bash
docker compose up -d --wait postgres redis minio
(cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_artifact_admission.py tests/test_artifact_architecture.py tests/test_artifact_cleanup_wiring.py tests/test_artifact_preparation.py tests/test_artifact_verification.py tests/test_artifacts.py tests/test_audit.py tests/test_config.py -q --cov=app.interfaces.artifact_operations --cov=app.modules.artifacts --cov=app.modules.audit --cov=app.core.config --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Is provider execution impossible without a committed admission/put attempt?
- Can any stale or duplicate Celery executor write terminal state?
- Is verification independent of upload acknowledgement and write replay?
