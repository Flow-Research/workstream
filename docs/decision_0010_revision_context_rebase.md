# ADR 0010: Human Revision Rebase Uses The Complete Active Project Context

## Status

Accepted

## Context

Project guidance can change while a task is already in progress or under review.

If rule changes live only in Slack, chat, or memory, contributors can be punished for missing an out-of-band update and reviewers can apply inconsistent standards. If guide changes silently mutate prior submissions, Workstream loses auditability.

Workstream needs both fairness and correctness:

- a submitted attempt must remain tied to the exact guide and policy versions it used
- a revised attempt must use the complete applicable project context active
  when revision preparation freezes the next attempt
- the contributor and reviewer must be able to see what changed

## Decision

Submitted attempts are immutable. Each submission remains evaluated against the
locked project guide, checker policy, review policy, and revision policy
versions stamped on that submission.

After a human `needs_revision` Review, Workstream runs an immutable revision
context preparation step before the contributor resumes. The task pipeline owns
the one Project Guide context used by the submitter and reviewer.
`TaskAssignment` stores only `task_id` for guide-context linkage, while its
separate submitter ContributionPolicyVersion selector follows the guarded rule
below. Every Submission stamps the exact guide identity, version, and immutable
per-project activation sequence used for that attempt.

Preparation compares the prior Submission's stamped context with the complete
currently active applicable project context:

- Project Guide identity, version, source snapshot, and activation sequence;
- effective SubmissionArtifactPolicy;
- generated pre-submit and approved post-submit checker policies;
- ReviewPolicy and RevisionPolicy;
- task-template and task-execution policy context; and
- the ContributionPolicyVersion in the prior attempt's locked context and the
  current guide-bound version validated through CON.

For every component:

- an exact identity/version/activation match keeps the prior value;
- any changed internally consistent active value rebases the next attempt and
  records forward or backward direction where chronology applies, including an
  older intentionally reactivated version;
- a missing, incomplete, crossed-project, internally inconsistent, revoked,
  suspended where new freezes are prohibited, or unsafe value blocks the whole
  preparation for covered Project Manager repair.

Preparation publishes one complete context. It cannot rebase the guide while
retaining a stale submitter contribution policy or otherwise mix components
from incompatible contexts.

Version strings are never ordered. RevisionPolicy supplies limit and deadline
inputs but does not choose a stale guide over the currently active authority.

Every revision context preparation must record its outcome. When the next attempt keeps the prior context, Workstream records that no rebase occurred and why. When the next attempt is rebased, Workstream records:

- task id
- prior submission id and version
- prior stamped guide identity, version, and activation sequence
- next frozen guide identity, version, activation sequence, source snapshot,
  and task-execution policy context
- prior and next effective submission-artifact, pre-submit checker,
  post-submit checker, review, revision, task-template/task-execution, and
  submitter ContributionPolicyVersion references
- outcome `kept`, `rebased`, or `blocked` and forward/backward direction where applicable
- rebase reason
- guide or policy change summary shown to the contributor
- actor or system process that prepared the revision context
- audit event id

Task Context returns the immutable preparation head and digest rather than a
moving active-guide pointer. The contributor must see the old context, new
context, and change summary before submitting. Submission N+1 acknowledges and
stamps that preparation exactly. A later guide activation cannot silently drift
an already prepared attempt.

No guide rebase occurs during review. The reviewer consumes the guide and policy
context stamped on the single Submission covered by the active ReviewLease. History
shows the guide transition without changing any prior Submission.

Publication or activation alone never mutates an active assignment, prepared
attempt, Submission, or ReviewLease. `accept` and `reject` finish under the
exact context already frozen for that attempt. Human `needs_revision` is the
only in-progress synchronization boundary for the complete next-attempt
context.

The ReviewLease that produced `needs_revision` and its reviewer
`completed_review` ContributionRecord remain governed by that lease's frozen
ContributionPolicyVersion. Revision preparation records prior/next lineage and,
when the complete current context changes, atomically rebases the continuing
Task and TaskAssignment for the next submission attempt. The next Submission
and ReviewLease use the rebased version. Prior Submissions, ReviewLeases,
Reviews, ContributionRecords, and
CompensationAwards are never rewritten.

The human `needs_revision` Review, reviewer contribution and applicable award,
task and assignment effects, initial kept/rebased/blocked preparation, audit and
outbox effects, and contributor-visible state commit once or roll back together.
Checker-caused remediation remains a separate CheckerRun-rooted path and does
not perform this human revision rebase.

Out-of-band guidance has no acceptance force until it is encoded in one of:

- project guide
- checker policy
- review policy
- revision policy
- task template
- checker implementation governed by the checker policy

Acceptance-affecting checker implementation changes must be tied to visible guide, policy, or checker-policy context. When those changes affect a rebased revision attempt, the contributor-visible change summary must describe the new requirement without exposing private detection details.

## Consequences

Positive:

- contributors are not expected to monitor chat to discover rule changes
- reviewers can see which standards governed each attempt
- guide and policy updates can improve future revisions without mutating prior submissions
- repeated lessons become durable guide, checker, review, revision, or template changes

- contributors receive one coherent current context after a human revision
  boundary instead of new guide requirements paired with stale economic terms
- completed reviewer and award history remains governed by its original
  ReviewLease freeze

Tradeoff:

- revision preparation needs an explicit audit record
- TaskAssignment policy lineage needs an explicit guarded rebase rather than a
  lifetime immutable selector
- revision replay must show context changes, immutable responses, and later resolutions
- services must keep submitted-attempt immutability separate from next-attempt preparation
