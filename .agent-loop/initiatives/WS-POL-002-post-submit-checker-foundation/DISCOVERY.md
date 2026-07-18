# Discovery: WS-POL-002 - Post-Submit Checker Foundation

## Current Code Path

The backend already has a durable post-submit checker gate.

Current runtime chain:

```text
Submission finalization
-> task status evaluation_pending
-> CheckerService.run_submission_checkers
-> locked PostSubmitCheckerPolicy id/version/hash/body validation
-> registered deterministic checker execution
-> durable CheckerRun and CheckerResult rows
-> review_pending | needs_revision | internal blocked/retry route
```

Key files discovered:

- `backend/app/modules/projects/post_submit_policy.py`
- `backend/app/modules/projects/models.py`
- `backend/app/modules/projects/service.py`
- `backend/app/modules/tasks/service.py`
- `backend/app/modules/tasks/models.py`
- `backend/app/modules/checkers/runner.py`
- `backend/app/modules/checkers/service.py`
- `backend/app/modules/checkers/models.py`
- `backend/tests/test_checkers.py`

## Current Default Post-Submit Checkers

`DEFAULT_DURABLE_CHECKERS` currently contains:

- `check_submission_packet`
- `check_policy_context_present`
- `check_evidence_present`
- `check_evidence_integrity`
- `check_required_files`
- `check_forbidden_files`
- `check_confidentiality_attestation`
- `check_low_quality_generated_artifacts`

The checker registry also includes `check_acceptance_criteria_present`, which
is a setup/readiness checker and is not part of the default durable list unless
a policy requires it.

## Current Policy Shape

`PostSubmitCheckerPolicy` is stored in the physical `checker_policies` table
and is attached to a project guide version.

Current canonical body fields:

- `schema_version`
- `project_id`
- `guide_version`
- `default_checkers`
- `required_checkers`
- `warning_checkers`
- `execution_checkers`
- `blocking_severities`

The policy hash is a canonical JSON hash of the policy body.

Task screening locks:

- post-submit checker policy id
- post-submit checker policy version
- post-submit checker policy hash
- post-submit checker policy body

Submissions copy that locked policy context from the task.

Checker runs copy the locked policy context from the submission.

## What Is Already Correct

- Post-submit checker runtime is separated from pre-submit intake.
- Pre-submit failures prevent submission creation.
- Post-submit failures happen after finalization and create durable checker
  evidence.
- The persisted post-submit evaluation status is `evaluation_pending`.
- Successful gate results route to `review_pending`.
- Worker-fixable checker failures route to `needs_revision`.
- Internal setup defects and trusted checker infrastructure failures can stay
  hidden from workers.
- Task/submission/checker-run provenance is locked to the post-submit policy
  id/version/hash/body.
- Guide activation already validates that a post-submit checker policy exists,
  hashes correctly, and references registered checkers.

## Gaps

The missing part is setup-time policy generation and approval.

Current gaps:

- `ProjectGuideCreate` and `ProjectGuideUpdate` still accept manual
  `post_submit_checker_policy` input.
- There is no `PostSubmitCheckerPolicyDerivationAgent`.
- There is no post-submit policy compiler equivalent to the pre-submit compiler
  contract.
- Project-specific post-submit checker choices are not derived from the guide
  source material.
- Unsupported project-specific checker needs are not represented as explicit
  setup blockers.
- Policy visibility exists through downstream locked-context/checker-run
  responses, but setup visibility for generated post-submit policy derivation is
  not yet first-class.
- The Terminal Benchmark live API drill proves current post-submit execution,
  not derived post-submit policy setup.

## Constraints From Existing Architecture

- Post-submit policy must remain project-scoped.
- Task-specific checker generation is explicitly rejected.
- Default Workstream checkers cannot be weakened.
- Runtime must use deterministic checkers, not an agent.
- Celery is the correct setup/job boundary for long-running derivation work.
- The Flow authentication boundary remains external; Workstream only verifies
  tokens and uses local actor/profile records for product authorization.
- No backward compatibility layer should preserve obsolete request fields once
  the new path exists.

## Implementation Implication

WS-POL-002 should not redesign the runtime gate from scratch. It should extend
the project setup pipeline so post-submit policy is derived, compiled, approved,
locked, visible, and proven with APIs the same way pre-submit policy now is.
