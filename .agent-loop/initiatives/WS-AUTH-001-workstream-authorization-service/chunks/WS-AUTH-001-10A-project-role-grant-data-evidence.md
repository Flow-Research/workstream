# Chunk Contract: WS-AUTH-001-10A - Project Role Grant Data And Evidence Foundation

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Status and prerequisite

Active. Planning parent AUTH-10 merged through PR #168 as
`70f9c7bcdb63680e545f661a956929379df138e4`; signed memory named 10A, and
explicit start workflow run `29828847015` activated this exact child on
2026-07-21.

## Goal

Create the immutable qualification-snapshot and independent three-role grant
truth plus typed/PostgreSQL evidence parity and planned action registrations,
without exposing a route or active action.

## Why this chunk exists

Reads and mutations must depend on database-enforced ownership and exact-role
history rather than shipping schema and behavior together.

## Risk class

L1 schema, authorization evidence, and privacy.

## SLA

P1

## Allowed files

```text
backend/app/modules/authorization/models.py
backend/app/modules/authorization/schemas.py
backend/app/modules/authorization/repository.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/service.py
backend/app/modules/audit/**
backend/app/db/models.py
backend/alembic/versions/0031_project_role_grants.py
backend/tests/test_authorization.py
backend/tests/test_alembic.py
backend/tests/test_audit.py
docs/operations_authorization_service.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-10A.json
.agent-loop/REVIEW_LOG.md
```

## Not allowed changes

```text
API routes or OpenAPI declarations
active ActionDefinition rows or callable action behavior
authorization kernel or PREP behavior
candidate/list/detail/issue/revoke services
project/task/review lifecycle behavior
`both`, replacement, automated issuance, aliases, or evidence conversion
editing a historical migration
```

## Exact durable contract

`ProjectRoleQualificationSnapshot` contains `id`, `project_id`,
`actor_profile_id`, exact `requested_role`, two structured availability
snapshots, bounded prior-work UUID references, bounded external-expertise
reference tokens, capturer profile/grant provenance, and database capture time.

Each availability snapshot is exactly:

```text
availability: available | unavailable
reference_ids: array[string], 0..20 items, each matching
               ^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$ and containing no `://`
unavailable_reason: not_collected | source_unavailable | no_record | null
```

`available` requires one or more reference IDs and null reason. `unavailable`
requires no references and one reason. Prior-work references are 0..20 UUIDs.
External-expertise references are 0..20 tokens with the same grammar. Issue and
revoke reasons are 1..500 UTF-8 bytes, must equal Python `str.strip()`, and
reject Unicode control characters. No free-form evidence narrative, score, contact field, issuer subject, raw claim,
secret, URL credential, or automatically inferred authority is stored.

`ProjectRoleGrant` is one immutable issuance row for exactly `submitter`,
`reviewer`, or `adjudicator`, with active/revoked lifecycle, manual method,
composite snapshot reference, issuer profile/grant provenance, bounded reason,
database timestamps, terminal revocation provenance, and a persisted integer
`version`. The invariant is exact: active grants persist version 1 and revoked
grants persist version 2. Only the active-version-1 to revoked-version-2
transition may mutate lifecycle fields.

## Acceptance criteria

- Migration `0031` creates both authorization-owned tables; 10A adds no route,
  active action, or callable behavior.
- Composite key `(snapshot_id, actor_profile_id, project_id, requested_role)`
  is referenced by the matching grant facts.
- Partial uniqueness permits one active actor/project/exact-role row while all
  three distinct roles may coexist.
- Regrant after revocation creates a new row; issuance provenance is immutable.
- Typed and PostgreSQL audit validators retain exactly
  `ProjectRoleQualificationSnapshotCaptured`, `ProjectRoleGrantIssued`, and
  `ProjectRoleGrantRevoked` for project-role success, plus the existing generic
  linked `AuthorityInvalidationRequested` event. Snapshot capture has a null
  `idempotency_reference` and is transaction-correlated to issuance by the same
  actor, target actor, project, request ID, and correlation ID; the grant-issued
  event carries the pending issue idempotency reference. Grant revocation and
  its linked invalidation carry the pending revoke idempotency reference.
  Typed/PostgreSQL validators accept only the three exact roles.
  `ProjectRoleGrantReplaced`, `authority_replacement`, replacement fields, and
  `both` are absent. Audit tests convert former replacement positives into
  negative rejection cases while preserving complete event-enum coverage.
- The existing dormant `AuthorityMutationService` is changed only to remove
  replacement-event selection and `replaced_grant_id` matching: a project-role
  issue can validate only `ProjectRoleGrantIssued`, with no matched prior grant.
  This is availability-neutral evidence cleanup, not an issue/revoke product
  service or callable behavior; no route invokes it until 10C.
- 10A adds the five `ActionId` enum members and closed `ActionDefinition` rows
  below with `ActionAvailability.PLANNED`; it adds exact `ActionOwner.AUTH_10B`
  and `ActionOwner.AUTH_10C` enum values and assigns each row to its named
  future owner. Migration `0031` reserves matching PostgreSQL evidence parity.
  No route or callable behavior is added:

  ```text
  project.contributor_candidate.list -> project.role_grant.manage -> AUTH_10B
  project_role_grant.list            -> project.role_grant.read   -> AUTH_10B
  project_role_grant.read            -> project.role_grant.read   -> AUTH_10B
  project_role_grant.issue           -> project.role_grant.manage -> AUTH_10C
  project_role_grant.revoke          -> project.role_grant.manage -> AUTH_10C
  ```

  It likewise reserves exactly the future denial codes
  `project_role_grant_already_revoked` and
  `project_role_grant_replay_state_changed` in the typed and PostgreSQL denial
  vocabularies. Planned registration does not make an action active; 10B and
  10C own the transition to active availability, routes, and emissions for
  their respective rows.
- Migration and schema tests prove all five pairs and both denial codes are
  admitted, a neighboring unreserved value is rejected, every new catalogue row
  is planned with its exact owner, and no route/OpenAPI surface exists in 10A.
- Upgrade inspects exact existing storage and refuses before DDL when any
  `audit_events` row with `event_domain='authority'` has
  `before_facts->>'role'='both'`, `after_facts->>'role'='both'`, a
  `replaced_grant_id` key in either facts object,
  `event_type='ProjectRoleGrantReplaced'`, or
  `reason='authority_replacement'`. It also refuses any
  `authority_idempotency_records.operation` in
  `('project_role_grant.issue','project_role_grant.revoke')`, because those
  records contain only a digest/resource reference and cannot prove an
  independent-role request safely. No other replacement/supersession key or
  fuzzy reason search is implied.
- Downgrade refuses before DDL when either new table contains any row or an
  `audit_events` row with `event_domain='authority'` has
  `before_facts->>'role'='adjudicator'`,
  `after_facts->>'role'='adjudicator'`, `action_id` equal to any of the five
  10A-registered action IDs, or `denial_code` equal to
  `project_role_grant_already_revoked` or
  `project_role_grant_replay_state_changed`. Each individual predicate and
  their combined form have transaction-level no-mutation proof before any table
  or validator DDL is changed.
- PostgreSQL checks/triggers, not only Pydantic, enforce availability-object
  grammar and cardinality, available/unavailable cross-field rules, reference
  bounds, Python-strip-equivalent reason byte bounds and control exclusion,
  composite snapshot ownership, status/version coupling, snapshot and issuance
  immutability, and the sole active-v1 to revoked-v2 lifecycle transition.
- Fresh install, prior-head upgrade, downgrade/refusal, replay, constraints,
  immutability, and preserved unrelated history are proven on PostgreSQL.
- No migration, model, schema, or fixture accepts automated creation.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/authorization app/modules/audit tests/test_authorization.py tests/test_alembic.py tests/test_audit.py)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-db> .venv/bin/python scripts/run_isolated_tests.py --metadata-json <path> --timeout-seconds 300 -- .venv/bin/python -m pytest -q tests/test_alembic.py tests/test_authorization.py -k 'project_role or qualification')
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-db> .venv/bin/python scripts/run_isolated_tests.py --metadata-json <path> --timeout-seconds 300 -- .venv/bin/python -m pytest -q tests/test_audit.py)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

The full suite, all shards, aggregate 78 percent coverage, authorization 90
percent coverage, API E2E, and Agent Gates run only on GitHub before PR
readiness.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Review privacy shapes, composite ownership, independent-role uniqueness,
immutability, refusal predicates, and absence of exposed behavior.

## Stop conditions

Stop if migration data would be converted/deleted, evidence becomes free-form,
an action/route becomes active, or one role affects another.
