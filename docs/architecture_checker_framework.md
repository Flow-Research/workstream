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
- `contributor_visible`
- `description`

Phase:

- project_activation
- task_screening
- pre_submit_intake
- submission_quality
- pre_review_gate
- lifecycle_transition
- compensation_fulfillment_reconciliation

Checker names must not drift between project guides, policy templates, implementation code, and checker results. New behavior uses a new checker version or a new checker id.

## Blocking Policy

Default:

- critical- and high-severity `failed` results block human review
- medium-severity `failed` result creates reviewer warning
- low-severity `failed` result creates informational note

Approved machine policies can declare stricter blocking behavior. `SubmissionArtifactPolicy` and generated project `PreSubmitCheckerPolicy` govern pre-submit artifact rules. `PostSubmitCheckerPolicy` governs durable post-submit checker blocking.

Project policy cannot weaken Workstream default submission artifact rules. Workstream defaults are applied before project policy. A project policy that attempts to require a forbidden artifact, remove hash requirements, allow credential-bearing storage references, or downgrade blocking defaults is a project setup defect.

The checker framework is conservative. It blocks objective structural failures and warns on judgment-heavy issues. Human reviewers own final quality judgment.

## Required Core Checkers

### check_policy_context_present

Ensures the task has locked guide, checker, review, and revision policy context.
Compensation is frozen independently on TaskAssignment and ReviewLease and is
not checker-policy context.

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

Ensures the contributor explicitly attests that the submission does not contain prohibited client data, private source material, credentials, or copied platform artifacts.

### check_low_quality_generated_artifacts

Flags repeated low-quality generated patterns banned by project submission artifact policy, such as generic helper files, hidden-test leakage patterns, fabricated model files, placeholder evidence, or boilerplate reports that do not prove task-specific work.

This checker produces warnings by default. If a project explicitly includes it
in required post-submit checkers, matching low-quality signals become
contributor-fixable blocking failures and route the task to `needs_revision`.

Revision closure, task lifecycle movement, task readiness, and pre-review routing are enforced as lifecycle guards in v0.1. They must not be configured as checker policy names until a registered checker exists for that contract.

The pre-review gate is a checker execution phase. The persisted task status during this phase is `evaluation_pending`.

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

Pre-submit intake is generated from policy. It is not manually supplied by the contributor.

The deterministic chain is:

```text
ProjectGuide
-> GuideSourceSnapshot
-> GuideSufficiencyReport
-> SubmissionArtifactPolicy
-> EffectiveProjectSubmissionArtifactPolicy
-> trusted Workstream checker compiler
-> PreSubmitCheckerPolicy
-> pre-submit intake checks
-> Submission row only when blocking checks pass
```

`ProjectGuide` is open-ended human-facing project material. Workstream first
persists a `GuideSufficiencyReport`. Blocking guide gaps stop activation and
create clarification requests for the project owner. Warnings require
acknowledgement by an authorized covered Project Manager.

`SubmissionArtifactPolicy` is machine-readable, derived by Workstream from
project guide material after sufficiency passes or passes with warnings, and
approved by an authorized covered Project Manager after
any warnings are acknowledged.
The project owner does not approve this internal policy. Workstream combines
that policy with the non-bypassable Workstream default submission artifact
policy.

Workstream default submission artifact rules require:

- summary
- artifact hash manifest
- contributor attestation
- safe relative artifact paths
- production artifact hashes shaped as `sha256:<64 lowercase hex>`
- pre-cutover only: validated caller-supplied storage references;
  `WS-ART-001-05` removes them and checkers then consume Workstream artifact
  bindings only
- no credentials, signed URLs, query strings, raw local filesystem paths, or token-bearing references
- no default forbidden artifacts such as `.env`, `.git`, private keys, credentials, secrets, tokens, `.pem`, `.key`, or `node_modules`

Project policy adds required artifacts, evidence requirements, stricter forbidden artifacts, stricter packaging rules, and project-specific attestation requirements.

The generated project `PreSubmitCheckerPolicy` is persisted with a compiled
bundle hash and locked to the effective project submission artifact policy before tasks enter the
contributor pipeline. Tasks lock references to the shared project's compiled checker
bundle hash. It runs before Workstream creates a submission. Preflight failures return
`PreSubmitCheckResponse` with `status="failed"`,
`eligible_to_submit=false`, and structured pass/fail/warning details in
`results`. Blocked submission-create attempts use the user-facing error code
`pre_submission_checker_failed`; it is not a review decision value.
Pre-submit results do not create durable `CheckerRun` records, do not move a
task to `review_pending`, and do not return review decision values: `accept`,
`needs_revision`, or `reject`.

The `SubmissionArtifactPolicyDerivationAgent` produces the artifact-intake
contract. It does not produce unrestricted checker code. Workstream's trusted
checker compiler builds and validates the project checker specification during
setup, then persists deterministic project-level checker logic using approved
primitives such as:

- `validate_submission_packet`
- `enforce_storage_scheme`
- `require_manifest_field`
- `verify_hash`
- `require_file`
- `require_minimum_evidence`
- `forbid_artifact`
- `require_attestation`
- `limit_file_size`
- `limit_package_size`
- `require_packaging`
- `warn_low_quality_generated_artifact`

`warn_low_quality_generated_artifact` is warning-only. The trusted compiler
rejects checker specifications that escalate that primitive to blocking.

Project-specific executable checker code is a future extension path, not the
default. That extension path must require static validation, generated tests,
sandboxed execution, no network, no shell, no secrets, no database access,
covered Project Manager approval of the exact code hash after those checks
pass, and a locked code hash.

Pre-submit checks are authoritative for intake. Post-submit checker runs are authoritative for review readiness.

## Post-Submit Derivation

Post-submit policy setup resumes after an authorized covered Project Manager
approves the derived `SubmissionArtifactPolicy`. That approval
creates the effective project submission artifact policy and compiled project
`PreSubmitCheckerPolicy`; only then does Workstream run
`PostSubmitCheckerPolicyDerivationAgent`.

The post-submit derivation agent receives bounded guide-source material,
sufficiency summary, effective policy summary, pre-submit checker summary, and
the registered post-submit checker catalog. It may request only registered
checker names and must tie project-specific requests to bounded evidence refs.
If the guide implies a required checker that is not registered, setup records
`post_submit_setup_blocked` with a safe unsupported-checker summary instead of
inventing a checker or letting activation proceed.

The agent output is a constrained spec. Workstream's trusted compiler owns the
canonical `PostSubmitCheckerPolicy.policy_body`, hash, default checker list,
and execution order. Runtime checker execution loads the locked compiled
policy; it does not call an agent to judge a contributor submission.

The compiled project `PostSubmitCheckerPolicy` is persisted with exact setup
provenance: guide id, source snapshot id/hash, effective project policy id/hash,
and pre-submit checker policy id/hash. A corrected submission artifact policy
approval supersedes and retains stale post-submit setup output, then regenerates
the compiled post-submit policy under the new provenance. Workstream must not
reuse a policy or correction request that only happens to match the same project
id and guide version.

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

## Post-Submit Compiler Boundary

`PostSubmitCheckerPolicy` is produced by Workstream's trusted post-submit
compiler from a constrained specification. The compiler owns the canonical
runtime body and hash. Setup agents may propose registered checker names and
routing classifications, but they do not produce executable runtime code and
they do not decide submission outcomes at runtime.

The compiler always includes the platform default durable checkers in
`default_checkers` and `execution_checkers`:

- `check_submission_packet`
- `check_policy_context_present`
- `check_evidence_present`
- `check_evidence_integrity`
- `check_required_files`
- `check_forbidden_files`
- `check_confidentiality_attestation`
- `check_low_quality_generated_artifacts`

Default-only projects are valid. In that case, project-specific
`required_checkers` and `warning_checkers` are empty, while
`execution_checkers` still contains every platform default checker. A project
may use `required_checkers` to tighten routing for a registered checker,
including a default checker such as `check_low_quality_generated_artifacts`.
Project policy cannot remove, rename, reorder, or weaken the platform default
checker list.

Platform blocking severities are `critical` and `high`. Project policy may add
stricter blocking severities, but it cannot remove those platform blocking
severities.

## Checker Run Flow

```text
Draft packet
-> load locked task context
-> load locked EffectiveProjectSubmissionArtifactPolicy hash
-> load locked PreSubmitCheckerPolicy compiled bundle hash
-> run pre-submit intake checks
-> create Submission only when blocking pre-submit checks pass
-> automatically lock submission
-> queue automatic pre-review CheckerRun
-> validate locked PostSubmitCheckerPolicy id/version/hash/body
-> execute locked PostSubmitCheckerPolicy execution_checkers
-> store CheckerResult records
-> calculate blocking status
-> if no blocking failures remain: store readiness proof on CheckerRun and move to REVIEW_PENDING
-> if contributor-fixable blocking failures exist: route to user-facing needs_revision with outcome_source = auto_checker
-> if locked task setup is incomplete or unsafe: route to internal task_setup_blocked
-> if checker infrastructure fails: keep in checker retry handling
```

The checker run must bind to one immutable submission version. If the contributor uploads a replacement file, the platform creates a new submission version and reruns checks.

`evaluation_pending` is the persisted state while post-submit checker execution
or infrastructure retry is active. After checker results, immutable output/log
artifact bindings, and completion facts commit atomically, the checker subsystem
preserves the routes above: passing work moves to `review_pending`, while
contributor-fixable blocking failures may move to `needs_revision` with
`outcome_source = auto_checker`. Artifact-storage cutover changes how exact
bytes and checker outputs are persisted; it does not redesign these routes.

`review_pending` marks readiness for the separately owned WS-REV lifecycle.
WS-REV alone creates `ReviewPacketManifest`, review queues, reviewer leases,
assignments, and review decisions. Checker completion facts and general
`ArtifactBinding` records are inputs to that later boundary, not review records.

Checker failures are not human review decisions. They do not `accept` or `reject` work. Contributor-fixable blocking failures can route the task to user-facing `needs_revision`, with `outcome_source = auto_checker` and no review decision id. Human review can also produce `needs_revision` later, but that records `outcome_source = human_review` and a review decision id.

If a checker crashes or cannot run because of platform infrastructure, the
checker run remains failed as an infrastructure failure and the task does not
move to human review. A retry requires Operator
`operations.checker.retry`, a reason, a new attempt/supersession record, and
append-only audit evidence.

If a checker finds missing locked guide or policy context, missing acceptance
criteria, or another task setup defect that is not contributor-fixable, the run uses
`task_setup_blocked`. That route is internal to covered Project Managers and
authorized Operators and must not be shown to contributors as a revision request.

## Readiness Proof

When all blocking checks pass, the checker service stores readiness proof on the current checker run.

The checker run records:

- submission id
- post-submit checker policy id, version, hash, and internal locked body
  stamped from the locked submission context
- artifact hash manifest
- blocking failure count
- warning count
- completion timestamp

This gives reviewers a clear proof that they are reviewing the same packet that passed automated checks.

A separate `ReadinessCertificate` record may be added later if reviewer routing needs a dedicated signed handoff object. v0.1 does not require that extra record.

## Checker Output Visibility

Contributors see:

- failed checker name
- severity
- message
- suggested fix when safe

Contributor-facing checker-run responses do not expose `routing_recommendation`,
`outcome_source`, internal route tokens, post-submit policy provenance fields,
locked post-submit policy body, or hidden task setup details.

Reviewers see:

- all checker output
- evidence references
- full metadata where allowed

Authorized Project Manager, Operator, and Audit projections expose only their
permission-appropriate fields. Depending on the matched permission they may
see:

- full logs
- internal rule IDs
- reasoned retry/repair controls

## Recovery, Not Checker Override

Critical- and high-severity checker failures cannot be converted into review
readiness by an administrative grant. A covered Project Manager may repair task
setup under `project.task.manage`; an Operator may use
`operations.submission_gate.repair` or `operations.checker.retry` only for the
registered recovery purpose.

Recovery requires:

- reason
- actor
- timestamp
- exact project/task/submission/checker resource
- matched grant and permission
- evidence

Recovery cannot delete checker results, mutate an immutable submission, create
a human review decision, or bypass a blocking content failure. It creates a new
audited repair/retry attempt while preserving prior evidence.

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
- repeated infrastructure retry/repair patterns or attempts to bypass blocking
  checker failures
- evidence that passed structurally but did not prove the claim
- generated or copied artifacts that evade forbidden-file rules

Each blind spot becomes a guide update, checker update, reviewer policy update,
revision policy update, contribution policy update, template update, or
reviewer-training change.

## First Implementation

The first checker runner can be simple:

- async-first execution
- authorized checker trigger that records a run before execution
- markdown/json output
- attached logs

The checker interface is async-first from the start so storage reads, external
checks, and later agent evaluation do not require a contract rewrite.

Background checker execution uses Celery. FastAPI background tasks are not the
Workstream product-job boundary. Request-bound pre-submit feedback can remain
fast and deterministic because it runs before submission creation, but any
long-running setup or post-submit checker work must go through the durable
worker boundary.
