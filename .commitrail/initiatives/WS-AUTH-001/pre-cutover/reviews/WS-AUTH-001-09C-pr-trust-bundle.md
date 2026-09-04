# WS-AUTH-001-09C PR Trust Bundle

## Chunk

`WS-AUTH-001-09C` - Actor And Identity-Link Administration Reads

## Goal

Give authorized human system administrators one exact, privacy-bounded view of
an ActorProfile or its single v0.1 ActorIdentityLink before lifecycle mutations
are introduced.

## Human-Approved Intent

The user explicitly started AUTH-09C after PR #143 merged and signed memory
stopped. No compatibility route, service admission, lifecycle mutation, or
feature-owned authorization is authorized.

## What Changed

- Added strict `GET /api/v1/actors/{actor_profile_id}` and
  `GET /api/v1/actors/{actor_profile_id}/identity-links` responses.
- Activated only `actor.profile.read` and `actor.identity_link.read`, moving the
  catalogue to 12 active / 53 planned actions.
- Added separate frozen resource contexts and serialized caller/link/grant
  revalidation through target disclosure and route commit.
- Added bounded actor-service projections, OpenAPI/manifest declarations, real
  HTTP proof, and behavior-first privacy, evidence, rollback, and race tests.

## Why It Changed

AUTH-09D needs administrators to select an exact actor or identity-link target.
The selection surface must exist first without adding list/search or revealing
external identity and authority data.

## Design Chosen

The server composes action-specific contexts from the path, authorizes before
lookup, reuses ActorService and ActorRepository exact reads, touches only the
verified caller, then commits the allow evidence and touch once. Missing targets
roll back and share one 404 contract. Self-target responses use the refreshed
caller timestamps from that same touch.

## Alternatives Rejected

Collection/search APIs, client-supplied actions or roles, project-scoped actor
registry authority, target-row locks, `AuthorityControl` on reads, a second
session, compatibility aliases, and raw issuer/subject output were rejected as
outside this chunk or unsafe.

## Scope Control

Trusted main through PR #141 at `a10d901` is integrated, including ART migration
`0025`, without changing its behavior. No AUTH migration, dependency, workflow,
grant/assignment behavior, service admission, ART/REV/CON activation, or
lifecycle mutation changed.

## Product Behavior

Effective system Access Administrator and Audit Authority grants may inspect
active, suspended, or deactivated human/service profiles and active/revoked
links. Project-scoped Audit Authority and every unsupported caller are denied
before target lookup.

## Acceptance Criteria Proof

Strict response fields, exact system authority, authorization-before-lookup,
stable 404 rollback, self-target freshness, exact persisted evidence, null
unverified service timestamps, response/log privacy, SQL failure rollback, and
real lock serialization are all covered by behavior tests.

## Tests And Checks Run

- Real PostgreSQL lifecycle and race repair selection: 2 passed.
- Final signed-token privacy/evidence repair: 1 passed.
- Authorization coverage selection: 136 passed, 92.04 percent branch coverage.
- Actor coverage selection: 145 passed, 91.06 percent branch coverage.
- Live HTTP API contract drill: passed.
- Ruff, route/kernel/OpenAPI/audit checks, stale scans, Markdown links, merge
  intent, diff integrity, and all 80 Agent Gates tests: passed.

## Test Delta

Tests add exact role/scope, cross-context, response, OpenAPI, audit, privacy,
self-target, missing-target, injected-failure, and two-session disabling-race
assertions. No test was skipped, weakened, or changed to conceal behavior.

## CI Integrity

The repository-wide 78 percent floor and focused 90 percent actor and
authorization floors are unchanged. No workflow, dependency, exclusion, or
threshold changed. GitHub Backend remains authoritative for the full suite.

## Reviewer Results

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta all pass the exact integrated repair
SHA `c47d6275c84e338e30f3d911d1cfdd9f1147fd86` after valid CodeRabbit and
internal-review findings were repaired.

## External Review

PR #146's original Backend, Agent Gates, and CodeRabbit checks passed.
CodeRabbit's five valid proof findings are repaired with exact transition
backend lock correlation, exact self-target and kernel assertions, both
missing-resource rollback routes, and both project-scoped Audit Authority
denials. Ten focused unit tests and two fresh real PostgreSQL lifecycle/race
tests pass after integrating trusted main. Exact integrated-head internal review
passes at `c47d627`; replacement external checks remain. The repair does not
change production behavior or weaken any test or threshold.

## Remaining Risks

The endpoints reveal bounded lifecycle timestamps and the closed local service
identity to system authorities by design. Exact external identity, provenance,
grant contents, and service authority remain concealed.

## Follow-Up Work

AUTH-09D owns lifecycle mutations only after this chunk merges, signed memory
passes, and the user gives a separate explicit start. AUTH-09E remains the
later fixed-service runtime-admission boundary.

## Human Review Focus

Review system-only role separation, caller/link/grant lock lifetime, response
privacy, self-target timestamp freshness, stable rollback behavior, exact audit
binding, and the absence of mutation or service admission.

## Human Merge Ownership

The agent may publish and repair this branch but may not merge it. Only the
human may approve and merge the PR. Trusted-main automation owns post-merge
schema-v2 memory; AUTH-09D does not start automatically.
