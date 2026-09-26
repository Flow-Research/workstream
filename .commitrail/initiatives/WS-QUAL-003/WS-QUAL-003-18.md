# WS-QUAL-003-18 — successful service-actor provisioning proof

- Initiative: WS-QUAL-003
- Durable disposition: Planned
- Intended merge outcome: Replace the remaining 641-line mixed success/API
  test with focused behavior proofs and an exact old-assertion reconciliation.

## Intent

### Problem being solved

`backend/tests/test_auth.py::test_controlled_service_actor_provisioning_includes_project_setup_and_is_atomic`
mixes successful provisioning, replay, validation, denials, privacy, conflict,
race, rollback/retry, audit and grant-absence assertions in one 641-line test.
PR #446 already extracted authority-write failure/retry, distinct-key
service-identity contention, and provision/revoke serialization. This change
must retain the remaining success contract without repeating those proofs.

### Why this matters

The successful public route is the source of service actor identity binding.
Its proof should make exact configured-issuer/subject/profile binding,
idempotent replay, denial boundaries, and absence of elevated grants directly
reviewable, while preserving real FastAPI and PostgreSQL behavior.

### Current behavior

The single test constructs a signed production app, calls the public
`POST /api/v1/service-actors` route, inspects persisted actor/link/idempotency/
audit facts, and covers multiple unrelated request outcomes. The adjacent
REV/adapter identity-catalogue test is a separate test and remains out of scope.

### Target behavior

Focused service-actor tests each prove one primary observable behavior using
the existing signed-access and admin-access fixtures. All materially distinct
old assertions and loops receive one exact disposition in the assertion map.
Existing PostgreSQL, audit, privacy, authorization, replay and transaction
semantics remain intact; cases already owned by PR #446 are mapped to those
surviving proofs rather than duplicated.

### Design chosen

Reuse `backend/tests/authorization/service_actors/` and its exported fixtures;
do not rebuild signed-app/bootstrap composition or introduce generic testing
frameworks. Expose the existing signed fixture's already-created FastAPI app
through `SignedAccess` only as needed to replace the verifier in the
canonical-issuer-unavailable case; do not reach through private HTTPX transport
state. For same-key races use `ordered_owner_calls(..., boundary="reservation")`;
for distinct-key shared-subject contention use
`ordered_owner_calls(..., boundary="control")`. Add a reservation-race
negative control demonstrating the exact PostgreSQL waiter proof fails if
reservation stops contending. The fixed-identity/distinct-key race is already
owned by PR #446 and maps to its surviving exact control-row test. Keep each
new test below 120 lines, helper below 100, and new module below 500 lines.

Before code changes, preserve this capability map as the semantic plan; the
machine assertion map supplements it and does not replace it:

| Primary behavior atom | Existing proof in selected node | Proposed exact final proof node | Layer and evidence custody |
|---|---|---|---|
| Signed human access resolves an actor profile and bootstrap supplies the system admin authority required to provision | `admin_profile` / `ordinary_profile` responses and `run_admin_bootstrap` assertion | Fixture setup used by `tests/authorization/service_actors/test_provisioning_success.py::test_service_actor_provisioning_binds_exact_identity`; fixture asserts profile reads and successful bootstrap | Existing signed HTTP + PostgreSQL fixture precondition; no duplicate bootstrap |
| Normal fixed-service provisioning returns the closed response and persists exact profile, configured issuer, opaque subject, creator and active states | Initial `created` request and state tuple | `tests/authorization/service_actors/test_provisioning_success.py::test_service_actor_provisioning_binds_exact_identity` | HTTP + PostgreSQL integration |
| `PROJECT_SETUP` is admitted with exact issuer/subject/profile binding | `setup_created` and `setup_state` block | `tests/authorization/service_actors/test_provisioning_success.py::test_project_setup_identity_is_provisioned` | HTTP + PostgreSQL integration |
| Before provisioning, a service token cannot self-authorize the provisioning route or create state | `unprovisioned_service` request | `tests/authorization/service_actors/test_provisioning_rejections.py::test_unprovisioned_service_cannot_provision_itself` | HTTP + PostgreSQL integration |
| After provisioning, the service token cannot use the human-only provisioning route or mutate its actor | `service_human_path_denial` and unchanged state | `tests/authorization/service_actors/test_provisioning_rejections.py::test_provisioned_service_cannot_use_human_provisioning_route` | HTTP + PostgreSQL integration |
| Exact committed same-key replay returns the original response and normal authenticated-actor timestamp touches | `replayed`, response equality, timestamp comparisons | `tests/authorization/service_actors/test_provisioning_success.py::test_exact_replay_returns_original_provisioning_response` | HTTP + PostgreSQL integration |
| Unavailable committed replay returns retryable 503 and rolls back caller timestamp touches | `unavailable_replay_result` and timestamp/state checks | `tests/authorization/service_actors/test_provisioning_success.py::test_unavailable_replay_does_not_touch_actor_or_service_state` | HTTP + PostgreSQL transaction |
| Same-key payload mismatch is 409 and rolls back caller timestamp touches | `mismatched` and timestamp/state checks | `tests/authorization/service_actors/test_provisioning_success.py::test_mismatched_replay_does_not_touch_actor_or_service_state` | HTTP + PostgreSQL transaction |
| Fixed service identity cannot be rebound to another subject | `fixed_identity_conflict` | `tests/authorization/service_actors/test_provisioning_rejections.py::test_fixed_identity_cannot_be_rebound` | HTTP + PostgreSQL integration |
| One external subject cannot be linked to a second fixed service identity | `subject_conflict` | `tests/authorization/service_actors/test_provisioning_rejections.py::test_subject_cannot_be_linked_to_second_identity` | HTTP + PostgreSQL integration |
| Ordinary human, agent and space callers cannot provision service identities | `denied` plus nonhuman-kind loop (`agent`, `space`) | `tests/authorization/service_actors/test_provisioning_rejections.py::test_only_authorized_human_can_provision_service_actor` | HTTP + persisted no-create assertion |
| A provisioned service identity cannot use the actor self-profile API | `service_denial` GET `/api/v1/actors/me` and unchanged service state | `tests/authorization/service_actors/test_provisioning_rejections.py::test_provisioned_service_cannot_read_human_self_profile` | HTTP + PostgreSQL integration |
| A regular human self-profile GET succeeds without token role authority | `ordinary_profile` status within the initial setup | `tests/actors/test_self_api.py::test_actors_me_returns_contributor_without_token_role_authority`; also exercised by the shared signed actor fixture | Existing route proof; remove incidental setup assertion |
| Malformed subject/reason, whitespace subject, unknown identity and malformed idempotency key are rejected without echo | `invalid`, `whitespace`, `unknown`, `invalid_header` | `tests/authorization/service_actors/test_provisioning_rejections.py::test_invalid_provisioning_inputs_are_rejected_without_echo` | HTTP contract |
| Same-key identical concurrent calls serialize at the real reservation boundary and return one result | `same_replays` race | `tests/authorization/service_actors/test_provisioning_concurrency.py::test_same_key_concurrent_identical_requests_replay_one_result` | HTTP + PostgreSQL waiter/blocker + stored rows |
| Same-key concurrent payload drift serializes at reservation and produces one success plus one mismatch | `drift_race` | `tests/authorization/service_actors/test_provisioning_concurrency.py::test_same_key_concurrent_payload_drift_is_rejected` | HTTP + PostgreSQL waiter/blocker + stored rows |
| Distinct identities racing for one external subject leave exactly one link owner | `external_race` | `tests/authorization/service_actors/test_provisioning_concurrency.py::test_distinct_identities_cannot_claim_same_subject` | HTTP + PostgreSQL AUTH-control waiter/blocker + exact rows |
| Reservation contention observer rejects a lock-free/no-op reservation owner | Existing `run_reservation_race` barrier only | `tests/authorization/service_actors/test_provisioning_concurrency.py::test_same_key_race_proof_rejects_nonblocking_reservation` | Test-of-test with hosted PostgreSQL; expected inner failure: `ordered lifecycle request never reached the database lock`, propagated as `actual owner lock observation failed` |
| Failure writing `SERVICE_ACTOR_PROVISIONED` evidence rolls back and allows same-key retry | `fail_success_evidence`, `failed`, `retried` | `tests/authorization/service_actors/test_provisioning_atomicity.py::test_success_evidence_failure_rolls_back_and_allows_retry` | HTTP + PostgreSQL transaction |
| Commit failure rolls back and allows same-key retry | `commit_failed`, `commit_retried` | `tests/authorization/service_actors/test_provisioning_atomicity.py::test_commit_failure_rolls_back_and_allows_retry` | HTTP + PostgreSQL transaction |
| Canonical issuer lookup failure returns the specific unavailable-verification error | `CanonicalIssuerUnavailable` verifier case | `tests/authorization/service_actors/test_provisioning_rejections.py::test_canonical_issuer_unavailable_fails_closed` | HTTP + shared app/verifier fixture |
| Sensitive token, issuer, subject, reason and request values are absent from responses, app logs and persisted audit serialization | `sensitive_values` collection and final response/log/audit assertions | `tests/authorization/service_actors/test_provisioning_privacy.py::test_provisioning_secrets_are_not_exposed_in_responses_logs_or_audit` | HTTP + logs + PostgreSQL audit |
| Provisioning leaves no service last-seen, admin/project grants or pending reservation; success/conflict audit actions remain exact | Final profile, pending, event, grant and denial queries | `tests/authorization/service_actors/test_provisioning_success.py::test_service_provisioning_persists_only_scoped_audit_and_no_grants` | PostgreSQL integration |
| Distinct idempotency keys for one fixed service identity cannot create duplicates | `fixed_race` | `tests/authorization/service_actors/test_provisioning_atomicity.py::test_distinct_keys_cannot_duplicate_service_actor_after_authority_serialization` in PR #446 | Already owned by PR #446 / PostgreSQL control-row waiter |
| Injected AUTH decision, invalidation and idempotency-completion failures fully roll back and allow retry | Prior failure slice | `tests/authorization/service_actors/test_provisioning_atomicity.py::test_authority_write_failure_rolls_back_provision_and_allows_retry` in PR #446 | Already owned by PR #446 / PostgreSQL transaction |
| Current admin authority is serialized against revocation in both orders | Prior failure/race slice | `tests/authorization/service_actors/test_provisioning_atomicity.py::test_authority_revocation_serializes_with_service_provisioning` in PR #446 | Already owned by PR #446 / PostgreSQL waiter/blocker |

The old loop/comprehension inventory is source-exact (line numbers refer to
the baseline node at `7ff306f`):

| Baseline lines | Old loop/comprehension | Disposition |
|---|---|---|
| 416, 670 | Build and exercise agent/space credentials | `test_only_authorized_human_can_provision_service_actor`; privacy requests also inspect their tokens |
| 720 | Iterate service self-profile path | `test_provisioned_service_cannot_read_human_self_profile` |
| 734 | Collect same-key race status codes | `test_same_key_concurrent_identical_requests_replay_one_result` |
| 748, 750 | Collect same-key drift outcomes and select mismatch | `test_same_key_concurrent_payload_drift_is_rejected` |
| 766, 768 | Collect fixed-identity race outcome and select conflict | PR #446's `test_distinct_keys_cannot_duplicate_service_actor_after_authority_serialization` |
| 795, 797 | Collect shared-subject race outcome and select conflict | `test_distinct_identities_cannot_claim_same_subject` |
| 917, 923, 935–936 | Build the private-value set, including nonhuman token subjects/IDs | `test_provisioning_secrets_are_not_exposed_in_responses_logs_or_audit` |
| 955–956 | Check private values against every captured response and application log | Same privacy test |
| 995, 1007 | Build service-profile ID lists for grant-absence queries | `test_service_provisioning_persists_only_scoped_audit_and_no_grants` |
| 1014, 1019–1020, 1022, 1024 | Check every service lifecycle, event and audit row | Same persisted-audit test; response/log/audit secrecy remains in the privacy test |

The old `run_reservation_race` barrier only synchronized Python callers; it did
not observe database lock custody. It is replaced by the shared owner-lock
observer and its hosted PostgreSQL negative control. The same-key fixed-identity
race is not recreated because PR #446 owns its exact control-row proof. Every
old assertion still has exactly one machine-checked disposition in the
assertion map; this table separately accounts for iterable behavior that the
assertion mapper does not model.

### Structural-scope finding

While validating the new files, the structural validator omitted the
`authorization/service_actors` owner directory from its unconditional scope.
Several focused modules did not directly import the authorization package, so
they could otherwise evade test-size and skip/xfail checks despite residing in
the AUTH owner. The bounded repair adds that exact directory to the existing
scope and a regression proving nested service-actor tests are included. This
does not broaden production scope, lane selection, CI policy or test execution;
it makes the existing AUTH structural policy inspect its own test package.

### Alternatives considered

- Keep the monolith: rejected because its mixed assertions obscure which
  provisioning behavior failed.
- Replace route/database proof with unit mocks: rejected because this contract
  depends on authentication, authorization, transaction and persistence wiring.
- Duplicate PR #446 failure/race cases: rejected; reuse its exact regression
  tests as mapped surviving proof.
- Rewrite unrelated service catalogue or actor lifecycle tests: rejected as
  separate capabilities.

### Boundaries preserved / what must not change

- Product code, API schemas/routes, migrations, runtime behavior, CI selection,
  thresholds, timeouts and dependencies are unchanged.
- Do not touch the neighboring
  `test_controlled_endpoint_provisions_review_and_adapter_target_identities`
  catalogue test or actor-profile/identity-link lifecycle matrices.
- Do not weaken, skip, xfail, deselect, or delete behavior without a named
  surviving proof; do not optimize for test count, coverage, or LOC.
- Preserve actual issuer/subject/profile binding, idempotency, current
  authorization, rollback/atomicity, audit privacy, and no-admin/project-grant
  behavior.

### Expected risks

The split could silently lose one of the old loop variants, conflate idempotency
replay with authorization, or move a PostgreSQL claim into a mock-only test.
The exact assertion map, real route/database tests, test-delta review and
hosted full Backend run mitigate those risks.

### How it will be proven

- Record the 641-line source node and exact baseline before editing.
- Generate a complete old assertion/loop inventory and map every item once.
- Run these deterministic repository checks:

  ```sh
  (cd backend && uv run python -m scripts.test_structure_boundary validate --policy ../.ci/auth-boundaries/TEST_STRUCTURE_POLICY.md --ledger ../.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json)
  (cd backend && uv run pytest --collect-only -q tests/authorization/service_actors)
  (cd backend && uv run pytest -q tests/test_ci_lane_catalogue.py)
  uv run --project backend ruff check backend/tests/authorization/service_actors backend/tests/authorization/admin_access/support.py backend/tests/authorization/admin_access/fixtures.py backend/tests/test_auth.py backend/scripts/test_lane_catalogue.py backend/tests/test_ci_lane_catalogue.py
  uv run --project backend ruff format --check backend/tests/authorization/service_actors backend/tests/authorization/admin_access/support.py backend/tests/authorization/admin_access/fixtures.py backend/tests/test_auth.py backend/scripts/test_lane_catalogue.py backend/tests/test_ci_lane_catalogue.py
  python3 scripts/check_markdown_links.py
  python3 scripts/check_stale_workstream_wording.py
  git diff --check
  ```

  The subshells keep the working directory at the repository root for every
  subsequent command.
- Require the full hosted Backend workflow on the exact PR head. Confirm each
  moved module has exactly one semantic lane owner and every manifest node
  completed with zero skipped/deselected tests. Use hosted PostgreSQL for all
  database claims; the local machine is not the full-suite judge.
- Run focused QA, test-delta, security, and CI-integrity reviews on the exact
  candidate because module/lane ownership changes.

### Human decisions required

None. This is a test-evidence refactor with unchanged product semantics.

## Bounded scope

### Allowed

- Remove only the selected function from `backend/tests/test_auth.py`.
- Add cohesive tests and minimal owner-scoped fixture support under
  `backend/tests/authorization/service_actors/`.
- Add the existing FastAPI app reference to
  `backend/tests/authorization/admin_access/support.py` and populate it in
  `backend/tests/authorization/admin_access/fixtures.py`; this exposes the app
  already created by the signed fixture without private transport access or a
  second bootstrap path.
- Add `backend/tests/authorization/service_actors/` to the structural
  validator's unconditional owner scope and cover that boundary in
  `backend/tests/architecture/test_test_structure_boundary.py`. This fixes the
  discovered scanner gap required to enforce the existing limits on these
  tests.
- Remove only imports made unused by deleting the selected function from
  `backend/tests/test_auth.py`.
- Register every added test module in the existing shared-foundations lane and
  its ownership test.
- Update `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`,
  `.ci/auth-boundaries/assertion-maps/WS-QUAL-003-18.json`, and the existing
  semantic lane catalogue/test to keep every moved test in full hosted execution.
- Update this record, WS-QUAL-003-17's durable status/reconciliation, and the
  initiative overview.

### Not allowed

- No production/API/schema/migration/runtime workflow, lane selection,
  thresholds or CI-policy edits; the explicitly allowed test-structure scanner
  scope above is the only enforcement-tool change.
- No edits to unrelated test families, product documentation, roadmap, or
  initiative index.
- No shared-fixture changes beyond carrying the existing app reference through
  `SignedAccess`; no HTTPX private transport access.
- No local full PostgreSQL or full Backend run.

## Acceptance criteria

- [x] Old test assertion and materially distinct loop inventory is complete;
  each item maps once to a final node or justified redundancy.
- [x] Successful provisioning asserts exact response contract and persisted
  configured issuer, opaque subject, service actor profile, creator, active
  lifecycle, and no service self-access.
- [x] Exact same-key replay returns the original result; mismatch and fixed
  identity/subject conflicts remain distinct and leave no unintended state.
- [x] Human/admin, ordinary, service, agent and space authority boundaries and
  validation/privacy outcomes retain their distinguishing expected responses.
- [x] `PROJECT_SETUP` provisioning and canonical-issuer-unavailable failure
  retain exact separate proof.
- [x] Success-event and generic commit failures retain rollback/retry proof
  without duplicating PR #446's AUTH evidence-write failures.
- [x] Success evidence is private as intended; idempotency is completed, no
  pending reservations remain, and service actors receive no admin/project
  grants.
- [ ] Same-key races observe the exact PostgreSQL reservation waiter and
  blocker; a negative control that bypasses reservation contention makes the
  observer fail. Shared-subject contention observes the AUTH control-row
  waiter; fixed-identity contention maps to PR #446.
- [x] No new structural debt; all new modules/tests/helpers meet policy limits.
- [x] The test-structure validator unconditionally scopes the service-actor
  owner directory, and its regression proves a nested file cannot evade size or
  skip/xfail detection.
- [x] Every moved module has one existing shared-foundations lane owner; the
  catalogue test passes and the focused package collects 30 nodes with no
  skips/deselections. Exact-head hosted Backend and applicable CI remain
  required before ready-for-merge.
- [x] Roadmap remains unchanged because delivered capability and API exposure
  are unchanged; verify again after main reconciliation.

## Risk, reviewers, and human focus

- Risk class: L1 — authorization and immutable identity/evidence proof only;
  no runtime change.
- Required reviews: focused QA, test-delta, security and CI-integrity because
  new test modules require semantic lane registration.
- Human review focus: exact identity binding, one-to-one assertion mapping,
  distinction from PR #446's existing proofs, actual transaction/evidence
  ownership, and no remaining unrelated assertions in each new test.

## Reconciliation

- Base: merged PR #446 at `7ff306f094ec28835e9da0506a2aeb38882569b7`.
- Prior boundary: PR #446 owns authority-write rollback/retry, distinct-key
  identity contention at the AUTH control row, and both provisioning/revocation
  serial orders. Do not repeat those tests.
- Next boundary after this change: audit actor-profile and identity-link
  lifecycle families, then remaining AUTH owners. Do not claim the full AUTH or
  repository test audit complete.
- Remaining risk: the other AUTH test families and the full suite inventory
  remain unaudited.
- Roadmap impact: none; this changes proof organization, not product capability
  or exposure.
