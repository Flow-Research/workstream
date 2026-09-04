# WS-AUTH-001-07B PR Trust Bundle

## Chunk

`WS-AUTH-001-07B` - Deny-By-Default Kernel And Self-Action Cutover

## Goal

Install the request-scoped central authorization kernel and cut only actor
self-read and self-update over to it, with immediate lifecycle revalidation and
privacy-bounded decision evidence.

## What Changed

- Added strict frozen authorization context, resource, decision, denial, and
  matched-authority contracts.
- Added request-scoped `AuthorizationService.require(action_id,
  resource_context)` with deny-by-default action dispatch and no transaction
  ownership.
- Activated only `actor.profile.read_self` and
  `actor.profile.update_self`; all other catalogue actions remain planned.
- Cut `GET /api/v1/actors/me` and `PATCH /api/v1/actors/me` over to the kernel
  with exact OpenAPI action declarations.
- Made PATCH lock and revalidate the identity link before actor profile state,
  so revocation or lifecycle changes win before mutation commit.
- Added privacy-bounded allow/deny evidence, exact denial rollback/restaging,
  signed-token API proof, deterministic race proof, and closed OpenAPI/E2E
  assertions.

## Design Boundaries

Token roles grant no authority. This chunk adds no admin grants, project grants,
project capability context, cross-request cache, feature repositories, second
unit of work, permission-definition API, or migration. AUTH-08 remains the
owner of bootstrap and administrative grants.

## Tests And Coverage

- 210 focused behavior tests passed against isolated PostgreSQL.
- Focused branch-aware coverage: 94.65 percent.
- Authorization kernel and runtime: 100 percent each.
- Real API contract E2E passed, including signed actor self GET/PATCH.
- Repair regression sample: 10 tests passed.
- Agent Gates previously passed 71 tests for this branch scope.
- Ruff, stale wording, authorization-doc consistency, Markdown links, and diff
  integrity passed.

GitHub Backend remains authoritative for the repository-wide 78 percent floor;
this PR does not change any coverage threshold or exclusion.

## Reviewer Results

Exact implementation SHA `aabc0f4c0131c53600750258a0bec8be404c7b90`
passed senior engineering, QA/test, security/auth, product/ops, architecture,
CI integrity, docs, reuse/dedup, and test-delta review with no remaining
findings.

## Remaining Risks

- Actor self-update depends on PostgreSQL row-lock ordering; non-database state
  changes are outside this chunk.
- Unknown actions cannot produce exact action evidence because no registered
  ActionId exists; their public response remains `permission_not_granted`.
- Admin and project authority remain unavailable until their owning chunks
  implement grant truth and resource composition.

## Human Review Focus

Review denial precedence, exact active-action closure, token-role non-authority,
self-resource targeting, suspended read/update separation, row-lock ordering,
transaction ownership, and bounded decision evidence.

## Human Merge Ownership

Only the human may approve and merge this PR. GitHub checks, CodeRabbit, and
internal review do not authorize merge.
