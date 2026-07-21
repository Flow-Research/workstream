# Chunk Contract: WS-AUTH-001-10 — Project Qualification And Contributor Role Grants

## Status

Active planning-only parent. Signed start event
`github-actions:29815937933:start` activated this exact chunk. Required L1 plan
review rejected the combined runtime scope at `5ad6e116`; the user approved the
10A/10B/10C design on 2026-07-21. This parent changes planning and contracts
only and names `WS-AUTH-001-10A` as its same-initiative successor.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Freeze the reviewed three-stage delivery design for independent project-role
authority before any AUTH-10 runtime or migration edit.

## Why this chunk exists

The inherited chunk mixed durable schema, a validator clean cut, five active
surfaces, privacy-sensitive pagination, PREP multi-principal locking, mutations,
and concurrency proof. Those boundaries require separate review and rollback.

## Risk class

L1 planning and authorization architecture.

## SLA

P1

## Approved split

1. `WS-AUTH-001-10A` — Project Role Grant Data And Evidence Foundation.
2. `WS-AUTH-001-10B` — Project Role Grant Read And Candidate Surfaces.
3. `WS-AUTH-001-10C` — Project Role Grant Mutations.

Each child requires its own signed start, internal review, merge intent, hosted
checks, human merge approval, signed merge memory, and stop. No child begins
automatically.

## Allowed files

```text
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-10.json
.agent-loop/REVIEW_LOG.md
docs/reference_specs/WS-AUTH-001-actor-profile-role-and-authorization-service-specification.md
```

## Not allowed changes

```text
backend or frontend runtime
database models or migrations
ActionId or permission availability
API routes or schemas
CI workflows or dependencies
starting AUTH-10A before this parent merges and signed memory stops
```

## Acceptance criteria

- D32 records the user-approved 10A/10B/10C design and exact dependency order.
- Every child has a complete contract with allowed files, exclusions,
  acceptance criteria, verification, reviewers, human focus, and stop rules.
- Migration `0031` belongs only to 10A; 10B and 10C add no migration.
- 10A registers all five actions as planned with exact 10B/10C owner values and
  activates no action or route; 10B owns activation of exactly three read
  actions; 10C owns activation of exactly two mutation actions.
- Project lifecycle behavior is frozen: discovery and issuance allow draft,
  active, and paused projects; list/detail and revocation remain available for
  every existing project state so evidence is inspectable and authority can
  always be removed.
- `/api/v1/actors/me/authorization-context` is explicitly deferred to AUTH-11,
  where the first complete project read cutover can expose useful contributor
  context without advertising inactive task/review actions.
- The canonical reference specification removes `both`, replacement, automated
  issuance, one-active-role-total, and noncanonical AUTH-10 route prefixes.
- Exactly one merge intent names 10A as successor with explicit start required.

## Verification commands

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
git diff --check
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Confirm the three boundaries, exact successor order, migration custody,
authorization-context deferral, and absence of runtime changes.

## Stop conditions

Stop if the planning PR changes runtime, combines child boundaries again,
starts a child automatically, or names a cross-initiative successor.
