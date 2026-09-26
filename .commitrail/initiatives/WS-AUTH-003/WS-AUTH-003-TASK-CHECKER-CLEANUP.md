# WS-AUTH-003-TASK-CHECKER-CLEANUP — Remove alternate TASK/checker authorization

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
- AUTH exact history actions, resource facts, prepared decisions and existing
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
rows. Contributor list authorization binds task/project/actor, then filters
Submission ownership; details bind the exact persisted submission contributor.
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
CHECKERS owns retained run/result queries and projections, consuming only TASK's
public target/ownership port. AUTH adapters implement the owners' typed authority
ports; application composition wires them. No new CHECKERS import of TASK private
models/repositories, no TASK import of CHECKERS private services, and no extension
of generic task-operation facts to smuggle checker reads through another action.

Use separate frozen closed contributor/management DTOs. Contributor submission
fields: id, task_id, version, status, summary, submitted_at, locked_at,
supersedes_submission_id, and evidence descriptors (id/type/label/size_bytes).
Management adds contributor_id, task_assignment_id and exact locked guide/policy
identifiers, versions and policy hashes including ContributionPolicy version ID.
Neither projection includes attestation, package URI/hash/manifest, evidence
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
scoped project lock. Recheck the target/query binding before consuming authority,
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
