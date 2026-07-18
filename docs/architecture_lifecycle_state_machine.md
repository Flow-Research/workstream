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

Compensation projection state is separate from task status:

```text
delivery_status: pending_delivery | acknowledged_by_adapter
fulfillment_status: pending | failed | fulfilled
```

Explicitly unpaid contributions create no award and therefore no compensation
projection.

External adapter pipeline states such as `INGESTED`, `FILTERED`, `NORMALIZED`, and `ROUTED` are not v0.1 task lifecycle states. If source adapters are added later, they must normalize accepted external input into the canonical task lifecycle before contributors see it.

## State Definitions

### DRAFT

The task is being created. It is not available to contributors.

Required before leaving:

- project selected
- guide version attached
- source type recorded
- title
- description
- acceptance criteria
- required output

### SCREENING

The task is structurally prepared but not yet released. This is the pre-release
quality gate used to catch weak guides, vague acceptance criteria, missing
submission artifact requirements, missing generated project
pre-submit checker policy, missing approved generated project post-submit checker
policy with matching provenance, missing review policy, or missing revision
policy before contributors see the task.

Required before entering:

- draft task has required fields
- project guide version is attached
- task creator believes the task is ready for independent screening

Required before leaving:

- screening checklist passed
- no open critical- or high-severity readiness finding
- task status snapshot created
- release decision recorded by an authorized covered Project Manager under the
  task-management permission and screening guards

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
- approved generated project PostSubmitCheckerPolicy with matching guide,
  source snapshot, effective project policy, and pre-submit checker provenance
  locked in the task context
- review policy present
- revision policy present
- guide version locked for this task
- source reference recorded when imported
- acceptance criteria frozen; a controlled new guide/task context follows its
  owning policy/rebase path and never rewrites existing locked context

### CLAIMED

A contributor has claimed or been assigned the task.

Required before entering:

- an active published project ContributionPolicyVersion exists
- TaskAssignment freezes that exact version for submitter compensation
- the `accepted_submission` rule is explicit: compensated or unpaid

### IN_PROGRESS

The contributor is actively working on the task.

### SUBMITTED

The contributor submitted a packet.

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
- contributor attestation that the packet does not include prohibited or confidential material

Workstream assigns the immutable submission version server-side. The contributor does not provide submission version, evidence ids, checker results, checker run ids, or guide/policy versions.

### EVALUATION_PENDING

Automated checks are running inside the pre-review gate.

`pre_review_gate` is a checker phase and audit label, not a separate v0.1 task status. The persisted task remains `evaluation_pending` until checker routing moves it to `review_pending`, `needs_revision`, or the internal `task_setup_blocked` repair route.

### REVIEW_PENDING

Automated checks passed or produced only non-blocking warnings. A human reviewer can now review the submission.

Required before entering:

- durable, final CheckerRun is current for the exact Submission version
- CheckerRun outcome is exactly `allow_review`
- CheckerRun references the same artifact hashes as the Submission packet
- no unresolved blocking checker failure is open under the locked post-submit
  checker policy

### NEEDS_REVISION

The contributor-facing state for fixable issues.

This state can be entered from:

- `EVALUATION_PENDING`, when automated checker results contain contributor-fixable blocking failures.
- `REVIEW_PENDING`, when a human reviewer records a `needs_revision` decision.

Required before entering:

- from `EVALUATION_PENDING`: checker run id, blocking checker results, contributor-visible messages, and suggested fixes
- from `REVIEW_PENDING`: immutable `needs_revision` Review, at least one
  unresolved blocking ReviewFinding, reviewer `completed_review` contribution,
  and any applicable reviewer award
- from `REVIEW_PENDING`: the same TaskAssignment remains `active`, with no
  FinalAcceptance or submitter contribution

Before the contributor resumes from a human Review, Workstream appends an
immutable RevisionContextPreparation. Exact prior Submission guide
identity/activation-sequence match with the currently active guide keeps
context. Any different valid active pair rebases forward or backward. Missing,
inconsistent, revoked, or unsafe context blocks for Project Manager repair.
Checker-caused remediation remains CheckerResult-rooted and creates no Review
episode.

A revision context rebase never mutates the prior submitted attempt. It only stamps the next submission attempt. The contributor and reviewer must see the prior version, the next version, and the guide or policy change summary.

### ACCEPTED

The submission is accepted.

Required before entering:

- accepted review decision
- no unresolved blocking checker failure under the locked post-submit checker policy
- evidence present
- reviewer cited evidence supporting acceptance
- no unresolved blocking prior ReviewFinding
- applicable submitter compensation evaluated from the TaskAssignment-frozen
  contribution policy

Required side effects:

- reviewer `completed_review` contribution created with the Review
- immutable FinalAcceptance created from the accepting Review and bound to the
  existing versioned Submission, task, submitter, recording reviewer, and locked
  ReviewPolicy
- submitter `accepted_submission` contribution created from FinalAcceptance,
  the exact TaskAssignment, frozen policy lineage, and artifact hash; it is not
  inferred directly from Review.decision
- applicable awards created independently from the reviewer and submitter
  contribution records
- reputation projection remains deferred

### REJECTED

The task or submission is rejected.

Required before entering:

- rejection review decision
- bounded human rejection reason
- reviewer `completed_review` contribution and any applicable reviewer award
- the same-task TaskAssignment is blocked
- no FinalAcceptance or submitter contribution is created

Required side effects:

- same-task TaskAssignment is `blocked` and bound to the source reject Review
- no other task, assignment, or actor grant changes
- no FinalAcceptance or submitter `accepted_submission` exists

### CANCELLED

The task is cancelled before acceptance. An authorized revision-limit/deadline
or legacy-context closure uses this state with a bounded reason, releases the
assignment, and creates no synthetic Review or contribution.

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
NEEDS_REVISION -> CANCELLED
DRAFT -> CANCELLED
SCREENING -> CANCELLED
READY -> CANCELLED
CLAIMED -> CANCELLED
IN_PROGRESS -> CANCELLED
```

## Forbidden Transitions

No administrative or recovery grant authorizes these transitions:

- `EVALUATION_PENDING -> REVIEW_PENDING` without a durable, final, current CheckerRun
  whose outcome is exactly `allow_review`, whose Submission version is exact,
  and whose artifact binding is verified
- `REVIEW_PENDING -> ACCEPTED` without review decision
- `REVIEW_PENDING -> ACCEPTED` without Review, FinalAcceptance, and both required contribution-source checks
- `NEEDS_REVISION -> ACCEPTED` directly; a replacement Submission must pass
  checker admission and receive a later accepting Review
- `SUBMITTED -> ACCEPTED` directly
- `SUBMITTED -> NEEDS_REVISION` directly without the persisted
  `EVALUATION_PENDING` CheckerRun outcome
- any transition based on artifacts whose hashes differ from the checker run
- compensation projection `pending -> fulfilled` without an immutable payable
  award and fulfillment receipt
- compensation exposure without a contribution record and frozen policy
- adjudication, appeal, acceptance replacement, or reopen transition in v0.1
- fulfillment without an external reference

## Submission Versioning

Each task can have multiple submissions.

```text
submission v1 -> needs revision
submission v2 -> review pending
submission v2 -> accepted
```

Each resubmission must link to the prior submission it supersedes.

Each submitted version keeps its own stamped guide and policy context. A later
revision may rebase forward or backward to the currently active guide. The
immutable preparation records that next-attempt context and never rewrites an
earlier Submission.

## Revision Replay

After a human Review enters NEEDS_REVISION, the next submission must include one
immutable response for each unresolved blocking finding:

```text
ReviewFinding A -> SubmissionFindingResponse X -> evidence Y
ReviewFinding B -> SubmissionFindingResponse Z -> evidence W
```

The later Review appends one FindingResolution for each required prior finding:

- resolved
- unresolved
- not_applicable

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
- matched permission/grant and authority-event id when a registered recovery
  operation participated

No lifecycle change happens silently.

Compensation-award and fulfillment transitions are recorded in their own
records and audit events, not as task lifecycle states.

## Anti-Bypass Rules

- Contributors cannot edit a submitted packet in place. They must create a new submission version.
- Reviewers cannot accept a submission whose checker run belongs to a different submission version.
- Registered recovery cannot erase failed checker results, rejected reviews, or
  prior submissions.
- Guide edits do not retroactively change active tasks; an owning policy/rebase
  path records affected tasks, context, actor authority, and reason.
- A task with disputed evidence, suspected copied material, or compensation conflict
  cannot be accepted until the issue is resolved through its owning review,
  rejection, revision, or compensation-dispute behavior. Authorization recovery does
  not create a product resolution.
