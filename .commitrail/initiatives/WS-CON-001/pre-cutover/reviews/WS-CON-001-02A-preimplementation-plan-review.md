# WS-CON-001-02A Preimplementation Plan Review

## ART-02C1 Current-Main Reconciliation

ART-02C1 PR #154 merged at trusted main `44f2467c` and owns
`0028_artifact_admission`. The reviewed 02A design and scope remain unchanged;
its migration is now the exact linear child
`0029_shared_transactional_outbox`. Fresh bounded proof and all nine exact-SHA
reviewer tracks are required before PR #155 is republished.

## Contributor Foundation Current-Main Reconciliation

Trusted main advanced to `8d5eb15b384fd75787ce98a099400a1d335d2560`
through contributor-foundation PR #153. The merge clean-cuts TaskAssignment and
Submission attribution to canonical human `contributor_id`, adds database
lineage guards and transaction-local active-human writer revalidation, and
owns `0027_contributor_foundation`. It changes no ActionId, PermissionId,
availability, grant, evaluator, fixed-service admission, review lifecycle,
dispatcher seam, or outbox behavior. CON-02A remains authorization-neutral and
moves to the exact linear child `0028_shared_transactional_outbox`. AUTH-09E
remains later.

The AUTH merge also deliberately makes its actor-lifecycle downgrade tests
revision-specific rather than treating repository `head` as `0026`. CON
preserves that test ownership and adds separate dedicated `0028` migration/head
proof. Repository-wide proof remains GitHub CI-owned; local reconciliation
proof is bounded to the outbox and migration selectors.

## AUTH-09D-B Historical Reconciliation

Trusted main advanced to `93dd392484b397cfdfaaa833631dc2c27f591ed7`
through AUTH-09D-B PR #152. The canonical catalogue remains 74 PermissionIds
and 65 ActionIds, now 17 active and 48 planned. The merge activates exactly
`actor.identity_link.revoke` and `actor.identity_link.reactivate`; it adds no
CON/task-claim ActionId, fixed-service admission, migration, or outbox seam.
At that historical point the contributor-field/canonical-human foundation was proposed next, with
AUTH-09E still later. CON-02A therefore remains authorization-neutral at
`0027`. PR #153 supersedes that migration-head statement as described above.

The exact isolated PostgreSQL plus MinIO suite on the prior `1b5422fc`
baseline was stopped after one hour solely because PR #152 advanced trusted
main. Its metadata was removed and it is not accepted evidence.

## ART-02B1 Historical Reconciliation

Trusted main advanced to `1b5422fcaa361152af7c2b1f82a763d99c0e6db5`
through ART-02B1 PR #151. The merge adds the S3-compatible ArtifactStore
adapter, real MinIO integration, inactive AWS-profile support, exact SDK pins,
CI services/coverage gates, and substantial artifact/configuration tests. It
adds no migration, outbox import, dispatcher seam, AUTH/CON identifier, ART
call in the core transaction, or 02A allowed-file change. Alembic therefore
still ends at CON-owned `0027_shared_transactional_outbox`, while the expanded
dependency and test tree requires fresh deterministic evidence.

The exact isolated suite on the prior `983b9e53` baseline was stopped after 3
hours 7 minutes solely because PR #151 advanced trusted main. Its metadata was
removed and it is not accepted evidence. Verification must restart on the
frozen `1b5422fc` baseline after installing the newly merged locked runtime
dependencies and starting the real MinIO test provider required by main.

## REV PLAN2 Historical Reconciliation

Trusted main advanced to `983b9e534b84f1590fafecc0ce1355cf131257ce`
through planning-only REV PLAN2 PR #150. The merge changes no backend runtime,
migration, test runner, AUTH catalogue, outbox contract, or 02A allowed-file
scope. It preserves the two ordered CON operations, accept-only
FinalAcceptance, REV-owned shared audit/outbox staging, and one caller commit.
It replaces future non-executable REV parent gates with explicit children:
CON-03B precedes REV-03A, CON-02A/02C precede REV-04B, CON-03C/07 precede
REV-10, the shared dispatcher/handler registry precedes REV-12P1, CON fence
hooks precede REV-12A3, and CON-11 precedes REV-13C. No 02A implementation
change is required.

An exact isolated suite started on the prior `99ae4c96` baseline was stopped
after two hours solely because PR #150 advanced trusted main. It produced no
accepted evidence artifact and is not counted below. Exact verification must
restart on the frozen `983b9e53` baseline.

## AUTH-09D-A Historical Reconciliation

Trusted main advanced to `99ae4c963e53f317175dcb308b9e47c93ccf19ed`
through AUTH-09D-A PR #148 before publication. AUTH now owns
`0026_actor_profile_lifecycle`, so CON-02A's reviewed linear migration is
`0027_shared_transactional_outbox` with parent
`0026_actor_profile_lifecycle`. AUTH-09D-A activates only three actor-profile
lifecycle actions; it adds no CON/outbox identifier, evaluator, service
identity, static row, fixed-service admission, or product behavior.
Historical local evidence used a 25,200-second full-suite safety ceiling after
the pre-AUTH-09D-A suite consumed 17,741.96 of 18,000 seconds. Human direction
D20 supersedes that local execution location: repository-wide proof now runs
in GitHub CI, with no selection, assertion, isolation control, or 78/90
coverage threshold change.

## Exact baseline and scope

- Baseline: trusted `origin/main` at `a10d901` after ART PR #141 merged.
- Risk: L1 infrastructure, schema, concurrency, audit, and data-integrity risk.
- Delivery priority: P1 active-sprint prerequisite for REV/CON composition.
- Human checkpoint: required before merge.
- Allowed implementation files and exclusions are exactly those in
  `../chunks/WS-CON-001-02A-shared-outbox-persistence.md`.
- The user-owned deleted reference PDF is outside scope and must remain
  unstaged and untouched.
- Before final implementation evidence, trusted `main` advanced again to
  `0ffdabf` through AUTH-09C PR #146. Its administrative actor/profile reads
  activate only existing AUTH-owned identifiers, add no migration or CON
  action, and leave this reviewed implementation contract unchanged.
- Trusted `main` later advanced to `b2b9016` through REV-01 PR #145. Its
  canonical review specification preserves the exact FinalAcceptance,
  two-operation CON participant, shared-outbox, and single-commit boundaries;
  it adds no backend runtime or migration and does not alter this plan.
- Trusted `main` later advanced to `f18b620` through planning-only REV-02 PR
  #147. Its future REV chunk decomposition adds no runtime, migration, test
  runner, CON, or outbox behavior and leaves this plan unchanged.
- Historical local full-suite execution reached 90 percent with no failures
  before its process ceiling. D20 now assigns the unchanged complete test set
  and 78 percent repository coverage floor to GitHub CI; local proof is bounded
  to focused real-service tests and the 90 percent subsystem floor.

## Proposed implementation

1. Add one `OutboxEvent` PostgreSQL table and SQLAlchemy model containing the
   exact immutable common event envelope and canonical payload digest frozen
   below, plus the complete generic operational-delivery shape required by the
   later migration-free CON-02B dispatcher chunk.
2. Enforce event/idempotency uniqueness, the exact payload/digest/token bounds
   below, database-owned occurrence time, closed delivery-state shapes,
   immutable envelope/payload custody, permanent physical delete/truncate
   denial, terminal archival-in-place, and a nonempty-table downgrade guard in
   linear revision `0028_shared_transactional_outbox` after AUTH-owned
   `0027_contributor_foundation`.
3. Add strict typed append input/output schemas. The caller supplies stable
   event identity and canonical event facts but not occurrence or delivery
   state. The service hashes only the validated payload with
   `canonical_json_hash`.
4. Reuse the existing PostgreSQL reserve/lock/replay sequence and typed
   conflict/replay semantics, without importing AUTH or creating a generic
   idempotency abstraction. Attempt the completed event insert with
   `ON CONFLICT DO NOTHING`; insertion itself is the event reservation and
   there is no separate pending-to-complete idempotency record. Lock matches in
   ascending event-ID order and apply the collision matrix below. Flush/refresh
   only; transaction commit remains caller-owned. Never commit, publish,
   enqueue, log payloads, or open another session.
5. Register the model in shared metadata and add PostgreSQL tests for linear
   migration upgrade/guarded downgrade, schema/trigger invariants, append and
   exact replay, the full collision/race matrix, canonical key-order replay,
   payload/error privacy bounds, and caller rollback proving no independent
   commit or publication.
6. Run the exact bounded isolated CON-02A row, focused coverage at or above 90
   percent, Ruff, stale-wording and link checks, then fan out all required
   internal reviewer tracks on one exact commit SHA. After the full PR is
   pushed, GitHub CI owns repository-wide tests and coverage at or above 78
   percent. Repair and rerun evidence/review after any implementation change.

## Explicit non-goals

- No AUTH catalogue or evaluator changes and no outbox action/permission.
- No dispatcher, Celery task, broker, registry, handler, route, claim action,
  retry execution, feature delivery, or external I/O.
- No contribution, compensation, review, task, project, audit, or ART behavior.
- No second JSON canonicalizer, generic idempotency framework, dependency, or
  CI/coverage change.
- No CON-02B work.

## Frozen persistence schema

### Immutable columns

| Column | PostgreSQL type | Null/default/bounds |
|---|---|---|
| `event_id` | `UUID` | primary key; caller-supplied |
| `event_type` | `VARCHAR(128)` | non-null; ASCII token `[A-Za-z][A-Za-z0-9._:-]{0,127}` |
| `event_version` | `SMALLINT` | non-null; `1..32767` |
| `producer` | `VARCHAR(32)` | non-null; database-forced `workstream` |
| `aggregate_type` | `VARCHAR(64)` | non-null; lower ASCII token `[a-z][a-z0-9_]{0,63}` |
| `aggregate_id` | `UUID` | non-null; canonical source aggregate identity |
| `project_id` | `VARCHAR(36)` | non-null FK to `projects.id`; canonical lowercase UUID text |
| `correlation_id` | `VARCHAR(200)` | non-null; ASCII token `[A-Za-z0-9._:-]{1,200}` |
| `causation_event_id` | `UUID` | nullable; no FK because the cause may live in another event ledger |
| `idempotency_key` | `VARCHAR(200)` | non-null; globally unique; ASCII token `[A-Za-z0-9._:-]{1,200}` |
| `payload` | `JSONB` | non-null object; generic structural/privacy bounds below |
| `payload_digest` | `VARCHAR(71)` | non-null `sha256:` plus 64 lowercase hex characters |
| `occurred_at` | `TIMESTAMPTZ` | non-null; database-forced `statement_timestamp()` |

The event ID and globally namespaced idempotency key are independent unique
identities. Every column in this table is immutable except the operational
allowlist below. The database insert trigger overwrites producer, occurrence
time, initial state, counters, eligibility time, and all nullable operational
fields so direct SQL cannot forge an already-claimed or completed event.

### Mutable operational columns

| Column | PostgreSQL type | Initial/bounds |
|---|---|---|
| `delivery_state` | `VARCHAR(16)` | `pending`; closed set `pending`, `claimed`, `retryable`, `acknowledged`, `dead_letter`, `cancelled` |
| `attempt_count` | `INTEGER` | `0`; nonnegative and equal to claim generation |
| `next_attempt_at` | `TIMESTAMPTZ` | occurrence time while initially pending; otherwise state-bound |
| `claim_owner` | `VARCHAR(120)` | nullable bounded ASCII token |
| `claim_generation` | `BIGINT` | `0`; nonnegative and incremented with each claim |
| `claimed_at` | `TIMESTAMPTZ` | nullable; equals `last_attempt_at` while claimed |
| `claim_expires_at` | `TIMESTAMPTZ` | nullable; greater than `claimed_at` |
| `last_attempt_at` | `TIMESTAMPTZ` | nullable; database-time attempt evidence |
| `last_error_code` | `VARCHAR(80)` | nullable; `[A-Z][A-Z0-9_]{0,79}` only; never free-form diagnostics |
| `finalized_at` | `TIMESTAMPTZ` | nullable; required for terminal states |
| `archived_at` | `TIMESTAMPTZ` | nullable; allowed only for terminal rows and not before `finalized_at` |

There is no physical purge seam. Retention in v0.1 means terminal
archival-in-place by setting `archived_at`; immutable event/payload truth is
never deleted or truncated. CON-02B may mutate only this operational allowlist.

### Closed state shapes

| State | Required shape |
|---|---|
| `pending` | zero attempts/generation; eligibility present; no claim, attempt, error, final, or archive fields |
| `claimed` | positive equal attempts/generation; owner, claimed/last-attempt, and future lease expiry present; no eligibility/final/archive fields; prior bounded error may remain |
| `retryable` | positive equal attempts/generation; eligibility, last attempt, and bounded error present; no live claim/final/archive fields |
| `acknowledged` | positive equal attempts/generation; last attempt and final time present; no eligibility/live claim; bounded prior error and later archive marker are allowed |
| `dead_letter` | positive equal attempts/generation; last attempt, bounded error, and final time present; no eligibility/live claim; later archive marker allowed |
| `cancelled` | final time present and no eligibility/live claim; either never attempted with zero generation/no attempt evidence or positive equal attempts/generation with last-attempt evidence; later archive marker allowed |

All operational timestamps are at or after `occurred_at`; claim expiry is
strictly after claim time; finalization is not before the last attempt when one
exists; archival is not before finalization. Expired `claimed` work may recover
to `retryable`, and only an unarchived `dead_letter` terminal may be requeued,
in both cases by clearing live-claim/final fields and satisfying the retryable
shape. `acknowledged` and `cancelled` never reopen. CON-02B owns the transition
service and authorization, not this chunk.

### Required indexes

- `(event_type, delivery_state, next_attempt_at, occurred_at, event_id)` for
  deterministic eligible-work selection;
- `(aggregate_type, aggregate_id, occurred_at, event_id)` for source-aggregate
  reconciliation without inspecting payloads;
- `(claim_expires_at, event_id)` partial on `claimed` for expired-lease recovery;
- `(project_id, delivery_state, occurred_at, event_id)` for same-session drain
  counts and project-bounded observation;
- `(finalized_at, event_id)` partial on terminal rows with `archived_at IS NULL`
  for retention eligibility;
- the primary key and global unique idempotency-key constraint for replay.

## Payload and privacy contract

The generic outbox accepts only a JSON object after producer-owned typed payload
validation. Every object key must use lower ASCII snake case
`[a-z][a-z0-9_]{0,127}`. It independently rejects floats, bytes, non-JSON values, more than
16 container levels, more than 4,096 total nodes, more than 1,024 members in
one object/list, keys over 128 UTF-8 bytes, strings over 16,384 UTF-8 bytes, and
integers outside signed 38-digit magnitude. A conservative traversal budget
must prove the canonical UTF-8 encoding cannot exceed 262,144 bytes without
serializing through a second canonicalizer; PostgreSQL also checks the stored
JSONB text representation is at most 262,144 bytes.

At every nesting level the generic validator first case-folds keys and converts
hyphens to underscores for denylist comparison, then independently enforces the
lower-snake-case key grammar. It rejects credential-bearing normalized keys:
`authorization`, `cookie`, `credentials`, `password`, `secret`,
`access_token`, `refresh_token`, `id_token`, `bearer_token`, `jwks`,
`signed_url`, `raw_callback`, `raw_provider_response`, `artifact_bytes`,
`request_body`, and `response_body`. Capitalization and hyphen/underscore
variants therefore cannot bypass the privacy check. Producer payload schemas must additionally
exclude bearer tokens, credentials, key material, raw claims, provider URLs or
messages, callback bodies, artifact bytes, and unbounded/free-form sensitive
diagnostics. Bounded non-secret opaque identifiers remain allowed where their
feature specification permits them.

Validation order is structure/privacy bounds, canonical hash, then database
reservation. Invalid input and idempotency conflict raise typed exceptions
whose messages contain only stable error codes; no exception, log, result, or
failure-code field contains payload values or secrets. The outbox module emits
no logs in this chunk.

## Replay and collision matrix

Replay compares event ID, event type, event version, fixed producer, aggregate
type/ID, project, correlation, causation, idempotency key, and canonical payload
digest. It also confirms stored JSONB object equality defensively. It preserves the original
database occurrence time and ignores all operational delivery fields.

| Locked match | Result |
|---|---|
| no identity exists | insert and return `created` |
| event ID and key resolve to the same row; every immutable fact matches | return that row as `replayed` |
| either identity exists with any immutable fact/digest drift | typed `outbox_idempotency_conflict` |
| event ID and key resolve to two different rows | typed `outbox_idempotency_conflict` |

Conflict lookup locks every distinct matching row in ascending `event_id`
order. Tests cover same/same, canonical object-key reordering, same ID/different
key, different ID/same key, changed payload, changed aggregate/envelope,
pre-seeded split identities, and independent-session races in both first-reserver
commit and rollback orders. If the first reserver commits, an exact contender
replays and a changed contender conflicts. If the first reserver rolls back,
the contender inserts as `created`; rolled-back truth never produces replay or
conflict. Exactly one row is durable in either order.

## Operational transition matrix

Database checks and the custody trigger permit only these future CON-02B
transitions; this chunk exposes no transition method:

- `pending -> claimed | cancelled`;
- `claimed -> retryable | acknowledged | dead_letter | cancelled`;
- `retryable -> claimed | cancelled`;
- unarchived `dead_letter -> retryable` for later independently authorized
  recovery;
- `pending -> pending` or `retryable -> retryable` only to change eligibility
  time for later independently authorized recovery/reconciliation;
- terminal same-state update only to set the one-way `archived_at` marker.

Every claim increments attempt count and claim generation together by exactly
one. Every outcome preserves both values. They never decrease. Requeue clears
finalization and preserves attempt/generation history. `acknowledged` and
`cancelled` never reopen; archived dead letters never reopen. No state may
transition out of archival, and no same-state mutation may change immutable or
unrelated operational facts.

## Migration and transaction proof details

- Upgrade from exact revision `0026_actor_profile_lifecycle` and verify
  columns, constraints, indexes, triggers, metadata, and head identity.
- Attempt direct SQL mutation of every immutable column and physical delete/
  truncate; each must fail. Exercise every operational column through at least
  one complete legal state sequence so the allowlist is not over-constrained,
  and directly prove acknowledged/cancelled/archived reopening and illegal
  same-state mutation fail.
- A downgrade takes `ACCESS EXCLUSIVE` lock before checking emptiness. Test it
  against an uncommitted insert in both commit and rollback orders: committed
  truth blocks downgrade; rolled-back truth permits it.
- After the nonempty refusal, remove only test data with triggers explicitly
  disabled, prove empty downgrade succeeds, then restore head.
- Inject failure after append insert/flush/refresh and roll back the caller
  session; prove zero outbox row, no commit, no broker/publish/enqueue call, and
  no other observable side effect.

## Proof and reviewer routing

Required tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, docs, reuse/dedup, test-delta, and CI integrity. Review must focus
on caller transaction ownership, PostgreSQL duplicate-race behavior, immutable
versus operational field separation, payload privacy/integrity, forward
compatibility with 02B without implementing it, migration downgrade safety,
and preservation of the exact chunk boundary.

## Review result

PASS after repair. Initial review found that the migration-free 02B schema,
retention/delete behavior, replay collision matrix, payload/privacy bounds,
aggregate identity, terminal recovery rules, and rolled-back-reserver outcome
were underspecified. The frozen schema, operational transition matrix, privacy
contract, collision matrix, and proof details above resolve every finding.
Architecture, senior engineering, reuse/dedup, QA/test, product/ops, docs,
security/auth, and CI integrity all returned PASS before implementation began.

After implementation began, ART PR #141 and AUTH-09D-A advanced trusted `main`
and moved CON through historical revisions 0026 and 0027. Contributor-
foundation PR #153 now owns AUTH revision `0027_contributor_foundation`.
Reconciliation preserves the reviewed schema and behavior while moving only
CON's revision identity and parent to linear
`0028_shared_transactional_outbox`. None of these merges adds a shared outbox
or CON authorization seam, so no implementation boundary or non-goal changes.
Final exact-SHA review must cover this current-main reconciliation.
