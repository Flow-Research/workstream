# ADR 0001: Core Scope

## Status

Accepted for 30-day build.

## Decision

Workstream will first build Flow's task evaluation and contribution infrastructure, not the marketplace, not the agent workspace, and not blockchain settlement.

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

The same evaluation and contribution infrastructure can support many project domains if project-specific rules are configurable.

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
