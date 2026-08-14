# Chunk Contract: WS-ARCH-001-CP02 — Hidden Adapter-Binding Behavior

Status: proposed executable contract; implementation may begin only after this
planning correction merges and receives explicit human approval. Risk: L1.

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
backend/app/modules/compensation/__init__.py
backend/app/modules/compensation/api/__init__.py
backend/app/modules/compensation/api/adapter_bindings.py
backend/app/modules/compensation/models.py
backend/app/modules/compensation/repository.py
backend/app/modules/compensation/service.py
backend/app/modules/compensation/schemas.py
backend/app/modules/actors/api/__init__.py
backend/app/modules/actors/api/compensation_adapter.py
backend/app/modules/projects/api/__init__.py
backend/app/modules/projects/api/compensation_binding.py
backend/tests/compensation/test_adapter_binding_api.py
backend/tests/compensation/test_adapter_binding_service.py
backend/tests/compensation/test_adapter_binding_persistence.py
backend/tests/architecture/test_module_boundaries.py
backend/tests/test_compensation.py (removal/replacement of superseded 03A proof only)
backend/tests/conftest.py (schema fingerprint and reset inventory parity only)
backend/tests/test_database_reset.py (new-table reset/guard proof only)
.ci/behavior-ownership/** (exact generated/owned-test parity only)
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json (generated parity only)
backend/alembic/baseline/** (generated schema-manifest parity only; do not rewrite 0001)
docs/spec_contribution_compensation.md
docs/spec_authorization_service.md
docs/operations_authorization_service.md
docs/roadmap_status.md
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/{CHUNK_MAP,STATUS,RISKS,DECISIONS}.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-CP02-con-binding-behavior.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP02-*.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/{CHUNK_MAP,STATUS,AUTHORIZATION_HANDOFF,CONFORMANCE_MATRIX,RUNTIME_VERIFICATION}.md
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

Requests carry exact UUID identities plus a server-owned operation identity and
canonical request digest. Create carries `instrument_type` unchanged and never
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
2. Generate the binding ID server-side and preserve the caller's operation
   identity/request digest.
3. Obtain exact PROJECTS and ACTORS eligibility facts through public ports.
4. Lock/serialize the project plus `instrument_type` creation boundary.
5. Build AUTH facts with exact `project_id`, generated
   `adapter_binding_id`, unchanged `instrument_type`, eligible
   `adapter_actor_id`, and the unchanged canonical non-secret `route_key`.
6. Prepare and consume authority before inserting product state.
7. Insert one active/version-1 binding and one immutable created event.
8. Flush only. The lifecycle-event table enforces global uniqueness of
   `operation_id`. The repository checks that identity before mutation; any
   duplicate, including an exact retry, returns the same bounded
   already-processed conflict without disclosing the prior binding or event.
   It never replays a success response or creates a second effect.

### Suspend

1. Require one caller-owned root transaction.
2. Lock by exact `(project_id, adapter_binding_id)`.
3. Require active status and the exact positive expected lifecycle version.
4. Recompose facts from the locked row and compare them to the request.
5. Prepare and consume authority before mutation.
6. Transition `active/N -> suspended/N+1`, set current
   `suspended_by/suspended_at` from the authorized actor and database clock,
   and append one immutable suspended event.
7. Flush only.

### Resume

1. Require one caller-owned root transaction.
2. Lock by exact `(project_id, adapter_binding_id)`.
3. Require suspended status and the exact positive expected lifecycle version.
4. Fail if another active binding exists for the same project and
   `instrument_type`.
5. Recompose facts from the locked row, prepare, and consume before mutation.
6. Transition `suspended/N -> active/N+1`, clear current suspension fields,
   and append one immutable resumed event containing the prior suspension and
   exact actor/version transition.
7. Flush only.

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
immediately preceding suspended event for the same binding and
`from_lifecycle_version`; that immutable suspended event remains the source of
the cleared suspension actor/time. Events are product lifecycle truth, not
authorization decisions. CP03 separately proves AUTH allowed-decision evidence
is staged atomically by the real PREP consumer in the same transaction. Planned
actions cannot produce allowed AUTH evidence before CP03 activation.

## Migration `0004_compensation_adapter_binding_lifecycle`

The migration follows `0003_submission_lineage` and must update ORM metadata,
database constraints/triggers, schema manifests, and PostgreSQL tests together.
It must:

- replace the active/version-1-only lifecycle shape with exact active and
  suspended shapes;
- replace `compensation_binding_updates_deferred` with a fail-closed trigger;
- permit only `active/N -> suspended/N+1` and
  `suspended/N -> active/N+1`;
- require database-owned transition timestamps and exact attribution fields;
- reject version skips, same-state updates, retired transitions, arbitrary
  updates, and changes to binding/project/instrument/adapter/route/creation
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
- Concurrent create for one project/instrument produces one active binding.
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
uv run pytest -q tests/test_schema.py tests/test_schema_baseline.py tests/test_schema_baseline_manifest.py
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

- Outcome on merge: `planned`
- The planned CP02 boundary has an executable implementation contract.
- Runtime behavior changed by this planning correction: no.
