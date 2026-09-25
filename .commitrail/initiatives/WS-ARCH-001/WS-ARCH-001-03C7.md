# ARCH-03C7 — Exact-authorized bounded task audit history

- Initiative: WS-ARCH-001
- Durable disposition: Complete
- Intended merge outcome: expose existing bounded lifecycle evidence to covered
  Audit Authority and remove the obsolete task-only audit route.
- Risk class: L1 (authorization, private audit data, append-only evidence schema).

## Intent

Main includes ARCH-03C6. ARCH-03B8 already owns the immutable bounded evidence
projection and one project/task-scoped AUDIT query. The remaining
`GET /tasks/{task_id}/audit-events` uses token-role/creator checks and unbounded
payload-bearing responses. Replace that public path; do not preserve a fallback.
This is audit inspection, not submission, review, checker activation or an export.
Leases and voluntary skip remain deferred. Open CI PRs own unrelated workflow
changes; this PR does not alter workflow selection or thresholds.

## Bounded change

Expose `GET /api/v1/audit/projects/{project_id}/tasks/{task_id}/evidence`, action
`audit.task.evidence.read`, existing permission `audit.read`, covered project or
system `Audit Authority` only. Other admin roles sharing `audit.read`, contributor
ownership, task creation and token roles do not confer access. Nonhuman admission
precedes TASK composition. Missing/foreign/denied selectors conceal alike as 404.
Pass `allowed_roles=frozenset({AdminRole.AUDIT_AUTHORITY})` through the existing
project-admin locker and repository grant filter; a permission-only lookup is
insufficient because all five administrative roles share `audit.read`.

Reuse `AuditTaskEvidenceRequest`, `AuditTaskEvidencePage` and the TASK repository
projection. All nine task states, including an unbound draft, are inspectable;
history does not require or revalidate a historical policy body. Fixed items
contain only event ID/type, status transition, stored actor ID, timestamp, and
validated assignment/decision references. No claim snapshots, raw JSON, private
reason, external identity, source/artifact URI or policy body is returned.

Query `limit` defaults to 50 and is bounded 1..100. Optional `cursor` is bounded
JSON encoding the existing `TaskEvidenceCursor` (project/task, aware timestamp,
event UUID), capped at 512 raw characters before decoding. Require exactly
`project_id`, `task_id`, `created_at`, `event_id`, all string values; reject duplicate
keys, extra/missing keys, naive/malformed timestamps, malformed UUIDs and crossed
scope. A route dependency raises sanitized 422 before entering the TASK operation;
direct callers validate the typed request before starting its transaction. This
does not promise that authentication/rate-control or identity SQL is absent.
Return the existing typed
cursor object as `next_cursor`. It is a live ascending position, not a capability,
snapshot or proof that an anchor exists. Revalidate current authority on every
page. Unlike queue-specific signed audience tokens, these fixed evidence
positions confer no additional selection power; no new signer/codec is needed.

Extend the existing TASK authority operation, exact concealed-read set and
resource guard. Reject mutation/replay fields. Reuse `_locked_task` with both
selectors: TASK row -> active assignment -> AUTH actor/link -> exact Audit
Authority grant. Filter project before any task lock. No PROJECTS lock or second
authority lookup. The existing inner evidence read stays nonlocking and retains
caller transaction ownership; the public operation owns authorization locks and
its transaction. Authorization evidence binds the exact task facts, not a claim
to export the returned page. Validate/serialize the complete bounded response
before committing ALLOW; read, reference, serialization and evidence failures
roll back. Sanitized invalid evidence is 422. Existing denial restaging remains.

Migration `0005_task_evidence_authority`, after `0004_task_context_authority`,
extends only the existing closed audit action/permission constraint with
`audit.task.evidence.read` / `audit.read`. Preserve prior records and exact pairs;
do not rewrite data or add a downgrade path. Update current schema fingerprints,
head checks and existing exact catalogue/route/lane inventories together. Keep
catalogue validation within existing size limits by separating row-shape from
closed-metadata validation without changing validation precedence.

## Cleanup and explicit retained dependencies

Remove the old route, `TaskService.list_task_audit_events`, `_audit_response`,
`AuditEventResponse`, and their exclusively used contributor-redaction constants.
Replace obsolete public-audit tests. Retain/rehome required transition,
submission-lock, repair provenance and private-data tests: internal full-payload
assertions use the real retained repository reader; public tests assert the new
fixed-field contract and old-route absence. No compatibility test helper calls
the removed endpoint. The shared `list_audit_events` repository method remains
required by `_locked_submission_context` recovery and shared audit consumers.
The role/creator helper still serves retained submission reads/hidden creation;
trace those consumers explicitly, but do not widen this PR into their cutover.

## Allowed files and prohibited changes

- TASK `router.py`, `authorized_commands.py`, `service.py`, `schemas.py`, and
  `api/{authorization,audit_evidence}.py`; no public TASK import of AUTH/PROJECTS.
- AUTH `catalogue.py`, `domain/task_authority.py`,
  `artifact_project_authority.py`; existing dependency composition only if the
  current shared error mapping needs an exact action declaration.
- One migration; existing Alembic head/schema assertions and exact inventories.
- `tests/authorization/task_audit_evidence/`, migration test; affected
  `tests/tasks/test_audit_evidence.py`, `tests/test_tasks.py`, `tests/test_checkers.py`, API/catalogue/lane
  tests and `scripts/api_contract_e2e.py`/`test_lane_catalogue.py`; the API drill
  idempotency key registration in `scripts/identifier_generation_classifications.json`.
- Selected MCP authorization-context snapshot: enum/digest/source provenance.
- README, glossary, canonical TASK/AUTH/data-model specs, operating manuals, roadmap and
  existing ARCH navigation; update any present local roadmap exports together.

No lifecycle transition, grant permission, claim/start, retained data, business
policy, API compatibility alias, new generic framework, worker, deployment,
frontend, private guide fixture, dependency or CI gate/threshold change.

## Acceptance criteria

1. Signed role/scope matrix proves only project/system Audit Authority succeeds;
   dual-role actor selects the exact audit grant, stored ALLOW and DENY identities
   are correct, and revoked grant/link/profile cannot read or continue a page.
2. Exact public route/action/response and old route/schema/wrapper absence;
   invalid UUID/limit/cursor/cross-scope cursor fails before product locks/read;
   nonhuman actor cannot enter TASK composition. Empty/draft and all states work.
   Oversized/deep/duplicate-key/extra-key/malformed-offset cursor controls and a
   pre-decode-cap removal probe protect the parser boundary.
3. Real pagination covers ties, limit-one traversal, exhaustion, absent anchors,
   project/task isolation and fixed private-field exclusion. Retain the inner
   SQL column/transaction/no-lock tests rather than rewriting them as HTTP tests.
4. Real PostgreSQL wrong-project request returns without waiting on a foreign
   task lock. Revocation interleavings preserve live authority and lock order.
   Response/reference failures roll back a genuinely staged ALLOW and marker.
   Separately, a failed audit write proves a real write attempt and marker rollback,
   with no projection entry; it cannot claim a successfully staged ALLOW.
5. Migration retains predecessor rows byte-for-byte (all three 0004 pairs,
   ALLOW/DENY); exact new pair succeeds, substituted permission fails specifically
   at the constraint. Disabling that constraint makes the negative probe fail.
6. Guard-removal probes discriminate role filtering, project-scoped locking,
   forbidden command fields and rollback/serialization boundaries. Positive
   controls must reach the intended guard; do not obtain denial via another guard.

## Evidence

Implementation test functions under `tests/authorization/task_audit_evidence/`:

- `test_contracts.py`: `test_public_contract`, `test_cursor_validation`,
  `test_cursor_cap_probe`, `test_http_cursor_rejection_before_task`,
  `test_http_cursor_cap_probe`, `test_command_field_guard`, `test_command_guard_probe`,
  `test_nonhuman_admission`.
- `test_authority.py`: `test_exact_role_matrix`, `test_dual_role_grant_identity`,
  `test_continuation_rechecks_authority`, `test_role_filter_probe`.
- `test_history.py`: `test_all_task_states`, `test_state_guard_probe`,
  `test_history_pagination_and_privacy`, `test_invalid_reference_is_sanitized`.
- `test_transactions_concurrency.py`: `test_post_consume_rollback`,
  `test_audit_write_rollback`, `test_wrong_project_does_not_wait`,
  `test_task_only_lock_probe`, `test_revocation_serialization`.
- `tests/migrations/test_task_evidence_authority.py`:
  `test_evidence_migration_retains_rows`, `test_evidence_migration_exact_pair`,
  `test_evidence_constraint_probe`.

Retained/reconciled existing nodes include `tests/test_tasks.py::test_full_task_claim_start_flow_writes_audit_events`,
`::test_finalization_repair_is_authorized_attributed_and_idempotent`,
`::test_task_service_finalization_provenance_fails_closed_without_lock_audit`,
Their private assertions read committed records through the owner, not an HTTP
redaction imitation. The complete affected caller disposition is:

| Existing node (under `backend/tests/`) | Disposition |
|---|---|
| `test_tasks.py::test_task_router_service_errors_use_canonical_request_context` | Replace obsolete route/wrapper case with new operation |
| `test_tasks.py::test_full_task_claim_start_flow_writes_audit_events` | Retain all stored transition/provenance assertions through repository |
| `test_tasks.py::test_different_worker_cannot_start_or_read_claimed_task` | Retain start/detail guards; audit denial covered by new signed matrix |
| `test_tasks.py::test_retained_packet_reads_preserve_locked_lineage_and_redact_audit` | Retain packet lineage and stored audit facts; replace obsolete public redaction in new privacy proof |
| `test_tasks.py::test_submitted_task_rejects_earlier_lifecycle_actions_without_new_task_audit` | Compare committed lifecycle evidence before/after denied mutations |
| `test_tasks.py::test_cross_worker_cannot_list_submissions_or_audit_after_submit` | Retain submission denial; audit denial covered by new signed matrix |
| `test_tasks.py::test_finalization_repair_is_authorized_attributed_and_idempotent` | Retain repair authority, exact stored requester/provenance and event counts |
| `test_checkers.py::test_locked_submission_checker_run_persists_results_and_allows_review` | Retain stored gate trigger facts through repository |
| `test_checkers.py::test_checker_revision_routing_and_reads_for_retained_packet_versions` | Retain checker/revision/submission guards; replace obsolete audit redaction with fixed privacy/denial proof |
| `test_checkers.py::test_retained_packet_setup_failure_stays_blocked_until_repaired` | Retain stored blocked/gate payload and repair evidence; replace obsolete worker audit view |

Keep `tests/tasks/test_audit_evidence.py::test_task_evidence_sql_privacy`,
`::test_task_evidence_caller_transaction`, and `::test_task_evidence_does_not_lock`
as existing inner-reader proofs; update only its obsolete hidden-surface test.
Run focused signed
PostgreSQL cases and existing inner evidence/recovery tests; Ruff, module/AUTH/
test boundaries, ownership and identifier-generation inventories, exact lanes,
stale wording, Markdown links,
Commitrail and hosted full PostgreSQL/MinIO coverage. Current schema head 0004;
expected head 0005. Runtime results are separate from this plan's feasibility.

## Risk and review routing

Before code: security/architecture/reuse and QA/product-ops plan review, including
feasibility of retained recovery assertions after old-route removal. After a
clean candidate: those tracks plus test-delta, docs and CI integrity. Human focus:
covered Audit Authority only, fixed evidence fields, exact project/task locks,
atomic read evidence and absence of obsolete public authority.

After this boundary, reconcile ARCH-03C completion and proceed separately to
public guide activation/approved-guide intake integration. Do not claim immutable
Submission or post-submit execution publicly delivered by this read operation.

## Plan corrections

- SEC-03C7-PLAN-01: make the exact Audit Authority role filter explicit, with
  dual-role matched-grant equality and every other shared-permission role denied.
- SEC-03C7-PLAN-02: define the pre-decode bound and closed cursor syntax; no
  signing framework or promise about pre-authentication validation is added.
- ARCH-03C7-PLAN-03: include the five checker-test callers. Preserve full-payload
  checker/requester/provenance assertions through the retained internal reader;
  replace obsolete public redaction assertions with fixed-field privacy and denial.
- QA-03C7-PLAN-01/02: use canonical record headings and exact future test nodes.
- QA-03C7-PLAN-03: distinguish failed audit-write rollback from post-consume
  response failures; only the latter assert successfully staged ALLOW evidence.
