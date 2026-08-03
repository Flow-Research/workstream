# ADR 0001: Core Scope

## Status

Accepted for v0.1.

## Decision

Workstream will first build the governed contribution core: project-defined
work, immutable submissions, deterministic checks, authorized review, revision,
and trusted contribution records. It will not begin with marketplace discovery,
an execution workspace, external source adapters, or blockchain settlement.

## Context

Across task evaluation and contribution projects, the repeated pattern is:

```text
Project Guide
-> Task
-> Submission
-> Platform Checker
-> Human Review
-> Needs Revision / Accepted / Rejected
-> Contribution Record
-> Conditional Compensation Award / Fulfillment
```

Reputation is a separately approved future consumer of immutable review and
contribution lineage. It is not a v0.1 review-transaction side effect.

The same governed contribution infrastructure can support many project domains
and source applications when project-specific rules are configurable. Flow
Identity is the current external authentication provider, not the product or
scope boundary.

## Consequences

The first version prioritizes:

- project guides
- task queues
- submissions
- checkers
- reviews
- revisions
- evidence
- contribution records
- compensation awards and fulfillment records

Deferred:

- source adapters
- autonomous execution runtime
- marketplace discovery
- blockchain settlement
- external client billing
- reputation policy, events, scoring, and projections

This keeps the build focused on the part that determines quality and acceptance.
