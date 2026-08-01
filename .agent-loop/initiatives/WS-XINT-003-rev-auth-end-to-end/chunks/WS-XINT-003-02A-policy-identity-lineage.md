# Chunk Contract: WS-XINT-003-02A — Immutable Policy Identity And Lineage

## Status

Implementation-ready candidate refreshed from `main` at `ad8da7e5`. Runtime
edits require L1 plan-review PASS. The user's start of parent 02 authorizes this
first child only; 02B does not begin automatically.

## Goal

Make the existing ReviewPolicy and RevisionPolicy tables express immutable,
append-only versions and make ProjectGuide, Task, Submission, and CheckerRun
lock exact policy identity instead of treating guide version as policy version.
No public mutation route or authorization action becomes available.

## Risk class

L1 policy identity and cross-subsystem data lineage.

## Allowed files

```text
backend/app/modules/projects/models.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/app/modules/projects/authorization_reads.py
backend/app/modules/projects/policy_lineage.py
backend/app/modules/tasks/models.py
backend/app/modules/tasks/repository.py
backend/app/modules/tasks/schemas.py
backend/app/modules/tasks/service.py
backend/app/modules/checkers/models.py
backend/app/modules/checkers/schemas.py
backend/app/modules/checkers/service.py
backend/app/modules/checkers/runner.py
backend/alembic/versions/0046_immutable_review_revision_policy_lineage.py
backend/tests/test_projects.py
backend/tests/test_tasks.py
backend/tests/test_checkers.py
backend/tests/test_alembic.py
backend/tests/test_artifact_admission.py
backend/tests/test_policy_identity_lineage.py
docs/spec_review_lifecycle.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-12D2-guide-bound-policy-mutations.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/chunks/WS-REV-001-03P-review-revision-policy-persistence.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/CHUNK_MAP.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/PLAN.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/STATUS.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/ACTION_CUSTODY.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/REVIEW_LOG.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/chunks/WS-XINT-003-02-policy-mutation-activation.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/chunks/WS-XINT-003-02A-policy-identity-lineage.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/chunks/WS-XINT-003-02B-policy-mutation-activation.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/reviews/WS-XINT-003-02A-preimplementation-review.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/reviews/WS-XINT-003-02A-internal-review.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/reviews/WS-XINT-003-02A-pr-trust-bundle.md
```

## Not allowed

Public policy mutation routes, ActionId activation, PREP consumption, grants,
queue/lease/Review/finding/revision execution, ART behavior, CON, payment,
reputation, frontend, duplicate policy tables, inferred lease/preference values,
or compatibility aliases for guide-version-as-policy-version fields.

## Acceptance criteria

- Existing `ReviewPolicy` and `RevisionPolicy` tables become immutable
  multi-version records for one exact ProjectGuide; no duplicate policy table
  or mutable current-row path exists.
- ProjectGuide selects the exact current review-policy and revision-policy row.
  Draft selection may advance only through the later 02B writer; activation
  freezes the selected identities. Existing guides with unambiguous policy rows
  are backfilled to those exact IDs. A new draft created between 02A and 02B has
  nullable selections, and policy readiness/activation fails closed until 02B
  installs complete selected versions; 02A does not modify the guide writer.
- Review policy types explicitly represent positive preference-window and
  lease-duration values, capacity fixed to one in v0.1,
  `self_review_allowed = false`,
  close-task rejection, finding-evidence requirement, and allowed decisions.
  None is inferred from legacy `sla_hours`.
- Revision policy explicitly represents positive revision limit and deadline
  semantics and the permitted resubmission/reassignment rules. Reaching a limit
  or deadline blocks preparation; it never auto-rejects or auto-closes a Task.
  The legacy `auto_reject_after_limit` field is removed from model, schema, and
  storage with no compatibility alias, and its historical value is not treated
  as lifecycle authority.
- Task locks exact review/revision policy IDs plus immutable generation/digest;
  Submission and CheckerRun copy and FK-chain those exact facts. Guide version
  remains guide lineage only and is not a policy identifier.
- Historical rows migrate deterministically without inventing lease/preference
  meaning. Storage distinguishes `complete` policy semantics from typed
  `legacy_incomplete` rows: complete rows require positive preference/lease and
  revision values, while migrated missing values remain nullable only on
  `legacy_incomplete` rows. Incomplete rows remain readable but the canonical
  lineage/readiness predicate must reject them for future review activation.
- PostgreSQL rejects policy update/delete/truncate and rejects any mismatch
  across project, guide, selected policy, Task, Submission, or CheckerRun.
- All existing task/submission/checker behavior remains otherwise unchanged,
  and both policy mutation ActionIds remain planned/unavailable.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && install -d -m 700 .ci/xint-003-02a && \
  WORKSTREAM_TEST_ADMIN_DATABASE_URL="$WORKSTREAM_TEST_ADMIN_DATABASE_URL" \
  .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json .ci/xint-003-02a/focused.json --lane xint_003_02a \
  -- .venv/bin/pytest -q tests/test_policy_identity_lineage.py \
  tests/test_alembic.py -k xint003_02a)
(cd backend && install -d -m 700 .ci/xint-003-02a && \
  WORKSTREAM_TEST_ADMIN_DATABASE_URL="$WORKSTREAM_TEST_ADMIN_DATABASE_URL" \
  .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json .ci/xint-003-02a/coverage.json --lane xint_003_02a_coverage \
  -- .venv/bin/pytest -q tests/test_policy_identity_lineage.py \
  --cov=app.modules.projects.policy_lineage --cov-branch \
  --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_review_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

The named tests must cover migration upgrade, downgrade/re-upgrade, historical
backfill, update/delete/truncate refusal, exact ProjectGuide/Task/Submission/
CheckerRun lineage, rollback, and both actions remaining unavailable. Focused
tests in both named files must use `xint003_02a` in their test node names so the
required keyword selection cannot silently omit new proof. They must include a
migrated incomplete-policy case proving the row remains readable and explicitly
marked `legacy_incomplete` while the canonical readiness predicate denies its
use. Focused
project/task/checker regression selections may be added by exact test node ID as
implementation reveals affected existing cases; they may not expand the
allowed test files. GitHub `Backend / test` supplies the repository-wide
78-percent suite and coverage gate and must demonstrate that materially changed
existing subsystems do not regress. Agent Gates and CodeRabbit must pass on the
exact final head.

## Required reviewers

Architecture, security/auth, product/operations, QA/test, senior engineering,
reuse/dedup, docs, test-delta, and CI integrity.

## Human review focus

Exact policy identity, safe historical migration, no invented policy semantics,
downstream lock stability, database immutability, and zero runtime activation.

## Stop condition

Merge and stop before 02B mutation activation.
