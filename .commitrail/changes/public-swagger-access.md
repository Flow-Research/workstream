# Public Swagger access and issuer-owned profile metadata

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Expose the existing Swagger UI/schema and make profile email issuer-owned across REST, CLI and MCP.

## Intent

The public proxy currently hides FastAPI's `/docs` and `/openapi.json`, making API exploration unavailable despite a working deployment. Extend its existing API path allowlist with those two exact paths. Keep the backend's method handling, token verification and authorization unchanged; documentation supplies no product authority.

## Bounded change

Allowed files: `backend/app/main.py`, `backend/tests/test_app.py`, `deploy/hosted/public.Caddyfile`, `scripts/test_public_ingress.py`, `deploy/hosted/PUBLIC_ACCESS.md`, `experiments/demo_identity/README.md`, `deploy/hosted/SINGLE_HOST.md`,
`docs/operations_authorization_service.md`, affected README/roadmap wording and this record.
Prohibited: new application endpoints, auth bypass, wildcard documentation exposure, unrelated deployment changes or additional worktrees.

## Acceptance criteria

1. Add the exact documentation paths to the existing backend proxy.
2. Extend the real Caddy socket regression: both paths reach the API upstream; adjacent/unrelated paths and foreign hosts remain denied before upstream access.
3. Update operator guidance and the affected capability statement.
4. Review, validate and install the configuration on the existing host; verify trusted HTTPS Swagger/schema, backend health and unauthorized API denial.

## Risk and review routing

Risk: L1 for identity metadata synchronization; Swagger itself is bounded L2 public metadata exposure. Focused security/architecture and QA/docs review cover exact routing and unchanged authority. Human review focus: publicly readable schema is intentional, credentials are still required for protected API operations. Existing ingress proof and relevant documentation checks remain required. No claim that public Swagger implements login or grants project access.

## Evidence

Plan review found the exact shared proxy matcher sufficient. Real Caddy socket proof passes; removing the documentation paths or broadening `/docs` to a wildcard makes the corresponding regression fail at its intended assertion. Live deployment proof is recorded separately from these fixtures.

User-requested documentation extension: make the existing Rust issuer README a complete four-endpoint operator reference, including separate administrator bootstrap, request/response/token contracts, participant onboarding and unsupported recovery. Cross-link the existing Workstream bootstrap owner; introduce no new identity API or behavior. Validate the descriptions against the Rust routes and schemas and review the final docs delta.

## Issuer-owned profile correction

User extends this same PR: email is issuer-owned metadata, never a Workstream edit;
display name is seeded from an optional signed name on first admission and thereafter
owned by the participant. Email updates occur during authorized self-profile reads
and updates using verified issuer/subject, never by matching email. Rust access tokens
include the stored account email; this does not assert mailbox verification.

Allowed additional files: ACTORS model/repository/service/schema, verified-token and
Flow verifier contracts, self-profile routes, AUTH requested-field contract, one linear
Alembic migration and schema fingerprint, affected backend tests/drill callers, test-lane registration and structural-debt
fingerprints (unchanged limits),
`cli/`, `mcp_server/`, `experiments/demo_identity/`, and current profile documentation.
No new identity APIs, authorization grants, alternate authentication, email matching,
worktrees or unrelated cleanup. Risk L1 (identity metadata); security/architecture and
QA/test-delta review required.

Plan: retain first-admission display-name seeding only (no override flag needed);
record an email observation `iat` on the exact identity link. Absent/null optional
claims are not observations. Only strictly later tokens replace email; equal-second
observations retain the first value until a later token. Existing contact values are
retained until a signed email replaces them; they are not mailbox-verification proof.
Use existing profile-before-link locks and caller-owned authorized transactions.
Remove email mutation from API, AUTH facts, CLI and MCP together.

Proof: signed first admission and changed email, stale-token non-regression, two
subjects sharing email remaining distinct, explicit display-name edits/null surviving
reads, denied mutations with no effect, rollback and concurrent profile operations.
Test issuer access claims, client rejection and migration from current predecessor.
Update current docs and roadmap; run focused reviews and final-head CI.

Plan review: PASS with low risks; use the bounded self-profile routes rather than
adding metadata side effects to every authorization touch. No global synchronization
middleware is introduced.

The signed self-profile proof moves from the oversized `test_auth.py` into the
focused actor profile module alongside new regressions. Existing authorization
and audit privacy assertions are retained; the email source changes from PATCH
to the signed token. The structural ledger shrinks, and the new module is added
to the existing identity test lane. The drill's stale fixed permission count is
reconciled to all 94 current permissions (including four setup-model operations),
with response total and uniqueness assertions; no gate is relaxed.

Review repair: reject signed issued-at values outside the supported nonnegative
64-bit range and malformed UTF-8 profile claims before persistence. The migration
preservation comparison includes the new nullable observation field as null before
its introduction, retaining every existing field, table identity and row version;
non-null post-upgrade observations cannot be hidden by the comparison.

External-review repair: the public Swagger page pins Swagger UI 5.32.0 JavaScript
and CSS with SHA-384 subresource integrity and anonymous CORS. Changed CDN bytes
are rejected by the browser; bearer authorization is not persisted. The app test
locks the rendered asset URLs, digests and crossorigin attributes. Historical
migration fixtures temporarily project the new nullable identity field for current
ORM readers, then remove it before upgrading; retained-effect assertions remain.

The authorization regressions now request editable display-name updates rather
than the removed email mutation; transaction revalidation, handle mismatch and
unconsumed-handle assertions are unchanged. The read/update contexts share one base identity with an empty requested-field
copy for reads, removing duplicated setup. Structural debt shrinks without
changing limits or dispositions.

Historical archive restoration remains exact: the shared nullable owner projection
is added only after archived column validation, checked for null-only values, and
removed before migration. The archive inventory check is not relaxed.

The final external-review documentation pass adds purpose/failure-boundary
docstrings to affected functions. AST comparison with function docstrings removed
proves executable Python structure is unchanged; structural evidence is refreshed
without changing limits. This does not add a percentage gate.
