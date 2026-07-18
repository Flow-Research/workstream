# Chunk Contract: WS-AUTH-001-05A - Shared Audit Ownership And Append-Only Authority Evidence

## Status

Merged through PR #115 as `8e1cde6` on 2026-07-14 after required internal
reviews, Backend, Agent Gates, CodeRabbit, and explicit human approval passed.
Reviewed code SHA: `ea16fd8`; final branch head: `d023952`.

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Evolve the existing `audit_events` path into one privacy-safe, append-only,
versioned authority-evidence envelope while preserving every legacy lifecycle
event and existing task/checker behavior.

## Risk and circuit breaker

- Risk: L1 / SLA P1.
- Scope is bounded by this chunk's allowed files, explicit non-goals, acceptance
  criteria, and AUTH-05A ownership boundary rather than a production-line cap.
- Stop and replan if implementation crosses into AUTH-05B, authorization
  evaluation, grant lifecycle, route activation, or another subsystem boundary.
- Security SQL must remain reviewable as named functions and multiline logical
  clauses; line packing is prohibited.
- The scope amendment is limited to AUTH-05A's required privacy, custody,
  registry, causation, and parity controls; it does not reactivate AUTH-05B.
- A readable typed-registry dry run reached 689 changed lines before the SQL
  matrix was complete. The draft was discarded. Typed and database enforcement
  are one atomic security boundary, so they are not split across mergeable PRs.

## Allowed files

```text
backend/app/modules/audit/**
backend/app/db/models.py
backend/app/modules/tasks/models.py
backend/app/modules/tasks/repository.py
backend/alembic/versions/0018_authority_audit_evidence.py
backend/tests/test_audit.py
backend/tests/test_alembic.py
backend/tests/test_tasks.py
docs/architecture_data_model.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

`backend/tests/test_tasks.py` may receive only bounded delegation/regression
proof; the existing full task suite remains an unchanged regression target.

## Not allowed

```text
authorization idempotency records or replay orchestration
routes, dependencies, middleware, or generic core helpers
actor/profile migration or first-access behavior
permission definitions/evaluation or admin/project grants
project/task/submission/checker authorization cutover
invalidation consumers, caches, queues, or external delivery
token-role or IdentityIssuerVerifier/factory changes
workflow, dependency, coverage-threshold, skip, or exclusion changes
backfilled or fabricated authority history
repository or service commit/rollback/session creation
```

## Authority event envelope

Migration `0018_authority_audit_evidence` revises `0017_api_controls` and
extends the existing `audit_events` table. It does not create a parallel event
table. Existing rows and legacy writers retain their current values and public
behavior; no legacy row is reclassified as authority evidence.

New rows use `event_domain = authority`, `event_version = 1`, and a typed event
token from the adopted specification. Authority rows require:

- database-owned `occurred_at`;
- `request_id` and `correlation_id` UUIDs;
- namespaced acting reference kind (`legacy_actor`, `actor_profile`, or
  `system_principal`) plus the exact local reference defined below;
- optional target actor reference with all-or-none kind/reference presence;
- optional matched-grant, permission, project, resource type/id, and target
  grant/link reference;
- required authority reason classification and optional denial code;
- optional idempotency-record reference;
- optional invalidation cause event and invalidation target kind/id;
- typed shallow before/after fact objects.

Authority rows never persist external issuer, external subject, token roles,
claim snapshots, request bodies, raw tokens, JWKS documents, secrets, emails,
or URLs. Conditional database constraints reject mixed legacy/authority
shapes using this exact compatibility matrix:

- existing `id` remains the event ID, `event_type` remains the typed event
  token, and `created_at` remains the legacy timestamp;
- existing `actor_id` stores the stable local acting reference and the new
  actor-reference-kind field supplies its namespace;
- existing `entity_type`/`entity_id` remain the primary audited aggregate
  reference; optional project/resource fields provide additional exact scope;
- existing `reason` may carry only a registered authority reason code;
- `from_status` and `to_status` are `NULL` because typed before/after facts own
  authority state transitions;
- `external_subject` and `external_issuer` are `NULL`;
- `actor_roles = '[]'`, `claim_snapshot = '{}'`,
  `auth_source = 'local_authority'`, and `is_dev_auth = false`;
- `event_payload = '{}'`; authority evidence cannot use the legacy JSON payload
  as an unbounded escape hatch.

Only the external subject/issuer columns become nullable for the conditional
authority shape. Existing legacy rows and writers retain all current values
and non-authority requirements.

Every authority string/reference field has one normative form:

| Field | Allowed value |
|---|---|
| `entity_type` | `actor_profile`, `actor_identity_link`, `admin_role_grant`, `qualification_snapshot`, `project_role_grant`, `authorization_decision`, or `authority_invalidation` |
| `entity_id`, `matched_grant_id`, `project_id`, `resource_id` | canonical lowercase UUID; nullable optional fields remain nullable; decision/invalidation `entity_id` equals its event ID |
| acting `legacy_actor` or `actor_profile` reference | canonical lowercase UUID |
| acting `system_principal` reference | `workstream:system:bootstrap`; additional principals require an approved registry change |
| target actor | kind `actor_profile` plus canonical lowercase UUID |
| `resource_type` | `actor_profile`, `actor_identity_link`, `admin_role_grant`, `project`, `project_role_grant`, `task`, `submission`, `review`, `contribution`, `compensation_award`, `compensation_delivery`, `operations`, or `audit_event` |
| target/invalidation kind and reference | `actor_profile`, `actor_identity_link`, `admin_role_grant`, `qualification_snapshot`, or `project_role_grant` uses a canonical UUID; `permission_registry` uses one registered `permission_id` below |
| UUID envelope fields | native/canonical UUID for event, request, correlation, idempotency, and cause references |

`permission_id` is closed to the exact specification Section 11 catalog:
`actor.profile.read_self`, `actor.profile.update_self`,
`actor.profile.read_any`, `actor.profile.suspend`, `actor.profile.reactivate`,
`actor.profile.deactivate`, `actor.identity_link.read`,
`actor.identity_link.revoke`, `actor.identity_link.reactivate`,
`actor.service.provision`, `admin_role.read`, `admin_role.grant`,
`admin_role.revoke`, `project.create`, `project.read`, `project.update`,
`project.archive`, `project.guide.manage`, `project.effective_policy.manage`,
`project.task.manage`, `project.review_policy.manage`,
`project.role_grant.read`, `project.role_grant.manage`, `task.queue.read`,
`task.claim`, `submission.create`, `submission.read_own`,
`submission.read_for_review`, `review.queue.read`, `review.queue.inspect`,
`review.claim`, `review.release`, `review.decline_preference`,
`review.decision`, `review.lease.force_release`, `review.chain.read`,
`contribution.read_self`, `contribution.read_project`,
`compensation.policy.manage`, `compensation.adapter_binding.manage`,
`compensation.award.read`, `compensation.delivery.reconcile`,
`operations.status.read`, `operations.timer.run`,
`operations.reconcile.run`, `operations.outbox.retry`,
`operations.projection.rebuild`, `audit.read`, and `audit.export`.

`denial_code` is closed to the exact specification Section 22 codes. The
authority writer may use only: `required_scope_missing`,
`unsupported_subject_kind`, `service_actor_not_provisioned`,
`identity_link_revoked`, `actor_suspended`, `actor_deactivated`,
`permission_not_granted`, `scope_not_authorized`, `self_grant_forbidden`,
`self_role_revoke_forbidden`, `resource_guard_denied`, `actor_not_found`,
`grant_not_found`, `resource_not_found`, `actor_already_suspended`,
`actor_not_suspended`, `actor_deactivated_terminal`,
`last_access_administrator`, `admin_role_grant_exists`,
`project_role_grant_exists`, `identity_link_conflict`,
`resource_project_mismatch`, `idempotency_mismatch`, `invalid_role_scope`,
`invalid_project_role`, or `qualification_snapshot_invalid`.

Audit `reason` is a privacy-safe classification, not operator-entered text and
not a replacement for the required rationale stored on the owning domain row.
The writer never copies domain reason text into audit evidence. Reason is
required and event-compatible as follows:

| Event group | Allowed reason classification |
|---|---|
| human/service provisioning | `automatic_first_access` / `manual_service_provisioning`, respectively |
| identity link create/revoke/reactivate | `identity_lifecycle_change` |
| actor suspend/deactivate | `security_response` or `administrative_correction` |
| actor reactivate | `administrative_correction` |
| initial Access Administrator bootstrap | `initial_access_bootstrap` |
| admin/project grant issue | `authority_assignment` |
| project grant replacement | `authority_replacement` (historical foundation value; AUTH-10 removes current emission/validation under D21) |
| admin/project grant revoke | `authority_revocation` |
| admin grant/last-admin denial | `authorization_policy_denial` |
| qualification snapshot | `qualification_evidence_captured` |
| sensitive allow/deny | `authorization_evaluation` |
| invalidation request | `authority_state_changed` |

Before/after facts are JSON objects with at most eight allowlisted scalar keys,
no nested containers, and at most 4096 encoded bytes. The only fact keys and
values are: `status` in `active`, `suspended`, `deactivated`, `revoked`, or
`captured`; `subject_kind` in `human` or `service`; `provisioning_method` in
`automatic_first_access` or `manual_service_provisioning`; `role` in
`access_administrator`, `operator`, `project_manager`, `finance_authority`,
`audit_authority`, `submitter`, `reviewer`, or `adjudicator`; `scope_type` in
`system` or `project`; `scope_id` as a canonical UUID; and `effective` and
`allowed` as booleans. `effective` describes persisted authority state;
`allowed` describes an authorization decision and they are not interchangeable.

The event-specific fact matrix is exact:

| Event group | Before facts | After facts |
|---|---|---|
| human/service provisioning | `NULL` | `status=active`, matching `subject_kind` and `provisioning_method` |
| identity linked | `NULL` | `status=active`, `subject_kind` |
| identity revoked/reactivated | `status=active` / `status=revoked` | `status=revoked` / `status=active` |
| actor suspended/reactivated | `status=active` / `status=suspended` | `status=suspended` / `status=active` |
| actor deactivated | `status=active` or `suspended` | `status=deactivated` |
| initial admin bootstrap | `NULL` | `status=active`, `role=access_administrator`, `scope_type=system`, `effective=true` |
| admin/project grant issued | `NULL` | `status=active`, applicable `role`/scope, `effective=true` |
| admin/project grant revoked | active role/scope with `effective=true` | same role/scope, `status=revoked`, `effective=false` |
| qualification snapshot captured | `NULL` | `status=captured` |
| grant operation denied or last-admin denial | `NULL` | `NULL`; `denial_code` carries the attempted-operation result |
| sensitive allowed/denied | `NULL` | `allowed=true` / `allowed=false` |
| invalidation requested | `effective=true` | `effective=false` |

For grant facts, `access_administrator` and `operator` use only `system`;
`project_manager`, `finance_authority`, and `audit_authority` use `system` or
`project`; `submitter`, `reviewer`, and `adjudicator` use only `project`.
`scope_id` is absent for system scope and required for project scope.
System-scope grant evidence has `project_id = NULL`. Project-scope grant evidence requires
`project_id`, and every before/after `scope_id` equals that envelope value. When
`resource_type = project` and `resource_id` is present, `resource_id` also
equals `project_id`. Typed and direct-SQL paths enforce these cross-field rules.
Typed validation and database constraints enforce the identical envelope and
fact matrices. Table-driven tests execute the same positive and negative cases
through Pydantic and direct SQL; lexical bounds alone are insufficient.

AUTH-10 supersedes the original combined-role and cross-role replacement
contract for new evidence. Previously persisted audit evidence remains
readable, but new issue/revoke evidence uses one independent submitter,
reviewer, or adjudicator grant.

The typed admission layer inspects every `collections.abc.Mapping`, including
non-dict mappings, before Pydantic owns rejected values. Unknown fields and
privacy-invalid known values raise one stable non-echoing error. A sanitized
`AuthorityAuditEventInput.model_validate_json` override replaces malformed,
scalar, list, string, bytes, and bytearray decode/type failures with that same
value-free error instead of exposing a decoder `.doc` or Pydantic input.
Constructor, `model_validate`, and `model_validate_json` tests traverse
structured errors, arguments, causes, contexts, and public object graphs to
prove forbidden input is not retained.

AUTH-05A behavior tests exercise these exact foundation shapes:

- `SensitiveAuthorizationAllowed` requires permission, forbids denial code and
  invalidation cause/target, and permits an optional canonical UUID
  idempotency reference for later AUTH-05B orchestration;
- `SensitiveAuthorizationDenied` requires permission plus a registered denial
  code and forbids invalidation cause/target and idempotency reference;
- `AuthorityInvalidationRequested` requires cause-event ID plus all-or-none
  target kind/reference, forbids denial code, and permits an optional canonical
  UUID idempotency reference for later AUTH-05B orchestration.

The 05A envelope and database constraints are final for the idempotency-reference
field: it has no foreign key to an idempotency table before AUTH-05B, and 05A
introduces no idempotency lookup or replay behavior. Tests persist both `NULL`
foundation use and a syntactically valid non-NULL future reference without
creating an idempotency record. AUTH-05B consumes this existing field without
changing audit schema, constraints, repository, or writer behavior.

Invalidation causation is a separate integrity boundary. Self, nonexistent,
and legacy-domain cause references are rejected; an invalidation cause must be
an existing authority event visible in the caller transaction. The typed
service and database insertion boundary enforce that rule without activating
an invalidation consumer or AUTH-05B replay behavior.

Target actor kind/reference and target/invalidation kind/reference are
all-or-none pairs. `resource_id` requires `resource_type`, but `resource_type`
may have a `NULL` ID for a system-wide decision as allowed by the adopted
`AuthorizationDecision` contract.

## Shared writer and append-only custody

- `AuditRepository` is the only supported insert/read implementation.
- `TaskRepository.add_audit_event` and `list_audit_events` remain temporary
  compatibility methods but delegate the same session/event/query to
  `AuditRepository`; task/checker call sites and responses do not change.
- Supported application APIs expose insert/read only.
- Named PostgreSQL triggers reject every `audit_events` UPDATE, DELETE, and
  TRUNCATE, regardless of event domain or session flag. Failed attempts leave
  both legacy and authority rows unchanged.
- No application-settable GUC or current-user bypass exists.
- The protection is a normal-DML custody boundary, not a defense against the
  table owner or DDL credentials. Production rollout requires a distinct
  non-owner runtime role without trigger/DDL privileges. The runbook documents
  that deployment gate and a separately controlled DB-owner maintenance
  procedure using an exclusive lock, explicit trigger disable/re-enable,
  transaction, change record, and post-check. Migration teardown is the only
  ordinary trigger-removal path.

## Migration custody

- Upgrade `0017 -> 0018` preserves representative populated prior-head domain
  and legacy audit rows without fabricating authority fields.
- Tests assert exact columns, nullability, defaults, constraints, indexes,
  trigger/function names, invalid direct inserts, and database time.
- Downgrade takes writer-blocking locks before inspection and refuses without
  mutation when any authority-domain audit row exists.
- Privileged test cleanup may delete only explicit fixture authority rows after
  deliberately disabling/re-enabling the trigger under lock; legacy rows are
  never deleted by downgrade.
- Empty authority evidence permits `0018 -> 0017 -> 0018`; re-upgrade recreates
  all triggers. Destructive migration tests restore Alembic `head` in `finally`.

## Acceptance criteria

- Legacy audit writers/readers and task/checker response projections remain
  behaviorally unchanged.
- Typed allowed, denied, and invalidation authority event shapes persist only
  bounded non-sensitive evidence and reject malformed/mixed shapes.
- Rejected provider/email/URL/token-like inputs are absent from every public
  exception object graph for dict and non-dict mapping inputs.
- Typed and direct-SQL paths enforce closed reason/fact registries and matching
  entity/type/reference privacy bounds.
- Application-role normal DML cannot update, delete, or truncate any audit row.
- Shared-writer tests instrument `AuditRepository` and prove TaskRepository
  compatibility methods pass the same session/event and return the shared
  result; row-count-only proof is insufficient.
- No new route, dependency, middleware, permission, grant, actor, product
  authority behavior, or invalidation consumer exists.

## Verification

```bash
cd backend
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT
.venv/bin/python scripts/run_isolated_tests.py --metadata-json "$tmp_dir/05a.json" --timeout-seconds 1800 -- \
  .venv/bin/python -m pytest -q \
  tests/test_alembic.py::test_authority_audit_schema_preserves_legacy_and_guards_downgrade \
  tests/test_audit.py \
  tests/test_tasks.py::test_task_repository_delegates_audit_persistence \
  tests/test_tasks.py::test_manual_checker_run_cannot_bypass_failed_automatic_gate \
  tests/test_tasks.py::test_queued_gate_fails_closed_when_lock_audit_is_missing
.venv/bin/python scripts/run_isolated_tests.py --metadata-json "$tmp_dir/05a-coverage.json" --timeout-seconds 1800 -- \
  .venv/bin/python -m pytest -q tests/test_audit.py \
  tests/test_tasks.py::test_task_repository_delegates_audit_persistence \
  --cov=app.modules.audit --cov-report=term-missing --cov-fail-under=90
.venv/bin/ruff check app tests
.venv/bin/docstr-coverage --config .docstr.yaml
.venv/bin/python - <<'PY'
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, "scripts")
from coverage_policy import weak_python  # noqa: E402

paths = subprocess.check_output(
    ["git", "diff", "--relative", "--name-only", "origin/main...HEAD", "--", "tests"],
    text=True,
).splitlines()
blocked = [path for path in paths if path.endswith(".py") and weak_python(Path(path))]
raise SystemExit(f"test weakening: {blocked}" if blocked else 0)
PY
cd ..
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_internal_review_evidence.py
changed_production_lines=$(git diff --unified=0 origin/main...HEAD -- backend/app backend/alembic | \
  awk '/^\+\+\+|^---/{next} /^[+-]/{line=substr($0,2); if (line !~ /^[[:space:]]*($|#)/) n++} END{print n+0}')
printf 'AUTH-05A changed production lines: %s\n' "$changed_production_lines"
awk 'length($0) > 120 { print FNR ":" $0; bad=1 } END { exit bad }' \
  backend/alembic/versions/0018_authority_audit_evidence.py
if git diff --unified=0 origin/main...HEAD -- backend/tests | \
  rg '^-(.*assert|.*pytest\.raises|.*pytest\.mark\.(skip|xfail)|.*pytest\.(skip|xfail)|.*skipTest)'; then exit 1; fi
git diff --check
```

Run the exact migration node before audit/delegation tests on the same isolated
database. Do not repeat the multi-hour local full suite after focused repairs;
GitHub Backend CI remains the final repository-wide `--cov-fail-under=78` gate.
Test delta must be additive: no assertion, raises, skip, xfail, threshold,
workflow, or exclusion weakening.

## Required reviewers

- senior engineering
- QA/test
- security/auth and privacy
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Review legacy audit compatibility, sole writer ownership, authority-envelope
privacy, unconditional normal-DML immutability, migration custody, and the
documented non-owner production role requirement.

## Stop conditions

Stop if legacy event behavior changes, authority evidence needs a canonical
ActorProfile FK, normal application DML can mutate history, production scope
exceeds the circuit breaker, or tests/CI must be weakened.
