# Chunk Contract: WS-XINT-003-02 — Review And Revision Policy Mutation Activation

## Status

Superseded before implementation by `WS-XINT-003-02A` and
`WS-XINT-003-02B`. Current-main plan review proved that immutable policy
versions cannot be introduced safely while Task, Submission, and CheckerRun
still use guide version as policy identity. This record is retained only as the
rejected combined design input and is not an implementation path.

## Goal

Implement one immutable/versioned policy persistence path and authorize the two
covered-project policy mutation routes through the existing PREP protocol.

## Risk class

L1 policy and authorization mutation.

## Allowed files

```text
backend/app/api/router.py
backend/app/modules/projects/models.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/app/modules/projects/policy_mutation_replay_repository.py
backend/app/modules/projects/policy_mutation_service.py
backend/app/modules/projects/policy_mutation_router.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/alembic/versions/0046_review_revision_policy_authority.py
backend/tests/test_authorization.py
backend/tests/test_project_policy_mutations.py
backend/tests/test_projects.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
docs/spec_review_lifecycle.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-12D2-guide-bound-policy-mutations.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/chunks/WS-REV-001-03P-review-revision-policy-persistence.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/STATUS.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/REVIEW_LOG.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/chunks/WS-XINT-003-02-policy-mutation-activation.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/reviews/WS-XINT-003-02-preimplementation-review.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/reviews/WS-XINT-003-02-internal-review.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/reviews/WS-XINT-003-02-pr-trust-bundle.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/reviews/WS-XINT-003-02-external-review-response.md
```

The dedicated policy mutation router/service and replay-only repository follow
the existing project-create and guide-mutation boundaries. The replay
repository may touch only the policy-mutation idempotency ledger and must not
read, insert, update, or delete `ReviewPolicy` or `RevisionPolicy` rows.
`ProjectRepository.add_review_policy_version()` and
`add_revision_policy_version()` are the only policy-table write primitives;
its policy read/lock/append methods remain internal and are not an independently
callable authorization path.

AUTH edits are limited to activating these two existing ActionIds and enforcing
their already-typed resource contexts through the existing PREP protocol. This
chunk may not reshape the general kernel, prepared-capability protocol, or any
unrelated action evaluator.

## Not allowed

Queue, lease, Review, finding, revision execution, artifact, CON, adjudication,
reputation, frontend, duplicate policy tables, or legacy writer compatibility.

## Acceptance criteria

- Only a covered Project Manager with the exact project grant may update the
  review or revision policy for that project and guide lineage.
- The actions remain distinct: `project.review_policy.update` and
  `project.revision_policy.update`.
- Final PREP consumption binds actor/link/grant, project, guide/version,
  existing/reserved policy identity, operation, request digest, idempotency,
  session, transaction, and server-validated policy facts.
- Cross-project, stale guide, wrong policy/action, revoked, replayed, copied, or
  concurrent changed requests deny with no policy/audit partial state.
- The previous embedded or duplicate writer path is removed without backward
  compatibility.
- No review lifecycle action is activated.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL="$WORKSTREAM_TEST_ADMIN_DATABASE_URL" \
  .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json .ci/xint-003-02-focused.json --lane xint_003_02 \
  -- .venv/bin/pytest -q tests/test_authorization.py \
  tests/test_project_policy_mutations.py tests/test_projects.py tests/test_alembic.py)
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

PostgreSQL tests must cover migration upgrade, downgrade/re-upgrade, direct SQL
update/delete refusal, crossed replacements, rollback, stale authority and
policy lineage, and exactly-once replay. GitHub `Backend / test` supplies the
repository-wide 78-percent full-suite gate; materially changed policy-mutation
files must remain at or above 90 percent. `Agent Gates / agent-gates` and
CodeRabbit must pass on the exact final PR head.

## Required reviewers

Architecture, security/auth, product/operations, QA/test, senior engineering,
reuse/dedup, docs, test-delta, and CI integrity.

## Human review focus

Confirm the sole writer path, immutable-version semantics, exact Project
Manager/project/guide binding, active-guide freeze, no compatibility path, and
absence of review-lifecycle activation.

## Stop condition

Merge and stop before queue/lease activation.
