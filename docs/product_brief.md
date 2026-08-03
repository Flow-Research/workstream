# Product Brief

## Product Name

Workstream

## One-Sentence Description

Workstream is governed contribution infrastructure for coordinating,
verifying, and recording work performed by humans, AI agents, or both. It turns
project-defined tasks, immutable submissions, deterministic checks, and
authorized review into trusted `ContributionRecord` facts that applications,
organizations, and economic systems can consume.

## Durable Outcome

Workstream establishes an attributable statement about governed work:

> This authorized actor completed this task under this locked version of the
> project rules, submitted this exact artifact, passed these checks, received
> this authorized review, and achieved this recorded outcome.

Every valid Review creates the reviewer's immutable `completed_review`
`ContributionRecord`. An `accept` decision additionally creates
`FinalAcceptance` and the submitter's immutable `accepted_submission`
`ContributionRecord`. Compensation, points, reputation, reporting, datasets,
model training, and other systems consume these records; they cannot create or
rewrite them.

## Problem

High-quality task work fails for operational reasons more often than technical reasons:

- rules are scattered across chats, markdown, and reviewer memory
- submissions reach reviewers before basic checks pass
- revision feedback is not replayed carefully
- compensation fulfillment status is tracked manually and inconsistently
- reviewers disagree because the project guide is not encoded into the workflow
- operators cannot see the true state of the pipeline

This creates wasted effort, delayed payments, repeated mistakes, and low trust.

## Insight

Across serious task projects, the surface language changes but the lifecycle is stable:

```text
Guide -> Task -> Submission -> Checker -> Review -> Revision/Decision
-> Contribution -> Conditional Compensation Award -> Fulfillment
```

Workstream makes that lifecycle explicit and configurable.

The system is source-agnostic without becoming source-adapter-first. A task
created manually, imported from Markdown or CSV, or later received from an
external origin normalizes into the same Workstream task contract. The source
retains its own experience and operating model; Workstream governs task,
artifact, check, review, and contribution truth underneath.

## Target Users

### Primary User: Contributor

The person who claims assigned work, packages submissions, submits evidence,
monitors their contribution status, and resolves revisions under an
exact-project Submitter grant.

Needs:

- know what to do next
- avoid missing project rules
- package submissions correctly
- track task decisions, contributions, compensation awards, and fulfillment

### Secondary User: Reviewer

The person who checks whether work satisfies the project guide and acceptance criteria.

Needs:

- see only review-ready submissions
- apply a consistent checklist
- issue actionable revision feedback
- avoid reviewing broken packages

### Project Manager And Operator

The covered Project Manager configures project rules and tasks. The Operator
inspects runtime health and performs registered recovery. Actor/grant,
finance, and audit duties remain separate authorities.

Needs:

- create covered project templates
- configure project statuses and checkers
- inspect permission-appropriate review evidence
- track throughput and compensation-award exposure

## MVP Boundary

The first version includes:

- project guide records
- task queue
- task detail
- task contract screening
- submission packet records
- checker framework
- human review workflow
- revision replay
- contribution records
- compensation awards, fulfillment receipts, and status projections
- contribution evidence for a future reputation projection
- status dashboard

## First Operator Value

The first version must make a small operator team better immediately:

- fewer missed project rules before submission
- fewer avoidable needs-revision cycles
- faster review readiness because broken packets are blocked early
- clearer reviewer feedback because findings are structured
- cleaner compensation tracking because contribution, award, and fulfillment
  are separate states
- less dependency on scattered chat memory

If the product does not reduce repeat mistakes and status confusion in the first pilot, it is not yet working.

## v0.1 Task Intake

The only v0.1 intake paths are:

- manual task creation in the app
- import from a controlled markdown or CSV template

External source adapters, origin onboarding, webhook drop notifications,
automated routing, owner-agent execution workspace, and on-chain settlement are
later work. This keeps v0.1 focused on proving the internal lifecycle instead
of integrating every possible source or settlement rail.

The first version excludes:

- built-in AI workspace
- on-chain settlement
- public marketplace
- external client portal
- fully autonomous task routing
- agent identity protocols
- complex dispute arbitration

## Product Promise

Workstream makes governed work independently verifiable and reusable. It tells
source applications and downstream systems what work occurred, which exact
artifact and rules governed it, who was authorized to submit and review it, and
which immutable contribution facts resulted.

Flow Identity is the current v0.1 authentication provider. It verifies external
identity; local Workstream grants and lifecycle guards determine authority.
That implementation choice does not make Workstream Flow-specific.

## First Market Wedge

Start with internal and partner-operated task programs where the team already understands the review loop:

- AI task creation
- technical review
- rubric/evaluation writing
- code/test quality review
- data QA

Avoid broad gig marketplace positioning until the quality engine is proven.

## Success Metrics

The v0.1 pilot is successful when it demonstrates:

- 3 project templates configured
- 20 tasks entered
- 10 submissions created
- 5 review decisions recorded across accept, needs_revision, and reject
- 3 needs-revision loops completed
- 100 percent of submissions have checker results
- 100 percent of valid human reviews have reviewer contribution records
- 100 percent of accepted tasks have evidence and submitter contribution records
- 100 percent of payable contributions have immutable CompensationAwards and
  fulfillment projections
- status dashboard reconciles with manual records
