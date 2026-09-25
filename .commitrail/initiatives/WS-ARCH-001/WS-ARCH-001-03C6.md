# ARCH-03C6 — Exact-authorized task locked-context reads

- Initiative: WS-ARCH-001
- Durable disposition: Planned
- Intended merge outcome: three exact-authorized public locked-context reads
  replace the role/creator-based task route, retaining historical policy identity.
- Risk class: L1 (authorization, historical policy disclosure, audit schema).

## Intent and current-source review

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

## Exact public contract

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
three exact read actions. They are separate from mutation guards and reject
idempotency/replay/request-digest command fields. Reuse
`AuthorizedTaskCommands._locked_task` with both selectors, so wrong-project
requests cannot lock a foreign task. Preserve TASK -> active assignment -> AUTH
actor/link -> matched grant -> historical PROJECTS custody lock ordering.

Reuse the existing PREP adapter and project-admin authority locker; require
system scope explicitly for the operational read, as for Operator start.
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
`0004_task_locked_context_authority` after 0003, Alembic admission and schema
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
baseline rewrite, threshold weakening or dependency change. Shared hidden owner
methods and old role helpers remain only where traced unaffected Submission or
audit consumers still require them; identify those dependencies explicitly.

## Acceptance and proof

1. Signed HTTP matrix for all three audiences: project/system covering grants,
   foreign grants, creator without grant, forged token roles, Submitter and
   unrelated admin roles. Assert exact matched grant IDs, not only non-null.
   Check Operator system-only scope and nonhuman admission nonentry.
2. Exact project/task filtering: foreign/missing/denied 404 equivalence; hold a
   real foreign task row locked and require each wrong-project route to return
   before release. Restoring a task-only lookup must fail this regression.
3. Valid same-project reads wait on TASK, refresh stale rows and retain lock
   order. Real grant revocation interleavings serialize read/deny correctly.
   Link/profile revocation invalidates future reads. No AUTH mock substitutes
   for these runtime proofs.
4. Exact original policy references/checker summary survive a distinct successor
   guide; operational/audit projections exclude management fields. Draft/corrupt
   history fails without committing ALLOW. Response serialization and audit
   insertion failures roll back evidence. Preserve existing historical fixtures.
5. Migration preserves retained evidence, accepts each new exact action/permission
   pair and rejects mismatches under real PostgreSQL; guard-removal mutation
   proves the intended check. Keep baseline, 0002, 0003 and head downgrade refusal.
6. Old endpoint, wrapper and wrapper-only tests are removed; affected callers use
   the canonical new route with actual grants. API/OpenAPI, selected MCP snapshot
   and exact catalogue/lane inventories agree without broad allowlists.

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
