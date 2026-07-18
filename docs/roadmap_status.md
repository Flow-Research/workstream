# Workstream Roadmap Status

Current phase: WS-AUTH-001 authorization foundation before further lifecycle
expansion.

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
- Compensation and reputation.
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
- Chunk 3 project guide foundation with checker, review, and revision policy
  context; compensation is superseded by the independent WS-CON contract.
- Chunk 4 task queue, contributor/reviewer profiles, assignment, claim, start, and task audit events.
- Chunk 5 submission packet foundation with evidence items, versioning, server-stamped locked context, and submission finalization.
- Backend API contract drill through `Project -> Guide -> Task -> Screening -> Ready -> Claim -> Start -> Submit -> automatic pre-review gate`.
- Week 2 checker framework scope specification.
- Chunk 6 checker contract and records specification.
- Chunk 7 checker runner, registry, structural checkers, durable checker records, and API tests.
- Chunk 8 evidence, policy, forbidden-file, confidentiality, and generated-artifact checkers.
- Chunk 9 automatic pre-review gate with pre-submit intake blocking, internal `task_setup_blocked`, trusted checker retry, and contributor redaction.
- Chunk 10 checker trial with the expanded real API sample matrix, failure catalog, false-positive notes, missing-checker notes, and internal verifier evidence.
- Week 2 real HTTP API drill through Flow-token auth, project/guide/task/submission lifecycle, pre-submit checks, automatic checker runs, `pre_submission_checker_failed` intake failures, contributor redaction, internal `task_setup_blocked`, and trusted checker retry.
- Chunk 11 actor identity/profile registry for verified Flow actors.
- Chunk 12 project setup-run and project policy visibility APIs for setup runs, sufficiency reports, submission artifact policies, effective policy, and compiled project pre-submit checker policy.
- Chunk 13 task work-context, contributor submission-requirements, and operator-only locked-context APIs.
- Chunk 14 submission finalization, system actor pre-review gate audit semantics, scoped operator visibility, and HTTP-visible Terminal Benchmark proof.
- Chunk 15 agent-derivation hardening after the accepted no-DB Terminal Benchmark drill exposed a required/forbidden self-conflict.
- Chunk 16 Terminal Benchmark live API drill with privacy-scrubbed evidence and
  professional PDF report proving the current lifecycle through HTTP-visible
  APIs without database inspection.
- WS-POL-002 post-submit checker foundation planning, including project-scoped
  `PostSubmitCheckerPolicy` setup, trusted compiler boundaries, deterministic
  runtime separation, and implementation chunk contracts.
- WS-AUTH-001 planning and post-merge memory through PRs #91 and #92, including
  the adopted external-auth/local-authorization boundary and 16 bounded chunks.

## Current Priority

- `WS-AUTH-001-01` adopts ADR 0012, canonical `/api/v1` authorization
  documentation, operational ownership, and deterministic stale-doc gates.
- Token roles and typed workflow profiles are not the target product authority;
  later chunks introduce canonical actors, links, grants, permissions,
  revocation, and authority evidence before resource-family cutover.
- WS-POL-002-03 is handled separately by PR #90. No WS-POL-002-04 or human
  review implementation starts automatically while authorization has priority.

## Review Tracks Closed

- Product strategy.
- Architecture.
- Systems architecture.
- Operations and review workflow.
- Process-pattern baseline.
- Adversarial quality.
- Chunk 9 pre-review gate internal verifier pass.
- Chunk 10 checker trial internal verifier pass.

## Preserved For Later Review Work

- Review queue scope starts only after the required authorization foundation;
  it will consume `review_pending` tasks that already passed internal checkers.
- Reviewer access must be object-level and tied to assigned review work; broad reviewer checker-run access is still intentionally deferred.
- Week 3 must keep review decisions canonical: `accept`, `needs_revision`, and `reject`.
- `needs_revision` from human review must carry `outcome_source = human_review` and a review decision id; checker-caused `needs_revision` keeps `outcome_source = auto_checker`.
- Review findings, revision replay, and reviewer-quality metrics remain later
  backend contracts after authorization proof.
- `WS-POL-001-15` hardened the agent-derived submission artifact policy
  contract after the accepted no-DB Terminal Benchmark drill exposed a
  required/forbidden self-conflict; the drill now passes after hardening.
- `WS-POL-001-16` completed a human-visible Terminal Benchmark live API drill
  without database inspection as lifecycle proof and merged through PR #84.
- `WS-POL-002` planning and chunks 01/02 are merged. Chunk 03 is handled in PR
  #90; chunk 04 remains inactive while authorization has priority.

## Pending Before Pilot

- Create the first pilot project guide from the template.
- Create the first 5 pilot task records.
- Confirm who owns product, engineering, review, operations, and compensation
  fulfillment reconciliation during the first build cycle.
- Confirm the first v0.1 project guide uses the locked guide fields, task contract fields, evidence IDs, and contribution record flow.

## Backend API Contract Drill

Run from the backend directory against local Postgres:

```bash
WORKSTREAM_DATABASE_URL=<local-test-db-url> .venv/bin/python scripts/api_contract_e2e.py
```

The script runs migrations forward and exercises project policy visibility plus task context APIs across the following flow:

`Project -> Guide -> Task -> Screening -> Ready -> Work context -> Submission requirements -> Locked context -> Claim -> Start -> Submit -> automatic pre-review gate`

## Week 2 Real API Drill

Run from the backend directory against local Postgres:

```bash
WORKSTREAM_DATABASE_URL=<local-test-db-url> .venv/bin/python scripts/week2_api_e2e.py
```

The script starts a real local API server, issues local Flow-compatible tokens,
runs migrations forward, and exercises:

`Project -> Guide -> Task -> Screening -> Ready -> Claim -> Start -> Pre-submit checks -> pre_submission_checker_failed | Submit -> automatic lock -> evaluation_pending -> review_pending | checker_caused_revision -> needs_revision -> fixed_resubmission -> evaluation_pending -> review_pending | internal task_setup_blocked -> trusted checker retry`

It also proves older submissions remain immutable, non-owning contributor calls create
no task-side effects, malicious internal fields are rejected before persistence,
and checker-caused `needs_revision` creates no human review decision.

## Deterministic Week 2 Closeout Gate

The Week 2 closeout gate is deterministic and must fail on contract drift.

Required invariants:

- Real API drills run only against local `postgresql+asyncpg://` test databases named `workstream_test` or `test_workstream` unless an explicit write-risk override is supplied.
- Pre-submit checker responses are non-authoritative preflight feedback; submission creation is the authoritative intake gate and must not create submissions, checker runs, or lifecycle transitions when blocking failures exist.
- Missing or unexpected pre-submit checker names fail the drill.
- Missing or unexpected durable checker names fail the drill.
- Submission creation returns `finalized_at`, stamps evidence rows, and the
  repair-only finalize endpoint is idempotent.
- Automatic checker-run creation, checker terminal status, and task-status transitions are polled because execution is async-first.
- Checker-run list visibility is checked for project manager, assigned contributor, unassigned contributor, and reviewer denial while broad reviewer checker-run access remains deferred.
- Trusted checker retry proves attempt ordering, supersession, and current-run flags.
- API-visible invariants are checked after the real API flows for locked guide/policy context, evidence finalization, checker results, checker counters, current-run uniqueness, and gate audit events. The legacy Week 2 regression script still includes direct database assertions; the accepted no-DB proof is the API contract drill plus the Terminal Benchmark API drill.

Week 2 closeout validation is not only this script. The full gate is:

```bash
.venv/bin/python -m ruff check app tests scripts
WORKSTREAM_DATABASE_URL=<local-test-db-url> .venv/bin/python scripts/api_contract_e2e.py
WORKSTREAM_DATABASE_URL=<local-test-db-url> .venv/bin/python scripts/week2_api_e2e.py
WORKSTREAM_DATABASE_URL=<local-test-db-url> .venv/bin/python -m pytest tests/test_checkers.py tests/test_tasks.py -q
WORKSTREAM_DATABASE_URL=<local-test-db-url> .venv/bin/python -m pytest -q
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
