# WS-POL-001-16 Live API Drill Evidence Index

## Verdict

PASS.

The final Terminal Benchmark reference drill ran through public/operator HTTP
APIs without database inspection as lifecycle proof.

The shareable evidence artifact is now the professional PDF report below. The
raw request/response transcript was intentionally removed from this Markdown
file because it was too large for human review and too easy to misuse as a
public artifact.

## Report Artifact

- PDF report:
  [WS-POL-001-16-live-api-drill-report.pdf](WS-POL-001-16-live-api-drill-report.pdf)
- Report source:
  [WS-POL-001-16-live-api-drill-report.md](WS-POL-001-16-live-api-drill-report.md)
- PDF SHA-256:
  `f455414dfd1d60f066352e7d74ea9e5b55271a3b943464f88968f8ffc7de5492`
- PDF page count: 14
- PDF file size: 64,913 bytes
- PDF metadata:
  - Title: Workstream Live API Drill Report
  - Author: Flow Research / Workstream Engineering
  - Creator: pandoc
  - Producer: WeasyPrint 68.0
  - Page size: A4
- Report/source date: 2026-07-09

## Evidence Boundary

This is privacy-redacted public evidence. Exact fixture ids, local database
UUIDs, source-material hashes, package hashes, artifact byte counts, local
source labels, credentials, bearer tokens, and source-specific task identifiers
are not committed.

Redaction placeholders are evidence labels, not replayable API literals. The
Terminal Benchmark reference fixture is used only to test Workstream's API
lifecycle; it is not Workstream product source material.

## Final State

```text
project_id: <redacted-id>
guide_id: <redacted-id>
source_snapshot_id: <redacted-id>
source_snapshot_hash: sha256:<redacted>
sufficiency_status: passed
submission_artifact_policy_hash: sha256:<redacted>
effective_policy_hash: sha256:<redacted>
pre_submit_checker_bundle_hash: sha256:<redacted>
task_id: <redacted-id>
submission_id: <redacted-id>
checker_run_id: <redacted-id>
final_task_status: review_pending
```

## API Lifecycle Proved

The PDF report records the full API sequence at a professional summary level:

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

The drill proved:

- automatic setup-run progress from `queued` to `policy_draft_ready`;
- sufficiency-agent and submission-policy-derivation inputs and outputs;
- policy approval, effective project policy, compiled project checker, and
  guide activation;
- task screening and locked policy context;
- blocked submission creation after failed pre-submit with
  `pre_submission_checker_failed` and no submission
  side effect;
- checker-run list/get APIs are submission-scoped, so blocked intake before a
  submission id exists is proved through the empty submission list and task
  audit events rather than a checker-run endpoint;
- successful pre-submit, submission creation, manager finalization, durable
  checker-run visibility, audit events, and final `review_pending` task state.

## Checker Evidence

Compiled project pre-submit checker bundle:

```text
check_submission_packet
check_forbidden_files
check_confidentiality_attestation
check_required_files
check_evidence_present
check_evidence_integrity
check_low_quality_generated_artifacts
```

Durable checker results after finalization:

```text
check_submission_packet: passed
check_policy_context_present: passed
check_evidence_present: passed
check_evidence_integrity: passed
check_required_files: passed
check_forbidden_files: passed
check_confidentiality_attestation: passed
check_low_quality_generated_artifacts: passed
```

## Audit Evidence

Final task audit event sequence:

```text
task_created: null -> draft
task_status_changed: draft -> screening
task_status_changed: screening -> ready
task_status_changed: ready -> claimed
task_status_changed: claimed -> in_progress
pre_submission_check_failed: in_progress -> in_progress
submission_created: in_progress -> submitted
submission_finalized: submitted -> submitted
pre_review_gate_started: submitted -> evaluation_pending
pre_review_gate_passed: evaluation_pending -> review_pending
```

## Validation

Validation performed before report publication:

- PDF rendered successfully with A4 page layout.
- PDF metadata confirmed 14 pages.
- Embedded PreSubmitCheckResponse JSON samples validated against the backend
  Pydantic schema.
- PDF SHA-256 recorded above.
- Extracted PDF text was inspected for readability.
- Targeted privacy scan passed against the report source and extracted PDF
  text.
- Stale wording scan passed.
- Markdown link check passed.
- Internal review evidence gate passed after the report-format change.

## Notes

- No Workstream default checker was weakened.
- No task-specific checker generation was introduced.
- No product review decision token leaked into pre-submit output.
- No database inspection was used as lifecycle proof.
