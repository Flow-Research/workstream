# PILOT-02A — Retain declared task-import JSON under ART custody

- Initiative: `None`
- Durable disposition: `Complete`
- Intended merge outcome: A covered Project Manager declares, uploads and reads a project-bound canonical JSON task-import source with exact byte commitments and ART recovery custody.

## Intent

Issue [489](https://github.com/Flow-Research/workstream/issues/489) requires atomic
DRAFT task imports whose exact received JSON remains under ART custody. This
prerequisite makes that source usable without bypassing the existing storage
owner. It does not create a Task or claim that a batch was imported.

## Current behavior

Before this change, `tasks/authorized_commands.py` owned manager task commands,
current authority and task-specific audit. `artifacts/service.py` owned prepared
scratch, durable admission, provider operations, verification and recovery; its
closed producer set contained guide sources, checker outputs and submission
bundles. `ArtifactStore` does not expose deletion and retained records are
immutable. This change adds a typed declared task-import source and exact PM
authority to those owners, without creating Tasks or a second byte lifecycle.

## Bounded change

### Allowed

- `backend/app/modules/artifacts/`: project-bound task-import source declaration,
  admission, verified read, source status and existing recovery integration.
- `backend/app/modules/tasks/api/task_import.py` and
  `contracts/task-import.schema.json`: canonical JSON used by live source upload.
- `backend/app/modules/authorization/`: import-source-specific closed actions,
  typed exact resource commitment, covered PM authority and preparation.
- `backend/app/interfaces/artifact_operations.py`, composition-root artifact
  adapters and public router registration: typed source operations and wiring.
  Source composition uses the existing `adapters/artifacts/__init__.py` and
  `adapters/auth/__init__.py` roots; no private-import debt is added.
- Backend tests for source validation, exact bytes, authority, concurrency,
  idempotent rollback, PostgreSQL custody and MinIO/provider recovery.
- Existing identifier inventory, public route/action inventory, AUTH custody
  documentation and explicit predecessor fixtures affected by source admission.
- One migration authored solely by the coordinated backend migration owner;
  required schema fingerprint updates follow that migration.
- Scoped current ART/TASK/AUTH specs, README, roadmap and boundary manifests.
  `mcp_server/contracts/authorization_context_get.json` receives only the three
  source-action enum additions, its selected-fragment digest and captured backend
  source revision; existing MCP operations and unrelated schemas stay unchanged.
  `backend/scripts/behavior_ownership.py`, its exact source target partition,
  `backend/scripts/test_lane_catalogue.py` and the existing AUTH structure debt
  ledger receive only additive source coverage or debt-removal reconciliation.
  The cohesive existing ART AUTH contexts move into
  `authorization/domain/artifact_storage.py`; the runtime facade retains its
  existing typed contracts and union while shrinking its frozen structure debt.

### Not allowed

- Task creation, batch screen/release, contributor task creation, external
  adapters, CLI conversion, per-row transactions, guide prerequisite changes.
- A second storage lifecycle, direct product filesystem/provider access,
  uncontrolled object deletion, checker subsystem changes or weakened CI.
- Merge, deployment, issue closure or starting the next bounded chunk.

## Design and decisions

A durable ART declaration is the parent of every admitted upload attempt. Its
project, exact SHA-256, byte count and JSON media type are immutable. Declaration
replay uses the project/idempotency-key namespace and requires current PM
authority. Upload validates the published 1..500-row canonical JSON contract
and exact declared bytes before durable admission. Existing ART scratch,
admission, put, verification and scanner owners perform byte work.

Failed or abandoned declarations and admitted sources remain retained governed
ART records, available through current authorized status/read operations when
their bytes verify. They have never represented imported tasks. The existing
immutable retention contract supplies custody; this change does not promise
object deletion or introduce a retention scheduler. A later atomic TASK import
will bind a verified source receipt and batch receipt in its root transaction.

External task IDs are required, case-sensitive strings of at most 200 characters
without surrounding whitespace; duplicate IDs inside a document fail before
durable admission. Existing project/task conflicts are checked by the future
TASK import owner. JSON bytes are UTF-8, with no duplicate object members or
non-finite numeric values. The received JSON is the retained source, including
when a client converts a CSV; it is never described as the original CSV.

## Acceptance criteria

- [x] A covered PM declares/uploads a 200-row JSON source and downloads identical
  verified bytes, SHA-256 and byte count through public routes on MinIO.
- [x] Invalid rows, duplicate IDs, 501 rows, malformed JSON and mismatched
  declared bytes create no admitted attempt or stored source content.
- [x] Same-key exact declaration/upload replay returns original source facts;
  changed payload/key binding conflicts and revoked-authority replay is denied.
- [x] Concurrent declaration/upload cannot duplicate source custody; PostgreSQL
  rejects foreign-project/source-byte substitution and declaration mutation.
- [x] Provider uncertainty recovers through existing ART attempts/scanners with
  retained declared-source custody and no task/batch effects.

## Risk and review routing

- Risk class: `L0`
- Required reviewers: architecture, security, QA, test delta and documentation;
  implementation/evidence review coordinated by the lead.
- Human review focus: typed source role, fresh PM authority, immutable failed
  source retention and the explicit remaining atomic task-import boundary.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing owner reuse and current-main union | ART admission/put/verification, canonical command composition and TASK tracing; parser, AUTH catalogue, actual audit construction, native identifier and checker-registry regressions | 86 focused checks passed at `f5b575f3d8db03d43e753aca4ab04a23fb08d626`; 148 actions retain all lifecycle, registry and source actions | Pure checks do not establish provider custody |
| Ordered native schema | Sole migration author's exact `2653edc843fed4be0120f54408550f75e714b86d` graph, reset, UUID-schema and external-registry PostgreSQL checks | 7 passed in 132.42 seconds; one linear head `0030_task_import_source`; owned database and role cleanup confirmed | Schema proof is separate from public operation proof |
| Exact public byte custody and authority | Canonical isolated runner with `pytest -q tests/test_task_import_sources.py` at clean `c5f5a13637d3db6958154b6b7bf97389f9c0b233` | All 16 passed in 279.94 seconds on native PostgreSQL 16 and MinIO; runner exit 0; metadata binds that head, migration 0030 and database/role/MinIO cleanup | Public-route local proof; no hosted-provider or deployment claim |
| Lock-cycle regression | Real public replay and terminal absence worker, with an observed admission-scope lock wait and exact blocking PostgreSQL PID before release | Repaired suite completes worker `missing` and upload `verified`, retaining one attempt and no Tasks; preceding clean `7afd2264e7f6c004b9bba549bb44890bd6b49d00` fails the same success assertion with HTTP 500 | This proves the observed source/scope interleaving, not all possible concurrency |
| Direct SQL role and immutable custody | Valid native attempt/receipt copies roll back; NULL source-role copies, source mutation, deletion and foreign attempt substitution are rejected | All positive/negative controls pass in the 16-case proof; a test-only in-memory replay against clean preceding `7afd2264e7f6c004b9bba549bb44890bd6b49d00` fails because NULL attempt insertion is accepted; control cleanup confirmed | No ORM-only custody claim |
| Actual AUTH decision classification | Exact task-import-source decision projected into the closed audit target/resource contract; preceding decision class replayed in memory | 12 focused audit cases passed; the preceding class fails the new decision construction as intended | No unrestricted resource string or alternate AUTH path |
| Exact denial custody after owner repair | Canonical isolated runner with all public source cases at clean `a3ef23fe46ec6687ba749b714b46e7e99b768a0e` | All 18 passed in 453.14 seconds on native PostgreSQL 16 and MinIO; runner exit 0; migration 0030 and owned database/role/MinIO cleanup confirmed | Local proof; full hosted CI and final independent review remain required |
| Denial regression discrimination | Retained real-service test body replayed against clean production `94fe55c3a171deb619debb2310d323703b71c666`; source restaging disabled in memory at `a3ef23fe46ec6687ba749b714b46e7e99b768a0e` | Old boundary fails the wrong-instance assertion in 73.61 seconds; no-op restaging fails the four canonical denied-event assertion in 73.43 seconds; both native control namespaces cleaned up | Test-only overlays are controls, not full executions of either production tree |
| Protected MCP contract coherence | Selected-fragment tamper/transitive checks and actual backend OpenAPI comparison at `dd5c6802e507b8c5d80237e99c93e7b364383be4` | All 11 passed; only the three additive source actions, selected digest and capture revision change; the eight other operations remain identical | Later DDL/test changes leave this selected public schema unchanged |
| Architecture and CI metadata invariants | Module/AUTH, structure/ownership and lane regressions at reconciled `7d5f637e8aed61314f6f6024ef0fb611bd29ea06`; affected structure/ownership and Ruff replay at `f5b575f3d8db03d43e753aca4ab04a23fb08d626` | 404 architecture/metadata checks and protected-base validators passed; configured docstring audit passed without threshold changes | Full hosted suites and independent review remain required engineering checks |
| Current routing/source schema and public integration | Canonical isolated runner at clean `812c68df49a6857f97858c58646ed3621fcfa59f`: all 18 public source cases plus graph, reset, native UUID and external-registry checks | All 25 passed in 437.76 seconds on PostgreSQL 16 and MinIO; runner exit 0; metadata binds that head, linear `0031_task_import_source`, and owned database/role/MinIO cleanup | Exact local integration proof after main's routing migration; full hosted suites remain required |
| Current owner and contract coherence | Source parser, AUTH catalogue/audit/setup and CI lane metadata at `812c68df49a6857f97858c58646ed3621fcfa59f`; canonical module/AUTH architecture checks and protected-main guards | 121 pure/metadata checks passed in 9.56 seconds and 94 architecture checks in 212.12 seconds; module/AUTH, structure/ownership, Ruff, configured docstring audit and stale contract checks passed | Independent source review closes both denial findings; the migration author's DDL remains subject to the lead's independent SQL review |
| Current selected MCP coherence | Actual backend OpenAPI, selected-fragment tamper and transitive checks at reconciled `169d2748608984257c565bff3ae05be2167bea0f` | All 11 passed in 20.27 seconds; the subsequent authored migration handoff changes only migration ordering, graph and native fingerprint consumers | Selected public schemas are unchanged by the handoff; no new MCP operation is introduced |

## Review findings

The selected MCP authorization-context snapshot initially omitted the new source
actions. Its enum, selected-fragment digest and captured source revision are
reconciled without changing existing operations. New source ports and public
operations document their fresh-authority, retained-source and byte-verification
contracts; no CI configuration or percentage threshold changes.

The first native public drill exposed two owner-composition gaps: the identity
resolver's read transaction was still open before the command root, and the
closed decision/audit resource union omitted `task_import_source`. Composition
now uses the existing canonical command pattern to finish the resolver's
read-only transaction before constructing the sole command root. Exact source
classification is added to the decision, context-digest and audit target/resource
sets while retaining all merged entries.

Independent native review reproduced a source/scope deadlock between public
upload replay and terminal absence recovery. The migration keeps INSERT custody
validation and its composite foreign key, rejects DELETE and changed custody,
and returns an unchanged attempt UPDATE before re-locking its immutable source.
The retained public regression observes the real intermediate scope wait and
requires both owners to finish with exact retained effects. Native role guards
also use explicit NULL-safe predicates, with matching model semantics and
positive direct-write controls before the negative substitutions.

The new native proof fixtures use distinct valid source bytes: a prior corruption
case intentionally changes its content-addressed MinIO object, and database reset
does not delete that governed provider key between cases. The controls therefore
exercise a fresh acknowledged write rather than assuming that reused content
can be overwritten. Existing provider failure and recovery behavior is preserved.

## Reconciliation

Independent source review found that nested resolver and verifier denial scopes
could let the verifier intercept a resolver's denied decision. Source composition
now passes each existing authority's denial scope to its corresponding operation;
put/replay and verification restage only their own captured decision. Retained
public tests suspend each real fixed-service principal and require its exact
canonical denial event, original ART resource, and zero wrong-instance restaging.
The revoked-manager public case also requires all four canonical denied decisions
and no additional ALLOW evidence. The new 18-case native proof above covers these affected application changes;
the earlier `c5f5a1` execution is not relabeled as that proof. Denial assertions
match the committed canonical event to the actual captured decision ID and
resource-context digest, retaining AUTH's bounded audit projection rather than
requiring raw private resource selectors.

- Current-source reconciliation: main `20b0beb8023c53e7c101c325aaceb3d38fb2a215` includes the merged lifecycle transitions, CLI guide/post-policy inspection and pre-submit proposal approval, PILOT-04 external checker contract/registry, and complete hidden authorized routing outcomes. Source actions coexist with the incoming routing action activation and the complete lifecycle/registry resource and role classifications. Native UUID mappings retain each owner's string or UUID representation. The roadmap retains main's delivered routing statements and only this source prerequisite's additions; existing selected MCP operations remain unchanged. The earlier `94fe55c3a171deb619debb2310d323703b71c666` reconciliation preceded the denial-owner repair and was source-equivalent to the `c5f5a1` native proof. The subsequent exact `a3ef23fe46ec6687ba749b714b46e7e99b768a0e` denial proof remains historical evidence for its tested tree; it is not relabeled as proof of this newer integration.
- Next usable boundary: atomic DRAFT TASK import from verified source, then explicit batch screen/release and CLI conversion in separately authorized bounded changes.
- Remaining risks: source retention has no deletion scheduler; Issue #489 remains open.
- Schema handoff: main owns `0028_lifecycle_transitions`,
  `0029_external_checker_registry` and `0030_routing_outcomes`. The sole coordinated
  migration author supplied successor `0031_task_import_source` in
  `641b3bae2072aded46d61cfd1367cfcca42d7d0b`, integrated at `812c68df49a6857f97858c58646ed3621fcfa59f`.
  Its SQL body retains the reviewed immutable-update lock and NULL-role repairs;
  only the revision and predecessor identifiers change. The combined PostgreSQL
  16 fingerprint is `a209b774a54f2dad9dacf43f7112b82e2366159fa6e7a677c2f3108a6f0d023f`.
  The earlier isolated source revision and native proofs used ordinal 0030
  before routing merged; their exact historical receipts remain distinct from
  the new 25-case successor-schema and public-operation proof above. No
  application author writes alternative DDL or bypasses the canonical schema
  guard. Source custody remains this chunk's complete outcome;
  atomic DRAFT import and batch operations remain separate implementation work.

The first full hosted execution after routing reconciliation exposed six
integration gaps. The source HTTP adapter moves to the existing `app/api/routes`
composition layer; its sole public error contract now lives beside its port.
The ART operation boundary translates existing admission/service errors to the
same closed source codes after transaction cleanup and canonical denial
restaging. No adapter import or new private-import debt remains in ART rules.
The identifier inventory recognizes explicit table primary-key constraints in
addition to inline declarations; native source primary-key custody was already
correct. Public route/action assertions and both AUTH custody documents retain
their previous rows and add the exact four source routes and three actions.
Predecessor seed fixtures temporarily admit the current nullable attempt column,
then restore the original column list and full retained ART row facts before
the migration under test. Corruption and uncertain-write fixtures use distinct
valid received JSON so retained provider corruption cannot contaminate another
case. No migration, provider behavior, test threshold or hosted suite is weakened.
The exact preceding `f1df115bc351f268c1c03603db42631921f2f91d` native control
reproduces the ordered provider collision and predecessor seeding failure
(two failed, one passed in 222.32 seconds), with owned database/role/MinIO cleanup.
Both explicit primary-key variants also fail against the preceding parser.
These controls establish the repaired defects; the earlier positive receipts
above remain bound to their original tested trees.


The repaired source/API/fixture tree at clean
`7a7bc3825c6e36921bd572cf49cda4b9a521bd3e` passed all 18 native public
source cases in 468.79 seconds and the separately ordered corruption then
uncertain-acknowledgement control in 111.51 seconds. Both canonical PostgreSQL
16/MinIO runners exited 0 at `0031_task_import_source`, with owned database,
role and provider cleanup confirmed. All 27 affected pure checks, 173
ownership/lane regressions, selected MCP checks (11), full Ruff, configured
80.2% docstring audit, protected-main module/AUTH guards and stale-contract
scans passed at that source tree.

The additive AUTH custody fixture also exposed structural-ledger drift. Two
existing expressions are compacted without changing their values or assertions;
the file shrinks from the protected 10,959 lines to 10,958. All retained debt
symbol hashes and lengths, thresholds, exceptions and policy are unchanged.
The clean affected freeze `ab00589526e265422205b3515365bcb560e2cb18`
passed the exact structure guard and all 30 custody/structure regressions in
112.91 seconds. The native review-policy migration control that previously
failed source-column seeding passed in 94.15 seconds at that clean head, with
`0031_task_import_source` and database/role/MinIO cleanup confirmed. Its
application, DDL, historical seed fixtures and public source tests are byte
identical to the 18-case tested source tree. Independent affected source review
passed both freezes; the migration author's SQL remains separately reviewed.

The 28-node predecessor migration batch reached its declared 1,200-second cap
after ten completed cases, without an assertion failure, and cleaned its owned
resources. It is not a completed 28-case proof. The source-equivalent diagnostic
review-policy run and older local proofs retain their actual execution states
and heads. Fresh complete hosted lanes and their aggregate remain required;
no full-suite pass or readiness is claimed from these bounded local checks.
