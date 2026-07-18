# Plan: WS-POL-002 - Post-Submit Checker Foundation

## Goal

Make post-submit checker setup match the quality of the pre-submit checker
pipeline without changing the product review decision contract.

The final architecture should be:

```text
ProjectGuide
-> GuideSourceSnapshot
-> GuideSufficiencyReport
-> SubmissionArtifactPolicy
-> EffectiveProjectSubmissionArtifactPolicy
-> project PreSubmitCheckerPolicy
-> PostSubmitCheckerPolicyDerivationAgent
-> constrained PostSubmitCheckerPolicySpec
-> trusted Workstream compiler
-> project PostSubmitCheckerPolicy
-> tasks lock references
-> finalized submissions execute deterministic post-submit checkers
```

## Current Baseline

The runtime gate exists, but this initiative tightened the happy path during
`WS-POL-002-02` so manager action is not required after a contributor submits:

```text
contributor creates submission
-> Workstream reruns pre-submit against the exact payload
-> Workstream locks the submission packet
-> automatic Celery pre-review gate
-> evaluation_pending
-> review_pending | needs_revision | internal repair route
```

This initiative strengthens the project setup side so the policy feeding that
gate is no longer manually assembled in guide create/update payloads. The
`finalize` route is a repair/requeue surface for locked submissions only; it is
not the normal contributor submission handoff.

## Design

### Setup Pipeline

The project setup pipeline becomes a resumable setup flow. The current Celery
pipeline stops when it produces a draft `SubmissionArtifactPolicy`; it does not
already have an effective policy or compiled pre-submit bundle at that point.
WS-POL-002 must preserve that reality.

Phase 1:

```text
Guide/source capture
-> GuideSufficiencyAgent
-> SubmissionArtifactPolicyDerivationAgent
-> policy_draft_ready
-> v0.1 setup-authorized admin/project_manager approval of SubmissionArtifactPolicy
-> EffectiveProjectSubmissionArtifactPolicy
-> trusted pre-submit compiler
```

Phase 2:

```text
pre-submit compile success
-> PostSubmitCheckerPolicyDerivationAgent
-> trusted post-submit compiler
-> compiled post-submit policy pending setup approval
-> v0.1 setup-authorized admin/project_manager approval of PostSubmitCheckerPolicy
-> guide activation
```

The post-submit derivation agent runs after the effective project submission
artifact policy and pre-submit checker bundle exist, because durable
post-submit checks often depend on the same artifact and evidence contract.
The trigger is the server-owned continuation after pre-submit approval/compile,
not the initial source-capture enqueue.

### Agent Contract

`PostSubmitCheckerPolicyDerivationAgent` receives:

- project id and guide version
- guide source snapshot id and bundle hash
- guide content/source excerpts
- guide sufficiency report summary
- submission artifact policy summary
- effective project submission artifact policy hash and summary
- compiled pre-submit checker bundle summary
- current registered post-submit checker catalog

The agent returns a constrained `PostSubmitCheckerPolicySpec`:

- required registered checker names
- warning registered checker names
- severity/routing requirements
- reasons tied to guide/source evidence
- unsupported required-check gaps
- human-readable setup notes

The agent must not return executable runtime code in v0.1.

Project source material is untrusted LLM input. The derivation adapter must
treat guide/source excerpts as data, not instructions. Returned reasons must be
tied to bounded source-evidence references, and server-side validation must
reject or ignore any source text that attempts to override Workstream defaults,
roles, checker routing, authorization, or review-decision values.

### Compiler Contract

The trusted Workstream post-submit compiler:

- canonicalizes the spec
- always includes default durable checkers
- rejects unknown checker names
- rejects attempts to remove or weaken default checkers
- rejects duplicate or contradictory checker classifications
- rejects blocking-severity downgrade attempts
- requires every required checker to map to a registered deterministic checker
- emits the canonical `PostSubmitCheckerPolicy.policy_body`
- emits `policy_hash = sha256(canonical_json(policy_body))`

The platform default checker list is authoritative at compile time.
`policy_body.default_checkers` is stamped into the versioned locked policy body,
and the body hash preserves that exact compiler output for future task context.
Default-only projects are valid: the compiler represents defaults as required
durable coverage and permits an empty project-specific addition set only when
all platform defaults remain required in the compiled body.

The compiler, not the agent, decides the executable policy body.

### Runtime Contract

Runtime does not run derivation. Runtime loads the locked
`PostSubmitCheckerPolicy` id/version/hash/body from the submission and executes
the registered deterministic checkers listed in that body.

Routing remains:

- all blocking checks pass: `review_pending`
- worker-fixable blocking failure: `needs_revision`
- setup/context defect: internal `task_setup_blocked`
- transient trusted checker issue: internal `checker_retry`

Internal repair routes must be operator-visible with a bounded reason, owner,
next action, retry/audit provenance, and proof that reviewers only receive work
after the task reaches `review_pending`.

### Default Checkers

Default durable post-submit checkers are currently:

- `check_submission_packet`
- `check_policy_context_present`
- `check_evidence_present`
- `check_evidence_integrity`
- `check_required_files`
- `check_forbidden_files`
- `check_confidentiality_attestation`
- `check_low_quality_generated_artifacts`

These remain platform-owned and cannot be removed by project policy.

### Project-Specific Checkers

Project-specific post-submit policy may add registered deterministic checkers.
For example, a project can require `check_acceptance_criteria_present` when it
needs task setup reviewability enforced before human review.

If the guide implies a check that does not exist in the registered catalog, the
setup output must say that clearly and block activation until Workstream adds a
checker or the project guide expectation is corrected.

### API Visibility

Setup-authorized admins and project_managers need API-visible state for:

- post-submit derivation input summary
- derivation result
- unsupported checker gaps
- compiled policy body summary
- compiled policy hash
- approval status
- activation readiness

Setup visibility and approval endpoints use the current v0.1 bootstrap
authorization boundary: verified `admin` or `project_manager` roles. Workers,
reviewers, finance actors, and auditors remain denied. Project-scoped
project-manager authorization requires the future Workstream role-assignment
source of truth and is out of scope for WS-POL-002.

Persisted derivation output and API summaries must be bounded and redacted by
default. They must not echo raw guide/source text, local paths, secrets,
credential-shaped values, replayable signed refs, or exact source hashes unless
an explicit future secure evidence surface is designed for that purpose.

Workers should only see post-submit results that are safe and relevant to their
fix path. Internal setup defects remain hidden.

## Non-Scope

- Human review packet assignment.
- Reviewer decision APIs.
- Revision replay APIs beyond existing checker-caused `needs_revision` routing.
- Payment, reputation, blockchain, x402, ERC standards, or settlement.
- Frontend product work.
- Arbitrary generated checker code execution.
- Per-task checker derivation.
- Backward compatibility aliases for removed guide request fields.

## Proof Strategy

Each implementation chunk must include deterministic tests. The final chunk must
run a Terminal Benchmark-style live API drill that shows:

- source snapshot capture
- setup-run progression
- post-submit policy derivation input/output
- compiled post-submit policy visibility
- activation gate
- task locked context
- submission finalization
- durable checker run
- worker-fixable `needs_revision`
- fixed resubmission returning to `review_pending`

The drill must be API-visible and privacy-safe. Database inspection is not
accepted as proof.
