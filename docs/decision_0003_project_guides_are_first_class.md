# ADR 0003: Project Guides Are First-Class Objects

## Status

Accepted

## Context

Different projects use different language and acceptance rules, but they share the same lifecycle.

If project rules live only in chat or loose markdown, operators and reviewers will repeat avoidable mistakes.

## Decision

Every active Workstream project must have a versioned project guide attached to its configuration.

The project guide is the human-facing project source of truth. It may be markdown, an imported document, or a URL-backed guide. Contributors and reviewers use it to understand the project purpose, quality bar, instructions, examples, reviewer rubric, and common rejection reasons.

Runtime enforcement uses approved machine-readable policies attached to the guide version. Workstream must not reread guide prose at submission time and guess what to enforce.

The guide drives:

- task requirements
- submission artifact policy
- guide source snapshot and effective project submission artifact policy
- project pre-submit checker policy generated from the effective project submission artifact policy
- post-submit checker policy
- review policy
- revision policy
- common rejection reasons

The submission artifact, checker, review, and revision policies are guide-version
policies. They must be tied to the project guide version they govern, not only
to the project.

Project guide activation requires the guide plus its required policy context before work can lock against it:

- guide source snapshot
- guide sufficiency report
- submission artifact policy
- effective project submission artifact policy hash
- project pre-submit checker bundle hash
- post-submit checker policy
- review policy
- revision policy

The Workstream-derived submission artifact policy defines project-level intake
rules. Project owners provide open-ended project material and business terms.
Workstream captures an immutable guide source snapshot, evaluates guide
sufficiency, derives the machine policy, and an authorized covered Project
Manager approves the internal policy bundle. Workstream combines that policy
with non-bypassable Workstream default artifact rules to create the effective
project submission artifact policy, then generates the project pre-submit
checker policy from that effective project submission artifact policy. Tasks
lock references to the applicable guide snapshot, effective project submission
artifact policy hash, and pre-submit checker bundle hash.

Authorization for this approval is governed by ADR 0012. Historical role labels
from the pre-ADR-0012 runtime do not grant product authority.

Blocking pre-submit failures prevent submission creation. They do not create durable post-submit checker runs and they do not create human review decisions.

Revision policy is not optional. It defines revision limits, revision deadlines,
allowed resubmission states, and reviewer-return preference. Reaching a limit or
deadline blocks further preparation and submission; it never creates a reject
Review. A covered Project Manager may later use the reason-bound administrative
closure defined by the active review lifecycle contract.

Guide and policy changes do not silently mutate submitted attempts. A submitted
attempt stays tied to the guide and policy versions stamped on that Submission.
After a human `needs_revision` Review, preparation compares the prior
Submission's complete stamped context with the project's complete applicable
active Project Guide, submission/checker, review, revision, task-execution, and
submitter ContributionPolicy context. Exact component matches are kept, every
changed valid component is rebased together, and missing or unsafe context
blocks the whole preparation for manager repair. RevisionPolicy does not select
a stale context. The reviewer always uses the context stamped on the exact
leased Submission and performs no separate rebase.

Rules that affect acceptance judgment may be encoded in the human-facing
project guide, review policy, revision policy, task template, or checker
implementation. Rules that affect submission intake must be encoded in
`SubmissionArtifactPolicy` and the generated project
`PreSubmitCheckerPolicy`. Chat messages and informal notices are not
enforceable rules until they are moved into those contracts.

Publication of a `ContributionPolicyVersion` is independent of guide
activation and never silently changes existing work. Guide activation binds
one version; task readiness locks it before claimability, and TaskAssignment
plus ReviewLease inherit it without claim-time selection. Human revision
preparation may create a newly prepared task context from a newly active guide
generation; existing rows are never rewritten.

## Consequences

Positive:

- rules become inspectable
- submission intake becomes deterministic
- checkers can be mapped to approved policy requirements
- reviewers have a consistent source of truth
- revision loops have explicit limits and deadlines
- project templates become reusable

Tradeoff:

- project setup takes more discipline
- guide changes need versioning
- policies must be versioned and validated with the guide
