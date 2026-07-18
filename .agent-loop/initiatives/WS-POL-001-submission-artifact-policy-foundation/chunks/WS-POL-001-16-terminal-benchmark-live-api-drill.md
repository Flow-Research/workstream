# Chunk Contract: WS-POL-001-16 - Terminal Benchmark Live API Drill

## Parent Initiative

`WS-POL-001` - Submission Artifact Policy Foundation

## Problem Being Solved

The current system has passed automated API drills and an accepted no-DB
Terminal Benchmark proof, but the next confidence step is a human-visible live
drill that walks the Terminal Benchmark project through Workstream one API call
at a time.

The drill must show lifecycle-critical request/response facts, agent inputs,
agent outputs, setup status, task context, pre-submit feedback, submission
creation, finalization, checker runs, and audit state through HTTP-visible
APIs. It must not rely on database inspection as proof.

## Why This Work Matters

The Terminal Benchmark project is the real-world pressure test that exposed
several architectural and implementation gaps. Running it slowly through the
public/operator APIs proves that project guide setup, derived submission
artifact policy, compiled project pre-submit checker policy, task locked
context, and submission intake are understandable without inspecting Postgres.

## Goal

Run a real Terminal Benchmark live API drill from project setup through
pre-submit and submission finalization, using HTTP-visible state and actual
Terminal Benchmark guide material.

This chunk is drill/evidence-only unless the contract is explicitly amended
after a blocker is found. If runtime behavior blocks the drill, stop with a
concrete finding instead of broadening implementation scope silently.

## Target Behavior

- Project setup starts from actual Terminal Benchmark guide/source material.
- Guide/source material is captured as an immutable source snapshot.
- Automatic setup runs sufficiency first, then policy derivation, then project
  pre-submit checker compilation.
- Project setup outputs are visible through setup-run, sufficiency report,
  submission artifact policy, effective policy, and pre-submit checker policy
  APIs.
- Task work context and submission requirements are visible through APIs.
- Pre-submit checker feedback is visible before submission creation and is not
  authoritative persistence.
- Blocking pre-submit failures prevent submission creation and return
  `pre_submission_checker_failed`.
- Successful submission creation and finalization move the task into the
  expected async checker/evaluation path.
- Durable checker-run and audit evidence is visible through APIs.

## Boundaries Preserved

- This is not a Terminal Benchmark product fork.
- Workstream remains project-scoped: one project guide, one effective project
  submission artifact policy, and one compiled project pre-submit checker
  policy reused by tasks.
- No task-specific checker generation is introduced.
- No database inspection is accepted as lifecycle proof.
- No new script is introduced for the live drill. Existing scripts may be read
  for endpoint discovery, but the human-visible drill uses direct HTTP calls.
- No backward compatibility layer is added for removed legacy request fields.
- No Workstream-owned login, signup, passwords, API-key auth, or primary auth
  sessions are added.

## Credential Boundary

- No production or shared credentials are used for this drill.
- The OpenAI API key may be read only from the local environment for the
  non-production agent call.
- Auth headers, bearer tokens, API keys, environment values, token-shaped
  values, signed URLs, query credentials, and local secret paths must never be
  committed, printed in evidence, or included in request/response transcripts.
- Evidence must redact credential-shaped values as `<redacted>`.
- Public PR evidence must also redact local source-material fingerprints when
  the fixture comes from private operator material. This includes exact fixture
  ids, local database UUIDs, exact source-material hashes, exact package hashes,
  exact artifact byte counts, and source-specific task identifiers. The
  evidence must state this boundary clearly and must not replace sensitive
  values with plausible fake literals.

## Authorization Boundary

- HTTP calls use local verified Flow-compatible bearer actors only.
- Project setup, policy approval, guide activation, locked-context operator
  reads, checker-run operator reads, and audit-event operator reads keep current
  `admin` / `project_manager` object-level rules.
- Worker-facing calls remain assigned-worker scoped.
- The pre-review system actor cannot authorize HTTP requests and cannot be
  supplied by a client.
- This chunk must not change auth defaults, dev-auth production guards, token
  verification, route-level roles, or object-level visibility.

## Risk Class

L1

## SLA

P1

## Work Type

Live API drill, backend/API correctness, project setup visibility, checker
intake proof.

## Depends On

`WS-POL-001-15`

## Allowed Files

```text
docs/roadmap_status.md
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/STATUS.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-16-terminal-benchmark-live-api-drill.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-live-api-drill-evidence.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-live-api-drill-report.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-live-api-drill-report.pdf
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-internal-review-evidence.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-pr-trust-bundle.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-external-review-response.md
```

## Privacy Scrub Amendment

After human review identified that earlier evidence and the standalone example
still exposed private/local source identifiers, this chunk permits a bounded
privacy scrub in addition to the original drill evidence scope.

Additional files allowed only for this scrub:

```text
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/reviews/WS-ENG-001-post-merge-loop-memory-internal-review-evidence.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/CHUNK_MAP.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/STATUS.md
examples/terminal_benchmark/README.md
examples/terminal_benchmark/LOCAL_VALIDATION_NOTES.md
examples/terminal_benchmark/terminal_benchmark_api_e2e.py
docs/review_closure.md
docs/review_process_baseline_operations_review.md
docs/review_process_pattern_baseline_review.md
docs/review_systems_architecture_review.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-06-terminal-benchmark-real-fixture-drill.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-06-internal-review-evidence.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-06-pr-trust-bundle.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-09-internal-review-evidence.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-14-external-review-response.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-14-internal-review-evidence.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-14-pr-trust-bundle.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-15-internal-review-evidence.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-15-pr-trust-bundle.md
```

This amendment does not allow backend, API, migration, test, CI, auth,
payment, reputation, or product behavior changes.

## Not Allowed

```text
backend/alembic/versions/**
backend/app/**
backend/tests/**
backend/scripts/**
examples/terminal_benchmark/** except the privacy-scrub files listed above
backend/app/adapters/auth/**
backend/app/adapters/project_agents/openai_agent_sdk.py
backend/app/core/config.py
backend/app/modules/actors/**
frontend or demo UI work
payment/reputation/blockchain settlement
new agent runtime providers
task-specific checker generation
DB-only drill proof
compatibility aliases for removed legacy fields
public API/schema behavior changes without a new approved implementation chunk
```

## Acceptance Criteria

- The chunk records the Terminal Benchmark source-material flow used for the
  project guide/source snapshot using sanitized durable refs and
  relative/public-safe labels. Because the source fixture came from private
  local operator material, public PR evidence must redact exact fixture ids,
  local database UUIDs, source-material hashes, package hashes, artifact byte
  counts, and source-specific task identifiers.
- Persisted snapshots and review evidence contain no raw local filesystem
  paths, signed URLs, credential-bearing refs, token-bearing refs, or unsafe
  source refs.
- Redacted fields in public evidence use explicit placeholders such as
  `<redacted-id>`, `<redacted-fixture-id>`, `<redacted-run-id>`, and
  `sha256:<redacted>`; they must not be presented as literal replayable API
  values.
- The drill report shows the human-review API path at professional summary
  level, with lifecycle-critical request/response facts preserved and
  credentials, local secret paths, raw ids, exact source hashes, exact byte
  counts, and source-specific identifiers redacted.
- The drill shows sufficiency-agent input and output.
- The drill shows submission-policy-derivation input and output.
- The drill shows setup-run status, sufficiency result, warning
  acknowledgement when applicable, policy approval, compiled checker policy
  visibility, and guide activation as API request/response evidence.
- The drill shows the compiled project pre-submit checker policy summary and
  hash through API response.
- The drill creates a task using the current task contract without legacy
  artifact/evidence request fields.
- The drill shows task work context, worker submission requirements, and
  operator locked context through APIs.
- The drill proves preflight returns `PreSubmitCheckResponse` with `status`,
  `eligible_to_submit`, structured pass/fail/warning details,
  `authoritative: false`, and no `accept`, `needs_revision`, or `reject`
  decision leakage.
- The drill proves a blocked pre-submit path creates no submission using
  HTTP-visible evidence: failed create response, unchanged/empty task
  submission list, and audit-event response. Because checker-run visibility is
  submission-scoped, blocked intake with no submission id must explicitly note
  that no checker-run list endpoint is valid before a submission exists.
- The drill proves a successful pre-submit path is non-authoritative and then a
  submission-create call creates the durable submission.
- The drill finalizes the submission and shows checker-run and audit visibility
  through APIs.
- Workstream default checker set and hard rules remain unchanged. If a drill
  blocker appears to require weakening hash, storage-ref, forbidden-artifact, or
  default-checker behavior, this chunk stops for a new human-approved contract.
- Any blocker found during the drill is explicitly stopped with a concrete
  finding unless a new approved contract amends the allowed implementation
  scope.

## Live Drill Evidence

The formal live-drill evidence must be committed as a concise evidence index
plus a professional PDF report and source Markdown:

```text
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-live-api-drill-evidence.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-live-api-drill-report.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-live-api-drill-report.pdf
```

The report may be professional summary evidence rather than a raw committed
request/response-body transcript. It must still preserve enough lifecycle facts
for a human reviewer to verify setup, policy derivation, checker compilation,
blocked intake, successful intake, checker-run visibility, audit flow, and final
task state without database inspection.

Required sections:

- local stack and environment summary, with secret values redacted
- source-material manifest with sanitized durable refs and relative/public-safe
  labels; public evidence must redact exact content hashes, exact fixture ids,
  local UUIDs, and exact byte counts when they fingerprint private local source
  material
- ordered API lifecycle index for project creation, guide creation, source
  snapshot capture, setup-run polling, sufficiency result, warning
  acknowledgement when applicable, derived policy visibility, policy approval,
  effective policy visibility, pre-submit checker policy visibility, guide
  activation, task creation, task screening/release/claim/start, work context,
  submission requirements, locked context, blocked pre-submit, blocked create,
  submission-list no-side-effect proof, successful pre-submit, successful
  submission create, finalize, checker-run list/get, and task audit events
- sufficiency-agent input and output
- submission-policy-derivation input and output
- explicit no-DB proof notes for every lifecycle assertion
- blocker notes and stop decision if any step cannot proceed
- PDF metadata, page count, and SHA-256 recorded in the evidence index

## Verification Commands

```bash
cd backend && .venv/bin/pytest tests/test_projects.py tests/test_tasks.py tests/test_checkers.py -q
cd backend && WORKSTREAM_DATABASE_URL=<local-test-db-url> .venv/bin/python scripts/api_contract_e2e.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
INTERNAL_REVIEW_CHUNK_ID=WS-POL-001-16-terminal-benchmark-live-api-drill python3 scripts/check_internal_review_evidence.py
```

Live drill verification is direct HTTP execution against local FastAPI,
Postgres, Celery, and Redis. Database access is allowed for migration reset and
cleanup only, not for proving lifecycle state.

The live drill must follow the ordered lifecycle checklist in the Live Drill
Evidence section and must commit the completed evidence artifacts before the
chunk can be reviewed.

## Required Reviewers

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

## Human Review Focus

- Whether the API drill is genuinely understandable without DB inspection.
- Whether Terminal Benchmark guide material flows into setup without invented
  fake project-guide fields.
- Whether agent-derived policy and compiled checker output are visible and
  project-scoped.
- Whether pre-submit failure, submission creation, finalization, checker-run,
  and audit evidence match the intended lifecycle.

## Stop Conditions

- Stop if the live drill requires database inspection for lifecycle proof.
- Stop if project setup cannot use actual Terminal Benchmark guide material.
- Stop if a fix requires weakening Workstream default checker policy.
- Stop if a fix requires adding task-specific checker generation.
- Stop if secrets or production credentials are required.
