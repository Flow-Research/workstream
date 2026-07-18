# PR Trust Bundle: WS-POL-001-16

## Intent

Prove the current Workstream project setup and submission intake lifecycle with a real Terminal Benchmark live API drill, using HTTP-visible evidence instead of database inspection.

This chunk exists because earlier Terminal Benchmark drills exposed real gaps in project setup visibility, worker requirements, finalization, and agent-derived submission policy quality. This pass proves the corrected flow slowly and visibly.

## Scope

Changed:

- `.agent-loop/LOOP_STATE.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/STATUS.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-16-terminal-benchmark-live-api-drill.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-live-api-drill-evidence.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-live-api-drill-report.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-live-api-drill-report.pdf`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-internal-review-evidence.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-pr-trust-bundle.md`
- Privacy scrub amendment: standalone Terminal Benchmark example docs/script,
  older Terminal Benchmark evidence references, WS-ENG memory evidence,
  chunk-map/status/loop files, and review-process docs were scrubbed or amended
  to remove private/local source identifiers, local secret paths, and stale
  scope claims.

Not changed:

- No backend code.
- No migrations.
- No backend tests or production scripts.
- No CI/workflow files.
- No frontend/demo work.
- No auth, payment, reputation, settlement, or blockchain behavior.
- No task-specific checker generation.

## Design

The drill evidence follows the real Workstream chain:

```text
ProjectGuide
-> GuideSourceSnapshot
-> GuideSufficiencyReport
-> SubmissionArtifactPolicy
-> EffectiveProjectSubmissionArtifactPolicy
-> project PreSubmitCheckerPolicy
-> task locked context
-> deterministic pre-submit
-> submission finalization
-> durable checker run
-> review_pending
```

The evidence records:

- sanitized Terminal Benchmark source material with public redaction of source
  fingerprints;
- automatic Celery setup status from queued through `policy_draft_ready`;
- sufficiency-agent and submission-policy-derivation inputs and outputs;
- policy approval, effective policy, checker policy, and guide activation;
- task creation, screening, release, worker profile activation, claim, and start;
- worker work-context and submission-requirements reads;
- blocked pre-submit and blocked create with no submission side effect;
- successful pre-submit, durable submission creation, manager finalization, checker-run list/get, audit events, and final `review_pending` task response.

The checker-run no-side-effect proof is aligned with the existing API design: checker-run list/get is submission-scoped, so blocked intake before a submission id is proved with task submissions plus audit events; checker-run visibility is proven after a submission exists and finalization starts the pre-review gate.

## Verification

Passed:

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
cd backend && .venv/bin/pytest tests/test_projects.py tests/test_tasks.py tests/test_checkers.py -q
cd backend && WORKSTREAM_DATABASE_URL=<local-test-db-url> .venv/bin/python scripts/api_contract_e2e.py
cd backend && .venv/bin/python -m ruff check ../examples/terminal_benchmark/terminal_benchmark_api_e2e.py
cd backend && python3 -m py_compile ../examples/terminal_benchmark/terminal_benchmark_api_e2e.py
redaction helper inline check for UUID, fixture-id, hash, and local-path sanitization
default missing-agent-env failure check for sanitized stderr and nonzero exit
render professional PDF report from the redacted evidence source
extract PDF text and run targeted privacy scan over the PDF/source artifacts
targeted privacy scan for private source names, local paths, fixture-id shapes, source-task labels, and agent hash prefixes
git diff --check
```

Key results:

- `342 passed in 4305.43s (1:11:45)` for focused backend tests.
- `API contract real API e2e passed`.
- Terminal Benchmark example Ruff and py_compile passed.
- Public-safe exception helper check passed.
- Default missing-agent-env failure emitted only the sanitized one-line public
  failure message and printed `terminal benchmark public failure output redaction passed`.
- Professional PDF report rendered as 14 A4 pages.
- PDF report SHA-256:
  `f455414dfd1d60f066352e7d74ea9e5b55271a3b943464f88968f8ffc7de5492`.
- Embedded PreSubmitCheckResponse JSON samples validated against the backend
  Pydantic schema.
- Extracted PDF text passed the targeted privacy scan.
- Privacy scan only reported intentional backend test literals for unsafe-path
  and reserved `agent-` prefix validation.
- Stale wording check passed.
- Markdown link check passed for 26 changed Markdown files.
- Diff whitespace check passed.

## Live Drill Result

The live drill values below are privacy-redacted for public PR evidence. Exact
fixture ids, local UUIDs, source-material hashes, package hashes, byte counts,
and source-specific task identifiers are not committed because they fingerprint
private local source material. Redaction placeholders are not replayable API
literals.

Final clean run:

```text
project_id: <redacted-id>
guide_id: <redacted-id>
source_snapshot_id: <redacted-id>
source_snapshot_hash: sha256:<redacted>
submission_artifact_policy_hash: sha256:<redacted>
effective_policy_hash: sha256:<redacted>
pre_submit_checker_bundle_hash: sha256:<redacted>
task_id: <redacted-id>
submission_id: <redacted-id>
checker_run_id: <redacted-id>
final_task_status: review_pending
```

Evidence:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-live-api-drill-evidence.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-live-api-drill-report.pdf`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-live-api-drill-report.md`

## Internal Review

| Reviewer | Result |
|---|---:|
| senior engineering | PASS |
| QA/test | PASS WITH LOW RISKS |
| security/auth | PASS |
| product/ops | PASS WITH LOW RISKS |
| architecture | PASS WITH LOW RISKS |
| docs | PASS WITH LOW RISKS |
| reuse/dedup | PASS |
| test delta | PASS WITH LOW RISKS |
| CI integrity | PASS WITH LOW RISKS |

Evidence:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-16-internal-review-evidence.md`

## Human Review Focus

- Confirm the live drill is understandable from HTTP-visible evidence without DB inspection.
- Confirm the Terminal Benchmark source material is treated as fixture/example evidence, not a Workstream product fork.
- Confirm the setup agent inputs/outputs, derived policy, effective policy, and compiled project checker remain project-scoped.
- Confirm blocked pre-submit creates no submission and does not rely on product review decisions.
- Confirm submission finalization, checker-run visibility, audit events, and final `review_pending` state match the intended lifecycle.

## Remaining Risks

- The detailed live drill report is now a PDF artifact, with a concise Markdown
  evidence index and source Markdown for reviewability.
- This chunk does not implement review packet assignment, human review decisions, or revision replay APIs; those remain future chunks.
- Default failure output may include unrelated Alembic INFO lines before the
  sanitized failure if migration logging is enabled, but reviewer reruns
  confirmed it does not expose fixture/source details, paths, hashes, UUIDs,
  or tracebacks.
