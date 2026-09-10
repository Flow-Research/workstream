# First User Flows

## Status

These flows describe the target v0.1 behavior, not a list of active endpoints.
Use the [capability ledger](roadmap_status.md) for delivered and remaining work.
The review and revision portions are the planned v0.1 contract and remain
unavailable until their owning REV chunks, exact AUTH activation, and REV-13
joint release complete. Earlier project/task/submission/checker behavior keeps
its separately recorded implementation status.

The detailed review flow below describes `human_review_required=true`, the
default in the existing versioned ReviewPolicy setting. False is a separately
planned post-check TASK handoff to authorized FinalAcceptance and CON, without
human queues, leases, Reviews or reviewer contributions. Required checks and
exact immutable evidence still apply. The [shared acceptance contract](spec_review_lifecycle.md#finalacceptance)
defines both triggers; runtime remains unavailable until its implementation
and exact shared release proof land.

The first user flows prove that Workstream can run real work from intake to acceptance. These flows come before any advanced routing or settlement.

## Flow 1: Project Manager Creates A Project

POL-04B delivers the automatic compilation and immutable draft/findings stop
below. The remaining manager proposal view, correction, fresh-generation rerun
and approval follow POL-05A → AUTH-12F4 → POL-05B; the complete activation flow
below describes the target lifecycle, not a claim that those surfaces are live.

1. A system-scoped Project Manager creates the project.
2. Project owner provides open-ended guide material and business terms.
3. An authorized covered Project Manager adds guide metadata with at least one
   ordinary-text task example in PostgreSQL and uploads the assigned
   PDF/DOCX/PPTX guide originals to ArtifactStore/S3.
4. Once ART commits every assigned original guide document,
   Workstream automatically queues its authorized unified compilation in Celery.
5. One unified compilation assesses sufficiency and proposes artifact,
   pre-submission and post-submission policy components from the exact guide
   and catalogue snapshots together with every supplied task example.
6. Blocking sufficiency gaps stop the setup pipeline and create clarification requests for the project owner.
7. An authorized covered Project Manager acknowledges non-blocking sufficiency warnings.
8. Workstream finalizes the exact compilation and its permitted projections.
   The finalized setup run and receipt remain immutable; no second derivation
   agent runs to fill the post-submit component.
9. An authorized covered Project Manager reviews and approves the derived submission artifact policy.
10. Workstream persists the effective project submission artifact policy hash.
11. Workstream compiles, persists, and locks the project `PreSubmitCheckerPolicy`.
12. A separate operation deterministically projects and compiles the post-submit
    component from that same unified result; it does not execute a checker.
13. An authorized covered Project Manager approves the current compiled
    post-submit checker policy.
14. If correction is requested instead, Workstream supersedes and retains the
    unapproved compiled output, preserves its policy hash/body plus bounded
    actor/reason/time and redacted derivation metadata. Correction has separate
    operation provenance; new model output requires a new unified compilation
    generation with bounded feedback for a known terminal result, never
    resuming the finalized run or restarting an uncertain provider operation. An
    unchanged replacement fails closed, and activation remains blocked.
15. An authorized covered Project Manager enables review policy.
16. An authorized covered Project Manager enables revision policy.
17. The owning Finance Authority publishes the ContributionPolicy version
    selected by the active policy, with explicit submitter and reviewer
    compensated/unpaid rules.
18. Project becomes active.

Acceptance:

- Project cannot become active without guide, immutable guide source snapshot,
  passed or acknowledged guide sufficiency report for that immutable guide
  source snapshot, submission artifact policy, effective project submission
  artifact policy hash, project pre-submit checker bundle hash, an approved
  current compiled project post-submit checker policy with matching guide,
  source snapshot, effective project policy, and pre-submit checker provenance,
  review policy, revision policy, and the current published version of the active
  `ContributionPolicy` containing exactly one explicit
  compensated/unpaid rule for each of `accepted_submission` and
  `completed_review`.
- Guide-policy activation and contribution-policy publication are independently
  governed. Project activation requires both to be complete and binds the
  exact published version. Task readiness locks it; `TaskAssignment` copies the
  task lock, Submission stamps the attempt version, and `ReviewLease` copies
  the Submission stamp without policy selection.
- Normal setup starts from guide/source capture and one authorized compilation
  request, not separate requests for sufficiency and each policy derivation.
- All pre/post capability-gap dispositions block projection/approval/activation.
  Explicit approved `human_review` requirements remain valid, but unsupported
  automation is never silently relabelled. An uncertain provider outcome stays
  blocked without a fresh call until same-operation recovery is supported.
- Submission artifact policy is Workstream-derived and approved by an
  authorized covered Project Manager; project owners do not author or approve
  the machine policy schema directly.
- This flow uses unified compilation and its deterministic verified-report
  projection. Manual reports and policies retain separate diagnostic/manual
  provenance and cannot replace or satisfy unified compilation evidence.
- Submission artifact, checker, review, and revision policies are visible on the
  project page; contribution policy/version is an independently governed
  project record.

## Flow 2: Project Manager Creates A Task

1. A covered Project Manager selects the active project.
2. The Project Manager creates a task with title, description, source reference, acceptance criteria, rejection criteria, deadline, and difficulty.
3. Workstream validates the task source and reviewability fields, then confirms the task fits the active project guide and policy bundle.
4. Task enters `SCREENING`.
5. Screening locks the guide source snapshot id/hash, effective project
   submission artifact policy hash, project pre-submit checker bundle hash, and
   approved provenance-matched project post-submit checker policy reference,
   then confirms the task contract, review policy, revision policy, and
   reviewability.
6. Task enters `READY`.

Acceptance:

- Missing required fields block `SCREENING`.
- Missing required fields block `READY`.
- Task shows project guide, required artifacts, generated project pre-submit
  checker policy summary, permission-appropriate post-submit checker policy
  summary, review policy, and revision policy. After claim, the contributor sees
  the Assignment-frozen submitter compensation terms.

## Flow 3: Contributor Submits Work

1. Contributor opens assigned task.
2. Contributor uploads one outer ZIP containing every required output and evidence file.
3. Contributor writes the required summary and attestation.
4. Workstream safely inspects and manifests the ZIP in bounded private scratch.
5. Workstream executes the single effective pre-submission plan: platform defaults plus the task-locked Project Guide policy.
6. Failure returns bounded same-request `pre_submission_checker_failed` details and creates no submission or durable artifact.
7. Passing bytes are stored and independently verified, producing a ready admission.
8. Contributor creates the immutable Submission by consuming that admission under fresh authority.
9. Task enters `SUBMITTED`.

Acceptance:

- Submission cannot be created when blocking pre-submit checks fail.
- Blocking pre-submit failures are not review decisions and never return `accept`, `needs_revision`, or `reject`.
- Submission cannot be created without required artifacts, evidence references, hashes, and contributor attestation defined by the locked project pre-submit checker policy.
- Submission packet is immutable after checks start.

## Flow 4: Automated Checks Run

1. Checker runner validates the submission-stamped locked `PostSubmitCheckerPolicy` id/version/hash/body.
2. Runner executes enabled checks from that locked policy body.
3. Results are saved with `passed`, `warning`, or `failed`, plus severity, message, and evidence.
4. Contributor-fixable checker failures route the Task to `NEEDS_REVISION` with
   `CheckerResult` lineage and no Review or reviewer contribution.
5. Setup or provenance defects keep the Task `evaluation_pending` on the
   internal `task_setup_blocked` repair route.
6. For locked `human_review_required=true`, only a durable, final, current `CheckerRun` outcome of `allow_review` admits
   the exact immutable Submission with verified binding facts and moves the
   Task to `REVIEW_PENDING`.

Acceptance:

- A retry, superseded run, different Submission, non-final result, or outcome
  other than `allow_review` cannot admit human review.
- Warnings remain visible to reviewer.
- Every checker result is timestamped.

## Flow 5: Reviewer Reviews Submission

This flow and its downstream human-review/revision effects apply only to the
human-required branch, not a project with locked false.

1. Reviewer current work returns an active lease, one server-selected offer, or none.
2. Reviewer claims the offer and receives the exact ReviewPacketManifest.
3. Reviewer reads the leased Submission's stamped guide context, evidence, and checker results.
4. Reviewer enters immutable blocking/advisory findings where applicable.
5. Reviewer selects accept, needs_revision, or reject.
6. Workstream atomically appends Review history, consumes the lease, closes the
   queue entry, and runs the CON reviewer operation for `completed_review`.
7. For `accept`, REV then creates internal FinalAcceptance, applies accepted
   Task and completed Assignment effects, and runs the CON submitter operation
   for `accepted_submission` from that fact.

Acceptance:

- Review cannot be submitted without a decision.
- needs_revision requires at least one blocking finding; reject requires a
  bounded human reason and may include findings.
- the leased Submission must retain its exact durable, final, current
  `allow_review` CheckerRun admission and verified binding facts.
- Every valid human decision has exactly one reviewer contribution.
- Accept sets Task `accepted`, Assignment `completed`, and has exactly one
  FinalAcceptance and one submitter contribution.
- Needs revision sets Task `needs_revision`, keeps Assignment `active`, and has
  neither FinalAcceptance nor submitter contribution.
- Reject sets Task `rejected` with a bounded human reason, blocks only the
  same-task Assignment with its source Review, changes no grant or unrelated
  task, and has neither FinalAcceptance nor submitter contribution.
- FinalAcceptance has no manual API/action and no adjudication/reopen path.
- Only accept has a submitter contribution.

## Flow 6: Human Review Revision Replay

1. Contributor opens a needs-revision task rooted in an immutable
   `Review(needs_revision)`.
2. Workstream prepares immutable context from every applicable currently active
   Project Guide and policy selector.
3. Exact prior component matches keep; every changed valid component rebases
   together; unsafe context blocks the whole preparation.
4. Contributor sees the frozen preparation and each unresolved blocking finding.
5. Contributor appends one SubmissionFindingResponse and optional evidence per required finding.
6. Contributor resubmits.
7. Checkers rerun.
8. Reviewer appends one FindingResolution per required prior finding.

Checker-caused remediation is separate: it retains `CheckerResult` lineage,
creates no Review, ReviewFinding, SubmissionFindingResponse, FindingResolution,
or reviewer contribution, and returns through the normal submission/checker
spine before human review.

Acceptance:

- Prior review remains visible.
- Context changes are visible before the contributor revises.
- Each required finding has an immutable response and later resolution.
- Revision count is tracked against the locked revision policy.
- A reached limit/deadline blocks resubmission but never auto-rejects or
  auto-closes the task; manager cancellation is a separate planned command.

## Flow 7: Accepted Work, FinalAcceptance, And Submitter Contribution

Both planned triggers invoke one shared acceptance operation. The human branch:

1. Reviewer accepts task.
2. The reviewer `completed_review` contribution created after the Review
   remains immutable.
3. REV creates immutable FinalAcceptance from the accepting Review.
4. The Task enters `ACCEPTED` and the TaskAssignment becomes `completed`.
5. The CON submitter operation creates `accepted_submission` only from
   FinalAcceptance, TaskAssignment, frozen policy lineage, and artifact hash.
6. The `completed_review` and `accepted_submission` rules from the applicable
   frozen ContributionPolicyVersion are evaluated independently; explicit
   unpaid rules create no awards.
7. External fulfillment runs after commit; reputation projection is deferred.

When the Submission's locked ReviewPolicy has `human_review_required=false`,
TASK instead validates current successful required checks, the exact immutable
ZIP and output references, zero applicable approved `human_review` requirements
and fresh routing authority. It invokes the same operation directly: Task
`ACCEPTED`, assignment `completed`, FinalAcceptance, submitter contribution,
applicable submitter awards, audit and outbox commit together. It never enters
`REVIEW_PENDING` or creates a Review, ReviewLease, reviewer contribution or
reviewer award. Checker output remains evidence, not a human decision.

Correctable checker failures follow ARCH-04F under the locked attempt context;
infrastructure/setup uncertainty never accepts or invents a human revision.
This false branch is planned, not currently enabled. Fulfillment remains
post-commit for either trigger and cannot change accepted work.

Acceptance:

- Accepted task cannot lack FinalAcceptance or its submitter contribution record.
- Every accepted Review cannot lack its reviewer contribution record.
- A payable contribution cannot lack its immutable CompensationAward and
  fulfillment projection; an explicit unpaid policy creates no award.
- Compensation fulfillment status is separate from assignment status.
