# WS-QUAL-003-15 — Split the mixed project-role PostgreSQL proof

- Initiative: WS-QUAL-003
- Durable disposition: Planned
- Intended merge outcome: Replace one oversized AUTH PostgreSQL test that
  combines independent project-role issue, revoke, uniqueness-conflict, and
  lock-cancellation behaviors with focused tests that preserve each real proof.

## Intent

Audit the current 665-line
`test_project_role_issue_postgresql_prep_binds_target_role_and_scope` before
changing it. Keep every distinct authorization, lifecycle, audit, rollback,
uniqueness, lock-wait and retry contract that survives source tracing. Separate
failures so one scenario cannot mask another. Correct the current false claim
that the public conflict case reaches the PostgreSQL unique-index fallback.

## Findings

- The test contains four independently meaningful behaviors: issue completion
  rejects substituted authority facts; revoke remains available after target
  profile/link lifecycle loss and emits exact invalidation evidence; the public
  issue route rejects an already-existing exact grant without losing persisted
  state; and a cancelled real PREP lock wait can retry the same idempotency key.
- The purported unique-index case does not currently reach the unique index.
  Its monkeypatch returns `None` for one lookup, then returns the existing grant
  on the next lookup (`find_calls == 2`), so the route rejects before insert.
  The production repository has a separate `IntegrityError` fallback for
  `uq_project_role_grants_active_exact_role`; this test does not prove it.
- Existing in-memory completion tests protect exact decision/resource matching,
  but they do not replace this test's PostgreSQL transaction-boundary proof.
  The cancelled-lock case is a genuine database lock wait, not a timing-only
  concurrency claim.

## Bounded change

### Allowed

- `backend/tests/test_authorization.py`: remove only the mixed test body and
  imports/helpers made unused by its extraction.
- `backend/tests/authorization/project_roles/`: add narrowly scoped PostgreSQL
  issue, revoke, conflict and cancellation tests plus the minimum shared seed,
  context, and database fixture needed by those tests.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json` and
  `.ci/auth-boundaries/assertion-maps/WS-QUAL-003-15.json` to retire the touched
  oversized-test debt item and map every old assertion from `origin/main` to
  its final named proof.
- This record and the initiative overview link.

### Prohibited

- No production, API, schema, migration, dependency, CI selection, coverage,
  roadmap capability, or unrelated test changes.
- Do not delete, skip, weaken, or merge any distinct assertion or lock case.
- Do not claim a concurrent-writer race from a forced query miss. The database
  unique-index fallback must be observed by catching its exact constraint name;
  otherwise name the retained test only for the recheck it actually proves.
- Do not add broad generic fixtures, arbitrary test-count targets, or duplicate
  authority setup abstractions.

## Acceptance criteria

- [x] Each extracted test has one primary behavior and is independently
  collected; functions stay within the AUTH structural limit.
- [x] Exact issue and revoke decision/resource substitution cases remain, with
  a valid reason digest so they reach the intended guard.
- [x] Revoke after target suspension and identity-link revocation remains a real
  PostgreSQL transaction and preserves the linked invalidation facts.
- [x] Existing-grant denial still proves the right status/code and absence of
  a second grant/snapshot, committed idempotency claim, allowed mutation audit,
  or invalidation.
- [x] Any claim of the unique-index fallback observes
  `uq_project_role_grants_active_exact_role`; otherwise the claim is removed.
- [x] Real lock wait, cancellation propagation/task cleanup, same-key retry,
  and exactly one committed idempotency record with linked events remain.
- [x] Assertion mapping covers every assertion in the exact old test node;
  no new structural debt is introduced.
- [ ] PostgreSQL-focused tests pass on the hosted Backend workflow; local
  collection and non-DB checks are not represented as PostgreSQL execution.

## Implementation checkpoint

The mixed test is replaced by five independently collected PostgreSQL cases:
exact issue binding, exact revoke binding, revoke after target suspension and
identity-link revocation, unique-index conflict rollback, and canceled-lock
same-key retry. The unchanged AUTH helper `_project_role_qualification` now
lives in the project-role test owner module and remains imported by the
existing AUTH tests that use it.

The former “real unique-index loser” path returned the existing grant on its
second lookup and never attempted the insert. The extracted test now simulates
the visibility miss at both pre-insert lookups, captures the actual
`IntegrityError`, and requires the exact active-role unique constraint before
checking that the public route returns the conflict and leaves no losing grant,
snapshot, committed idempotency claim, or claim-linked audit effect. This is a
controlled unique-index fallback proof, not a concurrent-writer race claim.

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Focused test collection | `uv run pytest --collect-only -q tests/authorization/project_roles` | Five expected nodes collected; exit 0 | Collection is not execution. |
| Full backend collection | `uv run pytest --collect-only -q` | 7,846 tests collected; exit 0 | Collection is not full test execution. |
| Focused test formatting/lint | `uv run ruff format tests/authorization/project_roles tests/test_authorization.py`; `uv run ruff check ...` | Pass | Does not prove PostgreSQL behavior. |
| Structural debt and assertion custody | `uv run python -m scripts.test_structure_boundary validate --policy ../.ci/auth-boundaries/TEST_STRUCTURE_POLICY.md --ledger ../.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json` | Pass; every assertion from `origin/main` is mapped; touched oversized function debt removed; root file shrinks | Semantic behavior still needs hosted PostgreSQL execution. |
| Markdown links and stale wording | `uv run python ../scripts/check_markdown_links.py`; `uv run python ../scripts/check_stale_workstream_wording.py`; `uv run python ../scripts/check_stale_authorization_docs.py` | Pass; changed Markdown links and stale wording checks clean | None for this test-only change. |
| Database availability | Check `WORKSTREAM_TEST_DATABASE_URL` presence | Not configured in this worktree | No local DB test execution is claimed. |

The first full collection caught a namespace collision from the new nested
`conftest.py`, which shadowed the root `conftest` import used by
`tests/test_database_reset.py`. The local conftest was removed; its fixtures
now live in the project-role fixture owner module and are imported explicitly
by the three test modules. Focused and full collection now pass, including the
database-reset test module.

The existing test function count increases because one mixed behavior was
separated into five focused cases; this is not a target to increase suite size.
Each retained case protects a different PostgreSQL boundary or authority
binding claim. No coverage/count threshold or CI selection changed.

## Risk and verification

- Risk: L1 — authorization and PostgreSQL mutation evidence; test-only change.
- Review: self-review against production route/service behavior, assertion map,
  and exact source ancestry. No product behavior or roadmap claim changes.
- Verification: focused PostgreSQL nodes on hosted CI; local collection,
  structural-debt/map validation, Ruff, stale-wording, Markdown-link, and diff
  checks. Full suite remains a hosted blocking check.
- Human review focus: no real authorization, rollback, invalidation, uniqueness,
  cancellation, or idempotency proof was lost or overstated.

No roadmap update is needed: this changes only the organization and accuracy
of existing AUTH test evidence; it does not change product capability,
exposure, delivered scope, or dependencies.
