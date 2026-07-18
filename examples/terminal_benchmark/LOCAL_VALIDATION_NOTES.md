# Terminal Benchmark Real API Drill Local Validation Notes

This file records local validation notes for the Terminal Benchmark example
drill. It is not Workstream internal-review evidence for a product chunk and
does not make this example part of required CI.

Date: 2026-06-15

Example scope:

- `examples/terminal_benchmark/terminal_benchmark_api_e2e.py`
- historical local checker revision experiment, not included in this example
- historical local checker tests, not included in this example

Purpose:

This historical note covered the earlier Terminal Benchmark API drill shape:

- project and active guide creation
- task screening, release, claim, and start
- pre-submit checker feedback for intake
- submission packet creation
- submission finalization
- automatic durable checker gate
- `review_pending`
- `needs_revision`
- fixed resubmission from revision state

## Local Observations

Engineering observations:

- The default fixture path was private/local, and ambiguous fixture file
  selection could hide mixed artifacts.
- The pre-submit checker set and persisted fixture artifact/evidence contract
  were under-asserted.
- The example now requires an explicit `WORKSTREAM_TERMINAL_BENCH_FIXTURE`,
  fails on ambiguous fixture matches, and asserts pre-submit checker set,
  artifact manifest, evidence rows, hashes, sizes, labels, checker statuses,
  and checker counts.

QA observations:

- Successful pre-submit non-durability and exact checker result counts were not
  proven in the first local draft.
- The fixed revision packet skipped pre-submit feedback in the first local draft.
- The example asserts no durable submissions are created by pre-submit checks,
  exact run counters and statuses match expectations, and the fixed revision
  packet runs pre-submit feedback before v2 submission.

Security observations:

- An inherited non-local database override could allow writes outside local test
  Postgres.
- Fixture paths could leak through persisted identifiers or normal success
  output.
- The example uses a strict local-only Postgres guard, derives a stable fixture
  id from content hashes, persists sanitized fixture identifiers, and normal
  success output does not print the absolute fixture path.

Product/ops observations:

- Worker profile setup needed to use the canonical profile workflow.
- Locked wording used time-relative and external-tool-specific phrasing.
- The drill now uses `POST /api/v1/workers/me/profile`, output includes
  `worker_profile_setup=canonical_worker_profile_api`, and guide/submission
  wording uses stable Terminal Benchmark fixture language.

## Validations

Commands run:

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && .venv/bin/docstr-coverage app scripts --config .docstr.yaml
git diff --check
cd backend && .venv/bin/python -m pytest tests/test_checkers.py -k 'pre_submit_check_allows_worker_revision_packet_feedback or pre_submit_check_returns_feedback_without_durable_run'
cd backend && WORKSTREAM_DATABASE_URL=<local-test-db-url> WORKSTREAM_TERMINAL_BENCH_FIXTURE=<redacted-local-fixture-path> .venv/bin/python ../examples/terminal_benchmark/terminal_benchmark_api_e2e.py
cd backend && .venv/bin/python -m pytest
```

Results:

- ruff passed
- docstring coverage passed at 100.0%
- diff whitespace check passed
- targeted checker tests passed: 2 passed
- Terminal Benchmark real API drill passed
- full backend pytest passed: 115 passed

These notes are historical local validation notes only. They do not certify any
future chunk and do not replace required internal reviewer evidence.

## Manual Policy-Bundle Proof Note

Date: 2026-07-05

Purpose:

Record that a real Terminal Benchmark reference fixture was used in formal
`.agent-loop` evidence to prove the current Workstream policy-bundle path:

- project guide creation
- immutable guide-source snapshot from real Terminal Benchmark guide, review program, task, and
  review packet material
- guide sufficiency report
- project `SubmissionArtifactPolicy`
- effective project submission artifact policy
- compiled project `PreSubmitCheckerPolicy`
- two tasks locking the same project policy context
- activation of a newer guide version with a distinct project
  `PreSubmitCheckerPolicy`
- proof that an already-started task still uses its locked v1 checker bundle
- pre-submit blocking before submission creation
- post-submit checker-caused `needs_revision`
- fixed v2 resubmission reaching `review_pending`

Commands run:

```bash
python3 scripts/check_stale_workstream_wording.py
cd backend && .venv/bin/python -m ruff check app tests scripts ../examples/terminal_benchmark
cd backend && .venv/bin/docstr-coverage app scripts --config .docstr.yaml
git diff --check
python3 scripts/check_markdown_links.py
```

Results:

- stale wording check passed
- ruff passed
- docstring coverage passed at 100.0%
- diff whitespace check passed
- Markdown link check passed for changed Markdown files
- Terminal Benchmark manual API drill passed against the selected local
  source-material directory
- clean packet reached `review_pending`
- missing static guard was blocked at pre-submit and created no submission
- blocked pre-submit and blocked submission-create produced no durable
  submission, evidence, checker-run, or checker-result side effects; task audit
  recorded the blocked intake attempt
- after a v2 guide and project checker became active, the already-started task
  still used its locked v1 checker bundle
- checker-caused v1 reached `needs_revision`
- fixed v2 superseded v1 and reached `review_pending`

This section is only a local pointer to the formal proof. Formal zero-trust
chunk evidence lives under `.agent-loop/`.

## Manual Live API Drill Update

Date: 2026-07-05

The 2026-07-05 proof was rerun manually over HTTP against a live local uvicorn
server and local Postgres. The Python example scaffold was not used as the
authoritative proof for this pass.

Live API sequence:

- health check returned `ok`
- project manager created project
- project manager created a project guide with full Terminal Benchmark submission program,
  project guide, review program, task TOML, and review packet content
- project manager created an immutable guide-source snapshot with source hashes
  and sanitized durable refs
- `ProjectGuideSufficiencyAgent` endpoint returned `passed`
- `SubmissionArtifactPolicyDerivationAgent` endpoint returned an immutable
  agent-derived draft policy
- project manager created a separate admin-reviewed exact Terminal Benchmark
  policy because the agent draft used generalized workspace paths
- policy approval produced an approved effective project submission artifact
  policy and compiled project `PreSubmitCheckerPolicy`
- guide activation returned the complete active guide-policy bundle
- task screening locked guide version `v1`, the guide-source snapshot hash, the
  effective project submission artifact policy hash, and the project
  pre-submit checker bundle hash
- incomplete packet missing `static_guard.txt` failed pre-submit and blocked
  submission creation with `pre_submission_checker_failed`
- blocked pre-submit and blocked create left submission count at `0`
- complete packet passed pre-submit, created a submission, locked policy context,
  ran the durable checker gate, and moved the task to `review_pending`
- placeholder summary passed pre-submit with a warning, failed the durable
  post-submit checker, and moved the revision-path task to `needs_revision`
- fixed v2 submission superseded v1 and moved the task back to `review_pending`

Live IDs captured from local HTTP API responses:

- project: `<redacted-id>`
- guide: `<redacted-id>`
- guide-source snapshot: `<redacted-id>`
- sufficiency report: `<redacted-id>`
- agent-derived policy draft: `<redacted-id>`
- admin exact policy: `<redacted-id>`
- effective project submission artifact policy hash:
  `sha256:<redacted>`
- compiled pre-submit checker hash:
  `sha256:<redacted>`
- clean task: `<redacted-id>`
- clean submission: `<redacted-id>`
- clean checker run: `<redacted-id>`
- revision-path task: `<redacted-id>`
- revision v1 submission: `<redacted-id>`
- revision v1 checker run: `<redacted-id>`
- fixed v2 submission: `<redacted-id>`

Runtime issue found and fixed:

- The OpenAI Agents SDK adapter initially rejected the derivation output schema
  because `policy_body` is intentionally an open JSON object and the SDK strict
  schema path does not accept that shape.
- The adapter now wraps output types with `AgentOutputSchema(...,
  strict_json_schema=False)`, while Workstream still validates the returned
  `policy_body` through `SubmissionArtifactPolicyInput` before persistence.
- The derivation prompt now names the exact constrained policy-body shape so
  the agent returns a compiler-ready specification instead of a broad policy
  memo.
