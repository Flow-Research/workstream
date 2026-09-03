# WS-AUTH-001-09B PR Trust Bundle

## Chunk

`WS-AUTH-001-09B` - Controlled Service Actor Provisioning

## Goal

Let an effective system Access Administrator bind one opaque Identity Issuer
subject to one fixed internal service ActorProfile without granting service
authority or admitting service tokens.

## Changes

- Added a strict idempotent `POST /api/v1/service-actors` route with a
  server-owned configured issuer and a closed fixed service identity.
- Added one atomic provisioning service for actor/link creation,
  authorization decision evidence, mutation success, invalidation, and replay.
- Activated only `actor.service.provision`; the catalogue is 65 actions with
  10 active and 55 planned.
- Added migration `0024` so human identity links remain verified while newly
  provisioned service links remain explicitly unverified.
- Repaired canonical profile-before-link locking and denied service/nonhuman
  subjects before actor lookup or timestamp touch.
- Forced locked actor/link queries to replace cached ORM state and proved both
  lifecycle directions with independent PostgreSQL sessions.
- Rejected surrounding subject whitespace without normalization and denied
  replay from deactivated profiles or revoked links.
- Added three independent GitHub Backend 90 percent coverage reports for the
  actor, authorization, and verifier boundaries.
- Added real concurrency, rollback, retry, privacy, migration, API, OpenAPI,
  and isolated HTTP behavior proof.

## Boundary

ActorProfile remains the stable local principal. `(issuer, subject)` remains a
separate credential link. The request cannot supply issuer, ActionId,
PermissionId, role, grant, or assignment. Subject, issuer, token, email, and raw
reason never enter public output, logs, or audit evidence.

Provisioning is not verification or admission. It creates no grant or dynamic
assignment and activates no ART, REV, CON, or feature action. AUTH-09E remains
the only future owner of fixed-service token admission.

## Proof

- Broad actor/auth/authorization behavior selection: 236 passed.
- Actor classification and migration tooling: 109 passed.
- Current-main API/OpenAPI integration selection: 16 passed.
- External-review lock/replay selection: two passed in isolated PostgreSQL.
- External-review provisioning concurrency/privacy selection: one passed.
- Exact active-action audit parity repair: one passed.
- Complete isolated PostgreSQL authorization file: 85 passed.
- New definition-route and SQL-failure behavior tests: two passed.
- Actor coverage: 92.74 percent.
- Prior focused authorization coverage: 90.18 percent.
- Verifier boundary coverage: 92.27 percent.
- Replacement GitHub full suite: 1,242 passed at 84.92 percent against the 78
  percent CI floor.
- Replacement authorization gate before the final test repair: 1,600
  statements, 164 misses, 89.75 percent. Nine newly exercised statements
  project 155 misses and 90.31 percent; replacement CI remains authoritative.
- Isolated PostgreSQL migration and real HTTP API contract drills passed.
- Compileall, Ruff, stale scans, links, merge intent, all 80 agent gates, and
  diff integrity pass.

Exact reviewed code SHA
`3a4d042213a555df7f479408ffafc43911296528` passed senior engineering,
QA/test, security/auth, product/ops, architecture, CI integrity, docs,
reuse/dedup, and test-delta review after all valid findings were repaired.

## External Review

CodeRabbit's four actionable fresh-row, subject-validation, replay-lifecycle,
and CI coverage findings are fixed. The first Backend run exposed one stale
exact active-action audit expectation after 1,240 tests passed at 84.87 percent
global coverage; that exact parity assertion is repaired. The next run passed
all 1,242 tests at 84.92 percent and exposed the authorization gate at 89.75
percent. The final behavior-test repair projects 90.31 percent without changing
production code or weakening CI. Replacement GitHub Backend, Agent Gates, and
CodeRabbit remain pending on the repaired PR head. Backend remains authoritative
for the global 78 percent floor and runs the destructive HTTP contract drill
only against an isolated derived database.

## Follow-up

AUTH-09C is a separate actor and identity-link administration-read chunk. It
requires AUTH-09B merge, signed post-merge memory, and a new explicit human
start. AUTH-09D and AUTH-09E remain later separate lifecycle and service
admission boundaries.

## Merge Intent

The immutable schema-v2 merge intent is
`.agent-loop/merge-intents/WS-AUTH-001-09B.json`. It records AUTH-09B as the
completed chunk candidate and names AUTH-09C only as the same-initiative
successor. AUTH-09C still requires this PR to merge, signed automated memory to
pass, and a separate explicit human start.

## Reviewer Results

| Track | Result | Blocking findings |
|---|---|---|
| Senior engineering | PASS AFTER FIXES | none |
| QA/test | PASS AFTER FIXES | none |
| Security/auth | PASS AFTER FIXES | none |
| Product/ops | PASS | none |
| Architecture | PASS AFTER FIXES | none |
| CI integrity | PASS AFTER FIXES | none |
| Docs | PASS AFTER FIXES | none |
| Reuse/dedup | PASS AFTER FIXES | none |
| Test delta | PASS AFTER FIXES | none |

## Remaining Risk

The created service link is intentionally unverified and unusable by service
callers. Service admission remains fail-closed until AUTH-09E provides exact
token verification and separately reviewed activation.

## Human Review Focus

Review the server-owned issuer, strict fixed identity request, atomic
idempotency/evidence chain, nullable unverified service timestamps,
profile-before-link ordering, pre-lookup service denial, and absence of grants
or feature activation. Only the human may approve and merge this PR.

## Merge Ownership

The agent may repair and publish this branch but may not merge it. Only the
human may approve PR #143 for merge. After merge, trusted-main automation owns
schema-v2 memory generation; no manual post-merge memory PR should be opened if
that workflow succeeds.
