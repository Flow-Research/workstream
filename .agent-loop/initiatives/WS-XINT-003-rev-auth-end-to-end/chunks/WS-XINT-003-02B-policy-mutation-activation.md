# Chunk Contract: WS-XINT-003-02B — Policy Mutation Activation

## Status

In progress after PR #242 merged 02A and the user explicitly started 02B on
2026-08-02. Refreshed from `origin/main` at merge `6babf81b` before application
code changes and rebased onto `2c24c91d` before external review.

## Goal

Expose the sole review/revision policy writer and activate exactly
`project.review_policy.update` and `project.revision_policy.update` through the
existing opaque, transaction-bound PREP protocol.

## Required boundary

- `ProjectPolicyMutationService` is the sole orchestration path.
- `ProjectRepository.add_review_policy_version()` and
  `add_revision_policy_version()` are the only policy-table writers.
- A replay-only repository may touch only the idempotency ledger.
- Exact committed replay returns the recorded response without new PREP,
  policy write, or allowed evidence, including after later grant/link
  revocation, but only after current authentication proves the same active
  ActorProfile and the replay row matches the actor, action, project, guide,
  idempotency key, and canonical request digest. An idempotency key alone never
  discloses a response. Changed or pending replay conflicts without product
  state.
- Final PREP consumption follows locks on the exact project, draft guide,
  selected current policy, reserved replacement identity, actor/link/grant,
  operation, request digest, session, and transaction.
- The two typed policy PREP contexts bind the operation identity, canonical
  request digest, reserved successor identity and generation, predecessor
  identity and digest (or the explicit no-current sentinel), draft-guide
  status, exact actor/link/grant/project scope, session, and root transaction.
- New versions persist actor, identity link, matched grant, project scope,
  ActionId, decision-event reference, predecessor identity/digest, generation,
  and canonical policy digest atomically with selection advancement.
- Active/stale guide, stale selected policy, revoked authority, copied/wrong
  handle, wrong actor/action/project/guide/policy, replay, and crossed
  replacement races fail with no partial policy or audit state.
- No review lifecycle ActionId or behavior is activated.

## Allowed files

```text
backend/app/api/router.py
backend/app/modules/projects/models.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/policy_lineage.py
backend/app/modules/projects/policy_mutation_replay_repository.py
backend/app/modules/projects/policy_mutation_service.py
backend/app/modules/projects/policy_mutation_router.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/alembic/versions/0048_review_revision_policy_authority.py
backend/tests/test_authorization.py
backend/tests/test_project_policy_mutations.py
backend/tests/test_policy_identity_lineage.py
backend/tests/test_projects.py
backend/tests/test_tasks.py
backend/tests/test_artifact_admission.py
backend/tests/project_create_fixtures.py
backend/tests/test_alembic.py
backend/tests/test_artifact_architecture.py
backend/scripts/api_contract_e2e.py
backend/scripts/run_test_lanes.py
docs/spec_authorization_service.md
docs/spec_review_lifecycle.md
docs/operations_authorization_service.md
docs/operations_roles_permissions.md
docs/operations_project_operating_manual.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-12D2-guide-bound-policy-mutations.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/chunks/WS-REV-001-03P-review-revision-policy-persistence.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/**
```

## Not allowed changes

- Queue, lease, review, finding, decision, or revision-execution behavior.
- Artifact, contribution, compensation, reputation, frontend, or token-verifier
  behavior.
- Compatibility routes, embedded guide policy fields, duplicate policy models,
  alternate writers, generic authorization protocols, or fallback authority.
- Mutation of historical policy versions or rewriting 02A lineage.

## Migration and schema ownership

- `0048_review_revision_policy_authority` follows merged `0047` and adds only
  the replay ledger plus nullable historical provenance/evidence columns needed
  by newly appended complete policy versions.
- Database constraints require each newly appended complete 02B row to carry a
  coherent non-null actor profile, identity link, matched grant, project scope,
  ActionId, decision-event reference, predecessor identity/digest (or the
  explicit first-version marker), generation, and canonical digest. Existing
  legacy rows remain explicitly grandfathered and nullable.
- Existing 02A immutable guards, lineage keys, Task/Submission/CheckerRun locks,
  and policy semantic fields remain authoritative.
- `0048` corrects the 02A draft-setup selector shape so the review selector
  triple and revision selector triple are each independently all-null or
  all-present. This is required because the two policies have separate routes
  and may be attached in either order. The active/superseded-guide constraint
  continues to require both complete selector triples, and partial triples are
  always rejected.
- The replay ledger has one UUID operation identity, action, actor, exact
  project/guide, request digest, state, reserved replacement policy identity,
  and committed response. It cannot be a policy writer.

## API and transaction contract

- `PUT /api/v1/projects/{project_id}/guides/{guide_id}/review-policy` declares
  only `project.review_policy.update`.
- `PUT /api/v1/projects/{project_id}/guides/{guide_id}/revision-policy` declares
  only `project.revision_policy.update`.
- Both require an `Idempotency-Key` UUID and an `If-Match` opaque selector that
  binds the current policy ID, generation, and canonical digest;
  creation requires the exact quoted sentinel `If-Match: "no-current-policy"`,
  never an omitted or wildcard precondition.
- The canonical request digest includes the HTTP method, exact ActionId,
  project ID, guide ID, policy kind, exact `If-Match` selector or no-current sentinel,
  normalized policy semantics, and idempotency operation identity.
- The service owns one root transaction. It checks committed replay before PREP,
  prepares exact Project Manager authority, locks project/guide/current policy
  and replay reservation, validates server-computed semantics/digest, consumes
  PREP, appends one policy, advances the guide selector, stages allowed evidence,
  records the response, and commits once.
- Denial and conflict paths expose bounded errors and create no policy row,
  selector advancement, committed replay, or allowed evidence.
- Denial/conflict audit evidence, when recorded, is limited to action,
  project/guide, reason code, and request digest; it never contains the raw
  request body, policy semantics, or internal error details.

## Acceptance criteria

- Exactly the two policy actions become active; no other action availability or
  permission mapping changes.
- Exact covered-project Project Manager authority is required and revalidated
  against the locked actor, identity link, grant, project, draft guide, current
  selected policy, reserved successor, generation, predecessor digest, request,
  session, and transaction.
- Complete request semantics are normalized through `policy_lineage.py`; the
  server owns the canonical policy digest.
- A successful replacement appends one immutable policy row, records complete
  provenance/evidence, and advances only the matching guide selector atomically.
- A draft guide with neither policy may attach review then revision or revision
  then review; the intermediate state has one complete selector triple. Guide
  activation remains impossible until both complete policies are selected.
- Exact committed replay returns the recorded response without PREP or a new
  allowed event, even after grant/link revocation, only for the same currently
  authenticated active ActorProfile and exact recorded actor/action/project/
  guide/idempotency/request tuple. Pending, changed, crossed, stale, or
  differently authenticated replay conflicts without product mutation.
- Active guide, stale `If-Match`, stale selected policy, cross-project/guide,
  wrong action, copied/replayed/wrong-session/wrong-transaction handle, revoked
  link/grant, and concurrent replacement all fail closed.
- Direct update/delete/truncate remains refused by 02A guards; old mutators and
  embedded guide-policy inputs do not reappear.
- OpenAPI and architecture tests prove one router/service/writer path and exact
  primary actions.

## Verification commands

```bash
(cd backend && .venv/bin/ruff check app tests scripts)
(cd backend && .venv/bin/pytest -q tests/test_artifact_architecture.py)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL="$WORKSTREAM_TEST_ADMIN_DATABASE_URL" \
  .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json .ci/xint-003-02b-focused.json --lane xint_003_02b \
  -- .venv/bin/pytest -q tests/test_authorization.py \
  tests/test_project_policy_mutations.py tests/test_alembic.py)
(cd backend && WORKSTREAM_TEST_DATABASE_URL="$WORKSTREAM_TEST_DATABASE_URL" \
  .venv/bin/pytest -q tests/test_project_policy_mutations.py \
  --cov=app.modules.projects.policy_mutation_replay_repository \
  --cov=app.modules.projects.policy_mutation_service \
  --cov=app.modules.projects.policy_mutation_router \
  --cov-report=term-missing --cov-fail-under=90)
(cd backend && .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

GitHub `Backend / test`, `Agent Gates / agent-gates`, and CodeRabbit must pass
on the exact final head. No local full-suite run is required.

## Required reviewers

Architecture, security/auth, product/operations, QA/test, senior engineering,
reuse/dedup, docs, test-delta, and CI integrity.

## Human review focus

The sole writer path, exact Project Manager/project/guide/policy binding,
append-only semantics, replay-before-PREP behavior, atomic provenance/evidence,
active-guide freeze, and absence of review-lifecycle activation.

## Risk, review, and stop

L1. Require all named reviewers, hosted full coverage, CodeRabbit, and human
merge. Merge and stop before 03A.
