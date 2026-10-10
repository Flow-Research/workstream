# PILOT-02A — Retain declared task-import JSON under ART custody

- Initiative: `None`
- Durable disposition: `Planned`
- Intended merge outcome: A covered Project Manager declares, uploads and reads a project-bound canonical JSON task-import source with exact byte commitments and ART recovery custody.

## Intent

Issue [489](https://github.com/Flow-Research/workstream/issues/489) requires atomic
DRAFT task imports whose exact received JSON remains under ART custody. This
prerequisite makes that source usable without bypassing the existing storage
owner. It does not create a Task or claim that a batch was imported.

## Current behavior

`tasks/authorized_commands.py` owns manager task commands, current authority and
task-specific audit. `artifacts/service.py` owns prepared scratch, durable
admission, provider operations, verification and recovery; its closed producer
set contains guide sources, checker outputs and submission bundles only.
`ArtifactStore` does not expose deletion and retained records are immutable.
Neither a typed task-import source nor its PM read authority exists.

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

- [ ] A covered PM declares/uploads a 200-row JSON source and downloads identical
  verified bytes, SHA-256 and byte count through public routes on MinIO.
- [ ] Invalid rows, duplicate IDs, 501 rows, malformed JSON and mismatched
  declared bytes create no admitted attempt or stored source content.
- [ ] Same-key exact declaration/upload replay returns original source facts;
  changed payload/key binding conflicts and revoked-authority replay is denied.
- [ ] Concurrent declaration/upload cannot duplicate source custody; PostgreSQL
  rejects foreign-project/source-byte substitution and declaration mutation.
- [ ] Provider uncertainty recovers through existing ART attempts/scanners with
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
| Existing owner reuse | ART admission/put/verification and TASK command tracing | Closed producer gap identified | New typed source extension requires verification |
| Canonical JSON and closed action mapping | Focused TASK parser and AUTH catalogue tests | 36 passed; 200 rows, ambiguity, indexed errors, strict field bounds and published schema parity | Pure rules only |
| Merged lifecycle and source action union | Focused TASK parser, AUTH catalogue and setup-finalization catalogue replay against main `dfea06a33` | 63 passed; exact inventory retains the merged lifecycle action and the three source actions, with 110 active and 37 planned actions | Source storage still requires its ordered migration and live proof |
| Protected MCP contract coherence | Selected-fragment tamper checks and real backend OpenAPI comparison | Only the three additive source actions change the authorization-context enum; all nine selected operations and unrelated schemas remain identical | Regenerate the shared enum union after PILOT-04 merges |
| Boundary and documentation coherence | Protected-base module/AUTH validation, structure and behavior-ownership validation, Ruff, changed Markdown links and stale AUTH/ART contract checks | Passed without new private-import debt; exact source metadata reconciled | Reconcile union after PILOT-04 merges |
| Existing architecture and CI metadata invariants | Module/AUTH regressions and structure/ownership/lane regressions | 130 focused tests passed; metadata suite 227 passed with one stale exact lane expectation repaired and its focused replay passed | Full integration lanes await schema handoff |
| Current-main architecture and CI metadata reconciliation | Protected-base module/AUTH, structure and behavior validation; architecture/ownership/lane regressions against main `dfea06a33` | Validators passed; 323 architecture/metadata checks passed, alongside the 63 parser/catalogue replay checks; selected OpenAPI/tamper/transitive guard passed all 11 cases | These checks do not establish PostgreSQL/MinIO source custody |
| Merged PILOT-04 and current-main union | Parser, AUTH catalogue, native identifier parity and checker-registry regression tests against main `3110353363547e603e7527a782467f95c00cb1f7`; selected MCP fragment tamper/transitive and actual OpenAPI comparison | 74 backend checks and 11 MCP checks passed; 148 actions retain all lifecycle, registry and source actions; the eight other MCP operations are unchanged | The 15 public source cases remain collected only until migration 0030 is handed off |
| Exact byte custody and rollback | 15 collected public API PostgreSQL/MinIO negative/concurrency/recovery cases | Not executed: ordered source migration pending | No live custody or deployment claim |

## Review findings

The selected MCP authorization-context snapshot initially omitted the new source
actions. Its enum, selected-fragment digest and captured source revision are
reconciled without changing existing operations. New source ports and public
operations document their fresh-authority, retained-source and byte-verification
contracts; no CI configuration or percentage threshold changes.

## Reconciliation

- Current-source reconciliation: main `3110353363547e603e7527a782467f95c00cb1f7` includes the merged lifecycle transitions, CLI guide inspection and PILOT-04 external checker contract/registry. Source actions coexist with the complete lifecycle and registry dispatch, resource and Operator-role classifications. Native UUID mappings retain each existing owner's string or UUID representation. The roadmap preserves merged Markdown and lifecycle delivery statements and keeps only this source prerequisite's additions. Existing MCP operations remain unchanged; the selected authorization-context contract includes the three additive source actions and captures the reconciled backend revision.
- Next usable boundary: atomic DRAFT TASK import from verified source, then explicit batch screen/release and CLI conversion in separately authorized bounded changes.
- Remaining risks: source retention has no deletion scheduler; full issue 489 remains open.
- Schema handoff: merged main owns `0028_lifecycle_transitions` and
  `0029_external_checker_registry`. The sole coordinated migration author
  supplies linear revision `0030` after this branch's current-main reconciliation.
  This implementation authors no migration and uses
  no alternative DDL or schema bypass. All 15 public PostgreSQL/MinIO source
  cases remain unexecuted until that schema handoff.
