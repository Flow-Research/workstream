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

Critical- and high-severity failed checks block human review.

Medium and low severities are visible to reviewers unless this policy overrides them.

## Required Checkers

Task setup and post-submit checks must stay separated from contributor-fixable submission intake checks.

| Checker | Severity | Blocks Review | Purpose |
| --- | --- | --- | --- |
| `check_policy_context_present` | high | yes | Task must have locked guide snapshot, effective project submission artifact policy hash, pre-submit checker bundle hash, post-submit checker policy id/version/hash, review policy, and revision policy context. |
| `check_submission_packet` | high | yes | Submission must include required packet fields. |
| `check_required_files` | high | yes | Submission must include artifacts required by the locked effective project policy and project pre-submit checker bundle. |
| `check_forbidden_files` | high | yes | Submission must not include forbidden file paths. |
| `check_evidence_present` | high | yes | Submission must include audit evidence. |
| `check_evidence_integrity` | high | yes | Evidence and checker runs must bind to submitted artifacts. |
| `check_confidentiality_attestation` | high | yes | Contributor attestation must address confidentiality and credential handling. |
| `check_low_quality_generated_artifacts` | medium/high | policy-dependent | Placeholder signals warn by default; the locked blocking severities may require contributor revision. |

Task setup checks:

| Checker | Severity | Blocks Review | Owner |
| --- | --- | --- | --- |
| `check_acceptance_criteria_present` | high | yes | Project manager repair, not contributor revision. |

## Compiler Contract

One compiler creates the canonical ordered `PostSubmitCheckerPolicy` body.
All eight platform defaults are mandatory and nonselectable. Default-only
projects have no project-specific required or warning entries but execute all
defaults. `check_acceptance_criteria_present` is the sole selectable structural
addition; it proves presence, not substantive satisfaction of task criteria.

Required/warning/execution lists are derived from canonical entries. Persisted
summaries must agree with that body and its exact hash. Unknown identities,
unsupported configuration, conflicting classifications, altered mandatory
entries and stale hashes reject. No earlier development body has a fallback
reader. A new project policy version records changed rules within this one
current software contract.

## Pre-Submit Boundary

Pre-submit checker policy is generated from:

```text
EffectiveProjectSubmissionArtifactPolicy =
  WorkstreamDefaultSubmissionArtifactPolicy
  + SubmissionArtifactPolicy

PreSubmitCheckerPolicy =
  trusted compiler output from EffectiveProjectSubmissionArtifactPolicy
```

Failed preparation returns `pre_submission_checker_failed` with ART's exact
ordered bounded results through the mounted authorized hidden route. The route
remains absent from OpenAPI, and public intake activation remains pending. POL-07B connects
the internal checker phase service and removes the standalone JSON precheck. WS-ARCH-001-02I retains the broader Submission caller
cutover. Pre-submit failures do not create durable
`CheckerRun` records and do not return review decision values: `accept`,
`needs_revision`, or `reject`.

The hidden platform/default phase uses `passed`, `warning`, `failed`,
`advisory_disabled`, and `dependency_not_run`. It authorizes and destroys one
callback-scoped sealed ART tree before returning these non-durable results.
Project-policy primitives execute in the later phase of the same effective
plan.

## Checker Registry Fields

Each checker definition specifies:

- checker id
- phase
- version
- default severity
- default blocking behavior
- contributor-visible message policy

## Project-Specific Checkers

| Checker | Severity | Blocks Review | Purpose |
| --- | --- | --- | --- |
| `<checker name>` | `<low/medium/high>` | `<yes/no>` | `<why it exists>` |

## Contributor-Visible Messages

Contributors may see:

- checker name
- status
- severity
- safe failure message
- suggested fix

Contributors must not see:

- hidden evaluator logic
- private reviewer notes
- confidential source metadata
- internal checker routing tokens such as `allow_review`, `checker_retry`, or
  `task_setup_blocked`
- post-submit checker policy provenance fields

## Recovery Contract

Blocking checker outcomes are not overridden into review readiness. Registered
Operator retry or covered Project Manager repair is allowed only with:

- actor
- matched grant and permission
- exact resource scope
- timestamp
- checker name
- reason
- evidence

Recovery creates a new attempt or repaired setup state and preserves every
prior checker result. It cannot create a human review decision.

## Review Cadence

Review this checker policy weekly during the pilot.
