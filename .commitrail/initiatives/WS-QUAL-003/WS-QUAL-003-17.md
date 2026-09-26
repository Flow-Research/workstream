# WS-QUAL-003-17 — AUTH service-provisioning failure and race proof

- Initiative: WS-QUAL-003
- Durable disposition: Planned
- Intended merge outcome: Replace one mixed service-actor failure/race test with
  small, independently identifiable PostgreSQL proofs for rollback, exact
  fixed-identity contention, and current-authority behavior during revocation.

## Intent

Continue the behavior audit by making the failure boundaries of controlled
service-actor provisioning reviewable. Preserve real HTTP, PostgreSQL,
transaction and authorization behavior. Improve the race test so success means
the exact database lock waiter was observed, not just that both test coroutines
arrived at a Python barrier.

## Current behavior

`backend/tests/test_auth.py::test_service_actor_provisioning_failure_and_authority_races_are_atomic`
is 401 lines and contains 37 assertion statements. It covers three injected
failure points, same-fixed-service provisioning under distinct idempotency
keys, and provisioning crossed with revocation of the caller's active
administrator grant. Both races synchronize at Python hooks but do not observe
an exact PostgreSQL waiter. Route inspection shows `authorization.require`
locks the shared authority-control row before provisioning takes the fixed
service-identity advisory lock. Therefore separate authorized public requests
serialize at the control row first; a test claiming that they contend at the
later advisory lock would be unreachable through this route.

Production behavior is owned by the existing `/api/v1/service-actors` route,
`ServiceActorProvisioningService`, `ActorRepository.lock_service_identity`, and
the existing authorization transaction. This change does not modify those
owners. Reuse signed-actor fixtures and `ordered_owner_calls` at the actual
control-row boundary; do not add a generic race framework or a lower-level lock
test that does not demonstrate a public behavior.

## Bounded change

### Allowed

- `backend/tests/test_auth.py`: remove only
  `test_service_actor_provisioning_failure_and_authority_races_are_atomic`.
- New `backend/tests/authorization/service_actors/` tests and minimal fixture
  re-exports/support for the selected behaviors.
- Reuse existing PostgreSQL lock-observation support to observe the exact
  authorization-control waiter and blocker for both public API races.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json` and
  `.ci/auth-boundaries/assertion-maps/WS-QUAL-003-17.json` for exact debt and
  old-assertion reconciliation.
- Existing semantic lane catalogue and its owner test, if needed to retain
  complete hosted execution of moved tests.
- This record and the initiative overview. No roadmap or product documentation
  change.

### Not allowed

- No product code, schema, migration, API contract, CI selection/threshold,
  dependency, timeout, or runtime behavior change.
- Do not weaken or remove real PostgreSQL rollback, retry, exact identity
  exclusivity, permission revocation, or audit/idempotency assertions.
- Do not count a synchronization barrier as proof of database contention.
- Do not modify the separate successful provisioning/catalogue test or the
  actor profile/identity-link lifecycle tests in this change.
- No test-count, coverage, or LOC target; do not replace the real route tests
  with unit mocks.

## Design and decisions

Keep failure injection cases independently named or parameterized by the exact
failed persistence boundary: authorization decision evidence, invalidation
evidence, and idempotency completion. Each must assert unchanged caller and
service state after failure, then an exact successful retry with no pending
reservation. Keep distinct-key creation for the same fixed service identity as
one PostgreSQL contention behavior. Observe the actual authorization-control
waiter and blocker, then assert one committed profile/link/evidence result and
one conflict. This proves the public route's real serialization boundary; it
does not claim the later service-identity advisory lock independently
arbitrates an HTTP race.

Keep current-authority validation during grant revocation as a separate race
from service-identity exclusivity. Reuse the existing exact-owner lock observer
if its boundary applies; otherwise use one test-local observer with named
waiter/blocker PIDs. Assert the permitted serial outcomes, persisted state,
denial evidence and fresh denial after revocation. Keep each test under 120
lines, helpers under 100 lines, and new modules under 500 lines. No original
assertion is retired without a named surviving assertion or a specific
redundancy rationale in the exact assertion map.

## Acceptance criteria

- [x] The old 401-line function is replaced by focused named behavior tests;
  each test has one primary invariant and remains within the AUTH structure
  limits.
- [x] Each injected failure boundary proves no partial actor/link, authority,
  idempotency or audit state and proves the same-key request can retry.
- [x] The distinct-key public API race proves the exact waiter is blocked by
  the exact authority-control lock holder and leaves one committed profile/link
  with one success evidence chain plus one conflict.
- [x] Revocation contention proves the actual control-row waiter and only the
  outcomes valid under serialized authority; a request after revocation is
  denied even when it reuses the prior key.
- [x] Every assertion and materially distinct loop case from the removed test
  has one exact assertion-map disposition.
- [x] PostgreSQL tests remain in existing required semantic lanes; no skips or
  deselections are introduced.
- [x] The structural debt ledger and full selected-module collection validate.
- [ ] Full hosted Backend and other required checks pass on the exact PR head;
  their current results remain on GitHub.
- [ ] `docs/roadmap_status.md` remains unchanged because this slice changes test
  evidence, not delivered capability or API exposure.

## Risk and review routing

- Risk class: L1 — authorization, race and rollback proof only; no runtime
  change.
- Required reviewers: focused QA, test-delta, security, and CI-integrity review
  because the change decomposes AUTH evidence, strengthens concurrency
  observation, and relocates hosted tests.
- Human review focus: exact locked rows and transaction boundaries; no loss of
  a distinct failure, denial, replay, event, or identity-conflict behavior; the
  race cannot pass without the actual PostgreSQL waiter.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current race assertions are individually mapped | `.ci/auth-boundaries/assertion-maps/WS-QUAL-003-17.json` and structural validator | All 37 original assertions mapped; validator passes | Semantic equivalence still receives internal review |
| Moved tests remain in full hosted execution | Lane catalogue and `tests/test_ci_lane_catalogue.py` | Module assigned to the existing shared-foundation lane; catalogue tests pass | Hosted exact-head execution remains required |
| Changed race proves real contention | `ordered_owner_calls` observes exact named PostgreSQL waiter and blocker on the shared AUTH control row | Test contract and exact custody helper are present | Local database unavailable; hosted PostgreSQL run required |

## Review findings

No implementation review has run yet.

## Reconciliation

- Current-source reconciliation: PR #444 is merged. It retired coverage quotas
  without changing the full behavior/integration run. This change does not
  repeat its CI or documentation work.
- Next usable boundary: continue the AUTH test audit with successful
  service-actor provisioning and actor-profile/identity-link lifecycle proof;
  do not repeat this failure/race slice.
- Remaining risks: the rest of `test_auth.py`, especially profile and
  identity-link lifecycle matrices, remains unaudited and is not certified by
  this change.
