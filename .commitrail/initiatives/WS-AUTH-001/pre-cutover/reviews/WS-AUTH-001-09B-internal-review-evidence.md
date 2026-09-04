# WS-AUTH-001-09B Internal Review Evidence

Reviewed code SHA: `3a4d042213a555df7f479408ffafc43911296528`

Reviewed implementation SHA: `127615fde8f1b5583acf9dbbb3c606db514a455d`

Reviewed against trusted main:
`a947b8693a97bdb94c9dc63202a51e197834d613`

Reviewed at: `2026-07-17T21:42:22Z`

Reviewer run IDs: `auth_xint_roles`, `auth_xint_art_service`,
`auth_xint_rev_con`

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

## Deterministic Evidence

- The catalogue contains 74 PermissionIds and 65 ActionIds: exactly 10 active
  and 55 planned. AUTH-09B activates only `actor.service.provision`; no ART,
  REV, CON, service-admission, grant, or assignment action becomes active.
- `POST /api/v1/service-actors` accepts one closed fixed service identity, one
  opaque subject, one bounded reason, and one UUID idempotency key. The issuer
  comes only from the configured `AuthVerifier.canonical_issuer()` port.
- Creation atomically commits one service ActorProfile, one unverified exact
  issuer/subject link, decision/success/invalidation evidence, and idempotency
  completion. Service `last_seen_at` and `last_verified_at` remain null.
- Service and other nonhuman tokens are denied inside the actor service before
  lookup, canonical resolution, or timestamp touch. AUTH-09E remains the only
  future service-token admission boundary.
- Independent-session behavior tests cover same-key replay and mismatch,
  fixed-identity and external-identity races, same pair with different keys,
  crossed grant revocation, rollback/retry, and deterministic conflict
  precedence without deadlock or partial state.
- Fresh-row authorization tests use independent PostgreSQL sessions to prove
  both cached active-to-suspended/revoked and cached inactive-to-reactivated
  lifecycle transitions. Removing `populate_existing=True` from either locked
  profile or link query breaks the corresponding identity-map assertion.
- Provisioning rejects a subject with leading or trailing whitespace rather
  than normalizing it, so every accepted byte-exact binding can match the
  Identity Issuer verifier. The 422 response remains non-echoing.
- Idempotent replay fails closed when the stored service profile is deactivated
  or its exact identity link is revoked.
- Injected decision-evidence, success-evidence, invalidation-evidence,
  idempotency-completion, and commit failures return the stable retryable 503
  envelope and prove full rollback before successful retry.
- Privacy tests scan every response body, application log, and audit row and
  prove raw tokens, subjects, issuer, email, and reasons never escape. OpenAPI
  documents the strict request and explicit 409 response contracts.
- The broad actor/auth/authorization selection passed 236 tests. Actor legacy
  classification and migration tooling passed 109 tests. The focused API and
  OpenAPI selection passed 16 tests after current-main integration.
- The isolated real HTTP API contract drill passed through
  `scripts/run_isolated_tests.py` and cleaned up its derived database. The
  GitHub Backend workflow and an exact agent-gate regression prevent use of a
  persistent application database for that destructive drill.
- GitHub Backend now has three separate post-full-suite `coverage report`
  gates for actors, authorization, and the verifier boundary, each with an
  exact 90 percent floor and regression-protected ordering before isolated
  E2E.
- Branch-aware focused coverage is 92.74 percent for the actor boundary, 90.18
  percent for authorization, and 92.27 percent for the verifier boundary. The
  replacement GitHub full suite passed 1,242 tests at 84.92 percent, above the
  78 percent repository floor.
- The replacement authorization gate then reported 1,600 statements, 164
  misses, and 89.75 percent. Two behavior tests prove authorization-before-
  disclosure, exact typed resource binding, caller touch, route-owned commit,
  rollback, and stable retryable 503 mapping. They execute nine previously
  missed statements, projecting 155 misses and 90.31 percent on the unchanged
  denominator; replacement GitHub Backend remains the authoritative proof.
- The complete isolated PostgreSQL authorization file passes 85 tests. The two
  new focused tests also pass directly and under targeted coverage.
- Migration `0024` upgrade, guarded downgrade, and re-upgrade behavior passed
  against isolated PostgreSQL. Human links remain timestamped while newly
  provisioned service links are explicitly unverified.
- Compileall, Ruff, merge-intent validation, stale Workstream, authorization,
  and artifact scans, Markdown links, all 80 agent-gate tests, the focused
  current-main integration tests, and diff integrity pass.
- The first PR Backend run passed evidence, install, lint, docstring, and
  isolated-runner steps, then reported 1 failed and 1,240 passed at 84.87
  percent global coverage because the exact active-action audit expectation
  omitted `actor.service.provision`. The next run passed all 1,242 tests and
  exposed only the new authorization coverage gate described above. The
  reviewed behavior repair closes that measured gap without changing
  production code or weakening any threshold; replacement checks remain.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | The route, transaction owner, replay contract, and fixed identity boundary are coherent and bounded. |
| QA/test | PASS AFTER FIXES | none | Behavior tests prove races, rollback, retry, privacy, migration, replay, denial, and stable API envelopes. |
| security/auth | PASS AFTER FIXES | none | Issuer configuration is server-owned, opaque identity data does not escape, and service callers remain denied before lookup. |
| product/ops | PASS | none | Only an effective system Access Administrator may provision; provisioning grants no service or human authority. |
| architecture | PASS AFTER FIXES | none | AUTH retains central identity, evaluator, activation, and evidence ownership without feature-owned authorization paths. |
| CI integrity | PASS AFTER FIXES | none | The real HTTP drill uses an isolated derived database and no threshold, skip, or exclusion was weakened. |
| docs | PASS AFTER FIXES | none | Specification, operations, chunk, and authored lifecycle state match runtime behavior and keep AUTH-09C inactive. |
| reuse/dedup | PASS AFTER FIXES | none | The implementation reuses canonical actor locks, authorization evidence, idempotency, and adapter ports without compatibility paths. |
| test delta | PASS AFTER FIXES | none | Tests are behavior-first and assert exact state, evidence, privacy, rollback, and retry outcomes. |

## Findings Resolved

Valid findings addressed: yes

Open sub-agent sessions: none

Initial review repairs added pre-lookup service denial inside `ActorService`, bounded
independent race proofs, crossed grant-revocation proof, injected evidence and
idempotency failure matrices, complete privacy scanning, explicit OpenAPI 409
contracts, and isolated-only real API verification. The final current-main
integration changed no reviewed AUTH runtime and preserved the WS-CON handoff's
registration -> hidden behavior -> AUTH activation order.

External review repairs force locked ORM rows to refresh, reject unusable
surrounding subject whitespace without normalization, deny replay from inactive
stored state, enforce all three 90 percent subsystem floors in GitHub Backend,
restore the exact active-action audit set, and add behavior proof for the
authorization coverage gap exposed by the enforced gate. All required tracks
passed the repair and its final lifecycle state at exact SHA `3a4d042`.

## Remaining Risk And Gate

This chunk records an unverified service credential binding; it deliberately
does not prove or admit the service token. A later separately approved AUTH-09E
must implement fixed-service verification and admission without weakening the
human boundary.

Replacement GitHub Backend, Agent Gates, CodeRabbit, and explicit human merge
approval remain. Do not start `WS-AUTH-001-09C` automatically.
