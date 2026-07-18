# Chunk Contract: WS-REV-001-12A

## Goal

Implement the hidden, persisted joint review/contribution release-control
aggregate and mandatory typed mutation fences required for safe product release,
shutdown, crash recovery, and forward reactivation.

## Risk class

L1 cross-domain release control, authorization, and operational safety.

## Allowed files

```text
backend/app/modules/lifecycle_control/{__init__,models,repository,schemas,service,ports,router}.py
backend/app/composition/joint_lifecycle_control.py
backend/app/composition/review_lifecycle.py only to inject the mandatory fence into existing task/checker/review construction
backend/app/composition/compensation.py only to install the exact merged CON obligation-writer, dispatch, and callback fence hooks
backend/app/modules/reviews/service.py only to require the merged lifecycle fence on mutations
backend/app/modules/tasks/service.py only to require the merged lifecycle fence on submission/replacement commands
backend/app/modules/checkers/service.py only to require the merged lifecycle fence on review-queue admission
backend/app/workers/reviews.py only to inject the mandatory fence into existing review maintenance commands
backend/app/core/config.py only for bounded observation settings
backend/app/db/models.py
backend/alembic/versions/<activation-next>_joint_lifecycle_release_control.py
backend/tests/test_{alembic,lifecycle_control,reviews,tasks,checkers,compensation,outbox,audit,authorization,api_contract_e2e,config}.py
docs/operations_{reviewer_workflow,operator_workflow,payment_reputation}.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-12A.json
```

## Not allowed

```text
production review/contribution/compensation/lifecycle-control router registration
review, contribution, award, compensation, or fulfillment policy changes
provider call in the control transaction
script-owned lifecycle truth or in-memory-only phase
optional/no-op production fence
schema/application downgrade after protected post-cutover rows exist
```

## Acceptance criteria

- `JointLifecycleReleaseControl` is one PostgreSQL-canonical singleton with a
  monotonically increasing generation, current phase, exact reviewed manifest
  digest, database timestamps, latest successful transition, and the immutable
  fulfillment-obligation cutoff captured for the current generation. Immutable
  transition/attempt rows store expected generation/prior phase, target phase,
  bounded reason, the server-derived cutoff when applicable, exact
  `initiating_actor_id` referencing canonical human `ActorProfile.id`,
  AuthorizationDecision, audit, and idempotency linkage.
- The only legal graph is
  `pre_activation(N) -> revision_cutover_fenced(N) -> active(N) ->
  admission_fenced(N) -> commands_draining(N) -> leases_released(N) ->
  delivery_draining(N) -> disabled(N)`, followed only by
  `disabled(N) -> pre_activation(N+1)` with a newly reviewed manifest digest.
  Migration creates only `pre_activation(1)`. Compare-and-set plus database
  constraints reject skipped, reversed, concurrent, crossed-generation, or
  unknown edges and preserve every prior generation unchanged.
- Every lifecycle-control observe, transition, and crash-resume attempt is a
  fresh authenticated Operator command declaring registered planned AUTH-owned
  `review.lifecycle.activation.manage` mapped to existing
  `operations.reconcile.run`. Only an Operator AdminRoleGrant is a candidate.
  Its typed resource contains operation, singleton ID, expected generation and
  phase, target phase when applicable, exact manifest digest, server-resolved
  drain observations, bounded batch/deadline, and reason. It uses caller-owned
  AsyncSession, revalidates authority, records one AuthorizationDecision/audit/
  outbox result, and exact replay returns the same result while changed replay
  conflicts. There is no lifecycle-control background job, serialized human-authority
  replay, or service actor that advances canonical phase; after a crash an
  Operator reloads status and reissues the exact or next adjacent command.
  Lease draining does not widen this action: each lease uses the existing
  `review.lease.force_release` command with its own fresh Operator decision,
  bounded reason, idempotency, audit, and review-owned effects.
- A shared typed `JointLifecycleMutationFence` is injected through one explicit
  composition root into review mutations, every task submission, review-queue
  admission, review maintenance commands, authority-loss replacement assignment,
  every CON fulfillment-obligation root creation, requeue, successor, and repair
  writer, and compensation fulfillment dispatch and callback handling. The CON
  writer hooks must be approved and merged before 12A; this chunk installs them
  through composition and does not edit CON-owned writer logic. There is no
  fallback constructor, service locator, optional/no-op port, or concrete
  cross-domain repository import.
- After AUTH prepares and locks current authority, it returns an opaque,
  non-Pydantic, single-use handle bound to exact session, ActionId,
  actor-reference kind and ID, idempotency key, and canonical request digest.
  Every mutation locks its feature-owned operation-idempotency row, acquires the
  shared PostgreSQL transaction advisory lock, reads the phase, locks its exact
  product-domain rows, and recomposes the final typed facts. Only then does AUTH
  validate and consume the exact handle, evaluate once, and stage decision
  evidence. Feature mutation and participant flush follow that decision; the
  request route or service command commits once. Phase transition follows the
  same prefix with the matching exclusive advisory lock, so
  it waits for prior mutation transactions and blocks new entrants without
  reversing the global lock order. After commit, new commands acquire the shared
  lock and fail or pass from the persisted phase. Independent-session tests prove
  both orderings, AUTH/fence concurrency without deadlock, and that process-local
  locks cannot substitute. Pre-consumption wrong-binding, serialization, forgery,
  or caller construction fails before feature/shared audit/outbox mutation,
  stages no AuthorizationDecision/evidence, and preserves the legitimate
  unconsumed handle. Authority or policy denial after valid
  consumption also leaves feature/shared audit/outbox state unchanged; its clean
  AUTH evidence follows the denial protocol below. The phase snapshot remains
  held for the transaction.
- Wrong-binding, serialized, forged, or caller-constructed attempts against an
  unconsumed handle are protocol rejections: they stage no
  AuthorizationDecision/evidence, preserve the legitimate handle, and permit its
  later exact first use. Stale/already-consumed and concurrent duplicate attempts
  remain invalid, stage no new evidence or feature state, and can never become
  valid again; exactly one concurrent exact consumer may win. For current-authority or policy denial after
  valid consumption, the
  request route or service command rolls back the dirty caller transaction; AUTH
  restages the unchanged bounded denial in a clean transaction; and that route
  or command commits the evidence once. No phase, product, feature/shared
  audit/outbox, or participant effect survives. Denial-evidence restaging failure
  commits nothing.
- Submission fencing is two-stage. After acquiring the shared fence and phase,
  the service loads canonical task, predecessor, assignment, and preparation
  rows in normal order; derives initial, legacy-revision, or prepared-revision
  class from those rows rather than request shape; then checks the derived class
  against the captured phase before mutation. Crossed or forged preparation
  claims fail without changing state.
- The closed phase/command matrix is:

| Command class | Pre-activation N=1 | Pre-activation N>1 | Revision cutover fenced | Active | Admission fenced | Commands draining | Leases released | Delivery draining | Disabled |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| initial submission | allow | allow | allow | allow | deny | deny | deny | deny | deny |
| legacy revision submission | allow | deny | deny | deny | deny | deny | deny | deny | deny |
| prepared revision submission | deny | deny | deny | allow | deny | deny | deny | deny | deny |
| review-queue admission | allow | allow | allow | allow | deny | deny | deny | deny | deny |
| new review claim/routing mutation | deny | deny | deny | allow | deny | deny | deny | deny | deny |
| leased review completion/owned release | deny | deny | deny | allow | allow | deny | deny | deny | deny |
| revision preparation/evidence/admin mutation | deny | deny | deny | allow | deny | deny | deny | deny | deny |
| review maintenance/projection or CON completion-only maintenance | deny | deny | deny | allow | allow | allow | allow | allow | deny |
| fulfillment-obligation creation, requeue, successor, or repair | deny | deny | deny | allow | allow | deny | deny | deny | deny |
| joint policy/configuration mutation | deny | deny | deny | allow | deny | deny | deny | deny | deny |
| legacy authority-loss replacement | allow | deny | deny | deny | deny | deny | deny | deny | deny |
| prepared authority-loss replacement | deny | deny | deny | allow | deny | deny | deny | deny | deny |
| authorized review recovery/lease release | deny | deny | deny | allow | allow | allow | deny | deny | deny |
| fulfillment dispatch | deny | deny | deny | allow | allow | allow | allow | pre-cutoff completion only | deny |
| authenticated fulfillment callback | allow | allow | allow | allow | allow | allow | allow | pre-cutoff completion only | deny |
| bounded canonical/control read | allow | allow | allow | allow | allow | allow | allow | allow | allow |
| lifecycle transition/status | allow | allow | allow | allow | allow | allow | allow | allow | allow |

  Bootstrap pre-activation therefore preserves the pre-cutover legacy pipeline
  plus post-REV-05 hidden queue creation without exposing human review or CON
  execution. Post-cutover generation N>1 pre-activation never re-enables legacy
  revision or replacement writers. The exact activation manifest maps every
  endpoint and async command to one matrix row; an unclassified command fails
  closed. Recovery/lease release retains each
  existing action and fixed service-actor or Operator authority; the matrix does
  not merge those authorities into lifecycle control.
- This chunk implements hidden lifecycle-control behavior, typed resource facts,
  guards, fence composition, and a feature-manifest delta while
  `review.lifecycle.activation.manage` remains registered and planned after the
  prerequisite `WS-AUTH-001-REV-REG`. `WS-AUTH-001-REV-LIFECYCLE` integrates its evaluator and
  activates it only after this chunk and all other additive manifests merge. The
  controller's `pre_activation` token is product state, not AUTH availability.
- The REV action/operation map is exact:

| Action or internal operation | `JointLifecycleCommandClass` |
|---|---|
| `submission.create` | server-derived initial, legacy-revision, or prepared-revision submission |
| checker `allow_review` participant | review-queue admission |
| `review.queue.read`, `review.queue.inspect`, `review.context.read`, `review.chain.read` | bounded canonical/control read |
| `review.claim`, `review.decline_preference`, `review.preference_expiry.run`, `review.queue.routing.override`, `review.queue.routing.correct`, `review.queue.close` | new review claim/routing mutation |
| `review.release`, `review.finding_evidence.ingest`, `review.decision` | leased review completion/owned release |
| `review.finding_response_evidence.ingest`, `review.revision_context.repair`, `review.revision_obligation.close`, `review.revision_context.legacy_close` | revision preparation/evidence/admin mutation |
| `review.lease_expiry.run`, `review.lease.force_release` | authorized review recovery/lease release |
| `review.reconcile.run` queue/routing mode | new review claim/routing mutation |
| `review.reconcile.run` lease-only mode | authorized review recovery/lease release |
| `review.reconcile.run` evidence-only scan, `review.artifact_reference.reconcile`, `review.projection.rebuild` | review maintenance/projection or CON completion-only maintenance |
| shared-outbox review snapshot projection handler under fixed `outbox.dispatch` authority | review maintenance/projection or CON completion-only maintenance |
| AUTH-13 revision-obligation replacement operation | server-derived legacy or prepared authority-loss replacement |
| `review.lifecycle.activation.manage` transition/status | lifecycle transition/status |

  Reconciliation mode is derived from locked canonical facts, never a caller
  label. The exact merged CON-owned joint-readiness manifest similarly maps every contribution,
  compensation, fulfillment, callback, read, policy, and operations command to
  the existing joint classes above. Missing, extra, ambiguous, or caller-chosen
  mappings fail startup and preflight. A command that can create, requeue,
  extend, or repair a fulfillment obligation cannot be classified as
  completion-only.
- The replacement-assignment command has a required typed slot for the
  preparation-transfer participant in prepared mode. REV-12A does not prescribe
  whether its fence foundation or amended AUTH-13 merges first: it classifies and
  fences the exact owner-installed legacy or prepared mode from the merged
  manifest, never from a caller label. After REV-09A supplies the participant,
  amended AUTH-13 atomically binds it, removes legacy replacement behavior, and
  fails startup/command execution when the binding is absent. Active generation
  and every generation N>1 require prepared mode and never re-enable the legacy
  class. REV-13 only verifies the merged binding and exposes the already cut-over
  command. No schema or release code infers or fabricates preparation.
- The composition root supplies the shared fence through the exact mandatory
  CON dispatch and callback hooks. Under the shared fence, the shared outbox
  dispatcher claims the event and passes an already-claimed command plus
  generation to the CON-owned handler. The handler validates that claim through
  a typed port and resolves the immutable root
  `fulfillment_obligation_ordinal` from canonical CON lineage. During
  `delivery_draining`, the captured generation must match and the root ordinal
  must be at or below the persisted cutoff. The handler may then persist a
  durable `in_flight` attempt under that existing root, commit, and release the
  database transaction and advisory fence. Only then may it call the adapter,
  with no lifecycle advisory lock or database transaction held; it finalizes
  delivery success or retry state for the same root in a new fenced transaction.
  It cannot create a new root, requeue a different root, or enqueue successor
  work. Only the shared dispatcher changes outbox claim/retry/dead-letter state.
  A lost pre-I/O race returns the same root event to retryable pending without
  changing award or delivery truth.
  After CON-owned signature verification plus AUTH/idempotency locking,
  the callback transaction acquires the shared fence, reads the captured phase,
  resolves the callback's canonical root obligation and ordinal, and holds the
  fence through idempotent receipt commit. In `delivery_draining`, the callback
  must target the captured generation and a root at or below the cutoff. It may
  only finalize that root; it cannot create a successor event, retry root,
  delivery obligation, award, or other follow-on work. It fails closed before
  provider or successor I/O on crossed, missing, or post-cutoff lineage, fails
  closed after `disabled`, and cannot race the exclusive disable transition.
  REV edits neither CON handler nor outbox policy.
- Typed readiness/drain ports provide only server-resolved observations. Merged
  chunk 12 supplies same-session `ReviewLifecycleDrainObservationPort` for
  active-lease plus pending/in-flight review-maintenance counts. The exact
  merged CON-owned capabilities supply
  same-session `FulfillmentLifecycleDrainObservationPort` for pending/claimed/
  retryable fulfillment events, in-flight dispatch, and nonterminal delivery/
  callback obligations through the shared-outbox capability. The same port
  returns the current maximum immutable, monotonically increasing
  `fulfillment_obligation_ordinal`, allocated by CON only after the shared fence
  is acquired. The lifecycle transition persists that server-derived value as
  the generation's cutoff; zero is valid when no obligation exists. Exact
  writer/composition/migration readiness is also typed. Each port uses the
  caller's AsyncSession, is read-only, never commits or calls a provider, and is
  named in the readiness manifest. Caller-supplied timestamps, ordinals, event
  IDs, or generation claims cannot substitute. Lifecycle control imports no
  review, CON, or outbox repository.
- The CON readiness manifest enumerates every obligation-root writer and proves
  that each writer acquires the shared fence before allocating its ordinal or
  locking CON-owned obligation rows. Missing, optional, or differently ordered
  writer hooks fail composition and preflight. Independent-session tests race
  every creation, requeue, successor, and repair writer against
  `admission_fenced -> commands_draining` in both orders. The writer either
  commits under an ordinal included by the cutoff or observes
  `commands_draining` and fails without allocating or mutating an obligation.
- ART-backed review maintenance/projection uses the same fenced handoff: claim
  and persist durable `in_flight` under the shared fence, commit/release, perform
  provider I/O outside every database transaction and lifecycle advisory lock,
  then finalize through a new fenced transaction. Pending work may survive
  shutdown; persisted in-flight work blocks disable until completion or
  canonical crash recovery returns it to retryable state.
- Edge guards are exact: cutover entry verifies the reviewed manifest; product activation
  requires zero old writers plus strict migration/composition readiness;
  `admission_fenced -> commands_draining` takes the exclusive lock and therefore
  waits for admitted completion commands, reads the CON-owned ordinal through
  the same-session port, and atomically stores the generation's immutable drain
  cutoff; `commands_draining -> leases_released` requires zero active leases
  after fresh Operator force-release calls;
  `leases_released -> delivery_draining` begins the bounded drain of fulfillment
  work that was committed before completion commands were fenced. Fulfillment
  dispatch and authenticated callbacks remain allowed in `delivery_draining`
  only for roots at or below the stored cutoff. Every command that can create,
  requeue, extend, or repair an obligation is denied, including maintenance,
  reconciliation, callback successor work, and post-cutoff events. The
  `delivery_draining -> disabled` guard requires zero dispatchable, retryable,
  claimed, or in-flight fulfillment events; zero nonterminal delivery or
  callback obligations; and zero in-flight review maintenance after the
  exclusive lock drains concurrent finalization and callback transactions.
  Pending retryable review projection work may remain durable for forward
  reactivation, but no remote operation may remain in flight. No provider I/O
  occurs while any lifecycle advisory fence or database transaction is held.
  New-generation pre-activation requires prior `disabled`, a new manifest, and
  no schema downgrade.
- Bounded settings use database time and reject invalid/unbounded values. A
  timeout appends an immutable failed attempt with captured observations while
  leaving phase and product truth unchanged. Fresh Operator retry resumes
  forward; it never fabricates completion, drops pending work, disables callbacks
  early, replays serialized human authority, or attempts schema downgrade.
- Lifecycle control reuses `canonical_json_hash`, shared request/correlation
  identifiers, the established reserve/lock/complete idempotency shape, and the
  shared caller-transaction audit/outbox participants. It creates no private
  canonicalizer, audit ledger, outbox, dispatcher, or retry framework.
- Operator transition route/service and every joint product router remain absent
  from production OpenAPI. Internal service, affected-execution integration,
  migration, and composition tests prove the foundation is present and fail
  closed if any mandatory fence binding is missing.
- REV-13 release keeps only the already-AUTH-active authenticated lifecycle-
  control transition and status surface available in `disabled`; product
  routes, product background jobs, and their fixed service identity mappings remain disabled. This
  retained control surface is the sole way to request `pre_activation(N+1)`.
- Migration/direct-SQL and independent-session tests cover singleton uniqueness,
  every legal/illegal edge and full generation-aware command matrix, N-to-N+1
  reactivation without legacy writer revival,
  compare-and-set/generation races, two-stage forged/crossed classification,
  actor/action linkage with the same composite/trigger human-kind enforcement
  used by review records, direct-SQL rejection of service/system/external/legacy
  actor IDs, AUTH/fence ordering, cutoff capture after prior completion
  transactions, every obligation writer versus cutoff capture in both orders,
  missing-writer-hook composition failure, callback-versus-disable, pre-cutoff
  dispatch before adapter I/O, post-cutoff/crossed-generation denial before
  adapter I/O, maintenance and callback-successor denial, canonical same-root
  claim recovery, bounded denial audit, and downgrade refusal once protected
  history exists.
  Failure injection after reservation, observation, history append, control CAS,
  audit, and outbox flush proves rollback; crash after commit plus exact replay,
  timeout-without-advance, bounded lease release, and forward retry are explicit.
  Review snapshot projection tests directly cover allowed phases, disabled
  denial, pending-versus-in-flight observation, blocked transition attempts,
  fresh retry, crash/retry, and unchanged canonical Review truth under its fixed
  `outbox.dispatch` actor.
  Independent-session tests run maintenance/projection versus disable in both
  orderings, prove durable in-flight state exists before fence release, deny
  disable advancement until finalization/recovery, prove the blocked attempt
  releases its exclusive lock and leaves phase unchanged, and instrument the
  adapter to prove provider I/O executes with no lifecycle advisory lock or DB
  transaction held.
- New/materially changed code is at least 90 percent covered and the repository
  remains at or above the 78 percent global floor.

## Verification

```text
cd backend && alembic upgrade head
cd backend && pytest -q tests/test_alembic.py tests/test_lifecycle_control.py tests/test_reviews.py tests/test_tasks.py tests/test_checkers.py tests/test_compensation.py tests/test_outbox.py tests/test_audit.py tests/test_authorization.py tests/test_api_contract_e2e.py tests/test_config.py
cd backend && ruff check app/modules/lifecycle_control app/modules/reviews app/modules/tasks app/modules/checkers app/workers/reviews.py app/composition/joint_lifecycle_control.py app/composition/review_lifecycle.py app/composition/compensation.py tests/test_lifecycle_control.py
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
cd backend && coverage report --include='app/modules/lifecycle_control/*' --precision=2 --fail-under=90
cd backend && for path in app/modules/reviews/service.py app/modules/tasks/service.py app/modules/checkers/service.py app/workers/reviews.py app/core/config.py app/composition/joint_lifecycle_control.py app/composition/review_lifecycle.py app/composition/compensation.py; do coverage report --include="$path" --precision=2 --fail-under=90 || exit 1; done
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test-delta, and CI integrity if proof tooling changes.

## Human review focus

Cross-domain fence ownership, advisory-lock behavior, Operator authority,
timeout/forward-recovery semantics, immutable fulfillment cutoff, completion-only
drain authority, callback preservation, and no public surface.

## Stop condition

Merge, record automated memory, and stop. Do not start 13.
