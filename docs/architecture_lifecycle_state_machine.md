# Lifecycle State Machine

## Task States

```text
DRAFT
SCREENING
READY
CLAIMED
IN_PROGRESS
SUBMITTED
EVALUATION_PENDING
REVIEW_PENDING
NEEDS_REVISION
ACCEPTED
REJECTED
CANCELLED
```

Payment status is separate from task status:

```text
NONE
PENDING
PAYOUT_SUBMITTED
PAID
DISPUTED
```

External adapter pipeline states such as `INGESTED`, `FILTERED`, `NORMALIZED`, and `ROUTED` are not v0.1 task lifecycle states. If source adapters are added later, they must normalize accepted external input into the canonical task lifecycle before workers see it.

## State Definitions

### DRAFT

The task is being created. It is not available to workers.

Required before leaving:

- project selected
- guide version attached
- source type recorded
- title
- description
- acceptance criteria
- base amount
- required output

### SCREENING

The task is structurally prepared but not yet released. This is the pre-release quality gate used to catch weak guides, vague acceptance criteria, missing submission artifact requirements, bad payment policy, missing generated project pre-submit checker policy, missing post-submit checker policy, missing review policy, or missing revision policy before workers see the task.

Required before entering:

- draft task has required fields
- project guide version is attached
- payment policy is present
- task creator believes the task is ready for independent screening

Required before leaving:

- screening checklist passed
- no open high-severity readiness finding
- task status snapshot created
- release decision recorded by an authorized reviewer, project manager, or admin

### READY

The task is available for assignment or claiming.

Required before entering:

- task schema valid
- project guide active
- current GuideSourceSnapshot id/hash locked
- GuideSufficiencyReport passed or warnings acknowledged for that source snapshot
- SubmissionArtifactPolicy approved
- EffectiveProjectSubmissionArtifactPolicy hash persisted
- project PreSubmitCheckerPolicy persisted with a compiled bundle hash and locked to that effective project submission artifact policy hash
- task locked to GuideSourceSnapshot id/hash, EffectiveProjectSubmissionArtifactPolicy hash, and PreSubmitCheckerPolicy compiled bundle hash
- PostSubmitCheckerPolicy present
- review policy present
- revision policy present
- payment policy present
- guide version locked for this task
- source reference recorded when imported
- acceptance criteria frozen unless an admin records a guide-correction event

### CLAIMED

A worker has claimed or been assigned the task.

### IN_PROGRESS

The worker is actively working on the task.

### SUBMITTED

The worker submitted a packet.

Required before entering:

- submission summary
- package or output reference
- evidence items
- effective project submission artifact policy loaded
- generated project pre-submit checker policy executed
- no blocking pre-submit failures
- immutable submission version
- content hash for every uploaded artifact
- evidence references bound to submitted artifact hashes
- worker attestation that the packet does not include prohibited or confidential material

Workstream assigns the immutable submission version server-side. The worker does not provide submission version, evidence ids, checker results, checker run ids, or guide/policy versions.

### EVALUATION_PENDING

Automated checks are running inside the pre-review gate.

`pre_review_gate` is a checker phase and audit label, not a separate v0.1 task status. The persisted task remains `evaluation_pending` until checker routing moves it to `review_pending`, `needs_revision`, or the internal `task_setup_blocked` repair route.

### REVIEW_PENDING

Automated checks passed or produced only non-blocking warnings. A human reviewer can now review the submission.

Required before entering:

- checker run exists for the exact submission version
- checker run references the same artifact hashes as the submission packet
- no unresolved blocking checker failure is open under the locked post-submit checker policy

### NEEDS_REVISION

The worker-facing state for fixable issues.

This state can be entered from:

- `EVALUATION_PENDING`, when automated checker results contain worker-fixable blocking failures.
- `REVIEW_PENDING`, when a human reviewer records a `needs_revision` decision.

Required before entering:

- from `EVALUATION_PENDING`: checker run id, blocking checker results, worker-visible messages, and suggested fixes
- from `REVIEW_PENDING`: review decision id and at least one structured review finding

Before the worker resumes, Workstream prepares the next revision context. That preparation checks whether the active project guide or policy context changed since the prior submission was locked. Revision policy decides whether the next attempt keeps the prior context, rebases to the current active context, or is blocked for project-manager repair.

A revision context rebase never mutates the prior submitted attempt. It only stamps the next submission attempt. The worker and reviewer must see the prior version, the next version, and the guide or policy change summary.

### ACCEPTED

The submission is accepted.

Required before entering:

- accepted review decision
- no unresolved blocking checker failure under the locked post-submit checker policy
- evidence present
- reviewer cited evidence supporting acceptance
- no unresolved high or medium prior revision finding
- payment amount calculated from the locked project payment policy

Required side effects:

- contribution record created from accepted submission, accepting review, locked guide version, artifact hash manifest, and acceptance evidence refs
- payment record created or updated from the contribution record
- reputation events reference the contribution record

### REJECTED

The task or submission is rejected.

Required before entering:

- rejection review decision
- rejection reason

### CANCELLED

The task is cancelled before acceptance.

## Allowed Transitions

```text
DRAFT -> SCREENING
SCREENING -> READY
SCREENING -> DRAFT
READY -> CLAIMED
CLAIMED -> IN_PROGRESS
IN_PROGRESS -> SUBMITTED
SUBMITTED -> EVALUATION_PENDING
EVALUATION_PENDING -> REVIEW_PENDING
EVALUATION_PENDING -> NEEDS_REVISION
REVIEW_PENDING -> EVALUATION_PENDING
REVIEW_PENDING -> ACCEPTED
REVIEW_PENDING -> NEEDS_REVISION
REVIEW_PENDING -> REJECTED
NEEDS_REVISION -> SUBMITTED
DRAFT -> CANCELLED
SCREENING -> CANCELLED
READY -> CANCELLED
CLAIMED -> CANCELLED
IN_PROGRESS -> CANCELLED
```

## Blocked Transitions

These require admin override:

- `SUBMITTED -> REVIEW_PENDING` without checker run
- `REVIEW_PENDING -> ACCEPTED` without review decision
- `REVIEW_PENDING -> ACCEPTED` without contribution record creation
- `NEEDS_REVISION -> ACCEPTED` without new submission or explicit finding closure
- `SUBMITTED -> ACCEPTED` directly
- `SUBMITTED -> NEEDS_REVISION` without checker run unless the submission packet cannot be parsed
- any transition based on artifacts whose hashes differ from the checker run
- payment `NONE -> PAID` without accepted task and payment record
- payment exposure without a contribution record
- payment `PENDING -> PAID` without payment reference

## Submission Versioning

Each task can have multiple submissions.

```text
submission v1 -> needs revision
submission v2 -> review pending
submission v2 -> accepted
```

Each resubmission must link to the prior submission it supersedes.

Each submitted version keeps its own locked guide and policy context. If a later revision is rebased to a newer active guide, that rebase is recorded as next-attempt preparation and does not rewrite earlier submission records.

## Revision Replay

When a task enters NEEDS_REVISION, the next submission must include a revision replay:

```text
Finding A -> fixed by change X -> evidence Y -> closed
Finding B -> fixed by change Z -> evidence W -> closed
```

The worker can claim each prior finding as:

- fixed
- disputed
- not_applicable

The reviewer can mark each prior finding:

- closed_fixed
- closed_rebutted
- partially_closed
- still_open
- obsolete

## Audit Requirements

Every transition records:

- task id
- old state
- new state
- actor
- timestamp
- reason
- related submission or review
- related guide version
- related artifact hashes when the transition depends on submitted files
- override id when an admin override was used

No lifecycle change happens silently.

Payment transitions are recorded in the payment ledger and audit log, not as task lifecycle states.

## Anti-Bypass Rules

- Workers cannot edit a submitted packet in place. They must create a new submission version.
- Reviewers cannot accept a submission whose checker run belongs to a different submission version.
- Admin overrides cannot erase failed checker results, rejected reviews, or prior submissions.
- Guide edits do not retroactively change active tasks unless policy allows the change and an admin records the affected tasks and reason.
- A task with disputed evidence, suspected copied material, or payment conflict cannot be accepted until the issue is resolved through review, rejection, revision, payment dispute handling, or an audit-recorded admin action.
