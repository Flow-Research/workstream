# Replace self-activated task eligibility with project authority

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Task claim/start and work-context use canonical authority; worker eligibility and old public packet submission are retired, while admission-backed submission remains hidden.

## Intent

An external identity or self-created eligibility row must not authorize work.
The user explicitly requested this repair before the broader TASK replacement.
An exact-project active Submitter grant authorizes contributor operations;
the canonical Operator permission alone authorizes a reasoned start override.

## Baseline behavior being replaced

This section records the pre-change behavior at `471bbbb3`, not the intended
merged API contract.

`TaskService` reads `LegacyWorkflowEligibilityCompatibility` for claim, start,
submission and work-context actions. `/workers/me/profile` lets a token-role
worker activate global eligibility. Token roles also guard those methods.
The existing AUTH repository already owns canonical actor/link locking and
exact-project active-role lookup. AUTH's submission creation action already
has a separate exact hidden ART-backed resource contract; this repair must
not weaken it to admit an old JSON packet as an ART-backed Submission.

## Bounded change

### Allowed

- `backend/app/modules/tasks/`: affected service/router/context construction,
  public authorization facts/ports and preserved state/assignment guards.
- `backend/app/modules/authorization/` and delivery composition/dependencies:
  exact task authority using existing actor/link, project-grant and Operator
  permission owners, catalogue/resource declarations where necessary.
- `backend/app/modules/actors/`: remove eligibility activation, bridge,
  exclusive schemas and repository accessors. Preserve stored rows/schema.
- Affected backend tests, fixtures and scripts; current AUTH/TASK plans,
  specifications, capability ledger and boundary/debt inventories.
- Shared typed audit participant: exact TASK transition events and the existing
  authorization-decision reference, without a parallel audit writer.
- Same-owner composition roots under `backend/app/adapters/{auth,tasks,audit}`:
  wire the existing AUTH and audit implementations through TASK public ports.
  No new private-import debt entry or validator exception is permitted.
- Catalogue parity migration only if required; no retained-data deletion.
- Coverage concurrency configuration and its existing contract tests: repair
  SQLAlchemy greenlet line attribution discovered while verifying this change.
  No workflow, test-selection, exclusion, dependency or floor weakening.

### Not allowed

- Guide-upload/setup changes, checker policy design, hidden API exposure,
  task queue/invalidation worker implementation, contribution/review activation.
- Compatibility aliases, role claims as authority, default-allow adapters,
  duplicate grant rules, weakened tests or coverage, history/data deletion.
- Merge, or changes to the paused API-drill branch.

## Design and decisions

The user selected retirement of old public submission, not public activation
of the hidden admission-backed command. The bounded manifest is:

| Operation | Action | Permission and authority |
|---|---|---|
| Claim | `task.claim` | `task.claim`, exact-project Submitter |
| Assigned start | `task.start` | `task.claim`, exact-project Submitter |
| Reasoned start of another contributor's assignment | `operations.task.start_override` | Existing permission, system Operator |
| Contributor work context | `task.work_context.read` | `task.queue.read`, exact-project Submitter |
| Management work context | `project.task.work_context.read` | `project.task.manage`, covered Project Manager |

Use new bounded action owner `task-project-grant-authorization`, not the
superseded broad AUTH-13 owner. Submission's existing action/resource and
hidden exposure boundary remain unchanged; its command reuses the existing
complete locked-policy validator before persistence or ART consumption.
The submission and worker-profile POST
routes are removed, not hidden or aliased. Contributor hints advertise only
claim/start where granted and valid; no submit/precheck hint remains.

TASK public facts/port live in `tasks/api/authorization.py`; AUTH strict
resources/rules in `authorization/domain/task_authority.py`, the adapter in
`authorization/task_authorization.py`, and delivery wiring in the existing
`api/deps/authorization.py` with same-owner AUTH/TASK/audit composition roots.
Extend the existing kernel, prepared service,
catalogue, runtime resource union and audit registries; do not add an evaluator
outside AUTH. TASK command methods and response builders remain TASK-owned.
The database parity migration follows current `0016_guide_document_runtime`;
reconcile its revision number if guide work advances the migration head.

Reuse AUTH decisions and typed public seams; TASK keeps lifecycle/assignment
ownership and passes server-loaded resource facts. Mutation authority must
remain current under the same transaction through writes, with a consistent
task/assignment/actor/link/grant lock order, aligned with hidden Submission
creation (which also locks its predecessor before AUTH). No repository query in TASK may become a
second authorization evaluator. Foreground revocation denial does not depend
on future asynchronous invalidation. Action hints use the same permission
mapping plus state and active-assignment ownership; hints are not authority.

Remove affected token-role guards rather than adding project grants as another
requirement. Preserve canonical contributor checks, locked policy validation,
pre-submission rejection, exact assignment ownership, one-winner claims,
reasoned authorized overrides and audit attribution. Preserve retained
eligibility rows without a callable activation/read bridge.

The broader ARCH-03B/03C work remains planned: reconcile its eligibility-removal
language to this delivered boundary without claiming queue, contribution-lock
or asynchronous invalidation completion.

## Acceptance criteria

- Exact active project Submitter permits claim/start where lifecycle,
  assignment, lineage and intake permit; no worker token role is required.
- Missing, revoked, reviewer-only and foreign-project grants deny without
  task/assignment/submission mutation. Suspended/deactivated actors and revoked
  or foreign identity links deny, including stale request contexts.
- Start override requires canonical system Operator authority and a reason;
  token admin/project-manager roles cannot bypass assignment ownership.
- Claim races have one winner; revocation races serialize without stale allow;
  invalid intake cannot create a Submission or discard required audit evidence.
- Available actions reflect project permission, state and actual assignment.
- Old endpoint/schema/activation/bridge and exclusive consumers are absent;
  retained data and required behavior tests remain protected.

## Risk and review routing

- Risk class: L1
- Required reviewers: security, architecture/reuse, QA/test_delta,
  product_ops, documentation and CI integrity. The lane catalogue replaces
  the deleted eligibility-test entry with the new task-authority modules;
  reviewers must verify that retained proof remains collected.
- Historical assertion-map treatment: 26 assertions targeting the four removed
  activation tests retain their original revision, node, span and hash. Their
  dispositions explicitly retire self-activation and point to the real HTTP
  absence/no-registry-write proof. This is an intentional contract replacement,
  not a claim of behavioral equivalence or preserved activation concurrency.
  Unrelated identity assertions in the same historical map remain unchanged.
  Four activation-provenance assertions also retain their historical references
  but now explicitly identify the canonical admission privacy proof: the
  accepted maximum-length identity remains private, and ActorProfileProvisioned
  evidence does not copy external issuer, subject or token claims. This does
  not preserve the removed activation event's external-identity payload.
- Human review focus: no second permission system or premature hidden action
  activation; exact-project authority and assignment/lineage preservation.

## Evidence

Coverage inspection found cross-file line attribution in raw hosted lane data.
A bounded SQLAlchemy `greenlet_spawn`/`await_only` reproduction showed resumed
application lines attributed to the caller under default thread-only tracing.
The repository now declares thread and greenlet concurrency in its existing
coverage configuration, with an exact-line regression in
`backend/tests/test_coverage_contract.py`. Earlier percentages measured without
that setting cannot certify coverage; full hosted measurement must be repeated.
Test execution outcomes remain distinct from coverage measurement. No threshold
is reduced and no parallel coverage mechanism is introduced.

The focused proof lives under `backend/tests/authorization/task_authority/`,
with retained TASK/checker/read tests and current intake/archive owners listed
below. It includes real PostgreSQL/API grant matrices, independent-session
races, rollback and exact policy rejection. Ruff, architectural boundaries,
lane/behavior catalogues, structural debt, stale wording and Markdown links
are deterministic checks. Hosted Backend owns full tests and unchanged
coverage floors. Current command results and review readiness belong in the PR,
not a second durable work queue.

This cross-file retirement is one cohesive change: route and bridge removal,
canonical command wiring, and affected callers/tests must move together.
The large test delta is reviewed through the explicit replacement-owner map;
it does not authorize changing guide setup, review activation or CI thresholds.

### Baseline consumer and proof map at `471bbbb3`

- `tasks/service.py`: claim and submission revalidate a canonical human, but
  start does not perform the same write revalidation; all three still use
  token-role guards. Start reads task/assignment without a write lock. Replace
  these guards and preserve the role-independent lifecycle controls.
- `TaskService._worker_lifecycle_context` currently checks `assigned_to`, not
  the actual active assignment row. The replacement hint proof must exercise
  inconsistent, absent and inactive assignment rows as well as grant denial.
- `actors/service.py`, `actors/repository.py`, `actors/schemas.py` and
  `tasks/router.py` own the exclusive activation and bridge surface. The
  `actors/models.py` mapping and database history must remain because deleting
  retained eligibility rows is not authorized.
- `tests/test_tasks.py` includes old HTTP activation, disabled-eligibility and
  service tests. Replace eligibility prerequisite/revocation assertions with
  genuine project-grant controls rather than removing their behavior coverage.
  `tests/actors/test_legacy_eligibility_postgresql.py` and the bridge allowlist
  in `tests/test_auth.py` exclusively protect the removed implementation;
  retain applicable identity/rate-limit checks from
  `tests/actors/test_identity_bounds_and_rate_controls.py` on a surviving API.
- `scripts/api_contract_e2e.py` still invokes the removed worker activation
  before separately granting the project role. Preserve the real role-grant
  journey and remove the obsolete prerequisite.
- Add future focused tests under `tests/authorization/task_authority/` for
  real request composition, exact grants, actor/link currentness, override
  authority and concurrent revoke/write ordering. Existing TASK and hidden
  admission-backed creation tests remain regression inputs, not substitutes
  for the new integration proof.

### Submission contract decision

The current public `SubmissionCreate` accepts a package URI, caller hash and
manifest. `TaskService.create_submission` persists that packet directly.
Canonical `SubmissionCreationResourceContext` instead requires an admission
identifier and exact assignment/policy facts;
`TransactionalSubmissionCreationCommand` atomically consumes the ART admission.
These are not interchangeable resource facts. Do not fabricate an admission,
relax the canonical resource, or register an alternate packet-creation action.
The user approved removing the obsolete public submission route until the
canonical public cutover. This is an intentional public-surface removal;
the hidden admission-backed implementation and its regression tests remain.

## Plan review findings

Independent feasibility review confirmed the submission boundary decision:
neither a fabricated admission nor a parallel packet action is acceptable.
The submission choice and exact action manifest above resolve the planning
boundary. The implementation must satisfy these review findings:

- New `task.claim` and `task.start` actions reuse `task.claim` permission;
  normal start also requires the exact active own assignment. Existing
  `operations.task.start_override` uses system Operator authority and reason.
  Declare the activation owner and audit-registry database parity changes;
  registering catalogue strings alone is insufficient.
- Work-context access must itself support canonical authority without token
  worker roles. Specify its exact Submitter read action and preserve separate
  management access; do not advertise removed submission/precheck operations.
- Lock task and assignment before canonical actor, exact link and grant;
  retain locks through the caller-owned write transaction and consume exact
  server-loaded resource facts through an AUTH-owned adapter at the delivery
  root. TASK must not query grants or import AUTH implementation details.
- The review is code/contract feasibility inspection, not runtime or
  implementation proof.

### Dependency findings during fixture migration

- `ARCH-LOCK-001`: the initial AUTH-first task approach inverted the existing
  hidden command's TASK-first locks. Contributor work-context can overlap
  submission creation on the same in-progress task. Align new commands with
  TASK/assignment then AUTH, and prove independent-session serialization.
  Revocation does not acquire TASK locks, so its target-grant lock still
  serializes without adding a reverse TASK edge.
- `ARCH-LINEAGE-002`: hidden creation copies more policy columns than its
  narrow context port validates. Invoke TASK's existing complete locked-context
  loader before constructing a Submission; preserve malformed-body/crossed-
  sidecar negatives without duplicating policy evaluation in AUTH.

- Removing the old submission POST affects TASK, checker and review fixtures.
  Do not simulate an HTTP success or call the removed packet writer from a
  helper. TASK/ART tests need the real hidden admission-backed command;
  checker/review tests may explicitly seed their upstream stored prerequisites
  and exercise their own real owner operations.
- `tasks.schemas.SubmissionCreate` is not exclusive to the removed POST:
  `checkers.schemas`, `checkers.service` and `checkers.runner` still consume
  the packet as checker input. Preserve that shared schema until its real
  checker consumers are replaced; it is not a callable submission-creation
  path. The TASK router no longer accepts it for Submission creation.
- The ready-task resource guard is shared by claim and contributor context:
  all assignment fields must be absent. A partial assignment must deny even
  with an active project grant; exact prepared-resource tests cover each field.
- AUTH structural cleanup keeps one implementation: decision/outcome contracts
  move from the runtime aggregate to its existing `domain.audit` owner; the
  runtime aggregate exports those same definitions. Project-grant locking and
  dispatch reuse `artifact_project_authority`, with distinct TASK and ART
  resource guards. Exact audit target selection stays in `domain.audit_targets`.
  No second authorization evaluator, event writer or compatibility variant is
  introduced. Contributor lifecycle races move to the task-authority test
  package and remain explicitly assigned to CI.
  The behavior catalogue must also stop classifying `domain.audit` as
  structural-only: it now owns the existing decision validator and denial
  projection moved from `runtime`. Their record is an explicit candidate,
  not a fabricated reviewed mutation-ownership claim. No previously reviewed
  executable ownership is removed by this relocation.
- The hidden command does not perform the old packet route's automatic
  finalize/enqueue choreography. It must not be represented as a replacement
  public workflow. Preserve locked-policy rejection proof when migrating the
  removed route's negative tests; copying policy columns is not validation.
- `LegacyActorIdentity` still has shared consumers through registered-actor
  resolution in remaining task-management/checker/read routes. Deleting that
  shared model without their cutover would break APIs. This repair removes the
  eligibility bridge and affected contributor-command dependency, not retained
  identity data or unrelated management authorization.
- Task transition evidence reuses `LifecycleAuditParticipant` and references
  the canonical authorization decision. The decision's exact resource digest
  binds task/assignment/locked-context/reason; the participant does not copy
  token claims or fabricate an external actor identity. Its existing stored
  audit-domain discriminator is not a new compatibility implementation.
- The typed TASK audit port is wired through the audit owner's composition
  root. No business command imports another owner's audit implementation.
  Six obsolete private edges are removed from the module ledger; none are
  added. Operator reasons are retained as bounded task reasons, not token
  identity claims.
- Do not translate every integrity error into an assignment conflict. Only
  `uq_task_assignments_one_active_per_task` means a competing assignment;
  unrelated storage failures must remain unavailable, with rollback.

### Concrete focused verification

Run through `backend/scripts/run_isolated_tests.py` against an owned PostgreSQL
server, using a fresh isolated database/role and the canonical Alembic head:

```sh
python -m pytest -q tests/authorization/task_authority --override-ini addopts=''
python -m pytest -q tests/test_submission_composition.py --override-ini addopts=''
```

`test_prepared.py` is bounded kernel/handle proof; `test_postgresql.py` is real
signed project-role issuance plus prepared AUTH database proof;
`test_task_commands.py` executes actual task HTTP commands and observes rows.
These are not interchangeable evidence boundaries. Full affected regression
tests, races, deterministic checks and final reviews remain required.

### Replacement test ownership

- Identity-only row/read fixtures no longer create eligibility rows. One
  shared actor fixture replaces the two overlapping profile helpers; grant
  journeys use the real role-grant helper instead. Retained-table registration
  tests still protect the stored data shape.
- Both canonical work-context routes preserve the structured locked-context
  422 response in OpenAPI through one shared response definition. Corruption
  tests first prove authorized context access, then require exact policy
  rejection, so an earlier missing-grant denial cannot mask their assertion.
  Invalid-state contributor start is denied by AUTH's resource guard even with
  a real project grant, with unchanged task/assignment state. Hidden submission
  and precheck actions remain absent from contributor hints.
- Removed private contributor-wrapper mocks are replaced by the real API
  grant/lifecycle denials and transactional rollback tests under
  `tests/authorization/task_authority/`. Router failures are injected into the
  current command owner across all five routes, preserving structured errors,
  retryability and request correlation. Retained management-read/finalize
  service tests remain separate.
- Eligibility-disable journeys now issue and revoke exact project grants via
  the public authority APIs. Their denial assertions preserve task state,
  assignment identity and the absence of unintended Submissions. Token worker
  roles do not repair absent grants; role-free granted actors can claim.
- The old project-manager/token-based start-override test is replaced by
  `test_manager_context_and_system_operator_override_are_distinct`: explicit
  system Operator grant, required reason, manager denial, retained assignee and
  exact decision/audit references. The removed context-bridge mock is replaced
  by real contributor and manager work-context API checks; retained detail,
  requirements and provenance-read owner checks remain.
- The public API script stops at claim/start while canonical submission
  creation is hidden. It no longer uses JSON-packet POST success as evidence
  of ART admission, submission finalization or checker routing. Its existing
  revoke journey must explicitly issue a fresh grant before task work.
- `test_artifact_bindings_db.py` owns isolated ART transaction proof and already
  doubles TASK/AUTH collaborators. Its new explicit TASK policy-validator
  double preserves that boundary; real policy rejection remains owned by
  `test_submission_policy.py`, not inferred from the isolated ART schema.
- `tests/submission_fixtures.py` seeds retained stored-packet prerequisites for
  checker-owner tests, then invokes the existing TASK finalization and queue
  operations. It returns a Submission ID, never a fabricated HTTP response.
  Its ART lineage group remains entirely absent, as allowed for retained rows;
  this is not proof of canonical submission creation, admission, or new writes.
  TASK/ART creation tests must not use this fixture as their creation proof.
- Queue-recovery fixtures explicitly select the existing non-raising initial
  dispatch mode only when testing persisted broker-failure recovery. They still
  require the failed claim, exact failure code, audit attribution and idempotent
  repair. The normal fixture retains raising behavior; no production dispatch
  exception is swallowed or changed for test convenience.
- Mutated effective policy, compiled pre-submit bundle and crossed post-submit
  sidecar tests move to `test_submission_policy.py` and invoke real hidden
  TASK/AUTH composition. A nonexistent admission makes these negative-only
  tests: each must fail with its exact locked-policy field before admission
  lookup. They preserve no-submission/no-checker-write assertions and the
  crossed-sidecar test preserves unchanged task locks and audit history.
  They do not claim successful ART creation or public HTTP exposure.
- The removed packet POST's OpenAPI 422 schema test is retired with that route.
  `test_public_surface.py` instead requires its absence and the retained GET;
  locked-context error contracts on surviving task APIs remain tested.
  Actual HTTP probes use a started task with a current assigned Submitter and
  complete, forged-context and empty packets. They require 405, no POST in the
  Allow header, unchanged task/assignment/submission/checker/audit snapshots,
  and a usable empty retained GET response.
- Shared packet schema rejection moves to `tests/checkers/test_packet_schema.py`,
  through its real `PreSubmitCheckRequest` consumer. Each forbidden top-level
  field, nested injection and unsafe URI is checked separately with its exact
  validation location and error type; a complete packet remains accepted.
  These are schema proofs, not submission creation or authority evidence.
- Stored-version read/finalization regressions retain both packets and exercise
  real GET, finalization and list operations, including foreign-contributor
  concealment, unchanged prior hashes/finalization and stamped guide locks
  after later guide activation. Their names explicitly identify retained-data
  proof. Canonical creation/version allocation is separately owned by hidden
  submission-composition and ART binding tests, not inferred from fixture rows.
- Lifecycle race ownership is explicit. Claim races execute and commit the
  actual TASK command. Submission-authority races lock real TASK/assignment
  context, invoke the existing AUTH preparation/consumption port, and commit
  its exact allow evidence before the opposing lifecycle transition acquires
  the actor/link locks. In the opposite ordering, current lifecycle state
  denies and the work snapshot is unchanged. Suspension, deactivation and
  identity-link revocation are covered in both orderings.
  The submission-authority branch does not create a Submission, manufacture a
  ready admission, execute intake, or dispatch a checker. Those old automatic
  packet-writer assertions are explicitly retired, not called equivalent to
  AUTH evidence. Successful TASK/ART composition and its rollback remain
  separate tests with their stated collaborator boundaries. A full real
  TASK/AUTH/ART successful-creation lifecycle race is not claimed here.
- After tracing every remaining consumer, remove the now-unused
  `ActorService.require_active_human_write_actor` wrapper, its two exclusive
  exceptions and its exclusive test-double selector. Canonical actor resolution
  still rejects subject-kind drift; AUTH owns current actor/link/grant checks.
  The retained ACTORS exact-row tests and new AUTH repository-selector tests
  separately prove their real owners. Historical wrapper assertions identify
  this intentional owner/contract replacement rather than claiming the old
  issuer/subject selector or private exception API remains supported.
- Retire the removed packet POST's manager/other-worker status-code and
  competing-POST tests. Its real absence/no-write probes replace public-route
  expectations. Current hidden submission proof separately requires manager
  and Operator grants not to substitute for Submitter authority, and rejects
  a foreign contributor before TASK lookup. TASK's real PostgreSQL context
  matrix/lock race and unique-version constraint tests remain; ART's isolated
  PostgreSQL consumption/transaction tests own one-winner admission effects.
  These boundaries are not represented as an exposed end-to-end submission API.
- Retire old packet-POST intake assertions with that endpoint, not the required
  intake behaviors. `test_effective_intake_rules.py` executes current compiled
  project rules over actual prepared ZIP bytes for complete content, missing
  files, exact project evidence keys, project attestation terms and forbidden
  files. The archive suite rejects duplicate physical members/collisions;
  mandatory-checker and policy-lineage regressions remain in the default and
  effective executor suites. The migrated policy-ID corruption test calls the
  real hidden command and still requires a precise locked-context rejection.
  The existing real PostgreSQL evidence-workflow test owns immutable blocked
  evidence, bounded failure projection, absence of pass capability, and no
  additional Submission/checker/review rows. Its fixture and collaborator
  boundaries remain explicit; it is not a public submission drill.

## Reconciliation

- AUTH evidence-storage failures on both command and denial-restaging paths
  return the structured retryable TASK 503 response. Service actors reach the
  existing fixed-service matrix and canonical denial staging, rather than being
  rejected by an unaudited adapter type check. Actor-ID substitution remains
  rejected; no service TASK action is enabled. The full fixed-service/operation
  negative matrix checks exact denial evidence and rollback restaging.
- Reconcile retained test expectations with the activated TASK action set and
  the discovered current migration head. Keep exact action-set comparison and
  failed-downgrade rollback assertions. Replace a stale prose census assertion
  with the documented non-activation invariant; independent ART custody and
  permission mappings remain fully checked.

- Reset-schema fingerprint uses the same PostgreSQL 16 engine as Backend CI.
  Fresh 16/17 schema captures each contained 4,806 rows; only three namespace
  function identities differed (`pg_catalog.json` versus `json`). All remaining
  captured objects matched. Keep a single CI-engine fingerprint, not a relaxed
  multi-hash guard or a normalization that could conceal object changes.

- Migration preflight recognizes both the preceding guide-document revision and
  this change's head. Repeated `upgrade head` must preserve an already-current
  database. Register the five new Python owners in the existing behavior
  partition with exact-path additive approval and neighbor-rejection proof;
  preserve existing assignments, protected-base custody and fail-closed checks.
  Partition completeness must be checked after new source files are tracked,
  because its inventory deliberately uses Git-tracked targets.

- Review repairs: preserve the complete Alembic chain in the graph assertion,
  including `0016_guide_document_runtime`; remove outdated rollout/eligibility
  claims from the AUTH runbook; distinguish target contribution-policy locks,
  submission handoff and canonical recovery from retained runtime routes in the
  operating manual. No pending feature is activated by these documentation fixes.
- Review identified pre-existing database-level Submission ownership debt:
  assignment and predecessor references have individual rather than composite
  ownership constraints. This change does not alter those constraints or expose
  a new writer. Existing TASK/ART command validation enforces exact ownership;
  database-enforced lineage against privileged direct SQL remains a separate
  hardening concern, not a claimed guarantee of this change.

Retained-packet integration tests exercise actual checker routing, retry,
revision-version visibility, audit redaction and locked lineage without calling
the removed public writer. One audit-read test explicitly seeds historical
`submission_created` evidence; it does not claim that hidden creation emits
that event. The revision test no longer claims the removed writer's
`needs_revision -> submitted` audit transition; its real evaluation transitions,
version links, immutable prior packet, privacy and foreign-contributor denials
remain asserted. Trial intake failures are covered by the current actual-ZIP
intake and durable blocked-evidence owners identified above, not fabricated
HTTP creation responses.

- Based on main after PR #393. The guide-upload work owns PROJECTS guide
  schemas/routes and ART guide ingestion; this repair does not edit those.
  Shared AUTH/composition/tests/docs must be reconciled against its actual
  branch diff before push.
- The guide work also removed `/auth/me` in its separate branch. Overlapping
  files include `tests/test_tasks.py`, `tests/test_api_controls.py`, `tests/test_auth.py`,
  `scripts/api_contract_e2e.py` and current authorization/roadmap docs. Preserve
  that actor-self correction when reconciling; do not restore its old callers.
- Both branches currently add a migration after `0016_guide_document_runtime`:
  guide-upload owns `0017_guide_document_creation`, this change owns
  `0017_task_project_authority`. Do not merge both as independent Alembic heads.
  Whichever change merges second must rebase its migration onto the then-current
  head and rerun clean-schema/migration proof. Neither branch is implicit
  implementation authority for the other; reconcile only against merged main.
- Paused API drill remains on its original branch; update affected drill
  callers only where they invoke the removed eligibility workflow.
- Remaining boundaries: canonical public submission, the remaining management
  and read-route cutovers, complete ContributionPolicy lineage and durable
  assignment invalidation remain separate work. This change does not certify
  those capabilities or the complete public API drill. Hosted full regression
  and coverage evidence, plus focused internal review, are required before a
  merge-readiness claim.
