# Chunk Contract: WS-AUTH-001-10A - Project Role Grant Data And Evidence Foundation

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Status and prerequisite

Proposed and inactive. Start only after planning parent AUTH-10 merges, signed
memory names 10A, and a fresh explicit start event activates this exact child.

## Goal

Create the immutable qualification-snapshot and independent three-role grant
truth plus typed/PostgreSQL evidence parity, without exposing a route or active
action.

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
backend/app/modules/audit/**
backend/app/db/models.py
backend/alembic/versions/0031_project_role_grants.py
backend/tests/test_authorization.py
backend/tests/test_alembic.py
docs/operations_authorization_service.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-10A.json
.agent-loop/REVIEW_LOG.md
```

## Not allowed changes

```text
API routes or OpenAPI declarations
new or active ActionId/ActionOwner rows
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
database timestamps, and terminal revocation provenance. Only active version 1
to revoked version 2 may mutate lifecycle fields.

## Acceptance criteria

- Migration `0031` creates both authorization-owned tables and no route/action.
- Composite key `(snapshot_id, actor_profile_id, project_id, requested_role)`
  is referenced by the matching grant facts.
- Partial uniqueness permits one active actor/project/exact-role row while all
  three distinct roles may coexist.
- Regrant after revocation creates a new row; issuance provenance is immutable.
- Typed and PostgreSQL audit/idempotency validators accept only the three exact
  roles and issued/revoked success events. Replacement fields/events/reasons
  and `both` are absent.
- Migration `0031` reserves availability-neutral typed and PostgreSQL evidence
  parity for exactly these future action/permission pairs, without adding an
  `ActionDefinition`, `ActionOwner`, route, or callable behavior:

  ```text
  project.contributor_candidate.list -> project.role_grant.manage
  project_role_grant.list            -> project.role_grant.read
  project_role_grant.read            -> project.role_grant.read
  project_role_grant.issue           -> project.role_grant.manage
  project_role_grant.revoke          -> project.role_grant.manage
  ```

  It likewise reserves exactly the future denial codes
  `project_role_grant_already_revoked` and
  `project_role_grant_replay_state_changed` in the typed and PostgreSQL denial
  vocabularies. Reservation does not make an action active; 10B and 10C own
  their respective action definitions, owners, routes, and emissions.
- Migration and schema tests prove all five pairs and both denial codes are
  admitted, a neighboring unreserved value is rejected, and the action
  registry/owner manifest remains unchanged by 10A.
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
  authority audit row has `before_facts->>'role'='adjudicator'` or
  `after_facts->>'role'='adjudicator'`. Each individual predicate and their
  combined form have transaction-level no-mutation proof.
- Fresh install, prior-head upgrade, downgrade/refusal, replay, constraints,
  immutability, and preserved unrelated history are proven on PostgreSQL.
- No migration, model, schema, or fixture accepts automated creation.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/authorization app/modules/audit tests/test_authorization.py tests/test_alembic.py)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-db> .venv/bin/python scripts/run_isolated_tests.py --metadata-json <path> --timeout-seconds 300 -- .venv/bin/python -m pytest -q tests/test_alembic.py tests/test_authorization.py -k 'project_role or qualification')
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
