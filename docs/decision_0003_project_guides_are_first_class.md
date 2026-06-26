# ADR 0003: Project Guides Are First-Class Objects

## Status

Accepted

## Context

Different projects use different language and acceptance rules, but they share the same lifecycle.

If project rules live only in chat or loose markdown, operators and reviewers will repeat avoidable mistakes.

## Decision

Every active Workstream project must have a versioned project guide attached to its configuration.

The project guide is the human-facing project source of truth. It may be markdown, an imported document, or a URL-backed guide. Workers and reviewers use it to understand the project purpose, quality bar, instructions, examples, reviewer rubric, and common rejection reasons.

Runtime enforcement uses approved machine-readable policies attached to the guide version. Workstream must not reread guide prose at submission time and guess what to enforce.

The guide drives:

- task requirements
- submission artifact policy
- guide source snapshot and effective project submission artifact policy
- project pre-submit checker policy generated from the effective project submission artifact policy
- post-submit checker policy
- review policy
- revision policy
- payment policy
- common rejection reasons

The submission artifact, checker, review, revision, and payment policies are guide-version policies. They must be tied to the project guide version they govern, not only to the project.

Project guide activation requires the guide plus its required policy context before work can lock against it:

- guide source snapshot
- guide sufficiency report
- submission artifact policy
- effective project submission artifact policy hash
- project pre-submit checker bundle hash
- post-submit checker policy
- review policy
- revision policy
- payment policy

The Workstream-derived submission artifact policy defines project-level intake rules. Project owners provide open-ended project material and business terms. Workstream captures an immutable guide source snapshot, evaluates guide sufficiency, derives the machine policy, and a Workstream actor with the `admin` or `project_manager` role approves the internal policy bundle. Workstream combines that policy with non-bypassable Workstream default artifact rules to create the effective project submission artifact policy, then generates the project pre-submit checker policy from that effective project submission artifact policy. Tasks lock references to the applicable guide snapshot, effective project submission artifact policy hash, and pre-submit checker bundle hash.

Blocking pre-submit failures prevent submission creation. They do not create durable post-submit checker runs and they do not create human review decisions.

Revision policy is not optional. It defines the revision loop contract, including revision limits, revision deadlines, allowed resubmission states, and automatic rejection behavior after the limit.

Guide and policy changes do not silently mutate submitted attempts. A submitted attempt stays tied to the guide and policy versions stamped on that submission. When a task enters `NEEDS_REVISION`, revision policy controls whether the next attempt keeps the prior context or rebases to the latest active guide and policy context.

Rules that affect acceptance judgment may be encoded in the human-facing project guide, review policy, revision policy, payment policy, task template, or checker implementation. Rules that affect submission intake must be encoded in `SubmissionArtifactPolicy` and the generated project `PreSubmitCheckerPolicy`. Chat messages and informal notices are not enforceable rules until they are moved into those contracts.

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
