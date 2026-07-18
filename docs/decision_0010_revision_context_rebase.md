# ADR 0010: Revision Context Rebase Uses The Active Project Guide

## Status

Accepted

## Context

Project guidance can change while a task is already in progress or under review.

If rule changes live only in Slack, chat, or memory, contributors can be punished for missing an out-of-band update and reviewers can apply inconsistent standards. If guide changes silently mutate prior submissions, Workstream loses auditability.

Workstream needs both fairness and correctness:

- a submitted attempt must remain tied to the exact guide and policy versions it used
- a revised attempt must use the Project Guide that is active when revision
  preparation freezes the next-attempt context
- the contributor and reviewer must be able to see what changed

## Decision

Submitted attempts are immutable. Each submission remains evaluated against the
locked project guide, checker policy, review policy, and revision policy
versions stamped on that submission.

After a human `needs_revision` Review, Workstream runs an immutable revision
context preparation step before the contributor resumes. The task pipeline owns
the one Project Guide context used by the submitter and reviewer.
`TaskAssignment` stores only `task_id`; every Submission stamps the exact guide
identity, version, and immutable per-project activation sequence used for that
attempt.

Preparation compares the prior Submission's stamped guide identity and
activation sequence with the project's currently active guide pair:

- an exact identity and activation-sequence match keeps the prior context;
- any different internally consistent active pair rebases the next attempt and
  records forward or backward direction, including an older reactivated guide;
- a missing, incomplete, internally inconsistent, revoked, or unsafe active
  pair blocks for covered Project Manager repair.

Version strings are never ordered. RevisionPolicy supplies limit and deadline
inputs but does not choose a stale guide over the currently active authority.

Every revision context preparation must record its outcome. When the next attempt keeps the prior context, Workstream records that no rebase occurred and why. When the next attempt is rebased, Workstream records:

- task id
- prior submission id and version
- prior stamped guide identity, version, and activation sequence
- next frozen guide identity, version, activation sequence, source snapshot,
  and task-execution policy context
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

Contribution terms never rebase through revision context. Submitter terms
remain governed by the `ContributionPolicyVersion` frozen on the
`TaskAssignment`; every `ReviewLease` independently freezes the reviewer
version active when that lease is created.

Tradeoff:

- revision preparation needs an explicit audit record
- revision replay must show context changes, immutable responses, and later resolutions
- services must keep submitted-attempt immutability separate from next-attempt preparation
