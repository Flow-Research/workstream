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
- pre_submit_intake
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

Approved machine policies can declare stricter blocking behavior. `SubmissionArtifactPolicy` and generated project `PreSubmitCheckerPolicy` govern pre-submit artifact rules. `PostSubmitCheckerPolicy` governs durable post-submit checker blocking.

Project policy cannot weaken Workstream default submission artifact rules. Workstream defaults are applied before project policy. A project policy that attempts to require a forbidden artifact, remove hash requirements, allow credential-bearing storage references, or downgrade blocking defaults is a project setup defect.

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

Validates required submission artifacts from the locked project pre-submit
checker policy.

### check_forbidden_files

Blocks known forbidden artifacts, secrets, private keys, copied internal data, or artifacts forbidden by the locked project pre-submit checker policy.

Default forbidden patterns include:

- private keys
- API tokens
- `.env`
- copied confidential client/source files
- generated low-quality helper artifacts banned by project submission artifact policy
- files not allowed in the submission packet

### check_confidentiality_attestation

Ensures the worker explicitly attests that the submission does not contain prohibited client data, private source material, credentials, or copied platform artifacts.

### check_low_quality_generated_artifacts

Flags repeated low-quality generated patterns banned by project submission artifact policy, such as generic helper files, hidden-test leakage patterns, fabricated model files, placeholder evidence, or boilerplate reports that do not prove task-specific work.

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

## Submission Artifact Policy And Pre-Submit Generation

Pre-submit intake is generated from policy. It is not manually supplied by the worker.

The deterministic chain is:

```text
ProjectGuide
-> GuideSourceSnapshot
-> GuideSufficiencyReport
-> ProjectSubmissionArtifactPolicy
-> EffectiveProjectSubmissionArtifactPolicy
-> trusted Workstream checker compiler
-> PreSubmitCheckerPolicy
-> pre-submit intake checks
-> Submission row only when blocking checks pass
```

`ProjectGuide` is open-ended human-facing project material. Workstream first
persists a `GuideSufficiencyReport`. Blocking guide gaps stop activation and
create clarification requests for the project owner. Warnings require
acknowledgement by `admin` or `project_manager`.

`SubmissionArtifactPolicy` is machine-readable, derived by Workstream from
project guide material after sufficiency passes or warnings are acknowledged,
and approved by a Workstream actor with the `admin` or `project_manager` role.
The project owner does not approve this internal policy. Workstream combines
that policy with the non-bypassable Workstream default submission artifact
policy.

Workstream default submission artifact rules require:

- summary
- artifact hash manifest
- worker attestation
- safe relative artifact paths
- production artifact hashes shaped as `sha256:<64 lowercase hex>`
- validated `local://`, `s3://`, or `r2://` storage references
- no credentials, signed URLs, query strings, raw local filesystem paths, or token-bearing references
- no default forbidden artifacts such as `.env`, `.git`, private keys, credentials, secrets, tokens, `.pem`, `.key`, or `node_modules`

Project policy adds required artifacts, evidence requirements, stricter forbidden artifacts, stricter packaging rules, and project-specific attestation requirements.

The generated project `PreSubmitCheckerPolicy` is persisted with a compiled
bundle hash and locked to the effective project submission artifact policy before tasks enter the
worker pipeline. Tasks lock references to the shared project's compiled checker
bundle hash. It runs before Workstream creates a submission. Preflight failures return
`PreSubmitCheckResponse` with `status="failed"`,
`eligible_to_submit=false`, and structured pass/fail/warning details in
`results`. Blocked submission-create attempts use the user-facing error code
`pre_submission_checker_failed`; it is not a review decision value.
Pre-submit results do not create durable `CheckerRun` records, do not move a
task to `review_pending`, and do not return review decision values: `accept`,
`needs_revision`, or `reject`.

The `SubmissionArtifactPolicyDerivationAgent` produces a constrained checker
specification. It does not produce unrestricted checker code. Workstream's
trusted checker compiler validates that project spec during setup, then
persists deterministic project-level checker logic using approved primitives
such as:

- `require_file`
- `allow_extension`
- `forbid_extension`
- `require_manifest_field`
- `validate_json_schema`
- `check_directory_structure`
- `require_minimum_evidence`
- `verify_hash`
- `limit_file_size`

Project-specific executable checker code is a future extension path, not the
default. That extension path must require static validation, generated tests,
sandboxed execution, no network, no shell, no secrets, no database access,
`admin` or `project_manager` approval of the exact code hash after those checks
pass, and a locked code hash.

Pre-submit checks are authoritative for intake. Post-submit checker runs are authoritative for review readiness.

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
-> load locked task context
-> load locked EffectiveProjectSubmissionArtifactPolicy hash
-> load locked PreSubmitCheckerPolicy compiled bundle hash
-> run pre-submit intake checks
-> create Submission only when blocking pre-submit checks pass
-> lock submission
-> create CheckerRun
-> load locked PostSubmitCheckerPolicy
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
- post-submit checker policy version derived from the locked task context
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
