# ARCH-03C6 — Exact-authorized task locked-context reads

- Initiative: WS-ARCH-001
- Durable disposition: Planned
- Intended merge outcome: three exact-authorized public locked-context reads
  replace the role/creator-based task route, retaining historical policy identity.
- Risk class: L1 (authorization, historical policy disclosure, audit schema).

## Intent

Merged ARCH-03C5 supplies exact task detail and requirements. ARCH-03B6 already
owns three frozen locked-context projections and the shared historical resolver.
The remaining `/tasks/{task_id}/locked-context` route still calls
`TaskService.get_task_locked_context` with token-role/creator authority. Replace
that route and wrapper; do not preserve an alias or a second authority path.

Locked-context provenance and paginated audit history are distinct operations.
This chunk completes the three scalar policy-reference reads. Audit evidence
activation and removal of its retained broad route follow as ARCH-03C7, using
03B8's existing bounded projection. Public guide/intake integration follows that
remaining authority work. Leases and voluntary skip remain deferred.

## Bounded change

All routes below are GET under `/api/v1` with UUID project/task selectors.

| Route | Action | Existing permission and principal |
|---|---|---|
| `/projects/{project_id}/tasks/{task_id}/locked-context` | `project.task.locked_context.read` | `project.task.manage`; covering project/system Project Manager |
| `/operations/projects/{project_id}/tasks/{task_id}/locked-context` | `operations.task.locked_context.read` | `operations.status.read`; system Operator only |
| `/audit/projects/{project_id}/tasks/{task_id}/locked-context` | `audit.task.locked_context.read` | `audit.read`; covering project/system Audit Authority |

Manager output remains `ManagementTaskLockedContext`, including the bounded
historical checker summary. Operator and Audit Authority receive their existing
reference-only models, never policy bodies, management summary, task instructions,
actor claims, artifact paths or audit payloads. These reads may inspect any task
state only when its complete historical locked context validates. Draft/missing
or corrupt context returns the existing 422 domain error. Missing, foreign and
denied valid selectors conceal alike as 404; malformed UUID syntax is 422.
Nonhuman admission occurs before TASK composition; token roles alone confer no
access. Existing assignment ownership is not an access requirement for these
three administrative reads.

## Existing operation and transaction

Extend `TaskAuthorityOperation`, catalogue and TASK resource rules with the
three exact read actions. Replace the existing detail-only action set with a
closed concealed-read union that includes these three actions and is shared by
resource guards and HTTP denial/restaging. No compatibility alias. These actions
are separate from mutation guards and reject
idempotency/replay/request-digest command fields. Reuse
`AuthorizedTaskCommands._locked_task` with both selectors, so wrong-project
requests cannot lock a foreign task. Preserve TASK -> active assignment -> AUTH
actor/link -> matched grant -> historical PROJECTS custody lock ordering.

Reuse the existing PREP adapter and project-admin authority locker; require
system scope explicitly for the operational read, as for Operator start.
`audit.read` is shared by all five admin roles, so permission alone is insufficient.
Pass action-specific `allowed_roles` through the existing locker into the existing
repository filter: Project Manager, Operator, or Audit Authority respectively.
Do not change global role permissions or add a second grant-selection query.
Use the already locked task and the sole `_load_locked_task_context` resolver,
then the existing management/reference constructors. Do not call a second
locking wrapper after AUTH. Validate/serialize the exact audience model before
committing ALLOW evidence. Projection, custody, serialization or audit failures
roll back the caller operation; denied authority uses existing rollback/restage
custody. Record the exact grant, actor, action/project and locked-context digest.
Never select today's policy or require current installed checker capability.

## Allowed files and prohibited changes

Allowed: existing TASK authorization API, commands, router, service and response
model wording; AUTH catalogue/resource rules/project authority dispatch; migration
`0004_task_context_authority` after 0003, Alembic admission and schema
fingerprint fixtures; affected route/call-site/action inventories and tests;
MCP authorization-context selected snapshot for additive ActionId changes;
canonical API drill; current TASK/AUTH specs, README/manual/roadmap and ARCH
navigation/records. New focused tests under
`backend/tests/authorization/task_locked_context/` use existing real actor,
project and task fixtures, with exact lane registration. Existing projection,
history, corruption and private-field tests remain required.

No new grantable permission, generic read workflow, new projection abstraction,
policy writer, claim/start/submission mutation, checker execution, public audit
history activation, leases/skip, compatibility route, retained-data deletion,
baseline rewrite, threshold weakening or dependency change. Remove `read_management_task_locked_context`,
`read_operational_task_locked_context` and `read_audit_task_locked_context`: only
tests consume them, and new commands already hold the task lock. Preserve the
shared `_read_locked_context`/`_lock_scoped_task` methods required by existing
requirements consumers, plus response constructors/historical resolver. Old role
helpers remain only for traced unaffected Submission/audit callers.

## Acceptance criteria

1. Signed HTTP matrix for all three audiences: project/system covering grants,
   foreign grants, creator without grant, forged token roles, Submitter and
   unrelated admin roles. Assert exact matched grant IDs, not only non-null.
   A dual-role actor with Project Manager and Audit Authority must select exactly
   the Audit Authority grant on the audit route. A creator-without-grant case
   creates under a real Manager grant then revokes it. Operator project grants
   are forbidden by the existing role-scope schema; test system-only dispatch
   using a valid system Operator and a missing-keyword mutation, preserving
   the schema control instead of inventing an invalid grant fixture. Check
   nonhuman admission nonentry and independently omitted concealed-action/
   command-field guards.
2. For each of the three audiences, cover all nine persisted task states with
   complete locked context; independently reload the exact state/context before
   each read. A restrictive status-allowlist mutation must fail.
   Exact project/task filtering: foreign/missing/denied 404 equivalence; hold a
   real foreign task row locked and require each wrong-project route to return
   before release. Restoring a task-only lookup must fail this regression.
3. Valid same-project reads wait on TASK, refresh stale rows and retain lock
   order. Real grant revocation interleavings serialize read/deny correctly.
   Link/profile revocation invalidates future reads. No AUTH mock substitutes
   for these runtime proofs.
4. Exact original policy references/checker summary survive a distinct successor
   guide; operational/audit projections exclude management fields. Draft/corrupt
   history fails without committing ALLOW. Response serialization and audit
   insertion failures roll back evidence. Before injecting response failure,
   observe a genuine selected projection and staged ALLOW, then independently
   prove response/audit failure rolled back both evidence and a transaction
   marker. Preserve existing historical fixtures.
5. Migration preserves retained evidence, accepts each new exact action/permission
   pair and rejects mismatches under real PostgreSQL; guard-removal mutation
   proves the intended check. Keep baseline, 0002, 0003 and head downgrade refusal.
6. `tests/tasks/test_locked_context.py` retains immutable DTO/private-field
   contracts; selector/scope/corruption/TASK-wait proofs move to authorized
   operations. `test_project_display.py` before/after distinct successor checks
   use all three public routes with actual grants. Caller-pending transaction
   tests tied only to removed wrappers are replaced by authorized transaction
   proof; requirements still retain their shared caller-owned resolver tests.
   `test_tasks.py` and the API drill use the new route; old wrapper-only and
   old-public-surface expectations are removed.
   Old endpoint, wrapper and wrapper-only tests are removed; affected callers use
   the canonical new route with actual grants. API/OpenAPI, selected MCP snapshot
   and exact catalogue/lane inventories agree without broad allowlists.

## Evidence

Verification: focused PostgreSQL/HTTP/contracts and affected TASK tests; Ruff,
module/AUTH boundaries, structural inventory, Markdown links and Commitrail;
hosted full backend/coverage, API drill and MCP contract checks. Required new
behavior coverage remains >=90%; preserve the existing global floor. No local
full-suite duplication. Runtime evidence must retain its original Git custody.

## Risk and review routing

Plan: security/architecture/reuse and QA/test-delta/product-operations tracks.
Implementation: affected tracks plus documentation and CI integrity. Human focus:
role/scope separation, private-field exclusion, lock order and original immutable
policy lineage. Reviewers receive a clean exact candidate and shared evidence.

## Reconciliation

Base is `4fd44fae` after merged PR #440. No open product PR owns these reads.
Open CI initiatives remain separate. Roadmap and current navigation must advance
locked-context reads to delivered and name only audit history as remaining
03C read authority. No local spreadsheet exports are present.


## Delivered boundary and retained dependencies

The three routes reuse AuthorizedTaskCommands, PREP and the historical policy
resolver. The closed action catalogue gains three actions and no permission.
Migration 0004 admits only their evidence pairs. The task-only route and four
unused service wrappers are removed. Existing requirements retain their shared
resolver; unaffected Submission and broad audit-history callers still use their
traced authority helpers. Replacing audit-history access is ARCH-03C7, not a
compatibility path in this change.

Proof locations: `authorization/task_locked_context` covers exact grants,
concealment, revocation, rollback, all-state historical facts and lock ordering;
`tasks/test_project_display.py` retains distinct-successor public history proof;
`tasks/test_locked_context.py` retains immutable/private-field DTO proof;
`migrations/test_task_context_authority.py` covers exact SQL pairs and retention.
Old wrapper-only tests are replaced by the authorized operation proofs. Hosted
CI supplies full-suite, API drill and MCP evidence; local runs remain focused.
No local roadmap spreadsheet exports are present. Current docs and navigation
advance only locked-context reads; public guide activation and audit history
remain pending.
