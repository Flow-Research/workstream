# WS-AUTH-003-TASKCHECKER — Remove alternate TASK/checker authorization

- Initiative: WS-AUTH-003
- Durable disposition: Planned
- Intended merge outcome: Submission and checker history use canonical AUTH;
  obsolete token-role authority and the alternate checker gate are removed.

## Intent

Workstream is unreleased v0.1. Earlier task cutovers left six submission/checker
HTTP operations behind `get_registered_actor`, token-role helpers and a
compatibility identity writer. The user explicitly requires removing these
paths before any further product integration, with no aliases or fallback.

## Current behavior

At main `6a9b38a6`, TASK has three remaining old handlers (submission list,
submission detail, gate repair) and CHECKERS has three (manual execution,
run list, run detail). The routers are registered. `get_registered_actor`
builds `ActorContext` from verified-token roles and writes a compatibility
identity table. The checker worker fabricates a privileged system actor.

Canonical admission-backed `TaskSubmissionCreationService` does not call
`CheckerService`, the gate queue or worker. The old enqueue path is reached only
from the old repair handler; its earlier private finalization helper has no
application caller. Keeping that alternate engine under a new authorization
wrapper would preserve the superseded implementation.

## Bounded change

### Allowed

- TASK retained-submission history, its routes/public contracts/repositories and
  application adapters; CHECKERS retained-run/result history, public contracts,
  routes/repository and obsolete service/queue/worker removal.
- AUTH exact history actions, resource facts, staged read decisions and existing
  project authority dispatch; one forward additive audit-constraint migration.
- Authentication result/verifier/dependency removal of token-role compatibility;
  ACTORS removal of the unused compatibility writer and its dead helpers.
- Dead requester/system-actor helpers, obsolete worker registration/configuration
  and their verified consumers. Shared schema/data owners are traced first.
- Affected tests, fixtures, canonical documentation, README, roadmap, initiative
  navigation, and shrinking module/structure/behavior ownership registrations.
- The structural-debt generator/ledger label must accurately describe remaining
  structural debt; relabeling is not proof of product cleanup.

### Not allowed

- Token-role-to-grant translation, compatibility constructors/aliases, fallback
  authority, duplicate runtime paths or fabricated service actors.
- Deleting retained Submission, checker, actor or audit data; rewriting immutable
  identifiers, results, lineage, or audit facts.
- Activating canonical post-submit execution, automatic acceptance, compensation,
  provider work or the next guide-activation product chunk.
- Weakening assertions protecting required behavior, CI selection or timeouts.

## Design and decisions

Preserve immutable history reads through canonical AUTH. Contributor reads bind
`Submission.contributor_id` to the current human actor and require the live exact
project Submitter grant; current assignment or a ready task never grants access to
another contributor's historical submission. Management inspection, where exposed,
uses separate project-scoped manager operations and fixed projections, never a
role-sensitive fallback in the contributor endpoint. Resolve project-scoped keys
before foreign-row locks. AUTH owns decisions; the caller transaction validates
the response and atomically persists evidence. Revocation, wrong project, unknown
resource and transaction failure must fail closed without leaking history.

The closed read action set is `task.submission.list`, `submission.read`,
`submission.checker_run.list`, and `checker_run.read` for contributors, mapped
to existing `submission.read_own`; management uses `project.`-prefixed variants
mapped to existing `project.task.manage`, restricted to exact project-manager
authority. Existing four GET paths become contributor-only fixed projections;
manager variants add `/projects/{project_id}` to the same resource paths. No
operator/auditor/reviewer authority is inferred or activated. Lists are bounded
and preserve version ordering/continuation without exposing other contributors'
rows. Contributor list resolution requires an existing Submission owned by the actor
before authorizing task/project/actor; no owned history returns concealed 404; details bind the exact persisted submission contributor.
Checker ownership resolves through its immutable Submission, never the current
assignee. CHECKERS owns its retained result projection through a typed public
read port; AUTH sees only exact server-loaded resource facts, not checker internals.

Remove the obsolete manual checker execution and gate-repair HTTP operations,
their unreferenced worker/queue/alternate routing implementation, and obsolete
role-authorized tests. Preserve history inspection and required storage/lineage
proofs. Canonical retry/repair and durable post-submit execution remain unavailable
until their existing exact-authority/result/routing contracts are implemented;
old mutation endpoints must not impersonate that delivery.

Once the consumers are replaced, delete the token-role verification projection,
`get_registered_actor`, compatibility identity write service/repository helpers,
old role authorization helpers and obsolete configuration. Retained data models
or evidence readers are not runtime fallback paths; identify necessary retained
references explicitly and never delete data to achieve a text-search result.

## Acceptance criteria

- [ ] No affected production path authorizes from token roles, task creator
  identity, compatibility actor context or fabricated system actor.
- [ ] Retained submission/checker reads preserve original ownership and privacy
  through reassignment, grant revocation, foreign project and missing resources.
- [ ] Required history projections have exact AUTH evidence and caller-owned
  rollback; unavailable AUTH/storage never produces an allowed response.
- [ ] Old execution/repair routes and worker registration are absent, not hidden
  or redirected; canonical hidden admission-backed creation remains intact.
- [ ] Shared consumers are traced; obsolete tests are removed and every required
  invariant has a surviving or replacement proof.
- [ ] Retained data and immutable evidence survive the migration unchanged.
- [ ] Source guards prevent reintroducing the removed authority paths.

## Risk and review routing

- Risk class: L1 authorization and workflow removal.
- Required reviewers: security/architecture, QA/test delta/product operations,
  CI integrity for test removals and owner registries, documentation.
- Human review focus: historical ownership, separate audience authority, removal
  of the alternate checker lifecycle, preserved data and explicit unavailable
  canonical execution/recovery rather than an accidental activation.

## Evidence

Required proof includes real PostgreSQL authorization/retention/rollback and
revocation cases, contributor/manager HTTP isolation, route/worker absence,
mutation probes for ownership and authority guards, preserved hidden creation,
old-to-surviving invariant mapping, import/structure/ownership checks, links,
stale wording and complete exact-head hosted CI/API contract verification.

## Reconciliation

- Current-source reconciliation: PR #445 is merged; start from main `6a9b38a6`
  including its nine-lane CI repair and corrected public policy navigation.
- Next usable boundary: resume manager activation/public guide activation only
  after this corrective cleanup is merged.
- Remaining risks: exact plan review and shared-consumer mapping precede code;
  retained-history inspection must not be mistaken for live canonical execution.

## Plan-review refinements

The eight GET operations are closed as follows. Contributor actions require
`submission.read_own`; management actions require `project.task.manage` and
Project Manager authority, never platform-admin status or token roles.

| Path | Action | Resource |
|---|---|---|
| `/tasks/{task_id}/submissions` | `task.submission.list` | task_submission_history / task |
| `/submissions/{submission_id}` | `submission.read` | submission_history / submission |
| `/submissions/{submission_id}/checker-runs` | `submission.checker_run.list` | submission_history / submission |
| `/checker-runs/{checker_run_id}` | `checker_run.read` | checker_history / run |
| `/projects/{project_id}/tasks/{task_id}/submissions` | `project.task.submission.list` | task_submission_history / task |
| `/projects/{project_id}/submissions/{submission_id}` | `project.submission.read` | submission_history / submission |
| `/projects/{project_id}/submissions/{submission_id}/checker-runs` | `project.submission.checker_run.list` | submission_history / submission |
| `/projects/{project_id}/checker-runs/{checker_run_id}` | `project.checker_run.read` | checker_history / run |

TASK owns immutable submission target/ownership facts and its public read port.
CHECKERS owns retained run/result queries and projections. Application
composition resolves its minimal references through TASK's public ownership port. AUTH adapters implement the owners' typed authority
ports; application composition wires them. No new CHECKERS import of TASK private
models/repositories, no TASK import of CHECKERS private services, and no extension
of generic task-operation facts to smuggle checker reads through another action.

Use separate frozen closed contributor/management DTOs. Contributor submission
fields: id, task_id, version, status, summary, submitted_at, locked_at,
supersedes_submission_id, and evidence descriptors (id/type/label/size_bytes).
Management adds contributor_id, task_assignment_id and exact locked guide/policy
identifiers, versions and policy hashes including ContributionPolicy version ID.
Neither projection includes locked_payment_policy_version or economic fields,
attestation, package URI/hash/manifest, evidence
URI/hash/metadata, external subject/issuer/claims or provider coordinates.

Contributor checker-run fields: id, task_id, submission_id, submission_version,
status, attempt_number, supersedes_checker_run_id, is_current_for_submission,
created_at/completed_at and visible results. Each visible result exposes only
id, checker_name, status, severity, worker_message and worker_suggested_fix.
Non-worker-visible results and all results for an internal-only routing outcome
remain hidden; no aggregate counts may reveal hidden results. Management adds
routing_recommendation, outcome_source, trigger_source and locked policy
identifiers/versions/hashes, and receives all result summaries with internal
message and blocks_review. Neither audience receives raw metadata, external
identity/claims, requester credentials, artifact provider locations or audit IDs.
Do not reuse nullable role-sensitive superset response schemas.

History never locks an assignment or uses the current assignee as authorization.
Detail/checker resolution first uses an owner-qualified nonlocking selector (and
explicit project predicate for management) to resolve immutable target facts.
Foreign owner/project rows must not cause a wait on a task owned elsewhere.
Then use the exact scoped TASK lock and existing task-first AUTH lock order,
with fresh canonical human actor/link and exact matched grant, followed by the
scoped project lock. Recheck the target/query binding before requiring authority,
and validate the detached closed response before committing AUTH evidence.
Valid missing/foreign/denied reads share concealed 404; unavailable AUTH/storage
rolls back and returns retryable 503. No live authority is inferred from a prior
receipt or retained submission.

Lists default to 25, maximum 100. Submissions order by `(version,id)` ascending;
checker runs by `(created_at,id)` ascending. Closed bounded cursors bind the
project, parent target, actor, audience/action and last position. Bind the exact
request limit and presented cursor into the AUTH decision query digest. Every
page rechecks current authority. Lists return fixed items plus next_cursor;
unknown cursor fields, duplicate JSON keys or wrong-scope cursors reject before
product SQL. No unbounded list or unsigned caller-supplied authority is added.

Retain the pure checker catalogue/compiler/registered implementations, persisted
models/repositories and retained-history projection. Delete the obsolete
orchestration service, manual request schema, gate queue/provenance module,
Celery worker registration and worker. Remove compatibility `ActorContext`, its
old audit/role helpers if no consumer survives, `core.permissions`, TASK's role
helper, verifier role projection, development role configuration and runtime
ACTORS legacy lookup/upsert methods. Retained historical tables/models and
classification tooling remain data-custody references, not application fallback
or authorization sources. No retained-data migration is authorized.

Counterexamples and controls: original contributor vs subsequent claimant;
READY/unassigned task with previous submissions; same contributor reclaims;
revoked grant; exact/project-covering PM grant only on the management surface;
forged token role claims without database grants; foreign locked rows returning
404 before release; real audit INSERT and response-validation failures rolling
back; byte-identical retained rows; canonical hidden creation producing no old
queued work; deleted POSTs, worker names and authority imports cannot return.

These refinements resolve SEC-PLAN-01/02 and ARCH-PLAN-01/02 through explicit
contracts; implementation and final proof remain required.


## Concrete implementation and proof inventory

The following paths are the allowed production surface (new owner history modules
are explicitly named):

- `backend/app/modules/tasks/{router,service,repository,schemas,authorization}.py`,
  `backend/app/modules/tasks/api/{__init__,submission_history}.py`,
  `backend/app/modules/tasks/submission_history.py`;
- `backend/app/modules/checkers/{router,service,repository,schemas,gate_queue,pre_review_gate}.py`,
  `backend/app/modules/checkers/api/{__init__,history}.py`,
  `backend/app/modules/checkers/history.py`;
- `backend/app/modules/authorization/{catalogue,prepared,runtime,kernel,artifact_project_authority,history_authorization}.py`,
  `backend/app/modules/authorization/domain/{action_groups,audit,audit_targets,submission_history}.py`,
  `backend/app/modules/authorization/api/{__init__,resources}.py`;
- `backend/app/adapters/{auth,tasks,checkers}/__init__.py`,
  `backend/app/api/deps/{auth,authorization,history}.py`,
  `backend/app/api/router.py`, `backend/app/schemas/auth.py`,
  `backend/app/adapters/auth/{flow,dev}.py`, `backend/app/core/{config,permissions}.py`,
  `backend/app/modules/actors/{models,service,repository}.py`,
  `backend/app/interfaces/auth.py`,
  `backend/app/workers/{checkers,celery_app}.py`;
- additive `backend/alembic/versions/0006_history_read_authority.py` after
  `0005_task_evidence_authority`; no baseline migration or retained-data edits.

Affected tests are `backend/tests/{test_tasks,test_checkers,test_auth,test_api_controls,test_db_session,test_ci_lane_catalogue,submission_fixtures}.py`,
`backend/tests/authentication/`, `backend/tests/actors/`,
`backend/tests/authorization/task_authority/`, and new
`backend/tests/authorization/submission_history/` (fixtures, contracts, reads,
privacy, authority, transactions, migration and absence modules).
Exact dependent import/fixture repairs in existing tests are permitted; assertion
semantics must be retained unless the table below explicitly retires the behavior.
Scripts are `backend/scripts/{api_contract_e2e,behavior_ownership,test_structure_boundary}.py`;
inventories are `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`,
`.ci/behavior-ownership/`, `.ci/module-boundaries/`, and the existing lane catalogue.
Documentation scope is README, canonical authentication/authorization/checker/task
specifications, operating manual, roadmap, and this AUTH initiative's navigation.
An additional shared consumer must be recorded before changing its implementation.

Future tests under `backend/tests/authorization/submission_history/`:

| Test | Proof |
|---|---|
| `test_exact_route_action_and_grant` | All eight GET paths, both valid PM grant scopes (project and system), exact recorded grant equality |
| `test_list_requires_owned_history` | A owns history; same-project B has Submitter but receives 404; A succeeds; removal of ownership predicate fails |
| `test_historical_owner_after_reassignment` | submitted/evaluation_pending/review_pending/needs_revision; released and reassigned; original owner succeeds, successor denied, same-person reclaim preserves history |
| `test_fixed_projection_and_selected_columns` | Separate audience DTOs and selected SQL columns, sentinel secrets and economic fields absent; hidden results and internal-only routing filtered |
| `test_cursor_scope_and_continuation` | Multiple pages, bounds/order, malformed/duplicate keys, cross-action/project/actor substitution rejected |
| `test_wrong_project_does_not_wait` | Held foreign task row, invalid project request returns 404 without waiting |
| `test_allow_commits_exact_evidence` | Independent session sees exact action/grant/project/resource digest after successful response |
| `test_product_query_failure_rolls_back` | Failure after staged ALLOW yields retryable 503; no committed ALLOW or product mutation |
| `test_response_failure_rolls_back` | Actual invalid projection fails validation, retryable 503, no committed ALLOW |
| `test_audit_insert_failure_rolls_back` | PostgreSQL rejects actual authorization audit INSERT before projection; projection nonentry, retryable 503 and rollback |
| `test_authority_unavailable` | AUTH failure yields retryable 503, no response or committed ALLOW |
| `test_denied_read_never_loads_private_rows` | Revocation, foreign owner and service/agent admission fail before private projection; concealed 404 for human resource denial |
| `test_removed_mutation_and_worker_surface` | Both old POSTs absent, old Celery task absent, deleted dependency/source names absent |
| `test_hidden_creation_does_not_queue_old_execution` | Canonical admission-backed creation remains valid, no old queue invocation or CheckerRun side effect |
| `test_verification_is_identity_only` | Flow/dev token-only result; role claims cannot grant access; no runtime identity compatibility write; issuer/subject/audience/scope/time validation preserved |
| `test_audit_migration_preserves_prior_evidence` | Seed all prior permitted action/permission pairs and both dispositions; byte-identical snapshot after upgrade; eight new exact pairs allowed, cross-pairs rejected; downgrade refuses and preserves rows |

A successful denied-resource path returns 404; malformed pagination returns422;
service/agent tokens fail canonical human admission. For each transaction failure,
observe independent-session audit state and unchanged retained product rows.
History has no task-state/current-assignment eligibility predicate: independently
introducing either predicate must fail the historical ownership matrix.

| Existing test / group | Disposition |
|---|---|
| `test_retained_packet_reads_preserve_locked_lineage_and_stored_audit` | Retarget to canonical authorized history; retain immutable lineage/audit proof |
| `test_retained_submission_versions_are_readable_without_exposing_packet_hashes` | Retarget to new pages and fixed redaction |
| `test_retained_submission_finalization_preserves_locked_guide_after_activation` | Replace old private-finalization setup with canonical admission-backed creation; retain historical guide proof |
| `test_retained_version_read_does_not_rewrite_prior_finalized_packet` | Retarget; compare stored rows before/after |
| cross-worker submission history denial tests | Retarget to distinct canonical actors/grants, exact concealed404 |
| `test_checker_revision_routing_and_reads_for_retained_packet_versions` | Retain historical read/version/currentness assertions; remove obsolete routing execution assertions |
| `test_retained_packet_checker_trial_exposes_only_role_visible_results` | Replace trial writer with retained-row fixture and fixed audience read |
| `test_worker_can_read_only_worker_visible_checker_result_fields`, `test_worker_cannot_see_hidden_checker_results` | Retarget to Submitter authority and SQL/response privacy proof |
| token-role/future-role authorization, manual checker trigger/retry, gate finalization/requeue/repair and automatic queue-only tests | Delete superseded behavior tests; keep database immutability/currentness/lineage constraints as independent retained-row tests |
| old checker-run OpenAPI role-sensitive response test | Replace with fixed read schemas and removed POST assertions |
| `authentication/test_registered_actor_dependency.py`, role normalization and development role config tests | Delete; canonical verifier and no-compatibility-write proofs remain |

The retained checker fixture inserts constraint-valid CheckerRun and CheckerResult
rows through ORM in the migrated PostgreSQL database, with real Submission and
policy foreign keys, attempt/currentness, matching locked hashes and all guards
enabled. It never invokes the deleted checker writer, queue or fabricated actor.
Canonical submission fixtures use the existing admission-backed creation path
where creation invariants are under test. Retained compatibility actor rows are
seeded only to prove byte-identical data custody, never to grant authority.


Final feasibility reconciliation: history uses the existing `AuthorizationService.require`
read transaction, not PREP: owner-qualified selector, scoped TASK lock and recheck,
fresh actor/grant/Project authority, staged ALLOW, fixed projection, validation,
then caller commit. There is no mutation gap requiring a capability lifecycle.

Reassignment/state history controls are constraint-valid retained-data fixtures,
not a newly supported release/reclaim workflow. Preserve the existing production
invalidation rule and its regression: an existing Submission prevents assignment
invalidation/release. Controlled retained rows prove that history authorization
itself never uses today's assignment or task state.

Consumer scan adds `backend/app/modules/projects/router.py` and
`backend/app/modules/projects/create_router.py`: remove their unused
`PermissionDenied` import/helper/catch with `core.permissions`. Canonical project
AUTH decisions and public behavior remain unchanged.


Implementation boundary reconciliation: TASK already depends on CHECKERS public
compiler contracts, so CHECKERS cannot import TASK even through a public port.
CHECKERS exposes only a minimal run/submission/task reference. Application
composition resolves that through TASK's public ownership selector before locks
and authorization, then requests the fixed CHECKERS projection. This preserves
acyclic owners and the intended exact historical ownership without a new subsystem.
History DTOs live in each owner's dependency-free public history module; delivery
imports owner adapters rather than private repositories or AUTH implementations.
Removed unused CHECKERS repository and obsolete TASK get/list/evidence-lock helpers
have no surviving consumers. Shared canonical submission creation remains intact.

History decisions preserve the existing project audit selector. The exact task,
submission, checker run, actor and query are bound by resource_context_digest;
tests compare the exact project, matched grant and independently computed digest.
