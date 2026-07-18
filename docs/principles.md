# Workstream Principles

## 1. Workstream Owns The Lifecycle

Operators and agents may do the actual work outside Workstream. Workstream owns the source of truth:

- project rules
- task status
- submission history
- checker results
- review decisions
- revision replay
- contribution records
- compensation awards, fulfillment receipts, and projections
- reputation projections when separately implemented

The first product is task evaluation and contribution infrastructure, not an execution IDE.

## 2. Project Guides And Policies Are Law

Each project has a human-facing guide and approved machine-readable policies.

The guide explains:

- task types
- quality bar
- submission format
- common rejection reasons

The policies enforce:

- submission artifact policy
- generated project pre-submit checker policy
- post-submit checker policy
- review policy
- revision policy
- contribution policy

If a rule matters, it belongs in the guide, submission artifact policy, checker
policy, review policy, revision policy, contribution policy, or task template.

Out-of-band guidance is not enforceable until it is moved into those contracts or into a checker that is governed by those contracts.

## 3. Automated Checks Protect Human Time

Human reviewers do not spend time discovering basic package failures. Workstream checkers catch structural issues before review:

- invalid task schema
- missing evidence
- malformed submission packet
- missing required files
- forbidden generated artifacts
- impossible status transitions
- known low-quality signatures

Critical- and high-severity failures block review.

Blocking pre-submit failures block submission creation before a submission version exists.

## 4. Human Review Provides Judgment

Automated checks can enforce structure. Human reviewers decide whether the work is actually good, useful, original, and aligned with the project guide.

Reviewers must produce actionable immutable findings:

- what failed
- why it matters
- what must change
- blocking or advisory lifecycle meaning
- evidence

## 5. Needs Revision Is A First-Class State

Needs revision is not a side note. It is a formal loop:

```text
NEEDS_REVISION -> SUBMITTED -> EVALUATION_PENDING -> REVIEW_PENDING
```

While a task is in `NEEDS_REVISION`, the assigned contributor receives the
frozen preparation, responds to every unresolved blocking finding, and submits
a replacement version. The system preserves immutable findings, responses,
evidence, and later resolutions.

Prior Submissions keep their stamped context. Preparation compares the prior
guide identity/activation sequence with the currently active guide: exact match
keeps, any different valid pair rebases forward or backward, and unsafe context
blocks. Task Context returns the frozen preparation. No guide rebase occurs
during review.

## 6. Compensation Follows Contribution

The first version uses immutable contribution and compensation-award records
with manually recorded fulfillment. Blockchain settlement comes later.

Every valid human Review creates a reviewer contribution. Accept additionally
creates FinalAcceptance, and only that fact creates the submitter contribution.
Compensation attaches to the applicable immutable contribution; explicit unpaid
rules create no award. Reputation remains a separately implemented projection.

`CompensationAward` and `CompensationFulfillmentReceipt` records track:

- contribution and beneficiary
- frozen `ContributionPolicyVersion` and `ContributionAwardDefinition`
- instrument, unit, and exact quantity
- delivery and fulfillment status
- immutable fulfillment receipt and external reference

## 7. Future Reputation Must Be Earned From Outcomes

When separately implemented, reputation is computed from work history rather
than assigned as a profile badge:

- acceptance rate
- revision rate
- rejection rate
- review accuracy
- dispute rate
- average turnaround
- task difficulty
- project weight

## 8. Do Not Copy Private Client Data

Workstream transfers operational ideas and workflow patterns. It must not copy confidential platform data, private task content, client materials, or proprietary evaluation details.

The product is built from our own schemas, rules, examples, and pilot tasks.

## 9. Source-Agnostic Does Not Mean Adapter-First

Workstream accepts work from different sources over time, but v0.1 supports only manual, markdown, and CSV intake.

External origins, webhook drop notifications, automated routing, agent identity, and on-chain settlement are later adapters.
