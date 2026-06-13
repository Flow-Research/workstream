# Checker Framework

## Purpose

The checker framework protects reviewer time and enforces project rules before human review.

It does not replace reviewers. It blocks structurally broken work and gives reviewers reliable evidence.

## Checker Result Contract

Every checker returns:

```json
{
  "name": "check_submission_packet",
  "status": "passed",
  "severity": "info",
  "message": "Submission packet is complete.",
  "suggested_fix": null,
  "evidence": [],
  "metadata": {}
}
```

Status:

- passed
- warning
- failed

Severity:

- info
- low
- medium
- high
- critical

## Checker Registry

Every checker is registered with a stable definition before projects reference it.

Definition fields:

- `checker_id`
- `name`
- `phase`
- `version`
- `default_severity`
- `default_blocks_review`
- `worker_visible`
- `description`

Phase:

- project_activation
- task_screening
- submission_quality
- pre_review_gate
- lifecycle_transition
- payment_reconciliation

Checker names must not drift between project guides, policy templates, implementation code, and checker results. New behavior uses a new checker version or a new checker id.

## Blocking Policy

Default:

- high-severity `failed` result blocks human review
- medium-severity `failed` result creates reviewer warning
- low-severity `failed` result creates informational note

Project guides can override this by declaring stricter policies.

The checker framework is conservative. It blocks objective structural failures and warns on judgment-heavy issues. Human reviewers own final quality judgment.

## Required Core Checkers

### check_policy_context_present

Ensures the task has locked guide, checker, review, revision, and payment policy context, including base amount and currency where required.

### check_submission_packet

Ensures submission has summary, output reference, and package/evidence where required.

### check_evidence_present

Ensures accepted work can be audited.

### check_evidence_integrity

Ensures the submission packet records content hashes for uploaded artifacts and that checker runs use those exact hashes.

### check_acceptance_criteria_present

Ensures a task has rubric or acceptance criteria.

### check_required_files

Validates project-specific required files.

### check_forbidden_files

Blocks known forbidden files, secrets, private keys, copied internal data, or files forbidden by the project guide.

Default forbidden patterns include:

- private keys
- API tokens
- `.env`
- copied confidential client/source files
- generated low-quality helper artifacts banned by the project guide
- files not allowed in the submission packet

### check_confidentiality_attestation

Ensures the worker explicitly attests that the submission does not contain prohibited client data, private source material, credentials, or copied platform artifacts.

### check_low_quality_generated_artifacts

Flags repeated low-quality generated patterns banned by the project guide, such as generic helper files, hidden-test leakage patterns, fabricated model files, placeholder evidence, or boilerplate reports that do not prove task-specific work.

Revision closure, task lifecycle movement, task readiness, and pre-review routing are enforced as lifecycle guards in v0.1. They must not be configured as checker policy names until a registered checker exists for that contract.

The pre-review gate is a checker execution phase. The persisted task status during this phase is `auto_checking`.

## Gate Mapping

Project activation gate:

- `check_policy_context_present`
- project-specific guide completeness checks

Task screening gate:

- `check_policy_context_present`
- `check_acceptance_criteria_present`
- task lifecycle transition guards

Submission quality gate:

- `check_submission_packet`
- `check_evidence_present`
- `check_evidence_integrity`
- `check_required_files`
- `check_forbidden_files`
- `check_confidentiality_attestation`
- `check_low_quality_generated_artifacts`

Pre-review gate phase:

- project-configured registered checkers run against the locked submission and policy context

The first two gates replace external origin qualification and task ingestion for v0.1. Origin qualification and webhook drop notifications are future adapter concerns.

## Project-Specific Checkers

Each project can register specialized checkers.

Examples:

- code task package checker
- rubric formatting checker
- document citation checker
- data annotation completeness checker
- security artifact checker
- plagiarism or originality checker
- hidden-test packaging checker
- no-confidential-source-data checker
- reviewer-simulation checker for first-of-kind or high-value tasks
- reviewer simulation gate
- prior feedback checklist checker

## Checker Run Flow

```text
Draft packet
-> run pre-submit static checks
-> submit packet
-> lock submission
-> create CheckerRun
-> load project CheckerPolicy
-> run required checkers
-> store CheckerResult records
-> calculate blocking status
-> if no blocking failures remain: store readiness proof on CheckerRun and move to REVIEW_PENDING
-> if worker-fixable blocking failures exist: route to user-facing needs_revision with outcome_source = auto_checker
-> if locked task setup is incomplete or unsafe: route to internal task_setup_blocked
-> if checker infrastructure fails: keep in checker retry handling
```

The checker run must bind to one immutable submission version. If the worker uploads a replacement file, the platform creates a new submission version and reruns checks.

Checker failures are not human review decisions. They do not `accept` or `reject` work. Worker-fixable blocking failures can route the task to user-facing `needs_revision`, with `outcome_source = auto_checker` and no review decision id. Human review can also produce `needs_revision` later, but that records `outcome_source = human_review` and a review decision id.

If a checker crashes or cannot run because of platform infrastructure, the checker run remains failed as an infrastructure failure and the task does not move to human review. The retry or admin action is recorded in audit history.

If a checker finds missing locked guide or policy context, missing acceptance criteria, or another task setup defect that is not worker-fixable, the run uses `task_setup_blocked`. That route is internal to project managers and must not be shown to workers as a revision request.

## Readiness Proof

When all blocking checks pass, the checker service stores readiness proof on the current checker run.

The checker run records:

- submission id
- checker policy version derived from the locked task context
- artifact hash manifest
- blocking failure count
- warning count
- completion timestamp

This gives reviewers a clear proof that they are reviewing the same packet that passed automated checks.

A separate `ReadinessCertificate` record may be added later if reviewer routing needs a dedicated signed handoff object. v0.1 does not require that extra record.

## Checker Output Visibility

Workers see:

- failed checker name
- severity
- message
- suggested fix when safe

Reviewers see:

- all checker output
- evidence references
- full metadata where allowed

Admins see:

- full logs
- internal rule IDs
- override controls

## Admin Override

An admin can override a high-severity checker failure only with:

- reason
- actor
- timestamp
- affected checker
- evidence

Overrides are rare and visible in audit logs.

Overrides cannot delete checker results. They only create an auditable exception record.

## Checker Quality Metrics

Track:

- false positive rate
- false negative rate
- most common failures
- checks that reviewers repeatedly ignore
- checks that predict rejection

Checker quality is reviewed weekly during the first month. A repeated reviewer finding becomes one of:

- a new checker
- a stronger project guide rule
- a template update
- a reviewer training note
- a ProjectLesson record for operating review

## Checker Blind-Spot Review

Every week, compare accepted submissions, rejected submissions, and needs-revision findings against checker output.

Look for:

- reviewer findings that no checker predicted
- checker warnings reviewers always ignore
- high-severity checker failures that admins repeatedly override
- evidence that passed structurally but did not prove the claim
- generated or copied artifacts that evade forbidden-file rules

Each blind spot becomes a guide update, checker update, reviewer policy update, revision policy update, or payment policy update.

## First Implementation

The first checker runner can be simple:

- async-first execution
- request-bound authorized manual checker trigger for the first structural checks
- markdown/json output
- attached logs

The checker interface is async-first from the start so storage reads, external checks, and later agent evaluation do not require a contract rewrite.

Chunk 7 may complete the first structural checker run inside the request path because those checks are local and fast. Longer-running checker execution should create a run as `running` and complete it through FastAPI background tasks, Celery, or an equivalent worker boundary.

Use Celery or an equivalent durable queue when checker execution needs retries, scheduled jobs, progress reporting, worker isolation, or distributed execution.
