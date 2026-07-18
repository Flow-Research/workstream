# Checker Trial Failure Catalog

## Purpose

This catalog records the Chunk 10 checker trial outcomes. It is the audit note for the first real sample submissions run through the Week 2 checker framework.

The trial does not add a lifecycle state, a review decision, or a frontend surface. It proves the current backend contracts for clean submissions, worker-fixable checker failures, internal task setup failures, and trusted checker retry.

## Trial Results

| Scenario | Sample Packet Shape | Primary Checker | Routing Recommendation | Task Status | Worker Visibility | Project Manager/Admin API Visibility |
| --- | --- | --- | --- | --- | --- | --- |
| Clean packet | Valid summary, package hash, `answer.md`, evidence, and confidentiality attestation | `check_submission_packet` plus required structural checks | `allow_review` | `review_pending` | Passing worker-visible checker context | Full checker run and result rows through backend API |
| Missing required file | Artifact manifest omits `answer.md` | `check_required_files` | `needs_revision` | `needs_revision` | Required-file message and suggested fix | Full checker result with missing file metadata |
| Forbidden file path | Artifact manifest includes a forbidden path pattern | `check_forbidden_files` | `needs_revision` | `needs_revision` | Generic forbidden-file message without raw sensitive path leakage | Full checker result with forbidden category metadata |
| Weak confidentiality attestation | Attestation is too short and generic | `check_confidentiality_attestation` | `needs_revision` | `needs_revision` | Attestation fix message | Full checker result with failed attestation fields |
| Locked task setup defect | Task loses reviewable acceptance criteria after screening | `check_acceptance_criteria_present` | `task_setup_blocked` | `evaluation_pending` until repair | Hidden from worker as `not_evaluated` with no result rows | Full internal checker route and blocked audit event |

## Routing Notes

Worker-fixable submission failures use `needs_revision`. The worker can see the relevant checker result, worker message, and suggested fix.

Locked task setup failures use `task_setup_blocked`. This is an internal checker routing recommendation for project-manager repair. It is not a task status, not a review decision, and not a worker-facing revision request.

Trusted checker retry is allowed after internal repair. The repair path is:

```text
task_setup_blocked
-> project manager repairs task setup
-> trusted checker retry
-> allow_review
-> review_pending
```

## False-Positive Notes

- `check_low_quality_generated_artifacts` is warning-only by default because simple placeholder wording can be legitimate during early task work. It blocks review only when a project explicitly requires that post-submit checker.
- `check_forbidden_files` intentionally reports a generic worker message. A forbidden path hit could be a false positive if a project intentionally requires a file with a sensitive-looking name, but the safe default is to block and require project-manager clarification.
- `check_confidentiality_attestation` is deterministic and text-based. It can reject a sincere but short attestation; this is acceptable for v0.1 because the required wording is part of the submission contract.

## Missing-Checker Notes

- No semantic answer-quality checker exists yet. Human review still owns correctness.
- No external execution sandbox checker exists yet. Week 2 only records structural and policy-context checks.
- No reputation, ERC-8004 identity, x402, escrow, or payment settlement checker exists in v0.1.
- No project-specific custom checker execution worker exists yet. The current registry is in-process and deterministic.

## Evidence

The API trial is covered by `test_chunk10_checker_trial_runs_sample_submissions_through_real_api` in `backend/tests/test_checkers.py`.
