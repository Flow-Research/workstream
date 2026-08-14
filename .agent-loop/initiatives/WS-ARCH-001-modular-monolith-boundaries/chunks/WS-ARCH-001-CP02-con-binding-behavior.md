# Chunk Contract: WS-ARCH-001-CP02 — Hidden Adapter-Binding Behavior

Status: complete on implementation merge; CP03 is the next activation gate.
Risk: L1.

## Goal

Implement CON-owned, route-unreachable create/read/suspend/resume behavior for
`ProjectCompensationAdapterBinding` while all four registered AUTH actions
remain unavailable. Prove the complete product state machine, public module
boundaries, PostgreSQL guards, immutable lifecycle history, and deny-default
authorization seams before CP03 installs real AUTH adapters and activates the
actions.

## Why this correction exists

The former skeleton was not executable. It did not distinguish request-scoped
read authorization from PREP mutations, name public ports, define the database
transition that replaces the deferred-update trigger, preserve lifecycle
history, or prevent unrelated internal service actors from becoming
compensation adapters.

Current main also proves that:

- migration head is `0003_submission_lineage`;
- the database permits only active/version-1 bindings and rejects every update;
- CP01A registered four actions as planned/unavailable;
- CP01C corrected create facts to the exact CON-owned `instrument_type` name;
- AUTH public ports expose preparation but not a public domain-specific
  consume/close protocol;
- existing ART and REV service identities are not compensation-adapter
  identities and must never substitute.

## Outcome on implementation merge

- Hidden CON behavior is complete and route-unreachable.
- Production composition remains deny-default.
- All four actions remain planned/unavailable.
- CP03 becomes the next gate and must install the real AUTH/ACTORS adapters,
  approved compensation-adapter identity rule, atomic authorization evidence,
  and exact activation before any surface becomes usable.

## Risk class

L1: authorization, payments-adjacent configuration, immutable audit history,
concurrency, schema, and cross-module public APIs.

## Allowed files

```text
backend/alembic/versions/0004_compensation_adapter_binding_lifecycle.py
backend/alembic/env.py (current-head guard update only)
backend/app/modules/compensation/__init__.py
backend/app/modules/compensation/api/__init__.py
backend/app/modules/compensation/api/adapter_bindings.py
backend/app/modules/compensation/models.py
backend/app/modules/compensation/repository.py
backend/app/modules/compensation/service.py
backend/app/modules/compensation/schemas.py
backend/app/db/models.py (new lifecycle-event metadata registration only)
backend/app/modules/actors/api/__init__.py
backend/app/modules/actors/api/compensation_adapter.py
backend/app/modules/projects/api/__init__.py
backend/app/modules/projects/api/compensation_binding.py
backend/tests/compensation/test_adapter_binding_api.py
backend/tests/adapter_binding_fixtures.py (shared CP02 PostgreSQL facts only)
backend/tests/adapter_binding_test_support.py (strict CP02 test doubles only)
backend/tests/compensation/test_adapter_binding_service.py
backend/tests/compensation/test_adapter_binding_recovery.py
backend/tests/compensation/test_adapter_binding_persistence.py
backend/tests/architecture/test_module_boundaries.py
backend/tests/compensation/test_adapter_binding_partition.py (exact CP02 additive partition proof only)
backend/tests/compensation/test_adapter_binding_owner_fences.py
backend/tests/test_compensation.py (removal/replacement of superseded 03A proof only)
backend/tests/conftest.py (schema fingerprint and reset inventory parity only)
backend/scripts/run_test_lanes.py (exact new-test lane assignment only)
backend/tests/test_database_reset.py (new-table reset/guard proof only)
backend/tests/test_alembic.py (HEAD_REVISION and 0003-to-0004 empty/non-empty upgrade proof only)
.ci/behavior-ownership/lifecycle/adapter-binding-behavior.json (new exact ownership entry only)
.ci/behavior-ownership/partition.v1.json (exact generated partition parity only)
backend/scripts/behavior_ownership.py (exact CP02 additive target allowlist only)
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json (generated parity only)
backend/alembic/baseline/v01_approved_manifest_delta.json (generated parity only)
backend/alembic/baseline/v01_baseline_manifest.json (generated parity only)
backend/alembic/baseline/v01_pre_reset_source_manifest.json (generated parity only)
backend/alembic/baseline/v01_schema.sql (generated parity only; do not rewrite 0001)
docs/spec_contribution_compensation.md
docs/architecture_data_model.md
docs/roadmap_status.md
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/STATUS.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-CP02-con-binding-behavior.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP02-implementation-review-evidence.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP02-external-review-response.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP02-pr-trust-bundle.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/CHUNK_MAP.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/STATUS.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/AUTHORIZATION_HANDOFF.md
```

The implementation plan review must remove any unused allowance before code is
written. New files remain subject to the repository size and behavior-ownership
gates.

## Not allowed

```text
HTTP routes or public reachability
AUTH catalogue, evaluator, grant, role, identity, matrix, availability, runtime, repository, or prepared-service edits
imports from AUTH, ACTORS, or PROJECTS private modules
construction, copying, serialization, or persistence of AUTH handles
CON-local authorization evaluation or role inspection
generic active-service eligibility or reuse of ART/REV service identities
adapter-binding retirement
ContributionPolicy commands or policy activation
award creation, fulfillment, callbacks, delivery, provider calls, credentials, endpoints, accounts, balances, or ledger references
ContributionRecord, Review, Task, Assignment, Submission, reputation, or project-guide behavior
compatibility aliases for `instrument`, `unit`, retired facts, or old lifecycle paths
independent commit inside any service, repository, authorization participant, or lifecycle-event participant
```

## Public CON surface

`app.modules.compensation.api` exposes dependency-light immutable types only:

- `AdapterBindingCreateRequest`;
- `AdapterBindingReadRequest`;
- `AdapterBindingSuspendRequest`;
- `AdapterBindingResumeRequest`;
- `AdapterBindingView`;
- `AdapterBindingMutationResult`;
- `AdapterBindingReadAuthorizationPort`;
- `AdapterBindingMutationAuthorizationPort`;
- `AdapterBindingProjectEligibilityPort`;
- `AdapterBindingActorEligibilityPort`;
- bounded unavailable/conflict errors.

`AdapterBindingMutationResult` is immutable and contains exactly
`event_id`, `operation_id`, `request_digest`, `project_id`,
`adapter_binding_id`, `event_type`, `actor_profile_id`, `from_status`,
`to_status`, `from_lifecycle_version`, `to_lifecycle_version`,
`prior_suspension_event_id`, and `occurred_at`. It contains no mutable current
binding status or suspension projection. The created result/event uses
`from_status = null`,
`to_status = active`, `from_lifecycle_version = 0`, and
`to_lifecycle_version = 1`, with `prior_suspension_event_id = null`.

Mutation requests carry exact UUID identities plus one stable `operation_id`
supplied by the trusted server-side command caller and preserved unchanged on
every retry. External clients never choose it directly; a future route may
derive it once from its validated idempotency contract before calling CON. CON
computes the canonical `request_digest` from the immutable request fields and
rejects any supplied digest field. Create carries `instrument_type` unchanged and never
contains `unit`. `route_key` uses the existing CON contract exactly: 1-120
characters, begins with an ASCII letter, contains only ASCII letters, digits,
`.`, `_`, `:`, or `-`, and never contains `..`. It is a non-secret configured
adapter selector, not a URL, credential, provider account, or service identity.
Mutation requests carry the authenticated actor profile ID;
the injected authorization port must bind and return that same actor before CON
may use it for lifecycle attribution.

The public authorization port is domain-specific and opaque:

```text
prepare(exact action facts + actor + operation context) -> object
consume(object, the same exact facts + actor + operation context) -> authorized actor
close(object) -> None
```

CON neither recognizes nor constructs the concrete object. Production defaults
deny. CP02 fakes must enforce identity, action, actor, project, facts, operation,
session/transaction, single consumption, replay rejection, and close
invalidation. CP03 later implements this port using the existing AUTH PREP
machinery; it must not introduce a second authorization protocol.

Every object returned by `prepare` is closed exactly once from an unconditional
`finally` around `consume`, before any product mutation or lifecycle-event
insertion. Consume success, denial, or exception all close the object. Closing
a consumed object is required cleanup, not a second consumption. Recovery never
prepares a mutation object. A `close` exception fails the command before product
mutation and forces the caller-owned root transaction to roll back any staged
AUTH evidence; it is never suppressed. After successful close, a later product
failure rolls back the transaction while the authorization object remains
invalid. Tests must prove these exact paths and that no failed or rolled-back
path leaves reusable authority.

Read uses a separate request-scoped authorization port before disclosure. It
does not prepare or consume a handle.

## External owner capabilities

Create depends on narrow public owner facts rather than foreign repositories:

- PROJECTS confirms the exact project is eligible for compensation binding;
- ACTORS confirms `adapter_actor_id` is an active service actor explicitly
  eligible for compensation-adapter binding.

Neither port returns private models. Generic `actor_kind=service` is
insufficient. Existing ART, REV, checker, dispatcher, or other internal service
identities must fail. CP03 must not activate create until AUTH/ACTORS has an explicitly
approved compensation-adapter identity rule and real adapter composition.

PROJECTS and ACTORS eligibility ports must acquire owner-controlled database
row locks or equivalent transaction-scoped eligibility fences in the fixed
order PROJECTS then ACTORS. Those fences remain held until the caller-owned
root transaction commits or rolls back. Lockless revalidation is forbidden:
eligibility cannot change between the accepted owner fact, AUTH consumption,
and binding insertion.

## Mutation idempotency and recovery

Every mutation follows one shared order:

```text
caller-owned root transaction
-> canonical request digest
-> operation fence
-> lifecycle-event recovery check
-> operation-specific owner/product locks
-> AUTH prepare
-> AUTH consume
-> unconditional close
-> mutation plus immutable lifecycle event
-> flush only
```

The operation fence is exactly a PostgreSQL transaction-level advisory lock
whose signed 64-bit key is the first eight bytes of SHA-256 over the canonical
16 UUID bytes of `operation_id`, interpreted as a signed big-endian integer by
one repository-owned helper. It is acquired with `pg_advisory_xact_lock` and
remains held until the root transaction commits or rolls back. A key collision
may only serialize unrelated operations; it cannot equate them or
authorize/recover an effect because every lookup and the
database uniqueness constraint still compare the complete UUID. An in-process
mutex, event-table lookup alone, or eventual unique-constraint failure is not
an acceptable substitute.

Before binding-ID generation, owner eligibility reads, product row locks, AUTH
preparation, or AUTH consumption, the fenced mutation checks the lifecycle-event
repository by the complete globally unique `operation_id`.

- No event: continue the canonical mutation while retaining the operation fence
  until transaction end.
- Existing event with a different action/event type, actor, project, request
  digest, or immutable binding facts: return the same concealed conflict.
- Exact existing event: join its exact binding and authorize request-scoped read
  of that exact `(project_id, adapter_binding_id)` before returning the stable
  original `AdapterBindingMutationResult`. Reconstruct that result only from
  the immutable lifecycle event and immutable binding identity fields, never
  from mutable current lifecycle state. A revoked, inactive, unauthorized,
  cross-project, or mismatched caller receives the same concealed conflict.

Recovery performs no mutation PREP preparation/consumption, creates no new AUTH
allowed-mutation evidence, and changes no binding or lifecycle event. This is
the sole recovery path after an unknown commit; callers need only retain the
stable `operation_id`. Concurrent duplicates wait on the same operation fence,
then observe either the committed event or no event after rollback.

## Canonical behavior

### Read

1. Validate UUID-only selectors.
2. Request-scope authorize the exact `(project_id, adapter_binding_id)` before
   revealing CON state.
3. Load by the exact project/binding pair.
4. Return only non-secret canonical fields: binding/project IDs,
   `instrument_type`, adapter actor ID, route key, status, lifecycle version,
   created fields, and current suspension fields. Existing retirement columns
   remain null and persistence-only until a later reviewed retirement chunk.
5. Cross-project, absent, and unauthorized cases use the same bounded concealed
   result and reveal no row existence.

### Create

1. Require one caller-owned root transaction; nested or missing transactions
   fail before reads or writes.
2. Compute the canonical request digest, acquire/check the operation fence, and
   complete concealed authorized recovery when the operation already exists.
3. Only for a new operation, generate the binding ID server-side.
4. Obtain and retain exact PROJECTS then ACTORS transaction-bound eligibility
   locks/fences through transaction end.
5. Lock/serialize the project plus `instrument_type` creation boundary.
6. Build AUTH facts with exact `project_id`, generated
   `adapter_binding_id`, unchanged `instrument_type`, eligible
   `adapter_actor_id`, and the unchanged canonical non-secret `route_key`.
7. Prepare and consume authority, and unconditionally close the prepared
   object, before inserting product state.
8. Only after successful close, insert one active/version-1 binding and one
   immutable created event.
9. Flush only. The lifecycle-event table independently enforces globally unique
   `operation_id`; the operation fence and database constraint together prove
   one mutation effect.

### Suspend

1. Require one caller-owned root transaction.
2. Compute the canonical request digest, acquire/check the operation fence, and
   complete concealed authorized recovery when the operation already exists.
3. Only for a new operation, lock by exact
   `(project_id, adapter_binding_id)`. Suspend deliberately performs no owner
   eligibility check so an authorized Finance Authority can disable a binding
   after its project or adapter actor becomes ineligible.
4. Require active status and the exact positive expected lifecycle version.
5. Recompose facts from the locked row and compare them to the request.
6. Prepare and consume authority, then close the prepared object from the
   unconditional `finally` around consume.
7. Only after successful close, transition `active/N -> suspended/N+1`, set current
   `suspended_by/suspended_at` from the authorized actor and database clock,
   and append one immutable suspended event.
8. Flush only.

### Resume

1. Require one caller-owned root transaction.
2. Compute the canonical request digest, acquire/check the operation fence, and
   complete concealed authorized recovery when the operation already exists.
3. Only for a new operation, acquire the PROJECTS eligibility fence, read the
   exact binding identity without disclosure, acquire the ACTORS eligibility
   fence for that bound adapter actor, then lock the exact
   `(project_id, adapter_binding_id)` row and prove its identity fields are
   unchanged. These are the same fixed-order, transaction-retained owner fences
   used by create. The project must remain eligible and the exact bound adapter
   actor must remain active and adapter-eligible. Either failure denies before
   AUTH consumption.
4. Require suspended status and the exact positive expected lifecycle version.
5. Fail if another active binding exists for the same project and
   `instrument_type`.
6. Recompose facts from the locked row, prepare, consume, and close from the
   unconditional `finally` around consume.
7. Only after successful close, transition `suspended/N -> active/N+1`, clear
   current suspension fields,
   and append one immutable resumed event containing the prior suspension and
   exact actor/version transition.
8. Flush only.

Creating a replacement active binding while an older binding is suspended is
allowed. It does not retire, supersede, or mutate the suspended binding.
Resuming the older binding while the replacement remains active conflicts.

## Immutable lifecycle history

CP02 adds a CON-owned append-only adapter-binding lifecycle event. Each event
contains:

```text
event_id
operation_id
request_digest
project_id
adapter_binding_id
event_type: created | suspended | resumed
actor_profile_id
from_status / to_status
from_lifecycle_version / to_lifecycle_version
prior_suspension_event_id (required for resumed; null otherwise)
occurred_at (database time)
```

`operation_id` is globally unique across adapter-binding lifecycle events.
There is exactly one event for each binding lifecycle version. Updates and
deletes fail at the database boundary. A resumed event must reference the exact
immediately preceding suspended event for the same binding, and
`prior_suspended_event.to_lifecycle_version` must equal
`resumed_event.from_lifecycle_version`. That immutable suspended event remains the source of
the cleared suspension actor/time. Events are product lifecycle truth, not
authorization decisions. CP03 separately proves AUTH allowed-decision evidence
is staged atomically by the real PREP consumer in the same transaction. Planned
actions cannot produce allowed AUTH evidence before CP03 activation.

## Migration `0004_compensation_adapter_binding_lifecycle`

The migration follows `0003_submission_lineage` and must update ORM metadata,
database constraints/triggers, schema manifests, and PostgreSQL tests together.
It must:

- fail closed before any schema mutation when
  `project_compensation_adapter_bindings` is non-empty; v0.1 has no deployed
  compatibility obligation or truthful source for inventing historical
  operation IDs, request digests, or created events;
- prove both upgrade cases: an empty table upgrades atomically, while a
  non-empty table leaves the complete `0003_submission_lineage` schema and data
  unchanged and requires database recreation;
- update `backend/tests/test_alembic.py::HEAD_REVISION` to
  `0004_compensation_adapter_binding_lifecycle` and prove the single-head graph;
- update `backend/alembic/env.py::_CURRENT_HEAD_REVISION` to
  `0004_compensation_adapter_binding_lifecycle`; no second head constant or
  compatibility path is permitted;
- replace the active/version-1-only lifecycle shape with exact active and
  suspended shapes;
- replace `compensation_binding_updates_deferred` with a fail-closed trigger;
- permit only `active/N -> suspended/N+1` and
  `suspended/N -> active/N+1`;
- require database-owned transition timestamps and exact attribution fields;
- reject version skips, same-state updates, retired transitions, arbitrary
  updates, and changes to binding/project/`instrument_type`/adapter/route/creation
  identity;
- preserve the one-active-binding partial unique index;
- add the append-only lifecycle-event table, unique binding/version rule,
  globally unique operation identity, same-binding prior-suspension reference,
  foreign keys, and update/delete rejection;
- provide no downgrade compatibility; v0.1 downgrade continues to require
  database recreation.

## Required fail-closed proof

- Wrong actor, action, project, binding, status, lifecycle version, operation,
  request digest, session, transaction, or authorization object denies.
- Copied, serialized, replayed, consumed, or closed authorization objects deny.
- Cross-project and absent reads/mutations are concealed.
- Denial occurs before binding mutation and lifecycle-event insertion.
- Stale and concurrent suspend/resume attempts produce one transition.
- Concurrent create for one project/`instrument_type` produces one active binding.
- Concurrent project ineligibility or adapter-actor revocation blocks on the
  retained owner fence; once it commits first, create denies before AUTH
  consumption, and when create holds the fence first, revocation cannot commit
  between eligibility proof and binding insertion.
- Resume concurrency proof separately requires: project ineligibility committed
  first denies before AUTH consumption; adapter-actor revocation committed
  first denies before AUTH consumption; when resume holds PROJECTS then ACTORS
  fences first, neither eligibility change can commit between validation and
  the binding transition; and every such denial creates no resumed event,
  allowed AUTH evidence, or binding state/version change.
- Duplicate operations are rejected or recovered before binding-ID generation
  and mutation AUTH preparation/consumption; they create no new allowed mutation
  evidence, binding, or lifecycle event.
- Exact duplicate recovery returns the immutable original result only after
  current request-scoped authorization of the exact binding. Changed facts,
  revocation, inactivity, cross-project access, or failed read authorization
  return the same concealed conflict. Recovery performs no mutation PREP and
  creates no new AUTH evidence or product effect.
- Concurrency tests cover create, suspend, and resume duplicates using the
  exact PostgreSQL advisory fence; a losing request observes the committed
  event after waiting or proceeds only after the winner rolls back.
- Every prepared mutation object is closed through the `finally` surrounding
  consume before product mutation. Consume denial/exception and close failure
  produce no product effect; later product failure rolls back staged AUTH
  evidence and cannot make the already-closed object reusable.
- Active replacement blocks resume of an older suspended binding.
- PostgreSQL independently rejects forbidden row/event mutations.
- Rollback removes binding changes, lifecycle events, and staged participant
  effects together.
- No denial produces allowed AUTH evidence.

## Verification commands

```bash
cd backend
uv run ruff check app/modules/compensation app/modules/actors/api app/modules/projects/api tests/compensation
uv run pytest -q tests/compensation tests/test_compensation.py
uv run pytest -q tests/authorization/test_adapter_binding_registration.py
uv run pytest -q tests/test_alembic.py
uv run pytest -q tests/test_database_reset.py
uv run python -m scripts.module_boundaries validate --protected-base "$(git merge-base HEAD origin/main)"
uv run python -m scripts.authorization_boundary validate --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md
uv run python -m scripts.test_structure_boundary validate --policy ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_POLICY.md --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
uv run python -m scripts.behavior_ownership validate
cd ..
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
python3 scripts/check_markdown_links.py --changed-from origin/main
git diff --check
```

Hosted Backend semantic lanes and the full coverage aggregate remain mandatory.
No local full-suite run is required on the user's slow machine.

## Required reviewers

- architecture;
- security/authorization;
- product/operations;
- QA;
- test delta;
- CI integrity;
- reuse/dedup;
- senior engineering;
- documentation.

## Human review focus

- CON lifecycle truth versus AUTH decision authority remains separated.
- `instrument_type` is copied unchanged; no mapping layer or `unit` alias exists.
- read is query authorization while mutations use opaque PREP integration.
- unrelated service identities cannot become adapter bindings.
- lifecycle history and authorization evidence are distinct and atomic on
  eventual activation.
- CP02 remains hidden/unavailable and CP03 is the only activation successor.

## Stop conditions

Stop if implementation requires an AUTH-private import, generic service-actor
eligibility, action activation, a second PREP implementation, provider access,
retirement behavior, non-atomic lifecycle history, CI weakening, or schema
changes beyond the exact adapter-binding aggregate and its immutable events.

## Merge state

- Outcome on merge: `complete`
- Hidden CON adapter-binding behavior and immutable lifecycle history are implemented.
- Runtime remains route-unreachable and deny-default; all four AUTH actions remain unavailable.
