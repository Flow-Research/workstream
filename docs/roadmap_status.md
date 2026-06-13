# Workstream Roadmap Status

Current phase: Week 3 review and revision preparation.

## Completed

- Root README.
- Product principles and product brief.
- First user flows.
- 30-day master plan.
- Day-by-day execution plan.
- Implementation backlog.
- Pilot plan.
- System architecture.
- Data model.
- Lifecycle state machine.
- Checker framework.
- Operator workflow.
- Queue policy.
- Reviewer workflow.
- Revision replay.
- Roles and permissions.
- Payment and reputation.
- Workspace and packet convention.
- Risk register.
- Templates for guides, tasks, submissions, reviews, checkers, revision replay, and prior feedback.
- Decision records.
- Independent review passes.
- Review closure record.
- June 3 architecture proposal preserved and reconciled.
- Architecture lockdown note.
- Week 1 backend chunk plan.
- Chunk 1 backend scaffold.
- Chunk 2 external Flow auth actor boundary.
- Chunk 3 project guide foundation with checker, review, revision, and payment policy context.
- Chunk 4 task queue, worker/reviewer profiles, assignment, claim, start, and task audit events.
- Chunk 5 submission packet foundation with evidence items, versioning, server-stamped locked context, and submission locking.
- Week 1 backend dry run through `Project -> Guide -> Task -> Screening -> Ready -> Claim -> Start -> Submit -> Lock submission`.
- Week 2 checker framework scope specification.
- Chunk 6 checker contract and records specification.
- Chunk 7 checker runner, registry, structural checkers, durable checker records, and API tests.
- Chunk 8 evidence, policy, forbidden-file, confidentiality, and generated-artifact checkers.
- Chunk 9 automatic pre-review gate with checker-caused `needs_revision`, internal `task_setup_blocked`, trusted checker retry, and worker redaction.
- Chunk 10 checker trial with the expanded real API sample matrix, failure catalog, false-positive notes, missing-checker notes, and internal verifier evidence.
- Week 2 real HTTP API drill through Flow-token auth, project/guide/task/submission lifecycle, pre-submit checks, automatic checker runs, checker-caused `needs_revision`, worker redaction, internal `task_setup_blocked`, and trusted checker retry.

## Review Tracks Closed

- Product strategy.
- Architecture.
- Systems architecture.
- Operations and review workflow.
- Process-pattern baseline.
- Adversarial quality.
- Chunk 9 pre-review gate internal verifier pass.
- Chunk 10 checker trial internal verifier pass.

## Ready For Week 3

- Review queue scope can start from `review_pending` tasks that already passed internal checkers.
- Reviewer access must be object-level and tied to assigned review work; broad reviewer checker-run access is still intentionally deferred.
- Week 3 must keep review decisions canonical: `accept`, `needs_revision`, and `reject`.
- `needs_revision` from human review must carry `outcome_source = human_review` and a review decision id; checker-caused `needs_revision` keeps `outcome_source = auto_checker`.
- Review findings, revision replay, and reviewer-quality metrics are the next backend contracts to lock.

## Pending Before Pilot

- Create the first pilot project guide from the template.
- Create the first 5 pilot task records.
- Confirm who owns product, engineering, review, operations, and payment reconciliation during the first build cycle.
- Confirm the first v0.1 project guide uses the locked guide fields, task contract fields, evidence IDs, and contribution record flow.

## Week 1 Dry Run

Run from the backend directory against local Postgres:

```bash
WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/week1_dry_run.py
```

The script runs migrations forward and exercises:

`Project -> Guide -> Task -> Screening -> Ready -> Claim -> Start -> Submit -> Lock submission`

## Week 2 Real API Drill

Run from the backend directory against local Postgres:

```bash
WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/week2_api_e2e.py
```

The script starts a real local API server, issues local Flow-compatible tokens, runs migrations forward, and exercises:

`Project -> Guide -> Task -> Screening -> Ready -> Claim -> Start -> Pre-submit checks -> Submit -> Lock submission -> Automatic checker run -> review_pending | needs_revision | internal task_setup_blocked -> trusted checker retry`

## Deterministic Week 2 Closeout Gate

The Week 2 closeout gate is deterministic and must fail on contract drift.

Required invariants:

- Week 1 and Week 2 real API drills run only against local `postgresql+asyncpg://` test databases named `workstream_test` or `test_workstream` unless an explicit write-risk override is supplied.
- Pre-submit checker responses are non-authoritative and must not create submissions, checker runs, or lifecycle transitions.
- Missing or unexpected pre-submit checker names fail the drill.
- Missing or unexpected durable checker names fail the drill.
- Submission locking returns `locked_at`, locks evidence rows, and is idempotent.
- Automatic checker-run creation, checker terminal status, and task-status transitions are polled because execution is async-first.
- Checker-run list visibility is checked for project manager, assigned worker, unassigned worker, and reviewer roles.
- Trusted checker retry proves attempt ordering, supersession, and current-run flags.
- Postgres invariants are checked after the real API flows for locked guide/policy context, evidence locks, checker results, checker counters, current-run uniqueness, and gate audit events.

Week 2 closeout validation is not only this script. The full gate is:

```bash
.venv/bin/python -m ruff check app tests scripts
WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/week1_api_e2e.py
WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/week2_api_e2e.py
WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_checkers.py tests/test_tasks.py -q
WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest -q
.venv/bin/docstr-coverage --config .docstr.yaml
```

The closeout also requires stale wording scan, Markdown link check, and internal verifier evidence before PR.

## Operating Rule

No roadmap item is considered closed until it is represented in one of:

- product spec
- architecture spec
- operation workflow
- template
- checker rule
- decision record
- review closure
