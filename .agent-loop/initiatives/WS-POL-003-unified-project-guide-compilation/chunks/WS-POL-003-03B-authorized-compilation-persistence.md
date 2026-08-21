# Chunk Contract: WS-POL-003-03B - Authorized Compilation Persistence

Status: Preimplementation review findings resolved; runtime not implemented.
Risk: L1.

## Outcome

Make the merged hidden POL-03A compilation custody usable under the exact
merged AUTH-12I request and execute capabilities. The chunk adds one
PROJECTS-owned transactional coordinator that:

1. atomically binds an authorized Project Manager request to the only attempt
   for one setup generation;
2. gives the fixed `workstream.project.setup` service a short-transaction
   execute preflight and commits a durable may-have-dispatched fence before any
   later provider call;
3. records one known provider result under the original attempt and provider
   key; and
4. consumes fresh, result-bound execute authority in the same root transaction
   that inserts the immutable compilation and completes the attempt.

The capability remains hidden. This chunk does not call a model, enqueue work,
add a route, project policy, approve a guide, or make setup live.

## Authoritative starting point

- Contract refresh base: `c716fa424c1a86bda9e0f85c77c307fa07172bca`.
- POL-03A prerequisite: merge commit `5e459a8f`; its hidden attempt,
  compilation, validator, repository, and AUTH public facts are present.
- AUTH-12I prerequisite: merge commit `98eae13e`; the exact request/execute
  catalogue entries and production authorization adapter are present.
- Current schema head: `0007_contribution_policy_publication_custody`.
- If schema custody described below is required, this chunk alone allocates
  `0008_guide_compilation_authorized_persistence` with `down_revision` equal to
  the current sole head. Implementation must stop and re-plan if main changes
  the sole head before work starts.
- GitHub had no open pull request at contract refresh. Open pull requests, not
  this document, remain authoritative for transient ownership.

## Scope and ownership

### PROJECTS/POL owns

- the exact request-operation receipt and its database constraints;
- attempt reservation, state locking, result validation, terminal failure,
  recovery classification, append-only compilation persistence, and lineage
  compare-and-swap;
- the coordinator's root transaction and rollback behavior; and
- server-derived request facts, attempt identity, provider key, accepted result
  hashes, and bounded receipts.

The coordinator is internal to
`app.modules.projects.guide_compilation`. POL-03B adds **no public Projects
port** because it has no cross-module or delivery consumer. POL-04A, not this
chunk, owns the later worker-facing Projects API and owner composition-root
wiring. Tests may construct the internal coordinator with the production AUTH
adapter; application delivery code may not import it yet.

### AUTH owns

- `ProjectGuideCompilationAuthorizationPort` and all public request,
  preflight, and persist fact types in
  `app.modules.authorization.api.project_guide_compilation`;
- Project Manager grant evaluation, fixed-service matrix evaluation, prepared
  handle custody, and allowed/denied authority evidence; and
- the production adapter in `app.modules.authorization.guide_compilation`.

POL consumes only that frozen public AUTH Protocol. It must not import an AUTH
model, repository, kernel, prepared service, concrete handle, concrete adapter,
or private resource context. This chunk changes no AUTH public method or fact
shape and no AUTH catalogue, evaluator, policy, runtime, service matrix, or
schema vocabulary.

The POL-03A `DenyProjectGuideCompilationAuthorization` was an intentionally
temporary seam while AUTH-12I was unavailable. AUTH-12I is now merged, so 03B
deletes that class/module and replaces its old behavior test with a
syntax-aware assertion that no production or test consumer imports the retired
seam. It is not retained as an alias, fallback, or second adapter.

### Composition boundary

The coordinator constructor accepts the frozen AUTH public Protocol and a
caller-provided `AsyncSession`/session factory only as required by the exact
operation. It creates repositories inside its own root transaction. No
repository, session, prepared handle, authorization context, workspace, raw
guide, provider result, or model client is returned or serialized.

There is no application composition-root change in this chunk. POL-04A must
compose the internal capability behind a typed Projects public API from
`app/adapters/projects/__init__.py`; workers must consume that future API rather
than these private files.

## Exact durable request-operation receipt

POL-03A reserved attempts but deliberately did not persist the request
operation or the allowed request decision. AUTH-12I therefore cannot yet prove
that concurrent prepared request handles commit at most one mutation and one
allowed event. POL-03B closes only that gap with the exact
`project_guide_compilation_request_operations` table.

Each immutable row contains only:

- `operation_id` as the primary key;
- `request_id` and `idempotency_key`;
- requesting human `actor_profile_id` and `identity_link_id`;
- exact `project_id`, `guide_id`, `source_snapshot_id`, `setup_run_id`, and
  positive `setup_generation` selectors;
- optional exact `expected_predecessor_compilation_id`;
- `request_facts_digest` from the merged public AUTH helper;
- the unique bound `attempt_id`;
- the exact allowed request `authorization_decision_event_id`; and
- database-owned `created_at`.

Database uniqueness covers the operation ID, the actor-scoped request ID, the
actor-scoped idempotency key, and the attempt ID. Foreign keys bind the exact
project/guide/snapshot/setup/attempt identities. A database trigger validates
that the referenced audit event is allowed, uses action and permission
`project.guide_compilation.request`, resource type
`project_guide_compilation_request`, resource ID equal to `operation_id`, the
same project/actor/link, and a resource-context digest containing the exact
request-facts digest. The row is insert-only; update, delete, and truncate fail
closed.

Migration 0008 installs two PROJECTS-owned, domain-specific SQL digest
functions: one reconstructs the exact no-whitespace, sorted-key UTF-8 preimage
used by `project_guide_compilation_facts_digest` from the operation and bound
attempt columns; the second reconstructs the exact preimage used by
`project_guide_compilation_request_authority_digest` from that facts digest,
the operation actor/link/project/operation values, and the audit event's
matched Project Manager grant. Both use PostgreSQL's built-in
`sha256(bytea)` plus `encode(..., 'hex')`; no extension or general digest
framework is added. The custody trigger first requires the stored facts digest
to equal the first function, then requires the event's
`after_facts.resource_context_digest` to equal the second. Golden parity tests
compare both SQL functions with the merged Python public helpers for null and
non-null predecessors and independently mutate every input. Thus PostgreSQL,
not an ORM or narrative assertion, proves the digest preimage and exact
identity-link/request-facts binding.

This is not a generic operation framework. It has no JSON request body, status
machine, response cache, arbitrary action, arbitrary resource, delivery state,
or reusable outbox abstraction.

## Transaction protocol

Every method requires a session with no active transaction, opens exactly one
root transaction for its mutation, and lets that root context commit or roll
back. Repositories and AUTH never commit independently.

### A. Authorized request or exact recovery

Input is the authenticated human actor, complete
`ProjectGuideCompilationRequestFacts`, and the server-derived
`CompilationAttemptIdentity` whose values must match the facts exactly.

1. Read an existing operation by operation ID and actor-scoped request and
   idempotency identities.
2. If one committed row exists, compare every immutable selector and the
   request-facts digest. Exact replay returns only its bounded attempt/provider
   identifiers and current recovery classification. A changed or crossed
   replay fails closed. Recovery creates no AUTH event, attempt, outbox row, or
   external effect.
3. For a new operation, prepare request authority in the root transaction.
4. Reserve the exact attempt through the merged POL-03A repository.
5. Reject `mismatch`. Reject an `existing` attempt without the exact immutable
   operation receipt; POL-03B must not adopt pre-authorized or legacy custody.
6. Consume the prepared request handle and insert the operation receipt bound
   to the returned allowed decision-event UUID.
7. Commit the attempt, operation receipt, and allowed event atomically.

If a concurrent identical caller wins after preparation, the losing root
transaction, including its tentative allowed event, rolls back. A fresh root
transaction then reloads and returns the winner's exact receipt. Constraint
errors are classified by exact constraint name; unknown storage errors remain
storage errors and are never reported as successful replay.

An exact committed replay is receipt recovery, not a new privileged mutation.
It does not reauthorize or expose compilation content. Revocation is still
checked before any future dispatch fence or final persistence.

### B. Fixed-service execute preflight and dispatch fence

Input is the fixed service actor plus complete
`ProjectGuideCompilationExecutePreflightFacts`.

1. Open a fresh root transaction and lock the attempt and its exact request
   operation.
2. Rebuild facts from durable server-owned state and reject caller/fact drift,
   stale setup/source/catalogue/agent lineage, missing request custody, wrong
   predecessor, wrong attempt/key, wrong actor/link/service, or a state other
   than `compilation_reserved`.
3. Call AUTH's non-evidencing `authorize_execute_preflight`.
4. Transition `compilation_reserved` to
   `compilation_provider_uncertain` and commit.
5. Return only a bounded dispatch receipt containing operation, attempt, and
   provider-idempotency UUIDs plus the recovery classification.

`compilation_provider_uncertain` is deliberately conservative: after the
commit, provider dispatch **may** have begun. A future caller may attempt the
external call only after receiving this committed receipt. A crash between the
commit and the call can strand the attempt, but cannot create a duplicate
provider attempt. Safety is preferred to silent redispatch.

The current `ProjectGuideAgentRuntime.compile_project_guide` boundary is a
one-shot call: it accepts no application idempotency key and exposes no
retrieve/reconcile operation. The current OpenAI adapter therefore does not
prove application-level same-key replay across process failure. POL-03B must
not pretend otherwise. From `compilation_provider_uncertain`, this chunk
returns `provider_outcome_unresolved` and never allocates a new key or directs a
redispatch. Any future same-key reconciliation requires a separately reviewed
provider-port capability and proof before POL-04A may rely on it.

### C. Known provider outcome custody

POL-03B itself never calls the provider. After a future POL-04A caller has a
known result, it invokes one of two fixed-service methods in a fresh root
transaction:

- `record_accepted_result` locks the exact uncertain attempt, rebuilds and
  reauthorizes execute preflight, strictly validates the complete result
  against the original context and hashes, and stores the accepted canonical
  result using the existing POL-03A transition; or
- `record_invalid_result` locks the exact uncertain attempt, rebuilds and
  reauthorizes execute preflight, maps only the existing allowlisted validation
  failure codes, and records the existing terminal-invalid transition.

No arbitrary provider error, text, trace, prompt, URL, path, credential, or
exception is durable. A transport timeout, connection loss, process crash, or
caller cancellation after the dispatch fence leaves the state uncertain; it
is not rewritten as invalid or retried.

### D. Fresh final authorized persistence

For `provider_result_accepted`:

1. Open a new root transaction, lock the exact attempt and request operation,
   and reload current setup/source and append-only predecessor lineage.
2. Revalidate the stored canonical result from its original strict context and
   recompute every full/component hash.
3. Build complete `ProjectGuideCompilationExecutePersistFacts` from durable
   values, including its canonical resource-context digest.
4. Prepare and consume fresh execute authority for the fixed service.
5. Insert the immutable compilation and transition the attempt to
   `compilation_persisted` through the existing repository.
6. Commit the allowed execute event, compilation, and attempt transition
   atomically.

Concurrent final callers may prepare independently, but only the winner's root
transaction commits. The loser rolls back its event and returns the winner's
bounded persisted receipt only after a fresh reload verifies exact identity.
Exact persisted replay creates no second event or mutation and returns no raw
result. Stale predecessor, changed authority, changed result/hash, or lineage
drift denies with no allowed event or product write.

## Closed invariants

### Authority and tenant isolation

- Only the covered active Project Manager human may create the request receipt.
- Only active `workstream.project.setup` may fence execution, record a known
  outcome, or persist; humans and all other services deny before mutation.
- Actor, identity link, project, guide, source snapshot, setup run/generation,
  catalogues, agent/instruction versions, operation/request/idempotency IDs,
  attempt, provider key, predecessor, and result/component hashes cannot be
  substituted or copied across a call.
- Request and final allowed events are durable only with their protected POL
  mutations. Preflight remains non-evidencing.

### Idempotency, replay, and recovery

- One setup generation has one attempt, one provider key, one request receipt,
  at most one request allowed event, and at most one final allowed event.
- Exact request replay returns the original receipt; changed reuse conflicts.
- Once dispatch is fenced, no path in this chunk returns to reserved or emits a
  second dispatch permit.
- Accepted-not-persisted recovery performs persistence only and never provider
  dispatch. Persisted and invalid-terminal states are terminal.
- Unknown provider outcome remains bounded and unresolved until a proven
  provider reconciliation capability exists.

### External I/O, crash, and cancellation

- POL-03B has no model/provider/network call, callback, Celery task, broker
  publish, or outbox write.
- No database transaction, row lock, prepared AUTH handle, session, workspace,
  or mutable ORM object crosses future provider/model I/O.
- The dispatch fence commits before a later caller may touch the provider.
- Cancellation before commit rolls back. Cancellation after a committed fence
  leaves the durable state uncertain and cannot trigger cleanup redispatch.
- Process restart recovers solely from PostgreSQL state; no process-local
  handle is needed.

### Rollback and forbidden effects

- Denial, validation failure, mismatch, stale state, known constraint conflict,
  unknown database error, or injected failure before commit leaves no partial
  request event/receipt/attempt or final event/compilation/transition.
- There is no outbox event because this hidden chunk dispatches nothing.
  Request authority is not authorization to publish a message.
- The chunk creates no approval, effective policy, policy projection, guide
  activation, setup success, Submission, Review, contribution, reputation,
  compensation, or settlement truth.

## Allowed files

```text
backend/app/modules/projects/guide_compilation/__init__.py
backend/app/modules/projects/guide_compilation/authorization.py  # delete merged deny-only seam
backend/app/modules/projects/guide_compilation/contracts.py
backend/app/modules/projects/guide_compilation/models.py
backend/app/modules/projects/guide_compilation/repository.py
backend/app/modules/projects/guide_compilation/service.py
backend/app/modules/projects/guide_compilation/validation.py
backend/app/db/models.py                              # metadata discovery only, if required
backend/alembic/versions/0008_guide_compilation_authorized_persistence.py
backend/tests/projects/guide_compilation/test_authorized_request_service.py
backend/tests/projects/guide_compilation/test_authorized_execution_service.py
backend/tests/projects/guide_compilation/test_request_operation_postgresql.py
backend/tests/projects/guide_compilation/test_authorized_recovery_postgresql.py
backend/tests/projects/guide_compilation/test_authorized_concurrency_postgresql.py
backend/tests/projects/guide_compilation/test_durable_dispatch_handoff.py
backend/tests/projects/guide_compilation/test_migration_authorized_persistence.py
backend/tests/projects/guide_compilation/test_public_authorization.py   # exact boundary assertions only
backend/tests/test_alembic.py                         # exact 0008 topology/fingerprint only
backend/tests/conftest.py                             # generic DB fixture plumbing only, if required
backend/scripts/run_test_lanes.py                     # exact new-test lane registration only
backend/tests/test_ci_test_lanes.py                   # exact lane inventory assertion only
backend/scripts/behavior_ownership.py                 # exact new callable ownership only, if required
backend/tests/test_behavior_ownership.py              # exact ownership assertion only, if required
backend/scripts/test_structure_boundary.py            # exact new-file scope only, if required
backend/tests/architecture/test_test_structure_boundary.py
.ci/behavior-ownership/partition.v1.json              # exact new callable ownership only, if required
.ci/behavior-ownership/auth/**                        # exact authority behavior atoms only, if required
.ci/behavior-ownership/lifecycle/**                   # exact lifecycle behavior atoms only, if required
.github/workflows/backend.yml                         # exact materially-changed coverage gate only
.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/**
docs/operations_backend_testing.md                    # lane command only, if registration changes it
```

No file is implicitly allowed by a directory wildcard other than the initiative
documents and the two already-governed behavior-ownership assertion directories.
If implementation needs another production, test, schema, CI, generated, or
documentation file, stop and amend/re-review this contract first.

## Prohibited changes

- Provider/model calls, prompts, agent-adapter changes, new provider
  idempotency claims, retries, polling, or fake reconciliation.
- `backend/app/workers/**`, Celery configuration, broker dispatch, outbox
  creation/publication, route, API router, or live composition changes.
- A public Projects port, application composition root, public endpoint, live
  setup cutover, or another execution path; these belong to POL-04A/04B.
- Policy projection or publication, sufficiency approval, pre/post approval,
  effective policy, guide activation, setup-ledger success, or checker work.
- AUTH public fact/Protocol changes, AUTH catalogue/policy/evaluator/runtime/
  service-matrix changes, broad compile authority, admin bypass, service
  inheritance, dynamic service authority, or another authorization adapter.
- A generic operation, workflow, idempotency, provider, outbox, or transaction
  framework; compatibility aliases; dual writes; mutable-current flags; or a
  second repository path.
- Imports from AUTH private modules or a new private cross-module dependency.
- Serialized or durable prepared AUTH handles, sessions, transactions,
  workspaces, authorization contexts, ORM objects, or provider credentials.
- Raw guide duplication, raw provider output outside the existing bounded
  canonical result, reasoning/traces, secret-bearing errors, paths, URLs, or
  unbounded strings in rows, logs, receipts, or exceptions.
- ART, TASK, Submission, Review, revision, contribution, compensation, payment,
  reputation, CP05, 02H hardening, or later POL behavior.
- Dependency additions, generated spreadsheet changes, threshold weakening,
  skip/xfail/pass-with-no-tests paths, mocks as sole lifecycle evidence, or
  changes to the current seven semantic-lane topology.

## Requirement -> risk -> test -> evidence matrix

| Requirement | Primary risk | Required discriminating test | Canonical observable evidence |
|---|---|---|---|
| Atomic PM request custody | Event commits without operation/attempt, or reverse | Real-PostgreSQL injected failure before each flush/commit boundary | Either all three exact rows exist and cross-reference, or none exist; audit count is exact |
| Concurrent request idempotency | Two prepared handles commit two events or attempts | Two independent sessions race identical operation/request/key; repeat with changed facts | One attempt, one provider key, one operation receipt, one allowed event; changed replay has zero new rows |
| Audit binding | Borrowed/cross-tenant allowed event satisfies custody | Direct SQL attempts every actor/link/project/resource/action/digest substitution | Postgres rejects each substitution at the owning constraint/trigger; original rows remain unchanged |
| SQL/Python digest parity | SQL trigger hashes a different preimage and accepts or rejects the wrong receipt | Golden values plus per-field mutation for both exact SQL functions, including null/non-null predecessor | SQL and public Python helper digests are byte-for-byte equal; every mutation changes both identically |
| Exact replay | Retried request mutates state or leaks raw result | Replay every recovery state and mutate one fact at a time | Exact bounded receipt/classification only; zero new audit/outbox/product rows; mutations conflict |
| Execute authority before dispatch | Human/wrong service or stale lineage obtains a dispatch fence | Production AUTH adapter with real DB actors/grants/services; all-pairs substitutions | Only fixed service commits reserved -> uncertain; denials leave reserved and create no event/outbox |
| Committed pre-I/O fence | Provider could start while tx/lock/handle is live | Instrument session state and forbidden provider sentinel; subprocess exits immediately after receipt | Uncertain row is visible to a second process before any provider call; no active tx/handle/callback crosses boundary |
| No unsafe provider replay | Crash/cancel causes duplicate one-shot call | Restart from uncertain and invoke every recovery entry point | `provider_outcome_unresolved`, original key, zero provider calls and zero new dispatch permits |
| Known result acceptance | Raw/changed/unsafe output enters custody | Unit/property validation plus real-Postgres accepted and invalid transitions | Accepted canonical bytes and hashes match recomputation, or bounded terminal code; no raw error material |
| Fresh final authority | Revoked/stale service persists accepted output | Revoke each actor/link/service/action/matrix element after acceptance, before persist | No final event, compilation, or attempt transition |
| Atomic final persistence | Event, compilation, or terminal state commits alone | Inject failures after prepare, consume, insert, and transition; include cancellation | Exactly one complete triple or no effect; accepted result remains recoverable after rollback |
| Concurrent append-only finalization | Two roots/children or two final events commit | Independent-session race for root and expected predecessor | One immutable compilation and event; loser rolls back; stale fork rejected |
| Crash recovery | Restart repeats provider work or loses accepted result | Separate-process real-Postgres cases for reserved, uncertain, accepted, persisted, invalid | Closed classification and exact row counts; accepted recovery performs persistence only |
| Outbox/side-effect absence | Hidden request accidentally dispatches or projects | Snapshot outbox and all named later-product tables before/after success, denial, replay, crash | Zero outbox/broker/provider/policy/approval/setup/checker/contribution deltas |
| Database immutability | ORM bypass changes or deletes governed evidence | Direct SQL update/delete/truncate and non-empty downgrade probes | Postgres rejection with unchanged rows; downgrade refuses governed custody |
| Module boundary | POL reaches AUTH private code or delivery reaches POL private code | Syntax-aware AUTH boundary and module reachability checks | Zero new private edges; no worker/route/composition consumer |
| Test trust | Happy-path tests pass without exercising failure | Test-of-test mutations for dropped lock, skipped AUTH consume, removed rollback, redispatch from uncertain, weakened trigger | Each named test fails for its seeded defect and passes only after restoration |

Every material assertion must name its exact SQL row/count, state transition,
decision-event ID, constraint/trigger, callback count, or absent downstream row.
Log text, mock invocation alone, test names, and narrative inspection are not
acceptance evidence.

## Required proof suite

### Unit, property, and contract proof

- Fact-to-attempt and attempt-to-fact reconstruction, digest determinism, UUID
  and bounded token/hash validation, exact mismatch classification, terminal
  failure allowlist, result/component hash recomputation, and closed recovery
  classification.
- Property tests mutate every bound field independently and prove a single
  mutation denies rather than normalizes or aliases.
- Public AUTH Protocol conformance uses the merged production adapter; no mock
  handle may stand in for final authority proof.

### Real PostgreSQL proof

- Migration upgrade, guarded downgrade, re-upgrade, sole-head topology, ORM
  parity, exact constraints/triggers, direct SQL attack, insert-only custody,
  transaction rollback, concurrent request, concurrent final persistence,
  stale predecessor, and accepted-not-persisted recovery.
- Use the repository's digest-pinned PostgreSQL harness and independent
  sessions. Do not add a second container abstraction or replace database
  behavior with SQLite/mocks.
- The request and final happy paths must use real actor, link, grant/service,
  AUTH adapter, audit, POL repository, and transaction composition.

### Durable handoff/provider-boundary proof

- A subprocess commits the dispatch fence and exits before any provider call;
  a fresh process/session must observe uncertain and refuse redispatch.
- A cancellation at each await before commit proves rollback; cancellation
  after the dispatch receipt proves the committed uncertain state survives.
- An instrumented provider sentinel must remain at zero calls throughout this
  chunk. A test that merely omits a provider dependency is insufficient: the
  coordinator surface and import graph must make provider invocation
  unreachable.
- Actual provider invocation, Celery redelivery, and reconcile-by-key proof are
  mandatory in POL-04A if that chunk introduces those effects; they are not
  faked here.

### Authorization and negative proof

- PM request vs fixed-service execute separation; wrong actor kind, identity
  link, grant, service identity, service matrix row, action, permission, tenant,
  resource, generation, request/key, attempt, predecessor, and hashes.
- Revocation between request and dispatch, and between acceptance and final
  persistence.
- Copied/replayed/wrong-session/wrong-transaction prepared handles through the
  existing AUTH suite plus composed rollback proof here.
- No raw data, secret, reasoning, provider exception, or unbounded failure
  enters audit, operation, attempt, compilation, receipt, or log output.

### Coverage and semantic-lane custody

- Register every new test module exactly once in the existing
  `project_lifecycle` semantic lane and update its exact inventory assertion.
- Preserve the seven-lane fan-in, missing/duplicate-node failures, no-skip
  policy, and all existing timeout/failure behavior.
- Repository-wide hosted coverage remains at least 78 percent.
- Each materially changed subsystem/file group is at least 90 percent:
  `app/modules/projects/guide_compilation/*`, the exact new service/repository/
  model files, and any changed AUTH or owner-composition surface. No gate may be
  weakened or satisfied by excluding changed files.

## Exact verification commands

Implementation must run these from repository root unless a command changes
directory explicitly:

```bash
git diff --check origin/main
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py

cd backend
uv run ruff check app/modules/projects/guide_compilation app/db/models.py \
  scripts/run_test_lanes.py tests/projects/guide_compilation \
  tests/test_alembic.py tests/test_ci_test_lanes.py
uv run pytest -q tests/projects/guide_compilation \
  tests/architecture/test_authorization_boundary.py
uv run pytest -q tests/projects/guide_compilation \
  -p pytest_cov.plugin --cov=app.modules.projects.guide_compilation \
  --cov-branch --cov-report=term-missing --cov-fail-under=90
uv run pytest -q tests/test_alembic.py tests/test_ci_test_lanes.py \
  tests/test_behavior_ownership.py \
  tests/architecture/test_test_structure_boundary.py
uv run python -m scripts.authorization_boundary validate \
  --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md
uv run python -m scripts.test_structure_boundary validate \
  --policy ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_POLICY.md \
  --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
uv run python -m scripts.behavior_ownership validate

lane_run_dir="$(mktemp -d)"
uv run python -m scripts.run_test_lanes \
  --metadata-dir "$lane_run_dir/metadata" \
  --summary-json "$lane_run_dir/summary.json" \
  --lane project_lifecycle
cd ..
```

Run the exact `project_lifecycle` lane through the repository lane runner after
registration. Full seven-lane semantic tests, combined coverage with
`coverage report --precision=2 --fail-under=78`, every accumulated subsystem
gate, Agent Gates, and review-evidence gates run on the exact pushed Phase 3
head in GitHub Actions. A local focused pass does not replace hosted proof.

## Stop and rollback conditions

Stop implementation and amend/re-review this contract if:

- the base, prerequisite behavior, sole migration head, frozen AUTH Protocol,
  provider port, or semantic-lane topology changes;
- safe implementation requires a provider call, worker, route, public Projects
  API, application composition root, outbox, policy projection, live setup
  behavior, generic operation abstraction, dependency, or file outside scope;
- the current provider must be retried/reconciled from uncertain without a
  proven same-key observation contract;
- exact request audit binding cannot be enforced by PostgreSQL without an AUTH
  schema or public-contract change, or the exact SQL/Python digest parity proof
  fails on any bound field;
- any transaction/lock/handle must cross external I/O, any handle/context must
  be serialized, or rollback cannot remove the matching allowed event;
- a test can pass without its canonical effect/forbidden-effect assertion, a
  required real-PostgreSQL boundary is mocked, or the 78/90 coverage floors
  require weakening.

Before merge, rollback is branch deletion. After migration is deployed,
downgrade is allowed only when the request-operation table is empty and no
request or execute compilation evidence/compilation custody would be orphaned.
Otherwise recovery is forward-only or requires a separately reviewed
retention/destructive-cleanup plan.

## Required preimplementation reviewers

All nine repository reviewer definitions must independently inspect the exact
final contract head using `python3 scripts/review_target.py` at start and end,
replay prior findings, supply atomized traceability and a discriminating
test-of-the-test/residual-escape probe, and finish `PASS`:

- architecture: owner/consumer/public-port matrix, transaction placement,
  hidden composition, and absence of a competing protocol;
- reuse/dedup: reuse of AUTH-12I/POL-03A and rejection of generic operation,
  provider, transaction, or outbox abstractions;
- security/authorization: actor/action/resource/state/failure/side-effect
  substitutions, audit custody, replay, rollback, and data safety;
- QA: split acceptance atoms, real PostgreSQL concurrency/crash/recovery, and
  forbidden-effect assertions;
- test delta: one primary invariant per test, test-of-test discrimination,
  structure limits, and false-green resistance;
- senior engineering: implementability, failure taxonomy, session lifecycle,
  cancellation, error classification, and simplicity;
- CI integrity: exact lane inventory, seven-lane fan-in, thresholds, commands,
  and no weakened gate;
- product/operations: bounded recovery, operator-visible uncertainty, and no
  false setup/approval/economic truth; and
- docs: current-main accuracy, terminology, links, commands, and clear deferred
  ownership.

Any Critical, High, unresolved Medium, narrative-only proof row, dirty/moving
target, or non-PASS verdict blocks Phase 3. Every valid finding must be resolved
in this contract and all reviewers rerun against the unchanged final contract
head.

## Human review focus

- Is the conservative pre-I/O uncertain fence acceptable until the provider
  port can prove reconciliation, including the possibility of a stranded call
  that never started?
- Does one concurrent request/finalization commit exactly one matching allowed
  event and product mutation while every loser rolls back?
- Is 03B still a hidden persistence boundary with zero provider, worker,
  outbox, policy, approval, live setup, or economic behavior?
- Are all external-I/O and public delivery concerns left explicitly to POL-04A
  rather than implied by this contract?
