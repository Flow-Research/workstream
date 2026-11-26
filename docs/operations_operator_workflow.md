# Operator Workflow

## Status

Existing project and task operations retain their owning implementation status.
Human review and its revision/contribution behavior below remain planned until
owning REV chunks, exact AUTH activation and the joint release complete. Checker
revision preparation, PM repair and durable timeout rejection/release are
implemented through TASK. Automated acceptance has its separately recorded
availability; see the capability ledger.

Contributor, management and operational task queues have exact-authorized public
reads with distinct fields and signed pagination. Contributor/Manager detail and
requirements are public through ARCH-03C5. ARCH-03C6 exposes separate Manager,
system-Operator and Audit Authority locked-context reads with exact current
grants. ARCH-03C7 exposes bounded task history only to covered Audit Authority;
Operator grants do not grant that access. See the
[capability ledger](roadmap_status.md) for current availability.

## Roles

### Project Manager

Creates projects when system-scoped and manages guides, tasks,
submission/checker configuration, review/revision configuration, and
contributor grants only for covered projects. This grant cannot publish
contribution policy or bind compensation adapters.

### Contributor

An exact-project Submitter grant permits queue/claim/submission candidates. The
person is a Contributor in product, lifecycle, assignment, and attribution
language.

### Reviewer

Reviews checker-passed submissions and issues accept, needs_revision, or reject decisions.

### Operator

Inspects runtime state and performs only registered reasoned recovery. Operator
does not issue grants, approve policy, or record review decisions by that grant.

### Access Administrator

Manages actors, identity links, and administrative grants. This grant does not
manage project work, edit AUTH's closed permission/action catalog, or change
action availability.

### Finance Authority

Publishes contribution policy and compensation-adapter bindings, and tracks
compensation awards, delivery, fulfillment, failure, and dispute state.

### Audit Authority

Reads authorized immutable and operational evidence without mutation.

## Cross-Role Daily Operating Loop

```text
1. Project Manager: check the covered-project task queue.
2. Project Manager: create drafts, then screen and release tasks under project lifecycle guards.
3. Contributor: claim a ready task under an exact-project Submitter grant.
4. Reviewer: consume current work as active lease, one server-selected offer, or none.
5. Reviewer and Submitter: issue and respond to `needs_revision`; Project Manager
   observes the covered-project queue without recording either party's action.
6. Finance Authority: reconcile contribution-policy, award, delivery, and
   fulfillment records through WS-CON-owned commands.
7. Project Manager: apply covered project repair where eligible. Operator may
   invoke only an exact registered, reasoned recovery action for infrastructure
   or setup failure. Submitter-fixable blockers return as `needs_revision`.
8. Project Manager: update covered-project lessons learned.
```

## Task Creation Workflow

1. Select the covered project.
2. Create a draft with its title and description, adding task-local acceptance
   criteria and skill tags when useful. Task-local criteria are optional,
   including through screening/release; the guide supplies governed requirements.
   An active guide is not required to create the draft.
3. Before screening and release, confirm the active approved guide and policies,
   including the required artifact outputs and a published ContributionPolicyVersion
   with explicit submitter and reviewer compensated/unpaid rules. Task readiness
   locks that policy before `READY`; Assignment copies it and Submission stamps
   the attempt value. ReviewLease will later copy that immutable stamp.
4. Screen the draft under the current project guide and lifecycle guards.
5. Release the screened task to `READY` for contributor claim.

## Contributor Submission Workflow

1. Read project guide.
2. Read task requirements.
3. Complete work outside Workstream.
4. Prepare submission packet.
5. Attach evidence.
6. Submit.
7. Wait for automated checks.
8. If NEEDS_REVISION, use revision replay.

## Revision Workflow

1. Read the frozen RevisionContextPreparation and every unresolved blocking finding.
2. Append one SubmissionFindingResponse per required finding.
3. Attach finalized evidence where needed.
4. Resubmit against the exact preparation head/digest.
5. The normal checker spine reruns.
6. The later reviewer appends one FindingResolution per required finding.

## Acceptance Workflow

1. Reviewer accepts submission.
2. REV appends the immutable Review and any submitted findings or resolutions,
   consumes the ReviewLease, and closes the ReviewQueueEntry.
3. CON records reviewer `completed_review` directly from Review and evaluates
   the ReviewLease-frozen contribution policy.
4. REV records one internal FinalAcceptance for the exact task, Submission,
   submitter, reviewer, and locked ReviewPolicy.
5. REV moves the task to ACCEPTED and completes the TaskAssignment.
6. CON records submitter `accepted_submission` only from FinalAcceptance and
   evaluates the TaskAssignment-frozen contribution policy.
7. Frozen contribution policies create awards only for payable contributions;
   explicit unpaid rules create none.
8. Finance Authority follows post-commit delivery only for created awards.
9. Reputation projection remains deferred.

The Review request owns one commit for Review, FinalAcceptance, task effects,
contributions, awards, audit, and outbox. There is no manual FinalAcceptance
command and no adjudication/reopen step in v0.1.

## Rejection Workflow

1. Reviewer rejects submission or task.
2. Review must include a bounded human rejection reason.
3. REV sets the Task to canonical `rejected`, blocks only the same-task
   TaskAssignment, and binds that block to the reject Review. It changes no
   actor grant or unrelated task.
4. The frozen reviewer contribution award rule determines whether the resulting
   `completed_review` contribution creates a `CompensationAward`; rejection
   creates no submitter `accepted_submission` contribution.

For `needs_revision`, REV instead sets the Task to `needs_revision`, keeps the
same TaskAssignment `active`, and creates no FinalAcceptance or submitter
contribution. `closed/review_rejected` is not a canonical task state.

## Revision Recovery

- A covered Project Manager may append an exact context-repair successor;
  checker-rooted repair is public and human-rooted integration remains planned.
- Each fixable failure with another revision remaining starts a fresh PostgreSQL-time window using
  the failed attempt's locked RevisionPolicy. Only immutable resubmission ends
  it. Setup-blocked rebase pauses the allowance and publishes durable PM-attention
  outbox evidence visible in the covered PM task detail; repair resumes only
  remaining time or preserves a running deadline. Upload, replay
  and infrastructure retry do not spend time while paused or reset a window.
- At expiry, the authorized durable TASK delivery handler records an immutable rejection
  receipt, marks the assignment `revision_expired`, releases it and returns the
  task to `ready` without Review or economic facts. Final-attempt failure
  records exhaustion and releases immediately, without another window. Anyone
  eligible can claim a new assignment at round 0; no contributor-count cap applies.
- Checker expiry/recovery is implemented. #554 owns future human decision
  integration with the same intended policy. Provision the exact expirer
  service and run Celery Beat and outbox delivery processes as described in
  [Revision Replay](operations_revision_replay.md#limits-and-recovery).
- Planned Operator closure applies only to evidence-linked unrecoverable
  historical human context. Operator authority never records a human Review
  or adjudication decision.

## Terminal Checker Infrastructure Recovery

1. Use
   `GET /api/v1/operations/projects/{project_id}/checker-retry-sources` with an
   active system Operator grant. Follow the signed cursor when present; each
   page revalidates current authority.
2. Select only an `eligible` finalized post-submit `infrastructure_failed`
   source. `retried` identifies the retained successor. `not_current` is
   historical evidence and cannot be retried.
3. Confirm the named infrastructure problem is restored, then call
   `POST /api/v1/operations/projects/{project_id}/checker-runs/{run_id}/retry`
   with a bounded reason and a new UUID `Idempotency-Key`.
4. On response loss, repeat the exact project, run, reason and key. Workstream
   rechecks current Operator authority and returns the same immutable receipt
   and successor without adding another run, retry event or initiation audit.

This operation preserves the failed run and creates no Review, acceptance,
contribution or award. It refuses queued, running, completed, stale and foreign
sources. A dead-lettered delivery with an uncertain effect is not a known
terminal failure. Use the separate reconciliation flow below for the two
supported post-submit deliveries.

## Uncertain Post-Submit Delivery Reconciliation

An active system Operator can inspect finalized uncertain request and completion
deliveries through
`GET /api/v1/operations/projects/{project_id}/post-submit-deliveries`.
Follow its signed cursor to read the next bounded page; each request checks
current authority. The response exposes the delivery identity, a closed error
code, source classification and any reconciliation child. It does not expose
raw event payloads, exception text, artifact contents or provider details.

| Classification | Meaning and permitted action |
|---|---|
| `committed` | The source owner verifies the exact retained checker result or routing effects. Reconciliation acknowledges those facts without another checker execution or acceptance. |
| `retry_safe` | Current durable facts prove the original source has no execution or routing effect. Reconciliation may invoke the existing owner after checking the facts again under its locks. |
| `unresolved` | Facts are incomplete, stale or uncertain. Keep the delivery held until an Operator investigates. For an expired checker attempt, an Operator can explicitly abandon the unknown result and request a successor. |

For a `committed` or `retry_safe` source without an existing child, send a bounded
reason and one UUID `Idempotency-Key` to
`POST /api/v1/operations/projects/{project_id}/post-submit-deliveries/{event_id}/reconcile`.
This schedules one durable reconciliation child; it does not synchronously run
the checker or accept the Submission. On response loss, repeat the exact project,
event, action, reason and key. Fresh authority is required for replay, which returns the
same child. Every different key conflicts once a child exists.

For a confirmed expired attempt whose result remains unknown, use
`workstream operations delivery reconcile PROJECT_ID EVENT_ID --abandon-unknown --reason REASON --idempotency-key UUID`.
API and MCP callers supply `"action": "abandon_unknown"` in the reconciliation body.
The successor uses the same Submission. The original attempt keeps its unknown outcome.

After a child is scheduled, `source.classification` records the scheduling
decision, while `reconciliation_state` reports the child's current progress or
outcome. For example, a `retry_safe` source can have an `acknowledged` child.

The OUTBOX handler rechecks source facts before acting. A committed false-policy outcome
retains its original FinalAcceptance, submitter ContributionRecord and award set;
reconciliation never fabricates a Review or duplicates those effects. The
original UNKNOWN delivery remains immutable. If the child also becomes UNKNOWN,
the read reports it as held and no further child is allowed. Other uncertain
event types remain outside this recovery surface. The full hosted interruption
drill is still required; focused source tests do not establish deployed recovery.

## Lessons Learned

Every project maintains lessons learned:

- common failure
- root cause
- new checker needed
- guide update needed
- reviewer policy update needed
- revision policy update needed
- contribution policy update needed

This is how Workstream compounds operational knowledge.

Each lesson links to an operating source:

- checker failure
- reviewer finding
- rejected task
- repeated needs-revision loop
- compensation fulfillment reconciliation issue
- user/operator incident

Lessons are not just notes. They become one of:

- guide update
- checker update
- reviewer workflow update
- queue policy update
- revision policy update
- contribution policy update
- risk register update
