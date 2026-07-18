# WS-AUTH-001-08 PR Trust Bundle

## Chunk

`WS-AUTH-001-08` - Bootstrap And Administrative Role Grants

## Goal

Establish the first local administrative authority: a one-time Access
Administrator bootstrap, immutable administrative grants, and grant-backed
central authorization for the exact administrative surface owned by this
chunk.

## What Changed

- Added migration `0022` for immutable `AdminRoleGrant` truth, lifecycle
  constraints, bootstrap uniqueness, and administrative extensions to the
  existing idempotency, evidence, and linked-invalidation foundations.
- Added one-time local bootstrap tooling that targets an explicitly verified,
  eligible canonical human ActorProfile with an active external identity link;
  the command accepts only its ActorProfile UUID and never accepts issuer or
  subject data.
- Added five closed administrative role definitions and seven active
  administrative actions with exact system or project scope rules.
- Added authenticated definition, grant-list, grant-issue, and grant-revoke
  APIs through the request-scoped central authorization kernel.
- Added final Access Administrator protection, transactional revalidation,
  privacy-bounded concealment, exact replay/mismatch behavior, and immutable
  allow/deny/success/invalidation evidence.
- Added deferred commit-time coupling between the unique bootstrap grant and
  `authority_control`, preventing orphan grants or mismatched completed control.
- Repaired AUTH-07B transaction ownership, evidence-failure mapping, and
  existing-actor verification timestamp behavior before adding new consumers.

## Design Boundaries

Identity remains global and external-issuer verified. Administrative authority
comes only from active local grants; token roles, email, and default Contributor
profile state grant no administrative permission. Project scope is an exact
grant constraint, not a duplicated permission definition. AUTH-08 adds no
project contributor grants, service actors, artifact behavior, review/revision
runtime, or Workstream-owned authentication.

## Tests And Coverage

- 275 focused behavior tests passed against isolated PostgreSQL.
- Focused branch-aware coverage: 90.17 percent.
- Administrative mutation service coverage: 100 percent.
- Signed-token lifecycle, idempotency replay/mismatch, concurrency, final-admin
  safety, audit linkage, and zero-write substitution behavior passed.
- All 17 isolated Alembic tests passed after repairing the retained-head
  rollback assertion and adding bootstrap/control and evidence-adoption proof.
- Repository docstring coverage is 92.5 percent under the enforced
  `docstr-coverage` configuration.
- Ruff, stale wording, authorization-doc consistency, Markdown links,
  loop-memory validation, 71 agent-gate tests, and diff integrity passed.

GitHub Backend remains authoritative for the repository-wide 78 percent floor;
this PR does not change any coverage threshold or exclusion.

## Reviewer Results

Exact implementation SHA `34f87a5aa7d75897349f64f5e904cb1847af019b`
passed senior engineering, QA/test, security/auth, product/ops, architecture,
CI integrity, docs, reuse/dedup, and test-delta review after all valid findings
were repaired. No reviewer sessions or actionable findings remain open.

## Remaining Risks

- The first bootstrap is an operational trust ceremony and must target an
  explicitly verified, eligible canonical human ActorProfile with an active
  external identity link in a controlled environment.
- Project-scoped administrative grants authorize only the seven actions
  activated here; project contributor grants and product cutovers remain
  unavailable until their owning chunks.
- Production issuer and database availability remain operational dependencies;
  evidence-write database failures deliberately return retryable 503 responses.

## Human Review Focus

Review bootstrap uniqueness, the five-role matrix, exact scope matching,
grant-backed decision provenance, final-administrator safety, revoke
idempotency semantics, transaction ownership, and the no-authority treatment of
token roles and email.

## Human Merge Ownership

Only the human may approve and merge this PR. GitHub checks, CodeRabbit, and
internal review do not authorize merge.
