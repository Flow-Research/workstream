# PR Trust Bundle: WS-AUTH-001-02

## Chunk

`WS-AUTH-001-02` - Verified Issuer Token And JWKS Boundary

## Goal

Authenticate externally issued Flow tokens through a pinned, bounded,
fail-closed JWT/JWKS/introspection boundary without granting Workstream product
authority from issuer role claims.

## Human-Approved Intent

The user explicitly started AUTH-02, approved D12's exact production
dependencies, and later explicitly resumed this work in its separate worktree.
This AUTH branch activates only AUTH-02; it does not activate later AUTH,
policy, coverage, review, or contribution chunks. Separately authorized
coverage work remains independently owned in its own worktree.

## What Changed And Why

- Replaced the production verifier placeholder with asymmetric JWT verification.
- Added bounded JWKS refresh/cache/rotation and required-mode introspection.
- Introduced minimal canonical verified-token and typed failure contracts.
- Preserved only bounded human legacy roles for enumerated unmigrated routes.
- Added app-bound verifier ownership and safe structured metrics.
- Updated configuration, API drill, tests, canonical spec, and auth runbook.

This establishes trustworthy authentication before Workstream-owned actor,
grant, permission, and resource-guard chunks begin.

## Design Chosen

One application-retained verifier receives trusted issuer/audience/algorithm
configuration. It parses bounded token segments, resolves only eligible keys
from a bounded JWKS response, verifies all mandatory claims, enforces
subject-kind-specific coarse scope, optionally requires exact-identity
introspection, and returns one immutable result. JWKS and introspection use
distinct injectable per-operation clients and never share bearer credentials.

## Alternatives Rejected

- PyJWT's network JWKS client: insufficient ownership of redirects, timeouts,
  response bounds, cache, and transport injection.
- Shared HMAC production secrets: violates the asymmetric issuer boundary.
- Token roles inside canonical verified identity: creates product authority
  outside Workstream grants and revocation.
- A second token-verifier hierarchy: duplicates the existing port/factory.
- Synchronous-first network verification: conflicts with the async backend.

## Scope Control

The diff is limited to approved AUTH-02 runtime/config/schema/test/runbook/API
drill files and durable loop memory. Contract amendments explicitly allow the
production app-factory boundary, three null identity-metadata expectations, and
the canonical auth-spec correction. No migration, grant, permission service,
product authorization cutover, review, contribution, payment, or frontend work
is included.

## Product Behavior

- Missing/invalid/inactive credentials return 401.
- Trusted verification infrastructure unavailability returns a non-secret 503.
- Human/service tokens require distinct coarse scopes.
- Agent and Space identities are represented but cannot reach human product
  routes.
- Issuer roles do not enter `VerifiedIssuerToken` or become product authority.
- During compatibility, `/api/v1/auth/me` no longer copies issuer email or
  display name; those response fields remain null.
- Existing review decisions and project/task/submission lifecycles are unchanged.

## Acceptance Criteria Proof

Tests cover malformed/oversized tokens, pinned algorithms, remote-key header
rejection, mandatory claims, temporal skew, subject kinds/scopes, JWKS key
eligibility/rotation/outage/cooldowns/single-flight/negative cache,
introspection success/mismatch/missing fields/redirect/timeout/oversize,
credential redaction, client separation/closure, bounded metrics, production
startup, dev-fixture exclusion, compatibility allowlists, and API behavior.

## Tests And Checks

- 130 tests passed with disposable PostgreSQL: every auth/config test plus
  three additional changed actor/task test nodes.
- 680 full backend tests passed in 7653.15 seconds.
- The real API contract drill passed.
- Clean base dependency install/import and `pip check` passed.
- Ruff, stale wording, stale authorization docs, Markdown links, loop memory,
  docstring coverage, and `git diff --check` passed.

## Test Delta

No tests were removed, skipped, xfailed, or weakened. Null identity-metadata
expectations changed across five test functions: two are in the complete
auth/config run and three are the additional actor/task nodes. The exact
changed-test delta passes independently. New tests exercise previously
uncovered security branches rather than mirroring implementation internals.

## CI Integrity

No workflow, threshold, runner, ignore, or failure-bypass change is included.
The only dependency change matches human-approved D12 and installs cleanly.

## Reviewer Results

All required tracks pass on reviewed code SHA
`47dd5a77c588d1b2b4e7f00489faf4c633f26aa2`: senior engineering, QA/test,
security/auth, product/ops, architecture, docs, CI integrity, reuse/dedup, and
test delta. First-cycle findings were repaired and independently re-reviewed.

## External Review

Ready PR #107 is published. GitHub checks, CodeRabbit, and explicit human
review remain pending.

## Remaining Risks

- Production issuer configuration and live issuer behavior remain deployment
  and later live-proof inputs.
- Development-only dynamic verifier settings remain intentionally separate
  from production app-bound issuer pinning.
- Bounded legacy role compatibility remains until its owning cutover/removal.

## Follow-Up Work

AUTH-03 and all later AUTH chunks remain inactive until this PR is externally
reviewed, explicitly merged by the user, and post-merge memory is completed.

## Human Review Focus

Inspect algorithm/issuer pinning, JWKS outage and rotation behavior,
introspection credential isolation, application verifier ownership, subject
kind/scope handling, absence of token-role authority, and the approved
dependency move.

## Human Merge Ownership

Only the user may approve and merge this PR. Publication is not merge approval.
