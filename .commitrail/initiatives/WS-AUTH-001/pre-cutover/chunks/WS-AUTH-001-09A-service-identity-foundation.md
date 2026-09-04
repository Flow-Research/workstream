# Chunk Contract: WS-AUTH-001-09A - Fixed Service Identity Foundation

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Register the eight planned AUTH-09 route ActionIds, make a service
`ActorProfile` carry one fixed Workstream service identity, and define the
closed seven-service/eleven-action matrix without provisioning an actor or
activating an authorization path.

## Why this chunk exists

A service ActorProfile is Workstream's equivalent of a Kubernetes
ServiceAccount: a stable local principal. Its exact external Identity Issuer
`(issuer, subject)` is only the credential link proving which token represents
that principal. Service permissions come from one closed typed matrix, not from
token claims, human grants, database-authored action rows, or display data.

## Risk routing

- Risk class: L1
- SLA: P1
- Work type: authorization architecture, actor schema, migration, audit parity
- Human gate: explicit PR review and merge approval
- Required reviewers: senior engineering, QA/test, security/auth, product/ops,
  architecture, CI integrity, docs, reuse/dedup, test delta

## Allowed files

```text
backend/app/modules/actors/models.py
backend/app/modules/actors/service_identities.py
backend/app/modules/actors/service_identity_migration.py
backend/app/modules/authorization/catalogue.py
backend/migration_contracts/__init__.py
backend/migration_contracts/service_identity_0023.py
backend/alembic/versions/0023_service_actor_identity.py
backend/pyproject.toml
backend/scripts/service_actor_identity_mapping.py
backend/tests/test_actors.py
backend/tests/test_actor_migration_tools.py
backend/tests/test_actor_legacy_classification.py
backend/tests/test_auth.py
backend/tests/test_authorization.py
backend/tests/test_audit.py
backend/tests/test_alembic.py
backend/tests/test_api_controls.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-09A.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
scripts/test_agent_gates.py
```

## Not allowed

```text
public routes or command handlers
active AUTH-09 actions or allowed decisions for them
service actor/profile/link creation or migration seeding
service registration or service-action-assignment tables
runtime service-token admission
client-authored ActionIds, PermissionIds, assignments, or policy
AdminRoleGrant, ProjectRoleGrant, or Contributor authority for services
artifact resource composers, guards, adapters, or call-site activation
actor/link state mutation or lifecycle reconciliation consumption
compatibility aliases, fallback constructors, dual authority paths, or token-role authority
obsolete role-shaped profile, grant, or API behavior for human contributors
```

## Exact planned route actions

| ActionId | PermissionId | Owner | Availability |
|---|---|---|---|
| `actor.profile.read` | `actor.profile.read_any` | `WS-AUTH-001-09C` | `planned` |
| `actor.profile.suspend` | `actor.profile.suspend` | `WS-AUTH-001-09D` | `planned` |
| `actor.profile.reactivate` | `actor.profile.reactivate` | `WS-AUTH-001-09D` | `planned` |
| `actor.profile.deactivate` | `actor.profile.deactivate` | `WS-AUTH-001-09D` | `planned` |
| `actor.identity_link.read` | `actor.identity_link.read` | `WS-AUTH-001-09C` | `planned` |
| `actor.identity_link.revoke` | `actor.identity_link.revoke` | `WS-AUTH-001-09D` | `planned` |
| `actor.identity_link.reactivate` | `actor.identity_link.reactivate` | `WS-AUTH-001-09D` | `planned` |
| `actor.service.provision` | `actor.service.provision` | `WS-AUTH-001-09B` | `planned` |

The catalogue therefore contains exactly 65 actions after this chunk: nine
active and 56 planned. This chunk does not change the active count.

The trusted entry state from PR #140 is 74 PermissionIds and 57 ActionIds: nine
active and 48 planned. AUTH-09A adds zero permissions, eight planned actions,
seven fixed service identities, and eleven static matrix memberships. The 25
ART and 19 REV actions retain their historical feature-owner enum values in this
pre-custody state; only the later availability-neutral ART/REV custody chunks
may replace those values with exact AUTH activation owners.

## Fixed service ActorProfile contract

- `ActorProfile.service_identity` is null for every human and required for
  every service.
- The value is one of the seven fixed identities below and is unique. It is
  immutable with actor kind, provisioning method, ID, creator, and creation
  time.
- ActorProfile ID and `service_identity` are separate stable local fields, like
  a Kubernetes object's UID and name. AUTH-09B creates a new service profile
  with a server-generated UUID; it never derives that ID from issuer or subject.
  Existing explicitly mapped service profiles preserve their IDs and history.
- It is not a display name, email, token subject, adapter provenance string,
  PermissionId, role, or grant.
- `ActorIdentityLink` remains the single v0.1 credential binding. Its issuer and
  opaque subject are never inferred from `service_identity`, email, or display
  data.
- Existing service profiles are assigned a fixed identity only through the
  strict operator mapping below. They are never guessed from ID, issuer,
  subject, email, display data, token role, or adapter provenance.

## Existing-service migration input

Migration `0020` could create explicitly classified service profiles before the
fixed identity field existed. When any such row exists, `0023` requires a
versioned private mapping file named by
`WORKSTREAM_SERVICE_ACTOR_IDENTITY_MAPPING_FILE`.

Each entry contains exactly `actor_profile_id`, `issuer`, opaque `subject`, and
one fixed `service_identity`. The complete entry set must equal the locked
database projection of all existing service profiles and their single links.
The loader enforces a regular non-symlink file, bounded size/count, restrictive
permissions, strict schema, canonical JSON, database binding, checksum, exact
byte-preserving issuer/subject comparison, unique profile/link/identity values,
and membership of every mapped value in the seven-identity closed set. The
mapping covers exactly the existing service rows, which may be zero, any valid
subset, or all seven; it does not pre-provision absent identities. Errors and
logs expose stable codes and counts only, never IDs, issuers, or subjects.

Draft and envelope bytes use strict key-sorted compact JSON followed by exactly
one newline. Paths must be absolute and outside the main checkout, every linked
worktree, and shared Git metadata; the CLI and Alembic consumer use the same
custody guard.

The supported operator tool reads the exact target database, validates the
operator-authored choices, and writes the confidential bound envelope. It does
not infer a service identity or modify the database. Missing, extra, stale,
duplicate, or ambiguous mappings stop migration atomically. A database with no
service profiles requires no file. Mapping count and non-secret manifest,
source-row-set, envelope, and database-binding digests are retained as migration
evidence; raw mapping content is not persisted.

## Exact static service-action matrix

| Service identity | Exact ActionIds |
|---|---|
| `workstream.artifact.verifier` | `artifact.verification.execute` |
| `workstream.artifact.put_resolver` | `artifact.put_attempt.resolve` |
| `workstream.artifact.scheduler` | `artifact.pending_work.scan`, `artifact.upload_session.expire` |
| `workstream.artifact.binding` | `artifact.guide_source.binding.create`, `artifact.submission.binding.create`, `artifact.checker_output.binding.create` |
| `workstream.artifact.guide_reader` | `artifact.guide_source.read` |
| `workstream.artifact.materializer` | `artifact.pre_submit.checker_input.materialize`, `artifact.post_submit.checker_input.materialize` |
| `workstream.artifact.checker_output` | `artifact.checker_output.write` |

The matrix is frozen typed code. It stores no database assignment rows and
computes no permission union. Changing an identity or row requires a reviewed
specification and code change. Every listed artifact action remains planned and
therefore non-executable until its resource-owning WS-ART behavior and manifest
have merged and its dedicated AUTH activation custodian integrates the evaluator
and changes availability.

## Clean-cut rule

This foundation adds only the canonical fixed-service model. It must not add or
preserve a compatibility alias, fallback service constructor, dynamic service
grant, database assignment path, token-role path, or second identity model.
Existing unrelated legacy human intake code is not expanded by this chunk and
remains deletion-only in its already assigned resource-family cutovers.

## Acceptance criteria

- Typed construction fails on any missing/extra fixed service identity, matrix
  ActionId, route ActionId, PermissionId mapping, owner, availability, duplicate
  row, or artifact action outside the approved eleven.
- Migration `0023` advances from exact head `0022`, locks the complete actor/link
  source projection, consumes the exact private mapping when service rows
  exist, adds `actor_profiles.service_identity`, preserves mapped profile IDs,
  and enforces human/null and service/fixed-identity parity plus uniqueness.
- The migration extends PostgreSQL action/evidence parity to exactly the eight
  route action mappings above without changing historical evidence.
- All eight route actions remain planned. Typed allowed evidence for them is
  rejected; registered denial evidence keeps exact ActionId/PermissionId parity.
- All artifact actions remain planned and inert. No executable service
  authority can be created by configuration, database insertion, token claim,
  role, grant, or request input.
- Direct SQL proves ActorProfile service-identity nullability, fixed-value,
  uniqueness, immutability, actor-kind/provisioning parity, and mapping-bound
  upgrade behavior. Tool tests prove secure-file, checksum, database-binding,
  exact-set, redaction, and no-inference behavior for zero, one/subset, and all
  seven existing service rows.
- Migration-owned state persists only bounded counts and non-secret source,
  manifest, envelope, and database-binding digests. It never persists raw
  mapping content, actor IDs, issuer, subject, file path, or environment value.
  Exact format constraints and update/delete/truncate guards keep that retained
  singleton evidence immutable.
- No ActorProfile, ActorIdentityLink, idempotency row, or audit event is seeded
  by migration or application startup.
- Upgrade refusal is exact and redacted: any pre-`0023` service row without a
  complete valid mapping stops the transaction with a stable code and no row
  details. Downgrade locks actor/audit state and refuses when any non-null
  `service_identity` or audit evidence carrying one of the exact eight new
  ActionIds would be lost. Otherwise it restores exact `0022` checks/triggers;
  empty and human-only prior-head upgrade, clean downgrade, and re-upgrade pass.
- OpenAPI paths and action declarations are byte-for-byte unchanged, and the
  existing nine active actions retain identical allow/deny behavior.
- The operations runbook defines draft review, bound-envelope generation,
  database verification, owner-only file custody, short-lived environment use,
  stable redacted failure handling, post-migration deletion/retention evidence,
  and the stop path when an existing service cannot truthfully map.
- No workflow, dependency, test skip, coverage exclusion, or global threshold
  changes. Focused branch-aware actor and authorization coverage remains at
  least 90 percent; GitHub Backend preserves the repository-wide 78 percent
  floor.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app migration_contracts tests scripts/service_actor_identity_mapping.py alembic/versions/0023_service_actor_identity.py)
(cd backend && .venv/bin/coverage erase && \
  WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> \
  .venv/bin/python scripts/run_isolated_tests.py --timeout-seconds 1800 -- \
  .venv/bin/python -m pytest -q tests/test_actors.py \
  tests/test_actor_migration_tools.py tests/test_actor_legacy_classification.py \
  tests/test_auth.py tests/test_authorization.py \
  tests/test_audit.py tests/test_alembic.py tests/test_api_controls.py \
  --cov=app.modules.actors \
  --cov=app.modules.authorization --cov-branch --cov-report= \
  --cov-fail-under=0 && \
  .venv/bin/coverage report --include='app/modules/actors/*' --fail-under=90 && \
  .venv/bin/coverage report --include='app/modules/authorization/*' --fail-under=90)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

Local deterministic evidence is the two independent branch-aware 90 percent
package reports above. GitHub Backend remains authoritative for the full suite
and repository-wide 78 percent floor; 09A has no API behavior or API drill.

## Human review focus

Review the ServiceAccount-style principal model, preservation of mapped legacy
profile IDs, confidential exact-set mapping, separation of local identity from
external subject, exact seven/eleven matrix parity, lack of database assignment
rows, planned-action inertness, and guarded downgrade custody.

## Stop conditions

Stop if the foundation requires a public route, live service token, seeded
principal, dynamic assignment, service grant, active artifact action, or feature
resource facts.

Stop after merge and signed memory. Do not start AUTH-09B automatically.
