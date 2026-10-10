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
| Protected MCP contract coherence | Selected-fragment tamper/transitive checks and actual backend OpenAPI comparison at `dd5c6802e507b8c5d80237e99c93e7b364383be4` | All 11 passed; only the three additive source actions, selected digest and capture revision change; the eight other operations remain identical | Later DDL/test changes leave this selected public schema unchanged |
| Architecture and CI metadata invariants | Module/AUTH, structure/ownership and lane regressions at reconciled `7d5f637e8aed61314f6f6024ef0fb611bd29ea06`; affected structure/ownership and Ruff replay at `f5b575f3d8db03d43e753aca4ab04a23fb08d626` | 404 architecture/metadata checks and protected-base validators passed; configured docstring audit passed without threshold changes | Full hosted suites and independent review remain required engineering checks |

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
and no additional ALLOW evidence. These affected application changes require a
new native proof; the earlier `c5f5a1` execution is not relabeled as that proof.

- Current-source reconciliation: main `4c5720034a2a1019f00df6c7f96601407ef1e43a` includes the merged lifecycle transitions, CLI guide inspection and pre-submit proposal approval, and PILOT-04 external checker contract/registry. Source actions coexist with the complete lifecycle and registry dispatch, resource and Operator-role classifications. Native UUID mappings retain each existing owner's string or UUID representation. The roadmap preserves merged Markdown, lifecycle and CLI delivery statements and keeps only this source prerequisite's additions. Existing MCP operations remain unchanged; the selected authorization-context contract includes the three additive source actions and captures the reconciled backend revision. After this reconciliation, the complete backend, contracts, MCP and CI-metadata trees remain byte-identical to the clean `c5f5a13637d3db6958154b6b7bf97389f9c0b233` public proof; incoming CLI source is unchanged from merged main.
- Next usable boundary: atomic DRAFT TASK import from verified source, then explicit batch screen/release and CLI conversion in separately authorized bounded changes.
- Remaining risks: source retention has no deletion scheduler; Issue #489 remains open.
- Schema handoff: merged main owns `0028_lifecycle_transitions` and
  `0029_external_checker_registry`. The sole coordinated migration author
  supplied linear revision `0030_task_import_source`, including the reviewed
  immutable-update lock and NULL-role repairs. The application implementer
  consumed that isolated handoff and matched its model constraint; no second
  migration author, alternative DDL or schema bypass was used. The clean final
  16-case public PostgreSQL/MinIO proof above includes the retained lock race and
  direct SQL role controls. Source custody is the complete outcome of this chunk;
  atomic DRAFT import and batch operations remain separate implementation work.
