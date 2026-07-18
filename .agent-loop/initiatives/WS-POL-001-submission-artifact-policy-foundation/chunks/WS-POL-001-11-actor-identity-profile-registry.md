# Chunk Contract: WS-POL-001-11 - Actor Identity And Profile Registry

Historical implemented chunk contract. It records the transitional authority
model used by PR #74 and is not a current authorization source. ADR 0012,
ADR 0015, `docs/spec_authorization_service.md`, and WS-XINT-001 supersede its
token-role and typed-profile authorization language.

## Parent initiative

WS-POL-001 - Submission Artifact Policy Foundation

## Goal

Add local Workstream actor identity and actor profile registries for verified
Flow actors so every operator, contributor, reviewer, project manager, project
owner, and system actor has a durable Workstream identity anchor and a shared
profile model for workflow metadata before task assignments, audit events, and
later reputation records attach to them.

## Why this chunk exists

`WS-POL-001-10` made worker profile creation a real API flow, but it also made
the remaining profile gap obvious: Workstream currently resolves `ActorContext`
from Flow tokens and stores actor snapshots on worker profiles and audit
events, while worker/reviewer/admin/project-manager/project-owner profile state
would otherwise drift into separate one-off implementations.

The correct boundary is:

```text
Flow token verification
-> trusted ActorContext
-> Workstream ActorIdentity is created/refreshed
-> Workstream ActorProfile rows are created/refreshed for observed profile types
-> workflow records attach to actor_id and profile context where needed
```

`ActorIdentity` and `ActorProfile` are not authentication. Flow remains the auth
provider. Workstream still does not own login, signup, password reset, password
storage, or primary auth sessions. Workstream owns product authorization. A
later Workstream-owned role-assignment layer will store product roles on local
`ActorIdentity` records derived from verified Flow issuer plus subject; this
chunk only adds the shared identity/profile registry needed before that layer.
In the v0.1 bootstrap, route access may still use trusted roles from the
verified `ActorContext` until Workstream-owned role assignment records are
implemented.

Persisted `ActorProfile.profile_type` is metadata, eligibility, audit context,
and later routing/reputation context. It may be required as an additional
workflow condition, but it is not the canonical product role-assignment table
and must never grant route access by itself.

## Approved plan reference

- INTENT:
  `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/INTENT.md`
- PLAN:
  `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/PLAN.md`
- CHUNK_MAP:
  `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed implementation files

```text
backend/alembic/versions/*_actor_identity_profile_registry.py
.github/workflows/backend.yml
backend/app/api/router.py
backend/app/api/deps/auth.py
backend/app/api/routes/auth.py
backend/app/adapters/auth/flow.py
backend/app/core/config.py
backend/app/db/models.py
backend/app/schemas/auth.py
backend/app/modules/audit/__init__.py
backend/app/modules/audit/repository.py
backend/app/modules/actors/__init__.py
backend/app/modules/actors/models.py
backend/app/modules/actors/repository.py
backend/app/modules/actors/schemas.py
backend/app/modules/actors/service.py
backend/app/modules/checkers/router.py
backend/app/modules/projects/router.py
backend/app/modules/projects/service.py
backend/app/modules/tasks/models.py
backend/app/modules/tasks/repository.py
backend/app/modules/tasks/router.py
backend/app/modules/tasks/schemas.py
backend/app/modules/tasks/service.py
backend/tests/test_actors.py
backend/tests/test_alembic.py
backend/tests/test_auth.py
backend/tests/test_projects.py
backend/tests/test_tasks.py
backend/scripts/api_contract_e2e.py
backend/scripts/week2_api_e2e.py
examples/terminal_benchmark/terminal_benchmark_api_e2e.py
examples/terminal_benchmark/LOCAL_VALIDATION_NOTES.md
README.md
docs/internal_reviews/2026-06-13_week1_week2_deterministic_hardening.md
docs/architecture_data_model.md
docs/architecture_brief/workstream_architecture_brief.md
docs/architecture_lockdown.md
docs/architecture_system_architecture.md
docs/diagrams/workstream_v01_container.md
docs/glossary.md
docs/operations_roles_permissions.md
docs/roadmap_day_by_day_execution_plan.md
docs/roadmap_status.md
docs/spec_chunk_2_auth_actor_boundary.md
docs/spec_chunk_4_task_queue_assignment.md
scripts/check_internal_review_evidence.py
scripts/test_agent_gates.py
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/CHUNK_MAP.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/STATUS.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-11-actor-identity-profile-registry.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-11-*
```

## Not allowed

```text
Workstream-owned login, signup, password reset, password storage, primary auth sessions, or API-key auth
Flow token verification provider replacement
roles or permissions sourced from ActorIdentity instead of the verified token
roles or permissions sourced from ActorProfile instead of the verified token
canonical product roles sourced from Identity Issuer token claims instead of Workstream-owned role-assignment records once that layer exists
automatic task claiming, reviewing, payment, or project access from profiles alone
worker/reviewer routing changes beyond moving profile storage to ActorProfile and preserving the canonical worker-profile API behavior
compatibility backfill or restoration of obsolete worker/reviewer profile rows
task lifecycle, submission, checker, review, revision, payment, or reputation behavior changes
agent runtime, project setup pipeline, Celery, storage, frontend, or demo feature changes
blockchain, ERC-8004, ERC-8183, settlement, marketplace, or external source adapters
```

Backend script/example edits are allowed only to remove, retire, or rewire
stale per-role profile imports and stale demo/profile calls that would break
application import or local evidence scripts after the shared actor profile
migration. Stale demo routes, demo workflow files, and obsolete script entry
points should be removed rather than kept as compatibility surfaces.

## Expected design

### ActorIdentity

Create a new `ActorIdentity` persistence model with one row per stable
Workstream actor id.

Required fields:

- `actor_id`
- `external_subject`
- `external_issuer`
- `display_name`
- `email`
- `last_seen_roles`
- `last_claim_snapshot`
- `auth_source`
- `is_dev_auth`
- `first_seen_at`
- `last_seen_at`
- `updated_at`

Rules:

- `actor_id` remains derived from external issuer and subject.
- `external_issuer + external_subject` must be unique.
- `ActorIdentity` is updated only from trusted `ActorContext`.
- `last_seen_roles` and `last_claim_snapshot` are observability snapshots, not
  permission authority.
- `display_name` and `email` may be null and may be refreshed from the latest
  verified token.
- System actors such as `workstream_system` must be representable without
  weakening Flow-user behavior.

### ActorProfile

Create a shared `ActorProfile` persistence model for role/profile metadata and
eligibility.

Required fields:

- `id`
- `actor_id`
- `profile_type`
- `status`
- `skill_tags`
- `scope_type`
- `scope_id`
- `profile_metadata`
- `created_at`
- `updated_at`

Initial `profile_type` values:

- `worker`
- `reviewer`
- `admin`
- `project_manager`
- `project_owner`

`project_owner` is a profile type and source/contact relationship. It is not a
route-authorizing role in v0.1. Workstream creates scoped
`ActorProfile(profile_type="project_owner")` rows from trusted project setup
source/contact data or trusted relationship claims when present. That profile
still cannot approve policies, manage projects, or access operator routes
without a route-authorizing token role such as `admin` or `project_manager`.

Rules:

- `actor_id + profile_type + scope_type + scope_id` is unique.
- Global profiles use `scope_type = "global"` and `scope_id = "global"`.
- Initial status values are `observed`, `active`, and `disabled`.
- `observed` means Workstream has seen the actor through a verified token role
  and keeps metadata for audit/display only. It is not workflow eligibility.
- `active` means the actor completed the explicit workflow for that profile
  type. For this chunk, only the worker self-profile API can make a worker
  profile active.
- `disabled` means the profile exists but cannot satisfy workflow eligibility.
- Worker and reviewer skill tags live on `ActorProfile`, not in duplicated
  worker/reviewer tables long term.
- `profile_metadata` is structured JSON for non-authoritative profile details;
  it must not store secrets.
- `ActorProfile.status = "active"` can be a workflow eligibility condition, but
  it cannot grant route access without a matching verified token role.
- A verified token role may create or refresh the matching profile type for
  observability and future routing with `status = "observed"`. It must not
  create unrelated profile types and must not mark profiles active by auth
  observation alone.
- Observation refresh must preserve existing `active` and `disabled` statuses.
  It may refresh metadata and last-seen details, but it must not downgrade an
  active profile to observed or revive a disabled profile.
- Any transition to `active` or `disabled` must happen through the profile
  type's explicit service workflow and must write audit evidence.
- Worker profile creation remains an explicit worker-owned API call in this
  chunk. Auth alone can refresh observed admin/project-manager profile records,
  but it must not mark a worker or reviewer eligible without the relevant
  profile workflow.
- `project_owner` is scoped source/contact metadata for the organization or
  person that supplied project material or business terms. It is not the same
  as `project_manager`, and it does not approve Workstream's machine-readable
  internal policy schema unless the verified token also carries an authorized
  Workstream role such as `admin` or `project_manager`.

### Auth Boundary

`get_current_actor` remains the pure Flow-token verification boundary. It must
not write database rows.

Add a separate actor-registration boundary, such as
`get_registered_actor`, backed by `backend/app/modules/actors/service.py` and
`backend/app/modules/actors/repository.py`, for routes that need the actor
registry side effect. That dependency resolves the trusted actor through
`get_current_actor`, then creates or refreshes `ActorIdentity` and allowed
non-eligibility observed profile rows before route services run.

The actor service may refresh non-eligibility observed profile rows for
route-authorizing roles carried by the verified token, such as `admin` and
`project_manager`. It may also create or refresh scoped non-route relationship
profiles such as `project_owner` from trusted project setup/source-contact data
or trusted relationship claims when those claims exist. Worker and reviewer
eligibility require their explicit profile workflows.

This must be fail-closed:

- missing or invalid bearer token still returns unauthorized
- failed actor identity/profile persistence returns a server error, not a
  silently unaudited request
- dev/mock auth still cannot run in production and remains visible through
  `auth_source` and `is_dev_auth`

### Route Access And Workflow Eligibility

Route authorization currently checks trusted request roles from `ActorContext`
as the v0.1 bootstrap path. The Identity Issuer is not the canonical source of
Workstream product roles; the later Workstream-owned role-assignment layer must
store and enforce that authorization state on local `ActorIdentity` records.
Profile checks are additional workflow eligibility checks, not route
permissions.

Examples:

```text
Admin route:
  require "admin" in verified token roles
  optionally record/refresh ActorProfile(profile_type="admin")

Worker profile API:
  require "worker" in verified token roles
  upsert ActorProfile(profile_type="worker", status="active", skill_tags=...)

Task claim:
  require "worker" in verified token roles
  require active ActorProfile(profile_type="worker")

Reviewer action later:
  require "reviewer" in verified token roles
  require active ActorProfile(profile_type="reviewer")
```

This preserves the security boundary and still gives Workstream one shared
profile implementation.

### Obsolete Surface Removal Boundary

The implementation path is fixed:

- create `actor_identities`
- create `actor_profiles`
- remove the separate `worker_profiles` and `reviewer_profiles` tables as
  independent profile stores
- remove old worker/reviewer profile ORM models and repository authority paths;
  after migration, task services must read and write profile state through the
  actor module
- keep the public `POST /api/v1/workers/me/profile` route, but make it read and
  write `ActorProfile(profile_type="worker")`

No new compatibility layer may treat `worker_profiles` or `reviewer_profiles`
as profile authority after this migration. Do not keep wrapper tables, shadow
tables, views, or dual-write paths in v0.1. If the implementation discovers a
hard migration blocker, stop and return for human review instead of keeping two
profile sources of truth.

This repository is still in active buildout. Obsolete experimental profile data
does not receive a compatibility backfill. The migration moves the schema to the
current contract and drops the old profile tables.

## Acceptance criteria

- [ ] Alembic creates `actor_identities` with uniqueness on `actor_id` and
      `external_issuer + external_subject`.
- [ ] Alembic creates `actor_profiles` with uniqueness on `actor_id`,
      `profile_type`, `scope_type`, and `scope_id`.
- [ ] Alembic removes the separate `worker_profiles` and `reviewer_profiles`
      tables as independent profile stores without keeping compatibility
      backfill or dual-write behavior.
- [ ] Worker/reviewer ORM models and repositories stop owning profile state;
      services use the actor module as the profile authority.
- [ ] SQLAlchemy metadata imports the new actor models so Alembic does not
      drift.
- [ ] Migration tests prove the new tables, unique constraints, metadata
      imports, and downgrade/upgrade path expected by the repo.
- [ ] Migration tests prove old profile tables are absent from the current
      schema and no legacy profile authority remains.
- [ ] API requests updated in this chunk create or refresh `ActorIdentity` from
      trusted `ActorContext` through the explicit actor-registration
      dependency. Routes outside this chunk may continue using pure
      `get_current_actor` until they are deliberately migrated.
- [ ] Registration-enabled API requests create or refresh observed
      non-eligibility profile rows for verified token roles without granting
      access from the stored row.
- [ ] `GET /api/v1/auth/me` proves actor identity/profile persistence without
      adding any Workstream-owned auth session behavior.
- [ ] Repeated requests by the same external issuer/subject never create
      duplicate actor rows. Registry writes may be skipped inside the configured
      freshness window when trusted claims and required observed profiles already
      match; stale or disabled freshness windows refresh identity last-seen
      metadata.
- [ ] Parametrized tests cover profile creation/refresh for `worker`,
      `reviewer`, `admin`, and `project_manager` from trusted token roles,
      plus scoped `project_owner` profile creation from trusted project
      source/contact data or relationship claims, including profile type,
      status, scope, and duplicate prevention.
- [ ] Tests prove token-observed admin, project-manager, worker, and reviewer
      profiles default to `observed`, scoped project-owner relationship
      profiles default to `observed`, and observed profiles do not satisfy
      worker or reviewer workflow eligibility.
- [ ] Tests prove observation refresh preserves existing `active` and
      `disabled` statuses unless an explicit audited profile workflow changes
      status.
- [ ] Worker profile creation writes the shared `ActorProfile` worker row while
      still requiring the worker role and explicit worker profile API call.
- [ ] Worker claim requires both verified `worker` token role and active
      `ActorProfile(profile_type="worker")`.
- [ ] A persisted active `worker` profile without the verified `worker` token
      role cannot claim tasks.
- [ ] Persisted active `admin` or `project_manager` profiles without matching
      verified token roles cannot access operator/project-manager routes.
- [ ] Reviewer profile storage uses the shared `ActorProfile` implementation
      when reviewer eligibility is touched, without adding new review lifecycle
      behavior in this chunk.
- [ ] Reviewer eligibility activation workflow is explicitly deferred unless a
      current API path already touches reviewer profile storage; auth
      observation alone must never create active reviewer eligibility.
- [ ] Profile status, skill-tag, scope, and eligibility changes write audit
      evidence sufficient for an operator to reconstruct why an actor was
      eligible at claim/review time.
- [ ] Non-worker actors can get an `ActorIdentity` and an observed profile for
      their token role, but cannot claim tasks or create worker profiles.
- [ ] Request bodies remain fail-closed; clients cannot spoof `actor_id`,
      `external_subject`, `external_issuer`, roles, email, or display name into
      the registry.
- [ ] Negative over-posting tests prove spoofed identity, role, email, and
      display-name fields submitted to `POST /api/v1/workers/me/profile` and
      registration-touched protected routes are rejected or ignored, and
      persisted identity/profile values remain token-derived.
- [ ] Docs clearly distinguish Flow auth, `ActorContext`, `ActorIdentity`,
      `ActorProfile`, route authorization, and workflow eligibility.
- [ ] The next Terminal Benchmark live API drill must use
      `POST /api/v1/workers/me/profile` for worker profile setup.
- [ ] Stale backend evidence helpers no longer import or write old per-role
      profile models after those stores are removed. They are rewired to
      `ActorProfile` or explicitly retired.
- [ ] `backend/scripts/api_contract_e2e.py`,
      `backend/scripts/week2_api_e2e.py`, and
      `examples/terminal_benchmark/terminal_benchmark_api_e2e.py` use
      `POST /api/v1/workers/me/profile` or are explicitly retired.
- [ ] Terminal Benchmark validation notes identify the canonical worker profile
      API and do not describe worker profile setup as an obsolete bootstrap path.
- [ ] The obsolete demo UI, local demo route, and deleted script entry points
      are not kept as compatibility surfaces.

## Verification commands

```bash
cd backend && .venv/bin/python -m ruff check app/api/deps/auth.py app/api/routes/auth.py app/modules/actors app/modules/tasks/models.py app/modules/tasks/repository.py app/modules/tasks/router.py app/modules/tasks/schemas.py app/modules/tasks/service.py tests/test_actors.py tests/test_alembic.py tests/test_auth.py tests/test_tasks.py
cd backend && .venv/bin/python -m pytest tests/test_alembic.py tests/test_actors.py tests/test_auth.py -q
cd backend && .venv/bin/python -m pytest tests/test_tasks.py -q
cd backend && .venv/bin/docstr-coverage app/api app/modules/actors app/modules/tasks --config .docstr.yaml
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Every listed reviewer must end with one exact result value:

- `PASS`
- `PASS AFTER FIXES`
- `PASS WITH LOW RISKS`
- `N/A - with approved reason`
- `FAIL`

Critical and High findings require `FAIL` until fixed. Medium findings must be
included in `PASS WITH LOW RISKS` or `FAIL` based on remediation effort and
human-decision need; they must not be omitted.

Required:

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

- `ActorIdentity` is a local registry of verified Flow actors, not Workstream
  auth.
- `ActorProfile` is shared workflow metadata and eligibility, not permission
  authority.
- Role/permission checks still use the verified token claims for the current
  request.
- Worker profile eligibility remains explicit; auth alone does not make a
  worker eligible to claim tasks.
- The implementation gives us a clean base for the next live Terminal Benchmark
  drill and later human-agent/reputation linkage.

## Stop conditions

Stop and escalate if:

- making the registry work requires Workstream-owned login/session behavior
- any route starts trusting persisted roles instead of verified token roles
- worker or reviewer eligibility becomes automatic from auth alone
- migration scope requires rewriting existing task/submission/checker records
- post-submit, review, revision, payment, reputation, blockchain, frontend, or
  agent-runtime scope becomes necessary
- tests or CI must be weakened to pass
- same blocker remains after 2 repair attempts
- secrets or production data are needed
