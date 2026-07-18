# Chunk Contract: WS-REV-001-08 - Pure Decision, Final Acceptance, And Task-Effect Contract

## Goal

Freeze pure request schemas, canonical hashing/idempotency inputs, final-fact
validation, typed task effects, and the two ordered CON operation inputs. Add no
repository mutation, AUTH evidence staging, Review, FinalAcceptance, route, or
commit-capable orchestration.

## Risk class

L1 canonical judgment contract.

## Preconditions

07B merged; exact current Review/lease/packet/finding/evidence schema; exact
current task and CON participant protocols; separate human start and plan review.

## Allowed scope

Only pure review schemas/validators/hash inputs, task-owned typed effect input
protocols, CON operation input protocols/fakes, focused pure tests, initiative
artifacts, and this chunk's single merge intent. The current-main start contract
must enumerate exact files before implementation.

## Not allowed

```text
AUTH prepare/evaluate/evidence calls
repository/model/migration/audit/outbox writes
Review, finding, resolution, FinalAcceptance, queue, lease, task, or assignment mutation
public/hidden route or service capable of committing a canonical decision
optional/no-op CON participant, ART call, contribution/award/reputation policy
```

## Acceptance criteria

- Decision values are exactly accept, needs_revision, reject. Findings use the
  canonical blocking/advisory rules; later resolutions remain append-only.
- Canonical request hash/idempotency input binds actor-reference kind/ID, action,
  lease, Submission, packet manifest, payload, and client key using the existing
  `canonical_json_hash` convention.
- Pure final-fact validation accepts exact canonical human reviewer/lease,
  reviewer grant, no-self-review, unexpired lease, open queue, task/assignment,
  Submission, packet/evidence, predecessor, and immutable lineage facts. It
  performs no database or external I/O.
- `TaskReviewEffectsInput` expresses exact branch effects against
  `Submission.task_assignment_id`: accept completes it/task; needs_revision
  retains it and carries typed human `RevisionOriginFacts`; reject blocks it and
  rejects task. No moving current assignment is inferred.
- CON reviewer operation input contains exact future Review, ReviewLease,
  reviewer, reviewer policy freeze, and stabilized lineage. CON submitter input
  contains exact future FinalAcceptance, TaskAssignment, submitter, assignment
  policy freeze, and the same lineage. Neither is nullable/omnibus.
- Pure choreography proves reviewer operation precedes every branch and
  submitter operation exists only after accept produces FinalAcceptance.
- No interface allows FinalAcceptance manual creation or separate authorization.
- Chunk 10 remains the first caller of AUTH prepared mutation and the first code
  capable of appending/committing Review, findings/resolutions,
  FinalAcceptance, task effects, CON rows, audit, or outbox.

## Verification

```text
cd backend && .venv/bin/python -m pytest -q tests/test_reviews.py tests/test_tasks.py tests/test_contributions.py
cd backend && .venv/bin/ruff check app/modules/reviews app/modules/tasks tests/test_reviews.py tests/test_tasks.py tests/test_contributions.py
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78)
cd backend && .venv/bin/coverage report --include='app/modules/reviews/*' --precision=2 --fail-under=90
cd backend && .venv/bin/coverage report --include='app/modules/tasks/*' --precision=2 --fail-under=90
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_review_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_internal_review_evidence.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 backend/.venv/bin/python scripts/test_agent_gates.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
git diff --check
```

The current-main start contract must preserve these gates and may only narrow
focused paths to the exact allowed-file manifest it approves.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
reuse/dedup, docs, and test-delta.

## Stop condition

Merge, record automated memory, and stop. Do not start 02A2 automatically.
