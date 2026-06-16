# First User Flows

The first user flows prove that Workstream can run real work from intake to acceptance. These flows come before any advanced routing or settlement.

## Flow 1: Admin Creates A Project

1. Admin creates project.
2. Admin adds guide.
3. Admin sets base amount.
4. Admin approves submission artifact policy.
5. Workstream generates pre-submit checker policy.
6. Admin enables post-submit checker policy.
7. Admin enables review policy.
8. Admin enables revision policy.
9. Admin enables payment policy.
10. Project becomes active.

Acceptance:

- Project cannot become active without guide, base amount, submission artifact policy, generated pre-submit checker policy, post-submit checker policy, review policy, revision policy, and payment policy.
- Submission artifact, checker, review, revision, and payment policies are visible on the project page.

## Flow 2: Operator Creates A Task

1. Operator selects active project.
2. Operator creates task with title, description, expected output, acceptance criteria, base amount, deadline, and difficulty.
3. Workstream validates task against project guide.
4. Task enters `SCREENING`.
5. Screening confirms guide version, task contract, submission artifact requirements, checker policy, review policy, revision policy, payment policy, and reviewability.
6. Task enters `READY`.

Acceptance:

- Missing required fields block `SCREENING`.
- Missing required fields block `READY`.
- Task shows project guide, required artifacts, generated pre-submit checker policy summary, post-submit checker policy, review policy, revision policy, and payment policy.

## Flow 3: Worker Submits Work

1. Worker opens assigned task.
2. Worker attaches output files or links.
3. Worker attaches evidence.
4. Worker writes submission notes.
5. Workstream runs pre-submit checks generated from the effective submission artifact policy.
6. Blocking pre-submit failures return worker-safe fixes and create no submission.
7. When blocking pre-submit checks pass, Worker submits packet.
8. Task enters `SUBMITTED`.

Acceptance:

- Submission cannot be created when blocking pre-submit checks fail.
- Submission cannot be created without required artifacts, evidence references, hashes, and worker attestation defined by the effective submission artifact policy.
- Submission packet is immutable after checks start.

## Flow 4: Automated Checks Run

1. Checker runner loads project policy.
2. Runner executes enabled checks.
3. Results are saved with `passed`, `warning`, or `failed`, plus severity, message, and evidence.
4. If high-severity failures exist, task enters `NEEDS_REVISION`.
5. If no high-severity failures exist, task enters `REVIEW_PENDING`.

Acceptance:

- High-severity failure blocks human review.
- Warnings remain visible to reviewer.
- Every checker result is timestamped.

## Flow 5: Reviewer Reviews Submission

1. Reviewer opens review queue.
2. Reviewer selects `REVIEW_PENDING` task.
3. Reviewer reads guide, task, submission, evidence, and checker results.
4. Reviewer enters structured findings.
5. Reviewer selects accept, needs_revision, or reject.

Acceptance:

- Review cannot be submitted without a decision.
- needs_revision and reject require at least one finding.
- accept requires no unresolved high-severity checker failure.

## Flow 6: Revision Replay

1. Worker opens needs-revision task.
2. Workstream prepares revision context from the revision policy.
3. Worker sees prior guide/policy version, next guide/policy version, and any change summary when the task was rebased.
4. Worker sees each finding as a checklist item.
5. Worker adds fix note and evidence per finding.
6. Worker resubmits.
7. Checkers rerun.
8. Reviewer closes or reopens each finding.

Acceptance:

- Prior review remains visible.
- Context changes are visible before the worker revises.
- Each required finding has a closure state.
- Revision count is tracked against the locked revision policy.
- Resubmission is blocked or rejected when the revision policy limit or deadline says so.

## Flow 7: Accepted Work Creates Contribution Record

1. Reviewer accepts task.
2. Task enters `ACCEPTED`.
3. Contribution record is created from accepted submission, accepting review, guide version, evidence refs, and artifact hashes.
4. Payment record is created or updated as `PENDING`.
5. Worker reputation updates from the contribution record.
6. Project dashboard updates.

Acceptance:

- Accepted task cannot lack contribution record.
- Accepted task cannot lack payment record.
- Payment status is separate from assignment status.
