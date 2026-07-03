# Post-Submit Checker Policy Template

## Project

`<project name>`

## Policy Version

`v1`

## Scope

This template governs durable internal checker runs after a submission is created, locked, and ready for the pre-review gate.

It does not define pre-submit intake. `PreSubmitCheckerPolicy` is generated from `EffectiveProjectSubmissionArtifactPolicy`.

## Design Boundaries

Revision closure, readiness, and lifecycle movement are lifecycle guards in v0.1. Do not add them as checker policy names unless they are present in the registered checker list.

## Blocking Rule

High-severity failed checks block human review.

Medium and low severities are visible to reviewers unless this policy overrides them.

## Required Checkers

Task setup and post-submit checks must stay separated from worker-fixable submission intake checks.

| Checker | Severity | Blocks Review | Purpose |
| --- | --- | --- | --- |
| `check_policy_context_present` | high | yes | Task must have locked guide snapshot, effective project submission artifact policy hash, pre-submit checker bundle hash, post-submit checker policy id/version/hash, review, revision, and payment policy context. |
| `check_submission_packet` | high | yes | Submission must include required packet fields. |
| `check_required_files` | high | yes | Submission must include artifacts required by the locked effective project policy and project pre-submit checker bundle. |
| `check_forbidden_files` | high | yes | Submission must not include forbidden file paths. |
| `check_evidence_present` | high | yes | Submission must include audit evidence. |
| `check_evidence_integrity` | high | yes | Evidence and checker runs must bind to submitted artifacts. |
| `check_confidentiality_attestation` | high | yes | Worker attestation must address confidentiality and credential handling. |
| `check_low_quality_generated_artifacts` | low | no | Low-quality generated artifact signals create warning results by default. |

Task setup checks:

| Checker | Severity | Blocks Review | Owner |
| --- | --- | --- | --- |
| `check_acceptance_criteria_present` | high | yes | Project manager repair, not worker revision. |

## Pre-Submit Boundary

Pre-submit checker policy is generated from:

```text
EffectiveProjectSubmissionArtifactPolicy =
  WorkstreamDefaultSubmissionArtifactPolicy
  + SubmissionArtifactPolicy

PreSubmitCheckerPolicy =
  trusted compiler output from EffectiveProjectSubmissionArtifactPolicy
```

Preflight failures return `PreSubmitCheckResponse(status="failed",
eligible_to_submit=false, results=[...])`. Blocked submission-create attempts
return `DomainError(code="pre_submission_checker_failed")` with structured
pass/fail/warning details. Pre-submit failures do not create durable
`CheckerRun` records and do not return review decision values: `accept`,
`needs_revision`, or `reject`.

## Checker Registry Fields

Each checker definition specifies:

- checker id
- phase
- version
- default severity
- default blocking behavior
- worker-visible message policy

## Project-Specific Checkers

| Checker | Severity | Blocks Review | Purpose |
| --- | --- | --- | --- |
| `<checker name>` | `<low/medium/high>` | `<yes/no>` | `<why it exists>` |

## Worker-Visible Messages

Workers may see:

- checker name
- status
- severity
- safe failure message
- suggested fix

Workers must not see:

- hidden evaluator logic
- private reviewer notes
- confidential source metadata
- internal checker routing tokens such as `allow_review`, `checker_retry`, or
  `task_setup_blocked`
- post-submit checker policy provenance fields

## Admin Override

Allowed only with:

- actor
- timestamp
- checker name
- reason
- evidence

## Review Cadence

Review this checker policy weekly during the pilot.
